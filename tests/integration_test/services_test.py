import os
import re
import tarfile
from io import BytesIO
from zipfile import ZipFile

import mongomock
import pytest
import responses
from fastapi.testclient import TestClient
from mongoengine import connect
from kairon.api.models import StoryEventType
from kairon.api.processor import AccountProcessor
from kairon.api.app.main import app
from kairon.data_processor.constant import CUSTOM_ACTIONS, UTTERANCE_TYPE, TRAINING_DATA_GENERATOR_STATUS
from kairon.data_processor.data_objects import Stories, Intents, TrainingExamples, Responses
from kairon.data_processor.processor import MongoProcessor, ModelProcessor, TrainingDataGenerationProcessor
from kairon.exceptions import AppException
from kairon.utils import Utility
from rasa.shared.utils.io import read_config_file

os.environ["system_file"] = "./tests/testing_data/system.yaml"
client = TestClient(app)
access_token = None
token_type = None


@pytest.fixture(autouse=True)
def setup():
    os.environ["system_file"] = "./tests/testing_data/system.yaml"
    Utility.load_evironment()
    connect(host=Utility.environment['database']["url"])


def pytest_configure():
    return {'token_type': None,
            'access_token': None
            }


def test_api_wrong_login():
    response = client.post(
        "/api/auth/login", data={"username": "test@demo.ai", "password": "Welcome@1"}
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert not actual["success"]
    assert actual["message"] == "User does not exist!"


def test_account_registration_error():
    response = client.post(
        "/api/account/registration",
        json={
            "email": "integration@demo.ai",
            "first_name": "Demo",
            "last_name": "User",
            "password": "welcome@1",
            "confirm_password": "welcome@1",
            "account": "integration",
            "bot": "integration",
        },
    )
    actual = response.json()
    assert actual[
               "message"] == '''1 validation error for Request\nbody -> password\n  Missing 1 uppercase letter (type=value_error)'''
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["data"] is None


def test_account_registration():
    response = client.post(
        "/api/account/registration",
        json={
            "email": "integration@demo.ai",
            "first_name": "Demo",
            "last_name": "User",
            "password": "Welcome@1",
            "confirm_password": "Welcome@1",
            "account": "integration",
            "bot": "integration",
        },
    )
    actual = response.json()
    assert actual["message"] == "Account Registered!"
    response = client.post(
        "/api/account/registration",
        json={
            "email": "integration2@demo.ai",
            "first_name": "Demo",
            "last_name": "User",
            "password": "Welcome@1",
            "confirm_password": "Welcome@1",
            "account": "integration2",
            "bot": "integration2",
        },
    )
    actual = response.json()
    assert actual["message"] == "Account Registered!"


def test_api_login():
    response = client.post(
        "/api/auth/login",
        data={"username": "integration@demo.ai", "password": "Welcome@1"},
    )
    actual = response.json()
    assert all(
        [
            True if actual["data"][key] else False
            for key in ["access_token", "token_type"]
        ]
    )
    assert actual["success"]
    assert actual["error_code"] == 0
    pytest.access_token = actual["data"]["access_token"]
    pytest.token_type = actual["data"]["token_type"]


def test_upload_missing_data():
    files = {
        "domain": (
            "tests/testing_data/all/domain.yml",
            open("tests/testing_data/all/domain.yml", "rb"),
        ),
        "stories": (
            "tests/testing_data/all/data/stories.md",
            open("tests/testing_data/all/data/stories.md", "rb"),
        ),
        "config": (
            "tests/testing_data/all/config.yml",
            open("tests/testing_data/all/config.yml", "rb"),
        ),
    }
    response = client.post(
        "/api/bot/upload",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=files,
    )
    actual = response.json()
    assert (
            actual["message"]
            == "1 validation error for Request\nbody -> nlu\n  field required (type=value_error.missing)"
    )
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert not actual["success"]


def test_upload_error():
    files = {
        "nlu": ("tests/testing_data/all/data/nlu.md", None),
        "domain": (
            "tests/testing_data/all/domain.yml",
            open("tests/testing_data/all/domain.yml", "rb"),
        ),
        "stories": (
            "tests/testing_data/all/data/stories.md",
            open("tests/testing_data/all/data/stories.md", "rb"),
        ),
        "config": (
            "tests/testing_data/all/config.yml",
            open("tests/testing_data/all/config.yml", "rb"),
        ),
    }
    response = client.post(
        "/api/bot/upload",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=files,
    )
    actual = response.json()
    assert (
            actual["message"]
            == "1 validation error for Request\nbody -> nlu\n  field required (type=value_error.missing)"
    )
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert not actual["success"]


def test_upload(monkeypatch):
    def mongo_store(*arge, **kwargs):
        return None

    monkeypatch.setattr(Utility, "get_local_mongo_store", mongo_store)
    files = {
        "nlu": (
            "tests/testing_data/all/data/nlu.md",
            open("tests/testing_data/all/data/nlu.md", "rb"),
        ),
        "domain": (
            "tests/testing_data/all/domain.yml",
            open("tests/testing_data/all/domain.yml", "rb"),
        ),
        "stories": (
            "tests/testing_data/all/data/stories.md",
            open("tests/testing_data/all/data/stories.md", "rb"),
        ),
        "config": (
            "tests/testing_data/all/config.yml",
            open("tests/testing_data/all/config.yml", "rb"),
        ),
    }
    response = client.post(
        "/api/bot/upload",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=files,
    )
    actual = response.json()
    assert actual["message"] == "Data uploaded successfully!"
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]


def test_get_intents():
    response = client.get(
        "/api/bot/intents",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert "data" in actual
    assert len(actual["data"]) == 27
    assert actual["success"]
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])


def test_get_all_intents():
    response = client.get(
        "/api/bot/intents/all",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert "data" in actual
    print(actual['data'])
    assert len(actual["data"]) == 27
    assert actual["success"]
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])


