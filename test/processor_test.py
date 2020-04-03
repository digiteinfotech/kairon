import pytest
from bot_trainer.data_processor.processor import MongoProcessor
from mongoengine import connect

connect('mongoenginetest', host='mongomock://localhost')

class TestMongoProcessor:

    def test_load_from_path(self):
        processor = MongoProcessor()
        assert processor.load_from_path('test/testing_data/correct', 'test', 100, 'testUser') == None

    def test_load_from_path_error(self):
        processor = MongoProcessor()
        with pytest.raises(Exception):
            processor.load_from_path('test/testing_data/error', 'test', 100, 'testUser')