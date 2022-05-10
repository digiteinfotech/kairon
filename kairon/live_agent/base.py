from abc import ABC, abstractmethod
from typing import Text, List, Dict, Optional


class LiveAgentBase(ABC):

    """Base class for live agents."""

    @classmethod
    @abstractmethod
    def from_config(cls, config: dict):
        raise NotImplementedError("Provider not implemented")

    @property
    def agent_type(self) -> str:
        raise NotImplementedError("Provider not implemented")

    @abstractmethod
    def validate_credentials(self):
        raise NotImplementedError("Provider not implemented")

    @abstractmethod
    def complete_prerequisites(self, **kwargs) -> Optional[Dict]:
        raise NotImplementedError("Provider not implemented")

    @abstractmethod
    def initiate_handoff(self, bot: Text, sender_id: Text):
        raise NotImplementedError("Provider not implemented")

    @abstractmethod
    def send_message(self, message: Text, destination: Text, **kwargs):
        raise NotImplementedError("Provider not implemented")

    @abstractmethod
    def send_conversation_log(self, messages: List[Text], destination: Text):
        raise NotImplementedError("Provider not implemented")
