from typing import Text, Dict, Any

from loguru import logger
from mongoengine import DoesNotExist
from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher

from kairon.actions.definitions.base import ActionsBase
from kairon.shared.actions.data_objects import ActionServerLogs, HubspotFormsAction
from kairon.shared.actions.exception import ActionFailure
from kairon.shared.actions.models import ActionType, KAIRON_ACTION_RESPONSE_SLOT
from kairon.shared.actions.utils import ActionUtility


class ActionHubspotForms(ActionsBase):

    def __init__(self, bot: Text, name: Text):
        """
        Initialize Hubspot action.

        @param bot: bot id
        @param name: action name
        """
        self.bot = bot
        self.name = name

    def retrieve_config(self):
        """
        Fetch Hubspot form action configuration parameters from the database.

        :return: HubspotFormsAction containing configuration for the action as a dict.
        """
        try:
            action = HubspotFormsAction.objects(bot=self.bot, name=self.name, status=True).get().to_mongo().to_dict()
            logger.debug("hubspot_forms_action_config: " + str(action))
        except DoesNotExist as e:
            logger.exception(e)
            raise ActionFailure("No Hubspot forms action found for given action and bot")
        return action

    async def execute(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]):
        """
        Retrieves action config and executes it.
        Information regarding the execution is logged in ActionServerLogs.

        @param dispatcher: Client to send messages back to the user.
        @param tracker: Tracker object to retrieve slots, events, messages and other contextual information.
        @param domain: Bot domain
        :return: Dict containing slot name as keys and their values.
        """
        status = "SUCCESS"
        exception = None
        http_response = None
        request_body = None
        action_config = self.retrieve_config()
        portal_id = action_config.get('portal_id')
        form_guid = action_config.get('form_guid')
        bot_response = action_config.get("response")
        try:
            http_url = f"https://api.hsforms.com/submissions/v3/integration/submit/{portal_id}/{form_guid}"
            tracker_data = ActionUtility.build_context(tracker)
            request_body = ActionUtility.prepare_hubspot_form_request(tracker_data, action_config.get("fields"), self.bot)
            http_response = ActionUtility.execute_http_request(
                http_url=http_url, request_method="POST", request_body=request_body
            )
        except Exception as e:
            logger.exception(e)
            logger.debug(e)
            exception = str(e)
            status = "FAILURE"
            bot_response = "I have failed to process your request"
        finally:
            ActionServerLogs(
                type=ActionType.hubspot_forms_action.value,
                request_params=request_body,
                intent=tracker.get_intent_of_latest_message(),
                action=action_config['name'],
                sender=tracker.sender_id,
                bot=tracker.get_slot("bot"),
                exception=exception,
                api_response=str(http_response) if http_response else None,
                bot_response=bot_response,
                status=status
            ).save()
        dispatcher.utter_message(bot_response)
        return {KAIRON_ACTION_RESPONSE_SLOT: bot_response}
