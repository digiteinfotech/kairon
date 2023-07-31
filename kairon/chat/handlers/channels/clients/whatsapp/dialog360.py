from kairon import Utility
from kairon.chat.handlers.channels.clients.whatsapp.cloud import WhatsappCloud
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

    def mark_as_read(self, msg_id, timeout=None):
        payload = {"messaging_product": "whatsapp", "status": "read", "message_id": msg_id}
        return self.send_action(payload)
