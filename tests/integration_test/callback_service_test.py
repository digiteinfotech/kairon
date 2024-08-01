import os
import textwrap

import pytest
from unittest.mock import patch, AsyncMock
from mongoengine import connect

from kairon import Utility
from fastapi.testclient import TestClient
from kairon.shared.callback.data_objects import CallbackData, CallbackConfig



@pytest.fixture(autouse=True, scope='class')
def setup():
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

from kairon.async_callback.main import app
client = TestClient(app)

from kairon.async_callback.router.pyscript_callback import process_router_message
from kairon.exceptions import AppException

@pytest.mark.asyncio
@patch("kairon.async_callback.channel_message_dispacher.ChannelMessageDispatcher.dispatch_message", new_callable=AsyncMock)
async def test_get_callback(mock_dispatch_message):
    response = client.get('/callback/6697add6b8e47524eb983373/callback_action1/019107c7570577a6b0f279b4038c4a8f?token=gAAAAABmqK71xDb4apnxOAfJjDUv1lrCTooWNX0GPyBHhqW1KBlblUqGNPwsX1V7FlIlgpwWGRWljiYp9mYAf1eG4AcG1dTXQuZCndCewox-CLU5_s7f-uMyncxWyaPV0i0oLE9skkZA')
    assert response.status_code == 200
    assert response.json() == {"message": "success", "data": "019107c7570577a6b0f279b4038c4a8f i am happy : )", "error_code": 0, "success": True}
    assert mock_dispatch_message.called_once_with("6697add6b8e47524eb983373", "5489844732", "019107c7570577a6b0f279b4038c4a8f i am happy : )", "telegram")

@pytest.mark.asyncio
@patch("kairon.async_callback.channel_message_dispacher.ChannelMessageDispatcher.dispatch_message", new_callable=AsyncMock)
async def test_post_callback(mock_dispatch_message):
    response = client.post('/callback/6697add6b8e47524eb983373/callback_action1/019107c7570577a6b0f279b4038c4a8f?token=gAAAAABmqK71xDb4apnxOAfJjDUv1lrCTooWNX0GPyBHhqW1KBlblUqGNPwsX1V7FlIlgpwWGRWljiYp9mYAf1eG4AcG1dTXQuZCndCewox-CLU5_s7f-uMyncxWyaPV0i0oLE9skkZA')
    assert response.status_code == 200
    assert response.json() == {"message": "success", "data": "019107c7570577a6b0f279b4038c4a8f i am happy : )", "error_code": 0, "success": True}
    assert mock_dispatch_message.called_once_with("6697add6b8e47524eb983373", "5489844732", "019107c7570577a6b0f279b4038c4a8f i am happy : )", "telegram")


@pytest.mark.asyncio
@patch("kairon.async_callback.channel_message_dispacher.ChannelMessageDispatcher.dispatch_message", new_callable=AsyncMock)
async def test_put_callback(mock_dispatch_message):
    response = client.put('/callback/6697add6b8e47524eb983373/callback_action1/019107c7570577a6b0f279b4038c4a8f?token=gAAAAABmqK71xDb4apnxOAfJjDUv1lrCTooWNX0GPyBHhqW1KBlblUqGNPwsX1V7FlIlgpwWGRWljiYp9mYAf1eG4AcG1dTXQuZCndCewox-CLU5_s7f-uMyncxWyaPV0i0oLE9skkZA')
    assert response.status_code == 200
    assert response.json() == {"message": "success", "data": "019107c7570577a6b0f279b4038c4a8f i am happy : )", "error_code": 0, "success": True}
    assert mock_dispatch_message.called_once_with("6697add6b8e47524eb983373", "5489844732", "019107c7570577a6b0f279b4038c4a8f i am happy : )", "telegram")


@pytest.mark.asyncio
@patch("kairon.async_callback.channel_message_dispacher.ChannelMessageDispatcher.dispatch_message", new_callable=AsyncMock)
async def test_patch_callback(mock_dispatch_message):
    response = client.patch('/callback/6697add6b8e47524eb983373/callback_action1/019107c7570577a6b0f279b4038c4a8f?token=gAAAAABmqK71xDb4apnxOAfJjDUv1lrCTooWNX0GPyBHhqW1KBlblUqGNPwsX1V7FlIlgpwWGRWljiYp9mYAf1eG4AcG1dTXQuZCndCewox-CLU5_s7f-uMyncxWyaPV0i0oLE9skkZA')
    assert response.status_code == 200
    assert response.json() == {"message": "success", "data": "019107c7570577a6b0f279b4038c4a8f i am happy : )", "error_code": 0, "success": True}
    assert mock_dispatch_message.called_once_with("6697add6b8e47524eb983373", "5489844732", "019107c7570577a6b0f279b4038c4a8f i am happy : )", "telegram")


