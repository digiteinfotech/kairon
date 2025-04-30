import json
from typing import Optional, Dict, Text, Any, List, Union

from rasa.core.channels import OutputChannel, UserMessage
from starlette.requests import Request

from kairon.chat.agent_processor import AgentProcessor
from kairon.chat.handlers.channels.clients.whatsapp.factory import WhatsappFactory
from kairon.chat.handlers.channels.clients.whatsapp.cloud import WhatsappCloud
from kairon.chat.handlers.channels.messenger import MessengerHandler
import logging

from kairon.shared.chat.processor import ChatDataProcessor
from kairon import Utility
from kairon.shared.chat.user_media import UserMedia
from kairon.shared.concurrency.actors.factory import ActorFactory
from kairon.shared.constants import ChannelTypes, ActorType
from kairon.shared.models import User

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
        media_ids = None
        if message.get("type") == "interactive":
            interactive_type = message.get("interactive").get("type")
            if interactive_type == "nfm_reply":
                logger.debug(message["interactive"][interactive_type])
                response_json = json.loads(message["interactive"][interactive_type]['response_json'])
                response_json.update({"type": interactive_type})
                entity = json.dumps({"flow_reply": response_json})
                text = f"/k_interactive_msg{entity}"
            else:
                text = message["interactive"][interactive_type]["id"]
        elif message.get("type") == "text":
            text = message["text"]['body']
        elif message.get("type") == "button":
            if message["button"].get("payload") == message["button"].get("text"):
                text = message["button"]["text"]
            else:
                text = f"/k_quick_reply_msg{{\"{'quick_reply'}\": \"{message['button']['payload']}\"}}"
        elif message.get("type") in {"image", "audio", "document", "video", "voice"}:
            if message['type'] == "voice":
                message['type'] = "audio"
            text = f"/k_multimedia_msg{{\"{message['type']}\": \"{message[message['type']]['id']}\"}}"
            media_ids = UserMedia.save_whatsapp_media_content(
                bot=bot,
                sender_id=message["from"],
                whatsapp_media_id=message[message['type']]['id'],
                config=self.config
            )
        elif message.get("type") == "location":
            logger.debug(message['location'])
            text = f"/k_multimedia_msg{{\"latitude\": \"{message['location']['latitude']}\", \"longitude\": \"{message['location']['longitude']}\"}}"
        elif message.get("type") == "order":
            logger.debug(message['order'])
            entity = json.dumps({message["type"]: message['order']})
            text = f"/k_order_msg{entity}"
        elif message.get("type") == "payment":
            logger.debug(message['payment'])
            entity = json.dumps({message["type"]: message['payment']})
            text = f"/k_payment_msg{entity}"
        else:
            logger.warning(f"Received a message from whatsapp that we can not handle. Message: {message}")
            return
        message.update(metadata)
        await self._handle_user_message(text, message["from"], message, bot, media_ids)

    async def handle_meta_payload(self, payload: Dict, metadata: Optional[Dict[Text, Any]], bot: str) -> None:
        provider = self.config.get("bsp_type", "meta")
        access_token = self.__get_access_token()
        for entry in payload["entry"]:
            for changes in entry["changes"]:
                self.last_message = changes
                client = WhatsappFactory.get_client(provider)
                self.client = client(access_token, from_phone_number_id=self.get_business_phone_number_id())
                msg_metadata = changes.get("value", {}).get("metadata", {})
                metadata.update(msg_metadata)
                messages = changes.get("value", {}).get("messages")
                if not messages:
                    statuses = changes.get("value", {}).get("statuses")
                    user = metadata.get('display_phone_number')
                    for status_data in statuses:
                        recipient = status_data.get('recipient_id')
                        ChatDataProcessor.save_whatsapp_audit_log(status_data, bot, user, recipient,
                                                                  ChannelTypes.WHATSAPP.value)
                        if status_data.get('type') == "payment":
                            status_data["from"] = user
                            await self.message(status_data, metadata, bot)
                for message in messages or []:
                    await self.message(message, metadata, bot)

    async def send_message_to_user(self, message: Any, recipient_id: str):
        """Send a message to the user."""
        from kairon.chat.converters.channels.response_factory import ConverterFactory

        is_bps = self.config.get("bsp_type", "meta") == "360dialog"
        client = WhatsappFactory.get_client(self.config.get("bsp_type", "meta"))
        phone_number_id = self.config.get('phone_number_id')
        if not phone_number_id and not is_bps:
            raise ValueError("Phone number not found in channel config")
        access_token = self.__get_access_token()
        c = client(access_token, from_phone_number_id=phone_number_id)
        message_type = "text"
        if isinstance(message, str):
            message = {
                'body': message,
                'preview_url': True
            }
            c.send(message, recipient_id, message_type)
        else:
            content_type = {"link": "text", "video": "video", "image": "image", "button": "interactive",
                            "dropdown": "interactive", "audio": "audio"}
            if isinstance(message, dict):
                message = [message]
            for item in message:
                message_type = content_type.get(item.get('type'))
                message_body = item.get('data')
                if not message_type:
                    c.send({'body': f"{message_body}", 'preview_url': True}, recipient_id, "text")
                else:
                    converter_instance = ConverterFactory.getConcreteInstance(item.get('type'), ChannelTypes.WHATSAPP.value)
                    response = await converter_instance.messageConverter(message_body)
                    c.send(response, recipient_id, message_type)

    async def handle_payload(self, request, metadata: Optional[Dict[Text, Any]], bot: str) -> str:
        msg = "success"
        payload = await request.json()
        request_bytes = await request.body()
        provider = self.config.get("bsp_type", "meta")
        metadata.update({"channel_type": ChannelTypes.WHATSAPP.value, "bsp_type": provider, "tabname": "default"})
        signature = request.headers.get("X-Hub-Signature") or ""
        if provider == "meta":
            if not MessengerHandler.validate_hub_signature(self.config["app_secret"], request_bytes, signature):
                logger.warning("Wrong app secret secret! Make sure this matches the secret in your whatsapp app settings.")
                msg = "not validated"
                return msg

        actor = ActorFactory.get_instance(ActorType.callable_runner.value)
        actor.execute(self.handle_meta_payload, payload, metadata, bot)
        return msg

    def get_business_phone_number_id(self) -> Text:
        return self.last_message.get("value", {}).get("metadata", {}).get("phone_number_id", "")

    async def _handle_user_message(
            self, text: Text, sender_id: Text, metadata: Optional[Dict[Text, Any]], bot: str, media_ids: list[str] = None
    ) -> None:
        """Pass on the text to the dialogue engine for processing."""
        out_channel = WhatsappBot(self.client)
        self.client.metadata = metadata
        await out_channel.mark_as_read(metadata["id"])
        user_msg = UserMessage(
            text, out_channel, sender_id, input_channel=self.name(), metadata=metadata
        )
        try:
            await self.process_message(bot, user_msg, media_ids)
        except Exception as e:
            logger.exception("Exception when trying to handle webhook for whatsapp message.")
            logger.exception(e)

    @staticmethod
    async def process_message(bot: str, user_message: UserMessage, media_ids: list[str] = None):
        await AgentProcessor.handle_channel_message(bot, user_message, media_ids=media_ids)

    def __get_access_token(self):
        provider = self.config.get("bsp_type", "meta")
        if provider == "meta":
            return self.config.get('access_token')
        else:
            return self.config.get('api_key')


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
        content_type = {"link": "text", "video": "video", "image": "image", "button": "interactive",
                        "dropdown": "interactive", "audio": "audio", "formatText": "text"}
        if messagetype is not None and messagetype in type_list:
            messaging_type = content_type.get(messagetype)
            from kairon.chat.converters.channels.response_factory import ConverterFactory
            converter_instance = ConverterFactory.getConcreteInstance(messagetype, ChannelTypes.WHATSAPP.value)
            response = await converter_instance.messageConverter(message)
            resp = self.whatsapp_client.send(response, recipient_id, messaging_type)

            if resp.get("error"):
                bot = kwargs.get("assistant_id")
                message_id = self.whatsapp_client.metadata.get("id")
                user = self.whatsapp_client.metadata.get("display_phone_number")
                if not bot:
                    logger.error("Missing assistant_id in kwargs for failed message logging")
                    return
                logger.error(f"WhatsApp message failed: {resp.get('error')}")
                try:
                    ChatDataProcessor.save_whatsapp_failed_messages(
                        resp, bot, recipient_id, ChannelTypes.WHATSAPP.value,
                        json_message=json_message, message_id=message_id, user=user,
                        metadata=self.whatsapp_client.metadata
                    )
                except Exception as e:
                    logger.error(f"Failed to log WhatsApp error: {str(e)}")
        else:
            self.send(recipient_id, {"preview_url": True, "body": str(json_message)})


