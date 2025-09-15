from typing import Text, Dict, Any

from loguru import logger
from mongoengine import DoesNotExist
from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher

from kairon.actions.definitions.base import ActionsBase
from kairon.shared.actions.data_objects import ActionServerLogs, SlotSetAction, TriggerInfo
from kairon.shared.actions.exception import ActionFailure
from kairon.shared.actions.models import ActionType
from kairon.shared.constants import SLOT_SET_TYPE
from kairon.shared.data.constant import STATUSES


class ActionSetSlot(ActionsBase):

    def __init__(self, bot: Text, name: Text):
        """
        Initialize Slot set action.

        @param bot: bot id
        @param name: action name
        """
        self.bot = bot
        self.name = name

    def retrieve_config(self):
        """
        Fetch Slot Setting action configuration parameters from the database.

        :return: SlotSetAction containing configuration for the action as a dict.
        """
        try:
            action = SlotSetAction.objects().get(bot=self.bot, name=self.name, status=True).to_mongo().to_dict()
            logger.debug("slot_set_action_config: " + str(action))
            return action
        except DoesNotExist as e:
            logger.exception(e)
            raise ActionFailure("No Slot set action found for given action and bot")

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

        message = []
        reset_slots = {}
        status = STATUSES.SUCCESS.value
        action_config = self.retrieve_config()
        for slots_to_reset in action_config['set_slots']:
            if slots_to_reset['type'] == SLOT_SET_TYPE.FROM_VALUE.value:
                reset_slots[slots_to_reset['name']] = slots_to_reset['value']
                message.append(f"Setting slot '{slots_to_reset['name']}' to '{slots_to_reset['value']}'.")
            else:
                reset_slots[slots_to_reset['name']] = None
                message.append(f"Resetting slot '{slots_to_reset['name']}' value to None.")

        trigger_info_data = action_call.get('trigger_info') or {}
        trigger_info_obj = TriggerInfo(**trigger_info_data)
        ActionServerLogs(
            type=ActionType.slot_set_action.value,
            intent=tracker.get_intent_of_latest_message(skip_fallback_intent=False),
            action=action_config['name'],
            sender=tracker.sender_id,
            messages=message,
            bot=tracker.get_slot("bot"),
            status=status,
            user_msg=tracker.latest_message.get('text'),
                trigger_info=trigger_info_obj
        ).save()
        return reset_slots
