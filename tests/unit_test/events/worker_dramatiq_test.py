import os
from unittest.mock import patch

import pytest
from dramatiq import Worker
from loguru import logger

from kairon import Utility
from kairon.events.executors.standalone import StandaloneExecutor
from kairon.shared.constants import EventClass
from kairon.shared.events.broker.factory import BrokerFactory


def mock_execute_failure(*args, **kwargs):
    logger.debug(f'args: {args}, kwargs: {kwargs}')
    logger.debug("raising exception")
    raise Exception("Failed to execute task")


class TestDramatiqWorker:

    @pytest.fixture(scope='class', autouse=True)
    def init(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()

    @patch('kairon.events.definitions.multilingual.MultilingualEvent.execute', autospec=True)
    @patch('kairon.events.definitions.data_importer.TrainingDataImporterEvent.execute', autospec=True)
    @patch('kairon.events.definitions.history_delete.DeleteHistoryEvent.execute', autospec=True)
    @patch('kairon.events.definitions.model_testing.ModelTestingEvent.execute', autospec=True)
    @patch('kairon.events.definitions.model_training.ModelTrainingEvent.execute', autospec=True)
    @patch('kairon.shared.events.broker.mongo.Database', autospec=True)
    @patch('kairon.shared.events.broker.mongo.MongoClient', autospec=True)
    def test_dramatiq_worker(self, mock_mongo, mock_db, mock_a, mock_b, mock_c, mock_d, mock_e):
        from dramatiq.brokers.stub import StubBroker

        broker = StubBroker()

        with patch('dramatiq_mongodb.MongoDBBroker.__new__') as mock_broker:
            mock_broker.return_value = broker
            mongo_broker = BrokerFactory.get_instance()
            mongo_broker.declare_actors({
                StandaloneExecutor().execute_task: Utility.environment['events']['queue']['name']
            })
            mongo_broker.enqueue(EventClass.model_training, **{"bot": "test", "user": "test_user"})
            mongo_broker.enqueue(EventClass.model_testing, **{"bot": "test", "user": "test_user"})
            mongo_broker.enqueue(EventClass.data_importer, **{"bot": "test", "user": "test_user"})
            mongo_broker.enqueue(EventClass.delete_history, **{"bot": "test", "user": "test_user"})

            assert len(mongo_broker.get_broker().queues['kairon_events'].queue) >= 4
            worker = Worker(mongo_broker.get_broker(), worker_timeout=10)
            worker.start()
            mongo_broker.get_broker().join("kairon_events", fail_fast=True)
            worker.join()
            assert len(mongo_broker.get_broker().queues['kairon_events'].queue) == 0
            worker.stop()

    @patch('kairon.events.definitions.multilingual.MultilingualEvent.execute', new=mock_execute_failure)
    @patch('kairon.events.definitions.data_importer.TrainingDataImporterEvent.execute', new=mock_execute_failure)
    @patch('kairon.events.definitions.history_delete.DeleteHistoryEvent.execute', new=mock_execute_failure)
    @patch('kairon.events.definitions.model_testing.ModelTestingEvent.execute', new=mock_execute_failure)
    @patch('kairon.events.definitions.model_training.ModelTrainingEvent.execute', new=mock_execute_failure)
    @patch('kairon.shared.events.broker.mongo.Database', autospec=True)
    @patch('kairon.shared.events.broker.mongo.MongoClient', autospec=True)
    def test_dramatiq_worker_failure(self, mock_mongo, mock_db):
        from dramatiq.brokers.stub import StubBroker

        broker = StubBroker()
        with patch('dramatiq_mongodb.MongoDBBroker.__new__') as mock_broker:
            mock_broker.return_value = broker
            mongo_broker = BrokerFactory.get_instance()
            mongo_broker.declare_actors({
                StandaloneExecutor().execute_task: Utility.environment['events']['queue']['name']
            })
            mongo_broker.enqueue(EventClass.model_training, **{"bot": "test", "user": "test_user"})
            mongo_broker.enqueue(EventClass.model_testing, **{"bot": "test", "user": "test_user"})
            mongo_broker.enqueue(EventClass.data_importer, **{"bot": "test", "user": "test_user"})
            mongo_broker.enqueue(EventClass.delete_history, **{"bot": "test", "user": "test_user"})

            assert len(mongo_broker.get_broker().queues['kairon_events'].queue) == 4
            worker = Worker(mongo_broker.get_broker(), worker_timeout=10)
            worker.start()
            with pytest.raises(Exception, match='Failed to execute task'):
                mongo_broker.get_broker().join("kairon_events", fail_fast=True)
                worker.join()
                assert len(mongo_broker.get_broker().queues['kairon_events'].queue) == 0
                worker.stop()

    @patch('kairon.shared.events.broker.mongo.Database', autospec=True)
    @patch('kairon.shared.events.broker.mongo.MongoClient', autospec=True)
    def test_broker_init(self, mock_mongo, mock_db):
        from dramatiq.brokers.stub import StubBroker

        broker = StubBroker()
        with patch('dramatiq_mongodb.MongoDBBroker.__new__') as mock_broker:
            mock_broker.return_value = broker

            from kairon.events.broker import broker
            from dramatiq import Actor

            assert list(broker.get_broker().actors.keys()) == ['execute_task']
            assert isinstance(broker.get_broker().actors['execute_task'], Actor)
            actor_function = broker.get_broker().actors['execute_task']
            assert actor_function.actor_name == 'execute_task'
            assert actor_function.queue_name == 'kairon_events'
