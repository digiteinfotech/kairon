"""Exotel outbound call client — outbound-action parity with the Twilio client.

Places a call *from* the platform to a customer and connects it to a bot flow,
the Exotel analogue of Twilio's outbound ``initiate_call``. It targets Exotel's
``Calls/connect`` REST API:

    POST https://<api_key>:<api_token>@<subdomain>
         /v1/Accounts/<account_sid>/Calls/connect.json
    From      = customer number to dial
    CallerId  = the bot's Exophone (verified caller id)
    Url       = Exotel App/flow URL that runs the Voicebot (streaming) applet

The client implements the shared :class:`VoiceOutboundBase` interface so it drops
into :class:`VoiceOutboundFactory` alongside Twilio. URL building and response
parsing are pure static methods so they can be unit-tested without any network.
"""
import logging
from typing import Optional

from kairon.exceptions import AppException
from kairon.shared.voice.base import VoiceOutboundBase
from kairon.shared.voice.constants import MAX_CALL_DURATION_LIMIT_SECONDS

logger = logging.getLogger(__name__)

DEFAULT_SUBDOMAIN = "api.exotel.com"
TIME_LIMIT_GRACE_SECONDS = 15


class ExotelOutboundClient(VoiceOutboundBase):
    def __init__(self, account_sid: str, auth_token: str, from_number: str,
                 api_key: Optional[str] = None, api_token: Optional[str] = None,
                 subdomain: Optional[str] = None,
                 time_limit: Optional[int] = None):
        """Store Exotel credentials and subdomain for this client.

        :param account_sid: Exotel account SID
        :param auth_token: Exotel API token (kept for base-class parity)
        :param from_number: verified Exophone used as CallerId
        :param api_key: Exotel API key (defaults to account_sid)
        :param api_token: Exotel API token (defaults to auth_token)
        :param subdomain: Exotel API subdomain (e.g. api.exotel.com / api.in.exotel.com)
        :param time_limit: hard cap on the call length in seconds, enforced by Exotel (``TimeLimit``)
        """
        super().__init__(account_sid, auth_token, from_number)
        self.api_key = api_key or account_sid
        self.api_token = api_token or auth_token
        self.subdomain = subdomain or DEFAULT_SUBDOMAIN
        self.time_limit = time_limit

    @classmethod
    def from_config(cls, config: dict) -> "ExotelOutboundClient":
        """Build a client from a decrypted Exotel channel config dict."""
        time_limit = None
        try:
            max_duration = int(config.get("max_call_duration_seconds") or 0)
        except (TypeError, ValueError):
            max_duration = 0
        if max_duration > 0:
            time_limit = min(max_duration + TIME_LIMIT_GRACE_SECONDS, MAX_CALL_DURATION_LIMIT_SECONDS)
        return cls(
            account_sid=config["account_sid"],
            auth_token=config.get("api_token") or config.get("auth_token", ""),
            from_number=config["phone_number"],
            api_key=config.get("api_key"),
            api_token=config.get("api_token"),
            subdomain=config.get("subdomain"),
            time_limit=time_limit,
        )

    def _connect_url(self) -> str:
        return f"https://{self.subdomain}/v1/Accounts/{self.account_sid}/Calls/connect.json"

    def _scrub(self, text) -> str:
        """Remove the API key/token from any text before it goes into an error message or log."""
        text = str(text)
        for secret in (self.api_key, self.api_token):
            if secret:
                text = text.replace(secret, "***")
        return text

    def place_call(self, to_phone: str, channel_config: dict) -> str:
        """Dial ``to_phone`` and hand the call to the channel's Exotel flow."""
        flow_app_id = channel_config.get("flow_app_id")
        if not flow_app_id:
            raise AppException("flow_app_id is not configured in voice channel config")
        return self.connect_to_flow(to_phone, flow_app_id, channel_config.get("status_url") or None)

    def flow_app_url(self, flow_app_id: str) -> str:
        """Build the Exotel App/flow URL that a connected call is handed to."""
        return f"http://my.exotel.com/{self.account_sid}/exoml/start_voice/{flow_app_id}"

    @staticmethod
    def _parse_call_sid(payload: dict) -> str:
        """Extract the call Sid from an Exotel connect response.

        Tolerant of the ``{"Call": {"Sid": ...}}`` and flat ``{"Sid": ...}`` shapes.
        """
        if not isinstance(payload, dict):
            return ""
        call = payload.get("Call") or payload.get("call") or payload
        if isinstance(call, dict):
            return call.get("Sid") or call.get("sid") or ""
        return ""

    def initiate_call(self, to_phone: str, twiml_url: str, status_callback_url: str = None) -> str:
        """Dial ``to_phone`` and connect it to ``twiml_url``; return the Exotel call Sid.

        ``twiml_url`` keeps the base-class parameter name; for Exotel it is the
        App/flow URL running the streaming applet rather than TwiML.
        """
        import requests

        payload = {"From": to_phone, "CallerId": self.from_number, "Url": twiml_url}
        if self.time_limit:
            payload["TimeLimit"] = str(self.time_limit)
        if status_callback_url:
            payload["StatusCallback"] = status_callback_url
            payload["StatusCallbackMethod"] = "POST"
        try:
            response = requests.post(
                self._connect_url(), data=payload, auth=(self.api_key, self.api_token), timeout=30
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.HTTPError as e:
            status = getattr(e.response, "status_code", "")
            reason = getattr(e.response, "reason", "") or ""
            raise AppException(
                self._scrub(f"Exotel outbound call failed: HTTP {status} {reason}".strip())
            ) from None
        except Exception as e:
            raise AppException(self._scrub(f"Exotel outbound call failed: {type(e).__name__}: {e}")) from None
        call_sid = self._parse_call_sid(data)
        if not call_sid:
            raise AppException(f"Exotel outbound call returned no Sid: {data}")
        logger.info("Exotel outbound call placed to=%s sid=%s", to_phone, call_sid)
        return call_sid

    def connect_to_flow(self, to_phone: str, flow_app_id: str, status_callback_url: str = None) -> str:
        """Dial ``to_phone`` and connect it to the Exotel flow identified by ``flow_app_id``."""
        return self.initiate_call(to_phone, self.flow_app_url(flow_app_id), status_callback_url)
