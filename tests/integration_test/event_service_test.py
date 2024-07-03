import os
import re

from dramatiq.brokers.stub import StubBroker
from loguru import logger
from unittest.mock import patch
from starlette.testclient import TestClient

from kairon.shared.constants import EventClass, EventExecutor
from kairon.shared.utils import Utility

os_patch = patch.dict(
    os.environ,
    {
        "DATABASE_URL": "mongodb://local:27035",
        "system_file": "./tests/testing_data/system.yaml",
        "ASYNC_TEST_TIMEOUT": "360",
        "ENABLE_APM": "False",
        "APM_SERVER_URL": "http://localhost:8800",
    },
    clear=True,
)
os_patch.start()
with patch("pymongo.collection.Collection.create_index"):
        from kairon.events.server import app

        Utility.load_environment()
        client = TestClient(app)

broker = StubBroker()


def test_index():
    response = client.get("/")
    assert response.json() == {
        "data": None,
        "message": "Event server running!",
        "error_code": 0,
        "success": True,
    }


def test_healthcheck():
    response = client.get("/healthcheck")
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"] == "health check ok"


def test_lambda_executor():
    mock_env = Utility.environment.copy()
    mock_env["events"]["executor"]["type"] = EventExecutor.aws_lambda
    mock_env["events"]["task_definition"][EventClass.model_training] = "train-model"

    def __mock_lambda_execution(*args, **kwargs):
        assert args == (
            "model_training",
            [
                {"name": "BOT", "value": "test"},
                {"name": "USER", "value": "test_user"},
                {"name": "TOKEN", "value": "asdfghjk23456789"},
            ],
        )
        return {
            "StatusCode": 200,
            "FunctionError": "Unhandled",
            "LogResult": "U1RBUlQgUmVxdWVzdElkOiBlOTJiMWNjMC02MjcwLTQ0OWItOA3O=",
            "ExecutedVersion": "$LATEST",
            "Payload": {"response": "task triggered"},
        }

    with patch.dict(Utility.environment, mock_env):
        with patch(
            "kairon.shared.cloud.utils.CloudUtility.trigger_lambda"
        ) as mock_trigger:
            mock_trigger.side_effect = __mock_lambda_execution
            request_body = {
                "data": {
                    "bot": "test",
                    "user": "test_user",
                    "token": "asdfghjk23456789",
                }
            }
            response = client.post(
                f"/api/events/execute/{EventClass.model_training}?is_scheduled=false",
                json=request_body,
            )
            response_json = response.json()
            assert response_json == {
                "data": {
                    "StatusCode": 200,
                    "FunctionError": "Unhandled",
                    "LogResult": "U1RBUlQgUmVxdWVzdElkOiBlOTJiMWNjMC02MjcwLTQ0OWItOA3O=",
                    "ExecutedVersion": "$LATEST",
                    "Payload": {"response": "task triggered"},
                },
                "success": True,
                "error_code": 0,
                "message": None,
            }


def test_lambda_executor_failed():
    mock_env = Utility.environment.copy()
    mock_env["events"]["executor"]["type"] = EventExecutor.aws_lambda
    mock_env["events"]["task_definition"][EventClass.model_training] = "train-model"

    def __mock_lambda_execution(*args, **kwargs):
        assert args == (
            "model_training",
            [
                {"name": "BOT", "value": "test_bot"},
                {"name": "USER", "value": "test_user"},
                {"name": "TOKEN", "value": "asdfghjk23456789"},
            ],
        )
        return {
            "StatusCode": 400,
            "FunctionError": "Unhandled",
            "LogResult": "U1RBUlQgUmVxdWVzdElkOiBlOTJiMWNjMC02MjcwLTQ0OWItOA3O=",
            "ExecutedVersion": "$LATEST",
            "Payload": {"response": "Failed to trigger task"},
        }

    with patch.dict(Utility.environment, mock_env):
        with patch(
            "kairon.shared.cloud.utils.CloudUtility.trigger_lambda"
        ) as mock_trigger:
            mock_trigger.side_effect = __mock_lambda_execution
            request_body = {
                "data": {
                    "bot": "test_bot",
                    "user": "test_user",
                    "token": "asdfghjk23456789",
                }
            }
            response = client.post(
                f"/api/events/execute/{EventClass.model_training}?is_scheduled=false",
                json=request_body,
            )
            response_json = response.json()
            assert response_json == {
                "data": None,
                "success": False,
                "error_code": 422,
                "message": "{'StatusCode': 400, 'FunctionError': 'Unhandled', 'LogResult': 'U1RBUlQgUmVxdWVzdElkOiBlOTJiMWNjMC02MjcwLTQ0OWItOA3O=', 'ExecutedVersion': '$LATEST', 'Payload': {'response': 'Failed to trigger task'}}",
            }


