import os
import re
from datetime import datetime
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from mongoengine import DoesNotExist
from rasa.shared.core.events import ActionExecuted
from rasa.shared.core.training_data.structures import StoryGraph, StoryStep

from kairon.exceptions import AppException
from kairon.shared.cognition.data_objects import CollectionData
from kairon.shared.cognition.processor import CognitionDataProcessor
from kairon.shared.data.collection_processor import DataProcessor
from kairon.shared.utils import Utility
os.environ["system_file"] = "./tests/testing_data/system.yaml"
Utility.load_environment()
Utility.load_system_metadata()

from kairon.shared.data.processor import MongoProcessor

# NOTE: use this file for adding new tests for the data_processor module


def test_data_format_correction():
    metadata = [
        {'column_name': 'age', 'data_type': 'int'},
        {'column_name': 'height', 'data_type': 'float'},
        {'column_name': 'name', 'data_type': 'str'},
        {'column_name': 'extra', 'data_type': 'dict'},  # Unsupported type
    ]

    data_entries = [
        {'age': '25', 'height': '175.5', 'name': 'Alice', 'extra': {'key': 'value'}},
        {'age': ['30'], 'height': [180.0], 'name': ['Bob'], 'extra': [1, 2, 3]},
        {'age': None, 'height': '165.2', 'name': 'Charlie', 'extra': None},
        {'age': '40', 'height': None, 'name': None, 'extra': 'not a dict'}
    ]

    expected_output = [
        {'age': 25, 'height': 175.5, 'name': 'Alice', 'extra': {'key': 'value'}},
        {'age': 30, 'height': 180.0, 'name': 'Bob', 'extra': [1, 2, 3]},
        {'age': None, 'height': 165.2, 'name': 'Charlie', 'extra': None},
        {'age': 40, 'height': None, 'name': None, 'extra': 'not a dict'}
    ]

    result = MongoProcessor.data_format_correction_cognition_data(data_entries, metadata)
    assert result == expected_output, f"Expected {expected_output}, but got {result}"

def test_empty_entries():
    metadata = [{'column_name': 'age', 'data_type': 'int'}]
    data_entries = []
    result = MongoProcessor.data_format_correction_cognition_data(data_entries, metadata)
    assert result == [], f"Expected [], but got {result}"


def test_add_intent_with_invalid_name():
    processor = MongoProcessor()
    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_intent("greeting-message", "tests", "testUser", is_integration=False)

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_intent("greeting.message", "tests", "testUser", is_integration=False)

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_intent("greeting@message", "tests", "testUser", is_integration=False)

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_intent("greeting#message", "tests", "testUser", is_integration=False)

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_intent("greeting/message", "tests", "testUser", is_integration=False)

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_intent("greeting>message", "tests", "testUser", is_integration=False)

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_intent("greeting message", "tests", "testUser", is_integration=False)

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_intent("greeting:message", "tests", "testUser", is_integration=False)

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_intent("greeting=message", "tests", "testUser", is_integration=False)

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_intent("greeting~message", "tests", "testUser", is_integration=False)


def test_add_utterance_with_invalid_name():
    processor = MongoProcessor()
    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_utterance_name('test-add', 'test', 'testUser')

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_utterance_name('test]add', 'test', 'testUser')

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_utterance_name('test+add', 'test', 'testUser')

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_utterance_name('test\add', 'test', 'testUser')

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_utterance_name('test?add', 'test', 'testUser')

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_utterance_name('test&add', 'test', 'testUser')

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_utterance_name('test>add', 'test', 'testUser')

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_utterance_name('test"add', 'test', 'testUser')

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_utterance_name('test^add', 'test', 'testUser')

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_utterance_name('test@add', 'test', 'testUser')


def test_add_slot_with_invalid_name():
    processor = MongoProcessor()
    bot = 'test_add_slot'
    user = 'test_user'
    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_slot({"name": "slot-name", "type": "text", "influence_conversation": True}, bot, user,
                           raise_exception_if_exists=False)

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_slot({"name": "slot,name", "type": "text", "influence_conversation": True}, bot, user,
                           raise_exception_if_exists=False)

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_slot({"name": "slot(name)", "type": "text", "influence_conversation": True}, bot, user,
                           raise_exception_if_exists=False)

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_slot({"name": "slot;name", "type": "text", "influence_conversation": True}, bot, user,
                           raise_exception_if_exists=False)

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_slot({"name": "slot:name", "type": "text", "influence_conversation": True}, bot, user,
                           raise_exception_if_exists=False)

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_slot({"name": "slot[name]", "type": "text", "influence_conversation": True}, bot, user,
                           raise_exception_if_exists=False)

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_slot({"name": "slot!name", "type": "text", "influence_conversation": True}, bot, user,
                           raise_exception_if_exists=False)

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_slot({"name": "slot{name}", "type": "text", "influence_conversation": True}, bot, user,
                           raise_exception_if_exists=False)

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_slot({"name": "slot@name", "type": "text", "influence_conversation": True}, bot, user,
                           raise_exception_if_exists=False)

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_slot({"name": "slot<name>", "type": "text", "influence_conversation": True}, bot, user,
                           raise_exception_if_exists=False)


