import asyncio
import glob
import os
import shutil
import tempfile
from datetime import datetime
from io import BytesIO
from typing import List

import pytest
import responses
from fastapi import UploadFile
from mongoengine import connect, DoesNotExist
from mongoengine.errors import ValidationError
from rasa.core.agent import Agent
from rasa.shared.constants import DEFAULT_DOMAIN_PATH, DEFAULT_DATA_PATH, DEFAULT_CONFIG_PATH
from rasa.shared.core.events import UserUttered, ActionExecuted
from rasa.shared.core.training_data.structures import StoryGraph, RuleStep, Checkpoint
from rasa.shared.importers.rasa import Domain, RasaFileImporter
from rasa.shared.nlu.training_data.training_data import TrainingData
from rasa.shared.utils.io import read_config_file

from kairon.shared.actions.data_objects import HttpActionConfig, HttpActionLog
from kairon.api import models
from kairon.api.models import StoryEventType, HttpActionParameters, HttpActionConfigRequest
from kairon.data_processor.constant import UTTERANCE_TYPE, EVENT_STATUS, STORY_EVENT, ALLOWED_DOMAIN_FORMATS, \
    ALLOWED_CONFIG_FORMATS, ALLOWED_NLU_FORMATS, ALLOWED_STORIES_FORMATS, ALLOWED_RULES_FORMATS, REQUIREMENTS
from kairon.data_processor.data_objects import (TrainingExamples,
                                                Slots,
                                                Entities,
                                                Intents,
                                                Actions,
                                                Responses,
                                                ModelTraining, StoryEvents, Stories, ResponseCustom, ResponseText,
                                                TrainingDataGenerator, TrainingDataGeneratorResponse,
                                                TrainingExamplesTrainingDataGenerator, Rules, Feedback, Configs
                                                )
from kairon.data_processor.processor import MongoProcessor
from kairon.data_processor.agent_processor import AgentProcessor
from kairon.data_processor.model_processor import ModelProcessor
from kairon.data_processor.training_data_generation_processor import TrainingDataGenerationProcessor
from kairon.exceptions import AppException
from kairon.train import train_model_for_bot, start_training, train_model_from_mongo
from kairon.utils import Utility
from kairon.api.auth import Authentication
from elasticmock import elasticmock


