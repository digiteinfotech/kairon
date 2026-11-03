from tests.integration_test.services_support import *  # noqa: F403
from tests.integration_test.services_support import setup, fast_rasa_training



@responses.activate
def test_augment_paraphrase_gpt():
    responses.add(
        responses.POST,
        url="http://localhost:8000/paraphrases/gpt",
        match=[
            responses.matchers.json_params_matcher(
                {
                    "api_key": "MockKey",
                    "data": ["Where is digite located?"],
                    "engine": "davinci",
                    "temperature": 0.75,
                    "max_tokens": 100,
                    "num_responses": 10,
                }
            )
        ],
        json={
            "success": True,
            "data": {
                "paraphrases": ["Where is digite located?", "Where is digite situated?"]
            },
            "message": None,
            "error_code": 0,
        },
        status=200,
    )
    response = client.post(
        "/api/augment/paraphrases/gpt",
        json={"data": ["Where is digite located?"], "api_key": "MockKey"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()

    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] == {
        "paraphrases": ["Where is digite located?", "Where is digite situated?"]
    }
    assert Utility.check_empty_string(actual["message"])


def test_augment_paraphrase_gpt_validation():
    response = client.post(
        "/api/augment/paraphrases/gpt",
        json={"data": [], "api_key": "MockKey"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"] == [
        {"loc": ["body", "data"], "msg": "Question Please!", "type": "value_error"}
    ]

    response = client.post(
        "/api/augment/paraphrases/gpt",
        json={
            "data": ["hi", "hello", "thanks", "hello", "bye", "how are you"],
            "api_key": "MockKey",
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"] == [
        {
            "loc": ["body", "data"],
            "msg": "Max 5 Questions are allowed!",
            "type": "value_error",
        }
    ]


@responses.activate
def test_augment_paraphrase_gpt_fail():
    key_error_message = "Incorrect API key provided: InvalidKey. You can find your API key at https://beta.openai.com."
    responses.add(
        responses.POST,
        url="http://localhost:8000/paraphrases/gpt",
        match=[
            responses.matchers.json_params_matcher(
                {
                    "api_key": "InvalidKey",
                    "data": ["Where is digite located?"],
                    "engine": "davinci",
                    "temperature": 0.75,
                    "max_tokens": 100,
                    "num_responses": 10,
                }
            )
        ],
        json={
            "success": False,
            "data": None,
            "message": key_error_message,
        },
        status=200,
    )
    response = client.post(
        "/api/augment/paraphrases/gpt",
        json={"data": ["Where is digite located?"], "api_key": "InvalidKey"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()

    assert not actual["success"]
    assert actual["data"] is None
    assert actual["message"] == key_error_message


@responses.activate
def test_augment_paraphrase():
    responses.add(
        responses.POST,
        "http://localhost:8000/paraphrases",
        json={
            "success": True,
            "data": {
                "questions": [
                    "Where is digite located?",
                    "Where is digite?",
                    "What is the location of digite?",
                    "Where is the digite located?",
                    "Where is it located?",
                    "What location is digite located?",
                    "Where is the digite?",
                    "where is digite located?",
                    "Where is digite situated?",
                    "digite is located where?",
                ]
            },
            "message": None,
            "error_code": 0,
        },
        status=200,
        match=[responses.matchers.json_params_matcher(["where is digite located?"])],
    )
    response = client.post(
        "/api/augment/paraphrases",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"data": ["where is digite located?"]},
    )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]
    assert Utility.check_empty_string(actual["message"])


def test_augment_paraphrase_no_of_questions():
    response = client.post(
        "/api/augment/paraphrases",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"data": []},
    )

    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"] == [
        {"loc": ["body", "data"], "msg": "Question Please!", "type": "value_error"}
    ]

    response = client.post(
        "/api/augment/paraphrases",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"data": ["Hi", "Hello", "How are you", "Bye", "Thanks", "Welcome"]},
    )

    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"] == [
        {
            "loc": ["body", "data"],
            "msg": "Max 5 Questions are allowed!",
            "type": "value_error",
        }
    ]


def test_get_user_details():
    response = client.get(
        "/api/user/details",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]
    assert Utility.check_empty_string(actual["message"])


