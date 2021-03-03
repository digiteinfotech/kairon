from abc import ABC
from collections import defaultdict
from enum import Enum
from typing import Union
from urllib.parse import urljoin

from quart import g

from kairon.chat_server.chat_server_utils import ChatServerUtils
from kairon.chat_server.exceptions import ChatServerException


class ChannelInterface(ABC):

    def name(self):
        """
        Name of the bot on channel.
        """
        raise NotImplementedError

    def type(self):
        """
        Type of channel.
        """
        raise NotImplementedError

    def handle_message(self, message):
        """
        Handles any kind of message from the channel.
        """
        raise NotImplementedError


class ChatChannelInterface(ChannelInterface, ABC):

    def send_text(self, sender_id, text):
        """
        Handles text messages from user.
        :return: response for text.
        """
        raise NotImplementedError

    def send_audio(self, sender_id, text):
        """
        Handles audio messages and returns voice message back to the channel.
        """
        raise NotImplementedError


class VoiceChannelInterface(ChannelInterface, ABC):

    def send_voice(self, sender_id, speech):
        """
        Handles voice streams and sends response back to the channel.
        :return:
        """
        raise NotImplementedError


class ChannelFactory:

    @staticmethod
    def create_client(channel_info):
        client = ChannelFactory._get_channel_implementation(channel_info.channel)
        return client(channel_info)

    @staticmethod
    def _get_channel_implementation(channel_type):
        if channel_type == KaironChannels.TELEGRAM:
            return ChannelFactory._create_telegram_client
        else:
            raise ChatServerException("Channel not supported!")

    @staticmethod
    def _create_telegram_client(channel_info):
        bot_name = g.bot
        auth_token = channel_info.credentials['auth_token']
        host = ChatServerUtils.environment['server']['host']
        webhook = urljoin(host, "/telegram/" + bot_name)

        from kairon.chat_server.channels.telegram import KaironTelegramClient
        return KaironTelegramClient(auth_token, bot_name, webhook)


class KaironChannels(str, Enum):
    TELEGRAM = "TELEGRAM"
    FACEBOOK = "FACEBOOK"
    WHATSAPP = "WHATSAPP"
    SLACK = "SLACK"
    HANGOUTS = "HANGOUTS"
    ALEXA = "ALEXA"
    GOOGLEHOME = "GOOGLE HOME"


class ChannelClientDictionary:
    __channel_client_holder = None

    def __init__(self, *args):
        if args:
            self.__channel_client_holder = defaultdict(args)
        else:
            self.__channel_client_holder = defaultdict(dict)

    def get(self, bot: str, channel: KaironChannels):
        if not self.__channel_client_holder[bot] or not self.__channel_client_holder[bot][channel]:
            return {}
        return self.__channel_client_holder[bot][channel]

    def put(self, bot: str, channel: KaironChannels, client: Union[ChatChannelInterface, VoiceChannelInterface]):
        self.__channel_client_holder[bot][channel] = client

    def remove(self, bot: str, channel: KaironChannels):
        self.__channel_client_holder[bot][channel] = {}

    def is_present(self, bot: str, channel: KaironChannels, raise_exception=False):
        exists = False

        if self.__channel_client_holder[bot] and self.__channel_client_holder[bot][channel]:
            exists = True

        if exists and raise_exception:
            raise ChatServerException("Channel already registered!")
        return exists

    def __str__(self):
        return self.__channel_client_holder.__str__()
