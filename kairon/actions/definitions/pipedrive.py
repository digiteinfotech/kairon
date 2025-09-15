from typing import Text, Dict, Any

from loguru import logger
from mongoengine import DoesNotExist
from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher

from kairon.actions.definitions.base import ActionsBase
from kairon.shared.actions.data_objects import ActionServerLogs, PipedriveLeadsAction, TriggerInfo
from kairon.shared.actions.exception import ActionFailure
from kairon.shared.actions.models import ActionType
from kairon.shared.actions.utils import ActionUtility
from kairon.shared.constants import KaironSystemSlots
from kairon.shared.data.constant import STATUSES


class ActionPipedriveLeads(ActionsBase):

    def __init__(self, bot: Text, name: Text):
        """
        Initialize Pipedrive action.

        @param bot: bot id
        @param name: action name
        """
        self.bot = bot
        self.name = name

    def retrieve_config(self):
        """
        Fetch PipedriveLeads action configuration parameters from the database.

        :return: PipedriveLeadsAction containing configuration for the action as a dict.
        """
        try:
            action = PipedriveLeadsAction.objects(bot=self.bot, name=self.name, status=True).get().to_mongo().to_dict()
            logger.debug("pipedrive_leads_action_config: " + str(action))
        except DoesNotExist as e:
            logger.exception(e)
            raise ActionFailure("No Pipedrive leads action found for given action and bot")
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

        status = STATUSES.SUCCESS.value
        exception = None
        action_config = self.retrieve_config()
        bot_response = action_config.get("response")
        title = f"{tracker.sender_id} {action_config['title']}"
        api_token = action_config.get('api_token')
        try:
            tracker_data = ActionUtility.build_context(tracker)
            api_token = ActionUtility.retrieve_value_for_custom_action_parameter(tracker_data, api_token, self.bot)
            _, conversation_as_str = ActionUtility.prepare_message_trail_as_str(tracker.events)
            metadata = ActionUtility.prepare_pipedrive_metadata(tracker, action_config)
            ActionUtility.create_pipedrive_lead(
                domain=action_config['domain'],
                api_token=api_token,
                title=title,
                conversation=conversation_as_str,
                **metadata
            )
        except Exception as e:
            logger.exception(e)
            logger.debug(e)
            exception = str(e)
            status = STATUSES.FAIL.value
            bot_response = "I have failed to create lead for you"
        finally:
            trigger_info_data = action_call.get('trigger_info') or {}
            trigger_info_obj = TriggerInfo(**trigger_info_data)
            ActionServerLogs(
                type=ActionType.pipedrive_leads_action.value,
                intent=tracker.get_intent_of_latest_message(skip_fallback_intent=False),
                action=action_config['name'],
                sender=tracker.sender_id,
                bot=tracker.get_slot("bot"),
                exception=exception,
                bot_response=bot_response,
                status=status,
                user_msg=tracker.latest_message.get('text'),
                trigger_info=trigger_info_obj
            ).save()
        dispatcher.utter_message(bot_response)
        return {KaironSystemSlots.kairon_action_response.value: bot_response}
