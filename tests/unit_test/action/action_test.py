import json
import os
import urllib.parse

from googleapiclient.http import HttpRequest
from pipedrive.exceptions import UnauthorizedError, BadRequestError

from kairon.shared.data.data_objects import Slots

os.environ["system_file"] = "./tests/testing_data/system.yaml"
from typing import Dict, Text, Any, List

import pytest
import responses
from mongoengine import connect, QuerySet
from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher
from kairon.shared.actions.models import ActionType
from kairon.shared.actions.data_objects import HttpActionRequestBody, HttpActionConfig, ActionServerLogs, SlotSetAction, \
    Actions, FormValidationAction, EmailActionConfig, GoogleSearchAction, JiraAction, ZendeskAction, \
    PipedriveLeadsAction, SetSlots
from kairon.actions.handlers.processor import ActionProcessor
from kairon.shared.actions.utils import ActionUtility, ExpressionEvaluator
from kairon.shared.actions.exception import ActionFailure
from kairon.shared.utils import Utility
import requests
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
            raise ActionFailure("No HTTP action found for bot and action")

        monkeypatch.setattr(ActionUtility, "get_action_config", _raise_excep)

    @responses.activate
    def test_execute_http_request_get_with_auth_token(self):
        http_url = 'http://localhost:8080/mock'
        # file deepcode ignore HardcodedNonCryptoSecret: Random string for testing
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
                                                      request_method=responses.GET)
        assert response
        assert response['data'] == 'test_data'
        assert len(response['test_class']) == 2
        assert response['test_class'][1]['key2'] == 'value2'
        assert responses.calls[0].request.headers['Authorization'] == auth_token

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

    def test_prepare_url_with_get(self):
        from urllib.parse import urlencode, quote_plus

        http_url = 'http://localhost:8080/mock'
        params = {"test": "val1", "test2": "val2"}
        updated_url = ActionUtility.prepare_url('GET', http_url, params)
        assert updated_url == http_url + "?" + urlencode(params, quote_via=quote_plus)

    def test_prepare_url_with_post(self):
        from urllib.parse import urlencode, quote_plus

        http_url = 'http://localhost:8080/mock'
        params = {"test": "val1", "test2": "val2"}
        updated_url = ActionUtility.prepare_url('POST', http_url, params)
        assert updated_url == http_url

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
            match=[responses.json_params_matcher(request_params)],
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
            match=[responses.json_params_matcher(request_params)]
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
            match=[responses.json_params_matcher(request_params)],
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
            match=[responses.json_params_matcher(request_params)]
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
            match=[responses.json_params_matcher(request_params)],
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
                responses.json_params_matcher(request_params)
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
                responses.json_params_matcher(request_params)
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
            response="json",
            http_url="http://test.com",
            request_method="GET",
            params_list=http_params,
            bot="bot",
            user="user"
        ).save().to_mongo().to_dict()

        actual = ActionUtility.get_http_action_config("bot", "http_action")
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
            response="${RESPONSE}",
            http_url="http://www.digite.com",
            request_method="POST",
            params_list=http_params,
            bot="bot",
            user="user",
            status=False
        ).save().to_mongo().to_dict()
        expected = HttpActionConfig(
            action_name="test_get_http_action_config_deleted_action",
            response="json",
            http_url="http://test.com",
            request_method="GET",
            params_list=http_params,
            bot="bot",
            user="user"
        ).save().to_mongo().to_dict()

        actual = ActionUtility.get_http_action_config("bot", "test_get_http_action_config_deleted_action")
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
            ActionUtility.get_action_config(bot=None, name="http_action")
            assert False
        except ActionFailure as ex:
            assert str(ex) == "Bot and action name are required for fetching configuration"

    def test_get_http_action_no_http_action(self):
        try:
            ActionUtility.get_action_config(bot="bot", name=None)
            assert False
        except ActionFailure as ex:
            assert str(ex) == "Bot and action name are required for fetching configuration"

    def test_get_http_action_invalid_bot(self):
        http_params = [HttpActionRequestBody(key="key1", value="value1", parameter_type="slot"),
                       HttpActionRequestBody(key="key2", value="value2")]
        HttpActionConfig(
            action_name="http_action",
            response="json",
            http_url="http://test.com",
            request_method="GET",
            params_list=http_params,
            bot="bot",
            user="user"
        ).save().to_mongo().to_dict()

        try:
            ActionUtility.get_http_action_config("bot1", "http_action")
            assert False
        except ActionFailure as ex:
            assert str(ex).__contains__("No HTTP action found for bot")

    def test_get_http_action_invalid_http_action(self):
        http_params = [HttpActionRequestBody(key="key1", value="value1", parameter_type="slot"),
                       HttpActionRequestBody(key="key2", value="value2")]
        HttpActionConfig(
            action_name="http_action",
            response="json",
            http_url="http://test.com",
            request_method="GET",
            params_list=http_params,
            bot="bot",
            user="user"
        ).save().to_mongo().to_dict()

        try:
            ActionUtility.get_http_action_config("bot", "http_action1")
            assert False
        except ActionFailure as ex:
            assert str(ex).__contains__("No HTTP action found for bot")

    def test_get_http_action_no_request_body(self):
        http_params = []
        HttpActionConfig(
            action_name="http_action",
            response="json",
            http_url="http://test.com",
            request_method="GET",
            params_list=http_params,
            bot="bot",
            user="user"
        ).save().to_mongo().to_dict()

        try:
            ActionUtility.get_http_action_config("bot", "http_action1")
            assert False
        except ActionFailure as ex:
            assert str(ex).__contains__("No HTTP action found for bot")

    def test_prepare_header_no_header(self):
        slots = {"bot": "demo_bot", "http_action_config": "http_action_name", "slot_name": "param2value"}
        events = [{"event1": "hello"}, {"event2": "how are you"}]
        tracker = Tracker(sender_id="sender1", slots=slots, events=events, paused=False, latest_message=None,
                          followup_action=None, active_loop=None, latest_action_name=None)
        actual = ActionUtility.prepare_request(tracker, None)
        assert actual == {}

    def test_prepare_request(self):
        slots = {"bot": "demo_bot", "http_action_config": "http_action_name", "slot_name": "param2value"}
        events = [{"event1": "hello"}, {"event2": "how are you"}]
        http_action_config_params = [HttpActionRequestBody(key="param1", value="value1"),
                                     HttpActionRequestBody(key="param2", value="slot_name", parameter_type="slot")]
        tracker = Tracker(sender_id="sender1", slots=slots, events=events, paused=False, latest_message=None,
                          followup_action=None, active_loop=None, latest_action_name=None)
        actual_request_body = ActionUtility.prepare_request(tracker=tracker,
                                                            http_action_config_params=http_action_config_params)
        assert actual_request_body
        assert actual_request_body['param1'] == 'value1'
        assert actual_request_body['param2'] == 'param2value'

    def test_prepare_request_empty_slot(self):
        slots = {"bot": "demo_bot", "http_action_config": "http_action_name", "param2": "param2value"}
        events = [{"event1": "hello"}, {"event2": "how are you"}]
        http_action_config_params = [HttpActionRequestBody(key="param1", value="value1"),
                                     HttpActionRequestBody(key="param3", value="", parameter_type="slot")]
        tracker = Tracker(sender_id="sender1", slots=slots, events=events, paused=False, latest_message=None,
                          followup_action=None, active_loop=None, latest_action_name=None)
        request_params = ActionUtility.prepare_request(tracker=tracker,
                                                       http_action_config_params=http_action_config_params)
        assert request_params['param1'] == "value1"
        assert not request_params['param3']

    def test_prepare_request_sender_id(self):
        slots = {"bot": "demo_bot", "http_action_config": "http_action_name", "param2": "param2value"}
        events = [{"event1": "hello"}, {"event2": "how are you"}]
        http_action_config_params = [HttpActionRequestBody(key="param1", value="value1"),
                                     HttpActionRequestBody(key="user_id", value="", parameter_type="sender_id")]
        tracker = Tracker(sender_id="kairon_user@digite.com", slots=slots, events=events, paused=False,
                          latest_message=None,
                          followup_action=None, active_loop=None, latest_action_name=None)
        request_params = ActionUtility.prepare_request(tracker=tracker,
                                                       http_action_config_params=http_action_config_params)
        assert request_params['param1'] == "value1"
        assert request_params['user_id'] == "kairon_user@digite.com"

    def test_prepare_request_with_intent(self):
        slots = {"bot": "demo_bot", "http_action_config": "http_action_name", "param2": "param2value"}
        events = [{"event1": "hello"}, {"event2": "how are you"}]
        http_action_config_params = [HttpActionRequestBody(key="param1", value="value1"),
                                     HttpActionRequestBody(key="card_type", parameter_type="intent")]
        tracker = Tracker(sender_id="kairon_user@digite.com", slots=slots, events=events, paused=False,
                          latest_message={'intent': {'name': 'credit_card', 'confidence': 1.0}, 'entities': [],
                                          'text': '/restart', 'message_id': 'f4341cbf3eb1446e889a69d768ac091c',
                                          'metadata': {}, 'intent_ranking': [{'name': 'restart', 'confidence': 1.0}]},
                          followup_action=None, active_loop=None, latest_action_name='action_listen')
        request_params = ActionUtility.prepare_request(tracker=tracker,
                                                       http_action_config_params=http_action_config_params)
        assert request_params['param1'] == "value1"
        assert request_params['card_type'] == "restart"

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
        tracker = Tracker(sender_id="kairon_user@digite.com", slots=slots, events=events, paused=False,
                          latest_message={'intent': {'name': 'restart', 'confidence': 1.0}, 'entities': [],
                                          'text': '/restart', 'message_id': 'f4341cbf3eb1446e889a69d768ac091c',
                                          'metadata': {}, 'intent_ranking': [{'name': 'restart', 'confidence': 1.0}]},
                          followup_action=None, active_loop=None, latest_action_name='action_listen')
        request_params = ActionUtility.prepare_request(tracker=tracker,
                                                       http_action_config_params=http_action_config_params)
        assert request_params == {'intent': 'restart', 'user_msg': {'sender_id': 'kairon_user@digite.com',
                                                                    'session_started': '2021-12-31 16:59:38',
                                                                    'conversation': [{'user': 'hi'},
                                                                                     {'bot': 'are you ok?'},
                                                                                     {'user': 'yes'},
                                                                                     {'bot': 'Great, carry on!'},
                                                                                     {'user': '/restart'}]}}

    def test_prepare_request_user_message(self):
        http_action_config_params = [HttpActionRequestBody(key="param1", value="value1"),
                                     HttpActionRequestBody(key="msg", parameter_type="user_message")]
        tracker = Tracker(sender_id="kairon_user@digite.com", slots=None, events=None, paused=False,
                          latest_message={'intent': {'name': 'google_search', 'confidence': 1.0},
                                          'entities': [],
                                          'text': 'perform google search',
                                          'message_id': 'd965c5dd62034dbc9bb76b64b4571434',
                                          'metadata': {},
                                          'intent_ranking': [{'name': 'google_search', 'confidence': 1.0}]},
                          followup_action=None, active_loop=None, latest_action_name=None)
        request_params = ActionUtility.prepare_request(tracker=tracker,
                                                       http_action_config_params=http_action_config_params)
        assert request_params['param1'] == "value1"
        assert request_params['msg'] == "perform google search"

        tracker = Tracker(sender_id="kairon_user@digite.com", slots=None, events=None, paused=False,
                          latest_message={'intent': {'name': 'google_search', 'confidence': 1.0},
                                          'entities': [],
                                          'text': None,
                                          'message_id': 'd965c5dd62034dbc9bb76b64b4571434',
                                          'metadata': {},
                                          'intent_ranking': [{'name': 'google_search', 'confidence': 1.0}]},
                          followup_action=None, active_loop=None, latest_action_name=None)
        request_params = ActionUtility.prepare_request(tracker=tracker,
                                                       http_action_config_params=http_action_config_params)
        assert request_params['param1'] == "value1"
        assert not request_params['msg']

    def test_prepare_request_no_request_params(self):
        slots = {"bot": "demo_bot", "http_action_config": "http_action_name", "param2": "param2value"}
        events: List[Dict] = None
        http_action_config_params: List[HttpActionRequestBody] = None
        tracker = Tracker(sender_id="sender1", slots=slots, events=events, paused=False, latest_message=None,
                          followup_action=None, active_loop=None, latest_action_name=None)
        actual_request_body = ActionUtility.prepare_request(tracker=tracker,
                                                            http_action_config_params=http_action_config_params)
        #  deepcode ignore C1801: empty request body for http request with no request body params
        assert len(actual_request_body) == 0

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
        response = ActionUtility.prepare_response("The value of ${a.b.3} in ${a.b.d.0} is ${a.b.c}", json1)
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
        try:
            ActionUtility.prepare_response("The value of ${a.b.3} in ${a.b.d.0} is ${a.b.e}", json1)
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
        response = ActionUtility.prepare_response("The value of red is 0", json1)
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
        response = ActionUtility.prepare_response("", json1)
        assert response == '{"a": {"b": {"3": 2, "43": 30, "c": [], "d": ["red", "buggy", "bumpers"]}}}'

    def test_prepare_response_string_empty_request_output(self):
        json1 = json.dumps("{}")
        try:
            ActionUtility.prepare_response("The value of ${a.b.3} in ${a.b.d.0} is ${a.b.e}", json1)
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
        response = ActionUtility.prepare_response("The value of 2 in red is []", json_as_string)
        assert response == 'The value of 2 in red is []'

    def test_prepare_response_as_string_and_expected_as_none(self):
        response = ActionUtility.prepare_response("The value of 2 in red is []", None)
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
            response="json",
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
        assert log['exception'].__contains__('No HTTP action found for bot')

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
            response=http_response,
            http_url=http_url,
            request_method="GET",
            params_list=None,
            bot="5f50fd0a56b698ca10d35d2e",
            user="user"
        )

        def _get_action(*arge, **kwargs):
            return action.to_mongo().to_dict(), ActionType.http_action.value

        monkeypatch.setattr(ActionUtility, "get_action_config", _get_action)
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
        from urllib.parse import urlencode, quote_plus
        http_url = "http://www.google.com"
        http_response = "This should be response"
        request_params = [HttpActionRequestBody(key='key1', value="value1"),
                          HttpActionRequestBody(key='key2', value="value2")]
        action = HttpActionConfig(
            action_name="http_action_with_params",
            response=http_response,
            http_url=http_url,
            request_method="GET",
            params_list=request_params,
            bot="5f50fd0a56b698ca10d35d2e",
            user="user"
        )

        def _get_action(*arge, **kwargs):
            return action.to_mongo().to_dict(), ActionType.http_action.value

        monkeypatch.setattr(ActionUtility, "get_action_config", _get_action)
        responses.start()
        responses.add(
            method=responses.GET,
            url=http_url,
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
        assert log['url'] == http_url + "?" + urlencode({"key1": "value1", "key2": "value2"}, quote_via=quote_plus)
        assert not log['request_params']

    @pytest.mark.asyncio
    async def test_run_with_post(self, monkeypatch):
        action = HttpActionConfig(
            action_name="test_run_with_post",
            response="Data added successfully, id:${RESPONSE}",
            http_url="http://localhost:8080/mock",
            request_method="POST",
            params_list=None,
            bot="5f50fd0a56b698ca10d35d2e",
            user="user"
        )

        def _get_action(*arge, **kwargs):
            return action.to_mongo().to_dict(), ActionType.http_action.value

        monkeypatch.setattr(ActionUtility, "get_action_config", _get_action)
        http_url = 'http://localhost:8080/mock'
        resp_msg = "5000"
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
            action_name="test_run_with_post",
            response="Data added successfully, id:${RESPONSE}",
            http_url="http://localhost:8080/mock",
            request_method="POST",
            params_list=request_params,
            bot="5f50fd0a56b698ca10d35d2e",
            user="user"
        )

        def _get_action(*arge, **kwargs):
            return action.to_mongo().to_dict(), ActionType.http_action.value

        monkeypatch.setattr(ActionUtility, "get_action_config", _get_action)
        http_url = 'http://localhost:8080/mock'
        resp_msg = "5000"
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
                                                                             "test_run_with_post")
        responses.stop()
        assert actual is not None
        assert str(actual[0]['name']) == 'kairon_action_response'
        assert str(actual[0]['value']) == 'Data added successfully, id:5000'
        log = ActionServerLogs.objects(sender="sender_test_run_with_post",
                                       action="test_run_with_post",
                                       status="SUCCESS").get()
        assert not log['exception']
        assert log['timestamp']
        assert log['intent'] == "test_run"
        assert log['action'] == "test_run_with_post"
        assert log['request_params'] == {"key1": "value1", "key2": "value2"}
        assert log['api_response'] == '5000'
        assert log['bot_response'] == 'Data added successfully, id:5000'

    @pytest.mark.asyncio
    async def test_run_with_get(self, monkeypatch):
        action = HttpActionConfig(
            action_name="test_run_with_get",
            response="The value of ${a.b.3} in ${a.b.d.0} is ${a.b.d}",
            http_url="http://localhost:8081/mock",
            request_method="GET",
            params_list=None,
            bot="5f50fd0a56b698ca10d35d2e",
            user="user"
        )

        def _get_action(*arge, **kwargs):
            return action.to_mongo().to_dict(), ActionType.http_action.value

        monkeypatch.setattr(ActionUtility, "get_action_config", _get_action)
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
        responses.start()
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
        responses.stop()
        assert actual is not None
        assert str(actual[0]['name']) == 'kairon_action_response'
        assert str(actual[0]['value']) == 'The value of 2 in red is [\'red\', \'buggy\', \'bumpers\']'

    @pytest.mark.asyncio
    async def test_run_no_connection(self, monkeypatch):
        action_name = "test_run_with_post"
        action = HttpActionConfig(
            action_name=action_name,
            response="This should be response",
            http_url="http://localhost:8085/mock",
            request_method="GET",
            params_list=None,
            bot="5f50fd0a56b698ca10d35d2e",
            user="user"
        )

        def _get_action(*arge, **kwargs):
            return action.to_mongo().to_dict(), ActionType.http_action.value

        monkeypatch.setattr(ActionUtility, "get_action_config", _get_action)
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
            response="The value of ${a.b.3} in ${a.b.d.0} is ${a.b.d}",
            http_url="http://localhost:8080/mock",
            request_method="GET",
            params_list=None,
            bot="5f50fd0a56b698ca10d35d2e",
            user="user"
        )

        def _get_action(*arge, **kwargs):
            return action.to_mongo().to_dict(), ActionType.http_action.value

        monkeypatch.setattr(ActionUtility, "get_action_config", _get_action)
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
        output = ActionUtility.attach_response("This has no placeholder", {"a": "b"})
        assert output == "This has no placeholder"

    def test_attach_response(self):
        output = ActionUtility.attach_response("I want $${RESPONSE}", {"dollars": "51"})
        assert output == 'I want ${\'dollars\': \'51\'}'

    def test_attach_response_int(self):
        output = ActionUtility.attach_response("I want $${RESPONSE}", 51)
        assert output == 'I want $51'

    def test_prepare_response_with_prefix(self):
        output = ActionUtility.prepare_response("I want rupee${price.1.rupee}. Also, want $${price.0.dollars}",
                                                {"price": [{"dollars": "51"}, {"rupee": "151"}]})
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

    @pytest.mark.asyncio
    async def test_run_get_with_parameters(self, monkeypatch):
        request_params = [HttpActionRequestBody(key='key1', value="value1"),
                          HttpActionRequestBody(key='key2', value="value2")]
        action = HttpActionConfig(
            action_name="test_run_get_with_parameters",
            response="The value of ${a.b.3} in ${a.b.d.0} is ${a.b.d}",
            http_url="http://localhost:8081/mock",
            request_method="GET",
            params_list=request_params,
            bot="5f50fd0a56b698ca10d35d2e",
            user="user"
        )

        def _get_action(*arge, **kwargs):
            return action.to_mongo().to_dict(), ActionType.http_action.value

        monkeypatch.setattr(ActionUtility, "get_action_config", _get_action)
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

        class MockResponse(object):
            def __init__(self, url, headers):
                self.status_code = 200
                self.url = url
                self.headers = headers

            def json(self):
                return resp_msg

            def text(self):
                return json.dumps(resp_msg)

        def mock_get(url, headers):
            if headers and url == http_url + '?' + urllib.parse.urlencode({'key1': 'value1', 'key2': 'value2'}):
                return MockResponse(url, headers)

        monkeypatch.setattr(requests, "get", mock_get)
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
        assert str(actual[0]['name']) == 'kairon_action_response'
        assert str(actual[0]['value']) == 'The value of 2 in red is [\'red\', \'buggy\', \'bumpers\']'

    @pytest.mark.asyncio
    async def test_run_get_with_parameters(self, monkeypatch):
        action = HttpActionConfig(
            action_name="test_run_get_with_parameters",
            response="The value of ${a.b.3} in ${a.b.d.0} is ${a.b.d}",
            http_url="http://localhost:8081/mock",
            request_method="GET",
            params_list=None,
            bot="5f50fd0a56b698ca10d35d2e",
            user="user"
        )

        def _get_action(*arge, **kwargs):
            return action.to_mongo().to_dict(), ActionType.http_action.value

        monkeypatch.setattr(ActionUtility, "get_action_config", _get_action)
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

        class MockResponse(object):
            def __init__(self, url, headers):
                self.status_code = 200
                self.url = url
                self.headers = headers

            def json(self):
                return resp_msg

            def text(self):
                return json.dumps(resp_msg)

        def mock_get(url, headers):
            if url == http_url:
                return MockResponse(url, headers)

        monkeypatch.setattr(requests, "get", mock_get)
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

        def _get_action(*arge, **kwargs):
            return action.to_mongo().to_dict(), ActionType.slot_set_action.value

        monkeypatch.setattr(ActionUtility, "get_action_config", _get_action)
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
            return action.to_mongo().to_dict(), ActionType.slot_set_action.value

        monkeypatch.setattr(ActionUtility, "get_action_config", _get_action)
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

        monkeypatch.setattr(ActionUtility, "get_action_config", _get_action)
        slots = {"bot": "5f50fd0a56b698ca10d35d2e", "location": None, "current_location": 'Mumbai'}
        events = [{"event1": "hello"}, {"event2": "how are you"}]
        dispatcher: CollectingDispatcher = CollectingDispatcher()
        latest_message = {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]}
        tracker = Tracker(sender_id="sender1", slots=slots, events=events, paused=False, latest_message=latest_message,
                          followup_action=None, active_loop=None, latest_action_name=None)
        domain: Dict[Text, Any] = None
        actual: List[Dict[Text, Any]] = await ActionProcessor.process_action(dispatcher, tracker, domain, action_name)
        assert actual is None

    def test_get_action_config_slot_set_action(self):
        bot = 'test_actions'
        user = 'test'
        Actions(name='action_get_user', type=ActionType.slot_set_action.value, bot=bot, user=user).save()
        SlotSetAction(name='action_get_user', set_slots=[SetSlots(name='user', type='from_value', value='name')],
                      bot=bot, user=user).save()
        config, action_type = ActionUtility.get_action_config(bot, 'action_get_user')
        assert config['name'] == 'action_get_user'
        assert config['set_slots'] == [{'name': 'user', 'type': 'from_value', 'value': 'name'}]
        assert action_type == ActionType.slot_set_action.value

    def test_get_action_config_http_action(self):
        bot = 'test_actions'
        user = 'test'
        Actions(name='action_hit_endpoint', type=ActionType.http_action.value, bot=bot, user=user).save()
        HttpActionConfig(
            action_name="action_hit_endpoint",
            response="json",
            http_url="http://test.com",
            request_method="GET",
            bot=bot,
            user=user
        ).save()

        config, action_type = ActionUtility.get_action_config(bot, 'action_hit_endpoint')
        assert config['action_name'] == 'action_hit_endpoint'
        assert config['response'] == 'json'
        assert config['http_url'] == "http://test.com"
        assert config['request_method'] == 'GET'
        assert action_type == ActionType.http_action.value

    def test_get_action_config_action_does_not_exists(self):
        bot = 'test_actions'
        with pytest.raises(ActionFailure, match='No action found for bot'):
            ActionUtility.get_action_config(bot, 'test_get_action_config_action_does_not_exists')

    def test_get_action_config_slot_set_action_does_not_exists(self):
        bot = 'test_actions'
        user = 'test'
        Actions(name='test_get_action_config_slot_set_action_does_not_exists',
                type=ActionType.slot_set_action.value, bot=bot, user=user).save()
        with pytest.raises(ActionFailure, match='No slot set action found for bot'):
            ActionUtility.get_action_config(bot, 'test_get_action_config_slot_set_action_does_not_exists')

    def test_get_action_config_http_action_does_not_exists(self):
        bot = 'test_actions'
        user = 'test'
        Actions(name='test_get_action_config_http_action_does_not_exists',
                type=ActionType.http_action.value, bot=bot, user=user).save()
        with pytest.raises(ActionFailure, match='No HTTP action found for bot'):
            ActionUtility.get_action_config(bot, 'test_get_action_config_http_action_does_not_exists')

    def test_get_http_action_config_bot_empty(self):
        with pytest.raises(ActionFailure, match='Bot name and action name are required'):
            ActionUtility.get_http_action_config(' ', 'test_get_action_config_http_action_does_not_exists')

    def test_get_http_action_config_action_empty(self):
        with pytest.raises(ActionFailure, match='Bot name and action name are required'):
            ActionUtility.get_http_action_config('test_get_action_config_http_action_does_not_exists', ' ')

    def test_get_action_config_custom_user_action(self):
        bot = 'test_actions'
        user = 'test'
        Actions(name='test_get_action_config_custom_user_action', bot=bot, user=user).save()
        with pytest.raises(ActionFailure, match='None action is not supported with action server'):
            ActionUtility.get_action_config(bot, 'test_get_action_config_custom_user_action')

    def test_get_form_validation_config_single_validation(self):
        bot = 'test_actions'
        user = 'test'
        validation_semantic = {'or': [{'less_than': '5'}, {'==': 6}]}
        expected_output = FormValidationAction(name='validate_form', slot='name',
                                               validation_semantic=validation_semantic,
                                               bot=bot, user=user).save().to_mongo().to_dict()
        config = ActionUtility.get_form_validation_config(bot, 'validate_form').get().to_mongo().to_dict()
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
        config = ActionUtility.get_form_validation_config(bot, 'validate_form_1').to_json()
        config = json.loads(config)
        for c in config:
            c.pop('timestamp')
            c.pop('_id')
        assert config[0] == expected_outputs[0]
        assert config[1] == expected_outputs[1]
        assert config[2] == expected_outputs[2]

    def test_get_form_validation_config_not_exists(self):
        bot = 'test_actions'
        config = ActionUtility.get_form_validation_config(bot, 'validate_form_2')
        assert not config
        assert isinstance(config, QuerySet)

    def test_get_action_config_form_validation(self):
        bot = 'test_actions'
        user = 'test'
        Actions(name='validate_form_1', type=ActionType.form_validation_action.value, bot=bot, user=user).save()
        config, action_type = ActionUtility.get_action_config(bot, 'validate_form_1')
        assert config[0]
        assert config[1]
        assert config[2]
        assert action_type == ActionType.form_validation_action.value

    def test_get_action_config_form_validation_not_exists(self):
        bot = 'test_actions'
        user = 'test'
        Actions(name='validate_form_2', type=ActionType.form_validation_action.value, bot=bot, user=user).save()
        config, action_type = ActionUtility.get_action_config(bot, 'validate_form_2')
        assert not config
        assert action_type == ActionType.form_validation_action.value

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

    def test_is_valid_slot_value_multiple_expressions_1(self):
        slot_type = 'text'
        slot_value = 'valid_slot_value'
        semantic_expression = {'and': [{'operator': '==', 'value': 'valid_slot_value'},
                                       {'operator': 'contains', 'value': '_slot_'},
                                       {'operator': 'in', 'value': ['valid_slot_value', 'slot_value']},
                                       {'operator': 'startswith', 'value': 'valid'},
                                       {'operator': 'endswith', 'value': 'value'},
                                       {'operator': 'has_length', 'value': 16},
                                       {'operator': 'has_length_greater_than', 'value': 15},
                                       {'operator': 'has_length_less_than', 'value': 20},
                                       {'operator': 'has_no_whitespace'},
                                       {'operator': 'matches_regex', 'value': '^[v]+.*[e]$'}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert final_expr == '{("valid_slot_value" == "valid_slot_value")and("_slot_" in "valid_slot_value")and("valid_slot_value" in [\'valid_slot_value\', \'slot_value\'])and("valid_slot_value".startswith("valid"))and("valid_slot_value".endswith("value"))and(len("valid_slot_value") == 16)and(len("valid_slot_value") > 15)and(len("valid_slot_value") < 20)and(" " not in "valid_slot_value")and(valid_slot_value.matches_regex(^[v]+.*[e]$))}'
        assert is_slot_data_valid

        semantic_expression = {'or': [{'operator': '==', 'value': 'valid_slot_value'},
                                      {'operator': 'is_an_email_address'}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert final_expr == '{("valid_slot_value" == "valid_slot_value")or(is_an_email_address(valid_slot_value))}'
        assert is_slot_data_valid

    def test_is_valid_slot_value_multiple_expressions_2(self):
        slot_type = 'text'
        slot_value = 'valid_slot_value'
        semantic_expression = {'and': [{'and': [{'operator': 'contains', 'value': '_slot_'},
                                                {'operator': 'in', 'value': ['valid_slot_value', 'slot_value']},
                                                {'operator': 'startswith', 'value': 'valid'},
                                                {'operator': 'endswith', 'value': 'value'},
                                                ]},
                                       {'or': [{'operator': 'has_length_greater_than', 'value': 20},
                                               {'operator': 'has_no_whitespace'},
                                               {'operator': 'matches_regex', 'value': '^[e]+.*[e]$'}]}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert is_slot_data_valid
        assert final_expr == '{{("_slot_" in "valid_slot_value")and("valid_slot_value" in [\'valid_slot_value\', \'slot_value\'])and("valid_slot_value".startswith("valid"))and("valid_slot_value".endswith("value"))}and{(len("valid_slot_value") > 20)or(" " not in "valid_slot_value")or(valid_slot_value.matches_regex(^[e]+.*[e]$))}}'

        semantic_expression = {'and': [{'and': [{'operator': 'contains', 'value': '_slot_'},
                                                {'operator': 'in', 'value': ['valid_slot_value', 'slot_value']},
                                                {'operator': 'startswith', 'value': 'valid'},
                                                {'operator': 'endswith', 'value': 'value'},
                                                ]},
                                       {'or': [{'operator': 'has_length_greater_than', 'value': 20},
                                               {'operator': 'is_an_email_address'},
                                               {'operator': 'matches_regex', 'value': '^[e]+.*[e]$'}]}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert not is_slot_data_valid
        assert final_expr == '{{("_slot_" in "valid_slot_value")and("valid_slot_value" in [\'valid_slot_value\', \'slot_value\'])and("valid_slot_value".startswith("valid"))and("valid_slot_value".endswith("value"))}and{(len("valid_slot_value") > 20)or(is_an_email_address(valid_slot_value))or(valid_slot_value.matches_regex(^[e]+.*[e]$))}}'

    def test_is_valid_slot_value_text_type(self):
        slot_type = 'text'
        slot_value = 'valid_slot_value'

        semantic_expression = {'and': [{'operator': 'matches_regex', 'value': '^[r]+.*[e]$'}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert final_expr == '{(valid_slot_value.matches_regex(^[r]+.*[e]$))}'
        assert not is_slot_data_valid

        semantic_expression = {'and': [{'operator': 'matches_regex', 'value': '^[v]+.*[e]$'}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert is_slot_data_valid
        assert final_expr == '{(valid_slot_value.matches_regex(^[v]+.*[e]$))}'

        semantic_expression = {'and': [{'operator': 'is_an_email_address'}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, 'pandey.udit867@gmail.com',
                                                                                 semantic_expression)
        assert is_slot_data_valid
        assert final_expr == '{(is_an_email_address(pandey.udit867@gmail.com))}'
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert not is_slot_data_valid
        assert final_expr == '{(is_an_email_address(valid_slot_value))}'

        semantic_expression = {'and': [{'operator': '==', 'value': 'valid_slot_value'}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert final_expr == '{("valid_slot_value" == "valid_slot_value")}'
        assert is_slot_data_valid

        semantic_expression = {'and': [{'operator': '!=', 'value': 'valid_slot_value'}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert final_expr == '{("valid_slot_value" != "valid_slot_value")}'
        assert not is_slot_data_valid

        semantic_expression = {'and': [{'operator': 'contains', 'value': 'valid'}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert is_slot_data_valid
        assert final_expr == '{("valid" in "valid_slot_value")}'

        semantic_expression = {'and': [{'operator': 'contains', 'value': 'not_present'}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert not is_slot_data_valid
        assert final_expr == '{("not_present" in "valid_slot_value")}'

        semantic_expression = {'and': [{'operator': 'in', 'value': ['valid_slot_value', 'slot_value']}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert is_slot_data_valid
        assert final_expr == '{("valid_slot_value" in [\'valid_slot_value\', \'slot_value\'])}'

        semantic_expression = {'and': [{'operator': 'in', 'value': ['another_value', 'slot_value']}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert not is_slot_data_valid
        assert final_expr == '{("valid_slot_value" in [\'another_value\', \'slot_value\'])}'

        semantic_expression = {'and': [{'operator': 'startswith', 'value': 'valid'}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert is_slot_data_valid
        assert final_expr == '{("valid_slot_value".startswith("valid"))}'

        semantic_expression = {'and': [{'operator': 'startswith', 'value': 'slot'}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert not is_slot_data_valid
        assert final_expr == '{("valid_slot_value".startswith("slot"))}'

        semantic_expression = {'and': [{'operator': 'endswith', 'value': 'value'}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert is_slot_data_valid
        assert final_expr == '{("valid_slot_value".endswith("value"))}'

        semantic_expression = {'and': [{'operator': 'endswith', 'value': 'slot'}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert not is_slot_data_valid
        assert final_expr == '{("valid_slot_value".endswith("slot"))}'

        semantic_expression = {'and': [{'operator': 'has_length', 'value': 16}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert is_slot_data_valid
        assert final_expr == '{(len("valid_slot_value") == 16)}'

        semantic_expression = {'and': [{'operator': 'has_length', 'value': 15}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert not is_slot_data_valid
        assert final_expr == '{(len("valid_slot_value") == 15)}'

        semantic_expression = {'and': [{'operator': 'has_length_greater_than', 'value': 15}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert is_slot_data_valid
        assert final_expr == '{(len("valid_slot_value") > 15)}'

        semantic_expression = {'and': [{'operator': 'has_length_greater_than', 'value': 16}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert not is_slot_data_valid
        assert final_expr == '{(len("valid_slot_value") > 16)}'

        semantic_expression = {'and': [{'operator': 'has_length_less_than', 'value': 17}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert is_slot_data_valid
        assert final_expr == '{(len("valid_slot_value") < 17)}'

        semantic_expression = {'and': [{'operator': 'has_length_less_than', 'value': 16}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert not is_slot_data_valid
        assert final_expr == '{(len("valid_slot_value") < 16)}'

        semantic_expression = {'and': [{'operator': 'has_no_whitespace'}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert is_slot_data_valid
        assert final_expr == '{(" " not in "valid_slot_value")}'

        semantic_expression = {'and': [{'operator': 'has_no_whitespace'}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, 'valid slot value',
                                                                                 semantic_expression)
        assert not is_slot_data_valid
        assert final_expr == '{(" " not in "valid slot value")}'

        with pytest.raises(ActionFailure, match='Cannot evaluate invalid operator ">" for current slot type'):
            semantic_expression = {'and': [{'operator': '>'}]}
            ExpressionEvaluator.is_valid_slot_value(slot_type, 'valid slot value', semantic_expression)

    def test_is_valid_slot_value_float_type(self):
        slot_type = 'float'
        slot_value = 5

        semantic_expression = {'and': [{'operator': '==', 'value': 5}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert is_slot_data_valid
        assert final_expr == '{(5.0 == 5)}'

        semantic_expression = {'and': [{'operator': '==', 'value': 6}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert not is_slot_data_valid
        assert final_expr == '{(5.0 == 6)}'

        semantic_expression = {'and': [{'operator': '>', 'value': 5}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert not is_slot_data_valid
        assert final_expr == '{(5.0 > 5)}'
        semantic_expression = {'and': [{'operator': '>', 'value': 4}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert is_slot_data_valid
        assert final_expr == '{(5.0 > 4)}'

        semantic_expression = {'and': [{'operator': '<', 'value': 5}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert not is_slot_data_valid
        assert final_expr == '{(5.0 < 5)}'
        semantic_expression = {'and': [{'operator': '<', 'value': 6}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert is_slot_data_valid
        assert final_expr == '{(5.0 < 6)}'

        semantic_expression = {'and': [{'operator': 'in', 'value': [1, 2, 5, 6]}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert is_slot_data_valid
        assert final_expr == '{(5.0 in [1, 2, 5, 6])}'
        semantic_expression = {'and': [{'operator': 'in', 'value': [1, 2, 3, 4]}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert not is_slot_data_valid
        assert final_expr == '{(5.0 in [1, 2, 3, 4])}'

        semantic_expression = {'and': [{'operator': '==', 'value': 5.0}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert is_slot_data_valid
        assert final_expr == '{(5.0 == 5.0)}'
        semantic_expression = {'and': [{'operator': '<', 'value': 6.12}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, 6.10, semantic_expression)
        assert is_slot_data_valid
        assert final_expr == '{(6.1 < 6.12)}'

        semantic_expression = {'and': [{'operator': 'not in', 'value': [1, 2, 5, 6]}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, 7, semantic_expression)
        assert is_slot_data_valid
        assert final_expr == '{(7.0 not in [1, 2, 5, 6])}'
        semantic_expression = {'and': [{'operator': 'not in', 'value': [1, 2, 5, 6]}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, 6, semantic_expression)
        assert not is_slot_data_valid
        assert final_expr == '{(6.0 not in [1, 2, 5, 6])}'

        with pytest.raises(ActionFailure, match='Cannot evaluate invalid operator "has_length" for slot type "float"'):
            semantic_expression = {'and': [{'operator': 'has_length', 'value': 6}]}
            ExpressionEvaluator.is_valid_slot_value(slot_type, 6, semantic_expression)

    def test_is_valid_slot_value_boolean_type(self):
        slot_type = 'bool'
        slot_value = 'true'

        semantic_expression = {'and': [{'operator': 'is_true'}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert is_slot_data_valid
        assert final_expr == '{(true is true)}'
        semantic_expression = {'and': [{'operator': 'is_true'}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, 'false',
                                                                                 semantic_expression)
        assert not is_slot_data_valid
        assert final_expr == '{(false is true)}'

        semantic_expression = {'and': [{'operator': 'is_false'}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, 'false',
                                                                                 semantic_expression)
        assert is_slot_data_valid
        assert final_expr == '{(false is False)}'
        semantic_expression = {'and': [{'operator': 'is_false'}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert not is_slot_data_valid
        assert final_expr == '{(true is False)}'

        semantic_expression = {'and': [{'operator': 'is_null_or_empty'}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, '', semantic_expression)
        assert is_slot_data_valid
        assert final_expr == '{(is_empty())}'
        semantic_expression = {'and': [{'operator': 'is_null_or_empty'}]}
        # assert ExpressionEvaluator.is_valid_slot_value(slot_type, '    ', semantic_expression)
        semantic_expression = {'and': [{'operator': 'is_null_or_empty'}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, None, semantic_expression)
        assert is_slot_data_valid
        assert final_expr == '{(is_empty(None))}'
        semantic_expression = {'and': [{'operator': 'is_null_or_empty'}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, True, semantic_expression)
        assert not is_slot_data_valid
        assert final_expr == '{(is_empty(True))}'
        semantic_expression = {'and': [{'operator': 'is_null_or_empty'}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, 'False',
                                                                                 semantic_expression)
        assert not is_slot_data_valid
        assert final_expr == '{(is_empty(False))}'

        semantic_expression = {'and': [{'operator': 'is_not_null_or_empty'}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, '', semantic_expression)
        assert not is_slot_data_valid
        assert final_expr == '{(is_not_empty())}'
        semantic_expression = {'and': [{'operator': 'is_not_null_or_empty'}]}
        # assert not ExpressionEvaluator.is_valid_slot_value(slot_type, '    ', semantic_expression)
        semantic_expression = {'and': [{'operator': 'is_not_null_or_empty'}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, None, semantic_expression)
        assert not is_slot_data_valid
        assert final_expr == '{(is_not_empty(None))}'
        semantic_expression = {'and': [{'operator': 'is_not_null_or_empty'}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, str(slot_value),
                                                                                 semantic_expression)
        assert is_slot_data_valid
        assert final_expr == '{(is_not_empty(true))}'
        semantic_expression = {'and': [{'operator': 'is_not_null_or_empty'}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, 'False',
                                                                                 semantic_expression)
        assert is_slot_data_valid
        assert final_expr == '{(is_not_empty(False))}'

    def test_is_valid_slot_value_list_type(self):
        slot_type = 'list'
        slot_value = [1, 2, 3, 4]

        semantic_expression = {'and': [{'operator': '==', 'value': [1, 2, 3, 4]}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert is_slot_data_valid
        assert final_expr == '{([1, 2, 3, 4] == [1, 2, 3, 4])}'
        semantic_expression = {'and': [{'operator': '==', 'value': [1, 2, 3, 5]}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert not is_slot_data_valid
        assert final_expr == '{([1, 2, 3, 4] == [1, 2, 3, 5])}'

        semantic_expression = {'and': [{'operator': 'contains', 'value': 1}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert is_slot_data_valid
        assert final_expr == '{(1 in [1, 2, 3, 4])}'
        semantic_expression = {'and': [{'operator': 'contains', 'value': 10}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert not is_slot_data_valid
        assert final_expr == '{(10 in [1, 2, 3, 4])}'

        semantic_expression = {'and': [{'operator': 'in', 'value': [1, 2, 3, 4, 5, 6, 7, 8, 9]}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert is_slot_data_valid
        assert final_expr == '{([1, 2, 3, 4] in [1, 2, 3, 4, 5, 6, 7, 8, 9])}'
        semantic_expression = {'and': [{'operator': 'in', 'value': [4, 5, 6, 7, 8, 9]}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert not is_slot_data_valid
        assert final_expr == '{([1, 2, 3, 4] in [4, 5, 6, 7, 8, 9])}'

        semantic_expression = {'and': [{'operator': 'not in', 'value': [6, 7, 8, 9]}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert is_slot_data_valid
        assert final_expr == '{([1, 2, 3, 4] not in [6, 7, 8, 9])}'
        semantic_expression = {'and': [{'operator': 'not in', 'value': [4, 5, 6, 7, 8, 9]}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert is_slot_data_valid
        assert final_expr == '{([1, 2, 3, 4] not in [4, 5, 6, 7, 8, 9])}'
        semantic_expression = {'and': [{'operator': 'not in', 'value': [1, 2, 3, 4]}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert not is_slot_data_valid
        assert final_expr == '{([1, 2, 3, 4] not in [1, 2, 3, 4])}'

        semantic_expression = {'and': [{'operator': 'has_length', 'value': 4}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert is_slot_data_valid
        assert final_expr == '{(len([1, 2, 3, 4]) == 4)}'
        semantic_expression = {'and': [{'operator': 'has_length', 'value': 5}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert not is_slot_data_valid
        assert final_expr == '{(len([1, 2, 3, 4]) == 5)}'

        semantic_expression = {'and': [{'operator': 'has_length_greater_than', 'value': 2}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert is_slot_data_valid
        assert final_expr == '{(len([1, 2, 3, 4]) > 2)}'
        semantic_expression = {'and': [{'operator': 'has_length_greater_than', 'value': 4}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert not is_slot_data_valid
        assert final_expr == '{(len([1, 2, 3, 4]) > 4)}'

        semantic_expression = {'and': [{'operator': 'has_length_less_than', 'value': 5}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert is_slot_data_valid
        assert final_expr == '{(len([1, 2, 3, 4]) < 5)}'
        semantic_expression = {'and': [{'operator': 'has_length_less_than', 'value': 4}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert not is_slot_data_valid
        assert final_expr == '{(len([1, 2, 3, 4]) < 4)}'

        semantic_expression = {'and': [{'operator': 'is_null_or_empty'}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, [], semantic_expression)
        assert is_slot_data_valid
        assert final_expr == '{(is_null_or_empty(None))}'
        semantic_expression = {'and': [{'operator': 'is_null_or_empty'}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, None, semantic_expression)
        assert is_slot_data_valid
        assert final_expr == '{(is_null_or_empty(None))}'
        semantic_expression = {'and': [{'operator': 'is_null_or_empty'}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert not is_slot_data_valid
        assert final_expr == '{(is_null_or_empty(None))}'

        semantic_expression = {'and': [{'operator': 'is_not_null_or_empty'}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, [], semantic_expression)
        assert not is_slot_data_valid
        assert final_expr == '{(is_not_null_or_empty(None))}'
        semantic_expression = {'and': [{'operator': 'is_not_null_or_empty'}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, None, semantic_expression)
        assert not is_slot_data_valid
        assert final_expr == '{(is_not_null_or_empty(None))}'
        semantic_expression = {'and': [{'operator': 'is_not_null_or_empty'}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert is_slot_data_valid
        assert final_expr == '{(is_not_null_or_empty(None))}'

    def test_get_email_action_config(self):
        with patch('kairon.shared.utils.SMTP', autospec=True) as mock:
            expected = EmailActionConfig(
                action_name="email_action",
                smtp_url="test.localhost",
                smtp_port=293,
                smtp_password="test",
                from_email="test@demo.com",
                subject="test",
                to_email=["test@test.com","test1@test.com"],
                response="Validated",
                bot="bot",
                user="user"
            ).save().to_mongo().to_dict()

            actual = ActionUtility.get_email_action_config("bot", "email_action")
            assert actual is not None
            assert expected['action_name'] == actual['action_name']
            assert expected['response'] == actual['response']
            assert 'test.localhost' == actual['smtp_url']
            assert expected['smtp_port'] == actual['smtp_port']
            assert "test" == actual['smtp_password']
            assert 'test@demo.com' == actual['from_email']
            assert expected['to_email'] == actual['to_email']
            assert expected.get("smtp_userid") == actual.get("smtp_userid")

            expected = EmailActionConfig(
                action_name="email_action1",
                smtp_url="test.localhost",
                smtp_port=293,
                smtp_userid='test.user_id',
                smtp_password="test",
                from_email="test@demo.com",
                subject="test",
                to_email=["test@test.com", "test1@test.com"],
                response="Validated",
                bot="bot",
                user="user"
            ).save().to_mongo().to_dict()

            actual = ActionUtility.get_email_action_config("bot", "email_action1")
            assert actual is not None
            assert expected['action_name'] == actual['action_name']
            assert expected['response'] == actual['response']
            assert 'test.localhost' == actual['smtp_url']
            assert expected['smtp_port'] == actual['smtp_port']
            assert "test" == actual['smtp_password']
            assert 'test@demo.com' == actual['from_email']
            assert expected['to_email'] == actual['to_email']
            assert 'test.user_id' == actual.get("smtp_userid")

    def test_prepare_email_body(self):
        Utility.email_conf['email']['templates']['conversation'] = open('template/emails/conversation.html', 'rb').read().decode()
        Utility.email_conf['email']['templates']['bot_msg_conversation'] = open('template/emails/bot_msg_conversation.html', 'rb').read().decode()
        Utility.email_conf['email']['templates']['user_msg_conversation'] = open('template/emails/user_msg_conversation.html', 'rb').read().decode()
        events = [{"event":"action","timestamp":1594907100.12764,"name":"action_session_start","policy":None,"confidence":None},{"event":"session_started","timestamp":1594907100.12765},{"event":"action","timestamp":1594907100.12767,"name":"action_listen","policy":None,"confidence":None},{"event":"user","timestamp":1594907100.42744,"text":"can't","parse_data":{"intent":{"name":"test intent","confidence":0.253578245639801},"entities":[],"intent_ranking":[{"name":"test intent","confidence":0.253578245639801},{"name":"goodbye","confidence":0.1504897326231},{"name":"greet","confidence":0.138640150427818},{"name":"affirm","confidence":0.0857767835259438},{"name":"smalltalk_human","confidence":0.0721133947372437},{"name":"deny","confidence":0.069614589214325},{"name":"bot_challenge","confidence":0.0664894133806229},{"name":"faq_vaccine","confidence":0.062177762389183},{"name":"faq_testing","confidence":0.0530692934989929},{"name":"out_of_scope","confidence":0.0480506233870983}],"response_selector":{"default":{"response":{"name":None,"confidence":0},"ranking":[],"full_retrieval_intent":None}},"text":"can't"},"input_channel":None,"message_id":"bbd413bf5c834bf3b98e0da2373553b2","metadata":{}},{"event":"action","timestamp":1594907100.4308,"name":"utter_test intent","policy":"policy_0_MemoizationPolicy","confidence":1},{"event":"bot","timestamp":1594907100.4308,"text":"will not = won\"t","data":{"elements":None,"quick_replies":None,"buttons":None,"attachment":None,"image":None,"custom":None},"metadata":{}},{"event":"action","timestamp":1594907100.43384,"name":"action_listen","policy":"policy_0_MemoizationPolicy","confidence":1},{"event":"user","timestamp":1594907117.04194,"text":"can\"t","parse_data":{"intent":{"name":"test intent","confidence":0.253578245639801},"entities":[],"intent_ranking":[{"name":"test intent","confidence":0.253578245639801},{"name":"goodbye","confidence":0.1504897326231},{"name":"greet","confidence":0.138640150427818},{"name":"affirm","confidence":0.0857767835259438},{"name":"smalltalk_human","confidence":0.0721133947372437},{"name":"deny","confidence":0.069614589214325},{"name":"bot_challenge","confidence":0.0664894133806229},{"name":"faq_vaccine","confidence":0.062177762389183},{"name":"faq_testing","confidence":0.0530692934989929},{"name":"out_of_scope","confidence":0.0480506233870983}],"response_selector":{"default":{"response":{"name":None,"confidence":0},"ranking":[],"full_retrieval_intent":None}},"text":"can\"t"},"input_channel":None,"message_id":"e96e2a85de0748798748385503c65fb3","metadata":{}},{"event":"action","timestamp":1594907117.04547,"name":"utter_test intent","policy":"policy_1_TEDPolicy","confidence":0.978452920913696},{"event":"bot","timestamp":1594907117.04548,"text":"can not = can't","data":{"elements":None,"quick_replies":None,"buttons":None,"attachment":None,"image":None,"custom":None},"metadata":{}}]
        actual = ActionUtility.prepare_email_body(events, "conversation history", "test@kairon.com")
        assert str(actual).__contains__("</table>")

    def test_get_google_search_action_config(self):
        bot = 'test_action_server'
        user = 'test_user'
        Actions(name='google_search_action', type=ActionType.google_search_action.value, bot=bot, user=user).save()
        GoogleSearchAction(name='google_search_action', api_key='1234567890',
                           search_engine_id='asdfg::123456', bot=bot, user=user).save()
        actual, a_type = ActionUtility.get_action_config(bot, 'google_search_action')
        assert actual['api_key'] == '1234567890'
        assert actual['search_engine_id'] == 'asdfg::123456'
        assert a_type == ActionType.google_search_action.value

    def test_get_google_search_action_config_not_exists(self):
        bot = 'test_action_server'
        with pytest.raises(ActionFailure, match='No action found for bot'):
            ActionUtility.get_action_config(bot, 'custom_search_action')

    def test_get_google_search_action_not_found(self):
        bot = 'test_action_server'
        user = 'test_user'
        Actions(name='custom_search_action', type=ActionType.google_search_action.value, bot=bot, user=user).save()
        with pytest.raises(ActionFailure, match='Google search action not found'):
            ActionUtility.get_action_config(bot, 'custom_search_action')

    def test_get_jira_action_not_exists(self):
        bot = 'test_action_server'
        with pytest.raises(ActionFailure, match='No action found for bot'):
            ActionUtility.get_action_config(bot, 'jira_action')

    def test_get_jira_action_not_found(self):
        bot = 'test_action_server'
        user = 'test_user'
        Actions(name='jira_action', type=ActionType.jira_action.value, bot=bot, user=user).save()
        with pytest.raises(ActionFailure, match='Jira action not found'):
            ActionUtility.get_action_config(bot, 'jira_action')

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
                api_token='ASDFGHJKL', project_key='HEL', issue_type='Bug', summary='fallback',
                response='Successfully created').save()
        action, a_type = ActionUtility.get_action_config(bot, 'jira_action')
        assert a_type == 'jira_action'
        action.pop('_id')
        action.pop('timestamp')
        assert action == {
            'name': 'jira_action', 'url': 'https://test-digite.atlassian.net', 'user_name': 'test@digite.com',
            'api_token': 'ASDFGHJKL', 'project_key': 'HEL', 'issue_type': 'Bug', 'summary': 'fallback',
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
        with pytest.raises(ActionFailure, match='No action found for bot'):
            ActionUtility.get_action_config(bot, 'zendesk_action')

    def test_get_zendesk_action_config_not_found(self):
        bot = 'test_action_server'
        user = 'test_user'
        Actions(name='zendesk_action', type=ActionType.zendesk_action.value, bot=bot, user=user).save()
        with pytest.raises(ActionFailure, match='Zendesk action not found'):
            ActionUtility.get_action_config(bot, 'zendesk_action')

    def test_get_zendesk_action_config(self):
        bot = 'test_action_server'
        user = 'test_user'

        with patch('zenpy.Zenpy'):
            ZendeskAction(
                name='zendesk_action', bot=bot, user=user, subdomain='digite751', user_name='test@digite.com',
                api_token='ASDFGHJKL', subject='new user detected', response='Successfully created').save()
        action, a_type = ActionUtility.get_action_config(bot, 'zendesk_action')
        assert a_type == 'zendesk_action'
        action.pop('_id')
        action.pop('timestamp')
        assert action == {
            'name': 'zendesk_action', 'subdomain': 'digite751', 'user_name': 'test@digite.com',
            'api_token': 'ASDFGHJKL', 'subject': 'new user detected',
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
            match=[responses.json_params_matcher({'ticket': {'id': None, 'subject': 'new ticket', 'comment': {'id': None}}})]
        )
        ActionUtility.create_zendesk_ticket('digite751', 'test@digite.com', 'ASDFGHJKL', 'new ticket')

        responses.add(
            'POST',
            'https://digite751.zendesk.com/api/v2/tickets.json',
            json={'count': 1},
            match=[responses.json_params_matcher(
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
            api_key='sd234567',
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
        with pytest.raises(ActionFailure, match='Pipedrive leads action not found'):
            ActionUtility.get_action_config(bot, 'pipedrive_leads_action')

    def test_get_pipedrive_leads_action_config(self):
        bot = 'test_action_server'
        user = 'test_user'

        with patch('pipedrive.client.Client'):
            PipedriveLeadsAction(
                name='pipedrive_leads_action', bot=bot, user=user, domain='digite751', api_token='ASDFGHJKL',
                title='new user detected', response='Lead successfully added',
                metadata={'name': 'name', 'org_name': 'organization', 'email': 'email', 'phone': 'phone'}).save()
        action, a_type = ActionUtility.get_action_config(bot, 'pipedrive_leads_action')
        assert a_type == 'pipedrive_leads_action'
        action.pop('_id')
        action.pop('timestamp')
        assert action == {
            'name': 'pipedrive_leads_action', 'domain': 'digite751', 'api_token': 'ASDFGHJKL',
            'title': 'new user detected', 'response': 'Lead successfully added', 'bot': 'test_action_server',
            'user': 'test_user', 'status': True, 'metadata': {'name': 'name', 'org_name': 'organization', 'email': 'email', 'phone': 'phone'}
        }

    def test_prepare_pipedrive_metadata(self):
        bot = 'test_action_server'
        slots = {"name": "udit pandey", "organization": "digite", "email": "pandey.udit867@gmail.com", 'phone': '9876543210'}
        events = [{"event1": "hello"}, {"event2": "how are you"}]
        tracker = Tracker(sender_id="sender1", slots=slots, events=events, paused=False, latest_message=None,
                          followup_action=None, active_loop=None, latest_action_name=None)
        action, a_type = ActionUtility.get_action_config(bot, 'pipedrive_leads_action')
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
