import os

from kairon.shared.data.constant import STATUSES, EVENT_STATUS

os.environ["system_file"] = "./tests/testing_data/system.yaml"
import shutil
import tempfile
import uuid

import pytest
from mongoengine import connect
from rasa.shared.importers.rasa import RasaFileImporter

from augmentation.paraphrase.paraphrasing import ParaPhrasing
from kairon.exceptions import AppException
from kairon.shared.data.data_objects import BotSettings
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.test.processor import ModelTestingLogProcessor
from kairon.shared.utils import Utility
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
                                                 event_status=EVENT_STATUS.COMPLETED.value)
        logs, row_count = ModelTestingLogProcessor.get_logs('test_bot')
        print(logs)
        assert logs[0]['data'][0]['conversation_accuracy']['success_count'] == 3
        assert logs[0]['data'][0]['conversation_accuracy']['failure_count'] == 2
        assert logs[0]['data'][0]['conversation_accuracy']['total_count'] == 5
        assert not logs[0].get('exception')
        assert logs[0]['start_timestamp']
        assert logs[0].get('data')
        assert not logs[0].get('nlu')
        assert next(data['failed_stories'] for data in logs[0].get('data') if data['type'] == 'stories')
        assert logs[0].get('end_timestamp')
        assert logs[0].get('status') == STATUSES.FAIL.value
        assert logs[0]['event_status'] == 'Completed'
        logs, row_count = ModelTestingLogProcessor.get_logs('test_bot', 'stories', logs[0]['reference_id'])
        assert len(logs['errors']) == 2
        assert logs['failure_count'] == 2
        assert logs['success_count'] == 3
        assert logs['total_count'] == 5

    def test_run_test_on_nlu(self):
        saved_phrases = {'hey', 'goodbye', 'that sounds good', 'I am feeling very good'}
        result = ModelTester.run_test_on_nlu('tests/testing_data/model_tester/nlu_success/nlu.yml',
                                             pytest.model_path, saved_phrases, "tests/testing_data/model_tester/domain.yml")
        assert result['intent_evaluation']['total_count'] == 43
        assert result['intent_evaluation']['failure_count'] == 0
        assert len(result['intent_evaluation']['successes']) == 0
        assert len(result['intent_evaluation']['errors']) == 0
        assert result['intent_evaluation']['precision']
        assert result['intent_evaluation']['f1_score']
        assert result['intent_evaluation']['accuracy']

    def test_run_test_on_nlu_failure(self):
        saved_phrases = {'sad', 'awful', 'that sounds good', 'I am feeling very good'}
        result = ModelTester.run_test_on_nlu('tests/testing_data/model_tester/nlu_failures/nlu.yml',
                                             pytest.model_path, saved_phrases, "tests/testing_data/model_tester/domain.yml")
        assert result['intent_evaluation']['total_count'] == 52
        assert result['intent_evaluation']['success_count'] == 29
        assert result['intent_evaluation']['failure_count'] == 23
        assert len(result['intent_evaluation']['successes']) == 0
        synthesized_phrases = [err for err in result['intent_evaluation']['errors'] if err['is_synthesized']]
        from_training_phrases = [err for err in result['intent_evaluation']['errors'] if err['is_synthesized'] == False]
        assert len(synthesized_phrases) == 21
        assert len(from_training_phrases) == 2
        assert len(result['intent_evaluation']['errors']) == 23
        assert result['intent_evaluation']['precision']
        assert result['intent_evaluation']['f1_score']
        assert result['intent_evaluation']['accuracy']

        assert len(result['entity_evaluation']['DIETClassifier']['errors']) == 2
        assert result['entity_evaluation']['DIETClassifier']['precision']
        assert result['entity_evaluation']['DIETClassifier']['f1_score']
        assert result['entity_evaluation']['DIETClassifier']['accuracy']
        ModelTestingLogProcessor.log_test_result('test_bot', 'test_user',
                                                 stories_result={},
                                                 nlu_result=result,
                                                 event_status=EVENT_STATUS.COMPLETED.value)
        logs1, row_count = ModelTestingLogProcessor.get_logs('test_bot')
        print(logs1)
        assert logs1[0]['data'][0]['intent_evaluation']['success_count'] == 29
        assert logs1[0]['data'][0]['intent_evaluation']['failure_count'] == 23
        assert logs1[0]['data'][0]['intent_evaluation']['total_count'] == 52
        synthesized_phrases = [err for err in logs1[0]['data'][0]['intent_evaluation']['errors'] if err['is_synthesized']]
        from_training_phrases = [err for err in logs1[0]['data'][0]['intent_evaluation']['errors'] if err['is_synthesized'] == False]
        assert len(synthesized_phrases) == 21
        assert len(from_training_phrases) == 2
        assert logs1[0]['data'][0]['entity_evaluation']['DIETClassifier']['success_count'] == 2
        assert logs1[0]['data'][0]['entity_evaluation']['DIETClassifier']['failure_count'] == 2
        assert logs1[0]['data'][0]['entity_evaluation']['DIETClassifier']['total_count'] == 4
        assert logs1[0]['data'][0]['response_selection_evaluation']['success_count'] == 0
        assert logs1[0]['data'][0]['response_selection_evaluation']['failure_count'] == 5
        assert logs1[0]['data'][0]['response_selection_evaluation']['total_count'] == 5
        assert not logs1[0].get('exception')
        assert logs1[0]['start_timestamp']
        assert not logs1[0].get('stories')
        assert next(data for data in logs1[0].get('data') if data['type'] == 'nlu')
        assert logs1[0].get('end_timestamp')
        assert logs1[0].get('status') == STATUSES.FAIL.value
        assert logs1[0]['event_status'] == 'Completed'
        logs, row_count = ModelTestingLogProcessor.get_logs('test_bot', 'nlu', logs1[0]['reference_id'])
        assert len(logs['intent_evaluation']['errors']) == 10
        assert logs['intent_evaluation']['failure_count'] == 23
        assert logs['intent_evaluation']['success_count'] == 29
        assert logs['intent_evaluation']['total_count'] == 52
        logs, row_count = ModelTestingLogProcessor.get_logs('test_bot', 'entity_evaluation_with_diet_classifier',
                                                 logs1[0]['reference_id'])
        assert len(logs['entity_evaluation']['errors']) == 2
        assert logs['entity_evaluation']['failure_count'] == 2
        assert logs['entity_evaluation']['success_count'] == 2
        assert logs['entity_evaluation']['total_count'] == 4
        logs, row_count = ModelTestingLogProcessor.get_logs('test_bot', 'entity_evaluation_with_regex_entity_extractor',
                                                 logs1[0]['reference_id'])
        assert len(logs['entity_evaluation']['errors']) == 0
        assert logs['entity_evaluation']['failure_count'] == 0
        assert logs['entity_evaluation']['success_count'] == 0
        assert logs['entity_evaluation']['total_count'] == 0
        logs, row_count = ModelTestingLogProcessor.get_logs('test_bot', 'response_selection_evaluation', logs1[0]['reference_id'])
        assert len(logs['response_selection_evaluation']['errors']) == 5
        assert logs['response_selection_evaluation']['failure_count'] == 5
        assert logs['response_selection_evaluation']['success_count'] == 0
        assert logs['response_selection_evaluation']['total_count'] == 5
        logs, row_count = ModelTestingLogProcessor.get_logs('test_bot', 'nlu', logs1[0]['reference_id'], 10, 15)
        assert len(logs['intent_evaluation']['errors']) == 13
        assert logs['intent_evaluation']['failure_count'] == 23
        assert logs['intent_evaluation']['success_count'] == 29
        assert logs['intent_evaluation']['total_count'] == 52
        logs, row_count = ModelTestingLogProcessor.get_logs('test_bot', 'entity_evaluation_with_diet_classifier',
                                                 logs1[0]['reference_id'], 10, 15)
        assert len(logs['entity_evaluation']['errors']) == 0
        assert logs['entity_evaluation']['failure_count'] == 2
        assert logs['entity_evaluation']['success_count'] == 2
        assert logs['entity_evaluation']['total_count'] == 4
        logs, row_count = ModelTestingLogProcessor.get_logs('test_bot', 'entity_evaluation_with_regex_entity_extractor',
                                                 logs1[0]['reference_id'], 10, 15)
        assert len(logs['entity_evaluation']['errors']) == 0
        assert logs['entity_evaluation']['failure_count'] == 0
        assert logs['entity_evaluation']['success_count'] == 0
        assert logs['entity_evaluation']['total_count'] == 0
        logs, row_count = ModelTestingLogProcessor.get_logs('test_bot', 'response_selection_evaluation',
                                                 logs1[0]['reference_id'], 10, 15)
        assert len(logs['response_selection_evaluation']['errors']) == 0
        assert logs['response_selection_evaluation']['failure_count'] == 5
        assert logs['response_selection_evaluation']['success_count'] == 0
        assert logs['response_selection_evaluation']['total_count'] == 5

        result['entity_evaluation'] = None
        result['response_selection_evaluation'] = None
        ModelTestingLogProcessor.log_test_result('test_bot', 'test_user',
                                                 stories_result={},
                                                 nlu_result=result,
                                                 event_status=EVENT_STATUS.COMPLETED.value)
        logs, row_count = ModelTestingLogProcessor.get_logs('test_bot')
        logs2, row_count = ModelTestingLogProcessor.get_logs('test_bot', 'nlu', logs[0]['reference_id'])
        assert len(logs2['intent_evaluation']['errors']) == 10
        assert logs2['intent_evaluation']['failure_count'] == 23
        assert logs2['intent_evaluation']['success_count'] == 29
        assert logs2['intent_evaluation']['total_count'] == 52
        logs2, row_count = ModelTestingLogProcessor.get_logs('test_bot', 'entity_evaluation_with_diet_classifier',
                                                  logs[0]['reference_id'])
        assert logs2['entity_evaluation'] == {'errors': [], 'failure_count': 0, 'success_count': 0, 'total_count': 0}
        logs2, row_count = ModelTestingLogProcessor.get_logs('test_bot', 'entity_evaluation_with_regex_entity_extractor',
                                                  logs[0]['reference_id'])
        assert logs2['entity_evaluation'] == {'errors': [], 'failure_count': 0, 'success_count': 0, 'total_count': 0}
        logs2, row_count = ModelTestingLogProcessor.get_logs('test_bot', 'response_selection_evaluation', logs[0]['reference_id'])
        assert logs2['response_selection_evaluation'] == {'errors': [], 'failure_count': 0,
                                                          'success_count': 0, 'total_count': 0}

    def test_is_event_in_progress(self):
        assert not ModelTestingLogProcessor.is_event_in_progress('test_bot')

    def test_is_event_in_progress_failure(self):
        ModelTestingLogProcessor.log_test_result('test_bot', 'test_user')
        assert ModelTestingLogProcessor.is_event_in_progress('test_bot', False)

        with pytest.raises(AppException, match='Event already in progress! Check logs.'):
            ModelTestingLogProcessor.is_event_in_progress('test_bot')

    def test_is_limit_exceeded_failure(self, monkeypatch):
        bot = 'test_bot_model_testing'
        BotSettings(bot=bot, user="test_user", test_limit_per_day=0).save()
        assert ModelTestingLogProcessor.is_limit_exceeded(bot, False)

        with pytest.raises(AppException, match='Daily limit exceeded.'):
            ModelTestingLogProcessor.is_limit_exceeded(bot)

    def test_is_limit_exceeded(self, monkeypatch):
        bot = 'test_bot_model_testing'
        bot_settings = BotSettings.objects(bot=bot).get()
        bot_settings.test_limit_per_day = 5
        bot_settings.save()
        assert not ModelTestingLogProcessor.is_limit_exceeded(bot)

    def test_trigger_model_testing_model_no_model_found(self):
        bot = 'test_events_no_nlu_model'
        with pytest.raises(AppException, match="Model testing failed: Folder does not exists!"):
            ModelTester.run_tests_on_model(bot)

    @pytest.fixture
    def load_data(self):
        from kairon.shared.data.constant import REQUIREMENTS
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

    @pytest.mark.asyncio
    async def test_data_generator(self, load_data, monkeypatch):
        bot = 'test_events_bot'
        user = 'test_user'
        config_path = 'tests/testing_data/model_tester/config.yml'
        domain_path = 'tests/testing_data/model_tester/domain.yml'
        nlu_path = 'tests/testing_data/model_tester/nlu_failures/nlu.yml'
        stories_path = 'tests/testing_data/model_tester/test_stories_success/test_stories.yml'
        await load_data(config_path, domain_path, nlu_path, stories_path, bot, user)

        def __mock_resp(*args, **kwargs):
            return []

        monkeypatch.setattr(ParaPhrasing, "paraphrases", __mock_resp)
        nlu_path, stories_path, saved_phrases, domain_path = TestDataGenerator.create(bot, True)
        assert os.path.exists(nlu_path)
        assert os.path.exists(stories_path)
        assert os.path.exists(domain_path)
        assert saved_phrases == {'name?', 'am i talking to a tiger?', 'good morning', 'are you a bot?', 'never',
                                 'what is your name?', 'am i talking to an elephant?', 'not really', 'extremely sad',
                                 'am I talking to a human?', 'bye', 'not very good', 'see you around', 'see you later',
                                 'sad', 'hello', 'correct', 'that sounds good', 'I am great', 'unhappy', 'great',
                                 'very bad', 'awful', 'of course', 'no', 'yes', 'what do you do?', 'terrible',
                                 'very sad', 'good evening', 'hi', 'am i talking to a mango?', 'bad', 'no way',
                                 "I don't think so", "I'm good", 'am i talking to a apple?', 'introduce yourself',
                                 'indeed', 'are you a human?', 'so sad', 'hey', 'wonderful', 'I am feeling very good',
                                 'am I talking to a bot?', 'where do you work?', 'very good', 'perfect', 'amazing',
                                 'hey there', "don't like that", 'goodbye'}

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

        def __mock_resp(*args, **kwargs):
            return ["agree", "right", "exactly"]

        monkeypatch.setattr(ParaPhrasing, "paraphrases", __mock_resp)
        nlu_path, stories_path, saved_phrases, domain_path = TestDataGenerator.create(bot, True)
        assert os.path.exists(nlu_path)
        assert os.path.exists(stories_path)
        assert os.path.exists(domain_path)
        assert saved_phrases == {'yes', 'that sounds good', 'indeed', 'correct', 'of course'}

    def test_data_generator_no_training_data(self):
        bot = 'no_data_bot'
        with pytest.raises(AppException, match='Not enough training data exists. Please add some training data.'):
            TestDataGenerator.create(bot, True)

    @pytest.mark.asyncio
    async def test_data_generator_samples_threshold(self, load_data, monkeypatch):
        bot = 'test_threshold'
        user = 'test_user'
        config_path = 'tests/testing_data/model_tester/config.yml'
        domain_path = 'tests/testing_data/model_tester/threshold/domain.yml'
        nlu_path = 'tests/testing_data/model_tester/threshold/nlu.yml'
        stories_path = 'tests/testing_data/model_tester/threshold/stories.yml'
        await load_data(config_path, domain_path, nlu_path, stories_path, bot, user)

        def __mock_resp(*args, **kwargs):
            return []

        monkeypatch.setattr(ParaPhrasing, "paraphrases", __mock_resp)

        nlu_path, stories_path, saved_phrases, domain_path = TestDataGenerator.create(bot, True)
        assert os.path.exists(nlu_path)
        assert os.path.exists(stories_path)
        assert os.path.exists(domain_path)
        assert len(saved_phrases) == 20

    @pytest.mark.asyncio
    async def test_data_generator_disable_augmentation(self):
        bot = 'test_threshold'
        nlu_path, stories_path, saved_phrases, domain_path = TestDataGenerator.create(bot, True, False)
        assert os.path.exists(nlu_path)
        assert os.path.exists(stories_path)
        assert os.path.exists(domain_path)
        assert len(saved_phrases) == 135
