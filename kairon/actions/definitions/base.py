from abc import ABC, abstractmethod
from typing import Any, Text, Dict

from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher


class ActionsBase(ABC):

    """Base class for all different actions."""

    @abstractmethod
    def retrieve_config(self):
        """Fetch action configuration parameters from the database."""
        raise NotImplementedError("Provider not implemented")

    @abstractmethod
    def execute(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]):
        """Execute the action."""
        raise NotImplementedError("Provider not implemented")
