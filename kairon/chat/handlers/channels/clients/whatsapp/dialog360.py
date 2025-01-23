
from aiohttp import ClientResponseError, ClientConnectionError, ClientError
from aiohttp_retry import ExponentialRetry, RetryClient

from kairon import Utility
from kairon.chat.handlers.channels.clients.whatsapp.cloud import WhatsappCloud, INVALID_STATUS_CODES
from kairon.shared.constants import WhatsappBSPTypes
from loguru import logger


class BSP360Dialog(WhatsappCloud):

    def __init__(self, access_token, **kwargs):
        super().__init__(access_token, **kwargs)
        self.access_token = access_token
        self.base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["360dialog"]["waba_base_url"]
        self.auth_header = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["360dialog"]["auth_header"]
        self.app = f'{self.base_url}'

    @property
    def client_type(self):
        return WhatsappBSPTypes.bsp_360dialog.value

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
        r = self.session.post(
            '{app}/messages'.format(app=self.app),
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
            url = f'{self.app}/messages'

            async with RetryClient(raise_for_status=False, retry_options=retry_options) as client:
                async with client.post(url, json=payload, headers=self.auth_args ) as response:
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


    def mark_as_read(self, msg_id, timeout=None):
        payload = {"messaging_product": "whatsapp", "status": "read", "message_id": msg_id}
        return self.send_action(payload)
