from kairon import Utility
from kairon.chat.handlers.channels.clients.whatsapp.cloud import WhatsappCloud
from kairon.shared.constants import WhatsappBSPTypes


class BSP360Dialog(WhatsappCloud):

    def __init__(self, access_token, **kwargs):
        super().__init__(access_token, **kwargs)
        self.access_token = access_token
        self.base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["360dialog"]["waba_base_url"]
        self.api_version = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["360dialog"]["api_version"]
        self.auth_header = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["360dialog"]["auth_header"]
        self.app = f'{self.base_url}/{self.api_version}'

    @property
    def client_type(self):
        return WhatsappBSPTypes.bsp_360dialog.value

    @property
    def auth_args(self):
        if not hasattr(self, '_auth_args'):
            self._auth_args = {self.auth_header: self.access_token}
        return self._auth_args
