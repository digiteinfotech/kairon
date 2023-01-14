from typing import Tuple, Optional, Text
import rasa
from rasa.core.actions.action import Action, ActionRetrieveResponse, ActionEndToEndResponse, RemoteAction, default_actions
from rasa.core.channels import UserMessage, OutputChannel, CollectingOutputChannel
from rasa.core.policies.policy import PolicyPrediction
from rasa.core.processor import MessageProcessor, logger
from rasa.shared.constants import DOCS_URL_POLICIES, UTTER_PREFIX
from rasa.shared.core.domain import Domain
from rasa.shared.core.events import UserUttered
from rasa.shared.core.trackers import DialogueStateTracker
from rasa.utils.endpoints import EndpointConfig

from kairon.shared.metering.constants import MetricType
from kairon.shared.metering.metering_processor import MeteringProcessor


class KaironMessageProcessor(MessageProcessor):
    """
    Class overriding MessageProcessor implementation from rasa.
    This is done to also retrieve model predictions along with the message response.
    """

    async def _handle_message_with_tracker(
        self, message: UserMessage, tracker: DialogueStateTracker
    ):

        if message.parse_data:
            parse_data = message.parse_data
        else:
            parse_data = await self.parse_message(message, tracker)

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

        return parse_data

    async def _predict_and_execute_next_action(
        self, output_channel: OutputChannel, tracker: DialogueStateTracker
    ):
        # keep taking actions decided by the policy until it chooses to 'listen'
        should_predict_another_action = True
        num_predicted_actions = 0
        actions_predicted = []

        # action loop. predicts actions until we hit action listen
        while (
            should_predict_another_action
            and self._should_handle_message(tracker)
            and num_predicted_actions < self.max_number_of_predictions
        ):
            # this actually just calls the policy's method by the same name
            action, prediction = self.predict_next_action(tracker)
            actions_predicted.append({"action_name": action.name(), "max_confidence": prediction.max_confidence,
                                      "policy_name": prediction.policy_name})

            should_predict_another_action = await self._run_action(
                action, tracker, output_channel, self.nlg, prediction
            )
            num_predicted_actions += 1

        if self.is_action_limit_reached(
            num_predicted_actions, should_predict_another_action
        ):
            # circuit breaker was tripped
            logger.warning(
                "Circuit breaker tripped. Stopped predicting "
                f"more actions for sender '{tracker.sender_id}'."
            )
            if self.on_circuit_break:
                # call a registered callback
                self.on_circuit_break(tracker, output_channel, self.nlg)

        return actions_predicted

    async def log_message(
        self, message: UserMessage, should_save_tracker: bool = True
    ):
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
            self._save_tracker(tracker)

        return tracker, predictions

    async def handle_message(
        self, message: UserMessage
    ):
        """Handle a single message with this processor."""
        response = {"nlu": None, "action": None, "response": None, "slots": None, "events": None}

        # preprocess message if necessary
        tracker, intent_predictions = await self.log_message(message, should_save_tracker=False)
        response["nlu"] = intent_predictions

        if not self.policy_ensemble or not self.domain:
            # save tracker state to continue conversation from this state
            self._save_tracker(tracker)
            rasa.shared.utils.io.raise_warning(
                "No policy ensemble or domain set. Skipping action prediction "
                "and execution.",
                docs=DOCS_URL_POLICIES,
            )
            return response

        actions_predictions = await self._predict_and_execute_next_action(message.output_channel, tracker)
        response["action"] = actions_predictions
        response["slots"] = [f"{s.name}: {s.value}" for s in tracker.slots.values()]

        # save tracker state to continue conversation from this state
        self._save_tracker(tracker)
        metadata = message.metadata
        metric_type = MetricType.prod_chat if metadata.get('is_integration_user') else MetricType.test_chat
        MeteringProcessor.add_metrics(
            metadata.get('bot'), metadata.get('account'), metric_type, user_id=message.sender_id,
            channel_type=metadata.get('channel_type')
        )
        if isinstance(message.output_channel, CollectingOutputChannel):
            response["response"] = message.output_channel.messages
            return response

        return response

    def predict_next_action(
        self, tracker: DialogueStateTracker
    ) -> Tuple[rasa.core.actions.action.Action, PolicyPrediction]:
        """Predicts the next action the bot should take after seeing x.

        This should be overwritten by more advanced policies to use
        ML to predict the action. Returns the index of the next action.
        """
        prediction = self._get_next_action_probabilities(tracker)

        action = KaironMessageProcessor.__action_for_index(
            prediction.max_confidence_index, self.domain, self.action_endpoint
        )

        logger.debug(
            f"Predicted next action '{action.name()}' with confidence "
            f"{prediction.max_confidence:.2f}."
        )

        return action, prediction

    @staticmethod
    def __action_for_index(
            index: int, domain: Domain, action_endpoint: Optional[EndpointConfig]
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

        return KaironMessageProcessor.__action_for_name_or_text(
            domain.action_names_or_texts[index], domain, action_endpoint
        )

    @staticmethod
    def __action_for_name_or_text(
            action_name_or_text: Text, domain: Domain, action_endpoint: Optional[EndpointConfig]
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

        if action_name_or_text.startswith(UTTER_PREFIX) and rasa.core.actions.action.is_retrieval_action(
                action_name_or_text, domain.retrieval_intents
        ):
            return ActionRetrieveResponse(action_name_or_text)

        if action_name_or_text in domain.action_texts:
            return ActionEndToEndResponse(action_name_or_text)

        if action_name_or_text.startswith(UTTER_PREFIX):
            return RemoteAction(action_name_or_text, action_endpoint)

        is_form = action_name_or_text in domain.form_names
        # Users can override the form by defining an action with the same name as the form
        user_overrode_form_action = is_form and action_name_or_text in domain.user_actions
        if is_form and not user_overrode_form_action:
            from rasa.core.actions.forms import FormAction

            return FormAction(action_name_or_text, action_endpoint)

        return RemoteAction(action_name_or_text, action_endpoint)
