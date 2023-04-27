from abc import ABC, abstractmethod
from typing import Any, List


class MessageBroadcastBase(ABC):

    @abstractmethod
    def pull_data(self):
        raise NotImplementedError("Provider not implemented")

    @abstractmethod
    def get_recipients(self, data: Any, **kwargs):
        raise NotImplementedError("Provider not implemented")

    @abstractmethod
    def send(self, recipients: List, data: Any, **kwargs):
        raise NotImplementedError("Provider not implemented")
