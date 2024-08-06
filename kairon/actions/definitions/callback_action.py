from typing import Text, Dict, Any

from loguru import logger
from mongoengine import DoesNotExist
from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher

from kairon.actions.definitions.base import ActionsBase
from kairon.shared.actions.data_objects import ActionServerLogs, CallbackActionConfig
from kairon.shared.actions.exception import ActionFailure
from kairon.shared.actions.models import ActionType, DispatchType
from kairon.shared.actions.utils import ActionUtility
from kairon.shared.callback.data_objects import CallbackData
from kairon.shared.constants import ChannelTypes


CONST_AVAILABLE_CHANNEL_NAME_MAP = {
    'TelegramHandler': ChannelTypes.TELEGRAM.value,
    'facebook': ChannelTypes.MESSENGER.value,
    'instagram': ChannelTypes.INSTAGRAM.value,
    'whatsapp': ChannelTypes.WHATSAPP.value,
}


class ActionCallback(ActionsBase):

    def __init__(self, bot: Text, name: Text):
        """
        Initialize cakkback action.

        @param bot: bot id
        @param name: action name
        """
        self.bot = bot
        self.name = name
        self.__response = None
        self.__is_success = False

    def retrieve_config(self):
        """
        Fetch AsyncCallbackActionConfig configuration parameters from the database

        :return: AsyncCallbackActionConfig containing configuration for the action as a dict.
        """
        try:
            live_agent_config_dict = CallbackActionConfig.objects().get(bot=self.bot,
                                                                        name=self.name, status=True).to_mongo().to_dict()
            return live_agent_config_dict
        except DoesNotExist as e:
            logger.exception(e)
            raise ActionFailure("No Async Callback action found for given action and bot")

    async def execute(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]):
        """
        Retrieves action config and executes it.
        Information regarding the execution is logged in ActionServerLogs.

        @param dispatcher: Client to send messages back to the user.
        @param tracker: Tracker object to retrieve slots, events, messages and other contextual information.
        @param domain: Bot domain
        :return: Dict containing slot name as keys and their values.
        """
        bot_response = None
        exception = None
        filled_slots = {}
        dispatch_bot_response = True
        status = "SUCCESS"
        msg_logger = []
        callback_url = None
        metadata_log = []
        dynamic_url_slot_name = None
        try:
            action_config = self.retrieve_config()
            dispatch_bot_response = action_config.get('dispatch_bot_response', True)
            bot_response = action_config.get('bot_response')
            dynamic_url_slot_name = action_config.get('dynamic_url_slot_name')
            metadata_list = action_config.get('metadata_list', [])
            callback_name = action_config.get('callback_name')
            sender_id = tracker.sender_id
            channel_key = tracker.get_latest_input_channel()
            channel = CONST_AVAILABLE_CHANNEL_NAME_MAP.get(channel_key, f'unsupported ({channel_key})')
            tracker_data = ActionUtility.build_context(tracker, True)
            tracker_data.update({'bot': self.bot})
            metadata, metadata_log = ActionUtility.prepare_request(tracker_data, metadata_list, self.bot)
            callback_url = CallbackData.create_entry(
                name=self.name,
                callback_config_name=callback_name,
                bot=self.bot,
                sender_id=sender_id,
                channel=channel,
                metadata=metadata
            )
            filled_slots.update({dynamic_url_slot_name: callback_url})
            bot_response = bot_response.replace("{callback_url}", callback_url)

        except Exception as e:
            exception = e
            self.__is_success = False
            logger.exception(e)
            status = "FAILURE"
            bot_response = bot_response if bot_response else "Sorry, I am unable to process your request at the moment."
        finally:
            if dispatch_bot_response:
                bot_response, message = ActionUtility.handle_utter_bot_response(dispatcher, DispatchType.text.value, bot_response)
                if message:
                    msg_logger.append(message)
            ActionServerLogs(
                type=ActionType.callback_action.value,
                intent=tracker.get_intent_of_latest_message(skip_fallback_intent=False),
                action=self.name,
                sender=tracker.sender_id,
                bot_response=str(bot_response) if bot_response else None,
                messages=msg_logger,
                exception=str(exception) if exception else None,
                bot=self.bot,
                status=status,
                user_msg=tracker.latest_message.get('text'),
                callback_url=callback_url,
                callback_url_slot=dynamic_url_slot_name,
                metadata=metadata_log
            ).save()
        return filled_slots

    @property
    def is_success(self):
        return self.__is_success

    @property
    def response(self):
        return self.__response
