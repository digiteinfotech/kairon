import os
import shutil
import tempfile
import uuid

import pytest
from mongoengine import connect

from kairon.exceptions import AppException
from kairon.importer.data_importer import DataImporter
from kairon.shared.data.constant import REQUIREMENTS
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.utils import Utility


def pytest_namespace():
    return {'tmp_dir': None}


class TestDataImporter:

    @pytest.fixture(scope='session', autouse=True)
    def init(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))
        tmp_dir = tempfile.mkdtemp()
        pytest.tmp_dir = tmp_dir
        yield None
        shutil.rmtree(tmp_dir)

    @pytest.mark.asyncio
    async def test_validate_success(self):
        path = 'tests/testing_data/validator/valid'
        importer = DataImporter(path, 'test_data_import', 'test', REQUIREMENTS.copy(), False, False)
        summary, component_count = await importer.validate()
        assert not summary.get('intents')
        assert not summary.get('stories')
        assert not summary.get('utterances')
        assert not summary.get('http_actions')
        assert not summary.get('training_examples')
        assert not summary.get('domain')
        assert not summary.get('config')
        assert not summary.get('exception')

    @pytest.mark.asyncio
    async def test_validate_invalid_domain(self):
        path = 'tests/testing_data/validator/invalid_domain'
        importer = DataImporter(path, 'test_data_import', 'test', REQUIREMENTS.copy(), False, False)
        with pytest.raises(AppException, match='Failed to load domain.yml. Error: \'Duplicate entities in domain. '
                                               'These entities occur more than once in the domain: \'location\'.\''):
            await importer.validate()

    @pytest.mark.asyncio
    async def test_validate_all_including_http_actions(self):
        path = 'tests/testing_data/validator/valid'
        http_actions = 'tests/testing_data/error/actions.yml'
        bot = 'test_data_import'
        user = 'test'
        bot_home = os.path.join(pytest.tmp_dir, bot, str(uuid.uuid4()))
        shutil.copytree(path, bot_home)
        shutil.copy2(http_actions, bot_home)
        importer = DataImporter(bot_home, bot, user, REQUIREMENTS.copy(), False, False)
        summary, component_count = await importer.validate()
        assert not summary.get('intents')
        assert not summary.get('stories')
        assert not summary.get('utterances')
        assert len(summary.get('http_action')) == 3
        summary.get('http_action')[0] = {'action_performanceUser1000@digite.com': " Required fields {'request_method'} not found."}
        assert not summary.get('training_examples')
        assert not summary.get('domain')
        assert not summary.get('config')
        assert not summary.get('exception')

    @pytest.mark.asyncio
    async def test_validate_failure(self):
        path = 'tests/testing_data/validator/common_training_examples'
        importer = DataImporter(path, 'test_data_import', 'test', REQUIREMENTS.copy())
        summary, component_count = await importer.validate()
        assert not summary.get('intents')
        assert not summary.get('stories')
        assert not summary.get('utterances')
        assert not summary.get('http_actions')
        assert summary.get('training_examples')
        assert not summary.get('domain')
        assert not summary.get('config')
        assert not summary.get('exception')

    @pytest.mark.asyncio
    async def test_validate_exception(self):
        path = 'tests/testing_data/validator/invalid_yaml'
        importer = DataImporter(path, 'test_data_import', 'test', REQUIREMENTS.copy())
        with pytest.raises(AppException):
            await importer.validate()

    @pytest.mark.asyncio
    async def test_validate_invalid_path(self):
        path = 'tests/testing_data/validator/invalid_path'
        importer = DataImporter(path, 'test_data_import', 'test', REQUIREMENTS.copy())
        with pytest.raises(AppException):
            await importer.validate()

    @pytest.mark.asyncio
    async def test_import_data(self):
        path = 'tests/testing_data/validator/valid'
        bot = 'test_data_import'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(uuid.uuid4()))
        shutil.copytree(path, test_data_path)
        importer = DataImporter(test_data_path, bot, user,
                                REQUIREMENTS - {"http_actions", "chat_client_config"}, True, True)
        await importer.validate()
        importer.import_data()

        processor = MongoProcessor()
        assert 'greet' in processor.fetch_intents(bot)
        assert 'deny' in processor.fetch_intents(bot)
        assert len(processor.fetch_stories(bot)) == 2
        assert len(list(processor.fetch_training_examples(bot))) == 7
        assert len(list(processor.fetch_responses(bot))) == 3
        assert len(processor.fetch_actions(bot)) == 2
        assert len(processor.fetch_rule_block_names(bot)) == 3

    @pytest.mark.asyncio
    async def test_import_data_with_valid_data(self):
        path = 'tests/testing_data/validator/valid_data'
        bot = 'test_data_import_with_valid_data'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(uuid.uuid4()))
        shutil.copytree(path, test_data_path)
        importer = DataImporter(test_data_path, bot, user,
                                REQUIREMENTS - {"http_actions", "chat_client_config"}, True, True)
        await importer.validate()
        importer.import_data()

        processor = MongoProcessor()
        assert 'greet' in processor.fetch_intents(bot)
        assert 'deny' in processor.fetch_intents(bot)
        assert len(processor.fetch_stories(bot)) == 2
        assert len(list(processor.fetch_training_examples(bot))) == 7
        assert len(list(processor.fetch_responses(bot))) == 4
        assert len(processor.fetch_actions(bot)) == 2
        assert len(processor.fetch_rule_block_names(bot)) == 4

    @pytest.mark.asyncio
    async def test_import_data_with_actions(self):
        path = 'tests/testing_data/validator/valid_data'
        actions = 'tests/testing_data/valid_yml/actions.yml'
        bot = 'test_data_import_with_valid_data'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(uuid.uuid4()))
        shutil.copytree(path, test_data_path)
        shutil.copy2(actions, test_data_path)
        importer = DataImporter(test_data_path, bot, user,
                                REQUIREMENTS - {"http_actions", "chat_client_config"}, True, False)
        await importer.validate()
        importer.import_data()

        processor = MongoProcessor()
        assert 'greet' in processor.fetch_intents(bot)
        assert 'deny' in processor.fetch_intents(bot)
        assert len(processor.fetch_stories(bot)) == 2
        assert len(list(processor.fetch_training_examples(bot))) == 7
        assert len(list(processor.fetch_responses(bot))) == 4
        assert len(processor.fetch_actions(bot)) == 16
        assert len(processor.fetch_rule_block_names(bot)) == 4

    @pytest.mark.asyncio
    async def test_import_data_with_multiflow(self):
        path = 'tests/testing_data/multiflow_stories/valid_with_multiflow'
        bot = 'test_data_import_multiflow'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(uuid.uuid4()))
        shutil.copytree(path, test_data_path)
        importer = DataImporter(test_data_path, bot, user,
                                REQUIREMENTS - {"http_actions", "chat_client_config"}, True, True)
        await importer.validate()
        importer.import_data()

        processor = MongoProcessor()
        assert 'greet' in processor.fetch_intents(bot)
        assert 'deny' in processor.fetch_intents(bot)
        assert len(processor.fetch_stories(bot)) == 2
        assert len(list(processor.fetch_training_examples(bot))) == 17
        assert len(list(processor.fetch_responses(bot))) == 7
        assert len(processor.fetch_actions(bot)) == 3
        assert len(processor.fetch_rule_block_names(bot)) == 3
        assert len(processor.fetch_multiflow_stories(bot)) == 2

    @pytest.mark.asyncio
    async def test_import_data_append(self):
        path = 'tests/testing_data/validator/append'
        bot = 'test_data_import'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(uuid.uuid4()))
        shutil.copytree(path, test_data_path)
        importer = DataImporter(test_data_path, bot, user,
                                REQUIREMENTS - {"http_actions", "chat_client_config"}, True, False)
        await importer.validate()
        importer.import_data()

        processor = MongoProcessor()
        assert 'greet' in processor.fetch_intents(bot)
        assert 'deny' in processor.fetch_intents(bot)
        assert 'location' in processor.fetch_intents(bot)
        assert 'affirm' in processor.fetch_intents(bot)
        assert len(processor.fetch_stories(bot)) == 4
        assert len(list(processor.fetch_training_examples(bot))) == 13
        assert len(list(processor.fetch_responses(bot))) == 6
        assert len(processor.fetch_actions(bot)) == 2
        assert len(processor.fetch_rule_block_names(bot)) == 3

    @pytest.mark.asyncio
    async def test_import_data_dont_save(self):
        path = 'tests/testing_data/validator/common_training_examples'
        bot = 'test_data_import'
        bot_2 = 'test_data_import_bot'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(uuid.uuid4()))
        shutil.copytree(path, test_data_path)
        importer = DataImporter(test_data_path, bot, user, set(), False)
        await importer.validate()
        importer.import_data()

        processor = MongoProcessor()
        intents = processor.fetch_intents(bot)
        assert 'greet' in intents
        assert 'deny' in intents
        assert 'location' in intents
        assert 'affirm' in intents
        assert len(processor.fetch_stories(bot)) == 4
        assert len(list(processor.fetch_training_examples(bot))) == 13
        assert len(list(processor.fetch_responses(bot))) == 6
        assert len(processor.fetch_actions(bot)) == 2
        assert len(processor.fetch_rule_block_names(bot)) == 3

        assert len(processor.fetch_intents(bot_2)) == 0
        assert len(processor.fetch_stories(bot_2)) == 0
        assert len(list(processor.fetch_training_examples(bot_2))) == 0
        assert len(list(processor.fetch_responses(bot_2))) == 0
        assert len(processor.fetch_actions(bot_2)) == 0
        assert len(processor.fetch_rule_block_names(bot_2)) == 0

    @pytest.mark.asyncio
    async def test_import_data_validation_failed(self):
        path = 'tests/testing_data/validator/common_training_examples'
        bot = 'test_data_import_bot'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(uuid.uuid4()))
        shutil.copytree(path, test_data_path)
        importer = DataImporter(test_data_path, bot, user, REQUIREMENTS.copy(), True)
        summary, component_count = await importer.validate()
        assert not summary.get('intents')
        assert not summary.get('stories')
        assert not summary.get('utterances')
        assert not summary.get('http_actions')
        assert summary.get('training_examples')
        assert not summary.get('domain')
        assert not summary.get('config')
        assert not summary.get('exception')

        importer.validator.intents = []
        importer.import_data()

        processor = MongoProcessor()
        assert len(processor.fetch_intents(bot)) == 0
        assert len(processor.fetch_stories(bot)) == 0
        assert len(list(processor.fetch_training_examples(bot))) == 0
        assert len(list(processor.fetch_responses(bot))) == 0
        assert len(processor.fetch_actions(bot)) == 0
