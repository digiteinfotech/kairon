import asyncio
import os

import pytest
from mongoengine import connect
from mongoengine.errors import ValidationError
from rasa.core.agent import Agent
from rasa.core.training.structures import StoryGraph
from rasa.importers.rasa import Domain
from rasa.nlu.training_data import TrainingData

from bot_trainer.data_processor.data_objects import (TrainingExamples,
                                                     Slots,
                                                     Entities,
                                                     Intents,
                                                     Actions,
                                                     Responses,
                                                     ModelTraining
                                                     )
from bot_trainer.data_processor.processor import MongoProcessor, AgentProcessor, ModelProcessor
from bot_trainer.exceptions import AppException
from bot_trainer.train import train_model_from_mongo, start_training
from bot_trainer.utils import Utility

class TestMongoProcessor:
    @pytest.fixture(autouse=True)
    def init_connection(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_evironment()
        connect(Utility.environment["mongo_db"], host=Utility.environment["mongo_url"])

    def test_load_from_path(self):
        processor = MongoProcessor()
        loop = asyncio.new_event_loop()
        assert (
                loop.run_until_complete(
                    processor.save_from_path(
                        "tests/testing_data/initial", bot="tests", user="testUser"
                    )
                )
                is None
        )

    def test_load_from_path_error(self):
        processor = MongoProcessor()
        loop = asyncio.new_event_loop()
        with pytest.raises(Exception):
            loop.run_until_complete(
                processor.save_from_path(
                    "tests/testing_data/error", bot="tests", user="testUser"
                )
            )

    def test_load_from_path_all_sccenario(self):
        processor = MongoProcessor()
        loop = asyncio.new_event_loop()
        loop.run_until_complete(
            processor.save_from_path("tests/testing_data/all", "all", user="testUser")
        )
        training_data = processor.load_nlu("all")
        assert isinstance(training_data, TrainingData)
        assert training_data.training_examples.__len__() == 283
        assert training_data.entity_synonyms.__len__() == 3
        assert training_data.regex_features.__len__() == 5
        assert training_data.lookup_tables.__len__() == 1
        story_graph = processor.load_stories("all")
        assert isinstance(story_graph, StoryGraph) == True
        assert story_graph.story_steps.__len__() == 13
        domain = processor.load_domain("all")
        assert isinstance(domain, Domain)
        assert domain.slots.__len__() == 8
        assert domain.templates.keys().__len__() == 21
        assert domain.entities.__len__() == 7
        assert domain.form_names.__len__() == 2
        assert domain.user_actions.__len__() == 32
        assert domain.intents.__len__() == 22
        assert not Utility.check_empty_string(
            domain.templates["utter_cheer_up"][0]["image"]
        )
        assert domain.templates["utter_did_that_help"][0]["buttons"].__len__() == 2
        assert domain.templates["utter_offer_help"][0]["custom"]
        assert domain.slots[0].type_name == "unfeaturized"

    def test_load_from_path_all_sccenario_append(self):
        processor = MongoProcessor()
        loop = asyncio.new_event_loop()
        loop.run_until_complete(
            processor.save_from_path("tests/testing_data/all",
                                     "all",
                                     overwrite=False,
                                     user="testUser")
        )
        training_data = processor.load_nlu("all")
        assert isinstance(training_data, TrainingData)
        assert training_data.training_examples.__len__() == 283
        assert training_data.entity_synonyms.__len__() == 3
        assert training_data.regex_features.__len__() == 5
        assert training_data.lookup_tables.__len__() == 1
        story_graph = processor.load_stories("all")
        assert isinstance(story_graph, StoryGraph) == True
        assert story_graph.story_steps.__len__() == 13
        domain = processor.load_domain("all")
        assert isinstance(domain, Domain)
        assert domain.slots.__len__() == 8
        assert domain.templates.keys().__len__() == 21
        assert domain.entities.__len__() == 7
        assert domain.form_names.__len__() == 2
        assert domain.user_actions.__len__() == 32
        assert domain.intents.__len__() == 22
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
        assert training_data.training_examples.__len__() == 43
        assert training_data.entity_synonyms.__len__() == 0
        assert training_data.regex_features.__len__() == 0
        assert training_data.lookup_tables.__len__() == 0

    def test_load_domain(self):
        processor = MongoProcessor()
        domain = processor.load_domain("tests")
        assert isinstance(domain, Domain)
        assert domain.slots.__len__() == 0
        assert domain.templates.keys().__len__() == 6
        assert domain.entities.__len__() == 0
        assert domain.form_names.__len__() == 0
        assert domain.user_actions.__len__() == 6
        assert domain.intents.__len__() == 7

    def test_load_stories(self):
        processor = MongoProcessor()
        story_graph = processor.load_stories("tests")
        assert isinstance(story_graph, StoryGraph)
        assert story_graph.story_steps.__len__() == 5

    def test_add_intent(self):
        processor = MongoProcessor()
        assert processor.add_intent("greeting", "tests", "testUser")
        intent = Intents.objects(bot="tests").get(name="greeting")
        assert intent.name == "greeting"

    def test_get_intents(self):
        processor = MongoProcessor()
        expected = [
            "affirm",
            "bot_challenge",
            "deny",
            "goodbye",
            "greet",
            "mood_great",
            "mood_unhappy",
            "greeting",
        ]
        actual = processor.get_intents("tests")
        assert actual.__len__() == expected.__len__()
        assert all(item["name"] in expected for item in actual)


    def test_add_intent_with_underscore(self):
        processor = MongoProcessor()
        assert processor.add_intent("greeting_examples", "tests", "testUser")
        intent = Intents.objects(bot="tests").get(name="greeting_examples")
        assert intent.name == "greeting_examples"


    def test_add_intent_duplicate(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            processor.add_intent("greeting", "tests", "testUser")


    def test_add_intent_duplicate_case_insensitive(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            processor.add_intent("Greeting", "tests", "testUser")

    def test_add_none_intent(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_intent(None, "tests", "testUser")

    def test_add_empty_intent(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_intent("", "tests", "testUser")

    def test_add_blank_intent(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            processor.add_intent("  ", "tests", "testUser")

    def test_add_training_example(self):
        processor = MongoProcessor()
        results = list(
            processor.add_training_example(["Hi, How are you?"], "greeting", "tests", "testUser")
        )
        assert results[0]["_id"]
        assert results[0]["text"] == "Hi, How are you?"
        assert results[0]["message"] == "Training Example added successfully!"

    def test_add_same_training_example(self):
        processor = MongoProcessor()
        results = list(
            processor.add_training_example(["Hi"], "greeting", "tests", "testUser")
        )
        assert results[0]["_id"] is None
        assert results[0]["text"] == "Hi"
        assert results[0]["message"] == "Training Example already exists!"


    def test_add_training_example_duplicate_case_insensitive(self):
        processor = MongoProcessor()
        results = list(
            processor.add_training_example(["hi"], "greeting", "tests", "testUser")
        )
        assert results[0]["_id"] is None
        assert results[0]["text"] == "hi"
        assert results[0]["message"] == "Training Example already exists!"

    def test_add_training_example_none_text(self):
        processor = MongoProcessor()
        results = list(
            processor.add_training_example([None], "greeting", "tests", "testUser")
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
            processor.add_training_example([""], "greeting", "tests", "testUser")
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
            processor.add_training_example(["  "], "greeting", "tests", "testUser")
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
                    ["Hi! How are you"], None, "tests", "testUser"
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
                    ["Hi! How are you"], "", "tests", "testUser"
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
                    ["Hi! How are you"], "  ", "tests", "testUser"
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
                processor.add_training_example([""], None, "tests", "testUser")
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
                                       bot="tests", user="testUser"))
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
        ]
        actual = processor.get_actions("tests")
        assert actual.__len__() == expected.__len__()
        assert all(item["name"] in expected for item in actual)

    def test_add_action_duplicate(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            assert processor.add_action("utter_priority", "tests", "testUser") == None


    def test_add_action_duplicate_caseinsentive(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            assert processor.add_action("Utter_Priority", "tests", "testUser") == None

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
        id = processor.add_session_config(
            id=session_config["_id"],
            sesssionExpirationTime=30,
            carryOverSlots=False,
            bot="tests",
            user="testUser",
        )
        assert id == session_config["_id"]
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
        id = processor.add_session_config(
            sesssionExpirationTime=30, carryOverSlots=False, bot="test", user="testUser"
        )
        assert id

    def test_train_model(self):
        loop = asyncio.new_event_loop()
        model = loop.run_until_complete(train_model_from_mongo("tests"))
        assert model

    def test_train_model_empty_data(self):
        loop = asyncio.new_event_loop()
        with pytest.raises(AppException):
            model = loop.run_until_complete(train_model_from_mongo("test"))
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
        with pytest.raises(AppException) as exp:
            assert start_training("test", "testUser")

        assert str(exp.value) == "Training data does not exists!"

        model_training = ModelTraining.objects(bot="test", status="Fail")
        assert model_training.__len__() == 1
        assert model_training.first().exception in str(exp.value)


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
        print(response)
        assert response == "utter_goodbye"

    def test_get_utterance_from_empty_intent(self):
        processor = MongoProcessor()
        with pytest.raises(AppException):
            response = processor.get_utterance_from_intent("", "tests")

    def test_get_stories(self):
        processor = MongoProcessor()
        stories = list(processor.get_stories("tests"))
        assert stories.__len__() == 6

    def test_edit_training_example_duplicate(self):
        processor = MongoProcessor()
        examples = list(processor.get_training_examples("greet", "tests"))
        with pytest.raises(AppException):
            processor.edit_training_example(examples[0]["_id"], example="hey there", intent="greet", bot="tests", user="testUser")

    def test_edit_training_example_does_not_exists(self):
        processor = MongoProcessor()
        examples = list(processor.get_training_examples("greet", "tests"))
        with pytest.raises(AppException):
            processor.edit_training_example(examples[0]["_id"], example="hey there", intent="happy", bot="tests", user="testUser")

    def test_edit_training_example(self):
        processor = MongoProcessor()
        examples = list(processor.get_training_examples("greet", "tests"))
        processor.edit_training_example(examples[0]["_id"], example="hey, there", intent="greet", bot="tests", user="testUser")
        examples = list(processor.get_training_examples("greet", "tests"))
        assert any(example['text'] == "hey, there" for example in examples)


    def test_edit_training_example_with_entities(self):
        processor = MongoProcessor()
        examples = list(processor.get_training_examples("greet", "tests"))
        processor.edit_training_example(examples[0]["_id"], example="[Meghalaya](Location) India", intent="greet", bot="tests", user="testUser")
        examples = list(processor.get_training_examples("greet", "tests"))
        assert any(example['text'] == "Meghalaya India" for example in examples)

    def test_edit_responses_duplicate(self):
        processor = MongoProcessor()
        responses = list(processor.get_response("utter_happy", "tests"))
        with pytest.raises(AppException):
            processor.edit_text_response(responses[0]["_id"], "Great, carry on!", name="utter_happy", bot="tests", user="testUser")


    def test_edit_responses_does_not_exist(self):
        processor = MongoProcessor()
        responses = list(processor.get_response("utter_happy", "tests"))
        with pytest.raises(AppException):
            processor.edit_text_response(responses[0]["_id"], "Great, carry on!", name="utter_greet", bot="tests", user="testUser")

    def test_edit_responses(self):
        processor = MongoProcessor()
        responses = list(processor.get_response("utter_happy", "tests"))
        processor.edit_text_response(responses[0]["_id"], "Great!", name="utter_happy", bot="tests", user="testUser")
        responses = list(processor.get_response("utter_happy", "tests"))
        assert any(response['value']['text'] == "Great!" for response in responses if "text" in response['value'])
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
        Utility.load_evironment()
        connect(Utility.environment["mongo_db"], host=Utility.environment["mongo_url"])

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

        assert model_training.count() == 2
        assert model_training[1].id == training_status_inprogress_id
        assert model_training[1].bot == "tests"
        assert model_training[1].user == "testUser"
        assert model_training[1].status == "Done"
        assert model_training[1].model_path == "model_path"
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
        monkeypatch.setitem(Utility.environment, "MODEL_TRAINING_LIMIT_PER_DAY", 5)
        actual_response = ModelProcessor.is_daily_training_limit_exceeded("tests")
        assert actual_response is False

    def test_is_daily_training_limit_exceeded_True(self, monkeypatch):
        monkeypatch.setitem(Utility.environment, "MODEL_TRAINING_LIMIT_PER_DAY", 1)
        actual_response = ModelProcessor.is_daily_training_limit_exceeded("tests", False)
        assert actual_response is True

    def test_is_daily_training_limit_exceeded_exception(self, monkeypatch):
        monkeypatch.setitem(Utility.environment, "MODEL_TRAINING_LIMIT_PER_DAY", 1)
        with pytest.raises(AppException) as exp:
            assert ModelProcessor.is_daily_training_limit_exceeded("tests")

        assert str(exp.value) == "Daily model training limit exceeded."

    def test_get_training_history(self):
        actual_response = ModelProcessor.get_training_history("tests")
        assert actual_response

    def test_delete_valid_intent_only(self):
        processor = MongoProcessor()
        processor.add_intent("TestingDelGreeting", "tests", "testUser")
        processor.delete_intent("TestingDelGreeting", "tests", "testUser", delete_dependencies=False)
        with pytest.raises(Exception):
            intent = Intents.objects(bot="tests", status=True).get(name="TestingDelGreeting")

    def test_delete_invalid_intent(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            processor.delete_intent("TestingDelGreetingInvalid", "tests", "testUser")

    def test_delete_empty_Intent(self):
        processor = MongoProcessor()
        with pytest.raises(AssertionError):
            processor.delete_intent("", "tests", "testUser")

    def test_delete_valid_intent(self):
        processor = MongoProcessor()
        processor.add_intent("TestingDelGreeting", "tests", "testUser")
        processor.delete_intent("TestingDelGreeting", "tests", "testUser")

    def test_intent_no_stories(self):
        processor = MongoProcessor()
        processor.add_intent("TestingDelGreeting", "tests", "testUser")
        processor.add_training_example(["Hows You Doing!"], "TestingDelGreeting", "tests", "testUser")
        processor.delete_intent("TestingDelGreeting", "tests", "testUser")
        actual = processor.get_intents("tests")
        assert not any(intent['name'] == 'TestingDelGreeting'  for intent in actual)
        actual = len(list(processor.get_training_examples("TestingDelGreeting", "tests")))
        assert not actual

    def test_delete_intent_no_trainingExamples(self):
        processor = MongoProcessor()
        processor.add_intent("TestingDelGreeting", "tests", "testUser")
        processor.add_story("path_TestingDelGreeting", [{"name": "TestingDelGreeting", "type": "user"}, {"name": "utter_TestingDelGreeting", "type": "action"}], "tests", "testUser")
        processor.add_text_response("Hello!", "utter_TestingDelGreeting", "tests", "testUser")
        processor.delete_intent("TestingDelGreeting", "tests", "testUser")
        actual = processor.get_intents("tests")
        assert not any(intent['name'] == 'TestingDelGreeting'  for intent in actual)
        actual = list(processor.get_stories("tests"))
        assert not any(story['block_name'] == 'TestingDelGreeting' for story in actual)
        actual = processor.get_utterance_from_intent("TestingDelGreeting", "tests")
        assert not actual

    def test_delete_intent_no_utterance(self):
        processor = MongoProcessor()
        processor.add_intent("TestingDelGreeting", "tests", "testUser")
        processor.add_story("path_TestingDelGreeting", [{"name": "TestingDelGreeting", "type": "user"}, {"name": "utter_TestingDelGreeting", "type": "action"}], "tests", "testUser")
        processor.delete_intent("TestingDelGreeting", "tests", "testUser")
        actual = processor.get_intents("tests")
        assert not any(intent['name'] == 'TestingDelGreeting'  for intent in actual)
        actual = list(processor.get_stories("tests"))
        assert not any(story['block_name'] == 'TestingDelGreeting' for story in actual)


    def test_delete_intent_with_examples_stories_utterance(self):
        processor = MongoProcessor()
        processor.add_intent("TestingDelGreeting", "tests", "testUser")
        processor.add_story("path_TestingDelGreeting", [{"name": "TestingDelGreeting", "type": "user"}, {"name": "utter_TestingDelGreeting", "type": "action"}], "tests", "testUser")
        processor.add_text_response("Hello!", "utter_TestingDelGreeting", "tests", "testUser")
        processor.delete_intent("TestingDelGreeting", "tests", "testUser")
        actual = processor.get_intents("tests")
        assert not any(intent['name'] == 'TestingDelGreeting'  for intent in actual)
        actual = list(processor.get_stories("tests"))
        assert not any(story['block_name'] == 'TestingDelGreeting' for story in actual)
        actual = processor.get_utterance_from_intent("TestingDelGreeting", "tests")
        assert not actual
