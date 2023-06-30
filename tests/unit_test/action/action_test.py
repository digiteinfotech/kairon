import json
import os
import urllib.parse

from googleapiclient.http import HttpRequest
from pipedrive.exceptions import UnauthorizedError, BadRequestError

from kairon.actions.definitions.email import ActionEmail
from kairon.actions.definitions.factory import ActionFactory
from kairon.actions.definitions.form_validation import ActionFormValidation
from kairon.actions.definitions.google import ActionGoogleSearch
from kairon.actions.definitions.http import ActionHTTP
from kairon.actions.definitions.hubspot import ActionHubspotForms
from kairon.actions.definitions.jira import ActionJiraTicket
from kairon.actions.definitions.prompt import ActionPrompt
from kairon.actions.definitions.pipedrive import ActionPipedriveLeads
from kairon.actions.definitions.set_slot import ActionSetSlot
from kairon.actions.definitions.two_stage_fallback import ActionTwoStageFallback
from kairon.actions.definitions.zendesk import ActionZendeskTicket
from kairon.shared.constants import KAIRON_USER_MSG_ENTITY
from kairon.shared.data.constant import KAIRON_TWO_STAGE_FALLBACK
from kairon.shared.data.data_objects import Slots, KeyVault, BotSettings, LLMSettings

os.environ["system_file"] = "./tests/testing_data/system.yaml"
from typing import Dict, Text, Any, List

import pytest
import responses
from mongoengine import connect, QuerySet
from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher
from kairon.shared.actions.models import ActionType, HttpRequestContentType
from kairon.shared.actions.data_objects import HttpActionRequestBody, HttpActionConfig, ActionServerLogs, SlotSetAction, \
    Actions, FormValidationAction, EmailActionConfig, GoogleSearchAction, JiraAction, ZendeskAction, \
    PipedriveLeadsAction, SetSlots, HubspotFormsAction, HttpActionResponse, CustomActionRequestParameters, \
    KaironTwoStageFallbackAction, SetSlotsFromResponse, PromptAction
from kairon.actions.handlers.processor import ActionProcessor
from kairon.shared.actions.utils import ActionUtility
from kairon.shared.actions.exception import ActionFailure
from kairon.shared.utils import Utility
from unittest.mock import patch