@pytest.mark.asyncio
@patch("kairon.async_callback.channel_message_dispacher.ChannelMessageDispatcher.dispatch_message", new_callable=AsyncMock)
async def test_delete_callback(mock_dispatch_message):
    response = client.delete('/callback/6697add6b8e47524eb983373/callback_action1/019107c7570577a6b0f279b4038c4a8f?token=gAAAAABmqK71xDb4apnxOAfJjDUv1lrCTooWNX0GPyBHhqW1KBlblUqGNPwsX1V7FlIlgpwWGRWljiYp9mYAf1eG4AcG1dTXQuZCndCewox-CLU5_s7f-uMyncxWyaPV0i0oLE9skkZA')
    assert response.status_code == 200
    assert response.json() == {"message": "success", "data": "019107c7570577a6b0f279b4038c4a8f i am happy : )", "error_code": 0, "success": True}
    assert mock_dispatch_message.called_once_with("6697add6b8e47524eb983373", "5489844732", "019107c7570577a6b0f279b4038c4a8f i am happy : )", "telegram")


@pytest.mark.asyncio
async def test_invalid_request():
    with pytest.raises(AppException):
        await process_router_message("test_bot", "test_name", "test_param", request=None)


@pytest.mark.asyncio
@patch("kairon.async_callback.processor.run_pyscript_async", new_callable=AsyncMock)
@patch("kairon.async_callback.channel_message_dispacher.ChannelMessageDispatcher.dispatch_message", new_callable=AsyncMock)
async def test_async_callback(mock_dispatch_message, mock_run_pyscript_async):
    response = client.get('/callback/6697add6b8e47524eb983373/callback_action2/019107c7570577a6b0f279b4038c4a8a?token=gAAAAABmqK71xDb4apnxOAfJjDUv1lrCTooWNX0GPyBHhqW1KBlblUqGNPwsX1V7FlIlgpwWGRWljiYp9mYAf1eG4AcG1dTXQuZCndCewox-CLU5_s7f-uMyncxWyaPV0i0oLE9skkZA')
    assert response.status_code == 200
    assert response.json() == {"message": "success", "data": None, "error_code": 0, "success": True}
    assert mock_run_pyscript_async.called_once()
    assert mock_dispatch_message.called_once()


@pytest.mark.asyncio
@patch("kairon.async_callback.processor.run_pyscript")
@patch("kairon.async_callback.channel_message_dispacher.ChannelMessageDispatcher.dispatch_message", new_callable=AsyncMock)
async def test_pyscript_failure(mock_dispatch_message, mock_run_pyscript):
    mock_run_pyscript.side_effect = AppException("Error")
    response = client.get('/callback/6697add6b8e47524eb983373/callback_action1/019107c7570577a6b0f279b4038c4a8f?token=gAAAAABmqK71xDb4apnxOAfJjDUv1lrCTooWNX0GPyBHhqW1KBlblUqGNPwsX1V7FlIlgpwWGRWljiYp9mYAf1eG4AcG1dTXQuZCndCewox-CLU5_s7f-uMyncxWyaPV0i0oLE9skkZA')
    assert response.status_code == 200
    assert response.json() == {"message": "Error", "error_code": 400, "success": False, "data": None}
    assert mock_run_pyscript.called_once()
    assert not mock_dispatch_message.called_once()


@pytest.mark.asyncio
@patch("kairon.async_callback.processor.run_pyscript")
@patch("kairon.async_callback.channel_message_dispacher.ChannelMessageDispatcher.dispatch_message", new_callable=AsyncMock)
async def test_dispatch_message_failure(mock_dispatch_message, mock_run_pyscript):
    mock_dispatch_message.side_effect = AppException("Error")
    response = client.get('/callback/6697add6b8e47524eb983373/callback_action1/019107c7570577a6b0f279b4038c4a8f?token=gAAAAABmqK71xDb4apnxOAfJjDUv1lrCTooWNX0GPyBHhqW1KBlblUqGNPwsX1V7FlIlgpwWGRWljiYp9mYAf1eG4AcG1dTXQuZCndCewox-CLU5_s7f-uMyncxWyaPV0i0oLE9skkZA')
    assert response.status_code == 200
    assert response.json() == {"message": "Error", "error_code": 400, "success": False, "data": {}}
    assert mock_run_pyscript.called_once()
    assert mock_dispatch_message.called_once()
