from tornado.test.testing_test import AsyncHTTPTestCase
from kairon.actions.server import make_app
from kairon.shared.actions.data_objects import HttpActionConfig, SlotSetAction, Actions, FormValidations
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

    def test_form_validation_action_valid_slot_value(self):
        action_name = "validate_location"
        bot = '5f50fd0a56b698ca10d35d2e'
        user = 'test_user'
        slot = 'location'
        semantic_expression = {'and': [{'and': [{'operator': 'is_in', 'value': ['Mumbai', 'Bangalore']},
                                                {'operator': 'starts_with', 'value': 'M'},
                                                {'operator': 'ends_with', 'value': 'i'},
                                                ]},
                                       {'or': [{'operator': 'has_length_greater_than', 'value': 20},
                                               {'operator': 'has_no_whitespace'},
                                               {'operator': 'matches_regex', 'value': '^[e]+.*[e]$'}]}]}
        Actions(name=action_name, type=ActionType.form_validation_action.value, bot=bot, user=user).save()
        FormValidations(name=action_name, slot=slot, validation_semantic=semantic_expression,
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

    def test_form_validation_action_valid_slot_value_with_utterance(self):
        action_name = "validate_user"
        bot = '5f50fd0a56b698ca10d35d2e'
        user = 'test_user'
        slot = 'user_id'
        semantic_expression = {'and': [{'and': [{'operator': 'is_an_email_address'},
                                                {'operator': 'is_not_null_or_empty'},
                                                {'operator': 'ends_with', 'value': '.com'},
                                                ]},
                                       {'or': [{'operator': 'has_length_greater_than', 'value': 4},
                                               {'operator': 'has_no_whitespace'},
                                               ]}]}
        Actions(name=action_name, type=ActionType.form_validation_action.value, bot=bot, user=user).save()
        FormValidations(name=action_name, slot='location', validation_semantic=semantic_expression,
                        bot=bot, user=user).save()
        FormValidations(name=action_name, slot=slot, validation_semantic=semantic_expression,
                        bot=bot, user=user,
                        utter_msg_on_valid='that is great!').save()
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
        self.assertEqual(response_json, {
            'events': [{'event': 'slot', 'timestamp': None, 'name': 'user_id', 'value': 'pandey.udit867@gmail.com'}],
            'responses': [
                {'text': 'that is great!', 'buttons': [], 'elements': [], 'custom': {}, 'template': None, 'image': None,
                 'attachment': None}]})

    def test_form_validation_action_invalid_slot_value(self):
        action_name = "validate_form_with_3_validations"
        bot = '5f50fd0a56b698ca10d35d2e'
        user = 'test_user'
        slot = 'current_location'
        semantic_expression = {'and': [{'and': [{'operator': 'is_in', 'value': ['Mumbai', 'Bangalore']},
                                                {'operator': 'starts_with', 'value': 'M'},
                                                {'operator': 'ends_with', 'value': 'i'},
                                                ]},
                                       {'or': [{'operator': 'has_length_greater_than', 'value': 20},
                                               {'operator': 'has_no_whitespace'},
                                               {'operator': 'matches_regex', 'value': '^[e]+.*[e]$'}]}]}
        Actions(name=action_name, type=ActionType.form_validation_action.value, bot=bot, user=user).save()
        FormValidations(name=action_name, slot='name', validation_semantic=semantic_expression,
                        bot=bot, user=user).save().to_mongo().to_dict()
        FormValidations(name=action_name, slot='user_id', validation_semantic=semantic_expression,
                        bot=bot, user=user, utter_msg_on_valid='that is great!').save().to_mongo().to_dict()
        FormValidations(name=action_name, slot=slot, validation_semantic=semantic_expression,
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
                                                {'operator': 'ends_with', 'value': '.com'},
                                                ]},
                                       {'or': [{'operator': 'has_length_greater_than', 'value': 4},
                                               {'operator': 'has_no_whitespace'},
                                               ]}]}
        Actions(name=action_name, type=ActionType.form_validation_action.value, bot=bot, user=user).save()
        FormValidations(name=action_name, slot='some_slot', validation_semantic=semantic_expression,
                        bot=bot, user=user).save().to_mongo().to_dict()
        FormValidations(name=action_name, slot=slot, validation_semantic=semantic_expression,
                        bot=bot, user=user, utter_msg_on_valid='that is great!',
                        utter_msg_on_invalid='Invalid value. Please type again!').save().to_mongo().to_dict()
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
        self.assertEqual(response_json, {
            'events': [{'event': 'slot', 'timestamp': None, 'name': 'profession', 'value': None}],
            'responses': [
                {'text': 'Invalid value. Please type again!', 'buttons': [], 'elements': [], 'custom': {},
                 'template': None, 'image': None,
                 'attachment': None}]})

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

    def test_form_validation_action_slot_type_not_found(self):
        action_name = "validate_hotel_booking"
        bot = '5f50fd0a56b698ca10d35d2e'
        user = 'test_user'
        slot = 'reservation_id'
        Actions(name=action_name, type=ActionType.form_validation_action.value, bot=bot, user=user).save()
        FormValidations(name=action_name, slot=slot, validation_semantic={},
                        bot=bot, user=user, utter_msg_on_valid='that is great!',
                        utter_msg_on_invalid='Invalid value. Please type again!').save()
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
