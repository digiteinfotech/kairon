from tests.integration_test.services_support import *  # noqa: F403
from tests.integration_test.services_support import setup, fast_rasa_training


@responses.activate
def test_upload_with_bot_content_only_validate_content_data():
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.data_importer_limit_per_day = 10
    bot_settings.llm_settings['enable_faq'] = True
    bot_settings.save()

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

    response = client.get(
        f"/api/bot/{pytest.bot}/importer/logs?start_idx=0&page_size=10",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["logs"][0]["event_status"] == EVENT_STATUS.COMPLETED.value
    assert set(actual["data"]["logs"][0]["files_received"]) == {"bot_content"}
    assert actual["data"]["logs"][0]["is_data_uploaded"]
    assert actual["data"]["logs"][0]["start_timestamp"]
    assert actual["data"]["logs"][0]["end_timestamp"]

    response = client.get(
        f"/api/bot/{pytest.bot}/data/cognition",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["success"]
    assert actual["error_code"] == 0
    assert "data" in actual
    assert "rows" in actual["data"]
    assert len(actual["data"]["rows"]) == 3
    assert all(row["content_type"] == "text" for row in actual["data"]["rows"])
    assert actual["data"]["rows"][0]["data"] == "I am testing upload download bot content in Default Collection 3"
    assert all(row["collection"] is None for row in actual["data"]["rows"])

    CognitionData.objects(bot=pytest.bot).delete()
    CognitionSchema.objects(bot=pytest.bot).delete()

    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.llm_settings['enable_faq'] = False
    bot_settings.save()


@responses.activate
def test_upload_with_bot_content_valifdate_payload_data():
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.data_importer_limit_per_day = 10
    bot_settings.llm_settings['enable_faq'] = True
    bot_settings.save()

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
            ("nlu.yml", open("template/use-cases/Hi-Hello/data/nlu.yml", "rb")),
        ),
        (
            "training_files",
            ("domain.yml", open("template/use-cases/Hi-Hello/domain.yml", "rb")),
        ),
        (
            "training_files",
            ("stories.yml", open("template/use-cases/Hi-Hello/data/stories.yml", "rb")),
        ),
        (
            "training_files",
            ("config.yml", open("template/use-cases/Hi-Hello/config.yml", "rb")),
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

    response = client.get(
        f"/api/bot/{pytest.bot}/importer/logs?start_idx=0&page_size=10",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    response = client.get(
        f"/api/bot/{pytest.bot}/logs/importer?start_idx=0&page_size=10",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["logs"][0]["event_status"] == EVENT_STATUS.COMPLETED.value
    assert actual["data"]["logs"][0]["is_data_uploaded"]
    assert actual["data"]["logs"][0]["start_timestamp"]
    assert actual["data"]["logs"][0]["end_timestamp"]

    print(actual)
    from_date = date.today()
    to_date = from_date + timedelta(days=1)

    search_response = client.get(
        f"/api/bot/{pytest.bot}/logs/importer/search?from_date={from_date}&to_date={to_date}&status=Success",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    response_json = search_response.json()
    print("importer:", response_json)
    assert response_json["success"] is True
    assert response_json["error_code"] == 0

    data = response_json["data"]
    assert "logs" in data
    assert isinstance(data["logs"], list)
    assert data['total'] == 2

    response = client.get(
        f"/api/bot/{pytest.bot}/data/cognition",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        params={"collection": "test_payload_collection"}

    )
    actual = response.json()

    assert actual["success"]
    assert actual["error_code"] == 0
    assert "data" in actual
    assert "rows" in actual["data"]
    assert len(actual["data"]["rows"]) == 3
    assert all(row["content_type"] == "json" for row in actual["data"]["rows"])
    assert actual["data"]["rows"][0]["data"]["city"] == "City 3"
    assert actual["data"]["rows"][1]["data"]["population"] == 200
    assert all(row["collection"] == "test_payload_collection" for row in actual["data"]["rows"])

    CognitionData.objects(bot=pytest.bot).delete()
    CognitionSchema.objects(bot=pytest.bot).delete()

    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.llm_settings['enable_faq'] = False
    bot_settings.save()


@responses.activate
def test_upload_with_bot_content_using_event_append_validate_content_data():
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.data_importer_limit_per_day = 10
    bot_settings.llm_settings['enable_faq'] = True
    bot_settings.save()

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
            ("nlu.yml", open("template/use-cases/Hi-Hello/data/nlu.yml", "rb")),
        ),
        (
            "training_files",
            ("domain.yml", open("template/use-cases/Hi-Hello/domain.yml", "rb")),
        ),
        (
            "training_files",
            ("stories.yml", open("template/use-cases/Hi-Hello/data/stories.yml", "rb")),
        ),
        (
            "training_files",
            ("config.yml", open("template/use-cases/Hi-Hello/config.yml", "rb")),
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
    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.data_importer
    )

    response = client.post(
        f"/api/bot/{pytest.bot}/upload?import_data=true&overwrite=false",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=files,
    )

    actual = response.json()
    assert actual["message"] == "Upload in progress! Check logs."
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]

    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.data_importer, overwrite=False
    )

    response = client.get(
        f"/api/bot/{pytest.bot}/importer/logs?start_idx=0&page_size=10",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["logs"][0]["event_status"] == EVENT_STATUS.COMPLETED.value
    assert actual["data"]["logs"][0]["is_data_uploaded"]
    assert actual["data"]["logs"][0]["start_timestamp"]
    assert actual["data"]["logs"][0]["end_timestamp"]

    response = client.get(
        f"/api/bot/{pytest.bot}/data/cognition",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        params={"collection": "test_content_collection"}
    )
    actual = response.json()

    assert actual["success"]
    assert actual["error_code"] == 0
    assert "data" in actual
    assert "rows" in actual["data"]
    assert len(actual["data"]["rows"]) == 4
    assert all(row["content_type"] == "text" for row in actual["data"]["rows"])
    assert actual["data"]["rows"][2]["data"] == "I am testing upload download bot content in Content Collection 2"
    assert all(row["collection"] == "test_content_collection" for row in actual["data"]["rows"])

    CognitionData.objects(bot=pytest.bot).delete()
    CognitionSchema.objects(bot=pytest.bot).delete()

    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.llm_settings['enable_faq'] = False
    bot_settings.save()


@responses.activate
def test_upload_with_bot_content_event_append_validate_payload_data():
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.data_importer_limit_per_day = 10
    bot_settings.llm_settings['enable_faq'] = True
    bot_settings.save()

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
            ("nlu.yml", open("template/use-cases/Hi-Hello/data/nlu.yml", "rb")),
        ),
        (
            "training_files",
            ("domain.yml", open("template/use-cases/Hi-Hello/domain.yml", "rb")),
        ),
        (
            "training_files",
            ("stories.yml", open("template/use-cases/Hi-Hello/data/stories.yml", "rb")),
        ),
        (
            "training_files",
            ("config.yml", open("template/use-cases/Hi-Hello/config.yml", "rb")),
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
    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.data_importer
    )

    response = client.post(
        f"/api/bot/{pytest.bot}/upload?import_data=true&overwrite=false",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=files,
    )
    actual = response.json()
    assert actual["message"] == "Upload in progress! Check logs."
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]

    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.data_importer, overwrite=False
    )

    response = client.get(
        f"/api/bot/{pytest.bot}/importer/logs?start_idx=0&page_size=10",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["logs"][0]["event_status"] == EVENT_STATUS.COMPLETED.value
    assert actual["data"]["logs"][0]["is_data_uploaded"]
    assert actual["data"]["logs"][0]["start_timestamp"]
    assert actual["data"]["logs"][0]["end_timestamp"]

    response = client.get(
        f"/api/bot/{pytest.bot}/data/cognition",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        params={"collection": "test_payload_collection"}
    )
    actual = response.json()

    assert actual["success"]
    assert actual["error_code"] == 0
    assert "data" in actual
    assert "rows" in actual["data"]
    assert len(actual["data"]["rows"]) == 6
    assert all(row["content_type"] == "json" for row in actual["data"]["rows"])
    assert actual["data"]["rows"][4]["data"]["city"] == "City 2"
    assert actual["data"]["rows"][1]["data"]["population"] == 200
    assert all(row["collection"] == "test_payload_collection" for row in actual["data"]["rows"])

    CognitionData.objects(bot=pytest.bot).delete()
    CognitionSchema.objects(bot=pytest.bot).delete()

    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.llm_settings['enable_faq'] = False
    bot_settings.save()

@pytest.fixture()
def get_executor_logs():
    from kairon.events.executors.base import ExecutorBase
    executor = ExecutorBase()
    executor.log_task(event_class=EventClass.model_training.value, task_type=TASK_TYPE.EVENT.value,
                      data=[{"name": "BOT", "value": pytest.bot}, {"name": "USER", "value": "test_user"}],
                      executor_log_id=ObjectId().__str__(), status=EVENT_STATUS.INITIATED.value,
                      from_executor=True)
    executor.log_task(event_class=EventClass.model_testing.value, task_type=TASK_TYPE.EVENT.value,
                      data=[{"name": "BOT", "value": pytest.bot}, {"name": "USER", "value": "test_user"}],
                      executor_log_id=ObjectId().__str__(), status=EVENT_STATUS.INITIATED.value,
                      from_executor=True)
    executor.log_task(event_class=EventClass.scheduler_evaluator.value, task_type=TASK_TYPE.ACTION.value,
                      data=[
                          {
                              "name": "SOURCE_CODE",
                              "value": "import requests\n\nurl=\"https://waba-v2.360dialog.io/messages\"\n\nheaders={'Content-Type': 'application/json', 'D360-API-KEY' : '6aYs394839849384rkU6Bs39R3RAK'}\n\ncontacts = ['919657099999','918210099999']\ncontacts = [\"919515999999\"]\nbody = {\n    \"messaging_product\": \"whatsapp\",\n    \"recipient_type\": \"individual\",\n    \"to\": \"9199991685\",\n    \"type\": \"template\",\n    \"template\": {\n        \"namespace\": \"54500467_f322_4595_becd_41555889bfd8\",\n        \"language\": {\n            \"policy\": \"deterministic\",\n            \"code\": \"en\"\n        },\n        \"name\": \"schedule_action_test\"\n    }\n}\n\nfor contact in contacts:\n  body[\"to\"] = contact\n  resp = requests.post(url, headers=headers, data=json.dumps(body))\n  resp = resp.json()\n  print(resp[\"messages\"])\n\nbot_response = 'this from callback pyscript'"
                          },
                          {
                              "name": "PREDEFINED_OBJECTS",
                              "value": {
                                  "val1": "rajan",
                                  "val2": "hitesh",
                                  "passwd": None,
                                  "myuser": "mahesh.sattala@digite.com",
                                  "bot": pytest.bot,
                                  "event": "01928ec7f495717b842dfdjfkdc65a161e3"
                              }
                          }
                      ],
                      executor_log_id=ObjectId().__str__(), status=EVENT_STATUS.FAIL.value,
                      exception="An error occurred (UnrecognizedClientException) when calling the Invoke operation: The security token included in the request is invalid.")
    executor.log_task(event_class=EventClass.pyscript_evaluator.value, task_type=TASK_TYPE.ACTION.value,
                      data={
                          "source_code": "bot_response = \"Test\"",
                          "predefined_objects": {
                              "sender_id": "mahesh.sattala@digite.com",
                              "user_message": "/pyscript",
                              "slot": {
                                  "calbkslot1": None,
                                  "calbkslot2": None,
                                  "quick_reply": None,
                                  "latitude": None,
                                  "longitude": None,
                                  "doc_url": None,
                                  "document": None,
                                  "video": None,
                                  "audio": None,
                                  "image": None,
                                  "http_status_code": None,
                                  "flow_reply": None,
                                  "order": None,
                                  "bot": pytest.bot,
                                  "kairon_action_response": "Test",
                                  "session_started_metadata": {
                                      "tabname": "default",
                                      "displayLabel": "",
                                      "telemetry-uid": "None",
                                      "telemetry-sid": "None",
                                      "is_integration_user": False,
                                      "bot": pytest.bot,
                                      "account": 8,
                                      "channel_type": "chat_client"
                                  }
                              },
                              "intent": "pyscript",
                              "chat_log": [
                                  {
                                      "user": "hi"
                                  },
                                  {
                                      "bot": {
                                          "text": "Let me be your AI Assistant and provide you with service",
                                          "elements": None,
                                          "quick_replies": None,
                                          "buttons": None,
                                          "attachment": None,
                                          "image": None,
                                          "custom": None
                                      }
                                  },
                                  {
                                      "user": "trigger callback"
                                  },
                                  {
                                      "bot": {
                                          "text": "callbk triggered",
                                          "elements": None,
                                          "quick_replies": None,
                                          "buttons": None,
                                          "attachment": None,
                                          "image": None,
                                          "custom": None
                                      }
                                  },
                                  {
                                      "user": "/pyscript"
                                  }
                              ],
                              "key_vault": {},
                              "latest_message": {
                                  "intent": {
                                      "name": "pyscript",
                                      "confidence": 1
                                  },
                                  "entities": [],
                                  "text": "/pyscript",
                                  "message_id": "ee57dde3c007448eb257d6b5e20c30ac",
                                  "metadata": {
                                      "tabname": "default",
                                      "displayLabel": "",
                                      "telemetry-uid": "None",
                                      "telemetry-sid": "None",
                                      "is_integration_user": False,
                                      "bot": pytest.bot,
                                      "account": 8,
                                      "channel_type": "chat_client"
                                  },
                                  "intent_ranking": [
                                      {
                                          "name": "pyscript",
                                          "confidence": 1
                                      }
                                  ]
                              },
                              "kairon_user_msg": None,
                              "session_started": None
                          }
                      },
                      executor_log_id=ObjectId().__str__(), status=EVENT_STATUS.INITIATED.value)
    executor.log_task(event_class=EventClass.pyscript_evaluator.value, task_type=TASK_TYPE.CALLBACK.value,
                      data={
                          "source_code": "bot_response = \"test - this is from callback test\"",
                          "predefined_objects": {
                              "req": {
                                  "type": "GET",
                                  "body": None,
                                  "params": {}
                              },
                              "req_host": "127.0.0.1",
                              "action_name": "clbk1",
                              "callback_name": "test",
                              "bot": pytest.bot,
                              "sender_id": "mahesh.sattala@digite.com",
                              "channel": "unsupported (None)",
                              "metadata": {
                                  "first_name": "rajan",
                                  "bot": pytest.bot
                              },
                              "identifier": "01928eb52813799e81c56803ecf39e6e",
                              "callback_url": "http://localhost:5059/callback/d/01928eb52813799e81c56803ecf39e6e/98bxWAMY9HF40La5AKQjEb-0JqaDTKX_Mmmmmmmmmmm",
                              "execution_mode": "async",
                              "state": 0,
                              "is_valid": True
                          }
                      },
                      executor_log_id=ObjectId().__str__(), status=EVENT_STATUS.COMPLETED.value,
                      response={
                          "ResponseMetadata": {
                              "RequestId": "0da1cdd1-1702-473b-8109-67a39f990835",
                              "HTTPStatusCode": 200,
                              "HTTPHeaders": {
                                  "date": "Tue, 15 Oct 2024 07:38:01 GMT",
                                  "content-type": "application/json",
                                  "content-length": "740",
                                  "connection": "keep-alive",
                                  "x-amzn-requestid": "0da1cdd1-1702-473b-8109-67a39f9sdlksldksl",
                                  "x-amzn-remapped-content-length": "0",
                                  "x-amz-executed-version": "$LATEST",
                                  "x-amz-log-result": "sdskjdksjdkjskdjskjdksj",
                                  "x-amzn-trace-id": "Root=1-670e1bd6-25e7667c7c6ce37f09a9afc7;Sampled=1;Lineage=1:d072fc6c:0"
                              },
                              "RetryAttempts": 0
                          },
                          "StatusCode": 200,
                          "LogResult": "sldklskdlskdlskdlk",
                          "ExecutedVersion": "$LATEST",
                          "Payload": {
                              "statusCode": 200,
                              "statusDescription": "200 OK",
                              "isBase64Encoded": False,
                              "headers": {
                                  "Content-Type": "text/html; charset=utf-8"
                              },
                              "body": {
                                  "req": {
                                      "type": "GET",
                                      "body": None,
                                      "params": {}
                                  },
                                  "req_host": "127.0.0.1",
                                  "action_name": "clbk1",
                                  "callback_name": "test",
                                  "bot": pytest.bot,
                                  "sender_id": "mahesh.sattala@digite.com",
                                  "channel": "unsupported (None)",
                                  "metadata": {
                                      "first_name": "rajan",
                                      "bot": pytest.bot
                                  },
                                  "identifier": "01928eb52813799e81c56803ecf39e6e",
                                  "callback_url": "http://localhost:5059/callback/d/01928eb52813799e81c56803ecf39e6e/98bxWAMY9HF40La5AKQjEb-0JqaDTKX_Mmmmmmmmmmm",
                                  "execution_mode": "async",
                                  "state": 0,
                                  "is_valid": True,
                                  "bot_response": "test - this is from callback test"
                              }
                          }
                      }
                      )

def test_get_executor_logs(get_executor_logs):
    response = client.get(
        url=f"/api/bot/{pytest.bot}/executor/logs?task_type=Callback",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    response = client.get(
        url=f"/api/bot/{pytest.bot}/logs/executor?task_type=Callback",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert not actual["message"]
    assert actual["success"]
    assert len(actual["data"]["logs"]) == actual["data"]["total"] == 1
    assert actual["data"]["logs"][0]["task_type"] == "Callback"
    assert actual["data"]["logs"][0]["event_class"] == "pyscript_evaluator"
    assert actual["data"]["logs"][0]["status"] == EVENT_STATUS.COMPLETED.value
    assert actual["data"]["logs"][0]["data"] == {
        'predefined_objects': {
            'req': {'type': 'GET', 'body': None, 'params': {}},
            'req_host': '127.0.0.1', 'action_name': 'clbk1',
            'callback_name': 'test', 'bot': pytest.bot,
            'sender_id': 'mahesh.sattala@digite.com',
            'channel': 'unsupported (None)',
            'metadata': {'first_name': 'rajan',
                         'bot': pytest.bot},
            'identifier': '01928eb52813799e81c56803ecf39e6e',
            'callback_url': 'http://localhost:5059/callback/d/01928eb52813799e81c56803ecf39e6e/98bxWAMY9HF40La5AKQjEb-0JqaDTKX_Mmmmmmmmmmm',
            'execution_mode': 'async', 'state': 0, 'is_valid': True}
    }
    assert actual["data"]["logs"][0]["response"] == {
        'ResponseMetadata': {'RequestId': '0da1cdd1-1702-473b-8109-67a39f990835', 'HTTPStatusCode': 200,
                             'HTTPHeaders': {'date': 'Tue, 15 Oct 2024 07:38:01 GMT',
                                             'content-type': 'application/json', 'content-length': '740',
                                             'connection': 'keep-alive',
                                             'x-amzn-requestid': '0da1cdd1-1702-473b-8109-67a39f9sdlksldksl',
                                             'x-amzn-remapped-content-length': '0', 'x-amz-executed-version': '$LATEST',
                                             'x-amz-log-result': 'sdskjdksjdkjskdjskjdksj',
                                             'x-amzn-trace-id': 'Root=1-670e1bd6-25e7667c7c6ce37f09a9afc7;Sampled=1;Lineage=1:d072fc6c:0'},
                             'RetryAttempts': 0}, 'StatusCode': 200, 'LogResult': 'sldklskdlskdlskdlk',
        'ExecutedVersion': '$LATEST',
        'Payload': {'statusCode': 200, 'statusDescription': '200 OK', 'isBase64Encoded': False,
                    'headers': {'Content-Type': 'text/html; charset=utf-8'},
                    'body': {'req': {'type': 'GET', 'body': None, 'params': {}}, 'req_host': '127.0.0.1',
                             'action_name': 'clbk1', 'callback_name': 'test', 'bot': pytest.bot,
                             'sender_id': 'mahesh.sattala@digite.com', 'channel': 'unsupported (None)',
                             'metadata': {'first_name': 'rajan', 'bot': pytest.bot},
                             'identifier': '01928eb52813799e81c56803ecf39e6e',
                             'callback_url': 'http://localhost:5059/callback/d/01928eb52813799e81c56803ecf39e6e/98bxWAMY9HF40La5AKQjEb-0JqaDTKX_Mmmmmmmmmmm',
                             'execution_mode': 'async', 'state': 0, 'is_valid': True,
                             'bot_response': 'test - this is from callback test'}}}
    assert actual["data"]["logs"][0]["executor_log_id"]
    assert actual["data"]["logs"][0]['bot'] == pytest.bot

    response = client.get(
        url=f"/api/bot/{pytest.bot}/executor/logs?task_type=Event",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert not actual["message"]
    assert actual["success"]
    print(actual["data"]["logs"])
    assert len(actual["data"]["logs"]) == actual["data"]["total"] == 2

    assert actual["data"]["logs"][0]["task_type"] == "Event"
    assert actual["data"]["logs"][0]["event_class"] == "model_testing"
    assert actual["data"]["logs"][0]["status"] == "Initiated"
    assert actual["data"]["logs"][0]["data"] == [
        {
            'name': 'BOT',
            'value': pytest.bot
        },
        {
            'name': 'USER',
            'value': 'test_user'
        }
    ]
    assert actual["data"]["logs"][0]["executor_log_id"]
    assert actual["data"]["logs"][0]['from_executor'] is True
    assert actual["data"]["logs"][0]['bot'] == pytest.bot

    assert actual["data"]["logs"][1]["task_type"] == "Event"
    assert actual["data"]["logs"][1]["event_class"] == "model_training"
    assert actual["data"]["logs"][1]["status"] == "Initiated"
    assert actual["data"]["logs"][1]["data"] == [
        {
            'name': 'BOT',
            'value': pytest.bot
        },
        {
            'name': 'USER',
            'value': 'test_user'
        }
    ]
    assert actual["data"]["logs"][1]["executor_log_id"]
    assert actual["data"]["logs"][1]['from_executor'] is True
    assert actual["data"]["logs"][1]['bot'] == pytest.bot

    response = client.get(
        url=f"/api/bot/{pytest.bot}/executor/logs?task_type=Event&event_class=model_training",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    response = client.get(
        url=f"/api/bot/{pytest.bot}/logs/executor?task_type=Event&event_class=model_training",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert not actual["message"]
    assert actual["success"]
    assert len(actual["data"]["logs"]) == actual["data"]["total"] == 1
    assert actual["data"]["logs"][0]["task_type"] == "Event"
    assert actual["data"]["logs"][0]["event_class"] == "model_training"
    assert actual["data"]["logs"][0]["status"] == "Initiated"
    assert actual["data"]["logs"][0]["data"] == [
        {
            'name': 'BOT',
            'value': pytest.bot
        },
        {
            'name': 'USER',
            'value': 'test_user'
        }
    ]
    assert actual["data"]["logs"][0]["executor_log_id"]
    assert actual["data"]["logs"][0]['from_executor'] is True
    assert actual["data"]["logs"][0]['bot'] == pytest.bot

def test_search_executor_logs(get_executor_logs):
    from_date = utc_now().date() - timedelta(days=1)
    to_date = from_date + timedelta(days=2)

    search_response = client.get(
        f"/api/bot/{pytest.bot}/logs/executor/search?from_date={from_date}&to_date={to_date}&status=Success",
        headers={"Authorization": f"{pytest.token_type} {pytest.access_token}"},
    )

    response_json = search_response.json()
    print("executor:", response_json)

    assert response_json["success"] is True
    assert response_json["error_code"] == 0

    data = response_json["data"]
    assert "logs" in data
    assert isinstance(data["logs"], list)

    logs = data["logs"]
    assert data["total"] == len(logs)
    assert all(log.get("status") == STATUSES.SUCCESS.value for log in logs)

    # Group by task_type and assert structure
    for log in logs:
        task_type = log.get("task_type")
        assert task_type in {"Callback", "Action", "Event"}

        assert "event_class" in log
        assert "data" in log
        assert "timestamp" in log
        assert "executor_log_id" in log

        if task_type == "Callback":
            assert log["event_class"] == "pyscript_evaluator"
            assert isinstance(log["data"], dict)
            assert "source_code" in log["data"]
            assert "predefined_objects" in log["data"]
            assert isinstance(log["data"]["predefined_objects"], dict)
            assert "bot_response" in str(log.get("response", {}))  # response body nested

        elif task_type == "Action":
            assert log["event_class"] in {"pyscript_evaluator", "scheduler_evaluator"}
            assert isinstance(log["data"], dict)
            assert "source_code" in log["data"]
            assert "predefined_objects" in log["data"]

        elif task_type == "Event":
            assert log["event_class"] in {"model_testing", "model_training"}
            assert isinstance(log["data"], list)
            assert all(isinstance(entry, dict) and "name" in entry and "value" in entry for entry in log["data"])

def test_update_user_details_with_invalid_onboarding_status():
    response = client.post(
        "/api/user/details/Invalid",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert not actual["data"]
    assert actual["message"] == "Invalid is not a valid status"

    response = client.post(
        "/api/user/details/INITIATED",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert not actual["data"]
    assert actual["message"] == "INITIATED is not a valid status"

    response = client.post(
        "/api/user/details/IN PROGRESS",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert not actual["data"]
    assert actual["message"] == "IN PROGRESS is not a valid status"

    response = client.post(
        "/api/user/details/Done",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert not actual["data"]
    assert actual["message"] == "Done is not a valid status"


def test_update_user_details_with_onboarding_status():
    response = client.get(
        "/api/user/details",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    assert response["data"]["user"]["_id"]
    assert response["data"]["user"]["email"] == "integration@demo.ai"
    assert (
            response["data"]["user"]["bots"]["account_owned"][0]["user"]
            == "integration@demo.ai"
    )
    assert response["data"]["user"]["bots"]["account_owned"][0]["timestamp"]
    assert response["data"]["user"]["bots"]["account_owned"][0]["name"]
    assert response["data"]["user"]["bots"]["account_owned"][0]["_id"]
    assert not response["data"]["user"]["bots"]["shared"]
    assert response["data"]["user"]["timestamp"]
    assert response["data"]["user"]["status"]
    assert response["data"]["user"]["account_name"] == "integration"
    assert response["data"]["user"]["first_name"] == "Demo"
    assert response["data"]["user"]["last_name"] == "User"
    assert response["data"]["user"]["onboarding_status"] == "Not Completed"
    assert response["data"]["user"]["is_onboarded"] is False

    response = client.post(
        "/api/user/details/In Progress",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Details updated!"

    response = client.get(
        "/api/user/details",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    assert response["data"]["user"]["_id"]
    assert response["data"]["user"]["email"] == "integration@demo.ai"
    assert (
            response["data"]["user"]["bots"]["account_owned"][0]["user"]
            == "integration@demo.ai"
    )
    assert response["data"]["user"]["bots"]["account_owned"][0]["timestamp"]
    assert response["data"]["user"]["bots"]["account_owned"][0]["name"]
    assert response["data"]["user"]["bots"]["account_owned"][0]["_id"]
    assert not response["data"]["user"]["bots"]["shared"]
    assert response["data"]["user"]["timestamp"]
    assert response["data"]["user"]["status"]
    assert response["data"]["user"]["account_name"] == "integration"
    assert response["data"]["user"]["first_name"] == "Demo"
    assert response["data"]["user"]["last_name"] == "User"
    assert response["data"]["user"]["onboarding_status"] == "In Progress"
    assert response["data"]["user"]["onboarding_timestamp"]
    assert response["data"]["user"]["is_onboarded"] is False

    response = client.post(
        "/api/user/details/Completed",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Details updated!"

    response = client.get(
        "/api/user/details",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    assert response["data"]["user"]["_id"]
    assert response["data"]["user"]["email"] == "integration@demo.ai"
    assert (
            response["data"]["user"]["bots"]["account_owned"][0]["user"]
            == "integration@demo.ai"
    )
    assert response["data"]["user"]["bots"]["account_owned"][0]["timestamp"]
    assert response["data"]["user"]["bots"]["account_owned"][0]["name"]
    assert response["data"]["user"]["bots"]["account_owned"][0]["_id"]
    assert not response["data"]["user"]["bots"]["shared"]
    assert response["data"]["user"]["timestamp"]
    assert response["data"]["user"]["status"]
    assert response["data"]["user"]["account_name"] == "integration"
    assert response["data"]["user"]["first_name"] == "Demo"
    assert response["data"]["user"]["last_name"] == "User"
    assert response["data"]["user"]["onboarding_status"] == "Completed"
    assert response["data"]["user"]["onboarding_timestamp"]
    assert response["data"]["user"]["is_onboarded"] is True
