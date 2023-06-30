import json
import logging
import re
from datetime import datetime
from typing import Any, List, Text

import requests
from loguru import logger
from mongoengine import DoesNotExist
from rasa.shared.constants import UTTER_PREFIX
from rasa_sdk import Tracker

from .data_objects import HttpActionRequestBody, Actions
from .exception import ActionFailure
from .models import ActionParameterType, HttpRequestContentType, EvaluationType, ActionType
from ..admin.constants import BotSecretType
from ..admin.processor import Sysadmin
from ..constants import KAIRON_USER_MSG_ENTITY, PluginTypes
from ..data.constant import REQUEST_TIMESTAMP_HEADER, DEFAULT_NLU_FALLBACK_RESPONSE
from ..data.data_objects import Slots, KeyVault
from ..plugins.factory import PluginFactory
from ..utils import Utility
from ...exceptions import AppException


class ActionUtility:

    """
    Utility class to assist executing actions
    """

    @staticmethod
    def execute_http_request(http_url: str, request_method: str, request_body=None, headers=None,
                             content_type: str = HttpRequestContentType.json.value):
        """Executes http urls provided.

        @param http_url: HTTP url to be executed
        @param request_method: One of GET, PUT, POST, DELETE
        @param request_body: Request body to be sent with the request
        @param headers: header for the HTTP request
        @param content_type: request content type HTTP request
        :return: JSON/string response
        """
        timeout = Utility.environment['action'].get('request_timeout', 1)
        if not headers:
            headers = {}
        headers.update({
            REQUEST_TIMESTAMP_HEADER: datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        })

        try:
            if request_method.lower() in {'get', 'post', 'put', 'delete'}:
                response = requests.request(
                    request_method.upper(), http_url, headers=headers, timeout=timeout, **{content_type: request_body}
                )
            else:
                raise ActionFailure("Invalid request method!")
            logger.debug("raw response: " + str(response.text))
            logger.debug("status " + str(response.status_code))

            if response.status_code not in [200, 202, 201, 204]:
                raise ActionFailure(f"Got non-200 status code: {response.status_code} {response.text}")
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
    def encrypt_secrets(request_body: dict, tracker_data: dict):
        def mask_nested_json_values(json_dict: dict):
            encrypted_dict = {}
            for key, value in json_dict.items():
                if isinstance(value, dict):
                    encrypted_dict[key] = mask_nested_json_values(value)
                elif isinstance(value, str) and value in tracker_data['key_vault'].values():
                    encrypted_dict[key] = Utility.get_masked_value(value)
                else:
                    encrypted_dict[key] = value
            return encrypted_dict

        return mask_nested_json_values(request_body)

    @staticmethod
    def prepare_request(tracker_data: dict, http_action_config_params: List[HttpActionRequestBody], bot: Text):
        """
        Prepares request body:
        1. Fetches value of parameter from slot(Tracker) if parameter_type is slot and adds to request body
        2. Adds value of parameter directly if parameter_type is value
        3. Adds value of parameter as the sender_id.
        4. Adds value of parameter as user_message.
        @param tracker_data: Tracker data for the Http Action
        @param http_action_config_params: User defined request body parameters <key, value, parameter_type>
        @param bot: bot id
        :return: Request body for the HTTP request
        """
        request_body = {}
        request_body_log = {}

        for param in http_action_config_params or []:
            if param['parameter_type'] == ActionParameterType.sender_id.value:
                value = tracker_data.get(ActionParameterType.sender_id.value)
            elif param['parameter_type'] == ActionParameterType.slot.value:
                value = tracker_data.get(ActionParameterType.slot.value, {}).get(param['value'])
            elif param['parameter_type'] == ActionParameterType.user_message.value:
                value = tracker_data.get(ActionParameterType.user_message.value)
                if not ActionUtility.is_empty(value) and value.startswith("/"):
                    user_msg = tracker_data.get(KAIRON_USER_MSG_ENTITY)
                    if not ActionUtility.is_empty(user_msg):
                        value = user_msg
            elif param['parameter_type'] == ActionParameterType.intent.value:
                value = tracker_data.get(ActionParameterType.intent.value)
            elif param['parameter_type'] == ActionParameterType.chat_log.value:
                value = {
                    'sender_id': tracker_data.get(ActionParameterType.sender_id.value),
                    'session_started': tracker_data['session_started'],
                    'conversation': tracker_data.get(ActionParameterType.chat_log.value)
                }
            elif param['parameter_type'] == ActionParameterType.key_vault.value:
                value = ActionUtility.get_secret_from_key_vault(param['value'], bot, False)
            else:
                value = param['value']
            log_value = value
            if param['encrypt'] is True and param['parameter_type'] != ActionParameterType.chat_log.value:
                if not ActionUtility.is_empty(value) and param['parameter_type'] == ActionParameterType.value.value:
                    value = Utility.decrypt_message(value)

                if not ActionUtility.is_empty(value):
                    log_value = Utility.get_masked_value(value)

            request_body[param['key']] = value
            request_body_log[param['key']] = log_value

        return request_body, request_body_log

    @staticmethod
    def retrieve_value_for_custom_action_parameter(tracker_data: dict, action_config_param: dict, bot: Text):
        value = None
        if action_config_param:
            request_body, _ = ActionUtility.prepare_request(tracker_data, [action_config_param], bot)
            value = request_body[action_config_param['key']]
        return value

    @staticmethod
    def get_bot_settings(bot: Text):
        from kairon.shared.data.data_objects import BotSettings
        try:
            bot_settings = BotSettings.objects(bot=bot, status=True).get()
        except DoesNotExist as e:
            logger.exception(e)
            bot_settings = BotSettings(bot=bot, status=True)
        bot_settings = bot_settings.to_mongo().to_dict()
        return bot_settings

    @staticmethod
    def get_faq_action_config(bot: Text, name: Text):
        from kairon.shared.actions.data_objects import PromptAction
        try:
            k_faq_action_config = PromptAction.objects(bot=bot, name=name, status=True).get()
        except DoesNotExist as e:
            logger.exception(e)
            raise AppException("No action found for given bot and name")
        k_faq_action_config = k_faq_action_config.to_mongo().to_dict()
        k_faq_action_config.pop('_id', None)
        return k_faq_action_config

    @staticmethod
    def prepare_bot_responses(tracker: Tracker, last_n):
        """
        Retrieve user question and bot responses from tracker events and formats them
        as required for GPT3 messages.
        """
        message_trail = []
        for event in reversed(tracker.events):
            if event.get('event') == 'bot' and event.get("text"):
                message_trail.insert(0, {"role": "assistant", "content": event.get('text')})
                last_n -= 1
            elif event.get('event') == 'user':
                if message_trail and message_trail[0].get("role") == "user":
                    message_trail.pop(0)
                message_trail.insert(0, {"role": "user", "content": event.get('text')})
                if last_n <= 0:
                    break
            elif event.get('event') == 'session_started':
                break
        return message_trail

    @staticmethod
    def build_context(tracker: Tracker, extract_keyvault: bool = False):
        """
        Creates a dict of tracker object that contains contextual information
        required for filling parameter values based on its type or using it to
        format response using evaluation engine.

        @tracker: Tracker object
        :return: dict of required parameters.
        """
        iat, msg_trail = ActionUtility.prepare_message_trail(tracker.events)
        key_vault = {}
        if extract_keyvault:
            bot = tracker.get_slot('bot')
            key_vault = ActionUtility.get_all_secrets_from_keyvault(bot)
        return {
            ActionParameterType.sender_id.value: tracker.sender_id,
            ActionParameterType.user_message.value: tracker.latest_message.get('text'),
            ActionParameterType.slot.value: tracker.current_slot_values(),
            ActionParameterType.intent.value: tracker.get_intent_of_latest_message(),
            ActionParameterType.chat_log.value: msg_trail,
            ActionParameterType.key_vault.value: key_vault,
            KAIRON_USER_MSG_ENTITY: next(tracker.get_latest_entity_values(KAIRON_USER_MSG_ENTITY), None),
            "session_started": iat
        }

    @staticmethod
    def get_secret_from_key_vault(key: Text, bot: Text, raise_err: bool = True):
        """
        Get secret value for key from key vault.

        :param key: key to be added
        :param raise_err: raise error if key does not exists
        :param bot: bot id
        """
        if not Utility.is_exist(KeyVault, raise_error=False, key=key, bot=bot):
            if raise_err:
                raise AppException(f"key '{key}' does not exists!")
            else:
                return None
        key_value = KeyVault.objects(key=key, bot=bot).get().to_mongo().to_dict()
        value = key_value.get("value")
        if not Utility.check_empty_string(value):
            value = Utility.decrypt_message(value)
        return value

    @staticmethod
    def get_all_secrets_from_keyvault(bot: Text):
        """
        Get secret value for key from key vault.

        :param key: key to be added
        :param raise_err: raise error if key does not exists
        :param bot: bot id
        """
        secrets = {}
        for keyvault in KeyVault.objects(bot=bot):
            value = keyvault.value
            if not Utility.check_empty_string(value):
                value = Utility.decrypt_message(value)
            secrets.update({keyvault.key: value})
        return secrets

    @staticmethod
    def prepare_message_trail(tracker_events):
        """
        Prepare a conversation trail from tracker events.
        """
        message_trail = []
        initiated_at = None
        for event in tracker_events:
            if event.get('event') == 'session_started' and event.get('timestamp'):
                initiated_at = datetime.utcfromtimestamp(event['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
            elif event.get('event') == 'bot':
                data = {"text": event.get('text')}
                data.update(event.get('data'))
                message_trail.append({event['event']: data})
            elif event.get('event') == 'user':
                message_trail.append({event['event']: event.get('text')})

        return initiated_at, message_trail

    @staticmethod
    def prepare_message_trail_as_str(tracker_events):
        """
        Prepare a conversation trail from tracker events in the form of string.
        """
        message_trail_as_str = ''
        initiated_at = None
        for event in tracker_events:
            if event.get('event') == 'session_started' and event.get('timestamp'):
                initiated_at = datetime.utcfromtimestamp(event['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
            elif event.get('event') == 'user' or event.get('event') == 'bot':
                message_trail_as_str = f"{message_trail_as_str}{event['event']}: {event.get('text')}\n"

        return initiated_at, message_trail_as_str

    @staticmethod
    def prepare_url(http_url: str, tracker_data: dict):
        """
        Forms URL by replacing placeholders in it with values from tracker.
        Supports substitution of sender_id, intent, user message, key_vault and slot in the URL.

        @param http_url: HTTP Url
        @param tracker_data: tracker containing contextual info.
        :return: Prepared URL.
        """
        user_msg = tracker_data.get(ActionParameterType.user_message.value, "")
        if not ActionUtility.is_empty(user_msg) and user_msg.startswith("/"):
            previous_user_msg = tracker_data.get(KAIRON_USER_MSG_ENTITY)
            if not ActionUtility.is_empty(previous_user_msg):
                user_msg = previous_user_msg
        http_url = http_url.replace("$SENDER_ID", tracker_data.get(ActionParameterType.sender_id.value, ""))
        http_url = http_url.replace("$INTENT", tracker_data.get(ActionParameterType.intent.value, ""))
        http_url = http_url.replace("$USER_MESSAGE", user_msg)

        pattern_keyvault = r'\$\$\w+'
        key_vault_params = re.findall(pattern_keyvault, http_url)
        for param in key_vault_params:
            name = param.replace("$$", "")
            value = tracker_data.get(ActionParameterType.key_vault.value, {}).get(name, "")
            http_url = http_url.replace(param, value)

        pattern_slot = r'\$\w+'
        slot_params = re.findall(pattern_slot, http_url)
        for param in slot_params:
            name = param.replace("$", "")
            value = tracker_data.get(ActionParameterType.slot.value, {}).get(name, "")
            http_url = http_url.replace(param, value)
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
    def get_action_type(bot: str, name: str):
        """
        Retrieves action type.
        @param bot: bot id
        @param name: action name
        """
        if name.startswith(UTTER_PREFIX):
            action_type = ActionType.kairon_bot_response
        else:
            action = ActionUtility.get_action(bot=bot, name=name)
            action_type = action.get('type')
        return action_type

    @staticmethod
    def get_action(bot: str, name: str):
        """
        Retrieves action from database.
        @param bot: bot id
        @param name: action name
        """
        try:
            return Actions.objects(bot=bot, name=name, status=True).get().to_mongo().to_dict()
        except DoesNotExist as e:
            logger.exception(e)
            raise ActionFailure("No action found for given bot and name")

    @staticmethod
    def get_slot_type(bot: str, slot: str):
        try:
            slot_info = Slots.objects(name=slot, bot=bot, status=True).get()
            return slot_info.type
        except DoesNotExist as e:
            logger.exception(e)
            raise ActionFailure(f'Slot not found in database: {slot}')

    @staticmethod
    def perform_google_search(api_key: str, search_engine_id: str, search_term: str, **kwargs):
        from googleapiclient.discovery import build

        results = []
        try:
            service = build("customsearch", "v1", developerKey=api_key)
            search_results = service.cse().list(q=search_term, cx=search_engine_id, **kwargs).execute()
            for item in search_results.get('items') or []:
                results.append({'title': item['title'], 'text': item['snippet'], 'link': item['link']})
        except Exception as e:
            logger.exception(e)
            raise ActionFailure(e)
        return results

    @staticmethod
    def format_search_result(results: list):
        link = f'<a href = "{results[0]["link"]}" target="_blank" >{results[0]["title"]}</a>'
        return f'{results[0]["text"]}\nTo know more, please visit: {link}'

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
        data = http_response
        if isinstance(http_response, dict):
            data = http_response['data']
        if template.__contains__('${RESPONSE}'):
            parsed_output = template.replace('${RESPONSE}', json.dumps(data))
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
    def compose_response(response_config: dict, http_response: Any):
        response = response_config.get('value')
        evaluation_type = response_config.get('evaluation_type', EvaluationType.expression.value)
        if Utility.check_empty_string(response):
            result = None
            log = f"{evaluation_type}: {response} || data: {http_response} || Skipping evaluation as value is empty"
        elif evaluation_type == EvaluationType.script.value:
            result, log = ActionUtility.evaluate_script(response, http_response)
        else:
            result = ActionUtility.prepare_response(response, http_response)
            log = f"{evaluation_type}: {response} || data: {http_response} || response: {result}"
        return result, log

    @staticmethod
    def fill_slots_from_response(set_slots: list, http_response: Any):
        evaluated_slot_values = {}
        response_log = ["initiating slot evaluation"]
        for slot in set_slots:
            try:
                value, log = ActionUtility.compose_response(slot, http_response)
            except Exception as e:
                logger.exception(e)
                value = None
                log = str(e)
            log = f"slot: {slot['name']} || {log}"
            evaluated_slot_values[slot['name']] = value
            response_log.append(log)
        return evaluated_slot_values, response_log

    @staticmethod
    def prepare_email_body(tracker_events, subject: str, user_email: str = None):
        html_output = ""
        conversation_mail_template = Utility.email_conf['email']['templates']['conversation']
        bot_msg_template = Utility.email_conf['email']['templates']['bot_msg_conversation']
        user_msg_template = Utility.email_conf['email']['templates']['user_msg_conversation']
        for event in tracker_events:
            msg = ""
            if list(event.keys())[0] == 'bot':
                bot_reply = ActionUtility.__format_bot_reply(event.get('bot'))
                msg = bot_msg_template.replace('BOT_MESSAGE', bot_reply)
            elif list(event.keys())[0] == 'user':
                msg = user_msg_template.replace('USER_MESSAGE', event.get('user', ""))
            html_output = f"{html_output}{msg}"
        conversation_mail_template = conversation_mail_template.replace('SUBJECT', subject)
        if not ActionUtility.is_empty(user_email):
            conversation_mail_template = conversation_mail_template.replace('USER_EMAIL', user_email)
        conversation_mail_template.replace('This email was sent to USER_EMAIL', '')
        conversation_mail_template = conversation_mail_template.replace('CONVERSATION_REPLACE', html_output)
        return conversation_mail_template

    @staticmethod
    def prepare_email_text(custom_text_mail: str, tracker_data: dict, subject: str, user_email: str = None):
        text, _ = ActionUtility.evaluate_script(custom_text_mail, tracker_data)
        custom_text_mail_template = Utility.email_conf['email']['templates']['custom_text_mail']
        custom_text_mail_template = custom_text_mail_template.replace('SUBJECT', subject)
        if not ActionUtility.is_empty(user_email):
            custom_text_mail_template = custom_text_mail_template.replace('USER_EMAIL', user_email)
        custom_text_mail_template.replace('This email was sent to USER_EMAIL', '')
        custom_text_mail_template = custom_text_mail_template.replace('CUSTOM_TEXT', text)
        return custom_text_mail_template

    @staticmethod
    def __format_bot_reply(reply: dict):
        bot_reply = ""
        button_template = Utility.email_conf['email']['templates']['button_template']

        if reply.get('text'):
            bot_reply = reply['text']
        elif reply.get('buttons'):
            for btn in reply['buttons']:
                btn_reply = """
                <div style="font-size: 14px; color: #000000; font-weight: 400; padding: 12px; overflow: hidden; word-wrap: break-word;
                            border: 2px solid #ffffff; margin: 8px 0px 0px 0px; text-align: center; border-radius: 20px; background: transparent;
                            background-color: inherit; color: #000; max-width: 250px; box-sizing: border-box;">
                    BUTTON_TEXT
                </div>
                """.replace('BUTTON_TEXT', btn.get('text', ''))
                bot_reply = f"{bot_reply}\n{btn_reply}"
            bot_reply = button_template.replace('ALL_BUTTONS', bot_reply)
        elif reply.get("custom"):
            if reply["custom"].get('data'):
                custom_data = reply["custom"]['data']
                bot_reply = list(map(lambda x: ActionUtility.__format_custom_bot_reply(x), custom_data))
                bot_reply = "".join(bot_reply)
            else:
                bot_reply = str(reply["custom"])
        return bot_reply

    @staticmethod
    def __format_custom_bot_reply(data):
        if data.get('text') is not None:
            return data['text']

        reply = list(map(lambda x: ActionUtility.__format_custom_bot_reply(x), data['children']))
        reply = "".join(reply)

        if data.get('type') == "image":
            reply = f'<span><img src="{data.get("src")}" alt="{data.get("alt")}" width="150" height="150"/><br/><p>{data.get("alt")}</p></span>'
        elif data.get('type') == "paragraph":
            reply = f'<p>{reply}</p>'
        elif data.get('type') == "link":
            reply = f'<a target="_blank" href="{data.get("href")}">{reply}</a>'
        elif data.get('type') == "video":
            reply = f'<a target="_blank" href="{data.get("url")}">{data.get("url")}</a>'

        return reply

    @staticmethod
    def get_jira_client(url: str, username: str, api_token: str):
        from jira import JIRA

        try:
            return JIRA(
                server=url,
                basic_auth=(username, api_token),
            )
        except Exception as e:
            raise ActionFailure(f'Could not connect to url: {e}')
        except:
            raise ActionFailure(f"Could not connect to url: '{url}' using given credentials")

    @staticmethod
    def validate_jira_action(url: str, username: str, api_token: str, project_key: str, issue_type: str, parent_key: str = None):
        try:
            jira = ActionUtility.get_jira_client(url, username, api_token)
            project_meta = jira.project(project_key)
            if not project_meta:
                raise ActionFailure('Invalid project key')
            issue_types = project_meta.issueTypes
            issue_types = {i_type.name for i_type in issue_types}
            if issue_type not in issue_types:
                raise ActionFailure(f"No issue type '{issue_type}' exists")
            if issue_type == 'Subtask' and parent_key is None:
                raise ActionFailure("parent key is required for issues of type 'Subtask'")
        except Exception as e:
            raise ActionFailure(e)
        except:
            raise ActionFailure('Run time error while trying to validate configuration')

    @staticmethod
    def create_jira_issue(
            url: str, username: str, api_token: str, project_key: str, issue_type: str, summary: str,
            description, parent_key: str = None
    ):
        try:
            jira = ActionUtility.get_jira_client(url, username, api_token)
            fields = {
                "project": {'key': project_key},
                'issuetype': {"name": issue_type},
                "summary": summary,
                "description": description
            }
            if parent_key:
                fields.update({'parent': {'key': parent_key}})
            jira.create_issue(fields)
        except Exception as e:
            logger.exception(e)
            raise ActionFailure(e)
        except:
            raise ActionFailure('Run time error while trying to create JIRA issue')

    @staticmethod
    def validate_zendesk_credentials(subdomain: str, user_name: str, api_token: str):
        from zenpy import Zenpy
        from zenpy.lib.exception import APIException

        try:
            zendesk_client = Zenpy(subdomain=subdomain, email=user_name, token=api_token)
            list(zendesk_client.search(assignee='test'))
        except APIException as e:
            raise ActionFailure(e)

    @staticmethod
    def create_zendesk_ticket(
            subdomain: str, user_name: str, api_token: str, subject: str, description: str = None,
            comment: str = None, tags: list = None
    ):
        from zenpy import Zenpy
        from zenpy.lib.exception import APIException
        from zenpy.lib.api_objects import Comment
        from zenpy.lib.api_objects import Ticket

        try:
            zendesk_client = Zenpy(subdomain=subdomain, email=user_name, token=api_token)
            comment = Comment(html_body=comment)
            zendesk_client.tickets.create(Ticket(subject=subject, description=description, tags=tags, comment=comment))
        except APIException as e:
            raise ActionFailure(e)

    @staticmethod
    def prepare_pipedrive_metadata(tracker: Tracker, action_config: dict):
        metadata = {}
        for key, slot in action_config.get('metadata', {}).items():
            metadata[key] = tracker.get_slot(slot)
        return metadata

    @staticmethod
    def validate_pipedrive_credentials(domain: str, api_token: str):
        from pipedrive.client import Client
        from pipedrive.exceptions import UnauthorizedError

        try:
            client = Client(domain=domain)
            client.set_api_token(api_token)
            client.leads.get_all_leads()
        except UnauthorizedError as e:
            raise ActionFailure(e)

    @staticmethod
    def create_pipedrive_lead(domain: str, api_token: str, title: str, conversation: str, **kwargs):
        from pipedrive.client import Client

        client = Client(domain=domain)
        client.set_api_token(api_token)
        if kwargs.get('org_name'):
            organization = ActionUtility.create_pipedrive_organization(domain, api_token, **kwargs)
            kwargs['org_id'] = organization['id']
        person = ActionUtility.create_pipedrive_person(domain, api_token, **kwargs)
        payload = {'title': title, 'person_id': person['id'], 'organization_id': kwargs.get('org_id')}
        response = client.leads.create_lead(payload)
        if response.get("success") is not True:
            raise ActionFailure(f'Failed to create lead: {response}')
        kwargs['lead_id'] = response['data']['id']
        ActionUtility.create_pipedrive_note(domain, api_token, conversation, **kwargs)

    @staticmethod
    def create_pipedrive_organization(domain: str, api_token: str, **kwargs):
        from pipedrive.client import Client

        client = Client(domain=domain)
        client.set_api_token(api_token)
        payload = {'name': kwargs.get('org_name')}
        response = client.organizations.create_organization(payload)
        if response.get("success") is not True:
            raise ActionFailure(f'Failed to create organization: {response}')
        return response['data']

    @staticmethod
    def create_pipedrive_person(domain: str, api_token: str, **kwargs):
        from pipedrive.client import Client

        client = Client(domain=domain)
        client.set_api_token(api_token)
        email = [kwargs['email']] if kwargs.get('email') else None
        phone = [kwargs['phone']] if kwargs.get('phone') else None
        payload = {'name': kwargs.get('name'), 'org_id': kwargs.get('org_id'), 'email': email, 'phone': phone}
        response = client.persons.create_person(payload)
        if response.get("success") is not True:
            raise ActionFailure(f'Failed to create person: {response}')
        return response['data']

    @staticmethod
    def create_pipedrive_note(domain: str, api_token: str, conversation: str, **kwargs):
        from pipedrive.client import Client

        client = Client(domain=domain)
        client.set_api_token(api_token)
        payload = {'content': conversation, 'lead_id': kwargs.get('lead_id')}
        response = client.notes.create_note(payload)
        if response.get("success") is not True:
            raise ActionFailure(f'Failed to attach note: {response}')
        return response['data']

    @staticmethod
    def prepare_hubspot_form_request(tracker, fields: list, bot: Text):
        request = []
        for field in fields:
            parameter_value, _ = ActionUtility.prepare_request(tracker, [field], bot)
            request.append({"name": field['key'], "value": parameter_value[field['key']]})
        return {"fields": request}

    @staticmethod
    def get_basic_auth_str(username: Text, password: Text):
        return requests.auth._basic_auth_str(username, password)

    @staticmethod
    def evaluate_script(script: Text, data: Any, raise_err_on_failure: bool = True):
        log = f"script: {script} || data: {data} || raise_err_on_failure: {raise_err_on_failure}"
        endpoint = Utility.environment['evaluator']['url']
        request_body = {
            "script": script,
            "data": data
        }
        resp = ActionUtility.execute_http_request(endpoint, "POST", request_body)
        log = f"{log} || response: {resp}"
        if not resp.get('success') and raise_err_on_failure:
            raise ActionFailure(f'Expression evaluation failed: {log}')
        result = resp.get('data')
        return result, log

    @staticmethod
    def trigger_rephrase(bot: Text, text_response: Text):
        rephrased_message = None
        raw_resp = None
        prompt = open('./template/rephrase-prompt.txt').read()
        gpt_key = Sysadmin.get_bot_secret(bot, BotSecretType.gpt_key.value, raise_err=False)
        if not Utility.check_empty_string(gpt_key):
            prompt = f"{prompt}{text_response}\noutput:"
            logger.debug(f"gpt3_prompt: {prompt}")
            raw_resp = PluginFactory.get_instance(PluginTypes.gpt).execute(key=gpt_key, prompt=prompt)
            rephrased_message = Utility.retrieve_gpt_response(raw_resp)
        return raw_resp, rephrased_message

    @staticmethod
    def format_recommendations(llm_response, k_faq_action_config):
        recommendations = None
        if llm_response['content']['result']:
            recommendations = [
                {"text": item['payload']['query'], "payload": item['payload']['query']}
                for item in llm_response['content']['result']
            ]
            bot_response = k_faq_action_config.get('failure_message', DEFAULT_NLU_FALLBACK_RESPONSE)
        else:
            bot_response = DEFAULT_NLU_FALLBACK_RESPONSE
        return recommendations, bot_response
