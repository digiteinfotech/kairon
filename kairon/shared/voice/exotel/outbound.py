"""
Exotel outbound call client — outbound-action parity with the Twilio client.

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

logger = logging.getLogger(__name__)

DEFAULT_SUBDOMAIN = "api.exotel.com"


class ExotelOutboundClient(VoiceOutboundBase):
    def __init__(self, account_sid: str, auth_token: str, from_number: str,
                 api_key: Optional[str] = None, api_token: Optional[str] = None,
                 subdomain: Optional[str] = None, exophone: Optional[str] = None):
        """
        :param account_sid: Exotel account SID
        :param auth_token: Exotel API token (kept for base-class parity)
        :param from_number: caller id / exophone in the account
        :param api_key: Exotel API key (defaults to account_sid)
        :param api_token: Exotel API token (defaults to auth_token)
        :param subdomain: Exotel API subdomain (e.g. api.exotel.com / api.in.exotel.com)
        :param exophone: verified Exophone to use as CallerId (defaults to from_number)
        """
        super().__init__(account_sid, auth_token, from_number)
        self.api_key = api_key or account_sid
        self.api_token = api_token or auth_token
        self.subdomain = subdomain or DEFAULT_SUBDOMAIN
        self.exophone = exophone or from_number

    @classmethod
    def from_config(cls, config: dict) -> "ExotelOutboundClient":
        """Build a client from a decrypted Exotel channel config dict."""
        return cls(
            account_sid=config["account_sid"],
            auth_token=config.get("api_token") or config.get("auth_token", ""),
            from_number=config.get("exophone") or config.get("phone_number", ""),
            api_key=config.get("api_key"),
            api_token=config.get("api_token"),
            subdomain=config.get("subdomain"),
            exophone=config.get("exophone"),
        )

    def _connect_url(self) -> str:
        return (
            f"https://{self.api_key}:{self.api_token}@{self.subdomain}"
            f"/v1/Accounts/{self.account_sid}/Calls/connect.json"
        )

    def flow_app_url(self, flow_app_id: str) -> str:
        """Build the Exotel App/flow URL that a connected call is handed to."""
        return f"http://my.exotel.com/{self.account_sid}/exoml/start_voice/{flow_app_id}"

    @staticmethod
    def _parse_call_sid(payload: dict) -> str:
        """Extract the call Sid from an Exotel connect response (tolerant of the
        ``{"Call": {"Sid": ...}}`` and flat ``{"Sid": ...}`` shapes)."""
        if not isinstance(payload, dict):
            return ""
        call = payload.get("Call") or payload.get("call") or payload
        if isinstance(call, dict):
            return call.get("Sid") or call.get("sid") or ""
        return ""

    def initiate_call(self, to_phone: str, twiml_url: str, status_callback_url: str = None) -> str:
        """Dial ``to_phone`` and connect the call to ``twiml_url`` (the Exotel
        App/flow URL running the streaming applet). Returns the Exotel call Sid.

        ``twiml_url`` keeps the base-class parameter name; for Exotel it is the
        flow/App URL rather than TwiML.
        """
        import requests

        payload = {"From": to_phone, "CallerId": self.exophone, "Url": twiml_url}
        if status_callback_url:
            payload["StatusCallback"] = status_callback_url
            payload["StatusCallbackMethod"] = "POST"
        try:
            response = requests.post(self._connect_url(), data=payload, timeout=30)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            raise AppException(f"Exotel outbound call failed: {e}") from e
        call_sid = self._parse_call_sid(data)
        if not call_sid:
            raise AppException(f"Exotel outbound call returned no Sid: {data}")
        logger.info("Exotel outbound call placed to=%s sid=%s", to_phone, call_sid)
        return call_sid

    def connect_to_flow(self, to_phone: str, flow_app_id: str, status_callback_url: str = None) -> str:
        """Convenience: dial ``to_phone`` and connect it to the Exotel flow
        identified by ``flow_app_id``."""
        return self.initiate_call(to_phone, self.flow_app_url(flow_app_id), status_callback_url)