def test_add_lookup_with_invalid_name():
    processor = MongoProcessor()
    bot = 'test_add_lookup_value'
    user = 'test_user'
    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_lookup("lookup-name", bot, user)

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_lookup("lookup^name", bot, user)

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_lookup("lookup`name", bot, user)

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_lookup("lookup/name", bot, user)

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_lookup("lookup'name", bot, user)


def test_edit_lookup_with_invalid_name():
    processor = MongoProcessor()
    bot = 'test_add_lookup_value'
    user = 'test_user'
    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.edit_lookup_value("test_lookup_id", "two", "lookup-name", bot, user)

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.edit_lookup_value("test_lookup_id", "two", "lookup^name", bot, user)

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.edit_lookup_value("test_lookup_id", "two", "lookup`name", bot, user)

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.edit_lookup_value("test_lookup_id", "two", "lookup/name", bot, user)

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.edit_lookup_value("test_lookup_id", "two", "lookup'name", bot, user)


def test_edit_synonym_with_invalid_name():
    processor = MongoProcessor()
    bot = 'add_synonym'
    user = 'test_user'
    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.edit_synonym("test_synonym_id", "exp2", "synonym*name", bot, user)

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.edit_synonym("test_synonym_id", "exp2", "synonym%name", bot, user)

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.edit_synonym("test_synonym_id", "exp2", "synonym#name", bot, user)

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.edit_synonym("test_synonym_id", "exp2", "synonym|name", bot, user)

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.edit_synonym("test_synonym_id", "exp2", "synonym-name", bot, user)

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.edit_synonym("test_synonym_id", "exp2", "synonym+name", bot, user)

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.edit_synonym("test_synonym_id", "exp2", "synonym,name", bot, user)

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.edit_synonym("test_synonym_id", "exp2", "synonym?name", bot, user)

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.edit_synonym("test_synonym_id", "exp2", "synonym_>name", bot, user)

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.edit_synonym("test_synonym_id", "exp2", "synonym\name", bot, user)


def test_add_synonym_with_invalid_name():
    processor = MongoProcessor()
    bot = 'add_synonym'
    user = 'test_user'
    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_synonym("synonym*name", bot, user)

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_synonym("synonym%name", bot, user)

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_synonym("synonym#name", bot, user)

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_synonym("synonym|name", bot, user)

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_synonym("synonym-name", bot, user)

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_synonym("synonym+name", bot, user)

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_synonym("synonym,name", bot, user)

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_synonym("synonym?name", bot, user)

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_synonym("synonym_>name", bot, user)

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_synonym("synonym\name", bot, user)


def test_add_regex_with_invalid_name():
    processor = MongoProcessor()
    bot = 'test_add_regex'
    user = 'test_user'
    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_regex({"name": "regex  name", "pattern": "exp"}, bot, user)

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_regex({"name": "regex.name", "pattern": "exp"}, bot, user)

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_regex({"name": " regex-name", "pattern": "exp"}, bot, user)

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_regex({"name": "regex*name", "pattern": "exp"}, bot, user)

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_regex({"name": "regex name", "pattern": "exp"}, bot, user)


def test_edit_regex_with_invalid_name():
    processor = MongoProcessor()
    bot = 'test_add_regex'
    user = 'test_user'
    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.edit_regex({"name": "regex  name", "pattern": "exp"}, bot, user)

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.edit_regex({"name": "regex.name", "pattern": "exp"}, bot, user)

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.edit_regex({"name": " regex-name", "pattern": "exp"}, bot, user)

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.edit_regex({"name": "regex*name", "pattern": "exp"}, bot, user)

    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.edit_regex({"name": "regex name", "pattern": "exp"}, bot, user)


def test_add_http_action_config_with_invalid_name():
    processor = MongoProcessor()
    bot = 'test_bot'
    user = 'test_user'
    config = {
        "action_name": "http-action",
        "response": {"value": "string"},
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "http_params_list": [
            {"key": "testParam1", "parameter_type": "value", "value": "testValue1"}
        ],
    }
    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_http_action_config(config, user, bot)


