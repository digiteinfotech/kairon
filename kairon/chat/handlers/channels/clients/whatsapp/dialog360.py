from kairon import Utility
from kairon.chat.handlers.channels.clients.whatsapp.on_premise import WhatsappOnPremise


class BSP360Dialog(WhatsappOnPremise):
    BASE_URL = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["360dialog"]["waba_base_url"]
    API_VERSION = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["360dialog"]["api_version"]
    AUTH_HEADER = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["360dialog"]["auth_header"]

    def __init__(self, access_token, **kwargs):
        super().__init__(access_token, **kwargs)
        self.access_token = access_token
        self.api_version = BSP360Dialog.API_VERSION
        self.app = f'{BSP360Dialog.BASE_URL}/{BSP360Dialog.API_VERSION}'

    @property
    def auth_args(self):
        if not hasattr(self, '_auth_args'):
            self._auth_args = {BSP360Dialog.AUTH_HEADER: self.access_token}
        return self._auth_args
