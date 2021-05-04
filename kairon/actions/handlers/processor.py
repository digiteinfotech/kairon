from typing import Dict, Text, List, Any

from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet
from rasa_sdk.interfaces import Tracker

from ...shared.actions.models import KAIRON_ACTION_RESPONSE_SLOT
from ...shared.actions.data_objects import HttpActionConfig, HttpActionLog
from ...shared.actions.exception import HttpActionFailure
from ...shared.actions.utils import ActionUtility
import logging


class ActionProcessor:

    @staticmethod
    async def process_action(dispatcher: CollectingDispatcher,
                             tracker: Tracker,
                             domain: Dict[Text, Any], action: Text) -> List[Dict[Text, Any]]:
        return await ActionProcessor.__process_http_action(dispatcher, tracker, domain, action)

    @staticmethod
    async def __process_http_action(dispatcher: CollectingDispatcher,
                                    tracker: Tracker,
                                    domain: Dict[Text, Any], action) -> List[Dict[Text, Any]]:
        bot_response = None
        http_response = None
        exception = None
        request_body = None
        status = "SUCCESS"
        http_url = None
        try:
            logging.debug(tracker.current_slot_values())
            intent = tracker.get_intent_of_latest_message()
            logging.debug("intent: " + str(intent))
            logging.debug("tracker.latest_message: " + str(tracker.latest_message))
            bot_id = tracker.get_slot("bot")
            if ActionUtility.is_empty(bot_id) or ActionUtility.is_empty(action):
                raise HttpActionFailure("Bot id and HTTP action configuration name not found in slot")

            http_action_config: HttpActionConfig = ActionUtility.get_http_action_config(bot=bot_id,
                                                                                        action_name=action)
            http_url = http_action_config['http_url']
            request_body = ActionUtility.prepare_request(tracker, http_action_config['params_list'])
            logging.debug("request_body: " + str(request_body))
            http_response = ActionUtility.execute_http_request(auth_token=http_action_config['auth_token'],
                                                               http_url=http_action_config['http_url'],
                                                               request_method=http_action_config['request_method'],
                                                               request_body=request_body)
            logging.debug("http response: " + str(http_response))

            bot_response = ActionUtility.prepare_response(http_action_config['response'], http_response)
            logging.debug("response: " + str(bot_response))
        #  deepcode ignore W0703: General exceptions are captured to raise application specific exceptions
        except Exception as e:
            exception = str(e)
            logging.error(exception)
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
