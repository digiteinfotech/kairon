import hashlib
import hmac
import json
import logging
from typing import Text, List, Dict, Any, Iterable, Optional, Union
import rasa.shared.utils.io
from fbmessenger import MessengerClient
from fbmessenger.attachments import Image
from fbmessenger.elements import Text as FBText
from fbmessenger.quick_replies import QuickReplies, QuickReply
from fbmessenger.sender_actions import SenderAction
from rasa.core.channels.channel import UserMessage, OutputChannel, InputChannel
from starlette.requests import Request

from kairon.chat.agent_processor import AgentProcessor
from kairon.chat.handlers.channels.base import ChannelHandlerBase
from kairon.shared.chat.processor import ChatDataProcessor
from kairon.shared.concurrency.actors.factory import ActorFactory
from kairon.shared.constants import ChannelTypes, ActorType
from kairon.shared.models import User
from kairon import Utility
from kairon.chat.converters.channels.response_factory import ConverterFactory

logger = logging.getLogger(__name__)


class Messenger:
    """Implement a fbmessenger to parse incoming webhooks and send msgs."""

    @classmethod
    def name(cls) -> Text:
        return "facebook"

    def __init__(
            self,
            page_access_token: Text,
            is_instagram: bool = False
    ) -> None:

        self.client = MessengerClient(page_access_token)
        self.last_message: Dict[Text, Any] = {}
        self.is_instagram = is_instagram
        self.post_config = None

    def get_user_id(self) -> Text:
        sender_id = self.last_message.get("sender", {}).get("id", "")
        if sender_id == '':
            sender_id = self.last_message.get("value", {}).get("from", {}).get("id", "")
        return sender_id

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
    def _is_comment(message: Dict[Text, Any]) -> bool:
        return  message.get("field", "") == "comments"

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
            for message in entry.get("messaging", []):
                self.last_message = message
                if message.get("message"):
                    return await self.message(message, metadata, bot)
                elif message.get("postback"):
                    return await self.postback(message, metadata, bot)
            for change in entry.get("changes",[]):
                self.last_message = change
                if change.get("value"):
                    return await self.comment(change, metadata, bot)

    async def message(
            self, message: Dict[Text, Any], metadata: Optional[Dict[Text, Any]], bot: str
    ) -> None:
        """Handle an incoming event from the fb webhook."""

        # quick reply and user message both share 'text' attribute
        # so quick reply should be checked first
        if self._is_quick_reply_message(message):
            payload = message["message"]["quick_reply"]["payload"]
            entity = json.dumps({"quick_reply": payload})
            text = f"/k_quick_reply{entity}"
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

    async def comment(
            self, message: Dict[Text, Any], metadata: Optional[Dict[Text, Any]], bot: str
    ):
        if self._is_comment(message):
            static_comment_reply = ChatDataProcessor.get_instagram_static_comment(bot=bot)
            text = message["value"]["text"]
            parent_id = message.get("value", {}).get("parent_id", None)
            comment_id = message["value"]["id"]
            user = message["value"]["from"]["username"]
            metadata["comment_id"] = comment_id
            metadata["user"] = user
            if static_comment_reply:
                metadata["static_comment_reply"] = f"@{user} {static_comment_reply}"
            if media := message["value"].get("media"):
                metadata["media_id"] = media.get("id")
                metadata["media_product_type"] = media.get("media_product_type")

            if not parent_id:
                await self._handle_user_message(text, self.get_user_id(), metadata, bot)

    async def _handle_user_message(
            self, text: Text, sender_id: Text, metadata: Optional[Dict[Text, Any]], bot: str
    ) -> None:
        """Pass on the text to the dialogue engine for processing."""
        out_channel = MessengerBot(self.client)
        media_id = metadata.get("media_id")
        media_post_config = self.post_config.get(media_id, {})
        keywords_str = media_post_config.get("keywords", "")
        keywords = Utility.string_to_list(keywords_str)

        if self.is_instagram and media_id in self.post_config:
            if text.lower() not in [word.lower() for word in keywords]:
                return

        await out_channel.send_action(sender_id, sender_action="mark_seen")
        input_channel_name = self.name() if not self.is_instagram else "instagram"
        user_msg = UserMessage(
            text, out_channel, sender_id, input_channel=input_channel_name, metadata=metadata
        )
        await out_channel.send_action(sender_id, sender_action="typing_on")

        user = metadata.get("user")
        comment_reply = media_post_config.get("comment_reply", "")
        comment_reply = f"@{user} {comment_reply}" if comment_reply else comment_reply
        metadata['static_comment_reply'] = comment_reply or metadata.get('static_comment_reply')
        out_channel.metadata = metadata

        if metadata.get("comment_id") and metadata.get('static_comment_reply'):
            await out_channel.reply_on_comment(**metadata)
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
        await AgentProcessor.handle_channel_message(bot, user_message)


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
        comment_id = self.metadata.pop("comment_id")
        bot = self.metadata.pop("bot")
        user = self.metadata.pop("user")

        if comment_id and not self.metadata.get("static_comment_reply"):
            self.metadata['static_comment_reply'] = f"@{user} {text}"
            await self.reply_on_comment(comment_id, bot, **self.metadata)
            return

        for message_part in text.strip().split("\n\n"):
            self.send(recipient_id, FBText(text=message_part))

    async def reply_on_comment(
            self, comment_id: Text, bot: Text, **kwargs: Any
    ):
        body = {}
        _ = self.messenger_client.session.post(
            '{graph_url}/{comment_id}/replies?message={message}'.
            format(graph_url=self.messenger_client.graph_url,
                   comment_id=comment_id,
                   message=kwargs.get("static_comment_reply")),
            params=self.messenger_client.auth_args,
            json=body
        )

    async def get_username_for_id(self, sender_id: str) -> str:
        params = f"fields=username&access_token={self.messenger_client.auth_args['access_token']}"
        resp = self.messenger_client.session.get(
            f"{self.messenger_client.graph_url}/{sender_id}?{params}"
        )
        return resp.json().get('username')

    async def get_user_media_posts(self):
        #   GET USER INSTAGRAM POSTS
        account_details = await self.get_user_account_details_from_page()
        ig_user_id = account_details.get('instagram_business_account', {}).get('id')
        params = (f"fields=id,ig_id,media_product_type,media_type,media_url,thumbnail_url,timestamp,username,permalink,"
                  f"caption,like_count,comments_count&access_token={self.messenger_client.auth_args['access_token']}")
        resp = self.messenger_client.session.get(
            f"{self.messenger_client.graph_url}/{ig_user_id}/media/?{params}"
        )
        user_posts = resp.json()
        return user_posts

    async def get_user_account_details_from_page(self):
        #   GET USER ACCOUNT DETAILS FROM PAGE
        page_details = await self.get_page_details()
        page_id = page_details.get('id')
        params = f"fields=instagram_business_account&access_token={self.messenger_client.auth_args['access_token']}"
        resp = self.messenger_client.session.get(
            f"{self.messenger_client.graph_url}/{page_id}/?{params}"
        )
        account_details = resp.json()
        return account_details

    async def get_page_details(self):
        #   GET PAGE DETAILS
        params = f"fields=id,name&access_token={self.messenger_client.auth_args['access_token']}"
        resp = self.messenger_client.session.get(
            f"{self.messenger_client.graph_url}/me/?{params}"
        )
        page_details = resp.json()
        return page_details

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
                converter_instance = ConverterFactory.getConcreteInstance(message_type, ChannelTypes.MESSENGER.value)
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


