from abc import ABC, abstractmethod
from typing import List

from starlette.requests import Request


class VoiceProviderBase(ABC):

    def __init__(self, bot: str, config: dict):
        """Base initialiser for voice provider implementations.

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

    @abstractmethod
    def build_hangup_response(self, messages: List[str]) -> str:
        raise NotImplementedError

    @classmethod
    def normalize_config(cls, config: dict, error, registries: dict) -> None:
        """Validate a channel config about to be saved and fill in the provider's defaults, in place.

        :param error: exception class used to report an invalid value
        :param registries: known STT/TTS providers keyed by config field (``stt_provider``, ``tts_provider``)
        """

    def build_resolver_response(self, params: dict, bot: str, user: str) -> dict:
        raise NotImplementedError(f"{self.__class__.__name__} does not support dynamic resolver")

    def build_greeting_response(self, params: dict, bot: str, user: str) -> str:
        raise NotImplementedError(f"{self.__class__.__name__} does not support greeting applet")

    @classmethod
    def supports_dynamic_resolver(cls) -> bool:
        return False
