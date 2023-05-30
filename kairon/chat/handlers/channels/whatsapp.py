from typing import Optional, Dict, Text, Any, List, Union

from rasa.core.channels import OutputChannel, UserMessage
from tornado.ioloop import IOLoop

from kairon.chat.agent_processor import AgentProcessor
from kairon.chat.handlers.channels.clients.whatsapp.factory import WhatsappFactory
from kairon.chat.handlers.channels.clients.whatsapp.cloud import WhatsappCloud
from kairon.chat.handlers.channels.messenger import MessengerHandler
import json
import logging
from http import HTTPStatus
import html
from tornado.escape import json_decode

from kairon.shared.chat.processor import ChatDataProcessor
from kairon import Utility
from kairon.shared.constants import WhatsappBSPTypes, ChannelTypes

logger = logging.getLogger(__name__)


class Whatsapp:
    """Whatsapp input channel to parse incoming webhooks and send msgs."""

    def __init__(self, config: dict) -> None:
        """Init whatsapp input channel."""
        self.config = config
        self.last_message: Dict[Text, Any] = {}

    @classmethod
    def name(cls) -> Text:
        return ChannelTypes.WHATSAPP.value

    async def message(
            self, message: Dict[Text, Any], metadata: Optional[Dict[Text, Any]], bot: str
    ) -> None:
        """Handle an incoming event from the whatsapp webhook."""

        # quick reply and user message both share 'text' attribute
        # so quick reply should be checked first
        if message.get("type") == "interactive":
            interactive_type = message.get("interactive").get("type")
            text = message["interactive"][interactive_type]["id"]
        elif message.get("type") == "text":
            text = message["text"]['body']
        elif message.get("type") in {"image", "audio", "document", "video"}:
            attachment_info = self.client.get_attachment(message[message["type"]]['id'])
            text = attachment_info.get("url")
            if Utility.check_empty_string(text):
                logger.warning(f"Unable to find url for attachment. Message: {attachment_info}")
        else:
            logger.warning(f"Received a message from whatsapp that we can not handle. Message: {message}")
            return
        message.update(metadata)
        await self._handle_user_message(text, message["from"], message, bot)

    async def __handle_meta_payload(self, payload: Dict, metadata: Optional[Dict[Text, Any]], bot: str) -> None:
        access_token = self.config.get('access_token')
        for entry in payload["entry"]:
            for changes in entry["changes"]:
                self.last_message = changes
                client = WhatsappFactory.get_client("meta")
                self.client = client(access_token, from_phone_number_id=self.get_business_phone_number_id())
                msg_metadata = changes.get("value", {}).get("metadata", {})
                metadata.update(msg_metadata)
                messages = changes.get("value", {}).get("messages")
                for message in messages or []:
                    await self.message(message, metadata, bot)

    async def handle_meta_payload(self, request, metadata: Optional[Dict[Text, Any]], bot: str) -> str:
        msg = "success"
        payload = json_decode(request.body)
        app_secret = self.config["app_secret"]
        signature = request.headers.get("X-Hub-Signature") or ""
        if not MessengerHandler.validate_hub_signature(app_secret, request.body, signature):
            logger.warning("Wrong app secret secret! Make sure this matches the secret in your whatsapp app settings.")
            msg = "not validated"
            return msg

        await self.__handle_meta_payload(payload, metadata, bot)
        return msg

    async def handle_360dialog_payload(self, request, metadata: Optional[Dict[Text, Any]], bot: str) -> str:
        payload = json_decode(request.body)
        if payload.get("messages"):
            IOLoop.current().spawn_callback(self.__handle_360dialog_payload, payload, metadata, bot)
        return "success"

    async def __handle_360dialog_payload(self, payload: Dict, metadata: Optional[Dict[Text, Any]], bot: str) -> None:
        access_token = self.config.get('api_key')
        for msg in payload.get("messages", {}):
            self.last_message = msg
            client = WhatsappFactory.get_client(WhatsappBSPTypes.bsp_360dialog.value)
            self.client = client(access_token, config=self.config,
                                 from_phone_number_id=self.get_business_phone_number_id())
            metadata.update(msg)
            await self.message(msg, metadata, bot)

    def get_business_phone_number_id(self) -> Text:
        if WhatsappBSPTypes.bsp_360dialog.value == self.config.get('bsp_type'):
            return self.last_message.get("from")
        else:
            return self.last_message.get("value", {}).get("metadata", {}).get("phone_number_id", "")

    async def _handle_user_message(
            self, text: Text, sender_id: Text, metadata: Optional[Dict[Text, Any]], bot: str
    ) -> None:
        """Pass on the text to the dialogue engine for processing."""
        out_channel = WhatsappBot(self.client)
        await out_channel.mark_as_read(metadata["id"])
        user_msg = UserMessage(
            text, out_channel, sender_id, input_channel=self.name(), metadata=metadata
        )
        try:
            await self.process_message(bot, user_msg)
        except Exception as e:
            logger.exception("Exception when trying to handle webhook for whatsapp message.")
            logger.exception(e)

    @staticmethod
    async def process_message(bot: str, user_message: UserMessage):
        await AgentProcessor.get_agent(bot).handle_message(user_message)


