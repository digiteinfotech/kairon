import logging
from http import HTTPStatus
from typing import Optional, Dict, Text, Any, List, Union

from rasa.core.channels import OutputChannel, UserMessage, InputChannel
from tornado.escape import json_decode
from tornado.ioloop import IOLoop

from kairon import Utility
from kairon.chat.agent_processor import AgentProcessor
from kairon.chat.handlers.channels.clients.waba import WABAClient
from kairon.shared.chat.processor import ChatDataProcessor
from kairon.shared.tornado.handlers.base import BaseHandler

logger = logging.getLogger(__name__)


class WABA:
    """waba input channel to parse incoming webhooks and send msgs."""

    def __init__(self, waba_conf: Dict) -> None:
        """Init waba input channel."""
        self.api_key = waba_conf.get("api_key")
        self.waba_conf = waba_conf
        self.wa_id: Text

    @classmethod
    def name(cls) -> Text:
        return "WABA"

    async def message(
            self, message: Dict[Text, Any], metadata: Optional[Dict[Text, Any]], bot: str
    ) -> None:
        """Handle an incoming event from the waba webhook."""

        # quick reply and user message both share 'text' attribute
        # so quick reply should be checked first
        if message.get("type") == "interactive" and message.get("interactive").get("type") == "button_reply":
            text = message["interactive"]["button_reply"]["id"]
        elif message.get("type") == "text":
            text = message["text"]['body']
        elif message.get("type") in {"image", "audio", "document", "video"}:
            attachment_info = self.client.get_attachment(message[message["type"]]['id'])
            text = attachment_info.get("url")
            if Utility.check_empty_string(text):
                logger.warning(f"Unable to find url for attachment. Message: {attachment_info}")
        else:
            logger.warning(f"Received a message from waba that we can not handle. Message: {message}")
            return
        message.update(metadata)
        await self._handle_user_message(text, message["from"], message, bot)

    async def handle(self, payload: Dict, metadata: Optional[Dict[Text, Any]], bot: str) -> None:
        # for entry in payload["entry"]:

        for msg in payload.get("messages", {}):
            self.wa_id = msg.get("from")
            self.client = WABAClient(self.waba_conf, self.get_business_phone_number_id())
            metadata.update(msg)
            return await self.message(msg, metadata, bot)

    def get_business_phone_number_id(self) -> Text:
        return self.wa_id

    async def _handle_user_message(
            self, text: Text, sender_id: Text, metadata: Optional[Dict[Text, Any]], bot: str
    ) -> None:
        """Pass on the text to the dialogue engine for processing."""
        out_channel = WABABot(self.client)
        await out_channel.mark_as_read(metadata["id"])
        user_msg = UserMessage(
            text, out_channel, sender_id, input_channel=self.name(), metadata=metadata
        )
        try:
            await self.process_message(bot, user_msg)
        except Exception:
            logger.exception("Exception when trying to handle webhook for waba message.")

    @staticmethod
    async def process_message(bot: str, user_message: UserMessage):
        await AgentProcessor.get_agent(bot).handle_message(user_message)


class WABABot(OutputChannel):
    """A bot that uses waba to communicate."""

    @classmethod
    def name(cls) -> Text:
        return "waba"

    def __init__(self, waba_client: WABAClient) -> None:
        """Init waba output channel."""
        self.waba_client = waba_client
        super().__init__()

    def send(self, recipient_id: Text, element: Any) -> None:
        """Sends a message to the recipient using the waba client."""

        # this is a bit hacky, but the client doesn't have a proper API to
        # send messages but instead expects the incoming sender to be present
        # which we don't have as it is stored in the input channel.
        self.waba_client.send(element, recipient_id, "text")

    async def send_text_message(
            self, recipient_id: Text, text: Text, **kwargs: Any
    ) -> None:
        """Send a message through this channel."""

        self.send(recipient_id, {"body": text})

    async def send_image_url(
            self, recipient_id: Text, image: Text, **kwargs: Any
    ) -> None:
        """Sends an image. Default will just post the url as a string."""
        link = kwargs.get("link")
        self.send(recipient_id, {"link": link})

    async def mark_as_read(self, msg_id: Text) -> None:
        """Mark user message as read.
        Args:
            msg_id: message id
        """
        self.waba_client.mark_as_read(msg_id)

    async def send_custom_json(
            self,
            recipient_id: Text,
            json_message: Union[List, Dict[Text, Any]],
            **kwargs: Any,
    ) -> None:
        """Sends custom json data to the output."""
        from kairon.chat.converters.channels.constants import CHANNEL_TYPES
        type_list = Utility.system_metadata.get("type_list")
        message = json_message.get("data")
        messagetype = json_message.get("type")
        content_type = {"link": "text", "video": "text", "image": "image", "button": "interactive"}
        if messagetype is not None and messagetype in type_list:
            messaging_type = content_type.get(messagetype)
            from kairon.chat.converters.channels.response_factory import ConverterFactory
            converter_instance = ConverterFactory.getConcreteInstance(messagetype, CHANNEL_TYPES.WABA.value)
            response = await converter_instance.messageConverter(message)
            self.waba_client.send(response, recipient_id, messaging_type)
        else:
            self.send(recipient_id, {"preview_url": True, "body": str(json_message)})


class WABAHandler(InputChannel, BaseHandler):
    """waba input channel implementation. Based on the HTTPInputChannel."""

    async def post(self, bot: str, token: str):
        user = super().authenticate_channel(token, bot, self.request)

        self.set_status(HTTPStatus.OK)
        self.write("Message received")

        if self.__is_user_message(json_decode(self.request.body)):
            IOLoop.current().spawn_callback(self.__handled_msg_bkground, bot, user, self.request)
        return

    async def __handled_msg_bkground(self, bot: str, user, request):
        waba_conf = ChatDataProcessor.get_channel_config("waba_partner", bot, mask_characters=False)

        config = waba_conf["config"]

        waba = WABA(config)

        metadata = self.get_metadata(request) or {}
        metadata.update({"is_integration_user": True, "bot": bot, "account": user.account, "channel_type": "waba"})
        await waba.handle(json_decode(request.body), metadata, bot)

    def __is_user_message(self, payload):
        if payload.get("messages"):
            return True
        return False