def test_update_http_config_with_invalid_name():
    processor = MongoProcessor()
    bot = 'test_bot'
    user = 'test_user'
    config = {
        "action_name": "http-action",
        "response": {"value": "string"},
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "http_params_list": [
            {"key": "testParam1", "parameter_type": "value", "value": "testValue1"}
        ],
    }
    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.update_http_config(config, user, bot)


def test_add_slot_set_action_with_invalid_name():
    processor = MongoProcessor()
    bot = 'test_bot'
    user = 'test_user'
    config = {
        "name": "action-set-name-slot",
        "set_slots": [
            {"name": "name", "type": "from_value", "value": 5},
            {"name": "age", "type": "reset_slot"},
        ],
    }
    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_slot_set_action(config, user, bot)


def test_edit_slot_set_action_with_invalid_name():
    processor = MongoProcessor()
    bot = 'test_bot'
    user = 'test_user'
    config = {
        "name": "action-set-name-slot",
        "set_slots": [
            {"name": "name", "type": "from_value", "value": 5},
            {"name": "age", "type": "reset_slot"},
        ],
    }
    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.edit_slot_set_action(config, user, bot)


def test_add_email_action_with_invalid_name():
    processor = MongoProcessor()
    bot = 'test_bot'
    user = 'test_user'
    config = {
        "action_name": "email~config",
        "smtp_url": "test.test.com",
        "smtp_port": 25,
        "smtp_userid": None,
        "smtp_password": {"value": "test"},
        "from_email": {"value": "from_email", "parameter_type": "slot"},
        "to_email": {"value": ["test@test.com", "test1@test.com"], "parameter_type": "value"},
        "subject": "Test Subject",
        "response": "Test Response",
        "tls": False,
    }
    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_email_action(config, user, bot)


def test_edit_email_action_with_invalid_name():
    processor = MongoProcessor()
    bot = 'test_bot'
    user = 'test_user'
    config = {
        "action_name": "email~config",
        "smtp_url": "test.test.com",
        "smtp_port": 25,
        "smtp_userid": None,
        "smtp_password": {"value": "test"},
        "from_email": {"value": "from_email", "parameter_type": "slot"},
        "to_email": {"value": ["test@test.com", "test1@test.com"], "parameter_type": "value"},
        "subject": "Test Subject",
        "response": "Test Response",
        "tls": False,
    }
    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.edit_email_action(config, user, bot)


def test_add_google_action_with_invalid_name():
    processor = MongoProcessor()
    bot = 'test_bot'
    user = 'test_user'
    config = {
        "name": "google>custom<search",
        "api_key": {"value": "12345678"},
        "search_engine_id": "asdfg:123456",
        "failure_response": "I have failed to process your request",
        "website": "https://www.google.com",
    }
    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_google_search_action(config, user, bot)


def test_edit_google_search_action_with_invalid_name():
    processor = MongoProcessor()
    bot = 'test_bot'
    user = 'test_user'
    config = {
        "name": "google>custom<search",
        "api_key": {"value": "12345678"},
        "search_engine_id": "asdfg:123456",
        "failure_response": "I have failed to process your request",
        "website": "https://www.google.com",
    }
    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.edit_google_search_action(config, user, bot)


def test_add_jira_action_with_invalid_name():
    processor = MongoProcessor()
    bot = 'test_bot'
    user = 'test_user'
    url = "https://test_add_jira_action_invalid_config.net"
    config = {
        "name": "jira'action'new",
        "url": url,
        "user_name": "test@digite.com",
        "api_token": {"value": "ASDFGHJKL"},
        "project_key": "HEL",
        "issue_type": "Bug",
        "summary": "new user",
        "response": "We have logged a ticket",
    }
    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_jira_action(config, user, bot)


def test_edit_jira_action_with_invalid_name():
    processor = MongoProcessor()
    bot = 'test_bot'
    user = 'test_user'
    url = "https://test_add_jira_action_invalid_config.net"
    config = {
        "name": "jira'action'new",
        "url": url,
        "user_name": "test@digite.com",
        "api_token": {"value": "ASDFGHJKL"},
        "project_key": "HEL",
        "issue_type": "Bug",
        "summary": "new user",
        "response": "We have logged a ticket",
    }
    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.edit_jira_action(config, user, bot)


def test_add_zendesk_action_with_invalid_name():
    processor = MongoProcessor()
    bot = 'test_bot'
    user = 'test_user'
    config = {
        "name": "zendesk@action",
        "subdomain": "digite751",
        "api_token": {"value": "123456789"},
        "subject": "new ticket",
        "user_name": "udit.pandey@digite.com",
        "response": "ticket filed",
    }
    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_zendesk_action(config, user, bot)


