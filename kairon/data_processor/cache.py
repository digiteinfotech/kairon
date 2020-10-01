from typing import Text
from rasa.core.agent import Agent
from cachetools.lru import LRUCache
from redis import Redis


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


class RedisAgentCache(AgentCache):

    def __init__(self, host, port=6379,db="kairon-agent"):
        self.cache = Redis(host=host, port=port,db=db)

    def set(self, bot: Text, agent: Agent):
        """
        loads bot agent in redis cache

        :param bot: bot id
        :param agent:  bot agent
        :return: None
        """
        from kairon.utils import Utility
        if bot in self.cache.keys():
            self.cache.delete(bot)
        self.cache.set(bot, agent, ex=Utility.environment['cache']['timeout'], keepttl=True)

    def get(self, bot: Text) -> Agent:
        """
        fetches bot agent from redis cache

        :param bot: bot id
        :return: Agent object
        """
        return self.cache.get(bot)

    def is_exists(self, bot: Text) -> bool:
        """
        checks if bot agent exist in redis cache

        :param bot: bot id
        :return: True/False
        """
        return self.cache.exists(bot)
