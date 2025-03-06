import os
import textwrap

import pytest
from unittest.mock import patch
from mongoengine import connect

from kairon import Utility
from fastapi.testclient import TestClient

from kairon.evaluator.main import app
from kairon.evaluator.processor import EvaluatorProcessor

client = TestClient(app)


@pytest.fixture(autouse=True, scope='class')
def setup():
    os.environ["system_file"] = "./tests/testing_data/system.yaml"
    Utility.load_environment()
    connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))


def test_index():
    response = client.get("/")
    actual = response.json()
    assert actual['success']
    assert actual['message'] == "Running Evaluator Server"
    assert not actual['data']


@patch.object(EvaluatorProcessor, 'evaluate_pyscript')
def test_run_pyscript_with_assertion_error(mock_evaluate_pyscript):
    script = """
    data = [1, 2, 3, 4, 5]
    total = 0
    for i in data:
        total += i
    print(total)
    """
    mock_evaluate_pyscript.side_effect = AssertionError("Assertion error")
    response = client.post("/evaluate", json={"source_code": script})
    actual = response.json()
    assert actual == {'success': False, 'message': 'Assertion error', 'data': None, 'error_code': 422}


@patch.object(EvaluatorProcessor, 'evaluate_pyscript')
def test_run_pyscript_with_app_does_not_exist_exception(mock_evaluate_pyscript):
    from mongoengine.errors import DoesNotExist

    script = """
    data = [1, 2, 3, 4, 5]
    total = 0
    for i in data:
        total += i
    print(total)
    """
    mock_evaluate_pyscript.side_effect = DoesNotExist("The requested item does not exist")
    response = client.post("/evaluate", json={"source_code": script})
    actual = response.json()
    assert actual == {'success': False, 'message': 'The requested item does not exist', 'data': None, 'error_code': 422}


@patch.object(EvaluatorProcessor, 'evaluate_pyscript')
def test_run_pyscript_with_pymongo_exception(mock_evaluate_pyscript):
    from pymongo.errors import PyMongoError

    script = """
    data = [1, 2, 3, 4, 5]
    total = 0
    for i in data:
        total += i
    print(total)
    """
    mock_evaluate_pyscript.side_effect = PyMongoError("An error occurred while processing the database request. "
                                                      "Please try again later or contact support for assistance.")
    response = client.post("/evaluate", json={"source_code": script})
    actual = response.json()
    assert actual == {'success': False, 'message': 'An error occurred while processing the database request. '
                                                   'Please try again later or contact support for assistance.',
                      'data': None, 'error_code': 422}


@patch.object(EvaluatorProcessor, 'evaluate_pyscript')
def test_run_pyscript_with_app_validation_exception(mock_evaluate_pyscript):
    from mongoengine.errors import ValidationError

    script = """
    data = [1, 2, 3, 4, 5]
    total = 0
    for i in data:
        total += i
    print(total)
    """
    mock_evaluate_pyscript.side_effect = ValidationError("Validation failed. "
                                                         "Please check your input data for errors and try again.")
    response = client.post("/evaluate", json={"source_code": script})
    actual = response.json()
    assert actual == {'success': False, 'message': 'Validation failed. '
                                                   'Please check your input data for errors and try again.',
                      'data': None, 'error_code': 422}


@patch.object(EvaluatorProcessor, 'evaluate_pyscript')
def test_run_pyscript_with_mongoengine_operation_exception(mock_evaluate_pyscript):
    from mongoengine.errors import OperationError

    script = """
    data = [1, 2, 3, 4, 5]
    total = 0
    for i in data:
        total += i
    print(total)
    """
    mock_evaluate_pyscript.side_effect = OperationError("An error occurred while processing the operation. "
                                                        "Please try again later or contact support for assistance.")
    response = client.post("/evaluate", json={"source_code": script})
    actual = response.json()
    assert actual == {'success': False, 'message': 'An error occurred while processing the operation. '
                                                   'Please try again later or contact support for assistance.',
                      'data': None, 'error_code': 422}


@patch.object(EvaluatorProcessor, 'evaluate_pyscript')
def test_run_pyscript_with_mongoengine_not_registered_exception(mock_evaluate_pyscript):
    from mongoengine.errors import NotRegistered

    script = """
    data = [1, 2, 3, 4, 5]
    total = 0
    for i in data:
        total += i
    print(total)
    """
    mock_evaluate_pyscript.side_effect = NotRegistered("An unexpected error occurred. The requested resource "
                                                       "or operation is not registered or supported.")
    response = client.post("/evaluate", json={"source_code": script})
    actual = response.json()
    assert actual == {'success': False, 'message': 'An unexpected error occurred. The requested resource or '
                                                   'operation is not registered or supported.',
                      'data': None, 'error_code': 422}


