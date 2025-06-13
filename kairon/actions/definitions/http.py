import ujson as json
from ujson import JSONDecodeError
from typing import Text, Dict, Any

from loguru import logger
from mongoengine import DoesNotExist
from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher

from kairon.actions.definitions.base import ActionsBase
from kairon.shared.actions.data_objects import ActionServerLogs, HttpActionConfig, TriggerInfo
from kairon.shared.actions.exception import ActionFailure
from kairon.shared.actions.models import ActionType, DispatchType, EvaluationType
from kairon.shared.actions.utils import ActionUtility
from kairon.shared.constants import KaironSystemSlots


class ActionHTTP(ActionsBase):

    def __init__(self, bot: Text, name: Text):
        """
        Initialize HTTP action.

        @param bot: bot id
        @param name: action name
        """
        self.bot = bot
        self.name = name
        self.__response = None
        self.__is_success = False

    def retrieve_config(self):
        """
        Fetch HTTP action configuration parameters from the database

        :return: HttpActionConfig containing configuration for the action as a dict.
        """
        try:
            http_config_dict = HttpActionConfig.objects().get(bot=self.bot,
                                                              action_name=self.name, status=True).to_mongo().to_dict()
            logger.debug("http_action_config: " + str(http_config_dict))
            return http_config_dict
        except DoesNotExist as e:
            logger.exception(e)
            raise ActionFailure("No HTTP action found for given action and bot")

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

        bot_response = None
        http_response = None
        exception = None
        body_log = None
        status = "SUCCESS"
        http_url = None
        request_method = None
        header_log = None
        filled_slots = {}
        response_log = {"type": "response"}
        api_call_log = {"type": "api_call"}
        parameter_log = {}
        initial_slots = {"type": "slots"}
        final_slots = {"type": "filled_slots"}
        dispatch_bot_response = True
        dispatch_type = DispatchType.text.value
        events = []
        slot_values = {}
        time_elapsed = 0
        time_taken_slots = 0
        time_taken_pyscript = 0
        time_taken_compose_response = 0
        resp_status_code = None
        try:
            http_action_config = self.retrieve_config()
            dispatch_bot_response = http_action_config['response']['dispatch']
            dispatch_type = http_action_config['response']['dispatch_type']
            data = http_action_config['response'].get('value')
            evaluation_type = http_action_config['response'].get('evaluation_type', EvaluationType.expression.value)
            set_slots = http_action_config['set_slots']
            if set_slots:
                for slot in set_slots:
                    slot_value = tracker.get_slot(slot['name'])
                    slot.update({"slot_value": slot_value})
                initial_slots.update({"data": set_slots}) if set_slots else initial_slots
            response_log.update({"dispatch_bot_response": dispatch_bot_response, "dispatch_type": dispatch_type,
                                 "data": data, "evaluation_type": evaluation_type})
            tracker_data = ActionUtility.build_context(tracker, True)
            tracker_data.update({'bot': self.bot})
            headers, header_log = ActionUtility.prepare_request(tracker_data, http_action_config.get('headers'), self.bot)
            api_call_log.update({"headers": header_log})
            logger.info("headers: " + str(header_log))
            dynamic_params = http_action_config.get('dynamic_params')
            if not ActionUtility.is_empty(dynamic_params):
                body, body_log, slots, time_taken_pyscript = ActionUtility.evaluate_pyscript(dynamic_params, tracker_data)
                filled_slots.update(slots)
                parameter_log.update({"type": "dynamic_params", "data": dynamic_params, "response": body, "slots": slots,
                                      "request_params": body_log, "time_elapsed": time_taken_pyscript})
                body_log = ActionUtility.encrypt_secrets(body, tracker_data)
            else:
                body, body_log = ActionUtility.prepare_request(tracker_data, http_action_config['params_list'], self.bot)
                parameter_log.update({"type": "params_list", "request_body": body, "request_params": body_log})
            logger.info("request_body: " + str(body_log))
            request_method = http_action_config['request_method']
            http_url = ActionUtility.prepare_url(http_url=http_action_config['http_url'], tracker_data=tracker_data)
            http_response, resp_status_code, time_elapsed, response_headers = await ActionUtility.execute_request_async(
                headers=headers, http_url=http_url,
                request_method=request_method, request_body=body,
                content_type=http_action_config['content_type']
            )
            time_elapsed = time_elapsed if time_elapsed else 0
            if response_headers:
                response_headers = dict(response_headers)
            logger.info("http response: " + str(http_response))
            logger.info("response headers: " + str(response_headers))
            api_call_log.update({"method": request_method, "url": http_url, "payload": body, "response": http_response,
                                 "status_code": resp_status_code, "time_elapsed": time_elapsed, "response_headers": response_headers})
            response_context = self.__add_user_context_to_http_response(http_response, resp_status_code, response_headers,  tracker_data)
            bot_response, bot_resp_log, time_taken_compose_response = ActionUtility.compose_response(http_action_config['response'], response_context)
            response_log.update({"response": bot_response, "bot_response_log": bot_resp_log, "time_elapsed": time_taken_compose_response})
            self.__response = bot_response
            self.__is_success = True
            slot_values, slot_eval_log, time_taken_slots = ActionUtility.fill_slots_from_response(http_action_config.get('set_slots', []),
                                                                                response_context)
            final_slots.update({"data": slot_values, "slot_eval_log": slot_eval_log, "time_elapsed": time_taken_slots})
            logger.info("response: " + str(bot_response))
        except Exception as e:
            exception = str(e)
            logger.exception(e)
            status = "FAILURE"
            api_call_log.update({"exception": exception})
            bot_response = bot_response if bot_response else "I have failed to process your request"
            response_log.update({"exception": bot_response})
        finally:
            if dispatch_bot_response:
                bot_response, message = ActionUtility.handle_utter_bot_response(dispatcher, dispatch_type, bot_response)
                if message:
                    response_log.update({"message": message})
            fail_reason = ActionUtility.validate_http_response_status(http_response, resp_status_code)
            events_to_extend = [response_log, api_call_log, parameter_log, final_slots]
            if 'data' in initial_slots.keys():
                events_to_extend.insert(0, initial_slots)
            events.extend(events_to_extend)
            total_time_elapsed = time_elapsed + time_taken_slots + time_taken_pyscript + time_taken_compose_response
            trigger_info_data = action_call.get('trigger_info') or {}
            trigger_info_obj = TriggerInfo(**trigger_info_data)
            ActionServerLogs(
                type=ActionType.http_action.value,
                intent=tracker.get_intent_of_latest_message(skip_fallback_intent=False),
                action=self.name,
                sender=tracker.sender_id,
                events=events,
                url=http_url,
                request_method=request_method,
                bot_response=str(bot_response) if bot_response else None,
                fail_reason=fail_reason,
                exception=exception,
                bot=self.bot,
                status=status,
                user_msg=tracker.latest_message.get('text'),
                time_elapsed=total_time_elapsed,
                http_status_code=resp_status_code,
                trigger_info=trigger_info_obj
            ).save()
            filled_slots.update({KaironSystemSlots.kairon_action_response.value: bot_response, "http_status_code": resp_status_code})
            filled_slots.update(slot_values)
        return filled_slots

    @staticmethod
    def __add_user_context_to_http_response(http_response, response_status_code, response_headers, tracker_data):
        response_context = {"data": http_response, 'context': tracker_data, 'http_status_code': response_status_code,
                            "response_headers": response_headers}
        return response_context

    @property
    def is_success(self):
        return self.__is_success

    @property
    def response(self):
        return self.__response
