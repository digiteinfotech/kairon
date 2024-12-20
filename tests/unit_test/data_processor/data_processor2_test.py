import os
from unittest.mock import patch, MagicMock

import pytest

from kairon.exceptions import AppException
from kairon.shared.cognition.processor import CognitionDataProcessor
from kairon.shared.utils import Utility
os.environ["system_file"] = "./tests/testing_data/system.yaml"
Utility.load_environment()
Utility.load_system_metadata()

from kairon.shared.data.processor import MongoProcessor

# NOTE: use this file for adding new tests for the data_processor module


def test_data_format_correction():
    metadata = [
        {'column_name': 'age', 'data_type': 'int'},
        {'column_name': 'height', 'data_type': 'float'},
        {'column_name': 'name', 'data_type': 'str'},
        {'column_name': 'extra', 'data_type': 'dict'},  # Unsupported type
    ]

    data_entries = [
        {'age': '25', 'height': '175.5', 'name': 'Alice', 'extra': {'key': 'value'}},
        {'age': ['30'], 'height': [180.0], 'name': ['Bob'], 'extra': [1, 2, 3]},
        {'age': None, 'height': '165.2', 'name': 'Charlie', 'extra': None},
        {'age': '40', 'height': None, 'name': None, 'extra': 'not a dict'}
    ]

    expected_output = [
        {'age': 25, 'height': 175.5, 'name': 'Alice', 'extra': {'key': 'value'}},
        {'age': 30, 'height': 180.0, 'name': 'Bob', 'extra': [1, 2, 3]},
        {'age': None, 'height': 165.2, 'name': 'Charlie', 'extra': None},
        {'age': 40, 'height': None, 'name': None, 'extra': 'not a dict'}
    ]

    result = MongoProcessor.data_format_correction_cognition_data(data_entries, metadata)
    assert result == expected_output, f"Expected {expected_output}, but got {result}"

def test_empty_entries():
    metadata = [{'column_name': 'age', 'data_type': 'int'}]
    data_entries = []
    result = MongoProcessor.data_format_correction_cognition_data(data_entries, metadata)
    assert result == [], f"Expected [], but got {result}"


def test_non_list_non_string_values():
    metadata = [{'column_name': 'age', 'data_type': 'int'}]
    data_entries = [{'age': '22', 'height': 5.7, 'name': 'Tom'}]
    expected_output = [{'age': 22, 'height': 5.7, 'name': 'Tom'}]
    result = MongoProcessor.data_format_correction_cognition_data(data_entries, metadata)
    assert result == expected_output, f"Expected {expected_output}, but got {result}"

def test_validate_metadata_and_payload_valid():
    schema = {
        "column_name": "item",
        "data_type": "str",
        "enable_search": True,
        "create_embeddings": True
    }
    data = {
        "id": 1,
        "item": "Cover",
        "price": 0.4,
        "quantity": 20
    }

    CognitionDataProcessor.validate_column_values(data, schema)

def test_validate_metadata_and_payload_invalid_str():
    schema = {
        "column_name": "item",
        "data_type": "str",
        "enable_search": True,
        "create_embeddings": True
    }
    data = {
        "id": 1,
        "item": 123,
        "price": 0.4,
        "quantity": 20
    }

    with pytest.raises(AppException, match="Invalid data type for 'item': Expected string value"):
        CognitionDataProcessor.validate_column_values(data, schema)


def test_validate_metadata_and_payload_invalid_int():
    schema = {
        "column_name": "id",
        "data_type": "int",
        "enable_search": True,
        "create_embeddings": True
    }
    data = {
        "id": "one",
        "item": "Cover",
        "price": 0.4,
        "quantity": 20
    }

    with pytest.raises(AppException, match="Invalid data type for 'id': Expected integer value"):
        CognitionDataProcessor.validate_column_values(data, schema)

def test_validate_metadata_and_payload_invalid_float():
    schema = {
        "column_name": "price",
        "data_type": "float",
        "enable_search": True,
        "create_embeddings": True
    }
    data = {
        "id": 1,
        "item": "Cover",
        "price": "cheap",
        "quantity": 20
    }

    with pytest.raises(AppException, match="Invalid data type for 'price': Expected float value"):
        CognitionDataProcessor.validate_column_values(data, schema)

def test_validate_metadata_and_payload_int_value_in_float_field():
    schema = {
        "column_name": "price",
        "data_type": "float",
        "enable_search": True,
        "create_embeddings": True
    }
    data = {
        "id": 1,
        "item": "Cover",
        "price": 231,
        "quantity": 20
    }
    CognitionDataProcessor.validate_column_values(data, schema)

def test_validate_metadata_and_payload_missing_column():
    schema = {
        "column_name": "quantity",
        "data_type": "int",
        "enable_search": True,
        "create_embeddings": True
    }
    data = {
        "id": 1,
        "item": "Cover",
        "price": 0.4
    }

    with pytest.raises(AppException, match="Column 'quantity' does not exist or has no value."):
        CognitionDataProcessor.validate_column_values(data, schema)



@patch('kairon.shared.cognition.processor.MongoProcessor')
@patch('kairon.shared.cognition.processor.CognitionSchema')
def test_is_collection_limit_exceeded_for_mass_uploading_exceeded(mock_cognition_schema, mock_mongo_processor):
    bot = "test_bot"
    user = "test_user"
    collection_names = ["collection1", "collection2", "collection3"]

    mock_mongo_processor.get_bot_settings.return_value.to_mongo.return_value.to_dict.return_value = {
        "cognition_collections_limit": 5
    }
    mock_cognition_schema.objects.return_value.distinct.return_value = ["collection_a", "collection_b", "collection_c"]

    result = CognitionDataProcessor.is_collection_limit_exceeded_for_mass_uploading(bot, user, collection_names)
    assert result is True