def test_add_intents():
    response = client.post(
        "/api/bot/intents",
        json={"data": "happier"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Intent added successfully!"


def test_add_intents_duplicate():
    response = client.post(
        "/api/bot/intents",
        json={"data": "happier"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Intent already exists!"


def test_add_empty_intents():
    response = client.post(
        "/api/bot/intents",
        json={"data": ""},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Intent Name cannot be empty or blank spaces"


def test_get_training_examples():
    response = client.get(
        "/api/bot/training_examples/greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert len(actual["data"]) == 8
    assert actual["success"]
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])


def test_get_training_examples_empty_intent():
    response = client.get(
        "/api/bot/training_examples/ ",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert len(actual["data"]) == 0
    assert actual["success"]
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])


def test_add_training_examples():
    response = client.post(
        "/api/bot/training_examples/greet",
        json={"data": ["How do you do?"]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"][0]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] is None
    response = client.get(
        "/api/bot/training_examples/greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert len(actual["data"]) == 9


def test_add_training_examples_duplicate():
    response = client.post(
        "/api/bot/training_examples/greet",
        json={"data": ["How do you do?"]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"][0]["message"] == "Training Example already exists!"
    assert actual["data"][0]["_id"] is None


def test_add_empty_training_examples():
    response = client.post(
        "/api/bot/training_examples/greet",
        json={"data": [""]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert (
            actual["data"][0]["message"]
            == "Training Example cannot be empty or blank spaces"
    )
    assert actual["data"][0]["_id"] is None


def test_remove_training_examples():
    training_examples = client.get(
        "/api/bot/training_examples/greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    training_examples = training_examples.json()
    assert len(training_examples["data"]) == 9
    response = client.delete(
        "/api/bot/training_examples",
        json={"data": training_examples["data"][0]["_id"]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Training Example removed!"
    training_examples = client.get(
        "/api/bot/training_examples/greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    training_examples = training_examples.json()
    assert len(training_examples["data"]) == 8


def test_remove_training_examples_empty_id():
    response = client.delete(
        "/api/bot/training_examples",
        json={"data": ""},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Unable to remove document"


def test_edit_training_examples():
    training_examples = client.get(
        "/api/bot/training_examples/greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    training_examples = training_examples.json()
    response = client.put(
        "/api/bot/training_examples/greet/" + training_examples["data"][0]["_id"],
        json={"data": "hey, there"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Training Example updated!"


def test_get_responses():
    response = client.get(
        "/api/bot/response/utter_greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert len(actual["data"]) == 1
    assert actual["success"]
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])


def test_get_all_responses():
    response = client.get(
        "/api/bot/response/all",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    print(actual["data"])
    assert len(actual["data"]) == 22
    assert actual["data"][0]['name']
    assert actual["data"][0]['texts'][0]['text']
    assert not actual["data"][0]['customs']
    assert actual["success"]
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])


def test_add_response():
    response = client.post(
        "/api/bot/response/utter_greet",
        json={"data": "Wow! How are you?"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Utterance added!"
    response = client.get(
        "/api/bot/response/utter_greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert len(actual["data"]) == 2


def test_add_response_duplicate():
    response = client.post(
        "/api/bot/response/utter_greet",
        json={"data": "Wow! How are you?"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Utterance already exists!"


def test_add_empty_response():
    response = client.post(
        "/api/bot/response/utter_greet",
        json={"data": ""},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Utterance text cannot be empty or blank spaces"


def test_remove_response():
    training_examples = client.get(
        "/api/bot/response/utter_greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    training_examples = training_examples.json()
    assert len(training_examples["data"]) == 2
    response = client.delete(
        "/api/bot/response/False",
        json={"data": training_examples["data"][0]["_id"]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Utterance removed!"
    training_examples = client.get(
        "/api/bot/response/utter_greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    training_examples = training_examples.json()
    assert len(training_examples["data"]) == 1


def test_remove_utterance_attached_to_story():
    response = client.post(
        "/api/bot/stories",
        json={
            "name": "test_remove_utterance_attached_to_story",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_greet", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Story added successfully"
    response = client.delete(
        "/api/bot/response/True",
        json={"data": "utter_greet"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Cannot remove utterance linked to story"


def test_remove_utterance():
    response = client.delete(
        "/api/bot/response/True",
        json={"data": "utter_delete"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Utterance removed!"


def test_remove_utterance_non_existing():
    response = client.delete(
        "/api/bot/response/True",
        json={"data": "utter_delete_non_existing"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Utterance does not exists"


def test_remove_utterance_empty():
    response = client.delete(
        "/api/bot/response/True",
        json={"data": " "},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Utterance cannot be empty or spaces"


def test_remove_response_empty_id():
    response = client.delete(
        "/api/bot/response/False",
        json={"data": ""},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Utterance Id cannot be empty or spaces"


def test_remove_response_():
    training_examples = client.get(
        "/api/bot/response/utter_greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    training_examples = training_examples.json()
    response = client.put(
        "/api/bot/response/utter_greet/" + training_examples["data"][0]["_id"],
        json={"data": "Hello, How are you!"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Utterance updated!"


def test_add_story():
    response = client.post(
        "/api/bot/stories",
        json={
            "name": "test_path",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_greet", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Story added successfully"
    assert actual["data"]["_id"]


def test_add_story_empty_event():
    response = client.post(
        "/api/bot/stories",
        json={"name": "test_add_story_empty_event", "steps": []},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "1 validation error for Request\nbody -> steps\n  Steps are required to form story (type=value_error)"


def test_add_story_consecutive_intents():
    response = client.post(
        "/api/bot/stories",
        json={
            "name": "test_add_story_consecutive_intents",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_greet", "type": "INTENT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "1 validation error for Request\nbody -> steps\n  Found 2 consecutive intents (type=value_error)"


def test_add_story_multiple_actions():
    response = client.post(
        "/api/bot/stories",
        json={
            "name": "test_add_story_consecutive_intents",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_greet", "type": "HTTP_ACTION"},
                {"name": "utter_greet_again", "type": "HTTP_ACTION"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "1 validation error for Request\nbody -> steps\n  You can have only one Http action against an intent (type=value_error)"


def test_add_story_utterance_as_first_step():
    response = client.post(
        "/api/bot/stories",
        json={
            "name": "test_add_story_consecutive_intents",
            "steps": [
                {"name": "greet", "type": "BOT"},
                {"name": "utter_greet", "type": "HTTP_ACTION"},
                {"name": "utter_greet_again", "type": "HTTP_ACTION"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "1 validation error for Request\nbody -> steps\n  First step should be an intent (type=value_error)"


def test_add_story_missing_event_type():
    response = client.post(
        "/api/bot/stories",
        json={
            "name": "test_path",
            "steps": [{"name": "greet"}, {"name": "utter_greet", "type": "BOT"}],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert (
            actual["message"]
            == "1 validation error for Request\nbody -> steps -> 0 -> type\n  field required (type=value_error.missing)"
    )


def test_add_story_invalid_event_type():
    response = client.post(
        "/api/bot/stories",
        json={
            "name": "test_path",
            "steps": [
                {"name": "greet", "type": "data"},
                {"name": "utter_greet", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert (
            actual["message"]
            == "1 validation error for Request\nbody -> steps -> 0 -> type\n  value is not a valid enumeration member; permitted: 'INTENT', 'BOT', 'HTTP_ACTION' (type=type_error.enum; enum_values=[<StoryStepType.intent: 'INTENT'>, <StoryStepType.bot: 'BOT'>, <StoryStepType.http_action: 'HTTP_ACTION'>])"
    )


def test_update_story():
    response = client.put(
        "/api/bot/stories",
        json={
            "name": "test_path",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_nonsense", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Story updated successfully"
    assert actual["data"]["_id"]


def test_update_story_invalid_event_type():
    response = client.put(
        "/api/bot/stories",
        json={
            "name": "test_path",
            "steps": [
                {"name": "greet", "type": "data"},
                {"name": "utter_nonsense", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert (
            actual["message"]
            == "1 validation error for Request\nbody -> steps -> 0 -> type\n  value is not a valid enumeration member; permitted: 'INTENT', 'BOT', 'HTTP_ACTION' (type=type_error.enum; enum_values=[<StoryStepType.intent: 'INTENT'>, <StoryStepType.bot: 'BOT'>, <StoryStepType.http_action: 'HTTP_ACTION'>])"
    )


def test_delete_story():
    response = client.post(
        "/api/bot/stories",
        json={
            "name": "test_path1",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_greet", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Story added successfully"
    assert actual["data"]["_id"]

    response = client.delete(
        "/api/bot/stories/test_path1",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Story deleted successfully"


def test_delete_non_existing_story():
    response = client.delete(
        "/api/bot/stories/test_path2",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Story does not exists"


def test_get_stories():
    response = client.get(
        "/api/bot/stories",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]
    assert Utility.check_empty_string(actual["message"])


def test_get_utterance_from_intent():
    response = client.get(
        "/api/bot/utterance_from_intent/greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["name"] == "utter_offer_help"
    assert actual["data"]["type"] == UTTERANCE_TYPE.BOT
    assert Utility.check_empty_string(actual["message"])


def test_get_utterance_from_not_exist_intent():
    response = client.get(
        "/api/bot/utterance_from_intent/greeting",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["name"] is None
    assert actual["data"]["type"] is None
    assert Utility.check_empty_string(actual["message"])


def test_train(monkeypatch):
    def mongo_store(*arge, **kwargs):
        return None

    monkeypatch.setattr(Utility, "get_local_mongo_store", mongo_store)
    response = client.post(
        "/api/bot/train",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "Model training started."


@pytest.fixture
def mock_is_training_inprogress_exception(monkeypatch):
    def _inprogress_execption_response(*args, **kwargs):
        raise AppException("Previous model training in progress.")

    monkeypatch.setattr(ModelProcessor, "is_training_inprogress", _inprogress_execption_response)


def test_train_inprogress(mock_is_training_inprogress_exception):
    response = client.post(
        "/api/bot/train",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"] == False
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"] == "Previous model training in progress."


@pytest.fixture
def mock_is_training_inprogress(monkeypatch):
    def _inprogress_response(*args, **kwargs):
        return False

    monkeypatch.setattr(ModelProcessor, "is_training_inprogress", _inprogress_response)


def test_train_daily_limit_exceed(mock_is_training_inprogress):
    response = client.post(
        "/api/bot/train",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"] == "Daily model training limit exceeded."


def test_get_model_training_history():
    response = client.get(
        "/api/bot/train/history",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"] is True
    assert actual["error_code"] == 0
    assert actual["data"]
    assert "training_history" in actual["data"]

def test_get_file_training_history():
    response = client.get(
        "/api/bot/data/generation/history",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"] is True
    assert actual["error_code"] == 0
    assert actual["data"]
    assert "training_history" in actual["data"]


def test_chat(monkeypatch):
    def mongo_store(*arge, **kwargs):
        return None

    monkeypatch.setattr(Utility, "get_local_mongo_store", mongo_store)
    monkeypatch.setitem(Utility.environment['action'], "url", None)
    response = client.post(
        "/api/bot/chat",
        json={"data": "Hi"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]
    assert Utility.check_empty_string(actual["message"])


def test_chat_fetch_from_cache(monkeypatch):
    def mongo_store(*arge, **kwargs):
        return None

    monkeypatch.setattr(Utility, "get_local_mongo_store", mongo_store)
    monkeypatch.setitem(Utility.environment['action'], "url", None)
    response = client.post(
        "/api/bot/chat",
        json={"data": "Hi"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]
    assert Utility.check_empty_string(actual["message"])


def test_chat_model_not_trained():
    response = client.post(
        "/api/auth/login",
        data={"username": "integration2@demo.ai", "password": "Welcome@1"},
    )
    token = response.json()
    response = client.post(
        "/api/bot/chat",
        json={"data": "Hi"},
        headers={
            "Authorization": token["data"]["token_type"]
                             + " "
                             + token["data"]["access_token"]
        },
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"] == "Bot has not been trained yet !"


def test_deploy_missing_configuration():
    response = client.post(
        "/api/bot/deploy",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "Please configure the bot endpoint for deployment!"


def endpoint_response(*args, **kwargs):
    return {"bot_endpoint": {"url": "http://localhost:5000"}}


@pytest.fixture
def mock_endpoint(monkeypatch):
    monkeypatch.setattr(MongoProcessor, "get_endpoints", endpoint_response)


@pytest.fixture
def mock_endpoint_with_token(monkeypatch):
    def _endpoint_response(*args, **kwargs):
        return {
            "bot_endpoint": {
                "url": "http://localhost:5000",
                "token": "AGTSUDH!@#78JNKLD",
                "token_type": "Bearer",
            }
        }

    monkeypatch.setattr(MongoProcessor, "get_endpoints", _endpoint_response)


def test_deploy_connection_error(mock_endpoint):
    response = client.post(
        "/api/bot/deploy",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "Host is not reachable"


@responses.activate
def test_deploy(mock_endpoint):
    responses.add(
        responses.PUT,
        "http://localhost:5000/model",
        status=204,
    )
    response = client.post(
        "/api/bot/deploy",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "Model was successfully replaced."


@responses.activate
def test_deployment_history():
    response = client.get(
        "/api/bot/deploy/history",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]['deployment_history']) == 3
    assert actual["message"] is None


@responses.activate
def test_deploy_with_token(mock_endpoint_with_token):
    responses.add(
        responses.PUT,
        "http://localhost:5000/model",
        json="Model was successfully replaced.",
        headers={"Content-type": "application/json",
                 "Accept": "text/plain",
                 "Authorization": "Bearer AGTSUDH!@#78JNKLD"},
        status=200,
    )
    response = client.post(
        "/api/bot/deploy",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "Model was successfully replaced."


@responses.activate
def test_deploy_bad_request(mock_endpoint):
    responses.add(
        responses.PUT,
        "http://localhost:5000/model",
        json={
            "version": "1.0.0",
            "status": "failure",
            "reason": "BadRequest",
            "code": 400,
        },
        status=200,
    )
    response = client.post(
        "/api/bot/deploy",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "BadRequest"


@responses.activate
def test_deploy_server_error(mock_endpoint):
    responses.add(
        responses.PUT,
        "http://localhost:5000/model",
        json={
            "version": "1.0.0",
            "status": "ServerError",
            "message": "An unexpected error occurred.",
            "code": 500,
        },
        status=200,
    )
    response = client.post(
        "/api/bot/deploy",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "An unexpected error occurred."


def test_integration_token():
    response = client.get(
        "/api/auth/integration/token",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    token = response.json()
    assert token["success"]
    assert token["error_code"] == 0
    assert token["data"]["access_token"]
    assert token["data"]["token_type"]
    assert (
            token["message"]
            == """It is your responsibility to keep the token secret.
        If leaked then other may have access to your system."""
    )
    response = client.get(
        "/api/bot/intents",
        headers={
            "Authorization": token["data"]["token_type"]
                             + " "
                             + token["data"]["access_token"],
            "X-USER": "integration",
        },
    )
    actual = response.json()
    assert "data" in actual
    assert len(actual["data"]) == 28
    assert actual["success"]
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])
    response = client.post(
        "/api/bot/intents",
        headers={
            "Authorization": token["data"]["token_type"]
                             + " "
                             + token["data"]["access_token"],
            "X-USER": "integration",
        },
        json={"data": "integration"},
    )
    actual = response.json()
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Intent added successfully!"


def test_integration_token_missing_x_user():
    response = client.get(
        "/api/auth/integration/token",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["access_token"]
    assert actual["data"]["token_type"]
    assert (
            actual["message"]
            == """It is your responsibility to keep the token secret.
        If leaked then other may have access to your system."""
    )
    response = client.get(
        "/api/bot/intents",
        headers={
            "Authorization": actual["data"]["token_type"]
                             + " "
                             + actual["data"]["access_token"]
        },
    )
    actual = response.json()
    assert actual["data"] is None
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Alias user missing for integration"


@mongomock.patch(servers=(('localhost', 27019),))
def test_predict_intent(monkeypatch):
    monkeypatch.setitem(Utility.environment['database'], "url", "mongodb://localhost:27019")
    monkeypatch.setitem(Utility.environment['action'], "url", None)
    response = client.post(
        "/api/bot/intents/predict",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"data": "Hi"},
    )

    actual = response.json()
    assert actual.get("data").get("intent")
    assert actual.get("data").get("confidence")


def test_predict_intent_error():
    response = client.post(
        "/api/auth/login",
        data={"username": "integration2@demo.ai", "password": "Welcome@1"},
    )
    token = response.json()
    response = client.post(
        "/api/bot/intents/predict",
        json={"data": "Hi"},
        headers={
            "Authorization": token["data"]["token_type"]
                             + " "
                             + token["data"]["access_token"]
        },
    )
    actual = response.json()
    assert actual["data"] is None
    assert actual["success"] is False
    assert actual["error_code"] == 422
    assert actual["message"] == "Bot has not been trained yet !"


@responses.activate
def test_augment_paraphrase():
    responses.add(
        responses.POST,
        "http://localhost:8000/paraphrases",
        json={
            "sucess": True,
            "data": {
                "questions": ['Where is digite located?',
                              'Where is digite?',
                              'What is the location of digite?',
                              'Where is the digite located?',
                              'Where is it located?',
                              'What location is digite located?',
                              'Where is the digite?',
                              'where is digite located?',
                              'Where is digite situated?',
                              'digite is located where?']
            },
            "message": None,
            "error_code": 0,
        },
        status=200,
    )
    response = client.post(
        "/api/augment/paraphrases",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"data": ["where is digite located?'"]},
    )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]
    assert Utility.check_empty_string(actual["message"])


def test_get_user_details():
    response = client.get(
        "/api/user/details",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]
    assert Utility.check_empty_string(actual["message"])


def test_download_data():
    response = client.get(
        "/api/bot/download/data",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    file_bytes = BytesIO(response.content)
    zip_file = ZipFile(file_bytes, mode='r')
    assert zip_file.filelist.__len__()
    zip_file.close()
    file_bytes.close()


def test_download_model():
    response = client.get(
        "/api/bot/download/model",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    d = response.headers['content-disposition']
    fname = re.findall("filename=(.+)", d)[0]
    file_bytes = BytesIO(response.content)
    tar = tarfile.open(fileobj=file_bytes, mode='r', name=fname)
    assert tar.members.__len__()
    tar.close()
    file_bytes.close()


def test_get_endpoint():
    response = client.get(
        "/api/bot/endpoint",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual['data']
    assert actual['error_code'] == 0
    assert actual['message'] is None
    assert actual['success']


def test_save_endpoint_error():
    response = client.put(
        "/api/bot/endpoint",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual['data'] is None
    assert actual['error_code'] == 422
    assert actual['message'] == '1 validation error for Request\nbody\n  field required (type=value_error.missing)'
    assert not actual['success']


def test_save_empty_endpoint():
    response = client.put(
        "/api/bot/endpoint",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={}
    )

    actual = response.json()
    assert actual['data'] is None
    assert actual['error_code'] == 0
    assert actual['message'] == 'Endpoint saved successfully!'
    assert actual['success']


def test_save_endpoint(monkeypatch):
    def mongo_store(*arge, **kwargs):
        return None

    monkeypatch.setattr(Utility, "get_local_mongo_store", mongo_store)
    monkeypatch.setitem(Utility.environment['action'], "url", None)
    response = client.put(
        "/api/bot/endpoint",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"bot_endpoint": {"url": "http://localhost:5005/"},
              "action_endpoint": {"url": "http://localhost:5000/"},
              "tracker_endpoint": {"url": "mongodb://localhost:27017", "db": "rasa"}}
    )

    actual = response.json()
    assert actual['data'] is None
    assert actual['error_code'] == 0
    assert actual['message'] == 'Endpoint saved successfully!'
    assert actual['success']
    response = client.get(
        "/api/bot/endpoint",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual['data']['endpoint'].get('bot_endpoint')
    assert actual['data']['endpoint'].get('action_endpoint')
    assert actual['data']['endpoint'].get('tracker_endpoint')


def test_get_templates():
    response = client.get(
        "/api/bot/templates/use-case",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert "Hi-Hello" in actual['data']['use-cases']
    assert actual['error_code'] == 0
    assert actual['message'] is None
    assert actual['success']


def test_set_templates():
    response = client.post(
        "/api/bot/templates/use-case",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"data": "Hi-Hello"}
    )

    actual = response.json()
    assert actual['data'] is None
    assert actual['error_code'] == 0
    assert actual['message'] == "Data applied!"
    assert actual['success']


def test_set_templates_invalid():
    response = client.post(
        "/api/bot/templates/use-case",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"data": "Hi"}
    )

    actual = response.json()
    assert actual['data'] is None
    assert actual['error_code'] == 422
    assert actual['message'] == "Invalid template!"
    assert not actual['success']


def test_reload_model(monkeypatch):
    def mongo_store(*arge, **kwargs):
        return None

    monkeypatch.setattr(Utility, "get_local_mongo_store", mongo_store)
    monkeypatch.setitem(Utility.environment['action'], "url", None)
    response = client.get(
        "/api/bot/model/reload",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )

    actual = response.json()
    assert actual['data'] is None
    assert actual['error_code'] == 0
    assert actual['message'] == "Reloading Model!"
    assert actual['success']


def test_get_config_templates():
    response = client.get(
        "/api/bot/templates/config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert any("default" == template['name'] for template in actual['data']['config-templates'])
    assert actual['error_code'] == 0
    assert actual['message'] is None
    assert actual['success']


def test_set_config_templates():
    response = client.post(
        "/api/bot/templates/config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"data": "default"}
    )

    actual = response.json()
    assert actual['data'] is None
    assert actual['error_code'] == 0
    assert actual['message'] == "Config applied!"
    assert actual['success']


def test_set_config_templates_invalid():
    response = client.post(
        "/api/bot/templates/config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"data": "test"}
    )

    actual = response.json()
    assert actual['data'] is None
    assert actual['error_code'] == 422
    assert actual['message'] == "Invalid config!"
    assert not actual['success']


def test_get_config():
    response = client.get(
        "/api/bot/config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert all(key in ["language", "pipeline", "policies"] for key in actual['data']['config'].keys())
    assert actual['error_code'] == 0
    assert actual['message'] is None
    assert actual['success']


def test_set_config():
    response = client.put(
        "/api/bot/config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=read_config_file('./template/config/default.yml')
    )

    actual = response.json()
    assert actual['data'] is None
    assert actual['error_code'] == 0
    assert actual['message'] == "Config saved!"
    assert actual['success']


def test_set_config_policy_error():
    data = read_config_file('./template/config/default.yml')
    data['policies'].append({"name": "TestPolicy"})
    response = client.put(
        "/api/bot/config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=data
    )

    actual = response.json()
    assert actual['data'] is None
    assert actual['error_code'] == 422
    assert actual[
               'message'] == "Module for policy 'TestPolicy' could not be loaded. Please make sure the name is a valid policy."
    assert not actual['success']


def test_set_config_pipeline_error():
    data = read_config_file('./template/config/default.yml')
    data['pipeline'].append({"name": "TestFeaturizer"})
    response = client.put(
        "/api/bot/config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=data
    )

    actual = response.json()
    assert actual['data'] is None
    assert actual['error_code'] == 422
    assert str(actual['message']).__contains__("Failed to load the component 'TestFeaturizer")
    assert not actual['success']


def test_delete_intent():
    client.post(
        "/api/bot/intents",
        json={"data": "happier"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    response = client.delete(
        "/api/bot/intents/happier/True",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual['data'] is None
    assert actual['error_code'] == 0
    assert actual['message'] == "Intent deleted!"
    assert actual['success']


def test_api_login_with_account_not_verified():
    AccountProcessor.EMAIL_ENABLED = True
    response = client.post(
        "/api/auth/login",
        data={"username": "integration@demo.ai", "password": "Welcome@1"},
    )
    actual = response.json()
    AccountProcessor.EMAIL_ENABLED = False

    assert not actual['success']
    assert actual['error_code'] == 422
    assert actual['data'] is None
    assert actual['message'] == 'Please verify your mail'


async def mock_smtp(*args, **kwargs):
    return None


def test_account_registration_with_confirmation(monkeypatch):
    monkeypatch.setattr(Utility, 'trigger_smtp', mock_smtp)
    AccountProcessor.EMAIL_ENABLED = True
    response = client.post(
        "/api/account/registration",
        json={
            "email": "integ1@gmail.com",
            "first_name": "Dem",
            "last_name": "User22",
            "password": "Welcome@1",
            "confirm_password": "Welcome@1",
            "account": "integration33",
            "bot": "integration33",
        },
    )
    actual = response.json()
    assert actual["message"] == "Account Registered! A confirmation link has been sent to your mail"
    assert actual['success']
    assert actual['error_code'] == 0
    assert actual['data'] is None

    response = client.post("/api/account/email/confirmation",
                           json={
                               'data': 'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJtYWlsX2lkIjoiaW50ZWcxQGdtYWlsLmNvbSJ9.Ycs1ROb1w6MMsx2WTA4vFu3-jRO8LsXKCQEB3fkoU20'},
                           )
    actual = response.json()
    AccountProcessor.EMAIL_ENABLED = False

    assert actual['message'] == "Account Verified!"
    assert actual['data'] is None
    assert actual['success']
    assert actual['error_code'] == 0


def test_invalid_token_for_confirmation():
    response = client.post("/api/account/email/confirmation",
                           json={
                               'data': 'hello'},
                           )
    actual = response.json()

    assert actual['message'] == "Invalid token"
    assert actual['data'] is None
    assert not actual['success']
    assert actual['error_code'] == 422


def test_login_for_verified():
    AccountProcessor.EMAIL_ENABLED = True
    response = client.post(
        "/api/auth/login",
        data={"username": "integ1@gmail.com", "password": "Welcome@1"},
    )
    actual = response.json()
    AccountProcessor.EMAIL_ENABLED = False

    assert actual["success"]
    assert actual["error_code"] == 0
    pytest.access_token = actual["data"]["access_token"]
    pytest.token_type = actual["data"]["token_type"]


def test_reset_password_for_valid_id(monkeypatch):
    monkeypatch.setattr(Utility, 'trigger_smtp', mock_smtp)
    AccountProcessor.EMAIL_ENABLED = True
    response = client.post(
        "/api/account/password/reset",
        json={"data": "integ1@gmail.com"},
    )
    actual = response.json()
    AccountProcessor.EMAIL_ENABLED = False
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Success! A password reset link has been sent to your mail id"
    assert actual['data'] is None


def test_reset_password_for_invalid_id():
    AccountProcessor.EMAIL_ENABLED = True
    response = client.post(
        "/api/account/password/reset",
        json={"data": "sasha.41195@gmail.com"},
    )
    actual = response.json()
    AccountProcessor.EMAIL_ENABLED = False
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Error! There is no user with the following mail id"
    assert actual['data'] is None


def test_overwrite_password_for_matching_passwords(monkeypatch):
    monkeypatch.setattr(Utility, 'trigger_smtp', mock_smtp)
    response = client.post(
        "/api/account/password/change",
        json={
            "data": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJtYWlsX2lkIjoiaW50ZWcxQGdtYWlsLmNvbSJ9.Ycs1ROb1w6MMsx2WTA4vFu3-jRO8LsXKCQEB3fkoU20",
            "password": "Welcome@2",
            "confirm_password": "Welcome@2"},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Success! Your password has been changed"
    assert actual['data'] is None


def test_login_new_password():
    response = client.post(
        "/api/auth/login",
        data={"username": "integ1@gmail.com", "password": "Welcome@2"},
    )
    actual = response.json()

    assert actual["success"]
    assert actual["error_code"] == 0
    pytest.access_token = actual["data"]["access_token"]
    pytest.token_type = actual["data"]["token_type"]


def test_login_old_password():
    response = client.post(
        "/api/auth/login",
        data={"username": "integ1@gmail.com", "password": "Welcome@1"},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 401
    assert actual["message"] == 'Incorrect username or password'
    assert actual['data'] is None


def test_send_link_for_valid_id(monkeypatch):
    monkeypatch.setattr(Utility, 'trigger_smtp', mock_smtp)
    AccountProcessor.EMAIL_ENABLED = True
    response = client.post("/api/account/email/confirmation/link",
                           json={
                               'data': 'integration@demo.ai'},
                           )
    actual = response.json()
    AccountProcessor.EMAIL_ENABLED = False
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == 'Success! Confirmation link sent'
    assert actual['data'] is None


def test_send_link_for_confirmed_id():
    AccountProcessor.EMAIL_ENABLED = True
    response = client.post("/api/account/email/confirmation/link",
                           json={
                               'data': 'integ1@gmail.com'},
                           )
    actual = response.json()
    AccountProcessor.EMAIL_ENABLED = False
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == 'Email already confirmed!'
    assert actual['data'] is None


def test_overwrite_password_for_non_matching_passwords():
    AccountProcessor.EMAIL_ENABLED = True
    response = client.post(
        "/api/account/password/change",
        json={
            "data": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJtYWlsX2lkIjoiaW50ZWcxQGdtYWlsLmNvbSJ9.Ycs1ROb1w6MMsx2WTA4vFu3-jRO8LsXKCQEB3fkoU20",
            "password": "Welcome@2",
            "confirm_password": "Welcume@2"},
    )
    actual = response.json()
    AccountProcessor.EMAIL_ENABLED = False
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual['data'] is None


def test_add_and_delete_intents_by_integration_user():
    response = client.get(
        "/api/auth/integration/token",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    token = response.json()
    assert token["success"]
    assert token["error_code"] == 0
    assert token["data"]["access_token"]
    assert token["data"]["token_type"]

    response = client.post(
        "/api/bot/intents",
        headers={
            "Authorization": token["data"]["token_type"]
                             + " "
                             + token["data"]["access_token"],
            "X-USER": "integration",
        },
        json={"data": "integration_intent"},
    )
    actual = response.json()
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Intent added successfully!"

    response = client.delete(
        "/api/bot/intents/integration_intent/True",
        headers={
            "Authorization": token["data"]["token_type"]
                             + " "
                             + token["data"]["access_token"],
            "X-USER": "integration1",
        },
    )

    actual = response.json()
    assert actual['data'] is None
    assert actual['error_code'] == 0
    assert actual['message'] == "Intent deleted!"
    assert actual['success']


def test_add_non_Integration_Intent_and_delete_intent_by_integration_user():
    response = client.get(
        "/api/auth/integration/token",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    token = response.json()
    assert token["success"]
    assert token["error_code"] == 0
    assert token["data"]["access_token"]
    assert token["data"]["token_type"]

    response = client.post(
        "/api/bot/intents",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"data": "non_integration_intent"},
    )
    actual = response.json()
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Intent added successfully!"

    response = client.delete(
        "/api/bot/intents/non_integration_intent/True",
        headers={
            "Authorization": token["data"]["token_type"]
                             + " "
                             + token["data"]["access_token"],
            "X-USER": "integration1",
        },
    )

    actual = response.json()
    assert actual['data'] is None
    assert actual['error_code'] == 422
    assert actual['message'] == "This intent cannot be deleted by an integration user"
    assert not actual['success']


def test_add_http_action_malformed_url():
    request_body = {
        "auth_token": "",
        "action_name": "new_http_action",
        "response": "",
        "http_url": "192.168.104.1/api/test",
        "request_method": "GET",
        "http_params_list": [{
            "key": "testParam1",
            "parameter_type": "value",
            "value": "testValue1"
        }]
    }
    response = client.post(
        url="/api/bot/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"]
    assert not actual["success"]


def test_add_http_action_invalid_req_method():
    request_body = {
        "auth_token": "",
        "action_name": "new_http_action",
        "response": "",
        "http_url": "http://www.google.com",
        "request_method": "TUP",
        "http_params_list": [{
            "key": "testParam1",
            "parameter_type": "value",
            "value": "testValue1"
        }]
    }
    response = client.post(
        url="/api/bot/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"]
    assert not actual["success"]


def test_add_http_action_no_action_name():
    request_body = {
        "auth_token": "",
        "action_name": "",
        "response": "string",
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "http_params_list": [{
            "key": "testParam1",
            "parameter_type": "value",
            "value": "testValue1"
        }]
    }

    response = client.post(
        url="/api/bot/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"]
    assert not actual["success"]


def test_add_http_action_no_token():
    request_body = {
        "auth_token": "",
        "action_name": "test_add_http_action_no_token",
        "response": "string",
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "http_params_list": [{
            "key": "testParam1",
            "parameter_type": "value",
            "value": "testValue1"
        }]
    }

    response = client.post(
        url="/api/bot/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"]
    assert actual["success"]


def test_add_http_action_with_token():
    request_body = {
        "auth_token": "bearer dfiuhdfishifoshfoishnfoshfnsifjfs",
        "action_name": "test_add_http_action_with_token_and_story",
        "response": "string",
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "http_params_list": [{
            "key": "testParam1",
            "parameter_type": "value",
            "value": "testValue1"
        }, {
            "key": "testParam1",
            "parameter_type": "value",
            "value": "testValue1"
        }, {
            "key": "testParam1",
            "parameter_type": "value",
            "value": "testValue1"
        }]
    }

    response = client.post(
        url="/api/bot/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"]
    assert actual["success"]

    response = client.get(
        url="/api/bot/action/httpaction/test_add_http_action_with_token_and_story",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual['data']["response"] == "string"
    assert actual['data']["auth_token"] == "bearer dfiuhdfishifoshfoishnfoshfnsifjfs"
    assert actual['data']["http_url"] == "http://www.google.com"
    assert actual['data']["request_method"] == "GET"
    assert len(actual['data']["params_list"]) == 3
    assert actual["success"]


def test_add_http_action_no_params():
    request_body = {
        "auth_token": "",
        "action_name": "test_add_http_action_no_params",
        "response": "string",
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "http_params_list": []
    }

    response = client.post(
        url="/api/bot/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"]
    assert actual["success"]


def test_add_http_action_existing():
    request_body = {
        "auth_token": "",
        "action_name": "test_add_http_action_existing",
        "response": "string",
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "http_params_list": [{
            "key": "testParam1",
            "parameter_type": "value",
            "value": "testValue1"
        }]
    }

    response = client.post(
        url="/api/bot/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0

    response = client.post(
        url="/api/bot/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"]
    assert not actual["success"]


def test_get_http_action_non_exisitng():
    response = client.get(
        url="/api/bot/action/httpaction/never_added",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] is not None
    assert not actual["success"]


def test_update_http_action():
    request_body = {
        "auth_token": "",
        "action_name": "test_update_http_action",
        "response": "",
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "http_params_list": [{
            "key": "testParam1",
            "parameter_type": "value",
            "value": "testValue1"
        }]
    }

    response = client.post(
        url="/api/bot/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0

    request_body = {
        "auth_token": "bearer hjklfsdjsjkfbjsbfjsvhfjksvfjksvfjksvf",
        "action_name": "test_update_http_action",
        "response": "json",
        "http_url": "http://www.alphabet.com",
        "request_method": "POST",
        "http_params_list": [{
            "key": "testParam1",
            "parameter_type": "value",
            "value": "testValue1"
        }, {
            "key": "testParam2",
            "parameter_type": "slot",
            "value": "testValue1"
        }]
    }
    response = client.put(
        url="/api/bot/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0

    response = client.get(
        url="/api/bot/action/httpaction/test_update_http_action",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual['data']["response"] == "json"
    assert actual['data']["auth_token"] == "bearer hjklfsdjsjkfbjsbfjsvhfjksvfjksvfjksvf"
    assert actual['data']["http_url"] == "http://www.alphabet.com"
    assert actual['data']["request_method"] == "POST"
    assert len(actual['data']["params_list"]) == 2
    assert actual['data']["params_list"][0]['key'] == 'testParam1'
    assert actual['data']["params_list"][0]['parameter_type'] == 'value'
    assert actual['data']["params_list"][0]['value'] == 'testValue1'
    assert actual["success"]


def test_update_http_action_non_existing():
    request_body = {
        "auth_token": "",
        "action_name": "test_update_http_action_non_existing",
        "response": "",
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "http_params_list": []
    }

    response = client.post(
        url="/api/bot/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    request_body = {
        "auth_token": "bearer hjklfsdjsjkfbjsbfjsvhfjksvfjksvfjksvf",
        "action_name": "test_update_http_action_non_existing_new",
        "response": "json",
        "http_url": "http://www.alphabet.com",
        "request_method": "POST",
        "http_params_list": [{
            "key": "param1",
            "value": "value1",
            "parameter_type": "value"},
            {
                "key": "param2",
                "value": "value2",
                "parameter_type": "slot"}]
    }
    response = client.put(
        url="/api/bot/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"]
    assert not actual["success"]


def test_delete_http_action():
    request_body = {
        "auth_token": "",
        "action_name": "test_delete_http_action",
        "response": "",
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "http_params_list": []
    }

    response = client.post(
        url="/api/bot/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    response = client.delete(
        url="/api/bot/action/httpaction/test_delete_http_action",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"]
    assert actual["success"]


def test_delete_http_action_non_existing():
    request_body = {
        "auth_token": "",
        "action_name": "new_http_action4",
        "response": "",
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "http_params_list": []
    }

    client.post(
        url="/api/bot/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    response = client.delete(
        url="/api/bot/action/httpaction/new_http_action_never_added",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"]
    assert not actual["success"]


@responses.activate
def test_train_using_event(monkeypatch):
    responses.add(
        responses.POST,
        "http://localhost/train",
        status=200
    )
    monkeypatch.setitem(Utility.environment['model']['train'], "event_url", "http://localhost/train")
    response = client.post(
        "/api/bot/train",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "Model training started."


def test_update_training_data_generator_status(monkeypatch):
    request_body = {
        "status": TRAINING_DATA_GENERATOR_STATUS.INITIATED
    }
    response = client.put(
        "/api/bot/update/data/generator/status",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "Status updated successfully!"


def test_get_training_data_history(monkeypatch):
    response = client.get(
        "/api/bot/data/generation/history",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    response = actual["data"]
    assert response is not None
    response['status'] = 'Initiated'
    assert actual["message"] is None

def test_update_training_data_generator_status_completed(monkeypatch):
    training_data = [{
        "intent": "intent1_test_add_training_data",
        "training_examples": ["example1", "example2"],
        "response": "response1"},
        {"intent": "intent2_test_add_training_data",
         "training_examples": ["example3", "example4"],
         "response": "response2"}]
    request_body = {
        "status": TRAINING_DATA_GENERATOR_STATUS.COMPLETED,
        "response": training_data
    }
    response = client.put(
        "/api/bot/update/data/generator/status",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "Status updated successfully!"


def test_add_training_data(monkeypatch):
    response = client.get(
        "/api/bot/data/generation/history",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    response = actual["data"]
    assert response is not None
    response['status'] = 'Initiated'
    assert actual["message"] is None
    print(response)
    doc_id = response['training_history'][0]['_id']
    training_data = {
        "history_id": doc_id,
        "training_data": [{
        "intent": "intent1_test_add_training_data",
        "training_examples": ["example1", "example2"],
        "response": "response1"},
        {"intent": "intent2_test_add_training_data",
         "training_examples": ["example3", "example4"],
         "response": "response2"}]}
    response = client.post(
        "/api/bot/data/bulk",
        json=training_data,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is not None
    assert actual["message"] == "Training data added successfully!"

    assert Intents.objects(name="intent1_test_add_training_data").get() is not None
    assert Intents.objects(name="intent2_test_add_training_data").get() is not None
    training_examples = list(TrainingExamples.objects(intent="intent1_test_add_training_data"))
    assert training_examples is not None
    assert len(training_examples) == 2
    training_examples = list(TrainingExamples.objects(intent="intent2_test_add_training_data"))
    assert len(training_examples) == 2
    assert Responses.objects(name="utter_intent1_test_add_training_data") is not None
    assert Responses.objects(name="utter_intent2_test_add_training_data") is not None
    story = Stories.objects(block_name="path_intent1_test_add_training_data").get()
    assert story is not None
    assert story['events'][0]['name'] == 'intent1_test_add_training_data'
    assert story['events'][0]['type'] == StoryEventType.user
    assert story['events'][1]['name'] == "utter_intent1_test_add_training_data"
    assert story['events'][1]['type'] == StoryEventType.action
    story = Stories.objects(block_name="path_intent2_test_add_training_data").get()
    assert story is not None
    assert story['events'][0]['name'] == 'intent2_test_add_training_data'
    assert story['events'][0]['type'] == StoryEventType.user
    assert story['events'][1]['name'] == "utter_intent2_test_add_training_data"
    assert story['events'][1]['type'] == StoryEventType.action


def test_get_training_data_history_1(monkeypatch):
    response = client.get(
        "/api/bot/data/generation/history",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] is None
    training_data = actual["data"]['training_history'][0]

    assert training_data['status'] == TRAINING_DATA_GENERATOR_STATUS.COMPLETED.value
    end_timestamp = training_data['end_timestamp']
    assert end_timestamp is not None
    assert training_data['last_update_timestamp'] == end_timestamp
    response = training_data['response']
    assert response is not None
    assert response[0]['intent'] == 'intent1_test_add_training_data'
    assert response[0]['training_examples'][0]['training_example'] == "example1"
    assert response[0]['training_examples'][0]['is_persisted']
    assert response[0]['training_examples'][1]['training_example'] == "example2"
    assert response[0]['training_examples'][1]['is_persisted']
    assert response[0]['response'] == 'response1'
    assert response[1]['intent'] == 'intent2_test_add_training_data'
    assert response[1]['training_examples'][0]['training_example'] == "example3"
    assert response[1]['training_examples'][0]['is_persisted']
    assert response[1]['training_examples'][1]['training_example'] == "example4"
    assert response[1]['training_examples'][1]['is_persisted']
    assert response[1]['response'] == 'response2'


def test_update_training_data_generator_status_exception(monkeypatch):
    request_body = {
        "status": TRAINING_DATA_GENERATOR_STATUS.INITIATED,
    }
    response = client.put(
        "/api/bot/update/data/generator/status",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "Status updated successfully!"

    request_body = {
        "status": TRAINING_DATA_GENERATOR_STATUS.FAIL,
        "exception": 'Exception message'
    }
    response = client.put(
        "/api/bot/update/data/generator/status",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "Status updated successfully!"


def test_get_training_data_history_2(monkeypatch):
    response = client.get(
        "/api/bot/data/generation/history",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] is None
    training_data = actual["data"]['training_history'][0]
    assert training_data['status'] == TRAINING_DATA_GENERATOR_STATUS.FAIL.value
    end_timestamp = training_data['end_timestamp']
    assert end_timestamp is not None
    assert training_data['last_update_timestamp'] == end_timestamp
    assert training_data['exception'] == 'Exception message'


def test_fetch_latest(monkeypatch):
    request_body = {
        "status": TRAINING_DATA_GENERATOR_STATUS.INITIATED,
    }
    response = client.put(
        "/api/bot/update/data/generator/status",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    response = client.get(
        "/api/bot/data/generation/latest",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    print(actual["data"])
    assert actual["data"]['status'] == TRAINING_DATA_GENERATOR_STATUS.INITIATED.value
    assert actual["message"] is None


async def mock_upload(doc):
    if not (doc.filename.lower().endswith('.pdf') or doc.filename.lower().endswith('.docx')):
        raise AppException("Invalid File Format")


@pytest.fixture
def mock_file_upload(monkeypatch):
    def _in_progress_mock(*args, **kwargs):
        return None
    def _daily_limit_mock(*args, **kwargs):
        return None
    def _set_status_mock(*args, **kwargs):
        return None
    def _train_data_gen(*args, **kwargs):
        return None

    monkeypatch.setattr(TrainingDataGenerationProcessor, "is_in_progress", _in_progress_mock)
    monkeypatch.setattr(TrainingDataGenerationProcessor, "check_data_generation_limit", _daily_limit_mock)
    monkeypatch.setattr(TrainingDataGenerationProcessor, "set_status", _set_status_mock)
    monkeypatch.setattr(Utility, "trigger_data_generation_event", _train_data_gen)


def test_file_upload_docx(mock_file_upload,monkeypatch):
    monkeypatch.setattr(Utility,"upload_document",mock_upload)


    response = client.post(
        "/api/bot/upload/data_generation/file",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files={"doc": (
            "tests/testing_data/file_data/sample1.docx",
            open("tests/testing_data/file_data/sample1.docx", "rb"))})


    actual = response.json()
    assert actual["message"] == "File uploaded successfully and training data generation has begun"
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]


def test_file_upload_pdf(mock_file_upload,monkeypatch):
    monkeypatch.setattr(Utility,"upload_document",mock_upload)


    response = client.post(
        "/api/bot/upload/data_generation/file",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files={"doc": (
            "tests/testing_data/file_data/sample1.pdf",
            open("tests/testing_data/file_data/sample1.pdf", "rb"))})


    actual = response.json()
    assert actual["message"] == "File uploaded successfully and training data generation has begun"
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]


def test_file_upload_error(mock_file_upload,monkeypatch):
    monkeypatch.setattr(Utility,"upload_document",mock_upload)


    response = client.post(
        "/api/bot/upload/data_generation/file",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files={"doc": (
            "tests/testing_data/all/data/nlu.md",
            open("tests/testing_data/all/data/nlu.md", "rb"))})


    actual = response.json()
    assert actual["message"] == "Invalid File Format"
    assert actual["error_code"] == 422
    assert not actual["success"]
