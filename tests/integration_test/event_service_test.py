from unittest import mock

from dramatiq.brokers.stub import StubBroker
from loguru import logger
from tornado.test.testing_test import AsyncHTTPTestCase

from kairon.events.server import make_app
from kairon.shared.constants import EventClass, EventExecutor
from kairon.shared.utils import Utility
from mongoengine import connect
import json
from mock import patch
import os

os.environ["system_file"] = "./tests/testing_data/system.yaml"
os.environ['ASYNC_TEST_TIMEOUT'] = "360"
Utility.load_environment()
connect(**Utility.mongoengine_connection())


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
                request_body = json.dumps({"bot": "test", "user": "test_user", "token": "asdfghjk23456789"}).encode('utf-8')
                response = self.fetch(f"/api/events/execute/{EventClass.model_training}", method="POST", body=request_body)
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
            assert args == ('model_training', [{'name': 'BOT', 'value': 'test_bot'}, {'name': 'USER', 'value': 'test_user'},
                                               {'name': 'TOKEN', 'value': 'asdfghjk23456789'}])
            return {'StatusCode': 400, 'FunctionError': 'Unhandled',
                                                   'LogResult': 'U1RBUlQgUmVxdWVzdElkOiBlOTJiMWNjMC02MjcwLTQ0OWItOA3O=',
                                                   'ExecutedVersion': '$LATEST',
                                                   'Payload': {'response': 'Failed to trigger task'}}

        with patch.dict(Utility.environment, mock_env):
            with mock.patch("kairon.shared.cloud.utils.CloudUtility.trigger_lambda") as mock_trigger:
                mock_trigger.side_effect = __mock_lambda_execution
                request_body = json.dumps({"bot": "test_bot", "user": "test_user", "token": "asdfghjk23456789"}).encode('utf-8')
                response = self.fetch(f"/api/events/execute/{EventClass.model_training}", method="POST", body=request_body)
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
                request_body = json.dumps({"bot": "test", "user": "test_user", "token": "asdfghjk23456789"}).encode('utf-8')
                response = self.fetch(f"/api/events/execute/{EventClass.model_training}", method="POST", body=request_body)
                response_json = json.loads(response.body.decode("utf8"))
                self.assertEqual(response.code, 200)
                self.assertRegexpMatches(response_json['data'], '{"queue_name": "kairon_events", "actor_name": "execute_task", "args": \["model_training", {"bot": "test", "user": "test_user", "token": "asdfghjk23456789"}], "kwargs": {}, "options": {}, *')
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
                self.assertEqual(response_json, {"data": None, "success": False, "error_code": 422, "message": "Failed to add message to mongo broker"})

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
                self.assertEqual(response_json, {'data': 'Task Spawned!', 'error_code': 0, 'message': None, 'success': True})

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
