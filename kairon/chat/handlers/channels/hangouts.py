import logging
from asyncio import CancelledError
from typing import Text, List, Dict, Any, Optional, Iterable, Union

import cachecontrol
import google.auth.transport.requests
import requests
from google.oauth2 import id_token
from rasa.core.channels.channel import InputChannel, OutputChannel, UserMessage
from tornado.escape import json_encode, json_decode

from kairon.chat.agent_processor import AgentProcessor
from kairon.shared.chat.processor import ChatDataProcessor
from kairon.shared.tornado.handlers.base import BaseHandler
from kairon import Utility
from kairon.chat.converters.channels.response_factory import ConverterFactory
from kairon.chat.converters.channels.constants import CHANNEL_TYPES


logger = logging.getLogger(__name__)

CHANNEL_NAME = "hangouts"
CERTS_URL = (
    "https://www.googleapis.com/service_accounts/"
    "v1/metadata/x509/chat@system.gserviceaccount.com"
)


class HangoutsOutput(OutputChannel):
    """A Hangouts communication channel."""

    @classmethod
    def name(cls) -> Text:
        """Return channel name."""
        return CHANNEL_NAME

    def __init__(self) -> None:
        """Starts messages as empty dictionary."""
        self.messages = {}

    @staticmethod
    def _text_card(message: Dict[Text, Any]) -> Dict:

        card = {
            "cards": [
                {
                    "sections": [
                        {"widgets": [{"textParagraph": {"text": message["text"]}}]}
                    ]
                }
            ]
        }
        return card

    @staticmethod
    def _image_card(image: Text) -> Dict:
        card = {
            "cards": [{"sections": [{"widgets": [{"image": {"imageUrl": image}}]}]}]
        }
        return card

    @staticmethod
    def _text_button_card(text: Text, buttons: List) -> Union[Dict, None]:
        hangouts_buttons = []
        for b in buttons:
            try:
                b_txt, b_pl = b["title"], b["payload"]
            except KeyError:
                logger.error(
                    "Buttons must be a list of dicts with 'title' and 'payload' as keys"
                )
                return

            hangouts_buttons.append(
                {
                    "textButton": {
                        "text": b_txt,
                        "onClick": {"action": {"actionMethodName": b_pl}},
                    }
                }
            )

        card = {
            "cards": [
                {
                    "sections": [
                        {
                            "widgets": [
                                {"textParagraph": {"text": text}},
                                {"buttons": hangouts_buttons},
                            ]
                        }
                    ]
                }
            ]
        }
        return card

    @staticmethod
    def _combine_cards(c1: Dict, c2: Dict) -> Dict:
        return {"cards": [*c1["cards"], *c2["cards"]]}

    async def _persist_message(self, message: Dict) -> None:
        """Google Hangouts only accepts single dict with single key 'text'
        for simple text messages. All other responses must be sent as cards.

        In case the bot sends multiple messages, all are transformed to either
        cards or text output"""

        # check whether current and previous message will send 'text' or 'card'
        if self.messages.get("text"):
            msg_state = "text"
        elif self.messages.get("cards"):
            msg_state = "cards"
        else:
            msg_state = None

        if message.get("text"):
            msg_new = "text"
        elif message.get("cards"):
            msg_new = "cards"
        else:
            raise Exception(
                "Your message to Hangouts channel must either contain 'text' or "
                "'cards'!"
            )

        # depending on above outcome, convert messages into same type and combine
        if msg_new == msg_state == "text":
            # two text messages are simply appended
            new_text = " ".join([self.messages.get("text", ""), message["text"]])
            new_messages = {"text": new_text}

        elif msg_new == msg_state == "cards":
            # two cards are combined into one
            new_messages = self._combine_cards(self.messages, message)

        elif msg_state == "cards" and msg_new == "text":
            # if any message is card, turn text message into TextParagraph card
            # and combine cards
            text_card = self._text_card(message)
            new_messages = self._combine_cards(self.messages, text_card)

        elif msg_state == "text" and msg_new == "cards":
            text_card = self._text_card(self.messages)
            new_messages = self._combine_cards(text_card, message)

        elif msg_new == "text":
            new_messages = {"text": message["text"]}
        else:
            new_messages = message

        self.messages = new_messages

    async def send_text_message(
        self, recipient_id: Text, text: Text, **kwargs: Any
    ) -> None:
        await self._persist_message({"text": text})

    async def send_image_url(
        self, recipient_id: Text, image: Text, **kwargs: Any
    ) -> None:
        await self._persist_message(self._image_card(image))

    async def send_text_with_buttons(
        self, recipient_id: Text, text: Text, buttons: List, **kwargs: Any
    ) -> None:
        await self._persist_message(self._text_button_card(text, buttons))

    async def send_attachment(
        self, recipient_id: Text, attachment: Text, **kwargs: Any
    ) -> None:
        await self.send_text_message(recipient_id, attachment)

    async def send_elements(
        self, recipient_id: Text, elements: Iterable[Dict[Text, Any]], **kwargs: Any
    ) -> None:
        raise NotImplementedError

    async def send_custom_json(
        self, recipient_id: Text, json_message: Dict, **kwargs: Any
    ) -> None:
        """Custom json payload is simply forwarded to Google Hangouts without
        any modifications. Use this for more complex cards, which can be created
        in actions.py."""
        try:
            message = json_message.get("data")
            message_type = json_message.get("type")
            type_list = Utility.system_metadata.get("type_list")
            if message_type is not None and message_type in type_list:
                converter_instance = ConverterFactory.getConcreteInstance(message_type, CHANNEL_TYPES.HANGOUT.value)
                response = await converter_instance.messageConverter(message)
                await self._persist_message(response)
            else:
                await self._persist_message({"text": str(json_message)})
        except Exception as ap:
            raise Exception(f"Error in Hangout send_custom_json {str(ap)}")


