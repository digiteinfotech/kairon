from kairon.chat.converters.channels.slack import SlackMessageConverter
from kairon.chat.converters.channels.hangout import HangoutResponseConverter
from kairon.chat.converters.channels.messenger import MessengerResponseConverter
from kairon.chat.converters.channels.whatsapp import WhatsappResponseConverter
from kairon.chat.converters.channels.telegram import TelegramResponseConverter
from kairon.chat.converters.channels.msteams import MSTeamsResponseConverter
from kairon.chat.converters.channels.line import LineResponseConverter
from kairon.shared.constants import ChannelTypes


class ConverterFactory():

    @staticmethod
    def getConcreteInstance(message_type, channel_type):
        class_instance_mapping = {ChannelTypes.SLACK.value: SlackMessageConverter(message_type, channel_type),
                                  ChannelTypes.HANGOUTS.value: HangoutResponseConverter(message_type, channel_type),
                                  ChannelTypes.MESSENGER.value: MessengerResponseConverter(message_type, channel_type),
                                  ChannelTypes.TELEGRAM.value: TelegramResponseConverter(message_type, channel_type),
                                  ChannelTypes.WHATSAPP.value: WhatsappResponseConverter(message_type, channel_type),
                                  ChannelTypes.MSTEAMS.value: MSTeamsResponseConverter(message_type, channel_type),
                                  ChannelTypes.LINE.value: LineResponseConverter(message_type, channel_type)}
        return class_instance_mapping.get(channel_type)
