import json
import os
import datetime
import responses
from fastapi.testclient import TestClient
from mongoengine import connect
import pytest

from kairon.api.app.main import app
from kairon.shared.account.processor import AccountProcessor
from kairon.shared.data.constant import EVENT_STATUS
from kairon.shared.data.data_objects import ConversationsHistoryDeleteLogs
from kairon.shared.data.processor import MongoProcessor
from kairon.exceptions import AppException
from kairon.history.processor import HistoryProcessor
from kairon.shared.utils import Utility
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
    Utility.load_environment()
    connect(**Utility.mongoengine_connection())


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


def _mock_user_role(*args, **kwargs):
    return {'role': 'tester'}


def _mock_user_role_designer(*args, **kwargs):
    return {'role': 'tester'}


def _mock_user_role_admin(*args, **kwargs):
    return {'role': 'admin'}


@pytest.fixture(scope='function')
def mock_auth(monkeypatch):
    monkeypatch.setattr(AccountProcessor, "fetch_role_for_user", _mock_user_role)
    monkeypatch.setattr(AccountProcessor, "get_user_details", user_details)
    monkeypatch.setattr(AccountProcessor, "get_bot", bot_details)


@pytest.fixture(scope='function')
def mock_auth_admin(monkeypatch):
    monkeypatch.setattr(AccountProcessor, "fetch_role_for_user", _mock_user_role_admin)
    monkeypatch.setattr(AccountProcessor, "get_user_details", user_details)
    monkeypatch.setattr(AccountProcessor, "get_bot", bot_details)


@pytest.fixture(scope='function')
def mock_auth_designer(monkeypatch):
    monkeypatch.setattr(AccountProcessor, "fetch_role_for_user", _mock_user_role_designer)
    monkeypatch.setattr(AccountProcessor, "get_user_details", user_details)
    monkeypatch.setattr(AccountProcessor, "get_bot", bot_details)


def endpoint_details(*args, **kwargs):
    return {"history_endpoint": {"url": "https://localhost:8083", "token": "test_token"}}


@pytest.fixture(scope='function')
def mock_mongo_processor(monkeypatch):
    monkeypatch.setattr(MongoProcessor, "get_endpoints", endpoint_details)


@pytest.fixture(scope='function')
def mock_mongo_processor_endpoint_not_configured(monkeypatch):
    def _mock_exception(*args, **kwargs):
        raise AppException('Config not found')
    monkeypatch.setattr(MongoProcessor, "get_endpoints", _mock_exception)


@pytest.fixture
def mock_db_client(monkeypatch):
    def db_client(*args, **kwargs):
        return MongoClient(), "conversation", None

    monkeypatch.setattr(HistoryProcessor, "get_mongo_connection", db_client)


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
    monkeypatch.setattr(HistoryProcessor, "fetch_user_history", user_history)
    monkeypatch.setattr(HistoryProcessor, "fetch_chat_users", history_users)


