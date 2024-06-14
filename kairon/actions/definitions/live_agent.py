from typing import Text, Dict, Any

from loguru import logger
from mongoengine import DoesNotExist
from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher

from kairon.actions.definitions.base import ActionsBase
from kairon.shared.actions.data_objects import ActionServerLogs, LiveAgentActionConfig
from kairon.shared.actions.exception import ActionFailure
from kairon.shared.actions.models import ActionType, DispatchType
from kairon.shared.actions.utils import ActionUtility
from kairon.shared.live_agent.live_agent import LiveAgentHandler
from kairon.shared.constants import ChannelTypes


CONST_CHANNEL_NAME_MAP = {
    'TelegramHandler': ChannelTypes.TELEGRAM.value,
    'facebook': ChannelTypes.MESSENGER.value,
    'instagram': ChannelTypes.INSTAGRAM.value,
    'whatsapp': ChannelTypes.WHATSAPP.value,
}


class ActionLiveAgent(ActionsBase):

    def __init__(self, bot: Text, name: Text):
        """
        Initialize HTTP action.

        @param bot: bot id
        @param name: action name
        """
        self.bot = bot
        self.name = 'live_agent_action'
        self.__response = None
        self.__is_success = False

    def retrieve_config(self):
        """
        Fetch LiveAgentAction configuration parameters from the database

        :return: HttpActionConfig containing configuration for the action as a dict.
        """
        try:
            live_agent_config_dict = LiveAgentActionConfig.objects().get(bot=self.bot,
                                                              name=self.name, status=True).to_mongo().to_dict()
            logger.debug("live_agent_action_config: " + str(live_agent_config_dict))
            return live_agent_config_dict
        except DoesNotExist as e:
            logger.exception(e)
            raise ActionFailure("No Live Agent action found for given action and bot")

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
        is_web = False
        try:
            action_config = self.retrieve_config()
            dispatch_bot_response = action_config.get('dispatch_bot_response', True)
            bot_response = action_config.get('bot_response')
            channel_key = tracker.get_latest_input_channel()
            if not channel_key:
                is_web = True
            channel = CONST_CHANNEL_NAME_MAP[channel_key] if channel_key else 'web'
            resp_data = await LiveAgentHandler.request_live_agent(self.bot, tracker.sender_id, channel)
            if resp_data and resp_data.get('msg'):
                bot_response = resp_data.get('msg')
            self.__is_success = True
            self.__response = bot_response
        except Exception as e:
            exception = e
            self.__is_success = False
            logger.exception(e)
            status = "FAILURE"
            bot_response = bot_response if bot_response else "Sorry, I am unable to process your request at the moment."
        finally:
            if dispatch_bot_response:
                if is_web:
                    bot_response = {
                        'action': 'live_agent',
                        'response': bot_response
                    }
                dispatch_type = DispatchType.json.value if is_web else DispatchType.text.value
                bot_response, message = ActionUtility.handle_utter_bot_response(dispatcher, dispatch_type, bot_response)
                if message:
                    msg_logger.append(message)
            ActionServerLogs(
                type=ActionType.live_agent_action.value,
                intent=tracker.get_intent_of_latest_message(skip_fallback_intent=False),
                action=self.name,
                sender=tracker.sender_id,
                bot_response=str(bot_response) if bot_response else None,
                messages=msg_logger,
                exception=str(exception) if exception else None,
                bot=self.bot,
                status=status,
                user_msg=tracker.latest_message.get('text')
            ).save()
        return filled_slots

    @property
    def is_success(self):
        return self.__is_success

    @property
    def response(self):
        return self.__response
