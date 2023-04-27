from typing import Text

from kairon.shared.channels.broadcast.whatsapp import WhatsappBroadcast
from kairon.shared.constants import ChannelTypes


class MessageBroadcastFactory:

    __clients = {
        ChannelTypes.WHATSAPP.value: WhatsappBroadcast
    }

    @staticmethod
    def get_instance(channel_type: Text):
        return MessageBroadcastFactory.__clients[channel_type]
