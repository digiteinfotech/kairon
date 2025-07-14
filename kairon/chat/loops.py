from typing import List

from rasa.core.actions.loops import LoopAction
from rasa.shared.core.events import Event
from typing import Text, Optional
from rasa.utils.endpoints import EndpointConfig


class KLoopAction(LoopAction):

    def __init__(self, name: Text, action_endpoint: Optional[EndpointConfig], retry_attempts=3) -> None:

        self._name = name
        self.action_endpoint = action_endpoint
        self.retry_attempts = retry_attempts

    def do(
        self,
        output_channel: "OutputChannel",
        nlg: "NaturalLanguageGenerator",
        tracker: "DialogueStateTracker",
        domain: "Domain",
        events_so_far: List[Event],
    ) -> List[Event]:
        pass


    def is_done(
        self,
        output_channel: "OutputChannel",
        nlg: "NaturalLanguageGenerator",
        tracker: "DialogueStateTracker",
        domain: "Domain",
        events_so_far: List[Event],
    ) -> bool:
        return False