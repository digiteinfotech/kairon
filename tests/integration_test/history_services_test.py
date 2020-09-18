import json
import os

from fastapi.testclient import TestClient
from mongoengine import connect
import pytest
from rasa.core.domain import Domain
from rasa.core.tracker_store import DialogueStateTracker

from kairon.api.app.main import app
from kairon.api.processor import AccountProcessor
from kairon.data_processor.history import ChatHistory
from kairon.data_processor.processor import MongoProcessor
from kairon.utils import Utility
from mongomock import MongoClient
client = TestClient(app)

def pytest_configure():
    return {'token_type': None,
            'access_token': None
            }

@pytest.fixture(autouse=True)
def setup():
    os.environ["system_file"] = "./tests/testing_data/system.yaml"
    Utility.load_evironment()
    connect(host=Utility.environment['database']["url"])


def user_details(*args, **kwargs):
    return {
        "email": "integration@demo.com",
        "password": Utility.get_password_hash("welcome@1"),
        "first_name": "integration",
        "last_name": "test",
        "status": True,
        "bot": "integration",
        "account": 1,
        "is_integration_user": False,
    }


@pytest.fixture
def mock_auth(monkeypatch):
    monkeypatch.setattr(AccountProcessor, "get_user_details", user_details)


def endpoint_details(*args, **kwargs):
    return {"tracker_endpoint": {"url": "mongodb://demo", "db": "conversation"}}


@pytest.fixture
def mock_mongo_processor(monkeypatch):
    monkeypatch.setattr(MongoProcessor, "get_endpoints", endpoint_details)

@pytest.fixture
def mock_db_client(monkeypatch):
    def db_client(*args, **kwargs):
        return MongoClient(), "conversation", "conversations", None
    monkeypatch.setattr(ChatHistory, "get_mongo_connection", db_client)


def history_users(*args, **kwargs):
    return [
        "5b029887-bed2-4bbb-aa25-bd12fda26244",
        "b868d6ee-f98f-4c1b-b284-ce034aaad01f",
        "b868d6ee-f98f-4c1b-b284-ce034aaad61f",
        "b868d6ee-f98f-4c1b-b284-ce4534aaad61f",
        "49931985-2b51-4db3-89d5-a50767e6d98e",
        "2e409e7c-06f8-4de8-8c88-93b4cf0b7211",
        "2fed7769-b647-4088-8ed9-a4f4f3653f25",
    ], None


def user_history(*args, **kwargs):
    json_data = json.load(open("tests/testing_data/history/conversation.json"))
    return (
        json_data['events'],
        None
    )


def history_conversations(*args, **kwargs):
    json_data = json.load(open("tests/testing_data/history/conversations_history.json"))
    return json_data, None


@pytest.fixture
def mock_chat_history(monkeypatch):
    monkeypatch.setattr(ChatHistory, "fetch_user_history", user_history)
    monkeypatch.setattr(ChatHistory, "get_conversations", history_conversations)
    monkeypatch.setattr(ChatHistory, "fetch_chat_users", history_users)




def test_chat_history_users_connection_error(mock_auth, mock_mongo_processor):
    response = client.post(
        "/api/auth/login",
        data={"username": "integration@demo.com", "password": "welcome@1"},
    )
    token_response = response.json()
    pytest.access_token = token_response["data"]["access_token"]
    pytest.token_type = token_response["data"]["token_type"]

    response = client.get(
        "/api/history/users",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"]
    assert not actual["success"]


def test_chat_history_users(mock_auth, mock_chat_history):
    response = client.get(
        "/api/history/users",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert len(actual["data"]["users"]) == 7
    assert actual["message"] is None
    assert actual["success"]


def test_chat_history(mock_auth, mock_chat_history):
    response = client.get(
        "/api/history/users/5e564fbcdcf0d5fad89e3acd",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert len(actual["data"]["history"]) == 12
    assert actual["message"] is None
    assert actual["success"]


def test_visitor_hit_fallback(mock_auth, mock_db_client):
    response = client.get(
        "/api/history/metrics/fallback",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["fallback_count"] == 0
    assert actual["data"]["total_count"] == 0
    assert actual["message"] is None
    assert actual["success"]


def test_conversation_steps(mock_auth, mock_db_client):
    response = client.get(
        "/api/history/metrics/conversation/steps",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert len(actual["data"]) == 0
    assert actual["message"] is None
    assert actual["success"]


def test_conversation_time(mock_auth, mock_db_client):
    response = client.get(
        "/api/history/metrics/conversation/time",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert len(actual["data"]) == 0
    assert actual["message"] is None
    assert actual["success"]


def test_user_with_metrics(mock_auth, mock_db_client):
    response = client.get(
        "/api/history/metrics/users",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["users"] == []
    assert actual["message"] is None
    assert actual["success"]