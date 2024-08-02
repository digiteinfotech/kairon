import time
from typing import Any

from uuid6 import uuid7
from loguru import logger
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
            "type": "flattened",
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
                logger.info(f"Sending message <{message}> to <{channel} , {sender}>")
                await handler_func(bot, config['config'], sender, message)
            else:
                raise ValueError(f"Channel handler not found for {channel}")

            chat_database_collection = MessageBroadcastProcessor.get_db_client(bot)
            chat_database_collection.insert_one({
                "type": "flattened",
                "tag": 'callback_message',
                "conversation_id": uuid7().hex,
                "timestamp": time.time(),
                "sender_id": sender,
                "data": {
                    "message": str(message),
                    "channel": channel
                }
            })
        else:
            await ChannelMessageDispatcher.handle_default(bot, None, sender, message)


