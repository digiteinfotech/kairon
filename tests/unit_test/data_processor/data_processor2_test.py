import os
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
