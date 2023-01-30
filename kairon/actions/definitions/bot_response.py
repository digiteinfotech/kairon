import random
from typing import Text, Dict, Any

from loguru import logger
from mongoengine import DoesNotExist
from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher

from kairon.shared.data.constant import DOMAIN
from kairon.shared.data.data_objects import BotSettings
from kairon.actions.definitions.base import ActionsBase
from kairon.shared.actions.data_objects import ActionServerLogs
from kairon.shared.actions.models import ActionType, KAIRON_ACTION_RESPONSE_SLOT
from kairon.shared.actions.utils import ActionUtility


class ActionKaironBotResponse(ActionsBase):

    def __init__(self, bot: Text, name: Text):
        """
        Initialize kAIron bot response action.

        @param bot: bot id
        @param name: action name
        """
        self.bot = bot
        self.name = name

    def retrieve_config(self):
        """
        Fetch Bot settings from the database.
        This action requires flag on whether to rephrase the
        bot utterance and the token required for performing the same.

        :return: BotSettings containing configuration for the action as dict.
        """
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
        Retrieves bot settings and triggers gpt api if response rephrasing
        is set to true else returns the response template as it is.
        Information regarding the execution is logged in ActionServerLogs.

        @param dispatcher: Client to send messages back to the user.
        @param tracker: Tracker object to retrieve slots, events, messages and other contextual information.
        @param domain: Bot domain
        :return: Dict containing slot name as keys and their values.
        """
        status = "SUCCESS"
        exception = None
        is_rephrased = False
        raw_resp = None
        bot_settings = self.retrieve_config()
        static_response = domain[DOMAIN.RESPONSES.value].get(self.name, [])
        bot_response = {"response": self.name}
        try:
            text_response = random.choice(static_response)
            text_response = text_response.get('text')
            if static_response and bot_settings['rephrase_response'] and not ActionUtility.is_empty(text_response):
                raw_resp, rephrased_message = ActionUtility.trigger_rephrase(self.bot, text_response)
                if rephrased_message:
                    is_rephrased = True
                    bot_response = {"text": rephrased_message}
        except Exception as e:
            logger.exception(e)
            logger.debug(e)
            exception = str(e)
            status = "FAILURE"
        finally:
            ActionServerLogs(
                type=ActionType.kairon_bot_response.value,
                intent=tracker.get_intent_of_latest_message(),
                action=self.name,
                sender=tracker.sender_id,
                bot=self.bot,
                exception=exception,
                bot_response=str(bot_response),
                status=status,
                enable_rephrasing=bot_settings['rephrase_response'],
                is_rephrased=is_rephrased,
                raw_gpt_response=raw_resp
            ).save()
        dispatcher.utter_message(**bot_response)
        return {KAIRON_ACTION_RESPONSE_SLOT: bot_response}
