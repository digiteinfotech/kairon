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
                       "metadata": {"happy": "i am happy : )"}, "identifier": "01916940879576a391a0cd1223fa8684",
                       "callback_url": "http://localhost:5059/callback/d/01916940879576a391a0cd1223fa8684/gAAAAABmwuGEYHfCz1vYBH9cp8KVcB0Pf9y5c6N3IOYIw8y0A-m4dX2gE9VW-1c9yLAK-ZKXVODp58jmSfhyeI03yUkLR1kqZUNPk_qNRIKROMXMV-wKDbqAtWOwXBXM5EVbWNj6YHCyZKwJgrGidGSjpt7UrDnprr_rmDexgCssfag_5xEtrHzVSziDEZSDCHxupAJZ_l1AA8SkxwVpqgxLdt1Nu1r2SjyZaMvtt4TFYCKYIO6CeMfgShbEqcqHeonfox_UCbhPA68RNWWHhsoHh5o66fm94A==",
                       "execution_mode": "sync"}
    callback_data_2 = {"action_name": "callback_action2", "callback_name": "callback_script3",
                       "bot": "6697add6b8e47524eb983373", "sender_id": "5489844732", "channel": "telegram",
                       "metadata": {"happy": "i am happy : )"}, "identifier": "01916940879576a391a0cd1223fa8685",
                       "callback_url": "http://localhost:5059/callback/d/01916940879576a391a0cd1223fa8685/gAAAAABmwuGEYHfCz1vYBH9cp8KVcB0Pf9y5c6N3IOYIw8y0A-m4dX2gE9VW-1c9yLAK-ZKXVODp58jmSfhyeI03yUkLR1kqZUNPk_qNRIKROMXMV-wKDbqAtWOwXBXM5EVbWNj6YHCyZKwJgrGidGSjpt7UrDnprr_rmDexgCssfag_5xEtrHzVSziDEZSDCHxupAJZ_l1AA8SkxwVpqgxLdt1Nu1r2SjyZaMvtt4TFYCKYIO6CeMfgShbEqcqHeonfox_UCbhPA68RNWWHhsoHh5o66fm94A==",
                       "execution_mode": "sync"}
    callback_config_1 = {"name": "callback_script2",
                         "pyscript_code": "bot_response = f\"{req} {metadata['happy']}\"",
                         "validation_secret": "0191693df8f972529fc22d83413f19b1",
                         "execution_mode": "sync", "bot": "6697add6b8e47524eb983373"}
    callback_config_2 = {"name": "callback_script3",
                         "pyscript_code": "bot_response = f\"{req} {metadata['happy']}\"",
                         "validation_secret": "0191693df8f972529fc22d83413f19b1",
                         "execution_mode": "async", "bot": "6697add6b8e47524eb983373"}

    callback_config_3 = {
      "name": "callback_script4",
      "pyscript_code": "bot_response = f'hello -> {req}'",
      "validation_secret": "01916febcbe67a8a9a151842320697d2",
      "execution_mode": "async",
      "expire_in": 0,
      "shorten_token": False,
      "standalone": False,
      "standalone_id_path": "",
      "bot": "6697add6b8e47524eb983373"
    }


    callback_data_3 = {
      "action_name": "callback_action1",
      "callback_name": "callback_script4",
      "bot": "6697add6b8e47524eb983373",
      "sender_id": "spandan.mondal@nimblework.com",
      "channel": "unsupported (None)",
      "metadata": {
        "happy": "i am happy"
      },
      "identifier": "01916fefd1897634ad82274af4a7ecde",
      "timestamp": 1724159873.4197152,
      "callback_url": "http://localhost:5059/callback/d/01916fefd1897634ad82274af4a7ecde/gAAAAABmxJeByymLTcvGh3ZcnUVSeh6hZrEV2EAVfBmMm1X5lDgjaSSp4E6h9LiqBE34uRgriOLU2ZRkBoKkg7w_pbq6cQ6OC_afnHagr99xNyBfnvzfXMujGCVNnNSGnPnlVYlN_TBK66QoaDVt1o6Mp4b1kJYyBE1I-Avq69Mj-5IRA2D0KP2r80kTWGWIGzbGVwPlWtsqTQtGj-gLl_O9eKJ0s5i-XlZC5Ge0B2P-EUsXqAA_G2tlDMOjpk0g9ppUiRXt4KYiW2ZQ6MdrJTJDY2ohydYnLw==",
      "execution_mode": "async",
      "state": 0,
      "is_valid": True
    }


    callback_config_4 = {
        "name": "callback_script5",
        "pyscript_code": "bot_response = f'hello -> {req}'",
        "validation_secret": "01916ffe298b7c1bb951ef9c9cbd1d74",
        "execution_mode": "sync",
        "expire_in": 0,
        "shorten_token": True,
        "token_hash": "01916ffe298d730d92a7d64ba792d0bd",
        "standalone": False,
        "standalone_id_path": "",
        "bot": "6697add6b8e47524eb983373",
        "token_value": "gAAAAABmxJustZ1pGC3vbLCbLHMhuunugQnnu9BRz1FA7f1PMstj5SeZRQMuVh_4-kiHWlklO6zc0P63sFQ7rirqICTFhRYWzPko9VzehrMA1GR9j77sk79mXSPTHI7UGSWsyrdABPHD7791dKOeSU_FPjdiwxiB-CbPppPOl6ZZcvzdMDJ_c7fNioF35cb9r7qqg9vrzmvAhzOjovbul7gqPOwDd_SGq2YV_yGGgbnpPFxwe6Jon3rS9zB8m24drkaMCsmqdJfah2AjgJrCP8XrFAsMKXd5uw=="

    }

    callback_data_4 = {
      "action_name": "callback_action1",
      "callback_name": "callback_script5",
      "bot": "6697add6b8e47524eb983373",
      "sender_id": "spandan.mondal@nimblework.com",
      "channel": "unsupported (None)",
      "metadata": {
        "happy": "I am happy"
      },
      "identifier": "019170001814712f8921076fd134a083",
      "timestamp": 1724160940.057088,
      "callback_url": "http://localhost:5059/callback/d/019170001814712f8921076fd134a083/98bxWFZL9nZy0L3lAKV2Qr_jI6iEQ6CpZq2vDnhQwQg",
      "execution_mode": "sync",
      "state": 0,
      "is_valid": True
    }

    callback_config_5 = {
        "name": "callback_script6",
        "pyscript_code": "bot_response = f'standalone -> {req}'",
        "validation_secret": "0191702079f47e4392f3bd4460d95409",
        "execution_mode": "sync",
        "expire_in": 0,
        "shorten_token": False,
        "standalone": True,
        "standalone_id_path": "data.id",
        "bot": "6697add6b8e47524eb983373"
    }

    callback_data_5 = {
      "action_name": "callback_action1",
      "callback_name": "callback_script6",
      "bot": "6697add6b8e47524eb983373",
      "sender_id": "spandan.mondal@nimblework.com",
      "channel": "unsupported (None)",
      "metadata": {
        "happy": "I am happy"
      },
      "identifier": "0191702183ca7ac6b75be9cd645c6437",
      "timestamp": 1724163130.3162396,
      "callback_url": "http://localhost:5059/callback/s/gAAAAABmxKQ6lHtDmxTmr_X4nyUGEKL72ylRLODr4IAxsUVr3e9dx7ZTDSL0IlzvGCwLzSDrsyVqanSPSj6JB7srql3dH-rVb9KG6oAcW4yhsMJVP_WPa9sD5J7NqCcShJI3KgjjE7kAEkqqr0VqE2XCEwC7vUCjcYPasw2q4PhOCvg-_CMxT6gC8ZQL7vUVi74FdOnNTQhfiOvXp4ggeV_Jq-xer_-8gTnsplM_nZ_HRxns45gGzAyvtwsUWYnWOPleh6HQn1rgmjfS1hQuYmR7JGxgZDFDZA==",
      "execution_mode": "async",
      "state": 0,
      "is_valid": True
    }

    callback_config_6 = {
      "name": "callback_script7",
      "pyscript_code": "state += 1\nbot_response = f'state -> {state}'",
      "validation_secret": "0191703078f779199d90c1a91fe9839f",
      "execution_mode": "sync",
      "expire_in": 0,
      "shorten_token": True,
      "token_hash": "0191703078f87a039906afc0a219dd5c",
      "standalone": True,
      "standalone_id_path": "data.id",
      "bot": "6697add6b8e47524eb983373",
      "token_value": "gAAAAABmxKl5tT0UKwkqYi2n9yV1lFAAJKsZEM0G9w7kmN8NIYR9JKF1F9ecZoUY6P9kClUC_QnLXXGLa3T4Xugdry84ioaDtGF9laXcQl_82Fvs9KmKX8xfa4-rJs1cto1Jd6fqeGIT7mR3kn56_EliP83aGoCl_sk9B0-2gPDgt-EJZQ20l-3OaT-rhFoFanjKvRiE8e4xp9sdxxjgDWLbCF3kCtTqTtg6Wovw3mXZoVzxzNEUmd2OGZiO6IsIJJaU202w3CZ2rPnmK8I2aRGg8tMi_-ObOg=="
    }

    callback_data_6 = {
      "action_name": "callback_action1",
      "callback_name": "callback_script7",
      "bot": "6697add6b8e47524eb983373",
      "sender_id": "spandan.mondal@nimblework.com",
      "channel": "unsupported (None)",
      "metadata": {
        "happy": "I am happy"
      },
      "identifier": "01917036016877eb8ffb3930e40f6162",
      "timestamp": 1724164473.1961515,
      "callback_url": "http://localhost:5059/callback/s/98bxWFcdoyN30eO5APd2Fb_ocqmBE_f7ZqinBXgElg8",
      "execution_mode": "sync",
      "state": 0,
      "is_valid": True
    }

    CallbackData.objects.delete()
    CallbackConfig.objects.delete()
    CallbackData.objects.insert(CallbackData(**callback_data_1))
    CallbackConfig.objects.insert(CallbackConfig(**callback_config_1))
    CallbackData.objects.insert(CallbackData(**callback_data_2))
    CallbackConfig.objects.insert(CallbackConfig(**callback_config_2))
    CallbackData.objects.insert(CallbackData(**callback_data_3))
    CallbackConfig.objects.insert(CallbackConfig(**callback_config_3))
    CallbackData.objects.insert(CallbackData(**callback_data_4))
    CallbackConfig.objects.insert(CallbackConfig(**callback_config_4))
    CallbackData.objects.insert(CallbackData(**callback_data_5))
    CallbackConfig.objects.insert(CallbackConfig(**callback_config_5))
    CallbackData.objects.insert(CallbackData(**callback_data_6))
    CallbackConfig.objects.insert(CallbackConfig(**callback_config_6))

