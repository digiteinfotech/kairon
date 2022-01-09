import json
import logging
import re
from datetime import datetime
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

from .data_objects import HttpActionConfig, HttpActionRequestBody, Actions, SlotSetAction, FormValidationAction, EmailActionConfig
from .exception import ActionFailure
from .models import ActionType, SlotValidationOperators, LogicalOperators, ActionParameterType
from ..data.constant import SLOT_TYPE
from ..data.data_objects import Slots
from json2html import *


class ActionUtility:

    """
    Utility class to assist executing actions
    """

    @staticmethod
    def execute_http_request(http_url: str, request_method: str, request_body=None, headers=None):
        """Executes http urls provided.

        :param http_url: HTTP url to be executed
        :param request_method: One of GET, PUT, POST, DELETE
        :param request_body: Request body to be sent with the request
        :param headers: header for the HTTP request
        :return: JSON/string response
        """
        if not headers:
            headers = {}
        headers.update({"User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"})

        if request_body is None:
            request_body = {}

        try:
            if request_method.lower() == 'get':
                response = requests.get(http_url, headers=headers)
            elif request_method.lower() in ['post', 'put', 'delete']:
                response = requests.request(request_method.upper(), http_url, json=request_body, headers=headers)
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

        return http_response_as_json

    @staticmethod
    def prepare_request(tracker: Tracker, http_action_config_params: List[HttpActionRequestBody]):
        """
        Prepares request body:
        1. Fetches value of parameter from slot(Tracker) if parameter_type is slot and adds to request body
        2. Adds value of parameter directly if parameter_type is value
        3. Adds value of parameter as the sender_id.
        4. Adds value of parameter as user_message.
        :param tracker: Tracker for the Http Action
        :param http_action_config_params: User defined request body parameters <key, value, parameter_type>
        :return: Request body for the HTTP request
        """
        request_body = {}

        for param in http_action_config_params or []:
            if param['parameter_type'] == ActionParameterType.sender_id.value:
                value = tracker.sender_id
            elif param['parameter_type'] == ActionParameterType.slot.value:
                value = tracker.get_slot(param['value'])
            elif param['parameter_type'] == ActionParameterType.user_message.value:
                value = tracker.latest_message.get('text')
            elif param['parameter_type'] == ActionParameterType.intent.value:
                value = tracker.get_intent_of_latest_message()
            elif param['parameter_type'] == ActionParameterType.chat_log.value:
                iat, msg_trail = ActionUtility.prepare_message_trail(tracker.events)
                value = {
                    'sender_id': tracker.sender_id,
                    'session_started': iat,
                    'conversation': msg_trail
                }
            else:
                value = param['value']
            request_body[param['key']] = value
            logger.debug("value for key " + param['key'] + ": " + str(value))

        return request_body

    @staticmethod
    def prepare_message_trail(tracker_events):
        message_trail = []
        initiated_at = None
        for event in tracker_events:
            if event.get('event') == 'session_started' and event.get('timestamp'):
                initiated_at = datetime.utcfromtimestamp(event['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
            elif event.get('event') == 'user' or event.get('event') == 'bot':
                message_trail.append({event['event']: event.get('text')})

        return initiated_at, message_trail

    @staticmethod
    def prepare_url(request_method: str, http_url: str, request_body=None):
        if request_method.lower() == 'get' and request_body:
            http_url = http_url + "?" + urlencode(request_body, quote_via=quote_plus)
        return http_url

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
            elif action.get('type') == ActionType.form_validation_action.value:
                config = ActionUtility.get_form_validation_config(bot, name)
            elif action.get('type') == ActionType.email_action.value:
                config = ActionUtility.get_email_action_config(bot, name)
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
    def get_form_validation_config(bot: str, name: str):
        action = FormValidationAction.objects(bot=bot, name=name, status=True)
        logger.debug("form_validation_config: " + str(action.to_json()))
        return action

    @staticmethod
    def get_email_action_config(bot: str, name: str):
        action = EmailActionConfig.objects(bot=bot, action_name=name, status=True).get().to_mongo().to_dict()
        logger.debug("email_action_config: " + str(action))
        return action

    @staticmethod
    def get_slot_type(bot: str, slot: str):
        try:
            slot_info = Slots.objects(name=slot, bot=bot, status=True).get()
            return slot_info.type
        except DoesNotExist as e:
            logger.exception(e)
            raise ActionFailure(f'Slot not found in database: {slot}')

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
        keys_with_placeholders = re.findall(r'\${(.+?)}', parsed_output)
        if not keys_with_placeholders:
            if ActionUtility.is_empty(response_template):
                return http_response
            return parsed_output

        if type(http_response) not in [dict, list]:
            if keys_with_placeholders is not None:
                raise ActionFailure("Could not find value for keys in response")

        value_mapping = ActionUtility.retrieve_value_from_response(keys_with_placeholders, http_response)
        for key in value_mapping:
            value_for_placeholder = value_mapping[key]
            if isinstance(value_for_placeholder, dict):
                parsed_output = parsed_output.replace(key, json.dumps(value_for_placeholder))
            else:
                parsed_output = parsed_output.replace(key, str(value_mapping[key]))

        return parsed_output

    @staticmethod
    def prepare_email_body(tracker_events):
        iat, msgtrail = ActionUtility.prepare_message_trail(tracker_events)
        return json2html.convert(msgtrail)

class ExpressionEvaluator:

    @staticmethod
    def is_valid_slot_value(slot_type: str, slot_value: Any, semantic_expression: dict):
        expression_evaluated_as_str = []
        final_expr = None
        is_slot_data_valid = True

        if slot_value is None:
            is_slot_data_valid = False

        if semantic_expression:
            result = []
            for parent_operator, expressions in semantic_expression.items():
                for sub_expression in expressions:
                    if sub_expression.get(LogicalOperators.and_operator.value):
                        all_sub_expressions = list(ExpressionEvaluator.__evaluate_expression_list(
                            sub_expression[LogicalOperators.and_operator.value], slot_type, slot_value
                        ))
                        is_valid = all(ex[1] for ex in all_sub_expressions)
                        expr_str = ExpressionEvaluator.expr_as_str(all_sub_expressions, LogicalOperators.and_operator.value)
                        expression_evaluated_as_str.append(expr_str)
                    elif sub_expression.get(LogicalOperators.or_operator.value):
                        all_sub_expressions = list(ExpressionEvaluator.__evaluate_expression_list(
                            sub_expression[LogicalOperators.or_operator.value], slot_type, slot_value
                        ))
                        is_valid = any(ex[1] for ex in all_sub_expressions)
                        expr_str = ExpressionEvaluator.expr_as_str(all_sub_expressions, LogicalOperators.or_operator.value)
                        expression_evaluated_as_str.append(expr_str)
                    else:
                        expr_str, is_valid = next(ExpressionEvaluator.__evaluate_expression_list([sub_expression], slot_type, slot_value))
                        expression_evaluated_as_str.append(expr_str)
                    result.append(is_valid)
                if parent_operator == LogicalOperators.and_operator.value:
                    is_slot_data_valid = all(result)
                else:
                    is_slot_data_valid = any(result)
                final_expr = ExpressionEvaluator.expr_as_str(expression_evaluated_as_str, parent_operator)
                break
        return final_expr, is_slot_data_valid

    @staticmethod
    def __evaluate_expression_list(expressions: list, slot_type: str, slot_value: Any):
        for expression in expressions:
            operator = expression.get('operator')
            operand = expression.get('value')
            yield ExpressionEvaluator.__evaluate_expression(slot_type, slot_value, operator, operand)

    @staticmethod
    def __evaluate_expression(slot_type: str, slot_value: Any, operator: str, operand: Any):
        if slot_type in {SLOT_TYPE.TEXT.value, SLOT_TYPE.CATEGORICAL.value, SLOT_TYPE.ANY.value}:
            expression, is_valid = ExpressionEvaluator.__evaluate_text_type(slot_value, operator, operand)
        elif slot_type == SLOT_TYPE.FLOAT.value:
            expression, is_valid = ExpressionEvaluator.__evaluate_float_type(slot_value, operator, operand)
        elif slot_type == SLOT_TYPE.BOOLEAN.value:
            expression, is_valid = ExpressionEvaluator.__evaluate_boolean_type(slot_value, operator)
        elif slot_type == SLOT_TYPE.LIST.value:
            expression, is_valid = ExpressionEvaluator.__evaluate_list_type(slot_value, operator, operand)
        else:
            raise ActionFailure(f'Unsupported slot type: {slot_type}')
        return expression, is_valid

    @staticmethod
    def __evaluate_float_type(slot_value: Any, operator: str, operand: Any):
        is_valid = False
        try:
            slot_value = float(slot_value)
        except ValueError:
            return is_valid
        expression = f'({slot_value} {operator} {operand})'
        if operator == SlotValidationOperators.equal_to.value:
            is_valid = slot_value == operand
        elif operator == SlotValidationOperators.is_greater_than.value:
            is_valid = slot_value > operand
        elif operator == SlotValidationOperators.is_less_than.value:
            is_valid = slot_value < operand
        elif operator == SlotValidationOperators.is_in.value:
            is_valid = slot_value in operand
        elif operator == SlotValidationOperators.is_not_in.value:
            is_valid = slot_value not in operand
        else:
            raise ActionFailure(f'Cannot evaluate invalid operator "{operator}" for slot type "float"')
        return expression, is_valid

    @staticmethod
    def __evaluate_text_type(slot_value: Any, operator: str, operand: Any):
        if operator == SlotValidationOperators.equal_to.value:
            expression = f'("{slot_value}" {operator} "{operand}")'
            is_valid = slot_value == operand
        elif operator == SlotValidationOperators.not_equal_to.value:
            expression = f'("{slot_value}" {operator} "{operand}")'
            is_valid = slot_value != operand
        elif operator == SlotValidationOperators.case_insensitive_equals.value:
            slot_value = slot_value.lower() if slot_value else slot_value
            expression = f'("{slot_value}" == "{operand.lower()}")'
            is_valid = slot_value == operand.lower()
        elif operator == SlotValidationOperators.contains.value:
            expression = f'("{operand}" in "{slot_value}")'
            is_valid = operand in slot_value if slot_value else False
        elif operator == SlotValidationOperators.starts_with.value:
            expression = f'("{slot_value}".startswith("{operand}"))'
            is_valid = slot_value.startswith(operand) if slot_value else False
        elif operator == SlotValidationOperators.ends_with.value:
            expression = f'("{slot_value}".endswith("{operand}"))'
            is_valid = slot_value.endswith(operand) if slot_value else False
        elif operator == SlotValidationOperators.has_length.value:
            expression = f'(len("{slot_value}") == {operand})'
            is_valid = len(slot_value) == operand if slot_value else False
        elif operator == SlotValidationOperators.has_length_greater_than.value:
            expression = f'(len("{slot_value}") > {operand})'
            is_valid = len(slot_value) > operand if slot_value else False
        elif operator == SlotValidationOperators.has_length_less_than.value:
            expression = f'(len("{slot_value}") < {operand})'
            is_valid = len(slot_value) < operand if slot_value else False
        elif operator == SlotValidationOperators.has_no_whitespace.value:
            expression = f'(" " not in "{slot_value}")'
            is_valid = " " not in slot_value if slot_value else False
        elif operator == SlotValidationOperators.is_in.value:
            expression = f'("{slot_value}" in {operand})'
            is_valid = slot_value in operand
        elif operator == SlotValidationOperators.is_not_in.value:
            expression = f'("{slot_value}" not in {operand})'
            is_valid = slot_value not in operand
        elif operator == SlotValidationOperators.is_not_null_or_empty.value:
            expression = f'(is_empty({slot_value}))'
            is_valid = not ActionUtility.is_empty(slot_value)
        elif operator == SlotValidationOperators.is_null_or_empty.value:
            expression = f'(is_empty({slot_value}))'
            is_valid = ActionUtility.is_empty(slot_value)
        elif operator == SlotValidationOperators.is_an_email_address.value:
            expression = f'(is_an_email_address({slot_value}))'
            regex = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
            is_valid = True if slot_value and re.fullmatch(regex, slot_value) else False
        elif operator == SlotValidationOperators.matches_regex.value:
            expression = f'({slot_value}.matches_regex({operand}))'
            is_valid = True if slot_value and re.fullmatch(operand, slot_value) else False
        else:
            raise ActionFailure(f'Cannot evaluate invalid operator "{operator}" for current slot type')

        return expression, is_valid

    @staticmethod
    def __evaluate_boolean_type(slot_value: Any, operator: str):
        if operator == SlotValidationOperators.is_true.value:
            expression = f'({slot_value} is true)'
            is_valid = slot_value and str(slot_value) == "true"
        elif operator == SlotValidationOperators.is_false.value:
            expression = f'({slot_value} is False)'
            is_valid = slot_value and str(slot_value) == "false"
        elif operator == SlotValidationOperators.is_null_or_empty.value:
            expression = f'(is_empty({slot_value}))'
            is_valid = not slot_value
        elif operator == SlotValidationOperators.is_not_null_or_empty.value:
            expression = f'(is_not_empty({slot_value}))'
            is_valid = slot_value and bool(slot_value)
        else:
            raise ActionFailure(f'Cannot evaluate invalid operator: "{operator}" for slot type "boolean"')

        return expression, is_valid

    @staticmethod
    def __evaluate_list_type(slot_value: Any, operator: str, operand: Any):
        if operator == SlotValidationOperators.equal_to.value:
            expression = f'({slot_value} == {operand})'
            is_valid = slot_value == operand if slot_value else False
        elif operator == SlotValidationOperators.contains.value:
            expression = f'({operand} in {slot_value})'
            is_valid = operand in slot_value if slot_value else False
        elif operator == SlotValidationOperators.has_length.value:
            expression = f'(len({slot_value}) == {operand})'
            is_valid = len(slot_value) == operand if slot_value else False
        elif operator == SlotValidationOperators.has_length_greater_than.value:
            expression = f'(len({slot_value}) > {operand})'
            is_valid = len(slot_value) > operand if slot_value else False
        elif operator == SlotValidationOperators.has_length_less_than.value:
            expression = f'(len({slot_value}) < {operand})'
            is_valid = len(slot_value) < operand if slot_value else False
        elif operator == SlotValidationOperators.is_in.value:
            expression = f'({slot_value} in {operand})'
            is_valid = False if slot_value and set(slot_value).difference(set(operand)) else True
        elif operator == SlotValidationOperators.is_not_in.value:
            expression = f'({slot_value} not in {operand})'
            is_valid = True if slot_value and set(slot_value).difference(set(operand)) else False
        elif operator == SlotValidationOperators.is_null_or_empty.value:
            expression = f'(is_null_or_empty({operand}))'
            is_valid = False if (slot_value and list(slot_value)) else True
        elif operator == SlotValidationOperators.is_not_null_or_empty.value:
            expression = f'(is_not_null_or_empty({operand}))'
            is_valid = True if (slot_value and list(slot_value)) else False
        else:
            raise ActionFailure(f'Cannot evaluate invalid operator: "{operator}" for slot type "list"')

        return expression, is_valid

    @staticmethod
    def expr_as_str(sub_expressions: list, operator: str):
        expr_str = ''
        for expr in sub_expressions:
            if isinstance(expr, tuple):
                expr_str = expr_str + expr[0] + operator
            else:
                expr_str = expr_str + expr + operator
        expr_str = f'{{{re.sub(f"{operator}$", "", expr_str)}}}'
        return expr_str

    @staticmethod
    def list_slot_validation_operators():
        text_data_validations = [SlotValidationOperators.equal_to.value, SlotValidationOperators.not_equal_to.value,
                                 SlotValidationOperators.case_insensitive_equals.value, SlotValidationOperators.contains.value,
                                 SlotValidationOperators.starts_with.value, SlotValidationOperators.ends_with.value,
                                 SlotValidationOperators.has_length.value, SlotValidationOperators.has_length_greater_than.value,
                                 SlotValidationOperators.has_length_less_than.value, SlotValidationOperators.has_no_whitespace.value,
                                 SlotValidationOperators.is_in.value, SlotValidationOperators.is_not_in.value,
                                 SlotValidationOperators.is_not_null_or_empty.value, SlotValidationOperators.is_null_or_empty.value,
                                 SlotValidationOperators.is_an_email_address.value, SlotValidationOperators.matches_regex.value]
        operators = {
            SLOT_TYPE.LIST.value: [SlotValidationOperators.equal_to.value, SlotValidationOperators.contains.value,
                                   SlotValidationOperators.has_length.value, SlotValidationOperators.has_length_greater_than.value,
                                   SlotValidationOperators.has_length_less_than.value, SlotValidationOperators.is_in.value,
                                   SlotValidationOperators.is_not_in.value, SlotValidationOperators.is_null_or_empty.value,
                                   SlotValidationOperators.is_not_null_or_empty.value],
            SLOT_TYPE.BOOLEAN.value: [SlotValidationOperators.is_true.value, SlotValidationOperators.is_false.value],
            SLOT_TYPE.FLOAT.value: [SlotValidationOperators.equal_to.value, SlotValidationOperators.is_greater_than.value,
                                    SlotValidationOperators.is_less_than.value, SlotValidationOperators.is_in.value,
                                    SlotValidationOperators.is_not_in.value],
            SLOT_TYPE.TEXT.value: text_data_validations,
            SLOT_TYPE.CATEGORICAL.value: text_data_validations,
            SLOT_TYPE.ANY.value: text_data_validations
        }
        return operators