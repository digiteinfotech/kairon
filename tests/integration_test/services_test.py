from bot_trainer.api.app.main import app
from fastapi.testclient import TestClient
import os
import pytest
from mongoengine import connect
from bot_trainer.utils import Utility
from bot_trainer.api.processor import AccountProcessor
from bot_trainer.data_processor.processor import MongoProcessor
import logging

logging.basicConfig(level=logging.DEBUG)
os.environ["system_file"] = "./tests/testing_data/system.yaml"

client = TestClient(app)


def pytest_namespace():
    return {"access_token": None, "token_type": None, "user_created": False}


def add_user():
    environment = Utility.load_evironment()
    connect(environment["mongo_db"], host=environment["mongo_url"])
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


add_user()
processor = MongoProcessor()
processor.save_from_path("tests/testing_data/all", "integration", "testAdmin")


def test_api_wrong_login():
    response = client.post(
        "/api/auth/login", data={"username": "test@demo.ai", "password": "welcome@1"}
    )
    actual = response.json()
    print(actual)
    assert actual["error_code"] == 400
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
    assert actual["data"]['_id']
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
    assert actual["error_code"] == 400
    assert actual["message"] == "Intent already exists!"


def test_add_empty_intents():
    response = client.post(
        "/api/bot/intents",
        json={"data": ""},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 400
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
        json={"data": "How do you do?"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"]['_id']
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Training Example added successfully!"
    response = client.get(
        "/api/bot/training_examples/greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert len(actual["data"]) == 9


def test_add_training_examples_duplicate():
    response = client.post(
        "/api/bot/training_examples/greet",
        json={"data": "How do you do?"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 400
    assert actual["message"] == "Training Example already exists!"


def test_add_empty_training_examples():
    response = client.post(
        "/api/bot/training_examples/greet",
        json={"data": ""},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    print(actual)
    assert not actual["success"]
    assert actual["error_code"] == 400
    assert actual["message"] == "Training Example name and text cannot be empty or blank spaces"


def test_remove_training_examples():
    training_examples = client.get(
        "/api/bot/training_examples/greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    training_examples = training_examples.json()
    assert len(training_examples["data"]) == 9
    response = client.delete(
        "/api/bot/training_examples",
        json={"data": training_examples['data'][0]['_id']},
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
    assert actual["error_code"] == 400
    assert actual["message"] == "Unable to remove document"

def test_get_responses():
    response = client.get(
        "/api/bot/responses/utter_greet",
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
        "/api/bot/responses/utter_greet",
        json={"data": "Wow! How are you?"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"]['_id']
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Response added successfully!"
    response = client.get(
        "/api/bot/responses/utter_greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert len(actual["data"]) == 2


def test_add_response_duplicate():
    response = client.post(
        "/api/bot/responses/utter_greet",
        json={"data": "Wow! How are you?"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 400
    assert actual["message"] == "Response already exists!"


def test_add_empty_response():
    response = client.post(
        "/api/bot/responses/utter_greet",
        json={"data": ""},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    print(actual)
    assert not actual["success"]
    assert actual["error_code"] == 400
    assert actual["message"] == "Response text cannot be empty or blank spaces"


def test_remove_response():
    training_examples = client.get(
        "/api/bot/responses/utter_greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    training_examples = training_examples.json()
    assert len(training_examples["data"]) == 2
    response = client.delete(
        "/api/bot/responses",
        json={"data": training_examples['data'][0]['_id']},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    print(actual)
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Response removed successfully!"
    training_examples = client.get(
        "/api/bot/responses/utter_greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    training_examples = training_examples.json()
    assert len(training_examples["data"]) == 1

def test_remove_response_empty_id():
    response = client.delete(
        "/api/bot/responses",
        json={"data": ""},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 400
    assert actual["message"] == "Unable to remove document"
