from typing import Text, Dict, Any

from loguru import logger
from mongoengine import DoesNotExist
from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher

from kairon.actions.definitions.base import ActionsBase
from kairon.shared.actions.data_objects import ActionServerLogs, PyscriptActionConfig, TriggerInfo
from kairon.shared.actions.exception import ActionFailure
from kairon.shared.actions.models import ActionType, DispatchType
from kairon.shared.actions.utils import ActionUtility
from kairon.shared.constants import KaironSystemSlots


class ActionPyscript(ActionsBase):

    def __init__(self, bot: Text, name: Text):
        """
        Initialize Pyscript action.

        @param bot: bot id
        @param name: action name
        """
        self.bot = bot
        self.name = name

    def retrieve_config(self):
        """
        Fetch Pyscript action configuration parameters from the database

        :return: PyscriptActionConfig containing configuration for the action as a dict.
        """
        try:
            pyscript_action_config_dict = PyscriptActionConfig.objects().get(bot=self.bot, name=self.name,
                                                                             status=True).to_mongo().to_dict()
            logger.debug("pyscript_action_config: " + str(pyscript_action_config_dict))
            pyscript_action_config_dict.pop('_id', None)
            return pyscript_action_config_dict
        except DoesNotExist as e:
            logger.exception(e)
            raise ActionFailure("No pyscript action found for given action and bot")

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

        pyscript_action_config = None
        bot_response = None
        exception = None
        status = "SUCCESS"
        dispatch_bot_response = False
        dispatch_type = DispatchType.text.value
        filled_slots = {}
        msg_logger = []

        try:
            pyscript_action_config = self.retrieve_config()
            tracker_data = ActionUtility.build_context(tracker, True)
            dispatch_bot_response = pyscript_action_config['dispatch_response']
            source_code = pyscript_action_config['source_code']
            response = ActionUtility.run_pyscript(source_code, tracker_data)
            dispatch_type = response.get('type',dispatch_type)
            bot_response = response.get('bot_response')
            slot_values = ActionUtility.filter_out_kairon_system_slots(response.get('slots', {}))
            filled_slots.update(slot_values)
            logger.info("response: " + str(bot_response))
        except Exception as e:
            exception = str(e)
            logger.exception(e)
            status = "FAILURE"
            bot_response = "I have failed to process your request"
        finally:
            if dispatch_bot_response:
                bot_response, message = ActionUtility.handle_utter_bot_response(dispatcher, dispatch_type, bot_response)
                if message:
                    msg_logger.append(message)
            trigger_info_data = action_call.get('trigger_info') or {}
            trigger_info_obj = TriggerInfo(**trigger_info_data)
            ActionServerLogs(
                type=ActionType.pyscript_action.value,
                intent=tracker.get_intent_of_latest_message(skip_fallback_intent=False),
                action=self.name,
                config=pyscript_action_config,
                sender=tracker.sender_id,
                bot_response=str(bot_response) if bot_response else None,
                messages=msg_logger,
                exception=exception,
                bot=self.bot,
                status=status,
                user_msg=tracker.latest_message.get('text'),
                trigger_info=trigger_info_obj
            ).save()
        filled_slots.update({KaironSystemSlots.kairon_action_response.value: bot_response})
        return filled_slots