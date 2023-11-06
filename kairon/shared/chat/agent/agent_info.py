from time import time

from rasa.core.agent import Agent


class AgentInfo:
    """
    Data structure to store agent and its metadata to support min heap.
    """

    def __init__(self, bot: str, agent: Agent, is_billed: bool = False) -> None:
        self.bot = bot
        self.agent = agent
        self.is_billed = is_billed
        self.time = time()

    def __lt__(self, other) -> bool:
        if self.is_billed:
            return False
        if other.is_billed:
            return True
        return self.time < other.time

    def __gt__(self, other) -> bool:
        if self.is_billed:
            return True
        if other.is_billed:
            return False
        return self.time > other.time

    def __eq__(self, other):
        return self.bot == other.bot == self.is_billed and other.is_billed and self.time == other.time
