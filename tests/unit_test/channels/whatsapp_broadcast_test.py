import asyncio
import os
from unittest.mock import patch, MagicMock

import pytest
from aiohttp import ClientConnectionError, ClientError
from aioresponses import aioresponses
from mongoengine import connect, disconnect

from kairon import Utility
from kairon.chat.handlers.channels.clients.whatsapp.cloud import WhatsappCloud
from kairon.chat.handlers.channels.clients.whatsapp.dialog360 import BSP360Dialog
from kairon.shared.channels.broadcast.whatsapp import WhatsappBroadcast
from kairon.shared.chat.agent.agent_flow import AgenticFlow
from kairon.shared.chat.broadcast.constants import MessageBroadcastLogType
from kairon.shared.chat.broadcast.data_objects import MessageBroadcastLogs
from kairon.shared.chat.broadcast.processor import MessageBroadcastProcessor
from kairon.shared.data.constant import EVENT_STATUS


@pytest.fixture(scope="module", autouse=True)
def setup_environment():
    os.environ["system_file"] = "./tests/testing_data/system.yaml"
    Utility.load_environment()
    Utility.load_system_metadata()
    connect(**Utility.mongoengine_connection())
    yield
    disconnect()


@pytest.mark.asyncio
async def test_send_action_async_success_meta():
    payload = {"key": "value"}
    whatsapp_cloud = WhatsappCloud(access_token="dummy_access_token", from_phone_number_id="dummy_phone_number_id")
    url = f'{whatsapp_cloud.app}/{whatsapp_cloud.from_phone_number_id}/messages?access_token={whatsapp_cloud.access_token}'

    with aioresponses() as mock:
        mock.post(url, payload={"success": True}, status=200)

        success, status_code, response = await whatsapp_cloud.send_action_async(payload)
        assert success is True
        assert status_code == 200
        assert response == {"success": True}

@pytest.mark.asyncio
async def test_send_action_async_retry_success_meta():
    payload = {"key": "value"}
    whatsapp_cloud = WhatsappCloud(access_token="dummy_access_token", from_phone_number_id="dummy_phone_number_id")
    url = f'{whatsapp_cloud.app}/{whatsapp_cloud.from_phone_number_id}/messages?access_token={whatsapp_cloud.access_token}'

    with aioresponses() as mock:
        mock.post(url, payload={"success": True}, status=500)
        mock.post(url, payload={"success": True}, status=200)

        success, status_code, response = await whatsapp_cloud.send_action_async(payload)
        assert success is True
        assert status_code == 200
        assert response == {"success": True}

@pytest.mark.asyncio
async def test_send_action_async_client_connection_error_meta():
    payload = {"key": "value"}
    whatsapp_cloud = WhatsappCloud(access_token="dummy_access_token", from_phone_number_id="dummy_phone_number_id")

    with patch("kairon.chat.handlers.channels.clients.whatsapp.cloud.RetryClient") as mock_retry_client:
        mock_client_instance = mock_retry_client.return_value
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.post.side_effect = ClientConnectionError("Connection Error")

        success, status_code, response = await whatsapp_cloud.send_action_async(payload)
        assert success is False
        assert status_code == 500
        assert "error" in response

@pytest.mark.asyncio
async def test_send_action_async_client_error_meta():
    payload = {"key": "value"}
    whatsapp_cloud = WhatsappCloud(access_token="dummy_access_token", from_phone_number_id="dummy_phone_number_id")

    with patch("kairon.chat.handlers.channels.clients.whatsapp.cloud.RetryClient") as mock_retry_client:
        mock_client_instance = mock_retry_client.return_value
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.post.side_effect = ClientError("Client Error")

        success, status_code, response = await whatsapp_cloud.send_action_async(payload)
        assert success is False
        assert status_code == 500
        assert "error" in response

@pytest.mark.asyncio
async def test_send_action_async_generic_exception_meta():
    payload = {"key": "value"}
    whatsapp_cloud = WhatsappCloud(access_token="dummy_access_token", from_phone_number_id="dummy_phone_number_id")

    with patch("kairon.chat.handlers.channels.clients.whatsapp.cloud.RetryClient") as mock_retry_client:
        mock_client_instance = mock_retry_client.return_value
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.post.side_effect = Exception("Generic Error")

        success, status_code, response = await whatsapp_cloud.send_action_async(payload)
        assert success is False
        assert status_code == 500
        assert "error" in response