from kairon.async_callback.main import app
client = TestClient(app)

from kairon.async_callback.router.pyscript_callback import process_router_message
from kairon.exceptions import AppException

@pytest.mark.asyncio
@patch("kairon.async_callback.channel_message_dispacher.ChannelMessageDispatcher.dispatch_message", new_callable=AsyncMock)
async def test_get_callback(mock_dispatch_message):
    response = client.get('/callback/d/01916940879576a391a0cd1223fa8684/gAAAAABmwuGEYHfCz1vYBH9cp8KVcB0Pf9y5c6N3IOYIw8y0A-m4dX2gE9VW-1c9yLAK-ZKXVODp58jmSfhyeI03yUkLR1kqZUNPk_qNRIKROMXMV-wKDbqAtWOwXBXM5EVbWNj6YHCyZKwJgrGidGSjpt7UrDnprr_rmDexgCssfag_5xEtrHzVSziDEZSDCHxupAJZ_l1AA8SkxwVpqgxLdt1Nu1r2SjyZaMvtt4TFYCKYIO6CeMfgShbEqcqHeonfox_UCbhPA68RNWWHhsoHh5o66fm94A==')
    assert response.status_code == 200
    assert response.json() == {"message": "success", "data": "{'type': 'GET', 'body': None, 'params': {}} i am happy : )", "error_code": 0, "success": True}
    assert mock_dispatch_message.called_once_with("6697add6b8e47524eb983373", "5489844732", "019107c7570577a6b0f279b4038c4a8f i am happy : )", "telegram")

