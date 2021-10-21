import os

import pytest
from mongoengine import connect

from kairon import Utility
from kairon.exceptions import AppException
from kairon.test.processor import ModelTestingLogProcessor
from kairon.test.test_models import ModelTester


class TestModelTesting:

    @pytest.fixture(autouse=True, scope="session")
    def init_connection(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))

    @pytest.mark.asyncio
    async def test_run_test_on_stories(self):
        result = await ModelTester.run_test_on_stories(
            'tests/testing_data/model_tester/test_stories_success/stories.yml',
            'tests/testing_data/model_tester/model_without_entities/20211020-135106.tar.gz', True)
        assert len(result['successful_stories']) == 5
        assert not result['failed_stories']
        assert result['precision']
        assert result['f1']
        assert result['accuracy']

    @pytest.mark.asyncio
    async def test_run_test_on_stories_failure(self):
        result = await ModelTester.run_test_on_stories(
            'tests/testing_data/model_tester/test_stories_failures/stories.yml',
            'tests/testing_data/model_tester/model_without_entities/20211020-135106.tar.gz', True)
        assert len(result['successful_stories']) == 3
        assert len(result['failed_stories']) == 2
        assert result['precision']
        assert result['f1']
        assert result['accuracy']

    def test_run_test_on_nlu(self):
        result = ModelTester.run_test_on_nlu('tests/testing_data/model_tester/nlu_success/nlu.yml',
                                             'tests/testing_data/model_tester/model_without_entities/20211020-135106.tar.gz')
        assert len(result['intent_evaluation']['predictions']) == 43
        assert len(result['intent_evaluation']['successes']) == 43
        assert len(result['intent_evaluation']['errors']) == 0
        assert result['intent_evaluation']['precision']
        assert result['intent_evaluation']['f1_score']
        assert result['intent_evaluation']['accuracy']

    def test_run_test_on_nlu_failure(self):
        result = ModelTester.run_test_on_nlu('tests/testing_data/model_tester/nlu_failures/nlu.yml',
                                             'tests/testing_data/model_tester/model_with_entities/20211021-141717.tar.gz')
        assert len(result['intent_evaluation']['predictions']) == 47
        assert len(result['intent_evaluation']['successes']) == 29
        assert len(result['intent_evaluation']['errors']) == 18
        assert result['intent_evaluation']['precision']
        assert result['intent_evaluation']['f1_score']
        assert result['intent_evaluation']['accuracy']

        assert len(result['entity_evaluation']['DIETClassifier']['successes']) == 2
        assert len(result['entity_evaluation']['DIETClassifier']['errors']) == 2
        assert result['entity_evaluation']['DIETClassifier']['precision']
        assert result['entity_evaluation']['DIETClassifier']['f1_score']
        assert result['entity_evaluation']['DIETClassifier']['accuracy']

    def test_is_event_in_progress(self):
        assert not ModelTestingLogProcessor.is_event_in_progress('test_bot')

    def test_is_event_in_progress_failure(self):
        ModelTestingLogProcessor.add_initiation_log('test_bot', 'test_user', False)
        assert ModelTestingLogProcessor.is_event_in_progress('test_bot', False)

        with pytest.raises(AppException, match='Event already in progress! Check logs.'):
            ModelTestingLogProcessor.is_event_in_progress('test_bot')

    def test_is_limit_exceeded(self, monkeypatch):
        monkeypatch.setitem(Utility.environment['model']['test'], 'limit_per_day', 5)
        assert not ModelTestingLogProcessor.is_limit_exceeded('test_bot')

    def test_is_limit_exceeded_failure(self, monkeypatch):
        monkeypatch.setitem(Utility.environment['model']['test'], 'limit_per_day', 0)
        assert ModelTestingLogProcessor.is_limit_exceeded('test_bot', False)

        with pytest.raises(AppException, match='Daily limit exceeded.'):
            ModelTestingLogProcessor.is_limit_exceeded('test_bot')
