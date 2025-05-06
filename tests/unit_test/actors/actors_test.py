import os
import re
import textwrap
from datetime import datetime
from unittest.mock import patch, MagicMock
from urllib.parse import urljoin

import litellm
import pytest
import requests
import responses
from mongoengine import connect
from orjson import orjson

from kairon.exceptions import AppException
from kairon.shared.actions.data_objects import DatabaseAction, HttpActionConfig
from kairon.shared.actions.utils import ActionUtility
from kairon.shared.concurrency.actors.factory import ActorFactory
from kairon.shared.concurrency.actors.pyscript_runner import PyScriptRunner
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
            ActorOrchestrator.run(ActorType.pyscript_runner, source_code=script, predefined_objects={"time": time},
                                  timeout=1)

    def test_actor_pyrunner_with_interpreter_error(self):
        script = """
            for i in 10
            """
        script = textwrap.dedent(script)

        with pytest.raises(AppException, match=re.escape(
                'Script execution error: ("Line 2: SyntaxError: expected \':\' at statement: \'for i in 10\'",)')):
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

        mock_get_embedding.assert_called_once_with('test query', 'test_user', invocation='db_action_qdrant',
                                                   vector_db_url=mock_vector_db_url)
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


def test_get_db_action_data():
    action_name = "test_action"
    user = "test_user"
    payload_dict = {"key": "value"}
    bot = "test_bot"
    predefined_objects = {}
    mock_response_data = {"mocked": "response"}
    mock_db_action_config = {
        "collection": "test_collection",
        "payload": [{"query_type": "test_query_type"}]
    }

    with patch.object(DatabaseAction, "objects") as mock_objects, \
            patch.object(PyscriptUtility, "get_payload", return_value=payload_dict) as mock_get_payload, \
            patch.object(PyscriptUtility, "perform_operation",
                         return_value=mock_response_data) as mock_perform_operation:
        mock_db_action = MagicMock()
        mock_db_action.get.return_value.to_mongo.return_value.to_dict.return_value = mock_db_action_config
        mock_objects.return_value = mock_db_action

        result = PyscriptUtility.get_db_action_data(action_name, user, payload_dict, bot, predefined_objects)

        expected_collection_name = f"{bot}_{mock_db_action_config['collection']}_faq_embd"  # Adjust suffix
        mock_perform_operation.assert_called_once_with(
            {"test_query_type": payload_dict},
            user=user,
            bot=bot,
            collection_name=expected_collection_name
        )
        assert result == mock_response_data


def test_get_payload():
    predefined_objects = {
        "slot": {"test_key": "{\"key\": \"value\"}"},
        "latest_message": {
            "text": "/user_command",
            "entities": [{"entity": "kairon_user_msg", "value": "extracted_value"}]
        }
    }

    payload = [
        {"type": "from_slot", "value": "test_key", "query_type": "payload_search"},
        {"type": "from_user_message", "value": "ignored", "query_type": "embedding_search"},
        {"type": "static", "value": "static_value", "query_type": "embedding_search"}
    ]

    expected_result = {
        "payload_search": {"key": "value"},
        "embedding_search": "extracted_value static_value"
    }

    with patch.object(ActionUtility, "is_empty", side_effect=lambda x: x is None or x == ""):
        result = PyscriptUtility.get_payload(payload, predefined_objects)

    assert result == expected_result


def get_dummy_objects(http_action_config_mock):
    # Create a dummy objects attribute with a get method that always returns our mock.
    class DummyObjects:
        def get(self, *args, **kwargs):
            return http_action_config_mock

    return DummyObjects()


def test_api_call_success(monkeypatch):
    bot = "test_bot"
    action_name = "test_action"
    user = "test_user"
    payload = {"key": "value"}
    headers = {"Authorization": "Bearer token"}
    predefined_objects = {"tracker": {}}

    http_action_config_mock = MagicMock()
    http_action_config_mock.to_mongo.return_value.to_dict.return_value = {
        "request_method": "POST",
        "http_url": "http://example.com/api"
    }

    # Override HttpActionConfig.objects entirely
    monkeypatch.setattr(HttpActionConfig, "objects", get_dummy_objects(http_action_config_mock))
    # Patch the ActionUtility.prepare_url method
    monkeypatch.setattr(ActionUtility, "prepare_url", lambda http_url, tracker_data: "http://example.com/api")
    # Patch the ActionUtility.prepare_request method (won't be used because headers is provided)
    monkeypatch.setattr(ActionUtility, "prepare_request", lambda predefined_objects, headers_config, bot: headers)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"success": True}

    # Patch requests.request
    monkeypatch.setattr(requests, "request", lambda method, url, headers, json: mock_response)

    response = PyscriptUtility.api_call(action_name, user, payload, headers, bot, predefined_objects)
    assert response == {"success": True}