@pytest.mark.asyncio
@patch("kairon.async_callback.channel_message_dispacher.ChannelMessageDispatcher.dispatch_message", new_callable=AsyncMock)
async def test_post_callback(mock_dispatch_message):
    req_body = {
        'key_1' : 'value_1'
    }

    response = client.post('/callback/d/01916940879576a391a0cd1223fa8684/gAAAAABmwuGEYHfCz1vYBH9cp8KVcB0Pf9y5c6N3IOYIw8y0A-m4dX2gE9VW-1c9yLAK-ZKXVODp58jmSfhyeI03yUkLR1kqZUNPk_qNRIKROMXMV-wKDbqAtWOwXBXM5EVbWNj6YHCyZKwJgrGidGSjpt7UrDnprr_rmDexgCssfag_5xEtrHzVSziDEZSDCHxupAJZ_l1AA8SkxwVpqgxLdt1Nu1r2SjyZaMvtt4TFYCKYIO6CeMfgShbEqcqHeonfox_UCbhPA68RNWWHhsoHh5o66fm94A==',
                            json=req_body)
    assert response.status_code == 200
    assert response.json() == {"message": "success", "data": "{'type': 'POST', 'body': {'key_1': 'value_1'}, 'params': {}} i am happy : )", "error_code": 0, "success": True}
    assert mock_dispatch_message.called_once_with("6697add6b8e47524eb983373", "5489844732", "{'type': 'POST', 'body': {'key_1': 'value_1'}, 'params': {}} i am happy : )", "telegram")


