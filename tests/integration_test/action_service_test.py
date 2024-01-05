import asyncio
import json
import os

import mock
import numpy as np
import pytest
import responses
from fastapi.testclient import TestClient
from jira import JIRAError
from mock import patch
from mongoengine import connect

from kairon.actions.definitions.set_slot import ActionSetSlot
from kairon.actions.server import action
from kairon.shared.actions.data_objects import HttpActionConfig, SlotSetAction, Actions, FormValidationAction, \
    EmailActionConfig, ActionServerLogs, GoogleSearchAction, JiraAction, ZendeskAction, PipedriveLeadsAction, SetSlots, \
    HubspotFormsAction, HttpActionResponse, HttpActionRequestBody, SetSlotsFromResponse, CustomActionRequestParameters, \
    KaironTwoStageFallbackAction, TwoStageFallbackTextualRecommendations, RazorpayAction, PromptAction, FormSlotSet, \
    DatabaseAction, DbQuery, PyscriptActionConfig, WebSearchAction, UserQuestion
from kairon.shared.actions.models import ActionType, ActionParameterType, DispatchType, DbActionOperationType
from kairon.shared.actions.utils import ActionUtility
from kairon.shared.admin.constants import BotSecretType
from kairon.shared.admin.data_objects import BotSecrets
from kairon.shared.constants import KAIRON_USER_MSG_ENTITY, FORM_SLOT_SET_TYPE
from kairon.shared.data.constant import KAIRON_TWO_STAGE_FALLBACK, FALLBACK_MESSAGE, GPT_LLM_FAQ, \
    DEFAULT_NLU_FALLBACK_RESPONSE
from kairon.shared.data.data_objects import Slots, KeyVault, BotSettings, LLMSettings
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.llm.clients.gpt3 import GPT3Resources
from kairon.shared.llm.gpt3 import GPT3FAQEmbedding
from kairon.shared.utils import Utility

os.environ['ASYNC_TEST_TIMEOUT'] = "360"
os.environ["system_file"] = "./tests/testing_data/system.yaml"

client = TestClient(action)


@pytest.fixture(autouse=True, scope='class')
def setup():
    os.environ["system_file"] = "./tests/testing_data/system.yaml"
    Utility.load_environment()
    connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))


def test_index():
    response = client.get("/")
    result = response.json()
    assert response.status_code == 200
    assert result["message"] == "Kairon Action Server Up and Running"


@responses.activate
def test_pyscript_action_execution():
    import textwrap

    action_name = "test_pyscript_action_execution"
    Actions(name=action_name, type=ActionType.pyscript_action.value,
            bot="5f50fd0a56b698ca10d35d2z", user="user").save()
    script = """
    numbers = [1, 2, 3, 4, 5]
    total = 0
    for i in numbers:
        total += i
    print(total)
    """
    script = textwrap.dedent(script)
    PyscriptActionConfig(
        name=action_name,
        source_code=script,
        bot="5f50fd0a56b698ca10d35d2z",
        user="user"
    ).save()

    responses.add(
        "POST", Utility.environment['evaluator']['pyscript']['url'],
        json={"success": True, "data": {"bot_response": {'numbers': [1, 2, 3, 4, 5], 'total': 15, 'i': 5},
                                        "slots": {"location": "Bangalore", "langauge": "Kannada"}, "type": "json"},
              "message": None, "error_code": 0},
        match=[responses.matchers.json_params_matcher(
            {'source_code': script,
             'predefined_objects': {'sender_id': 'default', 'user_message': 'get intents',
                                    'slot': {'bot': '5f50fd0a56b698ca10d35d2z', 'location': 'Bangalore',
                                             'langauge': 'Kannada'}, 'intent': 'pyscript_action', 'chat_log': [],
                                    'key_vault': {}, 'kairon_user_msg': None, 'session_started': None}})]
    )

    request_object = {
        "next_action": action_name,
        "tracker": {
            "sender_id": "default",
            "conversation_id": "default",
            "slots": {"bot": "5f50fd0a56b698ca10d35d2z", "location": "Bangalore", "langauge": "Kannada"},
            "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'pyscript_action'}]},
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
            "slots": {"bot": "5f50fd0a56b698ca10d35d2z"},
            "responses": {},
            "actions": [],
            "forms": {},
            "e2e_actions": []
        },
        "version": "version"
    }
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert len(response_json['events']) == 3
    assert len(response_json['responses']) == 1
    assert response_json['events'] == [
        {'event': 'slot', 'timestamp': None, 'name': 'location', 'value': 'Bangalore'},
        {'event': 'slot', 'timestamp': None, 'name': 'langauge', 'value': 'Kannada'},
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
         'value': {'numbers': [1, 2, 3, 4, 5], 'total': 15, 'i': 5}}]
    assert response_json['responses'][0]['custom'] == {'numbers': [1, 2, 3, 4, 5], 'total': 15, 'i': 5}


@responses.activate
def test_pyscript_action_execution_with_bot_response_none():
    import textwrap

    action_name = "test_pyscript_action_execution_with_bot_response_none"
    Actions(name=action_name, type=ActionType.pyscript_action.value,
            bot="5f50fd0a56b698ca10d35d2z", user="user").save()
    script = """
    numbers = [1, 2, 3, 4, 5]
    total = 0
    for i in numbers:
        total += i
    print(total)
    """
    script = textwrap.dedent(script)
    PyscriptActionConfig(
        name=action_name,
        source_code=script,
        bot="5f50fd0a56b698ca10d35d2z",
        dispatch_response=True,
        user="user"
    ).save()

    responses.add(
        "POST", Utility.environment['evaluator']['pyscript']['url'],
        json={"success": True, "data": {"bot_response": None,
                                        "slots": {"location": "Bangalore", "langauge": "Kannada"}},
              "message": None, "error_code": 0},
        match=[responses.matchers.json_params_matcher(
            {'source_code': script,
             'predefined_objects': {'sender_id': 'default', 'user_message': 'get intents',
                                    'slot': {'bot': '5f50fd0a56b698ca10d35d2z', 'location': 'Bangalore',
                                             'langauge': 'Kannada'}, 'intent': 'pyscript_action', 'chat_log': [],
                                    'key_vault': {}, 'kairon_user_msg': None, 'session_started': None}})]
    )

    request_object = {
        "next_action": action_name,
        "tracker": {
            "sender_id": "default",
            "conversation_id": "default",
            "slots": {"bot": "5f50fd0a56b698ca10d35d2z", "location": "Bangalore", "langauge": "Kannada"},
            "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'pyscript_action'}]},
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
            "slots": {"bot": "5f50fd0a56b698ca10d35d2z"},
            "responses": {},
            "actions": [],
            "forms": {},
            "e2e_actions": []
        },
        "version": "version"
    }
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert len(response_json['events']) == 3
    assert len(response_json['responses']) == 0
    assert response_json['events'] == [
        {'event': 'slot', 'timestamp': None, 'name': 'location', 'value': 'Bangalore'},
        {'event': 'slot', 'timestamp': None, 'name': 'langauge', 'value': 'Kannada'},
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response', 'value': None}]


@responses.activate
def test_pyscript_action_execution_with_type_json_bot_response_none():
    import textwrap

    action_name = "test_pyscript_action_execution_with_type_json_bot_response_none"
    Actions(name=action_name, type=ActionType.pyscript_action.value,
            bot="5f50fd0a56b698ca10d35d2z", user="user").save()
    script = """
    numbers = [1, 2, 3, 4, 5]
    total = 0
    for i in numbers:
        total += i
    print(total)
    """
    script = textwrap.dedent(script)
    PyscriptActionConfig(
        name=action_name,
        source_code=script,
        bot="5f50fd0a56b698ca10d35d2z",
        dispatch_response=True,
        user="user"
    ).save()

    responses.add(
        "POST", Utility.environment['evaluator']['pyscript']['url'],
        json={"success": True, "data": {"bot_response": None,
                                        "slots": {"location": "Bangalore", "langauge": "Kannada"}, "type": "json"},
              "message": None, "error_code": 0},
        match=[responses.matchers.json_params_matcher(
            {'source_code': script,
             'predefined_objects': {'sender_id': 'default', 'user_message': 'get intents',
                                    'slot': {'bot': '5f50fd0a56b698ca10d35d2z', 'location': 'Bangalore',
                                             'langauge': 'Kannada'}, 'intent': 'pyscript_action', 'chat_log': [],
                                    'key_vault': {}, 'kairon_user_msg': None, 'session_started': None}})]
    )

    request_object = {
        "next_action": action_name,
        "tracker": {
            "sender_id": "default",
            "conversation_id": "default",
            "slots": {"bot": "5f50fd0a56b698ca10d35d2z", "location": "Bangalore", "langauge": "Kannada"},
            "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'pyscript_action'}]},
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
            "slots": {"bot": "5f50fd0a56b698ca10d35d2z"},
            "responses": {},
            "actions": [],
            "forms": {},
            "e2e_actions": []
        },
        "version": "version"
    }
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert len(response_json['events']) == 3
    assert len(response_json['responses']) == 0
    assert response_json['events'] == [
        {'event': 'slot', 'timestamp': None, 'name': 'location', 'value': 'Bangalore'},
        {'event': 'slot', 'timestamp': None, 'name': 'langauge', 'value': 'Kannada'},
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response', 'value': None}]


@responses.activate
def test_pyscript_action_execution_with_type_json_bot_response_str():
    import textwrap

    action_name = "test_pyscript_action_execution_with_type_json_bot_response_str"
    Actions(name=action_name, type=ActionType.pyscript_action.value,
            bot="5f50fd0a56b698ca10d35d2z", user="user").save()
    script = """
    numbers = [1, 2, 3, 4, 5]
    total = 0
    for i in numbers:
        total += i
    print(total)
    """
    script = textwrap.dedent(script)
    PyscriptActionConfig(
        name=action_name,
        source_code=script,
        bot="5f50fd0a56b698ca10d35d2z",
        dispatch_response=True,
        user="user"
    ).save()

    responses.add(
        "POST", Utility.environment['evaluator']['pyscript']['url'],
        json={"success": True, "data": {"bot_response": "Successfully Evaluated the pyscript",
                                        "slots": {"location": "Bangalore", "langauge": "Kannada"}, "type": "json"},
              "message": None, "error_code": 0},
        match=[responses.matchers.json_params_matcher(
            {'source_code': script,
             'predefined_objects': {'sender_id': 'default', 'user_message': 'get intents',
                                    'slot': {'bot': '5f50fd0a56b698ca10d35d2z', 'location': 'Bangalore',
                                             'langauge': 'Kannada'}, 'intent': 'pyscript_action', 'chat_log': [],
                                    'key_vault': {}, 'kairon_user_msg': None, 'session_started': None}})]
    )

    request_object = {
        "next_action": action_name,
        "tracker": {
            "sender_id": "default",
            "conversation_id": "default",
            "slots": {"bot": "5f50fd0a56b698ca10d35d2z", "location": "Bangalore", "langauge": "Kannada"},
            "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'pyscript_action'}]},
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
            "slots": {"bot": "5f50fd0a56b698ca10d35d2z"},
            "responses": {},
            "actions": [],
            "forms": {},
            "e2e_actions": []
        },
        "version": "version"
    }
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert len(response_json['events']) == 3
    assert len(response_json['responses']) == 1
    assert response_json['events'] == [
        {'event': 'slot', 'timestamp': None, 'name': 'location', 'value': 'Bangalore'},
        {'event': 'slot', 'timestamp': None, 'name': 'langauge', 'value': 'Kannada'},
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
         'value': "Successfully Evaluated the pyscript"}]
    assert response_json['responses'][0]['text'] == "Successfully Evaluated the pyscript"


@responses.activate
def test_pyscript_action_execution_with_other_type():
    import textwrap

    action_name = "test_pyscript_action_execution_with_other_type"
    Actions(name=action_name, type=ActionType.pyscript_action.value,
            bot="5f50fd0a56b698ca10d35d2z", user="user").save()
    script = """
    numbers = [1, 2, 3, 4, 5]
    total = 0
    for i in numbers:
        total += i
    print(total)
    """
    script = textwrap.dedent(script)
    PyscriptActionConfig(
        name=action_name,
        source_code=script,
        bot="5f50fd0a56b698ca10d35d2z",
        dispatch_response=True,
        user="user"
    ).save()

    responses.add(
        "POST", Utility.environment['evaluator']['pyscript']['url'],
        json={"success": True, "data": {"bot_response": "Successfully Evaluated the pyscript",
                                        "slots": {"location": "Bangalore", "langauge": "Kannada"}, "type": "data"},
              "message": None, "error_code": 0},
        match=[responses.matchers.json_params_matcher(
            {'source_code': script,
             'predefined_objects': {'sender_id': 'default', 'user_message': 'get intents',
                                    'slot': {'bot': '5f50fd0a56b698ca10d35d2z', 'location': 'Bangalore',
                                             'langauge': 'Kannada'}, 'intent': 'pyscript_action', 'chat_log': [],
                                    'key_vault': {}, 'kairon_user_msg': None, 'session_started': None}})]
    )

    request_object = {
        "next_action": action_name,
        "tracker": {
            "sender_id": "default",
            "conversation_id": "default",
            "slots": {"bot": "5f50fd0a56b698ca10d35d2z", "location": "Bangalore", "langauge": "Kannada"},
            "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'pyscript_action'}]},
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
            "slots": {"bot": "5f50fd0a56b698ca10d35d2z"},
            "responses": {},
            "actions": [],
            "forms": {},
            "e2e_actions": []
        },
        "version": "version"
    }
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert len(response_json['events']) == 3
    assert len(response_json['responses']) == 1
    assert response_json['events'] == [
        {'event': 'slot', 'timestamp': None, 'name': 'location', 'value': 'Bangalore'},
        {'event': 'slot', 'timestamp': None, 'name': 'langauge', 'value': 'Kannada'},
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
         'value': "Successfully Evaluated the pyscript"}]
    assert response_json['responses'][0]['text'] == "Successfully Evaluated the pyscript"


@responses.activate
def test_pyscript_action_execution_with_slots_not_dict_type():
    import textwrap

    action_name = "test_pyscript_action_execution_with_slots_not_dict_type"
    Actions(name=action_name, type=ActionType.pyscript_action.value,
            bot="5f50fd0a56b698ca10d35d2z", user="user").save()
    script = """
    numbers = [1, 2, 3, 4, 5]
    total = 0
    for i in numbers:
        total += i
    print(total)
    """
    script = textwrap.dedent(script)
    PyscriptActionConfig(
        name=action_name,
        source_code=script,
        bot="5f50fd0a56b698ca10d35d2z",
        user="user"
    ).save()

    responses.add(
        "POST", Utility.environment['evaluator']['pyscript']['url'],
        json={"success": True, "data": {"bot_response": "Successfully Evaluated the pyscript",
                                        "slots": "invalid slots values"}, "message": None, "error_code": 0},
        match=[responses.matchers.json_params_matcher(
            {'source_code': script,
             'predefined_objects': {'sender_id': 'default', 'user_message': 'get intents',
                                    'slot': {'bot': '5f50fd0a56b698ca10d35d2z', 'location': 'Bangalore',
                                             'langauge': 'Kannada'}, 'intent': 'pyscript_action', 'chat_log': [],
                                    'key_vault': {}, 'kairon_user_msg': None, 'session_started': None}})]
    )

    request_object = {
        "next_action": action_name,
        "tracker": {
            "sender_id": "default",
            "conversation_id": "default",
            "slots": {"bot": "5f50fd0a56b698ca10d35d2z", "location": "Bangalore", "langauge": "Kannada"},
            "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'pyscript_action'}]},
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
            "slots": {"bot": "5f50fd0a56b698ca10d35d2z"},
            "responses": {},
            "actions": [],
            "forms": {},
            "e2e_actions": []
        },
        "version": "version"
    }
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert len(response_json['events']) == 1
    assert len(response_json['responses']) == 1
    assert response_json['events'] == [{'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
                                        'value': 'Successfully Evaluated the pyscript'}]


@responses.activate
@mock.patch("kairon.shared.cloud.utils.CloudUtility.trigger_lambda", autospec=True)
def test_pyscript_action_execution_without_pyscript_evaluator_url(mock_trigger_lambda):
    import textwrap

    action_name = "test_pyscript_action_execution_without_pyscript_evaluator_url"
    Actions(name=action_name, type=ActionType.pyscript_action.value,
            bot="5f50fd0a56b698ca10d35d2z", user="user").save()
    script = """
    numbers = [1, 2, 3, 4, 5]
    total = 0
    for i in numbers:
        total += i
    print(total)
    """
    script = textwrap.dedent(script)
    PyscriptActionConfig(
        name=action_name,
        source_code=script,
        bot="5f50fd0a56b698ca10d35d2z",
        user="user"
    ).save()
    mock_environment = {"evaluator": {"pyscript": {"trigger_task": True, "url": None}}}

    request_object = {
        "next_action": action_name,
        "tracker": {
            "sender_id": "default",
            "conversation_id": "default",
            "slots": {"bot": "5f50fd0a56b698ca10d35d2z", "location": "Bangalore", "langauge": "Kannada"},
            "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'pyscript_action'}]},
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
            "slots": {"bot": "5f50fd0a56b698ca10d35d2z"},
            "responses": {},
            "actions": [],
            "forms": {},
            "e2e_actions": []
        },
        "version": "version"
    }
    with patch("kairon.shared.utils.Utility.environment", new=mock_environment):
        mock_trigger_lambda.return_value = \
            {"Payload": {"body": {"bot_response": "Successfully Evaluated the pyscript",
                                  "slots": {"location": "Bangalore", "langauge": "Kannada"}}}, "StatusCode": 200}
        response = client.post("/webhook", json=request_object)
        response_json = response.json()
        assert response.status_code == 200
        assert len(response_json['events']) == 3
        assert len(response_json['responses']) == 1
        assert response_json['events'] == [
        {'event': 'slot', 'timestamp': None, 'name': 'location', 'value': 'Bangalore'},
        {'event': 'slot', 'timestamp': None, 'name': 'langauge', 'value': 'Kannada'},
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
         'value': "Successfully Evaluated the pyscript"}]
        assert response_json['responses'][0]['text'] == "Successfully Evaluated the pyscript"
        called_args = mock_trigger_lambda.call_args
        assert called_args.args[1] == \
               {'source_code': script,
                'predefined_objects': {'sender_id': 'default', 'user_message': 'get intents',
                                       'slot': {"bot": "5f50fd0a56b698ca10d35d2z", "location": "Bangalore",
                                                "langauge": "Kannada"},
                                       'intent': 'pyscript_action', 'chat_log': [], 'key_vault': {},
                                       'kairon_user_msg': None, 'session_started': None}}


@responses.activate
@mock.patch("kairon.shared.cloud.utils.CloudUtility.trigger_lambda", autospec=True)
def test_pyscript_action_execution_without_pyscript_evaluator_url_raise_exception(mock_trigger_lambda):
    import textwrap

    action_name = "test_pyscript_action_execution_without_pyscript_evaluator_url_raise_exception"
    Actions(name=action_name, type=ActionType.pyscript_action.value,
            bot="5f50fd0a56b698ca10d35d2z", user="user").save()
    script = """
    numbers = [1, 2, 3, 4, 5]
    total = 0
    for i in numbers:
        total += i
    print(total)
    """
    script = textwrap.dedent(script)
    PyscriptActionConfig(
        name=action_name,
        source_code=script,
        bot="5f50fd0a56b698ca10d35d2z",
        user="user"
    ).save()
    mock_environment = {"evaluator": {"pyscript": {"trigger_task": True, "url": None}}}

    request_object = {
        "next_action": action_name,
        "tracker": {
            "sender_id": "default",
            "conversation_id": "default",
            "slots": {"bot": "5f50fd0a56b698ca10d35d2z", "location": "Bangalore", "langauge": "Kannada"},
            "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'pyscript_action'}]},
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
            "slots": {"bot": "5f50fd0a56b698ca10d35d2z"},
            "responses": {},
            "actions": [],
            "forms": {},
            "e2e_actions": []
        },
        "version": "version"
    }
    with patch("kairon.shared.utils.Utility.environment", new=mock_environment):
        mock_trigger_lambda.return_value = {"Payload": {"body": "Failed to evaluated the pyscript"}, "StatusCode": 422}
        response = client.post("/webhook", json=request_object)
        response_json = response.json()
        assert response.status_code == 200
        assert len(response_json['events']) == 1
        assert len(response_json['responses']) == 1
        assert response_json['events'] == [
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
         'value': "I have failed to process your request"}]
        log = ActionServerLogs.objects(action=action_name).get().to_mongo().to_dict()
        assert log['exception'] == "Failed to evaluated the pyscript"


@responses.activate
def test_pyscript_action_execution_with_error():
    import textwrap

    action_name = "test_pyscript_action_execution_with_error"
    Actions(name=action_name, type=ActionType.pyscript_action.value,
            bot="5f50fd0a56b698ca10d35d2z", user="user").save()
    script = """
    import requests
    response = requests.get('http://localhost')
    value = response.json()
    data = value['data']
    """
    script = textwrap.dedent(script)
    PyscriptActionConfig(
        name=action_name,
        source_code=script,
        dispatch_response=False,
        bot="5f50fd0a56b698ca10d35d2z",
        user="user"
    ).save()

    def raise_custom_exception(request):
        import requests
        raise requests.exceptions.ConnectionError(f"Failed to connect to service: localhost")

    responses.add_callback(
        "POST", Utility.environment['evaluator']['pyscript']['url'], callback=raise_custom_exception,
        match=[responses.matchers.json_params_matcher(
            {'source_code': script,
             'predefined_objects': {'sender_id': 'default', 'user_message': 'get intents',
                                    'slot': {'bot': '5f50fd0a56b698ca10d35d2z', 'location': 'Bangalore',
                                             'langauge': 'Kannada'}, 'intent': 'pyscript_action', 'chat_log': [],
                                    'key_vault': {}, 'kairon_user_msg': None, 'session_started': None}})]
    )

    request_object = {
        "next_action": action_name,
        "tracker": {
            "sender_id": "default",
            "conversation_id": "default",
            "slots": {"bot": "5f50fd0a56b698ca10d35d2z", "location": "Bangalore",  "langauge": "Kannada"},
            "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'pyscript_action'}]},
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
            "slots": {"bot": "5f50fd0a56b698ca10d35d2z"},
            "responses": {},
            "actions": [],
            "forms": {},
            "e2e_actions": []
        },
        "version": "version"
    }
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert len(response_json['events']) == 1
    assert response_json['events'] == [
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
         'value': 'I have failed to process your request'}]
    log = ActionServerLogs.objects(action=action_name).get().to_mongo().to_dict()
    assert log['exception'] == 'Failed to execute the url: Failed to connect to service: localhost'


@responses.activate
def test_pyscript_action_execution_with_invalid_response():
    import textwrap

    action_name = "test_pyscript_action_execution_with_with_script_errors"
    Actions(name=action_name, type=ActionType.pyscript_action.value,
            bot="5f50fd0a56b698ca10d35d2z", user="user").save()
    script = """
    for i in 10
    """
    script = textwrap.dedent(script)
    PyscriptActionConfig(
        name=action_name,
        source_code=script,
        dispatch_response=False,
        bot="5f50fd0a56b698ca10d35d2z",
        user="user"
    ).save()

    responses.add(
        "POST", Utility.environment['evaluator']['pyscript']['url'],
        json={"success": False, "data": None,
              "message": 'Script execution error: ("Line 2: SyntaxError: invalid syntax at statement: for i in 10",)',
              "error_code": 422},
        match=[responses.matchers.json_params_matcher(
            {'source_code': script,
             'predefined_objects': {'sender_id': 'default', 'user_message': 'get intents',
                                    'slot': {'bot': '5f50fd0a56b698ca10d35d2z', 'location': 'Bangalore',
                                             'langauge': 'Kannada'}, 'intent': 'pyscript_action', 'chat_log': [],
                                    'key_vault': {}, 'kairon_user_msg': None, 'session_started': None}})]
    )

    request_object = {
        "next_action": action_name,
        "tracker": {
            "sender_id": "default",
            "conversation_id": "default",
            "slots": {"bot": "5f50fd0a56b698ca10d35d2z", "location": "Bangalore", "langauge": "Kannada"},
            "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'pyscript_action'}]},
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
            "slots": {"bot": "5f50fd0a56b698ca10d35d2z"},
            "responses": {},
            "actions": [],
            "forms": {},
            "e2e_actions": []
        },
        "version": "version"
    }
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert len(response_json['events']) == 1
    assert response_json['events'] == [
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
         'value': 'I have failed to process your request'}]
    log = ActionServerLogs.objects(action=action_name).get().to_mongo().to_dict()
    assert log['exception'] == 'Pyscript evaluation failed: {\'success\': False, \'data\': None, \'message\': \'Script execution error: ("Line 2: SyntaxError: invalid syntax at statement: for i in 10",)\', \'error_code\': 422}'


