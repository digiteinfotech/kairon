import re
import textwrap

import pytest
import responses
from RestrictedPython import PrintCollector
from pykka import ThreadingFuture

from kairon.exceptions import AppException
from kairon.shared.actors.factory import ActorFactory
from kairon.shared.constants import ActorTypes


class TestActors:

    def test_actor_pyrunner(self):
        script = """
        data = [1, 2, 3, 4, 5]
        total = 0
        for i in data:
            total += i
        print(total)
        """
        script = textwrap.dedent(script)
        result = ActorFactory.get_instance(ActorTypes.pyscript_runner).execute(script)
        assert isinstance(result, ThreadingFuture)
        actual = result.get()
        result.set()
        assert isinstance(actual['_print'], PrintCollector)
        assert actual["data"] == [1, 2, 3, 4, 5]
        assert actual['total'] == 15

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
        result = ActorFactory.get_instance(ActorTypes.pyscript_runner).execute(script, {"requests": requests, "json": json})
        assert isinstance(result, ThreadingFuture)
        actual = result.get()
        result.join()
        assert actual["requests"]
        assert actual['json']
        assert actual["response"]
        assert actual["value"] == {"data": "kairon", "message": "OK"}
        assert actual["data"] == "kairon"

    def test_actor_pyrunner_with_script_errors(self):
        script = """
            import requests
            response = requests.get('http://localhos')
            value = response.json()
            data = value['data']
            """
        script = textwrap.dedent(script)

        result = ActorFactory.get_instance(ActorTypes.pyscript_runner).execute(script)
        assert isinstance(result, ThreadingFuture)

        with pytest.raises(AppException, match="Script execution error: import of 'requests' is unauthorized"):
            result.get()

    def test_actor_pyrunner_with_timeout(self):
        import time
        import pykka

        script = """
            time.sleep(3) 
            """
        script = textwrap.dedent(script)

        result = ActorFactory.get_instance(ActorTypes.pyscript_runner).execute(script, {"time": time})
        assert isinstance(result, ThreadingFuture)

        with pytest.raises(pykka._exceptions.Timeout):
            result.get(timeout=1)

    def test_actor_pyrunner_with_interpreter_error(self):
        script = """
            for i in 10
            """
        script = textwrap.dedent(script)
        result = ActorFactory.get_instance(ActorTypes.pyscript_runner).execute(script)

        with pytest.raises(AppException, match=re.escape('Script execution error: ("Line 2: SyntaxError: invalid syntax at statement: \'for i in 10\'",)')):
            result.get()