@pytest.mark.asyncio
@patch("kairon.async_callback.channel_message_dispacher.ChannelMessageDispatcher.dispatch_message", new_callable=AsyncMock)
async def test_post_callback_req_body_non_json(mock_dispatch_message):
    req_body = "key_1=value_1"
    response = client.post('/callback/d/01916940879576a391a0cd1223fa8684/gAAAAABmwuGEYHfCz1vYBH9cp8KVcB0Pf9y5c6N3IOYIw8y0A-m4dX2gE9VW-1c9yLAK-ZKXVODp58jmSfhyeI03yUkLR1kqZUNPk_qNRIKROMXMV-wKDbqAtWOwXBXM5EVbWNj6YHCyZKwJgrGidGSjpt7UrDnprr_rmDexgCssfag_5xEtrHzVSziDEZSDCHxupAJZ_l1AA8SkxwVpqgxLdt1Nu1r2SjyZaMvtt4TFYCKYIO6CeMfgShbEqcqHeonfox_UCbhPA68RNWWHhsoHh5o66fm94A==',
                            json=req_body)
    assert response.status_code == 200
    assert response.json() == {"message": "success", "data": "{'type': 'POST', 'body': 'key_1=value_1', 'params': {}} i am happy : )", "error_code": 0, "success": True}
    assert mock_dispatch_message.called_once_with("6697add6b8e47524eb983373", "5489844732", "{'type': 'POST', 'body': 'key_1=value_1', 'params': {}} i am happy : )", "telegram")


@pytest.mark.asyncio
@patch("kairon.async_callback.channel_message_dispacher.ChannelMessageDispatcher.dispatch_message", new_callable=AsyncMock)
async def test_put_callback(mock_dispatch_message):
    response = client.put('/callback/d/01916940879576a391a0cd1223fa8684/gAAAAABmwuGEYHfCz1vYBH9cp8KVcB0Pf9y5c6N3IOYIw8y0A-m4dX2gE9VW-1c9yLAK-ZKXVODp58jmSfhyeI03yUkLR1kqZUNPk_qNRIKROMXMV-wKDbqAtWOwXBXM5EVbWNj6YHCyZKwJgrGidGSjpt7UrDnprr_rmDexgCssfag_5xEtrHzVSziDEZSDCHxupAJZ_l1AA8SkxwVpqgxLdt1Nu1r2SjyZaMvtt4TFYCKYIO6CeMfgShbEqcqHeonfox_UCbhPA68RNWWHhsoHh5o66fm94A==')
    assert response.status_code == 200
    assert response.json() == {"message": "success", "data": "{'type': 'PUT', 'body': None, 'params': {}} i am happy : )", "error_code": 0, "success": True}
    assert mock_dispatch_message.called_once_with("6697add6b8e47524eb983373", "5489844732", "{'type': 'PUT', 'body': None, 'params': {}} i am happy : )", "telegram")


