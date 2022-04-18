import asyncio
import glob
import json
import os
import re
import shutil
import tempfile
from datetime import datetime
from io import BytesIO
from typing import List

import pytest
import responses
from elasticmock import elasticmock
from fastapi import UploadFile
from jira import JIRAError, JIRA
from mongoengine import connect, DoesNotExist
from mongoengine.errors import ValidationError
from mongoengine.queryset.base import BaseQuerySet
from pipedrive.exceptions import UnauthorizedError
from rasa.core.agent import Agent
from rasa.shared.constants import DEFAULT_DOMAIN_PATH, DEFAULT_DATA_PATH, DEFAULT_CONFIG_PATH
from rasa.shared.core.events import UserUttered, ActionExecuted
from rasa.shared.core.training_data.structures import StoryGraph, RuleStep, Checkpoint
from rasa.shared.importers.rasa import Domain, RasaFileImporter
from rasa.shared.nlu.training_data.training_data import TrainingData
from rasa.shared.utils.io import read_config_file

from kairon.api import models
from kairon.shared.auth import Authentication
from kairon.api.models import HttpActionParameters, HttpActionConfigRequest
from kairon.shared.account.processor import AccountProcessor
from kairon.chat.agent_processor import AgentProcessor
from kairon.shared.data.constant import UTTERANCE_TYPE, EVENT_STATUS, STORY_EVENT, ALLOWED_DOMAIN_FORMATS, \
    ALLOWED_CONFIG_FORMATS, ALLOWED_NLU_FORMATS, ALLOWED_STORIES_FORMATS, ALLOWED_RULES_FORMATS, REQUIREMENTS, \
    DEFAULT_NLU_FALLBACK_RULE, SLOT_TYPE
from kairon.shared.data.data_objects import (TrainingExamples,
                                             Slots,
                                             Entities, EntitySynonyms, RegexFeatures,
                                             Intents,
                                             Responses,
                                             ModelTraining, StoryEvents, Stories, ResponseCustom, ResponseText,
                                             TrainingDataGenerator, TrainingDataGeneratorResponse,
                                             TrainingExamplesTrainingDataGenerator, Rules, Configs,
                                             Utterances, BotSettings, ChatClientConfig, LookupTables, Forms, SlotMapping
                                             )
from kairon.shared.data.model_processor import ModelProcessor
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.data.training_data_generation_processor import TrainingDataGenerationProcessor
from kairon.exceptions import AppException
from kairon.shared.actions.data_objects import HttpActionConfig, ActionServerLogs, Actions, SlotSetAction, \
    FormValidationAction, GoogleSearchAction, JiraAction, PipedriveLeadsAction
from kairon.shared.actions.models import ActionType
from kairon.shared.constants import SLOT_SET_TYPE
from kairon.shared.models import StoryEventType
from kairon.train import train_model_for_bot, start_training, train_model_from_mongo
from kairon.shared.utils import Utility
from kairon.shared.data.constant import ENDPOINT_TYPE
from unittest.mock import patch


class TestMongoProcessor:

    @pytest.fixture(autouse=True, scope='class')
    def init_connection(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        connect(**Utility.mongoengine_connection())
        Utility.environment['elasticsearch']['enable'] = False
        yield None
        Utility.environment['notifications']['enable'] = False

    @pytest.fixture()
    def get_training_data(self):

        async def _read_and_get_data(path: str):
            domain_path = os.path.join(path, DEFAULT_DOMAIN_PATH)
            training_data_path = os.path.join(path, DEFAULT_DATA_PATH)
            config_path = os.path.join(path, DEFAULT_CONFIG_PATH)
            http_actions_path = os.path.join(path, 'actions.yml')
            importer = RasaFileImporter.load_from_config(config_path=config_path,
                                                         domain_path=domain_path,
                                                         training_data_paths=training_data_path)
            domain = await importer.get_domain()
            story_graph = await importer.get_stories()
            config = await importer.get_config()
            nlu = await importer.get_nlu_data(config.get('language'))
            http_actions = Utility.read_yaml(http_actions_path)
            return nlu, story_graph, domain, config, http_actions

        return _read_and_get_data

    @pytest.mark.asyncio
    async def test_load_from_path(self):
        processor = MongoProcessor()
        result = await (
            processor.save_from_path(
                "./tests/testing_data/initial", bot="tests", user="testUser"
            )
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_save_from_path_yml(self):
        processor = MongoProcessor()
        result = await (
            processor.save_from_path(
                "./tests/testing_data/yml_training_files", bot="test_load_yml", user="testUser"
            )
        )
        assert result is None
        assert len(list(Intents.objects(bot="test_load_yml", user="testUser", use_entities=False))) == 2
        assert len(list(Intents.objects(bot="test_load_yml", user="testUser", use_entities=True))) == 27
        assert len(
            list(Slots.objects(bot="test_load_yml", user="testUser", influence_conversation=True, status=True))) == 2
        assert len(
            list(Slots.objects(bot="test_load_yml", user="testUser", influence_conversation=False, status=True))) == 8

    def test_bot_id_change(self):
        bot_id = Slots.objects(bot="test_load_yml", user="testUser", influence_conversation=False, name='bot').get()
        assert bot_id['initial_value'] == "test_load_yml"

    def test_add_or_overwrite_config_no_existing_config(self):
        bot = 'test_config'
        user = 'test_config'
        processor = MongoProcessor()
        config = Utility.read_yaml('./tests/testing_data/valid_yml/config.yml')
        processor.add_or_overwrite_config(config, bot, user)
        config = Configs.objects().get(bot=bot).to_mongo().to_dict()
        assert config['language'] == 'fr'
        assert len(config['pipeline']) == 9
        assert len(config['policies']) == 3
        rule_policy = next((comp for comp in config["policies"] if comp['name'] == 'RulePolicy'), {})
        assert rule_policy['core_fallback_action_name'] == 'action_small_talk'
        assert rule_policy['core_fallback_threshold'] == 0.75
        assert Rules.objects(block_name__iexact=DEFAULT_NLU_FALLBACK_RULE, bot=bot, status=True).get()
        assert Responses.objects(name__iexact='utter_please_rephrase', bot=bot, status=True).get()
        with pytest.raises(DoesNotExist):
            Responses.objects(name='utter_default', bot=bot, status=True).get()

    def test_add_or_overwrite_config(self):
        bot = 'test_config'
        user = 'test_config'
        processor = MongoProcessor()
        config = Utility.read_yaml('./tests/testing_data/valid_yml/config.yml')
        idx = next((idx for idx, comp in enumerate(config["policies"]) if comp['name'] == 'RulePolicy'), {})
        del config['policies'][idx]
        processor.add_or_overwrite_config(config, bot, user)
        config = Configs.objects().get(bot=bot).to_mongo().to_dict()
        assert config['language'] == 'fr'
        assert len(config['pipeline']) == 9
        assert len(config['policies']) == 3
        rule_policy = next((comp for comp in config["policies"] if comp['name'] == 'RulePolicy'), {})
        assert rule_policy['core_fallback_action_name'] == 'action_default_fallback'
        assert rule_policy['core_fallback_threshold'] == 0.3
        assert Rules.objects(block_name__iexact=DEFAULT_NLU_FALLBACK_RULE, bot=bot, status=True).get()
        assert Responses.objects(name__iexact='utter_please_rephrase', bot=bot, status=True).get()
        assert Responses.objects(name__iexact='utter_default', bot=bot, status=True).get()

    def test_add_or_overwrite_config_user_fallback(self):
        bot = 'test_config'
        user = 'test_config'
        processor = MongoProcessor()
        config = Utility.read_yaml('./tests/testing_data/valid_yml/config.yml')
        comp = next((comp for comp in config["pipeline"] if comp['name'] == 'DIETClassifier'), {})
        comp['epoch'] = 200
        comp = next((comp for comp in config["policies"] if comp['name'] == 'RulePolicy'), {})
        comp['core_fallback_action_name'] = 'action_error'
        comp['core_fallback_threshold'] = 0.5
        processor.add_or_overwrite_config(config, bot, user)
        config = Configs.objects().get(bot=bot).to_mongo().to_dict()
        assert config['language'] == 'fr'
        assert len(config['pipeline']) == 9
        assert len(config['policies']) == 3
        diet_classifier = next((comp for comp in config["pipeline"] if comp['name'] == 'DIETClassifier'), {})
        assert diet_classifier['epoch'] == 200
        rule_policy = next((comp for comp in config["policies"] if comp['name'] == 'RulePolicy'), {})
        assert rule_policy['core_fallback_action_name'] == 'action_error'
        assert rule_policy['core_fallback_threshold'] == 0.5
        assert Rules.objects(block_name__iexact=DEFAULT_NLU_FALLBACK_RULE, bot=bot, status=True).get()
        assert Responses.objects(name__iexact='utter_please_rephrase', bot=bot, status=True).get()
        assert Responses.objects(name__iexact='utter_default', bot=bot, status=True).get()

    def test_add_or_overwrite_config_no_action_and_threshold(self):
        bot = 'test_config'
        user = 'test_config'
        processor = MongoProcessor()
        config = Utility.read_yaml('./tests/testing_data/valid_yml/config.yml')
        comp = next((comp for comp in config["policies"] if comp['name'] == 'RulePolicy'), {})
        del comp['core_fallback_action_name']
        del comp['core_fallback_threshold']
        processor.add_or_overwrite_config(config, bot, user)
        config = Configs.objects().get(bot=bot).to_mongo().to_dict()
        assert config['language'] == 'fr'
        assert len(config['pipeline']) == 9
        assert len(config['policies']) == 3
        rule_policy = next((comp for comp in config["policies"] if comp['name'] == 'RulePolicy'), {})
        assert rule_policy['core_fallback_action_name'] == 'action_default_fallback'
        assert rule_policy['core_fallback_threshold'] == 0.3
        assert Rules.objects(block_name__iexact=DEFAULT_NLU_FALLBACK_RULE, bot=bot, status=True).get()
        assert Responses.objects(name__iexact='utter_please_rephrase', bot=bot, status=True).get()
        assert Responses.objects(name__iexact='utter_default', bot=bot, status=True).get()

    def test_add_or_overwrite_config_with_fallback_classifier(self):
        bot = 'test_config'
        user = 'test_config'
        processor = MongoProcessor()
        config = Utility.read_yaml('./tests/testing_data/valid_yml/config.yml')
        config["pipeline"].append({'name': 'FallbackClassifier', 'threshold': 0.7})
        processor.add_or_overwrite_config(config, bot, user)
        config = Configs.objects().get(bot=bot).to_mongo().to_dict()
        assert config['language'] == 'fr'
        assert len(config['pipeline']) == 9
        assert len(config['policies']) == 3
        diet_classifier = next((comp for comp in config["pipeline"] if comp['name'] == 'DIETClassifier'), {})
        assert diet_classifier['epochs'] == 5
        rule_policy = next((comp for comp in config["policies"] if comp['name'] == 'RulePolicy'), {})
        assert rule_policy['core_fallback_action_name'] == 'action_small_talk'
        assert rule_policy['core_fallback_threshold'] == 0.75
        assert Rules.objects(block_name__iexact=DEFAULT_NLU_FALLBACK_RULE, bot=bot, status=True).get()
        assert Responses.objects(name__iexact='utter_please_rephrase', bot=bot, status=True).get()
        assert Responses.objects(name__iexact='utter_default', bot=bot, status=True).get()

    def test_add_or_overwrite_config_with_fallback_policy(self):
        bot = 'test_config'
        user = 'test_config'
        processor = MongoProcessor()
        config = Utility.read_yaml('./tests/testing_data/valid_yml/config.yml')
        config['policies'].append({'name': 'FallbackPolicy', 'nlu_threshold': 0.75, 'core_threshold': 0.3})
        processor.add_or_overwrite_config(config, bot, user)
        config = Configs.objects().get(bot=bot).to_mongo().to_dict()
        assert config['language'] == 'fr'
        assert len(config['pipeline']) == 9
        assert len(config['policies']) == 3
        diet_classifier = next((comp for comp in config["pipeline"] if comp['name'] == 'DIETClassifier'), {})
        assert diet_classifier['epochs'] == 5
        rule_policy = next((comp for comp in config["policies"] if comp['name'] == 'RulePolicy'), {})
        assert rule_policy['core_fallback_action_name'] == 'action_small_talk'
        assert rule_policy['core_fallback_threshold'] == 0.75
        assert not next((comp for comp in config["policies"] if comp['name'] == 'FallbackPolicy'), None)
        assert Rules.objects(block_name__iexact=DEFAULT_NLU_FALLBACK_RULE, bot=bot, status=True).get()
        assert Responses.objects(name__iexact='utter_please_rephrase', bot=bot, status=True).get()
        assert Responses.objects(name__iexact='utter_default', bot=bot, status=True).get()

    @pytest.mark.asyncio
    async def test_upload_case_insensitivity(self):
        processor = MongoProcessor()
        await (
            processor.save_from_path(
                "./tests/testing_data/upper_case_data", bot="test_upload_case_insensitivity", user="testUser"
            )
        )
        training_data = processor.load_nlu("test_upload_case_insensitivity")
        assert isinstance(training_data, TrainingData)
        assert training_data.intents == {'deny', 'greet'}
        assert training_data.entity_synonyms == {'Bangalore': 'karnataka', 'bengaluru': 'karnataka',
                                                 'karnataka': 'karnataka', 'KA': 'karnataka'}
        assert training_data.regex_features == [{'name': 'application_name', 'pattern': '[azAz09\\s+]*'},
                                                {'name': 'email_id', 'pattern': '[^@]+@[^@]+\\.[^@]+'}]
        assert training_data.lookup_tables == [{'name': 'application_name', 'elements': ['Firefox', 'Chrome', 'Tor']},
                                               {'name': 'location', 'elements': ['Mumbai', 'Karnataka', 'Bangalore']}]
        story_graph = processor.load_stories("test_upload_case_insensitivity")
        assert story_graph.story_steps[0].block_name == 'greet'
        assert story_graph.story_steps[1].block_name == 'say goodbye'
        domain = processor.load_domain("test_upload_case_insensitivity")
        assert all(slot.name in ['session_started_metadata', 'requested_slot', 'application_name', 'bot', 'email_id',
                                 'location', 'user', 'kairon_action_response'] for slot in domain.slots)
        assert list(domain.templates.keys()) == ['utter_please_rephrase', 'utter_greet', 'utter_goodbye',
                                                 'utter_default']
        assert domain.entities == ['user', 'location', 'email_id', 'application_name', 'bot', 'kairon_action_response']
        assert domain.forms == {'ask_user': {'required_slots': {'user': [{'type': 'from_entity', 'entity': 'user'}],
                                                                'email_id': [
                                                                    {'type': 'from_entity', 'entity': 'email_id'}]}},
                                'ask_location': {
                                    'required_slots': {'location': [{'type': 'from_entity', 'entity': 'location'}],
                                                       'application_name': [
                                                           {'type': 'from_entity', 'entity': 'application_name'}]}}}
        assert domain.user_actions == ['action_get_google_application', 'action_get_microsoft_application',
                                       'utter_default', 'utter_goodbye', 'utter_greet', 'utter_please_rephrase']
        assert processor.fetch_actions('test_upload_case_insensitivity') == ['action_get_google_application',
                                                                             'action_get_microsoft_application']
        assert domain.intents == ['back', 'deny', 'greet', 'nlu_fallback', 'out_of_scope', 'restart', 'session_start']
        assert domain.templates == {
            'utter_please_rephrase': [{'text': "I'm sorry, I didn't quite understand that. Could you rephrase?"}],
            'utter_greet': [{'text': 'Hey! How are you?'}], 'utter_goodbye': [{'text': 'Bye'}],
            'utter_default': [{'text': 'Can you rephrase!'}]}
        rules = processor.fetch_rule_block_names("test_upload_case_insensitivity")
        assert rules == ['rule which will not wait for user message once it was applied',
                         'ask the user to rephrase whenever they send a message with low nlu confidence']
        actions = processor.load_http_action("test_upload_case_insensitivity")
        assert actions == {'http_action': [
            {'action_name': 'action_get_google_application', 'response': 'json', 'http_url': 'http://www.alphabet.com',
             'request_method': 'GET', 'headers': [{'key': 'testParam1', 'value': '', 'parameter_type': 'chat_log'},
                                                  {'key': 'testParam2', 'value': '', 'parameter_type': 'user_message'},
                                                  {'key': 'testParam3', 'value': '', 'parameter_type': 'value'},
                                                  {'key': 'testParam4', 'value': '', 'parameter_type': 'intent'},
                                                  {'key': 'testParam5', 'value': '', 'parameter_type': 'sender_id'},
                                                  {'key': 'testParam4', 'value': 'testvalue1',
                                                   'parameter_type': 'slot'}],
             'params_list': [{'key': 'testParam1', 'value': 'testValue1', 'parameter_type': 'value'},
                             {'key': 'testParam2', 'value': 'testvalue1', 'parameter_type': 'slot'}]},
            {'action_name': 'action_get_microsoft_application', 'response': 'json',
             'http_url': 'http://www.alphabet.com', 'request_method': 'GET',
             'params_list': [{'key': 'testParam1', 'value': 'testValue1', 'parameter_type': 'value'},
                             {'key': 'testParam2', 'value': 'testvalue1', 'parameter_type': 'slot'},
                             {'key': 'testParam1', 'value': '', 'parameter_type': 'chat_log'},
                             {'key': 'testParam2', 'value': '', 'parameter_type': 'user_message'},
                             {'key': 'testParam3', 'value': '', 'parameter_type': 'value'},
                             {'key': 'testParam4', 'value': '', 'parameter_type': 'intent'},
                             {'key': 'testParam5', 'value': '', 'parameter_type': 'sender_id'},
                             {'key': 'testParam4', 'value': 'testvalue1', 'parameter_type': 'slot'}]}]}
        assert set(Utterances.objects(bot='test_upload_case_insensitivity').values_list('name')) == {'utter_goodbye',
                                                                                                     'utter_greet',
                                                                                                     'utter_default',
                                                                                                     'utter_please_rephrase'}

    @pytest.mark.asyncio
    async def test_load_from_path_yml_training_files(self):
        processor = MongoProcessor()
        await (
            processor.save_from_path(
                "./tests/testing_data/yml_training_files", bot="test_load_from_path_yml_training_files", user="testUser"
            )
        )
        training_data = processor.load_nlu("test_load_from_path_yml_training_files")
        assert isinstance(training_data, TrainingData)
        assert training_data.training_examples.__len__() == 292
        assert training_data.entity_synonyms.__len__() == 3
        assert training_data.regex_features.__len__() == 5
        assert training_data.lookup_tables.__len__() == 1
        story_graph = processor.load_stories("test_load_from_path_yml_training_files")
        assert isinstance(story_graph, StoryGraph) is True
        assert story_graph.story_steps.__len__() == 16
        assert story_graph.story_steps[14].events[2].intent['name'] == 'user_feedback'
        assert not story_graph.story_steps[14].events[2].entities[0].get('start')
        assert not story_graph.story_steps[14].events[2].entities[0].get('end')
        assert story_graph.story_steps[14].events[2].entities[0]['value'] == 'like'
        assert story_graph.story_steps[14].events[2].entities[0]['entity'] == 'fdresponse'
        assert story_graph.story_steps[15].events[2].intent['name'] == 'user_feedback'
        assert not story_graph.story_steps[15].events[2].entities[0].get('start')
        assert not story_graph.story_steps[15].events[2].entities[0].get('end')
        assert story_graph.story_steps[15].events[2].entities[0]['value'] == 'hate'
        assert story_graph.story_steps[15].events[2].entities[0]['entity'] == 'fdresponse'
        domain = processor.load_domain("test_load_from_path_yml_training_files")
        assert isinstance(domain, Domain)
        assert domain.slots.__len__() == 12
        assert len([slot for slot in domain.slots if slot.influence_conversation is True]) == 2
        assert len([slot for slot in domain.slots if slot.influence_conversation is False]) == 10
        assert domain.intent_properties.__len__() == 29
        assert len([intent for intent in domain.intent_properties.keys() if
                    domain.intent_properties.get(intent)['used_entities']]) == 27
        assert len([intent for intent in domain.intent_properties.keys() if
                    not domain.intent_properties.get(intent)['used_entities']]) == 2
        assert domain.templates.keys().__len__() == 27
        assert domain.entities.__len__() == 11
        assert domain.forms.__len__() == 2
        assert domain.forms.__len__() == 2
        assert domain.forms['ticket_attributes_form'] == {
            'required_slots': {'date_time': [{'type': 'from_entity', 'entity': 'date_time'}],
                               'priority': [{'type': 'from_entity', 'entity': 'priority'}]}}
        assert domain.forms['ticket_file_form'] == {
            'required_slots': {'file': [{'type': 'from_entity', 'entity': 'file'}]}}
        assert isinstance(domain.forms, dict)
        assert domain.user_actions.__len__() == 45
        assert processor.list_actions('test_load_from_path_yml_training_files')["actions"].__len__() == 12
        assert processor.list_actions('test_load_from_path_yml_training_files')["form_validation_action"].__len__() == 1
        assert domain.intents.__len__() == 29
        assert not Utility.check_empty_string(
            domain.templates["utter_cheer_up"][0]["image"]
        )
        assert domain.templates["utter_did_that_help"][0]["buttons"].__len__() == 2
        assert domain.templates["utter_offer_help"][0]["custom"]
        assert domain.slots[0].type_name == "any"
        assert domain.slots[1].type_name == "any"
        assert domain.slots[2].type_name == "any"
        rules = processor.fetch_rule_block_names("test_load_from_path_yml_training_files")
        assert len(rules) == 4
        actions = processor.load_http_action("test_load_from_path_yml_training_files")
        assert isinstance(actions, dict) is True
        assert len(actions['http_action']) == 5
        assert Utterances.objects(bot='test_load_from_path_yml_training_files').count() == 27

    @pytest.mark.asyncio
    async def test_load_from_path_error(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            await (
                processor.save_from_path(
                    "./tests/testing_data/error", bot="tests", user="testUser"
                )
            )

    @pytest.mark.asyncio
    async def test_load_from_path_all_scenario(self):
        processor = MongoProcessor()
        await (
            processor.save_from_path("./tests/testing_data/all", bot="all", user="testUser")
        )
        training_data = processor.load_nlu("all")
        assert isinstance(training_data, TrainingData)
        assert training_data.training_examples.__len__() == 292
        assert training_data.entity_synonyms.__len__() == 3
        assert training_data.regex_features.__len__() == 5
        assert training_data.lookup_tables.__len__() == 1
        story_graph = processor.load_stories("all")
        assert isinstance(story_graph, StoryGraph) is True
        assert story_graph.story_steps.__len__() == 16
        assert story_graph.story_steps[14].events[2].intent['name'] == 'user_feedback'
        assert story_graph.story_steps[14].events[2].entities[0]['start'] == 13
        assert story_graph.story_steps[14].events[2].entities[0]['end'] == 34
        assert story_graph.story_steps[14].events[2].entities[0]['value'] == 'like'
        assert story_graph.story_steps[14].events[2].entities[0]['entity'] == 'fdresponse'
        assert story_graph.story_steps[15].events[2].intent['name'] == 'user_feedback'
        assert story_graph.story_steps[15].events[2].entities[0]['start'] == 13
        assert story_graph.story_steps[15].events[2].entities[0]['end'] == 34
        assert story_graph.story_steps[15].events[2].entities[0]['value'] == 'hate'
        assert story_graph.story_steps[15].events[2].entities[0]['entity'] == 'fdresponse'
        domain = processor.load_domain("all")
        assert isinstance(domain, Domain)
        assert domain.slots.__len__() == 11
        assert domain.templates.keys().__len__() == 27
        assert domain.entities.__len__() == 10
        assert domain.forms.__len__() == 2
        assert domain.forms['ticket_attributes_form'] == {'required_slots': {}}
        assert isinstance(domain.forms, dict)
        assert domain.user_actions.__len__() == 40
        assert processor.list_actions('all')["actions"].__len__() == 13
        assert domain.intents.__len__() == 29
        assert not Utility.check_empty_string(
            domain.templates["utter_cheer_up"][0]["image"]
        )
        assert domain.templates["utter_did_that_help"][0]["buttons"].__len__() == 2
        assert domain.templates["utter_offer_help"][0]["custom"]
        assert domain.slots[0].type_name == "any"
        assert domain.slots[1].type_name == "any"
        assert Utterances.objects(bot='all').count() == 27

    @pytest.mark.asyncio
    async def test_load_from_path_all_scenario_append(self):
        processor = MongoProcessor()
        await (
            processor.save_from_path("./tests/testing_data/all",
                                     "all",
                                     overwrite=False,
                                     user="testUser")
        )
        training_data = processor.load_nlu("all")
        assert isinstance(training_data, TrainingData)
        assert training_data.training_examples.__len__() == 292
        assert training_data.entity_synonyms.__len__() == 3
        assert training_data.regex_features.__len__() == 5
        assert training_data.lookup_tables.__len__() == 1
        story_graph = processor.load_stories("all")
        assert isinstance(story_graph, StoryGraph) is True
        assert story_graph.story_steps.__len__() == 16
        assert story_graph.story_steps[14].events[2].intent['name'] == 'user_feedback'
        assert story_graph.story_steps[14].events[2].entities[0]['start'] == 13
        assert story_graph.story_steps[14].events[2].entities[0]['end'] == 34
        assert story_graph.story_steps[14].events[2].entities[0]['value'] == 'like'
        assert story_graph.story_steps[14].events[2].entities[0]['entity'] == 'fdresponse'
        assert story_graph.story_steps[15].events[2].intent['name'] == 'user_feedback'
        assert story_graph.story_steps[15].events[2].entities[0]['start'] == 13
        assert story_graph.story_steps[15].events[2].entities[0]['end'] == 34
        assert story_graph.story_steps[15].events[2].entities[0]['value'] == 'hate'
        assert story_graph.story_steps[15].events[2].entities[0]['entity'] == 'fdresponse'
        domain = processor.load_domain("all")
        assert isinstance(domain, Domain)
        assert domain.slots.__len__() == 11
        assert domain.templates.keys().__len__() == 27
        assert domain.entities.__len__() == 10
        assert domain.forms.__len__() == 2
        assert isinstance(domain.forms, dict)
        assert domain.user_actions.__len__() == 40
        assert domain.intents.__len__() == 29
        assert processor.list_actions('all')["actions"].__len__() == 13
        assert not Utility.check_empty_string(
            domain.templates["utter_cheer_up"][0]["image"]
        )
        assert domain.templates["utter_did_that_help"][0]["buttons"].__len__() == 2
        assert domain.templates["utter_offer_help"][0]["custom"]
        assert domain.slots[0].type_name == "any"
        assert domain.slots[1].type_name == "any"
        assert Utterances.objects(bot='all').count() == 27

    def test_load_nlu(self):
        processor = MongoProcessor()
        training_data = processor.load_nlu("tests")
        assert isinstance(training_data, TrainingData)
        assert training_data.training_examples.__len__() == 52
        assert training_data.entity_synonyms.__len__() == 0
        assert training_data.regex_features.__len__() == 0
        assert training_data.lookup_tables.__len__() == 0

    def test_load_domain(self):
        processor = MongoProcessor()
        domain = processor.load_domain("tests")
        assert isinstance(domain, Domain)
        assert domain.slots.__len__() == 3
        assert domain.slots[0].name == 'kairon_action_response'
        assert domain.slots[0].value is None
        assert domain.templates.keys().__len__() == 11
        assert domain.entities.__len__() == 2
        assert domain.form_names.__len__() == 0
        assert domain.user_actions.__len__() == 11
        assert domain.intents.__len__() == 14
        assert Utterances.objects(bot="tests").count() == 11

    def test_load_stories(self):
        processor = MongoProcessor()
        story_graph = processor.load_stories("tests")
        assert isinstance(story_graph, StoryGraph)
        assert story_graph.story_steps.__len__() == 7

    def test_add_intent(self):
        processor = MongoProcessor()
        assert processor.add_intent("greeting", "tests", "testUser", is_integration=False)
        intent = Intents.objects(bot="tests").get(name="greeting")
        assert intent.name == "greeting"

    def test_get_intents(self):
        processor = MongoProcessor()
        actual = processor.get_intents("tests")
        assert actual.__len__() == 15

    def test_add_intent_with_underscore(self):
        processor = MongoProcessor()
        assert processor.add_intent("greeting_examples", "tests", "testUser", is_integration=False)
        intent = Intents.objects(bot="tests").get(name="greeting_examples")
        assert intent.name == "greeting_examples"

    def test_add_intent_duplicate(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            processor.add_intent("greeting", "tests", "testUser", is_integration=False)

    def test_add_intent_duplicate_case_insensitive(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            processor.add_intent("Greeting", "tests", "testUser", is_integration=False)

    def test_add_none_intent(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_intent(None, "tests", "testUser", is_integration=False)

    def test_add_empty_intent(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_intent("", "tests", "testUser", is_integration=False)

    def test_add_blank_intent(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_intent("  ", "tests", "testUser", is_integration=False)

    def test_add_training_example(self):
        processor = MongoProcessor()
        results = list(
            processor.add_training_example(["Hi, How are you?"], "greeting", "tests", "testUser", is_integration=False)
        )
        assert results[0]["_id"]
        assert results[0]["text"] == "Hi, How are you?"
        assert results[0]["message"] == "Training Example added"

    def test_add_same_training_example(self):
        processor = MongoProcessor()
        results = list(
            processor.add_training_example(["Hi"], "greeting", "tests", "testUser", is_integration=False)
        )
        assert results[0]["_id"] is None
        assert results[0]["text"] == "Hi"
        assert results[0]["message"] == 'Training Example exists in intent: [\'greet\']'

    def test_add_training_example_duplicate_case_insensitive(self):
        processor = MongoProcessor()
        results = list(
            processor.add_training_example(["hi"], "greeting", "tests", "testUser", is_integration=False)
        )
        assert results[0]["_id"] is None
        assert results[0]["text"] == "hi"
        assert results[0]["message"] == 'Training Example exists in intent: [\'greet\']'

    def test_add_training_example_none_text(self):
        processor = MongoProcessor()
        results = list(
            processor.add_training_example([None], "greeting", "tests", "testUser", is_integration=False)
        )
        assert results[0]["_id"] is None
        assert results[0]["text"] is None
        assert (
                results[0]["message"]
                == "Training Example cannot be empty or blank spaces"
        )

    def test_add_training_example_empty_text(self):
        processor = MongoProcessor()
        results = list(
            processor.add_training_example([""], "greeting", "tests", "testUser", is_integration=False)
        )
        assert results[0]["_id"] is None
        assert results[0]["text"] == ""
        assert (
                results[0]["message"]
                == "Training Example cannot be empty or blank spaces"
        )

    def test_add_training_example_blank_text(self):
        processor = MongoProcessor()
        results = list(
            processor.add_training_example(["  "], "greeting", "tests", "testUser", is_integration=False)
        )
        assert results[0]["_id"] is None
        assert results[0]["text"] == "  "
        assert (
                results[0]["message"]
                == "Training Example cannot be empty or blank spaces"
        )

    def test_add_training_example_none_intent(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            results = list(
                processor.add_training_example(
                    ["Hi! How are you"], None, "tests", "testUser", is_integration=False
                )
            )
            assert results[0]["_id"] is None
            assert results[0]["text"] == "Hi! How are you"
            assert (
                    results[0]["message"]
                    == "Intent cannot be empty or blank spaces"
            )

    def test_add_training_example_empty_intent(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            results = list(
                processor.add_training_example(
                    ["Hi! How are you"], "", "tests", "testUser", is_integration=False
                )
            )
            assert results[0]["_id"] is None
            assert results[0]["text"] == "Hi! How are you"
            assert (
                    results[0]["message"]
                    == "Intent cannot be empty or blank spaces"
            )

    def test_add_training_example_blank_intent(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            results = list(
                processor.add_training_example(
                    ["Hi! How are you"], "  ", "tests", "testUser", is_integration=False
                )
            )
            assert results[0]["_id"] is None
            assert results[0]["text"] == "Hi! How are you"
            assert (
                    results[0]["message"]
                    == "Intent cannot be empty or blank spaces"
            )

    def test_add_empty_training_example(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            results = list(
                processor.add_training_example([""], None, "tests", "testUser", is_integration=False)
            )
            assert results[0]["_id"] is None
            assert results[0]["text"] == "Hi! How are you"
            assert (
                    results[0]["message"]
                    == "Training Example cannot be empty or blank spaces"
            )

    def test_get_training_examples(self):
        processor = MongoProcessor()
        expected = ["hey", "hello", "hi", "good morning", "good evening", "hey there"]
        actual = list(processor.get_training_examples("greet", "tests"))
        assert actual.__len__() == expected.__len__()
        assert all(a_val["text"] in expected for a_val in actual)

    def test_get_training_examples_empty(self):
        processor = MongoProcessor()
        actual = list(processor.get_training_examples("greets", "tests"))
        assert actual.__len__() == 0

    def test_get_all_training_examples(self):
        processor = MongoProcessor()
        training_examples, ids = processor.get_all_training_examples("tests")
        assert training_examples
        assert ids

    def test_get_training_examples_as_dict(self, monkeypatch):
        processor = MongoProcessor()
        training_examples_expected = {'hi': 'greet', 'hello': 'greet', 'ok': 'affirm', 'no': 'deny'}

        def _mongo_aggregation(*args, **kwargs):
            return [{'training_examples': training_examples_expected}]

        monkeypatch.setattr(BaseQuerySet, 'aggregate', _mongo_aggregation)
        training_examples = processor.get_training_examples_as_dict("tests")
        assert training_examples == training_examples_expected

    def test_get_training_examples_as_dict_no_examples_added(self, monkeypatch):
        processor = MongoProcessor()

        def _mongo_aggregation(*args, **kwargs):
            return []

        monkeypatch.setattr(BaseQuerySet, 'aggregate', _mongo_aggregation)
        training_examples = processor.get_training_examples_as_dict("tests_bot")
        assert training_examples == {}

    def test_add_training_example_with_entity(self):
        processor = MongoProcessor()
        results = list(
            processor.add_training_example(
                ["Log a [critical issue](priority)"],
                "get_priority",
                "tests",
                "testUser",
                is_integration=False
            )
        )
        assert results[0]["_id"]
        assert results[0]["text"] == "Log a [critical issue](priority)"
        assert results[0]["message"] == "Training Example added"
        intents = processor.get_intents("tests")
        assert any("get_priority" == intent["name"] for intent in intents)
        entities = processor.get_entities("tests")
        assert any("priority" == entity["name"] for entity in entities)
        new_training_example = TrainingExamples.objects(bot="tests").get(
            text="Log a critical issue"
        )
        slots = Slots.objects(bot="tests")
        new_slot = slots.get(name="priority")
        assert slots.__len__() == 3
        assert new_slot.name == "priority"
        assert new_slot.type == "text"
        assert new_training_example.text == "Log a critical issue"

    def test_get_training_examples_with_entities(self):
        processor = MongoProcessor()
        results = list(
            processor.add_training_example(
                ["Make [TKT456](ticketID) a [critical issue](priority)"],
                "get_priority",
                "tests",
                "testUser",
                is_integration=False
            )
        )
        assert results[0]["_id"]
        assert (
                results[0]["text"] == "Make [TKT456](ticketid) a [critical issue](priority)"
        )
        assert results[0]["message"] == "Training Example added"
        actual = list(processor.get_training_examples("get_priority", "tests"))
        slots = Slots.objects(bot="tests")
        new_slot = slots.get(name="ticketid")
        assert any(
            [value["text"] == "Log a [critical issue](priority)" for value in actual]
        )
        assert any(
            [
                value["text"] == "Make [TKT456](ticketid) a [critical issue](priority)"
                for value in actual
            ]
        )
        assert slots.__len__() == 4
        assert new_slot.name == "ticketid"
        assert new_slot.type == "text"
        expected = ["hey", "hello", "hi", "good morning", "good evening", "hey there"]
        actual = list(processor.get_training_examples("greet", "tests"))
        assert actual.__len__() == expected.__len__()
        assert all(a_val["text"] in expected for a_val in actual)

    def test_delete_training_example(self):
        processor = MongoProcessor()
        training_examples = list(processor.get_training_examples(intent="get_priority", bot="tests"))
        expected_length = training_examples.__len__() - 1
        training_example = training_examples[0]
        expected_text = training_example['text']
        processor.remove_document(
            TrainingExamples, training_example['_id'], "tests", "testUser"
        )
        new_training_examples = list(
            processor.get_training_examples(intent="get_priority", bot="tests")
        )
        assert new_training_examples.__len__() == expected_length
        assert any(
            expected_text != example["text"] for example in new_training_examples
        )

    def test_add_training_example_multiple(self):
        processor = MongoProcessor()
        actual = list(processor.add_training_example(["Log a [critical issue](priority)",
                                                      "Make [TKT456](ticketID) a [high issue](priority)"],
                                                     intent="get_priority",
                                                     bot="tests", user="testUser", is_integration=False))
        assert actual[0]['message'] == 'Training Example exists in intent: [\'get_priority\']'
        assert actual[1]['message'] == "Training Example added"

    def test_add_entity(self):
        processor = MongoProcessor()
        assert processor.add_entity("file_text", "tests", "testUser")
        enitity = Entities.objects(bot="tests", status=True).get(name="file_text")
        assert enitity.name == "file_text"

    def test_get_entities(self):
        processor = MongoProcessor()
        expected = ["bot", "priority", "file_text", "ticketid", 'kairon_action_response']
        actual = processor.get_entities("tests")
        assert actual.__len__() == expected.__len__()
        assert all(item["name"] in expected for item in actual)

    def test_add_entity_duplicate(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            assert processor.add_entity("file_text", "tests", "testUser")

    def test_add_entity_duplicate_case_insensitive(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            assert processor.add_entity("File_Text", "tests", "testUser")

    def test_add_none_entity(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_entity(None, "tests", "testUser")

    def test_add_empty_entity(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_entity("", "tests", "testUser")

    def test_add_blank_entity(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_entity("  ", "tests", "testUser")

    def test_add_action(self):
        processor = MongoProcessor()
        assert processor.add_action("get_priority", "test", "testUser")
        action = Actions.objects(bot="test").get(name="get_priority")
        assert action.name == "get_priority"

    def test_add_action_starting_with_utter(self):
        processor = MongoProcessor()
        assert not processor.add_action("utter_get_priority", "test", "testUser")
        with pytest.raises(DoesNotExist):
            Actions.objects(bot="test").get(name="utter_get_priority")

    def test__action_data_object(self):
        assert Actions(name="test_action", bot='test', user='test')

    def test_data_obj_action_empty(self):
        with pytest.raises(ValidationError):
            Actions(name=" ", bot='test', user='test').save()

    def test_data_obj_action_starting_with_utter(self):
        with pytest.raises(ValidationError):
            Actions(name="utter_get_priority", bot='test', user='test').save()

    def test_get_actions(self):
        processor = MongoProcessor()
        actual = processor.get_actions("test")
        assert actual.__len__() == 1
        assert actual[0]['name'] == 'get_priority'

    def test_add_action_duplicate(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            processor.add_action("get_priority", "test", "testUser")

    def test_add_action_duplicate_case_insensitive(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            assert processor.add_action("Utter_Priority", "tests", "testUser") is None

    def test_add_none_action(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_action(None, "tests", "testUser")

    def test_add_empty_action(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_action("", "tests", "testUser")

    def test_add_blank_action(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_action("  ", "tests", "testUser")

    def test_add_text_response(self):
        processor = MongoProcessor()
        assert processor.add_text_response("Great", "utter_Happy", "tests", "testUser")
        response = Responses.objects(
            bot="tests", name="utter_happy", text__text="Great"
        ).get()
        assert response.name == "utter_happy"
        assert response.text.text == "Great"

    def test_add_text_response_case_insensitive(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            processor.add_text_response("Great", "Utter_Happy", "tests", "testUser")

    def test_add_text_response_duplicate(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            processor.add_text_response("Great", "utter_happy", "tests", "testUser")

    def test_get_text_response(self):
        processor = MongoProcessor()
        expected = ["Great, carry on!", "Great"]
        actual = list(processor.get_response("utter_happy", "tests"))
        assert actual.__len__() == expected.__len__()
        assert all(
            item["value"]["text"] in expected
            for item in actual
            if "text" in item["value"]
        )

    def test_get_text_response_empty_utterance(self):
        processor = MongoProcessor()
        actual = list(processor.get_response("", "tests"))
        assert actual.__len__() == 0
        actual = list(processor.get_response(" ", "tests"))
        assert actual.__len__() == 0

    def test_delete_text_response(self):
        processor = MongoProcessor()
        responses = list(processor.get_response(name="utter_happy", bot="tests"))
        expected_length = responses.__len__() - 1
        response = responses[0]
        expected_text = response['value']['text']
        processor.remove_document(Responses, response['_id'], "tests", "testUser")
        actual = list(processor.get_response("utter_happy", "tests"))
        assert actual.__len__() == expected_length
        assert all(
            expected_text != item["value"]["text"]
            for item in actual
            if "text" in item["value"]
        )

    def test_add_none_text_response(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_text_response(None, "utter_happy", "tests", "testUser")

    def test_add_empty_text_Response(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_text_response("", "utter_happy", "tests", "testUser")

    def test_add_blank_text_response(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_text_response("", "utter_happy", "tests", "testUser")

    def test_add_none_response_name(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_text_response("Greet", None, "tests", "testUser")

    def test_add_empty_response_name(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_text_response("Welcome", "", "tests", "testUser")

    def test_add_blank_response_name(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_text_response("Welcome", " ", "tests", "testUser")

    def test_get_session_config(self):
        processor = MongoProcessor()
        session_config = processor.get_session_config("tests")
        assert session_config
        assert all(
            session_config[key] for key in ["sesssionExpirationTime", "carryOverSlots"]
        )

    def test_update_session_config(self):
        processor = MongoProcessor()
        session_config = processor.get_session_config("tests")
        assert session_config
        assert all(
            session_config[key] for key in ["sesssionExpirationTime", "carryOverSlots"]
        )
        id_updated = processor.add_session_config(
            id=session_config["_id"],
            sesssionExpirationTime=30,
            carryOverSlots=False,
            bot="tests",
            user="testUser",
        )
        assert id_updated == session_config["_id"]
        session_config = processor.get_session_config("tests")
        assert session_config["sesssionExpirationTime"] == 30
        assert session_config["carryOverSlots"] is False

    def test_add_session_config_duplicate(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_session_config(
                sesssionExpirationTime=30,
                carryOverSlots=False,
                bot="tests",
                user="testUser",
            )

    def test_add_session_config_empty_id(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_session_config(
                id="",
                sesssionExpirationTime=30,
                carryOverSlots=False,
                bot="tests",
                user="testUser",
            )

    def test_add_session_config(self):
        processor = MongoProcessor()
        id_add = processor.add_session_config(
            sesssionExpirationTime=30, carryOverSlots=False, bot="test", user="testUser"
        )
        assert id_add

    def test_train_model(self):
        model = train_model_for_bot("tests")
        assert model
        folder = os.path.join("models/tests", '*.tar.gz')
        assert len(list(glob.glob(folder))) == 1

    @pytest.mark.asyncio
    async def test_train_model_empty_data(self):
        with pytest.raises(AppException):
            model = await (train_model_from_mongo("test"))
            assert model

    def test_start_training_done(self, monkeypatch):
        def mongo_store(*args, **kwargs):
            return None

        monkeypatch.setattr(Utility, "get_local_mongo_store", mongo_store)
        model_path = start_training("tests", "testUser")
        assert model_path
        model_training = ModelTraining.objects(bot="tests", status="Done")
        assert model_training.__len__() == 1
        assert model_training.first().model_path == model_path

    @elasticmock
    def test_start_training_done_with_intrumentation(self, monkeypatch):
        def mongo_store(*args, **kwargs):
            return None

        monkeypatch.setattr(Utility, "get_local_mongo_store", mongo_store)
        monkeypatch.setitem(Utility.environment["elasticsearch"], 'enable', True)
        monkeypatch.setitem(Utility.environment["elasticsearch"], 'service_name', "kairon")
        monkeypatch.setitem(Utility.environment["elasticsearch"], 'apm_server_url', "http://localhost:8082")

        processor = MongoProcessor()
        loop = asyncio.get_event_loop()
        loop.run_until_complete(processor.save_from_path(
            "./tests/testing_data/initial", bot="test_initial", user="testUser"
        ))

        model_path = start_training("test_initial", "testUser")
        assert model_path
        model_training = ModelTraining.objects(bot="test_initial", status="Done")
        assert model_training.__len__() == 1
        assert model_training.first().model_path == model_path

    def test_start_training_fail(self):
        start_training("test", "testUser")
        model_training = ModelTraining.objects(bot="test", status="Fail")
        assert model_training.__len__() == 1
        assert model_training.first().exception in str("Training data does not exists!")

    def test_add_endpoints(self):
        processor = MongoProcessor()
        config = {}
        processor.add_endpoints(config, bot="tests", user="testUser")
        endpoint = processor.get_endpoints("tests")
        assert endpoint.get("bot_endpoint") is None
        assert endpoint.get("action_endpoint") is None
        assert endpoint.get("tracker") is None

    def test_add_endpoints_add_bot_endpoint_empty_url(self):
        processor = MongoProcessor()
        config = {"bot_endpoint": {"url": ""}}
        with pytest.raises(AppException):
            processor.add_endpoints(config, bot="tests1", user="testUser")
            endpoint = processor.get_endpoints("tests1")
            assert endpoint.get("bot_endpoint") is None
            assert endpoint.get("action_endpoint") is None
            assert endpoint.get("tracker") is None

    def test_add_endpoints_add_bot_endpoint(self):
        processor = MongoProcessor()
        config = {"bot_endpoint": {"url": "http://localhost:5000/"}}
        processor.add_endpoints(config, bot="tests1", user="testUser")
        endpoint = processor.get_endpoints("tests1")
        assert endpoint["bot_endpoint"].get("url") == "http://localhost:5000/"
        assert endpoint.get("action_endpoint") is None
        assert endpoint.get("tracker") is None

    def test_add_endpoints_add_action_endpoint_empty_url(self):
        processor = MongoProcessor()
        config = {"action_endpoint": {"url": ""}}
        with pytest.raises(AppException):
            processor.add_endpoints(config, bot="tests2", user="testUser")
            endpoint = processor.get_endpoints("tests2")
            assert endpoint.get("bot_endpoint") is None
            assert endpoint.get("action_endpoint") is None
            assert endpoint.get("tracker") is None

    def test_add_endpoints_add_action_endpoint(self):
        processor = MongoProcessor()
        config = {"action_endpoint": {"url": "http://localhost:5000/"}}
        processor.add_endpoints(config, bot="tests2", user="testUser")
        endpoint = processor.get_endpoints("tests2")
        assert endpoint.get("bot_endpoint") is None
        assert endpoint.get("action_endpoint").get("url") == "http://localhost:5000/"
        assert endpoint.get("tracker") is None

    def test_add_endpoints_add_history_endpoint(self):
        processor = MongoProcessor()
        config = {
            "history_endpoint": {
                "url": "http://localhost:27017/",
                "token": "conversations"
            }
        }
        processor.add_endpoints(config, bot="tests3", user="testUser")
        endpoint = processor.get_endpoints("tests3")
        assert endpoint.get("bot_endpoint") is None
        assert endpoint.get("action_endpoint") is None
        assert endpoint.get("history_endpoint").get("url") == "http://localhost:27017/"
        assert endpoint.get("history_endpoint").get("token") == "conversations"

    def test_get_endpoints_mask_history_server_token(self):
        processor = MongoProcessor()
        config = {
            "history_endpoint": {
                "url": "http://localhost:27017/",
                "token": "conversations"
            }
        }
        processor.add_endpoints(config, bot="tests3", user="testUser")
        endpoint = processor.get_endpoints("tests3", mask_characters=True)
        assert endpoint.get("bot_endpoint") is None
        assert endpoint.get("action_endpoint") is None
        assert endpoint.get("history_endpoint").get("url") == "http://localhost:27017/"
        assert endpoint.get("history_endpoint").get("token") == "conversati***"

    def test_get_history_server_endpoint(self):
        processor = MongoProcessor()
        endpoint = processor.get_history_server_endpoint("tests3")
        assert endpoint.get("url") == "http://localhost:27017/"
        assert endpoint.get("token") == "conversations"
        assert endpoint.get("type") == 'user'

    def test_get_kairon_history_server_endpoint(self):
        processor = MongoProcessor()
        endpoint = processor.get_history_server_endpoint("test_bot")
        assert endpoint.get("url") == "http://localhost:8083"
        assert endpoint.get("token")
        assert endpoint.get("type") == 'kairon'

    def test_update_endpoints(self):
        processor = MongoProcessor()
        config = {
            "action_endpoint": {"url": "http://localhost:8000/"},
            "bot_endpoint": {"url": "http://localhost:5000/"},
            "history_endpoint": {
                "url": "http://localhost:27019/",
                "token": "kairon-history-user",
            },
        }
        processor.add_endpoints(config, bot="tests", user="testUser")
        endpoint = processor.get_endpoints("tests")
        assert endpoint.get("bot_endpoint").get("url") == "http://localhost:5000/"
        assert endpoint.get("action_endpoint").get("url") == "http://localhost:8000/"
        assert endpoint.get("history_endpoint").get("url") == "http://localhost:27019/"
        assert endpoint.get("history_endpoint").get("token") == "kairon-history-user"

    def test_update_endpoints_token_less_than_8_chars(self):
        processor = MongoProcessor()
        config = {
            "action_endpoint": {"url": "http://localhost:8000/"},
            "bot_endpoint": {"url": "http://localhost:5000/"},
            "history_endpoint": {
                "url": "http://localhost:27019/",
                "token": "kairon",
            },
        }
        with pytest.raises(AppException, match='token must contain at least 8 characters'):
            processor.add_endpoints(config, bot="tests", user="testUser")
        endpoint = processor.get_endpoints("tests")
        assert endpoint.get("bot_endpoint").get("url") == "http://localhost:5000/"
        assert endpoint.get("action_endpoint").get("url") == "http://localhost:8000/"
        assert endpoint.get("history_endpoint").get("url") == "http://localhost:27019/"
        assert endpoint.get("history_endpoint").get("token") == "kairon-history-user"

    def test_update_endpoints_token_with_space(self):
        processor = MongoProcessor()
        config = {
            "action_endpoint": {"url": "http://localhost:8000/"},
            "bot_endpoint": {"url": "http://localhost:5000/"},
            "history_endpoint": {
                "url": "http://localhost:27019/",
                "token": "kairon token",
            },
        }
        with pytest.raises(AppException, match='token cannot contain spaces'):
            processor.add_endpoints(config, bot="tests", user="testUser")
        endpoint = processor.get_endpoints("tests")
        assert endpoint.get("bot_endpoint").get("url") == "http://localhost:5000/"
        assert endpoint.get("action_endpoint").get("url") == "http://localhost:8000/"
        assert endpoint.get("history_endpoint").get("url") == "http://localhost:27019/"
        assert endpoint.get("history_endpoint").get("token") == "kairon-history-user"

    def test_update_endpoints_any(self):
        processor = MongoProcessor()
        config = {
            "action_endpoint": {"url": "http://127.0.0.1:8000/"},
            "bot_endpoint": {"url": "http://127.0.0.1:5000/"},
        }
        processor.add_endpoints(config, bot="tests", user="testUser")
        endpoint = processor.get_endpoints("tests")
        assert endpoint.get("bot_endpoint").get("url") == "http://127.0.0.1:5000/"
        assert endpoint.get("action_endpoint").get("url") == "http://127.0.0.1:8000/"
        assert endpoint.get("history_endpoint").get("url") == "http://localhost:27019/"
        assert endpoint.get("history_endpoint").get("token") == "kairon-history-user"

    def test_delete_endpoints(self):
        processor = MongoProcessor()
        config = {
            "bot_endpoint": {"url": "http://127.0.0.1:5000/"},
            "action_endpoint": {"url": "http://127.0.0.1:8000/"},
            "history_endpoint": {
                "url": "http://localhost:27019/",
                "token": "kairon-history-user",
            },
        }
        processor.add_endpoints(config, bot="test_delete_endpoint", user="testUser")

        processor.delete_endpoint('test_delete_endpoint', ENDPOINT_TYPE.BOT_ENDPOINT.value)
        endpoint = processor.get_endpoints("test_delete_endpoint")
        assert not endpoint.get(ENDPOINT_TYPE.BOT_ENDPOINT)
        assert endpoint.get("action_endpoint").get("url") == "http://127.0.0.1:8000/"
        assert endpoint.get("history_endpoint").get("url") == "http://localhost:27019/"

        processor.delete_endpoint('test_delete_endpoint', ENDPOINT_TYPE.ACTION_ENDPOINT.value)
        endpoint = processor.get_endpoints("test_delete_endpoint")
        assert not endpoint.get(ENDPOINT_TYPE.BOT_ENDPOINT)
        assert not endpoint.get(ENDPOINT_TYPE.ACTION_ENDPOINT)
        assert endpoint.get("history_endpoint").get("url") == "http://localhost:27019/"

        processor.delete_endpoint('test_delete_endpoint', ENDPOINT_TYPE.HISTORY_ENDPOINT.value)
        endpoint = processor.get_endpoints("test_delete_endpoint")
        assert not endpoint.get(ENDPOINT_TYPE.BOT_ENDPOINT.value)
        assert not endpoint.get(ENDPOINT_TYPE.ACTION_ENDPOINT.value)
        assert not endpoint.get(ENDPOINT_TYPE.HISTORY_ENDPOINT.value)

    def test_delete_endpoints_none(self):
        processor = MongoProcessor()
        config = {
            "bot_endpoint": {"url": "http://127.0.0.1:5000/"},
            "action_endpoint": {"url": "http://127.0.0.1:8000/"},
            "history_endpoint": {
                "url": "http://localhost:27019/",
                "token": "kairon-history-user",
            },
        }
        processor.add_endpoints(config, bot="test_delete_endpoint", user="testUser")

        with pytest.raises(AppException, match='endpoint_type is required for deletion'):
            processor.delete_endpoint('test_delete_endpoint', None)

    def test_delete_endpoints_not_exists(self):
        processor = MongoProcessor()
        with pytest.raises(AppException) as e:
            processor.delete_endpoint('test_delete_endpoints_not_exists', ENDPOINT_TYPE.BOT_ENDPOINT.value)
        assert str(e).__contains__("No Endpoint configured")

    def test_delete_endpoints_type_not_exists(self):
        processor = MongoProcessor()
        config = {
            "bot_endpoint": {"url": "http://127.0.0.1:5000/"},
        }
        processor.add_endpoints(config, bot="test_delete_endpoints_type_not_exists", user="testUser")

        with pytest.raises(AppException, match='Endpoint not configured'):
            processor.delete_endpoint('test_delete_endpoints_type_not_exists', ENDPOINT_TYPE.ACTION_ENDPOINT.value)

        processor.delete_endpoint('test_delete_endpoints_type_not_exists', ENDPOINT_TYPE.BOT_ENDPOINT.value)
        endpoint = processor.get_endpoints("test_delete_endpoints_type_not_exists")
        assert not endpoint.get(ENDPOINT_TYPE.BOT_ENDPOINT.value)

        with pytest.raises(AppException, match='Endpoint not configured') as e:
            processor.delete_endpoint('test_delete_endpoints_type_not_exists', ENDPOINT_TYPE.HISTORY_ENDPOINT.value)

    def test_get_kairon_history_server_endpoint_none_configured(self):
        processor = MongoProcessor()
        Utility.environment['history_server']['url'] = None
        with pytest.raises(AppException, match='No history server endpoint configured'):
            endpoint = processor.get_history_server_endpoint("test_bot")

    def test_download_data_files(self):
        processor = MongoProcessor()
        file = processor.download_files("tests")
        assert file.endswith(".zip")

    def test_get_utterance_from_intent(self):
        processor = MongoProcessor()
        response = processor.get_utterance_from_intent("deny", "tests")
        assert response[0] == "utter_goodbye"
        assert response[1] == UTTERANCE_TYPE.BOT

    def test_get_utterance_from_empty_intent(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.get_utterance_from_intent("", "tests")

    def test_get_stories(self):
        processor = MongoProcessor()
        stories = list(processor.get_stories("tests"))
        assert stories.__len__() == 8
        assert stories[0]['name'] == 'happy path'
        assert stories[0]['type'] == 'STORY'
        assert stories[0]['steps'][0]['name'] == 'greet'
        assert stories[0]['steps'][0]['type'] == 'INTENT'
        assert stories[0]['steps'][1]['name'] == 'utter_greet'
        assert stories[0]['steps'][1]['type'] == 'BOT'
        assert stories[0]['template_type'] == 'CUSTOM'

    def test_edit_training_example_duplicate(self):
        processor = MongoProcessor()
        examples = list(processor.get_training_examples("greet", "tests"))
        with pytest.raises(AppException):
            processor.edit_training_example(examples[0]["_id"], example="hey there", intent="greet", bot="tests",
                                            user="testUser")

    def test_edit_training_example_does_not_exists(self):
        processor = MongoProcessor()
        examples = list(processor.get_training_examples("greet", "tests"))
        with pytest.raises(AppException):
            processor.edit_training_example(examples[0]["_id"], example="hey there", intent="happy", bot="tests",
                                            user="testUser")

    def test_edit_training_example(self):
        processor = MongoProcessor()
        examples = list(processor.get_training_examples("greet", "tests"))
        processor.edit_training_example(examples[0]["_id"], example="hey, there", intent="greet", bot="tests",
                                        user="testUser")
        examples = list(processor.get_training_examples("greet", "tests"))
        assert any(example['text'] == "hey, there" for example in examples)

    def test_edit_training_example_case_insensitive(self):
        processor = MongoProcessor()
        examples = list(processor.get_training_examples("greet", "tests"))
        processor.edit_training_example(examples[0]["_id"], example="hello, there", intent="greet", bot="tests",
                                        user="testUser")
        examples = list(processor.get_training_examples("greet", "tests"))
        assert any(example['text'] == "hello, there" for example in examples)

    def test_edit_training_example_with_entities(self):
        processor = MongoProcessor()
        examples = list(processor.get_training_examples("greet", "tests"))
        processor.edit_training_example(examples[0]["_id"], example="[Meghalaya](location) India", intent="greet",
                                        bot="tests", user="testUser")
        examples = list(processor.get_training_examples("greet", "tests"))
        assert any(example['text'] == "[Meghalaya](location) India" for example in examples)

    def test_edit_same_training_example_with_entities(self):
        processor = MongoProcessor()
        examples = list(
            processor.add_training_example(["What is the weather today"], intent="greet", bot="tests", user="test",
                                           is_integration=False))
        processor.edit_training_example(examples[0]["_id"], example="What is the weather [today](date)", intent="greet",
                                        bot="tests", user="testUser")
        examples = list(processor.get_training_examples("greet", "tests"))
        assert any(example['text'] == "What is the weather [today](date)" for example in examples)

    def test_edit_responses_duplicate(self):
        processor = MongoProcessor()
        responses = list(processor.get_response("utter_happy", "tests"))
        with pytest.raises(AppException):
            processor.edit_text_response(responses[0]["_id"], "Great, carry on!", name="utter_happy", bot="tests",
                                         user="testUser")

    def test_edit_responses_does_not_exist(self):
        processor = MongoProcessor()
        responses = list(processor.get_response("utter_happy", "tests"))
        with pytest.raises(AppException):
            processor.edit_text_response(responses[0]["_id"], "Great, carry on!", name="utter_greet", bot="tests",
                                         user="testUser")

    def test_edit_responses_empty_response(self):
        processor = MongoProcessor()
        responses = list(processor.get_response("utter_happy", "tests"))
        with pytest.raises(ValidationError):
            processor.edit_text_response(responses[0]["_id"], "", name="utter_happy", bot="tests",
                                         user="testUser")
        with pytest.raises(ValidationError):
            processor.edit_text_response(responses[0]["_id"], " ", name="utter_happy", bot="tests",
                                         user="testUser")

    def test_edit_responses(self):
        processor = MongoProcessor()
        responses = list(processor.get_response("utter_happy", "tests"))
        processor.edit_text_response(responses[0]["_id"], "Great!", name="utter_happy", bot="tests", user="testUser")
        responses = list(processor.get_response("utter_happy", "tests"))
        assert any(response['value']['text'] == "Great!" for response in responses if "text" in response['value'])

    def test_edit_responses_case_insensitivity(self):
        processor = MongoProcessor()
        responses = list(processor.get_response("utter_happy", "tests"))
        processor.edit_text_response(responses[0]["_id"], "That's Great!", name="utter_happy", bot="tests",
                                     user="testUser")
        responses = list(processor.get_response("utter_happy", "tests"))
        assert any(
            response['value']['text'] == "That's Great!" for response in responses if "text" in response['value'])

    @responses.activate
    def test_start_training_done_using_event(self, monkeypatch):
        responses.add(
            responses.POST,
            "http://localhost/train",
            status=200,
            match=[responses.json_params_matcher({"bot": "test_event", "user": "testUser", "token": None})],
        )
        monkeypatch.setitem(Utility.environment['model']['train'], "event_url", "http://localhost/train")
        model_path = start_training("test_event", "testUser")
        assert model_path is None

    @responses.activate
    def test_start_training_done_using_event_and_token(self, monkeypatch):
        token = Authentication.create_access_token(data={"sub": "test@gmail.com"})
        responses.add(
            responses.POST,
            "http://localhost/train",
            status=200,
            match=[responses.json_params_matcher({"bot": "test_event_with_token", "user": "testUser", "token": token})],
        )
        monkeypatch.setitem(Utility.environment['model']['train'], "event_url", "http://localhost/train")
        model_path = start_training("test_event_with_token", "testUser", token)
        assert model_path is None

    @responses.activate
    def test_start_training_done_reload_event(self, monkeypatch):
        token = Authentication.create_access_token(data={"sub": "test@gmail.com"})
        bot = "tests"
        responses.add(
            responses.GET,
            f"http://localhost/api/bot/{bot}/model/reload",
            json='{"message": "Reloading Model!"}',
            status=200
        )
        monkeypatch.setitem(Utility.environment['model']['agent'], "url", "http://localhost/")
        model_path = start_training("tests", "testUser", token)
        assert model_path

    @responses.activate
    def test_start_training_done_reload_event_without_token(self, monkeypatch):
        monkeypatch.setitem(Utility.environment['model']['agent'], "url", "http://localhost/")
        responses.add(
            responses.GET,
            f"http://localhost/api/bot/tests/model/reload",
            json='{"message": "Reloading Model!"}',
            status=200
        )
        model_path = start_training("tests", "testUser")
        assert model_path

    def test_add_training_data(self):
        training_data = [
            models.TrainingData(intent="intent1",
                                training_examples=["example1", "example2"],
                                response="response1"),
            models.TrainingData(intent="intent2",
                                training_examples=["example3", "example4"],
                                response="response2")
        ]
        processor = MongoProcessor()
        processor.add_training_data(training_data, "training_bot", "training_user", False)
        assert Intents.objects(name="intent1").get() is not None
        assert Intents.objects(name="intent2").get() is not None
        training_examples = list(TrainingExamples.objects(intent="intent1"))
        assert training_examples is not None
        assert len(training_examples) == 2
        training_examples = list(TrainingExamples.objects(intent="intent2"))
        assert len(training_examples) == 2
        assert Responses.objects(name="utter_intent1") is not None
        assert Responses.objects(name="utter_intent2") is not None
        story = Stories.objects(block_name="path_intent1").get()
        assert story is not None
        assert story['events'][0]['name'] == 'intent1'
        assert story['events'][0]['type'] == StoryEventType.user
        assert story['events'][1]['name'] == "utter_intent1"
        assert story['events'][1]['type'] == StoryEventType.action
        story = Stories.objects(block_name="path_intent2").get()
        assert story is not None

    def test_add_training_data_with_invalid_training_example(self):
        training_data = [
            models.TrainingData(intent="intent3",
                                training_examples=[" ", "example"],
                                response="response3")]
        processor = MongoProcessor()
        processor.add_training_data(training_data, "training_bot", "training_user", False)
        assert Intents.objects(name="intent3").get() is not None
        training_examples = list(TrainingExamples.objects(intent="intent3"))
        assert training_examples is not None
        assert len(training_examples) == 1
        assert Responses.objects(name="utter_intent3") is not None
        story = Stories.objects(block_name="path_intent3").get()
        assert story is not None
        assert story['events'][0]['name'] == 'intent3'
        assert story['events'][0]['type'] == StoryEventType.user
        assert story['events'][1]['name'] == "utter_intent3"
        assert story['events'][1]['type'] == StoryEventType.action
        story = Stories.objects(block_name="path_intent3").get()
        assert story is not None

    def test_add_training_data_with_intent_exists(self):
        training_data = [
            models.TrainingData(intent="intent3",
                                training_examples=["example for intent3"],
                                response="response3")]
        processor = MongoProcessor()
        processor.add_training_data(training_data, "training_bot", "training_user", False)
        assert Intents.objects(name="intent3").get() is not None
        training_examples = list(TrainingExamples.objects(intent="intent3"))
        assert training_examples is not None
        assert len(training_examples) == 2
        assert Responses.objects(name="utter_intent3") is not None
        story = Stories.objects(block_name="path_intent3").get()
        assert story is not None
        assert story['events'][0]['name'] == 'intent3'
        assert story['events'][0]['type'] == StoryEventType.user
        assert story['events'][1]['name'] == "utter_intent3"
        assert story['events'][1]['type'] == StoryEventType.action
        story = Stories.objects(block_name="path_intent3").get()
        assert story is not None

    def test_delete_response(self):
        processor = MongoProcessor()
        intent = "test_delete_response_with_story"
        utterance = "utter_" + intent
        story = "path_" + intent
        bot = "testBot"
        user = "testUser"
        utter_intentA_1_id = processor.add_response({"text": "demo_response"}, utterance, bot, user)
        utter_intentA_2_id = processor.add_response({"text": "demo_response2"}, utterance, bot, user)
        resp = processor.get_response(utterance, bot)
        assert len(list(resp)) == 2
        processor.delete_response(utter_intentA_1_id, bot, user)
        resp = processor.get_response(utterance, bot)
        assert len(list(resp)) == 1
        assert Utterances.objects(name=utterance, bot=bot, status=True).get()
        processor.delete_response(utter_intentA_2_id, bot, user)
        resp = processor.get_response(utterance, bot)
        assert len(list(resp)) == 0
        with pytest.raises(DoesNotExist):
            Utterances.objects(name=utterance, bot=bot, status=True).get()

    def test_delete_response_non_existing(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.delete_response("0123456789ab0123456789ab", "testBot",
                                      "testUser")

    def test_delete_response_empty(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.delete_response(" ", "testBot", "testUser")

    def test_delete_utterance(self):
        processor = MongoProcessor()
        utterance = "test_delete_utterance"
        bot = "testBot"
        user = "testUser"
        processor.add_response({"text": "demo_response1"}, utterance, bot, user)
        Utterances.objects(name=utterance, bot=bot, status=True).get()
        processor.delete_utterance(utterance, bot, user)
        with pytest.raises(DoesNotExist):
            Utterances.objects(name=utterance, bot=bot, status=True).get()

    def test_delete_utterance_non_existing(self):
        processor = MongoProcessor()
        utterance = "test_delete_utterance_non_existing"
        bot = "testBot"
        user = "testUser"
        with pytest.raises(AppException):
            processor.delete_utterance(utterance, bot, user)

    def test_delete_utterance_empty(self):
        processor = MongoProcessor()
        utterance = " "
        bot = "testBot"
        user = "testUser"
        with pytest.raises(AppException):
            processor.delete_utterance(utterance, bot, user)

    def test_delete_utterance_name_having_no_responses(self):
        processor = MongoProcessor()
        utterance = "test_delete_utterance_name_having_no_responses"
        bot = "testBot"
        user = "testUser"
        processor.add_utterance_name(utterance, bot, user)
        processor.delete_utterance(utterance, bot, user)
        with pytest.raises(DoesNotExist):
            Utterances.objects(name__iexact=utterance, bot=bot, status=True).get()

    def test_add_slot(self):
        processor = MongoProcessor()
        bot = 'test_add_slot'
        user = 'test_user'
        processor.add_slot({"name": "bot", "type": "unfeaturized", "influence_conversation": True}, bot, user,
                           raise_exception_if_exists=False)
        slot = Slots.objects(name__iexact='bot', bot=bot, user=user).get()
        assert slot['name'] == 'bot'
        assert slot['type'] == 'unfeaturized'
        assert slot['initial_value'] is None
        assert slot['influence_conversation']
        assert Entities.objects(name='bot', bot=bot, user=user, status=True).get()

        processor.add_slot({"name": "bot", "type": "any", "initial_value": bot, "influence_conversation": False}, bot,
                           user, raise_exception_if_exists=False)
        slot = Slots.objects(name__iexact='bot', bot=bot, user=user).get()
        assert slot['name'] == 'bot'
        assert slot['type'] == 'any'
        assert slot['initial_value'] == bot
        assert not slot['influence_conversation']
        assert Entities.objects(name='bot', bot=bot, user=user, status=True).get()

    def test_add_duplicate_slot(self):
        processor = MongoProcessor()
        bot = 'test_add_slot'
        user = 'test_user'

        with pytest.raises(AppException):
            msg = processor.add_slot(
                {"name": "bot", "type": "any", "initial_value": bot, "influence_conversation": False}, bot, user,
                raise_exception_if_exists=True)
            assert msg == 'Slot already exists!'
            assert Entities.objects(name='bot', bot=bot, user=user, status=True).get()

    def test_add_empty_slot(self):
        processor = MongoProcessor()
        bot = 'test_add_slot'
        user = 'test_user'

        with pytest.raises(AppException):
            msg = processor.add_slot(
                {"name": "", "type": "invalid", "initial_value": bot, "influence_conversation": False}, bot, user,
                raise_exception_if_exists=False)
            assert msg == 'Slot Name cannot be empty or blank spaces'

    def test_add_invalid_slot_type(self):
        processor = MongoProcessor()
        bot = 'test_add_slot'
        user = 'test_user'

        with pytest.raises(AppException):
            msg = processor.add_slot(
                {"name": "bot", "type": "invalid", "initial_value": bot, "influence_conversation": False}, bot, user,
                raise_exception_if_exists=False)
            assert msg == 'Invalid slot type.'

    def test_min_max_for_other_slot_types(self):
        processor = MongoProcessor()
        bot = 'test_add_slot'
        user = 'test_user'

        for slot_type in SLOT_TYPE:
            if slot_type == SLOT_TYPE.FLOAT or slot_type == SLOT_TYPE.CATEGORICAL:
                continue
            else:
                processor.add_slot({"name": "bot", "type": slot_type, "max_value": 0.5, "min_value": 0.1,
                                    "influence_conversation": True}, bot, user, raise_exception_if_exists=False)
                slot = Slots.objects(name__iexact='bot', bot=bot, user=user).get()
                assert slot['name'] == 'bot'
                assert slot['type'] == slot_type
                assert slot['max_value'] is None
                assert slot['min_value'] is None

    def test_add_float_slot(self):
        processor = MongoProcessor()
        bot = 'test_add_slot'
        user = 'test_user'
        processor.add_slot({"name": "bot", "type": "float", "initial_value": 0.2, "max_value": 0.5, "min_value": 0.1,
                            "influence_conversation": True}, bot, user, raise_exception_if_exists=False)
        slot = Slots.objects(name__iexact='bot', bot=bot, user=user).get()
        assert slot['name'] == 'bot'
        assert slot['type'] == 'float'
        assert slot['initial_value'] == 0.2
        assert slot['influence_conversation']
        assert slot['max_value'] == 0.5
        assert slot['min_value'] == 0.1

    def test_values_for_other_slot_types(self):
        processor = MongoProcessor()
        bot = 'test_add_slot'
        user = 'test_user'

        for slot_type in SLOT_TYPE:

            if slot_type == SLOT_TYPE.CATEGORICAL:
                continue
            else:
                processor.add_slot(
                    {"name": "bot", "type": slot_type, "values": ["red", "blue"],
                     "influence_conversation": True}, bot, user, raise_exception_if_exists=False)
                slot = Slots.objects(name__iexact='bot', bot=bot, user=user).get()
                assert slot['name'] == 'bot'
                assert slot['type'] == slot_type
                assert slot['values'] is None
                assert slot['influence_conversation']

    def test_add_categorical_slot(self):
        processor = MongoProcessor()
        bot = 'test_add_slot'
        user = 'test_user'
        processor.add_slot({"name": "color", "type": "categorical", "values": ["red", "blue"],
                            "influence_conversation": True}, bot, user, raise_exception_if_exists=False)
        slot = Slots.objects(name__iexact='color', bot=bot, user=user).get()
        assert slot['name'] == 'color'
        assert slot['type'] == 'categorical'
        assert slot['values'] == ["red", "blue"]
        assert slot['influence_conversation']

    def test_add_categorical_slot_without_values(self):
        processor = MongoProcessor()
        bot = 'test_add_slot'
        user = 'test_user'
        with pytest.raises(ValidationError):
            msg = processor.add_slot({"name": "bot", "type": "categorical",
                                      "influence_conversation": True}, bot, user, raise_exception_if_exists=False)
            assert msg == "CategoricalSlot must have list of categories in values field"

    def test_delete_slot(self):
        processor = MongoProcessor()
        bot = 'test_add_slot'
        user = 'test_user'

        processor.delete_slot(slot_name='color', bot=bot, user=user)

        slot = Slots.objects(name__iexact='color', bot=bot, user=user).get()
        assert not Entities.objects(name='color', bot=bot, user=user, status=True)
        assert slot.status is False

    def test_delete_slot_default_slot(self):
        processor = MongoProcessor()
        bot = 'test_add_slot'
        user = 'test_user'

        with pytest.raises(AppException, match='Default kAIron slot deletion not allowed'):
            processor.delete_slot(slot_name='bot', bot=bot, user=user)

        with pytest.raises(AppException, match='Default kAIron slot deletion not allowed'):
            processor.delete_slot(slot_name='kairon_action_response', bot=bot, user=user)

    def test_delete_inexistent_slot(self):
        processor = MongoProcessor()
        bot = 'test_add_slot'
        user = 'test_user'

        with pytest.raises(AppException) as e:
            processor.delete_slot(slot_name='bot_doesnt_exist', bot=bot, user=user)
        assert str(e).__contains__('Slot does not exist.')

    def test_delete_empty_slot(self):
        processor = MongoProcessor()
        bot = 'test_add_slot'
        user = 'test_user'

        with pytest.raises(AppException) as e:
            processor.delete_slot(slot_name='', bot=bot, user=user)
        assert str(e).__contains__('Slot does not exist.')

    def test_delete_entity_not_exists(self):
        processor = MongoProcessor()
        with pytest.raises(AppException, match='Entity not found'):
            processor.delete_entity('entity_not_exists', 'test_bot', 'test_user')

    def test_fetch_rule_block_names(self):
        processor = MongoProcessor()
        Rules(
            block_name="rule1",
            condition_events_indices=[],
            start_checkpoints=["START"],
            end_checkpoints=["END"],
            events=[StoryEvents(name="greet", type="user"), StoryEvents(name="utter_greet", type="action")],
            bot="test_bot",
            user="rule_creator",
        ).save()
        Rules(
            block_name="rule2",
            condition_events_indices=[],
            start_checkpoints=["START"],
            end_checkpoints=["END"],
            events=[StoryEvents(name="greet", type="user"), StoryEvents(name="utter_greet", type="action")],
            bot="test_bot",
            user="rule_creator",
        ).save()
        block_names = processor.fetch_rule_block_names("test_bot")
        assert block_names[0] == "rule1"
        assert block_names[1] == "rule2"

    def test_fetch_rule_block_names_no_rules_present(self):
        processor = MongoProcessor()
        block_names = processor.fetch_rule_block_names("rule_creator")
        assert not block_names

    def test_save_rules(self):
        processor = MongoProcessor()
        intent = {
            STORY_EVENT.NAME.value: "greet",
            STORY_EVENT.CONFIDENCE.value: 1.0,
        }
        events = [UserUttered(text="greet", intent=intent),
                  ActionExecuted(action_name="utter_greet")]
        story_steps = [RuleStep(block_name="rule1",
                                start_checkpoints=[Checkpoint("START")],
                                end_checkpoints=[Checkpoint("END")],
                                events=events,
                                condition_events_indices={0}),
                       RuleStep(block_name="rule2",
                                start_checkpoints=[Checkpoint("START")],
                                end_checkpoints=[Checkpoint("END")],
                                events=events,
                                condition_events_indices={0})
                       ]
        processor.save_rules(story_steps, "test_save_rules", "rules_creator")
        rules = list(Rules.objects(bot="test_save_rules", user="rules_creator", status=True))
        assert rules[0]['block_name'] == "rule1"
        assert rules[0]['condition_events_indices'] == [0]
        assert rules[0]['start_checkpoints'] == ["START"]
        assert rules[0]['end_checkpoints'] == ["END"]
        assert rules[0]['events'][0]['name'] == "greet"
        assert rules[0]['events'][0]['type'] == "user"
        assert not rules[0]['events'][0]['value']
        assert rules[0]['events'][1]['name'] == "utter_greet"
        assert rules[0]['events'][1]['type'] == "action"
        assert not rules[0]['events'][1]['value']
        assert rules[1]['block_name'] == "rule2"

    def test_save_rules_already_present(self):
        processor = MongoProcessor()
        events = [UserUttered(text="greet"),
                  ActionExecuted(action_name="utter_greet")]
        Rules(block_name="rule2",
              start_checkpoints=["START"],
              end_checkpoints=["END"],
              events=[StoryEvents(name="greet", type="user"),
                      StoryEvents(name="utter_greet", type="action")],
              condition_events_indices={0}, bot="test_save_rules_already_present", user="rules_creator").save()
        story_steps = [RuleStep(block_name="rule1",
                                start_checkpoints=[Checkpoint("START")],
                                end_checkpoints=[Checkpoint("END")],
                                events=events,
                                condition_events_indices={0}),
                       RuleStep(block_name="rule2",
                                start_checkpoints=[Checkpoint("START")],
                                end_checkpoints=[Checkpoint("END")],
                                events=events,
                                condition_events_indices={0})
                       ]
        processor.save_rules(story_steps, "test_save_rules_already_present", "rules_creator")
        rules = list(Rules.objects(bot="test_save_rules_already_present", user="rules_creator", status=True))
        assert len(rules) == 2
        assert rules[0]['block_name'] == "rule2"
        assert rules[0]['condition_events_indices'] == [0]
        assert rules[0]['start_checkpoints'] == ["START"]
        assert rules[0]['end_checkpoints'] == ["END"]
        assert rules[0]['events'][0]['name'] == "greet"
        assert rules[0]['events'][0]['type'] == "user"
        assert not rules[0]['events'][0]['value']
        assert rules[0]['events'][1]['name'] == "utter_greet"
        assert rules[0]['events'][1]['type'] == "action"
        assert not rules[0]['events'][1]['value']
        assert rules[1]['block_name'] == "rule1"

    def test_get_rules_for_training(self):
        Rules(
            block_name="rule1",
            condition_events_indices=[],
            start_checkpoints=["START"],
            end_checkpoints=["END"],
            events=[StoryEvents(name="greet", type="user"), StoryEvents(name="utter_greet", type="action")],
            bot="test_get_rules_for_training",
            user="rule_creator",
        ).save()
        Rules(
            block_name="rule2",
            condition_events_indices=[],
            start_checkpoints=["START"],
            end_checkpoints=["END"],
            events=[StoryEvents(name="greet", type="user"), StoryEvents(name="utter_greet", type="action")],
            bot="test_get_rules_for_training",
            user="rule_creator",
        ).save()
        processor = MongoProcessor()
        rules = processor.get_rules_for_training("test_get_rules_for_training")
        assert isinstance(rules, StoryGraph)
        assert len(rules.story_steps) == 2

    def test_get_rules_no_rules_present(self):
        processor = MongoProcessor()
        rules = processor.get_rules_for_training("test_get_rules_no_rules_present")
        assert not rules.story_steps

    def test_delete_rules(self):
        processor = MongoProcessor()
        rules = (Rules.objects(bot="test_save_rules_already_present", user="rules_creator", status=True))
        assert rules
        processor.delete_rules("test_save_rules_already_present", "rules_creator")
        rules = (Rules.objects(bot="test_save_rules_already_present", user="rules_creator", status=True))
        assert not rules

    def test_delete_rules_no_rules(self):
        processor = MongoProcessor()
        rules = (Rules.objects(bot="test_save_rules_already_present", user="rules_creator", status=True))
        assert not rules
        processor.delete_rules("test_save_rules_already_present", "rules_creator")

    @pytest.mark.asyncio
    async def test_upload_and_save(self):
        processor = MongoProcessor()
        nlu_content = "## intent:greet\n- hey\n- hello".encode()
        stories_content = "## greet\n* greet\n- utter_offer_help\n- action_restart".encode()
        config_content = "language: en\npipeline:\n- name: WhitespaceTokenizer\n- name: RegexFeaturizer\n- name: LexicalSyntacticFeaturizer\n- name: CountVectorsFeaturizer\n- analyzer: char_wb\n  max_ngram: 4\n  min_ngram: 1\n  name: CountVectorsFeaturizer\n- epochs: 5\n  name: DIETClassifier\n- name: EntitySynonymMapper\n- epochs: 5\n  name: ResponseSelector\npolicies:\n- name: MemoizationPolicy\n- epochs: 5\n  max_history: 5\n  name: TEDPolicy\n- name: RulePolicy\n- core_threshold: 0.3\n  fallback_action_name: action_small_talk\n  name: FallbackPolicy\n  nlu_threshold: 0.75\n".encode()
        domain_content = "intents:\n- greet\nresponses:\n  utter_offer_help:\n  - text: 'how may i help you'\nactions:\n- utter_offer_help\n".encode()
        nlu = UploadFile(filename="nlu.yml", file=BytesIO(nlu_content))
        stories = UploadFile(filename="stories.md", file=BytesIO(stories_content))
        config = UploadFile(filename="config.yml", file=BytesIO(config_content))
        domain = UploadFile(filename="domain.yml", file=BytesIO(domain_content))
        await processor.upload_and_save(nlu, domain, stories, config, None, None, "test_upload_and_save",
                                        "rules_creator")
        assert len(list(Intents.objects(bot="test_upload_and_save", user="rules_creator"))) == 6
        assert len(list(Stories.objects(bot="test_upload_and_save", user="rules_creator"))) == 1
        assert len(list(Responses.objects(bot="test_upload_and_save", user="rules_creator"))) == 3
        assert len(
            list(TrainingExamples.objects(intent="greet", bot="test_upload_and_save", user="rules_creator"))) == 2

    @pytest.mark.asyncio
    async def test_upload_and_save_with_rules(self):
        processor = MongoProcessor()
        nlu_content = "## intent:greet\n- hey\n- hello".encode()
        stories_content = "## greet\n* greet\n- utter_offer_help\n- action_restart".encode()
        config_content = "language: en\npipeline:\n- name: WhitespaceTokenizer\n- name: RegexFeaturizer\n- name: LexicalSyntacticFeaturizer\n- name: CountVectorsFeaturizer\n- analyzer: char_wb\n  max_ngram: 4\n  min_ngram: 1\n  name: CountVectorsFeaturizer\n- epochs: 5\n  name: DIETClassifier\n- name: EntitySynonymMapper\n- epochs: 5\n  name: ResponseSelector\npolicies:\n- name: MemoizationPolicy\n- epochs: 5\n  max_history: 5\n  name: TEDPolicy\n- name: RulePolicy\n- core_threshold: 0.3\n  fallback_action_name: action_small_talk\n  name: FallbackPolicy\n  nlu_threshold: 0.75\n".encode()
        domain_content = "intents:\n- greet\nresponses:\n  utter_offer_help:\n  - text: 'how may i help you'\nactions:\n- utter_offer_help\n".encode()
        rules_content = "rules:\n\n- rule: Only say `hello` if the user provided a location\n  condition:\n  - slot_was_set:\n    - location: true\n  steps:\n  - intent: greet\n  - action: utter_greet\n".encode()
        nlu = UploadFile(filename="nlu.yml", file=BytesIO(nlu_content))
        stories = UploadFile(filename="stories.md", file=BytesIO(stories_content))
        config = UploadFile(filename="config.yml", file=BytesIO(config_content))
        domain = UploadFile(filename="domain.yml", file=BytesIO(domain_content))
        rules = UploadFile(filename="rules.yml", file=BytesIO(rules_content))
        await processor.upload_and_save(nlu, domain, stories, config, rules, None, "test_upload_and_save",
                                        "rules_creator")
        assert len(list(Intents.objects(bot="test_upload_and_save", user="rules_creator", status=True))) == 6
        assert len(list(Stories.objects(bot="test_upload_and_save", user="rules_creator", status=True))) == 1
        assert len(list(Responses.objects(bot="test_upload_and_save", user="rules_creator", status=True))) == 3
        assert len(
            list(TrainingExamples.objects(intent="greet", bot="test_upload_and_save", user="rules_creator",
                                          status=True))) == 2
        assert len(list(Rules.objects(bot="test_upload_and_save", user="rules_creator"))) == 2

    @pytest.mark.asyncio
    async def test_upload_and_save_with_http_action(self):
        processor = MongoProcessor()
        nlu_content = "## intent:greet\n- hey\n- hello".encode()
        stories_content = "## greet\n* greet\n- utter_offer_help\n- action_restart".encode()
        config_content = "language: en\npipeline:\n- name: WhitespaceTokenizer\n- name: RegexFeaturizer\n- name: LexicalSyntacticFeaturizer\n- name: CountVectorsFeaturizer\n- analyzer: char_wb\n  max_ngram: 4\n  min_ngram: 1\n  name: CountVectorsFeaturizer\n- epochs: 5\n  name: DIETClassifier\n- name: EntitySynonymMapper\n- epochs: 5\n  name: ResponseSelector\npolicies:\n- name: MemoizationPolicy\n- epochs: 5\n  max_history: 5\n  name: TEDPolicy\n- name: RulePolicy\n- core_threshold: 0.3\n  fallback_action_name: action_small_talk\n  name: FallbackPolicy\n  nlu_threshold: 0.75\n".encode()
        domain_content = "intents:\n- greet\nresponses:\n  utter_offer_help:\n  - text: 'how may i help you'\nactions:\n- utter_offer_help\n".encode()
        http_action_content = "http_action:\n- action_name: action_performanceUser1000@digite.com\n  http_url: http://www.alphabet.com\n  headers:\n  - key: auth_token\n    parameter_type: value\n    value: bearer hjklfsdjsjkfbjsbfjsvhfjksvfjksvfjksvf\n  params_list:\n  - key: testParam1\n    parameter_type: value\n    value: testValue1\n  - key: testParam2\n    parameter_type: slot\n    value: testValue1\n  request_method: GET\n  response: json\n".encode()
        nlu = UploadFile(filename="nlu.yml", file=BytesIO(nlu_content))
        stories = UploadFile(filename="stories.md", file=BytesIO(stories_content))
        config = UploadFile(filename="config.yml", file=BytesIO(config_content))
        domain = UploadFile(filename="domain.yml", file=BytesIO(domain_content))
        http_action = UploadFile(filename="actions.yml", file=BytesIO(http_action_content))
        await processor.upload_and_save(nlu, domain, stories, config, None, http_action, "test_upload_and_save",
                                        "rules_creator")
        assert len(list(Intents.objects(bot="test_upload_and_save", user="rules_creator", status=True))) == 6
        assert len(list(Stories.objects(bot="test_upload_and_save", user="rules_creator", status=True))) == 1
        assert len(list(Responses.objects(bot="test_upload_and_save", user="rules_creator", status=True))) == 3
        assert len(
            list(TrainingExamples.objects(intent="greet", bot="test_upload_and_save", user="rules_creator",
                                          status=True))) == 2
        assert len(list(HttpActionConfig.objects(bot="test_upload_and_save", user="rules_creator", status=True))) == 1

    def test_load_and_delete_http_action(self):
        HttpActionConfig(
            action_name="act1",
            http_url="http://www.alphabet.com",
            request_method="POST",
            response='zxcvb',
            bot="test_http",
            user="http_creator",
        ).save()
        processor = MongoProcessor()
        actions = processor.load_http_action("test_http")
        assert actions
        assert isinstance(actions, dict)
        assert len(actions["http_action"]) == 1
        processor.delete_bot_actions(bot="test_http", user="http_creator")
        actions = processor.load_http_action("test_http")
        assert not actions['http_action']
        assert isinstance(actions, dict)

    def test_save_http_action_already_exists(self):
        test_dict = {"http_action": [{"action_name": "rain_today", "http_url": "http://f2724.kairon.io/",
                                       "params_list": [{"key": 'location', "parameter_type": 'sender_id', "value": ''}],
                                       "request_method": "GET", "response": "${RESPONSE}"},
                                      {"action_name": "test_save_http_action_already_exists",
                                       "http_url": "http://f2724.kairon.io/",
                                       "request_method": "GET", "response": "${RESPONSE}"}
                                      ]}
        HttpActionConfig(action_name="test_save_http_action_already_exists",
                         http_url='http://kairon.ai',
                         response='response',
                         request_method='GET',
                         bot='test', user='test').save()
        Actions(name='test_save_http_action_already_exists', bot='test', user='test', status=True, type=ActionType.http_action.value).save()
        processor = MongoProcessor()
        processor.save_integrated_actions(test_dict, 'test', 'test')
        action = HttpActionConfig.objects(bot='test', user='test', status=True).get(
            action_name="test_save_http_action_already_exists")
        assert action
        assert action['http_url'] == "http://kairon.ai"
        assert not action['params_list']
        action = HttpActionConfig.objects(bot='test', user='test').get(action_name="rain_today")
        assert action
        assert action['http_url'] == "http://f2724.kairon.io/"
        assert action['params_list']

    def test_get_action_server_logs_empty(self):
        processor = MongoProcessor()
        logs = list(processor.get_action_server_logs("test_bot"))
        assert logs == []

    def test_get_action_server_logs(self):
        bot = "test_bot"
        bot_2 = "testing_bot"
        expected_intents = ["intent13", "intent11", "intent9", "intent8", "intent7", "intent6", "intent5",
                            "intent4", "intent3", "intent2"]
        request_params = {"key": "value", "key2": "value2"}
        ActionServerLogs(intent="intent1", action="http_action", sender="sender_id",
                         timestamp=datetime(2021, 4, 11, 11, 39, 48, 376000),
                         request_params=request_params, api_response="Response", bot_response="Bot Response",
                         bot=bot).save()
        ActionServerLogs(intent="intent2", action="http_action", sender="sender_id",
                         url="http://kairon-api.digite.com/api/bot",
                         request_params=request_params, api_response="Response", bot_response="Bot Response", bot=bot,
                         status="FAILURE").save()
        ActionServerLogs(intent="intent1", action="http_action", sender="sender_id",
                         request_params=request_params, api_response="Response", bot_response="Bot Response",
                         bot=bot_2).save()
        ActionServerLogs(intent="intent3", action="http_action", sender="sender_id",
                         request_params=request_params, api_response="Response", bot_response="Bot Response", bot=bot,
                         status="FAILURE").save()
        ActionServerLogs(intent="intent4", action="http_action", sender="sender_id",
                         request_params=request_params, api_response="Response", bot_response="Bot Response",
                         bot=bot).save()
        ActionServerLogs(intent="intent5", action="http_action", sender="sender_id",
                         request_params=request_params, api_response="Response", bot_response="Bot Response", bot=bot,
                         status="FAILURE").save()
        ActionServerLogs(intent="intent6", action="http_action", sender="sender_id",
                         request_params=request_params, api_response="Response", bot_response="Bot Response",
                         bot=bot).save()
        ActionServerLogs(intent="intent7", action="http_action", sender="sender_id",
                         request_params=request_params, api_response="Response", bot_response="Bot Response",
                         bot=bot).save()
        ActionServerLogs(intent="intent8", action="http_action", sender="sender_id",
                         request_params=request_params, api_response="Response", bot_response="Bot Response",
                         bot=bot).save()
        ActionServerLogs(intent="intent9", action="http_action", sender="sender_id",
                         request_params=request_params, api_response="Response", bot_response="Bot Response",
                         bot=bot).save()
        ActionServerLogs(intent="intent10", action="http_action", sender="sender_id",
                         request_params=request_params, api_response="Response", bot_response="Bot Response",
                         bot=bot_2).save()
        ActionServerLogs(intent="intent11", action="http_action", sender="sender_id",
                         request_params=request_params, api_response="Response", bot_response="Bot Response",
                         bot=bot).save()
        ActionServerLogs(intent="intent12", action="http_action", sender="sender_id",
                         request_params=request_params, api_response="Response", bot_response="Bot Response", bot=bot_2,
                         status="FAILURE").save()
        ActionServerLogs(intent="intent13", action="http_action", sender="sender_id_13",
                         request_params=request_params, api_response="Response", bot_response="Bot Response", bot=bot,
                         status="FAILURE").save()
        processor = MongoProcessor()
        logs = list(processor.get_action_server_logs(bot))
        assert len(logs) == 10
        assert [log['intent'] in expected_intents for log in logs]
        assert logs[0]['action'] == "http_action"
        assert any([log['request_params'] == request_params for log in logs])
        assert any([log['sender'] == "sender_id_13" for log in logs])
        assert any([log['api_response'] == "Response" for log in logs])
        assert any([log['bot_response'] == "Bot Response" for log in logs])
        assert any([log['status'] == "FAILURE" for log in logs])
        assert any([log['status'] == "SUCCESS" for log in logs])

        logs = list(processor.get_action_server_logs(bot_2))
        assert len(logs) == 3

    def test_get_action_server_logs_start_idx_page_size(self):
        processor = MongoProcessor()
        bot = "test_bot"
        bot_2 = "testing_bot"
        logs = list(processor.get_action_server_logs(bot, 10, 15))
        assert len(logs) == 1

        logs = list(processor.get_action_server_logs(bot, 10, 1))
        assert len(logs) == 1

        logs = list(processor.get_action_server_logs(bot, 0, 5))
        assert len(logs) == 5

        logs = list(processor.get_action_server_logs(bot_2, 0, 5))
        assert len(logs) == 3

        logs = list(processor.get_action_server_logs(bot_2, 2, 1))
        assert len(logs) == 1
        log = logs[0]
        assert log['intent'] == "intent1"

    def test_get_action_server_logs_cnt(self):
        processor = MongoProcessor()
        bot = "test_bot"
        bot_2 = "testing_bot"
        cnt = processor.get_row_count(ActionServerLogs, bot)
        assert cnt == 11

        cnt = processor.get_row_count(ActionServerLogs, bot_2)
        assert cnt == 3

    def test_get_existing_slots(self):
        Slots(
            name="location",
            type="text",
            initial_value="delhi",
            bot="test_get_existing_slots",
            user="bot_user",
        ).save()
        Slots(
            name="email_id",
            type="text",
            initial_value="bot_user@digite.com",
            bot="test_get_existing_slots",
            user="bot_user",
        ).save()
        Slots(
            name="username",
            type="text",
            initial_value="bot_user",
            bot="test_get_existing_slots",
            user="bot_user",
            status=False
        ).save()
        slots = list(MongoProcessor.get_existing_slots("test_get_existing_slots"))
        assert len(slots) == 2
        assert slots[0]['name'] == 'location'
        assert slots[1]['name'] == 'email_id'

    def test_get_existing_slots_bot_not_exists(self):
        slots = list(MongoProcessor.get_existing_slots("test_get_existing_slots_bot_not_exists"))
        assert len(slots) == 0

    @pytest.mark.asyncio
    async def test_save_training_data_all(self, get_training_data):
        path = 'tests/testing_data/yml_training_files'
        bot = 'test'
        user = 'test'
        nlu, story_graph, domain, config, http_actions = await get_training_data(path)

        mongo_processor = MongoProcessor()
        mongo_processor.save_training_data(bot, user, config, domain, story_graph, nlu, http_actions, True)

        training_data = mongo_processor.load_nlu(bot)
        assert isinstance(training_data, TrainingData)
        assert training_data.training_examples.__len__() == 292
        assert training_data.entity_synonyms.__len__() == 3
        assert training_data.regex_features.__len__() == 5
        assert training_data.lookup_tables.__len__() == 1
        story_graph = mongo_processor.load_stories(bot)
        assert isinstance(story_graph, StoryGraph) is True
        assert story_graph.story_steps.__len__() == 16
        assert story_graph.story_steps[14].events[2].intent['name'] == 'user_feedback'
        assert not story_graph.story_steps[14].events[2].entities[0].get('start')
        assert not story_graph.story_steps[14].events[2].entities[0].get('end')
        assert story_graph.story_steps[14].events[2].entities[0]['value'] == 'like'
        assert story_graph.story_steps[14].events[2].entities[0]['entity'] == 'fdresponse'
        assert story_graph.story_steps[15].events[2].intent['name'] == 'user_feedback'
        assert not story_graph.story_steps[15].events[2].entities[0].get('start')
        assert not story_graph.story_steps[15].events[2].entities[0].get('end')
        assert story_graph.story_steps[15].events[2].entities[0]['value'] == 'hate'
        assert story_graph.story_steps[15].events[2].entities[0]['entity'] == 'fdresponse'
        domain = mongo_processor.load_domain(bot)
        assert isinstance(domain, Domain)
        assert domain.slots.__len__() == 12
        assert len([slot for slot in domain.slots if slot.influence_conversation is True]) == 2
        assert len([slot for slot in domain.slots if slot.influence_conversation is False]) == 10
        assert domain.intent_properties.__len__() == 29
        assert len([intent for intent in domain.intent_properties.keys() if
                    domain.intent_properties.get(intent)['used_entities']]) == 27
        assert len([intent for intent in domain.intent_properties.keys() if
                    not domain.intent_properties.get(intent)['used_entities']]) == 2
        assert domain.templates.keys().__len__() == 27
        assert domain.entities.__len__() == 11
        assert domain.form_names.__len__() == 2
        assert domain.user_actions.__len__() == 45
        assert domain.intents.__len__() == 29
        assert not Utility.check_empty_string(
            domain.templates["utter_cheer_up"][0]["image"]
        )
        assert domain.templates["utter_did_that_help"][0]["buttons"].__len__() == 2
        assert domain.templates["utter_offer_help"][0]["custom"]
        assert domain.slots[0].type_name == "any"
        assert domain.slots[1].type_name == "any"
        assert domain.slots[2].type_name == "any"
        rules = mongo_processor.fetch_rule_block_names(bot)
        assert len(rules) == 4
        actions = mongo_processor.load_http_action(bot)
        assert isinstance(actions, dict) is True
        assert len(actions['http_action']) == 5
        assert len(Actions.objects(type='http_action', bot=bot)) == 5

    @pytest.mark.asyncio
    async def test_save_training_data_no_rules_and_http_actions(self, get_training_data):
        path = 'tests/testing_data/all'
        bot = 'test'
        user = 'test'
        nlu, story_graph, domain, config, http_actions = await get_training_data(path)

        mongo_processor = MongoProcessor()
        mongo_processor.save_training_data(bot, user, config, domain, story_graph, nlu, http_actions, True)

        training_data = mongo_processor.load_nlu(bot)
        assert isinstance(training_data, TrainingData)
        assert training_data.training_examples.__len__() == 292
        assert training_data.entity_synonyms.__len__() == 3
        assert training_data.regex_features.__len__() == 5
        assert training_data.lookup_tables.__len__() == 1
        story_graph = mongo_processor.load_stories(bot)
        assert isinstance(story_graph, StoryGraph) is True
        assert story_graph.story_steps.__len__() == 16
        assert story_graph.story_steps[14].events[2].intent['name'] == 'user_feedback'
        assert story_graph.story_steps[14].events[2].entities[0]['start'] == 13
        assert story_graph.story_steps[14].events[2].entities[0]['end'] == 34
        assert story_graph.story_steps[14].events[2].entities[0]['value'] == 'like'
        assert story_graph.story_steps[14].events[2].entities[0]['entity'] == 'fdresponse'
        assert story_graph.story_steps[15].events[2].intent['name'] == 'user_feedback'
        assert story_graph.story_steps[15].events[2].entities[0]['start'] == 13
        assert story_graph.story_steps[15].events[2].entities[0]['end'] == 34
        assert story_graph.story_steps[15].events[2].entities[0]['value'] == 'hate'
        assert story_graph.story_steps[15].events[2].entities[0]['entity'] == 'fdresponse'
        domain = mongo_processor.load_domain(bot)
        assert isinstance(domain, Domain)
        assert domain.slots.__len__() == 11
        assert domain.templates.keys().__len__() == 27
        assert domain.entities.__len__() == 10
        assert domain.form_names.__len__() == 2
        assert domain.user_actions.__len__() == 40
        assert domain.intents.__len__() == 29
        assert not Utility.check_empty_string(
            domain.templates["utter_cheer_up"][0]["image"]
        )
        assert domain.templates["utter_did_that_help"][0]["buttons"].__len__() == 2
        assert domain.templates["utter_offer_help"][0]["custom"]
        assert domain.slots[0].type_name == "any"
        assert domain.slots[1].type_name == "any"
        rules = mongo_processor.fetch_rule_block_names(bot)
        assert rules == ['ask the user to rephrase whenever they send a message with low nlu confidence']
        actions = mongo_processor.load_http_action(bot)
        assert not actions['http_action']

    @pytest.mark.asyncio
    async def test_save_training_data_all_overwrite(self, get_training_data):
        path = 'tests/testing_data/yml_training_files'
        bot = 'test'
        user = 'test'
        nlu, story_graph, domain, config, http_actions = await get_training_data(path)

        mongo_processor = MongoProcessor()
        mongo_processor.save_training_data(bot, user, config, domain, story_graph, nlu, http_actions, True)

        training_data = mongo_processor.load_nlu(bot)
        assert isinstance(training_data, TrainingData)
        assert training_data.training_examples.__len__() == 292
        assert training_data.entity_synonyms.__len__() == 3
        assert training_data.regex_features.__len__() == 5
        assert training_data.lookup_tables.__len__() == 1
        story_graph = mongo_processor.load_stories(bot)
        assert isinstance(story_graph, StoryGraph) is True
        assert story_graph.story_steps.__len__() == 16
        assert story_graph.story_steps[14].events[2].intent['name'] == 'user_feedback'
        assert not story_graph.story_steps[14].events[2].entities[0].get('start')
        assert not story_graph.story_steps[14].events[2].entities[0].get('end')
        assert story_graph.story_steps[14].events[2].entities[0]['value'] == 'like'
        assert story_graph.story_steps[14].events[2].entities[0]['entity'] == 'fdresponse'
        assert story_graph.story_steps[15].events[2].intent['name'] == 'user_feedback'
        assert not story_graph.story_steps[15].events[2].entities[0].get('start')
        assert not story_graph.story_steps[15].events[2].entities[0].get('end')
        assert story_graph.story_steps[15].events[2].entities[0]['value'] == 'hate'
        assert story_graph.story_steps[15].events[2].entities[0]['entity'] == 'fdresponse'
        domain = mongo_processor.load_domain(bot)
        assert isinstance(domain, Domain)
        assert domain.slots.__len__() == 12
        assert len([slot for slot in domain.slots if slot.influence_conversation is True]) == 2
        assert len([slot for slot in domain.slots if slot.influence_conversation is False]) == 10
        assert domain.intent_properties.__len__() == 29
        assert len([intent for intent in domain.intent_properties.keys() if
                    domain.intent_properties.get(intent)['used_entities']]) == 27
        assert len([intent for intent in domain.intent_properties.keys() if
                    not domain.intent_properties.get(intent)['used_entities']]) == 2
        assert domain.templates.keys().__len__() == 27
        assert domain.entities.__len__() == 11
        assert domain.form_names.__len__() == 2
        assert domain.user_actions.__len__() == 45
        assert domain.intents.__len__() == 29
        assert not Utility.check_empty_string(
            domain.templates["utter_cheer_up"][0]["image"]
        )
        assert domain.templates["utter_did_that_help"][0]["buttons"].__len__() == 2
        assert domain.templates["utter_offer_help"][0]["custom"]
        assert domain.slots[0].type_name == "any"
        assert domain.slots[1].type_name == "any"
        assert domain.slots[2].type_name == "any"
        rules = mongo_processor.fetch_rule_block_names(bot)
        assert len(rules) == 4
        actions = mongo_processor.load_http_action(bot)
        assert isinstance(actions, dict) is True
        assert len(actions['http_action']) == 5

    @pytest.mark.asyncio
    async def test_save_training_data_all_append(self, get_training_data):
        path = 'tests/testing_data/validator/append'
        bot = 'test'
        user = 'test'
        nlu, story_graph, domain, config, http_actions = await get_training_data(path)

        mongo_processor = MongoProcessor()
        mongo_processor.save_training_data(bot, user, config, domain, story_graph, nlu, http_actions, False)

        training_data = mongo_processor.load_nlu(bot)
        assert isinstance(training_data, TrainingData)
        assert training_data.training_examples.__len__() == 295
        assert training_data.entity_synonyms.__len__() == 3
        assert training_data.regex_features.__len__() == 5
        assert training_data.lookup_tables.__len__() == 1
        story_graph = mongo_processor.load_stories(bot)
        assert isinstance(story_graph, StoryGraph) is True
        assert story_graph.story_steps.__len__() == 18
        assert story_graph.story_steps[14].events[2].intent['name'] == 'user_feedback'
        assert not story_graph.story_steps[14].events[2].entities[0].get('start')
        assert not story_graph.story_steps[14].events[2].entities[0].get('end')
        assert story_graph.story_steps[14].events[2].entities[0]['value'] == 'like'
        assert story_graph.story_steps[14].events[2].entities[0]['entity'] == 'fdresponse'
        assert story_graph.story_steps[15].events[2].intent['name'] == 'user_feedback'
        assert not story_graph.story_steps[15].events[2].entities[0].get('start')
        assert not story_graph.story_steps[15].events[2].entities[0].get('end')
        assert story_graph.story_steps[15].events[2].entities[0]['value'] == 'hate'
        assert story_graph.story_steps[15].events[2].entities[0]['entity'] == 'fdresponse'
        domain = mongo_processor.load_domain(bot)
        assert isinstance(domain, Domain)
        assert domain.slots.__len__() == 12
        assert len([slot for slot in domain.slots if slot.influence_conversation is True]) == 2
        assert len([slot for slot in domain.slots if slot.influence_conversation is False]) == 10
        assert domain.intent_properties.__len__() == 30
        assert len([intent for intent in domain.intent_properties.keys() if
                    domain.intent_properties.get(intent)['used_entities']]) == 27
        assert len([intent for intent in domain.intent_properties.keys() if
                    not domain.intent_properties.get(intent)['used_entities']]) == 3
        assert domain.templates.keys().__len__() == 29
        assert domain.entities.__len__() == 11
        assert domain.form_names.__len__() == 2
        assert domain.user_actions.__len__() == 50
        assert domain.intents.__len__() == 30
        assert not Utility.check_empty_string(
            domain.templates["utter_cheer_up"][0]["image"]
        )
        assert domain.templates["utter_did_that_help"][0]["buttons"].__len__() == 2
        assert domain.templates["utter_offer_help"][0]["custom"]
        assert domain.slots[0].type_name == "any"
        assert domain.slots[1].type_name == "any"
        assert domain.slots[2].type_name == "any"
        rules = mongo_processor.fetch_rule_block_names(bot)
        assert len(rules) == 4
        actions = mongo_processor.load_http_action(bot)
        assert isinstance(actions, dict) is True
        assert len(actions['http_action']) == 5

    def test_delete_nlu_only(self):
        bot = 'test'
        user = 'test'
        mongo_processor = MongoProcessor()
        mongo_processor.delete_bot_data(bot, user, {"nlu"})
        training_data = mongo_processor.load_nlu(bot)
        assert isinstance(training_data, TrainingData)
        assert training_data.training_examples.__len__() == 0
        assert training_data.entity_synonyms.__len__() == 0
        assert training_data.regex_features.__len__() == 0
        assert training_data.lookup_tables.__len__() == 0
        story_graph = mongo_processor.load_stories(bot)
        assert isinstance(story_graph, StoryGraph) is True
        assert story_graph.story_steps.__len__() == 18
        assert story_graph.story_steps[14].events[2].intent['name'] == 'user_feedback'
        assert not story_graph.story_steps[14].events[2].entities[0].get('start')
        assert not story_graph.story_steps[14].events[2].entities[0].get('end')
        assert story_graph.story_steps[14].events[2].entities[0]['value'] == 'like'
        assert story_graph.story_steps[14].events[2].entities[0]['entity'] == 'fdresponse'
        assert story_graph.story_steps[15].events[2].intent['name'] == 'user_feedback'
        assert not story_graph.story_steps[15].events[2].entities[0].get('start')
        assert not story_graph.story_steps[15].events[2].entities[0].get('end')
        assert story_graph.story_steps[15].events[2].entities[0]['value'] == 'hate'
        assert story_graph.story_steps[15].events[2].entities[0]['entity'] == 'fdresponse'
        domain = mongo_processor.load_domain(bot)
        assert isinstance(domain, Domain)
        assert domain.slots.__len__() == 12
        assert len([slot for slot in domain.slots if slot.influence_conversation is True]) == 2
        assert len([slot for slot in domain.slots if slot.influence_conversation is False]) == 10
        assert domain.intent_properties.__len__() == 30
        assert len([intent for intent in domain.intent_properties.keys() if
                    domain.intent_properties.get(intent)['used_entities']]) == 27
        assert len([intent for intent in domain.intent_properties.keys() if
                    not domain.intent_properties.get(intent)['used_entities']]) == 3
        assert domain.templates.keys().__len__() == 29
        assert domain.entities.__len__() == 11
        assert domain.form_names.__len__() == 2
        assert domain.user_actions.__len__() == 50
        assert domain.intents.__len__() == 30
        assert not Utility.check_empty_string(
            domain.templates["utter_cheer_up"][0]["image"]
        )
        assert domain.templates["utter_did_that_help"][0]["buttons"].__len__() == 2
        assert domain.templates["utter_offer_help"][0]["custom"]
        assert domain.slots[0].type_name == "any"
        assert domain.slots[1].type_name == "any"
        assert domain.slots[2].type_name == "any"
        rules = mongo_processor.fetch_rule_block_names(bot)
        assert len(rules) == 4
        actions = mongo_processor.load_http_action(bot)
        assert isinstance(actions, dict) is True
        assert len(actions['http_action']) == 5

    @pytest.mark.asyncio
    async def test_save_nlu_only(self, get_training_data):
        path = 'tests/testing_data/yml_training_files'
        bot = 'test'
        user = 'test'
        nlu, story_graph, domain, config, http_actions = await get_training_data(path)

        mongo_processor = MongoProcessor()
        mongo_processor.save_training_data(bot, user, nlu=nlu, overwrite=True, what={'nlu'})

        training_data = mongo_processor.load_nlu(bot)
        assert isinstance(training_data, TrainingData)
        assert training_data.training_examples.__len__() == 292
        assert training_data.entity_synonyms.__len__() == 3
        assert training_data.regex_features.__len__() == 5
        assert training_data.lookup_tables.__len__() == 1

    def test_delete_stories_only(self):
        bot = 'test'
        user = 'test'
        mongo_processor = MongoProcessor()
        mongo_processor.delete_bot_data(bot, user, {"stories"})
        training_data = mongo_processor.load_nlu(bot)
        assert isinstance(training_data, TrainingData)
        assert training_data.training_examples.__len__() == 292
        assert training_data.entity_synonyms.__len__() == 3
        assert training_data.regex_features.__len__() == 5
        assert training_data.lookup_tables.__len__() == 1
        story_graph = mongo_processor.load_stories(bot)
        assert isinstance(story_graph, StoryGraph) is True
        assert story_graph.story_steps.__len__() == 0
        domain = mongo_processor.load_domain(bot)
        assert isinstance(domain, Domain)
        assert domain.slots.__len__() == 12
        assert len([slot for slot in domain.slots if slot.influence_conversation is True]) == 2
        assert len([slot for slot in domain.slots if slot.influence_conversation is False]) == 10
        assert domain.intent_properties.__len__() == 30
        assert len([intent for intent in domain.intent_properties.keys() if
                    domain.intent_properties.get(intent)['used_entities']]) == 27
        assert len([intent for intent in domain.intent_properties.keys() if
                    not domain.intent_properties.get(intent)['used_entities']]) == 3
        assert domain.templates.keys().__len__() == 29
        assert domain.entities.__len__() == 11
        assert domain.form_names.__len__() == 2
        assert domain.user_actions.__len__() == 50
        assert domain.intents.__len__() == 30
        assert not Utility.check_empty_string(
            domain.templates["utter_cheer_up"][0]["image"]
        )
        assert domain.templates["utter_did_that_help"][0]["buttons"].__len__() == 2
        assert domain.templates["utter_offer_help"][0]["custom"]
        assert domain.slots[0].type_name == "any"
        assert domain.slots[1].type_name == "any"
        assert domain.slots[2].type_name == "any"
        rules = mongo_processor.fetch_rule_block_names(bot)
        assert len(rules) == 4
        actions = mongo_processor.load_http_action(bot)
        assert isinstance(actions, dict) is True
        assert len(actions['http_action']) == 5

    @pytest.mark.asyncio
    async def test_save_stories_only(self, get_training_data):
        path = 'tests/testing_data/yml_training_files'
        bot = 'test'
        user = 'test'
        nlu, story_graph, domain, config, http_actions = await get_training_data(path)

        mongo_processor = MongoProcessor()
        mongo_processor.save_training_data(bot, user, story_graph=story_graph, overwrite=True, what={'stories'})

        story_graph = mongo_processor.load_stories(bot)
        assert isinstance(story_graph, StoryGraph) is True
        assert story_graph.story_steps.__len__() == 16
        assert story_graph.story_steps[14].events[2].intent['name'] == 'user_feedback'
        assert not story_graph.story_steps[14].events[2].entities[0].get('start')
        assert not story_graph.story_steps[14].events[2].entities[0].get('end')
        assert story_graph.story_steps[14].events[2].entities[0]['value'] == 'like'
        assert story_graph.story_steps[14].events[2].entities[0]['entity'] == 'fdresponse'
        assert story_graph.story_steps[15].events[2].intent['name'] == 'user_feedback'
        assert not story_graph.story_steps[15].events[2].entities[0].get('start')
        assert not story_graph.story_steps[15].events[2].entities[0].get('end')
        assert story_graph.story_steps[15].events[2].entities[0]['value'] == 'hate'
        assert story_graph.story_steps[15].events[2].entities[0]['entity'] == 'fdresponse'

    def test_delete_config_and_actions_only(self):
        bot = 'test'
        user = 'test'
        mongo_processor = MongoProcessor()
        mongo_processor.delete_bot_data(bot, user, {"config", "actions"})
        training_data = mongo_processor.load_nlu(bot)
        assert isinstance(training_data, TrainingData)
        assert training_data.training_examples.__len__() == 292
        assert training_data.entity_synonyms.__len__() == 3
        assert training_data.regex_features.__len__() == 5
        assert training_data.lookup_tables.__len__() == 1
        story_graph = mongo_processor.load_stories(bot)
        assert isinstance(story_graph, StoryGraph) is True
        assert story_graph.story_steps.__len__() == 16
        domain = mongo_processor.load_domain(bot)
        assert isinstance(domain, Domain)
        assert domain.slots.__len__() == 12
        assert domain.intent_properties.__len__() == 30
        assert domain.templates.keys().__len__() == 29
        assert domain.entities.__len__() == 11
        assert domain.form_names.__len__() == 2
        assert domain.user_actions.__len__() == 44
        assert domain.intents.__len__() == 30
        rules = mongo_processor.fetch_rule_block_names(bot)
        assert len(rules) == 4
        actions = mongo_processor.load_http_action(bot)
        assert isinstance(actions, dict) is True
        assert not actions['http_action']
        assert mongo_processor.load_config(bot)

    @pytest.mark.asyncio
    async def test_save_actions_and_config_only(self, get_training_data):
        path = 'tests/testing_data/yml_training_files'
        bot = 'test'
        user = 'test'
        nlu, story_graph, domain, config, http_actions = await get_training_data(path)
        config['language'] = 'fr'

        mongo_processor = MongoProcessor()
        mongo_processor.save_training_data(bot, user, config=config, actions=http_actions, overwrite=True,
                                           what={'actions', 'config'})

        assert len(mongo_processor.load_http_action(bot)['http_action']) == 5
        config = mongo_processor.load_config(bot)
        assert config['language'] == 'fr'
        assert config['pipeline']
        assert config['policies']

    def test_delete_rules_and_domain_only(self):
        bot = 'test'
        user = 'test'
        mongo_processor = MongoProcessor()
        mongo_processor.delete_bot_data(bot, user, {"rules", "domain"})
        training_data = mongo_processor.load_nlu(bot)
        assert isinstance(training_data, TrainingData)
        assert training_data.training_examples.__len__() == 292
        assert training_data.entity_synonyms.__len__() == 3
        assert training_data.regex_features.__len__() == 5
        assert training_data.lookup_tables.__len__() == 1
        story_graph = mongo_processor.load_stories(bot)
        assert isinstance(story_graph, StoryGraph) is True
        assert story_graph.story_steps.__len__() == 16
        domain = mongo_processor.load_domain(bot)
        assert isinstance(domain, Domain)
        assert domain.slots.__len__() == 1
        assert domain.intent_properties.__len__() == 5
        assert domain.templates.keys().__len__() == 0
        assert domain.entities.__len__() == 0
        assert domain.form_names.__len__() == 0
        assert domain.user_actions.__len__() == 5
        assert domain.intents.__len__() == 5
        rules = mongo_processor.fetch_rule_block_names(bot)
        assert len(rules) == 0
        actions = mongo_processor.load_http_action(bot)
        assert isinstance(actions, dict) is True
        assert len(actions['http_action']) == 5

    @pytest.mark.asyncio
    async def test_save_rules_and_domain_only(self, get_training_data):
        path = 'tests/testing_data/yml_training_files'
        bot = 'test'
        user = 'test'
        nlu, story_graph, domain, config, http_actions = await get_training_data(path)

        mongo_processor = MongoProcessor()
        mongo_processor.save_training_data(bot, user, story_graph=story_graph, domain=domain, overwrite=True,
                                           what={'rules', 'domain'})

        rules = mongo_processor.fetch_rule_block_names(bot)
        assert len(rules) == 3
        domain = mongo_processor.load_domain(bot)
        assert isinstance(domain, Domain)
        assert domain.slots.__len__() == 12
        assert domain.intent_properties.__len__() == 29
        assert domain.templates.keys().__len__() == 25
        assert domain.entities.__len__() == 11
        assert domain.form_names.__len__() == 2
        assert domain.user_actions.__len__() == 43
        assert domain.intents.__len__() == 29

    @pytest.fixture()
    def resource_prepare_training_data_for_validation_with_home_dir(self):
        tmp_dir = tempfile.mkdtemp()
        pytest.dir = tmp_dir
        yield 'resource_prepare_training_data_for_validation_with_home_dir'
        Utility.delete_directory(pytest.dir)

    @pytest.fixture()
    def resource_prepare_training_data_for_validation(self):
        yield 'resource_prepare_training_data_for_validation'
        Utility.delete_directory(os.path.join('training_data', 'test'))

    def test_prepare_training_data_for_validation_no_data(self, resource_prepare_training_data_for_validation):
        bot = 'test'
        processor = MongoProcessor()
        processor.prepare_training_data_for_validation(bot)
        bot_home = os.path.join('training_data', bot)
        assert os.path.exists(bot_home)
        dirs = os.listdir(bot_home)
        files = set(os.listdir(os.path.join(bot_home, dirs[0]))).union(
            os.listdir(os.path.join(bot_home, dirs[0], DEFAULT_DATA_PATH)))
        assert ALLOWED_DOMAIN_FORMATS.intersection(files).__len__() == 1
        assert ALLOWED_CONFIG_FORMATS.intersection(files).__len__() == 1
        assert ALLOWED_NLU_FORMATS.intersection(files).__len__() == 1
        assert ALLOWED_STORIES_FORMATS.intersection(files).__len__() == 1

    def test_prepare_training_data_for_validation_with_home_dir(self,
                                                                resource_prepare_training_data_for_validation_with_home_dir):
        bot = 'test'
        processor = MongoProcessor()
        processor.prepare_training_data_for_validation(bot, pytest.dir)
        bot_home = pytest.dir
        assert os.path.exists(bot_home)
        files = set(os.listdir(bot_home)).union(os.listdir(os.path.join(bot_home, DEFAULT_DATA_PATH)))
        assert ALLOWED_DOMAIN_FORMATS.intersection(files).__len__() == 1
        assert ALLOWED_CONFIG_FORMATS.intersection(files).__len__() == 1
        assert ALLOWED_NLU_FORMATS.intersection(files).__len__() == 1
        assert ALLOWED_STORIES_FORMATS.intersection(files).__len__() == 1
        assert ALLOWED_RULES_FORMATS.intersection(files).__len__() == 1

    @pytest.fixture()
    def resource_prepare_training_data_for_validation_nlu_only(self):
        pytest.nlu_only_tmp_dir = tempfile.mkdtemp()
        yield 'resource_prepare_training_data_for_validation_nlu_only'
        Utility.delete_directory(pytest.nlu_only_tmp_dir)

    @pytest.fixture()
    def resource_prepare_training_data_for_validation_rules_only(self):
        pytest.nlu_only_tmp_dir = tempfile.mkdtemp()
        yield 'resource_prepare_training_data_for_validation_rules_only'
        Utility.delete_directory(pytest.nlu_only_tmp_dir)

    def test_prepare_training_data_for_validation_nlu_domain_only(self,
                                                                  resource_prepare_training_data_for_validation_nlu_only):
        bot = 'test'
        processor = MongoProcessor()
        processor.prepare_training_data_for_validation(bot, pytest.nlu_only_tmp_dir, {'nlu', 'domain'})
        bot_home = pytest.nlu_only_tmp_dir
        assert os.path.exists(bot_home)
        files = set(os.listdir(os.path.join(bot_home))).union(
            os.listdir(os.path.join(bot_home, DEFAULT_DATA_PATH)))
        assert ALLOWED_DOMAIN_FORMATS.intersection(files).__len__() == 1
        assert ALLOWED_NLU_FORMATS.intersection(files).__len__() == 1
        assert ALLOWED_CONFIG_FORMATS.intersection(files).__len__() == 0
        assert ALLOWED_STORIES_FORMATS.intersection(files).__len__() == 0
        assert ALLOWED_RULES_FORMATS.intersection(files).__len__() == 0

    def test_prepare_training_data_for_validation_rules_only(self,
                                                             resource_prepare_training_data_for_validation_rules_only):
        bot = 'test'
        processor = MongoProcessor()
        processor.prepare_training_data_for_validation(bot, pytest.nlu_only_tmp_dir, {'rules'})
        bot_home = pytest.nlu_only_tmp_dir
        assert os.path.exists(bot_home)
        files = set(os.listdir(os.path.join(bot_home))).union(
            os.listdir(os.path.join(bot_home, DEFAULT_DATA_PATH)))
        assert ALLOWED_DOMAIN_FORMATS.intersection(files).__len__() == 0
        assert ALLOWED_NLU_FORMATS.intersection(files).__len__() == 0
        assert ALLOWED_CONFIG_FORMATS.intersection(files).__len__() == 0
        assert ALLOWED_STORIES_FORMATS.intersection(files).__len__() == 0
        assert ALLOWED_RULES_FORMATS.intersection(files).__len__() == 1

    def test_prepare_training_data_for_validation(self, resource_prepare_training_data_for_validation):
        bot = 'test'
        processor = MongoProcessor()
        processor.prepare_training_data_for_validation(bot)
        bot_home = os.path.join('training_data', bot)
        assert os.path.exists(bot_home)
        dirs = os.listdir(bot_home)
        files = set(os.listdir(os.path.join(bot_home, dirs[0]))).union(
            os.listdir(os.path.join(bot_home, dirs[0], DEFAULT_DATA_PATH)))
        assert ALLOWED_DOMAIN_FORMATS.intersection(files).__len__() == 1
        assert ALLOWED_CONFIG_FORMATS.intersection(files).__len__() == 1
        assert ALLOWED_NLU_FORMATS.intersection(files).__len__() == 1
        assert ALLOWED_STORIES_FORMATS.intersection(files).__len__() == 1
        assert ALLOWED_RULES_FORMATS.intersection(files).__len__() == 1

    @pytest.fixture()
    def resource_unzip_and_validate(self):
        pytest.bot = 'test_validate_and_prepare_data'
        data_path = 'tests/testing_data/yml_training_files'
        tmp_dir = tempfile.gettempdir()
        zip_file = os.path.join(tmp_dir, 'test')
        shutil.make_archive(zip_file, 'zip', data_path)
        pytest.zip = UploadFile(filename="test.zip", file=BytesIO(open(zip_file + '.zip', 'rb').read()))
        yield "resource_unzip_and_validate"
        os.remove(zip_file + '.zip')
        shutil.rmtree(os.path.join('training_data', pytest.bot))

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_zip(self, resource_unzip_and_validate):
        processor = MongoProcessor()
        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(
            pytest.bot, 'test', [pytest.zip], True)
        assert REQUIREMENTS == files_received
        assert is_event_data
        bot_data_home_dir = Utility.get_latest_file(os.path.join('training_data', pytest.bot))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'domain.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'data', 'nlu.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'config.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'data', 'stories.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'actions.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'data', 'rules.yml'))
        assert not non_event_validation_summary

    @pytest.fixture()
    def resource_save_and_validate_training_files(self):
        pytest.bot = 'test_validate_and_prepare_data'
        config_path = 'tests/testing_data/yml_training_files/config.yml'
        domain_path = 'tests/testing_data/yml_training_files/domain.yml'
        nlu_path = 'tests/testing_data/yml_training_files/data/nlu.yml'
        stories_path = 'tests/testing_data/yml_training_files/data/stories.yml'
        http_action_path = 'tests/testing_data/yml_training_files/actions.yml'
        rules_path = 'tests/testing_data/yml_training_files/data/rules.yml'
        pytest.config = UploadFile(filename="config.yml", file=BytesIO(open(config_path, 'rb').read()))
        pytest.domain = UploadFile(filename="domain.yml", file=BytesIO(open(domain_path, 'rb').read()))
        pytest.nlu = UploadFile(filename="nlu.yml", file=BytesIO(open(nlu_path, 'rb').read()))
        pytest.stories = UploadFile(filename="stories.yml", file=BytesIO(open(stories_path, 'rb').read()))
        pytest.http_actions = UploadFile(filename="actions.yml", file=BytesIO(open(http_action_path, 'rb').read()))
        pytest.rules = UploadFile(filename="rules.yml", file=BytesIO(open(rules_path, 'rb').read()))
        pytest.non_nlu = UploadFile(filename="non_nlu.yml", file=BytesIO(open(rules_path, 'rb').read()))
        yield "resource_save_and_validate_training_files"
        shutil.rmtree(os.path.join('training_data', pytest.bot))

    @pytest.fixture()
    def resource_validate_and_prepare_data_save_actions_and_config_append(self):
        import json

        pytest.bot = 'test_validate_and_prepare_data'
        config = "language: fr\npipeline:\n- name: WhitespaceTokenizer\n- name: LexicalSyntacticFeaturizer\n-  name: DIETClassifier\npolicies:\n-  name: TEDPolicy".encode()
        actions = {"http_action": [
            {"action_name": "test_validate_and_prepare_data", "http_url": "http://www.alphabet.com",
             "request_method": "GET", "response": "json"}]}
        actions = json.dumps(actions).encode('utf-8')
        pytest.config = UploadFile(filename="config.yml", file=BytesIO(config))
        pytest.http_actions = UploadFile(filename="actions.yml", file=BytesIO(actions))
        yield "resource_validate_and_prepare_data_save_actions_and_config_append"
        shutil.rmtree(os.path.join('training_data', pytest.bot))

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_save_training_files(self, resource_save_and_validate_training_files):
        processor = MongoProcessor()
        training_file = [pytest.config, pytest.domain, pytest.nlu, pytest.stories, pytest.http_actions, pytest.rules]
        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(
            pytest.bot, 'test', training_file, True)
        assert REQUIREMENTS == files_received
        assert is_event_data
        bot_data_home_dir = Utility.get_latest_file(os.path.join('training_data', pytest.bot))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'domain.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'data', 'nlu.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'config.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'data', 'stories.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'actions.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'data', 'rules.yml'))
        assert not non_event_validation_summary

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_save_nlu_only(self, resource_save_and_validate_training_files):
        processor = MongoProcessor()
        training_file = [pytest.nlu]
        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(
            pytest.bot, 'test', training_file, True)
        assert {'nlu'} == files_received
        assert is_event_data
        bot_data_home_dir = Utility.get_latest_file(os.path.join('training_data', pytest.bot))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'domain.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'data', 'nlu.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'config.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'data', 'stories.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'actions.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'data', 'rules.yml'))
        assert not non_event_validation_summary

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_save_stories_only(self, resource_save_and_validate_training_files):
        processor = MongoProcessor()
        training_file = [pytest.stories]
        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(
            pytest.bot, 'test', training_file, True)
        assert {'stories'} == files_received
        assert is_event_data
        bot_data_home_dir = Utility.get_latest_file(os.path.join('training_data', pytest.bot))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'domain.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'data', 'nlu.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'config.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'data', 'stories.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'actions.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'data', 'rules.yml'))
        assert not non_event_validation_summary

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_save_config(self, resource_save_and_validate_training_files):
        processor = MongoProcessor()
        training_file = [pytest.config]
        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(
            pytest.bot, 'test', training_file, True)
        assert {'config'} == files_received
        assert not is_event_data
        assert not non_event_validation_summary.get("config")
        assert not non_event_validation_summary.get("http_actions")
        assert processor.list_http_actions(pytest.bot).__len__() == 0
        config = processor.load_config(pytest.bot)
        assert config['pipeline']
        assert config['policies']
        assert config['language']

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_save_rules(self, resource_save_and_validate_training_files):
        processor = MongoProcessor()
        training_file = [pytest.rules]
        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(
            pytest.bot, 'test', training_file, True)
        assert {'rules'} == files_received
        assert is_event_data
        bot_data_home_dir = Utility.get_latest_file(os.path.join('training_data', pytest.bot))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'domain.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'data', 'nlu.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'config.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'data', 'stories.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'actions.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'data', 'rules.yml'))
        assert not non_event_validation_summary

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_save_actions(self, resource_save_and_validate_training_files):
        processor = MongoProcessor()
        training_file = [pytest.http_actions]
        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(
            pytest.bot, 'test', training_file, True)
        assert {'actions'} == files_received
        assert not is_event_data
        assert not non_event_validation_summary.get("http_actions")
        assert not non_event_validation_summary.get("config")
        assert processor.list_http_actions(pytest.bot).__len__() == 5

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_save_domain(self, resource_save_and_validate_training_files):
        processor = MongoProcessor()
        training_file = [pytest.domain]
        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(
            pytest.bot, 'test', training_file, True)
        assert {'domain'} == files_received
        assert is_event_data
        bot_data_home_dir = Utility.get_latest_file(os.path.join('training_data', pytest.bot))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'domain.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'data', 'nlu.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'config.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'data', 'stories.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'actions.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'data', 'rules.yml'))
        assert not non_event_validation_summary

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_save_actions_and_config_overwrite(self,
                                                                               resource_save_and_validate_training_files):
        processor = MongoProcessor()
        training_file = [pytest.http_actions, pytest.config]
        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(
            pytest.bot, 'test', training_file, True)
        assert {'actions', 'config'} == files_received
        assert not is_event_data
        assert not non_event_validation_summary.get("http_actions")
        assert not non_event_validation_summary.get("config")
        assert processor.list_http_actions(pytest.bot).__len__() == 5
        config = processor.load_config(pytest.bot)
        assert config['pipeline']
        assert config['policies']
        assert config['language']

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_save_actions_and_config_append(self,
                                                                            resource_validate_and_prepare_data_save_actions_and_config_append):
        processor = MongoProcessor()
        training_file = [pytest.http_actions, pytest.config]
        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(
            pytest.bot, 'test', training_file, False)
        assert {'actions', 'config'} == files_received
        assert not is_event_data
        assert not non_event_validation_summary.get("http_actions")
        assert not non_event_validation_summary.get("config")
        assert processor.list_http_actions(pytest.bot).__len__() == 6
        config = processor.load_config(pytest.bot)
        assert config['pipeline']
        assert config['policies']
        assert config['language'] == 'fr'

    @pytest.fixture()
    def resource_validate_and_prepare_data_no_valid_file_in_zip(self):
        data_path = 'tests/testing_data/validator'
        tmp_dir = tempfile.gettempdir()
        zip_file = os.path.join(tmp_dir, 'test')
        shutil.make_archive(zip_file, 'zip', data_path)
        pytest.zip = UploadFile(filename="test.zip", file=BytesIO(open(zip_file + '.zip', 'rb').read()))
        yield "resource_validate_and_prepare_data_no_valid_file_in_zip"
        os.remove(zip_file + '.zip')

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_no_valid_file_received(self,
                                                                    resource_validate_and_prepare_data_no_valid_file_in_zip):
        processor = MongoProcessor()
        bot = 'test_validate_and_prepare_data'
        with pytest.raises(AppException) as e:
            await processor.validate_and_prepare_data(bot, 'test', [pytest.zip], True)
        assert str(e).__contains__('Invalid files received')

    @pytest.fixture()
    def resource_validate_and_prepare_data_zip_actions_config(self):
        tmp_dir = tempfile.mkdtemp()
        pytest.bot = 'validate_and_prepare_data_zip_actions_config'
        zip_file = os.path.join(tmp_dir, 'test')
        shutil.copy2('tests/testing_data/yml_training_files/actions.yml', tmp_dir)
        shutil.copy2('tests/testing_data/yml_training_files/config.yml', tmp_dir)
        shutil.make_archive(zip_file, 'zip', tmp_dir)
        pytest.zip = UploadFile(filename="test.zip", file=BytesIO(open(zip_file + '.zip', 'rb').read()))
        yield "resource_validate_and_prepare_data_zip_actions_config"
        shutil.rmtree(tmp_dir)
        shutil.rmtree(os.path.join('training_data', pytest.bot))

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_zip_actions_config(self,
                                                                resource_validate_and_prepare_data_zip_actions_config):
        processor = MongoProcessor()
        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(
            pytest.bot, 'test', [pytest.zip], True)
        assert {'actions', 'config'} == files_received
        assert not is_event_data
        assert not non_event_validation_summary.get("http_actions")
        assert not non_event_validation_summary.get("config")
        assert processor.list_http_actions(pytest.bot).__len__() == 5
        config = processor.load_config(pytest.bot)
        assert config['pipeline']
        assert config['policies']
        assert config['language']

    @pytest.fixture()
    def resource_validate_and_prepare_data_invalid_zip_actions_config(self):
        import json
        tmp_dir = tempfile.mkdtemp()
        pytest.bot = 'validate_and_prepare_data_zip_actions_config'
        zip_file = os.path.join(tmp_dir, 'test')
        actions = Utility.read_yaml('tests/testing_data/yml_training_files/actions.yml')
        actions['http_action'][0].pop('action_name')
        Utility.write_to_file(os.path.join(tmp_dir, 'actions.yml'), json.dumps(actions).encode())
        shutil.copy2('tests/testing_data/yml_training_files/config.yml', tmp_dir)
        shutil.make_archive(zip_file, 'zip', tmp_dir)
        pytest.zip = UploadFile(filename="test.zip", file=BytesIO(open(zip_file + '.zip', 'rb').read()))
        yield "resource_validate_and_prepare_data_zip_actions_config"
        shutil.rmtree(tmp_dir)
        shutil.rmtree(os.path.join('training_data', pytest.bot))

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_invalid_zip_actions_config(self, resource_validate_and_prepare_data_invalid_zip_actions_config):
        processor = MongoProcessor()
        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(
            pytest.bot, 'test', [pytest.zip], True)
        assert 'Required http action' in non_event_validation_summary['summary']['http_actions'][0]
        assert files_received == {'actions', 'config'}
        assert not is_event_data

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_all_actions(self):
        with patch('kairon.shared.utils.SMTP'):
            with patch('kairon.shared.actions.data_objects.ZendeskAction.validate'):
                with patch('kairon.shared.actions.data_objects.JiraAction.validate'):
                    with patch('pipedrive.client.Client'):
                        processor = MongoProcessor()
                        actions = UploadFile(filename="actions.yml",
                                             file=BytesIO(open('tests/testing_data/actions/actions.yml', 'rb').read()))
                        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(
                            'test_validate_and_prepare_data_all_actions', 'test', [actions], True)
                        assert non_event_validation_summary['summary'] == {
                            'http_actions': [], 'slot_set_actions': [], 'form_validation_actions': [], 'email_actions': [],
                            'google_search_actions': [], 'jira_actions': [], 'zendesk_actions': [],
                            'pipedrive_leads_actions': []
                        }
                        assert non_event_validation_summary['component_count']['http_actions'] == 4
                        assert non_event_validation_summary['component_count']['jira_actions'] == 2
                        assert non_event_validation_summary['component_count']['google_search_actions'] == 2
                        assert non_event_validation_summary['component_count']['zendesk_actions'] == 2
                        assert non_event_validation_summary['component_count']['email_actions'] == 2
                        assert non_event_validation_summary['component_count']['slot_set_actions'] == 3
                        assert non_event_validation_summary['component_count']['form_validation_actions'] == 4
                        assert non_event_validation_summary['component_count']['pipedrive_leads_actions'] == 2
                        assert non_event_validation_summary['validation_failed'] is False
                        assert files_received == {'actions'}
                        assert not is_event_data
                        saved_actions = processor.load_action_configurations('test_validate_and_prepare_data_all_actions')
                        assert len(saved_actions['http_action']) == 4
                        assert len(saved_actions['slot_set_action']) == 3
                        assert len(saved_actions['form_validation_action']) == 4
                        assert len(saved_actions['jira_action']) == 2
                        assert len(saved_actions['google_search_action']) == 2
                        assert len(saved_actions['zendesk_action']) == 2
                        assert len(saved_actions['email_action']) == 2
                        assert len(saved_actions['pipedrive_leads_action']) == 2

    def test_save_component_properties_all(self):
        config = {"nlu_epochs": 200,
                  "response_epochs": 300,
                  "ted_epochs": 400,
                  "nlu_confidence_threshold": 0.6,
                  "action_fallback": "action_default_fallback"}
        Responses(name='utter_default', bot='test_all', user='test',
                  text=ResponseText(text='Sorry I didnt get that. Can you rephrase?')).save()
        processor = MongoProcessor()
        processor.save_component_properties(config, 'test_all', 'test')
        config = processor.load_config('test_all')
        nlu = next((comp for comp in config['pipeline'] if comp["name"] == "DIETClassifier"), None)
        assert nlu['name'] == 'DIETClassifier'
        assert nlu['epochs'] == 200
        response = next((comp for comp in config['pipeline'] if comp["name"] == "ResponseSelector"), None)
        assert response['name'] == 'ResponseSelector'
        assert response['epochs'] == 300
        action_fallback = next((comp for comp in config['policies'] if comp["name"] == "TEDPolicy"), None)
        assert action_fallback['name'] == 'TEDPolicy'
        assert action_fallback['epochs'] == 400
        nlu_fallback = next((comp for comp in config['pipeline'] if comp["name"] == "FallbackClassifier"), None)
        assert nlu_fallback['name'] == 'FallbackClassifier'
        assert nlu_fallback['threshold'] == 0.6
        rule_policy = next((comp for comp in config['policies'] if comp["name"] == "RulePolicy"), None)
        assert len(rule_policy) == 4
        assert rule_policy['core_fallback_action_name'] == 'action_default_fallback'
        assert rule_policy['core_fallback_threshold'] == 0.3
        expected = {'language': 'en', 'pipeline': [{'name': 'WhitespaceTokenizer'}, {'name': 'RegexFeaturizer'},
                                                   {'name': 'LexicalSyntacticFeaturizer'}, {'name': 'ConveRTFeaturizer',
                                                                                            'model_url': 'https://github.com/connorbrinton/polyai-models/releases/download/v1.0/model.tar.gz'},
                                                   {'constrain_similarities': True, 'epochs': 200,
                                                    'name': 'DIETClassifier'},
                                                   {'name': 'FallbackClassifier', 'threshold': 0.6},
                                                   {'name': 'EntitySynonymMapper'},
                                                   {'name': 'ResponseSelector', 'epochs': 300}],
                    'policies': [{'name': 'MemoizationPolicy'}, {'epochs': 400, 'max_history': 5, 'name': 'TEDPolicy'},
                                 {'core_fallback_action_name': 'action_default_fallback',
                                  'core_fallback_threshold': 0.3, 'enable_fallback_prediction': True,
                                  'name': 'RulePolicy'}]}
        assert config == expected

    def test_get_config_properties(self):
        expected = {'nlu_confidence_threshold': 0.6,
                    'action_fallback_threshold': 0.3,
                    'action_fallback': 'action_default_fallback',
                    'ted_epochs': 400,
                    'nlu_epochs': 200,
                    'response_epochs': 300}
        processor = MongoProcessor()
        config = processor.list_epoch_and_fallback_config('test_all')
        assert config == expected

    def test_save_component_properties_action_fallback_threshold_greater(self):
        config = {"nlu_epochs": 200,
                  "response_epochs": 300,
                  "ted_epochs": 400,
                  "nlu_confidence_threshold": 0.6,
                  "action_fallback_threshold": 0.7,
                  "action_fallback": "action_default_fallback"}
        processor = MongoProcessor()
        with pytest.raises(AppException,
                           match='Action fallback threshold should always be smaller than nlu fallback threshold'):
            processor.save_component_properties(config, 'test_all', 'test')

    def test_save_component_properties_action_fallback(self):
        config = {"nlu_epochs": 200,
                  "response_epochs": 300,
                  "ted_epochs": 400,
                  "nlu_confidence_threshold": 0.6,
                  "action_fallback_threshold": 0.6,
                  "action_fallback": "action_default_fallback"}
        processor = MongoProcessor()
        processor.save_component_properties(config, 'test_all', 'test')
        config = processor.load_config('test_all')
        nlu = next((comp for comp in config['pipeline'] if comp["name"] == "DIETClassifier"), None)
        assert nlu['name'] == 'DIETClassifier'
        assert nlu['epochs'] == 200
        response = next((comp for comp in config['pipeline'] if comp["name"] == "ResponseSelector"), None)
        assert response['name'] == 'ResponseSelector'
        assert response['epochs'] == 300
        action_fallback = next((comp for comp in config['policies'] if comp["name"] == "TEDPolicy"), None)
        assert action_fallback['name'] == 'TEDPolicy'
        assert action_fallback['epochs'] == 400
        nlu_fallback = next((comp for comp in config['pipeline'] if comp["name"] == "FallbackClassifier"), None)
        assert nlu_fallback['name'] == 'FallbackClassifier'
        assert nlu_fallback['threshold'] == 0.6
        rule_policy = next((comp for comp in config['policies'] if comp["name"] == "RulePolicy"), None)
        assert len(rule_policy) == 4
        assert rule_policy['core_fallback_action_name'] == 'action_default_fallback'
        assert rule_policy['core_fallback_threshold'] == 0.6

    def test_get_config_properties_action_fallback(self):
        expected = {'nlu_confidence_threshold': 0.6,
                    'action_fallback_threshold': 0.6,
                    'action_fallback': 'action_default_fallback',
                    'ted_epochs': 400,
                    'nlu_epochs': 200,
                    'response_epochs': 300}
        processor = MongoProcessor()
        config = processor.list_epoch_and_fallback_config('test_all')
        print(config)
        assert config == expected

    def test_save_component_properties_epoch_only(self):
        config = {"nlu_epochs": 200,
                  "response_epochs": 300,
                  "ted_epochs": 400}
        processor = MongoProcessor()
        processor.save_component_properties(config, 'test_epoch_only', 'test')
        config = processor.load_config('test_epoch_only')
        nlu = next((comp for comp in config['pipeline'] if comp["name"] == "DIETClassifier"), None)
        assert nlu['name'] == 'DIETClassifier'
        assert nlu['epochs'] == 200
        response = next((comp for comp in config['pipeline'] if comp["name"] == "ResponseSelector"), None)
        assert response['name'] == 'ResponseSelector'
        assert response['epochs'] == 300
        ted = next((comp for comp in config['policies'] if comp["name"] == "TEDPolicy"), None)
        assert ted['name'] == 'TEDPolicy'
        assert ted['epochs'] == 400
        expected = {'language': 'en', 'pipeline': [{'name': 'WhitespaceTokenizer'}, {'name': 'RegexFeaturizer'},
                                                   {'name': 'LexicalSyntacticFeaturizer'}, {'name': 'ConveRTFeaturizer',
                                                                                            'model_url': 'https://github.com/connorbrinton/polyai-models/releases/download/v1.0/model.tar.gz'},
                                                   {'constrain_similarities': True, 'epochs': 200,
                                                    'name': 'DIETClassifier'},
                                                   {'name': 'FallbackClassifier', 'threshold': 0.7},
                                                   {'name': 'EntitySynonymMapper'},
                                                   {'name': 'ResponseSelector', 'epochs': 300}],
                    'policies': [{'name': 'MemoizationPolicy'}, {'epochs': 400, 'max_history': 5, 'name': 'TEDPolicy'},
                                 {'core_fallback_action_name': 'action_default_fallback',
                                  'core_fallback_threshold': 0.3, 'enable_fallback_prediction': True,
                                  'name': 'RulePolicy'}]}
        assert config == expected

    def test_get_config_properties_epoch_only(self):
        expected = {'nlu_confidence_threshold': 0.7,
                    'action_fallback': 'action_default_fallback',
                    'action_fallback_threshold': 0.3,
                    'ted_epochs': 400,
                    'nlu_epochs': 200,
                    'response_epochs': 300}
        processor = MongoProcessor()
        config = processor.list_epoch_and_fallback_config('test_epoch_only')
        assert config == expected

    def test_save_component_properties_empty(self):
        processor = MongoProcessor()
        with pytest.raises(AppException) as e:
            processor.save_component_properties({}, 'test_properties_empty', 'test')
        assert str(e).__contains__('At least one field is required')
        config = processor.load_config('test_properties_empty')
        nlu = next((comp for comp in config['pipeline'] if comp["name"] == "DIETClassifier"), None)
        assert nlu['name'] == 'DIETClassifier'
        assert nlu['epochs'] == 100
        response = next((comp for comp in config['pipeline'] if comp["name"] == "ResponseSelector"), None)
        assert response['name'] == 'ResponseSelector'
        assert response['epochs'] == 100
        ted = next((comp for comp in config['policies'] if comp["name"] == "TEDPolicy"), None)
        assert ted['name'] == 'TEDPolicy'
        assert ted['epochs'] == 200

    def test_get_config_properties_fallback_not_set(self):
        expected = {'nlu_confidence_threshold': 0.7,
                    'action_fallback_threshold': 0.3,
                    'action_fallback': 'action_default_fallback',
                    'ted_epochs': 200,
                    'nlu_epochs': 100,
                    'response_epochs': 100}
        processor = MongoProcessor()
        config = processor.list_epoch_and_fallback_config('test_fallback_not_set')
        assert config == expected

    def test_list_epochs_for_components_not_present(self):
        configs = Configs._from_son(
            read_config_file("./template/config/kairon-default.yml")
        ).to_mongo().to_dict()
        del configs['pipeline'][4]
        del configs['pipeline'][6]
        del configs['policies'][1]
        processor = MongoProcessor()
        processor.save_config(configs, 'test_list_component_not_exists', 'test')

        expected = {"nlu_confidence_threshold": 0.7,
                    'action_fallback_threshold': 0.3,
                    "action_fallback": 'action_default_fallback',
                    "ted_epochs": None,
                    "nlu_epochs": None,
                    "response_epochs": None}
        processor = MongoProcessor()
        actual = processor.list_epoch_and_fallback_config('test_list_component_not_exists')
        assert actual == expected

    def test_save_component_properties_component_not_exists(self):
        configs = Configs._from_son(
            read_config_file("./template/config/kairon-default.yml")
        ).to_mongo().to_dict()
        del configs['pipeline'][4]
        del configs['pipeline'][6]
        del configs['policies'][1]
        processor = MongoProcessor()
        processor.save_config(configs, 'test_component_not_exists', 'test')

        config = {"nlu_epochs": 100,
                  "response_epochs": 200,
                  "ted_epochs": 300}
        processor = MongoProcessor()
        processor.save_component_properties(config, 'test_component_not_exists', 'test')
        config = processor.load_config('test_component_not_exists')
        diet = next((comp for comp in config['pipeline'] if comp["name"] == "DIETClassifier"), None)
        assert diet['name'] == 'DIETClassifier'
        assert diet['epochs'] == 100
        response = next((comp for comp in config['pipeline'] if comp["name"] == "ResponseSelector"), None)
        assert response['name'] == 'ResponseSelector'
        assert response['epochs'] == 200
        ted = next((comp for comp in config['policies'] if comp["name"] == "TEDPolicy"), None)
        assert ted['name'] == 'TEDPolicy'
        assert ted['epochs'] == 300

    def test_save_component_fallback_not_configured(self):
        Actions(name='action_say_bye', bot='test_fallback_not_configured', user='test').save()
        configs = Configs._from_son(
            read_config_file("./template/config/kairon-default.yml")
        ).to_mongo().to_dict()
        del configs['pipeline'][6]
        del configs['policies'][2]
        processor = MongoProcessor()
        processor.save_config(configs, 'test_fallback_not_configured', 'test')

        config = {'nlu_confidence_threshold': 0.8,
                  'action_fallback': 'action_say_bye'}
        processor = MongoProcessor()
        processor.save_component_properties(config, 'test_fallback_not_configured', 'test')
        config = processor.load_config('test_fallback_not_configured')
        expected = {'language': 'en', 'pipeline': [{'name': 'WhitespaceTokenizer'}, {'name': 'RegexFeaturizer'},
                                                   {'name': 'LexicalSyntacticFeaturizer'}, {'name': 'ConveRTFeaturizer',
                                                                                            'model_url': 'https://github.com/connorbrinton/polyai-models/releases/download/v1.0/model.tar.gz'},
                                                   {'constrain_similarities': True, 'epochs': 100,
                                                    'name': 'DIETClassifier'},
                                                   {'name': 'FallbackClassifier', 'threshold': 0.8},
                                                   {'name': 'ResponseSelector', 'epochs': 100}],
                    'policies': [{'name': 'MemoizationPolicy'}, {'epochs': 200, 'max_history': 5, 'name': 'TEDPolicy'},
                                 {'name': 'RulePolicy', 'core_fallback_action_name': 'action_say_bye',
                                  'core_fallback_threshold': 0.3}]}
        assert config == expected

    def test_save_component_properties_nlu_fallback_only(self):
        nlu_fallback = {"nlu_confidence_threshold": 0.6}
        processor = MongoProcessor()
        processor.save_component_properties(nlu_fallback, 'test_nlu_fallback_only', 'test')
        config = processor.load_config('test_nlu_fallback_only')
        nlu_fallback = next((comp for comp in config['pipeline'] if comp["name"] == "FallbackClassifier"), None)
        assert nlu_fallback['name'] == 'FallbackClassifier'
        assert nlu_fallback['threshold'] == 0.6
        rule_policy = next((comp for comp in config['policies'] if comp["name"] == "RulePolicy"), None)
        assert len(rule_policy) == 4
        expected = {'language': 'en', 'pipeline': [{'name': 'WhitespaceTokenizer'}, {'name': 'RegexFeaturizer'},
                                                   {'name': 'LexicalSyntacticFeaturizer'}, {'name': 'ConveRTFeaturizer',
                                                                                            'model_url': 'https://github.com/connorbrinton/polyai-models/releases/download/v1.0/model.tar.gz'},
                                                   {'constrain_similarities': True, 'epochs': 100,
                                                    'name': 'DIETClassifier'},
                                                   {'name': 'FallbackClassifier', 'threshold': 0.6},
                                                   {'name': 'EntitySynonymMapper'},
                                                   {'name': 'ResponseSelector', 'epochs': 100}],
                    'policies': [{'name': 'MemoizationPolicy'}, {'epochs': 200, 'max_history': 5, 'name': 'TEDPolicy'},
                                 {'core_fallback_action_name': 'action_default_fallback',
                                  'core_fallback_threshold': 0.3, 'enable_fallback_prediction': True,
                                  'name': 'RulePolicy'}]}
        assert config == expected

    def test_save_component_properties_all_nlu_fallback_update_threshold(self):
        nlu_fallback = {"nlu_confidence_threshold": 0.7}
        processor = MongoProcessor()
        processor.save_component_properties(nlu_fallback, 'test_nlu_fallback_only', 'test')
        config = processor.load_config('test_nlu_fallback_only')
        nlu_fallback = next((comp for comp in config['pipeline'] if comp["name"] == "FallbackClassifier"), None)
        assert nlu_fallback['name'] == 'FallbackClassifier'
        assert nlu_fallback['threshold'] == 0.7
        rule_policy = next((comp for comp in config['policies'] if comp["name"] == "RulePolicy"), None)
        assert len(rule_policy) == 4

    def test_save_component_properties_action_fallback_only(self):
        nlu_fallback = {'action_fallback': 'action_say_bye'}
        Actions(name='action_say_bye', bot='test_action_fallback_only', user='test').save()
        processor = MongoProcessor()
        processor.save_component_properties(nlu_fallback, 'test_action_fallback_only', 'test')
        config = processor.load_config('test_action_fallback_only')
        assert next((comp for comp in config['pipeline'] if comp["name"] == "FallbackClassifier"), None)
        rule_policy = next((comp for comp in config['policies'] if comp["name"] == "RulePolicy"), None)
        assert len(rule_policy) == 4
        assert rule_policy['core_fallback_action_name'] == 'action_say_bye'
        assert rule_policy['core_fallback_threshold'] == 0.3
        expected = {'language': 'en', 'pipeline': [{'name': 'WhitespaceTokenizer'}, {'name': 'RegexFeaturizer'},
                                                   {'name': 'LexicalSyntacticFeaturizer'}, {'name': 'ConveRTFeaturizer',
                                                                                            'model_url': 'https://github.com/connorbrinton/polyai-models/releases/download/v1.0/model.tar.gz'},
                                                   {'constrain_similarities': True, 'epochs': 100,
                                                    'name': 'DIETClassifier'},
                                                   {'name': 'FallbackClassifier', 'threshold': 0.7},
                                                   {'name': 'EntitySynonymMapper'},
                                                   {'name': 'ResponseSelector', 'epochs': 100}],
                    'policies': [{'name': 'MemoizationPolicy'}, {'epochs': 200, 'max_history': 5, 'name': 'TEDPolicy'},
                                 {'core_fallback_action_name': 'action_say_bye', 'core_fallback_threshold': 0.3,
                                  'enable_fallback_prediction': True, 'name': 'RulePolicy'}]}
        assert config == expected

    def test_save_component_properties_all_action_fallback_update(self):
        nlu_fallback = {'action_fallback': 'action_say_bye_bye'}
        Actions(name='action_say_bye_bye', bot='test_action_fallback_only', user='test').save()
        processor = MongoProcessor()
        processor.save_component_properties(nlu_fallback, 'test_action_fallback_only', 'test')
        config = processor.load_config('test_action_fallback_only')
        assert next((comp for comp in config['pipeline'] if comp["name"] == "FallbackClassifier"), None)
        rule_policy = next((comp for comp in config['policies'] if comp["name"] == "RulePolicy"), None)
        assert len(rule_policy) == 4
        assert rule_policy['core_fallback_action_name'] == 'action_say_bye_bye'
        assert rule_policy['core_fallback_threshold'] == 0.3

    def test_save_component_properties_all_action_fallback_action_not_exists(self):
        nlu_fallback = {'action_fallback': 'action_say_hello'}
        processor = MongoProcessor()
        with pytest.raises(AppException) as e:
            processor.save_component_properties(nlu_fallback, 'test_action_fallback_only', 'test')
        assert str(e).__contains__("Action fallback action_say_hello does not exists")
        config = processor.load_config('test_action_fallback_only')
        assert next((comp for comp in config['pipeline'] if comp["name"] == "FallbackClassifier"), None)
        rule_policy = next((comp for comp in config['policies'] if comp["name"] == "RulePolicy"), None)
        assert len(rule_policy) == 4
        assert rule_policy['core_fallback_action_name'] == 'action_say_bye_bye'
        assert rule_policy['core_fallback_threshold'] == 0.3

    def test_save_component_properties_all_action_fallback_utter_default_not_set(self):
        nlu_fallback = {'action_fallback': 'action_default_fallback'}
        processor = MongoProcessor()
        with pytest.raises(AppException) as e:
            processor.save_component_properties(nlu_fallback, 'test_action_fallback_only', 'test')
        assert str(e).__contains__("Utterance utter_default not defined")
        config = processor.load_config('test_action_fallback_only')
        assert next((comp for comp in config['pipeline'] if comp["name"] == "FallbackClassifier"), None)
        rule_policy = next((comp for comp in config['policies'] if comp["name"] == "RulePolicy"), None)
        assert len(rule_policy) == 4
        assert rule_policy['core_fallback_action_name'] == 'action_say_bye_bye'
        assert rule_policy['core_fallback_threshold'] == 0.3

    def test_save_component_properties_all_action_fallback_utter_default_set(self):
        nlu_fallback = {'action_fallback': 'action_default_fallback'}
        Responses(name='utter_default', bot='test_action_fallback_only', user='test',
                  text={'text': 'Sorry I didnt get that. Can you rephrase?'}).save()
        processor = MongoProcessor()
        processor.save_component_properties(nlu_fallback, 'test_action_fallback_only', 'test')
        config = processor.load_config('test_action_fallback_only')
        assert next((comp for comp in config['pipeline'] if comp["name"] == "FallbackClassifier"), None)
        rule_policy = next((comp for comp in config['policies'] if comp["name"] == "RulePolicy"), None)
        assert len(rule_policy) == 4
        assert rule_policy['core_fallback_action_name'] == 'action_default_fallback'
        assert rule_policy['core_fallback_threshold'] == 0.3

    def test_add__and_get_synonym(self):
        processor = MongoProcessor()
        bot = 'test_add_synonym'
        user = 'test_user'
        processor.add_synonym(
            {"name": "bot", "value": ["exp"]}, bot, user)
        syn = list(EntitySynonyms.objects(name__iexact='bot', bot=bot, user=user))
        assert syn[0]['name'] == "bot"
        assert syn[0]['value'] == "exp"

    def test_get_specific_synonym(self):
        processor = MongoProcessor()
        bot = 'test_add_synonym'
        response = list(processor.get_synonym_values("bot", bot))
        assert response[0]["value"] == "exp"

    def test_add_duplicate_synonym(self):
        processor = MongoProcessor()
        bot = 'test_add_synonym'
        user = 'test_user'
        with pytest.raises(AppException) as exp:
            processor.add_synonym({"name": "bot", "value": ["exp"]}, bot, user)
        assert str(exp.value) == "Synonym value already exists"

    def test_edit_specific_synonym(self):
        processor = MongoProcessor()
        bot = 'test_add_synonym'
        user = 'test_user'
        response = list(processor.get_synonym_values("bot", bot))
        processor.edit_synonym(response[0]["_id"], "exp2", "bot", bot, user)
        response = list(processor.get_synonym_values("bot", bot))
        assert response[0]["value"] == "exp2"

    def test_edit_synonym_duplicate(self):
        processor = MongoProcessor()
        bot = 'test_add_synonym'
        user = 'test_user'
        response = list(processor.get_synonym_values("bot", bot))
        with pytest.raises(AppException):
            processor.edit_synonym(response[0]["_id"], "exp2", "bot", bot, user)

    def test_edit_synonym_unavailable(self):
        processor = MongoProcessor()
        bot = 'test_add_synonym'
        user = 'test_user'
        response = list(processor.get_synonym_values("bot", bot))
        with pytest.raises(AppException):
            processor.edit_synonym(response[0]["_id"], "exp3", "bottt", bot, user)

    def test_add_delete_synonym_value(self):
        processor = MongoProcessor()
        bot = 'test_add_synonym'
        user = 'test_user'
        processor.add_synonym({"name": "bot", "value": ["exp"]}, bot, user)
        response = list(processor.get_synonym_values("bot", bot))
        assert len(response) == 2
        processor.delete_synonym_value(response[0]["_id"], bot, user)
        response = list(processor.get_synonym_values("bot", bot))
        assert len(response) == 1

    def test_delete_synonym_value_empty(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.delete_synonym_value(" ", "df", "ff")

    def test_delete_non_existent_synonym(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.delete_synonym_value("0123456789ab0123456789ab", "df", "ff")

    def test_delete_synonym_name(self):
        processor = MongoProcessor()
        bot = 'test_add_synonym'
        user = 'test_user'
        processor.delete_synonym("bot", bot, user)
        response = list(processor.get_synonym_values("bot", bot))
        assert len(response) == 0

    def test_delete_synonym_name_empty(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.delete_synonym(" ", "df", "ff")

    def test_delete_non_existent_synonym_name(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.delete_synonym("0123456789ab0123456789ab", "df", "ff")

    def test_add_empty_synonym(self):
        processor = MongoProcessor()
        bot = 'test_add_synonym'
        user = 'test_user'
        with pytest.raises(AppException) as exp:
            processor.add_synonym({"synonym": "", "value": ["exp"]}, bot, user)
        assert str(exp.value) == "Synonym name cannot be an empty string"

    def test_add_synonym_with_empty_value_list(self):
        processor = MongoProcessor()
        bot = 'test_add_synonym'
        user = 'test_user'
        with pytest.raises(AppException) as exp:
            processor.add_synonym({"name": "bot", "value": []}, bot, user)
        assert str(exp.value) == "Synonym value cannot be an empty string"

    def test_add_synonym_with_empty_element_in_value_list(self):
        processor = MongoProcessor()
        bot = 'test_add_synonym'
        user = 'test_user'
        with pytest.raises(AppException) as exp:
            processor.add_synonym({"name": "bot", "value": ["df", '']}, bot, user)
        assert str(exp.value) == "Synonym value cannot be an empty string"

    def test_add_utterance(self):
        processor = MongoProcessor()
        processor.add_utterance_name('test_add', 'test', 'testUser')

    def test_add_utterance_already_exists(self):
        processor = MongoProcessor()
        with pytest.raises(AppException, match='Utterance exists'):
            processor.add_utterance_name('test_add', 'test', 'testUser', raise_error_if_exists=True)

    def test_add_utterance_empty(self):
        processor = MongoProcessor()
        with pytest.raises(AppException, match='Name cannot be empty'):
            processor.add_utterance_name(' ', 'test', 'testUser', True)

    def test_utterance_data_object(self):
        with pytest.raises(ValidationError, match='Utterance Name cannot be empty or blank spaces'):
            Utterances(name=' ', bot='test', user='user').save()

    def test_add_utterance_already_exists_no_exc(self):
        processor = MongoProcessor()
        assert not processor.add_utterance_name('test_add', 'test', 'testUser')

    def test_get_utterance(self):
        processor = MongoProcessor()
        actual = list(processor.get_utterances('test'))
        assert len(actual) == 26

    def test_delete_utterance_name_does_not_exists(self):
        processor = MongoProcessor()
        with pytest.raises(AppException, match='Utterance not found'):
            processor.delete_utterance_name('test_add_1', 'test', raise_exc=True)

    def test_delete_utterance_name_does_not_exists_no_exc(self):
        processor = MongoProcessor()
        processor.delete_utterance_name('test_add_1', 'test')

    def test_delete_utterance_name(self):
        processor = MongoProcessor()
        processor.delete_utterance_name('test_add', 'test')

    def test_get_bot_settings_not_added(self):
        processor = MongoProcessor()
        settings = processor.get_bot_settings('not_created', 'test')
        assert not settings.ignore_utterances
        assert not settings.force_import
        assert settings.status
        assert settings.timestamp
        assert settings.user
        assert settings.bot

    def test_get_bot_settings(self):
        processor = MongoProcessor()
        settings = BotSettings.objects(bot='not_created').get()
        settings.ignore_utterances = True
        settings.force_import = True
        settings.save()
        fresh_settings = processor.get_bot_settings('not_created', 'test')
        assert fresh_settings.ignore_utterances
        assert fresh_settings.force_import
        assert fresh_settings.status
        assert fresh_settings.timestamp
        assert fresh_settings.user
        assert fresh_settings.bot

    def test_save_chat_client_config_not_exists(self, monkeypatch):
        def _mock_bot_info(*args, **kwargs):
            return {'name': 'test', 'account': 1, 'user': 'user@integration.com', 'status': True}

        def _mock_list_bot_accessors(*args, **kwargs):
            yield {'accessor_email': 'user@integration.com'}

        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        monkeypatch.setattr(AccountProcessor, 'list_bot_accessors', _mock_list_bot_accessors)
        processor = MongoProcessor()
        config_path = "./template/chat-client/default-config.json"
        config = json.load(open(config_path))
        processor.save_chat_client_config(config, 'test', 'testUser')
        saved_config = ChatClientConfig.objects(bot='test').get()
        assert saved_config.config == config
        assert saved_config.user == 'testUser'
        assert saved_config.timestamp
        assert saved_config.status

    def test_save_chat_client_config(self, monkeypatch):
        def _mock_bot_info(*args, **kwargs):
            return {'name': 'test', 'account': 1, 'user': 'user@integration.com', 'status': True}

        def _mock_list_bot_accessors(*args, **kwargs):
            yield {'accessor_email': 'user@integration.com'}

        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        monkeypatch.setattr(AccountProcessor, 'list_bot_accessors', _mock_list_bot_accessors)
        processor = MongoProcessor()
        config_path = "./template/chat-client/default-config.json"
        config = json.load(open(config_path))
        config['headers'] = {}
        config['headers']['authorization'] = 'Bearer eygbsbvuyfhbsfinlasfmishfiufnasfmsnf'
        config['headers']['X-USER'] = 'user@integration.com'
        processor.save_chat_client_config(config, 'test', 'testUser')
        saved_config = ChatClientConfig.objects(bot='test').get()
        assert saved_config.config == config
        assert saved_config.status

    def test_get_chat_client_config_not_exists(self, monkeypatch):
        def _mock_bot_info(*args, **kwargs):
            return {'name': 'test_bot', 'account': 2, 'user': 'user@integration.com', 'status': True}

        def _mock_list_bot_accessors(*args, **kwargs):
            yield {'accessor_email': 'user@integration.com'}

        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        monkeypatch.setattr(AccountProcessor, 'list_bot_accessors', _mock_list_bot_accessors)
        processor = MongoProcessor()
        config_path = "./template/chat-client/default-config.json"
        expected_config = json.load(open(config_path))
        actual_config = processor.get_chat_client_config('test_bot')
        assert actual_config.config['headers']['authorization']
        assert actual_config.config['headers']['X-USER']
        del actual_config.config['headers']
        assert expected_config == actual_config.config

    def test_get_chat_client_config(self, monkeypatch):
        def _mock_bot_info(*args, **kwargs):
            return {'name': 'test', 'account': 1, 'user': 'user@integration.com', 'status': True}

        def _mock_list_bot_accessors(*args, **kwargs):
            yield {'accessor_email': 'user@integration.com'}

        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        monkeypatch.setattr(AccountProcessor, 'list_bot_accessors', _mock_list_bot_accessors)
        processor = MongoProcessor()
        actual_config = processor.get_chat_client_config('test')
        assert actual_config.config['headers']['authorization']
        assert actual_config.config['headers']['X-USER'] == 'user@integration.com'

    def test_get_chat_client_config_default_not_found(self, monkeypatch):
        def _mock_exception(*args, **kwargs):
            raise AppException('Config not found')

        def _mock_bot_info(*args, **kwargs):
            return {'name': 'test', 'account': 1, 'user': 'user@integration.com', 'status': True}

        def _mock_list_bot_accessors(*args, **kwargs):
            yield {'accessor_email': 'user@integration.com'}

        monkeypatch.setattr(AccountProcessor, 'get_bot', _mock_bot_info)
        monkeypatch.setattr(AccountProcessor, 'list_bot_accessors', _mock_list_bot_accessors)
        monkeypatch.setattr(os.path, 'exists', _mock_exception)
        processor = MongoProcessor()
        with pytest.raises(AppException, match='Config not found'):
            processor.get_chat_client_config('test_bot')

    def test_add__and_get_regex(self):
        processor = MongoProcessor()
        bot = 'test_add_regex'
        user = 'test_user'
        processor.add_regex(
            {"name": "bot", "pattern": "exp"}, bot, user)
        reg = RegexFeatures.objects(name__iexact='bot', bot=bot, user=user).get()
        assert reg['name'] == "bot"
        assert reg['pattern'] == "exp"

    def test_add__duplicate_regex(self):
        processor = MongoProcessor()
        bot = 'test_add_regex'
        user = 'test_user'
        with pytest.raises(AppException) as e:
            processor.add_regex({"name": "bot", "pattern": "f"}, bot=bot, user=user)
        assert str(e).__contains__("Regex name already exists!")

    def test_add__empty_regex(self):
        processor = MongoProcessor()
        bot = 'test_add_regex'
        user = 'test_user'
        with pytest.raises(AppException) as e:
            processor.add_regex({"name": "", "pattern": "f"}, bot=bot, user=user)
        assert str(e).__contains__("Regex name and pattern cannot be empty or blank spaces")

    def test_edit__and_get_regex(self):
        processor = MongoProcessor()
        bot = 'test_add_regex'
        user = 'test_user'
        processor.edit_regex(
            {"name": "bot", "pattern": "exp1"}, bot, user)
        reg = RegexFeatures.objects(name__iexact='bot', bot=bot, user=user).get()
        assert reg['name'] == "bot"
        assert reg['pattern'] == "exp1"

    def test_edit__unavailable_regex(self):
        processor = MongoProcessor()
        bot = 'test_add_regex'
        user = 'test_user'
        with pytest.raises(AppException) as e:
            processor.edit_regex({"name": "bot1", "pattern": "f"}, bot=bot, user=user)
        assert str(e).__contains__("Regex name does not exist!")

    def test_edit__empty_regex(self):
        processor = MongoProcessor()
        bot = 'test_add_regex'
        user = 'test_user'
        with pytest.raises(AppException) as e:
            processor.edit_regex({"name": "bot", "pattern": ""}, bot=bot, user=user)
        assert str(e).__contains__("Regex name and pattern cannot be empty or blank spaces")

    def test_delete__unavailable_regex(self):
        processor = MongoProcessor()
        bot = 'test_add_regex'
        user = 'test_user'
        with pytest.raises(AppException) as e:
            processor.delete_regex("f", bot=bot, user=user)
        assert str(e).__contains__("Regex name does not exist.")

    def test_delete__and_get_regex(self):
        processor = MongoProcessor()
        bot = 'test_add_regex'
        user = 'test_user'
        processor.delete_regex("bot", bot, user)
        with pytest.raises(DoesNotExist):
            RegexFeatures.objects(name__iexact='bot', bot=bot, status=True).get()

    def test_add__invalid_regex(self):
        processor = MongoProcessor()
        bot = 'test_add_regex'
        user = 'test_user'
        with pytest.raises(AppException) as e:
            processor.add_regex({"name": "bot11", "pattern": "[0-9]++"}, bot=bot, user=user)
        assert str(e).__contains__("invalid regular expression")

    def test_add__and_get_lookup(self):
        processor = MongoProcessor()
        bot = 'test_add_lookup'
        user = 'test_user'
        processor.add_lookup(
            {"name": "number", "value": ["one"]}, bot, user)
        table = list(LookupTables.objects(name__iexact='number', bot=bot, user=user))
        assert table[0]['name'] == "number"
        assert table[0]['value'] == "one"

    def test_get_specific_lookup(self):
        processor = MongoProcessor()
        bot = 'test_add_lookup'
        response = list(processor.get_lookup_values("number", bot))
        assert response[0]["value"] == "one"

    def test_add_duplicate_lookup(self):
        processor = MongoProcessor()
        bot = 'test_add_lookup'
        user = 'test_user'
        with pytest.raises(AppException) as exp:
            processor.add_lookup({"name": "number", "value": ["one"]}, bot, user)
        assert str(exp.value) == "Lookup table value already exists"

    def test_edit_specific_lookup(self):
        processor = MongoProcessor()
        bot = 'test_add_lookup'
        user = 'test_user'
        response = list(processor.get_lookup_values("number", bot))
        processor.edit_lookup(response[0]["_id"], "two", "number", bot, user)
        response = list(processor.get_lookup_values("number", bot))
        assert response[0]["value"] == "two"

    def test_edit_lookup_duplicate(self):
        processor = MongoProcessor()
        bot = 'test_add_lookup'
        user = 'test_user'
        response = list(processor.get_lookup_values("number", bot))
        with pytest.raises(AppException):
            processor.edit_lookup(response[0]["_id"], "two", "number", bot, user)

    def test_edit_lookup_unavailable(self):
        processor = MongoProcessor()
        bot = 'test_add_lookup'
        user = 'test_user'
        response = list(processor.get_lookup_values("number", bot))
        with pytest.raises(AppException):
            processor.edit_lookup(response[0]["_id"], "exp3", "bottt", bot, user)

    def test_add_delete_lookup_value(self):
        processor = MongoProcessor()
        bot = 'test_add_lookup'
        user = 'test_user'
        processor.add_lookup({"name": "number", "value": ["one"]}, bot, user)
        response = list(processor.get_lookup_values("number", bot))
        assert len(response) == 2
        processor.delete_lookup_value(response[0]["_id"], bot, user)
        response = list(processor.get_lookup_values("number", bot))
        assert len(response) == 1

    def test_delete_lookup_value_empty(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.delete_lookup_value(" ", "df", "ff")

    def test_delete_non_existent_lookup(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.delete_lookup_value("0123456789ab0123456789ab", "df", "ff")

    def test_delete_lookup_name(self):
        processor = MongoProcessor()
        bot = 'test_add_lookup'
        user = 'test_user'
        processor.delete_lookup("number", bot, user)
        response = list(processor.get_lookup_values("number", bot))
        assert len(response) == 0

    def test_delete_lookup_name_empty(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.delete_lookup(" ", "df", "ff")

    def test_delete_non_existent_lookup_name(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.delete_lookup("0123456789ab0123456789ab", "df", "ff")

    def test_add_empty_lookup(self):
        processor = MongoProcessor()
        bot = 'test_add_lookup'
        user = 'test_user'
        with pytest.raises(AppException) as exp:
            processor.add_lookup({"name": "", "value": ["exp"]}, bot, user)
        assert str(exp.value) == "Lookup table name cannot be an empty string"

    def test_add_lookup_with_empty_value_list(self):
        processor = MongoProcessor()
        bot = 'test_add_lookup'
        user = 'test_user'
        with pytest.raises(AppException) as exp:
            processor.add_lookup({"name": "bot", "value": []}, bot, user)
        assert str(exp.value) == "Lookup Table value cannot be an empty string"

    def test_add_lookup_with_empty_element_in_value_list(self):
        processor = MongoProcessor()
        bot = 'test_add_lookup'
        user = 'test_user'
        with pytest.raises(AppException) as exp:
            processor.add_lookup({"name": "bot", "value": ["df", '']}, bot, user)
        assert str(exp.value) == "Lookup table value cannot be an empty string"

    def test_add_slot_mapping_slot_not_added(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'user'
        expected_slot = {"slot": "cuisine", 'mapping': [{'type': 'from_entity', 'entity': 'name'}]}
        with pytest.raises(AppException, match='Slot with name \'cuisine\' not found'):
            processor.add_or_update_slot_mapping(expected_slot, bot, user)

    def test_add_slot_with_mapping(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'user'
        expected_slot = {"slot": "name", 'mapping': [{'type': 'from_text', 'value': 'user', 'entity': 'name'},
                                                     {'type': 'from_entity', 'entity': 'name'}]}
        processor.add_or_update_slot_mapping(expected_slot, bot, user)
        slot = SlotMapping.objects(slot='name', bot=bot, user=user).get()
        assert slot.mapping == [{'type': 'from_text', 'value': 'user'}, {'type': 'from_entity', 'entity': 'name'}]

    def test_add_slot_with_empty_mapping(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'user'
        expected_slot = {"slot": "name", 'mapping': []}
        with pytest.raises(ValueError, match='At least one mapping is required'):
            processor.add_or_update_slot_mapping(expected_slot, bot, user)

        expected_slot = {"slot": "name", 'mapping': [{}]}
        with pytest.raises(ValueError, match='At least one mapping is required'):
            processor.add_or_update_slot_mapping(expected_slot, bot, user)

    def test_update_slot_with_mapping(self):
        expected_slot = {"name": "age", "type": "float", "influence_conversation": True}
        processor = MongoProcessor()
        bot = 'test'
        user = 'user'
        processor.add_slot(expected_slot, bot, user, raise_exception_if_exists=False)
        slot = Slots.objects(name__iexact='age', bot=bot, user=user).get()
        assert slot['name'] == 'age'
        assert slot['type'] == 'float'
        assert slot['initial_value'] is None
        assert slot['influence_conversation']

        expected_slot = {"slot": "age",
                         'mapping': [{'type': 'from_intent', 'intent': ['get_age'], 'entity': 'age', 'value': '18'}]}
        processor.add_or_update_slot_mapping(expected_slot, bot, user)
        slot = Slots.objects(name__iexact='age', bot=bot, user=user).get()
        assert slot['name'] == 'age'
        assert slot['type'] == 'float'
        assert slot['initial_value'] is None
        assert slot['influence_conversation']
        slot = SlotMapping.objects(slot='age', bot=bot, user=user).get()
        assert slot.mapping == [{'type': 'from_intent', 'intent': ['get_age'], 'value': '18'}]

    def test_remove_slot_mapping(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'user'
        processor.add_slot({"name": "occupation", "type": "text", "influence_conversation": True}, bot, user)
        expected_slot = {"slot": "occupation",
                         'mapping': [{'type': 'from_intent', 'intent': ['get_occupation'], 'value': 'business'},
                                     {'type': 'from_text', 'value': 'engineer'},
                                     {'type': 'from_entity', 'entity': 'occupation'},
                                     {'type': 'from_trigger_intent', 'value': 'tester',
                                      'intent': ['get_business', 'is_engineer', 'is_tester'],
                                      'not_intent': ['get_age', 'get_name']}]}
        processor.add_or_update_slot_mapping(expected_slot, bot, user)
        processor.delete_slot_mapping("occupation", bot, user)
        slot = Slots.objects(name__iexact='occupation', bot=bot, user=user).get()
        assert slot['name'] == 'occupation'
        assert slot['type'] == 'text'
        assert slot['initial_value'] is None
        assert slot['influence_conversation']
        with pytest.raises(DoesNotExist):
            SlotMapping.objects(slot='occupation', bot=bot, status=True).get()
        expected_slot = {"slot": "occupation", 'mapping': [
            {'type': 'from_intent', 'intent': ['get_occupation'], 'value': 'business'},
            {'type': 'from_text', 'value': 'engineer'},
            {'type': 'from_entity', 'entity': 'occupation'},
            {'type': 'from_trigger_intent', 'value': 'tester',
             'intent': ['get_business', 'is_engineer', 'is_tester'],
             'not_intent': ['get_age', 'get_name']}]}
        processor.add_or_update_slot_mapping(expected_slot, bot, user)
        slot = SlotMapping.objects(slot='occupation', bot=bot, status=True).get()
        assert slot.mapping == expected_slot['mapping']

    def test_get_slot(self):
        bot = 'test'
        processor = MongoProcessor()
        slots = list(processor.get_existing_slots(bot))
        assert slots == [
            {'name': 'category', 'type': 'unfeaturized', 'auto_fill': True, 'influence_conversation': False,
             '_has_been_set': False},
            {'name': 'file', 'type': 'unfeaturized', 'auto_fill': True, 'influence_conversation': False,
             '_has_been_set': False},
            {'name': 'file_error', 'type': 'unfeaturized', 'auto_fill': True, 'influence_conversation': False,
             '_has_been_set': False},
            {'name': 'file_text', 'type': 'unfeaturized', 'auto_fill': True, 'influence_conversation': False,
             '_has_been_set': False},
            {'name': 'name', 'type': 'unfeaturized', 'auto_fill': True, 'influence_conversation': False,
             '_has_been_set': False},
            {'name': 'priority', 'type': 'categorical', 'auto_fill': True,
             'values': ['low', 'medium', 'high', '__other__'], 'influence_conversation': True, '_has_been_set': False},
            {'name': 'ticketid', 'type': 'float', 'initial_value': 1.0, 'auto_fill': True, 'max_value': 1.0,
             'min_value': 0.0, 'influence_conversation': True, '_has_been_set': False},
            {'name': 'bot', 'type': 'any', 'initial_value': 'test', 'auto_fill': False, 'influence_conversation': False,
             '_has_been_set': False},
            {'name': 'kairon_action_response', 'type': 'any', 'auto_fill': False, 'influence_conversation': False,
             '_has_been_set': False},
            {'name': 'date_time', 'type': 'any', 'auto_fill': True, 'influence_conversation': False,
             '_has_been_set': False},
            {'name': 'age', 'type': 'float', 'auto_fill': True, 'max_value': 1.0, 'min_value': 0.0,
             'influence_conversation': True, '_has_been_set': False},
            {'name': 'occupation', 'type': 'text', 'auto_fill': True, 'influence_conversation': True,
             '_has_been_set': False}]

    def test_update_slot_add_value_intent_and_not_intent(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'user'
        processor.add_slot({"name": "location", "type": "text", "influence_conversation": True}, bot, user)
        slot = {"slot": "location", 'mapping': [{'type': 'from_text', 'value': 'user', 'entity': 'location'},
                                                {'type': 'from_entity', 'entity': 'location'}]}
        processor.add_or_update_slot_mapping(slot, bot, user)

        slots = [{"slot": "age", 'mapping': [{'type': 'from_intent', 'intent': ['retrieve_age', 'ask_age'],
                                              'not_intent': ['get_age', 'affirm', 'deny'], 'value': 20}]},
                 {"slot": "location",
                  'mapping': [{'type': 'from_intent', 'intent': ['get_location'], 'value': 'Mumbai'},
                              {'type': 'from_text', 'value': 'Bengaluru'},
                              {'type': 'from_entity', 'entity': 'location'},
                              {'type': 'from_trigger_intent', 'value': 'Kolkata',
                               'intent': ['get_location', 'is_location', 'current_location'],
                               'not_intent': ['get_age', 'get_name']}]}]
        processor.add_or_update_slot_mapping(slots[0], bot, user)
        processor.add_or_update_slot_mapping(slots[1], bot, user)
        slots = list(processor.get_slot_mappings(bot))
        print(slots)
        assert slots == [{'slot': 'date_time', 'mapping': [{'type': 'from_entity', 'entity': 'date_time'}]},
                         {'slot': 'priority', 'mapping': [{'type': 'from_entity', 'entity': 'priority'}]},
                         {'slot': 'file', 'mapping': [{'type': 'from_entity', 'entity': 'file'}]}, {'slot': 'name',
                                                                                                    'mapping': [{
                                                                                                        'type': 'from_text',
                                                                                                        'value': 'user'},
                                                                                                        {
                                                                                                            'type': 'from_entity',
                                                                                                            'entity': 'name'}]},
                         {'slot': 'age', 'mapping': [
                             {'type': 'from_intent', 'value': 20, 'intent': ['retrieve_age', 'ask_age'],
                              'not_intent': ['get_age', 'affirm', 'deny']}]}, {'slot': 'occupation', 'mapping': [
                {'type': 'from_intent', 'value': 'business', 'intent': ['get_occupation']},
                {'type': 'from_text', 'value': 'engineer'}, {'type': 'from_entity', 'entity': 'occupation'},
                {'type': 'from_trigger_intent', 'value': 'tester',
                 'intent': ['get_business', 'is_engineer', 'is_tester'], 'not_intent': ['get_age', 'get_name']}]},
                         {'slot': 'location',
                          'mapping': [{'type': 'from_intent', 'value': 'Mumbai', 'intent': ['get_location']},
                                      {'type': 'from_text', 'value': 'Bengaluru'},
                                      {'type': 'from_entity', 'entity': 'location'},
                                      {'type': 'from_trigger_intent', 'value': 'Kolkata',
                                       'intent': ['get_location', 'is_location', 'current_location'],
                                       'not_intent': ['get_age', 'get_name']}]}]

    def test_add_form(self):
        processor = MongoProcessor()
        path = [{'ask_questions': ['what is your name?', 'name?'], 'slot': 'name'},
                {'ask_questions': ['what is your age?', 'age?'], 'slot': 'age'},
                {'ask_questions': ['what is your occupation?', 'occupation?'], 'slot': 'occupation'}]
        bot = 'test'
        user = 'user'
        assert processor.add_form('know_user', path, bot, user)
        form = Forms.objects(name='know_user', bot=bot).get()
        assert form.required_slots == ['name', 'age', 'occupation']
        assert Utterances.objects(name='utter_ask_know_user_name', bot=bot,
                                  status=True).get().form_attached == 'know_user'
        assert Utterances.objects(name='utter_ask_know_user_age', bot=bot,
                                  status=True).get().form_attached == 'know_user'
        assert Utterances.objects(name='utter_ask_know_user_occupation', bot=bot,
                                  status=True).get().form_attached == 'know_user'
        resp = list(Responses.objects(name='utter_ask_know_user_name', bot=bot, status=True))
        assert resp[0].text.text == 'what is your name?'
        assert resp[1].text.text == 'name?'
        resp = list(Responses.objects(name='utter_ask_know_user_age', bot=bot, status=True))
        assert resp[0].text.text == 'what is your age?'
        assert resp[1].text.text == 'age?'
        resp = list(Responses.objects(name='utter_ask_know_user_occupation', bot=bot, status=True))
        assert resp[0].text.text == 'what is your occupation?'
        assert resp[1].text.text == 'occupation?'

    def test_add_utterance_to_form(self):
        bot = 'test'
        user = 'user'
        processor = MongoProcessor()
        assert processor.add_text_response('your occupation?', 'utter_ask_know_user_occupation', bot, user, 'know_user')

    def test_delete_utterance_from_form_2(self):
        bot = 'test'
        user = 'user'
        processor = MongoProcessor()
        resp = list(Responses.objects(name='utter_ask_know_user_occupation', bot=bot, status=True))
        assert resp[0].text.text == 'what is your occupation?'
        assert resp[1].text.text == 'occupation?'
        assert resp[2].text.text == 'your occupation?'
        assert not processor.delete_response(str(resp[2].id), bot, user)

    def test_add_utterance_to_form_not_exists(self):
        bot = 'test'
        user = 'user'
        processor = MongoProcessor()
        with pytest.raises(AppException, match="Form 'know_user_here' does not exists"):
            processor.add_text_response('give occupation', 'utter_ask_know_user_occupation', bot, user,
                                        'know_user_here')

    def test_create_flow_with_empty_step_name(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "", "type": "FORM_ACTION"},
            {"name": "know_user", "type": "FORM_START"},
            {"type": "FORM_END"},
            {"name": "utter_submit", "type": "BOT"},
        ]
        story_dict = {'name': "activate form", 'steps': steps, 'type': 'RULE', 'template_type': 'CUSTOM'}
        with pytest.raises(ValidationError, match="Empty name is allowed only for active_loop"):
            processor.add_complex_story(story_dict, bot, user)

    def test_create_form_activation_and_deactivation_rule(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "know_user", "type": "FORM_ACTION"},
            {"name": "know_user", "type": "FORM_START"},
            {"type": "FORM_END"},
            {"name": "utter_submit", "type": "BOT"},
        ]
        story_dict = {'name': "activate form", 'steps': steps, 'type': 'RULE', 'template_type': 'CUSTOM'}
        assert processor.add_complex_story(story_dict, bot, user)
        rule = Rules.objects(block_name="activate form", bot=bot, events__name='know_user', status=True).get()
        assert rule.events[2].type == 'action'
        assert rule.events[3].name == 'know_user'
        assert rule.events[3].type == 'active_loop'
        stories = list(processor.get_stories(bot))
        story_with_form = [s for s in stories if s['name'] == 'activate form']
        assert story_with_form[0]['steps'] == steps

    def test_create_unhappy_path_form_story(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "know_user", "type": "FORM_ACTION"},
            {"name": "know_user", "type": "FORM_START"},
            {"name": "deny", "type": "INTENT"},
            {"name": "utter_ask_continue", "type": "BOT"},
            {"name": "affirm", "type": "INTENT"},
            {"type": "FORM_END"},
            {"name": "utter_submit", "type": "BOT"},
        ]
        story_dict = {'name': "stop form + continue", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        assert processor.add_complex_story(story_dict, bot, user)
        stories = Stories.objects(block_name="stop form + continue", bot=bot, events__name='know_user',
                                  status=True).get()
        assert stories.events[1].type == 'action'
        assert stories.events[2].type == 'active_loop'
        assert stories.events[2].name == 'know_user'
        assert stories.events[6].type == 'active_loop'
        stories = list(processor.get_stories(bot))
        story_with_form = [s for s in stories if s['name'] == 'stop form + continue']
        assert story_with_form[0]['steps'] == steps

    def test_create_unhappy_path_form_story_to_breakout(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "know_user", "type": "FORM_ACTION"},
            {"name": "know_user", "type": "FORM_START"},
            {"name": "deny", "type": "INTENT"},
            {"name": "utter_ask_continue", "type": "BOT"},
            {"name": "deny", "type": "INTENT"},
            {"type": "FORM_END"},
            {"name": "utter_submit", "type": "BOT"},
        ]
        story_dict = {'name': "stop form + stop", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        assert processor.add_complex_story(story_dict, bot, user)
        stories = Stories.objects(block_name="stop form + stop", bot=bot, events__name='know_user', status=True).get()
        assert stories.events[1].type == 'action'
        assert stories.events[2].type == 'active_loop'
        assert stories.events[2].name == 'know_user'
        assert stories.events[6].type == 'active_loop'
        stories = list(processor.get_stories(bot))
        story_with_form = [s for s in stories if s['name'] == 'stop form + stop']
        assert story_with_form[0]['steps'] == steps

    def test_delete_slot_mapping_attached_to_form(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'user'
        with pytest.raises(AppException, match=re.escape('Slot mapping is required for form: [\'know_user\']')):
            processor.delete_slot_mapping("occupation", bot, user)

    def test_delete_slot_mapping_not_exists(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'user'
        with pytest.raises(AppException, match='No slot mapping exists for slot: menu_card'):
            processor.delete_slot_mapping("menu_card", bot, user)

    def test_add_form_slots_not_exists(self):
        processor = MongoProcessor()
        path = [{'ask_questions': ['please give us your name?'], 'slot': 'name',
                 'mapping': [{'type': 'from_text', 'value': 'user', 'entity': 'name'},
                             {'type': 'from_entity', 'entity': 'name'}]},
                {'ask_questions': ['seats required?'], 'slot': 'num_people',
                 'mapping': [{'type': 'from_entity', 'intent': ['inform', 'request_restaurant'], 'entity': 'number'}]},
                {'ask_questions': ['type of cuisine?'], 'slot': 'cuisine',
                 'mapping': [{'type': 'from_entity', 'entity': 'cuisine'}]},
                {'ask_questions': ['outdoor seating required?'], 'slot': 'outdoor_seating',
                 'mapping': [{'type': 'from_entity', 'entity': 'seating'},
                             {'type': 'from_intent', 'intent': ['affirm'], 'value': True},
                             {'type': 'from_intent', 'intent': ['deny'], 'value': False}]},
                {'ask_questions': ['any preferences?'], 'slot': 'preferences',
                 'mapping': [{'type': 'from_text', 'not_intent': ['affirm']},
                             {'type': 'from_intent', 'intent': ['affirm'], 'value': 'no additional preferences'}]},
                {'ask_questions': ['Please give your feedback on your experience so far'], 'slot': 'feedback',
                 'mapping': [{'type': 'from_text'},
                             {'type': 'from_entity', 'entity': 'feedback'}]},
                ]
        bot = 'test'
        user = 'user'
        Slots(name='num_people', type="float", bot=bot, user=user).save()
        Slots(name='cuisine', type="text", bot=bot, user=user).save()

        with pytest.raises(AppException) as e:
            processor.add_form('form', path, bot, user)
            assert str(e).__contains__('slots not exists: {')

    def test_add_form_mapping_not_found(self):
        processor = MongoProcessor()
        path = [{'ask_questions': ['please give us your name?'], 'slot': 'name'},
                {'ask_questions': ['seats required?'], 'slot': 'num_people'},
                {'ask_questions': ['food choice?'], 'slot': 'category'},
                {'ask_questions': ['outdoor seating required?'], 'slot': 'outdoor_seating'}]
        bot = 'test'
        user = 'user'
        Slots(name='outdoor_seating', type="text", bot=bot, user=user).save()
        with pytest.raises(AppException, match=r"Mapping is required for slot: {.*}"):
            processor.add_form('restaurant_form', path, bot, user)

    def test_add_form_2(self):
        processor = MongoProcessor()
        path = [{'ask_questions': ['please give us your name?'], 'slot': 'name'},
                {'ask_questions': ['seats required?'], 'slot': 'num_people'},
                {'ask_questions': ['type of cuisine?'], 'slot': 'cuisine'},
                {'ask_questions': ['outdoor seating required?'], 'slot': 'outdoor_seating'},
                {'ask_questions': ['any preferences?'], 'slot': 'preferences'},
                {'ask_questions': ['Please give your feedback on your experience so far'], 'slot': 'feedback'}]
        bot = 'test'
        user = 'user'
        slot = {"slot": "num_people",
                'mapping': [{'type': 'from_entity', 'intent': ['inform', 'request_restaurant'], 'entity': 'number'}]}
        processor.add_or_update_slot_mapping(slot, bot, user)
        slot = {"slot": "cuisine", 'mapping': [{'type': 'from_entity', 'entity': 'cuisine'}]}
        processor.add_or_update_slot_mapping(slot, bot, user)
        slot = {"slot": "outdoor_seating",
                'mapping': [{'type': 'from_entity', 'entity': 'seating'},
                            {'type': 'from_intent', 'intent': ['affirm'], 'value': True},
                            {'type': 'from_intent', 'intent': ['deny'], 'value': False}]}
        processor.add_slot({"name": "outdoor_seating", "type": "text", "influence_conversation": True}, bot, user,
                           raise_exception_if_exists=False)
        processor.add_or_update_slot_mapping(slot, bot, user)
        slot = {"slot": "preferences",
                'mapping': [{'type': 'from_text', 'not_intent': ['affirm']},
                            {'type': 'from_intent', 'intent': ['affirm'], 'value': 'no additional preferences'}]}
        processor.add_slot({"name": "preferences", "type": "text", "influence_conversation": True}, bot, user,
                           raise_exception_if_exists=False)
        processor.add_or_update_slot_mapping(slot, bot, user)
        slot = {"slot": "feedback", 'mapping': [{'type': 'from_text'},
                                                {'type': 'from_entity', 'entity': 'feedback'}]}
        processor.add_slot({"name": "feedback", "type": "text", "influence_conversation": True}, bot, user,
                           raise_exception_if_exists=False)
        processor.add_or_update_slot_mapping(slot, bot, user)

        assert processor.add_form('restaurant_form', path, bot, user)
        form = Forms.objects(name='restaurant_form', bot=bot, status=True).get()
        assert form.required_slots == ['name', 'num_people', 'cuisine', 'outdoor_seating', 'preferences', 'feedback']
        assert Utterances.objects(name='utter_ask_restaurant_form_name', bot=bot, status=True).get()
        assert Utterances.objects(name='utter_ask_restaurant_form_num_people', bot=bot, status=True).get()
        assert Utterances.objects(name='utter_ask_restaurant_form_cuisine', bot=bot, status=True).get()
        assert Utterances.objects(name='utter_ask_restaurant_form_outdoor_seating', bot=bot, status=True).get()
        assert Utterances.objects(name='utter_ask_restaurant_form_preferences', bot=bot, status=True).get()
        assert Utterances.objects(name='utter_ask_restaurant_form_feedback', bot=bot, status=True).get()
        assert Responses.objects(name='utter_ask_restaurant_form_name', bot=bot,
                                 status=True).get().text.text == 'please give us your name?'
        assert Responses.objects(name='utter_ask_restaurant_form_num_people', bot=bot,
                                 status=True).get().text.text == 'seats required?'
        assert Responses.objects(name='utter_ask_restaurant_form_cuisine', bot=bot,
                                 status=True).get().text.text == 'type of cuisine?'
        assert Responses.objects(name='utter_ask_restaurant_form_outdoor_seating', bot=bot,
                                 status=True).get().text.text == 'outdoor seating required?'
        assert Responses.objects(name='utter_ask_restaurant_form_preferences', bot=bot,
                                 status=True).get().text.text == 'any preferences?'
        assert Responses.objects(name='utter_ask_restaurant_form_feedback', bot=bot,
                                 status=True).get().text.text == 'Please give your feedback on your experience so far'

    def test_add_form_already_exists(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'user'
        with pytest.raises(AppException, match='Form with name "restaurant_form" exists'):
            processor.add_form('restaurant_form', [], bot, user)

    def test_add_form_name_empty(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'user'
        with pytest.raises(AppException, match='Form name cannot be empty or spaces'):
            processor.add_form(' ', [], bot, user)

    def test_add_form_no_entity_and_mapping_type(self):
        processor = MongoProcessor()
        path = [{'ask_questions': ['what is your name?'], 'slot': 'name'},
                {'ask_questions': ['what is your age?'], 'slot': 'age'},
                {'ask_questions': ['where are you located?'], 'slot': 'category'}]
        bot = 'test'
        user = 'user'
        with pytest.raises(AppException, match="Mapping is required for slot: {'category'}"):
            processor.add_form('get_user', path, bot, user)

    def test_add_form_with_validations(self):
        processor = MongoProcessor()
        name_validation = {'logical_operator': 'and',
                           'expressions': [{'validations': [{'operator': 'has_length_greater_than', 'value': 1},
                                                            {'operator': 'has_no_whitespace'}]}]}
        age_validation = {'logical_operator': 'and',
                          'expressions': [{'validations': [{'operator': 'is_greater_than', 'value': 10},
                                                           {'operator': 'is_less_than', 'value': 70},
                                                           {'operator': 'starts_with', 'value': 'valid'},
                                                           {'operator': 'ends_with', 'value': 'value'}]}]}
        occupation_validation = {'logical_operator': 'and', 'expressions': [
            {'logical_operator': 'and',
             'validations': [{'operator': 'is_in', 'value': ['teacher', 'programmer', 'student', 'manager']},
                             {'operator': 'has_no_whitespace'},
                             {'operator': 'ends_with', 'value': 'value'}]},
            {'logical_operator': 'or',
             'validations': [{'operator': 'has_length_greater_than', 'value': 20},
                             {'operator': 'has_no_whitespace'},
                             {'operator': 'matches_regex', 'value': '^[e]+.*[e]$'}]}]}
        path = [{'ask_questions': ['your name?', 'ur name?'], 'slot': 'name',
                 'validation': name_validation,
                 'valid_response': 'got it',
                 'invalid_response': 'please rephrase'},
                {'ask_questions': ['your age?', 'ur age?'], 'slot': 'age',
                 'validation': age_validation,
                 'valid_response': 'valid entry',
                 'invalid_response': 'please enter again'
                 },
                {'ask_questions': ['your occupation?', 'ur occupation?'], 'slot': 'occupation',
                 'validation': occupation_validation}]
        bot = 'test'
        user = 'user'
        assert processor.add_form('know_user_form', path, bot, user)
        form = Forms.objects(name='know_user_form', bot=bot).get()
        assert form.required_slots == ['name', 'age', 'occupation']
        assert Utterances.objects(name='utter_ask_know_user_form_name', bot=bot,
                                  status=True).get().form_attached == 'know_user_form'
        assert Utterances.objects(name='utter_ask_know_user_form_age', bot=bot,
                                  status=True).get().form_attached == 'know_user_form'
        assert Utterances.objects(name='utter_ask_know_user_form_occupation', bot=bot,
                                  status=True).get().form_attached == 'know_user_form'
        resp = list(Responses.objects(name='utter_ask_know_user_form_name', bot=bot, status=True))
        assert resp[0].text.text == 'your name?'
        assert resp[1].text.text == 'ur name?'
        resp = list(Responses.objects(name='utter_ask_know_user_form_age', bot=bot, status=True))
        assert resp[0].text.text == 'your age?'
        assert resp[1].text.text == 'ur age?'
        resp = list(Responses.objects(name='utter_ask_know_user_form_occupation', bot=bot, status=True))
        assert resp[0].text.text == 'your occupation?'
        assert resp[1].text.text == 'ur occupation?'

        validations_added = list(FormValidationAction.objects(name='validate_know_user_form', bot=bot, status=True))
        assert len(validations_added) == 3
        assert validations_added[0].slot == 'name'
        assert validations_added[0].validation_semantic == {'and': [{'operator': 'has_length_greater_than', 'value': 1},
                                                                    {'operator': 'has_no_whitespace'}]}
        assert validations_added[0].valid_response == 'got it'
        assert validations_added[0].invalid_response == 'please rephrase'

        assert validations_added[1].slot == 'age'
        assert validations_added[1].validation_semantic == {'and': [{'operator': 'is_greater_than', 'value': 10},
                                                                    {'operator': 'is_less_than', 'value': 70},
                                                                    {'operator': 'starts_with', 'value': 'valid'},
                                                                    {'operator': 'ends_with', 'value': 'value'},
                                                                    ]}
        assert validations_added[1].valid_response == 'valid entry'
        assert validations_added[1].invalid_response == 'please enter again'

        assert validations_added[2].slot == 'occupation'
        assert validations_added[2].validation_semantic == {'and': [
            {'and': [{'operator': 'is_in', 'value': ['teacher', 'programmer', 'student', 'manager']},
                     {'operator': 'has_no_whitespace'},
                     {'operator': 'ends_with', 'value': 'value'}]},
            {'or': [{'operator': 'has_length_greater_than', 'value': 20},
                    {'operator': 'has_no_whitespace'},
                    {'operator': 'matches_regex', 'value': '^[e]+.*[e]$'}]}]}
        assert not validations_added[2].valid_response
        assert not validations_added[2].invalid_response

    def test_list_forms(self):
        processor = MongoProcessor()
        forms = list(processor.list_forms('test'))
        print(forms)
        assert len(forms) == 5
        assert len([f['name'] for f in forms]) == 5
        assert len([f['_id'] for f in forms]) == 5
        required_slots = [f['required_slots'] for f in forms]
        assert required_slots == [['date_time', 'priority'], ['file'], ['name', 'age', 'occupation'],
                                  ['name', 'num_people', 'cuisine', 'outdoor_seating', 'preferences', 'feedback'],
                                  ['name', 'age', 'occupation']]

    def test_list_forms_no_form_added(self):
        processor = MongoProcessor()
        forms = list(processor.list_forms('new_bot'))
        assert forms == []

    def test_get_form(self):
        processor = MongoProcessor()
        forms = list(processor.list_forms('test'))
        form_id = [f['_id'] for f in forms if f['name'] == 'know_user'][0]
        form = processor.get_form(form_id, 'test')
        assert form['settings'][0]['slot'] == 'name'
        assert form['settings'][1]['slot'] == 'age'
        assert form['settings'][2]['slot'] == 'occupation'
        assert form['settings'][0]['ask_questions'][0]['_id']
        assert form['settings'][0]['ask_questions'][0]['value'] == {'text': 'name?'}
        assert form['settings'][0]['ask_questions'][1]['value'] == {'text': 'what is your name?'}
        assert form['settings'][1]['ask_questions'][0]['_id']
        assert form['settings'][1]['ask_questions'][0]['value'] == {'text': 'age?'}
        assert form['settings'][1]['ask_questions'][1]['value'] == {'text': 'what is your age?'}
        assert form['settings'][2]['ask_questions'][0]['_id']
        assert form['settings'][2]['ask_questions'][0]['value'] == {'text': 'occupation?'}
        assert form['settings'][2]['ask_questions'][1]['value'] == {'text': 'what is your occupation?'}
        assert not form['settings'][0]['validation']
        assert not form['settings'][0]['invalid_response']
        assert not form['settings'][0]['valid_response']
        assert not form['settings'][1]['validation']
        assert not form['settings'][1]['invalid_response']
        assert not form['settings'][1]['valid_response']
        assert not form['settings'][2]['validation']
        assert not form['settings'][2]['invalid_response']
        assert not form['settings'][2]['valid_response']

    def test_get_form_with_validations(self):
        processor = MongoProcessor()
        forms = list(processor.list_forms('test'))
        form_id = [f['_id'] for f in forms if f['name'] == 'know_user_form'][0]
        form = processor.get_form(form_id, 'test')
        print(form)
        assert form['settings'][0]['slot'] == 'name'
        assert form['settings'][1]['slot'] == 'age'
        assert form['settings'][2]['slot'] == 'occupation'
        assert form['settings'][0]['ask_questions'][0]['_id']
        assert form['settings'][0]['ask_questions'][0]['value']['text']
        assert form['settings'][0]['ask_questions'][1]['value']['text']
        assert form['settings'][1]['ask_questions'][0]['_id']
        assert form['settings'][1]['ask_questions'][0]['value']['text']
        assert form['settings'][1]['ask_questions'][1]['value']['text']
        assert form['settings'][2]['ask_questions'][0]['_id']
        assert form['settings'][2]['ask_questions'][0]['value']['text']
        assert form['settings'][2]['ask_questions'][1]['value']['text']
        assert form['settings'][0]['validation'] == {'and': [{'operator': 'has_length_greater_than', 'value': 1},
                                                             {'operator': 'has_no_whitespace'}]}
        assert form['settings'][0]['invalid_response'] == 'please rephrase'
        assert form['settings'][0]['valid_response'] == 'got it'
        assert form['settings'][1]['validation'] == {'and': [{'operator': 'is_greater_than', 'value': 10},
                                                             {'operator': 'is_less_than', 'value': 70},
                                                             {'operator': 'starts_with', 'value': 'valid'},
                                                             {'operator': 'ends_with', 'value': 'value'},
                                                             ]}
        assert form['settings'][1]['invalid_response'] == 'please enter again'
        assert form['settings'][1]['valid_response'] == 'valid entry'
        assert form['settings'][2]['validation'] == {'and': [
            {'and': [{'operator': 'is_in', 'value': ['teacher', 'programmer', 'student', 'manager']},
                     {'operator': 'has_no_whitespace'},
                     {'operator': 'ends_with', 'value': 'value'}]},
            {'or': [{'operator': 'has_length_greater_than', 'value': 20},
                    {'operator': 'has_no_whitespace'},
                    {'operator': 'matches_regex', 'value': '^[e]+.*[e]$'}]}]}
        assert not form['settings'][2]['invalid_response']
        assert not form['settings'][2]['valid_response']

    def test_get_form_not_added(self):
        import mongomock

        with pytest.raises(AppException, match='Form does not exists'):
            MongoProcessor().get_form(mongomock.ObjectId().__str__(), 'test')

    def test_get_form_having_on_intent_and_not_intent(self):
        processor = MongoProcessor()
        forms = list(processor.list_forms('test'))
        form_id = [f['_id'] for f in forms if f['name'] == 'restaurant_form'][0]
        form = MongoProcessor().get_form(form_id, 'test')
        assert form['settings'][0]['slot'] == 'name'
        assert form['settings'][1]['slot'] == 'num_people'
        assert form['settings'][2]['slot'] == 'cuisine'
        assert form['settings'][3]['slot'] == 'outdoor_seating'
        assert form['settings'][4]['slot'] == 'preferences'
        assert form['settings'][5]['slot'] == 'feedback'
        assert form['settings'][0]['ask_questions'][0]['_id']
        assert form['settings'][1]['ask_questions'][0]['_id']
        assert form['settings'][2]['ask_questions'][0]['_id']
        assert form['settings'][3]['ask_questions'][0]['_id']
        assert form['settings'][4]['ask_questions'][0]['_id']
        assert form['settings'][5]['ask_questions'][0]['_id']
        assert form['settings'][0]['ask_questions'][0]['value']['text']
        assert form['settings'][1]['ask_questions'][0]['value']['text']
        assert form['settings'][2]['ask_questions'][0]['value']['text']
        assert form['settings'][3]['ask_questions'][0]['value']['text']
        assert form['settings'][4]['ask_questions'][0]['value']['text']
        assert form['settings'][5]['ask_questions'][0]['value']['text']

    def test_edit_form_slot_not_present(self):
        processor = MongoProcessor()
        path = [{'ask_questions': 'which location would you prefer?', 'slot': 'restaurant_location',
                 'mapping': [{'type': 'from_text', 'value': 'user', 'entity': 'location'},
                             {'type': 'from_entity', 'entity': 'location'}]},
                {'ask_questions': 'seats required?', 'slot': 'num_people',
                 'mapping': [{'type': 'from_entity', 'intent': ['inform', 'request_restaurant'], 'entity': 'number'}]},
                {'ask_questions': 'type of cuisine?', 'slot': 'cuisine',
                 'mapping': [{'type': 'from_entity', 'entity': 'cuisine'}]},
                {'ask_questions': 'outdoor seating required?', 'slot': 'outdoor_seating',
                 'mapping': [{'type': 'from_entity', 'entity': 'seating'},
                             {'type': 'from_intent', 'intent': ['affirm'], 'value': True},
                             {'type': 'from_intent', 'intent': ['deny'], 'value': False}]},
                {'ask_questions': 'any preferences?', 'slot': 'preferences',
                 'mapping': [{'type': 'from_text', 'not_intent': ['affirm']},
                             {'type': 'from_intent', 'intent': ['affirm'], 'value': 'no additional preferences'}]},
                {'ask_questions': 'do you want to go with an AC room?', 'slot': 'ac_required',
                 'mapping': [{'type': 'from_intent', 'intent': ['affirm'], 'value': True},
                             {'type': 'from_intent', 'intent': ['deny'], 'value': False}]},
                {'ask_questions': 'Please give your feedback on your experience so far', 'slot': 'feedback',
                 'mapping': [{'type': 'from_text'},
                             {'type': 'from_entity', 'entity': 'feedback'}]}
                ]
        bot = 'test'
        user = 'user'

        with pytest.raises(AppException) as e:
            processor.edit_form('restaurant_form', path, bot, user)
            assert str(e).__contains__('slots not exists: {')

    def test_edit_form_change_validations(self):
        processor = MongoProcessor()
        name_validation = {'logical_operator': 'and',
                           'expressions': [{'validations': [{'operator': 'has_length_greater_than', 'value': 1},
                                                            {'operator': 'has_no_whitespace'}]}]}
        age_validation = {'logical_operator': 'and',
                          'expressions': [{'validations': [{'operator': 'is_greater_than', 'value': 10}]}]}
        path = [{'ask_questions': ['what is your name?', 'name?'], 'slot': 'name',
                 'validation': name_validation,
                 'valid_response': 'got it',
                 'invalid_response': 'please rephrase'},
                {'ask_questions': ['what is your age?', 'age?'], 'slot': 'age',
                 'validation': age_validation,
                 'valid_response': 'valid entry',
                 'invalid_response': 'please enter again'
                 },
                {'ask_questions': ['what is your occupation?', 'occupation?'], 'slot': 'occupation',
                 'validation': None}]
        bot = 'test'
        user = 'user'
        processor.edit_form('know_user_form', path, bot, user)
        form = Forms.objects(name='know_user_form', bot=bot).get()
        assert form.required_slots == ['name', 'age', 'occupation']
        assert Utterances.objects(name='utter_ask_know_user_form_name', bot=bot,
                                  status=True).get().form_attached == 'know_user_form'
        assert Utterances.objects(name='utter_ask_know_user_form_age', bot=bot,
                                  status=True).get().form_attached == 'know_user_form'
        assert Utterances.objects(name='utter_ask_know_user_form_occupation', bot=bot,
                                  status=True).get().form_attached == 'know_user_form'
        resp = list(Responses.objects(name='utter_ask_know_user_form_name', bot=bot, status=True))
        assert resp[0].text.text == 'your name?'
        assert resp[1].text.text == 'ur name?'
        resp = list(Responses.objects(name='utter_ask_know_user_form_age', bot=bot, status=True))
        assert resp[0].text.text == 'your age?'
        assert resp[1].text.text == 'ur age?'
        resp = list(Responses.objects(name='utter_ask_know_user_form_occupation', bot=bot, status=True))
        assert resp[0].text.text == 'your occupation?'
        assert resp[1].text.text == 'ur occupation?'

        validations_added = list(FormValidationAction.objects(name='validate_know_user_form', bot=bot, status=True))
        assert len(validations_added) == 3
        assert validations_added[0].slot == 'name'
        assert validations_added[0].validation_semantic == {'and': [{'operator': 'has_length_greater_than', 'value': 1},
                                                                    {'operator': 'has_no_whitespace'}]}
        assert validations_added[0].valid_response == 'got it'
        assert validations_added[0].invalid_response == 'please rephrase'

        assert validations_added[1].slot == 'age'
        assert validations_added[1].validation_semantic == {'and': [{'operator': 'is_greater_than', 'value': 10}]}
        assert validations_added[1].valid_response == 'valid entry'
        assert validations_added[1].invalid_response == 'please enter again'

        assert validations_added[2].slot == 'occupation'
        assert not validations_added[2].validation_semantic

    def test_edit_form_remove_validations(self):
        processor = MongoProcessor()
        path = [{'ask_questions': ['what is your name?', 'name?'], 'slot': 'name',
                 'mapping': [{'type': 'from_text', 'value': 'user', 'entity': 'name'},
                             {'type': 'from_entity', 'entity': 'name'}],
                 'validation': None,
                 'valid_response': 'got it',
                 'invalid_response': 'please rephrase'},
                {'ask_questions': ['what is your age?', 'age?'], 'slot': 'age',
                 'mapping': [{'type': 'from_intent', 'intent': ['get_age'], 'entity': 'age', 'value': '18'}],
                 'validation': None,
                 'valid_response': 'valid entry',
                 'invalid_response': 'please enter again'
                 },
                {'ask_questions': ['what is your occupation?', 'occupation?'], 'slot': 'occupation',
                 'mapping': [
                     {'type': 'from_intent', 'intent': ['get_occupation'], 'entity': 'occupation', 'value': 'business'},
                     {'type': 'from_text', 'entity': 'occupation', 'value': 'engineer'},
                     {'type': 'from_entity', 'entity': 'occupation'},
                     {'type': 'from_trigger_intent', 'entity': 'occupation', 'value': 'tester',
                      'intent': ['get_business', 'is_engineer', 'is_tester'], 'not_intent': ['get_age', 'get_name']}],
                 'validation': None}]
        bot = 'test'
        user = 'user'
        processor.edit_form('know_user_form', path, bot, user)
        form = Forms.objects(name='know_user_form', bot=bot).get()
        assert form.required_slots == ['name', 'age', 'occupation']
        assert Utterances.objects(name='utter_ask_know_user_form_name', bot=bot,
                                  status=True).get().form_attached == 'know_user_form'
        assert Utterances.objects(name='utter_ask_know_user_form_age', bot=bot,
                                  status=True).get().form_attached == 'know_user_form'
        assert Utterances.objects(name='utter_ask_know_user_form_occupation', bot=bot,
                                  status=True).get().form_attached == 'know_user_form'
        resp = list(Responses.objects(name='utter_ask_know_user_form_name', bot=bot, status=True))
        assert resp[0].text.text == 'your name?'
        assert resp[1].text.text == 'ur name?'
        resp = list(Responses.objects(name='utter_ask_know_user_form_age', bot=bot, status=True))
        assert resp[0].text.text == 'your age?'
        assert resp[1].text.text == 'ur age?'
        resp = list(Responses.objects(name='utter_ask_know_user_form_occupation', bot=bot, status=True))
        assert resp[0].text.text == 'your occupation?'
        assert resp[1].text.text == 'ur occupation?'

        validations = list(FormValidationAction.objects(name='validate_know_user_form', bot=bot, status=True))
        assert len(validations) == 3
        assert validations[0].validation_semantic == {}
        assert validations[0].valid_response == 'got it'
        assert validations[0].invalid_response == 'please rephrase'
        assert validations[1].validation_semantic == {}
        assert validations[1].valid_response == 'valid entry'
        assert validations[1].invalid_response == 'please enter again'
        assert validations[2].validation_semantic == {}
        assert not validations[2].valid_response
        assert not validations[2].invalid_response

    def test_edit_form_add_validations(self):
        processor = MongoProcessor()
        name_validation = {'logical_operator': 'and',
                           'expressions': [{'validations': [{'operator': 'has_no_whitespace'}]}]}
        path = [{'ask_questions': ['what is your name?', 'name?'], 'slot': 'name',
                 'validation': name_validation,
                 'valid_response': 'got it',
                 'invalid_response': 'please rephrase'},
                {'ask_questions': ['what is your age?', 'age?'], 'slot': 'age',
                 'validation': None,
                 'valid_response': 'valid entry',
                 'invalid_response': 'please enter again'
                 },
                {'ask_questions': ['what is your occupation?', 'occupation?'], 'slot': 'occupation',
                 'validation': None}]
        bot = 'test'
        user = 'user'
        processor.edit_form('know_user_form', path, bot, user)

        validations_added = list(FormValidationAction.objects(name='validate_know_user_form', bot=bot, status=True))
        assert len(validations_added) == 3
        assert validations_added[0].slot == 'name'
        assert validations_added[0].validation_semantic == {'and': [{'operator': 'has_no_whitespace'}]}
        assert validations_added[0].valid_response == 'got it'
        assert validations_added[0].invalid_response == 'please rephrase'

    def test_edit_form_remove_and_add_slots(self):
        processor = MongoProcessor()
        path = [{'ask_questions': ['which location would you prefer?'], 'slot': 'location'},
                {'ask_questions': ['seats required?'], 'slot': 'num_people'},
                {'ask_questions': ['type of cuisine?'], 'slot': 'cuisine',
                 'validation': {'logical_operator': 'and',
                                'expressions': [{'validations': [{'operator': 'has_no_whitespace'}]}]}},
                {'ask_questions': ['outdoor seating required?'], 'slot': 'outdoor_seating'},
                {'ask_questions': ['any preferences?'], 'slot': 'preferences'},
                {'ask_questions': ['do you want to go with an AC room?'], 'slot': 'ac_required'},
                {'ask_questions': ['Please give your feedback on your experience so far'], 'slot': 'feedback'}]
        bot = 'test'
        user = 'user'
        slot = {"slot": "ac_required",
                'mapping': [{'type': 'from_intent', 'intent': ['affirm'], 'value': True},
                            {'type': 'from_intent', 'intent': ['deny'], 'value': False}]}
        processor.add_slot({"name": "ac_required", "type": "text", "influence_conversation": True}, bot, user,
                           raise_exception_if_exists=False)
        processor.add_or_update_slot_mapping(slot, bot, user)

        processor.edit_form('restaurant_form', path, bot, user)
        form = Forms.objects(name='restaurant_form', bot=bot, status=True).get()
        assert form.required_slots == ['location', 'num_people', 'cuisine', 'outdoor_seating', 'preferences',
                                       'ac_required', 'feedback']
        assert Utterances.objects(name='utter_ask_restaurant_form_location', bot=bot,
                                  status=True).get().form_attached == 'restaurant_form'
        assert Utterances.objects(name='utter_ask_restaurant_form_num_people', bot=bot,
                                  status=True).get().form_attached == 'restaurant_form'
        assert Utterances.objects(name='utter_ask_restaurant_form_cuisine', bot=bot,
                                  status=True).get().form_attached == 'restaurant_form'
        assert Utterances.objects(name='utter_ask_restaurant_form_outdoor_seating', bot=bot,
                                  status=True).get().form_attached == 'restaurant_form'
        assert Utterances.objects(name='utter_ask_restaurant_form_preferences', bot=bot,
                                  status=True).get().form_attached == 'restaurant_form'
        assert Utterances.objects(name='utter_ask_restaurant_form_feedback', bot=bot,
                                  status=True).get().form_attached == 'restaurant_form'
        assert Utterances.objects(name='utter_ask_restaurant_form_ac_required', bot=bot,
                                  status=True).get().form_attached == 'restaurant_form'
        with pytest.raises(DoesNotExist):
            Utterances.objects(name='utter_ask_restaurant_form_name', bot=bot, status=True).get()
        with pytest.raises(DoesNotExist):
            Responses.objects(name='utter_ask_restaurant_form_name', bot=bot, status=True).get()
        assert Responses.objects(name='utter_ask_restaurant_form_location',
                                 bot=bot, status=True).get().text.text == 'which location would you prefer?'
        assert Responses.objects(name='utter_ask_restaurant_form_num_people',
                                 bot=bot, status=True).get().text.text == 'seats required?'
        assert Responses.objects(name='utter_ask_restaurant_form_cuisine',
                                 bot=bot, status=True).get().text.text == 'type of cuisine?'
        assert Responses.objects(name='utter_ask_restaurant_form_outdoor_seating',
                                 bot=bot, status=True).get().text.text == 'outdoor seating required?'
        assert Responses.objects(name='utter_ask_restaurant_form_preferences',
                                 bot=bot, status=True).get().text.text == 'any preferences?'
        assert Responses.objects(name='utter_ask_restaurant_form_ac_required',
                                 bot=bot, status=True).get().text.text == 'do you want to go with an AC room?'
        assert Responses.objects(name='utter_ask_restaurant_form_feedback',
                                 bot=bot,
                                 status=True).get().text.text == 'Please give your feedback on your experience so far'

        validations_added = list(FormValidationAction.objects(name='validate_restaurant_form', bot=bot, status=True))
        assert len(validations_added) == 7
        assert validations_added[1].slot == 'cuisine'
        assert validations_added[1].validation_semantic == {'and': [{'operator': 'has_no_whitespace'}]}

    def test_edit_form_not_exists(self):
        processor = MongoProcessor()
        with pytest.raises(AppException, match='Form does not exists'):
            processor.edit_form('form_not_present', [], 'test', 'test')

    def test_edit_form_utterance_not_exists(self):
        processor = MongoProcessor()
        path = [{'ask_questions': ['provide your age?'], 'slot': 'age'},
                {'ask_questions': ['provide your location?'], 'slot': 'location'}]
        bot = 'test'
        user = 'user'
        utterance = Utterances.objects(name='utter_ask_know_user_name', bot=bot).get()
        utterance.status = False
        utterance.save()
        for response in Responses.objects(name='utter_ask_know_user_name', bot=bot):
            response.status = False
            response.save()

        processor.edit_form('know_user', path, bot, user)
        assert Forms.objects(name='know_user', bot=bot, status=True).get()
        assert Utterances.objects(name='utter_ask_know_user_age', bot=bot,
                                  status=True).get().form_attached == 'know_user'
        assert Utterances.objects(name='utter_ask_know_user_location', bot=bot,
                                  status=True).get().form_attached == 'know_user'
        assert len(Responses.objects(name='utter_ask_know_user_age', bot=bot, status=True)) == 2
        assert Responses.objects(name='utter_ask_know_user_location', bot=bot,
                                 status=True).get().text.text == 'provide your location?'

    def test_delete_form_with_validations(self):
        bot = 'test'
        user = 'user'
        processor = MongoProcessor()
        processor.delete_form('know_user_form', bot, user)
        with pytest.raises(DoesNotExist):
            Forms.objects(name='know_user_form', bot=bot, status=True).get()
        form_validations = list(FormValidationAction.objects(name='know_user_form', bot=bot, status=True))
        assert not form_validations

    def test_delete_form_not_exists(self):
        bot = 'test'
        user = 'user'
        processor = MongoProcessor()
        with pytest.raises(AppException, match='Form "get_user" does not exists'):
            processor.delete_form('get_user', bot, user)
        with pytest.raises(AppException, match='Form "form_not_present" does not exists'):
            processor.delete_form('form_not_present', bot, user)

    def test_delete_empty_form(self):
        bot = 'test'
        user = 'user'
        processor = MongoProcessor()
        with pytest.raises(AppException, match='Form " " does not exists'):
            processor.delete_form(' ', bot, user)

    def test_delete_form_attached_to_rule(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'user'
        form_name = 'know_user'
        story_name = "stop form + continue"
        with pytest.raises(AppException,
                           match=re.escape(f'Cannot remove action "{form_name}" linked to flow "{story_name}"')):
            processor.delete_form(form_name, bot, user)

    def test_delete_rule_with_form(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        processor.delete_complex_story("activate form", 'RULE', bot, user)
        with pytest.raises(DoesNotExist):
            Rules.objects(block_name="activate form", bot=bot, events__name='know_user', status=True).get()

    def test_delete_rule_with_story(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        processor.delete_complex_story("stop form + continue", 'STORY', bot, user)
        processor.delete_complex_story("stop form + stop", 'STORY', bot, user)
        with pytest.raises(DoesNotExist):
            Stories.objects(block_name="stop form + continue", bot=bot, events__name='know_user', status=True).get()
        with pytest.raises(DoesNotExist):
            Stories.objects(block_name="stop form + stop", bot=bot, events__name='know_user', status=True).get()

    def test_delete_form_utterance_deleted(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'user'
        utterance = Utterances.objects(name='utter_ask_know_user_age', bot=bot).get()
        utterance.status = False
        utterance.save()
        processor.delete_form('know_user', bot, user)
        with pytest.raises(DoesNotExist):
            Forms.objects(name='know_user', bot=bot, status=True).get()
        with pytest.raises(DoesNotExist):
            Utterances.objects(name='utter_ask_know_user_name', bot=bot, status=True).get()
        with pytest.raises(DoesNotExist):
            Responses.objects(name='utter_ask_know_user_name', bot=bot, status=True).get()
        with pytest.raises(DoesNotExist):
            Utterances.objects(name='utter_ask_know_user_location', bot=bot, status=True).get()
        with pytest.raises(DoesNotExist):
            Responses.objects(name='utter_ask_know_user_location', bot=bot, status=True).get()

    def test_delete_utterance_linked_to_form(self):
        processor = MongoProcessor()
        bot = 'test'
        with pytest.raises(AppException,
                           match='At least one question is required for utterance linked to form: restaurant_form'):
            processor.delete_utterance('utter_ask_restaurant_form_cuisine', bot, "test")
        assert Utterances.objects(name='utter_ask_restaurant_form_cuisine', bot=bot, status=True).get()
        assert Responses.objects(name='utter_ask_restaurant_form_cuisine', bot=bot, status=True).get()

    def test_delete_response_linked_to_form(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        response = Responses.objects(name='utter_ask_restaurant_form_cuisine', bot=bot, status=True).get()
        with pytest.raises(AppException,
                           match='At least one question is required for utterance linked to form: restaurant_form'):
            processor.delete_response(str(response.id), bot, user)
        assert Utterances.objects(name='utter_ask_restaurant_form_cuisine', bot=bot, status=True).get()
        assert Responses.objects(name='utter_ask_restaurant_form_cuisine', bot=bot, status=True).get()

    def test_edit_utterance_for_form(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        response = Responses.objects(name='utter_ask_restaurant_form_cuisine', bot=bot, status=True).get()
        processor.edit_text_response(str(response.id), 'what cuisine are you interested in?',
                                     'utter_ask_restaurant_form_cuisine', bot, user)
        assert Responses.objects(name='utter_ask_restaurant_form_cuisine', bot=bot,
                                 status=True).get().text.text == 'what cuisine are you interested in?'

    def test_delete_response_linked_to_form_validation_false(self):
        processor = MongoProcessor()
        bot = 'test'
        processor.delete_utterance('utter_ask_restaurant_form_cuisine', bot, False)
        with pytest.raises(DoesNotExist):
            Utterances.objects(name='utter_ask_restaurant_form_cuisine', bot=bot, status=True).get()
        with pytest.raises(DoesNotExist):
            Responses.objects(name='utter_ask_restaurant_form_cuisine', bot=bot, status=True).get()

    def test_add_utterance_to_story_that_is_attached_to_form(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_ask_restaurant_form_outdoor_seating", "type": "BOT"},
        ]
        story_dict = {'name': "story with form utterance", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        with pytest.raises(AppException,
                           match='utterance "utter_ask_restaurant_form_outdoor_seating" is attached to a form'):
            processor.add_complex_story(story_dict, bot, user)

    def test_delete_intent_attached_to_story(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        with pytest.raises(AppException, match='Cannot remove intent "greet" linked to flow "greet"'):
            processor.delete_intent('greet', bot, user, False)

    def test_add_story_with_form(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "restaurant_form", "type": "FORM_ACTION"},
            {"name": "utter_thanks", "type": "ACTION"},
        ]
        story_dict = {'name': "story with form", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        assert processor.add_complex_story(story_dict, bot, user)
        story = Stories.objects(block_name="story with form", bot=bot,
                                events__name='restaurant_form', status=True).get()
        assert story.events[1].type == 'action'
        stories = list(processor.get_stories(bot))
        story_with_form = [s for s in stories if s['name'] == 'story with form']
        assert story_with_form[0]['steps'] == [
            {'name': 'greet', 'type': 'INTENT'},
            {'name': 'restaurant_form', 'type': 'FORM_ACTION'},
            {'name': 'utter_thanks', 'type': 'BOT'}
        ]

    def test_get_story_with_form(self):
        processor = MongoProcessor()
        bot = 'test'
        stories = list(processor.get_stories(bot))
        assert stories[16]['name'] == 'story with form'
        assert stories[16]['type'] == 'STORY'
        assert stories[16]['steps'][0]['name'] == 'greet'
        assert stories[16]['steps'][0]['type'] == 'INTENT'
        assert stories[16]['steps'][1]['name'] == 'restaurant_form'
        assert stories[16]['steps'][1]['type'] == 'FORM_ACTION'
        assert stories[16]['template_type'] == 'CUSTOM'

    def test_delete_form_attached_to_story(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        with pytest.raises(AppException,
                           match='Cannot remove action "restaurant_form" linked to flow "story with form"'):
            processor.delete_form("restaurant_form", bot, user)

    def test_delete_story_with_form(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        processor.delete_complex_story("story with form", 'STORY', bot, user)
        assert Stories.objects(block_name="story with form", bot=bot,
                               events__name='restaurant_form', status=False).get()

    def test_update_story_step_that_is_attached_to_form(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
        ]
        story_dict = {'name': "story without action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        processor.add_complex_story(story_dict, bot, user)

        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_ask_restaurant_form_outdoor_seating", "type": "BOT"},
        ]
        story_dict = {'name': "story without action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        with pytest.raises(AppException,
                           match='utterance "utter_ask_restaurant_form_outdoor_seating" is attached to a form'):
            processor.update_complex_story(story_dict, bot, user)

    def test_add_slot_set_action_from_value_no_value_passed(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        Slots(name='name', type='text', bot=bot, user=user).save()
        action = {'name': 'action_set_slot', 'slot': 'name', 'type': SLOT_SET_TYPE.FROM_VALUE.value}
        processor.add_slot_set_action(action, bot, user)
        assert Actions.objects(name='action_set_slot', type=ActionType.slot_set_action.value,
                               bot=bot, user=user, status=True).get()
        assert SlotSetAction.objects(name='action_set_slot', type=SLOT_SET_TYPE.FROM_VALUE.value, slot='name',
                                     bot=bot, user=user, status=True).get()

    def test_add_story_with_slot_set_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "action_set_slot", "type": "SLOT_SET_ACTION"},
        ]
        story_dict = {'name': "story with slot_set_action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        assert processor.add_complex_story(story_dict, bot, user)
        stories = list(processor.get_stories(bot))
        story_with_form = [s for s in stories if s['name'] == 'story with slot_set_action']
        assert story_with_form[0]['steps'] == [
            {'name': 'greet', 'type': 'INTENT'},
            {'name': 'action_set_slot', 'type': 'SLOT_SET_ACTION'},
        ]

    def test_fetch_story_with_slot_set_action(self):
        processor = MongoProcessor()
        data = list(processor.get_stories("test"))
        slot_set_story = next(item for item in data if item['name'] == 'story with slot_set_action')
        assert slot_set_story['steps'] == [{'name': 'greet', 'type': 'INTENT'},
                                           {'name': 'action_set_slot', 'type': 'SLOT_SET_ACTION'}]
        assert slot_set_story['template_type'] == 'CUSTOM'
        assert slot_set_story['type'] == 'STORY'

    def test_add_slot_set_action_from_value(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        action = {'name': 'action_set_name_slot', 'slot': 'name', 'type': SLOT_SET_TYPE.FROM_VALUE.value, 'value': '5'}
        processor.add_slot_set_action(action, bot, user)
        assert Actions.objects(name='action_set_name_slot', type=ActionType.slot_set_action.value,
                               bot=bot, user=user, status=True).get()
        assert SlotSetAction.objects(name='action_set_name_slot', type=SLOT_SET_TYPE.FROM_VALUE.value, value='5',
                                     slot='name', bot=bot, user=user, status=True).get()

    def test_add_slot_set_action_reset(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        Slots(name='location', type='text', bot=bot, user=user).save()
        action = {'name': 'action_set_location_slot', 'slot': 'location', 'type': SLOT_SET_TYPE.RESET_SLOT.value}
        processor.add_slot_set_action(action, bot, user)
        assert Actions.objects(name='action_set_location_slot', type=ActionType.slot_set_action.value,
                               bot=bot, user=user, status=True).get()
        assert SlotSetAction.objects(name='action_set_location_slot', type=SLOT_SET_TYPE.RESET_SLOT.value, value=None,
                                     slot='location', bot=bot, user=user, status=True).get()

    def test_add_slot_set_action_already_exists(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        action = {'name': 'action_set_name_slot', 'slot': 'name', 'type': SLOT_SET_TYPE.FROM_VALUE.value, 'value': '5'}
        with pytest.raises(AppException, match=f'Slot setting action "{action["name"]}" exists'):
            processor.add_slot_set_action(action, bot, user)

    def test_add_slot_set_action_name_empty(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        action = {'name': ' ', 'slot': 'name', 'type': SLOT_SET_TYPE.FROM_VALUE.value, 'value': '5'}
        with pytest.raises(AppException, match='Slot setting action name and slot cannot be empty or spaces'):
            processor.add_slot_set_action(action, bot, user)

        action = {'name': None, 'slot': 'name', 'type': SLOT_SET_TYPE.FROM_VALUE.value, 'value': '5'}
        with pytest.raises(AppException, match='Slot setting action name and slot cannot be empty or spaces'):
            processor.add_slot_set_action(action, bot, user)

    def test_add_slot_set_action_slot_empty(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        action = {'name': 'action_set_slot_name', 'slot': ' ', 'type': SLOT_SET_TYPE.FROM_VALUE.value, 'value': '5'}
        with pytest.raises(AppException, match='Slot setting action name and slot cannot be empty or spaces'):
            processor.add_slot_set_action(action, bot, user)

        action = {'name': 'action_set_slot_name', 'slot': None, 'type': SLOT_SET_TYPE.FROM_VALUE.value, 'value': '5'}
        with pytest.raises(AppException, match='Slot setting action name and slot cannot be empty or spaces'):
            processor.add_slot_set_action(action, bot, user)

    def test_add_slot_set_action_slot_not_exists(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        action = {'name': 'action_set_slot_non_existant', 'slot': 'non_existant',
                  'type': SLOT_SET_TYPE.FROM_VALUE.value, 'value': '5'}
        with pytest.raises(AppException, match=f'Slot with name "{action["slot"]}" not found'):
            processor.add_slot_set_action(action, bot, user)

    def test_add_slot_set_action_simple_action_with_same_name_present(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        Actions(name='action_trigger_some_api', bot=bot, user=user).save()
        action = {'name': 'action_trigger_some_api', 'slot': 'some_api',
                  'type': SLOT_SET_TYPE.FROM_VALUE.value, 'value': '5'}
        with pytest.raises(AppException, match=f'Slot setting action "{action["name"]}" exists'):
            processor.add_slot_set_action(action, bot, user)

    def test_list_slot_set_actions(self):
        processor = MongoProcessor()
        bot = 'test'
        actions = processor.list_slot_set_actions(bot)
        assert len(actions) == 3
        assert actions[0] == {'name': 'action_set_slot', 'slot': 'name', 'type': SLOT_SET_TYPE.FROM_VALUE.value}
        assert actions[1] == {'name': 'action_set_name_slot', 'slot': 'name', 'type': SLOT_SET_TYPE.FROM_VALUE.value,
                              'value': '5'}
        assert actions[2] == {'name': 'action_set_location_slot', 'slot': 'location',
                              'type': SLOT_SET_TYPE.RESET_SLOT.value}

    def test_list_slot_set_actions_not_present(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        actions = processor.list_slot_set_actions(bot)
        assert len(actions) == 0

    def test_edit_slot_set_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        Slots(name='name_new', type='text', bot=bot, user=user).save()
        action = {'name': 'action_set_name_slot', 'slot': 'name_new', 'type': SLOT_SET_TYPE.RESET_SLOT.value,
                  'value': 'name'}
        processor.edit_slot_set_action(action, bot, user)
        assert Actions.objects(name='action_set_name_slot', type=ActionType.slot_set_action.value,
                               bot=bot, user=user, status=True).get()
        assert SlotSetAction.objects(name='action_set_name_slot', type=SLOT_SET_TYPE.RESET_SLOT.value, value='name',
                                     slot='name_new', bot=bot, user=user, status=True).get()

    def test_edit_slot_set_action_not_present(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        action = {'name': 'action_non_existant', 'slot': 'name_new', 'type': SLOT_SET_TYPE.FROM_VALUE.value,
                  'value': 'name'}
        with pytest.raises(AppException, match=f'Slot setting action with name "{action["name"]}" not found'):
            processor.edit_slot_set_action(action, bot, user)

    def test_edit_slot_set_action_slot_not_exists(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        action = {'name': 'action_set_name_slot', 'slot': 'slot_non_existant', 'type': SLOT_SET_TYPE.FROM_VALUE.value,
                  'value': 'name'}
        with pytest.raises(AppException, match=f'Slot with name "{action["slot"]}" not found'):
            processor.edit_slot_set_action(action, bot, user)

    def test_edit_slot_set_action_name_empty(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        action = {'name': ' ', 'slot': 'name', 'type': SLOT_SET_TYPE.FROM_VALUE.value,
                  'value': 'name'}
        with pytest.raises(AppException, match=f'Slot setting action with name "{action["name"]}" not found'):
            processor.edit_slot_set_action(action, bot, user)

    def test_edit_slot_set_action_slot_empty(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        action = {'name': 'action_set_name_slot', 'slot': ' ', 'type': SLOT_SET_TYPE.FROM_VALUE.value,
                  'value': 'name'}
        with pytest.raises(AppException, match=f'Slot with name "{action["slot"]}" not found'):
            processor.edit_slot_set_action(action, bot, user)

    def test_delete_slot_set_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        processor.delete_action('action_set_name_slot', bot, user)

    def test_delete_slot_set_action_already_deleted(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        with pytest.raises(AppException, match=f'Action with name "action_set_name_slot" not found'):
            processor.delete_action('action_set_name_slot', bot, user)

    def test_delete_slot_set_action_not_present(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        with pytest.raises(AppException, match=f'Action with name "action_non_existant" not found'):
            processor.delete_action('action_non_existant', bot, user)

    def test_delete_slot_set_action_linked_to_story(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        Slots(name='age', type='text', bot=bot, user=user).save()
        action = {'name': 'action_set_age_slot', 'slot': 'age', 'type': SLOT_SET_TYPE.RESET_SLOT.value}
        processor.add_slot_set_action(action, bot, user)
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "action_set_age_slot", "type": "SLOT_SET_ACTION"},
        ]
        story_dict = {'name': "story with slot set action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        processor.add_complex_story(story_dict, bot, user)
        with pytest.raises(AppException,
                           match=f'Cannot remove action "action_set_age_slot" linked to flow "story with slot set action"'):
            processor.delete_action('action_set_age_slot', bot, user)

    def test_delete_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        Actions(name='action_custom', bot=bot, user=user).save()
        processor.delete_action('action_custom', bot, user)

    def test_delete_action_already_deleted(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        with pytest.raises(AppException, match=f'Action with name "action_custom" not found'):
            processor.delete_action('action_custom', bot, user)

    def test_push_notifications_enabled_create_type_event(self):
        Utility.environment['notifications']['enable'] = True
        bot = 'test_notifications'
        user = 'test'
        server_endpoint = f"ws://localhost/events/"
        Utility.environment['notifications']['server_endpoint'] = server_endpoint

        def _mock_websocket_response(*args, **kwargs):
            return None

        with patch('kairon.shared.utils.Utility.websocket_request', autospec=True) as mock:
            mock.side_effect = _mock_websocket_response
            processor = MongoProcessor()
            processor.add_intent('greet', bot, user, False)
            assert mock.call_args.args[0] == 'ws://localhost/events/test_notifications'
            request_body = json.loads(mock.call_args.args[1])
            assert request_body['event_type'] == "create"
            assert request_body['event']['entity_type'] == "Intents"
            assert request_body['event']['data']['name'] == 'greet'
            assert request_body['event']['data']['bot'] == bot
            assert request_body['event']['data']['user'] == user
            assert not Utility.check_empty_string(request_body['event']['data']['timestamp'])
            assert request_body['event']['data']['status']
            assert not request_body['event']['data']['is_integration']
            assert not request_body['event']['data']['use_entities']

    def test_push_notifications_enabled_update_type_event(self):
        bot = "tests"
        user = 'testUser'
        server_endpoint = f"ws://localhost/events/"
        Utility.environment['notifications']['server_endpoint'] = server_endpoint

        def _mock_websocket_response(*args, **kwargs):
            return None

        with patch('kairon.shared.utils.Utility.websocket_request', autospec=True) as mock:
            mock.side_effect = _mock_websocket_response
            processor = MongoProcessor()
            examples = list(processor.get_training_examples("greet", bot))
            processor.edit_training_example(examples[0]["_id"], example="[Kanpur](location) India", intent="greet",
                                            bot=bot, user=user)
            assert mock.call_args.args[0] == 'ws://localhost/events/tests'
            request_body = json.loads(mock.call_args.args[1])
            assert request_body['event_type'] == "update"
            assert request_body['event']['entity_type'] == "TrainingExamples"
            assert request_body['event']['data']['intent'] == 'greet'
            assert not Utility.check_empty_string(request_body['event']['data']['text'])
            assert request_body['event']['data']['bot'] == bot
            assert request_body['event']['data']['user'] == user
            assert not Utility.check_empty_string(request_body['event']['data']['timestamp'])
            assert request_body['event']['data']['status']

    def test_push_notifications_enabled_delete_type_event(self):
        bot = "test"
        user = 'test'
        server_endpoint = f"ws://localhost/events/"
        Utility.environment['notifications']['server_endpoint'] = server_endpoint

        def _mock_websocket_response(*args, **kwargs):
            return None

        with patch('kairon.shared.utils.Utility.websocket_request', autospec=True) as mock:
            mock.side_effect = _mock_websocket_response
            processor = MongoProcessor()
            processor.delete_complex_story('story with slot_set_action', 'STORY', bot, user)
            with pytest.raises(DoesNotExist):
                Stories.objects(block_name="story with slot_set_action", bot=bot, status=True).get()
            assert mock.call_args.args[0] == 'ws://localhost/events/test'
            request_body = json.loads(mock.call_args.args[1])
            assert request_body['event_type'] == "delete"
            assert request_body['event']['entity_type'] == "Stories"
            assert request_body['event']['data'][0]['_id']

    def test_push_notifications_enabled_update_type_event_connection_error(self):
        bot = "test"
        user = 'test'
        utterance = 'utter_notifications'
        processor = MongoProcessor()
        processor.add_utterance_name(utterance, bot, user, raise_error_if_exists=True)
        assert Utterances.objects(bot=bot, status=True, name__iexact=utterance).get()

    def test_push_notifications_enabled_delete_type_connection_error(self):
        bot = "test"
        user = 'test'
        story_name = 'test_push_notifications'
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_thanks", "type": "ACTION"},
        ]
        story_dict = {'name': story_name, 'steps': steps, 'type': 'STORY', 'template_type': 'Q&A'}
        assert processor.add_complex_story(story_dict, bot, user)
        processor.delete_complex_story(story_name, 'STORY', bot, user)
        with pytest.raises(DoesNotExist):
            Stories.objects(block_name=story_name, bot=bot, status=True).get()
        Utility.environment['notifications']['enable'] = False

    @responses.activate
    def test_add_jira_action(self):
        bot = 'test'
        user = 'test_user'
        url = 'https://test-digite.atlassian.net'
        action = {
            'name': 'jira_action', 'url': url, 'user_name': 'test@digite.com',
            'api_token': 'ASDFGHJKL', 'project_key': 'HEL', 'issue_type': 'Bug', 'summary': 'new user',
            'response': 'We have logged a ticket'
        }
        responses.add(
            'GET',
            f'{url}/rest/api/2/serverInfo',
            json={'baseUrl': 'https://udit-pandey.atlassian.net', 'version': '1001.0.0-SNAPSHOT',
                  'versionNumbers': [1001, 0, 0], 'deploymentType': 'Cloud', 'buildNumber': 100191,
                  'buildDate': '2022-02-11T05:35:40.000+0530', 'serverTime': '2022-02-15T10:54:09.906+0530',
                  'scmInfo': '831671b3b59f40b5108ef3f9491df89a1317ecaa', 'serverTitle': 'Jira',
                  'defaultLocale': {'locale': 'en_US'}}
        )
        responses.add(
            'GET',
            f'{url}/rest/api/2/project/HEL',
            json={'expand': 'description,lead,issueTypes,url,projectKeys,permissions,insight',
                  'self': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000', 'id': '10000', 'key': 'HEL',
                  'description': '', 'lead': {
                    'self': 'https://udit-pandey.atlassian.net/rest/api/2/user?accountId=6205e1585d18ad00729aa75f',
                    'accountId': '6205e1585d18ad00729aa75f', 'avatarUrls': {
                        '48x48': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png',
                        '24x24': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png',
                        '16x16': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png',
                        '32x32': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png'},
                    'displayName': 'Udit Pandey', 'active': True}, 'components': [], 'issueTypes': [
                    {'self': 'https://udit-pandey.atlassian.net/rest/api/2/issuetype/10001', 'id': '10001',
                     'description': 'A small, distinct piece of work.',
                     'iconUrl': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10318?size=medium',
                     'name': 'Task', 'subtask': False, 'avatarId': 10318, 'hierarchyLevel': 0},
                    {'self': 'https://udit-pandey.atlassian.net/rest/api/2/issuetype/10002', 'id': '10002',
                     'description': 'A collection of related bugs, stories, and tasks.',
                     'iconUrl': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10307?size=medium',
                     'name': 'Epic', 'subtask': False, 'avatarId': 10307, 'hierarchyLevel': 1},
                    {'self': 'https://udit-pandey.atlassian.net/rest/api/2/issuetype/10003', 'id': '10003',
                     'description': 'Subtasks track small pieces of work that are part of a larger task.',
                     'iconUrl': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10316?size=medium',
                     'name': 'Bug', 'subtask': True, 'avatarId': 10316, 'hierarchyLevel': -1}],
                  'assigneeType': 'UNASSIGNED', 'versions': [], 'name': 'helicopter', 'roles': {
                    'atlassian-addons-project-access': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10007',
                    'Administrator': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10004',
                    'Viewer': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10006',
                    'Member': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10005'}, 'avatarUrls': {
                    '48x48': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408',
                    '24x24': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=small',
                    '16x16': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=xsmall',
                    '32x32': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=medium'},
                  'projectTypeKey': 'software', 'simplified': True, 'style': 'next-gen', 'isPrivate': False,
                  'properties': {}, 'entityId': '8a851ebf-72eb-461d-be68-4c2c28805440',
                  'uuid': '8a851ebf-72eb-461d-be68-4c2c28805440'}
        )
        processor = MongoProcessor()
        assert processor.add_jira_action(action, bot, user)

    def test_add_jira_action_already_exists(self):
        bot = 'test'
        user = 'test_user'
        url = 'https://test-digite.atlassian.net'
        action = {
            'name': 'jira_action', 'url': url, 'user_name': 'test@digite.com',
            'api_token': 'ASDFGHJKL', 'project_key': 'HEL', 'issue_type': 'Bug', 'summary': 'new user',
            'response': 'We have logged a ticket'
        }
        processor = MongoProcessor()
        with pytest.raises(AppException, match="Action exists!"):
            processor.add_jira_action(action, bot, user)

    def test_add_jira_action_existing_name(self):
        processor = MongoProcessor()
        bot = 'test'
        http_url = 'http://www.google.com'
        action = 'test_action'
        # file deepcode ignore HardcodedNonCryptoSecret: Random string for testing
        user = 'test_user'
        response = "json"
        request_method = 'GET'
        http_params_list: List[HttpActionParameters] = [
            HttpActionParameters(key="param1", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param2", value="value2", parameter_type="value")]
        header: List[HttpActionParameters] = [
            HttpActionParameters(key="param3", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param4", value="value2", parameter_type="value")]
        http_action_config = HttpActionConfigRequest(
            action_name=action,
            response=response,
            http_url=http_url,
            request_method=request_method,
            params_list=http_params_list,
            headers=header
        )
        processor.add_http_action_config(http_action_config.dict(), user, bot)

        bot = 'test'
        user = 'test_user'
        url = 'https://test-digite.atlassian.net'
        action = {
            'name': 'test_action', 'url': url, 'user_name': 'test@digite.com',
            'api_token': 'ASDFGHJKL', 'project_key': 'HEL', 'issue_type': 'Bug', 'summary': 'new user',
            'response': 'We have logged a ticket'
        }
        processor = MongoProcessor()
        with pytest.raises(AppException, match="Action exists!"):
            processor.add_jira_action(action, bot, user)

    @responses.activate
    def test_add_jira_action_different_bot(self):
        bot = 'test_2'
        user = 'test_user'
        url = 'https://test-digite.atlassian.net'
        action = {
            'name': 'jira_action', 'url': url, 'user_name': 'test@digite.com',
            'api_token': 'ASDFGHJKL', 'project_key': 'HEL', 'issue_type': 'Bug', 'summary': 'new user',
            'response': 'We have logged a ticket'
        }
        responses.add(
            'GET',
            f'{url}/rest/api/2/serverInfo',
            json={'baseUrl': 'https://udit-pandey.atlassian.net', 'version': '1001.0.0-SNAPSHOT',
                  'versionNumbers': [1001, 0, 0], 'deploymentType': 'Cloud', 'buildNumber': 100191,
                  'buildDate': '2022-02-11T05:35:40.000+0530', 'serverTime': '2022-02-15T10:54:09.906+0530',
                  'scmInfo': '831671b3b59f40b5108ef3f9491df89a1317ecaa', 'serverTitle': 'Jira',
                  'defaultLocale': {'locale': 'en_US'}}
        )
        responses.add(
            'GET',
            f'{url}/rest/api/2/project/HEL',
            json={'expand': 'description,lead,issueTypes,url,projectKeys,permissions,insight',
                  'self': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000', 'id': '10000', 'key': 'HEL',
                  'description': '', 'lead': {
                    'self': 'https://udit-pandey.atlassian.net/rest/api/2/user?accountId=6205e1585d18ad00729aa75f',
                    'accountId': '6205e1585d18ad00729aa75f', 'avatarUrls': {
                        '48x48': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png',
                        '24x24': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png',
                        '16x16': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png',
                        '32x32': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png'},
                    'displayName': 'Udit Pandey', 'active': True}, 'components': [], 'issueTypes': [
                    {'self': 'https://udit-pandey.atlassian.net/rest/api/2/issuetype/10001', 'id': '10001',
                     'description': 'A small, distinct piece of work.',
                     'iconUrl': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10318?size=medium',
                     'name': 'Task', 'subtask': False, 'avatarId': 10318, 'hierarchyLevel': 0},
                    {'self': 'https://udit-pandey.atlassian.net/rest/api/2/issuetype/10002', 'id': '10002',
                     'description': 'A collection of related bugs, stories, and tasks.',
                     'iconUrl': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10307?size=medium',
                     'name': 'Epic', 'subtask': False, 'avatarId': 10307, 'hierarchyLevel': 1},
                    {'self': 'https://udit-pandey.atlassian.net/rest/api/2/issuetype/10003', 'id': '10003',
                     'description': 'Subtasks track small pieces of work that are part of a larger task.',
                     'iconUrl': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10316?size=medium',
                     'name': 'Bug', 'subtask': True, 'avatarId': 10316, 'hierarchyLevel': -1}],
                  'assigneeType': 'UNASSIGNED', 'versions': [], 'name': 'helicopter', 'roles': {
                    'atlassian-addons-project-access': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10007',
                    'Administrator': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10004',
                    'Viewer': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10006',
                    'Member': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10005'}, 'avatarUrls': {
                    '48x48': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408',
                    '24x24': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=small',
                    '16x16': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=xsmall',
                    '32x32': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=medium'},
                  'projectTypeKey': 'software', 'simplified': True, 'style': 'next-gen', 'isPrivate': False,
                  'properties': {}, 'entityId': '8a851ebf-72eb-461d-be68-4c2c28805440',
                  'uuid': '8a851ebf-72eb-461d-be68-4c2c28805440'}
        )
        processor = MongoProcessor()
        assert processor.add_jira_action(action, bot, user)

    def test_add_jira_action_invalid_url(self, monkeypatch):
        bot = 'test'
        user = 'test_user'
        url = 'https://test-digite.atlassian.net'
        action = {
            'name': 'jira_action_new', 'url': url, 'user_name': 'test@digite.com',
            'api_token': 'ASDFGHJKL', 'project_key': 'HEL', 'issue_type': 'Bug', 'summary': 'new user',
            'response': 'We have logged a ticket'
        }

        def _mock_error(*args, **kwargs):
            raise JIRAError(status_code=404, url=url)

        monkeypatch.setattr(JIRA, '_create_http_basic_session', _mock_error)

        processor = MongoProcessor()
        with pytest.raises(ValidationError, match='Could not connect to url: *'):
            processor.add_jira_action(action, bot, user)

    def test_add_jira_action_invalid_url_runtime_error(self, monkeypatch):
        bot = 'test'
        user = 'test_user'
        url = 'https://test-digite.atlassian.net'
        action = {
            'name': 'jira_action_new', 'url': url, 'user_name': 'test@digite.com',
            'api_token': 'ASDFGHJKL', 'project_key': 'HEL', 'issue_type': 'Bug', 'summary': 'new user',
            'response': 'We have logged a ticket'
        }

        def _mock_error(*args, **kwargs):
            raise RuntimeError()

        monkeypatch.setattr(JIRA, '_create_http_basic_session', _mock_error)

        processor = MongoProcessor()
        with pytest.raises(ValidationError, match='Could not connect to url: *'):
            processor.add_jira_action(action, bot, user)

    @responses.activate
    def test_add_jira_action_invalid_project_key(self):
        bot = 'test'
        user = 'test_user'
        url = 'https://test-digite.atlassian.net'
        action = {
            'name': 'jira_action_new', 'url': url, 'user_name': 'test@digite.com',
            'api_token': 'ASDFGHJKL', 'project_key': 'HEL', 'issue_type': 'Bug', 'summary': 'new user',
            'response': 'We have logged a ticket'
        }
        responses.add(
            'GET',
            f'{url}/rest/api/2/serverInfo',
            json={'baseUrl': 'https://udit-pandey.atlassian.net', 'version': '1001.0.0-SNAPSHOT',
                  'versionNumbers': [1001, 0, 0], 'deploymentType': 'Cloud', 'buildNumber': 100191,
                  'buildDate': '2022-02-11T05:35:40.000+0530', 'serverTime': '2022-02-15T10:54:09.906+0530',
                  'scmInfo': '831671b3b59f40b5108ef3f9491df89a1317ecaa', 'serverTitle': 'Jira',
                  'defaultLocale': {'locale': 'en_US'}}
        )
        responses.add(
            'GET',
            f'{url}/rest/api/2/project/HEL',
            json={'errorMessages': ["No project could be found with key 'HAL'."], 'errors': {}},
            status=404
        )
        processor = MongoProcessor()
        with pytest.raises(ValidationError):
            processor.add_jira_action(action, bot, user)

    @responses.activate
    def test_add_jira_action_invalid_issue_type(self):
        bot = 'test'
        user = 'test_user'
        url = 'https://test-digite.atlassian.net'
        issue_type = 'ProdIssue'
        action = {
            'name': 'jira_action_new', 'url': url, 'user_name': 'test@digite.com',
            'api_token': 'ASDFGHJKL', 'project_key': 'HEL', 'issue_type': issue_type, 'summary': 'new user',
            'response': 'We have logged a ticket'
        }
        responses.add(
            'GET',
            f'{url}/rest/api/2/serverInfo',
            json={'baseUrl': 'https://udit-pandey.atlassian.net', 'version': '1001.0.0-SNAPSHOT',
                  'versionNumbers': [1001, 0, 0], 'deploymentType': 'Cloud', 'buildNumber': 100191,
                  'buildDate': '2022-02-11T05:35:40.000+0530', 'serverTime': '2022-02-15T10:54:09.906+0530',
                  'scmInfo': '831671b3b59f40b5108ef3f9491df89a1317ecaa', 'serverTitle': 'Jira',
                  'defaultLocale': {'locale': 'en_US'}}
        )
        responses.add(
            'GET',
            f'{url}/rest/api/2/project/HEL',
            json={'expand': 'description,lead,issueTypes,url,projectKeys,permissions,insight',
                  'self': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000', 'id': '10000', 'key': 'HEL',
                  'description': '', 'lead': {
                    'self': 'https://udit-pandey.atlassian.net/rest/api/2/user?accountId=6205e1585d18ad00729aa75f',
                    'accountId': '6205e1585d18ad00729aa75f', 'avatarUrls': {
                        '48x48': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png',
                        '24x24': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png',
                        '16x16': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png',
                        '32x32': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png'},
                    'displayName': 'Udit Pandey', 'active': True}, 'components': [], 'issueTypes': [
                    {'self': 'https://udit-pandey.atlassian.net/rest/api/2/issuetype/10001', 'id': '10001',
                     'description': 'A small, distinct piece of work.',
                     'iconUrl': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10318?size=medium',
                     'name': 'Task', 'subtask': False, 'avatarId': 10318, 'hierarchyLevel': 0},
                    {'self': 'https://udit-pandey.atlassian.net/rest/api/2/issuetype/10002', 'id': '10002',
                     'description': 'A collection of related bugs, stories, and tasks.',
                     'iconUrl': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10307?size=medium',
                     'name': 'Epic', 'subtask': False, 'avatarId': 10307, 'hierarchyLevel': 1},
                    {'self': 'https://udit-pandey.atlassian.net/rest/api/2/issuetype/10003', 'id': '10003',
                     'description': 'Subtasks track small pieces of work that are part of a larger task.',
                     'iconUrl': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10316?size=medium',
                     'name': 'Bug', 'subtask': True, 'avatarId': 10316, 'hierarchyLevel': -1}],
                  'assigneeType': 'UNASSIGNED', 'versions': [], 'name': 'helicopter', 'roles': {
                    'atlassian-addons-project-access': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10007',
                    'Administrator': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10004',
                    'Viewer': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10006',
                    'Member': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10005'}, 'avatarUrls': {
                    '48x48': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408',
                    '24x24': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=small',
                    '16x16': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=xsmall',
                    '32x32': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=medium'},
                  'projectTypeKey': 'software', 'simplified': True, 'style': 'next-gen', 'isPrivate': False,
                  'properties': {}, 'entityId': '8a851ebf-72eb-461d-be68-4c2c28805440',
                  'uuid': '8a851ebf-72eb-461d-be68-4c2c28805440'}
        )
        processor = MongoProcessor()
        with pytest.raises(ValidationError, match=f"No issue type '{issue_type}' exists"):
            processor.add_jira_action(action, bot, user)

    @responses.activate
    def test_add_jira_action_parent_key_not_given_for_subtask(self):
        bot = 'test'
        user = 'test_user'
        url = 'https://test-digite.atlassian.net'
        action = {
            'name': 'jira_action_new', 'url': url, 'user_name': 'test@digite.com',
            'api_token': 'ASDFGHJKL', 'project_key': 'HEL', 'issue_type': 'Subtask', 'summary': 'new user',
            'response': 'We have logged a ticket'
        }
        responses.add(
            'GET',
            f'{url}/rest/api/2/serverInfo',
            json={'baseUrl': 'https://udit-pandey.atlassian.net', 'version': '1001.0.0-SNAPSHOT',
                  'versionNumbers': [1001, 0, 0], 'deploymentType': 'Cloud', 'buildNumber': 100191,
                  'buildDate': '2022-02-11T05:35:40.000+0530', 'serverTime': '2022-02-15T10:54:09.906+0530',
                  'scmInfo': '831671b3b59f40b5108ef3f9491df89a1317ecaa', 'serverTitle': 'Jira',
                  'defaultLocale': {'locale': 'en_US'}}
        )
        responses.add(
            'GET',
            f'{url}/rest/api/2/project/HEL',
            json={'expand': 'description,lead,issueTypes,url,projectKeys,permissions,insight',
                  'self': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000', 'id': '10000', 'key': 'HEL',
                  'description': '', 'lead': {
                    'self': 'https://udit-pandey.atlassian.net/rest/api/2/user?accountId=6205e1585d18ad00729aa75f',
                    'accountId': '6205e1585d18ad00729aa75f', 'avatarUrls': {
                        '48x48': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png',
                        '24x24': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png',
                        '16x16': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png',
                        '32x32': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png'},
                    'displayName': 'Udit Pandey', 'active': True}, 'components': [], 'issueTypes': [
                    {'self': 'https://udit-pandey.atlassian.net/rest/api/2/issuetype/10001', 'id': '10001',
                     'description': 'A small, distinct piece of work.',
                     'iconUrl': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10318?size=medium',
                     'name': 'Task', 'subtask': False, 'avatarId': 10318, 'hierarchyLevel': 0},
                    {'self': 'https://udit-pandey.atlassian.net/rest/api/2/issuetype/10002', 'id': '10002',
                     'description': 'A collection of related bugs, stories, and tasks.',
                     'iconUrl': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10307?size=medium',
                     'name': 'Subtask', 'subtask': True, 'avatarId': 10307, 'hierarchyLevel': 1},
                    {'self': 'https://udit-pandey.atlassian.net/rest/api/2/issuetype/10003', 'id': '10003',
                     'description': 'Subtasks track small pieces of work that are part of a larger task.',
                     'iconUrl': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10316?size=medium',
                     'name': 'Bug', 'subtask': True, 'avatarId': 10316, 'hierarchyLevel': -1}],
                  'assigneeType': 'UNASSIGNED', 'versions': [], 'name': 'helicopter', 'roles': {
                    'atlassian-addons-project-access': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10007',
                    'Administrator': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10004',
                    'Viewer': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10006',
                    'Member': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10005'}, 'avatarUrls': {
                    '48x48': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408',
                    '24x24': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=small',
                    '16x16': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=xsmall',
                    '32x32': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=medium'},
                  'projectTypeKey': 'software', 'simplified': True, 'style': 'next-gen', 'isPrivate': False,
                  'properties': {}, 'entityId': '8a851ebf-72eb-461d-be68-4c2c28805440',
                  'uuid': '8a851ebf-72eb-461d-be68-4c2c28805440'}
        )
        processor = MongoProcessor()
        with pytest.raises(ValidationError, match="parent key is required for issues of type 'Subtask'"):
            processor.add_jira_action(action, bot, user)

    def test_list_jira_actions(self):
        bot = 'test'
        processor = MongoProcessor()
        jira_actions = list(processor.list_jira_actions(bot))
        assert jira_actions == [
            {'name': 'jira_action', 'url': 'https://test-digite.atlassian.net', 'user_name': 'test@digite.com',
             'api_token': 'ASDFGH***', 'project_key': 'HEL', 'issue_type': 'Bug', 'summary': 'new user',
             'response': 'We have logged a ticket'}]

        jira_actions = list(processor.list_jira_actions(bot, False))
        assert jira_actions == [
            {'name': 'jira_action', 'url': 'https://test-digite.atlassian.net', 'user_name': 'test@digite.com',
             'api_token': 'ASDFGHJKL', 'project_key': 'HEL', 'issue_type': 'Bug', 'summary': 'new user',
             'response': 'We have logged a ticket'}]

    @responses.activate
    def test_edit_jira_action(self):
        bot = 'test'
        user = 'test_user'
        url = 'https://test-digite.atlassian.net'
        action = {
            'name': 'jira_action', 'url': url, 'user_name': 'test@digite.com',
            'api_token': 'ASDFGHJKL', 'project_key': 'HEL', 'issue_type': 'Subtask', 'parent_key': 'HEL-4',
            'summary': 'new user',
            'response': 'We have logged a ticket'
        }
        responses.add(
            'GET',
            f'{url}/rest/api/2/serverInfo',
            json={'baseUrl': 'https://udit-pandey.atlassian.net', 'version': '1001.0.0-SNAPSHOT',
                  'versionNumbers': [1001, 0, 0], 'deploymentType': 'Cloud', 'buildNumber': 100191,
                  'buildDate': '2022-02-11T05:35:40.000+0530', 'serverTime': '2022-02-15T10:54:09.906+0530',
                  'scmInfo': '831671b3b59f40b5108ef3f9491df89a1317ecaa', 'serverTitle': 'Jira',
                  'defaultLocale': {'locale': 'en_US'}}
        )
        responses.add(
            'GET',
            f'{url}/rest/api/2/project/HEL',
            json={'expand': 'description,lead,issueTypes,url,projectKeys,permissions,insight',
                  'self': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000', 'id': '10000', 'key': 'HEL',
                  'description': '', 'lead': {
                    'self': 'https://udit-pandey.atlassian.net/rest/api/2/user?accountId=6205e1585d18ad00729aa75f',
                    'accountId': '6205e1585d18ad00729aa75f', 'avatarUrls': {
                        '48x48': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png',
                        '24x24': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png',
                        '16x16': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png',
                        '32x32': 'https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png'},
                    'displayName': 'Udit Pandey', 'active': True}, 'components': [], 'issueTypes': [
                    {'self': 'https://udit-pandey.atlassian.net/rest/api/2/issuetype/10001', 'id': '10001',
                     'description': 'A small, distinct piece of work.',
                     'iconUrl': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10318?size=medium',
                     'name': 'Task', 'subtask': False, 'avatarId': 10318, 'hierarchyLevel': 0},
                    {'self': 'https://udit-pandey.atlassian.net/rest/api/2/issuetype/10002', 'id': '10002',
                     'description': 'A collection of related bugs, stories, and tasks.',
                     'iconUrl': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10307?size=medium',
                     'name': 'Subtask', 'subtask': True, 'avatarId': 10307, 'hierarchyLevel': 1},
                    {'self': 'https://udit-pandey.atlassian.net/rest/api/2/issuetype/10003', 'id': '10003',
                     'description': 'Subtasks track small pieces of work that are part of a larger task.',
                     'iconUrl': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10316?size=medium',
                     'name': 'Bug', 'subtask': True, 'avatarId': 10316, 'hierarchyLevel': -1}],
                  'assigneeType': 'UNASSIGNED', 'versions': [], 'name': 'helicopter', 'roles': {
                    'atlassian-addons-project-access': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10007',
                    'Administrator': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10004',
                    'Viewer': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10006',
                    'Member': 'https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10005'}, 'avatarUrls': {
                    '48x48': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408',
                    '24x24': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=small',
                    '16x16': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=xsmall',
                    '32x32': 'https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=medium'},
                  'projectTypeKey': 'software', 'simplified': True, 'style': 'next-gen', 'isPrivate': False,
                  'properties': {}, 'entityId': '8a851ebf-72eb-461d-be68-4c2c28805440',
                  'uuid': '8a851ebf-72eb-461d-be68-4c2c28805440'}
        )
        processor = MongoProcessor()
        assert not processor.edit_jira_action(action, bot, user)

    def test_edit_jira_action_not_exists(self):
        bot = 'test'
        user = 'test_user'
        url = 'https://test-digite.atlassian.net'
        action = {
            'name': 'jira_action_not_exists', 'url': url, 'user_name': 'test@digite.com',
            'api_token': 'ASDFGHJKL', 'project_key': 'HEL', 'issue_type': 'Subtask', 'parent_key': 'HEL-4',
            'summary': 'new user',
            'response': 'We have logged a ticket'
        }
        processor = MongoProcessor()
        with pytest.raises(AppException, match=f'Action with name "{action.get("name")}" not found'):
            processor.edit_jira_action(action, bot, user)

    def test_list_jira_actions_after_update(self):
        bot = 'test'
        processor = MongoProcessor()
        jira_actions = list(processor.list_jira_actions(bot))
        assert jira_actions == [
            {'name': 'jira_action', 'url': 'https://test-digite.atlassian.net', 'user_name': 'test@digite.com',
             'api_token': 'ASDFGH***', 'project_key': 'HEL', 'issue_type': 'Subtask', 'parent_key': 'HEL-4',
             'summary': 'new user', 'response': 'We have logged a ticket'}
        ]

        jira_actions = list(processor.list_jira_actions(bot, False))
        assert jira_actions == [
            {'name': 'jira_action', 'url': 'https://test-digite.atlassian.net', 'user_name': 'test@digite.com',
             'api_token': 'ASDFGHJKL', 'project_key': 'HEL', 'issue_type': 'Subtask', 'parent_key': 'HEL-4',
             'summary': 'new user', 'response': 'We have logged a ticket'}
        ]

    def test_add_jira_action_with_story(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "jira_action", "type": "JIRA_ACTION"},
        ]
        story_dict = {'name': "story with jira action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        assert processor.add_complex_story(story_dict, bot, user)
        story = Stories.objects(block_name="story with jira action", bot=bot, events__name='jira_action',
                                status=True).get()
        assert story.events[1].type == 'action'
        stories = list(processor.get_stories(bot))
        story_with_form = [s for s in stories if s['name'] == 'story with jira action']
        assert story_with_form[0]['steps'] == [
            {'name': 'greet', 'type': 'INTENT'},
            {'name': 'jira_action', 'type': 'JIRA_ACTION'},
        ]
        processor.delete_complex_story("story with jira action", 'STORY', bot, user)

    def test_delete_jira_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        processor.delete_action('jira_action', bot, user)
        with pytest.raises(DoesNotExist):
            JiraAction.objects(name='jira_action', status=True, bot=bot).get()
        with pytest.raises(DoesNotExist):
            Actions.objects(name='jira_action', status=True, bot=bot).get()

    def test_list_zendesk_actions_empty(self):
        bot = 'test'
        processor = MongoProcessor()
        assert list(processor.list_zendesk_actions(bot)) == []

    def test_add_zendesk_action(self):
        bot = 'test'
        user = 'test'
        action = {'name': 'zendesk_action', 'subdomain': 'digite751', 'api_token': '123456789', 'subject': 'new ticket',
                  'user_name': 'udit.pandey@digite.com', 'response': 'ticket filed'}
        processor = MongoProcessor()
        with patch('zenpy.Zenpy'):
            assert processor.add_zendesk_action(action, bot, user)

    def test_add_zendesk_action_with_story(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "zendesk_action", "type": "ZENDESK_ACTION"},
        ]
        story_dict = {'name': "story with zendesk action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        assert processor.add_complex_story(story_dict, bot, user)
        story = Stories.objects(block_name="story with zendesk action", bot=bot,
                                events__name='zendesk_action', status=True).get()
        assert story.events[1].type == 'action'
        stories = list(processor.get_stories(bot))
        story_with_form = [s for s in stories if s['name'] == 'story with zendesk action']
        assert story_with_form[0]['steps'] == [
            {"name": "greet", "type": "INTENT"},
            {"name": "zendesk_action", "type": "ZENDESK_ACTION"},
        ]
        processor.delete_complex_story('story with zendesk action', 'STORY', bot, user)

    def test_add_zendesk_action_invalid_subdomain(self):
        bot = 'test'
        user = 'test'
        action = {'name': 'zendesk_action_1', 'subdomain': 'digite751', 'api_token': '123456789',
                  'subject': 'new ticket',
                  'user_name': 'udit.pandey@digite.com', 'response': 'ticket filed'}

        def __mock_zendesk_error(*args, **kwargs):
            from zenpy.lib.exception import APIException
            raise APIException({"error": {"title": "No help desk at digite751.zendesk.com"}})

        processor = MongoProcessor()
        with patch('zenpy.Zenpy') as mock:
            mock.side_effect = __mock_zendesk_error
            with pytest.raises(ValidationError):
                assert processor.add_zendesk_action(action, bot, user)

    def test_add_zendesk_action_invalid_credentials(self):
        bot = 'test'
        user = 'test'
        action = {'name': 'zendesk_action_1', 'subdomain': 'digite751', 'api_token': '123456789',
                  'subject': 'new ticket',
                  'user_name': 'udit.pandey@digite.com', 'response': 'ticket filed'}

        def __mock_zendesk_error(*args, **kwargs):
            from zenpy.lib.exception import APIException
            raise APIException({"error": "Couldn't authenticate you"})

        processor = MongoProcessor()
        with patch('zenpy.Zenpy') as mock:
            mock.side_effect = __mock_zendesk_error
            with pytest.raises(ValidationError):
                assert processor.add_zendesk_action(action, bot, user)

    def test_add_zendesk_action_already_exists(self):
        bot = 'test'
        user = 'test'
        action = {'name': 'zendesk_action', 'subdomain': 'digite751', 'api_token': '123456789', 'subject': 'new ticket',
                  'user_name': 'udit.pandey@digite.com', 'response': 'ticket filed'}
        processor = MongoProcessor()
        with pytest.raises(AppException, match='Action exists!'):
            assert processor.add_zendesk_action(action, bot, user)

    def test_add_zendesk_action_existing_name(self):
        processor = MongoProcessor()
        bot = 'test'
        http_url = 'http://www.google.com'
        action = 'test_action_1'
        # file deepcode ignore HardcodedNonCryptoSecret: Random string for testing
        user = 'test'
        response = "json"
        request_method = 'GET'
        http_params_list: List[HttpActionParameters] = [
            HttpActionParameters(key="param1", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param2", value="value2", parameter_type="value")]
        header: List[HttpActionParameters] = [
            HttpActionParameters(key="param3", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param4", value="value2", parameter_type="value")]
        http_action_config = HttpActionConfigRequest(
            action_name=action,
            response=response,
            http_url=http_url,
            request_method=request_method,
            params_list=http_params_list,
            headers=header
        )
        processor.add_http_action_config(http_action_config.dict(), user, bot)

        bot = 'test'
        user = 'test'
        action = {'name': 'test_action_1', 'subdomain': 'digite751', 'api_token': '123456789', 'subject': 'new ticket',
                  'user_name': 'udit.pandey@digite.com', 'response': 'ticket filed'}
        processor = MongoProcessor()
        with pytest.raises(AppException, match='Action exists!'):
            assert processor.add_zendesk_action(action, bot, user)

    def test_edit_zendesk_action(self):
        bot = 'test'
        user = 'test'
        action = {'name': 'zendesk_action', 'subdomain': 'digite756', 'api_token': '123456789999',
                  'subject': 'new ticket',
                  'user_name': 'udit.pandey@digite.com', 'response': 'ticket filed here'}
        processor = MongoProcessor()
        with patch('zenpy.Zenpy'):
            processor.edit_zendesk_action(action, bot, user)

    def test_edit_zendesk_action_invalid_subdomain(self):
        bot = 'test'
        user = 'test'
        action = {'name': 'zendesk_action', 'subdomain': 'digite751', 'api_token': '123456789',
                  'subject': 'new ticket', 'user_name': 'udit.pandey@digite.com',
                  'response': 'ticket filed'}

        def __mock_zendesk_error(*args, **kwargs):
            from zenpy.lib.exception import APIException
            raise APIException({"error": {"title": "No help desk at digite751.zendesk.com"}})

        processor = MongoProcessor()
        with patch('zenpy.Zenpy') as mock:
            mock.side_effect = __mock_zendesk_error
            with pytest.raises(ValidationError):
                assert processor.edit_zendesk_action(action, bot, user)

    def test_edit_zendesk_action_does_not_exists(self):
        bot = 'test'
        user = 'test'
        action = {'name': 'zendesk_action_1', 'subdomain': 'digite751', 'api_token': '123456789',
                  'subject': 'new ticket',
                  'user_name': 'udit.pandey@digite.com', 'response': 'ticket filed'}
        processor = MongoProcessor()
        with pytest.raises(AppException, match=f'Action with name "{action.get("name")}" not found'):
            assert processor.edit_zendesk_action(action, bot, user)

    def test_list_zendesk_actions(self):
        bot = 'test'
        processor = MongoProcessor()
        assert list(processor.list_zendesk_actions(bot)) == [
            {'name': 'zendesk_action', 'subdomain': 'digite756', 'user_name': 'udit.pandey@digite.com',
             'api_token': '123456789***', 'subject': 'new ticket', 'response': 'ticket filed here'}]
        bot = 'test_1'
        processor = MongoProcessor()
        assert list(processor.list_zendesk_actions(bot)) == []

    def test_list_zendesk_actions_unmasked(self):
        bot = 'test'
        processor = MongoProcessor()
        assert list(processor.list_zendesk_actions(bot, False)) == [
            {'name': 'zendesk_action', 'subdomain': 'digite756', 'user_name': 'udit.pandey@digite.com',
             'api_token': '123456789999', 'subject': 'new ticket', 'response': 'ticket filed here'}]

    def test_delete_zendesk_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        processor.delete_action('zendesk_action', bot, user)
        with pytest.raises(DoesNotExist):
            Actions.objects(name='zendesk_action', status=True, bot=bot).get()
        with pytest.raises(DoesNotExist):
            PipedriveLeadsAction.objects(name='zendesk_action', status=True, bot=bot).get()

    def test_add_pipedrive_leads_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action = {
            'name': 'pipedrive_leads',
            'domain': 'https://digite751.pipedrive.com/',
            'api_token': '12345678',
            'title': 'new lead',
            'response': 'I have failed to create lead for you',
            'metadata': {'name': 'name', 'org_name': 'organization', 'email': 'email', 'phone': 'phone'}
        }
        with patch('pipedrive.client.Client'):
            assert processor.add_pipedrive_action(action, bot, user)
        assert Actions.objects(name='pipedrive_leads', status=True, bot=bot).get()
        assert PipedriveLeadsAction.objects(name='pipedrive_leads', status=True, bot=bot).get()

    def test_add_pipedrive_leads_action_required_metadata_absent(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action = {
            'name': 'pipedrive_invalid_metadata',
            'domain': 'https://digite751.pipedrive.com/',
            'api_token': '12345678',
            'title': 'new lead',
            'response': 'I have failed to create lead for you',
            'metadata': {'org_name': 'organization', 'email': 'email', 'phone': 'phone'}
        }
        with pytest.raises(ValidationError, match='metadata: name is required'):
            with patch('pipedrive.client.Client'):
                assert processor.add_pipedrive_action(action, bot, user)

    def test_add_pipedrive_leads_action_invalid_auth(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action = {
            'name': 'pipedrive_invalid_metadata',
            'domain': 'https://digite751.pipedrive.com/',
            'api_token': '12345678',
            'title': 'new lead',
            'response': 'I have failed to create lead for you',
            'metadata': {'name': 'name', 'org_name': 'organization', 'email': 'email', 'phone': 'phone'}
        }

        def __mock_exception(*args, **kwargs):
            raise UnauthorizedError('Invalid authentication', {'error_code': 401})

        with pytest.raises(ValidationError, match='Invalid authentication*'):
            with patch('pipedrive.client.Client', __mock_exception):
                assert processor.add_pipedrive_action(action, bot, user)

    def test_add_pipedrive_leads_action_with_story(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "pipedrive_leads", "type": "PIPEDRIVE_LEADS_ACTION"},
        ]
        story_dict = {'name': "story with pipedrive leads", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        assert processor.add_complex_story(story_dict, bot, user)
        story = Stories.objects(block_name="story with pipedrive leads", bot=bot,
                                events__name='pipedrive_leads', status=True).get()
        assert story.events[1].type == 'action'
        stories = list(processor.get_stories(bot))
        story_with_form = [s for s in stories if s['name'] == 'story with pipedrive leads']
        assert story_with_form[0]['steps'] == [
            {"name": "greet", "type": "INTENT"},
            {"name": "pipedrive_leads", "type": "PIPEDRIVE_LEADS_ACTION"},
        ]
        processor.delete_complex_story('story with pipedrive leads', 'STORY', bot, user)

    def test_add_pipedrive_leads_action_duplicate(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action = {
            'name': 'pipedrive_leads',
            'domain': 'https://digite751.pipedrive.com/',
            'api_token': '12345678',
            'title': 'new lead',
            'response': 'I have failed to create lead for you',
            'metadata': {'name': 'name', 'org_name': 'organization', 'email': 'email', 'phone': 'phone'}
        }
        with pytest.raises(AppException, match='Action exists!'):
            processor.add_pipedrive_action(action, bot, user)

    def test_add_pipedrive_leads_action_existing_name(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action = {
            'name': 'pipedrive_leads_action',
            'domain': 'https://digite751.pipedrive.com/',
            'api_token': '12345678',
            'title': 'new lead',
            'response': 'I have failed to create lead for you',
            'metadata': {'name': 'name', 'org_name': 'organization', 'email': 'email', 'phone': 'phone'}
        }
        Actions(name='pipedrive_leads_action', type=ActionType.pipedrive_leads_action.value, bot=bot, user=user).save()
        with pytest.raises(AppException, match='Action exists!'):
            processor.add_pipedrive_action(action, bot, user)

    def test_list_pipedrive_leads_action_masked(self):
        processor = MongoProcessor()
        bot = 'test'
        actions = list(processor.list_pipedrive_actions(bot))
        assert actions[0]['name'] == 'pipedrive_leads'
        assert actions[0]['api_token'] == '12345***'
        assert actions[0]['domain'] == 'https://digite751.pipedrive.com/'
        assert actions[0]['response'] == 'I have failed to create lead for you'
        assert actions[0]['title'] == 'new lead'
        assert actions[0]['metadata'] == {'name': 'name', 'org_name': 'organization', 'email': 'email', 'phone': 'phone'}

    def test_edit_pipedrive_leads_action_not_exists(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action = {
            'name': 'pipedrive_invalid_metadata',
            'domain': 'https://digite751.pipedrive.com/',
            'api_token': '12345678',
            'title': 'new lead',
            'response': 'I have failed to create lead for you',
            'metadata': {'name': 'name', 'org_name': 'organization', 'email': 'email', 'phone': 'phone'}
        }
        with pytest.raises(AppException, match='Action with name "pipedrive_invalid_metadata" not found'):
            processor.edit_pipedrive_action(action, bot, user)

    def test_edit_pipedrive_leads_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action = {
            'name': 'pipedrive_leads',
            'domain': 'https://digite7.pipedrive.com/',
            'api_token': 'asdfghjklertyui',
            'title': 'new lead generated',
            'response': 'Failed to create lead for you',
            'metadata': {'name': 'name', 'email': 'email', 'phone': 'phone'}
        }
        with patch('pipedrive.client.Client'):
            assert not processor.edit_pipedrive_action(action, bot, user)

    def test_list_pipedrive_leads_action(self):
        processor = MongoProcessor()
        bot = 'test'
        actions = list(processor.list_pipedrive_actions(bot, False))
        assert actions[0]['name'] == 'pipedrive_leads'
        assert actions[0]['api_token'] == 'asdfghjklertyui'
        assert actions[0]['domain'] == 'https://digite7.pipedrive.com/'
        assert actions[0]['response'] == 'Failed to create lead for you'
        assert actions[0]['title'] == 'new lead generated'
        assert actions[0]['metadata'] == {'name': 'name', 'email': 'email', 'phone': 'phone'}

        actions = list(processor.list_pipedrive_actions(bot, True))
        assert actions[0]['name'] == 'pipedrive_leads'
        assert actions[0]['api_token'] == 'asdfghjklert***'
        assert actions[0]['domain'] == 'https://digite7.pipedrive.com/'
        assert actions[0]['response'] == 'Failed to create lead for you'
        assert actions[0]['title'] == 'new lead generated'
        assert actions[0]['metadata'] == {'name': 'name', 'email': 'email', 'phone': 'phone'}

    def test_delete_pipedrive_leads_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        processor.delete_action('pipedrive_leads', bot, user)
        with pytest.raises(DoesNotExist):
            Actions.objects(name='pipedrive_leads', status=True, bot=bot).get()
        with pytest.raises(DoesNotExist):
            PipedriveLeadsAction.objects(name='pipedrive_leads', status=True, bot=bot).get()

    def test_push_notifications_enabled_message_type_event(self):
        bot = "test"
        user = 'test'
        server_endpoint = f"ws://localhost/events/"
        Utility.environment['notifications']['enable'] = True
        Utility.environment['notifications']['server_endpoint'] = server_endpoint

        def _mock_websocket_response(*args, **kwargs):
            return None

        with patch('kairon.shared.utils.Utility.websocket_request', autospec=True) as mock:
            mock.side_effect = _mock_websocket_response
            ModelProcessor.set_training_status(bot, user, "Inprogress")
            assert mock.call_args.args[0] == 'ws://localhost/events/test'
            request_body = json.loads(mock.call_args.args[1])
            assert request_body['event_type'] == "message"
            assert request_body['event']['entity_type'] == "ModelTraining"
            assert request_body['event']['data']['status'] == 'Inprogress'
            assert request_body['event']['data']['bot'] == bot
            assert request_body['event']['data']['user'] == user
            assert not Utility.check_empty_string(request_body['event']['data']['start_timestamp'])

    def test_delete_valid_intent_only(self):
        processor = MongoProcessor()
        processor.add_intent("TestingDelGreeting", "tests", "testUser", is_integration=False)
        processor.delete_intent("TestingDelGreeting", "tests", "testUser", is_integration=False,
                                delete_dependencies=False)
        with pytest.raises(Exception):
            intent = Intents.objects(bot="tests", status=True).get(name="TestingDelGreeting")

    def test_delete_invalid_intent(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            processor.delete_intent("TestingDelGreetingInvalid", "tests", "testUser", is_integration=False)

    def test_delete_empty_intent(self):
        processor = MongoProcessor()
        with pytest.raises(AssertionError):
            processor.delete_intent("", "tests", "testUser", is_integration=False)

    def test_delete_valid_intent(self):
        processor = MongoProcessor()
        processor.add_intent("TestingDelGreeting", "tests", "testUser", is_integration=False)
        processor.delete_intent("TestingDelGreeting", "tests", "testUser", is_integration=False)

    def test_delete_intent_case_insensitive(self):
        processor = MongoProcessor()
        processor.add_intent("TestingDelGreeting", "tests", "testUser", is_integration=False)
        processor.delete_intent("testingdelgreeting", "tests", "testUser", is_integration=False)

    def test_intent_no_stories(self):
        processor = MongoProcessor()
        processor.add_intent("TestingDelGreeting", "tests", "testUser", is_integration=False)
        processor.add_training_example(["Hows You Doing!"], "TestingDelGreeting", "tests", "testUser",
                                       is_integration=False)
        processor.delete_intent("TestingDelGreeting", "tests", "testUser", is_integration=False)
        actual = processor.get_intents("tests")
        assert not any(intent['name'] == 'TestingDelGreeting' for intent in actual)
        actual = len(list(processor.get_training_examples("TestingDelGreeting", "tests")))
        assert not actual

    def test_get_intents_and_training_examples(self):
        processor = MongoProcessor()
        actual = processor.get_intents_and_training_examples("tests")
        assert len(actual) == 17

    def test_delete_intent_no_training_examples(self):
        processor = MongoProcessor()
        processor.add_intent("TestingDelGreeting", "tests", "testUser", is_integration=False)
        processor.delete_intent("TestingDelGreeting", "tests", "testUser", is_integration=False)
        actual = processor.get_intents("tests")
        assert not any(intent['name'] == 'TestingDelGreeting' for intent in actual)

    def test_delete_intent_no_utterance(self):
        processor = MongoProcessor()
        processor.add_intent("TestingDelGreeting", "tests", "testUser", is_integration=False)
        processor.delete_intent("TestingDelGreeting", "tests", "testUser", is_integration=False)
        actual = processor.get_intents("tests")
        assert not any(intent['name'] == 'TestingDelGreeting' for intent in actual)

    def test_delete_intent_with_examples_stories_utterance(self):
        processor = MongoProcessor()
        processor.add_intent("TestingDelGreeting", "tests", "testUser", is_integration=False)
        processor.add_training_example(["hello", "hi"], "TestingDelGreeting", "tests", "testUser", is_integration=False)
        processor.delete_intent("TestingDelGreeting", "tests", "testUser", is_integration=False)
        actual = processor.get_intents("tests")
        assert not any(intent['name'] == 'TestingDelGreeting' for intent in actual)
        actual = list(processor.get_training_examples('TestingDelGreeting', "tests"))
        assert len(actual) == 0

    def test_move_training_example(self):
        processor = MongoProcessor()
        list(processor.add_training_example(["moving to another location", "i will stay"], "test_move_training_example",
                                            "tests", "testUser", is_integration=False))
        list(processor.add_training_example(
            ["moving to another intent [move_to_location](move_to_location)", "i will be here"],
            "move_training_example",
            "tests", "testUser", is_integration=False))
        list(processor.add_training_example(["this is forever"], "move_to_location",
                                            "tests", "testUser", is_integration=False))
        examples_to_move = ["moving to another location", "moving to another place",
                            "moving to another intent [move_to_location](move_to_location)", "this is new", "", " "]
        result = list(processor.add_or_move_training_example(examples_to_move, 'move_to_location', "tests", "testUser"))
        actual = list(processor.get_training_examples('move_to_location', "tests"))
        assert len(actual) == 5
        actual = list(processor.get_training_examples('test_move_training_example', "tests"))
        assert len(actual) == 1
        actual = list(processor.get_training_examples('move_training_example', "tests"))
        assert len(actual) == 1

    def test_move_training_example_intent_not_exists(self):
        processor = MongoProcessor()
        examples_to_move = ["moving to another location", "moving to another place", "", " "]
        with pytest.raises(AppException, match='Intent does not exists'):
            list(processor.add_or_move_training_example(examples_to_move, 'non_existent', "tests", "testUser"))

    def test_add_http_action_config(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        http_url = 'http://www.google.com'
        action = 'test_action'
        # file deepcode ignore HardcodedNonCryptoSecret: Random string for testing
        user = 'test_user'
        response = "json"
        request_method = 'GET'
        http_params_list: List[HttpActionParameters] = [
            HttpActionParameters(key="param1", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param2", value="value2", parameter_type="value")]
        header: List[HttpActionParameters] = [
            HttpActionParameters(key="param3", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param4", value="value2", parameter_type="value")]
        http_action_config = HttpActionConfigRequest(
            action_name=action,
            response=response,
            http_url=http_url,
            request_method=request_method,
            params_list=http_params_list,
            headers=header
        )
        processor.add_http_action_config(http_action_config.dict(), user, bot)
        actual_http_action = HttpActionConfig.objects(action_name=action, bot=bot, user=user, status=True).get(
            action_name__iexact=action)
        assert actual_http_action is not None
        assert actual_http_action['action_name'] == action
        assert actual_http_action['http_url'] == http_url
        assert actual_http_action['response'] == response
        assert actual_http_action['request_method'] == request_method
        assert actual_http_action['params_list'] is not None
        assert actual_http_action['params_list'][0]['key'] == "param1"
        assert actual_http_action['params_list'][0]['value'] == "param1"
        assert actual_http_action['params_list'][0]['parameter_type'] == "slot"
        assert actual_http_action['params_list'][1]['key'] == "param2"
        assert actual_http_action['params_list'][1]['value'] == "value2"
        assert actual_http_action['params_list'][1]['parameter_type'] == "value"
        assert actual_http_action['headers'][0]['key'] == "param3"
        assert actual_http_action['headers'][0]['value'] == "param1"
        assert actual_http_action['headers'][0]['parameter_type'] == "slot"
        assert actual_http_action['headers'][1]['key'] == "param4"
        assert actual_http_action['headers'][1]['value'] == "value2"
        assert actual_http_action['headers'][1]['parameter_type'] == "value"
        assert Utility.is_exist(Slots, raise_error=False, name__iexact="bot")
        assert Utility.is_exist(Actions, raise_error=False, name__iexact=action)

    def test_add_http_action_config_missing_values(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        http_url = 'http://www.google.com'
        action = 'test_action_missing_values'
        # file deepcode ignore HardcodedNonCryptoSecret: Random string for testing
        auth_token = "bearer dhdshghfhzxfgadfhdhdhshdshsdfhsdhsdhnxngfgxngf"
        user = 'test_user'
        response = "json"
        request_method = 'GET'
        http_params_list: List[HttpActionParameters] = [
            HttpActionParameters(key="param1", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param2", value="value2", parameter_type="value")]
        http_action_config = HttpActionConfigRequest(
            auth_token=auth_token,
            action_name=action,
            response=response,
            http_url=http_url,
            request_method=request_method,
            params_list=http_params_list
        )
        http_dict = http_action_config.dict()
        http_dict['action_name'] = ''
        with pytest.raises(ValidationError, match="Action name cannot be empty"):
            processor.add_http_action_config(http_dict, user, bot)
        http_dict['action_name'] = action
        http_dict['http_url'] = None
        with pytest.raises(ValidationError, match="URL cannot be empty"):
            processor.add_http_action_config(http_dict, user, bot)
        http_dict['http_url'] = "www.google.com"
        with pytest.raises(ValidationError, match="URL is malformed"):
            processor.add_http_action_config(http_dict, user, bot)
        http_dict['http_url'] = http_url
        http_dict['request_method'] = "XYZ"
        with pytest.raises(ValidationError, match="Invalid HTTP method"):
            processor.add_http_action_config(http_dict, user, bot)
        http_dict['request_method'] = "GET"
        http_dict['params_list'][0]['key'] = None
        with pytest.raises(ValidationError, match="key in http action parameters cannot be empty"):
            processor.add_http_action_config(http_dict, user, bot)
        http_dict['params_list'][0]['value'] = None
        http_dict['params_list'][0]['key'] = "param1"
        with pytest.raises(ValidationError, match="Provide name of the slot as value"):
            processor.add_http_action_config(http_dict, user, bot)

    def test_list_http_action(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        actions = processor.list_http_actions(bot)
        assert len(actions) == 1

    def test_list_http_action_names(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        actions = processor.list_http_action_names(bot)
        assert len(actions) == 1

    def test_list_http_action_names_empty(self):
        processor = MongoProcessor()
        bot = 'test_bot1'
        actions = processor.list_http_action_names(bot)
        assert len(actions) == 0

    def test_add_http_action_config_existing(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        http_url = 'http://www.google.com'
        action = 'test_add_http_action_config_existing'
        user = 'test_user'
        response = "json"
        request_method = 'GET'
        params = [HttpActionParameters(key="key", value="value", parameter_type="slot")]

        HttpActionConfig(
            action_name=action,
            response=response,
            http_url=http_url,
            request_method=request_method,
            bot=bot,
            user=user
        ).save().to_mongo().to_dict()["_id"].__str__()

        http_action_config = HttpActionConfigRequest(
            action_name=action,
            response=response,
            http_url=http_url,
            request_method=request_method,
            params_list=params
        )
        try:
            processor.add_http_action_config(http_action_config.dict(), user, bot)
            assert False
        except AppException as ex:
            assert str(ex).__contains__("Action exists")

    def test_add_http_action_config_existing_name(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        http_url = 'http://www.google.com'
        action = 'test_action'
        user = 'test_user'
        response = "json"
        request_method = 'GET'
        params = [HttpActionParameters(key="key", value="value", parameter_type="slot")]

        http_action_config = HttpActionConfigRequest(
            action_name=action,
            response=response,
            http_url=http_url,
            request_method=request_method,
            params_list=params
        )
        with pytest.raises(AppException, match="Action exists"):
            processor.add_http_action_config(http_action_config.dict(), user, bot)

    def test_delete_http_action_config(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        http_url = 'http://www.google.com'
        action = 'test_delete_http_action_config'
        user = 'test_user'
        response = "json"
        request_method = 'GET'
        Actions(name=action, type=ActionType.http_action.value, bot=bot, user=user).save()
        HttpActionConfig(
            action_name=action,
            response=response,
            http_url=http_url,
            request_method=request_method,
            bot=bot,
            user=user
        ).save().to_mongo()
        processor.delete_action(action, user=user, bot=bot)
        try:
            HttpActionConfig.objects(action_name=action, bot=bot, user=user, status=True).get(
                action_name__iexact=action)
            assert False
        except DoesNotExist:
            assert True

    def test_delete_http_action_config_non_existing(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        action = 'test_delete_http_action_config_non_existing'
        user = 'test_user'
        http_url = 'http://www.google.com'
        response = "json"
        request_method = 'GET'
        HttpActionConfig(
            action_name=action,
            response=response,
            http_url=http_url,
            request_method=request_method,
            bot=bot,
            user=user
        ).save().to_mongo()
        try:
            processor.delete_action("test_delete_http_action_config_non_existing_non_existing", user=user, bot=bot)
            assert False
        except AppException as e:
            assert str(e).__contains__(
                'Action with name "test_delete_http_action_config_non_existing_non_existing" not found')

    def test_get_http_action_config(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        http_url = 'http://www.google.com'
        action = 'test_get_http_action_config1'
        user = 'test_user'
        response = "json"
        request_method = 'GET'
        HttpActionConfig(
            action_name=action,
            response=response,
            http_url=http_url,
            request_method=request_method,
            bot=bot,
            user=user
        ).save().to_mongo()

        actual_test_user1 = processor.get_http_action_config(bot=bot, action_name=action)
        assert actual_test_user1 is not None
        assert actual_test_user1['action_name'] == action
        assert actual_test_user1['response'] == response
        assert actual_test_user1['http_url'] == http_url
        assert actual_test_user1['request_method'] == request_method

        http_url1 = 'http://www.google.com'
        action1 = 'test_get_http_action_config'
        user1 = 'test_user1'
        response1 = ""
        request_method1 = 'POST'
        HttpActionConfig(
            action_name=action1,
            response=response1,
            http_url=http_url1,
            request_method=request_method1,
            bot=bot,
            user=user1
        ).save().to_mongo()

        actual_test_user2 = processor.get_http_action_config(bot=bot, action_name=action)
        assert actual_test_user2 is not None
        assert actual_test_user2['action_name'] == action
        assert actual_test_user2['response'] == response
        assert actual_test_user2['http_url'] == http_url
        assert actual_test_user2['request_method'] == request_method

    def test_get_http_action_config_non_existing(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        http_url = 'http://www.google.com'
        action = 'test_action'
        user = 'test_user'
        response = "json"
        request_method = 'GET'
        HttpActionConfig(
            action_name=action,
            response=response,
            http_url=http_url,
            request_method=request_method,
            bot=bot,
            user=user
        ).save().to_mongo()

        try:
            processor.get_http_action_config(bot=bot, action_name="action")
            assert False
        except AppException as e:
            assert str(e) == "No HTTP action found for bot test_bot and action action"

    def test_update_http_config(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        http_url = 'http://www.google.com'
        action = 'test_update_http_config'
        user = 'test_user'
        response = "json"
        request_method = 'GET'
        http_params_list: List[HttpActionParameters] = [
            HttpActionParameters(key="param1", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param2", value="value2", parameter_type="value")]
        http_action_config = HttpActionConfigRequest(
            action_name=action,
            response=response,
            http_url=http_url,
            request_method=request_method,
            params_list=http_params_list
        )
        http_config_id = processor.add_http_action_config(http_action_config.dict(), user, bot)
        assert http_config_id is not None
        http_url = 'http://www.alphabet.com'
        response = "string"
        request_method = 'POST'
        http_params_list = [
            HttpActionParameters(key="param3", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param4", value="value2", parameter_type="value"),
            HttpActionParameters(key="param5", parameter_type="sender_id"),
            HttpActionParameters(key="param6", parameter_type="user_message"),
            HttpActionParameters(key="param7", parameter_type="chat_log"),
            HttpActionParameters(key="param8", parameter_type="intent")]
        header = [
            HttpActionParameters(key="param1", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param2", value="value2", parameter_type="value"),
            HttpActionParameters(key="param3", parameter_type="sender_id"),
            HttpActionParameters(key="param4", parameter_type="user_message"),
            HttpActionParameters(key="param5", parameter_type="chat_log"),
            HttpActionParameters(key="param6", parameter_type="intent")]
        http_action_config = HttpActionConfigRequest(
            action_name=action,
            response=response,
            http_url=http_url,
            request_method=request_method,
            params_list=http_params_list,
            headers=header
        )
        processor.update_http_config(http_action_config, user, bot)

        actual_http_action = HttpActionConfig.objects(action_name=action, bot=bot, status=True).get(
            action_name__iexact=action)
        assert actual_http_action is not None
        assert actual_http_action['action_name'] == action
        assert actual_http_action['http_url'] == http_url
        assert actual_http_action['response'] == response
        assert actual_http_action['request_method'] == request_method
        assert actual_http_action['params_list'] is not None
        assert actual_http_action['params_list'][0]['key'] == "param3"
        assert actual_http_action['params_list'][0]['value'] == "param1"
        assert actual_http_action['params_list'][0]['parameter_type'] == "slot"
        assert actual_http_action['params_list'][1]['key'] == "param4"
        assert actual_http_action['params_list'][1]['value'] == "value2"
        assert actual_http_action['params_list'][1]['parameter_type'] == "value"
        assert actual_http_action['params_list'][2]['key'] == "param5"
        assert not actual_http_action['params_list'][2]['value']
        assert actual_http_action['params_list'][2]['parameter_type'] == "sender_id"
        assert actual_http_action['params_list'][3]['key'] == "param6"
        assert not actual_http_action['params_list'][3]['value']
        assert actual_http_action['params_list'][3]['parameter_type'] == "user_message"
        assert actual_http_action['params_list'][4]['key'] == "param7"
        assert not actual_http_action['params_list'][4]['value']
        assert actual_http_action['params_list'][4]['parameter_type'] == "chat_log"
        assert actual_http_action['params_list'][5]['key'] == "param8"
        assert not actual_http_action['params_list'][5]['value']
        assert actual_http_action['params_list'][5]['parameter_type'] == "intent"
        assert actual_http_action['headers'][0]['key'] == "param1"
        assert actual_http_action['headers'][0]['value'] == "param1"
        assert actual_http_action['headers'][0]['parameter_type'] == "slot"
        assert actual_http_action['headers'][1]['key'] == "param2"
        assert actual_http_action['headers'][1]['value'] == "value2"
        assert actual_http_action['headers'][1]['parameter_type'] == "value"
        assert actual_http_action['headers'][2]['key'] == "param3"
        assert not actual_http_action['headers'][2]['value']
        assert actual_http_action['headers'][2]['parameter_type'] == "sender_id"
        assert actual_http_action['headers'][3]['key'] == "param4"
        assert not actual_http_action['headers'][3]['value']
        assert actual_http_action['headers'][3]['parameter_type'] == "user_message"
        assert actual_http_action['headers'][4]['key'] == "param5"
        assert not actual_http_action['headers'][4]['value']
        assert actual_http_action['headers'][4]['parameter_type'] == "chat_log"
        assert actual_http_action['headers'][5]['key'] == "param6"
        assert not actual_http_action['headers'][5]['value']
        assert actual_http_action['headers'][5]['parameter_type'] == "intent"

    def test_update_http_config_invalid_action(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        http_url = 'http://www.google.com'
        action = 'test_update_http_config_invalid_action'
        user = 'test_user'
        response = "json"
        request_method = 'GET'
        http_params_list: List[HttpActionParameters] = [
            HttpActionParameters(key="param1", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param2", value="value2", parameter_type="value")]
        http_action_config = HttpActionConfigRequest(
            action_name=action,
            response=response,
            http_url=http_url,
            request_method=request_method,
            params_list=http_params_list
        )
        http_config_id = processor.add_http_action_config(http_action_config.dict(), user, bot)
        assert http_config_id is not None
        bot = 'test_bot'
        http_url = 'http://www.alphabet.com'
        action = 'test_update_http_config_invalid'
        user = 'test_user'
        response = "string"
        request_method = 'POST'
        http_params_list = [
            HttpActionParameters(key="param3", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param4", value="value2", parameter_type="value")]
        http_action_config = HttpActionConfigRequest(
            action_name=action,
            response=response,
            http_url=http_url,
            request_method=request_method,
            params_list=http_params_list
        )
        try:
            processor.update_http_config(http_action_config, user, bot)
        except AppException as e:
            assert str(e) == 'No HTTP action found for bot test_bot and action test_update_http_config_invalid'

    def test_add_complex_story_without_http_action(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
        ]
        story_dict = {'name': "story without action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        processor.add_complex_story(story_dict, "test_without_http", "testUser")
        story = Stories.objects(block_name="story without action", bot="test_without_http").get()
        assert len(story.events) == 5
        actions = processor.list_actions("test_without_http")
        assert actions == {
            'actions': [], 'http_action': [], 'slot_set_action': [], 'utterances': [], 'jira_action': [],
            'email_action': [], 'form_validation_action': [], 'google_search_action': [], 'zendesk_action': [],
            'pipedrive_leads_action': []
        }

    def test_add_complex_story_with_action(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "action_check", "type": "ACTION"},
            {"name": "utter_greet", "type": "BOT"},
        ]
        story_dict = {'name': "story with action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        processor.add_complex_story(story_dict, "test_with_action", "testUser")
        story = Stories.objects(block_name="story with action", bot="test_with_action").get()
        assert len(story.events) == 6
        actions = processor.list_actions("test_with_action")
        assert actions == {
            'actions': ['action_check'],
            'http_action': [], 'jira_action': [],
            'slot_set_action': [], 'zendesk_action': [], 'pipedrive_leads_action': [],
            'utterances': [], 'email_action': [], 'form_validation_action': [], 'google_search_action': []}

    def test_add_complex_story(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"}
        ]
        story_dict = {'name': "story with action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        processor.add_complex_story(story_dict, "tests", "testUser")
        story = Stories.objects(block_name="story with action", bot="tests").get()
        assert len(story.events) == 6
        actions = processor.list_actions("tests")
        assert actions == {'actions': [], 'zendesk_action': [], 'pipedrive_leads_action': [],
                           'http_action': [], 'google_search_action': [], 'jira_action': [],
                           'slot_set_action': [], 'email_action': [], 'form_validation_action': [],
                           'utterances': ['utter_greet',
                                          'utter_cheer_up',
                                          'utter_did_that_help',
                                          'utter_happy',
                                          'utter_goodbye',
                                          'utter_iamabot',
                                          'utter_feedback',
                                          'utter_good_feedback',
                                          'utter_bad_feedback',
                                          'utter_default',
                                          'utter_please_rephrase']}

    def test_add_duplicate_complex_story(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"}
        ]
        with pytest.raises(Exception):
            story_dict = {'name': "story with action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
            processor.add_complex_story(story_dict, "tests", "testUser")

    def test_add_duplicate_case_insensitive_complex_story(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"}
        ]
        with pytest.raises(Exception):
            story_dict = {'name': "Story with action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
            processor.add_complex_story(story_dict, "tests", "testUser")

    def test_add_none_complex_story_name(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greeting", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
        ]
        with pytest.raises(AppException):
            story_dict = {'name': None, 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
            processor.add_complex_story(story_dict, "tests", "testUser")

    def test_add_empty_complex_story_name(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greeting", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"}
        ]
        with pytest.raises(AppException):
            story_dict = {'name': "", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
            processor.add_complex_story(story_dict, "tests", "testUser")

    def test_add_blank_complex_story_name(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greeting", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"}
        ]
        with pytest.raises(AppException):
            story_dict = {'name': " ", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
            processor.add_complex_story(story_dict, "tests", "testUser")

    def test_add_empty_complex_story_event(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            story_dict = {'name': "empty path", 'steps': [], 'type': 'STORY', 'template_type': 'CUSTOM'}
            processor.add_complex_story(story_dict, "tests", "testUser")

    def test_add_duplicate_complex_story_using_events(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"}
        ]
        with pytest.raises(Exception):
            story_dict = {'name': "story duplicate using events", 'steps': steps, 'type': 'STORY',
                          'template_type': 'CUSTOM'}
            processor.add_complex_story(story_dict, "tests", "testUser")

    def test_add_complex_story_with_invalid_event(self):
        processor = MongoProcessor()
        steps = [
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"}
        ]
        rule_dict = {'name': "rule with invalid events", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        with pytest.raises(ValidationError, match="First event should be an user"):
            processor.add_complex_story(rule_dict, "tests", "testUser")

        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
        ]
        rule_dict = {'name': "rule with invalid events", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        with pytest.raises(ValidationError, match="user event should be followed by action"):
            processor.add_complex_story(rule_dict, "tests", "testUser")

        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "mood_sad", "type": "INTENT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"}
        ]
        rule_dict = {'name': "rule with invalid events", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        with pytest.raises(ValidationError, match="Found 2 consecutive user events"):
            processor.add_complex_story(rule_dict, "tests", "testUser")

    def test_update_complex_story(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"}
        ]
        story_dict = {'name': "story with action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        processor.update_complex_story(story_dict, "tests", "testUser")
        story = Stories.objects(block_name="story with action", bot="tests").get()
        assert story.events[1].name == "utter_nonsense"

    def test_update_complex_story_same_events(self):
        def test_update_complex_story(self):
            processor = MongoProcessor()
            steps = [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_nonsense", "type": "BOT"},
                {"name": "utter_cheer_up", "type": "BOT"},
                {"name": "mood_great", "type": "INTENT"},
                {"name": "utter_greet", "type": "BOT"},
                {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"}
            ]
            story_dict = {'name': "story with same events", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
            with pytest.raises(AppException, match="FLow already exists!"):
                processor.update_complex_story(story_dict, "tests", "testUser")

    def test_case_insensitive_update_complex_story(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"},
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
        ]
        story_dict = {'name': "STory with action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        processor.update_complex_story(story_dict, "tests", "testUser")
        story = Stories.objects(block_name="story with action", bot="tests").get()
        assert story.events[1].name == "utter_nonsense"

    def test_update_non_existing_complex_story(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"},
        ]
        with pytest.raises(Exception):
            story_dict = {'name': "non existing story", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
            processor.update_complex_story(story_dict, "tests", "testUser")

    def test_update_complex_story_with_invalid_event(self):
        processor = MongoProcessor()
        steps = [
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"}
        ]
        rule_dict = {'name': "story with action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        with pytest.raises(ValidationError, match="First event should be an user"):
            processor.update_complex_story(rule_dict, "tests", "testUser")

        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
        ]
        rule_dict = {'name': "story with action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        with pytest.raises(ValidationError, match="user event should be followed by action"):
            processor.update_complex_story(rule_dict, "tests", "testUser")

        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "mood_sad", "type": "INTENT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"}
        ]
        rule_dict = {'name': "story with action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        with pytest.raises(ValidationError, match="Found 2 consecutive user events"):
            processor.update_complex_story(rule_dict, "tests", "testUser")

    def test_update_complex_story_name(self):
        processor = MongoProcessor()
        events = [
            {"name": "greeting", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"}
        ]
        with pytest.raises(AppException):
            story_dict = {'name': None, 'steps': events, 'type': 'STORY', 'template_type': 'CUSTOM'}
            processor.update_complex_story(story_dict, "tests", "testUser")

    def test_update_empty_complex_story_name(self):
        processor = MongoProcessor()
        events = [
            {"name": "greeting", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"}
        ]
        with pytest.raises(AppException):
            story_dict = {'name': "", 'steps': events, 'type': 'STORY', 'template_type': 'CUSTOM'}
            processor.update_complex_story(story_dict, "tests", "testUser")

    def test_update_blank_complex_story_name(self):
        processor = MongoProcessor()
        events = [
            {"name": "greeting", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"}
        ]
        with pytest.raises(AppException):
            story_dict = {'name': " ", 'steps': events, 'type': 'STORY', 'template_type': 'CUSTOM'}
            processor.update_complex_story(story_dict, "tests", "testUser")

    def test_update_empty_complex_story_event(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            story_dict = {'name': "empty path", 'steps': [], 'type': 'STORY', 'template_type': 'CUSTOM'}
            processor.update_complex_story(story_dict, "tests", "testUser")

    def test_list_actions(self):
        processor = MongoProcessor()
        processor.add_action("reset_slot", "test_upload_and_save", "test_user")
        actions = processor.list_actions("test_upload_and_save")
        assert actions == {
            'actions': ['reset_slot'], 'google_search_action': [], 'jira_action': [], 'pipedrive_leads_action': [],
            'http_action': ['action_performanceuser1000@digite.com'], 'zendesk_action': [], 'slot_set_action': [],
            'email_action': [], 'form_validation_action': [], 'utterances': ['utter_offer_help', 'utter_default',
                                                                             'utter_please_rephrase']}

    def test_delete_non_existing_complex_story(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            processor.delete_complex_story("non existing", "STORY", "tests", "testUser")

    def test_delete_empty_complex_story(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            processor.delete_complex_story(None, "STORY", "tests", "testUser")

    def test_case_insensitive_delete_complex_story(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"},
        ]
        story_dict = {"name": "story2", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        processor.add_complex_story(story_dict, "tests", "testUser")
        processor.delete_complex_story("STory2", "STORY", "tests", "testUser")

    def test_delete_complex_story(self):
        processor = MongoProcessor()
        processor.delete_complex_story("story with action", "STORY", "tests", "testUser")

    def test_get_utterance_from_intent_non_existing(self):
        processor = MongoProcessor()
        user = "test_user"
        story = "new_story"
        action = story
        bot = "bot"
        intent = "greet_you"
        story_event = [StoryEvents(name=intent, type="user"),
                       StoryEvents(name="bot", type="slot", value=bot),
                       StoryEvents(name="http_action_config", type="slot", value=action),
                       StoryEvents(name="kairon_http_action", type="action")]
        cust = ResponseCustom(custom={"key": "value"})
        text = ResponseText(text="hello")

        Responses(
            name=intent,
            text=text,
            custom=cust,
            bot=bot,
            user=user
        ).save(validate=False).to_mongo()
        Stories(
            block_name=story,
            bot=bot,
            user=user,
            events=story_event
        ).save(validate=False).to_mongo()
        HttpActionConfig(
            action_name=action,
            response="",
            http_url="http://www.google.com",
            request_method="GET",
            bot=bot,
            user=user
        ).save().to_mongo()
        actual_action = processor.get_utterance_from_intent(intent="intent", bot=bot)
        assert actual_action[0] is None
        assert actual_action[1] is None

    def test_add_and_delete_non_integration_intent_by_integration_user(self):
        processor = MongoProcessor()
        processor.add_intent("TestingDelGreeting", "tests", "testUser", is_integration=False)
        with pytest.raises(Exception):
            processor.delete_intent("TestingDelGreeting", "tests", "testUser1", is_integration=True,
                                    delete_dependencies=False)

    def test_add_and_delete_integration_intent_by_same_integration_user(self):
        processor = MongoProcessor()
        processor.add_intent("TestingDelGreeting1", "tests", "testUser", is_integration=True)
        processor.delete_intent("TestingDelGreeting1", "tests", "testUser", is_integration=True,
                                delete_dependencies=False)

    def test_add_and_delete_integration_intent_by_different_integration_user(self):
        processor = MongoProcessor()
        processor.add_intent("TestingDelGreeting2", "tests", "testUser", is_integration=True)
        processor.delete_intent("TestingDelGreeting2", "tests", "testUser2", is_integration=True,
                                delete_dependencies=False)

    def test_add_rule(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
        ]
        rule_dict = {'name': "rule with action", 'steps': steps, 'type': 'RULE', 'template_type': 'RULE'}
        processor.add_complex_story(rule_dict, "tests", "testUser")
        story = Rules.objects(block_name="rule with action", bot="tests").get()
        assert len(story.events) == 4
        assert story.events[0].name == "..."
        assert story.events[0].type == "action"
        actions = processor.list_actions("tests")
        assert actions == {
            'actions': [], 'zendesk_action': [],
            'http_action': [], 'google_search_action': [], 'pipedrive_leads_action': [],
            'slot_set_action': [], 'email_action': [], 'form_validation_action': [], 'jira_action': [],
            'utterances': ['utter_greet',
                           'utter_cheer_up',
                           'utter_did_that_help',
                           'utter_happy',
                           'utter_goodbye',
                           'utter_iamabot',
                           'utter_feedback',
                           'utter_good_feedback',
                           'utter_bad_feedback',
                           'utter_default',
                           'utter_please_rephrase']}

    def test_add_duplicate_rule(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
        ]
        with pytest.raises(Exception):
            rule_dict = {'name': "rule with action", 'steps': steps, 'type': 'RULE', 'template_type': 'RULE'}
            processor.add_complex_story(rule_dict, "tests", "testUser")

    def test_add_rule_invalid_type(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
        ]
        with pytest.raises(Exception):
            rule_dict = {'name': "rule with action", 'steps': steps, 'type': 'TEST', 'template_type': 'CUSTOM'}
            processor.add_complex_story(rule_dict, "tests", "testUser")

    def test_add_duplicate_case_insensitive_rule(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
        ]
        with pytest.raises(Exception):
            rule_dict = {'name': "RUle with action", 'steps': steps, 'type': 'RULE', 'template_type': 'RULE'}
            processor.add_complex_story(rule_dict, "tests", "testUser")

    def test_add_none_rule(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greeting", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
        ]
        with pytest.raises(AppException):
            rule_dict = {'name': None, 'steps': steps, 'type': 'RULE', 'template_type': 'RULE'}
            processor.add_complex_story(rule_dict, "tests", "testUser")

    def test_add_empty_rule(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greeting", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
        ]
        with pytest.raises(AppException):
            rule_dict = {'name': "", 'steps': steps, 'type': 'RULE', 'template_type': 'RULE'}
            processor.add_complex_story(rule_dict, "tests", "testUser")

    def test_add_blank_rule_name(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greeting", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
        ]
        with pytest.raises(AppException):
            rule_dict = {'name': " ", 'steps': steps, 'type': 'rule', 'template_type': 'RULE'}
            processor.add_complex_story(rule_dict, "tests", "testUser")

    def test_add_empty_rule_event(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            rule_dict = {'name': "empty path", 'steps': [], 'type': 'RULE', 'template_type': 'RULE'}
            processor.add_complex_story(rule_dict, "tests", "testUser")

    def test_add_rule_with_multiple_intents(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"}
        ]
        rule_dict = {'name': "rule with multiple intents", 'steps': steps, 'type': 'RULE', 'template_type': 'RULE'}
        with pytest.raises(ValidationError,
                           match="Found rules 'rule with multiple intents' that contain more than user event.\nPlease use stories for this case"):
            processor.add_complex_story(rule_dict, "tests", "testUser")

    def test_add_rule_with_invalid_event(self):
        processor = MongoProcessor()
        steps = [
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"}
        ]
        rule_dict = {'name': "rule with invalid events", 'steps': steps, 'type': 'RULE', 'template_type': 'RULE'}
        with pytest.raises(ValidationError, match="First event should be an user or conversation_start action"):
            processor.add_complex_story(rule_dict, "tests", "testUser")

        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
        ]
        rule_dict = {'name': "rule with invalid events", 'steps': steps, 'type': 'RULE', 'template_type': 'RULE'}
        with pytest.raises(ValidationError, match="user event should be followed by action"):
            processor.add_complex_story(rule_dict, "tests", "testUser")

        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "mood_sad", "type": "INTENT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"}
        ]
        rule_dict = {'name': "rule with invalid events", 'steps': steps, 'type': 'RULE', 'template_type': 'RULE'}
        with pytest.raises(ValidationError, match="Found 2 consecutive user events"):
            processor.add_complex_story(rule_dict, "tests", "testUser")

    def test_update_rule(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
        ]
        rule_dict = {'name': "rule with action", 'steps': steps, 'type': 'RULE', 'template_type': 'RULE'}
        processor.update_complex_story(rule_dict, "tests", "testUser")
        rule = Rules.objects(block_name="rule with action", bot="tests").get()
        assert rule.events[2].name == "utter_nonsense"
        assert rule.events[0].name == "..."
        assert rule.events[0].type == "action"

    def test_case_insensitive_update_rule(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "utter_greet", "type": "BOT"},
        ]
        rule_dict = {'name': "RUle with action", 'steps': steps, 'type': 'RULE', 'template_type': 'RULE'}
        processor.update_complex_story(rule_dict, "tests", "testUser")
        rule = Rules.objects(block_name="rule with action", bot="tests").get()
        assert rule.events[4].name == "utter_greet"

    def test_update_non_existing_rule(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
        ]
        with pytest.raises(Exception):
            rule_dict = {'name': "non existing story", 'steps': steps, 'type': 'RULE', 'template_type': 'RULE'}
            processor.update_complex_story(rule_dict, "tests", "testUser")

    def test_update_rule_name(self):
        processor = MongoProcessor()
        events = [
            {"name": "greeting", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
        ]
        with pytest.raises(AppException):
            rule_dict = {'name': None, 'steps': events, 'type': 'RULE', 'template_type': 'RULE'}
            processor.update_complex_story(rule_dict, "tests", "testUser")

    def test_fetch_stories_with_rules(self):
        processor = MongoProcessor()
        data = list(processor.get_stories("tests"))
        assert all(item['type'] in ['STORY', 'RULE'] for item in data)
        assert len(data) == 9

    def test_update_empty_rule_name(self):
        processor = MongoProcessor()
        events = [
            {"name": "greeting", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
        ]
        with pytest.raises(AppException):
            rule_dict = {'name': "", 'steps': events, 'type': 'RULE', 'template_type': 'RULE'}
            processor.update_complex_story(rule_dict, "tests", "testUser")

    def test_update_blank_rule_name(self):
        processor = MongoProcessor()
        events = [
            {"name": "greeting", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
        ]
        with pytest.raises(AppException):
            rule_dict = {'name': " ", 'steps': events, 'type': 'RULE', 'template_type': 'RULE'}
            processor.update_complex_story(rule_dict, "tests", "testUser")

    def test_update_empty_rule_event(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            rule_dict = {'name': "empty path", 'steps': [], 'type': 'RULE', 'template_type': 'RULE'}
            processor.update_complex_story(rule_dict, "tests", "testUser")

    def test_update_rule_invalid_type(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
        ]
        with pytest.raises(AppException):
            rule_dict = {'name': "rule with action", 'steps': steps, 'type': 'TEST', 'template_type': 'RULE'}
            processor.update_complex_story(rule_dict, "tests", "testUser")

    def test_delete_non_existing_rule(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            processor.delete_complex_story("non existing", "RULE", "tests", "testUser")

    def test_update_rules_with_multiple_intents(self):
        processor = MongoProcessor()
        events = [
            {"name": "greeting", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"}
        ]
        with pytest.raises(ValidationError,
                           match="Found rules 'rule with action' that contain more than user event.\nPlease use stories for this case"):
            rule_dict = {'name': "rule with action", 'steps': events, 'type': 'RULE', 'template_type': 'RULE'}
            processor.update_complex_story(rule_dict, "tests", "testUser")

    def test_update_rules_with_invalid_type(self):
        processor = MongoProcessor()
        events = [
            {"name": "greeting", "type": "USER"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"}
        ]
        with pytest.raises(AppException, match="Invalid event type!"):
            rule_dict = {'name': "rule with action", 'steps': events, 'type': 'RULE', 'template_type': 'RULE'}
            processor.update_complex_story(rule_dict, "tests", "testUser")

    def test_delete_empty_rule(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            processor.delete_complex_story(None, "RULE", "tests", "testUser")

    def test_case_insensitive_delete_rule(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"},
        ]
        rule_dict = {"name": "rule2", 'steps': steps, 'type': 'RULE'}
        processor.add_complex_story(rule_dict, "tests", "testUser")
        processor.delete_complex_story("RUle2", "RULE", "tests", "testUser")

    def test_update_rule_with_invalid_event(self):
        processor = MongoProcessor()
        steps = [
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"}
        ]
        rule_dict = {'name': "rule with invalid events", 'steps': steps, 'type': 'RULE'}
        with pytest.raises(ValidationError, match="First event should be an user"):
            processor.add_complex_story(rule_dict, "tests", "testUser")

        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
        ]
        rule_dict = {'name': "rule with invalid events", 'steps': steps, 'type': 'RULE'}
        with pytest.raises(ValidationError, match="user event should be followed by action"):
            processor.add_complex_story(rule_dict, "tests", "testUser")

        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "mood_sad", "type": "INTENT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"}
        ]
        rule_dict = {'name': "rule with invalid events", 'steps': steps, 'type': 'RULE'}
        with pytest.raises(ValidationError, match="Found 2 consecutive user events"):
            processor.add_complex_story(rule_dict, "tests", "testUser")

    def test_delete_rule(self):
        processor = MongoProcessor()
        processor.delete_complex_story("rule with action", "RULE", "tests", "testUser")

    def test_delete_rule_invalid_type(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.delete_complex_story("rule with action", "TEST", "tests", "testUser")

    def test_add_email_action(self):
        processor = MongoProcessor()
        email_config = {"action_name": "email_config",
                        "smtp_url": "test.test.com",
                        "smtp_port": 25,
                        "smtp_userid": None,
                        "smtp_password": "test",
                        "from_email": "test@demo.com",
                        "to_email": ["test@test.com","test1@test.com"],
                        "subject": "Test Subject",
                        "response": "Test Response",
                        "tls": False
                        }
        with patch("kairon.shared.utils.SMTP", autospec=True) as mock_smtp:
            assert processor.add_email_action(email_config, "TEST", "tests") is not None

    def test_add_email_action_with_story(self):
        processor = MongoProcessor()
        bot = 'TEST'
        user = 'tests'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "email_config", "type": "EMAIL_ACTION"},
        ]
        story_dict = {'name': "story with email action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        assert processor.add_complex_story(story_dict, bot, user)
        story = Stories.objects(block_name="story with email action", bot=bot,
                                events__name='email_config', status=True).get()
        assert story.events[1].type == 'action'
        stories = list(processor.get_stories(bot))
        story_with_form = [s for s in stories if s['name'] == "story with email action"]
        assert story_with_form[0]['steps'] == [
            {'name': 'greet', 'type': 'INTENT'},
            {'name': 'email_config', 'type': 'EMAIL_ACTION'},
        ]
        processor.delete_complex_story('story with email action', 'STORY', bot, user)

    def test_add_email_action_validation_error(self):
        processor = MongoProcessor()
        email_config = {"action_name": "email_config1",
                        "smtp_url": "test.test.com",
                        "smtp_port": 25,
                        "smtp_userid": None,
                        "smtp_password": "test",
                        "from_email": "test@demo.com",
                        "to_email": "test@test.com",
                        "subject": "Test Subject",
                        "response": "Test Response",
                        "tls": False
                        }
        with patch("kairon.shared.utils.SMTP", autospec=True) as mock_smtp:
            mock_smtp.return_value = Exception()
            with pytest.raises(ValidationError, match="Invalid SMTP url"):
                processor.add_email_action(email_config, "TEST", "tests")

        with patch("kairon.shared.utils.SMTP", autospec=True) as mock_smtp:
            temp = email_config['action_name']
            email_config['action_name'] = ""
            with pytest.raises(ValidationError, match="Action name cannot be empty"):
                processor.add_email_action(email_config, "TEST", "tests")
            email_config['action_name'] = temp

            temp = email_config['smtp_url']
            email_config['smtp_url'] = ""
            with pytest.raises(ValidationError, match="URL cannot be empty"):
                processor.add_email_action(email_config, "TEST", "tests")
            email_config['smtp_url'] = temp

            temp = email_config['from_email']
            email_config['from_email'] = "test@test"
            with pytest.raises(ValidationError, match="Invalid From or To email address"):
                processor.add_email_action(email_config, "TEST", "tests")
            email_config['from_email'] = temp

            temp = email_config['to_email']
            email_config['to_email'] = "test@test"
            with pytest.raises(ValidationError, match="Invalid From or To email address"):
                processor.add_email_action(email_config, "TEST", "tests")
            email_config['to_email'] = temp

    def test_add_email_action_duplicate(self):
        processor = MongoProcessor()
        email_config = {"action_name": "email_config",
                        "smtp_url": "test.test.com",
                        "smtp_port": 25,
                        "smtp_userid": None,
                        "smtp_password": "test",
                        "from_email": "test@demo.com",
                        "to_email": ["test@test.com"],
                        "subject": "Test Subject",
                        "response": "Test Response",
                        "tls": False
                        }
        with patch("kairon.shared.utils.SMTP", autospec=True) as mock_smtp:
            with pytest.raises(AppException, match="Action exists!"):
                processor.add_email_action(email_config, "TEST", "tests")

    def test_add_email_action_existing_name(self):
        processor = MongoProcessor()
        email_config = {"action_name": "test_action",
                        "smtp_url": "test.test.com",
                        "smtp_port": 25,
                        "smtp_userid": None,
                        "smtp_password": "test",
                        "from_email": "test@demo.com",
                        "to_email": ["test@test.com"],
                        "subject": "Test Subject",
                        "response": "Test Response",
                        "tls": False
                        }
        with patch("kairon.shared.utils.SMTP", autospec=True) as mock_smtp:
            with pytest.raises(AppException, match="Action exists!"):
                processor.add_email_action(email_config, "test_bot", "tests")

    def test_edit_email_action(self):
        processor = MongoProcessor()
        email_config = {"action_name": "email_config",
                        "smtp_url": "test.test.com",
                        "smtp_port": 25,
                        "smtp_userid": None,
                        "smtp_password": "test",
                        "from_email": "test@demo.com",
                        "to_email": ["test@test.com","test1@test.com"],
                        "subject": "Test Subject",
                        "response": "Test Response",
                        "tls": False
                        }
        with patch("kairon.shared.utils.SMTP", autospec=True) as mock_smtp:
            assert processor.edit_email_action(email_config, "TEST", "tests") is None

    def test_edit_email_action_validation_error(self):
        processor = MongoProcessor()
        email_config = {"action_name": "email_config",
                        "smtp_url": "test.test.com",
                        "smtp_port": 25,
                        "smtp_userid": None,
                        "smtp_password": "test",
                        "from_email": "test@demo.com",
                        "to_email": "test@test.com",
                        "subject": "Test Subject",
                        "response": "Test Response",
                        "tls": False
                        }
        with patch("kairon.shared.utils.SMTP", autospec=True) as mock_smtp:
            mock_smtp.return_value = Exception()
            with pytest.raises(ValidationError, match="Invalid SMTP url"):
                processor.edit_email_action(email_config, "TEST", "tests")

        with patch("kairon.shared.utils.SMTP", autospec=True) as mock_smtp:
            temp = email_config['action_name']
            email_config['action_name'] = ""
            with pytest.raises(AppException, match='Action with name "" not found'):
                processor.edit_email_action(email_config, "TEST", "tests")
            email_config['action_name'] = temp

            temp = email_config['smtp_url']
            email_config['smtp_url'] = ""
            with pytest.raises(ValidationError, match="URL cannot be empty"):
                processor.edit_email_action(email_config, "TEST", "tests")
            email_config['smtp_url'] = temp

            temp = email_config['from_email']
            email_config['from_email'] = "test@test"
            with pytest.raises(ValidationError, match="Invalid From or To email address"):
                processor.edit_email_action(email_config, "TEST", "tests")
            email_config['from_email'] = temp

            temp = email_config['to_email']
            email_config['to_email'] = "test@test"
            with pytest.raises(ValidationError, match="Invalid From or To email address"):
                processor.edit_email_action(email_config, "TEST", "tests")
            email_config['to_email'] = temp

    def test_edit_email_action_does_not_exist(self):
        processor = MongoProcessor()
        email_config = {"action_name": "email_config1",
                        "smtp_url": "test.test.com",
                        "smtp_port": 25,
                        "smtp_userid": None,
                        "smtp_password": "test",
                        "from_email": "test@demo.com",
                        "to_email": "test@test.com",
                        "subject": "Test Subject",
                        "response": "Test Response",
                        "tls": False
                        }
        with patch("kairon.shared.utils.SMTP", autospec=True) as mock_smtp:
            with pytest.raises(AppException, match='Action with name "email_config1" not found'):
                processor.edit_email_action(email_config, "TEST", "tests")

    def test_list_email_actions(self):
        processor = MongoProcessor()
        assert len(list(processor.list_email_action("TEST"))) == 1

    def test_add_google_search_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action = {
            'name': 'google_custom_search',
            'api_key': '12345678',
            'search_engine_id': 'asdfg:123456',
            'failure_response': 'I have failed to process your request',
        }
        assert processor.add_google_search_action(action, bot, user)
        assert Actions.objects(name='google_custom_search', status=True, bot=bot).get()
        assert GoogleSearchAction.objects(name='google_custom_search', status=True, bot=bot).get()

    def test_add_google_search_action_with_story(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test'
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "google_custom_search", "type": "GOOGLE_SEARCH_ACTION"},
        ]
        story_dict = {'name': "story with google action", 'steps': steps, 'type': 'STORY', 'template_type': 'CUSTOM'}
        assert processor.add_complex_story(story_dict, bot, user)
        story = Stories.objects(block_name="story with google action", bot=bot,
                                events__name='google_custom_search', status=True).get()
        assert story.events[1].type == 'action'
        stories = list(processor.get_stories(bot))
        story_with_form = [s for s in stories if s['name'] == 'story with google action']
        assert story_with_form[0]['steps'] == [
            {'name': 'greet', 'type': 'INTENT'},
            {'name': 'google_custom_search', 'type': 'GOOGLE_SEARCH_ACTION'},
        ]
        processor.delete_complex_story('story with google action', 'STORY', bot, user)

    def test_add_google_search_action_duplicate(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action = {
            'name': 'google_custom_search',
            'api_key': '12345678',
            'search_engine_id': 'asdfg:123456',
            'failure_response': 'I have failed to process your request',
        }
        with pytest.raises(AppException, match='Action with name "google_custom_search" exists'):
            processor.add_google_search_action(action, bot, user)
        assert Actions.objects(name='google_custom_search', status=True, bot=bot).get()
        assert GoogleSearchAction.objects(name='google_custom_search', status=True, bot=bot).get()

    def test_add_google_search_action_existing_name(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        action = {
            'name': 'test_action',
            'api_key': '12345678',
            'search_engine_id': 'asdfg:123456',
            'failure_response': 'I have failed to process your request',
        }
        with pytest.raises(AppException, match='Action with name "test_action" exists'):
            processor.add_google_search_action(action, bot, user)
        assert Actions.objects(name='test_action', status=True, bot=bot).get()

    def test_list_google_search_action_masked(self):
        processor = MongoProcessor()
        bot = 'test'
        actions = list(processor.list_google_search_actions(bot))
        assert actions[0]['name'] == 'google_custom_search'
        assert actions[0]['api_key'] == '12345***'
        assert actions[0]['search_engine_id'] == 'asdfg:123456'
        assert actions[0]['failure_response'] == 'I have failed to process your request'
        assert actions[0]['num_results'] == 1

    def test_edit_google_search_action_not_exists(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action = {
            'name': 'custom_search',
            'api_key': '12345678',
            'search_engine_id': 'asdfg:123456',
            'failure_response': 'I have failed to process your request',
        }
        with pytest.raises(AppException, match='Google search action with name "custom_search" not found'):
            processor.edit_google_search_action(action, bot, user)
        assert Actions.objects(name='google_custom_search', status=True, bot=bot).get()
        assert GoogleSearchAction.objects(name='google_custom_search', status=True, bot=bot).get()

    def test_edit_google_search_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        action = {
            'name': 'google_custom_search',
            'api_key': '1234567889',
            'search_engine_id': 'asdfg:12345689',
            'failure_response': 'Failed to perform search',
        }
        assert not processor.edit_google_search_action(action, bot, user)
        assert Actions.objects(name='google_custom_search', status=True, bot=bot).get()
        assert GoogleSearchAction.objects(name='google_custom_search', status=True, bot=bot).get()

    def test_list_google_search_action(self):
        processor = MongoProcessor()
        bot = 'test'
        actions = list(processor.list_google_search_actions(bot, False))
        assert actions[0]['name'] == 'google_custom_search'
        assert actions[0]['api_key'] == '1234567889'
        assert actions[0]['search_engine_id'] == 'asdfg:12345689'
        assert actions[0]['failure_response'] == 'Failed to perform search'
        assert actions[0]['num_results'] == 1

    def test_delete_google_search_action(self):
        processor = MongoProcessor()
        bot = 'test'
        user = 'test_user'
        processor.delete_action('google_custom_search', bot, user)
        with pytest.raises(DoesNotExist):
            Actions.objects(name='google_custom_search', status=True, bot=bot).get()
        with pytest.raises(DoesNotExist):
            GoogleSearchAction.objects(name='google_custom_search', status=True, bot=bot).get()


class TestTrainingDataProcessor:

    @pytest.fixture(autouse=True, scope='class')
    def init_connection(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        connect(**Utility.mongoengine_connection())

    def test_set_status_new_status(self):
        TrainingDataGenerationProcessor.set_status(
            bot="tests2",
            user="testUser2",
            document_path='document/doc.pdf',
            status=''
        )
        status = TrainingDataGenerator.objects(
            bot="tests2",
            user="testUser2").get()
        assert status['bot'] == 'tests2'
        assert status['user'] == 'testUser2'
        assert status['status'] == EVENT_STATUS.INITIATED.value
        assert status['document_path'] == 'document/doc.pdf'
        assert status['start_timestamp'] is not None
        assert status['last_update_timestamp'] is not None

    def test_fetch_latest_workload(self):
        status = TrainingDataGenerationProcessor.fetch_latest_workload(
            bot="tests2",
            user="testUser2"
        )
        assert status['bot'] == 'tests2'
        assert status['user'] == 'testUser2'
        assert status['status'] == EVENT_STATUS.INITIATED.value
        assert status['document_path'] == 'document/doc.pdf'
        assert status['start_timestamp'] is not None
        assert status['last_update_timestamp'] is not None

    def test_validate_history_id_no_response_generated(self):
        status = TrainingDataGenerator.objects(
            bot="tests2",
            user="testUser2").get()
        with pytest.raises(AppException):
            TrainingDataGenerationProcessor.validate_history_id(status["id"])

    def test_is_in_progress_true(self):
        status = TrainingDataGenerationProcessor.is_in_progress(
            bot="tests2",
            raise_exception=False
        )
        assert status

    def test_is_in_progress_exception(self):
        with pytest.raises(AppException):
            TrainingDataGenerationProcessor.is_in_progress(
                bot="tests2",
            )

    def test_set_status_update_status(self):
        training_examples1 = [TrainingExamplesTrainingDataGenerator(training_example="example1"),
                              TrainingExamplesTrainingDataGenerator(training_example="example2")]
        training_examples2 = [TrainingExamplesTrainingDataGenerator(training_example="example3"),
                              TrainingExamplesTrainingDataGenerator(training_example="example4")]
        TrainingDataGenerationProcessor.set_status(
            bot="tests2",
            user="testUser2",
            status=EVENT_STATUS.COMPLETED.value,
            response=[TrainingDataGeneratorResponse(
                intent="intent1",
                training_examples=training_examples1,
                response="this is response1"
            ),
                TrainingDataGeneratorResponse(
                    intent="intent2",
                    training_examples=training_examples2,
                    response="this is response2"
                )
            ]
        )
        status = TrainingDataGenerator.objects(
            bot="tests2",
            user="testUser2").get()
        assert status['bot'] == 'tests2'
        assert status['user'] == 'testUser2'
        assert status['status'] == EVENT_STATUS.COMPLETED.value
        assert status['document_path'] == 'document/doc.pdf'
        assert status['start_timestamp'] is not None
        assert status['last_update_timestamp'] is not None
        assert status['end_timestamp'] is not None
        assert status['response'] is not None

    def test_validate_history_id(self):
        status = TrainingDataGenerator.objects(
            bot="tests2",
            user="testUser2").get()
        assert not TrainingDataGenerationProcessor.validate_history_id(status["id"])

    def test_validate_history_id_invalid(self):
        with pytest.raises(AppException):
            TrainingDataGenerationProcessor.validate_history_id("6076f751452a66f16b7f1276")

    def test_update_is_persisted_flag(self):
        training_data = TrainingDataGenerator.objects(
            bot="tests2",
            user="testUser2").get()
        doc_id = training_data['id']
        persisted_training_examples = {
            "intent1": ["example1"],
            "intent2": ["example3", "example4"]
        }
        TrainingDataGenerationProcessor.update_is_persisted_flag(doc_id, persisted_training_examples)
        status = TrainingDataGenerator.objects(
            bot="tests2",
            user="testUser2").get()
        assert status['bot'] == 'tests2'
        assert status['user'] == 'testUser2'
        assert status['status'] == EVENT_STATUS.COMPLETED.value
        assert status['document_path'] == 'document/doc.pdf'
        assert status['start_timestamp'] is not None
        assert status['last_update_timestamp'] is not None
        assert status['end_timestamp'] is not None
        response = status['response']
        assert response is not None
        assert response[0]['intent'] == 'intent1'
        assert response[0]['training_examples'][0]['training_example'] == 'example2'
        assert not response[0]['training_examples'][0]['is_persisted']
        assert response[0]['training_examples'][1]['training_example'] == 'example1'
        assert response[0]['training_examples'][1]['is_persisted']
        assert response[1]['intent'] == 'intent2'
        assert response[1]['training_examples'][0]['training_example'] == 'example3'
        assert response[1]['training_examples'][0]['is_persisted']
        assert response[1]['training_examples'][1]['training_example'] == 'example4'
        assert response[1]['training_examples'][1]['is_persisted']

    def test_is_in_progress_false(self):
        status = TrainingDataGenerationProcessor.is_in_progress(
            bot="tests2",
            raise_exception=False
        )
        assert not status

    def test_get_training_data_processor_history(self):
        history = TrainingDataGenerationProcessor.get_training_data_generator_history(bot='tests2')
        assert len(history) == 1

    def test_daily_file_limit_exceeded_False(self, monkeypatch):
        monkeypatch.setitem(Utility.environment['data_generation'], "limit_per_day", 4)
        TrainingDataGenerationProcessor.set_status(
            "tests", "testUser", "Initiated")
        actual_response = TrainingDataGenerationProcessor.check_data_generation_limit("tests")
        assert actual_response is False

    def test_daily_file_limit_exceeded_True(self, monkeypatch):
        monkeypatch.setitem(Utility.environment['data_generation'], "limit_per_day", 1)
        actual_response = TrainingDataGenerationProcessor.check_data_generation_limit("tests", False)
        assert actual_response is True

    def test_daily_file_limit_exceeded_exception(self, monkeypatch):
        monkeypatch.setitem(Utility.environment['data_generation'], "limit_per_day", 1)
        with pytest.raises(AppException) as exp:
            assert TrainingDataGenerationProcessor.check_data_generation_limit("tests")

        assert str(exp.value) == "Daily file processing limit exceeded."


class TestAgentProcessor:

    def test_get_agent(self, monkeypatch):
        def mongo_store(*args, **kwargs):
            return None

        monkeypatch.setattr(Utility, "get_local_mongo_store", mongo_store)
        agent = AgentProcessor.get_agent("tests")
        assert isinstance(agent, Agent)

    def test_get_agent_from_cache(self):
        agent = AgentProcessor.get_agent("tests")
        assert isinstance(agent, Agent)

    def test_get_agent_from_cache_does_not_exists(self):
        with pytest.raises(AppException):
            agent = AgentProcessor.get_agent("test")
            assert isinstance(agent, Agent)


class TestModelProcessor:

    @pytest.fixture(autouse=True, scope='class')
    def init_connection(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        connect(**Utility.mongoengine_connection())
        yield None
        Utility.environment['notifications']['enable'] = False

    @pytest.fixture
    def test_set_training_status_inprogress(self):
        ModelProcessor.set_training_status("tests", "testUser", "Inprogress")
        model_training = ModelTraining.objects(bot="tests", status="Inprogress")
        return model_training

    def test_set_training_status_Done(self, test_set_training_status_inprogress):
        assert test_set_training_status_inprogress.__len__() == 1
        assert test_set_training_status_inprogress.first().bot == "tests"
        assert test_set_training_status_inprogress.first().user == "testUser"
        assert test_set_training_status_inprogress.first().status == "Inprogress"
        training_status_inprogress_id = test_set_training_status_inprogress.first().id

        ModelProcessor.set_training_status(bot="tests",
                                           user="testUser",
                                           status="Done",
                                           model_path="model_path"
                                           )
        model_training = ModelTraining.objects(bot="tests", status="Done")
        ids = [model.to_mongo().to_dict()['_id'] for model in model_training]
        index = ids.index(training_status_inprogress_id)
        assert model_training.count() == 4
        assert training_status_inprogress_id in ids
        assert model_training[index].bot == "tests"
        assert model_training[index].user == "testUser"
        assert model_training[index].status == "Done"
        assert model_training[index].model_path == "model_path"
        assert ModelTraining.objects(bot="tests", status="Inprogress").__len__() == 0

    def test_set_training_status_Fail(self, test_set_training_status_inprogress):
        assert test_set_training_status_inprogress.__len__() == 1
        assert test_set_training_status_inprogress.first().bot == "tests"
        assert test_set_training_status_inprogress.first().user == "testUser"
        assert test_set_training_status_inprogress.first().status == "Inprogress"
        training_status_inprogress_id = test_set_training_status_inprogress.first().id

        ModelProcessor.set_training_status(bot="tests",
                                           user="testUser",
                                           status="Fail",
                                           model_path=None,
                                           exception="exception occurred while training model."
                                           )
        model_training = ModelTraining.objects(bot="tests", status="Fail")

        assert model_training.__len__() == 1
        assert model_training.first().id == training_status_inprogress_id
        assert model_training.first().bot == "tests"
        assert model_training.first().user == "testUser"
        assert model_training.first().status == "Fail"
        assert model_training.first().model_path is None
        assert model_training.first().exception == "exception occurred while training model."
        assert ModelTraining.objects(bot="tests", status="Inprogress").__len__() == 0

    def test_is_training_inprogress_False(self):
        actual_response = ModelProcessor.is_training_inprogress("tests")
        assert actual_response is False

    def test_is_training_inprogress_True(self, test_set_training_status_inprogress):
        assert test_set_training_status_inprogress.__len__() == 1
        assert test_set_training_status_inprogress.first().bot == "tests"
        assert test_set_training_status_inprogress.first().user == "testUser"
        assert test_set_training_status_inprogress.first().status == "Inprogress"

        actual_response = ModelProcessor.is_training_inprogress("tests", False)
        assert actual_response is True

    def test_is_training_inprogress_exception(self, test_set_training_status_inprogress):
        with pytest.raises(AppException) as exp:
            assert ModelProcessor.is_training_inprogress("tests")

        assert str(exp.value) == "Previous model training in progress."

    def test_is_daily_training_limit_exceeded_False(self, monkeypatch):
        monkeypatch.setitem(Utility.environment['model']['train'], "limit_per_day", 7)
        actual_response = ModelProcessor.is_daily_training_limit_exceeded("tests")
        assert actual_response is False

    def test_is_daily_training_limit_exceeded_True(self, monkeypatch):
        monkeypatch.setitem(Utility.environment['model']['train'], "limit_per_day", 1)
        actual_response = ModelProcessor.is_daily_training_limit_exceeded("tests", False)
        assert actual_response is True

    def test_is_daily_training_limit_exceeded_exception(self, monkeypatch):
        monkeypatch.setitem(Utility.environment['model']['train'], "limit_per_day", 1)
        with pytest.raises(AppException) as exp:
            assert ModelProcessor.is_daily_training_limit_exceeded("tests")

        assert str(exp.value) == "Daily model training limit exceeded."

    def test_get_training_history(self):
        actual_response = ModelProcessor.get_training_history("tests")
        assert actual_response
