from typing import Text

from loguru import logger
from mongoengine import DoesNotExist
from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher

from kairon.actions.definitions.base import ActionsBase
from kairon.shared.actions.data_objects import ActionServerLogs, SlotSetAction
from kairon.shared.actions.exception import ActionFailure
from kairon.shared.actions.models import ActionType
from kairon.shared.constants import SLOT_SET_TYPE


class ActionSetSlot(ActionsBase):

    def __init__(self, bot: Text, name: Text):
        self.bot = bot
        self.name = name

    def retrieve_config(self):
        try:
            action = SlotSetAction.objects().get(bot=self.bot, name=self.name, status=True).to_mongo().to_dict()
            logger.debug("slot_set_action_config: " + str(action))
            return action
        except DoesNotExist as e:
            logger.exception(e)
            raise ActionFailure("No Slot set action found for given action and bot")

    async def execute(self, dispatcher: CollectingDispatcher, tracker: Tracker):
        message = []
        reset_slots = {}
        status = 'SUCCESS'
        action_config = self.retrieve_config()
        for slots_to_reset in action_config['set_slots']:
            if slots_to_reset['type'] == SLOT_SET_TYPE.FROM_VALUE.value:
                reset_slots[slots_to_reset['name']] = slots_to_reset['value']
                message.append(f"Setting slot '{slots_to_reset['name']}' to '{slots_to_reset['value']}'.")
            else:
                reset_slots[slots_to_reset['name']] = None
                message.append(f"Resetting slot '{slots_to_reset['name']}' value to None.")

        ActionServerLogs(
            type=ActionType.slot_set_action.value,
            intent=tracker.get_intent_of_latest_message(),
            action=action_config['name'],
            sender=tracker.sender_id,
            messages=message,
            bot=tracker.get_slot("bot"),
            status=status
        ).save()
        return reset_slots