@pytest.mark.asyncio
@patch("kairon.async_callback.channel_message_dispacher.ChannelMessageDispatcher.dispatch_message", new_callable=AsyncMock)
async def test_patch_callback(mock_dispatch_message):
    response = client.patch('/callback/d/01916940879576a391a0cd1223fa8684/gAAAAABmwuGEYHfCz1vYBH9cp8KVcB0Pf9y5c6N3IOYIw8y0A-m4dX2gE9VW-1c9yLAK-ZKXVODp58jmSfhyeI03yUkLR1kqZUNPk_qNRIKROMXMV-wKDbqAtWOwXBXM5EVbWNj6YHCyZKwJgrGidGSjpt7UrDnprr_rmDexgCssfag_5xEtrHzVSziDEZSDCHxupAJZ_l1AA8SkxwVpqgxLdt1Nu1r2SjyZaMvtt4TFYCKYIO6CeMfgShbEqcqHeonfox_UCbhPA68RNWWHhsoHh5o66fm94A==')
    assert response.status_code == 200
    assert response.json() == {"message": "success", "data": "{'type': 'PATCH', 'body': None, 'params': {}} i am happy : )", "error_code": 0, "success": True}
    assert mock_dispatch_message.called_once_with("6697add6b8e47524eb983373", "5489844732", "{'type': 'PATCH', 'body': None, 'params': {}} i am happy : )", "telegram")


@pytest.mark.asyncio
@patch("kairon.async_callback.channel_message_dispacher.ChannelMessageDispatcher.dispatch_message", new_callable=AsyncMock)
async def test_delete_callback(mock_dispatch_message):
    response = client.delete('/callback/d/01916940879576a391a0cd1223fa8684/gAAAAABmwuGEYHfCz1vYBH9cp8KVcB0Pf9y5c6N3IOYIw8y0A-m4dX2gE9VW-1c9yLAK-ZKXVODp58jmSfhyeI03yUkLR1kqZUNPk_qNRIKROMXMV-wKDbqAtWOwXBXM5EVbWNj6YHCyZKwJgrGidGSjpt7UrDnprr_rmDexgCssfag_5xEtrHzVSziDEZSDCHxupAJZ_l1AA8SkxwVpqgxLdt1Nu1r2SjyZaMvtt4TFYCKYIO6CeMfgShbEqcqHeonfox_UCbhPA68RNWWHhsoHh5o66fm94A==')
    assert response.status_code == 200
    assert response.json() == {"message": "success", "data": "{'type': 'DELETE', 'body': None, 'params': {}} i am happy : )", "error_code": 0, "success": True}
    assert mock_dispatch_message.called_once_with("6697add6b8e47524eb983373", "5489844732", "{'type': 'DELETE', 'body': None, 'params': {}} i am happy : )", "telegram")


@pytest.mark.asyncio
async def test_invalid_request():
    with pytest.raises(AppException):
        await process_router_message("test_bot", "test_name", "test_param", request=None)


