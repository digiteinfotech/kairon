import time
from typing import Any

from fbmessenger import MessengerClient
from uuid6 import uuid7

from kairon.chat.handlers.channels.messenger import MessengerClient, MessengerBot
from kairon.chat.handlers.channels.telegram import TelegramOutput
from kairon.chat.handlers.channels.whatsapp import Whatsapp
from kairon.shared.chat.broadcast.processor import MessageBroadcastProcessor
from kairon.shared.chat.processor import ChatDataProcessor
from kairon.shared.constants import ChannelTypes


class ChannelMessageDispatcher:

    @staticmethod
    async def handle_whatsapp(bot: str, config, sender: str, message: Any):
        whatsapp = Whatsapp(config)
        await whatsapp.send_message_to_user(message, sender)

    @staticmethod
    async def handle_telegram(bot: str, config, sender: str, message: Any):
        access_token = config['access_token']
        telegram = TelegramOutput(access_token)
        if isinstance(message, str):
            await telegram.send_text_message(sender, message)
        else:
            await telegram.send_custom_json(sender, message)

    @staticmethod
    async def handle_facebook(bot: str, config, sender: str, message: Any):
        page_access_token = config['page_access_token']
        messenger = MessengerBot(MessengerClient(page_access_token))
        if isinstance(message, str):
            await messenger.send_text_message(sender, message)
        else:
            await messenger.send_custom_json(sender, message)

    @staticmethod
    async def handle_instagram(bot: str, config, sender: str, message: Any):
        page_access_token = config['page_access_token']
        messenger = MessengerBot(MessengerClient(page_access_token))
        if isinstance(message, str):
            await messenger.send_text_message(sender, message)
        else:
            await messenger.send_custom_json(sender, message)

    @staticmethod
    async def handle_default(bot: str, config, sender: str, message: Any, channel: str = 'default'):
        chat_database_collection = MessageBroadcastProcessor.get_db_client(bot)
        chat_database_collection.insert_one({
            "type": "flatten",
            "tag": 'callback_message',
            "conversation_id": uuid7().hex,
            "timestamp": time.time(),
            "sender_id": sender,
            "data": {
                "message": message,
                "channel": channel
            }
        })

    @staticmethod
    async def dispatch_message(bot: str, sender: str, message: str, channel: str):

        channel_dict = {
            name.lower(): value.value for name, value in ChannelTypes.__members__.items()
        }
        channel_handlers = {
            ChannelTypes.WHATSAPP.value: ChannelMessageDispatcher.handle_whatsapp,
            ChannelTypes.TELEGRAM.value: ChannelMessageDispatcher.handle_telegram,
            ChannelTypes.MESSENGER.value: ChannelMessageDispatcher.handle_facebook,
            ChannelTypes.INSTAGRAM.value: ChannelMessageDispatcher.handle_instagram,
        }

        channel = channel_dict.get(channel, None)
        if channel:
            channel = str(channel)
            config = ChatDataProcessor.get_channel_config(connector_type=channel, bot=bot, mask_characters=False)
            handler_func = channel_handlers.get(channel, None)
            if handler_func:
                await handler_func(bot, config['config'], sender, message)
            else:
                raise ValueError(f"Channel handler not found for {channel}")

            chat_database_collection = MessageBroadcastProcessor.get_db_client(bot)
            chat_database_collection.insert_one({
                "type": "flatten",
                "tag": 'callback_message',
                "conversation_id": uuid7().hex,
                "timestamp": time.time(),
                "sender_id": sender,
                "data": {
                    "message": message,
                    "channel": channel
                }
            })
        else:
            await ChannelMessageDispatcher.handle_default(bot, None, sender, message)
            pass