@patch.object(EvaluatorProcessor, 'evaluate_pyscript')
def test_run_pyscript_with_mongoengine_invalid_document_exception(mock_evaluate_pyscript):
    from mongoengine.errors import InvalidDocumentError

    script = """
    data = [1, 2, 3, 4, 5]
    total = 0
    for i in data:
        total += i
    print(total)
    """
    mock_evaluate_pyscript.side_effect = InvalidDocumentError("The submitted data is invalid. "
                                                              "Please review your input and ensure it meets "
                                                              "the required format and constraints.")
    response = client.post("/evaluate", json={"source_code": script})
    actual = response.json()
    assert actual == {'success': False, 'message': 'The submitted data is invalid. Please review your input and '
                                                   'ensure it meets the required format and constraints.',
                      'data': None, 'error_code': 422}


@patch.object(EvaluatorProcessor, 'evaluate_pyscript')
def test_run_pyscript_with_mongoengine_lookup_exception(mock_evaluate_pyscript):
    from mongoengine.errors import LookUpError

    script = """
    data = [1, 2, 3, 4, 5]
    total = 0
    for i in data:
        total += i
    print(total)
    """
    mock_evaluate_pyscript.side_effect = LookUpError("An unexpected data lookup error occurred.")
    predefined_objects = {'sender_id': 'default', 'user_message': 'get intents',
                          'slot': {"bot": "5f50fd0a56b698ca10d35d2e", "location": "Bangalore", "langauge": "Kannada"}}
    response = client.post("/evaluate", json={"source_code": script, "predefined_objects": predefined_objects})
    actual = response.json()
    assert actual == {'success': False, 'message': 'An unexpected data lookup error occurred.',
                      'data': None, 'error_code': 422}


@patch.object(EvaluatorProcessor, 'evaluate_pyscript')
def test_run_pyscript_with_mongoengine_multiple_objects_exception(mock_evaluate_pyscript):
    from mongoengine.errors import MultipleObjectsReturned

    script = """
    data = [1, 2, 3, 4, 5]
    total = 0
    for i in data:
        total += i
    print(total)
    """
    mock_evaluate_pyscript.side_effect = MultipleObjectsReturned(
        "Multiple matching records found when only one was expected.")
    predefined_objects = {'sender_id': 'default', 'user_message': 'get intents',
                          'slot': {"bot": "5f50fd0a56b698ca10d35d2e", "location": "Bangalore", "langauge": "Kannada"}}
    response = client.post("/evaluate", json={"source_code": script, "predefined_objects": predefined_objects})
    actual = response.json()
    assert actual == {'success': False, 'message': 'Multiple matching records found when only one was expected.',
                      'data': None, 'error_code': 422}


@patch.object(EvaluatorProcessor, 'evaluate_pyscript')
def test_run_pyscript_with_mongoengine_invalid_query_exception(mock_evaluate_pyscript):
    from mongoengine.errors import InvalidQueryError

    script = """
    data = [1, 2, 3, 4, 5]
    total = 0
    for i in data:
        total += i
    print(total)
    """
    mock_evaluate_pyscript.side_effect = InvalidQueryError(
        "Invalid query error occurred while processing the request.")
    predefined_objects = {'sender_id': 'default', 'user_message': 'get intents',
                          'slot': {"bot": "5f50fd0a56b698ca10d35d2e", "location": "Bangalore", "langauge": "Kannada"}}
    response = client.post("/evaluate", json={"source_code": script, "predefined_objects": predefined_objects})
    actual = response.json()
    assert actual == {'success': False, 'message': 'Invalid query error occurred while processing the request.',
                      'data': None, 'error_code': 422}


@patch.object(EvaluatorProcessor, 'evaluate_pyscript')
def test_run_pyscript_with_app_exception(mock_evaluate_pyscript):
    from kairon.exceptions import AppException

    script = """
    data = [1, 2, 3, 4, 5]
    total = 0
    for i in data:
        total += i
    print(total)
    """
    mock_evaluate_pyscript.side_effect = AppException("Failed to execute the URL")
    predefined_objects = {'sender_id': 'default', 'user_message': 'get intents',
                          'slot': {"bot": "5f50fd0a56b698ca10d35d2e", "location": "Bangalore", "langauge": "Kannada"}}
    response = client.post("/evaluate", json={"source_code": script, "predefined_objects": predefined_objects})
    actual = response.json()
    assert actual == {'success': False, 'message': 'Failed to execute the URL', 'data': None, 'error_code': 422}


