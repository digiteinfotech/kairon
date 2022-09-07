import hashlib
import hmac
import json
import logging
from http import HTTPStatus
from typing import Text, List, Dict, Any, Iterable, Optional, Union
import html
import rasa.shared.utils.io
from fbmessenger import MessengerClient
from fbmessenger.attachments import Image
from fbmessenger.elements import Text as FBText
from fbmessenger.quick_replies import QuickReplies, QuickReply
from fbmessenger.sender_actions import SenderAction
from rasa.core.channels.channel import UserMessage, OutputChannel, InputChannel
from tornado.escape import json_decode

from kairon.chat.agent_processor import AgentProcessor
from kairon.shared.chat.processor import ChatDataProcessor
from kairon.shared.tornado.handlers.base import BaseHandler
from kairon import Utility
from kairon.chat.converters.channels.response_factory import ConverterFactory
from kairon.chat.converters.channels.constants import CHANNEL_TYPES

logger = logging.getLogger(__name__)


class Messenger:
    """Implement a fbmessenger to parse incoming webhooks and send msgs."""

    @classmethod
    def name(cls) -> Text:
        return "facebook"

    def __init__(
            self,
            page_access_token: Text,
    ) -> None:

        self.client = MessengerClient(page_access_token)
        self.last_message: Dict[Text, Any] = {}

    def get_user_id(self) -> Text:
        return self.last_message.get("sender", {}).get("id", "")

    @staticmethod
    def _is_audio_message(message: Dict[Text, Any]) -> bool:
        """Check if the users message is a recorded voice message."""
        return (
                "message" in message
                and "attachments" in message["message"]
                and message["message"]["attachments"][0]["type"] == "audio"
        )

    @staticmethod
    def _is_image_message(message: Dict[Text, Any]) -> bool:
        """Check if the users message is an image."""
        return (
                "message" in message
                and "attachments" in message["message"]
                and message["message"]["attachments"][0]["type"] == "image"
        )

    @staticmethod
    def _is_video_message(message: Dict[Text, Any]) -> bool:
        """Check if the users message is a video."""
        return (
                "message" in message
                and "attachments" in message["message"]
                and message["message"]["attachments"][0]["type"] == "video"
        )

    @staticmethod
    def _is_file_message(message: Dict[Text, Any]) -> bool:
        """Check if the users message is a file."""
        return (
                "message" in message
                and "attachments" in message["message"]
                and message["message"]["attachments"][0]["type"] == "file"
        )

    @staticmethod
    def _is_user_message(message: Dict[Text, Any]) -> bool:
        """Check if the message is a message from the user"""
        return (
                "message" in message
                and "text" in message["message"]
                and not message["message"].get("is_echo")
        )

    @staticmethod
    def _is_quick_reply_message(message: Dict[Text, Any]) -> bool:
        """Check if the message is a quick reply message."""
        return (
                message.get("message") is not None
                and message["message"].get("quick_reply") is not None
                and message["message"]["quick_reply"].get("payload")
        )

    async def handle(self, payload: Dict, metadata: Optional[Dict[Text, Any]], bot: str) -> None:
        for entry in payload["entry"]:
            for message in entry["messaging"]:
                self.last_message = message
                if message.get("message"):
                    return await self.message(message, metadata, bot)
                elif message.get("postback"):
                    return await self.postback(message, metadata, bot)

    async def message(
            self, message: Dict[Text, Any], metadata: Optional[Dict[Text, Any]], bot: str
    ) -> None:
        """Handle an incoming event from the fb webhook."""

        # quick reply and user message both share 'text' attribute
        # so quick reply should be checked first
        if self._is_quick_reply_message(message):
            text = message["message"]["quick_reply"]["payload"]
        elif self._is_user_message(message):
            text = message["message"]["text"]
        elif self._is_audio_message(message):
            attachment = message["message"]["attachments"][0]
            text = attachment["payload"]["url"]
        elif self._is_image_message(message):
            attachment = message["message"]["attachments"][0]
            text = attachment["payload"]["url"]
        elif self._is_video_message(message):
            attachment = message["message"]["attachments"][0]
            text = attachment["payload"]["url"]
        elif self._is_file_message(message):
            attachment = message["message"]["attachments"][0]
            text = attachment["payload"]["url"]
        else:
            logger.warning(
                "Received a message from facebook that we can not "
                f"handle. Message: {message}"
            )
            return

        await self._handle_user_message(text, self.get_user_id(), metadata, bot)

    async def postback(
            self, message: Dict[Text, Any], metadata: Optional[Dict[Text, Any]], bot: str
    ) -> None:
        """Handle a postback (e.g. quick reply button)."""

        text = message["postback"]["payload"]
        await self._handle_user_message(text, self.get_user_id(), metadata, bot)

    async def _handle_user_message(
            self, text: Text, sender_id: Text, metadata: Optional[Dict[Text, Any]], bot: str
    ) -> None:
        """Pass on the text to the dialogue engine for processing."""

        out_channel = MessengerBot(self.client)
        await out_channel.send_action(sender_id, sender_action="mark_seen")

        user_msg = UserMessage(
            text, out_channel, sender_id, input_channel=self.name(), metadata=metadata
        )
        await out_channel.send_action(sender_id, sender_action="typing_on")
        # noinspection PyBroadException
        try:
            await self.process_message(bot, user_msg)
        except Exception:
            logger.exception(
                "Exception when trying to handle webhook for facebook message."
            )
        finally:
            await out_channel.send_action(sender_id, sender_action="typing_off")

    @staticmethod
    async def process_message(bot: str, user_message: UserMessage):
        await AgentProcessor.get_agent(bot).handle_message(user_message)


