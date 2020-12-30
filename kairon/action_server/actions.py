import json
import logging
import os
from pathlib import Path
from typing import Dict, Any, Text, List

import requests
from loguru import logger
from rasa_sdk import Action, Tracker
from rasa_sdk.events import SlotSet
from rasa_sdk.executor import CollectingDispatcher
from mongoengine import connect, disconnect, DoesNotExist
from smart_config import ConfigLoader

from .data_objects import HttpActionRequestBody, HttpActionConfig
from .action_models import ParameterType
from .exception import HttpActionFailure


class ActionUtility:
    """Utility class to assist executing actions"""

    @staticmethod
    def execute_http_request(http_url: str, request_method: str, request_body=None, auth_token=None):
        """
        Executes http urls provided.

        :param http_url: HTTP url to be executed
        :param request_method: One of GET, PUT, POST, DELETE
        :param request_body: Request body to be sent with the request
        :param auth_token: auth token to be sent with request in case of token based authentication
        :return: JSON/string response
        """
        header = {"User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"}
        response = ""

        if request_body is None:
            request_body = {}

        if not ActionUtility.is_empty(auth_token):
            if request_method.upper() == 'GET':
                request_body['Authorization'] = auth_token
            else:
                header = {'Authorization': auth_token}
        try:
            if request_method.upper() == 'GET':
                response = requests.get(http_url, headers=request_body)
            elif request_method.upper() == 'POST':
                response = requests.post(http_url, json=request_body, headers=header)
            elif request_method.upper() == 'PUT':
                response = requests.put(http_url, json=request_body, headers=header)
            elif request_method.upper() == 'DELETE':
                response = requests.delete(http_url, json=request_body, headers=header)
            logger.debug("raw response: "+ str(response.text))

            if response.status_code != 200:
                raise HttpActionFailure("Got non-200 status code")
        except Exception as e:
            logger.error(str(e))
            raise HttpActionFailure("Failed to execute the url: " + str(e))

        try:
            http_response_as_json = response.json()
        except ValueError as e:
            logging.error(str(e))
            http_response_as_json = response.text

        return http_response_as_json

    @staticmethod
    def prepare_request(tracker: Tracker, http_action_config_params: List[HttpActionRequestBody]):
        """
        Prepares request body:
        1. Fetches value of parameter from slot(Tracker) if parameter_type is slot and adds to request body
        2. Adds value of parameter directly if parameter_type is value
        :param tracker: Tracker for the Http Action
        :param http_action_config_params: User defined request body parameters <key, value, parameter_type>
        :return: Request body for the HTTP request
        """
        request_body = {}
        if not http_action_config_params:
            return request_body

        for param in http_action_config_params:
            if param['parameter_type'] == ParameterType.slot:
                value = tracker.get_slot(param['key'])
                if value is None:
                    raise HttpActionFailure("Coudn't find value for key " + param['key'] + " from slot")
                request_body[param['key']] = value
            else:
                request_body[param['key']] = param['value']

        return request_body

    @staticmethod
    def is_empty(value: str):
        """
        checks for null or empty string

        :param value: string value
        :return: boolean
        """
        if not value:
            return True
        return bool(not value.strip())

    @staticmethod
    def get_db_url():
        """
        Fetches MongoDB URL defined in system.yaml file
        :return: MongoDB connection URL
        """
        system_yml_parent_dir = str(Path(os.path.realpath(__file__)).parent)
        environment = ConfigLoader(os.getenv("system_file", system_yml_parent_dir + "/system.yaml")).get_config()
        return environment['database']["url"]

    @staticmethod
    def get_http_action_config(db_url: str, bot: str, action_name: str):
        """
        Fetch HTTP action configuration parameters from the MongoDB database
        :param db_url: MongoDB connection string
        :param bot: BotID
        :param action_name: Action name
        :return: HttpActionConfig object containing configuration for the action
        """
        if ActionUtility.is_empty(db_url) or ActionUtility.is_empty(
                bot) or ActionUtility.is_empty(
            action_name):
            raise HttpActionFailure("Database url, bot name and action name are required")

        try:
            connect(host=db_url)
            http_config_dict = HttpActionConfig.objects().get(bot=bot,
                                                              action_name=action_name).to_mongo().to_dict()
            logger.debug("http_action_config: " + str(http_config_dict))
            if dict is None:
                raise DoesNotExist
        except DoesNotExist:
            raise HttpActionFailure("No HTTP action found for bot " + bot + " and action " + action_name)
        except Exception as ex:
            raise HttpActionFailure(ex)
        finally:
            disconnect()

        return http_config_dict

    @staticmethod
    def retrieve_value_from_response(grouped_keys: List[str], http_response: dict):
        """
        Retrieves values for user defined placeholders
        :param grouped_keys: List of user defined keys
        :param http_response: Response received from executing Http URL
        :return: A dictionary of user defined placeholder and value from json
        """
        value_mapping = {}
        try:
            for punctuation_separated_key in grouped_keys:
                keys = punctuation_separated_key.split(".")
                json_search_region = http_response
                for key in keys:
                    if isinstance(json_search_region, dict):
                        json_search_region = json_search_region[key]
                    else:
                        json_search_region = json_search_region[int(key)]

                value_mapping['${' + punctuation_separated_key + '}'] = json_search_region
        except Exception as e:
            raise HttpActionFailure("Unable to retrieve value for key from HTTP response: " + str(e))
        return value_mapping

    @staticmethod
    def attach_response(template, http_response):
        """
        Substitutes ${RESPONSE} placeholder with the response received from executing Http URL.
        :param template: A string with placeholders. It is basically the user expected output.
        :param http_response: Response received after executing Http URL.
        :return: Http response added to the user defined output string.
        """
        parsed_output = template
        if template.__contains__('${RESPONSE}'):
            parsed_output = template.replace('${RESPONSE}', str(http_response))
        return parsed_output

    @staticmethod
    def prepare_response(response_template: str, http_response: Any):
        """
        Prepares the user defined response.
        :param response_template: A string that may contain placeholders. It is basically the user expected output.
        :param http_response: Response received after executing Http URL.
        :return: Returns a response curated from user defined template and Http response.
        """
        value_mapping = {}
        parsed_output = ActionUtility.attach_response(response_template, http_response)
        keys_with_placeholders = [term for term in parsed_output.split(" ") if term.startswith("${") and term.endswith("}")]
        #  deepcode ignore C1801: Length check required in case there are no placeholders
        if keys_with_placeholders is None or len(keys_with_placeholders) == 0:
            if ActionUtility.is_empty(response_template):
                return http_response
            return parsed_output
        keys_without_placeholders = [plcehlder.lstrip("${").rstrip("}") for plcehlder in keys_with_placeholders]

        try:
            if not isinstance(http_response, dict):
                http_response_as_json = json.loads(http_response)
            else:
                http_response_as_json = http_response
        except ValueError as e:
            logging.error(e)
            if keys_with_placeholders is not None:
                raise HttpActionFailure("Could not find value for keys in response")
            return parsed_output
        value_mapping = ActionUtility.retrieve_value_from_response(keys_without_placeholders, http_response_as_json)
        for key in value_mapping:
            value_for_placeholder = value_mapping[key]
            if isinstance(value_for_placeholder, dict):
                parsed_output = parsed_output.replace(key, json.dumps(value_for_placeholder))
            else:
                parsed_output = parsed_output.replace(key, str(value_mapping[key]))

        return parsed_output


