import pytest
from bot_trainer.data_processor.processor import MongoProcessor
from mongoengine import connect, disconnect
from rasa.importers.rasa import Domain
from rasa.nlu.training_data import TrainingData
from rasa.core.training.structures import StoryGraph
from mongoengine.errors import ValidationError
from bot_trainer.data_processor.data_objects import *

class TestMongoProcessor:

    @pytest.fixture(autouse=True)
    def init_connection(self):
        connect('mongoenginetest', host='mongomock://localhost')

    def test_load_from_path(self):
        processor = MongoProcessor()
        assert processor.save_from_path('tests/testing_data/correct', 'tests', 'testUser') == None

    def test_load_from_path_error(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            processor.save_from_path('tests/testing_data/error', 'tests', 'testUser')

    def test_load_nlu(self):
        processor = MongoProcessor()
        assert isinstance(processor.load_nlu('tests'), TrainingData) == True

    def test_load_domain(self):
        processor = MongoProcessor()
        assert isinstance(processor.load_domain('tests'), Domain) == True

    def test_load_stories(self):
        processor = MongoProcessor()
        assert isinstance(processor.load_stories('tests'), StoryGraph) == True

    def test_add_intent(self):
        processor = MongoProcessor()
        assert processor.add_intent('greeting', 'tests', 'testUser') == None

    def test_get_intents(self):
        processor = MongoProcessor()
        expected = ['affirm', 'bot_challenge', 'deny', 'goodbye', 'greet', 'mood_great', 'mood_unhappy', 'greeting']
        actual = processor.get_intents('tests')
        print(actual)
        assert actual.__len__() == expected.__len__()
        assert all(item in expected for item in actual)

    def test_add_intent_duplicate(self):
        processor = MongoProcessor()
        print(Intents.objects(bot='tests', __raw__={ 'name': 'greeting' }).__len__())
        with pytest.raises(Exception):
            processor.add_intent('greeting', 'tests', 'testUser')

    def test_add_none_intent(self):
        processor = MongoProcessor()
        with pytest.raises(ValidationError):
            processor.add_intent(None, 'tests', 'testUser')

    def test_add_empty_intent(self):
        processor = MongoProcessor()
        with pytest.raises(ValidationError):
            processor.add_intent('', 'tests', 'testUser')

    def test_add_blank_intent(self):
        processor = MongoProcessor()
        with pytest.raises(ValidationError):
            processor.add_intent('  ', 'tests', 'testUser')

    def test_add_training_example(self):
        processor = MongoProcessor()
        assert processor.add_training_example('Hi','greeting', 'tests', 'testUser') == None

    def test_add_same_training_example(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            processor.add_training_example('Hi','greeting', 'tests', 'testUser')

    def test_add_training_example_none_text(self):
        processor = MongoProcessor()
        with pytest.raises(ValidationError):
            processor.add_training_example(None,'greeting', 'tests', 'testUser')

    def test_add_training_example_empty_text(self):
        processor = MongoProcessor()
        with pytest.raises(ValidationError):
            processor.add_training_example('','greeting', 'tests', 'testUser')

    def test_add_training_example_blank_text(self):
        processor = MongoProcessor()
        with pytest.raises(ValidationError):
            processor.add_training_example('  ','greeting', 'tests', 'testUser')


    def test_add_training_example_none_intent(self):
        processor = MongoProcessor()
        with pytest.raises(ValidationError):
            processor.add_training_example('Hi! How are you', None, 'tests', 'testUser')

    def test_add_training_example_empty_intent(self):
        processor = MongoProcessor()
        with pytest.raises(ValidationError):
            processor.add_training_example('Hi! How are you','', 'tests', 'testUser')

    def test_add_training_example_blank_intent(self):
        processor = MongoProcessor()
        with pytest.raises(ValidationError):
            processor.add_training_example('Hi! How are you','  ', 'tests', 'testUser')

    def test_add_empty_training_example(self):
        processor = MongoProcessor()
        with pytest.raises(ValidationError):
            processor.add_training_example('', None, 'tests', 'testUser')

    def test_get_training_examples(self):
        processor = MongoProcessor()
        expected = ['hey', 'hello', 'hi', 'good morning', 'good evening', 'hey there']
        actual = processor.get_training_examples('greet', 'tests')
        assert actual.__len__() == expected.__len__()
        assert all( item in expected for item in actual  )

    def test_add_training_example_with_entity(self):
        processor = MongoProcessor()
        processor.add_training_example('Log a [critical issue](priority)', 'get_priority', 'tests', 'testUser')
        new_intent = Intents.objects(bot='tests').get(name='get_priority')
        new_entity = Entities.objects(bot='tests').get(name='priority')
        new_training_example = TrainingExamples.objects(bot= 'tests').get(text="Log a critical issue")
        print(new_training_example.text)
        assert new_intent.name == "get_priority"
        assert new_entity.name == "priority"
        assert new_training_example.text == "Log a critical issue"

    def test_get_training_examples_with_entities(self):
        processor = MongoProcessor()
        processor.add_training_example('Make [TKT456](ticketID) a [critical issue](priority)', 'get_priority', 'tests', 'testUser')
        actual = processor.get_training_examples('get_priority', 'tests')
        assert "Log a [critical issue](priority)" in actual
        assert "Make [TKT456](ticketID) a [critical issue](priority)" in actual
        expected = ['hey', 'hello', 'hi', 'good morning', 'good evening', 'hey there']
        actual = processor.get_training_examples('greet', 'tests')
        assert actual.__len__() == expected.__len__()
        assert all(item in expected for item in actual)