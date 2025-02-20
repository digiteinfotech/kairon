import asyncio
import datetime
import os
from urllib.parse import urlencode, urljoin
from kairon.shared.utils import Utility
os.environ["system_file"] = "./tests/testing_data/system.yaml"
Utility.load_environment()
Utility.load_system_metadata()
import urllib

import litellm
from unittest import mock
import numpy as np
import pytest
import responses
import ujson as json
from apscheduler.util import obj_to_ref
from deepdiff import DeepDiff
from fastapi.testclient import TestClient
from jira import JIRAError
from litellm import embedding
from mongoengine import connect



from kairon.events.executors.factory import ExecutorFactory
from kairon.shared.callback.data_objects import CallbackConfig, encrypt_secret


from kairon.actions.definitions.live_agent import ActionLiveAgent
from kairon.actions.definitions.set_slot import ActionSetSlot
from kairon.actions.server import action
from kairon.shared.actions.data_objects import HttpActionConfig, SlotSetAction, Actions, FormValidationAction, \
    EmailActionConfig, ActionServerLogs, GoogleSearchAction, JiraAction, ZendeskAction, PipedriveLeadsAction, SetSlots, \
    HubspotFormsAction, HttpActionResponse, HttpActionRequestBody, SetSlotsFromResponse, CustomActionRequestParameters, \
    KaironTwoStageFallbackAction, TwoStageFallbackTextualRecommendations, RazorpayAction, PromptAction, FormSlotSet, \
    DatabaseAction, DbQuery, PyscriptActionConfig, WebSearchAction, UserQuestion, LiveAgentActionConfig, \
    CustomActionParameters, CallbackActionConfig, ScheduleAction, CustomActionDynamicParameters
from kairon.shared.actions.exception import ActionFailure
from kairon.shared.actions.models import ActionType, ActionParameterType, DispatchType, DbActionOperationType, \
    DbQueryValueType
from kairon.shared.actions.utils import ActionUtility
from kairon.shared.admin.constants import BotSecretType
from kairon.shared.admin.data_objects import BotSecrets, LLMSecret
from kairon.shared.constants import KAIRON_USER_MSG_ENTITY, FORM_SLOT_SET_TYPE
from kairon.shared.data.constant import KAIRON_TWO_STAGE_FALLBACK, FALLBACK_MESSAGE, GPT_LLM_FAQ, \
    DEFAULT_NLU_FALLBACK_RESPONSE
from kairon.shared.data.data_objects import Slots, KeyVault, BotSettings, LLMSettings
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.vector_embeddings.db.qdrant import Qdrant
from kairon.shared.llm.processor import LLMProcessor
import re
import pickle

os.environ['ASYNC_TEST_TIMEOUT'] = "360"
os.environ["system_file"] = "./tests/testing_data/system.yaml"

client = TestClient(action)
OPENAI_EMBEDDING_OUTPUT = 1536


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


def test_healthcheck():
    response = client.get("/healthcheck")
    result = response.json()
    assert response.status_code == 200
    assert result["message"] == "health check ok"


def test_callback_action_execution(aioresponses):
    bot_settings = BotSettings(bot='6697add6b8e47524eb983373', user='test')
    bot_settings.live_agent_enabled = True
    bot_settings.save()
    action_name = "callback_action1"
    Actions(name=action_name, type=ActionType.callback_action.value,
            bot="6697add6b8e47524eb983373", user="user").save()
    CallbackActionConfig(
        name="callback_action1",
        callback_name="callback_script2",
        dynamic_url_slot_name="callback_url",
        metadata_list=[],
        bot_response="Hello",
        dispatch_bot_response=True,
        bot="6697add6b8e47524eb983373",
        user="user"
    ).save()

    CallbackConfig(
        name="callback_script2",
        pyscript_code="bot_response='hello world'",
        validation_secret=encrypt_secret("gAAAAABmqK71xDb4apnxOAfJjDUv1lrCTooWNX0GPyBHhqW1KBlblUqGNPwsX1V7FlIlgpwWGRWljiYp9mYAf1eG4AcG1dTXQuZCndCewox"),
        execution_mode="sync",
        bot="6697add6b8e47524eb983373",
    ).save()

    request_object = {
        "next_action": action_name,
        "tracker": {
            "sender_id": "default",
            "conversation_id": "default",
            "slots": {"bot": "6697add6b8e47524eb983373", "location": "Bangalore", "langauge": "Kannada"},
            "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'live_agent_action'}]},
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
                                           "text": "can't"}, "input_channel": "facebook",
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
                 "input_channel": "facebook", "message_id": "e96e2a85de0748798748385503c65fb3", "metadata": {}},
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
            "slots": {"bot": "6697add6b8e47524eb983373"},
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
    assert len(response_json['responses']) == 1
    response_json['events'][0].pop('value')
    assert response_json == {'events': [{'event': 'slot', 'timestamp': None, 'name': 'callback_url', }], 'responses': [
        {'text': 'Hello', 'buttons': [], 'elements': [], 'custom': {}, 'template': None, 'response': None,
         'image': None, 'attachment': None}]}

    log = ActionServerLogs.objects(action="callback_action1").get().to_mongo().to_dict()
    log.pop('_id')
    log.pop('timestamp')
    log.pop('callback_url')
    log.pop('identifier')
    assert log == {'type': 'callback_action', 'intent': 'live_agent_action',
                   'action': 'callback_action1', 'sender': 'default',
                   'headers': {}, 'bot_response': 'Hello',
                   'messages': [], 'bot': '6697add6b8e47524eb983373',
                   'status': 'SUCCESS', 'user_msg': 'get intents',
                   'callback_url_slot': 'callback_url', 'metadata': {}}


def test_callback_action_execution_fail_no_callback_config(aioresponses):
    bot_settings = BotSettings(bot='6697add6b8e47524eb983373', user='test')
    bot_settings.save()
    action_name = "callback_action2"
    Actions(name=action_name, type=ActionType.callback_action.value,
            bot="6697add6b8e47524eb983373", user="user").save()
    CallbackActionConfig(
        name="callback_action2",
        callback_name="callback_script3",
        dynamic_url_slot_name="callback_url",
        metadata_list=[],
        bot_response="Hello",
        dispatch_bot_response=True,
        bot="6697add6b8e47524eb983373",
        user="user"
    ).save()

    request_object = {
        "next_action": action_name,
        "tracker": {
            "sender_id": "default",
            "conversation_id": "default",
            "slots": {"bot": "6697add6b8e47524eb983373", "location": "Bangalore", "langauge": "Kannada"},
            "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'live_agent_action'}]},
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
                                           "text": "can't"}, "input_channel": "facebook",
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
                 "input_channel": "facebook", "message_id": "e96e2a85de0748798748385503c65fb3", "metadata": {}},
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
            "slots": {"bot": "6697add6b8e47524eb983373"},
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

    log = ActionServerLogs.objects(action="callback_action2")[0].to_mongo().to_dict()
    print(log)
    log.pop('_id')
    log.pop('timestamp')
    log.pop('callback_url')
    log.pop('identifier')
    assert log == {'type': 'callback_action', 'intent': 'live_agent_action',
                   'action': 'callback_action2', 'sender': 'default',
                   'headers': {}, 'bot_response': 'Hello',
                   'messages': [], 'bot': '6697add6b8e47524eb983373',
                   'exception': "Callback Configuration with name 'callback_script3' does not exist!",
                   'status': 'FAILURE', 'user_msg': 'get intents',
                   'callback_url_slot': 'callback_url', 'metadata': {}}


def test_live_agent_action_execution(aioresponses):
    bot_settings = BotSettings(bot='5f50fd0a56b698ca10d35d2z', user='test')
    bot_settings.live_agent_enabled = True
    bot_settings.save()
    action_name = "live_agent_action"
    Actions(name=action_name, type=ActionType.live_agent_action.value,
            bot="5f50fd0a56b698ca10d35d2z", user="user").save()
    LiveAgentActionConfig(
        name="live_agent_action",
        bot_response="Connecting to live agent",
        dispatch_bot_response=True,
        bot="5f50fd0a56b698ca10d35d2z",
        user="user"
    ).save()

    aioresponses.add(
        method="POST",
        url=f"{Utility.environment['live_agent']['url']}/conversation/request",
        payload={"success": True, "data": {"identifier": "asjlbceuwvbalncouabvlvnlavni", "msg": None}, "message": None,
                 "error_code": 0},
        body={'bot_id': '5f50fd0a56b698ca10d35d2z', 'sender_id': 'default', 'channel': 'messenger'},
        status=200
    )

    request_object = {
        "next_action": action_name,
        "tracker": {
            "sender_id": "default",
            "conversation_id": "default",
            "slots": {"bot": "5f50fd0a56b698ca10d35d2z", "location": "Bangalore", "langauge": "Kannada"},
            "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'live_agent_action'}]},
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
                                           "text": "can't"}, "input_channel": "facebook",
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
                 "input_channel": "facebook", "message_id": "e96e2a85de0748798748385503c65fb3", "metadata": {}},
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
    assert len(response_json['responses']) == 1
    assert response_json['responses'][0]['text'] == 'Connecting to live agent'
    log = ActionServerLogs.objects(action="live_agent_action").get().to_mongo().to_dict()
    log.pop('_id')
    log.pop('timestamp')
    assert log == {'type': 'live_agent_action', 'intent': 'live_agent_action', 'action': 'live_agent_action',
                   'sender': 'default', 'headers': {}, 'bot_response': 'Connecting to live agent', 'messages': [],
                   'bot': '5f50fd0a56b698ca10d35d2z', 'status': 'SUCCESS', 'user_msg': 'get intents'}


def test_live_agent_action_execution_no_agent_available(aioresponses):
    action_name = "live_agent_action"
    aioresponses.add(
        method="POST",
        url=f"{Utility.environment['live_agent']['url']}/conversation/request",
        payload={"success": True,
                 "data": {"identifier": "asjlbceuwvbalncouabvlvnlavni", "msg": "live agent is not available"},
                 "message": None, "error_code": 0},
        body={'bot_id': '5f50fd0a56b698ca10d35d2z', 'sender_id': 'default', 'channel': 'messenger'},
        status=200
    )
    request_object = {
        "next_action": action_name,
        "tracker": {
            "sender_id": "default",
            "conversation_id": "default",
            "slots": {"bot": "5f50fd0a56b698ca10d35d2z", "location": "Bangalore", "langauge": "Kannada"},
            "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'live_agent_action'}]},
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
                                           "text": "can't"}, "input_channel": "facebook",
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
                 "input_channel": "facebook", "message_id": "e96e2a85de0748798748385503c65fb3", "metadata": {}},
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
    assert len(response_json['responses']) == 1
    assert response_json['responses'][0]['text'] == 'live agent is not available'


def test_live_agent_action_execution_with_exception(aioresponses):
    bot_settings = BotSettings(bot='5f50fd0a56b698ca10d35d21', user='user')
    bot_settings.live_agent_enabled = True
    bot_settings.save()

    action_name = "test_live_agent_action_execution_with_exception"
    Actions(name=action_name, type=ActionType.live_agent_action.value,
            bot="5f50fd0a56b698ca10d35d21", user="user").save()
    LiveAgentActionConfig(
        name="live_agent_action",
        bot_response="Connecting to live agent",
        dispatch_bot_response=True,
        bot="5f50fd0a56b698ca10d35d21",
        user="user"
    ).save()

    aioresponses.add(
        method="POST",
        url=f"{Utility.environment['live_agent']['url']}/conversation/request",
        payload={"success": False, "data": None, "message": "invalid request body", "error_code": 422},
        body={'bot_id': '5f50fd0a56b698ca10d35d21', 'sender_id': 'default', 'channel': 'invalid'},
        status=400
    )

    request_object = {
        "next_action": action_name,
        "tracker": {
            "sender_id": "default",
            "conversation_id": "default",
            "slots": {"bot": "5f50fd0a56b698ca10d35d21", "location": "Bangalore", "langauge": "Kannada"},
            "latest_message": {'text': 'get intents', 'intent_ranking': [{'name': 'live_agent_action'}]},
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
                                           "text": "can't"}, "input_channel": "facebook",
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
                 "input_channel": "facebook", "message_id": "e96e2a85de0748798748385503c65fb3", "metadata": {}},
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
            "slots": {"bot": "5f50fd0a56b698ca10d35d21"},
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
    assert len(response_json['responses']) == 1
    assert response_json['responses'][0]['text'] == 'Connecting to live agent'
    assert response_json == {'events': [], 'responses': [
        {'text': 'Connecting to live agent', 'buttons': [], 'elements': [], 'custom': {}, 'template': None,
         'response': None, 'image': None, 'attachment': None}]}


def test_retrieve_config_failure():
    action_live_agent = ActionLiveAgent(bot='test_bot', name='test_action')
    with pytest.raises(ActionFailure, match="No Live Agent action found for given action and bot"):
        action_live_agent.retrieve_config()


