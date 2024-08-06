import os

import pytest
from unittest.mock import patch, MagicMock
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
    CallbackConfig,
    CallbackData,
    CallbackRecordStatusType,
    CallbackLog,
)
from uuid6 import uuid7


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
        "channel": "channel",
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
        "channel": "channel",
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
@patch('kairon.async_callback.channel_message_dispacher.ChannelMessageDispatcher.handle_whatsapp')
@patch('kairon.async_callback.channel_message_dispacher.ChannelMessageDispatcher.handle_telegram')
@patch('kairon.async_callback.channel_message_dispacher.ChannelMessageDispatcher.handle_facebook')
@patch('kairon.async_callback.channel_message_dispacher.ChannelMessageDispatcher.handle_instagram')
@patch('kairon.async_callback.channel_message_dispacher.ChannelMessageDispatcher.handle_default')
@patch('kairon.async_callback.channel_message_dispacher.ChatDataProcessor.get_channel_config')
@patch('kairon.async_callback.channel_message_dispacher.MessageBroadcastProcessor.get_db_client')
async def test_dispatch_message_channel(mock_get_db_client, mock_get_channel_config, mock_handle_default, mock_handle_instagram, mock_handle_facebook, mock_handle_telegram, mock_handle_whatsapp):
    # Arrange
    bot = 'Test bot'
    sender = 'Test sender'
    message = 'Test message'
    channel = 'whatsapp'
    mock_get_channel_config.return_value = {'config': 'Test config'}
    mock_db_collection = MagicMock()
    mock_get_db_client.return_value = mock_db_collection

    # Act
    await ChannelMessageDispatcher.dispatch_message(bot, sender, message, channel)

    # Assert
    mock_handle_whatsapp.assert_called_once_with(bot, mock_get_channel_config.return_value['config'], sender, message)
    mock_get_db_client.assert_called_once_with(bot)
    mock_db_collection.insert_one.assert_called_once()

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
    message = {'type': 'image', 'url': 'http://example.com/image.jpg'}
    await whatsapp.send_message_to_user(message, recipient_id)
    mock_send.assert_called_with({'type': 'image', 'url': 'http://example.com/image.jpg'}, 'user1', 'image')
    message = {'type': 'video', 'url': 'http://example.com/video.mp4'}
    await whatsapp.send_message_to_user(message, recipient_id)
    mock_send.assert_called_with({'type': 'video', 'url': 'http://example.com/video.mp4'}, 'user1', 'video')


from kairon.async_callback.processor import CallbackProcessor

@patch('kairon.async_callback.processor.CloudUtility')
@patch('kairon.async_callback.processor.Utility')
def test_run_pyscript(mock_utility, mock_cloud_utility):
    # Arrange
    mock_utility.environment = {'async_callback_action': {'pyscript': {'trigger_task': True}}}
    mock_cloud_utility.trigger_lambda.return_value = {
        'Payload': {
            'body': {
                'bot_response': 'Test response'
            }
        }
    }
    mock_cloud_utility.lambda_execution_failed.return_value = False
    script = 'print("Hello, World!")'
    predefined_objects = {'key': 'value'}

    result = CallbackProcessor.run_pyscript(script, predefined_objects)

    mock_cloud_utility.trigger_lambda.assert_called_once_with('pyscript_evaluator', {
        'script': script,
        'predefined_objects': predefined_objects
    })
    mock_cloud_utility.lambda_execution_failed.assert_called_once_with(mock_cloud_utility.trigger_lambda.return_value)
    assert result == 'Test response'


import asyncio

from unittest.mock import AsyncMock, MagicMock, patch
from concurrent.futures import ThreadPoolExecutor

@pytest.fixture
def mock_callback():
    return AsyncMock()

@pytest.fixture
def mock_predefined_objects():
    return {"key": "value"}

@pytest.fixture
def mock_script():
    return "print('Hello, World!')"

@pytest.fixture
def mock_executor():
    with patch('kairon.async_callback.processor.async_task_executor', ThreadPoolExecutor(max_workers=1)) as mock_exec:
        yield mock_exec

