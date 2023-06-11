from typing import Text, Dict, Any

from loguru import logger
from mongoengine import DoesNotExist
from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.forms import REQUESTED_SLOT

from kairon.actions.definitions.base import ActionsBase
from kairon.shared.actions.data_objects import ActionServerLogs, FormValidationAction
from kairon.shared.actions.models import ActionType
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
            utter_msg_on_valid = validation.valid_response
            utter_msg_on_invalid = validation.invalid_response
            pre_validation_slot_set_type = validation.slot_set_pre_validation.type
            pre_validation_slot_set_value = validation.slot_set_pre_validation.value
            form_slot_set_type = validation.slot_set.type
            form_slot_set_value = validation.slot_set.value

            slot_value = await self.__get_slot_value_pre_validation(
                slot_value, pre_validation_slot_set_value, pre_validation_slot_set_type, dispatcher, tracker, domain
            )
            logger.info("pre_validation_slot_value: " + str(slot_value))

            if not ActionUtility.is_empty(validation.validation_semantic):
                is_valid, log = ActionUtility.evaluate_script(script=validation.validation_semantic, data=tracker_data)
                msg.append(f'Expression evaluation log: {log}')
                msg.append(f'Expression evaluation result: {is_valid}')
            elif (is_required_slot and tracker.get_slot(slot) is not None) or not is_required_slot:
                is_valid = True

            if is_valid:
                status = "SUCCESS"
                slot_value = self.__get_slot_value_post_validation(
                    slot_value, form_slot_set_value, form_slot_set_type, tracker)
                logger.info("post_validation_slot_value: " + str(slot_value))
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

    async def __execute_http_action(self, action_name: Text, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]):
        from kairon.actions.definitions.factory import ActionFactory

        action = ActionFactory.get_instance(self.bot, action_name)
        await action.execute(dispatcher, tracker, domain)
        if action.is_success:
            response = action.response
        return response

    async def __get_slot_value_pre_validation(
            self, current_value: Any, expected_value: Any, expected_value_type: str,
            dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any],
    ):
        if expected_value_type == FORM_SLOT_SET_TYPE.custom.value and expected_value is not None:
            current_value = expected_value
        elif expected_value_type == FORM_SLOT_SET_TYPE.slot.value:
            current_value = tracker.get_slot(expected_value)
        elif expected_value_type == FORM_SLOT_SET_TYPE.action.value:
            current_value = await self.__execute_http_action(action_name=expected_value, dispatcher=dispatcher,
                                                             tracker=tracker, domain=domain)
        return current_value

    def __get_slot_value_post_validation(
            self, current_value: Any, expected_value: Any, expected_value_type: str, tracker: Tracker,
    ):
        if expected_value and expected_value_type == FORM_SLOT_SET_TYPE.custom.value:
            current_value = expected_value
        elif expected_value_type == FORM_SLOT_SET_TYPE.slot.value:
            current_value = tracker.get_slot(expected_value)
        return current_value
