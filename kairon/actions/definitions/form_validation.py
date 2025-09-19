from typing import Text, Dict, Any

from loguru import logger
from mongoengine import DoesNotExist
from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher

from kairon.actions.definitions.base import ActionsBase
from kairon.shared.actions.data_objects import ActionServerLogs, FormValidationAction, TriggerInfo
from rasa_sdk.forms import REQUESTED_SLOT
from kairon.shared.actions.models import ActionType
from kairon.shared.actions.utils import ActionUtility
from kairon.shared.constants import FORM_SLOT_SET_TYPE
from kairon.shared.data.constant import STATUSES


class ActionFormValidation(ActionsBase):

    def __init__(self, bot: Text, name: Text):
        """
        Initialize form validation action.

        @param bot: bot id
        @param name: action name
        """
        self.bot = bot
        self.name = name

    def retrieve_config(self):
        """
        Fetch Form validation action configuration parameters from the database.

        :return: FormValidationAction object containing configuration for the action
        """
        action = FormValidationAction.objects(bot=self.bot, name=self.name, status=True)
        logger.debug("form_validation_config: " + str(action.to_json()))
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

        form_validations = self.retrieve_config()
        slot = tracker.get_slot(REQUESTED_SLOT)
        slot_value = tracker.get_slot(slot)
        msg = [f'slot: {slot} | slot_value: {slot_value}']
        is_valid = False
        status = STATUSES.FAIL.value
        if ActionUtility.is_empty(slot):
            return {}
        try:
            validation = form_validations.get(slot=slot)
            tracker_data = ActionUtility.build_context(tracker, True)
            msg.append(f'Validation Expression: {validation.validation_semantic}')
            is_required_slot = validation.is_required
            msg.append(f'Slot is required: {is_required_slot}')
            utter_msg_on_valid = validation.valid_response
            utter_msg_on_invalid = validation.invalid_response

            if not ActionUtility.is_empty(validation.validation_semantic):
                is_valid, log = ActionUtility.evaluate_script(script=validation.validation_semantic, data=tracker_data)
                msg.append(f'Expression evaluation log: {log}')
                msg.append(f'Expression evaluation result: {is_valid}')
            elif (is_required_slot and tracker.get_slot(slot) is not None) or not is_required_slot:
                is_valid = True

            if is_valid:
                status = STATUSES.SUCCESS.value
                form_slot_set_type = validation.slot_set.type
                custom_value = validation.slot_set.value
                if custom_value and form_slot_set_type == FORM_SLOT_SET_TYPE.custom.value:
                    slot_value = custom_value
                elif form_slot_set_type == FORM_SLOT_SET_TYPE.slot.value:
                    slot_value = tracker.get_slot(custom_value)
                if not ActionUtility.is_empty(utter_msg_on_valid):
                    dispatcher.utter_message(text=utter_msg_on_valid)
            else:
                slot_value = None
                if not ActionUtility.is_empty(utter_msg_on_invalid):
                    dispatcher.utter_message(utter_msg_on_invalid)
        except DoesNotExist as e:
            logger.exception(e)
            msg.append(f'Skipping validation as no validation config found for slot: {slot}')
            logger.debug(e)
        finally:
            trigger_info_data = action_call.get('trigger_info') or {}
            trigger_info_obj = TriggerInfo(**trigger_info_data)
            ActionServerLogs(
                type=ActionType.form_validation_action.value,
                intent=tracker.get_intent_of_latest_message(skip_fallback_intent=False),
                action=tracker.followup_action,
                sender=tracker.sender_id,
                bot=tracker.get_slot("bot"),
                messages=msg,
                status=status,
                trigger_info=trigger_info_obj
            ).save()

        return {slot: slot_value}
