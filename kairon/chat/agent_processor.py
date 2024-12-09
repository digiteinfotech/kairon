import os
from typing import Text

from loguru import logger as logging
from rasa.core.agent import Agent
from rasa.core.channels import UserMessage

from kairon.shared.chat.cache.in_memory_agent import AgentCache
from kairon.exceptions import AppException
from kairon.shared.data.processor import MongoProcessor
from .agent.agent import KaironAgent
from kairon.shared.chat.cache.in_memory_agent import InMemoryAgentCache
from ..shared.live_agent.live_agent import LiveAgentHandler
from ..shared.utils import Utility
from kairon.shared.otel import record_custom_attributes



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
        if not AgentProcessor.cache_provider.is_exists(bot) or not AgentProcessor.is_latest_version_in_mem(bot):
            AgentProcessor.reload(bot)
        record_custom_attributes(num_models=AgentProcessor.cache_provider.len())
        return AgentProcessor.cache_provider.get(bot)

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
            lock_store_endpoint = Utility.get_lock_store(bot)
            model_path = Utility.get_latest_model(bot)
            domain = AgentProcessor.mongo_processor.load_domain(bot)
            bot_settings = AgentProcessor.mongo_processor.get_bot_settings(bot, "system")
            mongo_store = Utility.get_local_mongo_store(bot, domain)
            agent = KaironAgent.load(model_path, action_endpoint=action_endpoint, tracker_store=mongo_store,
                                     lock_store=lock_store_endpoint)
            agent.model_ver = model_path.split("/")[-1]
            AgentProcessor.cache_provider.set(bot, agent, is_billed=bot_settings.is_billed)
        except Exception as e:
            logging.exception(e)
            raise AppException("Bot has not been trained yet!")

    @staticmethod
    def is_latest_version_in_mem(bot: Text):
        model_path = Utility.get_latest_model(bot)
        latest_ver = model_path.split("/")[-1]
        in_mem_model_ver = AgentProcessor.cache_provider.get(bot).model_ver
        logging.debug(f"PID:{os.getpid()} In memory model:{in_mem_model_ver}, latest trained model:{latest_ver}")
        return latest_ver == in_mem_model_ver

    @staticmethod
    async def handle_channel_message(bot: Text, userdata: UserMessage):
        is_live_agent_enabled = await LiveAgentHandler.check_live_agent_active(bot, userdata)
        logging.debug(f"Live agent enabled:{is_live_agent_enabled}")
        if not is_live_agent_enabled:
            return await AgentProcessor.get_agent(bot).handle_message(userdata)
        return await LiveAgentHandler.process_live_agent(bot, userdata)

    @staticmethod
    def get_agent_without_cache(bot: str, use_store: bool = True) -> Agent:
        endpoint = AgentProcessor.mongo_processor.get_endpoints(
            bot, raise_exception=False
        )
        action_endpoint = Utility.get_action_url(endpoint)
        model_path = Utility.get_latest_model(bot)
        domain = AgentProcessor.mongo_processor.load_domain(bot)
        if use_store:
            mongo_store = Utility.get_local_mongo_store(bot, domain)
            lock_store_endpoint = Utility.get_lock_store(bot)
            agent = KaironAgent.load(model_path, action_endpoint=action_endpoint, tracker_store=mongo_store,
                                     lock_store=lock_store_endpoint)
        else:
            agent = KaironAgent.load(model_path, action_endpoint=action_endpoint)

        agent.model_ver = model_path.split("/")[-1]
        return agent
