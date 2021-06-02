import json
import os
import shutil
import tempfile
from datetime import datetime

import pytest
import responses
from mongoengine import connect

from kairon import Utility
from kairon.data_processor.constant import EVENT_STATUS
from kairon.importer.processor import DataImporterLogProcessor
from kairon.data_processor.processor import MongoProcessor
from kairon.events.events import EventsTrigger


class TestEvents:

    @pytest.fixture(scope='session', autouse=True)
    def init(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_evironment()
        connect(host=Utility.environment["database"]['url'])
        tmp_dir = tempfile.mkdtemp()
        pytest.tmp_dir = tmp_dir
        yield None
        shutil.rmtree(tmp_dir)

    @pytest.mark.asyncio
    async def test_trigger_data_importer_validate_only(self, monkeypatch):
        bot = 'test_events'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(datetime.utcnow()))
        shutil.copytree('tests/testing_data/validator/valid', test_data_path)

        def _path(*args, **kwargs):
            return test_data_path

        monkeypatch.setattr(Utility, "get_latest_file", _path)

        await EventsTrigger.trigger_data_importer(bot, user, True, False)
        logs = list(DataImporterLogProcessor.get_logs(bot))
        assert len(logs) == 1
        assert not logs[0].get('intents')
        assert not logs[0].get('stories')
        assert not logs[0].get('utterances')
        assert not logs[0].get('http_actions')
        assert not logs[0].get('training_examples')
        assert not logs[0].get('domain')
        assert not logs[0].get('config')
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
        test_data_path = os.path.join(pytest.tmp_dir, str(datetime.utcnow()))
        os.mkdir(test_data_path)

        def _path(*args, **kwargs):
            return test_data_path

        monkeypatch.setattr(Utility, "get_latest_file", _path)

        await EventsTrigger.trigger_data_importer(bot, user, False, False)
        logs = list(DataImporterLogProcessor.get_logs(bot))
        assert len(logs) == 2
        assert not logs[0].get('intents')
        assert not logs[0].get('stories')
        assert not logs[0].get('utterances')
        assert not logs[0].get('http_actions')
        assert not logs[0].get('training_examples')
        assert not logs[0].get('domain')
        assert not logs[0].get('config')
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
        test_data_path = os.path.join(pytest.tmp_dir, str(datetime.utcnow()))
        shutil.copytree('tests/testing_data/validator/invalid_yaml', test_data_path)

        def _path(*args, **kwargs):
            return test_data_path

        monkeypatch.setattr(Utility, "get_latest_file", _path)

        await EventsTrigger.trigger_data_importer(bot, user, True, False)
        logs = list(DataImporterLogProcessor.get_logs(bot))
        assert len(logs) == 3
        assert not logs[0].get('intents')
        assert not logs[0].get('stories')
        assert not logs[0].get('utterances')
        assert not logs[0].get('http_actions')
        assert not logs[0].get('training_examples')
        assert not logs[0].get('domain')
        assert not logs[0].get('config')
        assert logs[0].get('exception').__contains__('Failed to read config.yml')
        assert logs[0]['is_data_uploaded']
        assert logs[0]['start_timestamp']
        assert logs[0]['end_timestamp']
        assert logs[0]['status'] == 'Failure'
        assert logs[0]['event_status'] == EVENT_STATUS.FAIL.value

    @pytest.mark.asyncio
    async def test_trigger_data_importer_validate_file_with_errors(self, monkeypatch):
        bot = 'test_events'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(datetime.utcnow()))
        shutil.copytree('tests/testing_data/validator/intent_name_mismatch', test_data_path)

        def _path(*args, **kwargs):
            return test_data_path

        monkeypatch.setattr(Utility, "get_latest_file", _path)

        await EventsTrigger.trigger_data_importer(bot, user, True, False)
        logs = list(DataImporterLogProcessor.get_logs(bot))
        assert len(logs) == 4
        assert logs[0].get('intents')
        assert not logs[0].get('stories')
        assert not logs[0].get('utterances')
        assert not logs[0].get('http_actions')
        assert not logs[0].get('training_examples')
        assert not logs[0].get('domain')
        assert not logs[0].get('config')
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
        test_data_path = os.path.join(pytest.tmp_dir, str(datetime.utcnow()))
        shutil.copytree('tests/testing_data/validator/valid', test_data_path)

        def _path(*args, **kwargs):
            return test_data_path

        monkeypatch.setattr(Utility, "get_latest_file", _path)

        await EventsTrigger.trigger_data_importer(bot, user, True, True)
        logs = list(DataImporterLogProcessor.get_logs(bot))
        assert len(logs) == 5
        assert not logs[0].get('intents')
        assert not logs[0].get('stories')
        assert not logs[0].get('utterances')
        assert not logs[0].get('http_actions')
        assert not logs[0].get('training_examples')
        assert not logs[0].get('domain')
        assert not logs[0].get('config')
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
        assert len(list(processor.fetch_responses(bot))) == 2
        assert len(processor.fetch_actions(bot)) == 2
        assert len(processor.fetch_rule_block_names(bot)) == 3

    @pytest.mark.asyncio
    async def test_trigger_data_importer_validate_and_save_append(self, monkeypatch):
        bot = 'test_events'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(datetime.utcnow()))
        shutil.copytree('tests/testing_data/validator/append', test_data_path)

        def _path(*args, **kwargs):
            return test_data_path

        monkeypatch.setattr(Utility, "get_latest_file", _path)

        await EventsTrigger.trigger_data_importer(bot, user, True, False)
        logs = list(DataImporterLogProcessor.get_logs(bot))
        assert len(logs) == 6
        assert not logs[0].get('intents')
        assert not logs[0].get('stories')
        assert not logs[0].get('utterances')
        assert not logs[0].get('http_actions')
        assert not logs[0].get('training_examples')
        assert not logs[0].get('domain')
        assert not logs[0].get('config')
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
        assert len(list(processor.fetch_responses(bot))) == 4
        assert len(processor.fetch_actions(bot)) == 4
        assert len(processor.fetch_rule_block_names(bot)) == 3

    @pytest.mark.asyncio
    async def test_trigger_data_importer_validate_and_save_overwrite_same_user(self, monkeypatch):
        bot = 'test_events'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(datetime.utcnow()))
        shutil.copytree('tests/testing_data/validator/valid', test_data_path)

        def _path(*args, **kwargs):
            return test_data_path

        monkeypatch.setattr(Utility, "get_latest_file", _path)

        await EventsTrigger.trigger_data_importer(bot, user, True, True)
        logs = list(DataImporterLogProcessor.get_logs(bot))
        assert len(logs) == 7
        assert not logs[0].get('intents')
        assert not logs[0].get('stories')
        assert not logs[0].get('utterances')
        assert not logs[0].get('http_actions')
        assert not logs[0].get('training_examples')
        assert not logs[0].get('domain')
        assert not logs[0].get('config')
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
        assert len(list(processor.fetch_responses(bot))) == 2
        assert len(processor.fetch_actions(bot)) == 2
        assert len(processor.fetch_rule_block_names(bot)) == 3

    @pytest.mark.asyncio
    async def test_trigger_data_importer_validate_event(self, monkeypatch):
        bot = 'test_events_bot'
        user = 'test_user'
        event_url = "http://url.event"
        monkeypatch.setitem(Utility.environment['model']['data_importer'], "event_url", event_url)

        responses.add("POST",
                      event_url,
                      json={"message": "Event triggered successfully!"},
                      status=200)
        responses.start()
        await EventsTrigger.trigger_data_importer(bot, user, True, False)
        responses.stop()
        request = json.loads(responses.calls[0].request.body)
        assert request['BOT'] == bot
        assert request['USER'] == user
        assert request['IMPORT_DATA'] == '--import-data'
        assert request['OVERWRITE'] == ''

        logs = list(DataImporterLogProcessor.get_logs(bot))
        assert len(logs) == 1
        assert not logs[0].get('intents')
        assert not logs[0].get('stories')
        assert not logs[0].get('utterances')
        assert not logs[0].get('http_actions')
        assert not logs[0].get('training_examples')
        assert not logs[0].get('domain')
        assert not logs[0].get('config')
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
                      status=200)
        responses.start()
        await EventsTrigger.trigger_data_importer(bot, user, True, True)
        responses.stop()
        request = json.loads(responses.calls[1].request.body)

        assert request['BOT'] == bot
        assert request['USER'] == user
        assert request['IMPORT_DATA'] == '--import-data'
        assert request['OVERWRITE'] == '--overwrite'

        logs = list(DataImporterLogProcessor.get_logs(bot))
        assert len(logs) == 1
        assert not logs[0].get('intents')
        assert not logs[0].get('stories')
        assert not logs[0].get('utterances')
        assert not logs[0].get('http_actions')
        assert not logs[0].get('training_examples')
        assert not logs[0].get('domain')
        assert not logs[0].get('config')
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
                      status=200)
        responses.start()
        await EventsTrigger.trigger_data_importer(bot, user, False, False)
        responses.stop()
        request = json.loads(responses.calls[2].request.body)

        assert request['BOT'] == bot
        assert request['USER'] == user
        assert request['IMPORT_DATA'] == ''
        assert request['OVERWRITE'] == ''

        logs = list(DataImporterLogProcessor.get_logs(bot))
        assert len(logs) == 1
        assert not logs[0].get('intents')
        assert not logs[0].get('stories')
        assert not logs[0].get('utterances')
        assert not logs[0].get('http_actions')
        assert not logs[0].get('training_examples')
        assert not logs[0].get('domain')
        assert not logs[0].get('config')
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
        assert not logs[0].get('intents')
        assert not logs[0].get('stories')
        assert not logs[0].get('utterances')
        assert not logs[0].get('http_actions')
        assert not logs[0].get('training_examples')
        assert not logs[0].get('domain')
        assert not logs[0].get('config')
        assert logs[0].get('exception') == 'Failed to trigger the event.'
        assert logs[0]['is_data_uploaded']
        assert logs[0]['start_timestamp']
        assert logs[0]['end_timestamp']
        assert logs[0]['status'] == 'Failure'
        assert logs[0]['event_status'] == EVENT_STATUS.FAIL.value