class HttpAction(Action):
    """
    Executes any HTTP action configured by user
    """

    def name(self) -> Text:
        """
        Name of HTTP action.

        :return: Returns literal "http_action".
        """
        return "kairon_http_action"

    def run(self,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        """
        Executes GET, PUT, POST, DELETE Http requests and curates and returns the user defined output.

        :param dispatcher: Rasa provided Dispatcher to send messages back to the user.
        :param tracker: Rasa provided Tracker to maintain the state of a dialogue between the assistant and the user in the form of conversation sessions.
        :param domain: Rasa provided Domain to specify the intents, entities, slots, and actions your bot should know about.
        :return: Curated Http response for the configured Http URL.
        """
        response = {}
        try:
            logger.debug(tracker.current_slot_values())
            intent = tracker.get_intent_of_latest_message()
            logger.debug("intent: " + str(intent))
            logger.debug(tracker.latest_message)
            bot_id = tracker.get_slot("bot")
            action = tracker.get_slot("http_action_config" + "_" + intent)
            if ActionUtility.is_empty(bot_id) or ActionUtility.is_empty(action):
                raise HttpActionFailure("Bot id and HTTP action configuration name not found in slot")

            db_url = ActionUtility.get_db_url()
            http_action_config: HttpActionConfig = ActionUtility.get_http_action_config(db_url=db_url, bot=bot_id,
                                                                                        action_name=action)
            request_body = ActionUtility.prepare_request(tracker, http_action_config['params_list'])
            logger.debug("request_body: " + str(request_body))
            http_response = ActionUtility.execute_http_request(auth_token=http_action_config['auth_token'],
                                                               http_url=http_action_config['http_url'],
                                                               request_method=http_action_config['request_method'],
                                                               request_body=request_body)
            logger.debug("http response: " + str(http_response))

            response = ActionUtility.prepare_response(http_action_config['response'], http_response)
            logger.debug("response: " + str(response))
        #  deepcode ignore W0703: General exceptions are captured to raise application specific exceptions
        except Exception as e:
            logger.error(str(e))
            response = "I have failed to process your request"

        dispatcher.utter_message(response)
        return [SlotSet(response)]