class MessengerBot(OutputChannel):
    """A bot that uses fb-messenger to communicate."""

    @classmethod
    def name(cls) -> Text:
        return "facebook"

    def __init__(self, messenger_client: MessengerClient) -> None:

        self.messenger_client = messenger_client
        super().__init__()

    def send(self, recipient_id: Text, element: Any) -> None:
        """Sends a message to the recipient using the messenger client."""

        # this is a bit hacky, but the client doesn't have a proper API to
        # send messages but instead expects the incoming sender to be present
        # which we don't have as it is stored in the input channel.
        self.messenger_client.send(element.to_dict(), recipient_id, "RESPONSE")

    async def send_text_message(
            self, recipient_id: Text, text: Text, **kwargs: Any
    ) -> None:
        """Send a message through this channel."""

        for message_part in text.strip().split("\n\n"):
            self.send(recipient_id, FBText(text=message_part))

    async def send_image_url(
            self, recipient_id: Text, image: Text, **kwargs: Any
    ) -> None:
        """Sends an image. Default will just post the url as a string."""

        self.send(recipient_id, Image(url=image))

    async def send_action(self, recipient_id: Text, sender_action: Text) -> None:
        """Sends a sender action to facebook (e.g. "typing_on").
        Args:
            recipient_id: recipient
            sender_action: action to send, e.g. "typing_on" or "mark_seen"
        """

        self.messenger_client.send_action(
            SenderAction(sender_action).to_dict(), recipient_id
        )

    async def send_text_with_buttons(
            self,
            recipient_id: Text,
            text: Text,
            buttons: List[Dict[Text, Any]],
            **kwargs: Any,
    ) -> None:
        """Sends buttons to the output."""

        # buttons is a list of tuples: [(option_name,payload)]
        if len(buttons) > 3:
            rasa.shared.utils.io.raise_warning(
                "Facebook API currently allows only up to 3 buttons. "
                "If you add more, all will be ignored."
            )
            await self.send_text_message(recipient_id, text, **kwargs)
        else:
            self._add_postback_info(buttons)

            # Currently there is no predefined way to create a message with
            # buttons in the fbmessenger framework - so we need to create the
            # payload on our own
            payload = {
                "attachment": {
                    "type": "template",
                    "payload": {
                        "template_type": "button",
                        "text": text,
                        "buttons": buttons,
                    },
                }
            }
            self.messenger_client.send(payload, recipient_id, "RESPONSE")

    async def send_quick_replies(
            self,
            recipient_id: Text,
            text: Text,
            quick_replies: List[Dict[Text, Any]],
            **kwargs: Any,
    ) -> None:
        """Sends quick replies to the output."""

        quick_replies = self._convert_to_quick_reply(quick_replies)
        self.send(recipient_id, FBText(text=text, quick_replies=quick_replies))

    async def send_elements(
            self, recipient_id: Text, elements: Iterable[Dict[Text, Any]], **kwargs: Any
    ) -> None:
        """Sends elements to the output."""

        for element in elements:
            if "buttons" in element:
                self._add_postback_info(element["buttons"])

        payload = {
            "attachment": {
                "type": "template",
                "payload": {"template_type": "generic", "elements": elements},
            }
        }
        self.messenger_client.send(payload, recipient_id, "RESPONSE")

    async def send_custom_json(
            self,
            recipient_id: Text,
            json_message: Union[List, Dict[Text, Any]],
            **kwargs: Any,
    ) -> None:
        """Sends custom json data to the output."""
        if isinstance(json_message, dict) and "sender" in json_message.keys():
            recipient_id = json_message.pop("sender", {}).pop("id", recipient_id)
        elif isinstance(json_message, list):
            for message in json_message:
                if "sender" in message.keys():
                    recipient_id = message.pop("sender", {}).pop("id", recipient_id)
                    break

        try:
            message = json_message.get("data")
            message_type = json_message.get("type")
            type_list = Utility.system_metadata.get("type_list")
            if message_type is not None and message_type in type_list:
                converter_instance = ConverterFactory.getConcreteInstance(message_type, CHANNEL_TYPES.MESSENGER.value)
                response = await converter_instance.messageConverter(message)
                self.messenger_client.send(response, recipient_id, "RESPONSE")
            else:
                self.send(recipient_id, FBText(text=str(json_message)))
        except Exception as ap:
            raise Exception(f"Error in messenger send_custom_json {str(ap)}")

    @staticmethod
    def _add_postback_info(buttons: List[Dict[Text, Any]]) -> None:
        """Make sure every button has a type. Modifications happen in place."""
        for button in buttons:
            if "type" not in button:
                button["type"] = "postback"

    @staticmethod
    def _convert_to_quick_reply(quick_replies: List[Dict[Text, Any]]) -> QuickReplies:
        """Convert quick reply dictionary to FB QuickReplies object"""

        fb_quick_replies = []
        for quick_reply in quick_replies:
            try:
                fb_quick_replies.append(
                    QuickReply(
                        title=quick_reply["title"],
                        payload=quick_reply["payload"],
                        content_type=quick_reply.get("content_type"),
                    )
                )
            except KeyError as e:
                raise ValueError(
                    'Facebook quick replies must define a "{}" field.'.format(e.args[0])
                )

        return QuickReplies(quick_replies=fb_quick_replies)


