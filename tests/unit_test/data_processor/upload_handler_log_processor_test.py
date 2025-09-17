import pytest, os
from mongoengine import connect
from unittest.mock import patch, MagicMock
from kairon.shared.data.data_objects import BotSettings
from kairon.shared.log_system.base import BaseLogHandler
from kairon.shared.upload_handler.data_objects import UploadHandlerLogs
from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.data.constant import EVENT_STATUS, STATUSES
from kairon.shared.upload_handler.upload_handler_log_processor import UploadHandlerLogProcessor


class TestUploadHandlerLogProcessor:

    @pytest.fixture(scope='session', autouse=True)
    def init(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))

    def test_add_log_creates_new(self):
        bot = 'test_bot'
        user = 'test_user'
        collection_name = 'test_collection'
        file_name="Salesstore.csv"
        upload_type="crud_data"
        UploadHandlerLogProcessor.add_log(bot, user,  file_name=file_name, upload_type=upload_type, collection_name=collection_name,)
        log = UploadHandlerLogs.objects(bot=bot).get().to_mongo().to_dict()
        assert not log.get('exception')
        assert log['collection_name']
        assert log['start_timestamp']
        assert not log.get('end_timestamp')
        assert not log.get('upload_errors')
        assert log.get('file_name')
        assert log.get('upload_type')
        assert log['event_status'] == EVENT_STATUS.INITIATED.value

    def test_add_log_updates_existing(self):
        bot = 'test_bot'
        user = 'test_user'
        UploadHandlerLogProcessor.add_log(bot, user,
                                            event_status=EVENT_STATUS.VALIDATING.value)
        log = UploadHandlerLogs.objects(bot=bot).get().to_mongo().to_dict()
        assert not log.get('exception')
        assert log['start_timestamp']
        assert log['collection_name']
        assert not log.get('end_timestamp')
        assert not log.get('Upload_errors')
        assert log.get('file_name')
        assert log['event_status'] == EVENT_STATUS.VALIDATING.value

    def test_is_event_in_progress_true_raises(self):
        bot="test_bot"
        collection_name="test_collection"
        assert UploadHandlerLogProcessor.is_event_in_progress(bot, collection_name, False)

        with pytest.raises(AppException):
            UploadHandlerLogProcessor.is_event_in_progress(bot, collection_name)

    def test_is_event_in_progress_true_no_exception(self):
        result = UploadHandlerLogProcessor.is_event_in_progress("test_bot", "test_collection_2")
        assert not result

    def test_add_log_success(self):
        bot = 'test_bot'
        user = 'test_user'
        UploadHandlerLogProcessor.add_log(bot, user, collection_name="test_collection", event_status=EVENT_STATUS.SAVE.value)
        UploadHandlerLogProcessor.add_log(bot, user,
                                         status=STATUSES.SUCCESS.value,
                                         event_status=EVENT_STATUS.COMPLETED.value)
        log, count = BaseLogHandler.get_logs(bot, "file_upload")
        assert not log[0].get('exception')
        assert log[0]['collection_name']
        assert log[0]['start_timestamp']
        assert log[0].get('end_timestamp')
        assert log[0]['file_name'] ==  "Salesstore.csv"
        assert log[0].get('status') == 'Success'
        assert log[0]['event_status'] == EVENT_STATUS.COMPLETED.value

    def test_add_log_with_exception_sets_fields(self):
        bot = 'test_bot'
        user = 'test_user'
        file_name = "Salesstore.csv"
        upload_type = "crud_data"
        collection_name = 'test_collection'

        UploadHandlerLogProcessor.add_log(bot, user, file_name=file_name, upload_type=upload_type, collection_name=collection_name)
        UploadHandlerLogProcessor.add_log(
            bot=bot,
            user=user,
            exception="File format not supported",
            upload_errors={"File type error" : "Invalid file type"},
            event_status=EVENT_STATUS.FAIL.value,
            status=STATUSES.FAIL.value
        )

        log, count = BaseLogHandler.get_logs(bot, "file_upload")

        assert log[0]['event_status'] == EVENT_STATUS.FAIL.value
        assert log[0]['exception'] == "File format not supported"
        assert log[0]['start_timestamp']
        assert log[0]['collection_name']
        assert log[0]['upload_errors']["File type error"] == "Invalid file type"
        assert log[0]["status"] == STATUSES.FAIL.value
        assert log[0]['end_timestamp'] is not None
        assert log[0]['start_timestamp'] is not None

    def test_is_limit_exceeded_exception(self, monkeypatch):
        bot = 'test_bot'
        try:
            bot_settings = BotSettings.objects(bot=bot).get()
            bot_settings.system_limits["file_upload_limit"] = 0
        except:
            bot_settings = BotSettings(bot=bot, system_limits={"file_upload_limit": 0}, user="test_user")
        bot_settings.save()
        with pytest.raises(AppException):
            assert UploadHandlerLogProcessor.is_limit_exceeded(bot)

    def test_is_limit_exceeded(self, monkeypatch):
        bot = 'test_bot'
        bot_settings = BotSettings.objects(bot=bot).get()
        bot_settings.system_limits["file_upload_limit"] = 3
        bot_settings.save()
        assert not UploadHandlerLogProcessor.is_limit_exceeded(bot, False)

    def test_is_limit_exceeded_false(self, monkeypatch):
        bot = 'test_bot'
        bot_settings = BotSettings.objects(bot=bot).get()
        bot_settings.system_limits["file_upload_limit"] = 6
        bot_settings.save()
        assert not UploadHandlerLogProcessor.is_limit_exceeded(bot)

    def test_get_latest_event_file_name(self):
        result = UploadHandlerLogProcessor.get_latest_event_file_name("test_bot")
        assert result == "Salesstore.csv"

    @patch("kairon.shared.upload_handler.data_objects.UploadHandlerLogs")
    def test_delete_enqueued_event_log_no_match(self, mock_logs):
        mock_instance = MagicMock()
        mock_instance.event_status = EVENT_STATUS.INITIATED.value
        mock_logs.objects.return_value.order_by.return_value.first.return_value = mock_instance

        UploadHandlerLogProcessor.delete_enqueued_event_log("test_bot")
        mock_instance.delete.assert_not_called()
