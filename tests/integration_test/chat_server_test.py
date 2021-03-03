import asyncio
import os
from urllib.parse import urljoin

import pytest
import mongomock
import responses
from mongoengine import connect
from rasa.core.agent import Agent

from kairon.api.data_objects import User, UserEmailConfirmation, Bot, Account
from kairon.chat_server.app import app
from kairon.chat_server.channels.channels import KaironChannels
from kairon.chat_server.channels.telegram import KaironTelegramClient
from kairon.chat_server.chat_server_utils import ChatServerUtils
from kairon.chat_server.processor import AgentProcessor

os.environ["chat_config_file"] = "./tests/testing_data/chat-config.yaml"
client = app.test_client()
access_token = None
token_type = None


def pytest_configure():
    return {'auth_token': None}


@pytest.fixture(autouse=True, scope='session')
def setup():
    os.environ["chat-config"] = "./tests/testing_data/chat-config.yaml"
    ChatServerUtils.load_evironment()
    connect(host=ChatServerUtils.environment['database']["url"])

    Bot(id="5ea8125db7c285f40551295c", name="5ea8125db7c285f40551295c", account=1, user="Admin").save()
    User(email="test@digite.com", first_name="test",
         last_name="user",
         password="$2b$12$mhxp/i29U1STS3ktERdIzOWigpgPtApOSjHdkMD/TtTcL0bu2SOna",
         role="admin",
         is_integration_user=False,
         account=1,
         bot="5ea8125db7c285f40551295c",
         user="Admin").save()
    UserEmailConfirmation(email="test@digite.com").save()
    Account(id=1, name="test", user="sysadmin").save()

    # expired token
    Bot(id="5ea8125db7c285f40551295d", name="5ea8125db7c285f40551295d", account=2, user="Admin").save()
    User(email="test_1@digite.com", first_name="test",
         last_name="user",
         password="$2b$12$mhxp/i29U1STS3ktERdIzOWigpgPtApOSjHdkMD/TtTcL0bu2SOna",
         role="admin",
         is_integration_user=False,
         account=2,
         bot="5ea8125db7c285f40551295d",
         user="Admin").save()
    UserEmailConfirmation(email="test_1@digite.com").save()
    Account(id=2, name="test", user="sysadmin").save()

    # deleted user
    Bot(id="5ea8125db7c285f40551296a", name="5ea8125db7c285f40551296a", account=5, user="Admin").save()
    User(email="test_5@digite.com", first_name="test",
         last_name="user",
         password="$2b$12$mhxp/i29U1STS3ktERdIzOWigpgPtApOSjHdkMD/TtTcL0bu2SOna",
         role="admin",
         is_integration_user=False,
         account=5,
         bot="5ea8125db7c285f40551296a",
         user="Admin",
         status=False).save()
    UserEmailConfirmation(email="test_4@digite.com").save()
    Account(id=5, name="test", user="sysadmin").save()

    # deleted bot
    Bot(id="5ea8125db7c285f40551295e", name="5ea8125db7c285f40551295e", account=3, user="Admin", status=False).save()
    User(email="test_2@digite.com", first_name="test",
         last_name="user",
         password="$2b$12$mhxp/i29U1STS3ktERdIzOWigpgPtApOSjHdkMD/TtTcL0bu2SOna",
         role="admin",
         is_integration_user=False,
         account=3,
         bot="5ea8125db7c285f40551295e",
         user="Admin").save()
    UserEmailConfirmation(email="test_2@digite.com").save()
    Account(id=3, name="test", user="sysadmin").save()

    # untrained bot
    Bot(id="5ea8125db7c285f40551295f", name="5ea8125db7c285f40551295f", account=4, user="Admin").save()
    User(email="test_3@digite.com", first_name="test",
         last_name="user",
         password="$2b$12$mhxp/i29U1STS3ktERdIzOWigpgPtApOSjHdkMD/TtTcL0bu2SOna",
         role="admin",
         is_integration_user=False,
         account=4,
         bot="5ea8125db7c285f40551295f",
         user="Admin").save()
    UserEmailConfirmation(email="test_3@digite.com").save()
    Account(id=4, name="test", user="sysadmin").save()

    pytest.auth_token = "Bearer " + ChatServerUtils.encode_auth_token("test@digite.com").decode("utf-8")


