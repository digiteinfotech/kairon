from typing import Text, Dict, Any

from loguru import logger
from mongoengine import DoesNotExist
from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher

from kairon.actions.definitions.base import ActionsBase
from kairon.shared.actions.data_objects import ActionServerLogs, FormValidationAction
from rasa_sdk.forms import REQUESTED_SLOT
from kairon.shared.actions.models import ActionType
from kairon.shared.actions.utils import ActionUtility, ExpressionEvaluator


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
        status = "FAILURE"
        if ActionUtility.is_empty(slot):
            return {}
        try:
            validation = form_validations.get(slot=slot)
            slot_type = ActionUtility.get_slot_type(validation.bot, slot)
            msg.append(f'slot_type: {slot_type}')
            semantic = validation.validation_semantic
            msg.append(f'validation: {semantic}')
            utter_msg_on_valid = validation.valid_response
            utter_msg_on_invalid = validation.invalid_response
            msg.append(f'utter_msg_on_valid: {utter_msg_on_valid}')
            msg.append(f'utter_msg_on_valid: {utter_msg_on_invalid}')
            expr_as_str, is_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value, semantic)
            msg.append(f'Expression: {expr_as_str}')
            msg.append(f'is_valid: {is_valid}')

            if is_valid:
                status = "SUCCESS"
                if not ActionUtility.is_empty(utter_msg_on_valid):
                    dispatcher.utter_message(text=utter_msg_on_valid)

            if not is_valid:
                slot_value = None
                if not ActionUtility.is_empty(utter_msg_on_invalid):
                    dispatcher.utter_message(utter_msg_on_invalid)
        except DoesNotExist as e:
            logger.exception(e)
            msg.append(f'Skipping validation as no validation config found for slot: {slot}')
            logger.debug(e)
        finally:
            ActionServerLogs(
                type=ActionType.form_validation_action.value,
                intent=tracker.get_intent_of_latest_message(),
                action=tracker.followup_action,
                sender=tracker.sender_id,
                bot=tracker.get_slot("bot"),
                messages=msg,
                status=status
            ).save()

        return {slot: slot_value}
