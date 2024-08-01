import os

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fernet import Fernet
from mongoengine import connect

from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.callback.data_objects import (
    check_nonempty_string,
    encrypt_secret,
    decrypt_secret,
    CallbackExecutionMode,
    CallbackConfig,
    CallbackData,
    CallbackRecordStatusType,
    CallbackLog,
)
from uuid6 import uuid7
from datetime import datetime


# Mock utility environment
@pytest.fixture(autouse=True)
def mock_environment(monkeypatch):
    os.environ["system_file"] = "./tests/testing_data/system.yaml"
    Utility.load_environment()
    connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))
    callback_data_1 = {"action_name": "callback_action1", "callback_name": "callback_script2",
                       "bot": "6697add6b8e47524eb983373", "sender_id": "5489844732", "channel": "telegram",
                       "metadata": {"happy": "i am happy : )"}, "identifier": "019107c7570577a6b0f279b4038c4a8f",
                       "callback_url": "http://localhost:5059/callback/6697add6b8e47524eb983373/callback_action1/019107c7570577a6b0f279b4038c4a8f?token=gAAAAABmqK71xDb4apnxOAfJjDUv1lrCTooWNX0GPyBHhqW1KBlblUqGNPwsX1V7FlIlgpwWGRWljiYp9mYAf1eG4AcG1dTXQuZCndCewox-CLU5_s7f-uMyncxWyaPV0i0oLE9skkZA",
                       "execution_mode": "sync"}
    callback_data_2 = {"action_name": "callback_action2", "callback_name": "callback_script3",
                       "bot": "6697add6b8e47524eb983373", "sender_id": "5489844732", "channel": "telegram",
                       "metadata": {"happy": "i am happy : )"}, "identifier": "019107c7570577a6b0f279b4038c4a8a",
                       "callback_url": "http://localhost:5059/callback/6697add6b8e47524eb983373/callback_action1/019107c7570577a6b0f279b4038c4a8f?token=gAAAAABmqK71xDb4apnxOAfJjDUv1lrCTooWNX0GPyBHhqW1KBlblUqGNPwsX1V7FlIlgpwWGRWljiYp9mYAf1eG4AcG1dTXQuZCndCewox-CLU5_s7f-uMyncxWyaPV0i0oLE9skkZA",
                       "execution_mode": "sync"}
    callback_config_1 = {"name": "callback_script2",
                         "pyscript_code": "bot_response = f\"{req['dynamic_param']} {metadata['happy']}\"",
                         "validation_secret": "gAAAAABmqK71xDb4apnxOAfJjDUv1lrCTooWNX0GPyBHhqW1KBlblUqGNPwsX1V7FlIlgpwWGRWljiYp9mYAf1eG4AcG1dTXQuZCndCewox-CLU5_s7f-uMyncxWyaPV0i0oLE9skkZA",
                         "execution_mode": "sync", "bot": "6697add6b8e47524eb983373"}
    callback_config_2 = {"name": "callback_script3",
                         "pyscript_code": "bot_response = f\"{req['dynamic_param']} {metadata['happy']}\"",
                         "validation_secret": "gAAAAABmqK71xDb4apnxOAfJjDUv1lrCTooWNX0GPyBHhqW1KBlblUqGNPwsX1V7FlIlgpwWGRWljiYp9mYAf1eG4AcG1dTXQuZCndCewox-CLU5_s7f-uMyncxWyaPV0i0oLE9skkZA",
                         "execution_mode": "async", "bot": "6697add6b8e47524eb983373"}

    CallbackData.objects.insert(CallbackData(**callback_data_1))
    CallbackConfig.objects.insert(CallbackConfig(**callback_config_1))
    CallbackData.objects.insert(CallbackData(**callback_data_2))
    CallbackConfig.objects.insert(CallbackConfig(**callback_config_2))


def test_check_nonempty_string():
    with pytest.raises(AppException):
        check_nonempty_string("")
    with pytest.raises(AppException):
        check_nonempty_string(None)
    check_nonempty_string("valid_string")


def test_encrypt_decrypt_secret():
    secret = "my_secret"
    encrypted = encrypt_secret(secret)
    decrypted = decrypt_secret(encrypted)
    assert secret == decrypted


@patch("kairon.shared.callback.data_objects.CallbackConfig.save", MagicMock())
def test_create_callback_config():
    data = {
        "bot": "test_bot",
        "name": "test_name",
        "pyscript_code": "print('Hello, World!')",
        "validation_secret": "secret"
    }
    result = CallbackConfig.create_entry(**data)
    assert result["name"] == data["name"]
    assert result["bot"] == data["bot"]
    assert result["pyscript_code"] == data["pyscript_code"]


