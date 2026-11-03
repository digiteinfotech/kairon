from tests.integration_test.services_support import *  # noqa: F403
from tests.integration_test.services_support import setup, fast_rasa_training



def test_list_keys_none():
    response = client.get(
        f"/api/bot/{pytest.bot}/secrets/keys",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"] == []
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])
    assert actual["success"]


def test_add_secret():
    request = {"key": "AWS_KEY", "value": "123456789asdfghjk"}
    response = client.post(
        f"/api/bot/{pytest.bot}/secrets/add",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=request,
    )
    actual = response.json()
    assert not Utility.check_empty_string(actual["data"]["key_id"])
    assert actual["error_code"] == 0
    assert actual["message"] == "Secret added!"
    assert actual["success"]


def test_add_secret_invalid_request():
    request = {"key": None, "value": "123456789asdfghjk"}
    response = client.post(
        f"/api/bot/{pytest.bot}/secrets/add",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=request,
    )
    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 422
    assert not actual["success"]

    request = {"key": "AWS_KEY", "value": None}
    response = client.post(
        f"/api/bot/{pytest.bot}/secrets/add",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=request,
    )
    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 422
    assert not actual["success"]


def test_add_secret_already_exists():
    request = {"key": "AWS_KEY", "value": "123456789asdfghjk"}
    response = client.post(
        f"/api/bot/{pytest.bot}/secrets/add",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=request,
    )
    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 422
    assert actual["message"] == "Key exists!"
    assert not actual["success"]


def test_get_secret_not_exists():
    response = client.get(
        f"/api/bot/{pytest.bot}/secrets/keys/GOOGLE_KEY",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 422
    assert not actual["success"]
    assert actual["message"] == "key 'GOOGLE_KEY' does not exists!"


def test_get_secret():
    response = client.get(
        f"/api/bot/{pytest.bot}/secrets/keys/AWS_KEY",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"] == "123456789asdfghjk"
    assert actual["error_code"] == 0
    assert actual["success"]


def test_update_secret():
    request = {"key": "AWS_KEY", "value": "123456789"}
    response = client.put(
        f"/api/bot/{pytest.bot}/secrets/update",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=request,
    )
    actual = response.json()
    assert not Utility.check_empty_string(actual["data"]["key_id"])
    assert actual["error_code"] == 0
    assert actual["message"] == "Secret updated!"
    assert actual["success"]


def test_add_secret_2():
    request = {"key": "GOOGLE_KEY", "value": "sdfghj45678"}
    response = client.post(
        f"/api/bot/{pytest.bot}/secrets/add",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=request,
    )
    actual = response.json()
    assert not Utility.check_empty_string(actual["data"]["key_id"])
    assert actual["error_code"] == 0
    assert actual["message"] == "Secret added!"
    assert actual["success"]


def test_update_secret_invalid_request():
    request = {"key": "  ", "value": "123456789"}
    response = client.put(
        f"/api/bot/{pytest.bot}/secrets/update",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=request,
    )
    actual = response.json()
    assert Utility.check_empty_string(actual["data"])
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {"loc": ["body", "key"], "msg": "key is required", "type": "value_error"}
    ]
    assert not actual["success"]

    request = {"key": "AWS_KEY", "value": "  "}
    response = client.put(
        f"/api/bot/{pytest.bot}/secrets/update",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=request,
    )
    actual = response.json()
    assert Utility.check_empty_string(actual["data"])
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {"loc": ["body", "value"], "msg": "value is required", "type": "value_error"}
    ]
    assert not actual["success"]


def test_update_secret_not_exists():
    request = {"key": "GCP_KEY", "value": "123456789"}
    response = client.put(
        f"/api/bot/{pytest.bot}/secrets/update",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=request,
    )
    actual = response.json()
    assert Utility.check_empty_string(actual["data"])
    assert actual["error_code"] == 422
    assert actual["message"] == "key 'GCP_KEY' does not exists!"
    assert not actual["success"]


def test_list_keys():
    response = client.get(
        f"/api/bot/{pytest.bot}/secrets/keys",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"] == ["AWS_KEY", "GOOGLE_KEY"]
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])
    assert actual["success"]


