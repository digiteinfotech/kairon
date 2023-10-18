from typing import Text

from loguru import logger as logging
from rasa.core.agent import Agent
from rasa.core.lock_store import LockStore

from kairon.chat.cache import AgentCache
from kairon.exceptions import AppException
from kairon.shared.data.processor import MongoProcessor
from .agent.agent import KaironAgent
from .cache import InMemoryAgentCache
from ..shared.data.model_processor import ModelProcessor
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
        if not AgentProcessor.cache_provider.is_exists(bot) or not AgentProcessor.is_latest_version_in_mem(bot):
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
            lock_store_endpoint = LockStore.create(Utility.get_lock_store_url(bot))
            model_path = Utility.get_latest_model(bot)
            domain = AgentProcessor.mongo_processor.load_domain(bot)
            mongo_store = Utility.get_local_mongo_store(bot, domain)
            agent = KaironAgent.load(model_path, action_endpoint=action_endpoint, tracker_store=mongo_store,
                                     lock_store=lock_store_endpoint)
            agent.model_ver = model_path.split("/")[-1]
            AgentProcessor.cache_provider.set(bot, agent)
        except Exception as e:
            logging.exception(e)
            raise AppException("Bot has not been trained yet!")

    @staticmethod
    def is_latest_version_in_mem(bot: Text):
        latest_ver = ModelProcessor.get_latest_model_version(bot)
        in_mem_model_ver = AgentProcessor.cache_provider.get(bot).model_ver
        logging.debug(f"In memory model:{in_mem_model_ver}, latest trained model:{latest_ver}")
        return latest_ver == in_mem_model_ver
