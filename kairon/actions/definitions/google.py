from typing import Text

from loguru import logger
from mongoengine import DoesNotExist
from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher

from kairon import Utility
from kairon.actions.definitions.base import ActionsBase
from kairon.shared.actions.data_objects import GoogleSearchAction, ActionServerLogs
from kairon.shared.actions.exception import ActionFailure
from kairon.shared.actions.models import ActionType, KAIRON_ACTION_RESPONSE_SLOT
from kairon.shared.actions.utils import ActionUtility


class ActionGoogleSearch(ActionsBase):

    def __init__(self, bot: Text, name: Text):
        self.bot = bot
        self.name = name

    def retrieve_config(self):
        try:
            action = GoogleSearchAction.objects(bot=self.bot, name=self.name, status=True).get().to_mongo().to_dict()
            logger.debug("google_search_action_config: " + str(action))
            action['api_key'] = Utility.decrypt_message(action['api_key'])
        except DoesNotExist as e:
            logger.exception(e)
            raise ActionFailure("No Google search action found for given action and bot")
        return action

    async def execute(self, dispatcher: CollectingDispatcher, tracker: Tracker):
        exception = None
        status = "SUCCESS"
        latest_msg = tracker.latest_message.get('text')
        action_config = self.retrieve_config()
        bot_response = action_config.get("failure_response")
        try:
            if not ActionUtility.is_empty(latest_msg):
                results = ActionUtility.perform_google_search(
                    action_config['api_key'], action_config['search_engine_id'], latest_msg,
                    num=action_config.get("num_results")
                )
                if results:
                    bot_response = ActionUtility.format_search_result(results)
        except Exception as e:
            logger.exception(e)
            exception = str(e)
            status = "FAILURE"
        finally:
            ActionServerLogs(
                type=ActionType.google_search_action.value,
                intent=tracker.get_intent_of_latest_message(),
                action=action_config['name'],
                bot_response=bot_response,
                sender=tracker.sender_id,
                bot=tracker.get_slot("bot"),
                exception=exception,
                status=status
            ).save()
        dispatcher.utter_message(bot_response)
        return {KAIRON_ACTION_RESPONSE_SLOT: bot_response}
