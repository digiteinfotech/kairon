from tests.integration_test.services_support import *  # noqa: F403
from tests.integration_test.services_support import setup, fast_rasa_training



def test_get_end_user_metrics_empty():
    response = client.get(
        f"/api/bot/{pytest.bot}/metric/user/logs/prod_chat?start_idx=0&page_size=10",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["logs"] == []
    assert actual["data"]["total"] == 0


def test_add_end_user_metrics():
    log_type = "user_metrics"
    response = client.post(
        f"/api/bot/{pytest.bot}/metric/user/logs/{log_type}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"data": {"source": "Digite.com", "language": "English"}},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert "id" in actual["data"]


@responses.activate
def test_add_end_user_metrics_with_ip(monkeypatch):
    log_type = "user_metrics"
    ip = "192.222.100.106"
    token = "abcgd563"
    enable = True
    monkeypatch.setitem(Utility.environment["plugins"]["location"], "token", token)
    monkeypatch.setitem(Utility.environment["plugins"]["location"], "enable", enable)
    ip_list = [ip.strip() for ip in ip.split(",")]
    url = f"https://ipinfo.io/batch?token={token}"
    payload = json.dumps(ip_list)
    expected = {
        "140.82.201.129": {
            "ip": "140.82.201.129",
            "city": "Mumbai",
            "region": "Maharashtra",
            "country": "IN",
            "loc": "19.0728,72.8826",
            "org": "AS13150 CATO NETWORKS LTD",
            "postal": "400070",
            "timezone": "Asia/Kolkata",
        }
    }
    responses.add("POST", url, json=expected)
    response = client.post(
        f"/api/bot/{pytest.bot}/metric/user/logs/{log_type}",
        headers={
            "Authorization": pytest.token_type + " " + pytest.access_token,
            "X-Forwarded-For": "192.222.100.106",
        },
        json={"data": {"source": "Digite.com", "language": "English", "ip": ip}},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert "id" in actual["data"]


@responses.activate
def test_add_end_user_metrics_ip_request_failure(monkeypatch):
    log_type = "user_metrics"
    ip = "192.222.100.106"
    token = "abcgd563"
    enable = True
    monkeypatch.setitem(Utility.environment["plugins"]["location"], "token", token)
    monkeypatch.setitem(Utility.environment["plugins"]["location"], "enable", enable)
    url = f"https://ipinfo.io/{ip}?token={token}"
    responses.add("GET", url, status=500)
    response = client.post(
        f"/api/bot/{pytest.bot}/metric/user/logs/{log_type}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"data": {"source": "Digite.com", "language": "English"}},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert "id" in actual["data"]


def test_add_and_update_conversation_feedback(monkeypatch):
    log_type = "conversation_feedback"
    data = {
        "feedback": "",
        "rating": 1,
        "botId": "6322ebbb3c62158dab4aee71",
        "botReply": [{"text": "Hello! How are you?"}],
        "userReply": "",
        "date": "2023-07-17T06:48:02.453Z",
        "sender_id": None,
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/metric/user/logs/{log_type}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"data": data},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert "id" in actual["data"]
    assert actual["message"] == "Metrics added"
    id = actual["data"]["id"]

    response = client.put(
        f"/api/bot/{pytest.bot}/metric/user/logs/{log_type}/{id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"data": {"feedback": "Good"}},
    )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert not actual["data"]
    assert actual["message"] == "Metrics updated"


@responses.activate
def test_get_end_user_metrics(monkeypatch):
    token = "abcgd563"
    enable = True
    monkeypatch.setitem(Utility.environment["plugins"]["location"], "token", token)
    monkeypatch.setitem(Utility.environment["plugins"]["location"], "enable", enable)
    url = f"https://ipinfo.io/batch?token={token}"

    expected = {
        "140.82.201.129": {
            "ip": "140.82.201.129",
            "city": "Mumbai",
            "region": "Maharashtra",
            "country": "IN",
            "loc": "19.0728,72.8826",
            "org": "AS13150 CATO NETWORKS LTD",
            "postal": "400070",
            "timezone": "Asia/Kolkata",
        }
    }
    responses.add("POST", url, json=expected)
    for i in range(5):
        client.post(
            f"/api/bot/{pytest.bot}/metric/user/logs/{MetricType.agent_handoff.value}",
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
            json={"data": {"source": "Digite.com", "language": "English"}},
        )

    response = client.get(
        f"/api/bot/{pytest.bot}/metric/user/logs/agent_handoff?start_idx=0&page_size=10",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["success"]
    assert len(actual["data"]["logs"]) == 5
    assert actual["data"]["total"] == 5

    from_date = date.today()
    to_date = from_date + timedelta(days=1)
    search_response = client.get(
        f"/api/bot/{pytest.bot}/logs/agent_handoff/search?from_date={from_date}&to_date={to_date}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    response_json = search_response.json()
    print("agent", response_json)
    assert response_json["success"] is True
    assert response_json["error_code"] == 0

    data = response_json["data"]
    assert "logs" in data
    assert isinstance(data["logs"], list)
    response = client.get(
        f"/api/bot/{pytest.bot}/metric/user/logs/user_metrics?start_idx=0&page_size=10",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]["logs"]) == 5
    assert actual["data"]["total"] == 5
    actual["data"]["logs"][0].pop("timestamp")
    actual["data"]["logs"][0].pop("account")
    assert actual["data"]["logs"][0] == {
        "metric_type": "user_metrics",
        "user": "integ1@gmail.com",
        "bot": pytest.bot,
        "source": "Digite.com",
        "language": "English",
    }
    actual["data"]["logs"][1].pop("timestamp")
    actual["data"]["logs"][1].pop("account")
    actual["data"]["logs"][2].pop("timestamp")
    actual["data"]["logs"][2].pop("account")
    assert actual["data"]["logs"][1]["ip"]
    del actual["data"]["logs"][1]["ip"]
    assert actual["data"]["logs"][1] == {
        "metric_type": "user_metrics",
        "user": "integ1@gmail.com",
        "bot": pytest.bot,
        "source": "Digite.com",
        "language": "English",
        "city": "Mumbai",
        "region": "Maharashtra",
        "country": "IN",
        "loc": "19.0728,72.8826",
        "org": "AS13150 CATO NETWORKS LTD",
        "postal": "400070",
        "timezone": "Asia/Kolkata",
    }
    assert actual["data"]["logs"][2] == {
        "metric_type": "user_metrics",
        "user": "integ1@gmail.com",
        "bot": pytest.bot,
        "source": "Digite.com",
        "language": "English",
    }

    response = client.get(
        f"/api/bot/{pytest.bot}/metric/user/logs/agent_handoff?start_idx=3",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0

    response = client.get(
        f"/api/bot/{pytest.bot}/metric/user/logs/agent_handoff?start_idx=3&page_size=1",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]["logs"]) == 1
    assert actual["data"]["total"] == 5


def test_get_roles():
    response = client.get(
        f"/api/user/roles/access",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] == Utility.system_metadata["roles"]


def test_generate_limited_access_temporary_token():
    response = client.get(
        f"/api/auth/{pytest.bot}/integration/token/temp",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["access_token"]
    assert actual["data"]["token_type"]
    assert (
            actual["message"]
            == "This token will be shown only once. Please copy this somewhere safe."
               "It is your responsibility to keep the token secret. If leaked, others may have access to your system."
    )
    token = actual["data"]["access_token"]

    response = client.get(
        f"/api/bot/{pytest.bot}/chat/client/config/{actual['data']['access_token']}",
        headers={"Authorization": pytest.token_type + " " + token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]
    assert isinstance(actual["data"], dict)
    assert None == actual.get("data").get("whitelist")

    response = client.get(
        f"/api/bot/{pytest.bot}/slots",
        headers={"Authorization": pytest.token_type + " " + token},
    )
    actual = response.json()
    assert actual == {
        "success": False,
        "message": "Access denied for this endpoint",
        "data": None,
        "error_code": 422,
    }

    response = client.post(
        f"/api/bot/{pytest.bot}/intents",
        json={"data": "happier"},
        headers={"Authorization": pytest.token_type + " " + token},
    )
    actual = response.json()
    assert actual == {
        "success": False,
        "message": "Access denied for this endpoint",
        "data": None,
        "error_code": 422,
    }

    response = client.post(
        "/api/account/bot",
        json={"name": "covid-bot"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    response = response.json()
    assert response["error_code"] == 0

    response = client.get(
        "/api/account/bot",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    bot_2 = response["data"]["account_owned"][1]["_id"]

    response = client.get(
        f"/api/bot/{bot_2}/chat/client/config/{token}",
    )
    actual = response.json()
    assert actual == {
        "success": False,
        "message": "Invalid token",
        "data": None,
        "error_code": 401,
    }


def test_get_client_config_using_uid_invalid_domains(monkeypatch):
    config_path = "./template/chat-client/default-config.json"
    config = json.load(open(config_path))
    config["headers"] = {}
    config["headers"]["X-USER"] = "kairon-user"
    config["whitelist"] = ["kairon.digite.com", "kairon-api.digite.com"]
    client.post(
        f"/api/bot/{pytest.bot}/chat/client/config",
        json={"data": config},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    monkeypatch.setitem(
        Utility.environment["model"]["agent"], "url", "http://localhost"
    )
    response = client.get(
        pytest.url, headers={"HTTP_REFERER": "http://www.attackers.com"}
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 403
    assert not actual["data"]
    assert actual["message"] == "Domain not registered for kAIron client"


def test_get_client_config_using_uid_valid_domains(monkeypatch):
    monkeypatch.setitem(
        Utility.environment["model"]["agent"], "url", "http://localhost"
    )
    response = client.get(
        pytest.url, headers={"HTTP_REFERER": "https://kairon-api.digite.com"}
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]
    assert None == actual.get("data").get("whitelist")


def test_get_client_config_using_uid_invalid_domains_referer(monkeypatch):
    monkeypatch.setitem(
        Utility.environment["model"]["agent"], "url", "http://localhost"
    )
    response = client.get(pytest.url, headers={"referer": "http://www.attackers.com"})
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 403
    assert not actual["data"]
    assert actual["message"] == "Domain not registered for kAIron client"


def test_get_client_config_using_uid_valid_domains_referer(monkeypatch):
    monkeypatch.setitem(
        Utility.environment["model"]["agent"], "url", "http://localhost"
    )
    response = client.get(
        pytest.url, headers={"referer": "https://kairon-api.digite.com"}
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]
    assert None == actual.get("data").get("whitelist")


def test_save_client_config_invalid_domain_format():
    config_path = "./template/chat-client/default-config.json"
    config = json.load(open(config_path))
    config["headers"] = {}
    config["headers"]["X-USER"] = "kairon-user"
    config["whitelist"] = ["invalid_domain_format"]
    response = client.post(
        f"/api/bot/{pytest.bot}/chat/client/config",
        json={"data": config},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "One of the domain is invalid"