# Google Hangouts input channel
class HangoutHandler(InputChannel, BaseHandler):
    """
    Channel that uses Google Hangouts Chat API to communicate.
    """
    hangouts_user_added_intent_name: Optional[Text] = "/user_added",
    hangouts_room_added_intent_name: Optional[Text] = "/room_added",
    hangouts_removed_intent_name: Optional[Text] = "/bot_removed",

    cached_session = cachecontrol.CacheControl(requests.session())
    google_request = google.auth.transport.requests.Request(
        session=cached_session
    )

    @staticmethod
    def _extract_sender(request_data: Dict) -> Text:

        if request_data["type"] == "MESSAGE":
            return request_data["message"]["sender"]["displayName"]

        return request_data["user"]["displayName"]

    # noinspection PyMethodMayBeStatic
    def _extract_message(self, request_data: Dict) -> Text:
        message = None
        if request_data["type"] == "MESSAGE":
            message = request_data["message"]["text"]

        elif request_data["type"] == "CARD_CLICKED":
            message = request_data["action"]["actionMethodName"]

        elif request_data["type"] == "ADDED_TO_SPACE":
            if self._extract_room(request_data) and self.hangouts_room_added_intent_name:
                message = self.hangouts_room_added_intent_name
            elif not self._extract_room(request_data) and self.hangouts_user_added_intent_name:
                message = self.hangouts_user_added_intent_name

        elif (
            request_data["type"] == "REMOVED_FROM_SPACE"
            and self.hangouts_user_added_intent_name
        ):
            message = self.hangouts_user_added_intent_name
        else:
            message = ""

        return message

    @staticmethod
    def _extract_room(request_data: Dict) -> Union[Text, None]:

        if request_data["space"]["type"] == "ROOM":
            return request_data["space"]["displayName"]

    def _extract_input_channel(self) -> Text:
        return self.name()

    def _check_token(self, bot_token: Text, project_id: Text) -> None:
        # see https://developers.google.com/chat/how-tos/bots-develop#verifying_bot_authenticity # noqa: E501, W505
        # and https://google-auth.readthedocs.io/en/latest/user-guide.html#identity-tokens # noqa: E501, W505
        decoded_token = {}
        try:
            decoded_token = id_token.verify_token(
                bot_token,
                self.google_request,
                audience=project_id,
                certs_url=CERTS_URL,
            )
        except ValueError:
            raise Exception(401)
        if decoded_token["iss"] != "chat@system.gserviceaccount.com":
            raise Exception(401)

    async def get(self, bot: str, token: str):
        self.write(json_encode({"status": "ok"}))

    async def post(self, bot: str, token: str):
        user = super().authenticate_channel(token, bot, self.request)
        hangout = ChatDataProcessor.get_channel_config("hangouts", bot=bot, mask_characters=False)
        project_id = hangout['config']['project_id']
        request_data = json_decode(self.request.body)
        if project_id:
            token = self.request.headers.get("Authorization").replace("Bearer ", "")
            self._check_token(token, project_id)

        sender_id = self._extract_sender(request_data)
        room_name = self._extract_room(request_data)
        text = self._extract_message(request_data)
        if text is None:
            self.write("OK")
            return
        input_channel = self._extract_input_channel()

        collector = HangoutsOutput()

        try:
            metadata = {"is_integration_user": True, "bot": bot, "account": user.account, "room": room_name,
                        "out_channel": collector.name(), "channel_type": "hangouts"}
            await AgentProcessor.get_agent(bot).handle_message(UserMessage(
                    text,
                    collector,
                    sender_id,
                    input_channel=input_channel,
                    metadata=metadata,
                ))
        except CancelledError:
            logger.error(
                "Message handling timed out for " "user message '{}'.".format(text)
            )
        except Exception as e:
            logger.exception(
                f"An exception occurred while handling user message: {e}, "
                f"text: {text}"
            )

        self.write(json_encode(collector.messages))
        return
