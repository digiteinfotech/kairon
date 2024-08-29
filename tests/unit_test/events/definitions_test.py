import ujson as json
import os
from datetime import datetime
from io import BytesIO
from urllib.parse import urljoin

from unittest import mock
import pytest
import responses
from fastapi import UploadFile
from unittest.mock import patch
from mongoengine import connect

from augmentation.utils import WebsiteParser
from kairon import Utility
from kairon.events.definitions.data_generator import DataGenerationEvent
from kairon.events.definitions.data_importer import TrainingDataImporterEvent
from kairon.events.definitions.faq_importer import FaqDataImporterEvent
from kairon.events.definitions.history_delete import DeleteHistoryEvent
from kairon.events.definitions.message_broadcast import MessageBroadcastEvent
from kairon.events.definitions.model_testing import ModelTestingEvent
from kairon.events.definitions.model_training import ModelTrainingEvent
from kairon.events.definitions.multilingual import MultilingualEvent
from kairon.exceptions import AppException
from kairon.multilingual.processor import MultilingualTranslator
from kairon.shared.account.processor import AccountProcessor
from kairon.shared.chat.broadcast.processor import MessageBroadcastProcessor
from kairon.shared.constants import EventClass, EventRequestType
from kairon.shared.data.constant import EVENT_STATUS, TrainingDataSourceType
from kairon.shared.data.data_objects import EndPointHistory, Endpoints, BotSettings
from kairon.shared.data.data_objects import StoryEvents, Rules
from kairon.shared.data.history_log_processor import HistoryDeletionLogProcessor
from kairon.shared.data.model_processor import ModelProcessor
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.data.training_data_generation_processor import TrainingDataGenerationProcessor
from kairon.shared.data.utils import DataUtility
from kairon.shared.importer.processor import DataImporterLogProcessor
from kairon.shared.multilingual.processor import MultilingualLogProcessor
from kairon.shared.test.processor import ModelTestingLogProcessor
from mongomock import MongoClient