def test_http_action_execution(aioresponses):
    action_name = "test_http_action_execution"
    Actions(name=action_name, type=ActionType.http_action.value, bot="5f50fd0a56b698ca10d35d2e", user="user").save()
    KeyVault(key="EMAIL", value="uditpandey@digite.com", bot="5f50fd0a56b698ca10d35d2e", user="user").save()
    KeyVault(key="FIRSTNAME", value="udit", bot="5f50fd0a56b698ca10d35d2e", user="user").save()
    HttpActionConfig(
        action_name=action_name,
        response=HttpActionResponse(value="The value of ${data.a.b.3} in ${data.a.b.d.0} is ${data.a.b.d}"),
        http_url="http://localhost:8081/mock",
        request_method="GET",
        headers=[HttpActionRequestBody(key="botid", parameter_type="slot", value="bot", encrypt=True),
                 HttpActionRequestBody(key="userid", parameter_type="value", value="1011", encrypt=True),
                 HttpActionRequestBody(key="tag", parameter_type="value", value="from_bot", encrypt=True),
                 HttpActionRequestBody(key="email", parameter_type="key_vault", value="EMAIL", encrypt=False)],
        params_list=[HttpActionRequestBody(key="bot", parameter_type="slot", value="bot", encrypt=True),
                     HttpActionRequestBody(key="user", parameter_type="value", value="1011", encrypt=False),
                     HttpActionRequestBody(key="tag", parameter_type="value", value="from_bot", encrypt=True),
                     HttpActionRequestBody(key="name", parameter_type="key_vault", value="FIRSTNAME",
                                           encrypt=False),
                     HttpActionRequestBody(key="contact", parameter_type="key_vault", value="CONTACT",
                                           encrypt=False)],
        set_slots=[SetSlotsFromResponse(name="val_d", value="${data.a.b.d}"),
                   SetSlotsFromResponse(name="val_d_0", value="${data.a.b.d.0}")],
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
    aioresponses.add(
        method=responses.GET,
        url=f"{http_url}?bot=5f50fd0a56b698ca10d35d2e&user=1011&tag=from_bot&name=udit",
        body=resp_msg,
        status=200
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
    response = client.post("/webhook", json=request_object)
    result = response.json()
    assert response.status_code == 200
    assert len(result['events']) == 3
    assert len(result['responses']) == 1
    assert result['events'] == [
        {"event": "slot", "timestamp": None, "name": "val_d", "value": "['red', 'buggy', 'bumpers']"},
        {"event": "slot", "timestamp": None, "name": "val_d_0", "value": "red"},
        {"event": "slot", "timestamp": None, "name": "kairon_action_response",
         "value": "The value of 2 in red is ['red', 'buggy', 'bumpers']"}]
    assert result['responses'][0]['text'] == "The value of 2 in red is ['red', 'buggy', 'bumpers']"
    log = ActionServerLogs.objects(action=action_name).get().to_mongo().to_dict()
    log.pop('_id')
    log.pop('timestamp')
    print(log)
    assert log == {'type': 'http_action', 'intent': 'test_run', 'action': 'test_http_action_execution',
                   'sender': 'default',
                   'headers': {'botid': '**********************2e', 'userid': '****', 'tag': '******ot',
                               'email': '*******************om'}, 'url': 'http://localhost:8081/mock',
                   'request_method': 'GET',
                   'request_params': {'bot': '**********************2e', 'user': '1011', 'tag': '******ot',
                                      'name': '****', 'contact': None},
                   'api_response': "{'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}",
                   'bot_response': "The value of 2 in red is ['red', 'buggy', 'bumpers']",
                   'messages': ['evaluation_type: expression',
                                'expression: The value of ${data.a.b.3} in ${data.a.b.d.0} is ${data.a.b.d}',
                                "data: {'data': {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}, 'context': {'sender_id': 'default', 'user_message': 'get intents', 'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run', 'chat_log': [], 'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'}, 'kairon_user_msg': None, 'session_started': None, 'bot': '5f50fd0a56b698ca10d35d2e'}}",
                                "response: The value of 2 in red is ['red', 'buggy', 'bumpers']",
                                'initiating slot evaluation', 'Slot: val_d', 'evaluation_type: expression',
                                'expression: ${data.a.b.d}',
                                "data: {'data': {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}, 'context': {'sender_id': 'default', 'user_message': 'get intents', 'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run', 'chat_log': [], 'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'}, 'kairon_user_msg': None, 'session_started': None, 'bot': '5f50fd0a56b698ca10d35d2e'}}",
                                "response: ['red', 'buggy', 'bumpers']", 'Slot: val_d_0',
                                'evaluation_type: expression', 'expression: ${data.a.b.d.0}',
                                "data: {'data': {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}, 'context': {'sender_id': 'default', 'user_message': 'get intents', 'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run', 'chat_log': [], 'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'}, 'kairon_user_msg': None, 'session_started': None, 'bot': '5f50fd0a56b698ca10d35d2e'}}",
                                'response: red'],
                   'bot': '5f50fd0a56b698ca10d35d2e', 'status': 'SUCCESS', 'user_msg': 'get intents'}


def test_http_action_execution_returns_custom_json(aioresponses):
    action_name = "test_http_action_execution_returns_custom_json"
    Actions(name=action_name, type=ActionType.http_action.value, bot="5f50fd0a56b698ca10d35d2e", user="user").save()
    HttpActionConfig(
        action_name=action_name,
        response=HttpActionResponse(value="${RESPONSE}", dispatch=True, evaluation_type="expression",
                                    dispatch_type=DispatchType.json.value),
        http_url="http://localhost:8081/mock",
        request_method="GET",
        headers=[HttpActionRequestBody(key="botid", parameter_type="slot", value="bot", encrypt=True),
                 HttpActionRequestBody(key="userid", parameter_type="value", value="1011", encrypt=True),
                 HttpActionRequestBody(key="tag", parameter_type="value", value="from_bot", encrypt=True),
                 HttpActionRequestBody(key="email", parameter_type="key_vault", value="EMAIL", encrypt=False)],
        params_list=[HttpActionRequestBody(key="bot", parameter_type="slot", value="bot", encrypt=True),
                     HttpActionRequestBody(key="user", parameter_type="value", value="1011", encrypt=False),
                     HttpActionRequestBody(key="tag", parameter_type="value", value="from_bot", encrypt=True),
                     HttpActionRequestBody(key="name", parameter_type="key_vault", value="FIRSTNAME",
                                           encrypt=False),
                     HttpActionRequestBody(key="contact", parameter_type="key_vault", value="CONTACT",
                                           encrypt=False)],
        set_slots=[SetSlotsFromResponse(name="val_d", value="${data.a.b.d}"),
                   SetSlotsFromResponse(name="val_d_0", value="${data.a.b.d.0}")],
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
    aioresponses.add(
        method=responses.GET,
        url=f"{http_url}?bot=5f50fd0a56b698ca10d35d2e&user=1011&tag=from_bot&name=udit",
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
    response = client.post("/webhook", json=request_object)
    result = response.json()
    assert response.status_code == 200
    assert len(result['events']) == 3
    assert len(result['responses']) == 1
    assert result['events'] == [
        {"event": "slot", "timestamp": None, "name": "val_d", "value": "['red', 'buggy', 'bumpers']"},
        {"event": "slot", "timestamp": None, "name": "val_d_0", "value": "red"},
        {"event": "slot", "timestamp": None, "name": "kairon_action_response",
         "value": {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}}]
    assert result['responses'][0]['custom'] == {
        'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}


def test_http_action_execution_custom_json_with_invalid_json_response(aioresponses):
    action_name = "test_http_action_execution_custom_json_with_invalid_json_response"
    Actions(name=action_name, type=ActionType.http_action.value, bot="5f50fd0a56b698ca10d35d2e", user="user").save()
    HttpActionConfig(
        action_name=action_name,
        response=HttpActionResponse(value="INVALID ${RESPONSE}", dispatch=True, evaluation_type="expression",
                                    dispatch_type=DispatchType.json.value),
        http_url="http://localhost:8081/mock",
        request_method="GET",
        headers=[HttpActionRequestBody(key="botid", parameter_type="slot", value="bot", encrypt=True),
                 HttpActionRequestBody(key="userid", parameter_type="value", value="1011", encrypt=True),
                 HttpActionRequestBody(key="tag", parameter_type="value", value="from_bot", encrypt=True),
                 HttpActionRequestBody(key="email", parameter_type="key_vault", value="EMAIL", encrypt=False)],
        params_list=[HttpActionRequestBody(key="bot", parameter_type="slot", value="bot", encrypt=True),
                     HttpActionRequestBody(key="user", parameter_type="value", value="1011", encrypt=False),
                     HttpActionRequestBody(key="tag", parameter_type="value", value="from_bot", encrypt=True),
                     HttpActionRequestBody(key="name", parameter_type="key_vault", value="FIRSTNAME",
                                           encrypt=False),
                     HttpActionRequestBody(key="contact", parameter_type="key_vault", value="CONTACT",
                                           encrypt=False)],
        set_slots=[SetSlotsFromResponse(name="val_d", value="${data.a.b.d}"),
                   SetSlotsFromResponse(name="val_d_0", value="${data.a.b.d.0}")],
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
    aioresponses.add(
        method=responses.GET,
        url=f"{http_url}?bot=5f50fd0a56b698ca10d35d2e&user=1011&tag=from_bot&name=udit",
        body=resp_msg,
        status=200
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
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert len(response_json['events']) == 3
    assert len(response_json['responses']) == 1
    assert response_json['events'] == [
        {"event": "slot", "timestamp": None, "name": "val_d", "value": "['red', 'buggy', 'bumpers']"},
        {"event": "slot", "timestamp": None, "name": "val_d_0", "value": "red"},
        {"event": "slot", "timestamp": None, "name": "kairon_action_response",
         "value": 'INVALID {"a": {"b": {"3": 2, "43": 30, "c": [], "d": ["red", "buggy", "bumpers"]}}}'}]
    assert response_json['responses'][0][
               'text'] == 'INVALID {"a": {"b": {"3": 2, "43": 30, "c": [], "d": ["red", "buggy", "bumpers"]}}}'


@responses.activate
def test_http_action_execution_return_custom_json_with_script_evaluation(aioresponses):
    action_name = "test_http_action_execution_return_custom_json_with_script_evaluation"
    Actions(name=action_name, type=ActionType.http_action.value, bot="5f50fd0a56b698ca10d35d2e", user="user").save()
    HttpActionConfig(
        action_name=action_name,
        response=HttpActionResponse(value="${RESPONSE}", dispatch=True, evaluation_type="script",
                                    dispatch_type=DispatchType.json.value),
        http_url="http://localhost:8081/mock",
        request_method="GET",
        headers=[HttpActionRequestBody(key="botid", parameter_type="slot", value="bot", encrypt=True),
                 HttpActionRequestBody(key="userid", parameter_type="value", value="1011", encrypt=True),
                 HttpActionRequestBody(key="tag", parameter_type="value", value="from_bot", encrypt=True),
                 HttpActionRequestBody(key="email", parameter_type="key_vault", value="EMAIL", encrypt=False)],
        params_list=[HttpActionRequestBody(key="bot", parameter_type="slot", value="bot", encrypt=True),
                     HttpActionRequestBody(key="user", parameter_type="value", value="1011", encrypt=False),
                     HttpActionRequestBody(key="tag", parameter_type="value", value="from_bot", encrypt=True),
                     HttpActionRequestBody(key="name", parameter_type="key_vault", value="FIRSTNAME",
                                           encrypt=False),
                     HttpActionRequestBody(key="contact", parameter_type="key_vault", value="CONTACT",
                                           encrypt=False)],
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
    aioresponses.add(
        method=responses.GET,
        url=f"{http_url}?bot=5f50fd0a56b698ca10d35d2e&user=1011&tag=from_bot&name=udit",
        body=resp_msg,
        status=200
    )
    responses.add(
        method=responses.POST,
        url=Utility.environment['evaluator']['url'],
        json={"success": True, "data": {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}},
        status=200,
        match=[
            responses.matchers.json_params_matcher(
                {'script': "${RESPONSE}",
                 'data': {'data': {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}},
                          'context': {'sender_id': 'default', 'user_message': 'get intents',
                                      'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run',
                                      'chat_log': [],
                                      'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'},
                                      'kairon_user_msg': None, 'session_started': None,
                                      'bot': '5f50fd0a56b698ca10d35d2e'}}})],
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
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert len(response_json['events']) == 1
    assert len(response_json['responses']) == 1
    assert response_json['events'] == [
        {"event": "slot", "timestamp": None, "name": "kairon_action_response",
         "value": {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}}]
    assert response_json['responses'][0]['custom'] == {
        'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}


@responses.activate
def test_http_action_execution_script_evaluation_with_json_response(aioresponses):
    action_name = "test_http_action_execution_script_evaluation_with_json_response"
    Actions(name=action_name, type=ActionType.http_action.value, bot="5f50fd0a56b698ca10d35d2d", user="user").save()
    HttpActionConfig(
        action_name=action_name,
        response=HttpActionResponse(value="'The value of '+`${a.b.d}`+' in '+`${a.b.d.0}`+' is '+`${a.b.d}`",
                                    dispatch=True, evaluation_type="script", dispatch_type=DispatchType.text.value),
        http_url="http://localhost:8081/mock",
        request_method="GET",
        headers=[HttpActionRequestBody(key="botid", parameter_type="slot", value="bot", encrypt=True),
                 HttpActionRequestBody(key="userid", parameter_type="value", value="1011", encrypt=True),
                 HttpActionRequestBody(key="tag", parameter_type="value", value="from_bot", encrypt=True),
                 HttpActionRequestBody(key="email", parameter_type="key_vault", value="EMAIL", encrypt=False)],
        params_list=[HttpActionRequestBody(key="bot", parameter_type="slot", value="bot", encrypt=True),
                     HttpActionRequestBody(key="user", parameter_type="value", value="1011", encrypt=False),
                     HttpActionRequestBody(key="tag", parameter_type="value", value="from_bot", encrypt=True),
                     HttpActionRequestBody(key="name", parameter_type="key_vault", value="FIRSTNAME",
                                           encrypt=False),
                     HttpActionRequestBody(key="contact", parameter_type="key_vault", value="CONTACT",
                                           encrypt=False)],
        bot="5f50fd0a56b698ca10d35d2d",
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
    aioresponses.add(
        method=responses.GET,
        url=f"{http_url}?bot=5f50fd0a56b698ca10d35d2d&tag=from_bot&user=1011",
        body=resp_msg,
        status=200
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
                          'context': {'sender_id': 'default', 'user_message': 'get intents',
                                      'slot': {'bot': '5f50fd0a56b698ca10d35d2d'}, 'intent': 'test_run',
                                      'chat_log': [], 'key_vault': {}, 'kairon_user_msg': None,
                                      'session_started': None, 'bot': '5f50fd0a56b698ca10d35d2d'}}})],
    )

    request_object = {
        "next_action": action_name,
        "tracker": {
            "sender_id": "default",
            "conversation_id": "default",
            "slots": {"bot": "5f50fd0a56b698ca10d35d2d"},
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
            "slots": {"bot": "5f50fd0a56b698ca10d35d2d"},
            "responses": {},
            "actions": [],
            "forms": {},
            "e2e_actions": []
        },
        "version": "version"
    }
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert len(response_json['events']) == 1
    assert len(response_json['responses']) == 1
    assert response_json['events'] == [
        {"event": "slot", "timestamp": None, "name": "kairon_action_response",
         "value": "The value of 2 in red is ['red', 'buggy', 'bumpers']"}]
    assert response_json['responses'][0]['text'] == "The value of 2 in red is ['red', 'buggy', 'bumpers']"


@responses.activate
def test_http_action_execution_no_response_dispatch(aioresponses):
    action_name = "test_http_action_execution_no_response_dispatch"
    Actions(name=action_name, type=ActionType.http_action.value, bot="5f50fd0a56b698ca10d35d2e", user="user").save()
    HttpActionConfig(
        action_name=action_name,
        content_type="data",
        response=HttpActionResponse(value="The value of ${data.a.b.3} in ${data.a.b.d.0} is ${data.a.b.d}",
                                    dispatch=False),
        http_url="http://localhost:8081/mock",
        request_method="GET",
        headers=[HttpActionRequestBody(key="botid", parameter_type="slot", value="bot", encrypt=False),
                 HttpActionRequestBody(key="userid", parameter_type="value", value="1011", encrypt=True),
                 HttpActionRequestBody(key="tag", parameter_type="value", value="from_bot", encrypt=True)],
        params_list=[HttpActionRequestBody(key="bot", parameter_type="slot", value="bot", encrypt=False),
                     HttpActionRequestBody(key="user", parameter_type="value", value="1011", encrypt=False),
                     HttpActionRequestBody(key="tag", parameter_type="value", value="from_bot", encrypt=True)],
        set_slots=[SetSlotsFromResponse(name="val_d", value="${data.a.b.d}"),
                   SetSlotsFromResponse(name="val_d_0", value="${data.a.b.d.0}")],
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
    aioresponses.add(
        method=responses.GET,
        url=f"{http_url}?bot=5f50fd0a56b698ca10d35d2e&user=1011&tag=from_bot",
        body=resp_msg,
        status=200
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
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert len(response_json['events']) == 3
    assert len(response_json['responses']) == 0
    assert response_json['events'] == [
        {"event": "slot", "timestamp": None, "name": "val_d", "value": "['red', 'buggy', 'bumpers']"},
        {"event": "slot", "timestamp": None, "name": "val_d_0", "value": "red"},
        {"event": "slot", "timestamp": None, "name": "kairon_action_response",
         "value": "The value of 2 in red is ['red', 'buggy', 'bumpers']"}]
    assert response_json['responses'] == []
    log = ActionServerLogs.objects(action=action_name).get().to_mongo().to_dict()
    log.pop('_id')
    log.pop('timestamp')
    print(log)
    assert log == {'type': 'http_action', 'intent': 'test_run',
                   'action': 'test_http_action_execution_no_response_dispatch', 'sender': 'default',
                   'headers': {'botid': '5f50fd0a56b698ca10d35d2e', 'userid': '****', 'tag': '******ot'},
                   'url': 'http://localhost:8081/mock', 'request_method': 'GET',
                   'request_params': {'bot': '5f50fd0a56b698ca10d35d2e', 'user': '1011', 'tag': '******ot'},
                   'api_response': "{'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}",
                   'bot_response': "The value of 2 in red is ['red', 'buggy', 'bumpers']",
                   'messages': ['evaluation_type: expression',
                                'expression: The value of ${data.a.b.3} in ${data.a.b.d.0} is ${data.a.b.d}',
                                "data: {'data': {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}, 'context': {'sender_id': 'default', 'user_message': 'get intents', 'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run', 'chat_log': [], 'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'}, 'kairon_user_msg': None, 'session_started': None, 'bot': '5f50fd0a56b698ca10d35d2e'}}",
                                "response: The value of 2 in red is ['red', 'buggy', 'bumpers']",
                                'initiating slot evaluation', 'Slot: val_d', 'evaluation_type: expression',
                                'expression: ${data.a.b.d}',
                                "data: {'data': {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}, 'context': {'sender_id': 'default', 'user_message': 'get intents', 'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run', 'chat_log': [], 'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'}, 'kairon_user_msg': None, 'session_started': None, 'bot': '5f50fd0a56b698ca10d35d2e'}}",
                                "response: ['red', 'buggy', 'bumpers']", 'Slot: val_d_0',
                                'evaluation_type: expression', 'expression: ${data.a.b.d.0}',
                                "data: {'data': {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}, 'context': {'sender_id': 'default', 'user_message': 'get intents', 'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run', 'chat_log': [], 'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'}, 'kairon_user_msg': None, 'session_started': None, 'bot': '5f50fd0a56b698ca10d35d2e'}}",
                                'response: red'],
                   'bot': '5f50fd0a56b698ca10d35d2e', 'status': 'SUCCESS', 'user_msg': 'get intents'}


@responses.activate
def test_http_action_execution_script_evaluation(aioresponses):
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
    aioresponses.add(
        method=responses.GET,
        url=f"{http_url}?bot=5f50fd0a56b698ca10d35d2e&user=1011&tag=from_bot",
        body=resp_msg,
        status=200
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
                          'context': {'sender_id': 'default', 'user_message': 'get intents',
                                      'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run',
                                      'chat_log': [],
                                      'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'},
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
                          'context': {'sender_id': 'default', 'user_message': 'get intents',
                                      'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run',
                                      'chat_log': [],
                                      'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'},
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
                          'context': {'sender_id': 'default', 'user_message': 'get intents',
                                      'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run',
                                      'chat_log': [],
                                      'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'},
                                      'kairon_user_msg': None, 'session_started': None,
                                      'bot': '5f50fd0a56b698ca10d35d2e'}}})],
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
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert len(response_json['events']) == 3
    assert len(response_json['responses']) == 0
    assert response_json['events'] == [
        {"event": "slot", "timestamp": None, "name": "val_d", "value": "['red', 'buggy', 'bumpers']"},
        {"event": "slot", "timestamp": None, "name": "val_d_0", "value": "red"},
        {"event": "slot", "timestamp": None, "name": "kairon_action_response",
         "value": "The value of 2 in red is ['red', 'buggy', 'bumpers']"}]
    assert response_json['responses'] == []


@responses.activate
def test_http_action_execution_script_evaluation_with_dynamic_params(aioresponses):
    action_name = "test_http_action_execution_script_evaluation_with_dynamic_params"
    Actions(name=action_name, type=ActionType.http_action.value, bot="5f50fd0a56b698ca10d35d2e", user="user").save()
    HttpActionConfig(
        action_name=action_name,
        content_type="json",
        response=HttpActionResponse(
            value="'The value of '+`${a.b.d}`+' in '+`${a.b.d.0}`+' is '+`${a.b.d}`",
            dispatch=True, evaluation_type="script"),
        http_url="http://localhost:8081/mock",
        request_method="GET",
        dynamic_params=
        "{\"sender_id\": \"${sender_id}\", \"user_message\": \"${user_message}\", \"intent\": \"${intent}\"}",
        headers=[HttpActionRequestBody(key="botid", parameter_type="slot", value="bot", encrypt=False),
                 HttpActionRequestBody(key="userid", parameter_type="value", value="1011", encrypt=True),
                 HttpActionRequestBody(key="tag", parameter_type="value", value="from_bot", encrypt=True)],
        set_slots=[SetSlotsFromResponse(name="val_d", value="${a.b.d}", evaluation_type="script"),
                   SetSlotsFromResponse(name="val_d_0", value="${a.b.d.0}", evaluation_type="script")],
        bot="5f50fd0a56b698ca10d35d2e",
        user="user"
    ).save()
    resp_msg = {
        "sender_id": "default",
        "user_message": "get intents",
        "intent": "test_run"
    }
    http_url = 'http://localhost:8081/mock'
    responses.add(
        method=responses.POST,
        url=Utility.environment['evaluator']['url'],
        json={"success": True, "data": resp_msg},
        status=200,
        match=[
            responses.matchers.json_params_matcher(
                {
                    'script': "{\"sender_id\": \"${sender_id}\", \"user_message\": \"${user_message}\", \"intent\": \"${intent}\"}",
                    'data': {'sender_id': 'default', 'user_message': 'get intents',
                             'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run', 'chat_log': [],
                             'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'},
                             'kairon_user_msg': None, 'session_started': None,
                             'bot': '5f50fd0a56b698ca10d35d2e'}})],
    )
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
    aioresponses.add(
        method=responses.GET,
        url=f"{http_url}?sender_id=default&user_message=get%20intents&intent=test_run",
        body=resp_msg,
        status=200
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
                          'context': {'sender_id': 'default', 'user_message': 'get intents',
                                      'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run',
                                      'chat_log': [],
                                      'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'},
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
                          'context': {'sender_id': 'default', 'user_message': 'get intents',
                                      'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run',
                                      'chat_log': [],
                                      'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'},
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
                          'context': {'sender_id': 'default', 'user_message': 'get intents',
                                      'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run',
                                      'chat_log': [],
                                      'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'},
                                      'kairon_user_msg': None, 'session_started': None,
                                      'bot': '5f50fd0a56b698ca10d35d2e'}}})],
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
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert len(response_json['events']) == 3
    assert len(response_json['responses']) == 1
    assert response_json['events'] == [
        {"event": "slot", "timestamp": None, "name": "val_d", "value": "['red', 'buggy', 'bumpers']"},
        {"event": "slot", "timestamp": None, "name": "val_d_0", "value": "red"},
        {"event": "slot", "timestamp": None, "name": "kairon_action_response",
         "value": "The value of 2 in red is ['red', 'buggy', 'bumpers']"}]
    assert response_json['responses'][0]['text'] == "The value of 2 in red is ['red', 'buggy', 'bumpers']"
    log = ActionServerLogs.objects(action=action_name).get().to_mongo().to_dict()
    log.pop('_id')
    log.pop('timestamp')
    print(log)
    assert log == {'type': 'http_action', 'intent': 'test_run',
                   'action': 'test_http_action_execution_script_evaluation_with_dynamic_params',
                   'sender': 'default',
                   'headers': {'botid': '5f50fd0a56b698ca10d35d2e', 'userid': '****', 'tag': '******ot'},
                   'url': 'http://localhost:8081/mock', 'request_method': 'GET',
                   'request_params': {'sender_id': 'default', 'user_message': 'get intents', 'intent': 'test_run'},
                   'api_response': "{'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}",
                   'bot_response': "The value of 2 in red is ['red', 'buggy', 'bumpers']",
                   'messages': ['evaluation_type: script',
                                'script: {"sender_id": "${sender_id}", "user_message": "${user_message}", "intent": "${intent}"}',
                                "data: {'sender_id': 'default', 'user_message': 'get intents', 'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run', 'chat_log': [], 'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'}, 'kairon_user_msg': None, 'session_started': None, 'bot': '5f50fd0a56b698ca10d35d2e'}",
                                'raise_err_on_failure: True',
                                "Evaluator response: {'success': True, 'data': {'sender_id': 'default', 'user_message': 'get intents', 'intent': 'test_run'}}",
                                'evaluation_type: script',
                                "script: 'The value of '+`${a.b.d}`+' in '+`${a.b.d.0}`+' is '+`${a.b.d}`",
                                "data: {'data': {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}, 'context': {'sender_id': 'default', 'user_message': 'get intents', 'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run', 'chat_log': [], 'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'}, 'kairon_user_msg': None, 'session_started': None, 'bot': '5f50fd0a56b698ca10d35d2e'}}",
                                'raise_err_on_failure: True',
                                'Evaluator response: {\'success\': True, \'data\': "The value of 2 in red is [\'red\', \'buggy\', \'bumpers\']"}',
                                'initiating slot evaluation', 'Slot: val_d', 'evaluation_type: script',
                                'script: ${a.b.d}',
                                "data: {'data': {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}, 'context': {'sender_id': 'default', 'user_message': 'get intents', 'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run', 'chat_log': [], 'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'}, 'kairon_user_msg': None, 'session_started': None, 'bot': '5f50fd0a56b698ca10d35d2e'}}",
                                'raise_err_on_failure: True',
                                'Evaluator response: {\'success\': True, \'data\': "[\'red\', \'buggy\', \'bumpers\']"}',
                                'Slot: val_d_0', 'evaluation_type: script', 'script: ${a.b.d.0}',
                                "data: {'data': {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}, 'context': {'sender_id': 'default', 'user_message': 'get intents', 'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run', 'chat_log': [], 'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'}, 'kairon_user_msg': None, 'session_started': None, 'bot': '5f50fd0a56b698ca10d35d2e'}}",
                                'raise_err_on_failure: True',
                                "Evaluator response: {'success': True, 'data': 'red'}"],
                   'bot': '5f50fd0a56b698ca10d35d2e', 'status': 'SUCCESS', 'user_msg': 'get intents'}


@responses.activate
def test_http_action_execution_script_evaluation_with_dynamic_params_returns_custom_json(aioresponses):
    action_name = "test_http_action_execution_script_evaluation_with_dynamic_params_returns_custom_json"
    Actions(name=action_name, type=ActionType.http_action.value, bot="5f50fd0a56b698ca10d35d2e", user="user").save()
    HttpActionConfig(
        action_name=action_name,
        content_type="json",
        response=HttpActionResponse(
            value="${RESPONSE}",
            dispatch=True, evaluation_type="expression", dispatch_type=DispatchType.json.value),
        http_url="http://localhost:8081/mock",
        request_method="GET",
        dynamic_params=
        "{\"sender_id\": \"${sender_id}\", \"user_message\": \"${user_message}\", \"intent\": \"${intent}\"}",
        headers=[HttpActionRequestBody(key="botid", parameter_type="slot", value="bot", encrypt=False),
                 HttpActionRequestBody(key="userid", parameter_type="value", value="1011", encrypt=True),
                 HttpActionRequestBody(key="tag", parameter_type="value", value="from_bot", encrypt=True)],
        set_slots=[SetSlotsFromResponse(name="val_d", value="${a.b.d}", evaluation_type="script"),
                   SetSlotsFromResponse(name="val_d_0", value="${a.b.d.0}", evaluation_type="script")],
        bot="5f50fd0a56b698ca10d35d2e",
        user="user"
    ).save()
    resp_msg = {
        "sender_id": "default",
        "user_message": "get intents",
        "intent": "test_run"
    }
    http_url = 'http://localhost:8081/mock'
    responses.add(
        method=responses.POST,
        url=Utility.environment['evaluator']['url'],
        json={"success": True, "data": resp_msg},
        status=200,
        match=[
            responses.matchers.json_params_matcher(
                {
                    'script': "{\"sender_id\": \"${sender_id}\", \"user_message\": \"${user_message}\", \"intent\": \"${intent}\"}",
                    'data': {'sender_id': 'default', 'user_message': 'get intents',
                             'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run', 'chat_log': [],
                             'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'},
                             'kairon_user_msg': None, 'session_started': None,
                             'bot': '5f50fd0a56b698ca10d35d2e'}})],
    )
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
    aioresponses.add(
        method=responses.GET,
        url=f"{http_url}?sender_id=default&user_message=get%20intents&intent=test_run",
        body=resp_msg,
        status=200
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
                          'context': {'sender_id': 'default', 'user_message': 'get intents',
                                      'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run',
                                      'chat_log': [],
                                      'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'},
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
                          'context': {'sender_id': 'default', 'user_message': 'get intents',
                                      'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run',
                                      'chat_log': [],
                                      'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'},
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
                          'context': {'sender_id': 'default', 'user_message': 'get intents',
                                      'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run',
                                      'chat_log': [],
                                      'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'},
                                      'kairon_user_msg': None, 'session_started': None,
                                      'bot': '5f50fd0a56b698ca10d35d2e'}}})],
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
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    print(response_json)
    assert response.status_code == 200
    assert len(response_json['events']) == 3
    assert len(response_json['responses']) == 1
    assert response_json['events'] == [
        {"event": "slot", "timestamp": None, "name": "val_d", "value": "['red', 'buggy', 'bumpers']"},
        {"event": "slot", "timestamp": None, "name": "val_d_0", "value": "red"},
        {"event": "slot", "timestamp": None, "name": "kairon_action_response",
         "value": {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}}]
    assert response_json['responses'][0]['custom'] == {
        'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}


@responses.activate
def test_http_action_execution_script_evaluation_with_dynamic_params_no_response_dispatch(aioresponses):
    action_name = "test_http_action_execution_script_evaluation_with_dynamic_params_no_response_dispatch"
    Actions(name=action_name, type=ActionType.http_action.value, bot="5f50fd0a56b698ca10d35d2e", user="user").save()
    HttpActionConfig(
        action_name=action_name,
        content_type="json",
        response=HttpActionResponse(
            value="'The value of '+`${a.b.d}`+' in '+`${a.b.d.0}`+' is '+`${a.b.d}`",
            dispatch=False, evaluation_type="script"),
        http_url="http://localhost:8081/mock",
        request_method="GET",
        dynamic_params=
        "{\"sender_id\": \"${sender_id}\", \"user_message\": \"${user_message}\", \"intent\": \"${intent}\"}",
        headers=[HttpActionRequestBody(key="botid", parameter_type="slot", value="bot", encrypt=False),
                 HttpActionRequestBody(key="userid", parameter_type="value", value="1011", encrypt=True),
                 HttpActionRequestBody(key="tag", parameter_type="value", value="from_bot", encrypt=True)],
        set_slots=[SetSlotsFromResponse(name="val_d", value="${a.b.d}", evaluation_type="script"),
                   SetSlotsFromResponse(name="val_d_0", value="${a.b.d.0}", evaluation_type="script")],
        bot="5f50fd0a56b698ca10d35d2e",
        user="user"
    ).save()
    resp_msg = {
        "sender_id": "default",
        "user_message": "get intents",
        "intent": "test_run"
    }
    http_url = 'http://localhost:8081/mock'
    responses.add(
        method=responses.POST,
        url=Utility.environment['evaluator']['url'],
        json={"success": True, "data": resp_msg},
        status=200,
        match=[
            responses.matchers.json_params_matcher(
                {
                    'script': "{\"sender_id\": \"${sender_id}\", \"user_message\": \"${user_message}\", \"intent\": \"${intent}\"}",
                    'data': {'sender_id': 'default', 'user_message': 'get intents',
                             'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run', 'chat_log': [],
                             'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'},
                             'kairon_user_msg': None, 'session_started': None,
                             'bot': '5f50fd0a56b698ca10d35d2e'}})],
    )
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
    aioresponses.add(
        method=responses.GET,
        url=f"{http_url}?sender_id=default&user_message=get%20intents&intent=test_run",
        body=resp_msg,
        status=200
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
                          'context': {'sender_id': 'default', 'user_message': 'get intents',
                                      'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run',
                                      'chat_log': [],
                                      'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'},
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
                          'context': {'sender_id': 'default', 'user_message': 'get intents',
                                      'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run',
                                      'chat_log': [],
                                      'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'},
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
                          'context': {'sender_id': 'default', 'user_message': 'get intents',
                                      'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run',
                                      'chat_log': [],
                                      'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'},
                                      'kairon_user_msg': None, 'session_started': None,
                                      'bot': '5f50fd0a56b698ca10d35d2e'}}})],
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
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert len(response_json['events']) == 3
    assert len(response_json['responses']) == 0
    assert response_json['events'] == [
        {"event": "slot", "timestamp": None, "name": "val_d", "value": "['red', 'buggy', 'bumpers']"},
        {"event": "slot", "timestamp": None, "name": "val_d_0", "value": "red"},
        {"event": "slot", "timestamp": None, "name": "kairon_action_response",
         "value": "The value of 2 in red is ['red', 'buggy', 'bumpers']"}]
    assert response_json['responses'] == []


