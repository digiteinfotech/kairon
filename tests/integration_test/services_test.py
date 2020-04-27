import logging
import os

import pytest
import responses
from fastapi.testclient import TestClient
from mongoengine import connect

from bot_trainer.api.app.main import app
from bot_trainer.api.processor import AccountProcessor
from bot_trainer.data_processor.processor import MongoProcessor
from bot_trainer.utils import Utility

logging.basicConfig(level=logging.DEBUG)
os.environ["system_file"] = "./tests/testing_data/system.yaml"

client = TestClient(app)


def pytest_namespace():
    return {"access_token": None, "token_type": None, "user_created": False}


def add_user():
    Utility.load_evironment()
    connect(Utility.environment["mongo_db"], host=Utility.environment["mongo_url"])
    account = AccountProcessor.add_account("integration", "testAdmin")
    bot = AccountProcessor.add_bot("integration", account["_id"], "testAdmin")
    AccountProcessor.add_user(
        email="integration@demo.ai",
        first_name="Demo",
        last_name="User",
        password="welcome@1",
        account=account["_id"],
        bot=bot["name"],
        user="testAdmin",
    )

    account = AccountProcessor.add_account("integration2", "testAdmin")
    bot = AccountProcessor.add_bot("integration2", account["_id"], "testAdmin")
    AccountProcessor.add_user(
        email="integration2@demo.ai",
        first_name="Demo",
        last_name="User",
        password="welcome@1",
        account=account["_id"],
        bot=bot["name"],
        user="testAdmin",
    )


add_user()
processor = MongoProcessor()
processor.save_from_path("tests/testing_data/all", "1_integration", "testAdmin")


