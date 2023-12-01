import os
from typing import Text

from loguru import logger as logging
from rasa.core.agent import Agent
from rasa.core.lock_store import LockStore

from kairon.exceptions import AppException
from kairon.shared.chat.cache.in_memory_agent import AgentCache
from kairon.shared.chat.cache.in_memory_agent import InMemoryAgentCache
from kairon.shared.data.processor import MongoProcessor
from .agent.agent import KaironAgent
from ..shared.account.activity_log import UserActivityLogger
from ..shared.account.data_objects import Bot
from ..shared.constants import UserActivityType
from ..shared.utils import Utility


class AgentProcessor:
    """
    Class contains logic for loading bot agents
    """

    mongo_processor = MongoProcessor()
    cache_provider: AgentCache = InMemoryAgentCache()

    @staticmethod
    def get_agent(bot: Text, account: int = None) -> Agent:
        """
        fetch the bot agent from cache if exist otherwise load it into the cache

        :param bot: bot id
        :param account: account
        :return: Agent Object
        """
        if not AgentProcessor.cache_provider.is_exists(bot) or not AgentProcessor.is_latest_version_in_mem(bot):
            if not account:
                bot_details = Bot.objects(name=bot).get()
                AgentProcessor.reload(bot, bot_details['account'])
            AgentProcessor.reload(bot, account)

        Utility.record_custom_metric_apm(num_models=AgentProcessor.cache_provider.len())
        return AgentProcessor.cache_provider.get(bot)

    @staticmethod
    def reload(bot: Text,  account: int = None, email: str = None):
        """
        reload bot agent

        :param bot: bot id
        :param account: account
        :param email: email
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
            bot_settings = AgentProcessor.mongo_processor.get_bot_settings(bot, "system")
            mongo_store = Utility.get_local_mongo_store(bot, domain)
            agent = KaironAgent.load(model_path, action_endpoint=action_endpoint, tracker_store=mongo_store,
                                     lock_store=lock_store_endpoint)
            agent.model_ver = model_path.split("/")[-1]
            AgentProcessor.cache_provider.set(bot, agent, is_billed=bot_settings.is_billed)
            UserActivityLogger.add_log(a_type=UserActivityType.reload_model_completion.value, account=account,
                                       email=email, bot=bot, message=['Model reload completed!'], data={"username": email})
        except Exception as e:
            UserActivityLogger.add_log(a_type=UserActivityType.reload_model_failure.value, account=account,
                                       email=email, bot=bot, message=['Model reload failed!'],
                                       data={"username": email})
            logging.exception(e)
            raise AppException("Bot has not been trained yet!")

    @staticmethod
    def is_latest_version_in_mem(bot: Text):
        model_path = Utility.get_latest_model(bot)
        latest_ver = model_path.split("/")[-1]
        in_mem_model_ver = AgentProcessor.cache_provider.get(bot).model_ver
        logging.debug(f"PID:{os.getpid()} In memory model:{in_mem_model_ver}, latest trained model:{latest_ver}")
        return latest_ver == in_mem_model_ver
