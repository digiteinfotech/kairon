"""Helpers for the voice channel: channel config validation, call tracking, voice detection and logging.

Call tracking
-------------
Every call has one *call row* in ``ChannelLogs`` keyed by its ``CallSid``:

  * outbound call -> the row the voice call action wrote (``initiator="bot"``, status ``initiated``)
  * inbound call  -> the ``resolver`` row written when Exotel asked for the stream URL

Status lifecycle:  ``initiated`` -> ``answered`` (stream requested) -> ``completed`` | ``failed``,
or a terminal status reported by the provider's status callback (``busy``, ``no-answer``,
``failed``, ``canceled``) when the call never reached us. ``data.end_reason`` says *why* a call
that reached us ended (caller hung up, bot disconnected, silence timeout, max duration, error).
"""
import json
import logging
import re
from typing import Any, Callable, Mapping, Optional

from kairon.shared.chat.data_objects import ChannelLogs
from kairon.shared.constants import ChannelTypes, KaironSystemSlots
from kairon.shared.utils import Utility
from kairon.shared.voice.constants import (
    DEFAULT_MAX_NOINPUT_ATTEMPTS,
    DEFAULT_NOINPUT_TIMEOUT_SECONDS,
    DEFAULT_SAMPLE_RATE,
    DEFAULT_SPEECH_PROVIDER,
    CallEndReason,
    CallStatus,
    EXCLUDED_CARRY_OVER_SLOTS,
    EXOTEL_DOMAIN_SUFFIX,
    EXOTEL_SAMPLE_RATES,
    MAX_CALL_DURATION_LIMIT_SECONDS,
    MAX_CARRY_OVER_SLOT_CHARS,
    PROVIDER_DEFAULTS,
    PROVIDER_STATUS_MAP,
    TERMINAL_STATUSES,
    UNKNOWN_CALL_SID,
)

logger = logging.getLogger(__name__)

_HOSTNAME = re.compile(
    r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*$"
)
_SYSTEM_SLOTS = {s.value for s in KaironSystemSlots} | EXCLUDED_CARRY_OVER_SLOTS


