from __future__ import annotations

import copy
import logging
import os
import tarfile
from pathlib import Path
from types import LambdaType
from typing import Dict, List, Optional, Text, Tuple, Union

import rasa
import rasa.core.actions.action
import rasa.core.actions.action
import rasa.core.tracker_store
import rasa.core.utils
import rasa.shared.core.trackers
import rasa.shared.utils.io
import structlog
from rasa.core.actions.action import (
    Action,
    ActionRetrieveResponse,
    ActionEndToEndResponse,
    default_actions,
    ActionBotResponse,
    ActionExtractSlots,
)
from rasa.core.actions.action import is_retrieval_action
from rasa.core.actions.forms import FormAction
from rasa.core.channels.channel import (
    CollectingOutputChannel,
    OutputChannel,
    UserMessage,
)
from rasa.core.http_interpreter import RasaNLUHttpInterpreter
from rasa.core.lock_store import LockStore
from rasa.core.nlg import NaturalLanguageGenerator
from rasa.core.policies.policy import PolicyPrediction
from rasa.core.processor import MessageProcessor, logger
from rasa.engine import loader
from rasa.engine.runner.dask import DaskGraphRunner
from rasa.engine.runner.interface import GraphRunner
from kairon.engine.storage.local_model_storage import LocalModelStorage
from rasa.engine.storage.storage import ModelMetadata
from rasa.exceptions import ActionLimitReached, ModelNotFound
from rasa.model import get_latest_model
from rasa.plugin import plugin_manager
from rasa.shared.constants import (
    ASSISTANT_ID_KEY,
    DOCS_URL_POLICIES,
    UTTER_PREFIX,
)
from rasa.shared.core.constants import (
    ACTION_SESSION_START_NAME,
    SESSION_START_METADATA_SLOT,
    ACTION_EXTRACT_SLOTS,
)
from rasa.shared.core.events import (
    SlotSet,
    UserUttered,
)
from rasa.shared.core.trackers import DialogueStateTracker
from rasa.shared.data import TrainingType
from rasa.shared.utils.io import raise_warning
from rasa.utils.common import TempDirectoryPath, get_temp_dir_name
from rasa.utils.endpoints import EndpointConfig

from kairon.chat.actions import KRemoteAction
from kairon.chat.loops import KLoopAction
from kairon.shared.core.domain import Domain
from kairon.shared.metering.constants import MetricType
from kairon.shared.metering.metering_processor import MeteringProcessor
from rasa.shared.constants import DEFAULT_DOMAIN_PATH
import shutil


logger = logging.getLogger(__name__)

structlogger = structlog.get_logger()
MAX_NUMBER_OF_PREDICTIONS = int(os.environ.get("MAX_NUMBER_OF_PREDICTIONS", "10"))