@patch('kairon.shared.cognition.processor.MongoProcessor')
@patch('kairon.shared.cognition.processor.CognitionSchema')
def test_is_collection_limit_exceeded_for_mass_uploading_exceeded_overwrite(mock_cognition_schema, mock_mongo_processor):
    bot = "test_bot"
    user = "test_user"
    collection_names = ["collection1", "collection2", "collection3", "collection_4", "collection_5", "collection_6"]

    mock_mongo_processor.get_bot_settings.return_value.to_mongo.return_value.to_dict.return_value = {
        "cognition_collections_limit": 5
    }
    mock_cognition_schema.objects.return_value.distinct.return_value = ["collection_a", "collection_b", "collection_c"]

    result = CognitionDataProcessor.is_collection_limit_exceeded_for_mass_uploading(bot, user, collection_names, True)
    assert result is True

@patch('kairon.shared.cognition.processor.MongoProcessor')
@patch('kairon.shared.cognition.processor.CognitionSchema')
def test_is_collection_limit_exceeded_for_mass_uploading_not_exceeded_overwrite(mock_cognition_schema, mock_mongo_processor):
    bot = "test_bot"
    user = "test_user"
    collection_names = ["collection1", "collection2", "collection3", "collection_4"]

    mock_mongo_processor.get_bot_settings.return_value.to_mongo.return_value.to_dict.return_value = {
        "cognition_collections_limit": 5
    }
    mock_cognition_schema.objects.return_value.distinct.return_value = ["collection_a", "collection_b", "collection_c"]

    result = CognitionDataProcessor.is_collection_limit_exceeded_for_mass_uploading(bot, user, collection_names, True)
    assert result is False

@patch('kairon.shared.cognition.processor.MongoProcessor')
@patch('kairon.shared.cognition.processor.CognitionSchema')
def test_is_collection_limit_exceeded_for_mass_uploading_not_exceeded(mock_cognition_schema, mock_mongo_processor):
    bot = "test_bot"
    user = "test_user"
    collection_names = ["collection1", "collection2"]

    mock_mongo_processor.get_bot_settings.return_value.to_mongo.return_value.to_dict.return_value = {
        "cognition_collections_limit": 5
    }
    mock_cognition_schema.objects.return_value.distinct.return_value = ["collection1"]

    result = CognitionDataProcessor.is_collection_limit_exceeded_for_mass_uploading(bot, user, collection_names)
    assert result is False


@patch.object(MongoProcessor, '_MongoProcessor__save_cognition_schema')
@patch.object(MongoProcessor, '_MongoProcessor__save_cognition_data')
def test_save_bot_content(mock_save_cognition_data, mock_save_cognition_schema):
    bot_content = [
        {
            'collection': 'collection1',
            'type': 'json',
            'metadata': [
                {'column_name': 'column1', 'data_type': 'str', 'enable_search': True, 'create_embeddings': False}
            ],
            'data': [
                {'column1': 'value1'}
            ]
        }
    ]
    bot = 'test_bot'
    user = 'test_user'
    processor = MongoProcessor()

    processor.save_bot_content(bot_content, bot, user)

    mock_save_cognition_schema.assert_called_once_with(bot_content, bot, user)
    mock_save_cognition_data.assert_called_once_with(bot_content, bot, user)

@patch.object(MongoProcessor, '_MongoProcessor__save_cognition_schema')
@patch.object(MongoProcessor, '_MongoProcessor__save_cognition_data')
def test_save_bot_content_empty(mock_save_cognition_data, mock_save_cognition_schema):
    bot_content = []
    bot = 'test_bot'
    user = 'test_user'
    processor = MongoProcessor()

    processor.save_bot_content(bot_content, bot, user)

    mock_save_cognition_schema.assert_not_called()
    mock_save_cognition_data.assert_not_called()




@patch.object(MongoProcessor, 'data_format_correction_cognition_data')
@patch('kairon.shared.data.processor.CognitionSchema.objects')
@patch('kairon.shared.data.processor.CognitionData.objects')
def test_prepare_cognition_data_for_bot_json(mock_cognition_data_objects, mock_cognition_schema_objects, mock_data_format_correction):
    bot = 'test_bot'
    schema_result = MagicMock()
    schema_result.collection_name = 'collection1'
    schema_result.metadata = [
        MagicMock(column_name='column1', data_type='str', enable_search=True, create_embeddings=False)
    ]
    mock_cognition_schema_objects.return_value.only.return_value = [schema_result]

    data_result = MagicMock()
    data_result.data = {'column1': 'value1'}
    mock_cognition_data_objects.return_value.only.return_value = [data_result]

    mock_data_format_correction.return_value = [{'column1': 'value1'}]

    processor = MongoProcessor()

    processor._MongoProcessor__prepare_cognition_data_for_bot(bot)

    mock_data_format_correction.assert_called_once()


@patch.object(MongoProcessor, 'data_format_correction_cognition_data')
@patch('kairon.shared.data.processor.CognitionSchema.objects')
@patch('kairon.shared.data.processor.CognitionData.objects')
def test_prepare_cognition_data_for_bot_text_format_not_called(mock_cognition_data_objects, mock_cognition_schema_objects, mock_data_format_correction):
    bot = 'test_bot'
    schema_result = MagicMock()
    schema_result.collection_name = 'collection1'
    schema_result.metadata = []
    mock_cognition_schema_objects.return_value.only.return_value = [schema_result]

    data_result = MagicMock()
    data_result.data = 'text data'
    mock_cognition_data_objects.return_value.only.return_value = [data_result]

    processor = MongoProcessor()

    processor._MongoProcessor__prepare_cognition_data_for_bot(bot)

    mock_data_format_correction.assert_not_called()
