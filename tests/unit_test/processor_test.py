import pytest
from bot_trainer.data_processor.processor import MongoProcessor
from mongoengine import connect, disconnect
from rasa.importers.rasa import Domain
from rasa.nlu.training_data import TrainingData
from rasa.core.training.structures import StoryGraph
from mongoengine.errors import ValidationError

connect('mongoenginetest', host='mongomock://localhost')

class TestMongoProcessor:

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