from typing import Text, Dict, Any

from loguru import logger
from mongoengine import DoesNotExist
from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher

from kairon.actions.definitions.base import ActionsBase
from kairon.shared.actions.data_objects import ActionServerLogs, FormValidationAction
from rasa_sdk.forms import REQUESTED_SLOT
from kairon.shared.actions.models import ActionType, DispatchType
from kairon.shared.actions.utils import ActionUtility
from kairon.shared.constants import FORM_SLOT_SET_TYPE


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

    async def execute(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]):
        """
        Retrieves action config and executes it.
        Information regarding the execution is logged in ActionServerLogs.

        @param dispatcher: Client to send messages back to the user.
        @param tracker: Tracker object to retrieve slots, events, messages and other contextual information.
        @param domain: Bot domain
        :return: Dict containing slot name as keys and their values.
        """
        form_validations = self.retrieve_config()
        slot = tracker.get_slot(REQUESTED_SLOT)
        slot_value = tracker.get_slot(slot)
        msg = [f'slot: {slot} | slot_value: {slot_value}']
        is_valid = False
        status = "FAILURE"
        if ActionUtility.is_empty(slot):
            return {}
        try:
            validation = form_validations.get(slot=slot)
            tracker_data = ActionUtility.build_context(tracker, True)
            msg.append(f'Validation Expression: {validation.validation_semantic}')
            is_required_slot = validation.is_required
            msg.append(f'Slot is required: {is_required_slot}')

            if not ActionUtility.is_empty(validation.validation_semantic):
                is_valid, log = ActionUtility.evaluate_script(script=validation.validation_semantic, data=tracker_data)
                msg.append(f'Expression evaluation log: {log}')
                msg.append(f'Expression evaluation result: {is_valid}')
            elif (is_required_slot and tracker.get_slot(slot) is not None) or not is_required_slot:
                is_valid = True
            status, slot_value = self.__utter_message_on_validation(is_valid, validation, dispatcher, tracker)
        except DoesNotExist as e:
            logger.exception(e)
            msg.append(f'Skipping validation as no validation config found for slot: {slot}')
            logger.debug(e)
        finally:
            ActionServerLogs(
                type=ActionType.form_validation_action.value,
                intent=tracker.get_intent_of_latest_message(skip_fallback_intent=False),
                action=tracker.followup_action,
                sender=tracker.sender_id,
                bot=tracker.get_slot("bot"),
                messages=msg,
                status=status
            ).save()

        return {slot: slot_value}

    def __utter_message_on_validation(self, is_valid: bool, validation: FormValidationAction,
                                      dispatcher: CollectingDispatcher, tracker: Tracker):
        slot = tracker.get_slot(REQUESTED_SLOT)
        slot_value = tracker.get_slot(slot)
        utter_msg_on_valid = validation.valid_response
        utter_msg_on_invalid = validation.invalid_response
        dispatch_slot_value = validation.dispatch_slot
        dispatch_type = validation.dispatch_type
        status = "FAILURE"
        if is_valid:
            status = "SUCCESS"
            form_slot_set_type = validation.slot_set.type
            custom_value = validation.slot_set.value
            if custom_value and form_slot_set_type == FORM_SLOT_SET_TYPE.custom.value:
                slot_value = custom_value
            elif form_slot_set_type == FORM_SLOT_SET_TYPE.slot.value:
                slot_value = tracker.get_slot(custom_value)
            if not ActionUtility.is_empty(utter_msg_on_valid):
                dispatcher.utter_message(text=utter_msg_on_valid)
        else:
            if dispatch_slot_value:
                if dispatch_type == DispatchType.json.value:
                    dispatcher.utter_message(json_message=slot_value)
                else:
                    dispatcher.utter_message(text=slot_value)
            elif not ActionUtility.is_empty(utter_msg_on_invalid):
                dispatcher.utter_message(utter_msg_on_invalid)
            slot_value = None
        return status, slot_value
