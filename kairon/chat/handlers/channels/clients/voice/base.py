from abc import ABC, abstractmethod
from typing import List

from starlette.requests import Request


class VoiceProviderBase(ABC):

    def __init__(self, bot: str, config: dict):
        """
        Base initialiser for voice provider implementations.

        :param bot: bot ID this provider is serving
        :param config: decrypted channel config dict for the bot
        """
        self.bot = bot
        self.config = config

    @abstractmethod
    def build_voice_response(self, messages: List[str], call_url: str) -> str:
        raise NotImplementedError

    @abstractmethod
    async def handle_call_status(self, request: Request, bot: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def validate_signature(self, request: Request, url: str, form_params: dict) -> bool:
        raise NotImplementedError

    @abstractmethod
    def validate_config(self, config: dict) -> None:
        raise NotImplementedError