def test_api_call_failure(monkeypatch):
    bot = "test_bot"
    action_name = "test_action"
    user = "test_user"
    payload = {"key": "value"}
    headers = {"Authorization": "Bearer token"}
    predefined_objects = {"tracker": {}}

    http_action_config_mock = MagicMock()
    http_action_config_mock.to_mongo.return_value.to_dict.return_value = {
        "request_method": "POST",
        "http_url": "http://example.com/api"
    }

    monkeypatch.setattr(HttpActionConfig, "objects", get_dummy_objects(http_action_config_mock))
    monkeypatch.setattr(ActionUtility, "prepare_url", lambda http_url, tracker_data: "http://example.com/api")
    monkeypatch.setattr(ActionUtility, "prepare_request", lambda predefined_objects, headers_config, bot: headers)

    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"

    monkeypatch.setattr(requests, "request", lambda method, url, headers, json: mock_response)

    with pytest.raises(Exception, match="Internal Server Error"):
        PyscriptUtility.api_call(action_name, user, payload, headers, bot, predefined_objects)


def test_api_call_no_headers(monkeypatch):
    bot = "test_bot"
    action_name = "test_action"
    user = "test_user"
    payload = {"key": "value"}
    headers = None
    predefined_objects = {"tracker": {}}

    http_action_config_mock = MagicMock()
    http_action_config_mock.to_mongo.return_value.to_dict.return_value = {
        "request_method": "POST",
        "http_url": "http://example.com/api"
    }

    monkeypatch.setattr(HttpActionConfig, "objects", get_dummy_objects(http_action_config_mock))
    monkeypatch.setattr(ActionUtility, "prepare_url", lambda http_url, tracker_data: "http://example.com/api")

    # Provide alternate headers since none were passed
    prepared_headers = {"Authorization": "Bearer generated-token"}
    monkeypatch.setattr(ActionUtility, "prepare_request",
                        lambda predefined_objects, headers_config, bot: prepared_headers)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"success": True}

    monkeypatch.setattr(requests, "request", lambda method, url, headers, json: mock_response)

    response = PyscriptUtility.api_call(action_name, user, payload, headers, bot, predefined_objects)
    assert response == {"success": True}


@pytest.fixture
def predefined_objects():
    return {
        "slot": {"test_key": "{\"key\": \"value\"}"},
        "latest_message": {
            "text": "/user_command",
            "entities": [{"entity": "kairon_user_msg", "value": "extracted_value"}]
        }
    }


def test_get_payload_success(predefined_objects):
    payload = [
        {"type": "from_slot", "value": "test_key", "query_type": "payload_search"},
        {"type": "from_user_message", "value": "ignored", "query_type": "embedding_search"},
        {"type": "static", "value": "static_value", "query_type": "embedding_search"}
    ]

    expected_result = {
        "payload_search": {"key": "value"},
        "embedding_search": "extracted_value static_value"
    }

    with patch.object(ActionUtility, "is_empty", side_effect=lambda x: x is None or x == ""):
        result = PyscriptUtility.get_payload(payload, predefined_objects)

    assert result == expected_result


def test_get_payload_empty_slot(predefined_objects):
    payload = [{"type": "from_slot", "value": "non_existent_key", "query_type": "payload_search"}]

    expected_result = {"payload_search": None}

    with patch.object(ActionUtility, "is_empty", return_value=True):
        result = PyscriptUtility.get_payload(payload, predefined_objects)

    assert result == expected_result


def test_get_payload_empty_user_message(predefined_objects):
    predefined_objects["latest_message"]["text"] = ""

    payload = [{"type": "from_user_message", "value": "ignored", "query_type": "embedding_search"}]

    expected_result = {"embedding_search": ""}  # Expecting empty string, not None

    with patch.object(ActionUtility, "is_empty", return_value=True):
        result = PyscriptUtility.get_payload(payload, predefined_objects)

    assert result == expected_result


