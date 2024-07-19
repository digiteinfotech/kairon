import asyncio
import os
import shutil
import tempfile
import textwrap
import uuid
from io import BytesIO
from unittest.mock import patch
from urllib.parse import urljoin

from unittest import mock
import mongomock
import pytest
import responses
from fastapi import UploadFile
from mongoengine import connect
from rasa.shared.constants import DEFAULT_DOMAIN_PATH, DEFAULT_DATA_PATH, DEFAULT_CONFIG_PATH
from rasa.shared.importers.rasa import RasaFileImporter
from responses import matchers
from kairon.shared.utils import Utility

Utility.load_system_metadata()

from kairon.shared.channels.broadcast.whatsapp import WhatsappBroadcast
from kairon.shared.chat.data_objects import ChannelLogs

os.environ["system_file"] = "./tests/testing_data/system.yaml"

from kairon.events.definitions.data_importer import TrainingDataImporterEvent
from kairon.events.definitions.faq_importer import FaqDataImporterEvent
from kairon.events.definitions.history_delete import DeleteHistoryEvent
from kairon.events.definitions.message_broadcast import MessageBroadcastEvent
from kairon.events.definitions.model_testing import ModelTestingEvent
from kairon.events.definitions.model_training import ModelTrainingEvent
from kairon.events.definitions.scheduled_base import ScheduledEventsBase
from kairon.exceptions import AppException
from kairon.shared.chat.broadcast.processor import MessageBroadcastProcessor
from kairon.shared.constants import EventClass, EventRequestType, ChannelTypes
from kairon.shared.data.constant import EVENT_STATUS, REQUIREMENTS
from kairon.shared.data.data_objects import Configs, BotSettings
from kairon.shared.data.history_log_processor import HistoryDeletionLogProcessor
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.importer.processor import DataImporterLogProcessor
from kairon.shared.test.processor import ModelTestingLogProcessor
from kairon.test.test_models import ModelTester

os.environ["system_file"] = "./tests/testing_data/system.yaml"