class MessengerHandler(InputChannel, BaseHandler):
    """Facebook input channel implementation. Based on the HTTPInputChannel."""

    # noinspection PyUnusedLocal
    async def get(self, bot: str, token: str):
        super().authenticate_channel(token, bot, self.request)
        self.set_status(HTTPStatus.OK)
        messenger_conf = ChatDataProcessor.get_channel_config("messenger", bot, mask_characters=False)

        fb_verify = messenger_conf["config"]["verify_token"]

        if (self.request.query_arguments.get("hub.verify_token")[0]).decode() == fb_verify:
            hub_challenge = (self.request.query_arguments.get("hub.challenge")[0]).decode()
            self.write(html.escape(hub_challenge))
            return
        else:
            logger.warning(
                "Invalid fb verify token! Make sure this matches "
                "your webhook settings on the facebook app."
            )
            self.write(json.dumps({"status": "failure, invalid verify_token"}))
            return

    async def post(self, bot: str, token: str):
        super().authenticate_channel(token, bot, self.request)
        messenger_conf = ChatDataProcessor.get_channel_config("messenger", bot, mask_characters=False)

        fb_secret = messenger_conf["config"]["app_secret"]
        page_access_token = messenger_conf["config"]["page_access_token"]

        signature = self.request.headers.get("X-Hub-Signature") or ""
        if not self.validate_hub_signature(fb_secret, self.request.body, signature):
            logger.warning(
                "Wrong fb secret! Make sure this matches the "
                "secret in your facebook app settings"
            )
            self.write("not validated")
            return

        messenger = Messenger(page_access_token)

        metadata = self.get_metadata(self.request)
        metadata.update({"channel_type": "messenger"})
        await messenger.handle(json_decode(self.request.body), metadata, bot)
        self.write("success")
        return

    @staticmethod
    def validate_hub_signature(
            app_secret: Text, request_payload: bytes, hub_signature_header: Text
    ) -> bool:
        """Make sure the incoming webhook requests are properly signed.
        Args:
            app_secret: Secret Key for application
            request_payload: request body
            hub_signature_header: X-Hub-Signature header sent with request
        Returns:
            bool: indicated that hub signature is validated
        """

        # noinspection PyBroadException
        try:
            hash_method, hub_signature = hub_signature_header.split("=")
        except Exception:
            logger.exception("Validation failed for hub.signature")
        else:
            digest_module = getattr(hashlib, hash_method)
            hmac_object = hmac.new(
                bytearray(app_secret, "utf8"), request_payload, digest_module
            )
            generated_hash = hmac_object.hexdigest()
            if hub_signature == generated_hash:
                return True
        return False

    def get_output_channel(self) -> OutputChannel:
        client = MessengerClient(self.fb_access_token)
        return MessengerBot(client)


