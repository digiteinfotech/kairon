from datetime import datetime, timedelta
import os
from fastapi.testclient import TestClient
from mongoengine import connect
import pytest
from kairon.history.main import app
from kairon.shared.utils import Utility
from mongomock import MongoClient
from kairon.history.processor import HistoryProcessor
from pymongo.collection import Collection
from unittest import mock
from urllib.parse import urlencode


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
    connect(**Utility.mongoengine_connection(Utility.environment['tracker']['url']), alias="history")
    pytest.bot = '542872407658659274'


@pytest.fixture
def get_connection_delete_history():
    os.environ["system_file"] = "./tests/testing_data/system.yaml"
    Utility.load_environment()
    connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))
    os.environ["system_file"] = "./tests/testing_data/tracker.yaml"
    Utility.load_environment()


@pytest.fixture
def mock_archive_history(monkeypatch):
    def archive_msg(*args, **kwargs):
        return f'User history archived in {pytest.bot}.5e564fbcdcf0d5fad89e3acd'

    def mock_find(*args, **kwargs):
        return [{'sender_id': 'fshaikh@digite.com'}]

    monkeypatch.setattr(Collection, 'aggregate', archive_msg)
    monkeypatch.setattr(Collection, 'update', archive_msg)
    monkeypatch.setattr(Collection, 'find', mock_find)


def test_healthcheck():
    response = client.get("/healthcheck")
    actual = response.json()
    assert response.status_code == 200
    assert actual["message"] == "health check ok"

