import pytest
from bot_trainer.data_processor.processor import MongoProcessor
from mongoengine import connect
from rasa.importers.rasa import Domain
from rasa.nlu.training_data import TrainingData
from rasa.core.training.structures import StoryGraph

connect('mongoenginetest', host='mongomock://localhost')

class TestMongoProcessor:

    def test_load_from_path(self):
        processor = MongoProcessor()
        assert processor.save_from_path('tests/testing_data/correct', 'tests', 100, 'testUser') == None

    def test_load_from_path_error(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            processor.save_from_path('tests/testing_data/error', 'tests', 100, 'testUser')

    def test_load_nlu(self):
        processor = MongoProcessor()
        assert isinstance(processor.load_nlu('tests', 100), TrainingData) == True

    def test_load_domain(self):
        processor = MongoProcessor()
        assert isinstance(processor.load_domain('tests', 100), Domain) == True

    def test_load_stories(self):
        processor = MongoProcessor()
        assert isinstance(processor.load_stories('tests', 100), StoryGraph) == True