@patch("kairon.shared.events.broker.mongo.Database", autospec=True)
@patch("kairon.shared.events.broker.mongo.MongoClient", autospec=True)
def test_dramatiq_executor(mock_mongo_client, mock_database):
    mock_env = Utility.environment.copy()
    mock_env["events"]["executor"]["type"] = EventExecutor.dramatiq
    mock_env["events"]["task_definition"][EventClass.model_training] = "train-model"
    with patch.dict(Utility.environment, mock_env):
        with patch("dramatiq_mongodb.MongoDBBroker.__new__") as mock_broker:
            mock_broker.return_value = broker
            request_body = {
                "data": {
                    "bot": "test",
                    "user": "test_user",
                    "token": "asdfghjk23456789",
                }
            }
            response = client.post(
                f"/api/events/execute/{EventClass.model_training}?is_scheduled=false",
                json=request_body,
            )
            response_json = response.json()
            assert re.match(
                '{"queue_name":"kairon_events","actor_name":"execute_task","args":\["model_training",{"bot":"test","user":"test_user","token":"asdfghjk23456789"}],"kwargs":\{},"options":\{},*',
                response_json["data"],
            )
            assert response_json["success"]
            assert response_json["error_code"] == 0
            assert response_json["message"] is None


@patch("kairon.shared.events.broker.mongo.Database", autospec=True)
@patch("kairon.shared.events.broker.mongo.MongoClient", autospec=True)
def test_dramatiq_executor_failure(mock_mongo_client, mock_database):
    mock_env = Utility.environment.copy()
    mock_env["events"]["executor"]["type"] = EventExecutor.dramatiq
    mock_env["events"]["task_definition"][EventClass.model_training] = "train-model"
    request_body = {
        "data": {"bot": "test", "user": "test_user", "token": "asdfghjk23456789"}
    }

    def __mock_enqueue_error(*args, **kwargs):
        raise Exception("Failed to add message to mongo broker")

    with patch.dict(Utility.environment, mock_env):
        with patch("dramatiq_mongodb.MongoDBBroker.__new__") as mock_broker:
            mock_broker.return_value = broker
            with patch(
                "kairon.shared.events.broker.mongo.MongoBroker.enqueue"
            ) as mock_enqueue:
                mock_enqueue.side_effect = __mock_enqueue_error
                response = client.post(
                    f"/api/events/execute/{EventClass.model_training}?is_scheduled=false",
                    json=request_body,
                )
            response_json = response.json()
            assert response_json == {
                "data": None,
                "success": False,
                "error_code": 422,
                "message": "Failed to add message to mongo broker",
            }


def test_standalone_executor():
    mock_env = Utility.environment.copy()
    mock_env["events"]["executor"]["type"] = EventExecutor.standalone
    mock_env["events"]["task_definition"][EventClass.model_training] = "train-model"
    request_body = {
        "data": {"bot": "test", "user": "test_user", "token": "asdfghjk23456789"}
    }

    def __mock_execute(*args, **kwargs):
        logger.debug(f"args: {args}, kwargs: {kwargs}")
        assert kwargs == {
            "bot": "test",
            "user": "test_user",
            "token": "asdfghjk23456789",
        }

    with patch.dict(Utility.environment, mock_env):
        with patch(
            "kairon.events.definitions.model_training.ModelTrainingEvent.execute"
        ) as event:
            event.side_effect = __mock_execute
            response = client.post(
                f"/api/events/execute/{EventClass.model_training}?is_scheduled=false",
                json=request_body,
            )
            response_json = response.json()
            assert response_json == {
                "data": "Task Spawned!",
                "error_code": 0,
                "message": None,
                "success": True,
            }


