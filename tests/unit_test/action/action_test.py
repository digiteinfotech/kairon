import json
import os
import urllib.parse

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
    Actions, FormValidationAction
from kairon.actions.handlers.processor import ActionProcessor
from kairon.shared.actions.utils import ActionUtility, ExpressionEvaluator
from kairon.shared.actions.exception import ActionFailure
from kairon.shared.utils import Utility
import requests


class TestActions:

    @pytest.fixture(autouse=True)
    def setup(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        db_url = Utility.environment['database']["url"]
        pytest.db_url = db_url

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
        assert str(actual[0]['name']) == 'KAIRON_ACTION_RESPONSE'
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
        assert str(actual[0]['name']) == 'KAIRON_ACTION_RESPONSE'
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
        assert actual[0]['name'] == 'KAIRON_ACTION_RESPONSE'
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
        assert str(actual[0]['name']) == 'KAIRON_ACTION_RESPONSE'
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
        assert str(actual[0]['name']) == 'KAIRON_ACTION_RESPONSE'
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
        assert str(actual[0]['name']) == 'KAIRON_ACTION_RESPONSE'
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
        assert str(actual[0]['name']) == 'KAIRON_ACTION_RESPONSE'
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
        output = ActionUtility.prepare_response("I want rupee${price.1.rupee}. Also, want $${price.0.dollars}", {"price": [{"dollars": "51"}, {"rupee": "151"}]})
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
        assert str(actual[0]['name']) == 'KAIRON_ACTION_RESPONSE'
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
        assert str(actual[0]['name']) == 'KAIRON_ACTION_RESPONSE'
        assert str(actual[0]['value']) == 'The value of 2 in red is [\'red\', \'buggy\', \'bumpers\']'

    @pytest.mark.asyncio
    async def test_slot_set_action_from_value(self, monkeypatch):
        action_name = "test_slot_set_action_from_value"
        action = SlotSetAction(
            name=action_name,
            slot="location",
            type="from_value",
            value="Bengaluru",
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
            slot="location",
            type="reset_slot",
            value="Bengaluru",
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
        SlotSetAction(name='action_get_user', slot='user', type='from_value', value='name', bot=bot, user=user).save()
        config, action_type = ActionUtility.get_action_config(bot, 'action_get_user')
        assert config['name'] == 'action_get_user'
        assert config['slot'] == 'user'
        assert config['type'] == 'from_value'
        assert config['value'] == 'name'
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
        with pytest.raises(ActionFailure, match='Only http & slot set actions are compatible with action server'):
            ActionUtility.get_action_config(bot, 'test_get_action_config_custom_user_action')

    def test_get_form_validation_config_single_validation(self):
        bot = 'test_actions'
        user = 'test'
        validation_semantic = {'or': [{'less_than': '5'}, {'==': 6}]}
        expected_output = FormValidationAction(name='validate_form', slot='name', validation_semantic=validation_semantic,
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
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value, semantic_expression)
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
        assert final_expr == '{(5 == 5)}'

        semantic_expression = {'and': [{'operator': '==', 'value': 6}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert not is_slot_data_valid
        assert final_expr == '{(5 == 6)}'

        semantic_expression = {'and': [{'operator': '>', 'value': 5}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert not is_slot_data_valid
        assert final_expr == '{(5 > 5)}'
        semantic_expression = {'and': [{'operator': '>', 'value': 4}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert is_slot_data_valid
        assert final_expr == '{(5 > 4)}'

        semantic_expression = {'and': [{'operator': '<', 'value': 5}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert not is_slot_data_valid
        assert final_expr == '{(5 < 5)}'
        semantic_expression = {'and': [{'operator': '<', 'value': 6}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert is_slot_data_valid
        assert final_expr == '{(5 < 6)}'

        semantic_expression = {'and': [{'operator': 'in', 'value': [1, 2, 5, 6]}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert is_slot_data_valid
        assert final_expr == '{(5 in [1, 2, 5, 6])}'
        semantic_expression = {'and': [{'operator': 'in', 'value': [1, 2, 3, 4]}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert not is_slot_data_valid
        assert final_expr == '{(5 in [1, 2, 3, 4])}'

        semantic_expression = {'and': [{'operator': '==', 'value': 5.0}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, slot_value,
                                                                                 semantic_expression)
        assert is_slot_data_valid
        assert final_expr == '{(5 == 5.0)}'
        semantic_expression = {'and': [{'operator': '<', 'value': 6.12}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, 6.10, semantic_expression)
        assert is_slot_data_valid
        assert final_expr == '{(6 < 6.12)}'

        semantic_expression = {'and': [{'operator': 'not in', 'value': [1, 2, 5, 6]}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, 7, semantic_expression)
        assert is_slot_data_valid
        assert final_expr == '{(7 not in [1, 2, 5, 6])}'
        semantic_expression = {'and': [{'operator': 'not in', 'value': [1, 2, 5, 6]}]}
        final_expr, is_slot_data_valid = ExpressionEvaluator.is_valid_slot_value(slot_type, 6, semantic_expression)
        assert not is_slot_data_valid
        assert final_expr == '{(6 not in [1, 2, 5, 6])}'

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