def test_edit_zendesk_action_with_invalid_name():
    processor = MongoProcessor()
    bot = 'test_bot'
    user = 'test_user'
    config = {
        "name": "zendesk@action",
        "subdomain": "digite751",
        "api_token": {"value": "123456789"},
        "subject": "new ticket",
        "user_name": "udit.pandey@digite.com",
        "response": "ticket filed",
    }
    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.edit_zendesk_action(config, user, bot)


def test_add_pipedrive_action_with_invalid_name():
    processor = MongoProcessor()
    bot = 'test_bot'
    user = 'test_user'
    config = {
        "name": "pipedrive#leads",
        "domain": "https://digite751.pipedrive.com/",
        "api_token": {"value": "12345678"},
        "title": "new lead",
        "response": "I have failed to create lead for you",
        "metadata": {
            "name": "name",
            "org_name": "organization",
            "email": "email",
            "phone": "phone",
        },
    }
    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_pipedrive_action(config, user, bot)


def test_edit_pipedrive_action_with_invalid_name():
    processor = MongoProcessor()
    bot = 'test_bot'
    user = 'test_user'
    config = {
        "name": "pipedrive#leads",
        "domain": "https://digite751.pipedrive.com/",
        "api_token": {"value": "12345678"},
        "title": "new lead",
        "response": "I have failed to create lead for you",
        "metadata": {
            "name": "name",
            "org_name": "organization",
            "email": "email",
            "phone": "phone",
        },
    }
    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.edit_pipedrive_action(config, user, bot)


def test_add_hubspot_action_with_invalid_name():
    processor = MongoProcessor()
    bot = 'test_bot'
    user = 'test_user'
    config = {
        "name": "action(hubspot)forms",
        "portal_id": "12345678",
        "form_guid": "asdfg:123456",
        "fields": [
            {"key": "email", "value": "email_slot", "parameter_type": "slot"},
            {"key": "firstname", "value": "firstname_slot", "parameter_type": "slot"},
        ],
        "response": "Form submitted",
    }
    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_hubspot_forms_action(config, user, bot)


def test_edit_hubspot_forms_action_with_invalid_name():
    processor = MongoProcessor()
    bot = 'test_bot'
    user = 'test_user'
    config = {
        "name": "action(hubspot)forms",
        "portal_id": "12345678",
        "form_guid": "asdfg:123456",
        "fields": [
            {"key": "email", "value": "email_slot", "parameter_type": "slot"},
            {"key": "firstname", "value": "firstname_slot", "parameter_type": "slot"},
        ],
        "response": "Form submitted",
    }
    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.edit_hubspot_forms_action(config, user, bot)


def test_add_razorpay_action_with_invalid_name():
    processor = MongoProcessor()
    bot = 'test_bot'
    user = 'test_user'
    action_name = "razorpay`action"
    config = {
        "name": action_name,
        "api_key": {"value": "API_KEY", "parameter_type": "key_vault"},
        "api_secret": {"value": "API_SECRET", "parameter_type": "key_vault"},
        "amount": {"value": "amount", "parameter_type": "slot"},
        "currency": {"value": "INR", "parameter_type": "value"},
        "username": {"parameter_type": "sender_id"},
        "email": {"parameter_type": "sender_id"},
        "contact": {"value": "contact", "parameter_type": "slot"},
        "notes": [
            {"key": "order_id", "parameter_type": "slot", "value": "order_id"},
            {"key": "phone_number", "parameter_type": "value", "value": "9876543210"}
        ]
    }
    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_razorpay_action(config, user, bot)


def test_edit_razorpay_action_with_invalid_name():
    processor = MongoProcessor()
    bot = 'test_bot'
    user = 'test_user'
    action_name = "razorpay`action"
    config = {
        "name": action_name,
        "api_key": {"value": "API_KEY", "parameter_type": "key_vault"},
        "api_secret": {"value": "API_SECRET", "parameter_type": "key_vault"},
        "amount": {"value": "amount", "parameter_type": "slot"},
        "currency": {"value": "INR", "parameter_type": "value"},
        "username": {"parameter_type": "sender_id"},
        "email": {"parameter_type": "sender_id"},
        "contact": {"value": "contact", "parameter_type": "slot"},
        "notes": [
            {"key": "order_id", "parameter_type": "slot", "value": "order_id"},
            {"key": "phone_number", "parameter_type": "value", "value": "9876543210"}
        ]
    }
    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.edit_razorpay_action(config, user, bot)


def test_add_pyscript_action_with_invalid_name():
    processor = MongoProcessor()
    bot = 'test_bot'
    user = 'test_user'
    script = "bot_response='hello world'"
    config = {
        "name": "pyscript-action",
        "source_code": script,
        "dispatch_response": False,
    }
    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_pyscript_action(config, user, bot)