def test_standalone_executor_failure():
    mock_env = Utility.environment.copy()
    mock_env["events"]["executor"]["type"] = EventExecutor.standalone
    mock_env["events"]["task_definition"][EventClass.model_training] = "train-model"
    request_body = {
        "data": {"bot": "test", "user": "test_user", "token": "asdfghjk23456789"}
    }

    def __mock_execute(*args, **kwargs):
        logger.debug(f"args: {args}, kwargs: {kwargs}")
        assert kwargs == {
            "bot": "test",
            "user": "test_user",
            "token": "asdfghjk23456789",
        }
        raise Exception("No training data found!")

    with patch.dict(Utility.environment, mock_env):
        with patch(
            "kairon.events.definitions.model_training.ModelTrainingEvent.execute"
        ) as event:
            event.side_effect = __mock_execute
            response = client.post(
                f"/api/events/execute/{EventClass.model_training}?is_scheduled=false",
                json=request_body,
            )
            response_json = response.json()
            assert response_json == {
                "data": "Task Spawned!",
                "error_code": 0,
                "message": None,
                "success": True,
            }


@patch("kairon.events.scheduler.kscheduler.KScheduler.add_job", autospec=True)
def test_scheduled_event_request(mock_add_job):
    mock_add_job.return_value = None
    request_body = {
        "data": {
            "bot": "test",
            "user": "test_user",
            "event_id": "6543212345678909876543",
        },
        "cron_exp": "* * * * *",
    }
    response = client.post(
        f"/api/events/execute/{EventClass.message_broadcast}?is_scheduled=True",
        json=request_body,
    )
    response_json = response.json()
    assert response_json == {
        "data": None,
        "success": True,
        "error_code": 0,
        "message": "Event Scheduled!",
    }


@patch("kairon.shared.cloud.utils.CloudUtility.trigger_lambda")
def test_non_scheduled_message_broadcast_request(mock_trigger_lambda):
    mock_env = Utility.environment.copy()
    mock_env["events"]["executor"]["type"] = EventExecutor.aws_lambda
    mock_env["events"]["task_definition"][
        EventClass.model_training
    ] = "message_broadcast"

    def __mock_lambda_execution(*args, **kwargs):
        assert args == (
            "message_broadcast",
            [
                {"name": "BOT", "value": "test"},
                {"name": "USER", "value": "test_user"},
                {"name": "EVENT_ID", "value": "6543212345678909876543"},
            ],
        )
        return {
            "StatusCode": 200,
            "FunctionError": "Unhandled",
            "LogResult": "U1RBUlQgUmVxdWVzdElkOiBlOTJiMWNjMC02MjcwLTQ0OWItOA3O=",
            "ExecutedVersion": "$LATEST",
            "Payload": {"response": "task triggered"},
        }

    mock_trigger_lambda.side_effect = __mock_lambda_execution

    request_body = {
        "data": {
            "bot": "test",
            "user": "test_user",
            "event_id": "6543212345678909876543",
        }
    }
    response = client.post(
        f"/api/events/execute/{EventClass.message_broadcast}?is_scheduled=false",
        json=request_body,
    )
    response_json = response.json()
    assert response_json == {
        "data": {
            "StatusCode": 200,
            "FunctionError": "Unhandled",
            "LogResult": "U1RBUlQgUmVxdWVzdElkOiBlOTJiMWNjMC02MjcwLTQ0OWItOA3O=",
            "ExecutedVersion": "$LATEST",
            "Payload": {"response": "task triggered"},
        },
        "success": True,
        "error_code": 0,
        "message": None,
    }


