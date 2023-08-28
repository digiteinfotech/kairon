import os
import textwrap

import pytest
from mongoengine import connect

from kairon import Utility
from fastapi.testclient import TestClient

from kairon.evaluator.main import app


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
    assert not actual['message']
    assert actual['data']['data'] == [1, 2, 3, 4, 5]
    assert actual['data']['total'] == 15


def test_evaluate_pyscript_with_script_errors():
    script = """
    import requests
    response = requests.get('http://localhost')
    value = response.json()
    data = value['data']
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
    assert not actual['data']
    assert actual['message'] == "Script execution error: import of 'requests' is unauthorized"


def test_evaluate_pyscript_with_interpreter_error():
    script = """
    for i in 10
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
    assert not actual['data']
    assert actual['message'] == 'Script execution error: ("Line 2: SyntaxError: invalid syntax at statement: \'for i in 10\'",)'
