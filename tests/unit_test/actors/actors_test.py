import os
import re
import textwrap
from datetime import datetime
from unittest.mock import patch, MagicMock
from urllib.parse import urljoin

import litellm
import pytest
import responses
from mongoengine import connect

from kairon.exceptions import AppException
from kairon.shared.concurrency.actors.factory import ActorFactory
from kairon.shared.concurrency.orchestrator import ActorOrchestrator
from kairon.shared.constants import ActorType
from kairon.shared.concurrency.actors.utils import PyscriptUtility
from kairon.shared.admin.processor import Sysadmin
from kairon.shared.utils import Utility



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


def test_srtptime():
    date_string = "2025-03-26"
    formate = "%Y-%m-%d"
    expected_date = datetime(2025, 3, 26)

    with patch("datetime.datetime") as mock_datetime:
        mock_datetime.strptime.return_value = expected_date
        result = PyscriptUtility.srtptime(date_string, formate)

    assert result == expected_date


def test_srtftime():
    date_obj = datetime(2025, 3, 26)
    formate = "%Y-%m-%d"
    expected_string = "2025-03-26"

    result = PyscriptUtility.srtftime(date_obj, formate)

    assert result == expected_string


def test_url_parse_quote_plus():
    input_string = "hello world!"
    expected_output = "hello+world%21"

    with patch("urllib.parse.quote_plus", return_value=expected_output) as mock_quote_plus:
        result = PyscriptUtility.url_parse_quote_plus(input_string)

    assert result == expected_output
    mock_quote_plus.assert_called_once_with(input_string, '', None, None)


def test_get_embedding():
    texts = ["Hello world!"]
    user = "test_user"
    bot = "test_bot"
    invocation = "test_invocation"
    mock_api_key = "mocked_api_key"
    mock_embedding_result = {"data": [{"embedding": [0.1, 0.2, 0.3]}]}

    with patch("tiktoken.get_encoding") as mock_get_encoding, \
         patch.object(Sysadmin, "get_llm_secret", return_value={"api_key": mock_api_key}) as mock_get_llm_secret, \
         patch("litellm.embedding", return_value=mock_embedding_result) as mock_litellm:

        mock_tokenizer = MagicMock()
        mock_tokenizer.encode.return_value = [1, 2, 3]
        mock_tokenizer.decode.return_value = texts[0]
        mock_get_encoding.return_value = mock_tokenizer

        result = PyscriptUtility.get_embedding(texts, user, bot, invocation)
        assert result == [[0.1, 0.2, 0.3]]


def test_perform_operation():
    data = {"embedding_search": "test message", "payload_search": {"filter": "some_filter"}}
    user = "test_user"
    kwargs = {"collection_name": "test_collection"}
    mock_vector_db_url = "http://mocked-vector-db.com"
    mock_embedding = [0.1, 0.2, 0.3]
    mock_response_data = {"result": "success"}

    with patch.dict(Utility.environment, {"vector": {"db": mock_vector_db_url}}), \
            patch.object(PyscriptUtility, "get_embedding", return_value=mock_embedding) as mock_get_embedding, \
            patch("requests.post") as mock_post:
        mock_post.return_value.json.return_value = mock_response_data

        result = PyscriptUtility.perform_operation(data, user, **kwargs)

        expected_url = urljoin(mock_vector_db_url, f"/collections/{kwargs['collection_name']}/points/scroll")
        expected_request = {
            "query": mock_embedding,
            "filter": "some_filter",
            "with_payload": True,
            "limit": 10
        }
        mock_get_embedding.assert_called_once_with("test message", user, invocation='db_action_qdrant')
        mock_post.assert_called_once_with(expected_url, json=expected_request)
        assert result == mock_response_data


def test_perform_operation_embedding_search():
    mock_vector_db_url = 'http://localhost:6333'
    mock_embedding = [0.1, 0.2, 0.3]
    mock_response_data = {"mocked": "response"}

    data = {"embedding_search": "test query"}
    user = "test_user"
    kwargs = {"collection_name": "test_collection"}

    with patch.object(PyscriptUtility, "get_embedding", return_value=mock_embedding) as mock_get_embedding, \
         patch("requests.post") as mock_post:

        mock_post.return_value.json.return_value = mock_response_data

        # Directly pass the URL instead of using Utility.environment
        result = PyscriptUtility.perform_operation(data, user, vector_db_url=mock_vector_db_url, **kwargs)

        expected_url = urljoin(mock_vector_db_url, f"/collections/{kwargs['collection_name']}/points/scroll")
        expected_request = {
            "query": mock_embedding,
            "with_payload": True,
            "limit": 10
        }

        mock_get_embedding.assert_called_once_with('test query', 'test_user', invocation='db_action_qdrant', vector_db_url=mock_vector_db_url)
        mock_post.assert_called_once_with(expected_url, json=expected_request)
        assert result == mock_response_data

def test_perform_operation_payload_search():
    mock_vector_db_url = 'http://localhost:6333'
    mock_response_data = {"mocked": "response"}

    data = {"payload_search": {"filter": {"field": "value"}}}
    user = "test_user"
    kwargs = {"collection_name": "test_collection"}

    with patch("requests.post") as mock_post:
        mock_post.return_value.json.return_value = mock_response_data

        # Directly pass the URL instead of using Utility.environment
        result = PyscriptUtility.perform_operation(data, user, vector_db_url=mock_vector_db_url, **kwargs)

        expected_url = urljoin(mock_vector_db_url, f"/collections/{kwargs['collection_name']}/points/scroll")
        expected_request = {
            "filter": {"field": "value"},
            "with_payload": True,
            "limit": 10
        }

        mock_post.assert_called_once_with(expected_url, json=expected_request)
        assert result == mock_response_data

def test_perform_operation_no_operation():
    data = {}  # No valid search parameters
    user = "test_user"
    kwargs = {"collection_name": "test_collection"}

    with pytest.raises(Exception) as context:
        PyscriptUtility.perform_operation(data, user, **kwargs)
    assert str(context.value) == "No Operation to perform"
