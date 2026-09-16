import logging
from typing import List

from starlette.requests import Request

from kairon.chat.handlers.channels.clients.voice.base import VoiceProviderBase
from kairon.shared.chat.data_objects import ChannelLogs

logger = logging.getLogger(__name__)

_STREAM_CONNECT_TEMPLATE = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    "<Response>"
    "<Connect>"
    '<Stream url="{stream_url}"/>'
    "</Connect>"
    "</Response>"
)

_GREETING_TEMPLATE = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    "<Response>"
    '<Play url="{wav_url}"/>'
    "<Connect>"
    '<Stream url="{stream_url}"/>'
    "</Connect>"
    "</Response>"
)


def _derive_stream_url(call_url: str) -> str:
    """Convert the HTTPS call_url to the WSS stream_url for the same bot/token."""
    url = call_url.replace("https://", "wss://", 1).replace("http://", "ws://", 1)
    # /call/{token} → /stream/{token}
    return url.replace("/call/", "/stream/", 1)


class ExotelVoiceProvider(VoiceProviderBase):
    """Exotel telephony provider — uses WebSocket media streaming."""

    def is_streaming(self) -> bool:
        """Return True; Exotel delivers audio over a persistent WebSocket stream."""
        return True

    @classmethod
    def supports_dynamic_resolver(cls) -> bool:
        """Return True; Exotel fetches a dynamic WSS URL from the resolver endpoint."""
        return True

    def validate_signature(self, request: Request, url: str, form_params: dict) -> bool:
        # Exotel does not sign webhooks with a per-request HMAC; always accept.
        return True

    def build_voice_response(self, messages: List[str], call_url: str) -> str:
        """Return ExoML that connects the call to the bot's WebSocket stream."""
        stream_url = self.config.get("stream_url") or _derive_stream_url(call_url)
        return _STREAM_CONNECT_TEMPLATE.format(stream_url=stream_url)

    def build_hangup_response(self, messages: List[str]) -> str:
        """Return ExoML that terminates the active call."""
        return '<?xml version="1.0" encoding="UTF-8"?><Response><Hangup/></Response>'

    async def handle_call_status(self, request: Request, bot: str) -> None:
        """Log Exotel call-status webhook payload to ChannelLogs."""
        form = dict(await request.form())
        call_status = form.get("Status") or form.get("CallStatus", "unknown")
        call_sid = form.get("CallSid", "unknown")
        logger.info("Exotel call status — bot=%s sid=%s status=%s", bot, call_sid, call_status)
        ChannelLogs(
            type="voice",
            status=call_status,
            data=form,
            message_id=call_sid,
            bot=bot,
            user=self.config.get("user", "system"),
        ).save()

    def validate_config(self, config: dict) -> None:
        """Raise AppException if any required Exotel credential field is absent."""
        from kairon.exceptions import AppException
        for field in ["api_key", "api_token", "account_sid", "exophone"]:
            if not config.get(field):
                raise AppException(f"Missing required Exotel voice config field: {field}")

    def _generate_stream_wss_url(self, bot: str, user: str, params: dict) -> str:
        """Generate a short-lived WSS stream URL with a bot/stream-scoped token."""
        from urllib.parse import urlencode, urljoin
        from kairon.shared.auth import Authentication
        from kairon.shared.data.constant import ACCESS_ROLES, TOKEN_TYPE
        from kairon.shared.utils import Utility

        # TODO: read expiry from BotSettings.voice_stream_token_expiry_minutes (default 30)
        token, _ = Authentication.generate_integration_token(
            bot=bot,
            user=user,
            role=ACCESS_ROLES.CHAT.value,
            expiry=30,
            access_limit=[f"/api/bot/{bot}/channel/voice/exotel/stream/.+"],
            token_type=TOKEN_TYPE.CHANNEL.value,
        )
        base = Utility.environment["model"]["agent"]["url"]
        base_wss = base.replace("https://", "wss://", 1).replace("http://", "ws://", 1)
        stream_path = f"/api/bot/{bot}/channel/voice/exotel/stream/{token}"
        query_keys = ("CallSid", "From", "To", "Direction")
        qs = urlencode({k: v for k, v in params.items() if k in query_keys and v})
        stream_url = urljoin(base_wss, stream_path)
        if qs:
            stream_url = f"{stream_url}?{qs}"
        return stream_url

    def build_resolver_response(self, params: dict, bot: str, user: str) -> dict:
        """Return JSON payload for Exotel dynamic HTTP(S) resolver — contains WSS stream URL."""
        stream_url = self._generate_stream_wss_url(bot, user, params)
        logger.info("Exotel resolver: bot=%s stream_url=%s", bot, stream_url)
        return {"url": stream_url}

    def build_greeting_response(self, params: dict, bot: str, user: str) -> str:
        """Return ExoML that plays greeting WAV then connects to WSS stream."""
        from kairon.exceptions import AppException
        wav_url = self.config.get("greeting_wav_url")
        if not wav_url:
            raise AppException("greeting_wav_url not configured in channel config")
        stream_url = self._generate_stream_wss_url(bot, user, params)
        logger.info("Exotel greeting: bot=%s wav_url=%s stream_url=%s", bot, wav_url, stream_url)
        return _GREETING_TEMPLATE.format(wav_url=wav_url, stream_url=stream_url)
