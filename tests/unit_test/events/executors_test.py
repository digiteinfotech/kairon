import ujson as json
import os
import re
from unittest.mock import patch
from mongoengine import connect

import pytest
from loguru import logger
from dramatiq.brokers.stub import StubBroker
from kairon import Utility
from kairon.events.definitions.data_importer import TrainingDataImporterEvent
from kairon.events.definitions.factory import EventFactory
from kairon.events.definitions.history_delete import DeleteHistoryEvent
from kairon.events.definitions.model_testing import ModelTestingEvent
from kairon.events.definitions.model_training import ModelTrainingEvent
from kairon.events.definitions.multilingual import MultilingualEvent
from kairon.events.executors.dramatiq import DramatiqExecutor
from kairon.events.executors.factory import ExecutorFactory
from kairon.events.executors.lamda import LambdaExecutor
from kairon.events.executors.standalone import StandaloneExecutor
from kairon.exceptions import AppException
from kairon.shared.constants import EventClass, EventExecutor
from kairon.shared.data.constant import TASK_TYPE
from kairon.shared.events.broker.factory import BrokerFactory
from kairon.shared.events.broker.mongo import MongoBroker


def _mock_broker_connection_error(*args, **kwargs):
    raise Exception("Failed to connect to broker")


class TestExecutors:
    broker = StubBroker()

    @pytest.fixture(scope='class', autouse=True)
    def init(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()

    @pytest.fixture(autouse=True, scope="class")
    def setup(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        connect(**Utility.mongoengine_connection(Utility.environment["database"]["url"]))
        from kairon.shared.account.processor import AccountProcessor
        AccountProcessor.load_system_properties()

    @patch('kairon.shared.events.broker.mongo.Database', autospec=True)
    @patch('kairon.shared.events.broker.mongo.MongoClient', autospec=True)
    def test_dramatiq_executor_model_training(self, mock_mongo_client, mock_database):
        mock_env = Utility.environment.copy()
        mock_env['events']['executor']['type'] = 'dramatiq'
        mock_env['events']['task_definition'][EventClass.model_training] = 'train-model'
        with patch.dict(Utility.environment, mock_env):
            with patch('dramatiq_mongodb.MongoDBBroker.__new__') as mock_broker:
                mock_broker.return_value = TestExecutors.broker
                resp = DramatiqExecutor().execute_task(EventClass.model_training,
                                                       {"bot": "test", "user": "test_user"},
                                                       task_type=TASK_TYPE.EVENT.value)
                resp = json.loads(resp)
                resp.pop('message_id')
                resp.pop('message_timestamp')
                assert resp == {'queue_name': 'kairon_events', 'actor_name': 'execute_task',
                                'args': ['model_training', {'bot': 'test', 'user': 'test_user'}],
                                'kwargs': {}, 'options': {}}

                from kairon.shared.events.data_objects import ExecutorLogs
                logs = ExecutorLogs.objects(task_type='Event', data={'bot': 'test', 'user': 'test_user'})
                log = logs[0].to_mongo().to_dict()
                log['response'].pop("message_timestamp")
                log['response'].pop("message_id")
                assert log['task_type'] == 'Event'
                assert log['event_class'] == 'model_training'
                assert log['data'] == {'bot': 'test', 'user': 'test_user'}
                assert log['status'] == 'Completed'
                assert log['response'] == {
                    'queue_name': 'kairon_events',
                    'actor_name': 'execute_task',
                    'args': ['model_training', {'bot': 'test', 'user': 'test_user'}],
                    'kwargs': {},
                    'options': {},
                }
                assert log['executor_log_id']
                assert log['from_executor'] is True
                assert log['elapsed_time']

    @patch('kairon.shared.events.broker.mongo.Database', autospec=True)
    @patch('kairon.shared.events.broker.mongo.MongoClient', autospec=True)
    def test_dramatiq_executor_model_testing(self, mock_mongo_client, mock_database):
        mock_env = Utility.environment.copy()
        mock_env['events']['executor']['type'] = 'dramatiq'
        mock_env['events']['task_definition'][EventClass.model_testing] = 'train-model'
        with patch.dict(Utility.environment, mock_env):
            with patch('dramatiq_mongodb.MongoDBBroker.__new__') as mock_broker:
                mock_broker.return_value = TestExecutors.broker
                resp = DramatiqExecutor().execute_task(EventClass.model_testing,
                                                       {"bot": "test", "user": "test_user"},
                                                       task_type=TASK_TYPE.EVENT.value)
                resp = json.loads(resp)
                resp.pop('message_id')
                resp.pop('message_timestamp')
                assert resp == {'queue_name': 'kairon_events', 'actor_name': 'execute_task',
                                'args': ['model_testing', {'bot': 'test', 'user': 'test_user'}],
                                'kwargs': {}, 'options': {}}

                from kairon.shared.events.data_objects import ExecutorLogs
                logs = ExecutorLogs.objects(task_type='Event', data={'bot': 'test', 'user': 'test_user'})
                log = logs[1].to_mongo().to_dict()
                log['response'].pop("message_timestamp")
                log['response'].pop("message_id")
                assert log['task_type'] == 'Event'
                assert log['event_class'] == 'model_testing'
                assert log['data'] == {'bot': 'test', 'user': 'test_user'}
                assert log['status'] == 'Completed'
                assert log['response'] == {
                    'queue_name': 'kairon_events',
                    'actor_name': 'execute_task',
                    'args': ['model_testing', {'bot': 'test', 'user': 'test_user'}],
                    'kwargs': {},
                    'options': {},
                }
                assert log['from_executor'] is True
                assert log['executor_log_id']
                assert log['elapsed_time']

    @patch('kairon.shared.events.broker.mongo.Database', autospec=True)
    @patch('kairon.shared.events.broker.mongo.MongoClient', autospec=True)
    def test_dramatiq_executor_data_importer(self, mock_mongo_client, mock_database):
        mock_env = Utility.environment.copy()
        mock_env['events']['executor']['type'] = 'dramatiq'
        mock_env['events']['task_definition'][EventClass.data_importer] = 'train-model'
        with patch.dict(Utility.environment, mock_env):
            with patch('dramatiq_mongodb.MongoDBBroker.__new__') as mock_broker:
                mock_broker.return_value = TestExecutors.broker
                resp = DramatiqExecutor().execute_task(EventClass.data_importer,
                                                       {"bot": "test", "user": "test_user"},
                                                       task_type=TASK_TYPE.EVENT.value)
                resp = json.loads(resp)
                resp.pop('message_id')
                resp.pop('message_timestamp')
                assert resp == {'queue_name': 'kairon_events', 'actor_name': 'execute_task',
                                'args': ['data_importer', {'bot': 'test', 'user': 'test_user'}],
                                'kwargs': {}, 'options': {}}

                from kairon.shared.events.data_objects import ExecutorLogs
                logs = ExecutorLogs.objects(task_type='Event', data={'bot': 'test', 'user': 'test_user'})
                log = logs[2].to_mongo().to_dict()
                log['response'].pop("message_timestamp")
                log['response'].pop("message_id")
                assert log['task_type'] == 'Event'
                assert log['event_class'] == 'data_importer'
                assert log['data'] == {'bot': 'test', 'user': 'test_user'}
                assert log['status'] == 'Completed'
                assert log['response'] == {
                    'queue_name': 'kairon_events',
                    'actor_name': 'execute_task',
                    'args': ['data_importer', {'bot': 'test', 'user': 'test_user'}],
                    'kwargs': {},
                    'options': {},
                }
                assert log['from_executor'] is True
                assert log['executor_log_id']
                assert log['elapsed_time']

    @patch('kairon.shared.events.broker.mongo.Database', autospec=True)
    @patch('kairon.shared.events.broker.mongo.MongoClient', autospec=True)
    def test_dramatiq_executor_delete_history(self, mock_mongo_client, mock_database):
        mock_env = Utility.environment.copy()
        mock_env['events']['executor']['type'] = 'dramatiq'
        mock_env['events']['task_definition'][EventClass.delete_history] = 'train-model'
        with patch.dict(Utility.environment, mock_env):
            with patch('dramatiq_mongodb.MongoDBBroker.__new__') as mock_broker:
                mock_broker.return_value = TestExecutors.broker
                resp = DramatiqExecutor().execute_task(EventClass.delete_history,
                                                       {"bot": "test", "user": "test_user"},
                                                       task_type=TASK_TYPE.EVENT.value)
                resp = json.loads(resp)
                resp.pop('message_id')
                resp.pop('message_timestamp')
                assert resp == {'queue_name': 'kairon_events', 'actor_name': 'execute_task',
                                'args': ['delete_history', {'bot': 'test', 'user': 'test_user'}], 'kwargs': {},
                                'options': {}}
                from kairon.shared.events.data_objects import ExecutorLogs
                logs = ExecutorLogs.objects(task_type='Event', data={'bot': 'test', 'user': 'test_user'})
                log = logs[3].to_mongo().to_dict()
                log['response'].pop("message_timestamp")
                log['response'].pop("message_id")
                assert log['task_type'] == 'Event'
                assert log['event_class'] == 'delete_history'
                assert log['data'] == {'bot': 'test', 'user': 'test_user'}
                assert log['status'] == 'Completed'
                assert log['response'] == {
                    'queue_name': 'kairon_events',
                    'actor_name': 'execute_task',
                    'args': ['delete_history', {'bot': 'test', 'user': 'test_user'}],
                    'kwargs': {},
                    'options': {},
                }
                assert log['executor_log_id']
                assert log['from_executor'] is True
                assert log['elapsed_time']

    @patch('kairon.shared.events.broker.mongo.Message', new=_mock_broker_connection_error)
    @patch('kairon.shared.events.broker.mongo.Database', autospec=True)
    @patch('kairon.shared.events.broker.mongo.MongoClient', autospec=True)
    def test_dramatiq_executor_failure(self, mock_mongo_client, mock_database):
        mock_env = Utility.environment.copy()
        mock_env['events']['executor']['type'] = 'dramatiq'
        mock_env['events']['task_definition'][EventClass.delete_history] = 'train-model'
        with patch.dict(Utility.environment, mock_env):
            with patch('dramatiq_mongodb.MongoDBBroker.__new__') as mock_broker:
                mock_broker.return_value = TestExecutors.broker

                with pytest.raises(Exception, match="Failed to add task to queue: Failed to connect to broker"):
                    DramatiqExecutor().execute_task(EventClass.delete_history,
                                                    {"bot": "test", "user": "test_user"},
                                                    task_type=TASK_TYPE.EVENT.value)

        from kairon.shared.events.data_objects import ExecutorLogs
        logs = ExecutorLogs.objects(task_type='Event', data={'bot': 'test', 'user': 'test_user'})
        log = logs[4].to_mongo().to_dict()
        assert log['task_type'] == 'Event'
        assert log['event_class'] == 'delete_history'
        assert log['data'] == {'bot': 'test', 'user': 'test_user'}
        assert log['status'] == 'Fail'
        assert log['response'] == {}
        assert log['exception'] == "Failed to add task to queue: Failed to connect to broker"
        assert log['from_executor'] is True
        assert log['executor_log_id']
        assert log['elapsed_time']

    def test_standalone_executor(self, monkeypatch):
        mock_env = Utility.environment.copy()
        mock_env['events']['executor']['type'] = 'standalone'
        mock_env['events']['task_definition'][EventClass.model_training] = 'train-model'

        def _mock_execute(*args, **kwargs):
            logger.debug(f"args: {args}, kwargs: {kwargs}")
            assert kwargs == {"bot": "test", "user": "test_user"}

        monkeypatch.setattr(ModelTrainingEvent, "execute", _mock_execute)

        with patch.dict(Utility.environment, mock_env):
            resp = StandaloneExecutor().execute_task(EventClass.model_training,
                                                     {"bot": "test", "user": "test_user"},
                                                     task_type=TASK_TYPE.EVENT.value)
            assert resp == 'Task Spawned!'

        from kairon.shared.events.data_objects import ExecutorLogs
        logs = ExecutorLogs.objects(task_type='Event', data={'bot': 'test', 'user': 'test_user'})
        log = logs[5].to_mongo().to_dict()
        assert log['task_type'] == 'Event'
        assert log['event_class'] == 'model_training'
        assert log['data'] == {'bot': 'test', 'user': 'test_user'}
        assert log['status'] == 'Completed'
        assert log['response'] == {'message': 'Task Spawned!'}
        assert log['executor_log_id']
        assert log['from_executor'] is True
        assert log['elapsed_time']

    def test_event_factory(self):
        assert EventFactory.get_instance(EventClass.model_training) == ModelTrainingEvent
        assert EventFactory.get_instance(EventClass.model_testing) == ModelTestingEvent
        assert EventFactory.get_instance(EventClass.data_importer) == TrainingDataImporterEvent
        assert EventFactory.get_instance(EventClass.delete_history) == DeleteHistoryEvent
        assert EventFactory.get_instance(EventClass.multilingual) == MultilingualEvent

    def test_event_factory_failure(self):
        event_class = None
        valid_events = [ev.value for ev in EventClass]
        with pytest.raises(AppException, match=re.escape(f"{event_class} is not a valid event. Accepted event types: {valid_events}")):
            EventFactory.get_instance(event_class)
        event_class = "modeltesting"
        with pytest.raises(AppException, match=re.escape(f"{event_class} is not a valid event. Accepted event types: {valid_events}")):
            EventFactory.get_instance(event_class)

    def test_executor_factory(self, monkeypatch):
        monkeypatch.setitem(Utility.environment['events']['executor'], "type", "aws_lambda")
        assert isinstance(ExecutorFactory.get_executor(), LambdaExecutor)

        monkeypatch.setitem(Utility.environment['events']['executor'], "type", "dramatiq")
        assert isinstance(ExecutorFactory.get_executor(), DramatiqExecutor)

        monkeypatch.setitem(Utility.environment['events']['executor'], "type", "standalone")
        assert isinstance(ExecutorFactory.get_executor(), StandaloneExecutor)

    def test_executor_factory_failure(self, monkeypatch):
        valid_executors = [ex.value for ex in EventExecutor]
        monkeypatch.setitem(Utility.environment['events']['executor'], "type", None)
        with pytest.raises(AppException, match=re.escape(f"Executor type not configured in system.yaml. Valid types: {valid_executors}")):
            ExecutorFactory.get_executor()

        monkeypatch.setitem(Utility.environment['events']['executor'], "type", "Standalone")
        with pytest.raises(AppException,
                           match=re.escape(f"Executor type not configured in system.yaml. Valid types: {valid_executors}")):
            ExecutorFactory.get_executor()

    @patch('kairon.shared.events.broker.mongo.Database', autospec=True)
    @patch('kairon.shared.events.broker.mongo.MongoClient', autospec=True)
    def test_broker_factory(self,  mock_mongo_client, mock_database):
        with patch('dramatiq_mongodb.MongoDBBroker.__new__') as mock_broker:
            mock_broker.return_value = TestExecutors.broker
            assert isinstance(BrokerFactory.get_instance(), MongoBroker)

    def test_broker_factory_failure(self, monkeypatch):
        monkeypatch.setitem(Utility.environment['events']['queue'], "type", "redis")
        with pytest.raises(AppException, match=re.escape("Not a valid broker type. Accepted types: ['mongo']")):
            BrokerFactory.get_instance()