def test_update_pyscript_action_with_invalid_name():
    processor = MongoProcessor()
    bot = 'test_bot'
    user = 'test_user'
    script = "bot_response='hello world'"
    config = {
        "name": "pyscript-action",
        "source_code": script,
        "dispatch_response": False,
    }
    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.update_pyscript_action(config, user, bot)


def test_add_database_action_with_invalid_name():
    processor = MongoProcessor()
    bot = 'test_bot'
    user = 'test_user'
    config = {
        "name": "add-vectordb-action",
        "collection": 'test_add_vectordb_action_empty_name',
        "payload": [{
            "type": "from_value",
            "value": {"ids": [0], "with_payload": True, "with_vector": True},
            "query_type": "embedding_search",
        }],
        "response": {"value": "0"},
    }
    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_db_action(config, user, bot)


def test_update_db_action_with_invalid_name():
    processor = MongoProcessor()
    bot = 'test_bot'
    user = 'test_user'
    config = {
        "name": "add-vectordb-action",
        "collection": 'test_add_vectordb_action_empty_name',
        "payload": [{
            "type": "from_value",
            "value": {"ids": [0], "with_payload": True, "with_vector": True},
            "query_type": "embedding_search",
        }],
        "response": {"value": "0"},
    }
    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.update_db_action(config, user, bot)


def test_add_callback_action_with_invalid_name():
    processor = MongoProcessor()
    bot = 'test_bot'
    user = 'test_user'
    config = {
        "name": "callback@1",
        "pyscript_code": "bot_response = 'Hello World!'",
        "validation_secret": "string",
        "execution_mode": "async"
    }
    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_callback_action(config, user, bot)


def test_edit_callback_action_with_invalid_name():
    processor = MongoProcessor()
    bot = 'test_bot'
    user = 'test_user'
    config = {
        "name": "callback@1",
        "pyscript_code": "bot_response = 'Hello World!'",
        "validation_secret": "string",
        "execution_mode": "async"
    }
    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.edit_callback_action(config, user, bot)


def test_add_schedule_action_with_invalid_name():
    processor = MongoProcessor()
    bot = 'test_bot'
    user = 'test_user'
    config = {
        "name": " test schedule action",
        "schedule_time": {"value": "2024-08-06T09:00:00.000+0530", "parameter_type": "value"},
        "timezone": None,
        "schedule_action": "test_pyscript",
        "response_text": "action scheduled",
        "params_list": [
            {
                "key": "param_key",
                "value": "param_1",
                "parameter_type": "value",
                "count": 0
            }
        ],
        "dispatch_bot_response": True
    }
    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.add_schedule_action(config, user, bot)


def test_update_schedule_action_with_invalid_name():
    processor = MongoProcessor()
    bot = 'test_bot'
    user = 'test_user'
    config = {
        "name": " test schedule action",
        "schedule_time": {"value": "2024-08-06T09:00:00.000+0530", "parameter_type": "value"},
        "timezone": None,
        "schedule_action": "test_pyscript",
        "response_text": "action scheduled",
        "params_list": [
            {
                "key": "param_key",
                "value": "param_1",
                "parameter_type": "value",
                "count": 0
            }
        ],
        "dispatch_bot_response": True
    }
    with pytest.raises(AppException,
                       match=re.escape("Invalid name! Only letters, numbers, and underscores (_) are allowed.")):
        processor.update_schedule_action(config, user, bot)


def test_non_list_non_string_values():
    metadata = [{'column_name': 'age', 'data_type': 'int'}]
    data_entries = [{'age': '22', 'height': 5.7, 'name': 'Tom'}]
    expected_output = [{'age': 22, 'height': 5.7, 'name': 'Tom'}]
    result = MongoProcessor.data_format_correction_cognition_data(data_entries, metadata)
    assert result == expected_output, f"Expected {expected_output}, but got {result}"

def test_validate_metadata_and_payload_valid():
    schema = {
        "column_name": "item",
        "data_type": "str",
        "enable_search": True,
        "create_embeddings": True
    }
    data = {
        "id": 1,
        "item": "Cover",
        "price": 0.4,
        "quantity": 20
    }

    CognitionDataProcessor.validate_column_values(data, schema)

def test_validate_metadata_and_payload_invalid_str():
    schema = {
        "column_name": "item",
        "data_type": "str",
        "enable_search": True,
        "create_embeddings": True
    }
    data = {
        "id": 1,
        "item": 123,
        "price": 0.4,
        "quantity": 20
    }

    with pytest.raises(AppException, match="Invalid data type for 'item': Expected string value"):
        CognitionDataProcessor.validate_column_values(data, schema)