def test_chat_history_users_connection_error(mock_auth, mock_mongo_processor):
    response = client.post(
        "/api/auth/login",
        data={"username": "integration@demo", "password": "welcome@1"},
    )
    token_response = response.json()
    pytest.access_token = token_response["data"]["access_token"]
    pytest.token_type = token_response["data"]["token_type"]

    response = client.get(
        f"/api/history/{pytest.bot}/users",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    print(actual)
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"].__contains__('Unable to connect to history server: ')
    assert not actual["success"]


@responses.activate
def test_chat_history_users_kairon_client_user_endpoint(mock_auth, mock_mongo_processor):
    responses.add(
        responses.GET,
        f"https://localhost:8083/api/history/{pytest.bot}/conversations/users",
        status=200,
        json={"data": {"users": history_users()[0]}},
        match=[responses.json_params_matcher({'month': 1})],
    )
    response = client.get(
        f"/api/history/{pytest.bot}/users",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    assert responses.calls[len(responses.calls) - 1].request.headers['Authorization'] == 'Bearer test_token'

    actual = response.json()
    assert actual["error_code"] == 0
    assert len(actual["data"]["users"]) == 7
    assert actual["message"] is None
    assert actual["success"]


@responses.activate
def test_chat_history_users_kairon_client_kairon_endpoint(mock_auth, mock_mongo_processor_endpoint_not_configured):
    responses.add(
        responses.GET,
        f"{Utility.environment['history_server']['url']}/api/history/{pytest.bot}/conversations/users",
        status=200,
        json={"data": {"users": history_users()[0]}},
        match=[responses.json_params_matcher({'month': 1})],
    )
    response = client.get(
        f"/api/history/{pytest.bot}/users",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    assert responses.calls[0].request.headers['Authorization'] == 'Bearer ' + Utility.environment['history_server']['token']

    actual = response.json()
    assert actual["error_code"] == 0
    assert len(actual["data"]["users"]) == 7
    assert actual["message"] is None
    assert actual["success"]


@responses.activate
def test_chat_history_with_kairon_client(mock_auth, mock_mongo_processor):
    responses.add(
        responses.GET,
        f"https://localhost:8083/api/history/{pytest.bot}/conversations/users/5e564fbcdcf0d5fad89e3acd",
        status=200,
        json={"data": {"history": history_conversations()[0]}},
        match=[responses.json_params_matcher({'month': 1})],
    )

    response = client.get(
        f"/api/history/{pytest.bot}/users/5e564fbcdcf0d5fad89e3acd",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert len(actual["data"]["history"]) == 7
    assert actual["message"] is None
    assert actual["success"]


@responses.activate
def test_fallback_count_range_no_nlu_fallback_rule(mock_auth, mock_mongo_processor):
    responses.add(
        responses.GET,
        f"https://localhost:8083/api/history/{pytest.bot}/trends/fallback",
        status=200,
        match=[responses.json_params_matcher({'month': 6, 'action_fallback': 'action_default_fallback',
                                              'nlu_fallback': None})],
        json={"data": {'fallback_counts': {1: 25, 2: 24, 3: 28, 4: 26, 5: 20, 6: 25}}}
    )

    response = client.get(
        f"/api/history/{pytest.bot}/metrics/trend/user/fallback",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["fallback_counts"] == {'1': 25, '2': 24, '3': 28, '4': 26, '5': 20, '6': 25}
    assert actual["message"] is None
    assert actual["success"]


@responses.activate
def test_visitor_hit_fallback_with_kairon_client(mock_auth, mock_mongo_processor):
    responses.add(
        responses.GET,
        f"https://localhost:8083/api/history/{pytest.bot}/metrics/fallback",
        status=200,
        json={"data": {'fallback_count': 10, 'total_count': 90}},
        match=[responses.json_params_matcher({'month': 1, 'action_fallback': 'action_default_fallback',
                                              'nlu_fallback': 'utter_please_rephrase'})],
    )

    steps = [
        {"name": "nlu_fallback", "type": "INTENT"},
        {"name": "utter_please_rephrase", "type": "BOT"}
    ]
    rule = {'name': 'fallback_rule', 'steps': steps, 'type': 'RULE'}
    MongoProcessor().add_complex_story(rule, pytest.bot, 'test')

    response = client.get(
        f"/api/history/{pytest.bot}/metrics/fallback",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["fallback_count"] == 10
    assert actual["data"]["total_count"] == 90
    assert actual["message"] is None
    assert actual["success"]


@responses.activate
def test_conversation_steps_with_kairon_client(mock_auth, mock_mongo_processor):
    responses.add(
        responses.GET,
        f"https://localhost:8083/api/history/{pytest.bot}/metrics/conversation/steps",
        status=200,
        match=[responses.json_params_matcher({'month': 1})],
        json={"data": 100}
    )

    response = client.get(
        f"/api/history/{pytest.bot}/metrics/conversation/steps",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"] == 100
    assert actual["message"] is None
    assert actual["success"]


@responses.activate
def test_conversation_time_with_kairon_client(mock_auth, mock_mongo_processor):
    responses.add(
        responses.GET,
        f"https://localhost:8083/api/history/{pytest.bot}/metrics/conversation/time",
        status=200,
        match=[responses.json_params_matcher({'month': 1})],
        json={"data": 900.5}
    )

    response = client.get(
        f"/api/history/{pytest.bot}/metrics/conversation/time",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"] == 900.5
    assert actual["message"] is None
    assert actual["success"]


@responses.activate
def test_user_with_metrics_with_kairon_client(mock_auth, mock_mongo_processor):
    responses.add(
        responses.GET,
        f"https://localhost:8083/api/history/{pytest.bot}/metrics/users",
        status=200,
        match=[responses.json_params_matcher({'month': 1})],
        json={"data": {'users': [{'sender_id': 'test@kairon.com', 'steps': 55, 'time': 15},
                                 {'sender_id': 'bot@kairon.com', 'steps': 20, 'time': 5}]}}
    )

    response = client.get(
        f"/api/history/{pytest.bot}/metrics/users",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["users"] == [{'sender_id': 'test@kairon.com', 'steps': 55, 'time': 15},
                                       {'sender_id': 'bot@kairon.com', 'steps': 20, 'time': 5}]
    assert actual["message"] is None
    assert actual["success"]


@responses.activate
def test_engaged_users_with_kairon_client(mock_auth, mock_mongo_processor):
    responses.add(
        responses.GET,
        f"https://localhost:8083/api/history/{pytest.bot}/metrics/users/engaged",
        match=[responses.json_params_matcher({'month': 1, 'conversation_step_threshold': 10})],
        status=200,
        json={"data": {'engaged_users': 50}}
    )

    response = client.get(
        f"/api/history/{pytest.bot}/metrics/user/engaged",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["engaged_users"] == 50
    assert actual["message"] is None
    assert actual["success"]


@responses.activate
def test_new_users_with_kairon_client(mock_auth, mock_mongo_processor):
    responses.add(
        responses.GET,
        f"https://localhost:8083/api/history/{pytest.bot}/metrics/users/new",
        match=[responses.json_params_matcher({'month': 1})],
        status=200,
        json={"data": {'new_users': 50}}
    )

    response = client.get(
        f"/api/history/{pytest.bot}/metrics/user/new",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["new_users"] == 50
    assert actual["message"] is None
    assert actual["success"]


@responses.activate
def test_successful_conversation_with_kairon_client(mock_auth, mock_mongo_processor):
    responses.add(
        responses.GET,
        f"https://localhost:8083/api/history/{pytest.bot}/metrics/conversation/success",
        status=200,
        match=[responses.json_params_matcher({'month': 1, 'action_fallback': 'action_default_fallback',
                                              'nlu_fallback': 'utter_please_rephrase'})],
        json={"data": {'successful_conversations': 150}}
    )

    response = client.get(
        f"/api/history/{pytest.bot}/metrics/conversation/success",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["successful_conversations"] == 150
    assert actual["message"] is None
    assert actual["success"]


@responses.activate
def test_user_retention_with_kairon_client(mock_auth, mock_mongo_processor):
    responses.add(
        responses.GET,
        f"https://localhost:8083/api/history/{pytest.bot}/metrics/users/retention",
        match=[responses.json_params_matcher({'month': 1})],
        status=200,
        json={"data": {'user_retention': 25}}
    )

    response = client.get(
        f"/api/history/{pytest.bot}/metrics/user/retention",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["user_retention"] == 25
    assert actual["message"] is None
    assert actual["success"]


@responses.activate
def test_engaged_user_range_with_kairon_client(mock_auth, mock_mongo_processor):
    responses.add(
        responses.GET,
        f"https://localhost:8083/api/history/{pytest.bot}/trends/users/engaged",
        status=200,
        match=[responses.json_params_matcher({'month': 6, 'conversation_step_threshold': 10})],
        json={"data": {'engaged_user_range': {1: 25, 2: 24, 3: 28, 4: 26, 5: 20, 6: 25}}}
    )

    response = client.get(
        f"/api/history/{pytest.bot}/metrics/trend/user/engaged",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]['engaged_user_range'] == {'1': 25, '2': 24, '3': 28, '4': 26, '5': 20, '6': 25}
    assert actual["message"] is None
    assert actual["success"]


@responses.activate
def test_new_user_range_with_kairon_client(mock_auth, mock_mongo_processor):
    responses.add(
        responses.GET,
        f"https://localhost:8083/api/history/{pytest.bot}/trends/users/new",
        status=200,
        match=[responses.json_params_matcher({'month': 6})],
        json={"data": {'new_user_range': {1: 25, 2: 24, 3: 28, 4: 26, 5: 20, 6: 25}}}
    )

    response = client.get(
        f"/api/history/{pytest.bot}/metrics/trend/user/new",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]['new_user_range'] == {'1': 25, '2': 24, '3': 28, '4': 26, '5': 20, '6': 25}
    assert actual["message"] is None
    assert actual["success"]


@responses.activate
def test_successful_conversation_range_with_kairon_client(mock_auth, mock_mongo_processor):
    responses.add(
        responses.GET,
        f"https://localhost:8083/api/history/{pytest.bot}/trends/conversations/success",
        status=200,
        match=[responses.json_params_matcher({'month': 6, 'action_fallback': 'action_default_fallback',
                                              'nlu_fallback': 'utter_please_rephrase'})],
        json={"data": {"successful_sessions": {1: 25, 2: 24, 3: 28, 4: 26, 5: 20, 6: 25}}}
    )

    response = client.get(
        f"/api/history/{pytest.bot}/metrics/trend/conversation/success",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]['successful_sessions'] == {'1': 25, '2': 24, '3': 28, '4': 26, '5': 20, '6': 25}
    assert actual["message"] is None
    assert actual["success"]


@responses.activate
def test_user_retention_range_with_kairon_client(mock_auth, mock_mongo_processor):
    responses.add(
        responses.GET,
        f"https://localhost:8083/api/history/{pytest.bot}/trends/users/retention",
        status=200,
        match=[responses.json_params_matcher({'month': 6})],
        json={"data": {'retention_range': {1: 25, 2: 24, 3: 28, 4: 26, 5: 20, 6: 25}}}
    )

    response = client.get(
        f"/api/history/{pytest.bot}/metrics/trend/user/retention",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["retention_range"] == {'1': 25, '2': 24, '3': 28, '4': 26, '5': 20, '6': 25}
    assert actual["message"] is None
    assert actual["success"]


@responses.activate
def test_engaged_users_with_value_with_kairon_client(mock_auth, mock_mongo_processor):
    responses.add(
        responses.GET,
        f"https://localhost:8083/api/history/{pytest.bot}/metrics/users/engaged",
        status=200,
        match=[responses.json_params_matcher({'month': 5, 'conversation_step_threshold': 11})],
        json={"data": {'engaged_users': 60}}
    )

    response = client.get(
        f"/api/history/{pytest.bot}/metrics/user/engaged?month=5&conversation_step_threshold=11",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["engaged_users"] == 60
    assert actual["message"] is None
    assert actual["success"]


@responses.activate
def test_engaged_user_range_with_value_with_kairon_client(mock_auth, mock_mongo_processor):
    responses.add(
        responses.GET,
        f"https://localhost:8083/api/history/{pytest.bot}/trends/users/engaged",
        status=200,
        match=[responses.json_params_matcher({'month': 5, 'conversation_step_threshold': 11})],
        json={"data": {'engaged_user_range': {1: 25, 2: 24, 3: 28, 4: 26, 5: 20, 6: 25}}}
    )

    response = client.get(
        f"/api/history/{pytest.bot}/metrics/trend/user/engaged/?month=5&conversation_step_threshold=11",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]['engaged_user_range'] == {'1': 25, '2': 24, '3': 28, '4': 26, '5': 20, '6': 25}
    assert actual["message"] is None
    assert actual["success"]


@responses.activate
def test_fallback_count_range_with_kairon_client(mock_auth, mock_mongo_processor):
    responses.add(
        responses.GET,
        f"https://localhost:8083/api/history/{pytest.bot}/trends/fallback",
        status=200,
        match=[responses.json_params_matcher({'month': 6, 'action_fallback': 'action_default_fallback',
                                              'nlu_fallback': 'utter_please_rephrase'})],
        json={"data": {'fallback_count_rate': {1: 25, 2: 24, 3: 28, 4: 26, 5: 20, 6: 25}}}
    )

    response = client.get(
        f"/api/history/{pytest.bot}/metrics/trend/user/fallback",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["fallback_count_rate"] == {'1': 25, '2': 24, '3': 28, '4': 26, '5': 20, '6': 25}
    assert actual["message"] is None
    assert actual["success"]


@responses.activate
def test_flat_conversations_with_kairon_client(mock_auth, mock_mongo_processor):
    responses.add(
        responses.GET,
        f"https://localhost:8083/api/history/{pytest.bot}/conversations/",
        status=200,
        match=[responses.json_params_matcher({'month': 1})],
        json={"data": {'conversation_data': history_conversations()[0]}}
    )

    response = client.get(
        f"/api/history/{pytest.bot}/conversations/",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert len(actual["data"]["conversation_data"]) == 7
    assert actual["message"] is None
    assert actual["success"]


def list_bot_mock(*args, **kwargs):
    return [{'name': 'test', '_id': pytest.bot}]


@pytest.fixture
def mock_list_bots(monkeypatch):
    monkeypatch.setattr(AccountProcessor, "list_bots", list_bot_mock)


@responses.activate
def test_download_conversation_with_data_with_kairon_client(mock_auth_admin, mock_mongo_processor, mock_list_bots):
    file = open('./tests/testing_data/history/conversation.json')
    responses.add(
        responses.GET,
        f"https://localhost:8083/api/history/{pytest.bot}/conversations/download",
        status=200,
        match=[responses.json_params_matcher({'month': 1})],
        body=file.read(),
        content_type="text/plain",
        adding_headers={"Content-Disposition": "attachment; filename=conversations.csv"},
        stream=True
    )

    response = client.get(
        f"/api/history/{pytest.bot}/conversations/download",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    assert response.status_code == 200
    assert response.content.decode('utf-8')
    assert f"conversation_history_test{datetime.date.today().strftime('_%d_%m_%y.csv')}" in str(response.headers)


@responses.activate
def test_download_conversation_with_error_with_kairon_client_access_denied1(mock_auth, mock_mongo_processor, mock_list_bots):
    responses.add(
        responses.GET,
        f"https://localhost:8083/api/history/{pytest.bot}/conversations/download",
        status=200,
        match=[responses.json_params_matcher({'month': 1})],
        json={'error_code': 422, 'message': "No data available!", 'success': False}
    )

    response = client.get(
        f"/api/history/{pytest.bot}/conversations/download",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 401
    assert actual["message"] == "['owner', 'admin'] access is required to perform this operation on the bot"
    assert not actual["success"]
    
    
@responses.activate
def test_download_conversation_with_error_with_kairon_client_access_denied2(mock_auth_designer, mock_mongo_processor, mock_list_bots):
    responses.add(
        responses.GET,
        f"https://localhost:8083/api/history/{pytest.bot}/conversations/download",
        status=200,
        match=[responses.json_params_matcher({'month': 1})],
        json={'error_code': 422, 'message': "No data available!", 'success': False}
    )

    response = client.get(
        f"/api/history/{pytest.bot}/conversations/download",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 401
    assert actual["message"] == "['owner', 'admin'] access is required to perform this operation on the bot"
    assert not actual["success"]


@responses.activate
def test_download_conversation_with_error_with_kairon_client(mock_auth_admin, mock_mongo_processor, mock_list_bots):
    responses.add(
        responses.GET,
        f"https://localhost:8083/api/history/{pytest.bot}/conversations/download",
        status=200,
        match=[responses.json_params_matcher({'month': 1})],
        json={'error_code': 422, 'message': "No data available!", 'success': False}
    )

    response = client.get(
        f"/api/history/{pytest.bot}/conversations/download",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == "No data available!"
    assert not actual["success"]


@responses.activate
def test_total_conversation_range_with_kairon_client(mock_auth, mock_mongo_processor):
    responses.add(
        responses.GET,
        f"https://localhost:8083/api/history/{pytest.bot}/trends/conversations/total",
        status=200,
        match=[responses.json_params_matcher({'month': 6})],
        json={"data": {'total_conversation_range': {1: 25, 2: 24, 3: 28, 4: 26, 5: 20, 6: 25}}}
    )

    response = client.get(
        f"/api/history/{pytest.bot}/metrics/trend/conversations/total",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["total_conversation_range"] == {'1': 25, '2': 24, '3': 28, '4': 26, '5': 20, '6': 25}
    assert actual["message"] is None
    assert actual["success"]


@responses.activate
def test_top_intent_with_kairon_client(mock_auth, mock_mongo_processor):
    responses.add(
        responses.GET,
        f"https://localhost:8083/api/history/{pytest.bot}/metrics/intents/topmost",
        match=[responses.json_params_matcher({'month': 1, "top_n": 10})],
        status=200,
        json={"data": [{'_id': 'action_google_search_kanban', 'count': 43}]}
    )

    response = client.get(
        f"/api/history/{pytest.bot}/metrics/intents/topmost",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"] == [{'_id': 'action_google_search_kanban', 'count': 43}]
    assert actual["message"] is None
    assert actual["success"]


@responses.activate
def test_top_action_with_kairon_client(mock_auth, mock_mongo_processor):
    responses.add(
        responses.GET,
        f"https://localhost:8083/api/history/{pytest.bot}/metrics/actions/topmost",
        match=[responses.json_params_matcher({'month': 1, "top_n": 10})],
        status=200,
        json={"data": [{'_id': 'nlu_fallback', 'count': 32}]}
    )

    response = client.get(
        f"/api/history/{pytest.bot}/metrics/actions/topmost",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"] == [{'_id': 'nlu_fallback', 'count': 32}]
    assert actual["message"] is None
    assert actual["success"]


@responses.activate
def test_conversation_step_range_with_kairon_client(mock_auth, mock_mongo_processor):
    responses.add(
        responses.GET,
        f"https://localhost:8083/api/history/{pytest.bot}/trends/conversations/steps",
        status=200,
        match=[responses.json_params_matcher({'month': 6})],
        json={"data": {'average_conversation_steps': {1: 25, 2: 24, 3: 28, 4: 26, 5: 20, 6: 25}}}
    )

    response = client.get(
        f"/api/history/{pytest.bot}/metrics/trend/conversations/steps",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["average_conversation_steps"] == {'1': 25, '2': 24, '3': 28, '4': 26, '5': 20, '6': 25}
    assert actual["message"] is None
    assert actual["success"]


@responses.activate
def test_wordcloud_with_kairon_client(mock_auth, mock_mongo_processor):
    responses.add(
        responses.GET,
        f"https://localhost:8083/api/history/{pytest.bot}/conversations/wordcloud",
        status=200,
        match=[responses.json_params_matcher({'month': 1, 'l_bound': 0, 'u_bound': 1, 'stopword_list': None})],
        json={"data": [{'_id': 'nlu_fallback', 'count': 32}]}
    )

    response = client.get(
        f"/api/history/{pytest.bot}/conversations/wordcloud",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["data"] == [{'_id': 'nlu_fallback', 'count': 32}]


@responses.activate
def test_unique_user_input_with_kairon_client(mock_auth, mock_mongo_processor):
    responses.add(
        responses.GET,
        f"https://localhost:8083/api/history/{pytest.bot}/metrics/users/input",
        status=200,
        match=[responses.json_params_matcher({'month': 1})],
        json={"data": [{'_id': 'nlu_fallback', 'count': 32}]}
    )

    response = client.get(
        f"/api/history/{pytest.bot}/conversations/input/unique",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"] == [{'_id': 'nlu_fallback', 'count': 32}]
    assert actual["message"] is None
    assert actual["success"]


@responses.activate
def test_conversation_time_range_with_kairon_client(mock_auth, mock_mongo_processor):
    responses.add(
        responses.GET,
        f"https://localhost:8083/api/history/{pytest.bot}/trends/conversations/time",
        status=200,
        match=[responses.json_params_matcher({'month': 6})],
        json={"data": {'total_conversation_range': {1: 25, 2: 24, 3: 28, 4: 26, 5: 20, 6: 25}}}
    )

    response = client.get(
        f"/api/history/{pytest.bot}/metrics/trend/conversations/time",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["total_conversation_range"] == {'1': 25, '2': 24, '3': 28, '4': 26, '5': 20, '6': 25}
    assert actual["message"] is None
    assert actual["success"]


@responses.activate
def test_dropoff_users_with_kairon_client(mock_auth, mock_mongo_processor):
    responses.add(
        responses.GET,
        f"https://localhost:8083/api/history/{pytest.bot}/metrics/fallback/dropoff",
        status=200,
        match=[responses.json_params_matcher({'month': 1, 'action_fallback': 'action_default_fallback',
                                              'nlu_fallback': 'utter_please_rephrase'})],
        json={"data": {'total_conversation_range': {1: 25, 2: 24, 3: 28, 4: 26, 5: 20, 6: 25}}}
    )

    response = client.get(
        f"/api/history/{pytest.bot}/metrics/user/fallback/dropoff",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["total_conversation_range"] == {'1': 25, '2': 24, '3': 28, '4': 26, '5': 20, '6': 25}
    assert actual["message"] is None
    assert actual["success"]


@responses.activate
def test_user_intent_dropoff_with_kairon_client(mock_auth, mock_mongo_processor):
    responses.add(
        responses.GET,
        f"https://localhost:8083/api/history/{pytest.bot}/metrics/intents/dropoff",
        status=200,
        match=[responses.json_params_matcher({'month': 1})],
        json={"data": {'total_conversation_range': {1: 25, 2: 24, 3: 28, 4: 26, 5: 20, 6: 25}}}
    )

    response = client.get(
        f"/api/history/{pytest.bot}/metrics/user/intent/dropoff",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["total_conversation_range"] == {'1': 25, '2': 24, '3': 28, '4': 26, '5': 20, '6': 25}
    assert actual["message"] is None
    assert actual["success"]


@responses.activate
def test_unsuccessful_session_count_with_kairon_client(mock_auth, mock_mongo_processor):
    responses.add(
        responses.GET,
        f"https://localhost:8083/api/history/{pytest.bot}/metrics/sessions/unsuccessful",
        status=200,
        match=[responses.json_params_matcher({'month': 1, 'action_fallback': 'action_default_fallback',
                                              'nlu_fallback': 'utter_please_rephrase'})],
        json={"data": {'user_1': 25, 'user_2': 24}}
    )

    response = client.get(
        f"/api/history/{pytest.bot}/metrics/user/sessions/unsuccessful",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"] == {'user_1': 25, 'user_2': 24}
    assert actual["message"] is None
    assert actual["success"]


@responses.activate
def test_total_sessions_with_kairon_client(mock_auth, mock_mongo_processor):
    responses.add(
        responses.GET,
        f"https://localhost:8083/api/history/{pytest.bot}/metrics/sessions/total",
        status=200,
        match=[responses.json_params_matcher({'month': 1})],
        json={"data": {"user_1": 250, "user_2": 240}}
    )

    response = client.get(
        f"/api/history/{pytest.bot}/metrics/user/sessions/total",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"] == {'user_1': 250, 'user_2': 240}
    assert actual["message"] is None
    assert actual["success"]


@responses.activate
def test_delete_user_chat_history_kairon_client_kairon_endpoint(mock_auth_admin, mock_mongo_processor_endpoint_not_configured,
                                                                monkeypatch):
    response = client.delete(
        f"/api/history/{pytest.bot}/delete/5e564fbcdcf0d5fad89e3acd?month=3",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"] == 'Delete user history initiated. It may take a while. Check logs!'
    assert actual["success"]


@responses.activate
def test_delete_user_chat_history_kairon_client_user_endpoint(mock_auth_admin, mock_mongo_processor):
    response = client.delete(
        f"/api/history/{pytest.bot}/delete/5e564fbcdcf0d5fad89e3acd",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == f'History server not managed by Kairon!. Manually delete the collection:{pytest.bot}'
    assert not actual["success"]


@responses.activate
def test_delete_user_chat_history_kairon_client_event(mock_auth_admin, mock_mongo_processor_endpoint_not_configured, monkeypatch):
    event_url = 'http://event.url'
    monkeypatch.setitem(Utility.environment['history_server']['deletion'], 'event_url', event_url)
    responses.add("POST",
                  event_url,
                  json={"message": "Event triggered successfully!"},
                  status=200)

    response = client.delete(
        f"/api/history/{pytest.bot}/delete/5e564fbcdcf0d5fad89e3acd",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"] == 'Delete user history initiated. It may take a while. Check logs!'
    assert actual["success"]


@responses.activate
def test_delete_user_chat_history_kairon_client_event_exists(mock_auth_admin, mock_mongo_processor_endpoint_not_configured,
                                                                monkeypatch):
    response = client.delete(
        f"/api/history/{pytest.bot}/delete/5e564fbcdcf0d5fad89e3acd?month=3",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == 'Event already in progress! Check logs.'
    assert not actual["success"]

    # update status
    log = ConversationsHistoryDeleteLogs.objects(bot=pytest.bot, status=EVENT_STATUS.TASKSPAWNED.value).get()
    log.status = EVENT_STATUS.COMPLETED.value
    log.save()


def test_delete_bot_chat_history_kairon_client_kairon_endpoint(mock_auth_admin, mock_mongo_processor_endpoint_not_configured):

    response = client.delete(
        f"/api/history/{pytest.bot}/bot/delete?month=3",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"] == 'Delete chat history initiated. It may take a while. Check logs!'
    assert actual["success"]


@responses.activate
def test_delete_bot_chat_history_kairon_client_user_endpoint(mock_auth_admin, mock_mongo_processor):
    response = client.delete(
        f"/api/history/{pytest.bot}/bot/delete",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == f'History server not managed by Kairon!. Manually delete the collection:{pytest.bot}'
    assert not actual["success"]


@responses.activate
def test_delete_bot_chat_history_kairon_client_event(mock_auth_admin, mock_mongo_processor_endpoint_not_configured, monkeypatch):
    event_url = 'http://event.url'
    monkeypatch.setitem(Utility.environment['history_server']['deletion'], 'event_url', event_url)
    responses.add("POST",
                  event_url,
                  json={"message": "Event triggered successfully!"},
                  status=200)

    response = client.delete(
        f"/api/history/{pytest.bot}/bot/delete",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"] == 'Delete chat history initiated. It may take a while. Check logs!'
    assert actual["success"]


def test_get_delete_history_logs(mock_auth_admin, mock_mongo_processor_endpoint_not_configured):

    response = client.get(
        f"/api/history/{pytest.bot}/delete/logs",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["success"]
    assert len(actual["data"]) == 4
    assert actual['data'][0]['status'] == EVENT_STATUS.TASKSPAWNED.value
    assert actual['data'][0]['bot'] == pytest.bot
    assert actual['data'][0]['user'] == 'integration@demo.com'
    # update status
    log = ConversationsHistoryDeleteLogs.objects(bot=pytest.bot, status=EVENT_STATUS.TASKSPAWNED.value).get()
    log.status = EVENT_STATUS.COMPLETED.value
    log.save()