@pytest.mark.asyncio
async def test_send_action_async_success_d360():
    payload = {"key": "value"}
    whatsapp_cloud = BSP360Dialog(access_token="dummy_access_token", from_phone_number_id="dummy_phone_number_id")
    url = f'{whatsapp_cloud.app}/messages'
    print(url)
    with aioresponses() as mock:
        mock.post(url, payload={"success": True}, status=200)

        success, status_code, response = await whatsapp_cloud.send_action_async(payload)
        assert success is True
        assert status_code == 200
        assert response == {"success": True}

@pytest.mark.asyncio
async def test_send_action_async_error_d360():
    payload = {"key": "value"}
    whatsapp_cloud = BSP360Dialog(access_token="dummy_access_token", from_phone_number_id="dummy_phone_number_id")
    url = f'{whatsapp_cloud.app}/messages'
    with aioresponses() as mock:
        mock.post(url, payload={"success": False}, status=301)
        mock.post(url, payload={"success": False}, status=301)
        mock.post(url, payload={"success": False}, status=301)


        success, status_code, response = await whatsapp_cloud.send_action_async(payload)
        assert not success
        assert status_code == 301
        assert response == {"success": False}

@pytest.mark.asyncio
async def test_send_action_async_error_2_d360():
    payload = {"key": "value"}
    whatsapp_cloud = BSP360Dialog(access_token="dummy_access_token", from_phone_number_id="dummy_phone_number_id")
    url = f'{whatsapp_cloud.app}/messages'
    with aioresponses() as mock:
        mock.post(url, payload="I love apple", status=301)
        mock.post(url, payload="I love apple", status=301)
        mock.post(url, payload="I love apple", status=301)


        success, status_code, response = await whatsapp_cloud.send_action_async(payload)
        assert not success
        assert status_code == 301
        assert response == "I love apple"



@pytest.mark.asyncio
async def test_send_action_async_client_response_error_d360():
    payload = {"key": "value"}
    whatsapp_cloud = BSP360Dialog(access_token="dummy_access_token", from_phone_number_id="dummy_phone_number_id")
    url = f'{whatsapp_cloud.app}/messages'

    with aioresponses() as mock:
        mock.post(url, status=500)

        success, status_code, response = await whatsapp_cloud.send_action_async(payload)
        assert success is False
        assert status_code == 500
        assert "error" in response

@pytest.mark.asyncio
async def test_send_action_async_client_connection_error_d360():
    payload = {"key": "value"}
    whatsapp_cloud = BSP360Dialog(access_token="dummy_access_token", from_phone_number_id="dummy_phone_number_id")
    url = f'{whatsapp_cloud.app}/messages'

    with aioresponses() as mock:
        mock.post(url, exception=ClientConnectionError("Connection Error"))

        success, status_code, response = await whatsapp_cloud.send_action_async(payload)
        assert success is False
        assert status_code == 500
        assert "error" in response

@pytest.mark.asyncio
async def test_send_action_async_client_error_d360():
    payload = {"key": "value"}
    whatsapp_cloud = BSP360Dialog(access_token="dummy_access_token", from_phone_number_id="dummy_phone_number_id")
    url = f'{whatsapp_cloud.app}/messages'

    with aioresponses() as mock:
        mock.post(url, exception=ClientError("Client Error"))

        success, status_code, response = await whatsapp_cloud.send_action_async(payload)
        assert success is False
        assert status_code == 500
        assert "error" in response

@pytest.mark.asyncio
async def test_send_action_async_generic_exception_d360():
    payload = {"key": "value"}
    whatsapp_cloud = BSP360Dialog(access_token="dummy_access_token", from_phone_number_id="dummy_phone_number_id")
    url = f'{whatsapp_cloud.app}/messages'

    with aioresponses() as mock:
        mock.post(url, exception=Exception("Generic Error"))

        success, status_code, response = await whatsapp_cloud.send_action_async(payload)
        assert success is False
        assert status_code == 500
        assert "error" in response



@pytest.mark.asyncio
async def test_send_async_success_whatsapp():
    payload = {"key": "value"}
    to_phone_number = "1234567890"
    messaging_type = "text"
    whatsapp_cloud = WhatsappCloud(access_token="dummy_access_token", from_phone_number_id="dummy_phone_number_id")
    url = f'{whatsapp_cloud.app}/{whatsapp_cloud.from_phone_number_id}/messages?access_token={whatsapp_cloud.access_token}'

    with aioresponses() as mock:
        mock.post(url, payload={"success": True}, status=200)

        success, status_code, response = await whatsapp_cloud.send_async(payload, to_phone_number, messaging_type)
        assert success is True
        assert status_code == 200
        assert response == {"success": True}

