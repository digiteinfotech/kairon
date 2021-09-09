import json
import logging
from typing import Any, List
from urllib.parse import urlencode, quote_plus, unquote_plus

import requests
from loguru import logger
from mongoengine import DoesNotExist
from pymongo.common import _CaseInsensitiveDictionary
from pymongo.errors import InvalidURI
from pymongo.uri_parser import (
    SRV_SCHEME_LEN,
    SCHEME,
    SCHEME_LEN,
    SRV_SCHEME,
    parse_userinfo,
)
from pymongo.uri_parser import _BAD_DB_CHARS, split_options
from rasa_sdk import Tracker

from .data_objects import HttpActionConfig, HttpActionRequestBody, Actions, SlotSetAction
from .exception import ActionFailure
from .models import ParameterType, ActionType


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
            header = {'Authorization': auth_token}
        try:
            if request_method.lower() == 'get':
                if request_body:
                    http_url = http_url + "?" + urlencode(request_body, quote_via=quote_plus)
                response = requests.get(http_url, headers=header)
            elif request_method.lower() in ['post', 'put', 'delete']:
                response = requests.request(request_method.upper(), http_url, json=request_body, headers=header)
            else:
                raise ActionFailure("Invalid request method!")
            logger.debug("raw response: " + str(response.text))
            logger.debug("status " + str(response.status_code))

            if response.status_code not in [200, 202, 201, 204]:
                raise ActionFailure("Got non-200 status code")
        except Exception as e:
            logger.error(str(e))
            raise ActionFailure("Failed to execute the url: " + str(e))

        try:
            http_response_as_json = response.json()
        except ValueError as e:
            logging.error(str(e))
            http_response_as_json = response.text

        return http_response_as_json, http_url

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
    def extract_db_config(uri: str):
        """
        extract username, password and host with port from mongo uri

        :param uri: mongo uri
        :return: username, password, scheme, hosts
        """
        user = None
        passwd = None
        dbase = None
        collection = None
        options = _CaseInsensitiveDictionary()
        hosts = None
        is_mock = False
        if uri.startswith("mongomock://"):
            uri = uri.replace("mongomock://", "mongodb://", 1)
            is_mock = True
        if uri.startswith(SCHEME):
            scheme_free = uri[SCHEME_LEN:]
            scheme = uri[:SCHEME_LEN]
        elif uri.startswith(SRV_SCHEME):
            scheme_free = uri[SRV_SCHEME_LEN:]
            scheme = uri[:SRV_SCHEME_LEN]
        else:
            raise InvalidURI(
                "Invalid URI scheme: URI must "
                "begin with '%s' or '%s'" % (SCHEME, SRV_SCHEME)
            )

        if not scheme_free:
            raise InvalidURI("Must provide at least one hostname or IP.")

        host_part, _, path_part = scheme_free.partition("/")
        if not host_part:
            host_part = path_part
            path_part = ""

        if not path_part and '?' in host_part:
            raise InvalidURI("A '/' is required between "
                             "the host list and any options.")

        if path_part:
            dbase, _, opts = path_part.partition('?')
            if dbase:
                dbase = unquote_plus(dbase)
                if '.' in dbase:
                    dbase, collection = dbase.split('.', 1)
                if _BAD_DB_CHARS.search(dbase):
                    raise InvalidURI('Bad database name "%s"' % dbase)
            else:
                dbase = None

            if opts:
                options.update(split_options(opts, True, False, True))

        if "@" in host_part:
            userinfo, _, hosts = host_part.rpartition("@")
            user, passwd = parse_userinfo(userinfo)
            hosts = scheme + hosts
        else:
            hosts = scheme + host_part
        settings = {
            "username": user,
            "password": passwd,
            "host": hosts,
            "db": dbase,
            "options": options,
            "collection": collection
        }

        if is_mock:
            settings['is_mock'] = is_mock
        return settings

    @staticmethod
    def mongoengine_connection(environment=None):
        config = ActionUtility.extract_db_config(environment['database']["url"])
        options = config.pop("options")
        config.pop("collection")
        if "replicaset" in options:
            config["replicaSet"] = options["replicaset"]
        if "authsource" in options:
            config["authentication_source"] = options["authsource"]
        if "authmechanism" in options:
            config["authentication_mechanism"] = options["authmechanism"]
        return config

    @staticmethod
    def get_action_config(bot: str, name: str):
        if ActionUtility.is_empty(bot) or ActionUtility.is_empty(name):
            raise ActionFailure("Bot and action name are required for fetching configuration")

        try:
            action = Actions.objects(bot=bot, name=name, status=True).get().to_mongo().to_dict()
            logger.debug("http_action_config: " + str(action))
            if action.get('type') == ActionType.http_action.value:
                config = ActionUtility.get_http_action_config(bot, name)
            elif action.get('type') == ActionType.slot_set_action.value:
                config = ActionUtility.get_slot_set_config(bot, name)
            else:
                raise ActionFailure('Only http & slot set actions are compatible with action server')
        except DoesNotExist as e:
            logger.exception(e)
            raise ActionFailure("No action found for bot")

        return config, action.get('type')

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
            raise ActionFailure("Bot name and action name are required")

        try:
            http_config_dict = HttpActionConfig.objects().get(bot=bot,
                                                              action_name=action_name, status=True).to_mongo().to_dict()
            logger.debug("http_action_config: " + str(http_config_dict))
        except DoesNotExist as e:
            logger.exception(e)
            raise ActionFailure("No HTTP action found for bot")

        return http_config_dict

    @staticmethod
    def get_slot_set_config(bot: str, name: str):
        try:
            action = SlotSetAction.objects().get(bot=bot, name=name, status=True).to_mongo().to_dict()
            logger.debug("slot_set_action_config: " + str(action))
        except DoesNotExist as e:
            logger.exception(e)
            raise ActionFailure("No slot set action found for bot")

        return action

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
            raise ActionFailure("Unable to retrieve value for key from HTTP response: " + str(e))
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
                raise ActionFailure("Could not find value for keys in response")

        value_mapping = ActionUtility.retrieve_value_from_response(keys_without_placeholders, http_response)
        for key in value_mapping:
            value_for_placeholder = value_mapping[key]
            if isinstance(value_for_placeholder, dict):
                parsed_output = parsed_output.replace(key, json.dumps(value_for_placeholder))
            else:
                parsed_output = parsed_output.replace(key, str(value_mapping[key]))

        return parsed_output