@mock.patch('kairon.history.processor.MongoClient', autospec=True)
def test_chat_history_users(mock_mongo):
    mock_mongo.return_value = MongoClient("mongodb://locahost/test")
    response = client.get(
        f"/api/history/{pytest.bot}/conversations/users",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert len(actual["data"]["users"]) == 0
    assert actual["message"] is None
    assert actual["success"]
    print(response.headers)
    assert response.headers == {'content-length': '66', 'content-type': 'application/json', 'server': 'Secure',
                                'strict-transport-security': 'includeSubDomains; preload; max-age=31536000',
                                'x-frame-options': 'SAMEORIGIN', 'x-xss-protection': '0',
                                'x-content-type-options': 'nosniff',
                                'content-security-policy': "default-src 'self'; frame-ancestors 'self'; form-action 'self'; base-uri 'self'; connect-src 'self'api.spam.com; frame-src 'self'; img-src 'self' static.spam.com",
                                'referrer-policy': 'no-referrer', 'cache-control': 'must-revalidate',
                                'permissions-policy': "accelerometer=(), autoplay=(), camera=(), document-domain=(), encrypted-media=(), fullscreen=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), midi=(), payment=(), picture-in-picture=(), sync-xhr=(), usb=(), geolocation=(self 'spam.com'), vibrate=()"}


def test_chat_history_users_with_from_date_less_than_six_months():
    from_date = (datetime.utcnow() - timedelta(300)).date()
    to_date = (datetime.utcnow()).date()
    response = client.get(
        f"/api/history/{pytest.bot}/conversations/users?from_date={from_date}&to_date={to_date}",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"].__contains__('from_date should be within six months and today date')
    assert not actual["success"]


def test_chat_history_users_with_from_date_greater_than_today_date():
    from_date = (datetime.utcnow() + timedelta(30)).date()
    to_date = (datetime.utcnow()).date()
    response = client.get(
        f"/api/history/{pytest.bot}/conversations/users?from_date={from_date}&to_date={to_date}",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"].__contains__('from_date should be within six months and today date')
    assert not actual["success"]


def test_chat_history_users_with_to_date_less_than_six_months():
    from_date = (datetime.utcnow() - timedelta(30)).date()
    to_date = (datetime.utcnow() - timedelta(300)).date()
    response = client.get(
        f"/api/history/{pytest.bot}/conversations/users?from_date={from_date}&to_date={to_date}",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"].__contains__('to_date should be within six months and today date')
    assert not actual["success"]


def test_chat_history_users_with_to_date_greater_than_today_date():
    from_date = (datetime.utcnow() - timedelta(30)).date()
    to_date = (datetime.utcnow() + timedelta(30)).date()
    response = client.get(
        f"/api/history/{pytest.bot}/conversations/users?from_date={from_date}&to_date={to_date}",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"].__contains__('to_date should be within six months and today date')
    assert not actual["success"]


def test_chat_history_users_with_from_date_greater_than_to_date():
    from_date = (datetime.utcnow()).date()
    to_date = (datetime.utcnow() - timedelta(90)).date()
    response = client.get(
        f"/api/history/{pytest.bot}/conversations/users?from_date={from_date}&to_date={to_date}",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"].__contains__('from_date must be less than to_date')
    assert not actual["success"]


@mock.patch('kairon.history.processor.MongoClient', autospec=True)
def test_chat_history_users_with_valid_from_date_and_to_date(mock_mongo):
    from_date = (datetime.utcnow() - timedelta(30)).date()
    to_date = (datetime.utcnow()).date()
    mock_mongo.return_value = MongoClient("mongodb://locahost/test")
    response = client.get(
        f"/api/history/{pytest.bot}/conversations/users?from_date={from_date}&to_date={to_date}",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert len(actual["data"]["users"]) == 0
    assert actual["message"] is None
    assert actual["success"]


@mock.patch('kairon.history.processor.MongoClient', autospec=True)
def test_chat_history(mock_mongo):
    mock_mongo.return_value = MongoClient("mongodb://locahost/test")
    response = client.get(
        f"/api/history/{pytest.bot}/conversations/users/5e564fbcdcf0d5fad89e3acd",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert len(actual["data"]["history"]) == 0
    assert actual["message"] is None
    assert actual["success"]


@mock.patch('kairon.history.processor.MongoClient', autospec=True)
def test_chat_history_with_user_id_contains_special_character(mock_chat_history):
    from urllib.parse import quote_plus

    response = client.get(
        f"/api/history/{pytest.bot}/conversations/users/{quote_plus('LNLMC1/daIk=')}",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert len(actual["data"]["history"]) == 0
    assert actual["message"] is None
    assert actual["success"]


@mock.patch('kairon.history.processor.MongoClient', autospec=True)
def test_visitor_hit_fallback(mock_mongo):
    mock_mongo.return_value = MongoClient("mongodb://locahost/test")
    response = client.get(
        f"/api/history/{pytest.bot}/metrics/fallback",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["fallback_count"] == 0
    assert actual["data"]["total_count"] == 0
    assert actual["message"] is None
    assert actual["success"]


@mock.patch('kairon.history.processor.MongoClient', autospec=True)
def test_conversation_steps(mock_mongo):
    mock_mongo.return_value = MongoClient("mongodb://locahost/test")
    response = client.get(
        f"/api/history/{pytest.bot}/metrics/conversation/steps",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert len(actual["data"]) == 0
    assert actual["message"] is None
    assert actual["success"]


@mock.patch('kairon.history.processor.MongoClient', autospec=True)
def test_user_with_metrics(mock_mongo):
    mock_mongo.return_value = MongoClient("mongodb://locahost/test")
    response = client.get(
        f"/api/history/{pytest.bot}/metrics/users",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["users"] == []
    assert actual["message"] is None
    assert actual["success"]


def test_user_with_metrics_with_from_date_less_than_six_months():
    from_date = (datetime.utcnow() - timedelta(300)).date()
    to_date = (datetime.utcnow()).date()
    response = client.get(
        f"/api/history/{pytest.bot}/metrics/users?from_date={from_date}&to_date={to_date}",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"].__contains__('from_date should be within six months and today date')
    assert not actual["success"]


def test_user_with_metrics_with_from_date_greater_than_today_date():
    from_date = (datetime.utcnow() + timedelta(30)).date()
    to_date = (datetime.utcnow()).date()
    response = client.get(
        f"/api/history/{pytest.bot}/metrics/users?from_date={from_date}&to_date={to_date}",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"].__contains__('from_date should be within six months and today date')
    assert not actual["success"]


def test_user_with_metrics_with_to_date_less_than_six_months():
    from_date = (datetime.utcnow() - timedelta(30)).date()
    to_date = (datetime.utcnow() - timedelta(300)).date()
    response = client.get(
        f"/api/history/{pytest.bot}/metrics/users?from_date={from_date}&to_date={to_date}",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"].__contains__('to_date should be within six months and today date')
    assert not actual["success"]


def test_user_with_metrics_with_to_date_greater_than_today_date():
    from_date = (datetime.utcnow() - timedelta(30)).date()
    to_date = (datetime.utcnow() + timedelta(30)).date()
    response = client.get(
        f"/api/history/{pytest.bot}/metrics/users?from_date={from_date}&to_date={to_date}",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"].__contains__('to_date should be within six months and today date')
    assert not actual["success"]


def test_user_with_metrics_with_from_date_greater_than_to_date():
    from_date = (datetime.utcnow()).date()
    to_date = (datetime.utcnow() - timedelta(90)).date()
    response = client.get(
        f"/api/history/{pytest.bot}/metrics/users?from_date={from_date}&to_date={to_date}",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"].__contains__('from_date must be less than to_date')
    assert not actual["success"]


@mock.patch('kairon.history.processor.MongoClient', autospec=True)
def test_user_with_metrics_with_valid_from_date_and_to_date(mock_mongo):
    from_date = (datetime.utcnow() - timedelta(30)).date()
    to_date = (datetime.utcnow()).date()
    mock_mongo.return_value = MongoClient("mongodb://locahost/test")
    response = client.get(
        f"/api/history/{pytest.bot}/metrics/users?from_date={from_date}&to_date={to_date}",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["users"] == []
    assert actual["message"] is None
    assert actual["success"]


@mock.patch('kairon.history.processor.MongoClient', autospec=True)
def test_engaged_users(mock_mongo):
    mock_mongo.return_value = MongoClient("mongodb://locahost/test")
    response = client.get(
        f"/api/history/{pytest.bot}/metrics/users/engaged",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["engaged_users"] == 0
    assert actual["message"] is None
    assert actual["success"]


@mock.patch('kairon.history.processor.MongoClient', autospec=True)
def test_new_users(mock_mongo):
    mock_mongo.return_value = MongoClient("mongodb://locahost/test")
    response = client.get(
        f"/api/history/{pytest.bot}/metrics/users/new",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["new_users"] == 0
    assert actual["message"] is None
    assert actual["success"]


@mock.patch('kairon.history.processor.MongoClient', autospec=True)
def test_successful_conversation(mock_mongo):
    mock_mongo.return_value = MongoClient("mongodb://locahost/test")
    response = client.get(
        f"/api/history/{pytest.bot}/metrics/conversation/success",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["successful_conversations"] == 0
    assert actual["message"] is None
    assert actual["success"]


@mock.patch('kairon.history.processor.MongoClient', autospec=True)
def test_successful_conversation_with_request(mock_mongo):
    mock_mongo.return_value = MongoClient("mongodb://locahost/test")
    response = client.get(
        f"/api/history/{pytest.bot}/metrics/conversation/success?"+urlencode({'month': 4, 'action_fallback': 'action_default_fallback', 'nlu_fallback': 'utter_please_rephrase'}),
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["successful_conversations"] == 0
    assert actual["message"] is None
    assert actual["success"]


@mock.patch('kairon.history.processor.MongoClient', autospec=True)
def test_successful_conversation_with_request_and_static_collection(mock_mongo):
    mock_mongo.return_value = MongoClient("mongodb://locahost/test")
    Utility.environment['tracker']['type'] = 'static'
    response = client.get(
        f"/api/history/{pytest.bot}/metrics/conversation/success?"+urlencode({'month': 4, 'action_fallback': 'action_default_fallback', 'nlu_fallback': 'utter_please_rephrase'}),
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["successful_conversations"] == 0
    assert actual["message"] is None
    assert actual["success"]


@mock.patch('kairon.history.processor.MongoClient', autospec=True)
def test_user_retention(mock_mongo):
    mock_mongo.return_value = MongoClient("mongodb://locahost/test")
    response = client.get(
        f"/api/history/{pytest.bot}/metrics/users/retention",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["user_retention"] == 0
    assert actual["message"] is None
    assert actual["success"]


@mock.patch('kairon.history.processor.MongoClient', autospec=True)
def test_engaged_user_range(mock_mongo):
    mock_mongo.return_value = MongoClient("mongodb://locahost/test")
    response = client.get(
        f"/api/history/{pytest.bot}/trends/users/engaged",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]['engaged_user_range'] == {}
    assert actual["message"] is None
    assert actual["success"]


def test_engaged_user_range_with_from_date_less_than_six_months():
    from_date = (datetime.utcnow() - timedelta(300)).date()
    to_date = (datetime.utcnow()).date()
    response = client.get(
        f"/api/history/{pytest.bot}/trends/users/engaged?from_date={from_date}&to_date={to_date}",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"].__contains__('from_date should be within six months and today date')
    assert not actual["success"]


def test_engaged_user_range_with_from_date_greater_than_today_date():
    from_date = (datetime.utcnow() + timedelta(30)).date()
    to_date = (datetime.utcnow()).date()
    response = client.get(
        f"/api/history/{pytest.bot}/trends/users/engaged?from_date={from_date}&to_date={to_date}",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"].__contains__('from_date should be within six months and today date')
    assert not actual["success"]


def test_engaged_user_range_with_to_date_less_than_six_months():
    from_date = (datetime.utcnow() - timedelta(30)).date()
    to_date = (datetime.utcnow() - timedelta(300)).date()
    response = client.get(
        f"/api/history/{pytest.bot}/trends/users/engaged?from_date={from_date}&to_date={to_date}",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"].__contains__('to_date should be within six months and today date')
    assert not actual["success"]


def test_engaged_user_range_with_to_date_greater_than_today_date():
    from_date = (datetime.utcnow() - timedelta(30)).date()
    to_date = (datetime.utcnow() + timedelta(30)).date()
    response = client.get(
        f"/api/history/{pytest.bot}/trends/users/engaged?from_date={from_date}&to_date={to_date}",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"].__contains__('to_date should be within six months and today date')
    assert not actual["success"]


def test_engaged_user_range_with_from_date_greater_than_to_date():
    from_date = (datetime.utcnow()).date()
    to_date = (datetime.utcnow() - timedelta(90)).date()
    response = client.get(
        f"/api/history/{pytest.bot}/trends/users/engaged?from_date={from_date}&to_date={to_date}",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"].__contains__('from_date must be less than to_date')
    assert not actual["success"]


@mock.patch('kairon.history.processor.MongoClient', autospec=True)
def test_engaged_user_range_with_valid_from_date_and_to_date(mock_mongo):
    from_date = (datetime.utcnow() - timedelta(30)).date()
    to_date = (datetime.utcnow()).date()
    mock_mongo.return_value = MongoClient("mongodb://locahost/test")
    response = client.get(
        f"/api/history/{pytest.bot}/trends/users/engaged?from_date={from_date}&to_date={to_date}",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]['engaged_user_range'] == {}
    assert actual["message"] is None
    assert actual["success"]


@mock.patch('kairon.history.processor.MongoClient', autospec=True)
def test_new_user_range(mock_mongo):
    mock_mongo.return_value = MongoClient("mongodb://locahost/test")
    response = client.get(
        f"/api/history/{pytest.bot}/trends/users/new",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]['new_user_range'] == {}
    assert actual["message"] is None
    assert actual["success"]


@mock.patch('kairon.history.processor.MongoClient', autospec=True)
def test_successful_conversation_range(mock_mongo):
    mock_mongo.return_value = MongoClient("mongodb://locahost/test")
    response = client.get(
        f"/api/history/{pytest.bot}/trends/conversations/success",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]['successful'] == []
    assert actual["message"] is None
    assert actual["success"]


@mock.patch('kairon.history.processor.MongoClient', autospec=True)
def test_successful_conversation_range_with_request(mock_mongo):
    mock_mongo.return_value = MongoClient("mongodb://locahost/test")
    response = client.get(
        f"/api/history/{pytest.bot}/trends/conversations/success?"+urlencode({'month': 4, 'action_fallback': 'action_default_fallback', 'nlu_fallback': 'utter_please_rephrase'}),
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]['successful'] == []
    assert actual["message"] is None
    assert actual["success"]


@mock.patch('kairon.history.processor.MongoClient', autospec=True)
def test_user_retention_range(mock_mongo):
    mock_mongo.return_value = MongoClient("mongodb://locahost/test")
    response = client.get(
        f"/api/history/{pytest.bot}/trends/users/retention",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["retention_range"] == {}
    assert actual["message"] is None
    assert actual["success"]


@mock.patch('kairon.history.processor.MongoClient', autospec=True)
def test_engaged_users_with_value(mock_mongo):
    mock_mongo.return_value = MongoClient("mongodb://locahost/test")
    response = client.get(
        f"/api/history/{pytest.bot}/metrics/users/engaged?"+urlencode({'month': 5, 'conversation_step_threshold': 11}),
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["engaged_users"] == 0
    assert actual["message"] is None
    assert actual["success"]


@mock.patch('kairon.history.processor.MongoClient', autospec=True)
def test_engaged_user_range_with_value(mock_mongo):
    mock_mongo.return_value = MongoClient("mongodb://locahost/test")
    response = client.get(
        f"/api/history/{pytest.bot}/trends/users/engaged?"+urlencode({'month': 5, 'conversation_step_threshold': 11}),
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]['engaged_user_range'] == {}
    assert actual["message"] is None
    assert actual["success"]


@mock.patch('kairon.history.processor.MongoClient', autospec=True)
def test_fallback_count_range(mock_mongo):
    mock_mongo.return_value = MongoClient("mongodb://locahost/test")
    response = client.get(
        f"/api/history/{pytest.bot}/trends/fallback",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["fallback_count_rate"] == {}
    assert actual["message"] is None
    assert actual["success"]


@mock.patch('kairon.history.processor.MongoClient', autospec=True)
def test_fallback_count_range_with_request(mock_mongo):
    mock_mongo.return_value = MongoClient("mongodb://locahost/test")
    response = client.get(
        f"/api/history/{pytest.bot}/trends/fallback?"+urlencode({'month': 4, 'action_fallback': 'action_default_fallback', 'nlu_fallback': 'utter_please_rephrase'}),
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["fallback_count_rate"] == {}
    assert actual["message"] is None
    assert actual["success"]


@mock.patch('kairon.history.processor.MongoClient', autospec=True)
def test_flat_conversations(mock_mongo):
    mock_mongo.return_value = MongoClient("mongodb://locahost/test")
    response = client.get(
        f"/api/history/{pytest.bot}/conversations",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["conversation_data"] == []
    assert actual["message"] is None
    assert actual["success"]


def mock_flatten_api_with_data(*args, **kwargs):
    return {"conversation_data": [{"test_key": "test_value"}]}, 'connecting to db, '


def mock_flatten_api_with_no_data(*args, **kwargs):
    return {"conversation_data": []}, None


def mock_flatten_api_with_error(*args, **kwargs):
    return {"conversation_data": []}, "error_message"


def test_download_conversation_with_data(monkeypatch):
    monkeypatch.setattr(HistoryProcessor, 'flatten_conversations', mock_flatten_api_with_data)
    response = client.get(
        f"/api/history/{pytest.bot}/conversations/download",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )
    assert "test_value" in str(response.content)


def test_download_conversation_with_no_data(monkeypatch):
    monkeypatch.setattr(HistoryProcessor, 'flatten_conversations', mock_flatten_api_with_no_data)
    response = client.get(
        f"/api/history/{pytest.bot}/conversations/download",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == "No data available!"
    assert not actual["success"]


def test_download_conversation_with_error(monkeypatch):
    monkeypatch.setattr(HistoryProcessor, 'flatten_conversations', mock_flatten_api_with_error)
    response = client.get(
        f"/api/history/{pytest.bot}/conversations/download",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == "No data available!"
    assert not actual["success"]


@mock.patch('kairon.history.processor.MongoClient', autospec=True)
def test_chat_history_no_token(mock_mongo):
    mock_mongo.return_value = MongoClient("mongodb://locahost/test")
    response = client.get(
        f"/api/history/{pytest.bot}/conversations/users/5e564fbcdcf0d5fad89e3acd"
    )

    actual = response.json()
    assert actual["error_code"] == 401
    assert not actual["data"]
    assert actual["message"] == 'Could not validate credentials'
    assert not actual["success"]


@mock.patch('kairon.history.processor.MongoClient', autospec=True)
def test_chat_history_users_invalid_auth(mock_mongo):
    mock_mongo.return_value = MongoClient("mongodb://locahost/test")
    response = client.get(
        f"/api/history/{pytest.bot}/conversations/users",
        headers={"Authorization": 'Bearer test_invalid_token'},
    )

    actual = response.json()
    assert actual["error_code"] == 401
    assert not actual["data"]
    assert actual["message"] == 'Could not validate credentials'
    assert not actual["success"]


@mock.patch('kairon.history.processor.MongoClient', autospec=True)
def test_no_auth_configured(mock_mongo):
    mock_mongo.return_value = MongoClient("mongodb://locahost/test")
    Utility.environment['tracker']['authentication']['token'] = None
    response = client.get(
        f"/api/history/{pytest.bot}/conversations/users/5e564fbcdcf0d5fad89e3acd",
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert len(actual["data"]["history"]) == 0
    assert actual["message"] is None
    assert actual["success"]


def test_no_bot_id():
    Utility.environment['tracker']['type'] = 'bot'
    response = client.get(
        f"/api/history/       /conversations/users/5e564fbcdcf0d5fad89e3acd",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']}
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert not actual["data"]
    assert actual["message"] == "Bot id is required"
    assert not actual["success"]


@mock.patch('kairon.history.processor.MongoClient', autospec=True)
def test_no_collection(mock_mongo):
    mock_mongo.return_value = MongoClient("mongodb://locahost/test")
    Utility.environment['tracker']['type'] = 'static'
    Utility.environment['tracker']['collection'] = None
    response = client.get(
        f"/api/history/{pytest.bot}/conversations/users/5e564fbcdcf0d5fad89e3acd",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert not actual["data"]
    assert actual["message"] == "Collection not configured"
    assert not actual["success"]


@mock.patch('kairon.history.processor.MongoClient', autospec=True)
def test_top_intents(mock_mongo):
    mock_mongo.return_value = MongoClient("mongodb://locahost/test")
    response = client.get(
        f"/api/history/{pytest.bot}/metrics/intents/topmost",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"] == []
    assert actual["success"]


@mock.patch('kairon.history.processor.MongoClient', autospec=True)
def test_top_actions(mock_mongo):
    mock_mongo.return_value = MongoClient("mongodb://locahost/test")
    response = client.get(
        f"/api/history/{pytest.bot}/metrics/actions/topmost",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"] == []
    assert actual["success"]


@mock.patch('kairon.history.processor.MongoClient', autospec=True)
def test_total_conversation_range(mock_mongo):
    mock_mongo.return_value = MongoClient("mongodb://locahost/test")
    response = client.get(
        f"/api/history/{pytest.bot}/trends/conversations/total",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["total_conversation_range"] == {}
    assert actual["message"] is None
    assert actual["success"]


@mock.patch('kairon.history.processor.MongoClient', autospec=True)
def test_total_conversation_range_with_request(mock_mongo):
    mock_mongo.return_value = MongoClient("mongodb://locahost/test")
    response = client.get(
        f"/api/history/{pytest.bot}/trends/conversations/total?"+urlencode({'month': 4}),
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["total_conversation_range"] == {}
    assert actual["message"] is None
    assert actual["success"]


@mock.patch('kairon.history.processor.MongoClient', autospec=True)
def test_conversation__step_range(mock_mongo):
    mock_mongo.return_value = MongoClient("mongodb://locahost/test")
    response = client.get(
        f"/api/history/{pytest.bot}/trends/conversations/steps",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["average_conversation_steps"] == {}
    assert actual["message"] is None
    assert actual["success"]


@mock.patch('kairon.history.processor.MongoClient', autospec=True)
def test_conversation__step_range_with_request(mock_mongo):
    mock_mongo.return_value = MongoClient("mongodb://locahost/test")
    response = client.get(
        f"/api/history/{pytest.bot}/trends/conversations/steps?"+urlencode({'month': 4}),
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["average_conversation_steps"] == {}
    assert actual["message"] is None
    assert actual["success"]


@mock.patch('kairon.history.processor.MongoClient', autospec=True)
def test_wordcloud(mock_mongo):
    mock_mongo.return_value = MongoClient("mongodb://locahost/test")
    response = client.get(
        f"/api/history/{pytest.bot}/conversations/wordcloud",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"] == ""
    assert actual["message"] is None
    assert actual["success"]


@mock.patch('kairon.history.processor.MongoClient', autospec=True)
def test_wordcloud_with_request(mock_mongo):
    mock_mongo.return_value = MongoClient("mongodb://locahost/test")
    response = client.get(
        f"/api/history/{pytest.bot}/conversations/wordcloud?"+urlencode({'month': 4}),
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"] == ""
    assert actual["message"] is None
    assert actual["success"]


@mock.patch('kairon.history.processor.MongoClient', autospec=True)
def test_unique_user_inputs(mock_mongo):
    mock_mongo.return_value = MongoClient("mongodb://locahost/test")
    response = client.get(
        f"/api/history/{pytest.bot}/metrics/users/input",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"] == []
    assert actual["message"] is None
    assert actual["success"]


@mock.patch('kairon.history.processor.MongoClient', autospec=True)
def test_unique_user_inputs_with_request(mock_mongo):
    mock_mongo.return_value = MongoClient("mongodb://locahost/test")
    response = client.get(
        f"/api/history/{pytest.bot}/metrics/users/input?"+urlencode({'month': 4}),
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"] == []
    assert actual["message"] is None
    assert actual["success"]


@mock.patch('kairon.history.processor.MongoClient', autospec=True)
def test_user_dropoff(mock_mongo):
    mock_mongo.return_value = MongoClient("mongodb://locahost/test")
    response = client.get(
        f"/api/history/{pytest.bot}/metrics/fallback/dropoff",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["Dropoff_list"] == {}
    assert actual["message"] is None
    assert actual["success"]


@mock.patch('kairon.history.processor.MongoClient', autospec=True)
def test_user_dropoff_with_request(mock_mongo):
    mock_mongo.return_value = MongoClient("mongodb://locahost/test")
    response = client.get(
        f"/api/history/{pytest.bot}/metrics/fallback/dropoff?"+urlencode({'month': 4}),
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["Dropoff_list"] == {}
    assert actual["message"] is None
    assert actual["success"]


@mock.patch('kairon.history.processor.MongoClient', autospec=True)
def test_user_intent_dropoff(mock_mongo):
    mock_mongo.return_value = MongoClient("mongodb://locahost/test")
    response = client.get(
        f"/api/history/{pytest.bot}/metrics/intents/dropoff",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"] == {}
    assert actual["message"] is None
    assert actual["success"]


@mock.patch('kairon.history.processor.MongoClient', autospec=True)
def test_user_intent_dropoff_with_request(mock_mongo):
    mock_mongo.return_value = MongoClient("mongodb://locahost/test")
    response = client.get(
        f"/api/history/{pytest.bot}/metrics/intents/dropoff?"+urlencode({'month': 4}),
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"] == {}
    assert actual["message"] is None
    assert actual["success"]


@mock.patch('kairon.history.processor.MongoClient', autospec=True)
def test_unsuccessful_sessions(mock_mongo):
    mock_mongo.return_value = MongoClient("mongodb://locahost/test")
    response = client.get(
        f"/api/history/{pytest.bot}/metrics/sessions/unsuccessful",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"] == {}
    assert actual["message"] is None
    assert actual["success"]


@mock.patch('kairon.history.processor.MongoClient', autospec=True)
def test_unsuccessful_sessions_with_request(mock_mongo):
    mock_mongo.return_value = MongoClient("mongodb://locahost/test")
    response = client.get(
        f"/api/history/{pytest.bot}/metrics/sessions/unsuccessful?"+urlencode({'month': 4}),
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"] == {}
    assert actual["message"] is None
    assert actual["success"]


@mock.patch('kairon.history.processor.MongoClient', autospec=True)
def test_total_session(mock_mongo):
    mock_mongo.return_value = MongoClient("mongodb://locahost/test")
    response = client.get(
        f"/api/history/{pytest.bot}/metrics/sessions/total",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"] == {}
    assert actual["message"] is None
    assert actual["success"]


@mock.patch('kairon.history.processor.MongoClient', autospec=True)
def test_total_sessions_with_request(mock_mongo):
    mock_mongo.return_value = MongoClient("mongodb://locahost/test")
    response = client.get(
        f"/api/history/{pytest.bot}/metrics/sessions/total?"+urlencode({'month': 4}),
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"] == {}
    assert actual["message"] is None
    assert actual["success"]


def test_total_session_with_from_date_less_than_six_months():
    from_date = (datetime.utcnow() - timedelta(300)).date()
    to_date = (datetime.utcnow()).date()
    response = client.get(
        f"/api/history/{pytest.bot}/metrics/sessions/total?from_date={from_date}&to_date={to_date}",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"].__contains__('from_date should be within six months and today date')
    assert not actual["success"]


def test_total_session_with_from_date_greater_than_today_date():
    from_date = (datetime.utcnow() + timedelta(30)).date()
    to_date = (datetime.utcnow()).date()
    response = client.get(
        f"/api/history/{pytest.bot}/metrics/sessions/total?from_date={from_date}&to_date={to_date}",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"].__contains__('from_date should be within six months and today date')
    assert not actual["success"]


def test_total_session_with_to_date_less_than_six_months():
    from_date = (datetime.utcnow() - timedelta(30)).date()
    to_date = (datetime.utcnow() - timedelta(300)).date()
    response = client.get(
        f"/api/history/{pytest.bot}/metrics/sessions/total?from_date={from_date}&to_date={to_date}",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"].__contains__('to_date should be within six months and today date')
    assert not actual["success"]


def test_total_session_with_to_date_greater_than_today_date():
    from_date = (datetime.utcnow() - timedelta(30)).date()
    to_date = (datetime.utcnow() + timedelta(30)).date()
    response = client.get(
        f"/api/history/{pytest.bot}/metrics/sessions/total?from_date={from_date}&to_date={to_date}",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"].__contains__('to_date should be within six months and today date')
    assert not actual["success"]


def test_total_session_with_from_date_greater_than_to_date():
    from_date = (datetime.utcnow()).date()
    to_date = (datetime.utcnow() - timedelta(90)).date()
    response = client.get(
        f"/api/history/{pytest.bot}/metrics/sessions/total?from_date={from_date}&to_date={to_date}",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"].__contains__('from_date must be less than to_date')
    assert not actual["success"]


@mock.patch('kairon.history.processor.MongoClient', autospec=True)
def test_total_session_with_valid_from_date_and_to_date(mock_mongo):
    from_date = (datetime.utcnow() - timedelta(30)).date()
    to_date = (datetime.utcnow()).date()
    mock_mongo.return_value = MongoClient("mongodb://locahost/test")
    response = client.get(
        f"/api/history/{pytest.bot}/metrics/sessions/total?from_date={from_date}&to_date={to_date}",
        headers={"Authorization": 'Bearer ' + Utility.environment['tracker']['authentication']['token']},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"] == {}
    assert actual["message"] is None
    assert actual["success"]
