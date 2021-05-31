import os
import shutil
import tempfile
from datetime import datetime

import pytest
from mongoengine import connect

from kairon import Utility
from kairon.data_processor.processor import MongoProcessor
from kairon.importer.data_importer import DataImporter
from kairon.exceptions import AppException


def pytest_namespace():
    return {'tmp_dir': None}


class TestDataImporter:

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
    async def test_validate_success(self):
        path = 'tests/testing_data/validator/valid'
        importer = DataImporter(path, 'test_data_import', 'test', False, False)
        summary = await importer.validate()
        assert not summary.get('intents')
        assert not summary.get('stories')
        assert not summary.get('utterances')
        assert not summary.get('http_actions')
        assert not summary.get('training_examples')
        assert not summary.get('domain')
        assert not summary.get('config')
        assert not summary.get('exception')

    @pytest.mark.asyncio
    async def test_validate_failure(self):
        path = 'tests/testing_data/validator/common_training_examples'
        importer = DataImporter(path, 'test_data_import', 'test')
        summary = await importer.validate()
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
        importer = DataImporter(path, 'test_data_import', 'test')
        with pytest.raises(AppException):
            await importer.validate()

    @pytest.mark.asyncio
    async def test_validate_invalid_path(self):
        path = 'tests/testing_data/validator/invalid_path'
        importer = DataImporter(path, 'test_data_import', 'test')
        with pytest.raises(AppException):
            await importer.validate()

    @pytest.mark.asyncio
    async def test_import_data(self):
        path = 'tests/testing_data/validator/valid'
        bot = 'test_data_import'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(datetime.utcnow()))
        shutil.copytree(path, test_data_path)
        importer = DataImporter(test_data_path, bot, user, True, True)
        await importer.validate()
        importer.import_data()

        processor = MongoProcessor()
        assert 'greet' in processor.fetch_intents(bot)
        assert 'deny' in processor.fetch_intents(bot)
        assert len(processor.fetch_stories(bot)) == 2
        assert len(list(processor.fetch_training_examples(bot))) == 7
        assert len(list(processor.fetch_responses(bot))) == 2
        assert len(processor.fetch_actions(bot)) == 2
        assert len(processor.fetch_rule_block_names(bot)) == 3

    @pytest.mark.asyncio
    async def test_import_data_append(self):
        path = 'tests/testing_data/validator/append'
        bot = 'test_data_import'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(datetime.utcnow()))
        shutil.copytree(path, test_data_path)
        importer = DataImporter(test_data_path, bot, user, True, False)
        await importer.validate()
        importer.import_data()

        processor = MongoProcessor()
        assert 'greet' in processor.fetch_intents(bot)
        assert 'deny' in processor.fetch_intents(bot)
        assert 'location' in processor.fetch_intents(bot)
        assert 'affirm' in processor.fetch_intents(bot)
        assert len(processor.fetch_stories(bot)) == 4
        assert len(list(processor.fetch_training_examples(bot))) == 13
        assert len(list(processor.fetch_responses(bot))) == 4
        assert len(processor.fetch_actions(bot)) == 3
        assert len(processor.fetch_rule_block_names(bot)) == 3

    @pytest.mark.asyncio
    async def test_import_data_dont_save(self):
        path = 'tests/testing_data/validator/common_training_examples'
        bot = 'test_data_import'
        bot_2 = 'test_data_import_bot'
        user = 'test'
        test_data_path = os.path.join(pytest.tmp_dir, str(datetime.utcnow()))
        shutil.copytree(path, test_data_path)
        importer = DataImporter(test_data_path, bot, user, False)
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
        assert len(list(processor.fetch_responses(bot))) == 4
        assert len(processor.fetch_actions(bot)) == 3
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
        test_data_path = os.path.join(pytest.tmp_dir, str(datetime.utcnow()))
        shutil.copytree(path, test_data_path)
        importer = DataImporter(test_data_path, bot, user)
        summary = await importer.validate()
        assert not summary.get('intents')
        assert not summary.get('stories')
        assert not summary.get('utterances')
        assert not summary.get('http_actions')
        assert summary.get('training_examples')
        assert not summary.get('domain')
        assert not summary.get('config')
        assert not summary.get('exception')

        importer.import_data()

        processor = MongoProcessor()
        intents = processor.fetch_intents(bot)
        assert 'greet' in intents
        assert 'refute' in intents
        assert 'deny' in intents
        assert len(processor.fetch_stories(bot)) == 3
        assert len(list(processor.fetch_training_examples(bot))) == 10
        assert len(list(processor.fetch_responses(bot))) == 2
        assert len(processor.fetch_actions(bot)) == 2
