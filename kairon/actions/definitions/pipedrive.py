from typing import Text

from loguru import logger
from mongoengine import DoesNotExist
from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher

from kairon import Utility
from kairon.actions.definitions.base import ActionsBase
from kairon.shared.actions.data_objects import ActionServerLogs, PipedriveLeadsAction
from kairon.shared.actions.exception import ActionFailure
from kairon.shared.actions.models import ActionType, KAIRON_ACTION_RESPONSE_SLOT
from kairon.shared.actions.utils import ActionUtility


class ActionPipedriveLeads(ActionsBase):

    def __init__(self, bot: Text, name: Text):
        self.bot = bot
        self.name = name

    def retrieve_config(self):
        try:
            action = PipedriveLeadsAction.objects(bot=self.bot, name=self.name, status=True).get().to_mongo().to_dict()
            logger.debug("pipedrive_leads_action_config: " + str(action))
            action['api_token'] = Utility.decrypt_message(action['api_token'])
        except DoesNotExist as e:
            logger.exception(e)
            raise ActionFailure("No Pipedrive leads action found for given action and bot")
        return action

    async def execute(self, dispatcher: CollectingDispatcher, tracker: Tracker):
        status = "SUCCESS"
        exception = None
        action_config = self.retrieve_config()
        bot_response = action_config.get("response")
        title = f"{tracker.sender_id} {action_config['title']}"
        try:
            _, conversation_as_str = ActionUtility.prepare_message_trail_as_str(tracker.events)
            metadata = ActionUtility.prepare_pipedrive_metadata(tracker, action_config)
            ActionUtility.create_pipedrive_lead(
                domain=action_config['domain'],
                api_token=action_config['api_token'],
                title=title,
                conversation=conversation_as_str,
                **metadata
            )
        except Exception as e:
            logger.exception(e)
            logger.debug(e)
            exception = str(e)
            status = "FAILURE"
            bot_response = "I have failed to create lead for you"
        finally:
            ActionServerLogs(
                type=ActionType.pipedrive_leads_action.value,
                intent=tracker.get_intent_of_latest_message(),
                action=action_config['name'],
                sender=tracker.sender_id,
                bot=tracker.get_slot("bot"),
                exception=exception,
                bot_response=bot_response,
                status=status
            ).save()
        dispatcher.utter_message(bot_response)
        return {KAIRON_ACTION_RESPONSE_SLOT: bot_response}
