from tests.integration_test.services_support import *  # noqa: F403
from tests.integration_test.services_support import setup, fast_rasa_training



def test_get_kairon_faq_action_with_no_actions():
    response = client.get(
        f"/api/bot/{pytest.bot}/action/prompt",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert not actual["message"]
    assert actual["data"] == []


def test_add_prompt_action_with_utter(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(
            bot=pytest.bot,
            user="integration@demo.ai",
            llm_settings=LLMSettings(enable_faq=True),
        )

    monkeypatch.setattr(MongoProcessor, "get_bot_settings", _mock_get_bot_settings)
    CognitionSchema(
        metadata=[
            {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
            {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True}
        ],
        collection_name="test_collection",
        user="integration@demo.ai",
        bot=pytest.bot,
        timestamp=utc_now(),
        schema_metadata=SchemaMetadata(training_needed=True, model_id="text-embedding-3-large", size=3072)
    ).save()
    action = {
        "name": "utter_test_add_prompt_action", 'user_question': {'type': 'from_user_message'},
        "llm_prompts": [
            {
                "name": "System Prompt",
                "data": "You are a personal assistant.",
                "type": "system",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Similarity Prompt",
                "data": "test_collection",
                "instructions": "Answer question based on the context above, if answer is not in the context go check previous logs.",
                "type": "user",
                "source": "bot_content",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "If there is no specific query, assume that user is aking about java programming.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
        ],
        "instructions": ["Answer in a short manner.", "Keep it simple."],
        "num_bot_responses": 5,
        "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE,
        "llm_type": DEFAULT_LLM,
        "hyperparameters": Utility.get_default_llm_hyperparameters()
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/prompt",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Action name cannot start with utter_"
    assert not actual["data"]
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_add_prompt_action_with_invalid_similarity_threshold(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(bot=pytest.bot, user="integration@demo.ai", llm_settings=LLMSettings(enable_faq=True))

    monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)
    CognitionSchema(
        metadata=[
            {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
            {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True}
        ],
        collection_name="science",
        user="integration@demo.ai",
        bot=pytest.bot,
        timestamp=utc_now(),
        schema_metadata=SchemaMetadata(training_needed=True, model_id="text-embedding-3-large", size=3072)
    ).save()
    action = {
        "name": "test_add_prompt_action_with_invalid_similarity_threshold",
        "llm_prompts": [
            {
                "name": "System Prompt",
                "data": "You are a personal assistant.",
                "type": "system",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Similarity Prompt",
                'hyperparameters': {"top_results": 10, "similarity_threshold": 1.70},
                "data": "science",
                "instructions": "Answer question based on the context above, if answer is not in the context go check previous logs.",
                "type": "user",
                "source": "bot_content",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "If there is no specific query, assume that user is aking about java programming.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
        ],
        "num_bot_responses": 5,
        "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE,
        "llm_type": DEFAULT_LLM,
        "hyperparameters": Utility.get_default_llm_hyperparameters()
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/prompt",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == [{'loc': ['body', 'llm_prompts', 1, 'hyperparameters', '__root__'],
                                  'msg': 'similarity_threshold should be within 0.3 and 1', 'type': 'value_error'}]
    assert not actual["data"]
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_add_prompt_action_with_invalid_top_results(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(bot=pytest.bot, user="integration@demo.ai", llm_settings=LLMSettings(enable_faq=True))

    monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)
    CognitionSchema(
        metadata=[
            {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
            {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True}
        ],
        collection_name="science",
        user="integration@demo.ai",
        bot=pytest.bot,
        timestamp=utc_now(),
        schema_metadata=SchemaMetadata(training_needed=True, model_id="text-embedding-3-large", size=3072)
    ).save()
    action = {
        "name": "test_add_prompt_action_with_invalid_top_results",
        "llm_prompts": [
            {
                "name": "System Prompt",
                "data": "You are a personal assistant.",
                "type": "system",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Similarity Prompt",
                'hyperparameters': {"top_results": 40, "similarity_threshold": 0.70},
                "data": "science",
                "instructions": "Answer question based on the context above, if answer is not in the context go check previous logs.",
                "type": "user",
                "source": "bot_content",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "If there is no specific query, assume that user is aking about java programming.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
        ],
        "num_bot_responses": 5,
        "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE,
        "llm_type": DEFAULT_LLM,
        "hyperparameters": Utility.get_default_llm_hyperparameters()
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/prompt",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == [{'loc': ['body', 'llm_prompts', 1, 'hyperparameters', '__root__'],
                                  'msg': 'top_results should not be greater than 30', 'type': 'value_error'}]
    assert not actual["data"]
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_add_prompt_action_with_invalid_query_prompt():
    CognitionSchema(
        metadata=[
            {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
            {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True}
        ],
        collection_name="science",
        user="integration@demo.ai",
        bot=pytest.bot,
        timestamp=utc_now(),
        schema_metadata=SchemaMetadata(training_needed=True, model_id="text-embedding-3-large", size=3072)
    ).save()
    action = {
        "name": "test_add_prompt_action_with_invalid_query_prompt",
        "llm_prompts": [
            {
                "name": "System Prompt",
                "data": "You are a personal assistant.",
                "type": "system",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Similarity Prompt",
                "data": "science",
                "instructions": "Answer question based on the context above, if answer is not in the context go check previous logs.",
                "type": "user",
                "source": "bot_content",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "history",
                "is_enabled": True,
            },
        ],
        "num_bot_responses": 5,
        "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE,
        "llm_type": DEFAULT_LLM,
        "hyperparameters": Utility.get_default_llm_hyperparameters()
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/prompt",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == [
        {
            "loc": ["body", "llm_prompts"],
            "msg": "Query prompt must have static source!",
            "type": "value_error",
        }
    ]
    assert not actual["data"]
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_add_prompt_action_with_invalid_num_bot_responses():
    CognitionSchema(
        metadata=[
            {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
            {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True}
        ],
        collection_name="science",
        user="integration@demo.ai",
        bot=pytest.bot,
        timestamp=utc_now(),
        schema_metadata=SchemaMetadata(training_needed=True, model_id="text-embedding-3-large", size=3072)
    ).save()
    action = {
        "name": "test_add_prompt_action_with_invalid_num_bot_responses",
        "llm_prompts": [
            {
                "name": "System Prompt",
                "data": "You are a personal assistant.",
                "type": "system",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Similarity Prompt",
                "data": "science",
                "instructions": "Answer question based on the context above, if answer is not in the context go check previous logs.",
                "type": "user",
                "source": "bot_content",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "If there is no specific query, assume that user is aking about java programming.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
        ],
        "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE,
        "num_bot_responses": 10,
        "llm_type": DEFAULT_LLM,
        "hyperparameters": Utility.get_default_llm_hyperparameters()
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/prompt",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == [
        {
            "loc": ["body", "num_bot_responses"],
            "msg": "num_bot_responses should not be greater than 5",
            "type": "value_error",
        }
    ]
    assert not actual["data"]
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_add_prompt_action_with_invalid_system_prompt_source():
    CognitionSchema(
        metadata=[
            {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
            {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True}
        ],
        collection_name="science",
        user="integration@demo.ai",
        bot=pytest.bot,
        timestamp=utc_now(),
        schema_metadata=SchemaMetadata(training_needed=True, model_id="text-embedding-3-large", size=3072)
    ).save()
    action = {
        "name": "test_add_prompt_action_with_invalid_system_prompt_source",
        "llm_prompts": [
            {
                "name": "System Prompt",
                "data": "You are a personal assistant.",
                "type": "system",
                "source": "history",
                "is_enabled": True,
            },
            {
                "name": "Similarity Prompt",
                "data": "science",
                "instructions": "Answer question based on the context above, if answer is not in the context go check previous logs.",
                "type": "user",
                "source": "bot_content",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "If there is no specific query, assume that user is aking about java programming.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
        ],
        "num_bot_responses": 5,
        "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE,
        "llm_type": DEFAULT_LLM,
        "hyperparameters": Utility.get_default_llm_hyperparameters()
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/prompt",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == [
        {
            "loc": ["body", "llm_prompts"],
            "msg": "System prompt must have static source!",
            "type": "value_error",
        }
    ]
    assert not actual["data"]
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_add_prompt_action_with_multiple_system_prompt():
    CognitionSchema(
        metadata=[
            {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
            {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True}
        ],
        collection_name="science",
        user="integration@demo.ai",
        bot=pytest.bot,
        timestamp=utc_now(),
        schema_metadata=SchemaMetadata(training_needed=True, model_id="text-embedding-3-large", size=3072)
    ).save()
    action = {
        "name": "test_add_prompt_action_with_multiple_system_prompt",
        "llm_prompts": [
            {
                "name": "System Prompt",
                "data": "You are a personal assistant.",
                "type": "system",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "System Prompt",
                "data": "You are a personal assistant.",
                "instructions": "Answer question based on the context below.",
                "type": "system",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Similarity Prompt",
                "data": "science",
                "instructions": "Answer question based on the context above, if answer is not in the context go check previous logs.",
                "type": "user",
                "source": "bot_content",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "If there is no specific query, assume that user is aking about java programming.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
        ],
        "num_bot_responses": 5,
        "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE,
        "llm_type": DEFAULT_LLM,
        "hyperparameters": Utility.get_default_llm_hyperparameters()
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/prompt",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == [
        {
            "loc": ["body", "llm_prompts"],
            "msg": "Only one system prompt can be present!",
            "type": "value_error",
        }
    ]
    assert not actual["data"]
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_add_prompt_action_with_empty_llm_prompt_name():
    CognitionSchema(
        metadata=[
            {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
            {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True}
        ],
        collection_name="science",
        user="integration@demo.ai",
        bot=pytest.bot,
        timestamp=utc_now(),
        schema_metadata=SchemaMetadata(training_needed=True, model_id="text-embedding-3-large", size=3072)
    ).save()
    action = {
        "name": "test_add_prompt_action_with_empty_llm_prompt_name",
        "llm_prompts": [
            {
                "name": "",
                "data": "You are a personal assistant.",
                "type": "system",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Similarity Prompt",
                "data": "science",
                "instructions": "Answer question based on the context above, if answer is not in the context go check previous logs.",
                "type": "user",
                "source": "bot_content",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "If there is no specific query, assume that user is aking about java programming.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
        ],
        "num_bot_responses": 5,
        "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE,
        "llm_type": DEFAULT_LLM,
        "hyperparameters": Utility.get_default_llm_hyperparameters()
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/prompt",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == [
        {
            "loc": ["body", "llm_prompts"],
            "msg": "Name cannot be empty!",
            "type": "value_error",
        }
    ]
    assert not actual["data"]
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_add_prompt_action_with_empty_data_for_static_prompt():
    CognitionSchema(
        metadata=[
            {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
            {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True}
        ],
        collection_name="science",
        user="integration@demo.ai",
        bot=pytest.bot,
        timestamp=utc_now(),
        schema_metadata=SchemaMetadata(training_needed=True, model_id="text-embedding-3-large", size=3072)
    ).save()
    action = {
        "name": "test_add_prompt_action_with_empty_data_for_static_prompt",
        "llm_prompts": [
            {
                "name": "System Prompt",
                "data": "You are a personal assistant.",
                "type": "system",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Similarity Prompt",
                "data": "science",
                "instructions": "Answer question based on the context above, if answer is not in the context go check previous logs.",
                "type": "user",
                "source": "bot_content",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "If there is no specific query, assume that user is aking about java programming.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
        ],
        "num_bot_responses": 5,
        "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE,
        "llm_type": DEFAULT_LLM,
        "hyperparameters": Utility.get_default_llm_hyperparameters()
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/prompt",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == [
        {
            "loc": ["body", "llm_prompts"],
            "msg": "data is required for static prompts!",
            "type": "value_error",
        }
    ]
    assert not actual["data"]
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_add_prompt_action_with_multiple_history_source_prompts():
    CognitionSchema(
        metadata=[
            {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
            {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True}
        ],
        collection_name="science",
        user="integration@demo.ai",
        bot=pytest.bot,
        timestamp=utc_now(),
        schema_metadata=SchemaMetadata(training_needed=True, model_id="text-embedding-3-large", size=3072)
    ).save()
    action = {
        "name": "test_add_prompt_action_with_multiple_history_source_prompts",
        "llm_prompts": [
            {
                "name": "System Prompt",
                "data": "You are a personal assistant.",
                "type": "system",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "History Prompt",
                "type": "user",
                "source": "history",
                "is_enabled": True,
            },
            {
                "name": "Analytical Prompt",
                "type": "user",
                "source": "history",
                "is_enabled": True,
            },
            {
                "name": "Similarity Prompt",
                "data": "science",
                "instructions": "Answer question based on the context above, if answer is not in the context go check previous logs.",
                "type": "user",
                "source": "bot_content",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "If there is no specific query, assume that user is aking about java programming.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
        ],
        "num_bot_responses": 5,
        "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE,
        "llm_type": DEFAULT_LLM,
        "hyperparameters": Utility.get_default_llm_hyperparameters()
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/prompt",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == [
        {
            "loc": ["body", "llm_prompts"],
            "msg": "Only one history source can be present!",
            "type": "value_error",
        }
    ]
    assert not actual["data"]
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_add_prompt_action_with_gpt_feature_disabled():
    CognitionSchema(
        metadata=[
            {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
            {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True}
        ],
        collection_name="science",
        user="integration@demo.ai",
        bot=pytest.bot,
        timestamp=utc_now(),
        schema_metadata=SchemaMetadata(training_needed=True, model_id="text-embedding-3-large", size=3072)
    ).save()
    action = {
        "name": "test_add_prompt_action_with_gpt_feature_disabled",
        "llm_prompts": [
            {
                "name": "System Prompt",
                "data": "You are a personal assistant.",
                "type": "system",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Similarity Prompt",
                "data": "science",
                "instructions": "Answer question based on the context above, if answer is not in the context go check previous logs.",
                "type": "user",
                "source": "bot_content",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "If there is no specific query, assume that user is aking about java programming.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
        ],
        "num_bot_responses": 5,
        "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE,
        "top_results": 10,
        "similarity_threshold": 0.70,
        "llm_type": DEFAULT_LLM,
        "hyperparameters": Utility.get_default_llm_hyperparameters()
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/prompt",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert (
            actual["message"]
            == "Faq feature is disabled for the bot! Please contact support."
    )
    assert not actual["data"]
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_add_prompt_action_with_invalid_llm_type(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(
            bot=pytest.bot,
            user="integration@demo.ai",
            llm_settings=LLMSettings(enable_faq=True),
        )

    monkeypatch.setattr(MongoProcessor, "get_bot_settings", _mock_get_bot_settings)
    CognitionSchema(
        metadata=[
            {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
            {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True}
        ],
        collection_name="test_collection",
        user="integration@demo.ai",
        bot=pytest.bot,
        timestamp=utc_now(),
        schema_metadata=SchemaMetadata(training_needed=True, model_id="text-embedding-3-large", size=3072)
    ).save()
    action = {
        "name": "test_add_prompt_action_with_invalid_llm_type", 'user_question': {'type': 'from_user_message'},
        "llm_prompts": [
            {
                "name": "System Prompt",
                "data": "You are a personal assistant.",
                "type": "system",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Similarity Prompt",
                "data": "test_collection",
                "instructions": "Answer question based on the context above, if answer is not in the context go check previous logs.",
                "type": "user",
                "source": "bot_content",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "If there is no specific query, assume that user is aking about java programming.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
        ],
        "instructions": ["Answer in a short manner.", "Keep it simple."],
        "num_bot_responses": 5,
        "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE,
        "llm_type": "test",
        "hyperparameters": Utility.get_default_llm_hyperparameters()
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/prompt",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not DeepDiff(actual["message"],
                        [{'loc': ['body', 'llm_type'], 'msg': 'Invalid llm type', 'type': 'value_error'}],
                        ignore_order=True)
    assert not actual["success"]
    assert not actual["data"]
    assert actual["error_code"] == 422


def test_add_prompt_action_with_invalid_hyperameters(monkeypatch):
    temp = Utility.get_default_llm_hyperparameters()
    temp['temperature'] = 3.0

    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(
            bot=pytest.bot,
            user="integration@demo.ai",
            llm_settings=LLMSettings(enable_faq=True),
        )

    monkeypatch.setattr(MongoProcessor, "get_bot_settings", _mock_get_bot_settings)
    CognitionSchema(
        metadata=[
            {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
            {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True}
        ],
        collection_name="test_collection",
        user="integration@demo.ai",
        bot=pytest.bot,
        timestamp=utc_now(),
        schema_metadata=SchemaMetadata(training_needed=True, model_id="text-embedding-3-large", size=3072)
    ).save()
    action = {
        "name": "test_add_prompt_action_with_invalid_hyperameters", 'user_question': {'type': 'from_user_message'},
        "llm_prompts": [
            {
                "name": "System Prompt",
                "data": "You are a personal assistant.",
                "type": "system",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Similarity Prompt",
                "data": "test_collection",
                "instructions": "Answer question based on the context above, if answer is not in the context go check previous logs.",
                "type": "user",
                "source": "bot_content",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "If there is no specific query, assume that user is aking about java programming.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
        ],
        "instructions": ["Answer in a short manner.", "Keep it simple."],
        "num_bot_responses": 5,
        "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE,
        "llm_type": DEFAULT_LLM,
        "hyperparameters": temp
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/prompt",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not DeepDiff(actual["message"],
                        [{'loc': ['body', 'hyperparameters'],
                          'msg': "['temperature']: 3.0 is greater than the maximum of 2.0", 'type': 'value_error'}],
                        ignore_order=True)
    assert not actual["success"]
    assert not actual["data"]
    assert actual["error_code"] == 422


def test_add_prompt_action(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(
            bot=pytest.bot,
            user="integration@demo.ai",
            llm_settings=LLMSettings(enable_faq=True),
        )

    monkeypatch.setattr(MongoProcessor, "get_bot_settings", _mock_get_bot_settings)
    CognitionSchema(
        metadata=[
            {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
            {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True}
        ],
        collection_name="test_collection",
        user="integration@demo.ai",
        bot=pytest.bot,
        timestamp=utc_now(),
        schema_metadata=SchemaMetadata(training_needed=True, model_id="text-embedding-3-large", size=3072)
    ).save()
    action = {
        "name": "test_add_prompt_action", 'user_question': {'type': 'from_user_message'},
        "llm_prompts": [
            {
                "name": "System Prompt",
                "data": "You are a personal assistant.",
                "type": "system",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Similarity Prompt",
                "data": "test_collection",
                "instructions": "Answer question based on the context above, if answer is not in the context go check previous logs.",
                "type": "user",
                "source": "bot_content",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "If there is no specific query, assume that user is aking about java programming.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
        ],
        "instructions": ["Answer in a short manner.", "Keep it simple."],
        "num_bot_responses": 5,
        "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE,
        "llm_type": DEFAULT_LLM,
        "hyperparameters": Utility.get_default_llm_hyperparameters()
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/prompt",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Action Added Successfully"
    assert actual["data"]["_id"]
    pytest.action_id = actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0


def test_add_prompt_action_already_exist(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(
            bot=pytest.bot,
            user="integration@demo.ai",
            llm_settings=LLMSettings(enable_faq=True),
        )

    monkeypatch.setattr(MongoProcessor, "get_bot_settings", _mock_get_bot_settings)
    CognitionSchema(
        metadata=[
            {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
            {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True}
        ],
        collection_name="test_collection",
        user="integration@demo.ai",
        bot=pytest.bot,
        timestamp=utc_now(),
        schema_metadata=SchemaMetadata(training_needed=True, model_id="text-embedding-3-large", size=3072)
    ).save()
    action = {
        "name": "test_add_prompt_action", 'user_question': {'type': 'from_user_message'},
        "llm_prompts": [
            {
                "name": "System Prompt",
                "data": "You are a personal assistant.",
                "type": "system",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Similarity Prompt",
                "data": "test_collection",
                "instructions": "Answer question based on the context above, if answer is not in the context go check previous logs.",
                "type": "user",
                "source": "bot_content",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "If there is no specific query, assume that user is aking about java programming.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
        ],
        "instructions": ["Answer in a short manner.", "Keep it simple."],
        "num_bot_responses": 5,
        "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE,
        "llm_type": DEFAULT_LLM,
        "hyperparameters": Utility.get_default_llm_hyperparameters()
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/prompt",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Action exists!"
    assert not actual["data"]
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_update_prompt_action_does_not_exist():
    CognitionSchema(
        metadata=[
            {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
            {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True}
        ],
        collection_name="test_collection",
        user="integration@demo.ai",
        bot=pytest.bot,
        timestamp=utc_now(),
        schema_metadata=SchemaMetadata(training_needed=True, model_id="text-embedding-3-large", size=3072)
    ).save()
    action = {
        "name": "test_update_prompt_action_does_not_exist",
        "llm_prompts": [
            {
                "name": "System Prompt",
                "data": "You are a personal assistant.",
                "type": "system",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Similarity Prompt",
                "data": "test_collection",
                "instructions": "Answer question based on the context above, if answer is not in the context go check previous logs.",
                "type": "user",
                "source": "bot_content",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "If there is no specific query, assume that user is aking about java programming.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
        ],
        "num_bot_responses": 5,
        "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE,
        "llm_type": DEFAULT_LLM,
        "hyperparameters": Utility.get_default_llm_hyperparameters()
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/prompt/61512cc2c6219f0aae7bba3d",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Action not found"
    assert not actual["data"]
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_update_prompt_action_with_invalid_similarity_threshold():
    CognitionSchema(
        metadata=[
            {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
            {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True}
        ],
        collection_name="test_collection",
        user="integration@demo.ai",
        bot=pytest.bot,
        timestamp=utc_now(),
        schema_metadata=SchemaMetadata(training_needed=True, model_id="text-embedding-3-large", size=3072)
    ).save()
    action = {
        "name": "test_update_prompt_action_with_invalid_similarity_threshold",
        "llm_prompts": [
            {
                "name": "System Prompt",
                "data": "You are a personal assistant.",
                "type": "system",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Similarity Prompt",
                "data": "test_collection",
                'hyperparameters': {"top_results": 9, "similarity_threshold": 1.50},
                "instructions": "Answer question based on the context above, if answer is not in the context go check previous logs.",
                "type": "user",
                "source": "bot_content",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "If there is no specific query, assume that user is aking about java programming.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
        ],
        "num_bot_responses": 5,
        "failure_message": "updated_failure_message",
        "llm_type": DEFAULT_LLM,
        "hyperparameters": Utility.get_default_llm_hyperparameters()
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/prompt/{pytest.action_id}",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == [{'loc': ['body', 'llm_prompts', 1, 'hyperparameters', '__root__'],
                                  'msg': 'similarity_threshold should be within 0.3 and 1', 'type': 'value_error'}]
    assert not actual["data"]
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_update_prompt_action_with_invalid_top_results():
    CognitionSchema(
        metadata=[
            {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
            {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True}
        ],
        collection_name="test_collection",
        user="integration@demo.ai",
        bot=pytest.bot,
        timestamp=utc_now(),
        schema_metadata=SchemaMetadata(training_needed=True, model_id="text-embedding-3-large", size=3072)
    ).save()
    action = {
        "name": "test_update_prompt_action_with_invalid_top_results",
        "llm_prompts": [
            {
                "name": "System Prompt",
                "data": "You are a personal assistant.",
                "type": "system",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Similarity Prompt",
                "data": "test_collection"
                , 'hyperparameters': {"top_results": 39, "similarity_threshold": 0.50},
                "instructions": "Answer question based on the context above, if answer is not in the context go check previous logs.",
                "type": "user",
                "source": "bot_content",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "If there is no specific query, assume that user is aking about java programming here.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
        ],
        "num_bot_responses": 5,
        "failure_message": "updated_failure_message",
        "llm_type": DEFAULT_LLM,
        "hyperparameters": Utility.get_default_llm_hyperparameters()
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/prompt/{pytest.action_id}",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == [{'loc': ['body', 'llm_prompts', 1, 'hyperparameters', '__root__'],
                                  'msg': 'top_results should not be greater than 30', 'type': 'value_error'}]
    assert not actual["data"]
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_update_prompt_action_with_invalid_num_bot_responses():
    CognitionSchema(
        metadata=[
            {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
            {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True}
        ],
        collection_name="science",
        user="integration@demo.ai",
        bot=pytest.bot,
        timestamp=utc_now(),
        schema_metadata=SchemaMetadata(training_needed=True, model_id="text-embedding-3-large", size=3072)
    ).save()
    action = {
        "name": "test_update_prompt_action_with_invalid_num_bot_responses",
        "llm_prompts": [
            {
                "name": "System Prompt",
                "data": "You are a personal assistant.",
                "type": "system",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Similarity Prompt",
                "data": "science",
                "instructions": "Answer question based on the context above, if answer is not in the context go check previous logs.",
                "type": "user",
                "source": "bot_content",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "If there is no specific query, assume that user is aking about java programming.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
        ],
        "num_bot_responses": 50,
        "failure_message": "updated_failure_message",
        "llm_type": DEFAULT_LLM,
        "hyperparameters": Utility.get_default_llm_hyperparameters()
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/prompt/{pytest.action_id}",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["message"] == [
        {'loc': ['body', 'num_bot_responses'], 'msg': 'num_bot_responses should not be greater than 5',
         'type': 'value_error'}]
    assert not actual["data"]
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_update_prompt_action_with_invalid_query_prompt():
    CognitionSchema(
        metadata=[
            {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
            {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True}
        ],
        collection_name="test_collection",
        user="integration@demo.ai",
        bot=pytest.bot,
        timestamp=utc_now(),
        schema_metadata=SchemaMetadata(training_needed=True, model_id="text-embedding-3-large", size=3072)
    ).save()
    action = {
        "name": "test_update_prompt_action_with_invalid_query_prompt",
        "llm_prompts": [
            {
                "name": "System Prompt",
                "data": "You are a personal assistant.",
                "type": "system",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Similarity Prompt",
                "data": "test_collection",
                "instructions": "Answer question based on the context above, if answer is not in the context go check previous logs.",
                "type": "user",
                "source": "bot_content",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "A programming language is a system of notation for writing computer programs.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "history",
                "is_enabled": True,
            },
        ],
        "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE,
        "num_bot_responses": 5,
        "use_query_prompt": True,
        "query_prompt": "",
        "llm_type": DEFAULT_LLM,
        "hyperparameters": Utility.get_default_llm_hyperparameters()
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/prompt/{pytest.action_id}",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["message"] == [
        {
            "loc": ["body", "llm_prompts"],
            "msg": "Query prompt must have static source!",
            "type": "value_error",
        }
    ]
    assert not actual["success"]


def test_update_prompt_action_with_query_prompt_with_false():
    action = {
        "name": "test_update_prompt_action_with_query_prompt_with_false",
        "llm_prompts": [
            {
                "name": "System Prompt",
                "data": "You are a personal assistant.",
                "type": "system",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Similarity Prompt",
                "data": "Bot_collection",
                "instructions": "Answer question based on the context above, if answer is not in the context go check previous logs.",
                "type": "user",
                "source": "bot_content",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "bot_content",
                "is_enabled": False,
            },
        ],
        "failure_message": "updated_failure_message",
        "num_bot_responses": 5,
        "set_slots": [
            {"name": "gpt_result", "value": "${data}", "evaluation_type": "expression"},
            {
                "name": "gpt_result_type",
                "value": "${data.type}",
                "evaluation_type": "script",
            },
        ],
        "dispatch_response": False,
        "llm_type": DEFAULT_LLM,
        "hyperparameters": Utility.get_default_llm_hyperparameters()
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/prompt/{pytest.action_id}",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["message"] == [
        {
            "loc": ["body", "llm_prompts"],
            "msg": "Query prompt must have static source!",
            "type": "value_error",
        }
    ]
    assert not actual["success"]


def test_update_prompt_action():
    CognitionSchema(
        metadata=[
            {"column_name": "id", "data_type": "int", "enable_search": True, "create_embeddings": True},
            {"column_name": "item", "data_type": "str", "enable_search": True, "create_embeddings": True}
        ],
        collection_name="test_collection",
        user="integration@demo.ai",
        bot=pytest.bot,
        timestamp=utc_now(),
        schema_metadata=SchemaMetadata(training_needed=True, model_id="text-embedding-3-large", size=3072)
    ).save()
    action = {
        "name": "test_update_prompt_action", 'user_question': {'type': 'from_slot', 'value': 'prompt_question'},
        "llm_prompts": [
            {
                "name": "System Prompt",
                "data": "You are a personal assistant.",
                "type": "system",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Similarity_analytical Prompt",
                "data": "test_collection",
                "instructions": "Answer question based on the context above, if answer is not in the context go check previous logs.",
                "type": "user",
                "source": "bot_content",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "A programming language is a system of notation for writing computer programs.Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "If there is no specific query, assume that user is aking about java programming language,",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
        ],
        "instructions": ["Answer in a short manner.", "Keep it simple."],
        "num_bot_responses": 5,
        "failure_message": "updated_failure_message",
        "llm_type": DEFAULT_LLM,
        "hyperparameters": Utility.get_default_llm_hyperparameters()
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/prompt/{pytest.action_id}",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["message"] == "Action updated!"
    assert not actual["data"]
    assert actual["success"]
    assert actual["error_code"] == 0


def test_get_prompt_action():
    response = client.get(
        f"/api/bot/{pytest.bot}/action/prompt",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["success"]
    assert actual["error_code"] == 0
    assert not actual["message"]

    actual_data = actual["data"]
    actual_data[0].pop("_id", None)

    expected_data = [{
        'name': 'test_update_prompt_action',
        'num_bot_responses': 5,
        'failure_message': 'updated_failure_message',
        'user_question': {'type': 'from_slot', 'value': 'prompt_question'},
        'llm_type': 'openai',
        'process_media': False,
        'hyperparameters': {
            'temperature': 0.0,
            'max_tokens': 300,
            'model': 'gpt-4.1-mini',
            'top_p': 0.0,
            'n': 1,
            'stop': None,
            'presence_penalty': 0.0,
            'frequency_penalty': 0.0,
            'logit_bias': {}
        },
        'llm_prompts': [
            {
                'name': 'System Prompt',
                'data': 'You are a personal assistant.',
                'type': 'system',
                'source': 'static',
                'is_enabled': True
            },
            {
                'name': 'Similarity_analytical Prompt',
                'data': 'test_collection',
                'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                'type': 'user',
                'source': 'bot_content',
                'is_enabled': True
            },
            {
                'name': 'Query Prompt',
                'data': 'A programming language is a system of notation for writing computer programs.Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                'instructions': 'Answer according to the context',
                'type': 'query',
                'source': 'static',
                'is_enabled': True
            },
            {
                'name': 'Query Prompt',
                'data': 'If there is no specific query, assume that user is aking about java programming language,',
                'instructions': 'Answer according to the context',
                'type': 'query',
                'source': 'static',
                'is_enabled': True
            }
        ],
        'instructions': ['Answer in a short manner.', 'Keep it simple.'],
        'set_slots': [],
        'dispatch_response': True,
        'status': True
    }]

    assert not DeepDiff(actual_data, expected_data, ignore_order=True)



def test_add_prompt_action_with_empty_collection_for_bot_content_prompt(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(
            bot=pytest.bot,
            user="integration@demo.ai",
            llm_settings=LLMSettings(enable_faq=True),
        )

    monkeypatch.setattr(MongoProcessor, "get_bot_settings", _mock_get_bot_settings)

    action = {
        "name": "test_add_prompt_action_with_empty_collection_for_bot_content_prompt",
        'user_question': {'type': 'from_user_message'},
        "llm_prompts": [
            {
                "name": "System Prompt",
                "data": "You are a personal assistant.",
                "type": "system",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Similarity Prompt",
                "data": "",
                "instructions": "Answer question based on the context above, if answer is not in the context go check previous logs.",
                "type": "user",
                "source": "bot_content",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "Query Prompt",
                "data": "If there is no specific query, assume that user is aking about java programming.",
                "instructions": "Answer according to the context",
                "type": "query",
                "source": "static",
                "is_enabled": True,
            },
        ],
        "instructions": ["Answer in a short manner.", "Keep it simple."],
        "num_bot_responses": 5,
        "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE,
        "llm_type": DEFAULT_LLM,
        "hyperparameters": Utility.get_default_llm_hyperparameters()
    }

    # Add prompt action
    response = client.post(
        f"/api/bot/{pytest.bot}/action/prompt",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Action Added Successfully"
    assert actual["data"]["_id"]
    pytest.action_id = actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0

    # Get all prompt actions
    response = client.get(
        f"/api/bot/{pytest.bot}/action/prompt",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert not actual["message"]

    prompt_action = actual["data"][1]
    prompt_action.pop("_id", None)

    expected_action = {
        'name': 'test_add_prompt_action_with_empty_collection_for_bot_content_prompt',
        'num_bot_responses': 5,
        'failure_message': "I'm sorry, I didn't quite understand that. Could you rephrase?",
        'user_question': {'type': 'from_user_message'},
        'llm_type': 'openai',
        'process_media': False,
        'hyperparameters': {
            'temperature': 0.0,
            'max_tokens': 300,
            'model': 'gpt-4.1-mini',
            'top_p': 0.0,
            'n': 1,
            'stop': None,
            'presence_penalty': 0.0,
            'frequency_penalty': 0.0,
            'logit_bias': {}
        },
        'llm_prompts': [
            {
                'name': 'System Prompt',
                'data': 'You are a personal assistant.',
                'type': 'system',
                'source': 'static',
                'is_enabled': True
            },
            {
                'name': 'Similarity Prompt',
                'data': 'default',
                'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                'type': 'user',
                'source': 'bot_content',
                'is_enabled': True
            },
            {
                'name': 'Query Prompt',
                'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                'instructions': 'Answer according to the context',
                'type': 'query',
                'source': 'static',
                'is_enabled': True
            },
            {
                'name': 'Query Prompt',
                'data': 'If there is no specific query, assume that user is aking about java programming.',
                'instructions': 'Answer according to the context',
                'type': 'query',
                'source': 'static',
                'is_enabled': True
            }
        ],
        'instructions': ['Answer in a short manner.', 'Keep it simple.'],
        'set_slots': [],
        'dispatch_response': True,
        'status': True
    }

    assert not DeepDiff(prompt_action, expected_action, ignore_order=True)
    CognitionSchema.objects(bot=pytest.bot).delete()

def test_add_prompt_action_with_bot_content_prompt_with_payload(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(bot=pytest.bot, user="integration@demo.ai", llm_settings=LLMSettings(enable_faq=True),
                           cognition_collections_limit=5)

    monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)

    response_one = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json={
            "metadata": [
                {"column_name": "name", "data_type": "str", "enable_search": True, "create_embeddings": True}],
            "collection_name": "states"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response_one.json()
    pytest.delete_schema_id = actual["data"]["_id"]

    payload = {
        "data": {"name": "Karnataka"},
        "content_type": "json",
        "collection": "states"}
    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    pytest.content_id_text = actual["data"]["_id"]
    assert actual["message"] == "Record saved!"
    assert actual["data"]["_id"]
    assert actual["error_code"] == 0

    action = {'name': 'test_add_prompt_action_with_bot_content_prompt_with_payload',
              'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                               'source': 'static', 'is_enabled': True},
                              {'name': 'Similarity Prompt',
                               'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                               'type': 'user', 'source': 'bot_content', 'data': 'states', 'is_enabled': True},
                              {'name': 'Query Prompt',
                               'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                               'instructions': 'Answer according to the context', 'type': 'query',
                               'source': 'static', 'is_enabled': True},
                              {'name': 'Query Prompt',
                               'data': 'If there is no specific query, assume that user is aking about java programming.',
                               'instructions': 'Answer according to the context', 'type': 'query',
                               'source': 'static', 'is_enabled': True}],
              'instructions': ['Answer in a short manner.', 'Keep it simple.'],
              'num_bot_responses': 5,
              "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE,
              "llm_type": DEFAULT_LLM,
              "hyperparameters": Utility.get_default_llm_hyperparameters()
              }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/prompt",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    response = client.get(
        f"/api/bot/{pytest.bot}/action/prompt",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    action_data = actual["data"][2]
    action_data.pop("_id", None)

    expected_action = {
        'name': 'test_add_prompt_action_with_bot_content_prompt_with_payload',
        'num_bot_responses': 5,
        'failure_message': "I'm sorry, I didn't quite understand that. Could you rephrase?",
        'user_question': {'type': 'from_user_message'},
        'llm_type': 'openai',
        'process_media': False,
        'hyperparameters': {
            'temperature': 0.0,
            'max_tokens': 300,
            'model': 'gpt-4.1-mini',
            'top_p': 0.0,
            'n': 1,
            'stop': None,
            'presence_penalty': 0.0,
            'frequency_penalty': 0.0,
            'logit_bias': {}
        },
        'llm_prompts': [
            {
                'name': 'System Prompt',
                'data': 'You are a personal assistant.',
                'type': 'system',
                'source': 'static',
                'is_enabled': True
            },
            {
                'name': 'Similarity Prompt',
                'data': 'states',
                'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                'type': 'user',
                'source': 'bot_content',
                'is_enabled': True
            },
            {
                'name': 'Query Prompt',
                'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                'instructions': 'Answer according to the context',
                'type': 'query',
                'source': 'static',
                'is_enabled': True
            },
            {
                'name': 'Query Prompt',
                'data': 'If there is no specific query, assume that user is aking about java programming.',
                'instructions': 'Answer according to the context',
                'type': 'query',
                'source': 'static',
                'is_enabled': True
            }
        ],
        'instructions': ['Answer in a short manner.', 'Keep it simple.'],
        'set_slots': [],
        'dispatch_response': True,
        'status': True
    }

    assert not DeepDiff(action_data, expected_action, ignore_order=True)


def test_add_prompt_action_with_bot_content_prompt_with_content(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(bot=pytest.bot, user="integration@demo.ai", llm_settings=LLMSettings(enable_faq=True),
                           cognition_collections_limit=5)

    monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)

    response_one = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json={
            "metadata": None,
            "collection_name": "python"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response_one.json()
    pytest.delete_schema_id = actual["data"]["_id"]

    payload = {
        "data": "Python is a high-level, general-purpose programming language. "
                "Its design philosophy emphasizes code readability with the use of significant indentation. "
                "Python is dynamically typed and garbage-collected.",
        "content_type": "text",
        "collection": "python"}
    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    pytest.content_id_text = actual["data"]["_id"]
    assert actual["message"] == "Record saved!"
    assert actual["data"]["_id"]
    assert actual["error_code"] == 0

    action = {'name': 'test_add_prompt_action_with_bot_content_prompt_with_content',
              'llm_prompts': [{'name': 'System Prompt', 'data': 'You are a personal assistant.', 'type': 'system',
                               'source': 'static', 'is_enabled': True},
                              {'name': 'Similarity Prompt',
                               'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                               'type': 'user', 'source': 'bot_content', 'data': 'python', 'is_enabled': True},
                              {'name': 'Query Prompt',
                               'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                               'instructions': 'Answer according to the context', 'type': 'query',
                               'source': 'static', 'is_enabled': True},
                              {'name': 'Query Prompt',
                               'data': 'If there is no specific query, assume that user is aking about java programming.',
                               'instructions': 'Answer according to the context', 'type': 'query',
                               'source': 'static', 'is_enabled': True}],
              'instructions': ['Answer in a short manner.', 'Keep it simple.'],
              'num_bot_responses': 5,
              "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE,
              "llm_type": DEFAULT_LLM,
              "hyperparameters": Utility.get_default_llm_hyperparameters()
              }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/prompt",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    response = client.get(
        f"/api/bot/{pytest.bot}/action/prompt",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual=response.json()
    prompt_action = actual["data"][3]
    prompt_action.pop("_id", None)

    expected = {
        'name': 'test_add_prompt_action_with_bot_content_prompt_with_content',
        'num_bot_responses': 5,
        'failure_message': "I'm sorry, I didn't quite understand that. Could you rephrase?",
        'user_question': {'type': 'from_user_message'},
        'llm_type': 'openai',
        'process_media': False,
        'hyperparameters': {
            'temperature': 0.0,
            'max_tokens': 300,
            'model': 'gpt-4.1-mini',
            'top_p': 0.0,
            'n': 1,
            'stop': None,
            'presence_penalty': 0.0,
            'frequency_penalty': 0.0,
            'logit_bias': {}
        },
        'llm_prompts': [
            {
                'name': 'System Prompt',
                'data': 'You are a personal assistant.',
                'type': 'system',
                'source': 'static',
                'is_enabled': True
            },
            {
                'name': 'Similarity Prompt',
                'data': 'python',
                'instructions': 'Answer question based on the context above, if answer is not in the context go check previous logs.',
                'type': 'user',
                'source': 'bot_content',
                'is_enabled': True
            },
            {
                'name': 'Query Prompt',
                'data': 'A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.',
                'instructions': 'Answer according to the context',
                'type': 'query',
                'source': 'static',
                'is_enabled': True
            },
            {
                'name': 'Query Prompt',
                'data': 'If there is no specific query, assume that user is aking about java programming.',
                'instructions': 'Answer according to the context',
                'type': 'query',
                'source': 'static',
                'is_enabled': True
            }
        ],
        'instructions': ['Answer in a short manner.', 'Keep it simple.'],
        'set_slots': [],
        'dispatch_response': True,
        'status': True
    }

    assert not DeepDiff(prompt_action, expected, ignore_order=True, ignore_type_in_groups=[(dict, dict)])

def test_add_prompt_action_with_crud(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(
            bot=pytest.bot,
            user="integration@demo.ai",
            llm_settings=LLMSettings(enable_faq=True),
        )
    add_payload_1 = {
        "collection_name": "test_collection",
        "is_secure": ["mobile_number"],
        "is_non_editable": ["empid"],
        "data": {
            "mobile_number": "09876541",
            "name": "testing_1",
            "empid": 12345
        },
        "status": True
    }
    add_resp_1 = client.post(
        f"/api/bot/{pytest.bot}/data/collection",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=add_payload_1
    )
    monkeypatch.setattr(MongoProcessor, "get_bot_settings", _mock_get_bot_settings)

    action = {
        "name": "test_add_prompt_action_crud",
        'user_question': {'type': 'from_user_message'},
        "llm_prompts": [
            {
                "name": "System Prompt",
                "data": "You are a personal assistant.",
                "type": "system",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "CRUD Prompt",
                "instructions": "Fetch data from the collection and answer accordingly.",
                "type": "user",
                "source": "crud",
                "is_enabled": True,
                "crud_config": {
                    "collections": ["test_collection"],
                    "query": {"key": "value"},
                    "result_limit": 5,
                    "query_source":"value"
                }
            }
        ],
        "instructions": ["Answer in a short manner.", "Keep it simple."],
        "num_bot_responses": 5,
        "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE,
        "llm_type": DEFAULT_LLM,
        "hyperparameters": Utility.get_default_llm_hyperparameters()
    }

    response = client.post(
        f"/api/bot/{pytest.bot}/action/prompt",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["message"] == "Action Added Successfully"
    assert actual["data"]["_id"]
    pytest.action_id = actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0

def test_add_prompt_action_with_crud_query_as_string(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(
            bot=pytest.bot,
            user="integration@demo.ai",
            llm_settings=LLMSettings(enable_faq=True),
        )

    monkeypatch.setattr(MongoProcessor, "get_bot_settings", _mock_get_bot_settings)

    action = {
        "name": "test_add_prompt_action_crud_string_query",
        'user_question': {'type': 'from_user_message'},
        "llm_prompts": [
            {
                "name": "System Prompt",
                "data": "You are a personal assistant.",
                "type": "system",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "CRUD Prompt",
                "instructions": "Fetch data from the collection and answer accordingly.",
                "type": "user",
                "source": "crud",
                "is_enabled": True,
                "crud_config": {
                    "collections": ["test_collection"],
                    "query": '{"key": "value"}',  # JSON string to hit the isinstance check
                    "result_limit": 5,
                    "query_source": "value"
                }
            }
        ],
        "instructions": ["Answer in a short manner.", "Keep it simple."],
        "num_bot_responses": 5,
        "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE,
        "llm_type": DEFAULT_LLM,
        "hyperparameters": Utility.get_default_llm_hyperparameters()
    }

    response = client.post(
        f"/api/bot/{pytest.bot}/action/prompt",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["message"] == "Action Added Successfully"
    assert actual["data"]["_id"]
    pytest.action_id = actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0

def test_add_prompt_action_with_crud_query_invalid_json(monkeypatch):
    from fastapi import status

    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(
            bot=pytest.bot,
            user="integration@demo.ai",
            llm_settings=LLMSettings(enable_faq=True),
        )
    monkeypatch.setattr(MongoProcessor, "get_bot_settings", _mock_get_bot_settings)

    action = {
        "name": "test_add_prompt_action_crud_invalid_json",
        "user_question": {"type": "from_user_message"},
        "llm_prompts": [
            {
                "name": "System Prompt",
                "data": "You are a personal assistant.",
                "type": "system",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "CRUD Prompt",
                "instructions": "Fetch data from the collection and answer accordingly.",
                "type": "user",
                "source": "crud",
                "is_enabled": True,
                "crud_config": {
                    "collections": ["test_collection"],
                    "query": "this is not json",
                    "result_limit": 5,
                    "query_source": "value"
                }
            }
        ],
        "instructions": ["Answer in a short manner.", "Keep it simple."],
        "num_bot_responses": 5,
        "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE,
        "llm_type": DEFAULT_LLM,
        "hyperparameters": Utility.get_default_llm_hyperparameters()
    }

    response = client.post(
        f"/api/bot/{pytest.bot}/action/prompt",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    response=response.json()
    assert response["error_code"] == 422
    assert any(
        "Invalid JSON format in query: this is not json" in err["msg"]
        for err in response["message"]
    )


def test_add_prompt_action_with_crud_query_source_slot_valid(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(
            bot=pytest.bot,
            user="integration@demo.ai",
            llm_settings=LLMSettings(enable_faq=True),
        )

    monkeypatch.setattr(MongoProcessor, "get_bot_settings", _mock_get_bot_settings)

    action = {
        "name": "test_add_prompt_action_crud_slot_query",
        "user_question": {"type": "from_user_message"},
        "llm_prompts": [
            {
                "name": "System Prompt",
                "data": "You are a personal assistant.",
                "type": "system",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "CRUD Prompt",
                "instructions": "Fetch data from the collection and answer accordingly.",
                "type": "user",
                "source": "crud",
                "is_enabled": True,
                "crud_config": {
                    "collections": ["test_collection"],
                    "query": "slot_name",  # This is a valid slot name
                    "result_limit": 5,
                    "query_source": "slot"
                }
            }
        ],
        "instructions": ["Answer in a short manner.", "Keep it simple."],
        "num_bot_responses": 5,
        "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE,
        "llm_type": DEFAULT_LLM,
        "hyperparameters": Utility.get_default_llm_hyperparameters()
    }

    response = client.post(
        f"/api/bot/{pytest.bot}/action/prompt",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["message"] == "Action Added Successfully"
    assert actual["data"]["_id"]
    pytest.action_id = actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0


def test_add_prompt_action_with_crud_query_source_slot_invalid(monkeypatch):
    from fastapi import status

    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(
            bot=pytest.bot,
            user="integration@demo.ai",
            llm_settings=LLMSettings(enable_faq=True),
        )

    monkeypatch.setattr(MongoProcessor, "get_bot_settings", _mock_get_bot_settings)

    action = {
        "name": "test_add_prompt_action_crud_slot_query_invalid",
        "user_question": {"type": "from_user_message"},
        "llm_prompts": [
            {
                "name": "System Prompt",
                "data": "You are a personal assistant.",
                "type": "system",
                "source": "static",
                "is_enabled": True,
            },
            {
                "name": "CRUD Prompt",
                "instructions": "Fetch data from the collection and answer accordingly.",
                "type": "user",
                "source": "crud",
                "is_enabled": True,
                "crud_config": {
                    "collections": ["test_collection"],
                    "query": {"slot": "value"},  # Invalid: query must be a string for slot source
                    "result_limit": 5,
                    "query_source": "slot"
                }
            }
        ],
        "instructions": ["Answer in a short manner.", "Keep it simple."],
        "num_bot_responses": 5,
        "failure_message": DEFAULT_NLU_FALLBACK_RESPONSE,
        "llm_type": DEFAULT_LLM,
        "hyperparameters": Utility.get_default_llm_hyperparameters()
    }

    response = client.post(
        f"/api/bot/{pytest.bot}/action/prompt",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    response = response.json()

    assert response["error_code"] == 422
    assert any(
        "When query_source is 'slot', query must be a valid slot name." in err["msg"]
        for err in response["message"]
    )



def test_delete_prompt_action_not_exists():
    response = client.delete(
        f"/api/bot/{pytest.bot}/action/non_existent_kairon_faq_action",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert (
            actual["message"]
            == 'Action with name "non_existent_kairon_faq_action" not found'
    )


def test_delete_prompt_action_1():
    response = client.delete(
        f"/api/bot/{pytest.bot}/action/test_add_prompt_action",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action deleted"


def test_list_entities_empty():
    response = client.get(
        f"/api/bot/{pytest.bot}/entities",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert len(actual['data']) == 31
    assert actual["success"]
