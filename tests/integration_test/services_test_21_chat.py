from tests.integration_test.services_support import *  # noqa: F403
from tests.integration_test.services_support import setup, fast_rasa_training



def test_get_training_data_count(monkeypatch):
    def _mock_training_data_count(*args, **kwargs):
        return {
            "intents": [{"name": "greet", "count": 5}, {"name": "affirm", "count": 3}],
            "utterances": [
                {"name": "utter_greet", "count": 4},
                {"name": "utter_affirm", "count": 11},
            ],
        }

    monkeypatch.setattr(
        MongoProcessor, "get_training_data_count", _mock_training_data_count
    )
    response = client.get(
        f"/api/bot/{pytest.bot}/data/count",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] == _mock_training_data_count()


@responses.activate
def test_chat(monkeypatch):
    monkeypatch.setitem(
        Utility.environment["model"]["agent"], "url", "http://localhost"
    )
    chat_json = {"data": "Hi"}
    responses.add(
        responses.POST,
        f"http://localhost/api/bot/{pytest.bot}/chat",
        status=200,
        match=[responses.matchers.json_params_matcher(chat_json)],
        json={
            "success": True,
            "error_code": 0,
            "data": {"response": [{"bot": "Hi"}]},
            "message": None,
        },
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/chat",
        json=chat_json,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["response"]


@responses.activate
def test_chat_user(monkeypatch):
    monkeypatch.setitem(
        Utility.environment["model"]["agent"], "url", "http://localhost"
    )
    chat_json = {"data": "Hi"}
    responses.add(
        responses.POST,
        f"http://localhost/api/bot/{pytest.bot}/chat",
        status=200,
        match=[responses.matchers.json_params_matcher(chat_json)],
        json={
            "success": True,
            "error_code": 0,
            "data": {"response": [{"bot": "Hi"}]},
            "message": None,
        },
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/chat",
        json=chat_json,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["response"]


@responses.activate
def test_chat_with_data_empty(monkeypatch):
    monkeypatch.setitem(
        Utility.environment["model"]["agent"], "url", "http://localhost"
    )
    chat_json = {"data": ""}
    response = client.post(
        f"/api/bot/{pytest.bot}/chat",
        json=chat_json,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["message"] == "data cannot be empty"
    assert actual["error_code"] == 422
    assert actual["data"] is None


@responses.activate
def test_chat_augment_user_with_data_empty(monkeypatch):
    monkeypatch.setitem(
        Utility.environment["model"]["agent"], "url", "http://localhost"
    )
    chat_json = {"data": ""}
    response = client.post(
        f"/api/bot/{pytest.bot}/chat/testUser",
        json=chat_json,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["message"] == "data cannot be empty"
    assert actual["error_code"] == 422
    assert actual["data"] is None


@responses.activate
def test_chat_augment_user(monkeypatch):
    monkeypatch.setitem(
        Utility.environment["model"]["agent"], "url", "http://localhost"
    )
    chat_json = {"data": "Hi"}
    responses.add(
        responses.POST,
        f"http://localhost/api/bot/{pytest.bot}/chat",
        status=200,
        match=[responses.matchers.json_params_matcher(chat_json)],
        json={
            "success": True,
            "error_code": 0,
            "data": {"response": [{"bot": "Hi"}]},
            "message": None,
        },
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/chat/testUser",
        json=chat_json,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["response"]


def test_get_client_config():
    response = client.get(
        f"/api/bot/{pytest.bot}/chat/client/config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]
    assert actual["data"]["whitelist"] == ["*"]


def test_get_client_config_url():
    response = client.get(
        f"/api/bot/{pytest.bot}/chat/client/config/url",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]
    pytest.url = actual["data"]


@responses.activate
def test_refresh_token(monkeypatch):
    response = client.get(pytest.url)
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]
    assert actual["data"]["headers"]["authorization"]["token_type"] == "Bearer"
    ate = actual["data"]["headers"]["authorization"]["access_token_expiry"]
    rte = actual["data"]["headers"]["authorization"]["refresh_token_expiry"]
    assert (
            31
            >= round(
        (utc_from_timestamp(ate) - utc_now()).total_seconds() / 60
    )
            >= 29
    )
    assert (
            61
            >= round(
        (utc_from_timestamp(rte) - utc_now()).total_seconds() / 60
    )
            >= 59
    )
    refresh_token = actual["data"]["headers"]["authorization"]["refresh_token"]

    response = client.get(
        f"/api/auth/{pytest.bot}/token/refresh",
        headers={"Authorization": pytest.token_type + " " + refresh_token},
    )
    actual = response.json()
    # assert 1 == 0
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["access_token"]
    assert actual["data"]["token_type"]
    assert actual["data"]["refresh_token"]
    assert (
            actual["message"]
            == "This token will be shown only once. Please copy this somewhere safe."
               "It is your responsibility to keep the token secret. "
               "If leaked, others may have access to your system."
    )
    new_token = actual["data"]["access_token"]
    token_type = actual["data"]["token_type"]

    monkeypatch.setitem(
        Utility.environment["model"]["agent"], "url", "http://localhost"
    )
    responses.add(
        responses.POST,
        f"http://localhost/api/bot/{pytest.bot}/chat",
        status=200,
        json={
            "success": True,
            "error_code": 0,
            "data": {"response": [{"bot": "Hi"}]},
            "message": None,
        },
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/chat",
        json={"data": "Hi"},
        headers={"Authorization": token_type + " " + new_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["response"]

    response = client.post(
        f"/api/bot/{pytest.bot}/metric/user/logs/user_metrics",
        json={"data": {"location": "india"}},
        headers={"Authorization": token_type + " " + new_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0

    response = client.get(
        f"/api/bot/{pytest.bot}/model/reload",
        headers={"Authorization": token_type + " " + new_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_refresh_token_from_dynamic_token():
    response = client.get(pytest.url)
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]
    chat_token = actual["data"]["headers"]["authorization"]["access_token"]

    response = client.get(
        f"/api/auth/{pytest.bot}/token/refresh",
        headers={"Authorization": pytest.token_type + " " + chat_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Access denied for this endpoint"
    assert not actual["data"]


def test_trigger_api_server_using_refresh_token():
    response = client.get(pytest.url)
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]
    token_type = actual["data"]["headers"]["authorization"]["token_type"]
    refresh_token = actual["data"]["headers"]["authorization"]["refresh_token"]

    response = client.get(
        f"/api/bot/{pytest.bot}/model/reload",
        headers={"Authorization": token_type + " " + refresh_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Access denied for this endpoint"
    assert not actual["data"]


def test_get_client_config_using_invalid_uid():
    response = client.get(
        f"/api/bot/{pytest.bot}/chat/client/config/ecmkfnufjsufysfbksjnfaksn"
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert not actual["data"]


def test_save_client_config():
    config_path = "./template/chat-client/default-config.json"
    config = json.load(open(config_path))
    config["headers"] = {}
    config["headers"]["X-USER"] = "kairon-user"
    response = client.post(
        f"/api/bot/{pytest.bot}/chat/client/config",
        json={"data": config},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Config saved"

    config = ChatClientConfig.objects(bot=pytest.bot).get()
    assert config.config
    assert config.config["headers"]["X-USER"]
    assert not config.config["headers"].get("authorization")


@responses.activate
def test_get_client_config_using_uid(monkeypatch):
    monkeypatch.setitem(
        Utility.environment["model"]["agent"], "url", "http://localhost"
    )
    chat_json = {"data": "Hi"}
    responses.add(
        responses.POST,
        f"http://localhost/api/bot/{pytest.bot}/chat",
        status=200,
        match=[responses.matchers.json_params_matcher(chat_json)],
        json={
            "success": True,
            "error_code": 0,
            "data": None,
            "message": "Bot has not been trained yet!",
        },
    )
    response = client.get(pytest.url)
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]
    assert None == actual.get("data").get("whitelist")

    access_token = actual["data"]["headers"]["authorization"]["access_token"]
    token_type = actual["data"]["headers"]["authorization"]["token_type"]
    response = client.post(
        f"/api/bot/{pytest.bot}/chat",
        json=chat_json,
        headers={"Authorization": f"{token_type} {access_token}", "X-USER": "hacker"},
    )
    actual = response.json()
    assert actual["message"] == "Bot has not been trained yet!"

    response = client.get(
        f"/api/bot/{pytest.bot}/intents",
        headers={"Authorization": f"{token_type} {access_token}", "X-USER": "hacker"},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert not actual["success"]
    assert actual["message"] == "Access denied for this endpoint"


@responses.activate
def test_get_client_config_refresh(monkeypatch):
    monkeypatch.setitem(
        Utility.environment["model"]["agent"], "url", "http://localhost"
    )
    chat_json = {"data": "Hi"}
    responses.add(
        responses.POST,
        f"http://localhost/api/bot/{pytest.bot}/chat",
        status=200,
        match=[responses.matchers.json_params_matcher(chat_json)],
        json={
            "success": True,
            "error_code": 0,
            "data": None,
            "message": "Bot has not been trained yet!",
        },
    )
    response = client.get(pytest.url)
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]
    assert actual["data"]["headers"]["X-USER"] == "kairon-user"
    assert None == actual.get("data").get("whitelist")

    access_token = actual["data"]["headers"]["authorization"]["access_token"]
    token_type = actual["data"]["headers"]["authorization"]["token_type"]
    user = actual["data"]["headers"]["X-USER"]
    response = client.post(
        f"/api/bot/{pytest.bot}/chat",
        json=chat_json,
        headers={"Authorization": f"{token_type} {access_token}", "X-USER": user},
    )
    actual = response.json()
    assert actual["message"] == "Bot has not been trained yet!"

    response = client.get(
        f"/api/bot/{pytest.bot}/intents",
        headers={"Authorization": f"{token_type} {access_token}", "X-USER": user},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert not actual["success"]
    assert actual["message"] == "Access denied for this endpoint"


def test_get_chat_client_config_multilingual_enabled_no_bots_enabled():
    from bson import ObjectId

    response = client.get(
        f"/api/bot/{pytest.bot}/chat/client/config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    actual["data"]["multilingual"]["enable"] = True
    actual["data"]["multilingual"]["bots"] = [
        {"id": ObjectId().__str__(), "is_enabled": True}
    ]

    response = client.post(
        f"/api/bot/{pytest.bot}/chat/client/config",
        json={"data": actual["data"]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Config saved"

    response = client.get(pytest.url)
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert not actual["data"]
    assert actual["message"] == "Bot is disabled. Please use a valid bot."

    response = client.get(
        f"/api/bot/{pytest.bot}/chat/client/config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0


def test_save_chat_client_config_enable_multilingual_bots():
    AccountProcessor.add_bot(
        name="demo-hi",
        account=pytest.account,
        user="integ1@gmail.com",
        metadata={
            "language": "hi",
            "source_bot_id": pytest.bot,
            "source_language": "en",
        },
    )
    response = client.get(
        f"/api/bot/{pytest.bot}/chat/client/config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["multilingual"]["enable"]
    actual["data"]["multilingual"]["bots"][0]["is_enabled"] = True

    response = client.post(
        f"/api/bot/{pytest.bot}/chat/client/config",
        json={"data": actual["data"]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Config saved"


def test_save_chat_client_config_enable_multilingual_bots_no_bot_enabled():
    response = client.get(
        f"/api/bot/{pytest.bot}/chat/client/config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["multilingual"]["enable"]
    actual["data"]["multilingual"]["bots"][0]["is_enabled"] = False

    response = client.post(
        f"/api/bot/{pytest.bot}/chat/client/config",
        json={"data": actual["data"]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "At least one bot should be enabled!"


def test_get_chat_client_config_multilingual_enabled():
    response = client.get(pytest.url)
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]["multilingual"]["bots"]) == 1
    assert actual["data"]["multilingual"]["bots"][0]["is_enabled"]

    AccountProcessor.add_bot(
        name="demo-mr",
        account=pytest.account,
        user="integ1@gmail.com",
        metadata={
            "language": "hi",
            "source_bot_id": pytest.bot,
            "source_language": "en",
        },
    )

    response = client.get(pytest.url)
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]["multilingual"]["bots"]) == 1
    assert actual["data"]["multilingual"]["bots"][0]["is_enabled"]

    response = client.get(
        f"/api/bot/{pytest.bot}/chat/client/config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]["multilingual"]["bots"]) == 3
    assert actual["data"]["multilingual"]["bots"][0]["is_enabled"]
    assert not actual["data"]["multilingual"]["bots"][1]["is_enabled"]
