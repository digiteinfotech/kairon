from tornado.test.testing_test import AsyncHTTPTestCase
from kairon.actions.server import make_app
from kairon.shared.actions.data_objects import HttpActionConfig
from kairon.shared.actions.utils import ActionUtility
import json
import responses
from mock import patch
import os
import pytest
os.environ["system_file"] = "./tests/testing_data/system.yaml"
os.environ['ASYNC_TEST_TIMEOUT'] = "360"

ActionUtility.connect_db()


class TestActionServer(AsyncHTTPTestCase):

    def get_app(self):
        return make_app()

    def test_index(self):
        response = self.fetch("/")
        self.assertEqual(response.code, 200)
        self.assertEqual(response.body.decode("utf8"), 'Kairon Action Server Running')

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
            return action.to_mongo().to_dict()

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
        with patch.object(ActionUtility, "get_http_action_config") as mocked:
            mocked.side_effect = _get_action
            response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
            response_json = json.loads(response.body.decode("utf8"))
            self.assertEqual(response.code, 200)
            self.assertEqual(len(response_json['events']), 1)
            self.assertEqual(len(response_json['responses']), 1)
            self.assertEqual(response_json['responses'][0]['text'], "The value of 2 in red is ['red', 'buggy', 'bumpers']")

    def test_http_action_failed_execution(self):
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
            return action.to_mongo().to_dict()

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
        with patch.object(ActionUtility, "get_http_action_config") as mocked:
            mocked.side_effect = _get_action
            response = self.fetch("/webhook", method="POST", body=json.dumps(request_object).encode('utf-8'))
            response_json = json.loads(response.body.decode("utf8"))
            self.assertEqual(response.code, 200)
            self.assertEqual(len(response_json['events']), 1)
            self.assertEqual(len(response_json['responses']), 1)
            self.assertEqual(response_json['responses'][0]['text'], "I have failed to process your request")
