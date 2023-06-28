import asyncio
import os
import shutil
import tempfile
import uuid
from io import BytesIO
from unittest.mock import patch
from urllib.parse import urljoin

import pytest
import responses
from fastapi import UploadFile
from mongoengine import connect
from rasa.shared.constants import DEFAULT_DOMAIN_PATH, DEFAULT_DATA_PATH, DEFAULT_CONFIG_PATH
from rasa.shared.importers.rasa import RasaFileImporter
from responses import matchers

from kairon.events.definitions.scheduled_base import ScheduledEventsBase
from kairon.shared.utils import Utility

os.environ["system_file"] = "./tests/testing_data/system.yaml"

from kairon.events.definitions.message_broadcast import MessageBroadcastEvent

from kairon.shared.chat.notifications.processor import MessageBroadcastProcessor
from kairon.events.definitions.data_importer import TrainingDataImporterEvent
from kairon.events.definitions.history_delete import DeleteHistoryEvent
from kairon.events.definitions.model_testing import ModelTestingEvent
from kairon.events.definitions.model_training import ModelTrainingEvent
from kairon.exceptions import AppException
from kairon.shared.constants import EventClass, EventRequestType
from kairon.shared.data.constant import EVENT_STATUS, REQUIREMENTS
from kairon.shared.data.data_objects import Configs, BotSettings
from kairon.shared.data.history_log_processor import HistoryDeletionLogProcessor
from kairon.shared.importer.processor import DataImporterLogProcessor
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.test.processor import ModelTestingLogProcessor
from kairon.test.test_models import ModelTester