def test_api_wrong_login():
    response = client.post(
        "/api/auth/login", data={"username": "test@demo.ai", "password": "welcome@1"}
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert not actual["success"]
    assert actual["message"] == "User does not exists!"


# need to write test cases for inactive user ,bot and account
def test_api_login():
    response = client.post(
        "/api/auth/login",
        data={"username": "integration@demo.ai", "password": "welcome@1"},
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


def test_get_intents():
    response = client.get(
        "/api/bot/intents",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert "data" in actual
    assert len(actual["data"]) == 22
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
    assert (
            actual["data"][0]["message"]
            == "Training Example already exists!"
    )
    assert (
            actual["data"][0]["_id"] is None
    )


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
        == "Training Example name and text cannot be empty or blank spaces"
    )
    assert (
            actual["data"][0]["_id"] is None
    )


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
    assert actual["message"] == "Training Example removed successfully!"
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


def test_get_responses():
    response = client.get(
        "/api/bot/response/utter_greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    print(actual)
    assert len(actual["data"]) == 1
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
    assert actual["message"] == "Response added successfully!"
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
    assert actual["message"] == "Response already exists!"


def test_add_empty_response():
    response = client.post(
        "/api/bot/response/utter_greet",
        json={"data": ""},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    print(actual)
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Response text cannot be empty or blank spaces"


def test_remove_response():
    training_examples = client.get(
        "/api/bot/response/utter_greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    training_examples = training_examples.json()
    assert len(training_examples["data"]) == 2
    response = client.delete(
        "/api/bot/response",
        json={"data": training_examples["data"][0]["_id"]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    print(actual)
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Response removed successfully!"
    training_examples = client.get(
        "/api/bot/response/utter_greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    training_examples = training_examples.json()
    assert len(training_examples["data"]) == 1


def test_remove_response_empty_id():
    response = client.delete(
        "/api/bot/response",
        json={"data": ""},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Unable to remove document"


def test_add_story():
    response = client.post(
        "/api/bot/stories",
        json={
            "name": "test_path",
            "events": [
                {"name": "greet", "type": "user"},
                {"name": "utter_greet", "type": "action"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    print(actual)
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Story added successfully"
    assert actual["data"]["_id"]


def test_add_story_empty_event():
    response = client.post(
        "/api/bot/stories",
        json={"name": "test_path", "events": []},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Stories cannot be empty"


def test_add_story_missing_event_type():
    response = client.post(
        "/api/bot/stories",
        json={
            "name": "test_path",
            "events": [{"name": "greet"}, {"name": "utter_greet", "type": "action"}],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    print(actual)
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert (
        actual["message"]
        == "1 validation error for Request\nbody -> story -> events -> 0 -> type\n  field required (type=value_error.missing)"
    )


def test_add_story_invalid_event_type():
    response = client.post(
        "/api/bot/stories",
        json={
            "name": "test_path",
            "events": [
                {"name": "greet", "type": "data"},
                {"name": "utter_greet", "type": "action"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    print(actual)
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert (
        actual["message"]
        == "1 validation error for Request\nbody -> story -> events -> 0 -> type\n  value is not a valid enumeration member; permitted: 'user', 'action', 'form', 'slot' (type=type_error.enum; enum_values=[<StoryEventType.user: 'user'>, <StoryEventType.action: 'action'>, <StoryEventType.form: 'form'>, <StoryEventType.slot: 'slot'>])"
    )


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
    assert actual["data"]
    assert Utility.check_empty_string(actual["message"])


def test_get_utterance_from_not_exist_intent():
    response = client.get(
        "/api/bot/utterance_from_intent/greeting",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert Utility.check_empty_string(actual["message"])


def test_train():
    response = client.post(
        "/api/bot/train",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    print(actual)
    assert actual["success"]
    assert actual["error_code"] is 0
    assert actual["data"]
    assert actual["message"] == "Model trained successfully"


def test_train_empty():
    response = client.post(
        "/api/auth/login",
        data={"username": "integration2@demo.ai", "password": "welcome@1"},
    )
    token = response.json()
    response = client.post(
        "/api/bot/train",
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
    assert actual["message"] == "Training data does not exists!"


def test_chat():
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


def test_chat_fetch_from_cache():
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
        data={"username": "integration2@demo.ai", "password": "welcome@1"},
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
    assert actual["message"] == "Please train the bot first"


def test_deploy_missing_configuration():
    response = client.post(
        "/api/bot/deploy",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    print(actual)
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"] == "Please configure the bot endpoint for deployment!"

def endpoint_response(*args, **kwargs):
    return {"bot_endpoint": {"url": "http://localhost:5000"}}

@pytest.fixture
def mock_endpoint(monkeypatch):
    monkeypatch.setattr(MongoProcessor,"get_endpoints", endpoint_response)

@responses.activate
def test_deploy(mock_endpoint):
    responses.add(responses.PUT, "http://localhost:5000/model", json="Model was successfully replaced.",status=200)
    response = client.post("/api/bot/deploy",
                           headers={"Authorization": pytest.token_type + " " + pytest.access_token}
                           )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "Model was successfully replaced."


@responses.activate
def test_deploy_bad_request(mock_endpoint):
    responses.add(responses.PUT,
                  "http://localhost:5000/model",
                  json={"version": "1.0.0",
                        "status": "failure",
                        "reason": "BadRequest",
                        "code": 400
                        },
                  status=200)
    response = client.post("/api/bot/deploy",
                           headers={"Authorization": pytest.token_type + " " + pytest.access_token}
                           )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "BadRequest"


@responses.activate
def test_deploy_server_error(mock_endpoint):
    responses.add(responses.PUT,
                  "http://localhost:5000/model",
                  json={
                      "version": "1.0.0",
                      "status": "ServerError",
                      "message": "An unexpected error occurred.",
                      "code": 500
                  },
                  status=200)
    response = client.post("/api/bot/deploy",
                           headers={"Authorization": pytest.token_type + " " + pytest.access_token}
                           )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "An unexpected error occurred."


def test_integration_token():
    response = client.get("/api/auth/integration/token",
                           headers={"Authorization": pytest.token_type + " " + pytest.access_token}
                           )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]['access_token']
    assert actual["data"]['token_type']
    assert actual["message"] == '''It is your responsibility to keep the token secret.
        If leaked then other may have access to your system.'''
    response = client.get(
        "/api/bot/intents",
        headers={"Authorization": actual["data"]['token_type'] + " " + actual["data"]['access_token'],
                 "X-USER": "integration"},
    )
    actual = response.json()
    assert "data" in actual
    assert len(actual["data"]) == 23
    assert actual["success"]
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])


def test_integration_token_missing_x_user():
    response = client.get("/api/auth/integration/token",
                           headers={"Authorization": pytest.token_type + " " + pytest.access_token}
                           )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]['access_token']
    assert actual["data"]['token_type']
    assert actual["message"] == '''It is your responsibility to keep the token secret.
        If leaked then other may have access to your system.'''
    response = client.get(
        "/api/bot/intents",
        headers={"Authorization": actual["data"]['token_type'] + " " + actual["data"]['access_token']}
    )
    actual = response.json()
    assert actual["data"] is None
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == 'Alias user missing for integration'


def test_predict_intent():
    response = client.post("/api/bot/intents/predict",
                          headers={"Authorization": pytest.token_type + " " + pytest.access_token},
                          json={"data": "Hi"},
                          )

    actual = response.json()
    assert actual.get('data').get("intent")
    assert actual.get('data').get("confidence")


def test_predict_intent_error():
    response = client.post(
        "/api/auth/login",
        data={"username": "integration2@demo.ai", "password": "welcome@1"},
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
    assert actual["message"] == "Please train the bot first"


@responses.activate
def test_augment_questions():
    responses.add(responses.POST,
                  "http://localhost:8000/questions",
                  json={
                      "sucess": True,
                      "data": {"questions":['where is digite centrally located?',
                     'where is digite conveniently located?',
                     'where is digite islocated?',
                     'where is digite situated?',
                     'where is digite strategically located?']},
                      "message": None,
                      "error_code": 0
                  },
                  status=200)
    response = client.post("/api/augment/questions",
                           headers={"Authorization": pytest.token_type + " " + pytest.access_token},
                           json = {"data":["where is digite located?'"]}
                           )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]
    assert Utility.check_empty_string(actual["message"])

