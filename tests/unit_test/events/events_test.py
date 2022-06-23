import json
import os
import shutil
import tempfile
from datetime import datetime
import uuid
import pytest
import responses
from mongoengine import connect
from rasa.shared.constants import DEFAULT_DOMAIN_PATH, DEFAULT_DATA_PATH, DEFAULT_CONFIG_PATH
from rasa.shared.importers.rasa import RasaFileImporter

from kairon import Utility
from kairon.shared.data.constant import EVENT_STATUS, REQUIREMENTS
from kairon.shared.data.data_objects import Configs, BotSettings
from kairon.shared.data.history_log_processor import HistoryDeletionLogProcessor
from kairon.shared.importer.processor import DataImporterLogProcessor
from kairon.shared.data.processor import MongoProcessor
from kairon.events.events import EventsTrigger
from kairon.shared.test.processor import ModelTestingLogProcessor
from kairon.test.test_models import ModelTester


class TestEvents:

    @pytest.fixture(scope='class', autouse=True)
    def init(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))
        tmp_dir = tempfile.mkdtemp()
        pytest.tmp_dir = tmp_dir

        from rasa import train
        # model without entities
        train_result = train(
            domain='tests/testing_data/model_tester/domain.yml',
            config='tests/testing_data/model_tester/config.yml',
            training_files=['tests/testing_data/model_tester/nlu_with_entities/nlu.yml',
                            'tests/testing_data/model_tester/training_stories_success/stories.yml'],
            output='tests/testing_data/model_tester/models',
            core_additional_arguments={"augmentation_factor": 100},
            force_training=True
        )
        pytest.model_path = train_result.model
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

    @pytest.mark.asyncio
    async def test_trigger_data_importer_validate_only(self, monkeypatch):
        bot = 'test_events'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(uuid.uuid4()))
        shutil.copytree('tests/testing_data/validator/valid', test_data_path)

        def _path(*args, **kwargs):
            return test_data_path

        monkeypatch.setattr(Utility, "get_latest_file", _path)

        DataImporterLogProcessor.add_log(bot, user, files_received=REQUIREMENTS-{"http_actions"})
        await EventsTrigger.trigger_data_importer(bot, user, True, False)
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
        assert logs[0]['is_data_uploaded']
        assert logs[0]['start_timestamp']
        assert logs[0]['end_timestamp']
        assert logs[0]['status'] == 'Success'
        assert logs[0]['event_status'] == EVENT_STATUS.COMPLETED.value

    @pytest.mark.asyncio
    async def test_trigger_data_importer_validate_exception(self, monkeypatch):
        bot = 'test_events'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(uuid.uuid4()))
        os.mkdir(test_data_path)

        def _path(*args, **kwargs):
            return test_data_path

        monkeypatch.setattr(Utility, "get_latest_file", _path)

        DataImporterLogProcessor.add_log(bot, user, files_received=REQUIREMENTS - {"domain", "http_actions"})
        await EventsTrigger.trigger_data_importer(bot, user, False, False)
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
        assert logs[0]['is_data_uploaded']
        assert logs[0]['start_timestamp']
        assert logs[0]['end_timestamp']
        assert logs[0]['status'] == 'Failure'
        assert logs[0]['event_status'] == EVENT_STATUS.FAIL.value

    @pytest.mark.asyncio
    async def test_trigger_data_importer_validate_invalid_yaml(self, monkeypatch):
        bot = 'test_events'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(uuid.uuid4()))
        shutil.copytree('tests/testing_data/validator/invalid_yaml', test_data_path)

        def _path(*args, **kwargs):
            return test_data_path

        monkeypatch.setattr(Utility, "get_latest_file", _path)

        DataImporterLogProcessor.add_log(bot, user, files_received=REQUIREMENTS - {"domain", "http_actions"})
        await EventsTrigger.trigger_data_importer(bot, user, True, False)
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
        assert logs[0]['is_data_uploaded']
        assert logs[0]['start_timestamp']
        assert logs[0]['end_timestamp']
        assert logs[0]['status'] == 'Failure'
        assert logs[0]['event_status'] == EVENT_STATUS.FAIL.value

    @pytest.mark.asyncio
    async def test_trigger_data_importer_validate_invalid_domain(self, monkeypatch):
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
        await EventsTrigger.trigger_data_importer(bot, user, True, False)
        logs = list(DataImporterLogProcessor.get_logs(bot))
        assert logs[0].get('exception') == ('Failed to load domain.yml. Error: \'Duplicate entities in domain. These '
                                            'entities occur more than once in the domain: \'location\'.\'')
        assert logs[0]['is_data_uploaded']
        assert logs[0]['start_timestamp']
        assert logs[0]['end_timestamp']
        assert logs[0]['status'] == 'Failure'
        assert logs[0]['event_status'] == EVENT_STATUS.FAIL.value

    @pytest.mark.asyncio
    async def test_trigger_data_importer_validate_file_with_errors(self, monkeypatch):
        bot = 'test_events'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(uuid.uuid4()))
        shutil.copytree('tests/testing_data/validator/intent_name_mismatch', test_data_path)

        def _path(*args, **kwargs):
            return test_data_path

        monkeypatch.setattr(Utility, "get_latest_file", _path)

        DataImporterLogProcessor.add_log(bot, user, files_received=REQUIREMENTS - {"http_actions"})
        await EventsTrigger.trigger_data_importer(bot, user, True, False)
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
        assert logs[0]['is_data_uploaded']
        assert logs[0]['start_timestamp']
        assert logs[0]['end_timestamp']
        assert logs[0]['status'] == 'Failure'
        assert logs[0]['event_status'] == EVENT_STATUS.COMPLETED.value

    @pytest.mark.asyncio
    async def test_trigger_data_importer_validate_and_save_overwrite(self, monkeypatch):
        bot = 'test_events'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(uuid.uuid4()))
        shutil.copytree('tests/testing_data/validator/valid', test_data_path)

        def _path(*args, **kwargs):
            return test_data_path

        monkeypatch.setattr(Utility, "get_latest_file", _path)

        DataImporterLogProcessor.add_log(bot, user, files_received=REQUIREMENTS - {"http_actions"})
        await EventsTrigger.trigger_data_importer(bot, user, True, True)
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
        assert logs[0]['is_data_uploaded']
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

    @pytest.mark.asyncio
    async def test_trigger_data_importer_validate_and_save_append(self, monkeypatch):
        bot = 'test_events'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(uuid.uuid4()))
        shutil.copytree('tests/testing_data/validator/append', test_data_path)

        def _path(*args, **kwargs):
            return test_data_path

        monkeypatch.setattr(Utility, "get_latest_file", _path)

        DataImporterLogProcessor.add_log(bot, user, files_received=REQUIREMENTS - {"http_actions", "rules"})
        await EventsTrigger.trigger_data_importer(bot, user, True, False)
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
        assert logs[0]['is_data_uploaded']
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

    @pytest.mark.asyncio
    async def test_trigger_data_importer_validate_and_save_overwrite_same_user(self, monkeypatch):
        bot = 'test_events'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(uuid.uuid4()))
        shutil.copytree('tests/testing_data/validator/valid', test_data_path)

        def _path(*args, **kwargs):
            return test_data_path

        monkeypatch.setattr(Utility, "get_latest_file", _path)

        DataImporterLogProcessor.add_log(bot, user, files_received=REQUIREMENTS - {"http_actions"})
        await EventsTrigger.trigger_data_importer(bot, user, True, True)
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
        assert logs[0]['is_data_uploaded']
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

    @pytest.mark.asyncio
    async def test_trigger_data_importer_validate_event(self, monkeypatch):
        bot = 'test_events_bot'
        user = 'test_user'
        event_url = "http://url.event"
        monkeypatch.setitem(Utility.environment['model']['data_importer'], "event_url", event_url)

        responses.add("POST",
                      event_url,
                      json={"message": "Event triggered successfully!"},
                      status=200,
                      match=[
                          responses.json_params_matcher(
                              [{'name': 'BOT', 'value': bot}, {'name': 'USER', 'value': user},
                               {'name': 'IMPORT_DATA', 'value': '--import-data'},
                               {'name': 'OVERWRITE', 'value': ''}])],
                      )
        responses.start()
        await EventsTrigger.trigger_data_importer(bot, user, True, False)
        responses.stop()

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
        assert logs[0]['is_data_uploaded']
        assert logs[0]['start_timestamp']
        assert not logs[0].get('end_timestamp')
        assert not logs[0].get('status')
        assert logs[0]['event_status'] == EVENT_STATUS.TASKSPAWNED.value

    @pytest.mark.asyncio
    async def test_trigger_data_importer_validate_and_save_event_overwrite(self, monkeypatch):
        bot = 'test_events_bot_1'
        user = 'test_user'
        event_url = "http://url.event2"
        monkeypatch.setitem(Utility.environment['model']['data_importer'], "event_url", event_url)

        responses.add("POST",
                      event_url,
                      json={"message": "Event triggered successfully!"},
                      status=200,
                      match=[
                          responses.json_params_matcher(
                              [{'name': 'BOT', 'value': bot}, {'name': 'USER', 'value': user},
                               {'name': 'IMPORT_DATA', 'value': '--import-data'},
                               {'name': 'OVERWRITE', 'value': '--overwrite'}])],
                      )
        responses.start()
        await EventsTrigger.trigger_data_importer(bot, user, True, True)
        responses.stop()
        request = json.loads(responses.calls[1].request.body)
        assert request == [{'name': 'BOT', 'value': bot}, {'name': 'USER', 'value': user},
                               {'name': 'IMPORT_DATA', 'value': '--import-data'},
                               {'name': 'OVERWRITE', 'value': '--overwrite'}]

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
        assert logs[0]['is_data_uploaded']
        assert logs[0]['start_timestamp']
        assert not logs[0].get('end_timestamp')
        assert not logs[0].get('status')
        assert logs[0]['event_status'] == EVENT_STATUS.TASKSPAWNED.value

    @pytest.mark.asyncio
    async def test_trigger_data_importer_validate_only_event(self, monkeypatch):
        bot = 'test_events_bot_1'
        user = 'test_user'
        event_url = "http://url.event3"
        monkeypatch.setitem(Utility.environment['model']['data_importer'], "event_url", event_url)

        responses.add("POST",
                      event_url,
                      json={"message": "Event triggered successfully!"},
                      status=200,
                      match=[
                          responses.json_params_matcher(
                              [{'name': 'BOT', 'value': bot}, {'name': 'USER', 'value': user},
                               {'name': 'IMPORT_DATA', 'value': ''},
                               {'name': 'OVERWRITE', 'value': ''}])],
                      )
        responses.start()
        await EventsTrigger.trigger_data_importer(bot, user, False, False)
        responses.stop()

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
        assert logs[0]['is_data_uploaded']
        assert logs[0]['start_timestamp']
        assert not logs[0].get('end_timestamp')
        assert not logs[0].get('status')
        assert logs[0]['event_status'] == EVENT_STATUS.TASKSPAWNED.value

    @pytest.mark.asyncio
    async def test_trigger_data_importer_event_connection_error(self, monkeypatch):
        bot = 'test_events_bot_1'
        user = 'test_user'
        event_url = "http://url.event4"
        monkeypatch.setitem(Utility.environment['model']['data_importer'], "event_url", event_url)

        await EventsTrigger.trigger_data_importer(bot, user, False, False)

        logs = list(DataImporterLogProcessor.get_logs(bot))
        assert len(logs) == 1
        assert not logs[0].get('intents').get('data')
        assert not logs[0].get('stories').get('data')
        assert not logs[0].get('utterances').get('data')
        assert not [action.get('data') for action in logs[0].get('actions') if action.get('type') == 'http_actions']
        assert not logs[0].get('training_examples').get('data')
        assert not logs[0].get('domain').get('data')
        assert not logs[0].get('config').get('data')
        assert logs[0].get('exception').__contains__('Failed to trigger the event.')
        assert logs[0]['is_data_uploaded']
        assert logs[0]['start_timestamp']
        assert logs[0]['end_timestamp']
        assert logs[0]['status'] == 'Failure'
        assert logs[0]['event_status'] == EVENT_STATUS.FAIL.value

    @pytest.mark.asyncio
    async def test_trigger_data_importer_nlu_only(self, monkeypatch, get_training_data):
        bot = 'test_trigger_data_importer'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(uuid.uuid4()))
        nlu_path = os.path.join(test_data_path, 'data')
        Utility.make_dirs(nlu_path)
        shutil.copy2('tests/testing_data/validator/valid/data/nlu.yml', nlu_path)
        nlu, story_graph, domain, config, http_actions = await get_training_data('tests/testing_data/validator/valid')
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
        await EventsTrigger.trigger_data_importer(bot, user, True, False)
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
        assert logs[0]['is_data_uploaded']
        assert logs[0]['start_timestamp']
        assert logs[0]['end_timestamp']
        assert logs[0]['status'] == 'Success'
        assert logs[0]['event_status'] == EVENT_STATUS.COMPLETED.value

        assert len(mongo_processor.fetch_stories(bot)) == 2
        assert len(list(mongo_processor.fetch_training_examples(bot))) == 7
        assert len(list(mongo_processor.fetch_responses(bot))) == 3
        assert len(mongo_processor.fetch_actions(bot)) == 2
        assert len(mongo_processor.fetch_rule_block_names(bot)) == 3

    @pytest.mark.asyncio
    async def test_trigger_data_importer_stories_only(self, monkeypatch, get_training_data):
        bot = 'test_trigger_data_importer_stories_only'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(uuid.uuid4()))
        data_path = os.path.join(test_data_path, 'data')
        Utility.make_dirs(data_path)
        shutil.copy2('tests/testing_data/validator/valid/data/stories.yml', data_path)
        nlu, story_graph, domain, config, http_actions = await get_training_data('tests/testing_data/validator/valid')
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
        await EventsTrigger.trigger_data_importer(bot, user, True, False)
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
        assert logs[0]['is_data_uploaded']
        assert logs[0]['start_timestamp']
        assert logs[0]['end_timestamp']
        assert logs[0]['status'] == 'Success'
        assert logs[0]['event_status'] == EVENT_STATUS.COMPLETED.value

        assert len(mongo_processor.fetch_stories(bot)) == 2
        assert len(list(mongo_processor.fetch_training_examples(bot))) == 7
        assert len(list(mongo_processor.fetch_responses(bot))) == 3
        assert len(mongo_processor.fetch_actions(bot)) == 2
        assert len(mongo_processor.fetch_rule_block_names(bot)) == 3

    @pytest.mark.asyncio
    async def test_trigger_data_importer_rules_only(self, monkeypatch, get_training_data):
        bot = 'test_trigger_data_importer_rules_only'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(uuid.uuid4()))
        data_path = os.path.join(test_data_path, 'data')
        Utility.make_dirs(data_path)
        shutil.copy2('tests/testing_data/validator/valid/data/rules.yml', data_path)
        nlu, story_graph, domain, config, http_actions = await get_training_data('tests/testing_data/validator/valid')
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
        await EventsTrigger.trigger_data_importer(bot, user, True, False)
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
        assert logs[0]['is_data_uploaded']
        assert logs[0]['start_timestamp']
        assert logs[0]['end_timestamp']
        assert logs[0]['status'] == 'Success'
        assert logs[0]['event_status'] == EVENT_STATUS.COMPLETED.value

        assert len(mongo_processor.fetch_stories(bot)) == 2
        assert len(list(mongo_processor.fetch_training_examples(bot))) == 7
        assert len(list(mongo_processor.fetch_responses(bot))) == 3
        assert len(mongo_processor.fetch_actions(bot)) == 2
        assert len(mongo_processor.fetch_rule_block_names(bot)) == 3

    @pytest.mark.asyncio
    async def test_trigger_data_importer_domain_only(self, monkeypatch, get_training_data):
        bot = 'test_trigger_data_importer_domain_only'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(uuid.uuid4()))
        Utility.make_dirs(test_data_path)
        shutil.copy2('tests/testing_data/validator/valid/domain.yml', test_data_path)
        nlu, story_graph, domain, config, http_actions = await get_training_data('tests/testing_data/validator/valid')
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
        await EventsTrigger.trigger_data_importer(bot, user, True, False)
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
        assert logs[0]['is_data_uploaded']
        assert logs[0]['start_timestamp']
        assert logs[0]['end_timestamp']
        assert logs[0]['status'] == 'Success'
        assert logs[0]['event_status'] == EVENT_STATUS.COMPLETED.value

        assert len(mongo_processor.fetch_stories(bot)) == 2
        assert len(list(mongo_processor.fetch_training_examples(bot))) == 7
        assert len(list(mongo_processor.fetch_responses(bot))) == 3
        assert len(mongo_processor.fetch_actions(bot)) == 2
        assert len(mongo_processor.fetch_rule_block_names(bot)) == 3

    @pytest.mark.asyncio
    async def test_trigger_data_importer_validate_existing_data(self, monkeypatch, get_training_data):
        bot = 'test_trigger_data_importer_domain_only'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(uuid.uuid4()))
        Utility.make_dirs(test_data_path)

        def _path(*args, **kwargs):
            return test_data_path

        monkeypatch.setattr(Utility, "get_latest_file", _path)

        DataImporterLogProcessor.add_log(bot, user)
        await EventsTrigger.trigger_data_importer(bot, user, True, False)
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
        assert logs[0]['is_data_uploaded']
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

    @pytest.mark.asyncio
    async def test_trigger_data_importer_import_with_utterance_issues(self, monkeypatch):
        bot = 'test_trigger_data_importer_import_with_utterance_issues'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(uuid.uuid4()))
        shutil.copytree('tests/testing_data/validator/orphan_utterances', test_data_path)

        def _path(*args, **kwargs):
            return test_data_path

        monkeypatch.setattr(Utility, "get_latest_file", _path)
        BotSettings(ignore_utterances=True, bot=bot, user=user).save()

        DataImporterLogProcessor.add_log(bot, user, files_received=['nlu', 'stories', 'domain', 'config'])
        await EventsTrigger.trigger_data_importer(bot, user, True, True)
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
        assert logs[0]['is_data_uploaded']
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

    @pytest.mark.asyncio
    async def test_trigger_data_importer_import_with_intent_issues(self, monkeypatch):
        bot = 'test_trigger_data_importer_import_with_intent_issues'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(uuid.uuid4()))
        shutil.copytree('tests/testing_data/validator/intent_name_mismatch', test_data_path)

        def _path(*args, **kwargs):
            return test_data_path

        monkeypatch.setattr(Utility, "get_latest_file", _path)
        BotSettings(ignore_utterances=True, bot=bot, user=user).save()

        DataImporterLogProcessor.add_log(bot, user, files_received=['nlu', 'stories', 'domain', 'config'])
        await EventsTrigger.trigger_data_importer(bot, user, True, True)
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
        assert logs[0]['is_data_uploaded']
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

    @pytest.mark.asyncio
    async def test_trigger_data_importer_forced_import(self, monkeypatch):
        bot = 'forced_import'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(uuid.uuid4()))
        shutil.copytree('tests/testing_data/validator/orphan_utterances', test_data_path)

        def _path(*args, **kwargs):
            return test_data_path

        monkeypatch.setattr(Utility, "get_latest_file", _path)
        BotSettings(force_import=True, bot=bot, user=user).save()

        DataImporterLogProcessor.add_log(bot, user, files_received=['nlu', 'stories', 'domain', 'config'])
        await EventsTrigger.trigger_data_importer(bot, user, True, True)
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
        assert logs[0]['is_data_uploaded']
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

    def test_trigger_model_testing_event_run_tests_on_model_no_model_found(self):
        bot = 'test_events_bot'
        user = 'test_user'
        EventsTrigger.trigger_model_testing(bot, user, False)
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
        async def _read_and_get_data(config_path: str, domain_path: str, nlu_path: str, stories_path: str, bot: str, user: str):
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
            processor.save_training_data(bot, user, config, domain, story_graph, nlu, overwrite=True)

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

    @pytest.mark.asyncio
    async def test_trigger_model_testing_event_run_tests_on_model(self, load_data, create_model, monkeypatch):
        import rasa.utils.common

        bot = 'test_events_bot'
        user = 'test_user'
        config_path = 'tests/testing_data/model_tester/config.yml'
        domain_path = 'tests/testing_data/model_tester/domain.yml'
        nlu_path = 'tests/testing_data/model_tester/nlu_success/nlu.yml'
        stories_path = 'tests/testing_data/model_tester/training_stories_success/stories.yml'
        await load_data(config_path, domain_path, nlu_path, stories_path, bot, user)
        create_model(pytest.model_path, bot)

        def _mock_stories_output(*args, **kwargs):
            return {
                "precision": 0.91,
                "f1": 0.98,
                "accuracy": 0.99,
                "failed_stories": [],
            }

        monkeypatch.setattr(rasa.utils.common, 'run_in_loop', _mock_stories_output)
        responses.reset()
        responses.stop()
        EventsTrigger.trigger_model_testing(bot, user, False)
        logs = list(ModelTestingLogProcessor.get_logs(bot))
        assert len(logs) == 2
        assert not logs[0].get('exception')
        assert logs[0]['start_timestamp']
        assert logs[0].get('data')
        assert logs[0].get('end_timestamp')
        assert not Utility.check_empty_string(logs[0].get('status'))
        assert logs[0]['event_status'] == EVENT_STATUS.COMPLETED.value
        assert not os.path.exists(os.path.join('./testing_data', bot))

    def test_trigger_model_testing_event_connection_error(self, monkeypatch):
        bot = 'test_events_bot'
        user = 'test_user'
        event_url = "http://url.event"
        monkeypatch.setitem(Utility.environment['model']['test'], "event_url", event_url)
        EventsTrigger.trigger_model_testing(bot, user, True)
        logs = list(ModelTestingLogProcessor.get_logs(bot))
        assert len(logs) == 3
        assert logs[0].get('exception').__contains__('Failed to trigger the event. ')
        assert logs[0]['start_timestamp']
        assert not logs[0].get('data')
        assert logs[0].get('end_timestamp')
        assert not logs[0].get('status')
        assert logs[0]['event_status'] == EVENT_STATUS.FAIL.value
        assert not os.path.exists(os.path.join('./testing_data', bot))

    @pytest.mark.asyncio
    async def test_trigger_model_testing(self, load_data, create_model, monkeypatch):
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
        EventsTrigger.trigger_model_testing(bot, user)
        config_path = 'tests/testing_data/model_tester/config.yml'
        domain_path = 'tests/testing_data/model_tester/domain.yml'
        nlu_path = 'tests/testing_data/model_tester/nlu_success/nlu.yml'
        stories_path = 'tests/testing_data/model_tester/test_stories_success/test_stories.yml'
        await load_data(config_path, domain_path, nlu_path, stories_path, bot, user)
        create_model(pytest.model_path, bot)

        logs = list(ModelTestingLogProcessor.get_logs(bot))
        assert len(logs) == 4
        assert not logs[0].get('exception')
        assert logs[0]['start_timestamp']
        assert logs[0].get('end_timestamp')
        assert logs[0].get('status')
        assert logs[0].get('data')
        assert logs[0]['event_status'] == EVENT_STATUS.COMPLETED.value
        assert not os.path.exists(os.path.join('./testing_data', bot))

    def test_trigger_model_testing_event(self, monkeypatch):
        bot = 'test_events_bot'
        user = 'test_user'
        event_url = "http://url.event"
        monkeypatch.setitem(Utility.environment['model']['test'], "event_url", event_url)
        responses.add("POST",
                      event_url,
                      json={"message": "Event triggered successfully!"},
                      status=200,
                      match=[
                          responses.json_params_matcher(
                              [{'name': 'BOT', 'value': bot}, {'name': 'USER', 'value': user}])],
                      )
        responses.start()
        EventsTrigger.trigger_model_testing(bot, user)
        responses.stop()

        logs = list(ModelTestingLogProcessor.get_logs(bot))
        assert len(logs) == 5
        assert not logs[0].get('exception')
        assert logs[0]['start_timestamp']
        assert not logs[0].get('end_timestamp')
        assert not logs[0].get('status')
        assert logs[0]['event_status'] == EVENT_STATUS.TASKSPAWNED.value
        assert not os.path.exists(os.path.join('./testing_data', bot))

    def test_trigger_history_deletion_for_bot(self, monkeypatch):
        bot = 'test_events_bot'
        user = 'test_user'
        month = 1
        sender_id = None
        event_url = "http://url.event"
        monkeypatch.setitem(Utility.environment['history_server']['deletion'], "event_url", event_url)
        responses.add("POST",
                      event_url,
                      json={"message": "Event triggered successfully!"},
                      status=200,
                      match=[
                          responses.json_params_matcher(
                              [{'name': 'BOT', 'value': bot}, {'name': 'USER', 'value': user},
                               {'name': 'MONTH', 'value': month}, {'name': 'SENDER_ID', 'value': sender_id}])],
                      )
        responses.start()
        EventsTrigger.trigger_history_deletion(bot, user, month)
        responses.stop()

        logs = list(HistoryDeletionLogProcessor.get_logs(bot))
        assert len(logs) == 1
        assert not logs[0].get('exception')
        assert logs[0]['start_timestamp']
        assert not logs[0].get('end_timestamp')
        assert logs[0]['status'] == EVENT_STATUS.TASKSPAWNED.value

