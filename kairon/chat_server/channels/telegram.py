import telebot

from kairon.chat_server.channels.channels import ChatChannelInterface, KaironChannels
from kairon.chat_server.processor import KaironMessageProcessor


class KaironTelegramClient(ChatChannelInterface):

    def __init__(self, auth_token, bot_name, webhook):
        self.__bot_name = bot_name
        self.__auth_token = auth_token
        self.__bot = telebot.TeleBot(auth_token)
        self.__bot.set_webhook(webhook, allowed_updates=[])

    @property
    def name(self):
        return self.__bot_name

    @property
    def type(self):
        return KaironChannels.TELEGRAM

    @staticmethod
    def is_text_message(message):
        return message['message'].get('text') is not None

    @staticmethod
    def is_voice_msg(message):
        return message['message'].get('voice') is not None

    def handle_message(self, message):
        """
        Takes text and audio messages and sends response back to the channel
        """
        sender_id = message['message']['chat']['id']
        if self.is_text_message(message):
            response = KaironMessageProcessor.process_text_message(self.name,
                                                                   message['message'].get('text'),
                                                                   sender_id)
            self.send_text(sender_id, response)
        elif self.is_voice_msg(message):
            response = KaironMessageProcessor.process_audio(self.name,
                                                            message['message'].get('voice'),
                                                            sender_id)
            self.send_audio(sender_id, response)
        else:
            response = "Sorry, I was not able to process the message."
            self.send_text(sender_id, response)

    def send_text(self, sender_id, text):
        """
        Handles text messages from user and sends response back to telegram bot.
        """
        self.__bot.send_message(sender_id, text)

    def send_audio(self, sender_id, audio_file):
        """
        Handles voice messages and returns voice message back to the telegram bot.
        """
        self.__bot.send_voice(sender_id, audio_file)
