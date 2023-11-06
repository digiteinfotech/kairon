from typing import Text

from rasa.core.agent import Agent

from kairon import Utility
from kairon.shared.chat.cache.base import AgentCache
from kairon.shared.chat.cache.least_priority import LeastPriorityCache


class InMemoryAgentCache(AgentCache):

    def __init__(self):
        self.cache = LeastPriorityCache(maxsize=Utility.environment["model"]["cache_size"])

    def set(self, bot: Text, agent: Agent, **kwargs):
        """
        loads bot agent in LRU cache

        :param bot: bot id
        :param agent:  bot agent
        :return: None
        """
        is_billed = kwargs.get("is_billed", False)
        self.cache.put(bot, agent, is_billed)

    def get(self, bot: Text) -> Agent:
        """
        fetches bot agent from LRU cache

        :param bot: bot id
        :return: Agent object
        """
        return self.cache.get(bot)

    def is_exists(self, bot: Text) -> bool:
        """
        checks if bot agent exist in LRU cache

        :param bot: bot id
        :return: True/False
        """
        return bot in self.cache.keys()

    def len(self):
        """
        fetches number of models loaded in cache
        :return: integer
        """
        return self.cache.len()