def test_validate_metadata_and_payload_invalid_int():
    schema = {
        "column_name": "id",
        "data_type": "int",
        "enable_search": True,
        "create_embeddings": True
    }
    data = {
        "id": "one",
        "item": "Cover",
        "price": 0.4,
        "quantity": 20
    }

    with pytest.raises(AppException, match="Invalid data type for 'id': Expected integer value"):
        CognitionDataProcessor.validate_column_values(data, schema)

def test_validate_metadata_and_payload_invalid_float():
    schema = {
        "column_name": "price",
        "data_type": "float",
        "enable_search": True,
        "create_embeddings": True
    }
    data = {
        "id": 1,
        "item": "Cover",
        "price": "cheap",
        "quantity": 20
    }

    with pytest.raises(AppException, match="Invalid data type for 'price': Expected float value"):
        CognitionDataProcessor.validate_column_values(data, schema)

def test_validate_metadata_and_payload_int_value_in_float_field():
    schema = {
        "column_name": "price",
        "data_type": "float",
        "enable_search": True,
        "create_embeddings": True
    }
    data = {
        "id": 1,
        "item": "Cover",
        "price": 231,
        "quantity": 20
    }
    CognitionDataProcessor.validate_column_values(data, schema)

def test_validate_metadata_and_payload_missing_column():
    schema = {
        "column_name": "quantity",
        "data_type": "int",
        "enable_search": True,
        "create_embeddings": True
    }
    data = {
        "id": 1,
        "item": "Cover",
        "price": 0.4
    }

    with pytest.raises(AppException, match="Column 'quantity' does not exist or has no value."):
        CognitionDataProcessor.validate_column_values(data, schema)



@patch('kairon.shared.cognition.processor.MongoProcessor')
@patch('kairon.shared.cognition.processor.CognitionSchema')
def test_is_collection_limit_exceeded_for_mass_uploading_exceeded(mock_cognition_schema, mock_mongo_processor):
    bot = "test_bot"
    user = "test_user"
    collection_names = ["collection1", "collection2", "collection3"]

    mock_mongo_processor.get_bot_settings.return_value.to_mongo.return_value.to_dict.return_value = {
        "cognition_collections_limit": 5
    }
    mock_cognition_schema.objects.return_value.distinct.return_value = ["collection_a", "collection_b", "collection_c"]

    result = CognitionDataProcessor.is_collection_limit_exceeded_for_mass_uploading(bot, user, collection_names)
    assert result is True

@patch('kairon.shared.cognition.processor.MongoProcessor')
@patch('kairon.shared.cognition.processor.CognitionSchema')
def test_is_collection_limit_exceeded_for_mass_uploading_exceeded_overwrite(mock_cognition_schema, mock_mongo_processor):
    bot = "test_bot"
    user = "test_user"
    collection_names = ["collection1", "collection2", "collection3", "collection_4", "collection_5", "collection_6"]

    mock_mongo_processor.get_bot_settings.return_value.to_mongo.return_value.to_dict.return_value = {
        "cognition_collections_limit": 5
    }
    mock_cognition_schema.objects.return_value.distinct.return_value = ["collection_a", "collection_b", "collection_c"]

    result = CognitionDataProcessor.is_collection_limit_exceeded_for_mass_uploading(bot, user, collection_names, True)
    assert result is True

@patch('kairon.shared.cognition.processor.MongoProcessor')
@patch('kairon.shared.cognition.processor.CognitionSchema')
def test_is_collection_limit_exceeded_for_mass_uploading_not_exceeded_overwrite(mock_cognition_schema, mock_mongo_processor):
    bot = "test_bot"
    user = "test_user"
    collection_names = ["collection1", "collection2", "collection3", "collection_4"]

    mock_mongo_processor.get_bot_settings.return_value.to_mongo.return_value.to_dict.return_value = {
        "cognition_collections_limit": 5
    }
    mock_cognition_schema.objects.return_value.distinct.return_value = ["collection_a", "collection_b", "collection_c"]

    result = CognitionDataProcessor.is_collection_limit_exceeded_for_mass_uploading(bot, user, collection_names, True)
    assert result is False

@patch('kairon.shared.cognition.processor.MongoProcessor')
@patch('kairon.shared.cognition.processor.CognitionSchema')
def test_is_collection_limit_exceeded_for_mass_uploading_not_exceeded(mock_cognition_schema, mock_mongo_processor):
    bot = "test_bot"
    user = "test_user"
    collection_names = ["collection1", "collection2"]

    mock_mongo_processor.get_bot_settings.return_value.to_mongo.return_value.to_dict.return_value = {
        "cognition_collections_limit": 5
    }
    mock_cognition_schema.objects.return_value.distinct.return_value = ["collection1"]

    result = CognitionDataProcessor.is_collection_limit_exceeded_for_mass_uploading(bot, user, collection_names)
    assert result is False


