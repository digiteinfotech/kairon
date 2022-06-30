from typing import Text

from loguru import logger
from mongoengine import DoesNotExist
from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher

from kairon import Utility
from kairon.actions.definitions.base import ActionsBase
from kairon.shared.actions.data_objects import ActionServerLogs, ZendeskAction
from kairon.shared.actions.exception import ActionFailure
from kairon.shared.actions.models import ActionType, KAIRON_ACTION_RESPONSE_SLOT
from kairon.shared.actions.utils import ActionUtility


class ActionZendeskTicket(ActionsBase):

    def __init__(self, bot: Text, name: Text):
        """
        Initialize Email action.

        @param bot: bot id
        @param name: action name
        """
        self.bot = bot
        self.name = name

    def retrieve_config(self):
        """
        Fetch Zendesk ticket action configuration parameters from the database.

        :return: ZendeskAction containing configuration for the action as a dict.
        """
        try:
            action = ZendeskAction.objects(bot=self.bot, name=self.name, status=True).get().to_mongo().to_dict()
            logger.debug("zendesk_action_config: " + str(action))
            action['user_name'] = Utility.decrypt_message(action['user_name'])
            action['api_token'] = Utility.decrypt_message(action['api_token'])
        except DoesNotExist as e:
            logger.exception(e)
            raise ActionFailure("No Zendesk action found for given action and bot")
        return action

    async def execute(self, dispatcher: CollectingDispatcher, tracker: Tracker):
        """
        Retrieves action config and executes it.
        Information regarding the execution is logged in ActionServerLogs.

        @param dispatcher: Client to send messages back to the user.
        @param tracker: Tracker object to retrieve slots, events, messages and other contextual information.
        :return: Dict containing slot name as keys and their values.
        """
        status = "SUCCESS"
        exception = None
        action_config = self.retrieve_config()
        bot_response = action_config.get("response")
        subject = f"{tracker.sender_id} {action_config['subject']}"
        try:
            comment = ActionUtility.prepare_email_body(tracker.events, action_config['subject'])
            ActionUtility.create_zendesk_ticket(
                subdomain=action_config['subdomain'],
                user_name=action_config['user_name'],
                api_token=action_config['api_token'],
                subject=subject,
                comment=comment,
                tags=action_config.get('tags')
            )
        except Exception as e:
            logger.exception(e)
            logger.debug(e)
            exception = str(e)
            status = "FAILURE"
            bot_response = "I have failed to create issue for you"
        finally:
            ActionServerLogs(
                type=ActionType.zendesk_action.value,
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
