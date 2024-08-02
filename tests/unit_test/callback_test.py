import asyncio
import os

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fernet import Fernet
from mongoengine import connect
from kairon import Utility

os.environ["system_file"] = "./tests/testing_data/system.yaml"
Utility.load_environment()

from kairon.chat.handlers.channels.whatsapp import Whatsapp
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


from kairon.async_callback.channel_message_dispacher import ChannelMessageDispatcher
from kairon.shared.constants import ChannelTypes


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

@pytest.mark.asyncio
async def test_handle_whatsapp():
    config = MagicMock()
    with patch('kairon.chat.handlers.channels.whatsapp.Whatsapp.send_message_to_user', new_callable=AsyncMock) as mock_send_message:
        await ChannelMessageDispatcher.handle_whatsapp('bot', config, 'sender', 'message')
        mock_send_message.assert_called_once_with('message', 'sender')


@pytest.mark.asyncio
async def test_handle_telegram_text_message():
    config = {'access_token': 'dummy_token'}
    with patch('kairon.chat.handlers.channels.telegram.TelegramOutput.send_text_message', new_callable=AsyncMock) as mock_send_message:
        await ChannelMessageDispatcher.handle_telegram('bot', config, 'sender', 'text message')
        mock_send_message.assert_called_once_with('sender', 'text message')

@pytest.mark.asyncio
async def test_handle_telegram_custom_json():
    config = {'access_token': 'dummy_token'}
    with patch('kairon.chat.handlers.channels.telegram.TelegramOutput.send_custom_json', new_callable=AsyncMock) as mock_send_custom_json:
        await ChannelMessageDispatcher.handle_telegram('bot', config, 'sender', {'key': 'value'})
        mock_send_custom_json.assert_called_once_with('sender', {'key': 'value'})

@pytest.mark.asyncio
async def test_handle_facebook_text_message():
    config = {'page_access_token': 'dummy_token'}
    with patch('kairon.chat.handlers.channels.messenger.MessengerBot.send_text_message', new_callable=AsyncMock) as mock_send_message:
        await ChannelMessageDispatcher.handle_facebook('bot', config, 'sender', 'text message')
        mock_send_message.assert_called_once_with('sender', 'text message')

@pytest.mark.asyncio
async def test_handle_instagram_text_message():
    config = {'page_access_token': 'dummy_token'}
    with patch('kairon.chat.handlers.channels.messenger.MessengerBot.send_text_message', new_callable=AsyncMock) as mock_send_message:
        await ChannelMessageDispatcher.handle_instagram('bot', config, 'sender', 'text message')
        mock_send_message.assert_called_once_with('sender', 'text message')

@pytest.mark.asyncio
async def test_handle_default():
    with patch('uuid6.uuid7') as mock_uuid, patch('time.time') as mock_time, patch('kairon.shared.chat.broadcast.processor.MessageBroadcastProcessor.get_db_client', new_callable=MagicMock) as mock_db_client:
        mock_uuid.return_value.hex = 'mock_uuid'
        mock_time.return_value = 1234567890
        mock_collection = MagicMock()
        mock_db_client.return_value = mock_collection

        await ChannelMessageDispatcher.handle_default('bot', None, 'sender', 'message')
        mock_collection.insert_one.assert_called_once()


@pytest.mark.asyncio
async def test_dispatch_message_unknown_channel():
    bot = 'bot'
    sender = 'sender'
    message = 'message'
    channel = 'unknown_channel'

    with patch('kairon.shared.chat.processor.ChatDataProcessor.get_channel_config', return_value={'config': {}}), \
         patch('kairon.shared.chat.broadcast.processor.MessageBroadcastProcessor.get_db_client') as mock_db_client, \
         patch('uuid6.uuid7') as mock_uuid, patch('time.time') as mock_time:

        mock_uuid.return_value.hex = 'mock_uuid'
        mock_time.return_value = 1234567890
        mock_collection = MagicMock()
        mock_db_client.return_value = mock_collection

        await ChannelMessageDispatcher.dispatch_message(bot, sender, message, channel)

        mock_collection.insert_one.assert_called_once()


@pytest.mark.asyncio
@patch('kairon.chat.handlers.channels.clients.whatsapp.cloud.WhatsappCloud.send')
async def test_send_message_to_user(mock_send):
    whatsapp = Whatsapp({'bsp_type': 'meta', 'phone_number_id': '1234'})
    message = 'Hello, World!'
    recipient_id = 'user1'
    await whatsapp.send_message_to_user(message, recipient_id)
    mock_send.assert_called_once_with('Hello, World!', 'user1', 'text')
