from abc import abstractmethod

from kairon.shared.constants import EventClass


class ExecutorBase:

    """Base class to create executors"""

    @abstractmethod
    def execute_task(self, event_class: EventClass, data: dict):
        raise NotImplementedError("Provider not implemented")