def test_delete_secret():
    response = client.delete(
        f"/api/bot/{pytest.bot}/secrets/AWS_KEY",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 0
    assert actual["message"] == "Secret deleted!"
    assert actual["success"]


def test_delete_secret_not_exists():
    response = client.delete(
        f"/api/bot/{pytest.bot}/secrets/AWS_KEY",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 422
    assert actual["message"] == "key 'AWS_KEY' does not exists!"
    assert not actual["success"]


def test_add_secret_with_deleted_key():
    request = {"key": "AWS_KEY", "value": "123456789asdfghjk"}
    response = client.post(
        f"/api/bot/{pytest.bot}/secrets/add",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=request,
    )
    actual = response.json()
    assert not Utility.check_empty_string(actual["data"]["key_id"])
    assert actual["error_code"] == 0
    assert actual["message"] == "Secret added!"
    assert actual["success"]


def test_get_secret_2():
    response = client.get(
        f"/api/bot/{pytest.bot}/secrets/keys/AWS_KEY",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"] == "123456789asdfghjk"
    assert actual["error_code"] == 0
    assert actual["success"]


def test_add_vectordb_action_empty_payload():
    request_body = {
        "name": "add_vectordb_action_empty_payload",
        "collection": 'test_add_vectordb_action_empty_name',
        "payload": [],
        "response": {"value": "0"},
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/db",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()

    assert actual["error_code"] == 422
    assert actual["message"] == [
        {"loc": ["body", "payload"], "msg": "payload is required", "type": "value_error"}
    ]
    assert not actual["success"]


def test_add_vectordb_action_empty_name():
    request_body = {
        "name": "",
        "collection": 'test_add_vectordb_action_empty_name',
        "payload": [{
            "type": "from_value",
            "value": {"ids": [0], "with_payload": True, "with_vector": True},
            "query_type": "embedding_search",
        }],
        "response": {"value": "0"},
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/db",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()

    assert actual["error_code"] == 422
    assert actual["message"] == [
        {"loc": ["body", "name"], "msg": "name is required", "type": "value_error"}
    ]
    assert not actual["success"]


def test_add_vectordb_action_with_utter():
    request_body = {
        "name": "utter_add_vectordb_action",
        "collection": 'test_add_vectordb_action_empty_name',
        "payload": [{
            "type": "from_value",
            "value": {"ids": [0], "with_payload": True, "with_vector": True},
            "query_type": "embedding_search",
        }],
        "response": {"value": "0"},
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/db",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == "Action name cannot start with utter_"
    assert not actual["success"]


def test_add_vectordb_action_empty_collection_name():
    request_body = {
        "name": 'test_add_vectordb_action_empty_collection_name',
        "collection": '',
        "payload": [{"type": "from_value", "value": {"ids": [0], "with_payload": True, "with_vector": True}, "query_type": "embedding_search",}],
        "response": {"value": "0"}
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/db",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()

    assert actual["error_code"] == 422
    assert actual["message"] == [
        {'loc': ['body', 'collection'], 'msg': 'collection is required', 'type': 'value_error'}]
    assert not actual["success"]


def test_add_vectordb_action_empty_operation_value():
    request_body = {
        "name": 'action_test_empty_operation_value',
        "collection": 'test_add_vectordb_action_empty_operation_value',
        "payload": [{"query_type": "", "type": "from_value", "value": {"ids": [0], "with_payload": True, "with_vector": True}}],
        "response": {"value": "0"}
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/db",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()

    assert actual["error_code"] == 422
    assert actual["message"] == [{'loc': ['body', 'payload', 0, 'query_type'],
                                  'msg': "value is not a valid enumeration member; permitted: 'payload_search', 'embedding_search'",
                                  'type': 'type_error.enum',
                                  'ctx': {'enum_values': ['payload_search', 'embedding_search']}}]
    assert not actual["success"]


def test_add_vectordb_action_empty_payload_type():
    request_body = {
        "name": "test_add_vectordb_action_empty_payload_type",
        "collection": 'test_add_vectordb_action_empty_payload_type',
        "payload": [{
            "query_type": "payload_search",
            "type": "",
            "value": {"ids": [0], "with_payload": True, "with_vector": True},
        }],
        "response": {"value": "0"},
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/db",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()

    assert actual["error_code"] == 422
    assert actual["message"] == [{'loc': ['body', 'payload', 0, 'type'],
                                  'msg': "value is not a valid enumeration member; permitted: 'from_value', 'from_slot', 'from_user_message'",
                                  'type': 'type_error.enum',
                                  'ctx': {'enum_values': ['from_value', 'from_slot', 'from_user_message']}},
                                 {'loc': ['body', 'payload', 0, '__root__'], 'msg': 'type is required',
                                  'type': 'value_error'}]
    assert not actual["success"]


def test_add_vectordb_action_without_enable_faq():
    request_body = {
        "name": "vectordb_action_test",
        "collection": 'test_add_vectordb_action_collection_does_not_exists',
        "payload": [{"query_type": "payload_search","type": "from_value", "value": {
            "filter": {
                "should": [
                    {"key": "city", "match": {"value": "London"}},
                    {"key": "color", "match": {"value": "red"}}
                ]
            }
        }}],
        "response": {"value": "0"}
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/db",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == 'Collection does not exist!'
    assert not actual["success"]


def test_add_vectordb_action_collection_does_not_exists(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(bot=pytest.bot, user="integration@demo.ai", llm_settings=LLMSettings(enable_faq=True))

    monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)
    request_body = {
        "name": "vectordb_action_test",
        "collection": 'test_add_vectordb_action_collection_does_not_exists',
        "payload": [{"query_type": "payload_search","type": "from_value", "value": {
            "filter": {
                "should": [
                    {"key": "city", "match": {"value": "London"}},
                    {"key": "color", "match": {"value": "red"}}
                ]
            }
        }}],
        "response": {"value": "0"}
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/db",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()

    assert actual["error_code"] == 422
    assert actual["message"] == 'Collection does not exist!'
    assert not actual["success"]


def test_add_vectordb_action(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(bot=pytest.bot, user="integration@demo.ai", llm_settings=LLMSettings(enable_faq=True))

    monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json={
            "metadata": [{"column_name": "city", "data_type": "str", "enable_search": True, "create_embeddings": True},
                         {"column_name": "color", "data_type": "str", "enable_search": True,
                          "create_embeddings": True}],
            "collection_name": "test_add_vectordb_action"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    pytest.delete_schema_id_db_action = actual["data"]["_id"]
    payload = {
        "data": {"city": "London", "color": "red"},
        "collection": "test_add_vectordb_action",
        "content_type": "json"}
    payload_response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    request_body = {
        "name": 'vectordb_action_test',
        "collection": 'test_add_vectordb_action',
        "payload": [{
            "query_type": "payload_search",
            "type": "from_value",
            "value": {
                "filter": {
                    "should": [
                        {"key": "city", "match": {"value": "London"}},
                        {"key": "color", "match": {"value": "red"}},
                    ]
                }
            },
        }],
        "response": {"value": "0"},
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/db",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()

    assert actual["error_code"] == 0
    assert actual["message"] == "Action added!"
    assert actual["success"]

    response_two = client.delete(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema/{pytest.delete_schema_id_db_action}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual_two = response_two.json()

    assert not actual_two["success"]
    assert actual_two[
               "message"] == 'Cannot remove collection test_add_vectordb_action linked to action "vectordb_action_test"!'
    assert actual_two["data"] is None
    assert actual_two["error_code"] == 422


def test_add_vectordb_action_case_insensitivity(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(bot=pytest.bot, user="integration@demo.ai", llm_settings=LLMSettings(enable_faq=True))

    monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)
    request_body = {
        "name": "VECTORDB_ACTION_CASE_INSENSITIVE",
        "collection": 'test_add_vectordb_action',
        "payload": [{
            "query_type": "payload_search",
            "type": "from_value",
            "value": {
                "filter": {
                    "should": [
                        {"key": "city", "match": {"value": "London"}},
                        {"key": "color", "match": {"value": "red"}},
                    ]
                }
            },
        }],
        "response": {"value": "0"},
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/db",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"] == "Action added!"
    assert actual["success"]

    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/db/VECTORDB_ACTION_CASE_INSENSITIVE",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert not actual["data"]

    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/db/vectordb_action_case_insensitive",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["error_code"] == 0
    assert actual["data"]
    assert actual["success"]


def test_add_vectordb_action_existing(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(bot=pytest.bot, user="integration@demo.ai", llm_settings=LLMSettings(enable_faq=True))

    monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)
    request_body = {
        "name": 'test_add_vectordb_action_existing',
        "collection": 'test_add_vectordb_action',
        "payload": [{
            "query_type": "embedding_search",
            "type": "from_value",
            "value": {"ids": [0], "with_payload": True, "with_vector": True},
        }],
        "response": {"value": "0"},
        "set_slots": [
            {"name": "bot", "value": "${RESPONSE}", "evaluation_type": "expression"}
        ],
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/db",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/db",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()

    assert actual["error_code"] == 422
    assert actual["message"] == "Action exists!"
    assert not actual["success"]


def test_add_vectordb_action_with_slots(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(bot=pytest.bot, user="integration@demo.ai", llm_settings=LLMSettings(enable_faq=True))

    monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)
    response = client.post(
        f"/api/bot/{pytest.bot}/slots",
        json={
            "name": "vectordb",
            "type": "text",
            "initial_value": "bot",
            "influence_conversation": False,
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert "data" in actual
    assert actual["message"] == "Slot added successfully!"
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0

    request_body = {
        "name": "test_add_vectordb_action_with_slots",
        "collection": 'test_add_vectordb_action',

        "payload": [{"query_type": "payload_search", "type": "from_slot", "value": "vectordb"}],
        "response": {"value": "0"},
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/db",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()

    assert actual["error_code"] == 0
    assert actual["message"]
    assert actual["success"]


def test_add_vectordb_action_payload_and_embedding_search(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(bot=pytest.bot, user="integration@demo.ai", llm_settings=LLMSettings(enable_faq=True))

    monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)
    payload = [{
            "query_type": "payload_search",
            "type": "from_value",
            "value": {
                "filter": {
                    "should": [
                        {"key": "city", "match": {"value": "London"}},
                        {"key": "color", "match": {"value": "red"}},
                    ]
                }
            },
        },
        {
            "query_type": "embedding_search",
            "type": "from_value",
            "value": "Hi"
        },
        {
            "query_type": "embedding_search",
            "type": "from_value",
            "value": "How are you"
        }]
    request_body = {
        "name": "vectordb_action_payload_and_embedding_search",
        "collection": 'test_add_vectordb_action',
        "payload": payload,
        "response": {"value": "0"},
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/db",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"] == "Action added!"
    assert actual["success"]

    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/db/vectordb_action_payload_and_embedding_search",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["error_code"] == 0
    assert actual["data"]['name'] == 'vectordb_action_payload_and_embedding_search'
    assert not DeepDiff(actual["data"]['payload'], payload, ignore_order=True)
    assert actual["success"]


def test_add_vectordb_action_payload_search_mutiple_error(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(bot=pytest.bot, user="integration@demo.ai", llm_settings=LLMSettings(enable_faq=True))

    monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)
    payload = [{
            "query_type": "payload_search",
            "type": "from_value",
            "value": {
                "filter": {
                    "should": [
                        {"key": "city", "match": {"value": "London"}},
                        {"key": "color", "match": {"value": "red"}},
                    ]
                }
            },
        },{
            "query_type": "payload_search",
            "type": "from_value",
            "value": {
                "filter": {
                    "should": [
                        {"key": "city", "match": {"value": "Canada"}},
                        {"key": "color", "match": {"value": "blue"}},
                    ]
                }
            },
        },
        {
            "query_type": "embedding_search",
            "type": "from_value",
            "value": "Hi"
        },
        {
            "query_type": "embedding_search",
            "type": "from_value",
            "value": "How are you"
        }]
    request_body = {
        "name": "vectordb_action_payload_and_embedding_search",
        "collection": 'test_add_vectordb_action',
        "payload": payload,
        "response": {"value": "0"},
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/db",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == [{'loc': ['body', 'payload'], 'msg': 'Only One payload_search is allowed!', 'type': 'value_error'}]
    assert not actual["success"]


def test_update_vectordb_action(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(bot=pytest.bot, user="integration@demo.ai", llm_settings=LLMSettings(enable_faq=True))

    monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)
    request_body = {
        "name": "test_update_vectordb_action",
        "collection": 'test_add_vectordb_action',
        "payload": [{
            "query_type": "payload_search",
            "type": "from_value",
            "value": {
                "filter": {
                    "should": [
                        {"key": "city", "match": {"value": "London"}},
                        {"key": "color", "match": {"value": "red"}},
                    ]
                }
            },
        }],
        "response": {"value": "0"},
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/db",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0

    request_body = {
        "name": "test_update_vectordb_action",
        "collection": 'test_add_vectordb_action',
        "payload": [{
            "query_type": "embedding_search",
            "type": "from_value",
            "value": {"ids": [0], "with_payload": True, "with_vector": True},
        }],
        "response": {"value": "0"},
        "set_slots": [
            {"name": "bot", "value": "${RESPONSE}", "evaluation_type": "script"}
        ],
    }
    response = client.put(
        url=f"/api/bot/{pytest.bot}/action/db",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["error_code"] == 0
    assert actual["message"] == "Action updated!"

    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/db/test_update_vectordb_action",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["success"]


def test_update_vectordb_action_non_existing(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(bot=pytest.bot, user="integration@demo.ai", llm_settings=LLMSettings(enable_faq=True))

    monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)
    request_body = {
        "name": "test_update_vectordb_action_non_existing",
        "collection": 'test_add_vectordb_action',
        "payload": [{
            "query_type": "embedding_search",
            "type": "from_value",
            "value": {"ids": [6], "with_payload": True, "with_vector": True},
        }],
        "response": {"value": "15"},
        "set_slots": [
            {"name": "age", "value": "${RESPONSE}", "evaluation_type": "script"}
        ],
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/db",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    request_body = {
        "name": "test_update_vectordb_action_non_existing_new",
        "collection": 'test_add_vectordb_action',
        "payload": [{
            "query_type": "embedding_search",
            "type": "from_value",
            "value": {"ids": [6], "with_payload": True, "with_vector": True},
        }],
        "response": {"value": "15"},
        "set_slots": [
            {"name": "age", "value": "${RESPONSE}", "evaluation_type": "script"}
        ],
    }
    response = client.put(
        url=f"/api/bot/{pytest.bot}/action/db",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["error_code"] == 422
    assert actual["message"]
    assert not actual["success"]


def test_update_vector_action_wrong_parameter(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(bot=pytest.bot, user="integration@demo.ai", llm_settings=LLMSettings(enable_faq=True))

    monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)
    request_body = {
        "name": "test_update_vector_action_1",
        "collection": 'test_add_vectordb_action',
        "payload": [{
            "query_type": "embedding_search",
            "type": "from_value",
            "value": {"ids": [8], "with_payload": True, "with_vector": True},
        }],
        "response": {"value": "15"},
        "set_slots": [
            {"name": "bot", "value": "${RESPONSE}", "evaluation_type": "expression"}
        ],
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/db",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0

    request_body = {
        "name": "test_update_vector_action_1",
        "collection": 'test_add_vectordb_action',
        "payload": [{
            "query_type": "embedding_search",
            "type": "from_val",
            "value": {"ids": [81], "with_payload": True, "with_vector": True},
        }],
        "response": {"value": "nupur"},
        "set_slots": [
            {"name": "bot", "value": "${RESPONSE}", "evaluation_type": "expression"}
        ],
    }
    response = client.put(
        url=f"/api/bot/{pytest.bot}/action/db",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["error_code"] == 422
    assert actual["message"]
    assert not actual["success"]


def test_get_vectordb_action():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/db/test_add_vectordb_action_with_slots",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["success"]


def test_get_vector_action_non_exisitng():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/db/never_added_vectordb_action",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] is not None
    assert not actual["success"]


def test_list_vector_db_action():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/db",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["error_code"] == 0
    assert actual["success"]
    assert actual['data'][0]['name'] == 'vectordb_action_test'


def test_delete_vectordb_action(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(bot=pytest.bot, user="integration@demo.ai", llm_settings=LLMSettings(enable_faq=True))

    monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)
    request_body = {
        "name": "test_delete_vectordb_action",
        "collection": 'test_add_vectordb_action',
        "payload": [{
            "query_type": "payload_search",
            "type": "from_value",
            "value": {
                "filter": {
                    "should": [
                        {"key": "city", "match": {"value": "London"}},
                        {"key": "color", "match": {"value": "red"}},
                    ]
                }
            },
        }],
        "response": {"value": "30"},
        "set_slots": [],
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/db",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    response = client.delete(
        url=f"/api/bot/{pytest.bot}/action/test_delete_vectordb_action",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"]
    assert actual["success"]


def test_delete_vectordb_action_non_existing(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(bot=pytest.bot, user="integration@demo.ai", llm_settings=LLMSettings(enable_faq=True))

    monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)
    request_body = {
        "name": "test_delete_vectordb_action_non_existing",
        "collection": 'test_add_vectordb_action',
        "payload": [{
            "query_type": "payload_search",
            "type": "from_value",
            "value": {
                "filter": {
                    "should": [
                        {"key": "city", "match": {"value": "India"}},
                        {"key": "color", "match": {"value": "red"}},
                    ]
                }
            },
        }],
        "response": {"value": "1"},
    }

    client.post(
        url=f"/api/bot/{pytest.bot}/action/db",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    response = client.delete(
        url=f"/api/bot/{pytest.bot}/action/new_vectordb_action_never_added",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["error_code"] == 422
    assert actual["message"]
    assert not actual["success"]


def test_add_http_action_malformed_url():
    request_body = {
        "auth_token": "",
        "action_name": "new_http_action",
        "response": {"value": "", "dispatch": False, "evaluation_type": "script"},
        "http_url": "192.168.104.1/api/test",
        "request_method": "GET",
        "http_params_list": [
            {"key": "testParam1", "parameter_type": "value", "value": "testValue1"}
        ],
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"]
    assert not actual["success"]


def test_add_http_action_missing_parameters():
    request_body = {
        "action_name": "new_http_action2",
        "response": {"value": "", "dispatch": False, "evaluation_type": "script"},
        "http_url": "http://www.google.com",
        "request_method": "put",
        "params_list": [{"key": "", "parameter_type": "", "value": ""}],
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"]
    assert not actual["success"]


def test_add_http_action_invalid_req_method():
    request_body = {
        "auth_token": "",
        "action_name": "new_http_action",
        "response": {"value": "", "dispatch": False},
        "http_url": "http://www.google.com",
        "request_method": "TUP",
        "http_params_list": [
            {"key": "testParam1", "parameter_type": "value", "value": "testValue1"}
        ],
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"]
    assert not actual["success"]


def test_add_http_action_no_action_name():
    request_body = {
        "auth_token": "",
        "action_name": "",
        "response": {"value": "string"},
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "http_params_list": [
            {"key": "testParam1", "parameter_type": "value", "value": "testValue1"}
        ],
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"]
    assert not actual["success"]


def test_add_http_action_with_utter():
    request_body = {
        "action_name": "utter_test_add_http_action_no_token",
        "response": {"value": "string"},
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "http_params_list": [
            {"key": "testParam1", "parameter_type": "value", "value": "testValue1"}
        ],
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == "Action name cannot start with utter_"
    assert not actual["success"]


def test_add_http_action_no_token():
    request_body = {
        "auth_token": "",
        "action_name": "test_add_http_action_no_token",
        "response": {"value": "string"},
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "http_params_list": [
            {"key": "testParam1", "parameter_type": "value", "value": "testValue1"}
        ],
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"]
    assert actual["success"]


def test_add_http_action_with_valid_dispatch_type():
    request_body = {
        "action_name": "test_add_http_action_with_valid_dispatch_type",
        "response": {"value": "string", "dispatch_type": "json"},
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "dynamic_params": '{"sender_id": "${sender_id}", "user_message": "${user_message}", "intent": "${intent}"}',
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"]
    assert actual["success"]

    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/httpaction/test_add_http_action_with_valid_dispatch_type",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["success"]
    assert actual["data"]["response"] == {
        "value": "string",
        "dispatch": True,
        "evaluation_type": "expression",
        "dispatch_type": "json",
    }
    assert actual["data"]["http_url"] == "http://www.google.com"
    assert actual["data"]["request_method"] == "GET"
    assert len(actual["data"]["params_list"]) == 0
    assert (
            actual["data"]["dynamic_params"]
            == '{"sender_id": "${sender_id}", "user_message": "${user_message}", "intent": "${intent}"}'
    )


def test_add_http_action_with_invalid_dispatch_type():
    request_body = {
        "action_name": "test_add_http_action_with_invalid_dispatch_type",
        "response": {"value": "string", "dispatch_type": "invalid_dispatch_type"},
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "dynamic_params": '{"sender_id": "${sender_id}", "user_message": "${user_message}", "intent": "${intent}"}',
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert not actual["success"]
    assert str(actual["message"]).__contains__(
        "value is not a valid enumeration member"
    )
    assert actual["data"] is None
    assert actual["error_code"] == 422


def test_add_http_action_with_dynamic_params():
    request_body = {
        "action_name": "test_add_http_action_with_dynamic_params",
        "response": {"value": "string"},
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "dynamic_params": '{"sender_id": "${sender_id}", "user_message": "${user_message}", "intent": "${intent}"}',
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"]
    assert actual["success"]


def test_update_http_action_with_dynamic_params():
    request_body = {
        "action_name": "test_update_http_action_with_dynamic_params",
        "response": {"value": "", "dispatch": False},
        "http_url": "http://www.google.com",
        "request_method": "GET",
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0

    request_body = {
        "action_name": "test_update_http_action_with_dynamic_params",
        "content_type": "application/x-www-form-urlencoded",
        "response": {
            "value": "json",
            "dispatch": False,
            "evaluation_type": "script",
            "dispatch_type": "json",
        },
        "http_url": "http://www.alphabet.com",
        "request_method": "POST",
        "dynamic_params": '{"sender_id": "${sender_id}", "user_message": "${user_message}", "intent": "${intent}"}',
        "headers": [
            {
                "key": "Authorization",
                "parameter_type": "value",
                "value": "bearer token",
                "encrypt": True,
            }
        ],
        "set_slots": [
            {"name": "bot", "value": "${RESPONSE}", "evaluation_type": "script"}
        ],
    }
    response = client.put(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0

    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/httpaction/test_update_http_action_with_dynamic_params",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["response"] == {
        "value": "json",
        "dispatch": False,
        "evaluation_type": "script",
        "dispatch_type": "json",
    }
    assert actual["data"]["http_url"] == "http://www.alphabet.com"
    assert actual["data"]["request_method"] == "POST"
    assert len(actual["data"]["params_list"]) == 0
    assert (
            actual["data"]["dynamic_params"]
            == '{"sender_id": "${sender_id}", "user_message": "${user_message}", "intent": "${intent}"}'
    )
    assert actual["data"]["headers"] == [
        {
            "key": "Authorization",
            "value": "bearer token",
            "parameter_type": "value",
            "encrypt": True,
        }
    ]
    assert actual["success"]


def test_add_http_action_with_sender_id_parameter_type():
    request_body = {
        "auth_token": "",
        "action_name": "test_add_http_action_with_sender_id_parameter_type",
        "response": {"value": "string"},
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "params_list": [
            {
                "key": "testParam1",
                "parameter_type": "sender_id",
                "value": "testValue1",
                "encrypt": True,
            },
            {
                "key": "testParam2",
                "parameter_type": "slot",
                "value": "testValue2",
                "encrypt": True,
            },
            {
                "key": "testParam3",
                "encrypt": True,
                "parameter_type": "user_message",
            },
            {"key": "testParam4", "parameter_type": "chat_log", "encrypt": True},
            {"key": "testParam5", "parameter_type": "intent", "encrypt": True},
            {
                "key": "testParam6",
                "parameter_type": "value",
                "encrypt": True,
                "value": "12345",
            },
            {
                "key": "testParam7",
                "parameter_type": "key_vault",
                "encrypt": False,
                "value": "ACCESS_KEY",
            },
        ],
        "headers": [
            {"key": "testParam1", "parameter_type": "sender_id", "value": "testValue1"},
            {"key": "testParam2", "parameter_type": "slot", "value": "testValue2"},
            {
                "key": "testParam3",
                "parameter_type": "user_message",
            },
            {
                "key": "testParam4",
                "parameter_type": "chat_log",
            },
            {
                "key": "testParam5",
                "parameter_type": "intent",
            },
            {"key": "testParam6", "parameter_type": "value", "value": "12345"},
            {
                "key": "testParam7",
                "parameter_type": "key_vault",
                "encrypt": False,
                "value": "SECRET_KEY",
            },
        ],
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"]
    assert actual["success"]


def test_get_http_action():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/httpaction/test_add_http_action_with_sender_id_parameter_type",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert (
            actual["data"]["action_name"]
            == "test_add_http_action_with_sender_id_parameter_type"
    )
    assert actual["data"]["response"] == {
        "value": "string",
        "dispatch": True,
        "evaluation_type": "expression",
        "dispatch_type": "text",
    }
    assert actual["data"]["http_url"] == "http://www.google.com"
    assert actual["data"]["request_method"] == "GET"
    assert actual["data"]["params_list"] == [
        {
            "key": "testParam1",
            "value": "testValue1",
            "parameter_type": "sender_id",
            "encrypt": True,
        },
        {
            "key": "testParam2",
            "value": "testvalue2",
            "parameter_type": "slot",
            "encrypt": True,
        },
        {
            "key": "testParam3",
            "value": "",
            "parameter_type": "user_message",
            "encrypt": True,
        },
        {
            "key": "testParam4",
            "value": "",
            "parameter_type": "chat_log",
            "encrypt": True,
        },
        {"key": "testParam5", "value": "", "parameter_type": "intent", "encrypt": True},
        {
            "key": "testParam6",
            "value": "12345",
            "parameter_type": "value",
            "encrypt": True,
        },
        {
            "key": "testParam7",
            "value": "ACCESS_KEY",
            "parameter_type": "key_vault",
            "encrypt": True,
        },
    ]
    assert actual["data"]["headers"] == [
        {
            "key": "testParam1",
            "value": "testValue1",
            "parameter_type": "sender_id",
            "encrypt": False,
        },
        {
            "key": "testParam2",
            "value": "testvalue2",
            "parameter_type": "slot",
            "encrypt": False,
        },
        {
            "key": "testParam3",
            "value": "",
            "parameter_type": "user_message",
            "encrypt": False,
        },
        {
            "key": "testParam4",
            "value": "",
            "parameter_type": "chat_log",
            "encrypt": False,
        },
        {
            "key": "testParam5",
            "value": "",
            "parameter_type": "intent",
            "encrypt": False,
        },
        {
            "key": "testParam6",
            "value": "12345",
            "parameter_type": "value",
            "encrypt": False,
        },
        {
            "key": "testParam7",
            "value": "SECRET_KEY",
            "parameter_type": "key_vault",
            "encrypt": True,
        },
    ]
    assert not actual["message"]
    assert actual["success"]


def test_add_http_action_invalid_parameter_type():
    request_body = {
        "auth_token": "",
        "action_name": "test_add_http_action_invalid_parameter_type",
        "response": {"value": "string"},
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "params_list": [
            {"key": "testParam1", "parameter_type": "val", "value": "testValue1"}
        ],
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"]
    assert not actual["success"]


def test_add_http_action_with_token():
    request_body = {
        "action_name": "test_add_http_action_with_token_and_story",
        "response": {"value": "string", "evaluation_type": "script"},
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "headers": [
            {
                "key": "Authorization",
                "parameter_type": "value",
                "value": "bearer dfiuhdfishifoshfoishnfoshfnsif***",
                "encrypt": True,
            },
            {
                "key": "testParam1",
                "parameter_type": "value",
                "value": "testVal***",
                "encrypt": True,
            },
            {
                "key": "testParam1",
                "parameter_type": "value",
                "value": "testVal***",
                "encrypt": True,
            },
        ],
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"]
    assert actual["success"]

    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/httpaction/test_add_http_action_with_token_and_story",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["response"] == {
        "dispatch": True,
        "evaluation_type": "script",
        "value": "string",
        "dispatch_type": "text",
    }
    assert actual["data"]["headers"] == [
        {
            "key": "Authorization",
            "parameter_type": "value",
            "value": "bearer dfiuhdfishifoshfoishnfoshfnsif***",
            "encrypt": True,
        },
        {
            "key": "testParam1",
            "parameter_type": "value",
            "value": "testVal***",
            "encrypt": True,
        },
        {
            "key": "testParam1",
            "parameter_type": "value",
            "value": "testVal***",
            "encrypt": True,
        },
    ]
    assert actual["data"]["http_url"] == "http://www.google.com"
    assert actual["data"]["request_method"] == "GET"
    assert len(actual["data"]["headers"]) == 3
    assert actual["success"]


def test_add_http_action_no_params():
    request_body = {
        "auth_token": "",
        "action_name": "test_add_http_action_no_params",
        "response": {"value": "string", "dispatch": False},
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "params_list": [],
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"]
    assert actual["success"]


def test_add_http_action_existing():
    request_body = {
        "auth_token": "",
        "action_name": "test_add_http_action_existing",
        "response": {"value": "string", "dispatch": False, "evaluation_type": "script"},
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "params_list": [
            {"key": "testParam1", "parameter_type": "value", "value": "testValue1"}
        ],
        "set_slots": [
            {"name": "bot", "value": "${RESPONSE}", "evaluation_type": "script"}
        ],
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"]
    assert not actual["success"]


def test_get_http_action_non_exisitng():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/httpaction/never_added",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] is not None
    assert not actual["success"]


def test_update_http_action():
    request_body = {
        "action_name": "test_update_http_action",
        "response": {"value": "", "dispatch": False},
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "params_list": [
            {"key": "testParam1", "parameter_type": "value", "value": "testValue1"}
        ],
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0

    request_body = {
        "action_name": "test_update_http_action",
        "content_type": "application/x-www-form-urlencoded",
        "response": {
            "value": "json",
            "dispatch": False,
            "evaluation_type": "script",
            "dispatch_type": "json",
        },
        "http_url": "http://www.alphabet.com",
        "request_method": "POST",
        "params_list": [
            {
                "key": "testParam1",
                "parameter_type": "value",
                "value": "testValue1",
                "encrypt": True,
            },
            {
                "key": "testParam2",
                "parameter_type": "slot",
                "value": "testValue1",
                "encrypt": True,
            },
        ],
        "headers": [
            {
                "key": "Authorization",
                "parameter_type": "value",
                "value": "bearer token",
                "encrypt": True,
            }
        ],
        "set_slots": [
            {"name": "bot", "value": "${RESPONSE}", "evaluation_type": "script"}
        ],
    }
    response = client.put(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0

    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/httpaction/test_update_http_action",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]["response"] == {
        "value": "json",
        "dispatch": False,
        "evaluation_type": "script",
        "dispatch_type": "json",
    }
    assert actual["data"]["http_url"] == "http://www.alphabet.com"
    assert actual["data"]["request_method"] == "POST"
    assert len(actual["data"]["params_list"]) == 2
    assert actual["data"]["params_list"] == [
        {
            "key": "testParam1",
            "value": "testValue1",
            "parameter_type": "value",
            "encrypt": True,
        },
        {
            "key": "testParam2",
            "value": "testvalue1",
            "parameter_type": "slot",
            "encrypt": True,
        },
    ]
    assert actual["data"]["headers"] == [
        {
            "key": "Authorization",
            "value": "bearer token",
            "parameter_type": "value",
            "encrypt": True,
        }
    ]
    assert actual["success"]


def test_update_http_action_wrong_parameter():
    request_body = {
        "auth_token": "",
        "action_name": "test_update_http_action_6",
        "response": {"value": "", "dispatch": False},
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "params_list": [
            {"key": "testParam1", "parameter_type": "value", "value": "testValue1"}
        ],
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0

    request_body = {
        "auth_token": "bearer hjklfsdjsjkfbjsbfjsvhfjksvfjksvfjksvf",
        "action_name": "test_update_http_action_6",
        "response": {"value": "json"},
        "http_url": "http://www.alphabet.com",
        "request_method": "POST",
        "params_list": [
            {"key": "testParam1", "parameter_type": "val", "value": "testValue1"},
            {"key": "testParam2", "parameter_type": "slot", "value": "testValue1"},
        ],
    }
    response = client.put(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"]
    assert not actual["success"]

    request_body = {
        "auth_token": "bearer hjklfsdjsjkfbjsbfjsvhfjksvfjksvfjksvf",
        "action_name": "test_update_http_action_6",
        "response": {"value": "json"},
        "http_url": "http://www.alphabet.com",
        "request_method": "POST",
        "params_list": [
            {"key": "testParam1", "parameter_type": "val", "value": "testValue1"},
            {"key": "testParam2", "parameter_type": "slot", "value": "testValue1"},
        ],
        "set_slots": [
            {"name": " ", "value": "${RESPONSE}", "evaluation_type": "script"}
        ],
    }
    response = client.put(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == [{'loc': ['body', 'params_list', 0, 'parameter_type'],
                                  'msg': "value is not a valid enumeration member; permitted: 'value', 'slot', 'sender_id', 'user_message', 'latest_message', 'intent', 'chat_log', 'key_vault'",
                                  'type': 'type_error.enum', 'ctx': {
            'enum_values': ['value', 'slot', 'sender_id', 'user_message', 'latest_message', 'intent', 'chat_log',
                            'key_vault']}}, {'loc': ['body', 'set_slots', 0, 'name'], 'msg': 'slot name is required',
                                             'type': 'value_error'}]

    assert not actual["success"]

    request_body = {
        "auth_token": "bearer hjklfsdjsjkfbjsbfjsvhfjksvfjksvfjksvf",
        "action_name": "test_update_http_action_6",
        "response": {"value": "json"},
        "http_url": "http://www.alphabet.com",
        "request_method": "POST",
        "params_list": [
            {"key": "testParam1", "parameter_type": "val", "value": "testValue1"},
            {"key": "testParam2", "parameter_type": "slot", "value": "testValue1"},
        ],
        "set_slots": [{"name": "bot", "value": " ", "evaluation_type": "script"}],
    }
    response = client.put(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == [{'loc': ['body', 'params_list', 0, 'parameter_type'],
                                  'msg': "value is not a valid enumeration member; permitted: 'value', 'slot', 'sender_id', 'user_message', 'latest_message', 'intent', 'chat_log', 'key_vault'",
                                  'type': 'type_error.enum', 'ctx': {
            'enum_values': ['value', 'slot', 'sender_id', 'user_message', 'latest_message', 'intent', 'chat_log',
                            'key_vault']}}, {'loc': ['body', 'set_slots', 0, 'value'],
                                             'msg': 'expression is required to evaluate value of slot',
                                             'type': 'value_error'}]

    assert not actual["success"]

    request_body = {
        "auth_token": "bearer hjklfsdjsjkfbjsbfjsvhfjksvfjksvfjksvf",
        "action_name": "test_update_http_action_6",
        "response": {"value": " ", "dispatch": True},
        "http_url": "http://www.alphabet.com",
        "request_method": "POST",
        "params_list": [
            {"key": "testParam1", "parameter_type": "val", "value": "testValue1"},
            {"key": "testParam2", "parameter_type": "slot", "value": "testValue1"},
        ],
        "set_slots": [{"name": "bot", "value": " ", "evaluation_type": "script"}],
    }
    response = client.put(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {'loc': ['body', 'response', '__root__'], 'msg': 'response is required for dispatch', 'type': 'value_error'},
        {'loc': ['body', 'params_list', 0, 'parameter_type'],
         'msg': "value is not a valid enumeration member; permitted: 'value', 'slot', 'sender_id', 'user_message', 'latest_message', 'intent', 'chat_log', 'key_vault'",
         'type': 'type_error.enum', 'ctx': {
            'enum_values': ['value', 'slot', 'sender_id', 'user_message', 'latest_message', 'intent', 'chat_log',
                            'key_vault']}},
        {'loc': ['body', 'set_slots', 0, 'value'], 'msg': 'expression is required to evaluate value of slot',
         'type': 'value_error'}]

    assert not actual["success"]


def test_update_http_action_non_existing():
    request_body = {
        "auth_token": "",
        "action_name": "test_update_http_action_non_existing",
        "response": {"value": "", "dispatch": False},
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "params_list": [],
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    request_body = {
        "auth_token": "bearer hjklfsdjsjkfbjsbfjsvhfjksvfjksvfjksvf",
        "action_name": "test_update_http_action_non_existing_new",
        "response": "json",
        "http_url": "http://www.alphabet.com",
        "request_method": "POST",
        "params_list": [
            {"key": "param1", "value": "value1", "parameter_type": "value"},
            {"key": "param2", "value": "value2", "parameter_type": "slot"},
        ],
    }
    response = client.put(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"]
    assert not actual["success"]


def test_delete_http_action():
    request_body = {
        "auth_token": "",
        "action_name": "test_delete_http_action",
        "response": {"value": "", "dispatch": False},
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "params_list": [],
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    response = client.delete(
        url=f"/api/bot/{pytest.bot}/action/test_delete_http_action",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"]
    assert actual["success"]


def test_delete_http_action_non_existing():
    request_body = {
        "auth_token": "",
        "action_name": "new_http_action4",
        "response": {"value": "", "dispatch": False},
        "http_url": "http://www.google.com",
        "request_method": "GET",
        "params_list": [],
    }

    client.post(
        url=f"/api/bot/{pytest.bot}/action/httpaction",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    response = client.delete(
        url=f"/api/bot/{pytest.bot}/action/new_http_action_never_added",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"]
    assert not actual["success"]


def test_list_actions():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_path_action",
            "type": "STORY",
            "template_type": "Q&A",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "action_greet", "type": "ACTION"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"] == "Flow added successfully"
    assert actual["data"]["_id"]
    assert actual["success"]

    response = client.get(
        url=f"/api/bot/{pytest.bot}/actions",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])
    assert not DeepDiff(actual['data'], {'actions': ['action_greet'],
                              'database_action': ['vectordb_action_test', 'vectordb_action_case_insensitive',
                                                  'test_add_vectordb_action_existing',
                                                  'test_add_vectordb_action_with_slots',
                                                  'test_update_vectordb_action',
                                                  'test_update_vectordb_action_non_existing',
                                                  'test_update_vector_action_1',
                                                  'test_delete_vectordb_action_non_existing',
                                                  'vectordb_action_payload_and_embedding_search'],
                              'http_action': ['test_add_http_action_no_token',
                                              'test_add_http_action_with_valid_dispatch_type',
                                              'test_add_http_action_with_dynamic_params',
                                              'test_update_http_action_with_dynamic_params',
                                              'test_add_http_action_with_sender_id_parameter_type',
                                              'test_add_http_action_with_token_and_story',
                                              'test_add_http_action_no_params',
                                              'test_add_http_action_existing', 'test_update_http_action',
                                              'test_update_http_action_6', 'test_update_http_action_non_existing',
                                              'new_http_action4'],
                              'utterances': ['utter_greet', 'utter_cheer_up', 'utter_did_that_help', 'utter_happy',
                                             'utter_goodbye', 'utter_iamabot', 'utter_default',
                                             'utter_please_rephrase'],
                              'slot_set_action': [], 'form_validation_action': [], 'email_action': [],
                              'google_search_action': [],
                              'jira_action': [], 'zendesk_action': [], 'pipedrive_leads_action': [],
                              'hubspot_forms_action': [],
                              'two_stage_fallback': [], 'kairon_bot_response': [], 'razorpay_action': [],
                              'prompt_action': [], 'callback_action': [], 'schedule_action': [],
                              'pyscript_action': [], 'web_search_action': [], 'live_agent_action': [],
                                         'parallel_action':[], 'voice_call_action':[], 'kairon_voice_disconnect': [],
                              'store_page_action': [], 'agent_action': []}, ignore_order=True)

    assert actual["success"]


@responses.activate
def test_train_using_event():
    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.model_training}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/train",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "Model training started."
    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.model_training
    )


def test_list_action_server_logs_empty():
    response = client.get(
        f"/api/bot/{pytest.bot}/actions/logs?start_idx=0&page_size=10",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["data"]["logs"] == []
    assert actual["data"]["total"] == 0


def test_list_action_server_logs():
    bot = pytest.bot
    bot_2 = "integration2"
    request_params = {"key": "value", "key2": "value2"}
    expected_intents = [
        "intent13",
        "intent11",
        "intent9",
        "intent8",
        "intent7",
        "intent6",
        "intent5",
        "intent4",
        "intent3",
        "intent2",
    ]
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
        intent="intent1",
        action="http_action",
        sender="sender_id",
        request_params=request_params,
        api_response="Response",
        bot_response="Bot Response",
        bot=bot_2,
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
    ActionServerLogs(
        intent="intent6",
        action="http_action",
        sender="sender_id",
        request_params=request_params,
        api_response="Response",
        bot_response="Bot Response",
        bot=bot,
    ).save()
    ActionServerLogs(
        intent="intent7",
        action="http_action",
        sender="sender_id",
        request_params=request_params,
        api_response="Response",
        bot_response="Bot Response",
        bot=bot,
    ).save()
    ActionServerLogs(
        intent="intent8",
        action="http_action",
        sender="sender_id",
        request_params=request_params,
        api_response="Response",
        bot_response="Bot Response",
        bot=bot,
    ).save()
    ActionServerLogs(
        intent="intent9",
        action="http_action",
        sender="sender_id",
        request_params=request_params,
        api_response="Response",
        bot_response="Bot Response",
        bot=bot,
    ).save()
    ActionServerLogs(
        intent="intent10",
        action="http_action",
        sender="sender_id",
        request_params=request_params,
        api_response="Response",
        bot_response="Bot Response",
        bot=bot_2,
    ).save()
    ActionServerLogs(
        intent="intent11",
        action="http_action",
        sender="sender_id",
        request_params=request_params,
        api_response="Response",
        bot_response="Bot Response",
        bot=bot,
    ).save()
    ActionServerLogs(
        intent="intent12",
        action="http_action",
        sender="sender_id",
        request_params=request_params,
        api_response="Response",
        bot_response="Bot Response",
        bot=bot_2,
        status=STATUSES.FAIL.value,
    ).save()
    ActionServerLogs(
        intent="intent13",
        action="http_action",
        sender="sender_id_13",
        request_params=request_params,
        api_response="Response",
        bot_response="Bot Response",
        bot=bot,
        status=STATUSES.FAIL.value,
    ).save()
    response = client.get(
        f"/api/bot/{pytest.bot}/actions/logs",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    response = client.get(
        f"/api/bot/{pytest.bot}/logs/actions",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )


    actual = response.json()
    print(actual)
    assert actual["error_code"] == 0
    assert actual["success"]
    assert len(actual["data"]["logs"]) == 10
    assert actual["data"]["total"] == 10
    assert [log["intent"] in expected_intents for log in actual["data"]["logs"]]
    assert actual["data"]["logs"][0]["action"] == "http_action"
    assert any(
        [log["request_params"] == request_params for log in actual["data"]["logs"]]
    )
    assert any([log["sender"] == "sender_id_13" for log in actual["data"]["logs"]])
    assert any(
        [log["bot_response"] == "Bot Response" for log in actual["data"]["logs"]]
    )
    assert any([log["api_response"] == "Response" for log in actual["data"]["logs"]])
    assert any([log["status"] == STATUSES.FAIL.value for log in actual["data"]["logs"]])
    assert any([log["status"] == STATUSES.SUCCESS.value for log in actual["data"]["logs"]])

    from_date = date.today()
    to_date = from_date + timedelta(days=1)
    search_response = client.get(
        f"/api/bot/{pytest.bot}/logs/actions/search"
        f"?from_date={from_date}&to_date={to_date}&status=Success",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    response_json = search_response.json()
    print("actions:", response_json)

    assert response_json["success"] is True
    assert response_json["error_code"] == 0

    data = response_json["data"]
    assert "logs" in data
    assert isinstance(data["logs"], list)
    assert data['total'] == 6

    search_response = client.get(
        f"/api/bot/{pytest.bot}/logs/actions/search"
        f"?from_date={from_date}&to_date={to_date}&status=Failed",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    response_json = search_response.json()
    print("actions:", response_json)

    assert response_json["success"] is True
    assert response_json["error_code"] == 0

    data = response_json["data"]
    assert "logs" in data
    assert isinstance(data["logs"], list)
    assert data['total'] == 4
    response = client.get(
        f"/api/bot/{pytest.bot}/actions/logs?start_idx=0&page_size=15",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    response = client.get(
        f"/api/bot/{pytest.bot}/logs/actions?start_idx=0&page_size=15",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert len(actual["data"]["logs"]) == 10
    assert actual["data"]["total"] == 10

    response = client.get(
        f"/api/bot/{pytest.bot}/actions/logs?start_idx=10&page_size=1",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["success"]
    assert len(actual["data"]["logs"]) == 1
    assert actual["data"]["total"] == 11
