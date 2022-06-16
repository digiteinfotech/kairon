from jira import JIRAError
from tornado.test.testing_test import AsyncHTTPTestCase
from kairon.actions.server import make_app
from kairon.shared.actions.data_objects import HttpActionConfig, SlotSetAction, Actions, FormValidationAction, \
    EmailActionConfig, ActionServerLogs, GoogleSearchAction, JiraAction, ZendeskAction, PipedriveLeadsAction, SetSlots, \
    HubspotFormsAction
from kairon.shared.actions.exception import ActionFailure
from kairon.shared.actions.models import ActionType
from kairon.shared.data.data_objects import Slots
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
                {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
                 'value': "The value of 2 in red is ['red', 'buggy', 'bumpers']"}])
            self.assertEqual(response_json['responses'][0]['text'],
                             "The value of 2 in red is ['red', 'buggy', 'bumpers']")

    def test_http_action_failed_execution(self):
        action_name = "test_run_with_get"
        action = HttpActionConfig(
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
        action = SlotSetAction(
            name=action_name,
            set_slots=[SetSlots(name="location", type="from_value", value="Mumbai")],
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

    def test_slot_set_action_reset_slot(self):
        action_name = "test_slot_set_action_reset_slot"
        action = SlotSetAction(
            name=action_name,
            set_slots=[SetSlots(name="location", type="reset_slot", value="current_location"),
                       SetSlots(name="name", type="from_value", value="end_user"),
                       SetSlots(name="age", type="reset_slot")],
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
        with patch.object(ActionUtility, "get_action_config") as mocked:
            mocked.side_effect = _get_action
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
        action = SlotSetAction(
            name=action_name,
            set_slots=[SetSlots(name="location", type="from_slot", value="current_location")],
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

    @patch("kairon.shared.actions.utils.ActionUtility.get_action_config")
    @patch("kairon.shared.utils.SMTP", autospec=True)
    def test_email_action_execution(self, mock_smtp, mock_action):
        Utility.email_conf['email']['templates']['conversation'] = open('template/emails/conversation.html', 'rb').read().decode()
        Utility.email_conf['email']['templates']['bot_msg_conversation'] = open('template/emails/bot_msg_conversation.html', 'rb').read().decode()
        Utility.email_conf['email']['templates']['user_msg_conversation'] = open('template/emails/user_msg_conversation.html', 'rb').read().decode()

        action_name = "test_run_email_action"
        action = EmailActionConfig(
                action_name=action_name,
                smtp_url="test.localhost",
                smtp_port=293,
                smtp_password="test",
                from_email="test@demo.com",
                subject="test",
                to_email=["test@test.com"],
                response="Email Triggered",
                bot="bot",
                user="user"
            )

        def _get_action(*arge, **kwargs):
            return action.to_mongo().to_dict(), ActionType.email_action.value

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
        assert host == action.smtp_url
        assert port == action.smtp_port
        name, args, kwargs = mock_smtp.method_calls.pop(0)
        assert name == '().login'
        assert {} == kwargs

        from_email, password = args
        assert from_email == action.from_email
        assert password == action.smtp_password

        name, args, kwargs = mock_smtp.method_calls.pop(0)
        assert name == '().sendmail'
        assert {} == kwargs

        assert args[0] == action.from_email
        assert args[1] == ["test@test.com"]
        assert str(args[2]).__contains__(action.subject)
        assert str(args[2]).__contains__("Content-Type: text/html")
        assert str(args[2]).__contains__("Subject: default test")

    @patch("kairon.shared.actions.utils.ActionUtility.get_action_config")
    def test_email_action_failed_execution(self, mock_action):
        action_name = "test_run_email_action"
        action = EmailActionConfig(
            action_name=action_name,
            smtp_url="test.localhost",
            smtp_port=293,
            smtp_password="test",
            from_email="test@demo.com",
            subject="test",
            to_email="test@test.com",
            response="Email Triggered",
            bot="bot",
            user="user"
        )

        def _get_action(*arge, **kwargs):
            return action.to_mongo().to_dict(), ActionType.email_action.value

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
        GoogleSearchAction(name=action_name, api_key='1234567890',
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

    def test_process_google_search_action_failure(self):
        action_name = "custom_search_failure"
        bot = "5f50fd0a56b698ca10d35d2e"
        user = 'test_user'
        Actions(name=action_name, type=ActionType.google_search_action.value, bot=bot, user='test_user').save()
        GoogleSearchAction(name=action_name, api_key='1234567890',
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
        GoogleSearchAction(name=action_name, api_key='1234567890',
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
                api_token='ASDFGHJKL', project_key='HEL', issue_type='Bug', summary='fallback',
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
                api_token='ASDFGHJKL', project_key='HEL', issue_type='Bug', summary='fallback',
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
                          api_token='1234567890', subject='new ticket', response='ticket created',
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
                          api_token='1234567890', subject='new ticket', response='ticket created',
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
            PipedriveLeadsAction(name=action_name, domain='https://digite751.pipedrive.com/', api_token='1234567890',
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

    def test_process_pipedrive_leads_action_failure(self):
        action_name = "test_process_pipedrive_leads_action_failure"
        bot = "5f50fd0a56b698ca10d35d2e"
        user = 'test_user'

        Actions(name=action_name, type=ActionType.pipedrive_leads_action.value, bot=bot, user='test_user').save()
        with patch('pipedrive.client.Client'):
            metadata = {'name': 'name', 'org_name': 'organization', 'email': 'email', 'phone': 'phone'}
            PipedriveLeadsAction(name=action_name, domain='https://digite751.pipedrive.com/', api_token='1234567890',
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
            json={'inlineMessage': 'Thankyou for the submission'}
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