class KaironMessageProcessor(MessageProcessor):
    """
    Class overriding MessageProcessor implementation from rasa.
    This is done to also retrieve model predictions along with the message response.
    """

    def __init__(
        self,
        model_path: Union[Text, Path],
        tracker_store: rasa.core.tracker_store.TrackerStore,
        lock_store: LockStore,
        generator: NaturalLanguageGenerator,
        action_endpoint: Optional[EndpointConfig] = None,
        max_number_of_predictions: int = MAX_NUMBER_OF_PREDICTIONS,
        on_circuit_break: Optional[LambdaType] = None,
        http_interpreter: Optional[RasaNLUHttpInterpreter] = None,
    ) -> None:
        """Initializes a `MessageProcessor`."""
        self.nlg = generator
        self.tracker_store = tracker_store
        self.lock_store = lock_store
        self.max_number_of_predictions = max_number_of_predictions
        self.on_circuit_break = on_circuit_break
        self.action_endpoint = action_endpoint
        self.model_filename, self.model_metadata, self.graph_runner, extracted_path = self._load_model(
            model_path
        )

        if self.model_metadata.assistant_id is None:
            rasa.shared.utils.io.raise_warning(
                f"The model metadata does not contain a value for the "
                f"'{ASSISTANT_ID_KEY}' attribute. Check that 'config.yml' "
                f"file contains a value for the '{ASSISTANT_ID_KEY}' key "
                f"and re-train the model. Failure to do so will result in "
                f"streaming events without a unique assistant identifier.",
                UserWarning,
            )

        self.model_path = Path(model_path)
        self.domain = self.model_metadata.domain
        self.http_interpreter = http_interpreter
        shutil.rmtree(extracted_path)

    @staticmethod
    def _load_model(
        model_path: Union[Text, Path]
    ) -> Tuple[Text, ModelMetadata, GraphRunner, Text]:
        """Unpacks a model from a given path using the graph model loader."""
        try:
            if os.path.isfile(model_path):
                model_tar = model_path
            else:
                model_file_path = get_latest_model(model_path)
                if not model_file_path:
                    raise ModelNotFound(f"No model found at path '{model_path}'.")
                model_tar = model_file_path
        except TypeError:
            raise ModelNotFound(f"Model {model_path} can not be loaded.")

        logger.info(f"Loading model {model_tar}...")
        temporary_directory = TempDirectoryPath(get_temp_dir_name())
        try:
            metadata, runner = loader.load_predict_graph_runner(
                Path(temporary_directory),
                Path(model_tar),
                LocalModelStorage,
                DaskGraphRunner,
            )
            return os.path.basename(model_tar), metadata, runner, temporary_directory
        except tarfile.ReadError:
            raise ModelNotFound(f"Model {model_path} can not be loaded.")

    async def _handle_message_with_tracker(
        self, message: UserMessage, tracker: DialogueStateTracker
    ):

        if message.parse_data:
            parse_data = message.parse_data
        else:
            parse_data = await self.parse_message(message)

        # don't ever directly mutate the tracker
        # - instead pass its events to log
        tracker.update(
            UserUttered(
                message.text,
                parse_data["intent"],
                parse_data["entities"],
                parse_data,
                input_channel=message.input_channel,
                message_id=message.message_id,
                metadata=message.metadata,
            ),
            self.domain,
        )

        if parse_data["entities"]:
            self._log_slots(tracker)

        return parse_data

    async def _run_prediction_loop(
        self, output_channel: OutputChannel, tracker: DialogueStateTracker
    ) -> List[Dict]:
        # keep taking actions decided by the policy until it chooses to 'listen'
        should_predict_another_action = True
        actions_predicted = []

        # action loop. predicts actions until we hit action listen
        predicted_action_count = 0
        last_predicted_action = None
        while should_predict_another_action and self._should_handle_message(tracker):
            # this actually just calls the policy's method by the same name
            try:
                if predicted_action_count >= self.max_number_of_predictions:
                    raise ActionLimitReached(
                        "The limit of actions to predict has been reached."
                    )

                action, prediction = self.predict_next_with_tracker_if_should(tracker)
                if action.name() != last_predicted_action:
                    actions_predicted.append(
                        {
                            "action_name": action.name(),
                            "max_confidence": prediction.max_confidence,
                            "policy_name": prediction.policy_name,
                        }
                    )
                    predicted_action_count += 1
                    last_predicted_action = action.name()
                else:
                    raise ActionLimitReached(
                        "Same action has been predicted again"
                    )
            except ActionLimitReached:
                logger.warning(
                    "Circuit breaker tripped. Stopped predicting "
                    f"more actions for sender '{tracker.sender_id}'."
                )
                if self.on_circuit_break:
                    # call a registered callback
                    self.on_circuit_break(tracker, output_channel, self.nlg)
                break

            if prediction.is_end_to_end_prediction:
                logger.debug(
                    f"An end-to-end prediction was made which has triggered the 2nd "
                    f"execution of the default action '{ACTION_EXTRACT_SLOTS}'."
                )
                tracker = await self.run_action_extract_slots(output_channel, tracker)

            should_predict_another_action = await self._run_action(
                action, tracker, output_channel, self.nlg, prediction
            )
        return actions_predicted

    async def log_message(self, message: UserMessage, should_save_tracker: bool = True):
        """
        Log `message` on tracker belonging to the message's conversation_id.

        Optionally save the tracker if `should_save_tracker` is `True`. Tracker saving
        can be skipped if the tracker returned by this method is used for further
        processing and saved at a later stage.
        """
        # we have a Tracker instance for each user
        # which maintains conversation state
        tracker = await self.fetch_tracker_and_update_session(
            message.sender_id, message.output_channel, message.metadata
        )

        predictions = await self._handle_message_with_tracker(message, tracker)

        if should_save_tracker:
            # save tracker state to continue conversation from this state
            await self.save_tracker(tracker)

        return tracker, predictions

    async def handle_message(self, message: UserMessage, enable_metering=True, media_ids: list[str] = None):
        """Handle a single message with this processor."""
        if message.metadata:
            tabname = message.metadata.get("tabname", "default")
        else:
            tabname = "default"
            message.metadata = {"tabname": tabname}
        response = {
            "nlu": None,
            "action": None,
            "response": None,
            "slots": None,
            "events": None,
            "tabname": tabname,
        }

        # preprocess message if necessary
        tracker, intent_predictions = await self.log_message(
            message, should_save_tracker=False
        )
        response["nlu"] = intent_predictions

        if self.model_metadata.training_type == TrainingType.NLU:
            await self.save_tracker(tracker)
            raise_warning(
                "No core model. Skipping action prediction and execution.",
                docs=DOCS_URL_POLICIES,
            )
            return None

        tracker = await self.run_action_extract_slots(message.output_channel, tracker)

        if media_ids:
            if current_media_ids := tracker.get_slot("media_ids"):
                current_media_ids.extend(media_ids)
                media_ids = current_media_ids
            slot_event = SlotSet(key="media_ids", value=media_ids)
            tracker.update(slot_event)

        actions_predictions = await self._run_prediction_loop(
            message.output_channel, tracker
        )
        anonymization = await self.run_anonymization_pipeline(tracker)

        response["anonymization_pipeline"] = anonymization
        response["action"] = actions_predictions
        response["slots"] = [f"{s.name}: {s.value}" for s in tracker.slots.values()]

        # save tracker state to continue conversation from this state
        await self.save_tracker(tracker)
        metadata = message.metadata
        metric_type = (
            MetricType.prod_chat
            if metadata and metadata.get("is_integration_user")
            else MetricType.test_chat
        )
        if metadata:
            if enable_metering:
                MeteringProcessor.add_metrics(
                    metadata.get("bot"),
                    metadata.get("account"),
                    metric_type,
                    user_id=message.sender_id,
                    channel_type=metadata.get("channel_type"),
                )
        if isinstance(message.output_channel, CollectingOutputChannel):
            response["response"] = message.output_channel.messages
            return response

        return response

    def _get_action(
        self, action_name: Text
    ) -> Optional[rasa.core.actions.action.Action]:
        return self.action_for_name_or_text(
            action_name, self.domain, self.action_endpoint
        )

    async def fetch_tracker_and_update_session(
        self,
        sender_id: Text,
        output_channel: Optional[OutputChannel] = None,
        metadata: Optional[Dict] = None,
    ) -> DialogueStateTracker:
        """Fetches tracker for `sender_id` and updates its conversation session.

        If a new tracker is created, `action_session_start` is run.

        Args:
            metadata: Data sent from client associated with the incoming user message.
            output_channel: Output channel associated with the incoming user message.
            sender_id: Conversation ID for which to fetch the tracker.

        Returns:
              Tracker for `sender_id`.
        """
        tracker = await self.get_tracker(sender_id)

        await self._update_tracker_session(tracker, output_channel, metadata)

        return tracker

    async def _update_tracker_session(
        self,
        tracker: DialogueStateTracker,
        output_channel: OutputChannel,
        metadata: Optional[Dict] = None,
    ) -> None:
        """Check the current session in `tracker` and update it if expired.

        An 'action_session_start' is run if the latest tracker session has expired,
        or if the tracker does not yet contain any events (only those after the last
        restart are considered).

        Args:
            metadata: Data sent from client associated with the incoming user message.
            tracker: Tracker to inspect.
            output_channel: Output channel for potential utterances in a custom
                `ActionSessionStart`.
        """
        if not tracker.applied_events() or self._has_session_expired(tracker):
            logger.debug(
                f"Starting a new session for conversation ID '{tracker.sender_id}'."
            )

            action_session_start = self._get_action(ACTION_SESSION_START_NAME)

            if metadata:
                tracker.update(
                    SlotSet(SESSION_START_METADATA_SLOT, metadata), self.domain
                )

            await self._run_action(
                action=action_session_start,
                tracker=tracker,
                output_channel=output_channel,
                nlg=self.nlg,
                prediction=PolicyPrediction.for_action_name(
                    self.domain, ACTION_SESSION_START_NAME
                ),
            )

    def predict_next_with_tracker_if_should(
        self, tracker: DialogueStateTracker
    ) -> Tuple[rasa.core.actions.action.Action, PolicyPrediction]:
        """Predicts the next action the bot should take after seeing x.

        This should be overwritten by more advanced policies to use
        ML to predict the action.

        Returns:
             The index of the next action and prediction of the policy.

        Raises:
            ActionLimitReached if the limit of actions to predict has been reached.
        """
        prediction = self._predict_next_with_tracker(tracker)

        action = self.action_for_index(
            prediction.max_confidence_index, self.domain, self.action_endpoint
        )

        logger.debug(
            f"Predicted next action '{action.name()}' with confidence "
            f"{prediction.max_confidence:.2f}."
        )

        return action, prediction

    @staticmethod
    def action_for_name_or_text(
        action_name_or_text: Text,
        domain: Domain,
        action_endpoint: Optional[EndpointConfig],
    ) -> "Action":
        """Retrieves an action by its name or by its text in case it's an end-to-end action.

        Args:
            action_name_or_text: The name of the action.
            domain: The current model domain.
            action_endpoint: The endpoint to execute custom actions.

        Raises:
            ActionNotFoundException: If action not in current domain.

        Returns:
            The instantiated action.
        """
        if action_name_or_text not in domain.action_names_or_texts:
            domain.raise_action_not_found_exception(action_name_or_text)

        defaults = {a.name(): a for a in default_actions(action_endpoint)}

        if (
            action_name_or_text in defaults
            and action_name_or_text not in domain.user_actions_and_forms
        ):
            return defaults[action_name_or_text]

        if action_name_or_text == ACTION_EXTRACT_SLOTS:
            return ActionExtractSlots(action_endpoint)

        if action_name_or_text.startswith(UTTER_PREFIX) and is_retrieval_action(
            action_name_or_text, domain.retrieval_intents
        ):
            return ActionRetrieveResponse(action_name_or_text)

        if action_name_or_text in domain.action_texts:
            return ActionEndToEndResponse(action_name_or_text)

        if action_name_or_text.startswith(UTTER_PREFIX):
            return ActionBotResponse(action_name_or_text)

        if action_name_or_text in domain.loop_names:
            return KLoopAction(action_name_or_text, action_endpoint)

        is_form = action_name_or_text in domain.form_names
        # Users can override the form by defining an action with the same name as the form
        user_overrode_form_action = (
            is_form and action_name_or_text in domain.user_actions
        )
        if is_form and not user_overrode_form_action:
            return FormAction(action_name_or_text, action_endpoint)

        return KRemoteAction(action_name_or_text, action_endpoint)

    def action_for_index(
        self, index: int, domain: Domain, action_endpoint: Optional[EndpointConfig]
    ) -> "Action":
        """Get an action based on its index in the list of available actions.

        Args:
            index: The index of the action. This is usually used by `Policy`s as they
                predict the action index instead of the name.
            domain: The `Domain` of the current model. The domain contains the actions
                provided by the user + the default actions.
            action_endpoint: Can be used to run `custom_actions`
                (e.g. using the `rasa-sdk`).

        Returns:
            The instantiated `Action` or `None` if no `Action` was found for the given
            index.
        """
        if domain.num_actions <= index or index < 0:
            raise IndexError(
                f"Cannot access action at index {index}. "
                f"Domain has {domain.num_actions} actions."
            )

        return self.action_for_name_or_text(
            domain.action_names_or_texts[index], domain, action_endpoint
        )

    async def run_action_extract_slots(
        self, output_channel: OutputChannel, tracker: DialogueStateTracker
    ) -> DialogueStateTracker:
        """Run action to extract slots and update the tracker accordingly.

        Args:
            output_channel: Output channel associated with the incoming user message.
            tracker: A tracker representing a conversation state.

        Returns:
            the given (updated) tracker
        """
        action_extract_slots = self.action_for_name_or_text(
            ACTION_EXTRACT_SLOTS, self.domain, self.action_endpoint
        )
        extraction_events = await action_extract_slots.run(
            output_channel, self.nlg, tracker, self.domain
        )

        await self._send_bot_messages(extraction_events, tracker, output_channel)

        tracker.update_with_events(extraction_events, self.domain)

        structlogger.debug(
            "processor.extract.slots",
            action_extract_slot=ACTION_EXTRACT_SLOTS,
            len_extraction_events=len(extraction_events),
            rasa_events=copy.deepcopy(extraction_events),
        )

        return tracker

    async def run_anonymization_pipeline(self, tracker: DialogueStateTracker):
        """Run the anonymization pipeline on the new tracker events.

        Args:
            tracker: A tracker representing a conversation state.
        """
        anonymization_pipeline = plugin_manager().hook.get_anonymization_pipeline()
        if anonymization_pipeline is None:
            return None

        old_tracker = await self.tracker_store.retrieve(tracker.sender_id)
        new_events = rasa.shared.core.trackers.TrackerEventDiffEngine.event_difference(
            old_tracker, tracker
        )

        anonymization = []
        for event in new_events:
            body = {"sender_id": tracker.sender_id}
            body.update(event.as_dict())
            anonymization_pipeline.run(body)
            anonymization.append(body.copy())
        return anonymization
