from __future__ import annotations

from pathlib import Path
from typing import Optional, Text, Union

from rasa.core.channels import UserMessage
from rasa.core.http_interpreter import RasaNLUHttpInterpreter
from rasa.core.lock_store import LockStore
from rasa.core.nlg import NaturalLanguageGenerator, TemplatedNaturalLanguageGenerator
from rasa.core.tracker_store import TrackerStore
from rasa.shared.core.domain import Domain
from rasa.utils.endpoints import EndpointConfig
from rasa.core.agent import Agent
from typing import List, Any, Dict
from kairon.chat.agent.message_processor import KaironMessageProcessor
from loguru import logger


class KaironAgent(Agent):
    model_ver: Text

    @classmethod
    def load(
        cls,
        model_path: Union[Text, Path],
        domain: Optional[Domain] = None,
        generator: Union[EndpointConfig, NaturalLanguageGenerator, None] = None,
        tracker_store: Optional[TrackerStore] = None,
        lock_store: Optional[LockStore] = None,
        action_endpoint: Optional[EndpointConfig] = None,
        fingerprint: Optional[Text] = None,
        model_server: Optional[EndpointConfig] = None,
        remote_storage: Optional[Text] = None,
        http_interpreter: Optional[RasaNLUHttpInterpreter] = None,
    ) -> Agent:
        """Constructs a new agent and loads the processer and model."""
        agent = KaironAgent(
            domain=domain,
            generator=generator,
            tracker_store=tracker_store,
            lock_store=lock_store,
            action_endpoint=action_endpoint,
            fingerprint=fingerprint,
            model_server=model_server,
            remote_storage=remote_storage,
            http_interpreter=http_interpreter,
        )
        agent.load_model(model_path=model_path, fingerprint=fingerprint)
        return agent

    def load_model(
        self, model_path: Union[Text, Path], fingerprint: Optional[Text] = None
    ) -> None:
        """Loads the agent's model and processor given a new model path."""
        self.processor = KaironMessageProcessor(
            model_path=model_path,
            tracker_store=self.tracker_store,
            lock_store=self.lock_store,
            action_endpoint=self.action_endpoint,
            generator=self.nlg,
            http_interpreter=self.http_interpreter,
        )
        self.domain = self.processor.domain

        self._set_fingerprint(fingerprint)

        # update domain on all instances
        self.tracker_store.domain = self.domain
        if isinstance(self.nlg, TemplatedNaturalLanguageGenerator):
            self.nlg.responses = self.domain.responses if self.domain else {}

    async def handle_message(
        self, message: UserMessage, enable_metering=True, media_ids: list[str] = None
    ) -> Optional[List[Dict[Text, Any]]]:
        """Handle a single message."""
        if not self.is_ready():
            logger.info("Ignoring message as there is no agent to handle it.")
            return None

        async with self.lock_store.lock(message.sender_id):
            return await self.processor.handle_message(  # type: ignore[union-attr]
                message, enable_metering, media_ids=media_ids
            )