class WhatsappHandler(MessengerHandler):
    """Whatsapp input channel implementation. Based on the HTTPInputChannel."""

    def __init__(self, bot: Text, user: User, request: Request):
        super().__init__(bot, user, request)
        self.bot = bot
        self.user = user
        self.request = request

    async def validate(self):
        messenger_conf = ChatDataProcessor.get_channel_config(ChannelTypes.WHATSAPP.value, self.bot, mask_characters=False)

        verify_token = messenger_conf["config"]["verify_token"]

        if self.request.query_params.get("hub.verify_token") == verify_token:
            hub_challenge = self.request.query_params.get("hub.challenge")
            return int(hub_challenge)
        else:
            logger.warning("Invalid verify token! Make sure this matches your webhook settings on the whatsapp app.")
            return {"status": "failure, invalid verify_token"}

    async def handle_message(self):
        channel_conf = ChatDataProcessor.get_channel_config(ChannelTypes.WHATSAPP.value, self.bot, mask_characters=False)
        whatsapp_channel = Whatsapp(channel_conf["config"])
        metadata = self.get_metadata(self.request) or {}
        metadata.update({"is_integration_user": True, "bot": self.bot, "account": self.user.account})
        msg = await whatsapp_channel.handle_payload(self.request, metadata, self.bot)
        return msg