@pytest.mark.asyncio
@patch("kairon.async_callback.processor.CallbackProcessor.run_pyscript_async", new_callable=AsyncMock)
@patch("kairon.async_callback.channel_message_dispacher.ChannelMessageDispatcher.dispatch_message", new_callable=AsyncMock)
async def test_async_callback(mock_dispatch_message, mock_run_pyscript_async):
    response = client.get('/callback/d/01916fefd1897634ad82274af4a7ecde/gAAAAABmxJeByymLTcvGh3ZcnUVSeh6hZrEV2EAVfBmMm1X5lDgjaSSp4E6h9LiqBE34uRgriOLU2ZRkBoKkg7w_pbq6cQ6OC_afnHagr99xNyBfnvzfXMujGCVNnNSGnPnlVYlN_TBK66QoaDVt1o6Mp4b1kJYyBE1I-Avq69Mj-5IRA2D0KP2r80kTWGWIGzbGVwPlWtsqTQtGj-gLl_O9eKJ0s5i-XlZC5Ge0B2P-EUsXqAA_G2tlDMOjpk0g9ppUiRXt4KYiW2ZQ6MdrJTJDY2ohydYnLw==')
    assert response.status_code == 200
    assert response.json() == {"message": "success", "data": None, "error_code": 0, "success": True}
    assert mock_run_pyscript_async.called_once()
    assert mock_dispatch_message.called_once()


@pytest.mark.asyncio
@patch("kairon.async_callback.processor.CallbackProcessor.run_pyscript")
@patch("kairon.async_callback.channel_message_dispacher.ChannelMessageDispatcher.dispatch_message", new_callable=AsyncMock)
async def test_pyscript_failure(mock_dispatch_message, mock_run_pyscript):
    mock_run_pyscript.side_effect = AppException("Error")
    response = client.get('/callback/d/01916940879576a391a0cd1223fa8684/gAAAAABmwuGEYHfCz1vYBH9cp8KVcB0Pf9y5c6N3IOYIw8y0A-m4dX2gE9VW-1c9yLAK-ZKXVODp58jmSfhyeI03yUkLR1kqZUNPk_qNRIKROMXMV-wKDbqAtWOwXBXM5EVbWNj6YHCyZKwJgrGidGSjpt7UrDnprr_rmDexgCssfag_5xEtrHzVSziDEZSDCHxupAJZ_l1AA8SkxwVpqgxLdt1Nu1r2SjyZaMvtt4TFYCKYIO6CeMfgShbEqcqHeonfox_UCbhPA68RNWWHhsoHh5o66fm94A==')
    assert response.status_code == 200
    assert response.json() == {"message": "Error", "error_code": 400, "success": False, "data": None}
    assert mock_run_pyscript.called_once()
    assert mock_dispatch_message.called_once()


@pytest.mark.asyncio
@patch("kairon.async_callback.processor.CallbackProcessor.run_pyscript")
@patch("kairon.async_callback.channel_message_dispacher.ChannelMessageDispatcher.dispatch_message", new_callable=AsyncMock)
async def test_dispatch_message_failure(mock_dispatch_message, mock_run_pyscript):
    mock_dispatch_message.side_effect = AppException("Error")
    response = client.get('/callback/d/01916940879576a391a0cd1223fa8684/gAAAAABmwuGEYHfCz1vYBH9cp8KVcB0Pf9y5c6N3IOYIw8y0A-m4dX2gE9VW-1c9yLAK-ZKXVODp58jmSfhyeI03yUkLR1kqZUNPk_qNRIKROMXMV-wKDbqAtWOwXBXM5EVbWNj6YHCyZKwJgrGidGSjpt7UrDnprr_rmDexgCssfag_5xEtrHzVSziDEZSDCHxupAJZ_l1AA8SkxwVpqgxLdt1Nu1r2SjyZaMvtt4TFYCKYIO6CeMfgShbEqcqHeonfox_UCbhPA68RNWWHhsoHh5o66fm94A==')
    result = response.json()
    assert result["error_code"] == 400
    assert result["success"] == False
    assert mock_run_pyscript.called_once()
    assert mock_dispatch_message.called_once()


@pytest.mark.asyncio
@patch("kairon.async_callback.channel_message_dispacher.ChannelMessageDispatcher.dispatch_message", new_callable=AsyncMock)
async def test_get_callback_url_shorten(mock_dispatch_message):
    response = client.get('/callback/d/019170001814712f8921076fd134a083/98bxWFZL9nZy0L3lAKV2Qr_jI6iEQ6CpZq2vDnhQwQg')
    assert response.status_code == 200
    assert response.json() == {"message": "success", "data": "hello -> {'type': 'GET', 'body': None, 'params': {}}", "error_code": 0, "success": True}


