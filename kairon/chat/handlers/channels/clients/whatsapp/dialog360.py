from kairon import Utility
from kairon.chat.handlers.channels.clients.whatsapp.on_premise import WhatsappOnPremise


class BSP360Dialog(WhatsappOnPremise):

    def __init__(self, access_token, **kwargs):
        super().__init__(access_token, **kwargs)
        self.access_token = access_token
        self.base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["360dialog"]["waba_base_url"]
        self.api_version = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["360dialog"]["api_version"]
        self.auth_header = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["360dialog"]["auth_header"]
        self.app = f'{self.base_url}/{self.api_version}'

    @property
    def auth_args(self):
        if not hasattr(self, '_auth_args'):
            self._auth_args = {self.auth_header: self.access_token}
        return self._auth_args