class MessengerHandler(InputChannel, ChannelHandlerBase):
    """Facebook input channel implementation. Based on the HTTPInputChannel."""

    def __init__(self, bot: Text, user: User, request: Request):
        self.bot = bot
        self.user = user
        self.request = request

    # noinspection PyUnusedLocal
    async def validate(self):
        messenger_conf = ChatDataProcessor.get_channel_config("messenger", self.bot, mask_characters=False)

        fb_verify = messenger_conf["config"]["verify_token"]

        if self.request.query_params.get("hub.verify_token") == fb_verify:
            hub_challenge = self.request.query_params.get("hub.challenge")
            return int(hub_challenge)
        else:
            logger.warning(
                "Invalid fb verify token! Make sure this matches "
                "your webhook settings on the facebook app."
            )
            return {"status": "failure, invalid verify_token"}

    async def handle_message(self):
        msg = "success"
        messenger_conf = ChatDataProcessor.get_channel_config("messenger", self.bot, mask_characters=False)

        fb_secret = messenger_conf["config"]["app_secret"]
        page_access_token = messenger_conf["config"]["page_access_token"]

        signature = self.request.headers.get("X-Hub-Signature") or ""
        if not self.validate_hub_signature(fb_secret, await self.request.body(), signature):
            logger.warning(
                "Wrong fb secret! Make sure this matches the "
                "secret in your facebook app settings"
            )
            return "not validated"

        messenger = Messenger(page_access_token)

        metadata = self.get_metadata(self.request) or {}
        metadata.update({"is_integration_user": True, "bot": self.bot, "account": self.user.account, "channel_type": "messenger",
                         "tabname": "default"})
        actor = ActorFactory.get_instance(ActorType.callable_runner.value)
        actor.execute(messenger.handle, await self.request.json(), metadata, self.bot)
        return msg

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

    def __init__(self, bot: Text, user: User, request: Request):
        super().__init__(bot, user, request)
        self.bot = bot
        self.user = user
        self.request = request

    # noinspection PyUnusedLocal
    async def validate(self):
        messenger_conf = ChatDataProcessor.get_channel_config("instagram", self.bot, mask_characters=False)

        fb_verify = messenger_conf["config"]["verify_token"]

        hub_verify_token = self.request.query_params.get("hub.verify_token")
        logger.debug(f"config verify_token: {fb_verify} and hub verify_token: {hub_verify_token}")
        if hub_verify_token == fb_verify:
            result = None
            try:
                hub_challenge = self.request.query_params.get("hub.challenge")
                result = int(hub_challenge)
            except Exception as e:
                logger.error(str(e))
            return result
        else:
            logger.warning(
                "Invalid verify token! Make sure this matches "
                "your webhook settings on the facebook app under instagram settings."
            )
            return {"status": "failure, invalid verify_token"}

    async def handle_message(self):
        msg = "success"
        messenger_conf = ChatDataProcessor.get_channel_config("instagram", self.bot, mask_characters=False)

        fb_secret = messenger_conf["config"]["app_secret"]
        page_access_token = messenger_conf["config"]["page_access_token"]

        signature = self.request.headers.get("X-Hub-Signature") or ""
        if not self.validate_hub_signature(fb_secret, await self.request.body(), signature):
            logger.warning(
                "Wrong fb secret! Make sure this matches the "
                "secret in your facebook app settings under instagram settings"
            )
            return "not validated"

        messenger = Messenger(page_access_token, is_instagram=True)

        if messenger_conf["config"].get("is_dev"):
            post_config = messenger_conf["config"].get("post_config", {})
            messenger.post_config = post_config

        metadata = self.get_metadata(self.request) or {}
        metadata.update({
            "is_integration_user": True,
            "bot": self.bot,
            "account": self.user.account,
            "channel_type": "instagram",
            "tabname": "default"
        })
        actor = ActorFactory.get_instance(ActorType.callable_runner.value)
        actor.execute(messenger.handle, await self.request.json(), metadata, self.bot)
        return msg

    async def get_user_posts(self):
        messenger_conf = ChatDataProcessor.get_channel_config("instagram", self.bot, mask_characters=False)

        page_access_token = messenger_conf["config"]["page_access_token"]
        messenger = Messenger(page_access_token, is_instagram=True)

        out_channel = MessengerBot(messenger.client)
        user_posts = await out_channel.get_user_media_posts()

        return user_posts