@pytest.mark.asyncio
async def test_send_async_invalid_messaging_type_whatsapp():
    payload = {"key": "value"}
    to_phone_number = "1234567890"
    messaging_type = "invalid_type"
    whatsapp_cloud = WhatsappCloud(access_token="dummy_access_token", from_phone_number_id="dummy_phone_number_id")

    with pytest.raises(ValueError) as excinfo:
        await whatsapp_cloud.send_async(payload, to_phone_number, messaging_type)
    assert str(excinfo.value) == "`invalid_type` is not a valid `messaging_type`"


@pytest.mark.asyncio
async def test_send_async_client_connection_error_whatsapp():
    payload = {"key": "value"}
    to_phone_number = "1234567890"
    messaging_type = "text"
    whatsapp_cloud = WhatsappCloud(access_token="dummy_access_token", from_phone_number_id="dummy_phone_number_id")
    url = f'{whatsapp_cloud.app}/{whatsapp_cloud.from_phone_number_id}/messages?access_token={whatsapp_cloud.access_token}'

    with aioresponses() as mock:
        mock.post(url, exception=ClientConnectionError("Connection Error"))

        success, status_code, response = await whatsapp_cloud.send_async(payload, to_phone_number, messaging_type)
        assert success is False
        assert status_code == 500
        assert "error" in response

@pytest.mark.asyncio
async def test_send_async_generic_exception_whatsapp():
    payload = {"key": "value"}
    to_phone_number = "1234567890"
    messaging_type = "text"
    whatsapp_cloud = WhatsappCloud(access_token="dummy_access_token", from_phone_number_id="dummy_phone_number_id")
    url = f'{whatsapp_cloud.app}/{whatsapp_cloud.from_phone_number_id}/messages?access_token={whatsapp_cloud.access_token}'

    with aioresponses() as mock:
        mock.post(url, exception=Exception("Generic Error"))

        success, status_code, response = await whatsapp_cloud.send_async(payload, to_phone_number, messaging_type)
        assert success is False
        assert status_code == 500
        assert "error" in response


@pytest.mark.asyncio
async def test_send_template_message_async_success():
    name = "template_name"
    to_phone_number = "1234567890"
    language_code = "en"
    components = {"type": "body", "parameters": [{"type": "text", "text": "Hello"}]}
    whatsapp_cloud = WhatsappCloud(access_token="dummy_access_token", from_phone_number_id="dummy_phone_number_id")
    url = f'{whatsapp_cloud.app}/{whatsapp_cloud.from_phone_number_id}/messages?access_token={whatsapp_cloud.access_token}'

    with aioresponses() as mock:
        mock.post(url, payload={"success": True}, status=200)

        success, status_code, response = await whatsapp_cloud.send_template_message_async(name, to_phone_number, language_code, components)
        assert success is True
        assert status_code == 200
        assert response == {"success": True}

@pytest.mark.asyncio
async def test_send_template_message_async_client_response_error():
    name = "template_name"
    to_phone_number = "1234567890"
    language_code = "en"
    components = {"type": "body", "parameters": [{"type": "text", "text": "Hello"}]}
    whatsapp_cloud = WhatsappCloud(access_token="dummy_access_token", from_phone_number_id="dummy_phone_number_id")
    url = f'{whatsapp_cloud.app}/{whatsapp_cloud.from_phone_number_id}/messages?access_token={whatsapp_cloud.access_token}'

    with aioresponses() as mock:
        mock.post(url, status=400)

        success, status_code, response = await whatsapp_cloud.send_template_message_async(name, to_phone_number, language_code, components)
        assert success is False
        assert "error" in response

@pytest.mark.asyncio
async def test_send_template_message_async_client_connection_error():
    name = "template_name"
    to_phone_number = "1234567890"
    language_code = "en"
    components = {"type": "body", "parameters": [{"type": "text", "text": "Hello"}]}
    whatsapp_cloud = WhatsappCloud(access_token="dummy_access_token", from_phone_number_id="dummy_phone_number_id")
    url = f'{whatsapp_cloud.app}/{whatsapp_cloud.from_phone_number_id}/messages?access_token={whatsapp_cloud.access_token}'

    with aioresponses() as mock:
        mock.post(url, exception=ClientConnectionError("Connection Error"))

        success, status_code, response = await whatsapp_cloud.send_template_message_async(name, to_phone_number, language_code, components)
        assert success is False
        assert status_code == 500
        assert "error" in response

