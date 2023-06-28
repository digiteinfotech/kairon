import json
from json import JSONDecodeError
from typing import Text, Dict, Any

from loguru import logger
from mongoengine import DoesNotExist
from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher

from kairon.actions.definitions.base import ActionsBase
from kairon.shared.actions.data_objects import ActionServerLogs, HttpActionConfig
from kairon.shared.actions.exception import ActionFailure
from kairon.shared.actions.models import ActionType, DispatchType
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
        http_response = None
        exception = None
        body_log = None
        status = "SUCCESS"
        http_url = None
        request_method = None
        header_log = None
        filled_slots = {}
        dispatch_bot_response = True
        dispatch_type = DispatchType.text.value
        msg_logger = []
        try:
            http_action_config = self.retrieve_config()
            dispatch_bot_response = http_action_config['response']['dispatch']
            dispatch_type = http_action_config['response']['dispatch_type']
            tracker_data = ActionUtility.build_context(tracker, True)
            tracker_data.update({'bot': self.bot})
            headers, header_log = ActionUtility.prepare_request(tracker_data, http_action_config.get('headers'), self.bot)
            logger.info("headers: " + str(header_log))
            dynamic_params = http_action_config.get('dynamic_params')
            if not ActionUtility.is_empty(dynamic_params):
                body, body_log = ActionUtility.evaluate_script(dynamic_params, tracker_data)
                msg_logger.extend(body_log)
                body_log = ActionUtility.encrypt_secrets(body, tracker_data)
            else:
                body, body_log = ActionUtility.prepare_request(tracker_data, http_action_config['params_list'], self.bot)
            logger.info("request_body: " + str(body_log))
            request_method = http_action_config['request_method']
            http_url = ActionUtility.prepare_url(http_url=http_action_config['http_url'], tracker_data=tracker_data)
            http_response = ActionUtility.execute_http_request(headers=headers, http_url=http_url,
                                                               request_method=request_method, request_body=body,
                                                               content_type=http_action_config['content_type'])
            logger.info("http response: " + str(http_response))
            response_context = self.__add_user_context_to_http_response(http_response, tracker_data)
            bot_response, bot_resp_log = ActionUtility.compose_response(http_action_config['response'],
                                                                        response_context)
            msg_logger.extend(bot_resp_log)
            self.__response = bot_response
            self.__is_success = True
            slot_values, slot_eval_log = ActionUtility.fill_slots_from_response(http_action_config.get('set_slots', []),
                                                                                response_context)
            msg_logger.extend(slot_eval_log)
            filled_slots.update(slot_values)
            logger.info("response: " + str(bot_response))
        except Exception as e:
            exception = str(e)
            logger.exception(e)
            status = "FAILURE"
            bot_response = "I have failed to process your request"
        finally:
            if dispatch_bot_response:
                if dispatch_type == DispatchType.json.value:
                    try:
                        if isinstance(bot_response, str):
                            bot_response = json.loads(bot_response)
                        dispatcher.utter_message(json_message=bot_response)
                    except JSONDecodeError as e:
                        msg_logger.append(f'Failed to convert http response to json: {str(e)}')
                        logger.exception(e)
                        dispatcher.utter_message(bot_response)
                else:
                    dispatcher.utter_message(bot_response)
            ActionServerLogs(
                type=ActionType.http_action.value,
                intent=tracker.get_intent_of_latest_message(skip_fallback_intent=False),
                action=self.name,
                sender=tracker.sender_id,
                headers=header_log,
                url=http_url,
                request_method=request_method,
                request_params=body_log,
                api_response=str(http_response) if http_response else None,
                bot_response=str(bot_response) if bot_response else None,
                messages=msg_logger,
                exception=exception,
                bot=self.bot,
                status=status,
                user_msg=tracker.latest_message.get('text')
            ).save()
        filled_slots.update({KaironSystemSlots.kairon_action_response.value: bot_response})
        return filled_slots

    @staticmethod
    def __add_user_context_to_http_response(http_response, tracker_data):
        response_context = {"data": http_response, 'context': tracker_data}
        return response_context

    @property
    def is_success(self):
        return self.__is_success

    @property
    def response(self):
        return self.__response