def test_run_pyscript_with_source_code_empty():
    predefined_objects = {'sender_id': 'default', 'user_message': 'get intents',
                          'slot': {"bot": "5f50fd0a56b698ca10d35d2e", "location": "Bangalore", "langauge": "Kannada"}}
    request_body = {
        "source_code": "",
        "predefined_objects": predefined_objects
    }
    response = client.post(
        url=f"/evaluate",
        json=request_body
    )
    actual = response.json()
    assert response.status_code == 422
    assert actual == {
        'detail': [{'loc': ['body', 'source_code'], 'msg': 'source_code is required', 'type': 'value_error'}]}


def test_run_pyscript_with_source_code_none():
    predefined_objects = {'sender_id': 'default', 'user_message': 'get intents',
                          'slot': {"bot": "5f50fd0a56b698ca10d35d2e", "location": "Bangalore", "langauge": "Kannada"}}
    request_body = {
        "source_code": None,
        "predefined_objects": predefined_objects
    }
    response = client.post(
        url=f"/evaluate",
        json=request_body
    )
    actual = response.json()
    assert response.status_code == 422
    assert actual == {
        'detail': [{'loc': ['body', 'source_code'],
                    'msg': 'none is not an allowed value', 'type': 'type_error.none.not_allowed'}]}


def test_run_pyscript():
    script = """
    data = [1, 2, 3, 4, 5]
    total = 0
    for i in data:
        total += i
    print(total)
    """
    script = textwrap.dedent(script)
    request_body = {
        "source_code": script,
    }
    response = client.post(
        url=f"/evaluate",
        json=request_body
    )
    actual = response.json()
    assert actual['success']
    assert actual['error_code'] == 0
    assert not actual['message']
    assert actual['data']['data'] == [1, 2, 3, 4, 5]
    assert actual['data']['total'] == 15


def test_run_pyscript_with_predefined_objects():
    script = """
    data = [1, 2, 3, 4, 5]
    total = 0
    for i in data:
        total += i
    print(total)
    """
    script = textwrap.dedent(script)
    predefined_objects = {'sender_id': 'default', 'user_message': 'get intents',
                          'slot': {"bot": "5f50fd0a56b698ca10d35d2e", "location": "Bangalore", "langauge": "Kannada"}}
    request_body = {
        "source_code": script,
        "predefined_objects": predefined_objects
    }
    response = client.post(
        url=f"/evaluate",
        json=request_body
    )
    actual = response.json()
    assert actual['success']
    assert actual['error_code'] == 0
    assert not actual['message']
    assert actual['data']['data'] == [1, 2, 3, 4, 5]
    assert actual['data']['total'] == 15


def test_run_pyscript_with_script_errors():
    script = """
        import numpy as np
        arr = np.array([1, 2, 3, 4, 5])
        mean_value = np.mean(arr)
        print("Mean:", mean_value)
        """
    script = textwrap.dedent(script)
    predefined_objects = {'sender_id': 'default', 'user_message': 'get intents',
                          'slot': {"bot": "5f50fd0a56b698ca10d35d2e", "location": "Bangalore", "langauge": "Kannada"}}
    request_body = {
        "source_code": script,
        "predefined_objects": predefined_objects
    }
    response = client.post(
        url=f"/evaluate",
        json=request_body
    )
    actual = response.json()
    assert not actual['success']
    assert actual['error_code'] == 422
    assert not actual['data']
    assert actual['message'] == "Script execution error: import of 'numpy' is unauthorized"


def test_run_pyscript_with_interpreter_error():
    script = """
    for i in 10
    """
    script = textwrap.dedent(script)
    predefined_objects = {'sender_id': 'default', 'user_message': 'get intents',
                          'slot': {"bot": "5f50fd0a56b698ca10d35d2e", "location": "Bangalore", "langauge": "Kannada"}}
    request_body = {
        "source_code": script,
        "predefined_objects": predefined_objects
    }
    response = client.post(
        url=f"/evaluate",
        json=request_body
    )
    actual = response.json()
    assert not actual['success']
    assert actual['error_code'] == 422
    assert not actual['data']
    assert actual['message'] == 'Script execution error: ("Line 2: SyntaxError: expected \':\' at statement: \'for i in 10\'",)'