@pytest.mark.asyncio
async def test_send_template_message_async_generic_exception():
    name = "template_name"
    to_phone_number = "1234567890"
    language_code = "en"
    components = {"type": "body", "parameters": [{"type": "text", "text": "Hello"}]}
    whatsapp_cloud = WhatsappCloud(access_token="dummy_access_token", from_phone_number_id="dummy_phone_number_id")
    url = f'{whatsapp_cloud.app}/{whatsapp_cloud.from_phone_number_id}/messages?access_token={whatsapp_cloud.access_token}'

    with aioresponses() as mock:
        mock.post(url, exception=Exception("Generic Error"))

        success, status_code, response = await whatsapp_cloud.send_template_message_async(name, to_phone_number, language_code, components)
        assert success is False
        assert status_code == 500
        assert "error" in response





def test_initiate_broadcast():
    # Mocking dependencies
    Utility.environment["broadcast"] = {
            "whatsapp_broadcast_batch_size": 2,
            "whatsapp_broadcast_rate_per_second": 4
    }


    message_list = [
        ("template_id_1", "recipient_1", "en", {"param": "value"}, "namespace_1"),
        ("template_id_2", "recipient_2", "en", {"param": "value"}, "namespace_2"),
        ("template_id_3", "recipient_3", "en", {"param": "value"}, "namespace_3"),
    ]

    bot = "test_bot"
    user = "test_user"
    config = Utility.environment["broadcast"]
    event_id = "test_event_id"
    reference_id = "test_reference_id"

    whatsapp_broadcast = WhatsappBroadcast(bot, user, config, event_id, reference_id)

    with patch.object(WhatsappBroadcast, 'send_template_message', return_value=(True, 200, {})) as mock_send_template_message, \
         patch.object(WhatsappBroadcast, 'send_template_message_retry', return_value=(True, 200, {})) as mock_send_template_message_retry, \
         patch.object(WhatsappBroadcast, 'log_failed_messages') as mock_log_failed_messages, \
         patch('asyncio.run', return_value=(False, [])) as mock_asyncio_run:

        sent_count, non_sent_recipients = whatsapp_broadcast.initiate_broadcast(message_list)

        assert sent_count == len(message_list)
        assert non_sent_recipients == []

        mock_send_template_message.assert_called()
        mock_send_template_message_retry.assert_not_called()
        mock_log_failed_messages.assert_not_called()
        mock_asyncio_run.assert_called()


def test_initiate_broadcast_resend():
    # Mocking dependencies
    Utility.environment["broadcast"] = {
        "whatsapp_broadcast_batch_size": 2,
        "whatsapp_broadcast_rate_per_second": 4
    }

    message_list = [
        ("template_id_1", "recipient_1", 1, "template", "en", {"param": "value"}, "namespace_1"),
        ("template_id_2", "recipient_2", 1, "template", "en", {"param": "value"}, "namespace_2"),
        ("template_id_3", "recipient_3", 1, "template", "en", {"param": "value"}, "namespace_3"),
    ]

    bot = "test_bot"
    user = "test_user"
    config = Utility.environment["broadcast"]
    event_id = "test_event_id"
    reference_id = "test_reference_id"

    whatsapp_broadcast = WhatsappBroadcast(bot, user, config, event_id, reference_id)

    with patch.object(WhatsappBroadcast, 'send_template_message', return_value=(True, 200, {})) as mock_send_template_message, \
         patch.object(WhatsappBroadcast, 'send_template_message_retry', return_value=(True, 200, {})) as mock_send_template_message_retry, \
         patch.object(WhatsappBroadcast, 'log_failed_messages') as mock_log_failed_messages, \
         patch('asyncio.run', return_value=(False, [])) as mock_asyncio_run:

        sent_count, non_sent_recipients = whatsapp_broadcast.initiate_broadcast(message_list, is_resend=True)

        assert sent_count == len(message_list)
        assert non_sent_recipients == []

        mock_send_template_message.assert_not_called()
        mock_send_template_message_retry.assert_called()
        mock_log_failed_messages.assert_not_called()
        mock_asyncio_run.assert_called()




