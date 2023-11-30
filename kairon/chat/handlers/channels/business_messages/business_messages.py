import hmac
import uuid
import base64
import hashlib

from typing import Text, Dict, Any, Optional
from starlette.requests import Request
from loguru import logger
from rasa.core.channels.channel import UserMessage, InputChannel

from businessmessages import businessmessages_v1_client as bm_client
from businessmessages.businessmessages_v1_messages import (
    BusinessmessagesConversationsMessagesCreateRequest, BusinessmessagesConversationsEventsCreateRequest,
    BusinessMessagesEvent
)
from businessmessages.businessmessages_v1_messages import BusinessMessagesMessage
from businessmessages.businessmessages_v1_messages import BusinessMessagesRepresentative
from oauth2client.service_account import ServiceAccountCredentials

from kairon.shared.models import User
from kairon.shared.chat.processor import ChatDataProcessor
from kairon.chat.agent_processor import AgentProcessor


path_to_service_account_key = 'kairon/chat/handlers/channels/business_messages/service_account_key.json'


class BusinessMessagesHandler(InputChannel):

    def __init__(self, bot: Text, user: User, request: Request):
        self.bot = bot
        self.user = user
        self.request = request

    async def validate(self):
        business_message_conf = ChatDataProcessor.get_channel_config("business_messages", self.bot,
                                                                     mask_characters=False)

        partner_key = business_message_conf["config"]["private_key_id"]
        generated_signature = base64.b64encode(hmac.new(partner_key.encode(), msg=await self.request.body(),
                                                        digestmod=hashlib.sha512).digest()).decode('UTF-8')
        google_signature = self.request.headers.get('x-goog-signature')

        if generated_signature == google_signature:
            logger.debug("Signature match.")
        else:
            logger.debug("Signature mismatch, do not trust this message.")

    async def handle_message(self):
        request_body = await self.request.json()

        if 'secret' in request_body:
            return request_body.get('secret')

        await self.validate()
        business_message_conf = ChatDataProcessor.get_channel_config("business_messages", self.bot,
                                                                     mask_characters=False)
        credentials_json = {
            "type": "service_account",
            "private_key_id": business_message_conf["config"]["private_key_id"],
            "private_key": business_message_conf["config"]["private_key"],
            "client_email": business_message_conf["config"]["client_email"],
            "client_id": business_message_conf["config"]["client_id"]
        }
        print("*"*100)
        print(request_body)
        metadata = self.get_metadata(self.request) or {}
        metadata.update({"is_integration_user": True, "bot": self.bot, "account": self.user.account,
                         "channel_type": "business_messages", "tabname": "default"})

        if 'message' in request_body and 'text' in request_body['message']:
            message = request_body['message']['text']
            conversation_id = request_body['conversationId']
            message_id = request_body['message']['messageId']
            business_messages = BusinessMessages(credentials_json)
            await business_messages.handle_user_message(text=message, sender_id=self.user.email, metadata=metadata,
                                                        conversation_id=conversation_id, bot=self.bot,
                                                        message_id=message_id)
        return ''


class BusinessMessages:

    def __init__(self, credentials_json: Dict):
        self.credentials_json = credentials_json

    @classmethod
    def name(cls) -> Text:
        return "business_messages"

    @staticmethod
    def write_json_to_file(json_code, file_path):
        import json

        try:
            with open(file_path, 'w') as json_file:
                json.dump(json_code, json_file, indent=2)
            print(f"JSON code successfully written to {file_path}")
        except Exception as e:
            print(f"Error writing JSON to file: {e}")

    def get_business_message_credentials(self):
        self.write_json_to_file(self.credentials_json, path_to_service_account_key)
        credentials = ServiceAccountCredentials.from_json_keyfile_name(
            path_to_service_account_key,
            scopes=['https://www.googleapis.com/auth/businessmessages'])
        return credentials

    async def handle_user_message(
            self, text: Text, sender_id: Text, message_id: Text, conversation_id: Text,
            metadata: Optional[Dict[Text, Any]], bot: str
    ) -> None:
        user_msg = UserMessage(text=text, message_id=message_id,
                               input_channel=self.name(), sender_id=sender_id, metadata=metadata)
        message = "No Response"
        try:
            response = await self.process_message(bot, user_msg)
            message = response['response'][0]['text']
        except Exception:
            logger.exception(
                "Exception when trying to handle webhook for business message."
            )
        await self.send_message(message=message, conversation_id=conversation_id)

    @staticmethod
    async def process_message(bot: str, user_message: UserMessage):
        response = await AgentProcessor.get_agent(bot).handle_message(user_message)
        print("^" * 100)
        print(response)
        return response

    async def send_message(self, message: Text, conversation_id: Text):
        """
        Posts a message to the Business Messages API, first sending
        a typing indicator event and sending a stop typing event after
        the message has been sent.

        Args:
            message (str): The message to send to the user.
            conversation_id (str): The unique id for this user and agent.
        """
        credentials = self.get_business_message_credentials()
        client = bm_client.BusinessmessagesV1(credentials=credentials)

        create_request = BusinessmessagesConversationsEventsCreateRequest(
            eventId=str(uuid.uuid4().int),
            businessMessagesEvent=BusinessMessagesEvent(
                representative=BusinessMessagesRepresentative(
                    representativeType=BusinessMessagesRepresentative.RepresentativeTypeValueValuesEnum.BOT
                ),
                eventType=BusinessMessagesEvent.EventTypeValueValuesEnum.TYPING_STARTED
            ),
            parent='conversations/' + conversation_id)

        bm_client.BusinessmessagesV1.ConversationsEventsService(
            client=client).Create(request=create_request)

        message_obj = BusinessMessagesMessage(
            messageId=str(uuid.uuid4().int),
            representative=BusinessMessagesRepresentative(
                representativeType=BusinessMessagesRepresentative.RepresentativeTypeValueValuesEnum.BOT
            ),
            text=message)

        create_request = BusinessmessagesConversationsMessagesCreateRequest(
            businessMessagesMessage=message_obj,
            parent='conversations/' + conversation_id)

        bm_client.BusinessmessagesV1.ConversationsMessagesService(
            client=client).Create(request=create_request)

        # Send the typing stopped event
        create_request = BusinessmessagesConversationsEventsCreateRequest(
            eventId=str(uuid.uuid4().int),
            businessMessagesEvent=BusinessMessagesEvent(
                representative=BusinessMessagesRepresentative(
                    representativeType=BusinessMessagesRepresentative.RepresentativeTypeValueValuesEnum.BOT
                ),
                eventType=BusinessMessagesEvent.EventTypeValueValuesEnum.TYPING_STOPPED
            ),
            parent='conversations/' + conversation_id)

        bm_client.BusinessmessagesV1.ConversationsEventsService(
            client=client).Create(request=create_request)
