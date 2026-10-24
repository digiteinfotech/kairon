from tests.integration_test.services_support import *  # noqa: F403
from tests.integration_test.services_support import setup, fast_rasa_training



def test_list_available_actions():
    script = "bot_response='hello world'"
    request_body = {
        "name": "test_list_available_actions_pyscript_action",
        "source_code": script,
        "dispatch_response": False,
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/pyscript",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["success"]

    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/actions",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual=response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual['data'][-1]['name'] == 'test_list_available_actions_pyscript_action'
    assert actual['data'][-1]['type'] == 'pyscript_action'


def test_get_client_config_url_with_ip_info(monkeypatch):
    monkeypatch.setitem(
        Utility.environment["model"]["agent"], "url", "http://localhost"
    )
    with patch(
            "kairon.shared.plugins.ipinfo.IpInfoTracker.execute"
    ) as mock_geo_location:
        mock_geo_location.return_value = {"City": "Mumbai", "Network": "CATO"}
        response = client.get(
            f"/api/bot/{pytest.bot}/chat/client/config/url",
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        )
        actual = response.json()
        assert actual["success"]
        assert actual["error_code"] == 0
        assert actual["data"]
        pytest.url = actual["data"]

    response = client.get(
        f"/api/bot/{pytest.bot}/metric/user/logs/user_metrics",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["total"] == 2
    assert actual["data"]["logs"][0]["geo_location"] == {
        "City": "Mumbai",
        "Network": "CATO",
    }
    assert actual["data"]["logs"][0]["ip_info"] == "testclient"
    assert actual["data"]["logs"][0]["metric_type"] == "user_metrics"
    assert actual["data"]["logs"][0]["bot"] == pytest.bot


def test_metadata_upload_api(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(bot=pytest.bot, user="integration@demo.ai", llm_settings=LLMSettings(enable_faq=True))

    monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)

    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json={
            "metadata": [
                {"column_name": "details", "data_type": "str", "enable_search": True, "create_embeddings": True}],
            "collection_name": "Details"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    pytest.schema_id = actual["data"]["_id"]
    assert actual["message"] == "Schema saved!"
    assert actual["data"]["_id"]
    assert actual["error_code"] == 0

    response_schema = client.get(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual_schema = response_schema.json()
    assert actual_schema["data"][0]['collection_name'] == 'details'
    assert actual_schema["data"][0]['metadata'][0] == {'column_name': 'details', 'data_type': 'str',
                                                       'enable_search': True, 'create_embeddings': True}
    assert actual_schema["error_code"] == 0

    payload = {
        "data": {"details": "Nupur"},
        "collection": "Details",
        "content_type": "json"}
    payload_response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    payload_actual = payload_response.json()
    pytest.cognition_id = payload_actual["data"]["_id"]
    assert payload_actual["message"] == "Record saved!"
    assert payload_actual["error_code"] == 0

    response_payload = client.get(
        url=f"/api/bot/{pytest.bot}/data/cognition?collection=Details",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual_payload = response_payload.json()
    assert actual_payload["success"]
    assert actual_payload["message"] is None
    assert actual_payload["error_code"] == 0
    assert actual_payload["data"]['rows'][0]['collection'] == 'details'
    assert actual_payload["data"]['rows'][0]['data'] == {'details': 'Nupur'}
    assert actual_payload["data"]['total'] == 1

    response_one = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json={
            "metadata": [
                {"column_name": "details_one", "data_type": "str", "enable_search": True, "create_embeddings": True}],
            "collection_name": "Details_one"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual_one = response_one.json()
    pytest.schema_id_one = actual_one["data"]["_id"]
    assert actual_one["message"] == "Schema saved!"
    assert actual_one["data"]["_id"]
    assert actual_one["error_code"] == 0

    response_two = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json={
            "metadata": [
                {"column_name": "details_two", "data_type": "str", "enable_search": True, "create_embeddings": True}],
            "collection_name": "Details_two"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual_two = response_two.json()

    pytest.schema_id_two = actual_two["data"]["_id"]
    assert actual_two["message"] == "Schema saved!"
    assert actual_two["data"]["_id"]
    assert actual_two["error_code"] == 0

    response_three = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json={
            "metadata": [
                {"column_name": "details_three", "data_type": "str", "enable_search": True, "create_embeddings": True}],
            "collection_name": "Details_three"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual_three = response_three.json()
    assert actual_three["message"] == "Collection limit exceeded!"
    assert not actual_three["data"]
    assert actual_three["error_code"] == 422

    response = client.delete(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema/{pytest.schema_id_one}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    response = client.delete(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema/{pytest.schema_id_two}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )

    response_four = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json={
            "metadata": [
                {"column_name": "details", "data_type": "str", "enable_search": True, "create_embeddings": True}],
            "collection_name": "Details"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual_four = response_four.json()
    assert not actual_four["success"]
    assert actual_four["message"] == "Collection already exists!"
    assert actual_four["data"] is None
    assert actual_four["error_code"] == 422


def test_metadata_upload_api_column_limit_exceeded():
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.cognition_columns_per_collection_limit = 5
    bot_settings.save()
    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json={
            "metadata": [
                {"column_name": "tech", "data_type": "str", "enable_search": True, "create_embeddings": True},
                {"column_name": "age", "data_type": "int", "enable_search": True, "create_embeddings": False},
                {"column_name": "color", "data_type": "str", "enable_search": True, "create_embeddings": True},
                {"column_name": "name", "data_type": "str", "enable_search": True, "create_embeddings": True},
                {"column_name": "gender", "data_type": "str", "enable_search": True, "create_embeddings": True},
                {"column_name": "experience", "data_type": "str", "enable_search": True, "create_embeddings": True}
            ],
            "collection_name": "test_metadata_upload_api_column_limit_exceeded"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["message"] == "Column limit exceeded for collection!"
    assert actual["data"] is None
    assert actual["error_code"] == 422


def test_metadata_upload_api_same_column_in_schema():
    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json={
            "metadata": [
                {"column_name": "tech", "data_type": "str", "enable_search": True, "create_embeddings": True},
                {"column_name": "ai", "data_type": "str", "enable_search": True, "create_embeddings": True},
                {"column_name": "ds", "data_type": "str", "enable_search": True, "create_embeddings": True},
                {"column_name": "tech", "data_type": "str", "enable_search": True, "create_embeddings": True}],
            "collection_name": "test_metadata_upload_api_same_column_in_schema"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["message"] == "Columns cannot be same in the schema!"
    assert actual["data"] is None
    assert actual["error_code"] == 422


def test_metadata_upload_invalid_data_type():
    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json={
            "metadata": [
                {"column_name": "test_metadata_upload_invalid_data_type", "data_type": "bool", "enable_search": True,
                 "create_embeddings": True}],
            "collection_name": "test_metadata_upload_invalid_data_type"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert actual["message"] == [{'loc': ['body', 'metadata', 0, 'data_type'],
                                  'msg': "value is not a valid enumeration member; permitted: 'str', 'int', 'float'",
                                  'type': 'type_error.enum', 'ctx': {'enum_values': ['str', 'int', 'float']}},
                                 {'loc': ['body', 'metadata', 0, '__root__'],
                                  'msg': 'Only str, int and float data types are supported', 'type': 'value_error'}]
    assert not actual["data"]
    assert actual["error_code"] == 422


def test_metadata_upload_column_name_empty():
    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json={
            "metadata": [
                {"column_name": "", "data_type": "int", "enable_search": True, "create_embeddings": True}],
            "collection_name": "test_metadata_upload_column_name_empty"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()

    assert actual["message"] == [
        {'loc': ['body', 'metadata', 0, '__root__'], 'msg': 'Column name cannot be empty', 'type': 'value_error'}]
    assert not actual["data"]
    assert actual["error_code"] == 422


def test_get_payload_metadata():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()

    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual['data'][0]['metadata'][0] == {'column_name': 'details', 'data_type': 'str', 'enable_search': True,
                                                'create_embeddings': True}
    assert actual['data'][0]['collection_name'] == 'details'


def test_delete_payload_content_metadata():
    response = client.delete(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema/{pytest.schema_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()

    assert actual["success"]
    assert actual["message"] == "Schema will be deleted soon!"
    assert actual["data"] is None
    assert actual["error_code"] == 0


def test_metadata_upload_api_and_delete_with_no_cognition_data(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(
            bot=pytest.bot,
            user="integration@demo.ai",
            llm_settings=LLMSettings(enable_faq=True),
        )

    monkeypatch.setattr(MongoProcessor, "get_bot_settings", _mock_get_bot_settings)
    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json={
            "metadata": [
                {"column_name": "country", "data_type": "str", "enable_search": True, "create_embeddings": True}],
            "collection_name": "Details"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()

    pytest.schema_id = actual["data"]["_id"]
    assert actual["message"] == "Schema saved!"
    assert actual["data"]["_id"]
    assert actual["error_code"] == 0

    response_one = client.delete(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema/{pytest.schema_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual_one = response_one.json()
    assert actual_one["success"]
    assert actual_one["message"] == "Schema will be deleted soon!"
    assert actual_one["data"] is None
    assert actual_one["error_code"] == 0


def test_delete_payload_content_metadata_does_not_exist():
    schema_id = '61f3a2c0aef98d5b4c58e90f'
    response = client.delete(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema/{schema_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["message"] == "Schema does not exists!"
    assert actual["data"] is None
    assert actual["error_code"] == 422


def test_get_payload_content_metadata_not_exists():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert actual["success"]
    assert actual["message"] is None
    assert actual["error_code"] == 0
    assert actual["data"] == []


def test_delete_schema_attached_to_prompt_action(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(bot=pytest.bot, user="integration@demo.ai", llm_settings=LLMSettings(enable_faq=True))

    monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)
    action = {'name': 'test_delete_schema_attached_to_prompt_action',
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
              "hyperparameters": Utility.get_default_llm_hyperparameters()}
    response_one = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json={
            "metadata": None,
            "collection_name": "python"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/action/prompt",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response_one.json()

    pytest.delete_schema_id = actual["data"]["_id"]

    response_two = client.delete(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema/{pytest.delete_schema_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual_two = response_two.json()

    assert not actual_two["success"]
    assert actual_two[
               "message"] == 'Cannot remove collection python linked to action "test_delete_schema_attached_to_prompt_action"!'
    assert actual_two["data"] is None
    assert actual_two["error_code"] == 422

    response_three = client.delete(
        f"/api/bot/{pytest.bot}/action/test_delete_schema_attached_to_prompt_action",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual_three = response_three.json()
    assert actual_three['message'] == 'Action deleted'

    response_four = client.delete(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema/{pytest.delete_schema_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual_four = response_four.json()
    assert actual_four['message'] == 'Schema will be deleted soon!'


def test_content_upload_api_with_gpt_feature_disabled():
    payload = {
        "data": "Data refers to any collection of facts, statistics, or information that can be analyzed or "
                "used to inform decision-making. Data can take many forms, including text, numbers, images, "
                "audio, and video.",
        "content_type": "text",
        "collection": "Data_details"}
    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert actual["message"] == "Faq feature is disabled for the bot! Please contact support."
    assert not actual["data"]
    assert actual["error_code"] == 422


def test_content_upload_api(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(bot=pytest.bot, user="integration@demo.ai", llm_settings=LLMSettings(enable_faq=True))

    monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)
    response_one = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json={
            "collection_name": "Details"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual_one = response_one.json()
    pytest.content_collection_id = actual_one["data"]["_id"]
    payload = {
        "data": "Data refers to any collection of facts, statistics, or information that can be analyzed or "
                "used to inform decision-making. Data can take many forms, including text, numbers, images, "
                "audio, and video.",
        "content_type": "text",
        "collection": "Details"}
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

    payload_two = {
        "data": "Data refers to any collection of facts, statistics, or information that can be analyzed.",
        "content_type": "text",
        "collection": "payload_two"}
    response_two = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition",
        json=payload_two,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response_two.json()
    assert actual["message"] == "Collection does not exist!"
    assert not actual["data"]
    assert actual["error_code"] == 422

    response_three = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json={
            "metadata": [
                {"column_name": "color", "data_type": "str", "enable_search": True, "create_embeddings": True}],
            "collection_name": "response_two"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    payload_three = {
        "data": "Data can take many forms, including text, numbers, images, audio, and video.",
        "content_type": "text",
        "collection": "response_two"}
    response_four = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition",
        json=payload_three,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response_four.json()
    assert actual["message"] == "Text content type does not have schema!"
    assert not actual["data"]
    assert actual["error_code"] == 422


def test_content_upload_api_invalid_atleast_ten_words(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(
            bot=pytest.bot,
            user="integration@demo.ai",
            llm_settings=LLMSettings(enable_faq=True),
        )

    monkeypatch.setattr(MongoProcessor, "get_bot_settings", _mock_get_bot_settings)
    payload = {
        "data": "Blockchain technology is an advanced"}
    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["message"] == "Content should contain atleast 10 words."
    assert not actual["success"]
    assert actual["data"] is None
    assert actual["error_code"] == 422


def test_content_upload_empty_data_text(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(bot=pytest.bot, user="integration@demo.ai", llm_settings=LLMSettings(enable_faq=True))

    monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)
    payload = {
        "data": "",
        "content_type": "text",
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["message"] == [{'loc': ['body', '__root__'], 'msg': 'data cannot be empty', 'type': 'value_error'}]


def test_content_upload_api_without_collection(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(bot=pytest.bot, user="integration@demo.ai", llm_settings=LLMSettings(enable_faq=True))

    monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)
    payload = {
        "data": "Blockchain technology is an advanced database mechanism that allows transparent information sharing within a business network."}
    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    pytest.content_id_no_collection = actual["data"]["_id"]
    assert actual["message"] == "Record saved!"
    assert actual["data"]["_id"]
    assert actual["error_code"] == 0


def test_content_update_api():
    response = client.put(
        url=f"/api/bot/{pytest.bot}/data/cognition/{pytest.content_id_text}",
        json={
            "row_id": pytest.content_id_text,
            "data": "AWS Fargate is a serverless compute engine for containers that allows you to run "
                    "Docker containers without having to manage the underlying EC2 instances. With Fargate, "
                    "you can focus on developing and deploying your applications rather than managing the infrastructure.",
            "collection": "Details",
            "content_type": "text"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["message"] == "Record updated!"
    assert actual["error_code"] == 0


def test_content_update_api_collection_does_not_exist():
    response = client.put(
        url=f"/api/bot/{pytest.bot}/data/cognition/{pytest.content_id_text}",
        json={
            "row_id": pytest.content_id_text,
            "data": "Docker containers without having to manage the underlying EC2 instances.",
            "collection": "test_content_update_api_collection_does_not_exist",
            "content_type": "text"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}

    )
    actual = response.json()
    assert not actual["success"]
    assert actual["message"] == "Collection does not exist!"
    assert actual["error_code"] == 422


def test_content_update_api_invalid():
    response = client.put(
        url=f"/api/bot/{pytest.bot}/data/cognition/{pytest.content_id_text}",
        json={
            "row_id": pytest.content_id_text,
            "data": "AWS Fargate is a serverless compute engine.",
            "collection": "Details",
            "content_type": "text"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["message"] == "Content should contain atleast 10 words."
    assert actual["data"] is None
    assert actual["error_code"] == 422


def test_content_update_api_already_exist():
    content_id = "6009cb85e65f6dce28fb3e51"
    response = client.put(
        url=f"/api/bot/{pytest.bot}/data/cognition/{content_id}",
        json={
            "row_id": content_id,
            "data": "AWS Fargate is a serverless compute engine for containers that allows you to run "
                    "Docker containers without having to manage the underlying EC2 instances. With Fargate, "
                    "you can focus on developing and deploying your applications rather than managing the infrastructure.",
            "collection": "Details",
            "content_type": "text"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["message"] == "Payload data already exists!"
    assert actual["data"] is None
    assert actual["error_code"] == 422


def test_content_update_api_id_not_found():
    content_id = "594ced02ed345b2b049222c5"
    response = client.put(
        url=f"/api/bot/{pytest.bot}/data/cognition/{content_id}",
        json={
            "row_id": content_id,
            "data": "Artificial intelligence (AI) involves using computers to do things that traditionally require human "
                    "intelligence. AI can process large amounts of data in ways that humans cannot. The goal for AI is "
                    "to be able to do things like recognize patterns, make decisions, and judge like humans.",
            "collection": "Details",
            "content_type": "text"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["message"] == "Payload with given id not found!"
    assert actual["data"] is None
    assert actual["error_code"] == 422


@mock.patch('kairon.shared.cognition.processor.CognitionDataProcessor.list_cognition_data', autospec=True)
@mock.patch('kairon.shared.cognition.processor.CognitionDataProcessor.get_cognition_data', autospec=True)
def test_list_cognition_data(mock_get_cognition_data, mock_list_cognition_data):
    cognition_data = [{'vector_id': 1,
                       'row_id': '65266ff16f0190ca4fd09898',
                       'data': 'AWS Fargate is a serverless compute engine for containers that allows you to run Docker containers without having to manage the underlying EC2 instances. With Fargate, you can focus on developing and deploying your applications rather than managing the infrastructure.',
                       'content_type': 'text',
                       'collection': 'aws', 'user': '"integration@demo.ai"', 'bot': pytest.bot}]
    row_count = 1

    def _list_cognition_data(*args, **kwargs):
        return cognition_data

    mock_list_cognition_data.return_value = _list_cognition_data()

    def _get_cognition_data(*args, **kwargs):
        return cognition_data, row_count

    mock_get_cognition_data.return_value = _get_cognition_data()

    filter_query = 'without having to manage'
    response = client.get(
        url=f"/api/bot/{pytest.bot}/data/cognition?data={filter_query}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]['rows'][0]['collection'] == 'aws'
    assert actual["data"]['total'] == 1


def test_get_content_without_data():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/data/cognition",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()

    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]['rows'][0]['collection'] == None
    assert actual["data"]['rows'][0][
               'data'] == 'Blockchain technology is an advanced database mechanism that allows transparent information sharing within a business network.'
    assert actual["data"]['total'] == 1


def test_delete_content():
    response_one = client.delete(
        url=f"/api/bot/{pytest.bot}/data/cognition/{pytest.content_id_no_collection}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual_one = response_one.json()
    assert actual_one["success"]
    assert actual_one["message"] == "Record deleted!"
    assert actual_one["data"] is None
    assert actual_one["error_code"] == 0

    response = client.delete(
        url=f"/api/bot/{pytest.bot}/data/cognition/{pytest.content_id_text}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert actual["success"]
    assert actual["message"] == "Record deleted!"
    assert actual["data"] is None
    assert actual["error_code"] == 0


def test_delete_content_does_not_exist():
    content_id = "635981f6e40f61599e000064"
    response = client.delete(
        url=f"/api/bot/{pytest.bot}/data/cognition/{content_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["message"] == "Payload does not exists!"
    assert actual["data"] is None
    assert actual["error_code"] == 422


def test_get_content_not_exists():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/data/cognition",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["success"]
    assert actual["message"] is None
    assert actual["error_code"] == 0
    assert actual["data"] == {'rows': [], 'total': 0}


def test_delete_payload_content_collection():
    response = client.delete(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema/{pytest.content_collection_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()

    assert actual["success"]
    assert actual["message"] == "Schema will be deleted soon!"
    assert actual["data"] is None
    assert actual["error_code"] == 0


def test_payload_upload_api_with_gpt_feature_disabled():
    payload = {
        "data": {"name": "Nupur", "age": 25, "city": "Bengaluru"},
        "content_type": "json"}
    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert (
            actual["message"]
            == "Faq feature is disabled for the bot! Please contact support."
    )
    assert not actual["data"]
    assert actual["error_code"] == 422


def test_payload_upload_api(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(
            bot=pytest.bot,
            user="integration@demo.ai",
            llm_settings=LLMSettings(enable_faq=True),
        )

    monkeypatch.setattr(MongoProcessor, "get_bot_settings", _mock_get_bot_settings)
    metadata = {
        "metadata": [{"column_name": "details", "data_type": "str", "enable_search": True, "create_embeddings": True}],
        "collection_name": "Details",
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json=metadata,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    payload = {
        "data": {"details": "AWS"},
        "content_type": "json",
        "collection": "Details"
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    pytest.payload_id = actual["data"]["_id"]
    assert actual["message"] == "Record saved!"
    assert actual["data"]["_id"]
    assert actual["error_code"] == 0


def test_payload_upload_collection_does_not_exists(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(
            bot=pytest.bot,
            user="integration@demo.ai",
            llm_settings=LLMSettings(enable_faq=True),
        )

    monkeypatch.setattr(MongoProcessor, "get_bot_settings", _mock_get_bot_settings)
    payload = {
        "data": {"name": "Ram", "age": 23, "color": "red"},
        "content_type": "json",
        "collection": "test_payload_upload_collection_does_not_exists"
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["message"] == 'Collection does not exist!'


def test_payload_upload_metadata_missing(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(bot=pytest.bot, user="integration@demo.ai", llm_settings=LLMSettings(enable_faq=True))

    monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)
    payload = {
        "data": {"city": "Pune", "color": "red"},
        "content_type": "json",
        "collection": "Details"
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["message"] == 'Columns do not exist in the schema!'


def test_payload_upload_metadata_invalid_data_type(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(bot=pytest.bot, user="integration@demo.ai", llm_settings=LLMSettings(enable_faq=True))

    monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)
    metadata = {
        "metadata": [{"column_name": "age", "data_type": "int", "enable_search": True, "create_embeddings": True}],
        "collection_name": "test_payload_upload_metadata_invalid_data_type"
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition/schema",
        json=metadata,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    payload = {
        "data": {"age": "Twenty-Three"},
        "content_type": "json",
        "collection": "test_payload_upload_metadata_invalid_data_type"
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["message"] == "Invalid data type for 'age': Expected integer value"


def test_payload_updated_api_collection_does_not_exists():
    response = client.put(
        url=f"/api/bot/{pytest.bot}/data/cognition/{pytest.payload_id}",
        json={
            "row_id": pytest.payload_id,
            "data": {"details": "data science"},
            "collection": "test_payload_updated_api_collection_does_not_exists",
            "content_type": "json"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}

    )
    actual = response.json()
    assert not actual["success"]
    assert actual["message"] == "Collection does not exist!"
    assert actual["error_code"] == 422


def test_payload_upload_json_data_content_type_text(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(bot=pytest.bot, user="integration@demo.ai", llm_settings=LLMSettings(enable_faq=True))

    monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)
    payload = {
        "data": {"age": 23},
        "content_type": "text",
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/data/cognition",
        json=payload,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["message"] == [
        {'loc': ['body', '__root__'], 'msg': 'content type and type of data do not match!', 'type': 'value_error'}]


def test_payload_updated_api():
    response = client.put(
        url=f"/api/bot/{pytest.bot}/data/cognition/{pytest.payload_id}",
        json={
            "row_id": pytest.payload_id,
            "data": {"details": "data science"},
            "collection": "Details",
            "content_type": "json"
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["message"] == "Record updated!"
    assert actual["error_code"] == 0


def test_payload_content_update_api_already_exists(monkeypatch):
    payload_id = "64b3b810efa74e8863544af3"

    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(
            bot=pytest.bot,
            user="integration@demo.ai",
            llm_settings=LLMSettings(enable_faq=True),
        )

    monkeypatch.setattr(MongoProcessor, "get_bot_settings", _mock_get_bot_settings)
    response = client.put(
        url=f"/api/bot/{pytest.bot}/data/cognition/{payload_id}",
        json={
            "row_id": payload_id,
            "data": {"details": "data science"},
            "content_type": "json",
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert not actual["success"]
    assert actual["message"] == "Payload data already exists!"
    assert actual["data"] is None
    assert actual["error_code"] == 422


def test_payload_content_update_api_id_not_found():
    payload_id = "594ced02ed345b2b049222c5"
    response = client.put(
        url=f"/api/bot/{pytest.bot}/data/cognition/{payload_id}",
        json={
            "row_id": payload_id,
            "data": {"details": "data"},
            "content_type": "json",
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}

    )
    actual = response.json()

    assert not actual["success"]
    assert actual["message"] == "Payload with given id not found!"
    assert actual["data"] is None
    assert actual["error_code"] == 422


def test_get_payload_content():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/data/cognition?collection=Details",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()

    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]['rows'][0]['data'] == {'details': 'data science'}
    assert actual["data"]['rows'][0]['collection'] == 'details'
    assert actual["data"]['total'] == 1


def test_delete_payload_content():
    response = client.delete(
        url=f"/api/bot/{pytest.bot}/data/cognition/{pytest.payload_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()

    assert actual["success"]
    assert actual["message"] == "Record deleted!"
    assert actual["data"] is None
    assert actual["error_code"] == 0


def test_delete_payload_content_does_not_exist():
    payload_id = "61f3a2c0aef88d5b4c58e90f"
    response = client.delete(
        url=f"/api/bot/{pytest.bot}/data/cognition/{payload_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["message"] == "Payload does not exists!"
    assert actual["data"] is None
    assert actual["error_code"] == 422


def test_get_payload_content_not_exists():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/data/cognition",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["message"] is None
    assert actual["error_code"] == 0
    assert actual["data"] == {"rows": [], "total": 0}