@pytest.mark.asyncio
async def test_send_template_message():
    Utility.environment['notifications'] = {'enable': False}
    template_id = "template_id_1"
    recipient = "recipient_1"
    language_code = "en"
    components = {"param": "value"}
    namespace = "namespace_1"

    bot = "test_bot"
    user = "test_user"
    config = {
        "broadcast": Utility.environment["broadcast"],
        "notifications": {}
    }
    event_id = "test_event_id"
    reference_id = "test_reference_id"

    whatsapp_broadcast = WhatsappBroadcast(bot, user, config, event_id, reference_id)

    async def mock_send_template_message_async(*args, **kwargs):
        return True, 200, {}

    with patch.object(WhatsappBroadcast, '_WhatsappBroadcast__get_client', return_value=MagicMock()) as mock_get_client, \
         patch.object(whatsapp_broadcast, 'channel_client', new_callable=MagicMock) as mock_channel_client, \
         patch.object(whatsapp_broadcast.channel_client, 'send_template_message_async', side_effect=mock_send_template_message_async) as mock_send_template_message_async, \
         patch.object(whatsapp_broadcast, 'log_failed_messages') as mock_log_failed_messages:

        status_flag, status_code, response = await whatsapp_broadcast.send_template_message(template_id, recipient, language_code, components, namespace)

        assert status_flag is True
        assert status_code == 200
        assert response == {}

        mock_send_template_message_async.assert_called_once_with(template_id, recipient, language_code, components, namespace)
        mock_log_failed_messages.assert_not_called()

    del Utility.environment['notifications']



@pytest.mark.asyncio
async def test_send_template_message_retry():
    Utility.environment['notifications'] = {'enable': False}

    template_id = "template_id_1"
    recipient = "recipient_1"
    retry_count = 1
    template = "template_body"
    language_code = "en"
    components = {"param": "value"}
    namespace = "namespace_1"

    bot = "test_bot"
    user = "test_user"
    config = {
        "broadcast": Utility.environment["broadcast"],
        "notifications": {}
    }
    event_id = "test_event_id"
    reference_id = "test_reference_id"

    whatsapp_broadcast = WhatsappBroadcast(bot, user, config, event_id, reference_id)

    async def mock_send_template_message_async(*args, **kwargs):
        return True, 200, {}

    with patch.object(WhatsappBroadcast, '_WhatsappBroadcast__get_client', return_value=MagicMock()) as mock_get_client, \
         patch.object(whatsapp_broadcast, 'channel_client', new_callable=MagicMock) as mock_channel_client, \
         patch.object(whatsapp_broadcast.channel_client, 'send_template_message_async', side_effect=mock_send_template_message_async) as mock_send_template_message_async, \
         patch.object(whatsapp_broadcast, 'log_failed_messages') as mock_log_failed_messages:

        status_flag, status_code, response = await whatsapp_broadcast.send_template_message_retry(template_id, recipient, retry_count, template, language_code, components, namespace)

        assert status_flag is True
        assert status_code == 200
        assert response == {}

        mock_send_template_message_async.assert_called_once_with(template_id, recipient, language_code, components, namespace)
        mock_log_failed_messages.assert_not_called()

    del Utility.environment['notifications']




def test_upsert_broadcast_progress_log_insert():
    Utility.environment["notifications"] = {"enable": False}

    bot = "test_bot_xxx"
    reference_id = "test_reference_id"
    event_id = "test_event_id"
    progress = 50
    total = 100

    MessageBroadcastProcessor.upsert_broadcast_progress_log(bot, reference_id, event_id, progress, total)

    log = MessageBroadcastLogs.objects(bot=bot, reference_id=reference_id, event_id=event_id,
                                       log_type=MessageBroadcastLogType.progress.value).first()
    assert log is not None
    assert log.progress == progress
    assert log.total == total

def test_upsert_broadcast_progress_log_update():
    Utility.environment["notifications"] = {"enable": False}
    bot = "test_bot_xxx"
    reference_id = "test_reference_id"
    event_id = "test_event_id"
    progress = 75
    total = 150

    MessageBroadcastProcessor.upsert_broadcast_progress_log(bot, reference_id, event_id, progress, total)

    log = MessageBroadcastLogs.objects(bot=bot, reference_id=reference_id, event_id=event_id,
                                       log_type=MessageBroadcastLogType.progress.value).first()
    assert log is not None
    assert log.progress == progress
    assert log.total == total


