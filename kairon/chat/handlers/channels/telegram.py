import logging
from copy import deepcopy
from typing import Dict, Text, Any, List, Optional

from rasa.core.channels.channel import InputChannel, UserMessage, OutputChannel
from rasa.shared.constants import INTENT_MESSAGE_PREFIX
from rasa.shared.core.constants import USER_INTENT_RESTART
from rasa.shared.exceptions import RasaException
from starlette.requests import Request
from telebot import TeleBot
from telebot.apihelper import ApiTelegramException
from telebot.types import (
    InlineKeyboardButton,
    Update,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Message,
)

from kairon.chat.handlers.channels.base import ChannelHandlerBase
from kairon.shared.chat.processor import ChatDataProcessor
from kairon.shared.constants import ChannelTypes
from kairon.shared.models import User
from kairon.chat.agent_processor import AgentProcessor
from kairon import Utility
from kairon.chat.converters.channels.response_factory import ConverterFactory
from kairon.chat.converters.channels.responseconverter import ElementTransformerOps
import json

logger = logging.getLogger(__name__)


class TelegramOutput(TeleBot, OutputChannel):
    """Output channel for Telegram."""

    # skipcq: PYL-W0236
    @classmethod
    def name(cls) -> Text:
        return "telegram"

    def __init__(self, access_token: Optional[Text]) -> None:
        super().__init__(access_token)

    async def send_text_message(
            self, recipient_id: Text, text: Text, **kwargs: Any
    ) -> None:
        for message_part in text.strip().split("\n\n"):
            self.send_message(recipient_id, message_part)

    async def send_image_url(
            self, recipient_id: Text, image: Text, **kwargs: Any
    ) -> None:
        self.send_photo(recipient_id, image)

    async def send_text_with_buttons(
            self,
            recipient_id: Text,
            text: Text,
            buttons: List[Dict[Text, Any]],
            button_type: Optional[Text] = "inline",
            **kwargs: Any,
    ) -> None:
        """Sends a message with keyboard.

        For more information: https://core.telegram.org/bots#keyboards

        :button_type inline: horizontal inline keyboard

        :button_type vertical: vertical inline keyboard

        :button_type reply: reply keyboard
        """
        if button_type == "inline":
            reply_markup = InlineKeyboardMarkup()
            button_list = [
                InlineKeyboardButton(s["title"], callback_data=s["payload"])
                for s in buttons
            ]
            reply_markup.row(*button_list)

        elif button_type == "vertical":
            reply_markup = InlineKeyboardMarkup()
            [
                reply_markup.row(
                    InlineKeyboardButton(s["title"], callback_data=s["payload"])
                )
                for s in buttons
            ]

        elif button_type == "reply":
            reply_markup = ReplyKeyboardMarkup(
                resize_keyboard=False, one_time_keyboard=True
            )
            # drop button_type from button_list
            button_list = [b for b in buttons if b.get("title")]
            for idx, button in enumerate(buttons):
                if isinstance(button, list):
                    reply_markup.add(KeyboardButton(s["title"]) for s in button)
                else:
                    reply_markup.add(KeyboardButton(button["title"]))
        else:
            logger.error(
                "Trying to send text with buttons for unknown "
                "button type {}".format(button_type)
            )
            return

        self.send_message(recipient_id, text, reply_markup=reply_markup)

    async def send_custom_json(
            self, recipient_id: Text, json_message: Dict[Text, Any], **kwargs: Any
    ) -> None:
        json_message = deepcopy(json_message)

        recipient_id = json_message.pop("chat_id", recipient_id)

        send_functions = {
            ("text",): "send_message",
            ("photo",): "send_photo",
            ("audio",): "send_audio",
            ("document",): "send_document",
            ("sticker",): "send_sticker",
            ("video",): "send_video",
            ("video_note",): "send_video_note",
            ("animation",): "send_animation",
            ("voice",): "send_voice",
            ("media",): "send_media_group",
            ("latitude", "longitude", "title", "address"): "send_venue",
            ("latitude", "longitude"): "send_location",
            ("phone_number", "first_name"): "send_contact",
            ("game_short_name",): "send_game",
            ("action",): "send_chat_action",
            (
                "title",
                "decription",
                "payload",
                "provider_token",
                "start_parameter",
                "currency",
                "prices",
            ): "send_invoice",
        }

        try:
            message = json_message.get("data")
            message_type = json_message.get("type")
            type_list = Utility.system_metadata.get("type_list")
            if message_type is not None and message_type in type_list:
                converter_instance = ConverterFactory.getConcreteInstance(message_type, ChannelTypes.TELEGRAM.value)
                ops_type = json_message.get("type")
                response = await converter_instance.messageConverter(message)
                response_list = []
                if ops_type == "image":
                    response_list.append(response.get("photo"))
                    del response["photo"]
                    api_call = getattr(self, send_functions[("photo",)])
                    api_call(recipient_id, *response_list, **response)
                elif ops_type in ["link", "video", "formatText"]:
                    response_list.append(response.get("text"))
                    del response["text"]
                    api_call = getattr(self, send_functions[("text",)])
                    api_call(recipient_id, *response_list, **response)
                elif ops_type in ["button"]:
                    body_default = ElementTransformerOps.getChannelConfig(ChannelTypes.TELEGRAM.value, "body_message")
                    logger.debug(f"body_default: {body_default}")
                    logger.debug(f"response: {response}")
                    logger.debug(f"json.dumps(response): {json.dumps(response)}")
                    self.send_message(recipient_id, text=body_default, reply_markup=json.dumps(response))
            else:
                self.send_message(recipient_id, str(json_message))
        except Exception as ap:
            raise Exception(f"Error in telegram send_custom_json {str(ap)}")


