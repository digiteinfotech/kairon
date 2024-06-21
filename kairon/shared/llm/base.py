from abc import ABC, abstractmethod
from typing import Text, Dict


class LLMBase(ABC):

    def __init__(self, bot: Text):
        self.bot = bot

    @abstractmethod
    async def train(self, user, bot, *args, **kwargs) -> Dict:
        pass

    @abstractmethod
    async def predict(self, query, user, bot, *args, **kwargs) -> Dict:
        pass
