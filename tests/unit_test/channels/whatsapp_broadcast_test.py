import os
from unittest.mock import patch

import pytest
from aiohttp import ClientConnectionError, ClientError
from aioresponses import aioresponses

from kairon import Utility
from kairon.chat.handlers.channels.clients.whatsapp.cloud import WhatsappCloud
from kairon.chat.handlers.channels.clients.whatsapp.dialog360 import BSP360Dialog

os.environ["system_file"] = "./tests/testing_data/system.yaml"
Utility.load_environment()
Utility.load_system_metadata()

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

import pytest
from aioresponses import aioresponses
from kairon.chat.handlers.channels.clients.whatsapp.cloud import WhatsappCloud

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

