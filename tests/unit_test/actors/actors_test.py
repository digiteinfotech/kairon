import os
import re
import textwrap

import pytest
import responses
from mongoengine import connect

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
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))

    def test_actor_pyrunner(self):
        script = """
        data = [1, 2, 3, 4, 5]
        total = 0
        for i in data:
            total += i
        print(total)
        """
        script = textwrap.dedent(script)
        result = ActorOrchestrator.run(ActorType.pyscript_runner, source_code=script, predefined_objects={"slot": {}},
                                       timeout=10)
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
        result = ActorOrchestrator.run(ActorType.pyscript_runner, source_code=script,
                                       predefined_objects={"requests": requests, "json": json, "slot": {}}, timeout=10)
        assert not result.get("requests")
        assert not result.get('json')
        assert result["response"]
        assert result["value"] == {"data": "kairon", "message": "OK"}
        assert result["data"] == "kairon"

    @responses.activate
    def test_actor_pyrunner_with_api_call_function(self):
        from kairon.shared.actions.data_objects import HttpActionConfig, HttpActionResponse

        HttpActionConfig(
            action_name="action_trigger_sell_produce_flow",
            content_type="json",
            response=HttpActionResponse(
                value="bot_response = Successful",
                dispatch=True, evaluation_type="script", dispatch_type="text"),
            http_url="https://waba-v2.360dialog.io/messages",
            request_method="POST",
            dynamic_params=
            "body = {'sender_id': sender_id, 'user_message': user_message, 'intent': intent}",
            bot="5f50fd0a56b698ca10d35d2e",
            user="user"
        ).save()

        source_code = """
            payload = {
              "recipient_type": "individual",
              "messaging_product": "whatsapp",
              "to": "919515991685",
              "type": "interactive",
              "interactive": {
                "type": "flow",
                "header": {
                  "type": "text",
                  "text": "User Details"
                },
                "body": {
                  "text": "Please Fill Your Details"
                },
                "action": {
                  "name": "flow",
                  "parameters": {
                      "mode": "draft",
                    "flow_message_version": "3",
                    "flow_token": "AQAAAAACS5FpgQ_cAAAAAD0QI3s.",
                    "flow_id": "996862885548613",
                    "flow_cta": "Register",
                    "flow_action": "navigate",
                    "flow_action_payload": {
                      "screen": "FOOD"
                    }
                  }
                }
              }
            }
            headers = {"D360-API-KEY" : "abcdcffdfdv1tsh9qlr9Oul5AK"}
            # headers = {}
            sender_id = "919876543210"
            resp = api_call("action_trigger_sell_produce_flow", sender_id, payload, headers)
            bot_response = resp
            """
        script = textwrap.dedent(source_code)

        responses.add(
            "POST", "https://waba-v2.360dialog.io/messages",
            json={
                "messaging_product": "whatsapp",
                "contacts": [
                    {
                        "input": "919876543210",
                        "wa_id": "919876543210"
                    }
                ],
                "messages": [
                    {
                        "id": "wamid.HBgMOTE5NTE1abcdcffdfdv1tsh9qlr9Oul5AKRkE0MzBCNTI3AA==",
                        "message_status": "accepted"
                    }
                ]
            }
        )
        result = ActorOrchestrator.run(ActorType.pyscript_runner, source_code=script,
                                       predefined_objects={"slot": {"bot": "5f50fd0a56b698ca10d35d2e"}}, timeout=10)
        print(result)
        assert result["resp"] == {
            'messaging_product': 'whatsapp',
            'contacts': [
                {
                    'input': '919876543210',
                    'wa_id': '919876543210'
                }
            ],
            'messages': [
                {
                    'id': 'wamid.HBgMOTE5NTE1abcdcffdfdv1tsh9qlr9Oul5AKRkE0MzBCNTI3AA==',
                    'message_status': 'accepted'
                }
            ]
        }
        assert result["headers"] == {'D360-API-KEY': 'abcdcffdfdv1tsh9qlr9Oul5AK'}
        assert result["bot_response"] == {
            'messaging_product': 'whatsapp',
            'contacts': [
                {
                    'input': '919876543210',
                    'wa_id': '919876543210'
                }
            ],
            'messages': [
                {
                    'id': 'wamid.HBgMOTE5NTE1abcdcffdfdv1tsh9qlr9Oul5AKRkE0MzBCNTI3AA==',
                    'message_status': 'accepted'
                }
            ]
        }

    @responses.activate
    def test_actor_pyrunner_with_get_db_action_data_function(self):
        from kairon.shared.actions.data_objects import DatabaseAction, DbQuery, HttpActionResponse
        DatabaseAction(
            name="retrieve_pop_content",
            collection='5f50fd0a56b698ca10d35d2e_crop_production_support_faq_embd',
            payload=[DbQuery(query_type="payload_search",
                             type="from_slot",
                             value="search")],
            response=HttpActionResponse(value="Action Successful"),
            bot="5f50fd0a56b698ca10d35d2e",
            user="user"
        ).save()

        source_code = """
            payload = {
                "filter": {
                    "must": [
                        {
                            "key": "crop",
                            "match": {
                                "text": "टमाटर"
                            }
                        },
                        {
                            "key": "category",
                            "match": {
                                "text": "भूमि की तैयारी"
                            }
                        },
                        {
                            "key": "stage",
                            "match": {
                                "text": "रोपण पूर्व"
                            }
                        }
                    ]
                },
                "limit": 25,
                "with_payload": True,
                "with_vector": False
            }
            sender_id = "919876543210"
            resp = get_db_action_data("retrieve_pop_content", sender_id, payload)
    
            bot_response = resp
            """
        script = textwrap.dedent(source_code)
        mock_response = {
            'result': {
                'points': [
                    {
                        'id': 7,
                        'payload': {
                            'activity': '*ट्राइकोडर्मा का प्रयोग:*\n\n- *प्रयोग दर:* अपनी {size} डिसमिल खेत के लिए {quantity} किलोग्राम\n- *विधि:* इसे गोबर की खाद के साथ मिलाकर मिट्टी में लगाएं\n',
                            'application': '0.02', 'attachment': 'n/a', 'category': 'भूमि की तैयारी', 'crop': 'टमाटर',
                            'mapping': 'Tomato -> Land Preparation -> Pre Planting -> Trichoderma Application',
                            'stage': 'रोपण पूर्व'
                        }
                    }
                ],
                'next_page_offset': None
            },
            'status': 'ok',
            'time': 0.000922177
        }

        responses.add(
            "POST",
            "http://localhost:6333/collections/5f50fd0a56b698ca10d35d2e_5f50fd0a56b698ca10d35d2e_crop_production_support_faq_embd_faq_embd/points/scroll",
            json=mock_response
        )
        result = ActorOrchestrator.run(ActorType.pyscript_runner, source_code=script,
                                       predefined_objects={"slot": {"bot": "5f50fd0a56b698ca10d35d2e"}}, timeout=10)
        print(result)
        assert result["resp"] == mock_response
        assert result["bot_response"] == mock_response

    def test_actor_pyrunner_with_script_errors(self):
        script = """
            import numpy as np
            arr = np.array([1, 2, 3, 4, 5])
            mean_value = np.mean(arr)
            print("Mean:", mean_value)
            """
        script = textwrap.dedent(script)

        with pytest.raises(AppException, match="Script execution error: import of 'numpy' is unauthorized"):
            ActorOrchestrator.run(ActorType.pyscript_runner, source_code=script,
                                  predefined_objects={"slot": {}}, timeout=10)

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
            ActorOrchestrator.run(ActorType.pyscript_runner, source_code=script,
                                  predefined_objects={"slot": {}}, timeout=10)

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