from kairon.events.definitions.faq_importer import FaqDataImporterEvent


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
            importer = RasaFileImporter.load_from_config(config_path=config_path,
                                                         domain_path=domain_path,
                                                         training_data_paths=training_data_path)
            domain = await importer.get_domain()
            story_graph = await importer.get_stories()
            config = await importer.get_config()
            nlu = await importer.get_nlu_data(config.get('language'))
            http_actions = Utility.read_yaml(http_actions_path)
            return nlu, story_graph, domain, config, http_actions

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
        assert logs[0].get('exception').__contains__('Failed to read YAML')
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
        assert len(processor.fetch_actions(bot)) == 4
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

        responses.add("POST",
                      event_url,
                      json={"success": True, "message": "Event triggered successfully!"},
                      status=200,
                      match=[
                          responses.matchers.json_params_matcher(
                              {'bot': bot, 'user': user, 'import_data': '--import-data', 'event_type': EventClass.data_importer, 'overwrite': ''})],
                      )
        event = TrainingDataImporterEvent(bot, user, import_data=True)
        event.validate()
        event.enqueue()
        responses.reset()

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
        responses.add("POST",
                      event_url,
                      json={"success": True, "message": "Event triggered successfully!"},
                      status=200,
                      match=[
                          responses.matchers.json_params_matcher(
                              {'bot': bot, 'user': user, 'import_data': '--import-data', 'event_type': EventClass.data_importer, 'overwrite': '--overwrite'})],
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

        responses.add("POST",
                      event_url,
                      json={"success": True, "message": "Event triggered successfully!"},
                      status=200,
                      match=[
                          responses.matchers.json_params_matcher(
                              {'bot': bot, 'user': user, 'import_data': '', 'event_type': EventClass.data_importer, 'overwrite': ''})],
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
        nlu, story_graph, domain, config, http_actions = asyncio.run(get_training_data('tests/testing_data/validator/valid'))
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

    def test_trigger_data_importer_stories_only(self, monkeypatch, get_training_data):
        bot = 'test_trigger_data_importer_stories_only'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(uuid.uuid4()))
        data_path = os.path.join(test_data_path, 'data')
        Utility.make_dirs(data_path)
        shutil.copy2('tests/testing_data/validator/valid/data/stories.yml', data_path)
        nlu, story_graph, domain, config, http_actions = asyncio.run(get_training_data('tests/testing_data/validator/valid'))
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
        nlu, story_graph, domain, config, http_actions = asyncio.run(get_training_data('tests/testing_data/validator/valid'))
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
        nlu, story_graph, domain, config, http_actions = asyncio.run(get_training_data('tests/testing_data/validator/valid'))
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
        assert logs[0]['status'] == 'Success'
        assert logs[0]['event_status'] == EVENT_STATUS.COMPLETED.value

        mongo_processor = MongoProcessor()
        assert len(mongo_processor.fetch_stories(bot)) == 2
        assert len(list(mongo_processor.fetch_training_examples(bot))) == 8
        assert len(list(mongo_processor.fetch_responses(bot))) == 8
        assert len(mongo_processor.fetch_actions(bot)) == 0
        assert len(mongo_processor.fetch_rule_block_names(bot)) == 1

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
        assert len(mongo_processor.fetch_stories(bot)) == 2
        assert len(list(mongo_processor.fetch_training_examples(bot))) == 8
        assert len(list(mongo_processor.fetch_responses(bot))) == 8
        assert len(mongo_processor.fetch_actions(bot)) == 0
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
        logs = list(ModelTestingLogProcessor.get_logs(bot))
        assert len(logs) == 1
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
            domain = await importer.get_domain()
            story_graph = await importer.get_stories()
            config = await importer.get_config()
            nlu = await importer.get_nlu_data(config.get('language'))

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

    def test_trigger_model_testing_event_run_tests_on_model(self, load_data, create_model, monkeypatch):
        import rasa.utils.common

        bot = 'test_events_bot'
        user = 'test_user'
        config_path = 'tests/testing_data/model_tester/config.yml'
        domain_path = 'tests/testing_data/model_tester/domain.yml'
        nlu_path = 'tests/testing_data/model_tester/nlu_success/nlu.yml'
        stories_path = 'tests/testing_data/model_tester/training_stories_success/stories.yml'
        asyncio.run(load_data(config_path, domain_path, nlu_path, stories_path, bot, user))

        def _mock_stories_output(*args, **kwargs):
            return {
                "precision": 0.91,
                "f1": 0.98,
                "accuracy": 0.99,
                "failed_stories": [],
            }

        monkeypatch.setattr(rasa.utils.common, 'run_in_loop', _mock_stories_output)
        ModelTestingEvent(bot, user, run_e2e=False).execute()
        logs = list(ModelTestingLogProcessor.get_logs(bot))
        assert len(logs) == 2
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
        logs = list(ModelTestingLogProcessor.get_logs(bot))
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

        logs = list(ModelTestingLogProcessor.get_logs(bot))
        assert len(logs) == 3
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
                              {'bot': bot, 'user': user, 'augment_data': '--augment'})],
                      )
        ModelTestingEvent(bot, user).enqueue()
        responses.reset()

        logs = list(ModelTestingLogProcessor.get_logs(bot))
        assert len(logs) == 4
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
                              {'bot': bot, 'user': user, 'augment_data': ''})],
                      )
        ModelTestingEvent(bot, user, augment_data=False).enqueue()
        responses.reset()

        logs = list(ModelTestingLogProcessor.get_logs(bot))
        assert len(logs) == 1
        assert not logs[0].get('exception')
        assert logs[0]['start_timestamp']
        assert not logs[0].get('end_timestamp')
        assert not logs[0].get('status')
        assert logs[0]['event_status'] == EVENT_STATUS.ENQUEUED.value
        assert not logs[0]['is_augmented']
        assert not os.path.exists(os.path.join('./testing_data', bot))

    def test_trigger_history_deletion_for_bot(self):
        from datetime import datetime, timedelta
        bot = 'test_events_bot'
        user = 'test_user'
        till_date = datetime.utcnow().date()
        sender_id = ""
        event_url = urljoin(Utility.environment['events']['server_url'], f"/api/events/execute/{EventClass.delete_history}")
        responses.reset()
        responses.add("POST",
                      event_url,
                      json={"success": True, "message": "Event triggered successfully!"},
                      status=200,
                      match=[
                          responses.matchers.json_params_matcher(
                              {'bot': bot, 'user': user, 'till_date': Utility.convert_date_to_string(till_date),
                               'sender_id': sender_id})],
                      )
        responses.start()
        event = DeleteHistoryEvent(bot, user, till_date=till_date, sender_id=None)
        event.validate()
        event.enqueue()
        responses.stop()

        logs = list(HistoryDeletionLogProcessor.get_logs(bot))
        assert len(logs) == 1
        assert not logs[0].get('exception')
        assert logs[0]['start_timestamp']
        assert not logs[0].get('end_timestamp')
        assert logs[0]['status'] == EVENT_STATUS.ENQUEUED.value

    @responses.activate
    def test_execute_message_broadcast_with_static_values(self):
        bot = 'test_execute_message_broadcast'
        user = 'test_user'
        config = {
            "name": "one_time_schedule",
            "connector_type": "whatsapp",
            "recipients_config": {
                "recipient_type": "static",
                "recipients": "918958030541,"
            },
            "template_config": [
                {
                    'language': 'hi',
                    "template_type": "static",
                    "template_id": "brochure_pdf",
                    "namespace": "13b1e228_4a08_4d19_a0da_cdb80bc76380",
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
        with patch("kairon.shared.utils.Utility.is_exist", autospec=True):
            event_id = event.enqueue(EventRequestType.trigger_async.value, config=config)

        with patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config") as mock_channel_config:
            mock_channel_config.return_value = {"config": {"access_token": "shjkjhrefdfghjkl", "from_phone_number_id": "918958030415"}}
            with patch("kairon.shared.data.processor.MongoProcessor.get_bot_settings") as mock_get_bot_settings:
                mock_get_bot_settings.return_value = {"whatsapp": "360dialog"}
                with patch("kairon.chat.handlers.channels.clients.whatsapp.dialog360.BSP360Dialog.send_template_message", autospec=True) as mock_send:
                    mock_send.return_value = {"contacts": [{"input": "+55123456789", "status": "valid", "wa_id": "55123456789"}]}

                    event.execute(event_id)

        logs = MessageBroadcastProcessor.get_broadcast_logs(bot)
        assert len(logs[0]) == logs[1] == 2
        logs[0][1].pop("timestamp")
        reference_id = logs[0][1].pop("reference_id")
        logged_config = logs[0][1].pop("config")
        logged_config.pop("_id")
        logged_config.pop("status")
        logged_config.pop("timestamp")
        assert logged_config == config
        print(logs)
        assert logs[0][1] == {'log_type': 'common', 'bot': 'test_execute_message_broadcast', 'status': 'Completed',
                              'user': 'test_user', 'broadcast_id': event_id, 'recipients': ['918958030541', ''],
                              'failure_cnt': 0, 'total': 2,
                              'Template 1': 'There are 2 recipients and 2 template bodies. Sending 2 messages to 2 recipients.'
                              }
        logs[0][0].pop("timestamp")
        assert logs[0][0] == {'reference_id': reference_id, 'log_type': 'send',
                              'bot': 'test_execute_message_broadcast', 'status': 'Success', 'api_response': {
                'contacts': [{'input': '+55123456789', 'status': 'valid', 'wa_id': '55123456789'}]},
                              'recipient': '918958030541', 'template_params': None}

        with pytest.raises(AppException, match="Notification settings not found!"):
            MessageBroadcastProcessor.get_settings(event_id, bot)

        settings = list(MessageBroadcastProcessor.list_settings(bot, status=False, name="one_time_schedule"))
        assert len(settings) == 1
        assert settings[0]["status"] == False

    @patch("kairon.chat.handlers.channels.clients.whatsapp.dialog360.BSP360Dialog.send_template_message", autospec=True)
    @patch("kairon.shared.data.processor.MongoProcessor.get_bot_settings")
    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    @patch("kairon.shared.utils.Utility.is_exist", autospec=True)
    def test_execute_message_broadcast_with_dynamic_values(self, mock_is_exist, mock_channel_config, mock_get_bot_settings, mock_send):
        bot = 'test_execute_dynamic_message_broadcast'
        user = 'test_user'
        params = [{"type": "header","parameters": [{"type": "document","document":
            {"link": "https://drive.google.com/uc?export=download&id=1GXQ43jilSDelRvy1kr3PNNpl1e21dRXm",
             "filename": "Brochure.pdf"}}]}]
        config = {
            "name": "one_time_schedule",
            "connector_type": "whatsapp",
            "recipients_config": {
                "recipient_type": "dynamic",
                "recipients": "${contacts}"
            },
            "data_extraction_config": {
                "headers": {"api_key": "asdfghjkl", "access_key": "dsfghjkl"},
                "url": "http://kairon.local",
            },
            "template_config": [
                {
                    'language': 'hi',
                    "template_type": "static",
                    "template_id": "brochure_pdf",
                    "namespace": "13b1e228_4a08_4d19_a0da_cdb80bc76380",
                    "data": str([params, params])
                }
            ]
        }

        url = f"http://localhost:5001/api/events/execute/{EventClass.message_broadcast}?is_scheduled=False"
        responses.start()
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
            "POST", "http://localhost:8080/format",
            json={"data": [9876543210, 876543212345], "success": True}
        )

        mock_get_bot_settings.return_value = {"whatsapp": "360dialog", "notification_scheduling_limit": 4}
        mock_channel_config.return_value = {"config": {"access_token": "shjkjhrefdfghjkl", "from_phone_number_id": "918958030415"}}
        mock_send.return_value = {"contacts": [{"input": "+55123456789", "status": "valid", "wa_id": "55123456789"}]}

        event = MessageBroadcastEvent(bot, user)
        event.validate()
        event_id = event.enqueue(EventRequestType.trigger_async.value, config=config)
        event.execute(event_id)
        responses.reset()

        logs = MessageBroadcastProcessor.get_broadcast_logs(bot)
        print(logs)
        assert len(logs[0]) == logs[1] == 3
        logs[0][2].pop("timestamp")
        reference_id = logs[0][2].pop("reference_id")
        logged_config = logs[0][2].pop("config")
        logged_config.pop("_id")
        logged_config.pop("status")
        logged_config.pop("timestamp")
        config['data_extraction_config']["method"] = "GET"
        config['data_extraction_config']["request_body"] = {}
        assert logged_config == config
        assert logs[0][2] == {'log_type': 'common', 'bot': 'test_execute_dynamic_message_broadcast',
                              'status': 'Completed', 'user': 'test_user', 'broadcast_id': event_id,
                              'data_extraction': {'url': 'http://kairon.local',
                                                  'headers': {'api_key': 'asdfghjkl', 'access_key': 'dsfghjkl'},
                                                  'method': 'GET',
                                                  'api_response': {'contacts': ['9876543210', '876543212345']}},
                              'recipients': [9876543210, 876543212345],
                              'evaluation_log': ['evaluation_type: script', 'script: ${contacts}',
                                                 "data: {'contacts': ['9876543210', '876543212345']}",
                                                 'raise_err_on_failure: True',
                                                 "Evaluator response: {'data': [9876543210, 876543212345], 'success': True}"],
                              'template_params': [[{'type': 'header', 'parameters': [{'type': 'document', 'document': {
                                  'link': 'https://drive.google.com/uc?export=download&id=1GXQ43jilSDelRvy1kr3PNNpl1e21dRXm',
                                  'filename': 'Brochure.pdf'}}]}], [{'type': 'header', 'parameters': [
                                  {'type': 'document', 'document': {
                                      'link': 'https://drive.google.com/uc?export=download&id=1GXQ43jilSDelRvy1kr3PNNpl1e21dRXm',
                                      'filename': 'Brochure.pdf'}}]}]], 'failure_cnt': 0, 'total': 2,
                              'Template 1': 'There are 2 recipients and 2 template bodies. Sending 2 messages to 2 recipients.'
                              }
        logs[0][1].pop("timestamp")
        logs[0][1].pop("recipient")
        logs[0][0].pop("recipient")
        assert logs[0][1] == {'reference_id': reference_id, 'log_type': 'send', 'bot': bot, 'status': 'Success',
                              'api_response': {
                'contacts': [{'input': '+55123456789', 'status': 'valid', 'wa_id': '55123456789'}]},
                              'template_params': [{'type': 'header', 'parameters': [
                {'type': 'document', 'document': {
                    'link': 'https://drive.google.com/uc?export=download&id=1GXQ43jilSDelRvy1kr3PNNpl1e21dRXm',
                    'filename': 'Brochure.pdf'}}]}]}
        logs[0][0].pop("timestamp")
        assert logs[0][0] == {'reference_id': reference_id, 'log_type': 'send', 'bot': bot, 'status': 'Success',
                              'api_response': {
                'contacts': [{'input': '+55123456789', 'status': 'valid', 'wa_id': '55123456789'}]},
                              'template_params': [{'type': 'header', 'parameters': [
                {'type': 'document', 'document': {
                    'link': 'https://drive.google.com/uc?export=download&id=1GXQ43jilSDelRvy1kr3PNNpl1e21dRXm',
                    'filename': 'Brochure.pdf'}}]}]}
        with pytest.raises(AppException, match="Notification settings not found!"):
            MessageBroadcastProcessor.get_settings(event_id, bot)

        assert mock_send.call_args[0][1] == '13b1e228_4a08_4d19_a0da_cdb80bc76380'
        assert mock_send.call_args[0][2] == 'brochure_pdf'
        assert mock_send.call_args[0][3] == '876543212345'
        assert mock_send.call_args[0][4] == 'hi'
        assert mock_send.call_args[0][5] == [{'type': 'header', 'parameters': [{'type': 'document', 'document': {
            'link': 'https://drive.google.com/uc?export=download&id=1GXQ43jilSDelRvy1kr3PNNpl1e21dRXm',
            'filename': 'Brochure.pdf'}}]}]

    @patch("kairon.chat.handlers.channels.clients.whatsapp.dialog360.BSP360Dialog.send_template_message", autospec=True)
    @patch("kairon.shared.data.processor.MongoProcessor.get_bot_settings")
    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    @patch("kairon.shared.utils.Utility.is_exist", autospec=True)
    def test_execute_message_broadcast_with_recipient_evaluation_failure(self, mock_is_exist, mock_channel_config,
                                                           mock_get_bot_settings, mock_send):
        bot = 'test_execute_dynamic_message_broadcast_recipient_evaluation_failure'
        user = 'test_user'
        config = {
            "name": "one_time_schedule",
            "connector_type": "whatsapp",
            "recipients_config": {
                "recipient_type": "dynamic",
                "recipients": "${contacts}"
            },
            "data_extraction_config": {
                "headers": {"api_key": "asdfghjkl", "access_key": "dsfghjkl"},
                "url": "http://kairon.local",
            },
            "template_config": [
                {
                    'language': 'hi',
                    "template_type": "static",
                    "template_id": "brochure_pdf",
                    "namespace": "13b1e228_4a08_4d19_a0da_cdb80bc76380",
                    "data": "[\n                {\n                    \"type\": \"header\",\n                    \"parameters\": [\n                        {\n                            \"type\": \"document\",\n                            \"document\": {\n                                \"link\": \"https://drive.google.com/uc?export=download&id=1GXQ43jilSDelRvy1kr3PNNpl1e21dRXm\",\n                                \"filename\": \"Brochure.pdf\"\n                            }\n                        }\n                    ]\n                }\n            ]"
                }
            ]
        }

        url = f"http://localhost:5001/api/events/execute/{EventClass.message_broadcast}?is_scheduled=False"
        responses.start()
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
            "POST", "http://localhost:8080/format",
            json={"data": "9876543210, 876543212345", "success": True}
        )

        mock_get_bot_settings.return_value = {"whatsapp": "360dialog", "notification_scheduling_limit": 4}
        mock_channel_config.return_value = {
            "config": {"access_token": "shjkjhrefdfghjkl", "from_phone_number_id": "918958030415"}}
        mock_send.return_value = {"contacts": [{"input": "+55123456789", "status": "valid", "wa_id": "55123456789"}]}

        event = MessageBroadcastEvent(bot, user)
        event.validate()
        event_id = event.enqueue(EventRequestType.trigger_async.value, config=config)
        event.execute(event_id)
        responses.reset()

        logs = MessageBroadcastProcessor.get_broadcast_logs(bot)
        assert len(logs[0]) == logs[1] == 1
        logs[0][0].pop("timestamp")
        reference_id = logs[0][0].pop("reference_id")
        assert reference_id
        logged_config = logs[0][0].pop("config")
        logged_config.pop("_id")
        logged_config.pop("status")
        logged_config.pop("timestamp")
        config['data_extraction_config']["method"] = "GET"
        config['data_extraction_config']["request_body"] = {}
        assert logged_config == config
        assert logs[0][0] == {'log_type': 'common', 'bot': bot, 'status': 'Fail', 'user': user,
                              'broadcast_id': event_id,
                              'data_extraction': {'url': 'http://kairon.local',
                                                  'headers': {'api_key': 'asdfghjkl', 'access_key': 'dsfghjkl'},
                                                  'method': 'GET',
                                                  'api_response': {'contacts': ['9876543210', '876543212345']}},
                              "exception": 'recipients evaluated to unexpected data type: 9876543210, 876543212345'
                              }

        with pytest.raises(AppException, match="Notification settings not found!"):
            MessageBroadcastProcessor.get_settings(event_id, bot)

    @patch("kairon.chat.handlers.channels.clients.whatsapp.dialog360.BSP360Dialog.send_template_message", autospec=True)
    @patch("kairon.shared.data.processor.MongoProcessor.get_bot_settings")
    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    @patch("kairon.shared.utils.Utility.is_exist", autospec=True)
    def test_execute_message_broadcast_with_data_extraction_failure(self, mock_is_exist, mock_channel_config,
                                                           mock_get_bot_settings, mock_send):
        bot = 'test_execute_dynamic_message_broadcast_data_extraction_failure'
        user = 'test_user'
        config = {
            "name": "one_time_schedule",
            "connector_type": "whatsapp",
            "recipients_config": {
                "recipient_type": "dynamic",
                "recipients": "${contacts}"
            },
            "data_extraction_config": {
                "headers": {"api_key": "asdfghjkl", "access_key": "dsfghjkl"},
                "url": "http://kairon.local",
            },
            "template_config": [
                {
                    'language': 'hi',
                    "template_type": "static",
                    "template_id": "brochure_pdf",
                    "namespace": "13b1e228_4a08_4d19_a0da_cdb80bc76380",
                    "data": "[\n                {\n                    \"type\": \"header\",\n                    \"parameters\": [\n                        {\n                            \"type\": \"document\",\n                            \"document\": {\n                                \"link\": \"https://drive.google.com/uc?export=download&id=1GXQ43jilSDelRvy1kr3PNNpl1e21dRXm\",\n                                \"filename\": \"Brochure.pdf\"\n                            }\n                        }\n                    ]\n                }\n            ]"
                }
            ]
        }

        url = f"http://localhost:5001/api/events/execute/{EventClass.message_broadcast}?is_scheduled=False"
        responses.start()
        responses.add(
            "POST", url,
            json={"message": "Event Triggered!", "success": True, "error_code": 0, "data": None}
        )
        responses.add(
            "POST", "http://localhost:8080/format",
            json={"data": "9876543210, 876543212345", "success": True}
        )

        mock_get_bot_settings.return_value = {"whatsapp": "360dialog", "notification_scheduling_limit": 4}
        mock_channel_config.return_value = {
            "config": {"access_token": "shjkjhrefdfghjkl", "from_phone_number_id": "918958030415"}}
        mock_send.return_value = {"contacts": [{"input": "+55123456789", "status": "valid", "wa_id": "55123456789"}]}

        event = MessageBroadcastEvent(bot, user)
        event.validate()
        event_id = event.enqueue(EventRequestType.trigger_async.value, config=config)
        event.execute(event_id)
        responses.reset()

        logs = MessageBroadcastProcessor.get_broadcast_logs(bot)
        assert len(logs[0]) == logs[1] == 1
        logs[0][0].pop("timestamp")
        reference_id = logs[0][0].pop("reference_id")
        assert reference_id
        logged_config = logs[0][0].pop("config")
        logged_config.pop("_id")
        logged_config.pop("status")
        logged_config.pop("timestamp")
        config['data_extraction_config']["method"] = "GET"
        config['data_extraction_config']["request_body"] = {}
        assert logged_config == config
        exception = logs[0][0].pop("exception")
        assert exception.startswith("Failed to connect to service: kairon.local")
        assert logs[0][0] == {'log_type': 'common', 'bot': bot, 'status': 'Fail', 'user': user, 'broadcast_id': event_id}

        with pytest.raises(AppException, match="Notification settings not found!"):
            MessageBroadcastProcessor.get_settings(event_id, bot)

    @patch("kairon.shared.data.processor.MongoProcessor.get_bot_settings")
    @patch("kairon.shared.utils.Utility.is_exist", autospec=True)
    def test_execute_message_broadcast_recipient_evaluation_failure(self, mock_is_exist, mock_get_bot_settings):
        bot = 'test_execute_message_broadcast_recipient_evaluation_failure'
        user = 'test_user'
        config = {
            "name": "one_time_schedule",
            "connector_type": "whatsapp",
            "recipients_config": {
                "recipient_type": "dynamic",
                "recipients": "${contacts}"
            },
            "template_config": [
                {
                    "template_type": "static",
                    "template_id": "brochure_pdf",
                    "namespace": "13b1e228_4a08_4d19_a0da_cdb80bc76380",
                    "data": "[\n                {\n                    \"type\": \"header\",\n                    \"parameters\": [\n                        {\n                            \"type\": \"document\",\n                            \"document\": {\n                                \"link\": \"https://drive.google.com/uc?export=download&id=1GXQ43jilSDelRvy1kr3PNNpl1e21dRXm\",\n                                \"filename\": \"Brochure.pdf\"\n                            }\n                        }\n                    ]\n                }\n            ]"
                }
            ]
        }

        url = f"http://localhost:5001/api/events/execute/{EventClass.message_broadcast}?is_scheduled=False"
        responses.start()
        responses.add(
            "POST", url,
            json={"message": "Event Triggered!", "success": True, "error_code": 0, "data": None}
        )
        responses.add(
            "POST", "http://localhost:8080/format",
            json={"data": "9876543210, 876543212345", "success": False}
        )

        mock_get_bot_settings.return_value = {"whatsapp": "360dialog", "notification_scheduling_limit": 4}

        event = MessageBroadcastEvent(bot, user)
        event.validate()
        event_id = event.enqueue(EventRequestType.trigger_async.value, config=config)
        event.execute(event_id)

        logs = MessageBroadcastProcessor.get_broadcast_logs(bot)
        assert len(logs[0]) == logs[1] == 1
        exception = logs[0][0].pop("exception")
        assert exception.startswith('Failed to evaluate dynamic recipients expression: ')
        responses.reset()

    @patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config")
    @patch("kairon.shared.data.processor.MongoProcessor.get_bot_settings")
    @patch("kairon.shared.utils.Utility.is_exist", autospec=True)
    def test_execute_message_broadcast_expression_evaluation_failure(self, mock_is_exist, mock_get_bot_settings, mock_channel_config):
        bot = 'test_execute_message_broadcast_expression_evaluation_failure'
        user = 'test_user'
        config = {
            "name": "one_time_schedule",
            "connector_type": "whatsapp",
            "recipients_config": {
                "recipient_type": "static",
                "recipients": "918958030541"
            },
            "template_config": [
                {
                    "template_type": "static",
                    "template_id": "brochure_pdf",
                    "namespace": "13b1e228_4a08_4d19_a0da_cdb80bc76380",
                    "data": "[{type: body, parameters: [{type: text, text: Udit}]}]"
                }
            ]
        }

        url = f"http://localhost:5001/api/events/execute/{EventClass.message_broadcast}?is_scheduled=False"
        responses.start()
        responses.add(
            "POST", url,
            json={"message": "Event Triggered!", "success": True, "error_code": 0, "data": None}
        )
        responses.add(
            "POST", "http://localhost:8080/format",
            json={"data": "9876543210, 876543212345", "success": False}
        )

        mock_get_bot_settings.return_value = {"whatsapp": "360dialog", "notification_scheduling_limit": 4}
        mock_channel_config.return_value = {
            "config": {"access_token": "shjkjhrefdfghjkl", "from_phone_number_id": "918958030415"}}

        event = MessageBroadcastEvent(bot, user)
        event.validate()
        event_id = event.enqueue(EventRequestType.trigger_async.value, config=config)
        event.execute(event_id)

        logs = MessageBroadcastProcessor.get_broadcast_logs(bot)
        assert len(logs[0]) == logs[1] == 1
        exception = logs[0][0].pop("exception")
        assert exception.startswith('Failed to evaluate static template expression: ')
        responses.reset()

    @patch("kairon.chat.handlers.channels.clients.whatsapp.dialog360.BSP360Dialog.send_template_message", autospec=True)
    @patch("kairon.shared.data.processor.MongoProcessor.get_bot_settings")
    @patch("kairon.shared.utils.Utility.is_exist", autospec=True)
    def test_execute_message_broadcast_with_channel_deleted(self, mock_is_exist, mock_get_bot_settings, mock_send):
        bot = 'test_execute_message_broadcast_with_channel_deleted'
        user = 'test_user'
        config = {
            "name": "one_time_schedule",
            "connector_type": "whatsapp",
            "recipients_config": {
                "recipient_type": "static",
                "recipients": "918958030541"
            },
            "template_config": [
                {
                    'language': 'hi',
                    "template_type": "static",
                    "template_id": "brochure_pdf",
                    "namespace": "13b1e228_4a08_4d19_a0da_cdb80bc76380",
                    "data": "[\n                {\n                    \"type\": \"header\",\n                    \"parameters\": [\n                        {\n                            \"type\": \"document\",\n                            \"document\": {\n                                \"link\": \"https://drive.google.com/uc?export=download&id=1GXQ43jilSDelRvy1kr3PNNpl1e21dRXm\",\n                                \"filename\": \"Brochure.pdf\"\n                            }\n                        }\n                    ]\n                }\n            ]"
                }
            ]
        }

        url = f"http://localhost:5001/api/events/execute/{EventClass.message_broadcast}?is_scheduled=False"
        responses.start()
        responses.add(
            "POST", url,
            json={"message": "Event Triggered!", "success": True, "error_code": 0, "data": None}
        )

        mock_get_bot_settings.return_value = {"whatsapp": "360dialog", "notification_scheduling_limit": 4}
        mock_send.return_value = {"contacts": [{"input": "+55123456789", "status": "valid", "wa_id": "55123456789"}]}

        event = MessageBroadcastEvent(bot, user)
        event.validate()

        with patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config") as mock_channel_config:
            mock_channel_config.return_value = {
                "config": {"access_token": "shjkjhrefdfghjkl", "from_phone_number_id": "918958030415"}}
            event_id = event.enqueue(EventRequestType.trigger_async.value, config=config)

        event.execute(event_id)
        responses.reset()

        logs = MessageBroadcastProcessor.get_broadcast_logs(bot)
        assert len(logs[0]) == logs[1] == 1
        logs[0][0].pop("timestamp")
        reference_id = logs[0][0].pop("reference_id")
        assert reference_id
        logged_config = logs[0][0].pop("config")
        logged_config.pop("_id")
        logged_config.pop("status")
        logged_config.pop("timestamp")
        assert logged_config == config
        exception = logs[0][0].pop("exception")
        assert exception.startswith("Whatsapp channel config not found!")
        assert logs[0][0] == {'log_type': 'common', 'bot': bot, 'status': 'Fail', 'user': user, 'broadcast_id': event_id,
                              'recipients': ['918958030541']}

        with pytest.raises(AppException, match="Notification settings not found!"):
            MessageBroadcastProcessor.get_settings(event_id, bot)

    @responses.activate
    def test_execute_message_broadcast_evaluate_template_parameters(self):
        bot = 'test_execute_message_broadcast_evaluate_template_parameters'
        user = 'test_user'
        config = {
            "name": "one_time_schedule",
            "connector_type": "whatsapp",
            "recipients_config": {
                "recipient_type": "static",
                "recipients": "918958030541,"
            },
            "template_config": [
                {
                    'language': 'hi',
                    "template_type": "dynamic",
                    "template_id": "brochure_pdf",
                    "namespace": "13b1e228_4a08_4d19_a0da_cdb80bc76380",
                    "data": "[{'body': '$responses.data'}]"
                }
            ]
        }

        url = f"http://localhost:5001/api/events/execute/{EventClass.message_broadcast}?is_scheduled=False"
        responses.add(
            "POST", url,
            json={"message": "Event Triggered!", "success": True, "error_code": 0, "data": None}
        )
        responses.add(
            "POST", "http://localhost:8080/format",
            json={"data": [[{'body': 'Udit Pandey'}]], "success": True}
        )
        event = MessageBroadcastEvent(bot, user)
        event.validate()
        with patch("kairon.shared.utils.Utility.is_exist", autospec=True):
            event_id = event.enqueue(EventRequestType.trigger_async.value, config=config)

        with patch("kairon.shared.chat.processor.ChatDataProcessor.get_channel_config") as mock_channel_config:
            mock_channel_config.return_value = {"config": {"access_token": "shjkjhrefdfghjkl", "from_phone_number_id": "918958030415"}}
            with patch("kairon.shared.data.processor.MongoProcessor.get_bot_settings") as mock_get_bot_settings:
                mock_get_bot_settings.return_value = {"whatsapp": "360dialog"}
                with patch("kairon.chat.handlers.channels.clients.whatsapp.dialog360.BSP360Dialog.send_template_message", autospec=True) as mock_send:
                    mock_send.return_value = {"contacts": [{"input": "+55123456789", "status": "valid", "wa_id": "55123456789"}]}

                    event.execute(event_id)

        logs = MessageBroadcastProcessor.get_broadcast_logs(bot)
        assert len(logs[0]) == logs[1] == 2
        logs[0][1].pop("timestamp")
        logs[0][1].pop("evaluation_log")
        reference_id = logs[0][1].pop("reference_id")
        logged_config = logs[0][1].pop("config")
        logged_config.pop("_id")
        logged_config.pop("status")
        logged_config.pop("timestamp")
        assert logged_config == config
        assert logs[0][1] == {'log_type': 'common', 'bot': bot, 'status': 'Completed',
                              'user': 'test_user', 'broadcast_id': event_id, 'recipients': ['918958030541', ''],
                              'template_params': [[{'body': 'Udit Pandey'}]], 'failure_cnt': 0, 'total': 2,
                              'Template 1': 'There are 2 recipients and 1 template bodies. Sending 1 messages to 1 recipients.'
                              }
        logs[0][0].pop("timestamp")
        assert logs[0][0] == {'reference_id': reference_id, 'log_type': 'send',
                              'bot': bot, 'status': 'Success', 'api_response': {
                'contacts': [{'input': '+55123456789', 'status': 'valid', 'wa_id': '55123456789'}]},
                              'recipient': '918958030541', 'template_params': [{'body': 'Udit Pandey'}]}

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
