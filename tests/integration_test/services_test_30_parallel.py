from tests.integration_test.services_support import *  # noqa: F403
from tests.integration_test.services_support import setup, fast_rasa_training



@responses.activate
def test_upload_invalid_csv():
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.data_importer_limit_per_day = 10
    bot_settings.save()
    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.faq_importer}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )
    csv_file = "Questions,Answer,\nWhat is Digite?, IT Company,\nHow are you?, I am good,\nWhat day is it?, It is Thursday,\n   ,  ,\nWhat day is it?, It is Thursday,\n".encode()
    csv_file = BytesIO(csv_file).read()
    files = {"csv_file": ("config.arff", csv_file)}
    response = client.post(
        f"/api/bot/{pytest.bot}/data/faq/upload",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=files,
    )
    actual = response.json()
    assert actual["data"] is None
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert (
            actual["message"] == "Invalid file type! Only csv and xlsx files are supported."
    )


@responses.activate
def test_upload_faq():
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.data_importer_limit_per_day = 10
    bot_settings.save()
    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.faq_importer}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )
    csv_file = "Questions,Answer,\nWhat is Digite?, IT Company,\nHow are you?, I am good,\nWhat day is it?, It is Thursday,\n   ,  ,\nWhat day is it?, It is Thursday,\n".encode()
    csv_file = BytesIO(csv_file).read()
    files = {"csv_file": ("config.csv", csv_file)}
    response = client.post(
        f"/api/bot/{pytest.bot}/data/faq/upload?overwrite=false",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=files,
    )
    actual = response.json()
    assert actual["message"] == "Upload in progress! Check logs."
    assert actual["data"] is None
    assert actual["success"]
    assert actual["error_code"] == 0


