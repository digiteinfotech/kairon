from typing import Dict, Any, Text, List

from loguru import logger
from rasa_sdk import Action, Tracker
from rasa_sdk.events import SlotSet
from rasa_sdk.executor import CollectingDispatcher

from .data_objects import HttpActionConfig, HttpActionLog
from .action_models import KAIRON_ACTION_RESPONSE_SLOT
from .exception import HttpActionFailure
from .utils import ActionUtility


class HttpAction(Action):
    """
    Executes any HTTP action configured by user
    """
    ActionUtility.connect_db()

    def name(self) -> Text:
        """
        Name of HTTP action.

        :return: Returns literal "http_action".
        """
        return "kairon_http_action"

    async def run(self,
                  dispatcher: CollectingDispatcher,
                  tracker: Tracker,
                  domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        """
        Executes GET, PUT, POST, DELETE Http requests and curates and returns the user defined output.

        :param dispatcher: Rasa provided Dispatcher to send messages back to the user.
        :param tracker: Rasa provided Tracker to maintain the state of a dialogue between the assistant and the user in the form of conversation sessions.
        :param domain: Rasa provided Domain to specify the intents, entities, slots, and actions your bot should know about.
        :return: Curated Http response for the configured Http URL.
        """
        bot_response = None
        http_response = None
        exception = None
        action = None
        request_body = None
        status = "SUCCESS"
        http_url = None
        try:
            logger.debug(tracker.current_slot_values())
            intent = tracker.get_intent_of_latest_message()
            logger.debug("intent: " + str(intent))
            logger.debug("tracker.latest_message: " + str(tracker.latest_message))
            bot_id = tracker.get_slot("bot")
            action = tracker.get_slot("http_action_config" + "_" + intent)
            if ActionUtility.is_empty(bot_id) or ActionUtility.is_empty(action):
                raise HttpActionFailure("Bot id and HTTP action configuration name not found in slot")

            http_action_config: HttpActionConfig = ActionUtility.get_http_action_config(bot=bot_id,
                                                                                        action_name=action)
            http_url = http_action_config['http_url']
            request_body = ActionUtility.prepare_request(tracker, http_action_config['params_list'])
            logger.debug("request_body: " + str(request_body))
            http_response = ActionUtility.execute_http_request(auth_token=http_action_config['auth_token'],
                                                               http_url=http_action_config['http_url'],
                                                               request_method=http_action_config['request_method'],
                                                               request_body=request_body)
            logger.debug("http response: " + str(http_response))

            bot_response = ActionUtility.prepare_response(http_action_config['response'], http_response)
            logger.debug("response: " + str(bot_response))
        #  deepcode ignore W0703: General exceptions are captured to raise application specific exceptions
        except Exception as e:
            exception = str(e)
            logger.error(exception)
            status = "FAILURE"
            bot_response = "I have failed to process your request"
        finally:
            dispatcher.utter_message(bot_response)
            HttpActionLog(
                intent=tracker.get_intent_of_latest_message(),
                action=action,
                sender=tracker.sender_id,
                url=http_url,
                request_params=request_body,
                api_response=str(http_response),
                bot_response=str(bot_response),
                exception=exception,
                bot=tracker.get_slot("bot"),
                status=status
            ).save()

        return [SlotSet(KAIRON_ACTION_RESPONSE_SLOT, bot_response)]
