import os

import pytest
from mongoengine import connect

from kairon import Utility
from kairon.data_processor.constant import EVENT_STATUS, REQUIREMENTS
from kairon.importer.processor import DataImporterLogProcessor
from kairon.importer.data_objects import ValidationLogs
from kairon.exceptions import AppException


class TestDataImporterLogProcessor:

    @pytest.fixture(scope='session', autouse=True)
    def init(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_evironment()
        connect(host=Utility.environment["database"]['url'])
    
    def test_add_log(self):
        bot = 'test'
        user = 'test'
        DataImporterLogProcessor.add_log(bot, user, is_data_uploaded=False)
        log = ValidationLogs.objects(bot=bot).get().to_mongo().to_dict()
        assert not log.get('intents')
        assert not log.get('stories')
        assert not log.get('utterances')
        assert not log.get('http_actions')
        assert not log.get('training_examples')
        assert not log.get('domain')
        assert not log.get('config')
        assert not log.get('exception')
        assert not log['is_data_uploaded']
        assert log['start_timestamp']
        assert not log.get('end_timestamp')
        assert not log.get('validation_status')
        assert log['event_status'] == EVENT_STATUS.INITIATED.value

    def test_add_log_exception(self):
        bot = 'test'
        user = 'test'
        DataImporterLogProcessor.add_log(bot, user,
                                         exception='Validation failed',
                                         status='Failure',
                                         event_status=EVENT_STATUS.FAIL.value)
        log = ValidationLogs.objects(bot=bot).get().to_mongo().to_dict()
        assert not log.get('intents')
        assert not log.get('stories')
        assert not log.get('utterances')
        assert not log.get('http_actions')
        assert not log.get('training_examples')
        assert not log.get('domain')
        assert not log.get('config')
        assert not log.get('files_received')
        assert log.get('exception') == 'Validation failed'
        assert not log['is_data_uploaded']
        assert log['start_timestamp']
        assert log.get('end_timestamp')
        assert log.get('status') == 'Failure'
        assert log['event_status'] == EVENT_STATUS.FAIL.value

    def test_get_files_received_empty(self):
        bot = 'test'
        files = DataImporterLogProcessor.get_files_received_for_latest_event(bot)
        assert isinstance(files, set)
        assert not files

    def test_add_log_success(self):
        bot = 'test'
        user = 'test'
        DataImporterLogProcessor.add_log(bot, user, files_received=list(REQUIREMENTS.copy()), is_data_uploaded=False)
        DataImporterLogProcessor.add_log(bot, user,
                                         status='Success',
                                         event_status=EVENT_STATUS.COMPLETED.value)
        log = list(DataImporterLogProcessor.get_logs(bot))
        assert not log[0].get('intents')
        assert not log[0].get('stories')
        assert not log[0].get('utterances')
        assert not log[0].get('http_actions')
        assert not log[0].get('training_examples')
        assert not log[0].get('domain')
        assert not log[0].get('config')
        assert not log[0].get('exception')
        assert not log[0]['is_data_uploaded']
        assert log[0]['start_timestamp']
        assert log[0].get('end_timestamp')
        assert all(file in log[0]['files_received'] for file in REQUIREMENTS)
        assert log[0].get('status') == 'Success'
        assert log[0]['event_status'] == EVENT_STATUS.COMPLETED.value

    def test_get_files_received(self):
        bot = 'test'
        files = DataImporterLogProcessor.get_files_received_for_latest_event(bot)
        assert isinstance(files, set)
        assert files == REQUIREMENTS

    def test_is_event_in_progress_false(self):
        bot = 'test'
        assert not DataImporterLogProcessor.is_event_in_progress(bot)

    def test_is_event_in_progress_true(self):
        bot = 'test'
        user = 'test'
        DataImporterLogProcessor.add_log(bot, user, is_data_uploaded=False)
        assert DataImporterLogProcessor.is_event_in_progress(bot, False)

        with pytest.raises(AppException):
            DataImporterLogProcessor.is_event_in_progress(bot)

    def test_get_logs(self):
        bot = 'test'
        logs = list(DataImporterLogProcessor.get_logs(bot))
        assert len(logs) == 3

    def test_is_limit_exceeded(self, monkeypatch):
        monkeypatch.setitem(Utility.environment['model']['data_importer'], "limit_per_day", 3)
        bot = 'test'
        assert DataImporterLogProcessor.is_limit_exceeded(bot, False)

    def test_is_limit_exceeded_exception(self, monkeypatch):
        monkeypatch.setitem(Utility.environment['model']['data_importer'], "limit_per_day", 3)
        bot = 'test'
        with pytest.raises(AppException):
            assert DataImporterLogProcessor.is_limit_exceeded(bot)

    def test_is_limit_exceeded_false(self, monkeypatch):
        monkeypatch.setitem(Utility.environment['model']['data_importer'], "limit_per_day", 4)
        bot = 'test'
        assert not DataImporterLogProcessor.is_limit_exceeded(bot)
