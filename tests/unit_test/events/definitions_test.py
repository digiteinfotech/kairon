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

from kairon import Utility
from kairon.events.definitions.agentic_flow import AgenticFlowEvent
from kairon.events.definitions.analytic_pipeline_handler import AnalyticsPipelineEvent
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
from kairon.shared.analytics.analytics_pipeline_processor import AnalyticsPipelineProcessor
from kairon.shared.callback.data_objects import CallbackConfig
from kairon.shared.chat.broadcast.processor import MessageBroadcastProcessor
from kairon.shared.cognition.data_objects import CollectionData
from kairon.shared.constants import EventClass, EventRequestType
from kairon.shared.data.constant import EVENT_STATUS
from kairon.shared.data.data_objects import EndPointHistory, Endpoints, BotSettings
from kairon.shared.data.data_objects import StoryEvents, Rules
from kairon.shared.data.history_log_processor import HistoryDeletionLogProcessor
from kairon.shared.data.model_processor import ModelProcessor
from kairon.shared.data.processor import MongoProcessor
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
        CollectionData(bot="test_bot", user="test_user_1", collection_name="test_collection_1").save()
        CollectionData(bot="test_bot", user="test_user_2", collection_name="test_collection_1").save()
        CollectionData(bot="test_bot", user="test_user_1", collection_name="test_collection_2").save()
        CollectionData(bot="test_bot", user="test_user_3", collection_name="test_collection_3").save()
        CollectionData(bot="test_bot", user="test_user_1", collection_name="test_collection_3").save()
        CollectionData(bot="test_bot_2", user="test_user_1", collection_name="test_collection_1").save()
        CollectionData(bot="test_bot_2", user="test_user_2", collection_name="test_collection_1").save()
        CollectionData(bot="test_bot_2", user="test_user_1", collection_name="test_collection_2").save()
        CollectionData(bot="test_bot_2", user="test_user_2", collection_name="test_collection_2").save()


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
                 "cron_exp": None, "timezone": None, "run_at":None})],
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
                               "cron_exp": None, "timezone": None, "run_at":None})]
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
            with pytest.raises(AppException, match=r"timezone is required for all schedules!"):
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
                          'collection_config': {},
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
                          'collection_config': {},
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
                          'collection_config': {},
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
        with pytest.raises(AppException, match="scheduler_config with a valid schedule is required!"):
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
                          'collection_config': {},
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
                          'collection_config': {},
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
                          'collection_config': {},
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


    @responses.activate
    def test_mail_channel_read_event_enqueue(self):
        from kairon.events.definitions.mail_channel import MailReadEvent
        bot = "test_add_schedule_event"
        user = "test_user"
        url = f"http://localhost:5001/api/events/execute/{EventClass.mail_channel_read_mails}?is_scheduled=False"
        responses.add(
            "POST", url,
            json={"message": "test msg", "success": True, "error_code": 400, "data": None}
        )
        event = MailReadEvent(bot, user)
        try:
            with patch('kairon.shared.channels.mail.processor.MailProcessor.__init__', return_value=None) as mp:
                with patch('kairon.shared.channels.mail.processor.MailProcessor.login_smtp',
                           return_value=None) as mock_login:
                    with patch('kairon.shared.channels.mail.processor.MailProcessor.logout_smtp',
                               return_value=None) as mock_logout:
                        with patch('kairon.shared.channels.mail.processor.MailProcessor.login_imap',
                                   return_value=None) as mock_login_imap:
                            with patch('kairon.shared.channels.mail.processor.MailProcessor.logout_imap',
                                       return_value=None) as mock_logout_imap:
                                event.enqueue()
        except AppException as e:
            pytest.fail(f"Unexpected exception: {e}")

    @patch('kairon.shared.channels.mail.processor.MailProcessor.read_mails')
    @patch('kairon.events.definitions.mail_channel.MailProcessor.process_message_task')
    def test_mail_read_event_execute(self, mock_process_message_task, mock_read_mails):
        from kairon.events.definitions.mail_channel import MailReadEvent
        bot = "test_add_schedule_event"
        user = "test_user"
        mock_read_mails.return_value = (["test@mail.com"], user)

        event = MailReadEvent(bot, user)
        event.execute()

        mock_read_mails.assert_called_once_with(bot)
        mock_process_message_task.assert_called_once_with('test_add_schedule_event', ["test@mail.com"])

    def test_mail_read_event_execute_exception(self):
        bot = "test_add_schedule_event"
        user = "test_user"

        with patch('kairon.shared.channels.mail.processor.MailProcessor.read_mails',
                   side_effect=Exception("Test error")):
            from kairon.events.definitions.mail_channel import MailReadEvent
            event = MailReadEvent(bot, user)
            with pytest.raises(AppException, match=f"Failed to schedule mail reading for bot {bot}. Error: Test error"):
                event.execute()

    @patch('kairon.events.definitions.agentic_flow.Utility.request_event_server')
    @patch('kairon.events.definitions.agentic_flow.AgenticFlowEvent.validate')
    def test_agentic_flow_event_enqueue(self, mock_validate, mock_request_event_server):
        mock_validate.return_value = True
        mock_request_event_server.return_value = None

        event = AgenticFlowEvent(bot='test_bot', user='test_user', flow_name='test_flow')
        event.enqueue(flow_name='test_flow', slot_data={'key': 'value'})

        mock_validate.assert_called_once()
        mock_request_event_server.assert_called_once_with(EventClass.agentic_flow, {
            'bot': 'test_bot',
            'user': 'test_user',
            'flow_name': 'test_flow',
            'slot_data': {'key': 'value'}
        })

    def test_agentic_flow_event_enqueue_exception(self):
        with patch('kairon.events.definitions.agentic_flow.Utility.request_event_server',
                   side_effect=Exception("Test Exception")):
            event = AgenticFlowEvent(bot='test_bot', user='test_user', flow_name='test_flow')
            with pytest.raises(AppException) as excinfo:
                event.enqueue(flow_name='test_flow', slot_data={'key': 'value'})
            assert str(excinfo.value) == "Test Exception"

    @patch('kairon.events.definitions.agentic_flow.AgenticFlow.execute_rule')
    @patch('kairon.events.definitions.agentic_flow.AgenticFlow.__init__', return_value=None)
    @patch('kairon.shared.auth.Authentication.get_current_user_and_bot')
    def test_agentic_flow_event_execute(self, mock_get_current_user_and_bot, mock_agentic_flow_init, mock_execute_rule):
        mock_get_current_user_and_bot.return_value = type('User', (object,), {
            'get_bot': lambda: 'test_bot',
            'get_user': lambda: 'test_user'}
        )
        mock_execute_rule.return_value = ({"result": "success"}, None)

        event = AgenticFlowEvent(bot='test_bot', user='test_user', flow_name='test_flow')
        event.execute(flow_name='test_flow', slot_data={'key': 'value'})

        mock_execute_rule.assert_called_once_with('test_flow')

    @patch('kairon.events.definitions.agentic_flow.AgenticFlow.execute_rule')
    @patch('kairon.events.definitions.agentic_flow.AgenticFlow.__init__', return_value=None)
    @patch('kairon.shared.auth.Authentication.get_current_user_and_bot')
    def test_agentic_flow_event_execute_slot_data_json_str(self, mock_get_current_user_and_bot, mock_agentic_flow_init, mock_execute_rule):
        mock_get_current_user_and_bot.return_value = type('User', (object,), {
            'get_bot': lambda: 'test_bot',
            'get_user': lambda: 'test_user'}
                                                          )
        mock_execute_rule.return_value = ({"result": "success"}, None)
        sld = {'key': 'value'}
        event = AgenticFlowEvent(bot='test_bot', user='test_user', flow_name='test_flow')
        event.execute(flow_name='test_flow', slot_data=json.dumps(sld))

        mock_execute_rule.assert_called_once_with('test_flow')

    @patch('kairon.events.definitions.agentic_flow.AgenticFlow.execute_rule')
    @patch('kairon.events.definitions.agentic_flow.AgenticFlow.__init__', return_value=None)
    @patch('kairon.shared.auth.Authentication.get_current_user_and_bot')
    def test_agentic_flow_event_execute_with_errors(self, mock_get_current_user_and_bot, mock_agentic_flow_init, mock_execute_rule):
        mock_get_current_user_and_bot.return_value = type('User', (object,), {
            'get_bot': lambda: 'test_bot',
            'get_user': lambda: 'test_user'}
        )
        mock_execute_rule.return_value = (None, ["error"])

        event = AgenticFlowEvent(bot='test_bot', user='test_user', flow_name='test_flow')
        with pytest.raises(AppException, match="Failed to execute flow test_flow. Errors: \['error'\]"):
            event.execute(flow_name='test_flow', slot_data={'key': 'value'})

        mock_execute_rule.assert_called_once_with('test_flow')

    @patch('kairon.events.definitions.agentic_flow.AgenticFlow.execute_rule')
    @patch('kairon.events.definitions.agentic_flow.AgenticFlow.__init__', return_value=None)
    @patch('kairon.shared.auth.Authentication.get_current_user_and_bot')
    def test_agentic_flow_event_execute_exception(self, mock_get_current_user_and_bot, mock_agentic_flow_init, mock_execute_rule):
        mock_get_current_user_and_bot.return_value = type('User', (object,), {'get_bot': lambda: 'test_bot',
                                                                              'get_user': lambda: 'test_user'})
        mock_execute_rule.side_effect = Exception("Test Exception")

        event = AgenticFlowEvent(bot='test_bot', user='test_user', flow_name='test_flow')
        with pytest.raises(AppException,
                           match="Failed to execute flow test_flow for bot test_bot. Error: Test Exception"):
            event.execute(flow_name='test_flow', slot_data={'key': 'value'})

        mock_execute_rule.assert_called_once_with('test_flow')

    @patch('kairon.shared.chat.agent.agent_flow.AgenticFlow.flow_exists')
    def test_agentic_flow_event_validate(self, mock_flow_exists):
        mock_flow_exists.return_value = True
        event = AgenticFlowEvent(bot='test_bot', user='test_user', flow_name='test_flow')
        result = event.validate()
        assert result is True
        mock_flow_exists.assert_called_once_with('test_bot', 'test_flow')

    @patch('kairon.shared.chat.agent.agent_flow.AgenticFlow.flow_exists')
    def test_agentic_flow_event_validate_no_flow_name(self, mock_flow_exists):
        event = AgenticFlowEvent(bot='test_bot', user='test_user')
        result = event.validate()
        assert result is None
        mock_flow_exists.assert_not_called()


    @patch("kairon.shared.data.collection_processor.DataProcessor.delete_collection_data_with_user")
    @patch("kairon.history.processor.HistoryProcessor.delete_user_history")
    def test_delete_data_called_when_till_date_is_today(self, mock_delete_conversation, mock_delete_data):
        from datetime import datetime
        today = datetime.today().date()

        event = DeleteHistoryEvent(bot="test_bot", user="test_user_1", till_date=today, sender_id="aniket.kharkia@nimblework.com")
        event.execute()

        mock_delete_data.assert_called_once_with("test_bot", "aniket.kharkia@nimblework.com")
        mock_delete_conversation.assert_called_once_with("test_bot", "aniket.kharkia@nimblework.com", today)


    @patch("kairon.shared.data.collection_processor.DataProcessor.delete_collection_data_with_user")
    @patch("kairon.history.processor.HistoryProcessor.delete_user_history")
    def test_delete_data_not_called_when_till_date_is_past(self, mock_delete_conversation, mock_delete_data):
        from datetime import datetime, timedelta
        past_date = datetime.today().date() - timedelta(days=3)

        event = DeleteHistoryEvent(bot="test_bot", user="test_user_1", till_date=past_date, sender_id="aniket.kharkia@nimblework.com")
        event.execute()

        mock_delete_data.assert_not_called()
        mock_delete_conversation.assert_called_once_with("test_bot", "aniket.kharkia@nimblework.com", past_date)


    @responses.activate
    def test_create_pipeline_event_cron_success(self):
        bot = "test_bot"
        user = "test_user"
        data = {
            "bot": "test_bot",
            "name": "test_name_cron",
            "pyscript_code": "print('Hello, World!')",
        }
        result = CallbackConfig.create_entry(**data)
        config = {
            "pipeline_name": "daily_pipeline",
            "callback_name": "test_name_cron",
            "scheduler_config": {
                "expression_type": "cron",
                "schedule": "32 11 * * *",
                "timezone": "Asia/Kolkata",
            },
            "data_deletion_policy": [],
            "triggers": [],
        }

        url = f"http://localhost:5001/api/events/execute/{EventClass.analytics_pipeline}?is_scheduled=True"
        responses.add("POST", url, json={"success": True})

        event = AnalyticsPipelineEvent(bot, user)
        event.callback_name = config["callback_name"]
        event.validate()

        with patch("kairon.shared.utils.Utility.is_exist"):
            event_id = event.enqueue(EventRequestType.add_schedule.value, config=config)

        assert event_id
        saved = AnalyticsPipelineProcessor.retrieve_config(event_id, bot)
        assert saved["pipeline_name"] == "daily_pipeline"

    @responses.activate
    def test_create_pipeline_event_cron_failure(self):
        bot = "test_bot"
        user = "test_user"
        data = {
            "bot": "test_bot",
            "name": "test_name",
            "pyscript_code": "print('Hello, World!')",
        }
        result = CallbackConfig.create_entry(**data)
        config = {
            "pipeline_name": "daily_pipeline_fail",
            "callback_name": "test_name",
            "scheduler_config": {
                "expression_type": "cron",
                "schedule": "32 11 * * *",
                "timezone": "Asia/Kolkata",
            },
            "data_deletion_policy": [],
            "triggers": [],
        }

        url = f"http://localhost:5001/api/events/execute/{EventClass.analytics_pipeline}?is_scheduled=True"
        responses.add("POST", url, json={"success": False, "message": "failed"})

        event = AnalyticsPipelineEvent(bot, user)
        event.callback_name = config["callback_name"]
        event.validate()

        with patch("kairon.shared.utils.Utility.is_exist"):
            with pytest.raises(AppException, match="Failed to trigger analytics_pipeline event"):
                event.enqueue(EventRequestType.add_schedule.value, config=config)


    def test_create_pipeline_event_connection_error(self):
        bot = "test_bot"
        user = "test_user"

        config = {
            "pipeline_name": "daily_pipeline_connection_error",
            "callback_name": "test_name",
            "timestamp": "2025-11-25T14:30:00Z",
            "scheduler_config": {
                "expression_type": "cron",
                "schedule": "32 11 * * *",
                "timezone": "Asia/Kolkata",
            },
            "data_deletion_policy": [],
            "triggers": [],
        }

        event = AnalyticsPipelineEvent(bot, user)
        event.callback_name = config["callback_name"]
        event.validate()

        with patch("kairon.shared.utils.Utility.request_event_server", side_effect=Exception("conn")):
            with pytest.raises(AppException, match="conn"):
                event.enqueue(EventRequestType.add_schedule.value, config=config)


    @responses.activate
    def test_create_one_time_pipeline_event_success(self):
        bot = "test_bot"
        user = "test_user"

        config = {
            "pipeline_name": "once_pipeline",
            "callback_name": "test_name",
            "scheduler_config": {
                "expression_type": "epoch",
                "schedule": 1700000000,
                "timezone": "Asia/Kolkata",
            },
            "data_deletion_policy": [],
            "triggers": [],
        }

        url = f"http://localhost:5001/api/events/execute/{EventClass.analytics_pipeline}?is_scheduled=True"
        responses.add("POST", url, json={"success": True})

        event = AnalyticsPipelineEvent(bot, user)
        event.callback_name = config["callback_name"]
        event.validate()

        with patch("kairon.shared.utils.Utility.is_exist"):
            event_id = event.enqueue(EventRequestType.add_one_time_schedule.value, config=config)

        assert event_id
        saved = AnalyticsPipelineProcessor.retrieve_config(event_id, bot)
        assert saved["pipeline_name"] == "once_pipeline"


    @responses.activate
    def test_trigger_async_pipeline_success(self):
        bot = "test_bot"
        user = "test_user"

        config = {
            "pipeline_name": "trigger_pipeline",
            "callback_name": "test_name",
            "timestamp": "2025-11-25T14:30:00Z",
            "data_deletion_policy": [],
            "triggers": [],
        }

        url = f"http://localhost:5001/api/events/execute/{EventClass.analytics_pipeline}?is_scheduled=False"
        responses.add("POST", url, json={"success": True})

        event = AnalyticsPipelineEvent(bot, user)
        event.callback_name = config["callback_name"]
        event.validate()

        with patch("kairon.shared.utils.Utility.is_exist"):
            event_id = event.enqueue(EventRequestType.trigger_async.value, config=config)


    @responses.activate
    def test_update_pipeline_success(self):
        bot = "test_bot"
        user = "test_user"

        config = {
            "pipeline_name": "daily_pipeline_for_update",
            "callback_name": "test_name_cron",
            "scheduler_config": {
                "expression_type": "cron",
                "schedule": "32 11 * * *",
                "timezone": "Asia/Kolkata",
            },
            "data_deletion_policy": [],
            "triggers": [],
        }

        url = f"http://localhost:5001/api/events/execute/{EventClass.analytics_pipeline}?is_scheduled=True"
        responses.add("POST", url, json={"success": True})

        event = AnalyticsPipelineEvent(bot, user)
        event.callback_name = config["callback_name"]
        event.validate()

        with patch("kairon.shared.utils.Utility.is_exist"):
            event_id = event.enqueue(EventRequestType.add_schedule.value, config=config)

        config = {
            "pipeline_name": "updated_pipeline",
            "callback_name": "test_name",
            "scheduler_config": {
                "expression_type": "cron",
                "schedule": "0 18 * * *",
                "timezone": "Asia/Kolkata",
            },
            "data_deletion_policy": [],
            "triggers": [],
        }

        url = f"http://localhost:5001/api/events/execute/{EventClass.analytics_pipeline}?is_scheduled=True"
        responses.add("PUT", url, json={"success": True})

        event = AnalyticsPipelineEvent(bot, user)

        with patch("kairon.shared.utils.Utility.is_exist"):
            event.enqueue(EventRequestType.update_schedule.value, event_id=event_id, config=config)

        updated = AnalyticsPipelineProcessor.retrieve_config(event_id, bot)
        assert updated["scheduler_config"]["schedule"] == "0 18 * * *"


    @responses.activate
    def test_update_pipeline_connection_error(self):
        bot = "test_bot"
        user = "test_user"
        config = {
            "pipeline_name": "daily_pipeline_update_fail",
            "callback_name": "test_name_cron",
            "scheduler_config": {
                "expression_type": "cron",
                "schedule": "32 11 * * *",
                "timezone": "Asia/Kolkata",
            },
            "data_deletion_policy": [],
            "triggers": [],
        }

        url = f"http://localhost:5001/api/events/execute/{EventClass.analytics_pipeline}?is_scheduled=True"
        responses.add("POST", url, json={"success": True})

        event = AnalyticsPipelineEvent(bot, user)
        event.callback_name = config["callback_name"]
        event.validate()

        with patch("kairon.shared.utils.Utility.is_exist"):
            event_id = event.enqueue(EventRequestType.add_schedule.value, config=config)

        config = {
            "pipeline_name": "updated_pipeline_failure",
            "callback_name": "test_name",
            "scheduler_config": {
                "expression_type": "cron",
                "schedule": "0 18 * * *",
                "timezone": "Asia/Kolkata",
            },
            "data_deletion_policy": [],
            "triggers": [],
        }

        event = AnalyticsPipelineEvent(bot, user)

        with patch("kairon.shared.utils.Utility.request_event_server",
                   side_effect=Exception("Failed to connect to service")):
            with pytest.raises(Exception, match="Failed to connect to service"):
                event.enqueue(EventRequestType.update_schedule.value, event_id=event_id, config=config)

    @responses.activate
    def test_delete_pipeline_event_success(self):
        bot = "test_bot"
        user = "test_user"
        config = {
            "pipeline_name": "daily_pipeline_delete",
            "callback_name": "test_name_cron",
            "scheduler_config": {
                "expression_type": "cron",
                "schedule": "32 11 * * *",
                "timezone": "Asia/Kolkata",
            },
            "data_deletion_policy": [],
            "triggers": [],
        }

        url = f"http://localhost:5001/api/events/execute/{EventClass.analytics_pipeline}?is_scheduled=True"
        responses.add("POST", url, json={"success": True})

        event = AnalyticsPipelineEvent(bot, user)
        event.callback_name = config["callback_name"]
        event.validate()

        with patch("kairon.shared.utils.Utility.is_exist"):
            event_id = event.enqueue(EventRequestType.add_schedule.value, config=config)

        with patch("kairon.events.definitions.analytic_pipeline_handler.AnalyticsPipelineEvent.delete_schedule") as mock_delete:
            event = AnalyticsPipelineEvent(bot, user)
            event.delete_schedule(event_id)
            mock_delete.assert_called_with(event_id)


    def test_execute_pipeline_success(self):
        bot = "test_bot"
        user = "test_user"
        event_id = "12345"

        config = {
            "pipeline_name": "pipeline_success",
            "callback_name": "cb_success",
            "scheduler_config": {"expression_type": "epoch"},
        }

        with patch("kairon.events.definitions.analytic_pipeline_handler.AnalyticsPipelineProcessor.retrieve_config",
                   return_value=config) as mock_retrieve, \
                patch(
                    "kairon.events.definitions.analytic_pipeline_handler.AnalyticsPipelineProcessor.get_pipeline_code",
                    return_value="print('hello')") as mock_code, \
                patch("kairon.events.definitions.analytic_pipeline_handler.AnalyticsRunner") as mock_runner, \
                patch(
                    "kairon.events.definitions.analytic_pipeline_handler.AnalyticsPipelineProcessor.add_event_log") as mock_log, \
                patch(
                    "kairon.events.definitions.analytic_pipeline_handler.AnalyticsPipelineProcessor.delete_task") as mock_del:
            event = AnalyticsPipelineEvent(bot, user)
            event.execute(event_id)

            mock_runner.return_value.execute.assert_called_once()
            mock_log.assert_called_once()
            mock_del.assert_called_once_with(event_id, bot)  # non-cron → delete task


    def test_execute_pipeline_fail(self):
        bot = "test_bot"
        user = "test_user"
        event_id = "999"

        config = {
            "pipeline_name": "pipeline_fail",
            "callback_name": "cb_fail",
            "scheduler_config": {"expression_type": "epoch"},
        }

        with patch("kairon.events.definitions.analytic_pipeline_handler.AnalyticsPipelineProcessor.retrieve_config",
                   return_value=config), \
                patch(
                    "kairon.events.definitions.analytic_pipeline_handler.AnalyticsPipelineProcessor.get_pipeline_code",
                    return_value="raise_error()"), \
                patch("kairon.events.definitions.analytic_pipeline_handler.AnalyticsRunner") as mock_runner, \
                patch(
                    "kairon.events.definitions.analytic_pipeline_handler.AnalyticsPipelineProcessor.add_event_log") as mock_log, \
                patch(
                    "kairon.events.definitions.analytic_pipeline_handler.AnalyticsPipelineProcessor.delete_task") as mock_del:
            mock_runner.return_value.execute.side_effect = Exception("boom")

            event = AnalyticsPipelineEvent(bot, user)
            event.execute(event_id)

            mock_log.call_args_list[0][1]["status"] == EVENT_STATUS.FAIL
            mock_del.assert_called_once_with(event_id, bot)


    def test_execute_pipeline_cron_event_no_delete(self):
        bot = "test_bot"
        user = "test_user"
        event_id = "cron1"

        config = {
            "pipeline_name": "cron_pipeline",
            "callback_name": "cron_cb",
            "scheduler_config": {"expression_type": "cron"},
        }

        with patch("kairon.events.definitions.analytic_pipeline_handler.AnalyticsPipelineProcessor.retrieve_config",
                   return_value=config), \
                patch(
                    "kairon.events.definitions.analytic_pipeline_handler.AnalyticsPipelineProcessor.get_pipeline_code",
                    return_value="print('cron run')"), \
                patch("kairon.events.definitions.analytic_pipeline_handler.AnalyticsRunner") as mock_runner, \
                patch(
                    "kairon.events.definitions.analytic_pipeline_handler.AnalyticsPipelineProcessor.add_event_log") as mock_log, \
                patch(
                    "kairon.events.definitions.analytic_pipeline_handler.AnalyticsPipelineProcessor.delete_task") as mock_del:
            event = AnalyticsPipelineEvent(bot, user)
            event.execute(event_id)

            mock_runner.return_value.execute.assert_called_once()
            mock_del.assert_not_called()


    def test_execute_pipeline_code_fetch_fails(self):
        bot = "test_bot"
        user = "test_user"
        event_id = "err2"

        config = {
            "pipeline_name": "pipeline_code_err",
            "callback_name": "cb_code_err",
            "scheduler_config": {"expression_type": "epoch"},
        }

        with patch("kairon.events.definitions.analytic_pipeline_handler.AnalyticsPipelineProcessor.retrieve_config",
                   return_value=config), \
                patch(
                    "kairon.events.definitions.analytic_pipeline_handler.AnalyticsPipelineProcessor.get_pipeline_code",
                    side_effect=Exception("code missing")), \
                patch(
                    "kairon.events.definitions.analytic_pipeline_handler.AnalyticsPipelineProcessor.add_event_log") as mock_log, \
                patch(
                    "kairon.events.definitions.analytic_pipeline_handler.AnalyticsPipelineProcessor.delete_task") as mock_del:
            event = AnalyticsPipelineEvent(bot, user)
            event.execute(event_id)

            mock_log.call_args_list[0][1]["status"] == EVENT_STATUS.FAIL
            mock_del.assert_called_once_with(event_id, bot)


    def test_execute_no_config(self):
        bot = "test_bot"
        user = "test_user"
        event_id = "nocfg"

        with patch("kairon.events.definitions.analytic_pipeline_handler.AnalyticsPipelineProcessor.retrieve_config",
                   return_value=None), \
                patch(
                    "kairon.events.definitions.analytic_pipeline_handler.AnalyticsPipelineProcessor.add_event_log") as mock_log, \
                patch(
                    "kairon.events.definitions.analytic_pipeline_handler.AnalyticsPipelineProcessor.delete_task") as mock_del:
            event = AnalyticsPipelineEvent(bot, user)
            event.execute(event_id)

            mock_log.assert_called_once()
            mock_del.assert_not_called()