class TestEventExecution:

    @pytest.fixture(scope='class', autouse=True)
    def init(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))
        tmp_dir = tempfile.mkdtemp()
        pytest.tmp_dir = tmp_dir
        yield None
        shutil.rmtree(tmp_dir)
        shutil.rmtree('models/test_events_bot')

    @pytest.fixture()
    def get_training_data(self):
        async def _read_and_get_data(path: str):
            domain_path = os.path.join(path, DEFAULT_DOMAIN_PATH)
            training_data_path = os.path.join(path, DEFAULT_DATA_PATH)
            config_path = os.path.join(path, DEFAULT_CONFIG_PATH)
            http_actions_path = os.path.join(path, 'actions.yml')
            multiflow_stories_path = os.path.join(path, 'multiflow_stories.yml')
            importer = RasaFileImporter.load_from_config(config_path=config_path,
                                                         domain_path=domain_path,
                                                         training_data_paths=training_data_path)
            domain = importer.get_domain()
            story_graph = importer.get_stories()
            config = importer.get_config()
            nlu = importer.get_nlu_data(config.get('language'))
            http_actions = Utility.read_yaml(http_actions_path)
            multiflow_stories = Utility.read_yaml(multiflow_stories_path)
            return nlu, story_graph, domain, config, http_actions, multiflow_stories

        return _read_and_get_data

    def test_trigger_data_importer_validate_only(self, monkeypatch):
        bot = 'test_events'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(uuid.uuid4()))
        shutil.copytree('tests/testing_data/validator/valid', test_data_path)

        def _path(*args, **kwargs):
            return test_data_path

        monkeypatch.setattr(Utility, "get_latest_file", _path)

        DataImporterLogProcessor.add_log(bot, user, files_received=REQUIREMENTS-{"http_actions", "chat_client_config"})
        TrainingDataImporterEvent(bot, user, import_data=True, overwrite=False).execute()
        logs = list(DataImporterLogProcessor.get_logs(bot))
        assert len(logs) == 1
        assert not logs[0].get('intents').get('data')
        assert not logs[0].get('stories').get('data')
        assert not logs[0].get('utterances').get('data')
        assert [action.get('data') for action in logs[0].get('actions') if action.get('type') == 'http_actions']
        assert not logs[0].get('training_examples').get('data')
        assert not logs[0].get('domain').get('data')
        assert not logs[0].get('config').get('data')
        assert not logs[0].get('exception')
        assert not logs[0]['is_data_uploaded']
        assert logs[0]['start_timestamp']
        assert logs[0]['end_timestamp']
        assert logs[0]['status'] == 'Success'
        assert logs[0]['event_status'] == EVENT_STATUS.COMPLETED.value

    def test_trigger_data_importer_validate_exception(self, monkeypatch):
        bot = 'test_events'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(uuid.uuid4()))
        os.mkdir(test_data_path)

        def _path(*args, **kwargs):
            return test_data_path

        monkeypatch.setattr(Utility, "get_latest_file", _path)

        DataImporterLogProcessor.add_log(bot, user, files_received=REQUIREMENTS - {"domain", "http_actions"})
        TrainingDataImporterEvent(bot, user, import_data=False, overwrite=False).execute()
        logs = list(DataImporterLogProcessor.get_logs(bot))
        assert len(logs) == 2
        assert not logs[0].get('intents').get('data')
        assert not logs[0].get('stories').get('data')
        assert not logs[0].get('utterances').get('data')
        assert not [action.get('data') for action in logs[0].get('actions') if action.get('type') == 'http_actions']
        assert not logs[0].get('training_examples').get('data')
        assert not logs[0].get('domain').get('data')
        assert not logs[0].get('config').get('data')
        assert logs[0].get('exception') == 'Some training files are absent!'
        assert not logs[0]['is_data_uploaded']
        assert logs[0]['start_timestamp']
        assert logs[0]['end_timestamp']
        assert logs[0]['status'] == 'Failure'
        assert logs[0]['event_status'] == EVENT_STATUS.FAIL.value

    def test_trigger_data_importer_validate_invalid_yaml(self, monkeypatch):
        bot = 'test_events'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(uuid.uuid4()))
        shutil.copytree('tests/testing_data/validator/invalid_yaml', test_data_path)

        def _path(*args, **kwargs):
            return test_data_path

        monkeypatch.setattr(Utility, "get_latest_file", _path)

        DataImporterLogProcessor.add_log(bot, user, files_received=REQUIREMENTS - {"domain", "http_actions"})
        TrainingDataImporterEvent(bot, user, import_data=True, overwrite=False).execute()
        logs = list(DataImporterLogProcessor.get_logs(bot))
        assert len(logs) == 3
        assert not logs[0].get('intents').get('data')
        assert not logs[0].get('stories').get('data')
        assert not logs[0].get('utterances').get('data')
        assert not [action.get('data') for action in logs[0].get('actions') if action.get('type') == 'http_actions']
        assert not logs[0].get('training_examples').get('data')
        assert not logs[0].get('domain').get('data')
        assert not logs[0].get('config').get('data')
        assert logs[0].get('exception').__contains__("Failed to validate nlu.yml. Please make sure the file is correct and all mandatory parameters are specified. Here are the errors found during validation:\n  in nlu.yml:3:\n      Value 'intent' is not a dict. Value path: '/nlu/1'")
        assert logs[0]['start_timestamp']
        assert logs[0]['end_timestamp']
        assert logs[0]['status'] == 'Failure'
        assert logs[0]['event_status'] == EVENT_STATUS.FAIL.value

    def test_trigger_data_importer_validate_invalid_domain(self, monkeypatch):
        bot = 'test_events'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(uuid.uuid4()))
        nlu_path = os.path.join(pytest.tmp_dir, str(uuid.uuid4()), 'data')
        shutil.copytree('tests/testing_data/validator/invalid_domain', test_data_path)
        shutil.copytree('tests/testing_data/validator/valid/data', nlu_path)
        shutil.copy2('tests/testing_data/validator/valid/config.yml', test_data_path)

        def _path(*args, **kwargs):
            return test_data_path

        monkeypatch.setattr(Utility, "get_latest_file", _path)

        DataImporterLogProcessor.add_log(bot, user, files_received=REQUIREMENTS - {"rules", "http_actions"})
        TrainingDataImporterEvent(bot, user, import_data=True, overwrite=False).execute()
        logs = list(DataImporterLogProcessor.get_logs(bot))
        assert logs[0].get('exception') == ('Failed to load domain.yml. Error: \'Duplicate entities in domain. These '
                                            'entities occur more than once in the domain: \'location\'.\'')
        assert logs[0]['start_timestamp']
        assert logs[0]['end_timestamp']
        assert logs[0]['status'] == 'Failure'
        assert logs[0]['event_status'] == EVENT_STATUS.FAIL.value

    def test_trigger_data_importer_validate_file_with_errors(self, monkeypatch):
        bot = 'test_events'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(uuid.uuid4()))
        shutil.copytree('tests/testing_data/validator/intent_name_mismatch', test_data_path)

        def _path(*args, **kwargs):
            return test_data_path

        monkeypatch.setattr(Utility, "get_latest_file", _path)

        DataImporterLogProcessor.add_log(bot, user, files_received=REQUIREMENTS - {"http_actions"})
        TrainingDataImporterEvent(bot, user, import_data=True, overwrite=False).execute()
        logs = list(DataImporterLogProcessor.get_logs(bot))
        assert len(logs) == 5
        assert logs[0].get('intents').get('data')
        assert not logs[0].get('stories').get('data')
        assert not logs[0].get('utterances').get('data')
        assert [action.get('data') for action in logs[0].get('actions') if action.get('type') == 'http_actions']
        assert not logs[0].get('training_examples').get('data')
        assert not logs[0].get('domain').get('data')
        assert not logs[0].get('config').get('data')
        assert not logs[0].get('exception')
        assert logs[0]['start_timestamp']
        assert logs[0]['end_timestamp']
        assert logs[0]['status'] == 'Failure'
        assert logs[0]['event_status'] == EVENT_STATUS.COMPLETED.value

    def test_trigger_data_importer_validate_and_save_overwrite(self, monkeypatch):
        bot = 'test_events'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(uuid.uuid4()))
        shutil.copytree('tests/testing_data/validator/valid', test_data_path)

        def _path(*args, **kwargs):
            return test_data_path

        monkeypatch.setattr(Utility, "get_latest_file", _path)

        DataImporterLogProcessor.add_log(bot, user,
                                         files_received=REQUIREMENTS - {"http_actions", "chat_client_config"})
        TrainingDataImporterEvent(bot, user, import_data=True, overwrite=False).execute()
        logs = list(DataImporterLogProcessor.get_logs(bot))
        assert len(logs) == 6
        assert not logs[0].get('intents').get('data')
        assert not logs[0].get('stories').get('data')
        assert not logs[0].get('utterances').get('data')
        assert [action.get('data') for action in logs[0].get('actions') if action.get('type') == 'http_actions']
        assert not logs[0].get('training_examples').get('data')
        assert not logs[0].get('domain').get('data')
        assert not logs[0].get('config').get('data')
        assert not logs[0].get('exception')
        assert logs[0]['start_timestamp']
        assert logs[0]['end_timestamp']
        assert logs[0]['status'] == 'Success'
        assert logs[0]['event_status'] == EVENT_STATUS.COMPLETED.value

        processor = MongoProcessor()
        assert 'greet' in processor.fetch_intents(bot)
        assert 'deny' in processor.fetch_intents(bot)
        assert len(processor.fetch_stories(bot)) == 2
        assert len(list(processor.fetch_training_examples(bot))) == 7
        assert len(list(processor.fetch_responses(bot))) == 4
        assert len(processor.fetch_actions(bot)) == 2
        assert len(processor.fetch_rule_block_names(bot)) == 4

    def test_trigger_data_importer_validate_and_save_append(self, monkeypatch):
        bot = 'test_events'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(uuid.uuid4()))
        shutil.copytree('tests/testing_data/validator/append', test_data_path)

        bot_content_path = os.path.join(test_data_path, 'bot_content.yml')
        if os.path.exists(bot_content_path):
            os.remove(bot_content_path)

        def _path(*args, **kwargs):
            return test_data_path

        monkeypatch.setattr(Utility, "get_latest_file", _path)

        DataImporterLogProcessor.add_log(bot, user,
                                         files_received=REQUIREMENTS - {"http_actions", "rules", "chat_client_config"})
        TrainingDataImporterEvent(bot, user, import_data=True, overwrite=False).execute()
        logs = list(DataImporterLogProcessor.get_logs(bot))
        assert len(logs) == 7
        assert not logs[0].get('intents').get('data')
        assert not logs[0].get('stories').get('data')
        assert not logs[0].get('utterances').get('data')
        assert [action.get('data') for action in logs[0].get('actions') if action.get('type') == 'http_actions']
        assert not logs[0].get('training_examples').get('data')
        assert not logs[0].get('domain').get('data')
        assert not logs[0].get('config').get('data')
        assert not logs[0].get('exception')
        assert logs[0]['start_timestamp']
        assert logs[0]['end_timestamp']
        assert logs[0]['status'] == 'Success'
        assert logs[0]['event_status'] == EVENT_STATUS.COMPLETED.value

        processor = MongoProcessor()
        assert 'greet' in processor.fetch_intents(bot)
        assert 'deny' in processor.fetch_intents(bot)
        assert 'location' in processor.fetch_intents(bot)
        assert 'affirm' in processor.fetch_intents(bot)
        assert len(processor.fetch_stories(bot)) == 4
        assert len(list(processor.fetch_training_examples(bot))) == 13
        assert len(list(processor.fetch_responses(bot))) == 6
        assert len(processor.fetch_actions(bot)) == 2
        assert len(processor.fetch_rule_block_names(bot)) == 4

    def test_trigger_data_importer_validate_and_save_overwrite_same_user(self, monkeypatch):
        bot = 'test_events'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(uuid.uuid4()))
        shutil.copytree('tests/testing_data/validator/valid', test_data_path)

        def _path(*args, **kwargs):
            return test_data_path

        monkeypatch.setattr(Utility, "get_latest_file", _path)

        DataImporterLogProcessor.add_log(bot, user,
                                         files_received=REQUIREMENTS - {"http_actions", "chat_client_config"})
        TrainingDataImporterEvent(bot, user, import_data=True, overwrite=True).execute()
        logs = list(DataImporterLogProcessor.get_logs(bot))
        assert len(logs) == 8
        assert not logs[0].get('intents').get('data')
        assert not logs[0].get('stories').get('data')
        assert not logs[0].get('utterances').get('data')
        assert [action.get('data') for action in logs[0].get('actions') if action.get('type') == 'http_actions']
        assert not logs[0].get('training_examples').get('data')
        assert not logs[0].get('domain').get('data')
        assert not logs[0].get('config').get('data')
        assert not logs[0].get('exception')
        assert logs[0]['start_timestamp']
        assert logs[0]['end_timestamp']
        assert logs[0]['status'] == 'Success'
        assert logs[0]['event_status'] == EVENT_STATUS.COMPLETED.value

        processor = MongoProcessor()
        assert 'greet' in processor.fetch_intents(bot)
        assert 'deny' in processor.fetch_intents(bot)
        assert len(processor.fetch_stories(bot)) == 2
        assert len(list(processor.fetch_training_examples(bot))) == 7
        assert len(list(processor.fetch_responses(bot))) == 4
        assert len(processor.fetch_actions(bot)) == 2
        assert len(processor.fetch_rule_block_names(bot)) == 4

    @responses.activate
    def test_trigger_data_importer_validate_event(self, monkeypatch):
        bot = 'test_events_bot'
        user = 'test_user'
        event_url = urljoin(Utility.environment['events']['server_url'], f"/api/events/execute/{EventClass.data_importer}")
        BotSettings(bot="test_events_bot", user="test_user").save()

        responses.add("POST",
                      event_url,
                      json={"success": True, "message": "Event triggered successfully!"},
                      status=200,
                      match=[
                          responses.matchers.json_params_matcher(
                              {"cron_exp": None, "data": {"bot": "test_events_bot", "event_type": "data_importer",
                                                          "import_data": "--import-data", "overwrite": "", "user": "test_user"}, "timezone": None})],
                      )
        event = TrainingDataImporterEvent(bot, user, import_data=True)
        event.validate()
        event.enqueue()

        logs = list(DataImporterLogProcessor.get_logs(bot))
        assert len(logs) == 1
        assert not logs[0].get('intents').get('data')
        assert not logs[0].get('stories').get('data')
        assert not logs[0].get('utterances').get('data')
        assert not [action.get('data') for action in logs[0].get('actions') if action.get('type') == 'http_actions']
        assert not logs[0].get('training_examples').get('data')
        assert not logs[0].get('domain').get('data')
        assert not logs[0].get('config').get('data')
        assert not logs[0].get('exception')
        assert logs[0]['start_timestamp']
        assert not logs[0].get('end_timestamp')
        assert not logs[0].get('status')
        assert logs[0]['event_status'] == EVENT_STATUS.ENQUEUED.value

    @responses.activate
    def test_trigger_data_importer_validate_and_save_event_overwrite(self, monkeypatch):
        bot = 'test_events_bot_1'
        user = 'test_user'
        event_url = urljoin(Utility.environment['events']['server_url'], f"/api/events/execute/{EventClass.data_importer}")
        BotSettings(bot="test_events_bot_1", user="test_user").save()
        responses.add("POST",
                      event_url,
                      json={"success": True, "message": "Event triggered successfully!"},
                      status=200,
                      match=[
                          responses.matchers.json_params_matcher(
                              {"data": {'bot': bot, 'user': user, 'import_data': '--import-data',
                                        'event_type': EventClass.data_importer, 'overwrite': '--overwrite'},
                               "cron_exp": None, "timezone": None})],
                      )
        event = TrainingDataImporterEvent(bot, user, import_data=True, overwrite=True)
        event.validate()
        event.enqueue()

        logs = list(DataImporterLogProcessor.get_logs(bot))
        assert len(logs) == 1
        assert not logs[0].get('intents').get('data')
        assert not logs[0].get('stories').get('data')
        assert not logs[0].get('utterances').get('data')
        assert not [action.get('data') for action in logs[0].get('actions') if action.get('type') == 'http_actions']
        assert not logs[0].get('training_examples').get('data')
        assert not logs[0].get('domain').get('data')
        assert not logs[0].get('config').get('data')
        assert not logs[0].get('exception')
        assert logs[0]['start_timestamp']
        assert not logs[0].get('end_timestamp')
        assert not logs[0].get('status')
        assert logs[0]['event_status'] == EVENT_STATUS.ENQUEUED.value

    @responses.activate
    def test_trigger_data_importer_validate_only_event(self, monkeypatch):
        bot = 'test_events_bot_2'
        user = 'test_user'
        event_url = urljoin(Utility.environment['events']['server_url'], f"/api/events/execute/{EventClass.data_importer}")
        BotSettings(bot="test_events_bot_2", user="test_user").save()

        responses.add("POST",
                      event_url,
                      json={"success": True, "message": "Event triggered successfully!"},
                      status=200,
                      match=[
                          responses.matchers.json_params_matcher(
                              {"data": {'bot': bot, 'user': user, 'import_data': '', 
                                        'event_type': EventClass.data_importer, 'overwrite': ''},
                               "cron_exp": None, "timezone": None})],
                      )
        event = TrainingDataImporterEvent(bot, user, import_data=False, overwrite=False)
        event.validate()
        event.enqueue()

        logs = list(DataImporterLogProcessor.get_logs(bot))
        assert len(logs) == 1
        assert not logs[0].get('intents').get('data')
        assert not logs[0].get('stories').get('data')
        assert not logs[0].get('utterances').get('data')
        assert not [action.get('data') for action in logs[0].get('actions') if action.get('type') == 'http_actions']
        assert not logs[0].get('training_examples').get('data')
        assert not logs[0].get('domain').get('data')
        assert not logs[0].get('config').get('data')
        assert not logs[0].get('exception')
        assert logs[0]['start_timestamp']
        assert not logs[0].get('end_timestamp')
        assert not logs[0].get('status')
        assert logs[0]['event_status'] == EVENT_STATUS.ENQUEUED.value

    def test_trigger_data_importer_event_connection_error(self, monkeypatch):
        bot = 'test_events_bot_3'
        user = 'test_user'
        BotSettings(bot="test_events_bot_3", user="test_user").save()

        event = TrainingDataImporterEvent(bot, user, import_data=False, overwrite=False)
        event.validate()
        with pytest.raises(AppException, match='Failed to connect to service: *'):
            event.enqueue()

        logs = list(DataImporterLogProcessor.get_logs(bot))
        assert len(logs) == 0

    def test_trigger_data_importer_nlu_only(self, monkeypatch, get_training_data):
        bot = 'test_trigger_data_importer'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(uuid.uuid4()))
        nlu_path = os.path.join(test_data_path, 'data')
        Utility.make_dirs(nlu_path)
        shutil.copy2('tests/testing_data/validator/valid/data/nlu.yml', nlu_path)
        nlu, story_graph, domain, config, http_actions, multiflow_stories = asyncio.run(get_training_data('tests/testing_data/validator/valid'))
        mongo_processor = MongoProcessor()
        mongo_processor.save_domain(domain, bot, user)
        mongo_processor.save_stories(story_graph.story_steps, bot, user)
        config["bot"] = bot
        config["user"] = user
        config_obj = Configs._from_son(config)
        config_obj.save()
        mongo_processor.save_rules(story_graph.story_steps, bot, user)
        mongo_processor.save_integrated_actions(http_actions, bot, user)

        def _path(*args, **kwargs):
            return test_data_path

        monkeypatch.setattr(Utility, "get_latest_file", _path)

        DataImporterLogProcessor.add_log(bot, user, files_received=["nlu"])
        TrainingDataImporterEvent(bot, user, import_data=True, overwrite=False).execute()
        logs = list(DataImporterLogProcessor.get_logs(bot))
        assert len(logs) == 1
        assert not logs[0].get('intents').get('data')
        assert not logs[0].get('stories').get('data')
        assert not logs[0].get('utterances').get('data')
        assert [action.get('data') for action in logs[0].get('actions') if action.get('type') == 'http_actions'] == [[]]
        assert not logs[0].get('training_examples').get('data')
        assert not logs[0].get('domain').get('data')
        assert not logs[0].get('config').get('data')
        assert not logs[0].get('exception')
        assert logs[0]['start_timestamp']
        assert logs[0]['end_timestamp']
        assert logs[0]['status'] == 'Success'
        assert logs[0]['event_status'] == EVENT_STATUS.COMPLETED.value

        assert len(mongo_processor.fetch_stories(bot)) == 2
        assert len(list(mongo_processor.fetch_training_examples(bot))) == 7
        assert len(list(mongo_processor.fetch_responses(bot))) == 3
        assert len(mongo_processor.fetch_actions(bot)) == 2
        assert len(mongo_processor.fetch_rule_block_names(bot)) == 3

    def test_trigger_data_importer_multiflow_stories_only(self, monkeypatch, get_training_data):
        bot = 'test_trigger_data_importer_multiflow_stories_only'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(uuid.uuid4()))
        nlu_path = os.path.join(test_data_path, 'data')
        Utility.make_dirs(nlu_path)
        shutil.copy2('tests/testing_data/multiflow_stories/valid_with_multiflow/data/nlu.yml', nlu_path)
        shutil.copy2('tests/testing_data/multiflow_stories/valid_with_multiflow/multiflow_stories.yml', test_data_path)
        nlu, story_graph, domain, config, http_actions, multiflow_stories = asyncio.run(
            get_training_data('tests/testing_data/multiflow_stories/valid_with_multiflow'))
        mongo_processor = MongoProcessor()
        mongo_processor.save_nlu(nlu, bot, user)
        mongo_processor.save_domain(domain, bot, user)
        mongo_processor.save_stories(story_graph.story_steps, bot, user)
        config["bot"] = bot
        config["user"] = user
        config_obj = Configs._from_son(config)
        config_obj.save()
        mongo_processor.save_rules(story_graph.story_steps, bot, user)
        mongo_processor.save_integrated_actions(http_actions, bot, user)
        mongo_processor.save_multiflow_stories(http_actions, bot, user)

        def _path(*args, **kwargs):
            return test_data_path

        monkeypatch.setattr(Utility, "get_latest_file", _path)

        DataImporterLogProcessor.add_log(bot, user, files_received=["multiflow_stories"])
        TrainingDataImporterEvent(bot, user, import_data=True, overwrite=False).execute()
        logs = list(DataImporterLogProcessor.get_logs(bot))
        assert len(logs) == 1
        print(logs)
        assert not logs[0].get('intents').get('data')
        assert not logs[0].get('stories').get('data')
        assert not logs[0].get('utterances').get('data')
        assert [action.get('data') for action in logs[0].get('actions') if action.get('type') == 'http_actions'] == [[]]
        assert not logs[0].get('training_examples').get('data')
        assert not logs[0].get('domain').get('data')
        assert not logs[0].get('config').get('data')
        assert not logs[0].get('exception')
        assert logs[0]['start_timestamp']
        assert logs[0]['end_timestamp']
        assert logs[0]['status'] == 'Success'
        assert logs[0]['event_status'] == EVENT_STATUS.COMPLETED.value

        assert len(mongo_processor.fetch_stories(bot)) == 2
        assert len(list(mongo_processor.fetch_training_examples(bot))) == 17
        assert len(list(mongo_processor.fetch_responses(bot))) == 7
        assert len(mongo_processor.fetch_actions(bot)) == 3
        assert len(mongo_processor.fetch_rule_block_names(bot)) == 3
        assert len(mongo_processor.fetch_multiflow_stories(bot)) == 2

    def test_trigger_data_importer_stories_only(self, monkeypatch, get_training_data):
        bot = 'test_trigger_data_importer_stories_only'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(uuid.uuid4()))
        data_path = os.path.join(test_data_path, 'data')
        Utility.make_dirs(data_path)
        shutil.copy2('tests/testing_data/validator/valid/data/stories.yml', data_path)
        nlu, story_graph, domain, config, http_actions, multiflow_stories = asyncio.run(get_training_data('tests/testing_data/validator/valid'))
        mongo_processor = MongoProcessor()
        mongo_processor.save_domain(domain, bot, user)
        mongo_processor.save_nlu(nlu, bot, user)
        config["bot"] = bot
        config["user"] = user
        config_obj = Configs._from_son(config)
        config_obj.save()
        mongo_processor.save_rules(story_graph.story_steps, bot, user)
        mongo_processor.save_integrated_actions(http_actions, bot, user)

        def _path(*args, **kwargs):
            return test_data_path

        monkeypatch.setattr(Utility, "get_latest_file", _path)

        DataImporterLogProcessor.add_log(bot, user, files_received=["stories"])
        TrainingDataImporterEvent(bot, user, import_data=True, overwrite=False).execute()
        logs = list(DataImporterLogProcessor.get_logs(bot))
        assert len(logs) == 1
        assert not logs[0].get('intents').get('data')
        assert not logs[0].get('stories').get('data')
        assert not logs[0].get('utterances').get('data')
        assert [action.get('data') for action in logs[0].get('actions') if action.get('type') == 'http_actions'] == [[]]
        assert not logs[0].get('training_examples').get('data')
        assert not logs[0].get('domain').get('data')
        assert not logs[0].get('config').get('data')
        assert not logs[0].get('exception')
        assert logs[0]['start_timestamp']
        assert logs[0]['end_timestamp']
        assert logs[0]['status'] == 'Success'
        assert logs[0]['event_status'] == EVENT_STATUS.COMPLETED.value

        assert len(mongo_processor.fetch_stories(bot)) == 2
        assert len(list(mongo_processor.fetch_training_examples(bot))) == 7
        assert len(list(mongo_processor.fetch_responses(bot))) == 3
        assert len(mongo_processor.fetch_actions(bot)) == 2
        assert len(mongo_processor.fetch_rule_block_names(bot)) == 3

    def test_trigger_data_importer_rules_only(self, monkeypatch, get_training_data):
        bot = 'test_trigger_data_importer_rules_only'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(uuid.uuid4()))
        data_path = os.path.join(test_data_path, 'data')
        Utility.make_dirs(data_path)
        shutil.copy2('tests/testing_data/validator/valid/data/rules.yml', data_path)
        nlu, story_graph, domain, config, http_actions, multiflow_stories = asyncio.run(get_training_data('tests/testing_data/validator/valid'))
        mongo_processor = MongoProcessor()
        mongo_processor.save_domain(domain, bot, user)
        mongo_processor.save_nlu(nlu, bot, user)
        config["bot"] = bot
        config["user"] = user
        config_obj = Configs._from_son(config)
        config_obj.save()
        mongo_processor.save_stories(story_graph.story_steps, bot, user)
        mongo_processor.save_integrated_actions(http_actions, bot, user)

        def _path(*args, **kwargs):
            return test_data_path

        monkeypatch.setattr(Utility, "get_latest_file", _path)

        DataImporterLogProcessor.add_log(bot, user, files_received=["rules"])
        TrainingDataImporterEvent(bot, user, import_data=True, overwrite=False).execute()
        logs = list(DataImporterLogProcessor.get_logs(bot))
        assert len(logs) == 1
        assert not logs[0].get('intents').get('data')
        assert not logs[0].get('stories').get('data')
        assert not logs[0].get('utterances').get('data')
        assert [action.get('data') for action in logs[0].get('actions') if action.get('type') == 'http_actions'] == [[]]
        assert not logs[0].get('training_examples').get('data')
        assert not logs[0].get('domain').get('data')
        assert not logs[0].get('config').get('data')
        assert not logs[0].get('exception')
        assert logs[0]['start_timestamp']
        assert logs[0]['end_timestamp']
        assert logs[0]['status'] == 'Success'
        assert logs[0]['event_status'] == EVENT_STATUS.COMPLETED.value

        assert len(mongo_processor.fetch_stories(bot)) == 2
        assert len(list(mongo_processor.fetch_training_examples(bot))) == 7
        assert len(list(mongo_processor.fetch_responses(bot))) == 3
        assert len(mongo_processor.fetch_actions(bot)) == 2
        assert len(mongo_processor.fetch_rule_block_names(bot)) == 3

    def test_trigger_data_importer_domain_only(self, monkeypatch, get_training_data):
        bot = 'test_trigger_data_importer_domain_only'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(uuid.uuid4()))
        Utility.make_dirs(test_data_path)
        shutil.copy2('tests/testing_data/validator/valid/domain.yml', test_data_path)
        nlu, story_graph, domain, config, http_actions, multiflow_stories = asyncio.run(get_training_data('tests/testing_data/validator/valid'))
        mongo_processor = MongoProcessor()
        mongo_processor.save_stories(story_graph.story_steps, bot, user)
        mongo_processor.save_nlu(nlu, bot, user)
        config["bot"] = bot
        config["user"] = user
        config_obj = Configs._from_son(config)
        config_obj.save()
        mongo_processor.save_rules(story_graph.story_steps, bot, user)
        mongo_processor.save_integrated_actions(http_actions, bot, user)

        def _path(*args, **kwargs):
            return test_data_path

        monkeypatch.setattr(Utility, "get_latest_file", _path)

        DataImporterLogProcessor.add_log(bot, user, files_received=["domain"])
        TrainingDataImporterEvent(bot, user, import_data=True, overwrite=False).execute()
        logs = list(DataImporterLogProcessor.get_logs(bot))
        assert len(logs) == 1
        assert not logs[0].get('intents').get('data')
        assert not logs[0].get('stories').get('data')
        assert not logs[0].get('utterances').get('data')
        assert [action.get('data') for action in logs[0].get('actions') if action.get('type') == 'http_actions'] == [[]]
        assert not logs[0].get('training_examples').get('data')
        assert not logs[0].get('domain').get('data')
        assert not logs[0].get('config').get('data')
        assert not logs[0].get('exception')
        assert logs[0]['start_timestamp']
        assert logs[0]['end_timestamp']
        assert logs[0]['status'] == 'Success'
        assert logs[0]['event_status'] == EVENT_STATUS.COMPLETED.value

        assert len(mongo_processor.fetch_stories(bot)) == 2
        assert len(list(mongo_processor.fetch_training_examples(bot))) == 7
        assert len(list(mongo_processor.fetch_responses(bot))) == 3
        assert len(mongo_processor.fetch_actions(bot)) == 2
        assert len(mongo_processor.fetch_rule_block_names(bot)) == 3

    def test_trigger_data_importer_validate_existing_data(self, monkeypatch):
        bot = 'test_trigger_data_importer_domain_only'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(uuid.uuid4()))
        Utility.make_dirs(test_data_path)

        def _path(*args, **kwargs):
            return test_data_path

        monkeypatch.setattr(Utility, "get_latest_file", _path)

        DataImporterLogProcessor.add_log(bot, user)
        TrainingDataImporterEvent(bot, user, import_data=True, overwrite=False).execute()
        logs = list(DataImporterLogProcessor.get_logs(bot))
        assert len(logs) == 2
        assert not logs[0].get('intents').get('data')
        assert not logs[0].get('stories').get('data')
        assert not logs[0].get('utterances').get('data')
        assert [action.get('data') for action in logs[0].get('actions') if action.get('type') == 'http_actions'] == [[]]
        assert not logs[0].get('training_examples').get('data')
        assert not logs[0].get('domain').get('data')
        assert not logs[0].get('config').get('data')
        assert not logs[0].get('exception')
        assert not logs[0]['is_data_uploaded']
        assert logs[0]['start_timestamp']
        assert logs[0]['end_timestamp']
        assert logs[0]['status'] == 'Success'
        assert logs[0]['event_status'] == EVENT_STATUS.COMPLETED.value

        mongo_processor = MongoProcessor()
        assert len(mongo_processor.fetch_stories(bot)) == 2
        assert len(list(mongo_processor.fetch_training_examples(bot))) == 7
        assert len(list(mongo_processor.fetch_responses(bot))) == 3
        assert len(mongo_processor.fetch_actions(bot)) == 2
        assert len(mongo_processor.fetch_rule_block_names(bot)) == 3

    def test_trigger_data_importer_import_with_utterance_issues(self, monkeypatch):
        bot = 'test_trigger_data_importer_import_with_utterance_issues'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(uuid.uuid4()))
        shutil.copytree('tests/testing_data/validator/orphan_utterances', test_data_path)

        def _path(*args, **kwargs):
            return test_data_path

        monkeypatch.setattr(Utility, "get_latest_file", _path)
        BotSettings(ignore_utterances=True, bot=bot, user=user).save()

        DataImporterLogProcessor.add_log(bot, user, files_received=['nlu', 'stories', 'domain', 'config'])
        TrainingDataImporterEvent(bot, user, import_data=True, overwrite=True).execute()
        logs = list(DataImporterLogProcessor.get_logs(bot))
        assert len(logs) == 1
        assert not logs[0].get('intents').get('data')
        assert not logs[0].get('stories').get('data')
        assert logs[0].get('utterances').get('data')
        assert [action.get('data') for action in logs[0].get('actions') if action.get('type') == 'http_actions']
        assert not logs[0].get('training_examples').get('data')
        assert not logs[0].get('domain').get('data')
        assert not logs[0].get('config').get('data')
        assert not logs[0].get('exception')
        assert logs[0]['start_timestamp']
        assert logs[0]['end_timestamp']
        assert logs[0]['status'] == 'Failure'
        assert logs[0]['event_status'] == EVENT_STATUS.COMPLETED.value

        mongo_processor = MongoProcessor()
        assert len(mongo_processor.fetch_stories(bot)) == 0
        assert len(list(mongo_processor.fetch_training_examples(bot))) == 0
        assert len(list(mongo_processor.fetch_responses(bot))) == 0
        assert len(mongo_processor.fetch_actions(bot)) == 0
        assert len(mongo_processor.fetch_rule_block_names(bot)) == 0

    def test_trigger_data_importer_import_with_intent_issues(self, monkeypatch):
        bot = 'test_trigger_data_importer_import_with_intent_issues'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(uuid.uuid4()))
        shutil.copytree('tests/testing_data/validator/intent_name_mismatch', test_data_path)

        def _path(*args, **kwargs):
            return test_data_path

        monkeypatch.setattr(Utility, "get_latest_file", _path)
        BotSettings(ignore_utterances=True, bot=bot, user=user).save()

        DataImporterLogProcessor.add_log(bot, user, files_received=['nlu', 'stories', 'domain', 'config'])
        TrainingDataImporterEvent(bot, user, import_data=True, overwrite=True).execute()
        logs = list(DataImporterLogProcessor.get_logs(bot))
        assert len(logs) == 1
        assert logs[0].get('intents').get('data')
        assert not logs[0].get('stories').get('data')
        assert not logs[0].get('utterances').get('data')
        assert [action.get('data') for action in logs[0].get('actions') if action.get('type') == 'http_actions']
        assert not logs[0].get('training_examples').get('data')
        assert not logs[0].get('domain').get('data')
        assert not logs[0].get('config').get('data')
        assert not logs[0].get('exception')
        assert logs[0]['start_timestamp']
        assert logs[0]['end_timestamp']
        assert logs[0]['status'] == 'Failure'
        assert logs[0]['event_status'] == EVENT_STATUS.COMPLETED.value

        mongo_processor = MongoProcessor()
        assert len(mongo_processor.fetch_stories(bot)) == 0
        assert len(list(mongo_processor.fetch_training_examples(bot))) == 0
        assert len(list(mongo_processor.fetch_responses(bot))) == 0
        assert len(mongo_processor.fetch_actions(bot)) == 0
        assert len(mongo_processor.fetch_rule_block_names(bot)) == 0

    def test_trigger_data_importer_forced_import(self, monkeypatch):
        bot = 'forced_import'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(uuid.uuid4()))
        shutil.copytree('tests/testing_data/validator/orphan_utterances', test_data_path)

        def _path(*args, **kwargs):
            return test_data_path

        monkeypatch.setattr(Utility, "get_latest_file", _path)
        BotSettings(force_import=True, bot=bot, user=user).save()

        DataImporterLogProcessor.add_log(bot, user, files_received=['nlu', 'stories', 'domain', 'config'])
        TrainingDataImporterEvent(bot, user, import_data=True, overwrite=True).execute()
        logs = list(DataImporterLogProcessor.get_logs(bot))
        assert len(logs) == 1
        assert not logs[0].get('intents').get('data')
        assert not logs[0].get('stories').get('data')
        assert logs[0].get('utterances').get('data')
        assert [action.get('data') for action in logs[0].get('actions') if action.get('type') == 'http_actions']
        assert not logs[0].get('training_examples').get('data')
        assert not logs[0].get('domain').get('data')
        assert not logs[0].get('config').get('data')
        assert not logs[0].get('exception')
        assert logs[0]['start_timestamp']
        assert logs[0]['end_timestamp']
        assert logs[0]['status'] == 'Success'
        assert logs[0]['event_status'] == EVENT_STATUS.COMPLETED.value

        mongo_processor = MongoProcessor()
        assert len(mongo_processor.fetch_stories(bot)) == 3
        assert len(list(mongo_processor.fetch_training_examples(bot))) == 21
        assert len(list(mongo_processor.fetch_responses(bot))) == 14
        assert len(mongo_processor.fetch_actions(bot)) == 4
        assert len(mongo_processor.fetch_rule_block_names(bot)) == 1

    def test_trigger_faq_importer_validate_only(self, monkeypatch):
        def _mock_execution(*args, **kwargs):
            return None

        def _mock_aggregation(*args, **kwargs):
            return {}

        monkeypatch.setattr(MongoProcessor, "delete_all_faq", _mock_execution)
        monkeypatch.setattr(MongoProcessor, 'get_training_examples_as_dict', _mock_aggregation)

        bot = 'test_faqs'
        user = 'test'
        BotSettings(bot="test_faqs", user="test").save()

        faq = "Questions,Answer,\nWhat is Digite?, IT Company,\nHow are you?, I am good,\nWhat day is it?, It is Thursday,\nWhat day is it?, It is Thursday,\n".encode()
        file = UploadFile(filename="faq.csv", file=BytesIO(faq))
        FaqDataImporterEvent(bot, user).validate(training_data_file=file)
        FaqDataImporterEvent(bot, user).execute()
        bot_data_home_dir = os.path.join('training_data', bot)
        assert not os.path.exists(bot_data_home_dir)
        logs = list(DataImporterLogProcessor.get_logs(bot))
        assert len(logs) == 1
        assert not logs[0].get('intents').get('data')
        assert len(logs[0].get('training_examples').get('data')) == 1
        assert len(logs[0].get('utterances').get('data')) == 1
        assert not logs[0].get('exception')
        assert logs[0]['is_data_uploaded']
        assert logs[0]['start_timestamp']
        assert logs[0]['end_timestamp']
        assert logs[0]['status'] == 'Failure'
        assert logs[0]['event_status'] == EVENT_STATUS.COMPLETED.value

    def test_trigger_faq_importer_overwrite(self, monkeypatch):
        def _mock_execution(*args, **kwargs):
            return None

        def _mock_aggregation(*args, **kwargs):
            return {}

        monkeypatch.setattr(MongoProcessor, "delete_all_faq", _mock_execution)
        monkeypatch.setattr(MongoProcessor, 'get_training_examples_as_dict', _mock_aggregation)

        bot = 'test_faqs'
        user = 'test'
        faq = "Questions,Answer,\nWhat is Digite?, IT Company,\nHow are you?, I am good,\nWhat day is it?, It is Thursday,\n".encode()
        file = UploadFile(filename="faq.csv", file=BytesIO(faq))
        FaqDataImporterEvent(bot, user).validate(training_data_file=file)
        FaqDataImporterEvent(bot, user, overwrite=True).execute()
        bot_data_home_dir = os.path.join('training_data', bot)
        assert not os.path.exists(bot_data_home_dir)
        logs = list(DataImporterLogProcessor.get_logs(bot))
        assert len(logs) == 2
        assert not logs[0].get('intents').get('data')
        assert len(logs[0].get('utterances').get('data')) == 0
        assert len(logs[0].get('training_examples').get('data')) == 0
        assert not logs[0].get('exception')
        assert logs[0]['is_data_uploaded']
        assert logs[0]['start_timestamp']
        assert logs[0]['end_timestamp']
        assert logs[0]['status'] == 'Success'
        assert logs[0]['event_status'] == EVENT_STATUS.COMPLETED.value

    def test_trigger_faq_importer_validate_exception(self, monkeypatch):
        bot = 'test_faqs'
        user = 'test'

        FaqDataImporterEvent(bot, user).execute()
        logs = list(DataImporterLogProcessor.get_logs(bot))
        assert len(logs) == 3
        assert not logs[0].get('intents').get('data')
        assert not logs[0].get('stories').get('data')
        assert not logs[0].get('utterances').get('data')
        assert logs[0].get('exception') == 'Folder does not exists!'
        assert not logs[0]['is_data_uploaded']
        assert logs[0]['start_timestamp']
        assert logs[0]['end_timestamp']
        assert logs[0]['status'] == 'Failure'
        assert logs[0]['event_status'] == EVENT_STATUS.FAIL.value

    def test_trigger_faq_importer_validate_only_append_mode(self, monkeypatch):
        def _mock_execution(*args, **kwargs):
            return None

        def _mock_aggregation(*args, **kwargs):
            return {}

        monkeypatch.setattr(MongoProcessor, "delete_all_faq", _mock_execution)
        monkeypatch.setattr(MongoProcessor, 'get_training_examples_as_dict', _mock_aggregation)
        bot = 'test_faqs'
        user = 'test'
        faq = "Questions,Answer,\nWhat is your name?, Nupur Khare,\nWhen is your birthday?, 15 June 2000,\nHow are you feeling today?, Not good,\n".encode()
        file = UploadFile(filename="faq.csv", file=BytesIO(faq))
        FaqDataImporterEvent(bot, user, overwrite=False).validate(training_data_file=file)
        FaqDataImporterEvent(bot, user, overwrite=False).execute()
        bot_data_home_dir = os.path.join('training_data', bot)
        assert not os.path.exists(bot_data_home_dir)
        logs = list(DataImporterLogProcessor.get_logs(bot))
        assert len(logs) == 4
        assert not logs[0].get('intents').get('data')
        print(logs[0].get('utterances').get('data'))
        assert len(logs[0].get('utterances').get('data')) == 0
        assert len(logs[0].get('training_examples').get('data')) == 0
        print(logs[0].get('exception'))
        assert not logs[0].get('exception')
        assert logs[0]['is_data_uploaded']
        assert logs[0]['start_timestamp']
        assert logs[0]['end_timestamp']
        assert logs[0]['status'] == 'Success'
        assert logs[0]['event_status'] == EVENT_STATUS.COMPLETED.value

    def test_trigger_model_testing_event_run_tests_on_model_no_model_found_1(self):
        bot = 'test_events_bot'
        user = 'test_user'
        event = ModelTestingEvent(bot, user)
        with pytest.raises(AppException, match='No model trained yet. Please train a model to test'):
            event.validate()

    def test_trigger_model_testing_event_run_tests_on_model_no_model_found_2(self):
        bot = 'test_events_bot'
        user = 'test_user'
        ModelTestingEvent(bot, user).execute()
        logs, count = ModelTestingLogProcessor.get_logs(bot)
        assert count == 1
        assert logs[0].get('exception').__contains__('Model testing failed: Folder does not exists!')
        assert logs[0]['start_timestamp']
        assert not logs[0].get('stories')
        assert not logs[0].get('nlu')
        assert logs[0].get('end_timestamp')
        assert not logs[0].get('status')
        assert logs[0]['event_status'] == EVENT_STATUS.FAIL.value
        assert not os.path.exists(os.path.join('./testing_data', bot))

    @pytest.fixture
    def load_data(self):
        async def _read_and_get_data(config_path: str, domain_path: str, nlu_path: str, stories_path: str, bot: str,
                                     user: str):
            data_path = os.path.join(pytest.tmp_dir, str(uuid.uuid4()))
            os.mkdir(data_path)
            shutil.copy2(nlu_path, data_path)
            shutil.copy2(stories_path, data_path)
            importer = RasaFileImporter.load_from_config(config_path=config_path,
                                                         domain_path=domain_path,
                                                         training_data_paths=data_path)
            domain = importer.get_domain()
            story_graph = importer.get_stories()
            config = importer.get_config()
            nlu = importer.get_nlu_data(config.get('language'))

            processor = MongoProcessor()
            processor.save_training_data(bot, user, config, domain, story_graph, nlu, overwrite=True,
                                         what=REQUIREMENTS.copy()-{"chat_client_config"})

        return _read_and_get_data

    @pytest.fixture
    def create_model(self):
        def move_model(path: str, bot: str, remove_nlu_model=False):
            bot_training_home_dir = os.path.join('models', bot)
            if not os.path.exists(bot_training_home_dir):
                os.mkdir(bot_training_home_dir)
            if remove_nlu_model:
                tmp = os.path.join(bot_training_home_dir, 'tmp')
                shutil.unpack_archive(path, tmp)
                shutil.rmtree(os.path.join(tmp, 'nlu'))
                shutil.make_archive(tmp, format='gztar', root_dir=bot_training_home_dir)
                shutil.rmtree(tmp)
            else:
                shutil.copy2(path, bot_training_home_dir)

        return move_model

    def test_trigger_model_training_event(self, load_data, create_model):
        bot = 'test_events_bot'
        user = 'test_user'
        config_path = 'tests/testing_data/model_tester/config.yml'
        domain_path = 'tests/testing_data/model_tester/domain.yml'
        nlu_path = 'tests/testing_data/model_tester/nlu_with_entities/nlu.yml'
        stories_path = 'tests/testing_data/model_tester/training_stories_success/stories.yml'
        asyncio.run(load_data(config_path, domain_path, nlu_path, stories_path, bot, user))
        pytest.model_path = ModelTrainingEvent(bot, user).execute()
        assert not Utility.check_empty_string(pytest.model_path)

    @mock.patch("kairon.test.test_models.ModelTester.run_test_on_stories")
    def test_trigger_model_testing_event_run_tests_on_model(self, mocked_run_stories, load_data, create_model):
        bot = 'test_events_bot'
        user = 'test_user'
        config_path = 'tests/testing_data/model_tester/config.yml'
        domain_path = 'tests/testing_data/model_tester/domain.yml'
        nlu_path = 'tests/testing_data/model_tester/nlu_success/nlu.yml'
        stories_path = 'tests/testing_data/model_tester/training_stories_success/stories.yml'
        asyncio.run(load_data(config_path, domain_path, nlu_path, stories_path, bot, user))

        mocked_run_stories.return_value = {
            "precision": 0.91,
            "f1": 0.98,
            "accuracy": 0.99,
            "failed_stories": [],
        }
        ModelTestingEvent(bot, user, run_e2e=False).execute()
        logs, row_count = ModelTestingLogProcessor.get_logs(bot)
        assert row_count == 2
        assert not logs[0].get('exception')
        assert logs[0]['start_timestamp']
        assert logs[0].get('data')
        assert logs[0].get('end_timestamp')
        assert not Utility.check_empty_string(logs[0].get('status'))
        assert logs[0]['event_status'] == EVENT_STATUS.COMPLETED.value
        assert not os.path.exists(os.path.join('./testing_data', bot))

    def test_trigger_model_testing_event_connection_error(self):
        bot = 'test_events_bot'
        user = 'test_user'
        with pytest.raises(AppException, match='Failed to connect to service: *'):
            ModelTestingEvent(bot, user).enqueue()
        logs, row_count = ModelTestingLogProcessor.get_logs(bot)
        assert not os.path.exists(os.path.join('./testing_data', bot))

    def test_trigger_model_testing(self, load_data, create_model, monkeypatch):
        bot = 'test_events_bot'
        user = 'test_user'

        def _mock_test_result(*args, **kwargs):
            stories = {
                "precision": 0.91,
                "f1": 0.98,
                "accuracy": 0.99,
                "failed_stories": [],
            }
            nlu = {
                "precision": 0.91,
                "f1": 0.98,
                "accuracy": 0.99,
                "response_selection_evaluation": [],
                "intent_evaluation": [],
            }
            return nlu, stories

        monkeypatch.setattr(ModelTester, "run_tests_on_model", _mock_test_result)
        ModelTestingEvent(bot, user).execute()
        config_path = 'tests/testing_data/model_tester/config.yml'
        domain_path = 'tests/testing_data/model_tester/domain.yml'
        nlu_path = 'tests/testing_data/model_tester/nlu_success/nlu.yml'
        stories_path = 'tests/testing_data/model_tester/test_stories_success/test_stories.yml'
        asyncio.run(load_data(config_path, domain_path, nlu_path, stories_path, bot, user))

        logs, row_count = ModelTestingLogProcessor.get_logs(bot)
        assert row_count == 3
        assert not logs[0].get('exception')
        assert logs[0]['start_timestamp']
        assert logs[0].get('end_timestamp')
        assert logs[0].get('status')
        assert logs[0].get('data')
        assert logs[0]['event_status'] == EVENT_STATUS.COMPLETED.value
        assert not os.path.exists(os.path.join('./testing_data', bot))

    @responses.activate
    def test_trigger_model_testing_event(self):
        bot = 'test_events_bot'
        user = 'test_user'
        event_url = urljoin(Utility.environment['events']['server_url'], f"/api/events/execute/{EventClass.model_testing}")
        responses.add("POST",
                      event_url,
                      json={"success": True, "message": "Event triggered successfully!"},
                      status=200,
                      match=[
                          responses.matchers.json_params_matcher(
                              {"data": {'bot': bot, 'user': user, 'augment_data': '--augment'}, "cron_exp": None, "timezone": None})],
                      )
        ModelTestingEvent(bot, user).enqueue()

        logs, row_count = ModelTestingLogProcessor.get_logs(bot)
        assert row_count == 4
        assert not logs[0].get('exception')
        assert logs[0]['start_timestamp']
        assert not logs[0].get('end_timestamp')
        assert not logs[0].get('status')
        assert logs[0]['event_status'] == EVENT_STATUS.ENQUEUED.value
        assert logs[0]['is_augmented']
        assert not os.path.exists(os.path.join('./testing_data', bot))

    @responses.activate
    def test_trigger_model_testing_event_2(self):
        bot = 'test_events_bot_2'
        user = 'test_user'
        event_url = urljoin(Utility.environment['events']['server_url'], f"/api/events/execute/{EventClass.model_testing}")
        responses.add("POST",
                      event_url,
                      json={"success": True, "message": "Event triggered successfully!"},
                      status=200,
                      match=[
                          responses.matchers.json_params_matcher(
                              {"data": {'bot': bot, 'user': user, 'augment_data': ''}, "cron_exp": None, "timezone": None})],
                      )
        ModelTestingEvent(bot, user, augment_data=False).enqueue()

        logs, row_count = ModelTestingLogProcessor.get_logs(bot)
        assert row_count == 1
        assert not logs[0].get('exception')
        assert logs[0]['start_timestamp']
        assert not logs[0].get('end_timestamp')
        assert not logs[0].get('status')
        assert logs[0]['event_status'] == EVENT_STATUS.ENQUEUED.value
        assert not logs[0]['is_augmented']
        assert not os.path.exists(os.path.join('./testing_data', bot))

    @responses.activate
    def test_trigger_history_deletion_for_bot(self):
        from datetime import datetime
        bot = 'test_events_bot'
        user = 'test_user'
        till_date = datetime.utcnow().date()
        sender_id = ""
        event_url = urljoin(Utility.environment['events']['server_url'], f"/api/events/execute/{EventClass.delete_history}")
        responses.add("POST",
                      event_url,
                      json={"success": True, "message": "Event triggered successfully!"},
                      status=200,
                      match=[
                          responses.matchers.json_params_matcher(
                              {"data": {'bot': bot, 'user': user, 'till_date': Utility.convert_date_to_string(till_date),
                               'sender_id': sender_id}, "cron_exp": None, "timezone": None})],
                      )
        event = DeleteHistoryEvent(bot, user, till_date=till_date, sender_id=None)
        event.validate()
        event.enqueue()

        logs = list(HistoryDeletionLogProcessor.get_logs(bot))
        assert len(logs) == 1
        assert not logs[0].get('exception')
        assert logs[0]['start_timestamp']
        assert not logs[0].get('end_timestamp')
        assert logs[0]['status'] == EVENT_STATUS.ENQUEUED.value

    @responses.activate
    @mongomock.patch(servers=(('localhost', 27017),))
    @patch("kairon.shared.channels.whatsapp.bsp.dialog360.BSP360Dialog.get_partner_auth_token", autospec=True)
    @patch("kairon.chat.handlers.channels.clients.whatsapp.dialog360.BSP360Dialog.send_template_message")
    @patch("kairon.shared.data.processor.MongoProcessor.get_bot_settings")
    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    @patch("kairon.shared.utils.Utility.is_exist", autospec=True)
    def test_execute_message_broadcast_with_logs_modification(self, mock_is_exist, mock_channel_config,
                                                              mock_get_bot_settings, mock_send,
                                                              mock_get_partner_auth_token):
        bot = 'test_execute_message_broadcast_with_logs_modification'
        user = 'test_user'
        config = {
            "name": "one_time_schedule", "broadcast_type": "static",
            "connector_type": "whatsapp",
            "recipients_config": {
                "recipients": "918958030541,"
            },
            "template_config": [
                {
                    'language': 'hi',
                    "template_id": "brochure_pdf",
                }
            ]
        }
        template = [
            {
                "format": "TEXT",
                "text": "Kisan Suvidha Program Follow-up",
                "type": "HEADER"
            },
            {
                "text": "Hello! As a part of our Kisan Suvidha program, I am dedicated to supporting farmers like you in maximizing your crop productivity and overall yield.\n\nI wanted to reach out to inquire if you require any assistance with your current farming activities. Our team of experts, including our skilled agronomists, are here to lend a helping hand wherever needed.",
                "type": "BODY"
            },
            {
                "text": "reply with STOP to unsubscribe",
                "type": "FOOTER"
            },
            {
                "buttons": [
                    {
                        "text": "Connect to Agronomist",
                        "type": "QUICK_REPLY"
                    }
                ],
                "type": "BUTTONS"
            }
        ]

        url = f"http://localhost:5001/api/events/execute/{EventClass.message_broadcast}?is_scheduled=False"
        template_url = 'https://hub.360dialog.io/api/v2/partners/sdfghjkjhgfddfghj/waba_accounts/asdfghjk/waba_templates?filters={"business_templates.name": "brochure_pdf"}&sort=business_templates.name'
        responses.add(
            "POST", url,
            json={"message": "Event Triggered!", "success": True, "error_code": 0, "data": None}
        )
        responses.add(
            "GET", template_url,
            json={"waba_templates": [
                {"category": "MARKETING", "components": template, "name": "agronomy_support", "language": "hi"}]}
        )

        mock_get_bot_settings.return_value = {"whatsapp": "360dialog", "notification_scheduling_limit": 4,
                                              "dynamic_broadcast_execution_timeout": 21600}
        mock_channel_config.return_value = {
            "config": {"access_token": "shjkjhrefdfghjkl", "from_phone_number_id": "918958030415",
                       "waba_account_id": "asdfghjk"}}
        mock_send.return_value = {"contacts": [{"input": "+55123456789", "status": "valid", "wa_id": "55123456789"}],
                                  "messages": [{"id": 'wamid.HBgLMTIxMTU1NTc5NDcVAgARGBIyRkQxREUxRDJFQUJGMkQ3NDIZ',
                                                "message_status": 'accepted'}]}
        mock_get_partner_auth_token.return_value = None

        ChannelLogs(
            type=ChannelTypes.WHATSAPP.value,
            status='Failed',
            data={'id': 'CONVERSATION_ID', 'expiration_timestamp': '1691598412',
                  'origin': {'type': 'business_initated'}},
            initiator='business_initated',
            message_id='wamid.HBgLMTIxMTU1NTc5NDcVAgARGBIyRkQxREUxRDJFQUJGMkQ3NDIZ',
            errors=[
                {
                    "code": 130472,
                    "title": "User's number is part of an experiment",
                    "message": "User's number is part of an experiment",
                    "error_data": {
                        "details": "Failed to send message because this user's phone number is part of an experiment"
                    },
                    "href": "https://developers.facebook.com/docs/whatsapp/cloud-api/support/error-codes/"
                }
            ],
            bot=bot,
            user=user
        ).save()
        with patch.dict(Utility.environment["channels"]["360dialog"], {"partner_id": "sdfghjkjhgfddfghj"}):
            event = MessageBroadcastEvent(bot, user)
            event.validate()
            event_id = event.enqueue(EventRequestType.trigger_async.value, config=config)
            event.execute(event_id)

        logs = MessageBroadcastProcessor.get_broadcast_logs(bot)
        assert len(logs[0]) == logs[1] == 2
        logs[0][0].pop("timestamp")
        reference_id = logs[0][0].get("reference_id")
        logged_config = logs[0][0]
        assert logged_config == {'reference_id': reference_id, 'log_type': 'send', "event_id": event_id,
                                 'bot': 'test_execute_message_broadcast_with_logs_modification', 'status': 'Failed',
                                 'api_response': {
                                     'contacts': [{'input': '+55123456789', 'status': 'valid', 'wa_id': '55123456789'}],
                                     'messages': [{'id': 'wamid.HBgLMTIxMTU1NTc5NDcVAgARGBIyRkQxREUxRDJFQUJGMkQ3NDIZ',
                                                   'message_status': 'accepted'}]}, 'recipient': '918958030541',
                                 'template_params': None, 'template_name': 'brochure_pdf',
                                 'language_code': 'hi', 'namespace': None, 'retry_count': 0, 'template': [
                {'format': 'TEXT', 'text': 'Kisan Suvidha Program Follow-up', 'type': 'HEADER'}, {
                    'text': 'Hello! As a part of our Kisan Suvidha program, I am dedicated to supporting farmers like you in maximizing your crop productivity and overall yield.\n\nI wanted to reach out to inquire if you require any assistance with your current farming activities. Our team of experts, including our skilled agronomists, are here to lend a helping hand wherever needed.',
                    'type': 'BODY'}, {'text': 'reply with STOP to unsubscribe', 'type': 'FOOTER'},
                {'buttons': [{'text': 'Connect to Agronomist', 'type': 'QUICK_REPLY'}], 'type': 'BUTTONS'}], 'errors': [
                {'code': 130472, 'title': "User's number is part of an experiment",
                 'message': "User's number is part of an experiment", 'error_data': {
                    'details': "Failed to send message because this user's phone number is part of an experiment"},
                 'href': 'https://developers.facebook.com/docs/whatsapp/cloud-api/support/error-codes/'}]}
        assert ChannelLogs.objects(bot=bot,
                                   message_id='wamid.HBgLMTIxMTU1NTc5NDcVAgARGBIyRkQxREUxRDJFQUJGMkQ3NDIZ').get().campaign_id == reference_id
        result = MessageBroadcastProcessor.get_channel_metrics(ChannelTypes.WHATSAPP.value, bot)
        assert result == [
            {
                'campaign_metrics': [
                    {
                        'retry_count': 0,
                        'statuses': {'Failed': 1}
                    }
                ],
                'campaign_id': reference_id
            }
        ]

    @responses.activate
    @mongomock.patch(servers=(('localhost', 27017),))
    @patch("kairon.shared.channels.whatsapp.bsp.dialog360.BSP360Dialog.get_partner_auth_token", autospec=True)
    @patch("kairon.chat.handlers.channels.clients.whatsapp.dialog360.BSP360Dialog.send_template_message")
    @patch("kairon.shared.data.processor.MongoProcessor.get_bot_settings")
    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    @patch("kairon.shared.utils.Utility.is_exist", autospec=True)
    def test_execute_message_broadcast_with_static_values(self, mock_is_exist, mock_channel_config,
                                                           mock_get_bot_settings, mock_send, mock_get_partner_auth_token):
        bot = 'test_execute_message_broadcast'
        user = 'test_user'
        config = {
            "name": "one_time_schedule", "broadcast_type": "static",
            "connector_type": "whatsapp",
            "recipients_config": {
                "recipients": "918958030541,"
            },
            "retry_count": 0,
            "template_config": [
                {
                    'language': 'hi',
                    "template_id": "brochure_pdf",
                }
            ]
        }
        template = [
            {
                "format": "TEXT",
                "text": "Kisan Suvidha Program Follow-up",
                "type": "HEADER"
            },
            {
                "text": "Hello! As a part of our Kisan Suvidha program, I am dedicated to supporting farmers like you in maximizing your crop productivity and overall yield.\n\nI wanted to reach out to inquire if you require any assistance with your current farming activities. Our team of experts, including our skilled agronomists, are here to lend a helping hand wherever needed.",
                "type": "BODY"
            },
            {
                "text": "reply with STOP to unsubscribe",
                "type": "FOOTER"
            },
            {
                "buttons": [
                    {
                        "text": "Connect to Agronomist",
                        "type": "QUICK_REPLY"
                    }
                ],
                "type": "BUTTONS"
            }
        ]

        url = f"http://localhost:5001/api/events/execute/{EventClass.message_broadcast}?is_scheduled=False"
        template_url = 'https://hub.360dialog.io/api/v2/partners/sdfghjkjhgfddfghj/waba_accounts/asdfghjk/waba_templates?filters={"business_templates.name": "brochure_pdf"}&sort=business_templates.name'
        responses.add(
            "POST", url,
            json={"message": "Event Triggered!", "success": True, "error_code": 0, "data": None}
        )
        responses.add(
            "GET", template_url,
            json={"waba_templates": [
                {"category": "MARKETING", "components": template, "name": "agronomy_support", "language": "hi"}]}
        )

        mock_get_bot_settings.return_value = {"whatsapp": "360dialog", "notification_scheduling_limit": 4, "dynamic_broadcast_execution_timeout": 21600}
        mock_channel_config.return_value = {
            "config": {"access_token": "shjkjhrefdfghjkl", "from_phone_number_id": "918958030415",
                       "waba_account_id": "asdfghjk"}}
        mock_send.return_value = {"contacts": [{"input": "+55123456789", "status": "valid", "wa_id": "55123456789"}]}
        mock_get_partner_auth_token.return_value = None

        with patch.dict(Utility.environment["channels"]["360dialog"], {"partner_id": "sdfghjkjhgfddfghj"}):
            event = MessageBroadcastEvent(bot, user)
            event.validate()
            event_id = event.enqueue(EventRequestType.trigger_async.value, config=config)
            event.execute(event_id)

        logs = MessageBroadcastProcessor.get_broadcast_logs(bot)
        assert len(logs[0]) == logs[1] == 2
        logs[0][1].pop("timestamp")
        reference_id = logs[0][1].pop("reference_id")
        logged_config = logs[0][1].pop("config")
        logged_config.pop("_id")
        logged_config.pop("status")
        logged_config.pop("timestamp")
        logged_config.pop('pyscript_timeout')
        assert logged_config == config
        logs[0][1]['recipients'] = set(logs[0][1]['recipients'])
        assert logs[0][1] == {"event_id": event_id, 'log_type': 'common', 'bot': 'test_execute_message_broadcast', 'status': 'Completed',
                              'user': 'test_user', 'recipients': {'', '918958030541'},
                              'failure_cnt': 0, 'total': 2,
                              'Template 1': 'There are 2 recipients and 2 template bodies. Sending 2 messages to 2 recipients.'
                              }
        logs[0][0].pop("timestamp")
        assert logs[0][0] == {"event_id": event_id, 'reference_id': reference_id, 'log_type': 'send',
                              'bot': 'test_execute_message_broadcast', 'status': 'Success', 'api_response': {
                'contacts': [{'input': '+55123456789', 'status': 'valid', 'wa_id': '55123456789'}]},
                              'recipient': '918958030541', 'template_params': None, "template": template,
                              'template_name': 'brochure_pdf', 'language_code': 'hi', 'namespace': None,
                              'retry_count': 0}

        with pytest.raises(AppException, match="Notification settings not found!"):
            MessageBroadcastProcessor.get_settings(event_id, bot)

        settings = list(MessageBroadcastProcessor.list_settings(bot, status=False, name="one_time_schedule"))
        assert len(settings) == 1
        assert settings[0]["status"] == False

    @responses.activate
    @mongomock.patch(servers=(('localhost', 27017),))
    @patch("kairon.shared.channels.whatsapp.bsp.dialog360.BSP360Dialog.get_partner_auth_token", autospec=True)
    @patch("kairon.chat.handlers.channels.clients.whatsapp.dialog360.BSP360Dialog.send_template_message", autospec=True)
    @patch("kairon.shared.data.processor.MongoProcessor.get_bot_settings")
    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    @patch("kairon.shared.utils.Utility.is_exist", autospec=True)
    def test_execute_message_broadcast_with_dynamic_values(self, mock_is_exist, mock_channel_config,
                                                           mock_get_bot_settings, mock_send,
                                                           mock_get_partner_auth_token):
        bot = 'test_execute_dynamic_message_broadcast'
        user = 'test_user'
        params = [{"type": "header", "parameters": [{"type": "document", "document":
            {"link": "https://drive.google.com/uc?export=download&id=1GXQ43jilSDelRvy1kr3PNNpl1e21dRXm",
             "filename": "Brochure.pdf"}}]}]
        template = [
            {
                "format": "TEXT",
                "text": "Kisan Suvidha Program Follow-up",
                "type": "HEADER"
            },
            {
                "text": "Hello! As a part of our Kisan Suvidha program, I am dedicated to supporting farmers like you in maximizing your crop productivity and overall yield.\n\nI wanted to reach out to inquire if you require any assistance with your current farming activities. Our team of experts, including our skilled agronomists, are here to lend a helping hand wherever needed.",
                "type": "BODY"
            },
            {
                "text": "reply with STOP to unsubscribe",
                "type": "FOOTER"
            },
            {
                "buttons": [
                    {
                        "text": "Connect to Agronomist",
                        "type": "QUICK_REPLY"
                    }
                ],
                "type": "BUTTONS"
            }
        ]

        config = {
            "name": "one_time_schedule", "broadcast_type": "static",
            "connector_type": "whatsapp",
            "recipients_config": {
                "recipients": "9876543210, 876543212345",
            },
            "retry_count": 0,
            "template_config": [
                {
                    'language': 'hi',
                    "template_id": "brochure_pdf",
                    "data": str([params, params])
                }
            ]
        }

        url = f"http://localhost:5001/api/events/execute/{EventClass.message_broadcast}?is_scheduled=False"
        template_url = 'https://hub.360dialog.io/api/v2/partners/sdfghjkjhgfddfghj/waba_accounts/asdfghjk/waba_templates?filters={"business_templates.name": "brochure_pdf"}&sort=business_templates.name'
        responses.add(
            "POST", url,
            json={"message": "Event Triggered!", "success": True, "error_code": 0, "data": None}
        )
        responses.add(
            "GET", template_url,
            json={"waba_templates": [
                {"category": "MARKETING", "components": template, "name": "agronomy_support", "language": "hi"}]}
        )

        mock_get_bot_settings.return_value = {"whatsapp": "360dialog", "notification_scheduling_limit": 4,
                                              "dynamic_broadcast_execution_timeout": 21600}
        mock_channel_config.return_value = {
            "config": {"access_token": "shjkjhrefdfghjkl", "from_phone_number_id": "918958030415",
                       "waba_account_id": "asdfghjk"}}
        mock_send.return_value = {"contacts": [{"input": "+55123456789", "status": "valid", "wa_id": "55123456789"}]}
        mock_get_partner_auth_token.return_value = None

        with patch.dict(Utility.environment["channels"]["360dialog"], {"partner_id": "sdfghjkjhgfddfghj"}):
            event = MessageBroadcastEvent(bot, user)
            event.validate()
            event_id = event.enqueue(EventRequestType.trigger_async.value, config=config)
            event.execute(event_id)

        logs = MessageBroadcastProcessor.get_broadcast_logs(bot)
        print(logs)
        assert len(logs[0]) == logs[1] == 3
        logs[0][2].pop("timestamp")
        reference_id = logs[0][2].pop("reference_id")
        logged_config = logs[0][2].pop("config")
        logged_config.pop("_id")
        logged_config.pop("status")
        logged_config.pop("timestamp")
        logged_config.pop('pyscript_timeout')
        assert logged_config == config
        logs[0][2]['recipients'] = set(logs[0][2]['recipients'])
        assert logs[0][2] == {"event_id": event_id, 'log_type': 'common', 'bot': 'test_execute_dynamic_message_broadcast',
                              'status': 'Completed', 'user': 'test_user',
                              'recipients': {'876543212345', '9876543210'},
                              'template_params': [[{'type': 'header', 'parameters': [{'type': 'document', 'document': {
                                  'link': 'https://drive.google.com/uc?export=download&id=1GXQ43jilSDelRvy1kr3PNNpl1e21dRXm',
                                  'filename': 'Brochure.pdf'}}]}], [{'type': 'header', 'parameters': [
                                  {'type': 'document', 'document': {
                                      'link': 'https://drive.google.com/uc?export=download&id=1GXQ43jilSDelRvy1kr3PNNpl1e21dRXm',
                                      'filename': 'Brochure.pdf'}}]}]], 'failure_cnt': 0, 'total': 2,
                              'Template 1': 'There are 2 recipients and 4 template bodies. Sending 2 messages to 2 recipients.'
                              }
        logs[0][1].pop("timestamp")
        logs[0][1].pop("recipient")
        logs[0][0].pop("recipient")
        assert logs[0][1] == {"event_id": event_id, 'reference_id': reference_id, 'log_type': 'send', 'bot': bot, 'status': 'Success',
                              'api_response': {
                                  'contacts': [{'input': '+55123456789', 'status': 'valid', 'wa_id': '55123456789'}]},
                              'template_params': [{'type': 'header', 'parameters': [
                                  {'type': 'document', 'document': {
                                      'link': 'https://drive.google.com/uc?export=download&id=1GXQ43jilSDelRvy1kr3PNNpl1e21dRXm',
                                      'filename': 'Brochure.pdf'}}]}], "template": template,
                              'template_name': 'brochure_pdf', 'language_code': 'hi', 'namespace': None,
                              'retry_count': 0}
        logs[0][0].pop("timestamp")
        assert logs[0][0] == {"event_id": event_id, 'reference_id': reference_id, 'log_type': 'send', 'bot': bot, 'status': 'Success',
                              'api_response': {
                                  'contacts': [{'input': '+55123456789', 'status': 'valid', 'wa_id': '55123456789'}]},
                              'template_params': [{'type': 'header', 'parameters': [
                                  {'type': 'document', 'document': {
                                      'link': 'https://drive.google.com/uc?export=download&id=1GXQ43jilSDelRvy1kr3PNNpl1e21dRXm',
                                      'filename': 'Brochure.pdf'}}]}], "template": template,
                              'template_name': 'brochure_pdf', 'language_code': 'hi', 'namespace': None,
                              'retry_count': 0}
        with pytest.raises(AppException, match="Notification settings not found!"):
            MessageBroadcastProcessor.get_settings(event_id, bot)

        assert mock_send.call_args[0][1] == 'brochure_pdf'
        assert mock_send.call_args[0][2] in ['876543212345', '9876543210']
        assert mock_send.call_args[0][3] == 'hi'
        assert mock_send.call_args[0][4] == [{'type': 'header', 'parameters': [{'type': 'document', 'document': {
            'link': 'https://drive.google.com/uc?export=download&id=1GXQ43jilSDelRvy1kr3PNNpl1e21dRXm',
            'filename': 'Brochure.pdf'}}]}]

    @responses.activate
    @patch("kairon.chat.handlers.channels.clients.whatsapp.dialog360.BSP360Dialog.send_template_message", autospec=True)
    @patch("kairon.shared.data.processor.MongoProcessor.get_bot_settings")
    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    @patch("kairon.shared.utils.Utility.is_exist", autospec=True)
    def test_execute_message_broadcast_with_recipient_evaluation_failure(self, mock_is_exist, mock_channel_config,
                                                           mock_get_bot_settings, mock_send):
        bot = 'test_execute_dynamic_message_broadcast_recipient_evaluation_failure'
        user = 'test_user'
        config = {
            "name": "one_time_schedule", "broadcast_type": "static",
            "connector_type": "whatsapp",
            "recipients_config": {
                "recipients": None,
            },
            "retry_count": 0,
            "template_config": [
                {
                    'language': 'hi',
                    "template_id": "brochure_pdf",
                    "data": "[\n                {\n                    \"type\": \"header\",\n                    \"parameters\": [\n                        {\n                            \"type\": \"document\",\n                            \"document\": {\n                                \"link\": \"https://drive.google.com/uc?export=download&id=1GXQ43jilSDelRvy1kr3PNNpl1e21dRXm\",\n                                \"filename\": \"Brochure.pdf\"\n                            }\n                        }\n                    ]\n                }\n            ]"
                }
            ]
        }

        url = f"http://localhost:5001/api/events/execute/{EventClass.message_broadcast}?is_scheduled=False"
        responses.add(
            "POST", url,
            json={"message": "Event Triggered!", "success": True, "error_code": 0, "data": None}
        )

        mock_get_bot_settings.return_value = {"whatsapp": "360dialog", "notification_scheduling_limit": 4, "dynamic_broadcast_execution_timeout": 21600}
        mock_channel_config.return_value = {
            "config": {"access_token": "shjkjhrefdfghjkl", "from_phone_number_id": "918958030415"}}
        mock_send.return_value = {"contacts": [{"input": "+55123456789", "status": "valid", "wa_id": "55123456789"}]}

        event = MessageBroadcastEvent(bot, user)
        event.validate()
        event_id = event.enqueue(EventRequestType.trigger_async.value, config=config)
        event.execute(event_id)

        logs = MessageBroadcastProcessor.get_broadcast_logs(bot)
        assert len(logs[0]) == logs[1] == 1
        logs[0][0].pop("timestamp")
        reference_id = logs[0][0].pop("reference_id")
        assert reference_id
        logged_config = logs[0][0].pop("config")
        logged_config.pop("_id")
        logged_config.pop("status")
        logged_config.pop("timestamp")
        logged_config.pop('pyscript_timeout')
        assert not logged_config.pop("recipients_config")
        config.pop("recipients_config")
        assert logged_config == config
        assert logs[0][0] == {"event_id": event_id, 'log_type': 'common', 'bot': bot, 'status': 'Fail', 'user': user,
                              'exception': "Failed to evaluate recipients: 'recipients'"
                              }

        with pytest.raises(AppException, match="Notification settings not found!"):
            MessageBroadcastProcessor.get_settings(event_id, bot)

    @responses.activate
    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    @patch("kairon.shared.data.processor.MongoProcessor.get_bot_settings")
    @patch("kairon.shared.utils.Utility.is_exist", autospec=True)
    def test_execute_message_broadcast_expression_evaluation_failure(self, mock_is_exist, mock_get_bot_settings, mock_channel_config):
        bot = 'test_execute_message_broadcast_expression_evaluation_failure'
        user = 'test_user'
        config = {
            "name": "one_time_schedule", "broadcast_type": "static",
            "connector_type": "whatsapp",
            "recipients_config": {
                "recipients": "918958030541"
            },
            "template_config": [
                {
                    "template_id": "brochure_pdf",
                    "data": "[{type: body, parameters: [{type: text, text: Udit}]}]"
                }
            ]
        }

        url = f"http://localhost:5001/api/events/execute/{EventClass.message_broadcast}?is_scheduled=False"
        responses.add(
            "POST", url,
            json={"message": "Event Triggered!", "success": True, "error_code": 0, "data": None}
        )

        mock_get_bot_settings.return_value = {"whatsapp": "360dialog", "notification_scheduling_limit": 4, "dynamic_broadcast_execution_timeout": 21600}
        mock_channel_config.return_value = {
            "config": {"access_token": "shjkjhrefdfghjkl", "from_phone_number_id": "918958030415"}}

        event = MessageBroadcastEvent(bot, user)
        event.validate()
        event_id = event.enqueue(EventRequestType.trigger_async.value, config=config)
        event.execute(event_id)

        logs = MessageBroadcastProcessor.get_broadcast_logs(bot)
        assert len(logs[0]) == logs[1] == 1
        exception = logs[0][0].pop("exception")
        assert exception.startswith('Failed to evaluate template: ')

    @responses.activate
    @patch("kairon.chat.handlers.channels.clients.whatsapp.dialog360.BSP360Dialog.send_template_message", autospec=True)
    @patch("kairon.shared.data.processor.MongoProcessor.get_bot_settings")
    @patch("kairon.shared.utils.Utility.is_exist", autospec=True)
    def test_execute_message_broadcast_with_channel_deleted(self, mock_is_exist, mock_get_bot_settings, mock_send):
        bot = 'test_execute_message_broadcast_with_channel_deleted'
        user = 'test_user'
        config = {
            "name": "one_time_schedule", "broadcast_type": "static",
            "connector_type": "whatsapp",
            "recipients_config": {
                "recipients": "918958030541"
            },
            "retry_count": 0,
            "template_config": [
                {
                    'language': 'hi',
                    "template_id": "brochure_pdf",
                    "data": "[\n                {\n                    \"type\": \"header\",\n                    \"parameters\": [\n                        {\n                            \"type\": \"document\",\n                            \"document\": {\n                                \"link\": \"https://drive.google.com/uc?export=download&id=1GXQ43jilSDelRvy1kr3PNNpl1e21dRXm\",\n                                \"filename\": \"Brochure.pdf\"\n                            }\n                        }\n                    ]\n                }\n            ]"
                }
            ]
        }

        url = f"http://localhost:5001/api/events/execute/{EventClass.message_broadcast}?is_scheduled=False"
        responses.add(
            "POST", url,
            json={"message": "Event Triggered!", "success": True, "error_code": 0, "data": None}
        )

        mock_get_bot_settings.return_value = {"whatsapp": "360dialog", "notification_scheduling_limit": 4, "dynamic_broadcast_execution_timeout": 21600}
        mock_send.return_value = {"contacts": [{"input": "+55123456789", "status": "valid", "wa_id": "55123456789"}]}

        event = MessageBroadcastEvent(bot, user)
        event.validate()

        with patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config") as mock_channel_config:
            mock_channel_config.return_value = {
                "config": {"access_token": "shjkjhrefdfghjkl", "from_phone_number_id": "918958030415"}}
            event_id = event.enqueue(EventRequestType.trigger_async.value, config=config)

        event.execute(event_id)

        logs = MessageBroadcastProcessor.get_broadcast_logs(bot)
        assert len(logs[0]) == logs[1] == 1
        logs[0][0].pop("timestamp")
        reference_id = logs[0][0].pop("reference_id")
        assert reference_id
        logged_config = logs[0][0].pop("config")
        logged_config.pop("_id")
        logged_config.pop("status")
        logged_config.pop("timestamp")
        logged_config.pop('pyscript_timeout')
        assert logged_config == config
        exception = logs[0][0].pop("exception")
        assert exception.startswith("Whatsapp channel config not found!")
        assert logs[0][0] == {"event_id": event_id, 'log_type': 'common', 'bot': bot, 'status': 'Fail', 'user': user, 'recipients': ['918958030541']}

        with pytest.raises(AppException, match="Notification settings not found!"):
            MessageBroadcastProcessor.get_settings(event_id, bot)

    @responses.activate
    @mongomock.patch(servers=(('localhost', 27017),))
    @patch("kairon.shared.channels.whatsapp.bsp.dialog360.BSP360Dialog.get_partner_auth_token", autospec=True)
    @patch("kairon.shared.data.processor.MongoProcessor.get_bot_settings")
    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    @patch("kairon.chat.handlers.channels.clients.whatsapp.dialog360.BSP360Dialog.send_template_message")
    @patch("kairon.shared.utils.Utility.is_exist", autospec=True)
    def test_execute_message_broadcast_evaluate_template_parameters(self, mock_is_exist, mock_send, mock_channel_config, mock_get_bot_settings, mock_bsp_auth_token):
        bot = 'test_execute_message_broadcast_evaluate_template_parameters'
        user = 'test_user'
        template_script = str([[{'body': 'Udit Pandey'}]])

        config = {
            "name": "one_time_schedule", "broadcast_type": "static",
            "connector_type": "whatsapp",
            "recipients_config": {
                "recipients": "918958030541,"
            },
            "retry_count": 0,
            "template_config": [
                {
                    'language': 'hi',
                    "template_id": "agronomy_support",
                    "data": template_script,
                }
            ]
        }
        template = [
                {
                    "format": "TEXT",
                    "text": "Kisan Suvidha Program Follow-up",
                    "type": "HEADER"
                },
                {
                    "text": "Hello! As a part of our Kisan Suvidha program, I am dedicated to supporting farmers like you in maximizing your crop productivity and overall yield.\n\nI wanted to reach out to inquire if you require any assistance with your current farming activities. Our team of experts, including our skilled agronomists, are here to lend a helping hand wherever needed.",
                    "type": "BODY"
                },
                {
                    "text": "reply with STOP to unsubscribe",
                    "type": "FOOTER"
                },
                {
                    "buttons": [
                        {
                            "text": "Connect to Agronomist",
                            "type": "QUICK_REPLY"
                        }
                    ],
                    "type": "BUTTONS"
                }
            ]

        mock_bsp_auth_token.return_value = "kdjfnskjksjfksjf"
        url = f"http://localhost:5001/api/events/execute/{EventClass.message_broadcast}?is_scheduled=False"
        template_url = 'https://hub.360dialog.io/api/v2/partners/sdfghjkjhgfddfghj/waba_accounts/asdfghjk/waba_templates?filters={"business_templates.name": "agronomy_support"}&sort=business_templates.name'
        responses.add(
            "POST", url,
            json={"message": "Event Triggered!", "success": True, "error_code": 0, "data": None}
        )
        responses.add(
            "GET", template_url,
            json={"waba_templates": [
                {"category": "MARKETING", "components": template, "name": "agronomy_support", "language": "hi"}]}
        )
        mock_channel_config.return_value = {"config": {"access_token": "shjkjhrefdfghjkl", "from_phone_number_id": "918958030415", "waba_account_id": "asdfghjk"}}
        mock_get_bot_settings.return_value = {"whatsapp": "360dialog", "notification_scheduling_limit": 10, "dynamic_broadcast_execution_timeout": 21600}
        mock_send.return_value = {
            "contacts": [
                {"input": "+55123456789", "status": "valid", "wa_id": "55123456789"}
            ],
            "messages": [
                {
                    "id": "wamid.HBgLMTIxMTU1NTc5NDcVAgARGBIyRkQxREUxRDJFQUJGMkQ3NDIZ"
                }
            ]
        }

        ChannelLogs(
            type=ChannelTypes.WHATSAPP.value,
            status='Failed',
            data={'id': 'CONVERSATION_ID', 'expiration_timestamp': '1691598412',
                  'origin': {'type': 'business_initated'}},
            initiator='business_initated',
            message_id='wamid.HBgLMTIxMTU1NTc5NDcVAgARGBIyRkQxREUxRDJFQUJGMkQ3NDIZ',
            errors=[
                {
                    "code": 130472,
                    "title": "User's number is part of an experiment",
                    "message": "User's number is part of an experiment",
                    "error_data": {
                        "details": "Failed to send message because this user's phone number is part of an experiment"
                    },
                    "href": "https://developers.facebook.com/docs/whatsapp/cloud-api/support/error-codes/"
                }
            ],
            bot=bot,
            user=user
        ).save()

        with patch.dict(Utility.environment["channels"]["360dialog"], {"partner_id": "sdfghjkjhgfddfghj"}):
            event = MessageBroadcastEvent(bot, user)
            event.validate()
            event_id = event.enqueue(EventRequestType.trigger_async.value, config=config)
            event.execute(event_id)

        logs = MessageBroadcastProcessor.get_broadcast_logs(bot)

        coll = MessageBroadcastProcessor.get_db_client(bot)
        history = list(coll.find({}))
        print(history)
        history[0].pop("timestamp")
        history[0].pop("_id")
        history[0].pop("conversation_id")
        assert history[0] == {
            'type': 'broadcast', 'sender_id': '918958030541',
            'data': {'name': 'agronomy_support', 'template': template, 'template_params': [{'body': 'Udit Pandey'}],},
            'status': 'Failed'
        }

        assert len(logs[0]) == logs[1] == 2
        logs[0][1].pop("timestamp")
        reference_id = logs[0][1].pop("reference_id")
        logged_config = logs[0][1].pop("config")
        logged_config.pop('pyscript_timeout')
        logged_config.pop("_id")
        logged_config.pop("status")
        logged_config.pop("timestamp")
        assert logged_config == config
        logs[0][1]['recipients'] = set(logs[0][1]['recipients'])
        assert logs[0][1] == {"event_id": event_id, 'log_type': 'common', 'bot': bot, 'status': 'Completed',
                              'user': 'test_user', 'recipients': {'918958030541', ''}, 'failure_cnt': 0, 'total': 2,
                              'template_params': [[{'body': 'Udit Pandey'}]],
                              'Template 1': 'There are 2 recipients and 2 template bodies. Sending 2 messages to 2 recipients.'
                              }
        logs[0][0].pop("timestamp")
        assert logs[0][0] == {"event_id": event_id, 'reference_id': reference_id, 'log_type': 'send', 'template': template,
                              'bot': bot, 'status': 'Failed',
                              'api_response': {
                                  'contacts': [{'input': '+55123456789', 'status': 'valid', 'wa_id': '55123456789'}],
                              'messages': [{'id': 'wamid.HBgLMTIxMTU1NTc5NDcVAgARGBIyRkQxREUxRDJFQUJGMkQ3NDIZ'}]},
                              'recipient': '918958030541', 'template_params': [{'body': 'Udit Pandey'}],
                              'template_name': 'agronomy_support', 'language_code': 'hi', 'namespace': None,
                              'retry_count': 0,
                              'errors': [
                                  {'code': 130472, 'title': "User's number is part of an experiment",
                                   'message': "User's number is part of an experiment",
                                   'error_data': {
                                       'details': "Failed to send message because this user's phone number is part of an experiment"},
                                   'href': 'https://developers.facebook.com/docs/whatsapp/cloud-api/support/error-codes/'}
                              ]}

        with pytest.raises(AppException, match="Notification settings not found!"):
            MessageBroadcastProcessor.get_settings(event_id, bot)

        settings = list(MessageBroadcastProcessor.list_settings(bot, status=False, name="one_time_schedule"))
        assert len(settings) == 1
        assert settings[0]["status"] is False

    def test_base_scheduler_class(self):
        with pytest.raises(AppException, match=f"'model_training' is not a valid event server request!"):
            MessageBroadcastEvent("test", "test").enqueue("model_training")

        for event_request_type in [EventRequestType.trigger_async.value, EventRequestType.add_schedule.value,
                                   EventRequestType.update_schedule.value]:
            with pytest.raises(Exception):
                ScheduledEventsBase("test", "test").enqueue(event_request_type, config={})

    @responses.activate
    @mongomock.patch(servers=(('localhost', 27017),))
    @patch("kairon.shared.channels.whatsapp.bsp.dialog360.BSP360Dialog.get_partner_auth_token", autospec=True)
    @patch("kairon.chat.handlers.channels.clients.whatsapp.dialog360.BSP360Dialog.send_template_message", autospec=True)
    @patch("kairon.shared.data.processor.MongoProcessor.get_bot_settings")
    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    @patch("kairon.shared.utils.Utility.is_exist", autospec=True)
    def test_execute_message_broadcast_with_pyscript(self, mock_is_exist, mock_channel_config,
                                                           mock_get_bot_settings, mock_send, mock_get_partner_auth_token):
        bot = 'test_execute_message_broadcast_with_pyscript'
        user = 'test_user'
        script = """
            api_response = requests.get("http://kairon.local", headers={"api_key": "asdfghjkl", "access_key": "dsfghjkl"})
            api_response = api_response.json()
            log(**api_response)

            components = [{'type': 'header', 'parameters': [{'type': 'document', 'document': {
                                  'link': 'https://drive.google.com/uc?export=download&id=1GXQ43jilSDelRvy1kr3PNNpl1e21dRXm',
                                  'filename': 'Brochure.pdf'}}]}]
            i = 0
            for contact in api_response["contacts"]:
                resp = send_msg("brochure_pdf", contact, components=components, namespace="13b1e228_4a08_4d19_a0da_cdb80bc76380")
                log(i=i, contact=contact, whatsapp_response=resp)            
            """
        script = textwrap.dedent(script)
        config = {
            "name": "one_time_schedule", "broadcast_type": "dynamic",
            "connector_type": "whatsapp",
            "pyscript": script,
            "retry_count": 0
        }
        template = [
                {
                    "format": "TEXT",
                    "text": "Kisan Suvidha Program Follow-up",
                    "type": "HEADER"
                },
                {
                    "text": "Hello! As a part of our Kisan Suvidha program, I am dedicated to supporting farmers like you in maximizing your crop productivity and overall yield.\n\nI wanted to reach out to inquire if you require any assistance with your current farming activities. Our team of experts, including our skilled agronomists, are here to lend a helping hand wherever needed.",
                    "type": "BODY"
                },
                {
                    "text": "reply with STOP to unsubscribe",
                    "type": "FOOTER"
                },
                {
                    "buttons": [
                        {
                            "text": "Connect to Agronomist",
                            "type": "QUICK_REPLY"
                        }
                    ],
                    "type": "BUTTONS"
                }
            ]

        url = f"http://localhost:5001/api/events/execute/{EventClass.message_broadcast}?is_scheduled=False"
        template_url = 'https://hub.360dialog.io/api/v2/partners/sdfghjkjhgfddfghj/waba_accounts/asdfghjk/waba_templates?filters={"business_templates.name": "brochure_pdf"}&sort=business_templates.name'
        responses.add(
            "POST", url,
            json={"message": "Event Triggered!", "success": True, "error_code": 0, "data": None}
        )
        responses.add(
            "GET", "http://kairon.local",
            match=[matchers.header_matcher({"api_key": "asdfghjkl", "access_key": "dsfghjkl"})],
            json={"contacts": ["9876543210", "876543212345"]}
        )
        responses.add(
            "GET", template_url,
            json={"waba_templates": [
                {"category": "MARKETING", "components": template, "name": "brochure_pdf", "language": "hi"}]}
        )

        mock_get_bot_settings.return_value = {"whatsapp": "360dialog", "notification_scheduling_limit": 4, "dynamic_broadcast_execution_timeout": 21600}
        mock_channel_config.return_value = {
            "config": {"access_token": "shjkjhrefdfghjkl", "from_phone_number_id": "918958030415", "waba_account_id": "asdfghjk"}}
        mock_send.return_value = {"contacts": [{"input": "+55123456789", "status": "valid", "wa_id": "55123456789"}]}
        mock_get_partner_auth_token.return_value = None

        with patch.dict(Utility.environment["channels"]["360dialog"], {"partner_id": "sdfghjkjhgfddfghj"}):
            event = MessageBroadcastEvent(bot, user)
            event.validate()
            event_id = event.enqueue(EventRequestType.trigger_async.value, config=config)
            event.execute(event_id)

        logs = MessageBroadcastProcessor.get_broadcast_logs(bot)

        # Current pyscript runner is created in separate process to support actor timeout.
        # Because of this, we are not able to assert below statements. Hence, commenting out for now.
        # assert len(logs[0]) == logs[1] == 6
        # [log.pop("timestamp") for log in logs[0]]
        # reference_id = logs[0][0].get("reference_id")
        #
        # expected_logs = [
        #     {'bot': bot, 'contact': '876543212345', 'i': 0, 'log_type': 'self',
        #      'reference_id': reference_id, 'whatsapp_response': {
        #         'contacts': [{'input': '+55123456789', 'status': 'valid', 'wa_id': '55123456789'}]}},
        #     {'reference_id': reference_id, 'log_type': 'send', 'bot': bot, 'status': 'Success',
        #      'api_response': {'contacts': [{'input': '+55123456789', 'status': 'valid', 'wa_id': '55123456789'}]},
        #      'recipient': '876543212345', 'template_params':
        #          [{'type': 'header', 'parameters': [{'type': 'document', 'document': {
        #              'link': 'https://drive.google.com/uc?export=download&id=1GXQ43jilSDelRvy1kr3PNNpl1e21dRXm',
        #              'filename': 'Brochure.pdf'}}]}]},
        #     {'reference_id': reference_id, 'log_type': 'self', 'bot': bot, 'i': 0,
        #      'contact': '9876543210',
        #      'whatsapp_response': {'contacts': [{'input': '+55123456789', 'status': 'valid', 'wa_id': '55123456789'}]}},
        #     {'reference_id': reference_id, 'log_type': 'send', 'bot': bot, 'status': 'Success',
        #      'api_response': {'contacts': [{'input': '+55123456789', 'status': 'valid', 'wa_id': '55123456789'}]},
        #      'recipient': '9876543210',
        #      'template_params': [{'type': 'header', 'parameters': [{'type': 'document', 'document': {
        #          'link': 'https://drive.google.com/uc?export=download&id=1GXQ43jilSDelRvy1kr3PNNpl1e21dRXm',
        #          'filename': 'Brochure.pdf'}}]}]},
        #     {'bot': bot, 'contacts': ['9876543210', '876543212345'], 'log_type': 'self',
        #      'reference_id': reference_id},
        #     {'reference_id': reference_id, 'log_type': 'common', 'bot': bot, 'status': 'Completed',
        #      'user': 'test_user', 'broadcast_id': event_id, 'failure_cnt': 0, 'total': 2,
        #      'components': [{'type': 'header', 'parameters': [{'type': 'document', 'document': {
        #          'link': 'https://drive.google.com/uc?export=download&id=1GXQ43jilSDelRvy1kr3PNNpl1e21dRXm',
        #          'filename': 'Brochure.pdf'}}]}], 'i': 0, 'contact': '876543212345',
        #      'api_response': {'contacts': ['9876543210', '876543212345']},
        #      'resp': {'contacts': [{'input': '+55123456789', 'status': 'valid', 'wa_id': '55123456789'}]}}
        # ]
        assert len(logs[0]) == logs[1] == 1
        [log.pop("timestamp") for log in logs[0]]
        reference_id = logs[0][0].get("reference_id")
        expected_logs = [{"event_id": event_id, 'reference_id': reference_id, 'log_type': 'common', 'bot': bot, 'status': 'Completed',
                          'user': 'test_user', 'failure_cnt': 0, 'total': 0,
                          'components': [{'type': 'header', 'parameters': [{'type': 'document', 'document': {
                              'link': 'https://drive.google.com/uc?export=download&id=1GXQ43jilSDelRvy1kr3PNNpl1e21dRXm',
                              'filename': 'Brochure.pdf'}}]}], 'i': 0, 'contact': '876543212345',
                          'api_response': {'contacts': ['9876543210', '876543212345']},
                          'resp': {'contacts': [{'input': '+55123456789', 'status': 'valid', 'wa_id': '55123456789'}]}}]
        for log in logs[0]:
            if log.get("config"):
                logged_config = log.pop("config")
            assert log in expected_logs

        logged_config.pop("status")
        logged_config.pop('pyscript_timeout')
        logged_config.pop("timestamp")
        logged_config.pop("_id")
        assert logged_config.pop("template_config") == []
        assert logged_config == config

        with pytest.raises(AppException, match="Notification settings not found!"):
            MessageBroadcastProcessor.get_settings(event_id, bot)

        # assert mock_send.call_args[0][1] == 'brochure_pdf'
        # assert mock_send.call_args[0][2] == '876543212345'
        # assert mock_send.call_args[0][3] == 'en'
        # assert mock_send.call_args[0][4] == [{'type': 'header', 'parameters': [{'type': 'document', 'document': {
        #     'link': 'https://drive.google.com/uc?export=download&id=1GXQ43jilSDelRvy1kr3PNNpl1e21dRXm',
        #     'filename': 'Brochure.pdf'}}]}]
        # assert mock_send.call_args[0][5] == '13b1e228_4a08_4d19_a0da_cdb80bc76380'

    @responses.activate
    @patch("kairon.shared.data.processor.MongoProcessor.get_bot_settings")
    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    @patch("kairon.shared.utils.Utility.is_exist", autospec=True)
    def test_execute_message_broadcast_with_pyscript_failure(self, mock_is_exist, mock_channel_config, mock_get_bot_settings):
        bot = 'test_execute_message_broadcast_with_pyscript_failure'
        user = 'test_user'
        script = """
                import os         
                """
        script = textwrap.dedent(script)
        config = {
            "name": "one_time_schedule", "broadcast_type": "dynamic",
            "connector_type": "whatsapp",
            "pyscript": script,
            "retry_count": 0
        }

        url = f"http://localhost:5001/api/events/execute/{EventClass.message_broadcast}?is_scheduled=False"
        responses.add(
            "POST", url,
            json={"message": "Event Triggered!", "success": True, "error_code": 0, "data": None}
        )

        mock_get_bot_settings.return_value = {"whatsapp": "360dialog", "notification_scheduling_limit": 4, "dynamic_broadcast_execution_timeout": 21600}
        mock_channel_config.return_value = {
            "config": {"access_token": "shjkjhrefdfghjkl", "from_phone_number_id": "918958030415"}}

        event = MessageBroadcastEvent(bot, user)
        event.validate()
        event_id = event.enqueue(EventRequestType.trigger_async.value, config=config)
        event.execute(event_id)

        logs = MessageBroadcastProcessor.get_broadcast_logs(bot)
        assert len(logs[0]) == logs[1] == 1
        reference_id = logs[0][0].get("reference_id")
        logged_config = logs[0][0].pop("config")
        logged_config.pop('pyscript_timeout')
        logged_config.pop("_id")
        logged_config.pop("status")
        logged_config.pop("timestamp")
        assert logged_config.pop("template_config") == []
        assert logged_config == config
        logs[0][0].pop("timestamp", None)

        assert logs[0][0] == {"event_id": event_id, 'reference_id': reference_id, 'log_type': 'common', 'bot': bot, 'status': 'Fail',
                              'user': user, "exception": "Script execution error: import of 'os' is unauthorized"}

        with pytest.raises(AppException, match="Notification settings not found!"):
            MessageBroadcastProcessor.get_settings(event_id, bot)

    @responses.activate
    @patch("kairon.shared.channels.broadcast.whatsapp.json")
    @patch("kairon.shared.data.processor.MongoProcessor.get_bot_settings")
    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    @patch("kairon.shared.utils.Utility.is_exist", autospec=True)
    def test_execute_message_broadcast_with_pyscript_timeout(self, mock_is_exist, mock_channel_config,
                                                             mock_get_bot_settings, mock_json):
        import time

        bot = 'test_execute_message_broadcast_with_pyscript_timeout'
        user = 'test_user'
        script = """
                json()     
                """
        script = textwrap.dedent(script)
        config = {
            "name": "one_time_schedule", "broadcast_type": "dynamic",
            "connector_type": "whatsapp", "pyscript": script,
            "retry_count": 0
        }

        url = f"http://localhost:5001/api/events/execute/{EventClass.message_broadcast}?is_scheduled=False"
        responses.add(
            "POST", url,
            json={"message": "Event Triggered!", "success": True, "error_code": 0, "data": None}
        )

        mock_get_bot_settings.return_value = {"whatsapp": "360dialog", "notification_scheduling_limit": 4, "dynamic_broadcast_execution_timeout": 1}
        mock_channel_config.return_value = {
            "config": {"access_token": "shjkjhrefdfghjkl", "from_phone_number_id": "918958030415"}}

        def sleep_for_some_time(*args, **kwargs):
            time.sleep(3)

        mock_json.side_effect = sleep_for_some_time

        event = MessageBroadcastEvent(bot, user)
        event.validate()
        event_id = event.enqueue(EventRequestType.trigger_async.value, config=config)
        event.execute(event_id)

        logs = MessageBroadcastProcessor.get_broadcast_logs(bot)
        assert len(logs[0]) == logs[1] == 1
        [log.pop("timestamp") for log in logs[0]]
        reference_id = logs[0][0].get("reference_id")
        logged_config = logs[0][0].pop("config")
        logged_config.pop("_id")
        logged_config.pop("status")
        logged_config.pop("timestamp")
        logged_config.pop('pyscript_timeout')
        assert logged_config.pop("template_config") == []
        assert logged_config == config

        assert logs[0][0] == {"event_id": event_id, 'reference_id': reference_id, 'log_type': 'common', 'bot': bot, 'status': 'Fail',
                              'user': user, 'exception': 'Operation timed out: 1 seconds'}

        with pytest.raises(AppException, match="Notification settings not found!"):
            MessageBroadcastProcessor.get_settings(event_id, bot)

    @responses.activate
    @mongomock.patch(servers=(('localhost', 27017),))
    @patch("kairon.shared.channels.whatsapp.bsp.dialog360.BSP360Dialog.get_partner_auth_token", autospec=True)
    @patch("kairon.chat.handlers.channels.clients.whatsapp.dialog360.BSP360Dialog.send_template_message")
    @patch("kairon.shared.data.processor.MongoProcessor.get_bot_settings")
    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    @patch("kairon.shared.utils.Utility.is_exist", autospec=True)
    def test_execute_message_broadcast_with_resend_broadcast_with_static_values(
            self, mock_is_exist, mock_channel_config, mock_get_bot_settings, mock_send,
            mock_get_partner_auth_token
    ):
        from datetime import datetime, timedelta
        from kairon.shared.chat.broadcast.data_objects import MessageBroadcastSettings, MessageBroadcastLogs

        bot = 'test_execute_message_broadcast_with_resend_broadcast_with_static_values'
        user = 'test_user'
        config = {
            "name": "test_broadcast", "broadcast_type": "static",
            "connector_type": "whatsapp",
            "recipients_config": {
                "recipients": "919876543210,919012345678"
            },
            "template_config": [
                {
                    'language': 'hi',
                    "template_id": "brochure_pdf",
                }
            ],
            "status": False,
            "bot": bot,
            "user": user
        }
        template = [
            {
                "format": "TEXT",
                "text": "Kisan Suvidha Program Follow-up",
                "type": "HEADER"
            },
            {
                "text": "Hello! As a part of our Kisan Suvidha program, I am dedicated to supporting farmers like you in maximizing your crop productivity and overall yield.\n\nI wanted to reach out to inquire if you require any assistance with your current farming activities. Our team of experts, including our skilled agronomists, are here to lend a helping hand wherever needed.",
                "type": "BODY"
            },
            {
                "text": "reply with STOP to unsubscribe",
                "type": "FOOTER"
            },
            {
                "buttons": [
                    {
                        "text": "Connect to Agronomist",
                        "type": "QUICK_REPLY"
                    }
                ],
                "type": "BUTTONS"
            }
        ]

        url = f"http://localhost:5001/api/events/execute/{EventClass.message_broadcast}?is_scheduled=False"
        template_url = 'https://hub.360dialog.io/api/v2/partners/sdfghjkjhgfddfghj/waba_accounts/asdfghjk/waba_templates?filters={"business_templates.name": "brochure_pdf"}&sort=business_templates.name'
        responses.add(
            "POST", url,
            json={"message": "Event Triggered!", "success": True, "error_code": 0, "data": None}
        )
        responses.add(
            "GET", template_url,
            json={"waba_templates": [
                {"category": "MARKETING", "components": template, "name": "agronomy_support", "language": "hi"}]}
        )

        mock_get_bot_settings.return_value = {"whatsapp": "360dialog", "notification_scheduling_limit": 4,
                                              "dynamic_broadcast_execution_timeout": 21600}
        mock_channel_config.return_value = {
            "config": {"access_token": "shjkjhrefdfghjkl", "from_phone_number_id": "918958030415",
                       "waba_account_id": "asdfghjk"}}
        mock_send.return_value = {"contacts": [{"input": "919876543210", "status": "valid", "wa_id": "55123456789"}],
                                  "messages": [{"id": 'wamid.HBgMOTE5NTE1OTkxNjg1FQIAERgSODFFNEM0QkM5MEJBODM4MjIBB==',
                                                "message_status": 'accepted'}]}
        mock_get_partner_auth_token.return_value = None

        msg_broadcast_id = MessageBroadcastSettings(**config).save().id.__str__()
        timestamp = datetime.utcnow()
        MessageBroadcastLogs(
            **{
                "reference_id": "667bed955bfdaf3466b19de2",
                "log_type": "common",
                "bot": bot,
                "status": "Completed",
                "user": "test_user",
                "event_id": msg_broadcast_id,
                "recipients": ["919876543210", "919012345678"],
                "timestamp": timestamp,

            }
        ).save()
        timestamp = timestamp + timedelta(minutes=2)
        MessageBroadcastLogs(
            **{
                "reference_id": "667bed955bfdaf3466b19de2",
                "log_type": "send",
                "bot": bot,
                "status": "Success",
                "template_name": "brochure_pdf",
                "template": template,
                "namespace": "54500467_f322_4595_becd_419af88spm4",
                "language_code": "hi",
                "errors": [],
                "api_response": {
                    "messaging_product": "whatsapp",
                    "contacts": [
                        {
                            "input": "919012345678",
                            "wa_id": "919012345678"
                        }
                    ],
                    "messages": [
                        {
                            "id": "wamid.HBgLMTIxMTU1NTc5NDcVAgARGBIyRkQxREUxRDJFQUJGMkQ3NDIZ"
                        }
                    ]
                },
                "recipient": "919012345678",
                "template_params": [
                    {
                        "type": "header",
                        "parameters": [
                            {
                                "type": "document",
                                "document": {
                                    "link": "https://drive.google.com/uc?export=download&id=1GXQ43jilSDelRvy1kr3PNNpl1e21dRXm",
                                    "filename": "Brochure.pdf",
                                },
                            }
                        ],
                    }
                ],
                "timestamp": timestamp,
                "retry_count": 0
            }
        ).save()
        timestamp = timestamp + timedelta(minutes=2)
        MessageBroadcastLogs(
            **{
                "reference_id": "667bed955bfdaf3466b19de2",
                "log_type": "send",
                "bot": bot,
                "status": "Success",
                "template_name": "brochure_pdf",
                "template": template,
                "namespace": "54500467_f322_4595_becd_419af88spm4",
                "language_code": "hi",
                "errors": [
                    {
                        "code": 130472,
                        "title": "User's number is part of an experiment",
                        "message": "User's number is part of an experiment",
                        "error_data": {
                            "details": "Failed to send message because this user's phone number is part of an experiment"
                        },
                        "href": "https://developers.facebook.com/docs/whatsapp/cloud-api/support/error-codes/"
                    }
                ],
                "api_response": {
                    "messaging_product": "whatsapp",
                    "contacts": [
                        {
                            "input": "919876543210",
                            "wa_id": "919876543210"
                        }
                    ],
                    "messages": [
                        {
                            "id": "wamid.HBgMOTE5NTE1OTkxNjg1FQIAERgSODFFNEM0QkM5MEJBODM4MjI4AA=="
                        }
                    ]
                },
                "recipient": "919876543210",
                "template_params": [
                    {
                        "type": "header",
                        "parameters": [
                            {
                                "type": "document",
                                "document": {
                                    "link": "https://drive.google.com/uc?export=download&id=1GXQ43jilSDelRvy1kr3PNNpl1e21dRXm",
                                    "filename": "Brochure.pdf",
                                },
                            }
                        ],
                    }
                ],
                "timestamp": timestamp,
                "retry_count": 0
            }
        ).save()

        ChannelLogs(
            type=ChannelTypes.WHATSAPP.value,
            status='sent',
            data={'id': 'CONVERSATION_ID', 'expiration_timestamp': '1691598412',
                  'origin': {'type': 'business_initated'}},
            initiator='business_initated',
            message_id='wamid.HBgLMTIxMTU1NTc5NDcVAgARGBIyRkQxREUxRDJFQUJGMkQ3NDIZ',
            campaign_id="667bed955bfdaf3466b19de2",
            bot=bot,
            user=user
        ).save()
        ChannelLogs(
            type=ChannelTypes.WHATSAPP.value,
            status='delivered',
            data={'id': 'CONVERSATION_ID', 'expiration_timestamp': '1691598412',
                  'origin': {'type': 'business_initated'}},
            initiator='business_initated',
            message_id='wamid.HBgLMTIxMTU1NTc5NDcVAgARGBIyRkQxREUxRDJFQUJGMkQ3NDIZ',
            campaign_id="667bed955bfdaf3466b19de2",
            bot=bot,
            user=user
        ).save()
        ChannelLogs(
            type=ChannelTypes.WHATSAPP.value,
            status='read',
            data={'id': 'CONVERSATION_ID', 'expiration_timestamp': '1691598412',
                  'origin': {'type': 'business_initated'}},
            initiator='business_initated',
            message_id='wamid.HBgLMTIxMTU1NTc5NDcVAgARGBIyRkQxREUxRDJFQUJGMkQ3NDIZ',
            campaign_id="667bed955bfdaf3466b19de2",
            bot=bot,
            user=user
        ).save()

        ChannelLogs(
            type=ChannelTypes.WHATSAPP.value,
            status='sent',
            data={'id': 'CONVERSATION_ID', 'expiration_timestamp': '1691598412',
                  'origin': {'type': 'business_initated'}},
            initiator='business_initated',
            message_id='wamid.HBgMOTE5NTE1OTkxNjg1FQIAERgSODFFNEM0QkM5MEJBODM4MjIBB==',
            campaign_id="667bed955bfdaf3466b19de2",
            bot=bot,
            user=user
        ).save()
        ChannelLogs(
            type=ChannelTypes.WHATSAPP.value,
            status='delivered',
            data={'id': 'CONVERSATION_ID', 'expiration_timestamp': '1691598412',
                  'origin': {'type': 'business_initated'}},
            initiator='business_initated',
            message_id='wamid.HBgMOTE5NTE1OTkxNjg1FQIAERgSODFFNEM0QkM5MEJBODM4MjIBB==',
            campaign_id="667bed955bfdaf3466b19de2",
            bot=bot,
            user=user
        ).save()
        ChannelLogs(
            type=ChannelTypes.WHATSAPP.value,
            status='read',
            data={'id': 'CONVERSATION_ID', 'expiration_timestamp': '1691598412',
                  'origin': {'type': 'business_initated'}},
            initiator='business_initated',
            message_id='wamid.HBgMOTE5NTE1OTkxNjg1FQIAERgSODFFNEM0QkM5MEJBODM4MjIBB==',
            campaign_id="667bed955bfdaf3466b19de2",
            bot=bot,
            user=user
        ).save()

        ChannelLogs(
            type=ChannelTypes.WHATSAPP.value,
            status='failed',
            data={'id': 'CONVERSATION_ID', 'expiration_timestamp': '1691598412',
                  'origin': {'type': 'business_initated'}},
            initiator='business_initated',
            message_id='wamid.HBgMOTE5NTE1OTkxNjg1FQIAERgSODFFNEM0QkM5MEJBODM4MjI4AA==',
            campaign_id="667bed955bfdaf3466b19de2",
            errors=[
                {
                    "code": 130472,
                    "title": "User's number is part of an experiment",
                    "message": "User's number is part of an experiment",
                    "error_data": {
                        "details": "Failed to send message because this user's phone number is part of an experiment"
                    },
                    "href": "https://developers.facebook.com/docs/whatsapp/cloud-api/support/error-codes/"
                }
            ],
            bot=bot,
            user=user
        ).save()

        with patch.dict(Utility.environment["channels"]["360dialog"], {"partner_id": "sdfghjkjhgfddfghj"}):
            event = MessageBroadcastEvent(bot, user)
            event.validate()
            event_id = event.enqueue(EventRequestType.resend_broadcast.value,
                                     msg_broadcast_id=msg_broadcast_id)
            event.execute(event_id, is_resend=True)

        logs = MessageBroadcastProcessor.get_broadcast_logs(bot)
        assert len(logs[0]) == logs[1] == 4
        logs[0][2].pop("timestamp")
        reference_id = logs[0][2].get("reference_id")
        logged_config = logs[0][2]
        assert logged_config == {
            'reference_id': reference_id, 'log_type': 'resend',
            'bot': 'test_execute_message_broadcast_with_resend_broadcast_with_static_values', 'status': 'Success',
            'api_response': {'contacts': [{'input': '919876543210', 'status': 'valid', 'wa_id': '55123456789'}],
                             'messages': [{'id': 'wamid.HBgMOTE5NTE1OTkxNjg1FQIAERgSODFFNEM0QkM5MEJBODM4MjIBB==',
                                           'message_status': 'accepted'}]},
            'recipient': '919876543210',
            'template_params': [
                {'type': 'header',
                 'parameters': [{'type': 'document',
                                 'document': {'link': 'https://drive.google.com/uc?export=download&id=1GXQ43jilSDelRvy1kr3PNNpl1e21dRXm',
                                              'filename': 'Brochure.pdf'}}]}],
            'template': [{'format': 'TEXT', 'text': 'Kisan Suvidha Program Follow-up', 'type': 'HEADER'},
                         {'text': 'Hello! As a part of our Kisan Suvidha program, I am dedicated to supporting farmers like you in maximizing your crop productivity and overall yield.\n\nI wanted to reach out to inquire if you require any assistance with your current farming activities. Our team of experts, including our skilled agronomists, are here to lend a helping hand wherever needed.', 'type': 'BODY'},
                         {'text': 'reply with STOP to unsubscribe', 'type': 'FOOTER'},
                         {'buttons': [{'text': 'Connect to Agronomist', 'type': 'QUICK_REPLY'}], 'type': 'BUTTONS'}],
            'event_id': event_id, 'template_name': 'brochure_pdf', 'language_code': 'hi',
            'namespace': '54500467_f322_4595_becd_419af88spm4', 'retry_count': 1, 'errors': []}

        logs[0][3].pop("timestamp")
        logs[0][3].get("config").pop("timestamp")
        reference_id = logs[0][3].get("reference_id")
        logged_config = logs[0][3]
        logs[0][3].pop("retry_1_timestamp")
        assert logged_config == {
            'reference_id': reference_id, 'log_type': 'common',
            'bot': 'test_execute_message_broadcast_with_resend_broadcast_with_static_values',
            'status': 'Completed', 'user': 'test_user', 'event_id': event_id,
            'recipients': ['919876543210', '919012345678'],
            'config': {'_id': event_id, 'name': 'test_broadcast', 'connector_type': 'whatsapp',
                       'broadcast_type': 'static', 'recipients_config': {'recipients': '919876543210,919012345678'},
                       'template_config': [{'template_id': 'brochure_pdf', 'language': 'hi'}], 'retry_count': 0,
                       'bot': 'test_execute_message_broadcast_with_resend_broadcast_with_static_values',
                       'user': 'test_user', 'status': False, 'pyscript_timeout': 21600},
            'resend_count_1': 1, 'skipped_count_1': 0}

        assert ChannelLogs.objects(
            bot=bot, message_id='wamid.HBgMOTE5NTE1OTkxNjg1FQIAERgSODFFNEM0QkM5MEJBODM4MjIBB==', status="sent"
        ).get().campaign_id == reference_id

        result = MessageBroadcastProcessor.get_channel_metrics(ChannelTypes.WHATSAPP.value, bot)
        assert result == [
            {
                'campaign_metrics': [
                    {
                        'retry_count': 0,
                        'statuses': {'delivered': 1, 'failed': 1, 'read': 1, 'sent': 1}
                    },
                    {
                        'retry_count': 1,
                        'statuses': {'delivered': 1, 'read': 1, 'sent': 1}
                    }
                ], 'campaign_id': reference_id
            }
        ]

    @responses.activate
    @mongomock.patch(servers=(('localhost', 27017),))
    @patch("kairon.shared.channels.whatsapp.bsp.dialog360.BSP360Dialog.get_partner_auth_token", autospec=True)
    @patch("kairon.chat.handlers.channels.clients.whatsapp.dialog360.BSP360Dialog.send_template_message")
    @patch("kairon.shared.data.processor.MongoProcessor.get_bot_settings")
    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    @patch("kairon.shared.utils.Utility.is_exist", autospec=True)
    def test_execute_message_broadcast_with_resend_broadcast_with_dynamic_values(
            self, mock_is_exist, mock_channel_config, mock_get_bot_settings, mock_send,
            mock_get_partner_auth_token
    ):
        from datetime import datetime, timedelta
        from kairon.shared.chat.broadcast.data_objects import MessageBroadcastSettings, MessageBroadcastLogs

        bot = 'test_execute_message_broadcast_with_resend_broadcast_with_dynamic_values'
        user = 'test_user'
        script = """
        contacts = ['919876543210','919012345678']

        components = components = [{'type': 'header', 'parameters': [{'type': 'document', 'document': {
                                  'link': 'https://drive.google.com/uc?export=download&id=1GXQ43jilSDelRvy1kr3PNNpl1e21dRXm',
                                  'filename': 'Brochure.pdf'}}]}]
        for contact in contacts:
            resp = send_msg("brochure_pdf", contact, components=components, namespace="13b1e228_4a08_4d19_a0da_cdb80bc76380")

            log(contact=contact,whatsapp_response=resp)            
        """
        script = textwrap.dedent(script)
        config = {
            "name": "one_time_schedule", "broadcast_type": "dynamic",
            "connector_type": "whatsapp",
            "pyscript": script,
            "bot": bot,
            "user": user,
            "status": False
        }
        template = [
            {
                "format": "TEXT",
                "text": "Kisan Suvidha Program Follow-up",
                "type": "HEADER"
            },
            {
                "text": "Hello! As a part of our Kisan Suvidha program, I am dedicated to supporting farmers like you in maximizing your crop productivity and overall yield.\n\nI wanted to reach out to inquire if you require any assistance with your current farming activities. Our team of experts, including our skilled agronomists, are here to lend a helping hand wherever needed.",
                "type": "BODY"
            },
            {
                "text": "reply with STOP to unsubscribe",
                "type": "FOOTER"
            },
            {
                "buttons": [
                    {
                        "text": "Connect to Agronomist",
                        "type": "QUICK_REPLY"
                    }
                ],
                "type": "BUTTONS"
            }
        ]

        url = f"http://localhost:5001/api/events/execute/{EventClass.message_broadcast}?is_scheduled=False"
        template_url = 'https://hub.360dialog.io/api/v2/partners/sdfghjkjhgfddfghj/waba_accounts/asdfghjk/waba_templates?filters={"business_templates.name": "brochure_pdf"}&sort=business_templates.name'
        responses.add(
            "POST", url,
            json={"message": "Event Triggered!", "success": True, "error_code": 0, "data": None}
        )
        responses.add(
            "GET", template_url,
            json={"waba_templates": [
                {"category": "MARKETING", "components": template, "name": "agronomy_support", "language": "hi"}]}
        )

        mock_get_bot_settings.return_value = {"whatsapp": "360dialog", "notification_scheduling_limit": 4,
                                              "dynamic_broadcast_execution_timeout": 21600}
        mock_channel_config.return_value = {
            "config": {"access_token": "shjkjhrefdfghjkl", "from_phone_number_id": "918958030415",
                       "waba_account_id": "asdfghjk"}}
        mock_send.return_value = {"contacts": [{"input": "919876543210", "status": "valid", "wa_id": "55123456789"}],
                                  "messages": [{"id": 'wamid.HBgMOTE5NTE1OTkxNjg1FQIAERgSODFFNEM0QkM5MEJBODM4MjIBB==',
                                                "message_status": 'accepted'}]}
        mock_get_partner_auth_token.return_value = None

        msg_broadcast_id = MessageBroadcastSettings(**config).save().id.__str__()
        timestamp = datetime.utcnow()
        MessageBroadcastLogs(
            **{
                "reference_id": "667bed955bfdaf3466b19de1",
                "log_type": "common",
                "bot": bot,
                "status": "Completed",
                "user": "test_user",
                "event_id": msg_broadcast_id,
                "recipients": ["919876543210", "919012345678"],
                "timestamp": timestamp,

            }
        ).save()
        timestamp = timestamp + timedelta(minutes=2)
        MessageBroadcastLogs(
            **{
                "reference_id": "667bed955bfdaf3466b19de1",
                "log_type": "send",
                "bot": bot,
                "status": "Success",
                "template_name": "brochure_pdf",
                "template": template,
                "namespace": "54500467_f322_4595_becd_419af88spm4",
                "language_code": "hi",
                "errors": [],
                "api_response": {
                    "messaging_product": "whatsapp",
                    "contacts": [
                        {
                            "input": "919012345678",
                            "wa_id": "919012345678"
                        }
                    ],
                    "messages": [
                        {
                            "id": "wamid.HBgLMTIxMTU1NTc5NDcVAgARGBIyRkQxREUxRDJFQUJGMkQ3NDIZ"
                        }
                    ]
                },
                "recipient": "919012345678",
                "template_params": [
                    {
                        "type": "header",
                        "parameters": [
                            {
                                "type": "document",
                                "document": {
                                    "link": "https://drive.google.com/uc?export=download&id=1GXQ43jilSDelRvy1kr3PNNpl1e21dRXm",
                                    "filename": "Brochure.pdf",
                                },
                            }
                        ],
                    }
                ],
                "timestamp": timestamp,
                "retry_count": 0
            }
        ).save()
        timestamp = timestamp + timedelta(minutes=2)
        MessageBroadcastLogs(
            **{
                "reference_id": "667bed955bfdaf3466b19de1",
                "log_type": "send",
                "bot": bot,
                "status": "Success",
                "template_name": "brochure_pdf",
                "template": template,
                "namespace": "54500467_f322_4595_becd_419af88spm4",
                "language_code": "hi",
                "errors": [
                    {
                        "code": 130472,
                        "title": "User's number is part of an experiment",
                        "message": "User's number is part of an experiment",
                        "error_data": {
                            "details": "Failed to send message because this user's phone number is part of an experiment"
                        },
                        "href": "https://developers.facebook.com/docs/whatsapp/cloud-api/support/error-codes/"
                    }
                ],
                "api_response": {
                    "messaging_product": "whatsapp",
                    "contacts": [
                        {
                            "input": "919876543210",
                            "wa_id": "919876543210"
                        }
                    ],
                    "messages": [
                        {
                            "id": "wamid.HBgMOTE5NTE1OTkxNjg1FQIAERgSODFFNEM0QkM5MEJBODM4MjI4AA=="
                        }
                    ]
                },
                "recipient": "919876543210",
                "template_params": [
                    {
                        "type": "header",
                        "parameters": [
                            {
                                "type": "document",
                                "document": {
                                    "link": "https://drive.google.com/uc?export=download&id=1GXQ43jilSDelRvy1kr3PNNpl1e21dRXm",
                                    "filename": "Brochure.pdf",
                                },
                            }
                        ],
                    }
                ],
                "timestamp": timestamp,
                "retry_count": 0
            }
        ).save()

        ChannelLogs(
            type=ChannelTypes.WHATSAPP.value,
            status='sent',
            data={'id': 'CONVERSATION_ID', 'expiration_timestamp': '1691598412',
                  'origin': {'type': 'business_initated'}},
            initiator='business_initated',
            message_id='wamid.HBgLMTIxMTU1NTc5NDcVAgARGBIyRkQxREUxRDJFQUJGMkQ3NDIZ',
            campaign_id="667bed955bfdaf3466b19de1",
            bot=bot,
            user=user
        ).save()
        ChannelLogs(
            type=ChannelTypes.WHATSAPP.value,
            status='delivered',
            data={'id': 'CONVERSATION_ID', 'expiration_timestamp': '1691598412',
                  'origin': {'type': 'business_initated'}},
            initiator='business_initated',
            message_id='wamid.HBgLMTIxMTU1NTc5NDcVAgARGBIyRkQxREUxRDJFQUJGMkQ3NDIZ',
            campaign_id="667bed955bfdaf3466b19de1",
            bot=bot,
            user=user
        ).save()
        ChannelLogs(
            type=ChannelTypes.WHATSAPP.value,
            status='read',
            data={'id': 'CONVERSATION_ID', 'expiration_timestamp': '1691598412',
                  'origin': {'type': 'business_initated'}},
            initiator='business_initated',
            message_id='wamid.HBgLMTIxMTU1NTc5NDcVAgARGBIyRkQxREUxRDJFQUJGMkQ3NDIZ',
            campaign_id="667bed955bfdaf3466b19de1",
            bot=bot,
            user=user
        ).save()

        ChannelLogs(
            type=ChannelTypes.WHATSAPP.value,
            status='sent',
            data={'id': 'CONVERSATION_ID', 'expiration_timestamp': '1691598412',
                  'origin': {'type': 'business_initated'}},
            initiator='business_initated',
            message_id='wamid.HBgMOTE5NTE1OTkxNjg1FQIAERgSODFFNEM0QkM5MEJBODM4MjIBB==',
            campaign_id="667bed955bfdaf3466b19de1",
            bot=bot,
            user=user
        ).save()
        ChannelLogs(
            type=ChannelTypes.WHATSAPP.value,
            status='delivered',
            data={'id': 'CONVERSATION_ID', 'expiration_timestamp': '1691598412',
                  'origin': {'type': 'business_initated'}},
            initiator='business_initated',
            message_id='wamid.HBgMOTE5NTE1OTkxNjg1FQIAERgSODFFNEM0QkM5MEJBODM4MjIBB==',
            campaign_id="667bed955bfdaf3466b19de1",
            bot=bot,
            user=user
        ).save()
        ChannelLogs(
            type=ChannelTypes.WHATSAPP.value,
            status='read',
            data={'id': 'CONVERSATION_ID', 'expiration_timestamp': '1691598412',
                  'origin': {'type': 'business_initated'}},
            initiator='business_initated',
            message_id='wamid.HBgMOTE5NTE1OTkxNjg1FQIAERgSODFFNEM0QkM5MEJBODM4MjIBB==',
            campaign_id="667bed955bfdaf3466b19de1",
            bot=bot,
            user=user
        ).save()

        ChannelLogs(
            type=ChannelTypes.WHATSAPP.value,
            status='failed',
            data={'id': 'CONVERSATION_ID', 'expiration_timestamp': '1691598412',
                  'origin': {'type': 'business_initated'}},
            initiator='business_initated',
            message_id='wamid.HBgMOTE5NTE1OTkxNjg1FQIAERgSODFFNEM0QkM5MEJBODM4MjI4AA==',
            campaign_id="667bed955bfdaf3466b19de1",
            errors=[
                {
                    "code": 130472,
                    "title": "User's number is part of an experiment",
                    "message": "User's number is part of an experiment",
                    "error_data": {
                        "details": "Failed to send message because this user's phone number is part of an experiment"
                    },
                    "href": "https://developers.facebook.com/docs/whatsapp/cloud-api/support/error-codes/"
                }
            ],
            bot=bot,
            user=user
        ).save()

        with patch.dict(Utility.environment["channels"]["360dialog"], {"partner_id": "sdfghjkjhgfddfghj"}):
            event = MessageBroadcastEvent(bot, user)
            event.validate()
            event_id = event.enqueue(EventRequestType.resend_broadcast.value,
                                     msg_broadcast_id=msg_broadcast_id)
            event.execute(event_id, is_resend=True)

        logs = MessageBroadcastProcessor.get_broadcast_logs(bot)
        assert len(logs[0]) == logs[1] == 4
        logs[0][2].pop("timestamp")
        reference_id = logs[0][2].get("reference_id")
        logged_config = logs[0][2]
        assert logged_config == {
            'reference_id': reference_id, 'log_type': 'resend',
            'bot': 'test_execute_message_broadcast_with_resend_broadcast_with_dynamic_values', 'status': 'Success',
            'api_response': {'contacts': [{'input': '919876543210', 'status': 'valid', 'wa_id': '55123456789'}],
                             'messages': [{'id': 'wamid.HBgMOTE5NTE1OTkxNjg1FQIAERgSODFFNEM0QkM5MEJBODM4MjIBB==',
                                           'message_status': 'accepted'}]},
            'recipient': '919876543210',
            'template_params': [
                {'type': 'header', 'parameters': [
                    {'type': 'document',
                     'document': {'link': 'https://drive.google.com/uc?export=download&id=1GXQ43jilSDelRvy1kr3PNNpl1e21dRXm',
                                  'filename': 'Brochure.pdf'}}]}],
            'template': [{'format': 'TEXT', 'text': 'Kisan Suvidha Program Follow-up', 'type': 'HEADER'},
                         {'text': 'Hello! As a part of our Kisan Suvidha program, I am dedicated to supporting farmers like you in maximizing your crop productivity and overall yield.\n\nI wanted to reach out to inquire if you require any assistance with your current farming activities. Our team of experts, including our skilled agronomists, are here to lend a helping hand wherever needed.', 'type': 'BODY'},
                         {'text': 'reply with STOP to unsubscribe', 'type': 'FOOTER'},
                         {'buttons': [{'text': 'Connect to Agronomist', 'type': 'QUICK_REPLY'}], 'type': 'BUTTONS'}],
            'event_id': event_id, 'template_name': 'brochure_pdf', 'language_code': 'hi',
            'namespace': '54500467_f322_4595_becd_419af88spm4', 'retry_count': 1, 'errors': []}

        logs[0][3].pop("timestamp")
        logs[0][3].get("config").pop("timestamp")
        reference_id = logs[0][3].get("reference_id")
        logs[0][3].pop("retry_1_timestamp")
        logged_config = logs[0][3]
        assert logged_config == {
            'reference_id': reference_id, 'log_type': 'common',
            'bot': 'test_execute_message_broadcast_with_resend_broadcast_with_dynamic_values', 'status': 'Completed',
            'user': 'test_user', 'event_id': event_id,
            'recipients': ['919876543210', '919012345678'],
            'config': {'_id': event_id, 'name': 'one_time_schedule', 'connector_type': 'whatsapp',
                       'broadcast_type': 'dynamic', 'template_config': [],
                       'pyscript': '\ncontacts = [\'919876543210\',\'919012345678\']\n\ncomponents = components = [{\'type\': \'header\', \'parameters\': [{\'type\': \'document\', \'document\': {\n                          \'link\': \'https://drive.google.com/uc?export=download&id=1GXQ43jilSDelRvy1kr3PNNpl1e21dRXm\',\n                          \'filename\': \'Brochure.pdf\'}}]}]\nfor contact in contacts:\n    resp = send_msg("brochure_pdf", contact, components=components, namespace="13b1e228_4a08_4d19_a0da_cdb80bc76380")\n\n    log(contact=contact,whatsapp_response=resp)            \n',
                       'retry_count': 0,
                       'bot': 'test_execute_message_broadcast_with_resend_broadcast_with_dynamic_values',
                       'user': 'test_user', 'status': False, 'pyscript_timeout': 21600},
            'resend_count_1': 1, 'skipped_count_1': 0}
        assert ChannelLogs.objects(
            bot=bot, message_id='wamid.HBgMOTE5NTE1OTkxNjg1FQIAERgSODFFNEM0QkM5MEJBODM4MjIBB==', status="sent"
        ).get().campaign_id == reference_id

        result = MessageBroadcastProcessor.get_channel_metrics(ChannelTypes.WHATSAPP.value, bot)
        assert result == [
            {
                'campaign_metrics': [
                    {
                        'retry_count': 0,
                        'statuses': {'delivered': 1, 'failed': 1, 'read': 1, 'sent': 1}
                    },
                    {
                        'retry_count': 1,
                        'statuses': {'delivered': 1, 'read': 1, 'sent': 1}
                    }
                ],
                'campaign_id': reference_id
            }
        ]

    @responses.activate
    @mongomock.patch(servers=(('localhost', 27017),))
    @patch("kairon.shared.channels.whatsapp.bsp.dialog360.BSP360Dialog.get_partner_auth_token", autospec=True)
    @patch("kairon.chat.handlers.channels.clients.whatsapp.dialog360.BSP360Dialog.send_template_message")
    @patch("kairon.shared.data.processor.MongoProcessor.get_bot_settings")
    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    @patch("kairon.shared.utils.Utility.is_exist", autospec=True)
    def test_execute_message_broadcast_with_resend_broadcast_with_meta_error_codes_to_skip(
            self, mock_is_exist, mock_channel_config, mock_get_bot_settings, mock_send,
            mock_get_partner_auth_token
    ):
        from datetime import datetime, timedelta
        from kairon.shared.chat.broadcast.data_objects import MessageBroadcastSettings, MessageBroadcastLogs

        bot = 'test_execute_message_broadcast_with_resend_broadcast_with_meta_error_codes_to_skip'
        user = 'test_user'
        config = {
            "name": "test_broadcast", "broadcast_type": "static",
            "connector_type": "whatsapp",
            "recipients_config": {
                "recipients": "919876543210,919012345678,919012341234"
            },
            "template_config": [
                {
                    'language': 'hi',
                    "template_id": "brochure_pdf",
                }
            ],
            "status": False,
            "bot": bot,
            "user": user
        }
        template = [
            {
                "format": "TEXT",
                "text": "Kisan Suvidha Program Follow-up",
                "type": "HEADER"
            },
            {
                "text": "Hello! As a part of our Kisan Suvidha program, I am dedicated to supporting farmers like you in maximizing your crop productivity and overall yield.\n\nI wanted to reach out to inquire if you require any assistance with your current farming activities. Our team of experts, including our skilled agronomists, are here to lend a helping hand wherever needed.",
                "type": "BODY"
            },
            {
                "text": "reply with STOP to unsubscribe",
                "type": "FOOTER"
            },
            {
                "buttons": [
                    {
                        "text": "Connect to Agronomist",
                        "type": "QUICK_REPLY"
                    }
                ],
                "type": "BUTTONS"
            }
        ]

        url = f"http://localhost:5001/api/events/execute/{EventClass.message_broadcast}?is_scheduled=False"
        template_url = 'https://hub.360dialog.io/api/v2/partners/sdfghjkjhgfddfghj/waba_accounts/asdfghjk/waba_templates?filters={"business_templates.name": "brochure_pdf"}&sort=business_templates.name'
        responses.add(
            "POST", url,
            json={"message": "Event Triggered!", "success": True, "error_code": 0, "data": None}
        )
        responses.add(
            "GET", template_url,
            json={"waba_templates": [
                {"category": "MARKETING", "components": template, "name": "agronomy_support", "language": "hi"}]}
        )

        mock_get_bot_settings.return_value = {"whatsapp": "360dialog", "notification_scheduling_limit": 4,
                                              "dynamic_broadcast_execution_timeout": 21600}
        mock_channel_config.return_value = {
            "config": {"access_token": "shjkjhrefdfghjkl", "from_phone_number_id": "918958030415",
                       "waba_account_id": "asdfghjk"}}
        mock_send.return_value = {"contacts": [{"input": "919876543210", "status": "valid", "wa_id": "55123456789"}],
                                  "messages": [{"id": 'wamid.HBgMOTE5NTE1OTkxNjg1FQIAERgSODFFNEM0QkM5MEJBODM4MjIBB==',
                                                "message_status": 'accepted'}]}
        mock_get_partner_auth_token.return_value = None

        msg_broadcast_id = MessageBroadcastSettings(**config).save().id.__str__()
        timestamp = datetime.utcnow()
        MessageBroadcastLogs(
            **{
                "reference_id": "667bed955bfdaf3466b19de3",
                "log_type": "common",
                "bot": bot,
                "status": "Completed",
                "user": "test_user",
                "event_id": msg_broadcast_id,
                "recipients": ["919876543210", "919012345678", "919012341234"],
                "timestamp": timestamp,

            }
        ).save()
        timestamp = timestamp + timedelta(minutes=2)
        MessageBroadcastLogs(
            **{
                "reference_id": "667bed955bfdaf3466b19de3",
                "log_type": "send",
                "bot": bot,
                "status": "Success",
                "template_name": "brochure_pdf",
                "template": template,
                "namespace": "54500467_f322_4595_becd_419af88spm4",
                "language_code": "hi",
                "errors": [],
                "api_response": {
                    "messaging_product": "whatsapp",
                    "contacts": [
                        {
                            "input": "919012345678",
                            "wa_id": "919012345678"
                        }
                    ],
                    "messages": [
                        {
                            "id": "wamid.HBgLMTIxMTU1NTc5NDcVAgARGBIyRkQxREUxRDJFQUJGMkQ3NDIZ"
                        }
                    ]
                },
                "recipient": "919012345678",
                "template_params": [
                    {
                        "type": "header",
                        "parameters": [
                            {
                                "type": "document",
                                "document": {
                                    "link": "https://drive.google.com/uc?export=download&id=1GXQ43jilSDelRvy1kr3PNNpl1e21dRXm",
                                    "filename": "Brochure.pdf",
                                },
                            }
                        ],
                    }
                ],
                "timestamp": timestamp,
                "retry_count": 0
            }
        ).save()
        timestamp = timestamp + timedelta(minutes=2)
        MessageBroadcastLogs(
            **{
                "reference_id": "667bed955bfdaf3466b19de3",
                "log_type": "send",
                "bot": bot,
                "status": "Success",
                "template_name": "brochure_pdf",
                "template": template,
                "namespace": "54500467_f322_4595_becd_419af88spm4",
                "language_code": "hi",
                "errors": [
                    {
                        "code": 130472,
                        "title": "User's number is part of an experiment",
                        "message": "User's number is part of an experiment",
                        "error_data": {
                            "details": "Failed to send message because this user's phone number is part of an experiment"
                        },
                        "href": "https://developers.facebook.com/docs/whatsapp/cloud-api/support/error-codes/"
                    }
                ],
                "api_response": {
                    "messaging_product": "whatsapp",
                    "contacts": [
                        {
                            "input": "919876543210",
                            "wa_id": "919876543210"
                        }
                    ],
                    "messages": [
                        {
                            "id": "wamid.HBgMOTE5NTE1OTkxNjg1FQIAERgSODFFNEM0QkM5MEJBODM4MjI4AA=="
                        }
                    ]
                },
                "recipient": "919876543210",
                "template_params": [
                    {
                        "type": "header",
                        "parameters": [
                            {
                                "type": "document",
                                "document": {
                                    "link": "https://drive.google.com/uc?export=download&id=1GXQ43jilSDelRvy1kr3PNNpl1e21dRXm",
                                    "filename": "Brochure.pdf",
                                },
                            }
                        ],
                    }
                ],
                "timestamp": timestamp,
                "retry_count": 0
            }
        ).save()

        MessageBroadcastLogs(
            **{
                "reference_id": "667bed955bfdaf3466b19de3",
                "log_type": "send",
                "bot": bot,
                "status": "Success",
                "template_name": "brochure_pdf",
                "template": template,
                "namespace": "54500467_f322_4595_becd_419af88spm4",
                "language_code": "hi",
                "errors": [
                    {
                        "code": 131021,
                        "title": "Sender and recipient phone number is the same.",
                        "message": "Sender and recipient phone number is the same.",
                        "error_data": {
                            "details": "Send a message to a phone number different from the sender."
                        },
                        "href": "https://developers.facebook.com/docs/whatsapp/cloud-api/support/error-codes/"
                    }
                ],
                "api_response": {
                    "messaging_product": "whatsapp",
                    "contacts": [
                        {
                            "input": "919876543210",
                            "wa_id": "919876543210"
                        }
                    ],
                    "messages": [
                        {
                            "id": "wamid.HBgMOTE5NTE1OTkxNjg1FQIAERgSODFFNEM0QkM5MEJBODM4MjI4AB=="
                        }
                    ]
                },
                "recipient": "919876543210",
                "template_params": [
                    {
                        "type": "header",
                        "parameters": [
                            {
                                "type": "document",
                                "document": {
                                    "link": "https://drive.google.com/uc?export=download&id=1GXQ43jilSDelRvy1kr3PNNpl1e21dRXm",
                                    "filename": "Brochure.pdf",
                                },
                            }
                        ],
                    }
                ],
                "timestamp": timestamp,
                "retry_count": 0
            }
        ).save()

        ChannelLogs(
            type=ChannelTypes.WHATSAPP.value,
            status='sent',
            data={'id': 'CONVERSATION_ID', 'expiration_timestamp': '1691598412',
                  'origin': {'type': 'business_initated'}},
            initiator='business_initated',
            message_id='wamid.HBgLMTIxMTU1NTc5NDcVAgARGBIyRkQxREUxRDJFQUJGMkQ3NDIZ',
            campaign_id="667bed955bfdaf3466b19de3",
            bot=bot,
            user=user
        ).save()
        ChannelLogs(
            type=ChannelTypes.WHATSAPP.value,
            status='delivered',
            data={'id': 'CONVERSATION_ID', 'expiration_timestamp': '1691598412',
                  'origin': {'type': 'business_initated'}},
            initiator='business_initated',
            message_id='wamid.HBgLMTIxMTU1NTc5NDcVAgARGBIyRkQxREUxRDJFQUJGMkQ3NDIZ',
            campaign_id="667bed955bfdaf3466b19de3",
            bot=bot,
            user=user
        ).save()
        ChannelLogs(
            type=ChannelTypes.WHATSAPP.value,
            status='read',
            data={'id': 'CONVERSATION_ID', 'expiration_timestamp': '1691598412',
                  'origin': {'type': 'business_initated'}},
            initiator='business_initated',
            message_id='wamid.HBgLMTIxMTU1NTc5NDcVAgARGBIyRkQxREUxRDJFQUJGMkQ3NDIZ',
            campaign_id="667bed955bfdaf3466b19de3",
            bot=bot,
            user=user
        ).save()

        ChannelLogs(
            type=ChannelTypes.WHATSAPP.value,
            status='sent',
            data={'id': 'CONVERSATION_ID', 'expiration_timestamp': '1691598412',
                  'origin': {'type': 'business_initated'}},
            initiator='business_initated',
            message_id='wamid.HBgMOTE5NTE1OTkxNjg1FQIAERgSODFFNEM0QkM5MEJBODM4MjIBB==',
            campaign_id="667bed955bfdaf3466b19de3",
            bot=bot,
            user=user
        ).save()
        ChannelLogs(
            type=ChannelTypes.WHATSAPP.value,
            status='delivered',
            data={'id': 'CONVERSATION_ID', 'expiration_timestamp': '1691598412',
                  'origin': {'type': 'business_initated'}},
            initiator='business_initated',
            message_id='wamid.HBgMOTE5NTE1OTkxNjg1FQIAERgSODFFNEM0QkM5MEJBODM4MjIBB==',
            campaign_id="667bed955bfdaf3466b19de3",
            bot=bot,
            user=user
        ).save()
        ChannelLogs(
            type=ChannelTypes.WHATSAPP.value,
            status='read',
            data={'id': 'CONVERSATION_ID', 'expiration_timestamp': '1691598412',
                  'origin': {'type': 'business_initated'}},
            initiator='business_initated',
            message_id='wamid.HBgMOTE5NTE1OTkxNjg1FQIAERgSODFFNEM0QkM5MEJBODM4MjIBB==',
            campaign_id="667bed955bfdaf3466b19de3",
            bot=bot,
            user=user
        ).save()

        ChannelLogs(
            type=ChannelTypes.WHATSAPP.value,
            status='failed',
            data={'id': 'CONVERSATION_ID', 'expiration_timestamp': '1691598412',
                  'origin': {'type': 'business_initated'}},
            initiator='business_initated',
            message_id='wamid.HBgMOTE5NTE1OTkxNjg1FQIAERgSODFFNEM0QkM5MEJBODM4MjI4AA==',
            campaign_id="667bed955bfdaf3466b19de3",
            errors=[
                {
                    "code": 130472,
                    "title": "User's number is part of an experiment",
                    "message": "User's number is part of an experiment",
                    "error_data": {
                        "details": "Failed to send message because this user's phone number is part of an experiment"
                    },
                    "href": "https://developers.facebook.com/docs/whatsapp/cloud-api/support/error-codes/"
                }
            ],
            bot=bot,
            user=user
        ).save()

        ChannelLogs(
            type=ChannelTypes.WHATSAPP.value,
            status='failed',
            data={'id': 'CONVERSATION_ID', 'expiration_timestamp': '1691598412',
                  'origin': {'type': 'business_initated'}},
            initiator='business_initated',
            message_id='wamid.HBgMOTE5NTE1OTkxNjg1FQIAERgSODFFNEM0QkM5MEJBODM4MjI4AB==',
            campaign_id="667bed955bfdaf3466b19de3",
            errors=[
                {
                    "code": 131021,
                    "title": "Sender and recipient phone number is the same.",
                    "message": "Sender and recipient phone number is the same.",
                    "error_data": {
                        "details": "Send a message to a phone number different from the sender."
                    },
                    "href": "https://developers.facebook.com/docs/whatsapp/cloud-api/support/error-codes/"
                }
            ],
            bot=bot,
            user=user
        ).save()

        with patch.dict(Utility.environment["channels"]["360dialog"], {"partner_id": "sdfghjkjhgfddfghj"}):
            event = MessageBroadcastEvent(bot, user)
            event.validate()
            event_id = event.enqueue(EventRequestType.resend_broadcast.value,
                                     msg_broadcast_id=msg_broadcast_id)
            event.execute(event_id, is_resend=True)

        logs = MessageBroadcastProcessor.get_broadcast_logs(bot)
        assert len(logs[0]) == logs[1] == 5
        logs[0][3].pop("timestamp")
        reference_id = logs[0][3].get("reference_id")
        logged_config = logs[0][3]
        assert logged_config == {
            'reference_id': reference_id, 'log_type': 'resend',
            'bot': 'test_execute_message_broadcast_with_resend_broadcast_with_meta_error_codes_to_skip',
            'status': 'Success',
            'api_response': {'contacts': [{'input': '919876543210', 'status': 'valid', 'wa_id': '55123456789'}],
                             'messages': [{'id': 'wamid.HBgMOTE5NTE1OTkxNjg1FQIAERgSODFFNEM0QkM5MEJBODM4MjIBB==',
                                           'message_status': 'accepted'}]},
            'recipient': '919876543210',
            'template_params': [
                {'type': 'header',
                 'parameters': [
                     {'type': 'document',
                      'document': {'link': 'https://drive.google.com/uc?export=download&id=1GXQ43jilSDelRvy1kr3PNNpl1e21dRXm',
                                   'filename': 'Brochure.pdf'}}]}],
            'template': [{'format': 'TEXT', 'text': 'Kisan Suvidha Program Follow-up', 'type': 'HEADER'},
                         {'text': 'Hello! As a part of our Kisan Suvidha program, I am dedicated to supporting farmers like you in maximizing your crop productivity and overall yield.\n\nI wanted to reach out to inquire if you require any assistance with your current farming activities. Our team of experts, including our skilled agronomists, are here to lend a helping hand wherever needed.', 'type': 'BODY'},
                         {'text': 'reply with STOP to unsubscribe', 'type': 'FOOTER'},
                         {'buttons': [{'text': 'Connect to Agronomist', 'type': 'QUICK_REPLY'}], 'type': 'BUTTONS'}],
            'event_id': event_id, 'template_name': 'brochure_pdf', 'language_code': 'hi',
            'namespace': '54500467_f322_4595_becd_419af88spm4', 'retry_count': 1, 'errors': []}

        logs[0][4].pop("timestamp")
        logs[0][4].get("config").pop("timestamp")
        reference_id = logs[0][4].get("reference_id")
        logs[0][4].pop("retry_1_timestamp")
        logged_config = logs[0][4]
        assert logged_config == {
            'reference_id': reference_id, 'log_type': 'common',
            'bot': 'test_execute_message_broadcast_with_resend_broadcast_with_meta_error_codes_to_skip',
            'status': 'Completed', 'user': 'test_user', 'event_id': event_id,
            'recipients': ['919876543210', '919012345678', '919012341234'],
            'config': {'_id': event_id, 'name': 'test_broadcast',
                       'connector_type': 'whatsapp', 'broadcast_type': 'static',
                       'recipients_config': {'recipients': '919876543210,919012345678,919012341234'},
                       'template_config': [{'template_id': 'brochure_pdf', 'language': 'hi'}], 'retry_count': 0,
                       'bot': 'test_execute_message_broadcast_with_resend_broadcast_with_meta_error_codes_to_skip',
                       'user': 'test_user', 'status': False, 'pyscript_timeout': 21600},
            'resend_count_1': 1, 'skipped_count_1': 1}

        assert ChannelLogs.objects(
            bot=bot, message_id='wamid.HBgMOTE5NTE1OTkxNjg1FQIAERgSODFFNEM0QkM5MEJBODM4MjIBB==', status="sent"
        ).get().campaign_id == reference_id

        result = MessageBroadcastProcessor.get_channel_metrics(ChannelTypes.WHATSAPP.value, bot)
        assert result == [
            {
                'campaign_metrics': [
                    {
                        'retry_count': 0,
                        'statuses': {'delivered': 1, 'failed': 2, 'read': 1, 'sent': 1}
                    },
                    {
                        'retry_count': 1,
                        'statuses': {'delivered': 1, 'read': 1, 'sent': 1}
                    }
                ],
                'campaign_id': reference_id
            }
        ]


    @responses.activate
    @mongomock.patch(servers=(('localhost', 27017),))
    @patch("kairon.shared.channels.whatsapp.bsp.dialog360.BSP360Dialog.get_partner_auth_token", autospec=True)
    @patch("kairon.chat.handlers.channels.clients.whatsapp.dialog360.BSP360Dialog.send_template_message")
    @patch("kairon.shared.data.processor.MongoProcessor.get_bot_settings")
    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    @patch("kairon.shared.utils.Utility.is_exist", autospec=True)
    def test_execute_message_broadcast_with_resend_broadcast_multiple_times(
            self, mock_is_exist, mock_channel_config, mock_get_bot_settings, mock_send,
            mock_get_partner_auth_token
    ):
        from datetime import datetime, timedelta
        from kairon.shared.chat.broadcast.data_objects import MessageBroadcastSettings, MessageBroadcastLogs

        bot = 'test_execute_message_broadcast_with_resend_broadcast_multiple_times'
        user = 'test_user'
        config = {
            "name": "test_broadcast", "broadcast_type": "static",
            "connector_type": "whatsapp",
            "recipients_config": {
                "recipients": "919876543210,919012345678,919012341234"
            },
            "template_config": [
                {
                    'language': 'hi',
                    "template_id": "brochure_pdf",
                }
            ],
            "status": False,
            "retry_count": 1,
            "bot": bot,
            "user": user
        }
        template = [
            {
                "format": "TEXT",
                "text": "Kisan Suvidha Program Follow-up",
                "type": "HEADER"
            },
            {
                "text": "Hello! As a part of our Kisan Suvidha program, I am dedicated to supporting farmers like you in maximizing your crop productivity and overall yield.\n\nI wanted to reach out to inquire if you require any assistance with your current farming activities. Our team of experts, including our skilled agronomists, are here to lend a helping hand wherever needed.",
                "type": "BODY"
            },
            {
                "text": "reply with STOP to unsubscribe",
                "type": "FOOTER"
            },
            {
                "buttons": [
                    {
                        "text": "Connect to Agronomist",
                        "type": "QUICK_REPLY"
                    }
                ],
                "type": "BUTTONS"
            }
        ]

        url = f"http://localhost:5001/api/events/execute/{EventClass.message_broadcast}?is_scheduled=False"
        template_url = 'https://hub.360dialog.io/api/v2/partners/sdfghjkjhgfddfghj/waba_accounts/asdfghjk/waba_templates?filters={"business_templates.name": "brochure_pdf"}&sort=business_templates.name'
        responses.add(
            "POST", url,
            json={"message": "Event Triggered!", "success": True, "error_code": 0, "data": None}
        )
        responses.add(
            "GET", template_url,
            json={"waba_templates": [
                {"category": "MARKETING", "components": template, "name": "agronomy_support", "language": "hi"}]}
        )

        mock_get_bot_settings.return_value = {"whatsapp": "360dialog", "notification_scheduling_limit": 4,
                                              "dynamic_broadcast_execution_timeout": 21600}
        mock_channel_config.return_value = {
            "config": {"access_token": "shjkjhrefdfghjkl", "from_phone_number_id": "918958030415",
                       "waba_account_id": "asdfghjk"}}
        mock_send.return_value = {"contacts": [{"input": "919876543210", "status": "valid", "wa_id": "55123456789"}],
                                  "messages": [{"id": 'wamid.HBgMOTE5NTE1OTkxNjg1FQIAERgSODFFNEM0QkM5MEJBODM4MjIBB==',
                                                "message_status": 'accepted'}]}
        mock_get_partner_auth_token.return_value = None

        msg_broadcast_id = MessageBroadcastSettings(**config).save().id.__str__()
        timestamp = datetime.utcnow()
        MessageBroadcastLogs(
            **{
                "reference_id": "667bed955bfdaf3466b19de4",
                "log_type": "common",
                "bot": bot,
                "status": "Completed",
                "user": "test_user",
                "total": 3,
                "resend_count_1": 2,
                "skipped_count_1": 0,
                "event_id": msg_broadcast_id,
                "recipients": ["919876543210", "919012345678", "919012341234"],
                "timestamp": timestamp,

            }
        ).save()
        timestamp = timestamp + timedelta(minutes=2)
        MessageBroadcastLogs(
            **{
                "reference_id": "667bed955bfdaf3466b19de4",
                "log_type": "send",
                "bot": bot,
                "status": "Success",
                "template_name": "brochure_pdf",
                "template": template,
                "namespace": "54500467_f322_4595_becd_419af88spm4",
                "language_code": "hi",
                "errors": [],
                "api_response": {
                    "messaging_product": "whatsapp",
                    "contacts": [
                        {
                            "input": "919012345678",
                            "wa_id": "919012345678"
                        }
                    ],
                    "messages": [
                        {
                            "id": "wamid.HBgLMTIxMTU1NTc5NDcVAgARGBIyRkQxREUxRDJFQUJGMkQ3NDIZ"
                        }
                    ]
                },
                "recipient": "919012345678",
                "template_params": [
                    {
                        "type": "header",
                        "parameters": [
                            {
                                "type": "document",
                                "document": {
                                    "link": "https://drive.google.com/uc?export=download&id=1GXQ43jilSDelRvy1kr3PNNpl1e21dRXm",
                                    "filename": "Brochure.pdf",
                                },
                            }
                        ],
                    }
                ],
                "timestamp": timestamp,
                "retry_count": 0
            }
        ).save()
        timestamp = timestamp + timedelta(minutes=2)
        MessageBroadcastLogs(
            **{
                "reference_id": "667bed955bfdaf3466b19de4",
                "log_type": "send",
                "bot": bot,
                "status": "Success",
                "template_name": "brochure_pdf",
                "template": template,
                "namespace": "54500467_f322_4595_becd_419af88spm4",
                "language_code": "hi",
                "errors": [
                    {
                        "code": 130472,
                        "title": "User's number is part of an experiment",
                        "message": "User's number is part of an experiment",
                        "error_data": {
                            "details": "Failed to send message because this user's phone number is part of an experiment"
                        },
                        "href": "https://developers.facebook.com/docs/whatsapp/cloud-api/support/error-codes/"
                    }
                ],
                "api_response": {
                    "messaging_product": "whatsapp",
                    "contacts": [
                        {
                            "input": "919876543210",
                            "wa_id": "919876543210"
                        }
                    ],
                    "messages": [
                        {
                            "id": "wamid.HBgMOTE5NTE1OTkxNjg1FQIAERgSODFFNEM0QkM5MEJBODM4MjI4AA=="
                        }
                    ]
                },
                "recipient": "919876543210",
                "template_params": [
                    {
                        "type": "header",
                        "parameters": [
                            {
                                "type": "document",
                                "document": {
                                    "link": "https://drive.google.com/uc?export=download&id=1GXQ43jilSDelRvy1kr3PNNpl1e21dRXm",
                                    "filename": "Brochure.pdf",
                                },
                            }
                        ],
                    }
                ],
                "timestamp": timestamp,
                "retry_count": 0
            }
        ).save()

        MessageBroadcastLogs(
            **{
                "reference_id": "667bed955bfdaf3466b19de4",
                "log_type": "send",
                "bot": bot,
                "status": "Success",
                "template_name": "brochure_pdf",
                "template": template,
                "namespace": "54500467_f322_4595_becd_419af88spm4",
                "language_code": "hi",
                "errors": [
                    {
                        "code": 131026,
                        "title": "Sender and recipient phone number is the same.",
                        "message": "Sender and recipient phone number is the same.",
                        "error_data": {
                            "details": "Send a message to a phone number different from the sender."
                        },
                        "href": "https://developers.facebook.com/docs/whatsapp/cloud-api/support/error-codes/"
                    }
                ],
                "api_response": {
                    "messaging_product": "whatsapp",
                    "contacts": [
                        {
                            "input": "919876543210",
                            "wa_id": "919876543210"
                        }
                    ],
                    "messages": [
                        {
                            "id": "wamid.HBgMOTE5NTE1OTkxNjg1FQIAERgSODFFNEM0QkM5MEJBODM4MjI4AB=="
                        }
                    ]
                },
                "recipient": "919876543210",
                "template_params": [
                    {
                        "type": "header",
                        "parameters": [
                            {
                                "type": "document",
                                "document": {
                                    "link": "https://drive.google.com/uc?export=download&id=1GXQ43jilSDelRvy1kr3PNNpl1e21dRXm",
                                    "filename": "Brochure.pdf",
                                },
                            }
                        ],
                    }
                ],
                "timestamp": timestamp,
                "retry_count": 0
            }
        ).save()

        MessageBroadcastLogs(
            **{
                "reference_id": "667bed955bfdaf3466b19de4",
                "log_type": "resend",
                "bot": bot,
                "status": "Success",
                "template_name": "brochure_pdf",
                "template": template,
                "namespace": "54500467_f322_4595_becd_419af88spm4",
                "language_code": "hi",
                "errors": [
                    {
                        "code": 130472,
                        "title": "User's number is part of an experiment",
                        "message": "User's number is part of an experiment",
                        "error_data": {
                            "details": "Failed to send message because this user's phone number is part of an experiment"
                        },
                        "href": "https://developers.facebook.com/docs/whatsapp/cloud-api/support/error-codes/"
                    }
                ],
                "api_response": {
                    "messaging_product": "whatsapp",
                    "contacts": [
                        {
                            "input": "919876543210",
                            "wa_id": "919876543210"
                        }
                    ],
                    "messages": [
                        {
                            "id": "wamid.HBgMOTE5NTE1OTkxNjg1FQIAERgSODFFNEM0QkM5MEJBODM4MjI4AB=="
                        }
                    ]
                },
                "recipient": "919876543210",
                "template_params": [
                    {
                        "type": "header",
                        "parameters": [
                            {
                                "type": "document",
                                "document": {
                                    "link": "https://drive.google.com/uc?export=download&id=1GXQ43jilSDelRvy1kr3PNNpl1e21dRXm",
                                    "filename": "Brochure.pdf",
                                },
                            }
                        ],
                    }
                ],
                "timestamp": timestamp,
                "retry_count": 1
            }
        ).save()

        ChannelLogs(
            type=ChannelTypes.WHATSAPP.value,
            status='sent',
            data={'id': 'CONVERSATION_ID', 'expiration_timestamp': '1691598412',
                  'origin': {'type': 'business_initated'}},
            initiator='business_initated',
            message_id='wamid.HBgLMTIxMTU1NTc5NDcVAgARGBIyRkQxREUxRDJFQUJGMkQ3NDIZ',
            campaign_id="667bed955bfdaf3466b19de4",
            bot=bot,
            user=user
        ).save()
        ChannelLogs(
            type=ChannelTypes.WHATSAPP.value,
            status='delivered',
            data={'id': 'CONVERSATION_ID', 'expiration_timestamp': '1691598412',
                  'origin': {'type': 'business_initated'}},
            initiator='business_initated',
            message_id='wamid.HBgLMTIxMTU1NTc5NDcVAgARGBIyRkQxREUxRDJFQUJGMkQ3NDIZ',
            campaign_id="667bed955bfdaf3466b19de4",
            bot=bot,
            user=user
        ).save()
        ChannelLogs(
            type=ChannelTypes.WHATSAPP.value,
            status='read',
            data={'id': 'CONVERSATION_ID', 'expiration_timestamp': '1691598412',
                  'origin': {'type': 'business_initated'}},
            initiator='business_initated',
            message_id='wamid.HBgLMTIxMTU1NTc5NDcVAgARGBIyRkQxREUxRDJFQUJGMkQ3NDIZ',
            campaign_id="667bed955bfdaf3466b19de4",
            bot=bot,
            user=user
        ).save()

        ChannelLogs(
            type=ChannelTypes.WHATSAPP.value,
            status='sent',
            data={'id': 'CONVERSATION_ID', 'expiration_timestamp': '1691598412',
                  'origin': {'type': 'business_initated'}},
            initiator='business_initated',
            message_id='wamid.HBgMOTE5NTE1OTkxNjg1FQIAERgSODFFNEM0QkM5MEJBODM4MjIBB==',
            campaign_id="667bed955bfdaf3466b19de4",
            bot=bot,
            user=user
        ).save()
        ChannelLogs(
            type=ChannelTypes.WHATSAPP.value,
            status='delivered',
            data={'id': 'CONVERSATION_ID', 'expiration_timestamp': '1691598412',
                  'origin': {'type': 'business_initated'}},
            initiator='business_initated',
            message_id='wamid.HBgMOTE5NTE1OTkxNjg1FQIAERgSODFFNEM0QkM5MEJBODM4MjIBB==',
            campaign_id="667bed955bfdaf3466b19de4",
            bot=bot,
            user=user
        ).save()
        ChannelLogs(
            type=ChannelTypes.WHATSAPP.value,
            status='read',
            data={'id': 'CONVERSATION_ID', 'expiration_timestamp': '1691598412',
                  'origin': {'type': 'business_initated'}},
            initiator='business_initated',
            message_id='wamid.HBgMOTE5NTE1OTkxNjg1FQIAERgSODFFNEM0QkM5MEJBODM4MjIBB==',
            campaign_id="667bed955bfdaf3466b19de4",
            bot=bot,
            user=user
        ).save()

        ChannelLogs(
            type=ChannelTypes.WHATSAPP.value,
            status='failed',
            data={'id': 'CONVERSATION_ID', 'expiration_timestamp': '1691598412',
                  'origin': {'type': 'business_initated'}},
            initiator='business_initated',
            message_id='wamid.HBgMOTE5NTE1OTkxNjg1FQIAERgSODFFNEM0QkM5MEJBODM4MjI4AA==',
            campaign_id="667bed955bfdaf3466b19de4",
            errors=[
                {
                    "code": 130472,
                    "title": "User's number is part of an experiment",
                    "message": "User's number is part of an experiment",
                    "error_data": {
                        "details": "Failed to send message because this user's phone number is part of an experiment"
                    },
                    "href": "https://developers.facebook.com/docs/whatsapp/cloud-api/support/error-codes/"
                }
            ],
            bot=bot,
            user=user
        ).save()

        ChannelLogs(
            type=ChannelTypes.WHATSAPP.value,
            status='failed',
            data={'id': 'CONVERSATION_ID', 'expiration_timestamp': '1691598412',
                  'origin': {'type': 'business_initated'}},
            initiator='business_initated',
            message_id='wamid.HBgMOTE5NTE1OTkxNjg1FQIAERgSODFFNEM0QkM5MEJBODM4MjI4AB==',
            campaign_id="667bed955bfdaf3466b19de4",
            errors=[
                {
                    "code": 131021,
                    "title": "Sender and recipient phone number is the same.",
                    "message": "Sender and recipient phone number is the same.",
                    "error_data": {
                        "details": "Send a message to a phone number different from the sender."
                    },
                    "href": "https://developers.facebook.com/docs/whatsapp/cloud-api/support/error-codes/"
                }
            ],
            bot=bot,
            user=user
        ).save()
        ChannelLogs(
            type=ChannelTypes.WHATSAPP.value,
            status='failed',
            data={'id': 'CONVERSATION_ID', 'expiration_timestamp': '1691598412',
                  'origin': {'type': 'business_initated'}},
            initiator='business_initated',
            message_id='wamid.HBgMOTE5NTE1OTkxNjg1FQIAERgSODFFNEM0QkM5MEJBODM4MjI4ABC==',
            campaign_id="667bed955bfdaf3466b19de4",
            retry_count=1,
            errors=[
                {
                    "code": 131021,
                    "title": "Sender and recipient phone number is the same.",
                    "message": "Sender and recipient phone number is the same.",
                    "error_data": {
                        "details": "Send a message to a phone number different from the sender."
                    },
                    "href": "https://developers.facebook.com/docs/whatsapp/cloud-api/support/error-codes/"
                }
            ],
            bot=bot,
            user=user
        ).save()
        ChannelLogs(
            type=ChannelTypes.WHATSAPP.value,
            status='sent',
            data={'id': 'CONVERSATION_ID', 'expiration_timestamp': '1691598412',
                  'origin': {'type': 'business_initated'}},
            initiator='business_initated',
            message_id='wamid.HBgMOTE5NTE1OTkxNjg1FQIAERgSODFFNEM0QkM5MEJBODM4MjIBBD==',
            campaign_id="667bed955bfdaf3466b19de4",
            retry_count=1,
            bot=bot,
            user=user
        ).save()
        ChannelLogs(
            type=ChannelTypes.WHATSAPP.value,
            status='delivered',
            data={'id': 'CONVERSATION_ID', 'expiration_timestamp': '1691598412',
                  'origin': {'type': 'business_initated'}},
            initiator='business_initated',
            message_id='wamid.HBgMOTE5NTE1OTkxNjg1FQIAERgSODFFNEM0QkM5MEJBODM4MjIBBD==',
            campaign_id="667bed955bfdaf3466b19de4",
            retry_count=1,
            bot=bot,
            user=user
        ).save()
        ChannelLogs(
            type=ChannelTypes.WHATSAPP.value,
            status='read',
            data={'id': 'CONVERSATION_ID', 'expiration_timestamp': '1691598412',
                  'origin': {'type': 'business_initated'}},
            initiator='business_initated',
            message_id='wamid.HBgMOTE5NTE1OTkxNjg1FQIAERgSODFFNEM0QkM5MEJBODM4MjIBBD==',
            campaign_id="667bed955bfdaf3466b19de4",
            retry_count=1,
            bot=bot,
            user=user
        ).save()

        with patch.dict(Utility.environment["channels"]["360dialog"], {"partner_id": "sdfghjkjhgfddfghj"}):
            event = MessageBroadcastEvent(bot, user)
            event.validate()
            event_id = event.enqueue(EventRequestType.resend_broadcast.value,
                                     msg_broadcast_id=msg_broadcast_id)
            event.execute(event_id, is_resend=True)

        logs = MessageBroadcastProcessor.get_broadcast_logs(bot)
        assert len(logs[0]) == logs[1] == 6
        logs[0][4].pop("timestamp")
        reference_id = logs[0][4].get("reference_id")
        logged_config = logs[0][4]
        assert logged_config == {
            'reference_id': reference_id, 'log_type': 'resend',
            'bot': 'test_execute_message_broadcast_with_resend_broadcast_multiple_times',
            'status': 'Success',
            'api_response': {'contacts': [{'input': '919876543210', 'status': 'valid', 'wa_id': '55123456789'}],
                             'messages': [{'id': 'wamid.HBgMOTE5NTE1OTkxNjg1FQIAERgSODFFNEM0QkM5MEJBODM4MjIBB==',
                                           'message_status': 'accepted'}]},
            'recipient': '919876543210', 'template_params': [
                {'type': 'header',
                 'parameters': [{'type': 'document', 'document': {'link': 'https://drive.google.com/uc?export=download&id=1GXQ43jilSDelRvy1kr3PNNpl1e21dRXm',
                                                                  'filename': 'Brochure.pdf'}}]}],
            'template': [{'format': 'TEXT', 'text': 'Kisan Suvidha Program Follow-up', 'type': 'HEADER'},
                         {'text': 'Hello! As a part of our Kisan Suvidha program, I am dedicated to supporting farmers like you in maximizing your crop productivity and overall yield.\n\nI wanted to reach out to inquire if you require any assistance with your current farming activities. Our team of experts, including our skilled agronomists, are here to lend a helping hand wherever needed.', 'type': 'BODY'},
                         {'text': 'reply with STOP to unsubscribe', 'type': 'FOOTER'},
                         {'buttons': [{'text': 'Connect to Agronomist', 'type': 'QUICK_REPLY'}], 'type': 'BUTTONS'}],
            'event_id': event_id, 'template_name': 'brochure_pdf', 'language_code': 'hi',
            'namespace': '54500467_f322_4595_becd_419af88spm4', 'retry_count': 2, 'errors': []}

        logs[0][5].pop("timestamp")
        logs[0][5].get("config").pop("timestamp")
        reference_id = logs[0][5].get("reference_id")
        logs[0][5].pop("retry_2_timestamp")
        logged_config = logs[0][5]
        assert logged_config == {
            'reference_id': reference_id, 'log_type': 'common',
            'bot': 'test_execute_message_broadcast_with_resend_broadcast_multiple_times', 'status': 'Completed',
            'user': 'test_user', 'total': 3, 'resend_count_1': 2, 'skipped_count_1': 0, 'event_id': event_id,
            'recipients': ['919876543210', '919012345678', '919012341234'],
            'config': {'_id': event_id, 'name': 'test_broadcast',
                       'connector_type': 'whatsapp', 'broadcast_type': 'static',
                       'recipients_config': {'recipients': '919876543210,919012345678,919012341234'},
                       'template_config': [{'template_id': 'brochure_pdf', 'language': 'hi'}],
                       'retry_count': 1, 'bot': 'test_execute_message_broadcast_with_resend_broadcast_multiple_times',
                       'user': 'test_user', 'status': False, 'pyscript_timeout': 21600},
            'resend_count_2': 1, 'skipped_count_2': 0}

        assert ChannelLogs.objects(
            bot=bot, message_id='wamid.HBgMOTE5NTE1OTkxNjg1FQIAERgSODFFNEM0QkM5MEJBODM4MjIBB==', status="sent"
        ).get().campaign_id == reference_id

        result = MessageBroadcastProcessor.get_channel_metrics(ChannelTypes.WHATSAPP.value, bot)
        assert result == [
            {
                'campaign_metrics': [
                    {
                        'retry_count': 0,
                        'statuses': {'delivered': 1, 'failed': 2, 'read': 1, 'sent': 1}
                    },
                    {
                        'retry_count': 1,
                        'statuses': {'delivered': 1, 'failed': 1, 'read': 1, 'sent': 1}
                    },
                    {
                        'retry_count': 2,
                        'statuses': {'delivered': 1, 'read': 1, 'sent': 1}
                     }
                ],
                'campaign_id': reference_id
            }
        ]

