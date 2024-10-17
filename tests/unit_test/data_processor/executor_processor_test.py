import os

import pytest
from bson import ObjectId
from mongoengine import connect

from kairon.shared.constants import EventClass
from kairon.shared.data.constant import EVENT_STATUS, TASK_TYPE
from kairon.shared.events.processor import ExecutorProcessor
from kairon.shared.utils import Utility

os.environ["system_file"] = "./tests/testing_data/system.yaml"
Utility.load_environment()
Utility.load_system_metadata()


class TestExecutorProcessor:

    @pytest.fixture(autouse=True, scope='class')
    def init_connection(self):
        connect(**Utility.mongoengine_connection())

    @pytest.fixture()
    def get_executor_logs(self):
        from kairon.events.executors.base import ExecutorBase
        executor = ExecutorBase()
        executor.log_task(event_class=EventClass.model_training.value, task_type=TASK_TYPE.EVENT.value,
                          data=[{"name": "BOT", "value": '66cd84e4f206edf5b776d6d8'},
                                {"name": "USER", "value": "test_user"}],
                          executor_log_id=ObjectId().__str__(), status=EVENT_STATUS.INITIATED.value,
                          from_executor=True)
        executor.log_task(event_class=EventClass.model_testing.value, task_type=TASK_TYPE.EVENT.value,
                          data=[{"name": "BOT", "value": '66cd84e4f206edf5b776d6d8'},
                                {"name": "USER", "value": "test_user"}],
                          executor_log_id=ObjectId().__str__(), status=EVENT_STATUS.INITIATED.value,
                          from_executor=True)
        executor.log_task(event_class=EventClass.web_search.value, task_type=TASK_TYPE.ACTION.value,
                          data={"text": "I am good", "site": "www.kairon.com", "topn": 1,
                                "bot": "66cd84e4f206edf5b776d6d8"},
                          executor_log_id=ObjectId().__str__(), status=EVENT_STATUS.COMPLETED.value,
                          response={
                              "ResponseMetadata": {
                                  "RequestId": "dc824d8c-843b-47fe-8b56-fd6cbec3023403b",
                                  "HTTPStatusCode": 200,
                                  "HTTPHeaders": {
                                      "date": "Wed, 18 Sep 2024 09:15:07 GMT",
                                      "content-type": "application/json",
                                      "content-length": "506",
                                      "connection": "keep-alive",
                                      "x-amzn-requestid": "dc824d8c-843b-47fe-8b56-fd6cbec3025b",
                                      "x-amzn-remapped-content-length": "0",
                                      "x-amz-executed-version": "$LATEST",
                                      "x-amz-log-result": "dfldfjklkdlsfkldfdjdjfdkj",
                                      "x-amzn-trace-id": "Root=1-66ea9a18-7dc80b6e0c0873b139369c35;Sampled=1;Lineage=1:79a5f83d:0"
                                  },
                                  "RetryAttempts": 0
                              },
                              "StatusCode": 200,
                              "LogResult": "kdflkdflkdkfldkfldklfdklfkdljdgn",
                              "ExecutedVersion": "$LATEST",
                              "Payload": {
                                  "statusCode": 200,
                                  "statusDescription": "200 OK",
                                  "isBase64Encoded": False,
                                  "headers": {
                                      "Content-Type": "text/html; charset=utf-8"
                                  },
                                  "body": [
                                      {
                                          "title": "David Guetta & Bebe Rexha - I'm Good (Blue) [Official Music Video] - YouTube",
                                          "description": "Listen to &quot;I&#x27;m <strong>Good</strong> (Blue)&quot; by David Guetta and Bebe Rexha: https://davidguetta.lnk.to/ImGood🔔 Subscribe to be notified for new videoshttps://davidguetta.ln",
                                          "url": "https://www.youtube.com/watch?v=90RLzVUuXe4"
                                      }
                                  ]
                              }
                          }
                          )
        executor.log_task(event_class=EventClass.scheduler_evaluator.value, task_type=TASK_TYPE.ACTION.value,
                          data=[
                              {
                                  "name": "SOURCE_CODE",
                                  "value": "import requests\n\nurl=\"https://waba-v2.360dialog.io/messages\"\n\nheaders={'Content-Type': 'application/json', 'D360-API-KEY' : 'mks3hj3489348938493849839R3RAK'}\n\ncontacts = ['919657099999','918210099999']\ncontacts = [\"919515999999\"]\nbody = {\n    \"messaging_product\": \"whatsapp\",\n    \"recipient_type\": \"individual\",\n    \"to\": \"9199991685\",\n    \"type\": \"template\",\n    \"template\": {\n        \"namespace\": \"54500467_f322_4595_becd_41555889bfd8\",\n        \"language\": {\n            \"policy\": \"deterministic\",\n            \"code\": \"en\"\n        },\n        \"name\": \"schedule_action_test\"\n    }\n}\n\nfor contact in contacts:\n  body[\"to\"] = contact\n  resp = requests.post(url, headers=headers, data=json.dumps(body))\n  resp = resp.json()\n  print(resp[\"messages\"])\n\nbot_response = 'this from callback pyscript'"
                              },
                              {
                                  "name": "PREDEFINED_OBJECTS",
                                  "value": {
                                      "val1": "rajan",
                                      "val2": "hitesh",
                                      "passwd": None,
                                      "myuser": "mahesh.sattala@digite.com",
                                      "bot": '66cd84e4f206edf5b776d6d8',
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
                                      "bot": '66cd84e4f206edf5b776d6d8',
                                      "kairon_action_response": "Test",
                                      "session_started_metadata": {
                                          "tabname": "default",
                                          "displayLabel": "",
                                          "telemetry-uid": "None",
                                          "telemetry-sid": "None",
                                          "is_integration_user": False,
                                          "bot": "66cd84e4f206edf5b776d6d8",
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
                                          "bot": '66cd84e4f206edf5b776d6d8',
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
                                  "bot": '66cd84e4f206edf5b776d6d8',
                                  "sender_id": "mahesh.sattala@digite.com",
                                  "channel": "unsupported (None)",
                                  "metadata": {
                                      "first_name": "rajan",
                                      "bot": '66cd84e4f206edf5b776d6d8'
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
                                      "bot": '66cd84e4f206edf5b776d6d8',
                                      "sender_id": "mahesh.sattala@digite.com",
                                      "channel": "unsupported (None)",
                                      "metadata": {
                                          "first_name": "rajan",
                                          "bot": '66cd84e4f206edf5b776d6d8'
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

    def test_get_executor_logs(self, get_executor_logs):
        processor = ExecutorProcessor()
        logs = list(processor.get_executor_logs("66cd84e4f206edf5b776d6d8", task_type="Callback"))
        assert len(logs) == 1
        assert logs[0]["task_type"] == "Callback"
        assert logs[0]["event_class"] == "pyscript_evaluator"
        assert logs[0]["status"] == "Completed"
        assert logs[0]["data"] == {
            'source_code': 'bot_response = "test - this is from callback test"',
            'predefined_objects': {
                'req': {'type': 'GET', 'body': None, 'params': {}},
                'req_host': '127.0.0.1', 'action_name': 'clbk1',
                'callback_name': 'test', 'bot': '66cd84e4f206edf5b776d6d8',
                'sender_id': 'mahesh.sattala@digite.com',
                'channel': 'unsupported (None)',
                'metadata': {'first_name': 'rajan',
                             'bot': '66cd84e4f206edf5b776d6d8'},
                'identifier': '01928eb52813799e81c56803ecf39e6e',
                'callback_url': 'http://localhost:5059/callback/d/01928eb52813799e81c56803ecf39e6e/98bxWAMY9HF40La5AKQjEb-0JqaDTKX_Mmmmmmmmmmm',
                'execution_mode': 'async', 'state': 0, 'is_valid': True}
        }
        assert logs[0]["response"] == {
            'ResponseMetadata': {'RequestId': '0da1cdd1-1702-473b-8109-67a39f990835', 'HTTPStatusCode': 200,
                                 'HTTPHeaders': {'date': 'Tue, 15 Oct 2024 07:38:01 GMT',
                                                 'content-type': 'application/json', 'content-length': '740',
                                                 'connection': 'keep-alive',
                                                 'x-amzn-requestid': '0da1cdd1-1702-473b-8109-67a39f9sdlksldksl',
                                                 'x-amzn-remapped-content-length': '0',
                                                 'x-amz-executed-version': '$LATEST',
                                                 'x-amz-log-result': 'sdskjdksjdkjskdjskjdksj',
                                                 'x-amzn-trace-id': 'Root=1-670e1bd6-25e7667c7c6ce37f09a9afc7;Sampled=1;Lineage=1:d072fc6c:0'},
                                 'RetryAttempts': 0}, 'StatusCode': 200, 'LogResult': 'sldklskdlskdlskdlk',
            'ExecutedVersion': '$LATEST',
            'Payload': {'statusCode': 200, 'statusDescription': '200 OK', 'isBase64Encoded': False,
                        'headers': {'Content-Type': 'text/html; charset=utf-8'},
                        'body': {'req': {'type': 'GET', 'body': None, 'params': {}}, 'req_host': '127.0.0.1',
                                 'action_name': 'clbk1', 'callback_name': 'test', 'bot': '66cd84e4f206edf5b776d6d8',
                                 'sender_id': 'mahesh.sattala@digite.com', 'channel': 'unsupported (None)',
                                 'metadata': {'first_name': 'rajan', 'bot': '66cd84e4f206edf5b776d6d8'},
                                 'identifier': '01928eb52813799e81c56803ecf39e6e',
                                 'callback_url': 'http://localhost:5059/callback/d/01928eb52813799e81c56803ecf39e6e/98bxWAMY9HF40La5AKQjEb-0JqaDTKX_Mmmmmmmmmmm',
                                 'execution_mode': 'async', 'state': 0, 'is_valid': True,
                                 'bot_response': 'test - this is from callback test'}}}
        assert logs[0]["executor_log_id"]
        assert logs[0]['bot'] == "66cd84e4f206edf5b776d6d8"

        logs = list(processor.get_executor_logs("66cd84e4f206edf5b776d6d8", task_type="Event"))
        assert len(logs) == 2
        assert logs[0]["task_type"] == "Event"
        assert logs[0]["event_class"] == "model_testing"
        assert logs[0]["status"] == "Initiated"
        assert logs[0]["data"] == [
            {
                'name': 'BOT',
                'value': "66cd84e4f206edf5b776d6d8"
            },
            {
                'name': 'USER',
                'value': 'test_user'
            }
        ]
        assert logs[0]["executor_log_id"]
        assert logs[0]['from_executor'] is True
        assert logs[0]['bot'] == "66cd84e4f206edf5b776d6d8"

        assert logs[1]["task_type"] == "Event"
        assert logs[1]["event_class"] == "model_training"
        assert logs[1]["status"] == "Initiated"
        assert logs[1]["data"] == [
            {
                'name': 'BOT',
                'value': "66cd84e4f206edf5b776d6d8"
            },
            {
                'name': 'USER',
                'value': 'test_user'
            }
        ]
        assert logs[1]["executor_log_id"]
        assert logs[1]['from_executor'] is True
        assert logs[1]['bot'] == "66cd84e4f206edf5b776d6d8"

        logs = list(processor.get_executor_logs("66cd84e4f206edf5b776d6d8", task_type="Event",
                                                event_class="model_training"))
        assert len(logs) == 1
        assert logs[0]["task_type"] == "Event"
        assert logs[0]["event_class"] == "model_training"
        assert logs[0]["status"] == "Initiated"
        assert logs[0]["data"] == [
            {
                'name': 'BOT',
                'value': "66cd84e4f206edf5b776d6d8"
            },
            {
                'name': 'USER',
                'value': 'test_user'
            }
        ]
        assert logs[0]["executor_log_id"]
        assert logs[0]['from_executor'] is True
        assert logs[0]['bot'] == "66cd84e4f206edf5b776d6d8"

    def test_get_row_count(self):
        processor = ExecutorProcessor()
        count = processor.get_row_count("66cd84e4f206edf5b776d6d8")
        assert count == 6

        count = processor.get_row_count("66cd84e4f206edf5b776d6d8", event_class="pyscript_evaluator")
        assert count == 2

        count = processor.get_row_count("66cd84e4f206edf5b776d6d8", event_class="pyscript_evaluator",
                                        task_type="Callback")
        assert count == 1

        count = processor.get_row_count("66cd84e4f206edf5b776d6d8", task_type="Event")
        assert count == 2

        count = processor.get_row_count("66cd84e4f206edf5b776d6d8", event_class="model_testing",
                                        task_type="Event")
        assert count == 1

        count = processor.get_row_count("66cd84e4f206edf5b776d6d8", task_type="Action")
        assert count == 3


