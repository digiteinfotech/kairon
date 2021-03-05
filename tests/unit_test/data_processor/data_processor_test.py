import os
from typing import List

import pytest
import responses
from mongoengine import connect, DoesNotExist
from mongoengine.errors import ValidationError
from rasa.core.agent import Agent
from rasa.shared.core.training_data.structures import StoryGraph
from rasa.shared.importers.rasa import Domain
from rasa.shared.nlu.training_data.training_data import TrainingData

from kairon.action_server.data_objects import HttpActionConfig
from kairon.api import models
from kairon.api.models import StoryEventType, HttpActionParameters, HttpActionConfigRequest, StoryEventRequest
from kairon.data_processor.constant import UTTERANCE_TYPE, CUSTOM_ACTIONS, TRAINING_DATA_GENERATOR_STATUS
from kairon.data_processor.data_objects import (TrainingExamples,
                                                Slots,
                                                Entities,
                                                Intents,
                                                Actions,
                                                Responses,
                                                ModelTraining, StoryEvents, Stories, ResponseCustom, ResponseText,
                                                TrainingDataGenerator, TrainingDataGeneratorResponse,
                                                TrainingExamplesTrainingDataGenerator
                                                )
from kairon.data_processor.processor import MongoProcessor, AgentProcessor, ModelProcessor, \
    TrainingDataGenerationProcessor
from kairon.exceptions import AppException
from kairon.train import train_model_for_bot, start_training, train_model_from_mongo
from kairon.utils import Utility


