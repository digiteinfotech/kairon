import os

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
