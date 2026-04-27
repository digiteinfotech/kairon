from abc import ABC, abstractmethod

from starlette.requests import Request


class VoiceProviderBase(ABC):

    def __init__(self, bot: str, config: dict):
        self.bot = bot
        self.config = config

    @abstractmethod
    async def handle_incoming_call(self, request: Request) -> str:
        raise NotImplementedError

    @abstractmethod
    async def handle_call_processing(self, request: Request, bot: str, rasa_response: str) -> str:
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
