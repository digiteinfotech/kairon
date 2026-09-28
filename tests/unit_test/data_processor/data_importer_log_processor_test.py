import os

import pytest
from mongoengine import connect

from kairon.shared.data.data_objects import BotSettings
from kairon.shared.utils import Utility
from kairon.shared.data.constant import EVENT_STATUS, REQUIREMENTS, COMPONENT_COUNT, STATUSES
from kairon.shared.importer.processor import DataImporterLogProcessor
from kairon.shared.importer.data_objects import ValidationLogs
from kairon.exceptions import AppException
from mongomock import MongoClient


class TestDataImporterLogProcessor:

    @pytest.fixture(scope='session', autouse=True)
    def init(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))
    
    def test_add_log(self):
        bot = 'test'
        user = 'test'
        DataImporterLogProcessor.add_log(bot, user, is_data_uploaded=False)
        log = ValidationLogs.objects(bot=bot).get().to_mongo().to_dict()
        assert not log.get('intents').get('data')
        assert not log.get('stories').get('data')
        assert not log.get('utterances').get('data')
        assert not log.get('actions')
        assert not log.get('training_examples').get('data')
        assert not log.get('domain').get('data')
        assert not log.get('config').get('data')
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
                                         status=STATUSES.FAIL.value,
                                         event_status=EVENT_STATUS.FAIL.value)
        log = ValidationLogs.objects(bot=bot).get().to_mongo().to_dict()
        assert not log.get('intents').get('data')
        assert not log.get('stories').get('data')
        assert not log.get('utterances').get('data')
        assert not log.get('actions')
        assert not log.get('training_examples').get('data')
        assert not log.get('domain').get('data')
        assert not log.get('config').get('data')
        assert not log.get('files_received')
        assert log.get('exception') == 'Validation failed'
        assert not log['is_data_uploaded']
        assert log['start_timestamp']
        assert log.get('end_timestamp')
        assert log.get('status') == STATUSES.FAIL.value
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
                                         status=STATUSES.SUCCESS.value,
                                         event_status=EVENT_STATUS.COMPLETED.value)
        log = list(DataImporterLogProcessor.get_logs(bot))
        assert not log[0].get('intents').get('data')
        assert not log[0].get('stories').get('data')
        assert not log[0].get('utterances').get('data')
        assert not log[0].get('actions')
        assert not log[0].get('training_examples').get('data')
        assert not log[0].get('domain').get('data')
        assert not log[0].get('config').get('data')
        assert not log[0].get('exception')
        assert not log[0]['is_data_uploaded']
        assert log[0]['start_timestamp']
        assert log[0].get('end_timestamp')
        assert all(file in log[0]['files_received'] for file in REQUIREMENTS)
        assert log[0].get('status') == STATUSES.SUCCESS.value
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

    def test_update_log(self):
        bot = 'test'
        user = 'test'
        DataImporterLogProcessor.add_log(bot, user, is_data_uploaded=False)
        log = next(DataImporterLogProcessor.get_logs(bot))
        assert not log.get('intents').get('data')
        assert not log.get('stories').get('data')
        assert not log.get('utterances').get('data')
        assert not log.get('actions')
        assert not log.get('training_examples').get('data')
        assert not log.get('domain').get('data')
        assert not log.get('config').get('data')
        assert not log.get('exception')
        assert not log['is_data_uploaded']
        assert log['start_timestamp']
        assert not log.get('end_timestamp')
        assert not log.get('validation_status')
        assert log['event_status'] == EVENT_STATUS.INITIATED.value
        count = COMPONENT_COUNT.copy()
        count['http_action'] = 6
        count['domain']['intents'] = 12
        summary = {'intents': ['Intent not added to domain'], 'config': ['Invalid component']}
        DataImporterLogProcessor.update_summary(bot, user, count, summary, STATUSES.FAIL.value, EVENT_STATUS.COMPLETED.value)
        log = next(DataImporterLogProcessor.get_logs(bot))
        assert log.get('intents').get('data') == ['Intent not added to domain']
        assert not log.get('stories').get('data')
        assert not log.get('utterances').get('data')
        assert not log.get('actions')
        assert not log.get('training_examples').get('data')
        assert not log.get('domain').get('data')
        assert log.get('config').get('data') == ['Invalid component']
        assert not log.get('exception')
        assert not log['is_data_uploaded']
        assert log['start_timestamp']
        assert log.get('end_timestamp')
        assert log.get('status') == STATUSES.FAIL.value
        assert log['event_status'] == EVENT_STATUS.COMPLETED.value

    def test_update_log_create_new(self):
        bot = 'test'
        user = 'test'
        count = COMPONENT_COUNT.copy()
        count['http_action'] = 6
        count['domain']['intents'] = 12
        summary = {'intents': ['Intent not added to domain'], 'config': ['Invalid component']}
        DataImporterLogProcessor.update_summary(bot, user, count, summary)
        log = next(DataImporterLogProcessor.get_logs(bot))
        assert log.get('intents').get('data') == ['Intent not added to domain']
        assert not log.get('stories').get('data')
        assert not log.get('utterances').get('data')
        assert not log.get('actions')
        assert not log.get('training_examples').get('data')
        assert not log.get('domain').get('data')
        assert log.get('config').get('data') == ['Invalid component']
        assert not log.get('exception')
        assert not log['is_data_uploaded']
        assert log['start_timestamp']
        assert log.get('end_timestamp')
        assert not log.get('validation_status')
        assert log['event_status'] == EVENT_STATUS.COMPLETED.value

    def test_is_limit_exceeded_exception(self, monkeypatch):
        bot = 'test'
        try:
            bot_settings = BotSettings.objects(bot=bot).get()
            bot_settings.data_importer_limit_per_day = 0
        except:
            bot_settings = BotSettings(bot=bot, data_importer_limit_per_day=0, user="test")
        bot_settings.save()
        with pytest.raises(AppException):
            assert DataImporterLogProcessor.is_limit_exceeded(bot)

    def test_is_limit_exceeded(self, monkeypatch):
        bot = 'test'
        bot_settings = BotSettings.objects(bot=bot).get()
        bot_settings.data_importer_limit_per_day=3
        bot_settings.save()
        assert DataImporterLogProcessor.is_limit_exceeded(bot, False)

    def test_is_limit_exceeded_false(self, monkeypatch):
        bot = 'test'
        bot_settings = BotSettings.objects(bot=bot).get()
        bot_settings.data_importer_limit_per_day = 6
        bot_settings.save()
        assert not DataImporterLogProcessor.is_limit_exceeded(bot)
