from typing import Text

from cachetools import LRUCache
from rasa.core.agent import Agent


class AgentCache:
    def set(self, bot: Text, agent: Agent):
        """
        loads the bot agent into cache

        :param bot: bot id
        :param agent: bot agent
        :return: pass
        """
        pass

    def get(self, bot: Text) -> Agent:
        """
        fetches bot agent from cache

        :param bot: bot id
        :return: pass
        """
        pass

    def is_exists(self, bot: Text) -> Agent:
        """
        checks if bot agent exist in the cache

        :param bot: bot id
        :return: pass
        """
        pass

    def len(self):
        """
        fetches number of models loaded in cache

        :return: pass
        """
        pass


class InMemoryAgentCache(AgentCache):

    def __init__(self):
        self.cache = LRUCache(maxsize=100)

    def set(self, bot: Text, agent: Agent):
        """
        loads bot agent in LRU cache

        :param bot: bot id
        :param agent:  bot agent
        :return: None
        """
        if bot in self.cache.keys():
            self.cache.pop(bot)
        self.cache.__setitem__(bot, agent)

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
        return len(self.cache)
