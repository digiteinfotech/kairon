import os

import pytest
from mongoengine import connect

from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.test.processor import ModelTestingLogProcessor
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
        assert not result['failed_stories']
        assert result['precision']
        assert result['f1']
        assert result['accuracy']

    @pytest.mark.asyncio
    async def test_run_test_on_stories_failure(self):
        result = await ModelTester.run_test_on_stories(
            'tests/testing_data/model_tester/test_stories_failures/stories.yml',
            'tests/testing_data/model_tester/model_without_entities/20211020-135106.tar.gz', True)
        assert len(result['failed_stories']) == 2
        assert result['precision']
        assert result['f1']
        assert result['accuracy']
        ModelTestingLogProcessor.log_test_result('test_bot', 'test_user',
                                                              stories_result=result,
                                                              nlu_result={},
                                                              event_status='Completed')
        logs = list(ModelTestingLogProcessor.get_logs('test_bot'))
        assert not logs[0].get('exception')
        assert logs[0]['start_timestamp']
        assert not logs[0]['run_on_test_stories']
        assert logs[0].get('stories')
        assert not logs[0].get('nlu')
        assert logs[0]['stories']['failed_stories']
        assert logs[0].get('end_timestamp')
        assert logs[0].get('status') == 'FAILURE'
        assert logs[0]['event_status'] == 'Completed'

    def test_run_test_on_nlu(self):
        result = ModelTester.run_test_on_nlu('tests/testing_data/model_tester/nlu_success/nlu.yml',
                                             'tests/testing_data/model_tester/model_without_entities/20211020-135106.tar.gz')
        assert len(result['intent_evaluation']['errors']) == 0
        assert result['intent_evaluation']['precision']
        assert result['intent_evaluation']['f1_score']
        assert result['intent_evaluation']['accuracy']

    def test_run_test_on_nlu_failure(self):
        result = ModelTester.run_test_on_nlu('tests/testing_data/model_tester/nlu_failures/nlu.yml',
                                             'tests/testing_data/model_tester/model_with_entities/20211021-141717.tar.gz')
        assert len(result['intent_evaluation']['errors']) == 18
        assert result['intent_evaluation']['precision']
        assert result['intent_evaluation']['f1_score']
        assert result['intent_evaluation']['accuracy']

        assert len(result['entity_evaluation']['DIETClassifier']['errors']) == 2
        assert result['entity_evaluation']['DIETClassifier']['precision']
        assert result['entity_evaluation']['DIETClassifier']['f1_score']
        assert result['entity_evaluation']['DIETClassifier']['accuracy']
        result['response_selection_evaluation'] = {'errors': [{'text': 'this is failure', 'confidence': 0.78}]}
        ModelTestingLogProcessor.log_test_result('test_bot', 'test_user',
                                                              stories_result={},
                                                              nlu_result=result,
                                                              event_status='Completed')
        logs = list(ModelTestingLogProcessor.get_logs('test_bot'))
        assert not logs[0].get('exception')
        assert logs[0]['start_timestamp']
        assert not logs[0]['run_on_test_stories']
        assert not logs[0].get('stories')
        assert logs[0].get('nlu')
        assert logs[0]['nlu']['intent_evaluation']['errors']
        assert logs[0]['nlu']['response_selection_evaluation']['errors']
        assert logs[0].get('end_timestamp')
        assert logs[0].get('status') == 'FAILURE'
        assert logs[0]['event_status'] == 'Completed'

    def test_is_event_in_progress(self):
        assert not ModelTestingLogProcessor.is_event_in_progress('test_bot')

    def test_is_event_in_progress_failure(self):
        ModelTestingLogProcessor.log_test_result('test_bot', 'test_user')
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