@pytest.mark.asyncio
@patch("kairon.async_callback.channel_message_dispacher.ChannelMessageDispatcher.dispatch_message", new_callable=AsyncMock)
async def test_post_callback_url_shorten(mock_dispatch_message):
    req_body = {
        'key_1': 'value_1'
    }
    response = client.post('/callback/d/019170001814712f8921076fd134a083/98bxWFZL9nZy0L3lAKV2Qr_jI6iEQ6CpZq2vDnhQwQg',
                            json=req_body)
    assert response.status_code == 200
    assert response.json() == {"message": "success", "data": "hello -> {'type': 'POST', 'body': {'key_1': 'value_1'}, 'params': {}}", "error_code": 0, "success": True}


@pytest.mark.asyncio
@patch("kairon.async_callback.channel_message_dispacher.ChannelMessageDispatcher.dispatch_message", new_callable=AsyncMock)
async def test_put_callback_url_shorten(mock_dispatch_message):
    req_body = {
        'key_1': 'value_1'
    }
    response = client.put('/callback/d/019170001814712f8921076fd134a083/98bxWFZL9nZy0L3lAKV2Qr_jI6iEQ6CpZq2vDnhQwQg',
                            json=req_body)
    assert response.status_code == 200
    assert response.json() == {"message": "success", "data": "hello -> {'type': 'PUT', 'body': {'key_1': 'value_1'}, 'params': {}}", "error_code": 0, "success": True}


@pytest.mark.asyncio
@patch("kairon.async_callback.channel_message_dispacher.ChannelMessageDispatcher.dispatch_message", new_callable=AsyncMock)
async def test_post_callback_standalone(mock_dispatch_message):
    req_body = {
        'data': {
            'id': '0191702183ca7ac6b75be9cd645c6437'
        }
    }
    response = client.post('/callback/s/gAAAAABmxKQ6lHtDmxTmr_X4nyUGEKL72ylRLODr4IAxsUVr3e9dx7ZTDSL0IlzvGCwLzSDrsyVqanSPSj6JB7srql3dH-rVb9KG6oAcW4yhsMJVP_WPa9sD5J7NqCcShJI3KgjjE7kAEkqqr0VqE2XCEwC7vUCjcYPasw2q4PhOCvg-_CMxT6gC8ZQL7vUVi74FdOnNTQhfiOvXp4ggeV_Jq-xer_-8gTnsplM_nZ_HRxns45gGzAyvtwsUWYnWOPleh6HQn1rgmjfS1hQuYmR7JGxgZDFDZA==',
                            json=req_body)
    assert response.status_code == 200
    assert response.json() == {"message": "success", "data": "standalone -> {'type': 'POST', 'body': {'data': {'id': '0191702183ca7ac6b75be9cd645c6437'}}, 'params': {}}", "error_code": 0, "success": True}


@pytest.mark.asyncio
@patch("kairon.async_callback.channel_message_dispacher.ChannelMessageDispatcher.dispatch_message", new_callable=AsyncMock)
async def test_post_callback_standalone_identifier_path_not_present(mock_dispatch_message):
    req_body = {
        'data': {
            'idea': '0191702183ca7ac6b75be9cd645c6437'
        }
    }
    response = client.post('/callback/s/gAAAAABmxKQ6lHtDmxTmr_X4nyUGEKL72ylRLODr4IAxsUVr3e9dx7ZTDSL0IlzvGCwLzSDrsyVqanSPSj6JB7srql3dH-rVb9KG6oAcW4yhsMJVP_WPa9sD5J7NqCcShJI3KgjjE7kAEkqqr0VqE2XCEwC7vUCjcYPasw2q4PhOCvg-_CMxT6gC8ZQL7vUVi74FdOnNTQhfiOvXp4ggeV_Jq-xer_-8gTnsplM_nZ_HRxns45gGzAyvtwsUWYnWOPleh6HQn1rgmjfS1hQuYmR7JGxgZDFDZA==',
                            json=req_body)
    assert response.status_code == 200
    assert response.json() == {"message": "Cannot find identifier at path 'data.id' in request data!", "data": None, "error_code": 400, "success": False}