class TestActions:

    @pytest.fixture(autouse=True, scope='class')
    def setup(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        db_url = Utility.environment['database']["url"]
        pytest.db_url = db_url
        Utility.load_email_configuration()
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))

    @pytest.fixture
    def mock_get_http_action_exception(self, monkeypatch):
        def _raise_excep(*arge, **kwargs):
            raise ActionFailure("No action found for given bot and name")

        monkeypatch.setattr(ActionUtility, "get_action", _raise_excep)

    @responses.activate
    def test_execute_http_request_get_with_auth_token(self):
        http_url = 'http://localhost:8080/mock'
        auth_token = "bearer jkhfhkujsfsfslfhjsfhkjsfhskhfksj"
        responses.reset()
        responses.add(
            method=responses.GET,
            url=http_url,
            json={'data': 'test_data', 'test_class': [{'key': 'value'}, {'key2': 'value2'}]},
            status=200,
            headers={"Authorization": auth_token}
        )

        response = ActionUtility.execute_http_request(headers={'Authorization': auth_token}, http_url=http_url,
                                                      request_method=responses.GET, content_type="json")
        assert response
        assert response['data'] == 'test_data'
        assert len(response['test_class']) == 2
        assert response['test_class'][1]['key2'] == 'value2'
        assert responses.calls[0].request.headers['Authorization'] == auth_token

    @responses.activate
    def test_execute_http_request_url_encoded_request_empty_request_body(self):
        http_url = 'http://localhost:8080/mock'
        auth_token = "bearer jkhfhkujsfsfslfhjsfhkjsfhskhfksj"
        responses.reset()
        responses.add(
            method=responses.GET,
            url=http_url,
            json={'data': 'test_data', 'test_class': [{'key': 'value'}, {'key2': 'value2'}]},
            status=200,
            headers={"Authorization": auth_token},
        )

        response = ActionUtility.execute_http_request(headers={'Authorization': auth_token}, http_url=http_url,
                                                      request_method=responses.GET, content_type=HttpRequestContentType.data.value)
        assert response
        assert response['data'] == 'test_data'
        assert len(response['test_class']) == 2
        assert response['test_class'][1]['key2'] == 'value2'
        assert responses.calls[0].request.headers['Authorization'] == auth_token

    def test_execute_http_request_url_invalid_content_type(self):
        http_url = 'http://localhost:8080/mock'
        with pytest.raises(ActionFailure):
            ActionUtility.execute_http_request(http_url=http_url, request_method=responses.GET,
                                               content_type=HttpRequestContentType.data.value)

    @responses.activate
    def test_execute_http_request_get_no_auth_token(self):
        http_url = 'http://localhost:8080/mock'
        responses.add(
            method=responses.GET,
            url=http_url,
            json={'data': 'test_data', 'test_class': [{'key': 'value'}, {'key2': 'value2'}]},
            status=200
        )

        response = ActionUtility.execute_http_request(headers={}, http_url=http_url,
                                                      request_method=responses.GET)
        assert response
        assert response['data'] == 'test_data'
        assert len(response['test_class']) == 2
        assert response['test_class'][1]['key2'] == 'value2'
        assert 'Authorization' not in responses.calls[0].request.headers

    @responses.activate
    def test_execute_http_request_get_with_params(self):
        http_url = 'http://localhost:8080/mock'
        responses.add(
            method=responses.GET,
            url=http_url,
            json={'data': 'test_data', 'test_class': [{'key': 'value'}, {'key2': 'value2'}]},
            status=200
        )
        params = {"test": "val1", "test2": "val2"}
        response = ActionUtility.execute_http_request(headers={}, http_url=http_url,
                                                      request_method=responses.GET, request_body=params)
        assert response
        assert response['data'] == 'test_data'
        assert len(response['test_class']) == 2
        assert response['test_class'][1]['key2'] == 'value2'
        assert 'Authorization' not in responses.calls[0].request.headers

    def test_prepare_url_with_path_params_and_query_params(self):
        http_url = 'http://localhost:8080/mock/$SENDER_ID/$INTENT/$USER_MESSAGE/$$KEY_VAULT/$$AWS/$email?sender_id=$SENDER_ID&userid=1011&intent=$INTENT&msg=$USER_MESSAGE&key=$$KEY_VAULT&aws=$$AWS&email=$email'
        tracker_data = {'slot': {"email": "udit.pandey@digite.com", "firstname": "udit"},
                        'sender_id': "987654321", "intent": "greet", "user_message": "hello",
                        'key_vault': {'EMAIL': 'nkhare@digite.com', 'KEY_VAULT': '123456789-0lmgxzxdfghj', 'AWS': '435fdr'}}
        updated_url = ActionUtility.prepare_url(http_url, tracker_data)
        assert updated_url == 'http://localhost:8080/mock/987654321/greet/hello/123456789-0lmgxzxdfghj/435fdr/udit.pandey@digite.com?sender_id=987654321&userid=1011&intent=greet&msg=hello&key=123456789-0lmgxzxdfghj&aws=435fdr&email=udit.pandey@digite.com'

        tracker_data['user_message'] = '/custom_action{"kairon_user_msg": "what is digite?"}'
        tracker_data[KAIRON_USER_MSG_ENTITY] = "what is digite?"
        updated_url = ActionUtility.prepare_url(http_url, tracker_data)
        assert updated_url == 'http://localhost:8080/mock/987654321/greet/what is digite?/123456789-0lmgxzxdfghj/435fdr/udit.pandey@digite.com?sender_id=987654321&userid=1011&intent=greet&msg=what is digite?&key=123456789-0lmgxzxdfghj&aws=435fdr&email=udit.pandey@digite.com'

    def test_prepare_url_without_params(self):
        http_url = 'http://localhost:8080/mock'
        tracker_data = {'slot': {"email": "udit.pandey@digite.com", "firstname": "udit"},
                        'sender_id': "987654321", "intent": "greet", "user_message": "hello",
                        'key_vault': {'EMAIL': 'nkhare@digite.com', 'KEY_VAULT': '123456789-0lmgxzxdfghj'}}
        updated_url = ActionUtility.prepare_url(http_url, tracker_data)
        assert updated_url == http_url

    def test_prepare_url_with_multiple_placeholders(self):
        http_url = 'http://localhost:8080/mock?sender_id1=$SENDER_ID&intent1=$INTENT&msg1=$USER_MESSAGE&key1=$$KEY_VAULT&email1=$email&sender_id=$SENDER_ID&intent=$INTENT&msg=$USER_MESSAGE&key=$$KEY_VAULT&email=$email/'
        tracker_data = {'slot': {"email": "udit.pandey@digite.com", "firstname": "udit"},
                        'sender_id': "987654321", "intent": "greet", "user_message": "hello",
                        'key_vault': {'EMAIL': 'nkhare@digite.com', 'KEY_VAULT': '123456789-0lmgxzxdfghj'}}
        updated_url = ActionUtility.prepare_url(http_url, tracker_data)
        assert updated_url == 'http://localhost:8080/mock?sender_id1=987654321&intent1=greet&msg1=hello&key1=123456789-0lmgxzxdfghj&email1=udit.pandey@digite.com&sender_id=987654321&intent=greet&msg=hello&key=123456789-0lmgxzxdfghj&email=udit.pandey@digite.com/'

    def test_prepare_url_with_expression_failed_evaluation(self):
        http_url = 'http://localhost:8080/mock?sender_id=$SENDER_ID&intent=$INTENT&msg=$USER_MESSAGE&email=$email/'
        tracker_data = {'slot': {"email": "udit.pandey@digite.com", "firstname": "udit"}}
        updated_url = ActionUtility.prepare_url(http_url, tracker_data)
        assert updated_url == 'http://localhost:8080/mock?sender_id=&intent=&msg=&email=udit.pandey@digite.com/'

    def test_prepare_url_with_expression_failed_evaluation_with_keyvault(self):
        http_url = 'http://localhost:8080/mock?sender_id=$SENDER_ID&intent=$INTENT&msg=$USER_MESSAGE&key=$$KEY_VAULT&email=$email/'
        tracker_data = {'slot': {"email": "udit.pandey@digite.com", "firstname": "udit"}}
        updated_url = ActionUtility.prepare_url(http_url, tracker_data)
        assert updated_url == 'http://localhost:8080/mock?sender_id=&intent=&msg=&key=&email=udit.pandey@digite.com/'

    def test_build_context_with_keyvault_flag_True(self):
        KeyVault(key="EMAIL", value="nkhare@digite.com", bot="5j59kk1a76b698ca10d35d2e", user="user").save()
        slots = {"bot": "5j59kk1a76b698ca10d35d2e", "param2": "param2value", "email": "nkhare@digite.com", "firstname": "nupur"}
        events = [{"event1": "hello"}, {"event2": "how are you"}]
        latest_message = {'text': 'get intents', 'intent_ranking': [{'name': 'http_action'}]}
        tracker = Tracker(sender_id="sender1", slots=slots, events=events, paused=False, latest_message=latest_message,
                          followup_action=None, active_loop=None, latest_action_name=None)
        tracker_data = ActionUtility.build_context(tracker, True)
        assert tracker_data == {'sender_id': 'sender1', 'user_message': 'get intents',
                                'slot': {'bot': '5j59kk1a76b698ca10d35d2e', 'param2': 'param2value',
                                         'email': 'nkhare@digite.com', 'firstname': 'nupur'}, 'intent': 'http_action',
                                'chat_log': [], 'key_vault': {'EMAIL': 'nkhare@digite.com'}, 'kairon_user_msg': None,
                                'session_started': None}

    def test_build_context_with_keyvault_flag_False(self):
        KeyVault(key="EMAIL", value="nkhare@digite.com", bot="5j59kk1a76b698ca10d35d2e", user="user").save()
        slots = {"bot": "5j59kk1a76b698ca10d35d2e", "param2": "param2value", "email": "nkhare@digite.com", "firstname": "nupur"}
        events = [{"event1": "hello"}, {"event2": "how are you"}]
        latest_message = {'text': 'get intents', 'intent_ranking': [{'name': 'http_action'}]}
        tracker = Tracker(sender_id="sender1", slots=slots, events=events, paused=False, latest_message=latest_message,
                          followup_action=None, active_loop=None, latest_action_name=None)
        tracker_data = ActionUtility.build_context(tracker, False)
        assert tracker_data == {'sender_id': 'sender1', 'user_message': 'get intents',
                                'slot': {'bot': '5j59kk1a76b698ca10d35d2e', 'param2': 'param2value',
                                         'email': 'nkhare@digite.com', 'firstname': 'nupur'}, 'intent': 'http_action',
                                'chat_log': [], 'key_vault': {}, 'kairon_user_msg': None, 'session_started': None}

    def test_build_context_no_keyvault(self):
        slots = {"bot": "5z11mk1a76b698ca10d15d2e", "param2": "param2value", "email": "nupur@digite.com", "firstname": "nkhare"}
        events = [{"event1": "hello"}, {"event2": "how are you"}]
        latest_message = {'text': 'get intents', 'intent_ranking': [{'name': 'http_action'}]}
        tracker = Tracker(sender_id="sender1", slots=slots, events=events, paused=False, latest_message=latest_message,
                          followup_action=None, active_loop=None, latest_action_name=None)
        tracker_data = ActionUtility.build_context(tracker, True)
        assert tracker_data == {'sender_id': 'sender1', 'user_message': 'get intents',
                                'slot': {'bot': '5z11mk1a76b698ca10d15d2e', 'param2': 'param2value',
                                         'email': 'nupur@digite.com', 'firstname': 'nkhare'}, 'intent': 'http_action',
                                'chat_log': [], 'key_vault': {}, 'kairon_user_msg': None,
                                'session_started': None}

    def test_execute_http_request_invalid_method_type(self):
        http_url = 'http://localhost:8080/mock'
        params = {"test": "val1", "test2": "val2"}
        with pytest.raises(ActionFailure, match="Invalid request method!"):
            ActionUtility.execute_http_request(headers=None, http_url=http_url,
                                               request_method='OPTIONS', request_body=params)

    @responses.activate
    def test_execute_http_request_post_with_auth_token(self):
        http_url = 'http://localhost:8080/mock'
        auth_token = "bearer jkhfhkujsfsfslfhjsfhkjsfhskhfksj"
        resp_msg = "Data added successfully"
        request_params = {'data': 'test_data', 'test_class': [{'key': 'value'}, {'key2': 'value2'}]}

        responses.add(
            method=responses.POST,
            url=http_url,
            body=resp_msg,
            status=200,
            match=[responses.matchers.json_params_matcher(request_params)],
            headers={"Authorization": auth_token}
        )

        response = ActionUtility.execute_http_request(headers={'Authorization': auth_token}, http_url=http_url,
                                                      request_method=responses.POST, request_body=request_params)
        assert response
        assert response == resp_msg
        assert responses.calls[0].request.headers['Authorization'] == auth_token

    @responses.activate
    def test_execute_http_request_post_no_auth_token(self):
        http_url = 'http://localhost:8080/mock'
        resp_msg = "Data added successfully"
        request_params = {'data': 'test_data', 'test_class': [{'key': 'value'}, {'key2': 'value2'}]}

        responses.add(
            method=responses.POST,
            url=http_url,
            body=resp_msg,
            status=200,
            match=[responses.matchers.json_params_matcher(request_params)]
        )

        response = ActionUtility.execute_http_request(headers=None, http_url=http_url,
                                                      request_method=responses.POST, request_body=request_params)
        assert response
        assert response == resp_msg
        assert 'Authorization' not in responses.calls[0].request.headers

    @responses.activate
    def test_execute_http_request_put_with_auth_token(self):
        http_url = 'http://localhost:8080/mock'
        auth_token = "bearer jkhfhkujsfsfslfhjsfhkjsfhskhfksj"
        resp_msg = "Data updated successfully"
        request_params = {'data': 'test_data', 'test_class': [{'key': 'value'}, {'key2': 'value2'}]}

        responses.add(
            method=responses.PUT,
            url=http_url,
            body=resp_msg,
            status=200,
            match=[responses.matchers.json_params_matcher(request_params)],
            headers={"Authorization": auth_token}
        )

        response = ActionUtility.execute_http_request(headers={'Authorization': auth_token}, http_url=http_url,
                                                      request_method=responses.PUT, request_body=request_params)
        assert response
        assert response == resp_msg
        assert responses.calls[0].request.headers['Authorization'] == auth_token

    @responses.activate
    def test_execute_http_request_put_no_auth_token(self):
        http_url = 'http://localhost:8080/mock'
        resp_msg = "Data updated successfully"
        request_params = {'data': 'test_data', 'test_class': [{'key': 'value'}, {'key2': 'value2'}]}

        responses.add(
            method=responses.PUT,
            url=http_url,
            body=resp_msg,
            status=200,
            match=[responses.matchers.json_params_matcher(request_params)]
        )

        response = ActionUtility.execute_http_request(headers=None, http_url=http_url,
                                                      request_method=responses.PUT, request_body=request_params)
        assert response
        assert response == resp_msg
        assert 'Authorization' not in responses.calls[0].request.headers

    @responses.activate
    def test_execute_http_request_delete_with_request_body_auth_token(self):
        http_url = 'http://localhost:8080/mock'
        auth_token = "bearer jkhfhkujsfsfslfhjsfhkjsfhskhfksj"
        resp_msg = "Data deleted successfully"
        request_params = {'data': 'test_data', 'test_class': [{'key': 'value'}, {'key2': 'value2'}]}

        responses.add(
            method=responses.DELETE,
            url=http_url,
            body=resp_msg,
            status=200,
            match=[responses.matchers.json_params_matcher(request_params)],
            headers={"Authorization": auth_token}
        )

        response = ActionUtility.execute_http_request(headers={'Authorization': auth_token}, http_url=http_url,
                                                      request_method=responses.DELETE, request_body=request_params)
        assert response
        assert response == resp_msg
        assert responses.calls[0].request.headers['Authorization'] == auth_token

    @responses.activate
    def test_execute_http_request_delete_with_auth_token_no_request_body(self):
        http_url = 'http://localhost:8080/mock'
        auth_token = "bearer jkhfhkujsfsfslfhjsfhkjsfhskhfksj"
        resp_msg = "Data deleted successfully"

        responses.add(
            method=responses.DELETE,
            url=http_url,
            body=resp_msg,
            status=200,
            headers={"Authorization": auth_token}
        )

        response = ActionUtility.execute_http_request(headers={'Authorization': auth_token}, http_url=http_url,
                                                      request_method=responses.DELETE, request_body=None)
        assert response
        assert response == resp_msg
        assert responses.calls[0].request.headers['Authorization'] == auth_token

    @responses.activate
    def test_execute_http_request_with_failed_request(self):
        http_url = 'http://localhost:8080/mock'
        resp_msg = "Internal Server Error"
        request_params = {'data': 'test_data', 'test_class': [{'key': 'value'}, {'key2': 'value2'}]}

        responses.add(
            method=responses.DELETE,
            url=http_url,
            body=resp_msg,
            status=500,
            match=[
                responses.matchers.json_params_matcher(request_params)
            ]
        )

        with pytest.raises(ActionFailure, match="Got non-200 status code"):
            ActionUtility.execute_http_request(headers=None, http_url=http_url,
                                               request_method=responses.DELETE, request_body=request_params)

    @responses.activate
    def test_execute_http_request_delete_no_auth_token(self):
        http_url = 'http://localhost:8080/mock'
        resp_msg = "Data updated successfully"
        request_params = {'data': 'test_data', 'test_class': [{'key': 'value'}, {'key2': 'value2'}]}

        responses.add(
            method=responses.DELETE,
            url=http_url,
            body=resp_msg,
            status=200,
            match=[
                responses.matchers.json_params_matcher(request_params)
            ]
        )

        response = ActionUtility.execute_http_request(headers=None, http_url=http_url,
                                                      request_method=responses.DELETE, request_body=request_params)
        assert response
        assert response == resp_msg
        assert 'Authorization' not in responses.calls[0].request.headers

    def test_get_http_action_config(self):
        http_params = [HttpActionRequestBody(key="key1", value="value1", parameter_type="slot"),
                       HttpActionRequestBody(key="key2", value="value2")]
        expected = HttpActionConfig(
            action_name="http_action",
            response=HttpActionResponse(value="json"),
            http_url="http://test.com",
            request_method="GET",
            params_list=http_params,
            bot="bot",
            user="user"
        ).save().to_mongo().to_dict()

        actual = ActionHTTP("bot", "http_action").retrieve_config()
        assert actual is not None
        assert expected['action_name'] == actual['action_name']
        assert expected['response'] == actual['response']
        assert expected['http_url'] == actual['http_url']
        assert expected['request_method'] == actual['request_method']
        assert expected['params_list'] is not None
        assert expected['params_list'][0]['key'] == actual['params_list'][0]['key']
        assert expected['params_list'][0]['value'] == actual['params_list'][0]['value']
        assert expected['params_list'][0]['parameter_type'] == actual['params_list'][0]['parameter_type']
        assert expected['params_list'][1]['key'] == actual['params_list'][1]['key']
        assert expected['params_list'][1]['value'] == actual['params_list'][1]['value']
        assert expected['params_list'][1]['parameter_type'] == actual['params_list'][1]['parameter_type']
        assert actual['status']

    def test_get_http_action_config_deleted_action(self):
        http_params = [HttpActionRequestBody(key="key1", value="value1", parameter_type="slot"),
                       HttpActionRequestBody(key="key2", value="value2")]
        HttpActionConfig(
            action_name="test_get_http_action_config_deleted_action",
            response=HttpActionResponse(value="${RESPONSE}"),
            http_url="http://www.digite.com",
            request_method="POST",
            params_list=http_params,
            bot="bot",
            user="user",
            status=False
        ).save().to_mongo().to_dict()
        expected = HttpActionConfig(
            action_name="test_get_http_action_config_deleted_action",
            response=HttpActionResponse(value="json"),
            http_url="http://test.com",
            request_method="GET",
            params_list=http_params,
            bot="bot",
            user="user"
        ).save().to_mongo().to_dict()

        actual = ActionHTTP("bot", "test_get_http_action_config_deleted_action").retrieve_config()
        assert actual is not None
        assert expected['action_name'] == actual['action_name']
        assert expected['response'] == actual['response']
        assert expected['http_url'] == actual['http_url']
        assert expected['request_method'] == actual['request_method']
        assert expected['params_list'] is not None
        assert expected['params_list'][0]['key'] == actual['params_list'][0]['key']
        assert expected['params_list'][0]['value'] == actual['params_list'][0]['value']
        assert expected['params_list'][0]['parameter_type'] == actual['params_list'][0]['parameter_type']
        assert expected['params_list'][1]['key'] == actual['params_list'][1]['key']
        assert expected['params_list'][1]['value'] == actual['params_list'][1]['value']
        assert expected['params_list'][1]['parameter_type'] == actual['params_list'][1]['parameter_type']
        assert actual['status']

    def test_get_http_action_no_bot(self):
        try:
            ActionHTTP(bot=None, name="http_action").retrieve_config()
            assert False
        except ActionFailure as ex:
            assert str(ex) == "No HTTP action found for given action and bot"

    def test_get_http_action_no_http_action(self):
        try:
            ActionHTTP(bot="bot", name=None).retrieve_config()
            assert False
        except ActionFailure as ex:
            assert str(ex) == "No HTTP action found for given action and bot"

    def test_get_http_action_invalid_bot(self):
        http_params = [HttpActionRequestBody(key="key1", value="value1", parameter_type="slot"),
                       HttpActionRequestBody(key="key2", value="value2")]
        HttpActionConfig(
            action_name="http_action",
            response=HttpActionResponse(value="json"),
            http_url="http://test.com",
            request_method="GET",
            params_list=http_params,
            bot="bot",
            user="user"
        ).save().to_mongo().to_dict()

        try:
            ActionHTTP("bot1", "http_action").retrieve_config()
            assert False
        except ActionFailure as ex:
            assert str(ex).__contains__("No HTTP action found for given action and bot")

    def test_get_http_action_invalid_http_action(self):
        http_params = [HttpActionRequestBody(key="key1", value="value1", parameter_type="slot"),
                       HttpActionRequestBody(key="key2", value="value2")]
        HttpActionConfig(
            action_name="http_action",
            response=HttpActionResponse(value="json"),
            http_url="http://test.com",
            request_method="GET",
            params_list=http_params,
            bot="bot",
            user="user"
        ).save().to_mongo().to_dict()

        try:
            ActionHTTP("bot", "http_action1").retrieve_config()
            assert False
        except ActionFailure as ex:
            assert str(ex).__contains__("No HTTP action found for given action and bot")

    def test_get_http_action_no_request_body(self):
        http_params = []
        HttpActionConfig(
            action_name="http_action",
            response=HttpActionResponse(value="json"),
            http_url="http://test.com",
            request_method="GET",
            params_list=http_params,
            bot="bot",
            user="user"
        ).save().to_mongo().to_dict()

        try:
            ActionHTTP("bot", "http_action1").retrieve_config()
            assert False
        except ActionFailure as ex:
            assert str(ex).__contains__("No HTTP action found for given action and bot")

    def test_prepare_header_no_header(self):
        slots = {"bot": "demo_bot", "http_action_config": "http_action_name", "slot_name": "param2value"}
        tracker = {"sender_id": "sender1", "slot": slots}
        actual = ActionUtility.prepare_request(tracker, None, "test")
        assert actual == ({}, {})

    def test_prepare_request(self):
        slots = {"bot": "demo_bot", "http_action_config": "http_action_name", "slot_name": "param2value"}
        http_action_config_params = [HttpActionRequestBody(key="param1", value="value1"),
                                     HttpActionRequestBody(key="param2", value="slot_name", parameter_type="slot")]
        tracker = {"sender_id": "sender1", "slot": slots}
        actual_request_body, log = ActionUtility.prepare_request(tracker, http_action_config_params=http_action_config_params, bot="test")
        assert actual_request_body
        assert actual_request_body['param1'] == 'value1'
        assert actual_request_body['param2'] == 'param2value'
        assert log == {'param1': 'value1', 'param2': 'param2value'}

    def test_prepare_request_encryption(self):
        bot = "demo_bot"
        KeyVault(key="ACCESS_KEY", value="234567890fdsf", bot=bot, user="test_user").save()
        slots = {"bot": "demo_bot", "http_action_config": "http_action_name", "slot_name": "param2value"}
        http_action_config_params = [HttpActionRequestBody(key="param1", value=Utility.encrypt_message("value1"), encrypt=True),
                                     HttpActionRequestBody(key="param2", value="bot", parameter_type="slot", encrypt=True),
                                     HttpActionRequestBody(key="param3", parameter_type="sender_id", encrypt=True),
                                     HttpActionRequestBody(key="param4", parameter_type="user_message", encrypt=True),
                                     HttpActionRequestBody(key="param5", parameter_type="intent", encrypt=True),
                                     HttpActionRequestBody(key="param6", parameter_type="chat_log", encrypt=True),
                                     HttpActionRequestBody(key="param7", value="http_action_config", parameter_type="slot", encrypt=True),
                                     HttpActionRequestBody(key="param8", parameter_type="key_vault", value="ACCESS_KEY", encrypt=True),]
        tracker = {"sender_id": "sender1", "slot": slots, "intent": "greet", "user_message": "hi",
                   "chat_log": [{'user': 'hi'}, {'bot': 'are you ok?'}, {'user': 'yes'}, {'bot': 'Great, carry on!'},
                                {'user': 'hi'}], 'session_started': '2021-12-31 16:59:38'}
        actual_request_body, log = ActionUtility.prepare_request(tracker, http_action_config_params, bot)
        assert actual_request_body == {'param1': 'value1', 'param2': 'demo_bot', 'param3': 'sender1', 'param4': 'hi',
                                       'param5': 'greet',
                                       'param6': {'sender_id': 'sender1', 'session_started': '2021-12-31 16:59:38',
                                                  'conversation': [{'user': 'hi'}, {'bot': 'are you ok?'},
                                                                   {'user': 'yes'}, {'bot': 'Great, carry on!'},
                                                                   {'user': 'hi'}]},
                                       'param7': 'http_action_name', 'param8': '234567890fdsf',
                                       }
        assert log == {'param1': '****e1', 'param2': '******ot', 'param3': '*****r1', 'param4': '**',
                       'param5': '***et', 'param6': {'sender_id': 'sender1', 'session_started': '2021-12-31 16:59:38',
                                                     'conversation': [{'user': 'hi'}, {'bot': 'are you ok?'},
                                                                      {'user': 'yes'}, {'bot': 'Great, carry on!'},
                                                                      {'user': 'hi'}]},
                       'param7': '**************me', 'param8': '***********sf'}

    def test_prepare_request_empty_slot(self):
        slots = {"bot": "demo_bot", "http_action_config": "http_action_name", "param2": "param2value"}
        http_action_config_params = [HttpActionRequestBody(key="param1", value="value1"),
                                     HttpActionRequestBody(key="param3", value="", parameter_type="slot")]
        tracker = {"sender_id": "sender1", "slot": slots}
        request_params, log = ActionUtility.prepare_request(tracker, http_action_config_params=http_action_config_params, bot="demo_bot")
        assert request_params['param1'] == "value1"
        assert not request_params['param3']
        assert log == {'param1': 'value1', 'param3': None}

    def test_prepare_request_sender_id(self):
        slots = {"bot": "demo_bot", "http_action_config": "http_action_name", "param2": "param2value"}
        events = [{"event1": "hello"}, {"event2": "how are you"}]
        http_action_config_params = [HttpActionRequestBody(key="param1", value="value1"),
                                     HttpActionRequestBody(key="user_id", value="", parameter_type="sender_id")]
        tracker = {"sender_id": "kairon_user@digite.com", "slot": slots}
        request_params, log = ActionUtility.prepare_request(tracker, http_action_config_params=http_action_config_params, bot="demo_bot")
        assert request_params['param1'] == "value1"
        assert request_params['user_id'] == "kairon_user@digite.com"
        assert log == {'param1': 'value1', 'user_id': 'kairon_user@digite.com'}

    def test_prepare_request_with_intent(self):
        slots = {"bot": "demo_bot", "http_action_config": "http_action_name", "param2": "param2value"}
        events = [{"event1": "hello"}, {"event2": "how are you"}]
        http_action_config_params = [HttpActionRequestBody(key="param1", value="value1"),
                                     HttpActionRequestBody(key="card_type", parameter_type="intent")]
        tracker = {"sender_id": "kairon_user@digite.com", "slot": slots, "intent": "restart"}
        request_params, log = ActionUtility.prepare_request(tracker, http_action_config_params=http_action_config_params, bot="demo_bot")
        assert request_params['param1'] == "value1"
        assert request_params['card_type'] == "restart"
        assert log['param1'] == "value1"
        assert log['card_type'] == "restart"

    def test_prepare_request_with_message_trail(self):
        slots = {"bot": "demo_bot", "http_action_config": "http_action_name", "param2": "param2value"}
        events = [{'event': 'action', 'timestamp': 1640969978.0159726, 'name': 'action_session_start', 'policy': None,
                   'confidence': 1.0, 'action_text': None, 'hide_rule_turn': False},
                  {'event': 'session_started', 'timestamp': 1640969978.0159986},
                  {'event': 'action', 'timestamp': 1640969978.016019, 'name': 'action_listen', 'policy': None,
                   'confidence': None, 'action_text': None, 'hide_rule_turn': False},
                  {'event': 'user', 'timestamp': 1640969978.0570025, 'text': 'hi', 'parse_data': {
                      'intent': {'id': -8668963632308028537, 'name': 'greet', 'confidence': 0.99999588727951},
                      'entities': [], 'text': 'hi', 'message_id': '4e73ad5c91b64efebdf40c7f3d4e52fa', 'metadata': {},
                      'intent_ranking': [{'id': -8668963632308028537, 'name': 'greet', 'confidence': 0.99999588727951},
                                         {'id': -1751152876609809599, 'name': 'request_form',
                                          'confidence': 2.344663471376407e-06},
                                         {'id': -2576880868556300477, 'name': 'bot_challenge',
                                          'confidence': 1.020069134938239e-06},
                                         {'id': 7193050473371041842, 'name': 'mood_great',
                                          'confidence': 1.82201702614293e-07},
                                         {'id': 663567542510652931, 'name': 'deny',
                                          'confidence': 1.634757040847034e-07},
                                         {'id': -6952488953767557633, 'name': 'mood_unhappy',
                                          'confidence': 1.4424769290144457e-07},
                                         {'id': 1097471593766011183, 'name': 'affirm',
                                          'confidence': 1.358881149826629e-07},
                                         {'id': 1147054466470445121, 'name': 'goodbye',
                                          'confidence': 1.20473117704023e-07}],
                      'response_selector': {'all_retrieval_intents': [], 'default': {
                          'response': {'id': None, 'responses': None, 'response_templates': None, 'confidence': 0.0,
                                       'intent_response_key': None, 'utter_action': 'utter_None',
                                       'template_name': 'utter_None'}, 'ranking': []}}}, 'input_channel': 'cmdline',
                   'message_id': '4e73ad5c91b64efebdf40c7f3d4e52fa', 'metadata': {}},
                  {'event': 'user_featurization', 'timestamp': 1640969978.0593514, 'use_text_for_featurization': False},
                  {'event': 'action', 'timestamp': 1640969978.0593657, 'name': 'know_user',
                   'policy': 'policy_1_RulePolicy', 'confidence': 1.0, 'action_text': None, 'hide_rule_turn': True},
                  {'event': 'active_loop', 'timestamp': 1640969978.059406, 'name': 'know_user'},
                  {'event': 'slot', 'timestamp': 1640969978.0594149, 'name': 'happy', 'value': 'happy_user'},
                  {'event': 'slot', 'timestamp': 1640969978.0594206, 'name': 'requested_slot', 'value': 'is_ok'},
                  {'event': 'bot', 'timestamp': 1640969978.0594227,
                   'metadata': {'utter_action': 'utter_ask_know_user_is_ok'}, 'text': 'are you ok?',
                   'data': {'elements': None, 'quick_replies': None, 'buttons': None, 'attachment': None, 'image': None,
                            'custom': None}},
                  {'event': 'action', 'timestamp': 1640969978.0599716, 'name': 'action_listen',
                   'policy': 'policy_1_RulePolicy', 'confidence': 1.0, 'action_text': None, 'hide_rule_turn': True},
                  {'event': 'user', 'timestamp': 1640969981.5157223, 'text': 'yes', 'parse_data': {
                      'intent': {'id': 1097471593766011183, 'name': 'affirm', 'confidence': 0.9999915361404411},
                      'entities': [], 'text': 'yes', 'message_id': '77e78de14cb046f0826cb90f9edb830a', 'metadata': {},
                      'intent_ranking': [
                          {'id': 1097471593766011183, 'name': 'affirm', 'confidence': 0.9999915361404411},
                          {'id': 7193050473371041842, 'name': 'mood_great', 'confidence': 4.36471009379602e-06},
                          {'id': -1751152876609809599, 'name': 'request_form', 'confidence': 1.730760686768917e-06},
                          {'id': -2576880868556300477, 'name': 'bot_challenge', 'confidence': 6.831762107140094e-07},
                          {'id': -6952488953767557633, 'name': 'mood_unhappy', 'confidence': 6.729432016072678e-07},
                          {'id': 1147054466470445121, 'name': 'goodbye', 'confidence': 5.120287482895947e-07},
                          {'id': 663567542510652931, 'name': 'deny', 'confidence': 3.602933134061459e-07},
                          {'id': -8668963632308028537, 'name': 'greet', 'confidence': 1.1663559007502039e-07}],
                      'response_selector': {'all_retrieval_intents': [], 'default': {
                          'response': {'id': None, 'responses': None, 'response_templates': None, 'confidence': 0.0,
                                       'intent_response_key': None, 'utter_action': 'utter_None',
                                       'template_name': 'utter_None'}, 'ranking': []}}}, 'input_channel': 'cmdline',
                   'message_id': '77e78de14cb046f0826cb90f9edb830a', 'metadata': {}},
                  {'event': 'user_featurization', 'timestamp': 1640969981.5169573, 'use_text_for_featurization': False},
                  {'event': 'action', 'timestamp': 1640969981.5169718, 'name': 'know_user',
                   'policy': 'policy_1_RulePolicy', 'confidence': 1.0, 'action_text': None, 'hide_rule_turn': True},
                  {'event': 'slot', 'timestamp': 1640969981.5169845, 'name': 'is_ok', 'value': 'yes'},
                  {'event': 'slot', 'timestamp': 1640969981.5169895, 'name': 'requested_slot', 'value': None},
                  {'event': 'active_loop', 'timestamp': 1640969981.5169928, 'name': None},
                  {'event': 'action', 'timestamp': 1640969981.5179346, 'name': 'utter_happy',
                   'policy': 'policy_1_RulePolicy', 'confidence': 1.0, 'action_text': None, 'hide_rule_turn': True},
                  {'event': 'bot', 'timestamp': 1640969981.5179627, 'metadata': {'utter_action': 'utter_happy'},
                   'text': 'Great, carry on!',
                   'data': {'elements': None, 'quick_replies': None, 'buttons': None, 'attachment': None, 'image': None,
                            'custom': None}},
                  {'event': 'action', 'timestamp': 1640969981.5188172, 'name': 'action_listen',
                   'policy': 'policy_1_RulePolicy', 'confidence': 1.0, 'action_text': None, 'hide_rule_turn': True},
                  {'event': 'user', 'timestamp': 1640969987.3492067, 'text': '/restart',
                   'parse_data': {'intent': {'name': 'restart', 'confidence': 1.0}, 'entities': [], 'text': '/restart',
                                  'message_id': 'f4341cbf3eb1446e889a69d768ac091c', 'metadata': {},
                                  'intent_ranking': [{'name': 'restart', 'confidence': 1.0}]},
                   'input_channel': 'cmdline', 'message_id': 'f4341cbf3eb1446e889a69d768ac091c', 'metadata': {}},
                  {'event': 'user_featurization', 'timestamp': 1640969987.350634, 'use_text_for_featurization': False}]
        http_action_config_params = [HttpActionRequestBody(key="intent", parameter_type="intent"),
                                     HttpActionRequestBody(key="user_msg", value="", parameter_type="chat_log")]
        tracker = {"sender_id": "kairon_user@digite.com", "slot": slots, "intent": "restart",
                   "chat_log": ActionUtility.prepare_message_trail(events)[1], 'session_started': '2021-12-31 16:59:38'}
        request_params, log = ActionUtility.prepare_request(tracker, http_action_config_params=http_action_config_params, bot="test")
        assert request_params == {'intent': 'restart', 'user_msg': {'sender_id': 'kairon_user@digite.com',
                                                                    'session_started': '2021-12-31 16:59:38',
                                                                    'conversation': [{'user': 'hi'}, {
                                                                        'bot': {'text': 'are you ok?', 'elements': None,
                                                                                'quick_replies': None, 'buttons': None,
                                                                                'attachment': None, 'image': None,
                                                                                'custom': None}}, {'user': 'yes'}, {
                                                                                         'bot': {
                                                                                             'text': 'Great, carry on!',
                                                                                             'elements': None,
                                                                                             'quick_replies': None,
                                                                                             'buttons': None,
                                                                                             'attachment': None,
                                                                                             'image': None,
                                                                                             'custom': None}},
                                                                                     {'user': '/restart'}]}}
        assert log == {'intent': 'restart',
                       'user_msg': {'sender_id': 'kairon_user@digite.com', 'session_started': '2021-12-31 16:59:38',
                                    'conversation': [{'user': 'hi'}, {
                                        'bot': {'text': 'are you ok?', 'elements': None, 'quick_replies': None,
                                                'buttons': None, 'attachment': None, 'image': None, 'custom': None}},
                                                     {'user': 'yes'}, {
                                                         'bot': {'text': 'Great, carry on!', 'elements': None,
                                                                 'quick_replies': None, 'buttons': None,
                                                                 'attachment': None, 'image': None, 'custom': None}},
                                                     {'user': '/restart'}]}}

    def test_prepare_request_user_message(self):
        http_action_config_params = [HttpActionRequestBody(key="param1", value="value1"),
                                     HttpActionRequestBody(key="msg", parameter_type="user_message")]
        tracker = {"sender_id": "kairon_user@digite.com", "slot": None, "user_message": "perform google search"}
        request_params, log = ActionUtility.prepare_request(tracker, http_action_config_params=http_action_config_params, bot="test")
        assert request_params['param1'] == "value1"
        assert request_params['msg'] == "perform google search"
        assert log['param1'] == "value1"
        assert log['msg'] == "perform google search"

        tracker = {"sender_id": "kairon_user@digite.com", "slot": None}
        request_params, log = ActionUtility.prepare_request(tracker, http_action_config_params=http_action_config_params, bot="test")
        assert request_params['param1'] == "value1"
        assert not request_params['msg']
        assert log['param1'] == "value1"
        assert not log['msg']

        http_action_config_params = [HttpActionRequestBody(key="param1", value="value1"),
                                     HttpActionRequestBody(key="msg", parameter_type="user_message")]
        tracker = {"sender_id": "kairon_user@digite.com", "slot": None, "user_message": "/google_search",
                   KAIRON_USER_MSG_ENTITY: "using custom msg"}
        request_params, log = ActionUtility.prepare_request(tracker,
                                                            http_action_config_params=http_action_config_params,
                                                            bot="test")
        assert request_params['param1'] == "value1"
        assert request_params['msg'] == "using custom msg"
        assert log['param1'] == "value1"
        assert log['msg'] == "using custom msg"

        http_action_config_params = [HttpActionRequestBody(key="param1", value="value1"),
                                     HttpActionRequestBody(key="msg", parameter_type="user_message")]
        tracker = {"sender_id": "kairon_user@digite.com", "slot": None, "user_message": "perform google search",
                   KAIRON_USER_MSG_ENTITY: "using custom msg"}
        request_params, log = ActionUtility.prepare_request(tracker,
                                                            http_action_config_params=http_action_config_params,
                                                            bot="test")
        assert request_params['param1'] == "value1"
        assert request_params['msg'] == "perform google search"
        assert log['param1'] == "value1"
        assert log['msg'] == "perform google search"

    def test_prepare_request_no_request_params(self):
        slots = {"bot": "demo_bot", "http_action_config": "http_action_name", "param2": "param2value"}
        http_action_config_params: List[HttpActionRequestBody] = None
        tracker = {"sender_id": "sender1", "slot": slots}
        actual_request_body = ActionUtility.prepare_request(tracker, http_action_config_params=http_action_config_params, bot="test")
        assert actual_request_body == ({}, {})

    def test_encrypt_secrets(self):
        request_body = {"sender_id": "default", "user_message": "get intents", "intent": "test_run",
                        "user_details": {"email": "uditpandey@digite.com", "name": "udit"}}
        tracker_data = {'sender_id': 'default', 'user_message': 'get intents',
                        'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run', 'chat_log': [],
                        'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'},
                        'kairon_user_msg': None, 'session_started': None, 'bot': '5f50fd0a56b698ca10d35d2e'}

        request_body_log = ActionUtility.encrypt_secrets(request_body, tracker_data)
        assert request_body_log == {'sender_id': 'default', 'user_message': 'get intents', 'intent': 'test_run',
                                    'user_details': {'email': '*******************om', 'name': '****'}}

    def test_encrypt_secrets_different_body(self):
        request_body = {"sender_id": "default", "user_message": "get intents", "intent": "test_run",
                        "user_personal_details": {"name": "udit"},
                        "user_contact_details": {"contact_no": "9876543210", "email": "uditpandey@digite.com"}}
        tracker_data = {'sender_id': 'default', 'user_message': 'get intents',
                        'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run', 'chat_log': [],
                        'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit', "CONTACT": "9876543210"},
                        'kairon_user_msg': None, 'session_started': None, 'bot': '5f50fd0a56b698ca10d35d2e'}

        request_body_log = ActionUtility.encrypt_secrets(request_body, tracker_data)
        assert request_body_log == {'sender_id': 'default', 'user_message': 'get intents', 'intent': 'test_run',
                                    'user_personal_details': {'name': '****'}, 'user_contact_details':
                                        {'contact_no': '********10', 'email': '*******************om'}}

    def test_encrypt_secrets_with_different_key_vaults(self):
        request_body = {"sender_id": "default", "user_message": "get intents", "intent": "test_run",
                        "user_personal_details": {"name": "udit"},
                        "user_contact_details": {"contact_no": "9876543210", "email": "uditpandey@digite.com"}}
        tracker_data = {'sender_id': 'default', 'user_message': 'get intents',
                        'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run', 'chat_log': [],
                        'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'},
                        'kairon_user_msg': None, 'session_started': None, 'bot': '5f50fd0a56b698ca10d35d2e'}

        request_body_log = ActionUtility.encrypt_secrets(request_body, tracker_data)
        assert request_body_log == {'sender_id': 'default', 'user_message': 'get intents', 'intent': 'test_run',
                                    'user_personal_details': {'name': '****'}, 'user_contact_details':
                                        {'contact_no': '9876543210', 'email': '*******************om'}}

    def test_test_encrypt_secrets_with_no_key_vaults(self):
        request_body = {"sender_id": "default", "user_message": "get intents", "intent": "test_run",
                        "user_details": {"email": "uditpandey@digite.com", "name": "udit"}}
        tracker_data = {'sender_id': 'default', 'user_message': 'get intents',
                        'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run', 'chat_log': [],
                        'key_vault': {},
                        'kairon_user_msg': None, 'session_started': None, 'bot': '5f50fd0a56b698ca10d35d2e'}
        request_body_log = ActionUtility.encrypt_secrets(request_body, tracker_data)
        assert request_body_log == {'sender_id': 'default', 'user_message': 'get intents', 'intent': 'test_run',
                                    'user_details': {'email': 'uditpandey@digite.com', 'name': 'udit'}}

    def test_encrypt_secrets_without_key_vault_values(self):
        request_body = {"sender_id": "default", "user_message": "get intents", "intent": "test_run"}
        tracker_data = {'sender_id': 'default', 'user_message': 'get intents',
                        'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run', 'chat_log': [],
                        'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'},
                        'kairon_user_msg': None, 'session_started': None, 'bot': '5f50fd0a56b698ca10d35d2e'}

        request_body_log = ActionUtility.encrypt_secrets(request_body, tracker_data)
        assert request_body_log == {'sender_id': 'default', 'user_message': 'get intents', 'intent': 'test_run'}

    def test_is_empty(self):
        assert ActionUtility.is_empty("")
        assert ActionUtility.is_empty("  ")
        assert ActionUtility.is_empty(None)
        assert not ActionUtility.is_empty("None")

    def test_prepare_response(self):
        json1 = {
            "a": {
                "b": {
                    "3": 2,
                    "43": 30,
                    "c": [],
                    "d": ['red', 'buggy', 'bumpers'],
                }
            }
        }
        http_response = {"data": json1, "context": {}}
        response = ActionUtility.prepare_response("The value of ${data.a.b.3} in ${data.a.b.d.0} is ${data.a.b.c}",
                                                  http_response)
        assert response == 'The value of 2 in red is []'

        json2 = {
            "data": [
                {"a": {
                    "b": {
                        "43": 30,
                        "c": [],
                        "d": ['red', 'buggy', 'bumpers'],
                    }}},
                {"a": {
                    "b": {
                        "43": 5,
                        "c": [1, 2],
                        "d": ['buggy', 'bumpers'],
                    }}}
            ]
        }
        response = ActionUtility.prepare_response("The value of ${data.0.a} in ${data.0.a.b} is ${data.0.a.b.d}", json2)
        assert response == 'The value of {"b": {"43": 30, "c": [], "d": ["red", "buggy", "bumpers"]}} in {"43": 30, "c": [], "d": ["red", "buggy", "bumpers"]} is [\'red\', \'buggy\', \'bumpers\']'

    def test_prepare_response_key_not_present(self):
        json1 = json.dumps({
            "a": {
                "b": {
                    "3": 2,
                    "43": 30,
                    "c": [],
                    "d": ['red', 'buggy', 'bumpers'],
                }
            }
        })
        http_response = {"data": json1, "context": {}}
        try:
            ActionUtility.prepare_response("The value of ${a.b.3} in ${a.b.d.0} is ${a.b.e}", http_response)
            assert False
        except ActionFailure:
            assert True

    def test_prepare_response_string_response(self):
        json1 = json.dumps({
            "a": {
                "b": {
                    "3": 2,
                    "43": 30,
                    "c": [],
                    "d": ['red', 'buggy', 'bumpers'],
                }
            }
        })
        http_response = {"data": json1, "context": {}}
        response = ActionUtility.prepare_response("The value of red is 0", http_response)
        assert response == "The value of red is 0"

    def test_prepare_response_string_empty_response_string(self):
        json1 = json.dumps({
            "a": {
                "b": {
                    "3": 2,
                    "43": 30,
                    "c": [],
                    "d": ['red', 'buggy', 'bumpers'],
                }
            }
        })
        http_response = {"data": json1, "context": {}}
        response = ActionUtility.prepare_response("", http_response)
        assert response == {'data': '{"a": {"b": {"3": 2, "43": 30, "c": [], "d": ["red", "buggy", "bumpers"]}}}',
                            'context': {}}

    def test_prepare_response_string_empty_request_output(self):
        json1 = json.dumps("{}")
        http_response = {"data": json1, "context": {}}
        try:
            ActionUtility.prepare_response("The value of ${a.b.3} in ${a.b.d.0} is ${a.b.e}", http_response)
            assert False
        except ActionFailure:
            assert True

    def test_prepare_response_invalid_response_json(self):
        json_as_string = "Not a json string"
        try:
            ActionUtility.prepare_response("The value of ${a.b.3} in ${a.b.d.0} is ${a.b.c}", json_as_string)
            assert False
        except ActionFailure as e:
            assert str(e) == 'Could not find value for keys in response'

    def test_prepare_response_as_json_and_expected_as_plain_string(self):
        json_as_string = "Not a json string"
        http_response = {"data": json_as_string, "context": {}}
        response = ActionUtility.prepare_response("The value of 2 in red is []", http_response)
        assert response == 'The value of 2 in red is []'

    def test_prepare_response_as_string_and_expected_as_none(self):
        http_response = {"data": None, "context": {}}
        response = ActionUtility.prepare_response("The value of 2 in red is []", http_response)
        assert response == 'The value of 2 in red is []'

    @pytest.mark.asyncio
    async def test_run_invalid_http_action(self, mock_get_http_action_exception):
        slots = {"bot": "5f50fd0a56b698ca10d35d2e",
                 "param2": "param2value"}
        events = [{"event1": "hello"}, {"event2": "how are you"}]
        latest_message = {'text': 'get intents', 'intent_ranking': [{'name': 'http_action'}]}
        actions_name = "test_run_invalid_http_action1"
        HttpActionConfig(
            action_name=actions_name,
            response=HttpActionResponse(value="json"),
            http_url="http://www.google.com",
            request_method="GET",
            params_list=None,
            bot="5f50fd0a56b698ca10d35d2e",
            user="user"
        ).save()
        dispatcher: CollectingDispatcher = CollectingDispatcher()
        tracker = Tracker(sender_id="sender1", slots=slots, events=events, paused=False, latest_message=latest_message,
                          followup_action=None, active_loop=None, latest_action_name=None)
        domain: Dict[Text, Any] = None
        await ActionProcessor.process_action(dispatcher, tracker, domain, actions_name)
        log = ActionServerLogs.objects(sender="sender1",
                                       bot="5f50fd0a56b698ca10d35d2e",
                                       status="FAILURE").get()
        assert log['exception'].__contains__('No action found for given bot and name')

    @pytest.mark.asyncio
    async def test_run_no_bot(self):
        action_name = "new_http_action"
        slots = {"bot": None, "param2": "param2value"}
        events = [{"event1": "hello"}, {"event2": "how are you"}]
        dispatcher: CollectingDispatcher = CollectingDispatcher()
        latest_message = {'text': 'get intents', 'intent_ranking': [{'name': 'http_action'}]}
        tracker = Tracker(sender_id="sender2", slots=slots, events=events, paused=False, latest_message=latest_message,
                          followup_action=None, active_loop=None, latest_action_name=None)
        domain: Dict[Text, Any] = None
        actual: List[Dict[Text, Any]] = await ActionProcessor.process_action(dispatcher, tracker, domain, action_name)
        assert actual is None
        log = ActionServerLogs.objects(sender="sender2",
                                       status="FAILURE").get()
        assert log['exception'] == 'Bot id and action name not found in slot'

    @pytest.mark.asyncio
    async def test_run_no_http_action(self):
        action_name = None
        slots = {"bot": "jhgfsjgfausyfgus", "param2": "param2value"}
        events = [{"event1": "hello"}, {"event2": "how are you"}]
        dispatcher: CollectingDispatcher = CollectingDispatcher()
        latest_message = {'text': 'get intents', 'intent_ranking': [{'name': 'http_action'}]}
        tracker = Tracker(sender_id="sender1", slots=slots, events=events, paused=False, latest_message=latest_message,
                          followup_action=None, active_loop=None, latest_action_name=None)
        domain: Dict[Text, Any] = None
        actual: List[Dict[Text, Any]] = await ActionProcessor.process_action(dispatcher, tracker, domain, action_name)
        assert actual is None

    @pytest.mark.asyncio
    async def test_run(self, monkeypatch):
        http_url = "http://www.google.com"
        http_response = "This should be response"
        action = HttpActionConfig(
            action_name="http_action",
            response=HttpActionResponse(value=http_response),
            http_url=http_url,
            request_method="GET",
            params_list=None,
            bot="5f50fd0a56b698ca10d35d2e",
            user="user"
        )

        def _get_action(*args, **kwargs):
            return {"type": ActionType.http_action.value}

        monkeypatch.setattr(ActionUtility, "get_action", _get_action)
        responses.reset()
        responses.start()
        responses.add(
            method=responses.GET,
            url=http_url,
            body=http_response,
            status=200,
        )

        action_name = "http_action"
        slots = {"bot": "5f50fd0a56b698ca10d35d2e",
                 "param2": "param2value"}
        events = [{"event1": "hello"}, {"event2": "how are you"}]
        dispatcher: CollectingDispatcher = CollectingDispatcher()
        latest_message = {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]}
        tracker = Tracker(sender_id="sender_test_run", slots=slots, events=events, paused=False,
                          latest_message=latest_message,
                          followup_action=None, active_loop=None, latest_action_name=None)
        domain: Dict[Text, Any] = None
        action.save().to_mongo().to_dict()
        actual: List[Dict[Text, Any]] = await ActionProcessor.process_action(dispatcher, tracker, domain, action_name)
        assert actual is not None
        assert str(actual[0]['name']) == 'kairon_action_response'
        assert str(actual[0]['value']) == 'This should be response'
        log = ActionServerLogs.objects(sender="sender_test_run",
                                       status="SUCCESS").get()
        assert not log['exception']
        assert log['timestamp']
        assert log['intent']
        assert log['action']
        assert log['bot_response']
        assert log['api_response']

    @pytest.mark.asyncio
    async def test_run_with_params(self, monkeypatch):
        http_url = "http://www.google.com/$SENDER_ID?id=$param2"
        http_response = "This should be response"
        request_params = [HttpActionRequestBody(key='key1', value="value1"),
                          HttpActionRequestBody(key='key2', value="value2")]
        action = HttpActionConfig(
            action_name="http_action_with_params",
            response=HttpActionResponse(value=http_response),
            http_url=http_url,
            request_method="GET",
            params_list=request_params,
            bot="5f50fd0a56b698ca10d35d2e",
            user="user"
        )

        def _get_action(*args, **kwargs):
            return {"type": ActionType.http_action.value}

        monkeypatch.setattr(ActionUtility, "get_action", _get_action)
        responses.reset()
        responses.start()
        responses.add(
            method=responses.GET,
            url="http://www.google.com/sender_test_run_with_params?id=param2value",
            body=http_response,
            status=200,
        )

        action_name = "http_action_with_params"
        slots = {"bot": "5f50fd0a56b698ca10d35d2e",
                 "param2": "param2value"}
        events = [{"event1": "hello"}, {"event2": "how are you"}]
        dispatcher: CollectingDispatcher = CollectingDispatcher()
        latest_message = {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]}
        tracker = Tracker(sender_id="sender_test_run_with_params", slots=slots, events=events, paused=False,
                          latest_message=latest_message,
                          followup_action=None, active_loop=None, latest_action_name=None)
        domain: Dict[Text, Any] = None
        action.save().to_mongo().to_dict()
        actual: List[Dict[Text, Any]] = await ActionProcessor.process_action(dispatcher, tracker, domain, action_name)
        assert actual is not None
        assert str(actual[0]['name']) == 'kairon_action_response'
        assert str(actual[0]['value']) == 'This should be response'
        log = ActionServerLogs.objects(sender="sender_test_run_with_params",
                                       status="SUCCESS").get()
        assert not log['exception']
        assert log['timestamp']
        assert log['intent']
        assert log['action']
        assert log['bot_response']
        assert log['api_response']
        assert log['url'] == "http://www.google.com/sender_test_run_with_params?id=param2value"
        assert log['request_params'] == {'key1': 'value1', 'key2': 'value2'}

    @pytest.mark.asyncio
    async def test_run_with_dynamic_params(self, monkeypatch):
        http_url = "http://localhost:8080/mock"
        http_response = "This should be response"
        dynamic_params = \
            "{\"sender_id\": \"${sender_id}\", \"user_message\": \"${user_message}\", \"intent\": \"${intent}\"}"
        action = HttpActionConfig(
            action_name="test_run_with_dynamic_params",
            response=HttpActionResponse(value=http_response),
            http_url=http_url,
            request_method="GET",
            dynamic_params=dynamic_params,
            bot="5f50fd0a56b698ca10d35d2e",
            user="user"
        )

        def _get_action(*args, **kwargs):
            return {"type": ActionType.http_action.value}

        monkeypatch.setattr(ActionUtility, "get_action", _get_action)
        responses.reset()
        responses.start()
        resp_msg = {"sender_id": "default_sender", "user_message": "get intents", "intent": "test_run"}
        responses.add(
            method=responses.POST,
            url=Utility.environment['evaluator']['url'],
            json={"success": True, "data": resp_msg},
            status=200,
        )
        responses.add(
            method=responses.GET,
            url="http://localhost:8080/mock",
            body=http_response,
            status=200,
        )

        action_name = "test_run_with_dynamic_params"
        slots = {"bot": "5f50fd0a56b698ca10d35d2e",
                 "param2": "param2value"}
        events = [{"event1": "hello"}, {"event2": "how are you"}]
        dispatcher: CollectingDispatcher = CollectingDispatcher()
        latest_message = {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]}
        tracker = Tracker(sender_id="default_sender", slots=slots, events=events, paused=False,
                          latest_message=latest_message,
                          followup_action=None, active_loop=None, latest_action_name=None)
        domain: Dict[Text, Any] = None
        action.save().to_mongo().to_dict()
        actual: List[Dict[Text, Any]] = await ActionProcessor.process_action(dispatcher, tracker, domain, action_name)
        assert actual is not None
        assert str(actual[0]['name']) == 'kairon_action_response'
        assert str(actual[0]['value']) == 'This should be response'
        log = ActionServerLogs.objects(sender="default_sender",
                                       status="SUCCESS").get()
        print(log.to_mongo().to_dict())
        assert not log['exception']
        assert log['timestamp']
        assert log['intent']
        assert log['action']
        assert log['bot_response']
        assert log['api_response']
        assert log['status']
        assert log['url'] == "http://localhost:8080/mock"
        assert log['request_params'] == {'sender_id': 'default_sender', 'user_message': 'get intents',
                                         'intent': 'test_run'}

    @pytest.mark.asyncio
    async def test_run_with_post(self, monkeypatch):
        action = HttpActionConfig(
            action_name="test_run_with_post",
            response=HttpActionResponse(value="Data added successfully, id:${data}"),
            http_url="http://localhost:8080/mock",
            request_method="POST",
            params_list=None,
            bot="5f50fd0a56b698ca10d35d2e",
            user="user"
        )

        def _get_action(*args, **kwargs):
            return {"type": ActionType.http_action.value}

        monkeypatch.setattr(ActionUtility, "get_action", _get_action)
        http_url = 'http://localhost:8080/mock'
        resp_msg = "5000"
        responses.reset()
        responses.start()
        responses.add(
            method=responses.POST,
            url=http_url,
            body=resp_msg,
            status=200,
        )

        slots = {"bot": "5f50fd0a56b698ca10d35d2e"}
        events = [{"event1": "hello"}, {"event2": "how are you"}]
        dispatcher: CollectingDispatcher = CollectingDispatcher()
        latest_message = {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]}
        tracker = Tracker(sender_id="sender1", slots=slots, events=events, paused=False, latest_message=latest_message,
                          followup_action=None, active_loop=None, latest_action_name=None)
        domain: Dict[Text, Any] = None
        action.save().to_mongo().to_dict()
        actual: List[Dict[Text, Any]] = await ActionProcessor.process_action(dispatcher, tracker, domain,
                                                                             "test_run_with_post")
        assert actual is not None
        assert actual[0]['name'] == 'kairon_action_response'
        assert actual[0]['value'] == 'Data added successfully, id:5000'

    @pytest.mark.asyncio
    async def test_run_with_post_and_parameters(self, monkeypatch):
        request_params = [HttpActionRequestBody(key='key1', value="value1"),
                          HttpActionRequestBody(key='key2', value="value2")]
        action = HttpActionConfig(
            action_name="test_run_with_post_and_parameters",
            response=HttpActionResponse(value="Data added successfully, id:${data}"),
            http_url="http://localhost:8080/mock",
            request_method="POST",
            params_list=request_params,
            bot="5f50fd0a56b698ca10d35d2e",
            user="user"
        )

        def _get_action(*args, **kwargs):
            return {"type": ActionType.http_action.value}

        monkeypatch.setattr(ActionUtility, "get_action", _get_action)

        http_url = 'http://localhost:8080/mock'
        resp_msg = "5000"
        responses.reset()
        responses.start()
        responses.add(
            method=responses.POST,
            url=http_url,
            body=resp_msg,
            status=200,
        )

        slots = {"bot": "5f50fd0a56b698ca10d35d2e"}
        events = [{"event1": "hello"}, {"event2": "how are you"}]
        dispatcher: CollectingDispatcher = CollectingDispatcher()
        latest_message = {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]}
        tracker = Tracker(sender_id="sender_test_run_with_post", slots=slots, events=events, paused=False,
                          latest_message=latest_message,
                          followup_action=None, active_loop=None, latest_action_name=None)
        domain: Dict[Text, Any] = None
        action.save().to_mongo().to_dict()
        actual: List[Dict[Text, Any]] = await ActionProcessor.process_action(dispatcher, tracker, domain,
                                                                             "test_run_with_post_and_parameters")
        responses.stop()
        responses.reset()
        assert actual is not None
        assert str(actual[0]['name']) == 'kairon_action_response'
        assert str(actual[0]['value']) == 'Data added successfully, id:5000'
        log = ActionServerLogs.objects(sender="sender_test_run_with_post",
                                       action="test_run_with_post_and_parameters",
                                       status="SUCCESS").get()
        assert not log['exception']
        assert log['timestamp']
        assert log['intent'] == "test_run"
        assert log['action'] == "test_run_with_post_and_parameters"
        assert log['request_params'] == {"key1": "value1", "key2": "value2"}
        assert log['api_response'] == '5000'
        assert log['bot_response'] == 'Data added successfully, id:5000'

    @pytest.mark.asyncio
    async def test_run_with_post_and_dynamic_params(self, monkeypatch):
        dynamic_params = \
            "{\"sender_id\": \"${sender_id}\", \"user_message\": \"${user_message}\", \"intent\": \"${intent}\"}"
        action = HttpActionConfig(
            action_name="test_run_with_post_and_dynamic_params",
            response=HttpActionResponse(value="Data added successfully, id:${data}"),
            http_url="http://localhost:8080/mock",
            request_method="POST",
            dynamic_params=dynamic_params,
            bot="5f50fd0a56b698ca10d35d2e",
            user="user"
        )

        def _get_action(*args, **kwargs):
            return {"type": ActionType.http_action.value}

        monkeypatch.setattr(ActionUtility, "get_action", _get_action)
        responses.reset()
        responses.start()
        resp_msg = {"sender_id": "default_sender", "user_message": "get intents", "intent": "test_run"}
        responses.add(
            method=responses.POST,
            url=Utility.environment['evaluator']['url'],
            json={"success": True, "data": resp_msg},
            status=200,
        )
        http_url = 'http://localhost:8080/mock'
        resp_msg = "5000"
        responses.add(
            method=responses.POST,
            url=http_url,
            body=resp_msg,
            status=200,
        )

        slots = {"bot": "5f50fd0a56b698ca10d35d2e"}
        events = [{"event1": "hello"}, {"event2": "how are you"}]
        dispatcher: CollectingDispatcher = CollectingDispatcher()
        latest_message = {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]}
        tracker = Tracker(sender_id="default_sender", slots=slots, events=events, paused=False,
                          latest_message=latest_message,
                          followup_action=None, active_loop=None, latest_action_name=None)
        domain: Dict[Text, Any] = None
        action.save().to_mongo().to_dict()
        actual: List[Dict[Text, Any]] = await ActionProcessor.process_action(dispatcher, tracker, domain,
                                                                             "test_run_with_post_and_dynamic_params")
        responses.stop()
        responses.reset()
        assert actual is not None
        assert str(actual[0]['name']) == 'kairon_action_response'
        assert str(actual[0]['value']) == 'Data added successfully, id:5000'
        log = ActionServerLogs.objects(sender="default_sender",
                                       action="test_run_with_post_and_dynamic_params",
                                       status="SUCCESS").get()
        assert not log['exception']
        assert log['timestamp']
        assert log['intent'] == "test_run"
        assert log['action'] == "test_run_with_post_and_dynamic_params"
        assert log['request_params'] == {'sender_id': 'default_sender', 'user_message': 'get intents',
                                         'intent': 'test_run'}
        assert log['api_response'] == '5000'
        assert log['bot_response'] == 'Data added successfully, id:5000'

    @pytest.mark.asyncio
    async def test_run_with_get(self, monkeypatch):
        action = HttpActionConfig(
            action_name="test_run_with_get",
            response=HttpActionResponse(value="The value of ${data.a.b.3} in ${data.a.b.d.0} is ${data.a.b.d}"),
            http_url="http://localhost:8081/mock",
            request_method="GET",
            params_list=None,
            bot="5f50fd0a56b698ca10d35d2e",
            user="user"
        )

        def _get_action(*args, **kwargs):
            return {"type": ActionType.http_action.value}

        monkeypatch.setattr(ActionUtility, "get_action", _get_action)
        http_url = 'http://localhost:8081/mock'
        responses.reset()
        responses.start()
        resp_msg = json.dumps({
            "a": {
                "b": {
                    "3": 2,
                    "43": 30,
                    "c": [],
                    "d": ['red', 'buggy', 'bumpers'],
                }
            }
        })
        responses.add(
            method=responses.GET,
            url=http_url,
            body=resp_msg,
            status=200,
        )
        slots = {"bot": "5f50fd0a56b698ca10d35d2e"}
        events = [{"event1": "hello"}, {"event2": "how are you"}]
        dispatcher: CollectingDispatcher = CollectingDispatcher()
        latest_message = {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]}
        tracker = Tracker(sender_id="sender1", slots=slots, events=events, paused=False, latest_message=latest_message,
                          followup_action=None, active_loop=None, latest_action_name=None)
        domain: Dict[Text, Any] = None
        action.save().to_mongo().to_dict()
        actual: List[Dict[Text, Any]] = await ActionProcessor.process_action(dispatcher, tracker, domain,
                                                                             "test_run_with_get")
        responses.stop()
        responses.reset()
        assert actual is not None
        assert str(actual[0]['name']) == 'kairon_action_response'
        assert str(actual[0]['value']) == 'The value of 2 in red is [\'red\', \'buggy\', \'bumpers\']'

    @pytest.mark.asyncio
    async def test_run_with_get_dispatch_type_text_with_json_response(self, monkeypatch):
        action = HttpActionConfig(
            action_name="test_run_with_get_with_json_response",
            response=HttpActionResponse(value="'The value of '+`${a.b.d}`+' in '+`${a.b.d.0}`+' is '+`${a.b.d}`",
                                        dispatch=True, evaluation_type="script"),
            http_url="http://localhost:8081/mock",
            request_method="GET",
            params_list=None,
            bot="5f50fd0a56b698ca10d35d2e",
            user="user"
        )
        KeyVault(key="EMAIL", value="uditpandey@digite.com", bot="5f50fd0a56b698ca10d35d2e", user="user").save()
        KeyVault(key="FIRSTNAME", value="udit", bot="5f50fd0a56b698ca10d35d2e", user="user").save()
        KeyVault(key="API_KEY", value="asdfghjkertyuio", bot="5f50fd0a56b698ca10d35d2e", user="user").save()
        KeyVault(key="API_SECRET", value="sdfghj345678dfghj", bot="5f50fd0a56b698ca10d35d2e", user="user").save()

        def _get_action(*args, **kwargs):
            return {"type": ActionType.http_action.value}

        monkeypatch.setattr(ActionUtility, "get_action", _get_action)
        http_url = 'http://localhost:8081/mock'
        responses.reset()
        responses.start()
        resp_msg = json.dumps({
            "a": {
                "b": {
                    "3": 2,
                    "43": 30,
                    "c": [],
                    "d": ['red', 'buggy', 'bumpers'],
                }
            }
        })
        responses.add(
            method=responses.GET,
            url=http_url,
            body=resp_msg,
            status=200,
        )
        responses.add(
            method=responses.POST,
            url=Utility.environment['evaluator']['url'],
            json={"success": True, "data": {"key": "name", "value": "Mahesh"}},
            status=200,
            match=[
                responses.matchers.json_params_matcher(
                    {'script': "'The value of '+`${a.b.d}`+' in '+`${a.b.d.0}`+' is '+`${a.b.d}`",
                     'data': {'data': {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}},
                              'context': {'sender_id': 'default_sender', 'user_message': 'get intents',
                                          'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run',
                                          'chat_log': [],
                                          'key_vault': {'API_KEY': 'asdfghjkertyuio', 'API_SECRET': 'sdfghj345678dfghj',
                                                        'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'},
                                          'kairon_user_msg': None,
                                          'session_started': None, 'bot': '5f50fd0a56b698ca10d35d2e'}}})],
        )
        slots = {"bot": "5f50fd0a56b698ca10d35d2e"}
        events = [{"event1": "hello"}, {"event2": "how are you"}]
        dispatcher: CollectingDispatcher = CollectingDispatcher()
        latest_message = {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]}
        tracker = Tracker(sender_id="default_sender", slots=slots, events=events, paused=False, latest_message=latest_message,
                          followup_action=None, active_loop=None, latest_action_name=None)
        domain: Dict[Text, Any] = None
        action.save().to_mongo().to_dict()
        actual: List[Dict[Text, Any]] = await ActionProcessor.process_action(dispatcher, tracker, domain,
                                                                             "test_run_with_get_with_json_response")
        responses.stop()
        responses.reset()
        assert actual is not None
        assert str(actual[0]['name']) == 'kairon_action_response'
        assert str(actual[0]['value']) == "{'key': 'name', 'value': 'Mahesh'}"
        log = ActionServerLogs.objects(sender="default_sender",
                                       action="test_run_with_get_with_json_response",
                                       status="SUCCESS").get()
        print(log.to_mongo().to_dict())
        assert not log['exception']
        assert log['timestamp']
        assert log['intent'] == "test_run"
        assert log['action'] == "test_run_with_get_with_json_response"
        assert log['api_response'] == "{'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}"
        assert log['bot_response'] == "{'key': 'name', 'value': 'Mahesh'}"

    @pytest.mark.asyncio
    async def test_run_with_get_with_dynamic_params(self, monkeypatch):
        dynamic_params = "{\"sender_id\": \"${sender_id}\", \"user_message\": \"${user_message}\", "\
                         "\"intent\": \"${intent}\", \"EMAIL\": \"${key_vault.EMAIL}\"}"
        KeyVault(key="EMAIL", value="uditpandey@digite.com", bot="5f50fd0a56b698ca10d35d2e", user="user").save()
        KeyVault(key="FIRSTNAME", value="udit", bot="5f50fd0a56b698ca10d35d2e", user="user").save()
        KeyVault(key="API_KEY", value="asdfghjkertyuio", bot="5f50fd0a56b698ca10d35d2e", user="user").save()
        KeyVault(key="API_SECRET", value="sdfghj345678dfghj", bot="5f50fd0a56b698ca10d35d2e", user="user").save()
        action = HttpActionConfig(
            action_name="test_run_with_get_with_dynamic_params",
            response=HttpActionResponse(value="The value of ${data.a.b.3} in ${data.a.b.d.0} is ${data.a.b.d}"),
            http_url="http://localhost:8081/mock",
            request_method="GET",
            dynamic_params=dynamic_params,
            set_slots=[SetSlotsFromResponse(name="val_d", value="${a.b.d}", evaluation_type="script"),
                       SetSlotsFromResponse(name="val_d_0", value="${a.b.d.0}", evaluation_type="script")],
            bot="5f50fd0a56b698ca10d35d2e",
            user="user"
        )

        def _get_action(*args, **kwargs):
            return {"type": ActionType.http_action.value}

        monkeypatch.setattr(ActionUtility, "get_action", _get_action)
        responses.reset()
        responses.start()
        resp_msg = {
            "sender_id": "default_sender",
            "user_message": "get intents",
            "intent": "test_run",
            "EMAIL": "uditpandey@digite.com"
        }
        responses.add(
            method=responses.POST,
            url=Utility.environment['evaluator']['url'],
            json={"success": True, "data": resp_msg},
            status=200,
        )
        http_url = 'http://localhost:8081/mock'
        resp_msg = json.dumps({
            "a": {
                "b": {
                    "3": 2,
                    "43": 30,
                    "c": [],
                    "d": ['red', 'buggy', 'bumpers'],
                }
            }
        })
        responses.add(
            method=responses.GET,
            url=http_url,
            body=resp_msg,
            status=200,
        )
        responses.add(
            method=responses.POST,
            url=Utility.environment['evaluator']['url'],
            json={"success": True, "data": "The value of 2 in red is ['red', 'buggy', 'bumpers']"},
            status=200,
            match=[
                responses.matchers.json_params_matcher(
                    {'script': "'The value of '+`${a.b.d}`+' in '+`${a.b.d.0}`+' is '+`${a.b.d}`",
                     'data': {'data': {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}},
                              'context': {'sender_id': 'default_sender', 'user_message': 'get intents',
                                          'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run',
                                          'chat_log': [],
                                          'key_vault': {'API_KEY': 'asdfghjkertyuio', 'API_SECRET': 'sdfghj345678dfghj',
                                                        'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'},
                                          'kairon_user_msg': None, 'session_started': None,
                                          'bot': '5f50fd0a56b698ca10d35d2e'}}})],
        )
        responses.add(
            method=responses.POST,
            url=Utility.environment['evaluator']['url'],
            json={"success": True, "data": "['red', 'buggy', 'bumpers']"},
            status=200,
            match=[
                responses.matchers.json_params_matcher(
                    {'script': "${a.b.d}",
                     'data': {'data': {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}},
                              'context': {'sender_id': 'default_sender', 'user_message': 'get intents',
                                          'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run',
                                          'chat_log': [],
                                          'key_vault': {'API_KEY': 'asdfghjkertyuio', 'API_SECRET': 'sdfghj345678dfghj',
                                                        'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'},
                                          'kairon_user_msg': None, 'session_started': None,
                                          'bot': '5f50fd0a56b698ca10d35d2e'}}})],
        )
        responses.add(
            method=responses.POST,
            url=Utility.environment['evaluator']['url'],
            json={"success": True, "data": "red"},
            status=200,
            match=[
                responses.matchers.json_params_matcher(
                    {'script': "${a.b.d.0}",
                     'data': {'data': {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}},
                              'context': {'sender_id': 'default_sender', 'user_message': 'get intents',
                                          'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run',
                                          'chat_log': [],
                                          'key_vault': {'API_KEY': 'asdfghjkertyuio', 'API_SECRET': 'sdfghj345678dfghj',
                                                        'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'},
                                          'kairon_user_msg': None, 'session_started': None,
                                          'bot': '5f50fd0a56b698ca10d35d2e'}}})],
        )
        slots = {"bot": "5f50fd0a56b698ca10d35d2e"}
        events = [{"event1": "hello"}, {"event2": "how are you"}]
        dispatcher: CollectingDispatcher = CollectingDispatcher()
        latest_message = {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]}
        tracker = Tracker(sender_id="default_sender", slots=slots, events=events, paused=False,
                          latest_message=latest_message,followup_action=None, active_loop=None, latest_action_name=None)
        domain: Dict[Text, Any] = None
        action.save().to_mongo().to_dict()
        actual: List[Dict[Text, Any]] = await ActionProcessor.process_action(dispatcher, tracker, domain,
                                                                             "test_run_with_get_with_dynamic_params")
        responses.stop()
        assert actual is not None
        assert str(actual[0]['name']) == 'val_d'
        assert str(actual[0]['value']) == "['red', 'buggy', 'bumpers']"
        assert str(actual[1]['name']) == 'val_d_0'
        assert str(actual[1]['value']) == "red"
        assert str(actual[2]['name']) == 'kairon_action_response'
        assert str(actual[2]['value']) == 'The value of 2 in red is [\'red\', \'buggy\', \'bumpers\']'
        log = ActionServerLogs.objects(sender="default_sender",
                                       action="test_run_with_get_with_dynamic_params",
                                       status="SUCCESS").get()
        print(log.to_mongo().to_dict())
        assert not log['exception']
        assert log['timestamp']
        assert log['intent'] == "test_run"
        assert log['action'] == "test_run_with_get_with_dynamic_params"
        assert log['request_params'] == {'sender_id': 'default_sender', 'user_message': 'get intents',
                                         'intent': 'test_run', 'EMAIL': '*******************om'}
        assert log['api_response'] == "{'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}"
        assert log['bot_response'] == "The value of 2 in red is ['red', 'buggy', 'bumpers']"

    @pytest.mark.asyncio
    async def test_run_no_connection(self, monkeypatch):
        action_name = "test_run_with_post"
        action = HttpActionConfig(
            action_name=action_name,
            response=HttpActionResponse(value="This should be response"),
            http_url="http://localhost:8085/mock",
            request_method="GET",
            params_list=None,
            bot="5f50fd0a56b698ca10d35d2e",
            user="user"
        )

        def _get_action(*args, **kwargs):
            return {"type": ActionType.http_action.value}

        monkeypatch.setattr(ActionUtility, "get_action", _get_action)
        slots = {"bot": "5f50fd0a56b698ca10d35d2e"}
        events = [{"event1": "hello"}, {"event2": "how are you"}]
        dispatcher: CollectingDispatcher = CollectingDispatcher()
        latest_message = {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]}
        tracker = Tracker(sender_id="sender1", slots=slots, events=events, paused=False, latest_message=latest_message,
                          followup_action=None, active_loop=None, latest_action_name=None)
        domain: Dict[Text, Any] = None
        action.save()
        actual: List[Dict[Text, Any]] = await ActionProcessor.process_action(dispatcher, tracker, domain, action_name)
        assert actual is not None
        assert str(actual[0]['name']) == 'kairon_action_response'
        assert str(actual[0]['value']).__contains__('I have failed to process your request')

    @pytest.mark.asyncio
    async def test_run_with_get_placeholder_vs_string_response(self, monkeypatch):
        action_name = "test_run_with_get_string_http_response_placeholder_required"
        action = HttpActionConfig(
            action_name=action_name,
            response=HttpActionResponse(value="The value of ${a.b.3} in ${a.b.d.0} is ${a.b.d}"),
            http_url="http://localhost:8080/mock",
            request_method="GET",
            params_list=None,
            bot="5f50fd0a56b698ca10d35d2e",
            user="user"
        )

        def _get_action(*args, **kwargs):
            return {"type": ActionType.http_action.value}

        monkeypatch.setattr(ActionUtility, "get_action", _get_action)
        http_url = 'http://localhost:8082/mock'
        resp_msg = "This is string http response"
        responses.start()
        responses.add(
            method=responses.GET,
            url=http_url,
            body=resp_msg,
            status=200,
        )

        slots = {"bot": "5f50fd0a56b698ca10d35d2e"}
        events = [{"event1": "hello"}, {"event2": "how are you"}]
        dispatcher: CollectingDispatcher = CollectingDispatcher()
        latest_message = {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]}
        tracker = Tracker(sender_id="sender1", slots=slots, events=events, paused=False, latest_message=latest_message,
                          followup_action=None, active_loop=None, latest_action_name=None)
        domain: Dict[Text, Any] = None
        action.save().to_mongo().to_dict()
        actual: List[Dict[Text, Any]] = await ActionProcessor.process_action(dispatcher, tracker, domain, action_name)
        responses.stop()
        assert actual is not None
        assert str(actual[0]['name']) == 'kairon_action_response'
        assert str(
            actual[0]['value']) == 'I have failed to process your request'

    def test_attach_response_no_placeholder(self):
        http_response = {"data": {"a": "b"}, "context": {}}
        output = ActionUtility.attach_response("This has no placeholder", http_response)
        assert output == "This has no placeholder"

    def test_attach_response(self):
        http_response = {"data": {"dollars": "51"}, "context": {}}
        output = ActionUtility.attach_response("I want $${RESPONSE}", http_response)
        assert output == 'I want ${\"dollars\": \"51\"}'

    def test_attach_response_int(self):
        output = ActionUtility.attach_response("I want $${RESPONSE}", 51)
        assert output == 'I want $51'

    def test_prepare_response_with_prefix(self):
        http_response = {"data": {"price": [{"dollars": "51"}, {"rupee": "151"}]}, "context": {}}
        output = ActionUtility.prepare_response("I want rupee${data.price.1.rupee}. Also, want $${data.price.0.dollars}",
                                                http_response)
        assert output == 'I want rupee151. Also, want $51'

    def test_retrieve_value_from_response(self):
        keys = ["a.b.3", 'a.b']
        resp_msg = {
            "a": {
                "b": {
                    "3": 2,
                    "43": 30,
                    "c": [],
                    "d": ['red', 'buggy', 'bumpers'],
                }
            }
        }
        key_values = ActionUtility.retrieve_value_from_response(keys, resp_msg)
        assert key_values is not None
        assert key_values['${a.b.3}'] == 2
        assert key_values['${a.b}'] is not None
        assert key_values['${a.b}']['3'] == 2
        assert key_values['${a.b}']['d'][0] == 'red'

    def test_retrieve_value_from_response_invalid_key(self):
        keys = ["d.e.f", 'g.h']
        resp_msg = {
            "a": {
                "b": {
                    "3": 2,
                    "43": 30,
                    "c": [],
                    "d": ['red', 'buggy', 'bumpers'],
                }
            }
        }
        try:
            ActionUtility.retrieve_value_from_response(keys, resp_msg)
            assert False
        except ActionFailure as e:
            assert str(e) == 'Unable to retrieve value for key from HTTP response: \'d\''

    @responses.activate
    @pytest.mark.asyncio
    async def test_run_get_with_parameters(self, monkeypatch):
        request_params = [HttpActionRequestBody(key='key1', value="value1"),
                          HttpActionRequestBody(key='key2', value="value2")]
        action = HttpActionConfig(
            action_name="test_run_get_with_parameters",
            response=HttpActionResponse(value="The value of ${data.a.b.3} in ${data.a.b.d.0} is ${data.a.b.d}"),
            http_url="http://localhost:8081/mock",
            request_method="GET",
            params_list=request_params,
            bot="5f50fd0a56b698ca10d35d2e",
            user="user"
        )

        def _get_action(*args, **kwargs):
            return {"type": ActionType.http_action.value}

        monkeypatch.setattr(ActionUtility, "get_action", _get_action)
        http_url = 'http://localhost:8081/mock'
        resp_msg = {
            "a": {
                "b": {
                    "3": 2,
                    "43": 30,
                    "c": [],
                    "d": ['red', 'buggy', 'bumpers'],
                }
            }
        }

        responses.add(
            responses.GET, http_url, json=resp_msg,
            match=[responses.matchers.urlencoded_params_matcher({'key1': 'value1', 'key2': 'value2'})],
        )

        slots = {"bot": "5f50fd0a56b698ca10d35d2e"}
        events = [{"event1": "hello"}, {"event2": "how are you"}]
        dispatcher: CollectingDispatcher = CollectingDispatcher()
        latest_message = {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]}
        tracker = Tracker(sender_id="sender1", slots=slots, events=events, paused=False, latest_message=latest_message,
                          followup_action=None, active_loop=None, latest_action_name=None)
        domain: Dict[Text, Any] = None
        action.save().to_mongo().to_dict()
        actual: List[Dict[Text, Any]] = await ActionProcessor.process_action(dispatcher, tracker, domain,
                                                                             "test_run_get_with_parameters")
        assert actual is not None
        assert str(actual[0]['name']) == 'kairon_action_response'
        assert str(actual[0]['value']) == 'The value of 2 in red is [\'red\', \'buggy\', \'bumpers\']'

    @responses.activate
    @pytest.mark.asyncio
    async def test_run_get_with_parameters_2(self, monkeypatch):
        action = HttpActionConfig(
            action_name="test_run_get_with_parameters_2",
            response=HttpActionResponse(value="The value of ${data.a.b.3} in ${data.a.b.d.0} is ${data.a.b.d}"),
            http_url="http://localhost:8081/mock",
            request_method="GET",
            params_list=None,
            bot="5f50fd0a56b698ca10d35d2e",
            user="user"
        )

        def _get_action(*args, **kwargs):
            return {"type": ActionType.http_action.value}

        monkeypatch.setattr(ActionUtility, "get_action", _get_action)
        http_url = 'http://localhost:8081/mock'
        resp_msg = {
            "a": {
                "b": {
                    "3": 2,
                    "43": 30,
                    "c": [],
                    "d": ['red', 'buggy', 'bumpers'],
                }
            }
        }

        responses.add(
            responses.GET, http_url, json=resp_msg
        )

        slots = {"bot": "5f50fd0a56b698ca10d35d2e"}
        events = [{"event1": "hello"}, {"event2": "how are you"}]
        dispatcher: CollectingDispatcher = CollectingDispatcher()
        latest_message = {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]}
        tracker = Tracker(sender_id="sender1", slots=slots, events=events, paused=False, latest_message=latest_message,
                          followup_action=None, active_loop=None, latest_action_name=None)
        domain: Dict[Text, Any] = None
        action.save().to_mongo().to_dict()
        actual: List[Dict[Text, Any]] = await ActionProcessor.process_action(dispatcher, tracker, domain,
                                                                             "test_run_get_with_parameters_2")
        assert actual is not None
        assert str(actual[0]['name']) == 'kairon_action_response'
        assert str(actual[0]['value']) == 'The value of 2 in red is [\'red\', \'buggy\', \'bumpers\']'

    @pytest.mark.asyncio
    async def test_slot_set_action_from_value(self, monkeypatch):
        action_name = "test_slot_set_action_from_value"
        action = SlotSetAction(
            name=action_name,
            set_slots=[SetSlots(name="location", type="from_value", value="Bengaluru")],
            bot="5f50fd0a56b698ca10d35d2e",
            user="user"
        )

        def _get_action(*args, **kwargs):
            return {"type": ActionType.slot_set_action.value}

        monkeypatch.setattr(ActionUtility, "get_action", _get_action)
        slots = {"bot": "5f50fd0a56b698ca10d35d2e", "location": None, "current_location": 'Mumbai'}
        events = [{"event1": "hello"}, {"event2": "how are you"}]
        dispatcher: CollectingDispatcher = CollectingDispatcher()
        latest_message = {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]}
        tracker = Tracker(sender_id="sender1", slots=slots, events=events, paused=False, latest_message=latest_message,
                          followup_action=None, active_loop=None, latest_action_name=None)
        domain: Dict[Text, Any] = None
        action.save().to_mongo().to_dict()
        actual: List[Dict[Text, Any]] = await ActionProcessor.process_action(dispatcher, tracker, domain, action_name)
        assert actual is not None
        assert str(actual[0]['name']) == 'location'
        assert str(actual[0]['value']) == 'Bengaluru'

    @pytest.mark.asyncio
    async def test_slot_set_action_reset_slot(self, monkeypatch):
        action_name = "test_slot_set_action_reset_slot"
        action = SlotSetAction(
            name=action_name,
            set_slots=[SetSlots(name="location", type="reset_slot", value="Bengaluru")],
            bot="5f50fd0a56b698ca10d35d2e", user="user"
        )

        def _get_action(*arge, **kwargs):
            return {'type': ActionType.slot_set_action.value}

        monkeypatch.setattr(ActionUtility, "get_action", _get_action)
        slots = {"bot": "5f50fd0a56b698ca10d35d2e", "location": None, "current_location": 'Mumbai'}
        events = [{"event1": "hello"}, {"event2": "how are you"}]
        dispatcher: CollectingDispatcher = CollectingDispatcher()
        latest_message = {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]}
        tracker = Tracker(sender_id="sender1", slots=slots, events=events, paused=False, latest_message=latest_message,
                          followup_action=None, active_loop=None, latest_action_name=None)
        domain: Dict[Text, Any] = None
        action.save().to_mongo().to_dict()
        actual: List[Dict[Text, Any]] = await ActionProcessor.process_action(dispatcher, tracker, domain, action_name)
        assert actual is not None
        assert str(actual[0]['name']) == 'location'
        assert actual[0]['value'] == None

    @pytest.mark.asyncio
    async def test_execute_action_with_no_type(self, monkeypatch):
        action_name = "test_execute_action_with_no_type"

        def _get_action(*arge, **kwargs):
            raise ActionFailure('Only http & slot set actions are compatible with action server')

        monkeypatch.setattr(ActionUtility, "get_action", _get_action)
        slots = {"bot": "5f50fd0a56b698ca10d35d2e", "location": None, "current_location": 'Mumbai'}
        events = [{"event1": "hello"}, {"event2": "how are you"}]
        dispatcher: CollectingDispatcher = CollectingDispatcher()
        latest_message = {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]}
        tracker = Tracker(sender_id="sender1", slots=slots, events=events, paused=False, latest_message=latest_message,
                          followup_action=None, active_loop=None, latest_action_name=None)
        domain: Dict[Text, Any] = None
        actual: List[Dict[Text, Any]] = await ActionProcessor.process_action(dispatcher, tracker, domain, action_name)
        assert actual is None

    def test_get_action_type(self):
        bot = 'test_actions'
        user = 'test'
        Actions(name='test_get_action_type', type=ActionType.slot_set_action.value, bot=bot, user=user).save()
        SlotSetAction(name='test_get_action_type', set_slots=[SetSlots(name='user', type='from_value', value='name')],
                      bot=bot, user=user).save()
        action_type = ActionUtility.get_action_type(bot, 'test_get_action_type')
        assert action_type == "slot_set_action"

        action_type = ActionUtility.get_action_type(bot, 'utter_greet')
        assert action_type == "kairon_bot_response"

    def test_get_action_config_slot_set_action(self):
        bot = 'test_actions'
        user = 'test'
        Actions(name='action_get_user', type=ActionType.slot_set_action.value, bot=bot, user=user).save()
        SlotSetAction(name='action_get_user', set_slots=[SetSlots(name='user', type='from_value', value='name')],
                      bot=bot, user=user).save()
        config = ActionUtility.get_action(bot, 'action_get_user')
        assert config['type'] == ActionType.slot_set_action.value
        config = ActionSetSlot(bot, 'action_get_user').retrieve_config()
        assert config['name'] == 'action_get_user'
        assert config['set_slots'] == [{'name': 'user', 'type': 'from_value', 'value': 'name'}]

    def test_get_action_config_http_action(self):
        bot = 'test_actions'
        user = 'test'
        HttpActionConfig(
            action_name="action_hit_endpoint",
            response=HttpActionResponse(value="json"),
            http_url="http://test.com",
            request_method="GET",
            bot=bot,
            user=user
        ).save()

        config = ActionHTTP(bot, 'action_hit_endpoint').retrieve_config()
        assert config['action_name'] == 'action_hit_endpoint'
        assert config['response'] == {'dispatch': True, 'evaluation_type': 'expression', 'value': 'json',
                                      'dispatch_type': 'text'}
        assert config['http_url'] == "http://test.com"
        assert config['request_method'] == 'GET'

    def test_get_action_config_action_does_not_exists(self):
        bot = 'test_actions'
        with pytest.raises(ActionFailure, match='No action found for given bot and name'):
            ActionUtility.get_action(bot, 'test_get_action_config_action_does_not_exists')

    def test_get_action_config_slot_set_action_does_not_exists(self):
        bot = 'test_actions'

        with pytest.raises(ActionFailure, match="No Slot set action found for given action and bot"):
            ActionSetSlot(bot, 'test_get_action_config_slot_set_action_does_not_exists').retrieve_config()

    def test_get_action_config_http_action_does_not_exists(self):
        bot = 'test_actions'
        user = 'test'
        with pytest.raises(ActionFailure, match="No HTTP action found for given action and bot"):
            ActionHTTP(bot, 'test_get_action_config_http_action_does_not_exists').retrieve_config()

    def test_get_http_action_config_bot_empty(self):
        with pytest.raises(ActionFailure, match="No HTTP action found for given action and bot"):
            ActionHTTP(' ', 'test_get_action_config_http_action_does_not_exists').retrieve_config()

    def test_get_http_action_config_action_empty(self):
        with pytest.raises(ActionFailure, match="No HTTP action found for given action and bot"):
            ActionHTTP('test_get_action_config_http_action_does_not_exists', ' ').retrieve_config()

    def test_get_action_config_custom_user_action(self):
        bot = 'test_actions'
        user = 'test'
        Actions(name='test_get_action_config_custom_user_action', bot=bot, user=user).save()
        with pytest.raises(ActionFailure, match='None type action is not supported with action server'):
            ActionFactory.get_instance(bot, 'test_get_action_config_custom_user_action')

    def test_get_form_validation_config_single_validation(self):
        bot = 'test_actions'
        user = 'test'
        validation_semantic = {'or': [{'less_than': '5'}, {'==': 6}]}
        expected_output = FormValidationAction(name='validate_form', slot='name',
                                               validation_semantic=validation_semantic,
                                               bot=bot, user=user).save().to_mongo().to_dict()
        config = ActionFormValidation(bot, 'validate_form').retrieve_config().get().to_mongo().to_dict()
        config.pop('timestamp')
        expected_output.pop('timestamp')
        assert config == expected_output

    def test_get_form_validation_config_multiple_validations(self):
        bot = 'test_actions'
        user = 'test'
        validation_semantic = {'or': [{'less_than': '5'}, {'==': 6}]}
        expected_outputs = []
        for slot in ['name', 'user', 'location']:
            expected_output = FormValidationAction(name='validate_form_1', slot=slot,
                                                   validation_semantic=validation_semantic,
                                                   bot=bot, user=user).save().to_mongo().to_dict()
            expected_output.pop('_id')
            expected_output.pop('timestamp')
            expected_outputs.append(expected_output)
        config = ActionFormValidation(bot, 'validate_form_1').retrieve_config().to_json()
        config = json.loads(config)
        for c in config:
            c.pop('timestamp')
            c.pop('_id')
        assert config[0] == expected_outputs[0]
        assert config[1] == expected_outputs[1]
        assert config[2] == expected_outputs[2]

    def test_get_form_validation_config_not_exists(self):
        bot = 'test_actions'
        config = ActionFormValidation(bot, 'validate_form_2').retrieve_config()
        assert not config
        assert isinstance(config, QuerySet)

    def test_get_action_config_form_validation(self):
        bot = 'test_actions'
        user = 'test'
        Actions(name='validate_form_1', type=ActionType.form_validation_action.value, bot=bot, user=user).save()
        config = ActionUtility.get_action(bot, 'validate_form_1')
        assert config
        assert config['type'] == ActionType.form_validation_action.value

    def test_get_slot_type(self):
        bot = 'test_actions'
        user = 'test'
        Slots(name='location', type='text', bot=bot, user=user).save()
        slot_type = ActionUtility.get_slot_type(bot, 'location')
        assert slot_type == 'text'

    def test_get_slot_type_not_exists(self):
        bot = 'test_actions'
        with pytest.raises(ActionFailure, match='Slot not found in database: non_existant'):
            ActionUtility.get_slot_type(bot, 'non_existant')

    def test_get_email_action_config(self):
        with patch('kairon.shared.utils.SMTP', autospec=True) as mock:
            expected = EmailActionConfig(
                action_name="email_action",
                smtp_url="test.localhost",
                smtp_port=293,
                smtp_password=CustomActionRequestParameters(key='smtp_password', value="test"),
                from_email="test@demo.com",
                subject="test",
                to_email=["test@test.com","test1@test.com"],
                response="Validated",
                bot="bot",
                user="user"
            ).save().to_mongo().to_dict()

            actual = ActionEmail("bot", "email_action").retrieve_config()
            assert actual is not None
            assert expected['action_name'] == actual['action_name']
            assert expected['response'] == actual['response']
            assert 'test.localhost' == actual['smtp_url']
            assert expected['smtp_port'] == actual['smtp_port']
            assert {'_cls': 'CustomActionRequestParameters', 'key': 'smtp_password', 'encrypt': False, 'value': 'test',
                    'parameter_type': 'value'} == actual['smtp_password']
            assert 'test@demo.com' == actual['from_email']
            assert expected['to_email'] == actual['to_email']
            assert expected.get("smtp_userid") == actual.get("smtp_userid")

            expected = EmailActionConfig(
                action_name="email_action1",
                smtp_url="test.localhost",
                smtp_port=293,
                smtp_userid=CustomActionRequestParameters(value='test.user_id'),
                smtp_password=CustomActionRequestParameters(value="test"),
                from_email="test@demo.com",
                subject="test",
                to_email=["test@test.com", "test1@test.com"],
                response="Validated",
                bot="bot",
                user="user"
            ).save().to_mongo().to_dict()

            actual = ActionEmail("bot", "email_action1").retrieve_config()
            assert actual is not None
            assert expected['action_name'] == actual['action_name']
            assert expected['response'] == actual['response']
            assert 'test.localhost' == actual['smtp_url']
            assert expected['smtp_port'] == actual['smtp_port']
            assert {'_cls': 'CustomActionRequestParameters', 'key': 'smtp_password', 'encrypt': False, 'value': 'test',
                    'parameter_type': 'value'} == actual['smtp_password'] == actual['smtp_password']
            assert 'test@demo.com' == actual['from_email']
            assert expected['to_email'] == actual['to_email']
            assert {'_cls': 'CustomActionRequestParameters', 'key': 'smtp_userid', 'encrypt': False,
                    'value': 'test.user_id', 'parameter_type': 'value'} == actual['smtp_userid'] == actual.get(
                "smtp_userid")

    def test_email_action_not_found(self):
        with pytest.raises(ActionFailure, match="No Email action found for given action and bot"):
            ActionEmail("test", "test_email_action_not_found").retrieve_config()

    def test_prepare_email_body(self):
        Utility.email_conf['email']['templates']['conversation'] = open('template/emails/conversation.html', 'rb').read().decode()
        Utility.email_conf['email']['templates']['bot_msg_conversation'] = open('template/emails/bot_msg_conversation.html', 'rb').read().decode()
        Utility.email_conf['email']['templates']['user_msg_conversation'] = open('template/emails/user_msg_conversation.html', 'rb').read().decode()
        events = [{"event":"action","timestamp":1594907100.12764,"name":"action_session_start","policy":None,"confidence":None},{"event":"session_started","timestamp":1594907100.12765},{"event":"action","timestamp":1594907100.12767,"name":"action_listen","policy":None,"confidence":None},{"event":"user","timestamp":1594907100.42744,"text":"can't","parse_data":{"intent":{"name":"test intent","confidence":0.253578245639801},"entities":[],"intent_ranking":[{"name":"test intent","confidence":0.253578245639801},{"name":"goodbye","confidence":0.1504897326231},{"name":"greet","confidence":0.138640150427818},{"name":"affirm","confidence":0.0857767835259438},{"name":"smalltalk_human","confidence":0.0721133947372437},{"name":"deny","confidence":0.069614589214325},{"name":"bot_challenge","confidence":0.0664894133806229},{"name":"faq_vaccine","confidence":0.062177762389183},{"name":"faq_testing","confidence":0.0530692934989929},{"name":"out_of_scope","confidence":0.0480506233870983}],"response_selector":{"default":{"response":{"name":None,"confidence":0},"ranking":[],"full_retrieval_intent":None}},"text":"can't"},"input_channel":None,"message_id":"bbd413bf5c834bf3b98e0da2373553b2","metadata":{}},{"event":"action","timestamp":1594907100.4308,"name":"utter_test intent","policy":"policy_0_MemoizationPolicy","confidence":1},{"event":"bot","timestamp":1594907100.4308,"text":"will not = won\"t","data":{"elements":None,"quick_replies":None,"buttons":None,"attachment":None,"image":None,"custom":None},"metadata":{}},{"event":"action","timestamp":1594907100.43384,"name":"action_listen","policy":"policy_0_MemoizationPolicy","confidence":1},{"event":"user","timestamp":1594907117.04194,"text":"can\"t","parse_data":{"intent":{"name":"test intent","confidence":0.253578245639801},"entities":[],"intent_ranking":[{"name":"test intent","confidence":0.253578245639801},{"name":"goodbye","confidence":0.1504897326231},{"name":"greet","confidence":0.138640150427818},{"name":"affirm","confidence":0.0857767835259438},{"name":"smalltalk_human","confidence":0.0721133947372437},{"name":"deny","confidence":0.069614589214325},{"name":"bot_challenge","confidence":0.0664894133806229},{"name":"faq_vaccine","confidence":0.062177762389183},{"name":"faq_testing","confidence":0.0530692934989929},{"name":"out_of_scope","confidence":0.0480506233870983}],"response_selector":{"default":{"response":{"name":None,"confidence":0},"ranking":[],"full_retrieval_intent":None}},"text":"can\"t"},"input_channel":None,"message_id":"e96e2a85de0748798748385503c65fb3","metadata":{}},{"event":"action","timestamp":1594907117.04547,"name":"utter_test intent","policy":"policy_1_TEDPolicy","confidence":0.978452920913696},{"event":"bot","timestamp":1594907117.04548,"text":"can not = can't","data":{"elements":None,"quick_replies":None,"buttons":None,"attachment":None,"image":None,"custom":None},"metadata":{}}]
        actual = ActionUtility.prepare_email_body(events, "conversation history", "test@kairon.com")
        assert str(actual).__contains__("</table>")

    def test_get_prompt_action_config(self):
        bot = 'test_action_server'
        user = 'test_user'
        Actions(name='kairon_faq_action', type=ActionType.prompt_action.value, bot=bot, user=user).save()
        BotSettings(bot=bot, user=user, llm_settings=LLMSettings(enable_faq=True)).save()
        actual = ActionUtility.get_action(bot, 'kairon_faq_action')
        llm_prompts = [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                        'source': 'static', 'is_enabled': True},
                       {'name': 'History Prompt', 'type': 'user', 'source': 'history', 'is_enabled': True}]
        PromptAction(name='kairon_faq_action', bot=bot, user=user, llm_prompts=llm_prompts).save()

        assert actual['type'] == ActionType.prompt_action.value
        actual_config, bot_settings = ActionPrompt(bot, 'kairon_faq_action').retrieve_config()
        actual_config.pop("timestamp")
        actual_config.pop("status")
        actual_config.pop("user")
        assert actual_config == {'name': 'kairon_faq_action', 'num_bot_responses': 5, 'top_results': 10,
                          'similarity_threshold': 0.7,
                          'failure_message': "I'm sorry, I didn't quite understand that. Could you rephrase?",
                          'bot': 'test_action_server', 'enable_response_cache': False,
                          'hyperparameters': {'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-3.5-turbo',
                                              'top_p': 0.0, 'n': 1, 'stream': False, 'stop': None,
                                              'presence_penalty': 0.0, 'frequency_penalty': 0.0, 'logit_bias': {}},
                          'llm_prompts': llm_prompts}
        bot_settings.pop("_id")
        bot_settings.pop("timestamp")
        bot_settings.pop("status")
        assert bot_settings == {'ignore_utterances': False, 'force_import': False, 'rephrase_response': False,
                                'website_data_generator_depth_search_limit': 2,
                                'llm_settings': {'enable_faq': True, 'provider': 'azure'}, 'chat_token_expiry': 30,
                                'refresh_token_expiry': 60, 'whatsapp': 'meta', 'notification_scheduling_limit': 4,
                                'bot': 'test_action_server', 'user': 'test_user'}

    def test_prompt_action_not_exists(self):
        with pytest.raises(ActionFailure, match="Faq feature is disabled for the bot! Please contact support."):
            ActionPrompt('test_kairon_faq_action_not_exists', 'testing_kairon_faq').retrieve_config()

    def test_get_google_search_action_config(self):
        bot = 'test_action_server'
        user = 'test_user'
        Actions(name='google_search_action', type=ActionType.google_search_action.value, bot=bot, user=user).save()
        GoogleSearchAction(name='google_search_action', api_key=CustomActionRequestParameters(value='1234567890'),
                           search_engine_id='asdfg::123456', bot=bot, user=user).save()
        actual = ActionUtility.get_action(bot, 'google_search_action')
        assert actual['type'] == ActionType.google_search_action.value
        actual = ActionGoogleSearch(bot, 'google_search_action').retrieve_config()
        assert actual['api_key'] == {'_cls': 'CustomActionRequestParameters', 'encrypt': False, 'key': 'api_key', 'parameter_type': 'value', 'value': '1234567890'}
        assert actual['search_engine_id'] == 'asdfg::123456'

    def test_get_google_search_action_config_not_exists(self):
        bot = 'test_action_server'
        with pytest.raises(ActionFailure, match="No Google search action found for given action and bot"):
            ActionGoogleSearch(bot, 'custom_search_action').retrieve_config()

    def test_get_jira_action_not_exists(self):
        bot = 'test_action_server'
        with pytest.raises(ActionFailure, match="No Jira action found for given action and bot"):
            ActionJiraTicket(bot, 'jira_action').retrieve_config()

    def test_get_jira_action_not_found(self):
        bot = 'test_action_server'
        user = 'test_user'
        Actions(name='jira_action', type=ActionType.jira_action.value, bot=bot, user=user).save()
        config = ActionUtility.get_action(bot, 'jira_action')
        assert config
        assert config['type'] == ActionType.jira_action.value

    @responses.activate
    def test_create_jira_issue(self):
        url = 'https://test-digite.atlassian.net'
        username = 'test@digite.com'
        api_token = 'ASDFGHJKL'
        project_key = 'HEL'
        issue_type = 'Bug'
        summary = 'Successfully created'
        description = json.dumps([{'bot': 'hi'}, {'user': 'hello'}, {'bot': 'whatup'}, {'user': 'cool'}])
        responses.add(
            'GET',
            f'{url}/rest/api/2/serverInfo',
            json={'baseUrl': 'https://udit-pandey.atlassian.net', 'version': '1001.0.0-SNAPSHOT',
                  'versionNumbers': [1001, 0, 0], 'deploymentType': 'Cloud', 'buildNumber': 100191,
                  'buildDate': '2022-02-11T05:35:40.000+0530', 'serverTime': '2022-02-15T10:54:09.906+0530',
                  'scmInfo': '831671b3b59f40b5108ef3f9491df89a1317ecaa', 'serverTitle': 'Jira',
                  'defaultLocale': {'locale': 'en_US'}},
        )
        responses.add(
            'POST',
            f'{url}/rest/api/2/issue',
            json={'id': '10006', 'key': 'HEL-7', 'self': f'{url}/rest/api/2/issue/10006'}
        )
        responses.add(
            'GET',
            f'{url}/rest/api/2/issue/HEL-7',
            json={
                'expand': 'renderedFields,names,schema,operations,editmeta,changelog,versionedRepresentations,customfield_10010.requestTypePractice',
                'id': '10007', 'self': 'https://udit-pandey.atlassian.net/rest/api/2/issue/10007', 'key': 'HEL-8',
                'fields': {'statuscategorychangedate': '2022-02-15T20:43:38.025+0530',
                           'issuetype': {'self': 'https://udit-pandey.atlassian.net/rest/api/2/issuetype/10003',
                                         'id': '10003',
                                         'description': 'Subtasks track small pieces of work that are part of a larger task.',
                                         'iconUrl': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10316?size=medium',
                                         'name': 'Subtask', 'subtask': True, 'avatarId': 10316,
                                         'entityId': 'd603fd3f-d368-46a6-b4c4-9fcffc1dc23b',
                                         'hierarchyLevel': -1}, 'parent': {'id': '10003', 'key': 'HEL-4',
                                                                           'self': 'https://udit-pandey.atlassian.net/rest/api/2/issue/10003',
                                                                           'fields': {'summary': 'order for apache',
                                                                                      'status': {
                                                                                          'self': 'https://udit-pandey.atlassian.net/rest/api/2/status/10000',
                                                                                          'description': '',
                                                                                          'iconUrl': 'https://udit-pandey.atlassian.net/',
                                                                                          'name': 'To Do',
                                                                                          'id': '10000',
                                                                                          'statusCategory': {
                                                                                              'self': 'https://udit-pandey.atlassian.net/rest/api/2/statuscategory/2',
                                                                                              'id': 2, 'key': 'new',
                                                                                              'colorName': 'blue-gray',
                                                                                              'name': 'To Do'}},
                                                                                      'priority': {
                                                                                          'self': 'https://udit-pandey.atlassian.net/rest/api/2/priority/3',
                                                                                          'iconUrl': 'https://udit-pandey.atlassian.net/images/icons/priorities/medium.svg',
                                                                                          'name': 'Medium', 'id': '3'},
                                                                                      'issuetype': {
                                                                                          'self': 'https://udit-pandey.atlassian.net/rest/api/2/issuetype/10001',
                                                                                          'id': '10001',
                                                                                          'description': 'A small, distinct piece of work.',
                                                                                          'iconUrl': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10318?size=medium',
                                                                                          'name': 'Task',
                                                                                          'subtask': False,
                                                                                          'avatarId': 10318,
                                                                                          'entityId': 'df701898-8426-493f-b0c4-51b30dddf1b2',
                                                                                          'hierarchyLevel': 0}}},
                           'timespent': None,
                           'project': {'self': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000',
                                       'id': '10000', 'key': 'HEL', 'name': 'helicopter', 'projectTypeKey': 'software',
                                       'simplified': True, 'avatarUrls': {
                                   '48x48': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408',
                                   '24x24': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=small',
                                   '16x16': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=xsmall',
                                   '32x32': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=medium'}},
                           'fixVersions': [], 'aggregatetimespent': None, 'resolution': None, 'resolutiondate': None,
                           'workratio': -1, 'issuerestriction': {'issuerestrictions': {}, 'shouldDisplay': True},
                           'lastViewed': None,
                           'watches': {'self': 'https://udit-pandey.atlassian.net/rest/api/2/issue/HEL-8/watchers',
                                       'watchCount': 1, 'isWatching': True}, 'created': '2022-02-15T20:43:37.691+0530',
                           'customfield_10020': None, 'customfield_10021': None, 'customfield_10022': None,
                           'priority': {'self': 'https://udit-pandey.atlassian.net/rest/api/2/priority/3',
                                        'iconUrl': 'https://udit-pandey.atlassian.net/images/icons/priorities/medium.svg',
                                        'name': 'Medium', 'id': '3'}, 'customfield_10023': None,
                           'customfield_10024': None, 'customfield_10025': None, 'labels': [],
                           'customfield_10016': None, 'customfield_10017': None,
                           'customfield_10018': {'hasEpicLinkFieldDependency': False, 'showField': False,
                                                 'nonEditableReason': {'reason': 'PLUGIN_LICENSE_ERROR',
                                                                       'message': 'The Parent Link is only available to Jira Premium users.'}},
                           'customfield_10019': '0|i0001j:', 'aggregatetimeoriginalestimate': None,
                           'timeestimate': None, 'versions': [], 'issuelinks': [], 'assignee': None,
                           'updated': '2022-02-15T20:43:37.960+0530',
                           'status': {'self': 'https://udit-pandey.atlassian.net/rest/api/2/status/10000',
                                      'description': '', 'iconUrl': 'https://udit-pandey.atlassian.net/',
                                      'name': 'To Do', 'id': '10000', 'statusCategory': {
                                   'self': 'https://udit-pandey.atlassian.net/rest/api/2/statuscategory/2', 'id': 2,
                                   'key': 'new', 'colorName': 'blue-gray', 'name': 'To Do'}}, 'components': [],
                           'timeoriginalestimate': None,
                           'description': 'Creating of an issue using project keys and issue type names using the REST API',
                           'customfield_10010': None, 'customfield_10014': None, 'timetracking': {},
                           'customfield_10015': None, 'customfield_10005': None, 'customfield_10006': None,
                           'customfield_10007': None, 'security': None, 'customfield_10008': None,
                           'customfield_10009': None, 'aggregatetimeestimate': None, 'attachment': [],
                           'summary': 'order for apache', 'creator': {
                        'self': 'https://udit-pandey.atlassian.net/rest/api/2/user?accountId=6205e1585d18ad00729aa75f',
                        'accountId': '6205e1585d18ad00729aa75f', 'emailAddress': 'udit.pandey@digite.com',
                        'avatarUrls': {
                            '48x48': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png',
                            '24x24': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png',
                            '16x16': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png',
                            '32x32': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png'},
                        'displayName': 'Udit Pandey', 'active': True, 'timeZone': 'Asia/Calcutta',
                        'accountType': 'atlassian'}, 'subtasks': [], 'reporter': {
                        'self': 'https://udit-pandey.atlassian.net/rest/api/2/user?accountId=6205e1585d18ad00729aa75f',
                        'accountId': '6205e1585d18ad00729aa75f', 'emailAddress': 'udit.pandey@digite.com',
                        'avatarUrls': {
                            '32x32': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png'},
                        'displayName': 'Udit Pandey', 'active': True, 'timeZone': 'Asia/Calcutta',
                        'accountType': 'atlassian'}, 'aggregateprogress': {'progress': 0, 'total': 0},
                           'customfield_10000': '{}', 'customfield_10001': None, 'customfield_10002': None,
                           'customfield_10003': None, 'customfield_10004': None, 'environment': None, 'duedate': None,
                           'progress': {'progress': 0, 'total': 0},
                           'votes': {'self': 'https://udit-pandey.atlassian.net/rest/api/2/issue/HEL-8/votes',
                                     'votes': 0, 'hasVoted': False}, 'comment': {'comments': [],
                                                                                 'self': 'https://udit-pandey.atlassian.net/rest/api/2/issue/10007/comment',
                                                                                 'maxResults': 0, 'total': 0,
                                                                                 'startAt': 0},
                           'worklog': {'startAt': 0, 'maxResults': 20, 'total': 0, 'worklogs': []}}}
        )
        assert not ActionUtility.create_jira_issue(url, username, api_token, project_key, issue_type, summary, description)

    def test_create_jira_issue_failure(self):
        url = 'https://test-digite.atlassian.net'
        username = 'test@digite.com'
        api_token = 'ASDFGHJKL'
        project_key = 'HEL'
        issue_type = 'Bug'
        summary = 'Successfully created'
        description = json.dumps([{'bot': 'hi'}, {'user': 'hello'}, {'bot': 'whatup'}, {'user': 'cool'}])
        responses.add(
            'GET',
            f'{url}/rest/api/2/serverInfo',
            status=500
        )
        with pytest.raises(Exception):
            ActionUtility.create_jira_issue(url, username, api_token, project_key, issue_type, summary, description)

    def test_get_jira_action(self):
        bot = 'test_action_server'
        user = 'test_user'

        def _mock_response(*args, **kwargs):
            return None

        with patch('kairon.shared.actions.data_objects.JiraAction.validate', new=_mock_response):
            JiraAction(
                name='jira_action', bot=bot, user=user, url='https://test-digite.atlassian.net', user_name='test@digite.com',
                api_token=CustomActionRequestParameters(value='ASDFGHJKL'), project_key='HEL', issue_type='Bug',
                summary='fallback', response='Successfully created').save()
        action = ActionUtility.get_action(bot, 'jira_action')
        assert action['type'] == 'jira_action'
        action = ActionJiraTicket(bot, 'jira_action').retrieve_config()
        action.pop('_id')
        action.pop('timestamp')
        assert action == {
            'name': 'jira_action', 'url': 'https://test-digite.atlassian.net', 'user_name': 'test@digite.com',
            'api_token':  {'_cls': 'CustomActionRequestParameters', 'encrypt': False, 'parameter_type': 'value',
                           'value': 'ASDFGHJKL'}, 'project_key': 'HEL', 'issue_type': 'Bug', 'summary': 'fallback',
            'response': 'Successfully created', 'bot': 'test_action_server', 'user': 'test_user', 'status': True
        }

    def test_google_search_action(self, monkeypatch):
        def _run_action(*arge, **kwargs):
            return {
                "kind": "customsearch#search",
                "url": {
                    "type": "application/json",
                    "template": "https://www.googleapis.com/customsearch/v1?q={searchTerms}&num={count?}&start={startIndex?}&lr={language?}&safe={safe?}&cx={cx?}&sort={sort?}&filter={filter?}&gl={gl?}&cr={cr?}&googlehost={googleHost?}&c2coff={disableCnTwTranslation?}&hq={hq?}&hl={hl?}&siteSearch={siteSearch?}&siteSearchFilter={siteSearchFilter?}&exactTerms={exactTerms?}&excludeTerms={excludeTerms?}&linkSite={linkSite?}&orTerms={orTerms?}&relatedSite={relatedSite?}&dateRestrict={dateRestrict?}&lowRange={lowRange?}&highRange={highRange?}&searchType={searchType}&fileType={fileType?}&rights={rights?}&imgSize={imgSize?}&imgType={imgType?}&imgColorType={imgColorType?}&imgDominantColor={imgDominantColor?}&alt=json"
                },
                "queries": {
                    "request": [
                        {
                            "title": "Google Custom Search - \"what is kanban\"",
                            "totalResults": "63",
                            "searchTerms": "\"what is kanban\"",
                            "count": 10,
                            "startIndex": 1,
                            "inputEncoding": "utf8",
                            "outputEncoding": "utf8",
                            "safe": "off",
                            "cx": "008204382765647029238:pt5fuheh0do"
                        }
                    ],
                    "nextPage": [
                        {
                            "title": "Google Custom Search - \"what is kanban\"",
                            "totalResults": "63",
                            "searchTerms": "\"what is kanban\"",
                            "count": 10,
                            "startIndex": 11,
                            "inputEncoding": "utf8",
                            "outputEncoding": "utf8",
                            "safe": "off",
                            "cx": "008204382765647029238:pt5fuheh0do"
                        }
                    ]
                },
                "context": {
                    "title": "DGT"
                },
                "searchInformation": {
                    "searchTime": 0.427328,
                    "formattedSearchTime": "0.43",
                    "totalResults": "63",
                    "formattedTotalResults": "63"
                },
                "items": [
                    {
                        "kind": "customsearch#result",
                        "title": "What Is Kanban? An Overview Of The Kanban Method",
                        "htmlTitle": "<b>What Is Kanban</b>? An Overview Of The Kanban Method",
                        "link": "https://www.digite.com/kanban/what-is-kanban/",
                        "displayLink": "www.digite.com",
                        "snippet": "Kanban visualizes both the process (the workflow) and the actual work passing through that process. The goal of Kanban is to identify potential bottlenecks in ...",
                        "htmlSnippet": "Kanban visualizes both the process (the workflow) and the actual work passing through that process. The goal of Kanban is to identify potential bottlenecks in&nbsp;...",
                        "cacheId": "JwKNqNQN0h0J",
                        "formattedUrl": "https://www.digite.com/kanban/what-is-kanban/",
                        "htmlFormattedUrl": "https://www.digite.com/kanban/<b>what-is-kanban</b>/",
                        "pagemap": {
                            "cse_thumbnail": [
                                {
                                    "src": "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRT-YhBrALL2k95qNSSMy_RT3TWdaolYNsPkEAEMfK-6t1K7eFj8N6aUpM",
                                    "width": "318",
                                    "height": "159"
                                }
                            ],
                            "metatags": [
                                {
                                    "og:image": "https://d112uwirao0vo9.cloudfront.net/wp-content/uploads/2019/11/Kanban.jpg",
                                    "og:image:width": "400",
                                    "article:published_time": "2013-08-18GMT+053008:45:29+05:30",
                                    "twitter:card": "summary_large_image",
                                    "shareaholic:keywords": "tag:kanban 101, type:page",
                                    "og:site_name": "Digite",
                                    "twitter:label1": "Time to read",
                                    "og:image:type": "image/jpeg",
                                    "shareaholic:article_modified_time": "2021-12-28T15:13:48+05:30",
                                    "og:description": "Kanban is a way for teams and organizations to visualize work, identify and eliminate bottlenecks and achieve dramatic operational improvements.",
                                    "twitter:creator": "@digiteinc",
                                    "article:publisher": "http://www.facebook.com/digite",
                                    "og:image:secure_url": "https://d112uwirao0vo9.cloudfront.net/wp-content/uploads/2019/11/Kanban.jpg",
                                    "twitter:image": "https://d112uwirao0vo9.cloudfront.net/wp-content/uploads/2019/11/Kanban.jpg",
                                    "twitter:data1": "17 minutes",
                                    "shareaholic:shareable_page": "true",
                                    "twitter:site": "@digiteinc",
                                    "article:modified_time": "2021-12-28GMT+053015:13:48+05:30",
                                    "shareaholic:article_published_time": "2013-08-18T08:45:29+05:30",
                                    "shareaholic:language": "en-US",
                                    "shareaholic:article_author_name": "admin",
                                    "og:type": "article",
                                    "og:image:alt": "What is Kanban?",
                                    "twitter:title": "What Is Kanban? An Overview Of The Kanban Method",
                                    "og:title": "What Is Kanban? An Overview Of The Kanban Method",
                                    "og:image:height": "200",
                                    "shareaholic:site_id": "d451b9c8eb7dc631f67dc9184b724726",
                                    "og:updated_time": "2021-12-28T15:13:48+05:30",
                                    "shareaholic:wp_version": "9.7.1",
                                    "shareaholic:image": "https://d112uwirao0vo9.cloudfront.net/wp-content/uploads/2019/11/Kanban.jpg",
                                    "article:tag": "Kanban 101",
                                    "shareaholic:url": "https://www.digite.com/kanban/what-is-kanban/",
                                    "viewport": "width=device-width, initial-scale=1.0",
                                    "twitter:description": "Kanban is a way for teams and organizations to visualize work, identify and eliminate bottlenecks and achieve dramatic operational improvements.",
                                    "og:locale": "en_US",
                                    "shareaholic:site_name": "Digite",
                                    "og:url": "https://www.digite.com/kanban/what-is-kanban/"
                                }
                            ],
                            "cse_image": [
                                {
                                    "src": "https://d112uwirao0vo9.cloudfront.net/wp-content/uploads/2019/11/Kanban.jpg"
                                }
                            ]
                        }
                    }]}

        monkeypatch.setattr(HttpRequest, 'execute', _run_action)
        results = ActionUtility.perform_google_search('123459876', 'asdfg::567890', 'what is kanban')
        assert results == [{
            'title': 'What Is Kanban? An Overview Of The Kanban Method',
            'text': 'Kanban visualizes both the process (the workflow) and the actual work passing through that process. The goal of Kanban is to identify potential bottlenecks in\xa0...',
            'link': 'https://www.digite.com/kanban/what-is-kanban/'
        }]

    def test_google_search_action_error(self):
        with pytest.raises(ActionFailure):
            ActionUtility.perform_google_search('123459876', 'asdfg::567890', 'what is kanban')

    def test_get_zendesk_action_not_found(self):
        bot = 'test_action_server'
        with pytest.raises(ActionFailure, match='No Zendesk action found for given action and bot'):
            ActionZendeskTicket(bot, 'zendesk_action').retrieve_config()

    def test_get_zendesk_action_config(self):
        bot = 'test_action_server'
        user = 'test_user'

        with patch('zenpy.Zenpy'):
            ZendeskAction(
                name='zendesk_action', bot=bot, user=user, subdomain='digite751', user_name='test@digite.com',
                api_token=CustomActionRequestParameters(value='ASDFGHJKL'), subject='new user detected', response='Successfully created').save()
        action = ActionZendeskTicket(bot, 'zendesk_action').retrieve_config()
        action.pop('_id')
        action.pop('timestamp')
        assert action == {
            'name': 'zendesk_action', 'subdomain': 'digite751', 'user_name': 'test@digite.com',
            'api_token': {'_cls': 'CustomActionRequestParameters', 'key': 'api_token', 'encrypt': False,
                          'value': 'ASDFGHJKL', 'parameter_type': 'value'}, 'subject': 'new user detected',
            'response': 'Successfully created', 'bot': 'test_action_server', 'user': 'test_user', 'status': True
        }

    def test_validate_zendesk_credentials_valid(self):
        with patch('zenpy.Zenpy'):
            ActionUtility.validate_zendesk_credentials('digite751', 'test@digite.com', 'ASDFGHJKL')

    def test_validate_zendesk_credentials_invalid(self):
        def __mock_zendesk_error(*args, **kwargs):
            from zenpy.lib.exception import APIException
            raise APIException({"error": {"title": "No help desk at digite751.zendesk.com"}})

        with patch('zenpy.Zenpy') as mock:
            mock.side_effect = __mock_zendesk_error
            with pytest.raises(ActionFailure):
                ActionUtility.validate_zendesk_credentials('digite751', 'test@digite.com', 'ASDFGHJKL')

    @responses.activate
    def test_create_zendesk_ticket_valid_credentials(self):
        responses.add(
            'POST',
            'https://digite751.zendesk.com/api/v2/tickets.json',
            json={'count': 1},
            match=[responses.matchers.json_params_matcher({'ticket': {'id': None, 'subject': 'new ticket', 'comment': {'id': None}}})]
        )
        ActionUtility.create_zendesk_ticket('digite751', 'test@digite.com', 'ASDFGHJKL', 'new ticket')

        responses.add(
            'POST',
            'https://digite751.zendesk.com/api/v2/tickets.json',
            json={'count': 1},
            match=[responses.matchers.json_params_matcher(
                {'ticket': {'description': 'ticket described', 'id': None, 'subject': 'new ticket',
                            'tags': ['kairon', 'bot'], 'comment': {'id': None, 'html_body': 'html comment'}}})]
        )
        ActionUtility.create_zendesk_ticket('digite751', 'test@digite.com', 'ASDFGHJKL', 'new ticket',
                                            'ticket described', 'html comment', ['kairon', 'bot'])

    def test_create_zendesk_ticket_invalid_credentials(self):
        def __mock_zendesk_error(*args, **kwargs):
            from zenpy.lib.exception import APIException
            raise APIException({"error": {"title": "No help desk at digite751.zendesk.com"}})

        with patch('zenpy.Zenpy') as mock:
            mock.side_effect = __mock_zendesk_error
            with pytest.raises(ActionFailure):
                ActionUtility.validate_zendesk_credentials('digite751', 'test@digite.com', 'ASDFGHJKL')

    def test_create_zendesk_ticket_failure(self):
        def __mock_zendesk_error(*args, **kwargs):
            from zenpy.lib.exception import APIException
            raise APIException({"error": {"title": "Failed to create ticket"}})

        with patch('zenpy.Zenpy') as mock:
            mock.side_effect = __mock_zendesk_error
            with pytest.raises(ActionFailure):
                ActionUtility.validate_zendesk_credentials('digite751', 'test@digite.com', 'ASDFGHJKL')

    def test_google_search_action_config_data_object(self):
        GoogleSearchAction(
            name='google_action',
            api_key=CustomActionRequestParameters(value='sd234567'),
            search_engine_id='asdfgh2345678',
            failure_response=None,
            num_results='asdf2345',
            bot='test_google_search',
            user='test_google_search',
        ).save()
        saved_action = GoogleSearchAction.objects(name='google_action', bot='test_google_search', status=True).get()
        assert saved_action.num_results == 1
        assert saved_action.failure_response == 'I have failed to process your request.'

    def test_get_pipedrive_leads_action_config_not_found(self):
        bot = 'test_action_server'
        user = 'test_user'
        Actions(name='pipedrive_leads_action', type=ActionType.pipedrive_leads_action.value, bot=bot, user=user).save()
        with pytest.raises(ActionFailure, match="No Pipedrive leads action found for given action and bot"):
            ActionPipedriveLeads(bot, 'pipedrive_leads_action').retrieve_config()

    def test_get_pipedrive_leads_action_config(self):
        bot = 'test_action_server'
        user = 'test_user'

        with patch('pipedrive.client.Client'):
            PipedriveLeadsAction(
                name='pipedrive_leads_action', bot=bot, user=user, domain='digite751',
                api_token=CustomActionRequestParameters(value='ASDFGHJKL'),
                title='new user detected', response='Lead successfully added',
                metadata={'name': 'name', 'org_name': 'organization', 'email': 'email', 'phone': 'phone'}).save()
        action = ActionUtility.get_action(bot, 'pipedrive_leads_action')
        assert action
        assert action['type'] == 'pipedrive_leads_action'
        action = ActionPipedriveLeads(bot, 'pipedrive_leads_action').retrieve_config()
        action.pop('_id')
        action.pop('timestamp')
        assert action == {
            'name': 'pipedrive_leads_action', 'domain': 'digite751',
            'api_token': {'_cls': 'CustomActionRequestParameters', 'encrypt': False, 'key': 'api_token',
                          'parameter_type': 'value', 'value': 'ASDFGHJKL'},
            'title': 'new user detected', 'response': 'Lead successfully added', 'bot': 'test_action_server',
            'user': 'test_user', 'status': True, 'metadata': {'name': 'name', 'org_name': 'organization', 'email': 'email', 'phone': 'phone'}
        }

    def test_prepare_pipedrive_metadata(self):
        bot = 'test_action_server'
        slots = {"name": "udit pandey", "organization": "digite", "email": "pandey.udit867@gmail.com", 'phone': '9876543210'}
        events = [{"event1": "hello"}, {"event2": "how are you"}]
        tracker = Tracker(sender_id="sender1", slots=slots, events=events, paused=False, latest_message=None,
                          followup_action=None, active_loop=None, latest_action_name=None)
        action = ActionPipedriveLeads(bot, 'pipedrive_leads_action').retrieve_config()
        metadata = ActionUtility.prepare_pipedrive_metadata(tracker, action)
        assert metadata == {'name': 'udit pandey', 'org_name': 'digite', 'email': 'pandey.udit867@gmail.com', 'phone': '9876543210'}

    def test_prepare_message_trail_as_str(self):
        events = [{"event": "bot", 'text': 'hello'}, {"event": "user", "text": "how are you"},
                  {"event": "bot", 'text': 'good'}, {"event": "user", "text": "ok bye"}]
        _, conversation = ActionUtility.prepare_message_trail_as_str(events)
        assert conversation == 'bot: hello\nuser: how are you\nbot: good\nuser: ok bye\n'

    def test_validate_pipedrive_credentials(self):
        with patch('pipedrive.client.Client'):
            assert not ActionUtility.validate_pipedrive_credentials('https://digite751.pipedrive.com/', 'ASDFGHJKL')

    def test_validate_pipedrive_credentials_failure(self):
        def __mock_exception(*args, **kwargs):
            raise UnauthorizedError('Invalid authentication', {'error_code': 401})
        with patch('pipedrive.client.Client', __mock_exception):
            with pytest.raises(ActionFailure):
                ActionUtility.validate_pipedrive_credentials('https://digite751.pipedrive.com/', 'ASDFGHJKL')

    def test_create_pipedrive_lead(self):
        conversation = 'bot: hello\nuser: how are you\nbot: good\nuser: ok bye\n'
        metadata = {'name': 'udit pandey', 'org_name': 'digite', 'email': 'pandey.udit867@gmail.com', 'phone': '9876543210'}

        def __mock_create_organization(*args, **kwargs):
            return {"success": True, "data": {"id": 2}}

        def __mock_create_person(*args, **kwargs):
            return {"success": True, "data": {"id": 2}}

        def __mock_create_leads(*args, **kwargs):
            return {"success": True, "data": {"id": 2}}

        def __mock_create_note(*args, **kwargs):
            return {"success": True, "data": {"id": 2}}

        with patch('pipedrive.organizations.Organizations.create_organization', __mock_create_organization):
            with patch('pipedrive.persons.Persons.create_person', __mock_create_person):
                with patch('pipedrive.leads.Leads.create_lead', __mock_create_leads):
                    with patch('pipedrive.notes.Notes.create_note', __mock_create_note):
                        ActionUtility.create_pipedrive_lead(
                            'https://digite751.pipedrive.com/', 'ASDFGHJKL', 'new user detected', conversation,
                            **metadata
                        )

    def test_create_pipedrive_lead_failure(self):
        conversation = 'bot: hello\nuser: how are you\nbot: good\nuser: ok bye\n'
        metadata = {'name': 'udit pandey', 'org_name': 'digite', 'email': 'pandey.udit867@gmail.com',
                    'phone': '9876543210'}

        def __mock_exception(*args, **kwargs):
            raise BadRequestError('Invalid request raised', {'error_code': 402})

        def __mock_create_organization(*args, **kwargs):
            return {"success": True, "data": {"id": 2}}

        def __mock_create_person(*args, **kwargs):
            return {"success": True, "data": {"id": 2}}

        def __mock_create_leads_failure(*args, **kwargs):
            return {"success": False, "data": {"id": 2}}

        with patch('pipedrive.client.Client._request', __mock_exception):
            with pytest.raises(BadRequestError):
                ActionUtility.create_pipedrive_lead('https://digite751.pipedrive.com/', 'ASDFGHJKL', 'new user detected',
                                                    conversation, **metadata)
        with patch('pipedrive.organizations.Organizations.create_organization', __mock_create_organization):
            with patch('pipedrive.persons.Persons.create_person', __mock_create_person):
                with patch('pipedrive.leads.Leads.create_lead', __mock_create_leads_failure):
                    with pytest.raises(ActionFailure, match='Failed to create lead: *'):
                        ActionUtility.create_pipedrive_lead('https://digite751.pipedrive.com/', 'ASDFGHJKL',
                                                            'new user detected',
                                                            conversation, **metadata)

    def test_create_pipedrive_organization_failure(self):
        conversation = 'bot: hello\nuser: how are you\nbot: good\nuser: ok bye\n'
        metadata = {'name': 'udit pandey', 'org_name': 'digite', 'email': 'pandey.udit867@gmail.com',
                    'phone': '9876543210'}

        def __mock_exception(*args, **kwargs):
            raise BadRequestError('Invalid request raised', {'error_code': 402})

        def __mock_create_organization_failure(*args, **kwargs):
            return {"success": False, "data": {"id": 2}}

        with patch('pipedrive.client.Client._request', __mock_exception):
            with pytest.raises(BadRequestError):
                ActionUtility.create_pipedrive_lead('https://digite751.pipedrive.com/', 'ASDFGHJKL',
                                                    'new user detected',
                                                    conversation, **metadata)
        with patch('pipedrive.organizations.Organizations.create_organization', __mock_create_organization_failure):
            with pytest.raises(ActionFailure, match='Failed to create organization: *'):
                ActionUtility.create_pipedrive_lead('https://digite751.pipedrive.com/', 'ASDFGHJKL',
                                                    'new user detected', conversation, **metadata)

    def test_create_pipedrive_person_failure(self):
        conversation = 'bot: hello\nuser: how are you\nbot: good\nuser: ok bye\n'
        metadata = {'name': 'udit pandey', 'org_name': 'digite', 'email': 'pandey.udit867@gmail.com',
                    'phone': '9876543210'}

        def __mock_exception(*args, **kwargs):
            raise BadRequestError('Invalid request raised', {'error_code': 402})

        def __mock_create_organization(*args, **kwargs):
            return {"success": True, "data": {"id": 2}}

        def __mock_create_person_failure(*args, **kwargs):
            return {"success": False, "data": {"id": 2}}

        with patch('pipedrive.client.Client._request', __mock_exception):
            with pytest.raises(BadRequestError):
                ActionUtility.create_pipedrive_lead('https://digite751.pipedrive.com/', 'ASDFGHJKL',
                                                    'new user detected', conversation, **metadata)

        with patch('pipedrive.organizations.Organizations.create_organization', __mock_create_organization):
            with patch('pipedrive.persons.Persons.create_person', __mock_create_person_failure):
                with pytest.raises(ActionFailure, match='Failed to create person: *'):
                    ActionUtility.create_pipedrive_lead('https://digite751.pipedrive.com/', 'ASDFGHJKL',
                                                        'new user detected',
                                                        conversation, **metadata)

    def test_create_pipedrive_note_failure(self):
        conversation = 'bot: hello\nuser: how are you\nbot: good\nuser: ok bye\n'
        metadata = {'name': 'udit pandey', 'org_name': 'digite', 'email': 'pandey.udit867@gmail.com',
                    'phone': '9876543210'}

        def __mock_exception(*args, **kwargs):
            raise BadRequestError('Invalid request raised', {'error_code': 402})

        def __mock_create_note_failure(*args, **kwargs):
            return {"success": False, "data": {"id": 2}}

        def __mock_create_organization(*args, **kwargs):
            return {"success": True, "data": {"id": 2}}

        def __mock_create_person(*args, **kwargs):
            return {"success": True, "data": {"id": 2}}

        def __mock_create_leads(*args, **kwargs):
            return {"success": True, "data": {"id": 2}}

        with patch('pipedrive.client.Client._request', __mock_exception):
            with pytest.raises(BadRequestError):
                ActionUtility.create_pipedrive_lead('https://digite751.pipedrive.com/', 'ASDFGHJKL',
                                                    'new user detected',
                                                    conversation, **metadata)
        with patch('pipedrive.organizations.Organizations.create_organization', __mock_create_organization):
            with patch('pipedrive.persons.Persons.create_person', __mock_create_person):
                with patch('pipedrive.leads.Leads.create_lead', __mock_create_leads):
                    with patch('pipedrive.notes.Notes.create_note', __mock_create_note_failure):
                        with pytest.raises(ActionFailure, match='Failed to attach note: *'):
                            ActionUtility.create_pipedrive_lead('https://digite751.pipedrive.com/', 'ASDFGHJKL',
                                                                'new user detected',
                                                                conversation, **metadata)

    def test_get_hubspot_forms_config_not_found(self):
        bot = 'test_action_server'
        user = 'test_user'
        Actions(name='hubspot_forms_action', type=ActionType.hubspot_forms_action.value, bot=bot, user=user).save()
        with pytest.raises(ActionFailure, match="No Hubspot forms action found for given action and bot"):
            ActionHubspotForms(bot, 'hubspot_forms_action').retrieve_config()

    def test_get_hubspot_forms_action_config(self):
        bot = 'test_action_server'
        user = 'test_user'

        fields = [
            {'_cls': 'HttpActionRequestBody', 'key': 'email', 'parameter_type': 'slot', 'value': 'email_slot', 'encrypt': False},
            {'_cls': 'HttpActionRequestBody', 'key': 'firstname', 'parameter_type': 'value', 'value': 'udit', 'encrypt': False}
        ]
        HubspotFormsAction(
            name='hubspot_forms_action', portal_id='asdf45', form_guid='2345678gh', fields=fields, bot=bot, user=user,
            response="Form submitted"
        ).save()
        action = ActionUtility.get_action(bot, 'hubspot_forms_action')
        assert action
        assert action['type'] == ActionType.hubspot_forms_action.value
        action = ActionHubspotForms(bot, 'hubspot_forms_action').retrieve_config()
        action.pop('_id')
        action.pop('timestamp')
        assert action == {
            'name': 'hubspot_forms_action', 'portal_id': 'asdf45', 'form_guid': '2345678gh', 'fields': fields,
            'bot': 'test_action_server', 'user': 'test_user', 'status': True, 'response': 'Form submitted'
        }

    @responses.activate
    def test_evaluate_script(self):
        script = "${a.b.d}"
        data = {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}
        responses.add(
            method=responses.POST,
            url=Utility.environment['evaluator']['url'],
            json={"success": True, "data": "['red', 'buggy', 'bumpers']"},
            status=200,
            match=[
                responses.matchers.json_params_matcher(
                    {'script': script,
                     'data': data})],
        )
        result, log = ActionUtility.evaluate_script(script, data)
        assert result == "['red', 'buggy', 'bumpers']"
        assert log == 'script: ${a.b.d} || data: {\'a\': {\'b\': {\'3\': 2, \'43\': 30, \'c\': [], \'d\': [\'red\', \'buggy\', \'bumpers\']}}} || raise_err_on_failure: True || response: {\'success\': True, \'data\': "[\'red\', \'buggy\', \'bumpers\']"}'

    @responses.activate
    def test_evaluate_script_evaluation_failure(self):
        script = "${a.b.d}"
        data = {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}
        responses.add(
            method=responses.POST,
            url=Utility.environment['evaluator']['url'],
            json={"success": False, "data": "['red', 'buggy', 'bumpers']"},
            status=200,
            match=[
                responses.matchers.json_params_matcher(
                    {'script': script,
                     'data': data})],
        )
        with pytest.raises(ActionFailure, match="Expression evaluation failed: script: ${a.b.d} || data: {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}} || raise_err_on_failure: True || response: {'success': False, 'data': \"['red', 'buggy', 'bumpers']\"}"):
            ActionUtility.evaluate_script(script, data)

    @responses.activate
    def test_evaluate_script_evaluation_failure(self):
        script = "${a.b.d}"
        data = {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}
        responses.add(
            method=responses.POST,
            url=Utility.environment['evaluator']['url'],
            json={"success": False},
            status=200,
            match=[
                responses.matchers.json_params_matcher(
                    {'script': script,
                     'data': data})],
        )
        result, log = ActionUtility.evaluate_script(script, data, False)
        assert result is None
        assert log == 'script: ${a.b.d} || data: {\'a\': {\'b\': {\'3\': 2, \'43\': 30, \'c\': [], \'d\': [\'red\', \'buggy\', \'bumpers\']}}} || raise_err_on_failure: False || response: {\'success\': False}'

    @responses.activate
    def test_prepare_email_text(self):
        custom_text = "The user with ${sender_id} has message ${user_message}."
        tracker_data = {'slot': {"email": "udit.pandey@digite.com", "firstname": "udit"},
                        'sender_id': "987654321", "intent": "greet", "user_message": "hello",
                        'key_vault': {'EMAIL': 'nkhare@digite.com', 'KEY_VAULT': '123456789-0lmgxzxdfghj',
                                      'AWS': '435fdr'}}
        responses.add(
            method=responses.POST,
            url=Utility.environment['evaluator']['url'],
            json={"success": True, "data": "The user with 987654321 has message hello."},
            status=200,
            match=[
                responses.matchers.json_params_matcher(
                    {'script': custom_text,
                     'data': tracker_data})],
        )
        Utility.email_conf['email']['templates']['custom_text_mail'] = open('template/emails/custom_text_mail.html', 'rb').read().decode()
        actual = ActionUtility.prepare_email_text(custom_text, tracker_data, "test@kairon.com")
        assert str(actual).__contains__("The user with 987654321 has message hello.")

    def test_prepare_email_text_failure(self):
        custom_text = "The user with ${sender_id} has message ${user_message}."
        tracker_data = {'slot': {"email": "udit.pandey@digite.com", "firstname": "udit"},
                        'sender_id': "987654321", "intent": "greet", "user_message": "hello",
                        'key_vault': {'EMAIL': 'nkhare@digite.com', 'KEY_VAULT': '123456789-0lmgxzxdfghj',
                                      'AWS': '435fdr'}}
        responses.add(
            method=responses.POST,
            url=Utility.environment['evaluator']['url'],
            json={"success": False, "data": "The user with 987654321 has message hello."},
            status=200,
            match=[
                responses.matchers.json_params_matcher(
                    {'script': custom_text,
                     'data': tracker_data})],
        )
        responses.reset()


        Utility.email_conf['email']['templates']['custom_text_mail'] = open('template/emails/custom_text_mail.html', 'rb').read().decode()
        with pytest.raises(ActionFailure, match="Expression evaluation failed: script: The user with ${sender_id} has message ${user_message}. || data: {\'slot\': ' \
                      '{\'email\': \'udit.pandey@digite.com\', \'firstname\': \'udit\'}, \'sender_id\': \'987654321\', ' \
                      '\'intent\': \'greet\', \'user_message\': \'hello\', \'key_vault\': {\'EMAIL\': \'nkhare@digite.com\', ' \
                      '\'KEY_VAULT\': \'123456789-0lmgxzxdfghj\', \'AWS\': \'435fdr\'}} || raise_err_on_failure: True || response: ' \
                      '{\'success\': False, \'data\': \'The user with 987654321 has message hello.\'}"):
            ActionUtility.prepare_email_text(custom_text, tracker_data, "test@kairon.com")

    def test_prepare_email_text_failure_no_data(self):
        custom_text = "The user with ${sender_id} has message ${user_message}."
        tracker_data = {'slot': {"email": "udit.pandey@digite.com", "firstname": "udit"},
                        'sender_id': "987654321", "intent": "greet", "user_message": "hello",
                        'key_vault': {'EMAIL': 'nkhare@digite.com', 'KEY_VAULT': '123456789-0lmgxzxdfghj',
                                      'AWS': '435fdr'}}
        responses.add(
            method=responses.POST,
            url=Utility.environment['evaluator']['url'],
            json={"success": False},
            status=200,
            match=[
                responses.matchers.json_params_matcher(
                    {'script': custom_text,
                     'data': tracker_data})],
        )

        Utility.email_conf['email']['templates']['custom_text_mail'] = open('template/emails/custom_text_mail.html','rb').read().decode()
        with pytest.raises(ActionFailure, match="Expression evaluation failed: script: "
                                                "The user with ${sender_id} has message ${user_message}. || data: "
                                                "{'slot': {'email': 'udit.pandey@digite.com', 'firstname': 'udit'}, "
                                                "'sender_id': '987654321', 'intent': 'greet', 'user_message': 'hello', "
                                                "'key_vault': {'EMAIL': 'nkhare@digite.com', 'KEY_VAULT': '123456789-0lmgxzxdfghj', "
                                                "'AWS': '435fdr'}} || raise_err_on_failure: True || response: {'success': False, "
                                                "'data': 'The user with 987654321 has message hello."):
            ActionUtility.prepare_email_text(custom_text, tracker_data, "test@kairon.com")

    def test_compose_response_using_expression(self):
        response_config = {"value": "${data.a.b.d}", "evaluation_type": "expression"}
        http_response = {"data": {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}},
                         "context": {}}
        result, log = ActionUtility.compose_response(response_config, http_response)
        assert result == '[\'red\', \'buggy\', \'bumpers\']'
        assert log == "expression: ${data.a.b.d} || data: {'data': {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}, 'context': {}} || response: ['red', 'buggy', 'bumpers']"

    def test_compose_response_using_expression_failure(self):
        response_config = {"value": "${data.a.b.d}", "evaluation_type": "expression"}
        http_response = {"data": {'a': {'b': {'3': 2, '43': 30, 'c': []}}}, "context": {}}
        with pytest.raises(ActionFailure, match="Unable to retrieve value for key from HTTP response: 'd'"):
            ActionUtility.compose_response(response_config, http_response)

    @responses.activate
    def test_compose_response_using_script(self):
        script = "${a.b.d}"
        response_config = {"value": script, "evaluation_type": "script"}
        http_response = {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}
        responses.add(
            method=responses.POST,
            url=Utility.environment['evaluator']['url'],
            json={"success": True, "data": "['red', 'buggy', 'bumpers']"},
            status=200,
            match=[responses.matchers.json_params_matcher({'script': script, 'data': http_response})],
        )
        result, log = ActionUtility.compose_response(response_config, http_response)
        assert result == '[\'red\', \'buggy\', \'bumpers\']'
        assert log == 'script: ${a.b.d} || data: {\'a\': {\'b\': {\'3\': 2, \'43\': 30, \'c\': [], \'d\': [\'red\', \'buggy\', \'bumpers\']}}} || raise_err_on_failure: True || response: {\'success\': True, \'data\': "[\'red\', \'buggy\', \'bumpers\']"}'

    @responses.activate
    def test_compose_response_using_script_failure(self):
        script = "${a.b.d}"
        response_config = {"value": script, "evaluation_type": "script"}
        http_response = {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}
        responses.add(
            method=responses.POST,
            url=Utility.environment['evaluator']['url'],
            json={"success": False},
            status=200,
            match=[responses.matchers.json_params_matcher({'script': script, 'data': http_response})],
        )
        with pytest.raises(ActionFailure, match="Expression evaluation failed: script: ${a.b.d} || data: {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}} || raise_err_on_failure: True || response: {'success': False, 'data': \"['red', 'buggy', 'bumpers']\"}"):
            ActionUtility.compose_response(response_config, http_response)

    def test_fill_slots_from_response_using_expression(self):
        set_slots = [{"name": "experience", "value": "${data.a.b.d}"}, {"name": "score", "value": "${data.a.b.3}"}]
        http_response = {"data": {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}},
                         "context": {}}
        evaluated_slot_values, response_log = ActionUtility.fill_slots_from_response(set_slots, http_response)
        assert evaluated_slot_values == {'experience': "['red', 'buggy', 'bumpers']", 'score': '2'}
        assert response_log == ['initiating slot evaluation',
                                "slot: experience || expression: ${data.a.b.d} || data: {'data': {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}, 'context': {}} || response: ['red', 'buggy', 'bumpers']",
                                "slot: score || expression: ${data.a.b.3} || data: {'data': {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}, 'context': {}} || response: 2"]

    @responses.activate
    def test_fill_slots_from_response_using_script(self):
        set_slots = [{"name": "experience", "value": "${data.a.b.d}"}, {"name": "score", "value": "${data.a.b.3}"}]
        http_response = {"data": {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}},
                         "context": {}}
        responses.add(
            method=responses.POST,
            url=Utility.environment['evaluator']['url'],
            json={"success": True, "data": ['red', 'buggy', 'bumpers']},
            status=200,
            match=[responses.matchers.json_params_matcher({'script': "${a.b.d}", 'data': http_response})],
        )
        responses.add(
            method=responses.POST,
            url=Utility.environment['evaluator']['url'],
            json={"success": True, "data": 2},
            status=200,
            match=[responses.matchers.json_params_matcher({'script': "${a.b.3}", 'data': http_response})],
        )
        evaluated_slot_values, response_log = ActionUtility.fill_slots_from_response(set_slots, http_response)
        assert evaluated_slot_values == {'experience': "['red', 'buggy', 'bumpers']", 'score': '2'}
        assert response_log == ['initiating slot evaluation',
                                "slot: experience || expression: ${data.a.b.d} || data: {'data': {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}, 'context': {}} || response: ['red', 'buggy', 'bumpers']",
                                "slot: score || expression: ${data.a.b.3} || data: {'data': {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}, 'context': {}} || response: 2"]

    @responses.activate
    def test_fill_slots_from_response_failure(self):
        set_slots = [{"name": "experience", "value": "${data.a.b.d}", "evaluation_type": "script"},
                     {"name": "score", "value": "${data.a.b.3}", "evaluation_type": "script"},
                     {"name": "percentage", "value": "${data.a.b.43}"}]
        http_response = {"data": {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}},
                         "context": {}}
        responses.add(
            method=responses.POST,
            url=Utility.environment['evaluator']['url'],
            json={"success": False},
            status=200,
            match=[responses.matchers.json_params_matcher({'script': "${data.a.b.d}", 'data': http_response})],
        )
        responses.add(
            method=responses.POST,
            url=Utility.environment['evaluator']['url'],
            json={"success": True, "data": 2},
            status=200,
            match=[responses.matchers.json_params_matcher({'script': "${data.a.b.3}", 'data': http_response})],
        )
        evaluated_slot_values, response_log = ActionUtility.fill_slots_from_response(set_slots, http_response)
        assert evaluated_slot_values == {'experience': None, 'score': 2, "percentage": "30"}
        assert response_log == ['initiating slot evaluation',
                                "slot: experience || Expression evaluation failed: script: ${data.a.b.d} || data: {'data': {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}, 'context': {}} || raise_err_on_failure: True || response: {'success': False}",
                                "slot: score || script: ${data.a.b.3} || data: {'data': {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}, 'context': {}} || raise_err_on_failure: True || response: {'success': True, 'data': 2}",
                                "slot: percentage || expression: ${data.a.b.43} || data: {'data': {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}, 'context': {}} || response: 30"]
    
    def test_retrieve_config_two_stage_fallback(self):
        bot = "test_bot"
        user = "test_user"
        KaironTwoStageFallbackAction(
            text_recommendations={"count": 3}, trigger_rules=[
                {"text": "Trigger", "payload": "set_context"}, {"text": "Mail me", "payload": "send_mail"}
            ], bot=bot, user=user
        ).save()
        config = ActionTwoStageFallback(bot=bot, name=KAIRON_TWO_STAGE_FALLBACK).retrieve_config()
        config.pop('_id')
        config.pop('bot')
        config.pop('user')
        config.pop('timestamp')
        config.pop('status')
        assert config == {'name': 'kairon_two_stage_fallback', 'text_recommendations': {"count": 3, 'use_intent_ranking': False},
                          'trigger_rules': [{'is_dynamic_msg': False, 'text': 'Trigger', 'payload': 'set_context'},
                                            {'is_dynamic_msg': False, 'text': 'Mail me', 'payload': 'send_mail'}],
                          'fallback_message': "I could not understand you! Did you mean any of the suggestions below?"
                                              " Or else please rephrase your question."}

    def test_get_bot_settings(self):
        bot = "test_bot"
        bot_settings = ActionUtility.get_bot_settings(bot=bot)
        bot_settings.pop('timestamp')
        assert bot_settings == {'ignore_utterances': False, 'force_import': False, 'rephrase_response': False,
                                'website_data_generator_depth_search_limit': 2,
                                'chat_token_expiry': 30, 'llm_settings': {'enable_faq': False, 'provider': 'azure'},
                                'refresh_token_expiry': 60, 'whatsapp': 'meta',
                                'notification_scheduling_limit': 4, 'bot': 'test_bot', 'status': True}

    def test_get_prompt_action_config_2(self):
        bot = "test_bot_action_test"
        user = "test_user_action_test"
        llm_prompts = [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                              'source': 'static', 'is_enabled': True},
                             {'name': 'History Prompt', 'type': 'user', 'source': 'history', 'is_enabled': True}]
        PromptAction(name='kairon_faq_action', bot=bot, user=user, llm_prompts=llm_prompts).save()
        k_faq_action_config = ActionUtility.get_faq_action_config(bot, "kairon_faq_action")
        k_faq_action_config.pop('timestamp')
        assert k_faq_action_config == {'name': 'kairon_faq_action', 'num_bot_responses': 5, 'top_results': 10,
                                       'similarity_threshold': 0.7,
                                       'enable_response_cache': False,
                'failure_message': "I'm sorry, I didn't quite understand that. Could you rephrase?",
                                       'bot': 'test_bot_action_test', 'user': 'test_user_action_test',
                                       'hyperparameters': {'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-3.5-turbo',
                                                           'top_p': 0.0, 'n': 1, 'stream': False, 'stop': None,
                                                           'presence_penalty': 0.0, 'frequency_penalty': 0.0,
                                                           'logit_bias': {}},
                                       'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.',
                                                        'type': 'system', 'source': 'static', 'is_enabled': True},
                                                       {'name': 'History Prompt', 'type': 'user', 'source': 'history',
                                                        'is_enabled': True}],
                                       'status': True}

    def test_retrieve_config_two_stage_fallback_not_found(self):
        with pytest.raises(ActionFailure, match="Two stage fallback action config not found"):
            ActionTwoStageFallback(bot="test", name=KAIRON_TWO_STAGE_FALLBACK).retrieve_config()

    def test_failure_response_empty(self):
        action_name = "custom_search_action_no_results"
        bot = "5f50fd0a56b698ca10d35d2e"
        user = 'test_user'
        action = GoogleSearchAction(name=action_name, api_key=CustomActionRequestParameters(value='1234567890'),
                           search_engine_id='asdfg::123456', failure_response="", bot=bot, user=user)
        action.save()
        assert getattr(action, "failure_response") == 'I have failed to process your request.'

    def test_prepare_bot_responses_empty(self):
        events = []
        latest_message = {'text': 'what is kairon?s', 'intent_ranking': [{'name': 'nlu_fallback'}]}
        slots = {"bot": "5j59kk1a76b698ca10d35d2e", "param2": "param2value", "email": "nkhare@digite.com",
                 "firstname": "nupur"}
        tracker = Tracker(sender_id="sender1", slots=slots, events=events, paused=False, latest_message=latest_message,
                          followup_action=None, active_loop=None, latest_action_name=None)
        assert ActionUtility.prepare_bot_responses(tracker, 5) == []

    def test_prepare_bot_responses_bot_utterance_empty_and_jumbled(self):
        events = Utility.read_yaml("tests/testing_data/history/tracker_events_multiple_actions_predicted.json")
        latest_message = {'text': 'what is kairon?s', 'intent_ranking': [{'name': 'nlu_fallback'}]}
        slots = {"bot": "5j59kk1a76b698ca10d35d2e", "param2": "param2value", "email": "nkhare@digite.com",
                 "firstname": "nupur"}
        tracker = Tracker(sender_id="sender1", slots=slots, events=events, paused=False, latest_message=latest_message,
                          followup_action=None, active_loop=None, latest_action_name=None)
        bot_responses = ActionUtility.prepare_bot_responses(tracker, 5)
        assert bot_responses == [{'role': 'user', 'content': 'Kairon pricing'},
                                 {'role': 'assistant', 'content': "Kairon's pricing ranges from $60 to $160 per month for simple digital assistants, while more complex ones require custom pricing. However, since Kairon offers a large array of features to build digital assistants of varying complexity, the pricing may vary. If you are interested in Kairon, please provide your name, company name, and email address, and our sales team will reach out to you with more information."}]

    def test_if_last_n_is_less_than_or_equal_to_zero(self):
        events = Utility.read_yaml("tests/testing_data/history/bot_user_tracker_events.json")
        latest_message = {'text': 'what is kairon?s', 'intent_ranking': [{'name': 'nlu_fallback'}]}
        slots = {"bot": "5j59kk1a76b698ca10d35d2e", "param2": "param2value", "email": "nkhare@digite.com",
                 "firstname": "nupur"}
        tracker = Tracker(sender_id="sender1", slots=slots, events=events, paused=False, latest_message=latest_message,
                          followup_action=None, active_loop=None, latest_action_name=None)
        bot_responses = ActionUtility.prepare_bot_responses(tracker, 5)
        assert bot_responses == [{'role': 'user', 'content': 'How can I use it?'},
                                 {'role': 'assistant', 'content': 'It depends on what "it" refers to. Can you please provide more context or specify what you are referring to?'},
                                 {'role': 'user', 'content': 'How can I use kairon?'},
                                 {'role': 'assistant', 'content': "Kairon can be used to create and deploy digital assistants for various purposes, such as providing customer support, helping customers find the right products, processing orders, managing inventory, generating leads, promoting sales and discounts, gathering customer feedback, and analyzing customer data. Kairon's low-code/no-code interface makes it easy for functional users to define how the digital assistant responds to user queries without needing extensive coding skills. Additionally, Kairon's telemetry feature monitors how users are interacting with the website/product where Kairon was injected and proactively intervenes if they are facing problems, improving the overall user experience. To know more about Kairon, you can visit their website at https://www.digite.com/kairon/."},
                                 {'role': 'user', 'content': 'Is there any example for how can I use it?'},
                                 {'role': 'assistant', 'content': 'Yes, there are several examples provided in the context. For example, one article discusses how to integrate kAIron with Slack or Telegram to create a digital assistant or chatbot. Another article provides best practices and guidelines for building conversational interfaces using kAIron. Additionally, there are articles discussing the use of chatbots for millennials, the effectiveness of AI agents in intent generation, and the potential for conversational AI in the gaming world.'},
                                 {'role': 'user', 'content': 'I am interested in Kairon and want to know what features it offers'},
                                 {'role': 'assistant', 'content': 'Kairon is a versatile conversational digital transformation platform that offers a range of capabilities to businesses. Its features include end-to-end lifecycle management, tethered digital assistants, low-code/no-code interface, secure script injection, Kairon Telemetry, chat client designer, analytics module, robust integration suite, and real-time struggle analytics. Additionally, Kairon offers natural language processing, artificial intelligence, and machine learning for developing sophisticated chatbots for e-commerce purposes. Kairon chatbots can perform a wide range of tasks, including providing customer support, helping customers find the right products, answering customer queries, processing orders, managing inventory, generating leads, promoting sales and discounts, gathering customer feedback, analyzing customer data, and much more.'},
                                 {'role': 'user', 'content': 'What is kairon simply?'},
                                 {'role': 'assistant', 'content': 'Kairon is a digital transformation platform that simplifies the process of building, deploying, and monitoring digital assistants. It allows companies to create intelligent digital assistants without the need for separate infrastructure or technical expertise.'}
                                 ]

    def test_prepare_bot_responses_messages_pop(self):
        events = Utility.read_yaml("tests/testing_data/history/tracker_file.json")
        latest_message = {'text': 'what is kairon?s', 'intent_ranking': [{'name': 'nlu_fallback'}]}
        slots = {"bot": "5j59kk1a76b698ca10d35d2e", "param2": "param2value", "email": "nkhare@digite.com",
                 "firstname": "nupur"}
        tracker = Tracker(sender_id="sender1", slots=slots, events=events, paused=False, latest_message=latest_message,
                          followup_action=None, active_loop=None, latest_action_name=None)
        bot_responses = ActionUtility.prepare_bot_responses(tracker, 5)
        assert bot_responses == [
            {'role': 'assistant', 'content': 'Kairon is a versatile conversational digital transformation platform '
                                             'that offers a range of capabilities to businesses. Its features include '
                                             'end-to-end lifecycle management, tethered digital assistants, '
                                             'low-code/no-code interface, secure script injection, Kairon Telemetry, '
                                             'chat client designer, analytics module, robust integration suite, '
                                             'and real-time struggle analytics. Additionally, Kairon offers natural '
                                             'language processing, artificial intelligence, and machine learning for '
                                             'developing sophisticated chatbots for e-commerce purposes. Kairon '
                                             'chatbots can perform a wide range of tasks, including providing '
                                             'customer support, helping customers find the right products, '
                                             'answering customer queries, processing orders, managing inventory, '
                                             'generating leads, promoting sales and discounts, gathering customer '
                                             'feedback, analyzing customer data, and much more.'},
            {'role': 'user', 'content': 'I am interested in Kairon and want to know what features it offers'}
        ]
