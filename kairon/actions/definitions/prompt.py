from typing import Text, Dict, Any

from loguru import logger
from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher

from kairon import Utility
from kairon.actions.definitions.base import ActionsBase
from kairon.shared.actions.data_objects import ActionServerLogs
from kairon.shared.actions.exception import ActionFailure
from kairon.shared.actions.models import ActionType
from kairon.shared.actions.utils import ActionUtility
from kairon.shared.constants import FAQ_DISABLED_ERR, KaironSystemSlots
from kairon.shared.data.constant import DEFAULT_NLU_FALLBACK_RESPONSE
from kairon.shared.llm.factory import LLMFactory
from kairon.shared.models import LlmPromptType, LlmPromptSource


class ActionPrompt(ActionsBase):

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
        if not bot_settings['llm_settings']["enable_faq"]:
            raise ActionFailure("Faq feature is disabled for the bot! Please contact support.")
        k_faq_action_config = ActionUtility.get_faq_action_config(self.bot, self.name)
        logger.debug("bot_settings: " + str(bot_settings))
        logger.debug("k_faq_action_config: " + str(k_faq_action_config))
        return k_faq_action_config, bot_settings

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
        k_faq_action_config = {}
        llm = None
        llm_logs = None
        recommendations = None
        bot_response = DEFAULT_NLU_FALLBACK_RESPONSE
        user_msg = tracker.latest_message.get('text')
        is_from_cache = False

        try:
            k_faq_action_config, bot_settings = self.retrieve_config()
            llm_params = await self.__get_llm_params(k_faq_action_config, dispatcher, tracker, domain)
            llm = LLMFactory.get_instance("faq")(self.bot, bot_settings["llm_settings"])
            llm_response = llm.predict(user_msg, **llm_params)
            status = "FAILURE" if llm_response.get("is_failure", False) is True else status
            exception = llm_response.get("exception")
            is_from_cache = llm_response['is_from_cache']
            if is_from_cache and not isinstance(llm_response['content'], str):
                recommendations, bot_response = ActionUtility.format_recommendations(llm_response, k_faq_action_config)
            else:
                bot_response = llm_response['content']
        except Exception as e:
            logger.exception(e)
            logger.debug(e)
            exception = str(e)
            status = "FAILURE"
            bot_response = FAQ_DISABLED_ERR if str(e) == FAQ_DISABLED_ERR else k_faq_action_config.get("failure_message") or DEFAULT_NLU_FALLBACK_RESPONSE
        finally:
            if llm:
                llm_logs = llm.logs
            ActionServerLogs(
                type=ActionType.prompt_action.value,
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
                user_msg=user_msg,
                is_from_cache=is_from_cache
            ).save()
        dispatcher.utter_message(text=bot_response, buttons=recommendations)
        return {KaironSystemSlots.kairon_action_response.value: bot_response}

    async def __get_llm_params(self, k_faq_action_config: dict, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]):
        implementations = {
            "GPT3_FAQ_EMBED": self.__get_gpt_params,
        }

        llm_type = Utility.environment['llm']["faq"]
        if not implementations.get(llm_type):
            raise ActionFailure(f'{llm_type} type LLM is not supported')
        return await implementations[Utility.environment['llm']["faq"]](k_faq_action_config, dispatcher, tracker, domain)

    async def __get_gpt_params(self, k_faq_action_config: dict, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]):
        from kairon.actions.definitions.factory import ActionFactory

        system_prompt = None
        context_prompt = ''
        query_prompt = ''
        history_prompt = None
        is_query_prompt_enabled = False
        similarity_prompt_name = None
        similarity_prompt_instructions = None
        use_similarity_prompt = False
        params = {}
        num_bot_responses = k_faq_action_config['num_bot_responses']
        for prompt in k_faq_action_config['llm_prompts']:
            if prompt['type'] == LlmPromptType.system.value and prompt['is_enabled']:
                system_prompt = f"{prompt['data']}\n"
            elif prompt['type'] == LlmPromptType.user.value and prompt['is_enabled']:
                if prompt['source'] == LlmPromptSource.history.value:
                    history_prompt = ActionUtility.prepare_bot_responses(tracker, num_bot_responses)
                elif prompt['source'] == LlmPromptSource.bot_content.value:
                    similarity_prompt_name = prompt['name']
                    similarity_prompt_instructions = prompt['instructions']
                    use_similarity_prompt = True
                elif prompt['source'] == LlmPromptSource.slot.value:
                    slot_data = tracker.get_slot(prompt['data'])
                    context_prompt += f"{prompt['name']}:\n{slot_data}\n"
                    context_prompt += f"Instructions on how to use {prompt['name']}:\n{prompt['instructions']}\n\n"
                elif prompt['source'] == LlmPromptSource.action.value:
                    action = ActionFactory.get_instance(self.bot, prompt['data'])
                    await action.execute(dispatcher, tracker, domain)
                    if action.is_success:
                        response = action.response
                        context_prompt += f"{prompt['name']}:\n{response}\n"
                        context_prompt += f"Instructions on how to use {prompt['name']}:\n{prompt['instructions']}\n\n"
                else:
                    context_prompt += f"{prompt['name']}:\n{prompt['data']}\n"
                    context_prompt += f"Instructions on how to use {prompt['name']}:\n{prompt['instructions']}\n\n"
            elif prompt['type'] == LlmPromptType.query.value and prompt['is_enabled']:
                query_prompt += f"{prompt['name']}:\n{prompt['data']}\n"
                query_prompt += f"Instructions on how to use {prompt['name']}:\n{prompt['instructions']}\n\n"
                is_query_prompt_enabled = True

        params["top_results"] = k_faq_action_config.get('top_results', 10)
        params["similarity_threshold"] = k_faq_action_config.get('similarity_threshold', 0.70)
        params["hyperparameters"] = k_faq_action_config.get('hyperparameters', Utility.get_llm_hyperparameters())
        params['enable_response_cache'] = k_faq_action_config.get('enable_response_cache', False)
        params["system_prompt"] = system_prompt
        params["context_prompt"] = context_prompt
        params["query_prompt"] = query_prompt
        params["use_query_prompt"] = is_query_prompt_enabled
        params["previous_bot_responses"] = history_prompt
        params['use_similarity_prompt'] = use_similarity_prompt
        params['similarity_prompt_name'] = similarity_prompt_name
        params['similarity_prompt_instructions'] = similarity_prompt_instructions
        return params
