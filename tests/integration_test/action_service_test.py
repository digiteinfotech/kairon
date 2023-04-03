import html

import mock
from jira import JIRAError
from tornado.test.testing_test import AsyncHTTPTestCase

from kairon.actions.definitions.set_slot import ActionSetSlot
from kairon.actions.server import make_app
from kairon.shared.actions.data_objects import HttpActionConfig, SlotSetAction, Actions, FormValidationAction, \
    EmailActionConfig, ActionServerLogs, GoogleSearchAction, JiraAction, ZendeskAction, PipedriveLeadsAction, SetSlots, \
    HubspotFormsAction, HttpActionResponse, HttpActionRequestBody, SetSlotsFromResponse, CustomActionRequestParameters, \
    KaironTwoStageFallbackAction, TwoStageFallbackTextualRecommendations, RazorpayAction, KaironFaqAction
from kairon.shared.actions.models import ActionType, ActionParameterType
from kairon.shared.admin.constants import BotSecretType
from kairon.shared.admin.data_objects import BotSecrets
from kairon.shared.constants import KAIRON_USER_MSG_ENTITY
from kairon.shared.data.constant import KAIRON_TWO_STAGE_FALLBACK, FALLBACK_MESSAGE, GPT_LLM_FAQ, \
    DEFAULT_NLU_FALLBACK_RESPONSE, KAIRON_FAQ_ACTION, DEFAULT_SYSTEM_PROMPT, DEFAULT_CONTEXT_PROMPT
import numpy as np
from kairon.shared.data.data_objects import Slots, KeyVault, BotSettings
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.utils import Utility
from kairon.shared.actions.utils import ActionUtility
from mongoengine import connect
import json
import responses
from mock import patch
import os

os.environ["system_file"] = "./tests/testing_data/system.yaml"
os.environ['ASYNC_TEST_TIMEOUT'] = "360"
Utility.load_environment()
connect(**Utility.mongoengine_connection())