def test_log_failed_messages():
    bot = "test_bot"
    user = "test_user"
    config = {
        "broadcast": Utility.environment["broadcast"],
        "notifications": {}
    }
    event_id = "test_event_id"
    reference_id = "test_reference_id"

    whatsapp_broadcast = WhatsappBroadcast(bot, user, config, event_id, reference_id)

    messages = [
        ("template_id_1", "recipient_1", "en", {"param": "value"}, "namespace_1"),
        ("template_id_2", "recipient_2", "en", {"param": "value"}, "namespace_2")
    ]
    error_msg = "terminated broadcast"
    broadcast_log_type = "send"

    with patch.object(MessageBroadcastProcessor, 'add_event_log') as mock_add_event_log:
        whatsapp_broadcast.log_failed_messages(messages, error_msg, broadcast_log_type)

        assert mock_add_event_log.call_count == len(messages)
        for call in mock_add_event_log.call_args_list:
            args, kwargs = call
            assert kwargs['api_response'] == {"error": error_msg}
            assert kwargs['status'] == EVENT_STATUS.FAIL.value
            assert kwargs['errors'] == [{'code': 131026, 'title': "Message undeliverable", 'message': error_msg}]





@pytest.mark.asyncio
async def test_send_using_flow():
    with patch.object(WhatsappBroadcast, '_WhatsappBroadcast__get_template', return_value=([], None)) as mock_get_template, \
         patch.object(WhatsappBroadcast, 'initiate_broadcast', return_value=(0, [])) as mock_initiate_broadcast, \
         patch.object(MessageBroadcastProcessor, 'add_event_log') as mock_add_event_log, \
         patch.object(MessageBroadcastProcessor, 'update_broadcast_logs_with_template') as mock_update_broadcast_logs_with_template:

        config = {
            "template_config": [
                {
                    "template_id": "template_1",
                    "namespace": "namespace_1",
                    "language": "en",
                    "params": ["param1", "param2"]
                }
            ],
            "flowname": "test_flow"
        }

        event_id = "test_event_id"
        reference_id = "test_reference_id"

        broadcast = WhatsappBroadcast(config=config, bot="test_bot", user="test_user", event_id=event_id, reference_id=reference_id)
        recipients = ["recipient1", "recipient2"]

        broadcast._WhatsappBroadcast__send_using_flow(recipients)

        mock_get_template.assert_called_once_with("template_1", "en")
        mock_initiate_broadcast.assert_called_once()
        mock_add_event_log.assert_called()
        mock_update_broadcast_logs_with_template.assert_called()

        assert mock_add_event_log.call_count == 2
        assert mock_update_broadcast_logs_with_template.call_count == 1




@pytest.mark.asyncio
async def test_send_template_message_success_with_flow():
    template_id = "template_id_1"
    recipient = "recipient_1"
    language_code = "en"
    components = {"param": "value"}
    namespace = "namespace_1"
    flowname = "test_flow"

    bot = "test_bot"
    user = "test_user"
    config = {
        "broadcast": {},
        "notifications": {}
    }
    event_id = "test_event_id"
    reference_id = "test_reference_id"

    whatsapp_broadcast = WhatsappBroadcast(bot, user, config, event_id, reference_id)

    async def mock_send_template_message_async(*args, **kwargs):
        return True, 200, {}

    async def mock_execute_rule(*args, **kwargs):
        return [{"text": '{"param": "value"}'}], None

    with patch.object(WhatsappBroadcast, '_WhatsappBroadcast__get_client', return_value=MagicMock()) as mock_get_client, \
         patch.object(whatsapp_broadcast, 'channel_client', new_callable=MagicMock) as mock_channel_client, \
         patch.object(whatsapp_broadcast.channel_client, 'send_template_message_async', side_effect=mock_send_template_message_async) as mock_send_template_message_async, \
         patch.object(MessageBroadcastProcessor, 'add_event_log') as mock_add_event_log, \
            patch.object(AgenticFlow, '__init__', return_value=None) as mock_init, \
            patch.object(AgenticFlow, 'execute_rule', side_effect=mock_execute_rule) as mock_execute_rule:

        status_flag, status_code, response = await whatsapp_broadcast.send_template_message(template_id, recipient, language_code, components, namespace, flowname)

        assert status_flag is True
        assert status_code == 200
        assert response == {}

        mock_send_template_message_async.assert_called_once_with(template_id, recipient, language_code, components, namespace)
        mock_add_event_log.assert_called_once()

