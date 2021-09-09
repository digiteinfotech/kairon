from tornado.test.testing_test import AsyncHTTPTestCase
from kairon.actions.server import make_app
from kairon.shared.actions.data_objects import HttpActionConfig, SlotSetAction
from kairon.shared.actions.exception import ActionFailure
from kairon.shared.actions.models import ActionType
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
        action_name = "test_run_with_get"
        action = HttpActionConfig(
            auth_token="",
            action_name=action_name,
            response="The value of ${a.b.3} in ${a.b.d.0} is ${a.b.d}",
            http_url="http://localhost:8081/mock",
            request_method="GET",
            params_list=None,
            bot="5f50fd0a56b698ca10d35d2e",
            user="user"
        )

        def _get_action(*arge, **kwargs):
            return action.to_mongo().to_dict(), ActionType.http_action.value

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
        with patch.object(ActionUtility, "get_action_config") as mocked:
            mocked.side_effect = _get_action
            response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
            response_json = json.loads(response.body.decode("utf8"))
            self.assertEqual(response.code, 200)
            self.assertEqual(len(response_json['events']), 1)
            self.assertEqual(len(response_json['responses']), 1)
            self.assertEqual(response_json['events'], [
                {'event': 'slot', 'timestamp': None, 'name': 'KAIRON_ACTION_RESPONSE',
                 'value': "The value of 2 in red is ['red', 'buggy', 'bumpers']"}])
            self.assertEqual(response_json['responses'][0]['text'],
                             "The value of 2 in red is ['red', 'buggy', 'bumpers']")

    def test_http_action_failed_execution(self):
        action_name = "test_run_with_get"
        action = HttpActionConfig(
            auth_token="",
            action_name=action_name,
            response="The value of ${a.b.3} in ${a.b.d.0} is ${a.b.d}",
            http_url="http://localhost:8082/mock",
            request_method="GET",
            params_list=None,
            bot="5f50fd0a56b698ca10d35d2e",
            user="user"
        )

        def _get_action(*arge, **kwargs):
            return action.to_mongo().to_dict(), ActionType.http_action.value

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
        with patch.object(ActionUtility, "get_action_config") as mocked:
            mocked.side_effect = _get_action
            response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
            response_json = json.loads(response.body.decode("utf8"))
            self.assertEqual(response.code, 200)
            self.assertEqual(len(response_json['events']), 1)
            self.assertEqual(len(response_json['responses']), 1)
            self.assertEqual(response_json['events'], [
                {'event': 'slot', 'timestamp': None, 'name': 'KAIRON_ACTION_RESPONSE',
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
        action = SlotSetAction(
            name=action_name,
            slot="location",
            type="from_value",
            value="Mumbai",
            bot="5f50fd0a56b698ca10d35d2e",
            user="user"
        )

        def _get_action(*arge, **kwargs):
            return action.to_mongo().to_dict(), ActionType.slot_set_action.value

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
        with patch.object(ActionUtility, "get_action_config") as mocked:
            mocked.side_effect = _get_action
            response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
            response_json = json.loads(response.body.decode("utf8"))
            self.assertEqual(response.code, 200)
            self.assertEqual(len(response_json['events']), 1)
            self.assertEqual(len(response_json['responses']), 0)
            self.assertEqual(response_json['events'],
                             [{'event': 'slot', 'timestamp': None, 'name': 'location', 'value': 'Mumbai'}])
            self.assertEqual(response_json['responses'], [])

    def test_slot_set_action_from_slot(self):
        action_name = "test_slot_set_from_slot"
        action = SlotSetAction(
            name=action_name,
            slot="location",
            type="from_slot",
            value="current_location",
            bot="5f50fd0a56b698ca10d35d2e",
            user="user"
        )

        def _get_action(*arge, **kwargs):
            return action.to_mongo().to_dict(), ActionType.slot_set_action.value

        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e", "location": None, 'current_location': 'Bengaluru'},
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
        with patch.object(ActionUtility, "get_action_config") as mocked:
            mocked.side_effect = _get_action
            response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
            response_json = json.loads(response.body.decode("utf8"))
            self.assertEqual(response.code, 200)
            self.assertEqual(len(response_json['events']), 1)
            self.assertEqual(len(response_json['responses']), 0)
            self.assertEqual(response_json['events'],
                             [{'event': 'slot', 'timestamp': None, 'name': 'location', 'value': 'Bengaluru'}])
            self.assertEqual(response_json['responses'], [])

    def test_slot_set_action_reset_slot(self):
        action_name = "test_slot_set_action_reset_slot"
        action = SlotSetAction(
            name=action_name,
            slot="location",
            type="reset_slot",
            value="current_location",
            bot="5f50fd0a56b698ca10d35d2e",
            user="user"
        )

        def _get_action(*arge, **kwargs):
            return action.to_mongo().to_dict(), ActionType.slot_set_action.value

        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {"bot": "5f50fd0a56b698ca10d35d2e", "location": 'Bengaluru', 'current_location': 'Bengaluru'},
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
        with patch.object(ActionUtility, "get_action_config") as mocked:
            mocked.side_effect = _get_action
            response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
            response_json = json.loads(response.body.decode("utf8"))
            self.assertEqual(response.code, 200)
            self.assertEqual(len(response_json['events']), 1)
            self.assertEqual(len(response_json['responses']), 0)
            self.assertEqual(response_json['events'],
                             [{'event': 'slot', 'timestamp': None, 'name': 'location', 'value': None}])
            self.assertEqual(response_json['responses'], [])

    def test_slot_set_action_from_slot_not_present(self):
        action_name = "test_slot_set_action_from_slot_not_present"
        action = SlotSetAction(
            name=action_name,
            slot="location",
            type="from_slot",
            value="current_location",
            bot="5f50fd0a56b698ca10d35d2e",
            user="user"
        )

        def _get_action(*arge, **kwargs):
            return action.to_mongo().to_dict(), ActionType.slot_set_action.value

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
        with patch.object(ActionUtility, "get_action_config") as mocked:
            mocked.side_effect = _get_action
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

        def _get_action(*arge, **kwargs):
            raise ActionFailure('Only http & slot set actions are compatible with action server')

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