@responses.activate
def test_http_action_execution_script_evaluation_failure_with_dynamic_params_no_response_dispatch(aioresponses):
    action_name = "test_http_action_execution_script_evaluation_failure_with_dynamic_params_no_response_dispatch"
    Actions(name=action_name, type=ActionType.http_action.value, bot="5f50fd0a56b698ca10d35d2e", user="user").save()
    HttpActionConfig(
        action_name=action_name,
        content_type="json",
        response=HttpActionResponse(
            value="'The value of '+`${a.b.d}`+' in '+`${a.b.d.0}`+' is '+`${a.b.d}`",
            dispatch=False, evaluation_type="script"),
        http_url="http://localhost:8081/mock",
        request_method="GET",
        dynamic_params=
        "{\"sender_id\": \"${sender_id}\", \"user_message\": \"${user_message}\", \"intent\": \"${intent}\"}",
        headers=[HttpActionRequestBody(key="botid", parameter_type="slot", value="bot", encrypt=False),
                 HttpActionRequestBody(key="userid", parameter_type="value", value="1011", encrypt=True),
                 HttpActionRequestBody(key="tag", parameter_type="value", value="from_bot", encrypt=True)],
        set_slots=[SetSlotsFromResponse(name="val_d", value="${a.b.d}", evaluation_type="script"),
                   SetSlotsFromResponse(name="val_d_0", value="${a.b.d.0}", evaluation_type="script")],
        bot="5f50fd0a56b698ca10d35d2e",
        user="user"
    ).save()
    resp_msg = {
        "sender_id": "default",
        "user_message": "get intents",
        "intent": "test_run"
    }
    http_url = 'http://localhost:8081/mock'
    responses.add(
        method=responses.POST,
        url=Utility.environment['evaluator']['url'],
        json={"success": True, "data": resp_msg},
        status=200,
        match=[
            responses.matchers.json_params_matcher(
                {
                    'script': "{\"sender_id\": \"${sender_id}\", \"user_message\": \"${user_message}\", \"intent\": \"${intent}\"}",
                    'data': {'sender_id': 'default', 'user_message': 'get intents',
                             'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run', 'chat_log': [],
                             'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'},
                             'kairon_user_msg': None, 'session_started': None,
                             'bot': '5f50fd0a56b698ca10d35d2e'}})],
    )
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
    aioresponses.add(
        method=responses.GET,
        url=f"{http_url}?sender_id=default&user_message=get%20intents&intent=test_run",
        body=resp_msg,
        status=200
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
                          'context': {'sender_id': 'default', 'user_message': 'get intents',
                                      'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run',
                                      'chat_log': [],
                                      'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'},
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
                          'context': {'sender_id': 'default', 'user_message': 'get intents',
                                      'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run',
                                      'chat_log': [],
                                      'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'},
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
                          'context': {'sender_id': 'default', 'user_message': 'get intents',
                                      'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run',
                                      'chat_log': [],
                                      'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'},
                                      'kairon_user_msg': None, 'session_started': None,
                                      'bot': '5f50fd0a56b698ca10d35d2e'}}})],
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
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert len(response_json['events']) == 3
    assert len(response_json['responses']) == 0
    assert response_json['events'] == [
        {"event": "slot", "timestamp": None, "name": "val_d", "value": "['red', 'buggy', 'bumpers']"},
        {"event": "slot", "timestamp": None, "name": "val_d_0", "value": 'red'},
        {"event": "slot", "timestamp": None, "name": "kairon_action_response",
         "value": "The value of 2 in red is ['red', 'buggy', 'bumpers']"}]
    assert response_json['responses'] == []


@responses.activate
def test_http_action_execution_script_evaluation_with_dynamic_params_failure():
    action_name = "test_http_action_execution_script_evaluation_failure_with_dynamic_params"
    Actions(name=action_name, type=ActionType.http_action.value, bot="5f50fd0a56b698ca10d35d2e", user="user").save()
    HttpActionConfig(
        action_name=action_name,
        content_type="json",
        response=HttpActionResponse(
            value="'The value of '+`${a.b.d}`+' in '+`${a.b.d.0}`+' is '+`${a.b.d}`",
            dispatch=True, evaluation_type="script"),
        http_url="http://localhost:8081/mock",
        request_method="GET",
        dynamic_params=
        "{\"sender_id\": \"${sender_id}\", \"user_message\": \"${user_message}\", \"intent\": \"${intent}\"}",
        headers=[HttpActionRequestBody(key="botid", parameter_type="slot", value="bot", encrypt=False),
                 HttpActionRequestBody(key="userid", parameter_type="value", value="1011", encrypt=True),
                 HttpActionRequestBody(key="tag", parameter_type="value", value="from_bot", encrypt=True)],
        set_slots=[SetSlotsFromResponse(name="val_d", value="${a.b.d}", evaluation_type="script"),
                   SetSlotsFromResponse(name="val_d_0", value="${a.b.d.0}", evaluation_type="script")],
        bot="5f50fd0a56b698ca10d35d2e",
        user="user"
    ).save()
    resp_msg = {
        "sender_id": "default",
        "user_message": "get intents",
        "intent": "test_run"
    }
    http_url = 'http://localhost:8081/mock'
    responses.add(
        method=responses.POST,
        url=Utility.environment['evaluator']['url'],
        json={"success": True, "data": resp_msg},
        status=200,
        match=[
            responses.matchers.json_params_matcher(
                {'script': "${e}",
                 'data': {'sender_id': 'default', 'user_message': 'get intents',
                          'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run', 'chat_log': [],
                          'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'},
                          'kairon_user_msg': None, 'session_started': None, 'bot': '5f50fd0a56b698ca10d35d2e'}})],
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
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert len(response_json['events']) == 1
    assert len(response_json['responses']) == 1
    assert response_json['events'] == [
        {"event": "slot", "timestamp": None, "name": "kairon_action_response",
         "value": "I have failed to process your request"}]
    assert response_json['responses'][0]['text'] == "I have failed to process your request"


@responses.activate
def test_http_action_execution_script_evaluation_with_dynamic_params_and_params_list(aioresponses):
    action_name = "test_http_action_execution_script_evaluation_with_dynamic_params_and_params_list"
    Actions(name=action_name, type=ActionType.http_action.value, bot="5f50fd0a56b698ca10d35d2e", user="user").save()
    KeyVault(key="EMAIL", value="uditpandey@digite.com", bot="5f50fd0a56b698ca10d35d2e", user="user").save()
    KeyVault(key="FIRSTNAME", value="udit", bot="5f50fd0a56b698ca10d35d2e", user="user").save()
    HttpActionConfig(
        action_name=action_name,
        content_type="json",
        response=HttpActionResponse(
            value="'The value of '+`${a.b.d}`+' in '+`${a.b.d.0}`+' is '+`${a.b.d}`",
            dispatch=True, evaluation_type="script"),
        http_url="http://localhost:8081/mock",
        request_method="GET",
        dynamic_params="{\"sender_id\": \"${sender_id}\", \"user_message\": \"${user_message}\", "
                       "\"intent\": \"${intent}\", \"EMAIL\": \"${key_vault.EMAIL}\"}",
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
    resp_msg = {
        "sender_id": "default",
        "user_message": "get intents",
        "intent": "test_run",
        "user_details": {"email": "uditpandey@digite.com"}
    }
    http_url = 'http://localhost:8081/mock'
    responses.add(
        method=responses.POST,
        url=Utility.environment['evaluator']['url'],
        json={"success": True, "data": resp_msg},
        status=200,
        match=[
            responses.matchers.json_params_matcher(
                {'script': "{\"sender_id\": \"${sender_id}\", \"user_message\": \"${user_message}\", "
                           "\"intent\": \"${intent}\", \"EMAIL\": \"${key_vault.EMAIL}\"}",
                 'data': {'sender_id': 'default', 'user_message': 'get intents',
                          'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run', 'chat_log': [],
                          'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'},
                          'kairon_user_msg': None, 'session_started': None, 'bot': '5f50fd0a56b698ca10d35d2e'}})],
    )
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
    aioresponses.add(
        method=responses.GET,
        url=f"{http_url}?intent=test_run&sender_id=default&user_details=%257B%2527email%2527%253A+%2527uditpandey%2540digite.com%2527%257D&user_message=get+intents",
        body=resp_msg,
        status=200
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
                          'context': {'sender_id': 'default', 'user_message': 'get intents',
                                      'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run',
                                      'chat_log': [],
                                      'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'},
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
                          'context': {'sender_id': 'default', 'user_message': 'get intents',
                                      'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run',
                                      'chat_log': [],
                                      'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'},
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
                          'context': {'sender_id': 'default', 'user_message': 'get intents',
                                      'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run',
                                      'chat_log': [],
                                      'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'},
                                      'kairon_user_msg': None, 'session_started': None,
                                      'bot': '5f50fd0a56b698ca10d35d2e'}}})],
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
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert len(response_json['events']) == 3
    assert len(response_json['responses']) == 1
    assert response_json['events'] == [
        {"event": "slot", "timestamp": None, "name": "val_d", "value": "['red', 'buggy', 'bumpers']"},
        {"event": "slot", "timestamp": None, "name": "val_d_0", "value": "red"},
        {"event": "slot", "timestamp": None, "name": "kairon_action_response",
         "value": "The value of 2 in red is ['red', 'buggy', 'bumpers']"}]
    assert response_json['responses'][0]['text'] == "The value of 2 in red is ['red', 'buggy', 'bumpers']"
    log = ActionServerLogs.objects(action=action_name).get().to_mongo().to_dict()
    log.pop('_id')
    log.pop('timestamp')
    print(log)
    assert log == {'type': 'http_action', 'intent': 'test_run',
                   'action': 'test_http_action_execution_script_evaluation_with_dynamic_params_and_params_list',
                   'sender': 'default',
                   'headers': {'botid': '5f50fd0a56b698ca10d35d2e', 'userid': '****', 'tag': '******ot'},
                   'url': 'http://localhost:8081/mock', 'request_method': 'GET',
                   'request_params': {'sender_id': 'default', 'user_message': 'get intents', 'intent': 'test_run',
                                      'user_details': {'email': '*******************om'}},
                   'api_response': "{'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}",
                   'bot_response': "The value of 2 in red is ['red', 'buggy', 'bumpers']",
                   'messages': ['evaluation_type: script',
                                'script: {"sender_id": "${sender_id}", "user_message": "${user_message}", "intent": "${intent}", "EMAIL": "${key_vault.EMAIL}"}',
                                "data: {'sender_id': 'default', 'user_message': 'get intents', 'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run', 'chat_log': [], 'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'}, 'kairon_user_msg': None, 'session_started': None, 'bot': '5f50fd0a56b698ca10d35d2e'}",
                                'raise_err_on_failure: True',
                                "Evaluator response: {'success': True, 'data': {'sender_id': 'default', 'user_message': 'get intents', 'intent': 'test_run', 'user_details': {'email': 'uditpandey@digite.com'}}}",
                                'evaluation_type: script',
                                "script: 'The value of '+`${a.b.d}`+' in '+`${a.b.d.0}`+' is '+`${a.b.d}`",
                                "data: {'data': {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}, 'context': {'sender_id': 'default', 'user_message': 'get intents', 'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run', 'chat_log': [], 'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'}, 'kairon_user_msg': None, 'session_started': None, 'bot': '5f50fd0a56b698ca10d35d2e'}}",
                                'raise_err_on_failure: True',
                                'Evaluator response: {\'success\': True, \'data\': "The value of 2 in red is [\'red\', \'buggy\', \'bumpers\']"}',
                                'initiating slot evaluation', 'Slot: val_d', 'evaluation_type: script',
                                'script: ${a.b.d}',
                                "data: {'data': {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}, 'context': {'sender_id': 'default', 'user_message': 'get intents', 'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run', 'chat_log': [], 'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'}, 'kairon_user_msg': None, 'session_started': None, 'bot': '5f50fd0a56b698ca10d35d2e'}}",
                                'raise_err_on_failure: True',
                                'Evaluator response: {\'success\': True, \'data\': "[\'red\', \'buggy\', \'bumpers\']"}',
                                'Slot: val_d_0', 'evaluation_type: script', 'script: ${a.b.d.0}',
                                "data: {'data': {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}, 'context': {'sender_id': 'default', 'user_message': 'get intents', 'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run', 'chat_log': [], 'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'}, 'kairon_user_msg': None, 'session_started': None, 'bot': '5f50fd0a56b698ca10d35d2e'}}",
                                'raise_err_on_failure: True',
                                "Evaluator response: {'success': True, 'data': 'red'}"],
                   'bot': '5f50fd0a56b698ca10d35d2e', 'status': 'SUCCESS', 'user_msg': 'get intents'}


@responses.activate
def test_http_action_execution_script_evaluation_failure_no_dispatch(aioresponses):
    action_name = "test_http_action_execution_script_evaluation_failure_no_dispatch"
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
    aioresponses.add(
        method=responses.GET,
        url=f"{http_url}?bot=5f50fd0a56b698ca10d35d2e&user=1011&tag=from_bot",
        body=resp_msg,
        status=200
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
                          'context': {'sender_id': 'default', 'user_message': 'get intents',
                                      'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run',
                                      'chat_log': [],
                                      'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'},
                                      'kairon_user_msg': None, 'session_started': None,
                                      'bot': '5f50fd0a56b698ca10d35d2e'}}})],
    )
    responses.add(
        method=responses.POST,
        url=Utility.environment['evaluator']['url'],
        json={"success": False, "data": None},
        status=200,
        match=[
            responses.matchers.json_params_matcher(
                {'script': "${e}",
                 'data': {'data': {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}},
                          'context': {'sender_id': 'default', 'user_message': 'get intents',
                                      'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run',
                                      'chat_log': [],
                                      'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'},
                                      'kairon_user_msg': None, 'session_started': None,
                                      'bot': '5f50fd0a56b698ca10d35d2e'}}})],
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
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert len(response_json['events']) == 3
    assert len(response_json['responses']) == 0
    assert response_json['events'] == [
        {"event": "slot", "timestamp": None, "name": "val_d", "value": None},
        {"event": "slot", "timestamp": None, "name": "val_d_0", "value": None},
        {"event": "slot", "timestamp": None, "name": "kairon_action_response",
         "value": "The value of 2 in red is ['red', 'buggy', 'bumpers']"}]
    assert response_json['responses'] == []


@responses.activate
def test_http_action_execution_script_evaluation_failure_and_dispatch(aioresponses):
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
    aioresponses.add(
        method=responses.GET,
        url=f"{http_url}?bot=5f50fd0a56b698ca10d35d2e&user=1011&tag=from_bot",
        body=resp_msg,
        status=200
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
                          'context': {'sender_id': 'default', 'user_message': 'get intents',
                                      'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run',
                                      'chat_log': [],
                                      'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'},
                                      'kairon_user_msg': None, 'session_started': None,
                                      'bot': '5f50fd0a56b698ca10d35d2e'}}})],
    )
    responses.add(
        method=responses.POST,
        url=Utility.environment['evaluator']['url'],
        json={"success": False, "data": None},
        status=200,
        match=[
            responses.matchers.json_params_matcher(
                {'script': "${e}",
                 'data': {'data': {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}},
                          'context': {'sender_id': 'default', 'user_message': 'get intents',
                                      'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run',
                                      'chat_log': [],
                                      'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'},
                                      'kairon_user_msg': None, 'session_started': None,
                                      'bot': '5f50fd0a56b698ca10d35d2e'}}})],
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
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert len(response_json['events']) == 3
    assert len(response_json['responses']) == 1
    assert response_json['events'] == [
        {"event": "slot", "timestamp": None, "name": "val_d", "value": None},
        {"event": "slot", "timestamp": None, "name": "val_d_0", "value": None},
        {"event": "slot", "timestamp": None, "name": "kairon_action_response",
         "value": "The value of 2 in red is ['red', 'buggy', 'bumpers']"}]
    assert response_json['responses'][0]['text'] == "The value of 2 in red is ['red', 'buggy', 'bumpers']"


@responses.activate
def test_http_action_execution_script_evaluation_failure_and_dispatch_2(aioresponses):
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
    aioresponses.add(
        method=responses.GET,
        url=f"{http_url}?bot=5f50fd0a56b698ca10d35d2e&user=1011&tag=from_bot",
        body=resp_msg,
        status=200
    )
    responses.add(
        method=responses.POST,
        url=Utility.environment['evaluator']['url'],
        json={"success": False, "data": "The value of 2 in red is ['red', 'buggy', 'bumpers']"},
        status=200,
        match=[
            responses.matchers.json_params_matcher(
                {'script': "'The value of '+`${a.b.d}`+' in '+`${a.b.d.0}`+' is '+`${a.b.d}`",
                 'data': {'data': {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}}})],
    )
    responses.add(
        method=responses.POST,
        url=Utility.environment['evaluator']['url'],
        json={"success": False, "data": None},
        status=200,
        match=[
            responses.matchers.json_params_matcher(
                {'script': "${e}",
                 'data': {'data': {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}}})],
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
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert len(response_json['events']) == 1
    assert len(response_json['responses']) == 1
    assert response_json['events'] == [
        {"event": "slot", "timestamp": None, "name": "kairon_action_response",
         "value": "I have failed to process your request"}]
    assert response_json['responses'][0]['text'] == "I have failed to process your request"


@patch("kairon.shared.actions.utils.ActionUtility.get_action")
@patch("kairon.actions.definitions.http.ActionHTTP.retrieve_config")
@mock.patch("kairon.shared.rest_client.AioRestClient._AioRestClient__trigger", autospec=True)
def test_http_action_failed_execution(mock_trigger_request, mock_action_config, mock_action):
    action_name = "test_run_with_get"
    action = Actions(name=action_name, type=ActionType.http_action.value, bot="5f50fd0a56b698ca10d35d2e",
                     user="user")
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
    mock_trigger_request.side_effect = asyncio.TimeoutError('408')
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert len(response_json['events']) == 1
    assert len(response_json['responses']) == 1
    assert response_json['events'] == [
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
         'value': "I have failed to process your request"}]
    assert response_json['responses'][0]['text'] == "I have failed to process your request"
    log = ActionServerLogs.objects(action=action_name).get().to_mongo().to_dict()
    log.pop('_id')
    log.pop('timestamp')
    print(log)
    assert log == {'type': 'http_action', 'intent': 'test_run', 'action': 'test_run_with_get', 'sender': 'default',
                   'headers': {}, 'url': 'http://localhost:8082/mock', 'request_method': 'GET', 'request_params': {},
                   'bot_response': 'I have failed to process your request',
                   'exception': 'Request timed out: 408', 'messages': [],
                   'bot': '5f50fd0a56b698ca10d35d2e', 'status': 'FAILURE', 'user_msg': 'get intents'}


def test_http_action_missing_action_name():
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
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert response_json == None


def test_http_action_doesnotexist():
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
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert response_json == {'events': [], 'responses': []}


@responses.activate
def test_vectordb_action_execution_embedding_search_from_value():
    action_name = "test_vectordb_action_execution"
    Actions(name=action_name, type=ActionType.database_action.value, bot="5f50fd0a56b698ca10d75d2e",
            user="user").save()
    payload_body = {"ids": [0], "with_payload": True, "with_vector": True}
    DatabaseAction(
        name=action_name,
        collection='test_vectordb_action_execution',
        query_type=DbActionOperationType.embedding_search.value,
        payload=DbQuery(type="from_value", value=payload_body),
        response=HttpActionResponse(value="The value of ${data.result.0.id} is ${data.result.0.vector}"),
        set_slots=[SetSlotsFromResponse(name="vector_value", value="${data.result.0.vector}")],
        bot="5f50fd0a56b698ca10d75d2e",
        user="user"
    ).save()

    http_url = 'http://localhost:6333/collections/5f50fd0a56b698ca10d75d2e_test_vectordb_action_execution_faq_embd/points'
    resp_msg = json.dumps(
        {
            "time": 0,
            "status": "ok",
            "result": [
                {
                    "id": 0,
                    "payload": {},
                    "vector": [
                        0
                    ]
                }
            ]
        }
    )
    responses.add(
        method=responses.POST,
        url=http_url,
        body=resp_msg,
        status=200,
        match=[responses.matchers.json_params_matcher(payload_body)],
    )

    request_object = {
        "next_action": action_name,
        "tracker": {
            "sender_id": "default",
            "conversation_id": "default",
            "slots": {"bot": "5f50fd0a56b698ca10d75d2e"},
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
            "slots": {"bot": "5f50fd0a56b698ca10d75d2e"},
            "responses": {},
            "actions": [],
            "forms": {},
            "e2e_actions": []
        },
        "version": "version"
    }
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    print(response_json['events'])
    print(response_json['responses'])
    assert len(response_json['events']) == 2
    assert len(response_json['responses']) == 1
    assert response_json['events'] == [
        {'event': 'slot', 'timestamp': None, 'name': 'vector_value', 'value': '[0]'},
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response', 'value': 'The value of 0 is [0]'}]
    assert response_json['responses'][0]['text'] == "The value of 0 is [0]"
    log = ActionServerLogs.objects(action=action_name, bot='5f50fd0a56b698ca10d75d2e').get().to_mongo().to_dict()
    log.pop('_id')
    log.pop('timestamp')


@responses.activate
def test_vectordb_action_execution_payload_search_from_value():
    action_name = "test_vectordb_action_execution"
    Actions(name=action_name, type=ActionType.database_action.value, bot="5f50md0a56b698ca10d35d2e",
            user="user").save()
    payload_body = json.dumps({'filter': {'should': [{'key': 'city', 'match': {'value': 'London'}}, {'key': 'color', 'match': {'value': 'red'}}]}})
    DatabaseAction(
        name=action_name,
        collection='test_vectordb_action_execution_payload_search_from_value',
        query_type=DbActionOperationType.payload_search.value,
        payload=DbQuery(type="from_value", value=payload_body),
        response=HttpActionResponse(value="The value of ${data.0.city} with color ${data.0.color} is ${data.0.id}"),
        set_slots=[SetSlotsFromResponse(name="city_value", value="${data.0.id}")],
        bot="5f50md0a56b698ca10d35d2e",
        user="user"
    ).save()

    http_url = 'http://localhost:6333/collections/5f50md0a56b698ca10d35d2e_test_vectordb_action_execution_payload_search_from_value_faq_embd/points/scroll'
    resp_msg = json.dumps(
        [{"id": 2, "city": "London", "color": "red"}]
    )
    json_params_matcher = {'filter': {'should': [{'key': 'city', 'match': {'value': 'London'}}, {'key': 'color', 'match': {'value': 'red'}}]}}
    responses.add(
        method=responses.POST,
        url=http_url,
        body=resp_msg,
        status=200,
        match=[responses.matchers.json_params_matcher(json_params_matcher)],
    )

    request_object = {
        "next_action": action_name,
        "tracker": {
            "sender_id": "default",
            "conversation_id": "default",
            "slots": {"bot": "5f50md0a56b698ca10d35d2e"},
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
            "slots": {"bot": "5f50md0a56b698ca10d35d2e"},
            "responses": {},
            "actions": [],
            "forms": {},
            "e2e_actions": []
        },
        "version": "version"
    }
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    print(response_json['events'])
    print(response_json['responses'])
    assert len(response_json['events']) == 2
    assert len(response_json['responses']) == 1
    assert response_json['events'] == [
        {'event': 'slot', 'timestamp': None, 'name': 'city_value', 'value': '2'},
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
         'value': 'The value of London with color red is 2'}]
    assert response_json['responses'][0]['text'] == "The value of London with color red is 2"
    log = ActionServerLogs.objects(action=action_name, bot='5f50md0a56b698ca10d35d2e').get().to_mongo().to_dict()
    log.pop('_id')
    log.pop('timestamp')


@responses.activate
def test_vectordb_action_execution_payload_search_from_value_json_decode_error():
    action_name = "test_vectordb_action_execution_payload_search_from_value_json_decode_error"
    Actions(name=action_name, type=ActionType.database_action.value, bot="5f50md0a56b698ca10d35d2e",
            user="user").save()
    payload_body = "{'filter'}"
    DatabaseAction(
        name=action_name,
        collection='test_vectordb_action_execution_payload_search_from_value',
        query_type=DbActionOperationType.payload_search.value,
        payload=DbQuery(type="from_value", value=payload_body),
        response=HttpActionResponse(value="The value of ${data.0.city} with color ${data.0.color} is ${data.0.id}"),
        set_slots=[SetSlotsFromResponse(name="city_value", value="${data.0.id}")],
        bot="5f50md0a56b698ca10d35d2e",
        user="user"
    ).save()

    request_object = {
        "next_action": action_name,
        "tracker": {
            "sender_id": "default",
            "conversation_id": "default",
            "slots": {"bot": "5f50md0a56b698ca10d35d2e"},
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
            "slots": {"bot": "5f50md0a56b698ca10d35d2e"},
            "responses": {},
            "actions": [],
            "forms": {},
            "e2e_actions": []
        },
        "version": "version"
    }
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    print(response_json['events'])
    print(response_json['responses'])
    assert len(response_json['events']) == 1
    assert len(response_json['responses']) == 1
    assert response_json['events'] == [{'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response', 'value': 'I have failed to process your request.'}]
    assert response_json['responses'][0]['text'] == 'I have failed to process your request.'
    log = ActionServerLogs.objects(action=action_name, bot='5f50md0a56b698ca10d35d2e').get().to_mongo().to_dict()
    print(log)
    assert log['exception'] == "Error converting payload to JSON: {'filter'}"
    log.pop('_id')
    log.pop('timestamp')


