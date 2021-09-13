from typing import Dict, Text, List, Any

from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet
from rasa_sdk.interfaces import Tracker

from ...shared.actions.models import KAIRON_ACTION_RESPONSE_SLOT, ActionType
from ...shared.actions.data_objects import ActionServerLogs
from ...shared.actions.exception import ActionFailure
from ...shared.actions.utils import ActionUtility
from loguru import logger

from ...shared.constants import SLOT_SET_TYPE


class ActionProcessor:

    @staticmethod
    async def process_action(dispatcher: CollectingDispatcher,
                             tracker: Tracker,
                             domain: Dict[Text, Any], action: Text) -> List[Dict[Text, Any]]:
        return await ActionProcessor.__process_action(dispatcher, tracker, domain, action)

    @staticmethod
    async def __process_action(dispatcher: CollectingDispatcher,
                               tracker: Tracker,
                               domain: Dict[Text, Any], action) -> List[Dict[Text, Any]]:
        slot = KAIRON_ACTION_RESPONSE_SLOT
        bot_response = None
        try:
            logger.info(tracker.current_slot_values())
            intent = tracker.get_intent_of_latest_message()
            logger.info("intent: " + str(intent))
            logger.info("tracker.latest_message: " + str(tracker.latest_message))
            bot_id = tracker.get_slot("bot")
            if ActionUtility.is_empty(bot_id) or ActionUtility.is_empty(action):
                raise ActionFailure("Bot id and action name not found in slot")

            action_config, action_type = ActionUtility.get_action_config(bot=bot_id, name=action)
            if action_type == ActionType.http_action.value:
                slot, bot_response = await ActionProcessor.__process_http_action(tracker, action_config)
                dispatcher.utter_message(bot_response)
            elif action_type == ActionType.slot_set_action.value:
                slot, bot_response = await ActionProcessor.__process_slot_set_action(tracker, action_config)
            return [SlotSet(slot, bot_response)]
        #  deepcode ignore W0703: General exceptions are captured to raise application specific exceptions
        except Exception as e:
            logger.exception(e)
            ActionServerLogs(
                intent=tracker.get_intent_of_latest_message(),
                action=action,
                sender=tracker.sender_id,
                exception=str(e),
                bot=tracker.get_slot("bot"),
                status="FAILURE"
            ).save()

    @staticmethod
    async def __process_http_action(tracker: Tracker, http_action_config: dict):
        bot_response = None
        http_response = None
        exception = None
        request_body = None
        status = "SUCCESS"
        http_url = None
        request_method = None
        try:
            request_body = ActionUtility.prepare_request(tracker, http_action_config['params_list'])
            logger.info("request_body: " + str(request_body))
            request_method = http_action_config['request_method']
            http_response, http_url = ActionUtility.execute_http_request(auth_token=http_action_config['auth_token'],
                                                                         http_url=http_action_config['http_url'],
                                                                         request_method=request_method,
                                                                         request_body=request_body)
            logger.info("http response: " + str(http_response))
            bot_response = ActionUtility.prepare_response(http_action_config['response'], http_response)
            logger.info("response: " + str(bot_response))
        except ActionFailure as e:
            exception = str(e)
            logger.exception(e)
            status = "FAILURE"
            bot_response = "I have failed to process your request"
        except Exception as e:
            exception = str(e)
            logger.exception(e)
            status = "FAILURE"
            bot_response = "I have failed to process your request"
        finally:
            ActionServerLogs(
                type=ActionType.http_action.value,
                intent=tracker.get_intent_of_latest_message(),
                action=http_action_config['action_name'],
                sender=tracker.sender_id,
                url=http_url,
                request_params=None if request_method and request_method.lower() == "get" else request_body,
                api_response=str(http_response) if http_response else None,
                bot_response=str(bot_response) if bot_response else None,
                exception=exception,
                bot=tracker.get_slot("bot"),
                status=status
            ).save()
        return KAIRON_ACTION_RESPONSE_SLOT, bot_response

    @staticmethod
    async def __process_slot_set_action(tracker: Tracker, action_config: dict):
        message = []
        status = 'SUCCESS'

        if action_config['type'] == SLOT_SET_TYPE.FROM_VALUE.value:
            message.append(f"Setting slot '{action_config['slot']}' to '{action_config['value']}'.")
            value = action_config['value']
        else:
            message.append(f"Resetting slot '{action_config['slot']}' value to None.")
            value = None

        ActionServerLogs(
            type=ActionType.slot_set_action.value,
            intent=tracker.get_intent_of_latest_message(),
            action=action_config['name'],
            sender=tracker.sender_id,
            bot_response=value,
            messages=message,
            bot=tracker.get_slot("bot"),
            status=status
        ).save()
        return action_config['slot'], value