class TestMongoProcessor:

    @pytest.fixture(autouse=True)
    def init_connection(self):
        os.environ["system_file"] = "./tests/testing_d" \
                                    "ata/system.yaml"
        Utility.load_evironment()
        connect(host=Utility.environment["database"]['url'])

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
        assert domain.slots.__len__() == 8
        assert domain.templates.keys().__len__() == 25
        assert domain.entities.__len__() == 8
        assert domain.form_names.__len__() == 2
        assert domain.user_actions.__len__() == 38
        assert domain.intents.__len__() == 29
        assert not Utility.check_empty_string(
            domain.templates["utter_cheer_up"][0]["image"]
        )
        assert domain.templates["utter_did_that_help"][0]["buttons"].__len__() == 2
        assert domain.templates["utter_offer_help"][0]["custom"]
        assert domain.slots[0].type_name == "unfeaturized"

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
        assert domain.slots.__len__() == 8
        assert domain.templates.keys().__len__() == 25
        assert domain.entities.__len__() == 8
        assert domain.form_names.__len__() == 2
        assert domain.user_actions.__len__() == 38
        assert domain.intents.__len__() == 29
        assert not Utility.check_empty_string(
            domain.templates["utter_cheer_up"][0]["image"]
        )
        assert domain.templates["utter_did_that_help"][0]["buttons"].__len__() == 2
        assert domain.templates["utter_offer_help"][0]["custom"]
        assert domain.slots[0].type_name == "unfeaturized"

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
        assert domain.slots.__len__() == 0
        assert domain.templates.keys().__len__() == 9
        assert domain.entities.__len__() == 0
        assert domain.form_names.__len__() == 0
        assert domain.user_actions.__len__() == 9
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
        assert slots.__len__() == 1
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
        assert slots.__len__() == 2
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
        assert slots.__len__() == 3
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

    def test_add_entity_duplicate_caseinsentive(self):
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
        assert processor.add_action("utter_priority", "tests", "testUser")
        action = Actions.objects(bot="tests").get(name="utter_priority")
        assert action.name == "utter_priority"

    def test_get_actions(self):
        processor = MongoProcessor()
        expected = [
            "utter_greet",
            "utter_cheer_up",
            "utter_happy",
            "utter_goodbye",
            "utter_priority",
            "utter_did_that_help",
            "utter_iamabot",
            'utter_feedback',
            "utter_bad_feedback",
            "utter_good_feedback"
        ]
        actual = processor.get_actions("tests")
        assert actual.__len__() == expected.__len__()
        assert all(item["name"] in expected for item in actual)

    def test_add_action_duplicate(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            assert processor.add_action("utter_priority", "tests", "testUser") is None

    def test_add_action_duplicate_caseinsentive(self):
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

    def test_add_story(self):
        processor = MongoProcessor()
        events = [
            {"name": "greet", "type": "user"},
            {"name": "utter_greet", "type": "action"},
            {"name": "mood_great", "type": "user"},
            {"name": "utter_greet", "type": "action"},
        ]
        processor.add_story("happy path", events, "tests", "testUser")

    def test_add_duplicate_story(self):
        processor = MongoProcessor()
        events = [
            {"name": "greet", "type": "user"},
            {"name": "utter_greet", "type": "action"},
            {"name": "mood_great", "type": "user"},
            {"name": "utter_greet", "type": "action"},
        ]
        with pytest.raises(Exception):
            processor.add_story("happy path", events, "tests", "testUser")

    def test_add_none_story_name(self):
        processor = MongoProcessor()
        events = [
            {"name": "greeting", "type": "user"},
            {"name": "utter_greet", "type": "action"},
            {"name": "mood_great", "type": "user"},
            {"name": "utter_greet", "type": "action"},
        ]
        with pytest.raises(AppException):
            processor.add_story(None, events, "tests", "testUser")

    def test_add_empty_story_name(self):
        processor = MongoProcessor()
        events = [
            {"name": "greeting", "type": "user"},
            {"name": "utter_greet", "type": "action"},
            {"name": "mood_great", "type": "user"},
            {"name": "utter_greet", "type": "action"},
        ]
        with pytest.raises(AppException):
            processor.add_story("", events, "tests", "testUser")

    def test_add_blank_story_name(self):
        processor = MongoProcessor()
        events = [
            {"name": "greeting", "type": "user"},
            {"name": "utter_greet", "type": "action"},
            {"name": "mood_great", "type": "user"},
            {"name": "utter_greet", "type": "action"},
        ]
        with pytest.raises(AppException):
            processor.add_story("  ", events, "tests", "testUser")

    def test_add_empty_story_event(self):
        processor = MongoProcessor()
        with pytest.raises(ValidationError):
            processor.add_story("happy path", [], "tests", "testUser")

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

    async def test_train_model(self):
        model = train_model_for_bot("tests")
        assert model

    @pytest.mark.asyncio
    async def test_train_model_empty_data(self):
        with pytest.raises(AppException):
            model = await (train_model_from_mongo("test"))
            assert model

    def test_start_training_done(self, monkeypatch):
        def mongo_store(*arge, **kwargs):
            return None

        monkeypatch.setattr(Utility, "get_local_mongo_store", mongo_store)
        model_path = start_training("tests", "testUser")
        assert model_path
        model_training = ModelTraining.objects(bot="tests", status="Done")
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
        stories = list(processor.get_stories("tests", "testUser"))
        assert stories.__len__() == 8
        assert stories[0]['name'] == 'happy path'
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

    def test_edit_training_example_with_entities(self):
        processor = MongoProcessor()
        examples = list(processor.get_training_examples("greet", "tests"))
        processor.edit_training_example(examples[0]["_id"], example="[Meghalaya](Location) India", intent="greet",
                                        bot="tests", user="testUser")
        examples = list(processor.get_training_examples("greet", "tests"))
        assert any(example['text'] == "Meghalaya India" for example in examples)

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

    def test_edit_responses(self):
        processor = MongoProcessor()
        responses = list(processor.get_response("utter_happy", "tests"))
        processor.edit_text_response(responses[0]["_id"], "Great!", name="utter_happy", bot="tests", user="testUser")
        responses = list(processor.get_response("utter_happy", "tests"))
        assert any(response['value']['text'] == "Great!" for response in responses if "text" in response['value'])

    @responses.activate
    def test_start_training_done_using_event(self, monkeypatch):
        responses.add(
            responses.POST,
            "http://localhost/train",
            status=200
        )
        monkeypatch.setitem(Utility.environment['model']['train'], "event_url", "http://localhost/train")
        model_path = start_training("tests", "testUser")
        assert model_path is None

    @responses.activate
    def test_start_training_done_reload_event(self, monkeypatch):
        responses.add(
            responses.GET,
            "http://localhost/api/bot/model/reload",
            json={"message": "Reloading Model!"},
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

    def test_delete_response_attached_to_story(self):
        processor = MongoProcessor()
        utterance = "test_delete_response_attached_to_story"
        bot = "testBot"
        user = "testUser"
        utter_intentA_1_id = processor.add_response({"text": "demo_response"}, utterance, bot, user)
        events = [
            {"name": "greet", "type": "user"},
            {"name": "utter_greet", "type": "action"},
            {"name": "mood_great", "type": "user"},
            {"name": utterance, "type": "action"},
        ]
        processor.add_story("test path", events, bot, user)
        with pytest.raises(AppException):
            processor.delete_response(utter_intentA_1_id, bot, user)

    def test_delete_utterance(self):
        processor = MongoProcessor()
        utterance = "test_delete_utterance"
        bot = "testBot"
        user = "testUser"
        processor.add_response({"text": "demo_response1"}, utterance, bot, user)
        processor.delete_utterance(utterance, bot, user)

    def test_delete_utterance_attached_to_story(self):
        processor = MongoProcessor()
        utterance = "test_delete_utterance_attached_to_story"
        bot = "testBot"
        user = "testUser"
        processor.add_response({"text": "demo_response2"}, utterance, bot, user)
        events = [
            {"name": "greet", "type": "user"},
            {"name": "utter_greet", "type": "action"},
            {"name": "mood_great", "type": "user"},
            {"name": utterance, "type": "action"},
        ]
        processor.add_story("test_delete_utterance", events, bot, user)
        with pytest.raises(Exception):
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
                      raise_exception=False)
        slot = Slots.objects(name__iexact='bot',bot=bot, user=user).get()
        assert slot['name'] == 'bot'
        assert slot['type'] == 'unfeaturized'
        assert slot['initial_value'] is None
        assert slot['influence_conversation']

        processor.add_slot({"name": "bot", "type": "any", "initial_value": bot, "influence_conversation": False}, bot,
                           user, raise_exception=False)
        slot = Slots.objects(name__iexact='bot', bot=bot, user=user).get()
        assert slot['name'] == 'bot'
        assert slot['type'] == 'any'
        assert slot['initial_value'] == bot
        assert not slot['influence_conversation']

        with pytest.raises(AppException):
            msg = processor.add_slot({"name": "bot", "type": "any", "initial_value": bot, "influence_conversation": False}, bot, user)
            assert msg ==  'Slot exists'


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
        assert model_training.count() == 3
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
        monkeypatch.setitem(Utility.environment['model']['train'], "limit_per_day", 6)
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

    def test_delete_empty_Intent(self):
        processor = MongoProcessor()
        with pytest.raises(AssertionError):
            processor.delete_intent("", "tests", "testUser", is_integration=False)

    def test_delete_valid_intent(self):
        processor = MongoProcessor()
        processor.add_intent("TestingDelGreeting", "tests", "testUser", is_integration=False)
        processor.delete_intent("TestingDelGreeting", "tests", "testUser", is_integration=False)

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

    def test_delete_intent_no_trainingExamples(self):
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
        processor.add_training_example(["hello","hi"],"TestingDelGreeting","tests", "testUser", is_integration=False)
        processor.delete_intent("TestingDelGreeting", "tests", "testUser", is_integration=False)
        actual = processor.get_intents("tests")
        assert not any(intent['name'] == 'TestingDelGreeting' for intent in actual)
        actual = list(processor.get_training_examples('TestingDelGreeting', "tests"))
        assert len(actual) == 0

    def test_prepare_and_add_story(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        action = 'test_action'
        user = 'test_user'
        intent = "greet_http_action"
        processor.prepare_and_add_story(story=action, intent=intent, bot=bot, user=user)
        story = Stories.objects(block_name=action, bot=bot, status=True).get(block_name__iexact=action)

        assert story['events'] is not None
        assert story['events'][0] is not None
        assert story['events'][0]['name'] == intent
        assert story['events'][0]['type'] == StoryEventType.user
        assert story['events'][1]['name'] == "bot"
        assert story['events'][1]['type'] == StoryEventType.slot
        assert story['events'][1]['value'] == bot
        assert story['events'][2]['name'] == "http_action_config"
        assert story['events'][2]['type'] == StoryEventType.slot
        assert story['events'][2]['value'] == action
        assert story['events'][3]['name'] == "kairon_http_action"
        assert story['events'][3]['type'] == StoryEventType.action

    def test_prepare_and_add_story_no_bot(self):
        processor = MongoProcessor()
        bot = None
        action = 'test_action'
        user = 'test_user'
        event_name = "greet_http_action"
        intent = "test"
        try:
            processor.prepare_and_add_story(story=action, intent=intent, bot=bot, user=user)
            assert False
        except AppException as e:
            assert str(e).__contains__("Story, bot and user are required")

    def test_prepare_and_add_story_no_user(self):
        processor = MongoProcessor()
        bot = "bot"
        action = 'test_action'
        user = None
        intent = "greet_http_action"
        try:
            processor.prepare_and_add_story(story=action, intent=intent, bot=bot, user=user)
            assert False
        except AppException as e:
            assert str(e).__contains__("Story, bot and user are required")

    def test_prepare_and_add_story_no_story(self):
        processor = MongoProcessor()
        bot = "bot"
        story = None
        user = "test_user"
        event_name = "greet_http_action"
        intent = "test"
        try:
            processor.prepare_and_add_story(story=story, intent=intent, bot=bot, user=user)
            assert False
        except AppException as e:
            assert str(e).__contains__("Story, bot and user are required")

    def test_delete_story(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        action = 'test_action'
        user = 'test_user'
        event_name = "greet_http_action"
        story_event = [StoryEvents(name=event_name, type="user")]
        Stories(
            block_name=action,
            events=story_event,
            bot=bot,
            user=user,
        ).save().to_mongo()
        processor.delete_story(story=action, user=user, bot=bot)
        try:
            Stories.objects(bot=bot, status=True).get(block_name__iexact=action)
            assert False
        except DoesNotExist:
            assert True

    def test_delete_story_non_existing(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        action = 'test_action'
        user = 'test_user'
        event_name = "greet_http_action"
        story_event = [StoryEvents(name=event_name, type="user")]
        Stories(
            block_name=action,
            events=story_event,
            bot=bot,
            user=user,
        ).save().to_mongo()
        try:
            processor.delete_story(story='test_action1', user=user, bot=bot)
        except AppException:
            assert True

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
        processor.add_http_action_config(http_action_config, user, bot)
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
        assert Utility.is_exist(Slots, raise_error=False, name__iexact="bot")
        assert Utility.is_exist(Actions, raise_error=False, name__iexact=CUSTOM_ACTIONS.HTTP_ACTION_NAME)

    def test_list_http_action(self):
        processor = MongoProcessor()
        bot = 'test_bot'
        user = 'test_user'
        actions = processor.list_http_actions(bot, user)
        assert len(actions) == 1

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
            processor.add_http_action_config(http_action_config, user, bot)
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
        action = 'test_get_http_action_config'
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

        actual_test_user1 = processor.get_http_action_config(bot=bot, user="test_user", action_name=action)
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

        actual_test_user2 = processor.get_http_action_config(bot=bot, user="test_user", action_name=action)
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
            processor.get_http_action_config(bot=bot, user="test_user", action_name="action")
            assert False
        except AppException as e:
            assert str(e) == "No HTTP action found for bot test_bot and action action"

    def test_update_story_non_existing(self):
        processor = MongoProcessor()
        user = "test_user"
        story = "new_story"
        bot = "bot"
        story_event = [StoryEvents(name="greet", type="user")]
        intent = "greet_again"
        Stories(
            block_name=story,
            bot=bot,
            user=user,
            events=story_event
        ).save(validate=False).to_mongo()
        try:
            processor.update_story(story="story", intent=intent, user=user, bot=bot)
        except AppException as ex:
            assert str(ex) == 'Story story does not exists'

    def test_update_story(self):
        processor = MongoProcessor()
        user = "test_user"
        story = "test_update_story"
        bot = "bot"
        story_event = [StoryEvents(name="greet", type="user")]
        intent = "slap"
        Stories(
            block_name=story,
            bot=bot,
            user=user,
            events=story_event
        ).save(validate=False).to_mongo()
        processor.update_story(story=story, intent=intent, user=user, bot=bot)
        updated = Stories.objects(block_name=story, bot=bot, user=user, status=True).get(block_name__iexact=story)
        assert updated is not None
        assert updated.events[0].name == intent
        assert updated.events[0].type == "user"
        assert updated.events[0].value is None

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
        http_config_id = processor.add_http_action_config(http_action_config, user, bot)
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

        actual_http_action = HttpActionConfig.objects(action_name=action, bot=bot, user=user, status=True).get(
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
        http_config_id = processor.add_http_action_config(http_action_config, user, bot)
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
        processor.add_complex_story("story with action", steps, "tests", "testUser")
        story = Stories.objects(block_name="story with action").get()
        assert len(story.events) == 6

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
            processor.add_complex_story("story with action", steps, "tests", "testUser")

    def test_add_none_complex_story_name(self):
        processor = MongoProcessor()
        events = [
            {"name": "greeting", "type": "user"},
            {"name": "utter_greet", "type": "action"},
            {"name": "mood_great", "type": "user"},
            {"name": "utter_greet", "type": "action"},
        ]
        with pytest.raises(AppException):
            processor.add_complex_story(None, events, "tests", "testUser")

    def test_add_empty_complex_story_name(self):
        processor = MongoProcessor()
        events = [
            {"name": "greeting", "type": "user"},
            {"name": "utter_greet", "type": "action"},
            {"name": "mood_great", "type": "user"},
            {"name": "utter_greet", "type": "action"},
        ]
        with pytest.raises(AppException):
            processor.add_complex_story("", events, "tests", "testUser")

    def test_add_blank_complex_story_name(self):
        processor = MongoProcessor()
        events = [
            {"name": "greeting", "type": "user"},
            {"name": "utter_greet", "type": "action"},
            {"name": "mood_great", "type": "user"},
            {"name": "utter_greet", "type": "action"},
        ]
        with pytest.raises(AppException):
            processor.add_complex_story("  ", events, "tests", "testUser")

    def test_add_empty_complex_story_event(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            processor.add_complex_story("empty path", [], "tests", "testUser")

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
        processor.update_complex_story("story with action", steps, "tests", "testUser")
        story = Stories.objects(block_name="story with action").get()
        assert story.events[1].name == "utter_nonsense"

    def test_update_non_existing_complex_story(self):
        processor = MongoProcessor()
        steps = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_nonsense", "type": "BOT"},
            {"name": "utter_cheer_up", "type": "BOT"},
            {"name": "mood_great", "type": "INTENT"},
            {"name": "utter_greet", "type": "BOT"},
            {"name": "test_update_http_config_invalid", "type": "HTTP_ACTION"}
        ]
        with pytest.raises(Exception):
            processor.update_complex_story("non existing story", steps, "tests", "testUser")

    def test_update_complex_story_name(self):
        processor = MongoProcessor()
        events = [
            {"name": "greeting", "type": "user"},
            {"name": "utter_greet", "type": "action"},
            {"name": "mood_great", "type": "user"},
            {"name": "utter_greet", "type": "action"},
        ]
        with pytest.raises(AppException):
            processor.update_complex_story(None, events, "tests", "testUser")

    def test_update_empty_complex_story_name(self):
        processor = MongoProcessor()
        events = [
            {"name": "greeting", "type": "user"},
            {"name": "utter_greet", "type": "action"},
            {"name": "mood_great", "type": "user"},
            {"name": "utter_greet", "type": "action"},
        ]
        with pytest.raises(AppException):
            processor.update_complex_story("", events, "tests", "testUser")

    def test_update_blank_complex_story_name(self):
        processor = MongoProcessor()
        events = [
            {"name": "greeting", "type": "user"},
            {"name": "utter_greet", "type": "action"},
            {"name": "mood_great", "type": "user"},
            {"name": "utter_greet", "type": "action"},
        ]
        with pytest.raises(AppException):
            processor.update_complex_story("  ", events, "tests", "testUser")

    def test_update_empty_complex_story_event(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            processor.update_complex_story("empty path", [], "tests", "testUser")

    def test_delete_non_existing_complex_story(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            processor.delete_complex_story("non existing", "tests", "testUser")

    def test_delete_complex_story(self):
        processor = MongoProcessor()
        processor.delete_complex_story("story with action", "tests", "testUser")

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
        assert status['status'] == TRAINING_DATA_GENERATOR_STATUS.INITIATED.value
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
        assert status['status'] == TRAINING_DATA_GENERATOR_STATUS.INITIATED.value
        assert status['document_path'] == 'document/doc.pdf'
        assert status['start_timestamp'] is not None
        assert status['last_update_timestamp'] is not None

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
            status=TRAINING_DATA_GENERATOR_STATUS.COMPLETED.value,
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
        assert status['status'] == TRAINING_DATA_GENERATOR_STATUS.COMPLETED.value
        assert status['document_path'] == 'document/doc.pdf'
        assert status['start_timestamp'] is not None
        assert status['last_update_timestamp'] is not None
        assert status['end_timestamp'] is not None
        assert status['response'] is not None

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
        assert status['status'] == TRAINING_DATA_GENERATOR_STATUS.COMPLETED.value
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
