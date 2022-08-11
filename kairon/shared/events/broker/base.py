from abc import abstractmethod
from typing import Text

from kairon.shared.constants import EventClass


class BrokerBase:

    """Base class to create broker"""

    _broker = None

    @classmethod
    @abstractmethod
    def create_instance(cls):
        raise NotImplementedError("Provider not implemented")

    @abstractmethod
    def declare_actors(self, actors: dict):
        raise NotImplementedError("Provider not implemented")

    def get_broker(self):
        return self._broker

    @abstractmethod
    def enqueue(
            self, event_class: EventClass, actor_name: Text = None, queue: Text = None, **message_body
    ):
        raise NotImplementedError("Provider not implemented")