@pytest.mark.asyncio
async def test_run_pyscript_async_success(mock_script, mock_predefined_objects, mock_callback, mock_executor):
    with patch('kairon.async_callback.processor.CallbackProcessor.run_pyscript', return_value="execution_result"):
        CallbackProcessor.run_pyscript_async(mock_script, mock_predefined_objects, mock_callback)
        await asyncio.sleep(0.1)  # Give time for the async task to complete

        mock_callback.assert_called_once_with({'result': 'execution_result'})

@pytest.mark.asyncio
async def test_run_pyscript_async_exception(mock_script, mock_predefined_objects, mock_callback, mock_executor):
    with patch('kairon.async_callback.processor.CallbackProcessor.run_pyscript', side_effect=AppException("execution_error")):
        CallbackProcessor.run_pyscript_async(mock_script, mock_predefined_objects, mock_callback)
        await asyncio.sleep(0.1)  # Give time for the async task to complete

        mock_callback.assert_called_once_with({'error': 'execution_error'})

@pytest.mark.asyncio
async def test_run_pyscript_async_submit_exception(mock_script, mock_predefined_objects, mock_callback, mock_executor):
    with patch('kairon.async_callback.processor.async_task_executor.submit', side_effect=AppException("submission_error")):
        with pytest.raises(AppException, match="Error while executing pyscript: submission_error"):
            CallbackProcessor.run_pyscript_async(mock_script, mock_predefined_objects, mock_callback)


@pytest.mark.asyncio
@patch('kairon.async_callback.processor.ChannelMessageDispatcher.dispatch_message')
@patch('kairon.async_callback.processor.CallbackLog.create_success_entry')
@patch('kairon.async_callback.processor.CallbackLog.create_failure_entry')
async def test_async_callback(mock_failure_entry, mock_success_entry, mock_dispatch_message):
    # Arrange
    obj = {'result': 'Test result'}
    ent = {'action_name': 'Test action', 'identifier': 'Test identifier', 'pyscript_code': 'Test code', 'sender_id': 'Test sender', 'metadata': 'Test metadata', 'callback_url': 'Test url', 'callback_source': 'Test source'}
    cb = {'pyscript_code': 'Test code'}
    c_src = 'Test source'
    bot_id = 'Test bot'
    sid = 'Test sender'
    chnl = 'Test channel'
    rd = {'key': 'value'}

    await CallbackProcessor.async_callback(obj, ent, cb, c_src, bot_id, sid, chnl, rd)

    mock_dispatch_message.assert_called_once_with(bot_id, sid, obj['result'], chnl)
    mock_success_entry.assert_called_once_with(name=ent['action_name'], bot=bot_id,
                                               channel=chnl,
                                               identifier=ent['identifier'],
                                               pyscript_code=cb['pyscript_code'], sender_id=sid, log=obj['result'], request_data=rd, metadata=ent['metadata'], callback_url=ent['callback_url'], callback_source=c_src)
    mock_failure_entry.assert_not_called()

@pytest.mark.asyncio
@patch('kairon.async_callback.processor.ChannelMessageDispatcher.dispatch_message')
@patch('kairon.async_callback.processor.CallbackLog.create_success_entry')
@patch('kairon.async_callback.processor.CallbackLog.create_failure_entry')
async def test_async_callback_fail(mock_failure_entry, mock_success_entry, mock_dispatch_message):
    obj = {'error': 'Test error'}
    ent = {'action_name': 'Test action', 'identifier': 'Test identifier', 'pyscript_code': 'Test code', 'sender_id': 'Test sender', 'metadata': 'Test metadata', 'callback_url': 'Test url', 'callback_source': 'Test source'}
    cb = {'pyscript_code': 'Test code'}
    c_src = 'Test source'
    bot_id = 'Test bot'
    sid = 'Test sender'
    chnl = 'Test channel'
    rd = {'key': 'value'}

    await CallbackProcessor.async_callback(obj, ent, cb, c_src, bot_id, sid, chnl, rd)

    mock_dispatch_message.assert_not_called()
    mock_success_entry.assert_not_called()
    mock_failure_entry.assert_called_once_with(name=ent['action_name'], bot=bot_id, identifier=ent['identifier'],
                                               channel=chnl,
                                               pyscript_code=cb['pyscript_code'], sender_id=sid, error_log=obj['error'], request_data=rd, metadata=ent['metadata'], callback_url=ent['callback_url'], callback_source=c_src)




