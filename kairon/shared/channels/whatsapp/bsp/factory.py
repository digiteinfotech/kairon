from kairon.exceptions import AppException
from kairon.shared.channels.whatsapp.bsp.dialog360 import BSP360Dialog
from kairon.shared.constants import WhatsappBSPTypes


class BusinessServiceProviderFactory:

    __implementations = {
        WhatsappBSPTypes.bsp_360dialog_on_premise.value: BSP360Dialog,
    }

    @staticmethod
    def get_instance(bsp_type):
        if bsp_type not in BusinessServiceProviderFactory.__implementations.keys():
            raise AppException("bsp_type not yet implemented!")
        return BusinessServiceProviderFactory.__implementations[bsp_type]