def test_update_user_details():
    response = client.post(
        "/api/user/details/Completed",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()

    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Details updated!"

def test_get_user_settings():
    response = client.get(
        url="/api/user/user/settings",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()

    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]

    assert "user" in actual["data"]
    assert "default_bot" in actual["data"]
    assert "is_fav" in actual["data"]

    assert Utility.check_empty_string(actual["message"])

def test_update_user_settings():
    response = client.post(
        url="/api/user/user/settings",
        json={
            "data": {
                "default_bot": pytest.bot,
                "is_fav": [pytest.bot],
            }
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )

    actual = response.json()

    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]

    assert actual["data"]["default_bot"] == pytest.bot
    assert actual["data"]["is_fav"] == [pytest.bot]

def test_update_user_settings_without_is_fav():
    response = client.post(
        url="/api/user/user/settings",
        json={
            "data": {
                "default_bot": pytest.bot,
            }
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )

    actual = response.json()

    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]

def test_download_data():
    response = client.get(
        f"/api/bot/{pytest.bot}/download/data",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    file_bytes = BytesIO(response.content)
    zip_file = ZipFile(file_bytes, mode="r")
    assert zip_file.filelist.__len__() == 10
    zip_file.close()
    file_bytes.close()


def test_download_model():
    response = client.get(
        f"/api/bot/{pytest.bot}/download/model",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    d = response.headers["content-disposition"]
    fname = re.findall("filename=(.+)", d)[0]
    file_bytes = BytesIO(response.content)
    tar = tarfile.open(fileobj=file_bytes, mode="r", name=fname)
    assert tar.members.__len__()
    tar.close()
    file_bytes.close()


def test_get_endpoint():
    response = client.get(
        f"/api/bot/{pytest.bot}/endpoint",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["data"]
    assert actual["error_code"] == 0
    assert actual["message"] is None
    assert actual["success"]


def test_save_endpoint_error():
    response = client.put(
        f"/api/bot/{pytest.bot}/endpoint",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {"loc": ["body"], "msg": "field required", "type": "value_error.missing"}
    ]
    assert not actual["success"]


def test_save_empty_endpoint():
    response = client.put(
        f"/api/bot/{pytest.bot}/endpoint",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={},
    )

    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 0
    assert actual["message"] == "Endpoint saved successfully!"
    assert actual["success"]


def test_save_history_endpoint():
    response = client.put(
        f"/api/bot/{pytest.bot}/endpoint",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={
            "history_endpoint": {
                "url": "http://localhost:27019/",
                "token": "kairon-history-user",
            }
        },
    )

    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 0
    assert actual["message"] == "Endpoint saved successfully!"
    assert actual["success"]


@responses.activate
def test_save_endpoint(monkeypatch):
    monkeypatch.setitem(
        Utility.environment["model"]["agent"], "url", "http://localhost/"
    )

    responses.add(
        responses.GET,
        f"http://localhost/api/bot/{pytest.bot}/reload",
        status=200,
        json={
            "success": True,
            "error_code": 0,
            "data": None,
            "message": "Reloading Model!",
        },
    )

    response = client.put(
        f"/api/bot/{pytest.bot}/endpoint",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={
            "bot_endpoint": {"url": "http://localhost:5005/"},
            "action_endpoint": {"url": "http://localhost:5000/"},
            "history_endpoint": {"url": "http://localhost", "token": "rasa234568"},
        },
    )

    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 0
    assert actual["message"] == "Endpoint saved successfully!"
    assert actual["success"]
    response = client.get(
        f"/api/bot/{pytest.bot}/endpoint",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["data"]["endpoint"].get("bot_endpoint")
    assert actual["data"]["endpoint"].get("action_endpoint")
    assert actual["data"]["endpoint"].get("history_endpoint")


def test_save_empty_history_endpoint():
    response = client.put(
        f"/api/bot/{pytest.bot}/endpoint",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"history_endpoint": {"url": " ", "token": "testing-endpoint"}},
    )

    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 422
    assert actual["message"] == "url cannot be blank or empty spaces"
    assert not actual["success"]


def test_get_history_endpoint():
    response = client.get(
        f"/api/bot/{pytest.bot}/endpoint",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["data"]["endpoint"]["history_endpoint"]["url"] == "http://localhost"
    assert actual["data"]["endpoint"]["history_endpoint"]["token"] == "rasa234***"
    assert actual["error_code"] == 0
    assert actual["message"] is None
    assert actual["success"]


def test_delete_endpoint():
    response = client.delete(
        f"/api/bot/{pytest.bot}/endpoint/history_endpoint",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 0
    assert actual["message"] == "Endpoint removed"
    assert actual["success"]


def test_get_templates():
    response = client.get(
        f"/api/system/templates/use-case",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert "Hi-Hello" in actual["data"]["use-cases"]
    assert actual["error_code"] == 0
    assert actual["message"] is None
    assert actual["success"]


def test_set_templates():
    response = client.post(
        f"/api/bot/{pytest.bot}/templates/use-case",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"data": "Hi-Hello"},
    )

    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 0
    assert actual["message"] == "Data applied!"
    assert actual["success"]


def test_set_templates_invalid():
    response = client.post(
        f"/api/bot/{pytest.bot}/templates/use-case",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"data": "Hi"},
    )

    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 422
    assert actual["message"] == "Invalid template!"
    assert not actual["success"]


def test_set_templates_insecure():
    response = client.post(
        f"/api/bot/{pytest.bot}/templates/use-case",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"data": "../Hi-Hello"},
    )

    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 0
    assert actual["message"] == "Data applied!"
    assert actual["success"]


@responses.activate
def test_reload_model(monkeypatch):
    processor = MongoProcessor()
    start_time = utc_now() - timedelta(days=1)
    end_time = utc_now() + timedelta(days=1)

    monkeypatch.setitem(
        Utility.environment["model"]["agent"], "url", "http://localhost/"
    )

    responses.add(
        responses.GET,
        f"http://localhost/api/bot/{pytest.bot}/reload",
        status=200,
        json={
            "success": True,
            "error_code": 0,
            "data": None,
            "message": "Reloading Model!",
        },
    )

    response = client.get(
        f"/api/bot/{pytest.bot}/model/reload",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 0
    assert actual["message"] == "Reloading Model!"
    assert actual["success"]
    logs = processor.get_logs(pytest.bot, "audit_logs", start_time, end_time)
    logs[0].pop('timestamp')
    logs[0].pop('_id')
    assert logs[0] == {'attributes': [{'key': 'bot', 'value': pytest.bot}], 'user': 'integration@demo.ai',
                       'action': 'activity', 'entity': 'model_reload',
                       'data': {'message': None, 'username': 'integration@demo.ai', 'exception': None,
                                'status': 'Initiated'}}


@responses.activate
def test_reload_model_exception():
    processor = MongoProcessor()
    start_time = utc_now() - timedelta(days=1)
    end_time = utc_now() + timedelta(days=1)
    # def mongo_store(*arge, **kwargs):
    #     return None
    #
    # monkeypatch.setattr(Utility, "get_local_mongo_store", mongo_store)
    # monkeypatch.setitem(Utility.environment['action'], "url", None)
    # monkeypatch.setitem(Utility.environment['model']['agent'], "url", "http://localhost/")
    response = client.get(
        f"/api/bot/{pytest.bot}/model/reload",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token}
    )
    actual = response.json()
    assert actual['data'] is None
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual['message'] == 'Agent config not found!'
    logs = processor.get_logs(pytest.bot, "audit_logs", start_time, end_time)
    logs[0].pop('timestamp')
    logs[0].pop('_id')
    assert logs[0] == {'attributes': [{'key': 'bot', 'value': pytest.bot}],
                       'user': 'integration@demo.ai', 'action': 'activity', 'entity': 'model_reload',
                       'data': {'message': None, 'username': 'integration@demo.ai',
                                'exception': 'Agent config not found!', 'status': 'Failed'}}


def test_get_config_templates():
    response = client.get(
        f"/api/bot/{pytest.bot}/templates/config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    templates = {template["name"] for template in actual["data"]["config-templates"]}
    assert templates == {
        "long-answer",
        "rasa-default",
        "contextual",
        "kairon-default",
        "gpt-faq",
        "openai-classifier",
        "openai-featurizer",
        "jev-classifier",
    }
    assert actual["error_code"] == 0
    assert actual["message"] is None
    assert actual["success"]


def test_set_config_templates():
    response = client.post(
        f"/api/bot/{pytest.bot}/templates/config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"data": "rasa-default"},
    )

    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 0
    assert actual["message"] == "Config applied!"
    assert actual["success"]


def test_set_config_templates_invalid():
    response = client.post(
        f"/api/bot/{pytest.bot}/templates/config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"data": "test"},
    )

    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 422
    assert actual["message"] == "Invalid config!"
    assert not actual["success"]


def test_set_config_templates_insecure():
    response = client.post(
        f"/api/bot/{pytest.bot}/templates/config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"data": "../rasa-default"},
    )

    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 0
    assert actual["message"] == "Config applied!"
    assert actual["success"]


def test_get_config():
    response = client.get(
        f"/api/bot/{pytest.bot}/config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert all(
        key in ["language", "pipeline", "policies", "recipe"]
        for key in actual["data"]["config"].keys()
    )
    assert actual["error_code"] == 0
    assert actual["message"] is None
    assert actual["success"]


def test_set_config():
    response = client.put(
        f"/api/bot/{pytest.bot}/config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=read_config_file("./tests/testing_data/kairon-default.yml"),
    )

    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 0
    assert actual["message"] == "Config saved!"
    assert actual["success"]


def test_set_config_policy_error():
    data = read_config_file("./tests/testing_data/kairon-default.yml")
    data["policies"].append({"name": "TestPolicy"})
    response = client.put(
        f"/api/bot/{pytest.bot}/config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=data,
    )

    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 422
    assert actual["message"] == "Invalid policy TestPolicy"
    assert not actual["success"]


def test_set_config_pipeline_error():
    data = read_config_file("./tests/testing_data/kairon-default.yml")
    data["pipeline"].append({"name": "TestFeaturizer"})
    response = client.put(
        f"/api/bot/{pytest.bot}/config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=data,
    )

    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 422
    assert str(actual["message"]).__contains__("Invalid component TestFeaturizer")
    assert not actual["success"]


def test_set_config_pipeline_error_empty_policies():
    data = read_config_file("./tests/testing_data/kairon-default.yml")
    data["policies"] = []
    response = client.put(
        f"/api/bot/{pytest.bot}/config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=data,
    )

    actual = response.json()
    assert actual["data"] is None
    assert str(actual["message"]).__contains__("You didn't define any policies")
    assert actual["error_code"] == 422
    assert not actual["success"]
