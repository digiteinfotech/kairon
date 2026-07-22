import json
import requests
from aiohttp import ClientResponseError, ClientConnectionError, ClientError
from aiohttp_retry import ExponentialRetry, RetryClient

from kairon import Utility
from kairon.chat.handlers.channels.clients.whatsapp.cloud import WhatsappCloud
from kairon.exceptions import AppException
from kairon.shared.constants import WhatsappBSPTypes
from loguru import logger

INVALID_STATUS_CODES = set(range(400, 600))

class BSPGupshup(WhatsappCloud):
    WHATSAPP_REQUEST_TIMEOUT = 120.0

    def __init__(self, access_token, **kwargs):
        """Initialize BSPGupshup chat client with access token and channel config."""
        super().__init__(access_token, **kwargs)
        self.access_token = access_token
        # config kwarg may be a full channel doc {"config": {...}, "connector_type": ...}
        # or an inner config dict {"app_id": ...} — handle both
        config_kwarg = kwargs.get('config', {})
        inner_config = config_kwarg.get('config', config_kwarg)
        self.app_id = inner_config.get('app_id')
        self.app_name = inner_config.get('app_name')
        self.phone_number = inner_config.get('phone_number')
        self.partner_base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["gupshup"][
            "partner_base_url"]
        self.auth_header = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["gupshup"][
            "auth_header"]
        self.app = f'{self.partner_base_url}'

    @property
    def client_type(self):
        return WhatsappBSPTypes.bsp_gupshup.value

    @property
    def auth_args(self):
        if not hasattr(self, '_auth_args'):
            self._auth_args = {self.auth_header: self.access_token}
        return self._auth_args

    def send_action(self, payload, timeout=None, **kwargs):
        """Send a synchronous Gupshup message."""
        messaging_type = payload.get("type")
        destination = payload.get("to") or payload.get("recipient")
        form_data = {
            "source": self.phone_number,
            "destination": destination,
            "message": json.dumps(self._build_gupshup_message(messaging_type, payload.get(messaging_type, {})))
        }
        r = requests.post(
            self.get_url(api_type="message"),
            headers=self.auth_args,
            data=form_data,
            timeout=timeout
        )
        resp = r.json()
        logger.debug(resp)
        return resp

    async def send_action_async(self, payload, timeout=None, attempts: int = 3, **kwargs):
        """Send an asynchronous Gupshup message with exponential retry."""
        last_status_code = 500
        last_response = None
        try:
            retry_options = ExponentialRetry(attempts=attempts, statuses=INVALID_STATUS_CODES, max_timeout=timeout)
            url = kwargs.get('url')
            use_form = kwargs.get('use_form', False)
            headers = kwargs.get('headers') or self.auth_args

            async with RetryClient(raise_for_status=False, retry_options=retry_options) as client:
                if use_form:
                    request = client.post(url, data=payload, headers=headers)
                else:
                    request = client.post(url, json=payload, headers=headers)
                async with request as response:
                    last_status_code = response.status

                    if response.status in (200, 202):
                        resp = await response.json()
                        logger.debug(f"Gupshup send success: {resp}")
                        return True, response.status, resp
                    else:
                        try:
                            last_response = await response.json()
                        except Exception:
                            last_response = await response.text()
                        logger.error(f"Gupshup send failed: status={last_status_code} url={url} response={last_response}")

            return False, last_status_code, last_response
        except ClientResponseError as cre:
            return False, last_status_code, {"error": str(cre), "response": last_response}
        except ClientConnectionError as cce:
            return False, last_status_code, {"error": str(cce), "response": last_response}
        except ClientError as ce:
            return False, last_status_code, {"error": str(ce), "response": last_response}
        except Exception as e:
            return False, last_status_code, {"error": str(e), "response": last_response}

    async def send_template_message_async(self, name: str, to_phone_number: str, language_code: str = "en",
                                          components: dict = None, namespace: str = None) -> (bool, int, any):
        payload = {
            "language": {
                "code": language_code
            },
            "name": name
        }
        if components:
            payload.update({"components": components})
        return await self.send_async(payload, to_phone_number, messaging_type="template")

    def get_url(self, api_type: str) -> str:
        if api_type == "message":
            # SMSGW apps use /msg (form-encoded); CAPI apps use /v3/message (JSON)
            return f"{self.partner_base_url}/partner/app/{self.app_id}/msg"
        elif api_type == "template":
            return f"{self.partner_base_url}/partner/app/{self.app_id}/template/msg"
        else:
            raise ValueError(f"Unknown api_type: {api_type}")

    def _build_gupshup_message(self, messaging_type: str, payload: dict) -> dict:
        """Map Meta Cloud API message payload to Gupshup SMSGW message format."""
        if messaging_type == "text":
            return {"type": "text", "text": payload.get("body", "")}
        elif messaging_type == "image":
            url = payload.get("link", "")
            return {"type": "image", "originalUrl": url, "previewUrl": url,
                    "caption": payload.get("caption", "")}
        elif messaging_type == "document":
            return {"type": "file", "url": payload.get("link", ""),
                    "filename": payload.get("filename", ""),
                    "caption": payload.get("caption", "")}
        elif messaging_type == "audio":
            return {"type": "audio", "url": payload.get("link", "")}
        elif messaging_type == "video":
            return {"type": "video", "url": payload.get("link", ""),
                    "caption": payload.get("caption", "")}
        elif messaging_type == "location":
            return {"type": "location", "longitude": payload.get("longitude"),
                    "latitude": payload.get("latitude"),
                    "name": payload.get("name", ""), "address": payload.get("address", "")}
        logger.warning(f"Gupshup SMSGW: unsupported messaging_type '{messaging_type}'")
        return {"type": messaging_type}

    async def send_gupshup_template_message(self, recipient, components):
        template, message = components

        url = self.get_url(api_type="template")

        headers = {
            self.auth_header: self.access_token,
            "Content-Type": "application/x-www-form-urlencoded",
            "accept": "application/json"
        }

        data = {
            "destination": recipient,
            "source": self.phone_number or self.app_name,
            "src.name": self.app_name,
            "template": json.dumps(template),
        }
        if message.get("type") != "text":
            data["message"] = json.dumps(message)


        return await self.send_action_async(
            payload=data,
            url=url,
            headers=headers,
            use_form=True
        )

    async def send_broadcast_template_async(self, template_id: str, recipient: str,
                                            language_code: str, components, namespace: str = None):
        if isinstance(components, tuple):
            return await self.send_gupshup_template_message(recipient, components)
        return await self.send_template_message_async(template_id, recipient, language_code, components, namespace)

    async def send_async(self, payload: dict, to_phone_number: str, messaging_type: str,
                         recipient_type: str = 'individual',
                         timeout: float = WHATSAPP_REQUEST_TIMEOUT, tag=None) -> (bool, int, any):
        """Send an async Gupshup message via SMSGW form-encoded endpoint."""
        if messaging_type not in self.MESSAGING_TYPES:
            raise ValueError('`{}` is not a valid `messaging_type`'.format(messaging_type))

        url = self.get_url(api_type="message")

        form_data = {
            "source": self.phone_number,
            "destination": to_phone_number,
            "message": json.dumps(self._build_gupshup_message(messaging_type, payload))
        }

        return await self.send_action_async(
            payload=form_data,
            url=url,
            timeout=timeout,
            headers=self.auth_args,
            use_form=True
        )


    def _v3_url(self):
        return f"{self.partner_base_url}/partner/app/{self.app_id}/v3/message"

    def _v3_headers(self):
        # v3 endpoint uses Authorization header (not token)
        return {"Authorization": self.access_token, "Content-Type": "application/json"}

    def send_statuses(self, payload, timeout):
        r = requests.post(self._v3_url(), headers=self._v3_headers(), json=payload, timeout=timeout)
        resp = r.json()
        return resp

    def mark_as_read(self, msg_id, timeout=None):
        payload = {"messaging_product": "whatsapp", "status": "read", "message_id": msg_id}
        return self.send_statuses(payload, timeout)

    def typing_indicator(self, msg_id, timeout=None):
        payload = {"messaging_product": "whatsapp", "status": "read", "message_id": msg_id,
                   "typing_indicator": {"type": "text"}}
        return self.send_statuses(payload, timeout)

    def get_media_info(self, whatsapp_media_id, config, media_data=None):
        import mimetypes

        headers = {"Authorization": self.access_token}
        logger.debug(media_data)

        if media_data and media_data.get("url"):
            download_url = media_data["url"]
            mime_type = media_data.get("mime_type", "")
            extension = mimetypes.guess_extension(mime_type) or ""
            file_path = f"whatsapp_gupshup_{whatsapp_media_id}{extension}"
            return download_url, headers, file_path

        endpoint = f"{self.partner_base_url}/partner/app/{self.app_id}/media/{whatsapp_media_id}"

        resp = requests.get(endpoint, headers=headers, timeout=10)

        if resp.status_code != 200:
            raise AppException(
                f"Failed to get media info from Gupshup: {resp.status_code}"
            )

        data = resp.json()
        download_url = data.get("url")
        mime_type = data.get("mime_type")
        extension = mimetypes.guess_extension(mime_type) or ""
        file_path = f"whatsapp_gupshup_{whatsapp_media_id}{extension}"

        return download_url, headers, file_path

