import os

import pytest
from mongoengine import connect

from kairon.shared.content_importer.content_processor import ContentImporterLogProcessor
from kairon.shared.content_importer.data_objects import ContentValidationLogs
from kairon.shared.data.constant import EVENT_STATUS, REQUIREMENTS, COMPONENT_COUNT, STATUSES
from kairon.shared.data.data_objects import BotSettings
from kairon.shared.utils import Utility
from kairon.exceptions import AppException


class TestContentImporterLogProcessor:

    @pytest.fixture(scope='session', autouse=True)
    def init(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))

    def test_add_log(self):
        bot = 'test'
        user = 'test'
        table_name = 'test_table'
        ContentImporterLogProcessor.add_log(bot, user, is_data_uploaded=False, table = table_name)
        log = ContentValidationLogs.objects(bot=bot).get().to_mongo().to_dict()
        assert not log.get('exception')
        assert not log['is_data_uploaded']
        assert log['table']
        assert log['start_timestamp']
        assert not log.get('end_timestamp')
        assert not log.get('validation_errors')
        assert not log.get('file_received')
        assert log['event_status'] == EVENT_STATUS.INITIATED.value

    def test_add_log_exception(self):
        bot = 'test'
        user = 'test'
        table_name = 'test_table'
        ContentImporterLogProcessor.add_log(bot, user,
                                            table=table_name,
                                         exception='Validation failed',
                                         status=STATUSES.FAIL.value,
                                         event_status=EVENT_STATUS.FAIL.value)
        log = ContentValidationLogs.objects(bot=bot).get().to_mongo().to_dict()
        assert log.get('exception') == 'Validation failed'
        assert not log['is_data_uploaded']
        assert log['table']
        assert log['start_timestamp']
        assert log.get('end_timestamp')
        assert not log.get('validation_errors')
        assert not log.get('files_received')
        assert log.get('status') == STATUSES.FAIL.value
        assert log['event_status'] == EVENT_STATUS.FAIL.value

    def test_add_log_validation_errors(self):
        bot = 'test'
        user = 'test'
        ContentImporterLogProcessor.add_log(bot, user,
                                         exception='Validation failed',
                                         status=STATUSES.FAIL.value,
                                         event_status=EVENT_STATUS.FAIL.value,
                                         validation_errors= {
                                            "Header mismatch": "Expected headers ['order_id', 'order_priority', 'sales', 'profit'] but found ['order_id', 'order_priority', 'revenue', 'sales'].",
                                            "Missing columns": "{'profit'}.",
                                            "Extra columns": "{'revenue'}."
                                        })
        log = list(ContentImporterLogProcessor.get_logs(bot))
        assert log[0].get('exception') == 'Validation failed'
        assert not log[0]['table']
        assert not log[0]['is_data_uploaded']
        assert log[0]['start_timestamp']
        assert log[0].get('end_timestamp')
        assert log[0].get('validation_errors')
        assert not log[0]['file_received']
        assert log[0].get('status') == STATUSES.FAIL.value
        assert log[0]['event_status'] == EVENT_STATUS.FAIL.value

    def test_get_files_received_empty(self):
        bot = 'test'
        file = ContentImporterLogProcessor.get_file_received_for_latest_event(bot)
        assert not file

    def test_add_log_success(self):
        bot = 'test'
        user = 'test'
        table_name = 'test_table'
        ContentImporterLogProcessor.add_log(bot, user, table=table_name, file_received= "Salesstore.csv", is_data_uploaded=False)
        ContentImporterLogProcessor.add_log(bot, user,
                                         status=STATUSES.SUCCESS.value,
                                         event_status=EVENT_STATUS.COMPLETED.value)
        log = list(ContentImporterLogProcessor.get_logs(bot))
        assert not log[0].get('exception')
        assert not log[0]['is_data_uploaded']
        assert log[0]['table']
        assert log[0]['start_timestamp']
        assert log[0].get('end_timestamp')
        assert log[0]['file_received'] ==  "Salesstore.csv"
        assert log[0].get('status') == STATUSES.SUCCESS.value
        assert log[0]['event_status'] == EVENT_STATUS.COMPLETED.value

    def test_get_files_received(self):
        bot = 'test'
        files = ContentImporterLogProcessor.get_file_received_for_latest_event(bot)
        assert files == "Salesstore.csv"

    def test_is_event_in_progress_false(self):
        bot = 'test'
        assert not ContentImporterLogProcessor.is_event_in_progress(bot)

    def test_is_event_in_progress_true(self):
        bot = 'test'
        user = 'test'
        table_name = 'test_table'
        ContentImporterLogProcessor.add_log(bot, user, is_data_uploaded=False, table=table_name)
        assert ContentImporterLogProcessor.is_event_in_progress(bot, False)

        with pytest.raises(AppException):
            ContentImporterLogProcessor.is_event_in_progress(bot)

    def test_get_logs(self):
        bot = 'test'
        logs = list(ContentImporterLogProcessor.get_logs(bot))
        assert len(logs) == 4

    def test_is_limit_exceeded_exception(self, monkeypatch):
        bot = 'test'
        try:
            bot_settings = BotSettings.objects(bot=bot).get()
            bot_settings.content_importer_limit_per_day = 0
        except:
            bot_settings = BotSettings(bot=bot, content_importer_limit_per_day=0, user="test")
        bot_settings.save()
        with pytest.raises(AppException):
            assert ContentImporterLogProcessor.is_limit_exceeded(bot)

    def test_is_limit_exceeded(self, monkeypatch):
        bot = 'test'
        bot_settings = BotSettings.objects(bot=bot).get()
        bot_settings.content_importer_limit_per_day = 3
        bot_settings.save()
        assert ContentImporterLogProcessor.is_limit_exceeded(bot, False)

    def test_is_limit_exceeded_false(self, monkeypatch):
        bot = 'test'
        bot_settings = BotSettings.objects(bot=bot).get()
        bot_settings.content_importer_limit_per_day = 6
        bot_settings.save()
        assert not ContentImporterLogProcessor.is_limit_exceeded(bot)
