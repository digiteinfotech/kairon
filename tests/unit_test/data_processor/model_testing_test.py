import os
import shutil
import tempfile
import uuid

import pytest
from mongoengine import connect
from rasa.shared.importers.rasa import RasaFileImporter

from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.test.processor import ModelTestingLogProcessor
from kairon.test.test_models import ModelTester, TestDataGenerator


class TestModelTesting:

    @pytest.fixture(autouse=True, scope="class")
    def init_connection(self):
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
        shutil.rmtree(pytest.tmp_dir)
        shutil.rmtree('tests/testing_data/model_tester/models')

    @pytest.mark.asyncio
    async def test_run_test_on_stories(self):
        result = await ModelTester.run_test_on_stories(
            'tests/testing_data/model_tester/test_stories_success/test_stories.yml',
            pytest.model_path, True)
        assert not result['failed_stories']
        assert result['precision']
        assert result['f1']
        assert result['accuracy']

    @pytest.mark.asyncio
    async def test_run_test_on_stories_failure(self):
        result = await ModelTester.run_test_on_stories(
            'tests/testing_data/model_tester/test_stories_failures/test_stories.yml',
            pytest.model_path, True)
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
        assert logs[0].get('data')
        assert not logs[0].get('nlu')
        assert next(data['failed_stories'] for data in logs[0].get('data') if data['type'] == 'stories')
        assert logs[0].get('end_timestamp')
        assert logs[0].get('status') == 'FAILURE'
        assert logs[0]['event_status'] == 'Completed'

    def test_run_test_on_nlu(self):
        result = ModelTester.run_test_on_nlu('tests/testing_data/model_tester/nlu_success/nlu.yml',
                                             pytest.model_path)
        assert len(result['intent_evaluation']['errors']) == 0
        assert result['intent_evaluation']['precision']
        assert result['intent_evaluation']['f1_score']
        assert result['intent_evaluation']['accuracy']

    def test_run_test_on_nlu_failure(self):
        result = ModelTester.run_test_on_nlu('tests/testing_data/model_tester/nlu_failures/nlu.yml',
                                             pytest.model_path)
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
        assert not logs[0].get('stories')
        assert next(data for data in logs[0].get('data') if data['type'] == 'nlu')
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

    def test_trigger_model_testing_model_no_model_found(self):
        bot = 'test_events_no_nlu_model'
        with pytest.raises(AppException, match="Model testing failed: Folder does not exists!"):
            ModelTester.run_tests_on_model(bot)

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
            processor.save_training_data(bot, user, config, domain, story_graph, nlu, overwrite=True)

        return _read_and_get_data

    @pytest.mark.asyncio
    async def test_data_generator(self, load_data):
        bot = 'test_events_bot'
        user = 'test_user'
        config_path = 'tests/testing_data/model_tester/config.yml'
        domain_path = 'tests/testing_data/model_tester/domain.yml'
        nlu_path = 'tests/testing_data/model_tester/nlu_success/nlu.yml'
        stories_path = 'tests/testing_data/model_tester/test_stories_success/test_stories.yml'
        await load_data(config_path, domain_path, nlu_path, stories_path, bot, user)
        nlu_path, stories_path = TestDataGenerator.create(bot, True)
        assert os.path.exists(nlu_path)
        assert os.path.exists(stories_path)

    @pytest.mark.asyncio
    async def test_data_generator_no_training_example_for_intent(self, load_data, monkeypatch):
        bot = 'test_events_bot'
        user = 'test_user'

        def _mock_test_data(*args, **kwargs):
            return {'affirm': [{'text': 'yes', 'entities': None, '_id': '61b08b91d0807d6fb24270ae'},
                               {'text': 'indeed', 'entities': None, '_id': '61b08b91d0807d6fb24270af'},
                               {'text': 'of course', 'entities': None, '_id': '61b08b91d0807d6fb24270b0'},
                               {'text': 'that sounds good', 'entities': None, '_id': '61b08b91d0807d6fb24270b1'},
                               {'text': 'correct', 'entities': None, '_id': '61b08b91d0807d6fb24270b2'}],
                    'mood_unhappy': []}

        monkeypatch.setattr(MongoProcessor, 'get_intents_and_training_examples', _mock_test_data)
        config_path = 'tests/testing_data/model_tester/config.yml'
        domain_path = 'tests/testing_data/model_tester/domain.yml'
        nlu_path = 'tests/testing_data/model_tester/nlu_success/nlu.yml'
        stories_path = 'tests/testing_data/model_tester/test_stories_success/test_stories.yml'
        await load_data(config_path, domain_path, nlu_path, stories_path, bot, user)
        with pytest.raises(AppException, match='No training examples found for intent: [\'mood_unhappy\']'):
            TestDataGenerator.create(bot, True)
