import os
import re
import textwrap

import pytest
import responses
from RestrictedPython import PrintCollector

from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.concurrency.actors.factory import ActorFactory
from kairon.shared.concurrency.orchestrator import ActorOrchestrator
from kairon.shared.constants import ActorType


class TestActors:

    @pytest.fixture(autouse=True, scope='class')
    def setup(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()

    def test_actor_pyrunner(self):
        script = """
        data = [1, 2, 3, 4, 5]
        total = 0
        for i in data:
            total += i
        print(total)
        """
        script = textwrap.dedent(script)
        result = ActorOrchestrator.run(ActorType.pyscript_runner, source_code=script, timeout=10)
        assert not result.get('_print')
        assert result["data"] == [1, 2, 3, 4, 5]
        assert result['total'] == 15

    @responses.activate
    def test_actor_pyrunner_with_predefined_objects(self):
        import requests, json

        script = """
        response = requests.get('http://localhos')
        value = response.json()
        data = value['data']
        """
        script = textwrap.dedent(script)

        responses.add(
            "GET", "http://localhos", json={"data": "kairon", "message": "OK"}
        )
        result = ActorOrchestrator.run(ActorType.pyscript_runner, source_code=script, predefined_objects={"requests": requests, "json": json}, timeout=10)
        assert not result.get("requests")
        assert not result.get('json')
        assert result["response"]
        assert result["value"] == {"data": "kairon", "message": "OK"}
        assert result["data"] == "kairon"

    def test_actor_pyrunner_with_script_errors(self):
        script = """
            import numpy as np
            arr = np.array([1, 2, 3, 4, 5])
            mean_value = np.mean(arr)
            print("Mean:", mean_value)
            """
        script = textwrap.dedent(script)

        with pytest.raises(AppException, match="Script execution error: import of 'numpy' is unauthorized"):
            ActorOrchestrator.run(ActorType.pyscript_runner, source_code=script, timeout=10)

    def test_actor_pyrunner_with_timeout(self):
        import time
        import pykka

        script = """
            time.sleep(3) 
            """
        script = textwrap.dedent(script)

        with pytest.raises(AppException, match="Operation timed out: 1 seconds"):
            ActorOrchestrator.run(ActorType.pyscript_runner, source_code=script, predefined_objects={"time": time}, timeout=1)

    def test_actor_pyrunner_with_interpreter_error(self):
        script = """
            for i in 10
            """
        script = textwrap.dedent(script)

        with pytest.raises(AppException, match=re.escape('Script execution error: ("Line 2: SyntaxError: expected \':\' at statement: \'for i in 10\'",)')):
            ActorOrchestrator.run(ActorType.pyscript_runner, source_code=script, timeout=10)

    def test_invalid_actor(self):
        with pytest.raises(AppException, match="custom actor not implemented!"):
            ActorOrchestrator.run("custom")

    def test_actor_callable(self):
        def add(a, b):
            return a + b

        value = ActorOrchestrator.run(ActorType.callable_runner, add, a=1, b=4)
        assert value == 5

    def test_actor_async_callable(self):
        async def add(a, b):
            return a + b

        value = ActorOrchestrator.run(ActorType.callable_runner, add, a=1, b=4)
        assert value == 5

    def test_actor_callable_failure(self):
        def add(a, b):
            raise Exception("Failed to perform operation!")

        with pytest.raises(Exception, match="Failed to perform operation!"):
            ActorOrchestrator.run(ActorType.callable_runner, add, a=1, b=4)

    def test_actor_async_callable_failure(self):
        async def add(a, b):
            raise Exception("Failed to perform operation!")

        with pytest.raises(Exception, match="Failed to perform operation!"):
            ActorOrchestrator.run(ActorType.callable_runner, add, a=1, b=4)

    def test_actor_dead(self):
        def add(a, b):
            return a + b

        actor_proxy = ActorFactory._ActorFactory__actors[ActorType.callable_runner.value][1]
        actor_proxy.stop()

        value = ActorOrchestrator.run(ActorType.callable_runner, add, a=1, b=4)
        assert value == 5
