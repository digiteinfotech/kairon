from tests.integration_test.services_support import *  # noqa: F403
from tests.integration_test.services_support import setup, fast_rasa_training



def test_channels_params():
    response = client.get(
        f"/api/bot/{pytest.bot}/channels/params",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert "slack" in list(actual["data"].keys())
    assert [
               "bot_user_oAuth_token",
               "slack_signing_secret",
               "client_id",
               "client_secret",
           ] == actual["data"]["slack"]["required_fields"]
    assert ["slack_channel", "team", "is_primary"] == actual["data"]["slack"][
        "optional_fields"
    ]
    assert ["team", "is_primary"] == actual["data"]["slack"]["disabled_fields"]


def test_get_channel_endpoint_not_configured():
    response = client.get(
        f"/api/bot/{pytest.bot}/channels/slack/endpoint",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert not actual["data"]
    assert actual["message"] == "Channel not configured"

def test_add_instagram_channel():
    response = client.post(
        f"/api/bot/{pytest.bot}/channels/add",
        json={
            "connector_type": "instagram",
            "config": {
                "app_secret": "98730987654321",
                "page_access_token": "accessangtoken",
                "verify_token": "tokenvld",
                "static_comment_reply": "welcome"
            }
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"] is True
    assert actual["data"]
    assert 'Channel' in actual["message"]

def test_missing_valid_config_instagram_channel():
    response = client.post(
        f"/api/bot/{pytest.bot}/channels/add",
        json={
            "connector_type": "instagram",
            "config": {
                "app_secret": "98730987654321",
                "page_access_token": "accessangtoken",
                "static_comment_reply": "welcome"
            }
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"] is False
    assert actual["data"] is None
    assert "verify_token" in actual["message"][0]["msg"]

def test_voice_channel_params():
    response = client.get(
        f"/api/bot/{pytest.bot}/channels/voice/params",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert "twilio" in actual["data"]


def test_list_voice_channel_config_empty():
    response = client.get(
        f"/api/bot/{pytest.bot}/channels/voice/list",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] == []


def test_add_voice_call_action_voice_not_enabled():
    response = client.post(
        f"/api/bot/{pytest.bot}/action/voicecall",
        json={
            "name": "test_voice_call_action",
            "to_phone_number": {"value": "+1234567890", "parameter_type": "value"},
            "telephony_provider": "twilio",
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert "Voice is not enabled" in actual["message"]


def test_add_voice_call_action(monkeypatch):
    monkeypatch.setattr(MongoProcessor, "is_voice_enabled", lambda *a, **kw: True)
    response = client.post(
        f"/api/bot/{pytest.bot}/action/voicecall",
        json={
            "name": "test_voice_call_action",
            "to_phone_number": {"value": "+1234567890", "parameter_type": "value"},
            "telephony_provider": "twilio",
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action added"


def test_add_voice_call_action_duplicate(monkeypatch):
    monkeypatch.setattr(MongoProcessor, "is_voice_enabled", lambda *a, **kw: True)
    response = client.post(
        f"/api/bot/{pytest.bot}/action/voicecall",
        json={
            "name": "test_voice_call_action",
            "to_phone_number": {"value": "+1234567890", "parameter_type": "value"},
            "telephony_provider": "twilio",
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert "Action exists!" in actual["message"]


def test_add_voice_call_action_missing_name():
    response = client.post(
        f"/api/bot/{pytest.bot}/action/voicecall",
        json={
            "to_phone_number": {"value": "+1234567890", "parameter_type": "value"},
            "telephony_provider": "twilio",
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]


def test_list_voice_call_actions():
    response = client.get(
        f"/api/bot/{pytest.bot}/action/voicecall",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert isinstance(actual["data"], list)
    assert len(actual["data"]) >= 1
    assert any(a["name"] == "test_voice_call_action" for a in actual["data"])


def test_edit_voice_call_action_voice_not_enabled():
    response = client.put(
        f"/api/bot/{pytest.bot}/action/voicecall",
        json={
            "name": "test_voice_call_action",
            "to_phone_number": {"value": "+19999999999", "parameter_type": "value"},
            "telephony_provider": "twilio",
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert "Voice is not enabled" in actual["message"]


def test_edit_voice_call_action_not_found(monkeypatch):
    monkeypatch.setattr(MongoProcessor, "is_voice_enabled", lambda *a, **kw: True)
    response = client.put(
        f"/api/bot/{pytest.bot}/action/voicecall",
        json={
            "name": "nonexistent_voice_action",
            "to_phone_number": {"value": "+1234567890", "parameter_type": "value"},
            "telephony_provider": "twilio",
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert "not found" in actual["message"]


def test_edit_voice_call_action(monkeypatch):
    monkeypatch.setattr(MongoProcessor, "is_voice_enabled", lambda *a, **kw: True)
    response = client.put(
        f"/api/bot/{pytest.bot}/action/voicecall",
        json={
            "name": "test_voice_call_action",
            "to_phone_number": {"value": "+19999999999", "parameter_type": "value"},
            "telephony_provider": "twilio",
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action updated"


def test_add_kairon_voice_disconnect():
    response = client.post(
        f"/api/bot/{pytest.bot}/action/voice_disconnect",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action added"


def test_add_kairon_voice_disconnect_idempotent():
    response = client.post(
        f"/api/bot/{pytest.bot}/action/voice_disconnect",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action added"


def test_list_kairon_voice_disconnect():
    response = client.get(
        f"/api/bot/{pytest.bot}/action/voice_disconnect",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert isinstance(actual["data"], list)
    assert len(actual["data"]) >= 1


def test_add_store_page_action():
    response = client.post(
        f"/api/bot/{pytest.bot}/action/store_page",
        json={"name": "test_store_page_action", "page_name": "home", "identifier_slot": "phone_number"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action added"


def test_add_store_page_action_duplicate():
    response = client.post(
        f"/api/bot/{pytest.bot}/action/store_page",
        json={"name": "test_store_page_action", "page_name": "home", "identifier_slot": "phone_number"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_add_store_page_action_missing_fields():
    response = client.post(
        f"/api/bot/{pytest.bot}/action/store_page",
        json={"name": "test_store_page_action_missing"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]


def test_list_store_page_actions():
    response = client.get(
        f"/api/bot/{pytest.bot}/action/store_page",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert isinstance(actual["data"], list)
    assert any(a["name"] == "test_store_page_action" for a in actual["data"])


def test_edit_store_page_action_not_found():
    response = client.put(
        f"/api/bot/{pytest.bot}/action/store_page",
        json={"name": "nonexistent_store_page_action", "page_name": "menu", "identifier_slot": "customer_id"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_edit_store_page_action():
    response = client.put(
        f"/api/bot/{pytest.bot}/action/store_page",
        json={"name": "test_store_page_action", "page_name": "menu", "identifier_slot": "customer_id"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action updated"


def test_delete_store_page_action_not_found():
    response = client.delete(
        f"/api/bot/{pytest.bot}/action/store_page/nonexistent_store_page_action",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_delete_store_page_action():
    response = client.delete(
        f"/api/bot/{pytest.bot}/action/store_page/test_store_page_action",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action deleted"


def test_get_store_page_metadata_not_found():
    response = client.get(
        f"/api/bot/{pytest.bot}/store_page/metadata",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert "not found" in actual["message"].lower()


def test_get_store_page_metadata():
    from kairon.shared.data.data_objects import StorePageMetadata
    StorePageMetadata.objects(bot=pytest.bot).delete()
    StorePageMetadata(
        bot=pytest.bot,
        user="testUser",
        config={"base_url": "https://store.example.com", "catalog_id": "cat_001"},
    ).save()
    response = client.get(
        f"/api/bot/{pytest.bot}/store_page/metadata",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["bot"] == pytest.bot
    assert actual["data"]["config"]["base_url"] == "https://store.example.com"
    StorePageMetadata.objects(bot=pytest.bot).delete()


def test_add_asset(monkeypatch):
    def __mock_file_upload(*args, **kwargs):
        return "https://kairon.s3.amazonaws.com/application/626a380d3060cf93782b52c3/actions_yml.yml"

    monkeypatch.setattr(CloudUtility, "upload_file", __mock_file_upload)
    monkeypatch.setitem(
        Utility.environment["storage"]["assets"], "allowed_extensions", [".yml"]
    )

    file = {"asset": open("tests/testing_data/valid_yml/actions.yml", "rb")}
    response = client.put(
        f"/api/bot/{pytest.bot}/assets/actions_yml",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=file,
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert (
            actual["data"]["url"]
            == "https://kairon.s3.amazonaws.com/application/626a380d3060cf93782b52c3/actions_yml.yml"
    )
    assert actual["message"] == "Asset added"


def test_add_asset_failure(monkeypatch):
    def __mock_file_upload(*args, **kwargs):
        api_resp = {
            "Error": {"Code": "400", "Message": "Bad Request"},
            "ResponseMetadata": {
                "RequestId": "BQFVQHD1KSD5V6RZ",
                "HostId": "t2uudD7x2V+rRHO4dp2XBqdmAOaWwlnsII7gs1JbYcrntVKRaZSpHxNPJEww+s5dCzCQOg2uero=",
                "HTTPStatusCode": 400,
                "HTTPHeaders": {
                    "x-amz-bucket-region": "us-east-1",
                    "x-amz-request-id": "BQFVQHD1KSD5V6RZ",
                    "x-amz-id-2": "t2uudD7x2V+rRHO4dp2XBqdmAOaWwlnsII7gs1JbYcrntVKRaZSpHxNPJEww+s5dCzCQOg2uero=",
                    "content-type": "application/xml",
                    "date": "Wed, 27 Apr 2022 08:53:05 GMT",
                    "server": "AmazonS3",
                    "connection": "close",
                },
                "RetryAttempts": 3,
            },
        }
        raise ClientError(api_resp, "PutObject")

    monkeypatch.setattr(CloudUtility, "upload_file", __mock_file_upload)
    monkeypatch.setitem(
        Utility.environment["storage"]["assets"], "allowed_extensions", [".yml"]
    )

    file = {"asset": open("tests/testing_data/valid_yml/actions.yml", "rb")}
    response = client.put(
        f"/api/bot/{pytest.bot}/assets/actions_yml",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=file,
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert not actual["data"]
    assert actual["message"] == "File upload failed"


def test_list_assets():
    response = client.get(
        f"/api/bot/{pytest.bot}/assets",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["assets"] == [
        {
            "asset_type": "actions_yml",
            "url": "https://kairon.s3.amazonaws.com/application/626a380d3060cf93782b52c3/actions_yml.yml",
        }
    ]


def test_delete_asset(monkeypatch):
    def __mock_delete_file(*args, **kwargs):
        return None

    monkeypatch.setattr(CloudUtility, "delete_file", __mock_delete_file)

    response = client.delete(
        f"/api/bot/{pytest.bot}/assets/actions_yml",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert not actual["data"]
    assert actual["message"] == "Asset deleted"


def test_delete_asset_not_exists():
    response = client.delete(
        f"/api/bot/{pytest.bot}/assets/actions_yml",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert not actual["data"]
    assert actual["message"] == "Asset does not exists"


def test_list_assets_not_exists():
    response = client.get(
        f"/api/bot/{pytest.bot}/assets",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["assets"] == []


def test_get_live_agent_config_params():
    response = client.get(
        f"/api/bot/{pytest.bot}/agents/live/params",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] == Utility.system_metadata["live_agents"]


def test_get_live_agent_config_none():
    response = client.get(
        f"/api/bot/{pytest.bot}/agents/live",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["agent"] is None


@responses.activate
def test_add_live_agent_config_agent_not_supported():
    config = {
        "agent_type": "livechat",
        "config": {"account_id": "12", "api_access_token": "asdfghjklty67"},
        "override_bot": False,
        "trigger_on_intents": ["greet", "enquiry"],
        "trigger_on_actions": ["action_default_fallback", "action_enquiry"],
    }

    response = client.put(
        f"/api/bot/{pytest.bot}/agents/live",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=config,
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert not actual["data"]
    assert actual["message"] == [
        {
            "loc": ["body", "agent_type"],
            "msg": "Agent system not supported",
            "type": "value_error",
        }
    ]


@responses.activate
def test_add_live_agent_config_required_fields_not_exists():
    config = {
        "agent_type": "chatwoot",
        "config": {"api_access_token": "asdfghjklty67"},
        "override_bot": False,
        "trigger_on_intents": ["greet", "enquiry"],
        "trigger_on_actions": ["action_default_fallback", "action_enquiry"],
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/agents/live",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=config,
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert not actual["data"]
    assert actual["message"] == [
        {
            "loc": ["body", "config"],
            "msg": "Missing ['api_access_token', 'account_id'] all or any in config",
            "type": "value_error",
        }
    ]

    config = {
        "agent_type": "chatwoot",
        "config": {"account_id": "12"},
        "override_bot": False,
        "trigger_on_intents": ["greet", "enquiry"],
        "trigger_on_actions": ["action_default_fallback", "action_enquiry"],
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/agents/live",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=config,
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert not actual["data"]
    assert actual["message"] == [
        {
            "loc": ["body", "config"],
            "msg": "Missing ['api_access_token', 'account_id'] all or any in config",
            "type": "value_error",
        }
    ]


@responses.activate
def test_add_live_agent_config_invalid_credentials():
    config = {
        "agent_type": "chatwoot",
        "config": {"account_id": "12", "api_access_token": "asdfghjklty67"},
        "override_bot": False,
        "trigger_on_intents": ["greet", "enquiry"],
        "trigger_on_actions": ["action_default_fallback", "action_enquiry"],
    }

    responses.add(
        "GET",
        f"https://app.chatwoot.com/public/api/v1/accounts/{config['config']['account_id']}/inboxes",
        status=404,
        body="Not found",
    )
    response = client.put(
        f"/api/bot/{pytest.bot}/agents/live",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=config,
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert not actual["data"]
    assert actual["message"] == "Unable to connect. Please verify credentials."


@responses.activate
def test_add_live_agent_config_triggers_not_added():
    config = {
        "agent_type": "chatwoot",
        "config": {"account_id": "12", "api_access_token": "asdfghjklty67"},
        "override_bot": False,
    }

    add_inbox_response = open(
        "tests/testing_data/live_agent/add_inbox_response.json"
    ).read()
    add_inbox_response = json.loads(add_inbox_response)
    responses.add(
        "GET",
        f"https://app.chatwoot.com/api/v1/accounts/{config['config']['account_id']}/inboxes",
        json={"payload": []},
    )
    responses.add(
        "POST",
        f"https://app.chatwoot.com/api/v1/accounts/{config['config']['account_id']}/inboxes",
        json=add_inbox_response,
    )

    response = client.put(
        f"/api/bot/{pytest.bot}/agents/live",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=config,
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert not actual["data"]
    assert actual["message"] == [
        {
            "loc": ["body", "override_bot"],
            "msg": "At least 1 intent or action is required to perform agent handoff",
            "type": "value_error",
        }
    ]

    config = {
        "agent_type": "chatwoot",
        "config": {"account_id": "12", "api_access_token": "asdfghjklty67"},
        "override_bot": False,
        "trigger_on_intents": [],
        "trigger_on_actions": [],
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/agents/live",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=config,
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert not actual["data"]
    assert actual["message"] == [
        {
            "loc": ["body", "override_bot"],
            "msg": "At least 1 intent or action is required to perform agent handoff",
            "type": "value_error",
        }
    ]


@responses.activate
def test_add_live_agent_config():
    config = {
        "agent_type": "chatwoot",
        "config": {"account_id": "12", "api_access_token": "asdfghjklty67"},
        "override_bot": False,
        "trigger_on_intents": ["greet", "enquiry"],
        "trigger_on_actions": ["action_default_fallback", "action_enquiry"],
    }

    add_inbox_response = open(
        "tests/testing_data/live_agent/add_inbox_response.json"
    ).read()
    add_inbox_response = json.loads(add_inbox_response)
    responses.add(
        "GET",
        f"https://app.chatwoot.com/api/v1/accounts/{config['config']['account_id']}/inboxes",
        json={"payload": []},
    )
    responses.add(
        "POST",
        f"https://app.chatwoot.com/api/v1/accounts/{config['config']['account_id']}/inboxes",
        json=add_inbox_response,
    )

    response = client.put(
        f"/api/bot/{pytest.bot}/agents/live",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=config,
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert not actual["data"]
    assert actual["message"] == "Live agent system added"


def test_get_live_agent_config():
    response = client.get(
        f"/api/bot/{pytest.bot}/agents/live",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    add_inbox_response = open(
        "tests/testing_data/live_agent/add_inbox_response.json"
    ).read()
    add_inbox_response = json.loads(add_inbox_response)
    assert actual["data"]["agent"]
    actual["data"]["agent"].pop("timestamp")
    assert actual["data"]["agent"] == {
        "agent_type": "chatwoot",
        "config": {
            "account_id": "***",
            "api_access_token": "asdfghjklt***",
            "inbox_identifier": add_inbox_response["inbox_identifier"],
        },
        "override_bot": False,
        "trigger_on_intents": ["greet", "enquiry"],
        "trigger_on_actions": ["action_default_fallback", "action_enquiry"],
    }


@responses.activate
def test_update_live_agent_config():
    add_inbox_response = open(
        "tests/testing_data/live_agent/add_inbox_response.json"
    ).read()
    add_inbox_response = json.loads(add_inbox_response)
    add_inbox_response["inbox_identifier"] = "sdghghj5466789fghjk"
    list_inbox_response = open(
        "tests/testing_data/live_agent/list_inboxes_response.json"
    ).read()
    list_inbox_response = json.loads(list_inbox_response)
    list_inbox_response["payload"][1]["inbox_identifier"] = add_inbox_response[
        "inbox_identifier"
    ]
    config = {
        "agent_type": "chatwoot",
        "config": {
            "account_id": "13",
            "api_access_token": "jfjdjhsk567890",
            "inbox_identifier": add_inbox_response["inbox_identifier"],
        },
        "override_bot": True,
    }
    responses.add(
        "GET",
        f"https://app.chatwoot.com/api/v1/accounts/{config['config']['account_id']}/inboxes",
        json=list_inbox_response,
    )
    responses.add(
        "POST",
        f"https://app.chatwoot.com/api/v1/accounts/{config['config']['account_id']}/inboxes",
        json=add_inbox_response,
    )

    response = client.put(
        f"/api/bot/{pytest.bot}/agents/live",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=config,
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert not actual["data"]
    assert actual["message"] == "Live agent system added"


def test_get_live_agent_config_after_update():
    response = client.get(
        f"/api/bot/{pytest.bot}/agents/live",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["agent"]
    actual["data"]["agent"].pop("timestamp")
    assert actual["data"]["agent"] == {
        "agent_type": "chatwoot",
        "config": {
            "account_id": "***",
            "api_access_token": "jfjdjhsk567***",
            "inbox_identifier": "sdghghj5466789fghjk",
        },
        "override_bot": True,
        "trigger_on_intents": [],
        "trigger_on_actions": [],
    }


def test_delete_live_agent_config():
    response = client.delete(
        f"/api/bot/{pytest.bot}/agents/live",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert not actual["data"]
    assert actual["message"] == "Live agent system deleted"


def test_get_live_agent_config_after_delete():
    response = client.get(
        f"/api/bot/{pytest.bot}/agents/live",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["agent"] is None
