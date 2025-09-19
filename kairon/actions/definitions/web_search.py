from typing import Text, Dict, Any

from loguru import logger
from mongoengine import DoesNotExist
from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher

from kairon.actions.definitions.base import ActionsBase
from kairon.shared.actions.data_objects import ActionServerLogs, WebSearchAction, TriggerInfo
from kairon.shared.actions.exception import ActionFailure
from kairon.shared.actions.models import ActionType
from kairon.shared.actions.utils import ActionUtility
from kairon.shared.constants import KAIRON_USER_MSG_ENTITY, KaironSystemSlots
from kairon.shared.data.constant import STATUSES


class ActionWebSearch(ActionsBase):

    def __init__(self, bot: Text, name: Text):
        """
        Initialize Public search action.

        @param bot: bot id
        @param name: action name
        """
        self.bot = bot
        self.name = name

    def retrieve_config(self):
        """
        Fetch Public search action configuration parameters from the database.

        :return: WebSearchAction containing configuration for the action as a dict.
        """
        try:
            action = WebSearchAction.objects(bot=self.bot, name=self.name, status=True).get().to_mongo().to_dict()
            logger.debug("public_search_action_config: " + str(action))
        except DoesNotExist as e:
            logger.exception(e)
            raise ActionFailure("No Public search action found for given action and bot")
        return action

    async def execute(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any], **kwargs):
        """
        Retrieves action config and executes it.
        Information regarding the execution is logged in ActionServerLogs.

        @param dispatcher: Client to send messages back to the user.
        @param tracker: Tracker object to retrieve slots, events, messages and other contextual information.
        @param domain: Bot domain
        :return: Dict containing slot name as keys and their values.
        """
        action_call = kwargs.get('action_call', {})

        slots_set = {}
        results = None
        exception = None
        status = STATUSES.SUCCESS.value
        latest_msg = tracker.latest_message.get('text')
        action_config = self.retrieve_config()
        bot_response = action_config.get("failure_response")
        try:
            if not ActionUtility.is_empty(latest_msg) and latest_msg.startswith("/"):
                user_msg = next(tracker.get_latest_entity_values(KAIRON_USER_MSG_ENTITY), None)
                if not ActionUtility.is_empty(user_msg):
                    latest_msg = user_msg
            if not ActionUtility.is_empty(latest_msg):
                results = ActionUtility.perform_web_search(latest_msg,
                                                           topn=action_config.get("topn"),
                                                           website=action_config.get("website"),
                                                           bot=self.bot)
                if results:
                    bot_response = ActionUtility.format_search_result(results)
                    if not ActionUtility.is_empty(action_config.get('set_slot')):
                        slots_set.update({action_config['set_slot']: bot_response})
        except Exception as e:
            logger.exception(e)
            exception = str(e)
            status = STATUSES.FAIL.value
        finally:
            trigger_info_data = action_call.get('trigger_info') or {}
            trigger_info_obj = TriggerInfo(**trigger_info_data)
            ActionServerLogs(
                type=ActionType.web_search_action.value,
                intent=tracker.get_intent_of_latest_message(skip_fallback_intent=False),
                action=action_config['name'],
                public_search_action_response=results,
                bot_response=bot_response,
                sender=tracker.sender_id,
                bot=tracker.get_slot("bot"),
                exception=exception,
                status=status,
                user_msg=tracker.latest_message.get('text'),
                trigger_info=trigger_info_obj
            ).save()
        if action_config.get('dispatch_response', True):
            dispatcher.utter_message(bot_response)
        slots_set.update({KaironSystemSlots.kairon_action_response.value: bot_response})
        return slots_set
