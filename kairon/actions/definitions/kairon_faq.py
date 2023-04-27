from typing import Text, Dict, Any

from loguru import logger
from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher
from kairon.actions.definitions.base import ActionsBase
from kairon.shared.actions.data_objects import ActionServerLogs
from kairon.shared.actions.exception import ActionFailure
from kairon.shared.actions.models import ActionType, KAIRON_ACTION_RESPONSE_SLOT
from kairon.shared.actions.utils import ActionUtility
from kairon.shared.data.constant import DEFAULT_NLU_FALLBACK_RESPONSE
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
        bot_settings = ActionUtility.get_bot_settings(bot=self.bot)
        if not bot_settings['enable_gpt_llm_faq']:
            bot_response = "Faq feature is disabled for the bot! Please contact support."
            raise ActionFailure(bot_response)
        k_faq_action_config = ActionUtility.get_faq_action_config(bot=self.bot)
        logger.debug("bot_settings: " + str(bot_settings))
        logger.debug("k_faq_action_config: " + str(k_faq_action_config))
        return k_faq_action_config

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
        k_faq_action_config = None
        llm_logs = None
        recommendations = None
        bot_response = "Faq feature is disabled for the bot! Please contact support."
        user_msg = tracker.latest_message.get('text')
        try:
            k_faq_action_config = self.retrieve_config()
            use_bot_responses = k_faq_action_config.get('use_bot_responses')
            num_bot_responses = k_faq_action_config.get('num_bot_responses')
            if use_bot_responses:
                previous_bot_responses = ActionUtility.prepare_bot_responses(tracker, num_bot_responses)
                k_faq_action_config['previous_bot_responses'] = previous_bot_responses
            bot_response = DEFAULT_NLU_FALLBACK_RESPONSE
            llm = LLMFactory.get_instance(self.bot, "faq")
            llm_response = llm.predict(user_msg, **k_faq_action_config)
            llm_logs = llm.logs
            if llm_response['is_from_cache'] and not isinstance(llm_response['content'], str):
                recommendations, bot_response = ActionUtility.format_recommendations(llm_response, k_faq_action_config)
            else:
                bot_response = llm_response['content']
        except Exception as e:
            logger.exception(e)
            logger.debug(e)
            exception = str(e)
            status = "FAILURE"
        finally:
            ActionServerLogs(
                type=ActionType.kairon_faq_action.value,
                intent=tracker.get_intent_of_latest_message(skip_fallback_intent=False),
                action=self.name,
                sender=tracker.sender_id,
                bot=self.bot,
                exception=exception,
                recommendations=recommendations,
                bot_response=bot_response,
                status=status,
                llm_response=llm_response,
                kairon_faq_action_config=k_faq_action_config,
                llm_logs=llm_logs,
                user_msg=user_msg
            ).save()
        dispatcher.utter_message(text=bot_response, buttons=recommendations)
        return {KAIRON_ACTION_RESPONSE_SLOT: bot_response}
