from typing import Text, Dict, Any

from loguru import logger
from mongoengine import DoesNotExist
from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher

from kairon.actions.definitions.base import ActionsBase
from kairon.shared.actions.data_objects import ActionServerLogs, DatabaseAction, TriggerInfo
from kairon.shared.actions.exception import ActionFailure
from kairon.shared.actions.models import ActionType
from kairon.shared.actions.utils import ActionUtility
from kairon.shared.constants import KaironSystemSlots
from kairon.shared.vector_embeddings.db.factory import DatabaseFactory


class ActionDatabase(ActionsBase):

    def __init__(self, bot: Text, name: Text):
        """
        Initialize Database action.

        @param bot: bot id
        @param name: action name
        """
        self.bot = bot
        self.name = name
        self.suffix = "_faq_embd"
        self.__response = None
        self.__is_success = False

    def retrieve_config(self):
        """
        Fetch Vector action configuration parameters from the database.

        :return: DatabaseAction containing configuration for the action as dict.
        """
        try:
            bot_settings = ActionUtility.get_bot_settings(bot=self.bot)
            if not bot_settings['llm_settings']["enable_faq"]:
                raise ActionFailure("Faq feature is disabled for the bot! Please contact support.")
            vector_action_dict = DatabaseAction.objects(bot=self.bot, name=self.name,
                                                        status=True).get().to_mongo().to_dict()
            vector_action_dict.pop('_id', None)
            logger.debug("bot_settings: " + str(bot_settings))
            logger.debug("vector_action_config: " + str(vector_action_dict))
            return vector_action_dict, bot_settings
        except DoesNotExist as e:
            logger.exception(e)
            raise ActionFailure("No Vector action found for given action and bot")

    async def execute(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any], **kwargs):
        """
        Retrieves action config and executes it.
        Information regarding the execution is logged in ActionServerLogs.

        @param dispatcher: Client to send messages back to the user.
        @param tracker: Tracker object to retrieve slots, events, messages and other contextual information.
        @param domain: Bot domain
        :return: Dict containing slot name as keys and their values.
        """
        action_call = kwargs.get('action_call')
        if not action_call:
            raise ActionFailure("Missing action_call in kwargs.")

        vector_action_config = None
        response = None
        bot_response = None
        exception = None
        status = "SUCCESS"
        dispatch_bot_response = False
        failure_response = 'I have failed to process your request.'
        filled_slots = {}
        msg_logger = []
        request_body = None

        try:
            vector_action_config, bot_settings = self.retrieve_config()
            dispatch_bot_response = vector_action_config['response']['dispatch']
            failure_response = vector_action_config['failure_response']
            collection_name = f"{self.bot}_{vector_action_config['collection']}{self.suffix}"
            db_type = vector_action_config['db_type']
            vector_db = DatabaseFactory.get_instance(db_type)(self.bot, collection_name,
                                                              bot_settings["llm_settings"])
            payload = vector_action_config['payload']
            request_body = ActionUtility.get_payload(payload, tracker)
            msg_logger.append(request_body)
            tracker_data = ActionUtility.build_context(tracker, True)
            response = await vector_db.perform_operation(request_body, user=tracker.sender_id)
            logger.info("response: " + str(response))
            response_context = self.__add_user_context_to_http_response(response, tracker_data)
            bot_response, bot_resp_log, _ = ActionUtility.compose_response(vector_action_config['response'], response_context)
            msg_logger.append(bot_resp_log)
            slot_values, slot_eval_log, _ = ActionUtility.fill_slots_from_response(vector_action_config.get('set_slots', []),
                                                                                response_context)
            msg_logger.extend(slot_eval_log)
            filled_slots.update(slot_values)
            logger.info("response: " + str(bot_response))
        except Exception as e:
            exception = str(e)
            logger.exception(e)
            status = "FAILURE"
            bot_response = failure_response
        finally:
            if dispatch_bot_response:
                dispatcher.utter_message(bot_response)
            trigger_info_data = action_call.get('trigger_info') or {}
            trigger_info_obj = TriggerInfo(**trigger_info_data)
            ActionServerLogs(
                type=ActionType.database_action.value,
                intent=tracker.get_intent_of_latest_message(skip_fallback_intent=False),
                action=self.name,
                config=vector_action_config,
                sender=tracker.sender_id,
                payload=str(request_body) if request_body else None,
                response=str(response) if response else None,
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

    @staticmethod
    def __add_user_context_to_http_response(http_response, tracker_data):
        response_context = {"data": http_response, 'context': tracker_data}
        return response_context

