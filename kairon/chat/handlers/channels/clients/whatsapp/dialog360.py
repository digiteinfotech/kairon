from loguru import logger

from kairon import Utility
from kairon.chat.handlers.channels.clients.whatsapp.cloud import WhatsappCloud
from kairon.shared.constants import WhatsappBSPTypes


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

    async def send_action(self, payload, timeout=None, **kwargs):
        """
            @required:
                payload: message request payload
            @optional:
                timeout: request timeout
            @outputs: response json
        """
        is_streaming_resp = kwargs.get("stream", False)
        url = '{app}/messages'.format(app=self.app)
        resp = await self.client.request("POST", url, headers=self.auth_args, request_body=payload, timeout=timeout,
                                              return_json=False, is_streaming_resp=is_streaming_resp, max_retries=3)
        await self.client.cleanup()
        logger.debug(resp)
        return resp

    async def mark_as_read(self, msg_id, timeout=None):
        payload = {"messaging_product": "whatsapp", "status": "read", "message_id": msg_id}
        return await self.send_action(payload)