@pytest.fixture
def mock_agent_response(monkeypatch):
    def _get_agent(*args, **kwargs):
        return Agent

    def _agent_response(*args, **kwargs):
        future = asyncio.Future()
        future.set_result([{"recipient_id": "text_user_id", "text": "hello"}])
        return future

    monkeypatch.setattr(Agent, "handle_text", _agent_response)
    monkeypatch.setattr(AgentProcessor, "get_agent", _get_agent)


@pytest.mark.asyncio
async def test_chat_no_auth():
    response = await client.post(
        "/chat", json={"text": "hi"}
    )
    actual = await response.get_json()
    assert response.status_code == 422
    assert not actual["success"]
    assert actual["message"] == "Could not validate credentials!"

    response = await client.post(
        "/chat", json={"text": "hi"}, headers={"Authentication": None}
    )
    actual = await response.get_json()
    assert response.status_code == 422
    assert not actual["success"]
    assert actual["message"] == "Could not validate credentials!"


@pytest.mark.asyncio
async def test_chat_with_invalid_auth():
    response = await client.post(
        "/chat", json={"text": "hi"}, headers={
            "Authentication": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"}
    )
    actual = await response.get_json()
    assert response.status_code == 422
    assert not actual["success"]
    assert actual["message"] == "Could not validate credentials!"


@pytest.mark.asyncio
async def test_chat_with_no_request_body():
    response = await client.post(
        "/chat", headers={"Authorization": pytest.auth_token}
    )
    actual = await response.get_json()
    assert response.status_code == 422
    assert not actual["success"]
    assert actual["message"] == "Invalid request body!"


@pytest.mark.asyncio
async def test_chat_with_invalid_request_body():
    response = await client.post(
        "/chat", json={"data": "hi"}, headers={"Authorization": pytest.auth_token}
    )
    actual = await response.get_json()
    assert response.status_code == 422
    assert not actual["success"]
    assert actual["message"] == "Invalid request body!"

    response = await client.post(
        "/chat", json={}, headers={"Authorization": pytest.auth_token}
    )
    actual = await response.get_json()
    assert response.status_code == 422
    assert not actual["success"]
    assert actual["message"] == "Invalid request body!"

    response = await client.post(
        "/chat", json={"data": "hi", "text": "hi"}, headers={"Authorization": pytest.auth_token}
    )
    actual = await response.get_json()
    assert response.status_code == 422
    assert not actual["success"]
    assert actual["message"] == "Invalid request body!"

    # response = await client.post(
    #     "/chat", json={"text": [{"text": "hi"}]}, headers={"Authorization": pytest.auth_token}
    # )
    # actual = await response.get_json()
    # assert response.status_code == 200
    # assert actual["success"]
    # assert actual["message"] == "Invalid request body!"


@pytest.mark.asyncio
async def test_chat_with_expired_auth_token():
    auth_token = "Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZXN0QGRpZ2l0ZS5jb20iLCJleHAiOjE2MTQ0MTQyNTcsImlhdCI6MTYxNDQxNDI1Mn0.iFWhGp0nxNjDmfYDuktdON7W-H0Q7O4jWvHmon7upCk"
    response = await client.post(
        "/chat", json={"text": "hi"}, headers={"Authorization": auth_token}
    )
    actual = await response.get_json()
    assert response.status_code == 422
    assert not actual["success"]
    assert actual["message"] == "Signature expired."


@pytest.mark.asyncio
async def test_chat_with_deleted_user():
    auth_token = "Bearer " + ChatServerUtils.encode_auth_token("test_5@digite.com").decode("utf-8")
    response = await client.post(
        "/chat", json={"text": "hi"}, headers={"Authorization": auth_token}
    )
    actual = await response.get_json()
    assert response.status_code == 422
    assert not actual["success"]
    assert actual["message"] == "Inactive User please contact admin!"


@pytest.mark.asyncio
async def test_chat_with_deleted_bot():
    auth_token = "Bearer " + ChatServerUtils.encode_auth_token("test_2@digite.com").decode("utf-8")
    response = await client.post(
        "/chat", json={"text": "hi"}, headers={"Authorization": auth_token}
    )
    actual = await response.get_json()
    assert response.status_code == 422
    assert not actual["success"]
    assert actual["message"] == "Inactive Bot Please contact system admin!"


@pytest.mark.asyncio
async def test_chat_with_bot_not_trained():
    auth_token = "Bearer " + ChatServerUtils.encode_auth_token("test_3@digite.com").decode("utf-8")
    response = await client.post(
        "/chat", json={"text": "hi"}, headers={"Authorization": auth_token}
    )
    actual = await response.get_json()
    assert response.status_code == 422
    assert not actual["success"]
    assert actual["message"] == "Bot has not been trained yet !"


@pytest.mark.asyncio
async def test_chat(mock_agent_response):
    response = await client.post(
        "/chat", json={"text": "hi"}, headers={"Authorization": pytest.auth_token}
    )
    actual = await response.get_json()
    assert response.status_code == 200
    assert actual["success"]
    assert actual["message"] == "hello"


@pytest.mark.asyncio
async def test_add_channel_exception(monkeypatch):
    def _mock_exception(*args, **kwargs):
        raise Exception("Cannot register this webhook!")

    monkeypatch.setattr(KaironTelegramClient, "__init__", _mock_exception)

    channel = KaironChannels.TELEGRAM
    credentials = {"auth_token": "abcde:1234567890"}
    request = {"channel": channel, "credentials": credentials}
    response = await client.post(
        "/chat/channel", json=request, headers={"Authorization": pytest.auth_token}
    )
    actual = await response.get_json()
    assert response.status_code == 422
    assert not actual["success"]
    assert actual["message"] == "Cannot register this webhook!"


@pytest.mark.asyncio
async def test_add_channel(monkeypatch):
    def _mock_telegram_client(*args, **kwargs):
        return None

    monkeypatch.setattr(KaironTelegramClient, "__init__", _mock_telegram_client)

    channel = KaironChannels.TELEGRAM
    credentials = {"auth_token": "abcde:1234567890"}
    request = {"channel": channel, "credentials": credentials}
    response = await client.post(
        "/chat/channel", json=request, headers={"Authorization": pytest.auth_token}
    )
    actual = await response.get_json()
    assert response.status_code == 200
    assert actual["success"]
    assert actual["message"] == "Credentials registered successfully"


@pytest.mark.asyncio
async def test_add_channel_already_exists(monkeypatch):
    def _mock_telegram_client(*args, **kwargs):
        return None

    monkeypatch.setattr(KaironTelegramClient, "__init__", _mock_telegram_client)

    channel = KaironChannels.TELEGRAM
    credentials = {"auth_token": "abcde:1234567890"}
    request = {"channel": channel, "credentials": credentials}
    response = await client.post(
        "/chat/channel", json=request, headers={"Authorization": pytest.auth_token}
    )
    actual = await response.get_json()
    assert response.status_code == 422
    assert not actual["success"]
    assert actual["message"] == "Channel already registered!"


# @pytest.mark.asyncio
# async def test_add_channel_existing_bot(monkeypatch):
#     def _mock_telegram_client(*args, **kwargs):
#         return None
#     monkeypatch.setattr(KaironTelegramClient, "__init__", _mock_telegram_client)
#
#     channel = KaironChannels.FACEBOOK
#     credentials = {"auth_token": "abcde:1234567890"}
#     request = {"channel": channel, "credentials": credentials}
#     response = await client.post(
#         "/chat/channel", json=request, headers={"Authorization": pytest.auth_token}
#     )
#     actual = await response.get_json()
#     assert response.status_code == 422
#     assert not actual["success"]
#     assert actual["message"] == "Channel already registered!"


@pytest.mark.asyncio
async def test_add_invalid_channel(monkeypatch):
    def _mock_telegram_client(*args, **kwargs):
        return None

    monkeypatch.setattr(KaironTelegramClient, "__init__", _mock_telegram_client)

    channel = "NEW_CHANNEL"
    credentials = {"auth_token": "abcde:1234567890"}
    request = {"channel": channel, "credentials": credentials}
    response = await client.post(
        "/chat/channel", json=request, headers={"Authorization": pytest.auth_token}
    )
    actual = await response.get_json()
    assert response.status_code == 422
    assert not actual["success"]
    assert actual["message"] == "Channel not supported!"


@pytest.mark.asyncio
async def test_get_channel():
    response = await client.get(
        "/chat/channel/TELEGRAM", headers={"Authorization": pytest.auth_token}
    )
    actual = await response.get_json()
    assert response.status_code == 200
    assert actual["success"]
    data = actual["data"]
    assert data['channel'] == KaironChannels.TELEGRAM
    assert data['bot'] == '5ea8125db7c285f40551295c'
    assert data['credentials']['auth_token'] == "abcde:1234567890"
    assert data['user'] == 'test@digite.com'
    assert data['status']
    assert data['timestamp']
    assert actual["message"] == "Credentials retrieved successfully"


@pytest.mark.asyncio
async def test_update_channel(monkeypatch):
    def _mock_telegram_client(*args, **kwargs):
        return None

    monkeypatch.setattr(KaironTelegramClient, "__init__", _mock_telegram_client)

    channel = KaironChannels.TELEGRAM
    credentials = {"auth_token": "abcde:0987654321"}
    request = {"channel": channel, "credentials": credentials}
    response = await client.put(
        "/chat/channel", json=request, headers={"Authorization": pytest.auth_token}
    )
    actual = await response.get_json()
    assert response.status_code == 200
    assert actual["success"]
    assert actual["message"] == "Credentials updated successfully"


@pytest.mark.asyncio
async def test_get_channel_update():
    response = await client.get(
        "/chat/channel/TELEGRAM", headers={"Authorization": pytest.auth_token}
    )
    actual = await response.get_json()
    assert response.status_code == 200
    assert actual["success"]
    data = actual["data"]
    assert data['channel'] == KaironChannels.TELEGRAM
    assert data['bot'] == '5ea8125db7c285f40551295c'
    assert data['credentials']['auth_token'] == "abcde:0987654321"
    assert data['user'] == 'test@digite.com'
    assert data['status']
    assert data['timestamp']
    assert actual["message"] == "Credentials retrieved successfully"


@pytest.mark.asyncio
async def test_list_channels():
    response = await client.get(
        "/chat/channel/all", headers={"Authorization": pytest.auth_token}
    )

    actual = await response.get_json()
    assert response.status_code == 200
    assert actual["success"]
    data = actual["data"]
    assert data[0]['channel'] == KaironChannels.TELEGRAM
    assert data[0]['bot'] == '5ea8125db7c285f40551295c'
    assert data[0]['credentials']['auth_token'] == "abcde:0987654321"
    assert data[0]['user'] == 'test@digite.com'
    assert data[0]['status']
    assert data[0]['timestamp']
    assert actual["message"] == "Credentials retrieved successfully"


@pytest.mark.asyncio
async def test_telegram_webhook(monkeypatch, mock_agent_response):
    def _mock_bot_name(*args, **kwargs):
        return "5ea8125db7c285f40551295c"

    def _mock_send_text(*args, **kwargs):
        return None

    monkeypatch.setattr(KaironTelegramClient, "name", _mock_bot_name)
    monkeypatch.setattr(KaironTelegramClient, "send_text", _mock_send_text)

    request = {
        "update_id": 646911460,
        "message": {
            "message_id": 93,
            "from": {
                "id": 100001111,
                "is_bot": False,
                "first_name": "Jiayu",
                "username": "jiayu",
                "language_code": "en-US"
            },
            "chat": {
                "id": 100001111,
                "first_name": "Jiayu",
                "username": "jiayu",
                "type": "private"
            },
            "date": 1509641174,
            "text": "hi"
        }
    }
    response = await client.post(
        urljoin("/telegram/5ea8125db7c285f40551295c/", pytest.auth_token),
        json=request
    )
    actual = await response.get_json()
    assert response.status_code == 200
    assert actual["success"]
    assert actual["message"] == "Message sent Successfully"


@pytest.mark.asyncio
async def test_delete_channel():
    response = await client.delete(
        "/chat/channel/TELEGRAM", headers={"Authorization": pytest.auth_token}
    )
    actual = await response.get_json()
    assert response.status_code == 200
    assert actual["success"]
    assert actual["message"] == "Credentials removed successfully"
