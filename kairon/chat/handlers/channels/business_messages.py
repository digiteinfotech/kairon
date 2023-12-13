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

from kairon.shared.constants import ChannelTypes
from kairon.shared.models import User
from kairon.shared.chat.processor import ChatDataProcessor
from kairon.chat.agent_processor import AgentProcessor


class BusinessMessagesHandler(InputChannel):

    def __init__(self, bot: Text, user: User, request: Request):
        self.bot = bot
        self.user = user
        self.request = request
        self.channel_config = {}

    async def validate(self):
        partner_key = self.channel_config["private_key_id"]
        generated_signature = base64.b64encode(hmac.new(partner_key.encode(), msg=await self.request.body(),
                                                        digestmod=hashlib.sha512).digest()).decode('UTF-8')
        google_signature = self.request.headers.get('x-goog-signature')

        if generated_signature != google_signature:
            logger.debug("Signature mismatch, do not trust this message.")

    async def handle_message(self):
        request_body = await self.request.json()

        if 'secret' in request_body:
            return request_body.get('secret')

        business_message_conf = ChatDataProcessor.get_channel_config(ChannelTypes.BUSINESS_MESSAGES.value, self.bot,
                                                                     mask_characters=False)
        self.channel_config = business_message_conf['config']
        await self.validate()
        print(request_body)
        metadata = self.get_metadata(self.request) or {}
        metadata.update({"is_integration_user": True, "bot": self.bot, "account": self.user.account,
                         "channel_type": ChannelTypes.BUSINESS_MESSAGES.value, "tabname": "default"})

        if 'message' in request_body and 'text' in request_body['message']:
            create_time = request_body['message']['createTime']
            if self.check_message_create_time(create_time):
                message = request_body['message']['text']
                conversation_id = request_body['conversationId']
                message_id = request_body['message']['messageId']
                business_messages = BusinessMessages(self.channel_config)
                await business_messages.handle_user_message(text=message, sender_id=self.user.email, metadata=metadata,
                                                            conversation_id=conversation_id, bot=self.bot,
                                                            message_id=message_id)
        logger.debug(f"Business Messages Request: {request_body}")
        return {"status": "OK"}

    @staticmethod
    def check_message_create_time(create_time: str):
        from datetime import datetime

        current_time = datetime.utcnow()
        message_time = datetime.strptime(create_time, '%Y-%m-%dT%H:%M:%S.%fZ')
        time_difference = current_time - message_time
        return True if time_difference.total_seconds() < 5 else False


class BusinessMessages:

    def __init__(self, channel_config: Dict):
        self.channel_config = channel_config

    @classmethod
    def name(cls) -> Text:
        return ChannelTypes.BUSINESS_MESSAGES.value

    def get_credentials(self):
        credentials_json = {
            "type": "service_account",
            "private_key_id": self.channel_config["private_key_id"],
            "private_key": self.channel_config["private_key"],
            "client_email": self.channel_config["client_email"],
            "client_id": self.channel_config["client_id"]
        }
        return credentials_json

    def get_business_message_credentials(self):
        credentials = self.get_credentials()
        credentials = ServiceAccountCredentials.from_json_keyfile_dict(
            credentials,
            scopes=['https://www.googleapis.com/auth/businessmessages'])
        return credentials

    async def handle_user_message(
            self, text: Text, sender_id: Text, message_id: Text, conversation_id: Text,
            metadata: Optional[Dict[Text, Any]], bot: str
    ) -> None:
        user_msg = UserMessage(text=text, message_id=message_id,
                               input_channel=self.name(), sender_id=sender_id, metadata=metadata)
        try:
            response = await self.process_message(bot, user_msg)
            print(response)
            message = response['response'][0].get('text')
            if message:
                await self.send_message(message=message, conversation_id=conversation_id)
        except Exception as e:
            raise Exception(f"Exception when trying to handle webhook for business message: {str(e)}")

    @staticmethod
    async def process_message(bot: str, user_message: UserMessage):
        response = await AgentProcessor.get_agent(bot).handle_message(user_message)
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

        self.trigger_start_typing_event(conversation_id, client)

        self.send_google_business_message(message, conversation_id, client)

        self.trigger_stop_typing_event(conversation_id, client)

    @staticmethod
    def send_google_business_message(message, conversation_id, client):
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

    @staticmethod
    def trigger_start_typing_event(conversation_id, client):
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

    @staticmethod
    def trigger_stop_typing_event(conversation_id, client):
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
