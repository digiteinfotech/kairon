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