def test_scheduled_event_request_not_allowed():
    request_body = {
        "data": {
            "bot": "test",
            "user": "test_user",
            "event_id": "6543212345678909876543",
        },
        "cron_exp": "* * * * *",
    }
    response = client.post(
        f"/api/events/execute/{EventClass.model_training}?is_scheduled=True",
        json=request_body,
    )
    response_json = response.json()
    assert response_json == {
        "data": None,
        "success": False,
        "error_code": 422,
        "message": "Only {'message_broadcast'} type events are allowed to be scheduled!",
    }


def test_scheduled_event_request_parameters_missing():
    request_body = {"data": {}, "cron_exp": "* * * * *"}
    response = client.post(
        f"/api/events/execute/{EventClass.message_broadcast}?is_scheduled=True",
        json=request_body,
    )
    response_json = response.json()
    print(response_json)
    assert response_json == {
        "detail": [
            {
                "loc": ["body", "data"],
                "msg": "user and bot are required!",
                "type": "value_error",
            }
        ]
    }

    request_body = {
        "data": {"bot": "test", "user": "test_user"},
        "cron_exp": "* * * * *",
    }
    response = client.post(
        f"/api/events/execute/{EventClass.message_broadcast}?is_scheduled=True",
        json=request_body,
    )
    response_json = response.json()
    print(response_json)
    assert response_json == {
        "data": None,
        "success": False,
        "error_code": 422,
        "message": "event_id is required for message_broadcast!",
    }


@patch("kairon.events.scheduler.kscheduler.KScheduler.update_job", autospec=True)
def test_update_scheduled_event_request(mock_update_job):
    mock_update_job.return_value = None
    request_body = {
        "data": {
            "bot": "test",
            "user": "test_user",
            "event_id": "6543212345678909876543",
        },
        "cron_exp": "* * * * *",
        "timezone": "Asia/Kolkata",
    }
    response = client.put(
        f"/api/events/execute/{EventClass.message_broadcast}?is_scheduled=True",
        json=request_body,
    )
    response_json = response.json()
    assert response_json == {
        "data": None,
        "success": True,
        "error_code": 0,
        "message": "Scheduled event updated!",
    }


def test_update_scheduled_event_request_not_allowed():
    request_body = {
        "data": {
            "bot": "test",
            "user": "test_user",
            "event_id": "6543212345678909876543",
        },
        "cron_exp": "* * * * *",
    }
    response = client.put(
        f"/api/events/execute/{EventClass.model_testing}?is_scheduled=True",
        json=request_body,
    )
    response_json = response.json()
    assert response_json == {
        "data": None,
        "success": False,
        "error_code": 422,
        "message": "Only {'message_broadcast'} type events are allowed to be scheduled!",
    }


def test_update_scheduled_event_request_missing_parameters():
    request_body = {"data": {"bot": "test", "user": "test_user"}}
    response = client.put(
        f"/api/events/execute/{EventClass.message_broadcast}?is_scheduled=True",
        json=request_body,
    )
    response_json = response.json()
    assert response_json == {
        "data": None,
        "success": False,
        "error_code": 422,
        "message": "cron_exp is required for scheduled events!",
    }


def test_update_non_scheduled_event_request():
    request_body = {
        "data": {
            "bot": "test",
            "user": "test_user",
            "event_id": "6543212345678909876543",
        }
    }
    response = client.put(
        f"/api/events/execute/{EventClass.message_broadcast}?is_scheduled=False",
        json=request_body,
    )
    response_json = response.json()
    assert response_json == {
        "data": None,
        "success": False,
        "error_code": 422,
        "message": "Updating non-scheduled event not supported!",
    }


@patch("kairon.events.scheduler.kscheduler.KScheduler.delete_job", autospec=True)
def test_delete_scheduled_event_request(mock_delet_job):
    mock_delet_job.return_value = None
    response = client.delete(f"/api/events/6543212345678909876543")
    response_json = response.json()
    assert response_json == {
        "data": None,
        "success": True,
        "error_code": 0,
        "message": "Scheduled event deleted!",
    }

os_patch.stop()