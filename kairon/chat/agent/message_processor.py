import rasa
from rasa.core.channels import UserMessage, OutputChannel, CollectingOutputChannel
from rasa.core.processor import MessageProcessor, logger
from rasa.shared.constants import DOCS_URL_POLICIES
from rasa.shared.core.events import UserUttered
from rasa.shared.core.trackers import DialogueStateTracker


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
            actions_predicted.append(action.name())

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

        if isinstance(message.output_channel, CollectingOutputChannel):
            response["response"] = message.output_channel.messages
            return response

        return response
