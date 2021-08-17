import json
import os

from fastapi.testclient import TestClient
from mongoengine import connect
import pytest

from kairon.api.processor import AccountProcessor
from kairon.data_processor.processor import MongoProcessor
from kairon.history.main import app
from kairon.history.processor import ChatHistory
from kairon.utils import Utility
from mongomock import MongoClient
client = TestClient(app)


def pytest_configure():
    return {'token_type': None,
            'access_token': None,
            'bot': None
            }


@pytest.fixture(autouse=True)
def setup():
    os.environ["system_file"] = "./tests/testing_data/system.yaml"
    Utility.load_evironment()
    Utility.environment['history_server']['is_deployed_with_kairon'] = True
    connect(host=Utility.environment['database']["url"])


def user_details(*args, **kwargs):
    pytest.bot = "integration"
    return {
        "email": "integration@demo.com",
        "password": Utility.get_password_hash("welcome@1"),
        "first_name": "integration",
        "last_name": "test",
        "status": True,
        "bot": [pytest.bot],
        "account": 1,
        "is_integration_user": False,
    }


def bot_details(*args, **kwargs):
    return {
        "user": "integration@demo.com",
        "status": True,
        "bot": pytest.bot,
        "account": 1,
    }


@pytest.fixture
def mock_auth(monkeypatch):
    monkeypatch.setattr(AccountProcessor, "get_user_details", user_details)
    monkeypatch.setattr(AccountProcessor, "get_bot", bot_details)


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
    monkeypatch.setattr(ChatHistory, "fetch_chat_users", history_users)


def test_chat_history_users_connection_error(mock_auth, mock_mongo_processor):
    from kairon.api.app.main import app
    login_client = TestClient(app)
    response = login_client.post(
        "/api/auth/login",
        data={"username": "integration@demo", "password": "welcome@1"},
    )
    token_response = response.json()
    pytest.access_token = token_response["data"]["access_token"]
    pytest.token_type = token_response["data"]["token_type"]

    response = client.get(
        f"/api/history/conversations/{pytest.bot}/users",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"]
    assert not actual["success"]


def test_chat_history_users(mock_auth, mock_chat_history):
    response = client.get(
        f"/api/history/conversations/{pytest.bot}/users",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert len(actual["data"]["users"]) == 7
    assert actual["message"] is None
    assert actual["success"]


def test_chat_history(mock_auth, mock_chat_history):
    response = client.get(
        f"/api/history/conversations/{pytest.bot}/users/5e564fbcdcf0d5fad89e3acd",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert len(actual["data"]["history"]) == 12
    assert actual["message"] is None
    assert actual["success"]


def test_visitor_hit_fallback(mock_auth, mock_db_client):
    response = client.get(
        f"/api/history/metrics/{pytest.bot}/fallback",
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
        f"/api/history/metrics/{pytest.bot}/conversation/steps",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert len(actual["data"]) == 0
    assert actual["message"] is None
    assert actual["success"]


def test_conversation_time(mock_auth, mock_db_client):
    response = client.get(
        f"/api/history/metrics/{pytest.bot}/conversation/time",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert len(actual["data"]) == 0
    assert actual["message"] is None
    assert actual["success"]


def test_user_with_metrics(mock_auth, mock_db_client):
    response = client.get(
        f"/api/history/metrics/{pytest.bot}/users",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["users"] == []
    assert actual["message"] is None
    assert actual["success"]


def test_engaged_users(mock_auth, mock_db_client):
    response = client.get(
        f"/api/history/metrics/{pytest.bot}/user/engaged",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["engaged_users"] == 0
    assert actual["message"] is None
    assert actual["success"]


def test_new_users(mock_auth, mock_db_client):
    response = client.get(
        f"/api/history/metrics/{pytest.bot}/user/new",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["new_users"] == 0
    assert actual["message"] is None
    assert actual["success"]


def test_successful_conversation(mock_auth, mock_db_client):
    response = client.get(
        f"/api/history/metrics/{pytest.bot}/conversation/success",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["successful_conversations"] == 0
    assert actual["message"] is None
    assert actual["success"]


def test_user_retention(mock_auth, mock_db_client):
    response = client.get(
        f"/api/history/metrics/{pytest.bot}/user/retention",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["user_retention"] == 0
    assert actual["message"] is None
    assert actual["success"]


def test_engaged_user_range(mock_auth, mock_db_client):
    response = client.get(
        f"/api/history/trends/{pytest.bot}/users/engaged",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]['engaged_user_range'] == {}
    assert actual["message"] is None
    assert actual["success"]


def test_new_user_range(mock_auth, mock_db_client):
    response = client.get(
        f"/api/history/trends/{pytest.bot}/users/new",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]['new_user_range'] == {}
    assert actual["message"] is None
    assert actual["success"]


def test_successful_conversation_range(mock_auth, mock_db_client):
    response = client.get(
        f"/api/history/trends/{pytest.bot}/conversations/success",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["success_conversation_range"] == {}
    assert actual["message"] is None
    assert actual["success"]


def test_user_retention_range(mock_auth, mock_db_client):
    response = client.get(
        f"/api/history/trends/{pytest.bot}/users/retention",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["retention_range"] == {}
    assert actual["message"] is None
    assert actual["success"]


def test_engaged_users_with_value(mock_auth, mock_db_client):
    response = client.get(
        f"/api/history/metrics/{pytest.bot}/user/engaged?month=5&conversation_step_threshold=11",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["engaged_users"] == 0
    assert actual["message"] is None
    assert actual["success"]


def test_engaged_user_range_with_value(mock_auth, mock_db_client):
    response = client.get(
        f"/api/history/trends/{pytest.bot}/users/engaged/?month=5&conversation_step_threshold=11",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]['engaged_user_range'] == {}
    assert actual["message"] is None
    assert actual["success"]


def test_fallback_count_range(mock_auth, mock_db_client):
    response = client.get(
        f"/api/history/trends/{pytest.bot}/fallback",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["fallback_counts"] == {}
    assert actual["message"] is None
    assert actual["success"]


def test_flat_conversations(mock_auth, mock_db_client):
    response = client.get(
        f"/api/history/conversations/{pytest.bot}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["conversation_data"] == []
    assert actual["message"] is None
    assert actual["success"]


def mock_flatten_api_with_data(*args, **kwargs):
    return {"conversation_data": [{"test_key": "test_value"}]}, None


def mock_flatten_api_with_no_data(*args, **kwargs):
    return {"conversation_data": []}, None


def mock_flatten_api_with_error(*args, **kwargs):
    return {"conversation_data": []}, "error_message"


def test_download_conversation_with_data(mock_auth, monkeypatch):
    monkeypatch.setattr(ChatHistory, 'flatten_conversations', mock_flatten_api_with_data)
    response = client.get(
        f"/api/history/conversations/{pytest.bot}/download",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    assert "test_value" in str(response.content)


def test_download_conversation_with_no_data(mock_auth, monkeypatch):
    monkeypatch.setattr(ChatHistory, 'flatten_conversations', mock_flatten_api_with_no_data)
    response = client.get(
        f"/api/history/conversations/{pytest.bot}/download",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == "No data available!"
    assert not actual["success"]


def test_download_conversation_with_error(mock_auth, monkeypatch):
    monkeypatch.setattr(ChatHistory, 'flatten_conversations', mock_flatten_api_with_error)
    response = client.get(
        f"/api/history/conversations/{pytest.bot}/download",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == "error_message"
    assert not actual["success"]