@responses.activate
def test_vectordb_action_execution_payload_search_from_slot():
    action_name = "test_vectordb_action_execution"
    Actions(name=action_name, type=ActionType.database_action.value, bot="5f50fx0a56b698ca10d35d2e",
            user="user").save()
    slot = 'name'
    Slots(name=slot, type='text', bot='5f50fx0a56b698ca10d35d2e', user='user').save()
    payload_body = json.dumps({'filter': {
        'should': [{'key': 'city', 'match': {'value': 'London'}}, {'key': 'color', 'match': {'value': 'red'}}]}})
    DatabaseAction(
        name=action_name,
        collection='test_vectordb_action_execution_embedding_search_from_slot',
        query_type=DbActionOperationType.embedding_search.value,
        payload=DbQuery(type="from_slot", value='name'),
        response=HttpActionResponse(value="The value of ${data.result.0.id} is ${data.result.0.vector}"),
        set_slots=[SetSlotsFromResponse(name="vector_value", value="${data.result.0.vector}")],
        bot="5f50fx0a56b698ca10d35d2e",
        user="user"
    ).save()

    http_url = 'http://localhost:6333/collections/5f50fx0a56b698ca10d35d2e_test_vectordb_action_execution_embedding_search_from_slot_faq_embd/points'
    resp_msg = json.dumps(
        {
            "time": 0,
            "status": "ok",
            "result": [
                {
                    "id": 15,
                    "payload": {},
                    "vector": [
                        15
                    ]
                }
            ]
        }
    )
    responses.add(
        method=responses.POST,
        url=http_url,
        body=resp_msg,
        status=200,
    )

    request_object = {
        "next_action": action_name,
        "tracker": {
            "sender_id": "default",
            "conversation_id": "default",
            "slots": {"bot": "5f50fx0a56b698ca10d35d2e", "name": payload_body},
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
            "slots": {"bot": "5f50fx0a56b698ca10d35d2e", "name": None},
            "responses": {},
            "actions": [],
            "forms": {},
            "e2e_actions": []
        },
        "version": "version"
    }
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    print(response_json['events'])
    print(response_json['responses'])
    assert len(response_json['events']) == 2
    assert len(response_json['responses']) == 1
    assert response_json['events'] == [
        {'event': 'slot', 'timestamp': None, 'name': 'vector_value', 'value': '[15]'},
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response', 'value': 'The value of 15 is [15]'}]
    assert response_json['responses'][0]['text'] == "The value of 15 is [15]"
    log = ActionServerLogs.objects(action=action_name, bot='5f50fx0a56b698ca10d35d2e').get().to_mongo().to_dict()
    log.pop('_id')
    log.pop('timestamp')


@responses.activate
def test_vectordb_action_execution_no_response_dispatch():
    action_name = "test_vectordb_action_execution_no_response_dispatch"
    Actions(name=action_name, type=ActionType.database_action.value, bot="5f50fd0a56v098ca10d75d2e",
            user="user").save()
    payload_body = {"ids": [0], "with_payload": True, "with_vector": True}
    DatabaseAction(
        name=action_name,
        collection='test_vectordb_action_execution_no_response_dispatch',
        query_type=DbActionOperationType.embedding_search.value,
        payload=DbQuery(type="from_value", value=payload_body),
        response=HttpActionResponse(value="The value of ${data.result.0.id} is ${data.result.0.vector}",
                                    dispatch=False),
        set_slots=[SetSlotsFromResponse(name="vector_value", value="${data.result.0.vector}")],
        bot="5f50fd0a56v098ca10d75d2e",
        user="user"
    ).save()

    http_url = 'http://localhost:6333/collections/5f50fd0a56v098ca10d75d2e_test_vectordb_action_execution_no_response_dispatch_faq_embd/points'
    resp_msg = json.dumps(
        {
            "time": 0,
            "status": "ok",
            "result": [
                {
                    "id": 0,
                    "payload": {},
                    "vector": [
                        0
                    ]
                }
            ]
        }
    )
    responses.add(
        method=responses.POST,
        url=http_url,
        body=resp_msg,
        status=200,
        match=[responses.matchers.json_params_matcher(payload_body)],
    )

    request_object = {
        "next_action": action_name,
        "tracker": {
            "sender_id": "default",
            "conversation_id": "default",
            "slots": {"bot": "5f50fd0a56v098ca10d75d2e"},
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
            "slots": {"bot": "5f50fd0a56v098ca10d75d2e"},
            "responses": {},
            "actions": [],
            "forms": {},
            "e2e_actions": []
        },
        "version": "version"
    }
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    print(response_json['events'])
    print(response_json['responses'])
    assert len(response_json['events']) == 2
    assert len(response_json['responses']) == 0
    assert response_json['events'] == [
        {'event': 'slot', 'timestamp': None, 'name': 'vector_value', 'value': '[0]'},
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response', 'value': 'The value of 0 is [0]'}]
    assert response_json['responses'] == []
    log = ActionServerLogs.objects(action=action_name, bot='5f50fd0a56v098ca10d75d2e').get().to_mongo().to_dict()
    log.pop('_id')
    log.pop('timestamp')


def test_vectordb_action_execution_invalid_operation_type():
    action_name = "test_vectordb_action_execution_invalid_operation_type"
    Actions(name=action_name, type=ActionType.database_action.value, bot="5f50fd0a56v908ca10d75d2e",
            user="user").save()
    payload_body = {"ids": [0], "with_payload": True, "with_vector": True}
    DatabaseAction(
        name=action_name,
        collection='test_vectordb_action_execution_invalid_operation_type',
        query_type="vector_search",
        payload=DbQuery(type="from_value", value=payload_body),
        response=HttpActionResponse(value="The value of ${data.result.0.id} is ${data.result.0.vector}",
                                    dispatch=False),
        set_slots=[SetSlotsFromResponse(name="vector_value", value="${data.result.0.vector}")],
        bot="5f50fd0a56v908ca10d75d2e",
        user="user"
    ).save()

    request_object = {
        "next_action": action_name,
        "tracker": {
            "sender_id": "default",
            "conversation_id": "default",
            "slots": {"bot": "5f50fd0a56v908ca10d75d2e"},
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
            "slots": {"bot": "5f50fd0a56v908ca10d75d2e"},
            "responses": {},
            "actions": [],
            "forms": {},
            "e2e_actions": []
        },
        "version": "version"
    }
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert len(response_json['events']) == 1
    assert len(response_json['responses']) == 0
    assert response_json['events'] == [
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
         'value': "I have failed to process your request."}]
    assert response_json['responses'] == []
    log = ActionServerLogs.objects(action=action_name, bot='5f50fd0a56v908ca10d75d2e').get().to_mongo().to_dict()
    log.pop('_id')
    log.pop('timestamp')


@patch("kairon.shared.actions.utils.ActionUtility.get_action")
@patch("kairon.actions.definitions.database.ActionDatabase.retrieve_config")
def test_vectordb_action_failed_execution(mock_action_config, mock_action):
    action_name = "test_run_with_get_action"
    payload_body = {"ids": [0], "with_payload": True, "with_vector": True}
    action = Actions(name=action_name, type=ActionType.database_action.value, bot="5f50fd0a56b697ca10d35d2e",
                     user="user")
    action_config = DatabaseAction(
        name=action_name,
        collection='test_vectordb_action_failed_execution',
        query_type=DbActionOperationType.embedding_search.value,
        payload=DbQuery(type="from_value", value=payload_body),
        response=HttpActionResponse(value="The value of ${data.result.0.id} is ${data.result.0.vector"),
        bot="5f50fd0a56b697ca10d35d2e",
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
            "slots": {'bot': "5f50fd0a56b697ca10d35d2e"},
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
            "slots": {"bot": "5f50fd0a56b697ca10d35d2e"},
            "responses": {},
            "actions": [],
            "forms": {},
            "e2e_actions": []
        },
        "version": "version"
    }
    mock_action.side_effect = _get_action
    mock_action_config.side_effect = _get_action_config
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert len(response_json['events']) == 1
    assert len(response_json['responses']) == 1
    assert response_json['events'] == [
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
         'value': "I have failed to process your request."}]
    assert response_json['responses'][0]['text'] == "I have failed to process your request."


def test_vectordb_action_missing_action_name():
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
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert response_json == None


def test_vectordb_action_does_not_exist():
    action_name = "vectordb_action_does_not_exist"

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
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert response_json == {'events': [], 'responses': []}
    log = ActionServerLogs.objects(action=action_name).get().to_mongo().to_dict()
    assert log['exception'] == 'No action found for given bot and name'


def test_slot_set_action_from_value():
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
            response = client.post("/webhook", json=request_object)
            response_json = response.json()
            assert response.status_code == 200
            assert len(response_json['events']) == 1
            assert len(response_json['responses']) == 0
            assert response_json['events'] == [
                {'event': 'slot', 'timestamp': None, 'name': 'location', 'value': 'Mumbai'}]
            assert response_json['responses'] == []


def test_slot_set_action_reset_slot():
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
            "slots": {"bot": "5f50fd0a56b698ca10d35d2e", "location": 'Bengaluru', 'current_location': 'Bengaluru',
                      "name": "Udit", "age": 24},
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
            response = client.post("/webhook", json=request_object)
            response_json = response.json()
            assert response.status_code == 200
            assert len(response_json['events']) == 3
            assert len(response_json['responses']) == 0
            assert response_json['events'] == [{'event': 'slot', 'timestamp': None, 'name': 'location', 'value': None},
                                               {'event': 'slot', 'timestamp': None, 'name': 'name',
                                                'value': "end_user"},
                                               {'event': 'slot', 'timestamp': None, 'name': 'age', 'value': None}]
            assert response_json['responses'] == []


def test_slot_set_action_from_slot_not_present():
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
            response = client.post("/webhook", json=request_object)
            response_json = response.json()
            assert response.status_code == 200
            assert len(response_json['events']) == 1
            assert len(response_json['responses']) == 0
            assert response_json['events'] == [{'event': 'slot', 'timestamp': None, 'name': 'location', 'value': None}]
            assert response_json['responses'] == []


def test_invalid_action():
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
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert response_json == {'events': [], 'responses': []}


@responses.activate
def test_form_validation_action_valid_slot_value():
    action_name = "validate_location"
    bot = '5f50fd0a56b698ca10d35d2e'
    user = 'test_user'
    slot = 'location'
    semantic_expression = "if ((location in ['Mumbai', 'Bangalore'] && location.startsWith('M') " \
                          "&& location.endsWith('i')) || location.length() > 20) " \
                          "{return true;} else {return false;}"
    Actions(name=action_name, type=ActionType.form_validation_action.value, bot=bot, user=user).save()
    FormValidationAction(name=action_name, slot=slot, validation_semantic=semantic_expression,
                         bot=bot, user=user).save()
    Slots(name=slot, type='text', bot=bot, user=user).save()

    responses.add(
        method=responses.POST,
        url=Utility.environment['evaluator']['url'],
        json={"success": True, "data": True},
        status=200,
        match=[responses.matchers.json_params_matcher(
            {'script': semantic_expression,
             'data': {'sender_id': 'default', 'user_message': 'get intents',
                      'slot': {'bot': '5f50fd0a56b698ca10d35d2e', 'location': 'Mumbai',
                               'requested_slot': 'location'}, 'intent': 'test_run', 'chat_log': [], 'key_vault': {
                     'EMAIL': 'uditpandey@digite.com',
                     'FIRSTNAME': 'udit'
                 },
                      'kairon_user_msg': None, 'session_started': None}}
        )],
    )

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
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert response_json == {'events': [{'event': 'slot', 'timestamp': None, 'name': 'location', 'value': 'Mumbai'}],
                             'responses': []}


@responses.activate
def test_form_validation_action_with_custom_value():
    action_name = "validate_location_with_custom_value"
    bot = '5f50fd0a56b698ca10d35d2e'
    user = 'test_user'
    slot = 'location'
    semantic_expression = "if ((location in ['Mumbai', 'Bangalore'] && location.startsWith('M') " \
                          "&& location.endsWith('i')) || location.length() > 20) " \
                          "{return true;} else {return false;}"
    Actions(name=action_name, type=ActionType.form_validation_action.value, bot=bot, user=user).save()
    FormValidationAction(name=action_name, slot=slot, validation_semantic=semantic_expression, bot=bot, user=user,
                         slot_set=FormSlotSet(type=FORM_SLOT_SET_TYPE.custom.value, value="Bangalore")
                         ).save()
    Slots(name=slot, type='text', bot=bot, user=user).save()

    responses.add(
        method=responses.POST,
        url=Utility.environment['evaluator']['url'],
        json={"success": True, "data": True},
        status=200,
        match=[responses.matchers.json_params_matcher(
            {'script': semantic_expression,
             'data': {'sender_id': 'default', 'user_message': 'get intents',
                      'slot': {'bot': '5f50fd0a56b698ca10d35d2e', 'location': 'Mumbai',
                               'requested_slot': 'location'}, 'intent': 'test_run', 'chat_log': [],
                      'key_vault': {'EMAIL': 'uditpandey@digite.com',
                                    'FIRSTNAME': 'udit'
                                    },
                      'kairon_user_msg': None, 'session_started': None}}
        )],
    )

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
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert response_json == {'events': [{'event': 'slot', 'timestamp': None, 'name': 'location', 'value': 'Bangalore'}],
                             'responses': []}


@responses.activate
def test_form_validation_action_with_custom_value_none():
    action_name = "validate_location_with_custom_value_none"
    bot = '5f50fd0a56b698ca10d35d2e'
    user = 'test_user'
    slot = 'location'
    semantic_expression = "if ((location in ['Mumbai', 'Bangalore'] && location.startsWith('M') " \
                          "&& location.endsWith('i')) || location.length() > 20) " \
                          "{return true;} else {return false;}"
    Actions(name=action_name, type=ActionType.form_validation_action.value, bot=bot, user=user).save()
    FormValidationAction(name=action_name, slot=slot, validation_semantic=semantic_expression, bot=bot, user=user,
                         slot_set=FormSlotSet(type=FORM_SLOT_SET_TYPE.custom.value)).save()
    Slots(name=slot, type='text', bot=bot, user=user).save()

    responses.add(
        method=responses.POST,
        url=Utility.environment['evaluator']['url'],
        json={"success": True, "data": True},
        status=200,
        match=[responses.matchers.json_params_matcher(
            {'script': semantic_expression,
             'data': {'sender_id': 'default', 'user_message': 'get intents',
                      'slot': {'bot': '5f50fd0a56b698ca10d35d2e', 'location': 'Mumbai',
                               'requested_slot': 'location'}, 'intent': 'test_run', 'chat_log': [],
                      'key_vault': {'EMAIL': 'uditpandey@digite.com',
                                    'FIRSTNAME': 'udit'
                                    },
                      'kairon_user_msg': None, 'session_started': None}}
        )],
    )
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
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert response_json == {'events': [{'event': 'slot', 'timestamp': None, 'name': 'location', 'value': 'Mumbai'}],
                             'responses': []}


@responses.activate
def test_form_validation_action_with_form_slot_type_slot():
    action_name = "validate_current_location_with_form_slot_type_slot"
    bot = '5f50fd0a56b698ca10d35d2e'
    user = 'test_user'
    slot = 'current_location'
    semantic_expression = "if ((current_location in ['Mumbai', 'Bangalore'] && current_location.startsWith('M') " \
                          "&& current_location.endsWith('i')) || current_location.length() > 20) " \
                          "{return true;} else {return false;}"
    Actions(name=action_name, type=ActionType.form_validation_action.value, bot=bot, user=user).save()
    FormValidationAction(name=action_name, slot=slot, validation_semantic=semantic_expression, bot=bot, user=user,
                         slot_set=FormSlotSet(type=FORM_SLOT_SET_TYPE.slot.value, value="current_location")).save()
    Slots(name=slot, type='text', bot=bot, user=user).save()

    responses.add(
        method=responses.POST,
        url=Utility.environment['evaluator']['url'],
        json={"success": True, "data": True},
        status=200,
        match=[responses.matchers.json_params_matcher(
            {'script': semantic_expression,
             'data': {'sender_id': 'default', 'user_message': 'get intents',
                      'slot': {'bot': '5f50fd0a56b698ca10d35d2e', 'current_location': 'Delhi',
                               'requested_slot': 'current_location'}, 'intent': 'test_run', 'chat_log': [],
                      'key_vault': {'EMAIL': 'uditpandey@digite.com',
                                    'FIRSTNAME': 'udit'
                                    },
                      'kairon_user_msg': None, 'session_started': None}}
        )],
    )
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
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert response_json == {'events': [{'event': 'slot', 'timestamp': None, 'name': 'current_location',
                                         'value': 'Delhi'}], 'responses': []}


def test_form_validation_action_no_requested_slot():
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
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert response_json == {'events': [], 'responses': []}


def test_form_validation_action_no_validation_provided_for_slot_with_none_value():
    action_name = "slot_with_none_value"
    bot = '5f50fd0a56b698ca10d35d2f'
    user = 'test_user'
    slot = 'location'
    Actions(name=action_name, type=ActionType.form_validation_action.value, bot=bot, user=user).save()
    FormValidationAction(name=action_name, slot=slot, validation_semantic=None, bot=bot, user=user).save()
    Slots(name=slot, type='text', bot=bot, user=user).save()

    responses.add(
        method=responses.POST,
        url=Utility.environment['evaluator']['url'],
        json={"success": True, "data": False},
        status=200,
        match=[responses.matchers.json_params_matcher(
            {'script': None,
             'data': {'sender_id': 'default', 'user_message': 'get intents',
                      'slot': {'bot': '5f50fd0a56b698ca10d35d2f', 'location': None, 'requested_slot': 'location'},
                      'intent': 'test_run', 'chat_log': [], 'key_vault': {}, 'kairon_user_msg': None,
                      'session_started': None}}
        )],
    )

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
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert response_json == {'events': [{'event': 'slot', 'timestamp': None, 'name': 'location', 'value': None}],
                             'responses': []}


@responses.activate
def test_form_validation_action_valid_slot_value_with_utterance():
    action_name = "validate_user"
    bot = '5f50fd0a56b698ca10d35d2e'
    user = 'test_user'
    slot = 'user_id'
    semantic_expression = "if (!user_id.isEmpty() && user_id.endsWith('.com) && " \
                          "(user_id.length() > 4 || !user_id.contains(" ")) " \
                          "{return true;} else {return false;}"
    Actions(name=action_name, type=ActionType.form_validation_action.value, bot=bot, user=user).save()
    FormValidationAction(name=action_name, slot='location', validation_semantic=semantic_expression,
                         bot=bot, user=user).save()
    FormValidationAction(name=action_name, slot=slot, validation_semantic=semantic_expression,
                         bot=bot, user=user,
                         valid_response='that is great!').save()
    Slots(name=slot, type='text', bot=bot, user=user).save()

    responses.add(
        method=responses.POST,
        url=Utility.environment['evaluator']['url'],
        json={"success": True, "data": True},
        status=200,
        match=[responses.matchers.json_params_matcher(
            {'script': semantic_expression,
             'data': {'sender_id': 'default', 'user_message': 'get intents',
                      'slot': {'bot': '5f50fd0a56b698ca10d35d2e', 'user_id': 'pandey.udit867@gmail.com',
                               'requested_slot': 'user_id'}, 'intent': 'test_run', 'chat_log': [],
                      'key_vault': {'EMAIL': 'uditpandey@digite.com',
                                    'FIRSTNAME': 'udit'},
                      'kairon_user_msg': None, 'session_started': None}}
        )],
    )

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
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert response_json == {
        'events': [{'event': 'slot', 'timestamp': None, 'name': 'user_id', 'value': 'pandey.udit867@gmail.com'}],
        'responses': [{'text': 'that is great!', 'buttons': [], 'elements': [], 'custom': {}, 'template': None,
                       'response': None, 'image': None, 'attachment': None}]}


@responses.activate
def test_form_validation_action_invalid_slot_value():
    action_name = "validate_form_with_3_validations"
    bot = '5f50fd0a56b698ca10d35d2e'
    user = 'test_user'
    slot = 'current_location'
    semantic_expression = "if ((current_location in ['Mumbai', 'Bangalore'] && current_location.startsWith('M') " \
                          "&& current_location.endsWith('i')) || current_location.length() > 20) " \
                          "{return true;} else {return false;}"
    Actions(name=action_name, type=ActionType.form_validation_action.value, bot=bot, user=user).save()
    FormValidationAction(name=action_name, slot='name', validation_semantic=semantic_expression,
                         bot=bot, user=user).save().to_mongo().to_dict()
    FormValidationAction(name=action_name, slot='user_id', validation_semantic=semantic_expression,
                         bot=bot, user=user, valid_response='that is great!').save().to_mongo().to_dict()
    FormValidationAction(name=action_name, slot=slot, validation_semantic=semantic_expression,
                         bot=bot, user=user).save().to_mongo().to_dict()
    Slots(name=slot, type='text', bot=bot, user=user).save()

    responses.add(
        method=responses.POST,
        url=Utility.environment['evaluator']['url'],
        json={"success": True, "data": False},
        status=200,
        match=[responses.matchers.json_params_matcher(
            {'script': semantic_expression,
             'data': {'sender_id': 'default', 'user_message': 'get intents',
                      'slot': {'bot': '5f50fd0a56b698ca10d35d2e', 'current_location': 'Delhi',
                               'requested_slot': 'current_location'},
                      'intent': 'test_run', 'chat_log': [], 'key_vault': {'EMAIL': 'uditpandey@digite.com',
                                                                          'FIRSTNAME': 'udit'},
                      'kairon_user_msg': None, 'session_started': None}}
        )],
    )

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
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert response_json == {
        'events': [{'event': 'slot', 'timestamp': None, 'name': 'current_location', 'value': None}],
        'responses': []}


@responses.activate
def test_form_validation_action_invalid_slot_value_with_utterance():
    action_name = "validate_form"
    bot = '5f50fd0a56b698ca10d35d2e'
    user = 'test_user'
    slot = 'profession'
    semantic_expression = "if (!profession.isEmpty() && profession.endsWith('.com) && " \
                          "(profession.length() > 4 || !profession.contains(" ")) " \
                          "{return true;} else {return false;}"
    Actions(name=action_name, type=ActionType.form_validation_action.value, bot=bot, user=user).save()
    FormValidationAction(name=action_name, slot='some_slot', validation_semantic=semantic_expression,
                         bot=bot, user=user).save().to_mongo().to_dict()
    FormValidationAction(name=action_name, slot=slot, validation_semantic=semantic_expression,
                         bot=bot, user=user, valid_response='that is great!',
                         invalid_response='Invalid value. Please type again!').save().to_mongo().to_dict()
    Slots(name=slot, type='text', bot=bot, user=user).save()

    responses.add(
        method=responses.POST,
        url=Utility.environment['evaluator']['url'],
        json={"success": True, "data": False},
        status=200,
        match=[responses.matchers.json_params_matcher(
            {'script': semantic_expression,
             'data': {'sender_id': 'default', 'user_message': 'get intents',
                      'slot': {'bot': '5f50fd0a56b698ca10d35d2e', 'profession': 'computer programmer',
                               'requested_slot': 'profession'}, 'intent': 'test_run', 'chat_log': [],
                      'key_vault': {'EMAIL': 'uditpandey@digite.com',
                                    'FIRSTNAME': 'udit'}, 'kairon_user_msg': None, 'session_started': None}}
        )],
    )

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
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert response_json == {'events': [{'event': 'slot', 'timestamp': None, 'name': 'profession', 'value': None}],
                             'responses': [
                                 {'text': 'Invalid value. Please type again!', 'buttons': [], 'elements': [],
                                  'custom': {},
                                  'template': None, 'response': None, 'image': None, 'attachment': None}]}


def test_form_validation_action_no_validation_configured():
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
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert response_json == {
        'events': [{'event': 'slot', 'timestamp': None, 'name': 'age', 'value': 10}],
        'responses': []}

    semantic_expression = "if (age > 10 && age < 70) {return true;} else {return false;}"
    FormValidationAction(name=action_name, slot='name', validation_semantic=semantic_expression,
                         bot=bot, user=user, valid_response='that is great!').save()
    FormValidationAction(name=action_name, slot='occupation', validation_semantic=semantic_expression,
                         bot=bot, user=user, valid_response='that is great!').save()
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert response_json == {
        'events': [{'event': 'slot', 'timestamp': None, 'name': 'age', 'value': 10}],
        'responses': []}


def test_form_validation_action_slot_type_not_found():
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
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert response_json == {
        'events': [{'event': 'slot', 'timestamp': None, 'name': 'reservation_id', 'value': "10974872t49"}],
        'responses': [{'text': 'that is great!', 'buttons': [], 'elements': [], 'custom': {}, 'template': None,
                       'response': None, 'image': None, 'attachment': None}]}


def test_form_validation_action_with_is_required_false():
    action_name = "validate_with_required_false"
    bot = '5f50fd0a56b698ca10d35d2e'
    user = 'test_user'
    slot = 'location'
    Actions(name=action_name, type=ActionType.form_validation_action.value, bot=bot, user=user).save()
    FormValidationAction(name=action_name, validation_semantic=None, is_required=False, slot=slot,
                         bot=bot, user=user, valid_response='that is great!',
                         invalid_response='Invalid value. Please type again!').save()

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
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert response_json == {'events': [{'event': 'slot', 'timestamp': None, 'name': 'location', 'value': "Mumbai"}],
                             'responses': [
                                 {'text': 'that is great!', 'buttons': [], 'elements': [], 'custom': {},
                                  'template': None,
                                  'response': None, 'image': None, 'attachment': None}]}


@responses.activate
def test_form_validation_action_with_is_required_false_and_semantics():
    action_name = "validate_with_required_false_and_semantics"
    bot = '5f50fd0a56b698ca10d35d2e'
    user = 'test_user'
    slot = 'current_location'
    semantic_expression = "if ((current_location in ['Mumbai', 'Bangalore'] && current_location.startsWith('M') " \
                          "&& current_location.endsWith('i')) || current_location.length() > 20) " \
                          "{return true;} else {return false;}"
    Actions(name=action_name, type=ActionType.form_validation_action.value, bot=bot, user=user).save()
    FormValidationAction(name=action_name, validation_semantic=semantic_expression, is_required=False, slot=slot,
                         bot=bot, user=user, valid_response='that is great!',
                         invalid_response='Invalid value. Please type again!').save()

    responses.add(
        method=responses.POST,
        url=Utility.environment['evaluator']['url'],
        json={"success": True, "data": False},
        status=200,
        match=[responses.matchers.json_params_matcher(
            {'script': semantic_expression,
             'data': {'sender_id': 'default', 'user_message': 'get intents',
                      'slot': {'bot': '5f50fd0a56b698ca10d35d2e', 'current_location': 'Delhi',
                               'requested_slot': 'current_location'}, 'intent': 'test_run', 'chat_log': [],
                      'key_vault': {'EMAIL': 'uditpandey@digite.com',
                                    'FIRSTNAME': 'udit'}, 'kairon_user_msg': None, 'session_started': None}}
        )],
    )

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
            "slots": {"bot": "5f50fd0a56b698ca10d35d2e", "location": None},
            "responses": {},
            "actions": [],
            "forms": {},
            "e2e_actions": []
        },
        "version": "version"
    }
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert response_json == {
        'events': [{'event': 'slot', 'timestamp': None, 'name': 'current_location', 'value': None}],
        'responses': [
            {'text': 'Invalid value. Please type again!', 'buttons': [], 'elements': [], 'custom': {},
             'template': None, 'response': None, 'image': None, 'attachment': None}]}


def test_form_validation_action_with_is_required_true():
    action_name = "validate_with_required_true"
    bot = '5f50fd0a56b698ca10d35d2e'
    user = 'test_user'
    slot = 'user_id'
    Actions(name=action_name, type=ActionType.form_validation_action.value, bot=bot, user=user).save()
    FormValidationAction(name=action_name, validation_semantic=None, is_required=True, slot=slot,
                         bot=bot, user=user, valid_response='that is great!',
                         invalid_response='Invalid value. Please type again!').save()

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
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert response_json == {
        'events': [{'event': 'slot', 'timestamp': None, 'name': 'user_id', 'value': 'pandey.udit867@gmail.com'}],
        'responses': [{'text': 'that is great!', 'buttons': [], 'elements': [], 'custom': {}, 'template': None,
                       'response': None, 'image': None, 'attachment': None}]}


def test_form_validation_action_with_is_required_true_and_no_slot():
    action_name = "validate_with_required_true_and_no_slot"
    bot = '5f50fd0a56b698ca10d35d2e'
    user = 'test_user'
    slot = 'reservation_id'
    Actions(name=action_name, type=ActionType.form_validation_action.value, bot=bot, user=user).save()
    FormValidationAction(name=action_name, validation_semantic=None, is_required=True, slot=slot,
                         bot=bot, user=user, valid_response='that is great!',
                         invalid_response='Invalid value. Please type again!').save()

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
            "slots": {"bot": "5f50fd0a56b698ca10d35d2e", "location": None},
            "responses": {},
            "actions": [],
            "forms": {},
            "e2e_actions": []
        },
        "version": "version"
    }
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert response_json == {'events': [{'event': 'slot', 'timestamp': None, 'name': 'reservation_id', 'value': None}],
                             'responses': [
                                 {'text': 'Invalid value. Please type again!', 'buttons': [], 'elements': [],
                                  'custom': {},
                                  'template': None, 'response': None, 'image': None, 'attachment': None}]}


