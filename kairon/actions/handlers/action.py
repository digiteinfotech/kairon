import logging
from abc import ABC

from rasa_sdk import utils
from rasa_sdk.interfaces import ActionExecutionRejection, ActionNotFoundException
from tornado.escape import json_decode, json_encode
from kairon.shared.tornado.handlers.base import BaseHandler
from rasa_sdk.executor import CollectingDispatcher, ActionExecutor
from .processor import ActionProcessor

logger = logging.getLogger(__name__)


class ActionHandler(BaseHandler, ABC):

    async def process_actions(self, action_call):
        from rasa_sdk.interfaces import Tracker

        action_name = action_call.get("next_action")
        if action_name and action_name.strip():
            logger.debug(f"Received request to run '{action_name}'")

            tracker_json = action_call["tracker"]
            domain = action_call.get("domain", {})
            tracker = Tracker.from_dict(tracker_json)
            dispatcher = CollectingDispatcher()

            events = await ActionProcessor.process_action(dispatcher, tracker, domain, action_name)

            if not events:
                events = []

            validated_events = ActionExecutor.validate_events(events, action_name)
            logger.debug(f"Finished running '{action_name}'")
            return ActionExecutor._create_api_response(validated_events, dispatcher.messages)

        logger.warning("Received an action call without an action.")
        return None

    async def post(self):
        logging.debug(self.request.body)
        request_json = json_decode(self.request.body)
        utils.check_version_compatibility(request_json.get("version"))
        try:
            result = await self.process_actions(request_json)
            self.write(json_encode(result))
        except ActionExecutionRejection as e:
            logger.debug(e)
            body = {"error": e.message, "action_name": e.action_name}
            self.set_status(400)
            self.write(json_encode(body))
        except ActionNotFoundException as e:
            logger.error(e)
            body = {"error": e.message, "action_name": e.action_name}
            self.set_status(400)
            self.write(json_encode(body))
