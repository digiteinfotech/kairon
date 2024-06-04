from typing import Text, Dict, Any

from loguru import logger
from mongoengine import DoesNotExist
from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher

from kairon.actions.definitions.base import ActionsBase
from kairon.shared.actions.data_objects import FlowActionConfig, ActionServerLogs
from kairon.shared.actions.exception import ActionFailure
from kairon.shared.actions.models import ActionType
from kairon.shared.actions.utils import ActionUtility
from kairon.shared.constants import KaironSystemSlots


class ActionFlow(ActionsBase):

    def __init__(self, bot: Text, name: Text):
        """
        Initialize Flow action.
        @param bot: bot id
        @param name: action name
        """
        self.bot = bot
        self.name = name

    def retrieve_config(self):
        """
        Fetch Flow action configuration parameters from the database
        :return: FlowActionConfig containing configuration for the action as a dict.
        """
        try:
            http_config_dict = FlowActionConfig.objects().get(bot=self.bot,
                                                              name=self.name,
                                                              status=True).to_mongo().to_dict()
            logger.debug("flow_action_config: " + str(http_config_dict))
            return http_config_dict
        except DoesNotExist as e:
            logger.exception(e)
            raise ActionFailure("No Flow action found for given action and bot")

    async def execute(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]):
        """
        Retrieves action config and executes it.
        Information regarding the execution is logged in ActionServerLogs.
        @param dispatcher: Client to send messages back to the user.
        @param tracker: Tracker object to retrieve slots, events, messages and other contextual information.
        @param domain: Bot domain
        :return: Dict containing slot name as keys and their values.
        """
        bot_response = None
        http_response = None
        exception = None
        status = "SUCCESS"
        http_url = None
        headers = {}
        body = {}
        dispatch_response = True
        try:
            flow_action_config = self.retrieve_config()
            bot_response = flow_action_config['response']
            dispatch_response = flow_action_config['dispatch_response']
            body, http_url, headers = ActionUtility.prepare_flow_body(flow_action_config, tracker)
            http_response, status_code, time_elapsed = await ActionUtility.execute_request_async(
                headers=headers, http_url=http_url, request_method="POST", request_body=body
            )
            logger.info("response: " + str(http_response))
        except Exception as e:
            exception = str(e)
            logger.exception(e)
            status = "FAILURE"
            bot_response = "I have failed to process your request"
        finally:
            if dispatch_response:
                dispatcher.utter_message(bot_response)
            ActionServerLogs(
                type=ActionType.flow_action.value,
                intent=tracker.get_intent_of_latest_message(skip_fallback_intent=False),
                action=self.name,
                sender=tracker.sender_id,
                bot=tracker.get_slot("bot"),
                url=http_url,
                headers=headers,
                request_params=body,
                exception=exception,
                api_response=str(http_response) if http_response else None,
                bot_response=bot_response,
                status=status,
                user_msg=tracker.latest_message.get('text')
            ).save()
        return {KaironSystemSlots.kairon_action_response.value: bot_response}