def test_download_faq(monkeypatch):
    data = [
        {
            "_id": "638dde37cfe8a7de324067fa",
            "story": "accelerator_28",
            "intent": "accelerator_28",
            "utterance": "utter_accelerator_28",
            "training_examples": [
                {
                    "text": "What is the purpose of an acceleration?",
                    "_id": "638dde36cfe8a7de32405eaa",
                },
                {
                    "text": "What is the purpose of an accelerators?",
                    "_id": "638dde36cfe8a7de32405eab",
                },
            ],
            "responses": [
                {
                    "_id": "638dde35cfe8a7de32405ada",
                    "text": {
                        "text": "•\tAnything that helps project teams reduce effort, save cost"
                    },
                }
            ],
        },
        {
            "_id": "638dde37cfe8a7de324067fd",
            "story": "accelerator_subscription_mainspring_31",
            "intent": "accelerator_subscription_mainspring_31",
            "utterance": "utter_accelerator_subscription_mainspring_31",
            "training_examples": [
                {
                    "text": "•\tHow do I subscribe to accelerators for my project?",
                    "_id": "638dde36cfe8a7de32405ec0",
                },
                {
                    "text": "•\tHow to do accelerator subscription in mainspring",
                    "_id": "638dde36cfe8a7de32405ec1",
                },
            ],
            "responses": [
                {
                    "_id": "638dde35cfe8a7de32405b64",
                    "custom": {
                        "custom": {
                            "data": [
                                {
                                    "type": "paragraph",
                                    "children": [
                                        {
                                            "text": "Step 1 : Navigate to PM Plan >> Delivery Assets"
                                        }
                                    ],
                                },
                                {
                                    "type": "paragraph",
                                    "children": [
                                        {
                                            "text": "Step 2 : Subscribe the accelerators which are applicable"
                                        }
                                    ],
                                },
                            ]
                        }
                    },
                }
            ],
        },
        {
            "_id": "638dde37cfe8a7de324067fe",
            "story": "accelerators_auto_recommended_32",
            "intent": "accelerators_auto_recommended_32",
            "utterance": "utter_accelerators_auto_recommended_32",
            "training_examples": [
                {
                    "text": "•\tOn what basis are accelerators recommended for a project?",
                    "_id": "638dde36cfe8a7de32405ec3",
                },
                {
                    "text": "•\tWhat is the criteria based on which accelerators are auto recommended ?",
                    "_id": "638dde36cfe8a7de32405ec4",
                },
            ],
            "responses": [
                {
                    "_id": "638dde35cfe8a7de32405b2d",
                    "text": {
                        "text": "•\tAccelerators are auto-recommended from Knowhub based on these project attributes"
                    },
                }
            ],
        },
    ]

    def __mock_qna(*args, **kwargs):
        for item in data:
            yield item

    monkeypatch.setattr(BaseQuerySet, "aggregate", __mock_qna)
    response = client.get(
        f"/api/bot/{pytest.bot}/data/faq/download",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    assert response.content


def test_add_prompt_action_with_stop_hyperparameters(monkeypatch):
    temp = Utility.get_default_llm_hyperparameters().copy()
    temp['stop'] = 'abc'
    temp['temperature'] = 1.0

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
        "name": "test_add_prompt_action_with_stop_hyperparameters", 'user_question': {'type': 'from_user_message'},
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
    assert actual["message"] == "Action Added Successfully"
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0

    from kairon.shared.actions.data_objects import PromptAction

    action = PromptAction.objects(bot=pytest.bot).get(id=actual["data"]["_id"])
    assert action.hyperparameters['stop'] == 'abc'
    assert action.hyperparameters['temperature'] == 1.0


def test_add_parallel_action_missing_existing_action(monkeypatch):
    script = "bot_response='hello world'"
    request_body = {
        "name": "pyscript_action",
        "source_code": script,
        "dispatch_response": False,
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/pyscript",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    print(actual)
    assert actual["error_code"] == 0
    assert actual["message"] == "Action added!"
    assert actual["success"]

    parallel_action_request_body = {
        "name": "parallel_action_test",
        "response_text": "Parallel Action Success",
        "dispatch_response_text": False,
        "actions": ["pyscript_action", "prompt_action"]
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/parallel",
        json=parallel_action_request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    print(actual)
    assert actual["error_code"] == 422
    assert actual["message"] == "Action with name prompt_action does not exist!"
    assert not actual["success"]
    Actions.objects(name="parallel_action_test").delete()
    Actions.objects(name="pyscript_action").delete()
    ParallelActionConfig.objects(name="parallel_action_test").delete()
    PyscriptActionConfig.objects(name="pyscript_action").delete()


def test_add_parallel_action_empty_actions_list(monkeypatch):

    parallel_action_request_body = {
        "name": "parallel_action_test",
        "response_text": "Parallel Action Success",
        "dispatch_response_text": False,
        "actions": []
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/parallel",
        json=parallel_action_request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"][0]['msg'] == "The 'actions' field must contain at least one action."
    assert actual["message"][0]['type'] == "value_error"
    assert not actual["success"]
    Actions.objects(name="parallel_action_test").delete()
    ParallelActionConfig.objects(name="parallel_action_test").delete()


def test_add_parallel_action_exceeds_max_actions(monkeypatch):
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.max_actions_per_parallel_action = 2
    bot_settings.save()

    parallel_action_request_body = {
        "name": "parallel_action_test",
        "response_text": "Parallel Action Success",
        "dispatch_response_text": False,
        "actions": ["pyscript_action","pyscript_action","pyscript_action"]
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/parallel",
        json=parallel_action_request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == f"Maximum {bot_settings.max_actions_per_parallel_action} actions are allowed in a parallel action."
    assert not actual["success"]

    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.max_actions_per_parallel_action = 5
    bot_settings.save()

    Actions.objects(name="parallel_action_test").delete()
    ParallelActionConfig.objects(name="parallel_action_test").delete()


def test_add_parallel_action_nested_parallel_action(monkeypatch):
    script = "bot_response='hello world'"
    request_body = {
        "name": "pyscript_action",
        "source_code": script,
        "dispatch_response": False,
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/pyscript",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"] == "Action added!"
    assert actual["success"]

    parallel_action_request_body = {
        "name": "parallel_action_test",
        "response_text": "Parallel Action Success",
        "dispatch_response_text": False,
        "actions": ["pyscript_action"]
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/parallel",
        json=parallel_action_request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"] == "Action added!"
    assert actual["success"]

    parallel_action_nested_request_body = {
        "name": "parallel_action_nested_test",
        "response_text": "Parallel Action Success",
        "dispatch_response_text": False,
        "actions": ["pyscript_action", "parallel_action_test"]
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/parallel",
        json=parallel_action_nested_request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"][0]['msg'] == "ParallelAction cannot include other parallel actions: ['parallel_action_test']"
    assert actual["message"][0]['type'] == "value_error"
    assert not actual["success"]
    Actions.objects(name="parallel_action_test").delete()
    Actions.objects(name="pyscript_action").delete()
    ParallelActionConfig.objects(name="parallel_action_test").delete()
    PyscriptActionConfig.objects(name="pyscript_action").delete()

def test_add_parallel_action(monkeypatch):
    script= "bot_response='hello world'"
    request_body = {
        "name": "pyscript_action",
        "source_code": script,
        "dispatch_response": False,
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/pyscript",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    print(actual)
    assert actual["error_code"] == 0
    assert actual["message"] == "Action added!"
    assert actual["success"]

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
        "name": "prompt_action", 'user_question': {'type': 'from_user_message'},
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

    parallel_action_request_body = {
        "name": "parallel_action_test",
        "response_text": "Parallel Action Success",
        "dispatch_response_text": False,
        "actions": ["pyscript_action", "prompt_action"]
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/parallel",
        json=parallel_action_request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    print(actual)
    assert actual["error_code"] == 0
    assert actual["message"] == "Action added!"
    assert actual["success"]


def test_update_parallel_action(monkeypatch):
    script = "bot_response='hello world'"
    request_body = {
        "name": "pyscript_action_2",
        "source_code": script,
        "dispatch_response": False,
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/pyscript",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"] == "Action added!"
    assert actual["success"]

    parallel_action_request_body = {
        "name": "parallel_action_test",
        "response_text": "Parallel Action Success",
        "dispatch_response_text": True,
        "actions": ["pyscript_action", "prompt_action", "pyscript_action_2"]
    }

    response = client.put(
        url=f"/api/bot/{pytest.bot}/action/parallel",
        json=parallel_action_request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    print(actual)
    assert actual["error_code"] == 0
    assert actual["message"] == "Action updated!"
    assert actual["success"]

    config = ParallelActionConfig.objects(name="parallel_action_test").first()
    assert config is not None

    config = config.to_mongo().to_dict()
    assert config["actions"] == ["pyscript_action", "prompt_action", "pyscript_action_2"]
    assert config["dispatch_response_text"] is True

def test_update_parallel_action_empty_action_list(monkeypatch):
    parallel_action_request_body = {
        "name": "parallel_action_test",
        "response_text": "Parallel Action Success",
        "dispatch_response_text": True,
        "actions": []
    }

    response = client.put(
        url=f"/api/bot/{pytest.bot}/action/parallel",
        json=parallel_action_request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"][0]['msg'] == "The 'actions' field must contain at least one action."
    assert actual["message"][0]['type'] == "value_error"
    assert not actual["success"]

def test_update_parallel_action_exceeds_max_actions(monkeypatch):
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.max_actions_per_parallel_action = 2
    bot_settings.save()

    parallel_action_request_body = {
        "name": "parallel_action_test",
        "response_text": "Parallel Action Success",
        "dispatch_response_text": True,
        "actions": ["pyscript_action","pyscript_action","pyscript_action"]
    }

    response = client.put(
        url=f"/api/bot/{pytest.bot}/action/parallel",
        json=parallel_action_request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == f"Maximum {bot_settings.max_actions_per_parallel_action} actions are allowed in a parallel action."
    assert not actual["success"]

    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.max_actions_per_parallel_action = 5
    bot_settings.save()

def test_delete_action_used_in_parallel_action():
    response = client.delete(
        f"/api/bot/{pytest.bot}/action/pyscript_action",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    print(actual)
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Action 'pyscript_action' cannot be deleted because it is used in parallel actions: ['parallel_action_test']"

def test_delete_parallel_action_not_exists():
    response = client.delete(
        f"/api/bot/{pytest.bot}/action/parallel_action_test_not_existing",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert (
            actual["message"]
            == 'Action with name "parallel_action_test_not_existing" not found'
    )

def test_delete_parallel_action():
    response = client.delete(
        f"/api/bot/{pytest.bot}/action/parallel_action_test",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action deleted"
    parallel_action_count = ParallelActionConfig.objects(bot = pytest.bot).count()
    assert parallel_action_count == 0
    Actions.objects(name__in=["pyscript_action", "pyscript_action_2", "prompt_action"]).delete()
    PyscriptActionConfig.objects(name__in=["pyscript_action", "pyscript_action_2"]).delete()
    PromptAction.objects(name="prompt_action").delete()


@responses.activate
def test_upload_with_parallel_action():
    ValidationLogs.objects(bot = pytest.bot).delete()
    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.data_importer}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )

    files = (
        (
            "training_files",
            ("nlu.yml", open("tests/testing_data/parallel_action/data/nlu.yml", "rb")),
        ),
        (
            "training_files",
            ("domain.yml", open("tests/testing_data/parallel_action/domain.yml", "rb")),
        ),
        (
            "training_files",
            ("stories.yml", open("tests/testing_data/parallel_action/data/stories.yml", "rb")),
        ),
        (
            "training_files",
            ("rules.yml", open("tests/testing_data/parallel_action/data/rules.yml", "rb")),
        ),
        (
            "training_files",
            ("multiflow_stories.yml", open("tests/testing_data/parallel_action/multiflow_stories.yml", "rb")),
        ),
        (
            "training_files",
            ("actions.yml", open("tests/testing_data/parallel_action/actions.yml", "rb")),
        ),
        (
            "training_files",
            ("config.yml", open("tests/testing_data/parallel_action/config.yml", "rb")),
        ),
        (
            "training_files",
            (
                "chat_client_config.yml",
                open("tests/testing_data/all/chat_client_config.yml", "rb"),
            ),
        ),
        (
            "training_files",
            (
                "bot_content.yml",
                open("tests/testing_data/all/bot_content.yml", "rb"),
            ),
        ),
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/upload?import_data=true&overwrite=true",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=files,
    )
    actual = response.json()
    assert actual["message"] == "Upload in progress! Check logs."
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]
    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.data_importer
    )

    Actions.objects(name__in=["api1", "api2", "py1", "py2", "parallel_action"]).delete()
    PyscriptActionConfig.objects(name__in=["py1", "py2"]).delete()
    HttpActionConfig.objects(action_name__in=["api1", "api2"]).delete()
    ParallelActionConfig.objects(name="parallel_action").delete()


def test_list_existing_actions_for_parallel_action():
    Actions.objects(bot=pytest.bot).delete()
    processor = MongoProcessor()
    user = "integration@demo.ai"
    action_1 = "http_action_1"
    action_2 = "email_action_1"
    action_3 = "jira_action_1"
    action_4 = "live_agent_action_1"
    action_5 = "parallel_action_1"

    processor.add_action(action_1, pytest.bot, user, action_type=ActionType.http_action)
    processor.add_action(action_2, pytest.bot, user, action_type=ActionType.email_action)
    processor.add_action(action_3, pytest.bot, user, action_type=ActionType.jira_action)
    processor.add_action(action_4, pytest.bot, user, action_type=ActionType.live_agent_action)
    processor.add_action(action_5, pytest.bot, user, action_type=ActionType.parallel_action)

    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/parallel/actions",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    print(actual)

    assert actual["success"] is True
    assert actual["error_code"] == 0
    assert actual["message"] is None

    assert len(actual["data"]) == 3
    expected_actions = {action_1: ActionType.http_action.value,
                        action_2: ActionType.email_action.value,
                        action_3: ActionType.jira_action.value}
    actual_actions = {action["name"]: action["type"] for action in actual["data"]}

    for name, action_type in expected_actions.items():
        assert name in actual_actions
        assert actual_actions[name] == action_type

    assert action_4 not in actual_actions
    assert action_5 not in actual_actions

    Actions.objects(name__in=[action_1, action_2, action_3, action_4, action_5], bot=pytest.bot).delete()
