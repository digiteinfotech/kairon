from typing import Text

from kairon.chat.handlers.channels.clients.whatsapp.dialog360 import BSP360Dialog
from kairon.chat.handlers.channels.clients.whatsapp.cloud import WhatsappCloud
from kairon.exceptions import AppException
from kairon.shared.constants import WhatsappBSPTypes


class WhatsappFactory:

    __clients = {
        "meta": WhatsappCloud,
        WhatsappBSPTypes.bsp_360dialog.value: BSP360Dialog
    }

    @staticmethod
    def get_client(client_type: Text):
        if client_type not in WhatsappFactory.__clients.keys():
            raise AppException(f"{client_type} client is not implemented. Valid clients: {WhatsappFactory.__clients.keys()}!")
        return WhatsappFactory.__clients[client_type]
