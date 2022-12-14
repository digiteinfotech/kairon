from kairon.chat.converters.channels.slack import SlackMessageConverter
from kairon.chat.converters.channels.hangout import HangoutResponseConverter
from kairon.chat.converters.channels.messenger import MessengerResponseConverter
from kairon.chat.converters.channels.whatsapp import WhatsappResponseConverter
from kairon.chat.converters.channels.telegram import TelegramResponseConverter
from kairon.chat.converters.channels.msteams import MSTeamsResponseConverter

class ConverterFactory():

    @staticmethod
    def getConcreteInstance(message_type, channel_type):
        class_instance_mapping = {"slack": SlackMessageConverter(message_type, channel_type),
                      "hangout": HangoutResponseConverter(message_type, channel_type),
                      "messenger": MessengerResponseConverter(message_type, channel_type),
                      "telegram": TelegramResponseConverter(message_type, channel_type),
                      "whatsapp": WhatsappResponseConverter(message_type, channel_type),
                      "msteams":MSTeamsResponseConverter(message_type, channel_type) }
        return class_instance_mapping.get(channel_type)