@patch("kairon.shared.callback.data_objects.CallbackConfig.objects")
def test_get_callback_config(mock_objects):
    mock_entry = MagicMock()
    mock_entry.to_mongo.return_value.to_dict.return_value = {
        "name": "test_name",
        "bot": "test_bot",
        "_id": "myid"
    }
    mock_objects.return_value.first.return_value = mock_entry

    result = CallbackConfig.get_entry("test_bot", "test_name")
    assert result["name"] == "test_name"
    assert result["bot"] == "test_bot"


@patch("kairon.shared.callback.data_objects.CallbackConfig.objects")
def test_get_callback_config_not_found(mock_objects):
    mock_objects.return_value.first.return_value = None
    with pytest.raises(AppException):
        CallbackConfig.get_entry("test_bot", "test_name")


@patch("kairon.shared.callback.data_objects.CallbackData.save", MagicMock())
@patch("kairon.shared.callback.data_objects.CallbackConfig.get_auth_token", MagicMock(return_value="auth_token"))
def test_create_callback_data():
    data = {
        "name": "test_action",
        "callback_config_name": "test_callback",
        "bot": "test_bot",
        "sender_id": "sender_123",
        "channel": "test_channel",
        "metadata": {}
    }
    url = CallbackData.create_entry(**data)
    assert "/callback/test_bot/test_action/" in url
    assert "?token=auth_token" in url


@patch("kairon.shared.callback.data_objects.CallbackLog.save", MagicMock())
def test_create_callback_log_success():
    data = {
        "name": "test_action",
        "bot": "test_bot",
        "identifier": uuid7().hex,
        "pyscript_code": "print('Hello, World!')",
        "sender_id": "sender_123",
        "log": "log data",
        "request_data": {},
        "metadata": {},
        "callback_url": "http://example.com",
        "callback_source": "source"
    }
    result = CallbackLog.create_success_entry(**data)
    assert result["callback_name"] == data["name"]
    assert result["status"] == CallbackRecordStatusType.SUCCESS.value


@patch("kairon.shared.callback.data_objects.CallbackLog.save", MagicMock())
def test_create_callback_log_failure():
    data = {
        "name": "test_action",
        "bot": "test_bot",
        "identifier": uuid7().hex,
        "pyscript_code": "print('Hello, World!')",
        "sender_id": "sender_123",
        "error_log": "error log data",
        "request_data": {},
        "metadata": {},
        "callback_url": "http://example.com",
        "callback_source": "source"
    }
    result = CallbackLog.create_failure_entry(**data)
    assert result["callback_name"] == data["name"]
    assert result["status"] == CallbackRecordStatusType.FAILED.value


def test_validate_callback_data():
    # Test case where all parameters are valid
    with patch("kairon.Utility.is_exist", return_value=True):
        result = CallbackData.validate_entry("6697add6b8e47524eb983373", "callback_action1", "019107c7570577a6b0f279b4038c4a8f", "gAAAAABmqK71xDb4apnxOAfJjDUv1lrCTooWNX0GPyBHhqW1KBlblUqGNPwsX1V7FlIlgpwWGRWljiYp9mYAf1eG4AcG1dTXQuZCndCewox")
        assert result["identifier"] == "019107c7570577a6b0f279b4038c4a8f", "Expected identifier to be 'new_identifier'"

    # Test case where action_name does not match
    with pytest.raises(AppException, match="Invalid identifier!"):
        CallbackData.validate_entry("6697add6b8e47524eb983373", "callback_action1ad", "019107c7570577a6b0f279b4038c4a8f", "gAAAAABmqK71xDb4apnxOAfJjDUv1lrCTooWNX0GPyBHhqW1KBlblUqGNPwsX1V7FlIlgpwWGRWljiYp9mYAf1eG4AcG1dTXQuZCndCewox")

    # Test case where validation_secret is invalid
    with patch("kairon.Utility.is_exist", return_value=False):
        with pytest.raises(AppException, match="Invalid validation secret!"):
            CallbackData.validate_entry("6697add6b8e47524eb983373", "callback_action1", "019107c7570577a6b0f279b4038c4a8f", "wrong_secret")

@patch("kairon.shared.callback.data_objects.CallbackData.objects")
def test_validate_callback_data_invalid(mock_objects):
    mock_objects.return_value.first.return_value = None
    with pytest.raises(AppException):
        CallbackData.validate_entry("6697add6b8e47524eb983373", "test_name", "identifier", "valid_secret")