class VoiceUtils:
    """Static helpers for the voice channel."""

    @staticmethod
    def is_voice_conversation(tracker) -> bool:
        """True only when the conversation is positively identified as a live voice call.

        Both voice paths (Twilio webhook and Exotel stream) send ``input_channel="voice"`` and ``channel_type="voice"``
        in the message metadata. Anything else (web chat sends no channel name at all, WhatsApp, Slack, ...) is not a
        call, so call-only behaviour (placing another call, the hang-up signal) must not run there.
        """
        channel = tracker.get_latest_input_channel()
        if not isinstance(channel, str):
            channel = ((tracker.latest_message or {}).get("metadata") or {}).get(
                "channel_type"
            )
        return channel == ChannelTypes.VOICE.value

    @staticmethod
    def provider_default(service: str, provider: str, key: str) -> Optional[str]:
        """Default ``key`` (``endpoint``, ``model``, ``speaker``) of a speech provider.

        ``service`` is ``stt`` or ``tts``. Taken from ``voice.<service>.<provider>`` in system.yaml, else from
        :data:`PROVIDER_DEFAULTS`. A bot's own speech provider config always wins over both."""
        configured = ((Utility.environment.get("voice") or {}).get(service) or {}).get(
            provider
        ) or {}
        return configured.get(key) or PROVIDER_DEFAULTS.get(service, {}).get(
            provider, {}
        ).get(key)

    @staticmethod
    def apply_exotel_defaults(
        config: dict, error: Callable, registries: Mapping[str, Mapping]
    ) -> None:
        """Validate an Exotel voice channel config in place and fill in its defaults.

        :param config: channel config as submitted (mutated)
        :param error: exception class/callable used to report an invalid value
        :param registries: known STT/TTS providers keyed by config field, e.g.
            ``{"stt_provider": {...}, "tts_provider": {...}}``
        """
        VoiceUtils._validate_subdomain(config, error)
        VoiceUtils._validate_flow_app_id(config, error)
        VoiceUtils._apply_sample_rate(config, error)
        VoiceUtils._apply_call_limits(config, error)
        VoiceUtils._apply_speech_providers(config, error, registries)

    @staticmethod
    def _validate_subdomain(config: dict, error: Callable) -> None:
        """Reject an API host outside ``*.exotel.com``: the channel's credentials are sent to it with every call."""
        subdomain = config.get("subdomain")
        if not subdomain:
            return
        host = str(subdomain).strip().lower()
        if not _HOSTNAME.match(host) or not host.endswith(EXOTEL_DOMAIN_SUFFIX):
            raise error(
                f"Invalid subdomain {subdomain!r}: must be an Exotel host such as api.exotel.com"
            )
        config["subdomain"] = host

    @staticmethod
    def _validate_flow_app_id(config: dict, error: Callable) -> None:
        """``flow_app_id`` is interpolated into a URL path, so it must be the numeric id of the Exotel flow."""
        flow_app_id = config.get("flow_app_id")
        if flow_app_id in (None, ""):
            return
        if not re.fullmatch(r"\d+", str(flow_app_id).strip()):
            raise error(
                f"Invalid flow_app_id {flow_app_id!r}: must be the numeric id of the Exotel flow"
            )
        config["flow_app_id"] = str(flow_app_id).strip()

    @staticmethod
    def _apply_sample_rate(config: dict, error: Callable) -> None:
        """Default ``sample_rate`` to 8000 and reject rates the audio pipeline does not support."""
        raw = config.get("sample_rate")
        if raw in (None, ""):
            config["sample_rate"] = DEFAULT_SAMPLE_RATE
            return
        try:
            rate = int(raw)
        except (TypeError, ValueError):
            rate = None
        if rate not in EXOTEL_SAMPLE_RATES:
            raise error(
                f"Unsupported sample_rate {raw!r}. Supported: {list(EXOTEL_SAMPLE_RATES)}"
            )
        config["sample_rate"] = rate

    @staticmethod
    def _apply_speech_providers(
        config: dict, error: Callable, registries: Mapping[str, Mapping]
    ) -> None:
        """Default ``stt_provider``/``tts_provider`` to sarvam and reject providers missing from their registry."""
        for field, known in registries.items():
            value = config.get(field)
            if value in (None, ""):
                config[field] = DEFAULT_SPEECH_PROVIDER
            elif known and value not in known:
                raise error(
                    f"Unsupported {field} {value!r}. Supported: {sorted(known)}"
                )

    @staticmethod
    def _number(
        config: dict,
        error: Callable,
        field: str,
        default,
        minimum,
        maximum=None,
        integer=False,
    ):
        """The numeric ``field`` of ``config`` (``default`` if blank), raising ``error`` if outside the bounds."""
        raw = config.get(field)
        if raw in (None, ""):
            return default
        try:
            value = int(raw) if integer else float(raw)
        except (TypeError, ValueError):
            value = None
        if (
            value is None
            or value < minimum
            or (maximum is not None and value > maximum)
        ):
            bound = f" and at most {maximum}" if maximum is not None else ""
            raise error(
                f"Invalid {field} {raw!r}: must be a number of at least {minimum}{bound}"
            )
        return int(value) if float(value).is_integer() else value

    @staticmethod
    def _apply_call_limits(config: dict, error: Callable) -> None:
        """Validate/default the call-lifecycle settings kept in the channel config.

        * ``max_call_duration_seconds``: optional hard cap on a call, 1..14400 (absent or 0 = unlimited; updates merge
          with the stored config, so 0 is how a previously set limit is switched off)
        * ``noinput_timeout_seconds``: seconds of caller silence before a reprompt (default 8, 0 disables)
        * ``max_noinput_attempts``: reprompts before saying goodbye and hanging up (default 1)
        """
        max_duration = VoiceUtils._number(
            config,
            error,
            "max_call_duration_seconds",
            None,
            0,
            MAX_CALL_DURATION_LIMIT_SECONDS,
            True,
        )
        if max_duration is None:
            config.pop("max_call_duration_seconds", None)
        else:
            config["max_call_duration_seconds"] = max_duration
        config["noinput_timeout_seconds"] = VoiceUtils._number(
            config, error, "noinput_timeout_seconds", DEFAULT_NOINPUT_TIMEOUT_SECONDS, 0
        )
        config["max_noinput_attempts"] = VoiceUtils._number(
            config,
            error,
            "max_noinput_attempts",
            DEFAULT_MAX_NOINPUT_ATTEMPTS,
            0,
            None,
            True,
        )

    @staticmethod
    def find_call_row(bot: str, call_sid: str):
        """The call row for ``call_sid``: the outbound row the voice action wrote, else the inbound resolver row.

        Rows that only audit a provider status callback are never call rows."""
        row = ChannelLogs.objects(
            bot=bot, type=ChannelTypes.VOICE.value, message_id=call_sid, initiator="bot"
        ).first()
        if row is None:
            row = ChannelLogs.objects(
                bot=bot,
                type=ChannelTypes.VOICE.value,
                message_id=call_sid,
                initiator=None,
                status__in=[
                    "resolver",
                    CallStatus.ANSWERED.value,
                    CallStatus.COMPLETED.value,
                    CallStatus.FAILED.value,
                ],
            ).first()
        return row

    @staticmethod
    def update_call_status(
        bot: str,
        call_sid: str,
        status: str,
        only_if_not_terminal: bool = False,
        **extra,
    ) -> int:
        """Set the status (and extra ``data`` fields) on the call row. Never raises: tracking must not break a call.

        :param only_if_not_terminal: leave the row alone if the call already finished
        :return: number of rows updated
        """
        if not call_sid or call_sid == UNKNOWN_CALL_SID:
            return 0
        try:
            row = VoiceUtils.find_call_row(bot, call_sid)
            if row is None:
                return 0
            updates = {"set__status": status}
            updates.update({f"set__data__{key}": value for key, value in extra.items()})
            query = {"id": row.id}
            if only_if_not_terminal:
                query["status__nin"] = list(TERMINAL_STATUSES)
            return ChannelLogs.objects(**query).update(**updates)
        except Exception as e:
            logger.warning(
                "Could not update call status bot=%s sid=%s: %s", bot, call_sid, e
            )
            return 0

    @staticmethod
    def finish_call(
        bot: str, call_sid: str, end_reason: str, duration_s: Optional[float] = None
    ) -> int:
        """Record how a call that reached us ended."""
        status = (
            CallStatus.FAILED
            if end_reason == CallEndReason.ERROR.value
            else CallStatus.COMPLETED
        ).value
        extra = {"end_reason": end_reason}
        if duration_s is not None:
            extra["duration_s"] = round(float(duration_s), 1)
        return VoiceUtils.update_call_status(bot, call_sid, status, **extra)

    @staticmethod
    def apply_provider_status(
        bot: str,
        call_sid: str,
        provider_status: Optional[str],
        details: Optional[dict] = None,
    ) -> int:
        """Apply a status callback from the telephony provider (the only signal for calls nobody answered).

        ``completed`` is ignored when we already recorded the call's end (our ``end_reason`` is more specific).
        """
        mapped = PROVIDER_STATUS_MAP.get(str(provider_status or "").strip().lower())
        if mapped is None:
            return 0
        extra = {"provider_status": str(provider_status)}
        for key in (
            "Duration",
            "ConversationDuration",
            "DateCreated",
            "StartTime",
            "EndTime",
        ):
            if details and details.get(key):
                extra[f"provider_{key}"] = str(details[key])
        return VoiceUtils.update_call_status(
            bot, call_sid, mapped, only_if_not_terminal=True, **extra
        )

    @staticmethod
    def select_carry_over_slots(slot_values: Optional[dict]) -> dict:
        """Slots from the triggering conversation worth carrying into the call: skip platform slots, empty
        values and anything too large; values are made JSON/BSON safe."""
        carried = {}
        for name, value in (slot_values or {}).items():
            if name in _SYSTEM_SLOTS or value in (None, "", [], {}):
                continue
            safe = VoiceUtils._json_safe(value)
            if safe is None or len(json.dumps(safe)) > MAX_CARRY_OVER_SLOT_CHARS:
                continue
            carried[name] = safe
        return carried

    @staticmethod
    def _json_safe(value) -> Any:
        """``value`` as plain JSON data (unknown objects become strings); ``None`` when it cannot be represented."""
        try:
            return json.loads(json.dumps(value, default=str))
        except Exception:
            return None

    @staticmethod
    def load_call_context(bot: str, call_sid: str) -> dict:
        """Context saved by the voice call action for this outbound call: ``{"slots": {...}, "origin_sender_id": ...}``."""
        if not call_sid:
            return {}
        try:
            row = ChannelLogs.objects(
                bot=bot,
                type=ChannelTypes.VOICE.value,
                message_id=call_sid,
                initiator="bot",
            ).first()
            data = (row.data or {}) if row is not None else {}
            return {
                "slots": data.get("slots") or {},
                "origin_sender_id": data.get("origin_sender_id"),
            }
        except Exception as e:
            logger.warning(
                "Could not load call context bot=%s sid=%s: %s", bot, call_sid, e
            )
            return {}