@responses.activate
def test_process_razorpay_action_with_notes():
    action_name = "test_process_razorpay_action_with_notes"
    bot = "5f50fd0a56b698ca10d35d1z"

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
        notes=[
            CustomActionRequestParameters(key="order_id", parameter_type="slot",
                                          value="order_id", encrypt=True),
            CustomActionRequestParameters(key="phone_number", parameter_type="value",
                                          value="9876543210", encrypt=False),
        ],
        bot=bot, user="udit.pandey@digite.com"
    ).save()
    request_object = json.load(open("tests/testing_data/actions/action-request.json"))
    request_object["tracker"]["slots"]["bot"] = bot
    request_object["tracker"]["slots"]["amount"] = 11000
    request_object["tracker"]["slots"]["contact"] = "987654320"
    request_object["tracker"]["slots"]["order_id"] = "dsjdksjdksjdksj"
    request_object["next_action"] = action_name
    request_object["tracker"]["sender_id"] = "udit.pandey"

    response_object = json.load(open("tests/testing_data/actions/razorpay-success.json"))
    responses.add(
        "POST",
        "https://api.razorpay.com/v1/payment_links/",
        json=response_object,
        match=[responses.matchers.json_params_matcher({
            "amount": 11000, "currency": "INR",
            "customer": {"username": "udit.pandey", "email": "udit.pandey", "contact": "987654320"},
            "notes": {"phone_number": "9876543210", "order_id": "dsjdksjdksjdksj", "bot": "5f50fd0a56b698ca10d35d1z"}
        })]
    )

    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    print(response_json)
    assert response_json == {'events': [{'event': 'slot', 'name': 'kairon_action_response',
                                         'timestamp': None, 'value': 'https://rzp.io/i/nxrHnLJ'}],
                             'responses': [{'attachment': None, 'buttons': [], 'custom': {},
                                            'elements': [], 'image': None, 'response': None,
                                            'template': None, 'text': 'https://rzp.io/i/nxrHnLJ'}]}


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
        match=[responses.matchers.json_params_matcher({'source_code': script,
                                                       'predefined_objects': {'chat_log': [],
                                                                              'intent': 'pyscript_action',
                                                                              'kairon_user_msg': None, 'key_vault': {},
                                                                              'latest_message': {'intent_ranking': [
                                                                                  {'name': 'pyscript_action'}],
                                                                                  'text': 'get intents'},
                                                                              'sender_id': 'default',
                                                                              'session_started': None,
                                                                              'slot': {
                                                                                  'bot': '5f50fd0a56b698ca10d35d2z',
                                                                                  'langauge': 'Kannada',
                                                                                  'location': 'Bangalore'},
                                                                              'user_message': 'get intents'}

                                                       })]
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
def test_pyscript_action_execution_with_multiple_utterances():
    import textwrap

    action_name = "test_pyscript_action_execution_with_multiple_utterances"
    Actions(name=action_name, type=ActionType.pyscript_action.value,
            bot="5f50fd0a56b698ca10d35d2z", user="user").save()
    script = """
    numbers = [1, 2, 3, 4, 5]
    total = 0
    for i in numbers:
        total += i
    print(total)
    type = 'text'
    bot_response = [{'text': 'Hello!'}, 'How can I help you?']
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
        json={"success": True, "data": {"bot_response": [{'text': 'Hello!'}, 'How can I help you?'],
                                        'numbers': [1, 2, 3, 4, 5], 'total': 15, 'i': 5,
                                        "slots": {"location": "Bangalore", "langauge": "Kannada"},
                                        "type": "text"},
              "message": None, "error_code": 0},
        match=[responses.matchers.json_params_matcher(
            {'source_code': script,
             'predefined_objects': {'sender_id': 'default', 'user_message': 'get intents',
                                    'latest_message': {'intent_ranking': [{'name': 'pyscript_action'}],
                                                       'text': 'get intents'},
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
    assert len(response_json['responses']) == 2
    assert response_json['events'] == [
        {'event': 'slot', 'timestamp': None, 'name': 'location', 'value': 'Bangalore'},
        {'event': 'slot', 'timestamp': None, 'name': 'langauge', 'value': 'Kannada'},
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
         'value': [{'text': 'Hello!'}, 'How can I help you?']}]
    assert response_json['responses'][0]['custom'] == {'text': 'Hello!'}
    assert response_json['responses'][1]['text'] == 'How can I help you?'


@responses.activate
def test_pyscript_action_execution_with_multiple_integer_utterances():
    import textwrap

    action_name = "test_pyscript_action_execution_with_multiple_integer_utterances"
    Actions(name=action_name, type=ActionType.pyscript_action.value,
            bot="5f50fd0a56b698ca10d35d2z", user="user").save()
    script = """
    numbers = [1, 2, 3]
    total = 0
    for i in numbers:
        total += i
    print(total)
    type = 'text'
    bot_response = numbers
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
        json={"success": True, "data": {"bot_response": [1, 2, 3],
                                        'numbers': [1, 2, 3], 'total': 6, 'i': 3,
                                        "slots": {"location": "Bangalore", "langauge": "Kannada"},
                                        "type": "text"},
              "message": None, "error_code": 0},
        match=[responses.matchers.json_params_matcher(
            {'source_code': script,
             'predefined_objects': {'sender_id': 'default', 'user_message': 'get intents',
                                    'latest_message': {'intent_ranking': [{'name': 'pyscript_action'}],
                                                       'text': 'get intents'},
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
    assert len(response_json['responses']) == 3
    assert response_json['events'] == [
        {'event': 'slot', 'timestamp': None, 'name': 'location', 'value': 'Bangalore'},
        {'event': 'slot', 'timestamp': None, 'name': 'langauge', 'value': 'Kannada'},
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response', 'value': [1, 2, 3]}]
    assert response_json['responses'][0]['text'] == '1'
    assert response_json['responses'][1]['text'] == '2'
    assert response_json['responses'][2]['text'] == '3'


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
                                    'latest_message': {'intent_ranking': [{'name': 'pyscript_action'}],
                                                       'text': 'get intents'},
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
                                    'latest_message': {'intent_ranking': [{'name': 'pyscript_action'}],
                                                       'text': 'get intents'},
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
                                    'latest_message': {'intent_ranking': [{'name': 'pyscript_action'}],
                                                       'text': 'get intents'},
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
                                    'latest_message': {'intent_ranking': [{'name': 'pyscript_action'}],
                                                       'text': 'get intents'},
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
                                    'latest_message': {'intent_ranking': [{'name': 'pyscript_action'}],
                                                       'text': 'get intents'},
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
    with mock.patch("kairon.shared.utils.Utility.environment", new=mock_environment):
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
                                       'latest_message': {'intent_ranking': [{'name': 'pyscript_action'}],
                                                          'text': 'get intents'},
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
    with mock.patch("kairon.shared.utils.Utility.environment", new=mock_environment):
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
                                    'latest_message': {'intent_ranking': [{'name': 'pyscript_action'}],
                                                       'text': 'get intents'},
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
                                    'latest_message': {'intent_ranking': [{'name': 'pyscript_action'}],
                                                       'text': 'get intents'},
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
    assert log[
               'exception'] == 'Pyscript evaluation failed: {\'success\': False, \'data\': None, \'message\': \'Script execution error: ("Line 2: SyntaxError: invalid syntax at statement: for i in 10",)\', \'error_code\': 422}'


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
        url=http_url + "?" + urlencode({"bot": "5f50fd0a56b698ca10d35d2e", "user": "1011", "tag": "from_bot",
                                        "name": "udit"}),
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
    assert len(result['events']) == 4
    assert len(result['responses']) == 1
    assert result['events'] == [
        {"event": "slot", "timestamp": None, "name": "kairon_action_response",
         "value": "The value of 2 in red is ['red', 'buggy', 'bumpers']"},
        {"event": "slot", "timestamp": None, "name": "http_status_code", "value": 200},
        {"event": "slot", "timestamp": None, "name": "val_d", "value": "['red', 'buggy', 'bumpers']"},
        {"event": "slot", "timestamp": None, "name": "val_d_0", "value": "red"}]
    assert result['responses'][0]['text'] == "The value of 2 in red is ['red', 'buggy', 'bumpers']"
    log = ActionServerLogs.objects(action=action_name).get().to_mongo().to_dict()
    assert isinstance(log['time_elapsed'], float) and log['time_elapsed'] > 0.0
    log.pop('_id')
    log.pop('timestamp')
    assert log["time_elapsed"]
    log.pop('time_elapsed')
    events = log.pop('events')
    for event in events:
        if event.get('time_elapsed') is not None:
            del event['time_elapsed']
    assert events == [{'type': 'slots', 'data': [
        {'name': 'val_d', 'value': '${data.a.b.d}', 'evaluation_type': 'expression', 'slot_value': None},
        {'name': 'val_d_0', 'value': '${data.a.b.d.0}', 'evaluation_type': 'expression', 'slot_value': None}]},
                      {'type': 'response', 'dispatch_bot_response': True, 'dispatch_type': 'text',
                       'data': 'The value of ${data.a.b.3} in ${data.a.b.d.0} is ${data.a.b.d}',
                       'evaluation_type': 'expression',
                       'response': "The value of 2 in red is ['red', 'buggy', 'bumpers']",
                       'bot_response_log': ['evaluation_type: expression',
                                            'expression: The value of ${data.a.b.3} in ${data.a.b.d.0} is ${data.a.b.d}',
                                            "data: {'data': {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}, 'context': {'sender_id': 'default', 'user_message': 'get intents', 'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run', 'chat_log': [], 'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'}, 'latest_message': {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]}, 'kairon_user_msg': None, 'session_started': None, 'bot': '5f50fd0a56b698ca10d35d2e'}, 'http_status_code': 200, 'response_headers': {'Content-Type': 'application/json'}}",
                                            "response: The value of 2 in red is ['red', 'buggy', 'bumpers']"]},
                      {'type': 'api_call',
                       'headers': {'botid': '**********************2e', 'userid': '****', 'tag': '******ot',
                                   'email': '*******************om'}, 'method': 'GET',
                       'url': 'http://localhost:8081/mock',
                       'payload': {'bot': '5f50fd0a56b698ca10d35d2e', 'user': '1011', 'tag': 'from_bot', 'name': 'udit',
                                   'contact': ''},
                       'response': {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}},
                       'status_code': 200, 'response_headers': {'Content-Type': 'application/json'}},
                      {'type': 'params_list',
                       'request_body': {'bot': '5f50fd0a56b698ca10d35d2e', 'user': '1011',
                                        'tag': 'from_bot', 'name': 'udit', 'contact': ''},
                       'request_params': {'bot': '**********************2e', 'user': '1011',
                                          'tag': '******ot', 'name': '****', 'contact': None}},
                      {'type': 'filled_slots', 'data': {'val_d': "['red', 'buggy', 'bumpers']", 'val_d_0': 'red'},
                       'slot_eval_log': ['initiating slot evaluation', 'Slot: val_d', 'evaluation_type: expression',
                                         'expression: ${data.a.b.d}',
                                         "data: {'data': {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}, 'context': {'sender_id': 'default', 'user_message': 'get intents', 'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run', 'chat_log': [], 'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'}, 'latest_message': {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]}, 'kairon_user_msg': None, 'session_started': None, 'bot': '5f50fd0a56b698ca10d35d2e'}, 'http_status_code': 200, 'response_headers': {'Content-Type': 'application/json'}}",
                                         "response: ['red', 'buggy', 'bumpers']", 'Slot: val_d_0',
                                         'evaluation_type: expression', 'expression: ${data.a.b.d.0}',
                                         "data: {'data': {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}, 'context': {'sender_id': 'default', 'user_message': 'get intents', 'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run', 'chat_log': [], 'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'}, 'latest_message': {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]}, 'kairon_user_msg': None, 'session_started': None, 'bot': '5f50fd0a56b698ca10d35d2e'}, 'http_status_code': 200, 'response_headers': {'Content-Type': 'application/json'}}",
                                         'response: red']}]
    assert log == {'type': 'http_action', 'intent': 'test_run', 'action': 'test_http_action_execution',
                   'sender': 'default', 'headers': {}, 'url': 'http://localhost:8081/mock', 'request_method': 'GET',
                   'bot_response': "The value of 2 in red is ['red', 'buggy', 'bumpers']",
                   'bot': '5f50fd0a56b698ca10d35d2e', 'status': 'SUCCESS', 'fail_reason': None,
                   'user_msg': 'get intents', 'http_status_code': 200
                   }


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
        url=http_url + "?" + urlencode({"bot": "5f50fd0a56b698ca10d35d2e", "user": "1011", "tag": "from_bot",
                                        "name": "udit"}),
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
    assert len(result['events']) == 4
    assert len(result['responses']) == 1
    assert result['events'] == [
        {"event": "slot", "timestamp": None, "name": "kairon_action_response",
         "value": {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}},
        {"event": "slot", "timestamp": None, "name": "http_status_code", "value": 200},
        {"event": "slot", "timestamp": None, "name": "val_d", "value": "['red', 'buggy', 'bumpers']"},
        {"event": "slot", "timestamp": None, "name": "val_d_0", "value": "red"}]
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
        url=http_url + "?" + urlencode({"bot": "5f50fd0a56b698ca10d35d2e", "user": "1011", "tag": "from_bot",
                                        "name": "udit"}),
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
    assert len(response_json['events']) == 4
    assert len(response_json['responses']) == 1
    assert not DeepDiff(response_json['events'], [
        {"event": "slot", "timestamp": None, "name": "kairon_action_response",
         "value": 'INVALID {"a":{"b":{"3":2,"43":30,"c":[],"d":["red","buggy","bumpers"]}}}'},
        {"event": "slot", "timestamp": None, "name": "http_status_code", "value": 200},
        {"event": "slot", "timestamp": None, "name": "val_d", "value": "['red', 'buggy', 'bumpers']"},
        {"event": "slot", "timestamp": None, "name": "val_d_0", "value": "red"}], ignore_order=True)
    assert response_json['responses'][0][
               'text'] == 'INVALID {"a":{"b":{"3":2,"43":30,"c":[],"d":["red","buggy","bumpers"]}}}'


@responses.activate
def test_http_action_execution_return_custom_json_with_script_evaluation(aioresponses):
    action_name = "test_http_action_execution_return_custom_json_with_script_evaluation"
    Actions(name=action_name, type=ActionType.http_action.value, bot="5f50fd0a56b698ca10d35d2e", user="user").save()
    HttpActionConfig(
        action_name=action_name,
        response=HttpActionResponse(value="bot_response=data", dispatch=True, evaluation_type="script",
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

    data_obj = {
        "a": 10,
        "b": {
            "name": "Mayank",
            "arr": ['red', 'green', 'hotpink']
        }
    }

    resp_msg = json.dumps(data_obj)
    aioresponses.add(
        method=responses.GET,
        url=http_url + "?" + urlencode({"bot": "5f50fd0a56b698ca10d35d2e", "user": "1011", "tag": "from_bot",
                                        "name": "udit"}),
        body=resp_msg,
        status=200
    )
    responses.add(
        method=responses.POST,
        url=Utility.environment['evaluator']['pyscript']['url'],
        json={"success": True, "data": {'bot_response': data_obj}, 'error_code': 0},
        status=200,
        match=[
            responses.matchers.json_params_matcher(
                {'predefined_objects': {'bot': '5f50fd0a56b698ca10d35d2e', 'chat_log': [],
                                        'data': data_obj, 'intent': 'test_run', 'kairon_user_msg': None,
                                        'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'},
                                        'latest_message': {'intent_ranking': [{'name': 'test_run'}],
                                                           'text': 'get intents'},
                                        'sender_id': 'default', 'session_started': None,
                                        'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'http_status_code': 200,
                                        'response_headers': {'Content-Type': 'application/json'},
                                        'user_message': 'get intents'},
                 'source_code': "bot_response=data"})]
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
    assert len(response_json['events']) == 2
    assert len(response_json['responses']) == 1
    assert response_json['events'] == [{'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
                                        'value': {'a': 10,
                                                  'b': {'name': 'Mayank', 'arr': ['red', 'green', 'hotpink']}}},
                                       {"event": "slot", "timestamp": None, "name": "http_status_code", "value": 200}, ]

    assert response_json['responses'][0]['custom'] == data_obj


@responses.activate
def test_http_action_execution_script_evaluation_with_json_response(aioresponses):
    action_name = "test_http_action_execution_script_evaluation_with_json_response"
    Actions(name=action_name, type=ActionType.http_action.value, bot="5f50fd0a56b698ca10d35d2d", user="user").save()
    HttpActionConfig(
        action_name=action_name,
        response=HttpActionResponse(value="bot_response = data['b']['name']",
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
    data_obj = {
        "a": 10,
        "b": {
            "name": "Mayank",
            "arr": ['red', 'green', 'hotpink']
        }
    }
    resp_msg = json.dumps(data_obj)

    aioresponses.add(
        method=responses.GET,
        url=http_url + "?" + urlencode({"bot": "5f50fd0a56b698ca10d35d2d", "user": "1011",
                                        "tag": "from_bot"}),
        body=resp_msg,
        status=200
    )
    responses.add(
        method=responses.POST,
        url=Utility.environment['evaluator']['pyscript']['url'],
        json={"success": True, "data": {'bot_response': 'Mayank'}, "error_code": 0},
        status=200,
        match=[
            responses.matchers.json_params_matcher(
                {'predefined_objects': {'bot': '5f50fd0a56b698ca10d35d2d', 'chat_log': [],
                                        'data': data_obj, 'intent': 'test_run', 'kairon_user_msg': None,
                                        'key_vault': {},
                                        'latest_message': {'intent_ranking': [{'name': 'test_run'}],
                                                           'text': 'get intents'},
                                        'sender_id': 'default', 'session_started': None,
                                        'slot': {'bot': '5f50fd0a56b698ca10d35d2d'}, 'http_status_code': 200,
                                        'response_headers': {'Content-Type': 'application/json'},
                                        'user_message': 'get intents'},
                 'source_code': "bot_response = data['b']['name']"})]
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
    assert len(response_json['events']) == 2
    assert len(response_json['responses']) == 1
    assert response_json['events'] == [
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response', 'value': 'Mayank'},
        {"event": "slot", "timestamp": None, "name": "http_status_code", "value": 200}]
    assert response_json['responses'][0]['text'] == "Mayank"


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
        url=http_url + "?" + urlencode({"bot": "5f50fd0a56b698ca10d35d2e", "user": "1011", "tag": "from_bot"}),
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
    assert len(response_json['events']) == 4
    assert len(response_json['responses']) == 0
    log = ActionServerLogs.objects(action=action_name).get().to_mongo().to_dict()
    log.pop('_id')
    log.pop('timestamp')
    log.pop('time_elapsed')
    events = log.pop('events')
    for event in events:
        if event.get('time_elapsed') is not None:
            del event['time_elapsed']
    assert events == [{'type': 'slots', 'data': [
        {'name': 'val_d', 'value': '${data.a.b.d}', 'evaluation_type': 'expression', 'slot_value': None},
        {'name': 'val_d_0', 'value': '${data.a.b.d.0}', 'evaluation_type': 'expression', 'slot_value': None}]},
                      {'type': 'response', 'dispatch_bot_response': False, 'dispatch_type': 'text',
                       'data': 'The value of ${data.a.b.3} in ${data.a.b.d.0} is ${data.a.b.d}',
                       'evaluation_type': 'expression',
                       'response': "The value of 2 in red is ['red', 'buggy', 'bumpers']",
                       'bot_response_log': ['evaluation_type: expression',
                                            'expression: The value of ${data.a.b.3} in ${data.a.b.d.0} is ${data.a.b.d}',
                                            "data: {'data': {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}, 'context': {'sender_id': 'default', 'user_message': 'get intents', 'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run', 'chat_log': [], 'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'}, 'latest_message': {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]}, 'kairon_user_msg': None, 'session_started': None, 'bot': '5f50fd0a56b698ca10d35d2e'}, 'http_status_code': 200, 'response_headers': {'Content-Type': 'application/json'}}",
                                            "response: The value of 2 in red is ['red', 'buggy', 'bumpers']"]},
                      {'type': 'api_call',
                       'headers': {'botid': '5f50fd0a56b698ca10d35d2e', 'userid': '****', 'tag': '******ot'},
                       'method': 'GET', 'url': 'http://localhost:8081/mock',
                       'payload': {'bot': '5f50fd0a56b698ca10d35d2e', 'user': '1011', 'tag': 'from_bot'},
                       'response': {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}},
                       'status_code': 200, 'response_headers': {'Content-Type': 'application/json'}},
                      {'type': 'params_list',
                       'request_body': {'bot': '5f50fd0a56b698ca10d35d2e', 'user': '1011',
                                        'tag': 'from_bot'},
                       'request_params': {'bot': '5f50fd0a56b698ca10d35d2e', 'user': '1011',
                                          'tag': '******ot'}},
                      {'type': 'filled_slots', 'data': {'val_d': "['red', 'buggy', 'bumpers']", 'val_d_0': 'red'},
                       'slot_eval_log': ['initiating slot evaluation', 'Slot: val_d', 'evaluation_type: expression',
                                         'expression: ${data.a.b.d}',
                                         "data: {'data': {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}, 'context': {'sender_id': 'default', 'user_message': 'get intents', 'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run', 'chat_log': [], 'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'}, 'latest_message': {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]}, 'kairon_user_msg': None, 'session_started': None, 'bot': '5f50fd0a56b698ca10d35d2e'}, 'http_status_code': 200, 'response_headers': {'Content-Type': 'application/json'}}",
                                         "response: ['red', 'buggy', 'bumpers']", 'Slot: val_d_0',
                                         'evaluation_type: expression', 'expression: ${data.a.b.d.0}',
                                         "data: {'data': {'a': {'b': {'3': 2, '43': 30, 'c': [], 'd': ['red', 'buggy', 'bumpers']}}}, 'context': {'sender_id': 'default', 'user_message': 'get intents', 'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run', 'chat_log': [], 'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'}, 'latest_message': {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]}, 'kairon_user_msg': None, 'session_started': None, 'bot': '5f50fd0a56b698ca10d35d2e'}, 'http_status_code': 200, 'response_headers': {'Content-Type': 'application/json'}}",
                                         'response: red']}]
    assert log == {'type': 'http_action', 'intent': 'test_run',
                   'action': 'test_http_action_execution_no_response_dispatch', 'sender': 'default', 'headers': {},
                   'url': 'http://localhost:8081/mock', 'request_method': 'GET',
                   'bot_response': "The value of 2 in red is ['red', 'buggy', 'bumpers']",
                   'bot': '5f50fd0a56b698ca10d35d2e', 'status': 'SUCCESS', 'fail_reason': None,
                   'user_msg': 'get intents', 'http_status_code': 200}


@responses.activate
def test_http_action_execution_script_evaluation(aioresponses):
    action_name = "test_http_action_execution_script_evaluation"
    Actions(name=action_name, type=ActionType.http_action.value, bot="5f50fd0a56b698ca10d35d2e", user="user").save()
    HttpActionConfig(
        action_name=action_name,
        content_type="json",
        response=HttpActionResponse(
            value="bot_response = data['b']['name']",
            dispatch=True, evaluation_type="script", dispatch_type=DispatchType.text.value),
        http_url="http://localhost:8081/mock",
        request_method="GET",
        headers=[HttpActionRequestBody(key="botid", parameter_type="slot", value="bot", encrypt=False),
                 HttpActionRequestBody(key="userid", parameter_type="value", value="1011", encrypt=True),
                 HttpActionRequestBody(key="tag", parameter_type="value", value="from_bot", encrypt=True)],
        bot="5f50fd0a56b698ca10d35d2e",
        user="user"
    ).save()

    http_url = 'http://localhost:8081/mock'

    data_obj = {
        "a": 10,
        "b": {
            "name": "Mayank",
            "arr": ['red', 'green', 'hotpink']
        }
    }

    resp_msg = json.dumps(data_obj)
    aioresponses.get(
        url=f"{http_url}",
        body=resp_msg,
        status=200,
    )
    responses.add(
        method=responses.POST,
        url=Utility.environment['evaluator']['pyscript']['url'],
        json={"success": True, "data": {'bot_response': 'Mayank'}, 'error_code': 0},
        status=200,
        match=[
            responses.matchers.json_params_matcher(
                {'predefined_objects': {'bot': '5f50fd0a56b698ca10d35d2e', 'chat_log': [],
                                        'data': data_obj, 'intent': 'test_run', 'kairon_user_msg': None,
                                        'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'},
                                        'latest_message': {'intent_ranking': [{'name': 'test_run'}],
                                                           'text': 'get intents'},
                                        'sender_id': 'default', 'session_started': None,
                                        'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'http_status_code': 200,
                                        'response_headers': {'Content-Type': 'application/json'},
                                        'user_message': 'get intents'},
                 'source_code': "bot_response = data['b']['name']"})]
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
    assert len(response_json) == 2
    assert len(response_json['events']) == 2
    assert response_json['responses'][0]['text'] == 'Mayank'
    log = ActionServerLogs.objects(action=action_name).get().to_mongo().to_dict()
    log.pop('_id')
    log.pop('timestamp')
    log.pop('time_elapsed')
    events = log.pop('events')
    for event in events:
        if event.get('time_elapsed') is not None:
            del event['time_elapsed']
    assert events == [{'type': 'response', 'dispatch_bot_response': True, 'dispatch_type': 'text',
                       'data': "bot_response = data['b']['name']", 'evaluation_type': 'script', 'response': 'Mayank',
                       'bot_response_log': ['evaluation_type: script', "script: bot_response = data['b']['name']",
                                            "data: {'data': {'a': 10, 'b': {'name': 'Mayank', 'arr': ['red', 'green', 'hotpink']}}, 'context': {'sender_id': 'default', 'user_message': 'get intents', 'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run', 'chat_log': [], 'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'}, 'latest_message': {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]}, 'kairon_user_msg': None, 'session_started': None, 'bot': '5f50fd0a56b698ca10d35d2e'}, 'http_status_code': 200, 'response_headers': {'Content-Type': 'application/json'}}",
                                            'raise_err_on_failure: True']}, {'type': 'api_call', 'headers': {
        'botid': '5f50fd0a56b698ca10d35d2e', 'userid': '****', 'tag': '******ot'}, 'method': 'GET',
                                                                             'url': 'http://localhost:8081/mock',
                                                                             'payload': {}, 'response': {'a': 10, 'b': {
            'name': 'Mayank', 'arr': ['red', 'green', 'hotpink']}}, 'status_code': 200, 'response_headers': {
            'Content-Type': 'application/json'}},
                      {'type': 'params_list', 'request_body': {}, 'request_params': {}},
                      {'type': 'filled_slots', 'data': {}, 'slot_eval_log': ['initiating slot evaluation']}]
    assert log == {'type': 'http_action', 'intent': 'test_run',
                   'action': 'test_http_action_execution_script_evaluation', 'sender': 'default', 'headers': {},
                   'url': 'http://localhost:8081/mock', 'request_method': 'GET', 'bot_response': 'Mayank',
                   'bot': '5f50fd0a56b698ca10d35d2e', 'status': 'SUCCESS', 'fail_reason': None,
                   'user_msg': 'get intents', 'http_status_code': 200}


@responses.activate
def test_http_action_execution_script_evaluation_with_dynamic_params_post(aioresponses):
    action_name = "test_http_action_execution_script_evaluation_with_dynamic_params_post"
    Actions(name=action_name, type=ActionType.http_action.value, bot="5f50fd0a56b698ca10d35d2e", user="user").save()
    HttpActionConfig(
        action_name=action_name,
        content_type="json",
        response=HttpActionResponse(
            value="bot_response = data['b']['name']",
            dispatch=True, evaluation_type="script", dispatch_type=DispatchType.text.value),
        http_url="http://localhost:8081/mock",
        request_method="POST",
        dynamic_params=
        "body = {'sender_id': sender_id, 'user_message': user_message, 'intent': intent}",
        headers=[HttpActionRequestBody(key="botid", parameter_type="slot", value="bot", encrypt=False),
                 HttpActionRequestBody(key="userid", parameter_type="value", value="1011", encrypt=True),
                 HttpActionRequestBody(key="tag", parameter_type="value", value="from_bot", encrypt=True)],
        bot="5f50fd0a56b698ca10d35d2e",
        user="user"
    ).save()
    resp_msg = {
        'body': {
            "sender_id": "default",
            "user_message": "get intents",
            "intent": "test_run"
        }

    }
    http_url = 'http://localhost:8081/mock'
    responses.add(
        method=responses.POST,
        url=Utility.environment['evaluator']['pyscript']['url'],
        json={"success": True, "data": resp_msg, 'error_code': 0},
        status=200,
        match=[
            responses.matchers.json_params_matcher(
                {"predefined_objects": {"bot": "5f50fd0a56b698ca10d35d2e", "chat_log": [],
                                        "intent": "test_run", "kairon_user_msg": None,
                                        "key_vault": {"EMAIL": "uditpandey@digite.com", "FIRSTNAME": "udit"},
                                        "latest_message": {"intent_ranking": [{"name": "test_run"}],
                                                           "text": "get intents"}, "sender_id": "default",
                                        "session_started": None, "slot": {"bot": "5f50fd0a56b698ca10d35d2e"},
                                        "user_message": "get intents"},
                 "source_code": "body = {'sender_id': sender_id, 'user_message': user_message, 'intent': intent}"})],
    )

    data_obj = {
        "a": 10,
        "b": {
            "name": "Mayank",
            "arr": ['red', 'green', 'hotpink']
        }
    }

    resp_msg = json.dumps(data_obj)
    aioresponses.add(
        method=responses.POST,
        url=f"{http_url}",
        body=resp_msg,
        status=200
    )
    responses.add(
        method=responses.POST,
        url=Utility.environment['evaluator']['pyscript']['url'],
        json={"success": True, "data": {'bot_response': 'Mayank'}, 'error_code': 0},
        status=200,
        match=[
            responses.matchers.json_params_matcher(
                {'predefined_objects': {'bot': '5f50fd0a56b698ca10d35d2e', 'chat_log': [],
                                        'data': data_obj, 'intent': 'test_run', 'kairon_user_msg': None,
                                        'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'},
                                        'latest_message': {'intent_ranking': [{'name': 'test_run'}],
                                                           'text': 'get intents'},
                                        'sender_id': 'default', 'session_started': None,
                                        'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'http_status_code': 200,
                                        'response_headers': {'Content-Type': 'application/json'},
                                        'user_message': 'get intents'},
                 'source_code': "bot_response = data['b']['name']"})]
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
    assert len(response_json) == 2
    assert len(response_json['events']) == 2
    assert response_json['responses'][0]['text'] == 'Mayank'
    log = ActionServerLogs.objects(action=action_name).get().to_mongo().to_dict()
    log.pop('_id')
    log.pop('timestamp')
    log.pop('time_elapsed')
    events = log.pop('events')
    for event in events:
        if event.get('time_elapsed') is not None:
            del event['time_elapsed']
    assert events == [{'type': 'response', 'dispatch_bot_response': True, 'dispatch_type': 'text',
                       'data': "bot_response = data['b']['name']", 'evaluation_type': 'script', 'response': 'Mayank',
                       'bot_response_log': ['evaluation_type: script', "script: bot_response = data['b']['name']",
                                            "data: {'data': {'a': 10, 'b': {'name': 'Mayank', 'arr': ['red', 'green', 'hotpink']}}, 'context': {'sender_id': 'default', 'user_message': 'get intents', 'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run', 'chat_log': [], 'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'}, 'latest_message': {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]}, 'kairon_user_msg': None, 'session_started': None, 'bot': '5f50fd0a56b698ca10d35d2e'}, 'http_status_code': 200, 'response_headers': {'Content-Type': 'application/json'}}",
                                            'raise_err_on_failure: True']}, {'type': 'api_call', 'headers': {
        'botid': '5f50fd0a56b698ca10d35d2e', 'userid': '****', 'tag': '******ot'}, 'method': 'POST',
                                                                             'url': 'http://localhost:8081/mock',
                                                                             'payload': {'sender_id': 'default',
                                                                                         'user_message': 'get intents',
                                                                                         'intent': 'test_run'},
                                                                             'response': {'a': 10,
                                                                                          'b': {'name': 'Mayank',
                                                                                                'arr': ['red', 'green',
                                                                                                        'hotpink']}},
                                                                             'status_code': 200, 'response_headers': {
            'Content-Type': 'application/json'}},
                      {'type': 'dynamic_params',
                       'data': "body = {'sender_id': sender_id, 'user_message': user_message, 'intent': intent}",
                       'response': {'sender_id': 'default', 'user_message': 'get intents', 'intent': 'test_run'},
                       'slots': {}, 'request_params': ['evaluation_type: script',
                                                       "script: body = {'sender_id': sender_id, 'user_message': user_message, 'intent': intent}",
                                                       "data: {'sender_id': 'default', 'user_message': 'get intents', 'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run', 'chat_log': [], 'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'}, 'latest_message': {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]}, 'kairon_user_msg': None, 'session_started': None, 'bot': '5f50fd0a56b698ca10d35d2e'}",
                                                       'raise_err_on_failure: True']},
                      {'type': 'filled_slots', 'data': {}, 'slot_eval_log': ['initiating slot evaluation']}]
    assert log == {'type': 'http_action', 'intent': 'test_run',
                   'action': 'test_http_action_execution_script_evaluation_with_dynamic_params_post',
                   'sender': 'default', 'headers': {}, 'url': 'http://localhost:8081/mock', 'request_method': 'POST',
                   'bot_response': 'Mayank', 'bot': '5f50fd0a56b698ca10d35d2e', 'status': 'SUCCESS',
                   'fail_reason': None, 'user_msg': 'get intents', 'http_status_code': 200}


@responses.activate
def test_http_action_execution_script_evaluation_with_dynamic_params(aioresponses):
    action_name = "test_http_action_execution_script_evaluation_with_dynamic_params"
    Actions(name=action_name, type=ActionType.http_action.value, bot="5f50fd0a56b698ca10d35d2e", user="user").save()
    HttpActionConfig(
        action_name=action_name,
        content_type="json",
        response=HttpActionResponse(
            value="bot_response = data['b']['name']",
            dispatch=True, evaluation_type="script", dispatch_type=DispatchType.text.value),
        http_url="http://localhost:8081/mock",
        request_method="GET",
        dynamic_params=
        "body = {'sender_id': sender_id, 'user_message': user_message, 'intent': intent}",
        headers=[HttpActionRequestBody(key="botid", parameter_type="slot", value="bot", encrypt=False),
                 HttpActionRequestBody(key="userid", parameter_type="value", value="1011", encrypt=True),
                 HttpActionRequestBody(key="tag", parameter_type="value", value="from_bot", encrypt=True)],
        bot="5f50fd0a56b698ca10d35d2e",
        user="user"
    ).save()
    resp_msg = {
        'body': {
            "sender_id": "default",
            "user_message": "get intents",
            "intent": "test_run"
        }

    }
    http_url = 'http://localhost:8081/mock'
    responses.add(
        method=responses.POST,
        url=Utility.environment['evaluator']['pyscript']['url'],
        json={"success": True, "data": resp_msg, 'error_code': 0},
        status=200,
        match=[
            responses.matchers.json_params_matcher(
                {"predefined_objects": {"bot": "5f50fd0a56b698ca10d35d2e", "chat_log": [],
                                        "intent": "test_run", "kairon_user_msg": None,
                                        "key_vault": {"EMAIL": "uditpandey@digite.com", "FIRSTNAME": "udit"},
                                        "latest_message": {"intent_ranking": [{"name": "test_run"}],
                                                           "text": "get intents"}, "sender_id": "default",
                                        "session_started": None, "slot": {"bot": "5f50fd0a56b698ca10d35d2e"},
                                        "user_message": "get intents"},
                 "source_code": "body = {'sender_id': sender_id, 'user_message': user_message, 'intent': intent}"})],
    )

    data_obj = {
        "a": 10,
        "b": {
            "name": "Mayank",
            "arr": ['red', 'green', 'hotpink']
        }
    }

    aioresponses.add(
        method=responses.GET,
        url=f"{http_url}?sender_id=default&user_message=get%20intents&intent=test_run",
        body=json.dumps(data_obj),
        status=200
    )
    responses.add(
        method=responses.POST,
        url=Utility.environment['evaluator']['pyscript']['url'],
        json={"success": True, "data": {'bot_response': 'Mayank'}, 'error_code': 0},
        status=200,
        match=[
            responses.matchers.json_params_matcher(
                {'predefined_objects': {'bot': '5f50fd0a56b698ca10d35d2e', 'chat_log': [],
                                        'data': data_obj, 'intent': 'test_run', 'kairon_user_msg': None,
                                        'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'},
                                        'latest_message': {'intent_ranking': [{'name': 'test_run'}],
                                                           'text': 'get intents'},
                                        'sender_id': 'default', 'session_started': None,
                                        'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'http_status_code': 200,
                                        'response_headers': {'Content-Type': 'application/json'},
                                        'user_message': 'get intents'},
                 'source_code': "bot_response = data['b']['name']"})]
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
    assert len(response_json) == 2
    assert len(response_json['events']) == 2
    assert response_json['responses'][0]['text'] == 'Mayank'
    log = ActionServerLogs.objects(action=action_name).get().to_mongo().to_dict()
    log.pop('_id')
    log.pop('timestamp')
    log.pop('time_elapsed')
    events = log.pop('events')
    for event in events:
        if event.get('time_elapsed') is not None:
            del event['time_elapsed']
    assert events == [{'type': 'response', 'dispatch_bot_response': True, 'dispatch_type': 'text',
                       'data': "bot_response = data['b']['name']", 'evaluation_type': 'script', 'response': 'Mayank',
                       'bot_response_log': ['evaluation_type: script', "script: bot_response = data['b']['name']",
                                            "data: {'data': {'a': 10, 'b': {'name': 'Mayank', 'arr': ['red', 'green', 'hotpink']}}, 'context': {'sender_id': 'default', 'user_message': 'get intents', 'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run', 'chat_log': [], 'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'}, 'latest_message': {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]}, 'kairon_user_msg': None, 'session_started': None, 'bot': '5f50fd0a56b698ca10d35d2e'}, 'http_status_code': 200, 'response_headers': {'Content-Type': 'application/json'}}",
                                            'raise_err_on_failure: True']}, {'type': 'api_call', 'headers': {
        'botid': '5f50fd0a56b698ca10d35d2e', 'userid': '****', 'tag': '******ot'}, 'method': 'GET',
                                                                             'url': 'http://localhost:8081/mock',
                                                                             'payload': {'sender_id': 'default',
                                                                                         'user_message': 'get intents',
                                                                                         'intent': 'test_run'},
                                                                             'response': {'a': 10,
                                                                                          'b': {'name': 'Mayank',
                                                                                                'arr': ['red', 'green',
                                                                                                        'hotpink']}},
                                                                             'status_code': 200, 'response_headers': {
            'Content-Type': 'application/json'}},
                      {'type': 'dynamic_params',
                       'data': "body = {'sender_id': sender_id, 'user_message': user_message, 'intent': intent}",
                       'response': {'sender_id': 'default', 'user_message': 'get intents', 'intent': 'test_run'},
                       'slots': {}, 'request_params': ['evaluation_type: script',
                                                       "script: body = {'sender_id': sender_id, 'user_message': user_message, 'intent': intent}",
                                                       "data: {'sender_id': 'default', 'user_message': 'get intents', 'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run', 'chat_log': [], 'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'}, 'latest_message': {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]}, 'kairon_user_msg': None, 'session_started': None, 'bot': '5f50fd0a56b698ca10d35d2e'}",
                                                       'raise_err_on_failure: True']},
                      {'type': 'filled_slots', 'data': {}, 'slot_eval_log': ['initiating slot evaluation']}]
    assert log == {'type': 'http_action', 'intent': 'test_run',
                   'action': 'test_http_action_execution_script_evaluation_with_dynamic_params', 'sender': 'default',
                   'headers': {}, 'url': 'http://localhost:8081/mock', 'request_method': 'GET',
                   'bot_response': 'Mayank', 'bot': '5f50fd0a56b698ca10d35d2e', 'status': 'SUCCESS',
                   'fail_reason': None, 'user_msg': 'get intents', 'http_status_code': 200}


@responses.activate
def test_http_action_execution_script_evaluation_with_dynamic_params_returns_custom_json(aioresponses):
    action_name = "test_http_action_execution_script_evaluation_with_dynamic_params_returns_custom_json"
    Actions(name=action_name, type=ActionType.http_action.value, bot="5f50fd0a56b698ca10d35d2e", user="user").save()
    HttpActionConfig(
        action_name=action_name,
        content_type="json",
        response=HttpActionResponse(
            value="bot_response = data",
            dispatch=True, evaluation_type="script", dispatch_type=DispatchType.json.value),
        http_url="http://localhost:8081/mock",
        request_method="GET",
        dynamic_params=
        "body = {'sender_id': sender_id, 'user_message': user_message, 'intent': intent}",
        headers=[HttpActionRequestBody(key="botid", parameter_type="slot", value="bot", encrypt=False),
                 HttpActionRequestBody(key="userid", parameter_type="value", value="1011", encrypt=True),
                 HttpActionRequestBody(key="tag", parameter_type="value", value="from_bot", encrypt=True)],
        bot="5f50fd0a56b698ca10d35d2e",
        user="user"
    ).save()
    resp_msg = {
        'body': {
            "sender_id": "default",
            "user_message": "get intents",
            "intent": "test_run"
        }

    }
    http_url = 'http://localhost:8081/mock'
    responses.add(
        method=responses.POST,
        url=Utility.environment['evaluator']['pyscript']['url'],
        json={"success": True, "data": resp_msg, 'error_code': 0},
        status=200,
        match=[
            responses.matchers.json_params_matcher(
                {"predefined_objects": {"bot": "5f50fd0a56b698ca10d35d2e", "chat_log": [],
                                        "intent": "test_run", "kairon_user_msg": None,
                                        "key_vault": {"EMAIL": "uditpandey@digite.com", "FIRSTNAME": "udit"},
                                        "latest_message": {"intent_ranking": [{"name": "test_run"}],
                                                           "text": "get intents"}, "sender_id": "default",
                                        "session_started": None, "slot": {"bot": "5f50fd0a56b698ca10d35d2e"},
                                        "user_message": "get intents"},
                 "source_code": "body = {'sender_id': sender_id, 'user_message': user_message, 'intent': intent}"})],
    )

    data_obj = {
        "a": 10,
        "b": {
            "name": "Mayank",
            "arr": ['red', 'green', 'hotpink']
        }
    }

    resp_msg = json.dumps(data_obj)
    aioresponses.add(
        method=responses.GET,
        url=http_url + "?" + urlencode({"sender_id": "default", "user_message": "get intents", "intent": "test_run"}),
        body=resp_msg,
        status=200
    )
    responses.add(
        method=responses.POST,
        url=Utility.environment['evaluator']['pyscript']['url'],
        json={"success": True, "data": {'bot_response': data_obj}, 'error_code': 0},
        status=200,
        match=[
            responses.matchers.json_params_matcher(
                {'predefined_objects': {'bot': '5f50fd0a56b698ca10d35d2e', 'chat_log': [],
                                        'data': data_obj, 'intent': 'test_run', 'kairon_user_msg': None,
                                        'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'},
                                        'latest_message': {'intent_ranking': [{'name': 'test_run'}],
                                                           'text': 'get intents'},
                                        'sender_id': 'default', 'session_started': None,
                                        'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'http_status_code': 200,
                                        'response_headers': {'Content-Type': 'application/json'},
                                        'user_message': 'get intents'},
                 'source_code': "bot_response = data"})]
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
    assert len(response_json) == 2
    assert len(response_json['events']) == 2
    assert response_json['responses'][0]['custom'] == data_obj
    log = ActionServerLogs.objects(action=action_name).get().to_mongo().to_dict()
    log.pop('_id')
    log.pop('timestamp')
    log.pop('time_elapsed')
    events = log.pop('events')
    for event in events:
        if event.get('time_elapsed') is not None:
            del event['time_elapsed']
    assert events == [
        {'type': 'response', 'dispatch_bot_response': True, 'dispatch_type': 'json', 'data': 'bot_response = data',
         'evaluation_type': 'script',
         'response': {'a': 10, 'b': {'name': 'Mayank', 'arr': ['red', 'green', 'hotpink']}},
         'bot_response_log': ['evaluation_type: script', 'script: bot_response = data',
                              "data: {'data': {'a': 10, 'b': {'name': 'Mayank', 'arr': ['red', 'green', 'hotpink']}}, 'context': {'sender_id': 'default', 'user_message': 'get intents', 'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run', 'chat_log': [], 'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'}, 'latest_message': {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]}, 'kairon_user_msg': None, 'session_started': None, 'bot': '5f50fd0a56b698ca10d35d2e'}, 'http_status_code': 200, 'response_headers': {'Content-Type': 'application/json'}}",
                              'raise_err_on_failure: True']},
        {'type': 'api_call', 'headers': {'botid': '5f50fd0a56b698ca10d35d2e', 'userid': '****', 'tag': '******ot'},
         'method': 'GET', 'url': 'http://localhost:8081/mock',
         'payload': {'sender_id': 'default', 'user_message': 'get intents', 'intent': 'test_run'},
         'response': {'a': 10, 'b': {'name': 'Mayank', 'arr': ['red', 'green', 'hotpink']}}, 'status_code': 200,
         'response_headers': {'Content-Type': 'application/json'}},
        {'type': 'dynamic_params',
         'data': "body = {'sender_id': sender_id, 'user_message': user_message, 'intent': intent}",
         'response': {'sender_id': 'default', 'user_message': 'get intents', 'intent': 'test_run'}, 'slots': {},
         'request_params': ['evaluation_type: script',
                            "script: body = {'sender_id': sender_id, 'user_message': user_message, 'intent': intent}",
                            "data: {'sender_id': 'default', 'user_message': 'get intents', 'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run', 'chat_log': [], 'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'}, 'latest_message': {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]}, 'kairon_user_msg': None, 'session_started': None, 'bot': '5f50fd0a56b698ca10d35d2e'}",
                            'raise_err_on_failure: True']},
        {'type': 'filled_slots', 'data': {}, 'slot_eval_log': ['initiating slot evaluation']}]
    assert log == {'type': 'http_action', 'intent': 'test_run',
                   'action': 'test_http_action_execution_script_evaluation_with_dynamic_params_returns_custom_json',
                   'sender': 'default', 'headers': {}, 'url': 'http://localhost:8081/mock', 'request_method': 'GET',
                   'bot_response': "{'a': 10, 'b': {'name': 'Mayank', 'arr': ['red', 'green', 'hotpink']}}",
                   'bot': '5f50fd0a56b698ca10d35d2e', 'status': 'SUCCESS', 'fail_reason': None,
                   'user_msg': 'get intents', 'http_status_code': 200}


@responses.activate
def test_http_action_execution_script_evaluation_with_dynamic_params_no_response_dispatch(aioresponses):
    action_name = "test_http_action_execution_script_evaluation_with_dynamic_params_no_response_dispatch"
    Actions(name=action_name, type=ActionType.http_action.value, bot="5f50fd0a56b698ca10d35d2e", user="user").save()
    HttpActionConfig(
        action_name=action_name,
        content_type="json",
        response=HttpActionResponse(
            value="bot_response = data['b']['name']",
            dispatch=False, evaluation_type="script", dispatch_type=DispatchType.text.value),
        http_url="http://localhost:8081/mock",
        request_method="GET",
        dynamic_params=
        "body = {'sender_id': sender_id, 'user_message': user_message, 'intent': intent}",
        headers=[HttpActionRequestBody(key="botid", parameter_type="slot", value="bot", encrypt=False),
                 HttpActionRequestBody(key="userid", parameter_type="value", value="1011", encrypt=True),
                 HttpActionRequestBody(key="tag", parameter_type="value", value="from_bot", encrypt=True)],
        bot="5f50fd0a56b698ca10d35d2e",
        user="user"
    ).save()
    resp_msg = {
        'body': {
            "sender_id": "default",
            "user_message": "get intents",
            "intent": "test_run"
        }

    }
    http_url = 'http://localhost:8081/mock'
    responses.add(
        method=responses.POST,
        url=Utility.environment['evaluator']['pyscript']['url'],
        json={"success": True, "data": resp_msg, 'error_code': 0},
        status=200,
        match=[
            responses.matchers.json_params_matcher(
                {"predefined_objects": {"bot": "5f50fd0a56b698ca10d35d2e", "chat_log": [],
                                        "intent": "test_run", "kairon_user_msg": None,
                                        "key_vault": {"EMAIL": "uditpandey@digite.com", "FIRSTNAME": "udit"},
                                        "latest_message": {"intent_ranking": [{"name": "test_run"}],
                                                           "text": "get intents"}, "sender_id": "default",
                                        "session_started": None, "slot": {"bot": "5f50fd0a56b698ca10d35d2e"},
                                        "user_message": "get intents"},
                 "source_code": "body = {'sender_id': sender_id, 'user_message': user_message, 'intent': intent}"})],
    )

    data_obj = {
        "a": 10,
        "b": {
            "name": "Mayank",
            "arr": ['red', 'green', 'hotpink']
        }
    }

    resp_msg = json.dumps(data_obj)
    aioresponses.add(
        method=responses.GET,
        url=http_url + "?" + urlencode({"sender_id": "default", "user_message": "get intents", "intent": "test_run"}),
        body=resp_msg,
        status=200
    )
    responses.add(
        method=responses.POST,
        url=Utility.environment['evaluator']['pyscript']['url'],
        json={"success": True, "data": {'bot_response': 'Mayank'}, 'error_code': 0},
        status=200,
        match=[
            responses.matchers.json_params_matcher(
                {'predefined_objects': {'bot': '5f50fd0a56b698ca10d35d2e', 'chat_log': [],
                                        'data': data_obj, 'intent': 'test_run', 'kairon_user_msg': None,
                                        'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'},
                                        'latest_message': {'intent_ranking': [{'name': 'test_run'}],
                                                           'text': 'get intents'},
                                        'sender_id': 'default', 'session_started': None,
                                        'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'http_status_code': 200,
                                        'response_headers': {'Content-Type': 'application/json'},
                                        'user_message': 'get intents'},
                 'source_code': "bot_response = data['b']['name']"})]
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
    assert len(response_json) == 2
    assert len(response_json['events']) == 2
    assert response_json['responses'] == []
    log = ActionServerLogs.objects(action=action_name).get().to_mongo().to_dict()
    log.pop('_id')
    log.pop('timestamp')
    log.pop('time_elapsed')
    events = log.pop('events')
    for event in events:
        if event.get('time_elapsed') is not None:
            del event['time_elapsed']
    assert events == [{'type': 'response', 'dispatch_bot_response': False, 'dispatch_type': 'text',
                       'data': "bot_response = data['b']['name']", 'evaluation_type': 'script', 'response': 'Mayank',
                       'bot_response_log': ['evaluation_type: script', "script: bot_response = data['b']['name']",
                                            "data: {'data': {'a': 10, 'b': {'name': 'Mayank', 'arr': ['red', 'green', 'hotpink']}}, 'context': {'sender_id': 'default', 'user_message': 'get intents', 'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run', 'chat_log': [], 'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'}, 'latest_message': {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]}, 'kairon_user_msg': None, 'session_started': None, 'bot': '5f50fd0a56b698ca10d35d2e'}, 'http_status_code': 200, 'response_headers': {'Content-Type': 'application/json'}}",
                                            'raise_err_on_failure: True']}, {'type': 'api_call', 'headers': {
        'botid': '5f50fd0a56b698ca10d35d2e', 'userid': '****', 'tag': '******ot'}, 'method': 'GET',
                                                                             'url': 'http://localhost:8081/mock',
                                                                             'payload': {'sender_id': 'default',
                                                                                         'user_message': 'get intents',
                                                                                         'intent': 'test_run'},
                                                                             'response': {'a': 10,
                                                                                          'b': {'name': 'Mayank',
                                                                                                'arr': ['red', 'green',
                                                                                                        'hotpink']}},
                                                                             'status_code': 200, 'response_headers': {
            'Content-Type': 'application/json'}},
                      {'type': 'dynamic_params',
                       'data': "body = {'sender_id': sender_id, 'user_message': user_message, 'intent': intent}",
                       'response': {'sender_id': 'default', 'user_message': 'get intents', 'intent': 'test_run'},
                       'slots': {}, 'request_params': ['evaluation_type: script',
                                                       "script: body = {'sender_id': sender_id, 'user_message': user_message, 'intent': intent}",
                                                       "data: {'sender_id': 'default', 'user_message': 'get intents', 'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run', 'chat_log': [], 'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'}, 'latest_message': {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]}, 'kairon_user_msg': None, 'session_started': None, 'bot': '5f50fd0a56b698ca10d35d2e'}",
                                                       'raise_err_on_failure: True']},
                      {'type': 'filled_slots', 'data': {}, 'slot_eval_log': ['initiating slot evaluation']}]
    assert log == {'type': 'http_action', 'intent': 'test_run',
                   'action': 'test_http_action_execution_script_evaluation_with_dynamic_params_no_response_dispatch',
                   'sender': 'default', 'headers': {}, 'url': 'http://localhost:8081/mock', 'request_method': 'GET',
                   'bot_response': 'Mayank', 'bot': '5f50fd0a56b698ca10d35d2e', 'status': 'SUCCESS',
                   'fail_reason': None, 'user_msg': 'get intents', 'http_status_code': 200}


@responses.activate
def test_http_action_execution_script_evaluation_failure_with_dynamic_params_no_response_dispatch(aioresponses):
    action_name = "test_http_action_execution_script_evaluation_with_dynamic_params_no_response_dispatch"
    Actions(name=action_name, type=ActionType.http_action.value, bot="5f50fd0a56b698ca10d35d2e", user="user").save()
    HttpActionConfig(
        action_name=action_name,
        content_type="json",
        response=HttpActionResponse(
            value="bot_response = data['b']['name']asdf",
            dispatch=False, evaluation_type="script", dispatch_type=DispatchType.text.value),
        http_url="http://localhost:8081/mock",
        request_method="GET",
        dynamic_params=
        "body = {'sender_id': sender_id, 'user_message': user_message, 'intent': intent}",
        headers=[HttpActionRequestBody(key="botid", parameter_type="slot", value="bot", encrypt=False),
                 HttpActionRequestBody(key="userid", parameter_type="value", value="1011", encrypt=True),
                 HttpActionRequestBody(key="tag", parameter_type="value", value="from_bot", encrypt=True)],
        bot="5f50fd0a56b698ca10d35d2e",
        user="user"
    ).save()
    resp_msg = {
        'body': {
            "sender_id": "default",
            "user_message": "get intents",
            "intent": "test_run"
        }

    }
    http_url = 'http://localhost:8081/mock'
    responses.add(
        method=responses.POST,
        url=Utility.environment['evaluator']['pyscript']['url'],
        json={"success": True, "data": resp_msg, 'error_code': 0},
        status=200,
        match=[
            responses.matchers.json_params_matcher(
                {"predefined_objects": {"bot": "5f50fd0a56b698ca10d35d2e", "chat_log": [],
                                        "intent": "test_run", "kairon_user_msg": None,
                                        "key_vault": {"EMAIL": "uditpandey@digite.com", "FIRSTNAME": "udit"},
                                        "latest_message": {"intent_ranking": [{"name": "test_run"}],
                                                           "text": "get intents"}, "sender_id": "default",
                                        "session_started": None, "slot": {"bot": "5f50fd0a56b698ca10d35d2e"},
                                        "user_message": "get intents"},
                 "source_code": "body = {'sender_id': sender_id, 'user_message': user_message, 'intent': intent}"})],
    )

    data_obj = {
        "a": 10,
        "b": {
            "name": "Mayank",
            "arr": ['red', 'green', 'hotpink']
        }
    }

    resp_msg = json.dumps(data_obj)
    aioresponses.add(
        method=responses.GET,
        url=http_url + "?" + urlencode({"sender_id": "default", "user_message": "get intents", "intent": "test_run"}),
        body=resp_msg,
        status=200
    )
    responses.add(
        method=responses.POST,
        url=Utility.environment['evaluator']['pyscript']['url'],
        json={"success": True, "data": 'some error'},
        status=200,
        match=[
            responses.matchers.json_params_matcher(
                {'predefined_objects': {'bot': '5f50fd0a56b698ca10d35d2e', 'chat_log': [],
                                        'data': data_obj, 'intent': 'test_run', 'kairon_user_msg': None,
                                        'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'},
                                        'latest_message': {'intent_ranking': [{'name': 'test_run'}],
                                                           'text': 'get intents'},
                                        'sender_id': 'default', 'session_started': None,
                                        'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'status_code': 200,
                                        'user_message': 'get intents'},
                 'source_code': "bot_response = data['b']['name']asdf"})]
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
    assert len(response_json) == 2
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
    assert len(response_json['events']) == 2
    assert response_json['events'] == [{'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
                                        'value': 'I have failed to process your request'},
                                       {"event": "slot", "timestamp": None, "name": "http_status_code",
                                        "value": None}, ]
    assert len(response_json['responses']) == 1
    assert response_json['responses'][0]['text'] == "I have failed to process your request"


@responses.activate
def test_http_action_execution_script_evaluation_with_dynamic_params_and_params_list(aioresponses):
    action_name = "test_http_action_execution_script_evaluation_with_dynamic_params_and_params_list"
    Actions(name=action_name, type=ActionType.http_action.value, bot="5f50fd0a56b698ca10d35d2e", user="user").save()
    HttpActionConfig(
        action_name=action_name,
        content_type="json",
        response=HttpActionResponse(
            value="bot_response = data['b']['name']",
            dispatch=True, evaluation_type="script", dispatch_type=DispatchType.text.value),
        http_url="http://localhost:8081/mock",
        request_method="GET",
        dynamic_params="body = {'sender_id': sender_id, 'user_message': user_message, 'intent': intent}",
        headers=[HttpActionRequestBody(key="botid", parameter_type="slot", value="bot", encrypt=False),
                 HttpActionRequestBody(key="userid", parameter_type="value", value="1011", encrypt=True),
                 HttpActionRequestBody(key="tag", parameter_type="value", value="from_bot", encrypt=True)],
        params_list=[HttpActionRequestBody(key="bot", parameter_type="slot", value="bot", encrypt=False),
                     HttpActionRequestBody(key="user", parameter_type="value", value="1011", encrypt=False),
                     HttpActionRequestBody(key="tag", parameter_type="value", value="from_bot", encrypt=True)],
        bot="5f50fd0a56b698ca10d35d2e",
        user="user"
    ).save()
    resp_msg = {
        'body': {
            "sender_id": "default",
            "user_message": "get intents",
            "intent": "test_run"
        }

    }
    http_url = 'http://localhost:8081/mock'
    responses.add(
        method=responses.POST,
        url=Utility.environment['evaluator']['pyscript']['url'],
        json={"success": True, "data": resp_msg, 'error_code': 0},
        status=200,
        match=[
            responses.matchers.json_params_matcher(
                {"predefined_objects": {"bot": "5f50fd0a56b698ca10d35d2e", "chat_log": [],
                                        "intent": "test_run", "kairon_user_msg": None,
                                        "key_vault": {"EMAIL": "uditpandey@digite.com", "FIRSTNAME": "udit"},
                                        "latest_message": {"intent_ranking": [{"name": "test_run"}],
                                                           "text": "get intents"}, "sender_id": "default",
                                        "session_started": None, "slot": {"bot": "5f50fd0a56b698ca10d35d2e"},
                                        "user_message": "get intents"},
                 "source_code": "body = {'sender_id': sender_id, 'user_message': user_message, 'intent': intent}"})],
    )

    data_obj = {
        "a": 10,
        "b": {
            "name": "Mayank",
            "arr": ['red', 'green', 'hotpink']
        }
    }

    resp_msg = json.dumps(data_obj)
    aioresponses.add(
        method=responses.GET,
        url=http_url + "?intent=test_run&sender_id=default&user_message=get+intents",
        body=resp_msg,
        status=200
    )
    responses.add(
        method=responses.POST,
        url=Utility.environment['evaluator']['pyscript']['url'],
        json={"success": True, "data": {'bot_response': 'Mayank'}, 'error_code': 0},
        status=200,
        match=[
            responses.matchers.json_params_matcher(
                {'predefined_objects': {'bot': '5f50fd0a56b698ca10d35d2e', 'chat_log': [],
                                        'data': data_obj, 'intent': 'test_run', 'kairon_user_msg': None,
                                        'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'},
                                        'latest_message': {'intent_ranking': [{'name': 'test_run'}],
                                                           'text': 'get intents'},
                                        'sender_id': 'default', 'session_started': None,
                                        'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'http_status_code': 200,
                                        'response_headers': {'Content-Type': 'application/json'},
                                        'user_message': 'get intents'},
                 'source_code': "bot_response = data['b']['name']"})]
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
    assert len(response_json) == 2
    assert len(response_json['events']) == 2
    assert response_json['responses'][0]['text'] == 'Mayank'
    log = ActionServerLogs.objects(action=action_name).get().to_mongo().to_dict()
    log.pop('_id')
    log.pop('timestamp')
    log.pop('time_elapsed')
    events = log.pop('events')
    for event in events:
        if event.get('time_elapsed') is not None:
            del event['time_elapsed']
    assert events == [{'type': 'response', 'dispatch_bot_response': True, 'dispatch_type': 'text',
                       'data': "bot_response = data['b']['name']", 'evaluation_type': 'script', 'response': 'Mayank',
                       'bot_response_log': ['evaluation_type: script', "script: bot_response = data['b']['name']",
                                            "data: {'data': {'a': 10, 'b': {'name': 'Mayank', 'arr': ['red', 'green', 'hotpink']}}, 'context': {'sender_id': 'default', 'user_message': 'get intents', 'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run', 'chat_log': [], 'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'}, 'latest_message': {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]}, 'kairon_user_msg': None, 'session_started': None, 'bot': '5f50fd0a56b698ca10d35d2e'}, 'http_status_code': 200, 'response_headers': {'Content-Type': 'application/json'}}",
                                            'raise_err_on_failure: True']}, {'type': 'api_call', 'headers': {
        'botid': '5f50fd0a56b698ca10d35d2e', 'userid': '****', 'tag': '******ot'}, 'method': 'GET',
                                                                             'url': 'http://localhost:8081/mock',
                                                                             'payload': {'sender_id': 'default',
                                                                                         'user_message': 'get intents',
                                                                                         'intent': 'test_run'},
                                                                             'response': {'a': 10,
                                                                                          'b': {'name': 'Mayank',
                                                                                                'arr': ['red', 'green',
                                                                                                        'hotpink']}},
                                                                             'status_code': 200, 'response_headers': {
            'Content-Type': 'application/json'}},
                      {'type': 'dynamic_params',
                       'data': "body = {'sender_id': sender_id, 'user_message': user_message, 'intent': intent}",
                       'response': {'sender_id': 'default', 'user_message': 'get intents', 'intent': 'test_run'},
                       'slots': {}, 'request_params': ['evaluation_type: script',
                                                       "script: body = {'sender_id': sender_id, 'user_message': user_message, 'intent': intent}",
                                                       "data: {'sender_id': 'default', 'user_message': 'get intents', 'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run', 'chat_log': [], 'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'}, 'latest_message': {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]}, 'kairon_user_msg': None, 'session_started': None, 'bot': '5f50fd0a56b698ca10d35d2e'}",
                                                       'raise_err_on_failure: True']},
                      {'type': 'filled_slots', 'data': {}, 'slot_eval_log': ['initiating slot evaluation']}]
    assert not DeepDiff(log, {'type': 'http_action', 'intent': 'test_run',
                              'action': 'test_http_action_execution_script_evaluation_with_dynamic_params_and_params_list',
                              'sender': 'default', 'headers': {}, 'url': 'http://localhost:8081/mock',
                              'request_method': 'GET', 'bot_response': 'Mayank', 'bot': '5f50fd0a56b698ca10d35d2e',
                              'status': 'SUCCESS', 'fail_reason': None, 'user_msg': 'get intents',
                              'http_status_code': 200}, ignore_order=True)


@responses.activate
def test_http_action_execution_script_evaluation_failure_no_dispatch(aioresponses):
    action_name = "test_http_action_execution_script_evaluation_failure_no_dispatch"
    Actions(name=action_name, type=ActionType.http_action.value, bot="5f50fd0a56b698ca10d35d2d", user="user").save()
    HttpActionConfig(
        action_name=action_name,
        response=HttpActionResponse(value="bot_response = data['b']['name']asdf",
                                    dispatch=False, evaluation_type="script", dispatch_type=DispatchType.text.value),
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
    data_obj = {
        "a": 10,
        "b": {
            "name": "Mayank",
            "arr": ['red', 'green', 'hotpink']
        }
    }
    resp_msg = json.dumps(data_obj)

    aioresponses.add(
        method=responses.GET,
        url=http_url + "?bot=5f50fd0a56b698ca10d35d2d&tag=from_bot&user=1011",
        body=resp_msg,
        status=200
    )
    responses.add(
        method=responses.POST,
        url=Utility.environment['evaluator']['pyscript']['url'],
        json={"success": True, "data": "error", },
        status=200,
        match=[
            responses.matchers.json_params_matcher(
                {'predefined_objects': {'bot': '5f50fd0a56b698ca10d35d2d', 'chat_log': [],
                                        'data': data_obj, 'intent': 'test_run', 'kairon_user_msg': None,
                                        'key_vault': {},
                                        'latest_message': {'intent_ranking': [{'name': 'test_run'}],
                                                           'text': 'get intents'},
                                        'sender_id': 'default', 'session_started': None,
                                        'slot': {'bot': '5f50fd0a56b698ca10d35d2d'}, 'status_code': 200,
                                        'user_message': 'get intents'},
                 'source_code': "bot_response = data['b']['name']asdf"})]
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
    assert len(response_json['events']) == 2
    assert response_json['events'] == [{'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
                                        'value': 'I have failed to process your request'},
                                       {"event": "slot", "timestamp": None, "name": "http_status_code", "value": 200}, ]
    assert response_json['responses'] == []


@responses.activate
def test_http_action_execution_script_evaluation_failure_and_dispatch(aioresponses):
    action_name = "test_http_action_execution_script_evaluation_failure_and_dispatch"
    Actions(name=action_name, type=ActionType.http_action.value, bot="5f50fd0a56b698ca10d35d2d", user="user").save()
    HttpActionConfig(
        action_name=action_name,
        response=HttpActionResponse(value="bot_response = data['b']['name']asdf",
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
    data_obj = {
        "a": 10,
        "b": {
            "name": "Mayank",
            "arr": ['red', 'green', 'hotpink']
        }
    }
    resp_msg = json.dumps(data_obj)

    aioresponses.add(
        method=responses.GET,
        url=http_url + "?bot=5f50fd0a56b698ca10d35d2d&tag=from_bot&user=1011",
        body=resp_msg,
        status=200,
    )
    responses.add(
        method=responses.POST,
        url=Utility.environment['evaluator']['pyscript']['url'],
        json={"success": True, "data": "error", },
        status=200,
        match=[
            responses.matchers.json_params_matcher(
                {'predefined_objects': {'bot': '5f50fd0a56b698ca10d35d2d', 'chat_log': [],
                                        'data': data_obj, 'intent': 'test_run', 'kairon_user_msg': None,
                                        'key_vault': {},
                                        'latest_message': {'intent_ranking': [{'name': 'test_run'}],
                                                           'text': 'get intents'},
                                        'sender_id': 'default', 'session_started': None,
                                        'slot': {'bot': '5f50fd0a56b698ca10d35d2d'}, 'status_code': 200,
                                        'user_message': 'get intents'},
                 'source_code': "bot_response = data['b']['name']asdf"})]
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
    assert len(response_json['events']) == 2
    assert len(response_json['responses']) == 1
    assert response_json['events'] == [{'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
                                        'value': 'I have failed to process your request'},
                                       {"event": "slot", "timestamp": None, "name": "http_status_code", "value": 200}, ]
    assert response_json['responses'][0]['text'] == "I have failed to process your request"


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
    assert len(response_json['events']) == 2
    assert len(response_json['responses']) == 1
    assert response_json['events'] == [
        {"event": "slot", "timestamp": None, "name": "kairon_action_response",
         "value": "I have failed to process your request"},
        {"event": "slot", "timestamp": None, "name": "http_status_code", "value": 200}, ]
    assert response_json['responses'][0]['text'] == "I have failed to process your request"


@mock.patch("kairon.shared.actions.utils.ActionUtility.get_action")
@mock.patch("kairon.actions.definitions.http.ActionHTTP.retrieve_config")
@mock.patch("kairon.shared.rest_client.AioRestClient._AioRestClient__trigger", autospec=True)
def test_http_action_failed_execution(mock_trigger_request, mock_action_config, mock_action):
    action_name = "test_run_with_get"
    action = Actions(name=action_name, type=ActionType.http_action.value, bot="5f50fd0a56b698ca10d35d2e",
                     user="user")
    action_config = HttpActionConfig(
        action_name=action_name,
        response=HttpActionResponse(value="The value of ${a.b.3} in ${a.b.d.0} is ${a.b.d}"),
        http_url="http://localhost:8800/mock",
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
    assert len(response_json['events']) == 2
    assert len(response_json['responses']) == 1
    assert response_json['responses'][0]['text'] == "I have failed to process your request"
    log = ActionServerLogs.objects(action=action_name).get().to_mongo().to_dict()
    log.pop('_id')
    log.pop('timestamp')
    assert log["exception"].startswith("Got non-200 status code:408")
    log.pop('exception')
    events = log.pop('events')
    for event in events:
        if event.get('time_elapsed') is not None:
            del event['time_elapsed']
    print(event)
    assert events == [{'type': 'response', 'dispatch_bot_response': True, 'dispatch_type': 'text',
                       'data': 'The value of ${a.b.3} in ${a.b.d.0} is ${a.b.d}', 'evaluation_type': 'expression',
                       'exception': 'I have failed to process your request'},
                      {'type': 'api_call', 'headers': {}, 'method': 'GET', 'url': 'http://localhost:8800/mock',
                       'payload': {}, 'response': None, 'status_code': 408, 'response_headers': None,
                       'exception': "Got non-200 status code:408 http_response:{'data': None, 'context': {'sender_id': 'default', 'user_message': 'get intents', 'slot': {'bot': '5f50fd0a56b698ca10d35d2e'}, 'intent': 'test_run', 'chat_log': [], 'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'}, 'latest_message': {'text': 'get intents', 'intent_ranking': [{'name': 'test_run'}]}, 'kairon_user_msg': None, 'session_started': None, 'bot': '5f50fd0a56b698ca10d35d2e'}, 'http_status_code': 408, 'response_headers': None}"},
                      {'type': 'params_list', 'request_body': {}, 'request_params': {}}, {'type': 'filled_slots'}]
    print(log)
    assert log == {'type': 'http_action', 'intent': 'test_run', 'action': 'test_run_with_get', 'sender': 'default',
                   'headers': {}, 'url': 'http://localhost:8800/mock', 'request_method': 'GET',
                   'bot_response': 'I have failed to process your request', 'bot': '5f50fd0a56b698ca10d35d2e',
                   'status': 'FAILURE', 'fail_reason': 'Got non-200 status code:408 http_response:None',
                   'user_msg': 'get intents', 'time_elapsed': 0, 'http_status_code': 408}


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
def test_vectordb_action_execution_payload_search_from_slot():
    responses.add_passthru("https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken")
    action_name = "test_vectordb_action_execution_payload_search_from_slot"
    bot = '5f50md0a56b698ca10d35e2e'
    Actions(name=action_name, type=ActionType.database_action.value, bot=bot,
            user="user").save()
    payload = {"filter": {
        "should": [{"key": "city", "match": {"value": "London"}}, {"key": "color", "match": {"value": "red"}}]}}
    DatabaseAction(
        name=action_name,
        collection='test_vectordb_action_execution_payload_search_from_slot',
        payload=[DbQuery(query_type=DbActionOperationType.payload_search.value,
                         type=DbQueryValueType.from_slot.value,
                         value="search")],
        response=HttpActionResponse(value="The value of ${data.0.city} with color ${data.0.color} is ${data.0.id}"),
        set_slots=[SetSlotsFromResponse(name="city_value", value="${data.0.id}")],
        bot=bot,
        user="user"
    ).save()
    BotSettings(llm_settings=LLMSettings(enable_faq=True), bot=bot, user="user").save()
    llm_secret = LLMSecret(
        llm_type="openai",
        api_key="key_value",
        models=["model1", "model2"],
        api_base_url="https://api.example.com",
        bot=bot,
        user="user"
    )
    llm_secret.save()

    http_url = f'http://localhost:6333/collections/{bot}_test_vectordb_action_execution_payload_search_from_slot_faq_embd/points/query'
    resp_msg = json.dumps(
        [{"id": 2, "city": "London", "color": "red"}]
    )
    json_params_matcher = payload.copy()
    json_params_matcher['with_payload'] = True
    json_params_matcher['limit'] = 10
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
            "slots": {"bot": bot, "search": payload},
            "latest_message": {'text': "Hi", 'intent_ranking': [{'name': 'user_story'}],
                               "entities": []},
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
    assert response.status_code == 200
    assert len(response_json['events']) == 2
    assert len(response_json['responses']) == 1
    assert response_json['events'] == [
        {'event': 'slot', 'timestamp': None, 'name': 'city_value', 'value': '2'},
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
         'value': 'The value of London with color red is 2'}]
    assert response_json['responses'][0]['text'] == "The value of London with color red is 2"
    log = ActionServerLogs.objects(action=action_name, bot=bot).get().to_mongo().to_dict()
    log.pop('_id')
    log.pop('timestamp')


@responses.activate
def test_vectordb_action_execution_payload_search_from_user_message():
    responses.add_passthru("https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken")
    action_name = "test_vectordb_action_execution_payload_search_from_user_message"
    Actions(name=action_name, type=ActionType.database_action.value, bot="5f50md0a56b698ca10d35d2e",
            user="user").save()
    payload = {"filter": {
        "should": [{"key": "city", "match": {"value": "London"}}, {"key": "color", "match": {"value": "red"}}]}}
    payload_body = json.dumps(payload)
    DatabaseAction(
        name=action_name,
        collection='test_vectordb_action_execution_payload_search_from_user_message',
        payload=[DbQuery(query_type=DbActionOperationType.payload_search.value,
                         type=DbQueryValueType.from_user_message.value)],
        response=HttpActionResponse(value="The value of ${data.0.city} with color ${data.0.color} is ${data.0.id}"),
        set_slots=[SetSlotsFromResponse(name="city_value", value="${data.0.id}")],
        bot="5f50md0a56b698ca10d35d2e",
        user="user"
    ).save()
    BotSettings(llm_settings=LLMSettings(enable_faq=True), bot="5f50md0a56b698ca10d35d2e", user="user").save()
    llm_secret = LLMSecret(
        llm_type="openai",
        api_key="key_value",
        models=["model1", "model2"],
        api_base_url="https://api.example.com",
        bot="5f50md0a56b698ca10d35d2e",
        user="user"
    )
    llm_secret.save()

    http_url = 'http://localhost:6333/collections/5f50md0a56b698ca10d35d2e_test_vectordb_action_execution_payload_search_from_user_message_faq_embd/points/query'
    resp_msg = json.dumps(
        [{"id": 2, "city": "London", "color": "red"}]
    )
    json_params_matcher = payload.copy()
    json_params_matcher['with_payload'] = True
    json_params_matcher['limit'] = 10
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
            "latest_message": {'text': payload_body, 'intent_ranking': [{'name': 'user_story'}],
                               "entities": [{"value": payload_body, "entity": KAIRON_USER_MSG_ENTITY}]},
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
def test_vectordb_action_execution_payload_search_from_user_message_in_slot():
    responses.add_passthru("https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken")
    action_name = "test_vectordb_action_execution_payload_search_from_user_message_in_slot"
    Actions(name=action_name, type=ActionType.database_action.value, bot="5f50md0a56b698ca10d35d2f",
            user="user").save()
    payload = {"filter": {
        "should": [{"key": "city", "match": {"value": "London"}}, {"key": "color", "match": {"value": "red"}}]}}
    payload_body = json.dumps(payload)
    user_msg = '/user_story{"kairon_user_msg": {"filter": {"should": [{"key": "city", "match": {"value": "London"}}, {"key": "color", "match": {"value": "red"}}]}}}'
    DatabaseAction(
        name=action_name,
        collection='test_vectordb_action_execution_payload_search_from_user_message_in_slot',
        payload=[DbQuery(query_type=DbActionOperationType.payload_search.value,
                         type=DbQueryValueType.from_user_message.value)],
        response=HttpActionResponse(value="The value of ${data.0.city} with color ${data.0.color} is ${data.0.id}"),
        set_slots=[SetSlotsFromResponse(name="city_value", value="${data.0.id}")],
        bot="5f50md0a56b698ca10d35d2f",
        user="user"
    ).save()
    BotSettings(llm_settings=LLMSettings(enable_faq=True), bot="5f50md0a56b698ca10d35d2f", user="user").save()
    llm_secret = LLMSecret(
        llm_type="openai",
        api_key="key_value",
        models=["model1", "model2"],
        api_base_url="https://api.example.com",
        bot="5f50md0a56b698ca10d35d2f",
        user="user"
    )
    llm_secret.save()

    http_url = 'http://localhost:6333/collections/5f50md0a56b698ca10d35d2f_test_vectordb_action_execution_payload_search_from_user_message_in_slot_faq_embd/points/query'
    resp_msg = json.dumps(
        [{"id": 2, "city": "London", "color": "red"}]
    )
    json_params_matcher = payload.copy()
    json_params_matcher.update(
        **{'with_payload': True, 'limit': 10}
    )
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
            "slots": {"bot": "5f50md0a56b698ca10d35d2f"},
            "latest_message": {'text': user_msg, 'intent_ranking': [{'name': 'user_story'}],
                               "entities": [{"value": payload_body, "entity": KAIRON_USER_MSG_ENTITY}]},
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
            "slots": {"bot": "5f50md0a56b698ca10d35d2f"},
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
    assert len(response_json['events']) == 2
    assert len(response_json['responses']) == 1
    assert response_json['events'] == [
        {'event': 'slot', 'timestamp': None, 'name': 'city_value', 'value': '2'},
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
         'value': 'The value of London with color red is 2'}]
    assert response_json['responses'][0]['text'] == "The value of London with color red is 2"
    log = ActionServerLogs.objects(action=action_name, bot='5f50md0a56b698ca10d35d2f').get().to_mongo().to_dict()
    log.pop('_id')
    log.pop('timestamp')


@responses.activate
@mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
def test_vectordb_action_execution_embedding_search_from_value(mock_get_embedding):
    responses.add_passthru("https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken")
    action_name = "test_vectordb_action_execution"
    Actions(name=action_name, type=ActionType.database_action.value, bot="5f50fd0a56b698ca10d75d2e",
            user="user").save()
    payload_body = "Hi"
    DatabaseAction(
        name=action_name,
        collection='test_vectordb_action_execution',
        payload=[
            DbQuery(query_type=DbActionOperationType.embedding_search.value, type="from_value", value=payload_body)],
        response=HttpActionResponse(value="The value of ${data.result.0.id} is ${data.result.0.vector}"),
        set_slots=[SetSlotsFromResponse(name="vector_value", value="${data.result.0.vector}")],
        bot="5f50fd0a56b698ca10d75d2e",
        user="user"
    ).save()
    BotSettings(llm_settings=LLMSettings(enable_faq=True), bot="5f50fd0a56b698ca10d75d2e", user="user").save()
    llm_secret = LLMSecret(
        llm_type="openai",
        api_key="key_value",
        models=["model1", "model2"],
        api_base_url="https://api.example.com",
        bot="5f50fd0a56b698ca10d75d2e",
        user="user"
    )
    llm_secret.save()

    text_embedding_3_small_embeddings = [np.random.random(1536).tolist()]
    colbertv2_0_embeddings = [[np.random.random(128).tolist()]]
    bm25_embeddings = [{
        "indices": [1850593538, 11711171],
        "values": [1.66, 1.66]
    }]

    embeddings = {
        "dense": text_embedding_3_small_embeddings,
        "rerank": colbertv2_0_embeddings,
        "sparse": bm25_embeddings,
    }

    mock_get_embedding.return_value = embeddings

    http_url = 'http://localhost:6333/collections/5f50fd0a56b698ca10d75d2e_test_vectordb_action_execution_faq_embd/points/query'
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
        match=[responses.matchers.json_params_matcher({'query': embeddings,
                                                       'with_payload': True, 'limit': 10})],
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
    responses.add_passthru("https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken")
    action_name = "test_vectordb_action_execution"
    Actions(name=action_name, type=ActionType.database_action.value, bot="5f50md0a56b698ca10d35d2z",
            user="user").save()
    payload = {'filter': {
        'should': [{'key': 'city', 'match': {'value': 'London'}}, {'key': 'color', 'match': {'value': 'red'}}]}}
    payload_body = json.dumps(payload)
    DatabaseAction(
        name=action_name,
        collection='test_vectordb_action_execution_payload_search_from_value',
        payload=[DbQuery(query_type=DbActionOperationType.payload_search.value, type="from_value", value=payload_body)],
        response=HttpActionResponse(value="The value of ${data.0.city} with color ${data.0.color} is ${data.0.id}"),
        set_slots=[SetSlotsFromResponse(name="city_value", value="${data.0.id}")],
        bot="5f50md0a56b698ca10d35d2z",
        user="user"
    ).save()
    BotSettings(llm_settings=LLMSettings(enable_faq=True), bot="5f50md0a56b698ca10d35d2z", user="user").save()
    llm_secret = LLMSecret(
        llm_type="openai",
        api_key="key_value",
        models=["model1", "model2"],
        api_base_url="https://api.example.com",
        bot="5f50md0a56b698ca10d35d2z",
        user="user"
    )
    llm_secret.save()

    http_url = 'http://localhost:6333/collections/5f50md0a56b698ca10d35d2z_test_vectordb_action_execution_payload_search_from_value_faq_embd/points/query'
    resp_msg = json.dumps(
        [{"id": 2, "city": "London", "color": "red"}]
    )
    json_params_matcher = payload.copy()
    json_params_matcher.update(
        **{'with_payload': True, 'limit': 10}
    )
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
            "slots": {"bot": "5f50md0a56b698ca10d35d2z"},
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
            "slots": {"bot": "5f50md0a56b698ca10d35d2z"},
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
    assert len(response_json['events']) == 2
    assert len(response_json['responses']) == 1
    assert response_json['events'] == [
        {'event': 'slot', 'timestamp': None, 'name': 'city_value', 'value': '2'},
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
         'value': 'The value of London with color red is 2'}]
    assert response_json['responses'][0]['text'] == "The value of London with color red is 2"
    log = ActionServerLogs.objects(action=action_name, bot='5f50md0a56b698ca10d35d2z').get().to_mongo().to_dict()
    log.pop('_id')
    log.pop('timestamp')


@responses.activate
def test_vectordb_action_execution_payload_search_from_value_json_decode_error():
    responses.add_passthru("https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken")
    action_name = "test_vectordb_action_execution_payload_search_from_value_json_decode_error"
    Actions(name=action_name, type=ActionType.database_action.value, bot="5f50md0a56b698ca10d35d2e",
            user="user").save()
    payload_body = "{'filter'}"
    DatabaseAction(
        name=action_name,
        collection='test_vectordb_action_execution_payload_search_from_value',
        payload=[DbQuery(query_type=DbActionOperationType.payload_search.value, type="from_value", value=payload_body)],
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
    assert len(response_json['events']) == 1
    assert len(response_json['responses']) == 1
    assert response_json['events'] == [{'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
                                        'value': 'I have failed to process your request.'}]
    assert response_json['responses'][0]['text'] == 'I have failed to process your request.'
    log = ActionServerLogs.objects(action=action_name, bot='5f50md0a56b698ca10d35d2e').get().to_mongo().to_dict()
    assert log['exception'] == "Error converting payload to JSON: {'filter'}"
    log.pop('_id')
    log.pop('timestamp')


@responses.activate
@mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
def test_vectordb_action_execution_embedding_search_from_slot(mock_get_embedding):
    responses.add_passthru("https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken")
    action_name = "test_vectordb_action_execution"
    Actions(name=action_name, type=ActionType.database_action.value, bot="5f50fx0a56b698ca10d35d2e",
            user="user").save()
    slot = 'name'
    Slots(name=slot, type='text', bot='5f50fx0a56b698ca10d35d2e', user='user').save()
    payload = "Hi"
    DatabaseAction(
        name=action_name,
        collection='test_vectordb_action_execution_embedding_search_from_slot',
        payload=[DbQuery(query_type=DbActionOperationType.embedding_search.value, type="from_slot", value='name')],
        response=HttpActionResponse(value="The value of ${data.result.0.id} is ${data.result.0.vector}"),
        set_slots=[SetSlotsFromResponse(name="vector_value", value="${data.result.0.vector}")],
        bot="5f50fx0a56b698ca10d35d2e",
        user="user"
    ).save()
    BotSettings(llm_settings=LLMSettings(enable_faq=True), bot="5f50fx0a56b698ca10d35d2e", user="user").save()
    llm_secret = LLMSecret(
        llm_type="openai",
        api_key="key_value",
        models=["model1", "model2"],
        api_base_url="https://api.example.com",
        bot="5f50fx0a56b698ca10d35d2e",
        user="user"
    )
    llm_secret.save()
    text_embedding_3_small_embeddings = [np.random.random(1536).tolist()]
    colbertv2_0_embeddings = [[np.random.random(128).tolist()]]
    bm25_embeddings = [{
        "indices": [1850593538, 11711171],
        "values": [1.66, 1.66]
    }]

    embeddings = {
        "dense": text_embedding_3_small_embeddings,
        "rerank": colbertv2_0_embeddings,
        "sparse": bm25_embeddings,
    }

    mock_get_embedding.return_value = embeddings



    http_url = 'http://localhost:6333/collections/5f50fx0a56b698ca10d35d2e_test_vectordb_action_execution_embedding_search_from_slot_faq_embd/points/query'
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
        match=[responses.matchers.json_params_matcher({'query': embeddings,
                                                       'with_payload': True, 'limit': 10})],
    )

    request_object = {
        "next_action": action_name,
        "tracker": {
            "sender_id": "default",
            "conversation_id": "default",
            "slots": {"bot": "5f50fx0a56b698ca10d35d2e", "name": payload},
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
@mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
def test_vectordb_action_execution_embedding_search_no_response_dispatch(mock_get_embedding):
    responses.add_passthru("https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken")
    action_name = "test_vectordb_action_execution_no_response_dispatch"
    Actions(name=action_name, type=ActionType.database_action.value, bot="5f50fd0a56v098ca10d75d2e",
            user="user").save()
    payload_body = "Milk"
    DatabaseAction(
        name=action_name,
        collection='test_vectordb_action_execution_no_response_dispatch',
        payload=[DbQuery(query_type=DbActionOperationType.embedding_search.value,
                         type="from_value", value=payload_body)],
        response=HttpActionResponse(value="The value of ${data.result.0.id} is ${data.result.0.vector}",
                                    dispatch=False),
        set_slots=[SetSlotsFromResponse(name="vector_value", value="${data.result.0.vector}")],
        bot="5f50fd0a56v098ca10d75d2e",
        user="user"
    ).save()
    BotSettings(llm_settings=LLMSettings(enable_faq=True), bot="5f50fd0a56v098ca10d75d2e", user="user").save()
    llm_secret = LLMSecret(
        llm_type="openai",
        api_key="key_value",
        models=["model1", "model2"],
        api_base_url="https://api.example.com",
        bot="5f50fd0a56v098ca10d75d2e",
        user="user"
    )
    llm_secret.save()

    text_embedding_3_small_embeddings = [np.random.random(1536).tolist()]
    colbertv2_0_embeddings = [[np.random.random(128).tolist()]]
    bm25_embeddings = [{
        "indices": [1850593538, 11711171],
        "values": [1.66, 1.66]
    }]

    embeddings = {
        "dense": text_embedding_3_small_embeddings,
        "rerank": colbertv2_0_embeddings,
        "sparse": bm25_embeddings,
    }

    mock_get_embedding.return_value = embeddings

    http_url = 'http://localhost:6333/collections/5f50fd0a56v098ca10d75d2e_test_vectordb_action_execution_no_response_dispatch_faq_embd/points/query'
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
        match=[responses.matchers.json_params_matcher({'query': embeddings,
                                                       'with_payload': True, 'limit': 10})],
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
        payload=[DbQuery(query_type="vector_search",
                         type="from_value", value=payload_body)],
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


@mock.patch("kairon.shared.actions.utils.ActionUtility.get_action")
@mock.patch("kairon.actions.definitions.database.ActionDatabase.retrieve_config")
def test_vectordb_action_failed_execution(mock_action_config, mock_action):
    action_name = "test_run_with_get_action"
    payload_body = {"ids": [0], "with_payload": True, "with_vector": True}
    action = Actions(name=action_name, type=ActionType.database_action.value, bot="5f50fd0a56b697ca10d35d2e",
                     user="user")
    action_config = DatabaseAction(
        name=action_name,
        collection='test_vectordb_action_failed_execution',
        payload=[DbQuery(query_type=DbActionOperationType.embedding_search.value,
                         type="from_value", value=payload_body)],
        response=HttpActionResponse(value="The value of ${data.result.0.id} is ${data.result.0.vector"),
        bot="5f50fd0a56b697ca10d35d2e",
        user="user"
    )
    bot_settings = BotSettings(llm_settings=LLMSettings(enable_faq=True), bot="5f50fd0a56b697ca10d35d2e",
                               user="user").save()
    BotSecrets(secret_type=BotSecretType.gpt_key.value, value="key_value",
               bot="5f50fd0a56b697ca10d35d2e", user="user").save()

    def _get_action_config(*arge, **kwargs):
        return action_config.to_mongo().to_dict(), bot_settings.to_mongo().to_dict()

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
    with mock.patch.object(ActionUtility, "get_action") as mock_action:
        mock_action.side_effect = _get_action
        with mock.patch.object(ActionSetSlot, "retrieve_config") as mocked:
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
    with mock.patch.object(ActionUtility, "get_action") as mock_action:
        mock_action.side_effect = _get_action
        with mock.patch.object(ActionSetSlot, "retrieve_config") as mocked:
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
    with mock.patch.object(ActionUtility, "get_action") as mock_action:
        mock_action.side_effect = _get_action
        with mock.patch.object(ActionSetSlot, "retrieve_config") as mocked:
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
                     'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'},
                      'latest_message': {'intent_ranking': [{'name': 'test_run'}], 'text': 'get intents'},
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
                      'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'},
                      'latest_message': {'intent_ranking': [{'name': 'test_run'}], 'text': 'get intents'},
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
                      'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'},
                      'latest_message': {'intent_ranking': [{'name': 'test_run'}], 'text': 'get intents'},
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
                      'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'},
                      'latest_message': {'intent_ranking': [{'name': 'test_run'}], 'text': 'get intents'},
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
                      'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'},
                      'latest_message': {'intent_ranking': [{'name': 'test_run'}], 'text': 'get intents'},
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
                      'intent': 'test_run', 'chat_log': [],
                      'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'},
                      'latest_message': {'intent_ranking': [{'name': 'test_run'}], 'text': 'get intents'},
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
                      'key_vault': {'EMAIL': 'uditpandey@digite.com', 'FIRSTNAME': 'udit'},
                      'latest_message': {'intent_ranking': [{'name': 'test_run'}], 'text': 'get intents'},
                      'kairon_user_msg': None, 'session_started': None}}
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
                                    'FIRSTNAME': 'udit'},
                      'latest_message': {'intent_ranking': [{'name': 'test_run'}], 'text': 'get intents'},
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
                      'latest_message': {'intent_ranking': [{'name': 'test_run'}], 'text': 'get intents'},
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
@mock.patch("kairon.shared.actions.utils.ActionUtility.get_action")
@mock.patch("kairon.actions.definitions.email.ActionEmail.retrieve_config")
@mock.patch("kairon.shared.utils.SMTP", autospec=True)
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
        from_email=CustomActionRequestParameters(value="test@demo.com", parameter_type="value"),
        to_email=CustomActionParameters(value=["test@test.com"], parameter_type="value"),
        subject="test",
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
    assert from_email == action_config.from_email.value
    assert password == action_config.smtp_password.value

    name, args, kwargs = mock_smtp.method_calls.pop(0)
    assert name == '().sendmail'
    assert {} == kwargs

    assert args[0] == action_config.from_email.value
    assert args[1] == ["test@test.com"]
    assert str(args[2]).__contains__(action_config.subject)
    assert str(args[2]).__contains__("Content-Type: text/html")


@mock.patch("kairon.shared.actions.utils.ActionUtility.get_action")
@mock.patch("kairon.actions.definitions.email.ActionEmail.retrieve_config")
@mock.patch("kairon.shared.utils.SMTP", autospec=True)
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
        from_email=CustomActionRequestParameters(value="test@demo.com", parameter_type="value"),
        to_email=CustomActionParameters(value=["test@test.com"], parameter_type="value"),
        subject="test",
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
    assert from_email == action_config.from_email.value
    assert password == action_config.smtp_password.value

    name, args, kwargs = mock_smtp.method_calls.pop(0)
    assert name == '().sendmail'
    assert {} == kwargs

    assert args[0] == action_config.from_email.value
    assert args[1] == ["test@test.com"]
    assert str(args[2]).__contains__(action_config.subject)
    assert str(args[2]).__contains__("Content-Type: text/html")
    assert str(args[2]).__contains__("Subject: default test")


@mock.patch("kairon.shared.actions.utils.ActionUtility.get_action")
@mock.patch("kairon.actions.definitions.email.ActionEmail.retrieve_config")
@mock.patch("kairon.shared.utils.SMTP", autospec=True)
def test_email_action_execution_with_sender_email_from_slot(mock_smtp, mock_action_config, mock_action):
    Utility.email_conf['email']['templates']['conversation'] = open('template/emails/conversation.html',
                                                                    'rb').read().decode()
    Utility.email_conf['email']['templates']['bot_msg_conversation'] = open(
        'template/emails/bot_msg_conversation.html', 'rb').read().decode()
    Utility.email_conf['email']['templates']['user_msg_conversation'] = open(
        'template/emails/user_msg_conversation.html', 'rb').read().decode()
    Utility.email_conf['email']['templates']['button_template'] = open('template/emails/button.html',
                                                                       'rb').read().decode()
    action_name = "test_email_action_execution_with_sender_email_from_slot"
    action = Actions(name=action_name, type=ActionType.email_action.value, bot="bot", user="user")
    action_config = EmailActionConfig(
        action_name=action_name,
        smtp_url="test.localhost",
        smtp_port=293,
        smtp_password=CustomActionRequestParameters(key='smtp_password', value="test"),
        from_email=CustomActionRequestParameters(value="from_email", parameter_type="slot"),
        to_email=CustomActionParameters(value=["test@test.com"], parameter_type="value"),
        subject="test",
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
            "sender_id": "mahesh.sattala",
            "conversation_id": "default",
            "slots": {"bot": "5f50fd0a56b698ca10d35d2e", "requested_slot": "from_email",
                      "from_email": "mahesh@gmail.com"},
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
    assert from_email == 'mahesh@gmail.com'
    assert password == action_config.smtp_password.value

    name, args, kwargs = mock_smtp.method_calls.pop(0)
    assert name == '().sendmail'
    assert {} == kwargs

    assert args[0] == 'mahesh@gmail.com'
    assert args[1] == ["test@test.com"]
    assert str(args[2]).__contains__(action_config.subject)
    assert str(args[2]).__contains__("Content-Type: text/html")
    assert str(args[2]).__contains__("Subject: mahesh.sattala test")


@mock.patch("kairon.shared.actions.utils.ActionUtility.get_action")
@mock.patch("kairon.actions.definitions.email.ActionEmail.retrieve_config")
@mock.patch("kairon.shared.utils.SMTP", autospec=True)
def test_email_action_execution_with_receiver_email_list_from_slot(mock_smtp, mock_action_config, mock_action):
    Utility.email_conf['email']['templates']['conversation'] = open('template/emails/conversation.html',
                                                                    'rb').read().decode()
    Utility.email_conf['email']['templates']['bot_msg_conversation'] = open(
        'template/emails/bot_msg_conversation.html', 'rb').read().decode()
    Utility.email_conf['email']['templates']['user_msg_conversation'] = open(
        'template/emails/user_msg_conversation.html', 'rb').read().decode()
    Utility.email_conf['email']['templates']['button_template'] = open('template/emails/button.html',
                                                                       'rb').read().decode()

    action_name = "test_email_action_execution_with_receiver_email_list_from_slot"
    action = Actions(name=action_name, type=ActionType.email_action.value, bot="bot", user="user")
    action_config = EmailActionConfig(
        action_name=action_name,
        smtp_url="test.localhost",
        smtp_port=293,
        smtp_password=CustomActionRequestParameters(key='smtp_password', value="test"),
        from_email=CustomActionRequestParameters(value="test@demo.com", parameter_type="value"),
        to_email=CustomActionParameters(value="to_email", parameter_type="slot"),
        subject="test",
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
            "sender_id": "mahesh.sattala",
            "conversation_id": "default",
            "slots": {"bot": "5f50fd0a56b698ca10d35d2e", "requested_slot": "to_email",
                      "to_email": ["test@gmail.com"]},
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
    assert from_email == action_config.from_email.value
    assert password == action_config.smtp_password.value

    name, args, kwargs = mock_smtp.method_calls.pop(0)
    assert name == '().sendmail'
    assert {} == kwargs

    assert args[0] == action_config.from_email.value
    assert args[1] == ["test@gmail.com"]
    assert str(args[2]).__contains__(action_config.subject)
    assert str(args[2]).__contains__("Content-Type: text/html")
    assert str(args[2]).__contains__("Subject: mahesh.sattala test")


@mock.patch("kairon.shared.actions.utils.ActionUtility.get_action")
@mock.patch("kairon.actions.definitions.email.ActionEmail.retrieve_config")
@mock.patch("kairon.shared.utils.SMTP", autospec=True)
def test_email_action_execution_with_single_receiver_email_from_slot(mock_smtp, mock_action_config, mock_action):
    Utility.email_conf['email']['templates']['conversation'] = open('template/emails/conversation.html',
                                                                    'rb').read().decode()
    Utility.email_conf['email']['templates']['bot_msg_conversation'] = open(
        'template/emails/bot_msg_conversation.html', 'rb').read().decode()
    Utility.email_conf['email']['templates']['user_msg_conversation'] = open(
        'template/emails/user_msg_conversation.html', 'rb').read().decode()
    Utility.email_conf['email']['templates']['button_template'] = open('template/emails/button.html',
                                                                       'rb').read().decode()

    action_name = "test_email_action_execution_with_single_receiver_email_from_slot"
    action = Actions(name=action_name, type=ActionType.email_action.value, bot="bot", user="user")
    action_config = EmailActionConfig(
        action_name=action_name,
        smtp_url="test.localhost",
        smtp_port=293,
        smtp_password=CustomActionRequestParameters(key='smtp_password', value="test"),
        from_email=CustomActionRequestParameters(value="test@demo.com", parameter_type="value"),
        to_email=CustomActionParameters(value="to_email", parameter_type="slot"),
        subject="test",
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
            "sender_id": "mahesh.sattala",
            "conversation_id": "default",
            "slots": {"bot": "5f50fd0a56b698ca10d35d2e", "requested_slot": "to_email",
                      "to_email": "example@gmail.com"},
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
    assert from_email == action_config.from_email.value
    assert password == action_config.smtp_password.value

    name, args, kwargs = mock_smtp.method_calls.pop(0)
    assert name == '().sendmail'
    assert {} == kwargs

    assert args[0] == action_config.from_email.value
    assert args[1] == ["example@gmail.com"]
    assert str(args[2]).__contains__(action_config.subject)
    assert str(args[2]).__contains__("Content-Type: text/html")
    assert str(args[2]).__contains__("Subject: mahesh.sattala test")


@mock.patch("kairon.shared.actions.utils.ActionUtility.get_action")
@mock.patch("kairon.actions.definitions.email.ActionEmail.retrieve_config")
@mock.patch("kairon.shared.utils.SMTP", autospec=True)
def test_email_action_execution_with_invalid_from_email(mock_smtp, mock_action_config, mock_action):
    Utility.email_conf['email']['templates']['conversation'] = open('template/emails/conversation.html',
                                                                    'rb').read().decode()
    Utility.email_conf['email']['templates']['bot_msg_conversation'] = open(
        'template/emails/bot_msg_conversation.html', 'rb').read().decode()
    Utility.email_conf['email']['templates']['user_msg_conversation'] = open(
        'template/emails/user_msg_conversation.html', 'rb').read().decode()
    Utility.email_conf['email']['templates']['button_template'] = open('template/emails/button.html',
                                                                       'rb').read().decode()

    action_name = "test_email_action_execution_with_invalid_from_email"
    action = Actions(name=action_name, type=ActionType.email_action.value, bot="bot", user="user")
    action_config = EmailActionConfig(
        action_name=action_name,
        smtp_url="test.localhost",
        smtp_port=293,
        smtp_password=CustomActionRequestParameters(key='smtp_password', value="test"),
        from_email=CustomActionRequestParameters(value=["test@demo.com"], parameter_type="value"),
        to_email=CustomActionParameters(value="to_email", parameter_type="slot"),
        subject="test",
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
            "sender_id": "mahesh.sattala",
            "conversation_id": "default",
            "slots": {"bot": "5f50fd0a56b698ca10d35d2e", "requested_slot": "to_email",
                      "to_email": "example@gmail.com"},
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
    assert logs.exception == "Invalid 'from_email' type. It must be of type str."


@mock.patch("kairon.shared.actions.utils.ActionUtility.get_action")
@mock.patch("kairon.actions.definitions.email.ActionEmail.retrieve_config")
@mock.patch("kairon.shared.utils.SMTP", autospec=True)
def test_email_action_execution_with_invalid_to_email(mock_smtp, mock_action_config, mock_action):
    Utility.email_conf['email']['templates']['conversation'] = open('template/emails/conversation.html',
                                                                    'rb').read().decode()
    Utility.email_conf['email']['templates']['bot_msg_conversation'] = open(
        'template/emails/bot_msg_conversation.html', 'rb').read().decode()
    Utility.email_conf['email']['templates']['user_msg_conversation'] = open(
        'template/emails/user_msg_conversation.html', 'rb').read().decode()
    Utility.email_conf['email']['templates']['button_template'] = open('template/emails/button.html',
                                                                       'rb').read().decode()

    action_name = "test_email_action_execution_with_invalid_to_email"
    action = Actions(name=action_name, type=ActionType.email_action.value, bot="bot", user="user")
    action_config = EmailActionConfig(
        action_name=action_name,
        smtp_url="test.localhost",
        smtp_port=293,
        smtp_password=CustomActionRequestParameters(key='smtp_password', value="test"),
        from_email=CustomActionRequestParameters(value="test@demo.com", parameter_type="value"),
        to_email=CustomActionParameters(value={"to_email": "test@test.com"}, parameter_type="value"),
        subject="test",
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
            "sender_id": "mahesh.sattala",
            "conversation_id": "default",
            "slots": {"bot": "5f50fd0a56b698ca10d35d2e", "requested_slot": "to_email",
                      "to_email": "example@gmail.com"},
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
    assert logs.exception == "Invalid 'from_email' type. It must be of type str."


@mock.patch("kairon.shared.actions.utils.ActionUtility.get_action")
@mock.patch("kairon.actions.definitions.email.ActionEmail.retrieve_config")
@mock.patch("kairon.shared.utils.SMTP", autospec=True)
def test_email_action_execution_with_invalid_to_email(mock_smtp, mock_action_config, mock_action):
    Utility.email_conf['email']['templates']['conversation'] = open('template/emails/conversation.html',
                                                                    'rb').read().decode()
    Utility.email_conf['email']['templates']['bot_msg_conversation'] = open(
        'template/emails/bot_msg_conversation.html', 'rb').read().decode()
    Utility.email_conf['email']['templates']['user_msg_conversation'] = open(
        'template/emails/user_msg_conversation.html', 'rb').read().decode()
    Utility.email_conf['email']['templates']['button_template'] = open('template/emails/button.html',
                                                                       'rb').read().decode()

    action_name = "test_email_action_execution_with_invalid_to_email"
    action = Actions(name=action_name, type=ActionType.email_action.value, bot="bot", user="user")
    action_config = EmailActionConfig(
        action_name=action_name,
        smtp_url="test.localhost",
        smtp_port=293,
        smtp_password=CustomActionRequestParameters(key='smtp_password', value="test"),
        from_email=CustomActionRequestParameters(value="test@demo.com", parameter_type="value"),
        to_email=CustomActionParameters(value={"to_email": "test@test.com"}, parameter_type="value"),
        subject="test",
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
            "sender_id": "mahesh.sattala",
            "conversation_id": "default",
            "slots": {"bot": "5f50fd0a56b698ca10d35d2e", "requested_slot": "to_email",
                      "to_email": "example@gmail.com"},
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
    assert logs.exception == "Invalid 'to_email' type. It must be of type str or list."


@mock.patch("kairon.shared.actions.utils.ActionUtility.get_action")
@mock.patch("kairon.actions.definitions.email.ActionEmail.retrieve_config")
@mock.patch("kairon.shared.utils.SMTP", autospec=True)
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
        from_email=CustomActionRequestParameters(value="test@demo.com", parameter_type="value"),
        to_email=CustomActionParameters(value=["test@test.com"], parameter_type="value"),
        subject="test",
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
    assert from_email == action_config.from_email.value
    assert password == action_config.smtp_password.value

    name, args, kwargs = mock_smtp.method_calls.pop(0)
    assert name == '().sendmail'
    assert {} == kwargs

    assert args[0] == action_config.from_email.value
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


@mock.patch("kairon.shared.actions.utils.ActionUtility.get_action")
@mock.patch("kairon.actions.definitions.email.ActionEmail.retrieve_config")
def test_email_action_failed_execution(mock_action_config, mock_action):
    action_name = "test_run_email_action"
    action = Actions(name=action_name, type=ActionType.email_action.value, bot="bot", user="user")
    action_config = EmailActionConfig(
        action_name=action_name,
        smtp_url="test.localhost",
        smtp_port=293,
        smtp_password=CustomActionRequestParameters(value="test"),
        from_email=CustomActionRequestParameters(value="test@demo.com", parameter_type="value"),
        to_email=CustomActionParameters(value="test@test.com", parameter_type="value"),
        subject="test",
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



def test_process_google_search_action_search_term():
    action_name = "custom_search_action"
    bot = "5f50fd0a56b698ca10d35d2e"
    user = 'test_user'
    Actions(name=action_name, type=ActionType.google_search_action.value, bot=bot, user='test_user').save()
    GoogleSearchAction(name=action_name, api_key=CustomActionRequestParameters(value='1234567890'),
                       search_engine_id='asdfg::123456', bot=bot, user=user, search_term=CustomActionRequestParameters(value='tajmahal', key='search_term')).save()

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
    with mock.patch.object(ActionUtility, "perform_google_search") as mocked:
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

    Actions.objects(name=action_name, bot=bot).delete()
    GoogleSearchAction.objects(name=action_name, bot=bot).delete()



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
    with mock.patch.object(ActionUtility, "perform_google_search") as mocked:
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
    with mock.patch.object(ActionUtility, "perform_google_search") as mocked:
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
    with mock.patch.object(ActionUtility, "perform_google_search") as mocked:
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

    with mock.patch.object(ActionUtility, "perform_google_search") as mocked:
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

    with mock.patch.object(ActionUtility, "perform_google_search") as mocked:
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

    with mock.patch.object(ActionUtility, "perform_google_search") as mocked:
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
    with mock.patch.object(ActionUtility, "perform_google_search") as mocked:
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
    with mock.patch.object(ActionUtility, "perform_google_search") as mocked:
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
        assert kwargs == {'topn': 1, 'website': 'https://www.w3schools.com/', 'bot': bot}
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
    with mock.patch.object(ActionUtility, "perform_web_search") as mocked:
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
    assert log[
               'bot_response'] == 'Data Science is a combination of multiple disciplines that uses statistics, data analysis, and machine learning to analyze data and to extract knowledge and insights from it. What is Data Science? Data Science is about data gathering, analysis and decision-making.\nTo know more, please visit: <a href = "https://www.w3schools.com/datascience/ds_introduction.asp" target="_blank" >Data Science Introduction - W3Schools</a>'


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
        json={"success": True, "data": [{"title": 'Data Science: Definition, Lifecycle, Skills and Tools | IBM',
                                         "description": "What is data science? Data science combines math and statistics, specialized programming, advanced analytics, artificial intelligence (AI), and machine learning with specific subject matter expertise to uncover actionable insights hidden in an organization's data. These insights can be used to guide decision making and strategic planning.",
                                         "url": "https://www.ibm.com/topics/data-science"}], "error_code": 0},
        status=200,
        match=[
            responses.matchers.json_params_matcher({
                "text": 'What is data science?', "site": '', "topn": 1, 'bot': bot
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
            {'event': 'slot', 'timestamp': None, 'name': 'public_search_response',
             'value': "What is data science? Data science combines math and statistics, specialized programming, advanced analytics, artificial intelligence (AI), and machine learning with specific subject matter expertise to uncover actionable insights hidden in an organization's data. These insights can be used to guide decision making and strategic planning.\nTo know more, please visit: <a href = \"https://www.ibm.com/topics/data-science\" target=\"_blank\" >Data Science: Definition, Lifecycle, Skills and Tools | IBM</a>"},
            {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
             'value': "What is data science? Data science combines math and statistics, specialized programming, advanced analytics, artificial intelligence (AI), and machine learning with specific subject matter expertise to uncover actionable insights hidden in an organization's data. These insights can be used to guide decision making and strategic planning.\nTo know more, please visit: <a href = \"https://www.ibm.com/topics/data-science\" target=\"_blank\" >Data Science: Definition, Lifecycle, Skills and Tools | IBM</a>"}],
            'responses': [
                {
                    'text': "What is data science? Data science combines math and statistics, specialized programming, advanced analytics, artificial intelligence (AI), and machine learning with specific subject matter expertise to uncover actionable insights hidden in an organization's data. These insights can be used to guide decision making and strategic planning.\nTo know more, please visit: <a href = \"https://www.ibm.com/topics/data-science\" target=\"_blank\" >Data Science: Definition, Lifecycle, Skills and Tools | IBM</a>",
                    'buttons': [], 'elements': [], 'custom': {}, 'template': None, 'response': None, 'image': None,
                    'attachment': None}]}


def test_process_web_search_action_with_kairon_user_msg_entity():
    action_name = "public_search_action_one_kairon_user_msg_entity"
    bot = "5f51zd0a56b698ca10d35d2e"
    user = 'test_user'
    Actions(name=action_name, type=ActionType.web_search_action.value, bot=bot, user='test_user').save()
    WebSearchAction(name=action_name, set_slot='public_search_response', topn=2, bot=bot,
                    user=user).save()

    def _perform_web_search(*args, **kwargs):
        assert args == ('my public search text',)
        assert kwargs == {'topn': 2, 'website': None, 'bot': bot}
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
    with mock.patch.object(ActionUtility, "perform_web_search") as mocked:
        mocked.side_effect = _perform_web_search
        response = client.post("/webhook", json=request_object)
        response_json = response.json()
        assert response.status_code == 200
        assert response_json == {'events': [
            {'event': 'slot', 'timestamp': None, 'name': 'public_search_response',
             'value': 'Data science combines math, statistics, programming, analytics, AI, and machine learning to uncover insights from data. Learn how data science works, what it entails, and how it differs from data science and BI.\nTo know more, please visit: <a href = "https://www.ibm.com/topics/data-science" target="_blank" >What is Data Science? | IBM</a>\n\nData science is an interdisciplinary field that uses algorithms, procedures, and processes to examine large amounts of data in order to uncover hidden patterns, generate insights, and direct decision-making.\nTo know more, please visit: <a href = "https://www.coursera.org/articles/what-is-data-science" target="_blank" >What Is Data Science? Definition, Examples, Jobs, and More</a>'},
            {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
             'value': 'Data science combines math, statistics, programming, analytics, AI, and machine learning to uncover insights from data. Learn how data science works, what it entails, and how it differs from data science and BI.\nTo know more, please visit: <a href = "https://www.ibm.com/topics/data-science" target="_blank" >What is Data Science? | IBM</a>\n\nData science is an interdisciplinary field that uses algorithms, procedures, and processes to examine large amounts of data in order to uncover hidden patterns, generate insights, and direct decision-making.\nTo know more, please visit: <a href = "https://www.coursera.org/articles/what-is-data-science" target="_blank" >What Is Data Science? Definition, Examples, Jobs, and More</a>'}],
            'responses': [
                {
                    'text': 'Data science combines math, statistics, programming, analytics, AI, and machine learning to uncover insights from data. Learn how data science works, what it entails, and how it differs from data science and BI.\nTo know more, please visit: <a href = "https://www.ibm.com/topics/data-science" target="_blank" >What is Data Science? | IBM</a>\n\nData science is an interdisciplinary field that uses algorithms, procedures, and processes to examine large amounts of data in order to uncover hidden patterns, generate insights, and direct decision-making.\nTo know more, please visit: <a href = "https://www.coursera.org/articles/what-is-data-science" target="_blank" >What Is Data Science? Definition, Examples, Jobs, and More</a>',
                    'buttons': [], 'elements': [], 'custom': {}, 'template': None, 'response': None, 'image': None,
                    'attachment': None}]}


def test_process_web_search_action_without_kairon_user_msg_entity():
    action_name = "public_search_action_one_without_kairon_user_msg_entity"
    bot = "5f51zd0a56b698ca10d35d6z"
    user = 'test_user'
    Actions(name=action_name, type=ActionType.web_search_action.value, bot=bot, user='test_user').save()
    WebSearchAction(name=action_name, set_slot='public_search_response', topn=2, bot=bot,
                    user=user).save()

    def _perform_web_search(*args, **kwargs):
        assert args == ('/action_public_search',)
        assert kwargs == {'topn': 2, 'website': None, 'bot': bot}
        return [
            {'title': 'What is Data Science? | IBM',
             'text': 'Data science combines math, statistics, programming, analytics, AI, and machine learning to uncover insights from data. Learn how data science works, what it entails, and how it differs from data science and BI.',
             'link': 'https://www.ibm.com/topics/data-science'},
            {'title': 'What Is Data Science? Definition, Examples, Jobs, and More',
             'text': 'Data science is an interdisciplinary field that uses algorithms, procedures, and processes to examine large amounts of data in order to uncover hidden patterns, generate insights, and direct decision-making.',
             'link': 'https://www.coursera.org/articles/what-is-data-science', }]

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
    with mock.patch.object(ActionUtility, "perform_web_search") as mocked:
        mocked.side_effect = _perform_web_search
        response = client.post("/webhook", json=request_object)
        response_json = response.json()
        assert response.status_code == 200
        assert response_json == {'events': [
            {'event': 'slot', 'timestamp': None, 'name': 'public_search_response',
             'value': 'Data science combines math, statistics, programming, analytics, AI, and machine learning to uncover insights from data. Learn how data science works, what it entails, and how it differs from data science and BI.\nTo know more, please visit: <a href = "https://www.ibm.com/topics/data-science" target="_blank" >What is Data Science? | IBM</a>\n\nData science is an interdisciplinary field that uses algorithms, procedures, and processes to examine large amounts of data in order to uncover hidden patterns, generate insights, and direct decision-making.\nTo know more, please visit: <a href = "https://www.coursera.org/articles/what-is-data-science" target="_blank" >What Is Data Science? Definition, Examples, Jobs, and More</a>'},
            {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
             'value': 'Data science combines math, statistics, programming, analytics, AI, and machine learning to uncover insights from data. Learn how data science works, what it entails, and how it differs from data science and BI.\nTo know more, please visit: <a href = "https://www.ibm.com/topics/data-science" target="_blank" >What is Data Science? | IBM</a>\n\nData science is an interdisciplinary field that uses algorithms, procedures, and processes to examine large amounts of data in order to uncover hidden patterns, generate insights, and direct decision-making.\nTo know more, please visit: <a href = "https://www.coursera.org/articles/what-is-data-science" target="_blank" >What Is Data Science? Definition, Examples, Jobs, and More</a>'}],
            'responses': [{
                'text': 'Data science combines math, statistics, programming, analytics, AI, and machine learning to uncover insights from data. Learn how data science works, what it entails, and how it differs from data science and BI.\nTo know more, please visit: <a href = "https://www.ibm.com/topics/data-science" target="_blank" >What is Data Science? | IBM</a>\n\nData science is an interdisciplinary field that uses algorithms, procedures, and processes to examine large amounts of data in order to uncover hidden patterns, generate insights, and direct decision-making.\nTo know more, please visit: <a href = "https://www.coursera.org/articles/what-is-data-science" target="_blank" >What Is Data Science? Definition, Examples, Jobs, and More</a>',
                'buttons': [], 'elements': [], 'custom': {}, 'template': None, 'response': None,
                'image': None, 'attachment': None}]}
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
        assert kwargs == {'topn': 1, 'website': None, 'bot': bot}
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

    with mock.patch.object(ActionUtility, "perform_web_search") as mocked:
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
    with mock.patch.object(ActionUtility, "perform_web_search") as mocked:
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
    with mock.patch.object(ActionUtility, "perform_web_search") as mocked:
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

    with mock.patch('kairon.shared.actions.data_objects.JiraAction.validate', new=_mock_response):
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
    with mock.patch.object(ActionUtility, "create_jira_issue") as mocked:
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

    with mock.patch('kairon.shared.actions.data_objects.JiraAction.validate', new=_mock_validation):
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
    with mock.patch.object(ActionUtility, "create_jira_issue") as mocked:
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
    with mock.patch('zenpy.Zenpy'):
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

    with mock.patch('zenpy.Zenpy'):
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
    with mock.patch('zenpy.Zenpy') as zen:
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

    with mock.patch('zenpy.Zenpy') as zen:
        zen.side_effect = __mock_zendesk_error
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
    with mock.patch('pipedrive.client.Client'):
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

    with mock.patch('pipedrive.organizations.Organizations.create_organization', __mock_create_organization):
        with mock.patch('pipedrive.persons.Persons.create_person', __mock_create_person):
            with mock.patch('pipedrive.leads.Leads.create_lead', __mock_create_leads):
                with mock.patch('pipedrive.notes.Notes.create_note', __mock_create_note):
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
        notes=[
            CustomActionRequestParameters(key="order_id", parameter_type="slot",
                                          value="order_id", encrypt=True),
            CustomActionRequestParameters(key="phone_number", parameter_type="value",
                                          value="9876543210", encrypt=False),
        ],
        bot=bot, user="udit.pandey@digite.com"
    ).save()
    request_object = json.load(open("tests/testing_data/actions/action-request.json"))
    request_object["tracker"]["slots"]["bot"] = bot
    request_object["tracker"]["slots"]["amount"] = 11000
    request_object["tracker"]["slots"]["contact"] = "987654320"
    request_object["tracker"]["slots"]["order_id"] = "dsjdksjdksjdksj"
    request_object["next_action"] = action_name
    request_object["tracker"]["sender_id"] = "udit.pandey"

    response_object = json.load(open("tests/testing_data/actions/razorpay-success.json"))
    responses.add(
        "POST",
        "https://api.razorpay.com/v1/payment_links/",
        json=response_object,
        match=[responses.matchers.json_params_matcher({
            "amount": 11000, "currency": "INR",
            "customer": {"username": "udit.pandey", "email": "udit.pandey", "contact": "987654320"},
            "notes": {"phone_number": "9876543210", "order_id": "dsjdksjdksjdksj", "bot": "5f50fd0a56b698ca10d35d2e"}
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
    with mock.patch('pipedrive.client.Client'):
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

    with mock.patch('pipedrive.organizations.Organizations.create_organization', __mock_pipedrive_error):
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

    with mock.patch.object(MongoProcessor, "search_training_examples") as mock_action:
        mock_action.side_effect = _mock_search
        response = client.post("/webhook", json=request_object)
        response_json = response.json()
        assert response_json['events'] == []
        assert len(response_json['responses'][0]['buttons']) == 3
        assert set(response_json['responses'][0]['buttons'][0].keys()) == {"text", "payload"}

    def _mock_search(*args, **kwargs):
        for _ in []:
            yield

    with mock.patch.object(MongoProcessor, "search_training_examples") as mock_action:
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
                                     "initial_value": "637f1b92df3b90588a30073e",
                                     "influence_conversation": True},
                             "kairon_action_response": {"type": "rasa.shared.core.slots.AnySlot",
                                                        "initial_value": None,
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
                                     "initial_value": "637f1b92df3b90588a30073e",
                                     "influence_conversation": True},
                             "kairon_action_response": {"type": "rasa.shared.core.slots.AnySlot",
                                                        "initial_value": None,
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
    llm_secret = LLMSecret(
        llm_type="openai",
        api_key="uditpandey",
        models=["gpt-3.5-turbo"],
        bot=bot,
        user=user
    )
    llm_secret.save()
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
                                     "initial_value": "637f1b92df3b90588a30073e",
                                     "influence_conversation": True},
                             "kairon_action_response": {"type": "rasa.shared.core.slots.AnySlot",
                                                        "initial_value": None,
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
    llm_secret = LLMSecret(
        llm_type="openai",
        api_key="uditpandey",
        models=["gpt-3.5-turbo"],
        bot=bot,
        user=user
    )
    llm_secret.save()
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
                                     "initial_value": "637f1b92df3b90588a30073e",
                                     "influence_conversation": True},
                             "kairon_action_response": {"type": "rasa.shared.core.slots.AnySlot",
                                                        "initial_value": None,
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

    response = client.post("/webhook", json=request_object)
    response_json = response.json()
    assert response_json['events'] == [
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
         'value': {'response': 'utter_greet'}}]
    assert response_json['responses'] == [
        {'text': None, 'buttons': [], 'elements': [], 'custom': {}, 'template': 'utter_greet',
         'response': 'utter_greet', 'image': None, 'attachment': None}
    ]
    assert len(responses.calls._calls) == 2


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
                                     "initial_value": "637f1b92df3b90588a30073e",
                                     "influence_conversation": True},
                             "kairon_action_response": {"type": "rasa.shared.core.slots.AnySlot",
                                                        "initial_value": None,
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

    with mock.patch.object(ActionUtility, "trigger_rephrase") as mock_utils:
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

    with mock.patch('kairon.actions.handlers.action.ActionHandler.process_actions', mock_process_actions):
        response = client.post("/webhook", json=request_object)
        response_json = response.json()
        assert response_json == {'error': "Custom action 'Action Execution Rejection' rejected execution.",
                                 'action_name': 'Action Execution Rejection'}

    async def mock_process_actions(*args, **kwargs):
        from rasa_sdk.interfaces import ActionNotFoundException
        raise ActionNotFoundException("Action Not Found Exception")

    with mock.patch('kairon.actions.handlers.action.ActionHandler.process_actions', mock_process_actions):
        response = client.post("/webhook", json=request_object)
        response_json = response.json()
        assert response_json == {'error': "No registered action found for name 'Action Not Found Exception'.",
                                 'action_name': 'Action Not Found Exception'}


@mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
def test_prompt_action_response_action_with_prompt_question_from_slot(mock_get_embedding, aioresponses):
    from uuid6 import uuid7

    llm_type = "openai"

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
         'type': 'user', 'source': 'bot_content', 'data': 'python',
         'hyperparameters': {"top_results": 10, "similarity_threshold": 0.70},
         'is_enabled': True}
    ]

    text_embedding_3_small_embeddings = np.random.random(1536).tolist()
    colbertv2_0_embeddings = [np.random.random(128).tolist()]
    bm25_embeddings = {
        "indices": [1850593538, 11711171],
        "values": [1.66, 1.66]
    }

    embeddings = {
        "dense": text_embedding_3_small_embeddings,
        "rerank": colbertv2_0_embeddings,
        "sparse": bm25_embeddings,
    }

    mock_get_embedding.return_value = embeddings

    expected_body = {'messages': [
        {'role': 'system', 'content': 'You are a personal assistant. Answer question based on the context below.\n'},
        {'role': 'user', 'content': 'hello'}, {'role': 'assistant', 'content': 'how are you'}, {'role': 'user',
                                                                                                'content': "\nInstructions on how to use Similarity Prompt:\n['Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.']\nAnswer question based on the context above, if answer is not in the context go check previous logs.\n \nQ: What kind of language is python? \nA:"}],
        'metadata': {'user': 'udit.pandey', 'bot': '5f50fd0a56b698ca10d35d2l', 'invocation': 'prompt_action'},
        'api_key': 'keyvalue',
        'num_retries': 3, 'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-4o-mini', 'top_p': 0.0, 'n': 1,
        'stop': None, 'presence_penalty': 0.0, 'frequency_penalty': 0.0, 'logit_bias': {}}

    aioresponses.add(
        url=urljoin(Utility.environment['llm']['url'],
                    f"/{bot}/completion/{llm_type}"),
        method="POST",
        status=200,
        payload={'formatted_response': generated_text, 'response': generated_text},
        body=json.dumps(expected_body)
    )

    aioresponses.add(
        url=urljoin(Utility.environment['vector']['db'],
                    f"/collections/{bot}_python_faq_embd/points/query"),
        method="POST",
        payload={
            "result": {
                "points": [
                    {
                        "id": uuid7().__str__(),
                        "version": 0,
                        "score": 0.80,
                        "payload": {
                            "content": bot_content
                        }
                    }
                ]
            },
            "status": "ok",
            "time": 0.000957728
        }
    )

    Actions(name=action_name, type=ActionType.prompt_action.value, bot=bot, user=user).save()
    BotSettings(llm_settings=LLMSettings(enable_faq=True), bot=bot, user=user).save()
    PromptAction(name=action_name, bot=bot, user=user, num_bot_responses=2, llm_prompts=llm_prompts,
                 user_question=UserQuestion(type="from_slot", value="prompt_question")).save()
    llm_secret = LLMSecret(
        llm_type=llm_type,
        api_key=value,
        models=["gpt-3.5-turbo", "gpt-4o-mini"],
        bot=bot,
        user=user
    )
    llm_secret.save()

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


@mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
@mock.patch.object(ActionUtility, 'execute_request_async', autospec=True)
def test_prompt_action_response_action_with_prompt_question_from_slot_perplexity(mock_execute_request_async, mock_get_embedding, aioresponses):
    from uuid6 import uuid7
    llm_type = "perplexity"
    action_name = "test_prompt_action_response_action_with_prompt_question_from_slot"
    bot = "5f50fd0a56b69s8ca10d35d2l"
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
         'type': 'user', 'source': 'bot_content', 'data': 'python',
         'hyperparameters': {"top_results": 10, "similarity_threshold": 0.70},
         'is_enabled': True}
    ]
    mock_execute_request_async.return_value = (
        {
            'formatted_response': 'Python is dynamically typed, garbage-collected, high level, general purpose programming.',
            'response': 'Python is dynamically typed, garbage-collected, high level, general purpose programming.'},
        200,
        mock.ANY,
        mock.ANY
    )
    text_embedding_3_small_embeddings = np.random.random(1536).tolist()
    colbertv2_0_embeddings = [np.random.random(128).tolist()]
    bm25_embeddings = {
        "indices": [1850593538, 11711171],
        "values": [1.66, 1.66]
    }

    embeddings = {
        "dense": text_embedding_3_small_embeddings,
        "rerank": colbertv2_0_embeddings,
        "sparse": bm25_embeddings,
    }

    mock_get_embedding.return_value = embeddings
    expected_body = {'messages': [
        {'role': 'system', 'content': 'You are a personal assistant. Answer question based on the context below.\n'},
        {'role': 'user', 'content': 'hello'}, {'role': 'assistant', 'content': 'how are you'}, {'role': 'user',
                                                                                                'content': "\nInstructions on how to use Similarity Prompt:\n['Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.']\nAnswer question based on the context above, if answer is not in the context go check previous logs.\n \nQ: What kind of language is python? \nA:"}],
        'metadata': {'user': 'udit.pandey', 'bot': '5f50fd0a56b698ca10d35d2l', 'invocation': 'prompt_action'},
        'api_key': 'keyvalue',
        'num_retries': 3, 'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-4o-mini', 'top_p': 0.0, 'n': 1,
        'stop': None, 'presence_penalty': 0.0, 'frequency_penalty': 0.0, 'logit_bias': {}}
    aioresponses.add(
        url=urljoin(Utility.environment['llm']['url'],
                    f"/{bot}/completion/{llm_type}"),
        method="POST",
        status=200,
        payload={'formatted_response': generated_text, 'response': generated_text},
        body=json.dumps(expected_body)
    )

    aioresponses.add(
        url=urljoin(Utility.environment['vector']['db'],
                    f"/collections/{bot}_python_faq_embd/points/query"),
        method="POST",
        payload={
            "result": {
                "points": [
                    {
                        "id": uuid7().__str__(),
                        "version": 0,
                        "score": 0.80,
                        "payload": {
                            "content": bot_content
                        }
                    }
                ]
            },
            "status": "ok",
            "time": 0.000957728
        }
    )
    hyperparameters = Utility.get_llm_hyperparameters("perplexity")
    hyperparameters['search_domain_filter'] = ["domain1.com", "domain2.com"]
    Actions(name=action_name, type=ActionType.prompt_action.value, bot=bot, user=user).save()
    BotSettings(llm_settings=LLMSettings(enable_faq=True), bot=bot, user=user).save()
    PromptAction(name=action_name, bot=bot, user=user, num_bot_responses=2, llm_prompts=llm_prompts, llm_type="perplexity", hyperparameters = hyperparameters,
                 user_question=UserQuestion(type="from_slot", value="prompt_question")).save()
    llm_secret = LLMSecret(
        llm_type=llm_type,
        api_key=value,
        models=["perplexity/llama-3.1-sonar-small-128k-online", "perplexity/llama-3.1-sonar-large-128k-online", "perplexity/llama-3.1-sonar-huge-128k-online"],
        bot=bot,
        user=user
    )
    llm_secret.save()
    llm_secret = LLMSecret(
        llm_type="openai",
        api_key="api_key",
        models=["gpt-3.5-turbo", "gpt-4o-mini"],
        bot=bot,
        user=user
    )
    llm_secret.save()
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
    mock_execute_request_async.assert_called_once_with(
        http_url=f"{Utility.environment['llm']['url']}/{urllib.parse.quote(bot)}/completion/{llm_type}",
        request_method="POST",
        request_body={
            'messages': [{'role': 'system', 'content': 'You are a personal assistant. Answer question based on the context below.\n'},
                         {'role': 'user', 'content': 'hello'},
                         {'role': 'assistant', 'content': 'how are you'},
                         {'role': 'user', 'content': "\nInstructions on how to use Similarity Prompt:\n['Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.']\nAnswer question based on the context above, if answer is not in the context go check previous logs.\n \nQ: What kind of language is python? inurl:domain1.com|domain2.com \nA:"}],
            'hyperparameters': hyperparameters,
            'user': user,
            'invocation': "prompt_action"
        },
        timeout=Utility.environment['llm'].get('request_timeout', 30)
    )
    called_args = mock_execute_request_async.call_args
    user_message = called_args.kwargs['request_body']['messages'][-1]['content']
    assert "inurl:domain1.com|domain2.com" in user_message
    assert response_json['events'] == [
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response', 'value': generated_text}]
    assert response_json['responses'] == [
        {'text': generated_text, 'buttons': [], 'elements': [], 'custom': {}, 'template': None,
         'response': None, 'image': None, 'attachment': None}
    ]

@mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
def test_prompt_action_response_action_with_prompt_question_from_slot_different_embedding_completion(mock_get_embedding, aioresponses):
    from uuid6 import uuid7

    llm_type = "anthropic"
    action_name = "test_prompt_action_response_action_with_prompt_question_from_slot_different_embedding_completion"
    bot = "5f50fd0a56b698ca10d35d2D"
    user = "udit.pandey"
    value = "keyvalue"
    user_msg = "What kind of language is python?"
    bot_content = "Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected."
    generated_text = "Python is dynamically typed, garbage-collected, high level, general purpose programming."
    hyperparameters = Utility.get_default_llm_hyperparameters()

    llm_prompts = [
        {'name': 'System Prompt',
         'data': 'You are a personal assistant. Answer question based on the context below.',
         'type': 'system', 'source': 'static', 'is_enabled': True},
        {'name': 'History Prompt', 'type': 'user', 'source': 'history', 'is_enabled': True},
        {'name': 'Query Prompt', 'data': "What kind of language is python?", 'instructions': 'Rephrase the query.',
         'type': 'query', 'source': 'static', 'is_enabled': False},
        {'name': 'Similarity Prompt',
         'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
         'type': 'user', 'source': 'bot_content', 'data': 'python',
         'hyperparameters': {"top_results": 10, "similarity_threshold": 0.70},
         'is_enabled': True}
    ]

    text_embedding_3_small_embeddings = np.random.random(1536).tolist()
    colbertv2_0_embeddings = [np.random.random(128).tolist()]
    bm25_embeddings = {
        "indices": [1850593538, 11711171],
        "values": [1.66, 1.66]
    }

    embeddings = {
        "dense": text_embedding_3_small_embeddings,
        "rerank": colbertv2_0_embeddings,
        "sparse": bm25_embeddings,
    }

    mock_get_embedding.return_value = embeddings
    expected_body = {'messages': [{'role': 'system', 'content': 'You are a personal assistant.\n'}, {'role': 'user',
                                                                                                     'content': "\nInstructions on how to use Similarity Prompt:\n['Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.']\nAnswer question based on the context above.\n\nInstructions on how to use Data science prompt:\n['Data science is a multidisciplinary field that uses scientific methods, processes, algorithms, and systems to extract insights and knowledge from structured and unstructured data.']\nAnswer question based on the context above.\n \nQ: What kind of language is python? \nA:"}],
                     "hyperparameters": hyperparameters,
                     'user': user,
                     'invocation': 'prompt_action'
                     }

    aioresponses.add(
        url=urljoin(Utility.environment['llm']['url'],
                    f"/{bot}/completion/{llm_type}"),
        method="POST",
        status=200,
        payload={'formatted_response': generated_text,
                 'response': {'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}},
        body=expected_body,
        repeat=True
    )


    aioresponses.add(
        url=urljoin(Utility.environment['vector']['db'],
                    f"/collections/{bot}_python_faq_embd/points/query"),
        method="POST",
        payload={
            "result": {
                "points": [
                    {
                        "id": uuid7().__str__(),
                        "version": 0,
                        "score": 0.80,
                        "payload": {
                            "content": bot_content
                        }
                    }
                ]
            },
            "status": "ok",
            "time": 0.000957728
        }
    )
    Actions(name=action_name, type=ActionType.prompt_action.value, bot=bot, user=user).save()
    BotSettings(llm_settings=LLMSettings(enable_faq=True), bot=bot, user=user).save()
    PromptAction(name=action_name,
                 llm_type="anthropic",
                 hyperparameters=Utility.get_llm_hyperparameters("anthropic"),
                 bot=bot, user=user, num_bot_responses=2, llm_prompts=llm_prompts,
                 user_question=UserQuestion(type="from_slot", value="prompt_question")).save()
    llm_secret = LLMSecret(
        llm_type="openai",
        api_key=value,
        models=["gpt-3.5-turbo", "gpt-4o-mini"],
        bot=bot,
        user=user
    )
    llm_secret.save()

    llm_secret = LLMSecret(
        llm_type="anthropic",
        api_key=value,
        models=["claude-3-sonnet-20240229", "claude-3-haiku-20240307"],
        bot=bot,
        user=user
    )
    llm_secret.save()

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


@mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
def test_prompt_action_response_action_with_bot_responses(mock_get_embedding, aioresponses):
    from uuid6 import uuid7

    llm_type = "openai"
    action_name = "test_prompt_action"
    bot = "5f50fd0a56b698ca10d35d2k"
    user = "udit.pandey"
    value = "keyvalue"
    user_msg = "What kind of language is python?"
    bot_content = "Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected."
    generated_text = "Python is dynamically typed, garbage-collected, high level, general purpose programming."
    hyperparameters = Utility.get_default_llm_hyperparameters()

    llm_prompts = [
        {'name': 'System Prompt',
         'data': 'You are a personal assistant. Answer question based on the context below.',
         'type': 'system', 'source': 'static', 'is_enabled': True},
        {'name': 'History Prompt', 'type': 'user', 'source': 'history', 'is_enabled': True},
        {'name': 'Query Prompt', 'data': "What kind of language is python?", 'instructions': 'Rephrase the query.',
         'type': 'query', 'source': 'static', 'is_enabled': False},
        {'name': 'Similarity Prompt',
         'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
         'type': 'user', 'source': 'bot_content', 'data': 'python',
         'hyperparameters': {"top_results": 10, "similarity_threshold": 0.70},
         'is_enabled': True}
    ]

    text_embedding_3_small_embeddings = np.random.random(1536).tolist()
    colbertv2_0_embeddings = [np.random.random(128).tolist()]
    bm25_embeddings = {
        "indices": [1850593538, 11711171],
        "values": [1.66, 1.66]
    }

    embeddings = {
        "dense": text_embedding_3_small_embeddings,
        "rerank": colbertv2_0_embeddings,
        "sparse": bm25_embeddings,
    }

    mock_get_embedding.return_value = embeddings
    expected_body = {'messages': [
        {'role': 'system', 'content': 'You are a personal assistant. Answer question based on the context below.\n'},
        {'role': 'user', 'content': 'hello'}, {'role': 'assistant', 'content': 'how are you'}, {'role': 'user',
                                                                                                'content': "\nInstructions on how to use Similarity Prompt:\n['Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.']\nAnswer question based on the context above, if answer is not in the context go check previous logs.\n \nQ: What kind of language is python? \nA:"}],
                     "hyperparameters": hyperparameters,
                     'user': user,
                     'invocation': 'prompt_action'
                     }

    aioresponses.add(
        url=urljoin(Utility.environment['llm']['url'],
                    f"/{bot}/completion/{llm_type}"),
        method="POST",
        status=200,
        payload={'formatted_response': generated_text,
                 'response': {'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}},
        body=expected_body
    )

    aioresponses.add(
        url=urljoin(Utility.environment['vector']['db'],
                    f"/collections/{bot}_python_faq_embd/points/query"),
        method="POST",
        payload={
            "result": {
                "points": [
                    {
                        "id": uuid7().__str__(),
                        "version": 0,
                        "score": 0.80,
                        "payload": {
                            "content": bot_content
                        }
                    }
                ]
            },
            "status": "ok",
            "time": 0.000957728
        }
    )
    Actions(name=action_name, type=ActionType.prompt_action.value, bot=bot, user=user).save()
    BotSettings(llm_settings=LLMSettings(enable_faq=True), bot=bot, user=user).save()
    PromptAction(name=action_name, bot=bot, user=user, num_bot_responses=2, llm_prompts=llm_prompts).save()
    llm_secret = LLMSecret(
        llm_type="openai",
        api_key=value,
        models=["gpt-3.5-turbo", "gpt-4o-mini"],
        bot=bot,
        user=user
    )
    llm_secret.save()
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


@mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
def test_prompt_action_response_action_with_bot_responses_with_instructions(mock_get_embedding,
                                                                            aioresponses):
    from uuid6 import uuid7

    llm_type = "openai"
    action_name = "test_prompt_action_with_bot_responses_with_instructions"
    bot = "5f50fd0a56b678ca10d35d2k"
    user = "udit.pandey"
    value = "keyvalue"
    user_msg = "What kind of language is python?"
    bot_content = "Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected."
    generated_text = "Python is dynamically typed, garbage-collected, high level, general purpose programming."
    instructions = ['Answer in a short way.', 'Keep it simple.']
    hyperparameters = Utility.get_default_llm_hyperparameters()

    llm_prompts = [
        {'name': 'System Prompt',
         'data': 'You are a personal assistant. Answer question based on the context below.',
         'type': 'system', 'source': 'static', 'is_enabled': True},
        {'name': 'History Prompt', 'type': 'user', 'source': 'history', 'is_enabled': True},
        {'name': 'Query Prompt', 'data': "What kind of language is python?", 'instructions': 'Rephrase the query.',
         'type': 'query', 'source': 'static', 'is_enabled': False},
        {'name': 'Similarity Prompt',
         'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
         'type': 'user', 'source': 'bot_content', 'data': 'python',
         'hyperparameters': {"top_results": 10, "similarity_threshold": 0.70},
         'is_enabled': True}
    ]
    text_embedding_3_small_embeddings = np.random.random(1536).tolist()
    colbertv2_0_embeddings = [np.random.random(128).tolist()]
    bm25_embeddings = {
        "indices": [1850593538, 11711171],
        "values": [1.66, 1.66]
    }

    embeddings = {
        "dense": text_embedding_3_small_embeddings,
        "rerank": colbertv2_0_embeddings,
        "sparse": bm25_embeddings,
    }

    mock_get_embedding.return_value = embeddings

    expected_body = {'messages': [
        {'role': 'system', 'content': 'You are a personal assistant. Answer question based on the context below.\n'},
        {'role': 'user', 'content': 'hello'}, {'role': 'assistant', 'content': 'how are you'}, {'role': 'user',
                                                                                                'content': "\nInstructions on how to use Similarity Prompt:\n['Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.']\nAnswer question based on the context above, if answer is not in the context go check previous logs.\n \nAnswer in a short way.\nKeep it simple. \nQ: What kind of language is python? \nA:"}],
                     "hyperparameters": hyperparameters,
                     'user': user,
                     'invocation': 'prompt_action'
                     }

    aioresponses.add(
        url=urljoin(Utility.environment['llm']['url'],
                    f"/{bot}/completion/{llm_type}"),
        method="POST",
        status=200,
        payload={'formatted_response': generated_text,
                 'response': {'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}},
        body=expected_body
    )

    aioresponses.add(
        url=urljoin(Utility.environment['vector']['db'],
                    f"/collections/{bot}_python_faq_embd/points/query"),
        method="POST",
        payload={
            "result": {
                "points": [
                    {
                        "id": uuid7().__str__(),
                        "version": 0,
                        "score": 0.80,
                        "payload": {
                            "content": bot_content
                        }
                    }
                ]
            },
            "status": "ok",
            "time": 0.000957728
        }
    )

    Actions(name=action_name, type=ActionType.prompt_action.value, bot=bot, user=user).save()
    BotSettings(llm_settings=LLMSettings(enable_faq=True), bot=bot, user=user).save()
    PromptAction(name=action_name, bot=bot, user=user, num_bot_responses=2, llm_prompts=llm_prompts,
                 instructions=instructions).save()
    llm_secret = LLMSecret(
        llm_type="openai",
        api_key=value,
        models=["gpt-3.5-turbo", "gpt-4o-mini"],
        bot=bot,
        user=user
    )
    llm_secret.save()

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


@mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
def test_prompt_action_response_action_with_query_prompt(mock_get_embedding, aioresponses):
    from uuid6 import uuid7

    llm_type = "openai"
    action_name = "test_prompt_action_response_action_with_query_prompt"
    bot = "5f50fd0a56b698ca10d35d2s"
    user = "udit.pandey"
    value = "keyvalue"
    user_msg = "What kind of language is python?"
    bot_content = "Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected."
    generated_text = "Python is dynamically typed, garbage-collected, high level, general purpose programming."
    rephrased_query = "Explain python is called high level programming language in laymen terms?"
    hyperparameters = Utility.get_default_llm_hyperparameters()

    llm_prompts = [
        {'name': 'System Prompt',
         'data': 'You are a personal assistant. Answer question based on the context below.',
         'type': 'system', 'source': 'static', 'is_enabled': True},
        {'name': 'Similarity Prompt',
         'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
         'type': 'user', 'source': 'bot_content', 'is_enabled': True,
         'data': 'python', 'hyperparameters': {"top_results": 10, "similarity_threshold": 0.70}},
        {'name': 'Query Prompt',
         'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
         'instructions': 'Answer according to the context', 'type': 'query', 'source': 'static',
         'is_enabled': True},
        {'name': 'Query Prompt',
         'data': 'If there is no specific query, assume that user is asking about java programming.',
         'instructions': 'Answer according to the context', 'type': 'query', 'source': 'static', 'is_enabled': True}
    ]

    expected_body = {'messages': [{'role': 'system', 'content': 'You are a personal assistant.\n'}, {'role': 'user',
                                                                                                     'content': "\nInstructions on how to use Similarity Prompt:\n['Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.']\nAnswer question based on the context above.\n\nInstructions on how to use Data science prompt:\n['Data science is a multidisciplinary field that uses scientific methods, processes, algorithms, and systems to extract insights and knowledge from structured and unstructured data.']\nAnswer question based on the context above.\n \nQ: What kind of language is python? \nA:"}],
                     "hyperparameters": hyperparameters,
                     'user': user,
                     'invocation': 'prompt_action'
                     }

    aioresponses.add(
        url=urljoin(Utility.environment['llm']['url'],
                    f"/{bot}/completion/{llm_type}"),
        method="POST",
        status=200,
        payload={'formatted_response': generated_text,
                 'response': {'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}},
        body=expected_body,
        repeat=True
    )

    text_embedding_3_small_embeddings = np.random.random(1536).tolist()
    colbertv2_0_embeddings = [np.random.random(128).tolist()]
    bm25_embeddings = {
        "indices": [1850593538, 11711171],
        "values": [1.66, 1.66]
    }

    embeddings = {
        "dense": text_embedding_3_small_embeddings,
        "rerank": colbertv2_0_embeddings,
        "sparse": bm25_embeddings,
    }

    mock_get_embedding.return_value = embeddings

    aioresponses.add(
        url=urljoin(Utility.environment['vector']['db'],
                    f"/collections/{bot}_python_faq_embd/points/query"),
        method="POST",
        payload={
            "result": {
                "points": [
                    {
                        "id": uuid7().__str__(),
                        "version": 0,
                        "score": 0.80,
                        "payload": {
                            "content": bot_content
                        }
                    }
                ]
            },
            "status": "ok",
            "time": 0.000957728
        }
    )
    Actions(name=action_name, type=ActionType.prompt_action.value, bot=bot, user=user).save()
    BotSettings(llm_settings=LLMSettings(enable_faq=True), bot=bot, user=user).save()
    PromptAction(name=action_name, bot=bot, user=user, llm_prompts=llm_prompts).save()
    llm_secret = LLMSecret(
        llm_type="openai",
        api_key=value,
        models=["gpt-3.5-turbo", "gpt-4o-mini"],
        bot=bot,
        user=user
    )
    llm_secret.save()

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


@mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
def test_prompt_response_action(mock_get_embedding, aioresponses):
    from uuid6 import uuid7

    llm_type = "openai"
    action_name = GPT_LLM_FAQ
    bot = "5f50fd0a56b698ca10d35d2e"
    user = "udit.pandey"
    value = "keyvalue"
    user_msg = "What kind of language is python?"
    bot_content = "Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected."
    generated_text = "Python is dynamically typed, garbage-collected, high level, general purpose programming."
    bot_content_two = "Data science is a multidisciplinary field that uses scientific methods, processes, algorithms, and systems to extract insights and knowledge from structured and unstructured data."
    hyperparameters = Utility.get_default_llm_hyperparameters()

    llm_prompts = [
        {'name': 'System Prompt', 'data': 'You are a personal assistant.',
         'instructions': 'Answer question based on the context below.', 'type': 'system', 'source': 'static'},
        {'name': 'Similarity Prompt',
         'instructions': 'Answer question based on the context above.', 'type': 'user', 'source': 'bot_content',
         'data': 'python',
         'hyperparameters': {"top_results": 10, "similarity_threshold": 0.70},
         'is_enabled': True
         },
        {'name': 'Data science prompt',
         'instructions': 'Answer question based on the context above.', 'type': 'user', 'source': 'bot_content',
         'data': 'data_science'},
    ]
    aioresponses.add(
        url=urljoin(Utility.environment['vector']['db'],
                    f"/collections/5f50fd0a56b698ca10d35d2e_python_faq_embd/points/query"),
        method="POST",
        payload={
            "result": {
                "points": [
                    {
                        "id": uuid7().__str__(),
                        "version": 0,
                        "score": 0.80,
                        "payload": {
                            "content": bot_content
                        }
                    }
                ]
            },
            "status": "ok",
            "time": 0.000957728
        }
    )
    aioresponses.add(
        url=urljoin(Utility.environment['vector']['db'],
                    f"/collections/5f50fd0a56b698ca10d35d2e_data_science_faq_embd/points/query"),
        method="POST",
        payload={
            "result": {
                "points": [
                    {
                        "id": uuid7().__str__(),
                        "version": 0,
                        "score": 0.80,
                        "payload": {
                            "content": bot_content_two
                        }
                    }
                ]
            },
            "status": "ok",
            "time": 0.000957728
        }
    )
    text_embedding_3_small_embeddings = np.random.random(1536).tolist()
    colbertv2_0_embeddings = [np.random.random(128).tolist()]
    bm25_embeddings = {
        "indices": [1850593538, 11711171],
        "values": [1.66, 1.66]
    }

    embeddings = {
        "dense": text_embedding_3_small_embeddings,
        "rerank": colbertv2_0_embeddings,
        "sparse": bm25_embeddings,
    }

    mock_get_embedding.return_value = embeddings

    expected_body = {'messages': [{'role': 'system', 'content': 'You are a personal assistant.\n'}, {'role': 'user',
                                                                                                     'content': "\nInstructions on how to use Similarity Prompt:\n['Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.']\nAnswer question based on the context above.\n\nInstructions on how to use Data science prompt:\n['Data science is a multidisciplinary field that uses scientific methods, processes, algorithms, and systems to extract insights and knowledge from structured and unstructured data.']\nAnswer question based on the context above.\n \nQ: What kind of language is python? \nA:"}],
                     "hyperparameters": hyperparameters,
                     'user': user,
                     'invocation': 'prompt_action'
                     }

    aioresponses.add(
        url=urljoin(Utility.environment['llm']['url'],
                    f"/{bot}/completion/{llm_type}"),
        method="POST",
        status=200,
        payload={'formatted_response': generated_text,
                 'response': {'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}},
        body=expected_body
    )

    Actions(name=action_name, type=ActionType.prompt_action.value, bot=bot, user=user).save()
    PromptAction(name=action_name,
                 bot=bot,
                 user=user,
                 llm_prompts=llm_prompts).save()
    BotSettings(llm_settings=LLMSettings(enable_faq=True), bot=bot, user=user).save()
    llm_secret = LLMSecret(
        llm_type="openai",
        api_key=value,
        models=["gpt-3.5-turbo", "gpt-4o-mini"],
        bot=bot,
        user=user
    )
    llm_secret.save()

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


@mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
def test_prompt_response_action_with_instructions(mock_get_embedding, aioresponses):
    from uuid6 import uuid7

    llm_type = "openai"
    action_name = 'test_prompt_response_action_with_instructions'
    bot = "5f50fd0a56b690ca10d35d2e"
    user = "udit.pandey"
    value = "keyvalue"
    user_msg = "What kind of language is java?"
    bot_content = "Java is a high-level, object-oriented programming language. It was developed by Sun Microsystems (later acquired by Oracle Corporation) and released in 1995. "
    generated_text = "Java is a high-level, object-oriented programming language. "
    instructions = ['Answer in a short way.', 'Keep it simple.']
    hyperparameters = Utility.get_default_llm_hyperparameters()

    llm_prompts = [
        {'name': 'System Prompt', 'data': 'You are a personal assistant.',
         'instructions': 'Answer question based on the context below.', 'type': 'system', 'source': 'static'},
        {'name': 'Similarity Prompt',
         'instructions': 'Answer question based on the context above.', 'type': 'user', 'source': 'bot_content',
         'data': 'python',
         'hyperparameters': {"top_results": 10, "similarity_threshold": 0.70},
         'is_enabled': True
         }
    ]
    text_embedding_3_small_embeddings = np.random.random(1536).tolist()
    colbertv2_0_embeddings = [np.random.random(128).tolist()]
    bm25_embeddings = {
        "indices": [1850593538, 11711171],
        "values": [1.66, 1.66]
    }

    embeddings = {
        "dense": text_embedding_3_small_embeddings,
        "rerank": colbertv2_0_embeddings,
        "sparse": bm25_embeddings,
    }

    mock_get_embedding.return_value = embeddings

    expected_body = {'messages': [{'role': 'system', 'content': 'You are a personal assistant.\n'}, {'role': 'user', 'content': "\nInstructions on how to use Similarity Prompt:\n['Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.']\nAnswer question based on the context above.\n\nInstructions on how to use Data science prompt:\n['Data science is a multidisciplinary field that uses scientific methods, processes, algorithms, and systems to extract insights and knowledge from structured and unstructured data.']\nAnswer question based on the context above.\n \nQ: What kind of language is python? \nA:"}],
        "hyperparameters": hyperparameters,
        'user': user,
        'invocation': 'prompt_action'
    }

    aioresponses.add(
        url=urljoin(Utility.environment['llm']['url'],
                    f"/{bot}/completion/{llm_type}"),
        method="POST",
        status=200,
        payload={'formatted_response': generated_text,
                 'response': {'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}},
        body=expected_body,
    )

    aioresponses.add(
        url=urljoin(Utility.environment['vector']['db'],
                    f"/collections/{bot}_python_faq_embd/points/query"),
        method="POST",
        payload={
            "result": {
                "points": [
                    {
                        "id": uuid7().__str__(),
                        "version": 0,
                        "score": 0.80,
                        "payload": {
                            "content": bot_content
                        }
                    }
                ]
            },
            "status": "ok",
            "time": 0.000957728
        }
    )

    Actions(name=action_name, type=ActionType.prompt_action.value, bot=bot, user=user).save()
    PromptAction(name=action_name, bot=bot, user=user, llm_prompts=llm_prompts, instructions=instructions).save()
    BotSettings(llm_settings=LLMSettings(enable_faq=True), bot=bot, user=user).save()
    llm_secret = LLMSecret(
        llm_type="openai",
        api_key=value,
        models=["gpt-3.5-turbo", "gpt-4o-mini"],
        bot=bot,
        user=user
    )
    llm_secret.save()

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


@mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
def test_prompt_response_action_streaming_enabled(mock_get_embedding, aioresponses):
    from uuid6 import uuid7

    llm_type = "openai"
    action_name = GPT_LLM_FAQ
    bot = "5f50k90a56b698ca10d35d2e"
    user = "udit.pandeyy"
    value = "keyvalue"
    user_msg = "What kind of language is python?"
    bot_content = "Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected."
    generated_text = "Python is dynamically typed, garbage-collected, high level, general purpose programming."
    hyperparameters = {'temperature': 0.0, 'max_tokens': 300,
                       'model': 'gpt-4o-mini', 'top_p': 0.0, 'n': 1,
                       'stream': True,
                       'stop': None,
                       'presence_penalty': 0.0,
                       'frequency_penalty': 0.0, 'logit_bias': {}}

    llm_prompts = [
        {'name': 'System Prompt', 'data': 'You are a personal assistant.',
         'instructions': 'Answer question based on the context below.', 'type': 'system', 'source': 'static'},
        {'name': 'Similarity Prompt',
         'instructions': 'Answer question based on the context above.', 'type': 'user', 'source': 'bot_content',
         'data': 'python',
         'hyperparameters': {"top_results": 10, "similarity_threshold": 0.70},
         'is_enabled': True
         }
    ]

    text_embedding_3_small_embeddings = np.random.random(1536).tolist()
    colbertv2_0_embeddings = [np.random.random(128).tolist()]
    bm25_embeddings = {
        "indices": [1850593538, 11711171],
        "values": [1.66, 1.66]
    }

    embeddings = {
        "dense": text_embedding_3_small_embeddings,
        "rerank": colbertv2_0_embeddings,
        "sparse": bm25_embeddings,
    }

    mock_get_embedding.return_value = embeddings

    expected_body = {'messages': [{'role': 'system', 'content': 'You are a personal assistant.\n'},
                                  {'role': 'user', 'content': "\nInstructions on how to use Similarity Prompt:\n['Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.']\nAnswer question based on the context above.\n \nQ: What kind of language is python? \nA:"}],
        "hyperparameters": hyperparameters,
        'user': user,
        'invocation': 'prompt_action'
    }

    aioresponses.add(
        url=urljoin(Utility.environment['llm']['url'],
                    f"/{bot}/completion/{llm_type}"),
        method="POST",
        status=200,
        payload={'formatted_response': generated_text,
                 'response': {'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}},
        body=expected_body
    )

    aioresponses.add(
        url=urljoin(Utility.environment['vector']['db'],
                    f"/collections/{bot}_python_faq_embd/points/query"),
        method="POST",
        payload={
            "result": {
                "points": [
                    {
                        "id": uuid7().__str__(),
                        "version": 0,
                        "score": 0.80,
                        "payload": {
                            "content": bot_content
                        }
                    }
                ]
            },
            "status": "ok",
            "time": 0.000957728
        }
    )

    Actions(name=action_name, type=ActionType.prompt_action.value, bot=bot, user=user).save()
    BotSettings(llm_settings=LLMSettings(enable_faq=True), bot=bot, user=user).save()
    PromptAction(name=action_name, bot=bot, user=user, hyperparameters=hyperparameters, llm_prompts=llm_prompts).save()
    llm_secret = LLMSecret(
        llm_type="openai",
        api_key=value,
        models=["gpt-3.5-turbo", "gpt-4o-mini"],
        bot=bot,
        user=user
    )
    llm_secret.save()

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


@mock.patch("kairon.shared.rest_client.AioRestClient.request", autospec=True)
def test_prompt_response_action_failure(mock_search):
    from uuid6 import uuid7

    action_name = GPT_LLM_FAQ
    bot = "5f50fd0a56b698ca10d35d2ef"
    user = "udit.pandey"
    user_msg = "What kind of language is python?"
    bot_content = "Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected."
    generated_text = "I don't know."
    embedding = list(np.random.random(OPENAI_EMBEDDING_OUTPUT))
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


@mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
def test_prompt_action_response_action_with_static_user_prompt(mock_get_embedding, aioresponses):
    from uuid6 import uuid7

    llm_type = "openai"
    action_name = "kairon_faq_action"
    bot = "5u80fd0a56b698ca10d35d2s"
    user = "udit.pandey"
    value = "keyvalue"
    user_msg = "What kind of language is python?"
    bot_content = "Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected."
    generated_text = "Python is dynamically typed, garbage-collected, high level, general purpose programming."
    hyperparameters = Utility.get_default_llm_hyperparameters()

    llm_prompts = [
        {'name': 'System Prompt',
         'data': 'You are a personal assistant. Answer question based on the context below.',
         'type': 'system', 'source': 'static', 'is_enabled': True},
        {'name': 'Similarity Prompt',
         'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
         'type': 'user', 'source': 'bot_content', 'is_enabled': True, 'data': 'python',
         'hyperparameters': {"top_results": 10, "similarity_threshold": 0.70}},
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
        return litellm.ModelResponse(**{'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]})

    def __mock_search_cache(*args, **kwargs):
        return {'result': []}

    def __mock_fetch_similar(*args, **kwargs):
        return {'result': [{'id': uuid7().__str__(), 'score': 0.80, 'payload': {'content': bot_content}}]}

    def __mock_cache_result(*args, **kwargs):
        return {'result': []}

    text_embedding_3_small_embeddings = np.random.random(1536).tolist()
    colbertv2_0_embeddings = [np.random.random(128).tolist()]
    bm25_embeddings = {
        "indices": [1850593538, 11711171],
        "values": [1.66, 1.66]
    }

    embeddings = {
        "dense": text_embedding_3_small_embeddings,
        "rerank": colbertv2_0_embeddings,
        "sparse": bm25_embeddings,
    }

    mock_get_embedding.return_value = embeddings

    expected_body = {'messages': [
        {'role': 'system', 'content': 'You are a personal assistant. Answer question based on the context below.\n'},
        {'role': 'user', 'content': 'hello'}, {'role': 'assistant', 'content': 'how are you'},
        {'role': 'user', 'content': ' \nQ: What kind of language is python? \nA:'}],
        "hyperparameters": hyperparameters,
        'user': user,
        'invocation': 'prompt_action'
    }

    aioresponses.add(
        url=urljoin(Utility.environment['llm']['url'],
                    f"/{bot}/completion/{llm_type}"),
        method="POST",
        status=200,
        payload={'formatted_response': generated_text,
                 'response': {'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}},
        body=expected_body
    )

    aioresponses.add(
        url=urljoin(Utility.environment['vector']['db'],
                    f"/collections/{bot}_python_faq_embd/points/query"),
        method="POST",
        payload={
            "result": {
                "points": [
                    {
                        "id": uuid7().__str__(),
                        "version": 0,
                        "score": 0.80,
                        "payload": {
                            "content": bot_content
                        }
                    }
                ]
            },
            "status": "ok",
            "time": 0.000957728
        }
    )

    Actions(name=action_name, type=ActionType.prompt_action.value, bot=bot, user=user).save()
    BotSettings(llm_settings=LLMSettings(enable_faq=True), bot=bot, user=user).save()
    PromptAction(name=action_name, bot=bot, user=user, llm_prompts=llm_prompts).save()
    llm_secret = LLMSecret(
        llm_type="openai",
        api_key=value,
        models=["gpt-3.5-turbo", "gpt-4o-mini"],
        bot=bot,
        user=user
    )
    llm_secret.save()

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
@mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
def test_prompt_action_response_action_with_action_prompt(mock_get_embedding, aioresponses):
    from uuid6 import uuid7

    llm_type = "openai"
    action_name = "kairon_faq_action"
    bot = "5u08kd0a56b698ca10d98e6s"
    user = "nupur.khare"
    value = "keyvalue"
    user_msg = "What kind of language is python?"
    bot_content = "Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected."
    generated_text = "Python is dynamically typed, garbage-collected, high level, general purpose programming."
    hyperparameters = Utility.get_default_llm_hyperparameters()

    text_embedding_3_small_embeddings = np.random.random(1536).tolist()
    colbertv2_0_embeddings = [np.random.random(128).tolist()]
    bm25_embeddings = {
        "indices": [1850593538, 11711171],
        "values": [1.66, 1.66]
    }

    embeddings = {
        "dense": text_embedding_3_small_embeddings,
        "rerank": colbertv2_0_embeddings,
        "sparse": bm25_embeddings,
    }

    mock_get_embedding.return_value = embeddings

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
        url=http_url + "?" + urlencode({"bot": "5u08kd0a56b698ca10d98e6s", "user": "1011", "tag": "from_bot",
                                        "name": "nupur", "contact": "9876543219"}),
        payload=resp_msg,
        status=200,
    )
    llm_prompts = [
        {'name': 'System Prompt', 'data': 'You are a personal assistant.',
         'instructions': 'Answer question based on the context below.', 'type': 'system', 'source': 'static',
         'is_enabled': True},
        {'name': 'Similarity Prompt',
         'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
         'type': 'user', 'source': 'bot_content', 'data': 'python', 'is_enabled': True,
         'hyperparameters': {"top_results": 10, "similarity_threshold": 0.70}},
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


    expected_body = {'messages': [{'role': 'system', 'content': 'You are a personal assistant.\n'},
                                  {'role': 'user', 'content': "Python Prompt:\nA programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.\nInstructions on how to use Python Prompt:\nAnswer according to the context\n\nJava Prompt:\nJava is a programming language and computing platform first released by Sun Microsystems in 1995.\nInstructions on how to use Java Prompt:\nAnswer according to the context\n\nAction Prompt:\nPython is a scripting language because it uses an interpreter to translate and run its code.\nInstructions on how to use Action Prompt:\nAnswer according to the context\n\n\nInstructions on how to use Similarity Prompt:\n['Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.']\nAnswer question based on the context above, if answer is not in the context go check previous logs.\n \nQ: What kind of language is python? \nA:"}],
        "hyperparameters": hyperparameters,
        'user': user,
        'invocation': 'prompt_action'
    }

    aioresponses.add(
        url=urljoin(Utility.environment['llm']['url'],
                    f"/{bot}/completion/{llm_type}"),
        method="POST",
        status=200,
        payload={'formatted_response': generated_text,
                 'response': {'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}},
        body=expected_body
    )

    aioresponses.add(
        url=urljoin(Utility.environment['vector']['db'],
                    f"/collections/{bot}_python_faq_embd/points/query"),
        method="POST",
        payload={
            "result": {
                "points": [
                    {
                        "id": uuid7().__str__(),
                        "version": 0,
                        "score": 0.80,
                        "payload": {
                            "content": bot_content
                        }
                    }
                ]
            },
            "status": "ok",
            "time": 0.000957728
        }
    )
    Actions(name=action_name, type=ActionType.prompt_action.value, bot=bot, user=user).save()
    BotSettings(llm_settings=LLMSettings(enable_faq=True), bot=bot, user=user).save()
    PromptAction(name=action_name, bot=bot, user=user, llm_prompts=llm_prompts).save()
    llm_secret = LLMSecret(
        llm_type="openai",
        api_key=value,
        models=["gpt-3.5-turbo", "gpt-4o-mini"],
        bot=bot,
        user=user
    )
    llm_secret.save()

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
    log = ActionServerLogs.objects(bot=bot, type=ActionType.prompt_action.value,
                                   status="SUCCESS").get().to_mongo().to_dict()
    expected = [{'messages': [{'role': 'system', 'content': 'You are a personal assistant.\n'}, {'role': 'user',
                                                                                                 'content': "Python Prompt:\nA programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.\nInstructions on how to use Python Prompt:\nAnswer according to the context\n\nJava Prompt:\nJava is a programming language and computing platform first released by Sun Microsystems in 1995.\nInstructions on how to use Java Prompt:\nAnswer according to the context\n\nAction Prompt:\nPython is a scripting language because it uses an interpreter to translate and run its code.\nInstructions on how to use Action Prompt:\nAnswer according to the context\n\n\nInstructions on how to use Similarity Prompt:\n['Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.']\nAnswer question based on the context above, if answer is not in the context go check previous logs.\n \nQ: What kind of language is python? \nA:"}],
                 'raw_completion_response': {'choices': [{'message': {
                     'content': 'Python is dynamically typed, garbage-collected, high level, general purpose programming.',
                     'role': 'assistant'}}]}, 'type': 'answer_query',
                 'hyperparameters': {'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-4o-mini', 'top_p': 0.0,
                                     'n': 1, 'stop': None, 'presence_penalty': 0.0,
                                     'frequency_penalty': 0.0, 'logit_bias': {}}}]
    excludedRegex = [
        r"['raw_completion_response']['id']",
        r"['raw_completion_response']['created']"
    ]
    assert not DeepDiff(log['llm_logs'][0], expected[0], ignore_order=True, exclude_regex_paths=excludedRegex)


@mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
@mock.patch.object(ActionUtility, "perform_google_search", autospec=True)
def test_kairon_faq_response_with_google_search_prompt(mock_google_search, mock_get_embedding, aioresponses):
    llm_type = "openai"
    action_name = "kairon_faq_action"
    google_action_name = "custom_search_action"
    bot = "5u08kd0a56b698ca10hgjgjkhgjks"
    value = "keyvalue"
    user_msg = "What is kanban"
    user = 'test_user'
    hyperparameters = Utility.get_default_llm_hyperparameters()
    text_embedding_3_small_embeddings = [np.random.random(1536).tolist()]
    colbertv2_0_embeddings = [[np.random.random(128).tolist()]]
    bm25_embeddings = [{
        "indices": [1850593538, 11711171],
        "values": [1.66, 1.66]
    }]

    embeddings = {
        "dense": text_embedding_3_small_embeddings,
        "rerank": colbertv2_0_embeddings,
        "sparse": bm25_embeddings,
    }

    mock_get_embedding.return_value = embeddings

    Actions(name=action_name, type=ActionType.prompt_action.value, bot=bot, user=user).save()
    Actions(name=google_action_name, type=ActionType.google_search_action.value, bot=bot, user='test_user').save()
    GoogleSearchAction(name=google_action_name, api_key=CustomActionRequestParameters(value='1234567890'),
                       search_engine_id='asdfg::123456', bot=bot, user=user, dispatch_response=False,
                       num_results=3,
                       set_slot="google_response").save()
    BotSettings(llm_settings=LLMSettings(enable_faq=True), bot=bot, user=user).save()
    llm_secret = LLMSecret(
        llm_type="openai",
        api_key=value,
        models=["gpt-3.5-turbo", "gpt-4o-mini"],
        bot=bot,
        user=user
    )
    llm_secret.save()
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

    expected_body = {'messages': [{'role': 'system', 'content': 'You are a personal assistant.\n'}, {'role': 'user',
                                                                                                'content': 'Google search Prompt:\nKanban visualizes both the process (the workflow) and the actual work passing through that process.\nTo know more, please visit: <a href = "https://www.digite.com/kanban/what-is-kanban/" target="_blank" >Kanban</a>\n\nKanban project management is one of the emerging PM methodologies, and the Kanban approach is suitable for every team and goal.\nTo know more, please visit: <a href = "https://www.digite.com/kanban/what-is-kanban-project-mgmt/" target="_blank" >Kanban Project management</a>\n\nKanban is a popular framework used to implement agile and DevOps software development.\nTo know more, please visit: <a href = "https://www.digite.com/kanban/what-is-kanban-agile/" target="_blank" >Kanban agile</a>\nInstructions on how to use Google search Prompt:\nAnswer according to the context\n\n \nQ: What is kanban \nA:'}],
        "hyperparameters": hyperparameters,
        'user': user,
        'invocation': 'prompt_action'
    }

    aioresponses.add(
        url=urljoin(Utility.environment['llm']['url'],
                    f"/{bot}/completion/{llm_type}"),
        method="POST",
        status=200,
        payload={'formatted_response': generated_text,
                 'response': {'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}},
        body=expected_body
    )

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
    log = ActionServerLogs.objects(bot=bot, type=ActionType.prompt_action.value,
                                   status="SUCCESS").get().to_mongo().to_dict()
    expected = [{'messages': [{'role': 'system', 'content': 'You are a personal assistant.\n'}, {'role': 'user',
                                                                                                 'content': 'Google search Prompt:\nKanban visualizes both the process (the workflow) and the actual work passing through that process.\nTo know more, please visit: <a href = "https://www.digite.com/kanban/what-is-kanban/" target="_blank" >Kanban</a>\n\nKanban project management is one of the emerging PM methodologies, and the Kanban approach is suitable for every team and goal.\nTo know more, please visit: <a href = "https://www.digite.com/kanban/what-is-kanban-project-mgmt/" target="_blank" >Kanban Project management</a>\n\nKanban is a popular framework used to implement agile and DevOps software development.\nTo know more, please visit: <a href = "https://www.digite.com/kanban/what-is-kanban-agile/" target="_blank" >Kanban agile</a>\nInstructions on how to use Google search Prompt:\nAnswer according to the context\n\n \nQ: What is kanban \nA:'}],
                 'raw_completion_response': {'choices': [{'message': {
                     'content': 'Kanban is a workflow management tool which visualizes both the process (the workflow) and the actual work passing through that process.',
                     'role': 'assistant'}}]}, 'type': 'answer_query',
                 'hyperparameters': {'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-4o-mini', 'top_p': 0.0,
                                     'n': 1, 'stop': None, 'presence_penalty': 0.0,
                                     'frequency_penalty': 0.0, 'logit_bias': {}}}]

    excludedRegex = [
        r"['raw_completion_response']['id']",
        r"['raw_completion_response']['created']"
    ]
    assert not DeepDiff(log['llm_logs'][0], expected[0], ignore_order=True, exclude_regex_paths=excludedRegex)


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


@mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
def test_prompt_action_dispatch_response_disabled(mock_get_embedding, aioresponses):
    from uuid6 import uuid7

    llm_type ="openai"
    action_name = "kairon_faq_action"
    bot = "5u80fd0a56c908ca10d35d2sjhj"
    user = "udit.pandey"
    value = "keyvalue"
    user_msg = "What is the name of prompt?"
    bot_content = "Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected."
    generated_text = "Python is dynamically typed, garbage-collected, high level, general purpose programming."
    hyperparameters = Utility.get_default_llm_hyperparameters()
    text_embedding_3_small_embeddings = np.random.random(1536).tolist()
    colbertv2_0_embeddings = [np.random.random(128).tolist()]
    bm25_embeddings = {
        "indices": [1850593538, 11711171],
        "values": [1.66, 1.66]
    }

    embeddings = {
        "dense": text_embedding_3_small_embeddings,
        "rerank": colbertv2_0_embeddings,
        "sparse": bm25_embeddings,
    }

    mock_get_embedding.return_value = embeddings

    llm_prompts = [
        {'name': 'System Prompt', 'data': 'You are a personal assistant.',
         'instructions': 'Answer question based on the context below.', 'type': 'system', 'source': 'static',
         'is_enabled': True},
        {'name': 'Similarity Prompt',
         'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
         'type': 'user', 'source': 'bot_content', 'data': 'python', 'is_enabled': True},
        {'name': 'Language Prompt',
         'data': 'type',
         'instructions': 'Answer according to the context', 'type': 'user', 'source': 'slot',
         'is_enabled': True},
    ]

    expected_body = {'messages': [{'role': 'system', 'content': 'You are a personal assistant.\n'}, {'role': 'user',
                                                                                                'content': "Language Prompt:\nPython is an interpreted, object-oriented, high-level programming language with dynamic semantics.\nInstructions on how to use Language Prompt:\nAnswer according to the context\n\n\nInstructions on how to use Similarity Prompt:\n['Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.']\nAnswer question based on the context above, if answer is not in the context go check previous logs.\n \nQ: What is the name of prompt? \nA:"}],
        "hyperparameters": hyperparameters,
        'user': user,
        'invocation': 'prompt_action'
    }

    aioresponses.add(
        url=urljoin(Utility.environment['llm']['url'],
                    f"/{bot}/completion/{llm_type}"),
        method="POST",
        status=200,
        payload={'formatted_response': generated_text,
                 'response': {'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}},
        body=expected_body
    )

    aioresponses.add(
        url=urljoin(Utility.environment['vector']['db'],
                    f"/collections/{bot}_python_faq_embd/points/query"),
        method="POST",
        payload={
            "result": {
                "points": [
                    {
                        "id": uuid7().__str__(),
                        "version": 0,
                        "score": 0.80,
                        "payload": {
                            "content": bot_content
                        }
                    }
                ]
            },
            "status": "ok",
            "time": 0.000957728
        }
    )

    Actions(name=action_name, type=ActionType.prompt_action.value, bot=bot, user=user).save()
    BotSettings(llm_settings=LLMSettings(enable_faq=True), bot=bot, user=user).save()
    PromptAction(name=action_name, bot=bot, user=user, llm_prompts=llm_prompts, dispatch_response=False).save()
    llm_secret = LLMSecret(
        llm_type="openai",
        api_key=value,
        models=["gpt-3.5-turbo", "gpt-4o-mini"],
        bot=bot,
        user=user
    )
    llm_secret.save()

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
    log = ActionServerLogs.objects(bot=bot, type=ActionType.prompt_action.value,
                                   status="SUCCESS").get().to_mongo().to_dict()
    assert isinstance(log['time_elapsed'], float) and log['time_elapsed'] > 0.0
    log.pop('_id')
    log.pop('timestamp')
    assert log["time_elapsed"]
    log.pop('time_elapsed')
    events = log.pop('events')
    for event in events:
        if event.get('time_elapsed') is not None:
            del event['time_elapsed']
    assert events == [
        {'type': 'llm_response',
         'response': 'Python is dynamically typed, garbage-collected, high level, general purpose programming.',
         'llm_response_log':
             {'content': 'Python is dynamically typed, garbage-collected, high level, general purpose programming.'}
         }, {'type': 'slots_to_fill', 'data': {}, 'slot_eval_log': ['initiating slot evaluation']}
    ]
    expected = [{'messages': [{'role': 'system', 'content': 'You are a personal assistant.\n'}, {'role': 'user',
                                                                                                 'content': "Language Prompt:\nPython is an interpreted, object-oriented, high-level programming language with dynamic semantics.\nInstructions on how to use Language Prompt:\nAnswer according to the context\n\n\nInstructions on how to use Similarity Prompt:\n['Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.']\nAnswer question based on the context above, if answer is not in the context go check previous logs.\n \nQ: What is the name of prompt? \nA:"}],
                 'raw_completion_response': {'choices': [{'message': {
                     'content': 'Python is dynamically typed, garbage-collected, high level, general purpose programming.',
                     'role': 'assistant'}}]}, 'type': 'answer_query',
                 'hyperparameters': {'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-4o-mini', 'top_p': 0.0,
                                     'n': 1, 'stop': None, 'presence_penalty': 0.0,
                                     'frequency_penalty': 0.0, 'logit_bias': {}}}]
    excludedRegex = [
        r"['raw_completion_response']['id']",
        r"['raw_completion_response']['created']"
    ]
    assert not DeepDiff(log['llm_logs'][0], expected[0], ignore_order=True, exclude_regex_paths=excludedRegex)


@mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
@mock.patch("kairon.shared.actions.utils.ActionUtility.compose_response", autospec=True)
def test_prompt_action_set_slots(mock_slot_set, mock_get_embedding, aioresponses):
    llm_type = "openai"
    action_name = "kairon_faq_action"
    bot = "5u80fd0a56c908ca10d35d2sjhjhjhj"
    user = "udit.pandey"
    value = "keyvalue"
    user_msg = "category of record created on 15/01/2023?"
    generated_text = "{\"api_type\": \"filter\", {\"filter\": {\"must\": [{\"key\": \"Date Added\", \"match\": {\"value\": 1673721000.0}}]}}}"
    hyperparameters = Utility.get_default_llm_hyperparameters()
    text_embedding_3_small_embeddings = [np.random.random(1536).tolist()]
    colbertv2_0_embeddings = [[np.random.random(128).tolist()]]
    bm25_embeddings = [{
        "indices": [1850593538, 11711171],
        "values": [1.66, 1.66]
    }]

    embeddings = {
        "dense": text_embedding_3_small_embeddings,
        "rerank": colbertv2_0_embeddings,
        "sparse": bm25_embeddings,
    }

    mock_get_embedding.return_value = embeddings

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


    expected_body = {'messages': [{'role': 'system', 'content': 'You are a personal assistant.\n'}, {'role': 'user', 'content': 'Qdrant Prompt:\nConvert user questions into json requests in qdrant such that they will either filter, apply range queries and search the payload in qdrant. Sample payload present in qdrant looks like below with each of the points starting with 1 to 5 is a record in qdrant.1. {"Category (Risk, Issue, Action Item)": "Risk", "Date Added": 1673721000.0,2. {"Category (Risk, Issue, Action Item)": "Action Item", "Date Added": 1673721000.0,For eg: to find category of record created on 15/01/2023, the filter query is:{"filter": {"must": [{"key": "Date Added", "match": {"value": 1673721000.0}}]}}\nInstructions on how to use Qdrant Prompt:\nCreate qdrant filter query out of user message based on above instructions.\n\n \nQ: category of record created on 15/01/2023? \nA:'}],
        "hyperparameters": hyperparameters,
        'user': user,
        'invocation': 'prompt_action'
    }

    aioresponses.add(
        url=urljoin(Utility.environment['llm']['url'],
                    f"/{bot}/completion/{llm_type}"),
        method="POST",
        status=200,
        payload={'formatted_response': generated_text,
                 'response': {'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}},
        body=expected_body
    )
    log1 = ['Slot: api_type', 'evaluation_type: expression', f"data: {generated_text}", 'response: filter']
    log2 = ['Slot: query', 'evaluation_type: expression', f"data: {generated_text}",
            'response: {\"must\": [{\"key\": \"Date Added\", \"match\": {\"value\": 1673721000.0}}]}']
    mock_slot_set.side_effect = [("filter", log1, 0.19473), (
        "{\"must\": [{\"key\": \"Date Added\", \"match\": {\"value\": 1673721000.0}}]}", log2, 0.10873)]
    Actions(name=action_name, type=ActionType.prompt_action.value, bot=bot, user=user).save()
    BotSettings(llm_settings=LLMSettings(enable_faq=True), bot=bot, user=user).save()
    PromptAction(name=action_name, bot=bot, user=user, llm_prompts=llm_prompts, dispatch_response=False,
                 set_slots=[
                     SetSlotsFromResponse(name="api_type", value="${data['api_type']}", evaluation_type="script"),
                     SetSlotsFromResponse(name="query", value="${data['filter']}",
                                          evaluation_type="script")]).save()
    llm_secret = LLMSecret(
        llm_type="openai",
        api_key=value,
        models=["gpt-3.5-turbo", "gpt-4o-mini"],
        bot=bot,
        user=user
    )
    llm_secret.save()

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
    assert response_json['events'] == [{'event': 'slot', 'timestamp': None, 'name': 'api_type', 'value': 'filter'},
                                       {'event': 'slot', 'timestamp': None, 'name': 'query',
                                        'value': '{"must": [{"key": "Date Added", "match": {"value": 1673721000.0}}]}'},
                                       {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response',
                                        'value': '{"api_type": "filter", {"filter": {"must": [{"key": "Date Added", "match": {"value": 1673721000.0}}]}}}'}]
    assert response_json['responses'] == []
    log = ActionServerLogs.objects(bot=bot, type=ActionType.prompt_action.value,
                                   status="SUCCESS").get().to_mongo().to_dict()
    assert isinstance(log['time_elapsed'], float) and log['time_elapsed'] > 0.0
    log.pop('_id')
    log.pop('timestamp')
    assert log["time_elapsed"]
    log.pop('time_elapsed')
    events = log.pop('events')
    for event in events:
        if event.get('time_elapsed') is not None:
            del event['time_elapsed']
    assert events == [
        {'type': 'llm_response',
         'response': '{"api_type": "filter", {"filter": {"must": [{"key": "Date Added", "match": {"value": 1673721000.0}}]}}}',
         'llm_response_log': {
             'content': '{"api_type": "filter", {"filter": {"must": [{"key": "Date Added", "match": {"value": 1673721000.0}}]}}}'}},
        {'type': 'slots_to_fill',
         'data': {'api_type': 'filter', 'query': '{"must": [{"key": "Date Added", "match": {"value": 1673721000.0}}]}'},
         'slot_eval_log': ['initiating slot evaluation', 'Slot: api_type', 'Slot: api_type',
                           'evaluation_type: expression',
                           'data: {"api_type": "filter", {"filter": {"must": [{"key": "Date Added", "match": {"value": 1673721000.0}}]}}}',
                           'response: filter', 'Slot: query', 'Slot: query', 'evaluation_type: expression',
                           'data: {"api_type": "filter", {"filter": {"must": [{"key": "Date Added", "match": {"value": 1673721000.0}}]}}}',
                           'response: {"must": [{"key": "Date Added", "match": {"value": 1673721000.0}}]}']}
    ]
    expected = [{'messages': [{'role': 'system', 'content': 'You are a personal assistant.\n'}, {'role': 'user',
                                                                                                 'content': 'Qdrant Prompt:\nConvert user questions into json requests in qdrant such that they will either filter, apply range queries and search the payload in qdrant. Sample payload present in qdrant looks like below with each of the points starting with 1 to 5 is a record in qdrant.1. {"Category (Risk, Issue, Action Item)": "Risk", "Date Added": 1673721000.0,2. {"Category (Risk, Issue, Action Item)": "Action Item", "Date Added": 1673721000.0,For eg: to find category of record created on 15/01/2023, the filter query is:{"filter": {"must": [{"key": "Date Added", "match": {"value": 1673721000.0}}]}}\nInstructions on how to use Qdrant Prompt:\nCreate qdrant filter query out of user message based on above instructions.\n\n \nQ: category of record created on 15/01/2023? \nA:'}],
                 'raw_completion_response': {'choices': [{'message': {
                     'content': '{"api_type": "filter", {"filter": {"must": [{"key": "Date Added", "match": {"value": 1673721000.0}}]}}}',
                     'role': 'assistant'}}]}, 'type': 'answer_query',
                 'hyperparameters': {'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-4o-mini', 'top_p': 0.0,
                                     'n': 1, 'stop': None, 'presence_penalty': 0.0,
                                     'frequency_penalty': 0.0, 'logit_bias': {}}}]
    excludedRegex = [
        r"['raw_completion_response']['id']",
        r"['raw_completion_response']['created']"
    ]
    assert not DeepDiff(log['llm_logs'][0], expected[0], ignore_order=True, exclude_regex_paths=excludedRegex)


@mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
def test_prompt_action_response_action_slot_prompt(mock_get_embedding, aioresponses):
    from uuid6 import uuid7

    llm_type = "openai"
    action_name = "kairon_faq_action"
    bot = "5u80fd0a56c908ca10d35d2s"
    user = "udit.pandey"
    value = "keyvalue"
    user_msg = "What is the name of prompt?"
    bot_content = "Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected."
    generated_text = "Python is dynamically typed, garbage-collected, high level, general purpose programming."
    hyperparameters = Utility.get_default_llm_hyperparameters()
    text_embedding_3_small_embeddings = np.random.random(1536).tolist()
    colbertv2_0_embeddings = [np.random.random(128).tolist()]
    bm25_embeddings = {
        "indices": [1850593538, 11711171],
        "values": [1.66, 1.66]
    }

    embeddings = {
        "dense": text_embedding_3_small_embeddings,
        "rerank": colbertv2_0_embeddings,
        "sparse": bm25_embeddings,
    }

    mock_get_embedding.return_value = embeddings

    llm_prompts = [
        {'name': 'System Prompt', 'data': 'You are a personal assistant.',
         'instructions': 'Answer question based on the context below.', 'type': 'system', 'source': 'static',
         'is_enabled': True},
        {'name': 'Similarity Prompt',
         'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
         'type': 'user', 'source': 'bot_content', 'data': 'python', 'is_enabled': True},
        {'name': 'Language Prompt',
         'data': 'type',
         'instructions': 'Answer according to the context', 'type': 'user', 'source': 'slot',
         'is_enabled': True},
    ]

    expected_body = {'messages': [{'role': 'system', 'content': 'You are a personal assistant.\n'}, {'role': 'user',
                                                                                                'content': "Language Prompt:\nPython is an interpreted, object-oriented, high-level programming language with dynamic semantics.\nInstructions on how to use Language Prompt:\nAnswer according to the context\n\n\nInstructions on how to use Similarity Prompt:\n['Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.']\nAnswer question based on the context above, if answer is not in the context go check previous logs.\n \nQ: What is the name of prompt? \nA:"}],
        "hyperparameters": hyperparameters,
        'user': user,
        'invocation': 'prompt_action'
    }

    aioresponses.add(
        url=urljoin(Utility.environment['llm']['url'],
                    f"/{bot}/completion/{llm_type}"),
        method="POST",
        status=200,
        payload={'formatted_response': generated_text,
                 'response': {'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}},
        body=expected_body
    )

    aioresponses.add(
        url=urljoin(Utility.environment['vector']['db'],
                    f"/collections/{bot}_python_faq_embd/points/query"),
        method="POST",
        payload={
            "result": {
                "points": [
                    {
                        "id": uuid7().__str__(),
                        "version": 0,
                        "score": 0.80,
                        "payload": {
                            "content": bot_content
                        }
                    }
                ]
            },
            "status": "ok",
            "time": 0.000957728
        }
    )
    Actions(name=action_name, type=ActionType.prompt_action.value, bot=bot, user=user).save()
    BotSettings(llm_settings=LLMSettings(enable_faq=True), bot=bot, user=user).save()
    PromptAction(name=action_name, bot=bot, user=user, llm_prompts=llm_prompts).save()
    llm_secret = LLMSecret(
        llm_type="openai",
        api_key=value,
        models=["gpt-3.5-turbo", "gpt-4o-mini"],
        bot=bot,
        user=user
    )
    llm_secret.save()

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
    log = ActionServerLogs.objects(bot=bot, type=ActionType.prompt_action.value,
                                   status="SUCCESS").get().to_mongo().to_dict()
    assert isinstance(log['time_elapsed'], float) and log['time_elapsed'] > 0.0
    log.pop('_id')
    log.pop('timestamp')
    assert log["time_elapsed"]
    log.pop('time_elapsed')
    events = log.pop('events')
    for event in events:
        if event.get('time_elapsed') is not None:
            del event['time_elapsed']
    assert events == [
        {'type': 'llm_response',
         'response': 'Python is dynamically typed, garbage-collected, high level, general purpose programming.',
         'llm_response_log':
             {'content': 'Python is dynamically typed, garbage-collected, high level, general purpose programming.'}
         }, {'type': 'slots_to_fill', 'data': {}, 'slot_eval_log': ['initiating slot evaluation']}
    ]
    expected = [{'messages': [{'role': 'system', 'content': 'You are a personal assistant.\n'}, {'role': 'user',
                                                                                                 'content': "Language Prompt:\nPython is an interpreted, object-oriented, high-level programming language with dynamic semantics.\nInstructions on how to use Language Prompt:\nAnswer according to the context\n\n\nInstructions on how to use Similarity Prompt:\n['Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.']\nAnswer question based on the context above, if answer is not in the context go check previous logs.\n \nQ: What is the name of prompt? \nA:"}],
                 'raw_completion_response': {'choices': [{'message': {
                     'content': 'Python is dynamically typed, garbage-collected, high level, general purpose programming.',
                     'role': 'assistant'}}]}, 'type': 'answer_query',
                 'hyperparameters': {'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-4o-mini', 'top_p': 0.0,
                                     'n': 1, 'stop': None, 'presence_penalty': 0.0,
                                     'frequency_penalty': 0.0, 'logit_bias': {}}}]
    excludedRegex = [
        r"['raw_completion_response']['id']",
        r"['raw_completion_response']['created']"
    ]
    assert not DeepDiff(log['llm_logs'][0], expected[0], ignore_order=True, exclude_regex_paths=excludedRegex)


@mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
def test_prompt_action_user_message_in_slot(mock_get_embedding, aioresponses):
    from uuid6 import uuid7

    llm_type ="openai"
    action_name = "kairon_faq_action"
    bot = "5u80fd0a56c908ca10d35d2sadfsf"
    user = "udit.pandey"
    value = "keyvalue"
    user_msg = '/kanban_story{"kairon_user_msg": "Kanban And Scrum Together?"}'
    bot_content = "Scrum teams using Kanban as a visual management tool can get work delivered faster and more often. Prioritized tasks are completed first as the team collectively decides what is best using visual cues from the Kanban board. The best part is that Scrum teams can use Kanban and Scrum at the same time."
    generated_text = "YES you can use both in a single project. However, in order to run the Sprint, you should only use the 'Scrum board'. On the other hand 'Kanban board' is only to track the progress or status of the Jira issues."
    hyperparameters = Utility.get_default_llm_hyperparameters()
    text_embedding_3_small_embeddings = np.random.random(1536).tolist()
    colbertv2_0_embeddings = [np.random.random(128).tolist()]
    bm25_embeddings = {
        "indices": [1850593538, 11711171],
        "values": [1.66, 1.66]
    }

    embeddings = {
        "dense": text_embedding_3_small_embeddings,
        "rerank": colbertv2_0_embeddings,
        "sparse": bm25_embeddings,
    }

    mock_get_embedding.return_value = embeddings

    llm_prompts = [
        {'name': 'System Prompt', 'data': 'You are a personal assistant.',
         'instructions': 'Answer question based on the context below.', 'type': 'system', 'source': 'static',
         'is_enabled': True},
        {'name': 'Similarity Prompt',
         'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
         'type': 'user', 'source': 'bot_content', 'data': 'python', 'is_enabled': True},
    ]

    expected_body = {'messages':[{'role': 'system', 'content': 'You are a personal assistant.\n'},
                                 {'role': 'user', 'content': "\nInstructions on how to use Similarity Prompt:\n['Scrum teams using Kanban as a visual management tool can get work delivered faster and more often. Prioritized tasks are completed first as the team collectively decides what is best using visual cues from the Kanban board. The best part is that Scrum teams can use Kanban and Scrum at the same time.']\nAnswer question based on the context above, if answer is not in the context go check previous logs.\n \nQ: Kanban And Scrum Together? \nA:"}],
        "hyperparameters": hyperparameters,
        'user': user,
        'invocation': 'prompt_action'
    }

    aioresponses.add(
        url=urljoin(Utility.environment['llm']['url'],
                    f"/{bot}/completion/{llm_type}"),
        method="POST",
        status=200,
        payload={'formatted_response': generated_text,
                 'response': {'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}},
        body=expected_body
    )

    aioresponses.add(
        url=urljoin(Utility.environment['vector']['db'],
                    f"/collections/{bot}_python_faq_embd/points/query"),
        method="POST",
        payload={
            "result": {
                "points": [
                    {
                        "id": uuid7().__str__(),
                        "version": 0,
                        "score": 0.80,
                        "payload": {
                            "content": bot_content
                        }
                    }
                ]
            },
            "status": "ok",
            "time": 0.000957728
        }
    )
    
    

    Actions(name=action_name, type=ActionType.prompt_action.value, bot=bot, user=user).save()
    BotSettings(llm_settings=LLMSettings(enable_faq=True), bot=bot, user=user).save()
    PromptAction(name=action_name, bot=bot, user=user, llm_prompts=llm_prompts).save()
    llm_secret = LLMSecret(
        llm_type="openai",
        api_key=value,
        models=["gpt-3.5-turbo", "gpt-4o-mini"],
        bot=bot,
        user=user
    )
    llm_secret.save()

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


@mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
def test_prompt_action_response_action_when_similarity_is_empty(mock_get_embedding, aioresponses):
    llm_type = "openai"
    action_name = "test_prompt_action_response_action_when_similarity_is_empty"
    bot = "5f50fd0a56b698ca10d35d2C"
    user = "udit.pandey"
    value = "keyvalue"
    user_msg = "What kind of language is python?"
    generated_text = "Python is dynamically typed, garbage-collected, high level, general purpose programming."
    hyperparameters = {"top_results": 10, "similarity_threshold": 0.70}
    llm_prompts = [
        {'name': 'System Prompt',
         'data': 'You are a personal assistant. Answer question based on the context below.',
         'type': 'system', 'source': 'static', 'is_enabled': True},
        {'name': 'History Prompt', 'type': 'user', 'source': 'history', 'is_enabled': True},
        {'name': 'Query Prompt', 'data': "What kind of language is python?", 'instructions': 'Rephrase the query.',
         'type': 'query', 'source': 'static', 'is_enabled': False},
        {'name': 'Similarity Prompt',
         'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
         'type': 'user', 'source': 'bot_content', 'data': 'python',
         'hyperparameters': hyperparameters,
         'is_enabled': True}
    ]

    text_embedding_3_small_embeddings = np.random.random(1536).tolist()
    colbertv2_0_embeddings = [np.random.random(128).tolist()]
    bm25_embeddings = {
        "indices": [1850593538, 11711171],
        "values": [1.66, 1.66]
    }

    embeddings = {
        "dense": text_embedding_3_small_embeddings,
        "rerank": colbertv2_0_embeddings,
        "sparse": bm25_embeddings,
    }

    mock_get_embedding.return_value = embeddings

    expected_body = {'messages': [
        {'role': 'system', 'content': 'You are a personal assistant. Answer question based on the context below.\n'},
        {'role': 'user', 'content': 'hello'}, {'role': 'assistant', 'content': 'how are you'},
        {'role': 'user', 'content': ' \nQ: What kind of language is python? \nA:'}],
        "hyperparameters": hyperparameters,
        'user': user,
        'invocation': 'prompt_action'
    }

    aioresponses.add(
        url=urljoin(Utility.environment['llm']['url'],
                    f"/{bot}/completion/{llm_type}"),
        method="POST",
        status=200,
        payload={'formatted_response': generated_text,
                 'response': {'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}},
        body=expected_body
    )

    aioresponses.add(
        url=urljoin(Utility.environment['vector']['db'],
                    f"/collections/{bot}_python_faq_embd/points/query"),
        method="POST",
        payload={
            "result": {
                "points": []
            },
            "status": "ok",
            "time": 0.000957728
        }
    )


    Actions(name=action_name, type=ActionType.prompt_action.value, bot=bot, user=user).save()
    BotSettings(llm_settings=LLMSettings(enable_faq=True), bot=bot, user=user).save()
    PromptAction(name=action_name, bot=bot, user=user, num_bot_responses=2, llm_prompts=llm_prompts).save()
    llm_secret = LLMSecret(
        llm_type="openai",
        api_key=value,
        models=["gpt-3.5-turbo", "gpt-4o-mini"],
        bot=bot,
        user=user
    )
    llm_secret.save()

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



@mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
def test_prompt_action_response_action_when_similarity_disabled(mock_get_embedding, aioresponses):
    llm_type = "openai"
    action_name = "test_prompt_action_response_action_when_similarity_disabled"
    bot = "5f50fd0a56b698ca10d35d2Z"
    user = "udit.pandey"
    value = "keyvalue"
    user_msg = "What kind of language is python?"
    generated_text = "Python is dynamically typed, garbage-collected, high level, general purpose programming."
    hyperparameters = {"top_results": 10, "similarity_threshold": 0.70}
    llm_prompts = [
        {'name': 'System Prompt',
         'data': 'You are a personal assistant. Answer question based on the context below.',
         'type': 'system', 'source': 'static', 'is_enabled': True},
        {'name': 'History Prompt', 'type': 'user', 'source': 'history', 'is_enabled': True},
        {'name': 'Query Prompt', 'data': "What kind of language is python?", 'instructions': 'Rephrase the query.',
         'type': 'query', 'source': 'static', 'is_enabled': False},
        {'name': 'Similarity Prompt',
         'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
         'type': 'user', 'source': 'bot_content', 'data': 'python',
         'hyperparameters': hyperparameters,
         'is_enabled': False}
    ]

    text_embedding_3_small_embeddings = [np.random.random(1536).tolist()]
    colbertv2_0_embeddings = [[np.random.random(128).tolist()]]
    bm25_embeddings = [{
        "indices": [1850593538, 11711171],
        "values": [1.66, 1.66]
    }]

    embeddings = {
        "dense": text_embedding_3_small_embeddings,
        "rerank": colbertv2_0_embeddings,
        "sparse": bm25_embeddings,
    }

    mock_get_embedding.return_value = embeddings

    expected_body = {'messages': [
        {'role': 'system', 'content': 'You are a personal assistant. Answer question based on the context below.\n'},
        {'role': 'user', 'content': 'hello'}, {'role': 'assistant', 'content': 'how are you'},
        {'role': 'user', 'content': ' \nQ: What kind of language is python? \nA:'}],
        "hyperparameters": hyperparameters,
        'user': user,
        'invocation': 'prompt_action'
    }

    aioresponses.add(
        url=urljoin(Utility.environment['llm']['url'],
                    f"/{bot}/completion/{llm_type}"),
        method="POST",
        status=200,
        payload={'formatted_response': generated_text, 'response': {'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}},
        body=expected_body
    )
    
    Actions(name=action_name, type=ActionType.prompt_action.value, bot=bot, user=user).save()
    BotSettings(llm_settings=LLMSettings(enable_faq=True), bot=bot, user=user).save()
    PromptAction(name=action_name, bot=bot, user=user, num_bot_responses=2, llm_prompts=llm_prompts).save()
    llm_secret = LLMSecret(
        llm_type=llm_type,
        api_key=value,
        models=["gpt-3.5-turbo", "gpt-4o-mini"],
        bot=bot,
        user=user
    )
    llm_secret.save()

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


@responses.activate
@mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
def test_vectordb_action_execution_embedding_payload_search(mock_get_embedding):
    bot = '5f50fx0a56b698ca10d35d2f'
    responses.add_passthru("https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken")
    action_name = "test_vectordb_action_execution_embedding_payload_search"
    Actions(name=action_name, type=ActionType.database_action.value, bot=bot,
            user="user").save()
    slot = 'name'
    Slots(name=slot, type='text', bot=bot, user='user').save()
    payload = {"filter": {
        "should": [{"key": "city", "match": {"value": "London"}}, {"key": "color", "match": {"value": "red"}}]}}
    payload_body = json.dumps(payload)
    user_msg = '/user_story{"kairon_user_msg": {"filter": {"should": [{"key": "city", "match": {"value": "London"}}, {"key": "color", "match": {"value": "red"}}]}}}'
    DatabaseAction(
        name=action_name,
        collection=action_name,
        payload=[DbQuery(query_type=DbActionOperationType.embedding_search.value, type="from_slot", value='name'),
                 DbQuery(query_type=DbActionOperationType.embedding_search.value, type="from_value",
                         value='How are you'),
                 DbQuery(query_type=DbActionOperationType.payload_search.value,
                         type=DbQueryValueType.from_user_message.value)
                 ],
        response=HttpActionResponse(value="The value of ${data.result.0.id} is ${data.result.0.vector}"),
        set_slots=[SetSlotsFromResponse(name="vector_value", value="${data.result.0.vector}")],
        bot=bot,
        user="user"
    ).save()
    BotSettings(llm_settings=LLMSettings(enable_faq=True), bot=bot, user="user").save()
    llm_secret = LLMSecret(
        llm_type="openai",
        api_key="key_value",
        models=["model1", "model2"],
        api_base_url="https://api.example.com",
        bot=bot,
        user="user"
    )
    llm_secret.save()
    text_embedding_3_small_embeddings = [np.random.random(1536).tolist()]
    colbertv2_0_embeddings = [[np.random.random(128).tolist()]]
    bm25_embeddings = [{
        "indices": [1850593538, 11711171],
        "values": [1.66, 1.66]
    }]

    embeddings = {
        "dense": text_embedding_3_small_embeddings,
        "rerank": colbertv2_0_embeddings,
        "sparse": bm25_embeddings,
    }

    mock_get_embedding.return_value = embeddings
    http_url = f'http://localhost:6333/collections/{bot}_{action_name}_faq_embd/points/query'
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
        match=[responses.matchers.json_params_matcher({'with_payload': True,
                                                       'limit': 10,
                                                       'query': embeddings,
                                                       **payload}, strict_match=False)],
    )

    request_object = {
        "next_action": action_name,
        "tracker": {
            "sender_id": "default",
            "conversation_id": "default",
            "slots": {"bot": bot, "name": "Hi"},
            "latest_message": {'text': user_msg, 'intent_ranking': [{'name': 'user_story'}],
                               "entities": [{"value": payload_body, "entity": KAIRON_USER_MSG_ENTITY}]},
            "latest_event_time": 1537645578.314389,
            "followup_action": "action_listen",
            "paused": False,
            "events": [{"event1": "hello"}, {"event2": "How are you"}],
            "latest_input_channel": "rest",
            "active_loop": {},
            "latest_action": {},
        },
        "domain": {
            "config": {},
            "session_config": {},
            "intents": [],
            "entities": [],
            "slots": {"bot": bot, "name": None},
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
    assert len(response_json['events']) == 2
    assert len(response_json['responses']) == 1
    assert response_json['events'] == [
        {'event': 'slot', 'timestamp': None, 'name': 'vector_value', 'value': '[15]'},
        {'event': 'slot', 'timestamp': None, 'name': 'kairon_action_response', 'value': 'The value of 15 is [15]'}]
    assert response_json['responses'][0]['text'] == "The value of 15 is [15]"
    log = ActionServerLogs.objects(action=action_name, bot=bot).get().to_mongo().to_dict()
    log.pop('_id')
    log.pop('timestamp')


def test_schedule_action_invalid_date():
    bot = '6697add6b8e47524eb983375'
    user = 'test'
    action_name = "test_schedule_action_invalid_date"
    callback_script = "test_schedule_action_invalid_date_script"
    date_str = "text"
    Actions(name=action_name, type=ActionType.schedule_action.value,
            bot=bot, user=user).save()

    CallbackConfig(
        name=callback_script,
        pyscript_code="bot_response='hello world'",
        validation_secret="test",
        execution_mode="async",
        bot=bot,
    ).save()

    ScheduleAction(
        name=action_name,
        bot=bot,
        user=user,
        schedule_time=CustomActionDynamicParameters(parameter_type='value',
                                                    value=date_str),
        schedule_action=callback_script,
        timezone="Asia/Kolkata",
        response_text="Action schedule",
        params_list=[CustomActionRequestParameters(key="bot", parameter_type="slot", value="bot", encrypt=True),
                     CustomActionRequestParameters(key="user", parameter_type="value", value="1011", encrypt=False)]
    ).save()

    request_object = {
        "next_action": action_name,
        "tracker": {
            "sender_id": "default",
            "conversation_id": "default",
            "slots": {"bot": bot},
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
    assert response.status_code == 200
    assert len(response_json['responses']) == 1
    assert response_json == {'events': [], 'responses': [
        {'text': 'Sorry, I am unable to process your request at the moment.', 'buttons': [], 'elements': [],
         'custom': {}, 'template': None, 'response': None,
         'image': None, 'attachment': None}]}

    log = ActionServerLogs.objects(action=action_name).get().to_mongo().to_dict()
    log.pop('_id')
    log.pop('timestamp')
    assert log == {'type': 'schedule_action', 'intent': 'test_run',
                   'action': action_name, 'sender': 'default', 'headers': {},
                   'bot_response': 'Sorry, I am unable to process your request at the moment.', 'messages': [],
                   'bot': bot,
                   'status': 'FAILURE',
                   'user_msg': 'get intents', 'schedule_action': callback_script,
                   'schedule_time': date_str, 'timezone': 'Asia/Kolkata',
                   'pyscript_code': "bot_response='hello world'",
                   'data': {'bot': '**********************75', 'user': '1011'},
                   'exception': 'Unknown string format: text'}


def test_schedule_action_invalid_callback():
    bot = '6697add6b8e47524eb983376'
    user = 'test'
    action_name = "test_schedule_action_invalid_callback"
    date_str = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    Actions(name=action_name, type=ActionType.schedule_action.value,
            bot=bot, user=user).save()

    ScheduleAction(
        name=action_name,
        bot=bot,
        user=user,
        schedule_time=CustomActionDynamicParameters(parameter_type='value',
                                                    value=date_str),
        schedule_action="invalid_callback",
        timezone="Asia/Kolkata",
        response_text="Action schedule",
        params_list=[CustomActionRequestParameters(key="bot", parameter_type="slot", value="bot", encrypt=True),
                     CustomActionRequestParameters(key="user", parameter_type="value", value="1011", encrypt=False)]
    ).save()

    request_object = {
        "next_action": action_name,
        "tracker": {
            "sender_id": "default",
            "conversation_id": "default",
            "slots": {"bot": bot},
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
    assert response.status_code == 200
    assert len(response_json['responses']) == 1
    assert response_json == {'events': [], 'responses': [
        {'text': 'Sorry, I am unable to process your request at the moment.', 'buttons': [], 'elements': [],
         'custom': {}, 'template': None, 'response': None,
         'image': None, 'attachment': None}]}

    log = ActionServerLogs.objects(action=action_name).get().to_mongo().to_dict()
    log.pop('_id')
    log.pop('timestamp')
    assert log == {'type': 'schedule_action', 'intent': 'test_run',
                   'action': action_name, 'sender': 'default', 'headers': {},
                   'bot_response': 'Sorry, I am unable to process your request at the moment.', 'messages': [],
                   'bot': bot,
                   'status': 'FAILURE',
                   'user_msg': 'get intents', 'schedule_action': 'invalid_callback',
                   'schedule_time': None, 'timezone': 'Asia/Kolkata',
                   'pyscript_code': None,
                   'data': {},
                   'exception': 'Callback Configuration with name \'invalid_callback\' does not exist!'}


@mock.patch("pymongo.collection.Collection.insert_one", autospec=True)
def test_schedule_action_execution(mock_add_job, aioresponses):
    mock_env = Utility.environment.copy()
    mock_env['events']['executor']['type'] = 'aws_lambda'

    bot = '6697add6b8e47524eb983374'
    user = 'test'
    action_name = "test_schedule_action_execution"
    callback_script = "test_schedule_action_script"
    date_str = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    timezone = "Asia/Kolkata"

    pattern = re.compile(rf'^{Utility.environment["events"]["server_url"]}/api/events/dispatch/.*')
    aioresponses.get(pattern, status=200, payload={'message': "Scheduled event dispatch!", 'data': None})
    with mock.patch.dict(Utility.environment, mock_env):
        Actions(name=action_name, type=ActionType.schedule_action.value,
                bot=bot, user=user).save()

        CallbackConfig(
            name=callback_script,
            pyscript_code="bot_response='hello world'",
            validation_secret="test",
            execution_mode="async",
            bot=bot,
        ).save()

        ScheduleAction(
            name=action_name,
            bot=bot,
            user=user,
            schedule_time=CustomActionDynamicParameters(parameter_type='value',
                                                        value=date_str),
            schedule_action=callback_script,
            timezone=timezone,
            response_text="Action schedule",
            params_list=[CustomActionRequestParameters(key="user", parameter_type="value", value="1011", encrypt=False)]
        ).save()

        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {"bot": bot},
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
        assert response.status_code == 200
        assert len(response_json['responses']) == 1
        assert response_json == {'events': [], 'responses': [
            {'text': 'Action schedule', 'buttons': [], 'elements': [], 'custom': {}, 'template': None, 'response': None,
             'image': None, 'attachment': None}]}

        log = ActionServerLogs.objects(action=action_name).get().to_mongo().to_dict()
        log.pop('_id')
        log.pop('timestamp')
        assert log == {'type': 'schedule_action', 'intent': 'test_run',
                       'action': 'test_schedule_action_execution', 'sender': 'default', 'headers': {},
                       'bot_response': 'Action schedule', 'messages': [], 'bot': bot,
                       'status': 'SUCCESS',
                       'user_msg': 'get intents', 'schedule_action': 'test_schedule_action_script',
                       'schedule_time': date_str, 'timezone': 'Asia/Kolkata',
                       'pyscript_code': "bot_response='hello world'",
                       'data': {'user': '1011'}}

        args, kwargs = mock_add_job.call_args
        assert args[1]['_id']
        assert args[1]['next_run_time']
        assert args[1]['job_state']
        job_state = pickle.loads(args[1]['job_state'])
        assert job_state['args'][0] == obj_to_ref(ExecutorFactory.get_executor().execute_task)
        assert job_state['args'][1] == 'scheduler_evaluator'
        assert not DeepDiff(list(job_state['args'][2]['predefined_objects'].keys()), ['bot', 'event', 'user'], ignore_order=True)
        assert job_state['args'][2]['predefined_objects']['bot'] == bot
        assert job_state['args'][2]['predefined_objects']['user'] == '1011'
        assert 'event' in job_state['args'][2]['predefined_objects']


@mock.patch("pymongo.collection.Collection.insert_one", autospec=True)
def test_schedule_action_execution_schedule_empty_data(mock_add_job, aioresponses):
    mock_env = Utility.environment.copy()
    mock_env['events']['executor']['type'] = 'aws_lambda'

    bot = '6697add6b8e47524eb983374'
    user = 'test'
    action_name = "test_schedule_action_execution_schedule_empty_data"
    callback_script = "test_schedule_action_script"
    date_str = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    slot_name = "schedule_slot"
    timezone = "Asia/Kolkata"

    pattern = re.compile(rf'^{Utility.environment["events"]["server_url"]}/api/events/dispatch/.*')
    aioresponses.get(pattern, status=200, payload={'message': "Scheduled event dispatch!", 'data': None})
    with mock.patch.dict(Utility.environment, mock_env):
        Actions(name=action_name, type=ActionType.schedule_action.value,
                bot=bot, user=user).save()

        CallbackConfig(
            name=callback_script,
            pyscript_code="bot_response='hello world'",
            validation_secret="test",
            execution_mode="async",
            bot=bot,
        ).save()

        ScheduleAction(
            name=action_name,
            bot=bot,
            user=user,
            schedule_time=CustomActionDynamicParameters(parameter_type=ActionParameterType.slot.value,
                                                        value=slot_name),
            schedule_action=callback_script,
            timezone=timezone,
            response_text="Action schedule",
            params_list=[]
        ).save()

        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {"bot": bot, "schedule_slot": date_str},
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
        assert response.status_code == 200
        assert len(response_json['responses']) == 1
        assert response_json == {'events': [], 'responses': [
            {'text': 'Action schedule', 'buttons': [], 'elements': [], 'custom': {}, 'template': None, 'response': None,
             'image': None, 'attachment': None}]}

        log = ActionServerLogs.objects(action=action_name).get().to_mongo().to_dict()
        log.pop('_id')
        log.pop('timestamp')
        assert log == {'type': 'schedule_action', 'intent': 'test_run',
                       'action': 'test_schedule_action_execution_schedule_empty_data', 'sender': 'default', 'headers': {},
                       'bot_response': 'Action schedule', 'messages': [], 'bot': bot,
                       'status': 'SUCCESS',
                       'user_msg': 'get intents', 'schedule_action': 'test_schedule_action_script',
                       'schedule_time': date_str, 'timezone': 'Asia/Kolkata',
                       'pyscript_code': "bot_response='hello world'",
                       'data': {}}

        args, kwargs = mock_add_job.call_args
        assert args[1]['_id']
        assert args[1]['next_run_time']
        assert args[1]['job_state']

        args, kwargs = mock_add_job.call_args
        assert args[1]['_id']
        assert args[1]['next_run_time']
        assert args[1]['job_state']
        job_state = pickle.loads(args[1]['job_state'])
        assert job_state['args'][0] == obj_to_ref(ExecutorFactory.get_executor().execute_task)
        assert job_state['args'][1] == 'scheduler_evaluator'
        assert not DeepDiff(list(job_state['args'][2]['predefined_objects'].keys()), ['bot', 'event'], ignore_order=True)
        assert job_state['args'][2]['predefined_objects']['bot'] == bot
        assert 'event' in job_state['args'][2]['predefined_objects']



@mock.patch("pymongo.collection.Collection.insert_one", autospec=True)
def test_schedule_action_execution_schedule_time_from_slot(mock_add_job, aioresponses):
    mock_env = Utility.environment.copy()
    mock_env['events']['executor']['type'] = 'aws_lambda'

    bot = '6697add6b8e47524eb983374'
    user = 'test'
    action_name = "test_schedule_action_execution_slot"
    callback_script = "test_schedule_action_script"
    date_str = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    slot_name = "schedule_slot"
    timezone = "Asia/Kolkata"

    pattern = re.compile(rf'^{Utility.environment["events"]["server_url"]}/api/events/dispatch/.*')
    aioresponses.get(pattern, status=200, payload={'message': "Scheduled event dispatch!", 'data': None})
    with mock.patch.dict(Utility.environment, mock_env):
        Actions(name=action_name, type=ActionType.schedule_action.value,
                bot=bot, user=user).save()

        CallbackConfig(
            name=callback_script,
            pyscript_code="bot_response='hello world'",
            validation_secret="test",
            execution_mode="async",
            bot=bot,
        ).save()

        ScheduleAction(
            name=action_name,
            bot=bot,
            user=user,
            schedule_time=CustomActionDynamicParameters(parameter_type=ActionParameterType.slot.value,
                                                        value=slot_name),
            schedule_action=callback_script,
            timezone=timezone,
            response_text="Action schedule",
            params_list=[CustomActionRequestParameters(key="bot", parameter_type="slot", value="bot", encrypt=True),
                         CustomActionRequestParameters(key="user", parameter_type="value", value="1011", encrypt=False)]
        ).save()

        request_object = {
            "next_action": action_name,
            "tracker": {
                "sender_id": "default",
                "conversation_id": "default",
                "slots": {"bot": bot, "schedule_slot": date_str},
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
        assert response.status_code == 200
        assert len(response_json['responses']) == 1
        assert response_json == {'events': [], 'responses': [
            {'text': 'Action schedule', 'buttons': [], 'elements': [], 'custom': {}, 'template': None, 'response': None,
             'image': None, 'attachment': None}]}

        log = ActionServerLogs.objects(action=action_name).get().to_mongo().to_dict()
        log.pop('_id')
        log.pop('timestamp')
        assert log == {'type': 'schedule_action', 'intent': 'test_run',
                       'action': 'test_schedule_action_execution_slot', 'sender': 'default', 'headers': {},
                       'bot_response': 'Action schedule', 'messages': [], 'bot': bot,
                       'status': 'SUCCESS',
                       'user_msg': 'get intents', 'schedule_action': 'test_schedule_action_script',
                       'schedule_time': date_str, 'timezone': 'Asia/Kolkata',
                       'pyscript_code': "bot_response='hello world'",
                       'data': {'bot': '**********************74', 'user': '1011'}}

        args, kwargs = mock_add_job.call_args
        assert args[1]['_id']
        assert args[1]['next_run_time']
        assert args[1]['job_state']
        job_state = pickle.loads(args[1]['job_state'])
        assert job_state['args'][0] == obj_to_ref(ExecutorFactory.get_executor().execute_task)
        assert job_state['args'][1] == 'scheduler_evaluator'
        print(job_state['args'][2]['predefined_objects'])
        assert not DeepDiff(list(job_state['args'][2]['predefined_objects'].keys()), ['bot', 'user', 'event'], ignore_order=True)
        assert job_state['args'][2]['predefined_objects']['bot'] == bot
        assert job_state['args'][2]['predefined_objects']['user'] == '1011'
        assert 'event' in job_state['args'][2]['predefined_objects']
