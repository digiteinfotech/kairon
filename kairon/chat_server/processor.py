import os
from datetime import datetime
from enum import Enum
from typing import Text

from loguru import logger
from mongoengine import DoesNotExist
from rasa.core.agent import Agent
from rasa.shared.constants import DEFAULT_MODELS_PATH

from kairon.api.data_objects import User, UserEmailConfirmation, Bot, Account
from kairon.api.processor import AccountProcessor
from kairon.chat_server.cache import AgentCache, InMemoryAgentCache
from kairon.chat_server.channels.channels import KaironChannels
from kairon.chat_server.chat_server_utils import ChatServerUtils
from kairon.chat_server.data_objects import ChannelCredentials
from kairon.chat_server.exceptions import AuthenticationException, ChatServerException
from kairon.data_processor.processor import MongoProcessor
from kairon.utils import Utility


class LanguageSupport(str, Enum):
    ENGLISH = "english"
    HINDI = "hindi"


class KaironMessageProcessor:

    @staticmethod
    async def process_text_message(bot: str, message: str, sender_id: str):
        model = AgentProcessor.get_agent(bot)
        response = await model.handle_text(
            message, sender_id=sender_id
        )
        return response[0]['text']

    @staticmethod
    def process_audio(bot: str, audio: bytes, sender_id: str):
        pass


# class MongoProcessor:
#
#     def get_endpoints(self, bot: Text, raise_exception=True):
#         """
#         fetches endpoint configuration
#
#         :param bot: bot id
#         :param raise_exception: wether to raise an exception, default is True
#         :return: endpoint configuration
#         """
#         try:
#             endpoint = Endpoints.objects().get(bot=bot).to_mongo().to_dict()
#             endpoint.pop("bot")
#             endpoint.pop("user")
#             endpoint.pop("timestamp")
#             endpoint["_id"] = endpoint["_id"].__str__()
#             return endpoint
#         except DoesNotExist as e:
#             if raise_exception:
#                 raise ChatServerException("Endpoint Configuration does not exists!")
#             else:
#                 return {}


class AgentProcessor:
    """
    Class contains logic for loading bot agents
    """
    mongo_processor = MongoProcessor()
    cache_provider: AgentCache = InMemoryAgentCache()

    @staticmethod
    def get_agent(bot: Text) -> Agent:
        """
        fetch the bot agent from cache if exist otherwise load it into the cache

        :param bot: bot id
        :return: Agent Object
        """
        if not AgentProcessor.cache_provider.is_exists(bot):
            AgentProcessor.reload(bot)
        return AgentProcessor.cache_provider.get(bot)

    @staticmethod
    def get_latest_model(bot: Text):
        """
        fetches the latest model from the path

        :param bot: bot id
        :return: latest model path
        """
        return Utility.get_latest_file(os.path.join(DEFAULT_MODELS_PATH, bot))

    @staticmethod
    def reload(bot: Text):
        """
        reload bot agent

        :param bot: bot id
        :return: None
        """
        try:
            endpoint = AgentProcessor.mongo_processor.get_endpoints(
                bot, raise_exception=False
            )
            action_endpoint = Utility.get_action_url(endpoint)
            model_path = AgentProcessor.get_latest_model(bot)
            domain = AgentProcessor.mongo_processor.load_domain(bot)
            mongo_store = Utility.get_local_mongo_store(bot, domain)
            agent = Agent.load(
                model_path, action_endpoint=action_endpoint, tracker_store=mongo_store
            )
            AgentProcessor.cache_provider.set(bot, agent)
        except Exception as e:
            raise ChatServerException("Bot has not been trained yet !")


class AuthenticationProcessor:

    @staticmethod
    def is_email_verified(email: str):
        if not UserEmailConfirmation.objects(email__iexact=email.strip(), raise_error=False):
            raise AuthenticationException("Please verify your mailing address")

    @staticmethod
    def validate_user_and_get_info(auth_token: str, alias_user: str = None):
        if ChatServerUtils.is_empty(auth_token):
            raise AuthenticationException("Could not validate credentials")
        username = ChatServerUtils.decode_auth_token(auth_token)
        user = AccountProcessor.get_user_details(username)
        if user is None:
            raise AuthenticationException("Could not validate credentials")

        # if user["is_integration_user"]:
        #     if ChatServerUtils.is_empty(alias_user):
        #         raise AuthenticationException("Alias user missing for integration")
        #     user_model.alias_user = alias_user
        return user


class ChannelCredentialsProcessor:

    @staticmethod
    def add_credentials(bot: str, user: str, channel: KaironChannels, credentials: dict):
        try:
            credentials = ChannelCredentials.objects.get(bot=bot, user=user, channel=channel, status=True)
            if credentials:
                raise ChatServerException("Credentials already exist for this channel!")
        except DoesNotExist:
            pass
        ChannelCredentials(
            bot=bot,
            user=user,
            channel=channel,
            credentials=credentials
        ).save()

    @staticmethod
    def update_credentials(bot: str, user: str, channel: KaironChannels, credentials: dict):
        try:
            channel_creds = ChannelCredentials.objects.get(bot=bot, user=user, channel=channel, status=True)
            channel_creds.credentials = credentials
            channel_creds.timestamp = datetime.utcnow()
            channel_creds.save()
        except DoesNotExist:
            raise ChatServerException("Credentials do not exist for the channel!")
        except Exception as e:
            raise ChatServerException(e)

    @staticmethod
    def get_credentials(bot: str, user: str, channel: KaironChannels):
        try:
            credentials = ChannelCredentials.objects.get(bot=bot, user=user, channel=channel, status=True).to_mongo().to_dict()
            if credentials:
                credentials.pop("_id")
            else:
                raise DoesNotExist
            return credentials
        except DoesNotExist:
            raise ChatServerException("Credentials do not exist for the channel!")

    @staticmethod
    def list_credentials(bot: str, user: str):
        try:
            for value in ChannelCredentials.objects(bot=bot, user=user, status=True).order_by("-start_timestamp"):
                value = value.to_mongo().to_dict()
                value.pop('_id')
                yield value
        except DoesNotExist:
            raise ChatServerException("No channels configured for the bot!")

    @staticmethod
    def delete_credentials(bot: str, user: str, channel: KaironChannels):
        try:
            channel_creds = ChannelCredentials.objects.get(bot=bot, user=user, channel=channel, status=True)
            channel_creds.timestamp = datetime.utcnow()
            channel_creds.status = False
            channel_creds.save()
        except DoesNotExist:
            raise ChatServerException("Credentials do not exist for the channel!")
