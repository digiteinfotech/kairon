import os
from datetime import datetime
from time import time
from typing import Optional
from loguru import logger

from pqdict import pqdict as PriorityQueue
from rasa.core.agent import Agent

from kairon.shared.chat.agent.agent_info import AgentInfo


class LeastPriorityCache:
    """
    A least priority caching mechanism where agents with least priority will be removed if cache max size is reached.
    Agents which were not accessed recently and are not billed will be assumed to have the least priority
    and thus will be removed. Also, agents which were not accessed recently
    but are billed will have higher priority than agents which were accessed recently and are not billed.
    """

    def __init__(self, maxsize: int) -> None:
        self.maxsize = maxsize
        self.agent_q: PriorityQueue[str, AgentInfo] = PriorityQueue()

    def __update_access_time(self, bot: str) -> None:
        agent = self.agent_q.get(bot)
        agent.time = time()
        self.agent_q.updateitem(bot, agent)

    def put(self, bot: str, agent: Agent, is_billed: bool = False) -> None:
        if self.agent_q.__len__() < self.maxsize:
            new_agent = AgentInfo(bot, agent, is_billed)
            if bot not in self.agent_q:
                self.agent_q.additem(bot, new_agent)
            else:
                self.agent_q.updateitem(bot, new_agent)
        else:
            # remove lru key
            _, popped_agent = self.agent_q.popitem()
            print(f"popped agent: {popped_agent.bot} {popped_agent.is_billed} {popped_agent.time}")
            self.put(bot, agent, is_billed)
        logger.debug(f"{self.agent_q.__len__()} bots in memory in process {os.getpid()}")
        logger.debug(self.__str__())

    def get(self, bot: str) -> Optional[Agent]:
        agent_info = self.agent_q.get(bot)
        if agent_info:
            self.__update_access_time(bot)
            return agent_info.agent

    def keys(self):
        return self.agent_q.keys()

    def len(self):
        return self.agent_q.__len__()

    def __str__(self) -> str:
        return str([{f"bot: {agent.bot}", f"is_billed: {agent.is_billed}",
                     f"last_accessed: {datetime.fromtimestamp(agent.time).__str__()}"}
                    for agent in self.agent_q.values()])