class InstagramHandler(MessengerHandler):
    """Instagram input channel implementation. Based on the HTTPInputChannel."""

    # noinspection PyUnusedLocal
    async def get(self, bot: str, token: str):
        super().authenticate_channel(token, bot, self.request)
        self.set_status(HTTPStatus.OK)
        messenger_conf = ChatDataProcessor.get_channel_config("instagram", bot, mask_characters=False)

        fb_verify = messenger_conf["config"]["verify_token"]

        if (self.request.query_arguments.get("hub.verify_token")[0]).decode() == fb_verify:
            hub_challenge = (self.request.query_arguments.get("hub.challenge")[0]).decode()
            self.write(html.escape(hub_challenge))
            return
        else:
            logger.warning(
                "Invalid verify token! Make sure this matches "
                "your webhook settings on the facebook app under instagram settings."
            )
            self.write(json.dumps({"status": "failure, invalid verify_token"}))
            return

    async def post(self, bot: str, token: str):
        user = super().authenticate_channel(token, bot, self.request)
        messenger_conf = ChatDataProcessor.get_channel_config("instagram", bot, mask_characters=False)

        fb_secret = messenger_conf["config"]["app_secret"]
        page_access_token = messenger_conf["config"]["page_access_token"]

        signature = self.request.headers.get("X-Hub-Signature") or ""
        if not self.validate_hub_signature(fb_secret, self.request.body, signature):
            logger.warning(
                "Wrong fb secret! Make sure this matches the "
                "secret in your facebook app settings under instagram settings"
            )
            self.write("not validated")
            return

        messenger = Messenger(page_access_token)

        metadata = self.get_metadata(self.request) or {}
        metadata.update({"is_integration_user": True, "bot": bot, "account": user.account, "channel_type": "instagram"})
        await messenger.handle(json_decode(self.request.body), metadata, bot)
        self.write("success")
        return
