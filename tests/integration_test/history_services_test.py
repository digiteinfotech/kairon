import json
import os
os.environ["system_file"] = "./tests/testing_data/tracker.yaml"

from fastapi.testclient import TestClient
import pytest

from kairon.history.main import app
from kairon.history.processor import ChatHistory
from kairon.history.utils import HistoryUtils
from mongomock import MongoClient

client = TestClient(app)


def pytest_configure():
    return {'token_type': None,
            'access_token': None,
            'bot': None
            }


@pytest.fixture(autouse=True)
def setup():
    os.environ["system_file"] = "./tests/testing_data/tracker.yaml"
    HistoryUtils.load_environment()
    pytest.bot = '542872407658659274'


@pytest.fixture
def mock_db_client(monkeypatch):
    def db_client(*args, **kwargs):
        return MongoClient(), "conversation", None

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


def test_chat_history_users(mock_chat_history):
    response = client.get(
        f"/api/history/{pytest.bot}/conversations/users",
        headers={"Authorization": 'Bearer ' + HistoryUtils.environment['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert len(actual["data"]["users"]) == 7
    assert actual["message"] is None
    assert actual["success"]


def test_chat_history(mock_chat_history):
    response = client.get(
        f"/api/history/{pytest.bot}/conversations/users/5e564fbcdcf0d5fad89e3acd",
        headers={"Authorization": 'Bearer ' + HistoryUtils.environment['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert len(actual["data"]["history"]) == 12
    assert actual["message"] is None
    assert actual["success"]


def test_visitor_hit_fallback(mock_db_client):
    response = client.get(
        f"/api/history/{pytest.bot}/metrics/fallback",
        headers={"Authorization": 'Bearer ' + HistoryUtils.environment['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["fallback_count"] == 0
    assert actual["data"]["total_count"] == 0
    assert actual["message"] is None
    assert actual["success"]


def test_conversation_steps(mock_db_client):
    response = client.get(
        f"/api/history/{pytest.bot}/metrics/conversation/steps",
        headers={"Authorization": 'Bearer ' + HistoryUtils.environment['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert len(actual["data"]) == 0
    assert actual["message"] is None
    assert actual["success"]


def test_conversation_time(mock_db_client):
    response = client.get(
        f"/api/history/{pytest.bot}/metrics/conversation/time",
        headers={"Authorization": 'Bearer ' + HistoryUtils.environment['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert len(actual["data"]) == 0
    assert actual["message"] is None
    assert actual["success"]


def test_user_with_metrics(mock_db_client):
    response = client.get(
        f"/api/history/{pytest.bot}/metrics/users",
        headers={"Authorization": 'Bearer ' + HistoryUtils.environment['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["users"] == []
    assert actual["message"] is None
    assert actual["success"]


def test_engaged_users(mock_db_client):
    response = client.get(
        f"/api/history/{pytest.bot}/metrics/users/engaged",
        headers={"Authorization": 'Bearer ' + HistoryUtils.environment['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["engaged_users"] == 0
    assert actual["message"] is None
    assert actual["success"]


def test_new_users(mock_db_client):
    response = client.get(
        f"/api/history/{pytest.bot}/metrics/users/new",
        headers={"Authorization": 'Bearer ' + HistoryUtils.environment['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["new_users"] == 0
    assert actual["message"] is None
    assert actual["success"]


def test_successful_conversation(mock_db_client):
    response = client.get(
        f"/api/history/{pytest.bot}/metrics/conversation/success",
        headers={"Authorization": 'Bearer ' + HistoryUtils.environment['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["successful_conversations"] == 0
    assert actual["message"] is None
    assert actual["success"]


def test_successful_conversation_with_request(mock_db_client):
    response = client.get(
        f"/api/history/{pytest.bot}/metrics/conversation/success",
        json={'month': 4, 'action_fallback': 'action_default_fallback', 'nlu_fallback': 'utter_please_rephrase'},
        headers={"Authorization": 'Bearer ' + HistoryUtils.environment['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["successful_conversations"] == 0
    assert actual["message"] is None
    assert actual["success"]


def test_successful_conversation_with_request_and_static_collection(mock_db_client):
    HistoryUtils.environment['tracker']['type'] = 'static'
    response = client.get(
        f"/api/history/{pytest.bot}/metrics/conversation/success",
        json={'month': 4, 'action_fallback': 'action_default_fallback', 'nlu_fallback': 'utter_please_rephrase'},
        headers={"Authorization": 'Bearer ' + HistoryUtils.environment['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["successful_conversations"] == 0
    assert actual["message"] is None
    assert actual["success"]


def test_user_retention(mock_db_client):
    response = client.get(
        f"/api/history/{pytest.bot}/metrics/users/retention",
        headers={"Authorization": 'Bearer ' + HistoryUtils.environment['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["user_retention"] == 0
    assert actual["message"] is None
    assert actual["success"]


def test_engaged_user_range(mock_db_client):
    response = client.get(
        f"/api/history/{pytest.bot}/trends/users/engaged",
        headers={"Authorization": 'Bearer ' + HistoryUtils.environment['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]['engaged_user_range'] == {}
    assert actual["message"] is None
    assert actual["success"]


def test_new_user_range(mock_db_client):
    response = client.get(
        f"/api/history/{pytest.bot}/trends/users/new",
        headers={"Authorization": 'Bearer ' + HistoryUtils.environment['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]['new_user_range'] == {}
    assert actual["message"] is None
    assert actual["success"]


def test_successful_conversation_range(mock_db_client):
    response = client.get(
        f"/api/history/{pytest.bot}/trends/conversations/success",
        headers={"Authorization": 'Bearer ' + HistoryUtils.environment['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["success_conversation_range"] == {}
    assert actual["message"] is None
    assert actual["success"]


def test_successful_conversation_range_with_request(mock_db_client):
    response = client.get(
        f"/api/history/{pytest.bot}/trends/conversations/success",
        json={'month': 4, 'action_fallback': 'action_default_fallback', 'nlu_fallback': 'utter_please_rephrase'},
        headers={"Authorization": 'Bearer ' + HistoryUtils.environment['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["success_conversation_range"] == {}
    assert actual["message"] is None
    assert actual["success"]


def test_user_retention_range(mock_db_client):
    response = client.get(
        f"/api/history/{pytest.bot}/trends/users/retention",
        headers={"Authorization": 'Bearer ' + HistoryUtils.environment['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["retention_range"] == {}
    assert actual["message"] is None
    assert actual["success"]


def test_engaged_users_with_value(mock_db_client):
    response = client.get(
        f"/api/history/{pytest.bot}/metrics/users/engaged",
        json={'month': 5, 'conversation_step_threshold': 11},
        headers={"Authorization": 'Bearer ' + HistoryUtils.environment['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["engaged_users"] == 0
    assert actual["message"] is None
    assert actual["success"]


def test_engaged_user_range_with_value(mock_db_client):
    response = client.get(
        f"/api/history/{pytest.bot}/trends/users/engaged",
        json={'month': 5, 'conversation_step_threshold': 11},
        headers={"Authorization": 'Bearer ' + HistoryUtils.environment['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]['engaged_user_range'] == {}
    assert actual["message"] is None
    assert actual["success"]


def test_fallback_count_range(mock_db_client):
    response = client.get(
        f"/api/history/{pytest.bot}/trends/fallback",
        headers={"Authorization": 'Bearer ' + HistoryUtils.environment['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["fallback_counts"] == {}
    assert actual["message"] is None
    assert actual["success"]


def test_fallback_count_range_with_request(mock_db_client):
    response = client.get(
        f"/api/history/{pytest.bot}/trends/fallback",
        json={'month': 4, 'action_fallback': 'action_default_fallback', 'nlu_fallback': 'utter_please_rephrase'},
        headers={"Authorization": 'Bearer ' + HistoryUtils.environment['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["fallback_counts"] == {}
    assert actual["message"] is None
    assert actual["success"]


def test_flat_conversations(mock_db_client):
    response = client.get(
        f"/api/history/{pytest.bot}/conversations",
        headers={"Authorization": 'Bearer ' + HistoryUtils.environment['authentication']['token']},
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


def test_download_conversation_with_data(monkeypatch):
    monkeypatch.setattr(ChatHistory, 'flatten_conversations', mock_flatten_api_with_data)
    response = client.get(
        f"/api/history/{pytest.bot}/conversations/download",
        headers={"Authorization": 'Bearer ' + HistoryUtils.environment['authentication']['token']},
    )
    assert "test_value" in str(response.content)


def test_download_conversation_with_no_data(monkeypatch):
    monkeypatch.setattr(ChatHistory, 'flatten_conversations', mock_flatten_api_with_no_data)
    response = client.get(
        f"/api/history/{pytest.bot}/conversations/download",
        headers={"Authorization": 'Bearer ' + HistoryUtils.environment['authentication']['token']},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == "No data available!"
    assert not actual["success"]


def test_download_conversation_with_error(monkeypatch):
    monkeypatch.setattr(ChatHistory, 'flatten_conversations', mock_flatten_api_with_error)
    response = client.get(
        f"/api/history/{pytest.bot}/conversations/download",
        headers={"Authorization": 'Bearer ' + HistoryUtils.environment['authentication']['token']},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == "error_message"
    assert not actual["success"]


def test_chat_history_no_token(mock_chat_history):
    response = client.get(
        f"/api/history/{pytest.bot}/conversations/users/5e564fbcdcf0d5fad89e3acd"
    )

    actual = response.json()
    assert actual["error_code"] == 401
    assert not actual["data"]
    assert actual["message"] == 'Could not validate credentials'
    assert not actual["success"]


def test_chat_history_users_invalid_auth(mock_chat_history):
    response = client.get(
        f"/api/history/{pytest.bot}/conversations/users",
        headers={"Authorization": 'Bearer test_invalid_token'},
    )

    actual = response.json()
    assert actual["error_code"] == 401
    assert not actual["data"]
    assert actual["message"] == 'Could not validate credentials'
    assert not actual["success"]


def test_no_auth_configured(mock_chat_history):
    HistoryUtils.environment['authentication']['token'] = None
    response = client.get(
        f"/api/history/{pytest.bot}/conversations/users/5e564fbcdcf0d5fad89e3acd",
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert len(actual["data"]["history"]) == 12
    assert actual["message"] is None
    assert actual["success"]


def test_no_bot_id():
    HistoryUtils.environment['tracker']['type'] = 'bot'
    response = client.get(
        f"/api/history/       /conversations/users/5e564fbcdcf0d5fad89e3acd",
        headers={"Authorization": 'Bearer ' + HistoryUtils.environment['authentication']['token']}
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert not actual["data"]
    assert actual["message"] == "Bot id is required"
    assert not actual["success"]


def test_no_collection():
    HistoryUtils.environment['tracker']['type'] = 'static'
    HistoryUtils.environment['tracker']['collection'] = None
    response = client.get(
        f"/api/history/{pytest.bot}/conversations/users/5e564fbcdcf0d5fad89e3acd",
        headers={"Authorization": 'Bearer ' + HistoryUtils.environment['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert not actual["data"]
    assert actual["message"] == "Collection not configured"
    assert not actual["success"]
