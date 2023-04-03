from unittest import mock

from dramatiq.brokers.stub import StubBroker
from loguru import logger
from tornado.test.testing_test import AsyncHTTPTestCase
from mock import patch

from kairon.shared.constants import EventClass, EventExecutor
from kairon.shared.utils import Utility
import json
import os

os.environ["system_file"] = "./tests/testing_data/system.yaml"
os.environ['ASYNC_TEST_TIMEOUT'] = "360"
os.environ["system_file"] = "./tests/testing_data/system.yaml"

with patch("pymongo.collection.Collection.create_index"):
    with patch.dict(os.environ, {"DATABASE_URL": "mongodb://local:27035"}):
        Utility.load_environment()
        from kairon.events.server import make_app


class TestEventServer(AsyncHTTPTestCase):
    broker = StubBroker()

    def get_app(self):
        return make_app()

    def test_index(self):
        response = self.fetch("/")
        self.assertEqual(response.code, 200)
        self.assertEqual(response.body.decode("utf8"), 'Kairon Server Running')

    def test_lambda_executor(self):
        mock_env = Utility.environment.copy()
        mock_env['events']['executor']['type'] = EventExecutor.aws_lambda
        mock_env['events']['task_definition'][EventClass.model_training] = 'train-model'

        def __mock_lambda_execution(*args, **kwargs):
            assert args == ('model_training', [{'name': 'BOT', 'value': 'test'}, {'name': 'USER', 'value': 'test_user'},
                                               {'name': 'TOKEN', 'value': 'asdfghjk23456789'}])
            return {'StatusCode': 200, 'FunctionError': 'Unhandled',
                    'LogResult': 'U1RBUlQgUmVxdWVzdElkOiBlOTJiMWNjMC02MjcwLTQ0OWItOA3O=',
                    'ExecutedVersion': '$LATEST',
                    'Payload': {'response': 'task triggered'}}

        with patch.dict(Utility.environment, mock_env):
            with mock.patch("kairon.shared.cloud.utils.CloudUtility.trigger_lambda") as mock_trigger:
                mock_trigger.side_effect = __mock_lambda_execution
                request_body = json.dumps({"bot": "test", "user": "test_user", "token": "asdfghjk23456789"}).encode(
                    'utf-8')
                response = self.fetch(f"/api/events/execute/{EventClass.model_training}", method="POST",
                                      body=request_body)
                response_json = json.loads(response.body.decode("utf8"))
                self.assertEqual(response.code, 200)
                self.assertEqual(response_json, {"data": {"StatusCode": 200, "FunctionError": "Unhandled",
                                                          "LogResult": "U1RBUlQgUmVxdWVzdElkOiBlOTJiMWNjMC02MjcwLTQ0OWItOA3O=",
                                                          "ExecutedVersion": "$LATEST",
                                                          "Payload": {"response": "task triggered"}}, "success": True,
                                                 "error_code": 0, "message": None})

    def test_lambda_executor_failed(self):
        mock_env = Utility.environment.copy()
        mock_env['events']['executor']['type'] = EventExecutor.aws_lambda
        mock_env['events']['task_definition'][EventClass.model_training] = 'train-model'

        def __mock_lambda_execution(*args, **kwargs):
            assert args == (
            'model_training', [{'name': 'BOT', 'value': 'test_bot'}, {'name': 'USER', 'value': 'test_user'},
                               {'name': 'TOKEN', 'value': 'asdfghjk23456789'}])
            return {'StatusCode': 400, 'FunctionError': 'Unhandled',
                    'LogResult': 'U1RBUlQgUmVxdWVzdElkOiBlOTJiMWNjMC02MjcwLTQ0OWItOA3O=',
                    'ExecutedVersion': '$LATEST',
                    'Payload': {'response': 'Failed to trigger task'}}

        with patch.dict(Utility.environment, mock_env):
            with mock.patch("kairon.shared.cloud.utils.CloudUtility.trigger_lambda") as mock_trigger:
                mock_trigger.side_effect = __mock_lambda_execution
                request_body = json.dumps({"bot": "test_bot", "user": "test_user", "token": "asdfghjk23456789"}).encode(
                    'utf-8')
                response = self.fetch(f"/api/events/execute/{EventClass.model_training}", method="POST",
                                      body=request_body)
                response_json = json.loads(response.body.decode("utf8"))
                self.assertEqual(response.code, 200)
                self.assertEqual(response_json, {'data': None, 'success': False, 'error_code': 422,
                                                 'message': "{'StatusCode': 400, 'FunctionError': 'Unhandled', 'LogResult': 'U1RBUlQgUmVxdWVzdElkOiBlOTJiMWNjMC02MjcwLTQ0OWItOA3O=', 'ExecutedVersion': '$LATEST', 'Payload': {'response': 'Failed to trigger task'}}"})

    @patch('kairon.shared.events.broker.mongo.Database', autospec=True)
    @patch('kairon.shared.events.broker.mongo.MongoClient', autospec=True)
    def test_dramatiq_executor(self, mock_mongo_client, mock_database):
        mock_env = Utility.environment.copy()
        mock_env['events']['executor']['type'] = EventExecutor.dramatiq
        mock_env['events']['task_definition'][EventClass.model_training] = 'train-model'
        with patch.dict(Utility.environment, mock_env):
            with patch('dramatiq_mongodb.MongoDBBroker.__new__') as mock_broker:
                mock_broker.return_value = TestEventServer.broker
                request_body = json.dumps({"bot": "test", "user": "test_user", "token": "asdfghjk23456789"}).encode(
                    'utf-8')
                response = self.fetch(f"/api/events/execute/{EventClass.model_training}", method="POST",
                                      body=request_body)
                response_json = json.loads(response.body.decode("utf8"))
                self.assertEqual(response.code, 200)
                self.assertRegexpMatches(response_json['data'],
                                         '{"queue_name": "kairon_events", "actor_name": "execute_task", "args": \["model_training", {"bot": "test", "user": "test_user", "token": "asdfghjk23456789"}], "kwargs": {}, "options": {}, *')
                self.assertEqual(response_json['success'], True)
                self.assertEqual(response_json['error_code'], 0)
                self.assertEqual(response_json['message'], None)

    @patch('kairon.shared.events.broker.mongo.Database', autospec=True)
    @patch('kairon.shared.events.broker.mongo.MongoClient', autospec=True)
    def test_dramatiq_executor_failure(self, mock_mongo_client, mock_database):
        mock_env = Utility.environment.copy()
        mock_env['events']['executor']['type'] = EventExecutor.dramatiq
        mock_env['events']['task_definition'][EventClass.model_training] = 'train-model'
        request_body = json.dumps({"bot": "test", "user": "test_user", "token": "asdfghjk23456789"}).encode(
            'utf-8')

        def __mock_enqueue_error(*args, **kwargs):
            raise Exception("Failed to add message to mongo broker")

        with patch.dict(Utility.environment, mock_env):
            with patch('dramatiq_mongodb.MongoDBBroker.__new__') as mock_broker:
                mock_broker.return_value = TestEventServer.broker
                with patch('kairon.shared.events.broker.mongo.MongoBroker.enqueue') as mock_enqueue:
                    mock_enqueue.side_effect = __mock_enqueue_error
                    response = self.fetch(f"/api/events/execute/{EventClass.model_training}", method="POST",
                                          body=request_body)
                response_json = json.loads(response.body.decode("utf8"))
                self.assertEqual(response.code, 200)
                self.assertEqual(response_json, {"data": None, "success": False, "error_code": 422,
                                                 "message": "Failed to add message to mongo broker"})

    def test_standalone_executor(self):
        mock_env = Utility.environment.copy()
        mock_env['events']['executor']['type'] = EventExecutor.standalone
        mock_env['events']['task_definition'][EventClass.model_training] = 'train-model'
        request_body = json.dumps({"bot": "test", "user": "test_user", "token": "asdfghjk23456789"}).encode(
            'utf-8')

        def __mock_execute(*args, **kwargs):
            logger.debug(f"args: {args}, kwargs: {kwargs}")
            assert kwargs == {"bot": "test", "user": "test_user", 'token': 'asdfghjk23456789'}

        with patch.dict(Utility.environment, mock_env):
            with mock.patch("kairon.events.definitions.model_training.ModelTrainingEvent.execute") as event:
                event.side_effect = __mock_execute
                response = self.fetch(f"/api/events/execute/{EventClass.model_training}", method="POST",
                                      body=request_body)
                response_json = json.loads(response.body.decode("utf8"))
                self.assertEqual(response.code, 200)
                self.assertEqual(response_json,
                                 {'data': 'Task Spawned!', 'error_code': 0, 'message': None, 'success': True})

    def test_standalone_executor_failure(self):
        mock_env = Utility.environment.copy()
        mock_env['events']['executor']['type'] = EventExecutor.standalone
        mock_env['events']['task_definition'][EventClass.model_training] = 'train-model'
        request_body = json.dumps({"bot": "test", "user": "test_user", "token": "asdfghjk23456789"}).encode(
            'utf-8')

        def __mock_execute(*args, **kwargs):
            logger.debug(f"args: {args}, kwargs: {kwargs}")
            assert kwargs == {"bot": "test", "user": "test_user", 'token': 'asdfghjk23456789'}
            raise Exception("No training data found!")

        with patch.dict(Utility.environment, mock_env):
            with mock.patch("kairon.events.definitions.model_training.ModelTrainingEvent.execute") as event:
                event.side_effect = __mock_execute
                response = self.fetch(f"/api/events/execute/{EventClass.model_training}", method="POST",
                                      body=request_body)
                response_json = json.loads(response.body.decode("utf8"))
                self.assertEqual(response.code, 200)
                self.assertEqual(response_json,
                                 {'data': 'Task Spawned!', 'error_code': 0, 'message': None, 'success': True})

    @patch('kairon.events.scheduler.kscheduler.KScheduler.add_job', autospec=True)
    def test_scheduled_event_request(self, mock_add_job):
        request_body = json.dumps(
            {"bot": "test", "user": "test_user", "cron_exp": "* * * * *", "event_id": "6543212345678909876543"}).encode(
            'utf-8')
        response = self.fetch(f"/api/events/execute/{EventClass.message_broadcast}?is_scheduled=True", method="POST",
                              body=request_body)
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response.code, 200)
        self.assertEqual(response_json, {"data": None, "success": True, "error_code": 0, "message": "Event Scheduled!"})

    @patch("kairon.shared.cloud.utils.CloudUtility.trigger_lambda")
    @patch('kairon.events.scheduler.kscheduler.KScheduler.add_job', autospec=True)
    def test_non_scheduled_message_broadcast_request(self, mock_add_job, mock_trigger_lambda):
        mock_env = Utility.environment.copy()
        mock_env['events']['executor']['type'] = EventExecutor.aws_lambda
        mock_env['events']['task_definition'][EventClass.model_training] = 'message_broadcast'

        def __mock_lambda_execution(*args, **kwargs):
            assert args == ('message_broadcast',
                            [{'name': 'BOT', 'value': 'test'}, {'name': 'USER', 'value': 'test_user'},
                             {'name': 'EVENT_ID', 'value': '6543212345678909876543'}])
            return {'StatusCode': 200, 'FunctionError': 'Unhandled',
                    'LogResult': 'U1RBUlQgUmVxdWVzdElkOiBlOTJiMWNjMC02MjcwLTQ0OWItOA3O=',
                    'ExecutedVersion': '$LATEST',
                    'Payload': {'response': 'task triggered'}}

        mock_trigger_lambda.side_effect = __mock_lambda_execution

        request_body = json.dumps(
            {"bot": "test", "user": "test_user", "event_id": "6543212345678909876543"}).encode('utf-8')
        response = self.fetch(f"/api/events/execute/{EventClass.message_broadcast}", method="POST", body=request_body)
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response.code, 200)
        self.assertEqual(response_json, {"data": {"StatusCode": 200, "FunctionError": "Unhandled",
                                                  "LogResult": "U1RBUlQgUmVxdWVzdElkOiBlOTJiMWNjMC02MjcwLTQ0OWItOA3O=",
                                                  "ExecutedVersion": "$LATEST",
                                                  "Payload": {"response": "task triggered"}}, "success": True,
                                         "error_code": 0, "message": None})

    def test_scheduled_event_request_not_allowed(self):
        request_body = json.dumps(
            {"bot": "test", "user": "test_user", "event_id": "6543212345678909876543"}).encode('utf-8')
        response = self.fetch(f"/api/events/execute/{EventClass.model_training}?is_scheduled=True", method="POST",
                              body=request_body)
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response.code, 200)
        self.assertEqual(response_json, {"data": None, "success": False,
                                         "error_code": 422,
                                         "message": "Scheduling is not allowed for 'model_training' event"})

    def test_scheduled_event_request_parameters_missing(self):
        request_body = json.dumps({"bot": "test", "user": "test_user"}).encode('utf-8')
        response = self.fetch(f"/api/events/execute/{EventClass.message_broadcast}?is_scheduled=True", method="POST",
                              body=request_body)
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response.code, 200)
        self.assertEqual(response_json, {"data": None, "success": False,
                                         "error_code": 422,
                                         "message": f'Missing {"event_id", "bot", "user", "cron_exp"} all or any from request body!'})

    @patch('kairon.events.scheduler.kscheduler.KScheduler.update_job', autospec=True)
    def test_update_scheduled_event_request(self, mock_update_job):
        request_body = json.dumps(
            {"bot": "test", "user": "test_user", "cron_exp": "* * * * *", "event_id": "6543212345678909876543"}).encode(
            'utf-8')
        response = self.fetch(f"/api/events/execute/{EventClass.message_broadcast}?is_scheduled=True", method="PUT",
                              body=request_body)
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response.code, 200)
        self.assertEqual(response_json, {"data": None, "success": True, "error_code": 0,
                                         "message": 'Scheduled event updated!'})

    def test_update_scheduled_event_request_not_allowed(self):
        request_body = json.dumps(
            {"bot": "test", "user": "test_user", "event_id": "6543212345678909876543"}).encode('utf-8')
        response = self.fetch(f"/api/events/execute/{EventClass.model_testing}?is_scheduled=True", method="PUT",
                              body=request_body)
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response.code, 200)
        self.assertEqual(response_json, {"data": None, "success": False,
                                         "error_code": 422,
                                         "message": "Scheduling is not allowed for 'model_testing' event"})

    def test_update_scheduled_event_request_missing_parameters(self):
        request_body = json.dumps({"bot": "test", "user": "test_user"}).encode('utf-8')
        response = self.fetch(f"/api/events/execute/{EventClass.message_broadcast}?is_scheduled=True", method="PUT",
                              body=request_body)
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response.code, 200)
        self.assertEqual(response_json, {"data": None, "success": False,
                                         "error_code": 422,
                                         "message": f'Missing {"event_id", "bot", "user", "cron_exp"} all or any from request body!'})

    def test_update_non_scheduled_event_request(self):
        request_body = json.dumps(
            {"bot": "test", "user": "test_user", "event_id": "6543212345678909876543"}).encode('utf-8')
        response = self.fetch(f"/api/events/execute/{EventClass.message_broadcast}?is_scheduled=False", method="PUT",
                              body=request_body)
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response.code, 200)
        self.assertEqual(response_json, {"data": None, "success": False,
                                         "error_code": 422,
                                         "message": "Updating non-scheduled event not supported!"})

    @patch('kairon.events.scheduler.kscheduler.KScheduler.delete_job', autospec=True)
    def test_delete_scheduled_event_request(self, mock_delet_job):
        response = self.fetch(
            f"/api/events/execute/{EventClass.message_broadcast}?is_scheduled=True&bot=test&user=test_user&event_id=6543212345678909876543",
            method="DELETE")
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response.code, 200)
        self.assertEqual(response_json, {"data": None, "success": True, "error_code": 0,
                                         "message": 'Scheduled event deleted!'})

    def test_delete_scheduled_event_request_not_allowed(self):
        response = self.fetch(
            f"/api/events/execute/{EventClass.data_importer}?is_scheduled=False&bot=test&user=test_user&event_id=6543212345678909876543",
            method="DELETE")
        response_json = json.loads(response.body.decode("utf8"))
        self.assertEqual(response.code, 200)
        self.assertEqual(response_json, {"data": None, "success": False,
                                         "error_code": 422, "message": "Updating non-scheduled event not supported!"})
