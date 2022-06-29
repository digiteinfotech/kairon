from abc import ABC, abstractmethod

from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher


class ActionsBase(ABC):

    @abstractmethod
    def retrieve_config(self):
        raise NotImplementedError("Provider not implemented")

    @abstractmethod
    def execute(self, dispatcher: CollectingDispatcher, tracker: Tracker):
        raise NotImplementedError("Provider not implemented")
