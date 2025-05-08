import asyncio
from typing import Text, Dict, Any
from loguru import logger
from mongoengine import DoesNotExist
from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher
from kairon.actions.definitions.base import ActionsBase
from kairon.shared.actions.data_objects import ActionServerLogs, ParallelActionConfig
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
            p_action_config_dict = ParallelActionConfig .objects().get(
                bot=self.bot, name=self.name, status=True
            ).to_mongo().to_dict()
            return p_action_config_dict
        except DoesNotExist as e:
            logger.exception(e)
            raise ActionFailure("No parallel action found for given action and bot")

    async def execute(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]):
        """
        Executes the actions in parallel and logs the results.

        @param dispatcher: Dispatcher to send messages back to the user.
        @param tracker: Tracker object to retrieve slots, events, messages, and other contextual information.
        @param domain: Bot domain providing context for the action execution.
        @return: A dictionary of slot changes after executing all actions.
        """
        from kairon.actions.definitions.factory import ActionFactory

        exception = None
        slot_changes = []
        filled_slots = {}
        status = "SUCCESS"
        dispatch_bot_response = False
        dispatch_type = DispatchType.text.value
        response_text = ""
        bot_response = None
        try:
            action_config = self.retrieve_config()
            action_names = action_config['actions']
            bot = action_config['bot']
            dispatch_bot_response = action_config['dispatch_response_text']
            response_text = action_config['response_text']
            actions = [
                (ActionFactory.get_instance(bot, name), name)
                for name in action_names
            ]

            results = await asyncio.gather(
                *[action[0].execute(dispatcher, tracker, domain) for action in actions],
                return_exceptions=True
            )

            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.exception(result)
                    raise result

                slot_changes.append((result, actions[i][1]))
                filled_slots.update(result)

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
            ActionServerLogs(
                type=ActionType.parallel_action.value,
                intent=tracker.get_intent_of_latest_message(skip_fallback_intent=False),
                action=self.name,
                sender=tracker.sender_id,
                exception=str(exception) if exception else None,
                bot_response=str(bot_response) if bot_response else None,
                bot=self.bot,
                status=status,
                user_msg=tracker.latest_message.get('text'),
                slot_changes=slot_changes
            ).save()

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
