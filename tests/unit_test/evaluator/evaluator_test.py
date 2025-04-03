import os
import re
import textwrap

import pytest
from mongoengine import connect

from kairon import Utility
from kairon.evaluator.processor import EvaluatorProcessor
from kairon.exceptions import AppException


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
        response = EvaluatorProcessor.evaluate_pyscript(source_code=script, predefined_objects={"slot": {}})
        assert response["data"] == [1, 2, 3, 4, 5]
        assert response['total'] == 15

    def test_evaluate_pyscript_with_predefined_objects(self):
        script = """
        data = [1, 2, 3, 4, 5]
        total = 0
        for i in data:
            total += i
        print(total)
        """
        predefined_objects = {'sender_id': 'default', 'user_message': 'get intents',
                              'slot': {"bot": "5f50fd0a56b698ca10d35d2e", "location": "Bangalore",
                                       "langauge": "Kannada"}}
        script = textwrap.dedent(script)
        response = EvaluatorProcessor.evaluate_pyscript(source_code=script,
                                                        predefined_objects=predefined_objects)
        assert response["data"] == [1, 2, 3, 4, 5]
        assert response['total'] == 15

    def test_evaluate_pyscript_with_script_errors(self):
        script = """
            import numpy as np
            arr = np.array([1, 2, 3, 4, 5])
            mean_value = np.mean(arr)
            print("Mean:", mean_value)
            """
        script = textwrap.dedent(script)
        with pytest.raises(AppException, match="Script execution error: import of 'numpy' is unauthorized"):
            EvaluatorProcessor.evaluate_pyscript(source_code=script, predefined_objects={"slot": {}})

    def test_evaluate_pyscript_with_interpreter_error(self):
        script = """
        for i in 10
        """
        script = textwrap.dedent(script)
        with pytest.raises(AppException, match=re.escape('Script execution error: ("Line 2: SyntaxError: expected \':\' at statement: \'for i in 10\'",)')):
            EvaluatorProcessor.evaluate_pyscript(source_code=script, predefined_objects={"slot": {}})