@patch.object(MongoProcessor, '_MongoProcessor__save_cognition_schema')
@patch.object(MongoProcessor, '_MongoProcessor__save_cognition_data')
def test_save_bot_content(mock_save_cognition_data, mock_save_cognition_schema):
    bot_content = [
        {
            'collection': 'collection1',
            'type': 'json',
            'metadata': [
                {'column_name': 'column1', 'data_type': 'str', 'enable_search': True, 'create_embeddings': False}
            ],
            'data': [
                {'column1': 'value1'}
            ]
        }
    ]
    bot = 'test_bot'
    user = 'test_user'
    processor = MongoProcessor()

    processor.save_bot_content(bot_content, bot, user)

    mock_save_cognition_schema.assert_called_once_with(bot_content, bot, user)
    mock_save_cognition_data.assert_called_once_with(bot_content, bot, user)

@patch.object(MongoProcessor, '_MongoProcessor__save_cognition_schema')
@patch.object(MongoProcessor, '_MongoProcessor__save_cognition_data')
def test_save_bot_content_empty(mock_save_cognition_data, mock_save_cognition_schema):
    bot_content = []
    bot = 'test_bot'
    user = 'test_user'
    processor = MongoProcessor()

    processor.save_bot_content(bot_content, bot, user)

    mock_save_cognition_schema.assert_not_called()
    mock_save_cognition_data.assert_not_called()




@patch.object(MongoProcessor, 'data_format_correction_cognition_data')
@patch('kairon.shared.data.processor.CognitionSchema.objects')
@patch('kairon.shared.data.processor.CognitionData.objects')
def test_prepare_cognition_data_for_bot_json(mock_cognition_data_objects, mock_cognition_schema_objects, mock_data_format_correction):
    bot = 'test_bot'
    schema_result = MagicMock()
    schema_result.collection_name = 'collection1'
    schema_result.metadata = [
        MagicMock(column_name='column1', data_type='str', enable_search=True, create_embeddings=False)
    ]
    mock_cognition_schema_objects.return_value.only.return_value = [schema_result]

    data_result = MagicMock()
    data_result.data = {'column1': 'value1'}
    mock_cognition_data_objects.return_value.only.return_value = [data_result]

    mock_data_format_correction.return_value = [{'column1': 'value1'}]

    processor = MongoProcessor()

    processor._MongoProcessor__prepare_cognition_data_for_bot(bot)

    mock_data_format_correction.assert_called_once()


@patch.object(MongoProcessor, 'data_format_correction_cognition_data')
@patch('kairon.shared.data.processor.CognitionSchema.objects')
@patch('kairon.shared.data.processor.CognitionData.objects')
def test_prepare_cognition_data_for_bot_text_format_not_called(mock_cognition_data_objects, mock_cognition_schema_objects, mock_data_format_correction):
    bot = 'test_bot'
    schema_result = MagicMock()
    schema_result.collection_name = 'collection1'
    schema_result.metadata = []
    mock_cognition_schema_objects.return_value.only.return_value = [schema_result]

    data_result = MagicMock()
    data_result.data = 'text data'
    mock_cognition_data_objects.return_value.only.return_value = [data_result]

    processor = MongoProcessor()

    processor._MongoProcessor__prepare_cognition_data_for_bot(bot)

    mock_data_format_correction.assert_not_called()



@patch('kairon.shared.data.processor.Rules')
@patch('kairon.shared.data.processor.MultiflowStories')
def test_get_flows_by_tag(mock_multiflow_stories, mock_rules):
    mock_rules.objects.return_value = [
        MagicMock(block_name='rule1'),
        MagicMock(block_name='rule2')
    ]
    mock_multiflow_stories.objects.return_value = [
        MagicMock(block_name='multiflow1'),
        MagicMock(block_name='multiflow2')
    ]

    result = MongoProcessor.get_flows_by_tag('test_bot', 'agentic_flow')

    mock_rules.objects.assert_called_once()
    mock_multiflow_stories.objects.assert_called_once()
    assert result == {
        'rule': ['rule1', 'rule2'],
        'multiflow': ['multiflow1', 'multiflow2']
    }

@patch('kairon.shared.data.processor.Rules')
@patch('kairon.shared.data.processor.MultiflowStories')
def test_get_flows_by_tag_no_flows(mock_multiflow_stories, mock_rules):
    mock_rules.objects.return_value = []
    mock_multiflow_stories.objects.return_value = []

    result = MongoProcessor.get_flows_by_tag('test_bot', 'test_tag')

    mock_rules.objects.assert_called_once()
    mock_multiflow_stories.objects.assert_called_once()
    assert result == {
        'rule': [],
        'multiflow': []
    }

