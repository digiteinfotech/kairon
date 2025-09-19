from typing import Dict, Text, List, Any

from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet

from rasa_sdk.interfaces import Tracker

from ..definitions.factory import ActionFactory
from ...shared.actions.data_objects import ActionServerLogs
from ...shared.actions.exception import ActionFailure
from ...shared.actions.utils import ActionUtility
from loguru import logger
from kairon.actions.definitions.custom_parallel_actions import ActionParallel
from ...shared.data.constant import STATUSES


class ActionProcessor:

    @staticmethod
    async def process_action(dispatcher: CollectingDispatcher,
                             tracker: Tracker,
                             domain: Dict[Text, Any], action: Text, **kwargs) -> List[Dict[Text, Any]]:
        return await ActionProcessor.__process_action(dispatcher=dispatcher, tracker=tracker, domain=domain, action=action, **kwargs)

    @staticmethod
    async def __process_action(dispatcher: CollectingDispatcher,
                               tracker: Tracker,
                               domain: Dict[Text, Any], action, **kwargs) -> List[Dict[Text, Any]]:
        try:
            logger.info(tracker.current_slot_values())
            intent = tracker.get_intent_of_latest_message()
            logger.info("intent: " + str(intent))
            logger.info("tracker.latest_message: " + str(tracker.latest_message))
            bot_id = tracker.get_slot("bot")
            if ActionUtility.is_empty(bot_id) or ActionUtility.is_empty(action):
                raise ActionFailure("Bot id and action name not found in slot")

            action_instance = ActionFactory.get_instance(bot_id, action)
            slots = await action_instance.execute(dispatcher=dispatcher, tracker=tracker, domain=domain, **kwargs)

            return [SlotSet(slot, value) for slot, value in slots.items()]
        except Exception as e:
            logger.exception(e)
            ActionServerLogs(
                intent=tracker.get_intent_of_latest_message(),
                action=action,
                sender=tracker.sender_id,
                exception=str(e),
                bot=tracker.get_slot("bot"),
                status=STATUSES.FAIL.value
            ).save()
