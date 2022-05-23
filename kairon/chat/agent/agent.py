from typing import Optional, Callable, Text

from rasa.core.agent import Agent
from rasa.core.exceptions import AgentNotReady

from kairon.chat.agent.message_processor import KaironMessageProcessor


class KaironAgent(Agent):

    def create_processor(
        self, preprocessor: Optional[Callable[[Text], Text]] = None
    ):
        """Instantiates a processor based on the set state of the agent."""
        # Checks that the interpreter and tracker store are set and
        # creates a processor
        if not self.is_ready():
            raise AgentNotReady(
                "Agent needs to be prepared before usage. You need to set an "
                "interpreter and a tracker store."
            )

        return KaironMessageProcessor(
            self.interpreter,
            self.policy_ensemble,
            self.domain,
            self.tracker_store,
            self.lock_store,
            self.nlg,
            action_endpoint=self.action_endpoint,
            message_preprocessor=preprocessor,
        )