@responses.activate
def test_form_validation_action_with_is_required_true_and_semantics():
    action_name = "validate_with_required_true_and_semantics"
    bot = '5f50fd0a56b698ca10d35d2e'
    user = 'test_user'
    slot = 'location'
    semantic_expression = "if ((location in ['Mumbai', 'Bangalore'] && location.startsWith('M') " \
                          "&& location.endsWith('i')) || location.length() > 20) " \
                          "{return true;} else {return false;}"
    Actions(name=action_name, type=ActionType.form_validation_action.value, bot=bot, user=user).save()
    FormValidationAction(name=action_name, validation_semantic=semantic_expression, is_required=True, slot=slot,
                         bot=bot, user=user, valid_response='that is great!',
                         invalid_response='Invalid value. Please type again!').save()

    responses.add(
        method=responses.POST,
        url=Utility.environment['evaluator']['url'],
        json={"success": True, "data": True},
        status=200,
        match=[responses.matchers.json_params_matcher(
            {'script': semantic_expression,
             'data': {'sender_id': 'default', 'user_message': 'get intents',
                      'slot': {'bot': '5f50fd0a56b698ca10d35d2e', 'location': 'Mumbai',
                               'requested_slot': 'location'}, 'intent': 'test_run', 'chat_log': [],
                      'key_vault': {'EMAIL': 'uditpandey@digite.com',
                                    'FIRSTNAME': 'udit'
                                    },
                      'kairon_user_msg': None, 'session_started': None}}
        )],
    )

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
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert response_json == {'events': [{'event': 'slot', 'timestamp': None, 'name': 'location', 'value': "Mumbai"}],
                             'responses': [
                                 {'text': 'that is great!', 'buttons': [], 'elements': [], 'custom': {},
                                  'template': None,
                                  'response': None, 'image': None, 'attachment': None}]}


@responses.activate
@patch("kairon.shared.actions.utils.ActionUtility.get_action")
@patch("kairon.actions.definitions.email.ActionEmail.retrieve_config")
@patch("kairon.shared.utils.SMTP", autospec=True)
def test_email_action_execution_script_evaluation(mock_smtp, mock_action_config, mock_action):
    Utility.email_conf['email']['templates']['custom_text_mail'] = open('template/emails/custom_text_mail.html',
                                                                        'rb').read().decode()

    bot = "5f50fd0a65b698ca10d35d2e"
    user = "udit.pandey"

    action_name = "test_run_email_script_action"
    action = Actions(name=action_name, type=ActionType.email_action.value, bot="5f50fd0a56b698ca10d35d2e",
                     user="user")
    action_config = EmailActionConfig(
        action_name=action_name,
        smtp_url="test.localhost",
        smtp_port=293,
        smtp_password=CustomActionRequestParameters(key='smtp_password', value="test"),
        from_email="test@demo.com",
        subject="test script",
        to_email=["test@test.com"],
        response="Email Triggered",
        custom_text=CustomActionRequestParameters(key="custom_text", value="custom_mail_text",
                                                  parameter_type=ActionParameterType.slot.value),
        bot=bot,
        user=user
    )

    def _get_action(*arge, **kwargs):
        return action.to_mongo().to_dict()

    def _get_action_config(*arge, **kwargs):
        return action_config.to_mongo().to_dict()

    request_object = json.load(open("tests/testing_data/actions/action-request.json"))
    request_object["tracker"]["slots"]["bot"] = bot
    request_object["tracker"]["slots"]["custom_mail_text"] = "The user has id udit.pandey"
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
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert len(response_json['events']) == 1
    assert len(response_json['responses']) == 1
    assert response_json['events'] == [
        {"event": "slot", "timestamp": None, "name": "kairon_action_response",
         "value": "Email Triggered"}]
    assert response_json['responses'][0]['text'] == "Email Triggered"

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
@patch("kairon.shared.utils.SMTP", autospec=True)
def test_email_action_execution(mock_smtp, mock_action_config, mock_action):
    Utility.email_conf['email']['templates']['conversation'] = open('template/emails/conversation.html',
                                                                    'rb').read().decode()
    Utility.email_conf['email']['templates']['bot_msg_conversation'] = open(
        'template/emails/bot_msg_conversation.html', 'rb').read().decode()
    Utility.email_conf['email']['templates']['user_msg_conversation'] = open(
        'template/emails/user_msg_conversation.html', 'rb').read().decode()
    Utility.email_conf['email']['templates']['button_template'] = open('template/emails/button.html',
                                                                       'rb').read().decode()

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
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert len(response_json['events']) == 1
    assert len(response_json['responses']) == 1
    assert response_json['events'] == [
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
         'value': "Email Triggered"}]
    assert response_json['responses'][0]['text'] == "Email Triggered"
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
def test_email_action_execution_varied_utterances(mock_smtp, mock_action_config, mock_action):
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
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert len(response_json['events']) == 1
    assert len(response_json['responses']) == 1
    assert response_json['events'] == [
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
         'value': "Email Triggered"}]
    assert response_json['responses'][0]['text'] == "Email Triggered"
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
                            {"text": "hi", "payload": "hi"}, {"text": "bye", "payload": "/goodbye"}],
                                 'attachment': None,
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
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert len(response_json['events']) == 1
    assert len(response_json['responses']) == 1
    assert response_json['events'] == [
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
         'value': "Email Triggered"}]
    assert response_json['responses'][0]['text'] == "Email Triggered"
    logs = ActionServerLogs.objects(type=ActionType.email_action.value).order_by("-id").first()
    assert logs.status == "SUCCESS"


@patch("kairon.shared.actions.utils.ActionUtility.get_action")
@patch("kairon.actions.definitions.email.ActionEmail.retrieve_config")
def test_email_action_failed_execution(mock_action_config, mock_action):
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
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert len(response_json['events']) == 1
    assert len(response_json['responses']) == 1
    assert response_json['events'] == [
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
         'value': "I have failed to process your request"}]
    assert response_json['responses'][0]['text'] == "I have failed to process your request"
    logs = ActionServerLogs.objects(type=ActionType.email_action.value).order_by("-id").first()
    assert logs.status == "FAILURE"


def test_email_action_execution_action_not_exist():
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
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert len(response_json['events']) == 0
    assert len(response_json['responses']) == 0


def test_google_search_action_not_found():
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
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert len(response_json['events']) == 0
    assert len(response_json['responses']) == 0


def test_process_google_search_action():
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
        response = client.post("/webhook", json=request_object)
        response_json = response.json()
        assert response.status_code == 200
        assert response_json == {'events': [{
            'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
            'value': 'Kanban visualizes both the process (the workflow) and the actual work passing through that process.\nTo know more, please visit: <a href = "https://www.digite.com/kanban/what-is-kanban/" target="_blank" >Kanban</a>'
        }],
            'responses': [{
                'text': 'Kanban visualizes both the process (the workflow) and the actual work passing through that process.\nTo know more, please visit: <a href = "https://www.digite.com/kanban/what-is-kanban/" target="_blank" >Kanban</a>',
                'buttons': [], 'elements': [], 'custom': {}, 'template': None, 'response': None, 'image': None,
                'attachment': None
            }]}

    def _run_action(*args, **kwargs):
        assert args == ('1234567890', 'asdfg::123456', 'my custom text')
        assert kwargs == {'num': 1, 'website': None}
        return [{
            'title': 'Kanban',
            'text': 'Kanban visualizes both the process (the workflow) and the actual work passing through that process.',
            'link': "https://www.digite.com/kanban/what-is-kanban/"
        }]

    request_object["tracker"]["latest_message"] = {
        'text': f'/action_google_search{{"{KAIRON_USER_MSG_ENTITY}": "my custom text"}}',
        'intent_ranking': [{'name': 'test_run'}],
        "entities": [{"value": "my custom text", "entity": KAIRON_USER_MSG_ENTITY}]
    }
    with patch.object(ActionUtility, "perform_google_search") as mocked:
        mocked.side_effect = _run_action
        response = client.post("/webhook", json=request_object)
        response_json = response.json()
        assert response.status_code == 200
        assert response_json == {'events': [{
            'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
            'value': 'Kanban visualizes both the process (the workflow) and the actual work passing through that process.\nTo know more, please visit: <a href = "https://www.digite.com/kanban/what-is-kanban/" target="_blank" >Kanban</a>'
        }],
            'responses': [{
                'text': 'Kanban visualizes both the process (the workflow) and the actual work passing through that process.\nTo know more, please visit: <a href = "https://www.digite.com/kanban/what-is-kanban/" target="_blank" >Kanban</a>',
                'buttons': [], 'elements': [], 'custom': {}, 'template': None, 'response': None, 'image': None,
                'attachment': None
            }]}

    def _run_action(*args, **kwargs):
        assert args == ('1234567890', 'asdfg::123456', '/action_google_search')
        assert kwargs == {'num': 1, 'website': None}
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
        response = client.post("/webhook", json=request_object)
        response_json = response.json()
        assert response.status_code == 200
        assert response_json == {'events': [{
            'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
            'value': 'Kanban visualizes both the process (the workflow) and the actual work passing through that process.\nTo know more, please visit: <a href = "https://www.digite.com/kanban/what-is-kanban/" target="_blank" >Kanban</a>'
        }],
            'responses': [{
                'text': 'Kanban visualizes both the process (the workflow) and the actual work passing through that process.\nTo know more, please visit: <a href = "https://www.digite.com/kanban/what-is-kanban/" target="_blank" >Kanban</a>',
                'buttons': [], 'elements': [], 'custom': {}, 'template': None, 'response': None, 'image': None,
                'attachment': None
            }]}


