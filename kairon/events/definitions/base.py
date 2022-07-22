from abc import abstractmethod


class EventsBase:

    """Base class to create events"""

    @abstractmethod
    def validate(self):
        raise NotImplementedError("Provider not implemented")

    @abstractmethod
    def enqueue(self):
        raise NotImplementedError("Provider not implemented")

    @abstractmethod
    def execute(self, **kwargs):
        raise NotImplementedError("Provider not implemented")