class TestActionServer(AsyncHTTPTestCase):

    def get_app(self):
        return make_app()

    def test_index(self):
        response = self.fetch("/")
        self.assertEqual(response.code, 200)
        self.assertEqual(response.body.decode("utf8"), 'Kairon Server Running')
    
    def test_http_action_execution(self):
        action_name = "test_http_action_execution"
        Actions(name=action_name, type=ActionType.http_action.value, bot="5f50fd0a56b698ca10d35d2e", user="user").save()
        KeyVault(key="EMAIL", value="uditpandey@digite.com", bot="5f50fd0a56b698ca10d35d2e", user="user").save()
        KeyVault(key="FIRSTNAME", value="udit", bot="5f50fd0a56b698ca10d35d2e", user="user").save()
        HttpActionConfig(
            action_name=action_name,
            response=HttpActionResponse(value="The value of ${a.b.3} in ${a.b.d.0} is ${a.b.d}"),
            http_url="http://localhost:8081/mock",
            request_method="GET",
            headers=[HttpActionRequestBody(key="botid", parameter_type="slot", value="bot", encrypt=True),
                     HttpActionRequestBody(key="userid", parameter_type="value", value="1011", encrypt=True),
                     HttpActionRequestBody(key="tag", parameter_type="value", value="from_bot", encrypt=True),
                     HttpActionRequestBody(key="email", parameter_type="key_vault", value="EMAIL", encrypt=False)],
            params_list=[HttpActionRequestBody(key="bot", parameter_type="slot", value="bot", encrypt=True),
                         HttpActionRequestBody(key="user", parameter_type="value", value="1011", encrypt=False),
                         HttpActionRequestBody(key="tag", parameter_type="value", value="from_bot", encrypt=True),
                         HttpActionRequestBody(key="name", parameter_type="key_vault", value="FIRSTNAME", encrypt=False),
                         HttpActionRequestBody(key="contact", parameter_type="key_vault", value="CONTACT", encrypt=False)],
            set_slots=[SetSlotsFromResponse(name="val_d", value="${a.b.d}"),
                       SetSlotsFromResponse(name="val_d_0", value="${a.b.d.0}")],
            bot="5f50fd0a56b698ca10d35d2e",
            user="user"
        ).save()

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
            match=[responses.matchers.json_params_matcher({"bot": "5f50fd0a56b698ca10d35d2e", "user": "1011", "tag": "from_bot",
                                                  "name": "udit", "contact": None})],
        )

        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e"},
                "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]},
                "latest_event_time": 1537645578.314389,
                "followup_action": "action_listen",
                "paused": False,
                "events": [{"event1": "hello"}, {"event2": "how are you"}],
                "latest_input_channel": "rest",
                "active_loop": {},
                "latest_action": {},
            },
            "domain": {
                "config": {},
                "session_config": {},
                "intents": [],
                "entities": [],
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e"},
                "responses": {},
                "actions": [],
                "forms": {},
                "e2e_actions": []
            },
            "version": "version"
        }
        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response.code, 200)
        self.assertEqual(len(response_json['events']), 3)
        self.assertEqual(len(response_json['responses']), 1)
        self.assertEqual(response_json['events'], [
            {"event": "slot", "timestamp": None, "name": "val_d", "value": "['red', 'buggy', 'bumpers']"},
            {"event": "slot", "timestamp": None, "name": "val_d_0", "value": "red"},
            {"event": "slot", "timestamp": None, "name": "kairon_action_response",
             "value": "The value of 2 in red is ['red', 'buggy', 'bumpers']"}])
        self.assertEqual(response_json['responses'][0]['text'], "The value of 2 in red is ['red', 'buggy', 'bumpers']")
        log = ActionServerLogs.objects(action=action_name).get().to_mongo().to_dict()
        log.pop('_id')
        log.pop('timestamp')
        assert log == {'type': 'http_action', 'intent': 'test_run', 'action': 'test_http_action_execution',
                       'sender': 'default', 'user_msg': 'get intents',
                       'headers': {'botid': '**********************2e', 'userid': '****', 'tag': '******ot', 'email': '*******************om'},
                       'url': 'http://localhost:8081/mock', 'request_method': 'GET',
                       'request_params': {'bot': '**********************2e', 'user': '1011', 'tag': '******ot', 'contact': None, 'name': '****'},
                       'api_response': "{'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}",
                       'bot_response': "The value of 2 in red is ['red', 'buggy', 'bumpers']", 'messages': [
                "expression: The value of ${a.b.3} in ${a.b.d.0} is ${a.b.d} || data: {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}} || response: The value of 2 in red is ['red', 'buggy', 'bumpers']",
                'initiating slot evaluation',
                "slot: val_d || expression: ${a.b.d} || data: {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}} || response: ['red', 'buggy', 'bumpers']",
                "slot: val_d_0 || expression: ${a.b.d.0} || data: {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}} || response: red"],
                       'bot': '5f50fd0a56b698ca10d35d2e', 'status': 'SUCCESS'}

    def test_http_action_execution_no_response_dispatch(self):
        action_name = "test_http_action_execution_no_response_dispatch"
        Actions(name=action_name, type=ActionType.http_action.value, bot="5f50fd0a56b698ca10d35d2e", user="user").save()
        HttpActionConfig(
            action_name=action_name,
            content_type="data",
            response=HttpActionResponse(value="The value of ${a.b.3} in ${a.b.d.0} is ${a.b.d}", dispatch=False),
            http_url="http://localhost:8081/mock",
            request_method="GET",
            headers=[HttpActionRequestBody(key="botid", parameter_type="slot", value="bot", encrypt=False),
                     HttpActionRequestBody(key="userid", parameter_type="value", value="1011", encrypt=True),
                     HttpActionRequestBody(key="tag", parameter_type="value", value="from_bot", encrypt=True)],
            params_list=[HttpActionRequestBody(key="bot", parameter_type="slot", value="bot", encrypt=False),
                         HttpActionRequestBody(key="user", parameter_type="value", value="1011", encrypt=False),
                         HttpActionRequestBody(key="tag", parameter_type="value", value="from_bot", encrypt=True)],
            set_slots=[SetSlotsFromResponse(name="val_d", value="${a.b.d}"),
                       SetSlotsFromResponse(name="val_d_0", value="${a.b.d.0}")],
            bot="5f50fd0a56b698ca10d35d2e",
            user="user"
        ).save()

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
            match=[responses.matchers.urlencoded_params_matcher({"bot": "5f50fd0a56b698ca10d35d2e", "user": "1011", "tag": "from_bot"})],
        )

        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e"},
                "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]},
                "latest_event_time": 1537645578.314389,
                "followup_action": "action_listen",
                "paused": False,
                "events": [{"event1": "hello"}, {"event2": "how are you"}],
                "latest_input_channel": "rest",
                "active_loop": {},
                "latest_action": {},
            },
            "domain": {
                "config": {},
                "session_config": {},
                "intents": [],
                "entities": [],
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e"},
                "responses": {},
                "actions": [],
                "forms": {},
                "e2e_actions": []
            },
            "version": "version"
        }
        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response.code, 200)
        self.assertEqual(len(response_json['events']), 3)
        self.assertEqual(len(response_json['responses']), 0)
        self.assertEqual(response_json['events'], [
            {"event": "slot", "timestamp": None, "name": "val_d", "value": "['red', 'buggy', 'bumpers']"},
            {"event": "slot", "timestamp": None, "name": "val_d_0", "value": "red"},
            {"event": "slot", "timestamp": None, "name": "kairon_action_response",
             "value": "The value of 2 in red is ['red', 'buggy', 'bumpers']"}])
        self.assertEqual(response_json['responses'], [])
        log = ActionServerLogs.objects(action=action_name).get().to_mongo().to_dict()
        log.pop('_id')
        log.pop('timestamp')
        assert log == {'type': 'http_action', 'intent': 'test_run', 'user_msg': 'get intents',
                       'action': 'test_http_action_execution_no_response_dispatch', 'sender': 'default',
                       'headers': {'botid': '5f50fd0a56b698ca10d35d2e', 'userid': '****', 'tag': '******ot'},
                       'url': 'http://localhost:8081/mock', 'request_method': 'GET',
                       'request_params': {'bot': '5f50fd0a56b698ca10d35d2e', 'user': '1011', 'tag': '******ot'},
                       'api_response': "{'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}",
                       'bot_response': "The value of 2 in red is ['red', 'buggy', 'bumpers']", 'messages': [
                "expression: The value of ${a.b.3} in ${a.b.d.0} is ${a.b.d} || data: {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}} || response: The value of 2 in red is ['red', 'buggy', 'bumpers']",
                'initiating slot evaluation',
                "slot: val_d || expression: ${a.b.d} || data: {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}} || response: ['red', 'buggy', 'bumpers']",
                "slot: val_d_0 || expression: ${a.b.d.0} || data: {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}} || response: red"],
                       'bot': '5f50fd0a56b698ca10d35d2e', 'status': 'SUCCESS'}

    def test_http_action_execution_script_evaluation(self):
        action_name = "test_http_action_execution_script_evaluation"
        Actions(name=action_name, type=ActionType.http_action.value, bot="5f50fd0a56b698ca10d35d2e", user="user").save()
        HttpActionConfig(
            action_name=action_name,
            content_type="json",
            response=HttpActionResponse(
                value="'The value of '+`${a.b.d}`+' in '+`${a.b.d.0}`+' is '+`${a.b.d}`",
                dispatch=False, evaluation_type="script"),
            http_url="http://localhost:8081/mock",
            request_method="GET",
            headers=[HttpActionRequestBody(key="botid", parameter_type="slot", value="bot", encrypt=False),
                     HttpActionRequestBody(key="userid", parameter_type="value", value="1011", encrypt=True),
                     HttpActionRequestBody(key="tag", parameter_type="value", value="from_bot", encrypt=True)],
            params_list=[HttpActionRequestBody(key="bot", parameter_type="slot", value="bot", encrypt=False),
                         HttpActionRequestBody(key="user", parameter_type="value", value="1011", encrypt=False),
                         HttpActionRequestBody(key="tag", parameter_type="value", value="from_bot", encrypt=True)],
            set_slots=[SetSlotsFromResponse(name="val_d", value="${a.b.d}", evaluation_type="script"),
                       SetSlotsFromResponse(name="val_d_0", value="${a.b.d.0}", evaluation_type="script")],
            bot="5f50fd0a56b698ca10d35d2e",
            user="user"
        ).save()

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
            match=[responses.matchers.json_params_matcher({"bot": "5f50fd0a56b698ca10d35d2e", "user": "1011", "tag": "from_bot"})],
        )
        responses.add(
            method=responses.POST,
            url=Utility.environment['evaluator']['url'],
            json={"success": True, "data": "The value of 2 in red is ['red', 'buggy', 'bumpers']"},
            status=200,
            match=[
                responses.matchers.json_params_matcher(
                    {'script': "'The value of '+`${a.b.d}`+' in '+`${a.b.d.0}`+' is '+`${a.b.d}`",
                     'data': {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}})],
        )
        responses.add(
            method=responses.POST,
            url=Utility.environment['evaluator']['url'],
            json={"success": True, "data": "['red', 'buggy', 'bumpers']"},
            status=200,
            match=[
                responses.matchers.json_params_matcher(
                    {'script': "${a.b.d}",
                     'data': {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}})],
        )
        responses.add(
            method=responses.POST,
            url=Utility.environment['evaluator']['url'],
            json={"success": True, "data": "red"},
            status=200,
            match=[
                responses.matchers.json_params_matcher(
                    {'script': "${a.b.d.0}",
                     'data': {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}})],
        )

        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e"},
                "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]},
                "latest_event_time": 1537645578.314389,
                "followup_action": "action_listen",
                "paused": False,
                "events": [{"event1": "hello"}, {"event2": "how are you"}],
                "latest_input_channel": "rest",
                "active_loop": {},
                "latest_action": {},
            },
            "domain": {
                "config": {},
                "session_config": {},
                "intents": [],
                "entities": [],
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e"},
                "responses": {},
                "actions": [],
                "forms": {},
                "e2e_actions": []
            },
            "version": "version"
        }
        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response.code, 200)
        self.assertEqual(len(response_json['events']), 3)
        self.assertEqual(len(response_json['responses']), 0)
        self.assertEqual(response_json['events'], [
            {"event": "slot", "timestamp": None, "name": "val_d", "value": "['red', 'buggy', 'bumpers']"},
            {"event": "slot", "timestamp": None, "name": "val_d_0", "value": "red"},
            {"event": "slot", "timestamp": None, "name": "kairon_action_response",
             "value": "The value of 2 in red is ['red', 'buggy', 'bumpers']"}])
        self.assertEqual(response_json['responses'], [])

    def test_http_action_execution_script_evaluation_failure_no_dispatch(self):
        action_name = "test_http_action_execution_script_evaluation_failure"
        Actions(name=action_name, type=ActionType.http_action.value, bot="5f50fd0a56b698ca10d35d2e", user="user").save()
        HttpActionConfig(
            action_name=action_name,
            content_type="json",
            response=HttpActionResponse(
                value="'The value of '+`${a.b.d}`+' in '+`${a.b.d.0}`+' is '+`${a.b.d}`",
                dispatch=False, evaluation_type="script"),
            http_url="http://localhost:8081/mock",
            request_method="GET",
            headers=[HttpActionRequestBody(key="botid", parameter_type="slot", value="bot", encrypt=False),
                     HttpActionRequestBody(key="userid", parameter_type="value", value="1011", encrypt=True),
                     HttpActionRequestBody(key="tag", parameter_type="value", value="from_bot", encrypt=True)],
            params_list=[HttpActionRequestBody(key="bot", parameter_type="slot", value="bot", encrypt=False),
                         HttpActionRequestBody(key="user", parameter_type="value", value="1011", encrypt=False),
                         HttpActionRequestBody(key="tag", parameter_type="value", value="from_bot", encrypt=True)],
            set_slots=[SetSlotsFromResponse(name="val_d", value="${e}", evaluation_type="script"),
                       SetSlotsFromResponse(name="val_d_0", value="${a.b.d}", evaluation_type="script")],
            bot="5f50fd0a56b698ca10d35d2e",
            user="user"
        ).save()

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
        responses.reset()
        responses.start()
        responses.add(
            method=responses.GET,
            url=http_url,
            body=resp_msg,
            status=200,
            match=[responses.matchers.json_params_matcher({"bot": "5f50fd0a56b698ca10d35d2e", "user": "1011", "tag": "from_bot"})],
        )
        responses.add(
            method=responses.POST,
            url=Utility.environment['evaluator']['url'],
            json={"success": True, "data": "The value of 2 in red is ['red', 'buggy', 'bumpers']"},
            status=200,
            match=[
                responses.matchers.json_params_matcher(
                    {'script': "'The value of '+`${a.b.d}`+' in '+`${a.b.d.0}`+' is '+`${a.b.d}`",
                     'data': {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}})],
        )
        responses.add(
            method=responses.POST,
            url=Utility.environment['evaluator']['url'],
            json={"success": False, "data": None},
            status=200,
            match=[
                responses.matchers.json_params_matcher(
                    {'script': "${e}",
                     'data': {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}})],
        )

        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e"},
                "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]},
                "latest_event_time": 1537645578.314389,
                "followup_action": "action_listen",
                "paused": False,
                "events": [{"event1": "hello"}, {"event2": "how are you"}],
                "latest_input_channel": "rest",
                "active_loop": {},
                "latest_action": {},
            },
            "domain": {
                "config": {},
                "session_config": {},
                "intents": [],
                "entities": [],
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e"},
                "responses": {},
                "actions": [],
                "forms": {},
                "e2e_actions": []
            },
            "version": "version"
        }
        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response.code, 200)
        self.assertEqual(len(response_json['events']), 3)
        self.assertEqual(len(response_json['responses']), 0)
        self.assertEqual(response_json['events'], [
            {"event": "slot", "timestamp": None, "name": "val_d", "value": None},
            {"event": "slot", "timestamp": None, "name": "val_d_0", "value": None},
            {"event": "slot", "timestamp": None, "name": "kairon_action_response",
             "value": "The value of 2 in red is ['red', 'buggy', 'bumpers']"}])
        self.assertEqual(response_json['responses'], [])

    def test_http_action_execution_script_evaluation_failure_and_dispatch(self):
        action_name = "test_http_action_execution_script_evaluation_failure_and_dispatch"
        Actions(name=action_name, type=ActionType.http_action.value, bot="5f50fd0a56b698ca10d35d2e", user="user").save()
        HttpActionConfig(
            action_name=action_name,
            content_type="json",
            response=HttpActionResponse(
                value="'The value of '+`${a.b.d}`+' in '+`${a.b.d.0}`+' is '+`${a.b.d}`",
                dispatch=True, evaluation_type="script"),
            http_url="http://localhost:8081/mock",
            request_method="GET",
            headers=[HttpActionRequestBody(key="botid", parameter_type="slot", value="bot", encrypt=False),
                     HttpActionRequestBody(key="userid", parameter_type="value", value="1011", encrypt=True),
                     HttpActionRequestBody(key="tag", parameter_type="value", value="from_bot", encrypt=True)],
            params_list=[HttpActionRequestBody(key="bot", parameter_type="slot", value="bot", encrypt=False),
                         HttpActionRequestBody(key="user", parameter_type="value", value="1011", encrypt=False),
                         HttpActionRequestBody(key="tag", parameter_type="value", value="from_bot", encrypt=True)],
            set_slots=[SetSlotsFromResponse(name="val_d", value="${e}", evaluation_type="script"),
                       SetSlotsFromResponse(name="val_d_0", value="${a.b.d}", evaluation_type="script")],
            bot="5f50fd0a56b698ca10d35d2e",
            user="user"
        ).save()

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
        responses.reset()
        responses.start()
        responses.add(
            method=responses.GET,
            url=http_url,
            body=resp_msg,
            status=200,
            match=[responses.matchers.json_params_matcher({"bot": "5f50fd0a56b698ca10d35d2e", "user": "1011", "tag": "from_bot"})],
        )
        responses.add(
            method=responses.POST,
            url=Utility.environment['evaluator']['url'],
            json={"success": True, "data": "The value of 2 in red is ['red', 'buggy', 'bumpers']"},
            status=200,
            match=[
                responses.matchers.json_params_matcher(
                    {'script': "'The value of '+`${a.b.d}`+' in '+`${a.b.d.0}`+' is '+`${a.b.d}`",
                     'data': {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}})],
        )
        responses.add(
            method=responses.POST,
            url=Utility.environment['evaluator']['url'],
            json={"success": False, "data": None},
            status=200,
            match=[
                responses.matchers.json_params_matcher(
                    {'script': "${e}",
                     'data': {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}})],
        )

        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e"},
                "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]},
                "latest_event_time": 1537645578.314389,
                "followup_action": "action_listen",
                "paused": False,
                "events": [{"event1": "hello"}, {"event2": "how are you"}],
                "latest_input_channel": "rest",
                "active_loop": {},
                "latest_action": {},
            },
            "domain": {
                "config": {},
                "session_config": {},
                "intents": [],
                "entities": [],
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e"},
                "responses": {},
                "actions": [],
                "forms": {},
                "e2e_actions": []
            },
            "version": "version"
        }
        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response.code, 200)
        self.assertEqual(len(response_json['events']), 3)
        self.assertEqual(len(response_json['responses']), 1)
        self.assertEqual(response_json['events'], [
            {"event": "slot", "timestamp": None, "name": "val_d", "value": None},
            {"event": "slot", "timestamp": None, "name": "val_d_0", "value": None},
            {"event": "slot", "timestamp": None, "name": "kairon_action_response",
             "value": "The value of 2 in red is ['red', 'buggy', 'bumpers']"}])
        self.assertEqual(response_json['responses'][0]['text'], "The value of 2 in red is ['red', 'buggy', 'bumpers']")

    def test_http_action_execution_script_evaluation_failure_and_dispatch_2(self):
        action_name = "test_http_action_execution_script_evaluation_failure_and_dispatch_2"
        Actions(name=action_name, type=ActionType.http_action.value, bot="5f50fd0a56b698ca10d35d2e", user="user").save()
        HttpActionConfig(
            action_name=action_name,
            content_type="json",
            response=HttpActionResponse(
                value="'The value of '+`${a.b.d}`+' in '+`${a.b.d.0}`+' is '+`${a.b.d}`",
                dispatch=True, evaluation_type="script"),
            http_url="http://localhost:8081/mock",
            request_method="GET",
            headers=[HttpActionRequestBody(key="botid", parameter_type="slot", value="bot", encrypt=False),
                     HttpActionRequestBody(key="userid", parameter_type="value", value="1011", encrypt=True),
                     HttpActionRequestBody(key="tag", parameter_type="value", value="from_bot", encrypt=True)],
            params_list=[HttpActionRequestBody(key="bot", parameter_type="slot", value="bot", encrypt=False),
                         HttpActionRequestBody(key="user", parameter_type="value", value="1011", encrypt=False),
                         HttpActionRequestBody(key="tag", parameter_type="value", value="from_bot", encrypt=True)],
            set_slots=[SetSlotsFromResponse(name="val_d", value="${e}", evaluation_type="script"),
                       SetSlotsFromResponse(name="val_d_0", value="${a.b.d}", evaluation_type="script")],
            bot="5f50fd0a56b698ca10d35d2e",
            user="user"
        ).save()

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
        responses.reset()
        responses.start()
        responses.add(
            method=responses.GET,
            url=http_url,
            body=resp_msg,
            status=200,
            match=[responses.matchers.json_params_matcher({"bot": "5f50fd0a56b698ca10d35d2e", "user": "1011", "tag": "from_bot"})],
        )
        responses.add(
            method=responses.POST,
            url=Utility.environment['evaluator']['url'],
            json={"success": False, "data": "The value of 2 in red is ['red', 'buggy', 'bumpers']"},
            status=200,
            match=[
                responses.matchers.json_params_matcher(
                    {'script': "'The value of '+`${a.b.d}`+' in '+`${a.b.d.0}`+' is '+`${a.b.d}`",
                     'data': {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}})],
        )
        responses.add(
            method=responses.POST,
            url=Utility.environment['evaluator']['url'],
            json={"success": False, "data": None},
            status=200,
            match=[
                responses.matchers.json_params_matcher(
                    {'script': "${e}",
                     'data': {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}})],
        )

        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e"},
                "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]},
                "latest_event_time": 1537645578.314389,
                "followup_action": "action_listen",
                "paused": False,
                "events": [{"event1": "hello"}, {"event2": "how are you"}],
                "latest_input_channel": "rest",
                "active_loop": {},
                "latest_action": {},
            },
            "domain": {
                "config": {},
                "session_config": {},
                "intents": [],
                "entities": [],
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e"},
                "responses": {},
                "actions": [],
                "forms": {},
                "e2e_actions": []
            },
            "version": "version"
        }
        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response.code, 200)
        self.assertEqual(len(response_json['events']), 1)
        self.assertEqual(len(response_json['responses']), 1)
        self.assertEqual(response_json['events'], [
            {"event": "slot", "timestamp": None, "name": "kairon_action_response",
             "value": "I have failed to process your request"}])
        self.assertEqual(response_json['responses'][0]['text'], "I have failed to process your request")

    @patch("kairon.shared.actions.utils.ActionUtility.get_action")
    @patch("kairon.actions.definitions.http.ActionHTTP.retrieve_config")
    def test_http_action_failed_execution(self, mock_action_config, mock_action):
        action_name = "test_run_with_get"
        action = Actions(name=action_name, type=ActionType.http_action.value, bot="5f50fd0a56b698ca10d35d2e", user="user")
        action_config = HttpActionConfig(
            action_name=action_name,
            response=HttpActionResponse(value="The value of ${a.b.3} in ${a.b.d.0} is ${a.b.d}"),
            http_url="http://localhost:8082/mock",
            request_method="GET",
            bot="5f50fd0a56b698ca10d35d2e",
            user="user"
        )

        def _get_action_config(*arge, **kwargs):
            return action_config.to_mongo().to_dict()

        def _get_action(*arge, **kwargs):
            return action.to_mongo().to_dict()

        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {'bot': "5f50fd0a56b698ca10d35d2e"},
                "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]},
                "latest_event_time": 1537645578.314389,
                "followup_action": "action_listen",
                "paused": False,
                "events": [{"event1": "hello"}, {"event2": "how are you"}],
                "latest_input_channel": "rest",
                "active_loop": {},
                "latest_action": {},
            },
            "domain": {
                "config": {},
                "session_config": {},
                "intents": [],
                "entities": [],
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e"},
                "responses": {},
                "actions": [],
                "forms": {},
                "e2e_actions": []
            },
            "version": "version"
        }
        mock_action.side_effect = _get_action
        mock_action_config.side_effect = _get_action_config
        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response.code, 200)
        self.assertEqual(len(response_json['events']), 1)
        self.assertEqual(len(response_json['responses']), 1)
        self.assertEqual(response_json['events'], [
            {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
             'value': "I have failed to process your request"}])
        self.assertEqual(response_json['responses'][0]['text'], "I have failed to process your request")

    def test_http_action_missing_action_name(self):
        action_name = ""

        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {},
                "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]},
                "latest_event_time": 1537645578.314389,
                "followup_action": "action_listen",
                "paused": False,
                "events": [{"event1": "hello"}, {"event2": "how are you"}],
                "latest_input_channel": "rest",
                "active_loop": {},
                "latest_action": {},
            },
            "domain": {
                "config": {},
                "session_config": {},
                "intents": [],
                "entities": [],
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e"},
                "responses": {},
                "actions": [],
                "forms": {},
                "e2e_actions": []
            },
            "version": "version"
        }
        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response.code, 200)
        self.assertEqual(response_json, None)

    def test_http_action_doesnotexist(self):
        action_name = "does_not_exist_action"

        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e"},
                "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]},
                "latest_event_time": 1537645578.314389,
                "followup_action": "action_listen",
                "paused": False,
                "events": [{"event1": "hello"}, {"event2": "how are you"}],
                "latest_input_channel": "rest",
                "active_loop": {},
                "latest_action": {},
            },
            "domain": {
                "config": {},
                "session_config": {},
                "intents": [],
                "entities": [],
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e"},
                "responses": {},
                "actions": [],
                "forms": {},
                "e2e_actions": []
            },
            "version": "version"
        }
        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response.code, 200)
        self.assertEqual(response_json, {'events': [], 'responses': []})

    def test_slot_set_action_from_value(self):
        action_name = "test_slot_set_from_value"
        action = Actions(
            name=action_name, type=ActionType.slot_set_action.value, bot="5f50fd0a56b698ca10d35d2e", user="user"
        )
        action_config = SlotSetAction(
            name=action_name,
            set_slots=[SetSlots(name="location", type="from_value", value="Mumbai")],
            bot="5f50fd0a56b698ca10d35d2e",
            user="user"
        )

        def _get_action_config(*arge, **kwargs):
            return action_config.to_mongo().to_dict()

        def _get_action(*arge, **kwargs):
            return action.to_mongo().to_dict()

        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e", "location": None},
                "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]},
                "latest_event_time": 1537645578.314389,
                "followup_action": "action_listen",
                "paused": False,
                "events": [{"event1": "hello"}, {"event2": "how are you"}],
                "latest_input_channel": "rest",
                "active_loop": {},
                "latest_action": {},
            },
            "domain": {
                "config": {},
                "session_config": {},
                "intents": [],
                "entities": [],
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e", "location": None},
                "responses": {},
                "actions": [],
                "forms": {},
                "e2e_actions": []
            },
            "version": "version"
        }
        with patch.object(ActionUtility, "get_action") as mock_action:
            mock_action.side_effect = _get_action
            with patch.object(ActionSetSlot, "retrieve_config") as mocked:
                mocked.side_effect = _get_action_config
                response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
                response_json = json.loads(response.body.decode("utf8"))
                self.assertEqual(response.code, 200)
                self.assertEqual(len(response_json['events']), 1)
                self.assertEqual(len(response_json['responses']), 0)
                self.assertEqual(response_json['events'],
                                 [{'event': 'slot', 'timestamp': None, 'name': 'location', 'value': 'Mumbai'}])
                self.assertEqual(response_json['responses'], [])

    def test_slot_set_action_reset_slot(self):
        action_name = "test_slot_set_action_reset_slot"
        action = Actions(
            name=action_name, type=ActionType.slot_set_action.value, bot="5f50fd0a56b698ca10d35d2e", user="user"
        )
        action_config = SlotSetAction(
            name=action_name,
            set_slots=[SetSlots(name="location", type="reset_slot", value="current_location"),
                       SetSlots(name="name", type="from_value", value="end_user"),
                       SetSlots(name="age", type="reset_slot")],
            bot="5f50fd0a56b698ca10d35d2e",
            user="user"
        )

        def _get_action_config(*arge, **kwargs):
            return action_config.to_mongo().to_dict()

        def _get_action(*arge, **kwargs):
            return action.to_mongo().to_dict()

        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e", "location": 'Bengaluru', 'current_location': 'Bengaluru', "name": "Udit", "age": 24},
                "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]},
                "latest_event_time": 1537645578.314389,
                "followup_action": "action_listen",
                "paused": False,
                "events": [{"event1": "hello"}, {"event2": "how are you"}],
                "latest_input_channel": "rest",
                "active_loop": {},
                "latest_action": {},
            },
            "domain": {
                "config": {},
                "session_config": {},
                "intents": [],
                "entities": [],
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e", "location": None, 'current_location': None},
                "responses": {},
                "actions": [],
                "forms": {},
                "e2e_actions": []
            },
            "version": "version"
        }
        with patch.object(ActionUtility, "get_action") as mock_action:
            mock_action.side_effect = _get_action
            with patch.object(ActionSetSlot, "retrieve_config") as mocked:
                mocked.side_effect = _get_action_config
                response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
                response_json = json.loads(response.body.decode("utf8"))
                self.assertEqual(response.code, 200)
                self.assertEqual(len(response_json['events']), 3)
                self.assertEqual(len(response_json['responses']), 0)
                self.assertEqual(response_json['events'],
                                 [{'event': 'slot', 'timestamp': None, 'name': 'location', 'value': None},
                                  {'event': 'slot', 'timestamp': None, 'name': 'name', 'value': "end_user"},
                                  {'event': 'slot', 'timestamp': None, 'name': 'age', 'value': None}])
                self.assertEqual(response_json['responses'], [])

    def test_slot_set_action_from_slot_not_present(self):
        action_name = "test_slot_set_action_from_slot_not_present"
        action = Actions(
            name=action_name, type=ActionType.slot_set_action.value, bot="5f50fd0a56b698ca10d35d2e", user="user"
        )
        action_config = SlotSetAction(
            name=action_name,
            set_slots=[SetSlots(name="location", type="from_slot", value="current_location")],
            bot="5f50fd0a56b698ca10d35d2e",
            user="user"
        )

        def _get_action_config(*arge, **kwargs):
            return action_config.to_mongo().to_dict()

        def _get_action(*arge, **kwargs):
            return action.to_mongo().to_dict()

        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e", "location": None},
                "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]},
                "latest_event_time": 1537645578.314389,
                "followup_action": "action_listen",
                "paused": False,
                "events": [{"event1": "hello"}, {"event2": "how are you"}],
                "latest_input_channel": "rest",
                "active_loop": {},
                "latest_action": {},
            },
            "domain": {
                "config": {},
                "session_config": {},
                "intents": [],
                "entities": [],
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e", "location": None},
                "responses": {},
                "actions": [],
                "forms": {},
                "e2e_actions": []
            },
            "version": "version"
        }
        with patch.object(ActionUtility, "get_action") as mock_action:
            mock_action.side_effect = _get_action
            with patch.object(ActionSetSlot, "retrieve_config") as mocked:
                mocked.side_effect = _get_action_config
                response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
                response_json = json.loads(response.body.decode("utf8"))
                self.assertEqual(response.code, 200)
                self.assertEqual(len(response_json['events']), 1)
                self.assertEqual(len(response_json['responses']), 0)
                self.assertEqual(response_json['events'],
                                 [{'event': 'slot', 'timestamp': None, 'name': 'location', 'value': None}])
                self.assertEqual(response_json['responses'], [])

    def test_invalid_action(self):
        action_name = "custom_user_action"

        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e"},
                "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]},
                "latest_event_time": 1537645578.314389,
                "followup_action": "action_listen",
                "paused": False,
                "events": [{"event1": "hello"}, {"event2": "how are you"}],
                "latest_input_channel": "rest",
                "active_loop": {},
                "latest_action": {},
            },
            "domain": {
                "config": {},
                "session_config": {},
                "intents": [],
                "entities": [],
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e"},
                "responses": {},
                "actions": [],
                "forms": {},
                "e2e_actions": []
            },
            "version": "version"
        }
        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response.code, 200)
        self.assertEqual(response_json, {'events': [], 'responses': []})

    def test_form_validation_action_valid_slot_value(self):
        action_name = "validate_location"
        bot = '5f50fd0a56b698ca10d35d2e'
        user = 'test_user'
        slot = 'location'
        semantic_expression = {'and': [{'and': [{'operator': 'in', 'value': ['Mumbai', 'Bangalore']},
                                                {'operator': 'startswith', 'value': 'M'},
                                                {'operator': 'endswith', 'value': 'i'},
                                                ]},
                                       {'or': [{'operator': 'has_length_greater_than', 'value': 20},
                                               {'operator': 'has_no_whitespace'},
                                               {'operator': 'matches_regex', 'value': '^[e]+.*[e]$'}]}]}
        Actions(name=action_name, type=ActionType.form_validation_action.value, bot=bot, user=user).save()
        FormValidationAction(name=action_name, slot=slot, validation_semantic=semantic_expression,
                             bot=bot, user=user).save()
        Slots(name=slot, type='text', bot=bot, user=user).save()

        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {"bot": bot, slot: 'Mumbai', 'requested_slot': slot},
                "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]},
                "latest_event_time": 1537645578.314389,
                "followup_action": "action_listen",
                "paused": False,
                "events": [{"event1": "hello"}, {"event2": "how are you"}],
                "latest_input_channel": "rest",
                "active_loop": {},
                "latest_action": {},
            },
            "domain": {
                "config": {},
                "session_config": {},
                "intents": [],
                "entities": [],
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e", "location": None},
                "responses": {},
                "actions": [],
                "forms": {},
                "e2e_actions": []
            },
            "version": "version"
        }
        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response.code, 200)
        self.assertEqual(response_json,
                         {'events': [{'event': 'slot', 'timestamp': None, 'name': 'location', 'value': 'Mumbai'}],
                          'responses': []})

    def test_form_validation_action_no_requested_slot(self):
        action_name = "validate_requested_slot"
        bot = '5f50fd0a56b698ca10d35d2e'
        user = 'test_user'
        slot = 'location'
        Actions(name=action_name, type=ActionType.form_validation_action.value, bot=bot, user=user).save()

        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {"bot": bot, slot: 'Mumbai', 'requested_slot': None},
                "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]},
                "latest_event_time": 1537645578.314389,
                "followup_action": "action_listen",
                "paused": False,
                "events": [{"event1": "hello"}, {"event2": "how are you"}],
                "latest_input_channel": "rest",
                "active_loop": {},
                "latest_action": {},
            },
            "domain": {
                "config": {},
                "session_config": {},
                "intents": [],
                "entities": [],
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e", "location": None},
                "responses": {},
                "actions": [],
                "forms": {},
                "e2e_actions": []
            },
            "version": "version"
        }
        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response.code, 200)
        self.assertEqual(response_json, {'events': [], 'responses': []})

    def test_form_validation_action_no_validation_provided_for_slot_with_none_value(self):
        action_name = "slot_with_none_value"
        bot = '5f50fd0a56b698ca10d35d2f'
        user = 'test_user'
        slot = 'location'
        Actions(name=action_name, type=ActionType.form_validation_action.value, bot=bot, user=user).save()
        FormValidationAction(name=action_name, slot=slot, validation_semantic={}, bot=bot, user=user).save()
        Slots(name=slot, type='text', bot=bot, user=user).save()

        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {"bot": bot, slot: None, 'requested_slot': slot},
                "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]},
                "latest_event_time": 1537645578.314389,
                "followup_action": "action_listen",
                "paused": False,
                "events": [{"event1": "hello"}, {"event2": "how are you"}],
                "latest_input_channel": "rest",
                "active_loop": {},
                "latest_action": {},
            },
            "domain": {
                "config": {},
                "session_config": {},
                "intents": [],
                "entities": [],
                "slots": {"bot": bot, "location": None},
                "responses": {},
                "actions": [],
                "forms": {},
                "e2e_actions": []
            },
            "version": "version"
        }
        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response.code, 200)
        self.assertEqual(response_json,
                         {'events': [{'event': 'slot', 'timestamp': None, 'name': 'location', 'value': None}],
                          'responses': []})

    def test_form_validation_action_valid_slot_value_with_utterance(self):
        action_name = "validate_user"
        bot = '5f50fd0a56b698ca10d35d2e'
        user = 'test_user'
        slot = 'user_id'
        semantic_expression = {'and': [{'and': [{'operator': 'is_an_email_address'},
                                                {'operator': 'is_not_null_or_empty'},
                                                {'operator': 'endswith', 'value': '.com'},
                                                ]},
                                       {'or': [{'operator': 'has_length_greater_than', 'value': 4},
                                               {'operator': 'has_no_whitespace'},
                                               ]}]}
        Actions(name=action_name, type=ActionType.form_validation_action.value, bot=bot, user=user).save()
        FormValidationAction(name=action_name, slot='location', validation_semantic=semantic_expression,
                             bot=bot, user=user).save()
        FormValidationAction(name=action_name, slot=slot, validation_semantic=semantic_expression,
                             bot=bot, user=user,
                             valid_response='that is great!').save()
        Slots(name=slot, type='text', bot=bot, user=user).save()

        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {"bot": bot, slot: 'pandey.udit867@gmail.com', 'requested_slot': slot},
                "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]},
                "latest_event_time": 1537645578.314389,
                "followup_action": "action_listen",
                "paused": False,
                "events": [{"event1": "hello"}, {"event2": "how are you"}],
                "latest_input_channel": "rest",
                "active_loop": {},
                "latest_action": {},
            },
            "domain": {
                "config": {},
                "session_config": {},
                "intents": [],
                "entities": [],
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e", "location": None},
                "responses": {},
                "actions": [],
                "forms": {},
                "e2e_actions": []
            },
            "version": "version"
        }
        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response.code, 200)
        self.assertEqual(response_json, {'events': [{'event': 'slot', 'timestamp': None, 'name': 'user_id', 'value': 'pandey.udit867@gmail.com'}], 'responses': [{'text': 'that is great!', 'buttons': [], 'elements': [], 'custom': {}, 'template': None, 'response': None, 'image': None, 'attachment': None}]}
)

    def test_form_validation_action_invalid_slot_value(self):
        action_name = "validate_form_with_3_validations"
        bot = '5f50fd0a56b698ca10d35d2e'
        user = 'test_user'
        slot = 'current_location'
        semantic_expression = {'and': [{'and': [{'operator': 'in', 'value': ['Mumbai', 'Bangalore']},
                                                {'operator': 'startswith', 'value': 'M'},
                                                {'operator': 'endswith', 'value': 'i'},
                                                ]},
                                       {'or': [{'operator': 'has_length_greater_than', 'value': 20},
                                               {'operator': 'has_no_whitespace'},
                                               {'operator': 'matches_regex', 'value': '^[e]+.*[e]$'}]}]}
        Actions(name=action_name, type=ActionType.form_validation_action.value, bot=bot, user=user).save()
        FormValidationAction(name=action_name, slot='name', validation_semantic=semantic_expression,
                             bot=bot, user=user).save().to_mongo().to_dict()
        FormValidationAction(name=action_name, slot='user_id', validation_semantic=semantic_expression,
                             bot=bot, user=user, valid_response='that is great!').save().to_mongo().to_dict()
        FormValidationAction(name=action_name, slot=slot, validation_semantic=semantic_expression,
                             bot=bot, user=user).save().to_mongo().to_dict()
        Slots(name=slot, type='text', bot=bot, user=user).save()

        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {"bot": bot, slot: 'Delhi', 'requested_slot': slot},
                "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]},
                "latest_event_time": 1537645578.314389,
                "followup_action": "action_listen",
                "paused": False,
                "events": [{"event1": "hello"}, {"event2": "how are you"}],
                "latest_input_channel": "rest",
                "active_loop": {},
                "latest_action": {},
            },
            "domain": {
                "config": {},
                "session_config": {},
                "intents": [],
                "entities": [],
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e", "current_location": None},
                "responses": {},
                "actions": [],
                "forms": {},
                "e2e_actions": []
            },
            "version": "version"
        }
        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response.code, 200)
        self.assertEqual(response_json,
                         {'events': [{'event': 'slot', 'timestamp': None, 'name': 'current_location', 'value': None}],
                          'responses': []})

    def test_form_validation_action_invalid_slot_value_with_utterance(self):
        action_name = "validate_form"
        bot = '5f50fd0a56b698ca10d35d2e'
        user = 'test_user'
        slot = 'profession'
        semantic_expression = {'and': [{'and': [{'operator': 'is_not_null_or_empty'},
                                                {'operator': 'endswith', 'value': '.com'},
                                                ]},
                                       {'or': [{'operator': 'has_length_greater_than', 'value': 4},
                                               {'operator': 'has_no_whitespace'},
                                               ]}]}
        Actions(name=action_name, type=ActionType.form_validation_action.value, bot=bot, user=user).save()
        FormValidationAction(name=action_name, slot='some_slot', validation_semantic=semantic_expression,
                             bot=bot, user=user).save().to_mongo().to_dict()
        FormValidationAction(name=action_name, slot=slot, validation_semantic=semantic_expression,
                             bot=bot, user=user, valid_response='that is great!',
                             invalid_response='Invalid value. Please type again!').save().to_mongo().to_dict()
        Slots(name=slot, type='text', bot=bot, user=user).save()

        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {"bot": bot, slot: 'computer programmer', 'requested_slot': slot},
                "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]},
                "latest_event_time": 1537645578.314389,
                "followup_action": "action_listen",
                "paused": False,
                "events": [{"event1": "hello"}, {"event2": "how are you"}],
                "latest_input_channel": "rest",
                "active_loop": {},
                "latest_action": {},
            },
            "domain": {
                "config": {},
                "session_config": {},
                "intents": [],
                "entities": [],
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e", "location": None},
                "responses": {},
                "actions": [],
                "forms": {},
                "e2e_actions": []
            },
            "version": "version"
        }
        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response.code, 200)
        self.assertEqual(response_json, {'events': [{'event': 'slot', 'timestamp': None, 'name': 'profession', 'value': None}], 'responses': [{'text': 'Invalid value. Please type again!', 'buttons': [], 'elements': [], 'custom': {}, 'template': None, 'response': None, 'image': None, 'attachment': None}]}
)

    def test_form_validation_action_no_validation_configured(self):
        action_name = "validate_user_details"
        bot = '5f50fd0a56b698ca10d35d2e'
        user = 'test_user'
        slot = 'age'
        Actions(name=action_name, type=ActionType.form_validation_action.value, bot=bot, user=user).save()
        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {"bot": bot, slot: 10, 'requested_slot': slot},
                "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]},
                "latest_event_time": 1537645578.314389,
                "followup_action": "action_listen",
                "paused": False,
                "events": [{"event1": "hello"}, {"event2": "how are you"}],
                "latest_input_channel": "rest",
                "active_loop": {},
                "latest_action": {},
            },
            "domain": {
                "config": {},
                "session_config": {},
                "intents": [],
                "entities": [],
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e", "location": None},
                "responses": {},
                "actions": [],
                "forms": {},
                "e2e_actions": []
            },
            "version": "version"
        }
        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response.code, 200)
        self.assertEqual(response_json, {
            'events': [{'event': 'slot', 'timestamp': None, 'name': 'age', 'value': 10}],
            'responses': []})

        semantic_expression = {'and': [{'and': [{'operator': 'is_not_null_or_empty'},
                                                {'operator': 'ends_with', 'value': '.com'},
                                                ]},
                                       {'or': [{'operator': 'has_length_greater_than', 'value': 4},
                                               {'operator': 'has_no_whitespace'},
                                               ]}]}
        FormValidationAction(name=action_name, slot='name', validation_semantic=semantic_expression,
                             bot=bot, user=user, valid_response='that is great!').save()
        FormValidationAction(name=action_name, slot='occupation', validation_semantic=semantic_expression,
                             bot=bot, user=user, valid_response='that is great!').save()
        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response.code, 200)
        self.assertEqual(response_json, {
            'events': [{'event': 'slot', 'timestamp': None, 'name': 'age', 'value': 10}],
            'responses': []})

    def test_form_validation_action_slot_type_not_found(self):
        action_name = "validate_hotel_booking"
        bot = '5f50fd0a56b698ca10d35d2e'
        user = 'test_user'
        slot = 'reservation_id'
        Actions(name=action_name, type=ActionType.form_validation_action.value, bot=bot, user=user).save()
        FormValidationAction(name=action_name, slot=slot, validation_semantic={},
                             bot=bot, user=user, valid_response='that is great!',
                             invalid_response='Invalid value. Please type again!').save()
        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {"bot": bot, slot: '10974872t49', 'requested_slot': slot},
                "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]},
                "latest_event_time": 1537645578.314389,
                "followup_action": "action_listen",
                "paused": False,
                "events": [{"event1": "hello"}, {"event2": "how are you"}],
                "latest_input_channel": "rest",
                "active_loop": {},
                "latest_action": {},
            },
            "domain": {
                "config": {},
                "session_config": {},
                "intents": [],
                "entities": [],
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e", "location": None},
                "responses": {},
                "actions": [],
                "forms": {},
                "e2e_actions": []
            },
            "version": "version"
        }
        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response.code, 200)
        self.assertEqual(response_json, {'events': [], 'responses': []})

    @patch("kairon.shared.actions.utils.ActionUtility.get_action")
    @patch("kairon.actions.definitions.email.ActionEmail.retrieve_config")
    @patch("kairon.shared.utils.SMTP", autospec=True)
    def test_email_action_execution_script_evaluation(self, mock_smtp, mock_action_config, mock_action):
        mock_env = mock.patch.dict(Utility.environment['evaluator'], {'url': 'http://kairon:8080/format'})
        mock_env.start()
        Utility.email_conf['email']['templates']['custom_text_mail'] = open('template/emails/custom_text_mail.html', 'rb').read().decode()

        bot = "5f50fd0a65b698ca10d35d2e"
        user = "udit.pandey"

        action_name = "test_run_email_script_action"
        action = Actions(name=action_name, type=ActionType.email_action.value, bot="5f50fd0a56b698ca10d35d2e", user="user")
        action_config = EmailActionConfig(
            action_name=action_name,
            smtp_url="test.localhost",
            smtp_port=293,
            smtp_password=CustomActionRequestParameters(key='smtp_password', value="test"),
            from_email="test@demo.com",
            subject="test script",
            to_email=["test@test.com"],
            response="Email Triggered",
            custom_text="The user has id ${sender_id}",
            bot=bot,
            user=user
        )

        def _get_action(*arge, **kwargs):
            return action.to_mongo().to_dict()

        def _get_action_config(*arge, **kwargs):
            return action_config.to_mongo().to_dict()

        request_object = json.load(open("tests/testing_data/actions/action-request.json"))
        request_object["tracker"]["slots"]["bot"] = bot
        request_object["next_action"] = action_name
        request_object["tracker"]["sender_id"] = user
        request_object["tracker"]["latest_message"]['text'] = 'hello'

        responses.add(
            method=responses.POST,
            url=Utility.environment['evaluator']['url'],
            json={"success": True, "data": "The user has id udit.pandey"},
            status=200
        )

        mock_action.side_effect = _get_action
        mock_action_config.side_effect = _get_action_config
        responses.start()
        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        responses.reset()
        mock_env.stop()
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response.code, 200)
        self.assertEqual(len(response_json['events']), 1)
        self.assertEqual(len(response_json['responses']), 1)
        self.assertEqual(response_json['events'], [
            {"event": "slot", "timestamp": None, "name": "kairon_action_response",
             "value": "Email Triggered"}])
        self.assertEqual(response_json['responses'][0]['text'],
                         "Email Triggered")

        name, args, kwargs = mock_smtp.method_calls.pop(0)
        assert name == '().connect'
        assert {} == kwargs

        host, port = args
        assert host == action_config.smtp_url
        assert port == action_config.smtp_port
        name, args, kwargs = mock_smtp.method_calls.pop(0)
        assert name == '().login'
        assert {} == kwargs

        from_email, password = args
        assert from_email == action_config.from_email
        assert password == action_config.smtp_password.value

        name, args, kwargs = mock_smtp.method_calls.pop(0)
        assert name == '().sendmail'
        assert {} == kwargs

        assert args[0] == action_config.from_email
        assert args[1] == ["test@test.com"]
        assert str(args[2]).__contains__(action_config.subject)
        assert str(args[2]).__contains__("Content-Type: text/html")

    @patch("kairon.shared.actions.utils.ActionUtility.get_action")
    @patch("kairon.actions.definitions.email.ActionEmail.retrieve_config")
    def test_email_action_execution_script_evaluation_failure(self, mock_action_config, mock_action):
        Utility.email_conf['email']['templates']['custom_text_mail'] = open(
            'template/emails/custom_text_mail.html', 'rb').read().decode()

        bot = "5c89fd0a65b698ca10d35d2e"
        user = "test_user"

        action_name = "test_run_email_script_action_failure"
        action = Actions(name=action_name, type=ActionType.email_action.value, bot="5c89fd0a65b698ca10d35d2e",
                         user="test_user")
        action_config = EmailActionConfig(
            action_name=action_name,
            smtp_url="test.localhost",
            smtp_port=293,
            smtp_password=CustomActionRequestParameters(key='smtp_password', value="test"),
            from_email="test@demo.com",
            subject="test script",
            to_email=["test@test.com"],
            response="Email Triggered",
            custom_text="The user has message ${message}",
            bot=bot,
            user=user
        )

        def _get_action(*arge, **kwargs):
            return action.to_mongo().to_dict()

        def _get_action_config(*arge, **kwargs):
            return action_config.to_mongo().to_dict()

        request_object = json.load(open("tests/testing_data/actions/action-request.json"))
        request_object["tracker"]["slots"]["bot"] = bot
        request_object["next_action"] = action_name
        request_object["tracker"]["sender_id"] = user
        request_object["tracker"]["latest_message"]['text'] = 'hello'
        Actions(name=action_name, type=ActionType.email_action.value, bot='5c89fd0a65b698ca10d35d2e',
                user='test_user').save()

        responses.add(
            method=responses.POST,
            url=Utility.environment['evaluator']['url'],
            json={"success": False, "data": "The user has message ${message}"},
            status=200,
        )

        mock_action.side_effect = _get_action
        mock_action_config.side_effect = _get_action_config
        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        responses.reset()
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response.code, 200)
        self.assertEqual(len(response_json['events']), 1)
        self.assertEqual(len(response_json['responses']), 1)
        self.assertEqual(response_json['events'], [
            {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
             'value': "I have failed to process your request"}])
        self.assertEqual(response_json['responses'][0]['text'],
                         "I have failed to process your request")

    @patch("kairon.shared.actions.utils.ActionUtility.get_action")
    @patch("kairon.actions.definitions.email.ActionEmail.retrieve_config")
    @patch("kairon.shared.utils.SMTP", autospec=True)
    def test_email_action_execution(self, mock_smtp, mock_action_config, mock_action):
        Utility.email_conf['email']['templates']['conversation'] = open('template/emails/conversation.html', 'rb').read().decode()
        Utility.email_conf['email']['templates']['bot_msg_conversation'] = open('template/emails/bot_msg_conversation.html', 'rb').read().decode()
        Utility.email_conf['email']['templates']['user_msg_conversation'] = open('template/emails/user_msg_conversation.html', 'rb').read().decode()
        Utility.email_conf['email']['templates']['button_template'] = open('template/emails/button.html', 'rb').read().decode()

        action_name = "test_run_email_action"
        action = Actions(name=action_name, type=ActionType.email_action.value, bot="bot", user="user")
        action_config = EmailActionConfig(
                action_name=action_name,
                smtp_url="test.localhost",
                smtp_port=293,
                smtp_password=CustomActionRequestParameters(key='smtp_password', value="test"),
                from_email="test@demo.com",
                subject="test",
                to_email=["test@test.com"],
                response="Email Triggered",
                bot="bot",
                user="user"
            )

        def _get_action(*arge, **kwargs):
            return action.to_mongo().to_dict()

        def _get_action_config(*arge, **kwargs):
            return action_config.to_mongo().to_dict()

        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e"},
                "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]},
                "latest_event_time": 1537645578.314389,
                "followup_action": "action_listen",
                "paused": False,
                "events": [{"event":"action","timestamp":1594907100.12764,"name":"action_session_start","policy":None,"confidence":None},{"event":"session_started","timestamp":1594907100.12765},{"event":"action","timestamp":1594907100.12767,"name":"action_listen","policy":None,"confidence":None},{"event":"user","timestamp":1594907100.42744,"text":"can't","parse_data":{"intent":{"name":"test intent","confidence":0.253578245639801},"entities":[],"intent_ranking":[{"name":"test intent","confidence":0.253578245639801},{"name":"goodbye","confidence":0.1504897326231},{"name":"greet","confidence":0.138640150427818},{"name":"affirm","confidence":0.0857767835259438},{"name":"smalltalk_human","confidence":0.0721133947372437},{"name":"deny","confidence":0.069614589214325},{"name":"bot_challenge","confidence":0.0664894133806229},{"name":"faq_vaccine","confidence":0.062177762389183},{"name":"faq_testing","confidence":0.0530692934989929},{"name":"out_of_scope","confidence":0.0480506233870983}],"response_selector":{"default":{"response":{"name":None,"confidence":0},"ranking":[],"full_retrieval_intent":None}},"text":"can't"},"input_channel":None,"message_id":"bbd413bf5c834bf3b98e0da2373553b2","metadata":{}},{"event":"action","timestamp":1594907100.4308,"name":"utter_test intent","policy":"policy_0_MemoizationPolicy","confidence":1},{"event":"bot","timestamp":1594907100.4308,"text":"will not = won\"t","data":{"elements":None,"quick_replies":None,"buttons":None,"attachment":None,"image":None,"custom":None},"metadata":{}},{"event":"action","timestamp":1594907100.43384,"name":"action_listen","policy":"policy_0_MemoizationPolicy","confidence":1},{"event":"user","timestamp":1594907117.04194,"text":"can\"t","parse_data":{"intent":{"name":"test intent","confidence":0.253578245639801},"entities":[],"intent_ranking":[{"name":"test intent","confidence":0.253578245639801},{"name":"goodbye","confidence":0.1504897326231},{"name":"greet","confidence":0.138640150427818},{"name":"affirm","confidence":0.0857767835259438},{"name":"smalltalk_human","confidence":0.0721133947372437},{"name":"deny","confidence":0.069614589214325},{"name":"bot_challenge","confidence":0.0664894133806229},{"name":"faq_vaccine","confidence":0.062177762389183},{"name":"faq_testing","confidence":0.0530692934989929},{"name":"out_of_scope","confidence":0.0480506233870983}],"response_selector":{"default":{"response":{"name":None,"confidence":0},"ranking":[],"full_retrieval_intent":None}},"text":"can\"t"},"input_channel":None,"message_id":"e96e2a85de0748798748385503c65fb3","metadata":{}},{"event":"action","timestamp":1594907117.04547,"name":"utter_test intent","policy":"policy_1_TEDPolicy","confidence":0.978452920913696},{"event":"bot","timestamp":1594907117.04548,"text":"can not = can't","data":{"elements":None,"quick_replies":None,"buttons":None,"attachment":None,"image":None,"custom":None},"metadata":{}}],
                "latest_input_channel": "rest",
                "active_loop": {},
                "latest_action": {},
            },
            "domain": {
                "config": {},
                "session_config": {},
                "intents": [],
                "entities": [],
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e"},
                "responses": {},
                "actions": [],
                "forms": {},
                "e2e_actions": []
            },
            "version": "version"
        }
        mock_action.side_effect = _get_action
        mock_action_config.side_effect = _get_action_config
        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response.code, 200)
        self.assertEqual(len(response_json['events']), 1)
        self.assertEqual(len(response_json['responses']), 1)
        self.assertEqual(response_json['events'], [
            {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
             'value': "Email Triggered"}])
        self.assertEqual(response_json['responses'][0]['text'],
                         "Email Triggered")
        logs = ActionServerLogs.objects(type=ActionType.email_action.value).order_by("-id").first()
        assert logs.status == "SUCCESS"

        name, args, kwargs = mock_smtp.method_calls.pop(0)
        assert name == '().connect'
        assert {} == kwargs

        host, port = args
        assert host == action_config.smtp_url
        assert port == action_config.smtp_port
        name, args, kwargs = mock_smtp.method_calls.pop(0)
        assert name == '().login'
        assert {} == kwargs

        from_email, password = args
        assert from_email == action_config.from_email
        assert password == action_config.smtp_password.value

        name, args, kwargs = mock_smtp.method_calls.pop(0)
        assert name == '().sendmail'
        assert {} == kwargs

        assert args[0] == action_config.from_email
        assert args[1] == ["test@test.com"]
        assert str(args[2]).__contains__(action_config.subject)
        assert str(args[2]).__contains__("Content-Type: text/html")
        assert str(args[2]).__contains__("Subject: default test")

    @patch("kairon.shared.actions.utils.ActionUtility.get_action")
    @patch("kairon.actions.definitions.email.ActionEmail.retrieve_config")
    @patch("kairon.shared.utils.SMTP", autospec=True)
    def test_email_action_execution_varied_utterances(self, mock_smtp, mock_action_config, mock_action):
        Utility.email_conf['email']['templates']['conversation'] = open('template/emails/conversation.html',
                                                                        'rb').read().decode()
        Utility.email_conf['email']['templates']['bot_msg_conversation'] = open(
            'template/emails/bot_msg_conversation.html', 'rb').read().decode()
        Utility.email_conf['email']['templates']['user_msg_conversation'] = open(
            'template/emails/user_msg_conversation.html', 'rb').read().decode()
        Utility.email_conf['email']['templates']['button_template'] = open('template/emails/button.html',
                                                                           'rb').read().decode()

        action_name = "test_email_action_execution_varied_utterances"
        action = Actions(name=action_name, type=ActionType.email_action.value, bot="bot", user="user")
        action_config = EmailActionConfig(
            action_name=action_name,
            smtp_url="test.localhost",
            smtp_port=293,
            smtp_password=CustomActionRequestParameters(key='smtp_password', value="test"),
            from_email="test@demo.com",
            subject="test",
            to_email=["test@test.com"],
            response="Email Triggered",
            bot="bot",
            user="user"
        )

        def _get_action(*arge, **kwargs):
            return action.to_mongo().to_dict()

        def _get_action_config(*arge, **kwargs):
            return action_config.to_mongo().to_dict()

        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e"},
                "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]},
                "latest_event_time": 1537645578.314389,
                "followup_action": "action_listen",
                "paused": False,
                "events": [{'event': 'session_started', 'timestamp': 1664983829.6084516},
                           {'event': 'action', 'timestamp': 1664983829.608483, 'name': 'action_listen', 'policy': None,
                            'confidence': None, 'action_text': None, 'hide_rule_turn': False},
                           {'event': 'user', 'timestamp': 1664983829.919788, 'text': 'link', 'parse_data': {
                               'intent': {'id': 2015045187461877599, 'name': 'link', 'confidence': 0.9997459053993225},
                               'entities': [], 'text': 'link', 'message_id': '76f5c53fc6ff4692a61550f598986ab1',
                               'metadata': {}, 'intent_ranking': [
                                   {'id': 2015045187461877599, 'name': 'link', 'confidence': 0.9997459053993225},
                                   {'id': -8857672120535800139, 'name': 'mail', 'confidence': 0.00020965914882253855},
                                   {'id': -7823499171713963943, 'name': 'video', 'confidence': 4.25996768171899e-05},
                                   {'id': 8484017656191423660, 'name': 'image', 'confidence': 1.9194467313354835e-06}],
                               'response_selector': {'all_retrieval_intents': [], 'default': {
                                   'response': {'id': None, 'responses': None, 'response_templates': None,
                                                'confidence': 0.0, 'intent_response_key': None,
                                                'utter_action': 'utter_None', 'template_name': 'utter_None'},
                                   'ranking': []}}}, 'input_channel': None,
                            'message_id': '76f5c53fc6ff4692a61550f598986ab1', 'metadata': {}},
                           {'event': 'user_featurization', 'timestamp': 1664983830.0568683,
                            'use_text_for_featurization': False},
                           {'event': 'action', 'timestamp': 1664983830.0568924, 'name': 'utter_link',
                            'policy': 'policy_0_MemoizationPolicy', 'confidence': 1.0, 'action_text': None,
                            'hide_rule_turn': False},
                           {'event': 'bot', 'timestamp': 1664983830.0570993, 'metadata': {'utter_action': 'utter_link'},
                            'text': None,
                            'data': {'elements': None, 'quick_replies': None, 'buttons': None, 'attachment': None,
                                     'image': None, 'custom': {'data': [{'type': 'paragraph', 'children': [{'text': ''},
                                                                                                           {
                                                                                                               'type': 'link',
                                                                                                               'href': 'https://github.com/jthomperoo/custom-pod-autoscaler',
                                                                                                               'children': [
                                                                                                                   {
                                                                                                                       'text': 'github link here'}]},
                                                                                                           {
                                                                                                               'text': ''}]},
                                                                        {'type': 'paragraph',
                                                                         'children': [{'text': ''}]}],
                                                               'type': 'link'}}},
                           {'event': 'action', 'timestamp': 1664983830.194102, 'name': 'action_listen',
                            'policy': 'policy_0_MemoizationPolicy', 'confidence': 1.0, 'action_text': None,
                            'hide_rule_turn': False},
                           {'event': 'user', 'timestamp': 1664983834.2071092, 'text': 'video', 'parse_data': {
                               'intent': {'id': -7823499171713963943, 'name': 'video',
                                          'confidence': 0.9999388456344604}, 'entities': [], 'text': 'video',
                               'message_id': '7b9d81e5b5fd4680863db2ad5b893ede', 'metadata': {}, 'intent_ranking': [
                                   {'id': -7823499171713963943, 'name': 'video', 'confidence': 0.9999388456344604},
                                   {'id': -8857672120535800139, 'name': 'mail', 'confidence': 3.681053567561321e-05},
                                   {'id': 8484017656191423660, 'name': 'image', 'confidence': 1.4123366781859659e-05},
                                   {'id': 2015045187461877599, 'name': 'link', 'confidence': 1.0227864549960941e-05}],
                               'response_selector': {'all_retrieval_intents': [], 'default': {
                                   'response': {'id': None, 'responses': None, 'response_templates': None,
                                                'confidence': 0.0, 'intent_response_key': None,
                                                'utter_action': 'utter_None', 'template_name': 'utter_None'},
                                   'ranking': []}}}, 'input_channel': None,
                            'message_id': '7b9d81e5b5fd4680863db2ad5b893ede', 'metadata': {}},
                           {'event': 'user_featurization', 'timestamp': 1664983834.3527381,
                            'use_text_for_featurization': False},
                           {'event': 'action', 'timestamp': 1664983834.3527615, 'name': 'utter_video',
                            'policy': 'policy_1_TEDPolicy', 'confidence': 0.9765785336494446, 'action_text': None,
                            'hide_rule_turn': False},
                           {'event': 'bot', 'timestamp': 1664983834.353261, 'metadata': {'utter_action': 'utter_video'},
                            'text': None,
                            'data': {'elements': None, 'quick_replies': None, 'buttons': None, 'attachment': None,
                                     'image': None, 'custom': {'data': [
                                    {'type': 'video', 'url': 'https://www.youtube.com/watch?v=Ia-UEYYR44s',
                                     'children': [{'text': ''}]}, {'type': 'paragraph', 'children': [{'text': ''}]}],
                                                               'type': 'video'}}},
                           {'event': 'action', 'timestamp': 1664983834.4991908, 'name': 'action_listen',
                            'policy': 'policy_1_TEDPolicy', 'confidence': 0.9985560774803162, 'action_text': None,
                            'hide_rule_turn': False},
                           {'event': 'user', 'timestamp': 1664983839.4883664, 'text': 'image', 'parse_data': {
                               'intent': {'id': 8484017656191423660, 'name': 'image', 'confidence': 0.9999688863754272},
                               'entities': [], 'text': 'image', 'message_id': '792c767f39394f13997049325a662f23',
                               'metadata': {}, 'intent_ranking': [
                                   {'id': 8484017656191423660, 'name': 'image', 'confidence': 0.9999688863754272},
                                   {'id': -7823499171713963943, 'name': 'video', 'confidence': 1.817748670873698e-05},
                                   {'id': -8857672120535800139, 'name': 'mail', 'confidence': 9.322835467173718e-06},
                                   {'id': 2015045187461877599, 'name': 'link', 'confidence': 3.717372237588279e-06}],
                               'response_selector': {'all_retrieval_intents': [], 'default': {
                                   'response': {'id': None, 'responses': None, 'response_templates': None,
                                                'confidence': 0.0, 'intent_response_key': None,
                                                'utter_action': 'utter_None', 'template_name': 'utter_None'},
                                   'ranking': []}}}, 'input_channel': None,
                            'message_id': '792c767f39394f13997049325a662f23', 'metadata': {}},
                           {'event': 'user_featurization', 'timestamp': 1664983839.528499,
                            'use_text_for_featurization': False},
                           {'event': 'action', 'timestamp': 1664983839.528521, 'name': 'utter_image',
                            'policy': 'policy_1_TEDPolicy', 'confidence': 0.9796480536460876, 'action_text': None,
                            'hide_rule_turn': False},
                           {'event': 'bot', 'timestamp': 1664983839.528629, 'metadata': {'utter_action': 'utter_image'},
                            'text': None,
                            'data': {'elements': None, 'quick_replies': None, 'buttons': None, 'attachment': None,
                                     'image': None, 'custom': {'data': [{'type': 'image', 'alt': 'this is kairon logo',
                                                                         'src': 'https://kairon.digite.com/assets/logo/logo.svg',
                                                                         'children': [{'text': 'this is kairon logo'}]},
                                                                        {'type': 'paragraph',
                                                                         'children': [{'text': ''}]}],
                                                               'type': 'image'}}},
                           {'event': 'action', 'timestamp': 1664983839.568023, 'name': 'action_listen',
                            'policy': 'policy_1_TEDPolicy', 'confidence': 0.9992861747741699, 'action_text': None,
                            'hide_rule_turn': False}, {'event': 'user', 'timestamp': 1664983842.8999915, 'text': 'mail',
                                                       'parse_data': {
                                                           'intent': {'id': -8857672120535800139, 'name': 'mail',
                                                                      'confidence': 0.9999262094497681}, 'entities': [],
                                                           'text': 'mail',
                                                           'message_id': '1c9193ec5618426db598a45e99b3cf51',
                                                           'metadata': {}, 'intent_ranking': [
                                                               {'id': -8857672120535800139, 'name': 'mail',
                                                                'confidence': 0.9999262094497681},
                                                               {'id': 2015045187461877599, 'name': 'link',
                                                                'confidence': 4.6336426748894155e-05},
                                                               {'id': -7823499171713963943, 'name': 'video',
                                                                'confidence': 2.5573279344826005e-05},
                                                               {'id': 8484017656191423660, 'name': 'image',
                                                                'confidence': 1.90976220437733e-06}],
                                                           'response_selector': {'all_retrieval_intents': [],
                                                                                 'default': {'response': {'id': None,
                                                                                                          'responses': None,
                                                                                                          'response_templates': None,
                                                                                                          'confidence': 0.0,
                                                                                                          'intent_response_key': None,
                                                                                                          'utter_action': 'utter_None',
                                                                                                          'template_name': 'utter_None'},
                                                                                             'ranking': []}}},
                                                       'input_channel': None,
                                                       'message_id': '1c9193ec5618426db598a45e99b3cf51',
                                                       'metadata': {}},
                           {'event': 'user_featurization', 'timestamp': 1664983842.967956,
                            'use_text_for_featurization': False},
                           {'event': 'action', 'timestamp': 1664983842.9679885, 'name': 'action_send_mail',
                            'policy': 'policy_1_TEDPolicy', 'confidence': 0.9561721086502075, 'action_text': None,
                            'hide_rule_turn': False}, {'event': 'bot', 'timestamp': 1664983842.9684947,
                                                       'text': 'I have failed to process your request',
                                                       'data': {'elements': None, 'quick_replies': None,
                                                                'buttons': None, 'attachment': None, 'image': None,
                                                                'custom': None}, 'metadata': {}},
                           {'event': 'slot', 'timestamp': 1664983842.9685051, 'name': 'kairon_action_response',
                            'value': 'I have failed to process your request'},
                           {'event': 'action', 'timestamp': 1664983843.0098503, 'name': 'action_listen',
                            'policy': 'policy_1_TEDPolicy', 'confidence': 0.9988918900489807, 'action_text': None,
                            'hide_rule_turn': False}, {'event': 'user', 'timestamp': 1664983980.0313635,
                                                       'metadata': {'is_integration_user': False,
                                                                    'bot': '633d9d427588dc6a4c1c4814', 'account': 32,
                                                                    'channel_type': 'chat_client'}, 'text': 'mail',
                                                       'parse_data': {
                                                           'intent': {'id': 809451388526489255, 'name': 'mail',
                                                                      'confidence': 0.9999262094497681}, 'entities': [],
                                                           'text': 'mail',
                                                           'message_id': '1056f87debd7412e8baa0f2fa121fc2a',
                                                           'metadata': {'is_integration_user': False,
                                                                        'bot': '633d9d427588dc6a4c1c4814',
                                                                        'account': 32, 'channel_type': 'chat_client'},
                                                           'intent_ranking': [{'id': 809451388526489255, 'name': 'mail',
                                                                               'confidence': 0.9999262094497681},
                                                                              {'id': -503604357833754988,
                                                                               'name': 'link',
                                                                               'confidence': 4.6336426748894155e-05},
                                                                              {'id': 5064283358982355594,
                                                                               'name': 'video',
                                                                               'confidence': 2.5573279344826005e-05},
                                                                              {'id': 3971486216002913969,
                                                                               'name': 'image',
                                                                               'confidence': 1.9097640233667335e-06}],
                                                           'response_selector': {'all_retrieval_intents': [],
                                                                                 'default': {'response': {'id': None,
                                                                                                          'responses': None,
                                                                                                          'response_templates': None,
                                                                                                          'confidence': 0.0,
                                                                                                          'intent_response_key': None,
                                                                                                          'utter_action': 'utter_None',
                                                                                                          'template_name': 'utter_None'},
                                                                                             'ranking': []}}},
                                                       'input_channel': None,
                                                       'message_id': '1056f87debd7412e8baa0f2fa121fc2a'},
                           {'event': 'user_featurization', 'timestamp': 1664984231.9888864,
                            'use_text_for_featurization': False},
                           {'event': 'action', 'timestamp': 1664984231.9890008, 'name': 'action_send_mail',
                            'policy': 'policy_1_TEDPolicy', 'confidence': 0.9616490006446838, 'action_text': None,
                            'hide_rule_turn': False},
                           {'event': 'action', 'timestamp': 1664984232.2413206, 'name': 'action_listen',
                            'policy': 'policy_1_TEDPolicy', 'confidence': 0.9986591339111328, 'action_text': None,
                            'hide_rule_turn': False}, {'event': 'user', 'timestamp': 1664984278.933671,
                                                       'metadata': {'is_integration_user': False,
                                                                    'bot': '633d9d427588dc6a4c1c4814', 'account': 32,
                                                                    'channel_type': 'chat_client'}, 'text': 'mail',
                                                       'parse_data': {
                                                           'intent': {'id': 809451388526489255, 'name': 'mail',
                                                                      'confidence': 0.9999262094497681}, 'entities': [],
                                                           'text': 'mail',
                                                           'message_id': '10a21aa9f02046bdb8c5e786c618ef3e',
                                                           'metadata': {'is_integration_user': False,
                                                                        'bot': '633d9d427588dc6a4c1c4814',
                                                                        'account': 32, 'channel_type': 'chat_client'},
                                                           'intent_ranking': [{'id': 809451388526489255, 'name': 'mail',
                                                                               'confidence': 0.9999262094497681},
                                                                              {'id': -503604357833754988,
                                                                               'name': 'link',
                                                                               'confidence': 4.6336426748894155e-05},
                                                                              {'id': 5064283358982355594,
                                                                               'name': 'video',
                                                                               'confidence': 2.5573279344826005e-05},
                                                                              {'id': 3971486216002913969,
                                                                               'name': 'image',
                                                                               'confidence': 1.9097640233667335e-06}],
                                                           'response_selector': {'all_retrieval_intents': [],
                                                                                 'default': {'response': {'id': None,
                                                                                                          'responses': None,
                                                                                                          'response_templates': None,
                                                                                                          'confidence': 0.0,
                                                                                                          'intent_response_key': None,
                                                                                                          'utter_action': 'utter_None',
                                                                                                          'template_name': 'utter_None'},
                                                                                             'ranking': []}}},
                                                       'input_channel': None,
                                                       'message_id': '10a21aa9f02046bdb8c5e786c618ef3e'},
                           {'event': 'user_featurization', 'timestamp': 1664984454.4048393,
                            'use_text_for_featurization': False},
                           {'event': 'action', 'timestamp': 1664984454.4049177, 'name': 'action_send_mail',
                            'policy': 'policy_1_TEDPolicy', 'confidence': 0.9651614427566528, 'action_text': None,
                            'hide_rule_turn': False},
                           {'event': 'action', 'timestamp': 1664984454.5234702, 'name': 'action_listen',
                            'policy': 'policy_1_TEDPolicy', 'confidence': 0.9986193776130676, 'action_text': None,
                            'hide_rule_turn': False}, {'event': 'user', 'timestamp': 1664984491.3683157,
                                                       'metadata': {'is_integration_user': False,
                                                                    'bot': '633d9d427588dc6a4c1c4814', 'account': 32,
                                                                    'channel_type': 'chat_client'}, 'text': 'mail',
                                                       'parse_data': {
                                                           'intent': {'id': 809451388526489255, 'name': 'mail',
                                                                      'confidence': 0.9999262094497681}, 'entities': [],
                                                           'text': 'mail',
                                                           'message_id': 'a0c5fc7182a24de8bacf550bb5e1a06c',
                                                           'metadata': {'is_integration_user': False,
                                                                        'bot': '633d9d427588dc6a4c1c4814',
                                                                        'account': 32, 'channel_type': 'chat_client'},
                                                           'intent_ranking': [{'id': 809451388526489255, 'name': 'mail',
                                                                               'confidence': 0.9999262094497681},
                                                                              {'id': -503604357833754988,
                                                                               'name': 'link',
                                                                               'confidence': 4.6336426748894155e-05},
                                                                              {'id': 5064283358982355594,
                                                                               'name': 'video',
                                                                               'confidence': 2.5573279344826005e-05},
                                                                              {'id': 3971486216002913969,
                                                                               'name': 'image',
                                                                               'confidence': 1.9097640233667335e-06}],
                                                           'response_selector': {'all_retrieval_intents': [],
                                                                                 'default': {'response': {'id': None,
                                                                                                          'responses': None,
                                                                                                          'response_templates': None,
                                                                                                          'confidence': 0.0,
                                                                                                          'intent_response_key': None,
                                                                                                          'utter_action': 'utter_None',
                                                                                                          'template_name': 'utter_None'},
                                                                                             'ranking': []}}},
                                                       'input_channel': None,
                                                       'message_id': 'a0c5fc7182a24de8bacf550bb5e1a06c'},
                           {'event': 'user_featurization', 'timestamp': 1664984491.4822395,
                            'use_text_for_featurization': False}],
                "latest_input_channel": "rest",
                "active_loop": {},
                "latest_action": {},
            },
            "domain": {
                "config": {},
                "session_config": {},
                "intents": [],
                "entities": [],
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e"},
                "responses": {},
                "actions": [],
                "forms": {},
                "e2e_actions": []
            },
            "version": "version"
        }
        mock_action.side_effect = _get_action
        mock_action_config.side_effect = _get_action_config
        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response.code, 200)
        self.assertEqual(len(response_json['events']), 1)
        self.assertEqual(len(response_json['responses']), 1)
        self.assertEqual(response_json['events'], [
            {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
             'value': "Email Triggered"}])
        self.assertEqual(response_json['responses'][0]['text'],
                         "Email Triggered")
        logs = ActionServerLogs.objects(type=ActionType.email_action.value).order_by("-id").first()
        assert logs.status == "SUCCESS"

        name, args, kwargs = mock_smtp.method_calls.pop(0)
        assert name == '().connect'
        assert {} == kwargs

        host, port = args
        assert host == action_config.smtp_url
        assert port == action_config.smtp_port
        name, args, kwargs = mock_smtp.method_calls.pop(0)
        assert name == '().login'
        assert {} == kwargs

        from_email, password = args
        assert from_email == action_config.from_email
        assert password == action_config.smtp_password.value

        name, args, kwargs = mock_smtp.method_calls.pop(0)
        assert name == '().sendmail'
        assert {} == kwargs

        assert args[0] == action_config.from_email
        assert args[1] == ["test@test.com"]
        assert str(args[2]).__contains__(action_config.subject)
        assert str(args[2]).__contains__("Content-Type: text/html")
        assert str(args[2]).__contains__("Subject: default test")

        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e"},
                "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]},
                "latest_event_time": 1537645578.314389,
                "followup_action": "action_listen",
                "paused": False,
                "events": [{'event': 'session_started', 'timestamp': 1664983829.6084516},
                           {'event': 'action', 'timestamp': 1664983829.608483, 'name': 'action_listen', 'policy': None,
                            'confidence': None, 'action_text': None, 'hide_rule_turn': False},
                           {'event': 'user', 'timestamp': 1664983829.919788, 'text': 'link', 'parse_data': {
                               'intent': {'id': 2015045187461877599, 'name': 'link', 'confidence': 0.9997459053993225},
                               'entities': [], 'text': 'link', 'message_id': '76f5c53fc6ff4692a61550f598986ab1',
                               'metadata': {}, 'intent_ranking': [
                                   {'id': 2015045187461877599, 'name': 'link', 'confidence': 0.9997459053993225},
                                   {'id': -8857672120535800139, 'name': 'mail', 'confidence': 0.00020965914882253855},
                                   {'id': -7823499171713963943, 'name': 'video', 'confidence': 4.25996768171899e-05},
                                   {'id': 8484017656191423660, 'name': 'image', 'confidence': 1.9194467313354835e-06}],
                               'response_selector': {'all_retrieval_intents': [], 'default': {
                                   'response': {'id': None, 'responses': None, 'response_templates': None,
                                                'confidence': 0.0, 'intent_response_key': None,
                                                'utter_action': 'utter_None', 'template_name': 'utter_None'},
                                   'ranking': []}}}, 'input_channel': None,
                            'message_id': '76f5c53fc6ff4692a61550f598986ab1', 'metadata': {}},
                           {'event': 'user_featurization', 'timestamp': 1664983830.0568683,
                            'use_text_for_featurization': False},
                           {'event': 'action', 'timestamp': 1664983830.0568924, 'name': 'utter_link',
                            'policy': 'policy_0_MemoizationPolicy', 'confidence': 1.0, 'action_text': None,
                            'hide_rule_turn': False},
                           {'event': 'bot', 'timestamp': 1664983830.0570993, 'metadata': {'utter_action': 'utter_link'},
                            'text': None,
                            'data': {'elements': None, 'quick_replies': None, 'buttons': None, 'attachment': None,
                                     'image': None, 'custom': {"type": "custom", "text": "hello"}}},
                           {'event': 'action', 'timestamp': 1664983829.608483, 'name': 'action_listen', 'policy': None,
                            'confidence': None, 'action_text': None, 'hide_rule_turn': False},
                           {'event': 'user', 'timestamp': 1664983829.919788, 'text': 'link', 'parse_data': {
                               'intent': {'id': 2015045187461877599, 'name': 'link', 'confidence': 0.9997459053993225},
                               'entities': [], 'text': 'link', 'message_id': '76f5c53fc6ff4692a61550f598986ab1',
                               'metadata': {}, 'intent_ranking': [
                                   {'id': 2015045187461877599, 'name': 'link', 'confidence': 0.9997459053993225},
                                   {'id': -8857672120535800139, 'name': 'mail', 'confidence': 0.00020965914882253855},
                                   {'id': -7823499171713963943, 'name': 'video', 'confidence': 4.25996768171899e-05},
                                   {'id': 8484017656191423660, 'name': 'image', 'confidence': 1.9194467313354835e-06}],
                               'response_selector': {'all_retrieval_intents': [], 'default': {
                                   'response': {'id': None, 'responses': None, 'response_templates': None,
                                                'confidence': 0.0, 'intent_response_key': None,
                                                'utter_action': 'utter_None', 'template_name': 'utter_None'},
                                   'ranking': []}}}, 'input_channel': None,
                            'message_id': '76f5c53fc6ff4692a61550f598986ab1', 'metadata': {}},
                           {'event': 'user_featurization', 'timestamp': 1664983830.0568683,
                            'use_text_for_featurization': False},
                           {'event': 'action', 'timestamp': 1664983830.0568924, 'name': 'utter_link',
                            'policy': 'policy_0_MemoizationPolicy', 'confidence': 1.0, 'action_text': None,
                            'hide_rule_turn': False},
                           {'event': 'bot', 'timestamp': 1664983830.0570993, 'metadata': {'utter_action': 'utter_link'},
                            'text': None,
                            'data': {'elements': None, 'quick_replies': None, 'buttons': [
                                {"text": "hi", "payload": "hi"}, {"text": "bye", "payload": "/goodbye"}], 'attachment': None,
                                     'image': None, 'custom': None}},
                           {'event': 'action', 'timestamp': 1664983830.194102, 'name': 'action_listen',
                            'policy': 'policy_0_MemoizationPolicy', 'confidence': 1.0, 'action_text': None,
                            'hide_rule_turn': False}
                           ],
                "latest_input_channel": "rest",
                "active_loop": {},
                "latest_action": {},
            },
            "domain": {
                "config": {},
                "session_config": {},
                "intents": [],
                "entities": [],
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e"},
                "responses": {},
                "actions": [],
                "forms": {},
                "e2e_actions": []
            },
            "version": "version"
        }
        mock_action.side_effect = _get_action
        mock_action_config.side_effect = _get_action_config
        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response.code, 200)
        self.assertEqual(len(response_json['events']), 1)
        self.assertEqual(len(response_json['responses']), 1)
        self.assertEqual(response_json['events'], [
            {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
             'value': "Email Triggered"}])
        self.assertEqual(response_json['responses'][0]['text'],
                         "Email Triggered")
        logs = ActionServerLogs.objects(type=ActionType.email_action.value).order_by("-id").first()
        assert logs.status == "SUCCESS"

    @patch("kairon.shared.actions.utils.ActionUtility.get_action")
    @patch("kairon.actions.definitions.email.ActionEmail.retrieve_config")
    def test_email_action_failed_execution(self, mock_action_config, mock_action):
        action_name = "test_run_email_action"
        action = Actions(name=action_name, type=ActionType.email_action.value, bot="bot", user="user")
        action_config = EmailActionConfig(
            action_name=action_name,
            smtp_url="test.localhost",
            smtp_port=293,
            smtp_password=CustomActionRequestParameters(value="test"),
            from_email="test@demo.com",
            subject="test",
            to_email="test@test.com",
            response="Email Triggered",
            bot="bot",
            user="user"
        )

        def _get_action(*arge, **kwargs):
            return action.to_mongo().to_dict()

        def _get_action_config(*arge, **kwargs):
            return action_config.to_mongo().to_dict()

        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e", "to_email": "test@test.com"},
                "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]},
                "latest_event_time": 1537645578.314389,
                "followup_action": "action_listen",
                "paused": False,
                "events": [
                    {"event": "action", "timestamp": 1594907100.12764, "name": "action_session_start", "policy": None,
                     "confidence": None}, {"event": "session_started", "timestamp": 1594907100.12765},
                    {"event": "action", "timestamp": 1594907100.12767, "name": "action_listen", "policy": None,
                     "confidence": None}, {"event": "user", "timestamp": 1594907100.42744, "text": "can't",
                                           "parse_data": {
                                               "intent": {"name": "test intent", "confidence": 0.253578245639801},
                                               "entities": [], "intent_ranking": [
                                                   {"name": "test intent", "confidence": 0.253578245639801},
                                                   {"name": "goodbye", "confidence": 0.1504897326231},
                                                   {"name": "greet", "confidence": 0.138640150427818},
                                                   {"name": "affirm", "confidence": 0.0857767835259438},
                                                   {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                   {"name": "deny", "confidence": 0.069614589214325},
                                                   {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                   {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                   {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                   {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                               "response_selector": {
                                                   "default": {"response": {"name": None, "confidence": 0},
                                                               "ranking": [], "full_retrieval_intent": None}},
                                               "text": "can't"}, "input_channel": None,
                                           "message_id": "bbd413bf5c834bf3b98e0da2373553b2", "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.4308, "name": "utter_test intent",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "bot", "timestamp": 1594907100.4308, "text": "will not = won\"t",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.43384, "name": "action_listen",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "user", "timestamp": 1594907117.04194, "text": "can\"t",
                     "parse_data": {"intent": {"name": "test intent", "confidence": 0.253578245639801}, "entities": [],
                                    "intent_ranking": [{"name": "test intent", "confidence": 0.253578245639801},
                                                       {"name": "goodbye", "confidence": 0.1504897326231},
                                                       {"name": "greet", "confidence": 0.138640150427818},
                                                       {"name": "affirm", "confidence": 0.0857767835259438},
                                                       {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                       {"name": "deny", "confidence": 0.069614589214325},
                                                       {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                       {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                       {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                       {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                    "response_selector": {
                                        "default": {"response": {"name": None, "confidence": 0}, "ranking": [],
                                                    "full_retrieval_intent": None}}, "text": "can\"t"},
                     "input_channel": None, "message_id": "e96e2a85de0748798748385503c65fb3", "metadata": {}},
                    {"event": "action", "timestamp": 1594907117.04547, "name": "utter_test intent",
                     "policy": "policy_1_TEDPolicy", "confidence": 0.978452920913696},
                    {"event": "bot", "timestamp": 1594907117.04548, "text": "can not = can't",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}}],
                "latest_input_channel": "rest",
                "active_loop": {},
                "latest_action": {},
            },
            "domain": {
                "config": {},
                "session_config": {},
                "intents": [],
                "entities": [],
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e"},
                "responses": {},
                "actions": [],
                "forms": {},
                "e2e_actions": []
            },
            "version": "version"
        }
        mock_action.side_effect = _get_action
        mock_action_config.side_effect = _get_action_config
        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response.code, 200)
        self.assertEqual(len(response_json['events']), 1)
        self.assertEqual(len(response_json['responses']), 1)
        self.assertEqual(response_json['events'], [
            {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
             'value': "I have failed to process your request"}])
        self.assertEqual(response_json['responses'][0]['text'],
                         "I have failed to process your request")
        logs = ActionServerLogs.objects(type=ActionType.email_action.value).order_by("-id").first()
        assert logs.status == "FAILURE"

    def test_email_action_execution_action_not_exist(self):
        action_name = "test_run_email_action"

        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e", "to_email": "test@test.com"},
                "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]},
                "latest_event_time": 1537645578.314389,
                "followup_action": "action_listen",
                "paused": False,
                "events": [{"event":"action","timestamp":1594907100.12764,"name":"action_session_start","policy":None,"confidence":None},{"event":"session_started","timestamp":1594907100.12765},{"event":"action","timestamp":1594907100.12767,"name":"action_listen","policy":None,"confidence":None},{"event":"user","timestamp":1594907100.42744,"text":"can't","parse_data":{"intent":{"name":"test intent","confidence":0.253578245639801},"entities":[],"intent_ranking":[{"name":"test intent","confidence":0.253578245639801},{"name":"goodbye","confidence":0.1504897326231},{"name":"greet","confidence":0.138640150427818},{"name":"affirm","confidence":0.0857767835259438},{"name":"smalltalk_human","confidence":0.0721133947372437},{"name":"deny","confidence":0.069614589214325},{"name":"bot_challenge","confidence":0.0664894133806229},{"name":"faq_vaccine","confidence":0.062177762389183},{"name":"faq_testing","confidence":0.0530692934989929},{"name":"out_of_scope","confidence":0.0480506233870983}],"response_selector":{"default":{"response":{"name":None,"confidence":0},"ranking":[],"full_retrieval_intent":None}},"text":"can't"},"input_channel":None,"message_id":"bbd413bf5c834bf3b98e0da2373553b2","metadata":{}},{"event":"action","timestamp":1594907100.4308,"name":"utter_test intent","policy":"policy_0_MemoizationPolicy","confidence":1},{"event":"bot","timestamp":1594907100.4308,"text":"will not = won\"t","data":{"elements":None,"quick_replies":None,"buttons":None,"attachment":None,"image":None,"custom":None},"metadata":{}},{"event":"action","timestamp":1594907100.43384,"name":"action_listen","policy":"policy_0_MemoizationPolicy","confidence":1},{"event":"user","timestamp":1594907117.04194,"text":"can\"t","parse_data":{"intent":{"name":"test intent","confidence":0.253578245639801},"entities":[],"intent_ranking":[{"name":"test intent","confidence":0.253578245639801},{"name":"goodbye","confidence":0.1504897326231},{"name":"greet","confidence":0.138640150427818},{"name":"affirm","confidence":0.0857767835259438},{"name":"smalltalk_human","confidence":0.0721133947372437},{"name":"deny","confidence":0.069614589214325},{"name":"bot_challenge","confidence":0.0664894133806229},{"name":"faq_vaccine","confidence":0.062177762389183},{"name":"faq_testing","confidence":0.0530692934989929},{"name":"out_of_scope","confidence":0.0480506233870983}],"response_selector":{"default":{"response":{"name":None,"confidence":0},"ranking":[],"full_retrieval_intent":None}},"text":"can\"t"},"input_channel":None,"message_id":"e96e2a85de0748798748385503c65fb3","metadata":{}},{"event":"action","timestamp":1594907117.04547,"name":"utter_test intent","policy":"policy_1_TEDPolicy","confidence":0.978452920913696},{"event":"bot","timestamp":1594907117.04548,"text":"can not = can't","data":{"elements":None,"quick_replies":None,"buttons":None,"attachment":None,"image":None,"custom":None},"metadata":{}}],
                "latest_input_channel": "rest",
                "active_loop": {},
                "latest_action": {},
            },
            "domain": {
                "config": {},
                "session_config": {},
                "intents": [],
                "entities": [],
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e"},
                "responses": {},
                "actions": [],
                "forms": {},
                "e2e_actions": []
            },
            "version": "version"
        }
        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        response_json = json.loads(response.body.decode("utf8"))
        print(response_json)
        self.assertEqual(response.code, 200)
        self.assertEqual(len(response_json['events']), 0)
        self.assertEqual(len(response_json['responses']), 0)

    def test_google_search_action_not_found(self):
        action_name = "google_search_action"
        bot = "5f50fd0a56b698ca10d35d2e"
        Actions(name=action_name, type=ActionType.google_search_action.value, bot=bot, user='test_user').save()

        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {"bot": bot, "to_email": "test@test.com"},
                "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]},
                "latest_event_time": 1537645578.314389,
                "followup_action": "action_listen",
                "paused": False,
                "events": [
                    {"event": "action", "timestamp": 1594907100.12764, "name": "action_session_start", "policy": None,
                     "confidence": None}, {"event": "session_started", "timestamp": 1594907100.12765},
                    {"event": "action", "timestamp": 1594907100.12767, "name": "action_listen", "policy": None,
                     "confidence": None}, {"event": "user", "timestamp": 1594907100.42744, "text": "can't",
                                           "parse_data": {
                                               "intent": {"name": "test intent", "confidence": 0.253578245639801},
                                               "entities": [], "intent_ranking": [
                                                   {"name": "test intent", "confidence": 0.253578245639801},
                                                   {"name": "goodbye", "confidence": 0.1504897326231},
                                                   {"name": "greet", "confidence": 0.138640150427818},
                                                   {"name": "affirm", "confidence": 0.0857767835259438},
                                                   {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                   {"name": "deny", "confidence": 0.069614589214325},
                                                   {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                   {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                   {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                   {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                               "response_selector": {
                                                   "default": {"response": {"name": None, "confidence": 0},
                                                               "ranking": [], "full_retrieval_intent": None}},
                                               "text": "can't"}, "input_channel": None,
                                           "message_id": "bbd413bf5c834bf3b98e0da2373553b2", "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.4308, "name": "utter_test intent",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "bot", "timestamp": 1594907100.4308, "text": "will not = won\"t",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.43384, "name": "action_listen",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "user", "timestamp": 1594907117.04194, "text": "can\"t",
                     "parse_data": {"intent": {"name": "test intent", "confidence": 0.253578245639801}, "entities": [],
                                    "intent_ranking": [{"name": "test intent", "confidence": 0.253578245639801},
                                                       {"name": "goodbye", "confidence": 0.1504897326231},
                                                       {"name": "greet", "confidence": 0.138640150427818},
                                                       {"name": "affirm", "confidence": 0.0857767835259438},
                                                       {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                       {"name": "deny", "confidence": 0.069614589214325},
                                                       {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                       {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                       {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                       {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                    "response_selector": {
                                        "default": {"response": {"name": None, "confidence": 0}, "ranking": [],
                                                    "full_retrieval_intent": None}}, "text": "can\"t"},
                     "input_channel": None, "message_id": "e96e2a85de0748798748385503c65fb3", "metadata": {}},
                    {"event": "action", "timestamp": 1594907117.04547, "name": "utter_test intent",
                     "policy": "policy_1_TEDPolicy", "confidence": 0.978452920913696},
                    {"event": "bot", "timestamp": 1594907117.04548, "text": "can not = can't",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}}],
                "latest_input_channel": "rest",
                "active_loop": {},
                "latest_action": {},
            },
            "domain": {
                "config": {},
                "session_config": {},
                "intents": [],
                "entities": [],
                "slots": {"bot": bot},
                "responses": {},
                "actions": [],
                "forms": {},
                "e2e_actions": []
            },
            "version": "version"
        }
        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(len(response_json['events']), 0)
        self.assertEqual(len(response_json['responses']), 0)

    def test_process_google_search_action(self):
        action_name = "custom_search_action"
        bot = "5f50fd0a56b698ca10d35d2e"
        user = 'test_user'
        Actions(name=action_name, type=ActionType.google_search_action.value, bot=bot, user='test_user').save()
        GoogleSearchAction(name=action_name, api_key=CustomActionRequestParameters(value='1234567890'),
                           search_engine_id='asdfg::123456', bot=bot, user=user).save()

        def _run_action(*args, **kwargs):
            return [{
                'title': 'Kanban',
                'text': 'Kanban visualizes both the process (the workflow) and the actual work passing through that process.',
                'link': "https://www.digite.com/kanban/what-is-kanban/"
            }]

        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {"bot": bot, "to_email": "test@test.com"},
                "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]},
                "latest_event_time": 1537645578.314389,
                "followup_action": "action_listen",
                "paused": False,
                "events": [
                    {"event": "action", "timestamp": 1594907100.12764, "name": "action_session_start", "policy": None,
                     "confidence": None}, {"event": "session_started", "timestamp": 1594907100.12765},
                    {"event": "action", "timestamp": 1594907100.12767, "name": "action_listen", "policy": None,
                     "confidence": None}, {"event": "user", "timestamp": 1594907100.42744, "text": "can't",
                                           "parse_data": {
                                               "intent": {"name": "test intent", "confidence": 0.253578245639801},
                                               "entities": [], "intent_ranking": [
                                                   {"name": "test intent", "confidence": 0.253578245639801},
                                                   {"name": "goodbye", "confidence": 0.1504897326231},
                                                   {"name": "greet", "confidence": 0.138640150427818},
                                                   {"name": "affirm", "confidence": 0.0857767835259438},
                                                   {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                   {"name": "deny", "confidence": 0.069614589214325},
                                                   {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                   {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                   {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                   {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                               "response_selector": {
                                                   "default": {"response": {"name": None, "confidence": 0},
                                                               "ranking": [], "full_retrieval_intent": None}},
                                               "text": "can't"}, "input_channel": None,
                                           "message_id": "bbd413bf5c834bf3b98e0da2373553b2", "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.4308, "name": "utter_test intent",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "bot", "timestamp": 1594907100.4308, "text": "will not = won\"t",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.43384, "name": "action_listen",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "user", "timestamp": 1594907117.04194, "text": "can\"t",
                     "parse_data": {"intent": {"name": "test intent", "confidence": 0.253578245639801}, "entities": [],
                                    "intent_ranking": [{"name": "test intent", "confidence": 0.253578245639801},
                                                       {"name": "goodbye", "confidence": 0.1504897326231},
                                                       {"name": "greet", "confidence": 0.138640150427818},
                                                       {"name": "affirm", "confidence": 0.0857767835259438},
                                                       {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                       {"name": "deny", "confidence": 0.069614589214325},
                                                       {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                       {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                       {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                       {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                    "response_selector": {
                                        "default": {"response": {"name": None, "confidence": 0}, "ranking": [],
                                                    "full_retrieval_intent": None}}, "text": "can\"t"},
                     "input_channel": None, "message_id": "e96e2a85de0748798748385503c65fb3", "metadata": {}},
                    {"event": "action", "timestamp": 1594907117.04547, "name": "utter_test intent",
                     "policy": "policy_1_TEDPolicy", "confidence": 0.978452920913696},
                    {"event": "bot", "timestamp": 1594907117.04548, "text": "can not = can't",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}}],
                "latest_input_channel": "rest",
                "active_loop": {},
                "latest_action": {},
            },
            "domain": {
                "config": {},
                "session_config": {},
                "intents": [],
                "entities": [],
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e"},
                "responses": {},
                "actions": [],
                "forms": {},
                "e2e_actions": []
            },
            "version": "version"
        }
        with patch.object(ActionUtility, "perform_google_search") as mocked:
            mocked.side_effect = _run_action
            response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
            response_json = json.loads(response.body.decode("utf8"))
            self.assertEqual(response.code, 200)
            self.assertEqual(response_json, {'events': [{
                'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
                 'value': 'Kanban visualizes both the process (the workflow) and the actual work passing through that process.\nTo know more, please visit: <a href = "https://www.digite.com/kanban/what-is-kanban/" target="_blank" >Kanban</a>'
                 }],
                'responses': [{
                    'text': 'Kanban visualizes both the process (the workflow) and the actual work passing through that process.\nTo know more, please visit: <a href = "https://www.digite.com/kanban/what-is-kanban/" target="_blank" >Kanban</a>',
                    'buttons': [], 'elements': [], 'custom': {}, 'template': None, 'response': None, 'image': None, 'attachment': None
                }]})

        def _run_action(*args, **kwargs):
            assert args == ('1234567890', 'asdfg::123456', 'my custom text')
            assert kwargs == {'num': 1}
            return [{
                'title': 'Kanban',
                'text': 'Kanban visualizes both the process (the workflow) and the actual work passing through that process.',
                'link': "https://www.digite.com/kanban/what-is-kanban/"
            }]

        request_object["tracker"]["latest_message"] = {
            'text': f'/action_google_search{{"{KAIRON_USER_MSG_ENTITY}": "my custom text"}}',
            'intent_ranking': [{'name': 'test_run'}], "entities": [{"value": "my custom text", "entity": KAIRON_USER_MSG_ENTITY}]
        }
        with patch.object(ActionUtility, "perform_google_search") as mocked:
            mocked.side_effect = _run_action
            response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
            response_json = json.loads(response.body.decode("utf8"))
            self.assertEqual(response.code, 200)
            self.assertEqual(response_json, {'events': [{
                'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
                 'value': 'Kanban visualizes both the process (the workflow) and the actual work passing through that process.\nTo know more, please visit: <a href = "https://www.digite.com/kanban/what-is-kanban/" target="_blank" >Kanban</a>'
                 }],
                'responses': [{
                    'text': 'Kanban visualizes both the process (the workflow) and the actual work passing through that process.\nTo know more, please visit: <a href = "https://www.digite.com/kanban/what-is-kanban/" target="_blank" >Kanban</a>',
                    'buttons': [], 'elements': [], 'custom': {}, 'template': None, 'response': None, 'image': None, 'attachment': None
                }]})

        def _run_action(*args, **kwargs):
            assert args == ('1234567890', 'asdfg::123456', '/action_google_search')
            assert kwargs == {'num': 1}
            return [{
                'title': 'Kanban',
                'text': 'Kanban visualizes both the process (the workflow) and the actual work passing through that process.',
                'link': "https://www.digite.com/kanban/what-is-kanban/"
            }]

        request_object["tracker"]["latest_message"] = {
            'text': '/action_google_search', 'intent_ranking': [{'name': 'test_run'}]
        }
        with patch.object(ActionUtility, "perform_google_search") as mocked:
            mocked.side_effect = _run_action
            response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
            response_json = json.loads(response.body.decode("utf8"))
            self.assertEqual(response.code, 200)
            self.assertEqual(response_json, {'events': [{
                'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
                 'value': 'Kanban visualizes both the process (the workflow) and the actual work passing through that process.\nTo know more, please visit: <a href = "https://www.digite.com/kanban/what-is-kanban/" target="_blank" >Kanban</a>'
                 }],
                'responses': [{
                    'text': 'Kanban visualizes both the process (the workflow) and the actual work passing through that process.\nTo know more, please visit: <a href = "https://www.digite.com/kanban/what-is-kanban/" target="_blank" >Kanban</a>',
                    'buttons': [], 'elements': [], 'custom': {}, 'template': None, 'response': None, 'image': None, 'attachment': None
                }]})

    def test_process_google_search_action_failure(self):
        action_name = "custom_search_failure"
        bot = "5f50fd0a56b698ca10d35d2e"
        user = 'test_user'
        Actions(name=action_name, type=ActionType.google_search_action.value, bot=bot, user='test_user').save()
        GoogleSearchAction(name=action_name, api_key=CustomActionRequestParameters(value='1234567890'),
                           search_engine_id='asdfg::123456', bot=bot, user=user).save()

        def _run_action(*args, **kwargs):
            raise Exception('Connection error')

        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {"bot": bot, "to_email": "test@test.com"},
                "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]},
                "latest_event_time": 1537645578.314389,
                "followup_action": "action_listen",
                "paused": False,
                "events": [
                    {"event": "action", "timestamp": 1594907100.12764, "name": "action_session_start", "policy": None,
                     "confidence": None}, {"event": "session_started", "timestamp": 1594907100.12765},
                    {"event": "action", "timestamp": 1594907100.12767, "name": "action_listen", "policy": None,
                     "confidence": None}, {"event": "user", "timestamp": 1594907100.42744, "text": "can't",
                                           "parse_data": {
                                               "intent": {"name": "test intent", "confidence": 0.253578245639801},
                                               "entities": [], "intent_ranking": [
                                                   {"name": "test intent", "confidence": 0.253578245639801},
                                                   {"name": "goodbye", "confidence": 0.1504897326231},
                                                   {"name": "greet", "confidence": 0.138640150427818},
                                                   {"name": "affirm", "confidence": 0.0857767835259438},
                                                   {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                   {"name": "deny", "confidence": 0.069614589214325},
                                                   {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                   {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                   {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                   {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                               "response_selector": {
                                                   "default": {"response": {"name": None, "confidence": 0},
                                                               "ranking": [], "full_retrieval_intent": None}},
                                               "text": "can't"}, "input_channel": None,
                                           "message_id": "bbd413bf5c834bf3b98e0da2373553b2", "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.4308, "name": "utter_test intent",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "bot", "timestamp": 1594907100.4308, "text": "will not = won\"t",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.43384, "name": "action_listen",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "user", "timestamp": 1594907117.04194, "text": "can\"t",
                     "parse_data": {"intent": {"name": "test intent", "confidence": 0.253578245639801}, "entities": [],
                                    "intent_ranking": [{"name": "test intent", "confidence": 0.253578245639801},
                                                       {"name": "goodbye", "confidence": 0.1504897326231},
                                                       {"name": "greet", "confidence": 0.138640150427818},
                                                       {"name": "affirm", "confidence": 0.0857767835259438},
                                                       {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                       {"name": "deny", "confidence": 0.069614589214325},
                                                       {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                       {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                       {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                       {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                    "response_selector": {
                                        "default": {"response": {"name": None, "confidence": 0}, "ranking": [],
                                                    "full_retrieval_intent": None}}, "text": "can\"t"},
                     "input_channel": None, "message_id": "e96e2a85de0748798748385503c65fb3", "metadata": {}},
                    {"event": "action", "timestamp": 1594907117.04547, "name": "utter_test intent",
                     "policy": "policy_1_TEDPolicy", "confidence": 0.978452920913696},
                    {"event": "bot", "timestamp": 1594907117.04548, "text": "can not = can't",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}}],
                "latest_input_channel": "rest",
                "active_loop": {},
                "latest_action": {},
            },
            "domain": {
                "config": {},
                "session_config": {},
                "intents": [],
                "entities": [],
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e"},
                "responses": {},
                "actions": [],
                "forms": {},
                "e2e_actions": []
            },
            "version": "version"
        }
        with patch.object(ActionUtility, "perform_google_search") as mocked:
            mocked.side_effect = _run_action
            response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
            response_json = json.loads(response.body.decode("utf8"))
            self.assertEqual(response.code, 200)
            self.assertEqual(response_json, {'events': [{'event': 'slot', 'timestamp': None,
                                                         'name': 'kairon_action_response',
                                                         'value': 'I have failed to process your request.'}],
                                             'responses': [{'text': 'I have failed to process your request.',
                                                            'buttons': [], 'elements': [], 'custom': {}, 'template': None,
                                                            'response': None, 'image': None, 'attachment': None}]})

    def test_process_google_search_action_no_results(self):
        action_name = "custom_search_action_no_results"
        bot = "5f50fd0a56b698ca10d35d2e"
        user = 'test_user'
        Actions(name=action_name, type=ActionType.google_search_action.value, bot=bot, user='test_user').save()
        GoogleSearchAction(name=action_name, api_key=CustomActionRequestParameters(value='1234567890'),
                           search_engine_id='asdfg::123456', bot=bot, user=user).save()

        def _run_action(*args, **kwargs):
            return []

        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {"bot": bot, "to_email": "test@test.com"},
                "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]},
                "latest_event_time": 1537645578.314389,
                "followup_action": "action_listen",
                "paused": False,
                "events": [
                    {"event": "action", "timestamp": 1594907100.12764, "name": "action_session_start", "policy": None,
                     "confidence": None}, {"event": "session_started", "timestamp": 1594907100.12765},
                    {"event": "action", "timestamp": 1594907100.12767, "name": "action_listen", "policy": None,
                     "confidence": None}, {"event": "user", "timestamp": 1594907100.42744, "text": "can't",
                                           "parse_data": {
                                               "intent": {"name": "test intent", "confidence": 0.253578245639801},
                                               "entities": [], "intent_ranking": [
                                                   {"name": "test intent", "confidence": 0.253578245639801},
                                                   {"name": "goodbye", "confidence": 0.1504897326231},
                                                   {"name": "greet", "confidence": 0.138640150427818},
                                                   {"name": "affirm", "confidence": 0.0857767835259438},
                                                   {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                   {"name": "deny", "confidence": 0.069614589214325},
                                                   {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                   {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                   {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                   {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                               "response_selector": {
                                                   "default": {"response": {"name": None, "confidence": 0},
                                                               "ranking": [], "full_retrieval_intent": None}},
                                               "text": "can't"}, "input_channel": None,
                                           "message_id": "bbd413bf5c834bf3b98e0da2373553b2", "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.4308, "name": "utter_test intent",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "bot", "timestamp": 1594907100.4308, "text": "will not = won\"t",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.43384, "name": "action_listen",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "user", "timestamp": 1594907117.04194, "text": "can\"t",
                     "parse_data": {"intent": {"name": "test intent", "confidence": 0.253578245639801}, "entities": [],
                                    "intent_ranking": [{"name": "test intent", "confidence": 0.253578245639801},
                                                       {"name": "goodbye", "confidence": 0.1504897326231},
                                                       {"name": "greet", "confidence": 0.138640150427818},
                                                       {"name": "affirm", "confidence": 0.0857767835259438},
                                                       {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                       {"name": "deny", "confidence": 0.069614589214325},
                                                       {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                       {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                       {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                       {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                    "response_selector": {
                                        "default": {"response": {"name": None, "confidence": 0}, "ranking": [],
                                                    "full_retrieval_intent": None}}, "text": "can\"t"},
                     "input_channel": None, "message_id": "e96e2a85de0748798748385503c65fb3", "metadata": {}},
                    {"event": "action", "timestamp": 1594907117.04547, "name": "utter_test intent",
                     "policy": "policy_1_TEDPolicy", "confidence": 0.978452920913696},
                    {"event": "bot", "timestamp": 1594907117.04548, "text": "can not = can't",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}}],
                "latest_input_channel": "rest",
                "active_loop": {},
                "latest_action": {},
            },
            "domain": {
                "config": {},
                "session_config": {},
                "intents": [],
                "entities": [],
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e"},
                "responses": {},
                "actions": [],
                "forms": {},
                "e2e_actions": []
            },
            "version": "version"
        }
        with patch.object(ActionUtility, "perform_google_search") as mocked:
            mocked.side_effect = _run_action
            response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
            response_json = json.loads(response.body.decode("utf8"))
            self.assertEqual(response_json, {'events': [{'event': 'slot', 'timestamp': None,
                                                         'name': 'kairon_action_response', 'value': 'I have failed to process your request.'}],
                                             'responses': [{'text': 'I have failed to process your request.', 'buttons': [], 'elements': [],
                                                            'custom': {}, 'template': None, 'response': None,
                                                            'image': None, 'attachment': None}]})

    def test_process_jira_action(self):
        action_name = "jira_action"
        bot = "5f50fd0a56b698ca10d35d2e"
        user = 'test_user'

        def _mock_response(*args, **kwargs):
            return None

        with patch('kairon.shared.actions.data_objects.JiraAction.validate', new=_mock_response):
            Actions(name=action_name, type=ActionType.jira_action.value, bot=bot, user=user).save()
            JiraAction(
                name=action_name, bot=bot, user=user, url='https://test-digite.atlassian.net',
                user_name='test@digite.com',
                api_token=CustomActionRequestParameters(key="api_token", value='ASDFGHJKL'), project_key='HEL', issue_type='Bug', summary='fallback',
                response='Successfully created').save()

        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {"bot": bot, "to_email": "test@test.com"},
                "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]},
                "latest_event_time": 1537645578.314389,
                "followup_action": "action_listen",
                "paused": False,
                "events": [
                    {"event": "action", "timestamp": 1594907100.12764, "name": "action_session_start", "policy": None,
                     "confidence": None}, {"event": "session_started", "timestamp": 1594907100.12765},
                    {"event": "action", "timestamp": 1594907100.12767, "name": "action_listen", "policy": None,
                     "confidence": None}, {"event": "user", "timestamp": 1594907100.42744, "text": "can't",
                                           "parse_data": {
                                               "intent": {"name": "test intent", "confidence": 0.253578245639801},
                                               "entities": [], "intent_ranking": [
                                                   {"name": "test intent", "confidence": 0.253578245639801},
                                                   {"name": "goodbye", "confidence": 0.1504897326231},
                                                   {"name": "greet", "confidence": 0.138640150427818},
                                                   {"name": "affirm", "confidence": 0.0857767835259438},
                                                   {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                   {"name": "deny", "confidence": 0.069614589214325},
                                                   {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                   {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                   {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                   {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                               "response_selector": {
                                                   "default": {"response": {"name": None, "confidence": 0},
                                                               "ranking": [], "full_retrieval_intent": None}},
                                               "text": "can't"}, "input_channel": None,
                                           "message_id": "bbd413bf5c834bf3b98e0da2373553b2", "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.4308, "name": "utter_test intent",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "bot", "timestamp": 1594907100.4308, "text": "will not = won\"t",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.43384, "name": "action_listen",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "user", "timestamp": 1594907117.04194, "text": "can\"t",
                     "parse_data": {"intent": {"name": "test intent", "confidence": 0.253578245639801}, "entities": [],
                                    "intent_ranking": [{"name": "test intent", "confidence": 0.253578245639801},
                                                       {"name": "goodbye", "confidence": 0.1504897326231},
                                                       {"name": "greet", "confidence": 0.138640150427818},
                                                       {"name": "affirm", "confidence": 0.0857767835259438},
                                                       {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                       {"name": "deny", "confidence": 0.069614589214325},
                                                       {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                       {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                       {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                       {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                    "response_selector": {
                                        "default": {"response": {"name": None, "confidence": 0}, "ranking": [],
                                                    "full_retrieval_intent": None}}, "text": "can\"t"},
                     "input_channel": None, "message_id": "e96e2a85de0748798748385503c65fb3", "metadata": {}},
                    {"event": "action", "timestamp": 1594907117.04547, "name": "utter_test intent",
                     "policy": "policy_1_TEDPolicy", "confidence": 0.978452920913696},
                    {"event": "bot", "timestamp": 1594907117.04548, "text": "can not = can't",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}}],
                "latest_input_channel": "rest",
                "active_loop": {},
                "latest_action": {},
            },
            "domain": {
                "config": {},
                "session_config": {},
                "intents": [],
                "entities": [],
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e"},
                "responses": {},
                "actions": [],
                "forms": {},
                "e2e_actions": []
            },
            "version": "version"
        }
        with patch.object(ActionUtility, "create_jira_issue") as mocked:
            mocked.side_effect = _mock_response
            response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
            response_json = json.loads(response.body.decode("utf8"))
            self.assertEqual(response_json, {'events': [
                {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
                 'value': 'Successfully created'}], 'responses': [
                {'text': 'Successfully created', 'buttons': [], 'elements': [], 'custom': {}, 'template': None,
                 'response': None, 'image': None, 'attachment': None}]})

    def test_process_jira_action_failure(self):
        action_name = "jira_action_failure"
        bot = "5f50fd0a56b698ca10d35d2e"
        user = 'test_user'

        def _mock_validation(*args, **kwargs):
            return None

        def _mock_response(*args, **kwargs):
            raise JIRAError(status_code=404, url='https://test-digite.atlassian.net')

        with patch('kairon.shared.actions.data_objects.JiraAction.validate', new=_mock_validation):
            Actions(name=action_name, type=ActionType.jira_action.value, bot=bot, user='test_user').save()
            JiraAction(
                name=action_name, bot=bot, user=user, url='https://test-digite.atlassian.net',
                user_name='test@digite.com',
                api_token=CustomActionRequestParameters(value='ASDFGHJKL'), project_key='HEL', issue_type='Bug', summary='fallback',
                response='Successfully created').save()

        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {"bot": bot, "to_email": "test@test.com"},
                "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]},
                "latest_event_time": 1537645578.314389,
                "followup_action": "action_listen",
                "paused": False,
                "events": [
                    {"event": "action", "timestamp": 1594907100.12764, "name": "action_session_start", "policy": None,
                     "confidence": None}, {"event": "session_started", "timestamp": 1594907100.12765},
                    {"event": "action", "timestamp": 1594907100.12767, "name": "action_listen", "policy": None,
                     "confidence": None}, {"event": "user", "timestamp": 1594907100.42744, "text": "can't",
                                           "parse_data": {
                                               "intent": {"name": "test intent", "confidence": 0.253578245639801},
                                               "entities": [], "intent_ranking": [
                                                   {"name": "test intent", "confidence": 0.253578245639801},
                                                   {"name": "goodbye", "confidence": 0.1504897326231},
                                                   {"name": "greet", "confidence": 0.138640150427818},
                                                   {"name": "affirm", "confidence": 0.0857767835259438},
                                                   {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                   {"name": "deny", "confidence": 0.069614589214325},
                                                   {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                   {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                   {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                   {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                               "response_selector": {
                                                   "default": {"response": {"name": None, "confidence": 0},
                                                               "ranking": [], "full_retrieval_intent": None}},
                                               "text": "can't"}, "input_channel": None,
                                           "message_id": "bbd413bf5c834bf3b98e0da2373553b2", "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.4308, "name": "utter_test intent",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "bot", "timestamp": 1594907100.4308, "text": "will not = won\"t",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.43384, "name": "action_listen",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "user", "timestamp": 1594907117.04194, "text": "can\"t",
                     "parse_data": {"intent": {"name": "test intent", "confidence": 0.253578245639801}, "entities": [],
                                    "intent_ranking": [{"name": "test intent", "confidence": 0.253578245639801},
                                                       {"name": "goodbye", "confidence": 0.1504897326231},
                                                       {"name": "greet", "confidence": 0.138640150427818},
                                                       {"name": "affirm", "confidence": 0.0857767835259438},
                                                       {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                       {"name": "deny", "confidence": 0.069614589214325},
                                                       {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                       {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                       {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                       {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                    "response_selector": {
                                        "default": {"response": {"name": None, "confidence": 0}, "ranking": [],
                                                    "full_retrieval_intent": None}}, "text": "can\"t"},
                     "input_channel": None, "message_id": "e96e2a85de0748798748385503c65fb3", "metadata": {}},
                    {"event": "action", "timestamp": 1594907117.04547, "name": "utter_test intent",
                     "policy": "policy_1_TEDPolicy", "confidence": 0.978452920913696},
                    {"event": "bot", "timestamp": 1594907117.04548, "text": "can not = can't",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}}],
                "latest_input_channel": "rest",
                "active_loop": {},
                "latest_action": {},
            },
            "domain": {
                "config": {},
                "session_config": {},
                "intents": [],
                "entities": [],
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e"},
                "responses": {},
                "actions": [],
                "forms": {},
                "e2e_actions": []
            },
            "version": "version"
        }
        with patch.object(ActionUtility, "create_jira_issue") as mocked:
            mocked.side_effect = _mock_response
            response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
            response_json = json.loads(response.body.decode("utf8"))
            self.assertEqual(response_json, {'events': [
                {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
                 'value': 'I have failed to create issue for you'}], 'responses': [
                {'text': 'I have failed to create issue for you', 'buttons': [], 'elements': [], 'custom': {}, 'template': None,
                 'response': None, 'image': None, 'attachment': None}]})

    def test_jira_action_not_found(self):
        action_name = "test_jira_action_not_found"
        bot = "5f50fd0a56b698ca10d35d2e"

        Actions(name=action_name, type=ActionType.jira_action.value, bot=bot, user='test_user').save()

        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {"bot": bot, "to_email": "test@test.com"},
                "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]},
                "latest_event_time": 1537645578.314389,
                "followup_action": "action_listen",
                "paused": False,
                "events": [
                    {"event": "action", "timestamp": 1594907100.12764, "name": "action_session_start", "policy": None,
                     "confidence": None}, {"event": "session_started", "timestamp": 1594907100.12765},
                    {"event": "action", "timestamp": 1594907100.12767, "name": "action_listen", "policy": None,
                     "confidence": None}, {"event": "user", "timestamp": 1594907100.42744, "text": "can't",
                                           "parse_data": {
                                               "intent": {"name": "test intent", "confidence": 0.253578245639801},
                                               "entities": [], "intent_ranking": [
                                                   {"name": "test intent", "confidence": 0.253578245639801},
                                                   {"name": "goodbye", "confidence": 0.1504897326231},
                                                   {"name": "greet", "confidence": 0.138640150427818},
                                                   {"name": "affirm", "confidence": 0.0857767835259438},
                                                   {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                   {"name": "deny", "confidence": 0.069614589214325},
                                                   {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                   {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                   {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                   {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                               "response_selector": {
                                                   "default": {"response": {"name": None, "confidence": 0},
                                                               "ranking": [], "full_retrieval_intent": None}},
                                               "text": "can't"}, "input_channel": None,
                                           "message_id": "bbd413bf5c834bf3b98e0da2373553b2", "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.4308, "name": "utter_test intent",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "bot", "timestamp": 1594907100.4308, "text": "will not = won\"t",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.43384, "name": "action_listen",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "user", "timestamp": 1594907117.04194, "text": "can\"t",
                     "parse_data": {"intent": {"name": "test intent", "confidence": 0.253578245639801}, "entities": [],
                                    "intent_ranking": [{"name": "test intent", "confidence": 0.253578245639801},
                                                       {"name": "goodbye", "confidence": 0.1504897326231},
                                                       {"name": "greet", "confidence": 0.138640150427818},
                                                       {"name": "affirm", "confidence": 0.0857767835259438},
                                                       {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                       {"name": "deny", "confidence": 0.069614589214325},
                                                       {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                       {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                       {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                       {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                    "response_selector": {
                                        "default": {"response": {"name": None, "confidence": 0}, "ranking": [],
                                                    "full_retrieval_intent": None}}, "text": "can\"t"},
                     "input_channel": None, "message_id": "e96e2a85de0748798748385503c65fb3", "metadata": {}},
                    {"event": "action", "timestamp": 1594907117.04547, "name": "utter_test intent",
                     "policy": "policy_1_TEDPolicy", "confidence": 0.978452920913696},
                    {"event": "bot", "timestamp": 1594907117.04548, "text": "can not = can't",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}}],
                "latest_input_channel": "rest",
                "active_loop": {},
                "latest_action": {},
            },
            "domain": {
                "config": {},
                "session_config": {},
                "intents": [],
                "entities": [],
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e"},
                "responses": {},
                "actions": [],
                "forms": {},
                "e2e_actions": []
            },
            "version": "version"
        }
        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response_json, {'events': [], 'responses': []})

    def test_process_zendesk_action_not_exists(self):
        action_name = "test_process_zendesk_action_not_exists"
        bot = "5f50fd0a56b698ca10d35d2e"

        Actions(name=action_name, type=ActionType.zendesk_action.value, bot=bot, user='test_user').save()

        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {"bot": bot, "to_email": "test@test.com"},
                "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]},
                "latest_event_time": 1537645578.314389,
                "followup_action": "action_listen",
                "paused": False,
                "events": [
                    {"event": "action", "timestamp": 1594907100.12764, "name": "action_session_start", "policy": None,
                     "confidence": None}, {"event": "session_started", "timestamp": 1594907100.12765},
                    {"event": "action", "timestamp": 1594907100.12767, "name": "action_listen", "policy": None,
                     "confidence": None}, {"event": "user", "timestamp": 1594907100.42744, "text": "can't",
                                           "parse_data": {
                                               "intent": {"name": "test intent", "confidence": 0.253578245639801},
                                               "entities": [], "intent_ranking": [
                                                   {"name": "test intent", "confidence": 0.253578245639801},
                                                   {"name": "goodbye", "confidence": 0.1504897326231},
                                                   {"name": "greet", "confidence": 0.138640150427818},
                                                   {"name": "affirm", "confidence": 0.0857767835259438},
                                                   {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                   {"name": "deny", "confidence": 0.069614589214325},
                                                   {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                   {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                   {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                   {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                               "response_selector": {
                                                   "default": {"response": {"name": None, "confidence": 0},
                                                               "ranking": [], "full_retrieval_intent": None}},
                                               "text": "can't"}, "input_channel": None,
                                           "message_id": "bbd413bf5c834bf3b98e0da2373553b2", "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.4308, "name": "utter_test intent",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "bot", "timestamp": 1594907100.4308, "text": "will not = won\"t",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.43384, "name": "action_listen",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "user", "timestamp": 1594907117.04194, "text": "can\"t",
                     "parse_data": {"intent": {"name": "test intent", "confidence": 0.253578245639801}, "entities": [],
                                    "intent_ranking": [{"name": "test intent", "confidence": 0.253578245639801},
                                                       {"name": "goodbye", "confidence": 0.1504897326231},
                                                       {"name": "greet", "confidence": 0.138640150427818},
                                                       {"name": "affirm", "confidence": 0.0857767835259438},
                                                       {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                       {"name": "deny", "confidence": 0.069614589214325},
                                                       {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                       {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                       {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                       {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                    "response_selector": {
                                        "default": {"response": {"name": None, "confidence": 0}, "ranking": [],
                                                    "full_retrieval_intent": None}}, "text": "can\"t"},
                     "input_channel": None, "message_id": "e96e2a85de0748798748385503c65fb3", "metadata": {}},
                    {"event": "action", "timestamp": 1594907117.04547, "name": "utter_test intent",
                     "policy": "policy_1_TEDPolicy", "confidence": 0.978452920913696},
                    {"event": "bot", "timestamp": 1594907117.04548, "text": "can not = can't",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}}],
                "latest_input_channel": "rest",
                "active_loop": {},
                "latest_action": {},
            },
            "domain": {
                "config": {},
                "session_config": {},
                "intents": [],
                "entities": [],
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e"},
                "responses": {},
                "actions": [],
                "forms": {},
                "e2e_actions": []
            },
            "version": "version"
        }
        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response_json, {'events': [], 'responses': []})

    def test_process_zendesk_action(self):
        action_name = "zendesk_action"
        bot = "5f50fd0a56b698ca10d35d2e"
        user = 'test_user'

        Actions(name=action_name, type=ActionType.zendesk_action.value, bot=bot, user='test_user').save()
        with patch('zenpy.Zenpy'):
            ZendeskAction(name=action_name, subdomain='digite751', user_name='udit.pandey@digite.com',
                          api_token=CustomActionRequestParameters(value='1234567890'), subject='new ticket', response='ticket created',
                          bot=bot, user=user).save()

        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {"bot": bot, "to_email": "test@test.com"},
                "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]},
                "latest_event_time": 1537645578.314389,
                "followup_action": "action_listen",
                "paused": False,
                "events": [
                    {"event": "action", "timestamp": 1594907100.12764, "name": "action_session_start", "policy": None,
                     "confidence": None}, {"event": "session_started", "timestamp": 1594907100.12765},
                    {"event": "action", "timestamp": 1594907100.12767, "name": "action_listen", "policy": None,
                     "confidence": None}, {"event": "user", "timestamp": 1594907100.42744, "text": "can't",
                                           "parse_data": {
                                               "intent": {"name": "test intent", "confidence": 0.253578245639801},
                                               "entities": [], "intent_ranking": [
                                                   {"name": "test intent", "confidence": 0.253578245639801},
                                                   {"name": "goodbye", "confidence": 0.1504897326231},
                                                   {"name": "greet", "confidence": 0.138640150427818},
                                                   {"name": "affirm", "confidence": 0.0857767835259438},
                                                   {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                   {"name": "deny", "confidence": 0.069614589214325},
                                                   {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                   {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                   {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                   {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                               "response_selector": {
                                                   "default": {"response": {"name": None, "confidence": 0},
                                                               "ranking": [], "full_retrieval_intent": None}},
                                               "text": "can't"}, "input_channel": None,
                                           "message_id": "bbd413bf5c834bf3b98e0da2373553b2", "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.4308, "name": "utter_test intent",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "bot", "timestamp": 1594907100.4308, "text": "will not = won\"t",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.43384, "name": "action_listen",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "user", "timestamp": 1594907117.04194, "text": "can\"t",
                     "parse_data": {"intent": {"name": "test intent", "confidence": 0.253578245639801}, "entities": [],
                                    "intent_ranking": [{"name": "test intent", "confidence": 0.253578245639801},
                                                       {"name": "goodbye", "confidence": 0.1504897326231},
                                                       {"name": "greet", "confidence": 0.138640150427818},
                                                       {"name": "affirm", "confidence": 0.0857767835259438},
                                                       {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                       {"name": "deny", "confidence": 0.069614589214325},
                                                       {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                       {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                       {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                       {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                    "response_selector": {
                                        "default": {"response": {"name": None, "confidence": 0}, "ranking": [],
                                                    "full_retrieval_intent": None}}, "text": "can\"t"},
                     "input_channel": None, "message_id": "e96e2a85de0748798748385503c65fb3", "metadata": {}},
                    {"event": "action", "timestamp": 1594907117.04547, "name": "utter_test intent",
                     "policy": "policy_1_TEDPolicy", "confidence": 0.978452920913696},
                    {"event": "bot", "timestamp": 1594907117.04548, "text": "can not = can't",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}}],
                "latest_input_channel": "rest",
                "active_loop": {},
                "latest_action": {},
            },
            "domain": {
                "config": {},
                "session_config": {},
                "intents": [],
                "entities": [],
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e"},
                "responses": {},
                "actions": [],
                "forms": {},
                "e2e_actions": []
            },
            "version": "version"
        }

        with patch('zenpy.Zenpy'):
            response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
            response_json = json.loads(response.body.decode("utf8"))
            self.assertEqual(response_json, {'events': [
                {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
                 'value': 'ticket created'}], 'responses': [
                {'text': 'ticket created', 'buttons': [], 'elements': [], 'custom': {},
                 'template': None,
                 'response': None, 'image': None, 'attachment': None}]})

    def test_process_zendesk_action_failure(self):
        action_name = "test_process_zendesk_action_failure"
        bot = "5f50fd0a56b698ca10d35d2e"
        user = 'test_user'

        Actions(name=action_name, type=ActionType.zendesk_action.value, bot=bot, user='test_user').save()
        with patch('zenpy.Zenpy'):
            ZendeskAction(name=action_name, subdomain='digite751', user_name='udit.pandey@digite.com',
                          api_token=CustomActionRequestParameters(value='1234567890'), subject='new ticket', response='ticket created',
                          bot=bot, user=user).save()

        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {"bot": bot, "to_email": "test@test.com"},
                "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]},
                "latest_event_time": 1537645578.314389,
                "followup_action": "action_listen",
                "paused": False,
                "events": [
                    {"event": "action", "timestamp": 1594907100.12764, "name": "action_session_start", "policy": None,
                     "confidence": None}, {"event": "session_started", "timestamp": 1594907100.12765},
                    {"event": "action", "timestamp": 1594907100.12767, "name": "action_listen", "policy": None,
                     "confidence": None}, {"event": "user", "timestamp": 1594907100.42744, "text": "can't",
                                           "parse_data": {
                                               "intent": {"name": "test intent", "confidence": 0.253578245639801},
                                               "entities": [], "intent_ranking": [
                                                   {"name": "test intent", "confidence": 0.253578245639801},
                                                   {"name": "goodbye", "confidence": 0.1504897326231},
                                                   {"name": "greet", "confidence": 0.138640150427818},
                                                   {"name": "affirm", "confidence": 0.0857767835259438},
                                                   {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                   {"name": "deny", "confidence": 0.069614589214325},
                                                   {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                   {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                   {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                   {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                               "response_selector": {
                                                   "default": {"response": {"name": None, "confidence": 0},
                                                               "ranking": [], "full_retrieval_intent": None}},
                                               "text": "can't"}, "input_channel": None,
                                           "message_id": "bbd413bf5c834bf3b98e0da2373553b2", "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.4308, "name": "utter_test intent",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "bot", "timestamp": 1594907100.4308, "text": "will not = won\"t",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.43384, "name": "action_listen",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "user", "timestamp": 1594907117.04194, "text": "can\"t",
                     "parse_data": {"intent": {"name": "test intent", "confidence": 0.253578245639801}, "entities": [],
                                    "intent_ranking": [{"name": "test intent", "confidence": 0.253578245639801},
                                                       {"name": "goodbye", "confidence": 0.1504897326231},
                                                       {"name": "greet", "confidence": 0.138640150427818},
                                                       {"name": "affirm", "confidence": 0.0857767835259438},
                                                       {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                       {"name": "deny", "confidence": 0.069614589214325},
                                                       {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                       {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                       {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                       {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                    "response_selector": {
                                        "default": {"response": {"name": None, "confidence": 0}, "ranking": [],
                                                    "full_retrieval_intent": None}}, "text": "can\"t"},
                     "input_channel": None, "message_id": "e96e2a85de0748798748385503c65fb3", "metadata": {}},
                    {"event": "action", "timestamp": 1594907117.04547, "name": "utter_test intent",
                     "policy": "policy_1_TEDPolicy", "confidence": 0.978452920913696},
                    {"event": "bot", "timestamp": 1594907117.04548, "text": "can not = can't",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}}],
                "latest_input_channel": "rest",
                "active_loop": {},
                "latest_action": {},
            },
            "domain": {
                "config": {},
                "session_config": {},
                "intents": [],
                "entities": [],
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e"},
                "responses": {},
                "actions": [],
                "forms": {},
                "e2e_actions": []
            },
            "version": "version"
        }

        def __mock_zendesk_error(*args, **kwargs):
            from zenpy.lib.exception import APIException
            raise APIException({"error": {"title": "No help desk at digite751.zendesk.com"}})

        with patch('zenpy.Zenpy') as mock:
            mock.side_effect = __mock_zendesk_error
            response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
            response_json = json.loads(response.body.decode("utf8"))
            self.assertEqual(response_json, {'events': [
                {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
                 'value': 'I have failed to create issue for you'}], 'responses': [
                {'text': 'I have failed to create issue for you', 'buttons': [], 'elements': [], 'custom': {},
                 'template': None,
                 'response': None, 'image': None, 'attachment': None}]})

    def test_process_pipedrive_leads_action_not_exists(self):
        action_name = "test_process_pipedrive_leads_action_not_exists"
        bot = "5f50fd0a56b698ca10d35d2e"

        Actions(name=action_name, type=ActionType.pipedrive_leads_action.value, bot=bot, user='test_user').save()

        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {"bot": bot, "to_email": "test@test.com"},
                "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]},
                "latest_event_time": 1537645578.314389,
                "followup_action": "action_listen",
                "paused": False,
                "events": [
                    {"event": "action", "timestamp": 1594907100.12764, "name": "action_session_start", "policy": None,
                     "confidence": None}, {"event": "session_started", "timestamp": 1594907100.12765},
                    {"event": "action", "timestamp": 1594907100.12767, "name": "action_listen", "policy": None,
                     "confidence": None}, {"event": "user", "timestamp": 1594907100.42744, "text": "can't",
                                           "parse_data": {
                                               "intent": {"name": "test intent", "confidence": 0.253578245639801},
                                               "entities": [], "intent_ranking": [
                                                   {"name": "test intent", "confidence": 0.253578245639801},
                                                   {"name": "goodbye", "confidence": 0.1504897326231},
                                                   {"name": "greet", "confidence": 0.138640150427818},
                                                   {"name": "affirm", "confidence": 0.0857767835259438},
                                                   {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                   {"name": "deny", "confidence": 0.069614589214325},
                                                   {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                   {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                   {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                   {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                               "response_selector": {
                                                   "default": {"response": {"name": None, "confidence": 0},
                                                               "ranking": [], "full_retrieval_intent": None}},
                                               "text": "can't"}, "input_channel": None,
                                           "message_id": "bbd413bf5c834bf3b98e0da2373553b2", "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.4308, "name": "utter_test intent",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "bot", "timestamp": 1594907100.4308, "text": "will not = won\"t",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.43384, "name": "action_listen",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "user", "timestamp": 1594907117.04194, "text": "can\"t",
                     "parse_data": {"intent": {"name": "test intent", "confidence": 0.253578245639801}, "entities": [],
                                    "intent_ranking": [{"name": "test intent", "confidence": 0.253578245639801},
                                                       {"name": "goodbye", "confidence": 0.1504897326231},
                                                       {"name": "greet", "confidence": 0.138640150427818},
                                                       {"name": "affirm", "confidence": 0.0857767835259438},
                                                       {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                       {"name": "deny", "confidence": 0.069614589214325},
                                                       {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                       {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                       {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                       {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                    "response_selector": {
                                        "default": {"response": {"name": None, "confidence": 0}, "ranking": [],
                                                    "full_retrieval_intent": None}}, "text": "can\"t"},
                     "input_channel": None, "message_id": "e96e2a85de0748798748385503c65fb3", "metadata": {}},
                    {"event": "action", "timestamp": 1594907117.04547, "name": "utter_test intent",
                     "policy": "policy_1_TEDPolicy", "confidence": 0.978452920913696},
                    {"event": "bot", "timestamp": 1594907117.04548, "text": "can not = can't",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}}],
                "latest_input_channel": "rest",
                "active_loop": {},
                "latest_action": {},
            },
            "domain": {
                "config": {},
                "session_config": {},
                "intents": [],
                "entities": [],
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e"},
                "responses": {},
                "actions": [],
                "forms": {},
                "e2e_actions": []
            },
            "version": "version"
        }
        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response_json, {'events': [], 'responses': []})

    def test_process_pipedrive_leads_action(self):
        action_name = "pipedrive_leads_action"
        bot = "5f50fd0a56b698ca10d35d2e"
        user = 'test_user'

        Actions(name=action_name, type=ActionType.pipedrive_leads_action.value, bot=bot, user='test_user').save()
        with patch('pipedrive.client.Client'):
            metadata = {'name': 'name', 'org_name': 'organization', 'email': 'email', 'phone': 'phone'}
            PipedriveLeadsAction(name=action_name, domain='https://digite751.pipedrive.com/',
                                 api_token=CustomActionRequestParameters(value='1234567890'),
                                 title='new lead generated', response='lead created', metadata=metadata, bot=bot,
                                 user=user).save()

        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {'bot': bot, 'name': 'udit pandey', 'organization': 'digite', 'email': 'pandey.udit867@gmail.com', 'phone': '9876543210'},
                "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]},
                "latest_event_time": 1537645578.314389,
                "followup_action": "action_listen",
                "paused": False,
                "events": [
                    {"event": "action", "timestamp": 1594907100.12764, "name": "action_session_start", "policy": None,
                     "confidence": None}, {"event": "session_started", "timestamp": 1594907100.12765},
                    {"event": "action", "timestamp": 1594907100.12767, "name": "action_listen", "policy": None,
                     "confidence": None}, {"event": "user", "timestamp": 1594907100.42744, "text": "can't",
                                           "parse_data": {
                                               "intent": {"name": "test intent", "confidence": 0.253578245639801},
                                               "entities": [], "intent_ranking": [
                                                   {"name": "test intent", "confidence": 0.253578245639801},
                                                   {"name": "goodbye", "confidence": 0.1504897326231},
                                                   {"name": "greet", "confidence": 0.138640150427818},
                                                   {"name": "affirm", "confidence": 0.0857767835259438},
                                                   {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                   {"name": "deny", "confidence": 0.069614589214325},
                                                   {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                   {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                   {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                   {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                               "response_selector": {
                                                   "default": {"response": {"name": None, "confidence": 0},
                                                               "ranking": [], "full_retrieval_intent": None}},
                                               "text": "can't"}, "input_channel": None,
                                           "message_id": "bbd413bf5c834bf3b98e0da2373553b2", "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.4308, "name": "utter_test intent",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "bot", "timestamp": 1594907100.4308, "text": "will not = won\"t",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.43384, "name": "action_listen",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "user", "timestamp": 1594907117.04194, "text": "can\"t",
                     "parse_data": {"intent": {"name": "test intent", "confidence": 0.253578245639801}, "entities": [],
                                    "intent_ranking": [{"name": "test intent", "confidence": 0.253578245639801},
                                                       {"name": "goodbye", "confidence": 0.1504897326231},
                                                       {"name": "greet", "confidence": 0.138640150427818},
                                                       {"name": "affirm", "confidence": 0.0857767835259438},
                                                       {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                       {"name": "deny", "confidence": 0.069614589214325},
                                                       {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                       {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                       {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                       {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                    "response_selector": {
                                        "default": {"response": {"name": None, "confidence": 0}, "ranking": [],
                                                    "full_retrieval_intent": None}}, "text": "can\"t"},
                     "input_channel": None, "message_id": "e96e2a85de0748798748385503c65fb3", "metadata": {}},
                    {"event": "action", "timestamp": 1594907117.04547, "name": "utter_test intent",
                     "policy": "policy_1_TEDPolicy", "confidence": 0.978452920913696},
                    {"event": "bot", "timestamp": 1594907117.04548, "text": "can not = can't",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}}],
                "latest_input_channel": "rest",
                "active_loop": {},
                "latest_action": {},
            },
            "domain": {
                "config": {},
                "session_config": {},
                "intents": [],
                "entities": [],
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e"},
                "responses": {},
                "actions": [],
                "forms": {},
                "e2e_actions": []
            },
            "version": "version"
        }

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
                        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
                        response_json = json.loads(response.body.decode("utf8"))
                        self.assertEqual(response_json, {'events': [
                            {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
                             'value': 'lead created'}], 'responses': [
                            {'text': 'lead created', 'buttons': [], 'elements': [], 'custom': {},
                             'template': None,
                             'response': None, 'image': None, 'attachment': None}]})

    def test_process_razorpay_action_failure(self):
        action_name = "test_process_razorpay_action_failure"
        bot = "5f50fd0a56b698ca10d35d2e"

        Actions(name=action_name, type=ActionType.razorpay_action.value, bot=bot, user='test_user').save()
        RazorpayAction(
            name=action_name,
            api_key=CustomActionRequestParameters(value="API_KEY", parameter_type=ActionParameterType.key_vault),
            api_secret=CustomActionRequestParameters(value="API_SECRET", parameter_type=ActionParameterType.key_vault),
            amount=CustomActionRequestParameters(value="amount", parameter_type=ActionParameterType.slot),
            currency=CustomActionRequestParameters(value="INR", parameter_type=ActionParameterType.value),
            username=CustomActionRequestParameters(parameter_type=ActionParameterType.sender_id),
            email=CustomActionRequestParameters(parameter_type=ActionParameterType.sender_id),
            contact=CustomActionRequestParameters(value="contact", parameter_type=ActionParameterType.slot),
            bot=bot, user="udit.pandey@digite.com"
        ).save()
        KeyVault(key="API_KEY", value="asdfghjkertyuio", bot=bot, user="user").save()
        KeyVault(key="API_SECRET", value="sdfghj345678dfghj", bot=bot, user="user").save()
        request_object = json.load(open("tests/testing_data/actions/action-request.json"))
        request_object["tracker"]["slots"]["bot"] = bot
        request_object["tracker"]["slots"]["amount"] = 11000
        request_object["tracker"]["slots"]["contact"] = "987654320"
        request_object["next_action"] = action_name
        request_object["tracker"]["sender_id"] = "udit.pandey"

        response_object = json.load(open("tests/testing_data/actions/razorpay-failure.json"))
        responses.add(
            "POST",
            "https://api.razorpay.com/v1/payment_links/",
            json=response_object,
            match=[responses.matchers.json_params_matcher({
                "amount": 11000, "currency": "INR",
                "customer": {"username": "udit.pandey", "email": "udit.pandey", "contact": "987654320"}
            })]
        )

        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response_json, {'events': [{'event': 'slot', 'name': 'kairon_action_response',
                                                     'timestamp': None, 'value': "I have failed to process your request"}],
                                         'responses': [{'attachment': None, 'buttons': [], 'custom': {},
                                                        'elements': [], 'image': None, 'response': None,
                                                        'template': None, 'text': "I have failed to process your request"}]})

    def test_process_razorpay_action_not_exists(self):
        action_name = "test_process_razorpay_action_not_exists"
        bot = "5f50fd0a56b698ca10d35d2e"

        Actions(name=action_name, type=ActionType.razorpay_action.value, bot=bot, user='test_user').save()

        request_object = json.load(open("tests/testing_data/actions/action-request.json"))
        request_object["tracker"]["slots"]["bot"] = bot
        request_object["next_action"] = action_name
        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response_json, {'events': [], 'responses': []})

    @responses.activate
    def test_process_razorpay_action(self):
        action_name = "test_process_razorpay_action"
        bot = "5f50fd0a56b698ca10d35d2e"

        Actions(name=action_name, type=ActionType.razorpay_action.value, bot=bot, user='test_user').save()
        RazorpayAction(
            name=action_name,
            api_key=CustomActionRequestParameters(value="API_KEY", parameter_type=ActionParameterType.key_vault),
            api_secret=CustomActionRequestParameters(value="API_SECRET", parameter_type=ActionParameterType.key_vault),
            amount=CustomActionRequestParameters(value="amount", parameter_type=ActionParameterType.slot),
            currency=CustomActionRequestParameters(value="INR", parameter_type=ActionParameterType.value),
            username=CustomActionRequestParameters(parameter_type=ActionParameterType.sender_id),
            email=CustomActionRequestParameters(parameter_type=ActionParameterType.sender_id),
            contact=CustomActionRequestParameters(value="contact", parameter_type=ActionParameterType.slot),
            bot=bot, user="udit.pandey@digite.com"
        ).save()
        KeyVault(key="API_KEY", value="asdfghjkertyuio", bot=bot, user="user").save()
        KeyVault(key="API_SECRET", value="sdfghj345678dfghj", bot=bot, user="user").save()
        request_object = json.load(open("tests/testing_data/actions/action-request.json"))
        request_object["tracker"]["slots"]["bot"] = bot
        request_object["tracker"]["slots"]["amount"] = 11000
        request_object["tracker"]["slots"]["contact"] = "987654320"
        request_object["next_action"] = action_name
        request_object["tracker"]["sender_id"] = "udit.pandey"

        response_object = json.load(open("tests/testing_data/actions/razorpay-success.json"))
        responses.add(
            "POST",
            "https://api.razorpay.com/v1/payment_links/",
            json=response_object,
            match=[responses.matchers.json_params_matcher({
                "amount": 11000, "currency": "INR",
                "customer": {"username": "udit.pandey", "email": "udit.pandey", "contact": "987654320"}
            })]
        )

        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response_json, {'events': [{'event': 'slot', 'name': 'kairon_action_response',
                                                     'timestamp': None, 'value': 'https://rzp.io/i/nxrHnLJ'}],
                                         'responses': [{'attachment': None,  'buttons': [], 'custom': {},
                                                        'elements': [], 'image': None, 'response': None,
                                                        'template': None, 'text': 'https://rzp.io/i/nxrHnLJ'}]})

    def test_process_pipedrive_leads_action_failure(self):
        action_name = "test_process_pipedrive_leads_action_failure"
        bot = "5f50fd0a56b698ca10d35d2e"
        user = 'test_user'

        Actions(name=action_name, type=ActionType.pipedrive_leads_action.value, bot=bot, user='test_user').save()
        with patch('pipedrive.client.Client'):
            metadata = {'name': 'name', 'org_name': 'organization', 'email': 'email', 'phone': 'phone'}
            PipedriveLeadsAction(name=action_name, domain='https://digite751.pipedrive.com/',
                                 api_token=CustomActionRequestParameters(value='1234567890'),
                                 title='new lead generated', response='new lead created', metadata=metadata, bot=bot,
                                 user=user).save()

        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {"bot": bot, "to_email": "test@test.com", "organization": "digite"},
                "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]},
                "latest_event_time": 1537645578.314389,
                "followup_action": "action_listen",
                "paused": False,
                "events": [
                    {"event": "action", "timestamp": 1594907100.12764, "name": "action_session_start", "policy": None,
                     "confidence": None}, {"event": "session_started", "timestamp": 1594907100.12765},
                    {"event": "action", "timestamp": 1594907100.12767, "name": "action_listen", "policy": None,
                     "confidence": None}, {"event": "user", "timestamp": 1594907100.42744, "text": "can't",
                                           "parse_data": {
                                               "intent": {"name": "test intent", "confidence": 0.253578245639801},
                                               "entities": [], "intent_ranking": [
                                                   {"name": "test intent", "confidence": 0.253578245639801},
                                                   {"name": "goodbye", "confidence": 0.1504897326231},
                                                   {"name": "greet", "confidence": 0.138640150427818},
                                                   {"name": "affirm", "confidence": 0.0857767835259438},
                                                   {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                   {"name": "deny", "confidence": 0.069614589214325},
                                                   {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                   {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                   {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                   {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                               "response_selector": {
                                                   "default": {"response": {"name": None, "confidence": 0},
                                                               "ranking": [], "full_retrieval_intent": None}},
                                               "text": "can't"}, "input_channel": None,
                                           "message_id": "bbd413bf5c834bf3b98e0da2373553b2", "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.4308, "name": "utter_test intent",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "bot", "timestamp": 1594907100.4308, "text": "will not = won\"t",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.43384, "name": "action_listen",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "user", "timestamp": 1594907117.04194, "text": "can\"t",
                     "parse_data": {"intent": {"name": "test intent", "confidence": 0.253578245639801}, "entities": [],
                                    "intent_ranking": [{"name": "test intent", "confidence": 0.253578245639801},
                                                       {"name": "goodbye", "confidence": 0.1504897326231},
                                                       {"name": "greet", "confidence": 0.138640150427818},
                                                       {"name": "affirm", "confidence": 0.0857767835259438},
                                                       {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                       {"name": "deny", "confidence": 0.069614589214325},
                                                       {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                       {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                       {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                       {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                    "response_selector": {
                                        "default": {"response": {"name": None, "confidence": 0}, "ranking": [],
                                                    "full_retrieval_intent": None}}, "text": "can\"t"},
                     "input_channel": None, "message_id": "e96e2a85de0748798748385503c65fb3", "metadata": {}},
                    {"event": "action", "timestamp": 1594907117.04547, "name": "utter_test intent",
                     "policy": "policy_1_TEDPolicy", "confidence": 0.978452920913696},
                    {"event": "bot", "timestamp": 1594907117.04548, "text": "can not = can't",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}}],
                "latest_input_channel": "rest",
                "active_loop": {},
                "latest_action": {},
            },
            "domain": {
                "config": {},
                "session_config": {},
                "intents": [],
                "entities": [],
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e"},
                "responses": {},
                "actions": [],
                "forms": {},
                "e2e_actions": []
            },
            "version": "version"
        }

        def __mock_pipedrive_error(*args, **kwargs):
            from pipedrive.exceptions import BadRequestError
            raise BadRequestError('Invalid request raised', {'error_code': 402})

        with patch('pipedrive.organizations.Organizations.create_organization', __mock_pipedrive_error):
            response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
            response_json = json.loads(response.body.decode("utf8"))
            self.assertEqual(response_json, {'events': [
                {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
                 'value': 'I have failed to create lead for you'}], 'responses': [
                {'text': 'I have failed to create lead for you', 'buttons': [], 'elements': [], 'custom': {},
                 'template': None,
                 'response': None, 'image': None, 'attachment': None}]})

    def test_process_hubspot_forms_action_not_exists(self):
        action_name = "test_process_hubspot_forms_action_not_exists"
        bot = "5f50fd0a56b698ca10d35d2e"

        Actions(name=action_name, type=ActionType.hubspot_forms_action.value, bot=bot, user='test_user').save()

        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {"bot": bot, "to_email": "test@test.com"},
                "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]},
                "latest_event_time": 1537645578.314389,
                "followup_action": "action_listen",
                "paused": False,
                "events": [
                    {"event": "action", "timestamp": 1594907100.12764, "name": "action_session_start", "policy": None,
                     "confidence": None}, {"event": "session_started", "timestamp": 1594907100.12765},
                    {"event": "action", "timestamp": 1594907100.12767, "name": "action_listen", "policy": None,
                     "confidence": None}, {"event": "user", "timestamp": 1594907100.42744, "text": "can't",
                                           "parse_data": {
                                               "intent": {"name": "test intent", "confidence": 0.253578245639801},
                                               "entities": [], "intent_ranking": [
                                                   {"name": "test intent", "confidence": 0.253578245639801},
                                                   {"name": "goodbye", "confidence": 0.1504897326231},
                                                   {"name": "greet", "confidence": 0.138640150427818},
                                                   {"name": "affirm", "confidence": 0.0857767835259438},
                                                   {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                   {"name": "deny", "confidence": 0.069614589214325},
                                                   {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                   {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                   {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                   {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                               "response_selector": {
                                                   "default": {"response": {"name": None, "confidence": 0},
                                                               "ranking": [], "full_retrieval_intent": None}},
                                               "text": "can't"}, "input_channel": None,
                                           "message_id": "bbd413bf5c834bf3b98e0da2373553b2", "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.4308, "name": "utter_test intent",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "bot", "timestamp": 1594907100.4308, "text": "will not = won\"t",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.43384, "name": "action_listen",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "user", "timestamp": 1594907117.04194, "text": "can\"t",
                     "parse_data": {"intent": {"name": "test intent", "confidence": 0.253578245639801}, "entities": [],
                                    "intent_ranking": [{"name": "test intent", "confidence": 0.253578245639801},
                                                       {"name": "goodbye", "confidence": 0.1504897326231},
                                                       {"name": "greet", "confidence": 0.138640150427818},
                                                       {"name": "affirm", "confidence": 0.0857767835259438},
                                                       {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                       {"name": "deny", "confidence": 0.069614589214325},
                                                       {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                       {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                       {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                       {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                    "response_selector": {
                                        "default": {"response": {"name": None, "confidence": 0}, "ranking": [],
                                                    "full_retrieval_intent": None}}, "text": "can\"t"},
                     "input_channel": None, "message_id": "e96e2a85de0748798748385503c65fb3", "metadata": {}},
                    {"event": "action", "timestamp": 1594907117.04547, "name": "utter_test intent",
                     "policy": "policy_1_TEDPolicy", "confidence": 0.978452920913696},
                    {"event": "bot", "timestamp": 1594907117.04548, "text": "can not = can't",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}}],
                "latest_input_channel": "rest",
                "active_loop": {},
                "latest_action": {},
            },
            "domain": {
                "config": {},
                "session_config": {},
                "intents": [],
                "entities": [],
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e"},
                "responses": {},
                "actions": [],
                "forms": {},
                "e2e_actions": []
            },
            "version": "version"
        }
        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response_json, {'events': [], 'responses': []})

    def test_process_hubspot_forms_action(self):
        action_name = "hubspot_forms_action"
        bot = "5f50fd0a56b698ca10d35d2e"
        user = 'test_user'
        portal_id = 'asdf45'
        form_guid = '2345678gh'
        fields = [
            {'key': 'email', 'parameter_type': 'slot', 'value': 'email_slot'},
            {'key': 'firstname', 'parameter_type': 'slot', 'value': 'firstname_slot'}
        ]

        Actions(name=action_name, type=ActionType.hubspot_forms_action.value, bot=bot, user=user).save()
        HubspotFormsAction(
            name=action_name, portal_id=portal_id, form_guid=form_guid, fields=fields, bot=bot, user=user,
            response="Hubspot Form submitted"
        ).save()

        responses.add(
            "POST",
            f"https://api.hsforms.com/submissions/v3/integration/submit/{portal_id}/{form_guid}",
            json={'inlineMessage': 'Thankyou for the submission'},
            match=[responses.matchers.json_params_matcher({"fields": [{"name": "email", "value": "pandey.udit867@gmail.com"},
                                                             {"name": "firstname", "value": "udit pandey"}]})]
        )
        responses.start()
        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {'bot': bot, 'firstname_slot': 'udit pandey', 'organization': 'digite',
                          'email_slot': 'pandey.udit867@gmail.com', 'phone': '9876543210'},
                "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]},
                "latest_event_time": 1537645578.314389,
                "followup_action": "action_listen",
                "paused": False,
                "events": [
                    {"event": "action", "timestamp": 1594907100.12764, "name": "action_session_start", "policy": None,
                     "confidence": None}, {"event": "session_started", "timestamp": 1594907100.12765},
                    {"event": "action", "timestamp": 1594907100.12767, "name": "action_listen", "policy": None,
                     "confidence": None}, {"event": "user", "timestamp": 1594907100.42744, "text": "can't",
                                           "parse_data": {
                                               "intent": {"name": "test intent", "confidence": 0.253578245639801},
                                               "entities": [], "intent_ranking": [
                                                   {"name": "test intent", "confidence": 0.253578245639801},
                                                   {"name": "goodbye", "confidence": 0.1504897326231},
                                                   {"name": "greet", "confidence": 0.138640150427818},
                                                   {"name": "affirm", "confidence": 0.0857767835259438},
                                                   {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                   {"name": "deny", "confidence": 0.069614589214325},
                                                   {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                   {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                   {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                   {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                               "response_selector": {
                                                   "default": {"response": {"name": None, "confidence": 0},
                                                               "ranking": [], "full_retrieval_intent": None}},
                                               "text": "can't"}, "input_channel": None,
                                           "message_id": "bbd413bf5c834bf3b98e0da2373553b2", "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.4308, "name": "utter_test intent",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "bot", "timestamp": 1594907100.4308, "text": "will not = won\"t",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.43384, "name": "action_listen",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "user", "timestamp": 1594907117.04194, "text": "can\"t",
                     "parse_data": {"intent": {"name": "test intent", "confidence": 0.253578245639801}, "entities": [],
                                    "intent_ranking": [{"name": "test intent", "confidence": 0.253578245639801},
                                                       {"name": "goodbye", "confidence": 0.1504897326231},
                                                       {"name": "greet", "confidence": 0.138640150427818},
                                                       {"name": "affirm", "confidence": 0.0857767835259438},
                                                       {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                       {"name": "deny", "confidence": 0.069614589214325},
                                                       {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                       {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                       {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                       {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                    "response_selector": {
                                        "default": {"response": {"name": None, "confidence": 0}, "ranking": [],
                                                    "full_retrieval_intent": None}}, "text": "can\"t"},
                     "input_channel": None, "message_id": "e96e2a85de0748798748385503c65fb3", "metadata": {}},
                    {"event": "action", "timestamp": 1594907117.04547, "name": "utter_test intent",
                     "policy": "policy_1_TEDPolicy", "confidence": 0.978452920913696},
                    {"event": "bot", "timestamp": 1594907117.04548, "text": "can not = can't",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}}],
                "latest_input_channel": "rest",
                "active_loop": {},
                "latest_action": {},
            },
            "domain": {
                "config": {},
                "session_config": {},
                "intents": [],
                "entities": [],
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e"},
                "responses": {},
                "actions": [],
                "forms": {},
                "e2e_actions": []
            },
            "version": "version"
        }

        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response_json, {'events': [
                            {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
                             'value': 'Hubspot Form submitted'}], 'responses': [
                            {'text': 'Hubspot Form submitted', 'buttons': [], 'elements': [], 'custom': {},
                             'template': None,
                             'response': None, 'image': None, 'attachment': None}]})
        responses.stop()
        responses.reset()

    def test_process_hubspot_forms_action_failure(self):
        action_name = "test_process_hubspot_forms_action_failure"
        bot = "5f50fd0a56b698ca10d35d2e"
        user = 'test_user'

        portal_id = 'asdf45jhgj'
        form_guid = '2345678ghkjnknj'
        fields = [
            {'key': 'email', 'parameter_type': 'slot', 'value': 'email_slot'},
            {'key': 'firstname', 'parameter_type': 'slot', 'value': 'firstname_slot'}
        ]
        Actions(name=action_name, type=ActionType.hubspot_forms_action.value, bot=bot, user=user).save()
        HubspotFormsAction(
            name=action_name, portal_id=portal_id, form_guid=form_guid, fields=fields, bot=bot, user=user,
            response="Hubspot Form submitted"
        ).save()

        responses.add(
            "POST",
            f"https://api.hsforms.com/submissions/v3/integration/submit/{portal_id}/{form_guid}",
            status=400, json={"inline_message": "invalid request body"}
        )
        responses.start()
        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {"bot": bot, "to_email": "test@test.com", "organization": "digite"},
                "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]},
                "latest_event_time": 1537645578.314389,
                "followup_action": "action_listen",
                "paused": False,
                "events": [
                    {"event": "action", "timestamp": 1594907100.12764, "name": "action_session_start", "policy": None,
                     "confidence": None}, {"event": "session_started", "timestamp": 1594907100.12765},
                    {"event": "action", "timestamp": 1594907100.12767, "name": "action_listen", "policy": None,
                     "confidence": None}, {"event": "user", "timestamp": 1594907100.42744, "text": "can't",
                                           "parse_data": {
                                               "intent": {"name": "test intent", "confidence": 0.253578245639801},
                                               "entities": [], "intent_ranking": [
                                                   {"name": "test intent", "confidence": 0.253578245639801},
                                                   {"name": "goodbye", "confidence": 0.1504897326231},
                                                   {"name": "greet", "confidence": 0.138640150427818},
                                                   {"name": "affirm", "confidence": 0.0857767835259438},
                                                   {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                   {"name": "deny", "confidence": 0.069614589214325},
                                                   {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                   {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                   {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                   {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                               "response_selector": {
                                                   "default": {"response": {"name": None, "confidence": 0},
                                                               "ranking": [], "full_retrieval_intent": None}},
                                               "text": "can't"}, "input_channel": None,
                                           "message_id": "bbd413bf5c834bf3b98e0da2373553b2", "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.4308, "name": "utter_test intent",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "bot", "timestamp": 1594907100.4308, "text": "will not = won\"t",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.43384, "name": "action_listen",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "user", "timestamp": 1594907117.04194, "text": "can\"t",
                     "parse_data": {"intent": {"name": "test intent", "confidence": 0.253578245639801}, "entities": [],
                                    "intent_ranking": [{"name": "test intent", "confidence": 0.253578245639801},
                                                       {"name": "goodbye", "confidence": 0.1504897326231},
                                                       {"name": "greet", "confidence": 0.138640150427818},
                                                       {"name": "affirm", "confidence": 0.0857767835259438},
                                                       {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                       {"name": "deny", "confidence": 0.069614589214325},
                                                       {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                       {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                       {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                       {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                    "response_selector": {
                                        "default": {"response": {"name": None, "confidence": 0}, "ranking": [],
                                                    "full_retrieval_intent": None}}, "text": "can\"t"},
                     "input_channel": None, "message_id": "e96e2a85de0748798748385503c65fb3", "metadata": {}},
                    {"event": "action", "timestamp": 1594907117.04547, "name": "utter_test intent",
                     "policy": "policy_1_TEDPolicy", "confidence": 0.978452920913696},
                    {"event": "bot", "timestamp": 1594907117.04548, "text": "can not = can't",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}}],
                "latest_input_channel": "rest",
                "active_loop": {},
                "latest_action": {},
            },
            "domain": {
                "config": {},
                "session_config": {},
                "intents": [],
                "entities": [],
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e"},
                "responses": {},
                "actions": [],
                "forms": {},
                "e2e_actions": []
            },
            "version": "version"
        }

        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response_json, {'events': [
                {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
                 'value': "I have failed to process your request"}], 'responses': [
                {'text': "I have failed to process your request", 'buttons': [], 'elements': [], 'custom': {},
                 'template': None,
                 'response': None, 'image': None, 'attachment': None}]})
        responses.stop()
        responses.reset()

    def test_two_stage_fallback_action(self):
        action_name = KAIRON_TWO_STAGE_FALLBACK.lower()
        bot = "5f50fd0a56b698ca10d35d2e"
        user = 'test_user'
        Actions(name=action_name, type=ActionType.two_stage_fallback.value, bot=bot, user=user).save()
        action = KaironTwoStageFallbackAction(
            name=action_name, text_recommendations={"count": 3, "use_intent_ranking": True}, bot=bot, user=user
        )
        action.save()
        mongo_processor = MongoProcessor()
        list(mongo_processor.add_training_example(["hi", "hello"], "greet", bot, user, False))
        list(mongo_processor.add_training_example(["bye", "bye bye"], "goodbye", bot, user, False))
        list(mongo_processor.add_training_example(["yes", "go ahead"], "affirm", bot, user, False))
        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {'bot': bot, 'firstname_slot': 'udit pandey', 'organization': 'digite',
                          'email_slot': 'pandey.udit867@gmail.com', 'phone': '9876543210'},
                "latest_message": {'text': 'get intents', 'intent_ranking': [
                    {"name": "test intent", "confidence": 0.253578245639801},
                    {"name": "goodbye", "confidence": 0.1504897326231},
                    {"name": "greet", "confidence": 0.138640150427818},
                    {"name": "affirm", "confidence": 0.0857767835259438},
                    {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                    {"name": "deny", "confidence": 0.069614589214325},
                    {"name": "bot_challenge", "confidence": 0.0664894133806229},
                    {"name": "faq_vaccine", "confidence": 0.062177762389183},
                    {"name": "faq_testing", "confidence": 0.0530692934989929},
                    {"name": "out_of_scope", "confidence": 0.0480506233870983}]},
                "latest_event_time": 1537645578.314389,
                "followup_action": "action_listen",
                "paused": False,
                "events": [
                    {"event": "action", "timestamp": 1594907100.12764, "name": "action_session_start", "policy": None,
                     "confidence": None}, {"event": "session_started", "timestamp": 1594907100.12765},
                    {"event": "action", "timestamp": 1594907100.12767, "name": "action_listen", "policy": None,
                     "confidence": None}, {"event": "user", "timestamp": 1594907100.42744, "text": "can't",
                                           "parse_data": {
                                               "intent": {"name": "test intent", "confidence": 0.253578245639801},
                                               "entities": [], "intent_ranking": [
                                                   {"name": "test intent", "confidence": 0.253578245639801},
                                                   {"name": "goodbye", "confidence": 0.1504897326231},
                                                   {"name": "greet", "confidence": 0.138640150427818},
                                                   {"name": "affirm", "confidence": 0.0857767835259438},
                                                   {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                   {"name": "deny", "confidence": 0.069614589214325},
                                                   {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                   {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                   {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                   {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                               "response_selector": {
                                                   "default": {"response": {"name": None, "confidence": 0},
                                                               "ranking": [], "full_retrieval_intent": None}},
                                               "text": "can't"}, "input_channel": None,
                                           "message_id": "bbd413bf5c834bf3b98e0da2373553b2", "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.4308, "name": "utter_test intent",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "bot", "timestamp": 1594907100.4308, "text": "will not = won\"t",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.43384, "name": "action_listen",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "user", "timestamp": 1594907117.04194, "text": "can\"t",
                     "parse_data": {"intent": {"name": "test intent", "confidence": 0.253578245639801}, "entities": [],
                                    "intent_ranking": [{"name": "test intent", "confidence": 0.253578245639801},
                                                       {"name": "goodbye", "confidence": 0.1504897326231},
                                                       {"name": "greet", "confidence": 0.138640150427818},
                                                       {"name": "affirm", "confidence": 0.0857767835259438},
                                                       {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                       {"name": "deny", "confidence": 0.069614589214325},
                                                       {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                       {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                       {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                       {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                    "response_selector": {
                                        "default": {"response": {"name": None, "confidence": 0}, "ranking": [],
                                                    "full_retrieval_intent": None}}, "text": "can\"t"},
                     "input_channel": None, "message_id": "e96e2a85de0748798748385503c65fb3", "metadata": {}},
                    {"event": "action", "timestamp": 1594907117.04547, "name": "utter_test intent",
                     "policy": "policy_1_TEDPolicy", "confidence": 0.978452920913696},
                    {"event": "bot", "timestamp": 1594907117.04548, "text": "can not = can't",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}}],
                "latest_input_channel": "rest",
                "active_loop": {},
                "latest_action": {},
            },
            "domain": {
                "config": {},
                "session_config": {},
                "intents": [],
                "entities": [],
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e"},
                "responses": {},
                "actions": [],
                "forms": {},
                "e2e_actions": []
            },
            "version": "version"
        }

        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response_json['events'], [])
        self.assertEqual(len(response_json['responses'][0]['buttons']), 3)
        self.assertEqual(set(response_json['responses'][0]['buttons'][0].keys()), {"text", "payload"})
        self.assertEqual(response_json['responses'][0]['text'], FALLBACK_MESSAGE)
        action.text_recommendations = TwoStageFallbackTextualRecommendations(**{"count": 3})
        action.save()

        def _mock_search(*args, **kwargs):
            for result in [{"text": "hi", "payload": "hi"}, {"text": "bye", "payload": "bye"}, {"text": "yes", "payload": "yes"}]:
                yield result

        with patch.object(MongoProcessor, "search_training_examples") as mock_action:
            mock_action.side_effect = _mock_search
            response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
            response_json = json.loads(response.body.decode("utf8"))
            self.assertEqual(response_json['events'], [])
            self.assertEqual(len(response_json['responses'][0]['buttons']), 3)
            self.assertEqual(set(response_json['responses'][0]['buttons'][0].keys()), {"text", "payload"})

        def _mock_search(*args, **kwargs):
            for _ in []:
                yield

        with patch.object(MongoProcessor, "search_training_examples") as mock_action:
            mock_action.side_effect = _mock_search
            response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
            response_json = json.loads(response.body.decode("utf8"))
            self.assertEqual(response_json['events'], [])
            self.assertEqual(response_json['responses'], [
                {"text": None, "buttons": [], "elements": [], "custom": {}, "template": "utter_default",
                 "response": "utter_default", "image": None, "attachment": None}])

    def test_two_stage_fallback_action_no_intent_ranking(self):
        action_name = KAIRON_TWO_STAGE_FALLBACK.lower()
        bot = "5f50fd0a56b698ca10d35d2f"
        user = 'test_user'
        mongo_processor = MongoProcessor()
        Actions(name=action_name, type=ActionType.two_stage_fallback.value, bot=bot, user=user).save()
        KaironTwoStageFallbackAction(
            name=action_name, text_recommendations={"count": 3, "use_intent_ranking": True}, trigger_rules=[
                {"text": "Trigger", "payload": "set_context"},
                {"text": "Mail me", "payload": "send_mail", 'message': "welcome new user"},
                {"text": "Mail me", "payload": "send_mail", 'message': "welcome new user", "is_dynamic_msg": True},
            ], bot=bot, user=user
        ).save()
        list(mongo_processor.add_training_example(["hi", "hello"], "greet", bot, user, False))
        list(mongo_processor.add_training_example(["bye", "bye bye"], "goodbye", bot, user, False))
        list(mongo_processor.add_training_example(["yes", "go ahead"], "affirm", bot, user, False))
        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {'bot': bot, 'firstname_slot': 'udit pandey', 'organization': 'digite',
                          'email_slot': 'pandey.udit867@gmail.com', 'phone': '9876543210'},
                "latest_message": {'text': 'get intents', 'intent_ranking': [
                    {"name": "test intent", "confidence": 0.253578245639801}]},
                "latest_event_time": 1537645578.314389,
                "followup_action": "action_listen",
                "paused": False,
                "events": [
                    {"event": "action", "timestamp": 1594907100.12764, "name": "action_session_start", "policy": None,
                     "confidence": None}, {"event": "session_started", "timestamp": 1594907100.12765},
                    {"event": "action", "timestamp": 1594907100.12767, "name": "action_listen", "policy": None,
                     "confidence": None}, {"event": "user", "timestamp": 1594907100.42744, "text": "can't",
                                           "parse_data": {
                                               "intent": {"name": "test intent", "confidence": 0.253578245639801},
                                               "entities": [], "intent_ranking": [
                                                   {"name": "test intent", "confidence": 0.253578245639801},
                                                   {"name": "goodbye", "confidence": 0.1504897326231},
                                                   {"name": "greet", "confidence": 0.138640150427818},
                                                   {"name": "affirm", "confidence": 0.0857767835259438},
                                                   {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                   {"name": "deny", "confidence": 0.069614589214325},
                                                   {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                   {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                   {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                   {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                               "response_selector": {
                                                   "default": {"response": {"name": None, "confidence": 0},
                                                               "ranking": [], "full_retrieval_intent": None}},
                                               "text": "can't"}, "input_channel": None,
                                           "message_id": "bbd413bf5c834bf3b98e0da2373553b2", "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.4308, "name": "utter_test intent",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "bot", "timestamp": 1594907100.4308, "text": "will not = won\"t",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.43384, "name": "action_listen",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "user", "timestamp": 1594907117.04194, "text": "can\"t",
                     "parse_data": {"intent": {"name": "test intent", "confidence": 0.253578245639801}, "entities": [],
                                    "intent_ranking": [{"name": "test intent", "confidence": 0.253578245639801},
                                                       {"name": "goodbye", "confidence": 0.1504897326231},
                                                       {"name": "greet", "confidence": 0.138640150427818},
                                                       {"name": "affirm", "confidence": 0.0857767835259438},
                                                       {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                       {"name": "deny", "confidence": 0.069614589214325},
                                                       {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                       {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                       {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                       {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                    "response_selector": {
                                        "default": {"response": {"name": None, "confidence": 0}, "ranking": [],
                                                    "full_retrieval_intent": None}}, "text": "can\"t"},
                     "input_channel": None, "message_id": "e96e2a85de0748798748385503c65fb3", "metadata": {}},
                    {"event": "action", "timestamp": 1594907117.04547, "name": "utter_test intent",
                     "policy": "policy_1_TEDPolicy", "confidence": 0.978452920913696},
                    {"event": "bot", "timestamp": 1594907117.04548, "text": "can not = can't",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}}],
                "latest_input_channel": "rest",
                "active_loop": {},
                "latest_action": {},
            },
            "domain": {
                "config": {},
                "session_config": {},
                "intents": [],
                "entities": [],
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e"},
                "responses": {},
                "actions": [],
                "forms": {},
                "e2e_actions": []
            },
            "version": "version"
        }

        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response_json['events'], [])
        self.assertEqual(response_json['responses'][0]['text'], FALLBACK_MESSAGE)
        self.assertEqual(len(response_json['responses'][0]['buttons']), 3)
        self.assertEqual(response_json['responses'][0]['buttons'], [
            {'payload': '/set_context', 'text': 'Trigger'},
            {'payload': '/send_mail{"kairon_user_msg": "welcome new user"}', 'text': 'Mail me'},
            {'payload': '/send_mail{"kairon_user_msg": "get intents"}', 'text': 'Mail me'}])

    def test_two_stage_fallback_intent_deleted(self):
        action_name = KAIRON_TWO_STAGE_FALLBACK.lower()
        bot = "5f50fd0a56b698ca10d35d2g"
        user = 'test_user'
        Actions(name=action_name, type=ActionType.two_stage_fallback.value, bot=bot, user=user).save()
        KaironTwoStageFallbackAction(
            name=action_name, text_recommendations={"count": 3, "use_intent_ranking": True}, trigger_rules=[
                {"text": "Trigger", "payload": "set_context"}, {"text": "Mail me", "payload": "send_mail"}
            ], bot=bot, user=user
        ).save()
        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {'bot': bot, 'firstname_slot': 'udit pandey', 'organization': 'digite',
                          'email_slot': 'pandey.udit867@gmail.com', 'phone': '9876543210'},
                "latest_message": {'text': 'get intents', 'intent_ranking': [
                    {"name": "test intent", "confidence": 0.253578245639801},
                    {"name": "goodbye", "confidence": 0.1504897326231},
                    {"name": "greet", "confidence": 0.138640150427818},
                    {"name": "affirm", "confidence": 0.0857767835259438},
                    {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                    {"name": "deny", "confidence": 0.069614589214325},
                    {"name": "bot_challenge", "confidence": 0.0664894133806229},
                    {"name": "faq_vaccine", "confidence": 0.062177762389183},
                    {"name": "faq_testing", "confidence": 0.0530692934989929},
                    {"name": "out_of_scope", "confidence": 0.0480506233870983}
                ]},
                "latest_event_time": 1537645578.314389,
                "followup_action": "action_listen",
                "paused": False,
                "events": [
                    {"event": "action", "timestamp": 1594907100.12764, "name": "action_session_start", "policy": None,
                     "confidence": None}, {"event": "session_started", "timestamp": 1594907100.12765},
                    {"event": "action", "timestamp": 1594907100.12767, "name": "action_listen", "policy": None,
                     "confidence": None}, {"event": "user", "timestamp": 1594907100.42744, "text": "can't",
                                           "parse_data": {
                                               "intent": {"name": "test intent", "confidence": 0.253578245639801},
                                               "entities": [], "intent_ranking": [
                                                   {"name": "test intent", "confidence": 0.253578245639801},
                                                   {"name": "goodbye", "confidence": 0.1504897326231},
                                                   {"name": "greet", "confidence": 0.138640150427818},
                                                   {"name": "affirm", "confidence": 0.0857767835259438},
                                                   {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                   {"name": "deny", "confidence": 0.069614589214325},
                                                   {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                   {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                   {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                   {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                               "response_selector": {
                                                   "default": {"response": {"name": None, "confidence": 0},
                                                               "ranking": [], "full_retrieval_intent": None}},
                                               "text": "can't"}, "input_channel": None,
                                           "message_id": "bbd413bf5c834bf3b98e0da2373553b2", "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.4308, "name": "utter_test intent",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "bot", "timestamp": 1594907100.4308, "text": "will not = won\"t",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.43384, "name": "action_listen",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "user", "timestamp": 1594907117.04194, "text": "can\"t",
                     "parse_data": {"intent": {"name": "test intent", "confidence": 0.253578245639801}, "entities": [],
                                    "intent_ranking": [{"name": "test intent", "confidence": 0.253578245639801},
                                                       {"name": "goodbye", "confidence": 0.1504897326231},
                                                       {"name": "greet", "confidence": 0.138640150427818},
                                                       {"name": "affirm", "confidence": 0.0857767835259438},
                                                       {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                       {"name": "deny", "confidence": 0.069614589214325},
                                                       {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                       {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                       {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                       {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                    "response_selector": {
                                        "default": {"response": {"name": None, "confidence": 0}, "ranking": [],
                                                    "full_retrieval_intent": None}}, "text": "can\"t"},
                     "input_channel": None, "message_id": "e96e2a85de0748798748385503c65fb3", "metadata": {}},
                    {"event": "action", "timestamp": 1594907117.04547, "name": "utter_test intent",
                     "policy": "policy_1_TEDPolicy", "confidence": 0.978452920913696},
                    {"event": "bot", "timestamp": 1594907117.04548, "text": "can not = can't",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}}],
                "latest_input_channel": "rest",
                "active_loop": {},
                "latest_action": {},
            },
            "domain": {
                "config": {},
                "session_config": {},
                "intents": [],
                "entities": [],
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e"},
                "responses": {},
                "actions": [],
                "forms": {},
                "e2e_actions": []
            },
            "version": "version"
        }

        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response_json['events'], [])
        self.assertEqual(len(response_json['responses'][0]['buttons']), 2)
        self.assertEqual(response_json['responses'][0]['buttons'], [{"text": "Trigger", "payload": "/set_context"},
                                                                     {"text": "Mail me", "payload": "/send_mail"}])

        config = KaironTwoStageFallbackAction.objects(bot=bot, user=user).get()
        config.trigger_rules = None
        config.save()
        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response_json, {'events': [], 'responses': [
            {'text': None, 'buttons': [], 'elements': [], 'custom': {}, 'template': "utter_default",
             'response': "utter_default", 'image': None, 'attachment': None}]})

    def test_bot_response_action(self):
        action_name = 'utter_greet'
        bot = "5f50fd0a56b698ca10d35d2e"
        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {'bot': bot, 'firstname_slot': 'udit pandey', 'organization': 'digite',
                          'email_slot': 'pandey.udit867@gmail.com', 'phone': '9876543210'},
                "latest_message": {'text': 'hi', 'intent_ranking': [
                    {"name": "greet", "confidence": 0.853578245639801},
                    {"name": "goodbye", "confidence": 0.1504897326231},
                    {"name": "greet", "confidence": 0.138640150427818},
                    {"name": "affirm", "confidence": 0.0857767835259438},
                    {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                    {"name": "deny", "confidence": 0.069614589214325},
                    {"name": "bot_challenge", "confidence": 0.0664894133806229},
                    {"name": "faq_vaccine", "confidence": 0.062177762389183},
                    {"name": "faq_testing", "confidence": 0.0530692934989929},
                    {"name": "out_of_scope", "confidence": 0.0480506233870983}]},
                "latest_event_time": 1537645578.314389,
                "followup_action": "action_listen",
                "paused": False,
                "events": [
                    {"event": "action", "timestamp": 1594907100.12764, "name": "action_session_start", "policy": None,
                     "confidence": None}, {"event": "session_started", "timestamp": 1594907100.12765},
                    {"event": "action", "timestamp": 1594907100.12767, "name": "action_listen", "policy": None,
                     "confidence": None}, {"event": "user", "timestamp": 1594907100.42744, "text": "can't",
                                           "parse_data": {
                                               "intent": {"name": "test intent", "confidence": 0.253578245639801},
                                               "entities": [], "intent_ranking": [
                                                   {"name": "test intent", "confidence": 0.253578245639801},
                                                   {"name": "goodbye", "confidence": 0.1504897326231},
                                                   {"name": "greet", "confidence": 0.138640150427818},
                                                   {"name": "affirm", "confidence": 0.0857767835259438},
                                                   {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                   {"name": "deny", "confidence": 0.069614589214325},
                                                   {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                   {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                   {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                   {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                               "response_selector": {
                                                   "default": {"response": {"name": None, "confidence": 0},
                                                               "ranking": [], "full_retrieval_intent": None}},
                                               "text": "can't"}, "input_channel": None,
                                           "message_id": "bbd413bf5c834bf3b98e0da2373553b2", "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.4308, "name": "utter_test intent",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "bot", "timestamp": 1594907100.4308, "text": "will not = won\"t",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.43384, "name": "action_listen",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "user", "timestamp": 1594907117.04194, "text": "can\"t",
                     "parse_data": {"intent": {"name": "test intent", "confidence": 0.253578245639801}, "entities": [],
                                    "intent_ranking": [{"name": "test intent", "confidence": 0.253578245639801},
                                                       {"name": "goodbye", "confidence": 0.1504897326231},
                                                       {"name": "greet", "confidence": 0.138640150427818},
                                                       {"name": "affirm", "confidence": 0.0857767835259438},
                                                       {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                       {"name": "deny", "confidence": 0.069614589214325},
                                                       {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                       {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                       {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                       {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                    "response_selector": {
                                        "default": {"response": {"name": None, "confidence": 0}, "ranking": [],
                                                    "full_retrieval_intent": None}}, "text": "can\"t"},
                     "input_channel": None, "message_id": "e96e2a85de0748798748385503c65fb3", "metadata": {}},
                    {"event": "action", "timestamp": 1594907117.04547, "name": "utter_test intent",
                     "policy": "policy_1_TEDPolicy", "confidence": 0.978452920913696},
                    {"event": "bot", "timestamp": 1594907117.04548, "text": "can not = can't",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}}],
                "latest_input_channel": "rest",
                "active_loop": {},
                "latest_action": {},
            },
            "domain": {"config": {"store_entities_as_slots": True},
                       "session_config": {"session_expiration_time": 60, "carry_over_slots_to_new_session": True},
                       "intents": [{"greet": {"use_entities": []}}, {"list_movie": {"use_entities": []}},
                                   {"movie_poster": {"use_entities": []}}, {"movie_trailer": {"use_entities": []}},
                                   {"movie_location": {"use_entities": []}}, {"booking_link": {"use_entities": []}},
                                   {"send_details": {"use_entities": []}}, {"restart": {"use_entities": True}},
                                   {"back": {"use_entities": True}}, {"out_of_scope": {"use_entities": True}},
                                   {"session_start": {"use_entities": True}}, {"nlu_fallback": {"use_entities": True}},
                                   {"callapi": {"use_entities": []}}], "entities": ["bot", "kairon_action_response"],
                       "slots": {"bot": {"type": "rasa.shared.core.slots.AnySlot",
                                         "initial_value": "637f1b92df3b90588a30073e", "auto_fill": True,
                                         "influence_conversation": True},
                                 "kairon_action_response": {"type": "rasa.shared.core.slots.AnySlot",
                                                            "initial_value": None, "auto_fill": False,
                                                            "influence_conversation": False}}, "responses": {
                    "utter_please_rephrase": [
                        {"text": "I\'m sorry, I didn\'t quite understand that. Could you rephrase?"}],
                    "utter_movietrailer": [{"custom": {"data": [
                        {"type": "video", "url": "https://www.youtube.com/watch?v=rUyrekdj5xs",
                         "children": [{"text": ""}]}, {"type": "paragraph", "children": [{"text": ""}]}],
                                                       "type": "video"}}],
                    "utter_movielocation": [{"custom": {"central bellandue": "godfather", "Jp nagar central": "CHUP"}}],
                    "utter_listmovie": [{"text": "PS1, CHUP, Brhamastra, Godfather"}],
                    "utter_greet": [{"text": "hi tell me"}],
                    "utter_default": [{"text": "Sorry I didn\'t get that. Can you rephrase?"}]},
                       "actions": ["ticket details", "kairon_two_stage_fallback", "call_api"], "forms": {},
                       "e2e_actions": []}, "version": "2.8.15"
        }

        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response_json['events'], [{'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response', 'value': {'response': 'utter_greet'}}])
        self.assertEqual(
            response_json['responses'],
            [{'text': None, 'buttons': [], 'elements': [], 'custom': {}, 'template': 'utter_greet',
             'response': 'utter_greet', 'image': None, 'attachment': None}
        ])

    def test_bot_response_action_empty_response_in_domain(self):
        action_name = 'utter_greet'
        bot = "5f50fd0a56b698ca10d35d2e"
        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {'bot': bot, 'firstname_slot': 'udit pandey', 'organization': 'digite',
                          'email_slot': 'pandey.udit867@gmail.com', 'phone': '9876543210'},
                "latest_message": {'text': 'hi', 'intent_ranking': [
                    {"name": "greet", "confidence": 0.853578245639801},
                    {"name": "goodbye", "confidence": 0.1504897326231},
                    {"name": "greet", "confidence": 0.138640150427818},
                    {"name": "affirm", "confidence": 0.0857767835259438},
                    {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                    {"name": "deny", "confidence": 0.069614589214325},
                    {"name": "bot_challenge", "confidence": 0.0664894133806229},
                    {"name": "faq_vaccine", "confidence": 0.062177762389183},
                    {"name": "faq_testing", "confidence": 0.0530692934989929},
                    {"name": "out_of_scope", "confidence": 0.0480506233870983}]},
                "latest_event_time": 1537645578.314389,
                "followup_action": "action_listen",
                "paused": False,
                "events": [
                    {"event": "action", "timestamp": 1594907100.12764, "name": "action_session_start", "policy": None,
                     "confidence": None}, {"event": "session_started", "timestamp": 1594907100.12765},
                    {"event": "action", "timestamp": 1594907100.12767, "name": "action_listen", "policy": None,
                     "confidence": None}, {"event": "user", "timestamp": 1594907100.42744, "text": "can't",
                                           "parse_data": {
                                               "intent": {"name": "test intent", "confidence": 0.253578245639801},
                                               "entities": [], "intent_ranking": [
                                                   {"name": "test intent", "confidence": 0.253578245639801},
                                                   {"name": "goodbye", "confidence": 0.1504897326231},
                                                   {"name": "greet", "confidence": 0.138640150427818},
                                                   {"name": "affirm", "confidence": 0.0857767835259438},
                                                   {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                   {"name": "deny", "confidence": 0.069614589214325},
                                                   {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                   {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                   {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                   {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                               "response_selector": {
                                                   "default": {"response": {"name": None, "confidence": 0},
                                                               "ranking": [], "full_retrieval_intent": None}},
                                               "text": "can't"}, "input_channel": None,
                                           "message_id": "bbd413bf5c834bf3b98e0da2373553b2", "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.4308, "name": "utter_test intent",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "bot", "timestamp": 1594907100.4308, "text": "will not = won\"t",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.43384, "name": "action_listen",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "user", "timestamp": 1594907117.04194, "text": "can\"t",
                     "parse_data": {"intent": {"name": "test intent", "confidence": 0.253578245639801}, "entities": [],
                                    "intent_ranking": [{"name": "test intent", "confidence": 0.253578245639801},
                                                       {"name": "goodbye", "confidence": 0.1504897326231},
                                                       {"name": "greet", "confidence": 0.138640150427818},
                                                       {"name": "affirm", "confidence": 0.0857767835259438},
                                                       {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                       {"name": "deny", "confidence": 0.069614589214325},
                                                       {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                       {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                       {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                       {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                    "response_selector": {
                                        "default": {"response": {"name": None, "confidence": 0}, "ranking": [],
                                                    "full_retrieval_intent": None}}, "text": "can\"t"},
                     "input_channel": None, "message_id": "e96e2a85de0748798748385503c65fb3", "metadata": {}},
                    {"event": "action", "timestamp": 1594907117.04547, "name": "utter_test intent",
                     "policy": "policy_1_TEDPolicy", "confidence": 0.978452920913696},
                    {"event": "bot", "timestamp": 1594907117.04548, "text": "can not = can't",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}}],
                "latest_input_channel": "rest",
                "active_loop": {},
                "latest_action": {},
            },
            "domain": {"config": {"store_entities_as_slots": True},
                       "session_config": {"session_expiration_time": 60, "carry_over_slots_to_new_session": True},
                       "intents": [{"greet": {"use_entities": []}}, {"list_movie": {"use_entities": []}},
                                   {"movie_poster": {"use_entities": []}}, {"movie_trailer": {"use_entities": []}},
                                   {"movie_location": {"use_entities": []}}, {"booking_link": {"use_entities": []}},
                                   {"send_details": {"use_entities": []}}, {"restart": {"use_entities": True}},
                                   {"back": {"use_entities": True}}, {"out_of_scope": {"use_entities": True}},
                                   {"session_start": {"use_entities": True}}, {"nlu_fallback": {"use_entities": True}},
                                   {"callapi": {"use_entities": []}}], "entities": ["bot", "kairon_action_response"],
                       "slots": {"bot": {"type": "rasa.shared.core.slots.AnySlot",
                                         "initial_value": "637f1b92df3b90588a30073e", "auto_fill": True,
                                         "influence_conversation": True},
                                 "kairon_action_response": {"type": "rasa.shared.core.slots.AnySlot",
                                                            "initial_value": None, "auto_fill": False,
                                                            "influence_conversation": False}}, "responses": {
                    "utter_please_rephrase": [
                        {"text": "I\'m sorry, I didn\'t quite understand that. Could you rephrase?"}],
                    "utter_movietrailer": [{"custom": {"data": [
                        {"type": "video", "url": "https://www.youtube.com/watch?v=rUyrekdj5xs",
                         "children": [{"text": ""}]}, {"type": "paragraph", "children": [{"text": ""}]}],
                                                       "type": "video"}}],
                    "utter_movielocation": [{"custom": {"central bellandue": "godfather", "Jp nagar central": "CHUP"}}],
                    "utter_listmovie": [{"text": "PS1, CHUP, Brhamastra, Godfather"}],
                    "utter_greet": [],
                    "utter_default": [{"text": "Sorry I didn\'t get that. Can you rephrase?"}]},
                       "actions": ["ticket details", "kairon_two_stage_fallback", "call_api"], "forms": {},
                       "e2e_actions": []}, "version": "2.8.15"
        }

        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response_json['events'], [{'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response', 'value': {'response': 'utter_greet'}}])
        self.assertEqual(response_json['responses'],
            [{'text': None, 'buttons': [], 'elements': [], 'custom': {}, 'template': 'utter_greet',
             'response': 'utter_greet', 'image': None, 'attachment': None}
        ])

    def test_bot_response_action_rephrase_enabled(self):
        action_name = 'utter_greet'
        bot = "5f50fd0a56b698ca10d35d2h"
        user = "test_user"
        BotSettings(rephrase_response=True, bot=bot, user=user).save()
        BotSecrets(secret_type=BotSecretType.gpt_key.value, value="uditpandey", bot=bot, user=user).save()
        gpt_prompt = open("./template/rephrase-prompt.txt").read()
        gpt_prompt = f"{gpt_prompt}hi\noutput:"
        gpt_response = {'id': 'cmpl-6Hh86Qkqq0PJih2YSl9JaNkPEuy4Y', 'object': 'text_completion', 'created': 1669675386,
                  'model': 'text-davinci-002', 'choices': [{
                                                               'text': "Greetings and welcome to kairon!!",
                                                               'index': 0, 'logprobs': None, 'finish_reason': 'stop'}],
                  'usage': {'prompt_tokens': 152, 'completion_tokens': 38, 'total_tokens': 81}}
        responses.add(
            "POST",
            Utility.environment["plugins"]["gpt"]["url"],
            status=200, json=gpt_response,
            match=[responses.matchers.json_params_matcher(
                {'model': 'text-davinci-003', 'prompt': gpt_prompt, 'temperature': 0.7,
                 'max_tokens': 152})],
        )

        responses.start()
        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {'bot': bot, 'firstname_slot': 'udit pandey', 'organization': 'digite',
                          'email_slot': 'pandey.udit867@gmail.com', 'phone': '9876543210'},
                "latest_message": {'text': 'hi', 'intent_ranking': [
                    {"name": "greet", "confidence": 0.853578245639801},
                    {"name": "goodbye", "confidence": 0.1504897326231},
                    {"name": "greet", "confidence": 0.138640150427818},
                    {"name": "affirm", "confidence": 0.0857767835259438},
                    {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                    {"name": "deny", "confidence": 0.069614589214325},
                    {"name": "bot_challenge", "confidence": 0.0664894133806229},
                    {"name": "faq_vaccine", "confidence": 0.062177762389183},
                    {"name": "faq_testing", "confidence": 0.0530692934989929},
                    {"name": "out_of_scope", "confidence": 0.0480506233870983}]},
                "latest_event_time": 1537645578.314389,
                "followup_action": "action_listen",
                "paused": False,
                "events": [
                    {"event": "action", "timestamp": 1594907100.12764, "name": "action_session_start", "policy": None,
                     "confidence": None}, {"event": "session_started", "timestamp": 1594907100.12765},
                    {"event": "action", "timestamp": 1594907100.12767, "name": "action_listen", "policy": None,
                     "confidence": None}, {"event": "user", "timestamp": 1594907100.42744, "text": "can't",
                                           "parse_data": {
                                               "intent": {"name": "test intent", "confidence": 0.253578245639801},
                                               "entities": [], "intent_ranking": [
                                                   {"name": "test intent", "confidence": 0.253578245639801},
                                                   {"name": "goodbye", "confidence": 0.1504897326231},
                                                   {"name": "greet", "confidence": 0.138640150427818},
                                                   {"name": "affirm", "confidence": 0.0857767835259438},
                                                   {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                   {"name": "deny", "confidence": 0.069614589214325},
                                                   {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                   {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                   {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                   {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                               "response_selector": {
                                                   "default": {"response": {"name": None, "confidence": 0},
                                                               "ranking": [], "full_retrieval_intent": None}},
                                               "text": "can't"}, "input_channel": None,
                                           "message_id": "bbd413bf5c834bf3b98e0da2373553b2", "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.4308, "name": "utter_test intent",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "bot", "timestamp": 1594907100.4308, "text": "will not = won\"t",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.43384, "name": "action_listen",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "user", "timestamp": 1594907117.04194, "text": "can\"t",
                     "parse_data": {"intent": {"name": "test intent", "confidence": 0.253578245639801}, "entities": [],
                                    "intent_ranking": [{"name": "test intent", "confidence": 0.253578245639801},
                                                       {"name": "goodbye", "confidence": 0.1504897326231},
                                                       {"name": "greet", "confidence": 0.138640150427818},
                                                       {"name": "affirm", "confidence": 0.0857767835259438},
                                                       {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                       {"name": "deny", "confidence": 0.069614589214325},
                                                       {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                       {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                       {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                       {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                    "response_selector": {
                                        "default": {"response": {"name": None, "confidence": 0}, "ranking": [],
                                                    "full_retrieval_intent": None}}, "text": "can\"t"},
                     "input_channel": None, "message_id": "e96e2a85de0748798748385503c65fb3", "metadata": {}},
                    {"event": "action", "timestamp": 1594907117.04547, "name": "utter_test intent",
                     "policy": "policy_1_TEDPolicy", "confidence": 0.978452920913696},
                    {"event": "bot", "timestamp": 1594907117.04548, "text": "can not = can't",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}}],
                "latest_input_channel": "rest",
                "active_loop": {},
                "latest_action": {},
            },
            "domain": {"config": {"store_entities_as_slots": True},
                       "session_config": {"session_expiration_time": 60, "carry_over_slots_to_new_session": True},
                       "intents": [{"greet": {"use_entities": []}}, {"list_movie": {"use_entities": []}},
                                   {"movie_poster": {"use_entities": []}}, {"movie_trailer": {"use_entities": []}},
                                   {"movie_location": {"use_entities": []}}, {"booking_link": {"use_entities": []}},
                                   {"send_details": {"use_entities": []}}, {"restart": {"use_entities": True}},
                                   {"back": {"use_entities": True}}, {"out_of_scope": {"use_entities": True}},
                                   {"session_start": {"use_entities": True}}, {"nlu_fallback": {"use_entities": True}},
                                   {"callapi": {"use_entities": []}}], "entities": ["bot", "kairon_action_response"],
                       "slots": {"bot": {"type": "rasa.shared.core.slots.AnySlot",
                                         "initial_value": "637f1b92df3b90588a30073e", "auto_fill": True,
                                         "influence_conversation": True},
                                 "kairon_action_response": {"type": "rasa.shared.core.slots.AnySlot",
                                                            "initial_value": None, "auto_fill": False,
                                                            "influence_conversation": False}}, "responses": {
                    "utter_please_rephrase": [
                        {"text": "I\'m sorry, I didn\'t quite understand that. Could you rephrase?"}],
                    "utter_movietrailer": [{"custom": {"data": [
                        {"type": "video", "url": "https://www.youtube.com/watch?v=rUyrekdj5xs",
                         "children": [{"text": ""}]}, {"type": "paragraph", "children": [{"text": ""}]}],
                                                       "type": "video"}}],
                    "utter_movielocation": [{"custom": {"central bellandue": "godfather", "Jp nagar central": "CHUP"}}],
                    "utter_listmovie": [{"text": "PS1, CHUP, Brhamastra, Godfather"}],
                    "utter_greet": [{"text": "hi"}],
                    "utter_default": [{"text": "Sorry I didn\'t get that. Can you rephrase?"}]},
                       "actions": ["ticket details", "kairon_two_stage_fallback", "call_api"], "forms": {},
                       "e2e_actions": []}, "version": "2.8.15"
        }

        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response_json['events'], [{'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response', 'value': {'text': "Greetings and welcome to kairon!!"}}])
        self.assertEqual(response_json['responses'],
            [{'text': "Greetings and welcome to kairon!!", 'buttons': [], 'elements': [], 'custom': {}, 'template': None,
             'response': None, 'image': None, 'attachment': None}
        ])
        responses.stop()
        responses.reset()

        request_object["domain"]["responses"]["utter_greet"] = [{"custom": {"type": "button", "text": "Greet"}}]
        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response_json['events'], [
            {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
             'value': {'response': 'utter_greet'}}])
        self.assertEqual(response_json['responses'],
                         [{'text': None, 'buttons': [], 'elements': [], 'custom': {}, 'template': 'utter_greet',
                           'response': 'utter_greet', 'image': None, 'attachment': None}
                          ])

    def test_bot_response_action_rephrase_failure(self):
        action_name = 'utter_greet'
        bot = "5f50fd0a56b698ca10d35d2i"
        user = "test_user"
        BotSettings(rephrase_response=True, bot=bot, user=user).save()
        secret = BotSecrets(secret_type=BotSecretType.gpt_key.value, value="uditpandey", bot=bot, user=user).save()
        gpt_prompt = open("./template/rephrase-prompt.txt").read()
        gpt_prompt = f"{gpt_prompt}hi\noutput:"
        gpt_response = {"error": {"message": "'100' is not of type 'integer' - 'max_tokens'", "type": "invalid_request_error", "param": None, "code": None} }
        responses.add(
            "POST",
            Utility.environment["plugins"]["gpt"]["url"],
            status=400,
            json=gpt_response,
            match=[responses.matchers.json_params_matcher({'model': 'text-davinci-003', 'prompt': gpt_prompt, 'temperature': 0.7, 'max_tokens': 152})],
        )

        responses.start()
        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {'bot': bot, 'firstname_slot': 'udit pandey', 'organization': 'digite',
                          'email_slot': 'pandey.udit867@gmail.com', 'phone': '9876543210'},
                "latest_message": {'text': 'hi', 'intent_ranking': [
                    {"name": "greet", "confidence": 0.853578245639801},
                    {"name": "goodbye", "confidence": 0.1504897326231},
                    {"name": "greet", "confidence": 0.138640150427818},
                    {"name": "affirm", "confidence": 0.0857767835259438},
                    {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                    {"name": "deny", "confidence": 0.069614589214325},
                    {"name": "bot_challenge", "confidence": 0.0664894133806229},
                    {"name": "faq_vaccine", "confidence": 0.062177762389183},
                    {"name": "faq_testing", "confidence": 0.0530692934989929},
                    {"name": "out_of_scope", "confidence": 0.0480506233870983}]},
                "latest_event_time": 1537645578.314389,
                "followup_action": "action_listen",
                "paused": False,
                "events": [
                    {"event": "action", "timestamp": 1594907100.12764, "name": "action_session_start", "policy": None,
                     "confidence": None}, {"event": "session_started", "timestamp": 1594907100.12765},
                    {"event": "action", "timestamp": 1594907100.12767, "name": "action_listen", "policy": None,
                     "confidence": None}, {"event": "user", "timestamp": 1594907100.42744, "text": "can't",
                                           "parse_data": {
                                               "intent": {"name": "test intent", "confidence": 0.253578245639801},
                                               "entities": [], "intent_ranking": [
                                                   {"name": "test intent", "confidence": 0.253578245639801},
                                                   {"name": "goodbye", "confidence": 0.1504897326231},
                                                   {"name": "greet", "confidence": 0.138640150427818},
                                                   {"name": "affirm", "confidence": 0.0857767835259438},
                                                   {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                   {"name": "deny", "confidence": 0.069614589214325},
                                                   {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                   {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                   {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                   {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                               "response_selector": {
                                                   "default": {"response": {"name": None, "confidence": 0},
                                                               "ranking": [], "full_retrieval_intent": None}},
                                               "text": "can't"}, "input_channel": None,
                                           "message_id": "bbd413bf5c834bf3b98e0da2373553b2", "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.4308, "name": "utter_test intent",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "bot", "timestamp": 1594907100.4308, "text": "will not = won\"t",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.43384, "name": "action_listen",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "user", "timestamp": 1594907117.04194, "text": "can\"t",
                     "parse_data": {"intent": {"name": "test intent", "confidence": 0.253578245639801}, "entities": [],
                                    "intent_ranking": [{"name": "test intent", "confidence": 0.253578245639801},
                                                       {"name": "goodbye", "confidence": 0.1504897326231},
                                                       {"name": "greet", "confidence": 0.138640150427818},
                                                       {"name": "affirm", "confidence": 0.0857767835259438},
                                                       {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                       {"name": "deny", "confidence": 0.069614589214325},
                                                       {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                       {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                       {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                       {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                    "response_selector": {
                                        "default": {"response": {"name": None, "confidence": 0}, "ranking": [],
                                                    "full_retrieval_intent": None}}, "text": "can\"t"},
                     "input_channel": None, "message_id": "e96e2a85de0748798748385503c65fb3", "metadata": {}},
                    {"event": "action", "timestamp": 1594907117.04547, "name": "utter_test intent",
                     "policy": "policy_1_TEDPolicy", "confidence": 0.978452920913696},
                    {"event": "bot", "timestamp": 1594907117.04548, "text": "can not = can't",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}}],
                "latest_input_channel": "rest",
                "active_loop": {},
                "latest_action": {},
            },
            "domain": {"config": {"store_entities_as_slots": True},
                       "session_config": {"session_expiration_time": 60, "carry_over_slots_to_new_session": True},
                       "intents": [{"greet": {"use_entities": []}}, {"list_movie": {"use_entities": []}},
                                   {"movie_poster": {"use_entities": []}}, {"movie_trailer": {"use_entities": []}},
                                   {"movie_location": {"use_entities": []}}, {"booking_link": {"use_entities": []}},
                                   {"send_details": {"use_entities": []}}, {"restart": {"use_entities": True}},
                                   {"back": {"use_entities": True}}, {"out_of_scope": {"use_entities": True}},
                                   {"session_start": {"use_entities": True}}, {"nlu_fallback": {"use_entities": True}},
                                   {"callapi": {"use_entities": []}}], "entities": ["bot", "kairon_action_response"],
                       "slots": {"bot": {"type": "rasa.shared.core.slots.AnySlot",
                                         "initial_value": "637f1b92df3b90588a30073e", "auto_fill": True,
                                         "influence_conversation": True},
                                 "kairon_action_response": {"type": "rasa.shared.core.slots.AnySlot",
                                                            "initial_value": None, "auto_fill": False,
                                                            "influence_conversation": False}}, "responses": {
                    "utter_please_rephrase": [
                        {"text": "I\'m sorry, I didn\'t quite understand that. Could you rephrase?"}],
                    "utter_movietrailer": [{"custom": {"data": [
                        {"type": "video", "url": "https://www.youtube.com/watch?v=rUyrekdj5xs",
                         "children": [{"text": ""}]}, {"type": "paragraph", "children": [{"text": ""}]}],
                                                       "type": "video"}}],
                    "utter_movielocation": [{"custom": {"central bellandue": "godfather", "Jp nagar central": "CHUP"}}],
                    "utter_listmovie": [{"text": "PS1, CHUP, Brhamastra, Godfather"}],
                    "utter_greet": [{"text": "hi"}],
                    "utter_default": [{"text": "Sorry I didn\'t get that. Can you rephrase?"}]},
                       "actions": ["ticket details", "kairon_two_stage_fallback", "call_api"], "forms": {},
                       "e2e_actions": []}, "version": "2.8.15"
        }

        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response_json['events'], [
            {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
             'value': {'response': 'utter_greet'}}])
        self.assertEqual(response_json['responses'],
                          [{'text': None, 'buttons': [], 'elements': [], 'custom': {}, 'template': 'utter_greet',
                            'response': 'utter_greet', 'image': None, 'attachment': None}
                           ])
        assert len(responses.calls._calls) == 1

        secret.value = ""
        secret.save()
        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response_json['events'], [
            {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
             'value': {'response': 'utter_greet'}}])
        self.assertEqual(response_json['responses'],
                          [{'text': None, 'buttons': [], 'elements': [], 'custom': {}, 'template': 'utter_greet',
                            'response': 'utter_greet', 'image': None, 'attachment': None}
                           ])
        assert len(responses.calls._calls) == 1
        responses.stop()
        responses.reset()
    
    def test_bot_response_action_failure(self):
        action_name = 'utter_greet'
        bot = "5f50fd0a56b698ca10d35d2j"
        user = "test_user"

        def __mock_error(*args, **kwargs):
            raise Exception("Failed to retrieve value")

        BotSettings(rephrase_response=True, bot=bot, user=user).save()
        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {'bot': bot, 'firstname_slot': 'udit pandey', 'organization': 'digite',
                          'email_slot': 'pandey.udit867@gmail.com', 'phone': '9876543210'},
                "latest_message": {'text': 'hi', 'intent_ranking': [
                    {"name": "greet", "confidence": 0.853578245639801},
                    {"name": "goodbye", "confidence": 0.1504897326231},
                    {"name": "greet", "confidence": 0.138640150427818},
                    {"name": "affirm", "confidence": 0.0857767835259438},
                    {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                    {"name": "deny", "confidence": 0.069614589214325},
                    {"name": "bot_challenge", "confidence": 0.0664894133806229},
                    {"name": "faq_vaccine", "confidence": 0.062177762389183},
                    {"name": "faq_testing", "confidence": 0.0530692934989929},
                    {"name": "out_of_scope", "confidence": 0.0480506233870983}]},
                "latest_event_time": 1537645578.314389,
                "followup_action": "action_listen",
                "paused": False,
                "events": [
                    {"event": "action", "timestamp": 1594907100.12764, "name": "action_session_start", "policy": None,
                     "confidence": None}, {"event": "session_started", "timestamp": 1594907100.12765},
                    {"event": "action", "timestamp": 1594907100.12767, "name": "action_listen", "policy": None,
                     "confidence": None}, {"event": "user", "timestamp": 1594907100.42744, "text": "can't",
                                           "parse_data": {
                                               "intent": {"name": "test intent", "confidence": 0.253578245639801},
                                               "entities": [], "intent_ranking": [
                                                   {"name": "test intent", "confidence": 0.253578245639801},
                                                   {"name": "goodbye", "confidence": 0.1504897326231},
                                                   {"name": "greet", "confidence": 0.138640150427818},
                                                   {"name": "affirm", "confidence": 0.0857767835259438},
                                                   {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                   {"name": "deny", "confidence": 0.069614589214325},
                                                   {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                   {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                   {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                   {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                               "response_selector": {
                                                   "default": {"response": {"name": None, "confidence": 0},
                                                               "ranking": [], "full_retrieval_intent": None}},
                                               "text": "can't"}, "input_channel": None,
                                           "message_id": "bbd413bf5c834bf3b98e0da2373553b2", "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.4308, "name": "utter_test intent",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "bot", "timestamp": 1594907100.4308, "text": "will not = won\"t",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.43384, "name": "action_listen",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "user", "timestamp": 1594907117.04194, "text": "can\"t",
                     "parse_data": {"intent": {"name": "test intent", "confidence": 0.253578245639801}, "entities": [],
                                    "intent_ranking": [{"name": "test intent", "confidence": 0.253578245639801},
                                                       {"name": "goodbye", "confidence": 0.1504897326231},
                                                       {"name": "greet", "confidence": 0.138640150427818},
                                                       {"name": "affirm", "confidence": 0.0857767835259438},
                                                       {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                       {"name": "deny", "confidence": 0.069614589214325},
                                                       {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                       {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                       {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                       {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                    "response_selector": {
                                        "default": {"response": {"name": None, "confidence": 0}, "ranking": [],
                                                    "full_retrieval_intent": None}}, "text": "can\"t"},
                     "input_channel": None, "message_id": "e96e2a85de0748798748385503c65fb3", "metadata": {}},
                    {"event": "action", "timestamp": 1594907117.04547, "name": "utter_test intent",
                     "policy": "policy_1_TEDPolicy", "confidence": 0.978452920913696},
                    {"event": "bot", "timestamp": 1594907117.04548, "text": "can not = can't",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}}],
                "latest_input_channel": "rest",
                "active_loop": {},
                "latest_action": {},
            },
            "domain": {"config": {"store_entities_as_slots": True},
                       "session_config": {"session_expiration_time": 60, "carry_over_slots_to_new_session": True},
                       "intents": [{"greet": {"use_entities": []}}, {"list_movie": {"use_entities": []}},
                                   {"movie_poster": {"use_entities": []}}, {"movie_trailer": {"use_entities": []}},
                                   {"movie_location": {"use_entities": []}}, {"booking_link": {"use_entities": []}},
                                   {"send_details": {"use_entities": []}}, {"restart": {"use_entities": True}},
                                   {"back": {"use_entities": True}}, {"out_of_scope": {"use_entities": True}},
                                   {"session_start": {"use_entities": True}}, {"nlu_fallback": {"use_entities": True}},
                                   {"callapi": {"use_entities": []}}], "entities": ["bot", "kairon_action_response"],
                       "slots": {"bot": {"type": "rasa.shared.core.slots.AnySlot",
                                         "initial_value": "637f1b92df3b90588a30073e", "auto_fill": True,
                                         "influence_conversation": True},
                                 "kairon_action_response": {"type": "rasa.shared.core.slots.AnySlot",
                                                            "initial_value": None, "auto_fill": False,
                                                            "influence_conversation": False}}, "responses": {
                    "utter_please_rephrase": [
                        {"text": "I\'m sorry, I didn\'t quite understand that. Could you rephrase?"}],
                    "utter_movietrailer": [{"custom": {"data": [
                        {"type": "video", "url": "https://www.youtube.com/watch?v=rUyrekdj5xs",
                         "children": [{"text": ""}]}, {"type": "paragraph", "children": [{"text": ""}]}],
                                                       "type": "video"}}],
                    "utter_movielocation": [{"custom": {"central bellandue": "godfather", "Jp nagar central": "CHUP"}}],
                    "utter_listmovie": [{"text": "PS1, CHUP, Brhamastra, Godfather"}],
                    "utter_greet": [{"text": "hi"}],
                    "utter_default": [{"text": "Sorry I didn\'t get that. Can you rephrase?"}]},
                       "actions": ["ticket details", "kairon_two_stage_fallback", "call_api"], "forms": {},
                       "e2e_actions": []}, "version": "2.8.15"
        }

        with patch.object(ActionUtility, "trigger_rephrase") as mock_utils:
            mock_utils.side_effect = __mock_error
            response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response_json['events'], [
            {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
             'value': {'response': 'utter_greet'}}])
        self.assertEqual(response_json['responses'],
                          [{'text': None, 'buttons': [], 'elements': [], 'custom': {}, 'template': 'utter_greet',
                            'response': 'utter_greet', 'image': None, 'attachment': None}
                           ])

    def test_action_handler_none(self):
        action_name = ""
        bot = ""

        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {"bot": bot, "to_email": "test@test.com", "organization": "digite"},
                "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]},
                "latest_event_time": 1537645578.314389,
                "followup_action": "action_listen",
                "paused": False,
                "events": [
                    {"event": "action", "timestamp": 1594907100.12764, "name": "action_session_start", "policy": None,
                     "confidence": None}, {"event": "session_started", "timestamp": 1594907100.12765},
                    {"event": "action", "timestamp": 1594907100.12767, "name": "action_listen", "policy": None,
                     "confidence": None}, {"event": "user", "timestamp": 1594907100.42744, "text": "can't",
                                           "parse_data": {
                                               "intent": {"name": "test intent", "confidence": 0.253578245639801},
                                               "entities": [], "intent_ranking": [
                                                   {"name": "test intent", "confidence": 0.253578245639801},
                                                   {"name": "goodbye", "confidence": 0.1504897326231},
                                                   {"name": "greet", "confidence": 0.138640150427818},
                                                   {"name": "affirm", "confidence": 0.0857767835259438},
                                                   {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                   {"name": "deny", "confidence": 0.069614589214325},
                                                   {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                   {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                   {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                   {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                               "response_selector": {
                                                   "default": {"response": {"name": None, "confidence": 0},
                                                               "ranking": [], "full_retrieval_intent": None}},
                                               "text": "can't"}, "input_channel": None,
                                           "message_id": "bbd413bf5c834bf3b98e0da2373553b2", "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.4308, "name": "utter_test intent",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "bot", "timestamp": 1594907100.4308, "text": "will not = won\"t",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.43384, "name": "action_listen",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "user", "timestamp": 1594907117.04194, "text": "can\"t",
                     "parse_data": {"intent": {"name": "test intent", "confidence": 0.253578245639801}, "entities": [],
                                    "intent_ranking": [{"name": "test intent", "confidence": 0.253578245639801},
                                                       {"name": "goodbye", "confidence": 0.1504897326231},
                                                       {"name": "greet", "confidence": 0.138640150427818},
                                                       {"name": "affirm", "confidence": 0.0857767835259438},
                                                       {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                       {"name": "deny", "confidence": 0.069614589214325},
                                                       {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                       {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                       {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                       {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                    "response_selector": {
                                        "default": {"response": {"name": None, "confidence": 0}, "ranking": [],
                                                    "full_retrieval_intent": None}}, "text": "can\"t"},
                     "input_channel": None, "message_id": "e96e2a85de0748798748385503c65fb3", "metadata": {}},
                    {"event": "action", "timestamp": 1594907117.04547, "name": "utter_test intent",
                     "policy": "policy_1_TEDPolicy", "confidence": 0.978452920913696},
                    {"event": "bot", "timestamp": 1594907117.04548, "text": "can not = can't",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}}],
                "latest_input_channel": "rest",
                "active_loop": {},
                "latest_action": {},
            },
            "domain": {
                "config": {},
                "session_config": {},
                "intents": [],
                "entities": [],
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e"},
                "responses": {},
                "actions": [],
                "forms": {},
                "e2e_actions": []
            },
            "version": "version"
        }

        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        response_json = json.loads(response.body.decode("utf8"))
        assert response_json is None

    def test_action_handler_exceptions(self):
        action_name = ""
        bot = ""

        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {"bot": bot, "to_email": "test@test.com", "organization": "digite"},
                "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]},
                "latest_event_time": 1537645578.314389,
                "followup_action": "action_listen",
                "paused": False,
                "events": [
                    {"event": "action", "timestamp": 1594907100.12764, "name": "action_session_start", "policy": None,
                     "confidence": None}, {"event": "session_started", "timestamp": 1594907100.12765},
                    {"event": "action", "timestamp": 1594907100.12767, "name": "action_listen", "policy": None,
                     "confidence": None}, {"event": "user", "timestamp": 1594907100.42744, "text": "can't",
                                           "parse_data": {
                                               "intent": {"name": "test intent", "confidence": 0.253578245639801},
                                               "entities": [], "intent_ranking": [
                                                   {"name": "test intent", "confidence": 0.253578245639801},
                                                   {"name": "goodbye", "confidence": 0.1504897326231},
                                                   {"name": "greet", "confidence": 0.138640150427818},
                                                   {"name": "affirm", "confidence": 0.0857767835259438},
                                                   {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                   {"name": "deny", "confidence": 0.069614589214325},
                                                   {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                   {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                   {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                   {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                               "response_selector": {
                                                   "default": {"response": {"name": None, "confidence": 0},
                                                               "ranking": [], "full_retrieval_intent": None}},
                                               "text": "can't"}, "input_channel": None,
                                           "message_id": "bbd413bf5c834bf3b98e0da2373553b2", "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.4308, "name": "utter_test intent",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "bot", "timestamp": 1594907100.4308, "text": "will not = won\"t",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}},
                    {"event": "action", "timestamp": 1594907100.43384, "name": "action_listen",
                     "policy": "policy_0_MemoizationPolicy", "confidence": 1},
                    {"event": "user", "timestamp": 1594907117.04194, "text": "can\"t",
                     "parse_data": {"intent": {"name": "test intent", "confidence": 0.253578245639801}, "entities": [],
                                    "intent_ranking": [{"name": "test intent", "confidence": 0.253578245639801},
                                                       {"name": "goodbye", "confidence": 0.1504897326231},
                                                       {"name": "greet", "confidence": 0.138640150427818},
                                                       {"name": "affirm", "confidence": 0.0857767835259438},
                                                       {"name": "smalltalk_human", "confidence": 0.0721133947372437},
                                                       {"name": "deny", "confidence": 0.069614589214325},
                                                       {"name": "bot_challenge", "confidence": 0.0664894133806229},
                                                       {"name": "faq_vaccine", "confidence": 0.062177762389183},
                                                       {"name": "faq_testing", "confidence": 0.0530692934989929},
                                                       {"name": "out_of_scope", "confidence": 0.0480506233870983}],
                                    "response_selector": {
                                        "default": {"response": {"name": None, "confidence": 0}, "ranking": [],
                                                    "full_retrieval_intent": None}}, "text": "can\"t"},
                     "input_channel": None, "message_id": "e96e2a85de0748798748385503c65fb3", "metadata": {}},
                    {"event": "action", "timestamp": 1594907117.04547, "name": "utter_test intent",
                     "policy": "policy_1_TEDPolicy", "confidence": 0.978452920913696},
                    {"event": "bot", "timestamp": 1594907117.04548, "text": "can not = can't",
                     "data": {"elements": None, "quick_replies": None, "buttons": None, "attachment": None,
                              "image": None, "custom": None}, "metadata": {}}],
                "latest_input_channel": "rest",
                "active_loop": {},
                "latest_action": {},
            },
            "domain": {
                "config": {},
                "session_config": {},
                "intents": [],
                "entities": [],
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e"},
                "responses": {},
                "actions": [],
                "forms": {},
                "e2e_actions": []
            },
            "version": "version"
        }

        async def mock_process_actions(*args, **kwargs):
            from rasa_sdk import ActionExecutionRejection
            raise ActionExecutionRejection("Action Execution Rejection")

        with patch('kairon.actions.handlers.action.ActionHandler.process_actions', mock_process_actions):
            response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
            response_json = json.loads(response.body.decode("utf8"))
            self.assertEqual(response_json, {'error': "Custom action 'Action Execution Rejection' rejected execution.",
                                            'action_name': 'Action Execution Rejection'})

        async def mock_process_actions(*args, **kwargs):
            from rasa_sdk.interfaces import ActionNotFoundException
            raise ActionNotFoundException("Action Not Found Exception")

        with patch('kairon.actions.handlers.action.ActionHandler.process_actions', mock_process_actions):
            response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
            response_json = json.loads(response.body.decode("utf8"))
            self.assertEqual(response_json, {'error': "No registered action found for name 'Action Not Found Exception'.",
                                             'action_name': 'Action Not Found Exception'})

    @patch("kairon.shared.llm.gpt3.openai.ChatCompletion.create", autospec=True)
    @patch("kairon.shared.llm.gpt3.openai.Embedding.create", autospec=True)
    @patch("kairon.shared.llm.gpt3.Utility.execute_http_request", autospec=True)
    def test_kairon_faq_response_action_with_bot_responses(self, mock_search, mock_embedding, mock_completion):
        from kairon.shared.llm.gpt3 import GPT3FAQEmbedding
        from openai.util import convert_to_openai_object
        from openai.openai_response import OpenAIResponse
        from uuid6 import uuid7

        action_name = KAIRON_FAQ_ACTION
        bot = "5f50fd0a56b698ca10d35d2k"
        user = "udit.pandey"
        value = "keyvalue"
        user_msg = "What kind of language is python?"
        bot_content = "Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected."
        generated_text = "Python is dynamically typed, garbage-collected, high level, general purpose programming."

        embedding = list(np.random.random(GPT3FAQEmbedding.__embedding__))
        mock_embedding.return_value = convert_to_openai_object(OpenAIResponse({'data': [{'embedding': embedding}]}, {}))
        mock_completion.return_value = convert_to_openai_object(
            OpenAIResponse({'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}, {}))
        mock_search.return_value = {
            'result': [{'id': uuid7().__str__(), 'score': 0.80, 'payload': {'content': bot_content}}]}
        Actions(name=action_name, type=ActionType.kairon_faq_action.value, bot=bot, user=user).save()
        BotSettings(enable_gpt_llm_faq=True, bot=bot, user=user).save()
        KaironFaqAction(bot=bot, user=user, use_bot_responses=True, num_bot_responses=2).save()
        BotSecrets(secret_type=BotSecretType.gpt_key.value, value=value, bot=bot, user=user).save()

        request_object = json.load(open("tests/testing_data/actions/action-request.json"))
        request_object["tracker"]["slots"]["bot"] = bot
        request_object["next_action"] = action_name
        request_object["tracker"]["sender_id"] = user
        request_object["tracker"]["latest_message"]['text'] = user_msg
        request_object['tracker']['events'] = [{"event": "bot", 'text': 'hello'},
                                               {'event': 'bot', "text": "how are you"}]

        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response_json['events'], [
            {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response', 'value': generated_text}])
        self.assertEqual(
            response_json['responses'],
            [{'text': generated_text, 'buttons': [], 'elements': [], 'custom': {}, 'template': None,
              'response': None, 'image': None, 'attachment': None}
             ])
        assert mock_completion.call_args.kwargs[
                   'messages'] == [
                   {"role": "system",
                    "content": DEFAULT_SYSTEM_PROMPT},
                   {"role": "user",
                    "content": f"{DEFAULT_CONTEXT_PROMPT} \n\nContext:\n{bot_content}\n\n Q: {user_msg}\n A:"},
                   {"role": "assistant",
                    "content": "hello\nhow are you\n"}
               ]

    @patch("kairon.shared.llm.gpt3.openai.ChatCompletion.create", autospec=True)
    @patch("kairon.shared.llm.gpt3.openai.Embedding.create", autospec=True)
    @patch("kairon.shared.llm.gpt3.Utility.execute_http_request", autospec=True)
    def test_kairon_faq_response_action_with_query_prompt(self, mock_search, mock_embedding, mock_completion):
        from kairon.shared.llm.gpt3 import GPT3FAQEmbedding
        from openai.util import convert_to_openai_object
        from openai.openai_response import OpenAIResponse
        from uuid6 import uuid7

        action_name = KAIRON_FAQ_ACTION
        bot = "5f50fd0a56b698ca10d35d2s"
        user = "udit.pandey"
        value = "keyvalue"
        user_msg = "What kind of language is python?"
        bot_content = "Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected."
        generated_text = "Python is dynamically typed, garbage-collected, high level, general purpose programming."
        query_prompt = "A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language."
        rephrased_query = "Explain python is called high level programming language in laymen terms?"

        def mock_completion_for_query_prompt(*args, **kwargs):
            return convert_to_openai_object(
            OpenAIResponse({'choices': [{'message': {'content': rephrased_query, 'role': 'assistant'}}]}, {}))

        def mock_completion_for_answer(*args, **kwargs):
            return convert_to_openai_object(
            OpenAIResponse({'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}, {}))

        mock_completion.side_effect = [mock_completion_for_query_prompt(), mock_completion_for_answer()]

        embedding = list(np.random.random(GPT3FAQEmbedding.__embedding__))
        mock_embedding.return_value = convert_to_openai_object(OpenAIResponse({'data': [{'embedding': embedding}]}, {}))
        mock_completion.return_value = convert_to_openai_object(
            OpenAIResponse({'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}, {}))
        mock_search.return_value = {
            'result': [{'id': uuid7().__str__(), 'score': 0.80, 'payload': {'content': bot_content}}]}
        Actions(name=action_name, type=ActionType.kairon_faq_action.value, bot=bot, user=user).save()
        BotSettings(enable_gpt_llm_faq=True, bot=bot, user=user).save()
        KaironFaqAction(bot=bot, user=user, use_query_prompt=True, query_prompt=query_prompt).save()
        BotSecrets(secret_type=BotSecretType.gpt_key.value, value=value, bot=bot, user=user).save()

        request_object = json.load(open("tests/testing_data/actions/action-request.json"))
        request_object["tracker"]["slots"]["bot"] = bot
        request_object["next_action"] = action_name
        request_object["tracker"]["sender_id"] = user
        request_object["tracker"]["latest_message"]['text'] = user_msg
        request_object['tracker']['events'] = [{"event": "bot", 'text': 'hello'},
                                               {'event': 'bot', "text": "how are you"}]

        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response_json['events'], [
            {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response', 'value': generated_text}])
        self.assertEqual(
            response_json['responses'],
            [{'text': generated_text, 'buttons': [], 'elements': [], 'custom': {}, 'template': None,
              'response': None, 'image': None, 'attachment': None}
             ])
        assert mock_completion.call_args.kwargs[
                   'messages'] == [
                   {"role": "system",
                    "content": DEFAULT_SYSTEM_PROMPT},
                   {"role": "user",
                    "content": f"{DEFAULT_CONTEXT_PROMPT} \n\nContext:\n{bot_content}\n\n Q: {rephrased_query}\n A:"}
               ]

    @patch("kairon.shared.llm.gpt3.openai.ChatCompletion.create", autospec=True)
    @patch("kairon.shared.llm.gpt3.openai.Embedding.create", autospec=True)
    @patch("kairon.shared.llm.gpt3.Utility.execute_http_request", autospec=True)
    def test_kairon_faq_response_action(self, mock_search, mock_embedding, mock_completion):
        from kairon.shared.llm.gpt3 import GPT3FAQEmbedding
        from openai.util import convert_to_openai_object
        from openai.openai_response import OpenAIResponse
        from uuid6 import uuid7

        action_name = GPT_LLM_FAQ
        bot = "5f50fd0a56b698ca10d35d2e"
        user = "udit.pandey"
        value = "keyvalue"
        user_msg = "What kind of language is python?"
        bot_content = "Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected."
        generated_text = "Python is dynamically typed, garbage-collected, high level, general purpose programming."
        embedding = list(np.random.random(GPT3FAQEmbedding.__embedding__))
        mock_embedding.return_value = convert_to_openai_object(OpenAIResponse({'data': [{'embedding': embedding}]}, {}))
        mock_completion.return_value = convert_to_openai_object(OpenAIResponse({'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}, {}))
        mock_search.return_value = {'result': [{'id': uuid7().__str__(), 'score':0.80, 'payload':{'content': bot_content}}]}
        Actions(name=action_name, type=ActionType.kairon_faq_action.value, bot=bot, user=user).save()
        BotSettings(enable_gpt_llm_faq=True, bot=bot, user=user).save()
        BotSecrets(secret_type=BotSecretType.gpt_key.value, value=value, bot=bot, user=user).save()

        request_object = json.load(open("tests/testing_data/actions/action-request.json"))
        request_object["tracker"]["slots"]["bot"] = bot
        request_object["next_action"] = action_name
        request_object["tracker"]["sender_id"] = user
        request_object["tracker"]["latest_message"]['text'] = user_msg

        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response_json['events'], [
            {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response', 'value': generated_text}])
        self.assertEqual(
            response_json['responses'],
            [{'text': generated_text, 'buttons': [], 'elements': [], 'custom': {}, 'template': None,
                'response': None, 'image': None, 'attachment': None}
             ])

    @patch("kairon.shared.llm.gpt3.openai.ChatCompletion.create", autospec=True)
    @patch("kairon.shared.llm.gpt3.openai.Embedding.create", autospec=True)
    @patch("kairon.shared.llm.gpt3.Utility.execute_http_request", autospec=True)
    def test_kairon_faq_response_action_failure(self, mock_search, mock_embedding, mock_completion):
        from kairon.shared.llm.gpt3 import GPT3FAQEmbedding
        from openai.util import convert_to_openai_object
        from openai.openai_response import OpenAIResponse
        from uuid6 import uuid7

        action_name = GPT_LLM_FAQ
        bot = "5f50fd0a56b698ca10d35d2ef"
        user = "udit.pandey"
        user_msg = "What kind of language is python?"
        bot_content = "Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected."
        generated_text = "I don't know."
        embedding = list(np.random.random(GPT3FAQEmbedding.__embedding__))
        mock_embedding.return_value = convert_to_openai_object(OpenAIResponse({'data': [{'embedding': embedding}]}, {}))
        mock_completion.return_value = convert_to_openai_object(OpenAIResponse({'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}, {}))
        mock_search.return_value = {'result': [{'id': uuid7().__str__(), 'score':0.80, 'payload':{'content': bot_content}}]}
        Actions(name=action_name, type=ActionType.kairon_faq_action.value, bot=bot, user=user).save()
        BotSettings(enable_gpt_llm_faq=True, bot=bot, user=user).save()

        request_object = json.load(open("tests/testing_data/actions/action-request.json"))
        request_object["tracker"]["slots"]["bot"] = bot
        request_object["next_action"] = action_name
        request_object["tracker"]["sender_id"] = user
        request_object["tracker"]["latest_message"]['text'] = user_msg

        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response_json['events'], [
            {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response', 'value': DEFAULT_NLU_FALLBACK_RESPONSE}])
        self.assertEqual(
            response_json['responses'],
            [{'text': DEFAULT_NLU_FALLBACK_RESPONSE, 'buttons': [], 'elements': [], 'custom': {}, 'template': None,
                'response': None, 'image': None, 'attachment': None}
             ])

    def test_kairon_faq_response_action_disabled(self):
        bot = "5f50fd0a56b698ca10d35d2efg"
        user = "udit.pandey"
        user_msg = "What kind of language is python?"
        action_name = GPT_LLM_FAQ

        request_object = json.load(open("tests/testing_data/actions/action-request.json"))
        request_object["tracker"]["slots"]["bot"] = bot
        request_object["next_action"] = action_name
        request_object["tracker"]["sender_id"] = user
        request_object["tracker"]["latest_message"]['text'] = user_msg
        Actions(name=action_name, type=ActionType.kairon_faq_action.value, bot=bot, user=user).save()
        BotSettings(enable_gpt_llm_faq=False, bot=bot, user=user).save()

        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response_json['events'], [
            {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
             'value': 'Faq feature is disabled for the bot! Please contact support.'}])
        self.assertEqual(
            response_json['responses'],
            [{'text': 'Faq feature is disabled for the bot! Please contact support.', 'buttons': [], 'elements': [],
              'custom': {}, 'template': None,
                'response': None, 'image': None, 'attachment': None}
             ])
        log = ActionServerLogs.objects(type=ActionType.kairon_faq_action.value, status="FAILURE").get()
        assert log['bot_response'] == 'Faq feature is disabled for the bot! Please contact support.'
        assert log['exception'] == 'Faq feature is disabled for the bot! Please contact support.'

    def test_kairon_faq_response_action_does_not_exists(self):
        bot = "5n80fd0a56b698ca10d35d2efg"
        user = "uditpandey"
        user_msg = "What kind of language is python?"
        action_name = GPT_LLM_FAQ

        request_object = json.load(open("tests/testing_data/actions/action-request.json"))
        request_object["tracker"]["slots"]["bot"] = bot
        request_object["next_action"] = action_name
        request_object["tracker"]["sender_id"] = user
        request_object["tracker"]["latest_message"]['text'] = user_msg

        response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
        response_json = json.loads(response.body.decode("utf8"))
        print(response_json)
        self.assertEqual(response.code, 200)
        self.assertEqual(len(response_json['events']), 0)
        self.assertEqual(len(response_json['responses']), 0)