def test_process_google_search_action_dispatch_false():
    action_name = "custom_search_action"
    bot = "5f50fd0a56b698asdfghjkiuytre"
    user = 'test_user'
    Actions(name=action_name, type=ActionType.google_search_action.value, bot=bot, user='test_user').save()
    GoogleSearchAction(name=action_name, api_key=CustomActionRequestParameters(value='1234567890'),
                       search_engine_id='asdfg::123456', bot=bot, user=user, dispatch_response=False,
                       set_slot="google_response").save()

    def _run_action(*args, **kwargs):
        return [{
            'title': 'Kanban',
            'text': 'Kanban visualizes both the process (the workflow) and the actual work passing through that process.',
            'link': "https://www.digite.com/kanban/what-is-kanban/"
        }]

    expected_resp = 'Kanban visualizes both the process (the workflow) and the actual work passing through that process.\nTo know more, please visit: <a href = "https://www.digite.com/kanban/what-is-kanban/" target="_blank" >Kanban</a>'
    request_object = json.load(open("tests/testing_data/actions/action-request.json"))
    request_object["tracker"]["slots"]["bot"] = bot
    request_object["next_action"] = action_name
    request_object["tracker"]["sender_id"] = user
    request_object["tracker"]["latest_message"]['text'] = "what is Kanban?"

    with patch.object(ActionUtility, "perform_google_search") as mocked:
        mocked.side_effect = _run_action
        response = client.post("/webhook", json=request_object)
        response_json = response.json()
        assert response.status_code == 200
        assert response_json == {'events': [
            {'event': 'slot', 'timestamp': None, 'name': 'google_response', 'value': expected_resp},
            {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response', 'value': expected_resp},
        ], 'responses': []}


def test_process_google_search_action_globally():
    action_name = "test_process_google_search_action_globally"
    bot = "5f50fd0a56b698asdfghjkiuytre"
    user = 'test_user'
    Actions(name=action_name, type=ActionType.google_search_action.value, bot=bot, user='test_user').save()
    GoogleSearchAction(name=action_name, search_engine_id='asdfg::123456', bot=bot, user=user,
                       dispatch_response=True, set_slot="google_response", website="https://nimblework.com").save()

    def _run_action(*args, **kwargs):
        assert args == (None, 'asdfg::123456', 'what is Kanban?',)
        assert kwargs == {'num': 1, 'website': "https://nimblework.com"}
        return [{
            'title': 'Kanban',
            'text': 'Kanban visualizes both the process (the workflow) and the actual work passing through that process.',
            'link': "https://www.digite.com/kanban/what-is-kanban/"
        }]

    expected_resp = 'Kanban visualizes both the process (the workflow) and the actual work passing through that process.\nTo know more, please visit: <a href = "https://www.digite.com/kanban/what-is-kanban/" target="_blank" >Kanban</a>'
    request_object = json.load(open("tests/testing_data/actions/action-request.json"))
    request_object["tracker"]["slots"]["bot"] = bot
    request_object["next_action"] = action_name
    request_object["tracker"]["sender_id"] = user
    request_object["tracker"]["latest_message"]['text'] = "what is Kanban?"

    with patch.object(ActionUtility, "perform_google_search") as mocked:
        mocked.side_effect = _run_action
        response = client.post("/webhook", json=request_object)
        response_json = response.json()
        assert response.status_code == 200
        assert response_json == {'events': [
            {'event': 'slot', 'timestamp': None, 'name': 'google_response', 'value': expected_resp},
            {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response', 'value': expected_resp},
        ],
            'responses': [{
                'text': 'Kanban visualizes both the process (the workflow) and the actual work passing through that process.\nTo know more, please visit: <a href = "https://www.digite.com/kanban/what-is-kanban/" target="_blank" >Kanban</a>',
                'buttons': [], 'elements': [], 'custom': {}, 'template': None, 'response': None,
                'image': None, 'attachment': None}]}


def test_process_google_search_action_globally_dispatch_false():
    action_name = "test_process_google_search_action_globally_dispatch_false"
    bot = "5f50fd0a56b698asdfghjkiuytre"
    user = 'test_user'
    Actions(name=action_name, type=ActionType.google_search_action.value, bot=bot, user='test_user').save()
    GoogleSearchAction(name=action_name, search_engine_id='asdfg::123456', bot=bot, user=user,
                       dispatch_response=False, set_slot="google_response").save()

    def _run_action(*args, **kwargs):
        return [{
            'title': 'Kanban',
            'text': 'Kanban visualizes both the process (the workflow) and the actual work passing through that process.',
            'link': "https://www.digite.com/kanban/what-is-kanban/"
        }]

    expected_resp = 'Kanban visualizes both the process (the workflow) and the actual work passing through that process.\nTo know more, please visit: <a href = "https://www.digite.com/kanban/what-is-kanban/" target="_blank" >Kanban</a>'
    request_object = json.load(open("tests/testing_data/actions/action-request.json"))
    request_object["tracker"]["slots"]["bot"] = bot
    request_object["next_action"] = action_name
    request_object["tracker"]["sender_id"] = user
    request_object["tracker"]["latest_message"]['text'] = "what is Kanban?"

    with patch.object(ActionUtility, "perform_google_search") as mocked:
        mocked.side_effect = _run_action
        response = client.post("/webhook", json=request_object)
        response_json = response.json()
        assert response.status_code == 200
        assert response_json == {'events': [
            {'event': 'slot', 'timestamp': None, 'name': 'google_response', 'value': expected_resp},
            {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response', 'value': expected_resp},
        ], 'responses': []}


def test_process_google_search_action_failure():
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
        response = client.post("/webhook", json=request_object)
        response_json = response.json()
        assert response.status_code == 200
        assert response_json == {'events': [{'event': 'slot', 'timestamp': None,
                                             'name': 'kairon_action_response',
                                             'value': 'I have failed to process your request.'}],
                                 'responses': [{'text': 'I have failed to process your request.',
                                                'buttons': [], 'elements': [], 'custom': {},
                                                'template': None,
                                                'response': None, 'image': None, 'attachment': None}]}


def test_process_google_search_action_no_results():
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
        response = client.post("/webhook", json=request_object)
        response_json = response.json()
        assert response_json == {'events': [{'event': 'slot', 'timestamp': None,
                                             'name': 'kairon_action_response',
                                             'value': 'I have failed to process your request.'}],
                                 'responses': [
                                     {'text': 'I have failed to process your request.', 'buttons': [],
                                      'elements': [],
                                      'custom': {}, 'template': None, 'response': None,
                                      'image': None, 'attachment': None}]}


def test_web_search_action_not_found():
    action_name = "public_search_action"
    bot = "5f51zd0a56b698ca10d35d2e"
    Actions(name=action_name, type=ActionType.web_search_action.value, bot=bot, user='test_user').save()

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
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert len(response_json['events']) == 0
    assert len(response_json['responses']) == 0


def test_process_web_search_action():
    action_name = "public_search_action_one"
    bot = "5f51zd0a56b698ca10d35d2e"
    user = 'test_user'
    Actions(name=action_name, type=ActionType.web_search_action.value, bot=bot, user='test_user').save()
    WebSearchAction(name=action_name, website="https://www.w3schools.com/", topn=1,
                    set_slot='public_search_response', bot=bot, user=user).save()

    def _perform_web_search(*args, **kwargs):
        assert args == ('What is data?',)
        assert kwargs == {'topn': 1, 'website': 'https://www.w3schools.com/'}
        return [{
            'title': 'Data Science Introduction - W3Schools',
            'text': "Data Science is a combination of multiple disciplines that uses statistics, data analysis, and machine learning to analyze data and to extract knowledge and insights from it. What is Data Science? Data Science is about data gathering, analysis and decision-making.",
            'link': 'https://www.w3schools.com/datascience/ds_introduction.asp'
        }]

    request_object = {
        "next_action": action_name,
        "tracker": {
            "sender_id": "default",
            "conversation_id": "default",
            "slots": {"bot": bot, "to_email": "test@test.com"},
            "latest_message": {'text': 'What is data?', 'intent_ranking': [{'name': 'test_run'}]},
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
            "slots": {"bot": "5f51zd0a56b698ca10d35d2e"},
            "responses": {},
            "actions": [],
            "forms": {},
            "e2e_actions": []
        },
        "version": "version"
    }
    with patch.object(ActionUtility, "perform_web_search") as mocked:
        mocked.side_effect = _perform_web_search
        response = client.post("/webhook", json=request_object)
        response_json = response.json()
        assert response.status_code == 200
        assert response_json == {'events': [
            {'event': 'slot', 'timestamp': None, 'name': 'public_search_response',
             'value': 'Data Science is a combination of multiple disciplines that uses statistics, data analysis, and machine learning to analyze data and to extract knowledge and insights from it. What is Data Science? Data Science is about data gathering, analysis and decision-making.\nTo know more, please visit: <a href = "https://www.w3schools.com/datascience/ds_introduction.asp" target="_blank" >Data Science Introduction - W3Schools</a>'},
            {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
             'value': 'Data Science is a combination of multiple disciplines that uses statistics, data analysis, and machine learning to analyze data and to extract knowledge and insights from it. What is Data Science? Data Science is about data gathering, analysis and decision-making.\nTo know more, please visit: <a href = "https://www.w3schools.com/datascience/ds_introduction.asp" target="_blank" >Data Science Introduction - W3Schools</a>'}],
            'responses': [
                {
                    'text': 'Data Science is a combination of multiple disciplines that uses statistics, data analysis, and machine learning to analyze data and to extract knowledge and insights from it. What is Data Science? Data Science is about data gathering, analysis and decision-making.\nTo know more, please visit: <a href = "https://www.w3schools.com/datascience/ds_introduction.asp" target="_blank" >Data Science Introduction - W3Schools</a>',
                    'buttons': [], 'elements': [], 'custom': {}, 'template': None, 'response': None, 'image': None,
                    'attachment': None}]}
    log = ActionServerLogs.objects(bot=bot, type=ActionType.web_search_action.value, status="SUCCESS").get()
    assert log['bot_response'] == 'Data Science is a combination of multiple disciplines that uses statistics, data analysis, and machine learning to analyze data and to extract knowledge and insights from it. What is Data Science? Data Science is about data gathering, analysis and decision-making.\nTo know more, please visit: <a href = "https://www.w3schools.com/datascience/ds_introduction.asp" target="_blank" >Data Science Introduction - W3Schools</a>'


@responses.activate
def test_process_web_search_action_with_search_engine_url():
    Utility.load_environment()
    action_name = "public_search_action_with_search_engine_url"
    bot = "5f51zd0a56b698ca10d35d2e"
    user = 'test_user'
    search_engine_url = "https://duckduckgo.com/"
    Actions(name=action_name, type=ActionType.web_search_action.value, bot=bot, user='test_user').save()
    WebSearchAction(name=action_name,
                    set_slot='public_search_response', bot=bot, user=user).save()

    responses.add(
        method=responses.POST,
        url=search_engine_url,
        json={"success": True, "data": [{"title": 'Data Science: Definition, Lifecycle, Skills and Tools | IBM', "description": "What is data science? Data science combines math and statistics, specialized programming, advanced analytics, artificial intelligence (AI), and machine learning with specific subject matter expertise to uncover actionable insights hidden in an organization's data. These insights can be used to guide decision making and strategic planning.",
                        "url": "https://www.ibm.com/topics/data-science"}], "error_code": 0},
        status=200,
        match=[
            responses.matchers.json_params_matcher({
            "text": 'What is data science?', "site": '', "topn": 1
        })],
    )

    request_object = {
        "next_action": action_name,
        "tracker": {
            "sender_id": "default",
            "conversation_id": "default",
            "slots": {"bot": bot, "to_email": "test@test.com"},
            "latest_message": {'text': 'What is data science?', 'intent_ranking': [{'name': 'test_run'}]},
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
            "slots": {"bot": "5f51zd0a56b698ca10d35d2e"},
            "responses": {},
            "actions": [],
            "forms": {},
            "e2e_actions": []
        },
        "version": "version"
    }
    with mock.patch.dict(Utility.environment, {'web_search': {"trigger_task": False, "url": search_engine_url}}):
        response = client.post("/webhook", json=request_object)
        response_json = response.json()
        assert response.status_code == 200
        assert response_json == {'events': [
            {'event': 'slot', 'timestamp': None, 'name': 'public_search_response', 'value': "What is data science? Data science combines math and statistics, specialized programming, advanced analytics, artificial intelligence (AI), and machine learning with specific subject matter expertise to uncover actionable insights hidden in an organization's data. These insights can be used to guide decision making and strategic planning.\nTo know more, please visit: <a href = \"https://www.ibm.com/topics/data-science\" target=\"_blank\" >Data Science: Definition, Lifecycle, Skills and Tools | IBM</a>"},
            {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response', 'value': "What is data science? Data science combines math and statistics, specialized programming, advanced analytics, artificial intelligence (AI), and machine learning with specific subject matter expertise to uncover actionable insights hidden in an organization's data. These insights can be used to guide decision making and strategic planning.\nTo know more, please visit: <a href = \"https://www.ibm.com/topics/data-science\" target=\"_blank\" >Data Science: Definition, Lifecycle, Skills and Tools | IBM</a>"}],
            'responses': [
                {'text': "What is data science? Data science combines math and statistics, specialized programming, advanced analytics, artificial intelligence (AI), and machine learning with specific subject matter expertise to uncover actionable insights hidden in an organization's data. These insights can be used to guide decision making and strategic planning.\nTo know more, please visit: <a href = \"https://www.ibm.com/topics/data-science\" target=\"_blank\" >Data Science: Definition, Lifecycle, Skills and Tools | IBM</a>",
                 'buttons': [], 'elements': [], 'custom': {}, 'template': None, 'response': None, 'image': None, 'attachment': None}]}


def test_process_web_search_action_with_kairon_user_msg_entity():
    action_name = "public_search_action_one_kairon_user_msg_entity"
    bot = "5f51zd0a56b698ca10d35d2e"
    user = 'test_user'
    Actions(name=action_name, type=ActionType.web_search_action.value, bot=bot, user='test_user').save()
    WebSearchAction(name=action_name, set_slot='public_search_response', topn=2, bot=bot,
                    user=user).save()

    def _perform_web_search(*args, **kwargs):
        assert args == ('my public search text',)
        assert kwargs == {'topn': 2, 'website': None}
        return [
            {'title': 'What is Data Science? | IBM',
             'text': 'Data science combines math, statistics, programming, analytics, AI, and machine learning to uncover insights from data. Learn how data science works, what it entails, and how it differs from data science and BI.',
             'link': 'https://www.ibm.com/topics/data-science'},
            {'title': 'What Is Data Science? Definition, Examples, Jobs, and More',
             'text': 'Data science is an interdisciplinary field that uses algorithms, procedures, and processes to examine large amounts of data in order to uncover hidden patterns, generate insights, and direct decision-making.',
             'link': 'https://www.coursera.org/articles/what-is-data-science'}]

    request_object = {
        "next_action": action_name,
        "tracker": {
            "sender_id": "default",
            "conversation_id": "default",
            "slots": {"bot": bot, "to_email": "test@test.com"},
            "latest_message": {
                'text': f'/action_public_search{{"{KAIRON_USER_MSG_ENTITY}": "my public search text"}}',
                'intent_ranking': [{'name': 'test_run'}],
                "entities": [{"value": "my public search text", "entity": KAIRON_USER_MSG_ENTITY}]},
            "latest_event_time": 1537645578.314389,
            "followup_action": "action_listen",
            "paused": False,
            "events": [
                {"event": "action", "timestamp": 1594907100.12764, "name": "action_session_start",
                 "policy": None,
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
                 "parse_data": {"intent": {"name": "test intent", "confidence": 0.253578245639801},
                                "entities": [],
                                "intent_ranking": [{"name": "test intent", "confidence": 0.253578245639801},
                                                   {"name": "goodbye", "confidence": 0.1504897326231},
                                                   {"name": "greet", "confidence": 0.138640150427818},
                                                   {"name": "affirm", "confidence": 0.0857767835259438},
                                                   {"name": "smalltalk_human",
                                                    "confidence": 0.0721133947372437},
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
            "slots": {"bot": "5f51zd0a56b698ca10d35d2e"},
            "responses": {},
            "actions": [],
            "forms": {},
            "e2e_actions": []
        },
        "version": "version"
    }
    with patch.object(ActionUtility, "perform_web_search") as mocked:
        mocked.side_effect = _perform_web_search
        response = client.post("/webhook", json=request_object)
        response_json = response.json()
        assert response.status_code == 200
        assert response_json == {'events': [
            {'event': 'slot', 'timestamp': None, 'name': 'public_search_response', 'value': 'Data science combines math, statistics, programming, analytics, AI, and machine learning to uncover insights from data. Learn how data science works, what it entails, and how it differs from data science and BI.\nTo know more, please visit: <a href = "https://www.ibm.com/topics/data-science" target="_blank" >What is Data Science? | IBM</a>\n\nData science is an interdisciplinary field that uses algorithms, procedures, and processes to examine large amounts of data in order to uncover hidden patterns, generate insights, and direct decision-making.\nTo know more, please visit: <a href = "https://www.coursera.org/articles/what-is-data-science" target="_blank" >What Is Data Science? Definition, Examples, Jobs, and More</a>'},
            {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response', 'value': 'Data science combines math, statistics, programming, analytics, AI, and machine learning to uncover insights from data. Learn how data science works, what it entails, and how it differs from data science and BI.\nTo know more, please visit: <a href = "https://www.ibm.com/topics/data-science" target="_blank" >What is Data Science? | IBM</a>\n\nData science is an interdisciplinary field that uses algorithms, procedures, and processes to examine large amounts of data in order to uncover hidden patterns, generate insights, and direct decision-making.\nTo know more, please visit: <a href = "https://www.coursera.org/articles/what-is-data-science" target="_blank" >What Is Data Science? Definition, Examples, Jobs, and More</a>'}],
            'responses': [
                {'text': 'Data science combines math, statistics, programming, analytics, AI, and machine learning to uncover insights from data. Learn how data science works, what it entails, and how it differs from data science and BI.\nTo know more, please visit: <a href = "https://www.ibm.com/topics/data-science" target="_blank" >What is Data Science? | IBM</a>\n\nData science is an interdisciplinary field that uses algorithms, procedures, and processes to examine large amounts of data in order to uncover hidden patterns, generate insights, and direct decision-making.\nTo know more, please visit: <a href = "https://www.coursera.org/articles/what-is-data-science" target="_blank" >What Is Data Science? Definition, Examples, Jobs, and More</a>',
                 'buttons': [], 'elements': [], 'custom': {}, 'template': None, 'response': None, 'image': None, 'attachment': None}]}


def test_process_web_search_action_without_kairon_user_msg_entity():
    action_name = "public_search_action_one_without_kairon_user_msg_entity"
    bot = "5f51zd0a56b698ca10d35d6z"
    user = 'test_user'
    Actions(name=action_name, type=ActionType.web_search_action.value, bot=bot, user='test_user').save()
    WebSearchAction(name=action_name, set_slot='public_search_response', topn=2, bot=bot,
                    user=user).save()

    def _perform_web_search(*args, **kwargs):
        assert args == ('/action_public_search',)
        assert kwargs == {'topn': 2, 'website': None}
        return [
            {'title': 'What is Data Science? | IBM',
             'text': 'Data science combines math, statistics, programming, analytics, AI, and machine learning to uncover insights from data. Learn how data science works, what it entails, and how it differs from data science and BI.',
             'link': 'https://www.ibm.com/topics/data-science'},
            {'title': 'What Is Data Science? Definition, Examples, Jobs, and More',
             'text': 'Data science is an interdisciplinary field that uses algorithms, procedures, and processes to examine large amounts of data in order to uncover hidden patterns, generate insights, and direct decision-making.',
             'link': 'https://www.coursera.org/articles/what-is-data-science',}]

    request_object = {
        "next_action": action_name,
        "tracker": {
            "sender_id": "default",
            "conversation_id": "default",
            "slots": {"bot": bot, "to_email": "test@test.com"},
            "latest_message": {
                'text': '/action_public_search',
                'intent_ranking': [{'name': 'test_run'}]},
            "latest_event_time": 1537645578.314389,
            "followup_action": "action_listen",
            "paused": False,
            "events": [
                {"event": "action", "timestamp": 1594907100.12764, "name": "action_session_start",
                 "policy": None,
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
                 "parse_data": {"intent": {"name": "test intent", "confidence": 0.253578245639801},
                                "entities": [],
                                "intent_ranking": [{"name": "test intent", "confidence": 0.253578245639801},
                                                   {"name": "goodbye", "confidence": 0.1504897326231},
                                                   {"name": "greet", "confidence": 0.138640150427818},
                                                   {"name": "affirm", "confidence": 0.0857767835259438},
                                                   {"name": "smalltalk_human",
                                                    "confidence": 0.0721133947372437},
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
            "slots": {"bot": "5f51zd0a56b698ca10d35d2e"},
            "responses": {},
            "actions": [],
            "forms": {},
            "e2e_actions": []
        },
        "version": "version"
    }
    with patch.object(ActionUtility, "perform_web_search") as mocked:
        mocked.side_effect = _perform_web_search
        response = client.post("/webhook", json=request_object)
        response_json = response.json()
        print(response_json)
        assert response.status_code == 200
        assert response_json == {'events': [
            {'event': 'slot', 'timestamp': None, 'name': 'public_search_response', 'value': 'Data science combines math, statistics, programming, analytics, AI, and machine learning to uncover insights from data. Learn how data science works, what it entails, and how it differs from data science and BI.\nTo know more, please visit: <a href = "https://www.ibm.com/topics/data-science" target="_blank" >What is Data Science? | IBM</a>\n\nData science is an interdisciplinary field that uses algorithms, procedures, and processes to examine large amounts of data in order to uncover hidden patterns, generate insights, and direct decision-making.\nTo know more, please visit: <a href = "https://www.coursera.org/articles/what-is-data-science" target="_blank" >What Is Data Science? Definition, Examples, Jobs, and More</a>'},
            {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response', 'value': 'Data science combines math, statistics, programming, analytics, AI, and machine learning to uncover insights from data. Learn how data science works, what it entails, and how it differs from data science and BI.\nTo know more, please visit: <a href = "https://www.ibm.com/topics/data-science" target="_blank" >What is Data Science? | IBM</a>\n\nData science is an interdisciplinary field that uses algorithms, procedures, and processes to examine large amounts of data in order to uncover hidden patterns, generate insights, and direct decision-making.\nTo know more, please visit: <a href = "https://www.coursera.org/articles/what-is-data-science" target="_blank" >What Is Data Science? Definition, Examples, Jobs, and More</a>'}],
            'responses': [{'text': 'Data science combines math, statistics, programming, analytics, AI, and machine learning to uncover insights from data. Learn how data science works, what it entails, and how it differs from data science and BI.\nTo know more, please visit: <a href = "https://www.ibm.com/topics/data-science" target="_blank" >What is Data Science? | IBM</a>\n\nData science is an interdisciplinary field that uses algorithms, procedures, and processes to examine large amounts of data in order to uncover hidden patterns, generate insights, and direct decision-making.\nTo know more, please visit: <a href = "https://www.coursera.org/articles/what-is-data-science" target="_blank" >What Is Data Science? Definition, Examples, Jobs, and More</a>',
                           'buttons': [], 'elements': [], 'custom': {}, 'template': None, 'response': None, 'image': None, 'attachment': None}]}
    log = ActionServerLogs.objects(bot=bot, type=ActionType.web_search_action.value, status="SUCCESS").get()
    assert log['user_msg'] == '/action_public_search'


def test_process_web_search_action_dispatch_false():
    action_name = "public_search_action_dispatch_false"
    bot = "5f50fd9x56b698asdfghjkiuytre"
    user = 'test_user'
    Actions(name=action_name, type=ActionType.web_search_action.value, bot=bot, user='test_user').save()
    WebSearchAction(name=action_name, bot=bot, user=user, dispatch_response=False,
                    set_slot="public_response").save()

    def _perform_web_search(*args, **kwargs):
        assert args == ('What is Python?',)
        assert kwargs == {'topn': 1, 'website': None}
        return [
            {'title': 'Python.org - What is Python? Executive Summary',
             'text': 'Python is an interpreted, object-oriented, high-level programming language with dynamic semantics. Its high-level built in data structures, combined with dynamic typing and dynamic binding, make it very attractive for Rapid Application Development, as well as for use as a scripting or glue language to connect existing components together.',
             'link': 'https://www.python.org/doc/essays/blurb/'}
        ]

    request_object = json.load(open("tests/testing_data/actions/action-request.json"))
    request_object["tracker"]["slots"]["bot"] = bot
    request_object["next_action"] = action_name
    request_object["tracker"]["sender_id"] = user
    request_object["tracker"]["latest_message"]['text'] = "What is Python?"

    with patch.object(ActionUtility, "perform_web_search") as mocked:
        mocked.side_effect = _perform_web_search
        response = client.post("/webhook", json=request_object)
        response_json = response.json()
        assert response.status_code == 200
        assert response_json == {'events': [
            {'event': 'slot', 'timestamp': None, 'name': 'public_response',
             'value': 'Python is an interpreted, object-oriented, high-level programming language with dynamic semantics. Its high-level built in data structures, combined with dynamic typing and dynamic binding, make it very attractive for Rapid Application Development, as well as for use as a scripting or glue language to connect existing components together.\nTo know more, please visit: <a href = "https://www.python.org/doc/essays/blurb/" target="_blank" >Python.org - What is Python? Executive Summary</a>'},
            {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
             'value': 'Python is an interpreted, object-oriented, high-level programming language with dynamic semantics. Its high-level built in data structures, combined with dynamic typing and dynamic binding, make it very attractive for Rapid Application Development, as well as for use as a scripting or glue language to connect existing components together.\nTo know more, please visit: <a href = "https://www.python.org/doc/essays/blurb/" target="_blank" >Python.org - What is Python? Executive Summary</a>'}],
            'responses': []}


def test_process_web_search_action_failure():
    action_name = "custom_public_search_failure"
    bot = "5f50fd0a89b698ca10d35d2e"
    user = 'test_user'
    Actions(name=action_name, type=ActionType.web_search_action.value, bot=bot, user='test_user').save()
    WebSearchAction(name=action_name, bot=bot, user=user).save()

    def _perform_web_search(*args, **kwargs):
        assert args == ('get intents',)
        assert kwargs == {'topn': 1, 'website': None}
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
    with patch.object(ActionUtility, "perform_web_search") as mocked:
        mocked.side_effect = _perform_web_search
        response = client.post("/webhook", json=request_object)
        response_json = response.json()
        assert response.status_code == 200
        assert response_json == {'events': [{'event': 'slot', 'timestamp': None,
                                                     'name': 'kairon_action_response',
                                                     'value': 'I have failed to process your request.'}],
                                         'responses': [{'text': 'I have failed to process your request.',
                                                        'buttons': [], 'elements': [], 'custom': {},
                                                        'template': None,
                                                        'response': None, 'image': None, 'attachment': None}]}


def test_process_web_search_action_no_results():
    action_name = "custom_public_search_action_no_results"
    bot = "5f50fd0a56b698ca10d35d2e"
    user = 'test_user'
    Actions(name=action_name, type=ActionType.web_search_action.value, bot=bot, user='test_user').save()
    WebSearchAction(name=action_name, bot=bot, user=user).save()

    def _perform_web_search(*args, **kwargs):
        assert args == ('get intents',)
        assert kwargs == {'topn': 1, 'website': None}
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
    with patch.object(ActionUtility, "perform_web_search") as mocked:
        mocked.side_effect = _perform_web_search
        response = client.post("/webhook", json=request_object)
        response_json = response.json()
        assert response.status_code == 200
        assert response_json == {'events': [{'event': 'slot', 'timestamp': None,
                                                     'name': 'kairon_action_response',
                                                     'value': 'I have failed to process your request.'}],
                                         'responses': [
                                             {'text': 'I have failed to process your request.', 'buttons': [],
                                              'elements': [],
                                              'custom': {}, 'template': None, 'response': None,
                                              'image': None, 'attachment': None}]}


def test_process_jira_action():
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
            api_token=CustomActionRequestParameters(key="api_token", value='ASDFGHJKL'), project_key='HEL',
            issue_type='Bug', summary='fallback',
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
        response = client.post("/webhook", json=request_object)
        response_json = response.json()
        assert response_json == {'events': [
            {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
             'value': 'Successfully created'}], 'responses': [
            {'text': 'Successfully created', 'buttons': [], 'elements': [], 'custom': {}, 'template': None,
             'response': None, 'image': None, 'attachment': None}]}


def test_process_jira_action_failure():
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
            api_token=CustomActionRequestParameters(value='ASDFGHJKL'), project_key='HEL', issue_type='Bug',
            summary='fallback',
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
        response = client.post("/webhook", json=request_object)
        response_json = response.json()
        assert response_json == {'events': [
            {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
             'value': 'I have failed to create issue for you'}], 'responses': [
            {'text': 'I have failed to create issue for you', 'buttons': [], 'elements': [], 'custom': {},
             'template': None,
             'response': None, 'image': None, 'attachment': None}]}


def test_jira_action_not_found():
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
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response_json == {'events': [], 'responses': []}


def test_process_zendesk_action_not_exists():
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
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response_json == {'events': [], 'responses': []}


def test_process_zendesk_action():
    action_name = "zendesk_action"
    bot = "5f50fd0a56b698ca10d35d2e"
    user = 'test_user'

    Actions(name=action_name, type=ActionType.zendesk_action.value, bot=bot, user='test_user').save()
    with patch('zenpy.Zenpy'):
        ZendeskAction(name=action_name, subdomain='digite751', user_name='udit.pandey@digite.com',
                      api_token=CustomActionRequestParameters(value='1234567890'), subject='new ticket',
                      response='ticket created',
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
        response = client.post("/webhook", json=request_object)
        response_json = response.json()
        assert response_json == {'events': [
            {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
             'value': 'ticket created'}], 'responses': [
            {'text': 'ticket created', 'buttons': [], 'elements': [], 'custom': {},
             'template': None,
             'response': None, 'image': None, 'attachment': None}]}


def test_process_zendesk_action_failure():
    action_name = "test_process_zendesk_action_failure"
    bot = "5f50fd0a56b698ca10d35d2e"
    user = 'test_user'

    Actions(name=action_name, type=ActionType.zendesk_action.value, bot=bot, user='test_user').save()
    with patch('zenpy.Zenpy'):
        ZendeskAction(name=action_name, subdomain='digite751', user_name='udit.pandey@digite.com',
                      api_token=CustomActionRequestParameters(value='1234567890'), subject='new ticket',
                      response='ticket created',
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
        response = client.post("/webhook", json=request_object)
        response_json = response.json()
        assert response_json == {'events': [
            {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
             'value': 'I have failed to create issue for you'}], 'responses': [
            {'text': 'I have failed to create issue for you', 'buttons': [], 'elements': [], 'custom': {},
             'template': None,
             'response': None, 'image': None, 'attachment': None}]}


def test_process_pipedrive_leads_action_not_exists():
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
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response_json == {'events': [], 'responses': []}


def test_process_pipedrive_leads_action():
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
            "slots": {'bot': bot, 'name': 'udit pandey', 'organization': 'digite',
                      'email': 'pandey.udit867@gmail.com', 'phone': '9876543210'},
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
                    response = client.post("/webhook", json=request_object)
                    response_json = response.json()
                    assert response_json == {'events': [
                        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
                         'value': 'lead created'}], 'responses': [
                        {'text': 'lead created', 'buttons': [], 'elements': [], 'custom': {},
                         'template': None,
                         'response': None, 'image': None, 'attachment': None}]}


@responses.activate
def test_process_razorpay_action_invalid_amount():
    action_name = "test_process_razorpay_action_invalid_amount"
    bot = "5f50fd0a56b698ca10d35d2e"

    Actions(name=action_name, type=ActionType.razorpay_action.value, bot=bot, user='test_user').save()
    RazorpayAction(
        name=action_name,
        api_key=CustomActionRequestParameters(value="API_KEY", parameter_type=ActionParameterType.value),
        api_secret=CustomActionRequestParameters(value="API_SECRET", parameter_type=ActionParameterType.value),
        amount=CustomActionRequestParameters(value="amount", parameter_type=ActionParameterType.slot),
        currency=CustomActionRequestParameters(value="INR", parameter_type=ActionParameterType.value),
        username=CustomActionRequestParameters(parameter_type=ActionParameterType.sender_id),
        email=CustomActionRequestParameters(parameter_type=ActionParameterType.sender_id),
        contact=CustomActionRequestParameters(value="contact", parameter_type=ActionParameterType.slot),
        bot=bot, user="udit.pandey@digite.com"
    ).save()
    request_object = json.load(open("tests/testing_data/actions/action-request.json"))
    request_object["tracker"]["slots"]["bot"] = bot
    request_object["tracker"]["slots"]["amount"] = None
    request_object["tracker"]["slots"]["contact"] = "987654320"
    request_object["next_action"] = action_name
    request_object["tracker"]["sender_id"] = "udit.pandey"

    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response_json == {'events': [{'event': 'slot', 'name': 'kairon_action_response',
                                                 'timestamp': None,
                                                 'value': "I have failed to process your request"}],
                                     'responses': [{'attachment': None, 'buttons': [], 'custom': {},
                                                    'elements': [], 'image': None, 'response': None,
                                                    'template': None,
                                                    'text': "I have failed to process your request"}]}

    request_object["tracker"]["slots"]["amount"] = 'NA'
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response_json == {'events': [{'event': 'slot', 'name': 'kairon_action_response',
                                                 'timestamp': None,
                                                 'value': "I have failed to process your request"}],
                                     'responses': [{'attachment': None, 'buttons': [], 'custom': {},
                                                    'elements': [], 'image': None, 'response': None,
                                                    'template': None,
                                                    'text': "I have failed to process your request"}]}

    logs = list(ActionServerLogs.objects(bot=bot, action=action_name))
    assert len(logs) == 2
    assert logs[0].exception == 'amount must be a whole number! Got None.'
    assert logs[1].exception == 'amount must be a whole number! Got NA.'


@responses.activate
def test_process_razorpay_action_failure():
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

    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response_json == {'events': [{'event': 'slot', 'name': 'kairon_action_response',
                                         'timestamp': None,
                                         'value': "I have failed to process your request"}],
                             'responses': [{'attachment': None, 'buttons': [], 'custom': {},
                                            'elements': [], 'image': None, 'response': None,
                                            'template': None,
                                            'text': "I have failed to process your request"}]}


def test_process_razorpay_action_not_exists():
    action_name = "test_process_razorpay_action_not_exists"
    bot = "5f50fd0a56b698ca10d35d2e"

    Actions(name=action_name, type=ActionType.razorpay_action.value, bot=bot, user='test_user').save()

    request_object = json.load(open("tests/testing_data/actions/action-request.json"))
    request_object["tracker"]["slots"]["bot"] = bot
    request_object["next_action"] = action_name
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response_json == {'events': [], 'responses': []}


@responses.activate
def test_process_razorpay_action():
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

    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response_json == {'events': [{'event': 'slot', 'name': 'kairon_action_response',
                                         'timestamp': None, 'value': 'https://rzp.io/i/nxrHnLJ'}],
                             'responses': [{'attachment': None, 'buttons': [], 'custom': {},
                                            'elements': [], 'image': None, 'response': None,
                                            'template': None, 'text': 'https://rzp.io/i/nxrHnLJ'}]}


def test_process_pipedrive_leads_action_failure():
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
        response = client.post("/webhook", json=request_object)
        response_json = response.json()
        assert response_json == {'events': [
            {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
             'value': 'I have failed to create lead for you'}], 'responses': [
            {'text': 'I have failed to create lead for you', 'buttons': [], 'elements': [], 'custom': {},
             'template': None,
             'response': None, 'image': None, 'attachment': None}]}


def test_process_hubspot_forms_action_not_exists():
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
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response_json == {'events': [], 'responses': []}


@responses.activate
def test_process_hubspot_forms_action():
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
        match=[responses.matchers.json_params_matcher(
            {"fields": [{"name": "email", "value": "pandey.udit867@gmail.com"},
                        {"name": "firstname", "value": "udit pandey"}]})]
    )
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

    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response_json == {'events': [
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
         'value': 'Hubspot Form submitted'}], 'responses': [
        {'text': 'Hubspot Form submitted', 'buttons': [], 'elements': [], 'custom': {},
         'template': None,
         'response': None, 'image': None, 'attachment': None}]}


@responses.activate
def test_process_hubspot_forms_action_failure():
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

    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response_json == {'events': [
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
         'value': "I have failed to process your request"}], 'responses': [
        {'text': "I have failed to process your request", 'buttons': [], 'elements': [], 'custom': {},
         'template': None,
         'response': None, 'image': None, 'attachment': None}]}


def test_two_stage_fallback_action():
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

    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response_json['events'] == []
    assert len(response_json['responses'][0]['buttons']) == 3
    assert set(response_json['responses'][0]['buttons'][0].keys()) == {"text", "payload"}
    assert response_json['responses'][0]['text'] == FALLBACK_MESSAGE
    action.text_recommendations = TwoStageFallbackTextualRecommendations(**{"count": 3})
    action.save()

    def _mock_search(*args, **kwargs):
        for result in [{"text": "hi", "payload": "hi"}, {"text": "bye", "payload": "bye"},
                       {"text": "yes", "payload": "yes"}]:
            yield result

    with patch.object(MongoProcessor, "search_training_examples") as mock_action:
        mock_action.side_effect = _mock_search
        response = client.post("/webhook", json=request_object)
        response_json = response.json()
        assert response_json['events'] == []
        assert len(response_json['responses'][0]['buttons']) == 3
        assert set(response_json['responses'][0]['buttons'][0].keys()) == {"text", "payload"}

    def _mock_search(*args, **kwargs):
        for _ in []:
            yield

    with patch.object(MongoProcessor, "search_training_examples") as mock_action:
        mock_action.side_effect = _mock_search
        response = client.post("/webhook", json=request_object)
        response_json = response.json()
        assert response_json['events'] == []
        assert response_json['responses'] == [
            {"text": None, "buttons": [], "elements": [], "custom": {}, "template": "utter_default",
             "response": "utter_default", "image": None, "attachment": None}]


def test_two_stage_fallback_action_no_intent_ranking():
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

    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response_json['events'] == []
    assert response_json['responses'][0]['text'] == FALLBACK_MESSAGE
    assert len(response_json['responses'][0]['buttons']) == 3
    assert response_json['responses'][0]['buttons'] == [{'payload': '/set_context', 'text': 'Trigger'},
                                                        {'payload': '/send_mail{"kairon_user_msg": "welcome new user"}',
                                                         'text': 'Mail me'},
                                                        {'payload': '/send_mail{"kairon_user_msg": "get intents"}',
                                                         'text': 'Mail me'}]


def test_two_stage_fallback_intent_deleted():
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

    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response_json['events'] == []
    assert len(response_json['responses'][0]['buttons']) == 2
    assert response_json['responses'][0]['buttons'], [{"text": "Trigger", "payload": "/set_context"},
                                                      {"text": "Mail me", "payload": "/send_mail"}]

    config = KaironTwoStageFallbackAction.objects(bot=bot, user=user).get()
    config.trigger_rules = None
    config.save()
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response_json == {'events': [], 'responses': [
        {'text': None, 'buttons': [], 'elements': [], 'custom': {}, 'template': "utter_default",
         'response': "utter_default", 'image': None, 'attachment': None}]}


def test_bot_response_action():
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

    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response_json['events'] == [
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
         'value': {'response': 'utter_greet'}}]
    assert response_json['responses'] == [
        {'text': None, 'buttons': [], 'elements': [], 'custom': {}, 'template': 'utter_greet',
         'response': 'utter_greet', 'image': None, 'attachment': None}
        ]


def test_bot_response_action_empty_response_in_domain():
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

    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response_json['events'] == [
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
         'value': {'response': 'utter_greet'}}]
    assert response_json['responses'] == [
        {'text': None, 'buttons': [], 'elements': [], 'custom': {}, 'template': 'utter_greet',
         'response': 'utter_greet', 'image': None, 'attachment': None}
        ]


@responses.activate
def test_bot_response_action_rephrase_enabled():
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

    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response_json['events'] == [
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
         'value': {'text': "Greetings and welcome to kairon!!"}}]
    assert response_json['responses'] == [
        {'text': "Greetings and welcome to kairon!!", 'buttons': [], 'elements': [], 'custom': {},
         'template': None,
         'response': None, 'image': None, 'attachment': None}
        ]

    request_object["domain"]["responses"]["utter_greet"] = [{"custom": {"type": "button", "text": "Greet"}}]
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response_json['events'] == [
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
         'value': {'response': 'utter_greet'}}]
    assert response_json['responses'] == [
        {'text': None, 'buttons': [], 'elements': [], 'custom': {}, 'template': 'utter_greet',
         'response': 'utter_greet', 'image': None, 'attachment': None}
        ]


@responses.activate
def test_bot_response_action_rephrase_failure():
    action_name = 'utter_greet'
    bot = "5f50fd0a56b698ca10d35d2i"
    user = "test_user"
    BotSettings(rephrase_response=True, bot=bot, user=user).save()
    secret = BotSecrets(secret_type=BotSecretType.gpt_key.value, value="uditpandey", bot=bot, user=user).save()
    gpt_prompt = open("./template/rephrase-prompt.txt").read()
    gpt_prompt = f"{gpt_prompt}hi\noutput:"
    gpt_response = {
        "error": {"message": "'100' is not of type 'integer' - 'max_tokens'", "type": "invalid_request_error",
                  "param": None, "code": None}}
    responses.add(
        "POST",
        Utility.environment["plugins"]["gpt"]["url"],
        status=400,
        json=gpt_response,
        match=[responses.matchers.json_params_matcher(
            {'model': 'text-davinci-003', 'prompt': gpt_prompt, 'temperature': 0.7, 'max_tokens': 152})],
    )

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

    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response_json['events'] == [
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
         'value': {'response': 'utter_greet'}}]
    assert response_json['responses'] == [
        {'text': None, 'buttons': [], 'elements': [], 'custom': {}, 'template': 'utter_greet',
         'response': 'utter_greet', 'image': None, 'attachment': None}
        ]
    assert len(responses.calls._calls) == 1

    secret.value = ""
    secret.save()
    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response_json['events'] == [
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
         'value': {'response': 'utter_greet'}}]
    assert response_json['responses'] == [
        {'text': None, 'buttons': [], 'elements': [], 'custom': {}, 'template': 'utter_greet',
         'response': 'utter_greet', 'image': None, 'attachment': None}
        ]
    assert len(responses.calls._calls) == 1


def test_bot_response_action_failure():
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
        response = client.post("/webhook", json=request_object)

    response_json = response.json()
    assert response_json['events'] == [
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
         'value': {'response': 'utter_greet'}}]
    assert response_json['responses'] == [
        {'text': None, 'buttons': [], 'elements': [], 'custom': {}, 'template': 'utter_greet',
         'response': 'utter_greet', 'image': None, 'attachment': None}
        ]


def test_action_handler_none():
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

    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response_json is None


def test_action_handler_exceptions():
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
        response = client.post("/webhook", json=request_object)
        response_json = response.json()
        assert response_json == {'error': "Custom action 'Action Execution Rejection' rejected execution.",
                                 'action_name': 'Action Execution Rejection'}

    async def mock_process_actions(*args, **kwargs):
        from rasa_sdk.interfaces import ActionNotFoundException
        raise ActionNotFoundException("Action Not Found Exception")

    with patch('kairon.actions.handlers.action.ActionHandler.process_actions', mock_process_actions):
        response = client.post("/webhook", json=request_object)
        response_json = response.json()
        assert response_json == {'error': "No registered action found for name 'Action Not Found Exception'.",
                                 'action_name': 'Action Not Found Exception'}


@mock.patch.object(GPT3FAQEmbedding, "_GPT3FAQEmbedding__get_answer", autospec=True)
@mock.patch.object(GPT3FAQEmbedding, "_GPT3FAQEmbedding__get_embedding", autospec=True)
@patch("kairon.shared.rest_client.AioRestClient.request", autospec=True)
def test_prompt_action_response_action_with_prompt_question_from_slot(mock_search, mock_embedding, mock_completion):
    from kairon.shared.llm.gpt3 import GPT3FAQEmbedding
    from uuid6 import uuid7

    action_name = "test_prompt_action_response_action_with_prompt_question_from_slot"
    bot = "5f50fd0a56b698ca10d35d2l"
    user = "udit.pandey"
    value = "keyvalue"
    user_msg = "What kind of language is python?"
    bot_content = "Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected."
    generated_text = "Python is dynamically typed, garbage-collected, high level, general purpose programming."
    llm_prompts = [
        {'name': 'System Prompt',
         'data': 'You are a personal assistant. Answer question based on the context below.',
         'type': 'system', 'source': 'static', 'is_enabled': True},
        {'name': 'History Prompt', 'type': 'user', 'source': 'history', 'is_enabled': True},
        {'name': 'Query Prompt', 'data': "What kind of language is python?", 'instructions': 'Rephrase the query.',
         'type': 'query', 'source': 'static', 'is_enabled': False},
        {'name': 'Similarity Prompt',
         'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
         'type': 'user', 'source': 'bot_content',
         'is_enabled': True}
    ]

    embedding = list(np.random.random(GPT3FAQEmbedding.__embedding__))
    mock_embedding.return_value = embedding
    mock_completion.return_value = generated_text
    mock_search.return_value = {
        'result': [{'id': uuid7().__str__(), 'score': 0.80, 'payload': {'content': bot_content}}]}
    Actions(name=action_name, type=ActionType.prompt_action.value, bot=bot, user=user).save()
    BotSettings(llm_settings=LLMSettings(enable_faq=True), bot=bot, user=user).save()
    PromptAction(name=action_name, bot=bot, user=user, num_bot_responses=2, llm_prompts=llm_prompts,
                 user_question=UserQuestion(type="from_slot", value="prompt_question")).save()
    BotSecrets(secret_type=BotSecretType.gpt_key.value, value=value, bot=bot, user=user).save()

    request_object = json.load(open("tests/testing_data/actions/action-request.json"))
    request_object["tracker"]["slots"] = {"bot": bot, "prompt_question": user_msg}
    request_object["next_action"] = action_name
    request_object["tracker"]["sender_id"] = user
    request_object['tracker']['events'] = [{"event": "user", 'text': 'hello',
                                            "data": {"elements": '', "quick_replies": '', "buttons": '',
                                                     "attachment": '', "image": '', "custom": ''}},
                                           {'event': 'bot', "text": "how are you",
                                            "data": {"elements": '', "quick_replies": '', "buttons": '',
                                                     "attachment": '', "image": '', "custom": ''}}]

    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response_json['events'] == [
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response', 'value': generated_text}]
    assert response_json['responses'] == [
        {'text': generated_text, 'buttons': [], 'elements': [], 'custom': {}, 'template': None,
         'response': None, 'image': None, 'attachment': None}
        ]

    assert mock_completion.call_args.args[1] == 'What kind of language is python?'
    assert mock_completion.call_args.args[
               2] == """You are a personal assistant. Answer question based on the context below.\n"""
    assert mock_completion.call_args.args[
               3] == """\nSimilarity Prompt:\nPython is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.\nInstructions on how to use Similarity Prompt: Answer question based on the context above, if answer is not in the context go check previous logs.\n"""
    print(mock_completion.call_args.kwargs)
    assert mock_completion.call_args.kwargs == {'top_results': 10, 'similarity_threshold': 0.7,
                                                'enable_response_cache': False,
                                                'hyperparameters': {'temperature': 0.0, 'max_tokens': 300,
                                                                    'model': 'gpt-3.5-turbo', 'top_p': 0.0, 'n': 1,
                                                                    'stream': False, 'stop': None,
                                                                    'presence_penalty': 0.0,
                                                                    'frequency_penalty': 0.0, 'logit_bias': {}},
                                                'query_prompt': '', 'use_query_prompt': False,
                                                'previous_bot_responses': [{'role': 'user', 'content': 'hello'},
                                                                           {'role': 'assistant',
                                                                            'content': 'how are you'}],
                                                'use_similarity_prompt': True,
                                                'similarity_prompt_name': 'Similarity Prompt',
                                                'similarity_prompt_instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                                                'instructions': [], 'collection': None}


@mock.patch.object(GPT3FAQEmbedding, "_GPT3FAQEmbedding__get_answer", autospec=True)
@mock.patch.object(GPT3FAQEmbedding, "_GPT3FAQEmbedding__get_embedding", autospec=True)
@patch("kairon.shared.rest_client.AioRestClient.request", autospec=True)
def test_prompt_action_response_action_with_bot_responses(mock_search, mock_embedding, mock_completion):
    from kairon.shared.llm.gpt3 import GPT3FAQEmbedding
    from uuid6 import uuid7

    action_name = "test_prompt_action"
    bot = "5f50fd0a56b698ca10d35d2k"
    user = "udit.pandey"
    value = "keyvalue"
    user_msg = "What kind of language is python?"
    bot_content = "Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected."
    generated_text = "Python is dynamically typed, garbage-collected, high level, general purpose programming."
    llm_prompts = [
        {'name': 'System Prompt',
         'data': 'You are a personal assistant. Answer question based on the context below.',
         'type': 'system', 'source': 'static', 'is_enabled': True},
        {'name': 'History Prompt', 'type': 'user', 'source': 'history', 'is_enabled': True},
        {'name': 'Query Prompt', 'data': "What kind of language is python?", 'instructions': 'Rephrase the query.',
         'type': 'query', 'source': 'static', 'is_enabled': False},
        {'name': 'Similarity Prompt',
         'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
         'type': 'user', 'source': 'bot_content',
         'is_enabled': True}
    ]

    embedding = list(np.random.random(GPT3FAQEmbedding.__embedding__))
    mock_embedding.return_value = embedding
    mock_completion.return_value = generated_text
    mock_search.return_value = {
        'result': [{'id': uuid7().__str__(), 'score': 0.80, 'payload': {'content': bot_content}}]}
    Actions(name=action_name, type=ActionType.prompt_action.value, bot=bot, user=user).save()
    BotSettings(llm_settings=LLMSettings(enable_faq=True), bot=bot, user=user).save()
    PromptAction(name=action_name, bot=bot, user=user, num_bot_responses=2, llm_prompts=llm_prompts).save()
    BotSecrets(secret_type=BotSecretType.gpt_key.value, value=value, bot=bot, user=user).save()

    request_object = json.load(open("tests/testing_data/actions/action-request.json"))
    request_object["tracker"]["slots"]["bot"] = bot
    request_object["next_action"] = action_name
    request_object["tracker"]["sender_id"] = user
    request_object["tracker"]["latest_message"]['text'] = user_msg
    request_object['tracker']['events'] = [{"event": "user", 'text': 'hello',
                                            "data": {"elements": '', "quick_replies": '', "buttons": '',
                                                     "attachment": '', "image": '', "custom": ''}},
                                           {'event': 'bot', "text": "how are you",
                                            "data": {"elements": '', "quick_replies": '', "buttons": '',
                                                     "attachment": '', "image": '', "custom": ''}}]

    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response_json['events'] == [
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response', 'value': generated_text}]
    assert response_json['responses'] == [
        {'text': generated_text, 'buttons': [], 'elements': [], 'custom': {}, 'template': None,
         'response': None, 'image': None, 'attachment': None}
        ]

    assert mock_completion.call_args.args[1] == 'What kind of language is python?'
    assert mock_completion.call_args.args[
               2] == """You are a personal assistant. Answer question based on the context below.\n"""
    assert mock_completion.call_args.args[
               3] == """\nSimilarity Prompt:\nPython is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.\nInstructions on how to use Similarity Prompt: Answer question based on the context above, if answer is not in the context go check previous logs.\n"""
    print(mock_completion.call_args.kwargs)
    assert mock_completion.call_args.kwargs == {'top_results': 10, 'similarity_threshold': 0.7,
                                                'enable_response_cache': False,
                                                'hyperparameters': {'temperature': 0.0, 'max_tokens': 300,
                                                                    'model': 'gpt-3.5-turbo', 'top_p': 0.0, 'n': 1,
                                                                    'stream': False, 'stop': None,
                                                                    'presence_penalty': 0.0,
                                                                    'frequency_penalty': 0.0, 'logit_bias': {}},
                                                'query_prompt': '', 'use_query_prompt': False,
                                                'previous_bot_responses': [{'role': 'user', 'content': 'hello'},
                                                                           {'role': 'assistant',
                                                                            'content': 'how are you'}],
                                                'use_similarity_prompt': True,
                                                'similarity_prompt_name': 'Similarity Prompt',
                                                'similarity_prompt_instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                                                'instructions': [], 'collection': None}


@mock.patch.object(GPT3FAQEmbedding, "_GPT3FAQEmbedding__get_answer", autospec=True)
@mock.patch.object(GPT3FAQEmbedding, "_GPT3FAQEmbedding__get_embedding", autospec=True)
@patch("kairon.shared.rest_client.AioRestClient.request", autospec=True)
def test_prompt_action_response_action_with_bot_responses_with_instructions(mock_search, mock_embedding,
                                                                            mock_completion):
    from kairon.shared.llm.gpt3 import GPT3FAQEmbedding
    from uuid6 import uuid7

    action_name = "test_prompt_action_with_bot_responses_with_instructions"
    bot = "5f50fd0a56b678ca10d35d2k"
    user = "udit.pandey"
    value = "keyvalue"
    user_msg = "What kind of language is python?"
    bot_content = "Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected."
    generated_text = "Python is dynamically typed, garbage-collected, high level, general purpose programming."
    instructions = ['Answer in a short way.', 'Keep it simple.']
    llm_prompts = [
        {'name': 'System Prompt',
         'data': 'You are a personal assistant. Answer question based on the context below.',
         'type': 'system', 'source': 'static', 'is_enabled': True},
        {'name': 'History Prompt', 'type': 'user', 'source': 'history', 'is_enabled': True},
        {'name': 'Query Prompt', 'data': "What kind of language is python?", 'instructions': 'Rephrase the query.',
         'type': 'query', 'source': 'static', 'is_enabled': False},
        {'name': 'Similarity Prompt',
         'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
         'type': 'user', 'source': 'bot_content',
         'is_enabled': True}
    ]

    embedding = list(np.random.random(GPT3FAQEmbedding.__embedding__))
    mock_embedding.return_value = embedding
    mock_completion.return_value = generated_text
    mock_search.return_value = {
        'result': [{'id': uuid7().__str__(), 'score': 0.80, 'payload': {'content': bot_content}}]}
    Actions(name=action_name, type=ActionType.prompt_action.value, bot=bot, user=user).save()
    BotSettings(llm_settings=LLMSettings(enable_faq=True), bot=bot, user=user).save()
    PromptAction(name=action_name, bot=bot, user=user, num_bot_responses=2, llm_prompts=llm_prompts,
                 instructions=instructions).save()
    BotSecrets(secret_type=BotSecretType.gpt_key.value, value=value, bot=bot, user=user).save()

    request_object = json.load(open("tests/testing_data/actions/action-request.json"))
    request_object["tracker"]["slots"]["bot"] = bot
    request_object["next_action"] = action_name
    request_object["tracker"]["sender_id"] = user
    request_object["tracker"]["latest_message"]['text'] = user_msg
    request_object['tracker']['events'] = [{"event": "user", 'text': 'hello',
                                            "data": {"elements": '', "quick_replies": '', "buttons": '',
                                                     "attachment": '', "image": '', "custom": ''}},
                                           {'event': 'bot', "text": "how are you",
                                            "data": {"elements": '', "quick_replies": '', "buttons": '',
                                                     "attachment": '', "image": '', "custom": ''}}]

    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response_json['events'] == [
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response', 'value': generated_text}]
    assert response_json['responses'] == [
        {'text': generated_text, 'buttons': [], 'elements': [], 'custom': {}, 'template': None,
         'response': None, 'image': None, 'attachment': None}
        ]

    assert mock_completion.call_args.args[1] == 'What kind of language is python?'
    assert mock_completion.call_args.args[
               2] == """You are a personal assistant. Answer question based on the context below.\n"""
    assert mock_completion.call_args.args[
               3] == """\nSimilarity Prompt:\nPython is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.\nInstructions on how to use Similarity Prompt: Answer question based on the context above, if answer is not in the context go check previous logs.\n"""
    print(mock_completion.call_args.kwargs)
    assert mock_completion.call_args.kwargs == {'top_results': 10, 'similarity_threshold': 0.7,
                                                'enable_response_cache': False,
                                                'hyperparameters': {'temperature': 0.0, 'max_tokens': 300,
                                                                    'model': 'gpt-3.5-turbo', 'top_p': 0.0, 'n': 1,
                                                                    'stream': False, 'stop': None,
                                                                    'presence_penalty': 0.0,
                                                                    'frequency_penalty': 0.0, 'logit_bias': {}},
                                                'query_prompt': '', 'use_query_prompt': False,
                                                'previous_bot_responses': [{'role': 'user', 'content': 'hello'},
                                                                           {'role': 'assistant',
                                                                            'content': 'how are you'}],
                                                'use_similarity_prompt': True,
                                                'similarity_prompt_name': 'Similarity Prompt',
                                                'similarity_prompt_instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                                                'instructions': ['Answer in a short way.', 'Keep it simple.'],
                                                'collection': None}


@mock.patch.object(GPT3Resources, "invoke", autospec=True)
@mock.patch.object(GPT3FAQEmbedding, "_GPT3FAQEmbedding__get_embedding", autospec=True)
@patch("kairon.shared.rest_client.AioRestClient.request", autospec=True)
def test_prompt_action_response_action_with_query_prompt(mock_search, mock_embedding, mock_completion):
    from kairon.shared.llm.gpt3 import GPT3FAQEmbedding
    from uuid6 import uuid7

    action_name = "test_prompt_action_response_action_with_query_prompt"
    bot = "5f50fd0a56b698ca10d35d2s"
    user = "udit.pandey"
    value = "keyvalue"
    user_msg = "What kind of language is python?"
    bot_content = "Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected."
    generated_text = "Python is dynamically typed, garbage-collected, high level, general purpose programming."
    rephrased_query = "Explain python is called high level programming language in laymen terms?"
    llm_prompts = [
        {'name': 'System Prompt',
         'data': 'You are a personal assistant. Answer question based on the context below.',
         'type': 'system', 'source': 'static', 'is_enabled': True},
        {'name': 'Similarity Prompt',
         'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
         'type': 'user', 'source': 'bot_content', 'is_enabled': True},
        {'name': 'Query Prompt',
         'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
         'instructions': 'Answer according to the context', 'type': 'query', 'source': 'static',
         'is_enabled': True},
        {'name': 'Query Prompt',
         'data': 'If there is no specific query, assume that user is aking about java programming.',
         'instructions': 'Answer according to the context', 'type': 'query', 'source': 'static', 'is_enabled': True}
    ]

    mock_completion_for_query_prompt = rephrased_query, {
        'choices': [{'message': {'content': rephrased_query, 'role': 'assistant'}}]}

    mock_completion_for_answer = generated_text, {
        'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}

    mock_completion.side_effect = [mock_completion_for_query_prompt, mock_completion_for_answer]

    embedding = list(np.random.random(GPT3FAQEmbedding.__embedding__))
    mock_embedding.return_value = embedding
    mock_search.return_value = {
        'result': [{'id': uuid7().__str__(), 'score': 0.80, 'payload': {'content': bot_content}}]}
    Actions(name=action_name, type=ActionType.prompt_action.value, bot=bot, user=user).save()
    BotSettings(llm_settings=LLMSettings(enable_faq=True), bot=bot, user=user).save()
    PromptAction(name=action_name, bot=bot, user=user, llm_prompts=llm_prompts).save()
    BotSecrets(secret_type=BotSecretType.gpt_key.value, value=value, bot=bot, user=user).save()

    request_object = json.load(open("tests/testing_data/actions/action-request.json"))
    request_object["tracker"]["slots"]["bot"] = bot
    request_object["next_action"] = action_name
    request_object["tracker"]["sender_id"] = user
    request_object["tracker"]["latest_message"]['text'] = user_msg
    request_object['tracker']['events'] = [{"event": "bot", 'text': 'hello',
                                            "data": {"elements": '', "quick_replies": '', "buttons": '',
                                                     "attachment": '', "image": '', "custom": ''}},
                                           {'event': 'bot', "text": "how are you",
                                            "data": {"elements": '', "quick_replies": '', "buttons": '',
                                                     "attachment": '', "image": '', "custom": ''}}]

    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response_json['events'] == [
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response', 'value': generated_text}]
    assert response_json['responses'] == [
        {'text': generated_text, 'buttons': [], 'elements': [], 'custom': {}, 'template': None,
         'response': None, 'image': None, 'attachment': None}
        ]
    print(mock_completion.call_args.kwargs['messages'])
    assert mock_completion.call_args.kwargs['messages'] == [
        {'role': 'system',
         'content': 'You are a personal assistant. Answer question based on the context below.\n'},
        {'role': 'user',
         'content': '\nSimilarity Prompt:\nPython is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.\nInstructions on how to use Similarity Prompt: Answer question based on the context above, if answer is not in the context go check previous logs.\n \nQ: Explain python is called high level programming language in laymen terms? \nA:'}]


@mock.patch.object(GPT3FAQEmbedding, "_GPT3FAQEmbedding__get_answer", autospec=True)
@mock.patch.object(GPT3FAQEmbedding, "_GPT3FAQEmbedding__get_embedding", autospec=True)
@patch("kairon.shared.rest_client.AioRestClient.request", autospec=True)
def test_prompt_response_action(mock_search, mock_embedding, mock_completion):
    from kairon.shared.llm.gpt3 import GPT3FAQEmbedding
    from uuid6 import uuid7

    action_name = GPT_LLM_FAQ
    bot = "5f50fd0a56b698ca10d35d2e"
    user = "udit.pandey"
    value = "keyvalue"
    user_msg = "What kind of language is python?"
    bot_content = "Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected."
    generated_text = "Python is dynamically typed, garbage-collected, high level, general purpose programming."
    llm_prompts = [
        {'name': 'System Prompt', 'data': 'You are a personal assistant.',
         'instructions': 'Answer question based on the context below.', 'type': 'system', 'source': 'static'},
        {'name': 'Similarity Prompt',
         'instructions': 'Answer question based on the context above.', 'type': 'user', 'source': 'bot_content'},
    ]
    embedding = list(np.random.random(GPT3FAQEmbedding.__embedding__))
    mock_embedding.return_value = embedding
    mock_completion.return_value = generated_text
    mock_search.return_value = {
        'result': [{'id': uuid7().__str__(), 'score': 0.80, 'payload': {'content': bot_content}}]}
    Actions(name=action_name, type=ActionType.prompt_action.value, bot=bot, user=user).save()
    PromptAction(name=action_name, bot=bot, user=user, llm_prompts=llm_prompts).save()
    BotSettings(llm_settings=LLMSettings(enable_faq=True), bot=bot, user=user).save()
    BotSecrets(secret_type=BotSecretType.gpt_key.value, value=value, bot=bot, user=user).save()

    request_object = json.load(open("tests/testing_data/actions/action-request.json"))
    request_object["tracker"]["slots"]["bot"] = bot
    request_object["next_action"] = action_name
    request_object["tracker"]["sender_id"] = user
    request_object["tracker"]["latest_message"]['text'] = user_msg

    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response_json['events'] == [
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response', 'value': generated_text}]
    assert response_json['responses'] == [
        {'text': generated_text, 'buttons': [], 'elements': [], 'custom': {}, 'template': None,
         'response': None, 'image': None, 'attachment': None}
        ]


@mock.patch.object(GPT3FAQEmbedding, "_GPT3FAQEmbedding__get_answer", autospec=True)
@mock.patch.object(GPT3FAQEmbedding, "_GPT3FAQEmbedding__get_embedding", autospec=True)
@patch("kairon.shared.rest_client.AioRestClient.request", autospec=True)
def test_prompt_response_action_with_instructions(mock_search, mock_embedding, mock_completion):
    from kairon.shared.llm.gpt3 import GPT3FAQEmbedding
    from uuid6 import uuid7

    action_name = 'test_prompt_response_action_with_instructions'
    bot = "5f50fd0a56b690ca10d35d2e"
    user = "udit.pandey"
    value = "keyvalue"
    user_msg = "What kind of language is java?"
    bot_content = "Java is a high-level, object-oriented programming language. It was developed by Sun Microsystems (later acquired by Oracle Corporation) and released in 1995. "
    generated_text = "Java is a high-level, object-oriented programming language. "
    instructions = ['Answer in a short way.', 'Keep it simple.']
    llm_prompts = [
        {'name': 'System Prompt', 'data': 'You are a personal assistant.',
         'instructions': 'Answer question based on the context below.', 'type': 'system', 'source': 'static'},
        {'name': 'Similarity Prompt',
         'instructions': 'Answer question based on the context above.', 'type': 'user', 'source': 'bot_content'},
    ]
    embedding = list(np.random.random(GPT3FAQEmbedding.__embedding__))
    mock_embedding.return_value = embedding
    mock_completion.return_value = generated_text
    mock_search.return_value = {
        'result': [{'id': uuid7().__str__(), 'score': 0.80, 'payload': {'content': bot_content}}]}
    Actions(name=action_name, type=ActionType.prompt_action.value, bot=bot, user=user).save()
    PromptAction(name=action_name, bot=bot, user=user, llm_prompts=llm_prompts, instructions=instructions).save()
    BotSettings(llm_settings=LLMSettings(enable_faq=True), bot=bot, user=user).save()
    BotSecrets(secret_type=BotSecretType.gpt_key.value, value=value, bot=bot, user=user).save()

    request_object = json.load(open("tests/testing_data/actions/action-request.json"))
    request_object["tracker"]["slots"]["bot"] = bot
    request_object["next_action"] = action_name
    request_object["tracker"]["sender_id"] = user
    request_object["tracker"]["latest_message"]['text'] = user_msg

    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response_json['events'] == [
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response', 'value': generated_text}]
    assert response_json['responses'] == [
        {'text': generated_text, 'buttons': [], 'elements': [], 'custom': {}, 'template': None,
         'response': None, 'image': None, 'attachment': None}
        ]


@mock.patch.object(GPT3Resources, "invoke", autospec=True)
@mock.patch.object(GPT3FAQEmbedding, "_GPT3FAQEmbedding__get_embedding", autospec=True)
@patch("kairon.shared.rest_client.AioRestClient.request", autospec=True)
def test_prompt_response_action_streaming_enabled(mock_search, mock_embedding, mock_completion):
    from kairon.shared.llm.gpt3 import GPT3FAQEmbedding
    from uuid6 import uuid7

    action_name = GPT_LLM_FAQ
    bot = "5f50k90a56b698ca10d35d2e"
    user = "udit.pandeyy"
    value = "keyvalue"
    user_msg = "What kind of language is python?"
    bot_content = "Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected."
    generated_text = "Python is dynamically typed, garbage-collected, high level, general purpose programming."
    llm_prompts = [
        {'name': 'System Prompt', 'data': 'You are a personal assistant.',
         'instructions': 'Answer question based on the context below.', 'type': 'system', 'source': 'static'},
        {'name': 'Similarity Prompt',
         'instructions': 'Answer question based on the context above.', 'type': 'user', 'source': 'bot_content'},
    ]

    embedding = list(np.random.random(GPT3FAQEmbedding.__embedding__))
    mock_embedding.return_value = embedding
    mock_completion.return_value = generated_text, generated_text
    mock_search.return_value = {
        'result': [{'id': uuid7().__str__(), 'score': 0.80, 'payload': {'content': bot_content}}]}
    Actions(name=action_name, type=ActionType.prompt_action.value, bot=bot, user=user).save()
    BotSettings(llm_settings=LLMSettings(enable_faq=True), bot=bot, user=user).save()
    hyperparameters = Utility.get_llm_hyperparameters().copy()
    hyperparameters['stream'] = True
    PromptAction(name=action_name, bot=bot, user=user, hyperparameters=hyperparameters,
                 llm_prompts=llm_prompts).save()
    BotSecrets(secret_type=BotSecretType.gpt_key.value, value=value, bot=bot, user=user).save()

    request_object = json.load(open("tests/testing_data/actions/action-request.json"))
    request_object["tracker"]["slots"]["bot"] = bot
    request_object["next_action"] = action_name
    request_object["tracker"]["sender_id"] = user
    request_object["tracker"]["latest_message"]['text'] = user_msg

    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response_json['events'] == [
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response', 'value': generated_text}]
    assert response_json['responses'] == [
        {'text': generated_text, 'buttons': [], 'elements': [], 'custom': {}, 'template': None,
         'response': None, 'image': None, 'attachment': None}
        ]
    assert mock_completion.call_args.kwargs == {'messages': [
        {'role': 'system', 'content': 'You are a personal assistant.\n'},
        {'role': 'user',
         'content': '\nSimilarity Prompt:\nPython is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.\nInstructions on how to use Similarity Prompt: Answer question based on the context above.\n \nQ: What kind of language is python? \nA:'}],
        'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-3.5-turbo',
        'top_p': 0.0, 'n': 1, 'stream': True, 'stop': None,
        'presence_penalty': 0.0, 'frequency_penalty': 0.0, 'logit_bias': {}}
    assert mock_completion.call_args.args[1] == 'chat/completions'


@patch("kairon.shared.llm.gpt3.openai.ChatCompletion.create", autospec=True)
@patch("kairon.shared.llm.gpt3.openai.Embedding.create", autospec=True)
@patch("kairon.shared.rest_client.AioRestClient.request", autospec=True)
def test_prompt_response_action_failure(mock_search, mock_embedding, mock_completion):
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
    mock_completion.return_value = convert_to_openai_object(
        OpenAIResponse({'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}, {}))
    mock_search.return_value = {
        'result': [{'id': uuid7().__str__(), 'score': 0.80, 'payload': {'content': bot_content}}]}
    Actions(name=action_name, type=ActionType.prompt_action.value, bot=bot, user=user).save()
    BotSettings(llm_settings=LLMSettings(enable_faq=True), bot=bot, user=user).save()

    request_object = json.load(open("tests/testing_data/actions/action-request.json"))
    request_object["tracker"]["slots"]["bot"] = bot
    request_object["next_action"] = action_name
    request_object["tracker"]["sender_id"] = user
    request_object["tracker"]["latest_message"]['text'] = user_msg

    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response_json['events'] == [
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
         'value': DEFAULT_NLU_FALLBACK_RESPONSE}]
    assert response_json['responses'] == [
        {'text': DEFAULT_NLU_FALLBACK_RESPONSE, 'buttons': [], 'elements': [], 'custom': {}, 'template': None,
         'response': None, 'image': None, 'attachment': None}
        ]


def test_prompt_response_action_disabled():
    bot = "5f50fd0a56b698ca10d35d2efg"
    user = "udit.pandey"
    user_msg = "What kind of language is python?"
    action_name = GPT_LLM_FAQ

    request_object = json.load(open("tests/testing_data/actions/action-request.json"))
    request_object["tracker"]["slots"]["bot"] = bot
    request_object["next_action"] = action_name
    request_object["tracker"]["sender_id"] = user
    request_object["tracker"]["latest_message"]['text'] = user_msg
    Actions(name=action_name, type=ActionType.prompt_action.value, bot=bot, user=user).save()
    BotSettings(llm_settings=LLMSettings(enable_faq=False), bot=bot, user=user).save()

    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response_json['events'] == [
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
         'value': 'Faq feature is disabled for the bot! Please contact support.'}]
    assert response_json['responses'] == [
        {'text': 'Faq feature is disabled for the bot! Please contact support.', 'buttons': [], 'elements': [],
         'custom': {}, 'template': None,
         'response': None, 'image': None, 'attachment': None}
        ]
    log = ActionServerLogs.objects(bot=bot, type=ActionType.prompt_action.value, status="FAILURE").get()
    assert log['bot_response'] == 'Faq feature is disabled for the bot! Please contact support.'
    assert log['exception'] == 'Faq feature is disabled for the bot! Please contact support.'


def test_prompt_action_response_action_does_not_exists():
    bot = "5n80fd0a56b698ca10d35d2efg"
    user = "uditpandey"
    user_msg = "What kind of language is python?"
    action_name = GPT_LLM_FAQ

    request_object = json.load(open("tests/testing_data/actions/action-request.json"))
    request_object["tracker"]["slots"]["bot"] = bot
    request_object["next_action"] = action_name
    request_object["tracker"]["sender_id"] = user
    request_object["tracker"]["latest_message"]['text'] = user_msg

    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response.status_code == 200
    assert len(response_json['events']) == 0
    assert len(response_json['responses']) == 0


@mock.patch.object(GPT3FAQEmbedding, "_GPT3FAQEmbedding__get_answer", autospec=True)
@mock.patch.object(GPT3FAQEmbedding, "_GPT3FAQEmbedding__get_embedding", autospec=True)
@patch("kairon.shared.rest_client.AioRestClient.request", autospec=True)
def test_prompt_action_response_action_with_static_user_prompt(mock_search, mock_embedding, mock_completion):
    from kairon.shared.llm.gpt3 import GPT3FAQEmbedding
    from openai.util import convert_to_openai_object
    from openai.openai_response import OpenAIResponse
    from uuid6 import uuid7

    action_name = "kairon_faq_action"
    bot = "5u80fd0a56b698ca10d35d2s"
    user = "udit.pandey"
    value = "keyvalue"
    user_msg = "What kind of language is python?"
    bot_content = "Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected."
    generated_text = "Python is dynamically typed, garbage-collected, high level, general purpose programming."
    llm_prompts = [
        {'name': 'System Prompt',
         'data': 'You are a personal assistant. Answer question based on the context below.',
         'type': 'system', 'source': 'static', 'is_enabled': True},
        {'name': 'Similarity Prompt',
         'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
         'type': 'user', 'source': 'bot_content', 'is_enabled': True},
        {'name': 'Python Prompt',
         'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
         'instructions': 'Answer according to the context', 'type': 'user', 'source': 'static',
         'is_enabled': True},
        {'name': 'Java Prompt',
         'data': 'Java is a programming language and computing platform first released by Sun Microsystems in 1995.',
         'instructions': 'Answer according to the context', 'type': 'user', 'source': 'static',
         'is_enabled': True}
    ]

    def mock_completion_for_answer(*args, **kwargs):
        return convert_to_openai_object(
            OpenAIResponse({'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}, {}))

    def __mock_search_cache(*args, **kwargs):
        return {'result': []}

    def __mock_fetch_similar(*args, **kwargs):
        return {'result': [{'id': uuid7().__str__(), 'score': 0.80, 'payload': {'content': bot_content}}]}

    def __mock_cache_result(*args, **kwargs):
        return {'result': []}

    mock_completion.return_value = mock_completion_for_answer()

    embedding = list(np.random.random(GPT3FAQEmbedding.__embedding__))
    mock_embedding.return_value = embedding
    mock_completion.return_value = generated_text
    mock_search.side_effect = [__mock_search_cache(), __mock_fetch_similar(), __mock_cache_result()]
    Actions(name=action_name, type=ActionType.prompt_action.value, bot=bot, user=user).save()
    BotSettings(llm_settings=LLMSettings(enable_faq=True), bot=bot, user=user).save()
    PromptAction(name=action_name, bot=bot, user=user, llm_prompts=llm_prompts).save()
    BotSecrets(secret_type=BotSecretType.gpt_key.value, value=value, bot=bot, user=user).save()

    request_object = json.load(open("tests/testing_data/actions/action-request.json"))
    request_object["tracker"]["slots"]["bot"] = bot
    request_object["next_action"] = action_name
    request_object["tracker"]["sender_id"] = user
    request_object["tracker"]["latest_message"]['text'] = user_msg
    request_object['tracker']['events'] = [{"event": "bot", 'text': 'hello',
                                            "data": {"elements": '', "quick_replies": '', "buttons": '',
                                                     "attachment": '', "image": '', "custom": ''}},
                                           {'event': 'bot', "text": "how are you",
                                            "data": {"elements": '', "quick_replies": '', "buttons": '',
                                                     "attachment": '', "image": '', "custom": ''}}]

    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response_json['events'] == [
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response', 'value': generated_text}]
    assert response_json['responses'] == [
        {'text': generated_text, 'buttons': [], 'elements': [], 'custom': {}, 'template': None,
         'response': None, 'image': None, 'attachment': None}
        ]


@responses.activate
@mock.patch.object(GPT3FAQEmbedding, "_GPT3FAQEmbedding__get_answer", autospec=True)
@mock.patch.object(GPT3FAQEmbedding, "_GPT3FAQEmbedding__get_embedding", autospec=True)
@patch("kairon.shared.llm.gpt3.GPT3FAQEmbedding.__collection_search__", autospec=True)
def test_prompt_action_response_action_with_action_prompt(mock_search, mock_embedding, mock_completion, aioresponses):
    from kairon.shared.llm.gpt3 import GPT3FAQEmbedding
    from openai.util import convert_to_openai_object
    from openai.openai_response import OpenAIResponse
    from uuid6 import uuid7

    action_name = "kairon_faq_action"
    bot = "5u08kd0a56b698ca10d98e6s"
    user = "nupur.khare"
    value = "keyvalue"
    user_msg = "What kind of language is python?"
    bot_content = "Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected."
    generated_text = "Python is dynamically typed, garbage-collected, high level, general purpose programming."
    Actions(name='http_action', type=ActionType.http_action.value, bot=bot, user=user).save()
    KeyVault(key="FIRSTNAME", value="nupur", bot=bot, user=user).save()
    KeyVault(key="CONTACT", value="9876543219", bot=bot, user=user).save()
    HttpActionConfig(
        action_name='http_action',
        response=HttpActionResponse(dispatch=False,
                                    value="Python is a scripting language because it uses an interpreter to translate and run its code."),
        http_url="http://localhost:8081/mock",
        request_method="GET",
        headers=[HttpActionRequestBody(key="botid", parameter_type="slot", value="bot", encrypt=True),
                 HttpActionRequestBody(key="userid", parameter_type="value", value="1011", encrypt=True),
                 HttpActionRequestBody(key="tag", parameter_type="value", value="from_bot", encrypt=True),
                 HttpActionRequestBody(key="name", parameter_type="key_vault", value="FIRSTNAME", encrypt=True),
                 HttpActionRequestBody(key="contact", parameter_type="key_vault", value="CONTACT", encrypt=True)],
        params_list=[HttpActionRequestBody(key="bot", parameter_type="slot", value="bot", encrypt=True),
                     HttpActionRequestBody(key="user", parameter_type="value", value="1011", encrypt=False),
                     HttpActionRequestBody(key="tag", parameter_type="value", value="from_bot", encrypt=True),
                     HttpActionRequestBody(key="name", parameter_type="key_vault", value="FIRSTNAME",
                                           encrypt=False),
                     HttpActionRequestBody(key="contact", parameter_type="key_vault", value="CONTACT",
                                           encrypt=False)],
        bot=bot,
        user=user
    ).save()

    http_url = 'http://localhost:8081/mock'
    resp_msg = "Python is a scripting language because it uses an interpreter to translate and run its code."
    aioresponses.add(
        method=responses.GET,
        url=f"{http_url}?bot=5u08kd0a56b698ca10d98e6s&user=1011&tag=from_bot&name=nupur&contact=9876543219",
        payload=resp_msg,
        status=200
    )
    llm_prompts = [
        {'name': 'System Prompt', 'data': 'You are a personal assistant.',
         'instructions': 'Answer question based on the context below.', 'type': 'system', 'source': 'static',
         'is_enabled': True},
        {'name': 'Similarity Prompt',
         'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
         'type': 'user', 'source': 'bot_content', 'is_enabled': True},
        {'name': 'Python Prompt',
         'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
         'instructions': 'Answer according to the context', 'type': 'user', 'source': 'static',
         'is_enabled': True},
        {'name': 'Java Prompt',
         'data': 'Java is a programming language and computing platform first released by Sun Microsystems in 1995.',
         'instructions': 'Answer according to the context', 'type': 'user', 'source': 'static',
         'is_enabled': True},
        {'name': 'Action Prompt',
         'data': 'http_action',
         'instructions': 'Answer according to the context', 'type': 'user', 'source': 'action',
         'is_enabled': True}
    ]

    def mock_completion_for_answer(*args, **kwargs):
        return convert_to_openai_object(
            OpenAIResponse({'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}, {}))

    def __mock_fetch_similar(*args, **kwargs):
        return {'result': [{'id': uuid7().__str__(), 'score': 0.80, 'payload': {'content': bot_content}}]}

    mock_completion.return_value = mock_completion_for_answer()
    embedding = list(np.random.random(GPT3FAQEmbedding.__embedding__))
    mock_embedding.return_value = embedding
    mock_completion.return_value = generated_text
    mock_search.return_value = __mock_fetch_similar()
    Actions(name=action_name, type=ActionType.prompt_action.value, bot=bot, user=user).save()
    BotSettings(llm_settings=LLMSettings(enable_faq=True), bot=bot, user=user).save()
    PromptAction(name=action_name, bot=bot, user=user, llm_prompts=llm_prompts).save()
    BotSecrets(secret_type=BotSecretType.gpt_key.value, value=value, bot=bot, user=user).save()

    request_object = json.load(open("tests/testing_data/actions/action-request.json"))
    request_object["tracker"]["slots"]["bot"] = bot
    request_object["next_action"] = action_name
    request_object["tracker"]["sender_id"] = user
    request_object["tracker"]["latest_message"]['text'] = user_msg
    request_object['tracker']['events'] = [{"event": "bot", 'text': 'hello',
                                            "data": {"elements": '', "quick_replies": '', "buttons": '',
                                                     "attachment": '',
                                                     "image": '', "custom": ''}},
                                           {'event': 'bot', "text": "how are you",
                                            "data": {"elements": '', "quick_replies": '', "buttons": '',
                                                     "attachment": '',
                                                     "image": '', "custom": ''}}]

    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response_json['events'] == [
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response', 'value': generated_text}]
    assert response_json['responses'] == [
        {'text': generated_text, 'buttons': [], 'elements': [], 'custom': {}, 'template': None, 'response': None,
         'image': None, 'attachment': None}]
    log = ActionServerLogs.objects(bot=bot, type=ActionType.prompt_action.value, status="SUCCESS").get()
    assert log['llm_logs'] == []
    assert mock_completion.call_args.args[1] == 'What kind of language is python?'
    assert mock_completion.call_args.args[2] == 'You are a personal assistant.\n'
    with open('tests/testing_data/actions/action_prompt.txt', 'r') as file:
        prompt_data = file.read()
    assert mock_completion.call_args.args[3] == prompt_data


@mock.patch.object(GPT3FAQEmbedding, "_GPT3FAQEmbedding__get_answer", autospec=True)
@mock.patch.object(GPT3FAQEmbedding, "_GPT3FAQEmbedding__get_embedding", autospec=True)
@mock.patch.object(ActionUtility, "perform_google_search", autospec=True)
def test_kairon_faq_response_with_google_search_prompt(mock_google_search, mock_embedding, mock_completion):
    from kairon.shared.llm.gpt3 import GPT3FAQEmbedding
    from openai.util import convert_to_openai_object
    from openai.openai_response import OpenAIResponse

    responses.reset()
    action_name = "kairon_faq_action"
    google_action_name = "custom_search_action"
    bot = "5u08kd0a56b698ca10hgjgjkhgjks"
    value = "keyvalue"
    user_msg = "What is kanban"
    user = 'test_user'
    Actions(name=action_name, type=ActionType.prompt_action.value, bot=bot, user=user).save()
    Actions(name=google_action_name, type=ActionType.google_search_action.value, bot=bot, user='test_user').save()
    GoogleSearchAction(name=google_action_name, api_key=CustomActionRequestParameters(value='1234567890'),
                       search_engine_id='asdfg::123456', bot=bot, user=user, dispatch_response=False,
                       num_results=3,
                       set_slot="google_response").save()
    BotSettings(llm_settings=LLMSettings(enable_faq=True), bot=bot, user=user).save()
    BotSecrets(secret_type=BotSecretType.gpt_key.value, value=value, bot=bot, user=user).save()
    generated_text = 'Kanban is a workflow management tool which visualizes both the process (the workflow) and the actual work passing through that process.'

    def _run_action(*args, **kwargs):
        return [{
            'title': 'Kanban',
            'text': 'Kanban visualizes both the process (the workflow) and the actual work passing through that process.',
            'link': "https://www.digite.com/kanban/what-is-kanban/"
        }, {
            'title': 'Kanban Project management',
            'text': 'Kanban project management is one of the emerging PM methodologies, and the Kanban approach is suitable for every team and goal.',
            'link': "https://www.digite.com/kanban/what-is-kanban-project-mgmt/"
        }, {
            'title': 'Kanban agile',
            'text': 'Kanban is a popular framework used to implement agile and DevOps software development.',
            'link': "https://www.digite.com/kanban/what-is-kanban-agile/"
        }]

    llm_prompts = [
        {'name': 'System Prompt', 'data': 'You are a personal assistant.', 'is_enabled': True,
         'instructions': 'Answer question based on the context below.', 'type': 'system', 'source': 'static'},
        {'name': 'Google search Prompt', 'data': 'custom_search_action',
         'instructions': 'Answer according to the context', 'type': 'user', 'source': 'action', 'is_enabled': True}
    ]
    PromptAction(name=action_name, bot=bot, user=user, llm_prompts=llm_prompts).save()

    def mock_completion_for_answer(*args, **kwargs):
        return convert_to_openai_object(
            OpenAIResponse({'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}, {}))

    mock_completion.return_value = mock_completion_for_answer()
    embedding = list(np.random.random(GPT3FAQEmbedding.__embedding__))
    mock_embedding.return_value = embedding
    mock_completion.return_value = generated_text
    mock_google_search.side_effect = _run_action

    request_object = json.load(open("tests/testing_data/actions/action-request.json"))
    request_object["tracker"]["slots"]["bot"] = bot
    request_object["next_action"] = action_name
    request_object["tracker"]["sender_id"] = user
    request_object["tracker"]["latest_message"]['text'] = user_msg

    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response_json['events'] == [
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response', 'value': generated_text}]
    assert response_json['responses'] == [{'text': generated_text,
                                           'buttons': [], 'elements': [], 'custom': {}, 'template': None,
                                           'response': None, 'image': None,
                                           'attachment': None}]
    log = ActionServerLogs.objects(bot=bot, type=ActionType.prompt_action.value, status="SUCCESS").get()
    assert log['llm_logs'] == []
    assert mock_completion.call_args.args[1] == 'What is kanban'
    assert mock_completion.call_args.args[2] == 'You are a personal assistant.\n'
    print(mock_completion.call_args.args[3])
    assert mock_completion.call_args.args[
               3] == 'Google search Prompt:\nKanban visualizes both the process (the workflow) and the actual work passing through that process.\nTo know more, please visit: <a href = "https://www.digite.com/kanban/what-is-kanban/" target="_blank" >Kanban</a>\n\nKanban project management is one of the emerging PM methodologies, and the Kanban approach is suitable for every team and goal.\nTo know more, please visit: <a href = "https://www.digite.com/kanban/what-is-kanban-project-mgmt/" target="_blank" >Kanban Project management</a>\n\nKanban is a popular framework used to implement agile and DevOps software development.\nTo know more, please visit: <a href = "https://www.digite.com/kanban/what-is-kanban-agile/" target="_blank" >Kanban agile</a>\nInstructions on how to use Google search Prompt:\nAnswer according to the context\n\n'


def test_prompt_response_action_with_action_not_found():
    action_name = "kairon_faq_action"
    bot = "5u08kd0a00b698ca10d98u9q"
    user = "nupurk"
    value = "keyvalue"
    user_msg = "What kind of language is python?"

    Actions(name=action_name, type=ActionType.prompt_action.value, bot=bot, user=user).save()
    BotSettings(llm_settings=LLMSettings(enable_faq=True), bot=bot, user=user).save()
    BotSecrets(secret_type=BotSecretType.gpt_key.value, value=value, bot=bot, user=user).save()

    request_object = json.load(open("tests/testing_data/actions/action-request.json"))
    request_object["tracker"]["slots"]["bot"] = bot
    request_object["next_action"] = action_name
    request_object["tracker"]["sender_id"] = user
    request_object["tracker"]["latest_message"]['text'] = user_msg

    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response_json['events'] == [
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
         'value': "I'm sorry, I didn't quite understand that. Could you rephrase?"}]
    assert response_json['responses'] == [
        {'text': "I'm sorry, I didn't quite understand that. Could you rephrase?", 'buttons': [], 'elements': [],
         'custom': {}, 'template': None, 'response': None, 'image': None, 'attachment': None}]
    log = ActionServerLogs.objects(bot=bot, type=ActionType.prompt_action.value, status="FAILURE").get()
    log['exception'] = 'No action found for given bot and name'


@mock.patch.object(GPT3FAQEmbedding, "_GPT3FAQEmbedding__get_answer", autospec=True)
@mock.patch.object(GPT3FAQEmbedding, "_GPT3FAQEmbedding__get_embedding", autospec=True)
@patch("kairon.shared.rest_client.AioRestClient.request", autospec=True)
def test_prompt_action_dispatch_response_disabled(mock_search, mock_embedding, mock_completion):
    from kairon.shared.llm.gpt3 import GPT3FAQEmbedding
    from openai.util import convert_to_openai_object
    from openai.openai_response import OpenAIResponse
    from uuid6 import uuid7

    action_name = "kairon_faq_action"
    bot = "5u80fd0a56c908ca10d35d2sjhj"
    user = "udit.pandey"
    value = "keyvalue"
    user_msg = "What is the name of prompt?"
    bot_content = "Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected."
    generated_text = "Python is dynamically typed, garbage-collected, high level, general purpose programming."
    llm_prompts = [
        {'name': 'System Prompt', 'data': 'You are a personal assistant.',
         'instructions': 'Answer question based on the context below.', 'type': 'system', 'source': 'static',
         'is_enabled': True},
        {'name': 'Similarity Prompt',
         'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
         'type': 'user', 'source': 'bot_content', 'is_enabled': True},
        {'name': 'Language Prompt',
         'data': 'type',
         'instructions': 'Answer according to the context', 'type': 'user', 'source': 'slot',
         'is_enabled': True},
    ]

    def mock_completion_for_answer(*args, **kwargs):
        return convert_to_openai_object(
            OpenAIResponse({'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}, {}))

    def __mock_fetch_similar(*args, **kwargs):
        return {'result': [{'id': uuid7().__str__(), 'score': 0.80, 'payload': {'content': bot_content}}]}

    mock_completion.return_value = mock_completion_for_answer()

    embedding = list(np.random.random(GPT3FAQEmbedding.__embedding__))
    mock_embedding.return_value = embedding
    mock_completion.return_value = generated_text
    mock_search.return_value = __mock_fetch_similar()
    Actions(name=action_name, type=ActionType.prompt_action.value, bot=bot, user=user).save()
    BotSettings(llm_settings=LLMSettings(enable_faq=True), bot=bot, user=user).save()
    PromptAction(name=action_name, bot=bot, user=user, llm_prompts=llm_prompts, dispatch_response=False).save()
    BotSecrets(secret_type=BotSecretType.gpt_key.value, value=value, bot=bot, user=user).save()

    request_object = json.load(open("tests/testing_data/actions/action-request.json"))
    request_object["tracker"]["slots"]["bot"] = bot
    request_object["next_action"] = action_name
    request_object["tracker"]["sender_id"] = user
    request_object["tracker"]["latest_message"]['text'] = user_msg
    request_object['tracker']['events'] = [{"event": "bot", 'text': 'hello',
                                            "data": {"elements": '', "quick_replies": '', "buttons": '',
                                                     "attachment": '', "image": '', "custom": ''}},
                                           {'event': 'bot', "text": "how are you",
                                            "data": {"elements": '', "quick_replies": '', "buttons": '',
                                                     "attachment": '', "image": '', "custom": ''}}]

    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response_json['events'] == [
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response', 'value': generated_text}]
    assert response_json['responses'] == []
    log = ActionServerLogs.objects(bot=bot, type=ActionType.prompt_action.value, status="SUCCESS").get()
    assert log['llm_logs'] == []
    assert mock_completion.call_args.args[1] == 'What is the name of prompt?'
    assert mock_completion.call_args.args[2] == 'You are a personal assistant.\n'
    with open('tests/testing_data/actions/slot_prompt.txt', 'r') as file:
        prompt_data = file.read()
    assert mock_completion.call_args.args[3] == prompt_data


@mock.patch.object(GPT3FAQEmbedding, "_GPT3FAQEmbedding__get_answer", autospec=True)
@mock.patch.object(GPT3FAQEmbedding, "_GPT3FAQEmbedding__get_embedding", autospec=True)
@patch("kairon.shared.actions.utils.ActionUtility.compose_response", autospec=True)
@patch("kairon.shared.rest_client.AioRestClient.request", autospec=True)
def test_prompt_action_set_slots(mock_search, mock_slot_set, mock_mock_embedding, mock_completion):
    from openai.util import convert_to_openai_object
    from openai.openai_response import OpenAIResponse

    action_name = "kairon_faq_action"
    bot = "5u80fd0a56c908ca10d35d2sjhjhjhj"
    user = "udit.pandey"
    value = "keyvalue"
    user_msg = "category of record created on 15/01/2023?"
    generated_text = "{\"api_type\": \"filter\", {\"filter\": {\"must\": [{\"key\": \"Date Added\", \"match\": {\"value\": 1673721000.0}}]}}}"
    llm_prompts = [
        {'name': 'System Prompt', 'data': 'You are a personal assistant.',
         'instructions': 'Answer question based on the context below.', 'type': 'system', 'source': 'static',
         'is_enabled': True},
        {'name': 'Qdrant Prompt',
         'data': "Convert user questions into json requests in qdrant such that they will either filter, apply range queries "
                 "and search the payload in qdrant. Sample payload present in qdrant looks like below with each of the points starting with 1 to 5 is a record in qdrant."
                 "1. {\"Category (Risk, Issue, Action Item)\": \"Risk\", \"Date Added\": 1673721000.0,"
                 "2. {\"Category (Risk, Issue, Action Item)\": \"Action Item\", \"Date Added\": 1673721000.0,"
                 "For eg: to find category of record created on 15/01/2023, the filter query is:"
                 "{\"filter\": {\"must\": [{\"key\": \"Date Added\", \"match\": {\"value\": 1673721000.0}}]}}",
         'instructions': 'Create qdrant filter query out of user message based on above instructions.',
         'type': 'user', 'source': 'static', 'is_enabled': True},
    ]

    def mock_completion_for_answer(*args, **kwargs):
        return convert_to_openai_object(
            OpenAIResponse({'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}, {}))

    mock_completion.return_value = mock_completion_for_answer()
    mock_completion.return_value = generated_text
    log1 = ['Slot: api_type', 'evaluation_type: expression', f"data: {generated_text}", 'response: filter']
    log2 = ['Slot: query', 'evaluation_type: expression', f"data: {generated_text}",
            'response: {\"must\": [{\"key\": \"Date Added\", \"match\": {\"value\": 1673721000.0}}]}']
    mock_slot_set.side_effect = [("filter", log1), (
        "{\"must\": [{\"key\": \"Date Added\", \"match\": {\"value\": 1673721000.0}}]}", log2)]
    Actions(name=action_name, type=ActionType.prompt_action.value, bot=bot, user=user).save()
    BotSettings(llm_settings=LLMSettings(enable_faq=True), bot=bot, user=user).save()
    PromptAction(name=action_name, bot=bot, user=user, llm_prompts=llm_prompts, dispatch_response=False,
                 set_slots=[
                     SetSlotsFromResponse(name="api_type", value="${data['api_type']}", evaluation_type="script"),
                     SetSlotsFromResponse(name="query", value="${data['filter']}",
                                          evaluation_type="script")]).save()
    BotSecrets(secret_type=BotSecretType.gpt_key.value, value=value, bot=bot, user=user).save()

    request_object = json.load(open("tests/testing_data/actions/action-request.json"))
    request_object["tracker"]["slots"]["bot"] = bot
    request_object["next_action"] = action_name
    request_object["tracker"]["sender_id"] = user
    request_object["tracker"]["latest_message"]['text'] = user_msg
    request_object['tracker']['events'] = [{"event": "bot", 'text': 'hello',
                                            "data": {"elements": '', "quick_replies": '', "buttons": '',
                                                     "attachment": '', "image": '', "custom": ''}},
                                           {'event': 'bot', "text": "how are you",
                                            "data": {"elements": '', "quick_replies": '', "buttons": '',
                                                     "attachment": '', "image": '', "custom": ''}}]

    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    print(response_json)
    assert response_json['events'] == [{'event': 'slot', 'timestamp': None, 'name': 'api_type', 'value': 'filter'},
                                       {'event': 'slot', 'timestamp': None, 'name': 'query',
                                        'value': '{"must": [{"key": "Date Added", "match": {"value": 1673721000.0}}]}'},
                                       {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
                                        'value': '{"api_type": "filter", {"filter": {"must": [{"key": "Date Added", "match": {"value": 1673721000.0}}]}}}'}]
    assert response_json['responses'] == []
    log = ActionServerLogs.objects(bot=bot, type=ActionType.prompt_action.value, status="SUCCESS").get()
    assert log['llm_logs'] == []
    assert mock_completion.call_args.args[1] == user_msg
    assert mock_completion.call_args.args[2] == 'You are a personal assistant.\n'


@mock.patch.object(GPT3FAQEmbedding, "_GPT3FAQEmbedding__get_answer", autospec=True)
@mock.patch.object(GPT3FAQEmbedding, "_GPT3FAQEmbedding__get_embedding", autospec=True)
@patch("kairon.shared.rest_client.AioRestClient.request", autospec=True)
def test_prompt_action_response_action_slot_prompt(mock_search, mock_embedding, mock_completion):
    from kairon.shared.llm.gpt3 import GPT3FAQEmbedding
    from openai.util import convert_to_openai_object
    from openai.openai_response import OpenAIResponse
    from uuid6 import uuid7

    action_name = "kairon_faq_action"
    bot = "5u80fd0a56c908ca10d35d2s"
    user = "udit.pandey"
    value = "keyvalue"
    user_msg = "What is the name of prompt?"
    bot_content = "Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected."
    generated_text = "Python is dynamically typed, garbage-collected, high level, general purpose programming."
    llm_prompts = [
        {'name': 'System Prompt', 'data': 'You are a personal assistant.',
         'instructions': 'Answer question based on the context below.', 'type': 'system', 'source': 'static',
         'is_enabled': True},
        {'name': 'Similarity Prompt',
         'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
         'type': 'user', 'source': 'bot_content', 'is_enabled': True},
        {'name': 'Language Prompt',
         'data': 'type',
         'instructions': 'Answer according to the context', 'type': 'user', 'source': 'slot',
         'is_enabled': True},
    ]

    def mock_completion_for_answer(*args, **kwargs):
        return convert_to_openai_object(
            OpenAIResponse({'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}, {}))

    def __mock_fetch_similar(*args, **kwargs):
        return {'result': [{'id': uuid7().__str__(), 'score': 0.80, 'payload': {'content': bot_content}}]}

    mock_completion.return_value = mock_completion_for_answer()

    embedding = list(np.random.random(GPT3FAQEmbedding.__embedding__))
    mock_embedding.return_value = embedding
    mock_completion.return_value = generated_text
    mock_search.return_value = __mock_fetch_similar()
    Actions(name=action_name, type=ActionType.prompt_action.value, bot=bot, user=user).save()
    BotSettings(llm_settings=LLMSettings(enable_faq=True), bot=bot, user=user).save()
    PromptAction(name=action_name, bot=bot, user=user, llm_prompts=llm_prompts).save()
    BotSecrets(secret_type=BotSecretType.gpt_key.value, value=value, bot=bot, user=user).save()

    request_object = json.load(open("tests/testing_data/actions/action-request.json"))
    request_object["tracker"]["slots"]["bot"] = bot
    request_object["next_action"] = action_name
    request_object["tracker"]["sender_id"] = user
    request_object["tracker"]["latest_message"]['text'] = user_msg
    request_object['tracker']['events'] = [{"event": "bot", 'text': 'hello',
                                            "data": {"elements": '', "quick_replies": '', "buttons": '',
                                                     "attachment": '', "image": '', "custom": ''}},
                                           {'event': 'bot', "text": "how are you",
                                            "data": {"elements": '', "quick_replies": '', "buttons": '',
                                                     "attachment": '', "image": '', "custom": ''}}]

    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response_json['events'] == [
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response', 'value': generated_text}]
    assert response_json['responses'] == [
        {'text': generated_text, 'buttons': [], 'elements': [], 'custom': {}, 'template': None,
         'response': None, 'image': None, 'attachment': None}
        ]
    log = ActionServerLogs.objects(bot=bot, type=ActionType.prompt_action.value, status="SUCCESS").get()
    assert log['llm_logs'] == []
    assert mock_completion.call_args.args[1] == 'What is the name of prompt?'
    assert mock_completion.call_args.args[2] == 'You are a personal assistant.\n'
    with open('tests/testing_data/actions/slot_prompt.txt', 'r') as file:
        prompt_data = file.read()
    assert mock_completion.call_args.args[3] == prompt_data


@mock.patch.object(GPT3FAQEmbedding, "_GPT3FAQEmbedding__get_answer", autospec=True)
@mock.patch.object(GPT3FAQEmbedding, "_GPT3FAQEmbedding__get_embedding", autospec=True)
@patch("kairon.shared.rest_client.AioRestClient.request", autospec=True)
def test_prompt_action_user_message_in_slot(mock_search, mock_embedding, mock_completion):
    from kairon.shared.llm.gpt3 import GPT3FAQEmbedding
    from openai.util import convert_to_openai_object
    from openai.openai_response import OpenAIResponse
    from uuid6 import uuid7

    action_name = "kairon_faq_action"
    bot = "5u80fd0a56c908ca10d35d2sadfsf"
    user = "udit.pandey"
    value = "keyvalue"
    user_msg = '/kanban_story{"kairon_user_msg": "Kanban And Scrum Together?"}'
    bot_content = "Scrum teams using Kanban as a visual management tool can get work delivered faster and more often. Prioritized tasks are completed first as the team collectively decides what is best using visual cues from the Kanban board. The best part is that Scrum teams can use Kanban and Scrum at the same time."
    generated_text = "YES you can use both in a single project. However, in order to run the Sprint, you should only use the 'Scrum board'. On the other hand 'Kanban board' is only to track the progress or status of the Jira issues."
    llm_prompts = [
        {'name': 'System Prompt', 'data': 'You are a personal assistant.',
         'instructions': 'Answer question based on the context below.', 'type': 'system', 'source': 'static',
         'is_enabled': True},
        {'name': 'Similarity Prompt',
         'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
         'type': 'user', 'source': 'bot_content', 'is_enabled': True},
    ]

    def mock_completion_for_answer(*args, **kwargs):
        return convert_to_openai_object(
            OpenAIResponse({'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}, {}))

    def __mock_fetch_similar(*args, **kwargs):
        return {'result': [{'id': uuid7().__str__(), 'score': 0.80, 'payload': {'content': bot_content}}]}

    mock_completion.return_value = mock_completion_for_answer()

    embedding = list(np.random.random(GPT3FAQEmbedding.__embedding__))
    mock_embedding.return_value = embedding
    mock_completion.return_value = generated_text
    mock_search.return_value = __mock_fetch_similar()
    Actions(name=action_name, type=ActionType.prompt_action.value, bot=bot, user=user).save()
    BotSettings(llm_settings=LLMSettings(enable_faq=True), bot=bot, user=user).save()
    PromptAction(name=action_name, bot=bot, user=user, llm_prompts=llm_prompts).save()
    BotSecrets(secret_type=BotSecretType.gpt_key.value, value=value, bot=bot, user=user).save()

    request_object = json.load(open("tests/testing_data/actions/action-request.json"))
    request_object["tracker"]["slots"]["bot"] = bot
    request_object["next_action"] = action_name
    request_object["tracker"]["sender_id"] = user
    request_object["tracker"]["latest_message"] = {
        'text': user_msg, 'intent_ranking': [{'name': 'kanban_story'}],
        "entities": [{"value": "Kanban And Scrum Together?", "entity": KAIRON_USER_MSG_ENTITY}]
    }

    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response_json['events'] == [
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response', 'value': generated_text}]
    assert response_json['responses'] == [
        {'text': generated_text, 'buttons': [], 'elements': [], 'custom': {}, 'template': None,
         'response': None, 'image': None, 'attachment': None}
        ]
    assert mock_completion.call_args[0][1] == 'Kanban And Scrum Together?'
    assert mock_completion.call_args[0][2] == 'You are a personal assistant.\n'
    assert mock_completion.call_args[0][3] == """
Similarity Prompt:
Scrum teams using Kanban as a visual management tool can get work delivered faster and more often. Prioritized tasks are completed first as the team collectively decides what is best using visual cues from the Kanban board. The best part is that Scrum teams can use Kanban and Scrum at the same time.
Instructions on how to use Similarity Prompt: Answer question based on the context above, if answer is not in the context go check previous logs.
"""
