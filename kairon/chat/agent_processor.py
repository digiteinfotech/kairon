from typing import Text

from loguru import logger as logging
from rasa.core.agent import Agent

from kairon.chat.cache import AgentCache
from kairon.exceptions import AppException
from kairon.shared.data.processor import MongoProcessor
from .agent.agent import KaironAgent
from .cache import InMemoryAgentCache
from ..shared.utils import Utility


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
        Utility.record_custom_metric_apm(num_models=AgentProcessor.cache_provider.len())
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
            model_path = Utility.get_latest_model(bot)
            domain = AgentProcessor.mongo_processor.load_domain(bot)
            mongo_store = Utility.get_local_mongo_store(bot, domain)
            agent = KaironAgent.load(model_path, action_endpoint=action_endpoint, tracker_store=mongo_store)
            AgentProcessor.cache_provider.set(bot, agent)
        except Exception as e:
            logging.exception(e)
            raise AppException("Bot has not been trained yet!")
