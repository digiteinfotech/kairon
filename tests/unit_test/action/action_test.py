import json
import os
import urllib.parse

os.environ["system_file"] = "./tests/testing_data/system.yaml"
from typing import Dict, Text, Any, List

import pytest
import responses
from mongoengine import connect
from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher

from kairon.shared.actions.data_objects import HttpActionRequestBody, HttpActionConfig, HttpActionLog
from kairon.actions.handlers.processor import ActionProcessor
from kairon.shared.actions.utils import ActionUtility
from kairon.shared.actions.exception import HttpActionFailure
from kairon.utils import Utility
import requests


class TestActions:

    @pytest.fixture(autouse=True)
    def setup(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_evironment()
        db_url = Utility.environment['database']["url"]
        pytest.db_url = db_url

        connect(host=db_url)

    @pytest.fixture
    def mock_get_http_action_exception(self, monkeypatch):
        def _raise_excep(*arge, **kwargs):
            raise HttpActionFailure("No HTTP action found for bot and action")

        monkeypatch.setattr(ActionUtility, "get_http_action_config", _raise_excep)

    @responses.activate
    def test_execute_http_request_getWith_auth_token(self):
        http_url = 'http://localhost:8080/mock'
        # file deepcode ignore HardcodedNonCryptoSecret: Random string for testing
        auth_token = "bearer jkhfhkujsfsfslfhjsfhkjsfhskhfksj"

        responses.add(
            method=responses.GET,
            url=http_url,
            json={'data': 'test_data', 'test_class': [{'key': 'value'}, {'key2': 'value2'}]},
            status=200
        )

        response = ActionUtility.execute_http_request(auth_token=auth_token, http_url=http_url,
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

        response = ActionUtility.execute_http_request(auth_token=None, http_url=http_url,
                                                      request_method=responses.GET)
        assert response
        assert response['data'] == 'test_data'
        assert len(response['test_class']) == 2
        assert response['test_class'][1]['key2'] == 'value2'
        assert 'Authorization' not in responses.calls[0].request.headers

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
            match=[responses.json_params_matcher(request_params)]
        )

        response = ActionUtility.execute_http_request(auth_token=auth_token, http_url=http_url,
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

        response = ActionUtility.execute_http_request(auth_token=None, http_url=http_url,
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
            match=[responses.json_params_matcher(request_params)]
        )

        response = ActionUtility.execute_http_request(auth_token=auth_token, http_url=http_url,
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

        response = ActionUtility.execute_http_request(auth_token=None, http_url=http_url,
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
            match=[responses.json_params_matcher(request_params)]
        )

        response = ActionUtility.execute_http_request(auth_token=auth_token, http_url=http_url,
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
        )

        response = ActionUtility.execute_http_request(auth_token=auth_token, http_url=http_url,
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

        with pytest.raises(HttpActionFailure, match="Got non-200 status code"):
            ActionUtility.execute_http_request(auth_token=None, http_url=http_url,
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

        response = ActionUtility.execute_http_request(auth_token=None, http_url=http_url,
                                                      request_method=responses.DELETE, request_body=request_params)
        assert response
        assert response == resp_msg
        assert 'Authorization' not in responses.calls[0].request.headers

    def test_get_http_action_config(self):
        http_params = [HttpActionRequestBody(key="key1", value="value1", parameter_type="slot"),
                       HttpActionRequestBody(key="key2", value="value2")]
        expected = HttpActionConfig(
            auth_token="bearer kjflksjflksajfljsdflinlsufisnflisjbjsdalibvs",
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
        assert expected['auth_token'] == actual['auth_token']
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
            auth_token="",
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
            auth_token="bearer kjflksjflksajfljsdflinlsufisnflisjbjsdalibvs",
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
        assert expected['auth_token'] == actual['auth_token']
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
            ActionUtility.get_http_action_config(bot=None, action_name="http_action")
            assert False
        except HttpActionFailure as ex:
            assert str(ex) == "Bot name and action name are required"

    def test_get_http_action_no_http_action(self):
        try:
            ActionUtility.get_http_action_config(bot="bot", action_name=None)
            assert False
        except HttpActionFailure as ex:
            assert str(ex) == "Bot name and action name are required"

    def test_get_http_action_invalid_bot(self):
        http_params = [HttpActionRequestBody(key="key1", value="value1", parameter_type="slot"),
                       HttpActionRequestBody(key="key2", value="value2")]
        HttpActionConfig(
            auth_token="bearer kjflksjflksajfljsdflinlsufisnflisjbjsdalibvs",
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
        except HttpActionFailure as ex:
            assert str(ex).__contains__("No HTTP action found for bot")

    def test_get_http_action_invalid_http_action(self):
        http_params = [HttpActionRequestBody(key="key1", value="value1", parameter_type="slot"),
                       HttpActionRequestBody(key="key2", value="value2")]
        HttpActionConfig(
            auth_token="bearer kjflksjflksajfljsdflinlsufisnflisjbjsdalibvs",
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
        except HttpActionFailure as ex:
            assert str(ex).__contains__("No HTTP action found for bot")

    def test_get_http_action_no_request_body(self):
        http_params = []
        HttpActionConfig(
            auth_token="bearer kjflksjflksajfljsdflinlsufisnflisjbjsdalibvs",
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
        except HttpActionFailure as ex:
            assert str(ex).__contains__("No HTTP action found for bot")

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
        request_params = ActionUtility.prepare_request(tracker=tracker, http_action_config_params=http_action_config_params)
        assert request_params['param1'] == "value1"
        assert not request_params['param3']

    def test_prepare_request_sender_id(self):
        slots = {"bot": "demo_bot", "http_action_config": "http_action_name", "param2": "param2value"}
        events = [{"event1": "hello"}, {"event2": "how are you"}]
        http_action_config_params = [HttpActionRequestBody(key="param1", value="value1"),
                                     HttpActionRequestBody(key="user_id", value="", parameter_type="sender_id")]
        tracker = Tracker(sender_id="kairon_user@digite.com", slots=slots, events=events, paused=False, latest_message=None,
                          followup_action=None, active_loop=None, latest_action_name=None)
        request_params = ActionUtility.prepare_request(tracker=tracker, http_action_config_params=http_action_config_params)
        assert request_params['param1'] == "value1"
        assert request_params['user_id'] == "kairon_user@digite.com"

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
        except HttpActionFailure:
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
        except HttpActionFailure:
            assert True

    def test_prepare_response_invalid_response_json(self):
        json_as_string = "Not a json string"
        try:
            ActionUtility.prepare_response("The value of ${a.b.3} in ${a.b.d.0} is ${a.b.c}", json_as_string)
            assert False
        except HttpActionFailure as e:
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
        actions_name="test_run_invalid_http_action1"
        HttpActionConfig(
            auth_token="bearer kjflksjflksajfljsdflinlsufisnflisjbjsdalibvs",
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
        str(dispatcher.messages[0]['text']).__contains__(
            "I have failed to process your request: No HTTP action found for bot")
        log = HttpActionLog.objects(sender="sender1",
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
        assert actual is not None
        assert str(actual[0]['name']) == 'KAIRON_ACTION_RESPONSE'
        assert str(actual[0]['value']) == 'I have failed to process your request'
        log = HttpActionLog.objects(sender="sender2",
                                    status="FAILURE").get()
        assert log['exception'] == 'Bot id and HTTP action configuration name not found in slot'

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
        assert actual is not None
        assert str(actual[0]['name']) == 'KAIRON_ACTION_RESPONSE'
        assert str(actual[0]['value']) == 'I have failed to process your request'

    @pytest.mark.asyncio
    async def test_run(self, monkeypatch):
        http_url = "http://www.google.com"
        http_response = "This should be response"
        action = HttpActionConfig(
            auth_token="bearer kjflksjflksajfljsdflinlsufisnflisjbjsdalibvs",
            action_name="http_action",
            response=http_response,
            http_url=http_url,
            request_method="GET",
            params_list=None,
            bot="5f50fd0a56b698ca10d35d2e",
            user="user"
        )

        def _get_action(*arge, **kwargs):
            return action.to_mongo().to_dict()

        monkeypatch.setattr(ActionUtility, "get_http_action_config", _get_action)
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
        log = HttpActionLog.objects(sender="sender_test_run",
                                    status="SUCCESS").get()
        assert not log['exception']
        assert log['timestamp']
        assert log['intent']
        assert log['action']
        assert log['bot_response']
        assert log['api_response']

    @pytest.mark.asyncio
    async def test_run_with_post(self, monkeypatch):
        action = HttpActionConfig(
            auth_token="",
            action_name="test_run_with_post",
            response="Data added successfully, id:${RESPONSE}",
            http_url="http://localhost:8080/mock",
            request_method="POST",
            params_list=None,
            bot="5f50fd0a56b698ca10d35d2e",
            user="user"
        )

        def _get_action(*arge, **kwargs):
            return action.to_mongo().to_dict()

        monkeypatch.setattr(ActionUtility, "get_http_action_config", _get_action)
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
        actual: List[Dict[Text, Any]] = await ActionProcessor.process_action(dispatcher, tracker, domain, "test_run_with_post")
        assert actual is not None
        assert actual[0]['name'] == 'KAIRON_ACTION_RESPONSE'
        assert actual[0]['value'] == 'Data added successfully, id:5000'

    @pytest.mark.asyncio
    async def test_run_with_post_and_parameters(self, monkeypatch):
        request_params = [HttpActionRequestBody(key='key1', value="value1"),
                          HttpActionRequestBody(key='key2', value="value2")]
        action = HttpActionConfig(
            auth_token="",
            action_name="test_run_with_post",
            response="Data added successfully, id:${RESPONSE}",
            http_url="http://localhost:8080/mock",
            request_method="POST",
            params_list=request_params,
            bot="5f50fd0a56b698ca10d35d2e",
            user="user"
        )

        def _get_action(*arge, **kwargs):
            return action.to_mongo().to_dict()

        monkeypatch.setattr(ActionUtility, "get_http_action_config", _get_action)
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
        actual: List[Dict[Text, Any]] = await ActionProcessor.process_action(dispatcher, tracker, domain, "test_run_with_post")
        responses.stop()
        assert actual is not None
        assert str(actual[0]['name']) == 'KAIRON_ACTION_RESPONSE'
        assert str(actual[0]['value']) == 'Data added successfully, id:5000'
        log = HttpActionLog.objects(sender="sender_test_run_with_post",
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
            auth_token="",
            action_name="test_run_with_get",
            response="The value of ${a.b.3} in ${a.b.d.0} is ${a.b.d}",
            http_url="http://localhost:8081/mock",
            request_method="GET",
            params_list=None,
            bot="5f50fd0a56b698ca10d35d2e",
            user="user"
        )

        def _get_action(*arge, **kwargs):
            return action.to_mongo().to_dict()

        monkeypatch.setattr(ActionUtility, "get_http_action_config", _get_action)
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
        actual: List[Dict[Text, Any]] = await ActionProcessor.process_action(dispatcher, tracker, domain, "test_run_with_post")
        responses.stop()
        assert actual is not None
        assert str(actual[0]['name']) == 'KAIRON_ACTION_RESPONSE'
        assert str(actual[0]['value']) == 'The value of 2 in red is [\'red\', \'buggy\', \'bumpers\']'

    @pytest.mark.asyncio
    async def test_run_no_connection(self, monkeypatch):
        action_name = "test_run_with_post"
        action = HttpActionConfig(
            auth_token="",
            action_name=action_name,
            response="This should be response",
            http_url="http://localhost:8085/mock",
            request_method="GET",
            params_list=None,
            bot="5f50fd0a56b698ca10d35d2e",
            user="user"
        )

        def _get_action(*arge, **kwargs):
            return action.to_mongo().to_dict()

        monkeypatch.setattr(ActionUtility, "get_http_action_config", _get_action)
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
            auth_token="",
            action_name=action_name,
            response="The value of ${a.b.3} in ${a.b.d.0} is ${a.b.d}",
            http_url="http://localhost:8080/mock",
            request_method="GET",
            params_list=None,
            bot="5f50fd0a56b698ca10d35d2e",
            user="user"
        )

        def _get_action(*arge, **kwargs):
            return action.to_mongo().to_dict()

        monkeypatch.setattr(ActionUtility, "get_http_action_config", _get_action)
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
        except HttpActionFailure as e:
            assert str(e) == 'Unable to retrieve value for key from HTTP response: \'d\''

    @pytest.mark.asyncio
    async def test_run_get_with_parameters(self, monkeypatch):
        request_params = [HttpActionRequestBody(key='key1', value="value1"),
                          HttpActionRequestBody(key='key2', value="value2")]
        action = HttpActionConfig(
            auth_token="",
            action_name="test_run_get_with_parameters",
            response="The value of ${a.b.3} in ${a.b.d.0} is ${a.b.d}",
            http_url="http://localhost:8081/mock",
            request_method="GET",
            params_list=request_params,
            bot="5f50fd0a56b698ca10d35d2e",
            user="user"
        )

        def _get_action(*arge, **kwargs):
            return action.to_mongo().to_dict()

        monkeypatch.setattr(ActionUtility, "get_http_action_config", _get_action)
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
            if headers and url == http_url+'?'+urllib.parse.urlencode({'key1': 'value1', 'key2': 'value2'}):
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
