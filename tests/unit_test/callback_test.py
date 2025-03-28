import json
import os
from datetime import time

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
    xor_encrypt_secret,
    xor_decrypt_secret,
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
                       "callback_url": "http://localhost:5059/callback/d/01916946f81c7eba899dd82b45350784/VQEBBAcPVwVeD18HB1IBUVNeVVsLUgBUBABZV1JSBFM=",
                       "execution_mode": "sync"}
    callback_data_2 = {"action_name": "callback_action2", "callback_name": "callback_script3",
                       "bot": "6697add6b8e47524eb983373", "sender_id": "5489844732", "channel": "telegram",
                       "metadata": {"happy": "i am happy : )"}, "identifier": "019107c7570577a6b0f279b4038c4a8a",
                       "callback_url": "http://localhost:5059/callback/d/01916946f81c7eba899dd82b45350784/VQEBBAcPVwVeD18HB1IBUVNeVVsLUgBUBABZV1JSBFM=",
                       "execution_mode": "sync"}
    callback_config_1 = {"name": "callback_script2",
                         "pyscript_code": "bot_response = f\"{req['dynamic_param']} {metadata['happy']}\"",
                         "validation_secret": encrypt_secret("0191695805617deabc2ba8ea5ee774da"),
                         "execution_mode": "sync", "bot": "6697add6b8e47524eb983373"}
    callback_config_2 = {"name": "callback_script3",
                         "pyscript_code": "bot_response = f\"{req['dynamic_param']} {metadata['happy']}\"",
                         "validation_secret": encrypt_secret("0191695805617deabc2ba8ea5ee774da"),
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


def test_encrypt_secret():
    secret = "my_secret"
    encrypted = encrypt_secret(secret)
    decrypted_secret = decrypt_secret(encrypted)
    assert len(encrypted) == 100
    assert decrypted_secret == secret

def test_xor_encrypt_secret():
    secret = "my_secret"
    encrypted = xor_encrypt_secret(secret)
    decrypted_secret = xor_decrypt_secret(encrypted)
    assert decrypted_secret == secret

@patch("kairon.shared.callback.data_objects.CallbackConfig.save", MagicMock())
def test_create_callback_config():
    data = {
        "bot": "test_bot",
        "name": "test_name",
        "pyscript_code": "print('Hello, World!')",
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
@patch("kairon.shared.callback.data_objects.CallbackConfig.get_auth_token", MagicMock(return_value=("auth_token", False)))
def test_create_callback_data():
    data = {
        "name": "test_action",
        "callback_config_name": "test_callback",
        "bot": "test_bot",
        "sender_id": "sender_123",
        "channel": "test_channel",
        "metadata": {}
    }
    url, identifier, is_standalone = CallbackData.create_entry(**data)
    assert "/callback/d" in url
    assert "/auth_token" in url


def test_get_value_from_json():
    json_obj = {"key1": {"key2": "value"}}
    path = "key1.key2"
    assert CallbackData.get_value_from_json(json_obj, path) == "value"

    json_obj = {"key1": {"key2": {
        "apple": 'my apple',
        "banana": 'my banana',
    }}}
    path = "key1.key2.banana"
    assert CallbackData.get_value_from_json(json_obj, path) == "my banana"

    json_obj = {"key1": {"key2": ["value0", "value1", "value2"]}}
    path = "key1.key2.1"
    assert CallbackData.get_value_from_json(json_obj, path) == "value1"

    json_obj = {"key1": {"key2": {"key3": "value"}}}
    path = "key1.key2.key4"
    with pytest.raises(AppException, match="Cannot find identifier at path 'key1.key2.key4' in request data!"):
        CallbackData.get_value_from_json(json_obj, path)

    json_obj = "invalid_json"
    path = "key1.key2.key3"
    with pytest.raises(AppException):
        CallbackData.get_value_from_json(json_obj, path)




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



def test_validate_entry():
    # Arrange
    mock_token = "mock_token"
    mock_identifier = "mock_identifier"
    mock_request_body = {"key": "value"}

    with patch('kairon.shared.callback.data_objects.check_nonempty_string'), \
         patch.object(CallbackConfig, 'verify_auth_token') as mock_verify_auth_token, \
         patch.object(CallbackData, 'get_value_from_json') as mock_get_value_from_json, \
         patch('kairon.shared.callback.data_objects.CallbackData.objects') as mock_objects, \
         patch('kairon.shared.callback.data_objects.time.time') as mock_time:

        mock_config_entry = MagicMock()
        mock_config_entry.standalone = False
        mock_config_entry.expire_in = 0
        mock_config_entry.bot = "mock_bot"
        mock_config_entry.to_mongo().to_dict.return_value = {"config": "entry"}

        mock_record = MagicMock()
        mock_record.is_valid = True
        mock_record.timestamp = 0
        mock_mongo = MagicMock()
        mock_mongo.to_dict.return_value = {"record": "entry"}
        mock_record.to_mongo.return_value = mock_mongo

        mock_verify_auth_token.return_value = mock_config_entry
        mock_get_value_from_json.return_value = mock_identifier
        mock_objects.first.return_value = mock_record
        mock_time.return_value = 0

        # Act
        result = CallbackData.validate_entry(mock_token, mock_identifier, mock_request_body)

        # Assert
        assert result[1] == {"config": "entry"}


@patch("kairon.shared.callback.data_objects.CallbackConfig.verify_auth_token")
def test_validate_callback_data(mock_verify_auth_token):
    # Create a mock config_entry object
    mock_config_entry = MagicMock()
    mock_config_entry.standalone = False
    mock_config_entry.expire_in = 0
    mock_config_entry.bot = "6697add6b8e47524eb983373"
    mock_config_entry.to_mongo().to_dict.return_value = {"config": "entry"}

    mock_verify_auth_token.return_value = mock_config_entry

    with patch("kairon.Utility.is_exist", return_value=True):
        result = CallbackData.validate_entry("VQEBBAcPVwVeD18HB1IBUVNeVVsLUgBUBABZV1JSBFM=", "019107c7570577a6b0f279b4038c4a8f", {})
        print(result)
        assert result == ({'action_name': 'callback_action1', 'callback_name': 'callback_script2', 'bot': '6697add6b8e47524eb983373', 'sender_id': '5489844732', 'channel': 'telegram', 'metadata': {'happy': 'i am happy : )'}, 'identifier': '019107c7570577a6b0f279b4038c4a8f', 'callback_url': 'http://localhost:5059/callback/d/01916946f81c7eba899dd82b45350784/VQEBBAcPVwVeD18HB1IBUVNeVVsLUgBUBABZV1JSBFM=', 'execution_mode': 'sync', 'state': 0, 'is_valid': True}, {'config': 'entry'})

        mock_verify_auth_token.assert_called_once_with("VQEBBAcPVwVeD18HB1IBUVNeVVsLUgBUBABZV1JSBFM=")


@patch("kairon.shared.callback.data_objects.CallbackData.objects")
def test_validate_callback_data_invalid(mock_objects):
    mock_objects.return_value.first.return_value = None
    with pytest.raises(AppException):
        CallbackData.validate_entry("VQEBBAcPVwVeD18HB1IBUVNeVVsLUgBUBABZV1JSBFM=", "test_name", {})

@pytest.mark.asyncio
async def test_handle_whatsapp():
    config = MagicMock()
    with patch('kairon.chat.handlers.channels.whatsapp.Whatsapp.send_message_to_user', new_callable=AsyncMock) as mock_send_message:
        await ChannelMessageDispatcher.handle_whatsapp('bot', config, 'sender', 'message')
        mock_send_message.assert_called_once_with('message', 'sender')


@pytest.mark.asyncio
async def test_handle_telegram_text_message():
    config = {'access_token': '270485614:AAHfiqksKZ8WmR2zSjiQ7_v4TMAKdiHm9T0'}
    with patch('kairon.chat.handlers.channels.telegram.TelegramOutput.send_text_message', new_callable=AsyncMock) as mock_send_message:
        await ChannelMessageDispatcher.handle_telegram('bot', config, 'sender', 'text message')
        mock_send_message.assert_called_once_with('sender', 'text message')

@pytest.mark.asyncio
async def test_handle_telegram_custom_json():
    config = {'access_token': '270485614:AAHfiqksKZ8WmR2zSjiQ7_v4TMAKdiHm9T0'}
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
    bot = 'Test bot'
    sender = 'Test sender'
    message = 'Test message'
    channel = 'whatsapp'
    mock_get_channel_config.return_value = {'config': 'Test config'}
    mock_db_collection = MagicMock()
    mock_get_db_client.return_value = mock_db_collection

    await ChannelMessageDispatcher.dispatch_message(bot, sender, message, channel)

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
    mock_send.assert_called_once_with({'body': 'Hello, World!', 'preview_url': True}, 'user1', 'text')
    message = {
        "data": [
            {
                "type": "button",
                "value": "/greet",
                "id": "btn_end",
                "children": [{"text": "hello world"}],
            }
        ],
        "type": "button",
    }
    await whatsapp.send_message_to_user(message, recipient_id)
    mock_send.assert_called_with({'type': 'button', 'body': {'text': 'Please select from quick buttons:'},
                                  'action': {'buttons': [{'type': 'reply', 'reply': {'id': '/greet', 'title':
                                      'hello world'}}]}}, 'user1', 'interactive')


from kairon.async_callback.processor import CallbackProcessor


@patch('kairon.async_callback.processor.CallbackUtility')
@patch('kairon.async_callback.processor.Utility')
def test_run_pyscript(mock_utility, mock_callback_utility):
    mock_utility.environment = {'async_callback_action': {'pyscript': {'trigger_task': False}}}
    resp = {
        "statusCode": 200,
        "statusDescription": "200 OK",
        "isBase64Encoded": False,
        "headers": {
            "Content-Type": "text/html; charset=utf-8"
        },
        "body": {'bot_response': 'Test response'}
    }
    mock_callback_utility.pyscript_handler.return_value = resp
    script = 'print("Hello, World!")'
    predefined_objects = {'bot_response': 'Test response'}

    result = CallbackProcessor.run_pyscript(script, predefined_objects)
    assert result == {'bot_response': 'Test response'}

@patch('kairon.async_callback.processor.CloudUtility.lambda_execution_failed')
@patch('kairon.async_callback.processor.CloudUtility.trigger_lambda')
@patch('kairon.async_callback.processor.Utility')
def test_run_pyscript_with_lambda(mock_utility, mock_trigger_lambda, mock_lambda_execution_failed):
    mock_utility.environment = {'async_callback_action': {'pyscript': {'trigger_task': True}}}

    lambda_response = {
        "Payload": {
            "body": {'bot_response': 'Lambda test response'},
            "errorMessage": None
        }
    }
    mock_trigger_lambda.return_value = lambda_response
    mock_lambda_execution_failed.return_value = False

    script = 'print("Hello, Lambda!")'
    predefined_objects = {'bot_response': 'Lambda test response'}

    result = CallbackProcessor.run_pyscript(script, predefined_objects)

    assert result == {'bot_response': 'Lambda test response'}
    mock_trigger_lambda.assert_called_once()
    mock_lambda_execution_failed.assert_called_once()


@patch('kairon.async_callback.processor.CloudUtility.lambda_execution_failed')
@patch('kairon.async_callback.processor.CloudUtility.trigger_lambda')
@patch('kairon.async_callback.processor.Utility')
def test_run_pyscript_with_lambda_failure(mock_utility, mock_trigger_lambda, mock_lambda_execution_failed):
    mock_utility.environment = {'async_callback_action': {'pyscript': {'trigger_task': True}}}
    lambda_response = {
        "Payload": {
            "body": None,
            "errorMessage": "Lambda execution failed!"
        }
    }
    mock_trigger_lambda.return_value = lambda_response
    mock_lambda_execution_failed.return_value = False

    script = 'print("Error Case")'
    predefined_objects = {}

    with pytest.raises(AppException, match="Lambda execution failed!"):
        CallbackProcessor.run_pyscript(script, predefined_objects)

    mock_trigger_lambda.assert_called_once()
    mock_lambda_execution_failed.assert_called_once()

@patch('kairon.async_callback.processor.CallbackUtility.pyscript_handler')
@patch('kairon.async_callback.processor.Utility')
def test_run_pyscript_fallback_server_failure(mock_utility, mock_pyscript_handler):
    mock_utility.environment = {'async_callback_action': {'pyscript': {'trigger_task': False}}}
    mock_pyscript_handler.return_value = {
        "statusCode": 500,  # Failure case
        "body": "Internal Server Error"
    }

    script = 'print("This should fail")'
    predefined_objects = {}

    with pytest.raises(AppException, match="Internal Server Error"):
        CallbackProcessor.run_pyscript(script, predefined_objects)
    mock_pyscript_handler.assert_called_once()

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
        await asyncio.sleep(0.1)

        mock_callback.assert_called_once_with({'result': 'execution_result'})

@pytest.mark.asyncio
async def test_run_pyscript_async_exception(mock_script, mock_predefined_objects, mock_callback, mock_executor):
    with patch('kairon.async_callback.processor.CallbackProcessor.run_pyscript', side_effect=AppException("execution_error")):
        CallbackProcessor.run_pyscript_async(mock_script, mock_predefined_objects, mock_callback)
        await asyncio.sleep(0.1)

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
@patch('kairon.shared.callback.data_objects.CallbackData.update_state')
async def test_async_callback(mock_update_state, mock_failure_entry, mock_success_entry, mock_dispatch_message):
    obj = {'result': {'bot_response': 'Test result'}}
    ent = {'action_name': 'Test action', 'bot': 'Test bot', 'identifier': 'Test identifier', 'pyscript_code': 'Test code', 'sender_id': 'Test sender', 'metadata': 'Test metadata', 'callback_url': 'Test url', 'callback_source': 'Test source'}
    cb = {'pyscript_code': 'Test code'}
    c_src = 'Test source'
    bot_id = 'Test bot'
    sid = 'Test sender'
    chnl = 'Test channel'
    rd = {'key': 'value'}

    await CallbackProcessor.async_callback(obj, ent, cb, c_src, bot_id, sid, chnl, rd)

    mock_dispatch_message.assert_called_once_with(bot_id, sid, obj['result']['bot_response'], chnl)
    mock_success_entry.assert_called_once_with(name=ent['action_name'], bot=bot_id,
                                               channel=chnl,
                                               identifier=ent['identifier'],
                                               pyscript_code=cb['pyscript_code'], sender_id=sid, log=obj['result']['bot_response'], request_data=rd, metadata=ent['metadata'], callback_url=ent['callback_url'], callback_source=c_src)
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
                                               pyscript_code=cb['pyscript_code'], sender_id=sid, error_log=f"Error while executing pyscript: {obj['error']}", request_data=rd, metadata=ent['metadata'], callback_url=ent['callback_url'], callback_source=c_src)


@pytest.mark.asyncio
@patch('kairon.async_callback.processor.CallbackLog.create_failure_entry')
async def test_async_callback_no_response_none(mock_failure_entry):
    obj = None  # Simulating a None response
    ent = {'action_name': 'Test action', 'bot': 'Test bot', 'identifier': 'Test identifier',
           'pyscript_code': 'Test code', 'sender_id': 'Test sender', 'metadata': 'Test metadata',
           'callback_url': 'Test url', 'callback_source': 'Test source'}
    cb = {'pyscript_code': 'Test code'}
    c_src = 'Test source'
    bot_id = 'Test bot'
    sid = 'Test sender'
    chnl = 'Test channel'
    rd = {'key': 'value'}

    await CallbackProcessor.async_callback(obj, ent, cb, c_src, bot_id, sid, chnl, rd)
    mock_failure_entry.assert_called_once_with(
        name=ent['action_name'], bot=bot_id, identifier=ent['identifier'],
        channel=chnl, pyscript_code=cb['pyscript_code'], sender_id=sid,
        error_log="No response received from callback script",
        request_data=rd, metadata=ent['metadata'], callback_url=ent['callback_url'], callback_source=c_src
    )

@pytest.mark.asyncio
@patch('kairon.async_callback.processor.CallbackLog.create_failure_entry')
async def test_async_callback_no_response_empty_dict(mock_failure_entry):
    obj = {}  # Simulating an empty dictionary response
    ent = {'action_name': 'Test action', 'bot': 'Test bot', 'identifier': 'Test identifier', 'pyscript_code': 'Test code', 'sender_id': 'Test sender', 'metadata': 'Test metadata', 'callback_url': 'Test url', 'callback_source': 'Test source'}
    cb = {'pyscript_code': 'Test code'}
    c_src = 'Test source'
    bot_id = 'Test bot'
    sid = 'Test sender'
    chnl = 'Test channel'
    rd = {'key': 'value'}

    await CallbackProcessor.async_callback(obj, ent, cb, c_src, bot_id, sid, chnl, rd)
    mock_failure_entry.assert_called_once_with(
        name=ent['action_name'], bot=bot_id, identifier=ent['identifier'],
        channel=chnl, pyscript_code=cb['pyscript_code'], sender_id=sid,
        error_log="No response received from callback script",
        request_data=rd, metadata=ent['metadata'], callback_url=ent['callback_url'], callback_source=c_src
    )

#not needed already covered in other tests
# @patch('kairon.shared.callback.data_objects.CallbackConfig.objects')
# @patch('kairon.shared.callback.data_objects.xor_decrypt_secret')
# @patch('kairon.shared.callback.data_objects.decrypt_secret')
# def test_verify_auth_token(mock_decrypt_secret, mock_xor_decrypt_secret, mock_objects):
#     # Mock the CallbackConfig objects
#     mock_config = MagicMock()
#     mock_config.bot = "test_bot"
#     mock_config.name = "test_name"
#     mock_config.validation_secret = encrypt_secret("test_secret")
#
#     # Use the same mock_config for both the first() and objects.first() calls
#     mock_objects.first.return_value = mock_config
#     mock_objects.return_value.first.return_value = mock_config
#
#     # Mock the decrypt_secret and xor_decrypt_secret functions
#     mock_decrypt_secret.return_value = json.dumps({
#         "bot": "test_bot",
#         "callback_name": "test_name",
#         "validation_secret": "test_secret"
#     })
#     mock_xor_decrypt_secret.return_value = "test_key"
#
#     # Test with valid token
#     token = "valid_token"
#     result = CallbackConfig.verify_auth_token(token)
#     assert result == mock_config, "Expected the returned config to be the mock config"


def test_verify_auth_token_invalid():
    token = "VABBBAcPVwVeD18HB1IBUVNeVVsLUgBUBABZV1JSBFM="
    with pytest.raises(AppException, match="Invalid token!"):
        CallbackConfig.verify_auth_token(token)