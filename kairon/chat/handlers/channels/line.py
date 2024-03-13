import logging
from copy import deepcopy
from typing import Dict, Text, Any, List, Optional

from rasa.core.channels.channel import InputChannel, UserMessage, OutputChannel
from rasa.shared.constants import INTENT_MESSAGE_PREFIX
from rasa.shared.core.constants import USER_INTENT_RESTART
from starlette.requests import Request

from kairon.chat.converters.channels.response_factory import ConverterFactory
from kairon.chat.handlers.channels.base import ChannelHandlerBase
from kairon.shared.chat.processor import ChatDataProcessor
from kairon.shared.constants import ChannelTypes
from kairon.shared.models import User
from kairon.chat.agent_processor import AgentProcessor
from kairon import Utility
import json
import aiohttp
import base64
import hashlib
import hmac

logger = logging.getLogger(__name__)


CONST_LINE_REPLY_ENDPOINT = "https://api.line.me/v2/bot/message/reply"


class LineOutput(OutputChannel):
    """Output channel for Line."""

    @classmethod
    def name(cls) -> Text:
        return "line"

    def __init__(self, channel_access_token: Optional[Text]) -> None:
        self.channel_access_token = channel_access_token

    async def _send_message_data(self, recipient_id: Text, message_data: List[Dict], **kwargs: Any) -> None:
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.channel_access_token}'
        }
        data = {
            'replyToken': recipient_id,
            'messages': message_data
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(CONST_LINE_REPLY_ENDPOINT, headers=headers, json=data) as response:
                response = await response.json()

    async def send_text_message(
            self, recipient_id: Text, text: Text, **kwargs: Any
    ) -> None:
        message_data = []
        for message_part in text.strip().split("\n\n"):
            message_data.append({"type": "text", "text": message_part})
        await self._send_message_data(recipient_id, message_data)

    async def send_image_url(
            self, recipient_id: Text, image: Text, **kwargs: Any
    ) -> None:
        message_data = [{"type": "image", "originalContentUrl": image, "previewImageUrl": image}]
        await self._send_message_data(recipient_id, message_data)

    async def send_text_with_buttons(
            self,
            recipient_id: Text,
            text: Text,
            buttons: List[Dict[Text, Any]],
            **kwargs: Any,
    ) -> None:
        actions = []
        for button in buttons:
            if button.get("value"):
                actions.append(
                    {
                        "type": "message",
                        "label": button["title"],
                        "data": button["value"],
                    }
                )
            else:
                actions.append(
                    {
                        "type": "message",
                        "label": button["title"],
                        "data": button["title"],
                    }
                )
        message_data = [
            {
                "type": "template",
                "altText": text,
                "template": {"type": "buttons", "text": text, "actions": actions},
            }]
        await self._send_message_data(recipient_id, message_data)

    async def send_custom_json(self, recipient_id: Text, json_message: Dict[Text, Any], **kwargs: Any) -> None:
        try:
            message = json_message.get("data")
            message_type = json_message.get("type")
            type_list = Utility.system_metadata.get("type_list")
            if message_type is not None and message_type in type_list:
                converter_instance = ConverterFactory.getConcreteInstance(message_type, ChannelTypes.LINE.value)
                msg = await converter_instance.messageConverter(message)
                await self._send_message_data(recipient_id, [msg])
            else:
                message_data = [{"type": "text", "text": str(json_message)}]
                await self._send_message_data(recipient_id, message_data)
        except Exception as e:
            raise Exception(f"Error in line send_custom_json {e}")

class LineHandler(InputChannel, ChannelHandlerBase):
    """line input channel"""
    def __init__(self, bot: Text, user: User, request: Request):
        self.bot = bot
        self.user = user
        self.request = request

    async def validate(self):
        return {"status": "ok"}

    @staticmethod
    def validate_message_authenticity(channel_secret: Text, request_body: Text, signature: Text) -> bool:
        hash_value = hmac.new(channel_secret.encode('utf-8'), request_body.encode('utf-8'), hashlib.sha256).digest()
        return signature == base64.b64encode(hash_value).decode('utf-8')

    async def handle_message(self):
        line = ChatDataProcessor.get_channel_config("line", self.bot, mask_characters=False)
        out_channel = LineOutput(line['config']['channel_access_token'])
        signature = self.request.headers.get("X-Line-Signature")
        if not signature:
            return "success"
        body = await self.request.body()
        body_str = body.decode('utf-8')
        request_dict = json.loads(body)
        events = request_dict.get("events", [])
        if len(events) < 1 or events[0]['type'] != 'message':
            return "success"
        msg_type = events[0]['message']['type']
        if msg_type == 'text':
            text = events[0]['message']['text']
        elif msg_type in ['image', 'video', 'audio', 'file']:
            text = f"k_multimedia_msg{{\"{msg_type}\": \"{events[0]['message']['id']}\"}}"
        elif msg_type == 'location':
            text = f"k_location_msg{{\"latitude\": {events[0]['message']['latitude']}, \"longitude\": {events[0]['message']['longitude']}}}"
        elif msg_type == 'sticker':
            text = f"k_sticker_msg{{\"packageId\": {events[0]['message']['packageId']}, \"stickerId\": {events[0]['message']['stickerId']}}}"
        else:
            logger.warning(f"Received a message from line that we can not handle. Message: {events[0]['message']}")
            return "success"

        sender_id = events[0]['replyToken']

        metadata = {"out_channel": out_channel.name(),
                    "is_integration_user": True, "bot": self.bot, "account": self.user.account,
                    "channel_type": "telegram", "tabname": "default"}
        try:
            if not self.validate_message_authenticity(line['config']['channel_secret'], body_str, signature):
                return "success"

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
            logger.error(f"Exception when trying to handle message for line.{e}")
            logger.debug(e, exc_info=True)
        return "success"

    @staticmethod
    async def process_message(bot: str, user_message: UserMessage):
        await AgentProcessor.get_agent(bot).handle_message(user_message)

    @staticmethod
    def is_validate_hash(request: Request):
        """
        Validates whether the hash present as part of the line channel webhook URL is
        equivalent to the one present as part of the db config.
        """
        bot = request.path_params.get('bot')
        token = request.path_params.get("token")
        messenger_conf = ChatDataProcessor.get_channel_config(ChannelTypes.LINE.value, bot, mask_characters=False)
        secrethash = messenger_conf["meta_config"]["secrethash"]
        secrettoken = messenger_conf["meta_config"]["secrettoken"]
        jwt_token = Utility.decrypt_message(secrettoken)
        return secrethash == token, jwt_token