# from enum import Enum
# from typing import Any
#
# import aiohttp
# from cryptography.fernet import Fernet
#
# from kairon import Utility
# from kairon.exceptions import AppException
# from kairon.shared.chat.data_objects import Channels
#
#
# async def post_request(url: str, data, headers=None):
#     if headers is None:
#         headers = {}
#     async with aiohttp.ClientSession(headers=headers) as session:
#         async with session.post(url, json=data) as response:
#             return await response.json()
#
#
# class ChannelTypes(Enum):
#     WHATSAPP = 'whatsapp'
#     TELEGRAM = 'telegram'
#
#
# class ChannelMessageDispatcher:
#     def __init__(self, bot_id: str, sender_id: str):
#         self.sender_id = sender_id
#         self.bot_id = bot_id
#         self.config = self.get_channel_config()
#
#     @staticmethod
#     def decode_channel_config(config):
#         secret = Utility.environment['security']['fernet_key']
#         fernet = Fernet(secret.encode("utf-8"))
#         decoded_config = {}
#         for key, value in config.items():
#             if isinstance(value, str):
#                 decoded_config[key] = fernet.decrypt(value.encode("utf-8")).decode("utf-8")
#             else:
#                 decoded_config[key] = value
#         return decoded_config
#
#     @staticmethod
#     def fetch_channel_config_data(bot_id: str, channel: str, decode: bool = True):
#
#         if not channel in [channel.value for channel in ChannelTypes]:
#             raise AppException("Invalid channel for fetching config")
#         channel_info = Channels.objects(bot=bot_id, connector_type='telegram').first()
#         if not channel_info:
#             raise AppException("Channel config not found")
#         if decode:
#             return ChannelMessageDispatcher.decode_channel_config(channel_info.config)
#         else:
#             return channel_info.config
#
#     async def get_channel_config(self) -> dict:
#         raise NotImplementedError("get_channel_config method must be implemented in subclass")
#
#     async def send_message(self, message: Any):
#         raise NotImplementedError("send_message method must be implemented in subclass")
#
#
# class TelegramDispatcher(ChannelMessageDispatcher):
#     def __init__(self, bot_id: str, sender_id: str):
#         super().__init__(bot_id, sender_id)
#
#     def get_channel_config(self) -> dict:
#         return ChannelMessageDispatcher.fetch_channel_config_data(self.bot_id, ChannelTypes.TELEGRAM.value)
#
#     async def send_message(self,  message: Any):
#         token = self.config['access_token']
#         send_message_url = f'https://api.telegram.org/bot{token}/sendMessage'
#
#         data = {
#             'chat_id': self.sender_id,
#             'text': str(message)
#         }
#         response = await post_request(send_message_url, data)
#
#
# class WhatsappDispatcher(ChannelMessageDispatcher):
#     def __init__(self, bot_id: str, sender_id: str):
#         self.is_360_dialog = False
#         self.phone_number_id = None
#         super().__init__(bot_id, sender_id)
#
#     def get_channel_config(self) -> dict:
#         config = ChannelMessageDispatcher.fetch_channel_config_data(self.bot_id, ChannelTypes.WHATSAPP.value, False)
#         self.is_360_dialog = config.get('bsp_type', '') == '360dialog'
#         if not self.is_360_dialog:
#             self.phone_number_id = config.get('phone_number_id')
#             if not self.phone_number_id:
#                 raise ValueError("Phone number not found in channel config")
#             config.pop('phone_number_id')
#             config = ChannelMessageDispatcher.decode_channel_config(config)
#         return config
#
#     async def meta_send_message(self, message: Any):
#         text = str(message)
#         api_version = 'v19.0'
#         send_message_url = f'https://graph.facebook.com/{api_version}/{self.phone_number_id}/messages'
#         data = {
#             'messaging_product': 'whatsapp',
#             'recipient_type': 'individual',
#             'to': f'{self.sender_id}',
#             'type': 'text',
#             'text': {'body': text}
#         }
#         token = self.config['access_token']
#         headers = {
#             'Authorization': f'Bearer {token}',
#             'Content-Type': 'application/json'
#         }
#         response = await post_request(send_message_url, data, headers)
#
#     async def dialog_360_send_message(self, message: Any):
#         text = str(message)
#
#         send_message_url = f'https://waba-v2.360dialog.io/messages'
#         data = {
#             'messaging_product': 'whatsapp',
#             'recipient_type': 'individual',
#             'to': f'{self.sender_id}',
#             'type': 'text',
#             'text': {'body': text}
#         }
#         api_key = self.config['api_key']
#         headers = {
#             'D360-API-KEY': f'{api_key}',
#             'Content-Type': 'application/json'
#         }
#         response = await post_request(send_message_url, data, headers)
#
#     async def send_message(self, message: Any):
#         if self.is_360_dialog:
#             await self.dialog_360_send_message(message)
#         else:
#             await self.meta_send_message(message)
#
#
# def get_async_message_dispatcher(bot_id: str, sender_id: str, channel: str):
#     dispatchers = {
#         ChannelTypes.TELEGRAM.value: TelegramDispatcher,
#         ChannelTypes.WHATSAPP.value: WhatsappDispatcher
#     }
#     return dispatchers[channel](bot_id, sender_id)
