import logging

from rasa_sdk.executor import CollectingDispatcher, ActionExecutor
from .processor import ActionProcessor

logger = logging.getLogger(__name__)


class ActionHandler():

    @staticmethod
    async def process_actions(action_call):
        from rasa_sdk.interfaces import Tracker

        action_name = action_call.get("next_action")
        if action_name and action_name.strip():
            logger.debug(f"Received request to run '{action_name}'")

            tracker_json = action_call["tracker"]
            domain = action_call.get("domain", {})
            tracker = Tracker.from_dict(tracker_json)
            dispatcher = CollectingDispatcher()

            events = await ActionProcessor.process_action(dispatcher=dispatcher, tracker=tracker, domain=domain, action=action_name, action_call=action_call)

            if not events:
                events = []

            validated_events = ActionExecutor.validate_events(events, action_name)
            logger.debug(f"Finished running '{action_name}'")
            return ActionExecutor._create_api_response(validated_events, dispatcher.messages)

        logger.warning("Received an action call without an action.")
        return None