class TestMongoProcessor:

    @pytest.fixture(autouse=True)
    def init_connection(self):
        os.environ["system_file"] = "./tests/testing_d" \
                                    "ata/system.yaml"
        Utility.load_evironment()
        connect(host=Utility.environment["database"]['url'])

    @pytest.fixture()
    def get_training_data(self):

        async def _read_and_get_data(path: str):
            domain_path = os.path.join(path, DEFAULT_DOMAIN_PATH)
            training_data_path = os.path.join(path, DEFAULT_DATA_PATH)
            config_path = os.path.join(path, DEFAULT_CONFIG_PATH)
            http_actions_path = os.path.join(path, 'http_action.yml')
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
            list(Slots.objects(bot="test_load_yml", user="testUser", influence_conversation=False, status=True))) == 7

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
        assert story_graph.story_steps[14].events[2].entities[0]['entity'] == 'fdResponse'
        assert story_graph.story_steps[15].events[2].intent['name'] == 'user_feedback'
        assert not story_graph.story_steps[15].events[2].entities[0].get('start')
        assert not story_graph.story_steps[15].events[2].entities[0].get('end')
        assert story_graph.story_steps[15].events[2].entities[0]['value'] == 'hate'
        assert story_graph.story_steps[15].events[2].entities[0]['entity'] == 'fdResponse'
        domain = processor.load_domain("test_load_from_path_yml_training_files")
        assert isinstance(domain, Domain)
        assert domain.slots.__len__() == 9
        assert len([slot for slot in domain.slots if slot.influence_conversation is True]) == 2
        assert len([slot for slot in domain.slots if slot.influence_conversation is False]) == 7
        assert domain.intent_properties.__len__() == 29
        assert len([intent for intent in domain.intent_properties.keys() if
                    domain.intent_properties.get(intent)['used_entities']]) == 27
        assert len([intent for intent in domain.intent_properties.keys() if
                    not domain.intent_properties.get(intent)['used_entities']]) == 2
        assert domain.templates.keys().__len__() == 27
        assert domain.entities.__len__() == 8
        assert domain.forms.__len__() == 2
        assert domain.forms.__len__() == 2
        assert domain.forms['ticket_attributes_form'] == {'priority': [{'type': 'from_entity', 'entity': 'priority'}]}
        assert domain.forms['ticket_file_form'] == {'file': [{'type': 'from_entity', 'entity': 'file'}]}
        assert isinstance(domain.forms, dict)
        assert domain.user_actions.__len__() == 43
        assert processor.list_actions('test_load_from_path_yml_training_files').__len__() == 11
        assert domain.intents.__len__() == 29
        assert not Utility.check_empty_string(
            domain.templates["utter_cheer_up"][0]["image"]
        )
        assert domain.templates["utter_did_that_help"][0]["buttons"].__len__() == 2
        assert domain.templates["utter_offer_help"][0]["custom"]
        assert domain.slots[0].type_name == "any"
        assert domain.slots[1].type_name == "unfeaturized"
        rules = processor.fetch_rule_block_names("test_load_from_path_yml_training_files")
        assert len(rules) == 4
        actions = processor.load_http_action("test_load_from_path_yml_training_files")
        assert isinstance(actions, dict) is True
        assert len(actions['http_actions']) == 5

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
        assert story_graph.story_steps[14].events[2].entities[0]['entity'] == 'fdResponse'
        assert story_graph.story_steps[15].events[2].intent['name'] == 'user_feedback'
        assert story_graph.story_steps[15].events[2].entities[0]['start'] == 13
        assert story_graph.story_steps[15].events[2].entities[0]['end'] == 34
        assert story_graph.story_steps[15].events[2].entities[0]['value'] == 'hate'
        assert story_graph.story_steps[15].events[2].entities[0]['entity'] == 'fdResponse'
        domain = processor.load_domain("all")
        assert isinstance(domain, Domain)
        assert domain.slots.__len__() == 9
        assert domain.templates.keys().__len__() == 27
        assert domain.entities.__len__() == 8
        assert domain.forms.__len__() == 2
        assert domain.forms['ticket_attributes_form'] == {}
        assert isinstance(domain.forms, dict)
        print(domain.user_actions)
        assert domain.user_actions.__len__() == 38
        assert processor.list_actions('all').__len__() == 11
        assert domain.intents.__len__() == 29
        assert not Utility.check_empty_string(
            domain.templates["utter_cheer_up"][0]["image"]
        )
        assert domain.templates["utter_did_that_help"][0]["buttons"].__len__() == 2
        assert domain.templates["utter_offer_help"][0]["custom"]
        assert domain.slots[0].type_name == "any"
        assert domain.slots[1].type_name == "unfeaturized"

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
        assert story_graph.story_steps[14].events[2].entities[0]['entity'] == 'fdResponse'
        assert story_graph.story_steps[15].events[2].intent['name'] == 'user_feedback'
        assert story_graph.story_steps[15].events[2].entities[0]['start'] == 13
        assert story_graph.story_steps[15].events[2].entities[0]['end'] == 34
        assert story_graph.story_steps[15].events[2].entities[0]['value'] == 'hate'
        assert story_graph.story_steps[15].events[2].entities[0]['entity'] == 'fdResponse'
        domain = processor.load_domain("all")
        assert isinstance(domain, Domain)
        assert domain.slots.__len__() == 9
        assert domain.templates.keys().__len__() == 27
        assert domain.entities.__len__() == 8
        assert domain.forms.__len__() == 2
        assert isinstance(domain.forms, dict)
        assert domain.user_actions.__len__() == 38
        assert domain.intents.__len__() == 29
        assert processor.list_actions('all').__len__() == 11
        assert not Utility.check_empty_string(
            domain.templates["utter_cheer_up"][0]["image"]
        )
        assert domain.templates["utter_did_that_help"][0]["buttons"].__len__() == 2
        assert domain.templates["utter_offer_help"][0]["custom"]
        assert domain.slots[0].type_name == "any"
        assert domain.slots[1].type_name == "unfeaturized"

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
        assert domain.slots.__len__() == 1
        assert domain.slots[0].name == 'bot'
        assert domain.slots[0].value == 'tests'
        assert domain.templates.keys().__len__() == 11
        assert domain.entities.__len__() == 0
        assert domain.form_names.__len__() == 0
        assert domain.user_actions.__len__() == 11
        assert domain.intents.__len__() == 14

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
        assert results[0]["message"] == "Training Example added successfully!"

    def test_add_same_training_example(self):
        processor = MongoProcessor()
        results = list(
            processor.add_training_example(["Hi"], "greeting", "tests", "testUser", is_integration=False)
        )
        assert results[0]["_id"] is None
        assert results[0]["text"] == "Hi"
        assert results[0]["message"] == "Training Example already exists!"

    def test_add_training_example_duplicate_case_insensitive(self):
        processor = MongoProcessor()
        results = list(
            processor.add_training_example(["hi"], "greeting", "tests", "testUser", is_integration=False)
        )
        assert results[0]["_id"] is None
        assert results[0]["text"] == "hi"
        assert results[0]["message"] == "Training Example already exists!"

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
        assert results[0]["message"] == "Training Example added successfully!"
        intents = processor.get_intents("tests")
        assert any("get_priority" == intent["name"] for intent in intents)
        entities = processor.get_entities("tests")
        assert any("priority" == entity["name"] for entity in entities)
        new_training_example = TrainingExamples.objects(bot="tests").get(
            text="Log a critical issue"
        )
        slots = Slots.objects(bot="tests")
        new_slot = slots.get(name="priority")
        assert slots.__len__() == 2
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
                results[0]["text"] == "Make [TKT456](ticketID) a [critical issue](priority)"
        )
        assert results[0]["message"] == "Training Example added successfully!"
        actual = list(processor.get_training_examples("get_priority", "tests"))
        slots = Slots.objects(bot="tests")
        new_slot = slots.get(name="ticketID")
        assert any(
            [value["text"] == "Log a [critical issue](priority)" for value in actual]
        )
        assert any(
            [
                value["text"] == "Make [TKT456](ticketID) a [critical issue](priority)"
                for value in actual
            ]
        )
        assert slots.__len__() == 3
        assert new_slot.name == "ticketID"
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
        assert actual[0]['message'] == "Training Example already exists!"
        assert actual[1]['message'] == "Training Example added successfully!"

    def test_add_entity(self):
        processor = MongoProcessor()
        assert processor.add_entity("file_text", "tests", "testUser")
        slots = Slots.objects(bot="tests")
        new_slot = slots.get(name="file_text")
        enitity = Entities.objects(bot="tests").get(name="file_text")
        assert slots.__len__() == 4
        assert new_slot.name == "file_text"
        assert new_slot.type == "text"
        assert enitity.name == "file_text"

    def test_get_entities(self):
        processor = MongoProcessor()
        expected = ["priority", "file_text", "ticketID"]
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
        assert processor.add_text_response("Great", "utter_happy", "tests", "testUser")
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
        folder = "models/tests"
        file = Utility.get_latest_file(folder, '*.tar.gz')
        Utility.move_old_models(folder, file)
        assert len(list(glob.glob(folder+'/*.tar.gz'))) == 1

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

        model_path = start_training("test_initial", "testUser", reload=False)
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

    def test_add_endpoints_add_tracker_endpoint_missing_db(self):
        processor = MongoProcessor()
        config = {"tracker_endpoint": {"url": "mongodb://localhost:27017"}}
        with pytest.raises(ValidationError):
            processor.add_endpoints(config, bot="tests3", user="testUser")
            endpoint = processor.get_endpoints("tests3")
            assert endpoint.get("bot_endpoint") is None
            assert endpoint.get("action_endpoint") is None
            assert endpoint.get("tracker_endpoint") is None

    def test_add_endpoints_add_tracker_endpoint_invalid_url(self):
        processor = MongoProcessor()
        config = {
            "tracker_endpoint": {
                "url": "mongo://localhost:27017",
                "db": "conversations",
            }
        }
        with pytest.raises(AppException):
            processor.add_endpoints(config, bot="tests3", user="testUser")
            endpoint = processor.get_endpoints("tests3")
            assert endpoint.get("bot_endpoint") is None
            assert endpoint.get("action_endpoint") is None
            assert endpoint.get("tracker") is None

    def test_add_endpoints_add_tracker_endpoint(self):
        processor = MongoProcessor()
        config = {
            "tracker_endpoint": {
                "url": "mongodb://localhost:27017/",
                "db": "conversations",
            }
        }
        processor.add_endpoints(config, bot="tests3", user="testUser")
        endpoint = processor.get_endpoints("tests3")
        assert endpoint.get("bot_endpoint") is None
        assert endpoint.get("action_endpoint") is None
        assert (
                endpoint.get("tracker_endpoint").get("url") == "mongodb://localhost:27017/"
        )
        assert endpoint.get("tracker_endpoint").get("db") == "conversations"
        assert endpoint.get("tracker_endpoint").get("type") == "mongo"

    def test_update_endpoints(self):
        processor = MongoProcessor()
        config = {
            "action_endpoint": {"url": "http://localhost:8000/"},
            "bot_endpoint": {"url": "http://localhost:5000/"},
            "tracker_endpoint": {
                "url": "mongodb://localhost:27017/",
                "db": "conversations",
            },
        }
        processor.add_endpoints(config, bot="tests", user="testUser")
        endpoint = processor.get_endpoints("tests")
        assert endpoint.get("bot_endpoint").get("url") == "http://localhost:5000/"
        assert endpoint.get("action_endpoint").get("url") == "http://localhost:8000/"
        assert (
                endpoint.get("tracker_endpoint").get("url") == "mongodb://localhost:27017/"
        )
        assert endpoint.get("tracker_endpoint").get("db") == "conversations"
        assert endpoint.get("tracker_endpoint").get("type") == "mongo"

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
        assert (
                endpoint.get("tracker_endpoint").get("url") == "mongodb://localhost:27017/"
        )
        assert endpoint.get("tracker_endpoint").get("db") == "conversations"
        assert endpoint.get("tracker_endpoint").get("type") == "mongo"

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
            response = processor.get_utterance_from_intent("", "tests")

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
        processor.edit_training_example(examples[0]["_id"], example="hello, there", intent="Greet", bot="tests",
                                        user="testUser")
        examples = list(processor.get_training_examples("greet", "tests"))
        assert any(example['text'] == "hello, there" for example in examples)

    def test_edit_training_example_with_entities(self):
        processor = MongoProcessor()
        examples = list(processor.get_training_examples("greet", "tests"))
        processor.edit_training_example(examples[0]["_id"], example="[Meghalaya](Location) India", intent="greet",
                                        bot="tests", user="testUser")
        examples = list(processor.get_training_examples("greet", "tests"))
        assert any(example['text'] == "[Meghalaya](Location) India" for example in examples)

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
        processor.edit_text_response(responses[0]["_id"], "That's Great!", name="Utter_Happy", bot="tests",
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
        token = Authentication.create_access_token(data={"sub": "test@gmail.com"}).decode("utf8")
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
        token = Authentication.create_access_token(data={"sub": "test@gmail.com"}).decode("utf8")
        responses.add(
            responses.GET,
            "http://localhost/api/bot/model/reload",
            json={"message": "Reloading Model!"},
            match=[responses.json_params_matcher({"bot": "tests", "user": "testUser", "token": token})],
            status=200
        )
        monkeypatch.setitem(Utility.environment['model']['train'], "agent_url", "http://localhost/")
        model_path = start_training("tests", "testUser")
        assert model_path

    def test_start_training_done_reload_event_without_token(self, monkeypatch):
        responses.add(
            responses.GET,
            "http://localhost/api/bot/model/reload",
            json={"message": "Reloading Model!"},
            match=[responses.json_params_matcher({"bot": "tests", "user": "testUser", "token": None})],
            status=200
        )
        monkeypatch.setitem(Utility.environment['model']['train'], "agent_url", "http://localhost/")
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
        processor.delete_response(utter_intentA_2_id, bot, user)
        resp = processor.get_response(utterance, bot)
        assert len(list(resp)) == 0

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
        processor.delete_utterance(utterance, bot, user)

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

        processor.add_slot({"name": "bot", "type": "any", "initial_value": bot, "influence_conversation": False}, bot,
                           user, raise_exception_if_exists=False)
        slot = Slots.objects(name__iexact='bot', bot=bot, user=user).get()
        assert slot['name'] == 'bot'
        assert slot['type'] == 'any'
        assert slot['initial_value'] == bot
        assert not slot['influence_conversation']

        with pytest.raises(AppException):
            msg = processor.add_slot(
                {"name": "bot", "type": "any", "initial_value": bot, "influence_conversation": False}, bot, user)
            assert msg == 'Slot exists'

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
        http_action_content = "http_actions:\n- action_name: action_performanceUser1000@digite.com\n  auth_token: bearer hjklfsdjsjkfbjsbfjsvhfjksvfjksvfjksvf\n  http_url: http://www.alphabet.com\n  params_list:\n  - key: testParam1\n    parameter_type: value\n    value: testValue1\n  - key: testParam2\n    parameter_type: slot\n    value: testValue1\n  request_method: GET\n  response: json\n".encode()
        nlu = UploadFile(filename="nlu.yml", file=BytesIO(nlu_content))
        stories = UploadFile(filename="stories.md", file=BytesIO(stories_content))
        config = UploadFile(filename="config.yml", file=BytesIO(config_content))
        domain = UploadFile(filename="domain.yml", file=BytesIO(domain_content))
        http_action = UploadFile(filename="http_action.yml", file=BytesIO(http_action_content))
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
        assert len(actions["http_actions"]) == 1
        processor.delete_http_action(bot="test_http", user="http_creator")
        actions = processor.load_http_action("test_http")
        assert not actions
        assert isinstance(actions, dict)

    def test_save_http_action_already_exists(self):
        test_dict = {"http_actions": [{"action_name": "rain_today", "http_url": "http://f2724.kairon.io/",
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
        processor = MongoProcessor()
        processor.save_http_action(test_dict, 'test', 'test')
        action = HttpActionConfig.objects(bot='test', user='test').get(
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
        HttpActionLog(intent="intent1", action="http_action", sender="sender_id",
                      timestamp=datetime(2021, 4, 11, 11, 39, 48, 376000),
                      request_params=request_params, api_response="Response", bot_response="Bot Response",
                      bot=bot).save()
        HttpActionLog(intent="intent2", action="http_action", sender="sender_id",
                      url="http://kairon-api.digite.com/api/bot",
                      request_params=request_params, api_response="Response", bot_response="Bot Response", bot=bot,
                      status="FAILURE").save()
        HttpActionLog(intent="intent1", action="http_action", sender="sender_id",
                      request_params=request_params, api_response="Response", bot_response="Bot Response",
                      bot=bot_2).save()
        HttpActionLog(intent="intent3", action="http_action", sender="sender_id",
                      request_params=request_params, api_response="Response", bot_response="Bot Response", bot=bot,
                      status="FAILURE").save()
        HttpActionLog(intent="intent4", action="http_action", sender="sender_id",
                      request_params=request_params, api_response="Response", bot_response="Bot Response",
                      bot=bot).save()
        HttpActionLog(intent="intent5", action="http_action", sender="sender_id",
                      request_params=request_params, api_response="Response", bot_response="Bot Response", bot=bot,
                      status="FAILURE").save()
        HttpActionLog(intent="intent6", action="http_action", sender="sender_id",
                      request_params=request_params, api_response="Response", bot_response="Bot Response",
                      bot=bot).save()
        HttpActionLog(intent="intent7", action="http_action", sender="sender_id",
                      request_params=request_params, api_response="Response", bot_response="Bot Response",
                      bot=bot).save()
        HttpActionLog(intent="intent8", action="http_action", sender="sender_id",
                      request_params=request_params, api_response="Response", bot_response="Bot Response",
                      bot=bot).save()
        HttpActionLog(intent="intent9", action="http_action", sender="sender_id",
                      request_params=request_params, api_response="Response", bot_response="Bot Response",
                      bot=bot).save()
        HttpActionLog(intent="intent10", action="http_action", sender="sender_id",
                      request_params=request_params, api_response="Response", bot_response="Bot Response",
                      bot=bot_2).save()
        HttpActionLog(intent="intent11", action="http_action", sender="sender_id",
                      request_params=request_params, api_response="Response", bot_response="Bot Response",
                      bot=bot).save()
        HttpActionLog(intent="intent12", action="http_action", sender="sender_id",
                      request_params=request_params, api_response="Response", bot_response="Bot Response", bot=bot_2,
                      status="FAILURE").save()
        HttpActionLog(intent="intent13", action="http_action", sender="sender_id_13",
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
        cnt = processor.get_row_count(HttpActionLog, bot)
        assert cnt == 11

        cnt = processor.get_row_count(HttpActionLog, bot_2)
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

    def test_add_feedback(self):
        mongo_processor = MongoProcessor()
        mongo_processor.add_feedback(4.5, 'test', 'test', feedback='product is good')
        feedback = Feedback.objects(bot='test', user='test').get()
        assert feedback['rating'] == 4.5
        assert feedback['scale'] == 5.0
        assert feedback['feedback'] == 'product is good'
        assert feedback['timestamp']

    def test_add_feedback_2(self):
        mongo_processor = MongoProcessor()
        mongo_processor.add_feedback(5.0, 'test', 'test_user', scale=10, feedback='i love kairon')
        feedback = Feedback.objects(bot='test', user='test_user').get()
        assert feedback['rating'] == 5.0
        assert feedback['scale'] == 10
        assert feedback['feedback'] == 'i love kairon'
        assert feedback['timestamp']

    def test_add_feedback_3(self):
        mongo_processor = MongoProcessor()
        mongo_processor.add_feedback(5.0, 'test', 'test')
        feedback = list(Feedback.objects(bot='test', user='test'))
        assert feedback[1]['rating'] == 5.0
        assert feedback[1]['scale'] == 5.0
        assert not feedback[1]['feedback']
        assert feedback[1]['timestamp']

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
        assert story_graph.story_steps[14].events[2].entities[0]['entity'] == 'fdResponse'
        assert story_graph.story_steps[15].events[2].intent['name'] == 'user_feedback'
        assert not story_graph.story_steps[15].events[2].entities[0].get('start')
        assert not story_graph.story_steps[15].events[2].entities[0].get('end')
        assert story_graph.story_steps[15].events[2].entities[0]['value'] == 'hate'
        assert story_graph.story_steps[15].events[2].entities[0]['entity'] == 'fdResponse'
        domain = mongo_processor.load_domain(bot)
        assert isinstance(domain, Domain)
        assert domain.slots.__len__() == 9
        assert len([slot for slot in domain.slots if slot.influence_conversation is True]) == 2
        assert len([slot for slot in domain.slots if slot.influence_conversation is False]) == 7
        assert domain.intent_properties.__len__() == 29
        assert len([intent for intent in domain.intent_properties.keys() if
                    domain.intent_properties.get(intent)['used_entities']]) == 27
        assert len([intent for intent in domain.intent_properties.keys() if
                    not domain.intent_properties.get(intent)['used_entities']]) == 2
        assert domain.templates.keys().__len__() == 27
        assert domain.entities.__len__() == 8
        assert domain.form_names.__len__() == 2
        assert domain.user_actions.__len__() == 43
        assert domain.intents.__len__() == 29
        assert not Utility.check_empty_string(
            domain.templates["utter_cheer_up"][0]["image"]
        )
        assert domain.templates["utter_did_that_help"][0]["buttons"].__len__() == 2
        assert domain.templates["utter_offer_help"][0]["custom"]
        assert domain.slots[0].type_name == "any"
        assert domain.slots[1].type_name == "unfeaturized"
        rules = mongo_processor.fetch_rule_block_names(bot)
        assert len(rules) == 4
        actions = mongo_processor.load_http_action(bot)
        assert isinstance(actions, dict) is True
        assert len(actions['http_actions']) == 5

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
        assert story_graph.story_steps[14].events[2].entities[0]['entity'] == 'fdResponse'
        assert story_graph.story_steps[15].events[2].intent['name'] == 'user_feedback'
        assert story_graph.story_steps[15].events[2].entities[0]['start'] == 13
        assert story_graph.story_steps[15].events[2].entities[0]['end'] == 34
        assert story_graph.story_steps[15].events[2].entities[0]['value'] == 'hate'
        assert story_graph.story_steps[15].events[2].entities[0]['entity'] == 'fdResponse'
        domain = mongo_processor.load_domain(bot)
        assert isinstance(domain, Domain)
        assert domain.slots.__len__() == 9
        assert domain.templates.keys().__len__() == 27
        assert domain.entities.__len__() == 8
        assert domain.form_names.__len__() == 2
        assert domain.user_actions.__len__() == 38
        assert domain.intents.__len__() == 29
        assert not Utility.check_empty_string(
            domain.templates["utter_cheer_up"][0]["image"]
        )
        assert domain.templates["utter_did_that_help"][0]["buttons"].__len__() == 2
        assert domain.templates["utter_offer_help"][0]["custom"]
        assert domain.slots[0].type_name == "any"
        assert domain.slots[1].type_name == "unfeaturized"
        rules = mongo_processor.fetch_rule_block_names(bot)
        assert rules == ['ask the user to rephrase whenever they send a message with low nlu confidence']
        actions = mongo_processor.load_http_action(bot)
        assert not actions

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
        assert story_graph.story_steps[14].events[2].entities[0]['entity'] == 'fdResponse'
        assert story_graph.story_steps[15].events[2].intent['name'] == 'user_feedback'
        assert not story_graph.story_steps[15].events[2].entities[0].get('start')
        assert not story_graph.story_steps[15].events[2].entities[0].get('end')
        assert story_graph.story_steps[15].events[2].entities[0]['value'] == 'hate'
        assert story_graph.story_steps[15].events[2].entities[0]['entity'] == 'fdResponse'
        domain = mongo_processor.load_domain(bot)
        assert isinstance(domain, Domain)
        assert domain.slots.__len__() == 9
        assert len([slot for slot in domain.slots if slot.influence_conversation is True]) == 2
        assert len([slot for slot in domain.slots if slot.influence_conversation is False]) == 7
        assert domain.intent_properties.__len__() == 29
        assert len([intent for intent in domain.intent_properties.keys() if
                    domain.intent_properties.get(intent)['used_entities']]) == 27
        assert len([intent for intent in domain.intent_properties.keys() if
                    not domain.intent_properties.get(intent)['used_entities']]) == 2
        assert domain.templates.keys().__len__() == 27
        assert domain.entities.__len__() == 8
        assert domain.form_names.__len__() == 2
        assert domain.user_actions.__len__() == 43
        assert domain.intents.__len__() == 29
        assert not Utility.check_empty_string(
            domain.templates["utter_cheer_up"][0]["image"]
        )
        assert domain.templates["utter_did_that_help"][0]["buttons"].__len__() == 2
        assert domain.templates["utter_offer_help"][0]["custom"]
        assert domain.slots[0].type_name == "any"
        assert domain.slots[1].type_name == "unfeaturized"
        rules = mongo_processor.fetch_rule_block_names(bot)
        assert len(rules) == 4
        actions = mongo_processor.load_http_action(bot)
        assert isinstance(actions, dict) is True
        assert len(actions['http_actions']) == 5

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
        assert story_graph.story_steps[14].events[2].entities[0]['entity'] == 'fdResponse'
        assert story_graph.story_steps[15].events[2].intent['name'] == 'user_feedback'
        assert not story_graph.story_steps[15].events[2].entities[0].get('start')
        assert not story_graph.story_steps[15].events[2].entities[0].get('end')
        assert story_graph.story_steps[15].events[2].entities[0]['value'] == 'hate'
        assert story_graph.story_steps[15].events[2].entities[0]['entity'] == 'fdResponse'
        domain = mongo_processor.load_domain(bot)
        assert isinstance(domain, Domain)
        assert domain.slots.__len__() == 9
        assert len([slot for slot in domain.slots if slot.influence_conversation is True]) == 2
        assert len([slot for slot in domain.slots if slot.influence_conversation is False]) == 7
        assert domain.intent_properties.__len__() == 30
        assert len([intent for intent in domain.intent_properties.keys() if
                    domain.intent_properties.get(intent)['used_entities']]) == 27
        assert len([intent for intent in domain.intent_properties.keys() if
                    not domain.intent_properties.get(intent)['used_entities']]) == 3
        assert domain.templates.keys().__len__() == 29
        assert domain.entities.__len__() == 8
        assert domain.form_names.__len__() == 2
        assert domain.user_actions.__len__() == 48
        assert domain.intents.__len__() == 30
        assert not Utility.check_empty_string(
            domain.templates["utter_cheer_up"][0]["image"]
        )
        assert domain.templates["utter_did_that_help"][0]["buttons"].__len__() == 2
        assert domain.templates["utter_offer_help"][0]["custom"]
        assert domain.slots[0].type_name == "any"
        assert domain.slots[1].type_name == "unfeaturized"
        rules = mongo_processor.fetch_rule_block_names(bot)
        assert len(rules) == 4
        actions = mongo_processor.load_http_action(bot)
        assert isinstance(actions, dict) is True
        assert len(actions['http_actions']) == 5

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
        assert story_graph.story_steps[14].events[2].entities[0]['entity'] == 'fdResponse'
        assert story_graph.story_steps[15].events[2].intent['name'] == 'user_feedback'
        assert not story_graph.story_steps[15].events[2].entities[0].get('start')
        assert not story_graph.story_steps[15].events[2].entities[0].get('end')
        assert story_graph.story_steps[15].events[2].entities[0]['value'] == 'hate'
        assert story_graph.story_steps[15].events[2].entities[0]['entity'] == 'fdResponse'
        domain = mongo_processor.load_domain(bot)
        assert isinstance(domain, Domain)
        assert domain.slots.__len__() == 9
        assert len([slot for slot in domain.slots if slot.influence_conversation is True]) == 2
        assert len([slot for slot in domain.slots if slot.influence_conversation is False]) == 7
        assert domain.intent_properties.__len__() == 30
        assert len([intent for intent in domain.intent_properties.keys() if
                    domain.intent_properties.get(intent)['used_entities']]) == 27
        assert len([intent for intent in domain.intent_properties.keys() if
                    not domain.intent_properties.get(intent)['used_entities']]) == 3
        assert domain.templates.keys().__len__() == 29
        assert domain.entities.__len__() == 8
        assert domain.form_names.__len__() == 2
        assert domain.user_actions.__len__() == 48
        assert domain.intents.__len__() == 30
        assert not Utility.check_empty_string(
            domain.templates["utter_cheer_up"][0]["image"]
        )
        assert domain.templates["utter_did_that_help"][0]["buttons"].__len__() == 2
        assert domain.templates["utter_offer_help"][0]["custom"]
        assert domain.slots[0].type_name == "any"
        assert domain.slots[1].type_name == "unfeaturized"
        rules = mongo_processor.fetch_rule_block_names(bot)
        assert len(rules) == 4
        actions = mongo_processor.load_http_action(bot)
        assert isinstance(actions, dict) is True
        assert len(actions['http_actions']) == 5

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
        assert domain.slots.__len__() == 9
        assert len([slot for slot in domain.slots if slot.influence_conversation is True]) == 2
        assert len([slot for slot in domain.slots if slot.influence_conversation is False]) == 7
        assert domain.intent_properties.__len__() == 30
        assert len([intent for intent in domain.intent_properties.keys() if
                    domain.intent_properties.get(intent)['used_entities']]) == 27
        assert len([intent for intent in domain.intent_properties.keys() if
                    not domain.intent_properties.get(intent)['used_entities']]) == 3
        assert domain.templates.keys().__len__() == 29
        assert domain.entities.__len__() == 8
        assert domain.form_names.__len__() == 2
        assert domain.user_actions.__len__() == 48
        assert domain.intents.__len__() == 30
        assert not Utility.check_empty_string(
            domain.templates["utter_cheer_up"][0]["image"]
        )
        assert domain.templates["utter_did_that_help"][0]["buttons"].__len__() == 2
        assert domain.templates["utter_offer_help"][0]["custom"]
        assert domain.slots[0].type_name == "any"
        assert domain.slots[1].type_name == "unfeaturized"
        rules = mongo_processor.fetch_rule_block_names(bot)
        assert len(rules) == 4
        actions = mongo_processor.load_http_action(bot)
        assert isinstance(actions, dict) is True
        assert len(actions['http_actions']) == 5

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
        assert story_graph.story_steps[14].events[2].entities[0]['entity'] == 'fdResponse'
        assert story_graph.story_steps[15].events[2].intent['name'] == 'user_feedback'
        assert not story_graph.story_steps[15].events[2].entities[0].get('start')
        assert not story_graph.story_steps[15].events[2].entities[0].get('end')
        assert story_graph.story_steps[15].events[2].entities[0]['value'] == 'hate'
        assert story_graph.story_steps[15].events[2].entities[0]['entity'] == 'fdResponse'

    def test_delete_config_and_actions_only(self):
        bot = 'test'
        user = 'test'
        mongo_processor = MongoProcessor()
        mongo_processor.delete_bot_data(bot, user, {"config", "http_actions"})
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
        assert domain.slots.__len__() == 9
        assert domain.intent_properties.__len__() == 30
        assert domain.templates.keys().__len__() == 29
        assert domain.entities.__len__() == 8
        assert domain.form_names.__len__() == 2
        assert domain.user_actions.__len__() == 48
        assert domain.intents.__len__() == 30
        rules = mongo_processor.fetch_rule_block_names(bot)
        assert len(rules) == 4
        actions = mongo_processor.load_http_action(bot)
        assert isinstance(actions, dict) is True
        assert not actions
        assert mongo_processor.load_config(bot)

    @pytest.mark.asyncio
    async def test_save_actions_and_config_only(self, get_training_data):
        path = 'tests/testing_data/yml_training_files'
        bot = 'test'
        user = 'test'
        nlu, story_graph, domain, config, http_actions = await get_training_data(path)
        config['language'] = 'fr'

        mongo_processor = MongoProcessor()
        mongo_processor.save_training_data(bot, user, config=config, http_actions=http_actions, overwrite=True,
                                           what={'http_actions', 'config'})

        assert len(mongo_processor.load_http_action(bot)['http_actions']) == 5
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
        assert domain.slots.__len__() == 0
        assert domain.intent_properties.__len__() == 5
        assert domain.templates.keys().__len__() == 0
        assert domain.entities.__len__() == 0
        assert domain.form_names.__len__() == 0
        assert domain.user_actions.__len__() == 0
        assert domain.intents.__len__() == 5
        rules = mongo_processor.fetch_rule_block_names(bot)
        assert len(rules) == 0
        actions = mongo_processor.load_http_action(bot)
        assert isinstance(actions, dict) is True
        assert len(actions['http_actions']) == 5

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
        assert domain.slots.__len__() == 9
        assert domain.intent_properties.__len__() == 29
        assert domain.templates.keys().__len__() == 25
        assert domain.entities.__len__() == 8
        assert domain.form_names.__len__() == 2
        assert domain.user_actions.__len__() == 36
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

    def test_prepare_training_data_for_validation_with_home_dir(self, resource_prepare_training_data_for_validation_with_home_dir):
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

    def test_prepare_training_data_for_validation_nlu_domain_only(self, resource_prepare_training_data_for_validation_nlu_only):
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

    def test_prepare_training_data_for_validation_rules_only(self, resource_prepare_training_data_for_validation_rules_only):
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
        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(pytest.bot, 'test', [pytest.zip], True)
        assert REQUIREMENTS == files_received
        assert is_event_data
        bot_data_home_dir = Utility.get_latest_file(os.path.join('training_data', pytest.bot))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'domain.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'data', 'nlu.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'config.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'data', 'stories.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'http_action.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'data', 'rules.yml'))
        assert not non_event_validation_summary

    @pytest.fixture()
    def resource_save_and_validate_training_files(self):
        pytest.bot = 'test_validate_and_prepare_data'
        config_path = 'tests/testing_data/yml_training_files/config.yml'
        domain_path = 'tests/testing_data/yml_training_files/domain.yml'
        nlu_path = 'tests/testing_data/yml_training_files/data/nlu.yml'
        stories_path = 'tests/testing_data/yml_training_files/data/stories.yml'
        http_action_path = 'tests/testing_data/yml_training_files/http_action.yml'
        rules_path = 'tests/testing_data/yml_training_files/data/rules.yml'
        pytest.config = UploadFile(filename="config.yml", file=BytesIO(open(config_path, 'rb').read()))
        pytest.domain = UploadFile(filename="domain.yml", file=BytesIO(open(domain_path, 'rb').read()))
        pytest.nlu = UploadFile(filename="nlu.yml", file=BytesIO(open(nlu_path, 'rb').read()))
        pytest.stories = UploadFile(filename="stories.yml", file=BytesIO(open(stories_path, 'rb').read()))
        pytest.http_actions = UploadFile(filename="http_action.yml", file=BytesIO(open(http_action_path, 'rb').read()))
        pytest.rules = UploadFile(filename="rules.yml", file=BytesIO(open(rules_path, 'rb').read()))
        pytest.non_nlu = UploadFile(filename="non_nlu.yml", file=BytesIO(open(rules_path, 'rb').read()))
        yield "resource_save_and_validate_training_files"
        shutil.rmtree(os.path.join('training_data', pytest.bot))

    @pytest.fixture()
    def resource_validate_and_prepare_data_save_actions_and_config_append(self):
        import json

        pytest.bot = 'test_validate_and_prepare_data'
        config = "language: fr\npipeline:\n- name: WhitespaceTokenizer\n- name: LexicalSyntacticFeaturizer\n-  name: DIETClassifier\npolicies:\n-  name: TEDPolicy".encode()
        actions = {"http_actions": [{"action_name": "test_validate_and_prepare_data", "http_url": "http://www.alphabet.com", "request_method": "GET", "response": "json"}]}
        actions = json.dumps(actions).encode('utf-8')
        pytest.config = UploadFile(filename="config.yml", file=BytesIO(config))
        pytest.http_actions = UploadFile(filename="http_action.yml", file=BytesIO(actions))
        yield "resource_validate_and_prepare_data_save_actions_and_config_append"
        shutil.rmtree(os.path.join('training_data', pytest.bot))

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_save_training_files(self, resource_save_and_validate_training_files):
        processor = MongoProcessor()
        training_file = [pytest.config, pytest.domain, pytest.nlu, pytest.stories, pytest.http_actions, pytest.rules]
        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(pytest.bot, 'test', training_file, True)
        assert REQUIREMENTS == files_received
        assert is_event_data
        bot_data_home_dir = Utility.get_latest_file(os.path.join('training_data', pytest.bot))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'domain.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'data', 'nlu.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'config.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'data', 'stories.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'http_action.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'data', 'rules.yml'))
        assert not non_event_validation_summary

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_save_nlu_only(self, resource_save_and_validate_training_files):
        processor = MongoProcessor()
        training_file = [pytest.nlu]
        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(pytest.bot, 'test', training_file, True)
        assert {'nlu'} == files_received
        assert is_event_data
        bot_data_home_dir = Utility.get_latest_file(os.path.join('training_data', pytest.bot))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'domain.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'data', 'nlu.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'config.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'data', 'stories.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'http_action.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'data', 'rules.yml'))
        assert not non_event_validation_summary

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_save_stories_only(self, resource_save_and_validate_training_files):
        processor = MongoProcessor()
        training_file = [pytest.stories]
        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(pytest.bot, 'test', training_file, True)
        assert {'stories'} == files_received
        assert is_event_data
        bot_data_home_dir = Utility.get_latest_file(os.path.join('training_data', pytest.bot))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'domain.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'data', 'nlu.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'config.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'data', 'stories.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'http_action.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'data', 'rules.yml'))
        assert not non_event_validation_summary

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_save_config(self, resource_save_and_validate_training_files):
        processor = MongoProcessor()
        training_file = [pytest.config]
        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(pytest.bot, 'test', training_file, True)
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
        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(pytest.bot, 'test', training_file, True)
        assert {'rules'} == files_received
        assert is_event_data
        bot_data_home_dir = Utility.get_latest_file(os.path.join('training_data', pytest.bot))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'domain.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'data', 'nlu.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'config.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'data', 'stories.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'http_action.yml'))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'data', 'rules.yml'))
        assert not non_event_validation_summary

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_save_actions(self, resource_save_and_validate_training_files):
        processor = MongoProcessor()
        training_file = [pytest.http_actions]
        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(pytest.bot, 'test', training_file, True)
        assert {'http_actions'} == files_received
        assert not is_event_data
        assert not non_event_validation_summary.get("http_actions")
        assert not non_event_validation_summary.get("config")
        assert processor.list_http_actions(pytest.bot).__len__() == 5

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_save_domain(self, resource_save_and_validate_training_files):
        processor = MongoProcessor()
        training_file = [pytest.domain]
        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(pytest.bot, 'test', training_file, True)
        assert {'domain'} == files_received
        assert is_event_data
        bot_data_home_dir = Utility.get_latest_file(os.path.join('training_data', pytest.bot))
        assert os.path.exists(os.path.join(bot_data_home_dir, 'domain.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'data', 'nlu.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'config.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'data', 'stories.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'http_action.yml'))
        assert not os.path.exists(os.path.join(bot_data_home_dir, 'data', 'rules.yml'))
        assert not non_event_validation_summary

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_save_actions_and_config_overwrite(self, resource_save_and_validate_training_files):
        processor = MongoProcessor()
        training_file = [pytest.http_actions, pytest.config]
        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(pytest.bot, 'test', training_file, True)
        assert {'http_actions', 'config'} == files_received
        assert not is_event_data
        assert not non_event_validation_summary.get("http_actions")
        assert not non_event_validation_summary.get("config")
        assert processor.list_http_actions(pytest.bot).__len__() == 5
        config = processor.load_config(pytest.bot)
        assert config['pipeline']
        assert config['policies']
        assert config['language']

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_save_actions_and_config_append(self, resource_validate_and_prepare_data_save_actions_and_config_append):
        processor = MongoProcessor()
        training_file = [pytest.http_actions, pytest.config]
        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(pytest.bot, 'test', training_file, False)
        assert {'http_actions', 'config'} == files_received
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
    async def test_validate_and_prepare_data_no_valid_file_received(self, resource_validate_and_prepare_data_no_valid_file_in_zip):
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
        shutil.copy2('tests/testing_data/yml_training_files/http_action.yml', tmp_dir)
        shutil.copy2('tests/testing_data/yml_training_files/config.yml', tmp_dir)
        shutil.make_archive(zip_file, 'zip', tmp_dir)
        pytest.zip = UploadFile(filename="test.zip", file=BytesIO(open(zip_file + '.zip', 'rb').read()))
        yield "resource_validate_and_prepare_data_zip_actions_config"
        shutil.rmtree(tmp_dir)
        shutil.rmtree(os.path.join('training_data', pytest.bot))

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_zip_actions_config(self, resource_validate_and_prepare_data_zip_actions_config):
        processor = MongoProcessor()
        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(pytest.bot, 'test', [pytest.zip], True)
        assert {'http_actions', 'config'} == files_received
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
        actions = Utility.read_yaml('tests/testing_data/yml_training_files/http_action.yml')
        actions['http_actions'][0].pop('action_name')
        Utility.write_to_file(os.path.join(tmp_dir, 'http_action.yml'), json.dumps(actions).encode())
        shutil.copy2('tests/testing_data/yml_training_files/config.yml', tmp_dir)
        shutil.make_archive(zip_file, 'zip', tmp_dir)
        pytest.zip = UploadFile(filename="test.zip", file=BytesIO(open(zip_file + '.zip', 'rb').read()))
        yield "resource_validate_and_prepare_data_zip_actions_config"
        shutil.rmtree(tmp_dir)
        shutil.rmtree(os.path.join('training_data', pytest.bot))

    @pytest.mark.asyncio
    async def test_validate_and_prepare_data_invalid_zip_actions_config(self, resource_validate_and_prepare_data_invalid_zip_actions_config):
        processor = MongoProcessor()
        files_received, is_event_data, non_event_validation_summary = await processor.validate_and_prepare_data(pytest.bot, 'test', [pytest.zip], True)
        assert non_event_validation_summary['summary']['http_actions'] == ['Required http action fields not found']
        assert files_received == {'http_actions', 'config'}
        assert not is_event_data

    def test_save_component_properties_all(self):
        config = {"nlu_epochs": 200,
                  "response_epochs": 300,
                  "ted_epochs": 400,
                  "nlu_confidence_threshold": 60,
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
        assert len(rule_policy) == 3
        assert rule_policy['core_fallback_action_name'] == 'action_default_fallback'
        assert rule_policy['core_fallback_threshold'] == 0.3
        expected = {
            "language": "en",
            "pipeline": [
                {"name": "WhitespaceTokenizer"},
                {"name": "RegexFeaturizer"},
                {"name": "LexicalSyntacticFeaturizer"},
                {"name": "CountVectorsFeaturizer"},
                {"name": "CountVectorsFeaturizer",
                 "analyzer": "char_wb",
                 "min_ngram": 1,
                 "max_ngram": 4},
                {"name": "DIETClassifier",
                 "epochs": 200},
                {"name": "FallbackClassifier",
                 "threshold": 0.6},
                {"name": "EntitySynonymMapper"},
                {"name": "ResponseSelector",
                 "epochs": 300}
            ],
            "policies": [
                {"name": "MemoizationPolicy"},
                {"name": "TEDPolicy",
                 "epochs": 400},
                {"name": "RulePolicy",
                 'core_fallback_threshold': 0.3,
                 'core_fallback_action_name': 'action_default_fallback'}]
        }
        assert config == expected

    def test_get_config_properties(self):
        expected = {'nlu_confidence_threshold': 0.6,
                    'action_fallback': 'action_default_fallback',
                    'ted_epochs': 400,
                    'nlu_epochs': 200,
                    'response_epochs': 300}
        processor = MongoProcessor()
        config = processor.list_epoch_and_fallback_config('test_all')
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
        expected = {
            "language": "en",
            "pipeline": [
                {"name": "WhitespaceTokenizer"},
                {"name": "RegexFeaturizer"},
                {"name": "LexicalSyntacticFeaturizer"},
                {"name": "CountVectorsFeaturizer"},
                {"name": "CountVectorsFeaturizer",
                 "analyzer": "char_wb",
                 "min_ngram": 1,
                 "max_ngram": 4},
                {"name": "DIETClassifier",
                 "epochs": 200},
                {'name': 'FallbackClassifier',
                 'threshold': 0.7},
                {"name": "EntitySynonymMapper"},
                {"name": "ResponseSelector",
                 "epochs": 300}
            ],
            "policies": [
                {"name": "MemoizationPolicy"},
                {"name": "TEDPolicy",
                 "epochs": 400},
                {"name": "RulePolicy", 'core_fallback_action_name': 'action_default_fallback',
                 'core_fallback_threshold': 0.3 }]
        }
        assert config == expected

    def test_get_config_properties_epoch_only(self):
        expected = {'nlu_confidence_threshold': 0.7,
                    'action_fallback': 'action_default_fallback',
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
                    'action_fallback': 'action_default_fallback',
                    'ted_epochs': 200,
                    'nlu_epochs': 100,
                    'response_epochs': 100}
        processor = MongoProcessor()
        config = processor.list_epoch_and_fallback_config('test_fallback_not_set')
        assert config == expected

    def test_save_component_properties_component_not_exists(self):
        configs = Configs._from_son(
            read_config_file("./template/config/default.yml")
        ).to_mongo().to_dict()
        del configs['pipeline'][5]
        del configs['pipeline'][7]
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
            read_config_file("./template/config/default.yml")
        ).to_mongo().to_dict()
        del configs['pipeline'][6]
        del configs['policies'][2]
        processor = MongoProcessor()
        processor.save_config(configs, 'test_fallback_not_configured', 'test')

        config = {'nlu_confidence_threshold': 80,
                  'action_fallback': 'action_say_bye'}
        processor = MongoProcessor()
        processor.save_component_properties(config, 'test_fallback_not_configured', 'test')
        config = processor.load_config('test_fallback_not_configured')
        expected = {
            "language": "en",
            "pipeline": [
                {"name": "WhitespaceTokenizer"},
                {"name": "RegexFeaturizer"},
                {"name": "LexicalSyntacticFeaturizer"},
                {"name": "CountVectorsFeaturizer"},
                {"name": "CountVectorsFeaturizer",
                 "analyzer": "char_wb",
                 "min_ngram": 1,
                 "max_ngram": 4},
                {"name": "DIETClassifier",
                 "epochs": 100},
                {"name": "FallbackClassifier",
                 "threshold": 0.8},
                {"name": "EntitySynonymMapper"},
                {"name": "ResponseSelector",
                 "epochs": 100}
            ],
            "policies": [
                {"name": "MemoizationPolicy"},
                {"name": "TEDPolicy",
                 "epochs": 200},
                {"name": "RulePolicy", 'core_fallback_action_name': 'action_say_bye',
                 'core_fallback_threshold': 0.3}]
        }
        assert config == expected

    def test_save_component_properties_nlu_fallback_only(self):
        nlu_fallback = {"nlu_confidence_threshold": 60}
        processor = MongoProcessor()
        processor.save_component_properties(nlu_fallback, 'test_nlu_fallback_only', 'test')
        config = processor.load_config('test_nlu_fallback_only')
        nlu_fallback = next((comp for comp in config['pipeline'] if comp["name"] == "FallbackClassifier"), None)
        assert nlu_fallback['name'] == 'FallbackClassifier'
        assert nlu_fallback['threshold'] == 0.6
        rule_policy = next((comp for comp in config['policies'] if comp["name"] == "RulePolicy"), None)
        assert len(rule_policy) == 3
        expected = {
            "language": "en",
            "pipeline": [
                {"name": "WhitespaceTokenizer"},
                {"name": "RegexFeaturizer"},
                {"name": "LexicalSyntacticFeaturizer"},
                {"name": "CountVectorsFeaturizer"},
                {"name": "CountVectorsFeaturizer",
                 "analyzer": "char_wb",
                 "min_ngram": 1,
                 "max_ngram": 4},
                {"name": "DIETClassifier",
                 "epochs": 100},
                {"name": "FallbackClassifier",
                 "threshold": 0.6},
                {"name": "EntitySynonymMapper"},
                {"name": "ResponseSelector",
                 "epochs": 100}
            ],
            "policies": [
                {"name": "MemoizationPolicy"},
                {"name": "TEDPolicy",
                 "epochs": 200},
                {"name": "RulePolicy", 'core_fallback_action_name': 'action_default_fallback',
                 'core_fallback_threshold': 0.3}]
        }
        assert config == expected

    def test_save_component_properties_all_nlu_fallback_update_threshold(self):
        nlu_fallback = {"nlu_confidence_threshold": 70}
        processor = MongoProcessor()
        processor.save_component_properties(nlu_fallback, 'test_nlu_fallback_only', 'test')
        config = processor.load_config('test_nlu_fallback_only')
        nlu_fallback = next((comp for comp in config['pipeline'] if comp["name"] == "FallbackClassifier"), None)
        assert nlu_fallback['name'] == 'FallbackClassifier'
        assert nlu_fallback['threshold'] == 0.7
        rule_policy = next((comp for comp in config['policies'] if comp["name"] == "RulePolicy"), None)
        assert len(rule_policy) == 3

    def test_save_component_properties_action_fallback_only(self):
        nlu_fallback = {'action_fallback': 'action_say_bye'}
        Actions(name='action_say_bye', bot='test_action_fallback_only', user='test').save()
        processor = MongoProcessor()
        processor.save_component_properties(nlu_fallback, 'test_action_fallback_only', 'test')
        config = processor.load_config('test_action_fallback_only')
        assert next((comp for comp in config['pipeline'] if comp["name"] == "FallbackClassifier"), None)
        rule_policy = next((comp for comp in config['policies'] if comp["name"] == "RulePolicy"), None)
        assert len(rule_policy) == 3
        assert rule_policy['core_fallback_action_name'] == 'action_say_bye'
        assert rule_policy['core_fallback_threshold'] == 0.3
        expected = {
            "language": "en",
            "pipeline": [
                {"name": "WhitespaceTokenizer"},
                {"name": "RegexFeaturizer"},
                {"name": "LexicalSyntacticFeaturizer"},
                {"name": "CountVectorsFeaturizer"},
                {"name": "CountVectorsFeaturizer",
                 "analyzer": "char_wb",
                 "min_ngram": 1,
                 "max_ngram": 4},
                {"name": "DIETClassifier",
                 "epochs": 100},
                {'name': 'FallbackClassifier', 'threshold': 0.7},
                {"name": "EntitySynonymMapper"},
                {"name": "ResponseSelector",
                 "epochs": 100}
            ],
            "policies": [
                {"name": "MemoizationPolicy"},
                {"name": "TEDPolicy",
                 "epochs": 200},
                {"core_fallback_action_name": "action_say_bye",
                 "core_fallback_threshold": 0.3,
                 "name": "RulePolicy"}]
        }
        assert config == expected

    def test_save_component_properties_all_action_fallback_update(self):
        nlu_fallback = {'action_fallback': 'action_say_bye_bye'}
        Actions(name='action_say_bye_bye', bot='test_action_fallback_only', user='test').save()
        processor = MongoProcessor()
        processor.save_component_properties(nlu_fallback, 'test_action_fallback_only', 'test')
        config = processor.load_config('test_action_fallback_only')
        assert next((comp for comp in config['pipeline'] if comp["name"] == "FallbackClassifier"), None)
        rule_policy = next((comp for comp in config['policies'] if comp["name"] == "RulePolicy"), None)
        assert len(rule_policy) == 3
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
        assert len(rule_policy) == 3
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
        assert len(rule_policy) == 3
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
        assert len(rule_policy) == 3
        assert rule_policy['core_fallback_action_name'] == 'action_default_fallback'
        assert rule_policy['core_fallback_threshold'] == 0.3


# pylint: disable=R0201
class TestAgentProcessor:

    def test_get_agent(self, monkeypatch):
        def mongo_store(*arge, **kwargs):
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
    @pytest.fixture(autouse=True)
    def init_connection(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_evironment()
        connect(host=Utility.environment['database']["url"])

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

    def test_add_http_action_config(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        http_url = 'http://www.google.com'
        action = 'test_action'
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
            http_params_list=http_params_list
        )
        processor.add_http_action_config(http_action_config.dict(), user, bot)
        actual_http_action = HttpActionConfig.objects(action_name=action, bot=bot, user=user, status=True).get(
            action_name__iexact=action)
        assert actual_http_action is not None
        assert actual_http_action['action_name'] == action
        assert actual_http_action['http_url'] == http_url
        assert actual_http_action['auth_token'] == auth_token
        assert actual_http_action['response'] == response
        assert actual_http_action['request_method'] == request_method
        assert actual_http_action['params_list'] is not None
        assert actual_http_action['params_list'][0]['key'] == "param1"
        assert actual_http_action['params_list'][0]['value'] == "param1"
        assert actual_http_action['params_list'][0]['parameter_type'] == "slot"
        assert actual_http_action['params_list'][1]['key'] == "param2"
        assert actual_http_action['params_list'][1]['value'] == "value2"
        assert actual_http_action['params_list'][1]['parameter_type'] == "value"
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
            http_params_list=http_params_list
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
        http_dict['http_params_list'][0]['key'] = None
        with pytest.raises(ValidationError, match="key in http action parameters cannot be empty"):
            processor.add_http_action_config(http_dict, user, bot)
        http_dict['http_params_list'][0]['value'] = None
        http_dict['http_params_list'][0]['key'] = "param1"
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
        auth_token = "bearer dhdshghfhzxfgadfhdhdhshdshsdfhsdhsdhnxngfgxngf"
        user = 'test_user'
        response = "json"
        request_method = 'GET'
        params = [HttpActionParameters(key="key", value="value", parameter_type="slot")]

        HttpActionConfig(
            auth_token=auth_token,
            action_name=action,
            response=response,
            http_url=http_url,
            request_method=request_method,
            bot=bot,
            user=user
        ).save().to_mongo().to_dict()["_id"].__str__()

        http_action_config = HttpActionConfigRequest(
            auth_token=auth_token,
            action_name=action,
            response=response,
            http_url=http_url,
            request_method=request_method,
            http_params_list=params
        )
        try:
            processor.add_http_action_config(http_action_config.dict(), user, bot)
            assert False
        except AppException as ex:
            assert str(ex).__contains__("Action exists")

    def test_delete_http_action_config(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        http_url = 'http://www.google.com'
        action = 'test_delete_http_action_config'
        auth_token = "bearer dhdshghfhzxfgadfhdhdhshdshsdfhsdhsdhnxngfgxngf"
        user = 'test_user'
        response = "json"
        request_method = 'GET'
        HttpActionConfig(
            auth_token=auth_token,
            action_name=action,
            response=response,
            http_url=http_url,
            request_method=request_method,
            bot=bot,
            user=user
        ).save().to_mongo()
        processor.delete_http_action_config(action=action, user=user, bot=bot)
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
        auth_token = "bearer dhdshghfhzxfgadfhdhdhshdshsdfhsdhsdhnxngfgxngf"
        response = "json"
        request_method = 'GET'
        HttpActionConfig(
            auth_token=auth_token,
            action_name=action,
            response=response,
            http_url=http_url,
            request_method=request_method,
            bot=bot,
            user=user
        ).save().to_mongo()
        try:
            processor.delete_http_action_config(action="test_delete_http_action_config_non_existing_non_existing",
                                                user=user, bot=bot)
            assert False
        except AppException as e:
            assert str(e).__contains__(
                'No HTTP action found for bot test_bot and action test_delete_http_action_config_non_existing_non_existing')

    def test_get_http_action_config(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        http_url = 'http://www.google.com'
        action = 'test_get_http_action_config1'
        auth_token = "bearer dhdshghfhzxfgadfhdhdhshdshsdfhsdhsdhnxngfgxngf"
        user = 'test_user'
        response = "json"
        request_method = 'GET'
        HttpActionConfig(
            auth_token=auth_token,
            action_name=action,
            response=response,
            http_url=http_url,
            request_method=request_method,
            bot=bot,
            user=user
        ).save().to_mongo()

        actual_test_user1 = processor.get_http_action_config(bot=bot, action_name=action)
        assert actual_test_user1 is not None
        assert actual_test_user1['auth_token'] == auth_token
        assert actual_test_user1['action_name'] == action
        assert actual_test_user1['response'] == response
        assert actual_test_user1['http_url'] == http_url
        assert actual_test_user1['request_method'] == request_method

        http_url1 = 'http://www.google.com'
        action1 = 'test_get_http_action_config'
        auth_token1 = "bearer ndgxffffgfhfgkjfjfjfcjjjjjjjj"
        user1 = 'test_user1'
        response1 = ""
        request_method1 = 'POST'
        HttpActionConfig(
            auth_token=auth_token1,
            action_name=action1,
            response=response1,
            http_url=http_url1,
            request_method=request_method1,
            bot=bot,
            user=user1
        ).save().to_mongo()

        actual_test_user2 = processor.get_http_action_config(bot=bot, action_name=action)
        assert actual_test_user2 is not None
        assert actual_test_user2['auth_token'] == auth_token
        assert actual_test_user2['action_name'] == action
        assert actual_test_user2['response'] == response
        assert actual_test_user2['http_url'] == http_url
        assert actual_test_user2['request_method'] == request_method

    def test_get_http_action_config_non_existing(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        http_url = 'http://www.google.com'
        action = 'test_action'
        auth_token = "bearer dhdshghfhzxfgadfhdhdhshdshsdfhsdhsdhnxngfgxngf"
        user = 'test_user'
        response = "json"
        request_method = 'GET'
        HttpActionConfig(
            auth_token=auth_token,
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
            http_params_list=http_params_list
        )
        http_config_id = processor.add_http_action_config(http_action_config.dict(), user, bot)
        assert http_config_id is not None
        http_url = 'http://www.alphabet.com'
        auth_token = ""
        response = "string"
        request_method = 'POST'
        http_params_list = [
            HttpActionParameters(key="param3", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param4", value="value2", parameter_type="value")]
        http_action_config = HttpActionConfigRequest(
            auth_token=auth_token,
            action_name=action,
            response=response,
            http_url=http_url,
            request_method=request_method,
            http_params_list=http_params_list
        )
        processor.update_http_config(http_action_config, user, bot)

        actual_http_action = HttpActionConfig.objects(action_name=action, bot=bot, status=True).get(
            action_name__iexact=action)
        assert actual_http_action is not None
        assert actual_http_action['action_name'] == action
        assert actual_http_action['http_url'] == http_url
        assert actual_http_action['auth_token'] == auth_token
        assert actual_http_action['response'] == response
        assert actual_http_action['request_method'] == request_method
        assert actual_http_action['params_list'] is not None
        assert actual_http_action['params_list'][0]['key'] == "param3"
        assert actual_http_action['params_list'][0]['value'] == "param1"
        assert actual_http_action['params_list'][0]['parameter_type'] == "slot"
        assert actual_http_action['params_list'][1]['key'] == "param4"
        assert actual_http_action['params_list'][1]['value'] == "value2"
        assert actual_http_action['params_list'][1]['parameter_type'] == "value"

    def test_update_http_config_invalid_action(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        http_url = 'http://www.google.com'
        action = 'test_update_http_config_invalid_action'
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
            http_params_list=http_params_list
        )
        http_config_id = processor.add_http_action_config(http_action_config.dict(), user, bot)
        assert http_config_id is not None
        bot = 'test_bot'
        http_url = 'http://www.alphabet.com'
        action = 'test_update_http_config_invalid'
        auth_token = "bearer dhdshghfhzxfgadfhdhdhshdshsdfhsdhsdhnxngfgxngf"
        user = 'test_user'
        response = "string"
        request_method = 'POST'
        http_params_list = [
            HttpActionParameters(key="param3", value="param1", parameter_type="slot"),
            HttpActionParameters(key="param4", value="value2", parameter_type="value")]
        http_action_config = HttpActionConfigRequest(
            auth_token=auth_token,
            action_name=action,
            response=response,
            http_url=http_url,
            request_method=request_method,
            http_params_list=http_params_list
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
        story_dict = {'name': "story without action", 'steps': steps, 'type': 'STORY'}
        processor.add_complex_story(story_dict, "test_without_http", "testUser")
        story = Stories.objects(block_name="story without action", bot="test_without_http").get()
        assert len(story.events) == 5
        actions = processor.list_actions("test_without_http")
        assert actions == []

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
        story_dict = {'name': "story with action", 'steps': steps, 'type': 'STORY'}
        processor.add_complex_story(story_dict, "test_with_action", "testUser")
        story = Stories.objects(block_name="story with action", bot="test_with_action").get()
        assert len(story.events) == 6
        actions = processor.list_actions("test_with_action")
        assert actions == ["action_check"]

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
        story_dict = {'name': "story with action", 'steps': steps, 'type': 'STORY'}
        processor.add_complex_story(story_dict, "tests", "testUser")
        story = Stories.objects(block_name="story with action", bot="tests").get()
        assert len(story.events) == 6
        actions = processor.list_actions("tests")
        assert actions == []

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
            story_dict = {'name': "story with action", 'steps': steps, 'type': 'STORY'}
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
            story_dict = {'name': "Story with action", 'steps': steps, 'type': 'STORY'}
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
            story_dict = {'name': None, 'steps': steps, 'type': 'STORY'}
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
            story_dict = {'name': "", 'steps': steps, 'type': 'STORY'}
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
            story_dict = {'name': " ", 'steps': steps, 'type': 'STORY'}
            processor.add_complex_story(story_dict, "tests", "testUser")

    def test_add_empty_complex_story_event(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            story_dict = {'name': "empty path", 'steps': [], 'type': 'STORY'}
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
            story_dict = {'name': "story duplicate using events", 'steps': steps, 'type': 'STORY'}
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
        rule_dict = {'name': "rule with invalid events", 'steps': steps, 'type': 'STORY'}
        with pytest.raises(ValidationError, match="First event should be an user"):
            processor.add_complex_story(rule_dict, "tests", "testUser")

        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
        ]
        rule_dict = {'name': "rule with invalid events", 'steps': steps, 'type': 'STORY'}
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
        rule_dict = {'name': "rule with invalid events", 'steps': steps, 'type': 'STORY'}
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
        story_dict = {'name': "story with action", 'steps': steps, 'type': 'STORY'}
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
            story_dict = {'name': "story with same events", 'steps': steps, 'type': 'STORY'}
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
        story_dict = {'name': "STory with action", 'steps': steps, 'type': 'STORY'}
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
            story_dict = {'name': "non existing story", 'steps': steps, 'type': 'STORY'}
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
        rule_dict = {'name': "story with action", 'steps': steps, 'type': 'STORY'}
        with pytest.raises(ValidationError, match="First event should be an user"):
            processor.update_complex_story(rule_dict, "tests", "testUser")

        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
        ]
        rule_dict = {'name': "story with action", 'steps': steps, 'type': 'STORY'}
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
        rule_dict = {'name': "story with action", 'steps': steps, 'type': 'STORY'}
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
            story_dict = {'name': None, 'steps': events, 'type': 'STORY'}
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
            story_dict = {'name': "", 'steps': events, 'type': 'STORY'}
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
            story_dict = {'name': " ", 'steps': events, 'type': 'STORY'}
            processor.update_complex_story(story_dict, "tests", "testUser")

    def test_update_empty_complex_story_event(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            story_dict = {'name': "empty path", 'steps': [], 'type': 'STORY'}
            processor.update_complex_story(story_dict, "tests", "testUser")

    def test_list_actions(self):
        processor = MongoProcessor()
        processor.add_action("reset_slot", "test_upload_and_save", "test_user")
        actions = processor.list_actions("test_upload_and_save")
        assert actions == ['reset_slot']

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
        story_dict = {"name": "story2", 'steps': steps, 'type': 'STORY'}
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
            auth_token="",
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


class TestTrainingDataProcessor:

    @pytest.fixture(autouse=True)
    def init_connection(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_evironment()
        connect(host=Utility.environment["database"]['url'])

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
        print(status.to_mongo().to_dict())
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
        print(status.to_mongo().to_dict())
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

    def test_add_rule(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
        ]
        rule_dict = {'name': "rule with action", 'steps': steps, 'type': 'RULE'}
        processor.add_complex_story(rule_dict, "tests", "testUser")
        story = Rules.objects(block_name="rule with action", bot="tests").get()
        assert len(story.events) == 3
        actions = processor.list_actions("tests")
        assert actions == []

    def test_add_duplicate_rule(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
        ]
        with pytest.raises(Exception):
            rule_dict = {'name': "rule with action", 'steps': steps, 'type': 'RULE'}
            processor.add_complex_story(rule_dict, "tests", "testUser")


    def test_add_rule_invalid_type(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
        ]
        with pytest.raises(Exception):
            rule_dict = {'name': "rule with action", 'steps': steps, 'type': 'TEST'}
            processor.add_complex_story(rule_dict, "tests", "testUser")

    def test_add_duplicate_case_insensitive_rule(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
        ]
        with pytest.raises(Exception):
            rule_dict = {'name': "RUle with action", 'steps': steps, 'type': 'RULE'}
            processor.add_complex_story(rule_dict, "tests", "testUser")

    def test_add_none_rule(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greeting", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
        ]
        with pytest.raises(AppException):
            rule_dict = {'name': None, 'steps': steps, 'type': 'RULE'}
            processor.add_complex_story(rule_dict, "tests", "testUser")

    def test_add_empty_rule(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greeting", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
        ]
        with pytest.raises(AppException):
            rule_dict = {'name': "", 'steps': steps, 'type': 'RULE'}
            processor.add_complex_story(rule_dict, "tests", "testUser")

    def test_add_blank_rule_name(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greeting", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
        ]
        with pytest.raises(AppException):
            rule_dict = {'name': " ", 'steps': steps, 'type': 'rule'}
            processor.add_complex_story(rule_dict, "tests", "testUser")

    def test_add_empty_rule_event(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            rule_dict = {'name': "empty path", 'steps': [], 'type': 'RULE'}
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
        rule_dict = {'name': "rule with multiple intents", 'steps': steps, 'type': 'RULE'}
        with pytest.raises(ValidationError, match="Found rules 'rule with multiple intents' that contain more than user event.\nPlease use stories for this case"):
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


    def test_update_rule(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
        ]
        rule_dict = {'name': "rule with action", 'steps': steps, 'type': 'RULE'}
        processor.update_complex_story(rule_dict, "tests", "testUser")
        rule = Rules.objects(block_name="rule with action", bot="tests").get()
        assert rule.events[1].name == "utter_nonsense"

    def test_case_insensitive_update_rule(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "utter_greet", "type": "BOT"},
        ]
        rule_dict = {'name': "RUle with action", 'steps': steps, 'type': 'RULE'}
        processor.update_complex_story(rule_dict, "tests", "testUser")
        rule = Rules.objects(block_name="rule with action", bot="tests").get()
        assert rule.events[3].name == "utter_greet"

    def test_update_non_existing_rule(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
        ]
        with pytest.raises(Exception):
            rule_dict = {'name': "non existing story", 'steps': steps, 'type': 'RULE'}
            processor.update_complex_story(rule_dict, "tests", "testUser")

    def test_update_rule_name(self):
        processor = MongoProcessor()
        events = [
            {"name": "greeting", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
        ]
        with pytest.raises(AppException):
            rule_dict = {'name': None, 'steps': events, 'type': 'RULE'}
            processor.update_complex_story(rule_dict, "tests", "testUser")

    def test_fetch_stories_with_rules(self):
        processor = MongoProcessor()
        data = list(processor.get_stories("tests"))
        assert all( item['type'] in ['STORY', 'RULE'] for item in data)
        assert len(data) == 9

    def test_update_empty_rule_name(self):
        processor = MongoProcessor()
        events = [
            {"name": "greeting", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
        ]
        with pytest.raises(AppException):
            rule_dict = {'name': "", 'steps': events, 'type': 'RULE'}
            processor.update_complex_story(rule_dict, "tests", "testUser")

    def test_update_blank_rule_name(self):
        processor = MongoProcessor()
        events = [
            {"name": "greeting", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
        ]
        with pytest.raises(AppException):
            rule_dict = {'name': " ", 'steps': events, 'type': 'RULE'}
            processor.update_complex_story(rule_dict, "tests", "testUser")

    def test_update_empty_rule_event(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            rule_dict = {'name': "empty path", 'steps': [], 'type': 'RULE'}
            processor.update_complex_story(rule_dict, "tests", "testUser")

    def test_update_rule_invalid_type(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
        ]
        with pytest.raises(AppException):
            rule_dict = {'name': "rule with action", 'steps': steps, 'type': 'TEST'}
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
        with pytest.raises(ValidationError, match="Found rules 'rule with action' that contain more than user event.\nPlease use stories for this case"):
            rule_dict = {'name': "rule with action", 'steps': events, 'type': 'RULE'}
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
            rule_dict = {'name': "rule with action", 'steps': events, 'type': 'RULE'}
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