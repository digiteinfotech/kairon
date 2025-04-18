from typing import Text, Dict, Any

from loguru import logger
from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher

from kairon.actions.definitions.base import ActionsBase
from kairon.shared.actions.data_objects import ActionServerLogs
from kairon.shared.actions.exception import ActionFailure
from kairon.shared.actions.models import ActionType, UserMessageType
from kairon.shared.actions.utils import ActionUtility
from kairon.shared.admin.processor import Sysadmin
from kairon.shared.constants import FAQ_DISABLED_ERR, KaironSystemSlots, KAIRON_USER_MSG_ENTITY
from kairon.shared.data.constant import DEFAULT_NLU_FALLBACK_RESPONSE
from kairon.shared.models import LlmPromptType, LlmPromptSource
from kairon.shared.llm.processor import LLMProcessor



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
        user_msg = None
        bot_response = DEFAULT_NLU_FALLBACK_RESPONSE
        slots_to_fill = {}
        events = []
        time_taken_llm_response = 0
        time_taken_slots = 0
        final_slots = {"type": "slots_to_fill"}
        llm_response_log = {"type": "llm_response"}
        llm_processor = None
        media_ids = None
        try:
            k_faq_action_config, bot_settings = self.retrieve_config()
            user_question = k_faq_action_config.get('user_question')
            user_msg = self.__get_user_msg(tracker, user_question)
            llm_type = k_faq_action_config['llm_type']
            llm_params = await self.__get_llm_params(k_faq_action_config, dispatcher, tracker, domain)
            llm_processor = LLMProcessor(self.bot, llm_type)
            model_to_check = llm_params['hyperparameters'].get('model')
            Sysadmin.check_llm_model_exists(model_to_check, llm_type, self.bot)
            media_ids = tracker.get_slot('media_ids')
            llm_response, time_taken_llm_response = await llm_processor.predict(user_msg,
                                                                                user= tracker.sender_id,
                                                                                invocation='prompt_action',
                                                                                llm_type=llm_type,
                                                                                media_ids=media_ids,
                                                                                **llm_params)
            status = "FAILURE" if llm_response.get("is_failure", False) is True else status
            exception = llm_response.get("exception")
            bot_response = llm_response['content']
            tracker_data = ActionUtility.build_context(tracker, True)
            response_context = self.__add_user_context_to_http_response(bot_response, tracker_data)
            slot_values, slot_eval_log, time_taken_slots = ActionUtility.fill_slots_from_response(
                k_faq_action_config.get('set_slots', []), response_context)
            if slot_values:
                slots_to_fill.update(slot_values)

            final_slots.update({"data": slot_values, "slot_eval_log": slot_eval_log, "time_elapsed": time_taken_slots})
            llm_response_log.update({"response": bot_response, "llm_response_log": llm_response,
                                     "time_elapsed": time_taken_llm_response})
        except Exception as e:
            logger.exception(e)
            logger.debug(e)
            exception = str(e)
            status = "FAILURE"
            bot_response = FAQ_DISABLED_ERR if str(e) == FAQ_DISABLED_ERR else k_faq_action_config.get("failure_message") or DEFAULT_NLU_FALLBACK_RESPONSE
        finally:
            total_time_elapsed = time_taken_llm_response + time_taken_slots
            events_to_extend = [llm_response_log, final_slots]
            events.extend(events_to_extend)
            if llm_processor:
                llm_logs = llm_processor.logs
            ActionServerLogs(
                type=ActionType.prompt_action.value,
                intent=tracker.get_intent_of_latest_message(skip_fallback_intent=False),
                action=self.name,
                sender=tracker.sender_id,
                events=events,
                bot=self.bot,
                exception=exception,
                recommendations=recommendations,
                bot_response=bot_response,
                status=status,
                llm_response=llm_response,
                kairon_faq_action_config=k_faq_action_config,
                llm_logs=llm_logs,
                user_msg=user_msg,
                media_ids=media_ids,
                time_elapsed=total_time_elapsed
            ).save()
        if k_faq_action_config.get('dispatch_response', True):
            dispatcher.utter_message(text=bot_response, buttons=recommendations)
        slots_to_fill.update({KaironSystemSlots.kairon_action_response.value: bot_response})

        return slots_to_fill

    async def __get_llm_params(self, k_faq_action_config: dict, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]):
        from kairon.actions.definitions.factory import ActionFactory

        system_prompt = None
        context_prompt = ''
        query_prompt = ''
        query_prompt_dict = {}
        history_prompt = None
        similarity_prompt = []
        params = {}
        num_bot_responses = k_faq_action_config['num_bot_responses']
        for prompt in k_faq_action_config['llm_prompts']:
            if prompt['type'] == LlmPromptType.system.value and prompt['is_enabled']:
                system_prompt = f"{prompt['data']}\n"
            elif prompt['type'] == LlmPromptType.user.value and prompt['is_enabled']:
                if prompt['source'] == LlmPromptSource.history.value:
                    history_prompt = ActionUtility.prepare_bot_responses(tracker, num_bot_responses)
                elif prompt['source'] == LlmPromptSource.bot_content.value and prompt['is_enabled']:
                    use_similarity_prompt = True
                    hyperparameters = prompt.get("hyperparameters", {})
                    similarity_prompt.append({'similarity_prompt_name': prompt['name'],
                                              'similarity_prompt_instructions': prompt['instructions'],
                                              'collection': prompt['data'],
                                              'use_similarity_prompt': use_similarity_prompt,
                                              'top_results': hyperparameters.get('top_results', 10),
                                              'similarity_threshold': hyperparameters.get('similarity_threshold',
                                                                                          0.70)})
                elif prompt['source'] == LlmPromptSource.slot.value:
                    slot_data = tracker.get_slot(prompt['data'])
                    context_prompt += f"{prompt['name']}:\n{slot_data}\n"
                    if prompt['instructions']:
                        context_prompt += f"Instructions on how to use {prompt['name']}:\n{prompt['instructions']}\n\n"
                elif prompt['source'] == LlmPromptSource.action.value:
                    action = ActionFactory.get_instance(self.bot, prompt['data'])
                    await action.execute(dispatcher, tracker, domain)
                    if action.is_success:
                        response = action.response
                        context_prompt += f"{prompt['name']}:\n{response}\n"
                        if prompt['instructions']:
                            context_prompt += f"Instructions on how to use {prompt['name']}:\n{prompt['instructions']}\n\n"
                else:
                    context_prompt += f"{prompt['name']}:\n{prompt['data']}\n"
                    if prompt['instructions']:
                        context_prompt += f"Instructions on how to use {prompt['name']}:\n{prompt['instructions']}\n\n"
            elif prompt['type'] == LlmPromptType.query.value and prompt['is_enabled']:
                query_prompt += f"{prompt['name']}:\n{prompt['data']}\n"
                if prompt['instructions']:
                    query_prompt += f"Instructions on how to use {prompt['name']}:\n{prompt['instructions']}\n\n"
                is_query_prompt_enabled = True
                query_prompt_dict.update({'query_prompt': query_prompt, 'use_query_prompt': is_query_prompt_enabled})

        params["hyperparameters"] = k_faq_action_config['hyperparameters']
        params["system_prompt"] = system_prompt
        params["context_prompt"] = context_prompt
        params["query_prompt"] = query_prompt_dict
        params["previous_bot_responses"] = history_prompt
        params["similarity_prompt"] = similarity_prompt
        params['instructions'] = k_faq_action_config.get('instructions', [])
        return params

    @staticmethod
    def __add_user_context_to_http_response(http_response, tracker_data):
        response_context = {"data": http_response, 'context': tracker_data}
        return response_context
    
    @staticmethod
    def __get_user_msg(tracker: Tracker, user_question: Dict):
        user_question_type = user_question.get('type')
        if user_question_type == UserMessageType.from_slot.value:
            slot = user_question.get('value')
            user_msg = tracker.get_slot(slot)
        else:
            user_msg = tracker.latest_message.get('text')
            if not ActionUtility.is_empty(user_msg) and user_msg.startswith("/"):
                msg = next(tracker.get_latest_entity_values(KAIRON_USER_MSG_ENTITY), None)
                if not ActionUtility.is_empty(msg):
                    user_msg = msg
        return user_msg