class TelegramHandler(InputChannel, ChannelHandlerBase):

    """Telegram input channel"""

    def __init__(self, bot: Text, user: User, request: Request):
        self.bot = bot
        self.user = user
        self.request = request

    @staticmethod
    def _is_location(message: Message) -> bool:
        return message.location is not None

    @staticmethod
    def _is_user_message(message: Message) -> bool:
        return message.text is not None

    @staticmethod
    def _is_edited_message(message: Update) -> bool:
        return message.edited_message is not None

    @staticmethod
    def _is_button(message: Update) -> bool:
        return message.callback_query is not None

    async def validate(self):
        return {"status": "ok"}

    async def handle_message(self):
        telegram = ChatDataProcessor.get_channel_config("telegram", self.bot, mask_characters=False)
        out_channel = TelegramOutput(telegram['config']['access_token'])
        request_dict = await self.request.json()
        update = Update.de_json(request_dict)
        if not out_channel.get_me().username == telegram['config'].get("username_for_bot"):
            logger.debug("Invalid access token, check it matches Telegram")
            return "failed"

        if self._is_button(update):
            msg = update.callback_query.message
            text = update.callback_query.data
        elif self._is_edited_message(update):
            msg = update.edited_message
            text = update.edited_message.text
        else:
            msg = update.message
            if self._is_user_message(msg):
                text = msg.text.replace("/bot", "")
            elif self._is_location(msg):
                text = '{{"lng":{0}, "lat":{1}}}'.format(
                    msg.location.longitude, msg.location.latitude
                )
            else:
                return "success"
        sender_id = msg.chat.id
        metadata = {"out_channel": out_channel.name(), "is_integration_user": True, "bot": self.bot, "account": self.user.account,
                    "channel_type": "telegram", "tabname": "default"}
        try:
            if text == (INTENT_MESSAGE_PREFIX + USER_INTENT_RESTART):
                await self.process_message(self.bot, UserMessage(
                        text,
                        out_channel,
                        sender_id,
                        input_channel=self.name(),
                        metadata=metadata,
                    ))
                await self.process_message(self.bot, UserMessage(
                        "/start",
                        out_channel,
                        sender_id,
                        input_channel=self.name(),
                        metadata=metadata,
                    ))
            else:
                await self.process_message(self.bot, UserMessage(
                        text,
                        out_channel,
                        sender_id,
                        input_channel=self.name(),
                        metadata=metadata,
                    ))
        except Exception as e:
            logger.error(f"Exception when trying to handle message.{e}")
            logger.debug(e, exc_info=True)
        return "success"

    @staticmethod
    async def process_message(bot: str, user_message: UserMessage):
        await AgentProcessor.handle_channel_message(bot, user_message)

    @staticmethod
    def get_output_channel(access_token, webhook_url) -> TelegramOutput:
        """Loads the telegram channel."""
        channel = TelegramOutput(access_token)

        try:
            channel.set_webhook(url=webhook_url)
        except ApiTelegramException as error:
            raise RasaException(
                "Failed to set channel webhook: " + str(error)
            ) from error

        return channel


