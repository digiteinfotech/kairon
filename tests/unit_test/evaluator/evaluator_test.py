import os
import textwrap

import pytest
from mongoengine import connect

from kairon import Utility
from kairon.evaluator.processor import EvaluatorProcessor


class TestEvaluatorProcessor:

    @pytest.fixture(autouse=True, scope='class')
    def init_connection(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        connect(**Utility.mongoengine_connection())

    def test_evaluate_pyscript(self):
        script = """
        data = [1, 2, 3, 4, 5]
        total = 0
        for i in data:
            total += i
        print(total)
        """
        script = textwrap.dedent(script)
        response, message = EvaluatorProcessor.evaluate_pyscript(source_code=script)
        assert response["data"] == [1, 2, 3, 4, 5]
        assert response['total'] == 15
        assert not message

    def test_evaluate_pyscript_with_script_errors(self):
        script = """
        import requests
        response = requests.get('http://localhost')
        value = response.json()
        data = value['data']
        """
        script = textwrap.dedent(script)
        response, message = EvaluatorProcessor.evaluate_pyscript(source_code=script)
        assert not response
        assert message == "Script execution error: import of 'requests' is unauthorized"

    def test_evaluate_pyscript_with_interpreter_error(self):
        script = """
        for i in 10
        """
        script = textwrap.dedent(script)
        response, message = EvaluatorProcessor.evaluate_pyscript(source_code=script)
        assert not response
        assert message == 'Script execution error: ("Line 2: SyntaxError: invalid syntax at statement: \'for i in 10\'",)'
