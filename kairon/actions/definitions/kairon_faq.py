from typing import Text, Dict, Any

from loguru import logger
from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher
from mongoengine import DoesNotExist
from kairon.actions.definitions.base import ActionsBase
from kairon.shared.actions.data_objects import ActionServerLogs
from kairon.shared.actions.exception import ActionFailure
from kairon.shared.actions.models import ActionType, KAIRON_ACTION_RESPONSE_SLOT
from kairon.shared.data.constant import DEFAULT_NLU_FALLBACK_RESPONSE
from kairon.shared.data.data_objects import BotSettings
from kairon.shared.llm.factory import LLMFactory


class ActionKaironFaq(ActionsBase):

    def __init__(self, bot: Text, name: Text):
        """
        Initialize zendesk action.

        @param bot: bot id
        @param name: action name
        """
        self.bot = bot
        self.name = name

    def retrieve_config(self):
        try:
            bot_settings = BotSettings.objects(bot=self.bot, status=True).get()
        except DoesNotExist as e:
            logger.exception(e)
            bot_settings = BotSettings(bot=self.bot, status=True)
        bot_settings = bot_settings.to_mongo().to_dict()
        logger.debug("bot_settings: " + str(bot_settings))
        return bot_settings

    async def execute(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]):
        """
        Fetches response for user query from llm configured.
        Information regarding the execution is logged in ActionServerLogs.

        @param dispatcher: Client to send messages back to the user.
        @param tracker: Tracker object to retrieve slots, events, messages and other contextual information.
        @param domain: Bot domain
        :return: Dict containing slot name as keys and their values.
        """
        status = "SUCCESS"
        exception = None
        llm_response = None
        bot_settings = self.retrieve_config()
        bot_response = DEFAULT_NLU_FALLBACK_RESPONSE
        try:
            if not bot_settings['enable_gpt_llm_faq']:
                bot_response = "Faq feature is disabled for the bot! Please contact support."
                raise ActionFailure(bot_response)
            user_msg = tracker.latest_message.get('text')
            llm = LLMFactory.get_instance(self.bot, "faq")
            llm_response = llm.predict(user_msg)
            if llm_response.get('content') != "I don't know.":
                bot_response = llm_response['content']
        except Exception as e:
            logger.exception(e)
            logger.debug(e)
            exception = str(e)
            status = "FAILURE"
        finally:
            ActionServerLogs(
                type=ActionType.kairon_faq_action.value,
                intent=tracker.get_intent_of_latest_message(),
                action=self.name,
                sender=tracker.sender_id,
                bot=self.bot,
                exception=exception,
                bot_response=bot_response,
                status=status,
                llm_response=llm_response
            ).save()
        dispatcher.utter_message(bot_response)
        return {KAIRON_ACTION_RESPONSE_SLOT: bot_response}
