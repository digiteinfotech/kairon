import requests
from aiohttp import ClientResponseError, ClientConnectionError, ClientError
from aiohttp_retry import ExponentialRetry, RetryClient

from kairon import Utility
from kairon.chat.handlers.channels.clients.whatsapp.cloud import WhatsappCloud
from kairon.shared.constants import WhatsappBSPTypes
from loguru import logger

GUPSHUP_VERSION = 'v3'
INVALID_STATUS_CODES = set(range(400, 600))

class BSPGupshup(WhatsappCloud):
    WHATSAPP_REQUEST_TIMEOUT = 120.0

    def __init__(self, access_token, **kwargs):
        super().__init__(access_token, **kwargs)
        self.access_token = access_token
        self.app_id = kwargs.get('config', {}).get('app_id')
        self.app_name = kwargs.get('config', {}).get('app_id')
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
        """
            @required:
                payload: message request payload
            @optional:
                timeout: request timeout
            @outputs: response json
        """
        r = requests.post(
            f'{self.app}/partner/app/{self.app_id}/{GUPSHUP_VERSION}/message',
            headers=self.auth_args,
            json=payload,
            timeout=timeout
        )
        resp = r.json()
        logger.debug(resp)
        return resp

    async def send_action_async(self, payload, timeout=None, attempts: int = 3, **kwargs):
        """
            @required:
                payload: message request payload
            @optional:
                timeout: request timeout
            @outputs: response json
        """
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

                    if response.status == 200:
                        resp = await response.json()
                        return True, response.status, resp
                    else:
                        try:
                            last_response = await response.json()
                        except Exception:
                            last_response = await response.text()

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

    # async def send_gupshup_template_message(self, recipient, components):
    #     import json
    #
    #     template, message = components
    #
    #     payload = {
    #         "template": template,
    #         "message": message
    #     }
    #
    #     url = f"{self.partner_base_url}/partner/app/{self.app_id}/template/msg"
    #
    #     headers = {
    #         "Authorization": self.access_token,
    #         "Content-Type": "application/x-www-form-urlencoded",
    #         "accept": "application/json"
    #     }
    #
    #     data = {
    #         "destination": recipient,
    #         "source": self.app_name,
    #         "src.name": self.app_name,
    #         "template": json.dumps(template),
    #         "message": json.dumps(message)
    #     }
    #
    #     async with self.channel_client.post(url, headers=headers, data=data) as resp:
    #         response = await resp.json()
    #         status_flag = resp.status == 200
    #
    #     return status_flag, resp.status, response
    def get_url(self, api_type: str) -> str:
        if api_type == "message":
            return f"{self.app}/partner/app/{self.app_id}/{GUPSHUP_VERSION}/message"
        elif api_type == "template":
            return f"{self.partner_base_url}/partner/app/{self.app_id}/template/msg"
        else:
            raise ValueError(f"Unknown api_type: {api_type}")

    async def send_gupshup_template_message(self, recipient, components):
        import json

        template, message = components

        # url = f"{self.partner_base_url}/partner/app/{self.app_id}/template/msg"
        url = self.get_url(api_type="template")

        headers = {
            "Authorization": self.access_token,
            "Content-Type": "application/x-www-form-urlencoded",
            "accept": "application/json"
        }

        data = {
            "destination": recipient,
            "source": self.app_name,
            "src.name": self.app_name,
            "template": json.dumps(template),
            "message": json.dumps(message)
        }

        return await self.send_action_async(
            payload=data,
            url=url,
            headers=headers,
            use_form=True
        )

    async def send_async(self, payload: dict, to_phone_number: str, messaging_type: str,
                         recipient_type: str = 'individual',
                         timeout: float = WHATSAPP_REQUEST_TIMEOUT, tag=None) -> (bool, int, any):
        """
            @required:
                payload: message request payload
                to_phone_number: receiver's phone number
                messaging_type: text/document, etc
            @optional:
                recipient_type: recipient type
                timeout: request timeout
                tag
            @outputs: response json
        """
        if messaging_type not in self.MESSAGING_TYPES:
            raise ValueError('`{}` is not a valid `messaging_type`'.format(messaging_type))

        # url = f'{self.app}/partner/app/{self.app_id}/{GUPSHUP_VERSION}/message'
        url = self.get_url(api_type="message")

        body = {
            'messaging_product': "whatsapp",
            'recipient_type': recipient_type,
            "to": to_phone_number,
            "type": messaging_type,
            messaging_type: payload
        }

        if tag:
            body['tag'] = tag

        return await self.send_action_async(
            payload=body,
            url=url,
            timeout=timeout,
            headers=self.auth_args,
            use_form=False
        )


    def mark_as_read(self, msg_id, timeout=None):
        payload = {"messaging_product": "whatsapp", "status": "read", "message_id": msg_id}
        return self.send_action(payload)

    def get_media_info(self, whatsapp_media_id, config):
        import mimetypes
        import requests

        endpoint = f"{self.base_url}/{whatsapp_media_id}"

        headers = {
            "D360-API-KEY": config.get("api_key")
        }

        resp = requests.get(
            endpoint,
            headers=headers,
            timeout=10
        )

        if resp.status_code != 200:
            raise AppException(
                f"Failed to download media from 360 dialog: {resp.status_code}"
            )

        data = resp.json()

        download_url = data.get("url")

        download_url = download_url.replace(
            "https://lookaside.fbsbx.com",
            "https://waba-v2.360dialog.io"
        )

        mime_type = data.get("mime_type")

        extension = mimetypes.guess_extension(mime_type) or ""

        file_path = f"whatsapp_360_{whatsapp_media_id}{extension}"

        return download_url, headers, file_path

    def __get_template(self, name, language):
        template_exception = None
        template = []
        try:
            for template in BSPGupshup(self.bot, self.user).list_templates(**{'elementName': name}):
                if template.get("languageCode") == language:
                    template = template
                    break
            return template, template_exception
        except Exception as e:
            logger.exception(e)
            template_exception = str(e)
            return template, template_exception