def test_get_payload_with_json_parsing_error(predefined_objects):
    predefined_objects["slot"]["invalid_json"] = "{invalid_json}"

    payload = [{"type": "from_slot", "value": "invalid_json", "query_type": "payload_search"}]

    with patch.object(ActionUtility, "is_empty", return_value=False):
        with pytest.raises(Exception, match=r"Error converting payload to JSON: {invalid_json}"):
            PyscriptUtility.get_payload(payload, predefined_objects)


def test_get_payload_user_message_with_command(predefined_objects):
    payload = [{"type": "from_user_message", "value": "ignored", "query_type": "embedding_search"}]

    expected_result = {"embedding_search": "extracted_value"}

    with patch.object(ActionUtility, "is_empty", side_effect=lambda x: x is None or x == ""):
        result = PyscriptUtility.get_payload(payload, predefined_objects)

    assert result == expected_result


def test_get_payload_without_kairon_user_msg(predefined_objects):
    predefined_objects["latest_message"]["entities"] = []  # No kairon_user_msg entity

    payload = [{"type": "from_user_message", "value": "ignored", "query_type": "embedding_search"}]

    expected_result = {"embedding_search": "/user_command"}  # Falls back to text value

    with patch.object(ActionUtility, "is_empty", side_effect=lambda x: x is None or x == ""):
        result = PyscriptUtility.get_payload(payload, predefined_objects)

    assert result == expected_result


def test_get_payload_multiple_embedding_search(predefined_objects):
    payload = [
        {"type": "static", "value": "value1", "query_type": "embedding_search"},
        {"type": "static", "value": "value2", "query_type": "embedding_search"},
    ]

    expected_result = {"embedding_search": "value1 value2"}

    result = PyscriptUtility.get_payload(payload, predefined_objects)

    assert result == expected_result


def test_send_waba_message_success():
    payload = {"to": "12345", "type": "text", "text": {"body": "hello"}}
    api_key = "test_api_key"
    bot_id = "bot123"
    predefined = {"some": "object"}
    fake_response = MagicMock()
    fake_response.json = {"messages": [{"id": "abc123"}]}
    with patch("kairon.shared.concurrency.actors.utils.requests.post", return_value=fake_response) as mock_post:
        result = PyscriptUtility.send_waba_message(payload, api_key, bot_id, predefined)
        assert result == {"messages": [{"id": "abc123"}]}

        mock_post.assert_called_once_with(
            url="https://waba-v2.360dialog.io/messages",
            headers={"D360-API-KEY": api_key, "Content-TYpe": "application/json"},
            data=orjson.dumps(payload)
        )

def test_execute_simple_assignment():
    runner = PyScriptRunner()
    script = "x = 10\ny = 20"
    # Provide minimal predefined_objects with required 'bot'
    result = runner.execute(script, predefined_objects={"slot": {"bot": "bot123"}})

    assert result.get("x") == 10
    assert result.get("y") == 20
    # Ensure callables and modules are filtered out
    assert "send_waba_message" not in result


def test_execute_predefined_objects():
    runner = PyScriptRunner()
    predefined = {"foo": "bar", "slot": {"bot": "botid"}}
    script = "z = foo"
    result = runner.execute(script, predefined_objects=predefined)

    assert result.get("z") == "bar"
    # Predefined non-callable objects should remain
    assert result.get("foo") == "bar"


def test_datetime_and_date_cleanup():
    runner = PyScriptRunner()
    script = (
        "from datetime import datetime, date\n"
        "dt = datetime(2021, 1, 2, 3, 4, 5)\n"
        "d = date(2020, 12, 31)\n"
    )
    result = runner.execute(script, predefined_objects={"slot": {"bot": "botid"}})

    # datetime should be formatted as MM/DD/YYYY, HH:MM:SS
    assert result.get("dt") == "01/02/2021, 03:04:05"
    # date should be formatted as YYYY-MM-DD
    assert result.get("d") == "2020-12-31"


def test_script_exception_wrapped():
    runner = PyScriptRunner()
    # The script raises a ValueError, which should be caught and re-raised as AppException
    with pytest.raises(AppException) as exc_info:
        runner.execute(
            "raise ValueError('oops')",
            predefined_objects={"slot": {"bot": "botid"}},
            timeout=5
        )
    assert "Script execution error" in str(exc_info.value)