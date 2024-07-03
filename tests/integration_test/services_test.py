import ujson as json
import os
import re
import shutil
import tarfile
import tempfile
from datetime import datetime, timedelta
from io import BytesIO
import yaml
from mock import patch
from urllib.parse import urljoin
from zipfile import ZipFile

import mock
import pytest
import responses
from botocore.exceptions import ClientError
from bson import ObjectId
from fastapi.testclient import TestClient
from jira import JIRAError
from mongoengine import connect
from mongoengine.queryset.base import BaseQuerySet
from pipedrive.exceptions import UnauthorizedError
from pydantic import SecretStr
from rasa.shared.utils.io import read_config_file
from slack_sdk.web.slack_response import SlackResponse

from kairon.api.app.main import app
from kairon.events.definitions.multilingual import MultilingualEvent
from kairon.exceptions import AppException
from kairon.idp.processor import IDPProcessor
from kairon.shared.account.processor import AccountProcessor
from kairon.shared.actions.data_objects import ActionServerLogs
from kairon.shared.actions.utils import ActionUtility
from kairon.shared.auth import Authentication
from kairon.shared.cloud.utils import CloudUtility
from kairon.shared.cognition.data_objects import CognitionSchema, CognitionData
from kairon.shared.constants import EventClass, ChannelTypes
from kairon.shared.data.audit.data_objects import AuditLogData
from kairon.shared.data.constant import (
    UTTERANCE_TYPE,
    EVENT_STATUS,
    TOKEN_TYPE,
    AuditlogActions,
    KAIRON_TWO_STAGE_FALLBACK,
    FeatureMappings,
    DEFAULT_NLU_FALLBACK_RESPONSE,
)
from kairon.shared.data.data_objects import (
    Stories,
    Rules,
    Utterances,
    Intents,
    TrainingExamples,
    Responses,
    ChatClientConfig,
    BotSettings,
    LLMSettings,
    DemoRequestLogs,
)
from kairon.shared.data.model_processor import ModelProcessor
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.data.training_data_generation_processor import (
    TrainingDataGenerationProcessor,
)
from kairon.shared.data.utils import DataUtility
from kairon.shared.metering.constants import MetricType
from kairon.shared.models import StoryEventType
from kairon.shared.models import User
from kairon.shared.multilingual.processor import MultilingualLogProcessor
from kairon.shared.multilingual.utils.translator import Translator
from kairon.shared.organization.processor import OrgProcessor
from kairon.shared.sso.clients.google import GoogleSSO
from kairon.shared.utils import Utility, MailUtility
from urllib.parse import urlencode
from deepdiff import DeepDiff

os.environ["system_file"] = "./tests/testing_data/system.yaml"
client = TestClient(app)
access_token = None
refresh_token = None
token_type = None


@pytest.fixture(autouse=True, scope="class")
def setup():
    os.environ["system_file"] = "./tests/testing_data/system.yaml"
    Utility.load_environment()
    connect(**Utility.mongoengine_connection(Utility.environment["database"]["url"]))
    AccountProcessor.load_system_properties()


def pytest_configure():
    return {
        "token_type": None,
        "access_token": None,
        "refresh_token": None,
        "username": None,
        "bot": None,
        "content_id": None,
    }


async def mock_smtp(*args, **kwargs):
    return None


def complete_end_to_end_event_execution(bot, user, event_class, **kwargs):
    from kairon.events.definitions.data_importer import TrainingDataImporterEvent
    from kairon.events.definitions.model_training import ModelTrainingEvent
    from kairon.events.definitions.model_testing import ModelTestingEvent
    from kairon.events.definitions.history_delete import DeleteHistoryEvent

    overwrite = kwargs.get('overwrite', True)
    if event_class == EventClass.data_importer:
        TrainingDataImporterEvent(bot, user, import_data=True, overwrite=overwrite).execute()
    elif event_class == EventClass.model_training:
        ModelTrainingEvent(bot, user).execute()
    elif event_class == EventClass.model_testing:
        ModelTestingEvent(bot, user).execute()
    elif event_class == EventClass.delete_history:
        DeleteHistoryEvent(bot, user).execute()
    elif event_class == EventClass.multilingual:
        MultilingualEvent(
            bot,
            user,
            dest_lang=kwargs.get("kwargs"),
            translate_responses=kwargs.get("translate_responses"),
            translate_actions=kwargs.get("translate_actions"),
        ).execute()


def test_healthcheck():
    response = client.get("/healthcheck")
    actual = response.json()
    assert response.status_code == 200
    assert actual["message"] == "health check ok"


def test_api_wrong_login():
    response = client.post(
        "/api/auth/login", data={"username": "test@demo.ai", "password": "Welcome@1"}
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert not actual["success"]
    assert actual["message"] == "User does not exist!"
    assert response.headers == {
        "content-length": "79",
        "content-type": "application/json",
        "server": "Secure",
        "strict-transport-security": "includeSubDomains; preload; max-age=31536000",
        "x-frame-options": "SAMEORIGIN",
        "x-xss-protection": "0",
        "x-content-type-options": "nosniff",
        "content-security-policy": "default-src 'self'; frame-ancestors 'self'; form-action 'self'; base-uri 'self'; connect-src 'self'; frame-src 'self'; style-src 'self' https: 'unsafe-inline'; img-src 'self' https:; script-src 'self' https: 'unsafe-inline'",
        "referrer-policy": "no-referrer",
        "cache-control": "must-revalidate",
        "permissions-policy": "accelerometer=(), autoplay=(), camera=(), document-domain=(), encrypted-media=(), fullscreen=(), vibrate=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), midi=(), payment=(), picture-in-picture=(), sync-xhr=(), usb=()",
        "Cross-Origin-Embedder-Policy": "require-corp",
        "Cross-Origin-Opener-Policy": "same-origin",
        "Cross-Origin-Resource-Policy": "same-origin",
        "Access-Control-Allow-Origin": "*",
    }
    value = list(AuditLogData.objects(user="test@demo.ai", action='activity', entity='invalid_login'))
    assert value[0]["entity"] == "invalid_login"
    assert value[0]["timestamp"]
    assert len(value) == 1


@mock.patch("kairon.shared.utils.Utility.validate_recaptcha", autospec=True)
@mock.patch("kairon.shared.utils.MailUtility.trigger_smtp", autospec=True)
def test_book_a_demo(trigger_smtp_mock, validate_recaptcha_mock, monkeypatch):
    monkeypatch.setitem(Utility.environment["security"], "validate_recaptcha", True)
    monkeypatch.setitem(
        Utility.environment["security"], "recaptcha_secret", "asdfghjkl1234567890"
    )
    data = {
        "first_name": "sample",
        "last_name": "test",
        "email": "sampletest@gmail.com",
        "contact": "9876543210",
        "additional_info": "Thank You",
    }
    form_data = {"data": data, "recaptcha_response": "1234567890"}

    with patch("kairon.shared.plugins.ipinfo.IpInfoTracker.execute") as mock_geo:
        mock_geo.return_value = {"City": "Mumbai", "Network": "CATO"}
        response = client.post("/api/user/demo", json=form_data).json()
    assert (
            response["message"]
            == "Thank You for your interest in Kairon. We will reach out to you soon."
    )
    assert not response["data"]
    assert response["error_code"] == 0
    assert response["success"]


@mock.patch("kairon.shared.utils.MailUtility.trigger_smtp", autospec=True)
def test_book_a_demo_with_invalid_recaptcha_response(trigger_smtp_mock, monkeypatch):
    monkeypatch.setitem(Utility.environment["security"], "validate_recaptcha", True)
    monkeypatch.setitem(
        Utility.environment["security"], "recaptcha_secret", "asdfghjkl1234567890"
    )
    data = {
        "first_name": "sample",
        "last_name": "test",
        "email": "sampletest@gmail.com",
        "contact": "9876543210",
        "additional_info": "Thank You",
    }
    form_data = {"data": data, "recaptcha_response": ""}

    with patch("kairon.shared.plugins.ipinfo.IpInfoTracker.execute") as mock_geo:
        mock_geo.return_value = {"City": "Mumbai", "Network": "CATO"}
        response = client.post("/api/user/demo", json=form_data).json()
    assert response["message"] == "recaptcha_response is required"
    assert not response["data"]
    assert response["error_code"] == 422
    assert not response["success"]


@responses.activate
@mock.patch("kairon.shared.utils.MailUtility.trigger_smtp", autospec=True)
def test_book_a_demo_with_validate_recaptcha_failed(trigger_smtp_mock):
    data = {
        "first_name": "sample",
        "last_name": "test",
        "email": "sampletest@gmail.com",
        "contact": "9876543210",
        "additional_info": "Thank You",
    }
    form_data = {"data": data, "recaptcha_response": "1234567890"}

    with patch.dict(
            Utility.environment["security"],
            {"validate_recaptcha": True, "recaptcha_secret": "asdfghjkl1234567890"},
    ):
        with patch("kairon.shared.plugins.ipinfo.IpInfoTracker.execute") as mock_geo:
            mock_geo.return_value = {"City": "Mumbai", "Network": "CATO"}

            responses.add(
                responses.POST,
                "https://www.google.com/recaptcha/api/siteverify?secret=asdfghjkl1234567890&response=1234567890&remoteip=testclient",
                json={"success": False},
            )

            response = client.post("/api/user/demo", json=form_data).json()
    assert response["message"] == "Failed to validate recaptcha"
    assert not response["data"]
    assert response["error_code"] == 422
    assert not response["success"]


@mock.patch("kairon.shared.utils.Utility.validate_recaptcha", autospec=True)
@mock.patch("kairon.shared.utils.MailUtility.trigger_smtp", autospec=True)
def test_book_a_demo_with_valid_data(trigger_smtp_mock, validate_recaptcha_mock, monkeypatch):
    monkeypatch.setitem(Utility.environment['security'], 'validate_recaptcha', True)
    monkeypatch.setitem(Utility.environment['security'], 'recaptcha_secret', 'asdfghjkl1234567890')
    data = {
        "first_name": "Mahesh",
        "last_name": 'Sattala',
        "email": "mahesh.sattala@digite.com",
        "phone": "+919876543210",
        "message": "Thank You",
        "recaptcha_response": "Svw2mPVxM0SkO4_2yxTcDQQ7iKNUDeDhGf4l6C2i"
    }
    form_data = {"data": data, "recaptcha_response": "1234567890"}

    with patch("kairon.shared.plugins.ipinfo.IpInfoTracker.execute") as mock_geo:
        mock_geo.return_value = {"City": "Mumbai", "Network": "CATO"}
        response = client.post(
            "/api/user/demo",
            json=form_data
        ).json()
    assert response['message'] == 'Thank You for your interest in Kairon. We will reach out to you soon.'
    assert not response['data']
    assert response['error_code'] == 0
    assert response['success']
    demo_request_logs = DemoRequestLogs.objects(first_name="Mahesh", last_name="Sattala",
                                                email="mahesh.sattala@digite.com").get().to_mongo().to_dict()
    assert demo_request_logs['first_name'] == "Mahesh"
    assert demo_request_logs['last_name'] == "Sattala"
    assert demo_request_logs['email'] == "mahesh.sattala@digite.com"
    assert demo_request_logs['phone'] == "+919876543210"
    assert demo_request_logs['status'] == "request_received"
    assert demo_request_logs['message'] == "Thank You"
    assert demo_request_logs['recaptcha_response'] == "Svw2mPVxM0SkO4_2yxTcDQQ7iKNUDeDhGf4l6C2i"


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
    assert actual["message"] == [
        {'loc': ['body', 'password'], 'msg': 'Password length must be 10\nMissing 1 uppercase letter',
         'type': 'value_error'}]
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["data"] is None


@responses.activate
def test_recaptcha_verified_request(monkeypatch):
    monkeypatch.setitem(Utility.environment["security"], "validate_recaptcha", True)
    monkeypatch.setitem(
        Utility.environment["security"], "recaptcha_secret", "asdfghjkl1234567890"
    )

    responses.add(
        "POST",
        f"{Utility.environment['security']['recaptcha_url']}?secret=asdfghjkl1234567890&response=1234567890",
        json={"success": True},
    )
    response = client.post(
        "/api/account/registration",
        json={
            "recaptcha_response": "1234567890",
            "email": "integration1234567890@demo.ai",
            "first_name": "Demo",
            "last_name": "User",
            "password": "Welcome@10",
            "confirm_password": "Welcome@10",
            "account": "integration1234567890",
            "bot": "integration",
        },
    )
    actual = response.json()
    assert actual["message"] == "Account Registered!"

    responses.add(
        "POST",
        f"{Utility.environment['security']['recaptcha_url']}?secret=asdfghjkl1234567890&response=1234567890&remoteip=58.0.127.89",
        json={"success": True},
    )
    response = client.post(
        "/api/account/registration",
        json={
            "recaptcha_response": "1234567890",
            "remote_ip": "58.0.127.89",
            "email": "integration1234567@demo.ai",
            "first_name": "Demo",
            "last_name": "User",
            "password": "Welcome@10",
            "confirm_password": "Welcome@10",
            "account": "integration1234567",
            "bot": "integration",
            "add_trusted_device": True,
        },
    )
    actual = response.json()
    assert actual["message"] == "Account Registered!"


@responses.activate
def test_recaptcha_verified_request_invalid(monkeypatch):
    monkeypatch.setitem(Utility.environment["security"], "validate_recaptcha", True)
    monkeypatch.setitem(
        Utility.environment["security"], "recaptcha_secret", "asdfghjkl1234567890"
    )

    responses.add(
        "POST",
        f"{Utility.environment['security']['recaptcha_url']}?secret=asdfghjkl1234567890&response=1234567890",
        json={"success": False},
    )

    responses.add(
        "POST",
        f"{Utility.environment['security']['recaptcha_url']}?secret=asdfghjkl1234567890&response=987654321",
        json={"success": True},
        status=204,
    )

    response = client.post(
        "/api/account/registration",
        json={
            "recaptcha_response": "1234567890",
            "email": "integration1234567890@demo.ai",
            "first_name": "Demo",
            "last_name": "User",
            "password": "Welcome@10",
            "confirm_password": "Welcome@10",
            "account": "integration",
            "bot": "integration",
        },
    )
    actual = response.json()
    assert actual == {
        "success": False,
        "message": "Failed to validate recaptcha",
        "data": None,
        "error_code": 422,
    }

    response = client.post(
        "/api/account/registration",
        json={
            "recaptcha_response": "987654321",
            "email": "integration1234567890@demo.ai",
            "first_name": "Demo",
            "last_name": "User",
            "password": "Welcome@10",
            "confirm_password": "Welcome@10",
            "account": "integration",
            "bot": "integration",
        },
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["message"]
    assert actual["data"] is None
    assert actual["error_code"] == 422

    response = client.post(
        "/api/account/registration",
        json={
            "email": "integration1234567890@demo.ai",
            "first_name": "Demo",
            "last_name": "User",
            "password": "Welcome@10",
            "confirm_password": "Welcome@10",
            "account": "integration",
            "bot": "integration",
        },
    )
    actual = response.json()
    assert actual == {
        "success": False,
        "message": "recaptcha_response is required",
        "data": None,
        "error_code": 422,
    }


@responses.activate
def test_account_registation_temporary_email():
    email = "test@temporay.com"
    api_key = "test"
    with patch.dict(
            Utility.environment,
            {"verify": {"email": {"type": "quickemail", "key": api_key, "enable": True}}},
    ):
        responses.add(
            responses.GET,
            "http://api.quickemailverification.com/v1/verify?"
            + urlencode({"apikey": api_key, "email": email}),
            json={
                "result": "valid",
                "reason": "rejected_email",
                "disposable": "true",
                "accept_all": "false",
                "role": "false",
                "free": "false",
                "email": email,
                "user": "test",
                "domain": "quickemailverification.com",
                "mx_record": "us2.mx1.mailhostbox.com",
                "mx_domain": "mailhostbox.com",
                "safe_to_send": "false",
                "did_you_mean": "",
                "success": "true",
                "message": None,
            },
        )
        response = client.post(
            "/api/account/registration",
            json={
                "email": email,
                "first_name": "Demo",
                "last_name": "User",
                "password": "Welcome@10",
                "confirm_password": "Welcome@10",
                "account": "integration",
                "bot": "integration",
            },
        )
        actual = response.json()
        assert actual["message"] == [
            {
                "loc": ["body", "email"],
                "msg": "Invalid or disposable Email!",
                "type": "value_error",
            }
        ]


@responses.activate
def test_account_registation_invalid_email():
    email = "test@temporay.com"
    api_key = "test"
    with patch.dict(
            Utility.environment,
            {"verify": {"email": {"type": "quickemail", "key": api_key, "enable": True}}},
    ):
        responses.add(
            responses.GET,
            "http://api.quickemailverification.com/v1/verify?"
            + urlencode({"apikey": api_key, "email": email}),
            json={
                "result": "invalid",
                "reason": "rejected_email",
                "disposable": "false",
                "accept_all": "false",
                "role": "false",
                "free": "false",
                "email": email,
                "user": "test",
                "domain": "quickemailverification.com",
                "mx_record": "us2.mx1.mailhostbox.com",
                "mx_domain": "mailhostbox.com",
                "safe_to_send": "false",
                "did_you_mean": "",
                "success": "true",
                "message": None,
            },
        )
        response = client.post(
            "/api/account/registration",
            json={
                "email": email,
                "first_name": "Demo",
                "last_name": "User",
                "password": "Welcome@10",
                "confirm_password": "Welcome@10",
                "account": "integration",
                "bot": "integration",
            },
        )
        actual = response.json()
        assert actual["message"] == [
            {
                "loc": ["body", "email"],
                "msg": "Invalid or disposable Email!",
                "type": "value_error",
            }
        ]


@responses.activate
def test_account_registation_invalid_email_quick_email_valid():
    email = "test@temporay.com"
    api_key = "test"
    with patch.dict(
            Utility.environment,
            {
                "verify": {
                    "email": {"type": "quickemail", "key": api_key, "enable": True}
                }
            },
    ):
        responses.add(
            responses.GET,
            "http://api.quickemailverification.com/v1/verify?"
            + urlencode({"apikey": api_key, "email": email}),
            json={
                "result": "valid",
                "reason": "rejected_email",
                "disposable": "false",
                "accept_all": "false",
                "role": "false",
                "free": "false",
                "email": email,
                "user": "test",
                "domain": "quickemailverification.com",
                "mx_record": "us2.mx1.mailhostbox.com",
                "mx_domain": "mailhostbox.com",
                "safe_to_send": "false",
                "did_you_mean": "",
                "success": "true",
                "message": None,
            },
        )
        response = client.post(
            "/api/account/registration",
            json={
                "email": email,
                "first_name": "Email",
                "last_name": "Validation",
                "password": "Welcome@12",
                "confirm_password": "Welcome@12",
                "account": "email_validation",
                "bot": "email_validation",
            },
        )
        actual = response.json()
        assert actual["message"] == "Account Registered!"


def test_account_registration(monkeypatch):
    response = client.post(
        "/api/account/registration",
        json={
            "email": "integration@demo.ai",
            "first_name": "Demo",
            "last_name": "User",
            "password": "Welcome@10",
            "confirm_password": "Welcome@10",
            "account": "integration",
            "bot": "integration",
        },
    )
    actual = response.json()
    assert actual["message"] == "Account Registered!"

    monkeypatch.setitem(Utility.environment["user"], "validate_trusted_device", True)
    response = client.post(
        "/api/account/registration",
        json={
            "email": "INTEGRATIONTEST@DEMO.AI",
            "first_name": "Demo",
            "last_name": "User",
            "password": "Welcome@10",
            "confirm_password": "Welcome@10",
            "account": "integrationtest",
            "bot": "integrationtest",
            "fingerprint": "asdfghj4567890",
        },
    )
    actual = response.json()
    assert actual["message"] == "Account Registered!"

    monkeypatch.setitem(Utility.environment["user"], "validate_trusted_device", True)
    response = client.post(
        "/api/account/registration",
        json={
            "email": "INTEGRATION2@DEMO.AI",
            "first_name": "Demo",
            "last_name": "User",
            "password": "Welcome@10",
            "confirm_password": "Welcome@10",
            "account": "integration2",
            "bot": "integration2",
            "fingerprint": "asdfghj4567890",
        },
    )
    actual = response.json()
    assert actual["message"] == "Account Registered!"
    assert response.headers == {
        "content-length": "75",
        "content-type": "application/json",
        "server": "Secure",
        "strict-transport-security": "includeSubDomains; preload; max-age=31536000",
        "x-frame-options": "SAMEORIGIN",
        "x-xss-protection": "0",
        "x-content-type-options": "nosniff",
        "content-security-policy": "default-src 'self'; frame-ancestors 'self'; form-action 'self'; base-uri 'self'; connect-src 'self'; frame-src 'self'; style-src 'self' https: 'unsafe-inline'; img-src 'self' https:; script-src 'self' https: 'unsafe-inline'",
        "referrer-policy": "no-referrer",
        "cache-control": "must-revalidate",
        "permissions-policy": "accelerometer=(), autoplay=(), camera=(), document-domain=(), encrypted-media=(), fullscreen=(), vibrate=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), midi=(), payment=(), picture-in-picture=(), sync-xhr=(), usb=()",
        "Cross-Origin-Embedder-Policy": "require-corp",
        "Cross-Origin-Opener-Policy": "same-origin",
        "Cross-Origin-Resource-Policy": "same-origin",
        "Access-Control-Allow-Origin": "*",
    }


def test_account_registration_enable_sso_only(monkeypatch):
    monkeypatch.setitem(Utility.environment["app"], "enable_sso_only", True)
    response = client.post(
        "/api/account/registration",
        json={
            "email": "integration@demo.ai",
            "first_name": "Demo",
            "last_name": "User",
            "password": "Welcome@10",
            "confirm_password": "Welcome@10",
            "account": "integration",
            "bot": "integration",
        },
    )
    actual = response.json()
    assert actual["message"] == "This feature is disabled"
    assert actual["error_code"] == 422
    assert not actual["success"]


def test_api_wrong_password():
    response = client.post(
        "/api/auth/login",
        data={"username": "INTEGRATION@DEMO.AI", "password": "welcome@1"},
    )
    actual = response.json()
    assert actual["error_code"] == 401
    assert not actual["success"]
    assert actual["message"] == "Incorrect username or password"
    value = list(AuditLogData.objects(user="integration@demo.ai", action='activity', entity='invalid_login'))

    assert value[0]["entity"] == "invalid_login"
    assert value[0]["timestamp"]
    assert len(value) == 1


@responses.activate
def test_api_login_with_recaptcha(monkeypatch):
    email = "integration@demo.ai"
    monkeypatch.setitem(Utility.environment["security"], "validate_recaptcha", True)
    monkeypatch.setitem(
        Utility.environment["security"], "recaptcha_secret", "asdfghjkl123456"
    )

    responses.add(
        "POST",
        f"{Utility.environment['security']['recaptcha_url']}?secret=asdfghjkl123456&response=asdfghjkl2345",
        json={"success": True},
    )
    response = client.post(
        "/api/auth/login",
        data={
            "username": email,
            "password": "Welcome@10",
            "recaptcha_response": "asdfghjkl2345",
        },
    )
    actual = response.json()
    assert all(
        [
            True if actual["data"][key] else False
            for key in ["access_token", "token_type"]
        ]
    )


@responses.activate
def test_api_login_with_recaptcha_failed(monkeypatch):
    email = "integration@demo.ai"
    monkeypatch.setitem(Utility.environment["security"], "validate_recaptcha", True)
    monkeypatch.setitem(
        Utility.environment["security"], "recaptcha_secret", "asdfghjkl123456"
    )

    responses.add(
        "POST",
        f"{Utility.environment['security']['recaptcha_url']}?secret=asdfghjkl123456&response=asdfghjkl23",
        json={"success": False},
    )
    response = client.post(
        "/api/auth/login",
        data={
            "username": email,
            "password": "Welcome@10",
            "recaptcha_response": "asdfghjkl23",
        },
    )
    actual = response.json()
    assert actual == {
        "success": False,
        "message": "Failed to validate recaptcha",
        "data": None,
        "error_code": 422,
    }

    response = client.post(
        "/api/auth/login",
        data={"username": email, "password": "Welcome@10"},
    )
    actual = response.json()
    assert actual == {
        "success": False,
        "message": "recaptcha_response is required",
        "data": None,
        "error_code": 422,
    }


def test_api_login(monkeypatch):
    email = "integration@demo.ai"
    response = client.post(
        "/api/auth/login",
        data={"username": email, "password": "Welcome@10"},
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

    response = client.post(
        "/api/account/bot",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token, 'Content-Type': 'application/json'},
        json={"name": "Hi-Hello", "from_template": "Hi-Hello"},
    ).json()
    assert response['message'] == "Bot created"
    assert response['data']['bot_id']

    pytest.username = email
    response = client.get(
        "/api/user/details",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    assert response["data"]["user"]["_id"]
    assert response["data"]["user"]["email"] == "integration@demo.ai"
    assert (
            response["data"]["user"]["bots"]["account_owned"][0]["user"]
            == "integration@demo.ai"
    )
    assert response["data"]["user"]["bots"]["account_owned"][0]["timestamp"]
    assert response["data"]["user"]["bots"]["account_owned"][0]["name"]
    assert response["data"]["user"]["bots"]["account_owned"][0]["_id"]
    assert not response["data"]["user"]["bots"]["shared"]
    assert response["data"]["user"]["timestamp"]
    assert response["data"]["user"]["status"]
    assert response["data"]["user"]["account_name"] == "integration"
    assert response["data"]["user"]["first_name"] == "Demo"
    assert response["data"]["user"]["last_name"] == "User"

    email = "integrationtest@demo.ai"
    response = client.post(
        "/api/auth/login",
        data={"username": email, "password": "Welcome@10"},
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

    email = "integration2@demo.ai"
    response = client.post(
        "/api/auth/login",
        data={"username": email, "password": "Welcome@10"},
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

    email = "integration@demo.ai"
    response = client.post(
        "/api/auth/login",
        data={"username": email, "password": "Welcome@10"},
    )
    actual = response.json()

    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "User Authenticated"
    assert actual["data"]
    assert actual["data"]["token_type"] == "bearer"
    assert actual["data"]["access_token"]
    assert actual["data"]["refresh_token"]
    assert actual["data"]["access_token_expiry"]
    assert actual["data"]["refresh_token_expiry"]
    refresh_token = actual["data"]["refresh_token"]
    access_token = actual["data"]["access_token"]

    response = client.get(
        f"/api/auth/token/refresh",
        headers={"Authorization": pytest.token_type + " " + access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"] == "Only refresh tokens can be used to generate new token!"

    response = client.get(
        f"/api/auth/token/refresh",
        headers={"Authorization": pytest.token_type + " " + refresh_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["access_token"]
    assert actual["data"]["token_type"]
    assert actual["data"]["refresh_token"]
    assert (
            actual["message"]
            == "This token will be shown only once. Please copy this somewhere safe."
               "It is your responsibility to keep the token secret. "
               "If leaked, others may have access to your system."
    )


@responses.activate
def test_augment_questions_without_authenticated():
    response = client.post(
        "/api/augment/questions",
        json={"data": "TESTING TEXTDATA"},
    )

    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 401
    assert actual["data"] is None
    assert actual["message"] == "Not authenticated"


@responses.activate
def test_augment_questions():
    responses.add(
        responses.POST,
        url="http://localhost:8000/questions",
        match=[responses.matchers.json_params_matcher({"data": "TESTING TEXTDATA"})],
        json={
            "success": True,
            "data": {"question": "How can I help you?"},
            "message": None,
            "error_code": 0,
        },
        status=200,
    )
    response = client.post(
        "/api/augment/questions",
        json={"data": "TESTING TEXTDATA"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] == {"question": "How can I help you?"}
    assert Utility.check_empty_string(actual["message"])


def test_api_login_enabled_with_fingerprint(monkeypatch):
    monkeypatch.setitem(Utility.environment["user"], "validate_trusted_device", True)
    email = "integration@demo.ai"
    response = client.post(
        "/api/auth/login",
        data={"username": email, "password": "Welcome@10"},
    )
    actual = response.json()
    assert actual["message"] == "fingerprint is required"
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_add_trusted_device_on_signup_error(monkeypatch):
    monkeypatch.setitem(Utility.environment["user"], "validate_trusted_device", True)
    response = client.post(
        "/api/account/registration",
        json={
            "recaptcha_response": "1234567890",
            "remote_ip": "58.0.127.89",
            "email": "integration1234567@demo.ai",
            "first_name": "Demo",
            "last_name": "User",
            "password": "Welcome@10",
            "confirm_password": "Welcome@10",
            "account": "integration1234567",
            "bot": "integration",
            "fingerprint": None,
        },
    )
    actual = response.json()
    assert actual["message"] == [
        {
            "loc": ["body", "__root__"],
            "msg": "fingerprint is required",
            "type": "value_error",
        }
    ]
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["data"] is None


def test_add_trusted_device_disabled(monkeypatch):
    monkeypatch.setattr(AccountProcessor, "check_email_confirmation", mock_smtp)
    monkeypatch.setattr(MailUtility, "trigger_smtp", mock_smtp)
    response = client.post(
        "/api/account/device/trusted",
        json={"data": "0987654321234567890"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    assert response["message"] == "Trusted devices are disabled!"
    assert not response["data"]
    assert response["error_code"] == 422
    assert not response["success"]


def test_add_trusted_device(monkeypatch):
    monkeypatch.setitem(Utility.environment["user"], "validate_trusted_device", True)
    monkeypatch.setitem(Utility.email_conf["email"], "enable", True)
    monkeypatch.setattr(AccountProcessor, "check_email_confirmation", mock_smtp)
    monkeypatch.setattr(MailUtility, "trigger_smtp", mock_smtp)

    with patch("kairon.shared.plugins.ipinfo.IpInfoTracker.execute") as mock_geo:
        mock_geo.return_value = {"City": "Mumbai", "Network": "CATO"}
        response = client.post(
            "/api/account/device/trusted",
            json={"data": "0987654321234567890"},
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        ).json()
    assert (
            response["message"]
            == "A confirmation link has been sent to your registered mail address"
    )
    assert not response["data"]
    assert response["error_code"] == 0
    assert response["success"]


def test_add_trusted_device_email_disabled(monkeypatch):
    monkeypatch.setitem(Utility.environment["user"], "validate_trusted_device", True)
    with patch("kairon.shared.plugins.ipinfo.IpInfoTracker.execute") as mock_geo:
        mock_geo.return_value = {"City": "Mumbai", "Network": "CATO"}
        response = client.post(
            "/api/account/device/trusted",
            json={"data": "098765432123456456734567"},
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        ).json()
    assert response["message"] == "Trusted device added!"
    assert response["error_code"] == 0
    assert response["success"]


def test_list_trusted_device():
    response = client.get(
        "/api/account/device/trusted",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    assert len(response["data"]["trusted_devices"]) == 1
    assert not response["data"]["trusted_devices"][0].get("fingerprint")
    assert response["data"]["trusted_devices"][0]["is_confirmed"]
    assert response["data"]["trusted_devices"][0]["geo_location"] == {
        "City": "Mumbai",
        "Network": "CATO",
    }
    assert response["data"]["trusted_devices"][0]["geo_location"]
    assert response["data"]["trusted_devices"][0]["confirmation_timestamp"]
    assert response["error_code"] == 0
    assert response["success"]


def test_confirm_trusted_device():
    payload = {"mail_id": "integration@demo.ai", "fingerprint": "0987654321234567890"}
    token = Utility.generate_token_payload(payload, minutes_to_expire=120)
    response = client.post(
        "/api/account/device/trusted/confirm", json={"data": token}
    ).json()
    assert response["message"] == "Trusted device added!"
    assert response["error_code"] == 0
    assert response["success"]


def test_list_trusted_device_2():
    response = client.get(
        "/api/account/device/trusted",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    assert len(response["data"]["trusted_devices"]) == 2
    assert not response["data"]["trusted_devices"][0].get("fingerprint")
    assert response["data"]["trusted_devices"][0]["is_confirmed"]
    assert response["data"]["trusted_devices"][0]["geo_location"] == {
        "City": "Mumbai",
        "Network": "CATO",
    }
    assert response["data"]["trusted_devices"][0]["geo_location"]
    assert response["data"]["trusted_devices"][0]["confirmation_timestamp"]
    assert response["error_code"] == 0
    assert response["success"]


def test_verify_is_trusted():
    response = client.post(
        "/api/account/device/trusted/verify",
        json={"data": "098765432123456456734567"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    assert response["data"] == {"is_trusted_device": True}
    assert response["error_code"] == 0
    assert response["success"]

    response = client.post(
        "/api/account/device/trusted/verify",
        json={"data": "76645657"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    assert response["data"] == {"is_trusted_device": False}
    assert response["error_code"] == 0
    assert response["success"]


def test_remove_trusted_device():
    response = client.delete(
        "/api/account/device/trusted/098765432123456456734567",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    assert not response["data"]
    assert response["error_code"] == 0
    assert response["success"]

    response = client.get(
        "/api/account/device/trusted",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    assert len(response["data"]["trusted_devices"]) == 1


def test_api_login_enabled_sso_only(monkeypatch):
    monkeypatch.setitem(Utility.environment["app"], "enable_sso_only", True)
    email = "integration@demo.ai"
    response = client.post(
        "/api/auth/login",
        data={"username": email, "password": "Welcome@10"},
    )
    actual = response.json()
    assert actual["message"] == "This feature is disabled"
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_add_bot():
    response = client.post(
        "/api/account/bot",
        json={"name": "covid-bot"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    assert response.headers == {
        "content-length": "100",
        "content-type": "application/json",
        "server": "Secure",
        "strict-transport-security": "includeSubDomains; preload; max-age=31536000",
        "x-frame-options": "SAMEORIGIN",
        "x-xss-protection": "0",
        "x-content-type-options": "nosniff",
        "content-security-policy": "default-src 'self'; frame-ancestors 'self'; form-action 'self'; base-uri 'self'; connect-src 'self'; frame-src 'self'; style-src 'self' https: 'unsafe-inline'; img-src 'self' https:; script-src 'self' https: 'unsafe-inline'",
        "referrer-policy": "no-referrer",
        "cache-control": "must-revalidate",
        "permissions-policy": "accelerometer=(), autoplay=(), camera=(), document-domain=(), encrypted-media=(), fullscreen=(), vibrate=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), midi=(), payment=(), picture-in-picture=(), sync-xhr=(), usb=()",
        "Cross-Origin-Embedder-Policy": "require-corp",
        "Cross-Origin-Opener-Policy": "same-origin",
        "Cross-Origin-Resource-Policy": "same-origin",
        "Access-Control-Allow-Origin": "*",
    }
    response = response.json()
    assert response["message"] == "Bot created"
    assert response["error_code"] == 0
    assert response["success"]
    assert response["data"]["bot_id"]


def test_list_bots():
    response = client.get(
        "/api/account/bot",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    pytest.bot = response["data"]["account_owned"][0]["_id"]
    assert response["data"]["account_owned"][0]["user"] == "integration@demo.ai"
    assert response["data"]["account_owned"][0]["timestamp"]
    assert response["data"]["account_owned"][0]["name"] == "Hi-Hello"
    assert response["data"]["account_owned"][0]["_id"]
    assert response["data"]["account_owned"][1]["user"] == "integration@demo.ai"
    assert response["data"]["account_owned"][1]["timestamp"]
    assert response["data"]["account_owned"][1]["name"] == "covid-bot"
    assert response["data"]["account_owned"][1]["_id"]
    assert response["data"]["shared"] == []


def test_get_client_config_with_nudge_server_url():
    expected_app_server_url = Utility.environment['app']['server_url']
    expected_nudge_server_url = Utility.environment['nudge']['server_url']
    expected_chat_server_url = Utility.environment['model']['agent']['url']

    response = client.get(f"/api/bot/{pytest.bot}/chat/client/config",
                          headers={"Authorization": pytest.token_type + " " + pytest.access_token})
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]
    assert actual["data"]["welcomeMessage"] == 'Hello! How are you?'
    assert actual["data"]["name"] == 'kairon'
    assert actual["data"]["buttonType"] == 'button'
    assert actual["data"]["whitelist"] == ["*"]
    assert actual["data"]["nudge_server_url"] == expected_nudge_server_url
    assert actual["data"]["api_server_host_url"] == expected_app_server_url
    assert actual["data"]["chat_server_base_url"] == expected_chat_server_url

@responses.activate
def test_default_values():
    response = client.get(
        "/api/system/default/names"
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0

    expected_default_names = [
        "restart", "back", "out_of_scope", "session_start", "nlu_fallback",
        "action_listen", "action_restart", "action_session_start", "action_default_fallback",
        "action_deactivate_loop", "action_revert_fallback_events", "action_default_ask_affirmation",
        "action_default_ask_rephrase", "action_two_stage_fallback", "action_unlikely_intent",
        "action_back", "...", "action_extract_slots",
        "requested_slot", "session_started_metadata", "knowledge_base_listed_objects",
        "knowledge_base_last_object", "knowledge_base_last_object_type"
    ]

    assert sorted(actual["data"]["default_names"]) == sorted(expected_default_names)

@responses.activate
def test_upload_with_bot_content_only_validate_content_data():
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.data_importer_limit_per_day = 10
    bot_settings.llm_settings['enable_faq'] = True
    bot_settings.save()

    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.data_importer}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )

    files = (
        (
            "training_files",
            (
                "bot_content.yml",
                open("tests/testing_data/all/bot_content.yml", "rb"),
            ),
        ),
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/upload?import_data=true&overwrite=true",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=files,
    )
    actual = response.json()
    assert actual["message"] == "Upload in progress! Check logs."
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]

    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.data_importer
    )

    response = client.get(
        f"/api/bot/{pytest.bot}/importer/logs?start_idx=0&page_size=10",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["logs"][0]["event_status"] == EVENT_STATUS.COMPLETED.value
    assert set(actual["data"]["logs"][0]["files_received"]) == {"bot_content"}
    assert actual["data"]["logs"][0]["is_data_uploaded"]
    assert actual["data"]["logs"][0]["start_timestamp"]
    assert actual["data"]["logs"][0]["end_timestamp"]

    response = client.get(
        f"/api/bot/{pytest.bot}/data/cognition",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    print(actual)

    assert actual["success"]
    assert actual["error_code"] == 0
    assert "data" in actual
    assert "rows" in actual["data"]
    assert len(actual["data"]["rows"]) == 3
    assert all(row["content_type"] == "text" for row in actual["data"]["rows"])
    assert actual["data"]["rows"][0]["data"] == "I am testing upload download bot content in Default Collection 3"
    assert all(row["collection"] is None for row in actual["data"]["rows"])

    CognitionData.objects(bot=pytest.bot).delete()
    CognitionSchema.objects(bot=pytest.bot).delete()

    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.llm_settings['enable_faq'] = False
    bot_settings.save()


@responses.activate
def test_upload_with_bot_content_valifdate_payload_data():
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.data_importer_limit_per_day = 10
    bot_settings.llm_settings['enable_faq'] = True
    bot_settings.save()

    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.data_importer}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )

    files = (
        (
            "training_files",
            ("nlu.yml", open("template/use-cases/Hi-Hello/data/nlu.yml", "rb")),
        ),
        (
            "training_files",
            ("domain.yml", open("template/use-cases/Hi-Hello/domain.yml", "rb")),
        ),
        (
            "training_files",
            ("stories.yml", open("template/use-cases/Hi-Hello/data/stories.yml", "rb")),
        ),
        (
            "training_files",
            ("config.yml", open("template/use-cases/Hi-Hello/config.yml", "rb")),
        ),
        (
            "training_files",
            (
                "chat_client_config.yml",
                open("tests/testing_data/all/chat_client_config.yml", "rb"),
            ),
        ),
        (
            "training_files",
            (
                "bot_content.yml",
                open("tests/testing_data/all/bot_content.yml", "rb"),
            ),
        ),
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/upload?import_data=true&overwrite=true",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=files,
    )
    actual = response.json()
    assert actual["message"] == "Upload in progress! Check logs."
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]

    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.data_importer
    )

    response = client.get(
        f"/api/bot/{pytest.bot}/importer/logs?start_idx=0&page_size=10",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["logs"][0]["event_status"] == EVENT_STATUS.COMPLETED.value
    assert actual["data"]["logs"][0]["is_data_uploaded"]
    assert actual["data"]["logs"][0]["start_timestamp"]
    assert actual["data"]["logs"][0]["end_timestamp"]

    response = client.get(
        f"/api/bot/{pytest.bot}/data/cognition",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        params={"collection": "test_payload_collection"}

    )
    actual = response.json()
    print(actual)

    assert actual["success"]
    assert actual["error_code"] == 0
    assert "data" in actual
    assert "rows" in actual["data"]
    assert len(actual["data"]["rows"]) == 3
    assert all(row["content_type"] == "json" for row in actual["data"]["rows"])
    assert actual["data"]["rows"][0]["data"]["city"] == "City 3"
    assert actual["data"]["rows"][1]["data"]["population"] == "200"
    assert all(row["collection"] == "test_payload_collection" for row in actual["data"]["rows"])

    CognitionData.objects(bot=pytest.bot).delete()
    CognitionSchema.objects(bot=pytest.bot).delete()

    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.llm_settings['enable_faq'] = False
    bot_settings.save()


@responses.activate
def test_upload_with_bot_content_using_event_append_validate_content_data():
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.data_importer_limit_per_day = 10
    bot_settings.llm_settings['enable_faq'] = True
    bot_settings.save()

    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.data_importer}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )

    files = (
        (
            "training_files",
            ("nlu.yml", open("template/use-cases/Hi-Hello/data/nlu.yml", "rb")),
        ),
        (
            "training_files",
            ("domain.yml", open("template/use-cases/Hi-Hello/domain.yml", "rb")),
        ),
        (
            "training_files",
            ("stories.yml", open("template/use-cases/Hi-Hello/data/stories.yml", "rb")),
        ),
        (
            "training_files",
            ("config.yml", open("template/use-cases/Hi-Hello/config.yml", "rb")),
        ),
        (
            "training_files",
            (
                "chat_client_config.yml",
                open("tests/testing_data/all/chat_client_config.yml", "rb"),
            ),
        ),
        (
            "training_files",
            (
                "bot_content.yml",
                open("tests/testing_data/all/bot_content.yml", "rb"),
            ),
        ),
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/upload?import_data=true&overwrite=true",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=files,
    )
    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.data_importer
    )

    response = client.post(
        f"/api/bot/{pytest.bot}/upload?import_data=true&overwrite=false",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=files,
    )

    actual = response.json()
    assert actual["message"] == "Upload in progress! Check logs."
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]

    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.data_importer, overwrite=False
    )

    response = client.get(
        f"/api/bot/{pytest.bot}/importer/logs?start_idx=0&page_size=10",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["logs"][0]["event_status"] == EVENT_STATUS.COMPLETED.value
    assert actual["data"]["logs"][0]["is_data_uploaded"]
    assert actual["data"]["logs"][0]["start_timestamp"]
    assert actual["data"]["logs"][0]["end_timestamp"]

    response = client.get(
        f"/api/bot/{pytest.bot}/data/cognition",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        params={"collection": "test_content_collection"}
    )
    actual = response.json()

    assert actual["success"]
    assert actual["error_code"] == 0
    assert "data" in actual
    assert "rows" in actual["data"]
    assert len(actual["data"]["rows"]) == 4
    assert all(row["content_type"] == "text" for row in actual["data"]["rows"])
    assert actual["data"]["rows"][2]["data"] == "I am testing upload download bot content in Content Collection 2"
    assert all(row["collection"] == "test_content_collection" for row in actual["data"]["rows"])

    CognitionData.objects(bot=pytest.bot).delete()
    CognitionSchema.objects(bot=pytest.bot).delete()

    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.llm_settings['enable_faq'] = False
    bot_settings.save()


@responses.activate
def test_upload_with_bot_content_event_append_validate_payload_data():
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.data_importer_limit_per_day = 10
    bot_settings.llm_settings['enable_faq'] = True
    bot_settings.save()

    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.data_importer}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )

    files = (
        (
            "training_files",
            ("nlu.yml", open("template/use-cases/Hi-Hello/data/nlu.yml", "rb")),
        ),
        (
            "training_files",
            ("domain.yml", open("template/use-cases/Hi-Hello/domain.yml", "rb")),
        ),
        (
            "training_files",
            ("stories.yml", open("template/use-cases/Hi-Hello/data/stories.yml", "rb")),
        ),
        (
            "training_files",
            ("config.yml", open("template/use-cases/Hi-Hello/config.yml", "rb")),
        ),
        (
            "training_files",
            (
                "chat_client_config.yml",
                open("tests/testing_data/all/chat_client_config.yml", "rb"),
            ),
        ),
        (
            "training_files",
            (
                "bot_content.yml",
                open("tests/testing_data/all/bot_content.yml", "rb"),
            ),
        ),
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/upload?import_data=true&overwrite=true",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=files,
    )
    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.data_importer
    )

    response = client.post(
        f"/api/bot/{pytest.bot}/upload?import_data=true&overwrite=false",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=files,
    )
    actual = response.json()
    assert actual["message"] == "Upload in progress! Check logs."
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]

    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.data_importer, overwrite=False
    )

    response = client.get(
        f"/api/bot/{pytest.bot}/importer/logs?start_idx=0&page_size=10",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["logs"][0]["event_status"] == EVENT_STATUS.COMPLETED.value
    assert actual["data"]["logs"][0]["is_data_uploaded"]
    assert actual["data"]["logs"][0]["start_timestamp"]
    assert actual["data"]["logs"][0]["end_timestamp"]

    response = client.get(
        f"/api/bot/{pytest.bot}/data/cognition",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        params={"collection": "test_payload_collection"}
    )
    actual = response.json()

    assert actual["success"]
    assert actual["error_code"] == 0
    assert "data" in actual
    assert "rows" in actual["data"]
    assert len(actual["data"]["rows"]) == 6
    assert all(row["content_type"] == "json" for row in actual["data"]["rows"])
    assert actual["data"]["rows"][4]["data"]["city"] == "City 2"
    assert actual["data"]["rows"][1]["data"]["population"] == "200"
    assert all(row["collection"] == "test_payload_collection" for row in actual["data"]["rows"])

    CognitionData.objects(bot=pytest.bot).delete()
    CognitionSchema.objects(bot=pytest.bot).delete()

    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.llm_settings['enable_faq'] = False
    bot_settings.save()


def test_get_live_agent_with_no_live_agent():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/live_agent",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["data"] == []
    assert actual["error_code"] == 0
    assert not actual["message"]
    assert actual["success"]


def test_enable_live_agent():

    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.live_agent_enabled = True
    bot_settings.save()

    request_body = {
        "bot_response": "connecting to live agent",
        "dispatch_bot_response": False,
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/live_agent",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    print(actual)
    assert actual["error_code"] == 0
    assert actual["message"] == 'Live Agent Action enabled!'
    assert actual["success"]



def test_get_live_agent_after_enabled_no_bot_settings_enabled():
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.live_agent_enabled = False
    bot_settings.save()
    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/live_agent",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    print(actual)
    assert actual["data"] == []
    assert actual["error_code"] == 0
    assert not actual["message"]
    assert actual["success"]

def test_get_live_agent_after_enabled():
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.live_agent_enabled = True
    bot_settings.save()
    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/live_agent",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    print(actual)
    assert actual["data"] == {'name': 'live_agent_action', 'bot_response': 'connecting to live agent',
                              'agent_connect_response': 'Connected to live agent',
                              'agent_disconnect_response': 'Agent has closed the conversation',
                              'agent_not_available_response': 'No agents available at this moment. An agent will reply you shortly.',
                              'dispatch_bot_response': False, 'dispatch_agent_connect_response': True,
                              'dispatch_agent_disconnect_response': True, 'dispatch_agent_not_available_response': True}
    assert actual["error_code"] == 0
    assert not actual["message"]
    assert actual["success"]


def test_enable_live_agent_already_exist():
    request_body = {
        "bot_response": "connecting to live agent",
        "dispatch_bot_response": False,
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/live_agent",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"] == 'Live Agent Action already enabled!'
    assert actual["success"]


def test_update_live_agent():
    BotSettings(bot=pytest.bot, user="integration@demo.ai", live_agent_enabled=True)
    request_body = {
        "bot_response": "connecting to different live agent...",
        "dispatch_bot_response": True,
    }

    response = client.put(
        url=f"/api/bot/{pytest.bot}/action/live_agent",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"] == 'Action updated!'
    assert actual["success"]


def test_get_live_agent_after_updated():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/live_agent",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    print(actual)
    assert actual["data"] == {'name': 'live_agent_action',
                              'bot_response': 'connecting to different live agent...',
                              'agent_connect_response': 'Connected to live agent',
                              'agent_disconnect_response': 'Agent has closed the conversation',
                              'agent_not_available_response': 'No agents available at this moment. An agent will reply you shortly.',
                              'dispatch_bot_response': True,
                              'dispatch_agent_connect_response': True,
                              'dispatch_agent_disconnect_response': True,
                              'dispatch_agent_not_available_response': True}
    assert actual["error_code"] == 0
    assert not actual["message"]
    assert actual["success"]


def test_disable_live_agent():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/live_agent/disable",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert not actual["data"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Live Agent Action disabled!"
    assert actual["success"]


def test_update_live_agent_does_not_exist():
    request_body = {
        "bot_response": "connecting to different live agent",
        "dispatch_bot_response": True,
    }

    response = client.put(
        url=f"/api/bot/{pytest.bot}/action/live_agent",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == 'Live agent not enabled for the bot'
    assert not actual["success"]


def test_get_live_agent_after_disabled():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/live_agent",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    print(actual)
    assert not actual["data"]
    assert actual["error_code"] == 0
    assert not actual["message"]
    assert actual["success"]


def test_add_pyscript_action_empty_name():
    script = """
    data = [1, 2, 3, 4, 5]
    total = 0
    for i in data:
        total += i
    print(total)
    """
    request_body = {
        "name": "",
        "source_code": script,
        "dispatch_response": False,
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/pyscript",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {"loc": ["body", "name"], "msg": "name is required", "type": "value_error"}
    ]
    assert not actual["success"]


def test_add_pyscript_action_empty_source_code():
    request_body = {
        "name": "test_add_pyscript_action_empty_source_code",
        "source_code": "",
        "dispatch_response": False,
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/pyscript",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "source_code"],
            "msg": "source_code is required",
            "type": "value_error",
        }
    ]
    assert not actual["success"]


def test_add_pyscript_action():
    script = """
    data = [1, 2, 3, 4, 5]
    total = 0
    for i in data:
        total += i
    print(total)
    """
    request_body = {
        "name": "test_add_pyscript_action",
        "source_code": script,
        "dispatch_response": False,
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/pyscript",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"] == "Action added!"
    assert actual["success"]


def test_add_pyscript_action_name_already_exist():
    script = """
    data = [1, 2, 3, 4, 5]
    total = 0
    for i in data:
        total += i
    print(total)
    """
    request_body = {
        "name": "test_add_pyscript_action",
        "source_code": script,
        "dispatch_response": False,
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/pyscript",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == "Action exists!"
    assert not actual["success"]


def test_add_pyscript_action_case_insensitivity():
    script = """
    data = [1, 2, 3, 4, 5]
    total = 0
    for i in data:
        total += i
    print(total)
    """
    request_body = {
        "name": "TEST_ADD_PYSCRIPT_ACTION_CASE_INSENSITIVITY",
        "source_code": script,
        "dispatch_response": True,
        "set_slots": [
            {"name": "data", "value": "${data.data}", "evaluation_type": "expression"}
        ],
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/pyscript",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"] == "Action added!"
    assert actual["success"]


def test_update_pyscript_action_does_not_exist():
    script = """
    data = [1, 2, 3, 4, 5]
    total = 0
    for i in data:
        total += i
    print(total)
    """
    request_body = {
        "name": "test_update_pyscript_action",
        "source_code": script,
        "dispatch_response": False,
    }
    response = client.put(
        url=f"/api/bot/{pytest.bot}/action/pyscript",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert (
            actual["message"] == 'Action with name "test_update_pyscript_action" not found'
    )
    assert not actual["success"]


def test_update_pyscript_action():
    script = """
    data = [1, 2, 3, 4, 5, 6, 7]
    total = 0
    for i in data:
        total += i
    print(total)
    """
    request_body = {
        "name": "test_add_pyscript_action",
        "source_code": script,
        "dispatch_response": True,
    }
    response = client.put(
        url=f"/api/bot/{pytest.bot}/action/pyscript",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"] == "Action updated!"
    assert actual["success"]


def test_list_pyscript_actions():
    script1 = """
    data = [1, 2, 3, 4, 5, 6, 7]
    total = 0
    for i in data:
        total += i
    print(total)
    """
    script2 = """
    data = [1, 2, 3, 4, 5]
    total = 0
    for i in data:
        total += i
    print(total)
    """
    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/pyscript",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["success"]
    assert len(actual["data"]) == 2
    assert actual["data"][0]["name"] == "test_add_pyscript_action"
    assert actual["data"][0]["source_code"] == script1
    assert actual["data"][0]["dispatch_response"]
    assert actual["data"][1]["name"] == "test_add_pyscript_action_case_insensitivity"
    assert actual["data"][1]["source_code"] == script2
    assert actual["data"][1]["dispatch_response"]


def test_delete_pyscript_action_not_exists():
    response = client.delete(
        f"/api/bot/{pytest.bot}/action/test_delete_pyscript_action_not_exists",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert (
            actual["message"]
            == 'Action with name "test_delete_pyscript_action_not_exists" not found'
    )


def test_delete_pyscript_action():
    response = client.delete(
        f"/api/bot/{pytest.bot}/action/test_add_pyscript_action",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action deleted"


def test_list_pyscript_actions_after_action_deleted():
    script2 = """
    data = [1, 2, 3, 4, 5]
    total = 0
    for i in data:
        total += i
    print(total)
    """
    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/pyscript",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["success"]
    assert len(actual["data"]) == 1
    assert actual["data"][0]["name"] == "test_add_pyscript_action_case_insensitivity"
    assert actual["data"][0]["source_code"] == script2
    assert actual["data"][0]["dispatch_response"]


def test_list_available_actions():
    script = """
    data = [1, 2, 3, 4, 5, 6]
    total = 0
    for i in data:
        total += i
    print(total)
    """
    request_body = {
        "name": "test_list_available_actions_pyscript_action",
        "source_code": script,
        "dispatch_response": False,
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/pyscript",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["success"]

    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/actions",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual=response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual['data'][-1]['name'] == 'test_list_available_actions_pyscript_action'
    assert actual['data'][-1]['type'] == 'pyscript_action'


def test_get_client_config_url_with_ip_info(monkeypatch):
    monkeypatch.setitem(
        Utility.environment["model"]["agent"], "url", "http://localhost"
    )
    with patch(
            "kairon.shared.plugins.ipinfo.IpInfoTracker.execute"
    ) as mock_geo_location:
        mock_geo_location.return_value = {"City": "Mumbai", "Network": "CATO"}
        response = client.get(
            f"/api/bot/{pytest.bot}/chat/client/config/url",
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        )
        actual = response.json()
        assert actual["success"]
        assert actual["error_code"] == 0
        assert actual["data"]
        pytest.url = actual["data"]

    response = client.get(
        f"/api/bot/{pytest.bot}/metric/user/logs/user_metrics",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["total"] == 2
    assert actual["data"]["logs"][0]["geo_location"] == {
        "City": "Mumbai",
        "Network": "CATO",
    }
    assert actual["data"]["logs"][0]["ip_info"] == "testclient"
    assert actual["data"]["logs"][0]["metric_type"] == "user_metrics"
    assert actual["data"]["logs"][0]["bot"] == pytest.bot


def test_metadata_upload_api(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(bot=pytest.bot, user="integration@demo.ai", llm_settings=LLMSettings(enable_faq=True))

    monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json={
            "metadata": [
                {"column_name": "details", "data_type": "str", "enable_search": True, "create_embeddings": True}],
            "collection_name": "Details"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    pytest.schema_id = actual["data"]["_id"]
    assert actual["message"] == "Schema saved!"
    assert actual["data"]["_id"]
    assert actual["error_code"] == 0

    response_schema = client.get(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual_schema = response_schema.json()
    assert actual_schema["data"][0]['collection_name'] == 'details'
    assert actual_schema["data"][0]['metadata'][0] == {'column_name': 'details', 'data_type': 'str',
                                                       'enable_search': True, 'create_embeddings': True}
    assert actual_schema["error_code"] == 0

    payload = {
        "data": {"details": "Nupur"},
        "collection": "Details",
        "content_type": "json"}
    payload_response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    payload_actual = payload_response.json()
    pytest.cognition_id = payload_actual["data"]["_id"]
    assert payload_actual["message"] == "Record saved!"
    assert payload_actual["error_code"] == 0

    response_payload = client.get(
        url=f"/api/bot/{pytest.bot}/data/cognition?collection=Details",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual_payload = response_payload.json()
    assert actual_payload["success"]
    assert actual_payload["message"] is None
    assert actual_payload["error_code"] == 0
    assert actual_payload["data"]['rows'][0]['collection'] == 'details'
    assert actual_payload["data"]['rows'][0]['data'] == {'details': 'Nupur'}
    assert actual_payload["data"]['total'] == 1

    response_one = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json={
            "metadata": [
                {"column_name": "details_one", "data_type": "str", "enable_search": True, "create_embeddings": True}],
            "collection_name": "Details_one"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual_one = response_one.json()
    pytest.schema_id_one = actual_one["data"]["_id"]
    assert actual_one["message"] == "Schema saved!"
    assert actual_one["data"]["_id"]
    assert actual_one["error_code"] == 0

    response_two = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json={
            "metadata": [
                {"column_name": "details_two", "data_type": "str", "enable_search": True, "create_embeddings": True}],
            "collection_name": "Details_two"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual_two = response_two.json()

    pytest.schema_id_two = actual_two["data"]["_id"]
    assert actual_two["message"] == "Schema saved!"
    assert actual_two["data"]["_id"]
    assert actual_two["error_code"] == 0

    response_three = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json={
            "metadata": [
                {"column_name": "details_three", "data_type": "str", "enable_search": True, "create_embeddings": True}],
            "collection_name": "Details_three"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual_three = response_three.json()
    assert actual_three["message"] == "Collection limit exceeded!"
    assert not actual_three["data"]
    assert actual_three["error_code"] == 422

    response = client.delete(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema/{pytest.schema_id_one}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    response = client.delete(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema/{pytest.schema_id_two}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )

    response_four = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json={
            "metadata": [
                {"column_name": "details", "data_type": "str", "enable_search": True, "create_embeddings": True}],
            "collection_name": "Details"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual_four = response_four.json()
    assert not actual_four["success"]
    assert actual_four["message"] == "Collection already exists!"
    assert actual_four["data"] is None
    assert actual_four["error_code"] == 422


def test_metadata_upload_api_column_limit_exceeded():
    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json={
            "metadata": [
                {"column_name": "tech", "data_type": "str", "enable_search": True, "create_embeddings": True},
                {"column_name": "age", "data_type": "int", "enable_search": True, "create_embeddings": False},
                {"column_name": "color", "data_type": "str", "enable_search": True, "create_embeddings": True},
                {"column_name": "name", "data_type": "str", "enable_search": True, "create_embeddings": True},
                {"column_name": "gender", "data_type": "str", "enable_search": True, "create_embeddings": True}
            ],
            "collection_name": "test_metadata_upload_api_column_limit_exceeded"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["message"] == "Column limit exceeded for collection!"
    assert actual["data"] is None
    assert actual["error_code"] == 422


def test_metadata_upload_api_same_column_in_schema():
    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json={
            "metadata": [
                {"column_name": "tech", "data_type": "str", "enable_search": True, "create_embeddings": True},
                {"column_name": "ai", "data_type": "str", "enable_search": True, "create_embeddings": True},
                {"column_name": "ds", "data_type": "str", "enable_search": True, "create_embeddings": True},
                {"column_name": "tech", "data_type": "str", "enable_search": True, "create_embeddings": True}],
            "collection_name": "test_metadata_upload_api_same_column_in_schema"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["message"] == "Columns cannot be same in the schema!"
    assert actual["data"] is None
    assert actual["error_code"] == 422


def test_metadata_upload_invalid_data_type():
    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json={
            "metadata": [
                {"column_name": "test_metadata_upload_invalid_data_type", "data_type": "bool", "enable_search": True,
                 "create_embeddings": True}],
            "collection_name": "test_metadata_upload_invalid_data_type"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert actual["message"] == [{'loc': ['body', 'metadata', 0, 'data_type'],
                                  'msg': "value is not a valid enumeration member; permitted: 'str', 'int'",
                                  'type': 'type_error.enum', 'ctx': {'enum_values': ['str', 'int']}},
                                 {'loc': ['body', 'metadata', 0, '__root__'],
                                  'msg': 'Only str and int data types are supported', 'type': 'value_error'}]
    assert not actual["data"]
    assert actual["error_code"] == 422


def test_metadata_upload_column_name_empty():
    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json={
            "metadata": [
                {"column_name": "", "data_type": "int", "enable_search": True, "create_embeddings": True}],
            "collection_name": "test_metadata_upload_column_name_empty"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()

    assert actual["message"] == [
        {'loc': ['body', 'metadata', 0, '__root__'], 'msg': 'Column name cannot be empty', 'type': 'value_error'}]
    assert not actual["data"]
    assert actual["error_code"] == 422


def test_get_payload_metadata():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()

    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual['data'][0]['metadata'][0] == {'column_name': 'details', 'data_type': 'str', 'enable_search': True,
                                                'create_embeddings': True}
    assert actual['data'][0]['collection_name'] == 'details'


def test_delete_payload_content_metadata():
    response = client.delete(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema/{pytest.schema_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()

    assert actual["success"]
    assert actual["message"] == "Schema deleted!"
    assert actual["data"] is None
    assert actual["error_code"] == 0


def test_metadata_upload_api_and_delete_with_no_cognition_data(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(
            bot=pytest.bot,
            user="integration@demo.ai",
            llm_settings=LLMSettings(enable_faq=True),
        )

    monkeypatch.setattr(MongoProcessor, "get_bot_settings", _mock_get_bot_settings)
    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json={
            "metadata": [
                {"column_name": "country", "data_type": "str", "enable_search": True, "create_embeddings": True}],
            "collection_name": "Details"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()

    pytest.schema_id = actual["data"]["_id"]
    assert actual["message"] == "Schema saved!"
    assert actual["data"]["_id"]
    assert actual["error_code"] == 0

    response_one = client.delete(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema/{pytest.schema_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual_one = response_one.json()
    assert actual_one["success"]
    assert actual_one["message"] == "Schema deleted!"
    assert actual_one["data"] is None
    assert actual_one["error_code"] == 0


def test_delete_payload_content_metadata_does_not_exist():
    schema_id = '61f3a2c0aef98d5b4c58e90f'
    response = client.delete(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema/{schema_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["message"] == "Schema does not exists!"
    assert actual["data"] is None
    assert actual["error_code"] == 422


def test_get_payload_content_metadata_not_exists():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert actual["success"]
    assert actual["message"] is None
    assert actual["error_code"] == 0
    assert actual["data"] == []


def test_delete_schema_attached_to_prompt_action(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(bot=pytest.bot, user="integration@demo.ai", llm_settings=LLMSettings(enable_faq=True))

    monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)
    action = {'name': 'test_delete_schema_attached_to_prompt_action',
              'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                               'source': 'static', 'is_enabled': True},
                              {'name': 'Similarity Prompt',
                               'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                               'type': 'user', 'source': 'bot_content', 'data': 'python', 'is_enabled': True},
                              {'name': 'Query Prompt',
                               'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                               'instructions': 'Answer according to the context', 'type': 'query',
                               'source': 'static', 'is_enabled': True},
                              {'name': 'Query Prompt',
                               'data': 'If there is no specific query, assume that user is aking about java programming.',
                               'instructions': 'Answer according to the context', 'type': 'query',
                               'source': 'static', 'is_enabled': True}],
              'instructions': ['Answer in a short manner.', 'Keep it simple.'],
              'num_bot_responses': 5,
              "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE}
    response = client.post(
        f"/api/bot/{pytest.bot}/action/prompt",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    response_one = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json={
            "metadata": None,
            "collection_name": "Python"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response_one.json()

    pytest.delete_schema_id = actual["data"]["_id"]

    response_two = client.delete(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema/{pytest.delete_schema_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual_two = response_two.json()

    assert not actual_two["success"]
    assert actual_two[
               "message"] == 'Cannot remove collection python linked to action "test_delete_schema_attached_to_prompt_action"!'
    assert actual_two["data"] is None
    assert actual_two["error_code"] == 422

    response_three = client.delete(
        f"/api/bot/{pytest.bot}/action/test_delete_schema_attached_to_prompt_action",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual_three = response_three.json()
    assert actual_three['message'] == 'Action deleted'

    response_four = client.delete(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema/{pytest.delete_schema_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual_four = response_four.json()
    assert actual_four['message'] == 'Schema deleted!'


def test_content_upload_api_with_gpt_feature_disabled():
    payload = {
        "data": "Data refers to any collection of facts, statistics, or information that can be analyzed or "
                "used to inform decision-making. Data can take many forms, including text, numbers, images, "
                "audio, and video.",
        "content_type": "text",
        "collection": "Data_details"}
    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert actual["message"] == "Faq feature is disabled for the bot! Please contact support."
    assert not actual["data"]
    assert actual["error_code"] == 422


def test_content_upload_api(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(bot=pytest.bot, user="integration@demo.ai", llm_settings=LLMSettings(enable_faq=True))

    monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)
    response_one = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json={
            "collection_name": "Details"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual_one = response_one.json()
    pytest.content_collection_id = actual_one["data"]["_id"]
    payload = {
        "data": "Data refers to any collection of facts, statistics, or information that can be analyzed or "
                "used to inform decision-making. Data can take many forms, including text, numbers, images, "
                "audio, and video.",
        "content_type": "text",
        "collection": "Details"}
    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    pytest.content_id_text = actual["data"]["_id"]
    assert actual["message"] == "Record saved!"
    assert actual["data"]["_id"]
    assert actual["error_code"] == 0

    payload_two = {
        "data": "Data refers to any collection of facts, statistics, or information that can be analyzed.",
        "content_type": "text",
        "collection": "payload_two"}
    response_two = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition",
        json=payload_two,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response_two.json()
    assert actual["message"] == "Collection does not exist!"
    assert not actual["data"]
    assert actual["error_code"] == 422

    response_three = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json={
            "metadata": [
                {"column_name": "color", "data_type": "str", "enable_search": True, "create_embeddings": True}],
            "collection_name": "response_two"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    payload_three = {
        "data": "Data can take many forms, including text, numbers, images, audio, and video.",
        "content_type": "text",
        "collection": "response_two"}
    response_four = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition",
        json=payload_three,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response_four.json()
    assert actual["message"] == "Text content type does not have schema!"
    assert not actual["data"]
    assert actual["error_code"] == 422


def test_content_upload_api_invalid_atleast_ten_words(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(
            bot=pytest.bot,
            user="integration@demo.ai",
            llm_settings=LLMSettings(enable_faq=True),
        )

    monkeypatch.setattr(MongoProcessor, "get_bot_settings", _mock_get_bot_settings)
    payload = {
        "data": "Blockchain technology is an advanced"}
    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["message"] == "Content should contain atleast 10 words."
    assert not actual["success"]
    assert actual["data"] is None
    assert actual["error_code"] == 422


def test_content_upload_empty_data_text(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(bot=pytest.bot, user="integration@demo.ai", llm_settings=LLMSettings(enable_faq=True))

    monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)
    payload = {
        "data": "",
        "content_type": "text",
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["message"] == [{'loc': ['body', '__root__'], 'msg': 'data cannot be empty', 'type': 'value_error'}]


def test_content_upload_api_without_collection(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(bot=pytest.bot, user="integration@demo.ai", llm_settings=LLMSettings(enable_faq=True))

    monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)
    payload = {
        "data": "Blockchain technology is an advanced database mechanism that allows transparent information sharing within a business network."}
    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    pytest.content_id_no_collection = actual["data"]["_id"]
    assert actual["message"] == "Record saved!"
    assert actual["data"]["_id"]
    assert actual["error_code"] == 0


def test_content_update_api():
    response = client.put(
        url=f"/api/bot/{pytest.bot}/data/cognition/{pytest.content_id_text}",
        json={
            "row_id": pytest.content_id_text,
            "data": "AWS Fargate is a serverless compute engine for containers that allows you to run "
                    "Docker containers without having to manage the underlying EC2 instances. With Fargate, "
                    "you can focus on developing and deploying your applications rather than managing the infrastructure.",
            "collection": "Details",
            "content_type": "text"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["message"] == "Record updated!"
    assert actual["error_code"] == 0


def test_content_update_api_collection_does_not_exist():
    response = client.put(
        url=f"/api/bot/{pytest.bot}/data/cognition/{pytest.content_id_text}",
        json={
            "row_id": pytest.content_id_text,
            "data": "Docker containers without having to manage the underlying EC2 instances.",
            "collection": "test_content_update_api_collection_does_not_exist",
            "content_type": "text"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}

    )
    actual = response.json()
    assert not actual["success"]
    assert actual["message"] == "Collection does not exist!"
    assert actual["error_code"] == 422


def test_content_update_api_invalid():
    response = client.put(
        url=f"/api/bot/{pytest.bot}/data/cognition/{pytest.content_id_text}",
        json={
            "row_id": pytest.content_id_text,
            "data": "AWS Fargate is a serverless compute engine.",
            "collection": "Details",
            "content_type": "text"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["message"] == "Content should contain atleast 10 words."
    assert actual["data"] is None
    assert actual["error_code"] == 422


def test_content_update_api_already_exist():
    content_id = "6009cb85e65f6dce28fb3e51"
    response = client.put(
        url=f"/api/bot/{pytest.bot}/data/cognition/{content_id}",
        json={
            "row_id": content_id,
            "data": "AWS Fargate is a serverless compute engine for containers that allows you to run "
                    "Docker containers without having to manage the underlying EC2 instances. With Fargate, "
                    "you can focus on developing and deploying your applications rather than managing the infrastructure.",
            "collection": "Details",
            "content_type": "text"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["message"] == "Payload data already exists!"
    assert actual["data"] is None
    assert actual["error_code"] == 422


def test_content_update_api_id_not_found():
    content_id = "594ced02ed345b2b049222c5"
    response = client.put(
        url=f"/api/bot/{pytest.bot}/data/cognition/{content_id}",
        json={
            "row_id": content_id,
            "data": "Artificial intelligence (AI) involves using computers to do things that traditionally require human "
                    "intelligence. AI can process large amounts of data in ways that humans cannot. The goal for AI is "
                    "to be able to do things like recognize patterns, make decisions, and judge like humans.",
            "collection": "Details",
            "content_type": "text"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["message"] == "Payload with given id not found!"
    assert actual["data"] is None
    assert actual["error_code"] == 422


@mock.patch('kairon.shared.cognition.processor.CognitionDataProcessor.list_cognition_data', autospec=True)
@mock.patch('kairon.shared.cognition.processor.CognitionDataProcessor.get_cognition_data', autospec=True)
def test_list_cognition_data(mock_get_cognition_data, mock_list_cognition_data):
    cognition_data = [{'vector_id': 1,
                       'row_id': '65266ff16f0190ca4fd09898',
                       'data': 'AWS Fargate is a serverless compute engine for containers that allows you to run Docker containers without having to manage the underlying EC2 instances. With Fargate, you can focus on developing and deploying your applications rather than managing the infrastructure.',
                       'content_type': 'text',
                       'collection': 'aws', 'user': '"integration@demo.ai"', 'bot': pytest.bot}]
    row_count = 1

    def _list_cognition_data(*args, **kwargs):
        return cognition_data

    mock_list_cognition_data.return_value = _list_cognition_data()

    def _get_cognition_data(*args, **kwargs):
        return cognition_data, row_count

    mock_get_cognition_data.return_value = _get_cognition_data()

    filter_query = 'without having to manage'
    response = client.get(
        url=f"/api/bot/{pytest.bot}/data/cognition?data={filter_query}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]['rows'][0]['collection'] == 'aws'
    assert actual["data"]['total'] == 1


def test_get_content_without_data():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/data/cognition",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()

    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]['rows'][0]['collection'] == None
    assert actual["data"]['rows'][0][
               'data'] == 'Blockchain technology is an advanced database mechanism that allows transparent information sharing within a business network.'
    assert actual["data"]['total'] == 1


def test_delete_content():
    response_one = client.delete(
        url=f"/api/bot/{pytest.bot}/data/cognition/{pytest.content_id_no_collection}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual_one = response_one.json()
    assert actual_one["success"]
    assert actual_one["message"] == "Record deleted!"
    assert actual_one["data"] is None
    assert actual_one["error_code"] == 0

    response = client.delete(
        url=f"/api/bot/{pytest.bot}/data/cognition/{pytest.content_id_text}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert actual["success"]
    assert actual["message"] == "Record deleted!"
    assert actual["data"] is None
    assert actual["error_code"] == 0


def test_delete_content_does_not_exist():
    content_id = "635981f6e40f61599e000064"
    response = client.delete(
        url=f"/api/bot/{pytest.bot}/data/cognition/{content_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["message"] == "Payload does not exists!"
    assert actual["data"] is None
    assert actual["error_code"] == 422


def test_get_content_not_exists():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/data/cognition",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["success"]
    assert actual["message"] is None
    assert actual["error_code"] == 0
    assert actual["data"] == {'rows': [], 'total': 0}


def test_delete_payload_content_collection():
    response = client.delete(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema/{pytest.content_collection_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()

    assert actual["success"]
    assert actual["message"] == "Schema deleted!"
    assert actual["data"] is None
    assert actual["error_code"] == 0


def test_payload_upload_api_with_gpt_feature_disabled():
    payload = {
        "data": {"name": "Nupur", "age": 25, "city": "Bengaluru"},
        "content_type": "json"}
    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert (
            actual["message"]
            == "Faq feature is disabled for the bot! Please contact support."
    )
    assert not actual["data"]
    assert actual["error_code"] == 422


def test_payload_upload_api(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(
            bot=pytest.bot,
            user="integration@demo.ai",
            llm_settings=LLMSettings(enable_faq=True),
        )

    monkeypatch.setattr(MongoProcessor, "get_bot_settings", _mock_get_bot_settings)
    metadata = {
        "metadata": [{"column_name": "details", "data_type": "str", "enable_search": True, "create_embeddings": True}],
        "collection_name": "Details",
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json=metadata,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    payload = {
        "data": {"details": "AWS"},
        "content_type": "json",
        "collection": "Details"
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    pytest.payload_id = actual["data"]["_id"]
    assert actual["message"] == "Record saved!"
    assert actual["data"]["_id"]
    assert actual["error_code"] == 0


def test_payload_upload_collection_does_not_exists(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(
            bot=pytest.bot,
            user="integration@demo.ai",
            llm_settings=LLMSettings(enable_faq=True),
        )

    monkeypatch.setattr(MongoProcessor, "get_bot_settings", _mock_get_bot_settings)
    payload = {
        "data": {"name": "Ram", "age": 23, "color": "red"},
        "content_type": "json",
        "collection": "test_payload_upload_collection_does_not_exists"
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["message"] == 'Collection does not exist!'


def test_payload_upload_metadata_missing(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(bot=pytest.bot, user="integration@demo.ai", llm_settings=LLMSettings(enable_faq=True))

    monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)
    payload = {
        "data": {"city": "Pune", "color": "red"},
        "content_type": "json",
        "collection": "Details"
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["message"] == 'Columns do not exist in the schema!'


def test_payload_upload_metadata_invalid_data_type(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(bot=pytest.bot, user="integration@demo.ai", llm_settings=LLMSettings(enable_faq=True))

    monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)
    metadata = {
        "metadata": [{"column_name": "age", "data_type": "int", "enable_search": True, "create_embeddings": True}],
        "collection_name": "test_payload_upload_metadata_invalid_data_type"
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json=metadata,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    payload = {
        "data": {"age": "Twenty-Three"},
        "content_type": "json",
        "collection": "test_payload_upload_metadata_invalid_data_type"
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["message"] == 'Invalid data type!'


def test_payload_updated_api_collection_does_not_exists():
    response = client.put(
        url=f"/api/bot/{pytest.bot}/data/cognition/{pytest.payload_id}",
        json={
            "row_id": pytest.payload_id,
            "data": {"details": "data science"},
            "collection": "test_payload_updated_api_collection_does_not_exists",
            "content_type": "json"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}

    )
    actual = response.json()
    assert not actual["success"]
    assert actual["message"] == "Collection does not exist!"
    assert actual["error_code"] == 422


def test_payload_upload_json_data_content_type_text(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(bot=pytest.bot, user="integration@demo.ai", llm_settings=LLMSettings(enable_faq=True))

    monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)
    payload = {
        "data": {"age": 23},
        "content_type": "text",
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["message"] == [
        {'loc': ['body', '__root__'], 'msg': 'content type and type of data do not match!', 'type': 'value_error'}]


def test_payload_updated_api():
    response = client.put(
        url=f"/api/bot/{pytest.bot}/data/cognition/{pytest.payload_id}",
        json={
            "row_id": pytest.payload_id,
            "data": {"details": "data science"},
            "collection": "Details",
            "content_type": "json"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["message"] == "Record updated!"
    assert actual["error_code"] == 0


def test_payload_content_update_api_already_exists(monkeypatch):
    payload_id = "64b3b810efa74e8863544af3"

    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(
            bot=pytest.bot,
            user="integration@demo.ai",
            llm_settings=LLMSettings(enable_faq=True),
        )

    monkeypatch.setattr(MongoProcessor, "get_bot_settings", _mock_get_bot_settings)
    response = client.put(
        url=f"/api/bot/{pytest.bot}/data/cognition/{payload_id}",
        json={
            "row_id": payload_id,
            "data": {"details": "data science"},
            "content_type": "json",
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert not actual["success"]
    assert actual["message"] == "Payload data already exists!"
    assert actual["data"] is None
    assert actual["error_code"] == 422


def test_payload_content_update_api_id_not_found():
    payload_id = "594ced02ed345b2b049222c5"
    response = client.put(
        url=f"/api/bot/{pytest.bot}/data/cognition/{payload_id}",
        json={
            "row_id": payload_id,
            "data": {"details": "data"},
            "content_type": "json",
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}

    )
    actual = response.json()

    assert not actual["success"]
    assert actual["message"] == "Payload with given id not found!"
    assert actual["data"] is None
    assert actual["error_code"] == 422


def test_get_payload_content():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/data/cognition?collection=Details",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()

    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]['rows'][0]['data'] == {'details': 'data science'}
    assert actual["data"]['rows'][0]['collection'] == 'details'
    assert actual["data"]['total'] == 1


def test_delete_payload_content():
    response = client.delete(
        url=f"/api/bot/{pytest.bot}/data/cognition/{pytest.payload_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()

    assert actual["success"]
    assert actual["message"] == "Record deleted!"
    assert actual["data"] is None
    assert actual["error_code"] == 0


def test_delete_payload_content_does_not_exist():
    payload_id = "61f3a2c0aef88d5b4c58e90f"
    response = client.delete(
        url=f"/api/bot/{pytest.bot}/data/cognition/{payload_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["message"] == "Payload does not exists!"
    assert actual["data"] is None
    assert actual["error_code"] == 422


def test_get_payload_content_not_exists():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/data/cognition",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["message"] is None
    assert actual["error_code"] == 0
    assert actual["data"] == {"rows": [], "total": 0}


def test_get_kairon_faq_action_with_no_actions():
    response = client.get(
        f"/api/bot/{pytest.bot}/action/prompt",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert not actual["message"]
    assert actual["data"] == []


def test_add_prompt_action_with_invalid_similarity_threshold(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(bot=pytest.bot, user="integration@demo.ai", llm_settings=LLMSettings(enable_faq=True))

    monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)
    action = {
        "name": "test_add_prompt_action_with_invalid_similarity_threshold",
        "llm_prompts": [
            {
                "name": "System Prompt",
                "data": "You are a personal assistant.",
                "type": "system",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Similarity Prompt",
                'hyperparameters': {"top_results": 10, "similarity_threshold": 1.70},
                "data": "Science",
                "instructions": "Answer question based on the context above, if answer is not in the context go check previous logs.",
                "type": "user",
                "source": "bot_content",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "If there is no specific query, assume that user is aking about java programming.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
        ],
        "num_bot_responses": 5,
        "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE,
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/prompt",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == [{'loc': ['body', 'llm_prompts', 1, 'hyperparameters', '__root__'],
                                  'msg': 'similarity_threshold should be within 0.3 and 1', 'type': 'value_error'}]
    assert not actual["data"]
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_add_prompt_action_with_invalid_top_results(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(bot=pytest.bot, user="integration@demo.ai", llm_settings=LLMSettings(enable_faq=True))

    monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)
    action = {
        "name": "test_add_prompt_action_with_invalid_top_results",
        "llm_prompts": [
            {
                "name": "System Prompt",
                "data": "You are a personal assistant.",
                "type": "system",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Similarity Prompt",
                'hyperparameters': {"top_results": 40, "similarity_threshold": 0.70},
                "data": "Science",
                "instructions": "Answer question based on the context above, if answer is not in the context go check previous logs.",
                "type": "user",
                "source": "bot_content",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "If there is no specific query, assume that user is aking about java programming.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
        ],
        "num_bot_responses": 5,
        "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE,
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/prompt",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == [{'loc': ['body', 'llm_prompts', 1, 'hyperparameters', '__root__'],
                                  'msg': 'top_results should not be greater than 30', 'type': 'value_error'}]
    assert not actual["data"]
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_add_prompt_action_with_invalid_query_prompt():
    action = {
        "name": "test_add_prompt_action_with_invalid_query_prompt",
        "llm_prompts": [
            {
                "name": "System Prompt",
                "data": "You are a personal assistant.",
                "type": "system",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Similarity Prompt",
                "data": "Science",
                "instructions": "Answer question based on the context above, if answer is not in the context go check previous logs.",
                "type": "user",
                "source": "bot_content",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "history",
                "is_enabled": True,
            },
        ],
        "num_bot_responses": 5,
        "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE,
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/prompt",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == [
        {
            "loc": ["body", "llm_prompts"],
            "msg": "Query prompt must have static source!",
            "type": "value_error",
        }
    ]
    assert not actual["data"]
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_add_prompt_action_with_invalid_num_bot_responses():
    action = {
        "name": "test_add_prompt_action_with_invalid_num_bot_responses",
        "llm_prompts": [
            {
                "name": "System Prompt",
                "data": "You are a personal assistant.",
                "type": "system",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Similarity Prompt",
                "data": "Science",
                "instructions": "Answer question based on the context above, if answer is not in the context go check previous logs.",
                "type": "user",
                "source": "bot_content",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "If there is no specific query, assume that user is aking about java programming.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
        ],
        "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE,
        "num_bot_responses": 10,
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/prompt",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == [
        {
            "loc": ["body", "num_bot_responses"],
            "msg": "num_bot_responses should not be greater than 5",
            "type": "value_error",
        }
    ]
    assert not actual["data"]
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_add_prompt_action_with_invalid_system_prompt_source():
    action = {
        "name": "test_add_prompt_action_with_invalid_system_prompt_source",
        "llm_prompts": [
            {
                "name": "System Prompt",
                "data": "You are a personal assistant.",
                "type": "system",
                "source": "history",
                "is_enabled": True,
            },
            {
                "name": "Similarity Prompt",
                "data": "Science",
                "instructions": "Answer question based on the context above, if answer is not in the context go check previous logs.",
                "type": "user",
                "source": "bot_content",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "If there is no specific query, assume that user is aking about java programming.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
        ],
        "num_bot_responses": 5,
        "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/prompt",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == [
        {
            "loc": ["body", "llm_prompts"],
            "msg": "System prompt must have static source!",
            "type": "value_error",
        }
    ]
    assert not actual["data"]
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_add_prompt_action_with_multiple_system_prompt():
    action = {
        "name": "test_add_prompt_action_with_multiple_system_prompt",
        "llm_prompts": [
            {
                "name": "System Prompt",
                "data": "You are a personal assistant.",
                "type": "system",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "System Prompt",
                "data": "You are a personal assistant.",
                "instructions": "Answer question based on the context below.",
                "type": "system",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Similarity Prompt",
                "data": "Science",
                "instructions": "Answer question based on the context above, if answer is not in the context go check previous logs.",
                "type": "user",
                "source": "bot_content",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "If there is no specific query, assume that user is aking about java programming.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
        ],
        "num_bot_responses": 5,
        "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/prompt",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == [
        {
            "loc": ["body", "llm_prompts"],
            "msg": "Only one system prompt can be present!",
            "type": "value_error",
        }
    ]
    assert not actual["data"]
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_add_prompt_action_with_empty_llm_prompt_name():
    action = {
        "name": "test_add_prompt_action_with_empty_llm_prompt_name",
        "llm_prompts": [
            {
                "name": "",
                "data": "You are a personal assistant.",
                "type": "system",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Similarity Prompt",
                "data": "Science",
                "instructions": "Answer question based on the context above, if answer is not in the context go check previous logs.",
                "type": "user",
                "source": "bot_content",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "If there is no specific query, assume that user is aking about java programming.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
        ],
        "num_bot_responses": 5,
        "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/prompt",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == [
        {
            "loc": ["body", "llm_prompts"],
            "msg": "Name cannot be empty!",
            "type": "value_error",
        }
    ]
    assert not actual["data"]
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_add_prompt_action_with_empty_data_for_static_prompt():
    action = {
        "name": "test_add_prompt_action_with_empty_data_for_static_prompt",
        "llm_prompts": [
            {
                "name": "System Prompt",
                "data": "You are a personal assistant.",
                "type": "system",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Similarity Prompt",
                "data": "Science",
                "instructions": "Answer question based on the context above, if answer is not in the context go check previous logs.",
                "type": "user",
                "source": "bot_content",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "If there is no specific query, assume that user is aking about java programming.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
        ],
        "num_bot_responses": 5,
        "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/prompt",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == [
        {
            "loc": ["body", "llm_prompts"],
            "msg": "data is required for static prompts!",
            "type": "value_error",
        }
    ]
    assert not actual["data"]
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_add_prompt_action_with_multiple_history_source_prompts():
    action = {
        "name": "test_add_prompt_action_with_multiple_history_source_prompts",
        "llm_prompts": [
            {
                "name": "System Prompt",
                "data": "You are a personal assistant.",
                "type": "system",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "History Prompt",
                "type": "user",
                "source": "history",
                "is_enabled": True,
            },
            {
                "name": "Analytical Prompt",
                "type": "user",
                "source": "history",
                "is_enabled": True,
            },
            {
                "name": "Similarity Prompt",
                "data": "Science",
                "instructions": "Answer question based on the context above, if answer is not in the context go check previous logs.",
                "type": "user",
                "source": "bot_content",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "If there is no specific query, assume that user is aking about java programming.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
        ],
        "num_bot_responses": 5,
        "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/prompt",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == [
        {
            "loc": ["body", "llm_prompts"],
            "msg": "Only one history source can be present!",
            "type": "value_error",
        }
    ]
    assert not actual["data"]
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_add_prompt_action_with_gpt_feature_disabled():
    action = {
        "name": "test_add_prompt_action_with_gpt_feature_disabled",
        "llm_prompts": [
            {
                "name": "System Prompt",
                "data": "You are a personal assistant.",
                "type": "system",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Similarity Prompt",
                "data": "Science",
                "instructions": "Answer question based on the context above, if answer is not in the context go check previous logs.",
                "type": "user",
                "source": "bot_content",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "If there is no specific query, assume that user is aking about java programming.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
        ],
        "num_bot_responses": 5,
        "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE,
        "top_results": 10,
        "similarity_threshold": 0.70,
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/prompt",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert (
            actual["message"]
            == "Faq feature is disabled for the bot! Please contact support."
    )
    assert not actual["data"]
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_add_prompt_action(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(
            bot=pytest.bot,
            user="integration@demo.ai",
            llm_settings=LLMSettings(enable_faq=True),
        )

    monkeypatch.setattr(MongoProcessor, "get_bot_settings", _mock_get_bot_settings)
    action = {
        "name": "test_add_prompt_action", 'user_question': {'type': 'from_user_message'},
        "llm_prompts": [
            {
                "name": "System Prompt",
                "data": "You are a personal assistant.",
                "type": "system",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Similarity Prompt",
                "data": "Bot_collection",
                "instructions": "Answer question based on the context above, if answer is not in the context go check previous logs.",
                "type": "user",
                "source": "bot_content",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "If there is no specific query, assume that user is aking about java programming.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
        ],
        "instructions": ["Answer in a short manner.", "Keep it simple."],
        "num_bot_responses": 5,
        "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/prompt",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Action Added Successfully"
    assert actual["data"]["_id"]
    pytest.action_id = actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0


def test_add_prompt_action_already_exist(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(
            bot=pytest.bot,
            user="integration@demo.ai",
            llm_settings=LLMSettings(enable_faq=True),
        )

    monkeypatch.setattr(MongoProcessor, "get_bot_settings", _mock_get_bot_settings)
    action = {
        "name": "test_add_prompt_action", 'user_question': {'type': 'from_user_message'},
        "llm_prompts": [
            {
                "name": "System Prompt",
                "data": "You are a personal assistant.",
                "type": "system",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Similarity Prompt",
                "data": "Bot_collection",
                "instructions": "Answer question based on the context above, if answer is not in the context go check previous logs.",
                "type": "user",
                "source": "bot_content",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "If there is no specific query, assume that user is aking about java programming.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
        ],
        "instructions": ["Answer in a short manner.", "Keep it simple."],
        "num_bot_responses": 5,
        "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/prompt",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Action exists!"
    assert not actual["data"]
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_update_prompt_action_does_not_exist():
    action = {
        "name": "test_update_prompt_action_does_not_exist",
        "llm_prompts": [
            {
                "name": "System Prompt",
                "data": "You are a personal assistant.",
                "type": "system",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Similarity Prompt",
                "data": "Bot_collection",
                "instructions": "Answer question based on the context above, if answer is not in the context go check previous logs.",
                "type": "user",
                "source": "bot_content",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "If there is no specific query, assume that user is aking about java programming.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
        ],
        "num_bot_responses": 5,
        "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/prompt/61512cc2c6219f0aae7bba3d",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Action not found"
    assert not actual["data"]
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_update_prompt_action_with_invalid_similarity_threshold():
    action = {
        "name": "test_update_prompt_action_with_invalid_similarity_threshold",
        "llm_prompts": [
            {
                "name": "System Prompt",
                "data": "You are a personal assistant.",
                "type": "system",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Similarity Prompt",
                "data": "Bot_collection",
                'hyperparameters': {"top_results": 9, "similarity_threshold": 1.50},
                "instructions": "Answer question based on the context above, if answer is not in the context go check previous logs.",
                "type": "user",
                "source": "bot_content",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "If there is no specific query, assume that user is aking about java programming.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
        ],
        "num_bot_responses": 5,
        "failure_message": "updated_failure_message"
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/prompt/{pytest.action_id}",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == [{'loc': ['body', 'llm_prompts', 1, 'hyperparameters', '__root__'],
                                  'msg': 'similarity_threshold should be within 0.3 and 1', 'type': 'value_error'}]
    assert not actual["data"]
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_update_prompt_action_with_invalid_top_results():
    action = {
        "name": "test_update_prompt_action_with_invalid_top_results",
        "llm_prompts": [
            {
                "name": "System Prompt",
                "data": "You are a personal assistant.",
                "type": "system",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Similarity Prompt",
                "data": "Bot_collection"
                , 'hyperparameters': {"top_results": 39, "similarity_threshold": 0.50},
                "instructions": "Answer question based on the context above, if answer is not in the context go check previous logs.",
                "type": "user",
                "source": "bot_content",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "If there is no specific query, assume that user is aking about java programming here.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
        ],
        "num_bot_responses": 5,
        "failure_message": "updated_failure_message"
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/prompt/{pytest.action_id}",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == [{'loc': ['body', 'llm_prompts', 1, 'hyperparameters', '__root__'],
                                  'msg': 'top_results should not be greater than 30', 'type': 'value_error'}]
    assert not actual["data"]
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_update_prompt_action_with_invalid_num_bot_responses():
    action = {
        "name": "test_update_prompt_action_with_invalid_num_bot_responses",
        "llm_prompts": [
            {
                "name": "System Prompt",
                "data": "You are a personal assistant.",
                "type": "system",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Similarity Prompt",
                "data": "Science",
                "instructions": "Answer question based on the context above, if answer is not in the context go check previous logs.",
                "type": "user",
                "source": "bot_content",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "If there is no specific query, assume that user is aking about java programming.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
        ],
        "num_bot_responses": 50,
        "failure_message": "updated_failure_message"
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/prompt/{pytest.action_id}",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["message"] == [
        {'loc': ['body', 'num_bot_responses'], 'msg': 'num_bot_responses should not be greater than 5',
         'type': 'value_error'}]
    assert not actual["data"]
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_update_prompt_action_with_invalid_query_prompt():
    action = {
        "name": "test_update_prompt_action_with_invalid_query_prompt",
        "llm_prompts": [
            {
                "name": "System Prompt",
                "data": "You are a personal assistant.",
                "type": "system",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Similarity Prompt",
                "data": "Bot_collection",
                "instructions": "Answer question based on the context above, if answer is not in the context go check previous logs.",
                "type": "user",
                "source": "bot_content",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "A programming language is a system of notation for writing computer programs.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "history",
                "is_enabled": True,
            },
        ],
        "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE,
        "num_bot_responses": 5,
        "use_query_prompt": True,
        "query_prompt": "",
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/prompt/{pytest.action_id}",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["message"] == [
        {
            "loc": ["body", "llm_prompts"],
            "msg": "Query prompt must have static source!",
            "type": "value_error",
        }
    ]
    assert not actual["success"]


def test_update_prompt_action_with_query_prompt_with_false():
    action = {
        "name": "test_update_prompt_action_with_query_prompt_with_false",
        "llm_prompts": [
            {
                "name": "System Prompt",
                "data": "You are a personal assistant.",
                "type": "system",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Similarity Prompt",
                "data": "Bot_collection",
                "instructions": "Answer question based on the context above, if answer is not in the context go check previous logs.",
                "type": "user",
                "source": "bot_content",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "bot_content",
                "is_enabled": False,
            },
        ],
        "failure_message": "updated_failure_message",
        "num_bot_responses": 5,
        "set_slots": [
            {"name": "gpt_result", "value": "${data}", "evaluation_type": "expression"},
            {
                "name": "gpt_result_type",
                "value": "${data.type}",
                "evaluation_type": "script",
            },
        ],
        "dispatch_response": False,
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/prompt/{pytest.action_id}",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["message"] == [
        {
            "loc": ["body", "llm_prompts"],
            "msg": "Query prompt must have static source!",
            "type": "value_error",
        }
    ]
    assert not actual["success"]


def test_update_prompt_action():
    action = {
        "name": "test_update_prompt_action", 'user_question': {'type': 'from_slot', 'value': 'prompt_question'},
        "llm_prompts": [
            {
                "name": "System Prompt",
                "data": "You are a personal assistant.",
                "type": "system",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Similarity_analytical Prompt",
                "data": "Bot_collection",
                "instructions": "Answer question based on the context above, if answer is not in the context go check previous logs.",
                "type": "user",
                "source": "bot_content",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "A programming language is a system of notation for writing computer programs.Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "If there is no specific query, assume that user is aking about java programming language,",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
        ],
        "instructions": ["Answer in a short manner.", "Keep it simple."],
        "num_bot_responses": 5,
        "failure_message": "updated_failure_message"
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/prompt/{pytest.action_id}",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["message"] == "Action updated!"
    assert not actual["data"]
    assert actual["success"]
    assert actual["error_code"] == 0


def test_get_prompt_action():
    response = client.get(
        f"/api/bot/{pytest.bot}/action/prompt",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert not actual["message"]
    actual["data"][0].pop("_id")
    assert actual["data"] == [
        {'name': 'test_update_prompt_action', 'num_bot_responses': 5, 'failure_message': 'updated_failure_message',
         'user_question': {'type': 'from_slot', 'value': 'prompt_question'},
         'hyperparameters': {'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-3.5-turbo', 'top_p': 0.0, 'n': 1,
                             'stream': False, 'stop': None, 'presence_penalty': 0.0, 'frequency_penalty': 0.0,
                             'logit_bias': {}}, 'llm_prompts': [
            {'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system', 'source': 'static',
             'is_enabled': True}, {'name': 'Similarity_analytical Prompt', 'data': 'Bot_collection',
                                   'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                                   'type': 'user', 'source': 'bot_content', 'is_enabled': True},
            {'name': 'Query Prompt',
             'data': 'A programming language is a system of notation for writing computer programs.Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
             'instructions': 'Answer according to the context', 'type': 'query', 'source': 'static',
             'is_enabled': True}, {'name': 'Query Prompt',
                                   'data': 'If there is no specific query, assume that user is aking about java programming language,',
                                   'instructions': 'Answer according to the context', 'type': 'query',
                                   'source': 'static', 'is_enabled': True}],
         'instructions': ['Answer in a short manner.', 'Keep it simple.'], 'set_slots': [], 'dispatch_response': True,
         'status': True}]


def test_add_prompt_action_with_empty_collection_for_bot_content_prompt(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(
            bot=pytest.bot,
            user="integration@demo.ai",
            llm_settings=LLMSettings(enable_faq=True),
        )

    monkeypatch.setattr(MongoProcessor, "get_bot_settings", _mock_get_bot_settings)
    action = {
        "name": "test_add_prompt_action_with_empty_collection_for_bot_content_prompt",
        'user_question': {'type': 'from_user_message'},
        "llm_prompts": [
            {
                "name": "System Prompt",
                "data": "You are a personal assistant.",
                "type": "system",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Similarity Prompt",
                "data": "",
                "instructions": "Answer question based on the context above, if answer is not in the context go check previous logs.",
                "type": "user",
                "source": "bot_content",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "If there is no specific query, assume that user is aking about java programming.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
        ],
        "instructions": ["Answer in a short manner.", "Keep it simple."],
        "num_bot_responses": 5,
        "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/prompt",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Action Added Successfully"
    assert actual["data"]["_id"]
    pytest.action_id = actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0

    response = client.get(
        f"/api/bot/{pytest.bot}/action/prompt",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert not actual["message"]
    actual["data"][1].pop("_id")
    assert actual["data"][1] == {
        'name': 'test_add_prompt_action_with_empty_collection_for_bot_content_prompt', 'num_bot_responses': 5,
        'failure_message': "I'm sorry, I didn't quite understand that. Could you rephrase?",
        'user_question': {'type': 'from_user_message'},
        'hyperparameters': {'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-3.5-turbo', 'top_p': 0.0, 'n': 1,
                            'stream': False, 'stop': None, 'presence_penalty': 0.0, 'frequency_penalty': 0.0,
                            'logit_bias': {}},
        'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                         'source': 'static', 'is_enabled': True},
                        {'name': 'Similarity Prompt', 'data': 'default',
                         'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                         'type': 'user', 'source': 'bot_content', 'is_enabled': True},
                        {'name': 'Query Prompt',
                         'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                         'instructions': 'Answer according to the context', 'type': 'query', 'source': 'static',
                         'is_enabled': True},
                        {'name': 'Query Prompt',
                         'data': 'If there is no specific query, assume that user is aking about java programming.',
                         'instructions': 'Answer according to the context', 'type': 'query', 'source': 'static',
                         'is_enabled': True}],
        'instructions': ['Answer in a short manner.', 'Keep it simple.'], 'set_slots': [],
        'dispatch_response': True, 'status': True}


def test_add_prompt_action_with_bot_content_prompt_with_payload(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(bot=pytest.bot, user="integration@demo.ai", llm_settings=LLMSettings(enable_faq=True),
                           cognition_collections_limit=5)

    monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)

    response_one = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json={
            "metadata": [
                {"column_name": "name", "data_type": "str", "enable_search": True, "create_embeddings": True}],
            "collection_name": "States"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response_one.json()
    pytest.delete_schema_id = actual["data"]["_id"]

    payload = {
        "data": {"name": "Karnataka"},
        "content_type": "json",
        "collection": "States"}
    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    pytest.content_id_text = actual["data"]["_id"]
    assert actual["message"] == "Record saved!"
    assert actual["data"]["_id"]
    assert actual["error_code"] == 0

    action = {'name': 'test_add_prompt_action_with_bot_content_prompt_with_payload',
              'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                               'source': 'static', 'is_enabled': True},
                              {'name': 'Similarity Prompt',
                               'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                               'type': 'user', 'source': 'bot_content', 'data': 'states', 'is_enabled': True},
                              {'name': 'Query Prompt',
                               'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                               'instructions': 'Answer according to the context', 'type': 'query',
                               'source': 'static', 'is_enabled': True},
                              {'name': 'Query Prompt',
                               'data': 'If there is no specific query, assume that user is aking about java programming.',
                               'instructions': 'Answer according to the context', 'type': 'query',
                               'source': 'static', 'is_enabled': True}],
              'instructions': ['Answer in a short manner.', 'Keep it simple.'],
              'num_bot_responses': 5,
              "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE}
    response = client.post(
        f"/api/bot/{pytest.bot}/action/prompt",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    response = client.get(
        f"/api/bot/{pytest.bot}/action/prompt",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    actual["data"][2].pop("_id")
    assert actual["data"][2] == {
        'name': 'test_add_prompt_action_with_bot_content_prompt_with_payload', 'num_bot_responses': 5,
        'failure_message': "I'm sorry, I didn't quite understand that. Could you rephrase?",
        'user_question': {'type': 'from_user_message'},
        'hyperparameters': {'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-3.5-turbo', 'top_p': 0.0, 'n': 1,
                            'stream': False, 'stop': None, 'presence_penalty': 0.0,
                            'frequency_penalty': 0.0, 'logit_bias': {}},
        'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                         'source': 'static', 'is_enabled': True},
                        {'name': 'Similarity Prompt', 'data': 'states',
                         'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                         'type': 'user', 'source': 'bot_content', 'is_enabled': True},
                        {'name': 'Query Prompt',
                         'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                         'instructions': 'Answer according to the context', 'type': 'query', 'source': 'static',
                         'is_enabled': True},
                        {'name': 'Query Prompt',
                         'data': 'If there is no specific query, assume that user is aking about java programming.',
                         'instructions': 'Answer according to the context', 'type': 'query', 'source': 'static',
                         'is_enabled': True}], 'instructions': ['Answer in a short manner.', 'Keep it simple.'],
        'set_slots': [], 'dispatch_response': True, 'status': True}
    assert actual["success"]
    assert actual["error_code"] == 0
    assert not actual["message"]


def test_add_prompt_action_with_bot_content_prompt_with_content(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(bot=pytest.bot, user="integration@demo.ai", llm_settings=LLMSettings(enable_faq=True),
                           cognition_collections_limit=5)

    monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)

    response_one = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json={
            "metadata": None,
            "collection_name": "Python"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response_one.json()
    pytest.delete_schema_id = actual["data"]["_id"]

    payload = {
        "data": "Python is a high-level, general-purpose programming language. "
                "Its design philosophy emphasizes code readability with the use of significant indentation. "
                "Python is dynamically typed and garbage-collected.",
        "content_type": "text",
        "collection": "Python"}
    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    pytest.content_id_text = actual["data"]["_id"]
    assert actual["message"] == "Record saved!"
    assert actual["data"]["_id"]
    assert actual["error_code"] == 0

    action = {'name': 'test_add_prompt_action_with_bot_content_prompt_with_content',
              'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                               'source': 'static', 'is_enabled': True},
                              {'name': 'Similarity Prompt',
                               'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                               'type': 'user', 'source': 'bot_content', 'data': 'python', 'is_enabled': True},
                              {'name': 'Query Prompt',
                               'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                               'instructions': 'Answer according to the context', 'type': 'query',
                               'source': 'static', 'is_enabled': True},
                              {'name': 'Query Prompt',
                               'data': 'If there is no specific query, assume that user is aking about java programming.',
                               'instructions': 'Answer according to the context', 'type': 'query',
                               'source': 'static', 'is_enabled': True}],
              'instructions': ['Answer in a short manner.', 'Keep it simple.'],
              'num_bot_responses': 5,
              "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE}
    response = client.post(
        f"/api/bot/{pytest.bot}/action/prompt",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    response = client.get(
        f"/api/bot/{pytest.bot}/action/prompt",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    actual["data"][3].pop("_id")
    assert actual["data"][3] == {
        'name': 'test_add_prompt_action_with_bot_content_prompt_with_content', 'num_bot_responses': 5,
        'failure_message': "I'm sorry, I didn't quite understand that. Could you rephrase?",
        'user_question': {'type': 'from_user_message'},
        'hyperparameters': {'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-3.5-turbo', 'top_p': 0.0, 'n': 1,
                            'stream': False, 'stop': None, 'presence_penalty': 0.0, 'frequency_penalty': 0.0,
                            'logit_bias': {}},
        'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                         'source': 'static', 'is_enabled': True},
                        {'name': 'Similarity Prompt', 'data': 'python',
                         'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                         'type': 'user', 'source': 'bot_content', 'is_enabled': True},
                        {'name': 'Query Prompt',
                         'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                         'instructions': 'Answer according to the context', 'type': 'query', 'source': 'static',
                         'is_enabled': True},
                        {'name': 'Query Prompt',
                         'data': 'If there is no specific query, assume that user is aking about java programming.',
                         'instructions': 'Answer according to the context', 'type': 'query', 'source': 'static',
                         'is_enabled': True}],
        'instructions': ['Answer in a short manner.', 'Keep it simple.'], 'set_slots': [],
        'dispatch_response': True, 'status': True}
    assert actual["success"]
    assert actual["error_code"] == 0
    assert not actual["message"]


def test_delete_prompt_action_not_exists():
    response = client.delete(
        f"/api/bot/{pytest.bot}/action/non_existent_kairon_faq_action",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert (
            actual["message"]
            == 'Action with name "non_existent_kairon_faq_action" not found'
    )


def test_delete_prompt_action_1():
    response = client.delete(
        f"/api/bot/{pytest.bot}/action/test_add_prompt_action",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action deleted"


def test_list_entities_empty():
    response = client.get(
        f"/api/bot/{pytest.bot}/entities",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert len(actual['data']) == 13
    assert actual["success"]


def test_update_bot_name():
    response = client.put(
        f"/api/account/bot/{pytest.bot}",
        json={"data": "Hi-Hello-bot"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    assert response["message"] == "Name updated"
    assert response["error_code"] == 0
    assert response["success"]

    response = client.get(
        "/api/account/bot",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    assert len(response["data"]) == 2
    pytest.bot = response["data"]["account_owned"][0]["_id"]
    assert response["data"]["account_owned"][0]["name"] == "Hi-Hello-bot"
    assert response["data"]["account_owned"][1]["name"] == "covid-bot"


@pytest.fixture()
def resource_test_upload_zip():
    data_path = "tests/testing_data/yml_training_files"
    tmp_dir = tempfile.gettempdir()
    zip_file = os.path.join(tmp_dir, "test")
    shutil.make_archive(zip_file, "zip", data_path)
    pytest.zip = open(zip_file + ".zip", "rb").read()
    yield "resource_test_upload_zip"
    if os.path.exists(zip_file + ".zip"):
        os.remove(zip_file + ".zip")
    if os.path.exists(os.path.join("training_data", pytest.bot)):
        shutil.rmtree(os.path.join("training_data", pytest.bot))


@responses.activate
def test_upload_zip(resource_test_upload_zip):
    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.data_importer}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )

    files = (
        ("training_files", ("data.zip", pytest.zip)),
        (
            "training_files",
            ("domain.yml", open("tests/testing_data/all/domain.yml", "rb")),
        ),
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/upload?import_data=true&overwrite=false",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=files,
    )
    actual = response.json()
    assert actual["message"] == "Upload in progress! Check logs."
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]

    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.data_importer
    )


@responses.activate
def test_upload():
    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.data_importer}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )

    files = (
        (
            "training_files",
            ("nlu.yml", open("tests/testing_data/all/data/nlu.yml", "rb")),
        ),
        (
            "training_files",
            ("domain.yml", open("tests/testing_data/all/domain.yml", "rb")),
        ),
        (
            "training_files",
            ("stories.yml", open("tests/testing_data/all/data/stories.yml", "rb")),
        ),
        (
            "training_files",
            ("config.yml", open("tests/testing_data/all/config.yml", "rb")),
        ),
        (
            "training_files",
            (
                "chat_client_config.yml",
                open("tests/testing_data/all/chat_client_config.yml", "rb"),
            ),
        ),
        (
            "training_files",
            (
                "bot_content.yml",
                open("tests/testing_data/all/bot_content.yml", "rb"),
            ),
        ),
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/upload?import_data=true&overwrite=true",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=files,
    )
    actual = response.json()
    assert actual["message"] == "Upload in progress! Check logs."
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]
    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.data_importer
    )


@responses.activate
def test_upload_yml():
    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.data_importer}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )

    files = (
        (
            "training_files",
            ("nlu.yml", open("tests/testing_data/valid_yml/data/nlu.yml", "rb")),
        ),
        (
            "training_files",
            ("domain.yml", open("tests/testing_data/valid_yml/domain.yml", "rb")),
        ),
        (
            "training_files",
            (
                "stories.yml",
                open("tests/testing_data/valid_yml/data/stories.yml", "rb"),
            ),
        ),
        (
            "training_files",
            ("config.yml", open("tests/testing_data/valid_yml/config.yml", "rb")),
        ),
        (
            "training_files",
            ("actions.yml", open("tests/testing_data/valid_yml/actions.yml", "rb")),
        ),
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/upload",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=files,
    )
    actual = response.json()
    assert actual["message"] == "Upload in progress! Check logs."
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]
    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.data_importer
    )


def test_list_entities():
    response = client.get(
        f"/api/bot/{pytest.bot}/entities",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    expected = {'bot', 'file', 'category', 'file_text', 'ticketid', 'file_error',
                'priority', 'requested_slot', 'fdresponse', 'kairon_action_response',
                'audio', 'image', 'doc_url', 'document', 'video', 'order', 'latitude',
                'longitude', 'flow_reply', 'http_status_code', 'name', 'quick_reply'}
    assert not DeepDiff({item['name'] for item in actual['data']}, expected, ignore_order=True)
    assert actual["success"]


def test_model_testing_no_existing_models():
    response = client.post(
        url=f"/api/bot/{pytest.bot}/test",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == "No model trained yet. Please train a model to test"
    assert not actual["success"]


@responses.activate
@patch.object(ModelProcessor, "is_daily_training_limit_exceeded")
def test_train(mock_training_limit):
    mock_training_limit.return_value = False
    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.model_training}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )

    response = client.post(
        f"/api/bot/{pytest.bot}/train",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "Model training started."
    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.model_training
    )


def test_upload_limit_exceeded(monkeypatch):
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.data_importer_limit_per_day = 2
    bot_settings.save()
    response = client.post(
        f"/api/bot/{pytest.bot}/upload?import_data=true&overwrite=false",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files={
            "training_files": (
                "nlu.yml",
                open("tests/testing_data/yml_training_files/data/nlu.yml", "rb"),
            )
        },
    )
    actual = response.json()
    assert actual["message"] == "Daily limit exceeded."
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert not actual["success"]


@responses.activate
def test_upload_using_event_failure(monkeypatch):
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.data_importer_limit_per_day = 15
    bot_settings.save()
    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.data_importer}",
    )
    responses.add(
        "POST", event_url, json={"success": False, "message": "Failed to trigger url"}
    )

    response = client.post(
        f"/api/bot/{pytest.bot}/upload?import_data=true&overwrite=true",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=(
            (
                "training_files",
                (
                    "nlu.yml",
                    open("tests/testing_data/yml_training_files/data/nlu.yml", "rb"),
                ),
            ),
            (
                "training_files",
                (
                    "domain.yml",
                    open("tests/testing_data/yml_training_files/domain.yml", "rb"),
                ),
            ),
            (
                "training_files",
                (
                    "stories.yml",
                    open(
                        "tests/testing_data/yml_training_files/data/stories.yml", "rb"
                    ),
                ),
            ),
            (
                "training_files",
                (
                    "config.yml",
                    open("tests/testing_data/yml_training_files/config.yml", "rb"),
                ),
            ),
            (
                "training_files",
                (
                    "actions.yml",
                    open("tests/testing_data/yml_training_files/actions.yml", "rb"),
                ),
            ),
        ),
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert (
            actual["message"]
            == "Failed to trigger data_importer event: Failed to trigger url"
    )


@responses.activate
def test_upload_using_event_append(monkeypatch):
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.data_importer_limit_per_day = 15
    bot_settings.save()

    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.data_importer}",
    )
    responses.add(
        responses.POST,
        event_url,
        json={"success": True},
        status=200,
        match=[
            responses.matchers.json_params_matcher(
                {
                    "data": {
                        "bot": pytest.bot,
                        "user": pytest.username,
                        "import_data": "--import-data",
                        "overwrite": "",
                        "event_type": EventClass.data_importer,
                    },
                    "cron_exp": None,
                    "timezone": None,
                }
            )
        ],
    )

    response = client.post(
        f"/api/bot/{pytest.bot}/upload?import_data=true&overwrite=false",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=(
            (
                "training_files",
                (
                    "nlu.yml",
                    open("tests/testing_data/yml_training_files/data/nlu.yml", "rb"),
                ),
            ),
            (
                "training_files",
                (
                    "domain.yml",
                    open("tests/testing_data/yml_training_files/domain.yml", "rb"),
                ),
            ),
            (
                "training_files",
                (
                    "stories.yml",
                    open(
                        "tests/testing_data/yml_training_files/data/stories.yml", "rb"
                    ),
                ),
            ),
            (
                "training_files",
                (
                    "config.yml",
                    open("tests/testing_data/yml_training_files/config.yml", "rb"),
                ),
            ),
            (
                "training_files",
                (
                    "actions.yml",
                    open("tests/testing_data/yml_training_files/actions.yml", "rb"),
                ),
            ),
        ),
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "Upload in progress! Check logs."
    complete_end_to_end_event_execution(
        pytest.bot, "test_user", EventClass.data_importer
    )


def test_get_qna(monkeypatch):
    data = [
        {
            "_id": "638dde37cfe8a7de324067fa",
            "story": "accelerator_28",
            "intent": "accelerator_28",
            "utterance": "utter_accelerator_28",
            "training_examples": [
                {
                    "text": "What is the purpose of an acceleration?",
                    "_id": "638dde36cfe8a7de32405eaa",
                },
                {
                    "text": "What is the purpose of an accelerators?",
                    "_id": "638dde36cfe8a7de32405eab",
                },
            ],
            "responses": [
                {
                    "_id": "638dde35cfe8a7de32405ada",
                    "text": {
                        "text": "•\tAnything that helps project teams reduce effort, save cost"
                    },
                }
            ],
        },
        {
            "_id": "638dde37cfe8a7de324067fd",
            "story": "accelerator_subscription_mainspring_31",
            "intent": "accelerator_subscription_mainspring_31",
            "utterance": "utter_accelerator_subscription_mainspring_31",
            "training_examples": [
                {
                    "text": "•\tHow do I subscribe to accelerators for my project?",
                    "_id": "638dde36cfe8a7de32405ec0",
                },
                {
                    "text": "•\tHow to do accelerator subscription in mainspring",
                    "_id": "638dde36cfe8a7de32405ec1",
                },
            ],
            "responses": [
                {
                    "_id": "638dde35cfe8a7de32405b64",
                    "custom": {
                        "custom": {
                            "data": [
                                {
                                    "type": "paragraph",
                                    "children": [
                                        {
                                            "text": "Step 1 : Navigate to PM Plan >> Delivery Assets"
                                        }
                                    ],
                                },
                                {
                                    "type": "paragraph",
                                    "children": [
                                        {
                                            "text": "Step 2 : Subscribe the accelerators which are applicable"
                                        }
                                    ],
                                },
                            ]
                        }
                    },
                }
            ],
        },
        {
            "_id": "638dde37cfe8a7de324067fe",
            "story": "accelerators_auto_recommended_32",
            "intent": "accelerators_auto_recommended_32",
            "utterance": "utter_accelerators_auto_recommended_32",
            "training_examples": [
                {
                    "text": "•\tOn what basis are accelerators recommended for a project?",
                    "_id": "638dde36cfe8a7de32405ec3",
                },
                {
                    "text": "•\tWhat is the criteria based on which accelerators are auto recommended ?",
                    "_id": "638dde36cfe8a7de32405ec4",
                },
            ],
            "responses": [
                {
                    "_id": "638dde35cfe8a7de32405b2d",
                    "text": {
                        "text": "•\tAccelerators are auto-recommended from Knowhub based on these project attributes"
                    },
                }
            ],
        },
    ]

    def __mock_qna(*args, **kwargs):
        for item in data:
            yield item

    monkeypatch.setattr(BaseQuerySet, "aggregate", __mock_qna)

    response = client.get(
        f"/api/bot/{pytest.bot}/qna/flatten",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["success"]
    assert actual["data"] == {"qna": data, "total": 0}


def test_model_testing_not_trained():
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.test_limit_per_day = 0
    bot_settings.save()
    response = client.post(
        url=f"/api/bot/{pytest.bot}/test",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == "Daily limit exceeded."
    assert not actual["success"]


def test_get_data_importer_logs():
    response = client.get(
        f"/api/bot/{pytest.bot}/importer/logs?start_idx=0&page_size=10",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]["logs"]) == 10
    assert actual["data"]["total"] == 10
    assert actual["data"]["logs"][0]["event_status"] == EVENT_STATUS.COMPLETED.value
    assert set(actual["data"]["logs"][0]["files_received"]) == {
        "stories",
        "nlu",
        "domain",
        "config",
        "actions",
    }
    assert actual["data"]["logs"][0]["is_data_uploaded"]
    assert actual["data"]["logs"][0]["start_timestamp"]
    assert actual["data"]["logs"][0]["end_timestamp"]

    assert actual['data']["logs"][1]['event_status'] == EVENT_STATUS.COMPLETED.value
    assert actual['data']["logs"][1]['status'] == 'Success'
    assert set(actual['data']["logs"][1]['files_received']) == {'stories', 'nlu', 'domain', 'config', 'actions'}
    assert actual['data']["logs"][1]['is_data_uploaded']
    assert actual['data']["logs"][1]['start_timestamp']
    assert actual['data']["logs"][1]['end_timestamp']
    del actual['data']["logs"][1]['start_timestamp']
    del actual['data']["logs"][1]['end_timestamp']
    del actual['data']["logs"][1]['files_received']
    assert actual['data']["logs"][1] == {'intents': {'count': 14, 'data': []}, 'utterances': {'count': 14, 'data': []},
                                         'stories': {'count': 16, 'data': []},
                                         'training_examples': {'count': 192, 'data': []},
                                         'domain': {'intents_count': 19, 'actions_count': 23, 'slots_count': 10,
                                                    'utterances_count': 14, 'forms_count': 2, 'entities_count': 8,
                                                    'data': []},
                                         'config': {'count': 0, 'data': []}, 'rules': {'count': 1, 'data': []},
                                         'actions': [{'type': 'http_actions', 'count': 5, 'data': []},
                                                     {'type': 'slot_set_actions', 'count': 0, 'data': []},
                                                     {'type': 'form_validation_actions', 'count': 0, 'data': []},
                                                     {'type': 'email_actions', 'count': 0, 'data': []},
                                                     {'type': 'google_search_actions', 'count': 0, 'data': []},
                                                     {'type': 'jira_actions', 'count': 0, 'data': []},
                                                     {'type': 'zendesk_actions', 'count': 0, 'data': []},
                                                     {'type': 'pipedrive_leads_actions', 'count': 0, 'data': []},
                                                     {'type': 'prompt_actions', 'count': 0, 'data': []},
                                                     {'type': 'razorpay_actions', 'count': 0, 'data': []},
                                                     {'type': 'pyscript_actions', 'count': 0, 'data': []}],
                                         'multiflow_stories': {'count': 0, 'data': []},
                                         'bot_content': {'count': 0, 'data': []},
                                         'user_actions': {'count': 7, 'data': []},
                                         'exception': '',
                                         'is_data_uploaded': True,
                                         'status': 'Success', 'event_status': 'Completed'}
    assert actual['data']["logs"][2]['event_status'] == EVENT_STATUS.COMPLETED.value
    assert actual['data']["logs"][2]['status'] == 'Failure'
    assert set(actual['data']["logs"][2]['files_received']) == {'stories', 'nlu', 'domain', 'config',
                                                                'chat_client_config', 'bot_content'}
    assert actual['data']["logs"][2]['is_data_uploaded']
    assert actual['data']["logs"][2]['start_timestamp']
    assert actual['data']["logs"][2]['end_timestamp']

    assert actual['data']["logs"][3]['event_status'] == EVENT_STATUS.COMPLETED.value
    assert actual['data']["logs"][3]['status'] == 'Failure'
    assert set(actual['data']["logs"][3]['files_received']) == {'rules', 'stories', 'nlu', 'domain', 'config',
                                                                'actions', 'chat_client_config', 'multiflow_stories', 'bot_content'}
    assert actual['data']["logs"][3]['is_data_uploaded']
    assert actual['data']["logs"][3]['start_timestamp']
    assert actual['data']["logs"][3]['end_timestamp']
    assert actual['data']["logs"][3]['intents']['count'] == 19
    assert len(actual['data']["logs"][3]['intents']['data']) == 21
    assert actual['data']["logs"][3]['utterances']['count'] == 27
    assert len(actual['data']["logs"][3]['utterances']['data']) == 11
    assert actual['data']["logs"][3]['stories']['count'] == 16
    assert len(actual['data']["logs"][3]['stories']['data']) == 1
    assert actual['data']["logs"][3]['rules']['count'] == 3
    assert len(actual['data']["logs"][3]['rules']['data']) == 0
    assert actual['data']["logs"][3]['training_examples']['count'] == 305
    assert len(actual['data']["logs"][3]['training_examples']['data']) == 0
    assert actual['data']["logs"][3]['domain'] == {'intents_count': 32, 'actions_count': 41, 'slots_count': 11,
                                                   'utterances_count': 27, 'forms_count': 2, 'entities_count': 9,
                                                   'data': []}
    assert actual['data']["logs"][3]['config'] == {'count': 0, 'data': []}
    assert actual['data']["logs"][3]['actions'] == [{'type': 'http_actions', 'count': 5, 'data': []},
                                                    {'type': 'slot_set_actions', 'count': 0, 'data': []},
                                                    {'type': 'form_validation_actions', 'count': 0, 'data': []},
                                                    {'type': 'email_actions', 'count': 0, 'data': []},
                                                    {'type': 'google_search_actions', 'count': 1, 'data': []},
                                                    {'type': 'jira_actions', 'count': 0, 'data': []},
                                                    {'type': 'zendesk_actions', 'count': 0, 'data': []},
                                                    {'type': 'pipedrive_leads_actions', 'count': 0, 'data': []},
                                                    {'type': 'prompt_actions', 'count': 0, 'data': []},
                                                    {'type': 'razorpay_actions', 'count': 0, 'data': []},
                                                    {'type': 'pyscript_actions', 'count': 0, 'data': []}
                                                    ]
    assert actual['data']["logs"][3]['is_data_uploaded']
    assert set(actual['data']["logs"][3]['files_received']) == {'rules', 'stories', 'nlu', 'config', 'domain',
                                                                'actions', 'chat_client_config', 'multiflow_stories','bot_content'}


@responses.activate
def test_upload_with_chat_client_config_only():
    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.data_importer}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )

    files = (
        (
            "training_files",
            (
                "chat_client_config.yml",
                open("tests/testing_data/all/chat_client_config.yml", "rb"),
            ),
        ),
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/upload?import_data=true&overwrite=true",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=files,
    )
    actual = response.json()
    assert actual["message"] == "Upload in progress! Check logs."
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]

    response = client.get(
        f"/api/bot/{pytest.bot}/importer/logs?start_idx=0&page_size=10",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["logs"][0]["event_status"] == EVENT_STATUS.COMPLETED.value
    assert set(actual["data"]["logs"][0]["files_received"]) == {"chat_client_config"}
    assert actual["data"]["logs"][0]["is_data_uploaded"]
    assert actual["data"]["logs"][0]["start_timestamp"]
    assert actual["data"]["logs"][0]["end_timestamp"]

    response = client.get(
        f"/api/bot/{pytest.bot}/chat/client/config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    actual['data'].pop('headers')
    actual['data'].pop('nudge_server_url')
    assert actual["data"] == Utility.read_yaml("tests/testing_data/all/chat_client_config.yml")["config"]


@responses.activate
def test_upload_with_chat_client_config():
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.data_importer_limit_per_day = 15
    bot_settings.save()
    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.data_importer}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )

    files = (
        (
            "training_files",
            ("nlu.yml", open("tests/testing_data/all/data/nlu.yml", "rb")),
        ),
        (
            "training_files",
            ("domain.yml", open("tests/testing_data/all/domain.yml", "rb")),
        ),
        (
            "training_files",
            ("stories.yml", open("tests/testing_data/all/data/stories.yml", "rb")),
        ),
        (
            "training_files",
            ("config.yml", open("tests/testing_data/all/config.yml", "rb")),
        ),
        (
            "training_files",
            (
                "chat_client_config.yml",
                open("tests/testing_data/all/chat_client_config.yml", "rb"),
            ),
        ),
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/upload?import_data=true&overwrite=true",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=files,
    )
    actual = response.json()
    assert actual["message"] == "Upload in progress! Check logs."
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]
    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.data_importer
    )


@responses.activate
def test_upload_without_chat_client_config():
    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.data_importer}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )

    files = (
        (
            "training_files",
            ("nlu.yml", open("tests/testing_data/all/data/nlu.yml", "rb")),
        ),
        (
            "training_files",
            ("domain.yml", open("tests/testing_data/all/domain.yml", "rb")),
        ),
        (
            "training_files",
            ("stories.yml", open("tests/testing_data/all/data/stories.yml", "rb")),
        ),
        (
            "training_files",
            ("config.yml", open("tests/testing_data/all/config.yml", "rb")),
        ),
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/upload?import_data=true&overwrite=true",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=files,
    )
    actual = response.json()
    assert actual["message"] == "Upload in progress! Check logs."
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]
    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.data_importer
    )


def test_download_data_with_chat_client_config():
    response = client.get(
        f"/api/bot/{pytest.bot}/download/data",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    file_bytes = BytesIO(response.content)
    zip_file = ZipFile(file_bytes, mode="r")
    assert zip_file.filelist.__len__() == 10
    assert zip_file.getinfo("chat_client_config.yml")
    assert zip_file.getinfo("config.yml")
    assert zip_file.getinfo("domain.yml")
    assert zip_file.getinfo("actions.yml")
    assert zip_file.getinfo("bot_content.yml")
    assert zip_file.getinfo("multiflow_stories.yml")
    assert zip_file.getinfo("data/stories.yml")
    assert zip_file.getinfo("data/rules.yml")
    assert zip_file.getinfo("data/nlu.yml")


def test_get_slots():
    response = client.get(
        f"/api/bot/{pytest.bot}/slots",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert "data" in actual
    assert len(actual["data"]) == 20
    assert actual["success"]
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])


def test_add_slots():
    response = client.post(
        f"/api/bot/{pytest.bot}/slots",
        json={
            "name": "bot_add",
            "type": "any",
            "initial_value": "bot",
            "influence_conversation": False,
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert "data" in actual
    assert actual["message"] == "Slot added successfully!"
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0


def test_add_slots_duplicate():
    response = client.post(
        f"/api/bot/{pytest.bot}/slots",
        json={
            "name": "bot_add",
            "type": "any",
            "initial_value": "bot",
            "influence_conversation": False,
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["message"] == "Slot already exists!"
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_add_empty_slots():
    response = client.post(
        f"/api/bot/{pytest.bot}/slots",
        json={
            "name": "",
            "type": "any",
            "initial_value": "bot",
            "influence_conversation": False,
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Slot Name cannot be empty or blank spaces"


def test_add_invalid_slots_type():
    response = client.post(
        f"/api/bot/{pytest.bot}/slots",
        json={
            "name": "bot_invalid",
            "type": "invalid",
            "initial_value": "bot",
            "influence_conversation": False,
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert (
            actual["message"][0]["msg"]
            == "value is not a valid enumeration member; permitted: 'float', 'categorical', 'list', 'text', 'bool', 'any'"
    )
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_edit_slots():
    response = client.put(
        f"/api/bot/{pytest.bot}/slots",
        json={
            "name": "bot",
            "type": "text",
            "initial_value": "bot",
            "influence_conversation": False,
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Slot updated!"


def test_edit_empty_slots():
    response = client.put(
        f"/api/bot/{pytest.bot}/slots",
        json={
            "name": "",
            "type": "any",
            "initial_value": "bot",
            "influence_conversation": False,
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Slot Name cannot be empty or blank spaces"


def test_delete_slots():
    response = client.post(
        f"/api/bot/{pytest.bot}/slots",
        json={
            "name": "color",
            "type": "any",
            "initial_value": "bot",
            "influence_conversation": False,
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    print(response.json())

    response = client.delete(
        f"/api/bot/{pytest.bot}/slots/color",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["message"] == "Slot deleted!"
    assert actual["success"]
    assert actual["error_code"] == 0


def test_edit_invalid_slots_type():
    response = client.put(
        f"/api/bot/{pytest.bot}/slots",
        json={
            "name": "bot",
            "type": "invalid",
            "initial_value": "bot",
            "influence_conversation": False,
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert (
            actual["message"][0]["msg"]
            == "value is not a valid enumeration member; permitted: 'float', 'categorical', 'list', 'text', 'bool', 'any'"
    )


def test_get_intents():
    response = client.get(
        f"/api/bot/{pytest.bot}/intents",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert "data" in actual
    assert len(actual["data"]) == 19
    assert actual["success"]
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])


def test_get_all_intents():
    response = client.get(
        f"/api/bot/{pytest.bot}/intents/all",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert "data" in actual
    assert len(actual["data"]) == 19
    assert actual["success"]
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])


def test_add_intents():
    response = client.post(
        f"/api/bot/{pytest.bot}/intents",
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
        f"/api/bot/{pytest.bot}/intents",
        json={"data": "happier"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Intent already exists!"


def test_add_empty_intents():
    response = client.post(
        f"/api/bot/{pytest.bot}/intents",
        json={"data": ""},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Intent Name cannot be empty or blank spaces"


def test_get_training_examples():
    response = client.get(
        f"/api/bot/{pytest.bot}/training_examples/greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert len(actual["data"]) == 8
    assert actual["success"]
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])


def test_training_example_exists():
    response = client.get(
        f"/api/bot/{pytest.bot}/training_examples/exists/hey",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"] == {"is_exists": True, "intent": "greet"}
    assert actual["success"]
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])


def test_training_example_does_not_exist():
    response = client.get(
        f"/api/bot/{pytest.bot}/training_examples/exists/xyz",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"] == {"is_exists": False, "intent": None}
    assert actual["success"] == True
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])


def test_get_training_examples_empty_intent():
    response = client.get(
        f"/api/bot/{pytest.bot}/training_examples/ ",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert len(actual["data"]) == 0
    assert actual["success"]
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])


def test_get_training_examples_as_dict(monkeypatch):
    training_examples = {"hi": "greet", "hello": "greet", "ok": "affirm", "no": "deny"}

    def _mongo_aggregation(*args, **kwargs):
        return [{"training_examples": training_examples}]

    monkeypatch.setattr(BaseQuerySet, "aggregate", _mongo_aggregation)

    response = client.get(
        f"/api/bot/{pytest.bot}/training_examples",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"] == training_examples
    assert actual["success"]
    assert actual["error_code"] == 0


def test_add_training_examples():
    response = client.post(
        f"/api/bot/{pytest.bot}/training_examples/greet",
        json={"data": ["How do you do?"]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"][0]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] is None
    response = client.get(
        f"/api/bot/{pytest.bot}/training_examples/greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert len(actual["data"]) == 9


def test_add_training_examples_duplicate():
    response = client.post(
        f"/api/bot/{pytest.bot}/training_examples/greet",
        json={"data": ["How do you do?"]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert (
            actual["data"][0]["message"] == "Training Example exists in intent: ['greet']"
    )
    assert actual["data"][0]["_id"] is None


def test_add_empty_training_examples():
    response = client.post(
        f"/api/bot/{pytest.bot}/training_examples/greet",
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
        f"/api/bot/{pytest.bot}/training_examples/greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    training_examples = training_examples.json()
    assert len(training_examples["data"]) == 9
    id = training_examples["data"][0]["_id"]
    response = client.delete(
        f"/api/bot/{pytest.bot}/training_examples/{id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Training Example removed!"
    training_examples = client.get(
        f"/api/bot/{pytest.bot}/training_examples/greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    training_examples = training_examples.json()
    assert len(training_examples["data"]) == 8


def test_remove_training_examples_empty_id():
    response = client.delete(
        f"/api/bot/{pytest.bot}/training_examples/ ",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Unable to remove document"


def test_edit_training_examples():
    training_examples = client.get(
        f"/api/bot/{pytest.bot}/training_examples/greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    training_examples = training_examples.json()
    response = client.put(
        f"/api/bot/{pytest.bot}/training_examples/greet/"
        + training_examples["data"][0]["_id"],
        json={"data": "hey, there"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Training Example updated!"


def test_get_responses():
    response = client.get(
        f"/api/bot/{pytest.bot}/response/utter_greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert len(actual["data"]) == 1
    assert actual["success"]
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])


def test_get_all_responses():
    response = client.get(
        f"/api/bot/{pytest.bot}/response/all",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert len(actual["data"]) == 14
    assert actual["data"][0]["name"]
    assert actual["data"][0]["texts"][0]["text"]
    assert not actual["data"][0]["customs"]
    assert actual["success"]
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])


def test_add_response_already_exists():
    response = client.post(
        f"/api/bot/{pytest.bot}/utterance",
        json={"data": "utter_greet"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Utterance exists"


def test_add_utterance_name():
    response = client.post(
        f"/api/bot/{pytest.bot}/utterance",
        json={"data": "utter_test_add_name"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Utterance added!"


def test_add_utterance_name_empty():
    response = client.post(
        f"/api/bot/{pytest.bot}/utterance",
        json={"data": " "},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_get_utterances():
    response = client.get(
        f"/api/bot/{pytest.bot}/utterance",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]["utterances"]) == 15
    assert type(actual["data"]["utterances"]) == list


def test_add_response():
    response = client.post(
        f"/api/bot/{pytest.bot}/response/utter_greet",
        json={"data": "Wow! How are you?"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Response added!"
    response = client.get(
        f"/api/bot/{pytest.bot}/response/utter_greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert len(actual["data"]) == 2


def test_add_custom_response():
    response = client.post(
        f"/api/bot/{pytest.bot}/response/json/utter_custom",
        json={"data": {"question": "Wow! How are you?"}},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Response added!"
    response = client.get(
        f"/api/bot/{pytest.bot}/utterance",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert len(actual["data"]) == 1


def test_get_custom_responses():
    response = client.get(
        f"/api/bot/{pytest.bot}/response/utter_custom",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert len(actual["data"]) == 1
    assert actual["success"]
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])


def test_add_response_upper_case():
    response = client.post(
        f"/api/bot/{pytest.bot}/response/Utter_Greet",
        json={"data": "Upper Greet Response"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Response added!"


def test_get_response_upper_case():
    response = client.get(
        f"/api/bot/{pytest.bot}/response/Utter_Greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert len(actual["data"]) == 3

    response_lower = client.get(
        f"/api/bot/{pytest.bot}/response/utter_greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual_lower = response_lower.json()
    assert len(actual_lower["data"]) == 3
    assert actual_lower["data"] == actual["data"]


def test_add_response_duplicate():
    response = client.post(
        f"/api/bot/{pytest.bot}/response/utter_greet",
        json={"data": "Wow! How are you?"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Utterance already exists!"


def test_add_custom_response_duplicate():
    response = client.post(
        f"/api/bot/{pytest.bot}/response/json/utter_custom",
        json={"data": {"question": "Wow! How are you?"}},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Utterance already exists!"


def test_add_empty_response():
    response = client.post(
        f"/api/bot/{pytest.bot}/response/utter_greet",
        json={"data": ""},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Utterance text cannot be empty or blank spaces"


def test_add_custom_empty_response():
    response = client.post(
        f"/api/bot/{pytest.bot}/response/json/utter_custom",
        json={"data": ""},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Utterance must be dict type and must not be empty"


def test_remove_response():
    response = client.get(
        f"/api/bot/{pytest.bot}/response/utter_greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    utterances = response.json()
    assert len(utterances["data"]) == 3
    id = utterances["data"][0]["_id"]
    response = client.delete(
        f"/api/bot/{pytest.bot}/response/{id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Response removed!"
    training_examples = client.get(
        f"/api/bot/{pytest.bot}/response/utter_greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    training_examples = training_examples.json()
    assert len(training_examples["data"]) == 2


def test_remove_utterance_attached_to_story():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_remove_utterance_attached_to_story",
            "type": "STORY",
            "template_type": "Q&A",
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
    assert actual["message"] == "Flow added successfully"
    response = client.delete(
        f"/api/bot/{pytest.bot}/responses/utter_greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert (
            actual["message"]
            == 'Cannot remove action "utter_greet" linked to flow "greet again"'
    )


def test_remove_utterance():
    client.post(
        f"/api/bot/{pytest.bot}/response/utter_remove_utterance",
        json={"data": "this will be removed"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    response = client.delete(
        f"/api/bot/{pytest.bot}/responses/utter_remove_utterance",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Utterance removed!"


def test_remove_utterance_non_existing():
    response = client.delete(
        f"/api/bot/{pytest.bot}/responses/utter_delete_non_existing",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Utterance does not exists"


def test_remove_utterance_empty():
    response = client.delete(
        f"/api/bot/{pytest.bot}/responses/ ",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Utterance cannot be empty or spaces"


def test_remove_response_empty_id():
    response = client.delete(
        f"/api/bot/{pytest.bot}/response/ ",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Response Id cannot be empty or spaces"


def test_edit_response():
    training_examples = client.get(
        f"/api/bot/{pytest.bot}/response/utter_greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    training_examples = training_examples.json()
    response = client.put(
        f"/api/bot/{pytest.bot}/response/utter_greet/"
        + training_examples["data"][0]["_id"],
        json={"data": "Hello, How are you!"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Utterance updated!"


def test_edit_custom_response():
    training_examples = client.get(
        f"/api/bot/{pytest.bot}/response/utter_custom",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    training_examples = training_examples.json()
    response = client.put(
        f"/api/bot/{pytest.bot}/response/json/utter_custom/"
        + training_examples["data"][0]["_id"],
        json={"data": {"question": "How are you?"}},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Utterance updated!"

    training_examples = client.get(
        f"/api/bot/{pytest.bot}/response/utter_custom",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    training_examples = training_examples.json()
    assert training_examples["data"][0]["_id"]
    assert training_examples["data"][0]["value"] == {
        "custom": {"question": "How are you?"}
    }
    assert training_examples["data"][0]["type"] == "json"


def test_remove_custom_utterance():
    response = client.post(
        f"/api/bot/{pytest.bot}/response/json/utter_custom",
        json={"data": {"question": "are you ok?"}},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"]["_id"]
    id = actual["data"]["_id"]
    response = client.delete(
        f"/api/bot/{pytest.bot}/response/{id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Response removed!"

    response = client.delete(
        f"/api/bot/{pytest.bot}/responses/utter_custom",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Utterance removed!"


def test_add_story():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_path",
            "type": "STORY",
            "template_type": "Q&A",
            "steps": [
                {"name": "test_greet", "type": "INTENT"},
                {"name": "utter_test_greet", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Flow added successfully"
    assert actual["data"]["_id"]
    pytest.story_id = actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0


def test_add_story_with_name_already_exists():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "greet",
            "type": "STORY",
            "template_type": "Q&A",
            "steps": [
                {"name": "test_greet", "type": "INTENT"},
                {"name": "utter_test_greet", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["message"] == "Story with the name already exists"
    assert actual["data"] is None
    assert actual["error_code"] == 422


def test_add_story_invalid_type():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_path",
            "type": "TEST",
            "template_type": "Q&A",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_greet", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "type"],
            "msg": "value is not a valid enumeration member; permitted: 'STORY', 'RULE', 'MULTIFLOW'",
            "type": "type_error.enum",
            "ctx": {"enum_values": ["STORY", "RULE", "MULTIFLOW"]},
        }
    ]


def test_add_story_empty_event():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={"name": "test_add_story_empty_event", "type": "STORY", "steps": []},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "steps"],
            "msg": "Steps are required to form Flow",
            "type": "value_error",
        }
    ]

def test_add_story_lone_intent():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_add_story_lone_intent",
            "type": "STORY",
            "template_type": "Q&A",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_greet", "type": "BOT"},
                {"name": "greet_again", "type": "INTENT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "steps"],
            "msg": "Intent should be followed by utterance or action",
            "type": "value_error",
        }
    ]

def test_add_story_consecutive_intents():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_add_story_consecutive_intents",
            "type": "STORY",
            "template_type": "Q&A",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_greet", "type": "INTENT"},
                {"name": "utter_greet", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "steps"],
            "msg": "Found 2 consecutive intents",
            "type": "value_error",
        }
    ]


def test_add_story_multiple_actions():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_add_story_consecutive_actions",
            "type": "STORY",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_greet", "type": "HTTP_ACTION"},
                {"name": "utter_greet_again", "type": "HTTP_ACTION"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Flow added successfully"


def test_add_story_utterance_as_first_step():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_add_story_consecutive_intents",
            "type": "STORY",
            "template_type": "Q&A",
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
    assert actual["message"] == [
        {
            "loc": ["body", "steps"],
            "msg": "First step should be an intent",
            "type": "value_error",
        }
    ]


def test_add_story_missing_event_type():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_path",
            "type": "STORY",
            "template_type": "Q&A",
            "steps": [{"name": "greet"}, {"name": "utter_greet", "type": "BOT"}],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "steps", 0, "type"],
            "msg": "field required",
            "type": "value_error.missing",
        }
    ]


def test_add_story_invalid_event_type():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_path",
            "type": "STORY",
            "template_type": "Q&A",
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
    assert actual["message"] == [
        {
            "ctx": {
                "enum_values": [
                    "INTENT",
                    "SLOT",
                    "FORM_START",
                    "FORM_END",
                    "BOT",
                    "HTTP_ACTION",
                    "ACTION",
                    "SLOT_SET_ACTION",
                    "FORM_ACTION",
                    "GOOGLE_SEARCH_ACTION",
                    "EMAIL_ACTION",
                    "JIRA_ACTION",
                    "ZENDESK_ACTION",
                    "PIPEDRIVE_LEADS_ACTION",
                    "HUBSPOT_FORMS_ACTION",
                    "RAZORPAY_ACTION",
                    "TWO_STAGE_FALLBACK_ACTION",
                    "PYSCRIPT_ACTION",
                    "PROMPT_ACTION",
                    "DATABASE_ACTION",
                    "WEB_SEARCH_ACTION",
                    "LIVE_AGENT_ACTION",
                    "STOP_FLOW_ACTION"
                ]
            },
            "loc": ["body", "steps", 0, "type"],
            "msg": "value is not a valid enumeration member; permitted: 'INTENT', 'SLOT', 'FORM_START', 'FORM_END', 'BOT', 'HTTP_ACTION', 'ACTION', 'SLOT_SET_ACTION', 'FORM_ACTION', 'GOOGLE_SEARCH_ACTION', 'EMAIL_ACTION', 'JIRA_ACTION', 'ZENDESK_ACTION', 'PIPEDRIVE_LEADS_ACTION', 'HUBSPOT_FORMS_ACTION', 'RAZORPAY_ACTION', 'TWO_STAGE_FALLBACK_ACTION', 'PYSCRIPT_ACTION', 'PROMPT_ACTION', 'DATABASE_ACTION', 'WEB_SEARCH_ACTION', 'LIVE_AGENT_ACTION', 'STOP_FLOW_ACTION'",
            "type": "type_error.enum",
        }
    ]


def test_add_multiflow_story():
    response = client.post(
        f"/api/bot/{pytest.bot}/v2/stories",
        json={
            "name": "test_path",
            "steps": [
                {
                    "step": {
                        "name": "greet",
                        "type": "INTENT",
                        "node_id": "1",
                        "component_id": "Mnvehd",
                    },
                    "connections": [
                        {
                            "name": "utter_greet",
                            "type": "BOT",
                            "node_id": "2",
                            "component_id": "PLhfhs",
                        }
                    ],
                },
                {
                    "step": {
                        "name": "utter_greet",
                        "type": "BOT",
                        "node_id": "2",
                        "component_id": "PLhfhs",
                    },
                    "connections": [
                        {
                            "name": "more_queries",
                            "type": "INTENT",
                            "node_id": "3",
                            "component_id": "MNbcg",
                        },
                        {
                            "name": "goodbye",
                            "type": "INTENT",
                            "node_id": "4",
                            "component_id": "QQAA",
                        },
                    ],
                },
                {
                    "step": {
                        "name": "goodbye",
                        "type": "INTENT",
                        "node_id": "4",
                        "component_id": "QQAA",
                    },
                    "connections": [
                        {
                            "name": "utter_goodbye",
                            "type": "BOT",
                            "node_id": "5",
                            "component_id": "NNXX",
                        }
                    ],
                },
                {
                    "step": {
                        "name": "utter_goodbye",
                        "type": "BOT",
                        "node_id": "5",
                        "component_id": "NNXX",
                    },
                    "connections": None,
                },
                {
                    "step": {
                        "name": "utter_more_queries",
                        "type": "BOT",
                        "node_id": "6",
                        "component_id": "MnveRRhd",
                    },
                    "connections": None,
                },
                {
                    "step": {
                        "name": "more_queries",
                        "type": "INTENT",
                        "node_id": "3",
                        "component_id": "MNbcg",
                    },
                    "connections": [
                        {
                            "name": "utter_more_queries",
                            "type": "BOT",
                            "node_id": "6",
                            "component_id": "MnveRRhd",
                        }
                    ],
                },
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["message"] == "Story flow added successfully"
    assert actual["data"]["_id"]
    pytest.multiflow_story_id = actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0


def test_add_multiflow_story_with_slot_values():
    response = client.post(
        f"/api/bot/{pytest.bot}/v2/stories",
        json={
            "name": "test_path_with_slot",
            "steps": [
                {
                    "step": {
                        "name": "greet",
                        "type": "INTENT",
                        "node_id": "1",
                        "component_id": "Mnvehd",
                    },
                    "connections": [
                        {
                            "name": "utter_greet",
                            "type": "BOT",
                            "node_id": "2",
                            "component_id": "PLhfhs",
                        }
                    ],
                },
                {
                    "step": {
                        "name": "utter_greet",
                        "type": "BOT",
                        "node_id": "2",
                        "component_id": "PLhfhs",
                    },
                    "connections": [
                        {
                            "name": "more_queries",
                            "type": "SLOT",
                            "value": "Yes",
                            "node_id": "3",
                            "component_id": "MNbcg",
                        },
                        {
                            "name": "goodbye",
                            "type": "INTENT",
                            "node_id": "4",
                            "component_id": "QQAA",
                        },
                    ],
                },
                {
                    "step": {
                        "name": "goodbye",
                        "type": "INTENT",
                        "node_id": "4",
                        "component_id": "QQAA",
                    },
                    "connections": [
                        {
                            "name": "utter_goodbye",
                            "type": "BOT",
                            "node_id": "5",
                            "component_id": "NNXX",
                        }
                    ],
                },
                {
                    "step": {
                        "name": "utter_goodbye",
                        "type": "BOT",
                        "node_id": "5",
                        "component_id": "NNXX",
                    },
                    "connections": None,
                },
                {
                    "step": {
                        "name": "utter_more_queries",
                        "type": "BOT",
                        "node_id": "6",
                        "component_id": "MnveRRhd",
                    },
                    "connections": None,
                },
                {
                    "step": {
                        "name": "more_queries",
                        "type": "SLOT",
                        "value": "Yes",
                        "node_id": "3",
                        "component_id": "MNbcg",
                    },
                    "connections": [
                        {
                            "name": "utter_more_queries",
                            "type": "BOT",
                            "node_id": "6",
                            "component_id": "MnveRRhd",
                        }
                    ],
                },
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["message"] == "Story flow added successfully"
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0


def test_add_multiflow_story_with_path():
    response = client.post(
        f"/api/bot/{pytest.bot}/v2/stories",
        json={
            "name": "test_multiflow_with_path_type",
            "steps": [
                {
                    "step": {
                        "name": "hobby",
                        "type": "INTENT",
                        "node_id": "1",
                        "component_id": "Mnvehd",
                    },
                    "connections": [
                        {
                            "name": "utter_hobby",
                            "type": "BOT",
                            "node_id": "2",
                            "component_id": "PLhfhs",
                        }
                    ],
                },
                {
                    "step": {
                        "name": "utter_hobby",
                        "type": "BOT",
                        "node_id": "2",
                        "component_id": "PLhfhs",
                    },
                    "connections": [
                        {
                            "name": "frontend",
                            "type": "SLOT",
                            "value": "Yes",
                            "node_id": "3",
                            "component_id": "MNbcg",
                        },
                        {
                            "name": "backend",
                            "type": "HTTP_ACTION",
                            "node_id": "4",
                            "component_id": "QQAA",
                        },
                    ],
                },
                {
                    "step": {
                        "name": "backend",
                        "type": "HTTP_ACTION",
                        "node_id": "4",
                        "component_id": "QQAA",
                    },
                    "connections": [
                        {
                            "name": "utter_backend",
                            "type": "BOT",
                            "node_id": "5",
                            "component_id": "NNXX",
                        }
                    ],
                },
                {
                    "step": {
                        "name": "utter_backend",
                        "type": "BOT",
                        "node_id": "5",
                        "component_id": "NNXX",
                    },
                    "connections": None,
                },
                {
                    "step": {
                        "name": "utter_frontend",
                        "type": "BOT",
                        "node_id": "6",
                        "component_id": "MnveRRhd",
                    },
                    "connections": None,
                },
                {
                    "step": {
                        "name": "frontend",
                        "type": "SLOT",
                        "value": "Yes",
                        "node_id": "3",
                        "component_id": "MNbcg",
                    },
                    "connections": [
                        {
                            "name": "utter_frontend",
                            "type": "BOT",
                            "node_id": "6",
                            "component_id": "MnveRRhd",
                        }
                    ],
                },
            ],
            "metadata": [
                {"node_id": "5", "flow_type": "RULE"},
                {"node_id": "6", "flow_type": "STORY"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["message"] == "Story flow added successfully"
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0


def test_add_multiflow_story_with_name_already_exists():
    response = client.post(
        f"/api/bot/{pytest.bot}/v2/stories",
        json={
            "name": "test_path",
            "steps": [
                {
                    "step": {
                        "name": "greet",
                        "type": "INTENT",
                        "node_id": "1",
                        "component_id": "MNbcg",
                    },
                    "connections": [
                        {
                            "name": "utter_greet",
                            "type": "BOT",
                            "node_id": "2",
                            "component_id": "MNbcg",
                        }
                    ],
                },
                {
                    "step": {
                        "name": "utter_greet",
                        "type": "BOT",
                        "node_id": "2",
                        "component_id": "MNbcg",
                    },
                    "connections": [
                        {
                            "name": "more_queries",
                            "type": "INTENT",
                            "node_id": "3",
                            "component_id": "MNbcg",
                        },
                        {
                            "name": "goodbye",
                            "type": "INTENT",
                            "node_id": "4",
                            "component_id": "MNbcg",
                        },
                    ],
                },
                {
                    "step": {
                        "name": "goodbye",
                        "type": "INTENT",
                        "node_id": "4",
                        "component_id": "MNbcg",
                    },
                    "connections": [
                        {
                            "name": "utter_goodbye",
                            "type": "BOT",
                            "node_id": "5",
                            "component_id": "MNbcg",
                        }
                    ],
                },
                {
                    "step": {
                        "name": "utter_goodbye",
                        "type": "BOT",
                        "node_id": "5",
                        "component_id": "MNbcg",
                    },
                    "connections": None,
                },
                {
                    "step": {
                        "name": "utter_more_queries",
                        "type": "BOT",
                        "node_id": "6",
                        "component_id": "MNbcg",
                    },
                    "connections": None,
                },
                {
                    "step": {
                        "name": "more_queries",
                        "type": "INTENT",
                        "node_id": "3",
                        "component_id": "MNbcg",
                    },
                    "connections": [
                        {
                            "name": "utter_more_queries",
                            "type": "BOT",
                            "node_id": "6",
                            "component_id": "MNbcg",
                        }
                    ],
                },
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["message"] == "Multiflow Story with the name already exists"
    assert actual["data"] is None
    assert actual["error_code"] == 422


def test_add_multiflow_story_no_steps():
    response = client.post(
        f"/api/bot/{pytest.bot}/v2/stories",
        json={"name": "test_path", "steps": []},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["message"] == [
        {
            "loc": ["body", "steps"],
            "msg": "Steps are required to form Flow",
            "type": "value_error",
        }
    ]
    assert actual["data"] is None
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_add_multiflow_story_lone_intent():
    response = client.post(
        f"/api/bot/{pytest.bot}/v2/stories",
        json={
            "name": "test_add_multiflow_story_lone_intent",
            "steps": [
                {
                    "step": {
                        "name": "greet",
                        "type": "INTENT",
                        "node_id": "1",
                        "component_id": "MNbcg",
                    },
                    "connections": [
                        {
                            "name": "utter_greet",
                            "type": "BOT",
                            "node_id": "2",
                            "component_id": "MNbcg",
                        }
                    ],
                },
                {
                    "step": {
                        "name": "utter_greet",
                        "type": "BOT",
                        "node_id": "2",
                        "component_id": "MNbcg",
                    },
                    "connections": [
                        {
                            "name": "queries",
                            "type": "INTENT",
                            "node_id": "3",
                            "component_id": "MNbcg",
                        },
                        {
                            "name": "goodbye",
                            "type": "INTENT",
                            "node_id": "4",
                            "component_id": "MNbcg",
                        },
                    ],
                },
                {
                    "step": {
                        "name": "goodbye",
                        "type": "INTENT",
                        "node_id": "4",
                        "component_id": "MNbcg",
                    },
                    "connections": None,
                },
                {
                    "step": {
                        "name": "queries",
                        "type": "INTENT",
                        "node_id": "3",
                        "component_id": "MNbcg",
                    },
                    "connections": None,
                },
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422

    assert actual["message"] == "Leaf nodes cannot be intent"


def test_add_multiflow_story_missing_event_type():
    response = client.post(
        f"/api/bot/{pytest.bot}/v2/stories",
        json={
            "name": "test_path",
            "steps": [
                {
                    "step": {"name": "hi", "node_id": "1", "component_id": "MNbcg"},
                    "connections": [
                        {
                            "name": "utter_hi",
                            "type": "BOT",
                            "node_id": "2",
                            "component_id": "MNbcg",
                        }
                    ],
                },
                {
                    "step": {
                        "name": "utter_greet",
                        "type": "BOT",
                        "node_id": "3",
                        "component_id": "MNbcg",
                    },
                    "connections": [
                        {
                            "name": "queries",
                            "type": "INTENT",
                            "node_id": "4",
                            "component_id": "MNbcg",
                        },
                        {
                            "name": "goodbye",
                            "type": "INTENT",
                            "node_id": "5",
                            "component_id": "MNbcg",
                        },
                    ],
                },
                {
                    "step": {
                        "name": "goodbye",
                        "type": "INTENT",
                        "node_id": "5",
                        "component_id": "MNbcg",
                    },
                    "connections": None,
                },
                {
                    "step": {
                        "name": "queries",
                        "type": "INTENT",
                        "node_id": "4",
                        "component_id": "MNbcg",
                    },
                    "connections": None,
                },
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]

    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "steps", 0, "step", "type"],
            "msg": "field required",
            "type": "value_error.missing",
        }
    ]


def test_add_multiflow_story_invalid_event_type():
    response = client.post(
        f"/api/bot/{pytest.bot}/v2/stories",
        json={
            "name": "test_path",
            "steps": [
                {
                    "step": {
                        "name": "hi",
                        "type": "data",
                        "node_id": "1",
                        "component_id": "MNbcg",
                    },
                    "connections": [
                        {
                            "name": "utter_hi",
                            "type": "BOT",
                            "node_id": "2",
                            "component_id": "MNbcg",
                        }
                    ],
                },
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422

    assert actual["message"] == [
        {
            "loc": ["body", "steps", 0, "step", "type"],
            "msg": "value is not a valid enumeration member; permitted: 'INTENT', 'SLOT', 'FORM_START', 'FORM_END', "
                   "'BOT', 'HTTP_ACTION', 'ACTION', 'SLOT_SET_ACTION', 'FORM_ACTION', 'GOOGLE_SEARCH_ACTION', "
                   "'EMAIL_ACTION', 'JIRA_ACTION', 'ZENDESK_ACTION', 'PIPEDRIVE_LEADS_ACTION', "
                   "'HUBSPOT_FORMS_ACTION', 'RAZORPAY_ACTION', 'TWO_STAGE_FALLBACK_ACTION', 'PYSCRIPT_ACTION', "
                   "'PROMPT_ACTION', 'DATABASE_ACTION', 'WEB_SEARCH_ACTION', 'LIVE_AGENT_ACTION', 'STOP_FLOW_ACTION'",
            "type": "type_error.enum",
            "ctx": {
                "enum_values": [
                    "INTENT",
                    "SLOT",
                    "FORM_START",
                    "FORM_END",
                    "BOT",
                    "HTTP_ACTION",
                    "ACTION",
                    "SLOT_SET_ACTION",
                    "FORM_ACTION",
                    "GOOGLE_SEARCH_ACTION",
                    "EMAIL_ACTION",
                    "JIRA_ACTION",
                    "ZENDESK_ACTION",
                    "PIPEDRIVE_LEADS_ACTION",
                    "HUBSPOT_FORMS_ACTION",
                    "RAZORPAY_ACTION",
                    "TWO_STAGE_FALLBACK_ACTION",
                    "PYSCRIPT_ACTION",
                    "PROMPT_ACTION",
                    "DATABASE_ACTION",
                    "WEB_SEARCH_ACTION",
                    "LIVE_AGENT_ACTION",
                    "STOP_FLOW_ACTION",
                ]
            },
        }
    ]


def test_update_story():
    response = client.put(
        f"/api/bot/{pytest.bot}/stories/{pytest.story_id}",
        json={
            "name": "test_path",
            "type": "STORY",
            "template_type": "Q&A",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_nonsense", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Flow updated successfully"
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0


def test_update_story_with_name_already_exists():
    response = client.put(
        f"/api/bot/{pytest.bot}/stories/{pytest.story_id}",
        json={
            "name": "test_add_story_consecutive_actions",
            "type": "STORY",
            "template_type": "Q&A",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_nonsense", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Story with the name already exists"
    assert actual["data"] is None
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_update_story_invalid_event_type():
    response = client.put(
        f"/api/bot/{pytest.bot}/stories/{pytest.story_id}",
        json={
            "name": "test_path",
            "type": "STORY",
            "template_type": "Q&A",
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
    assert actual["message"] == [
        {
            "ctx": {
                "enum_values": [
                    "INTENT",
                    "SLOT",
                    "FORM_START",
                    "FORM_END",
                    "BOT",
                    "HTTP_ACTION",
                    "ACTION",
                    "SLOT_SET_ACTION",
                    "FORM_ACTION",
                    "GOOGLE_SEARCH_ACTION",
                    "EMAIL_ACTION",
                    "JIRA_ACTION",
                    "ZENDESK_ACTION",
                    "PIPEDRIVE_LEADS_ACTION",
                    "HUBSPOT_FORMS_ACTION",
                    "RAZORPAY_ACTION",
                    "TWO_STAGE_FALLBACK_ACTION",
                    "PYSCRIPT_ACTION",
                    "PROMPT_ACTION",
                    "DATABASE_ACTION",
                    "WEB_SEARCH_ACTION",
                    "LIVE_AGENT_ACTION",
                    "STOP_FLOW_ACTION",
                ]
            },
            "loc": ["body", "steps", 0, "type"],
            "msg": "value is not a valid enumeration member; permitted: 'INTENT', 'SLOT', 'FORM_START', 'FORM_END', 'BOT', 'HTTP_ACTION', 'ACTION', 'SLOT_SET_ACTION', 'FORM_ACTION', 'GOOGLE_SEARCH_ACTION', 'EMAIL_ACTION', 'JIRA_ACTION', 'ZENDESK_ACTION', 'PIPEDRIVE_LEADS_ACTION', 'HUBSPOT_FORMS_ACTION', 'RAZORPAY_ACTION', 'TWO_STAGE_FALLBACK_ACTION', 'PYSCRIPT_ACTION', 'PROMPT_ACTION', 'DATABASE_ACTION', 'WEB_SEARCH_ACTION', 'LIVE_AGENT_ACTION', 'STOP_FLOW_ACTION'",
            "type": "type_error.enum",
        }
    ]


def test_update_multiflow_story():
    response = client.put(
        f"/api/bot/{pytest.bot}/v2/stories/{pytest.multiflow_story_id}",
        json={
            "name": "test_path",
            "steps": [
                {
                    "step": {
                        "name": "greeting",
                        "type": "INTENT",
                        "node_id": "1",
                        "component_id": "MNbcg",
                    },
                    "connections": [
                        {
                            "name": "utter_greeting",
                            "type": "BOT",
                            "node_id": "2",
                            "component_id": "MNbcZZg",
                        }
                    ],
                },
                {
                    "step": {
                        "name": "utter_greeting",
                        "type": "BOT",
                        "node_id": "2",
                        "component_id": "MNbcZZg",
                    },
                    "connections": [
                        {
                            "name": "more_query",
                            "type": "INTENT",
                            "node_id": "3",
                            "component_id": "uhsjJ",
                        },
                        {
                            "name": "goodbye",
                            "type": "INTENT",
                            "node_id": "4",
                            "component_id": "MgGFD",
                        },
                    ],
                },
                {
                    "step": {
                        "name": "goodbye",
                        "type": "INTENT",
                        "node_id": "4",
                        "component_id": "MgGFD",
                    },
                    "connections": [
                        {
                            "name": "utter_goodbye",
                            "type": "BOT",
                            "node_id": "5",
                            "component_id": "MNbcg",
                        }
                    ],
                },
                {
                    "step": {
                        "name": "utter_goodbye",
                        "type": "BOT",
                        "node_id": "5",
                        "component_id": "MNbcg",
                    },
                    "connections": None,
                },
                {
                    "step": {
                        "name": "utter_more_query",
                        "type": "BOT",
                        "node_id": "6",
                        "component_id": "IIUUUYY",
                    },
                    "connections": None,
                },
                {
                    "step": {
                        "name": "more_query",
                        "type": "INTENT",
                        "node_id": "3",
                        "component_id": "uhsjJ",
                    },
                    "connections": [
                        {
                            "name": "utter_more_query",
                            "type": "BOT",
                            "node_id": "6",
                            "component_id": "IIUUUYY",
                        }
                    ],
                },
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["message"] == "Story flow updated successfully"
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0


def test_update_multiflow_story_with_name_already_exists():
    response = client.post(
        f"/api/bot/{pytest.bot}/v2/stories",
        json={
            "name": "another_test_path",
            "steps": [
                {
                    "step": {
                        "name": "greet",
                        "type": "INTENT",
                        "node_id": "1",
                        "component_id": "63g0SIHe0vlF7BpABhUBlcOW",
                    },
                    "connections": [
                        {
                            "name": "utter_greet",
                            "type": "BOT",
                            "node_id": "2",
                            "component_id": "637k8PnBABFMoKiUJqQTCBRP",
                        }
                    ],
                },
                {
                    "step": {
                        "name": "utter_greet",
                        "type": "BOT",
                        "node_id": "2",
                        "component_id": "637k8PnBABFMoKiUJqQTCBRP",
                    },
                    "connections": [
                        {
                            "name": "more_queries",
                            "type": "INTENT",
                            "node_id": "3",
                            "component_id": "63NUrDSW34K8XzuabEwO7SJH",
                        },
                        {
                            "name": "goodbye",
                            "type": "INTENT",
                            "node_id": "4",
                            "component_id": "63zr5t71RcH6WZCP5kNGpZYv",
                        },
                    ],
                },
                {
                    "step": {
                        "name": "goodbye",
                        "type": "INTENT",
                        "node_id": "4",
                        "component_id": "63zr5t71RcH6WZCP5kNGpZYv",
                    },
                    "connections": [
                        {
                            "name": "utter_goodbye",
                            "type": "BOT",
                            "node_id": "5",
                            "component_id": "630r3YIqp2UhggEsIvC8Q8pC",
                        }
                    ],
                },
                {
                    "step": {
                        "name": "utter_goodbye",
                        "type": "BOT",
                        "node_id": "5",
                        "component_id": "630r3YIqp2UhggEsIvC8Q8pC",
                    },
                    "connections": None,
                },
                {
                    "step": {
                        "name": "utter_more_queries",
                        "type": "BOT",
                        "node_id": "6",
                        "component_id": "63vwObDTOE2KLCP1FejFbSm8",
                    },
                    "connections": None,
                },
                {
                    "step": {
                        "name": "more_queries",
                        "type": "INTENT",
                        "node_id": "3",
                        "component_id": "63NUrDSW34K8XzuabEwO7SJH",
                    },
                    "connections": [
                        {
                            "name": "utter_more_queries",
                            "type": "BOT",
                            "node_id": "6",
                            "component_id": "63vwObDTOE2KLCP1FejFbSm8",
                        }
                    ],
                },
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Story flow added successfully"
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0

    response = client.put(
        f"/api/bot/{pytest.bot}/v2/stories/{pytest.multiflow_story_id}",
        json={
            "name": "another_test_path",
            "steps": [
                {
                    "step": {
                        "name": "greeting",
                        "type": "INTENT",
                        "node_id": "1",
                        "component_id": "NNNNHHG",
                    },
                    "connections": [
                        {
                            "name": "utter_greeting",
                            "type": "BOT",
                            "node_id": "2",
                            "component_id": "NNNNHHG",
                        }
                    ],
                },
                {
                    "step": {
                        "name": "utter_greeting",
                        "type": "BOT",
                        "node_id": "2",
                        "component_id": "NNNNHHG",
                    },
                    "connections": [
                        {
                            "name": "more_query",
                            "type": "INTENT",
                            "node_id": "3",
                            "component_id": "NNNNHHG",
                        },
                        {
                            "name": "goodbye",
                            "type": "INTENT",
                            "node_id": "4",
                            "component_id": "NNNNHHG",
                        },
                    ],
                },
                {
                    "step": {
                        "name": "goodbye",
                        "type": "INTENT",
                        "node_id": "4",
                        "component_id": "NNNNHHG",
                    },
                    "connections": [
                        {
                            "name": "utter_goodbye",
                            "type": "BOT",
                            "node_id": "5",
                            "component_id": "NNNNHHG",
                        }
                    ],
                },
                {
                    "step": {
                        "name": "utter_goodbye",
                        "type": "BOT",
                        "node_id": "5",
                        "component_id": "NNNNHHG",
                    },
                    "connections": None,
                },
                {
                    "step": {
                        "name": "utter_more_query",
                        "type": "BOT",
                        "node_id": "6",
                        "component_id": "NNNNHHG",
                    },
                    "connections": None,
                },
                {
                    "step": {
                        "name": "more_query",
                        "type": "INTENT",
                        "node_id": "3",
                        "component_id": "NNNNHHG",
                    },
                    "connections": [
                        {
                            "name": "utter_more_query",
                            "type": "BOT",
                            "node_id": "6",
                            "component_id": "NNNNHHG",
                        }
                    ],
                },
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["message"] == "Multiflow Story with the name already exists"
    assert actual["data"] is None
    assert actual["error_code"] == 422


def test_update_multiflow_story_invalid_event_type():
    response = client.put(
        f"/api/bot/{pytest.bot}/v2/stories/{pytest.multiflow_story_id}",
        json={
            "name": "test_path",
            "steps": [
                {
                    "step": {
                        "name": "hiie",
                        "type": "data",
                        "node_id": "1",
                        "component_id": "63Xx6ZbMOcBcq5Ltb1XoC3R5",
                    },
                    "connections": [
                        {
                            "name": "utter_hiie",
                            "type": "BOT",
                            "node_id": "2",
                            "component_id": "63nzrQFKnrc97QOI2renluu9",
                        }
                    ],
                },
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422

    assert actual["message"] == [
        {
            "loc": ["body", "steps", 0, "step", "type"],
            "msg": "value is not a valid enumeration member; permitted: 'INTENT', 'SLOT', 'FORM_START', "
                   "'FORM_END', 'BOT', 'HTTP_ACTION', 'ACTION', 'SLOT_SET_ACTION', 'FORM_ACTION', "
                   "'GOOGLE_SEARCH_ACTION', 'EMAIL_ACTION', 'JIRA_ACTION', 'ZENDESK_ACTION', "
                   "'PIPEDRIVE_LEADS_ACTION', 'HUBSPOT_FORMS_ACTION', 'RAZORPAY_ACTION', "
                   "'TWO_STAGE_FALLBACK_ACTION', 'PYSCRIPT_ACTION', 'PROMPT_ACTION', 'DATABASE_ACTION', "
                   "'WEB_SEARCH_ACTION', 'LIVE_AGENT_ACTION', 'STOP_FLOW_ACTION'",
            "type": "type_error.enum",
            "ctx": {
                "enum_values": [
                    "INTENT",
                    "SLOT",
                    "FORM_START",
                    "FORM_END",
                    "BOT",
                    "HTTP_ACTION",
                    "ACTION",
                    "SLOT_SET_ACTION",
                    "FORM_ACTION",
                    "GOOGLE_SEARCH_ACTION",
                    "EMAIL_ACTION",
                    "JIRA_ACTION",
                    "ZENDESK_ACTION",
                    "PIPEDRIVE_LEADS_ACTION",
                    "HUBSPOT_FORMS_ACTION",
                    "RAZORPAY_ACTION",
                    "TWO_STAGE_FALLBACK_ACTION",
                    "PYSCRIPT_ACTION",
                    "PROMPT_ACTION",
                    "DATABASE_ACTION",
                    "WEB_SEARCH_ACTION",
                    "LIVE_AGENT_ACTION",
                    "STOP_FLOW_ACTION"
                ]
            },
        }
    ]


def test_get_multiflow_stories():
    response = client.get(
        f"/api/bot/{pytest.bot}/stories",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    #
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]
    assert Utility.check_empty_string(actual["message"])
    get_story = [
        x
        for x in actual["data"]
        if x["type"] == "MULTIFLOW" and x["name"] == "test_path"
    ]
    assert len(get_story) == 1
    get_story = get_story[0]
    assert get_story["type"] == "MULTIFLOW"
    assert get_story["name"] == "test_path"
    assert get_story["steps"] == [
        {
            "step": {
                "name": "greeting",
                "type": "INTENT",
                "node_id": "1",
                "component_id": "MNbcg",
            },
            "connections": [
                {
                    "name": "utter_greeting",
                    "type": "BOT",
                    "node_id": "2",
                    "component_id": "MNbcZZg",
                }
            ],
        },
        {
            "step": {
                "name": "utter_greeting",
                "type": "BOT",
                "node_id": "2",
                "component_id": "MNbcZZg",
            },
            "connections": [
                {
                    "name": "more_query",
                    "type": "INTENT",
                    "node_id": "3",
                    "component_id": "uhsjJ",
                },
                {
                    "name": "goodbye",
                    "type": "INTENT",
                    "node_id": "4",
                    "component_id": "MgGFD",
                },
            ],
        },
        {
            "step": {
                "name": "goodbye",
                "type": "INTENT",
                "node_id": "4",
                "component_id": "MgGFD",
            },
            "connections": [
                {
                    "name": "utter_goodbye",
                    "type": "BOT",
                    "node_id": "5",
                    "component_id": "MNbcg",
                }
            ],
        },
        {
            "step": {
                "name": "utter_goodbye",
                "type": "BOT",
                "node_id": "5",
                "component_id": "MNbcg",
            },
            "connections": [],
        },
        {
            "step": {
                "name": "utter_more_query",
                "type": "BOT",
                "node_id": "6",
                "component_id": "IIUUUYY",
            },
            "connections": [],
        },
        {
            "step": {
                "name": "more_query",
                "type": "INTENT",
                "node_id": "3",
                "component_id": "uhsjJ",
            },
            "connections": [
                {
                    "name": "utter_more_query",
                    "type": "BOT",
                    "node_id": "6",
                    "component_id": "IIUUUYY",
                }
            ],
        },
    ]


def test_delete_multiflow_story():
    response = client.delete(
        f"/api/bot/{pytest.bot}/stories/{pytest.multiflow_story_id}/MULTIFLOW",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Flow deleted successfully"


def test_delete_multiflow_non_existing_story():
    response = client.delete(
        f"/api/bot/{pytest.bot}/stories/{pytest.multiflow_story_id}/MULTIFLOW",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Flow does not exists"


def test_delete_story():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_path1",
            "type": "STORY",
            "template_type": "Q&A",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_greet_delete", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Flow added successfully"
    assert actual["success"]
    assert actual["error_code"] == 0
    pytest.story_id = actual["data"]["_id"]

    response = client.delete(
        f"/api/bot/{pytest.bot}/stories/{pytest.story_id}/STORY",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Flow deleted successfully"


def test_delete_non_existing_story():
    response = client.delete(
        f"/api/bot/{pytest.bot}/stories/{pytest.story_id}/STORY",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Flow does not exists"


def test_get_stories():
    response = client.get(
        f"/api/bot/{pytest.bot}/stories",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]
    assert Utility.check_empty_string(actual["message"])
    assert actual["data"][0]["template_type"] == "CUSTOM"
    assert actual["data"][1]["template_type"] == "CUSTOM"
    assert actual["data"][16]["template_type"] == "Q&A"
    assert actual["data"][17]["template_type"] == "Q&A"
    assert actual["data"][19].get("template_type")


def test_get_utterance_from_intent():
    response = client.get(
        f"/api/bot/{pytest.bot}/utterance_from_intent/greet",
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
        f"/api/bot/{pytest.bot}/utterance_from_intent/greeting",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["name"] is None
    assert actual["data"]["type"] is None
    assert Utility.check_empty_string(actual["message"])


def test_add_story_stop_flow_action():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_add_story_stop_flow_action",
            "type": "STORY",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_goodbye", "type": "BOT"},
                {"name": "utter_goodbye", "type": "BOT"},
                {"name": "stop", "type": "STOP_FLOW_ACTION"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Flow added successfully"
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0

    response = client.get(
        f"/api/bot/{pytest.bot}/stories",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    story = next((item for item in actual['data'] if item['name'] == 'test_add_story_stop_flow_action'), None)
    assert story is not None
    assert story['steps'][-1]['name'] == 'stop_flow_action'
    assert story['steps'][-1]['type'] == 'STOP_FLOW_ACTION'


def test_add_story_stop_flow_action_not_at_end():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_add_story_stop_flow_action_not_at_end",
            "type": "STORY",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_goodbye", "type": "BOT"},
                {"name": "stop", "type": "STOP_FLOW_ACTION"},
                {"name": "utter_goodbye", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "steps"],
            "msg": "Stop Flow Action should only be at the end of the flow",
            "type": "value_error",
        }
    ]


def test_add_story_stop_flow_action_after_intent():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_add_story_stop_flow_action_after_intent",
            "type": "STORY",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "stop", "type": "STOP_FLOW_ACTION"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "steps"],
            "msg": "Stop Flow Action should not be after intent",
            "type": "value_error",
        }
    ]

@responses.activate
def test_upload_stop_flow_action():
    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.data_importer}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )

    files = (
        (
            "training_files",
            ("nlu.yml", open("tests/testing_data/stop_flow_action/upload_story/data/nlu.yml", "rb")),
        ),
        (
            "training_files",
            ("domain.yml", open("tests/testing_data/stop_flow_action/upload_story/domain.yml", "rb")),
        ),
        (
            "training_files",
            ("stories.yml", open("tests/testing_data/stop_flow_action/upload_story/data/stories.yml", "rb")),
        ),
        (
            "training_files",
            ("config.yml", open("tests/testing_data/stop_flow_action/upload_story/config.yml", "rb")),
        ),
        (
            "training_files",
            (
                "chat_client_config.yml",
                open("tests/testing_data/stop_flow_action/upload_story/chat_client_config.yml", "rb"),
            ),
        ),
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/upload?import_data=true&overwrite=true",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=files,
    )
    actual = response.json()
    assert actual["message"] == "Upload in progress! Check logs."
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]
    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.data_importer
    )

    response = client.get(
        f"/api/bot/{pytest.bot}/stories",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    story = next((story_item for story_item in actual["data"] if story_item["name"] == "story_with_stop_flow_action"), None)

    assert story is not None
    assert story["steps"][-1]["name"] == "stop_flow_action"
    assert story["steps"][-1]["type"] == "STOP_FLOW_ACTION"


def test_download_story_with_stop_flow_action():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_download_story_with_stop_flow_action",
            "type": "STORY",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_goodbye", "type": "BOT"},
                {"name": "stop_flow_action", "type": "STOP_FLOW_ACTION"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Flow added successfully"
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0

    response = client.get(
        f"/api/bot/{pytest.bot}/download/data",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    file_bytes = BytesIO(response.content)

    zip_file = ZipFile(file_bytes, mode="r")
    with zip_file.open("data/stories.yml") as file:
        stories_yaml = yaml.safe_load(file.read().decode("utf-8"))
    with zip_file.open("domain.yml") as file:
        domain_yaml = yaml.safe_load(file.read().decode("utf-8"))

    story = next((story_item for story_item in stories_yaml["stories"] if story_item["story"] == "test_download_story_with_stop_flow_action"), None)
    assert story is not None
    assert story["steps"][-1]["action"] == "action_listen"
    assert domain_yaml["actions"][-1] == "action_listen"


@responses.activate
def test_add_multiflow_story_stop_flow_action():
    response = client.post(
        f"/api/bot/{pytest.bot}/v2/stories",
        json={
            "name": "test_add_multiflow_story_stop_flow_action",
            "steps": [
                {
                    "step": {
                        "name": "greet",
                        "type": "INTENT",
                        "node_id": "1",
                        "component_id": "Mnvehd",
                    },
                    "connections": [
                        {
                            "name": "utter_greet",
                            "type": "BOT",
                            "node_id": "2",
                            "component_id": "PLhfhs",
                        }
                    ],
                },
                {
                    "step": {
                        "name": "utter_greet",
                        "type": "BOT",
                        "node_id": "2",
                        "component_id": "PLhfhs",
                    },
                    "connections": [
                        {
                            "name": "stop_flow",
                            "type": "STOP_FLOW_ACTION",
                            "node_id": "3",
                            "component_id": "NNXX",
                        },
                        {
                            "name": "utter_bye",
                            "type": "BOT",
                            "node_id": "4",
                            "component_id": "NNXXY",
                        },
                    ],
                },
                {
                    "step": {
                        "name": "stop_flow",
                        "type": "STOP_FLOW_ACTION",
                        "node_id": "3",
                        "component_id": "NNXX",
                    },
                    "connections": None,
                },
                {
                    "step": {
                        "name": "utter_bye",
                        "type": "BOT",
                        "node_id": "4",
                        "component_id": "NNXXY",
                    },
                    "connections": [
                        {
                            "name": "utter_bye",
                            "type": "BOT",
                            "node_id": "5",
                            "component_id": "NNXXY",
                        }
                    ],
                },
                {
                    "step": {
                        "name": "utter_bye",
                        "type": "BOT",
                        "node_id": "5",
                        "component_id": "NNXXY",
                    },
                    "connections": None,
                }
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Story flow added successfully"
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0

    response = client.get(
        f"/api/bot/{pytest.bot}/stories",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    story = next((item for item in actual['data'] if item['name'] == 'test_add_multiflow_story_stop_flow_action'), None)
    assert story is not None

    stop_flow_step = next((step for step in story['steps'] if
                           step['step']['name'] == 'stop_flow' and step['step']['type'] == 'STOP_FLOW_ACTION'), None)

    assert stop_flow_step is not None
    assert stop_flow_step['connections'] == []


def test_add_multiflow_story_stop_flow_action_not_at_end():
    response = client.post(
        f"/api/bot/{pytest.bot}/v2/stories",
        json={
            "name": "test_stop_path",
            "steps": [
                {
                    "step": {
                        "name": "greet",
                        "type": "INTENT",
                        "node_id": "1",
                        "component_id": "Mnvehd",
                    },
                    "connections": [
                        {
                            "name": "utter_greet",
                            "type": "BOT",
                            "node_id": "2",
                            "component_id": "PLhfhs",
                        }
                    ],
                },
                {
                    "step": {
                        "name": "utter_greet",
                        "type": "BOT",
                        "node_id": "2",
                        "component_id": "PLhfhs",
                    },
                    "connections": [
                        {
                            "name": "more_queries",
                            "type": "INTENT",
                            "node_id": "3",
                            "component_id": "MNbcg",
                        },
                        {
                            "name": "stop_flow",
                            "type": "STOP_FLOW_ACTION",
                            "node_id": "4",
                            "component_id": "QQAA",
                        },
                    ],
                },
                {
                    "step": {
                        "name": "stop_flow",
                        "type": "STOP_FLOW_ACTION",
                        "node_id": "4",
                        "component_id": "QQAA",
                    },
                    "connections": [
                        {
                            "name": "utter_goodbye",
                            "type": "BOT",
                            "node_id": "5",
                            "component_id": "NNXX",
                        }
                    ],
                },
                {
                    "step": {
                        "name": "utter_goodbye",
                        "type": "BOT",
                        "node_id": "5",
                        "component_id": "NNXX",
                    },
                    "connections": None,
                },
                {
                    "step": {
                        "name": "utter_more_queries",
                        "type": "BOT",
                        "node_id": "6",
                        "component_id": "MnveRRhd",
                    },
                    "connections": None,
                },
                {
                    "step": {
                        "name": "more_queries",
                        "type": "INTENT",
                        "node_id": "3",
                        "component_id": "MNbcg",
                    },
                    "connections": [
                        {
                            "name": "utter_more_queries",
                            "type": "BOT",
                            "node_id": "6",
                            "component_id": "MnveRRhd",
                        }
                    ],
                },
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual['success']
    assert actual['message'] == 'STOP_FLOW_ACTION should be a leaf node!'
    assert actual["error_code"] == 422


def test_add_multiflow_story_stop_flow_action_after_intent():
    response = client.post(
        f"/api/bot/{pytest.bot}/v2/stories",
        json={
            "name": "test_stop_path",
            "steps": [
                {
                    "step": {
                        "name": "greet",
                        "type": "INTENT",
                        "node_id": "1",
                        "component_id": "Mnvehd",
                    },
                    "connections": [
                        {
                            "name": "stop_flow",
                            "type": "STOP_FLOW_ACTION",
                            "node_id": "2",
                            "component_id": "PLhfhs",
                        }
                    ],
                },
                {
                    "step": {
                        "name": "stop_flow",
                        "type": "STOP_FLOW_ACTION",
                        "node_id": "2",
                        "component_id": "PLhfhs",
                    },
                    "connections": None,
                },
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual['success']
    assert actual['message'] == 'STOP_FLOW_ACTION cannot be a successor of an intent!'
    assert actual["error_code"] == 422

@responses.activate
@patch.object(ModelProcessor, "is_daily_training_limit_exceeded")
def test_upload_stop_flow_action_multiflow(mock_training_limit):
    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.data_importer}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )

    files = (
        (
            "training_files",
            ("nlu.yml", open("tests/testing_data/stop_flow_action/upload_multiflow_story/data/nlu.yml", "rb")),
        ),
        (
            "training_files",
            ("rules.yml", open("tests/testing_data/stop_flow_action/upload_multiflow_story/data/rules.yml", "rb")),
        ),
        (
            "training_files",
            ("domain.yml", open("tests/testing_data/stop_flow_action/upload_multiflow_story/domain.yml", "rb")),
        ),
        (
            "training_files",
            ("stories.yml", open("tests/testing_data/stop_flow_action/upload_multiflow_story/data/stories.yml", "rb")),
        ),
        (
            "training_files",
            ("config.yml", open("tests/testing_data/stop_flow_action/upload_multiflow_story/config.yml", "rb")),
        ),
        (
            "training_files",
            (
                "chat_client_config.yml",
                open("tests/testing_data/stop_flow_action/upload_multiflow_story/chat_client_config.yml", "rb"),
            ),
        ),
        (
            "training_files",
            (
                "actions.yml",
                open("tests/testing_data/stop_flow_action/upload_multiflow_story/actions.yml", "rb"),
            ),
        ),
        (
            "training_files",
            (
                "multiflow_stories.yml",
                open("tests/testing_data/stop_flow_action/upload_multiflow_story/multiflow_stories.yml", "rb"),
            ),
        ),
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/upload?import_data=true&overwrite=true",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=files,
    )
    actual = response.json()
    assert actual["message"] == "Upload in progress! Check logs."
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]
    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.data_importer
    )

    response = client.get(
        f"/api/bot/{pytest.bot}/stories",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    for story in actual["data"]:
        if story.get("type") == "MULTIFLOW":
            for substep in story["steps"]:
                if substep.get("step", {}).get("name") == "stop_flow_action":
                    assert substep["connections"] == []


    mock_training_limit.return_value = False
    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.model_training}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )

    response = client.post(
        f"/api/bot/{pytest.bot}/train",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "Model training started."
    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.model_training
    )


def test_download_multiflow_story_with_stop_flow_action():
    response = client.post(
        f"/api/bot/{pytest.bot}/v2/stories",
        json={
            "name": "test_download_multiflow_story_with_stop_flow_action",
            "steps": [
                {
                    "step": {
                        "name": "greet",
                        "type": "INTENT",
                        "node_id": "1",
                        "component_id": "Mnvehd",
                    },
                    "connections": [
                        {
                            "name": "utter_greet",
                            "type": "BOT",
                            "node_id": "2",
                            "component_id": "PLhfhs",
                        }
                    ],
                },
                {
                    "step": {
                        "name": "utter_greet",
                        "type": "BOT",
                        "node_id": "2",
                        "component_id": "PLhfhs",
                    },
                    "connections": [
                        {
                            "name": "stop_flow_action",
                            "type": "STOP_FLOW_ACTION",
                            "node_id": "3",
                            "component_id": "NNXX",
                        },
                        {
                            "name": "utter_bye",
                            "type": "BOT",
                            "node_id": "4",
                            "component_id": "NNXXY",
                        },
                    ],
                },
                {
                    "step": {
                        "name": "stop_flow_action",
                        "type": "STOP_FLOW_ACTION",
                        "node_id": "3",
                        "component_id": "NNXX",
                    },
                    "connections": None,
                },
                {
                    "step": {
                        "name": "utter_bye",
                        "type": "BOT",
                        "node_id": "4",
                        "component_id": "NNXXY",
                    },
                    "connections": None,
                },
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Story flow added successfully"
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0

    response = client.get(
        f"/api/bot/{pytest.bot}/download/data",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    file_bytes = BytesIO(response.content)
    zip_file = ZipFile(file_bytes, mode="r")

    with zip_file.open("multiflow_stories.yml") as file:
        multi_stories_content = yaml.safe_load(file.read().decode("utf-8"))
    with zip_file.open("domain.yml") as file:
        domain_content = yaml.safe_load(file.read().decode("utf-8"))

    events = next(block['events'] for block in multi_stories_content['multiflow_story'] if block['block_name'] == 'test_download_multiflow_story_with_stop_flow_action')

    for event in events:
        if event["step"]["name"] == "stop_flow_action":
            assert event["connections"] == []

    for event in events:
        if event["step"]["name"] == "utter_greet":
            assert any(conn["name"] == "stop_flow_action" for conn in event["connections"])

    assert domain_content['actions'][-1] == 'stop_flow_action'



@responses.activate
def test_train_on_updated_data(monkeypatch):
    def _mock_training_limit(*arge, **kwargs):
        return False

    monkeypatch.setattr(
        ModelProcessor, "is_daily_training_limit_exceeded", _mock_training_limit
    )

    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.model_training}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )

    response = client.post(
        f"/api/bot/{pytest.bot}/slots",
        json={
            "name": "frontend",
            "type": "text",
            "influence_conversation": True,
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert "data" in actual
    assert actual["message"] == "Slot added successfully!"
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0

    response = client.post(
        f"/api/bot/{pytest.bot}/slots",
        json={
            "name": "more_queries",
            "type": "text",
            "influence_conversation": True,
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    response = client.post(
        f"/api/bot/{pytest.bot}/train",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "Model training started."
    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.model_training
    )


def test_download_model_training_logs(monkeypatch):
    start_date = datetime.utcnow() - timedelta(days=1)
    end_date = datetime.utcnow() + timedelta(days=1)
    response = client.get(
        f"/api/bot/{pytest.bot}/logs/download/model_training?start_date={start_date}&end_date={end_date}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    assert response.content


@pytest.fixture
def mock_is_training_inprogress_exception(monkeypatch):
    def _inprogress_execption_response(*args, **kwargs):
        raise AppException("Previous model training in progress.")

    monkeypatch.setattr(
        ModelProcessor, "is_training_inprogress", _inprogress_execption_response
    )


def test_train_inprogress(mock_is_training_inprogress_exception):
    response = client.post(
        f"/api/bot/{pytest.bot}/train",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"] is False
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"] == "Previous model training in progress."


@pytest.fixture
def mock_is_training_inprogress(monkeypatch):
    def _inprogress_response(*args, **kwargs):
        return False

    monkeypatch.setattr(ModelProcessor, "is_training_inprogress", _inprogress_response)


def test_train_daily_limit_exceed(mock_is_training_inprogress, monkeypatch):
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.training_limit_per_day = 2
    bot_settings.save()
    response = client.post(
        f"/api/bot/{pytest.bot}/train",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"] == "Daily model training limit exceeded."


def test_get_model_training_history():
    response = client.get(
        f"/api/bot/{pytest.bot}/train/history",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"] is True
    assert actual["error_code"] == 0
    assert actual["data"]
    assert "training_history" in actual["data"]


def test_model_testing_limit_exceeded(monkeypatch):
    monkeypatch.setitem(Utility.environment["model"]["test"], "limit_per_day", 0)
    response = client.post(
        url=f"/api/bot/{pytest.bot}/test",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == "Daily limit exceeded."
    assert not actual["success"]


@responses.activate
def test_model_testing_event(monkeypatch):
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.test_limit_per_day = 5
    bot_settings.save()
    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.model_testing}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )
    response = client.post(
        url=f"/api/bot/{pytest.bot}/test",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"] == "Testing in progress! Check logs."
    assert actual["success"]


@responses.activate
def test_model_testing_in_progress():
    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.model_testing}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )

    response = client.post(
        url=f"/api/bot/{pytest.bot}/test",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == "Event already in progress! Check logs."
    assert not actual["success"]
    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.model_testing
    )


def test_get_model_testing_logs():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/logs/test?start_idx=0&page_size=10",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]
    assert actual["success"]

    response = client.get(
        url=f"/api/bot/{pytest.bot}/logs/test?log_type=stories&reference_id={actual['data']['logs'][0]['reference_id']}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["success"]


def test_download_model_testing_logs(monkeypatch):
    start_date = datetime.utcnow() - timedelta(days=1)
    end_date = datetime.utcnow() + timedelta(days=1)
    response = client.get(
        f"/api/bot/{pytest.bot}/logs/download/model_testing?start_date={start_date}&end_date={end_date}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    assert response.content


def test_get_file_training_history():
    response = client.get(
        f"/api/bot/{pytest.bot}/data/generation/history",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"] is True
    assert actual["error_code"] == 0
    assert actual["data"]
    assert "training_history" in actual["data"]


def test_deploy_missing_configuration():
    response = client.post(
        f"/api/bot/{pytest.bot}/deploy",
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
        f"/api/bot/{pytest.bot}/deploy",
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
        f"/api/bot/{pytest.bot}/deploy",
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
        f"/api/bot/{pytest.bot}/deploy/history",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]["deployment_history"]) == 3
    assert actual["message"] is None


@responses.activate
def test_deploy_with_token(mock_endpoint_with_token):
    responses.add(
        responses.PUT,
        "http://localhost:5000/model",
        json="Model was successfully replaced.",
        headers={
            "Content-type": "application/json",
            "Accept": "text/plain",
            "Authorization": "Bearer AGTSUDH!@#78JNKLD",
        },
        status=200,
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/deploy",
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
        f"/api/bot/{pytest.bot}/deploy",
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
        f"/api/bot/{pytest.bot}/deploy",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "An unexpected error occurred."


def test_integration_token():
    response = client.post(
        f"/api/auth/{pytest.bot}/integration/token",
        json={"name": "integration 1", "expiry_minutes": 1440, "role": "designer"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    token = response.json()
    assert token["success"]
    assert token["error_code"] == 0
    assert token["data"]["access_token"]
    assert token["data"]["token_type"]
    assert (
            token["message"]
            == """This token will be shown only once. Please copy this somewhere safe. 
            It is your responsibility to keep the token secret. If leaked, others may have access to your system."""
    )

    response = client.get(
        "/api/user/details",
        headers={
            "Authorization": token["data"]["token_type"]
                             + " "
                             + token["data"]["access_token"],
            "X-USER": "integration",
        },
    ).json()
    assert len(response["data"]["user"]["bots"]["account_owned"]) == 1
    assert len(response["data"]["user"]["bots"]["shared"]) == 0

    response = client.get(
        "/api/account/bot",
        headers={
            "Authorization": token["data"]["token_type"]
                             + " "
                             + token["data"]["access_token"],
            "X-USER": "integration",
        },
    ).json()
    assert len(response["data"]["account_owned"]) == 1
    assert len(response["data"]["shared"]) == 0

    response = client.get(
        "/api/user/details",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    assert len(response["data"]["user"]["bots"]["account_owned"]) == 2

    response = client.get(
        f"/api/bot/{pytest.bot}/intents",
        headers={
            "Authorization": token["data"]["token_type"]
                             + " "
                             + token["data"]["access_token"],
            "X-USER": "integration",
        },
    )
    actual = response.json()
    assert "data" in actual
    assert len(actual["data"]) == 8
    assert actual["success"]
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])
    response = client.post(
        f"/api/bot/{pytest.bot}/intents",
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
    response = client.post(
        f"/api/auth/{pytest.bot}/integration/token",
        json={"name": "integration 2"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["access_token"]
    assert actual["data"]["token_type"]
    assert (
            actual["message"]
            == """This token will be shown only once. Please copy this somewhere safe. 
            It is your responsibility to keep the token secret. If leaked, others may have access to your system."""
    )
    response = client.get(
        f"/api/bot/{pytest.bot}/intents",
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


@responses.activate
def test_augment_paraphrase_gpt():
    responses.add(
        responses.POST,
        url="http://localhost:8000/paraphrases/gpt",
        match=[
            responses.matchers.json_params_matcher(
                {
                    "api_key": "MockKey",
                    "data": ["Where is digite located?"],
                    "engine": "davinci",
                    "temperature": 0.75,
                    "max_tokens": 100,
                    "num_responses": 10,
                }
            )
        ],
        json={
            "success": True,
            "data": {
                "paraphrases": ["Where is digite located?", "Where is digite situated?"]
            },
            "message": None,
            "error_code": 0,
        },
        status=200,
    )
    response = client.post(
        "/api/augment/paraphrases/gpt",
        json={"data": ["Where is digite located?"], "api_key": "MockKey"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()

    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] == {
        "paraphrases": ["Where is digite located?", "Where is digite situated?"]
    }
    assert Utility.check_empty_string(actual["message"])


def test_augment_paraphrase_gpt_validation():
    response = client.post(
        "/api/augment/paraphrases/gpt",
        json={"data": [], "api_key": "MockKey"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"] == [
        {"loc": ["body", "data"], "msg": "Question Please!", "type": "value_error"}
    ]

    response = client.post(
        "/api/augment/paraphrases/gpt",
        json={
            "data": ["hi", "hello", "thanks", "hello", "bye", "how are you"],
            "api_key": "MockKey",
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"] == [
        {
            "loc": ["body", "data"],
            "msg": "Max 5 Questions are allowed!",
            "type": "value_error",
        }
    ]


@responses.activate
def test_augment_paraphrase_gpt_fail():
    key_error_message = "Incorrect API key provided: InvalidKey. You can find your API key at https://beta.openai.com."
    responses.add(
        responses.POST,
        url="http://localhost:8000/paraphrases/gpt",
        match=[
            responses.matchers.json_params_matcher(
                {
                    "api_key": "InvalidKey",
                    "data": ["Where is digite located?"],
                    "engine": "davinci",
                    "temperature": 0.75,
                    "max_tokens": 100,
                    "num_responses": 10,
                }
            )
        ],
        json={
            "success": False,
            "data": None,
            "message": key_error_message,
        },
        status=200,
    )
    response = client.post(
        "/api/augment/paraphrases/gpt",
        json={"data": ["Where is digite located?"], "api_key": "InvalidKey"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()

    assert not actual["success"]
    assert actual["data"] is None
    assert actual["message"] == key_error_message


@responses.activate
def test_augment_paraphrase():
    responses.add(
        responses.POST,
        "http://localhost:8000/paraphrases",
        json={
            "success": True,
            "data": {
                "questions": [
                    "Where is digite located?",
                    "Where is digite?",
                    "What is the location of digite?",
                    "Where is the digite located?",
                    "Where is it located?",
                    "What location is digite located?",
                    "Where is the digite?",
                    "where is digite located?",
                    "Where is digite situated?",
                    "digite is located where?",
                ]
            },
            "message": None,
            "error_code": 0,
        },
        status=200,
        match=[responses.matchers.json_params_matcher(["where is digite located?"])],
    )
    response = client.post(
        "/api/augment/paraphrases",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"data": ["where is digite located?"]},
    )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]
    assert Utility.check_empty_string(actual["message"])


def test_augment_paraphrase_no_of_questions():
    response = client.post(
        "/api/augment/paraphrases",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"data": []},
    )

    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"] == [
        {"loc": ["body", "data"], "msg": "Question Please!", "type": "value_error"}
    ]

    response = client.post(
        "/api/augment/paraphrases",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"data": ["Hi", "Hello", "How are you", "Bye", "Thanks", "Welcome"]},
    )

    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"] == [
        {
            "loc": ["body", "data"],
            "msg": "Max 5 Questions are allowed!",
            "type": "value_error",
        }
    ]


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


def test_update_user_details():
    response = client.post(
        "/api/user/details",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Details updated!"


def test_download_data():
    response = client.get(
        f"/api/bot/{pytest.bot}/download/data",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    file_bytes = BytesIO(response.content)
    zip_file = ZipFile(file_bytes, mode="r")
    assert zip_file.filelist.__len__() == 10
    zip_file.close()
    file_bytes.close()


def test_download_model():
    response = client.get(
        f"/api/bot/{pytest.bot}/download/model",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    d = response.headers["content-disposition"]
    fname = re.findall("filename=(.+)", d)[0]
    file_bytes = BytesIO(response.content)
    tar = tarfile.open(fileobj=file_bytes, mode="r", name=fname)
    assert tar.members.__len__()
    tar.close()
    file_bytes.close()


def test_get_endpoint():
    response = client.get(
        f"/api/bot/{pytest.bot}/endpoint",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["data"]
    assert actual["error_code"] == 0
    assert actual["message"] is None
    assert actual["success"]


def test_save_endpoint_error():
    response = client.put(
        f"/api/bot/{pytest.bot}/endpoint",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {"loc": ["body"], "msg": "field required", "type": "value_error.missing"}
    ]
    assert not actual["success"]


def test_save_empty_endpoint():
    response = client.put(
        f"/api/bot/{pytest.bot}/endpoint",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={},
    )

    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 0
    assert actual["message"] == "Endpoint saved successfully!"
    assert actual["success"]


def test_save_history_endpoint():
    response = client.put(
        f"/api/bot/{pytest.bot}/endpoint",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={
            "history_endpoint": {
                "url": "http://localhost:27019/",
                "token": "kairon-history-user",
            }
        },
    )

    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 0
    assert actual["message"] == "Endpoint saved successfully!"
    assert actual["success"]


@responses.activate
def test_save_endpoint(monkeypatch):
    monkeypatch.setitem(
        Utility.environment["model"]["agent"], "url", "http://localhost/"
    )

    responses.add(
        responses.GET,
        f"http://localhost/api/bot/{pytest.bot}/reload",
        status=200,
        json={
            "success": True,
            "error_code": 0,
            "data": None,
            "message": "Reloading Model!",
        },
    )

    response = client.put(
        f"/api/bot/{pytest.bot}/endpoint",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={
            "bot_endpoint": {"url": "http://localhost:5005/"},
            "action_endpoint": {"url": "http://localhost:5000/"},
            "history_endpoint": {"url": "http://localhost", "token": "rasa234568"},
        },
    )

    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 0
    assert actual["message"] == "Endpoint saved successfully!"
    assert actual["success"]
    response = client.get(
        f"/api/bot/{pytest.bot}/endpoint",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["data"]["endpoint"].get("bot_endpoint")
    assert actual["data"]["endpoint"].get("action_endpoint")
    assert actual["data"]["endpoint"].get("history_endpoint")


def test_save_empty_history_endpoint():
    response = client.put(
        f"/api/bot/{pytest.bot}/endpoint",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"history_endpoint": {"url": " ", "token": "testing-endpoint"}},
    )

    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 422
    assert actual["message"] == "url cannot be blank or empty spaces"
    assert not actual["success"]


def test_get_history_endpoint():
    response = client.get(
        f"/api/bot/{pytest.bot}/endpoint",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["data"]["endpoint"]["history_endpoint"]["url"] == "http://localhost"
    assert actual["data"]["endpoint"]["history_endpoint"]["token"] == "rasa234***"
    assert actual["error_code"] == 0
    assert actual["message"] is None
    assert actual["success"]


def test_delete_endpoint():
    response = client.delete(
        f"/api/bot/{pytest.bot}/endpoint/history_endpoint",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 0
    assert actual["message"] == "Endpoint removed"
    assert actual["success"]


def test_get_templates():
    response = client.get(
        f"/api/system/templates/use-case",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert "Hi-Hello" in actual["data"]["use-cases"]
    assert actual["error_code"] == 0
    assert actual["message"] is None
    assert actual["success"]


def test_set_templates():
    response = client.post(
        f"/api/bot/{pytest.bot}/templates/use-case",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"data": "Hi-Hello"},
    )

    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 0
    assert actual["message"] == "Data applied!"
    assert actual["success"]


def test_set_templates_invalid():
    response = client.post(
        f"/api/bot/{pytest.bot}/templates/use-case",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"data": "Hi"},
    )

    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 422
    assert actual["message"] == "Invalid template!"
    assert not actual["success"]


def test_set_templates_insecure():
    response = client.post(
        f"/api/bot/{pytest.bot}/templates/use-case",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"data": "../Hi-Hello"},
    )

    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 0
    assert actual["message"] == "Data applied!"
    assert actual["success"]


@responses.activate
def test_reload_model(monkeypatch):
    processor = MongoProcessor()
    start_time = datetime.utcnow() - timedelta(days=1)
    end_time = datetime.utcnow() + timedelta(days=1)

    monkeypatch.setitem(
        Utility.environment["model"]["agent"], "url", "http://localhost/"
    )

    responses.add(
        responses.GET,
        f"http://localhost/api/bot/{pytest.bot}/reload",
        status=200,
        json={
            "success": True,
            "error_code": 0,
            "data": None,
            "message": "Reloading Model!",
        },
    )

    response = client.get(
        f"/api/bot/{pytest.bot}/model/reload",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 0
    assert actual["message"] == "Reloading Model!"
    assert actual["success"]
    logs = processor.get_logs(pytest.bot, "audit_logs", start_time, end_time)
    logs[0].pop('timestamp')
    logs[0].pop('_id')
    assert logs[0] == {'attributes': [{'key': 'bot', 'value': pytest.bot}], 'user': 'integration@demo.ai',
                       'action': 'activity', 'entity': 'model_reload',
                       'data': {'message': None, 'username': 'integration@demo.ai', 'exception': None,
                                'status': 'Initiated'}}


@responses.activate
def test_reload_model_exception():
    processor = MongoProcessor()
    start_time = datetime.utcnow() - timedelta(days=1)
    end_time = datetime.utcnow() + timedelta(days=1)
    # def mongo_store(*arge, **kwargs):
    #     return None
    #
    # monkeypatch.setattr(Utility, "get_local_mongo_store", mongo_store)
    # monkeypatch.setitem(Utility.environment['action'], "url", None)
    # monkeypatch.setitem(Utility.environment['model']['agent'], "url", "http://localhost/")
    response = client.get(
        f"/api/bot/{pytest.bot}/model/reload",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert actual['data'] is None
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual['message'] == 'Agent config not found!'
    logs = processor.get_logs(pytest.bot, "audit_logs", start_time, end_time)
    logs[0].pop('timestamp')
    logs[0].pop('_id')
    assert logs[0] == {'attributes': [{'key': 'bot', 'value': pytest.bot}],
                       'user': 'integration@demo.ai', 'action': 'activity', 'entity': 'model_reload',
                       'data': {'message': None, 'username': 'integration@demo.ai',
                                'exception': 'Agent config not found!', 'status': 'Failed'}}


def test_get_config_templates():
    response = client.get(
        f"/api/bot/{pytest.bot}/templates/config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    templates = {template["name"] for template in actual["data"]["config-templates"]}
    assert templates == {
        "long-answer",
        "rasa-default",
        "contextual",
        "kairon-default",
        "gpt-faq",
        "openai-classifier",
        "openai-featurizer",
    }
    assert actual["error_code"] == 0
    assert actual["message"] is None
    assert actual["success"]


def test_set_config_templates():
    response = client.post(
        f"/api/bot/{pytest.bot}/templates/config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"data": "rasa-default"},
    )

    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 0
    assert actual["message"] == "Config applied!"
    assert actual["success"]


def test_set_config_templates_invalid():
    response = client.post(
        f"/api/bot/{pytest.bot}/templates/config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"data": "test"},
    )

    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 422
    assert actual["message"] == "Invalid config!"
    assert not actual["success"]


def test_set_config_templates_insecure():
    response = client.post(
        f"/api/bot/{pytest.bot}/templates/config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"data": "../rasa-default"},
    )

    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 0
    assert actual["message"] == "Config applied!"
    assert actual["success"]


def test_get_config():
    response = client.get(
        f"/api/bot/{pytest.bot}/config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert all(
        key in ["language", "pipeline", "policies", "recipe"]
        for key in actual["data"]["config"].keys()
    )
    assert actual["error_code"] == 0
    assert actual["message"] is None
    assert actual["success"]


def test_set_config():
    response = client.put(
        f"/api/bot/{pytest.bot}/config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=read_config_file("./tests/testing_data/kairon-default.yml"),
    )

    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 0
    assert actual["message"] == "Config saved!"
    assert actual["success"]


def test_set_config_policy_error():
    data = read_config_file("./tests/testing_data/kairon-default.yml")
    data["policies"].append({"name": "TestPolicy"})
    response = client.put(
        f"/api/bot/{pytest.bot}/config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=data,
    )

    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 422
    assert actual["message"] == "Invalid policy TestPolicy"
    assert not actual["success"]


def test_set_config_pipeline_error():
    data = read_config_file("./tests/testing_data/kairon-default.yml")
    data["pipeline"].append({"name": "TestFeaturizer"})
    response = client.put(
        f"/api/bot/{pytest.bot}/config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=data,
    )

    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 422
    assert str(actual["message"]).__contains__("Invalid component TestFeaturizer")
    assert not actual["success"]


def test_set_config_pipeline_error_empty_policies():
    data = read_config_file("./tests/testing_data/kairon-default.yml")
    data["policies"] = []
    response = client.put(
        f"/api/bot/{pytest.bot}/config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=data,
    )

    actual = response.json()
    assert actual["data"] is None
    assert str(actual["message"]).__contains__("You didn't define any policies")
    assert actual["error_code"] == 422
    assert not actual["success"]


def test_delete_intent():
    client.post(
        f"/api/bot/{pytest.bot}/intents",
        json={"data": "happier"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    response = client.delete(
        f"/api/bot/{pytest.bot}/intents/happier",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 0
    assert actual["message"] == "Intent deleted!"
    assert actual["success"]


def test_api_login_with_account_not_verified():
    Utility.email_conf["email"]["enable"] = True
    response = client.post(
        "/api/auth/login",
        data={"username": "integration@demo.ai", "password": "Welcome@10"},
    )
    actual = response.json()
    Utility.email_conf["email"]["enable"] = False

    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"] == "Please verify your mail"
    value = list(
        AuditLogData.objects(user="integration@demo.ai", action='activity', entity='invalid_login').order_by(
            "-timestamp")
    )[0]
    assert value["entity"] == "invalid_login"
    assert value["timestamp"]
    assert value["data"] == {'message': ['Please verify your mail'], 'username': 'integration@demo.ai'}


def test_account_registration_with_confirmation(monkeypatch):
    monkeypatch.setattr(MailUtility, "trigger_smtp", mock_smtp)
    Utility.email_conf["email"]["enable"] = True
    response = client.post(
        "/api/account/registration",
        json={
            "email": "integ1@gmail.com",
            "first_name": "Dem",
            "last_name": "User22",
            "password": "Welcome@10",
            "confirm_password": "Welcome@10",
            "account": "integration33",
            "bot": "integration33",
        },
    )
    actual = response.json()
    assert (
            actual["message"]
            == "Account Registered! A confirmation link has been sent to your mail"
    )
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None

    response = client.post(
        "/api/account/email/confirmation",
        json={
            "data": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJtYWlsX2lkIjoiaW50ZWcxQGdtYWlsLmNvbSJ9.Ycs1ROb1w6MMsx2WTA4vFu3-jRO8LsXKCQEB3fkoU20"
        },
    )
    actual = response.json()
    Utility.email_conf["email"]["enable"] = False

    assert actual["message"] == "Account Verified!"
    assert actual["data"] is None
    assert actual["success"]
    assert actual["error_code"] == 0

    response = client.post(
        "/api/auth/login",
        data={"username": "integ1@gmail.com", "password": "Welcome@10"},
    )
    actual = response.json()
    pytest.add_member_token = actual["data"]["access_token"]
    pytest.add_member_token_type = actual["data"]["token_type"]

    response = client.post(
        "/api/account/bot",
        headers={"Authorization": pytest.add_member_token_type + " " + pytest.add_member_token,
                 'Content-Type': 'application/json'},
        json={"name": "Hi-Hello", "from_template": "Hi-Hello"},
    ).json()
    assert response['message'] == "Bot created"
    assert response['data']['bot_id']

    response = client.get(
        "/api/account/bot",
        headers={
            "Authorization": pytest.add_member_token_type
                             + " "
                             + pytest.add_member_token
        },
    ).json()
    pytest.add_member_bot = response["data"]["account_owned"][0]["_id"]


def test_account_registration_with_confirmation_enabled_sso_only(monkeypatch):
    monkeypatch.setitem(Utility.environment["app"], "enable_sso_only", True)
    response = client.post(
        "/api/account/email/confirmation",
        json={
            "data": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJtYWlsX2lkIjoiaW50ZWcxQGdtYWlsLmNvbSJ9.Ycs1ROb1w6MMsx2WTA4vFu3-jRO8LsXKCQEB3fkoU20"
        },
    )
    actual = response.json()
    Utility.email_conf["email"]["enable"] = False

    assert actual["message"] == "This feature is disabled"
    assert actual["data"] is None
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_invalid_token_for_confirmation():
    response = client.post(
        "/api/account/email/confirmation",
        json={"data": "hello"},
    )
    actual = response.json()

    assert actual["message"] == "Invalid token"
    assert actual["data"] is None
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_add_member(monkeypatch):
    monkeypatch.setattr(MailUtility, "trigger_smtp", mock_smtp)
    monkeypatch.setitem(Utility.email_conf["email"], "enable", True)

    response = client.post(
        f"/api/user/{pytest.add_member_bot}/member",
        json={"email": "integration@demo.ai", "role": "tester"},
        headers={
            "Authorization": pytest.add_member_token_type
                             + " "
                             + pytest.add_member_token
        },
    ).json()
    assert response["message"] == "An invitation has been sent to the user"
    assert response["error_code"] == 0
    assert response["success"]

    response = client.post(
        f"/api/user/{pytest.add_member_bot}/member",
        json={"email": "integration2@demo.ai", "role": "designer"},
        headers={
            "Authorization": pytest.add_member_token_type
                             + " "
                             + pytest.add_member_token
        },
    ).json()
    assert response["message"] == "An invitation has been sent to the user"
    assert response["error_code"] == 0
    assert response["success"]

    response = client.post(
        f"/api/user/{pytest.add_member_bot}/member",
        json={"email": "integrationtest@demo.ai", "role": "designer"},
        headers={
            "Authorization": pytest.add_member_token_type
                             + " "
                             + pytest.add_member_token
        },
    ).json()
    assert response["message"] == "An invitation has been sent to the user"
    assert response["error_code"] == 0
    assert response["success"]


@responses.activate
def test_add_member_invalid_email():
    api_key = "test"
    email = "integration@demo.ai"
    with patch.dict(
            Utility.environment,
            {"verify": {"email": {"type": "quickemail", "key": api_key, "enable": True}}},
    ):
        responses.add(
            responses.GET,
            "http://api.quickemailverification.com/v1/verify?"
            + urlencode({"apikey": api_key, "email": email}),
            json={
                "result": "valid",
                "reason": "rejected_email",
                "disposable": "true",
                "accept_all": "false",
                "role": "false",
                "free": "false",
                "email": email,
                "user": "test",
                "domain": "quickemailverification.com",
                "mx_record": "us2.mx1.mailhostbox.com",
                "mx_domain": "mailhostbox.com",
                "safe_to_send": "false",
                "did_you_mean": "",
                "success": "true",
                "message": None,
            },
        )

        response = client.post(
            f"/api/user/{pytest.add_member_bot}/member",
            json={"email": email, "role": "tester"},
            headers={
                "Authorization": pytest.add_member_token_type
                                 + " "
                                 + pytest.add_member_token
            },
        ).json()
        assert response["message"] == [
            {
                "loc": ["body", "email"],
                "msg": "Invalid or disposable Email!",
                "type": "value_error",
            }
        ]
        assert response["error_code"] == 422
        assert not response["success"]


def test_add_member_as_owner(monkeypatch):
    response = client.post(
        f"/api/user/{pytest.add_member_bot}/member",
        json={"email": "integration@demo.ai", "role": "owner"},
        headers={
            "Authorization": pytest.add_member_token_type
                             + " "
                             + pytest.add_member_token
        },
    ).json()
    assert response["message"] == [
        {
            "loc": ["body", "role"],
            "msg": "There can be only 1 owner per bot",
            "type": "value_error",
        }
    ]
    assert response["error_code"] == 422
    assert not response["success"]


def test_list_bot_invites():
    response = client.post(
        "/api/auth/login",
        data={"username": "integration@demo.ai", "password": "Welcome@10"},
    ).json()

    response = client.get(
        "/api/user/invites/active",
        headers={
            "Authorization": response["data"]["token_type"]
                             + " "
                             + response["data"]["access_token"]
        },
    ).json()
    assert (
            response["data"]["active_invites"][0]["accessor_email"] == "integration@demo.ai"
    )
    assert response["data"]["active_invites"][0]["role"] == "tester"
    assert response["data"]["active_invites"][0]["bot_name"] == "Hi-Hello"
    assert response["error_code"] == 0
    assert response["success"]


def test_login_limit_exceeded():
    response_one = client.post(
        "/api/auth/login",
        data={"username": "integration@demo.ai", "password": "Welcome@3010"},
    ).json()
    response_two = client.post(
        "/api/auth/login",
        data={"username": "integration@demo.ai", "password": "Welcome@3010"},
    ).json()
    response_three = client.post(
        "/api/auth/login",
        data={"username": "integration@demo.ai", "password": "Welcome@3010"},
    ).json()
    response = client.post(
        "/api/auth/login",
        data={"username": "integration@demo.ai", "password": "Welcome@3010"},
    ).json()

    assert not response['success']
    assert response['message'].__contains__("Account frozen due to too many unsuccessful login attempts.")
    assert response['data'] is None
    assert response['error_code'] == 422


def test_search_users(monkeypatch):
    def __mock_list_bot_invites(*args, **kwargs):
        for item in ["integration@demo.ai", "integration2@demo.com"]:
            yield item

    monkeypatch.setattr(AccountProcessor, "search_user", __mock_list_bot_invites)

    response = client.post(
        f"/api/user/search",
        json={"data": "inte"},
        headers={
            "Authorization": pytest.add_member_token_type
                             + " "
                             + pytest.add_member_token
        },
    ).json()
    assert response["data"]["matching_users"] == [
        "integration@demo.ai",
        "integration2@demo.com",
    ]
    assert response["error_code"] == 0
    assert response["success"]


def test_transfer_ownership_to_user_not_a_member(monkeypatch):
    monkeypatch.setitem(Utility.email_conf["email"], "enable", True)
    response = client.put(
        f"/api/user/{pytest.add_member_bot}/owner/change",
        json={"data": "integration@demo.ai"},
        headers={
            "Authorization": pytest.add_member_token_type
                             + " "
                             + pytest.add_member_token
        },
    ).json()
    assert response["message"] == "User is yet to accept the invite"
    assert response["error_code"] == 422
    assert not response["success"]


def test_accept_bot_invite(monkeypatch):
    def __mock_verify_token(*args, **kwargs):
        return {"mail_id": "integration@demo.ai"}

    monkeypatch.setattr(Utility, "verify_token", __mock_verify_token)
    monkeypatch.setattr(MailUtility, "trigger_smtp", mock_smtp)
    monkeypatch.setattr(AccountProcessor, "get_user_details", mock_smtp)
    monkeypatch.setitem(Utility.email_conf["email"], "enable", True)
    response = client.post(
        f"/api/user/{pytest.add_member_bot}/invite/accept",
        json={
            "data": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJtYWlsX2lkIjoidXNlckBrYWlyb24uY"
        },
    ).json()
    assert response["message"] == "Invitation accepted"
    assert response["error_code"] == 0
    assert response["success"]


def test_accept_bot_invite_logged_in_user_with_email_enabled(monkeypatch):
    response = client.post(
        "/api/auth/login",
        data={"username": "integrationtest@demo.ai", "password": "Welcome@10"},
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

    response = client.get(
        "/api/user/invites/active",
        headers={
            "Authorization": actual["data"]["token_type"]
                             + " "
                             + actual["data"]["access_token"]
        },
    ).json()
    assert (
            response["data"]["active_invites"][0]["accessor_email"]
            == "integrationtest@demo.ai"
    )
    assert response["data"]["active_invites"][0]["role"] == "designer"
    assert response["data"]["active_invites"][0]["bot_name"] == "Hi-Hello"

    monkeypatch.setattr(MailUtility, "trigger_smtp", mock_smtp)
    monkeypatch.setattr(AccountProcessor, "check_email_confirmation", mock_smtp)
    Utility.email_conf["email"]["enable"] = True
    response = client.post(
        f"/api/user/{pytest.add_member_bot}/member/invite/accept",
        headers={
            "Authorization": actual["data"]["token_type"]
                             + " "
                             + actual["data"]["access_token"]
        },
    ).json()
    Utility.email_conf["email"]["enable"] = False
    assert response["message"] == "Invitation accepted"
    assert response["error_code"] == 0
    assert response["success"]


def test_accept_bot_invite_logged_in_user():
    response = client.post(
        "/api/auth/login",
        data={"username": "integration2@demo.ai", "password": "Welcome@10"},
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

    response = client.get(
        "/api/user/invites/active",
        headers={
            "Authorization": actual["data"]["token_type"]
                             + " "
                             + actual["data"]["access_token"]
        },
    ).json()
    assert (
            response["data"]["active_invites"][0]["accessor_email"]
            == "integration2@demo.ai"
    )
    assert response["data"]["active_invites"][0]["role"] == "designer"
    assert response["data"]["active_invites"][0]["bot_name"] == "Hi-Hello"

    response = client.post(
        f"/api/user/{pytest.add_member_bot}/member/invite/accept",
        headers={
            "Authorization": actual["data"]["token_type"]
                             + " "
                             + actual["data"]["access_token"]
        },
    ).json()
    assert response["message"] == "Invitation accepted"
    assert response["error_code"] == 0
    assert response["success"]


def test_list_bot_invites_none():
    response = client.get(
        f"/api/user/invites/active",
        headers={
            "Authorization": pytest.add_member_token_type
                             + " "
                             + pytest.add_member_token
        },
    ).json()
    assert response["data"]["active_invites"] == []
    assert response["error_code"] == 0
    assert response["success"]


def test_add_member_email_disabled():
    response = client.post(
        f"/api/user/{pytest.add_member_bot}/member",
        json={"email": "integration_email_false@demo.ai", "role": "designer"},
        headers={
            "Authorization": pytest.add_member_token_type
                             + " "
                             + pytest.add_member_token
        },
    ).json()
    assert response["message"] == "User added"
    assert response["error_code"] == 0
    assert response["success"]


def test_list_members():
    response = client.get(
        f"/api/user/{pytest.add_member_bot}/member",
        headers={
            "Authorization": pytest.add_member_token_type
                             + " "
                             + pytest.add_member_token
        },
    ).json()
    assert response["error_code"] == 0
    assert response["success"]
    assert response["data"][0]["accessor_email"] == "integ1@gmail.com"
    assert response["data"][0]["role"] == "owner"
    assert response["data"][1]["status"]
    assert response["data"][1]["accessor_email"] == "integration@demo.ai"
    assert response["data"][1]["role"] == "tester"
    assert response["data"][1]["status"]
    assert response["data"][2]["accessor_email"] == "integration2@demo.ai"
    assert response["data"][2]["role"] == "designer"
    assert response["data"][2]["status"]
    assert response["data"][3]["accessor_email"] == "integrationtest@demo.ai"
    assert response["data"][3]["role"] == "designer"
    assert response["data"][3]["status"]
    assert response["data"][4]["accessor_email"] == "integration_email_false@demo.ai"
    assert response["data"][4]["role"] == "designer"
    assert response["data"][4]["status"]


def test_transfer_ownership(monkeypatch):
    monkeypatch.setitem(Utility.email_conf["email"], "enable", True)
    monkeypatch.setattr(MailUtility, "trigger_smtp", mock_smtp)
    response = client.put(
        f"/api/user/{pytest.add_member_bot}/owner/change",
        json={"data": "integration@demo.ai"},
        headers={
            "Authorization": pytest.add_member_token_type
                             + " "
                             + pytest.add_member_token
        },
    ).json()
    assert response["message"] == "Ownership transferred"
    assert response["error_code"] == 0
    assert response["success"]

    response = client.get(
        f"/api/user/{pytest.add_member_bot}/member",
        headers={
            "Authorization": pytest.add_member_token_type
                             + " "
                             + pytest.add_member_token
        },
    ).json()
    assert response["error_code"] == 0
    assert response["success"]
    assert response["data"][0]["accessor_email"] == "integ1@gmail.com"
    assert response["data"][0]["role"] == "admin"
    assert response["data"][1]["status"]
    assert response["data"][1]["accessor_email"] == "integration@demo.ai"
    assert response["data"][1]["role"] == "owner"
    assert response["data"][1]["status"]
    assert response["data"][2]["accessor_email"] == "integration2@demo.ai"
    assert response["data"][2]["role"] == "designer"
    assert response["data"][2]["status"]
    assert response["data"][3]["accessor_email"] == "integrationtest@demo.ai"
    assert response["data"][3]["role"] == "designer"
    assert response["data"][3]["status"]
    assert response["data"][4]["accessor_email"] == "integration_email_false@demo.ai"
    assert response["data"][4]["role"] == "designer"
    assert response["data"][4]["status"]


def test_list_members_2():
    response = client.get(
        "/api/account/bot",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    bot = response["data"]["account_owned"][1]["_id"]
    response = client.get(
        f"/api/user/{bot}/member",
        headers={
            "Authorization": pytest.add_member_token_type
                             + " "
                             + pytest.add_member_token
        },
    ).json()
    assert response["error_code"] == 422
    assert not response["success"]
    assert not response["data"]
    assert response["message"] == "Access to bot is denied"


def test_update_member_role_not_exists(monkeypatch):
    response = client.post(
        "/api/account/registration",
        json={
            "email": "user@kairon.ai",
            "first_name": "Demo",
            "last_name": "User",
            "password": "Welcome@10",
            "confirm_password": "Welcome@10",
            "account": "user@kairon.ai",
        },
    )
    actual = response.json()
    assert actual["message"] == "Account Registered!"

    response = client.put(
        f"/api/user/{pytest.add_member_bot}/member",
        json={"email": "user@kairon.ai", "role": "admin", "status": "inactive"},
        headers={
            "Authorization": pytest.add_member_token_type
                             + " "
                             + pytest.add_member_token
        },
    ).json()
    assert response["message"] == "User not yet invited to collaborate"
    assert response["error_code"] == 422
    assert not response["success"]


def test_update_member_role(monkeypatch):
    response = client.put(
        f"/api/user/{pytest.add_member_bot}/member",
        json={
            "email": "integration_email_false@demo.ai",
            "role": "admin",
            "status": "inactive",
        },
        headers={
            "Authorization": pytest.add_member_token_type
                             + " "
                             + pytest.add_member_token
        },
    ).json()
    assert response["message"] == "User does not exist!"
    assert response["error_code"] == 422
    assert not response["success"]

    response = client.post(
        "/api/account/registration",
        json={
            "email": "integration_email_false@demo.ai",
            "first_name": "Demo",
            "last_name": "User",
            "password": "Welcome@10",
            "confirm_password": "Welcome@10",
            "account": "integration_email_false@demo.ai",
        },
    )
    actual = response.json()
    assert actual["message"] == "Account Registered!"

    monkeypatch.setitem(Utility.email_conf["email"], "enable", True)
    monkeypatch.setattr(MailUtility, "trigger_smtp", mock_smtp)
    response = client.put(
        f"/api/user/{pytest.add_member_bot}/member",
        json={
            "email": "integration_email_false@demo.ai",
            "role": "admin",
            "status": "inactive",
        },
        headers={
            "Authorization": pytest.add_member_token_type
                             + " "
                             + pytest.add_member_token
        },
    ).json()
    assert response["message"] == "User access updated"
    assert response["error_code"] == 0
    assert response["success"]


def test_delete_member():
    response = client.delete(
        f"/api/user/{pytest.add_member_bot}/member/integration_email_false@demo.ai",
        headers={
            "Authorization": pytest.add_member_token_type
                             + " "
                             + pytest.add_member_token
        },
    ).json()
    assert response["message"] == "User removed"
    assert response["error_code"] == 0
    assert response["success"]


def test_add_deleted_member_and_updated_role():
    response = client.post(
        f"/api/user/{pytest.add_member_bot}/member",
        json={"email": "integration_email_false@demo.ai", "role": "designer"},
        headers={
            "Authorization": pytest.add_member_token_type
                             + " "
                             + pytest.add_member_token
        },
    ).json()
    assert response["message"] == "User added"
    assert response["error_code"] == 0
    assert response["success"]

    response = client.put(
        f"/api/user/{pytest.add_member_bot}/member",
        json={
            "email": "integration_email_false@demo.ai",
            "role": "admin",
            "status": "inactive",
        },
        headers={
            "Authorization": pytest.add_member_token_type
                             + " "
                             + pytest.add_member_token
        },
    ).json()
    assert response["message"] == "User access updated"
    assert response["error_code"] == 0
    assert response["success"]


def test_remove_self():
    response = client.delete(
        f"/api/user/{pytest.add_member_bot}/member/integ1@gmail.com",
        headers={
            "Authorization": pytest.add_member_token_type
                             + " "
                             + pytest.add_member_token
        },
    ).json()
    assert response["message"] == "User cannot remove himself"
    assert response["error_code"] == 422
    assert not response["success"]


def test_add_intents_no_bot():
    response = client.post(
        "/api/bot/ /intents",
        json={"data": "greet"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Bot is required"


def test_add_intents_not_authorised():
    response = client.post(
        "/api/bot/5ea8127db7c285f4055129a4/intents",
        json={"data": "greet"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Access to bot is denied"


def test_add_intents_inactive_bot(monkeypatch):
    def _mock_bot(*args, **kwargs):
        return {"status": False}

    async def _mock_user(*args, **kwargs):
        return User(
            email="test",
            first_name="test",
            last_name="test",
            account=2,
            status=True,
            is_integration_user=False,
        )

    def _mock_role(*args, **kwargs):
        return {"role": "admin"}

    monkeypatch.setattr(AccountProcessor, "get_bot", _mock_bot)
    monkeypatch.setattr(Authentication, "get_current_user", _mock_user)
    monkeypatch.setattr(AccountProcessor, "fetch_role_for_user", _mock_role)

    response = client.post(
        "/api/bot/5ea8127db7c285f4055129a4/intents",
        json={"data": "greet"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Inactive Bot Please contact system admin!"


def test_add_intents_invalid_auth_token():
    token = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJuYW1lIjoiSm9obiBEb2UiLCJpYXQiOjE1MTYyMzkwMjJ9.hqWGSaFpvbrXkOWc6lrnffhNWR19W_S1YKFBx2arWBk"
    response = client.post(
        "/api/bot/ /intents",
        json={"data": "greet"},
        headers={"Authorization": token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 401
    assert actual["message"] == "Could not validate credentials"


def test_add_intents_invalid_auth_token_2():
    token = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    response = client.post(
        "/api/bot/ /intents",
        json={"data": "greet"},
        headers={"Authorization": token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 401
    assert actual["message"] == "Could not validate credentials"


def test_add_intents_to_different_bot():
    response = client.get(
        "/api/account/bot",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    pytest.bot_2 = response["data"]["account_owned"][1]["_id"]

    response = client.post(
        f"/api/bot/{pytest.bot_2}/intents",
        json={"data": "greeting"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Intent added successfully!"


def test_add_training_examples_to_different_bot():
    response = client.post(
        f"/api/bot/{pytest.bot_2}/training_examples/greet",
        json={"data": ["Heya"]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"][0]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] is None
    response = client.get(
        f"/api/bot/{pytest.bot_2}/training_examples/greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert len(actual["data"]) == 10


def test_add_response_different_bot():
    response = client.post(
        f"/api/bot/{pytest.bot_2}/response/utter_greet",
        json={"data": "Hi! How are you?"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Response added!"
    response = client.get(
        f"/api/bot/{pytest.bot_2}/response/utter_greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert len(actual["data"]) == 3


def test_add_story_to_different_bot():
    response = client.post(
        f"/api/bot/{pytest.bot_2}/stories",
        json={
            "name": "greet user",
            "type": "STORY",
            "template_type": "Q&A",
            "steps": [
                {"name": "greeting", "type": "INTENT"},
                {"name": "utter_greet", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Flow added successfully"
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0


@responses.activate
def test_train_on_different_bot(monkeypatch):
    def _mock_training_limit(*arge, **kwargs):
        return False

    monkeypatch.setattr(
        ModelProcessor, "is_daily_training_limit_exceeded", _mock_training_limit
    )

    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.model_training}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )

    response = client.post(
        f"/api/bot/{pytest.bot_2}/train",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "Model training started."
    complete_end_to_end_event_execution(
        pytest.bot_2, "integration@demo.ai", EventClass.model_training
    )


def test_train_insufficient_data(monkeypatch):
    def _mock_training_limit(*arge, **kwargs):
        return False

    monkeypatch.setattr(
        ModelProcessor, "is_daily_training_limit_exceeded", _mock_training_limit
    )

    response = client.post(
        "/api/account/bot",
        json={"name": "sample-bot"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    response = client.get(
        "/api/account/bot",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    pytest.bot_sample = response["data"]["account_owned"][3]["_id"]

    response_story = client.get(
        f"/api/bot/{pytest.bot_sample}/stories",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response_story.json()
    rule_one = actual["data"][1]["_id"]
    rule_two = actual["data"][2]["_id"]

    response_delete_story_one = client.delete(
        f"/api/bot/{pytest.bot_sample}/stories/{rule_one}/RULE",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    response_delete_story_two = client.delete(
        f"/api/bot/{pytest.bot_sample}/stories/{rule_two}/RULE",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    response = client.post(
        f"/api/bot/{pytest.bot_sample}/train",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert (
            actual["message"]
            == "Please add at least 2 flows and 2 intents before training the bot!"
    )


def test_delete_bot():
    response = client.get(
        "/api/account/bot",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    bot = response["data"]["account_owned"][1]["_id"]

    response = client.delete(
        f"/api/account/bot/{bot}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    assert response["message"] == "Bot removed"
    assert response["error_code"] == 0
    assert response["success"]


def test_login_for_verified():
    Utility.email_conf["email"]["enable"] = True
    response = client.post(
        "/api/auth/login",
        data={"username": "integ1@gmail.com", "password": "Welcome@10"},
    )
    actual = response.json()
    Utility.email_conf["email"]["enable"] = False

    assert actual["success"]
    assert actual["error_code"] == 0
    pytest.access_token = actual["data"]["access_token"]
    pytest.token_type = actual["data"]["token_type"]

def test_list_bots_for_different_user():
    response = client.get(
        "/api/account/bot",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    assert len(response["data"]["shared"]) == 1
    pytest.bot = response["data"]["shared"][0]["_id"]


def test_reset_password_for_valid_id(monkeypatch):
    monkeypatch.setattr(MailUtility, "trigger_smtp", mock_smtp)
    Utility.email_conf["email"]["enable"] = True
    response = client.post(
        "/api/account/password/reset",
        json={"data": "integ1@gmail.com"},
    )
    actual = response.json()
    Utility.email_conf["email"]["enable"] = False
    assert actual["success"]
    assert actual["error_code"] == 0
    assert (
            actual["message"]
            == "Success! A password reset link has been sent to your mail id"
    )
    assert actual["data"] is None


def test_reset_password_enabled_sso_only(monkeypatch):
    monkeypatch.setitem(Utility.environment["app"], "enable_sso_only", True)
    response = client.post(
        "/api/account/password/reset",
        json={"data": "integ1@gmail.com"},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "This feature is disabled"
    assert actual["data"] is None


def test_reset_password_for_invalid_id():
    Utility.email_conf["email"]["enable"] = True
    response = client.post(
        "/api/account/password/reset",
        json={"data": "sasha.41195@gmail.com"},
    )
    actual = response.json()
    Utility.email_conf["email"]["enable"] = False
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Error! There is no user with the following mail id"
    assert actual["data"] is None


def test_list_bots_for_different_user_2():
    response = client.get(
        "/api/account/bot",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    assert len(response["data"]["shared"]) == 1
    pytest.bot = response["data"]["shared"][0]["_id"]
    pytest.account = response["data"]["shared"][0]["account"]


def test_send_link_for_valid_id(monkeypatch):
    monkeypatch.setattr(MailUtility, "trigger_smtp", mock_smtp)
    Utility.email_conf["email"]["enable"] = True
    response = client.post(
        "/api/account/email/confirmation/link",
        json={"data": "integration@demo.ai"},
    )
    actual = response.json()
    Utility.email_conf["email"]["enable"] = False
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Success! Confirmation link sent"
    assert actual["data"] is None


def test_send_link_enabled_sso_only(monkeypatch):
    monkeypatch.setitem(Utility.environment["app"], "enable_sso_only", True)
    response = client.post(
        "/api/account/email/confirmation/link",
        json={"data": "integration@demo.ai"},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "This feature is disabled"
    assert actual["data"] is None


def test_send_link_for_confirmed_id():
    Utility.email_conf["email"]["enable"] = True
    response = client.post(
        "/api/account/email/confirmation/link",
        json={"data": "integ1@gmail.com"},
    )
    actual = response.json()
    Utility.email_conf["email"]["enable"] = False
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Email already confirmed!"
    assert actual["data"] is None


def test_overwrite_password_for_non_matching_passwords():
    Utility.email_conf["email"]["enable"] = True
    response = client.post(
        "/api/account/password/change",
        json={
            "data": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJtYWlsX2lkIjoiaW50ZWcxQGdtYWlsLmNvbSJ9.Ycs1ROb1w6MMsx2WTA4vFu3-jRO8LsXKCQEB3fkoU20",
            "password": "Welcome@2",
            "confirm_password": "Welcume@2",
        },
    )
    actual = response.json()
    Utility.email_conf["email"]["enable"] = False
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["data"] is None


def test_overwrite_password_enabled_sso_only(monkeypatch):
    monkeypatch.setitem(Utility.environment["app"], "enable_sso_only", True)
    response = client.post(
        "/api/account/password/change",
        json={
            "data": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJtYWlsX2lkIjoiaW50ZWcxQGdtYWlsLmNvbSJ9.Ycs1ROb1w6MMsx2WTA4vFu3-jRO8LsXKCQEB3fkoU20",
            "password": "Welcome@20",
            "confirm_password": "Welcome@20",
        },
    )
    actual = response.json()
    assert actual["message"] == "This feature is disabled"
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["data"] is None


def test_add_and_delete_intents_by_integration_user():
    response = client.post(
        f"/api/auth/{pytest.bot}/integration/token",
        json={"name": "integration 1", "role": "designer"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    token = response.json()
    assert token["success"]
    assert token["error_code"] == 0
    assert token["data"]["access_token"]
    assert token["data"]["token_type"]

    response = client.post(
        f"/api/bot/{pytest.bot}/intents",
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
        f"/api/bot/{pytest.bot}/intents/integration_intent",
        headers={
            "Authorization": token["data"]["token_type"]
                             + " "
                             + token["data"]["access_token"],
            "X-USER": "integration1",
        },
    )

    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 0
    assert actual["message"] == "Intent deleted!"
    assert actual["success"]


def test_add_non_integration_intent_and_delete_intent_by_integration_user():
    response = client.post(
        f"/api/auth/{pytest.bot}/integration/token",
        json={"name": "integration 3", "role": "designer"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    token = response.json()
    assert token["success"]
    assert token["error_code"] == 0
    assert token["data"]["access_token"]
    assert token["data"]["token_type"]
    pytest.disable_token = (
        f'{token["data"]["token_type"]} {token["data"]["access_token"]}'
    )

    response = client.post(
        f"/api/bot/{pytest.bot}/intents",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"data": "non_integration_intent"},
    )
    actual = response.json()
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Intent added successfully!"

    response = client.delete(
        f"/api/bot/{pytest.bot}/intents/non_integration_intent",
        headers={
            "Authorization": token["data"]["token_type"]
                             + " "
                             + token["data"]["access_token"],
            "X-USER": "integration1",
        },
    )

    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 422
    assert actual["message"] == "This intent cannot be deleted by an integration user"
    assert not actual["success"]


def test_list_keys_none():
    response = client.get(
        f"/api/bot/{pytest.bot}/secrets/keys",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"] == []
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])
    assert actual["success"]


def test_add_secret():
    request = {"key": "AWS_KEY", "value": "123456789asdfghjk"}
    response = client.post(
        f"/api/bot/{pytest.bot}/secrets/add",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=request,
    )
    actual = response.json()
    assert not Utility.check_empty_string(actual["data"]["key_id"])
    assert actual["error_code"] == 0
    assert actual["message"] == "Secret added!"
    assert actual["success"]


def test_add_secret_invalid_request():
    request = {"key": None, "value": "123456789asdfghjk"}
    response = client.post(
        f"/api/bot/{pytest.bot}/secrets/add",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=request,
    )
    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 422
    assert not actual["success"]

    request = {"key": "AWS_KEY", "value": None}
    response = client.post(
        f"/api/bot/{pytest.bot}/secrets/add",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=request,
    )
    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 422
    assert not actual["success"]


def test_add_secret_already_exists():
    request = {"key": "AWS_KEY", "value": "123456789asdfghjk"}
    response = client.post(
        f"/api/bot/{pytest.bot}/secrets/add",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=request,
    )
    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 422
    assert actual["message"] == "Key exists!"
    assert not actual["success"]


def test_get_secret_not_exists():
    response = client.get(
        f"/api/bot/{pytest.bot}/secrets/keys/GOOGLE_KEY",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 422
    assert not actual["success"]
    assert actual["message"] == "key 'GOOGLE_KEY' does not exists!"


def test_get_secret():
    response = client.get(
        f"/api/bot/{pytest.bot}/secrets/keys/AWS_KEY",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"] == "123456789asdfghjk"
    assert actual["error_code"] == 0
    assert actual["success"]


def test_update_secret():
    request = {"key": "AWS_KEY", "value": "123456789"}
    response = client.put(
        f"/api/bot/{pytest.bot}/secrets/update",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=request,
    )
    actual = response.json()
    assert not Utility.check_empty_string(actual["data"]["key_id"])
    assert actual["error_code"] == 0
    assert actual["message"] == "Secret updated!"
    assert actual["success"]


def test_add_secret_2():
    request = {"key": "GOOGLE_KEY", "value": "sdfghj45678"}
    response = client.post(
        f"/api/bot/{pytest.bot}/secrets/add",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=request,
    )
    actual = response.json()
    assert not Utility.check_empty_string(actual["data"]["key_id"])
    assert actual["error_code"] == 0
    assert actual["message"] == "Secret added!"
    assert actual["success"]


def test_update_secret_invalid_request():
    request = {"key": "  ", "value": "123456789"}
    response = client.put(
        f"/api/bot/{pytest.bot}/secrets/update",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=request,
    )
    actual = response.json()
    assert Utility.check_empty_string(actual["data"])
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {"loc": ["body", "key"], "msg": "key is required", "type": "value_error"}
    ]
    assert not actual["success"]

    request = {"key": "AWS_KEY", "value": "  "}
    response = client.put(
        f"/api/bot/{pytest.bot}/secrets/update",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=request,
    )
    actual = response.json()
    assert Utility.check_empty_string(actual["data"])
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {"loc": ["body", "value"], "msg": "value is required", "type": "value_error"}
    ]
    assert not actual["success"]


def test_update_secret_not_exists():
    request = {"key": "GCP_KEY", "value": "123456789"}
    response = client.put(
        f"/api/bot/{pytest.bot}/secrets/update",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=request,
    )
    actual = response.json()
    assert Utility.check_empty_string(actual["data"])
    assert actual["error_code"] == 422
    assert actual["message"] == "key 'GCP_KEY' does not exists!"
    assert not actual["success"]


def test_list_keys():
    response = client.get(
        f"/api/bot/{pytest.bot}/secrets/keys",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"] == ["AWS_KEY", "GOOGLE_KEY"]
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])
    assert actual["success"]


def test_delete_secret():
    response = client.delete(
        f"/api/bot/{pytest.bot}/secrets/AWS_KEY",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 0
    assert actual["message"] == "Secret deleted!"
    assert actual["success"]


def test_delete_secret_not_exists():
    response = client.delete(
        f"/api/bot/{pytest.bot}/secrets/AWS_KEY",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 422
    assert actual["message"] == "key 'AWS_KEY' does not exists!"
    assert not actual["success"]


def test_add_secret_with_deleted_key():
    request = {"key": "AWS_KEY", "value": "123456789asdfghjk"}
    response = client.post(
        f"/api/bot/{pytest.bot}/secrets/add",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=request,
    )
    actual = response.json()
    assert not Utility.check_empty_string(actual["data"]["key_id"])
    assert actual["error_code"] == 0
    assert actual["message"] == "Secret added!"
    assert actual["success"]


def test_get_secret_2():
    response = client.get(
        f"/api/bot/{pytest.bot}/secrets/keys/AWS_KEY",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"] == "123456789asdfghjk"
    assert actual["error_code"] == 0
    assert actual["success"]


def test_add_vectordb_action_empty_name():
    request_body = {
        "name": "",
        "collection": 'test_add_vectordb_action_empty_name',
        "query_type": "embedding_search",
        "payload": {
            "type": "from_value",
            "value": {"ids": [0], "with_payload": True, "with_vector": True},
        },
        "response": {"value": "0"},
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/db",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()

    assert actual["error_code"] == 422
    assert actual["message"] == [
        {"loc": ["body", "name"], "msg": "name is required", "type": "value_error"}
    ]
    assert not actual["success"]


def test_add_vectordb_action_empty_collection_name():
    request_body = {
        "name": 'test_add_vectordb_action_empty_collection_name',
        "collection": '',
        "query_type": "embedding_search",
        "payload": {"type": "from_value", "value": {"ids": [0], "with_payload": True, "with_vector": True}},
        "response": {"value": "0"}
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/db",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()

    assert actual["error_code"] == 422
    assert actual["message"] == [
        {'loc': ['body', 'collection'], 'msg': 'collection is required', 'type': 'value_error'}]
    assert not actual["success"]


def test_add_vectordb_action_empty_operation_value():
    request_body = {
        "name": 'action_test_empty_operation_value',
        "collection": 'test_add_vectordb_action_empty_operation_value',
        "query_type": "",
        "payload": {"type": "from_value", "value": {"ids": [0], "with_payload": True, "with_vector": True}},
        "response": {"value": "0"}
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/db",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()

    assert actual["error_code"] == 422
    assert actual["message"] == [{'loc': ['body', 'query_type'],
                                  'msg': "value is not a valid enumeration member; permitted: 'payload_search', 'embedding_search'",
                                  'type': 'type_error.enum',
                                  'ctx': {'enum_values': ['payload_search', 'embedding_search']}}]
    assert not actual["success"]


def test_add_vectordb_action_empty_payload_type():
    request_body = {
        "name": "test_add_vectordb_action_empty_payload_type",
        "collection": 'test_add_vectordb_action_empty_payload_type',
        "query_type": "payload_search",
        "payload": {
            "type": "",
            "value": {"ids": [0], "with_payload": True, "with_vector": True},
        },
        "response": {"value": "0"},
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/db",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()

    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "payload", "type"],
            "msg": "value is not a valid enumeration member; permitted: 'from_value', 'from_slot', 'from_user_message'",
            "type": "type_error.enum",
            "ctx": {"enum_values": ["from_value", "from_slot", "from_user_message"]},
        },
        {
            "loc": ["body", "payload", "__root__"],
            "msg": "type is required",
            "type": "value_error",
        },
    ]
    assert not actual["success"]


def test_add_vectordb_action_without_enable_faq():
    request_body = {
        "name": "vectordb_action_test",
        "collection": 'test_add_vectordb_action_collection_does_not_exists',
        "query_type": "payload_search",
        "payload": {"type": "from_value", "value": {
            "filter": {
                "should": [
                    {"key": "city", "match": {"value": "London"}},
                    {"key": "color", "match": {"value": "red"}}
                ]
            }
        }},
        "response": {"value": "0"}
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/db",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == 'Collection does not exist!'
    assert not actual["success"]


def test_add_vectordb_action_collection_does_not_exists(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(bot=pytest.bot, user="integration@demo.ai", llm_settings=LLMSettings(enable_faq=True))

    monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)
    request_body = {
        "name": "vectordb_action_test",
        "collection": 'test_add_vectordb_action_collection_does_not_exists',
        "query_type": "payload_search",
        "payload": {"type": "from_value", "value": {
            "filter": {
                "should": [
                    {"key": "city", "match": {"value": "London"}},
                    {"key": "color", "match": {"value": "red"}}
                ]
            }
        }},
        "response": {"value": "0"}
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/db",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()

    assert actual["error_code"] == 422
    assert actual["message"] == 'Collection does not exist!'
    assert not actual["success"]


def test_add_vectordb_action(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(bot=pytest.bot, user="integration@demo.ai", llm_settings=LLMSettings(enable_faq=True))

    monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json={
            "metadata": [{"column_name": "city", "data_type": "str", "enable_search": True, "create_embeddings": True},
                         {"column_name": "color", "data_type": "str", "enable_search": True,
                          "create_embeddings": True}],
            "collection_name": "test_add_vectordb_action"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    pytest.delete_schema_id_db_action = actual["data"]["_id"]
    payload = {
        "data": {"city": "London", "color": "red"},
        "collection": "test_add_vectordb_action",
        "content_type": "json"}
    payload_response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    request_body = {
        "name": 'vectordb_action_test',
        "collection": 'test_add_vectordb_action',
        "query_type": "payload_search",
        "payload": {
            "type": "from_value",
            "value": {
                "filter": {
                    "should": [
                        {"key": "city", "match": {"value": "London"}},
                        {"key": "color", "match": {"value": "red"}},
                    ]
                }
            },
        },
        "response": {"value": "0"},
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/db",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()

    assert actual["error_code"] == 0
    assert actual["message"] == "Action added!"
    assert actual["success"]

    response_two = client.delete(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema/{pytest.delete_schema_id_db_action}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual_two = response_two.json()

    assert not actual_two["success"]
    assert actual_two[
               "message"] == 'Cannot remove collection test_add_vectordb_action linked to action "vectordb_action_test"!'
    assert actual_two["data"] is None
    assert actual_two["error_code"] == 422


def test_add_vectordb_action_case_insensitivity(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(bot=pytest.bot, user="integration@demo.ai", llm_settings=LLMSettings(enable_faq=True))

    monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)
    request_body = {
        "name": "VECTORDB_ACTION_CASE_INSENSITIVE",
        "collection": 'test_add_vectordb_action',
        "query_type": "payload_search",
        "payload": {
            "type": "from_value",
            "value": {
                "filter": {
                    "should": [
                        {"key": "city", "match": {"value": "London"}},
                        {"key": "color", "match": {"value": "red"}},
                    ]
                }
            },
        },
        "response": {"value": "0"},
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/db",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"] == "Action added!"
    assert actual["success"]

    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/db/VECTORDB_ACTION_CASE_INSENSITIVE",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert not actual["data"]

    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/db/vectordb_action_case_insensitive",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["error_code"] == 0
    assert actual["data"]
    assert actual["success"]


def test_add_vectordb_action_existing(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(bot=pytest.bot, user="integration@demo.ai", llm_settings=LLMSettings(enable_faq=True))

    monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)
    request_body = {
        "name": 'test_add_vectordb_action_existing',
        "collection": 'test_add_vectordb_action',
        "query_type": "embedding_search",
        "payload": {
            "type": "from_value",
            "value": {"ids": [0], "with_payload": True, "with_vector": True},
        },
        "response": {"value": "0"},
        "set_slots": [
            {"name": "bot", "value": "${RESPONSE}", "evaluation_type": "expression"}
        ],
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/db",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/db",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()

    assert actual["error_code"] == 422
    assert actual["message"] == "Action exists!"
    assert not actual["success"]


def test_add_vectordb_action_with_slots(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(bot=pytest.bot, user="integration@demo.ai", llm_settings=LLMSettings(enable_faq=True))

    monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)
    response = client.post(
        f"/api/bot/{pytest.bot}/slots",
        json={
            "name": "vectordb",
            "type": "text",
            "initial_value": "bot",
            "influence_conversation": False,
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert "data" in actual
    assert actual["message"] == "Slot added successfully!"
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0

    request_body = {
        "name": "test_add_vectordb_action_with_slots",
        "collection": 'test_add_vectordb_action',
        "query_type": "payload_search",
        "payload": {"type": "from_slot", "value": "vectordb"},
        "response": {"value": "0"},
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/db",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()

    assert actual["error_code"] == 0
    assert actual["message"]
    assert actual["success"]


def test_update_vectordb_action(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(bot=pytest.bot, user="integration@demo.ai", llm_settings=LLMSettings(enable_faq=True))

    monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)
    request_body = {
        "name": "test_update_vectordb_action",
        "collection": 'test_add_vectordb_action',
        "query_type": "payload_search",
        "payload": {
            "type": "from_value",
            "value": {
                "filter": {
                    "should": [
                        {"key": "city", "match": {"value": "London"}},
                        {"key": "color", "match": {"value": "red"}},
                    ]
                }
            },
        },
        "response": {"value": "0"},
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/db",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0

    request_body = {
        "name": "test_update_vectordb_action",
        "collection": 'test_add_vectordb_action',
        "query_type": "embedding_search",
        "payload": {
            "type": "from_value",
            "value": {"ids": [0], "with_payload": True, "with_vector": True},
        },
        "response": {"value": "0"},
        "set_slots": [
            {"name": "bot", "value": "${RESPONSE}", "evaluation_type": "script"}
        ],
    }
    response = client.put(
        url=f"/api/bot/{pytest.bot}/action/db",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["error_code"] == 0
    assert actual["message"] == "Action updated!"

    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/db/test_update_vectordb_action",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["success"]


def test_update_vectordb_action_non_existing(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(bot=pytest.bot, user="integration@demo.ai", llm_settings=LLMSettings(enable_faq=True))

    monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)
    request_body = {
        "name": "test_update_vectordb_action_non_existing",
        "collection": 'test_add_vectordb_action',
        "query_type": "embedding_search",
        "payload": {
            "type": "from_value",
            "value": {"ids": [6], "with_payload": True, "with_vector": True},
        },
        "response": {"value": "15"},
        "set_slots": [
            {"name": "age", "value": "${RESPONSE}", "evaluation_type": "script"}
        ],
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/db",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    request_body = {
        "name": "test_update_vectordb_action_non_existing_new",
        "collection": 'test_add_vectordb_action',
        "query_type": "embedding_search",
        "payload": {
            "type": "from_value",
            "value": {"ids": [6], "with_payload": True, "with_vector": True},
        },
        "response": {"value": "15"},
        "set_slots": [
            {"name": "age", "value": "${RESPONSE}", "evaluation_type": "script"}
        ],
    }
    response = client.put(
        url=f"/api/bot/{pytest.bot}/action/db",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["error_code"] == 422
    assert actual["message"]
    assert not actual["success"]


def test_update_vector_action_wrong_parameter(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(bot=pytest.bot, user="integration@demo.ai", llm_settings=LLMSettings(enable_faq=True))

    monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)
    request_body = {
        "name": "test_update_vector_action_1",
        "collection": 'test_add_vectordb_action',
        "query_type": "embedding_search",
        "payload": {
            "type": "from_value",
            "value": {"ids": [8], "with_payload": True, "with_vector": True},
        },
        "response": {"value": "15"},
        "set_slots": [
            {"name": "bot", "value": "${RESPONSE}", "evaluation_type": "expression"}
        ],
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/db",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0

    request_body = {
        "name": "test_update_vector_action_1",
        "collection": 'test_add_vectordb_action',
        "query_type": "embedding_search",
        "payload": {
            "type": "from_val",
            "value": {"ids": [81], "with_payload": True, "with_vector": True},
        },
        "response": {"value": "nupur"},
        "set_slots": [
            {"name": "bot", "value": "${RESPONSE}", "evaluation_type": "expression"}
        ],
    }
    response = client.put(
        url=f"/api/bot/{pytest.bot}/action/db",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["error_code"] == 422
    assert actual["message"]
    assert not actual["success"]


def test_get_vectordb_action():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/db/test_add_vectordb_action_with_slots",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["success"]


def test_get_vector_action_non_exisitng():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/db/never_added_vectordb_action",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] is not None
    assert not actual["success"]


def test_list_vector_db_action():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/db",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["error_code"] == 0
    assert actual["success"]
    assert actual['data'][0]['name'] == 'vectordb_action_test'


def test_delete_vectordb_action(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(bot=pytest.bot, user="integration@demo.ai", llm_settings=LLMSettings(enable_faq=True))

    monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)
    request_body = {
        "name": "test_delete_vectordb_action",
        "collection": 'test_add_vectordb_action',
        "query_type": "payload_search",
        "payload": {
            "type": "from_value",
            "value": {
                "filter": {
                    "should": [
                        {"key": "city", "match": {"value": "London"}},
                        {"key": "color", "match": {"value": "red"}},
                    ]
                }
            },
        },
        "response": {"value": "30"},
        "set_slots": [],
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/db",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    response = client.delete(
        url=f"/api/bot/{pytest.bot}/action/test_delete_vectordb_action",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"]
    assert actual["success"]


def test_delete_vectordb_action_non_existing(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(bot=pytest.bot, user="integration@demo.ai", llm_settings=LLMSettings(enable_faq=True))

    monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)
    request_body = {
        "name": "test_delete_vectordb_action_non_existing",
        "collection": 'test_add_vectordb_action',
        "query_type": "payload_search",
        "payload": {
            "type": "from_value",
            "value": {
                "filter": {
                    "should": [
                        {"key": "city", "match": {"value": "India"}},
                        {"key": "color", "match": {"value": "red"}},
                    ]
                }
            },
        },
        "response": {"value": "1"},
    }

    client.post(
        url=f"/api/bot/{pytest.bot}/action/db",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    response = client.delete(
        url=f"/api/bot/{pytest.bot}/action/new_vectordb_action_never_added",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["error_code"] == 422
    assert actual["message"]
    assert not actual["success"]


def test_add_http_action_malformed_url():
    request_body = {
        "auth_token": "",
        "action_name": "new_http_action",
        "response": {"value": "", "dispatch": False, "evaluation_type": "script"},
        "http_url": "192.168.104.1/api/test",
        "request_method": "GET",
        "http_params_list": [
            {"key": "testParam1", "parameter_type": "value", "value": "testValue1"}
        ],
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"]
    assert not actual["success"]


def test_add_http_action_missing_parameters():
    request_body = {
        "action_name": "new_http_action2",
        "response": {"value": "", "dispatch": False, "evaluation_type": "script"},
        "http_url": "http://www.google.com",
        "request_method": "put",
        "params_list": [{"key": "", "parameter_type": "", "value": ""}],
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
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
        "response": {"value": "", "dispatch": False},
        "http_url": "http://www.google.com",
        "request_method": "TUP",
        "http_params_list": [
            {"key": "testParam1", "parameter_type": "value", "value": "testValue1"}
        ],
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
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
        "response": {"value": "string"},
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "http_params_list": [
            {"key": "testParam1", "parameter_type": "value", "value": "testValue1"}
        ],
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
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
        "response": {"value": "string"},
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "http_params_list": [
            {"key": "testParam1", "parameter_type": "value", "value": "testValue1"}
        ],
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"]
    assert actual["success"]


def test_add_http_action_with_valid_dispatch_type():
    request_body = {
        "action_name": "test_add_http_action_with_valid_dispatch_type",
        "response": {"value": "string", "dispatch_type": "json"},
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "dynamic_params": '{"sender_id": "${sender_id}", "user_message": "${user_message}", "intent": "${intent}"}',
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"]
    assert actual["success"]

    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/httpaction/test_add_http_action_with_valid_dispatch_type",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["success"]
    assert actual["data"]["response"] == {
        "value": "string",
        "dispatch": True,
        "evaluation_type": "expression",
        "dispatch_type": "json",
    }
    assert actual["data"]["http_url"] == "http://www.google.com"
    assert actual["data"]["request_method"] == "GET"
    assert len(actual["data"]["params_list"]) == 0
    assert (
            actual["data"]["dynamic_params"]
            == '{"sender_id": "${sender_id}", "user_message": "${user_message}", "intent": "${intent}"}'
    )


def test_add_http_action_with_invalid_dispatch_type():
    request_body = {
        "action_name": "test_add_http_action_with_invalid_dispatch_type",
        "response": {"value": "string", "dispatch_type": "invalid_dispatch_type"},
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "dynamic_params": '{"sender_id": "${sender_id}", "user_message": "${user_message}", "intent": "${intent}"}',
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert not actual["success"]
    assert str(actual["message"]).__contains__(
        "value is not a valid enumeration member"
    )
    assert actual["data"] is None
    assert actual["error_code"] == 422


def test_add_http_action_with_dynamic_params():
    request_body = {
        "action_name": "test_add_http_action_with_dynamic_params",
        "response": {"value": "string"},
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "dynamic_params": '{"sender_id": "${sender_id}", "user_message": "${user_message}", "intent": "${intent}"}',
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"]
    assert actual["success"]


def test_update_http_action_with_dynamic_params():
    request_body = {
        "action_name": "test_update_http_action_with_dynamic_params",
        "response": {"value": "", "dispatch": False},
        "http_url": "http://www.google.com",
        "request_method": "GET",
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0

    request_body = {
        "action_name": "test_update_http_action_with_dynamic_params",
        "content_type": "application/x-www-form-urlencoded",
        "response": {
            "value": "json",
            "dispatch": False,
            "evaluation_type": "script",
            "dispatch_type": "json",
        },
        "http_url": "http://www.alphabet.com",
        "request_method": "POST",
        "dynamic_params": '{"sender_id": "${sender_id}", "user_message": "${user_message}", "intent": "${intent}"}',
        "headers": [
            {
                "key": "Authorization",
                "parameter_type": "value",
                "value": "bearer token",
                "encrypt": True,
            }
        ],
        "set_slots": [
            {"name": "bot", "value": "${RESPONSE}", "evaluation_type": "script"}
        ],
    }
    response = client.put(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0

    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/httpaction/test_update_http_action_with_dynamic_params",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["response"] == {
        "value": "json",
        "dispatch": False,
        "evaluation_type": "script",
        "dispatch_type": "json",
    }
    assert actual["data"]["http_url"] == "http://www.alphabet.com"
    assert actual["data"]["request_method"] == "POST"
    assert len(actual["data"]["params_list"]) == 0
    assert (
            actual["data"]["dynamic_params"]
            == '{"sender_id": "${sender_id}", "user_message": "${user_message}", "intent": "${intent}"}'
    )
    assert actual["data"]["headers"] == [
        {
            "key": "Authorization",
            "value": "bearer token",
            "parameter_type": "value",
            "encrypt": True,
        }
    ]
    assert actual["success"]


def test_add_http_action_with_sender_id_parameter_type():
    request_body = {
        "auth_token": "",
        "action_name": "test_add_http_action_with_sender_id_parameter_type",
        "response": {"value": "string"},
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "params_list": [
            {
                "key": "testParam1",
                "parameter_type": "sender_id",
                "value": "testValue1",
                "encrypt": True,
            },
            {
                "key": "testParam2",
                "parameter_type": "slot",
                "value": "testValue2",
                "encrypt": True,
            },
            {
                "key": "testParam3",
                "encrypt": True,
                "parameter_type": "user_message",
            },
            {"key": "testParam4", "parameter_type": "chat_log", "encrypt": True},
            {"key": "testParam5", "parameter_type": "intent", "encrypt": True},
            {
                "key": "testParam6",
                "parameter_type": "value",
                "encrypt": True,
                "value": "12345",
            },
            {
                "key": "testParam7",
                "parameter_type": "key_vault",
                "encrypt": False,
                "value": "ACCESS_KEY",
            },
        ],
        "headers": [
            {"key": "testParam1", "parameter_type": "sender_id", "value": "testValue1"},
            {"key": "testParam2", "parameter_type": "slot", "value": "testValue2"},
            {
                "key": "testParam3",
                "parameter_type": "user_message",
            },
            {
                "key": "testParam4",
                "parameter_type": "chat_log",
            },
            {
                "key": "testParam5",
                "parameter_type": "intent",
            },
            {"key": "testParam6", "parameter_type": "value", "value": "12345"},
            {
                "key": "testParam7",
                "parameter_type": "key_vault",
                "encrypt": False,
                "value": "SECRET_KEY",
            },
        ],
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"]
    assert actual["success"]


def test_get_http_action():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/httpaction/test_add_http_action_with_sender_id_parameter_type",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert (
            actual["data"]["action_name"]
            == "test_add_http_action_with_sender_id_parameter_type"
    )
    assert actual["data"]["response"] == {
        "value": "string",
        "dispatch": True,
        "evaluation_type": "expression",
        "dispatch_type": "text",
    }
    assert actual["data"]["http_url"] == "http://www.google.com"
    assert actual["data"]["request_method"] == "GET"
    assert actual["data"]["params_list"] == [
        {
            "key": "testParam1",
            "value": "testValue1",
            "parameter_type": "sender_id",
            "encrypt": True,
        },
        {
            "key": "testParam2",
            "value": "testvalue2",
            "parameter_type": "slot",
            "encrypt": True,
        },
        {
            "key": "testParam3",
            "value": "",
            "parameter_type": "user_message",
            "encrypt": True,
        },
        {
            "key": "testParam4",
            "value": "",
            "parameter_type": "chat_log",
            "encrypt": True,
        },
        {"key": "testParam5", "value": "", "parameter_type": "intent", "encrypt": True},
        {
            "key": "testParam6",
            "value": "12345",
            "parameter_type": "value",
            "encrypt": True,
        },
        {
            "key": "testParam7",
            "value": "ACCESS_KEY",
            "parameter_type": "key_vault",
            "encrypt": True,
        },
    ]
    assert actual["data"]["headers"] == [
        {
            "key": "testParam1",
            "value": "testValue1",
            "parameter_type": "sender_id",
            "encrypt": False,
        },
        {
            "key": "testParam2",
            "value": "testvalue2",
            "parameter_type": "slot",
            "encrypt": False,
        },
        {
            "key": "testParam3",
            "value": "",
            "parameter_type": "user_message",
            "encrypt": False,
        },
        {
            "key": "testParam4",
            "value": "",
            "parameter_type": "chat_log",
            "encrypt": False,
        },
        {
            "key": "testParam5",
            "value": "",
            "parameter_type": "intent",
            "encrypt": False,
        },
        {
            "key": "testParam6",
            "value": "12345",
            "parameter_type": "value",
            "encrypt": False,
        },
        {
            "key": "testParam7",
            "value": "SECRET_KEY",
            "parameter_type": "key_vault",
            "encrypt": True,
        },
    ]
    assert not actual["message"]
    assert actual["success"]


def test_add_http_action_invalid_parameter_type():
    request_body = {
        "auth_token": "",
        "action_name": "test_add_http_action_invalid_parameter_type",
        "response": {"value": "string"},
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "params_list": [
            {"key": "testParam1", "parameter_type": "val", "value": "testValue1"}
        ],
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"]
    assert not actual["success"]


def test_add_http_action_with_token():
    request_body = {
        "action_name": "test_add_http_action_with_token_and_story",
        "response": {"value": "string", "evaluation_type": "script"},
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "headers": [
            {
                "key": "Authorization",
                "parameter_type": "value",
                "value": "bearer dfiuhdfishifoshfoishnfoshfnsif***",
                "encrypt": True,
            },
            {
                "key": "testParam1",
                "parameter_type": "value",
                "value": "testVal***",
                "encrypt": True,
            },
            {
                "key": "testParam1",
                "parameter_type": "value",
                "value": "testVal***",
                "encrypt": True,
            },
        ],
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"]
    assert actual["success"]

    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/httpaction/test_add_http_action_with_token_and_story",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["response"] == {
        "dispatch": True,
        "evaluation_type": "script",
        "value": "string",
        "dispatch_type": "text",
    }
    assert actual["data"]["headers"] == [
        {
            "key": "Authorization",
            "parameter_type": "value",
            "value": "bearer dfiuhdfishifoshfoishnfoshfnsif***",
            "encrypt": True,
        },
        {
            "key": "testParam1",
            "parameter_type": "value",
            "value": "testVal***",
            "encrypt": True,
        },
        {
            "key": "testParam1",
            "parameter_type": "value",
            "value": "testVal***",
            "encrypt": True,
        },
    ]
    assert actual["data"]["http_url"] == "http://www.google.com"
    assert actual["data"]["request_method"] == "GET"
    assert len(actual["data"]["headers"]) == 3
    assert actual["success"]


def test_add_http_action_no_params():
    request_body = {
        "auth_token": "",
        "action_name": "test_add_http_action_no_params",
        "response": {"value": "string", "dispatch": False},
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "params_list": [],
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
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
        "response": {"value": "string", "dispatch": False, "evaluation_type": "script"},
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "params_list": [
            {"key": "testParam1", "parameter_type": "value", "value": "testValue1"}
        ],
        "set_slots": [
            {"name": "bot", "value": "${RESPONSE}", "evaluation_type": "script"}
        ],
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"]
    assert not actual["success"]


def test_get_http_action_non_exisitng():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/httpaction/never_added",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] is not None
    assert not actual["success"]


def test_update_http_action():
    request_body = {
        "action_name": "test_update_http_action",
        "response": {"value": "", "dispatch": False},
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "params_list": [
            {"key": "testParam1", "parameter_type": "value", "value": "testValue1"}
        ],
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0

    request_body = {
        "action_name": "test_update_http_action",
        "content_type": "application/x-www-form-urlencoded",
        "response": {
            "value": "json",
            "dispatch": False,
            "evaluation_type": "script",
            "dispatch_type": "json",
        },
        "http_url": "http://www.alphabet.com",
        "request_method": "POST",
        "params_list": [
            {
                "key": "testParam1",
                "parameter_type": "value",
                "value": "testValue1",
                "encrypt": True,
            },
            {
                "key": "testParam2",
                "parameter_type": "slot",
                "value": "testValue1",
                "encrypt": True,
            },
        ],
        "headers": [
            {
                "key": "Authorization",
                "parameter_type": "value",
                "value": "bearer token",
                "encrypt": True,
            }
        ],
        "set_slots": [
            {"name": "bot", "value": "${RESPONSE}", "evaluation_type": "script"}
        ],
    }
    response = client.put(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0

    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/httpaction/test_update_http_action",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["response"] == {
        "value": "json",
        "dispatch": False,
        "evaluation_type": "script",
        "dispatch_type": "json",
    }
    assert actual["data"]["http_url"] == "http://www.alphabet.com"
    assert actual["data"]["request_method"] == "POST"
    assert len(actual["data"]["params_list"]) == 2
    assert actual["data"]["params_list"] == [
        {
            "key": "testParam1",
            "value": "testValue1",
            "parameter_type": "value",
            "encrypt": True,
        },
        {
            "key": "testParam2",
            "value": "testvalue1",
            "parameter_type": "slot",
            "encrypt": True,
        },
    ]
    assert actual["data"]["headers"] == [
        {
            "key": "Authorization",
            "value": "bearer token",
            "parameter_type": "value",
            "encrypt": True,
        }
    ]
    assert actual["success"]


def test_update_http_action_wrong_parameter():
    request_body = {
        "auth_token": "",
        "action_name": "test_update_http_action_6",
        "response": {"value": "", "dispatch": False},
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "params_list": [
            {"key": "testParam1", "parameter_type": "value", "value": "testValue1"}
        ],
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0

    request_body = {
        "auth_token": "bearer hjklfsdjsjkfbjsbfjsvhfjksvfjksvfjksvf",
        "action_name": "test_update_http_action_6",
        "response": {"value": "json"},
        "http_url": "http://www.alphabet.com",
        "request_method": "POST",
        "params_list": [
            {"key": "testParam1", "parameter_type": "val", "value": "testValue1"},
            {"key": "testParam2", "parameter_type": "slot", "value": "testValue1"},
        ],
    }
    response = client.put(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"]
    assert not actual["success"]

    request_body = {
        "auth_token": "bearer hjklfsdjsjkfbjsbfjsvhfjksvfjksvfjksvf",
        "action_name": "test_update_http_action_6",
        "response": {"value": "json"},
        "http_url": "http://www.alphabet.com",
        "request_method": "POST",
        "params_list": [
            {"key": "testParam1", "parameter_type": "val", "value": "testValue1"},
            {"key": "testParam2", "parameter_type": "slot", "value": "testValue1"},
        ],
        "set_slots": [
            {"name": " ", "value": "${RESPONSE}", "evaluation_type": "script"}
        ],
    }
    response = client.put(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == [{'loc': ['body', 'params_list', 0, 'parameter_type'],
                                  'msg': "value is not a valid enumeration member; permitted: 'value', 'slot', 'sender_id', 'user_message', 'latest_message', 'intent', 'chat_log', 'key_vault'",
                                  'type': 'type_error.enum', 'ctx': {
            'enum_values': ['value', 'slot', 'sender_id', 'user_message', 'latest_message', 'intent', 'chat_log',
                            'key_vault']}}, {'loc': ['body', 'set_slots', 0, 'name'], 'msg': 'slot name is required',
                                             'type': 'value_error'}]

    assert not actual["success"]

    request_body = {
        "auth_token": "bearer hjklfsdjsjkfbjsbfjsvhfjksvfjksvfjksvf",
        "action_name": "test_update_http_action_6",
        "response": {"value": "json"},
        "http_url": "http://www.alphabet.com",
        "request_method": "POST",
        "params_list": [
            {"key": "testParam1", "parameter_type": "val", "value": "testValue1"},
            {"key": "testParam2", "parameter_type": "slot", "value": "testValue1"},
        ],
        "set_slots": [{"name": "bot", "value": " ", "evaluation_type": "script"}],
    }
    response = client.put(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == [{'loc': ['body', 'params_list', 0, 'parameter_type'],
                                  'msg': "value is not a valid enumeration member; permitted: 'value', 'slot', 'sender_id', 'user_message', 'latest_message', 'intent', 'chat_log', 'key_vault'",
                                  'type': 'type_error.enum', 'ctx': {
            'enum_values': ['value', 'slot', 'sender_id', 'user_message', 'latest_message', 'intent', 'chat_log',
                            'key_vault']}}, {'loc': ['body', 'set_slots', 0, 'value'],
                                             'msg': 'expression is required to evaluate value of slot',
                                             'type': 'value_error'}]

    assert not actual["success"]

    request_body = {
        "auth_token": "bearer hjklfsdjsjkfbjsbfjsvhfjksvfjksvfjksvf",
        "action_name": "test_update_http_action_6",
        "response": {"value": " ", "dispatch": True},
        "http_url": "http://www.alphabet.com",
        "request_method": "POST",
        "params_list": [
            {"key": "testParam1", "parameter_type": "val", "value": "testValue1"},
            {"key": "testParam2", "parameter_type": "slot", "value": "testValue1"},
        ],
        "set_slots": [{"name": "bot", "value": " ", "evaluation_type": "script"}],
    }
    response = client.put(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {'loc': ['body', 'response', '__root__'], 'msg': 'response is required for dispatch', 'type': 'value_error'},
        {'loc': ['body', 'params_list', 0, 'parameter_type'],
         'msg': "value is not a valid enumeration member; permitted: 'value', 'slot', 'sender_id', 'user_message', 'latest_message', 'intent', 'chat_log', 'key_vault'",
         'type': 'type_error.enum', 'ctx': {
            'enum_values': ['value', 'slot', 'sender_id', 'user_message', 'latest_message', 'intent', 'chat_log',
                            'key_vault']}},
        {'loc': ['body', 'set_slots', 0, 'value'], 'msg': 'expression is required to evaluate value of slot',
         'type': 'value_error'}]

    assert not actual["success"]


def test_update_http_action_non_existing():
    request_body = {
        "auth_token": "",
        "action_name": "test_update_http_action_non_existing",
        "response": {"value": "", "dispatch": False},
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "params_list": [],
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    request_body = {
        "auth_token": "bearer hjklfsdjsjkfbjsbfjsvhfjksvfjksvfjksvf",
        "action_name": "test_update_http_action_non_existing_new",
        "response": "json",
        "http_url": "http://www.alphabet.com",
        "request_method": "POST",
        "params_list": [
            {"key": "param1", "value": "value1", "parameter_type": "value"},
            {"key": "param2", "value": "value2", "parameter_type": "slot"},
        ],
    }
    response = client.put(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
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
        "response": {"value": "", "dispatch": False},
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "params_list": [],
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    response = client.delete(
        url=f"/api/bot/{pytest.bot}/action/test_delete_http_action",
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
        "response": {"value": "", "dispatch": False},
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "params_list": [],
    }

    client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    response = client.delete(
        url=f"/api/bot/{pytest.bot}/action/new_http_action_never_added",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"]
    assert not actual["success"]


def test_list_actions():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_path_action",
            "type": "STORY",
            "template_type": "Q&A",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "action_greet", "type": "ACTION"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"] == "Flow added successfully"
    assert actual["data"]["_id"]
    assert actual["success"]

    response = client.get(
        url=f"/api/bot/{pytest.bot}/actions",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])
    assert actual['data'] == {'actions': ['action_greet'],
                              'database_action': ['vectordb_action_test', 'vectordb_action_case_insensitive',
                                                  'test_add_vectordb_action_existing',
                                                  'test_add_vectordb_action_with_slots',
                                                  'test_update_vectordb_action',
                                                  'test_update_vectordb_action_non_existing',
                                                  'test_update_vector_action_1',
                                                  'test_delete_vectordb_action_non_existing'],
                              'http_action': ['test_add_http_action_no_token',
                                              'test_add_http_action_with_valid_dispatch_type',
                                              'test_add_http_action_with_dynamic_params',
                                              'test_update_http_action_with_dynamic_params',
                                              'test_add_http_action_with_sender_id_parameter_type',
                                              'test_add_http_action_with_token_and_story',
                                              'test_add_http_action_no_params',
                                              'test_add_http_action_existing', 'test_update_http_action',
                                              'test_update_http_action_6', 'test_update_http_action_non_existing',
                                              'new_http_action4'],
                              'utterances': ['utter_greet', 'utter_cheer_up', 'utter_did_that_help', 'utter_happy',
                                             'utter_goodbye', 'utter_iamabot', 'utter_default',
                                             'utter_please_rephrase'],
                              'slot_set_action': [], 'form_validation_action': [], 'email_action': [],
                              'google_search_action': [],
                              'jira_action': [], 'zendesk_action': [], 'pipedrive_leads_action': [],
                              'hubspot_forms_action': [],
                              'two_stage_fallback': [], 'kairon_bot_response': [], 'razorpay_action': [],
                              'prompt_action': [],
                              'pyscript_action': [], 'web_search_action': [], 'live_agent_action': []}

    assert actual["success"]


@responses.activate
def test_train_using_event():
    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.model_training}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/train",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "Model training started."
    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.model_training
    )


def test_update_training_data_generator_status(monkeypatch):
    request_body = {"status": EVENT_STATUS.INITIATED.value}
    response = client.put(
        f"/api/bot/{pytest.bot}/update/data/generator/status",
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
        f"/api/bot/{pytest.bot}/data/generation/history",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    response = actual["data"]
    assert response is not None
    response["status"] = "Initiated"
    assert actual["message"] is None


def test_update_training_data_generator_status_completed(monkeypatch):
    training_data = [
        {
            "intent": "intent1_test_add_training_data",
            "training_examples": ["example1", "example2"],
            "response": "response1",
        },
        {
            "intent": "intent2_test_add_training_data",
            "training_examples": ["example3", "example4"],
            "response": "response2",
        },
    ]
    request_body = {"status": EVENT_STATUS.COMPLETED.value, "response": training_data}
    response = client.put(
        f"/api/bot/{pytest.bot}/update/data/generator/status",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "Status updated successfully!"


def test_update_training_data_generator_wrong_status(monkeypatch):
    training_data = [
        {
            "intent": "intent1_test_add_training_data",
            "training_examples": ["example1", "example2"],
            "response": "response1",
        },
        {
            "intent": "intent2_test_add_training_data",
            "training_examples": ["example3", "example4"],
            "response": "response2",
        },
    ]
    request_body = {"status": "test", "response": training_data}
    response = client.put(
        f"/api/bot/{pytest.bot}/update/data/generator/status",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 422
    assert str(actual["message"]).__contains__(
        "value is not a valid enumeration member"
    )
    assert not actual["success"]


def test_add_training_data(monkeypatch):
    response = client.get(
        f"/api/bot/{pytest.bot}/data/generation/history",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    response = actual["data"]
    assert response is not None
    response["status"] = "Initiated"
    assert actual["message"] is None
    doc_id = response["training_history"][0]["_id"]
    training_data = {
        "history_id": doc_id,
        "training_data": [
            {
                "intent": "intent1_test_add_training_data",
                "training_examples": ["example1", "example2"],
                "response": "response1",
            },
            {
                "intent": "intent2_test_add_training_data",
                "training_examples": ["example3", "example4"],
                "response": "response2",
            },
        ],
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/data/bulk",
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
    training_examples = list(
        TrainingExamples.objects(intent="intent1_test_add_training_data")
    )
    assert training_examples is not None
    assert len(training_examples) == 2
    training_examples = list(
        TrainingExamples.objects(intent="intent2_test_add_training_data")
    )
    assert len(training_examples) == 2
    assert Responses.objects(name="utter_intent1_test_add_training_data") is not None
    assert Responses.objects(name="utter_intent2_test_add_training_data") is not None
    story = Stories.objects(block_name="path_intent1_test_add_training_data").get()
    assert story is not None
    assert story["events"][0]["name"] == "intent1_test_add_training_data"
    assert story["events"][0]["type"] == StoryEventType.user
    assert story["events"][1]["name"] == "utter_intent1_test_add_training_data"
    assert story["events"][1]["type"] == StoryEventType.action
    story = Stories.objects(block_name="path_intent2_test_add_training_data").get()
    assert story is not None
    assert story["events"][0]["name"] == "intent2_test_add_training_data"
    assert story["events"][0]["type"] == StoryEventType.user
    assert story["events"][1]["name"] == "utter_intent2_test_add_training_data"
    assert story["events"][1]["type"] == StoryEventType.action


def test_get_training_data_history_1(monkeypatch):
    response = client.get(
        f"/api/bot/{pytest.bot}/data/generation/history",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] is None
    training_data = actual["data"]["training_history"][0]

    assert training_data["status"] == EVENT_STATUS.COMPLETED.value
    end_timestamp = training_data["end_timestamp"]
    assert end_timestamp is not None
    assert training_data["last_update_timestamp"] == end_timestamp
    response = training_data["response"]
    assert response is not None
    assert response[0]["intent"] == "intent1_test_add_training_data"
    assert response[0]["training_examples"][0]["training_example"] == "example1"
    assert response[0]["training_examples"][0]["is_persisted"]
    assert response[0]["training_examples"][1]["training_example"] == "example2"
    assert response[0]["training_examples"][1]["is_persisted"]
    assert response[0]["response"] == "response1"
    assert response[1]["intent"] == "intent2_test_add_training_data"
    assert response[1]["training_examples"][0]["training_example"] == "example3"
    assert response[1]["training_examples"][0]["is_persisted"]
    assert response[1]["training_examples"][1]["training_example"] == "example4"
    assert response[1]["training_examples"][1]["is_persisted"]
    assert response[1]["response"] == "response2"


def test_update_training_data_generator_status_exception(monkeypatch):
    request_body = {
        "status": EVENT_STATUS.INITIATED.value,
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/update/data/generator/status",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "Status updated successfully!"

    request_body = {"status": EVENT_STATUS.FAIL.value, "exception": "Exception message"}
    response = client.put(
        f"/api/bot/{pytest.bot}/update/data/generator/status",
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
        f"/api/bot/{pytest.bot}/data/generation/history",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] is None
    training_data = actual["data"]["training_history"][0]
    assert training_data["status"] == EVENT_STATUS.FAIL.value
    end_timestamp = training_data["end_timestamp"]
    assert end_timestamp is not None
    assert training_data["last_update_timestamp"] == end_timestamp
    assert training_data["exception"] == "Exception message"


def test_fetch_latest(monkeypatch):
    request_body = {
        "status": EVENT_STATUS.INITIATED.value,
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/update/data/generator/status",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    response = client.get(
        f"/api/bot/{pytest.bot}/data/generation/latest",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["status"] == EVENT_STATUS.INITIATED.value
    assert actual["message"] is None


async def mock_upload(doc):
    if not (
            doc.filename.lower().endswith(".pdf") or doc.filename.lower().endswith(".docx")
    ):
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

    monkeypatch.setattr(
        TrainingDataGenerationProcessor, "is_in_progress", _in_progress_mock
    )
    monkeypatch.setattr(
        TrainingDataGenerationProcessor,
        "check_data_generation_limit",
        _daily_limit_mock,
    )
    monkeypatch.setattr(TrainingDataGenerationProcessor, "set_status", _set_status_mock)
    monkeypatch.setattr(DataUtility, "trigger_data_generation_event", _train_data_gen)


def test_file_upload_docx(mock_file_upload, monkeypatch):
    monkeypatch.setattr(Utility, "upload_document", mock_upload)

    response = client.post(
        f"/api/bot/{pytest.bot}/upload/data_generation/file",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files={
            "doc": (
                "tests/testing_data/file_data/sample1.docx",
                open("tests/testing_data/file_data/sample1.docx", "rb"),
            )
        },
    )

    actual = response.json()
    assert (
            actual["message"]
            == "File uploaded successfully and training data generation has begun"
    )
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]


def test_file_upload_pdf(mock_file_upload, monkeypatch):
    monkeypatch.setattr(Utility, "upload_document", mock_upload)

    response = client.post(
        f"/api/bot/{pytest.bot}/upload/data_generation/file",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files={
            "doc": (
                "tests/testing_data/file_data/sample1.pdf",
                open("tests/testing_data/file_data/sample1.pdf", "rb"),
            )
        },
    )

    actual = response.json()
    assert (
            actual["message"]
            == "File uploaded successfully and training data generation has begun"
    )
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]


def test_file_upload_error(mock_file_upload, monkeypatch):
    monkeypatch.setattr(Utility, "upload_document", mock_upload)

    response = client.post(
        f"/api/bot/{pytest.bot}/upload/data_generation/file",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files={"doc": ("nlu.yml", open("tests/testing_data/all/data/nlu.yml", "rb"))},
    )

    actual = response.json()
    assert actual["message"] == "Invalid File Format"
    assert actual["error_code"] == 422
    assert not actual["success"]


def test_list_action_server_logs_empty():
    response = client.get(
        f"/api/bot/{pytest.bot}/actions/logs?start_idx=0&page_size=10",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["data"]["logs"] == []
    assert actual["data"]["total"] == 0


def test_list_action_server_logs():
    bot = pytest.bot
    bot_2 = "integration2"
    request_params = {"key": "value", "key2": "value2"}
    expected_intents = [
        "intent13",
        "intent11",
        "intent9",
        "intent8",
        "intent7",
        "intent6",
        "intent5",
        "intent4",
        "intent3",
        "intent2",
    ]
    ActionServerLogs(
        intent="intent1",
        action="http_action",
        sender="sender_id",
        timestamp="2021-04-05T07:59:08.771000",
        request_params=request_params,
        api_response="Response",
        bot_response="Bot Response",
        bot=bot,
    ).save()
    ActionServerLogs(
        intent="intent2",
        action="http_action",
        sender="sender_id",
        url="http://kairon-api.digite.com/api/bot",
        request_params=request_params,
        api_response="Response",
        bot_response="Bot Response",
        bot=bot,
        status="FAILURE",
    ).save()
    ActionServerLogs(
        intent="intent1",
        action="http_action",
        sender="sender_id",
        request_params=request_params,
        api_response="Response",
        bot_response="Bot Response",
        bot=bot_2,
    ).save()
    ActionServerLogs(
        intent="intent3",
        action="http_action",
        sender="sender_id",
        request_params=request_params,
        api_response="Response",
        bot_response="Bot Response",
        bot=bot,
        status="FAILURE",
    ).save()
    ActionServerLogs(
        intent="intent4",
        action="http_action",
        sender="sender_id",
        request_params=request_params,
        api_response="Response",
        bot_response="Bot Response",
        bot=bot,
    ).save()
    ActionServerLogs(
        intent="intent5",
        action="http_action",
        sender="sender_id",
        request_params=request_params,
        api_response="Response",
        bot_response="Bot Response",
        bot=bot,
        status="FAILURE",
    ).save()
    ActionServerLogs(
        intent="intent6",
        action="http_action",
        sender="sender_id",
        request_params=request_params,
        api_response="Response",
        bot_response="Bot Response",
        bot=bot,
    ).save()
    ActionServerLogs(
        intent="intent7",
        action="http_action",
        sender="sender_id",
        request_params=request_params,
        api_response="Response",
        bot_response="Bot Response",
        bot=bot,
    ).save()
    ActionServerLogs(
        intent="intent8",
        action="http_action",
        sender="sender_id",
        request_params=request_params,
        api_response="Response",
        bot_response="Bot Response",
        bot=bot,
    ).save()
    ActionServerLogs(
        intent="intent9",
        action="http_action",
        sender="sender_id",
        request_params=request_params,
        api_response="Response",
        bot_response="Bot Response",
        bot=bot,
    ).save()
    ActionServerLogs(
        intent="intent10",
        action="http_action",
        sender="sender_id",
        request_params=request_params,
        api_response="Response",
        bot_response="Bot Response",
        bot=bot_2,
    ).save()
    ActionServerLogs(
        intent="intent11",
        action="http_action",
        sender="sender_id",
        request_params=request_params,
        api_response="Response",
        bot_response="Bot Response",
        bot=bot,
    ).save()
    ActionServerLogs(
        intent="intent12",
        action="http_action",
        sender="sender_id",
        request_params=request_params,
        api_response="Response",
        bot_response="Bot Response",
        bot=bot_2,
        status="FAILURE",
    ).save()
    ActionServerLogs(
        intent="intent13",
        action="http_action",
        sender="sender_id_13",
        request_params=request_params,
        api_response="Response",
        bot_response="Bot Response",
        bot=bot,
        status="FAILURE",
    ).save()
    response = client.get(
        f"/api/bot/{pytest.bot}/actions/logs",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["success"]
    assert len(actual["data"]["logs"]) == 10
    assert actual["data"]["total"] == 11
    assert [log["intent"] in expected_intents for log in actual["data"]["logs"]]
    assert actual["data"]["logs"][0]["action"] == "http_action"
    assert any(
        [log["request_params"] == request_params for log in actual["data"]["logs"]]
    )
    assert any([log["sender"] == "sender_id_13" for log in actual["data"]["logs"]])
    assert any(
        [log["bot_response"] == "Bot Response" for log in actual["data"]["logs"]]
    )
    assert any([log["api_response"] == "Response" for log in actual["data"]["logs"]])
    assert any([log["status"] == "FAILURE" for log in actual["data"]["logs"]])
    assert any([log["status"] == "SUCCESS" for log in actual["data"]["logs"]])

    response = client.get(
        f"/api/bot/{pytest.bot}/actions/logs?start_idx=0&page_size=15",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert len(actual["data"]["logs"]) == 11
    assert actual["data"]["total"] == 11

    response = client.get(
        f"/api/bot/{pytest.bot}/actions/logs?start_idx=10&page_size=1",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["success"]
    assert len(actual["data"]["logs"]) == 1
    assert actual["data"]["total"] == 11


def test_add_training_data_invalid_id(monkeypatch):
    request_body = {"status": EVENT_STATUS.COMPLETED.value}
    client.put(
        f"/api/bot/{pytest.bot}/update/data/generator/status",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    response = client.get(
        f"/api/bot/{pytest.bot}/data/generation/history",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    response = actual["data"]
    assert response is not None
    response["status"] = "Initiated"
    assert actual["message"] is None
    doc_id = response["training_history"][0]["_id"]
    training_data = {
        "history_id": doc_id,
        "training_data": [
            {
                "intent": "intent1_test_add_training_data",
                "training_examples": ["example1", "example2"],
                "response": "response1",
            },
            {
                "intent": "intent2_test_add_training_data",
                "training_examples": ["example3", "example4"],
                "response": "response2",
            },
        ],
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/data/bulk",
        json=training_data,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"] == "No Training Data Generated"


def test_feedback():
    request = {
        "rating": 5.0,
        "scale": 5.0,
        "feedback": "The product is better than rasa.",
    }
    response = client.post(
        f"/api/account/feedback",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=request,
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert not actual["data"]
    assert actual["message"] == "Thanks for your feedback!"


def test_add_rule():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_path",
            "type": "RULE",
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
    assert actual["message"] == "Flow added successfully"
    assert actual["data"]["_id"]
    pytest.story_id = actual["data"]["_id"]


def test_add_rule_with_name_already_exists():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "ask the user to rephrase whenever they send a message with low nlu confidence",
            "type": "RULE",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_greet", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"] == "Rule with the name already exists"


def test_add_rule_invalid_type():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_path",
            "type": "TEST",
            "template_type": "Q&A",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_greet", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "type"],
            "msg": "value is not a valid enumeration member; permitted: 'STORY', 'RULE', 'MULTIFLOW'",
            "type": "type_error.enum",
            "ctx": {"enum_values": ["STORY", "RULE", "MULTIFLOW"]},
        }
    ]


def test_add_rule_empty_event():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={"name": "test_add_rule_empty_event", "type": "RULE", "steps": []},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "steps"],
            "msg": "Steps are required to form Flow",
            "type": "value_error",
        }
    ]


def test_add_rule_lone_intent():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_add_rule_lone_intent",
            "type": "RULE",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_greet", "type": "BOT"},
                {"name": "greet_again", "type": "INTENT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "steps"],
            "msg": "Intent should be followed by utterance or action",
            "type": "value_error",
        }
    ]


def test_add_rule_consecutive_intents():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_add_rule_consecutive_intents",
            "type": "RULE",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_greet", "type": "INTENT"},
                {"name": "utter_greet", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "steps"],
            "msg": "Found 2 consecutive intents",
            "type": "value_error",
        }
    ]


def test_add_rule_multiple_actions():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_add_rule_consecutive_actions",
            "type": "RULE",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_greet", "type": "HTTP_ACTION"},
                {"name": "utter_greet_again", "type": "HTTP_ACTION"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Flow added successfully"


def test_add_rule_utterance_as_first_step():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_add_rule_consecutive_intents",
            "type": "RULE",
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
    assert actual["message"] == [
        {
            "loc": ["body", "steps"],
            "msg": "First step should be an intent",
            "type": "value_error",
        }
    ]


def test_add_rule_missing_event_type():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_path",
            "type": "RULE",
            "steps": [{"name": "greet"}, {"name": "utter_greet", "type": "BOT"}],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "steps", 0, "type"],
            "msg": "field required",
            "type": "value_error.missing",
        }
    ]


def test_add_rule_invalid_event_type():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_path",
            "type": "RULE",
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
    assert actual["message"] == [
        {
            "ctx": {
                "enum_values": [
                    "INTENT",
                    "SLOT",
                    "FORM_START",
                    "FORM_END",
                    "BOT",
                    "HTTP_ACTION",
                    "ACTION",
                    "SLOT_SET_ACTION",
                    "FORM_ACTION",
                    "GOOGLE_SEARCH_ACTION",
                    "EMAIL_ACTION",
                    "JIRA_ACTION",
                    "ZENDESK_ACTION",
                    "PIPEDRIVE_LEADS_ACTION",
                    "HUBSPOT_FORMS_ACTION",
                    "RAZORPAY_ACTION",
                    "TWO_STAGE_FALLBACK_ACTION",
                    "PYSCRIPT_ACTION",
                    "PROMPT_ACTION",
                    "DATABASE_ACTION",
                    "WEB_SEARCH_ACTION",
                    "LIVE_AGENT_ACTION",
                    "STOP_FLOW_ACTION"
                ]
            },
            "loc": ["body", "steps", 0, "type"],
            "msg": "value is not a valid enumeration member; permitted: 'INTENT', 'SLOT', 'FORM_START', 'FORM_END', 'BOT', 'HTTP_ACTION', 'ACTION', 'SLOT_SET_ACTION', 'FORM_ACTION', 'GOOGLE_SEARCH_ACTION', 'EMAIL_ACTION', 'JIRA_ACTION', 'ZENDESK_ACTION', 'PIPEDRIVE_LEADS_ACTION', 'HUBSPOT_FORMS_ACTION', 'RAZORPAY_ACTION', 'TWO_STAGE_FALLBACK_ACTION', 'PYSCRIPT_ACTION', 'PROMPT_ACTION', 'DATABASE_ACTION', 'WEB_SEARCH_ACTION', 'LIVE_AGENT_ACTION', 'STOP_FLOW_ACTION'",
            "type": "type_error.enum",
        }
    ]


def test_update_rule():
    response = client.put(
        f"/api/bot/{pytest.bot}/stories/{pytest.story_id}",
        json={
            "name": "test_path",
            "type": "RULE",
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
    assert actual["message"] == "Flow updated successfully"
    assert actual["data"]["_id"]


def test_update_rule_with_name_already_exists():
    response = client.put(
        f"/api/bot/{pytest.bot}/stories/{pytest.story_id}",
        json={
            "name": "test_add_rule_consecutive_actions",
            "type": "RULE",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_nonsense", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Rule with the name already exists"
    assert actual["data"] is None
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_update_rule_invalid_event_type():
    response = client.put(
        f"/api/bot/{pytest.bot}/stories/{pytest.story_id}",
        json={
            "name": "test_path",
            "type": "RULE",
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
    assert actual["message"] == [
        {
            "ctx": {
                "enum_values": [
                    "INTENT",
                    "SLOT",
                    "FORM_START",
                    "FORM_END",
                    "BOT",
                    "HTTP_ACTION",
                    "ACTION",
                    "SLOT_SET_ACTION",
                    "FORM_ACTION",
                    "GOOGLE_SEARCH_ACTION",
                    "EMAIL_ACTION",
                    "JIRA_ACTION",
                    "ZENDESK_ACTION",
                    "PIPEDRIVE_LEADS_ACTION",
                    "HUBSPOT_FORMS_ACTION",
                    "RAZORPAY_ACTION",
                    "TWO_STAGE_FALLBACK_ACTION",
                    "PYSCRIPT_ACTION",
                    "PROMPT_ACTION",
                    "DATABASE_ACTION",
                    "WEB_SEARCH_ACTION",
                    "LIVE_AGENT_ACTION",
                    "STOP_FLOW_ACTION",
                ]
            },
            "loc": ["body", "steps", 0, "type"],
            "msg": "value is not a valid enumeration member; permitted: 'INTENT', 'SLOT', 'FORM_START', 'FORM_END', 'BOT', 'HTTP_ACTION', 'ACTION', 'SLOT_SET_ACTION', 'FORM_ACTION', 'GOOGLE_SEARCH_ACTION', 'EMAIL_ACTION', 'JIRA_ACTION', 'ZENDESK_ACTION', 'PIPEDRIVE_LEADS_ACTION', 'HUBSPOT_FORMS_ACTION', 'RAZORPAY_ACTION', 'TWO_STAGE_FALLBACK_ACTION', 'PYSCRIPT_ACTION', 'PROMPT_ACTION', 'DATABASE_ACTION', 'WEB_SEARCH_ACTION', 'LIVE_AGENT_ACTION', 'STOP_FLOW_ACTION'",
            "type": "type_error.enum",
        }
    ]


def test_delete_rule():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_path1",
            "type": "RULE",
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
    assert actual["message"] == "Flow added successfully"
    pytest.story_id = actual["data"]["_id"]

    response = client.delete(
        f"/api/bot/{pytest.bot}/stories/{pytest.story_id}/RULE",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Flow deleted successfully"


def test_delete_non_existing_rule():
    response = client.delete(
        f"/api/bot/{pytest.bot}/stories/{pytest.story_id}/RULE",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Flow does not exists"


def test_add_rule_with_multiple_intents():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_path",
            "type": "RULE",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_greet", "type": "BOT"},
                {"name": "location", "type": "INTENT"},
                {"name": "utter_location", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "steps"],
            "msg": "Found rules 'test_path' that contain more than intent.\nPlease use stories for this case",
            "type": "value_error",
        }
    ]
    assert actual["data"] is None


@responses.activate
def test_validate():
    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.data_importer}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )

    response = client.post(
        f"/api/bot/{pytest.bot}/validate",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert not actual["data"]
    assert actual["message"] == "Event triggered! Check logs."
    complete_end_to_end_event_execution(
        pytest.bot, "test_user", EventClass.data_importer
    )


@responses.activate
def test_upload_missing_data():
    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.data_importer}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )
    files = (
        (
            "training_files",
            (
                "domain.yml",
                BytesIO(open("tests/testing_data/all/domain.yml", "rb").read()),
            ),
        ),
        (
            "training_files",
            (
                "stories.yml",
                BytesIO(open("tests/testing_data/all/data/stories.yml", "rb").read()),
            ),
        ),
        (
            "training_files",
            (
                "config.yml",
                BytesIO(open("tests/testing_data/all/config.yml", "rb").read()),
            ),
        ),
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/upload",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=files,
    )
    actual = response.json()
    assert actual["message"] == "Upload in progress! Check logs."
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]
    complete_end_to_end_event_execution(
        pytest.bot, "test_user", EventClass.data_importer
    )


@responses.activate
def test_upload_valid_and_invalid_data():
    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.data_importer}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )
    files = (
        ("training_files", ("nlu_1.yml", b"")),
        (
            "training_files",
            ("domain_5.yml", open("tests/testing_data/all/domain.yml", "rb")),
        ),
        (
            "training_files",
            ("stories.yml", open("tests/testing_data/all/data/stories.yml", "rb")),
        ),
        (
            "training_files",
            ("config_6.yml", open("tests/testing_data/all/config.yml", "rb")),
        ),
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/upload",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=files,
    )
    actual = response.json()
    assert actual["message"] == "Upload in progress! Check logs."
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]
    complete_end_to_end_event_execution(
        pytest.bot, "test_user", EventClass.data_importer
    )


def test_upload_with_http_error():
    config = Utility.load_yaml("./tests/testing_data/yml_training_files/config.yml")
    config.get("pipeline").append({"name": "XYZ"})
    files = (
        ("training_files", ("config.yml", json.dumps(config).encode())),
        (
            "training_files",
            ("actions.yml", open("tests/testing_data/error/actions.yml", "rb")),
        ),
    )

    response = client.post(
        f"/api/bot/{pytest.bot}/upload",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=files,
    )
    actual = response.json()
    assert actual["message"] == "Upload in progress! Check logs."
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]

    response = client.get(
        f"/api/bot/{pytest.bot}/importer/logs?start_idx=0&page_size=10",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]["logs"]) == 4
    assert actual["data"]["total"] == 4
    assert actual["data"]["logs"][0]["status"] == "Failure"
    assert actual["data"]["logs"][0]["event_status"] == EVENT_STATUS.COMPLETED.value
    assert actual["data"]["logs"][0]["is_data_uploaded"]
    assert actual["data"]["logs"][0]["start_timestamp"]
    assert actual["data"]["logs"][0]["start_timestamp"]
    assert actual["data"]["logs"][0]["start_timestamp"]
    assert (
            "Required http action fields"
            in actual["data"]["logs"][0]["actions"][0]["data"][0]
    )
    assert actual["data"]["logs"][0]["config"]["data"] == ["Invalid component XYZ"]


def test_upload_actions_and_config():
    files = (
        (
            "training_files",
            (
                "config.yml",
                open("tests/testing_data/yml_training_files/config.yml", "rb"),
            ),
        ),
        (
            "training_files",
            (
                "actions.yml",
                open("tests/testing_data/yml_training_files/actions.yml", "rb"),
            ),
        ),
    )

    response = client.post(
        f"/api/bot/{pytest.bot}/upload",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=files,
    )
    actual = response.json()
    assert actual["message"] == "Upload in progress! Check logs."
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]

    response = client.get(
        f"/api/bot/{pytest.bot}/importer/logs?start_idx=0&page_size=10",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]["logs"]) == 5
    assert actual["data"]["total"] == 5
    assert actual['data']["logs"][0]['status'] == 'Success'
    assert actual['data']["logs"][0]['event_status'] == EVENT_STATUS.COMPLETED.value
    assert actual['data']["logs"][0]['is_data_uploaded']
    assert actual['data']["logs"][0]['start_timestamp']
    assert actual['data']["logs"][0]['end_timestamp']
    assert actual['data']["logs"][0]['actions'] == [{'type': 'http_actions', 'count': 5, 'data': []},
                                                    {'type': 'slot_set_actions', 'count': 0, 'data': []},
                                                    {'type': 'form_validation_actions', 'count': 0, 'data': []},
                                                    {'type': 'email_actions', 'count': 0, 'data': []},
                                                    {'type': 'google_search_actions', 'count': 1, 'data': []},
                                                    {'type': 'jira_actions', 'count': 0, 'data': []},
                                                    {'type': 'zendesk_actions', 'count': 0, 'data': []},
                                                    {'type': 'pipedrive_leads_actions', 'data': [], 'count': 0},
                                                    {'type': 'prompt_actions', 'data': [], 'count': 0},
                                                    {'type': 'razorpay_actions', 'data': [], 'count': 0},
                                                    {'type': 'pyscript_actions', 'data': [], 'count': 0}]
    assert not actual['data']["logs"][0]['config']['data']

    response = client.get(
        f"/api/bot/{pytest.bot}/action/httpaction",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]) == 5


@patch(
    "kairon.shared.importer.processor.DataImporterLogProcessor.is_limit_exceeded",
    autospec=True,
)
@patch("kairon.shared.utils.Utility.request_event_server", autospec=True)
def test_upload_multiflow_stories(mock_is_limit_exceeded, mock_event_server):
    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.data_importer}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )
    files = (
        (
            "training_files",
            (
                "domain.yml",
                open("tests/testing_data/yml_training_files/domain.yml", "rb"),
            ),
        ),
        (
            "training_files",
            (
                "nlu.yml",
                open("tests/testing_data/yml_training_files/data/nlu.yml", "rb"),
            ),
        ),
        (
            "training_files",
            (
                "stories.yml",
                open("tests/testing_data/yml_training_files/data/stories.yml", "rb"),
            ),
        ),
        (
            "training_files",
            (
                "rules.yml",
                open("tests/testing_data/yml_training_files/data/rules.yml", "rb"),
            ),
        ),
        (
            "training_files",
            (
                "actions.yml",
                open("tests/testing_data/yml_training_files/actions.yml", "rb"),
            ),
        ),
        (
            "training_files",
            (
                "chat_client_config.yml",
                open(
                    "tests/testing_data/yml_training_files/chat_client_config.yml", "rb"
                ),
            ),
        ),
        (
            "training_files",
            (
                "config.yml",
                open("tests/testing_data/yml_training_files/config.yml", "rb"),
            ),
        ),
        (
            "training_files",
            (
                "multiflow_stories.yml",
                open(
                    "tests/testing_data/yml_training_files/multiflow_stories.yml", "rb"
                ),
            ),
        ),
    )
    mock_is_limit_exceeded.return_value = False
    response = client.post(
        f"/api/bot/{pytest.bot}/upload",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=files,
    )
    actual = response.json()
    assert actual["message"] == "Upload in progress! Check logs."
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]
    complete_end_to_end_event_execution(
        pytest.bot, "test_user", EventClass.data_importer
    )

    response = client.get(
        f"/api/bot/{pytest.bot}/importer/logs?start_idx=0&page_size=10",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["success"]
    assert actual["error_code"] == 0
    assert set(actual["data"]["logs"][0]["files_received"]) == {
        "rules",
        "stories",
        "nlu",
        "domain",
        "config",
        "actions",
        "chat_client_config",
        "multiflow_stories",
    }


def test_get_editable_config():
    response = client.get(
        f"/api/bot/{pytest.bot}/config/properties",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert not DeepDiff(
        actual["data"],
        {
            "nlu_confidence_threshold": 0.75,
            "action_fallback": "action_small_talk",
            "action_fallback_threshold": 0.3,
            "ted_epochs": 5,
            "nlu_epochs": 5,
            "response_epochs": 5,
        },
        ignore_order=True,
    )


def test_set_epoch_and_fallback():
    request = {
        "nlu_epochs": 200,
        "response_epochs": 100,
        "ted_epochs": 150,
        "nlu_confidence_threshold": 0.7,
        "action_fallback_threshold": 0.3,
        "action_fallback": "action_default_fallback",
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/response/utter_default",
        json={"data": "Sorry I didnt get that. Can you rephrase?"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Response added!"

    response = client.put(
        f"/api/bot/{pytest.bot}/config/properties",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=request,
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Config saved"


def test_get_config_all():
    response = client.get(
        f"/api/bot/{pytest.bot}/config/properties",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]


def test_set_epoch_and_fallback_modify_action_only():
    request = {"nlu_confidence_threshold": 0.3, "action_fallback": "utter_default"}
    response = client.put(
        f"/api/bot/{pytest.bot}/config/properties",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=request,
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Config saved"


def test_set_epoch_and_fallback_empty_pipeline_and_policies():
    request = {"nlu_confidence_threshold": 20}
    response = client.put(
        f"/api/bot/{pytest.bot}/config/properties",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=request,
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "nlu_confidence_threshold"],
            "msg": "Please choose a threshold between 0.3 and 0.9",
            "type": "value_error",
        }
    ]


def test_set_epoch_and_fallback_empty_request():
    response = client.put(
        f"/api/bot/{pytest.bot}/config/properties",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "At least one field is required"


def test_set_epoch_and_fallback_negative_epochs():
    response = client.put(
        f"/api/bot/{pytest.bot}/config/properties",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"nlu_epochs": 0},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "nlu_epochs"],
            "msg": "Choose a positive number as epochs",
            "type": "value_error",
        }
    ]

    response = client.put(
        f"/api/bot/{pytest.bot}/config/properties",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"response_epochs": -1, "ted_epochs": 0, "nlu_epochs": 200},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"][0] == {
        "loc": ["body", "response_epochs"],
        "msg": "Choose a positive number as epochs",
        "type": "value_error",
    }
    assert actual["message"][1] == {
        "loc": ["body", "ted_epochs"],
        "msg": "Choose a positive number as epochs",
        "type": "value_error",
    }


def test_set_epoch_and_fallback_max_epochs():
    epoch_max_limit = Utility.environment["model"]["config_properties"][
        "epoch_max_limit"
    ]
    response = client.put(
        f"/api/bot/{pytest.bot}/config/properties",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"nlu_epochs": epoch_max_limit + 1},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "nlu_epochs"],
            "msg": f"Please choose a epoch between 1 and {epoch_max_limit}",
            "type": "value_error",
        }
    ]

    response = client.put(
        f"/api/bot/{pytest.bot}/config/properties",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={
            "response_epochs": -1,
            "ted_epochs": epoch_max_limit + 1,
            "nlu_epochs": 200,
        },
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"][0] == {
        "loc": ["body", "response_epochs"],
        "msg": "Choose a positive number as epochs",
        "type": "value_error",
    }
    assert actual["message"][1] == {
        "loc": ["body", "ted_epochs"],
        "msg": f"Please choose a epoch between 1 and {epoch_max_limit}",
        "type": "value_error",
    }


def test_get_synonyms():
    response = client.get(
        f"/api/bot/{pytest.bot}/entity/synonyms",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert "data" in actual
    assert len(actual["data"]) == 0
    assert actual["success"]
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])


def test_add_synonym_values():
    response = client.post(
        f"/api/bot/{pytest.bot}/entity/synonym",
        json={"data": "bot_add"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Synonym added!"
    assert actual["data"]["_id"]

    response = client.post(
        f"/api/bot/{pytest.bot}/entity/synonym/bot_add/values",
        json={"value": ["any"]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Synonym values added!"
    assert all(
        key in item.keys() for item in actual["data"] for key in ["_id", "value"]
    )

    response = client.post(
        f"/api/bot/{pytest.bot}/entity/synonym/bot_add/value",
        json={"data": "any1"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Synonym value added!"
    assert actual["data"]["_id"]

    response = client.get(
        f"/api/bot/{pytest.bot}/entity/synonym/bot_add/values",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert all(item["value"] in ["any", "any1"] for item in actual["data"])
    assert all(
        key in item.keys()
        for item in actual["data"]
        for key in ["_id", "synonym", "value"]
    )


def test_get_specific_synonym_values():
    response = client.get(
        f"/api/bot/{pytest.bot}/entity/synonym/bot_add/values",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert len(actual["data"]) == 2


def test_add_synonyms_duplicate():
    response = client.post(
        f"/api/bot/{pytest.bot}/entity/synonym/bot_add/values",
        json={"value": ["any"]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Synonym value already exists"


def test_add_synonyms_value_empty():
    response = client.post(
        f"/api/bot/{pytest.bot}/entity/synonym/bot_add/values",
        json={"value": []},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"][0]["msg"] == "value field cannot be empty"


def test_add_synonyms_empty():
    response = client.post(
        f"/api/bot/{pytest.bot}/entity/synonym/%20/values",
        json={"value": ["h"]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Synonym name cannot be an empty!"


def test_edit_synonyms():
    response = client.get(
        f"/api/bot/{pytest.bot}/entity/synonym/bot_add/values",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    response = client.put(
        f"/api/bot/{pytest.bot}/entity/synonym/bot_add/value/{actual['data'][0]['_id']}",
        json={"data": "any4"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Synonym value updated!"

    response = client.get(
        f"/api/bot/{pytest.bot}/entity/synonym/bot_add/values",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert len(actual["data"])
    assert any(item["value"] == "any4" for item in actual["data"])


def test_delete_synonym_one_value():
    response = client.get(
        f"/api/bot/{pytest.bot}/entity/synonym/bot_add/values",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()

    response = client.delete(
        f"/api/bot/{pytest.bot}/entity/synonym/bot_add/value/{actual['data'][0]['_id']}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Synonym value removed!"

    response = client.get(
        f"/api/bot/{pytest.bot}/entity/synonym/bot_add/values",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert len(actual["data"]) == 1


def test_delete_synonym():
    response = client.get(
        f"/api/bot/{pytest.bot}/entity/synonyms",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["success"]
    assert all(
        key in item.keys() for item in actual["data"] for key in ["_id", "synonym"]
    )

    synonym_id = actual["data"][0]["_id"]
    synonym_name = actual["data"][0]["synonym"]
    response = client.delete(
        f"/api/bot/{pytest.bot}/entity/synonym/{synonym_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Synonym removed!"

    response = client.get(
        f"/api/bot/{pytest.bot}/entity/synonyms",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["data"] == []

    response = client.get(
        f"/api/bot/{pytest.bot}/entity/synonym/{synonym_name}/values",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["data"] == []


def test_add_synonyms_empty_value_element():
    response = client.post(
        f"/api/bot/{pytest.bot}/entity/synonym/bot_add/values",
        json={"value": ["df", ""]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"][0]["msg"] == "value cannot be an empty string"


def test_get_training_data_count(monkeypatch):
    def _mock_training_data_count(*args, **kwargs):
        return {
            "intents": [{"name": "greet", "count": 5}, {"name": "affirm", "count": 3}],
            "utterances": [
                {"name": "utter_greet", "count": 4},
                {"name": "utter_affirm", "count": 11},
            ],
        }

    monkeypatch.setattr(
        MongoProcessor, "get_training_data_count", _mock_training_data_count
    )
    response = client.get(
        f"/api/bot/{pytest.bot}/data/count",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] == _mock_training_data_count()


@responses.activate
def test_chat(monkeypatch):
    monkeypatch.setitem(
        Utility.environment["model"]["agent"], "url", "http://localhost"
    )
    chat_json = {"data": "Hi"}
    responses.add(
        responses.POST,
        f"http://localhost/api/bot/{pytest.bot}/chat",
        status=200,
        match=[responses.matchers.json_params_matcher(chat_json)],
        json={
            "success": True,
            "error_code": 0,
            "data": {"response": [{"bot": "Hi"}]},
            "message": None,
        },
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/chat",
        json=chat_json,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["response"]


@responses.activate
def test_chat_user(monkeypatch):
    monkeypatch.setitem(
        Utility.environment["model"]["agent"], "url", "http://localhost"
    )
    chat_json = {"data": "Hi"}
    responses.add(
        responses.POST,
        f"http://localhost/api/bot/{pytest.bot}/chat",
        status=200,
        match=[responses.matchers.json_params_matcher(chat_json)],
        json={
            "success": True,
            "error_code": 0,
            "data": {"response": [{"bot": "Hi"}]},
            "message": None,
        },
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/chat",
        json=chat_json,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["response"]


@responses.activate
def test_chat_with_data_empty(monkeypatch):
    monkeypatch.setitem(
        Utility.environment["model"]["agent"], "url", "http://localhost"
    )
    chat_json = {"data": ""}
    response = client.post(
        f"/api/bot/{pytest.bot}/chat",
        json=chat_json,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["message"] == "data cannot be empty"
    assert actual["error_code"] == 422
    assert actual["data"] is None


@responses.activate
def test_chat_augment_user_with_data_empty(monkeypatch):
    monkeypatch.setitem(
        Utility.environment["model"]["agent"], "url", "http://localhost"
    )
    chat_json = {"data": ""}
    response = client.post(
        f"/api/bot/{pytest.bot}/chat/testUser",
        json=chat_json,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["message"] == "data cannot be empty"
    assert actual["error_code"] == 422
    assert actual["data"] is None


@responses.activate
def test_chat_augment_user(monkeypatch):
    monkeypatch.setitem(
        Utility.environment["model"]["agent"], "url", "http://localhost"
    )
    chat_json = {"data": "Hi"}
    responses.add(
        responses.POST,
        f"http://localhost/api/bot/{pytest.bot}/chat",
        status=200,
        match=[responses.matchers.json_params_matcher(chat_json)],
        json={
            "success": True,
            "error_code": 0,
            "data": {"response": [{"bot": "Hi"}]},
            "message": None,
        },
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/chat/testUser",
        json=chat_json,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["response"]


def test_get_client_config():
    response = client.get(
        f"/api/bot/{pytest.bot}/chat/client/config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]
    assert actual["data"]["whitelist"] == ["*"]


def test_get_client_config_url():
    response = client.get(
        f"/api/bot/{pytest.bot}/chat/client/config/url",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]
    pytest.url = actual["data"]


@responses.activate
def test_refresh_token(monkeypatch):
    response = client.get(pytest.url)
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]
    assert actual["data"]["headers"]["authorization"]["token_type"] == "Bearer"
    ate = actual["data"]["headers"]["authorization"]["access_token_expiry"]
    rte = actual["data"]["headers"]["authorization"]["refresh_token_expiry"]
    assert (
            31
            >= round(
        (datetime.utcfromtimestamp(ate) - datetime.utcnow()).total_seconds() / 60
    )
            >= 29
    )
    assert (
            61
            >= round(
        (datetime.utcfromtimestamp(rte) - datetime.utcnow()).total_seconds() / 60
    )
            >= 59
    )
    refresh_token = actual["data"]["headers"]["authorization"]["refresh_token"]

    response = client.get(
        f"/api/auth/{pytest.bot}/token/refresh",
        headers={"Authorization": pytest.token_type + " " + refresh_token},
    )
    actual = response.json()
    # assert 1 == 0
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["access_token"]
    assert actual["data"]["token_type"]
    assert actual["data"]["refresh_token"]
    assert (
            actual["message"]
            == "This token will be shown only once. Please copy this somewhere safe."
               "It is your responsibility to keep the token secret. "
               "If leaked, others may have access to your system."
    )
    new_token = actual["data"]["access_token"]
    token_type = actual["data"]["token_type"]

    monkeypatch.setitem(
        Utility.environment["model"]["agent"], "url", "http://localhost"
    )
    responses.add(
        responses.POST,
        f"http://localhost/api/bot/{pytest.bot}/chat",
        status=200,
        json={
            "success": True,
            "error_code": 0,
            "data": {"response": [{"bot": "Hi"}]},
            "message": None,
        },
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/chat",
        json={"data": "Hi"},
        headers={"Authorization": token_type + " " + new_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["response"]

    response = client.post(
        f"/api/bot/{pytest.bot}/metric/user/logs/user_metrics",
        json={"data": {"location": "india"}},
        headers={"Authorization": token_type + " " + new_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0

    response = client.get(
        f"/api/bot/{pytest.bot}/model/reload",
        headers={"Authorization": token_type + " " + new_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_refresh_token_from_dynamic_token():
    response = client.get(pytest.url)
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]
    chat_token = actual["data"]["headers"]["authorization"]["access_token"]

    response = client.get(
        f"/api/auth/{pytest.bot}/token/refresh",
        headers={"Authorization": pytest.token_type + " " + chat_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Access denied for this endpoint"
    assert not actual["data"]


def test_trigger_api_server_using_refresh_token():
    response = client.get(pytest.url)
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]
    token_type = actual["data"]["headers"]["authorization"]["token_type"]
    refresh_token = actual["data"]["headers"]["authorization"]["refresh_token"]

    response = client.get(
        f"/api/bot/{pytest.bot}/model/reload",
        headers={"Authorization": token_type + " " + refresh_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Access denied for this endpoint"
    assert not actual["data"]


def test_get_client_config_using_invalid_uid():
    response = client.get(
        f"/api/bot/{pytest.bot}/chat/client/config/ecmkfnufjsufysfbksjnfaksn"
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert not actual["data"]


def test_save_client_config():
    config_path = "./template/chat-client/default-config.json"
    config = json.load(open(config_path))
    config["headers"] = {}
    config["headers"]["X-USER"] = "kairon-user"
    response = client.post(
        f"/api/bot/{pytest.bot}/chat/client/config",
        json={"data": config},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Config saved"

    config = ChatClientConfig.objects(bot=pytest.bot).get()
    assert config.config
    assert config.config["headers"]["X-USER"]
    assert not config.config["headers"].get("authorization")


@responses.activate
def test_get_client_config_using_uid(monkeypatch):
    monkeypatch.setitem(
        Utility.environment["model"]["agent"], "url", "http://localhost"
    )
    chat_json = {"data": "Hi"}
    responses.add(
        responses.POST,
        f"http://localhost/api/bot/{pytest.bot}/chat",
        status=200,
        match=[responses.matchers.json_params_matcher(chat_json)],
        json={
            "success": True,
            "error_code": 0,
            "data": None,
            "message": "Bot has not been trained yet!",
        },
    )
    response = client.get(pytest.url)
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]
    assert None == actual.get("data").get("whitelist")

    access_token = actual["data"]["headers"]["authorization"]["access_token"]
    token_type = actual["data"]["headers"]["authorization"]["token_type"]
    response = client.post(
        f"/api/bot/{pytest.bot}/chat",
        json=chat_json,
        headers={"Authorization": f"{token_type} {access_token}", "X-USER": "hacker"},
    )
    actual = response.json()
    assert actual["message"] == "Bot has not been trained yet!"

    response = client.get(
        f"/api/bot/{pytest.bot}/intents",
        headers={"Authorization": f"{token_type} {access_token}", "X-USER": "hacker"},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert not actual["success"]
    assert actual["message"] == "Access denied for this endpoint"


@responses.activate
def test_get_client_config_refresh(monkeypatch):
    monkeypatch.setitem(
        Utility.environment["model"]["agent"], "url", "http://localhost"
    )
    chat_json = {"data": "Hi"}
    responses.add(
        responses.POST,
        f"http://localhost/api/bot/{pytest.bot}/chat",
        status=200,
        match=[responses.matchers.json_params_matcher(chat_json)],
        json={
            "success": True,
            "error_code": 0,
            "data": None,
            "message": "Bot has not been trained yet!",
        },
    )
    response = client.get(pytest.url)
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]
    assert actual["data"]["headers"]["X-USER"] == "kairon-user"
    assert None == actual.get("data").get("whitelist")

    access_token = actual["data"]["headers"]["authorization"]["access_token"]
    token_type = actual["data"]["headers"]["authorization"]["token_type"]
    user = actual["data"]["headers"]["X-USER"]
    response = client.post(
        f"/api/bot/{pytest.bot}/chat",
        json=chat_json,
        headers={"Authorization": f"{token_type} {access_token}", "X-USER": user},
    )
    actual = response.json()
    assert actual["message"] == "Bot has not been trained yet!"

    response = client.get(
        f"/api/bot/{pytest.bot}/intents",
        headers={"Authorization": f"{token_type} {access_token}", "X-USER": user},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert not actual["success"]
    assert actual["message"] == "Access denied for this endpoint"


def test_get_chat_client_config_multilingual_enabled_no_bots_enabled():
    from bson import ObjectId

    response = client.get(
        f"/api/bot/{pytest.bot}/chat/client/config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    actual["data"]["multilingual"]["enable"] = True
    actual["data"]["multilingual"]["bots"] = [
        {"id": ObjectId().__str__(), "is_enabled": True}
    ]

    response = client.post(
        f"/api/bot/{pytest.bot}/chat/client/config",
        json={"data": actual["data"]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Config saved"

    response = client.get(pytest.url)
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert not actual["data"]
    assert actual["message"] == "Bot is disabled. Please use a valid bot."

    response = client.get(
        f"/api/bot/{pytest.bot}/chat/client/config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0


def test_save_chat_client_config_enable_multilingual_bots():
    AccountProcessor.add_bot(
        name="demo-hi",
        account=pytest.account,
        user="integ1@gmail.com",
        metadata={
            "language": "hi",
            "source_bot_id": pytest.bot,
            "source_language": "en",
        },
    )
    response = client.get(
        f"/api/bot/{pytest.bot}/chat/client/config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["multilingual"]["enable"]
    actual["data"]["multilingual"]["bots"][0]["is_enabled"] = True

    response = client.post(
        f"/api/bot/{pytest.bot}/chat/client/config",
        json={"data": actual["data"]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Config saved"


def test_save_chat_client_config_enable_multilingual_bots_no_bot_enabled():
    response = client.get(
        f"/api/bot/{pytest.bot}/chat/client/config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["multilingual"]["enable"]
    actual["data"]["multilingual"]["bots"][0]["is_enabled"] = False

    response = client.post(
        f"/api/bot/{pytest.bot}/chat/client/config",
        json={"data": actual["data"]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "At least one bot should be enabled!"


def test_get_chat_client_config_multilingual_enabled():
    response = client.get(pytest.url)
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]["multilingual"]["bots"]) == 1
    assert actual["data"]["multilingual"]["bots"][0]["is_enabled"]

    AccountProcessor.add_bot(
        name="demo-mr",
        account=pytest.account,
        user="integ1@gmail.com",
        metadata={
            "language": "hi",
            "source_bot_id": pytest.bot,
            "source_language": "en",
        },
    )

    response = client.get(pytest.url)
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]["multilingual"]["bots"]) == 1
    assert actual["data"]["multilingual"]["bots"][0]["is_enabled"]

    response = client.get(
        f"/api/bot/{pytest.bot}/chat/client/config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]["multilingual"]["bots"]) == 3
    assert actual["data"]["multilingual"]["bots"][0]["is_enabled"]
    assert not actual["data"]["multilingual"]["bots"][1]["is_enabled"]


def test_get_metering():
    response = client.get(
        f"/api/bot/{pytest.bot}/metric/test_chat",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual == {"success": True, "message": None, "data": 0, "error_code": 0}
    response = client.get(
        f"/api/bot/{pytest.bot}/metric/prod_chat",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual == {"success": True, "message": None, "data": 0, "error_code": 0}


def test_add_story_with_no_type():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_add_story_with_no_type",
            "type": "STORY",
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
    assert actual["message"] == "Flow added successfully"

    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_path",
            "type": "STORY",
            "steps": [
                {"name": "test_greet", "type": "INTENT"},
                {"name": "utter_test_greet", "type": "ACTION"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Flow added successfully"
    assert actual["success"]
    assert actual["error_code"] == 0


def test_get_stories_another_bot():
    response = client.get(
        f"/api/bot/{pytest.bot}/stories",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]
    assert actual["data"][0]["template_type"] == "CUSTOM"
    assert actual["data"][1]["template_type"] == "CUSTOM"
    assert actual["data"][8]["template_type"] == "CUSTOM"
    assert actual["data"][8]["name"] == "test_add_story_with_no_type"
    assert actual["data"][9]["template_type"] == "CUSTOM"
    assert actual["data"][9]["name"] == "test_path"


def test_add_regex_invalid():
    response = client.post(
        f"/api/bot/{pytest.bot}/regex",
        json={"name": "bot_add", "pattern": "[0-9]++"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "invalid regular expression"


def test_add_regex_empty_name():
    response = client.post(
        f"/api/bot/{pytest.bot}/regex",
        json={"name": "", "pattern": "q"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"][0]["msg"] == "Regex name cannot be empty or a blank space"


def test_add_regex_empty_pattern():
    response = client.post(
        f"/api/bot/{pytest.bot}/regex",
        json={"name": "b", "pattern": ""},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert (
            actual["message"][0]["msg"] == "Regex pattern cannot be empty or a blank space"
    )


def test_add_regex_():
    response = client.post(
        f"/api/bot/{pytest.bot}/regex",
        json={"name": "b", "pattern": "bb"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Regex pattern added successfully!"


def test_get_regex():
    response = client.get(
        f"/api/bot/{pytest.bot}/regex",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert "data" in actual
    assert len(actual["data"]) == 1
    assert actual["success"]
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])
    assert "b" in actual["data"][0].values()
    assert "bb" in actual["data"][0].values()


def test_edit_regex():
    response = client.put(
        f"/api/bot/{pytest.bot}/regex",
        json={"name": "b", "pattern": "bbb"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Regex pattern modified successfully!"

    response = client.get(
        f"/api/bot/{pytest.bot}/regex",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert "data" in actual
    assert len(actual["data"]) == 1
    assert actual["success"]
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])
    assert "b" in actual["data"][0].values()
    assert "bbb" in actual["data"][0].values()


def test_delete_regex():
    response = client.delete(
        f"/api/bot/{pytest.bot}/regex/b",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Regex pattern deleted!"

    response = client.get(
        f"/api/bot/{pytest.bot}/regex",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert "data" in actual
    assert len(actual["data"]) == 0
    assert actual["success"]
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])


def test_add_and_move_training_examples_to_different_intent():
    response = client.post(
        f"/api/bot/{pytest.bot}/training_examples/greet",
        json={"data": ["hey, there [bot](bot)!!"]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"][0]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] is None
    response = client.get(
        f"/api/bot/{pytest.bot}/training_examples/greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert len(actual["data"]) == 7

    response = client.post(
        f"/api/bot/{pytest.bot}/intents",
        json={"data": "test_add_and_move"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Intent added successfully!"

    response = client.post(
        f"/api/bot/{pytest.bot}/training_examples/move/test_add_and_move",
        json={
            "data": [
                "this will be moved",
                "this is a new [example](example)",
                " ",
                "",
                "hey, there [bot](bot)!!",
            ]
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"][0]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] is None
    response = client.get(
        f"/api/bot/{pytest.bot}/training_examples/test_add_and_move",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert len(actual["data"]) == 3


def test_add_and_move_training_examples_to_different_intent_not_exists():
    response = client.post(
        f"/api/bot/{pytest.bot}/training_examples/move/greeting",
        json={
            "data": [
                "this will be moved",
                "this is a new [example](example)",
                " ",
                "",
                "hey, there [bot](bot)!!",
            ]
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Intent does not exists"


def test_get_lookup_tables():
    response = client.get(
        f"/api/bot/{pytest.bot}/lookups",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert "data" in actual
    assert len(actual["data"]) == 0
    assert actual["success"]
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])


def test_add_lookup_tables():
    response = client.post(
        f"/api/bot/{pytest.bot}/lookup",
        json={"data": "country"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Lookup added!"
    assert actual["data"]["_id"]

    response = client.post(
        f"/api/bot/{pytest.bot}/lookup/country/values",
        json={"value": ["india", "australia"]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Lookup values added!"
    assert all(
        key in item.keys() for item in actual["data"] for key in ["_id", "value"]
    )

    response = client.post(
        f"/api/bot/{pytest.bot}/lookup",
        json={"data": "number"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Lookup added!"
    assert actual["data"]["_id"]

    response = client.post(
        f"/api/bot/{pytest.bot}/lookup/number/values",
        json={"value": ["one", "two"]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Lookup values added!"

    response = client.get(
        f"/api/bot/{pytest.bot}/lookup/number/values",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert all(item["value"] in ["one", "two"] for item in actual["data"])
    assert all(
        key in item.keys()
        for item in actual["data"]
        for key in ["_id", "lookup", "value"]
    )


def test_get_lookup_table_values():
    response = client.get(
        f"/api/bot/{pytest.bot}/lookup/country/values",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert len(actual["data"]) == 2


def test_add_lookup_duplicate():
    response = client.post(
        f"/api/bot/{pytest.bot}/lookup/country/values",
        json={"value": ["india"]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Lookup value already exists"


def test_add_lookup_empty():
    response = client.post(
        f"/api/bot/{pytest.bot}/lookup/country/values",
        json={"value": []},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"][0]["msg"] == "value field cannot be empty"


def test_edit_lookup():
    response = client.get(
        f"/api/bot/{pytest.bot}/lookup/country/values",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    response = client.put(
        f"/api/bot/{pytest.bot}/lookup/country/value/{actual['data'][0]['_id']}",
        json={"data": "japan"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Lookup value updated!"


def test_add_lookup_empty_name():
    response = client.post(
        f"/api/bot/{pytest.bot}/lookup/%20/values",
        json={"value": ["h"]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Lookup cannot be an empty string"


def test_delete_lookup_one_value():
    response = client.get(
        f"/api/bot/{pytest.bot}/lookup/country/values",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    response = client.delete(
        f"/api/bot/{pytest.bot}/lookup/country/value/{actual['data'][0]['_id']}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Lookup value removed!"

    response = client.get(
        f"/api/bot/{pytest.bot}/lookup/country/values",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert len(actual["data"]) == 1


def test_delete_lookup():
    response = client.get(
        f"/api/bot/{pytest.bot}/lookups",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0

    lookup = actual["data"][0]

    response = client.delete(
        f"/api/bot/{pytest.bot}/lookup/{lookup['_id']}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Lookup removed!"

    response = client.get(
        f"/api/bot/{pytest.bot}/lookups",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert len(actual["data"]) == 1


def test_add_lookup_empty_value_element():
    response = client.post(
        f"/api/bot/{pytest.bot}/lookup/country/values",
        json={"value": ["df", ""]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert (
            actual["message"][0]["msg"] == "lookup value cannot be empty or a blank space"
    )


def test_list_form_none_exists():
    response = client.get(
        f"/api/bot/{pytest.bot}/forms",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] == []


def test_add_form_invalid_parameters():
    path = [
        {
            "ask_questions": [],
            "slot": "name",
            "slot_set": {"type": "custom", "value": "Mahesh"},
        },
        {
            "ask_questions": ["seats required?"],
            "slot": "num_people",
            "slot_set": {"type": "current", "value": 10},
        },
    ]
    request = {"name": "restaurant_form", "settings": path}
    response = client.post(
        f"/api/bot/{pytest.bot}/forms",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "settings", 0, "ask_questions"],
            "msg": "Questions cannot be empty or contain spaces",
            "type": "value_error",
        }
    ]

    path = [
        {
            "ask_questions": [" "],
            "slot": "name",
            "slot_set": {"type": "custom", "value": "Mahesh"},
        },
        {
            "ask_questions": ["seats required?"],
            "slot": "num_people",
            "slot_set": {"type": "current", "value": 10},
        },
    ]
    request = {"name": "restaurant_form", "settings": path}
    response = client.post(
        f"/api/bot/{pytest.bot}/forms",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "settings", 0, "ask_questions"],
            "msg": "Questions cannot be empty or contain spaces",
            "type": "value_error",
        }
    ]

    path = [
        {
            "ask_questions": ["name ?"],
            "slot": "",
            "slot_set": {"type": "custom", "value": "Mahesh"},
        },
        {
            "ask_questions": ["seats required?"],
            "slot": "num_people",
            "slot_set": {"type": "current", "value": 10},
        },
    ]
    request = {"name": "restaurant_form", "settings": path}
    response = client.post(
        f"/api/bot/{pytest.bot}/forms",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "settings", 0, "slot"],
            "msg": "Slot is required",
            "type": "value_error",
        }
    ]


def test_get_slot_mapping_empty():
    response = client.get(
        f"/api/bot/{pytest.bot}/slots/mapping",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["data"] == []


def test_add_slot_mapping():
    response = client.post(
        f"/api/bot/{pytest.bot}/slots",
        json={"name": "name", "type": "text"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["message"] == "Slot added successfully!"
    assert actual["success"]
    assert actual["error_code"] == 0
    response = client.post(
        f"/api/bot/{pytest.bot}/slots/mapping",
        json={
            "slot": "name",
            "mapping": {"type": "from_text", "value": "user", "entity": "name"},
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot mapping added"
    assert actual["success"]
    assert actual["error_code"] == 0


def test_add_empty_slot_mapping():
    response = client.post(
        f"/api/bot/{pytest.bot}/slots/mapping",
        json={"slot": "num_people", "mapping": {}},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert not actual["success"]
    assert actual["message"] == [
        {
            "loc": ["body", "mapping", 'type'],
            "msg": "field required",
            "type": "value_error.missing",
        }
    ]

    response = client.post(
        f"/api/bot/{pytest.bot}/slots/mapping",
        json={"slot": "num_people",
              "mapping": {"type": "from_text", "conditions": [{"requested_slot": "num_people"}]}},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert not actual["success"]
    assert actual["message"] == [{'loc': ['body', 'mapping', 'conditions', 0],
                                  'msg': 'active_loop is required to add requested_slot as condition!',
                                  'type': 'value_error'}]


def test_add_form_with_invalid_slot_set_type():
    path = [
        {
            "ask_questions": ["what is your name?", "name?"],
            "slot": "name",
            "slot_set": {"type": "invalid_type", "value": "Mahesh"},
        },
        {
            "ask_questions": ["seats required?"],
            "slot": "num_people",
            "slot_set": {"type": "current", "value": 10},
        },
    ]
    request = {"name": "restaurant_form", "settings": path}
    response = client.post(
        f"/api/bot/{pytest.bot}/forms",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert str(actual["message"]).__contains__(
        "value is not a valid enumeration member"
    )


def test_add_form():
    response = client.post(
        f"/api/bot/{pytest.bot}/slots",
        json={"name": "num_people", "type": "float"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot added successfully!"
    assert actual["success"]
    response = client.post(
        f"/api/bot/{pytest.bot}/slots/mapping",
        json={
            "slot": "num_people",
            "mapping":
                {
                    "type": "from_entity",
                    "intent": ["inform", "request_restaurant"],
                    "entity": "number",
                }
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot mapping added"
    assert actual["success"]

    response = client.post(
        f"/api/bot/{pytest.bot}/slots",
        json={"name": "cuisine", "type": "text"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot added successfully!"
    assert actual["success"]
    response = client.post(
        f"/api/bot/{pytest.bot}/slots/mapping",
        json={
            "slot": "cuisine",
            "mapping": {"type": "from_entity", "entity": "cuisine"},
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot mapping added"
    assert actual["success"]

    response = client.post(
        f"/api/bot/{pytest.bot}/slots",
        json={"name": "outdoor_seating", "type": "text"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot added successfully!"
    assert actual["success"]

    response = client.post(
        f"/api/bot/{pytest.bot}/slots/mapping",
        json={
            "slot": "outdoor_seating",
            "mapping":
                {"type": "from_text", "not_intent": ["affirm"],
                 "conditions": [{"active_loop": "booking", "requested_slot": "outdoor_seating"}]}
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot mapping added"
    assert actual["success"]

    response = client.post(
        f"/api/bot/{pytest.bot}/slots",
        json={"name": "preferences", "type": "text"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot added successfully!"
    assert actual["success"]
    response = client.post(
        f"/api/bot/{pytest.bot}/slots/mapping",
        json={
            "slot": "preferences",
            "mapping":
                {"type": "from_text", "not_intent": ["affirm"],
                 "conditions": [{"active_loop": "booking", "requested_slot": "preferences"}]}
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot mapping added"
    assert actual["success"]

    response = client.post(
        f"/api/bot/{pytest.bot}/slots",
        json={"name": "feedback", "type": "text"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot added successfully!"
    assert actual["success"]
    response = client.post(
        f"/api/bot/{pytest.bot}/slots/mapping",
        json={
            "slot": "feedback",
            "mapping":
                {"type": "from_entity", "entity": "feedback"}
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot mapping added"
    assert actual["success"]

    path = [
        {
            "ask_questions": ["please give us your name?"],
            "slot": "name",
            "slot_set": {"type": "custom", "value": "Mahesh"},
        },
        {
            "ask_questions": ["seats required?"],
            "slot": "num_people",
            "slot_set": {"type": "current", "value": 10},
        },
        {
            "ask_questions": ["type of cuisine?"],
            "slot": "cuisine",
            "slot_set": {"type": "current", "value": "Indian Cuisine"},
        },
        {"ask_questions": ["outdoor seating required?"], "slot": "outdoor_seating"},
        {
            "ask_questions": ["any preferences?"],
            "slot": "preferences",
            "slot_set": {"type": "slot", "value": "preferences"},
        },
        {
            "ask_questions": ["Please give your feedback on your experience so far"],
            "slot": "feedback",
            "slot_set": {"type": "custom", "value": "Very Nice!"},
        },
    ]
    request = {"name": "restaurant_form", "settings": path}
    response = client.post(
        f"/api/bot/{pytest.bot}/forms",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Form added"


def test_add_form_with_any_slot():
    response = client.post(
        f"/api/bot/{pytest.bot}/slots",
        json={"name": "user_feedback", "type": "any"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot added successfully!"
    assert actual["success"]
    response = client.post(
        f"/api/bot/{pytest.bot}/slots/mapping",
        json={
            "slot": "user_feedback",
            "mapping":
                {"type": "from_text"},
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot mapping added"
    assert actual["success"]
    response = client.post(
        f"/api/bot/{pytest.bot}/slots/mapping",
        json={
            "slot": "user_feedback",
            "mapping":
                {"type": "from_entity", "entity": "user_feedback"},
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot mapping added"
    assert actual["success"]
    path = [
        {
            "ask_questions": ["please give us your name?"],
            "slot": "name",
            "slot_set": {"type": "custom", "value": "Mahesh"},
        },
        {
            "ask_questions": ["seats required?"],
            "slot": "num_people",
            "slot_set": {"type": "current", "value": 10},
        },
        {
            "ask_questions": ["type of cuisine?"],
            "slot": "cuisine",
            "slot_set": {"type": "current", "value": "Indian Cuisine"},
        },
        {"ask_questions": ["outdoor seating required?"], "slot": "outdoor_seating"},
        {
            "ask_questions": ["any preferences?"],
            "slot": "preferences",
            "slot_set": {"type": "slot", "value": "preferences"},
        },
        {
            "ask_questions": ["Please give your feedback on your experience so far"],
            "slot": "user_feedback",
            "slot_set": {"type": "custom", "value": "Very Nice!"},
        }
    ]
    request = {"name": "restaurant_booking_form", "settings": path}
    response = client.post(
        f"/api/bot/{pytest.bot}/forms",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "form will not accept any type slots: {'user_feedback'}"


def test_add_utterance_to_form():
    response = client.post(
        f"/api/bot/{pytest.bot}/response/utter_ask_restaurant_form_num_people?form_attached=restaurant_form",
        json={"data": "num people?"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Response added!"


def test_delete_utterance_in_form():
    response = client.get(
        f"/api/bot/{pytest.bot}/response/utter_ask_restaurant_form_num_people",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"]
    assert actual["success"]
    assert actual["error_code"] == 0
    id = actual["data"][0]["_id"]
    response = client.delete(
        f"/api/bot/{pytest.bot}/response/{id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Response removed!"


def test_create_rule_with_form_invalid_step():
    steps = [
        {"name": None, "type": "INTENT"},
        {"name": "know_user", "type": "FORM_ACTION"},
        {"name": "know_user", "type": "FORM_START"},
        {"type": "FORM_END"},
        {"name": "utter_submit", "type": "BOT"},
    ]
    story_dict = {
        "name": "activate form",
        "steps": steps,
        "type": "RULE",
        "template_type": "CUSTOM",
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json=story_dict,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == [
        {
            "loc": ["body", "steps"],
            "msg": "Only FORM_END step type can have empty name",
            "type": "value_error",
        }
    ]
    assert not actual["data"]
    assert not actual["success"]
    assert actual["error_code"] == 422

    steps = [
        {"name": "greet", "type": "INTENT"},
        {"name": "   ", "type": "FORM_ACTION"},
        {"name": "know_user", "type": "FORM_START"},
        {"type": "FORM_END"},
        {"name": "utter_submit", "type": "BOT"},
    ]
    story_dict = {
        "name": "activate form",
        "steps": steps,
        "type": "RULE",
        "template_type": "CUSTOM",
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json=story_dict,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == [
        {
            "loc": ["body", "steps"],
            "msg": "Only FORM_END step type can have empty name",
            "type": "value_error",
        }
    ]
    assert not actual["data"]
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_create_rule_with_form():
    steps = [
        {"name": "greet", "type": "INTENT"},
        {"name": "know_user", "type": "FORM_ACTION"},
        {"name": "know_user", "type": "FORM_START"},
        {"type": "FORM_END"},
        {"name": "utter_submit", "type": "BOT"},
    ]
    story_dict = {
        "name": "activate form",
        "steps": steps,
        "type": "RULE",
        "template_type": "CUSTOM",
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json=story_dict,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Flow added successfully"
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0

    response = client.get(
        f"/api/bot/{pytest.bot}/stories",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0


def test_create_stories_with_form():
    steps = [
        {"name": "greet", "type": "INTENT"},
        {"name": "know_user", "type": "FORM_ACTION"},
        {"name": "know_user", "type": "FORM_START"},
        {"name": "deny", "type": "INTENT"},
        {"name": "utter_ask_continue", "type": "BOT"},
        {"name": "affirm", "type": "INTENT"},
        {"type": "FORM_END"},
        {"name": "utter_submit", "type": "BOT"},
    ]
    story_dict = {
        "name": "stop form + continue",
        "steps": steps,
        "type": "STORY",
        "template_type": "CUSTOM",
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json=story_dict,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Flow added successfully"
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0

    response = client.get(
        f"/api/bot/{pytest.bot}/stories",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0


def test_get_form_with_no_validations():
    response = client.get(
        f"/api/bot/{pytest.bot}/forms",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    form_id = actual["data"][0]["_id"]

    response = client.get(
        f"/api/bot/{pytest.bot}/forms/{form_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    form = actual["data"]
    assert len(form["settings"]) == 6
    assert form["settings"][0]["slot"] == "name"
    assert form["settings"][1]["slot"] == "num_people"
    assert form["settings"][2]["slot"] == "cuisine"
    assert form["settings"][3]["slot"] == "outdoor_seating"
    assert form["settings"][4]["slot"] == "preferences"
    assert form["settings"][5]["slot"] == "feedback"
    assert form["settings"][0]["ask_questions"][0]["_id"]
    assert form["settings"][1]["ask_questions"][0]["_id"]
    assert form["settings"][2]["ask_questions"][0]["_id"]
    assert form["settings"][3]["ask_questions"][0]["_id"]
    assert form["settings"][4]["ask_questions"][0]["_id"]
    assert form["settings"][5]["ask_questions"][0]["_id"]
    assert (
            form["settings"][0]["ask_questions"][0]["value"]["text"]
            == "please give us your name?"
    )
    assert form["settings"][1]["ask_questions"][0]["value"]["text"] == "seats required?"
    assert (
            form["settings"][2]["ask_questions"][0]["value"]["text"] == "type of cuisine?"
    )
    assert (
            form["settings"][3]["ask_questions"][0]["value"]["text"]
            == "outdoor seating required?"
    )
    assert (
            form["settings"][4]["ask_questions"][0]["value"]["text"] == "any preferences?"
    )
    assert (
            form["settings"][5]["ask_questions"][0]["value"]["text"]
            == "Please give your feedback on your experience so far"
    )
    assert form["settings"][0]["slot_set"] == {"type": "custom", "value": "Mahesh"}
    assert form["settings"][1]["slot_set"] == {"type": "current", "value": 10}
    assert form["settings"][2]["slot_set"] == {
        "type": "current",
        "value": "Indian Cuisine",
    }
    assert form["settings"][3]["slot_set"] == {"type": "current", "value": None}
    assert form["settings"][4]["slot_set"] == {"type": "slot", "value": "preferences"}
    assert form["settings"][5]["slot_set"] == {"type": "custom", "value": "Very Nice!"}

    response = client.get(
        f"/api/bot/{pytest.bot}/response/all",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    saved_responses = {response["name"] for response in actual["data"]}
    assert (
            len(
                {
                    "utter_ask_restaurant_form_name",
                    "utter_ask_restaurant_form_num_people",
                    "utter_ask_restaurant_form_cuisine",
                    "utter_ask_restaurant_form_outdoor_seating",
                    "utter_ask_restaurant_form_preferences",
                    "utter_ask_restaurant_form_feedback",
                }.difference(saved_responses)
            )
            == 0
    )
    assert actual["success"]
    assert actual["error_code"] == 0


def test_add_form_slot_not_present():
    path = [
        {
            "ask_questions": ["please give us your location?"],
            "slot": "location",
            "slot_set": {"type": "custom", "value": "Bangalore"},
            "mapping": [
                {"type": "from_text", "value": "user", "entity": "name"},
                {"type": "from_entity", "entity": "name"},
            ],
        },
        {
            "ask_questions": ["seats required?"],
            "slot": "num_people",
            "slot_set": {"type": "current", "value": 10},
            "mapping": [
                {
                    "type": "from_entity",
                    "intent": ["inform", "request_restaurant"],
                    "entity": "number",
                }
            ],
        },
        {
            "ask_questions": ["type of cuisine?"],
            "slot": "cuisine",
            "slot_set": {"type": "current", "value": "Indian Cuisine"},
            "mapping": [{"type": "from_entity", "entity": "cuisine"}],
        },
        {
            "ask_questions": ["outdoor seating required?"],
            "slot": "outdoor_seating",
            "slot_set": {"type": "custom", "value": True},
            "mapping": [
                {"type": "from_entity", "entity": "seating"},
                {"type": "from_intent", "intent": ["affirm"], "value": True},
                {"type": "from_intent", "intent": ["deny"], "value": False},
            ],
        },
        {
            "ask_questions": ["any preferences?"],
            "slot": "preferences",
            "slot_set": {"type": "slot", "value": "preferences"},
            "mapping": [
                {"type": "from_text", "not_intent": ["affirm"]},
                {
                    "type": "from_intent",
                    "intent": ["affirm"],
                    "value": "no additional preferences",
                },
            ],
        },
        {
            "ask_questions": ["Please give your feedback on your experience so far"],
            "slot": "feedback",
            "slot_set": {"type": "custom", "value": "Very Nice!"},
            "mapping": [
                {"type": "from_text"},
                {"type": "from_entity", "entity": "feedback"},
            ],
        },
    ]
    request = {"name": "know_user", "settings": path}
    response = client.post(
        f"/api/bot/{pytest.bot}/forms",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"].__contains__("slots not exists: {")


def test_add_form_with_validations():
    response = client.post(
        f"/api/bot/{pytest.bot}/slots",
        json={"name": "age", "type": "float"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot added successfully!"
    assert actual["success"]
    response = client.post(
        f"/api/bot/{pytest.bot}/slots/mapping",
        json={
            "slot": "age",
            "mapping":
                {
                    "type": "from_intent",
                    "intent": ["get_age"],
                    "entity": "age",
                    "value": "18",
                }
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot mapping added"
    assert actual["success"]

    response = client.post(
        f"/api/bot/{pytest.bot}/slots",
        json={"name": "location", "type": "text"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot added successfully!"
    assert actual["success"]
    response = client.post(
        f"/api/bot/{pytest.bot}/slots/mapping",
        json={
            "slot": "location",
            "mapping": {"type": "from_entity", "entity": "location"},
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot mapping added"
    assert actual["success"]

    response = client.post(
        f"/api/bot/{pytest.bot}/slots",
        json={"name": "occupation", "type": "text"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot added successfully!"
    assert actual["success"]
    response = client.post(
        f"/api/bot/{pytest.bot}/slots/mapping",
        json={
            "slot": "occupation",
            "mapping":
                {
                    "type": "from_intent",
                    "intent": ["get_occupation"],
                    "entity": "occupation",
                    "value": "business",
                }
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot mapping added"
    assert actual["success"]

    response = client.post(
        f"/api/bot/{pytest.bot}/slots/mapping",
        json={
            "slot": "occupation",
            "mapping":
                {"type": "from_text", "entity": "occupation", "value": "engineer"},
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot mapping added"
    assert actual["success"]

    response = client.post(
        f"/api/bot/{pytest.bot}/slots/mapping",
        json={
            "slot": "occupation",
            "mapping": {"type": "from_entity", "entity": "occupation"},
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot mapping added"
    assert actual["success"]

    response = client.post(
        f"/api/bot/{pytest.bot}/slots/mapping",
        json={
            "slot": "occupation",
            "mapping":
                {
                    "type": "from_trigger_intent",
                    "entity": "occupation",
                    "value": "tester",
                    "intent": ["get_business", "is_engineer", "is_tester"],
                    "not_intent": ["get_age", "get_name"],
                }
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot mapping added"
    assert actual["success"]

    name_validation = (
        "if (&& name.contains('i') && name.length() > 4 || !name.contains("
        ")) "
        "{return true;} else {return false;}"
    )

    age_validation = "if (age > 10 && age < 70) {return true;} else {return false;}"

    occupation_validation = (
        "if (occupation in ['teacher', 'programmer', 'student', 'manager'] "
        "&& !occupation.contains("
        ") && occupation.length() > 20) "
        "{return true;} else {return false;}"
    )

    path = [
        {
            "ask_questions": ["what is your name?", "name?"],
            "slot": "name",
            "validation_semantic": name_validation,
            "is_required": True,
            "slot_set": {"type": "custom", "value": "Mahesh"},
            "valid_response": "got it",
            "invalid_response": "please rephrase",
        },
        {
            "ask_questions": ["what is your age?", "age?"],
            "slot": "age",
            "validation_semantic": age_validation,
            "is_required": True,
            "slot_set": {"type": "current", "value": 22},
            "valid_response": "valid entry",
            "invalid_response": "please enter again",
        },
        {
            "ask_questions": ["what is your location?", "location?"],
            "slot": "location",
            "slot_set": {"type": "custom", "value": "Bangalore"},
        },
        {
            "ask_questions": ["what is your occupation?", "occupation?"],
            "slot": "occupation",
            "slot_set": {"type": "slot", "value": "occupation"},
            "validation_semantic": occupation_validation,
            "is_required": False,
        },
    ]
    request = {"name": "know_user_form", "settings": path}
    response = client.post(
        f"/api/bot/{pytest.bot}/forms",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Form added"


def test_get_form_with_validations():
    response = client.get(
        f"/api/bot/{pytest.bot}/forms",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    form_id = actual["data"][1]["_id"]

    response = client.get(
        f"/api/bot/{pytest.bot}/forms/{form_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    form = actual["data"]
    assert len(form["settings"]) == 4
    assert form["settings"][0]["slot"] == "name"
    assert form["settings"][1]["slot"] == "age"
    assert form["settings"][2]["slot"] == "location"
    assert form["settings"][3]["slot"] == "occupation"
    assert form["settings"][0]["ask_questions"][0]["_id"]
    assert form["settings"][1]["ask_questions"][0]["_id"]
    assert form["settings"][2]["ask_questions"][0]["_id"]
    assert form["settings"][0]["ask_questions"][0]["value"]["text"]
    assert form["settings"][1]["ask_questions"][0]["value"]["text"]
    assert form["settings"][2]["ask_questions"][0]["value"]["text"]
    assert form["settings"][3]["ask_questions"][0]["value"]["text"]
    assert (
            form["settings"][0]["validation_semantic"]
            == "if (&& name.contains('i') && name.length() > 4 || "
               "!name.contains("
               ")) {return true;} else {return false;}"
    )
    assert form["settings"][0]["is_required"]
    assert form["settings"][0]["slot_set"] == {"type": "custom", "value": "Mahesh"}
    assert (
            form["settings"][1]["validation_semantic"]
            == "if (age > 10 && age < 70) {return true;} else {return false;}"
    )
    assert form["settings"][1]["is_required"]
    assert form["settings"][1]["slot_set"] == {"type": "current", "value": 22}
    assert not form["settings"][2]["validation_semantic"]
    assert form["settings"][2]["is_required"]
    assert form["settings"][2]["slot_set"] == {"type": "custom", "value": "Bangalore"}
    assert (
            form["settings"][3]["validation_semantic"]
            == "if (occupation in ['teacher', 'programmer', 'student', 'manager'] "
               "&& !occupation.contains("
               ") && occupation.length() > 20) "
               "{return true;} else {return false;}"
    )
    assert not form["settings"][3]["is_required"]
    assert form["settings"][3]["slot_set"] == {"type": "slot", "value": "occupation"}


def test_edit_form_add_validations():
    name_validation = (
        "if (&& name.contains('i') && name.length() > 4 || "
        "!name.contains("
        ")) {return true;} else {return false;}"
    )
    num_people_validation = (
        "if (num_people > 1 && num_people < 10) {return true;} else {return false;}"
    )
    path = [
        {
            "ask_questions": ["please give us your name?"],
            "slot": "name",
            "slot_set": {"type": "custom", "value": "Mahesh"},
            "mapping": [
                {"type": "from_text", "value": "user", "entity": "name"},
                {"type": "from_entity", "entity": "name"},
            ],
            "validation_semantic": name_validation,
            "is_required": True,
        },
        {
            "ask_questions": ["seats required?"],
            "slot": "num_people",
            "mapping": [
                {
                    "type": "from_entity",
                    "intent": ["inform", "request_restaurant"],
                    "entity": "number",
                }
            ],
            "validation_semantic": num_people_validation,
            "is_required": False,
            "valid_response": "valid value",
            "invalid_response": "invalid value. please enter again",
        },
        {
            "ask_questions": ["type of cuisine?"],
            "slot": "cuisine",
            "slot_set": {"type": "custom", "value": "Indian Cuisine"},
            "mapping": [{"type": "from_entity", "entity": "cuisine"}],
        },
        {
            "ask_questions": ["outdoor seating required?"],
            "slot": "outdoor_seating",
            "mapping": [
                {"type": "from_entity", "entity": "seating"},
                {"type": "from_intent", "intent": ["affirm"], "value": True},
                {"type": "from_intent", "intent": ["deny"], "value": False},
            ],
        },
        {
            "ask_questions": ["any preferences?"],
            "slot": "preferences",
            "slot_set": {"type": "slot", "value": "preferences"},
            "mapping": [
                {"type": "from_text", "not_intent": ["affirm"]},
                {
                    "type": "from_intent",
                    "intent": ["affirm"],
                    "value": "no additional preferences",
                },
            ],
        },
        {
            "ask_questions": ["Please give your feedback on your experience so far"],
            "slot": "feedback",
            "slot_set": {"type": "custom", "value": "Very Nice!"},
            "mapping": [
                {"type": "from_text"},
                {"type": "from_entity", "entity": "feedback"},
            ],
        },
    ]
    request = {"name": "restaurant_form", "settings": path}
    response = client.put(
        f"/api/bot/{pytest.bot}/forms",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Form updated"


def test_edit_form_remove_validations():
    path = [
        {
            "ask_questions": ["what is your name?", "name?"],
            "slot": "name",
            "valid_response": "got it",
            "slot_set": {"type": "custom", "value": "Mahesh"},
            "invalid_response": "please rephrase",
        },
        {
            "ask_questions": ["what is your age?", "age?"],
            "slot": "age",
            "slot_set": {"type": "current", "value": 22},
            "valid_response": "valid entry",
            "invalid_response": "please enter again",
        },
        {
            "ask_questions": ["what is your location?", "location?"],
            "slot": "location",
            "slot_set": {"type": "custom", "value": "Bangalore"},
        },
        {
            "ask_questions": ["what is your occupation?", "occupation?"],
            "slot": "occupation",
            "slot_set": {"type": "slot", "value": "occupation"},
        },
    ]
    request = {"name": "know_user_form", "settings": path}
    response = client.put(
        f"/api/bot/{pytest.bot}/forms",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Form updated"


def test_list_form():
    response = client.get(
        f"/api/bot/{pytest.bot}/forms",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"][0]["name"] == "restaurant_form"
    assert actual["data"][0]["required_slots"] == [
        "name",
        "num_people",
        "cuisine",
        "outdoor_seating",
        "preferences",
        "feedback",
    ]
    assert actual["data"][1]["name"] == "know_user_form"
    assert actual["data"][1]["required_slots"] == [
        "name",
        "age",
        "location",
        "occupation",
    ]


def test_get_form_after_edit():
    response = client.get(
        f"/api/bot/{pytest.bot}/forms",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    form_1 = actual["data"][0]["_id"]

    response = client.get(
        f"/api/bot/{pytest.bot}/forms/{form_1}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    form = actual["data"]
    assert len(form["settings"]) == 6
    assert form["settings"][0]["slot"] == "name"
    assert form["settings"][1]["slot"] == "num_people"
    assert form["settings"][2]["slot"] == "cuisine"
    assert form["settings"][3]["slot"] == "outdoor_seating"
    assert form["settings"][4]["slot"] == "preferences"
    assert form["settings"][5]["slot"] == "feedback"
    assert form["settings"][0]["ask_questions"][0]["_id"]
    assert form["settings"][1]["ask_questions"][0]["_id"]
    assert form["settings"][2]["ask_questions"][0]["_id"]
    assert form["settings"][3]["ask_questions"][0]["_id"]
    assert form["settings"][4]["ask_questions"][0]["_id"]
    assert form["settings"][5]["ask_questions"][0]["_id"]
    assert (
            form["settings"][0]["ask_questions"][0]["value"]["text"]
            == "please give us your name?"
    )
    assert form["settings"][1]["ask_questions"][0]["value"]["text"] == "seats required?"
    assert (
            form["settings"][2]["ask_questions"][0]["value"]["text"] == "type of cuisine?"
    )
    assert (
            form["settings"][3]["ask_questions"][0]["value"]["text"]
            == "outdoor seating required?"
    )
    assert (
            form["settings"][4]["ask_questions"][0]["value"]["text"] == "any preferences?"
    )
    assert (
            form["settings"][5]["ask_questions"][0]["value"]["text"]
            == "Please give your feedback on your experience so far"
    )
    assert (
            form["settings"][0]["validation_semantic"]
            == "if (&& name.contains('i') && name.length() > 4 || "
               "!name.contains("
               ")) {return true;} else {return false;}"
    )
    assert form["settings"][0]["is_required"]
    assert form["settings"][0]["slot_set"] == {"type": "custom", "value": "Mahesh"}
    assert (
            form["settings"][1]["validation_semantic"]
            == "if (num_people > 1 && num_people < 10) {return true;} else {return false;}"
    )
    assert not form["settings"][1]["is_required"]
    assert form["settings"][1]["slot_set"] == {"type": "current", "value": None}
    assert not form["settings"][2]["validation_semantic"]
    assert form["settings"][2]["slot_set"] == {
        "type": "custom",
        "value": "Indian Cuisine",
    }
    assert not form["settings"][3]["validation_semantic"]
    assert form["settings"][3]["slot_set"] == {"type": "current", "value": None}
    assert not form["settings"][4]["validation_semantic"]
    assert form["settings"][4]["slot_set"] == {"type": "slot", "value": "preferences"}

    response = client.get(
        f"/api/bot/{pytest.bot}/response/all",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    saved_responses = {response["name"] for response in actual["data"]}
    assert (
            len(
                {
                    "utter_ask_restaurant_form_name",
                    "utter_ask_restaurant_form_num_people",
                    "utter_ask_restaurant_form_cuisine",
                    "utter_ask_restaurant_form_outdoor_seating",
                    "utter_ask_restaurant_form_preferences",
                    "utter_ask_restaurant_form_feedback",
                }.difference(saved_responses)
            )
            == 0
    )
    assert actual["success"]
    assert actual["error_code"] == 0


def test_edit_form():
    response = client.post(
        f"/api/bot/{pytest.bot}/slots",
        json={"name": "ac_required", "type": "text"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot added successfully!"
    assert actual["success"]
    response = client.post(
        f"/api/bot/{pytest.bot}/slots/mapping",
        json={
            "slot": "ac_required",
            "mapping": {"type": "from_intent", "intent": ["affirm"], "value": True}
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot mapping added"
    assert actual["success"]

    response = client.post(
        f"/api/bot/{pytest.bot}/slots/mapping",
        json={
            "slot": "ac_required",
            "mapping":
                {"type": "from_intent", "intent": ["deny"], "value": False}
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot mapping added"
    assert actual["success"]

    path = [
        {
            "ask_questions": ["which location would you prefer?"],
            "slot": "location",
            "slot_set": {"type": "custom", "value": "Bangalore"},
            "mapping": [
                {"type": "from_text", "value": "user", "entity": "location"},
                {"type": "from_entity", "entity": "location"},
            ],
        },
        {
            "ask_questions": ["seats required?"],
            "slot": "num_people",
            "slot_set": {"type": "current", "value": 10},
            "mapping": [
                {
                    "type": "from_entity",
                    "intent": ["inform", "request_restaurant"],
                    "entity": "number",
                }
            ],
        },
        {
            "ask_questions": ["type of cuisine?"],
            "slot": "cuisine",
            "slot_set": {"type": "custom", "value": "Indian Cuisine"},
            "mapping": [{"type": "from_entity", "entity": "cuisine"}],
        },
        {
            "ask_questions": ["outdoor seating required?"],
            "slot": "outdoor_seating",
            "slot_set": {"type": "custom", "value": True},
            "mapping": [
                {"type": "from_entity", "entity": "seating"},
                {"type": "from_intent", "intent": ["affirm"], "value": True},
                {"type": "from_intent", "intent": ["deny"], "value": False},
            ],
        },
        {
            "ask_questions": ["any preferences?"],
            "slot": "preferences",
            "slot_set": {"type": "slot", "value": "preferences"},
            "mapping": [
                {"type": "from_text", "not_intent": ["affirm"]},
                {
                    "type": "from_intent",
                    "intent": ["affirm"],
                    "value": "no additional preferences",
                },
            ],
        },
        {
            "ask_questions": ["do you want to go with an AC room?"],
            "slot": "ac_required",
            "slot_set": {"type": "current", "value": True},
        },
        {
            "ask_questions": ["Please give your feedback on your experience so far"],
            "slot": "feedback",
            "slot_set": {"type": "custom", "value": "Very Nice!"},
            "mapping": [
                {"type": "from_text"},
                {"type": "from_entity", "entity": "feedback"},
            ],
        },
    ]
    request = {"name": "restaurant_form", "settings": path}
    response = client.put(
        f"/api/bot/{pytest.bot}/forms",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Form updated"


def test_edit_form_with_any_slot():
    response = client.post(
        f"/api/bot/{pytest.bot}/slots",
        json={"name": "account_required", "type": "any"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot added successfully!"
    assert actual["success"]
    response = client.post(
        f"/api/bot/{pytest.bot}/slots/mapping",
        json={
            "slot": "account_required",
            "mapping":
                {"type": "from_intent", "intent": ["affirm"], "value": True},
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot mapping added"
    assert actual["success"]

    response = client.post(
        f"/api/bot/{pytest.bot}/slots/mapping",
        json={
            "slot": "account_required",
            "mapping":
                {"type": "from_intent", "intent": ["deny"], "value": False},
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot mapping added"
    assert actual["success"]

    path = [
        {
            "ask_questions": ["which location would you prefer?"],
            "slot": "location",
            "slot_set": {"type": "custom", "value": "Bangalore"},
            "mapping": [
                {"type": "from_text", "value": "user", "entity": "location"},
                {"type": "from_entity", "entity": "location"},
            ],
        },
        {
            "ask_questions": ["seats required?"],
            "slot": "num_people",
            "slot_set": {"type": "current", "value": 10},
            "mapping": [
                {
                    "type": "from_entity",
                    "intent": ["inform", "request_restaurant"],
                    "entity": "number",
                }
            ],
        },
        {
            "ask_questions": ["type of cuisine?"],
            "slot": "cuisine",
            "slot_set": {"type": "custom", "value": "Indian Cuisine"},
            "mapping": [{"type": "from_entity", "entity": "cuisine"}],
        },
        {
            "ask_questions": ["outdoor seating required?"],
            "slot": "outdoor_seating",
            "slot_set": {"type": "custom", "value": True},
            "mapping": [
                {"type": "from_entity", "entity": "seating"},
                {"type": "from_intent", "intent": ["affirm"], "value": True},
                {"type": "from_intent", "intent": ["deny"], "value": False},
            ],
        },
        {
            "ask_questions": ["any preferences?"],
            "slot": "preferences",
            "slot_set": {"type": "slot", "value": "preferences"},
            "mapping": [
                {"type": "from_text", "not_intent": ["affirm"]},
                {
                    "type": "from_intent",
                    "intent": ["affirm"],
                    "value": "no additional preferences",
                },
            ],
        },
        {
            "ask_questions": ["do you want to go with an AC room?"],
            "slot": "account_required",
            "slot_set": {"type": "current", "value": True},
        },
    ]
    request = {"name": "restaurant_form", "settings": path}
    response = client.put(
        f"/api/bot/{pytest.bot}/forms",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "form will not accept any type slots: {'account_required'}"


def test_edit_slot_mapping():
    response = client.post(
        f"/api/bot/{pytest.bot}/slots/mapping",
        json={
            "slot": "cuisine",
            "mapping":
                {"type": "from_intent", "intent": ["order", "menu"], "value": "cuisine"}
            ,
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot mapping added"
    assert actual["success"]
    assert actual["error_code"] == 0
    mapping_id = actual["data"]["id"]
    response = client.put(
        f"/api/bot/{pytest.bot}/slots/mapping/{mapping_id}",
        json={
            "slot": "cuisine",
            "mapping":
                {"type": "from_intent", "intent": ["order", "menu"], "value": "cuisine"}
            ,
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Slot mapping updated"
    assert actual["success"]
    assert actual["error_code"] == 0


def test_get_slot_mapping():
    response = client.get(
        f"/api/bot/{pytest.bot}/slots/mapping",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    for obj in actual['data']:
        for m in obj['mapping']:
            m.pop('_id')

    assert not DeepDiff(
        actual["data"],
        [{'slot': 'ac_required',
          'mapping': [{'type': 'from_intent', 'value': True, 'intent': ['affirm']},
                      {'type': 'from_intent', 'value': False, 'intent': ['deny']}]},
         {'slot': 'account_required',
          'mapping': [{'type': 'from_intent', 'value': True, 'intent': ['affirm']},
                      {'type': 'from_intent', 'value': False, 'intent': ['deny']}]},
         {'slot': 'age', 'mapping': [
             {'type': 'from_intent', 'value': '18', 'intent': ['get_age'], }]},
         {'slot': 'cuisine',
          'mapping': [{'type': 'from_entity', 'entity': 'cuisine'},
                      {'type': 'from_intent', 'value': 'cuisine', 'intent': ['order', 'menu'],
                       }]},
         {'slot': 'feedback', 'mapping': [
             {'type': 'from_entity', 'entity': 'feedback'}]}, {'slot': 'location',
                                                               'mapping': [{
                                                                   'type': 'from_entity',
                                                                   'entity': 'location',
                                                               }]},
         {'slot': 'name', 'mapping': [{'type': 'from_text', 'value': 'user'}]},
         {'slot': 'num_people', 'mapping': [
             {'type': 'from_entity', 'entity': 'number', 'intent': ['inform', 'request_restaurant'],
              }]}, {'slot': 'occupation', 'mapping': [
            {'type': 'from_intent', 'value': 'business', 'intent': ['get_occupation'],
             },
            {'type': 'from_text', 'value': 'engineer'},
            {'type': 'from_entity', 'entity': 'occupation'},
            {'type': 'from_trigger_intent', 'value': 'tester', 'intent': ['get_business', 'is_engineer', 'is_tester'],
             'not_intent': ['get_age', 'get_name']}]},
         {'slot': 'outdoor_seating',
          'mapping': [
              {'type': 'from_text',
               'not_intent': [
                   'affirm'],
               'conditions': [{
                   'active_loop': 'booking',
                   'requested_slot': 'outdoor_seating'}],
               }]},
         {'slot': 'preferences', 'mapping': [{'type': 'from_text', 'not_intent': ['affirm'], 'conditions': [
             {'active_loop': 'booking', 'requested_slot': 'preferences'}]}]},
         {'slot': 'user_feedback', 'mapping': [{'type': 'from_text'},
                                               {'type': 'from_entity', 'entity': 'user_feedback',
                                                }]}]
        ,
        ignore_order=True,
    )

    response = client.get(
        f"/api/bot/{pytest.bot}/slots/mapping?form=booking",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    for obj in actual['data']:
        for m in obj['mapping']:
            m.pop('_id')
    assert actual["success"]
    assert actual["data"] == [{'slot': 'outdoor_seating', 'mapping': [{'type': 'from_text', 'not_intent': ['affirm'],
                                                                       'conditions': [{'active_loop': 'booking',
                                                                                       'requested_slot': 'outdoor_seating'}]}]},
                              {'slot': 'preferences', 'mapping': [{'type': 'from_text', 'not_intent': ['affirm'],
                                                                   'conditions': [{'active_loop': 'booking',
                                                                                   'requested_slot': 'preferences'}]}]}]

    assert actual["error_code"] == 0


def test_delete_form():
    response = client.delete(
        f"/api/bot/{pytest.bot}/forms/restaurant_form",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Form deleted"


def test_delete_form_already_deleted():
    response = client.delete(
        f"/api/bot/{pytest.bot}/forms/restaurant_form",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == 'Form "restaurant_form" does not exists'


def test_delete_form_not_exists():
    response = client.delete(
        f"/api/bot/{pytest.bot}/forms/form_not_exists",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == 'Form "form_not_exists" does not exists'


def test_delete_slot_mapping():
    response = client.delete(
        f"/api/bot/{pytest.bot}/slots/mapping/ac_required",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Slot mapping deleted"


def test_delete_slot_mapping_non_existing():
    response = client.delete(
        f"/api/bot/{pytest.bot}/slots/mapping/ac_required",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "No slot mapping exists for slot: ac_required"


def test_add_slot_set_action():
    request = {
        "name": "action_set_name_slot",
        "set_slots": [
            {"name": "name", "type": "from_value", "value": 5},
            {"name": "age", "type": "reset_slot"},
        ],
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/slotset",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action added"


def test_add_slot_set_action_slot_not_exists():
    request = {
        "name": "action_set_new_user_slot",
        "set_slots": [{"name": "new_user", "type": "from_value", "value": False}],
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/slotset",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == 'Slot with name "new_user" not found'


def test_list_slot_set_actions():
    response = client.get(
        f"/api/bot/{pytest.bot}/action/slotset",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]) == 1
    actual["data"][0].pop("_id")
    assert actual["data"][0] == {
        "name": "action_set_name_slot",
        "set_slots": [
            {"name": "name", "type": "from_value", "value": 5},
            {"name": "age", "type": "reset_slot"},
        ],
    }


def test_edit_slot_set_action():
    request = {
        "name": "action_set_name_slot",
        "set_slots": [{"name": "name", "type": "from_value", "value": "age"}],
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/slotset",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action updated"


def test_edit_slot_set_action_slot_not_exists():
    request = {
        "name": "action_set_name_slot",
        "set_slots": [{"name": "non_existant", "type": "from_value", "value": "age"}],
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/slotset",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == 'Slot with name "non_existant" not found'


def test_delete_slot_set_action_not_exists():
    response = client.delete(
        f"/api/bot/{pytest.bot}/action/non_existant",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == 'Action with name "non_existant" not found'


def test_delete_slot_set_action():
    response = client.delete(
        f"/api/bot/{pytest.bot}/action/action_set_name_slot",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action deleted"


def test_list_slot_set_action_none_present():
    response = client.get(
        f"/api/bot/{pytest.bot}/action/slotset",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] == []


def test_add_intent_case_insensitivity():
    response = client.post(
        f"/api/bot/{pytest.bot}/intents",
        json={"data": "CASE_INSENSITIVE_INTENT"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Intent added successfully!"

    response = client.get(
        f"/api/bot/{pytest.bot}/intents",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert "data" in actual
    intents_added = [i["name"] for i in actual["data"]]
    assert "CASE_INSENSITIVE_INTENT" not in intents_added
    assert "case_insensitive_intent" in intents_added
    assert actual["success"]
    assert actual["error_code"] == 0

    response = client.post(
        f"/api/bot/{pytest.bot}/training_examples/CASE_INSENSITIVE_INTENT",
        json={"data": ["IS THIS CASE_INSENSITIVE_INTENT?"]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"][0]["message"] == "Training Example added"

    response = client.get(
        f"/api/bot/{pytest.bot}/training_examples/case_insensitive_intent",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    training_examples = [t["text"] for t in actual["data"]]
    assert "IS THIS CASE_INSENSITIVE_INTENT?" in training_examples
    assert actual["success"]
    assert actual["error_code"] == 0


def test_add_training_example_case_insensitivity():
    response = client.post(
        f"/api/bot/{pytest.bot}/training_examples/CASE_INSENSITIVE_TRAINING_EX_INTENT",
        json={"data": ["IS THIS CASE_INSENSITIVE_TRAINING_EX_INTENT?"]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"][0]["message"] == "Training Example added"

    response = client.get(
        f"/api/bot/{pytest.bot}/training_examples/case_insensitive_training_ex_intent",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert "IS THIS CASE_INSENSITIVE_TRAINING_EX_INTENT?" in [
        t["text"] for t in actual["data"]
    ]
    assert actual["success"]
    assert actual["error_code"] == 0


def test_add_utterances_case_insensitivity():
    response = client.post(
        f"/api/bot/{pytest.bot}/utterance",
        json={"data": "utter_CASE_INSENSITIVE_UTTERANCE"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Utterance added!"

    response = client.get(
        f"/api/bot/{pytest.bot}/utterance",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    utterances_added = [u["name"] for u in actual["data"]["utterances"]]
    assert "utter_CASE_INSENSITIVE_UTTERANCE" not in utterances_added
    assert "utter_case_insensitive_utterance" in utterances_added


def test_add_responses_case_insensitivity():
    response = client.post(
        f"/api/bot/{pytest.bot}/response/utter_CASE_INSENSITIVE_RESPONSE",
        json={"data": "yes, this is utter_CASE_INSENSITIVE_RESPONSE"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Response added!"

    response = client.get(
        f"/api/bot/{pytest.bot}/response/utter_CASE_INSENSITIVE_RESPONSE",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"][0]["value"] == {
        "text": "yes, this is utter_CASE_INSENSITIVE_RESPONSE"
    }

    response = client.get(
        f"/api/bot/{pytest.bot}/response/utter_case_insensitive_response",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]) == 1


def test_add_story_case_insensitivity():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "CASE_INSENSITIVE_STORY",
            "type": "STORY",
            "template_type": "Q&A",
            "steps": [
                {"name": "case_insensitive_training_ex_intent", "type": "INTENT"},
                {"name": "utter_case_insensitive_response", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Flow added successfully"
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0
    pytest.story_id = actual["data"]["_id"]

    response = client.get(
        f"/api/bot/{pytest.bot}/stories",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]
    assert Utility.check_empty_string(actual["message"])
    stories_added = [s["name"] for s in actual["data"]]
    assert "CASE_INSENSITIVE_STORY" not in stories_added
    assert "case_insensitive_story" in stories_added

    response = client.delete(
        f"/api/bot/{pytest.bot}/stories/{pytest.story_id}/STORY",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Flow deleted successfully"


def test_add_rule_case_insensitivity():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "CASE_INSENSITIVE_RULE",
            "type": "RULE",
            "steps": [
                {"name": "case_insensitive_training_ex_intent", "type": "INTENT"},
                {"name": "utter_case_insensitive_response", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Flow added successfully"
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0

    response = client.get(
        f"/api/bot/{pytest.bot}/stories",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]
    assert Utility.check_empty_string(actual["message"])
    stories_added = [s["name"] for s in actual["data"]]
    assert "CASE_INSENSITIVE_RULE" not in stories_added
    assert "case_insensitive_rule" in stories_added


def test_add_regex_case_insensitivity():
    response = client.post(
        f"/api/bot/{pytest.bot}/regex",
        json={"name": "CASE_INSENSITIVE_REGEX", "pattern": "b*b"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Regex pattern added successfully!"

    response = client.get(
        f"/api/bot/{pytest.bot}/regex",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])
    assert "CASE_INSENSITIVE_REGEX" != actual["data"][0]["name"]
    assert "case_insensitive_regex" == actual["data"][0]["name"]


def test_add_lookup_single_value():
    response = client.post(
        f"/api/bot/{pytest.bot}/lookup",
        json={"data": "single_value"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Lookup added!"

    response = client.post(
        f"/api/bot/{pytest.bot}/lookup/single_value/value",
        json={"data": "test"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Lookup value added!"

    response = client.get(
        f"/api/bot/{pytest.bot}/lookup/single_value/values",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert len(actual["data"]) == 1
    assert all(
        key in item.keys()
        for item in actual["data"]
        for key in ["_id", "value", "lookup"]
    )


def test_add_lookup_table_case_insensitivity():
    response = client.post(
        f"/api/bot/{pytest.bot}/lookup",
        json={"data": "CASE_INSENSITIVE_LOOKUP"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Lookup added!"

    response = client.post(
        f"/api/bot/{pytest.bot}/lookup/CASE_INSENSITIVE_LOOKUP/values",
        json={"value": ["test1", "test2"]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Lookup values added!"

    response = client.get(
        f"/api/bot/{pytest.bot}/lookup/CASE_INSENSITIVE_LOOKUP/values",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert len(actual["data"]) == 2
    assert any("case_insensitive_lookup" == item["lookup"] for item in actual["data"])

    response = client.get(
        f"/api/bot/{pytest.bot}/lookups",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert any("case_insensitive_lookup" == item["lookup"] for item in actual["data"])


def test_add_entity_synonym_case_insensitivity():
    response = client.post(
        f"/api/bot/{pytest.bot}/entity/synonym",
        json={"data": "CASE_INSENSITIVE"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Synonym added!"

    response = client.post(
        f"/api/bot/{pytest.bot}/entity/synonym/CASE_INSENSITIVE/values",
        json={"value": ["CASE_INSENSITIVE_SYNONYM"]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Synonym values added!"

    response = client.get(
        f"/api/bot/{pytest.bot}/entity/synonym/case_insensitive/values",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert any(
        item["value"] == "CASE_INSENSITIVE_SYNONYM"
        and item["synonym"] == "case_insensitive"
        for item in actual["data"]
    )


def test_add_slot_case_insensitivity():
    response = client.post(
        f"/api/bot/{pytest.bot}/slots",
        json={
            "name": "CASE_INSENSITIVE_SLOT",
            "type": "any",
            "initial_value": "bot",
            "influence_conversation": False,
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert "data" in actual
    assert actual["message"] == "Slot added successfully!"
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0

    response = client.get(
        f"/api/bot/{pytest.bot}/slots",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert "data" in actual
    assert len(actual["data"])
    assert actual["success"]
    assert actual["error_code"] == 0


def test_add_form_case_insensitivity():
    path = [
        {
            "ask_questions": ["please give us your name?"],
            "slot": "name",
            "slot_set": {"type": "custom", "value": "Mahesh"},
            "mapping": [
                {"type": "from_text", "value": "user", "entity": "name"},
                {"type": "from_entity", "entity": "name"},
            ],
        },
    ]
    request = {"name": "CASE_INSENSITIVE_FORM", "settings": path}
    response = client.post(
        f"/api/bot/{pytest.bot}/forms",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Form added"

    response = client.get(
        f"/api/bot/{pytest.bot}/forms",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    form_1 = actual["data"][1]["_id"]

    response = client.get(
        f"/api/bot/{pytest.bot}/forms/{form_1}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["name"] == "case_insensitive_form"


def test_add_slot_set_action_case_insensitivity():
    request = {
        "name": "CASE_INSENSITIVE_SLOT_SET_ACTION",
        "set_slots": [{"name": "name", "type": "from_value", "value": 5}],
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/slotset",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action added"

    response = client.get(
        f"/api/bot/{pytest.bot}/action/slotset",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]) == 1
    actual["data"][0].pop("_id")
    assert actual["data"][0] == {
        "name": "case_insensitive_slot_set_action",
        "set_slots": [{"name": "name", "type": "from_value", "value": 5}],
    }


def test_add_http_action_case_insensitivity():
    request_body = {
        "action_name": "CASE_INSENSITIVE_HTTP_ACTION",
        "response": {"value": "string"},
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "params_list": [
            {"key": "testParam1", "parameter_type": "value", "value": "testValue1"}
        ],
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"]
    assert actual["success"]

    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/httpaction/CASE_INSENSITIVE_HTTP_ACTION",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert not actual["data"]

    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/httpaction/case_insensitive_http_action",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]
    assert actual["success"]


def test_get_ui_config_empty():
    response = client.get(
        url=f"/api/account/config/ui",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"] == {}
    assert actual["success"]


def test_add_ui_config():
    response = client.put(
        url=f"/api/account/config/ui",
        json={"data": {"has_stepper": True, "has_tour": False, "theme": "white"}},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert not actual["data"]
    assert actual["success"]
    assert actual["message"] == "Config saved!"

    response = client.put(
        url=f"/api/account/config/ui",
        json={"data": {"has_stepper": True, "has_tour": False, "theme": "black"}},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert not actual["data"]
    assert actual["success"]
    assert actual["message"] == "Config saved!"


def test_get_ui_config():
    response = client.get(
        url=f"/api/account/config/ui",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"] == {"has_stepper": True, "has_tour": False, "theme": "black"}
    assert actual["success"]


def test_sso_redirect_url_invalid_type():
    response = client.get(url=f"/api/auth/login/sso/ethereum")
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == "ethereum login is not supported"
    assert not actual["success"]


def test_list_sso_not_enabled(monkeypatch):
    monkeypatch.setitem(Utility.environment["app"], "enable_sso_only", True)
    response = client.get(url=f"/api/system/properties", allow_redirects=False)
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["success"]
    assert actual["data"] == {
        "sso": {"facebook": False, "linkedin": False, "google": False},
        "enable_sso_only": True,
        "validate_trusted_device": False,
        "enable_apm": False,
        "enable_notifications": False,
        "validate_recaptcha": False,
        "enable_multilingual": False,
        "properties": {"bot": {"enable_onboarding": True}},
    }


def test_sso_redirect_url_not_enabled():
    response = client.get(url=f"/api/auth/login/sso/google", allow_redirects=False)
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == "google login is not enabled"
    assert not actual["success"]

    response = client.get(url=f"/api/auth/login/sso/linkedin", allow_redirects=False)
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == "linkedin login is not enabled"
    assert not actual["success"]

    response = client.get(url=f"/api/auth/login/sso/facebook", allow_redirects=False)
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == "facebook login is not enabled"
    assert not actual["success"]


def test_sso_redirect_url(monkeypatch):
    discovery_url = (
        "https://accounts.google.com/o/oauth2/v2/auth?response_type=code&client_id="
    )

    async def _mock_get_discovery_doc(*args, **kwargs):
        return {"authorization_endpoint": discovery_url}

    Utility.environment["sso"]["linkedin"]["enable"] = True
    Utility.environment["sso"]["google"]["enable"] = True
    Utility.environment["sso"]["facebook"]["enable"] = True
    monkeypatch.setattr(GoogleSSO, "get_discovery_document", _mock_get_discovery_doc)

    response = client.get(url=f"/api/auth/login/sso/google", allow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].__contains__(discovery_url)

    response = client.get(url=f"/api/auth/login/sso/linkedin", allow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].__contains__(
        "https://www.linkedin.com/oauth/v2/authorization?response_type=code&client_id="
    )

    response = client.get(url=f"/api/auth/login/sso/facebook", allow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].__contains__(
        "https://www.facebook.com/v9.0/dialog/oauth?response_type=code&client_id="
    )


def test_list_sso_enabled():
    Utility.environment["sso"]["linkedin"]["enable"] = True
    Utility.environment["sso"]["google"]["enable"] = True

    response = client.get(url=f"/api/system/properties", allow_redirects=False)
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["success"]
    assert actual["data"] == {
        "sso": {"facebook": False, "linkedin": True, "google": True},
        "enable_apm": False,
        "enable_notifications": False,
        "validate_recaptcha": False,
        "enable_sso_only": False,
        "validate_trusted_device": False,
        "enable_multilingual": False,
        "properties": {"bot": {"enable_onboarding": True}},
    }


def test_sso_get_login_token_invalid_type():
    response = client.get(url=f"/api/auth/login/sso/callback/ethereum")
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == "ethereum login is not supported"
    assert not actual["success"]


def test_sso_get_login_token(monkeypatch):
    async def __mock_verify_and_process(*args, **kwargs):
        return True, {}, "fgyduhsaifusijfisofwh87eyfhw98yqwhfc8wufchwufehwncj"

    monkeypatch.setattr(Authentication, "verify_and_process", __mock_verify_and_process)
    response = client.get(
        url=f"/api/auth/login/sso/callback/google?code=123456789", allow_redirects=False
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

    response = client.get(
        url=f"/api/auth/login/sso/callback/linkedin?code=123456789",
        allow_redirects=False,
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

    response = client.get(
        url=f"/api/auth/login/sso/callback/facebook?code=123456789",
        allow_redirects=False,
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


def test_trigger_mail_on_new_signup_with_sso(monkeypatch):
    token = "fgyduhsaifusijfisofwh87eyfhw98yqwhfc8wufchwufehwncj"

    async def __mock_verify_and_process(*args, **kwargs):
        return (
            False,
            {
                "email": "new_user@digite.com",
                "first_name": "new",
                "password": SecretStr("123456789"),
            },
            token,
        )

    monkeypatch.setattr(Authentication, "verify_and_process", __mock_verify_and_process)
    monkeypatch.setattr(MailUtility, "trigger_smtp", mock_smtp)
    Utility.email_conf["email"]["enable"] = True
    response = client.get(
        url=f"/api/auth/login/sso/callback/google?code=123456789", allow_redirects=False
    )
    actual = response.json()
    Utility.email_conf["email"]["enable"] = False
    assert actual["success"]
    assert actual["error_code"] == 0
    assert not Utility.check_empty_string(actual["message"])
    actual = response.json()
    assert actual["data"]["access_token"] == token
    assert actual["data"]["token_type"] == "bearer"


@patch("kairon.shared.utils.SMTP", autospec=True)
def test_add_email_action(mock_smtp):
    request = {
        "action_name": "email_config",
        "smtp_url": "test.test.com",
        "smtp_port": 25,
        "smtp_userid": None,
        "smtp_password": {"value": "test"},
        "from_email": {"value": "from_email", "parameter_type": "slot"},
        "to_email": {"value": ["test@test.com", "test1@test.com"], "parameter_type": "value"},
        "subject": "Test Subject",
        "response": "Test Response",
        "tls": False,
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/email",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action added"


@patch("kairon.shared.utils.SMTP", autospec=True)
def test_add_email_action_from_different_parameter_type(mock_smtp):
    request = {
        "action_name": "email_config_with_slot",
        "smtp_url": "test.test.com",
        "smtp_port": 25,
        "smtp_userid": None,
        "smtp_password": {"value": "test", "parameter_type": "slot"},
        "from_email": {"value": "test@demo.com", "parameter_type": "value"},
        "to_email": {"value": "to_email", "parameter_type": "slot"},
        "subject": "Test Subject",
        "response": "Test Response",
        "tls": False,
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/email",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action added"

    request = {
        "action_name": "email_config_with_key_vault",
        "smtp_url": "test.test.com",
        "smtp_port": 25,
        "smtp_userid": None,
        "smtp_password": {"value": "test", "parameter_type": "key_vault"},
        "from_email": {"value": "test@demo.com", "parameter_type": "value"},
        "to_email": {"value": "to_email", "parameter_type": "slot"},
        "subject": "Test Subject",
        "response": "Test Response",
        "tls": False,
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/email",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action added"


@patch("kairon.shared.utils.SMTP", autospec=True)
def test_add_email_action_from_invalid_parameter_type(mock_smtp):
    request = {
        "action_name": "email_config_invalid_parameter_type",
        "smtp_url": "test.test.com",
        "smtp_port": 25,
        "smtp_userid": None,
        "smtp_password": {"value": "test", "parameter_type": "intent"},
        "from_email": {"value": "test@demo.com", "parameter_type": "value"},
        "to_email": {"value": "to_email", "parameter_type": "slot"},
        "subject": "Test Subject",
        "response": "Test Response",
        "tls": False,
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/email",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422

    request = {
        "action_name": "email_config_invalid_parameter_type",
        "smtp_url": "test.test.com",
        "smtp_port": 25,
        "smtp_userid": None,
        "smtp_password": {"value": "", "parameter_type": "slot"},
        "from_email": {"value": "test@demo.com", "parameter_type": "value"},
        "to_email": {"value": "to_email", "parameter_type": "slot"},
        "subject": "Test Subject",
        "response": "Test Response",
        "tls": False,
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/email",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422

    request = {
        "action_name": "email_config_invalid_parameter_type",
        "smtp_url": "test.test.com",
        "smtp_port": 25,
        "smtp_userid": None,
        "smtp_password": {"value": "", "parameter_type": "key_vault"},
        "from_email": {"value": "test@demo.com", "parameter_type": "value"},
        "to_email": {"value": "to_email", "parameter_type": "slot"},
        "subject": "Test Subject",
        "response": "Test Response",
        "tls": False,
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/email",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422


@patch("kairon.shared.utils.SMTP", autospec=True)
def test_add_email_action_from_invalid_parameter_type_1(mock_smtp):
    request = {"action_name": "email_config_invalid_parameter_type",
               "smtp_url": "test.test.com",
               "smtp_port": 25,
               "smtp_userid": None,
               "smtp_password": {'value': "test", "parameter_type": "slot"},
               "from_email": {"value": "test@demo.com", "parameter_type": "value"},
               "to_email": {"value": "to_email", "parameter_type": "intent"},
               "subject": "Test Subject",
               "response": "Test Response",
               "tls": False
               }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/email",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422

    request = {"action_name": "email_config_invalid_parameter_type",
               "smtp_url": "test.test.com",
               "smtp_port": 25,
               "smtp_userid": None,
               "smtp_password": {'value': "test", "parameter_type": "slot"},
               "from_email": {"value": "test@demo.com", "parameter_type": "value"},
               "to_email": {"value": "", "parameter_type": "slot"},
               "subject": "Test Subject",
               "response": "Test Response",
               "tls": False
               }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/email",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [{'loc': ['body', 'to_email', '__root__'],
                                  'msg': 'Provide name of the slot as value', 'type': 'value_error'}]
    assert str(actual['message']).__contains__("Provide name of the slot as value")

    request = {"action_name": "email_config_invalid_parameter_type",
               "smtp_url": "test.test.com",
               "smtp_port": 25,
               "smtp_userid": None,
               "smtp_password": {'value': "test", "parameter_type": "key_vault"},
               "from_email": {"value": "test@demo.com", "parameter_type": "value"},
               "to_email": {"value": "", "parameter_type": "value"},
               "subject": "Test Subject",
               "response": "Test Response",
               "tls": False
               }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/email",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [{'loc': ['body', 'to_email', '__root__'],
                                  'msg': 'Provide list of emails as value', 'type': 'value_error'}]
    assert str(actual['message']).__contains__("Provide list of emails as value")

    request = {"action_name": "email_config_invalid_parameter_type",
               "smtp_url": "test.test.com",
               "smtp_port": 25,
               "smtp_userid": None,
               "smtp_password": {'value': "test", "parameter_type": "slot"},
               "from_email": {"value": "test@demo.com", "parameter_type": "intent"},
               "to_email": {"value": "to_email", "parameter_type": "slot"},
               "subject": "Test Subject",
               "response": "Test Response",
               "tls": False
               }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/email",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422

    request = {"action_name": "email_config_invalid_parameter_type",
               "smtp_url": "test.test.com",
               "smtp_port": 25,
               "smtp_userid": None,
               "smtp_password": {'value': "test", "parameter_type": "slot"},
               "from_email": {"value": "", "parameter_type": "slot"},
               "to_email": {"value": ["test@demo.com"], "parameter_type": "value"},
               "subject": "Test Subject",
               "response": "Test Response",
               "tls": False
               }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/email",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [{'loc': ['body', 'from_email', '__root__'],
                                  'msg': 'Provide name of the slot as value', 'type': 'value_error'}]
    assert str(actual['message']).__contains__("Provide name of the slot as value")

    request = {"action_name": "email_config_invalid_parameter_type",
               "smtp_url": "test.test.com",
               "smtp_port": 25,
               "smtp_userid": None,
               "smtp_password": {'value': "test", "parameter_type": "key_vault"},
               "from_email": {"value": "", "parameter_type": "value"},
               "to_email": {"value": ["test@demo.com"], "parameter_type": "value"},
               "subject": "Test Subject",
               "response": "Test Response",
               "tls": False
               }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/email",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == 'Invalid From or To email address'


def test_list_email_actions():
    response = client.get(
        f"/api/bot/{pytest.bot}/action/email",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]) == 3
    [action.pop("_id") for action in actual["data"]]
    assert actual["data"] == [
        {
            "action_name": "email_config",
            "smtp_url": "test.test.com",
            "smtp_port": 25,
            "smtp_password": {
                "_cls": "CustomActionRequestParameters",
                "key": "smtp_password",
                "encrypt": False,
                "value": "test",
                "parameter_type": "value",
            },
           'from_email': {'_cls': 'CustomActionRequestParameters', 'encrypt': False,
                          'value': 'from_email', 'parameter_type': 'slot'},
           'subject': 'Test Subject',
           'to_email': {'_cls': 'CustomActionParameters', 'encrypt': False,
                        'value': ['test@test.com', 'test1@test.com'], 'parameter_type': 'value'},
           'response': 'Test Response',
            'tls': False
        },
        {
            "action_name": "email_config_with_slot",
            "smtp_url": "test.test.com",
            "smtp_port": 25,
            "smtp_password": {
                "_cls": "CustomActionRequestParameters",
                "key": "smtp_password",
                "encrypt": False,
                "value": "test",
                "parameter_type": "slot",
            },
           'from_email': {'_cls': 'CustomActionRequestParameters', 'encrypt': False,
                          'value': 'test@demo.com', 'parameter_type': 'value'},
           'subject': 'Test Subject',
           'to_email': {'_cls': 'CustomActionParameters', 'encrypt': False, 'value': 'to_email',
                        'parameter_type': 'slot'},
            'response': 'Test Response',
            "tls": False,
        },
        {
            "action_name": "email_config_with_key_vault",
            "smtp_url": "test.test.com",
            "smtp_port": 25,
            "smtp_password": {
                "_cls": "CustomActionRequestParameters",
                "key": "smtp_password",
                "encrypt": False,
                "value": "test",
                "parameter_type": "key_vault",
            },
            'from_email': {'_cls': 'CustomActionRequestParameters', 'encrypt': False,
                           'value': 'test@demo.com', 'parameter_type': 'value'},
            'subject': 'Test Subject',
            'to_email': {'_cls': 'CustomActionParameters', 'encrypt': False, 'value': 'to_email',
                         'parameter_type': 'slot'},
            'response': 'Test Response',
            "tls": False,
        },
    ]


@patch("kairon.shared.utils.SMTP", autospec=True)
def test_edit_email_action(mock_smtp):
    request = {
        "action_name": "email_config",
        "smtp_url": "test.test.com",
        "smtp_port": 25,
        "smtp_userid": None,
        "smtp_password": {"value": "test"},
        "from_email": {"value": "test@demo.com", "parameter_type": "value"},
        "to_email": {"value": "to_email", "parameter_type": "slot"},
        "subject": "Test Subject",
        "response": "Test Response",
        "tls": False,
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/email",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action updated"


@patch("kairon.shared.utils.SMTP", autospec=True)
def test_edit_email_action_different_parameter_type(mock_smtp):
    request = {
        "action_name": "email_config_with_slot",
        "smtp_url": "test.test.com",
        "smtp_port": 25,
        "smtp_userid": None,
        "smtp_password": {"value": "test", "parameter_type": "slot"},
        "from_email": {"value": "from_email", "parameter_type": "slot"},
        "to_email": {"value": ["test@test.com", "test1@test.com"], "parameter_type": "value"},
        "subject": "Test Subject",
        "response": "Test Response",
        "tls": False,
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/email",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action updated"

    request = {
        "action_name": "email_config_with_key_vault",
        "smtp_url": "test.test.com",
        "smtp_port": 25,
        "smtp_userid": None,
        "smtp_password": {"value": "test", "parameter_type": "key_vault"},
        "from_email": {"value": "test@demo.com", "parameter_type": "value"},
        "to_email": {"value": "to_email", "parameter_type": "slot"},
        "subject": "Test Subject",
        "response": "Test Response",
        "tls": False,
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/email",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action updated"


@patch("kairon.shared.utils.SMTP", autospec=True)
def test_edit_email_action_invalid_parameter_type(mock_smtp):
    request = {
        "action_name": "email_config_with_slot",
        "smtp_url": "test.test.com",
        "smtp_port": 25,
        "smtp_userid": None,
        "smtp_password": {'value': "test", "parameter_type": "slot"},
        "from_email": {"value": "test@demo.com", "parameter_type": "intent"},
        "to_email": {"value": "to_email", "parameter_type": "slot"},
        "subject": "Test Subject",
        "response": "Test Response",
        "tls": False
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/email",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422


@patch("kairon.shared.utils.SMTP", autospec=True)
def test_edit_email_action_invalid_parameter_type_1(mock_smtp):
    request = {"action_name": "email_config_with_slot",
               "smtp_url": "test.test.com",
               "smtp_port": 25,
               "smtp_userid": None,
               "smtp_password": {'value': "test", "parameter_type": "slot"},
               "from_email": {"value": "test@demo.com", "parameter_type": "value"},
               "to_email": {"value": "to_email", "parameter_type": "intent"},
               "subject": "Test Subject",
               "response": "Test Response",
               "tls": False
               }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/email",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422

    request = {"action_name": "email_config_with_slot",
               "smtp_url": "test.test.com",
               "smtp_port": 25,
               "smtp_userid": None,
               "smtp_password": {'value': "test", "parameter_type": "slot"},
               "from_email": {"value": "test@demo.com", "parameter_type": "value"},
               "to_email": {"value": "", "parameter_type": "slot"},
               "subject": "Test Subject",
               "response": "Test Response",
               "tls": False
               }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/email",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [{'loc': ['body', 'to_email', '__root__'],
                                  'msg': 'Provide name of the slot as value', 'type': 'value_error'}]
    assert str(actual['message']).__contains__("Provide name of the slot as value")

    request = {"action_name": "email_config_with_slot",
               "smtp_url": "test.test.com",
               "smtp_port": 25,
               "smtp_userid": None,
               "smtp_password": {'value': "test", "parameter_type": "key_vault"},
               "from_email": {"value": "test@demo.com", "parameter_type": "value"},
               "to_email": {"value": "test@demo.com", "parameter_type": "value"},
               "subject": "Test Subject",
               "response": "Test Response",
               "tls": False
               }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/email",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [{'loc': ['body', 'to_email', '__root__'],
                                  'msg': 'Provide list of emails as value', 'type': 'value_error'}]
    assert str(actual['message']).__contains__("Provide list of emails as value")

    request = {"action_name": "email_config_with_slot",
               "smtp_url": "test.test.com",
               "smtp_port": 25,
               "smtp_userid": None,
               "smtp_password": {'value': "test", "parameter_type": "slot"},
               "from_email": {"value": "test@demo.com", "parameter_type": "intent"},
               "to_email": {"value": "to_email", "parameter_type": "slot"},
               "subject": "Test Subject",
               "response": "Test Response",
               "tls": False
               }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/email",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422

    request = {"action_name": "email_config_with_slot",
               "smtp_url": "test.test.com",
               "smtp_port": 25,
               "smtp_userid": None,
               "smtp_password": {'value': "test", "parameter_type": "slot"},
               "from_email": {"value": "", "parameter_type": "slot"},
               "to_email": {"value": ["test@demo.com"], "parameter_type": "value"},
               "subject": "Test Subject",
               "response": "Test Response",
               "tls": False
               }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/email",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [{'loc': ['body', 'from_email', '__root__'],
                                  'msg': 'Provide name of the slot as value', 'type': 'value_error'}]
    assert str(actual['message']).__contains__("Provide name of the slot as value")

    request = {"action_name": "email_config_with_slot",
               "smtp_url": "test.test.com",
               "smtp_port": 25,
               "smtp_userid": None,
               "smtp_password": {'value': "test", "parameter_type": "key_vault"},
               "from_email": {"value": "", "parameter_type": "value"},
               "to_email": {"value": ["test@demo.com"], "parameter_type": "value"},
               "subject": "Test Subject",
        "response": "Test Response",
        "tls": False,
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/email",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == 'Invalid From or To email address'


@patch("kairon.shared.utils.SMTP", autospec=True)
def test_edit_email_action_does_not_exists(mock_smtp):
    request = {
        "action_name": "email_config1",
        "smtp_url": "test.test.com",
        "smtp_port": 25,
        "smtp_userid": None,
        "smtp_password": {"value": "test"},
        "from_email": {"value": "test@demo.com", "parameter_type": "value"},
        "to_email": {"value": "to_email", "parameter_type": "slot"},
        "subject": "Test Subject",
        "response": "Test Response",
        "tls": False,
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/email",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == 'Action with name "email_config1" not found'


def test_delete_email_action_not_exists():
    response = client.delete(
        f"/api/bot/{pytest.bot}/action/non_existant",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == 'Action with name "non_existant" not found'


def test_delete_email_action():
    response = client.delete(
        f"/api/bot/{pytest.bot}/action/email_config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action deleted"


def test_list_google_search_action_one():
    response = client.get(
        f"/api/bot/{pytest.bot}/action/googlesearch",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]) == 1


def test_add_google_search_action():
    action = {
        "name": "google_custom_search",
        "api_key": {"value": "12345678"},
        "search_engine_id": "asdfg:123456",
        "failure_response": "I have failed to process your request",
        "website": "https://www.google.com",
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/googlesearch",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action added"


def test_add_google_search_exists():
    action = {
        "name": "google_custom_search",
        "api_key": {"value": "12345678"},
        "search_engine_id": "asdfg:123456",
        "failure_response": "I have failed to process your request",
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/googlesearch",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Action exists!"


def test_add_google_search_invalid_parameters():
    action = {
        "name": "google_custom_search",
        "api_key": {"value": "12345678"},
        "search_engine_id": "asdfg:123456",
        "num_results": 0,
        "failure_response": "I have failed to process your request",
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/googlesearch",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "num_results"],
            "msg": "num_results must be greater than or equal to 1!",
            "type": "value_error",
        }
    ]


def test_add_google_search_different_parameter_types():
    action = {
        "name": "google_custom_search_slot",
        "api_key": {"value": "12345678", "parameter_type": "slot"},
        "search_engine_id": "asdfg:123456",
        "failure_response": "I have failed to process your request",
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/googlesearch",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action added"

    action = {
        "name": "google_custom_search_key_vault",
        "api_key": {"value": "12345678", "parameter_type": "key_vault"},
        "search_engine_id": "asdfg:123456",
        "failure_response": "I have failed to process your request",
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/googlesearch",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action added"


def test_add_google_search_invalid_parameter_types():
    action = {
        "name": "google_custom_search_slot",
        "api_key": {"value": "12345678", "parameter_type": "chat_log"},
        "search_engine_id": "asdfg:123456",
        "failure_response": "I have failed to process your request",
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/googlesearch",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_edit_google_search_action_not_exists():
    action = {
        "name": "custom_search",
        "api_key": {"value": "12345678"},
        "search_engine_id": "asdfg:123456",
        "failure_response": "I have failed to process your request",
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/googlesearch",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert (
            actual["message"] == 'Google search action with name "custom_search" not found'
    )


def test_edit_google_search_action():
    action = {
        "name": "google_custom_search",
        "api_key": {"value": "1234567889"},
        "search_engine_id": "asdfg:12345689",
        "failure_response": "Failed to perform search",
        "website": "https://nimblework.com",
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/googlesearch",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action updated"


def test_edit_google_search_action_different_parameter_types():
    action = {
        "name": "google_custom_search_slot",
        "api_key": {"value": "1234567889", "parameter_type": "key_vault"},
        "search_engine_id": "asdfg:12345689",
        "failure_response": "Failed to perform search",
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/googlesearch",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action updated"

    action = {
        "name": "google_custom_search_key_vault",
        "api_key": {"value": "1234567889", "parameter_type": "slot"},
        "search_engine_id": "asdfg:12345689",
        "failure_response": "Failed to perform search",
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/googlesearch",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action updated"


def test_edit_google_search_action_invalid_parameter_type():
    action = {
        "name": "google_custom_search_key_vault",
        "api_key": {"value": "12345678", "parameter_type": "user_message"},
        "search_engine_id": "asdfg:123456",
        "failure_response": "I have failed to process your request",
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/googlesearch",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_list_google_search_action():
    response = client.get(
        f"/api/bot/{pytest.bot}/action/googlesearch",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]) == 4
    actual["data"][0].pop("_id")
    assert actual["data"][1]["name"] == "google_custom_search"
    assert actual["data"][1]["api_key"] == {
        "_cls": "CustomActionRequestParameters",
        "encrypt": False,
        "key": "api_key",
        "parameter_type": "value",
        "value": "1234567889",
    }
    assert actual["data"][1]["search_engine_id"] == "asdfg:12345689"
    assert actual["data"][1]["failure_response"] == "Failed to perform search"
    assert actual["data"][1]["website"] == "https://nimblework.com"
    assert actual["data"][1]["num_results"] == 1
    assert actual["data"][1]["dispatch_response"]
    assert not actual["data"][1].get("set_slot")


def test_delete_google_search_action():
    response = client.delete(
        f"/api/bot/{pytest.bot}/action/google_custom_search",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action deleted"


def test_delete_google_search_action_not_exists():
    response = client.delete(
        f"/api/bot/{pytest.bot}/action/google_custom_search",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == 'Action with name "google_custom_search" not found'


def test_add_web_search_action():
    action = {
        "name": "public_custom_search",
        "dispatch_response": False,
        "set_slot": "public_search_result",
        "failure_response": "I have failed to process your request",
        "website": "https://www.google.com",
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/websearch",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action added"


def test_add_web_search_exists():
    action = {
        "name": "public_custom_search",
        "dispatch_response": False,
        "set_slot": "public_search_result",
        "failure_response": "I have failed to process your request",
        "website": "https://www.google.com",
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/websearch",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Action exists!"


def test_add_web_search_invalid_parameters_top_n():
    action = {
        "name": "public_custom_search_two",
        "topn": 0,
        "dispatch_response": False,
        "set_slot": "public_search_result",
        "failure_response": "I have failed to process your request",
        "website": "https://www.google.com",
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/websearch",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "topn"],
            "msg": "topn must be greater than or equal to 1!",
            "type": "value_error",
        }
    ]


def test_add_web_search_invalid_parameters_name():
    action = {
        "name": "",
        "topn": 1,
        "dispatch_response": False,
        "set_slot": "public_search_result",
        "failure_response": "I have failed to process your request",
        "website": "https://www.google.com",
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/websearch",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {"loc": ["body", "name"], "msg": "name is required", "type": "value_error"}
    ]


def test_edit_web_search_action_not_exists():
    action = {
        "name": "custom_search",
        "failure_response": "I have failed to process your request",
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/websearch",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert (
            actual["message"] == 'Public search action with name "custom_search" not found'
    )


def test_edit_web_search_action():
    action = {
        "name": "public_custom_search",
        "dispatch_response": False,
        "set_slot": "public_search_result",
        "failure_response": "Failed to perform public search",
        "website": "https://nimblework.com",
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/websearch",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action updated"


def test_list_web_search_action():
    response = client.get(
        f"/api/bot/{pytest.bot}/action/websearch",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]) == 1
    actual["data"][0].pop("_id")
    assert actual["data"][0]["name"] == "public_custom_search"
    assert actual["data"][0]["failure_response"] == "Failed to perform public search"
    assert actual["data"][0]["website"] == "https://nimblework.com"
    assert actual["data"][0]["topn"] == 1
    assert not actual["data"][0]["dispatch_response"]
    assert actual["data"][0].get("set_slot")


def test_delete_web_search_action():
    response = client.delete(
        f"/api/bot/{pytest.bot}/action/public_custom_search",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action deleted"


def test_delete_web_search_action_not_exists():
    response = client.delete(
        f"/api/bot/{pytest.bot}/action/public_custom_search",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == 'Action with name "public_custom_search" not found'


def test_list_hubspot_forms_action_no_actions():
    response = client.get(
        f"/api/bot/{pytest.bot}/action/hubspot/forms",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]) == 0


def test_add_hubspot_forms_action():
    action = {
        "name": "action_hubspot_forms",
        "portal_id": "12345678",
        "form_guid": "asdfg:123456",
        "fields": [
            {"key": "email", "value": "email_slot", "parameter_type": "slot"},
            {"key": "firstname", "value": "firstname_slot", "parameter_type": "slot"},
        ],
        "response": "Form submitted",
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/hubspot/forms",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action added"


def test_add_hubspot_forms_action_invalid_param_type():
    action = {
        "name": "action_hubspot_forms",
        "portal_id": "12345678",
        "form_guid": "asdfg:123456",
        "fields": [
            {"key": "email", "value": "email_slot", "parameter_type": "header"},
            {"key": "firstname", "value": "firstname_slot", "parameter_type": "slot"},
        ],
        "response": "Form submitted",
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/hubspot/forms",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [{'loc': ['body', 'fields', 0, 'parameter_type'],
                                  'msg': "value is not a valid enumeration member; permitted: 'value', 'slot', 'sender_id', 'user_message', 'latest_message', 'intent', 'chat_log', 'key_vault'",
                                  'type': 'type_error.enum', 'ctx': {
            'enum_values': ['value', 'slot', 'sender_id', 'user_message', 'latest_message', 'intent', 'chat_log',
                            'key_vault']}}]


def test_add_hubspot_forms_exists():
    action = {
        "name": "action_hubspot_forms",
        "portal_id": "12345678",
        "form_guid": "asdfg:123456",
        "fields": [
            {"key": "email", "value": "email_slot", "parameter_type": "slot"},
            {"key": "firstname", "value": "firstname_slot", "parameter_type": "slot"},
        ],
        "response": "Form submitted",
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/hubspot/forms",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Action exists!"


def test_edit_hubspot_forms_action_not_exists():
    action = {
        "name": "hubspot_forms_action",
        "portal_id": "12345678",
        "form_guid": "asdfg:123456",
        "fields": [
            {"key": "email", "value": "email_slot", "parameter_type": "slot"},
            {"key": "firstname", "value": "firstname_slot", "parameter_type": "slot"},
        ],
        "response": "Form submitted",
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/hubspot/forms",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == 'Action with name "hubspot_forms_action" not found'


def test_edit_hubspot_forms_action():
    action = {
        "name": "action_hubspot_forms",
        "portal_id": "123456785787",
        "form_guid": "asdfg:12345678787",
        "fields": [
            {"key": "email", "value": "email_slot", "parameter_type": "slot"},
            {"key": "fullname", "value": "fullname_slot", "parameter_type": "slot"},
            {"key": "company", "value": "digite", "parameter_type": "value"},
            {"key": "phone", "value": "phone_slot", "parameter_type": "slot"},
        ],
        "response": "Hubspot Form submitted",
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/hubspot/forms",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action updated"


def test_list_hubspot_forms_action():
    response = client.get(
        f"/api/bot/{pytest.bot}/action/hubspot/forms",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]) == 1
    actual["data"][0].pop("_id")
    assert actual["data"][0]["name"] == "action_hubspot_forms"
    assert actual["data"][0]["portal_id"] == "123456785787"
    assert actual["data"][0]["form_guid"] == "asdfg:12345678787"
    assert actual["data"][0]["fields"] == [
        {
            "_cls": "HttpActionRequestBody",
            "key": "email",
            "value": "email_slot",
            "parameter_type": "slot",
            "encrypt": False,
        },
        {
            "_cls": "HttpActionRequestBody",
            "key": "fullname",
            "value": "fullname_slot",
            "parameter_type": "slot",
            "encrypt": False,
        },
        {
            "_cls": "HttpActionRequestBody",
            "key": "company",
            "value": "digite",
            "parameter_type": "value",
            "encrypt": False,
        },
        {
            "_cls": "HttpActionRequestBody",
            "key": "phone",
            "value": "phone_slot",
            "parameter_type": "slot",
            "encrypt": False,
        },
    ]
    assert actual["data"][0]["response"] == "Hubspot Form submitted"


def test_delete_hubspot_forms_action():
    response = client.delete(
        f"/api/bot/{pytest.bot}/action/action_hubspot_forms",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action deleted"


def test_get_kairon_two_stage_fallback_action():
    response = client.get(
        f"/api/bot/{pytest.bot}/action/fallback/two_stage",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] == []
    assert not actual["message"]


def test_add_kairon_two_stage_fallback_action_error():
    action = {"trigger_rules": []}
    response = client.post(
        f"/api/bot/{pytest.bot}/action/fallback/two_stage",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "__root__"],
            "msg": "One of text_recommendations or trigger_rules should be defined",
            "type": "value_error",
        }
    ]

    action = {
        "text_recommendations": {"count": -1},
        "trigger_rules": [{"text": "hi", "payload": "greet"}],
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/fallback/two_stage",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "__root__"],
            "msg": "count cannot be negative",
            "type": "value_error",
        }
    ]


def test_edit_kairon_two_stage_fallback_action_not_exists():
    action = {
        "trigger_rules": [{"text": "Hi", "payload": "kairon_two_stage_fallback_action"}]
    }

    response = client.put(
        f"/api/bot/{pytest.bot}/action/fallback/two_stage",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert (
            actual["message"] == f'Action with name "{KAIRON_TWO_STAGE_FALLBACK}" not found'
    )


def test_add_kairon_two_stage_fallback_action():
    action = {
        "fallback_message": "I could not understand you! Did you mean any of the suggestions below?"
                            " Or else please rephrase your question.",
        "text_recommendations": {"count": 0, "use_intent_ranking": True},
        "trigger_rules": [{"text": "Hi", "payload": "greet"}],
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/fallback/two_stage",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action added!"


def test_add_kairon_two_stage_fallback_action_exists():
    action = {"trigger_rules": [{"text": "Hi", "payload": "greet"}]}
    response = client.post(
        f"/api/bot/{pytest.bot}/action/fallback/two_stage",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Action exists!"


def test_edit_kairon_two_stage_fallback_action_action():
    action = {
        "fallback_message": "I could not understand you! Did you mean any of the suggestions below?"
                            " Or else please rephrase your question.",
        "text_recommendations": {"count": 4},
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/fallback/two_stage",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action updated!"


def test_get_kairon_two_stage_fallback_action_1():
    response = client.get(
        f"/api/bot/{pytest.bot}/action/fallback/two_stage",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"][0].get("timestamp") is None
    actual["data"][0].pop("_id")
    assert actual["data"] == [
        {
            "name": "kairon_two_stage_fallback",
            "text_recommendations": {"count": 4, "use_intent_ranking": False},
            "trigger_rules": [],
            "fallback_message": "I could not understand you! Did you mean any of the suggestions"
                                " below? Or else please rephrase your question.",
        }
    ]


def test_delete_kairon_two_stage_fallback_action():
    response = client.delete(
        f"/api/bot/{pytest.bot}/action/{KAIRON_TWO_STAGE_FALLBACK}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action deleted"


def test_get_kairon_two_stage_fallback_action_2():
    response = client.get(
        f"/api/bot/{pytest.bot}/action/fallback/two_stage",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] == []


def test_disable_integration_token():
    response = client.put(
        f"/api/auth/{pytest.bot}/integration/token",
        json={"name": "integration 3", "status": "inactive"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Integration status updated!"


def test_list_integrations_after_disable():
    response = client.get(
        f"/api/auth/{pytest.bot}/integration/token/list",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"][0]["name"] == "integration 1"
    assert actual["data"][0]["user"] == "integ1@gmail.com"
    assert actual["data"][0]["iat"]
    assert actual["data"][0]["status"] == "active"
    assert actual["data"][0]["role"] == "designer"
    assert actual["data"][1]["name"] == "integration 3"
    assert actual["data"][1]["user"] == "integ1@gmail.com"
    assert actual["data"][1]["iat"]
    assert actual["data"][1]["status"] == "inactive"
    assert actual["data"][1]["role"] == "designer"
    assert actual["success"]
    assert actual["error_code"] == 0


def test_use_inactive_token():
    response = client.get(
        f"/api/bot/{pytest.bot}/intents",
        headers={
            "Authorization": pytest.disable_token,
            "X-USER": "integration",
        },
    )
    actual = response.json()
    assert actual["message"] == "Access to bot is denied"
    assert not actual["success"]
    assert actual["error_code"] == 401

    response = client.put(
        f"/api/auth/{pytest.bot}/integration/token",
        json={"name": "integration 3", "status": "active", "role": "tester"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0

    response = client.get(
        f"/api/bot/{pytest.bot}/intents",
        headers={
            "Authorization": pytest.disable_token,
            "X-USER": "integration",
        },
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]


def test_delete_integration_token():
    response = client.put(
        f"/api/auth/{pytest.bot}/integration/token",
        json={"name": "integration 3", "status": "deleted"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Integration status updated!"

    response = client.get(
        f"/api/auth/{pytest.bot}/integration/token/list",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert len(actual["data"]) == 1


def test_integration_token_from_one_bot_on_another_bot():
    response = client.post(
        "/api/account/bot",
        json={"name": "demo-bot"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    assert response["message"] == "Bot created"
    assert response["error_code"] == 0
    assert response["success"]

    response = client.get(
        "/api/account/bot",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    assert len(response["data"]["account_owned"]) == 1
    assert len(response["data"]["shared"]) == 3
    bot1 = response["data"]["account_owned"][0]["_id"]
    bot2 = response["data"]["shared"][0]["_id"]

    response = client.post(
        f"/api/auth/{bot2}/integration/token",
        json={"name": "integration 4", "expiry_minutes": 1440},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    token = response.json()
    assert token["success"]
    assert token["error_code"] == 0
    assert token["data"]["access_token"]
    assert token["data"]["token_type"]

    response = client.get(
        f"/api/bot/{bot1}/intents",
        headers={
            "Authorization": token["data"]["token_type"]
                             + " "
                             + token["data"]["access_token"],
            "X-USER": "integration",
        },
    )
    actual = response.json()
    assert actual["message"] == "Access to bot is denied"
    assert not actual["success"]
    assert actual["error_code"] == 401

    response = client.get(
        f"/api/bot/{pytest.bot}/intents",
        headers={
            "Authorization": token["data"]["token_type"]
                             + " "
                             + token["data"]["access_token"],
            "X-USER": "integration",
        },
    )
    actual = response.json()
    assert (
            actual["message"]
            == "['owner', 'admin', 'designer', 'tester'] access is required to perform this operation on the bot"
    )
    assert not actual["success"]
    assert actual["error_code"] == 401

    response = client.post(
        f"/api/bot/{pytest.bot}/chat",
        json={"data": "hi"},
        headers={
            "Authorization": token["data"]["token_type"]
                             + " "
                             + token["data"]["access_token"],
            "X-USER": "integration",
        },
    )
    actual = response.json()
    assert actual["error_code"] != 401


def test_integration_limit_reached(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(bot=pytest.bot, user="integration@demo.ai", integrations_per_user_limit=2)

    monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)

    response = client.post(
        f"/api/auth/{pytest.bot}/integration/token",
        json={"name": "integration 4", "expiry_minutes": 1440},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    token = response.json()
    assert not token["success"]
    assert token["error_code"] == 422
    assert token["message"] == "Integrations limit reached!"
    assert not token["data"]


def test_list_integrations():
    response = client.get(
        f"/api/auth/{pytest.bot}/integration/token/list",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"][0]["name"] == "integration 1"
    assert actual["data"][0]["user"] == "integ1@gmail.com"
    assert actual["data"][0]["iat"]
    assert actual["data"][0]["status"] == "active"
    assert actual["data"][1]["name"] == "integration 4"
    assert actual["data"][1]["user"] == "integ1@gmail.com"
    assert actual["data"][1]["iat"]
    assert actual["data"][1]["expiry"]
    assert actual["data"][1]["status"] == "active"
    assert actual["success"]
    assert actual["error_code"] == 0


def test_add_channel_config_error():
    data = {
        "connector_type": "custom",
        "config": {
            "bot_user_oAuth_token": "xoxb-801939352912-801478018484-v3zq6MYNu62oSs8vammWOY8K",
            "slack_signing_secret": "79f036b9894eef17c064213b90d1042b",
            "client_id": "3396830255712.3396861654876869879",
            "client_secret": "cf92180a7634d90bf42a217408376878",
        },
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/channels/add",
        json=data,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "__root__"],
            "msg": "Invalid channel type custom",
            "type": "value_error",
        }
    ]

    data = {
        "connector_type": "slack",
        "config": {"slack_signing_secret": "79f036b9894eef17c064213b90d1042b"},
    }

    response = client.post(
        f"/api/bot/{pytest.bot}/channels/add",
        json=data,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "__root__"],
            "msg": "Missing ['bot_user_oAuth_token', 'slack_signing_secret', 'client_id', 'client_secret'] all or any in config",
            "type": "value_error",
        }
    ]

    data = {
        "connector_type": "slack",
        "config": {
            "bot_user_oAuth_token": "xoxb-801939352912-801478018484-v3zq6MYNu62oSs8vammWOY8K"
        },
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/channels/add",
        json=data,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "__root__"],
            "msg": "Missing ['bot_user_oAuth_token', 'slack_signing_secret', 'client_id', 'client_secret'] all or any in config",
            "type": "value_error",
        }
    ]

    data = {
        "connector_type": "slack",
        "config": {
            "bot_user_oAuth_token": "xoxb-801939352912-801478018484-v3zq6MYNu62oSs8vammWOY8K",
            "slack_signing_secret": "79f036b9894eef17c064213b90d1042b",
            "client_id": "3396830255712.3396861654876869879",
            "client_secret": "cf92180a7634d90bf42a217408376878",
            "is_primary": False,
        },
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/channels/add",
        json=data,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert (
            actual["message"]
            == "Cannot edit secondary slack app. Please delete and install the app again using oAuth."
    )


def test_add_bot_with_template_name(monkeypatch):
    from kairon.shared.admin.data_objects import BotSecrets

    def mock_reload_model(*args, **kwargs):
        mock_reload_model.called_with = (args, kwargs)
        return None

    monkeypatch.setattr(Utility, "reload_model", mock_reload_model)
    monkeypatch.setitem(Utility.environment["llm"], "key", "secret_value")

    response = client.post(
        "/api/account/bot",
        json={"name": "hi-hello-gpt-bot", "from_template": "Hi-Hello-GPT"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    response = response.json()
    assert response["message"] == "Bot created"
    assert response["error_code"] == 0
    assert response["success"]
    assert response["data"]["bot_id"]
    bot_id = response["data"]["bot_id"]
    response = client.get(
        url=f"/api/bot/{bot_id}/actions",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not DeepDiff(
        actual["data"],
        {
            "prompt_action": ["kairon_faq_action"],
            "web_search_action": ["google_search_action"],
            "utterances": ["utter_please_rephrase", "utter_default"],
            "http_action": [],
            "slot_set_action": [],
            "form_validation_action": [],
            "email_action": [],
            "google_search_action": [],
            "jira_action": [],
            "zendesk_action": [],
            "pipedrive_leads_action": [],
            "hubspot_forms_action": [],
            "two_stage_fallback": [],
            "kairon_bot_response": [],
            "razorpay_action": [],
            "database_action": [],
            "actions": [],
            "pyscript_action": [],
            "live_agent_action": [],
        },
        ignore_order=True,
    )
    bot_secret = (
        BotSecrets.objects(bot=bot_id, secret_type="gpt_key").get().to_mongo().to_dict()
    )
    assert bot_secret["secret_type"] == "gpt_key"
    assert Utility.decrypt_message(bot_secret["value"]) == "secret_value"
    assert len(mock_reload_model.called_with[0]) == 2
    assert mock_reload_model.called_with[0][0] == bot_id
    assert mock_reload_model.called_with[0][1] == "integ1@gmail.com"


def test_set_templates_with_sysadmin_as_user():
    response = client.post(
        f"/api/bot/{pytest.bot}/templates/use-case",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"data": "Hi-Hello-GPT"},
    )

    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 0
    assert actual["message"] == "Data applied!"
    assert actual["success"]

    stories = Stories.objects(bot=pytest.bot)
    stories = [{k: v for k, v in story.to_mongo().to_dict().items() if k not in ['_id', 'bot', 'timestamp']} for
               story in stories]

    assert stories == [
        {'block_name': 'greet', 'start_checkpoints': ['STORY_START'], 'end_checkpoints': [],
         'events': [{'name': 'greet', 'type': 'user', 'entities': []},
                    {'name': 'google_search_action', 'type': 'action'},
                    {'name': 'kairon_faq_action', 'type': 'action'}],
         'user': 'sysadmin', 'status': True, 'template_type': 'CUSTOM'},
        {'block_name': 'goodbye', 'start_checkpoints': ['STORY_START'], 'end_checkpoints': [],
         'events': [{'name': 'goodbye', 'type': 'user', 'entities': []},
                    {'name': 'google_search_action', 'type': 'action'},
                    {'name': 'kairon_faq_action', 'type': 'action'}],
         'user': 'sysadmin', 'status': True, 'template_type': 'CUSTOM'}
    ]

    intents = Intents.objects(bot=pytest.bot)
    intents = [{k: v for k, v in intent.to_mongo().to_dict().items() if k not in ['_id', 'bot', 'timestamp']} for
                         intent in intents]

    assert intents == [
        {'name': 'greet', 'user': 'sysadmin', 'status': True, 'is_integration': False, 'use_entities': False},
        {'name': 'goodbye', 'user': 'sysadmin', 'status': True, 'is_integration': False, 'use_entities': False},
        {'name': 'nlu_fallback', 'user': 'sysadmin', 'status': True, 'is_integration': False, 'use_entities': False},
        {'name': 'restart', 'user': 'sysadmin', 'status': True, 'is_integration': False, 'use_entities': True},
        {'name': 'back', 'user': 'sysadmin', 'status': True, 'is_integration': False, 'use_entities': True},
        {'name': 'out_of_scope', 'user': 'sysadmin', 'status': True, 'is_integration': False, 'use_entities': True},
        {'name': 'session_start', 'user': 'sysadmin', 'status': True, 'is_integration': False, 'use_entities': True}
    ]

    training_examples = TrainingExamples.objects(bot=pytest.bot)
    training_examples = [{k: v for k, v in example.to_mongo().to_dict().items() if k not in
                          ['_id', 'bot', 'timestamp']} for example in training_examples]

    assert training_examples == [
        {'intent': 'goodbye', 'text': 'bye', 'user': 'sysadmin', 'status': True},
        {'intent': 'goodbye', 'text': 'goodbye', 'user': 'sysadmin', 'status': True},
        {'intent': 'goodbye', 'text': 'see you around', 'user': 'sysadmin', 'status': True},
        {'intent': 'goodbye', 'text': 'see you later', 'user': 'sysadmin', 'status': True},
        {'intent': 'greet', 'text': 'hey', 'user': 'sysadmin', 'status': True},
        {'intent': 'greet', 'text': 'hello', 'user': 'sysadmin', 'status': True},
        {'intent': 'greet', 'text': 'hi', 'user': 'sysadmin', 'status': True},
        {'intent': 'greet', 'text': 'good morning', 'user': 'sysadmin', 'status': True},
        {'intent': 'greet', 'text': 'good evening', 'user': 'sysadmin', 'status': True},
        {'intent': 'greet', 'text': 'hey there', 'user': 'sysadmin', 'status': True}
    ]


def test_add_channel_config(monkeypatch):
    monkeypatch.setitem(
        Utility.environment["model"]["agent"], "url", "http://localhost:5056"
    )
    data = {
        "connector_type": "slack",
        "config": {
            "bot_user_oAuth_token": "xoxb-801939352912-801478018484-v3zq6MYNu62oSs8vammWOY8K",
            "slack_signing_secret": "79f036b9894eef17c064213b90d1042b",
            "client_id": "3396830255712.3396861654876869879",
            "client_secret": "cf92180a7634d90bf42a217408376878",
        },
    }
    with patch("slack_sdk.web.client.WebClient.team_info") as mock_slack_resp:
        mock_slack_resp.return_value = SlackResponse(
            client=None,
            http_verb="POST",
            api_url="https://slack.com/api/team.info",
            req_args={},
            data={
                "ok": True,
                "team": {
                    "id": "T03BNQE7HLX",
                    "name": "helicopter",
                    "avatar_base_url": "https://ca.slack-edge.com/",
                    "is_verified": False,
                },
            },
            headers=dict(),
            status_code=200,
        ).validate()
        response = client.post(
            f"/api/bot/{pytest.bot}/channels/add",
            json=data,
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Channel added"
    assert actual["data"].startswith(
        f"http://localhost:5056/api/bot/slack/{pytest.bot}/e"
    )


def test_add_bot_with_template_with_sysadmin_as_user(monkeypatch):

    def mock_reload_model(*args, **kwargs):
        mock_reload_model.called_with = (args, kwargs)
        return None

    monkeypatch.setattr(Utility, "reload_model", mock_reload_model)
    monkeypatch.setitem(Utility.environment["llm"], "key", "secret_value")

    response = client.post(
        "/api/account/bot",
        json={"name": "gpt-bot", "from_template": "Hi-Hello-GPT"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    response = response.json()
    assert response["message"] == "Bot created"
    assert response["data"] is not None
    assert response["error_code"] == 0
    assert response["success"]
    bot_id = response["data"]["bot_id"]

    stories = Stories.objects(bot=bot_id)
    stories = [{k: v for k, v in story.to_mongo().to_dict().items() if k not in ['_id', 'bot', 'timestamp']} for
               story in stories]

    assert stories == [
        {'block_name': 'greet', 'start_checkpoints': ['STORY_START'], 'end_checkpoints': [],
         'events': [{'name': 'greet', 'type': 'user', 'entities': []},
                    {'name': 'google_search_action', 'type': 'action'},
                    {'name': 'kairon_faq_action', 'type': 'action'}],
         'user': 'sysadmin', 'status': True, 'template_type': 'CUSTOM'},
        {'block_name': 'goodbye', 'start_checkpoints': ['STORY_START'], 'end_checkpoints': [],
         'events': [{'name': 'goodbye', 'type': 'user', 'entities': []},
                    {'name': 'google_search_action', 'type': 'action'},
                    {'name': 'kairon_faq_action', 'type': 'action'}],
         'user': 'sysadmin', 'status': True, 'template_type': 'CUSTOM'}
    ]

    rules = Rules.objects(bot=bot_id)
    rules = [{k: v for k, v in rule.to_mongo().to_dict().items() if k not in ['_id', 'bot', 'timestamp']} for
               rule in rules]

    assert rules == [
        {'block_name': 'ask the user to rephrase whenever they send a message with low nlu confidence',
         'condition_events_indices': [], 'start_checkpoints': ['STORY_START'], 'end_checkpoints': [],
         'events': [{'name': '...', 'type': 'action'},
                    {'name': 'nlu_fallback', 'type': 'user', 'entities': []},
                    {'name': 'google_search_action', 'type': 'action'},
                    {'name': 'kairon_faq_action', 'type': 'action'}],
         'user': 'sysadmin', 'status': True, 'template_type': 'CUSTOM'}
    ]

    utterances = Utterances.objects(bot=bot_id)
    utterances = [{k: v for k, v in utterance.to_mongo().to_dict().items() if k not in ['_id', 'bot', 'timestamp']} for
             utterance in utterances]

    assert utterances == [
        {'name': 'utter_please_rephrase', 'user': 'sysadmin', 'status': True},
        {'name': 'utter_default', 'user': 'sysadmin', 'status': True}
    ]

    intents = Intents.objects(bot=bot_id)
    intents = [{k: v for k, v in intent.to_mongo().to_dict().items() if k not in ['_id', 'bot', 'timestamp']} for
               intent in intents]

    assert intents == [
        {'name': 'greet', 'user': 'sysadmin', 'status': True, 'is_integration': False, 'use_entities': False},
        {'name': 'goodbye', 'user': 'sysadmin', 'status': True, 'is_integration': False, 'use_entities': False},
        {'name': 'nlu_fallback', 'user': 'sysadmin', 'status': True, 'is_integration': False, 'use_entities': False},
        {'name': 'restart', 'user': 'sysadmin', 'status': True, 'is_integration': False, 'use_entities': True},
        {'name': 'back', 'user': 'sysadmin', 'status': True, 'is_integration': False, 'use_entities': True},
        {'name': 'out_of_scope', 'user': 'sysadmin', 'status': True, 'is_integration': False, 'use_entities': True},
        {'name': 'session_start', 'user': 'sysadmin', 'status': True, 'is_integration': False, 'use_entities': True}
    ]

    responses = Responses.objects(bot=bot_id)
    responses = [{k: v for k, v in response.to_mongo().to_dict().items() if k not in
                  ['_id', 'bot', 'timestamp']} for response in responses]

    assert responses == [
        {'name': 'utter_please_rephrase',
         'text': {'text': "I'm sorry, I didn't quite understand that. Could you rephrase?"},
         'user': 'sysadmin', 'status': True},
        {'name': 'utter_default', 'text': {'text': "Sorry I didn't get that. Can you rephrase?"},
         'user': 'sysadmin', 'status': True}
    ]


def test_add_bot_without_template(monkeypatch):
    def mock_reload_model(*args, **kwargs):
        mock_reload_model.called_with = (args, kwargs)
        return None

    monkeypatch.setattr(Utility, "reload_model", mock_reload_model)
    monkeypatch.setitem(Utility.environment["llm"], "key", "secret_value")

    response = client.post(
        "/api/account/bot",
        json={"name": "normal-bot"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    response = response.json()
    assert response["message"] == "Bot created"
    assert response["data"] is not None
    assert response["error_code"] == 0
    assert response["success"]
    bot_id = response["data"]["bot_id"]

    rules = Rules.objects(bot=bot_id)
    rules = [{k: v for k, v in rule.to_mongo().to_dict().items() if k not in ['_id', 'bot', 'timestamp']} for
             rule in rules]

    assert rules == [
        {'block_name': 'ask the user to rephrase whenever they send a message with low nlu confidence',
         'condition_events_indices': [], 'start_checkpoints': ['STORY_START'], 'end_checkpoints': [],
         'events': [{'name': '...', 'type': 'action'}, {'name': 'nlu_fallback', 'type': 'user'},
                    {'name': 'utter_please_rephrase', 'type': 'action'}],
         'user': 'integ1@gmail.com', 'status': True, 'template_type': 'CUSTOM'},
        {'block_name': 'bye', 'condition_events_indices': [], 'start_checkpoints': ['STORY_START'],
         'end_checkpoints': [],
         'events': [{'name': '...', 'type': 'action'}, {'name': 'bye', 'type': 'user'},
                    {'name': 'utter_bye', 'type': 'action'}], 'user': 'integ1@gmail.com',
         'status': True, 'template_type': 'Q&A'},
        {'block_name': 'greet', 'condition_events_indices': [], 'start_checkpoints': ['STORY_START'],
         'end_checkpoints': [],
         'events': [{'name': '...', 'type': 'action'}, {'name': 'greet', 'type': 'user'},
                    {'name': 'utter_greet', 'type': 'action'}],
         'user': 'integ1@gmail.com', 'status': True, 'template_type': 'Q&A'}
    ]

    utterances = Utterances.objects(bot=bot_id)
    utterances = [{k: v for k, v in utterance.to_mongo().to_dict().items() if k not in ['_id', 'bot', 'timestamp']} for
                  utterance in utterances]

    assert utterances == [
        {'name': 'utter_please_rephrase', 'user': 'integ1@gmail.com', 'status': True},
        {'name': 'utter_default', 'user': 'integ1@gmail.com', 'status': True},
        {'name': 'utter_bye', 'user': 'integ1@gmail.com', 'status': True},
        {'name': 'utter_greet', 'user': 'integ1@gmail.com', 'status': True}
    ]

    intents = Intents.objects(bot=bot_id)
    intents = [{k: v for k, v in intent.to_mongo().to_dict().items() if k not in ['_id', 'bot', 'timestamp']} for
               intent in intents]

    assert intents == [
        {'name': 'bye', 'user': 'integ1@gmail.com', 'status': True, 'is_integration': False, 'use_entities': False},
        {'name': 'greet', 'user': 'integ1@gmail.com', 'status': True, 'is_integration': False, 'use_entities': False}
    ]

    training_examples = TrainingExamples.objects(bot=bot_id)
    training_examples = [{k: v for k, v in training_example.to_mongo().to_dict().items() if k not in
                          ['_id', 'bot', 'timestamp']} for training_example in training_examples]

    assert training_examples == [
        {'intent': 'bye', 'text': 'good bye', 'user': 'integ1@gmail.com', 'status': True},
        {'intent': 'bye', 'text': 'bye', 'user': 'integ1@gmail.com', 'status': True},
        {'intent': 'bye', 'text': 'See you later!', 'user': 'integ1@gmail.com', 'status': True},
        {'intent': 'bye', 'text': 'Goodbye!', 'user': 'integ1@gmail.com', 'status': True},
        {'intent': 'greet', 'text': 'Hi', 'user': 'integ1@gmail.com', 'status': True},
        {'intent': 'greet', 'text': 'Hello', 'user': 'integ1@gmail.com', 'status': True},
        {'intent': 'greet', 'text': 'Greetings', 'user': 'integ1@gmail.com', 'status': True},
        {'intent': 'greet', 'text': 'Hi there', 'user': 'integ1@gmail.com', 'status': True},
        {'intent': 'greet', 'text': 'Good day', 'user': 'integ1@gmail.com', 'status': True},
        {'intent': 'greet', 'text': 'Howdy', 'user': 'integ1@gmail.com', 'status': True},
        {'intent': 'greet', 'text': 'Hey there', 'user': 'integ1@gmail.com', 'status': True},
        {'intent': 'greet', 'text': "What's up?", 'user': 'integ1@gmail.com', 'status': True},
        {'intent': 'greet', 'text': 'Hullo', 'user': 'integ1@gmail.com', 'status': True}
    ]

    responses = Responses.objects(bot=bot_id)
    responses = [{k: v for k, v in response.to_mongo().to_dict().items() if k not in
                  ['_id', 'bot', 'timestamp']} for response in responses]

    assert responses == [
        {'name': 'utter_please_rephrase',
         'text': {'text': "I'm sorry, I didn't quite understand that. Could you rephrase?"},
         'user': 'integ1@gmail.com', 'status': True},
        {'name': 'utter_default', 'text': {'text': "Sorry I didn't get that. Can you rephrase?"},
         'user': 'integ1@gmail.com', 'status': True},
        {'name': 'utter_bye', 'text': {'text': "Take care, I'm here for you if you need anything."},
         'user': 'integ1@gmail.com', 'status': True},
        {'name': 'utter_bye', 'text': {'text': 'Adieu, always here for you.'},
         'user': 'integ1@gmail.com', 'status': True},
        {'name': 'utter_bye', 'text': {'text': "See you later, I'm here to help."},
         'user': 'integ1@gmail.com', 'status': True},
        {'name': 'utter_greet', 'text': {'text': "I'm your AI Assistant, ready to assist"},
         'user': 'integ1@gmail.com', 'status': True},
        {'name': 'utter_greet', 'text': {'text': 'Let me be your AI Assistant and provide you with service'},
         'user': 'integ1@gmail.com', 'status': True}
    ]


@patch("kairon.shared.channels.whatsapp.bsp.dialog360.BSP360Dialog.get_partner_auth_token", autospec=True)
def test_add_template_error(mock_get_partner_auth_token):
    mock_get_partner_auth_token.return_value = "Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIs.ImtpZCI6Ik1EZEZOVFk1UVVVMU9FSXhPRGN3UVVZME9EUTFRVFJDT1.RSRU9VUTVNVGhDTURWRk9UUTNPQSJ9"
    data = {
        "name": "Introduction template",
        "category": "UTILITY",
        "components": [
            {
                "format": "TEXT",
                "text": "New request",
                "type": "HEADER"
            },
            {
                "type": "BODY",
                "text": "Hi {{1}}, thanks for getting in touch with {{2}}. We will process your request get back to you shortly",
                "example": {
                    "body_text": [
                        [
                            "Nupur",
                            "360dialog"
                        ]
                    ]
                }
            },
            {
                "text": "WhatsApp Business API provided by 360dialog",
                "type": "FOOTER"
            }
        ],
        "language": "es_ES",
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/channels/whatsapp/templates/360dialog",
        json={'data': data},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Channel not found!"
    assert actual["data"] == None


@patch("kairon.shared.channels.whatsapp.bsp.dialog360.BSP360Dialog.get_partner_auth_token", autospec=True)
def test_edit_template_error(mock_get_partner_auth_token):
    mock_get_partner_auth_token.return_value = "Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIs.ImtpZCI6Ik1EZEZOVFk1UVVVMU9FSXhPRGN3UVVZME9EUTFRVFJDT1.RSRU9VUTVNVGhDTURWRk9UUTNPQSJ9"
    data = {
        "components": [
            {
                "format": "TEXT",
                "text": "New request",
                "type": "HEADER"
            },
            {
                "type": "BODY",
                "text": "Hi {{1}}, thanks for getting in touch with {{2}}. Let us know your queries!",
                "example": {
                    "body_text": [
                        [
                            "Nupur",
                            "360dialog"
                        ]
                    ]
                }
            },
            {
                "text": "WhatsApp Business API provided by 360dialog",
                "type": "FOOTER"
            }
        ],
        "allow_category_change": False
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/channels/whatsapp/templates/360dialog/test_one_id",
        json={'data': data},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Channel not found!"
    assert actual["data"] == None


@patch("kairon.shared.channels.whatsapp.bsp.dialog360.BSP360Dialog.get_partner_auth_token", autospec=True)
def test_delete_template_error(mock_get_partner_auth_token):
    mock_get_partner_auth_token.return_value = "Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIs.ImtpZCI6Ik1EZEZOVFk1UVVVMU9FSXhPRGN3UVVZME9EUTFRVFJDT1.RSRU9VUTVNVGhDTURWRk9UUTNPQSJ9"
    response = client.delete(
        f"/api/bot/{pytest.bot}/channels/whatsapp/templates/360dialog/test_one_id",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Channel not found!"
    assert actual["data"] == None


def test_list_whatsapp_templates_error():
    response = client.get(
        f"/api/bot/{pytest.bot}/channels/whatsapp/templates/360dialog/list",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Channel not found!"


def test_get_channel_logs():
    from kairon.shared.chat.data_objects import ChannelLogs
    ChannelLogs(
        type=ChannelTypes.WHATSAPP.value,
        status='read',
        data={'id': 'CONVERSATION_ID', 'expiration_timestamp': '1691598412',
              'origin': {'type': 'business_initated'}},
        initiator='business_initated',
        campaign_id='6779002886649302',
        message_id='wamid.HBgLMTIxMTU1NTc5NDcVAgARGBIyRkQxREUxRDJFQUJGMkQ3NDIZ',
        bot=pytest.bot,
        user='integration@demo.ai'
    ).save()
    ChannelLogs(
        type=ChannelTypes.WHATSAPP.value,
        status='delivered',
        data={'id': 'CONVERSATION_ID', 'expiration_timestamp': '1621598412',
              'origin': {'type': 'business_initated'}},
        initiator='business_initated',
        campaign_id='6779002886649302',
        message_id='wamid.HBgLMTIxMTU1NTc5NDcVAgARGBIyRkQxREUxRDJFQUJGMkQ3NDIZ',
        bot=pytest.bot,
        user='integration@demo.ai'
    ).save()
    ChannelLogs(
        type=ChannelTypes.WHATSAPP.value,
        status='sent',
        data={'id': 'CONVERSATION_ID', 'expiration_timestamp': '1631598412',
              'origin': {'type': 'business_initated'}},
        initiator='business_initated',
        campaign_id='6779002886649302',
        message_id='wamid.HBgLMTIxMTU1NTc5NDcVAgARGBIyRkQxREUxRDJFQUJGMkQ3NDIZ',
        bot=pytest.bot,
        user='integration@demo.ai'
    ).save()
    response = client.get(
        f"/api/bot/{pytest.bot}/channels/whatsapp/metrics",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] == [{'campaign_id': '6779002886649302', 'status': {'delivered': 1, 'read': 1, 'sent': 1}}]


@responses.activate
def test_initiate_bsp_onboarding_without_channels(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(whatsapp="360dialog", bot=pytest.bot, user="test_user")

    monkeypatch.setattr(MongoProcessor, "get_bot_settings", _mock_get_bot_settings)
    monkeypatch.setitem(
        Utility.environment["model"]["agent"], "url", "http://kairon-api.digite.com"
    )
    monkeypatch.setitem(
        Utility.environment["channels"]["360dialog"], "partner_id", "f167CmPA"
    )
    url = "https://hub.360dialog.io/api/v2/token"
    responses.add("POST", json={}, url=url, status=500)

    response = client.post(
        f"/api/bot/{pytest.bot}/channels/whatsapp/360dialog/onboarding?clientId=kairon&client=sdfgh5678&channels=[]",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"].startswith(
        "Failed to save channel config, onboarding unsuccessful!"
    )
    assert actual["data"] is None


@responses.activate
def test_initiate_bsp_onboarding_failure(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(whatsapp="360dialog", bot=pytest.bot, user="test_user")

    monkeypatch.setattr(MongoProcessor, "get_bot_settings", _mock_get_bot_settings)
    monkeypatch.setitem(
        Utility.environment["model"]["agent"], "url", "http://kairon-api.digite.com"
    )
    monkeypatch.setitem(
        Utility.environment["channels"]["360dialog"], "partner_id", "f167CmPA"
    )
    url = "https://hub.360dialog.io/api/v2/token"
    responses.add("POST", json={}, url=url, status=500)

    response = client.post(
        f"/api/bot/{pytest.bot}/channels/whatsapp/360dialog/onboarding?clientId=kairon&client=sdfgh5678&channels=['sdfghjk678']",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"].startswith("Failed to get partner auth token: ")
    assert actual["data"] is None


def test_initiate_bsp_onboarding_disabled(monkeypatch):
    monkeypatch.setitem(
        Utility.environment["channels"]["360dialog"], "partner_id", "f167CmPA"
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/channels/whatsapp/360dialog/onboarding?clientId=kairon&client=sdfgh5678&channels=['sdfghjk678']",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert (
            actual["message"]
            == "Feature disabled for this account. Please contact support!"
    )
    assert actual["data"] is None


def test_initiate_bsp_onboarding(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(whatsapp="360dialog", bot=pytest.bot, user="test_user")

    monkeypatch.setattr(MongoProcessor, "get_bot_settings", _mock_get_bot_settings)
    monkeypatch.setitem(
        Utility.environment["model"]["agent"], "url", "http://kairon-api.digite.com"
    )
    monkeypatch.setitem(
        Utility.environment["channels"]["360dialog"], "partner_id", "f167CmPA"
    )

    with patch(
            "kairon.shared.channels.whatsapp.bsp.dialog360.BSP360Dialog.get_account"
    ) as mock_get_account:
        mock_get_account.return_value = "dfghj5678"
        with patch(
                "kairon.shared.channels.whatsapp.bsp.dialog360.BSP360Dialog.generate_waba_key"
        ) as mock_generate_waba_key:
            mock_generate_waba_key.return_value = "dfghjk5678"
            response = client.post(
                f"/api/bot/{pytest.bot}/channels/whatsapp/360dialog/onboarding?clientId=kairon&client=sdfgh5678&channels=['sdfghjk678']",
                headers={
                    "Authorization": pytest.token_type + " " + pytest.access_token
                },
            )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Channel added"
    assert actual["data"].startswith(
        f"http://kairon-api.digite.com/api/bot/whatsapp/{pytest.bot}/e"
    )


def test_post_process(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(whatsapp="360dialog", bot=pytest.bot, user="test_user")

    monkeypatch.setattr(MongoProcessor, "get_bot_settings", _mock_get_bot_settings)
    monkeypatch.setitem(
        Utility.environment["model"]["agent"], "url", "http://kairon-api.digite.com"
    )
    monkeypatch.setitem(
        Utility.environment["channels"]["360dialog"], "partner_id", "f167CmPA"
    )

    with patch(
            "kairon.shared.channels.whatsapp.bsp.dialog360.BSP360Dialog.get_account"
    ) as mock_get_account:
        mock_get_account.return_value = "dfghj5678"
        with patch(
                "kairon.shared.channels.whatsapp.bsp.dialog360.BSP360Dialog.generate_waba_key"
        ) as mock_generate_waba_key:
            mock_generate_waba_key.return_value = "dfghjk5678"
            with patch(
                    "kairon.shared.channels.whatsapp.bsp.dialog360.BSP360Dialog.set_webhook_url",
                    autospec=True,
            ):
                response = client.post(
                    f"/api/bot/{pytest.bot}/channels/whatsapp/360dialog/post_process",
                    headers={
                        "Authorization": pytest.token_type + " " + pytest.access_token
                    },
                )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Credentials refreshed!"
    assert actual["data"].startswith(
        f"http://kairon-api.digite.com/api/bot/whatsapp/{pytest.bot}/e"
    )


@patch("kairon.shared.channels.whatsapp.bsp.dialog360.BSP360Dialog.add_template", autospec=True)
def test_add_template(mock_add_template):
    data = {
        "name": "Introduction template",
        "category": "MARKETING",
        "components": [
            {
                "format": "TEXT",
                "text": "New request",
                "type": "HEADER"
            },
            {
                "type": "BODY",
                "text": "Hi {{1}}, thanks for getting in touch with {{2}}. We will process your request get back to you shortly",
                "example": {
                    "body_text": [
                        [
                            "Nupur",
                            "360dialog"
                        ]
                    ]
                }
            },
            {
                "text": "WhatsApp Business API provided by 360dialog",
                "type": "FOOTER"
            }
        ],
        "language": "es_ES",
        "allow_category_change": True
    }
    api_resp = {
        "id": "594425479261596",
        "status": "PENDING",
        "category": "MARKETING"
    }
    mock_add_template.return_value = api_resp

    response = client.post(
        f"/api/bot/{pytest.bot}/channels/whatsapp/templates/360dialog",
        json={'data': data},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] == {'id': '594425479261596', 'status': 'PENDING', 'category': 'MARKETING'}


@patch("kairon.shared.channels.whatsapp.bsp.dialog360.BSP360Dialog.edit_template", autospec=True)
def test_edit_template(mock_edit_template):
    data = {
        "components": [
            {
                "format": "TEXT",
                "text": "New request",
                "type": "HEADER"
            },
            {
                "type": "BODY",
                "text": "Hi {{1}}, thanks for getting in touch with {{2}}. Let us know your queries!",
                "example": {
                    "body_text": [
                        [
                            "Nupur",
                            "360dialog"
                        ]
                    ]
                }
            },
            {
                "text": "WhatsApp Business API provided by 360dialog",
                "type": "FOOTER"
            }
        ],
        "allow_category_change": False
    }
    api_resp = {
        "success": True
    }
    mock_edit_template.return_value = api_resp

    response = client.put(
        f"/api/bot/{pytest.bot}/channels/whatsapp/templates/360dialog/test_id",
        json={'data': data},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] == [{'success': True}]


@patch("kairon.shared.channels.whatsapp.bsp.dialog360.BSP360Dialog.delete_template", autospec=True)
def test_delete_template(mock_delete_template):
    api_resp = {
        "meta": {
            "developer_message": "template name=Introduction template was deleted",
            "http_code": 200,
            "success": True
        }
    }
    mock_delete_template.return_value = api_resp

    response = client.delete(
        f"/api/bot/{pytest.bot}/channels/whatsapp/templates/360dialog/test_id",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] == api_resp


@patch(
    "kairon.shared.channels.whatsapp.bsp.dialog360.BSP360Dialog.list_templates",
    autospec=True,
)
def test_list_templates(mock_list_templates):
    api_resp = {
        "waba_templates": [
            {
                "category": "MARKETING",
                "components": [
                    {
                        "example": {"body_text": [["Peter"]]},
                        "text": "Hi {{1}},\n\nWe are thrilled to share that *kAIron* has now been integrated with WhatsApp through the *WhatsApp Business Solution Provide*r (BSP). \n\nThis integration will expand kAIron's ability to engage with a larger audience, increase sales acceleration, and provide better customer support.\n\nWith this integration, sending customized templates and broadcasting general, sales, or marketing information over WhatsApp will be much quicker and more efficient. \n\nStay tuned for more exciting updates from Team kAIron! ",
                        "type": "BODY",
                    }
                ],
                "id": "GVsEkeI2PIiARwVXQEDVWT",
                "language": "en",
                "modified_at": "2023-03-02T13:39:27Z",
                "modified_by": {"user_id": "system", "user_name": "system"},
                "name": "kairon_new_features",
                "namespace": "092819ec_f801_461b_b975_3a2d464f50a8",
                "partner_id": "9Mg0AiPA",
                "waba_account_id": "Cyih7GWA",
            }
        ]
    }
    mock_list_templates.return_value = api_resp["waba_templates"]

    response = client.get(
        f"/api/bot/{pytest.bot}/channels/whatsapp/templates/360dialog/list",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["templates"] == api_resp["waba_templates"]


def test_get_channel_endpoint(monkeypatch):
    monkeypatch.setitem(
        Utility.environment["model"]["agent"], "url", "http://localhost:5056"
    )
    response = client.get(
        f"/api/bot/{pytest.bot}/channels/slack/endpoint",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"].startswith(
        f"http://localhost:5056/api/bot/slack/{pytest.bot}/e"
    )


def test_get_channels_config():
    response = client.get(
        f"/api/bot/{pytest.bot}/channels/list",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] is None
    assert len(actual["data"]) == 2
    pytest.slack_channel_id = actual["data"][0]["_id"]
    actual["data"][0].pop("_id")
    actual["data"][1].pop("_id")
    assert actual["data"] == [
        {
            "bot": pytest.bot,
            "connector_type": "slack",
            "config": {
                "bot_user_oAuth_token": "xoxb-801939352912-801478018484-v3zq6MYNu62oSs8vamm*****",
                "slack_signing_secret": "79f036b9894eef17c064213b90d*****",
                "client_id": "3396830255712.33968616548768*****",
                "client_secret": "cf92180a7634d90bf42a2174083*****",
                "is_primary": True,
                "team": {"id": "T03BNQE7HLX", "name": "helicopter"},
            },
            "meta_config": {},
        },
        {
            "bot": pytest.bot,
            "connector_type": "whatsapp",
            "config": {
                "client_name": "k*****",
                "client_id": "sdfgh5678",
                "channel_id": "sdfghjk678",
                "partner_id": "f167CmPA",
                "waba_account_id": "dfghj5678",
                "api_key": "dfghjk5678",
                "bsp_type": "360dialog",
            },
            "meta_config": {},
        },
    ]


@patch("kairon.shared.utils.Utility.request_event_server", autospec=True)
def test_add_scheduled_broadcast(mock_event_server):
    config = {
        "name": "first_scheduler",
        "broadcast_type": "static",
        "connector_type": "whatsapp",
        "scheduler_config": {
            "expression_type": "cron",
            "schedule": "57 22 * * *",
            "timezone": "UTC",
        },
        "recipients_config": {"recipients": "918958030541, "},
        "template_config": [
            {
                "template_id": "brochure_pdf",
            }
        ],
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/channels/broadcast/message",
        json=config,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Broadcast added!"
    pytest.first_scheduler_id = actual["data"]["msg_broadcast_id"]
    assert pytest.first_scheduler_id


@patch("kairon.shared.utils.Utility.request_event_server", autospec=True)
def test_add_one_time_broadcast(mock_event_server):
    config = {
        "name": "one_time_schedule",
        "broadcast_type": "static",
        "connector_type": "whatsapp",
        "recipients_config": {"recipients": "918958030541,"},
        "template_config": [
            {
                "template_id": "brochure_pdf",
            }
        ],
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/channels/broadcast/message",
        json=config,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Broadcast added!"
    pytest.one_time_schedule_id = actual["data"]["msg_broadcast_id"]
    assert pytest.one_time_schedule_id


def test_broadcast_config_error():
    config = {
        "name": "one_time_schedule",
        "broadcast_type": "static",
        "connector_type": "whatsapp",
        "scheduler_config": {
            "expression_type": "cron",
            "schedule": "* * * * *",
            "timezone": "UTC",
        },
        "recipients_config": {"recipients": "918958030541,"},
        "template_config": [
            {
                "template_id": "brochure_pdf",
            }
        ],
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/channels/broadcast/message",
        json=config,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "scheduler_config", "__root__"],
            "msg": "recurrence interval must be at least 86340 seconds!",
            "type": "value_error",
        }
    ]

    config["scheduler_config"] = {
        "expression_type": "cron",
        "schedule": "57 22 * * *",
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/channels/broadcast/message",
        json=config,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "scheduler_config", "__root__"],
            "msg": "timezone is required for cron expressions!",
            "type": "value_error",
        }
    ]

    config["scheduler_config"]["schedule"] = ""
    config["scheduler_config"]["timezone"] = "UTC"
    response = client.post(
        f"/api/bot/{pytest.bot}/channels/broadcast/message",
        json=config,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "scheduler_config", "__root__"],
            "msg": f"Invalid cron expression: ''",
            "type": "value_error",
        }
    ]

    config["scheduler_config"] = {
        "expression_type": "cron",
        "schedule": "30 5 * * *",
        "timezone": "UTC",
    }
    config["broadcast_type"] = "dynamic"
    response = client.post(
        f"/api/bot/{pytest.bot}/channels/broadcast/message",
        json=config,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "__root__"],
            "msg": "pyscript is required for dynamic broadcasts!",
            "type": "value_error",
        },
    ]

    config["broadcast_type"] = "static"
    config.pop("template_config")
    response = client.post(
        f"/api/bot/{pytest.bot}/channels/broadcast/message",
        json=config,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "__root__"],
            "msg": "recipients_config and template_config is required for static broadcasts!",
            "type": "value_error",
        }
    ]


@patch("kairon.shared.utils.Utility.request_event_server", autospec=True)
def test_update_broadcast(mock_event_server):
    config = {
        "name": "first_scheduler_dynamic",
        "broadcast_type": "dynamic",
        "connector_type": "whatsapp",
        "scheduler_config": {
            "expression_type": "cron",
            "schedule": "21 11 * * *",
            "timezone": "Asia/Kolkata",
        },
        "pyscript": "send_msg('template_name', '9876543210')",
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/channels/broadcast/message/{pytest.first_scheduler_id}",
        json=config,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Broadcast updated!"


def test_update_one_time_broadcast():
    config = {
        "name": "one_time_schedule",
        "broadcast_type": "static",
        "connector_type": "whatsapp",
        "recipients_config": {"recipients": "918958030541,"},
        "template_config": [
            {
                "template_id": "brochure_pdf",
            }
        ],
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/channels/broadcast/message/{pytest.one_time_schedule_id}",
        json=config,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "scheduler_config is required!"


def test_list_broadcast_config():
    response = client.get(
        f"/api/bot/{pytest.bot}/channels/broadcast/message/list",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    actual["data"]["schedules"][0].pop("_id")
    actual["data"]["schedules"][0].pop("timestamp")
    actual["data"]["schedules"][0].pop("bot")
    actual["data"]["schedules"][0].pop("user")
    actual["data"]["schedules"][1].pop("_id")
    actual["data"]["schedules"][1].pop("timestamp")
    actual["data"]["schedules"][1].pop("bot")
    actual["data"]["schedules"][1].pop("user")
    assert actual["data"] == {
        "schedules": [
            {
                "name": "first_scheduler_dynamic",
                "connector_type": "whatsapp",
                "broadcast_type": "dynamic",
                "scheduler_config": {
                    "expression_type": "cron",
                    "schedule": "21 11 * * *",
                    "timezone": "Asia/Kolkata",
                },
                "pyscript": "send_msg('template_name', '9876543210')",
                "status": True,
                "template_config": [],
            },
            {
                "name": "one_time_schedule",
                "connector_type": "whatsapp",
                "broadcast_type": "static",
                "recipients_config": {"recipients": "918958030541,"},
                "template_config": [{"template_id": "brochure_pdf", "language": "en"}],
                "status": True,
            },
        ]
    }


@patch("kairon.shared.utils.Utility.delete_scheduled_event", autospec=True)
def test_delete_broadcast(mock_event_server):
    response = client.delete(
        f"/api/bot/{pytest.bot}/channels/broadcast/message/{pytest.first_scheduler_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Broadcast removed!"


def test_delete_broadcast_not_exists():
    response = client.delete(
        f"/api/bot/{pytest.bot}/channels/broadcast/message/{pytest.first_scheduler_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Notification settings not found!"


def test_list_broadcast_():
    response = client.get(
        f"/api/bot/{pytest.bot}/channels/broadcast/message/list",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    actual["data"]["schedules"][0].pop("timestamp")
    actual["data"]["schedules"][0].pop("user")
    assert actual["data"] == {
        "schedules": [
            {
                "_id": pytest.one_time_schedule_id,
                "name": "one_time_schedule",
                "connector_type": "whatsapp",

                "broadcast_type": "static",
                "recipients_config": {"recipients": "918958030541,"},
                "template_config": [{"template_id": "brochure_pdf", "language": "en"}],
                "bot": pytest.bot,
                "status": True,
            }
        ]
    }


def test_list_broadcast_logs():
    from kairon.shared.chat.broadcast.data_objects import MessageBroadcastLogs

    ref_id = ObjectId().__str__()
    timestamp = datetime.utcnow()
    MessageBroadcastLogs(
        **{
            "reference_id": ref_id,
            "log_type": "common",
            "bot": pytest.bot,
            "status": "Completed",
            "user": "test_user",
            "broadcast_id": pytest.first_scheduler_id,
            "recipients": ["918958030541", ""],
            "timestamp": timestamp,
        }
    ).save()
    timestamp = timestamp + timedelta(minutes=2)
    MessageBroadcastLogs(
        **{
            "reference_id": ref_id,
            "log_type": "send",
            "bot": pytest.bot,
            "status": "Success",
            "api_response": {
                "contacts": [
                    {"input": "+55123456789", "status": "valid", "wa_id": "55123456789"}
                ]
            },
            "recipient": "9876543210",
            "template_params": [
                {
                    "type": "header",
                    "parameters": [
                        {
                            "type": "document",
                            "document": {
                                "link": "https://drive.google.com/uc?export=download&id=1GXQ43jilSDelRvy1kr3PNNpl1e21dRXm",
                                "filename": "Brochure.pdf",
                            },
                        }
                    ],
                }
            ],
            "timestamp": timestamp,
        }
    ).save()
    response = client.get(
        f"/api/bot/{pytest.bot}/channels/broadcast/message/logs?log_type=common",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    actual["data"]["logs"][0].pop("timestamp")
    assert actual["data"]["logs"] == [
        {
            "reference_id": ref_id,
            "log_type": "common",
            "bot": pytest.bot,
            "status": "Completed",
            "user": "test_user",
            "broadcast_id": pytest.first_scheduler_id,
            "recipients": ["918958030541", ""],
        }
    ]
    assert actual["data"]["total_count"] == 1

    response = client.get(
        f"/api/bot/{pytest.bot}/channels/broadcast/message/logs?reference_id={ref_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    actual["data"]["logs"][0].pop("timestamp")
    actual["data"]["logs"][1].pop("timestamp")
    assert actual["data"] == {
        "logs": [
            {
                "reference_id": ref_id,
                "log_type": "send",
                "bot": pytest.bot,
                "status": "Success",
                "api_response": {
                    "contacts": [
                        {
                            "input": "+55123456789",
                            "status": "valid",
                            "wa_id": "55123456789",
                        }
                    ]
                },
                "recipient": "9876543210",
                "template_params": [
                    {
                        "type": "header",
                        "parameters": [
                            {
                                "type": "document",
                                "document": {
                                    "link": "https://drive.google.com/uc?export=download&id=1GXQ43jilSDelRvy1kr3PNNpl1e21dRXm",
                                    "filename": "Brochure.pdf",
                                },
                            }
                        ],
                    }
                ],
            },
            {
                "reference_id": ref_id,
                "log_type": "common",
                "bot": pytest.bot,
                "status": "Completed",
                "user": "test_user",
                "broadcast_id": pytest.first_scheduler_id,
                "recipients": ["918958030541", ""],
            },
        ],
        "total_count": 2,
    }


def test_get_bot_settings():
    response = client.get(
        f"/api/bot/{pytest.bot}/settings",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] is None
    actual["data"].pop("bot")
    actual["data"].pop("user")
    actual["data"].pop("timestamp")
    actual["data"].pop("status")
    assert actual['data'] == {'is_billed': False, 'chat_token_expiry': 30,
                              'data_generation_limit_per_day': 3,
                              'data_importer_limit_per_day': 5,
                              'force_import': False,
                              'ignore_utterances': False,
                              'llm_settings': {'enable_faq': False, 'provider': 'openai'},
                              'analytics': {'fallback_intent': 'nlu_fallback'},
                              'multilingual_limit_per_day': 2,
                              'notification_scheduling_limit': 4,
                              'refresh_token_expiry': 60,
                              'rephrase_response': False,
                              'live_agent_enabled': False,
                              'test_limit_per_day': 5,
                              'training_limit_per_day': 5, 'dynamic_broadcast_execution_timeout': 21600,
                              'website_data_generator_depth_search_limit': 2,
                              'whatsapp': 'meta',
                              'cognition_collections_limit': 3,
                              'cognition_columns_per_collection_limit': 5,
                              'integrations_per_user_limit':3 }


def test_update_analytics_settings_with_empty_value():
    bot_settings = {
        "analytics": {'fallback_intent': ''},
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/settings",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=bot_settings
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [{'loc': ['body', 'analytics', 'fallback_intent'],
                                  'msg': 'fallback_intent field cannot be empty', 'type': 'value_error'}]


def test_update_analytics_settings_with_none():
    bot_settings = {
        "analytics": {'fallback_intent': None},
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/settings",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=bot_settings
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [{'loc': ['body', 'analytics', 'fallback_intent'],
                                  'msg': 'none is not an allowed value', 'type': 'type_error.none.not_allowed'}]


def test_update_analytics_settings():
    bot_settings = {
        "analytics": {'fallback_intent': 'utter_please_rephrase'},
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/settings",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=bot_settings
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Bot Settings updated"
    response = client.get(
        f"/api/bot/{pytest.bot}/settings",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] is None
    actual["data"].pop("bot")
    actual["data"].pop("user")
    actual["data"].pop("timestamp")
    actual["data"].pop("status")
    assert actual['data'] == {'is_billed': False, 'chat_token_expiry': 30,
                              'data_generation_limit_per_day': 3,
                              'data_importer_limit_per_day': 5,
                              'force_import': False,
                              'ignore_utterances': False,
                              'llm_settings': {'enable_faq': False, 'provider': 'openai'},
                              'analytics': {'fallback_intent': 'utter_please_rephrase'},
                              'multilingual_limit_per_day': 2,
                              'notification_scheduling_limit': 4,
                              'refresh_token_expiry': 60,
                              'rephrase_response': False,
                              'test_limit_per_day': 5,
                              'training_limit_per_day': 5, 'dynamic_broadcast_execution_timeout': 21600,
                              'website_data_generator_depth_search_limit': 2,
                              'whatsapp': 'meta',
                              'live_agent_enabled': False,
                              'cognition_collections_limit': 3,
                              'cognition_columns_per_collection_limit': 5,
                              'integrations_per_user_limit':3 }


def test_delete_channels_config():
    response = client.delete(
        f"/api/bot/{pytest.bot}/channels/{pytest.slack_channel_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Channel deleted"


def _mock_error(*args, **kwargs):
    raise JIRAError(status_code=404, url="https://test1-digite.atlassian.net")


def test_add_jira_action_invalid_config(monkeypatch):
    url = "https://test_add_jira_action_invalid_config.net"
    action = {
        "name": "jira_action_new",
        "url": url,
        "user_name": "test@digite.com",
        "api_token": {"value": "ASDFGHJKL"},
        "project_key": "HEL",
        "issue_type": "Bug",
        "summary": "new user",
        "response": "We have logged a ticket",
    }
    monkeypatch.setattr(ActionUtility, "get_jira_client", _mock_error)
    response = client.post(
        f"/api/bot/{pytest.bot}/action/jira",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert (
            actual["message"]
            == "JiraError HTTP 404 url: https://test1-digite.atlassian.net\n\t"
    )


def test_list_jira_action_empty():
    response = client.get(
        f"/api/bot/{pytest.bot}/action/jira",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] == []


@responses.activate
def test_add_jira_action():
    url = "https://test-digite.atlassian.net"
    action = {
        "name": "jira_action",
        "url": url,
        "user_name": "test@digite.com",
        "api_token": {"value": "ASDFGHJKL"},
        "project_key": "HEL",
        "issue_type": "Bug",
        "summary": "new user",
        "response": "We have logged a ticket",
    }
    responses.add(
        "GET",
        f"{url}/rest/api/2/serverInfo",
        json={
            "baseUrl": "https://udit-pandey.atlassian.net",
            "version": "1001.0.0-SNAPSHOT",
            "versionNumbers": [1001, 0, 0],
            "deploymentType": "Cloud",
            "buildNumber": 100191,
            "buildDate": "2022-02-11T05:35:40.000+0530",
            "serverTime": "2022-02-15T10:54:09.906+0530",
            "scmInfo": "831671b3b59f40b5108ef3f9491df89a1317ecaa",
            "serverTitle": "Jira",
            "defaultLocale": {"locale": "en_US"},
        },
    )
    responses.add(
        "GET",
        f"{url}/rest/api/2/project/HEL",
        json={
            "expand": "description,lead,issueTypes,url,projectKeys,permissions,insight",
            "self": "https://udit-pandey.atlassian.net/rest/api/2/project/10000",
            "id": "10000",
            "key": "HEL",
            "description": "",
            "lead": {
                "self": "https://udit-pandey.atlassian.net/rest/api/2/user?accountId=6205e1585d18ad00729aa75f",
                "accountId": "6205e1585d18ad00729aa75f",
                "avatarUrls": {
                    "48x48": "https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png",
                    "24x24": "https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png",
                    "16x16": "https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png",
                    "32x32": "https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png",
                },
                "displayName": "Udit Pandey",
                "active": True,
            },
            "components": [],
            "issueTypes": [
                {
                    "self": "https://udit-pandey.atlassian.net/rest/api/2/issuetype/10001",
                    "id": "10001",
                    "description": "A small, distinct piece of work.",
                    "iconUrl": "https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10318?size=medium",
                    "name": "Task",
                    "subtask": False,
                    "avatarId": 10318,
                    "hierarchyLevel": 0,
                },
                {
                    "self": "https://udit-pandey.atlassian.net/rest/api/2/issuetype/10002",
                    "id": "10002",
                    "description": "A collection of related bugs, stories, and tasks.",
                    "iconUrl": "https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10307?size=medium",
                    "name": "Epic",
                    "subtask": False,
                    "avatarId": 10307,
                    "hierarchyLevel": 1,
                },
                {
                    "self": "https://udit-pandey.atlassian.net/rest/api/2/issuetype/10003",
                    "id": "10003",
                    "description": "Subtasks track small pieces of work that are part of a larger task.",
                    "iconUrl": "https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10316?size=medium",
                    "name": "Bug",
                    "subtask": True,
                    "avatarId": 10316,
                    "hierarchyLevel": -1,
                },
            ],
            "assigneeType": "UNASSIGNED",
            "versions": [],
            "name": "helicopter",
            "roles": {
                "atlassian-addons-project-access": "https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10007",
                "Administrator": "https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10004",
                "Viewer": "https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10006",
                "Member": "https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10005",
            },
            "avatarUrls": {
                "48x48": "https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408",
                "24x24": "https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=small",
                "16x16": "https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=xsmall",
                "32x32": "https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=medium",
            },
            "projectTypeKey": "software",
            "simplified": True,
            "style": "next-gen",
            "isPrivate": False,
            "properties": {},
            "entityId": "8a851ebf-72eb-461d-be68-4c2c28805440",
            "uuid": "8a851ebf-72eb-461d-be68-4c2c28805440",
        },
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/action/jira",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action added"


@patch("kairon.shared.actions.utils.ActionUtility.get_jira_client", autospec=True)
@patch("kairon.shared.actions.utils.ActionUtility.validate_jira_action", autospec=True)
def test_add_jira_action_different_parameter_type(mock_jira_client, mock_validate):
    url = "https://test-digite.atlassian.net"
    action = {
        "name": "jira_action_slot",
        "url": url,
        "user_name": "test@digite.com",
        "api_token": {"value": "ASDFGHJKL", "parameter_type": "slot"},
        "project_key": "HEL",
        "issue_type": "Bug",
        "summary": "new user",
        "response": "We have logged a ticket",
    }

    response = client.post(
        f"/api/bot/{pytest.bot}/action/jira",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action added"

    action = {
        "name": "jira_action_key_vault",
        "url": url,
        "user_name": "test@digite.com",
        "api_token": {"value": "AWS_KEY", "parameter_type": "key_vault"},
        "project_key": "HEL",
        "issue_type": "Bug",
        "summary": "new user",
        "response": "We have logged a ticket",
    }

    response = client.post(
        f"/api/bot/{pytest.bot}/action/jira",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action added"


@patch("kairon.shared.actions.data_objects.JiraAction.validate", autospec=True)
def test_add_jira_action_invalid_parameter_type(moack_jira):
    url = "https://test-digite.atlassian.net"
    action = {
        "name": "jira_action_slot",
        "url": url,
        "user_name": "test@digite.com",
        "api_token": {"value": "ASDFGHJKL", "parameter_type": "user_message"},
        "project_key": "HEL",
        "issue_type": "Bug",
        "summary": "new user",
        "response": "We have logged a ticket",
    }

    response = client.post(
        f"/api/bot/{pytest.bot}/action/jira",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_list_jira_action():
    response = client.get(
        f"/api/bot/{pytest.bot}/action/jira",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    [action.pop("_id") for action in actual["data"]]
    assert actual["data"] == [
        {
            "name": "jira_action",
            "url": "https://test-digite.atlassian.net",
            "user_name": "test@digite.com",
            "api_token": {
                "_cls": "CustomActionRequestParameters",
                "key": "api_token",
                "encrypt": False,
                "value": "ASDFGHJKL",
                "parameter_type": "value",
            },
            "project_key": "HEL",
            "issue_type": "Bug",
            "summary": "new user",
            "response": "We have logged a ticket",
        },
        {
            "name": "jira_action_slot",
            "url": "https://test-digite.atlassian.net",
            "user_name": "test@digite.com",
            "api_token": {
                "_cls": "CustomActionRequestParameters",
                "key": "api_token",
                "encrypt": False,
                "value": "ASDFGHJKL",
                "parameter_type": "slot",
            },
            "project_key": "HEL",
            "issue_type": "Bug",
            "summary": "new user",
            "response": "We have logged a ticket",
        },
        {
            "name": "jira_action_key_vault",
            "url": "https://test-digite.atlassian.net",
            "user_name": "test@digite.com",
            "api_token": {
                "_cls": "CustomActionRequestParameters",
                "key": "api_token",
                "encrypt": False,
                "value": "AWS_KEY",
                "parameter_type": "key_vault",
            },
            "project_key": "HEL",
            "issue_type": "Bug",
            "summary": "new user",
            "response": "We have logged a ticket",
        },
    ]


@responses.activate
def test_edit_jira_action():
    url = "https://test-digite.atlassian.net"
    action = {
        "name": "jira_action",
        "url": url,
        "user_name": "test@digite.com",
        "api_token": {"value": "ASDFGHJKL"},
        "project_key": "HEL",
        "issue_type": "Subtask",
        "parent_key": "HEL-4",
        "summary": "new user",
        "response": "We have logged a ticket",
    }
    responses.add(
        "GET",
        f"{url}/rest/api/2/serverInfo",
        json={
            "baseUrl": "https://udit-pandey.atlassian.net",
            "version": "1001.0.0-SNAPSHOT",
            "versionNumbers": [1001, 0, 0],
            "deploymentType": "Cloud",
            "buildNumber": 100191,
            "buildDate": "2022-02-11T05:35:40.000+0530",
            "serverTime": "2022-02-15T10:54:09.906+0530",
            "scmInfo": "831671b3b59f40b5108ef3f9491df89a1317ecaa",
            "serverTitle": "Jira",
            "defaultLocale": {"locale": "en_US"},
        },
    )
    responses.add(
        "GET",
        f"{url}/rest/api/2/project/HEL",
        json={
            "expand": "description,lead,issueTypes,url,projectKeys,permissions,insight",
            "self": "https://udit-pandey.atlassian.net/rest/api/2/project/10000",
            "id": "10000",
            "key": "HEL",
            "description": "",
            "lead": {
                "self": "https://udit-pandey.atlassian.net/rest/api/2/user?accountId=6205e1585d18ad00729aa75f",
                "accountId": "6205e1585d18ad00729aa75f",
                "avatarUrls": {
                    "48x48": "https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png",
                    "24x24": "https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png",
                    "16x16": "https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png",
                    "32x32": "https://secure.gravatar.com/avatar/6864b14113f03cbe6d55af5006b12efe?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FUP-0.png",
                },
                "displayName": "Udit Pandey",
                "active": True,
            },
            "components": [],
            "issueTypes": [
                {
                    "self": "https://udit-pandey.atlassian.net/rest/api/2/issuetype/10001",
                    "id": "10001",
                    "description": "A small, distinct piece of work.",
                    "iconUrl": "https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10318?size=medium",
                    "name": "Task",
                    "subtask": False,
                    "avatarId": 10318,
                    "hierarchyLevel": 0,
                },
                {
                    "self": "https://udit-pandey.atlassian.net/rest/api/2/issuetype/10002",
                    "id": "10002",
                    "description": "A collection of related bugs, stories, and tasks.",
                    "iconUrl": "https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10307?size=medium",
                    "name": "Epic",
                    "subtask": False,
                    "avatarId": 10307,
                    "hierarchyLevel": 1,
                },
                {
                    "self": "https://udit-pandey.atlassian.net/rest/api/2/issuetype/10003",
                    "id": "10003",
                    "description": "Subtasks track small pieces of work that are part of a larger task.",
                    "iconUrl": "https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/issuetype/avatar/10316?size=medium",
                    "name": "Subtask",
                    "subtask": True,
                    "avatarId": 10316,
                    "hierarchyLevel": -1,
                },
            ],
            "assigneeType": "UNASSIGNED",
            "versions": [],
            "name": "helicopter",
            "roles": {
                "atlassian-addons-project-access": "https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10007",
                "Administrator": "https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10004",
                "Viewer": "https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10006",
                "Member": "https://udit-pandey.atlassian.net/rest/api/2/project/10000/role/10005",
            },
            "avatarUrls": {
                "48x48": "https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408",
                "24x24": "https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=small",
                "16x16": "https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=xsmall",
                "32x32": "https://udit-pandey.atlassian.net/rest/api/2/universal_avatar/view/type/project/avatar/10408?size=medium",
            },
            "projectTypeKey": "software",
            "simplified": True,
            "style": "next-gen",
            "isPrivate": False,
            "properties": {},
            "entityId": "8a851ebf-72eb-461d-be68-4c2c28805440",
            "uuid": "8a851ebf-72eb-461d-be68-4c2c28805440",
        },
    )
    response = client.put(
        f"/api/bot/{pytest.bot}/action/jira",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action updated"


@patch("kairon.shared.actions.utils.ActionUtility.get_jira_client", autospec=True)
@patch("kairon.shared.actions.utils.ActionUtility.validate_jira_action", autospec=True)
def test_edit_jira_action_different_parameter_type(mock_jira_client, mock_validate):
    url = "https://test-digite.atlassian.net"
    action = {
        "name": "jira_action_slot",
        "url": url,
        "user_name": "test@digite.com",
        "api_token": {"value": "AWS_KEY", "parameter_type": "key_vault"},
        "project_key": "HEL",
        "issue_type": "Bug",
        "summary": "new user",
        "response": "We have logged a ticket",
    }

    response = client.put(
        f"/api/bot/{pytest.bot}/action/jira",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action updated"

    action = {
        "name": "jira_action_key_vault",
        "url": url,
        "user_name": "test@digite.com",
        "api_token": {"value": "ASDFGHJKL", "parameter_type": "slot"},
        "project_key": "HEL",
        "issue_type": "Bug",
        "summary": "new user",
        "response": "We have logged a ticket",
    }

    response = client.put(
        f"/api/bot/{pytest.bot}/action/jira",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action updated"


@patch("kairon.shared.actions.utils.ActionUtility", autospec=True)
def test_edit_jira_action_invalid_parameter_type(mock_jira):
    url = "https://test-digite.atlassian.net"
    action = {
        "name": "jira_action_slot",
        "url": url,
        "user_name": "test@digite.com",
        "api_token": {"value": "ASDFGHJKL", "parameter_type": "chat_log"},
        "project_key": "HEL",
        "issue_type": "Bug",
        "summary": "new user",
        "response": "We have logged a ticket",
    }

    response = client.put(
        f"/api/bot/{pytest.bot}/action/jira",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_edit_jira_action_invalid_config(monkeypatch):
    url = "https://test_edit_jira_action_invalid_config.net"
    action = {
        "name": "jira_action",
        "url": url,
        "user_name": "test@digite.com",
        "api_token": {"value": "ASDFGHJKL"},
        "project_key": "HEL",
        "issue_type": "Bug",
        "summary": "new user",
        "response": "We have logged a ticket",
    }

    monkeypatch.setattr(ActionUtility, "get_jira_client", _mock_error)
    response = client.put(
        f"/api/bot/{pytest.bot}/action/jira",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert (
            actual["message"]
            == "JiraError HTTP 404 url: https://test1-digite.atlassian.net\n\t"
    )


def test_edit_jira_action_not_found():
    url = "https://test-digite.atlassian.net"
    action = {
        "name": "jira_action_new",
        "url": url,
        "user_name": "test@digite.com",
        "api_token": {"value": "ASDFGHJKL"},
        "project_key": "HEL",
        "issue_type": "Bug",
        "summary": "new user",
        "response": "We have logged a ticket",
    }

    response = client.put(
        f"/api/bot/{pytest.bot}/action/jira",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == 'Action with name "jira_action_new" not found'


def test_add_zendesk_action_invalid_config(monkeypatch):
    def __mock_zendesk_error(*args, **kwargs):
        from zenpy.lib.exception import APIException

        raise APIException(
            {"error": {"title": "No help desk at digite751.zendesk.com"}}
        )

    action = {
        "name": "zendesk_action_1",
        "subdomain": "digite751",
        "api_token": {"value": "AWS_KEY", "parameter_type": "key_vault"},
        "subject": "new ticket",
        "user_name": "udit.pandey@digite.com",
        "response": "ticket filed",
    }
    with patch("zenpy.Zenpy") as mock:
        mock.side_effect = __mock_zendesk_error
        response = client.post(
            f"/api/bot/{pytest.bot}/action/zendesk",
            json=action,
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        )
        actual = response.json()
        assert not actual["success"]
        assert actual["error_code"] == 422
        assert (
                actual["message"]
                == "{'error': {'title': 'No help desk at digite751.zendesk.com'}}"
        )


def test_list_zendesk_action_empty():
    response = client.get(
        f"/api/bot/{pytest.bot}/action/zendesk",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] == []


def test_add_zendesk_action():
    action = {
        "name": "zendesk_action",
        "subdomain": "digite751",
        "api_token": {"value": "123456789"},
        "subject": "new ticket",
        "user_name": "udit.pandey@digite.com",
        "response": "ticket filed",
    }
    with patch("zenpy.Zenpy"):
        response = client.post(
            f"/api/bot/{pytest.bot}/action/zendesk",
            json=action,
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        )
        actual = response.json()
        assert actual["success"]
        assert actual["error_code"] == 0
        assert actual["message"] == "Action added"


@patch("kairon.shared.actions.data_objects.ZendeskAction.validate", autospec=True)
def test_add_zendesk_action_different_parameter_type(mock_zedesk):
    action = {
        "name": "zendesk_action_slot",
        "subdomain": "digite751",
        "api_token": {"value": "123456789", "parameter_type": "slot"},
        "subject": "new ticket",
        "user_name": "udit.pandey@digite.com",
        "response": "ticket filed",
    }
    with patch("zenpy.Zenpy"):
        response = client.post(
            f"/api/bot/{pytest.bot}/action/zendesk",
            json=action,
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        )
        actual = response.json()
        assert actual["success"]
        assert actual["error_code"] == 0
        assert actual["message"] == "Action added"

    action = {
        "name": "zendesk_action_key_vault",
        "subdomain": "digite751",
        "api_token": {"value": "AWS_KEY", "parameter_type": "key_vault"},
        "subject": "new ticket",
        "user_name": "udit.pandey@digite.com",
        "response": "ticket filed",
    }
    with patch("zenpy.Zenpy"):
        response = client.post(
            f"/api/bot/{pytest.bot}/action/zendesk",
            json=action,
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        )
        actual = response.json()
        assert actual["success"]
        assert actual["error_code"] == 0
        assert actual["message"] == "Action added"


def test_add_zendesk_action_invalid_parameter_type():
    action = {
        "name": "zendesk_action_intent",
        "subdomain": "digite751",
        "api_token": {"value": "123456789", "parameter_type": "intent"},
        "subject": "new ticket",
        "user_name": "udit.pandey@digite.com",
        "response": "ticket filed",
    }
    with patch("zenpy.Zenpy"):
        response = client.post(
            f"/api/bot/{pytest.bot}/action/zendesk",
            json=action,
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        )
        actual = response.json()
        assert not actual["success"]
        assert actual["error_code"] == 422


def test_list_zendesk_action():
    response = client.get(
        f"/api/bot/{pytest.bot}/action/zendesk",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    [action.pop("_id") for action in actual["data"]]
    assert actual["data"] == [
        {
            "name": "zendesk_action",
            "subdomain": "digite751",
            "user_name": "udit.pandey@digite.com",
            "api_token": {
                "_cls": "CustomActionRequestParameters",
                "key": "api_token",
                "encrypt": False,
                "value": "123456789",
                "parameter_type": "value",
            },
            "subject": "new ticket",
            "response": "ticket filed",
        },
        {
            "name": "zendesk_action_slot",
            "subdomain": "digite751",
            "user_name": "udit.pandey@digite.com",
            "api_token": {
                "_cls": "CustomActionRequestParameters",
                "encrypt": False,
                "value": "123456789",
                "parameter_type": "slot",
            },
            "subject": "new ticket",
            "response": "ticket filed",
        },
        {
            "name": "zendesk_action_key_vault",
            "subdomain": "digite751",
            "user_name": "udit.pandey@digite.com",
            "api_token": {
                "_cls": "CustomActionRequestParameters",
                "encrypt": False,
                "value": "AWS_KEY",
                "parameter_type": "key_vault",
            },
            "subject": "new ticket",
            "response": "ticket filed",
        },
    ]


def test_edit_zendesk_action():
    action = {
        "name": "zendesk_action",
        "subdomain": "digite756",
        "api_token": {"value": "123456789999"},
        "subject": "new ticket",
        "user_name": "udit.pandey@digite.com",
        "response": "ticket filed here",
    }
    with patch("zenpy.Zenpy"):
        response = client.put(
            f"/api/bot/{pytest.bot}/action/zendesk",
            json=action,
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        )
        actual = response.json()
        assert actual["success"]
        assert actual["error_code"] == 0
        assert actual["message"] == "Action updated"


@patch("kairon.shared.actions.data_objects.ZendeskAction.validate", autospec=True)
def test_edit_zendesk_action_different_parameter_type(mock_zendesk):
    action = {
        "name": "zendesk_action_slot",
        "subdomain": "digite751",
        "api_token": {"value": "AWS_KEY", "parameter_type": "key_vault"},
        "subject": "new ticket",
        "user_name": "udit.pandey@digite.com",
        "response": "ticket filed",
    }
    with patch("zenpy.Zenpy"):
        response = client.put(
            f"/api/bot/{pytest.bot}/action/zendesk",
            json=action,
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        )
        actual = response.json()
        assert actual["success"]
        assert actual["error_code"] == 0
        assert actual["message"] == "Action updated"

    action = {
        "name": "zendesk_action_key_vault",
        "subdomain": "digite751",
        "api_token": {"value": "123456789", "parameter_type": "slot"},
        "subject": "new ticket",
        "user_name": "udit.pandey@digite.com",
        "response": "ticket filed",
    }
    with patch("zenpy.Zenpy"):
        response = client.put(
            f"/api/bot/{pytest.bot}/action/zendesk",
            json=action,
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        )
        actual = response.json()
        assert actual["success"]
        assert actual["error_code"] == 0
        assert actual["message"] == "Action updated"


def test_edit_zendesk_action_invalid_parameter_type():
    action = {
        "name": "zendesk_action_intent",
        "subdomain": "digite751",
        "api_token": {"value": "123456789", "parameter_type": "intent"},
        "subject": "new ticket",
        "user_name": "udit.pandey@digite.com",
        "response": "ticket filed",
    }
    with patch("zenpy.Zenpy"):
        response = client.put(
            f"/api/bot/{pytest.bot}/action/zendesk",
            json=action,
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        )
        actual = response.json()
        assert not actual["success"]
        assert actual["error_code"] == 422


def test_edit_zendesk_action_invalid_config(monkeypatch):
    action = {
        "name": "zendesk_action",
        "subdomain": "digite751",
        "api_token": {"value": "AWS_KEY", "parameter_type": "key_vault"},
        "subject": "new ticket",
        "user_name": "udit.pandey@digite.com",
        "response": "ticket filed",
    }

    def __mock_zendesk_error(*args, **kwargs):
        from zenpy.lib.exception import APIException

        raise APIException(
            {"error": {"title": "No help desk at digite751.zendesk.com"}}
        )

    with patch("zenpy.Zenpy") as mock:
        mock.side_effect = __mock_zendesk_error
        response = client.put(
            f"/api/bot/{pytest.bot}/action/zendesk",
            json=action,
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        )
        actual = response.json()
        assert not actual["success"]
        assert actual["error_code"] == 422
        assert (
                actual["message"]
                == "{'error': {'title': 'No help desk at digite751.zendesk.com'}}"
        )


def test_edit_zendesk_action_not_found():
    action = {
        "name": "zendesk_action_1",
        "subdomain": "digite751",
        "api_token": {"value": "123456789"},
        "subject": "new ticket",
        "user_name": "udit.pandey@digite.com",
        "response": "ticket filed",
    }

    response = client.put(
        f"/api/bot/{pytest.bot}/action/zendesk",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == 'Action with name "zendesk_action_1" not found'


def test_add_pipedrive_leads_action_invalid_config(monkeypatch):
    def __mock_exception(*args, **kwargs):
        raise UnauthorizedError("Invalid authentication", {"error_code": 401})

    action = {
        "name": "pipedrive_leads",
        "domain": "https://digite751.pipedrive.com/",
        "api_token": {"value": "12345678"},
        "title": "new lead",
        "response": "I have failed to create lead for you",
        "metadata": {
            "name": "name",
            "org_name": "organization",
            "email": "email",
            "phone": "phone",
        },
    }
    with patch("pipedrive.client.Client._request", __mock_exception) as mock:
        response = client.post(
            f"/api/bot/{pytest.bot}/action/pipedrive",
            json=action,
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        )
        actual = response.json()
        assert not actual["success"]
        assert actual["error_code"] == 422
        assert actual["message"] == "Invalid authentication"


def test_add_pipedrive_leads_name_not_filled(monkeypatch):
    action = {
        "name": "pipedrive_leads",
        "domain": "https://digite751.pipedrive.com/",
        "api_token": {"value": "12345678"},
        "title": "new lead",
        "response": "I have failed to create lead for you",
        "metadata": {"org_name": "organization", "email": "email", "phone": "phone"},
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/pipedrive",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {"loc": ["body", "metadata"], "msg": "name is required", "type": "value_error"}
    ]


def test_list_pipedrive_actions_empty():
    response = client.get(
        f"/api/bot/{pytest.bot}/action/pipedrive",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] == []


def test_add_pipedrive_action():
    action = {
        "name": "pipedrive_leads",
        "domain": "https://digite751.pipedrive.com/",
        "api_token": {"value": "12345678"},
        "title": "new lead",
        "response": "I have failed to create lead for you",
        "metadata": {
            "name": "name",
            "org_name": "organization",
            "email": "email",
            "phone": "phone",
        },
    }
    with patch("pipedrive.client.Client"):
        response = client.post(
            f"/api/bot/{pytest.bot}/action/pipedrive",
            json=action,
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        )
        actual = response.json()
        assert actual["success"]
        assert actual["error_code"] == 0
        assert actual["message"] == "Action added"


def test_add_pipedrive_action_different_parameter_types():
    action = {
        "name": "pipedrive_leads_slot",
        "domain": "https://digite751.pipedrive.com/",
        "api_token": {"value": "12345678", "parameter_type": "slot"},
        "title": "new lead",
        "response": "I have failed to create lead for you",
        "metadata": {
            "name": "name",
            "org_name": "organization",
            "email": "email",
            "phone": "phone",
        },
    }
    with patch("pipedrive.client.Client"):
        response = client.post(
            f"/api/bot/{pytest.bot}/action/pipedrive",
            json=action,
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        )
        actual = response.json()
        assert actual["success"]
        assert actual["error_code"] == 0
        assert actual["message"] == "Action added"

    action = {
        "name": "pipedrive_leads_slot_key_vault",
        "domain": "https://digite751.pipedrive.com/",
        "api_token": {"value": "AWS_KEY", "parameter_type": "key_vault"},
        "title": "new lead",
        "response": "I have failed to create lead for you",
        "metadata": {
            "name": "name",
            "org_name": "organization",
            "email": "email",
            "phone": "phone",
        },
    }
    with patch("pipedrive.client.Client"):
        response = client.post(
            f"/api/bot/{pytest.bot}/action/pipedrive",
            json=action,
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        )
        actual = response.json()
        assert actual["success"]
        assert actual["error_code"] == 0
        assert actual["message"] == "Action added"


def test_add_pipedrive_action_invalid_parameter_types():
    action = {
        "name": "pipedrive_leads_sender_id",
        "domain": "https://digite751.pipedrive.com/",
        "api_token": {"value": "12345678", "parameter_type": "intent"},
        "title": "new lead",
        "response": "I have failed to create lead for you",
        "metadata": {
            "name": "name",
            "org_name": "organization",
            "email": "email",
            "phone": "phone",
        },
    }
    with patch("pipedrive.client.Client"):
        response = client.post(
            f"/api/bot/{pytest.bot}/action/pipedrive",
            json=action,
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        )
        actual = response.json()
        assert not actual["success"]
        assert actual["error_code"] == 422


def test_list_pipedrive_action():
    response = client.get(
        f"/api/bot/{pytest.bot}/action/pipedrive",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    [action.pop("_id") for action in actual["data"]]
    assert actual["data"] == [
        {
            "name": "pipedrive_leads",
            "domain": "https://digite751.pipedrive.com/",
            "api_token": {
                "_cls": "CustomActionRequestParameters",
                "key": "api_token",
                "encrypt": False,
                "value": "12345678",
                "parameter_type": "value",
            },
            "title": "new lead",
            "metadata": {
                "name": "name",
                "org_name": "organization",
                "email": "email",
                "phone": "phone",
            },
            "response": "I have failed to create lead for you",
        },
        {
            "name": "pipedrive_leads_slot",
            "domain": "https://digite751.pipedrive.com/",
            "api_token": {
                "_cls": "CustomActionRequestParameters",
                "key": "api_token",
                "encrypt": False,
                "value": "12345678",
                "parameter_type": "slot",
            },
            "title": "new lead",
            "metadata": {
                "name": "name",
                "org_name": "organization",
                "email": "email",
                "phone": "phone",
            },
            "response": "I have failed to create lead for you",
        },
        {
            "name": "pipedrive_leads_slot_key_vault",
            "domain": "https://digite751.pipedrive.com/",
            "api_token": {
                "_cls": "CustomActionRequestParameters",
                "key": "api_token",
                "encrypt": False,
                "value": "AWS_KEY",
                "parameter_type": "key_vault",
            },
            "title": "new lead",
            "metadata": {
                "name": "name",
                "org_name": "organization",
                "email": "email",
                "phone": "phone",
            },
            "response": "I have failed to create lead for you",
        },
    ]


def test_edit_pipedrive_action():
    action = {
        "name": "pipedrive_leads",
        "domain": "https://digite7.pipedrive.com/",
        "api_token": {"value": "1asdfghjklqwertyuio"},
        "title": "new lead generated",
        "response": "Failed to create lead for you",
        "metadata": {"name": "name"},
    }

    with patch("pipedrive.client.Client"):
        response = client.put(
            f"/api/bot/{pytest.bot}/action/pipedrive",
            json=action,
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        )
        actual = response.json()
        assert actual["success"]
        assert actual["error_code"] == 0
        assert actual["message"] == "Action updated"


@patch(
    "kairon.shared.actions.data_objects.PipedriveLeadsAction.validate", autospec=True
)
def test_edit_pipedrive_action_different_parameter_type(mock_pipedrive):
    action = {
        "name": "pipedrive_leads_slot",
        "domain": "https://digite7.pipedrive.com/",
        "api_token": {"value": "AWS_KEY", "parameter_type": "key_vault"},
        "title": "new lead generated",
        "response": "Failed to create lead for you",
        "metadata": {"name": "name"},
    }

    with patch("pipedrive.client.Client"):
        response = client.put(
            f"/api/bot/{pytest.bot}/action/pipedrive",
            json=action,
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        )
        actual = response.json()
        assert actual["success"]
        assert actual["error_code"] == 0
        assert actual["message"] == "Action updated"

    action = {
        "name": "pipedrive_leads_slot_key_vault",
        "domain": "https://digite7.pipedrive.com/",
        "api_token": {"value": "1asdfghjklqwertyuio", "parameter_type": "slot"},
        "title": "new lead generated",
        "response": "Failed to create lead for you",
        "metadata": {"name": "name"},
    }

    with patch("pipedrive.client.Client"):
        response = client.put(
            f"/api/bot/{pytest.bot}/action/pipedrive",
            json=action,
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        )
        actual = response.json()
        assert actual["success"]
        assert actual["error_code"] == 0
        assert actual["message"] == "Action updated"


def test_edit_pipedrive_action_invalid_parameter_type():
    action = {
        "name": "pipedrive_leads_slot_key_vault",
        "domain": "https://digite751.pipedrive.com/",
        "api_token": {"value": "12345678", "parameter_type": "intent"},
        "title": "new lead",
        "response": "I have failed to create lead for you",
        "metadata": {
            "name": "name",
            "org_name": "organization",
            "email": "email",
            "phone": "phone",
        },
    }

    response = client.put(
        f"/api/bot/{pytest.bot}/action/pipedrive",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_edit_pipedrive_action_invalid_config(monkeypatch):
    action = {
        "name": "pipedrive_leads",
        "domain": "https://digite751.pipedrive.com/",
        "api_token": {"value": "12345678"},
        "title": "new lead",
        "response": "I have failed to create lead for you",
        "metadata": {
            "name": "name",
            "org_name": "organization",
            "email": "email",
            "phone": "phone",
        },
    }

    def __mock_exception(*args, **kwargs):
        raise UnauthorizedError("Invalid authentication", {"error_code": 401})

    with patch("pipedrive.client.Client._request", __mock_exception):
        response = client.put(
            f"/api/bot/{pytest.bot}/action/pipedrive",
            json=action,
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        )
        actual = response.json()
        assert not actual["success"]
        assert actual["error_code"] == 422
        assert actual["message"] == "Invalid authentication"


def test_edit_pipedrive_action_not_found():
    action = {
        "name": "pipedrive_action",
        "domain": "https://digite751.pipedrive.com/",
        "api_token": {"value": "12345678"},
        "title": "new lead",
        "response": "I have failed to create lead for you",
        "metadata": {
            "name": "name",
            "org_name": "organization",
            "email": "email",
            "phone": "phone",
        },
    }

    response = client.put(
        f"/api/bot/{pytest.bot}/action/pipedrive",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == 'Action with name "pipedrive_action" not found'


def test_list_razorpay_actions_empty():
    response = client.get(
        f"/api/bot/{pytest.bot}/action/razorpay",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] == []


def test_add_razorpay_action():
    action_name = "razorpay_action"
    action = {
        "name": action_name,
        "api_key": {"value": "API_KEY", "parameter_type": "key_vault"},
        "api_secret": {"value": "API_SECRET", "parameter_type": "key_vault"},
        "amount": {"value": "amount", "parameter_type": "slot"},
        "currency": {"value": "INR", "parameter_type": "value"},
        "username": {"parameter_type": "sender_id"},
        "email": {"parameter_type": "sender_id"},
        "contact": {"value": "contact", "parameter_type": "slot"},
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/razorpay",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action added!"


def test_add_razorpay_action_with_required_values_only():
    action_name = "razorpay_action_required_values_only"
    action = {
        "name": action_name,
        "api_key": {"value": "API_KEY", "parameter_type": "value"},
        "api_secret": {"value": "API_SECRET", "parameter_type": "value"},
        "amount": {"value": "amount", "parameter_type": "value"},
        "currency": {"value": "INR", "parameter_type": "slot"},
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/razorpay",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action added!"


def test_add_razorpay_action_without_required_values():
    action_name = "razorpay_action_required_values_only"
    action = {
        "name": action_name,
        "amount": {"value": "amount", "parameter_type": "value"},
        "currency": {"value": "INR", "parameter_type": "slot"},
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/razorpay",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == [
        {
            "loc": ["body", "api_key"],
            "msg": "field required",
            "type": "value_error.missing",
        },
        {
            "loc": ["body", "api_secret"],
            "msg": "field required",
            "type": "value_error.missing",
        },
    ]
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_list_razorpay_actions():
    response = client.get(
        f"/api/bot/{pytest.bot}/action/razorpay",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    [v.pop("timestamp") for v in actual["data"]]
    [action.pop("_id") for action in actual["data"]]
    assert actual["data"] == [
        {
            "name": "razorpay_action",
            "api_key": {
                "_cls": "CustomActionRequestParameters",
                "key": "api_key",
                "encrypt": False,
                "value": "API_KEY",
                "parameter_type": "key_vault",
            },
            "api_secret": {
                "_cls": "CustomActionRequestParameters",
                "key": "api_secret",
                "encrypt": False,
                "value": "API_SECRET",
                "parameter_type": "key_vault",
            },
            "amount": {
                "_cls": "CustomActionRequestParameters",
                "key": "amount",
                "encrypt": False,
                "value": "amount",
                "parameter_type": "slot",
            },
            "currency": {
                "_cls": "CustomActionRequestParameters",
                "key": "currency",
                "encrypt": False,
                "value": "INR",
                "parameter_type": "value",
            },
            "username": {
                "_cls": "CustomActionRequestParameters",
                "key": "username",
                "encrypt": False,
                "parameter_type": "sender_id",
            },
            "email": {
                "_cls": "CustomActionRequestParameters",
                "key": "email",
                "encrypt": False,
                "parameter_type": "sender_id",
            },
            "contact": {
                "_cls": "CustomActionRequestParameters",
                "key": "contact",
                "encrypt": False,
                "value": "contact",
                "parameter_type": "slot",
            },
        },
        {
            "name": "razorpay_action_required_values_only",
            "api_key": {
                "_cls": "CustomActionRequestParameters",
                "key": "api_key",
                "encrypt": False,
                "value": "API_KEY",
                "parameter_type": "value",
            },
            "api_secret": {
                "_cls": "CustomActionRequestParameters",
                "key": "api_secret",
                "encrypt": False,
                "value": "API_SECRET",
                "parameter_type": "value",
            },
            "amount": {
                "_cls": "CustomActionRequestParameters",
                "key": "amount",
                "encrypt": False,
                "value": "amount",
                "parameter_type": "value",
            },
            "currency": {
                "_cls": "CustomActionRequestParameters",
                "key": "currency",
                "encrypt": False,
                "value": "INR",
                "parameter_type": "slot",
            },
        },
    ]
    assert actual["success"]
    assert actual["error_code"] == 0


def test_edit_razorpay_action():
    action_name = "razorpay_action"
    action = {
        "name": action_name,
        "api_key": {"value": "API_KEY", "parameter_type": "key_vault"},
        "api_secret": {"value": "API_SECRET", "parameter_type": "key_vault"},
        "amount": {"value": "amount", "parameter_type": "value"},
        "currency": {"value": "INR", "parameter_type": "slot"},
        "email": {"parameter_type": "sender_id"},
        "contact": {"value": "contact", "parameter_type": "value"},
    }

    response = client.put(
        f"/api/bot/{pytest.bot}/action/razorpay",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action updated!"


def test_edit_razorpay_action_required_config_missing():
    action_name = "razorpay_action"
    action = {
        "name": action_name,
        "email": {"parameter_type": "sender_id"},
        "contact": {"value": "contact", "parameter_type": "value"},
    }

    response = client.put(
        f"/api/bot/{pytest.bot}/action/razorpay",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == [
        {
            "loc": ["body", "api_key"],
            "msg": "field required",
            "type": "value_error.missing",
        },
        {
            "loc": ["body", "api_secret"],
            "msg": "field required",
            "type": "value_error.missing",
        },
        {
            "loc": ["body", "amount"],
            "msg": "field required",
            "type": "value_error.missing",
        },
        {
            "loc": ["body", "currency"],
            "msg": "field required",
            "type": "value_error.missing",
        },
    ]
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_edit_razorpay_action_not_found():
    action_name = "new_razorpay_action"
    action = {
        "name": action_name,
        "api_key": {"value": "API_KEY", "parameter_type": "key_vault"},
        "api_secret": {"value": "API_SECRET", "parameter_type": "key_vault"},
        "amount": {"value": "amount", "parameter_type": "value"},
        "currency": {"value": "INR", "parameter_type": "slot"},
        "email": {"parameter_type": "sender_id"},
        "contact": {"value": "contact", "parameter_type": "value"},
    }

    response = client.put(
        f"/api/bot/{pytest.bot}/action/razorpay",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == 'Action with name "new_razorpay_action" not found'


def test_delete_razorpay_action():
    response = client.delete(
        url=f"/api/bot/{pytest.bot}/action/razorpay_action",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"]
    assert actual["success"]


def test_get_fields_for_integrated_actions():
    response = client.get(
        f"/api/bot/{pytest.bot}/action/fields/list",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["pipedrive"] == {
        "required_fields": ["name"],
        "optional_fields": ["org_name", "email", "phone"],
    }


def test_channels_params():
    response = client.get(
        f"/api/bot/{pytest.bot}/channels/params",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert "slack" in list(actual["data"].keys())
    assert [
               "bot_user_oAuth_token",
               "slack_signing_secret",
               "client_id",
               "client_secret",
           ] == actual["data"]["slack"]["required_fields"]
    assert ["slack_channel", "team", "is_primary"] == actual["data"]["slack"][
        "optional_fields"
    ]
    assert ["team", "is_primary"] == actual["data"]["slack"]["disabled_fields"]


def test_get_channel_endpoint_not_configured():
    response = client.get(
        f"/api/bot/{pytest.bot}/channels/slack/endpoint",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert not actual["data"]
    assert actual["message"] == "Channel not configured"


def test_add_asset(monkeypatch):
    def __mock_file_upload(*args, **kwargs):
        return "https://kairon.s3.amazonaws.com/application/626a380d3060cf93782b52c3/actions_yml.yml"

    monkeypatch.setattr(CloudUtility, "upload_file", __mock_file_upload)
    monkeypatch.setitem(
        Utility.environment["storage"]["assets"], "allowed_extensions", [".yml"]
    )

    file = {"asset": open("tests/testing_data/valid_yml/actions.yml", "rb")}
    response = client.put(
        f"/api/bot/{pytest.bot}/assets/actions_yml",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=file,
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert (
            actual["data"]["url"]
            == "https://kairon.s3.amazonaws.com/application/626a380d3060cf93782b52c3/actions_yml.yml"
    )
    assert actual["message"] == "Asset added"


def test_add_asset_failure(monkeypatch):
    def __mock_file_upload(*args, **kwargs):
        api_resp = {
            "Error": {"Code": "400", "Message": "Bad Request"},
            "ResponseMetadata": {
                "RequestId": "BQFVQHD1KSD5V6RZ",
                "HostId": "t2uudD7x2V+rRHO4dp2XBqdmAOaWwlnsII7gs1JbYcrntVKRaZSpHxNPJEww+s5dCzCQOg2uero=",
                "HTTPStatusCode": 400,
                "HTTPHeaders": {
                    "x-amz-bucket-region": "us-east-1",
                    "x-amz-request-id": "BQFVQHD1KSD5V6RZ",
                    "x-amz-id-2": "t2uudD7x2V+rRHO4dp2XBqdmAOaWwlnsII7gs1JbYcrntVKRaZSpHxNPJEww+s5dCzCQOg2uero=",
                    "content-type": "application/xml",
                    "date": "Wed, 27 Apr 2022 08:53:05 GMT",
                    "server": "AmazonS3",
                    "connection": "close",
                },
                "RetryAttempts": 3,
            },
        }
        raise ClientError(api_resp, "PutObject")

    monkeypatch.setattr(CloudUtility, "upload_file", __mock_file_upload)
    monkeypatch.setitem(
        Utility.environment["storage"]["assets"], "allowed_extensions", [".yml"]
    )

    file = {"asset": open("tests/testing_data/valid_yml/actions.yml", "rb")}
    response = client.put(
        f"/api/bot/{pytest.bot}/assets/actions_yml",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=file,
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert not actual["data"]
    assert actual["message"] == "File upload failed"


def test_list_assets():
    response = client.get(
        f"/api/bot/{pytest.bot}/assets",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["assets"] == [
        {
            "asset_type": "actions_yml",
            "url": "https://kairon.s3.amazonaws.com/application/626a380d3060cf93782b52c3/actions_yml.yml",
        }
    ]


def test_delete_asset(monkeypatch):
    def __mock_delete_file(*args, **kwargs):
        return None

    monkeypatch.setattr(CloudUtility, "delete_file", __mock_delete_file)

    response = client.delete(
        f"/api/bot/{pytest.bot}/assets/actions_yml",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert not actual["data"]
    assert actual["message"] == "Asset deleted"


def test_delete_asset_not_exists():
    response = client.delete(
        f"/api/bot/{pytest.bot}/assets/actions_yml",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert not actual["data"]
    assert actual["message"] == "Asset does not exists"


def test_list_assets_not_exists():
    response = client.get(
        f"/api/bot/{pytest.bot}/assets",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["assets"] == []


def test_get_live_agent_config_params():
    response = client.get(
        f"/api/bot/{pytest.bot}/agents/live/params",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] == Utility.system_metadata["live_agents"]


def test_get_live_agent_config_none():
    response = client.get(
        f"/api/bot/{pytest.bot}/agents/live",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["agent"] is None


@responses.activate
def test_add_live_agent_config_agent_not_supported():
    config = {
        "agent_type": "livechat",
        "config": {"account_id": "12", "api_access_token": "asdfghjklty67"},
        "override_bot": False,
        "trigger_on_intents": ["greet", "enquiry"],
        "trigger_on_actions": ["action_default_fallback", "action_enquiry"],
    }

    response = client.put(
        f"/api/bot/{pytest.bot}/agents/live",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=config,
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert not actual["data"]
    assert actual["message"] == [
        {
            "loc": ["body", "agent_type"],
            "msg": "Agent system not supported",
            "type": "value_error",
        }
    ]


@responses.activate
def test_add_live_agent_config_required_fields_not_exists():
    config = {
        "agent_type": "chatwoot",
        "config": {"api_access_token": "asdfghjklty67"},
        "override_bot": False,
        "trigger_on_intents": ["greet", "enquiry"],
        "trigger_on_actions": ["action_default_fallback", "action_enquiry"],
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/agents/live",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=config,
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert not actual["data"]
    assert actual["message"] == [
        {
            "loc": ["body", "config"],
            "msg": "Missing ['api_access_token', 'account_id'] all or any in config",
            "type": "value_error",
        }
    ]

    config = {
        "agent_type": "chatwoot",
        "config": {"account_id": "12"},
        "override_bot": False,
        "trigger_on_intents": ["greet", "enquiry"],
        "trigger_on_actions": ["action_default_fallback", "action_enquiry"],
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/agents/live",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=config,
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert not actual["data"]
    assert actual["message"] == [
        {
            "loc": ["body", "config"],
            "msg": "Missing ['api_access_token', 'account_id'] all or any in config",
            "type": "value_error",
        }
    ]


@responses.activate
def test_add_live_agent_config_invalid_credentials():
    config = {
        "agent_type": "chatwoot",
        "config": {"account_id": "12", "api_access_token": "asdfghjklty67"},
        "override_bot": False,
        "trigger_on_intents": ["greet", "enquiry"],
        "trigger_on_actions": ["action_default_fallback", "action_enquiry"],
    }

    responses.add(
        "GET",
        f"https://app.chatwoot.com/public/api/v1/accounts/{config['config']['account_id']}/inboxes",
        status=404,
        body="Not found",
    )
    response = client.put(
        f"/api/bot/{pytest.bot}/agents/live",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=config,
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert not actual["data"]
    assert actual["message"] == "Unable to connect. Please verify credentials."


@responses.activate
def test_add_live_agent_config_triggers_not_added():
    config = {
        "agent_type": "chatwoot",
        "config": {"account_id": "12", "api_access_token": "asdfghjklty67"},
        "override_bot": False,
    }

    add_inbox_response = open(
        "tests/testing_data/live_agent/add_inbox_response.json"
    ).read()
    add_inbox_response = json.loads(add_inbox_response)
    responses.add(
        "GET",
        f"https://app.chatwoot.com/api/v1/accounts/{config['config']['account_id']}/inboxes",
        json={"payload": []},
    )
    responses.add(
        "POST",
        f"https://app.chatwoot.com/api/v1/accounts/{config['config']['account_id']}/inboxes",
        json=add_inbox_response,
    )

    response = client.put(
        f"/api/bot/{pytest.bot}/agents/live",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=config,
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert not actual["data"]
    assert actual["message"] == [
        {
            "loc": ["body", "override_bot"],
            "msg": "At least 1 intent or action is required to perform agent handoff",
            "type": "value_error",
        }
    ]

    config = {
        "agent_type": "chatwoot",
        "config": {"account_id": "12", "api_access_token": "asdfghjklty67"},
        "override_bot": False,
        "trigger_on_intents": [],
        "trigger_on_actions": [],
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/agents/live",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=config,
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert not actual["data"]
    assert actual["message"] == [
        {
            "loc": ["body", "override_bot"],
            "msg": "At least 1 intent or action is required to perform agent handoff",
            "type": "value_error",
        }
    ]


@responses.activate
def test_add_live_agent_config():
    config = {
        "agent_type": "chatwoot",
        "config": {"account_id": "12", "api_access_token": "asdfghjklty67"},
        "override_bot": False,
        "trigger_on_intents": ["greet", "enquiry"],
        "trigger_on_actions": ["action_default_fallback", "action_enquiry"],
    }

    add_inbox_response = open(
        "tests/testing_data/live_agent/add_inbox_response.json"
    ).read()
    add_inbox_response = json.loads(add_inbox_response)
    responses.add(
        "GET",
        f"https://app.chatwoot.com/api/v1/accounts/{config['config']['account_id']}/inboxes",
        json={"payload": []},
    )
    responses.add(
        "POST",
        f"https://app.chatwoot.com/api/v1/accounts/{config['config']['account_id']}/inboxes",
        json=add_inbox_response,
    )

    response = client.put(
        f"/api/bot/{pytest.bot}/agents/live",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=config,
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert not actual["data"]
    assert actual["message"] == "Live agent system added"


def test_get_live_agent_config():
    response = client.get(
        f"/api/bot/{pytest.bot}/agents/live",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    add_inbox_response = open(
        "tests/testing_data/live_agent/add_inbox_response.json"
    ).read()
    add_inbox_response = json.loads(add_inbox_response)
    assert actual["data"]["agent"]
    actual["data"]["agent"].pop("timestamp")
    assert actual["data"]["agent"] == {
        "agent_type": "chatwoot",
        "config": {
            "account_id": "***",
            "api_access_token": "asdfghjklt***",
            "inbox_identifier": add_inbox_response["inbox_identifier"],
        },
        "override_bot": False,
        "trigger_on_intents": ["greet", "enquiry"],
        "trigger_on_actions": ["action_default_fallback", "action_enquiry"],
    }


@responses.activate
def test_update_live_agent_config():
    add_inbox_response = open(
        "tests/testing_data/live_agent/add_inbox_response.json"
    ).read()
    add_inbox_response = json.loads(add_inbox_response)
    add_inbox_response["inbox_identifier"] = "sdghghj5466789fghjk"
    list_inbox_response = open(
        "tests/testing_data/live_agent/list_inboxes_response.json"
    ).read()
    list_inbox_response = json.loads(list_inbox_response)
    list_inbox_response["payload"][1]["inbox_identifier"] = add_inbox_response[
        "inbox_identifier"
    ]
    config = {
        "agent_type": "chatwoot",
        "config": {
            "account_id": "13",
            "api_access_token": "jfjdjhsk567890",
            "inbox_identifier": add_inbox_response["inbox_identifier"],
        },
        "override_bot": True,
    }
    responses.add(
        "GET",
        f"https://app.chatwoot.com/api/v1/accounts/{config['config']['account_id']}/inboxes",
        json=list_inbox_response,
    )
    responses.add(
        "POST",
        f"https://app.chatwoot.com/api/v1/accounts/{config['config']['account_id']}/inboxes",
        json=add_inbox_response,
    )

    response = client.put(
        f"/api/bot/{pytest.bot}/agents/live",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=config,
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert not actual["data"]
    assert actual["message"] == "Live agent system added"


def test_get_live_agent_config_after_update():
    response = client.get(
        f"/api/bot/{pytest.bot}/agents/live",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["agent"]
    actual["data"]["agent"].pop("timestamp")
    assert actual["data"]["agent"] == {
        "agent_type": "chatwoot",
        "config": {
            "account_id": "***",
            "api_access_token": "jfjdjhsk567***",
            "inbox_identifier": "sdghghj5466789fghjk",
        },
        "override_bot": True,
        "trigger_on_intents": [],
        "trigger_on_actions": [],
    }


def test_delete_live_agent_config():
    response = client.delete(
        f"/api/bot/{pytest.bot}/agents/live",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert not actual["data"]
    assert actual["message"] == "Live agent system deleted"


def test_get_live_agent_config_after_delete():
    response = client.get(
        f"/api/bot/{pytest.bot}/agents/live",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["agent"] is None


def test_get_end_user_metrics_empty():
    response = client.get(
        f"/api/bot/{pytest.bot}/metric/user/logs/prod_chat?start_idx=0&page_size=10",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["logs"] == []
    assert actual["data"]["total"] == 0


def test_add_end_user_metrics():
    log_type = "user_metrics"
    response = client.post(
        f"/api/bot/{pytest.bot}/metric/user/logs/{log_type}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"data": {"source": "Digite.com", "language": "English"}},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert "id" in actual["data"]


@responses.activate
def test_add_end_user_metrics_with_ip(monkeypatch):
    log_type = "user_metrics"
    ip = "192.222.100.106"
    token = "abcgd563"
    enable = True
    monkeypatch.setitem(Utility.environment["plugins"]["location"], "token", token)
    monkeypatch.setitem(Utility.environment["plugins"]["location"], "enable", enable)
    ip_list = [ip.strip() for ip in ip.split(",")]
    url = f"https://ipinfo.io/batch?token={token}"
    payload = json.dumps(ip_list)
    expected = {
        "ip": "140.82.201.129",
        "city": "Mumbai",
        "region": "Maharashtra",
        "country": "IN",
        "loc": "19.0728,72.8826",
        "org": "AS13150 CATO NETWORKS LTD",
        "postal": "400070",
        "timezone": "Asia/Kolkata",
    }
    responses.add("POST", url, json=expected)
    response = client.post(
        f"/api/bot/{pytest.bot}/metric/user/logs/{log_type}",
        headers={
            "Authorization": pytest.token_type + " " + pytest.access_token,
            "X-Forwarded-For": "192.222.100.106",
        },
        json={"data": {"source": "Digite.com", "language": "English", "ip": ip}},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert "id" in actual["data"]


@responses.activate
def test_add_end_user_metrics_ip_request_failure(monkeypatch):
    log_type = "user_metrics"
    ip = "192.222.100.106"
    token = "abcgd563"
    enable = True
    monkeypatch.setitem(Utility.environment["plugins"]["location"], "token", token)
    monkeypatch.setitem(Utility.environment["plugins"]["location"], "enable", enable)
    url = f"https://ipinfo.io/{ip}?token={token}"
    responses.add("GET", url, status=500)
    response = client.post(
        f"/api/bot/{pytest.bot}/metric/user/logs/{log_type}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"data": {"source": "Digite.com", "language": "English"}},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert "id" in actual["data"]


def test_add_and_update_conversation_feedback(monkeypatch):
    log_type = "conversation_feedback"
    data = {
        "feedback": "",
        "rating": 1,
        "botId": "6322ebbb3c62158dab4aee71",
        "botReply": [{"text": "Hello! How are you?"}],
        "userReply": "",
        "date": "2023-07-17T06:48:02.453Z",
        "sender_id": None,
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/metric/user/logs/{log_type}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"data": data},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert "id" in actual["data"]
    assert actual["message"] == "Metrics added"
    id = actual["data"]["id"]

    response = client.put(
        f"/api/bot/{pytest.bot}/metric/user/logs/{log_type}/{id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"data": {"feedback": "Good"}},
    )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert not actual["data"]
    assert actual["message"] == "Metrics updated"


def test_get_end_user_metrics(monkeypatch):
    token = "abcgd563"
    enable = True
    monkeypatch.setitem(Utility.environment["plugins"]["location"], "token", token)
    monkeypatch.setitem(Utility.environment["plugins"]["location"], "enable", enable)
    url = f"https://ipinfo.io/batch?token={token}"

    expected = {
        "ip": "140.82.201.129",
        "city": "Mumbai",
        "region": "Maharashtra",
        "country": "IN",
        "loc": "19.0728,72.8826",
        "org": "AS13150 CATO NETWORKS LTD",
        "postal": "400070",
        "timezone": "Asia/Kolkata",
    }
    responses.add("POST", url, json=expected)
    for i in range(5):
        client.post(
            f"/api/bot/{pytest.bot}/metric/user/logs/{MetricType.agent_handoff}",
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
            json={"data": {"source": "Digite.com", "language": "English"}},
        )

    response = client.get(
        f"/api/bot/{pytest.bot}/metric/user/logs/agent_handoff?start_idx=0&page_size=10",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["success"]
    assert len(actual["data"]["logs"]) == 5
    assert actual["data"]["total"] == 5
    response = client.get(
        f"/api/bot/{pytest.bot}/metric/user/logs/user_metrics?start_idx=0&page_size=10",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]["logs"]) == 5
    assert actual["data"]["total"] == 5
    actual["data"]["logs"][0].pop("timestamp")
    actual["data"]["logs"][0].pop("account")
    assert actual["data"]["logs"][0] == {
        "metric_type": "user_metrics",
        "user": "integ1@gmail.com",
        "bot": pytest.bot,
        "source": "Digite.com",
        "language": "English",
    }
    actual["data"]["logs"][1].pop("timestamp")
    actual["data"]["logs"][1].pop("account")
    actual["data"]["logs"][2].pop("timestamp")
    actual["data"]["logs"][2].pop("account")
    assert actual["data"]["logs"][1]["ip"]
    del actual["data"]["logs"][1]["ip"]
    assert actual["data"]["logs"][1] == {
        "metric_type": "user_metrics",
        "user": "integ1@gmail.com",
        "bot": pytest.bot,
        "source": "Digite.com",
        "language": "English",
        "city": "Mumbai",
        "region": "Maharashtra",
        "country": "IN",
        "loc": "19.0728,72.8826",
        "org": "AS13150 CATO NETWORKS LTD",
        "postal": "400070",
        "timezone": "Asia/Kolkata",
    }
    assert actual["data"]["logs"][2] == {
        "metric_type": "user_metrics",
        "user": "integ1@gmail.com",
        "bot": pytest.bot,
        "source": "Digite.com",
        "language": "English",
    }

    response = client.get(
        f"/api/bot/{pytest.bot}/metric/user/logs/agent_handoff?start_idx=3",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0

    response = client.get(
        f"/api/bot/{pytest.bot}/metric/user/logs/agent_handoff?start_idx=3&page_size=1",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]["logs"]) == 1
    assert actual["data"]["total"] == 5


def test_get_roles():
    response = client.get(
        f"/api/user/roles/access",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] == Utility.system_metadata["roles"]


def test_generate_limited_access_temporary_token():
    response = client.get(
        f"/api/auth/{pytest.bot}/integration/token/temp",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["access_token"]
    assert actual["data"]["token_type"]
    assert (
            actual["message"]
            == "This token will be shown only once. Please copy this somewhere safe."
               "It is your responsibility to keep the token secret. If leaked, others may have access to your system."
    )
    token = actual["data"]["access_token"]

    response = client.get(
        f"/api/bot/{pytest.bot}/chat/client/config/{actual['data']['access_token']}",
        headers={"Authorization": pytest.token_type + " " + token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]
    assert isinstance(actual["data"], dict)
    assert None == actual.get("data").get("whitelist")

    response = client.get(
        f"/api/bot/{pytest.bot}/slots",
        headers={"Authorization": pytest.token_type + " " + token},
    )
    actual = response.json()
    assert actual == {
        "success": False,
        "message": "Access denied for this endpoint",
        "data": None,
        "error_code": 422,
    }

    response = client.post(
        f"/api/bot/{pytest.bot}/intents",
        json={"data": "happier"},
        headers={"Authorization": pytest.token_type + " " + token},
    )
    actual = response.json()
    assert actual == {
        "success": False,
        "message": "Access denied for this endpoint",
        "data": None,
        "error_code": 422,
    }

    response = client.post(
        "/api/account/bot",
        json={"name": "covid-bot"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    response = response.json()
    assert response["error_code"] == 0

    response = client.get(
        "/api/account/bot",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    bot_2 = response["data"]["account_owned"][1]["_id"]

    response = client.get(
        f"/api/bot/{bot_2}/chat/client/config/{token}",
    )
    actual = response.json()
    assert actual == {
        "success": False,
        "message": "Invalid token",
        "data": None,
        "error_code": 401,
    }


def test_get_client_config_using_uid_invalid_domains(monkeypatch):
    config_path = "./template/chat-client/default-config.json"
    config = json.load(open(config_path))
    config["headers"] = {}
    config["headers"]["X-USER"] = "kairon-user"
    config["whitelist"] = ["kairon.digite.com", "kairon-api.digite.com"]
    client.post(
        f"/api/bot/{pytest.bot}/chat/client/config",
        json={"data": config},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    monkeypatch.setitem(
        Utility.environment["model"]["agent"], "url", "http://localhost"
    )
    response = client.get(
        pytest.url, headers={"HTTP_REFERER": "http://www.attackers.com"}
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 403
    assert not actual["data"]
    assert actual["message"] == "Domain not registered for kAIron client"


def test_get_client_config_using_uid_valid_domains(monkeypatch):
    monkeypatch.setitem(
        Utility.environment["model"]["agent"], "url", "http://localhost"
    )
    response = client.get(
        pytest.url, headers={"HTTP_REFERER": "https://kairon-api.digite.com"}
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]
    assert None == actual.get("data").get("whitelist")


def test_get_client_config_using_uid_invalid_domains_referer(monkeypatch):
    monkeypatch.setitem(
        Utility.environment["model"]["agent"], "url", "http://localhost"
    )
    response = client.get(pytest.url, headers={"referer": "http://www.attackers.com"})
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 403
    assert not actual["data"]
    assert actual["message"] == "Domain not registered for kAIron client"


def test_get_client_config_using_uid_valid_domains_referer(monkeypatch):
    monkeypatch.setitem(
        Utility.environment["model"]["agent"], "url", "http://localhost"
    )
    response = client.get(
        pytest.url, headers={"referer": "https://kairon-api.digite.com"}
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]
    assert None == actual.get("data").get("whitelist")


def test_save_client_config_invalid_domain_format():
    config_path = "./template/chat-client/default-config.json"
    config = json.load(open(config_path))
    config["headers"] = {}
    config["headers"]["X-USER"] = "kairon-user"
    config["whitelist"] = ["invalid_domain_format"]
    response = client.post(
        f"/api/bot/{pytest.bot}/chat/client/config",
        json={"data": config},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "One of the domain is invalid"


def get_client_config_valid_domain():
    response = client.get(
        f"/api/bot/{pytest.bot}/chat/client/config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]
    assert actual["data"]["whitelist"] == ["kairon.digite.com", "kairon-api.digite.com"]


def test_multilingual_translate_logs_empty():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/multilingual/logs?start_idx=0&page_size=10",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"]["logs"] == []
    assert actual["data"]["total"] == 0


@responses.activate
def test_multilingual_translate():
    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.multilingual}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
        match=[
            responses.matchers.json_params_matcher(
                {
                    "data": {
                        "bot": pytest.bot,
                        "user": "integ1@gmail.com",
                        "dest_lang": "es",
                        "translate_responses": "",
                        "translate_actions": "",
                    },
                    "cron_exp": None,
                    "timezone": None,
                }
            )
        ],
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/multilingual/translate",
        json={
            "dest_lang": "es",
            "translate_responses": False,
            "translate_actions": False,
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()

    assert response["success"]
    assert response["message"] == "Bot translation in progress! Check logs."
    assert response["error_code"] == 0
    MultilingualLogProcessor.add_log(
        pytest.bot, "integ1@gmail.com", event_status="Completed", status="Success"
    )


def test_multilingual_translate_invalid_bot_id():
    response = client.post(
        f"/api/bot/{pytest.bot + '0'}/multilingual/translate",
        json={
            "dest_lang": "es",
            "translate_responses": False,
            "translate_actions": False,
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()

    assert not response["success"]
    assert response["message"] == "Access to bot is denied"
    assert response["error_code"] == 422


def test_multilingual_translate_no_destination_lang():
    response = client.post(
        f"/api/bot/{pytest.bot}/multilingual/translate",
        json={"translate_responses": False, "translate_actions": False},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()

    assert not response["success"]
    assert response["message"] == [
        {
            "loc": ["body", "dest_lang"],
            "msg": "field required",
            "type": "value_error.missing",
        }
    ]
    assert response["error_code"] == 422

    response = client.post(
        f"/api/bot/{pytest.bot}/multilingual/translate",
        json={
            "dest_lang": " ",
            "translate_responses": False,
            "translate_actions": False,
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()

    assert not response["success"]
    assert response["message"] == [
        {
            "loc": ["body", "dest_lang"],
            "msg": "dest_lang cannot be empty",
            "type": "value_error",
        }
    ]
    assert response["error_code"] == 422


def test_multilingual_translate_limit_exceeded(monkeypatch):
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.multilingual_limit_per_day = 0
    bot_settings.save()

    response = client.post(
        f"/api/bot/{pytest.bot}/multilingual/translate",
        json={
            "dest_lang": "es",
            "translate_responses": False,
            "translate_actions": False,
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()

    assert response["message"] == "Daily limit exceeded."
    assert response["error_code"] == 422
    assert not response["success"]


@responses.activate
def test_multilingual_translate_using_event_with_actions_and_responses(monkeypatch):
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.multilingual_limit_per_day = 2
    bot_settings.save()
    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.multilingual}",
    )
    responses.add(
        responses.POST,
        event_url,
        status=200,
        json={"success": True, "message": "Event triggered successfully!"},
        match=[
            responses.matchers.json_params_matcher(
                {
                    "data": {
                        "bot": pytest.bot,
                        "user": "integ1@gmail.com",
                        "dest_lang": "es",
                        "translate_responses": "--translate-responses",
                        "translate_actions": "--translate-actions",
                    },
                    "cron_exp": None,
                    "timezone": None,
                }
            )
        ],
    )

    response = client.post(
        f"/api/bot/{pytest.bot}/multilingual/translate",
        json={
            "dest_lang": "es",
            "translate_responses": True,
            "translate_actions": True,
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()

    assert response["success"]
    assert response["error_code"] == 0
    assert response["message"] == "Bot translation in progress! Check logs."


def test_multilingual_translate_in_progress():
    response = client.post(
        url=f"/api/bot/{pytest.bot}/multilingual/translate",
        json={
            "dest_lang": "es",
            "translate_responses": False,
            "translate_actions": False,
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    assert response["error_code"] == 422
    assert response["message"] == "Event already in progress! Check logs."
    assert not response["success"]


def test_multilingual_translate_logs():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/multilingual/logs?start_idx=0&page_size=10",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]["logs"]) == 2
    assert actual["data"]["total"] == 2
    assert actual["data"]["logs"][0]["d_lang"] == "es"
    assert actual["data"]["logs"][0]["copy_type"] == "Translation"
    assert actual["data"]["logs"][0]["translate_responses"]
    assert actual["data"]["logs"][0]["translate_actions"]
    assert actual["data"]["logs"][0]["event_status"] == "Enqueued"
    assert actual["data"]["logs"][0]["start_timestamp"]
    assert actual["data"]["logs"][1]["d_lang"] == "es"
    assert actual["data"]["logs"][1]["copy_type"] == "Translation"
    assert actual["data"]["logs"][1]["translate_responses"] == False
    assert actual["data"]["logs"][1]["translate_actions"] == False
    assert actual["data"]["logs"][1]["event_status"] == "Completed"
    assert actual["data"]["logs"][1]["status"] == "Success"
    assert actual["data"]["logs"][1]["start_timestamp"]
    assert actual["data"]["logs"][1]["end_timestamp"]


def test_multilingual_language_support(monkeypatch):
    def _mock_supported_languages(*args, **kwargs):
        return ["es", "en", "hi"]

    monkeypatch.setattr(
        Translator, "get_supported_languages", _mock_supported_languages
    )

    response = client.get(
        f"/api/user/multilingual/languages",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()

    assert response["data"] == ["es", "en", "hi"]
    assert response["success"]
    assert response["error_code"] == 0


@responses.activate
def test_data_generation_from_website(monkeypatch):
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.data_generation_limit_per_day = 10
    bot_settings.save()

    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.data_generator}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
        match=[
            responses.matchers.json_params_matcher(
                {
                    "data": {
                        "bot": pytest.bot,
                        "user": "integ1@gmail.com",
                        "type": "--from-website",
                        "website_url": "website.com",
                        "depth": 1,
                    },
                    "cron_exp": None,
                    "timezone": None,
                }
            )
        ],
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/data/generator/website?website_url=website.com&depth=1",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    assert response["success"]
    assert response["message"] == "Story generator in progress! Check logs."
    assert response["error_code"] == 0
    TrainingDataGenerationProcessor.set_status(
        pytest.bot, "integ1@gmail.com", status="Completed"
    )


def test_data_generation_invalid_bot_id():
    response = client.post(
        f"/api/bot/{pytest.bot + '0'}/data/generator/website?website_url=website.com",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()

    assert not response["success"]
    assert response["message"] == "Access to bot is denied"
    assert response["error_code"] == 422


def test_data_generation_no_website_url(monkeypatch):
    monkeypatch.setitem(Utility.environment["data_generation"], "limit_per_day", 10)

    response = client.post(
        f"/api/bot/{pytest.bot}/data/generator/website",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()

    assert not response["success"]
    assert response["message"] == [
        {
            "loc": ["query", "website_url"],
            "msg": "field required",
            "type": "value_error.missing",
        }
    ]
    assert response["error_code"] == 422

    response = client.post(
        f"/api/bot/{pytest.bot}/data/generator/website?website_url= ",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()

    assert not response["success"]
    assert response["message"] == "website_url cannot be empty"
    assert response["error_code"] == 422


@responses.activate
def test_data_generation_limit_exceeded(monkeypatch):
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.data_generation_limit_per_day = 0
    bot_settings.save()

    response = client.post(
        f"/api/bot/{pytest.bot}/data/generator/website?website_url=website.com",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()

    assert response["message"] == "Daily limit exceeded."
    assert response["error_code"] == 422
    assert not response["success"]


@responses.activate
def test_data_generation_in_progress(monkeypatch):
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.data_generation_limit_per_day = 10
    bot_settings.save()

    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.data_generator}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
        match=[
            responses.matchers.json_params_matcher(
                {
                    "data": {
                        "bot": pytest.bot,
                        "user": "integ1@gmail.com",
                        "type": "--from-website",
                        "website_url": "website.com",
                        "depth": 0,
                    },
                    "cron_exp": None,
                    "timezone": None,
                }
            )
        ],
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/data/generator/website?website_url=website.com",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    assert response["success"]
    assert response["message"] == "Story generator in progress! Check logs."
    assert response["error_code"] == 0

    response = client.post(
        f"/api/bot/{pytest.bot}/data/generator/website?website_url=website.com",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    assert response["error_code"] == 422
    assert response["message"] == "Event already in progress! Check logs."
    assert not response["success"]


def test_download_logs(monkeypatch):
    start_date = datetime.utcnow()
    end_date = datetime.utcnow() + timedelta(days=1)
    response = client.get(
        f"/api/bot/{pytest.bot}/logs/download/model_training?start_date={start_date}&end_date={end_date}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    response = response.json()
    assert response == {
        "success": False,
        "message": "Logs not found!",
        "data": None,
        "error_code": 422,
    }


def test_download_logs_with_action_logs(monkeypatch):
    import csv

    start_date = datetime.utcnow()
    end_date = datetime.utcnow() + timedelta(days=1)
    bot = pytest.bot
    request_params = {"key": "value", "key2": "value2"}
    ActionServerLogs(
        intent="intent1",
        action="http_action",
        sender="sender_id",
        timestamp="2021-04-05T07:59:08.771000",
        request_params=request_params,
        api_response="Response",
        bot_response="Bot Response",
        bot=bot,
    ).save()
    ActionServerLogs(
        intent="intent2",
        action="http_action",
        sender="sender_id",
        url="http://kairon-api.digite.com/api/bot",
        request_params=request_params,
        api_response="Response",
        bot_response="Bot Response",
        bot=bot,
        status="FAILURE",
    ).save()
    ActionServerLogs(
        intent="intent3",
        action="http_action",
        sender="sender_id",
        request_params=request_params,
        api_response="Response",
        bot_response="Bot Response",
        bot=bot,
        status="FAILURE",
    ).save()
    ActionServerLogs(
        intent="intent4",
        action="http_action",
        sender="sender_id",
        request_params=request_params,
        api_response="Response",
        bot_response="Bot Response",
        bot=bot,
    ).save()
    ActionServerLogs(
        intent="intent5",
        action="http_action",
        sender="sender_id",
        request_params=request_params,
        api_response="Response",
        bot_response="Bot Response",
        bot=bot,
        status="FAILURE",
    ).save()

    response = client.get(
        f"/api/bot/{pytest.bot}/logs/download/action_logs?start_date={start_date}&end_date={end_date}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    assert response.content
    csv_content = response.content.decode("utf-8")
    csv_file = csv.reader(csv_content.splitlines())
    action_logs = list(csv_file)
    assert len(action_logs) == 5


def test_get_auditlog_for_user_1():
    email = "integration1234567890@demo.ai"
    response = client.post(
        "/api/auth/login",
        data={"username": email, "password": "Welcome@10"},
    )
    login = response.json()
    response = client.get(
        f"/api/user/auditlog/data",
        headers={
            "Authorization": login["data"]["token_type"]
                             + " "
                             + login["data"]["access_token"]
        },
    )
    actual = response.json()

    assert actual["data"] is not None
    assert actual["data"][0]["action"] == AuditlogActions.ACTIVITY.value
    assert actual["data"][0]["entity"] == "login"
    assert actual["data"][0]["user"] == email

    assert actual["data"][0]["action"] == AuditlogActions.ACTIVITY.value
    assert actual["data"][0]["attributes"][0]["value"] is not None


def test_get_auditlog_for_bot():
    from_date = datetime.utcnow().date() - timedelta(days=1)
    to_date = datetime.utcnow().date() + timedelta(days=1)
    response = client.get(
        f"/api/bot/{pytest.bot}/auditlog/data/{from_date}/{to_date}?start_idx=0&page_size=100",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    audit_log_data = actual["data"]["logs"]

    assert audit_log_data is not None
    actions = [d["action"] for d in audit_log_data]
    from collections import Counter

    counter = Counter(actions)
    assert counter.get(AuditlogActions.SAVE.value) > 5
    assert counter.get(AuditlogActions.SOFT_DELETE.value) >= 3
    assert counter.get(AuditlogActions.UPDATE.value) > 5


@mock.patch('kairon.shared.account.activity_log.UserActivityLogger.is_login_within_cooldown_period', autospec=True)
def test_get_auditlog_for_user_2(mock_password_reset):
    def _password_reset(*args, **kwargs):
        return

    mock_password_reset.return_value = _password_reset
    email = "integration@demo.ai"
    response = client.post(
        "/api/auth/login",
        data={"username": email, "password": "Welcome@10"},
    )
    login_2 = response.json()
    response = client.get(
        f"/api/user/auditlog/data?start_idx=0&page_size=100",
        headers={
            "Authorization": login_2["data"]["token_type"]
                             + " "
                             + login_2["data"]["access_token"]
        },
    )
    actual = response.json()
    audit_log_data = actual["data"]
    assert audit_log_data is not None
    actions = [d["action"] for d in audit_log_data]
    from collections import Counter

    counter = Counter(actions)
    assert counter.get(AuditlogActions.SAVE.value) > 5
    assert counter.get(AuditlogActions.SOFT_DELETE.value) >= 1
    assert counter.get(AuditlogActions.UPDATE.value) > 5

    assert audit_log_data[0]["action"] == AuditlogActions.ACTIVITY.value
    assert audit_log_data[0]["entity"] == "login"
    assert audit_log_data[0]["user"] == email


def test_add_custom_widget():
    response = client.post(
        url=f"/api/bot/{pytest.bot}/widgets/custom",
        json={
            "name": "agtech weekly trends",
            "http_url": "http://agtech.com/trends/1",
            "request_parameters": [
                {"key": "crop_type", "value": "tomato", "parameter_type": "value"},
                {"key": "org", "value": "ORG_NAME", "parameter_type": "key_vault"},
            ],
            "headers": [
                {"key": "client", "value": "kairon", "parameter_type": "value"},
                {
                    "key": "authorization",
                    "value": "AUTH_TOKEN",
                    "parameter_type": "key_vault",
                },
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Widget config added!"
    assert actual["data"]
    pytest.widget_id = actual["data"]
    assert actual["error_code"] == 0


def test_get_custom_widget():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/widgets/custom",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"]["widgets"] == [
        {
            "name": "agtech weekly trends",
            "http_url": "http://agtech.com/trends/1",
            "request_parameters": [
                {"key": "crop_type", "value": "tomato", "parameter_type": "value"},
                {"key": "org", "value": "ORG_NAME", "parameter_type": "key_vault"},
            ],
            "headers": [
                {"key": "client", "value": "kairon", "parameter_type": "value"},
                {
                    "key": "authorization",
                    "value": "AUTH_TOKEN",
                    "parameter_type": "key_vault",
                },
            ],
            "timeout": 5,
            "bot": pytest.bot,
            "request_method": "GET",
            "_id": pytest.widget_id,
        }
    ]
    assert actual["error_code"] == 0
    assert not actual["message"]


@responses.activate
def test_add_member_with_view_role():
    email = "test_view@demo.ai"
    response = client.post(
        "/api/account/registration",
        json={
            "email": email,
            "first_name": "Dem",
            "last_name": "User22",
            "password": "Welcome@10",
            "confirm_password": "Welcome@10",
            "account": email,
        },
    )
    actual = response.json()
    assert actual["message"] == "Account Registered!"
    assert actual["error_code"] == 0
    assert actual["success"]

    response = client.post(
        f"/api/user/{pytest.bot}/member",
        json={"email": email, "role": "view"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"]
    assert actual["error_code"] == 0
    assert actual["success"]

    response = client.post(
        "/api/auth/login",
        data={"username": email, "password": "Welcome@10"},
    )
    actual = response.json()

    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "User Authenticated"
    pytest.refresh_token_view_role = actual["data"]["refresh_token"]
    pytest.access_token_view_role = actual["data"]["access_token"]


@responses.activate
def test_trigger_widget():
    expected_query_parameters = {"crop_type": "tomato", "org": "kairon"}
    expected_query_parameters.update(
        {"start_date": "11-11-2021", "end_date": "21-11-2021"}
    )
    expected_resp = {"data": [{"1": 200, "2": 300, "3": 400, "4": 500, "5": 600}]}

    for key_vault in [
        {"key": "ORG_NAME", "value": "kairon"},
        {"key": "AUTH_TOKEN", "value": "sdfghjk456789"},
    ]:
        response = client.post(
            f"/api/bot/{pytest.bot}/secrets/add",
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
            json=key_vault,
        )
        actual = response.json()
        assert actual["error_code"] == 0
        assert actual["success"]

    responses.add(
        "GET",
        "http://agtech.com/trends/1",
        json=expected_resp,
        match=[
            responses.matchers.query_param_matcher(expected_query_parameters),
            responses.matchers.header_matcher(
                {"client": "kairon", "authorization": "sdfghjk456789"}
            ),
        ],
    )

    # Test with view role
    response = client.get(
        url=f"/api/bot/{pytest.bot}/widgets/custom/trigger/{pytest.widget_id}?start_date=11-11-2021&end_date=21-11-2021",
        headers={
            "Authorization": pytest.token_type + " " + pytest.access_token_view_role
        },
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] == expected_resp
    assert not actual["message"]

    # Test with admin role
    response = client.get(
        url=f"/api/bot/{pytest.bot}/widgets/custom/trigger/{pytest.widget_id}?start_date=11-11-2021&end_date=21-11-2021",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] == expected_resp
    assert not actual["message"]

    response = client.get(
        url=f"/api/bot/{pytest.bot}/widgets/custom/logs/all",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]) == 2
    assert not actual["message"]


def test_add_custom_widget_invalid_config():
    response = client.post(
        url=f"/api/bot/{pytest.bot}/widgets/custom",
        json={
            "name": "agtech weekly trends 1",
            "http_url": "http://agtech.com/trends/1",
            "request_parameters": [
                {"key": "crop_type", "value": "tomato", "parameter_type": "sender_id"},
                {"key": "org", "value": "ORG_NAME", "parameter_type": "key_vault"},
            ],
            "headers": [
                {"key": "client", "value": "kairon", "parameter_type": "value"},
                {
                    "key": "authorization",
                    "value": "AUTH_TOKEN",
                    "parameter_type": "key_vault",
                },
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == [
        {
            "ctx": {"enum_values": ["value", "key_vault"]},
            "loc": ["body", "request_parameters", 0, "parameter_type"],
            "msg": "value is not a valid enumeration member; permitted: 'value', 'key_vault'",
            "type": "type_error.enum",
        }
    ]
    assert not actual["data"]
    assert actual["error_code"] == 422


def test_add_custom_widget_already_exists():
    response = client.post(
        url=f"/api/bot/{pytest.bot}/widgets/custom",
        json={
            "name": "agtech weekly trends",
            "http_url": "http://agtech.com/trends/1",
            "request_parameters": [
                {"key": "crop_type", "value": "tomato", "parameter_type": "value"},
                {"key": "org", "value": "ORG_NAME", "parameter_type": "key_vault"},
            ],
            "headers": [
                {"key": "client", "value": "kairon", "parameter_type": "value"},
                {
                    "key": "authorization",
                    "value": "AUTH_TOKEN",
                    "parameter_type": "key_vault",
                },
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Widget with name exists!"
    assert not actual["data"]
    assert actual["error_code"] == 422


def test_edit_custom_widget_invalid_config():
    response = client.put(
        url=f"/api/bot/{pytest.bot}/widgets/custom/{pytest.widget_id}",
        json={"name": "agtech weekly trends 1", "http_url": None},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == [
        {
            "loc": ["body", "http_url"],
            "msg": "none is not an allowed value",
            "type": "type_error.none.not_allowed",
        }
    ]
    assert not actual["data"]
    assert actual["error_code"] == 422


def test_edit_custom_widget():
    response = client.put(
        url=f"/api/bot/{pytest.bot}/widgets/custom/{pytest.widget_id}",
        json={
            "name": "agtech trends ",
            "http_url": "http://agtech.com/trends",
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Widget config updated!"
    assert not actual["data"]
    assert actual["error_code"] == 0


def test_list_custom_widgets():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/widgets/custom/list",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"]["widgets"] == [pytest.widget_id]
    assert actual["error_code"] == 0
    assert not actual["message"]


def test_get_custom_widget_post_update():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/widgets/custom",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"]["widgets"] == [
        {
            "name": "agtech trends ",
            "http_url": "http://agtech.com/trends",
            "timeout": 5,
            "request_method": "GET",
            "request_parameters": [],
            # "_id": pytest.bot,
            "headers": [],
            "bot": pytest.bot,
            "_id": pytest.widget_id,
        }
    ]
    assert actual["error_code"] == 0
    assert not actual["message"]


def test_delete_custom_widget():
    response = client.delete(
        url=f"/api/bot/{pytest.bot}/widgets/custom/{pytest.widget_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Widget config removed!"
    assert not actual["data"]
    assert actual["error_code"] == 0


def test_trigger_widget_failure():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/widgets/custom/trigger/{pytest.widget_id}",
        headers={
            "Authorization": pytest.token_type + " " + pytest.access_token_view_role
        },
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert not actual["data"]
    assert actual["message"] == "Widget does not exists!"


def test_delete_custom_widget_invalid_widget_id():
    response = client.delete(
        url=f"/api/bot/{pytest.bot}/widgets/custom/{pytest.widget_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Widget does not exists!"
    assert not actual["data"]
    assert actual["error_code"] == 422


def test_list_custom_widgets_empty():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/widgets/custom",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"]["widgets"] == []
    assert actual["error_code"] == 0
    assert not actual["message"]


def test_get_custom_widget_post_delete():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/widgets/custom",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["data"]["widgets"]
    assert actual["error_code"] == 0
    assert not actual["message"]


@responses.activate
def test_upload_invalid_csv():
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.data_importer_limit_per_day = 10
    bot_settings.save()
    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.faq_importer}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )
    csv_file = "Questions,Answer,\nWhat is Digite?, IT Company,\nHow are you?, I am good,\nWhat day is it?, It is Thursday,\n   ,  ,\nWhat day is it?, It is Thursday,\n".encode()
    csv_file = BytesIO(csv_file).read()
    files = {"csv_file": ("config.arff", csv_file)}
    response = client.post(
        f"/api/bot/{pytest.bot}/data/faq/upload",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=files,
    )
    actual = response.json()
    assert actual["data"] is None
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert (
            actual["message"] == "Invalid file type! Only csv and xlsx files are supported."
    )


@responses.activate
def test_upload_faq():
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.data_importer_limit_per_day = 10
    bot_settings.save()
    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.faq_importer}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )
    csv_file = "Questions,Answer,\nWhat is Digite?, IT Company,\nHow are you?, I am good,\nWhat day is it?, It is Thursday,\n   ,  ,\nWhat day is it?, It is Thursday,\n".encode()
    csv_file = BytesIO(csv_file).read()
    files = {"csv_file": ("config.csv", csv_file)}
    response = client.post(
        f"/api/bot/{pytest.bot}/data/faq/upload?overwrite=false",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=files,
    )
    actual = response.json()
    assert actual["message"] == "Upload in progress! Check logs."
    assert actual["data"] is None
    assert actual["success"]
    assert actual["error_code"] == 0


def test_download_faq(monkeypatch):
    data = [
        {
            "_id": "638dde37cfe8a7de324067fa",
            "story": "accelerator_28",
            "intent": "accelerator_28",
            "utterance": "utter_accelerator_28",
            "training_examples": [
                {
                    "text": "What is the purpose of an acceleration?",
                    "_id": "638dde36cfe8a7de32405eaa",
                },
                {
                    "text": "What is the purpose of an accelerators?",
                    "_id": "638dde36cfe8a7de32405eab",
                },
            ],
            "responses": [
                {
                    "_id": "638dde35cfe8a7de32405ada",
                    "text": {
                        "text": "•\tAnything that helps project teams reduce effort, save cost"
                    },
                }
            ],
        },
        {
            "_id": "638dde37cfe8a7de324067fd",
            "story": "accelerator_subscription_mainspring_31",
            "intent": "accelerator_subscription_mainspring_31",
            "utterance": "utter_accelerator_subscription_mainspring_31",
            "training_examples": [
                {
                    "text": "•\tHow do I subscribe to accelerators for my project?",
                    "_id": "638dde36cfe8a7de32405ec0",
                },
                {
                    "text": "•\tHow to do accelerator subscription in mainspring",
                    "_id": "638dde36cfe8a7de32405ec1",
                },
            ],
            "responses": [
                {
                    "_id": "638dde35cfe8a7de32405b64",
                    "custom": {
                        "custom": {
                            "data": [
                                {
                                    "type": "paragraph",
                                    "children": [
                                        {
                                            "text": "Step 1 : Navigate to PM Plan >> Delivery Assets"
                                        }
                                    ],
                                },
                                {
                                    "type": "paragraph",
                                    "children": [
                                        {
                                            "text": "Step 2 : Subscribe the accelerators which are applicable"
                                        }
                                    ],
                                },
                            ]
                        }
                    },
                }
            ],
        },
        {
            "_id": "638dde37cfe8a7de324067fe",
            "story": "accelerators_auto_recommended_32",
            "intent": "accelerators_auto_recommended_32",
            "utterance": "utter_accelerators_auto_recommended_32",
            "training_examples": [
                {
                    "text": "•\tOn what basis are accelerators recommended for a project?",
                    "_id": "638dde36cfe8a7de32405ec3",
                },
                {
                    "text": "•\tWhat is the criteria based on which accelerators are auto recommended ?",
                    "_id": "638dde36cfe8a7de32405ec4",
                },
            ],
            "responses": [
                {
                    "_id": "638dde35cfe8a7de32405b2d",
                    "text": {
                        "text": "•\tAccelerators are auto-recommended from Knowhub based on these project attributes"
                    },
                }
            ],
        },
    ]

    def __mock_qna(*args, **kwargs):
        for item in data:
            yield item

    monkeypatch.setattr(BaseQuerySet, "aggregate", __mock_qna)
    response = client.get(
        f"/api/bot/{pytest.bot}/data/faq/download",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    assert response.content


@responses.activate
def test_idp_provider_fields():
    response = client.get(
        "/api/idp/provider/fields",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    actual_data = Utility.system_metadata["providers"]

    assert response["data"] == actual_data
    assert len(response["data"]["oidc"]["azure_oidc"]["required_fields"]) == 4


@responses.activate
def test_add_organization():
    email = "integration1234567890@demo.ai"
    response = client.post(
        "/api/auth/login",
        data={"username": email, "password": "Welcome@10"},
    )
    login = response.json()
    response = client.post(
        "/api/account/organization",
        json={"data": {"name": "sample"}},
        headers={
            "Authorization": login["data"]["token_type"]
                             + " "
                             + login["data"]["access_token"]
        },
    )
    result = response.json()
    assert result["data"]["org_id"] is not None
    assert result["message"] == "organization added"


@responses.activate
def test_get_organization():
    email = "integration1234567890@demo.ai"
    response = client.post(
        "/api/auth/login",
        data={"username": email, "password": "Welcome@10"},
    )
    login = response.json()
    response = client.get(
        "/api/account/organization",
        headers={
            "Authorization": login["data"]["token_type"]
                             + " "
                             + login["data"]["access_token"]
        },
    )
    result = response.json()
    assert result["data"] is not None
    assert result["data"]["name"] == "sample"
    assert result["data"]["user"] == "integration1234567890@demo.ai"


@responses.activate
def test_update_organization():
    email = "integration1234567890@demo.ai"
    response = client.post(
        "/api/auth/login",
        data={"username": email, "password": "Welcome@10"},
    )
    login = response.json()
    response = client.post(
        "/api/account/organization",
        json={"data": {"name": "updated_sample"}},
        headers={
            "Authorization": login["data"]["token_type"]
                             + " "
                             + login["data"]["access_token"]
        },
    )
    result = response.json()
    assert result["message"] == "organization added"


@responses.activate
def test_get_organization_after_update():
    email = "integration1234567890@demo.ai"
    response = client.post(
        "/api/auth/login",
        data={"username": email, "password": "Welcome@10"},
    )
    login = response.json()
    response = client.get(
        "/api/account/organization",
        headers={
            "Authorization": login["data"]["token_type"]
                             + " "
                             + login["data"]["access_token"]
        },
    )
    result = response.json()
    assert result["data"] is not None
    assert result["data"]["name"] == "updated_sample"
    assert result["data"]["user"] == "integration1234567890@demo.ai"


@responses.activate
def test_delete_organization(monkeypatch):
    def _delete_idp(*args, **kwargs):
        return

    monkeypatch.setattr(IDPProcessor, "delete_idp", _delete_idp)
    email = "integration1234567890@demo.ai"
    response = client.post(
        "/api/auth/login",
        data={"username": email, "password": "Welcome@10"},
    )
    login = response.json()
    response = client.delete(
        f"/api/account/organization/updated_sample",
        headers={
            "Authorization": login["data"]["token_type"]
                             + " "
                             + login["data"]["access_token"]
        },
    )
    result = response.json()
    assert result["data"] is None
    assert result["message"] == "Organization deleted"


def test_get_model_testing_logs_accuracy():
    response = client.get(
        f"/api/user/test/accuracy",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()

    assert response["data"] is not None
    assert response["success"] is True
    assert response["error_code"] == 0


@mock.patch('kairon.shared.account.activity_log.UserActivityLogger.is_login_within_cooldown_period', autospec=True)
def test_delete_account(mock_password_reset):
    def _password_reset(*args, **kwargs):
        return

    mock_password_reset.return_value = _password_reset
    response_log = client.post(
        "/api/auth/login",
        data={"username": "integration@demo.ai", "password": "Welcome@10"},
    )
    actual = response_log.json()

    assert actual["success"]
    assert actual["error_code"] == 0
    pytest.access_token_delete = actual["data"]["access_token"]
    pytest.token_type_delete = actual["data"]["token_type"]
    response = client.delete(
        "/api/account/delete",
        headers={
            "Authorization": pytest.token_type_delete + " " + pytest.access_token_delete
        },
    ).json()

    assert response["success"]
    assert response["message"] == "Account deleted"
    assert response["error_code"] == 0


def test_delete_account_already_deleted():
    response = client.delete(
        "/api/account/delete",
        headers={
            "Authorization": pytest.token_type_delete + " " + pytest.access_token_delete
        },
    ).json()
    assert not response["success"]
    assert response["message"] == "User does not exist!"


def test_get_responses_post_passwd_reset(monkeypatch):
    email = "active_session@demo.ai"
    regsiter_response = client.post(
        "/api/account/registration",
        json={
            "email": email,
            "first_name": "Demo",
            "last_name": "User",
            "password": "Welcome@10",
            "confirm_password": "Welcome@10",
            "account": "integration",
            "bot": "integration",
        },
    )
    actual = regsiter_response.json()
    login_response = client.post(
        "/api/auth/login",
        data={"username": email, "password": "Welcome@10"},
    )
    login_actual = login_response.json()
    pytest.access_token = login_actual["data"]["access_token"]
    pytest.token_type = login_actual["data"]["token_type"]

    response = client.post(
        "/api/account/bot",
        json={"name": "covid-bot"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    response = response.json()
    assert response["data"]['bot_id']
    assert response['message'] == "Bot created"

    bot_response = client.get(
        "/api/account/bot",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()

    pytest.bot = bot_response["data"]["account_owned"][0]["_id"]
    token = Authentication.create_access_token(data={"mail_id": email})

    def get_token(*args, **kwargs):
        return token

    monkeypatch.setattr(Authentication, "create_access_token", get_token)
    monkeypatch.setattr(MailUtility, "trigger_smtp", mock_smtp)
    passwrd_change_response = client.post(
        "/api/account/password/change",
        json={
            "data": token,
            "password": "Welcome@21",
            "confirm_password": "Welcome@21",
        },
    )

    utter_response = client.get(
        f"/api/bot/{pytest.bot}/response/utter_greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = utter_response.json()
    message = actual["message"]
    error_code = actual['error_code']
    assert message == 'Session expired. Please login again!'
    assert error_code == 401


def test_create_access_token_with_iat():
    access_token = Authentication.create_access_token(
        data={"sub": "test@chat.com", "access-limit": ["/api/bot/.+/intent"]},
        token_type=TOKEN_TYPE.LOGIN.value,
    )
    payload = Utility.decode_limited_access_token(access_token)
    assert payload.get("iat") is not None


def test_overwrite_password_for_matching_passwords(monkeypatch):
    monkeypatch.setattr(MailUtility, "trigger_smtp", mock_smtp)
    response = client.post(
        "/api/account/password/change",
        json={
            "data": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJtYWlsX2lkIjoiaW50ZWcxQGdtYWlsLmNvbSJ9.Ycs1ROb1w6MMsx2WTA4vFu3-jRO8LsXKCQEB3fkoU20",
            "password": "Welcome@20",
            "confirm_password": "Welcome@20",
        },
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Success! Your password has been changed"
    assert actual["data"] is None


def test_login_new_password():
    response = client.post(
        "/api/auth/login",
        data={"username": "integ1@gmail.com", "password": "Welcome@20"},
    )
    actual = response.json()

    assert actual["success"]
    assert actual["error_code"] == 0
    pytest.access_token = actual["data"]["access_token"]
    pytest.token_type = actual["data"]["token_type"]


def test_login_old_password():
    response = client.post(
        "/api/auth/login",
        data={"username": "integ1@gmail.com", "password": "Welcome@10"},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 401
    assert actual["message"] == "Incorrect username or password"
    assert actual["data"] is None
    value = list(AuditLogData.objects(user="integ1@gmail.com", action='activity', entity='invalid_login').order_by(
        "-timestamp"))[
        0
    ]
    assert value["entity"] == "invalid_login"
    assert value["timestamp"]
    assert value["data"] == {'message': ['Incorrect username or password'], 'username': 'integ1@gmail.com'}


def test_get_responses_change_passwd_with_same_passwrd(monkeypatch):
    email = "samepasswrd@demo.ai"
    regsiter_response = client.post(
        "/api/account/registration",
        json={
            "email": email,
            "first_name": "Demo",
            "last_name": "User",
            "password": "Welcome@10",
            "confirm_password": "Welcome@10",
            "account": "samepasswrd",
            "bot": "samepasswrd",
        },
    )
    token = Authentication.create_access_token(data={"mail_id": email})

    def get_token(*args, **kwargs):
        return token

    monkeypatch.setattr(Authentication, "create_access_token", get_token)
    monkeypatch.setattr(MailUtility, "trigger_smtp", mock_smtp)
    Utility.environment["user"]["reset_password_cooldown_period"] = 0
    passwrd_change_response = client.post(
        "/api/account/password/change",
        json={"data": token, "password": "Welcome@10", "confirm_password": "Welcome@10"},
    )
    response = passwrd_change_response.json()
    message = response.get("message")
    assert message == "You have already used this password, try another!"


def test_get_responses_change_passwd_with_same_passwrd_rechange(monkeypatch):
    Utility.environment["user"]["reset_password_cooldown_period"] = 0
    email = "samepasswrd2@demo.ai"
    regsiter_response = client.post(
        "/api/account/registration",
        json={
            "email": email,
            "first_name": "Demo",
            "last_name": "User",
            "password": "Welcome@10",
            "confirm_password": "Welcome@10",
            "account": "samepasswrd2",
            "bot": "samepasswrd2",
        },
    )
    token = Authentication.create_access_token(data={"mail_id": email})

    def get_token(*args, **kwargs):
        return token

    monkeypatch.setattr(Authentication, "create_access_token", get_token)
    monkeypatch.setattr(MailUtility, "trigger_smtp", mock_smtp)
    passwrd_change_response = client.post(
        "/api/account/password/change",
        json={
            "data": token,
            "password": "Welcome@21",
            "confirm_password": "Welcome@21",
        },
    )
    passwrd_firstchange = passwrd_change_response.json()
    assert passwrd_firstchange["success"]
    assert passwrd_firstchange["error_code"] == 0
    assert passwrd_firstchange["message"] == "Success! Your password has been changed"
    assert passwrd_firstchange["data"] is None

    passwrd_rechange_response = client.post(
        "/api/account/password/change",
        json={
            "data": token,
            "password": "Welcome@21",
            "confirm_password": "Welcome@21",
        },
    )
    response = passwrd_rechange_response.json()
    message = response.get("message")
    assert message == "You have already used this password, try another!"


def test_idp_provider_fields_unauth():
    response = client.get(
        "/api/idp/provider/fields",
        headers={"Authorization": pytest.token_type + " worng_token"},
    ).json()

    assert response["error_code"] == 401


def test_allowed_origin_default():
    response = client.post(
        "/api/auth/login", data={"username": "test@demo.ai", "password": "Welcome@10"}
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert not actual["success"]
    assert actual["message"] == "User does not exist!"
    assert response.headers == {
        "content-length": "79",
        "content-type": "application/json",
        "server": "Secure",
        "strict-transport-security": "includeSubDomains; preload; max-age=31536000",
        "x-frame-options": "SAMEORIGIN",
        "x-xss-protection": "0",
        "x-content-type-options": "nosniff",
        "content-security-policy": "default-src 'self'; frame-ancestors 'self'; form-action 'self'; base-uri 'self'; connect-src 'self'; frame-src 'self'; style-src 'self' https: 'unsafe-inline'; img-src 'self' https:; script-src 'self' https: 'unsafe-inline'",
        "referrer-policy": "no-referrer",
        "cache-control": "must-revalidate",
        "permissions-policy": "accelerometer=(), autoplay=(), camera=(), document-domain=(), encrypted-media=(), fullscreen=(), vibrate=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), midi=(), payment=(), picture-in-picture=(), sync-xhr=(), usb=()",
        "cross-origin-embedder-policy": "require-corp",
        "cross-origin-opener-policy": "same-origin",
        "cross-origin-resource-policy": "same-origin",
        "access-control-allow-origin": "*",
    }


def test_allowed_origin(monkeypatch):
    monkeypatch.setitem(Utility.environment["cors"], "origin", "http://digite.com")

    response = client.post(
        "/api/auth/login",
        data={"username": "test@demo.ai", "password": "Welcome@10"},
        headers={"origin": "http://digite.com"},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert not actual["success"]
    assert actual["message"] == "User does not exist!"
    assert response.headers == {
        "content-length": "79",
        "content-type": "application/json",
        "server": "Secure",
        "strict-transport-security": "includeSubDomains; preload; max-age=31536000",
        "x-frame-options": "SAMEORIGIN",
        "x-xss-protection": "0",
        "x-content-type-options": "nosniff",
        "content-security-policy": "default-src 'self'; frame-ancestors 'self'; form-action 'self'; base-uri 'self'; connect-src 'self'; frame-src 'self'; style-src 'self' https: 'unsafe-inline'; img-src 'self' https:; script-src 'self' https: 'unsafe-inline'",
        "referrer-policy": "no-referrer",
        "cache-control": "must-revalidate",
        "permissions-policy": "accelerometer=(), autoplay=(), camera=(), document-domain=(), encrypted-media=(), fullscreen=(), vibrate=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), midi=(), payment=(), picture-in-picture=(), sync-xhr=(), usb=()",
        "cross-origin-embedder-policy": "require-corp",
        "cross-origin-opener-policy": "same-origin",
        "cross-origin-resource-policy": "same-origin",
        "access-control-allow-origin": "http://digite.com",
        "access-control-allow-credentials": "true",
        "access-control-expose-headers": "content-disposition",
    }


def test_get_client_ip():
    headers = {"X-Forwarded-For": "10.0.0.1"}
    response = client.post(
        "/api/auth/login",
        data={"username": "test@demo.ai", "password": "Welcome@10"},
        headers=headers,
    )
    assert Utility.get_client_ip(response.request) == "10.0.0.1"

    headers = {"X-Forwarded-For": "10.0.0.2, 10.0.1.1"}
    response = client.post(
        "/api/auth/login",
        data={"username": "test@demo.ai", "password": "Welcome@10"},
        headers=headers,
    )
    assert Utility.get_client_ip(response.request) == "10.0.0.2, 10.0.1.1"

    headers = {"X-Real-IP": "10.0.0.3"}
    response = client.post(
        "/api/auth/login",
        data={"username": "test@demo.ai", "password": "Welcome@10"},
        headers=headers,
    )
    assert Utility.get_client_ip(response.request) == "10.0.0.3"


def test_allow_only_sso_login(monkeypatch):
    user = "test@demo.in"
    organization = "new_test"
    feature_type = FeatureMappings.ONLY_SSO_LOGIN.value
    value = True
    OrgProcessor.upsert_user_org_mapping(
        user=user, org=organization, feature=feature_type, value=value
    )

    response = client.post(
        "/api/auth/login",
        data={"username": user, "password": "Welcome@10"},
    )
    actual = response.json()
    assert (
            actual["message"]
            == "Login with your org SSO url, Login with username/password not allowed"
    )


def test_idp_callback(monkeypatch):
    def _validate_org_settings(*args, **kwargs):
        return

    def _get_idp_token(*args, **kwargs):
        return {
            "email": "new_idp_user@demo.in",
            "given_name": "test",
            "family_name": "user",
        }

    monkeypatch.setattr(IDPProcessor, "get_idp_token", _get_idp_token)
    monkeypatch.setattr(OrgProcessor, "validate_org_settings", _validate_org_settings)

    realm_name = "test"
    response = client.get(
        f"/api/auth/login/idp/callback/{realm_name}?session_state=asikndhfnnin-jinsdn-sdnknsdn&code=kjaskjkajb-wkejhwejwe",
    )
    result = response.json()
    assert result["data"]["access_token"] is not None
    assert result["data"]["token_type"] == "bearer"
    assert result["message"] == "User Authenticated"


def test_api_login_with_SSO_only_flag():
    user = "idp_user@demo.in"
    organization = "new_test"
    feature_type = FeatureMappings.ONLY_SSO_LOGIN.value
    value = True
    OrgProcessor.upsert_user_org_mapping(
        user=user, org=organization, feature=feature_type, value=value
    )

    email = "idp_user@demo.in"
    response = client.post(
        "/api/auth/login",
        data={"username": email, "password": "Welcome@10"},
    )
    actual = response.json()
    assert (
            actual["message"]
            == "Login with your org SSO url, Login with username/password not allowed"
    )
    assert actual["error_code"] == 422
    assert actual["success"] == False


def test_list_system_metadata():
    response = client.get(url=f"/api/system/metadata", allow_redirects=False)
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["success"]
    assert len(actual["data"]) == 17