def test_extract_action_names_from_story_graph():
    story_graph = MagicMock(spec=StoryGraph)

    story_step = MagicMock(spec=StoryStep)

    action_executed_event = MagicMock(spec=ActionExecuted)
    action_executed_event.action_name = 'action_test'

    story_step.events = [action_executed_event]

    story_graph.story_steps = [story_step]

    action_names = MongoProcessor.extract_action_names_from_story_graph([story_graph])

    assert action_names == ['action_test']

@patch.object(MongoProcessor, 'fetch_actions')
@patch.object(MongoProcessor, 'extract_action_names_from_story_graph')
def test_prepare_training_actions_with_story_graphs(mock_extract_action_names, mock_fetch_actions):
    mock_fetch_actions.return_value = ['action1', 'action2', 'action3']
    mock_extract_action_names.return_value = ['action1', 'action3']

    processor = MongoProcessor()
    story_graphs = [MagicMock(spec=StoryGraph)]
    result = processor._MongoProcessor__prepare_training_actions('test_bot', story_graphs)

    mock_fetch_actions.assert_called_once_with('test_bot')
    mock_extract_action_names.assert_called_once_with(story_graphs)
    assert result == ['action1', 'action3']

@patch.object(MongoProcessor, 'fetch_actions')
def test_prepare_training_actions_without_story_graphs(mock_fetch_actions):
    mock_fetch_actions.return_value = ['action1', 'action2', 'action3']

    processor = MongoProcessor()
    result = processor._MongoProcessor__prepare_training_actions('test_bot')

    mock_fetch_actions.assert_called_once_with('test_bot')
    assert result == ['action1', 'action2', 'action3']


class CollectionProcessor:
    pass

def test_get_all_collections_success():
    # Mocked aggregation result
    mocked_result = [
        {"collection_name": "collection1", "count": 2},
        {"collection_name": "collection2", "count": 5},
    ]

    with patch('kairon.shared.cognition.data_objects.CollectionData.objects') as mock_objects:
        mock_query_set = MagicMock()
        mock_query_set.aggregate.return_value = mocked_result
        mock_objects.return_value = mock_query_set

        # Act
        result = DataProcessor.get_all_collections(bot="test_bot")

        # Assert
        assert result == mocked_result
        assert len(result) == 2
        assert {"collection_name": "collection1", "count": 2} in result
        assert {"collection_name": "collection2", "count": 5} in result


def test_delete_collection_success():
    with patch('kairon.shared.cognition.data_objects.CollectionData.objects') as mock_objects:
        mock_query = MagicMock()
        mock_query.delete.return_value = 1  # Simulate successful deletion
        mock_objects.return_value = mock_query

        result = DataProcessor.delete_collection(bot="test_bot", name="sample_collection")

        mock_objects.assert_called_once_with(bot="test_bot", collection_name="sample_collection")
        mock_query.delete.assert_called_once()
        assert result == ["Collection sample_collection deleted successfully!", 1]


def test_delete_collection_not_found():
    with patch('kairon.shared.cognition.data_objects.CollectionData.objects') as mock_objects:
        mock_query = MagicMock()
        mock_query.delete.return_value = 0  # Simulate no deletion (not found)
        mock_objects.return_value = mock_query

        result = DataProcessor.delete_collection(bot="test_bot", name="nonexistent_collection")

        mock_objects.assert_called_once_with(bot="test_bot", collection_name="nonexistent_collection")
        mock_query.delete.assert_called_once()
        assert result == ["Collection nonexistent_collection does not exist!", 0]



def test_delete_collection_data_success():
    with patch('kairon.shared.cognition.data_objects.CollectionData.objects') as mock_collection_data:
        mock_query = MagicMock()
        mock_query.delete.return_value = 1
        mock_collection_data.return_value = mock_query


        DataProcessor.delete_collection_data_with_user(bot="test_bot", user="test_user_1")

        mock_collection_data.assert_called_once_with(bot="test_bot", user="test_user_1")
        mock_query.delete.assert_called_once()



def test_delete_collection_data_no_records():
    with patch('kairon.shared.cognition.data_objects.CollectionData.objects') as mock_collection_data:
        mock_query = MagicMock()
        mock_query.delete.return_value = 0
        mock_collection_data.return_value = mock_query

        DataProcessor.delete_collection_data_with_user(bot="test_bot", user="aniket.kharkia@nimblework,com")

        mock_collection_data.assert_called_once_with(bot="test_bot", user="aniket.kharkia@nimblework,com")
        mock_query.delete.assert_called_once()