@pytest.mark.asyncio
async def test_send_template_message_success_with_flow():
    template_id = "template_id_1"
    recipient = "recipient_1"
    language_code = "en"
    components = {"param": "value"}
    namespace = "namespace_1"
    flowname = "test_flow"

    bot = "test_bot"
    user = "test_user"
    config = {
        "broadcast": {},
        "notifications": {}
    }
    event_id = "test_event_id"
    reference_id = "test_reference_id"

    whatsapp_broadcast = WhatsappBroadcast(bot, user, config, event_id, reference_id)

    async def mock_send_template_message_async(*args, **kwargs):
        return False, 500, {"error": "Some error"}

    async def mock_execute_rule(*args, **kwargs):
        return [{"text": '{"param": "value"}'}], None

    with patch.object(WhatsappBroadcast, '_WhatsappBroadcast__get_client', return_value=MagicMock()) as mock_get_client, \
         patch.object(whatsapp_broadcast, 'channel_client', new_callable=MagicMock) as mock_channel_client, \
         patch.object(whatsapp_broadcast.channel_client, 'send_template_message_async', side_effect=mock_send_template_message_async) as mock_send_template_message_async, \
         patch.object(MessageBroadcastProcessor, 'add_event_log') as mock_add_event_log, \
        patch.object(AgenticFlow, '__init__', return_value = None) as mock_init,\
         patch.object(AgenticFlow, 'execute_rule', side_effect=mock_execute_rule) as mock_execute_rule:

        status_flag, status_code, response = await whatsapp_broadcast.send_template_message(template_id, recipient, language_code, components, namespace, flowname)

        assert status_flag is False
        assert status_code == 500
        assert response == {"error": "Some error"}

        mock_send_template_message_async.assert_called_once_with(template_id, recipient, language_code, components, namespace)
        mock_add_event_log.assert_not_called()

@pytest.mark.parametrize("should_fail", [False, True])
def test_resend_broadcast_status_transition(should_fail):
    retry_count = 1
    event_id = "64d23a6b3cd4567a12345678"
    reference_id = "test_reference_id"


    dummy_log = MagicMock()
    dummy_log.errors = [{"code": 1001}]
    dummy_log.template_name = "template_1"
    dummy_log.language_code = "en"
    dummy_log.namespace = "namespace_1"
    dummy_log.template_params = ["param1"]
    dummy_log.recipient = "recipient1"
    dummy_log.template = {"name": "template_data"}

    with patch.object(MessageBroadcastProcessor, 'get_settings', return_value={"retry_count": retry_count - 1}), \
         patch.object(MessageBroadcastProcessor, 'extract_message_ids_from_broadcast_logs', return_value={"log1": dummy_log}), \
         patch.object(WhatsappBroadcast, '_WhatsappBroadcast__get_template', return_value=("template_data", None)), \
         patch.object(WhatsappBroadcast, 'initiate_broadcast') as mock_initiate_broadcast, \
         patch.object(MessageBroadcastProcessor, 'add_event_log') as mock_add_event_log, \
         patch.object(MessageBroadcastProcessor, 'update_retry_count', return_value={"retry_count": retry_count}):

        if should_fail:
            mock_initiate_broadcast.side_effect = Exception("Sending failed")
        else:
            mock_initiate_broadcast.return_value = (0, [])


        broadcast = WhatsappBroadcast(
            config={},
            bot="test_bot",
            user="test_user",
            event_id=event_id,
            reference_id=reference_id
        )


        broadcast.resend_broadcast()


        calls = mock_add_event_log.call_args_list
        inprogress_key = f"retry_count_{retry_count}_status"


        inprogress_logged = any(
            call.kwargs.get(inprogress_key) == EVENT_STATUS.INPROGRESS.value
            for call in calls
        )
        final_status = EVENT_STATUS.FAIL.value if should_fail else EVENT_STATUS.COMPLETED.value

        final_logged = any(
            call.kwargs.get(inprogress_key) == final_status
            for call in calls
        )

        assert inprogress_logged, "Expected INPROGRESS status to be logged"
        assert final_logged, f"Expected {final_status} status to be logged"


        final_call_kwargs = calls[-1].kwargs
        assert f"template_{retry_count}" in final_call_kwargs
        assert f"failure_count_{retry_count}" in final_call_kwargs
        assert final_call_kwargs[inprogress_key] == final_status


