import json
from datetime import datetime, timedelta
import os

import pytest
from unittest.mock import patch, AsyncMock

from httpx import QueryParams
from jose import jwt
from mongoengine import connect
from blacksheep.contents import JSONContent
from requests import Request

from kairon import Utility
from fastapi.testclient import TestClient
from blacksheep.testing import TestClient
from kairon.shared.callback.data_objects import CallbackData, CallbackConfig, encrypt_secret
from kairon.shared.auth import Authentication

from kairon.async_callback.main import app

from kairon.async_callback.router.pyscript_callback import process_router_message
from kairon.exceptions import AppException


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
                         "validation_secret": encrypt_secret("0191693df8f972529fc22d83413f19b1"),
                         "execution_mode": "sync", "bot": "6697add6b8e47524eb983373"}
    callback_config_2 = {"name": "callback_script3",
                         "pyscript_code": "bot_response = f\"{req} {metadata['happy']}\"",
                         "validation_secret": encrypt_secret("0191693df8f972529fc22d83413f19b1"),
                         "execution_mode": "async", "bot": "6697add6b8e47524eb983373"}

    callback_config_3 = {
        "name": "callback_script4",
        "pyscript_code": "bot_response = f'hello -> {req}'",
        "validation_secret": encrypt_secret("01916febcbe67a8a9a151842320697d2"),
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
        "validation_secret": encrypt_secret("01916ffe298b7c1bb951ef9c9cbd1d74"),
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
        "validation_secret": encrypt_secret("0191702079f47e4392f3bd4460d95409"),
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
        "validation_secret": encrypt_secret("0191703078f779199d90c1a91fe9839f"),
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


@pytest.mark.asyncio
async def test_index():
    await app.start()
    client = TestClient(app)
    response = await client.get("/")
    json_response = await response.json()
    print(json_response)
    assert json_response["success"]
    assert not json_response["data"]
    assert json_response["message"] == "Running BlackSheep Async Callback Server"
    assert json_response["error_code"] == 0


@pytest.mark.asyncio
async def test_healthcheck():
    await app.start()
    client = TestClient(app)
    response = await client.get("/healthcheck")

    json_response = await response.json()
    print(json_response)
    assert json_response["success"]
    assert not json_response["data"]
    assert json_response["message"] == "Health check OK"
    assert json_response["error_code"] == 0


@pytest.mark.asyncio
@patch("kairon.async_callback.channel_message_dispacher.ChannelMessageDispatcher.dispatch_message",
       new_callable=AsyncMock)
async def test_get_callback(mock_dispatch_message):
    await app.start()
    client = TestClient(app)
    response = await client.get(
        '/callback/d/01916940879576a391a0cd1223fa8684/gAAAAABmwuGEYHfCz1vYBH9cp8KVcB0Pf9y5c6N3IOYIw8y0A-m4dX2gE9VW-1c9yLAK-ZKXVODp58jmSfhyeI03yUkLR1kqZUNPk_qNRIKROMXMV-wKDbqAtWOwXBXM5EVbWNj6YHCyZKwJgrGidGSjpt7UrDnprr_rmDexgCssfag_5xEtrHzVSziDEZSDCHxupAJZ_l1AA8SkxwVpqgxLdt1Nu1r2SjyZaMvtt4TFYCKYIO6CeMfgShbEqcqHeonfox_UCbhPA68RNWWHhsoHh5o66fm94A==')
    assert response.status == 200
    json_response = await response.json()
    assert json_response["success"]
    assert "i am happy : )" in json_response["data"]
    assert json_response["message"] == "success"
    assert json_response["error_code"] == 0
    assert mock_dispatch_message.called_once()


@pytest.mark.asyncio
@patch("kairon.async_callback.channel_message_dispacher.ChannelMessageDispatcher.dispatch_message",
       new_callable=AsyncMock)
async def test_get_callback_response_type(mock_dispatch_message):
    await app.start()
    client = TestClient(app)
    callback = CallbackConfig.objects(name='callback_script2', bot='6697add6b8e47524eb983373').get()
    callback.response_type = 'text'
    callback.save()

    response = await client.get(
        '/callback/d/01916940879576a391a0cd1223fa8684/gAAAAABmwuGEYHfCz1vYBH9cp8KVcB0Pf9y5c6N3IOYIw8y0A-m4dX2gE9VW-1c9yLAK-ZKXVODp58jmSfhyeI03yUkLR1kqZUNPk_qNRIKROMXMV-wKDbqAtWOwXBXM5EVbWNj6YHCyZKwJgrGidGSjpt7UrDnprr_rmDexgCssfag_5xEtrHzVSziDEZSDCHxupAJZ_l1AA8SkxwVpqgxLdt1Nu1r2SjyZaMvtt4TFYCKYIO6CeMfgShbEqcqHeonfox_UCbhPA68RNWWHhsoHh5o66fm94A==')
    assert response.status == 200
    json_response = await response.text()
    assert "i am happy : )" in json_response
    assert "{'type': 'GET', 'body': None" in json_response
    assert mock_dispatch_message.called_once()
    callback.response_type = 'json'
    callback.pyscript_code = "bot_response={'arr': [1,2,3]}"
    callback.save()

    response = await client.get(
        '/callback/d/01916940879576a391a0cd1223fa8684/gAAAAABmwuGEYHfCz1vYBH9cp8KVcB0Pf9y5c6N3IOYIw8y0A-m4dX2gE9VW-1c9yLAK-ZKXVODp58jmSfhyeI03yUkLR1kqZUNPk_qNRIKROMXMV-wKDbqAtWOwXBXM5EVbWNj6YHCyZKwJgrGidGSjpt7UrDnprr_rmDexgCssfag_5xEtrHzVSziDEZSDCHxupAJZ_l1AA8SkxwVpqgxLdt1Nu1r2SjyZaMvtt4TFYCKYIO6CeMfgShbEqcqHeonfox_UCbhPA68RNWWHhsoHh5o66fm94A==')
    assert response.status == 200
    json_response = await response.json()
    assert json_response == {'arr': [1, 2, 3]}

    callback.response_type = 'kairon_json'
    callback.pyscript_code = "bot_response = f\"{req} {metadata['happy']}\""
    callback.save()


@pytest.mark.asyncio
@patch("kairon.async_callback.channel_message_dispacher.ChannelMessageDispatcher.dispatch_message",
       new_callable=AsyncMock)
async def test_post_callback(mock_dispatch_message):
    await app.start()
    client = TestClient(app)
    req_body = {
        'key_1': 'value_1'
    }

    response = await client.post(
        '/callback/d/01916940879576a391a0cd1223fa8684/gAAAAABmwuGEYHfCz1vYBH9cp8KVcB0Pf9y5c6N3IOYIw8y0A-m4dX2gE9VW-1c9yLAK-ZKXVODp58jmSfhyeI03yUkLR1kqZUNPk_qNRIKROMXMV-wKDbqAtWOwXBXM5EVbWNj6YHCyZKwJgrGidGSjpt7UrDnprr_rmDexgCssfag_5xEtrHzVSziDEZSDCHxupAJZ_l1AA8SkxwVpqgxLdt1Nu1r2SjyZaMvtt4TFYCKYIO6CeMfgShbEqcqHeonfox_UCbhPA68RNWWHhsoHh5o66fm94A==',
        content=JSONContent(req_body))
    json_response = await response.json()
    assert json_response["success"]
    assert "'type': 'POST', 'body': {'key_1': 'value_1'}" in json_response["data"]
    assert json_response["message"] == "success"
    assert json_response["error_code"] == 0
    assert mock_dispatch_message.called_once()


@pytest.mark.asyncio
@patch("kairon.async_callback.channel_message_dispacher.ChannelMessageDispatcher.dispatch_message",
       new_callable=AsyncMock)
async def test_post_callback_req_body_non_json(mock_dispatch_message):
    await app.start()
    client = TestClient(app)
    req_body = "key_1=value_1"
    response = await client.post(
        '/callback/d/01916940879576a391a0cd1223fa8684/gAAAAABmwuGEYHfCz1vYBH9cp8KVcB0Pf9y5c6N3IOYIw8y0A-m4dX2gE9VW-1c9yLAK-ZKXVODp58jmSfhyeI03yUkLR1kqZUNPk_qNRIKROMXMV-wKDbqAtWOwXBXM5EVbWNj6YHCyZKwJgrGidGSjpt7UrDnprr_rmDexgCssfag_5xEtrHzVSziDEZSDCHxupAJZ_l1AA8SkxwVpqgxLdt1Nu1r2SjyZaMvtt4TFYCKYIO6CeMfgShbEqcqHeonfox_UCbhPA68RNWWHhsoHh5o66fm94A==',
        content=JSONContent(req_body))
    json_response = await response.json()
    print(json_response)
    assert json_response["success"]
    assert "'type': 'POST', 'body': 'key_1=value_1'" in json_response["data"]
    assert json_response["message"] == "success"
    assert json_response["error_code"] == 0
    assert mock_dispatch_message.called_once()


@pytest.mark.asyncio
@patch("kairon.async_callback.channel_message_dispacher.ChannelMessageDispatcher.dispatch_message",
       new_callable=AsyncMock)
async def test_put_callback(mock_dispatch_message):
    await app.start()
    client = TestClient(app)
    response = await client.put(
        '/callback/d/01916940879576a391a0cd1223fa8684/gAAAAABmwuGEYHfCz1vYBH9cp8KVcB0Pf9y5c6N3IOYIw8y0A-m4dX2gE9VW-1c9yLAK-ZKXVODp58jmSfhyeI03yUkLR1kqZUNPk_qNRIKROMXMV-wKDbqAtWOwXBXM5EVbWNj6YHCyZKwJgrGidGSjpt7UrDnprr_rmDexgCssfag_5xEtrHzVSziDEZSDCHxupAJZ_l1AA8SkxwVpqgxLdt1Nu1r2SjyZaMvtt4TFYCKYIO6CeMfgShbEqcqHeonfox_UCbhPA68RNWWHhsoHh5o66fm94A==')

    json_response = await response.json()
    print(json_response)
    assert json_response["success"]
    assert "'type': 'PUT', 'body': None," in json_response["data"]
    assert json_response["message"] == "success"
    assert json_response["error_code"] == 0
    assert mock_dispatch_message.called_once()


@pytest.mark.asyncio
@patch("kairon.async_callback.channel_message_dispacher.ChannelMessageDispatcher.dispatch_message",
       new_callable=AsyncMock)
async def test_patch_callback(mock_dispatch_message):
    await app.start()
    client = TestClient(app)
    response = await client.patch(
        '/callback/d/01916940879576a391a0cd1223fa8684/gAAAAABmwuGEYHfCz1vYBH9cp8KVcB0Pf9y5c6N3IOYIw8y0A-m4dX2gE9VW-1c9yLAK-ZKXVODp58jmSfhyeI03yUkLR1kqZUNPk_qNRIKROMXMV-wKDbqAtWOwXBXM5EVbWNj6YHCyZKwJgrGidGSjpt7UrDnprr_rmDexgCssfag_5xEtrHzVSziDEZSDCHxupAJZ_l1AA8SkxwVpqgxLdt1Nu1r2SjyZaMvtt4TFYCKYIO6CeMfgShbEqcqHeonfox_UCbhPA68RNWWHhsoHh5o66fm94A==')

    json_response = await response.json()
    print(json_response)
    assert json_response["success"]
    assert "'type': 'PATCH'," in json_response["data"]
    assert json_response["message"] == "success"
    assert json_response["error_code"] == 0
    assert mock_dispatch_message.called_once()


@pytest.mark.asyncio
@patch("kairon.async_callback.channel_message_dispacher.ChannelMessageDispatcher.dispatch_message",
       new_callable=AsyncMock)
async def test_delete_callback(mock_dispatch_message):
    await app.start()
    client = TestClient(app)
    response = await client.delete(
        '/callback/d/01916940879576a391a0cd1223fa8684/gAAAAABmwuGEYHfCz1vYBH9cp8KVcB0Pf9y5c6N3IOYIw8y0A-m4dX2gE9VW-1c9yLAK-ZKXVODp58jmSfhyeI03yUkLR1kqZUNPk_qNRIKROMXMV-wKDbqAtWOwXBXM5EVbWNj6YHCyZKwJgrGidGSjpt7UrDnprr_rmDexgCssfag_5xEtrHzVSziDEZSDCHxupAJZ_l1AA8SkxwVpqgxLdt1Nu1r2SjyZaMvtt4TFYCKYIO6CeMfgShbEqcqHeonfox_UCbhPA68RNWWHhsoHh5o66fm94A==')

    json_response = await response.json()
    print(json_response)
    assert json_response["success"]
    assert "{'type': 'DELETE', 'body': None, 'params': {}" in json_response["data"]
    assert json_response["message"] == "success"
    assert json_response["error_code"] == 0
    assert mock_dispatch_message.called_once_with("6697add6b8e47524eb983373", "5489844732",
                                                  "{'type': 'DELETE', 'body': None, 'params': {}} i am happy : )",
                                                  "telegram")


@pytest.mark.asyncio
async def test_invalid_request():
    with pytest.raises(AppException):
        await process_router_message("test_bot", "test_name", "test_param", request=None)


@pytest.mark.asyncio
async def test_request_fallback_to_text():
    mock_request = AsyncMock(spec=Request)
    mock_request.json = AsyncMock(side_effect=Exception("JSON decode error"))
    mock_request.read = AsyncMock(return_value=b"test body content")
    mock_request.query = QueryParams({})
    mock_request.scope = {"client": ["127.0.0.1"]}
    with patch("kairon.async_callback.processor.CallbackProcessor.process_async_callback_request",
               new=AsyncMock(return_value=({}, "Success", 0, 'kairon_json'))):
        response = await process_router_message("valid_token", "test_name", "GET", request=mock_request)
    response_json = await response.json()
    assert response_json["success"] is True
    assert response_json["message"] == 'Success'


@pytest.mark.asyncio
@patch("kairon.async_callback.processor.CallbackProcessor.run_pyscript_async", new_callable=AsyncMock)
@patch("kairon.async_callback.channel_message_dispacher.ChannelMessageDispatcher.dispatch_message",
       new_callable=AsyncMock)
async def test_async_callback(mock_dispatch_message, mock_run_pyscript_async):
    await app.start()
    client = TestClient(app)
    response = await client.get(
        '/callback/d/01916fefd1897634ad82274af4a7ecde/gAAAAABmxJeByymLTcvGh3ZcnUVSeh6hZrEV2EAVfBmMm1X5lDgjaSSp4E6h9LiqBE34uRgriOLU2ZRkBoKkg7w_pbq6cQ6OC_afnHagr99xNyBfnvzfXMujGCVNnNSGnPnlVYlN_TBK66QoaDVt1o6Mp4b1kJYyBE1I-Avq69Mj-5IRA2D0KP2r80kTWGWIGzbGVwPlWtsqTQtGj-gLl_O9eKJ0s5i-XlZC5Ge0B2P-EUsXqAA_G2tlDMOjpk0g9ppUiRXt4KYiW2ZQ6MdrJTJDY2ohydYnLw==')

    json_response = await response.json()
    print(json_response)
    assert json_response["success"]
    assert not json_response["data"]
    assert json_response["message"] == "success"
    assert json_response["error_code"] == 0
    assert json_response == {"message": "success", "data": None, "error_code": 0, "success": True}
    assert mock_run_pyscript_async.called_once()
    assert mock_dispatch_message.called_once()


@pytest.mark.asyncio
@patch("kairon.async_callback.processor.CallbackProcessor.run_pyscript")
@patch("kairon.async_callback.channel_message_dispacher.ChannelMessageDispatcher.dispatch_message",
       new_callable=AsyncMock)
async def test_pyscript_failure(mock_dispatch_message, mock_run_pyscript):
    await app.start()
    client = TestClient(app)
    mock_run_pyscript.side_effect = AppException("Error")
    response = await client.get(
        '/callback/d/01916940879576a391a0cd1223fa8684/gAAAAABmwuGEYHfCz1vYBH9cp8KVcB0Pf9y5c6N3IOYIw8y0A-m4dX2gE9VW-1c9yLAK-ZKXVODp58jmSfhyeI03yUkLR1kqZUNPk_qNRIKROMXMV-wKDbqAtWOwXBXM5EVbWNj6YHCyZKwJgrGidGSjpt7UrDnprr_rmDexgCssfag_5xEtrHzVSziDEZSDCHxupAJZ_l1AA8SkxwVpqgxLdt1Nu1r2SjyZaMvtt4TFYCKYIO6CeMfgShbEqcqHeonfox_UCbhPA68RNWWHhsoHh5o66fm94A==')

    json_response = await response.json()
    print(json_response)
    assert not json_response["success"]
    assert not json_response["data"]
    assert json_response["message"] == "Error"
    assert json_response["error_code"] == 400
    assert json_response == {"message": "Error", "error_code": 400, "success": False, "data": None}
    assert mock_run_pyscript.called_once()
    assert mock_dispatch_message.called_once()


@pytest.mark.asyncio
@patch("kairon.async_callback.processor.CallbackProcessor.run_pyscript")
@patch("kairon.async_callback.channel_message_dispacher.ChannelMessageDispatcher.dispatch_message",
       new_callable=AsyncMock)
async def test_dispatch_message_failure(mock_dispatch_message, mock_run_pyscript):
    await app.start()
    client = TestClient(app)
    mock_dispatch_message.side_effect = AppException("Error")
    response = await client.get(
        '/callback/d/01916940879576a391a0cd1223fa8684/gAAAAABmwuGEYHfCz1vYBH9cp8KVcB0Pf9y5c6N3IOYIw8y0A-m4dX2gE9VW-1c9yLAK-ZKXVODp58jmSfhyeI03yUkLR1kqZUNPk_qNRIKROMXMV-wKDbqAtWOwXBXM5EVbWNj6YHCyZKwJgrGidGSjpt7UrDnprr_rmDexgCssfag_5xEtrHzVSziDEZSDCHxupAJZ_l1AA8SkxwVpqgxLdt1Nu1r2SjyZaMvtt4TFYCKYIO6CeMfgShbEqcqHeonfox_UCbhPA68RNWWHhsoHh5o66fm94A==')

    result = await response.json()
    assert result["error_code"] == 400
    assert not result["success"]
    assert mock_run_pyscript.called_once()
    assert mock_dispatch_message.called_once()


@pytest.mark.asyncio
@patch("kairon.async_callback.channel_message_dispacher.ChannelMessageDispatcher.dispatch_message",
       new_callable=AsyncMock)
async def test_get_callback_url_shorten(mock_dispatch_message):
    await app.start()
    client = TestClient(app)
    response = await client.get(
        '/callback/d/019170001814712f8921076fd134a083/98bxWFZL9nZy0L3lAKV2Qr_jI6iEQ6CpZq2vDnhQwQg')

    json_response = await response.json()
    print(json_response)
    assert json_response["success"]
    assert "hello -> {'type': 'GET', 'body': None, 'params': {}" in json_response["data"]
    assert "headers" in json_response["data"]
    assert json_response["message"] == "success"
    assert json_response["error_code"] == 0


@pytest.mark.asyncio
@patch("kairon.async_callback.channel_message_dispacher.ChannelMessageDispatcher.dispatch_message",
       new_callable=AsyncMock)
async def test_post_callback_url_shorten(mock_dispatch_message):
    await app.start()
    client = TestClient(app)
    req_body = {
        'key_1': 'value_1'
    }
    response = await client.post(
        '/callback/d/019170001814712f8921076fd134a083/98bxWFZL9nZy0L3lAKV2Qr_jI6iEQ6CpZq2vDnhQwQg',
        content=JSONContent(req_body))
    json_response = await response.json()
    print(json_response)
    assert json_response["success"]
    assert "hello -> {'type': 'POST', 'body': {'key_1': 'value_1'}" in json_response["data"]
    assert "headers" in json_response["data"]
    assert json_response["message"] == "success"
    assert json_response["error_code"] == 0


@pytest.mark.asyncio
@patch("kairon.async_callback.channel_message_dispacher.ChannelMessageDispatcher.dispatch_message",
       new_callable=AsyncMock)
async def test_put_callback_url_shorten(mock_dispatch_message):
    await app.start()
    client = TestClient(app)
    req_body = {
        'key_1': 'value_1'
    }
    response = await client.put(
        '/callback/d/019170001814712f8921076fd134a083/98bxWFZL9nZy0L3lAKV2Qr_jI6iEQ6CpZq2vDnhQwQg',
        content=JSONContent(req_body))
    json_response = await response.json()
    print(json_response)
    assert json_response["success"]
    assert "hello -> {'type': 'PUT', 'body': {'key_1': 'value_1'}" in json_response["data"]
    assert json_response["message"] == "success"
    assert json_response["error_code"] == 0


@pytest.mark.asyncio
@patch("kairon.async_callback.channel_message_dispacher.ChannelMessageDispatcher.dispatch_message",
       new_callable=AsyncMock)
async def test_post_callback_standalone(mock_dispatch_message):
    await app.start()
    client = TestClient(app)
    req_body = {
        'data': {
            'id': '0191702183ca7ac6b75be9cd645c6437'
        }
    }
    response = await client.post(
        '/callback/s/gAAAAABmxKQ6lHtDmxTmr_X4nyUGEKL72ylRLODr4IAxsUVr3e9dx7ZTDSL0IlzvGCwLzSDrsyVqanSPSj6JB7srql3dH-rVb9KG6oAcW4yhsMJVP_WPa9sD5J7NqCcShJI3KgjjE7kAEkqqr0VqE2XCEwC7vUCjcYPasw2q4PhOCvg-_CMxT6gC8ZQL7vUVi74FdOnNTQhfiOvXp4ggeV_Jq-xer_-8gTnsplM_nZ_HRxns45gGzAyvtwsUWYnWOPleh6HQn1rgmjfS1hQuYmR7JGxgZDFDZA==',
        content=JSONContent(req_body))
    json_response = await response.json()
    print(json_response)
    assert json_response["success"]
    assert "standalone -> {'type': 'POST', 'body': {'data': {'id': '0191702183ca7ac6b75be9cd645c6437'}}" in \
           json_response["data"]
    assert json_response["message"] == "success"
    assert json_response["error_code"] == 0


@pytest.mark.asyncio
@patch("kairon.async_callback.channel_message_dispacher.ChannelMessageDispatcher.dispatch_message",
       new_callable=AsyncMock)
async def test_post_callback_standalone_identifier_path_not_present(mock_dispatch_message):
    await app.start()
    client = TestClient(app)
    req_body = {
        'data': {
            'idea': '0191702183ca7ac6b75be9cd645c6437'
        }
    }
    response = await client.post(
        '/callback/s/gAAAAABmxKQ6lHtDmxTmr_X4nyUGEKL72ylRLODr4IAxsUVr3e9dx7ZTDSL0IlzvGCwLzSDrsyVqanSPSj6JB7srql3dH-rVb9KG6oAcW4yhsMJVP_WPa9sD5J7NqCcShJI3KgjjE7kAEkqqr0VqE2XCEwC7vUCjcYPasw2q4PhOCvg-_CMxT6gC8ZQL7vUVi74FdOnNTQhfiOvXp4ggeV_Jq-xer_-8gTnsplM_nZ_HRxns45gGzAyvtwsUWYnWOPleh6HQn1rgmjfS1hQuYmR7JGxgZDFDZA==',
        content=JSONContent(req_body))
    json_response = await response.json()
    print(json_response)
    assert not json_response["success"]
    assert json_response["message"] == "Cannot find identifier at path 'data.id' in request data!"
    assert json_response["error_code"] == 422
    assert not json_response["data"]
    assert json_response == {'message': "Cannot find identifier at path 'data.id' in request data!",
                             'error_code': 422, 'data': None, 'success': False}


@pytest.mark.asyncio
@patch("kairon.async_callback.channel_message_dispacher.ChannelMessageDispatcher.dispatch_message",
       new_callable=AsyncMock)
async def test_post_callback_standalone_wrong_identifier(mock_dispatch_message):
    await app.start()
    client = TestClient(app)
    req_body = {
        'data': {
            'id': '0191702183ca7ac6b75be9cd645c6438'
        }
    }
    response = await client.post(
        '/callback/s/gAAAAABmxKQ6lHtDmxTmr_X4nyUGEKL72ylRLODr4IAxsUVr3e9dx7ZTDSL0IlzvGCwLzSDrsyVqanSPSj6JB7srql3dH-rVb9KG6oAcW4yhsMJVP_WPa9sD5J7NqCcShJI3KgjjE7kAEkqqr0VqE2XCEwC7vUCjcYPasw2q4PhOCvg-_CMxT6gC8ZQL7vUVi74FdOnNTQhfiOvXp4ggeV_Jq-xer_-8gTnsplM_nZ_HRxns45gGzAyvtwsUWYnWOPleh6HQn1rgmjfS1hQuYmR7JGxgZDFDZA==',
        content=JSONContent(req_body))
    json_response = await response.json()
    print(json_response)
    assert not json_response["success"]
    assert json_response["message"] == "Callback Record does not exist, invalid identifier!"
    assert json_response["error_code"] == 400
    assert not json_response["data"]
    assert json_response == {'message': 'Callback Record does not exist, invalid identifier!',
                             'error_code': 400, 'data': None, 'success': False}


@pytest.mark.asyncio
@patch("kairon.async_callback.channel_message_dispacher.ChannelMessageDispatcher.dispatch_message",
       new_callable=AsyncMock)
async def test_post_callback_standalone_url_shorten(mock_dispatch_message):
    await app.start()
    client = TestClient(app)
    req_body = {
        'data': {
            'id': '01917036016877eb8ffb3930e40f6162'
        }
    }
    response = await client.post('/callback/s/98bxWFcdoyN30eO5APd2Fb_ocqmBE_f7ZqinBXgElg8',
                                 content=JSONContent(req_body))
    json_response = await response.json()
    print(json_response)
    assert json_response["success"]
    assert json_response["data"] == "state -> 1"
    assert json_response["message"] == "success"
    assert json_response["error_code"] == 0
    assert json_response == {"message": "success", "data": "state -> 1", "error_code": 0, "success": True}


@pytest.mark.asyncio
@patch("kairon.async_callback.channel_message_dispacher.ChannelMessageDispatcher.dispatch_message",
       new_callable=AsyncMock)
async def test_post_callback_standalone_url_shorten_wrong_url(mock_dispatch_message):
    await app.start()
    client = TestClient(app)
    req_body = {
        'data': {
            'id': '01917036016877eb8ffb3930e40f6162'
        }
    }
    response = await client.post('/callback/s/VQEBBAYGV1EPD19eB1UHVgsBAw5SBQEGAAIJCwGVBlK=',
                                 content=JSONContent(req_body))
    json_response = await response.json()
    print(json_response)
    assert not json_response["success"]
    assert json_response["message"] == "Invalid token!"
    assert json_response["error_code"] == 400
    assert not json_response["data"]
    assert json_response == {"message": "Invalid token!", "data": None, "error_code": 400, "success": False}


@pytest.mark.asyncio
@patch("kairon.async_callback.channel_message_dispacher.ChannelMessageDispatcher.dispatch_message",
       new_callable=AsyncMock)
async def test_post_callback_statechange(mock_dispatch_message):
    await app.start()
    client = TestClient(app)
    req_body = {
        'data': {
            'id': '01917036016877eb8ffb3930e40f6162'
        }
    }
    response = await client.post('/callback/s/98bxWFcdoyN30eO5APd2Fb_ocqmBE_f7ZqinBXgElg8',
                                 content=JSONContent(req_body))
    json_response = await response.json()
    print(json_response)
    assert json_response["success"]
    assert json_response["message"] == "success"
    assert json_response["error_code"] == 0
    assert json_response["data"] == 'state -> 1'
    assert json_response == {"message": "success", "data": "state -> 1", "error_code": 0, "success": True}

    response = await client.post('/callback/s/98bxWFcdoyN30eO5APd2Fb_ocqmBE_f7ZqinBXgElg8',
                                 content=JSONContent(req_body))
    json_response = await response.json()
    print(json_response)
    assert json_response["success"]
    assert json_response["message"] == "success"
    assert json_response["error_code"] == 0
    assert json_response["data"] == 'state -> 2'
    assert json_response == {"message": "success", "data": "state -> 2", "error_code": 0, "success": True}

    response = await client.post('/callback/s/98bxWFcdoyN30eO5APd2Fb_ocqmBE_f7ZqinBXgElg8',
                                 content=JSONContent(req_body))
    json_response = await response.json()
    print(json_response)
    assert json_response["success"]
    assert json_response["message"] == "success"
    assert json_response["error_code"] == 0
    assert json_response["data"] == 'state -> 3'
    assert json_response == {"message": "success", "data": "state -> 3", "error_code": 0, "success": True}


@pytest.mark.asyncio
@patch("kairon.async_callback.utils.CallbackUtility.main_pyscript_handler")
async def test_execute_python_success(mock_handler):
    await app.start()
    client = TestClient(app)

    payload = {
        "source_code": "bot_response=100",
        "predefined_objects": {"x": 1}
    }

    # Simulate response from handler
    mock_handler.return_value = {"output": "Execution successful", "success": True}

    response = await client.post("/main_pyscript/execute-python", content=JSONContent(payload))
    json_response = await response.json()
    print(json_response)

    assert response.status == 200
    assert json_response["output"] == "Execution successful"
    assert json_response["success"] is True


@pytest.mark.asyncio
@patch("kairon.async_callback.utils.CallbackUtility.main_pyscript_handler")
async def test_execute_python_failure(mock_handler):
    await app.start()
    client = TestClient(app)

    payload = {
        "source_code": "raise Exception('fail')",
        "predefined_objects": {}
    }

    # Simulate exception from handler
    mock_handler.side_effect = Exception("Restricted execution error")
    print(app.router.routes)
    response = await client.post("/main_pyscript/execute-python", content=JSONContent(payload))
    json_response = await response.json()
    print(json_response)

    assert response.status == 422
    assert json_response["success"] is False


SECRET_KEY = Utility.environment['security']["secret_key"]
ALGORITHM = Utility.environment['security']["algorithm"]
from kairon.shared.data.constant import TOKEN_TYPE

@pytest.mark.asyncio
@patch("kairon.async_callback.utils.CallbackUtility.execute_script")
async def test_handle_callback_success(mock_execute, monkeypatch):
    mock_execute.return_value = {"result": "ok", "details": {"x": 1}}

    # Generate encrypted token claims and extract only the encrypted string
    claims = Authentication.encrypt_token_claims({"type": TOKEN_TYPE.DYNAMIC.value})
    token = jwt.encode({"sub": claims["sub"]}, SECRET_KEY, algorithm=ALGORITHM)

    client = TestClient(app)
    await app.start()

    request_payload = {
        "event_class": "scheduler_evaluator",
        "data": {
            "source_code": "bot_response = 42",
            "predefined_objects": {"x": 1}
        },
        "task_type": "Callback"
    }

    headers = {
        "Authorization": f"Bearer {token}"
    }

    response = await client.post(
        "/callback/handle_event",
        headers=headers,
        content=JSONContent(request_payload),
    )

    body = await response.json()
    assert body["statusCode"] == 200
    assert body["body"] == {"result": "ok", "details": {"x": 1}}


@pytest.mark.asyncio
@patch("kairon.async_callback.utils.CallbackUtility.execute_script")
async def test_handle_callback_failure(mock_execute, monkeypatch):
    mock_execute.side_effect = Exception("script error")

    # Use datetime.utcnow() as expected by encrypt_token_claims
    exp = datetime.utcnow() + timedelta(minutes=5)
    token_claims = {
        "type": TOKEN_TYPE.DYNAMIC.value,
        "exp": exp
    }
    encrypted = Authentication.encrypt_token_claims(token_claims)

    # Construct token from encrypted claims
    token_payload = {
        "sub": encrypted["sub"],
        "exp": encrypted["exp"]  # already converted in encrypt_token_claims
    }

    token = jwt.encode(token_payload, SECRET_KEY, algorithm=ALGORITHM)

    client = TestClient(app)
    await app.start()

    request_payload = {
        "event_class": "scheduler_evaluator",
        "data": {
            "source_code": "raise Exception('fail')",
            "predefined_objects": {}
        },
        "task_type": "Callback"
    }

    response = await client.post(
        "/callback/handle_event",
        headers={"Authorization": f"Bearer {token}"},
        content=JSONContent(request_payload)
    )
    json_body = await response.json()
    print(json_body)
    assert json_body["statusCode"] == 422
    assert "script error" in json_body["body"]

@pytest.mark.asyncio
async def test_missing_authorization_header():
    client = TestClient(app)
    await app.start()
    valid_body_payload = {
        "event_class": "scheduler_evaluator",
        "data": {
            "source_code": "",
            "predefined_objects": {}
        },
        "task_type": "Callback"
    }

    response = await client.post("/callback/handle_event", content=JSONContent(valid_body_payload))
    body = await response.json()
    print(body)
    assert body == {"success": False,'error_code': 422, "error": "Missing Authorization header"}

@pytest.mark.asyncio
async def test_bad_authorization_header_format():
    client = TestClient(app)
    await app.start()
    headers = {"Authorization": "InvalidToken"}

    valid_body_payload = {
        "event_class": "scheduler_evaluator",
        "data": {
            "source_code": "",
            "predefined_objects": {}
        },
        "task_type": "Callback"
    }

    response = await client.post(
        "/callback/handle_event",
        headers=headers,
        content=JSONContent(valid_body_payload)
    )
    body = await response.json()
    print(body)
    assert body == {'success': False, 'error_code': 422, 'error': 'Bad Authorization header'}


@pytest.mark.asyncio
async def test_invalid_token_type(monkeypatch):
    claims = {"type": "wrong_type"}
    encrypted_claims = Authentication.encrypt_token_claims(claims)
    # Ensure it's string
    if not isinstance(encrypted_claims, str):
        encrypted_claims = json.dumps(encrypted_claims)

    payload = {
        "sub": encrypted_claims,
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    client = TestClient(app)
    await app.start()
    headers = {"Authorization": f"Bearer {token}"}

    valid_body_payload = {
        "event_class": "scheduler_evaluator",
        "data": {
            "source_code": "",
            "predefined_objects": {}
        },
        "task_type": "Callback"
    }

    response = await client.post("/callback/handle_event", headers=headers, content=JSONContent(valid_body_payload))
    body = await response.json()
    print(body)
    assert body["success"] is False
    assert body["error"].startswith("Token error:")

@pytest.mark.asyncio
async def test_expired_token(monkeypatch):
    expired_time = datetime.utcnow() - timedelta(hours=1)
    claims = {"type": TOKEN_TYPE.DYNAMIC.value, "exp": expired_time}
    encrypted_claims = Authentication.encrypt_token_claims(claims)
    payload = {"sub": encrypted_claims["sub"], "exp": int(expired_time.timestamp())}
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    client = TestClient(app)
    await app.start()
    headers = {"Authorization": f"Bearer {token}"}

    valid_body_payload = {
        "event_class": "scheduler_evaluator",
        "data": {
            "source_code": "",
            "predefined_objects": {}
        },
        "task_type": "Callback"
    }

    response = await client.post("/callback/handle_event", headers=headers, content=JSONContent(valid_body_payload))
    body = await response.json()
    print(body)
    assert body == {'success': False, 'error_code': 422, 'error': 'Token expired'}

@pytest.mark.asyncio
async def test_invalid_token(monkeypatch):
    token = "malformed.token.value"
    client = TestClient(app)
    await app.start()
    headers = {"Authorization": f"Bearer {token}"}

    valid_body_payload = {
        "event_class": "scheduler_evaluator",
        "data": {
            "source_code": "",
            "predefined_objects": {}
        },
        "task_type": "Callback"
    }

    response = await client.post("/callback/handle_event", headers=headers, content=JSONContent(valid_body_payload))
    body = await response.json()
    print(body)
    assert body["success"] is False
    assert body["error"].startswith("Token error:")

@pytest.mark.asyncio
@patch("kairon.async_callback.utils.CallbackUtility.execute_script")
async def test_successful_execution(mock_execute, monkeypatch):
    mock_execute.return_value = {"result": "ok", "details": {"x": 1}}
    claims = {"type": TOKEN_TYPE.DYNAMIC.value}
    encrypted_claims = Authentication.encrypt_token_claims(claims)
    payload = {"sub": encrypted_claims["sub"]}
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    client = TestClient(app)
    await app.start()
    headers = {"Authorization": f"Bearer {token}"}
    request_payload = {
        "event_class": "scheduler_evaluator",
        "data": {
            "source_code": "bot_response = 42",
            "predefined_objects": {"x": 1}
        },
        "task_type": "Callback"
    }

    response = await client.post(
        "/callback/handle_event",
        headers=headers,
        content=JSONContent(request_payload)
    )
    body = await response.json()
    print(body)
    assert body == {"statusCode": 200, "body": mock_execute.return_value}

@pytest.mark.asyncio
@patch("kairon.async_callback.utils.CallbackUtility.execute_script")
async def test_script_execution_failure(mock_execute, monkeypatch):
    mock_execute.side_effect = Exception("script error")
    claims = {"type": TOKEN_TYPE.DYNAMIC.value}
    encrypted_claims = Authentication.encrypt_token_claims(claims)
    payload = {"sub": encrypted_claims["sub"]}
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    client = TestClient(app)
    await app.start()
    headers = {"Authorization": f"Bearer {token}"}
    request_payload = {
        "event_class": "scheduler_evaluator",
        "data": {
            "source_code": "raise Exception('fail')",
            "predefined_objects": {}
        },
        "task_type": "Callback"
    }

    response = await client.post(
        "/callback/handle_event",
        headers=headers,
        content=JSONContent(request_payload)
    )
    body = await response.json()
    print(body)
    assert body["statusCode"] == 422
    assert "script error" in body["body"]