import json
import logging
import os
from pathlib import Path
from typing import Any, List

import requests
from loguru import logger
from mongoengine import DoesNotExist, connect
from rasa_sdk import Tracker
from smart_config import ConfigLoader

from .models import ParameterType
from .data_objects import HttpActionConfig, HttpActionRequestBody
from .exception import HttpActionFailure
from rasa_sdk.interfaces import ActionNotFoundException


class ActionUtility:

    """
    Utility class to assist executing actions
    """

    @staticmethod
    def execute_http_request(http_url: str, request_method: str, request_body=None, auth_token=None):
        """Executes http urls provided.

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
            logger.debug("raw response: " + str(response.text))

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
            if param['parameter_type'] == ParameterType.sender_id:
                value = tracker.sender_id
            elif param['parameter_type'] == ParameterType.slot:
                value = tracker.get_slot(param['value'])
            else:
                value = param['value']
            request_body[param['key']] = value
            logger.debug("value for key " + param['key'] + ": " + str(value))

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
    def connect_db():
        """
        Creates connection to database.
        :return: MongoDB connection URL
        """
        system_yml_parent_dir = str(Path(os.path.realpath(__file__)).parent)
        environment = ConfigLoader(os.getenv("system_file", system_yml_parent_dir + "/system.yaml")).get_config()
        connect(host=environment['database']["url"])

    @staticmethod
    def get_http_action_config(bot: str, action_name: str):
        """
        Fetch HTTP action configuration parameters from the MongoDB database
        :param db_url: MongoDB connection string
        :param bot: BotID
        :param action_name: Action name
        :return: HttpActionConfig object containing configuration for the action
        """
        if ActionUtility.is_empty(bot) or ActionUtility.is_empty(action_name):
            raise HttpActionFailure("Bot name and action name are required")

        try:
            http_config_dict = HttpActionConfig.objects().get(bot=bot,
                                                              action_name=action_name, status=True).to_mongo().to_dict()
            logger.debug("http_action_config: " + str(http_config_dict))
        except DoesNotExist as e:
            logger.exception(e)
            raise HttpActionFailure("No HTTP action found for bot")

        return http_config_dict

    @staticmethod
    def retrieve_value_from_response(grouped_keys: List[str], http_response: Any):
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

        if type(http_response) not in [dict, list]:
            if keys_with_placeholders is not None:
                raise HttpActionFailure("Could not find value for keys in response")

        value_mapping = ActionUtility.retrieve_value_from_response(keys_without_placeholders, http_response)
        for key in value_mapping:
            value_for_placeholder = value_mapping[key]
            if isinstance(value_for_placeholder, dict):
                parsed_output = parsed_output.replace(key, json.dumps(value_for_placeholder))
            else:
                parsed_output = parsed_output.replace(key, str(value_mapping[key]))

        return parsed_output