class TestEventDefinitions:

    @pytest.fixture(scope='class', autouse=True)
    def init(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))
        BotSettings(bot="test_definitions", user="test_user").save()
        BotSettings(bot="test_definitions_bot", user="test_user").save()
        BotSettings(bot="test_faq", user="test_user").save()

    def test_data_importer_presteps_no_training_files(self):
        bot = 'test_definitions'
        user = 'test_user'

        with pytest.raises(AppException, match="No files received!"):
            TrainingDataImporterEvent(bot, user).validate(is_data_uploaded=True)

    def test_data_importer_presteps_limit_exceeded(self, monkeypatch):
        bot = 'test_definitions'
        user = 'test_user'
        file_path = 'tests/testing_data/all/config.yml'
        file = UploadFile(filename="file.yml", file=BytesIO(open(file_path, 'rb').read()))
        bot_settings = BotSettings.objects(bot=bot).get()
        bot_settings.data_importer_limit_per_day = 0
        bot_settings.save()

        with pytest.raises(AppException, match="Daily limit exceeded."):
            TrainingDataImporterEvent(bot, user).validate(is_data_uploaded=True, training_files=[file])

    def test_data_importer_presteps_non_event(self):
        bot = 'test_definitions'
        user = 'test_user'
        file_path = 'tests/testing_data/all/config.yml'
        file = UploadFile(filename="config.yml", file=BytesIO(open(file_path, 'rb').read()))
        bot_settings = BotSettings.objects(bot=bot).get()
        bot_settings.data_importer_limit_per_day = 5
        bot_settings.save()
        assert not TrainingDataImporterEvent(bot, user, overwrite=True).validate(is_data_uploaded=True, training_files=[file])

    def test_data_importer_presteps_event(self):
        bot = 'test_definitions'
        user = 'test_user'
        file_path = 'tests/testing_data/all/domain.yml'
        file = UploadFile(filename="domain.yml", file=BytesIO(open(file_path, 'rb').read()))

        assert TrainingDataImporterEvent(bot, user).validate(is_data_uploaded=True, training_files=[file], overwrite=True)
        logs = list(DataImporterLogProcessor.get_logs(bot))
        assert len(logs) == 2
        assert logs[0]['files_received'] == ['domain']
        assert logs[0]['event_status'] == EVENT_STATUS.INITIATED.value

    def test_data_importer_presteps_already_in_progress(self):
        bot = 'test_definitions'
        user = 'test_user'

        with pytest.raises(AppException, match="Event already in progress! Check logs."):
            TrainingDataImporterEvent(bot, user).validate(is_data_uploaded=True)

    @responses.activate
    def test_data_importer_enqueue(self):
        bot = 'test_definitions'
        user = 'test_user'

        url = f"http://localhost:5001/api/events/execute/{EventClass.data_importer}?is_scheduled=False"
        responses.add(
            "POST", url,
            json={"message": "Success", "success": True, "error_code": 0, "data": {
                'StatusCode': 200,
                'FunctionError': None,
                'LogResult': 'Success',
                'ExecutedVersion': 'v1.0'
            }}
        )
        TrainingDataImporterEvent(bot, user, import_data=True, overwrite=True).enqueue()
        body = [call.request.body for call in list(responses.calls) if call.request.url == url][0]
        body = json.loads(body.decode())
        assert body["data"]['bot'] == bot
        assert body["data"]['user'] == user
        assert body["data"]['import_data'] == '--import-data'
        assert body["data"]['overwrite'] == '--overwrite'
        assert body["data"]['event_type'] == 'data_importer'
        assert body["cron_exp"] is None
        assert body["timezone"] is None
        logs = list(DataImporterLogProcessor.get_logs(bot))
        assert len(logs) == 2
        assert logs[0]['files_received'] == ['domain']
        assert logs[0]['event_status'] == EVENT_STATUS.ENQUEUED.value

    @responses.activate
    def test_data_importer_enqueue_event_server_failure(self):
        bot = 'test_definitions'
        user = 'test_user'

        url = f"http://localhost:5001/api/events/execute/{EventClass.data_importer}?is_scheduled=False"
        responses.add(
            "POST", url,
            json={"message": "Failed", "success": False, "error_code": 400, "data": None}
        )
        with pytest.raises(AppException, match='Failed to trigger data_importer event: Failed'):
            TrainingDataImporterEvent(bot, user, import_data=True, overwrite=False).enqueue()
        body = [call.request.body for call in list(responses.calls) if call.request.url == url][0]
        body = json.loads(body.decode())
        assert body["data"]['bot'] == bot
        assert body["data"]['user'] == user
        assert body["data"]['import_data'] == '--import-data'
        assert body["data"]['overwrite'] == ''
        assert body["data"]['event_type'] == 'data_importer'
        assert body["cron_exp"] is None
        assert body["timezone"] is None
        logs = list(DataImporterLogProcessor.get_logs(bot))
        assert len(logs) == 1
        assert logs[0]['files_received'] == ['config']
        assert logs[0]['event_status'] == EVENT_STATUS.COMPLETED.value
        assert not os.path.isdir('training_data/test_definitions')

    def test_data_importer_enqueue_connection_failure(self):
        bot = 'test_definitions'
        user = 'test_user'
        file_path = 'tests/testing_data/all/data/nlu.yml'
        file = UploadFile(filename="nlu.yml", file=BytesIO(open(file_path, 'rb').read()))

        assert TrainingDataImporterEvent(bot, user).validate(is_data_uploaded=True, training_files=[file], overwrite=True)
        logs = list(DataImporterLogProcessor.get_logs(bot))
        assert len(logs) == 2
        assert logs[0]['files_received'] == ['nlu']
        assert logs[0]['event_status'] == EVENT_STATUS.INITIATED.value

        with pytest.raises(AppException, match='Failed to connect to service: *'):
            TrainingDataImporterEvent(bot, user, import_data=True, overwrite=False).enqueue()
        assert not os.path.isdir('training_data/test_definitions')
        logs = list(DataImporterLogProcessor.get_logs(bot))
        assert len(logs) == 1

    def test_faq_importer_presteps_no_training_files(self):
        bot = 'test_faq'
        user = 'test_user'

        with pytest.raises(AppException, match="Invalid file type! Only csv and xlsx files are supported."):
            FaqDataImporterEvent(bot, user).validate()

    def test_faq_importer_presteps_limit_exceeded(self, monkeypatch):
        bot = 'test_faq'
        user = 'test_user'
        file_path = 'tests/testing_data/all/config.yml'
        file = UploadFile(filename="file.yml", file=BytesIO(open(file_path, 'rb').read()))
        bot_settings = BotSettings.objects(bot=bot).get()
        bot_settings.data_importer_limit_per_day = 0
        bot_settings.save()
        with pytest.raises(AppException, match="Daily limit exceeded."):
            FaqDataImporterEvent(bot, user).validate(training_data_file=file)

    def test_faq_importer_presteps_event(self):
        bot = 'test_faq'
        user = 'test_user'
        config = "Questions,Answer,\nWhat is Digite?, IT Company,\nHow are you?, I am good,\nWhat day is it?, It is Thursday,\n   ,  ,\nWhat day is it?, It is Thursday,\n".encode()
        file = UploadFile(filename="config.csv", file=BytesIO(config))
        bot_settings = BotSettings.objects(bot=bot).get()
        bot_settings.data_importer_limit_per_day = 5
        bot_settings.save()
        FaqDataImporterEvent(bot, user).validate(training_data_file=file)
        logs = list(DataImporterLogProcessor.get_logs(bot))
        assert len(logs) == 1
        assert logs[0]['files_received'] == ['config.csv']
        assert logs[0]['event_status'] == EVENT_STATUS.INITIATED.value

    def test_faq_importer_presteps_already_in_progress(self):
        bot = 'test_faq'
        user = 'test_user'

        with pytest.raises(AppException, match="Event already in progress! Check logs."):
            FaqDataImporterEvent(bot, user).validate()

    @responses.activate
    def test_faq_importer_enqueue(self):
        bot = 'test_faq'
        user = 'test_user'

        url = f"http://localhost:5001/api/events/execute/{EventClass.faq_importer}?is_scheduled=False"
        responses.add(
            "POST", url,
            json={"message": "Success", "success": True, "error_code": 0, "data": {
                'StatusCode': 200,
                'FunctionError': None,
                'LogResult': 'Success',
                'ExecutedVersion': 'v1.0'
            }}
        )
        FaqDataImporterEvent(bot, user).enqueue()
        body = [call.request.body for call in list(responses.calls) if call.request.url == url][0]
        body = json.loads(body.decode())
        assert body["data"]['bot'] == bot
        assert body["data"]['user'] == user
        assert body["data"]['event_type'] == EventClass.faq_importer
        assert body["data"]['import_data'] == "--import-data"
        assert body["cron_exp"] is None
        assert body["timezone"] is None
        logs = list(DataImporterLogProcessor.get_logs(bot))
        assert len(logs) == 1
        assert logs[0]['files_received'] == ['config.csv']
        assert logs[0]['event_status'] == EVENT_STATUS.ENQUEUED.value

    @responses.activate
    def test_faq_importer_enqueue_event_server_failure(self):
        bot = 'test_faq'
        user = 'test_user'

        url = f"http://localhost:5001/api/events/execute/{EventClass.faq_importer}?is_scheduled=False"
        responses.add(
            "POST", url,
            json={"message": "Failed", "success": False, "error_code": 400, "data": None}
        )
        with pytest.raises(AppException, match='Failed to trigger faq_importer event: Failed'):
            FaqDataImporterEvent(bot, user).enqueue()
        body = [call.request.body for call in list(responses.calls) if call.request.url == url][0]
        body = json.loads(body.decode())
        assert body["data"]['bot'] == bot
        assert body["data"]['user'] == user
        assert body["data"]['event_type'] == EventClass.faq_importer
        assert body["data"]['import_data'] == "--import-data"
        assert body["cron_exp"] is None
        assert body["timezone"] is None
        logs = list(DataImporterLogProcessor.get_logs(bot))
        assert len(logs) == 0
        assert not os.path.isdir('training_data/test_faq')

    def test_faq_importer_enqueue_connection_failure(self):
        bot = 'test_faq'
        user = 'test_user'
        config = "Questions,Answer,\nWhat is Digite?, IT Company,\nHow are you?, I am good,\nWhat day is it?, It is Thursday,\n   ,  ,\nWhat day is it?, It is Thursday,\n".encode()
        file = UploadFile(filename="cfile.csv", file=BytesIO(config))

        FaqDataImporterEvent(bot, user).validate(training_data_file=file)
        logs = list(DataImporterLogProcessor.get_logs(bot))
        assert len(logs) == 1
        assert logs[0]['files_received'] == ['cfile.csv']
        assert logs[0]['event_status'] == EVENT_STATUS.INITIATED.value

        with pytest.raises(AppException, match='Failed to connect to service: *'):
            FaqDataImporterEvent(bot, user).enqueue()
        assert not os.path.isdir('training_data/test_faq')
        logs = list(DataImporterLogProcessor.get_logs(bot))
        assert len(logs) == 0

    def test_faq_importer_xlsx(self):
        bot = 'test_faq'
        user = 'test_user'
        file = "tests/testing_data/upload_faq/upload.xlsx"
        file = UploadFile(filename="cfile.xlsx", file=open(file, "rb"))

        FaqDataImporterEvent(bot, user).validate(training_data_file=file)
        logs = list(DataImporterLogProcessor.get_logs(bot))
        assert len(logs) == 1
        assert logs[0]['files_received'] == ['cfile.xlsx']
        assert logs[0]['event_status'] == EVENT_STATUS.INITIATED.value

        with pytest.raises(AppException, match='Failed to connect to service: *'):
            FaqDataImporterEvent(bot, user).enqueue()
        assert not os.path.isdir('training_data/test_faq')
        logs = list(DataImporterLogProcessor.get_logs(bot))
        assert len(logs) == 0

    def test_model_training_presteps_no_training_data(self):
        bot = 'test_definitions'
        user = 'test_user'
        with pytest.raises(AppException, match='Please add at least 2 flows and 2 intents before training the bot!'):
            ModelTrainingEvent(bot, user).validate()
        logs = list(ModelProcessor.get_training_history(bot))
        assert len(logs) == 0

    def test_model_training_presteps_rule_exists(self):
        bot = 'test_definitions'
        user = 'test_user'
        story = 'new_story'
        intent = 'test_intent'
        action = 'test_action'
        story_event = [StoryEvents(name=intent, type="user"),
                       StoryEvents(name="bot", type="slot", value=bot),
                       StoryEvents(name="http_action_config", type="slot", value=action),
                       StoryEvents(name="kairon_http_action", type="action")]
        Rules(
            block_name=story,
            bot=bot,
            user=user,
            events=story_event
        ).save(validate=False)
        Rules(
            block_name=story,
            bot=bot,
            user=user,
            events=story_event
        ).save(validate=False)

        with pytest.raises(AppException, match='Please add at least 2 flows and 2 intents before training the bot!'):
            ModelTrainingEvent(bot, user).validate()
        processor = MongoProcessor()
        assert processor.add_intent("greeting", bot, user, is_integration=False)
        with pytest.raises(AppException, match='Please add at least 2 flows and 2 intents before training the bot!'):
            ModelTrainingEvent(bot, user).validate()
        assert processor.add_intent("goodbye", bot, user, is_integration=False)
        ModelTrainingEvent(bot, user).validate()
        logs = list(ModelProcessor.get_training_history(bot))
        assert len(logs) == 0

    def test_model_training_presteps(self, monkeypatch):
        bot = 'test_definitions'
        user = 'test_user'

        def _mock_validation(*args, **kwargs):
            return None
        monkeypatch.setattr(DataUtility, "validate_existing_data_train", _mock_validation)
        ModelTrainingEvent(bot, user).validate()
        logs = list(ModelProcessor.get_training_history(bot))
        assert len(logs) == 0

    @responses.activate
    def test_model_training_enqueue(self, monkeypatch):
        bot = 'test_definitions'
        user = 'test_user'
        url = f"http://localhost:5001/api/events/execute/{EventClass.model_training}?is_scheduled=False"
        responses.add(
            "POST", url,
            json={"message": "Success", "success": True, "error_code": 0, "data": {
                'StatusCode': 200,
                'FunctionError': None,
                'LogResult': 'Success',
                'ExecutedVersion': 'v1.0'
            }}
        )

        def __mock_get_bot(*args, **kwargs):
            return {"account": 1000}

        monkeypatch.setattr(AccountProcessor, "get_bot", __mock_get_bot)
        ModelTrainingEvent(bot, user).enqueue()
        body = [call.request.body for call in list(responses.calls) if call.request.url == url][0]
        body = json.loads(body.decode())
        assert body["data"]['bot'] == bot
        assert body["data"]['user'] == user
        assert body["cron_exp"] is None
        assert body["timezone"] is None
        assert not Utility.check_empty_string(body["data"]['token'])
        logs = list(ModelProcessor.get_training_history(bot))
        assert len(logs) == 1
        assert logs[0]['status'] == EVENT_STATUS.ENQUEUED.value

    def test_model_training_presteps_event_in_progress(self, monkeypatch):
        bot = 'test_definitions'
        user = 'test_user'

        def _mock_validation(*args, **kwargs):
            return None
        monkeypatch.setattr(DataUtility, "validate_existing_data_train", _mock_validation)
        with pytest.raises(AppException, match="Previous model training in progress."):
            ModelTrainingEvent(bot, user).validate()

    def test_model_training_presteps_limit_exceeded(self, monkeypatch):
        bot = 'test_definitions_bot'
        user = 'test_user'

        def _mock_validation(*args, **kwargs):
            return None
        monkeypatch.setattr(DataUtility, "validate_existing_data_train", _mock_validation)
        bot_settings = BotSettings.objects(bot=bot).get()
        bot_settings.training_limit_per_day = 0
        bot_settings.save()
        with pytest.raises(AppException, match="Daily model training limit exceeded."):
            ModelTrainingEvent(bot, user).validate()

    @responses.activate
    def test_model_training_enqueue_event_server_failure(self, monkeypatch):
        bot = 'test_definitions'
        user = 'test_user'

        def __mock_get_bot(*args, **kwargs):
            return {"account": 1000}

        monkeypatch.setattr(AccountProcessor, "get_bot", __mock_get_bot)
        responses.add(
            "POST", f"http://localhost:5001/api/events/execute/{EventClass.model_training}",
            json={"message": "Failed", "success": False, "error_code": 400, "data": None}
        )
        with pytest.raises(AppException, match='Failed to trigger model_training event: Failed'):
            ModelTrainingEvent(bot, user).enqueue()
        logs = list(ModelProcessor.get_training_history(bot))
        assert len(logs) == 0

    def test_model_training_enqueue_connection_failure(self, monkeypatch):
        bot = 'test_definitions'
        user = 'test_user'

        def _mock_validation(*args, **kwargs):
            return None

        def __mock_get_bot(*args, **kwargs):
            return {"account": 1000}

        monkeypatch.setattr(AccountProcessor, "get_bot", __mock_get_bot)
        monkeypatch.setattr(DataUtility, "validate_existing_data_train", _mock_validation)
        with pytest.raises(AppException, match='Failed to connect to service: *'):
            ModelTrainingEvent(bot, user).enqueue()
        logs = list(ModelProcessor.get_training_history(bot))
        assert len(logs) == 0

    def test_model_testing_presteps_model_file_not_found(self):
        bot = 'test_definitions'
        user = 'test_user'
        with pytest.raises(AppException, match='No model trained yet. Please train a model to test'):
            ModelTestingEvent(bot, user).validate()

    def test_model_testing_presteps(self, monkeypatch):
        bot = 'test_definitions'
        user = 'test_user'

        def _mock_validation(*args, **kwargs):
            return None
        monkeypatch.setattr(Utility, "is_model_file_exists", _mock_validation)
        ModelTestingEvent(bot, user).validate()
        logs, row_count = ModelTestingLogProcessor.get_logs(bot)
        assert row_count == 0

    @responses.activate
    def test_model_testing_enqueue(self):
        bot = 'test_definitions'
        user = 'test_user'
        url = f"http://localhost:5001/api/events/execute/{EventClass.model_testing}?is_scheduled=False"
        responses.add(
            "POST", url,
            json={"message": "Success", "success": True, "error_code": 0, "data": {
                'StatusCode': 200,
                'FunctionError': None,
                'LogResult': 'Success',
                'ExecutedVersion': 'v1.0'
            }}
        )
        ModelTestingEvent(bot, user).enqueue()
        body = [call.request.body for call in list(responses.calls) if call.request.url == url][0]
        body = json.loads(body.decode())
        assert body["data"]['bot'] == bot
        assert body["data"]['user'] == user
        logs, row_count = ModelTestingLogProcessor.get_logs(bot)
        assert row_count == 1
        assert logs[0]['event_status'] == EVENT_STATUS.ENQUEUED.value
        assert logs[0]['is_augmented'] is True

    def test_model_testing_presteps_event_in_progress(self, monkeypatch):
        bot = 'test_definitions'
        user = 'test_user'

        def _mock_validation(*args, **kwargs):
            return None
        monkeypatch.setattr(Utility, "is_model_file_exists", _mock_validation)
        with pytest.raises(AppException, match='Event already in progress! Check logs.'):
            ModelTestingEvent(bot, user).validate()
        logs, row_count = ModelTestingLogProcessor.get_logs(bot)
        assert row_count == 1
        assert logs[0]['event_status'] == EVENT_STATUS.ENQUEUED.value

    def test_model_testing_presteps_event_limit_reached(self, monkeypatch):
        bot = 'test_definitions_bot'
        user = 'test_user'

        def _mock_validation(*args, **kwargs):
            return None
        monkeypatch.setattr(Utility, "is_model_file_exists", _mock_validation)
        bot_settings = BotSettings.objects(bot=bot).get()
        bot_settings.test_limit_per_day = 0
        bot_settings.save()
        with pytest.raises(AppException, match='Daily limit exceeded.'):
            ModelTestingEvent(bot, user).validate()
        logs, row_count = ModelTestingLogProcessor.get_logs(bot)
        assert row_count == 0

    @responses.activate
    def test_model_testing_enqueue_event_server_failure(self):
        bot = 'test_definitions'
        user = 'test_user'
        responses.add(
            "POST", f"http://localhost:5001/api/events/execute/{EventClass.model_testing}",
            json={"message": "Failed", "success": False, "error_code": 400, "data": None}
        )
        with pytest.raises(AppException, match='Failed to trigger model_testing event: Failed'):
            ModelTestingEvent(bot, user).enqueue()
        logs, row_count = ModelTestingLogProcessor.get_logs(bot)
        assert row_count == 0

    def test_model_testing_enqueue_connection_failure(self, monkeypatch):
        bot = 'test_definitions'
        user = 'test_user'

        def _mock_validation(*args, **kwargs):
            return None

        monkeypatch.setattr(Utility, "is_model_file_exists", _mock_validation)
        ModelTestingEvent(bot, user).validate()
        logs, row_count = ModelTestingLogProcessor.get_logs(bot)
        assert row_count == 0

        with pytest.raises(AppException, match='Failed to connect to service: *'):
            ModelTestingEvent(bot, user).enqueue()
        logs, row_count = ModelTestingLogProcessor.get_logs(bot)
        assert row_count == 0

    def test_delete_history_presteps_validate_endpoint(self):
        bot = 'test_definitions_unmanaged'
        user = 'test_user'

        history_endpoint = EndPointHistory(url="http://localhost:10000")
        Endpoints(history_endpoint=history_endpoint, bot=bot, user=user).save()

        with pytest.raises(AppException,
                           match=f'History server not managed by Kairon!. Manually delete the collection:{bot}'):
            DeleteHistoryEvent(bot, user).validate()
        logs = list(HistoryDeletionLogProcessor.get_logs(bot))
        assert len(logs) == 0

    def test_delete_history_presteps(self):
        bot = 'test_definitions'
        user = 'test_user'

        DeleteHistoryEvent(bot, user).validate()
        logs = list(HistoryDeletionLogProcessor.get_logs(bot))
        assert len(logs) == 0

    @responses.activate
    def test_delete_history_enqueue(self):
        till_date = datetime.utcnow().date()
        bot = 'test_definitions'
        user = 'test_user'
        url = f"http://localhost:5001/api/events/execute/{EventClass.delete_history}"
        responses.add(
            "POST", url,
            match=[responses.matchers.json_params_matcher(
                {"data": {"bot": bot, "user": user, "till_date": str(till_date), "sender_id": "udit.pandey@digite.com"},
                 "cron_exp": None, "timezone": None})],
            json={"message": "Success", "success": True, "error_code": 0, "data": {
                'StatusCode': 200,
                'FunctionError': None,
                'LogResult': 'Success',
                'ExecutedVersion': 'v1.0'
            }}
        )
        DeleteHistoryEvent(bot, user, till_date=till_date, sender_id='udit.pandey@digite.com').enqueue()
        logs = list(HistoryDeletionLogProcessor.get_logs(bot))
        assert len(logs) == 1
        assert logs[0]['status'] == EVENT_STATUS.ENQUEUED.value

    def test_delete_history_presteps_already_in_progress(self):
        bot = 'test_definitions'
        user = 'test_user'

        with pytest.raises(AppException, match="Event already in progress! Check logs."):
            DeleteHistoryEvent(bot, user).validate()
        logs = list(HistoryDeletionLogProcessor.get_logs(bot))
        assert len(logs) == 1
        assert logs[0]['status'] == EVENT_STATUS.ENQUEUED.value

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_delete_history_execute(self, mock_mongo):
        import time

        bot = 'test_definitions'
        user = 'test_user'
        mongo_client = MongoClient("mongodb://test/conversations")
        db = mongo_client.get_database("conversation")
        collection = db.get_collection(bot)
        items = json.load(open("./tests/testing_data/history/conversations_history.json", "r"))
        for item in items:
            item['event']['timestamp'] = time.time()
        collection.insert_many(items)
        mock_mongo.return_value = mongo_client

        DeleteHistoryEvent(bot, user).execute()
        logs = list(HistoryDeletionLogProcessor.get_logs(bot))
        assert len(logs) == 1
        assert logs[0]['status'] == EVENT_STATUS.COMPLETED.value

    @responses.activate
    def test_delete_history_enqueue_event_server_failure(self):
        bot = 'test_definitions'
        user = 'test_user'
        url = f"http://localhost:5001/api/events/execute/{EventClass.delete_history}?is_scheduled=False"
        responses.add(
            "POST", url,
            json={"message": "Failed", "success": False, "error_code": 400, "data": None}
        )
        with pytest.raises(AppException, match='Failed to trigger delete_history event: Failed'):
            DeleteHistoryEvent(bot, user).enqueue()
        body = [call.request.body for call in list(responses.calls) if call.request.url == url][0]
        body = json.loads(body.decode())
        assert body["data"]['bot'] == bot
        assert body["data"]['user'] == user
        assert body["data"]['till_date']
        assert body["data"]['sender_id'] == ""
        logs = list(HistoryDeletionLogProcessor.get_logs(bot))
        assert len(logs) == 1

    def test_delete_history_enqueue_connection_failure(self):
        bot = 'test_definitions'
        user = 'test_user'

        DeleteHistoryEvent(bot, user).validate()
        logs = list(HistoryDeletionLogProcessor.get_logs(bot))
        assert len(logs) == 1

        with pytest.raises(AppException, match='Failed to connect to service: *'):
            DeleteHistoryEvent(bot, user).enqueue()
        logs = list(HistoryDeletionLogProcessor.get_logs(bot))
        assert len(logs) == 1

    def test_trigger_multilingual_execute_presteps(self):
        bot_name = 'test_events_bot'
        user = 'test_user'
        d_lang = "es"
        translate_responses = False
        translate_actions = True
        bot_obj = AccountProcessor.add_bot(bot_name, 1, user)
        pytest.multilingual_bot = bot_obj['_id'].__str__()
        MultilingualEvent(pytest.multilingual_bot, user, dest_lang=d_lang, translate_responses=translate_responses,
                          translate_actions=translate_actions).validate()

        logs = list(MultilingualLogProcessor.get_logs(pytest.multilingual_bot))
        assert len(logs) == 0

    def test_trigger_multilingual_source_and_dest_language_same(self):
        bot_name = 'test_events_bot_en'
        user = 'test_user'
        d_lang = "en"
        translate_responses = False
        translate_actions = True
        bot_obj = AccountProcessor.add_bot(bot_name, 1, user)
        pytest.multilingual_bot = bot_obj['_id'].__str__()

        with pytest.raises(AppException, match='Source and destination language cannot be the same.'):
            MultilingualEvent(pytest.multilingual_bot, user, dest_lang=d_lang, translate_responses=translate_responses,
                              translate_actions=translate_actions).validate()

        logs = list(MultilingualLogProcessor.get_logs(pytest.multilingual_bot))
        assert len(logs) == 0

    @responses.activate
    def test_trigger_multilingual_translation_enqueue(self):
        user = 'test_user'
        d_lang = "es"
        event_url = urljoin(Utility.environment['events']['server_url'],
                            f"/api/events/execute/{EventClass.multilingual}")
        responses.add("POST",
                      event_url,
                      json={"message": "Event triggered successfully!", "success": True},
                      status=200,
                      match=[
                          responses.matchers.json_params_matcher(
                              {"data": {'bot': pytest.multilingual_bot, 'user': user, 'dest_lang': d_lang,
                               'translate_responses': '', 'translate_actions': '--translate-actions'},
                               "cron_exp": None, "timezone": None})]
                      )
        MultilingualEvent(pytest.multilingual_bot, user, dest_lang=d_lang, translate_responses=False,
                          translate_actions=True).enqueue()

        logs = list(MultilingualLogProcessor.get_logs(pytest.multilingual_bot))
        assert len(logs) == 1
        assert not logs[0].get('exception')
        assert logs[0]['start_timestamp']
        assert not logs[0].get('end_timestamp')
        assert not logs[0].get('status')
        assert logs[0]['event_status'] == EVENT_STATUS.ENQUEUED.value

    def test_trigger_multilingual_in_progress(self):
        user = 'test_user'
        d_lang = "es"
        translate_responses = False
        translate_actions = True
        with pytest.raises(AppException, match="Event already in progress! Check logs."):
            MultilingualEvent(pytest.multilingual_bot, user, dest_lang=d_lang, translate_responses=translate_responses,
                              translate_actions=translate_actions).validate()
        logs = list(MultilingualLogProcessor.get_logs(pytest.multilingual_bot))
        assert len(logs) == 1

    def test_trigger_multilingual_translation(self, monkeypatch):
        user = 'test_user'
        d_lang = "es"
        translate_responses = False
        translate_actions = True

        def _mock_create_multilingual_bot(*args, **kwargs):
            return 'translated_test_events_bot'

        monkeypatch.setattr(MultilingualTranslator, "create_multilingual_bot", _mock_create_multilingual_bot)
        MultilingualEvent(pytest.multilingual_bot, user, dest_lang=d_lang, translate_responses=translate_responses,
                          translate_actions=translate_actions).execute()
        logs = list(MultilingualLogProcessor.get_logs(pytest.multilingual_bot))
        assert len(logs) == 1
        assert logs[0]['destination_bot'] == 'translated_test_events_bot'
        assert logs[0]['d_lang'] == d_lang
        assert logs[0]['translate_responses'] == translate_responses
        assert logs[0]['translate_actions'] == translate_actions
        assert logs[0]['copy_type'] == 'Translation'
        assert logs[0]['start_timestamp']
        assert logs[0]['end_timestamp']
        assert not logs[0].get('exception')
        assert logs[0].get('status') == 'Success'
        assert logs[0].get('event_status') == EVENT_STATUS.COMPLETED.value

    def test_trigger_multilingual_translation_event_connection_error(self, monkeypatch):
        bot = 'test_events_bot'
        user = 'test_user'
        d_lang = "es"
        with pytest.raises(AppException, match='Failed to connect to service: *'):
            MultilingualEvent(bot, user, dest_lang=d_lang, translate_responses=True, translate_actions=True).enqueue()
        logs = list(MultilingualLogProcessor.get_logs(bot))
        assert len(logs) == 0

    def test_trigger_website_data_generation_execute_presteps(self):
        bot = 'test_data_generation_bot'
        user = 'test_user'
        website_url = 'https://www.nimblework.com/blog/#gsc.tab=0'
        source_type = TrainingDataSourceType.website
        DataGenerationEvent(bot, user, website_url=website_url).validate()
        logs = list(TrainingDataGenerationProcessor.get_training_data_generator_history(bot, source_type))
        assert len(logs) == 0

    def test_trigger_website_data_generation_invalid_depth(self):
        bot = 'test_data_generation_bot'
        user = 'test_user'
        website_url = 'https://www.nimblework.com/blog/#gsc.tab=0'
        source_type = TrainingDataSourceType.website
        with pytest.raises(AppException, match="depth should be between 0 and 2"):
            DataGenerationEvent(bot, user, website_url=website_url, depth=3).validate()
        logs = list(TrainingDataGenerationProcessor.get_training_data_generator_history(bot, source_type))
        assert len(logs) == 0

    @responses.activate
    def test_trigger_website_data_generation_enqueue(self):
        bot = 'test_data_generation_bot'
        user = 'test_user'
        website_url = 'https://www.nimblework.com/blog/#gsc.tab=0'
        source_type = TrainingDataSourceType.website
        event_url = urljoin(Utility.environment['events']['server_url'],
                            f"/api/events/execute/{EventClass.data_generator}")
        responses.add("POST",
                      event_url,
                      json={"message": "Event triggered successfully!", "success": True},
                      status=200,
                      match=[
                          responses.matchers.json_params_matcher(
                              {"data": {'bot': bot, 'user': user, 'type': '--from-website', 'website_url': website_url,
                               'depth': 0}, "cron_exp": None, "timezone": None})]
                      )
        DataGenerationEvent(bot, user, website_url=website_url).enqueue()
        logs = list(TrainingDataGenerationProcessor.get_training_data_generator_history(bot, source_type))
        assert len(logs) == 1
        assert not logs[0].get('exception')
        assert logs[0]['start_timestamp']
        assert not logs[0].get('end_timestamp')
        assert logs[0]['status'] == EVENT_STATUS.ENQUEUED.value

    def test_trigger_website_data_generation_in_progress(self):
        bot = 'test_data_generation_bot'
        user = 'test_user'
        website_url = 'https://www.nimblework.com/blog/#gsc.tab=0'
        source_type = TrainingDataSourceType.website
        with pytest.raises(AppException, match="Event already in progress! Check logs."):
            DataGenerationEvent(bot, user, website_url=website_url).validate()

        logs = list(TrainingDataGenerationProcessor.get_training_data_generator_history(bot, source_type))
        assert len(logs) == 1

    def test_trigger_website_data_generation(self):
        bot = 'test_data_generation_bot'
        user = 'test_user'
        website_url = 'https://www.nimblework.com/blog/#gsc.tab=0'
        source_type = TrainingDataSourceType.website
        DataGenerationEvent(bot, user, website_url=website_url).execute()
        logs = list(TrainingDataGenerationProcessor.get_training_data_generator_history(bot, source_type))
        assert len(logs) == 1
        assert not logs[0].get('exception')
        assert logs[0]['start_timestamp']
        assert logs[0].get('end_timestamp')
        assert logs[0].get('document_path') == website_url
        assert logs[0].get('source_type') == source_type
        assert logs[0].get('status') == EVENT_STATUS.COMPLETED.value
        assert list(logs[0].get('response')[0].keys()) == ['intent', 'training_examples', 'response']

    def test_trigger_website_data_generation_no_data_found(self, monkeypatch):
        bot = 'test_data_generation_bot'
        user = 'test_user'
        website_url = 'https://www.nimblework.com/blog/#gsc.tab=0'
        source_type = TrainingDataSourceType.website

        def _mock_get_qna(*args, **kwargs):
            return {}, {}

        monkeypatch.setattr(WebsiteParser, "get_qna", _mock_get_qna)
        DataGenerationEvent(bot, user, website_url=website_url).execute()
        logs = list(TrainingDataGenerationProcessor.get_training_data_generator_history(bot, source_type))
        assert len(logs) == 2
        assert logs[0]['start_timestamp']
        assert logs[0].get('end_timestamp')
        assert logs[0].get('document_path') == website_url
        assert logs[0].get('source_type') == source_type
        assert logs[0].get('status') == EVENT_STATUS.FAIL.value
        assert logs[0].get('exception') == "No data could be scraped!"

    @responses.activate
    def test_trigger_website_data_generation_event_connection_error(self):
        bot = 'test_data_generation_bot_1'
        user = 'test_user'
        website_url = '/test/website.com'
        source_type = TrainingDataSourceType.website
        with pytest.raises(AppException, match='Failed to connect to service: *'):
            DataGenerationEvent(bot, user, website_url=website_url).enqueue()
        logs = list(TrainingDataGenerationProcessor.get_training_data_generator_history(bot, source_type))
        assert len(logs) == 0

    def test_add_message_broadcast_invalid_config(self):
        bot = "test_achedule"
        user = "test_user"
        config = {
            "name": "first_scheduler",
            "connector_type": "whatsapp",
            "broadcast_type": "static",
            "recipients_config": {
                "recipients": "918958030541, "
            },
            "template_config": [
                {
                    "template_id": "brochure_pdf",
                }
            ]
        }
        event = MessageBroadcastEvent(bot, user)
        event.validate()

        with patch("kairon.shared.utils.Utility.is_exist", autospec=True):
            with pytest.raises(AppException, match="scheduler_config is required!"):
                event.enqueue(EventRequestType.add_schedule.value, config=config)

        config["scheduler_config"] = {
                "expression_type": "cron",
                "schedule": "57 22 * * *"
            }
        with pytest.raises(AppException, match=f"Channel 'whatsapp' not configured!"):
            event.enqueue(EventRequestType.add_schedule.value, config=config)

        with patch("kairon.shared.utils.Utility.is_exist", autospec=True):
            with pytest.raises(AppException, match=r"timezone is required for cron expressions!*"):
                event.enqueue(EventRequestType.add_schedule.value, config=config)

    @responses.activate
    def test_add_message_broadcast_recurring_schedule(self):
        bot = "test_add_schedule_event"
        user = "test_user"
        config = {
            "name": "first_scheduler",
            "connector_type": "whatsapp",
            "broadcast_type": "static",
            "scheduler_config": {
                "expression_type": "cron",
                "schedule": "57 22 * * *",
                "timezone": "Asia/Kolkata"
            },
            "recipients_config": {
                "recipients": "918958030541, "
            },
            "template_config": [
                {
                    "template_id": "brochure_pdf",
                }
            ]
        }

        url = f"http://localhost:5001/api/events/execute/{EventClass.message_broadcast}?is_scheduled=True"
        responses.add(
            "POST", url,
            json={"message": "Event Triggered!", "success": True, "error_code": 0, "data": None},
        )

        event = MessageBroadcastEvent(bot, user)
        event.validate()

        with patch("kairon.shared.utils.Utility.is_exist", autospec=True):
            event.enqueue(EventRequestType.add_schedule.value, config=config)

        assert len(list(MessageBroadcastProcessor.list_settings(bot))) == 1

    def test_add_message_broadcast_one_time_event_failure(self):
        bot = "test_add_schedule_event"
        user = "test_user"
        config = {
            "name": "first_scheduler",
            "connector_type": "whatsapp",
            "broadcast_type": "static",
            "recipients_config": {
                "recipients": "918958030541, "
            },
            "template_config": [
                {
                    "template_id": "brochure_pdf",
                }
            ]
        }

        event = MessageBroadcastEvent(bot, user)
        event.validate()
        with patch("kairon.shared.data.processor.MongoProcessor.get_bot_settings") as mock_get_bot_settings:
            mock_get_bot_settings.return_value = {"notification_scheduling_limit": 2}
            with patch("kairon.shared.utils.Utility.is_exist", autospec=True):
                with pytest.raises(AppException, match=r"Failed to connect to service: *"):
                    event.enqueue(EventRequestType.trigger_async.value, config=config)

        assert len(list(MessageBroadcastProcessor.list_settings(bot))) == 1

    @responses.activate
    def test_add_message_broadcast_one_time(self):
        bot = "test_add_schedule_event"
        user = "test_user"
        config = {
            "name": "first_scheduler",
            "connector_type": "whatsapp",
            "broadcast_type": "static",
            "recipients_config": {
                "recipients": "918958030541, "
            },
            "template_config": [
                {
                    "template_id": "brochure_pdf",
                }
            ]
        }

        url = f"http://localhost:5001/api/events/execute/{EventClass.message_broadcast}?is_scheduled=False"
        responses.add(
            "POST", url,
            json={"message": "Event Triggered!", "success": True, "error_code": 0, "data": None}
        )

        event = MessageBroadcastEvent(bot, user)
        event.validate()
        with patch("kairon.shared.data.processor.MongoProcessor.get_bot_settings") as mock_get_bot_settings:
            mock_get_bot_settings.return_value = {"notification_scheduling_limit": 2}
            with patch("kairon.shared.utils.Utility.is_exist", autospec=True):
                event.enqueue(EventRequestType.trigger_async.value, config=config)

        assert len(list(MessageBroadcastProcessor.list_settings(bot))) == 2

    @patch("kairon.shared.data.processor.MongoProcessor.get_bot_settings")
    def test_add_message_broadcast_limit_reached(self, mock_get_bot_settings):
        bot = "test_add_schedule_event"
        user = "test_user"
        event = MessageBroadcastEvent(bot, user)

        mock_get_bot_settings.return_value = {"notification_scheduling_limit": 2}
        with pytest.raises(AppException, match="Notification scheduling limit reached!"):
            event.validate()

        assert len(list(MessageBroadcastProcessor.list_settings(bot))) == 2

    def test_add_message_broadcast_event_server_connection_err(self):
        bot = "test_add_schedule_event"
        user = "test_user"
        config = {
            "name": "failed_schedule",
            "connector_type": "whatsapp",
            "broadcast_type": "static",
            "scheduler_config": {
                "expression_type": "cron",
                "schedule": "57 22 * * *",
                "timezone": "UTC"
            },
            "recipients_config": {
                "recipients": "918958030541, "
            },
            "template_config": [
                {
                    "template_id": "brochure_pdf",
                }
            ]
        }

        event = MessageBroadcastEvent(bot, user)
        event.validate()

        with patch("kairon.shared.utils.Utility.is_exist", autospec=True):
            with pytest.raises(AppException, match=r"Failed to connect to service: *"):
                event.enqueue(EventRequestType.add_schedule.value, config=config)

        assert len(list(MessageBroadcastProcessor.list_settings(bot))) == 2

    @responses.activate
    def test_add_message_broadcast_event_server_failure(self):
        bot = "test_add_schedule_event"
        user = "test_user"
        config = {
            "name": "failed_schedule",
            "connector_type": "whatsapp",
            "broadcast_type": "static",
            "scheduler_config": {
                "expression_type": "cron",
                "schedule": "57 22 * * *",
                "timezone": "Asia/Kolkata"
            },
            "recipients_config": {
                "recipients": "918958030541, "
            },
            "template_config": [
                {
                    "template_id": "brochure_pdf",
                }
            ]
        }

        url = f"http://localhost:5001/api/events/execute/{EventClass.message_broadcast}?is_scheduled=True"
        responses.add(
            "POST", url,
            json={"message": "Failed to add event!", "success": False, "error_code": 0, "data": None}
        )

        event = MessageBroadcastEvent(bot, user)
        event.validate()

        with patch("kairon.shared.utils.Utility.is_exist", autospec=True):
            with pytest.raises(AppException, match=r"Failed to trigger message_broadcast event: *"):
                event.enqueue(EventRequestType.add_schedule.value, config=config)

        assert len(list(MessageBroadcastProcessor.list_settings(bot))) == 2

    def test_update_message_broadcast_event_server_connection_error(self):
        bot = "test_add_schedule_event"
        user = "test_user"
        setting_id = next(MessageBroadcastProcessor.list_settings(bot))["_id"]
        config = {
            "name": "first_scheduler",
            "connector_type": "whatsapp",
            "broadcast_type": "static",
            "recipients_config": {
                "recipients": "919756653433,918958030541, "
            },
            "scheduler_config": {
                "expression_type": "cron",
                "schedule": "11 11 * * *",
                "timezone": "Asia/Kolkata"
            },
            "template_config": [
                {
                    "template_id": "brochure_pdf",
                }
            ]
        }

        event = MessageBroadcastEvent(bot, user)
        with pytest.raises(AppException, match=r"Failed to connect to service: *"):
            event.enqueue(EventRequestType.update_schedule.value, msg_broadcast_id=setting_id, config=config)

        assert len(list(MessageBroadcastProcessor.list_settings(bot))) == 2
        config = MessageBroadcastProcessor.get_settings(setting_id, bot)
        config.pop("_id")
        config.pop("timestamp")
        config.pop("status")
        config.pop("user")
        config.pop("bot")
        assert config == {'name': 'first_scheduler', 'connector_type': 'whatsapp', "broadcast_type": "static",
                          'scheduler_config': {'expression_type': 'cron', 'schedule': '57 22 * * *', "timezone": "Asia/Kolkata"},
                          'recipients_config': {'recipients': "918958030541,"}, 'retry_count': 0,
                          'template_config': [{'language': 'en', 'template_id': 'brochure_pdf'}]}

    @responses.activate
    def test_update_message_broadcast_event_server_failure(self):
        bot = "test_add_schedule_event"
        user = "test_user"
        setting_id = next(MessageBroadcastProcessor.list_settings(bot))["_id"]
        config = {
            "name": "first_scheduler",
            "connector_type": "whatsapp",
            "broadcast_type": "static",
            "recipients_config": {
                "recipients": "919756653433,918958030541, "
            },
            "scheduler_config": {
                "expression_type": "cron",
                "schedule": "11 11 * * *",
                "timezone": "Asia/Kolkata"
            },
            "template_config": [
                {
                    "template_id": "brochure_pdf",
                }
            ]
        }

        url = f"http://localhost:5001/api/events/execute/{EventClass.message_broadcast}?is_scheduled=True"
        responses.add(
            "PUT", url,
            json={"message": "Failed to update event!", "success": False, "error_code": 0, "data": None}
        )

        event = MessageBroadcastEvent(bot, user)
        with pytest.raises(AppException, match=r"Failed to trigger message_broadcast event: *"):
            event.enqueue(EventRequestType.update_schedule.value, msg_broadcast_id=setting_id, config=config)

        assert len(list(MessageBroadcastProcessor.list_settings(bot))) == 2
        config = MessageBroadcastProcessor.get_settings(setting_id, bot)
        config.pop("_id")
        config.pop("timestamp")
        config.pop("status")
        config.pop("user")
        config.pop("bot")
        assert config == {'name': 'first_scheduler', 'connector_type': 'whatsapp', "broadcast_type": "static",
                          'scheduler_config': {'expression_type': 'cron', 'schedule': '57 22 * * *', "timezone": "Asia/Kolkata"},
                          'recipients_config': {'recipients': "918958030541,"}, 'retry_count': 0,
                          'template_config': [{'language': 'en', 'template_id': 'brochure_pdf'}]}

    @responses.activate
    def test_update_message_broadcast(self):
        bot = "test_add_schedule_event"
        user = "test_user"
        setting_id = next(MessageBroadcastProcessor.list_settings(bot))["_id"]
        config = {
            "name": "first_scheduler",
            "connector_type": "whatsapp",
            "broadcast_type": "static",
            "recipients_config": {
                "recipients": "919756653433,918958030541, "
            },
            "scheduler_config": {
                "expression_type": "cron",
                "schedule": "11 11 * * *",
                "timezone": "GMT"
            },
            "template_config": [
                {
                    "template_id": "brochure_pdf",
                }
            ]
        }

        url = f"http://localhost:5001/api/events/execute/{EventClass.message_broadcast}?is_scheduled=True"
        responses.add(
            "PUT", url,
            json={"message": "Event Triggered!", "success": True, "error_code": 0, "data": None}
        )

        event = MessageBroadcastEvent(bot, user)
        event.enqueue(EventRequestType.update_schedule.value, msg_broadcast_id=setting_id, config=config)

        assert len(list(MessageBroadcastProcessor.list_settings(bot))) == 2
        config = MessageBroadcastProcessor.get_settings(setting_id, bot)
        config.pop("_id")
        config.pop("timestamp")
        config.pop("status")
        config.pop("user")
        config.pop("bot")
        assert config == {'name': 'first_scheduler', 'connector_type': 'whatsapp', "broadcast_type": "static",
                          'scheduler_config': {'expression_type': 'cron', 'schedule': '11 11 * * *', "timezone": "GMT"},
                          'recipients_config': {'recipients': "919756653433,918958030541,"}, 'retry_count': 0,
                          'template_config': [{'language': 'en', 'template_id': 'brochure_pdf'}]}

    def test_update_message_broadcast_invalid_config(self):
        bot = "test_add_schedule_event"
        user = "test_user"
        setting_id = next(MessageBroadcastProcessor.list_settings(bot))["_id"]
        config = {
            "name": "first_scheduler",
            "connector_type": "whatsapp",
            "broadcast_type": "static",
            "recipients_config": {
                "recipients": '918958030541,'
            },
            "template_config": [
                {
                    "template_id": "brochure_pdf",
                }
            ]
        }

        url = f"http://localhost:5001/api/events/execute/{EventClass.message_broadcast}?is_scheduled=False"
        responses.add(
            "POST", url,
            json={"message": "Event Triggered!", "success": True, "error_code": 0, "data": None}
        )

        event = MessageBroadcastEvent(bot, user)
        with pytest.raises(AppException, match="scheduler_config is required!"):
            event.enqueue(EventRequestType.update_schedule.value, msg_broadcast_id=setting_id, config=config)

        assert len(list(MessageBroadcastProcessor.list_settings(bot))) == 2
        config = MessageBroadcastProcessor.get_settings(setting_id, bot)
        config.pop("_id")
        config.pop("timestamp")
        config.pop("status")
        config.pop("user")
        config.pop("bot")
        assert config == {'name': 'first_scheduler', 'connector_type': 'whatsapp', "broadcast_type": "static",
                          'scheduler_config': {'expression_type': 'cron', 'schedule': '11 11 * * *', "timezone": "GMT"},
                          'recipients_config': {'recipients': "919756653433,918958030541,"}, 'retry_count': 0,
                          'template_config': [{'language': 'en', 'template_id': 'brochure_pdf'}]}

    def test_delete_message_broadcast_event_server_failure(self):
        bot = "test_add_schedule_event"
        user = "test_user"
        setting_id = next(MessageBroadcastProcessor.list_settings(bot))["_id"]

        event = MessageBroadcastEvent(bot, user)
        with pytest.raises(AppException, match=r"Failed to connect to service: *"):
            event.delete_schedule(msg_broadcast_id=setting_id)

        assert len(list(MessageBroadcastProcessor.list_settings(bot))) == 2
        config = MessageBroadcastProcessor.get_settings(setting_id, bot)
        config.pop("_id")
        config.pop("timestamp")
        config.pop("status")
        config.pop("user")
        config.pop("bot")
        assert config == {'name': 'first_scheduler', 'connector_type': 'whatsapp', "broadcast_type": "static",
                          'scheduler_config': {'expression_type': 'cron', 'schedule': '11 11 * * *', "timezone": "GMT"},
                          'recipients_config': {'recipients': "919756653433,918958030541,"}, 'retry_count': 0,
                          'template_config': [{'language': 'en', 'template_id': 'brochure_pdf'}]}

    @responses.activate
    def test_delete_message_broadcast_failure(self):
        bot = "test_add_schedule_event"
        user = "test_user"
        setting_id = next(MessageBroadcastProcessor.list_settings(bot))["_id"]

        url = f"http://localhost:5001/api/events/{setting_id}"
        responses.add(
            "DELETE", url,
            json={"message": "Failed to delete event!", "success": False, "error_code": 0, "data": None},
        )

        event = MessageBroadcastEvent(bot, user)
        with pytest.raises(AppException, match=f"Failed to delete scheduled event {setting_id}: Failed to delete event!"):
            event.delete_schedule(msg_broadcast_id=setting_id)

        assert len(list(MessageBroadcastProcessor.list_settings(bot))) == 2
        config = MessageBroadcastProcessor.get_settings(setting_id, bot)
        config.pop("_id")
        config.pop("timestamp")
        config.pop("status")
        config.pop("user")
        config.pop("bot")
        assert config == {'name': 'first_scheduler', 'connector_type': 'whatsapp', "broadcast_type": "static",
                          'scheduler_config': {'expression_type': 'cron', 'schedule': '11 11 * * *', "timezone": "GMT"},
                          'recipients_config': {'recipients': "919756653433,918958030541,"}, 'retry_count': 0,
                          'template_config': [{'language': 'en', 'template_id': 'brochure_pdf'}]}

    @responses.activate
    def test_delete_message_broadcast(self):
        bot = "test_add_schedule_event"
        user = "test_user"
        setting_id = next(MessageBroadcastProcessor.list_settings(bot))["_id"]

        url = f"http://localhost:5001/api/events/{setting_id}"
        responses.add(
            "DELETE", url,
            json={"message": "Event Triggered!", "success": True, "error_code": 0, "data": None},
        )

        event = MessageBroadcastEvent(bot, user)
        event.delete_schedule(msg_broadcast_id=setting_id)

        assert len(list(MessageBroadcastProcessor.list_settings(bot))) == 1
        with pytest.raises(AppException, match="Notification settings not found!"):
            MessageBroadcastProcessor.get_settings(setting_id, bot)
