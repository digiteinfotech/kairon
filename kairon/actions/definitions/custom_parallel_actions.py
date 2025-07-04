import asyncio
from typing import Text, Dict, Any

import aiohttp
from bson import ObjectId
from loguru import logger
from mongoengine import DoesNotExist
from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher

from kairon import Utility
from kairon.actions.definitions.base import ActionsBase
from kairon.shared.actions.data_objects import ActionServerLogs, ParallelActionConfig, TriggerInfo
from kairon.shared.actions.exception import ActionFailure
from kairon.shared.actions.models import ActionType, DispatchType
from kairon.shared.actions.utils import ActionUtility
from kairon.shared.constants import KaironSystemSlots


class ActionParallel(ActionsBase):

    def __init__(self, bot: Text, name: Text):
        """
        Initialize callback action.

        @param bot: Bot ID
        @param name: Action Name
        """
        self.bot = bot
        self.name = name
        self.__response = None
        self.__is_success = False

    def retrieve_config(self):
        """
        Retrieves the action configuration for the given bot and action name.
        Fetches the action configuration from the database.

        @return: Action configuration dictionary.
        """
        try:
            p_action_config_dict = ParallelActionConfig.objects().get(
                bot=self.bot, name=self.name, status=True
            ).to_mongo().to_dict()
            return p_action_config_dict
        except DoesNotExist as e:
            logger.exception(e)
            raise ActionFailure("No parallel action found for given action and bot")

    async def execute(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any], **kwargs):
        """
        Executes the actions in parallel and logs the results.

        @param dispatcher: Dispatcher to send messages back to the user.
        @param tracker: Tracker object to retrieve slots, events, messages, and other contextual information.
        @param domain: Bot domain providing context for the action execution.
        @return: A dictionary of slot changes after executing all actions.
        """
        action_call = kwargs.get('action_call', {})

        exception = None
        filled_slots = {}
        status = "SUCCESS"
        dispatch_bot_response = False
        dispatch_type = DispatchType.text.value
        response_text = ""
        bot_response = None
        trigger_id = ""
        try:
            action_config = self.retrieve_config()
            action_names = action_config['actions']
            dispatch_bot_response = action_config['dispatch_response_text']
            response_text = action_config['response_text']
            log_entry = ActionServerLogs()
            log_entry.save()
            trigger_id = str(log_entry.id)
            results = await asyncio.gather(
                *[self.execute_webhook(action_name, action_call,trigger_id)
                  for action_name in action_names],
                return_exceptions=True
            )

            filled_slots = self.extract_and_update_slots(results, filled_slots)

            self.__is_success = True

        except Exception as e:
            exception = e
            self.__is_success = False
            logger.exception(e)
            status = "FAILURE"
        finally:
            if dispatch_bot_response:
                bot_response, message = ActionUtility.handle_utter_bot_response(dispatcher, dispatch_type, response_text)
                filled_slots.update({KaironSystemSlots.kairon_action_response.value: bot_response})
                if message:
                    logger.exception(message)
            trigger_info_data = action_call.get('trigger_info') or {}
            trigger_info_obj = TriggerInfo(**trigger_info_data)
            if not trigger_id:
                log_entry = ActionServerLogs()
                log_entry.save()
                trigger_id = str(log_entry.id)
            action_server_log_obj=ActionServerLogs.objects(_id=ObjectId(trigger_id)).get()
            action_server_log_obj.type = ActionType.parallel_action.value
            action_server_log_obj.intent = tracker.get_intent_of_latest_message(skip_fallback_intent=False)
            action_server_log_obj.action = self.name
            action_server_log_obj.sender = tracker.sender_id
            action_server_log_obj.exception = str(exception) if exception else None
            action_server_log_obj.bot_response = str(bot_response) if bot_response else None
            action_server_log_obj.bot = self.bot
            action_server_log_obj.status = status
            action_server_log_obj.user_msg = tracker.latest_message.get('text')
            action_server_log_obj.trigger_info = trigger_info_obj
            action_server_log_obj.save()

        return filled_slots

    @property
    def is_success(self):
        """
        Property to check if the action was successful.

        @return: True if the action was successful, False otherwise.
        """
        return self.__is_success

    @property
    def response(self):
        """
        Property to retrieve the response of the action.

        @return: The response from the action execution.
        """
        return self.__response

    async def execute_webhook(self, action_name, action_instance, trigger_id):
        """
        Executes the /webhook call for each action instance.

        @param action_name: The name of the action.
        @param action_instance: The instance of the action to execute.
        @return: The response from the webhook call.
        """
        request_json = action_instance.copy()
        request_json['next_action'] = action_name
        request_json['trigger_info'] = {
            "trigger_name": self.name,
            "trigger_type": ActionType.parallel_action.value,
            "trigger_id": trigger_id
        }

        url = Utility.environment["action"].get("url")

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=request_json) as response:
                response_json = await response.json()

        return response_json


    @staticmethod
    def extract_and_update_slots(results, filled_slots):
        """
        Extracts slot changes from the webhook results and updates the filled_slots dict.

        @param results: List of JSON responses from webhook calls.
        @param filled_slots: Dictionary to update slot values.
        @return: The updated filled_slots dictionary.
        """
        for body in results:
            if isinstance(body, dict) and "events" in body:
                for event in body["events"]:
                    if (
                        isinstance(event, dict)
                        and event.get("event") == "slot"
                        and "name" in event
                        and "value" in event
                    ):
                        filled_slots[event["name"]] = event["value"]
        return filled_slots