class WhatsappBot(OutputChannel):
    """A bot that uses whatsapp to communicate."""

    @classmethod
    def name(cls) -> Text:
        return ChannelTypes.WHATSAPP.value

    def __init__(self, whatsapp_client: WhatsappCloud) -> None:
        """Init whatsapp output channel."""
        self.whatsapp_client = whatsapp_client
        super().__init__()

    def send(self, recipient_id: Text, element: Any) -> None:
        """Sends a message to the recipient using the messenger client."""

        # this is a bit hacky, but the client doesn't have a proper API to
        # send messages but instead expects the incoming sender to be present
        # which we don't have as it is stored in the input channel.
        self.whatsapp_client.send(element, recipient_id, "text")

    async def send_text_message(
            self, recipient_id: Text, text: Text, **kwargs: Any
    ) -> None:
        """Send a message through this channel."""

        self.send(recipient_id, {"preview_url": True, "body": text})

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
        self.whatsapp_client.mark_as_read(msg_id)

    async def send_custom_json(
            self,
            recipient_id: Text,
            json_message: Union[List, Dict[Text, Any]],
            **kwargs: Any,
    ) -> None:
        """Sends custom json data to the output."""
        type_list = Utility.system_metadata.get("type_list")
        message = json_message.get("data")
        messagetype = json_message.get("type")
        content_type = {"link": "text", "video": "text", "image": "image", "button": "interactive",
                        "dropdown": "interactive"}
        if messagetype is not None and messagetype in type_list:
            messaging_type = content_type.get(messagetype)
            from kairon.chat.converters.channels.response_factory import ConverterFactory
            converter_instance = ConverterFactory.getConcreteInstance(messagetype, ChannelTypes.WHATSAPP.value)
            response = await converter_instance.messageConverter(message)
            self.whatsapp_client.send(response, recipient_id, messaging_type)
        else:
            self.send(recipient_id, {"preview_url": True, "body": str(json_message)})


class WhatsappHandler(MessengerHandler):
    """Whatsapp input channel implementation. Based on the HTTPInputChannel."""

    async def get(self, bot: str, token: str):
        super().authenticate_channel(token, bot, self.request)
        self.set_status(HTTPStatus.OK)
        messenger_conf = ChatDataProcessor.get_channel_config(ChannelTypes.WHATSAPP.value, bot, mask_characters=False)

        verify_token = messenger_conf["config"]["verify_token"]

        if (self.request.query_arguments.get("hub.verify_token")[0]).decode() == verify_token:
            hub_challenge = (self.request.query_arguments.get("hub.challenge")[0]).decode()
            self.write(html.escape(hub_challenge))
            return
        else:
            logger.warning("Invalid verify token! Make sure this matches your webhook settings on the whatsapp app.")
            self.write(json.dumps({"status": "failure, invalid verify_token"}))
            return

    async def post(self, bot: str, token: str):
        user = super().authenticate_channel(token, bot, self.request)
        channel_conf = ChatDataProcessor.get_channel_config(ChannelTypes.WHATSAPP.value, bot, mask_characters=False)
        whatsapp_channel = Whatsapp(channel_conf["config"])
        client = channel_conf["config"].get("bsp_type", "meta")
        metadata = self.get_metadata(self.request) or {}
        metadata.update({
            "is_integration_user": True, "bot": bot, "account": user.account,
            "channel_type": ChannelTypes.WHATSAPP.value, "bsp_type": client
        })
        client_handlers = {
            "meta": whatsapp_channel.handle_meta_payload,
            WhatsappBSPTypes.bsp_360dialog.value: whatsapp_channel.handle_360dialog_payload
        }
        msg = await client_handlers[client](self.request, metadata, bot)
        self.set_status(HTTPStatus.OK)
        self.write(msg)
        return
