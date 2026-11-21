from tests.integration_test.services_support import *  # noqa: F403
from tests.integration_test.services_support import setup, fast_rasa_training



def get_client_config_valid_domain():
    response = client.get(
        f"/api/bot/{pytest.bot}/chat/client/config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]
    assert actual["data"]["whitelist"] == ["kairon.digite.com", "kairon-api.digite.com"]


def test_multilingual_translate_logs_empty():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/multilingual/logs?start_idx=0&page_size=10",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"]["logs"] == []
    assert actual["data"]["total"] == 0


@responses.activate
def test_multilingual_translate():
    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.multilingual}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
        match=[
            responses.matchers.json_params_matcher(
                {
                    "data": {
                        "bot": pytest.bot,
                        "user": "integ1@gmail.com",
                        "dest_lang": "es",
                        "translate_responses": "",
                        "translate_actions": "",
                    },
                    "cron_exp": None,
                    "timezone": None,
                    "run_at": None
                }
            )
        ],
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/multilingual/translate",
        json={
            "dest_lang": "es",
            "translate_responses": False,
            "translate_actions": False,
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()

    assert response["success"]
    assert response["message"] == "Bot translation in progress! Check logs."
    assert response["error_code"] == 0
    MultilingualLogProcessor.add_log(
        pytest.bot, "integ1@gmail.com", event_status=EVENT_STATUS.COMPLETED.value, status=STATUSES.SUCCESS.value
    )


def test_multilingual_translate_invalid_bot_id():
    response = client.post(
        f"/api/bot/{pytest.bot + '0'}/multilingual/translate",
        json={
            "dest_lang": "es",
            "translate_responses": False,
            "translate_actions": False,
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()

    assert not response["success"]
    assert response["message"] == "Access to bot is denied"
    assert response["error_code"] == 422


def test_multilingual_translate_no_destination_lang():
    response = client.post(
        f"/api/bot/{pytest.bot}/multilingual/translate",
        json={"translate_responses": False, "translate_actions": False},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()

    assert not response["success"]
    assert response["message"] == [
        {
            "loc": ["body", "dest_lang"],
            "msg": "field required",
            "type": "value_error.missing",
        }
    ]
    assert response["error_code"] == 422

    response = client.post(
        f"/api/bot/{pytest.bot}/multilingual/translate",
        json={
            "dest_lang": " ",
            "translate_responses": False,
            "translate_actions": False,
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()

    assert not response["success"]
    assert response["message"] == [
        {
            "loc": ["body", "dest_lang"],
            "msg": "dest_lang cannot be empty",
            "type": "value_error",
        }
    ]
    assert response["error_code"] == 422


def test_multilingual_translate_limit_exceeded(monkeypatch):
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.multilingual_limit_per_day = 0
    bot_settings.save()

    response = client.post(
        f"/api/bot/{pytest.bot}/multilingual/translate",
        json={
            "dest_lang": "es",
            "translate_responses": False,
            "translate_actions": False,
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()

    assert response["message"] == "Daily limit exceeded."
    assert response["error_code"] == 422
    assert not response["success"]


@responses.activate
def test_multilingual_translate_using_event_with_actions_and_responses(monkeypatch):
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.multilingual_limit_per_day = 2
    bot_settings.save()
    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.multilingual}",
    )
    responses.add(
        responses.POST,
        event_url,
        status=200,
        json={"success": True, "message": "Event triggered successfully!"},
        match=[
            responses.matchers.json_params_matcher(
                {
                    "data": {
                        "bot": pytest.bot,
                        "user": "integ1@gmail.com",
                        "dest_lang": "es",
                        "translate_responses": "--translate-responses",
                        "translate_actions": "--translate-actions",
                    },
                    "cron_exp": None,
                    "timezone": None,
                    "run_at": None
                }
            )
        ],
    )

    response = client.post(
        f"/api/bot/{pytest.bot}/multilingual/translate",
        json={
            "dest_lang": "es",
            "translate_responses": True,
            "translate_actions": True,
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()

    assert response["success"]
    assert response["error_code"] == 0
    assert response["message"] == "Bot translation in progress! Check logs."


def test_multilingual_translate_in_progress():
    response = client.post(
        url=f"/api/bot/{pytest.bot}/multilingual/translate",
        json={
            "dest_lang": "es",
            "translate_responses": False,
            "translate_actions": False,
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    assert response["error_code"] == 422
    assert response["message"] == "Event already in progress! Check logs."
    assert not response["success"]


def test_multilingual_translate_logs():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/multilingual/logs?start_idx=0&page_size=10",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    response = client.get(
        url=f"/api/bot/{pytest.bot}/logs/multilingual?start_idx=0&page_size=10",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    print(actual)
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]["logs"]) == 2
    assert actual["data"]["total"] == 2
    assert actual["data"]["logs"][0]["d_lang"] == "es"
    assert actual["data"]["logs"][0]["copy_type"] == "Translation"
    assert actual["data"]["logs"][0]["translate_responses"]
    assert actual["data"]["logs"][0]["translate_actions"]
    assert actual["data"]["logs"][0]["event_status"] == "Enqueued"
    assert actual["data"]["logs"][0]["start_timestamp"]
    assert actual["data"]["logs"][1]["d_lang"] == "es"
    assert actual["data"]["logs"][1]["copy_type"] == "Translation"
    assert actual["data"]["logs"][1]["translate_responses"] == False
    assert actual["data"]["logs"][1]["translate_actions"] == False
    assert actual["data"]["logs"][1]["event_status"] == EVENT_STATUS.COMPLETED.value
    assert actual["data"]["logs"][1]["status"] == STATUSES.SUCCESS.value
    assert actual["data"]["logs"][1]["start_timestamp"]
    assert actual["data"]["logs"][1]["end_timestamp"]

    from_date = date.today()
    to_date = from_date + timedelta(days=1)
    search_response = client.get(
        f"/api/bot/{pytest.bot}/logs/multilingual/search?from_date={from_date}&to_date={to_date}&status=Success",
        headers={"Authorization": pytest.token_type + ' ' + pytest.access_token},
    )

    response_json = search_response.json()
    print("multilingual", response_json)
    assert response_json["success"] is True
    assert response_json["error_code"] == 0

    data = response_json["data"]
    assert "logs" in data
    assert isinstance(data["logs"], list)

def test_multilingual_language_support(monkeypatch):
    def _mock_supported_languages(*args, **kwargs):
        return {"ab": "Abkhaz",
                "ace": "Acehnese",
                "ach": "Acholi",
                "af": "Afrikaans",
                "sq": "Albanian",
                "alz": "Alur",
                "am": "Amharic",
                "ar": "Arabic",
                "hy": "Armenian",
                "as": "Assamese",
                "awa": "Awadhi",
                "ay": "Aymara"}

    monkeypatch.setattr(
        Translator, "get_supported_languages", _mock_supported_languages
    )

    response = client.get(
        f"/api/user/multilingual/languages",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()

    assert response["data"] == {"ab": "Abkhaz",
                                "ace": "Acehnese",
                                "ach": "Acholi",
                                "af": "Afrikaans",
                                "sq": "Albanian",
                                "alz": "Alur",
                                "am": "Amharic",
                                "ar": "Arabic",
                                "hy": "Armenian",
                                "as": "Assamese",
                                "awa": "Awadhi",
                                "ay": "Aymara"}
    assert response["success"]
    assert response["error_code"] == 0


def test_download_logs(monkeypatch):
    start_date = utc_now()
    end_date = utc_now() + timedelta(days=1)
    response = client.get(
        f"/api/bot/{pytest.bot}/logs/download/model_training?start_date={start_date}&end_date={end_date}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    response = response.json()
    assert response == {
        "success": False,
        "message": "Logs not found!",
        "data": None,
        "error_code": 422,
    }


def test_download_logs_with_action_logs(monkeypatch):
    import csv

    start_date = utc_now()
    end_date = utc_now() + timedelta(days=1)
    bot = pytest.bot
    request_params = {"key": "value", "key2": "value2"}
    ActionServerLogs(
        intent="intent1",
        action="http_action",
        sender="sender_id",
        timestamp="2021-04-05T07:59:08.771000",
        request_params=request_params,
        api_response="Response",
        bot_response="Bot Response",
        bot=bot,
    ).save()
    ActionServerLogs(
        intent="intent2",
        action="http_action",
        sender="sender_id",
        url="http://kairon-api.digite.com/api/bot",
        request_params=request_params,
        api_response="Response",
        bot_response="Bot Response",
        bot=bot,
        status=STATUSES.FAIL.value,
    ).save()
    ActionServerLogs(
        intent="intent3",
        action="http_action",
        sender="sender_id",
        request_params=request_params,
        api_response="Response",
        bot_response="Bot Response",
        bot=bot,
        status=STATUSES.FAIL.value,
    ).save()
    ActionServerLogs(
        intent="intent4",
        action="http_action",
        sender="sender_id",
        request_params=request_params,
        api_response="Response",
        bot_response="Bot Response",
        bot=bot,
    ).save()
    ActionServerLogs(
        intent="intent5",
        action="http_action",
        sender="sender_id",
        request_params=request_params,
        api_response="Response",
        bot_response="Bot Response",
        bot=bot,
        status=STATUSES.FAIL.value,
    ).save()

    response = client.get(
        f"/api/bot/{pytest.bot}/logs/download/action_logs?start_date={start_date}&end_date={end_date}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    assert response.content
    csv_content = response.content.decode("utf-8")
    csv_file = csv.reader(csv_content.splitlines())
    action_logs = list(csv_file)
    assert len(action_logs) == 5


def test_get_auditlog_for_user_1():
    email = "integration1234567890@demo.ai"
    response = client.post(
        "/api/auth/login",
        data={"username": email, "password": "Welcome@10"},
    )
    login = response.json()
    response = client.get(
        f"/api/user/auditlog/data",
        headers={
            "Authorization": login["data"]["token_type"]
                             + " "
                             + login["data"]["access_token"]
        },
    )

    actual = response.json()

    assert actual["data"] is not None
    assert actual["data"][0]["action"] == AuditlogActions.ACTIVITY.value
    assert actual["data"][0]["entity"] == "login"
    assert actual["data"][0]["user"] == email

    assert actual["data"][0]["action"] == AuditlogActions.ACTIVITY.value
    assert actual["data"][0]["attributes"][0]["value"] is not None


def test_get_auditlog_for_bot():
    from_date = utc_now().date() - timedelta(days=1)
    to_date = utc_now().date() + timedelta(days=1)
    response = client.get(
        f"/api/bot/{pytest.bot}/auditlog/data/{from_date}/{to_date}?start_idx=0&page_size=100",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    response = client.get(
        f"/api/bot/{pytest.bot}/logs/audit?from_date={from_date}&to_date={to_date}&start_idx=0&page_size=100",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    print(actual)
    audit_log_data = actual["data"]["logs"]

    assert audit_log_data is not None
    actions = [d["action"] for d in audit_log_data]
    from collections import Counter

    counter = Counter(actions)
    assert counter.get(AuditlogActions.SAVE.value) > 5
    assert counter.get(AuditlogActions.SOFT_DELETE.value) >= 3
    assert counter.get(AuditlogActions.UPDATE.value) > 5

    search_response = client.get(
        f"/api/bot/{pytest.bot}/logs/audit/search"
        f"?from_date={from_date}&to_date={to_date}"
        f"&start_idx=0&page_size=10",
        headers={"Authorization": f"{pytest.token_type} {pytest.access_token}"},
    )

    response_json = search_response.json()
    print("audit", response_json)
    assert response_json["success"] is True
    assert response_json["error_code"] == 0

    data = response_json["data"]
    assert "logs" in data
    assert isinstance(data["logs"], list)


@mock.patch('kairon.shared.account.activity_log.UserActivityLogger.is_login_within_cooldown_period', autospec=True)
def test_get_auditlog_for_user_2(mock_password_reset):
    def _password_reset(*args, **kwargs):
        return

    mock_password_reset.return_value = _password_reset
    email = "integration@demo.ai"
    response = client.post(
        "/api/auth/login",
        data={"username": email, "password": "Welcome@10"},
    )
    login_2 = response.json()
    response = client.get(
        f"/api/user/auditlog/data?start_idx=0&page_size=100",
        headers={
            "Authorization": login_2["data"]["token_type"]
                             + " "
                             + login_2["data"]["access_token"]
        },
    )
    actual = response.json()
    audit_log_data = actual["data"]
    assert audit_log_data is not None
    actions = [d["action"] for d in audit_log_data]
    from collections import Counter

    counter = Counter(actions)
    assert counter.get(AuditlogActions.SAVE.value) > 5
    assert counter.get(AuditlogActions.SOFT_DELETE.value) >= 1
    assert counter.get(AuditlogActions.UPDATE.value) >= 5

    assert audit_log_data[0]["action"] == AuditlogActions.ACTIVITY.value
    assert audit_log_data[0]["entity"] == "login"
    assert audit_log_data[0]["user"] == email


def test_add_custom_widget():
    response = client.post(
        url=f"/api/bot/{pytest.bot}/widgets/custom",
        json={
            "name": "agtech weekly trends",
            "http_url": "http://agtech.com/trends/1",
            "request_parameters": [
                {"key": "crop_type", "value": "tomato", "parameter_type": "value"},
                {"key": "org", "value": "ORG_NAME", "parameter_type": "key_vault"},
            ],
            "headers": [
                {"key": "client", "value": "kairon", "parameter_type": "value"},
                {
                    "key": "authorization",
                    "value": "AUTH_TOKEN",
                    "parameter_type": "key_vault",
                },
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Widget config added!"
    assert actual["data"]
    pytest.widget_id = actual["data"]
    assert actual["error_code"] == 0


def test_get_custom_widget():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/widgets/custom",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"]["widgets"] == [
        {
            "name": "agtech weekly trends",
            "http_url": "http://agtech.com/trends/1",
            "request_parameters": [
                {"key": "crop_type", "value": "tomato", "parameter_type": "value"},
                {"key": "org", "value": "ORG_NAME", "parameter_type": "key_vault"},
            ],
            "headers": [
                {"key": "client", "value": "kairon", "parameter_type": "value"},
                {
                    "key": "authorization",
                    "value": "AUTH_TOKEN",
                    "parameter_type": "key_vault",
                },
            ],
            "timeout": 5,
            "bot": pytest.bot,
            "request_method": "GET",
            "_id": pytest.widget_id,
        }
    ]
    assert actual["error_code"] == 0
    assert not actual["message"]


@responses.activate
def test_add_member_with_view_role():
    email = "test_view@demo.ai"
    response = client.post(
        "/api/account/registration",
        json={
            "email": email,
            "first_name": "Dem",
            "last_name": "User22",
            "password": "Welcome@10",
            "confirm_password": "Welcome@10",
            "account": email,
            "accepted_privacy_policy": True,
            "accepted_terms": True,
            "accepted_ai_guidelines": True
        },
    )
    actual = response.json()
    assert actual["message"] == "Account Registered!"
    assert actual["error_code"] == 0
    assert actual["success"]

    response = client.post(
        f"/api/user/{pytest.bot}/member",
        json={"email": email, "role": "view"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"]
    assert actual["error_code"] == 0
    assert actual["success"]

    response = client.post(
        "/api/auth/login",
        data={"username": email, "password": "Welcome@10"},
    )
    actual = response.json()

    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "User Authenticated"
    pytest.refresh_token_view_role = actual["data"]["refresh_token"]
    pytest.access_token_view_role = actual["data"]["access_token"]


@responses.activate
def test_trigger_widget():
    expected_query_parameters = {"crop_type": "tomato", "org": "kairon"}
    expected_query_parameters.update(
        {"start_date": "11-11-2021", "end_date": "21-11-2021"}
    )
    expected_resp = {"data": [{"1": 200, "2": 300, "3": 400, "4": 500, "5": 600}]}

    for key_vault in [
        {"key": "ORG_NAME", "value": "kairon"},
        {"key": "AUTH_TOKEN", "value": "sdfghjk456789"},
    ]:
        response = client.post(
            f"/api/bot/{pytest.bot}/secrets/add",
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
            json=key_vault,
        )
        actual = response.json()
        assert actual["error_code"] == 0
        assert actual["success"]

    responses.add(
        "GET",
        "http://agtech.com/trends/1",
        json=expected_resp,
        match=[
            responses.matchers.query_param_matcher(expected_query_parameters),
            responses.matchers.header_matcher(
                {"client": "kairon", "authorization": "sdfghjk456789"}
            ),
        ],
    )

    # Test with view role
    response = client.get(
        url=f"/api/bot/{pytest.bot}/widgets/custom/trigger/{pytest.widget_id}?start_date=11-11-2021&end_date=21-11-2021",
        headers={
            "Authorization": pytest.token_type + " " + pytest.access_token_view_role
        },
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] == expected_resp
    assert not actual["message"]

    # Test with admin role
    response = client.get(
        url=f"/api/bot/{pytest.bot}/widgets/custom/trigger/{pytest.widget_id}?start_date=11-11-2021&end_date=21-11-2021",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] == expected_resp
    assert not actual["message"]

    response = client.get(
        url=f"/api/bot/{pytest.bot}/widgets/custom/logs/all",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]) == 2
    assert not actual["message"]


def test_get_llm_logs():
    import asyncio
    from kairon.shared.actions.utils import ActionUtility
    from kairon.shared.llm.data_objects import LLMLogs
    from unittest.mock import patch, AsyncMock

    loop = asyncio.new_event_loop()
    user = "test"

    messages = [{"role": "user", "content": "Hi"}]
    expected = "Hi, How may i help you?"

    mock_llm_http_response = {
        "formatted_response": {
            "choices": [
                {
                    "message": {
                        "content": expected
                    }
                }
            ]
        },
        "response": {}
    }

    mock_return = (
        mock_llm_http_response,
        200,
        0.05,
        {}
    )

    with patch.object(
            ActionUtility,
            "execute_request_async",
            new=AsyncMock(return_value=mock_return)
    ):
        from kairon.shared.llm.processor import LLMProcessor

        processor = LLMProcessor(bot=pytest.bot, llm_type="openai")

        formatted_response, raw_response = loop.run_until_complete(
            processor._LLMProcessor__get_completion(
                messages=messages,
                hyperparameters={},
                user=user,
                invocation="prompt_action",
                media_ids=[],
                should_process_media=False
            )
        )
        assert formatted_response["choices"][0]["message"]["content"] == expected
        import uuid

        call_id = str(uuid.uuid4())

        log_data = LLMLogs(
            llm_call_id=call_id,
            llm_provider="openai",
            model=None,
            model_params={},
            metadata={
                "user": user,
                "bot": pytest.bot,
                "invocation": "prompt_action"
            },
            response=raw_response,
            start_time=utc_now(),
            end_time=utc_now(),
            cost=0.0
        )

        log_data.save()

    time.sleep(2)

    response = client.get(
        f"/api/bot/{pytest.bot}/llm/logs?start_idx=0&page_size=10",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    response = client.get(
        f"/api/bot/{pytest.bot}/logs/llm?start_idx=0&page_size=10",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    print(actual["data"])
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]

    from_date = utc_now().date() - timedelta(days=1)
    to_date = utc_now().date() + timedelta(days=1)
    search_response = client.get(
        f"/api/bot/{pytest.bot}/logs/llm/search?from_date={from_date}&to_date={to_date}&user=test",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = search_response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]["logs"]) == 1
    assert actual["data"]["total"] == 1
    assert actual["data"]["logs"][0]['start_time']
    assert actual["data"]["logs"][0]['end_time']
    assert 'cost' in actual["data"]["logs"][0]
    assert actual["data"]["logs"][0]['llm_call_id']
    assert actual["data"]["logs"][0]["llm_provider"] == "openai"
    assert not actual["data"]["logs"][0].get("model")
    assert actual["data"]["logs"][0]["model_params"] == {}
    assert actual["data"]["logs"][0]["metadata"]['bot'] == pytest.bot
    assert actual["data"]["logs"][0]["metadata"]['user'] == "test"
    assert not actual["data"]["logs"][0].get('response', {}).get("data", None)
    call_id = actual["data"]["logs"][0]['llm_call_id']

    search_with_invocation = client.get(
        f"/api/bot/{pytest.bot}/logs/llm/search?from_date={from_date}&to_date={to_date}&user=test&invocation=prompt_action",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = search_with_invocation.json()
    print(actual)
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]["logs"]) == 1

    search_with_call_id = client.get(
        f"/api/bot/{pytest.bot}/logs/llm/search?from_date={from_date}&to_date={to_date}&user=test&llm_call_id={call_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = search_with_call_id.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]["logs"]) == 1
    assert actual["data"]["total"] == 1
    assert actual["data"]["logs"][0]['start_time']
    assert actual["data"]["logs"][0]['end_time']
    assert 'cost' in actual["data"]["logs"][0]
    assert actual["data"]["logs"][0]['llm_call_id']
    assert actual["data"]["logs"][0]["llm_provider"] == "openai"
    assert not actual["data"]["logs"][0].get("model")
    assert actual["data"]["logs"][0]["model_params"] == {}
    assert actual["data"]["logs"][0]["metadata"]['bot'] == pytest.bot
    assert actual["data"]["logs"][0]["metadata"]['user'] == "test"
    assert not actual["data"]["logs"][0].get('response', {}).get("data", None)

    llm_call_id_param = f"'{call_id}'"
    search_with_call_id = client.get(
        f"/api/bot/{pytest.bot}/logs/llm/search?from_date={from_date}&to_date={to_date}&user=test&llm_call_id={llm_call_id_param}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = search_with_call_id.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]["logs"]) == 1
    assert actual["data"]["total"] == 1
    assert actual["data"]["logs"][0]['start_time']
    assert actual["data"]["logs"][0]['end_time']
    assert 'cost' in actual["data"]["logs"][0]
    assert actual["data"]["logs"][0]['llm_call_id']
    assert actual["data"]["logs"][0]["llm_provider"] == "openai"
    assert not actual["data"]["logs"][0].get("model")
    assert actual["data"]["logs"][0]["model_params"] == {}
    assert actual["data"]["logs"][0]["metadata"]['bot'] == pytest.bot
    assert actual["data"]["logs"][0]["metadata"]['user'] == "test"
    assert not actual["data"]["logs"][0].get('response', {}).get("data", None)

    llm_call_id_param = [call_id]

    response = client.get(
        f"/api/bot/{pytest.bot}/logs/llm/search?"
        f"from_date={from_date}&to_date={to_date}&user=test&llm_call_id={llm_call_id_param}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()

    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]["logs"]) == 1
    assert actual["data"]["total"] == 1

    log = actual["data"]["logs"][0]
    assert log["llm_call_id"] == call_id
    assert log["metadata"]["bot"] == pytest.bot
    assert log["metadata"]["user"] == "test"

    llm_call_id_param = f"['{call_id}']"

    response = client.get(
        f"/api/bot/{pytest.bot}/logs/llm/search?"
        f"from_date={from_date}&to_date={to_date}&user=test&llm_call_id={llm_call_id_param}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()

    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]["logs"]) == 1
    assert actual["data"]["total"] == 1

    log = actual["data"]["logs"][0]
    assert log["llm_call_id"] == call_id
    assert log["metadata"]["bot"] == pytest.bot
    assert log["metadata"]["user"] == "test"


def test_add_custom_widget_invalid_config():
    response = client.post(
        url=f"/api/bot/{pytest.bot}/widgets/custom",
        json={
            "name": "agtech weekly trends 1",
            "http_url": "http://agtech.com/trends/1",
            "request_parameters": [
                {"key": "crop_type", "value": "tomato", "parameter_type": "sender_id"},
                {"key": "org", "value": "ORG_NAME", "parameter_type": "key_vault"},
            ],
            "headers": [
                {"key": "client", "value": "kairon", "parameter_type": "value"},
                {
                    "key": "authorization",
                    "value": "AUTH_TOKEN",
                    "parameter_type": "key_vault",
                },
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == [
        {
            "ctx": {"enum_values": ["value", "key_vault"]},
            "loc": ["body", "request_parameters", 0, "parameter_type"],
            "msg": "value is not a valid enumeration member; permitted: 'value', 'key_vault'",
            "type": "type_error.enum",
        }
    ]
    assert not actual["data"]
    assert actual["error_code"] == 422


def test_add_custom_widget_already_exists():
    response = client.post(
        url=f"/api/bot/{pytest.bot}/widgets/custom",
        json={
            "name": "agtech weekly trends",
            "http_url": "http://agtech.com/trends/1",
            "request_parameters": [
                {"key": "crop_type", "value": "tomato", "parameter_type": "value"},
                {"key": "org", "value": "ORG_NAME", "parameter_type": "key_vault"},
            ],
            "headers": [
                {"key": "client", "value": "kairon", "parameter_type": "value"},
                {
                    "key": "authorization",
                    "value": "AUTH_TOKEN",
                    "parameter_type": "key_vault",
                },
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Widget with name exists!"
    assert not actual["data"]
    assert actual["error_code"] == 422


def test_edit_custom_widget_invalid_config():
    response = client.put(
        url=f"/api/bot/{pytest.bot}/widgets/custom/{pytest.widget_id}",
        json={"name": "agtech weekly trends 1", "http_url": None},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == [
        {
            "loc": ["body", "http_url"],
            "msg": "none is not an allowed value",
            "type": "type_error.none.not_allowed",
        }
    ]
    assert not actual["data"]
    assert actual["error_code"] == 422


def test_edit_custom_widget():
    response = client.put(
        url=f"/api/bot/{pytest.bot}/widgets/custom/{pytest.widget_id}",
        json={
            "name": "agtech trends ",
            "http_url": "http://agtech.com/trends",
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Widget config updated!"
    assert not actual["data"]
    assert actual["error_code"] == 0


def test_list_custom_widgets():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/widgets/custom/list",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"]["widgets"] == [pytest.widget_id]
    assert actual["error_code"] == 0
    assert not actual["message"]


def test_get_custom_widget_post_update():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/widgets/custom",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"]["widgets"] == [
        {
            "name": "agtech trends ",
            "http_url": "http://agtech.com/trends",
            "timeout": 5,
            "request_method": "GET",
            "request_parameters": [],
            # "_id": pytest.bot,
            "headers": [],
            "bot": pytest.bot,
            "_id": pytest.widget_id,
        }
    ]
    assert actual["error_code"] == 0
    assert not actual["message"]


def test_delete_custom_widget():
    response = client.delete(
        url=f"/api/bot/{pytest.bot}/widgets/custom/{pytest.widget_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Widget config removed!"
    assert not actual["data"]
    assert actual["error_code"] == 0


def test_trigger_widget_failure():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/widgets/custom/trigger/{pytest.widget_id}",
        headers={
            "Authorization": pytest.token_type + " " + pytest.access_token_view_role
        },
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert not actual["data"]
    assert actual["message"] == "Widget does not exists!"


def test_delete_custom_widget_invalid_widget_id():
    response = client.delete(
        url=f"/api/bot/{pytest.bot}/widgets/custom/{pytest.widget_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Widget does not exists!"
    assert not actual["data"]
    assert actual["error_code"] == 422


def test_list_custom_widgets_empty():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/widgets/custom",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"]["widgets"] == []
    assert actual["error_code"] == 0
    assert not actual["message"]


def test_get_custom_widget_post_delete():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/widgets/custom",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["data"]["widgets"]
    assert actual["error_code"] == 0
    assert not actual["message"]
