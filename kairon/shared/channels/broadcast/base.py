from abc import ABC, abstractmethod
from typing import List


class MessageBroadcastBase(ABC):

    @abstractmethod
    def get_recipients(self, **kwargs):
        raise NotImplementedError("Provider not implemented")

    @abstractmethod
    def send(self, recipients: List, **kwargs):
        raise NotImplementedError("Provider not implemented")