@pytest.mark.asyncio
@patch("kairon.async_callback.channel_message_dispacher.ChannelMessageDispatcher.dispatch_message", new_callable=AsyncMock)
async def test_post_callback_standalone_wrong_identifier(mock_dispatch_message):
    req_body = {
        'data': {
            'id': '0191702183ca7ac6b75be9cd645c6438'
        }
    }
    response = client.post('/callback/s/gAAAAABmxKQ6lHtDmxTmr_X4nyUGEKL72ylRLODr4IAxsUVr3e9dx7ZTDSL0IlzvGCwLzSDrsyVqanSPSj6JB7srql3dH-rVb9KG6oAcW4yhsMJVP_WPa9sD5J7NqCcShJI3KgjjE7kAEkqqr0VqE2XCEwC7vUCjcYPasw2q4PhOCvg-_CMxT6gC8ZQL7vUVi74FdOnNTQhfiOvXp4ggeV_Jq-xer_-8gTnsplM_nZ_HRxns45gGzAyvtwsUWYnWOPleh6HQn1rgmjfS1hQuYmR7JGxgZDFDZA==',
                            json=req_body)
    assert response.status_code == 200
    assert response.json() == {"message": "Callback Record does not exist, invalid identifier!", "data": None, "error_code": 400, "success": False}

@pytest.mark.asyncio
@patch("kairon.async_callback.channel_message_dispacher.ChannelMessageDispatcher.dispatch_message", new_callable=AsyncMock)
async def test_post_callback_standalone_url_shorten(mock_dispatch_message):
    req_body = {
        'data': {
            'id': '01917036016877eb8ffb3930e40f6162'
        }
    }
    response = client.post('/callback/s/98bxWFcdoyN30eO5APd2Fb_ocqmBE_f7ZqinBXgElg8',
                            json=req_body)
    assert response.status_code == 200
    assert response.json() == {"message": "success", "data": "state -> 1", "error_code": 0, "success": True}

@pytest.mark.asyncio
@patch("kairon.async_callback.channel_message_dispacher.ChannelMessageDispatcher.dispatch_message", new_callable=AsyncMock)
async def test_post_callback_standalone_url_shorten_wrong_url(mock_dispatch_message):
    req_body = {
        'data': {
            'id': '01917036016877eb8ffb3930e40f6162'
        }
    }
    response = client.post('/callback/s/VQEBBAYGV1EPD19eB1UHVgsBAw5SBQEGAAIJCwGVBlK=',
                            json=req_body)
    assert response.status_code == 200
    assert response.json() == {"message": "Invalid token!", "data": None, "error_code": 400, "success": False}


@pytest.mark.asyncio
@patch("kairon.async_callback.channel_message_dispacher.ChannelMessageDispatcher.dispatch_message", new_callable=AsyncMock)
async def test_post_callback_statechange(mock_dispatch_message):
    req_body = {
        'data': {
            'id': '01917036016877eb8ffb3930e40f6162'
        }
    }
    response = client.post('/callback/s/98bxWFcdoyN30eO5APd2Fb_ocqmBE_f7ZqinBXgElg8',
                            json=req_body)
    assert response.status_code == 200
    assert response.json() == {"message": "success", "data": "state -> 1", "error_code": 0, "success": True}

    response = client.post('/callback/s/98bxWFcdoyN30eO5APd2Fb_ocqmBE_f7ZqinBXgElg8',
                            json=req_body)
    assert response.status_code == 200
    assert response.json() == {"message": "success", "data": "state -> 2", "error_code": 0, "success": True}

    response = client.post('/callback/s/98bxWFcdoyN30eO5APd2Fb_ocqmBE_f7ZqinBXgElg8',
                            json=req_body)
    assert response.status_code == 200
    assert response.json() == {"message": "success", "data": "state -> 3", "error_code": 0, "success": True}
