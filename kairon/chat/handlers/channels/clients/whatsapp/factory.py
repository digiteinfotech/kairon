from typing import Text

from kairon.chat.handlers.channels.clients.whatsapp.dialog360 import BSP360Dialog
from kairon.chat.handlers.channels.clients.whatsapp.cloud import WhatsappCloud
from kairon.chat.handlers.channels.clients.whatsapp.dialog360_cloud import BSP360DialogCloud
from kairon.exceptions import AppException
from kairon.shared.constants import WhatsappBSPTypes


class WhatsappFactory:

    __clients = {
        "meta": WhatsappCloud,
        WhatsappBSPTypes.bsp_360dialog_on_premise.value: BSP360Dialog,
        WhatsappBSPTypes.bsp_360dialog_cloud.value: BSP360DialogCloud
    }

    @staticmethod
    def get_client(client_type: Text):
        if client_type not in WhatsappFactory.__clients.keys():
            raise AppException(f"{client_type} client is not implemented. Valid clients: {WhatsappFactory.__clients.keys()}!")
        return WhatsappFactory.__clients[client_type]
