from typing import Text
from rasa.core.agent import Agent


class AgentCache:
    def set(self, bot: Text, agent: Agent, **kwargs):
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
