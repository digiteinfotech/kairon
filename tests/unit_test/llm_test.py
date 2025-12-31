import os
from urllib.parse import urljoin
import ujson as json

from kairon.shared.admin.processor import Sysadmin
from kairon.shared.utils import Utility
import urllib
from unittest import mock
from unittest.mock import patch, AsyncMock, MagicMock
from urllib.parse import urljoin

from loguru import logger
from io import StringIO

import numpy as np
import pytest
from aiohttp import ClientConnectionError
from fastembed import SparseTextEmbedding, LateInteractionTextEmbedding
from mongoengine import connect

from kairon.shared.rest_client import AioRestClient
from kairon.shared.utils import Utility

Utility.load_system_metadata()


from kairon.exceptions import AppException
from kairon.shared.admin.constants import BotSecretType
from kairon.shared.admin.data_objects import BotSecrets, LLMSecret
from kairon.shared.cognition.data_objects import CognitionData, CognitionSchema
from kairon.shared.data.constant import DEFAULT_SYSTEM_PROMPT, DEFAULT_LLM
from kairon.shared.llm.processor import LLMProcessor
import litellm
from deepdiff import DeepDiff
from kairon.shared.actions.utils import ActionUtility
from aioresponses import aioresponses
from cryptography.fernet import Fernet

from aioresponses import aioresponses as aioresponses_mocker


class TestLLM:
    @pytest.fixture(autouse=True, scope="class")
    def init_connection(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))

    @pytest.mark.asyncio
    @mock.patch("kairon.shared.utils.Utility.decrypt_message", autospec=True)
    @mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
    async def test_gpt3_faq_embedding_train(
            self,
            mock_get_embedding,
            mock_decrypt_message
    ):
        mock_decrypt_message.side_effect = lambda x: x

        bot = "test_embed_faq"
        user = "test"
        value = "nupurkhare"

        test_content = CognitionData(
            data="Welcome! Are you completely new to programming?",
            bot=bot,
            user=user
        ).save()

        LLMSecret(
            llm_type="openai",
            api_key=value,
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        ).save()

        embedding = list(np.random.random(LLMProcessor.__embedding__))
        mock_get_embedding.return_value = [embedding]

        from aioresponses import aioresponses as aioresponses_mocker

        with aioresponses_mocker() as m:
            with mock.patch.dict(
                    Utility.environment,
                    {
                        "llm": {
                            "faq": "GPT3_FAQ_EMBED",
                            "url": "http://localhost",
                            "request_timeout": 30
                        },
                        "vector": {
                            "db": "http://localhost:6333",
                            "key": None
                        },
                        "action": {
                            "request_timeout": 30
                        },
                        "security": {
                            "enable_ssl": False
                        }
                    },
                    clear=True
            ):
                gpt3 = LLMProcessor(bot, DEFAULT_LLM)

                m.get(
                    "http://localhost:6333/collections",
                    payload={"time": 0, "status": "ok", "result": {"collections": []}}
                )

                m.put(
                    f"http://localhost:6333/collections/{gpt3.bot}{gpt3.suffix}",
                    status=200
                )

                m.put(
                    f"http://localhost:6333/collections/{gpt3.bot}{gpt3.suffix}/points",
                    payload={
                        "result": {"operation_id": 0, "status": "acknowledged"},
                        "status": "ok",
                        "time": 0.003
                    }
                )

                response = await gpt3.train(user=user)

                assert response["faq"] == 1

                points_payload = list(m.requests.values())[2][0].kwargs["json"]
                point = points_payload["points"][0]

                assert point["id"] == test_content.vector_id
                assert point["payload"] == {"content": test_content.data}

                assert len(point["vector"]) == len(embedding)
                assert all(a == b for a, b in zip(point["vector"], embedding))

    @pytest.mark.asyncio
    @mock.patch("kairon.shared.utils.Utility.decrypt_message", autospec=True)
    @mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
    async def test_gpt3_faq_embedding_train_payload_text(self, mock_get_embedding, mock_decrypt_message):
        mock_decrypt_message.side_effect = lambda x: x

        bot = "test_embed_faq_text"
        user = "test"
        value = "test_api_key"
        CognitionSchema(
            metadata=[
                {"column_name": "name", "data_type": "str", "enable_search": True, "create_embeddings": True},
                {"column_name": "city", "data_type": "str", "enable_search": False, "create_embeddings": True}
            ],
            collection_name="User_details",
            bot=bot, user=user
        ).save()

        CognitionSchema(
            metadata=[
                {"column_name": "country", "data_type": "str", "enable_search": True, "create_embeddings": True},
                {"column_name": "role", "data_type": "str", "enable_search": True, "create_embeddings": True}
            ],
            collection_name="Country_details",
            bot=bot, user=user
        ).save()

        test_content_user = CognitionData(
            data={"name": "Nupur", "city": "Pune"},
            content_type="json",
            collection="User_details",
            bot=bot, user=user
        ).save()

        test_content_country1 = CognitionData(
            data={"country": "Spain", "role": "analyst"},
            content_type="json",
            collection="Country_details",
            bot=bot, user=user
        ).save()

        test_content_country2 = CognitionData(
            data={"country": "USA", "role": "ds"},
            content_type="json",
            collection="Country_details",
            bot=bot, user=user
        ).save()

        # Save LLM Secret
        LLMSecret(
            llm_type="openai",
            api_key=value,
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        ).save()
        embedding = list(np.random.random(LLMProcessor.__embedding__))
        mock_get_embedding.return_value = embedding

        with aioresponses_mocker() as m:
            with mock.patch.dict(
                    Utility.environment,
                    {
                        "llm": {
                            "faq": "GPT3_FAQ_EMBED",
                            "url": "http://localhost",
                            "request_timeout": 30
                        },
                        "vector": {
                            "db": "http://localhost:6333",
                            "key": None
                        },
                        "action": {"request_timeout": 30},
                        "security": {"enable_ssl": False}
                    },
                    clear=True
            ):
                gpt3 = LLMProcessor(bot, DEFAULT_LLM)
                m.get(
                    "http://localhost:6333/collections",
                    payload={"time": 0, "status": "ok", "result": {"collections": []}}
                )

                m.put(
                    f"http://localhost:6333/collections/{gpt3.bot}_user_details{gpt3.suffix}",
                    status=200
                )

                m.put(
                    f"http://localhost:6333/collections/{gpt3.bot}_user_details{gpt3.suffix}/points",
                    payload={"result": {"operation_id": 0, "status": "acknowledged"}, "status": "ok", "time": 0.003}
                )

                m.put(
                    f"http://localhost:6333/collections/{gpt3.bot}_country_details{gpt3.suffix}",
                    status=200
                )

                m.put(
                    f"http://localhost:6333/collections/{gpt3.bot}_country_details{gpt3.suffix}/points",
                    payload={"result": {"operation_id": 0, "status": "acknowledged"}, "status": "ok", "time": 0.003}
                )
                response = await gpt3.train(user=user)

                assert response['faq'] == 3
                points_requests = [
                    r[0].kwargs['json'] for r in m.requests.values() if 'points' in r[0].kwargs.get('json', {})
                ]

                for i, pr in enumerate(points_requests):
                    print(f"Points request {i}: {pr}")

                assert any(
                    any('name' in point['payload'] and point['payload']['name'] == 'Nupur' for point in req['points'])
                    for req in points_requests
                )
                assert any(
                    any('country' in point['payload'] and point['payload']['country'] == 'Spain' for point in
                        req['points'])
                    for req in points_requests
                )
                assert any(
                    any('country' in point['payload'] and point['payload']['country'] == 'USA' for point in
                        req['points'])
                    for req in points_requests
                )

    @pytest.mark.asyncio
    @mock.patch("kairon.shared.utils.Utility.decrypt_message", autospec=True)
    @mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
    async def test_gpt3_faq_embedding_train_payload_with_int(self, mock_get_embedding, mock_decrypt_message):
        mock_decrypt_message.side_effect = lambda x: x

        bot = "test_embed_faq_json"
        user = "test"
        value = "nupurkhare"

        CognitionSchema(
            metadata=[
                {"column_name": "name", "data_type": "str", "enable_search": True, "create_embeddings": True},
                {"column_name": "age", "data_type": "int", "enable_search": True, "create_embeddings": False},
                {"column_name": "color", "data_type": "str", "enable_search": True, "create_embeddings": True}
            ],
            collection_name="payload_with_int",
            bot=bot, user=user
        ).save()

        test_content = CognitionData(
            data={"name": "Ram", "age": 23, "color": "red"},
            content_type="json",
            collection="payload_with_int",
            bot=bot, user=user
        ).save()
        LLMSecret(
            llm_type="openai",
            api_key=value,
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        ).save()
        embedding = list(np.random.random(LLMProcessor.__embedding__))
        mock_get_embedding.return_value = embedding

        from aioresponses import aioresponses as aioresponses_mocker

        with aioresponses_mocker() as m:
            with mock.patch.dict(
                    Utility.environment,
                    {
                        "llm": {
                            "faq": "GPT3_FAQ_EMBED",
                            "url": "http://localhost",
                            "request_timeout": 30
                        },
                        "vector": {
                            "db": "http://localhost:6333",
                            "key": None
                        },
                        "action": {
                            "request_timeout": 30
                        },
                        "security": {
                            "enable_ssl": False
                        }
                    },
                    clear=True
            ):
                gpt3 = LLMProcessor(bot, DEFAULT_LLM)
                m.get(
                    "http://localhost:6333/collections",
                    payload={"time": 0, "status": "ok", "result": {"collections": []}}
                )

                m.put(
                    f"http://localhost:6333/collections/{gpt3.bot}_payload_with_int_faq_embd",
                    status=200
                )

                m.put(
                    f"http://localhost:6333/collections/{gpt3.bot}_payload_with_int_faq_embd/points",
                    payload={"result": {"operation_id": 0, "status": "acknowledged"}, "status": "ok", "time": 0.003}
                )

                response = await gpt3.train(user=user)
                assert response['faq'] == 1

                points_request = list(m.requests.values())[1][0].kwargs['json']
                assert points_request['name'] == f"{gpt3.bot}_payload_with_int_faq_embd"
                assert 'vectors' in points_request
                assert points_request['vectors']['distance'] == 'Cosine'
                assert points_request['vectors']['size'] == LLMProcessor.__embedding__

    @pytest.mark.asyncio
    @mock.patch("kairon.shared.utils.Utility.decrypt_message", autospec=True)
    @mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
    async def test_gpt3_faq_embedding_train_int(self, mock_get_embedding, mock_decrypt_message):
        mock_decrypt_message.side_effect = lambda x: x

        bot = "test_int"
        user = "test"
        value = "nupurkhare"

        CognitionSchema(
            metadata=[
                {"column_name": "name", "data_type": "str", "enable_search": True, "create_embeddings": True},
                {"column_name": "age", "data_type": "int", "enable_search": True, "create_embeddings": False},
                {"column_name": "color", "data_type": "str", "enable_search": True, "create_embeddings": True}
            ],
            collection_name="embd_int",
            bot=bot, user=user
        ).save()

        test_content = CognitionData(
            data={"name": "Ram", "age": 23, "color": "red"},
            content_type="json",
            collection="embd_int",
            bot=bot, user=user
        ).save()

        LLMSecret(
            llm_type="openai",
            api_key=value,
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        ).save()

        embedding = list(np.random.random(LLMProcessor.__embedding__))
        mock_get_embedding.return_value = embedding

        from aioresponses import aioresponses as aioresponses_mocker

        with aioresponses_mocker() as m:
            with mock.patch.dict(
                    Utility.environment,
                    {
                        "llm": {"faq": "GPT3_FAQ_EMBED", "url": "http://localhost", "request_timeout": 30},
                        "vector": {"db": "http://localhost:6333", "key": None},
                        "action": {"request_timeout": 30},
                        "security": {"enable_ssl": False}
                    },
                    clear=True
            ):
                gpt3 = LLMProcessor(bot, DEFAULT_LLM)

                m.get("http://localhost:6333/collections",
                      payload={"time": 0, "status": "ok", "result": {"collections": []}})
                m.put(f"http://localhost:6333/collections/{gpt3.bot}_embd_int_faq_embd", status=200)
                m.put(f"http://localhost:6333/collections/{gpt3.bot}_embd_int_faq_embd/points",
                      payload={"result": {"operation_id": 0, "status": "acknowledged"}, "status": "ok", "time": 0.003})

                response = await gpt3.train(user=user)
                assert response['faq'] == 1

    def test_gpt3_faq_embedding_train_failure(self):
        with pytest.raises(AppException, match=f"LLM secret for '{DEFAULT_LLM}' is not configured!"):
            LLMProcessor('test_gpt3_faq_embedding_train_failure', DEFAULT_LLM)

    @pytest.fixture
    def llm_processor(self):
        with mock.patch(
                "kairon.shared.llm.processor.Utility.environment",
                {
                    "vector": {"db": "test", "key": "key"},
                    "llm": {
                        "request_timeout": 30,
                        "url": "http://fake-llm-service"
                    }
                }
        ), \
                mock.patch(
                    "kairon.shared.llm.processor.Sysadmin.get_llm_secret",
                    return_value={"key": "secret"}
                ), \
                mock.patch(
                    "kairon.shared.llm.processor.get_encoding"
                ):
            yield LLMProcessor(bot="test_bot", llm_type="openai")

    @pytest.mark.asyncio
    async def test_parse_completion_response_stream_success(self,llm_processor):
        response = {
            "choices": [
                {
                    "index": 0,
                    "delta": {"content": "hello"}
                }
            ]
        }

        with mock.patch(
                "kairon.shared.llm.processor.randbelow", return_value=0
        ):
            result = await llm_processor._LLMProcessor__parse_completion_response(
                response,
                stream=True,
                n=1
            )

        assert result == "hello"

    @pytest.mark.asyncio
    async def test_parse_completion_response_stream_no_match(self,llm_processor):
        response = {
            "choices": [
                {
                    "index": 1,  # mismatch
                    "delta": {"content": "hello"}
                }
            ]
        }

        with mock.patch(
                "kairon.shared.llm.processor.randbelow", return_value=0
        ):
            result = await llm_processor._LLMProcessor__parse_completion_response(
                response,
                stream=True,
                n=1
            )

        assert result == ""

    @pytest.mark.asyncio
    async def test_parse_completion_response_non_stream(self,llm_processor):
        response = {
            "choices": [
                {
                    "message": {"content": "final answer"}
                }
            ]
        }

        with mock.patch(
                "kairon.shared.llm.processor.choice",
                return_value=response["choices"][0]
        ):
            result = await llm_processor._LLMProcessor__parse_completion_response(
                response,
                stream=False
            )

        assert result == "final answer"

    @pytest.mark.asyncio
    async def test_get_completion_returns_non_dict_response(self, llm_processor):
        messages = [{"role": "user", "content": "hello"}]
        hyperparameters = {}
        user = "test_user"

        http_response = "RAW_RESPONSE"
        status_code = 200

        with mock.patch(
            "kairon.shared.llm.processor.ActionUtility.execute_request_async",
            return_value=(http_response, status_code, 0.1, None)
        ):
            result = await llm_processor._LLMProcessor__get_completion(
                messages=messages,
                hyperparameters=hyperparameters,
                user=user,
                media_ids=None
            )

        assert result == ("RAW_RESPONSE", "RAW_RESPONSE")

    @pytest.mark.asyncio
    async def test_delete_collections_deletes_bot_collections(self, llm_processor):
        mock_client = mock.AsyncMock()

        # GET response with matching collection name
        mock_client.request.side_effect = [
            {
                "result": {
                    "collections": [
                        {"name": f"{llm_processor.bot}_faq_embd"},
                        {"name": "other_bot_faq_embd"}
                    ]
                }
            },
            None  # DELETE call returns nothing
        ]

        with mock.patch(
                "kairon.shared.llm.processor.AioRestClient",
                return_value=mock_client
        ):
            await llm_processor._LLMProcessor__delete_collections()

        assert mock_client.request.call_count == 2

        delete_call = mock_client.request.call_args_list[1]
        assert delete_call.kwargs["request_method"] == "DELETE"
        assert llm_processor.bot in delete_call.kwargs["http_url"]
        mock_client.cleanup.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_collection_points_raises_exception(self, llm_processor):
        error_response = {
            "result": False,
            "status": {
                "error": "delete failed"
            }
        }

        with mock.patch("kairon.shared.llm.processor.AioRestClient") as mock_client:
            mock_instance = mock_client.return_value
            mock_instance.request = mock.AsyncMock(return_value=error_response)

            with pytest.raises(AppException):
                await llm_processor.__delete_collection_points__(
                    collection_name="test_collection",
                    point_ids=["p1", "p2"],
                    err_msg="delete error",
                    raise_err=True
                )

    @pytest.mark.asyncio
    async def test_delete_collection_points_no_raise(self, llm_processor):
        error_response = {
            "result": False,
            "status": {
                "error": "delete failed"
            }
        }

        with mock.patch("kairon.shared.llm.processor.AioRestClient") as mock_client:
            mock_instance = mock_client.return_value
            mock_instance.request = mock.AsyncMock(return_value=error_response)

            await llm_processor.__delete_collection_points__(
                collection_name="test_collection",
                point_ids=["p1"],
                err_msg="delete error",
                raise_err=False
            )

    def test_get_llm_metadata_default_with_secret(self):
        mock_secret = mock.Mock()
        mock_secret.models = ["gpt-4", "gpt-3.5"]

        with mock.patch(
                "kairon.shared.llm.processor.LLMSecret.objects"
        ) as mock_objects:
            mock_objects.return_value.first.return_value = mock_secret
            result = LLMProcessor.get_llm_metadata_default("openai")
            assert result == ["gpt-4", "gpt-3.5"]

    def test_get_llm_metadata_default_without_secret(self):
        with mock.patch(
                "kairon.shared.llm.processor.LLMSecret.objects"
        ) as mock_objects:
            mock_objects.return_value.first.return_value = None
            result = LLMProcessor.get_llm_metadata_default("openai")
            assert result == []

    @pytest.mark.asyncio
    @mock.patch("kairon.shared.utils.Utility.decrypt_message", autospec=True)
    @mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
    async def test_gpt3_faq_embedding_train_upsert_error(
            self,
            mock_get_embedding,
            mock_decrypt_message
    ):
        mock_decrypt_message.side_effect = lambda x: x

        bot = "test_embed_faq_not_exists"
        user = "test"
        value = "nupurk"

        test_content = CognitionData(
            data="Welcome! Are you completely new to programming?",
            bot=bot,
            user=user
        ).save()

        LLMSecret(
            llm_type="openai",
            api_key=value,  # plaintext
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        ).save()

        embedding = list(np.random.random(LLMProcessor.__embedding__))
        mock_get_embedding.return_value = embedding

        from aioresponses import aioresponses

        with aioresponses() as m:
            with mock.patch.dict(
                    Utility.environment,
                    {
                        "llm": {
                            "faq": "GPT3_FAQ_EMBED",
                            "url": "http://localhost",
                            "request_timeout": 30
                        },
                        "vector": {
                            "db": "http://localhost:6333",
                            "key": None
                        },
                        "action": {
                            "request_timeout": 30
                        },
                        "security": {
                            "enable_ssl": False
                        }
                    },
                    clear=True
            ):
                gpt3 = LLMProcessor(bot, DEFAULT_LLM)

                m.get(
                    "http://localhost:6333/collections",
                    payload={"result": {"collections": []}},
                )

                m.put(
                    f"http://localhost:6333/collections/{gpt3.bot}{gpt3.suffix}",
                    status=200,
                )

                m.put(
                    f"http://localhost:6333/collections/{gpt3.bot}{gpt3.suffix}/points",
                    payload={
                        "result": None,
                        "status": {"error": "Json deserialize error"}
                    },
                )

                with pytest.raises(AppException, match="Unable to train FAQ! Contact support"):
                    await gpt3.train(user=user)

        args, kwargs = mock_get_embedding.call_args
        assert args[1] == [test_content.data]
        assert args[2] == user

    @mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
    @pytest.mark.asyncio
    async def test_gpt3_faq_embedding_train_payload_upsert_error_json(self, mock_embedding, aioresponses):
        bot = "payload_upsert_error"
        user = "test"
        value = "nupurk"

        CognitionSchema(
            metadata=[
                {"column_name": "city", "data_type": "str", "enable_search": True, "create_embeddings": True},
                {"column_name": "color", "data_type": "str", "enable_search": True, "create_embeddings": True}
            ],
            collection_name="error_json",
            bot=bot,
            user=user
        ).save()

        test_content = CognitionData(
            data={'city': 'London', 'color': 'red'},
            content_type="json",
            collection="error_json",
            bot=bot,
            user=user
        ).save()

        LLMSecret(
            llm_type="openai",
            api_key=value,
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        ).save()

        embedding = list(np.random.random(LLMProcessor.__embedding__))
        mock_embedding.return_value = embedding

        with mock.patch.dict(Utility.environment, {
            'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': value, 'url': 'http://localhost:8000'},
            'vector': {"db": "http://localhost:6333", "key": "test"}
        }):
            gpt3 = LLMProcessor(test_content.bot, DEFAULT_LLM)

            aioresponses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections"),
                method="GET",
                payload={"time": 0, "status": "ok", "result": {"collections": []}}
            )

            aioresponses.add(
                method="DELETE",
                url=urljoin(Utility.environment['vector']['db'],
                            f"/collections/payload_upsert_error_error_json_faq_embd")
            )

            aioresponses.add(
                url=urljoin(Utility.environment['vector']['db'],
                            f"/collections/payload_upsert_error_error_json_faq_embd"),
                method="PUT",
                status=200
            )

            aioresponses.add(
                url=urljoin(Utility.environment['vector']['db'],
                            f"/collections/payload_upsert_error_error_json_faq_embd/points"),
                method="PUT",
                payload={"result": None,
                         'status': {'error': 'Json deserialize error: missing field `vectors` at line 1 column 34779'},
                         "time": 0.003612634}
            )

            with pytest.raises(AppException, match="Unable to train FAQ! Contact support"):
                await gpt3.train(user=user)

    @pytest.mark.asyncio
    @mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
    async def test_gpt3_faq_embedding_predict(self, mock_embedding):
        embedding = list(np.random.random(LLMProcessor.__embedding__))

        bot = "test_embed_faq_predict"
        user = "test"
        value = "knupur"
        collection = 'python'
        llm_type = "openai"

        test_content = CognitionData(
            data="Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.",
            collection=collection, bot=bot, user=user
        ).save()

        LLMSecret(
            llm_type=llm_type,
            api_key=value,
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        ).save()

        generated_text = "Python is dynamically typed, garbage-collected, high level, general purpose programming."
        query = "What kind of language is python?"
        hyperparameters = Utility.get_default_llm_hyperparameters()

        k_faq_action_config = {
            "system_prompt": "You are a personal assistant. Answer the question according to the below context",
            "context_prompt": "Based on below context answer question, if answer not in context check previous logs.",
            "similarity_prompt": [{
                "top_results": 10,
                "similarity_threshold": 0.70,
                'use_similarity_prompt': True,
                'similarity_prompt_name': 'Similarity Prompt',
                'similarity_prompt_instructions': 'Answer according to this context.',
                'collection': collection
            }],
            "hyperparameters": hyperparameters
        }
        mock_embedding.return_value = embedding

        from aioresponses import aioresponses as aioresponses_mocker

        with aioresponses_mocker() as aioresponses:
            aioresponses.add(
                url=urljoin(Utility.environment['llm']['url'], f"/{bot}/completion/{llm_type}"),
                method="POST",
                status=200,
                payload={
                    'formatted_response': generated_text,
                    'response': {'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}
                }
            )

            with mock.patch.dict(Utility.environment, {
                'vector': {"db": "http://localhost:6333", "key": "test"},
                'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': value, 'url': 'http://localhost'}
            }):
                gpt3 = LLMProcessor(bot, DEFAULT_LLM)
                aioresponses.add(
                    url=urljoin(Utility.environment['vector']['db'],
                                f"/collections/{gpt3.bot}_{test_content.collection}{gpt3.suffix}/points/search"),
                    method="POST",
                    payload={'result': [
                        {'id': test_content.vector_id, 'score': 0.80, "payload": {'content': test_content.data}}]
                    }
                )

                response, time_elapsed = await gpt3.predict(query, user=user, **k_faq_action_config)
                assert list(aioresponses.requests.values())[0][0].kwargs['json'] == {
                    'vector': embedding,
                    'limit': 10,
                    'with_payload': True,
                    'score_threshold': 0.70
                }

                args, kwargs = mock_embedding.call_args
                assert args[1] == query
                assert args[2] == user
                assert isinstance(time_elapsed, float) and time_elapsed > 0.0

    @pytest.mark.asyncio
    @mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
    async def test_gpt3_faq_embedding_predict_with_default_collection(self, mock_embedding):
        embedding = list(np.random.random(LLMProcessor.__embedding__))

        bot = "test_embed_faq_predict_with_default_collection"
        user = "test"
        value = "knupur"
        collection = 'default'
        llm_type = "openai"

        test_content = CognitionData(
            data="Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.",
            collection=collection,
            bot=bot,
            user=user
        ).save()

        LLMSecret(
            llm_type=llm_type,
            api_key=value,
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        ).save()

        generated_text = "Python is dynamically typed, garbage-collected, high level, general purpose programming."
        query = "What kind of language is python?"
        hyperparameters = Utility.get_default_llm_hyperparameters()

        k_faq_action_config = {
            "system_prompt": "You are a personal assistant. Answer the question according to the below context",
            "context_prompt": "Based on below context answer question, if answer not in context check previous logs.",
            "similarity_prompt": [{
                "top_results": 10,
                "similarity_threshold": 0.70,
                'use_similarity_prompt': True,
                'similarity_prompt_name': 'Similarity Prompt',
                'similarity_prompt_instructions': 'Answer according to this context.',
                'collection': collection
            }],
            'hyperparameters': hyperparameters
        }

        mock_embedding.return_value = embedding

        from aioresponses import aioresponses as aioresponses_mocker

        with aioresponses_mocker() as aioresponses:
            aioresponses.add(
                url=urljoin(Utility.environment['llm']['url'], f"/{bot}/completion/{llm_type}"),
                method="POST",
                status=200,
                payload={
                    'formatted_response': generated_text,
                    'response': {
                        'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]
                    }
                }
            )

            with mock.patch.dict(Utility.environment, {
                'vector': {"db": "http://localhost:6333", "key": "test"},
                'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': value, 'url': 'http://localhost'}
            }):
                gpt3 = LLMProcessor(bot, DEFAULT_LLM)
                aioresponses.add(
                    url=urljoin(Utility.environment['vector']['db'],
                                f"/collections/{gpt3.bot}{gpt3.suffix}/points/search"),
                    method="POST",
                    payload={'result': [
                        {'id': test_content.vector_id, 'score': 0.80, "payload": {'content': test_content.data}}]
                    }
                )
                response, time_elapsed = await gpt3.predict(query, user=user, **k_faq_action_config)
                assert response['content'] == generated_text
                assert list(aioresponses.requests.values())[0][0].kwargs['json'] == {
                    'vector': embedding,
                    'limit': 10,
                    'with_payload': True,
                    'score_threshold': 0.70
                }

                args, kwargs = mock_embedding.call_args
                assert args[1] == query
                assert args[2] == user

                assert isinstance(time_elapsed, float) and time_elapsed > 0.0




    @pytest.mark.asyncio
    @mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
    async def test_gpt3_faq_embedding_predict_with_values(self, mock_embedding, aioresponses):
        embedding = list(np.random.random(LLMProcessor.__embedding__))

        test_content = CognitionData(
            data="Python is a high-level, general-purpose programming language. "
                 "Its design philosophy emphasizes code readability with the use of significant indentation. "
                 "Python is dynamically typed and garbage-collected.",
            collection="python",
            bot="test_gpt3_faq_embedding_predict_with_values",
            user="test"
        ).save()

        generated_text = (
            "Python is dynamically typed, garbage-collected, high level, "
            "general purpose programming."
        )
        query = "What kind of language is python?"

        hyperparameters = Utility.get_default_llm_hyperparameters()
        key = "test"
        user = "tests"
        llm_type = "openai"

        llm_secret = LLMSecret(
            llm_type=llm_type,
            api_key=key,
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=test_content.bot,
            user=user
        )
        llm_secret.save()

        k_faq_action_config = {
            "system_prompt": "You are a personal assistant. Answer the question according to the below context",
            "context_prompt": "Based on below context answer question, if answer not in context check previous logs.",
            "similarity_prompt": [
                {
                    "top_results": 10,
                    "similarity_threshold": 0.70,
                    "use_similarity_prompt": True,
                    "similarity_prompt_name": "Similarity Prompt",
                    "similarity_prompt_instructions": "Answer according to this context.",
                    "collection": "python"
                }
            ],
            "hyperparameters": hyperparameters
        }

        mock_embedding.return_value = embedding

        aioresponses.add(
            url=urljoin(
                Utility.environment["llm"]["url"],
                f"/{test_content.bot}/completion/{llm_type}"
            ),
            method="POST",
            payload={
                "formatted_response": generated_text,
                "response": {
                    "id": "chatcmpl-5cde438e-0c93-47d8-bbee-13319b4f2000",
                    "created": 1720090690,
                    "choices": [
                        {
                            "message": {
                                "content": generated_text,
                                "role": "assistant"
                            }
                        }
                    ]
                }
            }
            ,
        )

        with mock.patch.dict(
                Utility.environment,
                {"vector": {"key": "test", "db": "http://localhost:6333"}}
        ):
            gpt3 = LLMProcessor(test_content.bot, DEFAULT_LLM)

            aioresponses.add(
                url=urljoin(
                    Utility.environment["vector"]["db"],
                    f"/collections/{gpt3.bot}_{test_content.collection}{gpt3.suffix}/points/search"
                ),
                method="POST",
                payload={
                    "result": [
                        {
                            "id": test_content.vector_id,
                            "score": 0.80,
                            "payload": {"content": test_content.data}
                        }
                    ]
                },
            )

            response, time_elapsed = await gpt3.predict(
                query, user=user, **k_faq_action_config
            )

            assert response["content"] == generated_text

            assert gpt3.logs == [
                {
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a personal assistant. Answer the question according to the below context",
                        },
                        {
                            "role": "user",
                            "content": (
                                "Based on below context answer question, if answer not in context check previous logs.\n"
                                "Instructions on how to use Similarity Prompt:\n"
                                "['Python is a high-level, general-purpose programming language. "
                                "Its design philosophy emphasizes code readability with the use of significant indentation. "
                                "Python is dynamically typed and garbage-collected.']\n"
                                "Answer according to this context.\n \n"
                                "Q: What kind of language is python? \nA:"
                            ),
                        },
                    ],
                    "raw_completion_response": {
                        "id": "chatcmpl-5cde438e-0c93-47d8-bbee-13319b4f2000",
                        "created": 1720090690,
                        "choices": [
                            {
                                "message": {
                                    "content": generated_text,
                                    "role": "assistant"
                                }
                            }
                        ],
                    },
                    "type": "answer_query",
                    "hyperparameters": {
                        "temperature": 0.0,
                        "max_tokens": 300,
                        "model": "gpt-4.1-mini",
                        "top_p": 0.0,
                        "n": 1,
                        "stop": None,
                        "presence_penalty": 0.0,
                        "frequency_penalty": 0.0,
                        "logit_bias": {},
                    },
                }
            ]

            assert list(aioresponses.requests.values())[0][0].kwargs["json"] == {
                "vector": embedding,
                "limit": 10,
                "with_payload": True,
                "score_threshold": 0.70,
            }

            assert isinstance(time_elapsed, float) and time_elapsed > 0.0

    @pytest.mark.asyncio
    @mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
    async def test_gpt3_faq_embedding_predict_with_values_and_stream(
            self,
            mock_get_embedding,
            aioresponses):
        embedding = list(np.random.random(LLMProcessor.__embedding__))

        test_content = CognitionData(
            data="Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.",
            collection='python',
            bot="test_gpt3_faq_embedding_predict_with_values_and_stream",
            user="test"
        ).save()

        generated_text = (
            "Python is dynamically typed, garbage-collected, high level, general purpose programming."
        )
        query = "What kind of language is python?"

        hyperparameters = Utility.get_default_llm_hyperparameters()
        hyperparameters["stream"] = True

        key = "test"
        user = "tests"
        llm_type = "openai"

        llm_secret = LLMSecret(
            llm_type=llm_type,
            api_key=key,
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=test_content.bot,
            user=user
        )
        llm_secret.save()

        k_faq_action_config = {
            "system_prompt": "You are a personal assistant. Answer the question according to the below context",
            "context_prompt": "Based on below context answer question, if answer not in context check previous logs.",
            "similarity_prompt": [{
                "top_results": 10,
                "similarity_threshold": 0.70,
                "use_similarity_prompt": True,
                "similarity_prompt_name": "Similarity Prompt",
                "similarity_prompt_instructions": "Answer according to this context.",
                "collection": "python"
            }],
            "hyperparameters": hyperparameters
        }

        mock_get_embedding.return_value = embedding

        aioresponses.add(
            url=urljoin(
                Utility.environment["llm"]["url"],
                f"/{test_content.bot}/completion/{llm_type}"
            ),
            method="POST",
            status=200,
            payload={
                "formatted_response": generated_text,
                "response": {
                    "choices": [
                        {"message": {"content": generated_text, "role": "assistant"}}
                    ]
                }
            },
        )

        with mock.patch.dict(
                Utility.environment,
                {"llm": {"faq": "GPT3_FAQ_EMBED", "api_key": key, "url": "http://localhost"}}
        ):
            gpt3 = LLMProcessor(test_content.bot, DEFAULT_LLM)

            aioresponses.add(
                url=urljoin(
                    Utility.environment["vector"]["db"],
                    f"/collections/{gpt3.bot}_{test_content.collection}{gpt3.suffix}/points/search"
                ),
                method="POST",
                payload={
                    "result": [{
                        "id": test_content.vector_id,
                        "score": 0.80,
                        "payload": {"content": test_content.data}
                    }]
                }
            )

            response, time_elapsed = await gpt3.predict(
                query, user=user, **k_faq_action_config
            )

            assert response["content"] == generated_text

            assert gpt3.logs == [{
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a personal assistant. Answer the question according to the below context"
                    },
                    {
                        "role": "user",
                        "content": (
                            "Based on below context answer question, if answer not in context check previous logs.\n"
                            "Instructions on how to use Similarity Prompt:\n"
                            "['Python is a high-level, general-purpose programming language. "
                            "Its design philosophy emphasizes code readability with the use of significant indentation. "
                            "Python is dynamically typed and garbage-collected.']\n"
                            "Answer according to this context.\n \n"
                            "Q: What kind of language is python? \nA:"
                        )
                    }
                ],
                "raw_completion_response": {
                    "choices": [{
                        "message": {
                            "content": generated_text,
                            "role": "assistant"
                        }
                    }]
                },
                "type": "answer_query",
                "hyperparameters": hyperparameters
            }]

            assert list(aioresponses.requests.values())[0][0].kwargs["json"] == {
                "vector": embedding,
                "limit": 10,
                "with_payload": True,
                "score_threshold": 0.70
            }

            assert isinstance(time_elapsed, float)
            assert time_elapsed > 0.0

    @pytest.mark.asyncio
    @mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
    async def test_gpt3_faq_embedding_predict_with_values_with_instructions(
            self,
            mock_get_embedding,
            aioresponses):
        embedding = list(np.random.random(LLMProcessor.__embedding__))
        user = "test"
        bot = "payload_with_instruction"
        key = "test"
        llm_type = "openai"

        CognitionSchema(
            metadata=[
                {"column_name": "name", "data_type": "str", "enable_search": True, "create_embeddings": True},
                {"column_name": "city", "data_type": "str", "enable_search": True, "create_embeddings": True}
            ],
            collection_name="User_details",
            bot=bot,
            user=user
        ).save()

        test_content1 = CognitionData(
            data={"name": "Nupur", "city": "Pune"},
            content_type="json",
            collection="User_details",
            bot=bot,
            user=user
        ).save()

        test_content2 = CognitionData(
            data={"name": "Fahad", "city": "Mumbai"},
            content_type="json",
            collection="User_details",
            bot=bot,
            user=user
        ).save()

        test_content3 = CognitionData(
            data={"name": "Hitesh", "city": "Mumbai"},
            content_type="json",
            collection="User_details",
            bot=bot,
            user=user
        ).save()

        llm_secret = LLMSecret(
            llm_type=llm_type,
            api_key=key,
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        )
        llm_secret.save()

        generated_text = "Hitesh and Fahad lives in mumbai city."
        query = "List all the user lives in mumbai city"
        hyperparameters = Utility.get_default_llm_hyperparameters()

        k_faq_action_config = {
            "system_prompt": "You are a personal assistant. Answer the question according to the below context",
            "context_prompt": "Based on below context answer question, if answer not in context check previous logs.",
            "similarity_prompt": [{
                "top_results": 10,
                "similarity_threshold": 0.70,
                "use_similarity_prompt": True,
                "similarity_prompt_name": "Similarity Prompt",
                "similarity_prompt_instructions": "Answer according to this context.",
                "collection": "user_details"
            }],
            "instructions": ["Answer in a short way.", "Keep it simple."],
            "hyperparameters": hyperparameters
        }

        mock_get_embedding.return_value = embedding

        expected_body = {
            "messages": [
                {
                    "role": "system",
                    "content": "You are a personal assistant. Answer the question according to the below context"
                },
                {
                    "role": "user",
                    "content": (
                        "Based on below context answer question, if answer not in context check previous logs.\n"
                        "Instructions on how to use Similarity Prompt:\n"
                        "[{'name': 'Fahad', 'city': 'Mumbai'}, {'name': 'Hitesh', 'city': 'Mumbai'}]\n"
                        "Answer according to this context.\n \n"
                        "Answer in a short way.\n"
                        "Keep it simple. \n"
                        "Q: List all the user lives in mumbai city \nA:"
                    )
                }
            ],
            "hyperparameters": hyperparameters,
            "user": user,
            "invocation": "prompt_action"
        }

        aioresponses.add(
            url=urljoin(
                Utility.environment["llm"]["url"],
                f"/{bot}/completion/{llm_type}"
            ),
            method="POST",
            status=200,
            payload={
                "formatted_response": generated_text,
                "response": {
                    "choices": [{
                        "choices": [{
                            "finish_reason": "stop",
                            "index": 0,
                            "message": {
                                "content": generated_text,
                                "role": "assistant"
                            }
                        }]
                    }]
                }
            },
            body=expected_body
        )

        gpt3 = LLMProcessor(bot, DEFAULT_LLM)

        aioresponses.add(
            url=urljoin(
                Utility.environment["vector"]["db"],
                f"/collections/{gpt3.bot}_{test_content1.collection}{gpt3.suffix}/points/search"
            ),
            method="POST",
            payload={
                "result": [
                    {"id": test_content2.vector_id, "score": 0.80, "payload": test_content2.data},
                    {"id": test_content3.vector_id, "score": 0.80, "payload": test_content3.data}
                ]
            }
        )

        response, time_elapsed = await gpt3.predict(query, user=user, **k_faq_action_config)

        assert response["content"] == generated_text
        assert isinstance(time_elapsed, float)
        assert time_elapsed > 0.0

        assert list(aioresponses.requests.values())[0][0].kwargs["json"] == {
            "vector": embedding,
            "limit": 10,
            "with_payload": True,
            "score_threshold": 0.70
        }

    @pytest.mark.asyncio
    @mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
    async def test_gpt3_faq_embedding_predict_completion_connection_error(
            self, mock_embedding, aioresponses):
        embedding = list(np.random.random(LLMProcessor.__embedding__))
        bot = "test_gpt3_faq_embedding_predict_completion_connection_error"
        user = "test"
        key = "test"
        llm_type = "openai"

        test_content = CognitionData(
            data="Python is a high-level, general-purpose programming language. "
                 "Its design philosophy emphasizes code readability with the use of significant indentation. "
                 "Python is dynamically typed and garbage-collected.",
            collection="python",
            bot=bot,
            user=user
        ).save()

        llm_secret = LLMSecret(
            llm_type=llm_type,
            api_key=key,
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=test_content.bot,
            user=user
        )
        llm_secret.save()

        hyperparameters = Utility.get_default_llm_hyperparameters()
        query = "What kind of language is python?"

        k_faq_action_config = {
            "system_prompt": "You are a personal assistant. Answer the question according to the below context",
            "context_prompt": "Based on below context answer question, if answer not in context check previous logs.",
            "similarity_prompt": [{
                "top_results": 10,
                "similarity_threshold": 0.70,
                "use_similarity_prompt": True,
                "similarity_prompt_name": "Similarity Prompt",
                "similarity_prompt_instructions": "Answer according to this context.",
                "collection": "python"
            }],
            "hyperparameters": hyperparameters
        }

        mock_embedding.return_value = embedding

        aioresponses.add(
            url=urljoin(
                Utility.environment["llm"]["url"],
                f"/{bot}/completion/{llm_type}"
            ),
            method="POST",
            exception=Exception("Connection reset by peer!")
        )

        gpt3 = LLMProcessor(test_content.bot, DEFAULT_LLM)

        aioresponses.add(
            url=urljoin(
                Utility.environment["vector"]["db"],
                f"/collections/{gpt3.bot}_{test_content.collection}{gpt3.suffix}/points/search"
            ),
            method="POST",
            payload={
                "result": [
                    {
                        "id": test_content.vector_id,
                        "score": 0.80,
                        "payload": {"content": test_content.data}
                    }
                ]
            }
        )

        response, time_elapsed = await gpt3.predict(query, user=user, **k_faq_action_config)

        assert response == {
            "is_failure": True,
            "exception": "Internal Server Error",
            "content": None
        }

        assert gpt3.logs == [
            {
                "error": "Retrieving chat completion for the provided query. Internal Server Error"
            }
        ]

        assert list(aioresponses.requests.values())[0][0].kwargs["json"] == {
            "vector": embedding,
            "limit": 10,
            "with_payload": True,
            "score_threshold": 0.70
        }

        assert isinstance(time_elapsed, float)
        assert time_elapsed > 0.0

    @pytest.mark.asyncio
    @mock.patch(
        "kairon.shared.rest_client.AioRestClient._AioRestClient__trigger",
        autospec=True
    )
    @mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
    async def test_gpt3_faq_embedding_predict_exact_match(
            self,
            mock_get_embedding,
            mock_llm_request
    ):
        embedding = list(np.random.random(LLMProcessor.__embedding__))

        user = "test"
        bot = "test_gpt3_faq_embedding_predict_exact_match"
        key = "test"

        test_content = CognitionData(
            data=(
                "Python is a high-level, general-purpose programming language. "
                "Its design philosophy emphasizes code readability with the use "
                "of significant indentation. Python is dynamically typed and garbage-collected."
            ),
            collection="python",
            bot=bot,
            user=user
        ).save()

        llm_secret = LLMSecret(
            llm_type="openai",
            api_key=key,
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        )
        llm_secret.save()

        query = "What kind of language is python?"
        hyperparameters = Utility.get_default_llm_hyperparameters()

        k_faq_action_config = {
            "system_prompt": (
                "You are a personal assistant. Answer the question according "
                "to the below context"
            ),
            "context_prompt": (
                "Based on below context answer question, if answer not in context "
                "check previous logs."
            ),
            "similarity_prompt": [
                {
                    "top_results": 10,
                    "similarity_threshold": 0.70,
                    "use_similarity_prompt": True,
                    "similarity_prompt_name": "Similarity Prompt",
                    "similarity_prompt_instructions": "Answer according to this context.",
                    "collection": "python",
                }
            ],
            "hyperparameters": hyperparameters,
        }

        mock_get_embedding.return_value = embedding

        mock_llm_request.side_effect = ClientConnectionError()

        gpt3 = LLMProcessor(bot, DEFAULT_LLM)

        response, time_elapsed = await gpt3.predict(
            query,
            user=user,
            **k_faq_action_config
        )

        assert response == {
            "exception": "Failed to connect to service: localhost",
            "is_failure": True,
            "content": None,
        }

        assert gpt3.logs == [
            {
                "error": (
                    "Retrieving chat completion for the provided query. "
                    "Failed to connect to service: localhost"
                )
            }
        ]

        assert isinstance(time_elapsed, float)
        assert time_elapsed > 0.0

        mock_get_embedding.assert_called_once()

    @pytest.mark.asyncio
    @mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
    async def test_gpt3_faq_embedding_predict_embedding_connection_error(
            self, mock_get_embedding
    ):
        user = "test"
        bot = "test_gpt3_faq_embedding_predict_embedding_connection_error"
        key = "test"

        test_content = CognitionData(
            data=(
                "Python is a high-level, general-purpose programming language. "
                "Its design philosophy emphasizes code readability with the use "
                "of significant indentation. Python is dynamically typed and garbage-collected."
            ),
            bot=bot,
            user=user
        ).save()

        llm_secret = LLMSecret(
            llm_type="openai",
            api_key=key,
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        )
        llm_secret.save()

        hyperparameters = Utility.get_default_llm_hyperparameters()
        query = "What kind of language is python?"

        k_faq_action_config = {
            "system_prompt": "You are a personal assistant. Answer the question according to the below context",
            "context_prompt": (
                "Based on below context answer question, if answer not in context "
                "check previous logs."
            ),
            "hyperparameters": hyperparameters,
        }

        gpt3 = LLMProcessor(bot, DEFAULT_LLM)

        mock_get_embedding.side_effect = Exception("Service Unavailable")

        response, time_elapsed = await gpt3.predict(query, user=user, **k_faq_action_config)

        assert response == {
            "exception": "Service Unavailable",
            "is_failure": True,
            "content": None,
        }

        assert gpt3.logs == [
            {"error": "Creating a new embedding for the provided query. Service Unavailable"}
        ]

        assert isinstance(time_elapsed, float)
        assert time_elapsed > 0.0

        mock_get_embedding.assert_called_once()

    @pytest.mark.asyncio
    @mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
    async def test_gpt3_faq_embedding_predict_with_previous_bot_responses(
            self, mock_get_embedding, aioresponses
    ):
        embedding = list(np.random.random(LLMProcessor.__embedding__))

        llm_type = "openai"
        bot = "test_gpt3_faq_embedding_predict_with_previous_bot_responses"
        user = "test"
        key = "test"

        hyperparameters = Utility.get_default_llm_hyperparameters()

        test_content = CognitionData(
            data=(
                "Python is a high-level, general-purpose programming language. "
                "Its design philosophy emphasizes code readability with the use "
                "of significant indentation. Python is dynamically typed and garbage-collected."
            ),
            collection="python",
            bot=bot,
            user=user
        ).save()

        llm_secret = LLMSecret(
            llm_type="openai",
            api_key=key,
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        )
        llm_secret.save()

        generated_text = (
            "Python is dynamically typed, garbage-collected, high level, "
            "general purpose programming."
        )

        query = "What kind of language is python?"

        k_faq_action_config = {
            "previous_bot_responses": [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "how are you"},
            ],
            "similarity_prompt": [
                {
                    "use_similarity_prompt": True,
                    "similarity_prompt_name": "Similarity Prompt",
                    "similarity_prompt_instructions": "Answer according to this context.",
                    "collection": "python",
                }
            ],
            "hyperparameters": hyperparameters,
        }

        mock_get_embedding.return_value = embedding

        expected_body = {
            "messages": [
                {
                    "role": "system",
                    "content": "You are a personal assistant. Answer question based on the context below",
                },
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "how are you"},
                {
                    "role": "user",
                    "content": (
                        "Answer question based on the context below, if answer is not in the context "
                        "go check previous logs.\n"
                        "Instructions on how to use Similarity Prompt:\n"
                        "[\"Python is a high-level, general-purpose programming language. "
                        "Its design philosophy emphasizes code readability with the use "
                        "of significant indentation. Python is dynamically typed and garbage-collected.\"]\n"
                        "Answer according to this context.\n \n"
                        f"Q: {query} \nA:"
                    ),
                },
            ],
            "hyperparameters": hyperparameters,
            "user": user,
            "invocation": "prompt_action",
        }

        aioresponses.add(
            url=urljoin(
                Utility.environment["llm"]["url"],
                f"/{bot}/completion/{llm_type}",
            ),
            method="POST",
            status=200,
            payload={
                "formatted_response": generated_text,
                "response": {
                    "choices": [
                        {"message": {"content": generated_text, "role": "assistant"}}
                    ]
                },
            },
            body=expected_body,
        )

        gpt3 = LLMProcessor(bot, DEFAULT_LLM)

        aioresponses.add(
            url=urljoin(
                Utility.environment["vector"]["db"],
                f"/collections/{gpt3.bot}_{test_content.collection}{gpt3.suffix}/points/search",
            ),
            method="POST",
            payload={
                "result": [
                    {
                        "id": test_content.vector_id,
                        "score": 0.80,
                        "payload": {"content": test_content.data},
                    }
                ]
            },
        )

        response, time_elapsed = await gpt3.predict(query, user=user, **k_faq_action_config)
        assert response["content"] == generated_text
        assert isinstance(time_elapsed, float)
        assert time_elapsed > 0.0

        assert list(aioresponses.requests.values())[0][0].kwargs["json"] == {
            "vector": embedding,
            "limit": 10,
            "with_payload": True,
            "score_threshold": 0.70,
        }

        mock_get_embedding.assert_called_once()

    @pytest.mark.asyncio
    @mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
    async def test_gpt3_faq_embedding_predict_with_query_prompt(
            self, mock_get_embedding, aioresponses
    ):
        embedding = list(np.random.random(LLMProcessor.__embedding__))

        llm_type = "openai"
        bot = "test_gpt3_faq_embedding_predict_with_query_prompt"
        user = "test"
        key = "test"

        test_content = CognitionData(
            data="Python is a high-level, general-purpose programming language. "
                 "Its design philosophy emphasizes code readability with the use "
                 "of significant indentation. Python is dynamically typed and garbage-collected.",
            collection="python",
            bot=bot,
            user=user
        ).save()

        llm_secret = LLMSecret(
            llm_type=llm_type,
            api_key=key,
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        )
        llm_secret.save()

        generated_text = (
            "Python is dynamically typed, garbage-collected, high level, "
            "general purpose programming."
        )

        query = "What kind of language is python?"
        rephrased_query = (
            "Explain python is called high level programming language in laymen terms?"
        )

        hyperparameters = Utility.get_default_llm_hyperparameters()

        k_faq_action_config = {
            "query_prompt": {
                "query_prompt": (
                    "A programming language is a system of notation for writing "
                    "computer programs.[1] Most programming languages are text-based "
                    "formal languages, but they may also be graphical."
                ),
                "use_query_prompt": True
            },
            "similarity_prompt": [
                {
                    "use_similarity_prompt": True,
                    "similarity_prompt_name": "Similarity Prompt",
                    "similarity_prompt_instructions": "Answer according to this context.",
                    "collection": "python"
                }
            ],
            "hyperparameters": hyperparameters
        }

        mock_get_embedding.return_value = embedding

        expected_completion_body = {
            "messages": [
                {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "Answer question based on the context below, if answer is not in the context "
                        "go check previous logs.\n"
                        "Instructions on how to use Similarity Prompt:\n"
                        "[\"Python is a high-level, general-purpose programming language. "
                        "Its design philosophy emphasizes code readability with the use "
                        "of significant indentation. Python is dynamically typed and garbage-collected.\"]\n"
                        "Answer according to this context.\n \n"
                        f"Q: {rephrased_query} \nA:"
                    )
                }
            ],
            "hyperparameters": hyperparameters,
            "user": user,
            "invocation": "prompt_action"
        }

        aioresponses.add(
            url=urljoin(Utility.environment["llm"]["url"], f"/{bot}/completion/{llm_type}"),
            method="POST",
            status=200,
            payload={
                "formatted_response": generated_text,
                "response": {
                    "choices": [
                        {"message": {"content": generated_text, "role": "assistant"}}
                    ]
                }
            },
            body=expected_completion_body,
            repeat=True
        )

        gpt3 = LLMProcessor(bot, DEFAULT_LLM)

        aioresponses.add(
            url=urljoin(
                Utility.environment["vector"]["db"],
                f"/collections/{gpt3.bot}_{test_content.collection}{gpt3.suffix}/points/search"
            ),
            method="POST",
            payload={
                "result": [
                    {
                        "id": test_content.vector_id,
                        "score": 0.80,
                        "payload": {"content": test_content.data}
                    }
                ]
            }
        )

        response, time_elapsed = await gpt3.predict(
            query,
            user=user,
            **k_faq_action_config
        )

        assert response["content"] == generated_text
        assert isinstance(time_elapsed, float)
        assert time_elapsed > 0.0

        assert list(aioresponses.requests.values())[0][0].kwargs["json"] == {
            "vector": embedding,
            "limit": 10,
            "with_payload": True,
            "score_threshold": 0.70
        }
        mock_get_embedding.assert_called_once()

    @pytest.mark.asyncio
    @mock.patch.object(AioRestClient, "request", autospec=True)
    async def test_collection_exists_success(self, mock_request):
        collection_name = "test_collection"
        bot = "test_collection_exists_success"
        user = "test_new"

        llm_secret = LLMSecret(
            llm_type="openai",
            api_key="openai_key",
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        )
        llm_secret.save()

        mock_request.return_value = {"status": "ok"}

        llm_processor = LLMProcessor(bot, DEFAULT_LLM)

        result = await llm_processor.__collection_exists__(collection_name)

        mock_request.assert_called_once_with(
            mock.ANY,
            http_url=f"{llm_processor.db_url}/collections/{collection_name}",
            request_method="GET",
            headers=llm_processor.headers,
            return_json=True,
            timeout=5
        )
        assert result is True
        LLMSecret.objects.delete()

    @pytest.mark.asyncio
    @mock.patch.object(AioRestClient, "request", autospec=True)
    async def test_collection_exists_failure(self, mock_request):
        collection_name = "test_collection"
        bot = "test_collection_exists_failure"
        user = "test_new"

        llm_secret = LLMSecret(
            llm_type="openai",
            api_key="openai_key",
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        )
        llm_secret.save()

        mock_request.side_effect = Exception("Connection error")

        llm_processor = LLMProcessor(bot, DEFAULT_LLM)

        result = await llm_processor.__collection_exists__(collection_name)

        mock_request.assert_called_once_with(
            mock.ANY,
            http_url=f"{llm_processor.db_url}/collections/{collection_name}",
            request_method="GET",
            headers=llm_processor.headers,
            return_json=True,
            timeout=5
        )
        assert result is False
        LLMSecret.objects.delete()

    @pytest.mark.asyncio
    @mock.patch.object(AioRestClient, "request", autospec=True)
    async def test_delete_single_collection_success(self, mock_request):
        collection_name = "collection_to_delete"
        bot = "test_delete_single_collection_success"
        user = "test_new"

        llm_secret = LLMSecret(
            llm_type="openai",
            api_key="openai_key",
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        )
        llm_secret.save()

        mock_request.return_value = {"status": "ok"}

        llm_processor = LLMProcessor(bot, DEFAULT_LLM)

        await llm_processor._delete_single_collection(collection_name)

        mock_request.assert_called_once_with(
            mock.ANY,
            http_url=f"{llm_processor.db_url}/collections/{collection_name}",
            request_method="DELETE",
            headers=llm_processor.headers,
            return_json=False,
            timeout=5
        )
        LLMSecret.objects.delete()

    @pytest.mark.asyncio
    @mock.patch.object(AioRestClient, "request", autospec=True)
    async def test_delete_single_collection_failure(self, mock_request):
        collection_name = "collection_to_delete"
        bot = "test_delete_single_collection_success"
        user = "test_new"

        llm_secret = LLMSecret(
            llm_type="openai",
            api_key="openai_key",
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        )
        llm_secret.save()

        mock_request.side_effect = Exception("Connection error")

        llm_processor = LLMProcessor(bot, DEFAULT_LLM)

        with pytest.raises(Exception, match="Connection error"):
            await llm_processor._delete_single_collection(collection_name)

        mock_request.assert_called_once_with(
            mock.ANY,
            http_url=f"{llm_processor.db_url}/collections/{collection_name}",
            request_method="DELETE",
            headers=llm_processor.headers,
            return_json=False,
            timeout=5
        )
        LLMSecret.objects.delete()

    @pytest.mark.asyncio
    @patch("kairon.shared.actions.utils.ActionUtility.execute_request_async", new_callable=AsyncMock)
    async def test_initialize_vector_configs_success(self, mock_execute_request_async):
        bot = "test_bot"
        llm_type = "openai"
        key = "test"
        user = "test"
        llm_secret = LLMSecret(
            llm_type=llm_type,
            api_key=key,
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        )
        llm_secret.save()

        mock_response = {
            'configs': {
                'sparse_vectors_config': {'sparse': {}},
                'vectors_config': {
                    'dense': {'distance': 'Cosine', 'size': 1536},
                    'rerank': {
                        'distance': 'Cosine',
                        'multivector_config': {'comparator': 'max_sim'},
                        'size': 128
                    }
                }
            }
        }
        mock_execute_request_async.return_value = (mock_response, 200, None, None)

        processor = LLMProcessor(bot, llm_type)
        await processor.initialize_vector_configs()

        assert processor.vectors_config == {
                    'dense': {'distance': 'Cosine', 'size': 1536},
                    'rerank': {
                        'distance': 'Cosine',
                        'multivector_config': {'comparator': 'max_sim'},
                        'size': 128
                    }
                }
        assert processor.sparse_vectors_config == {'sparse': {}}

        mock_execute_request_async.assert_called_once_with(
            http_url = f"{Utility.environment['llm']['url']}/{urllib.parse.quote(bot)}/config",
            request_method="GET",
            timeout=Utility.environment['llm'].get('request_timeout', 30)
        )
        LLMSecret.objects.delete()

    @pytest.mark.asyncio
    @patch("kairon.shared.actions.utils.ActionUtility.execute_request_async", new_callable=AsyncMock)
    async def test_initialize_vector_configs_failure(self, mock_execute_request_async):
        bot = "test_bot"
        llm_type = "openai"
        key = "test"
        user = "test"
        llm_secret = LLMSecret(
            llm_type=llm_type,
            api_key=key,
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        )
        llm_secret.save()

        mock_execute_request_async.return_value = ({"message": "Error fetching data"}, 500, None, None)

        processor = LLMProcessor(bot, llm_type)

        with pytest.raises(Exception, match="Failed to fetch vector configs: Error fetching data"):
            await processor.initialize_vector_configs()

        mock_execute_request_async.assert_called_once()
        LLMSecret.objects.delete()

    @pytest.mark.asyncio
    @patch("kairon.shared.actions.utils.ActionUtility.execute_request_async", new_callable=AsyncMock)
    async def test_initialize_vector_configs_empty_response(self, mock_execute_request_async):
        bot = "test_bot"
        llm_type = "openai"
        key = "test"
        user = "test"
        llm_secret = LLMSecret(
            llm_type=llm_type,
            api_key=key,
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        )
        llm_secret.save()
        mock_execute_request_async.return_value = ({}, 200, None, None)

        processor = LLMProcessor(bot, llm_type)
        await processor.initialize_vector_configs()

        assert processor.vectors_config == {}
        assert processor.sparse_vectors_config == {}

        mock_execute_request_async.assert_called_once()
        LLMSecret.objects.delete()

    @pytest.mark.asyncio
    @patch("kairon.shared.rest_client.AioRestClient.request", new_callable=AsyncMock)
    async def test_collection_hybrid_query_success(self, mock_request):
        bot = "test_bot"
        llm_type = "openai"
        key = "test"
        user = "test"
        collection_name = "test_collection"
        limit = 5
        score_threshold = 0.7

        llm_secret = LLMSecret(
            llm_type=llm_type,
            api_key=key,
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        )
        llm_secret.save()

        embeddings = {
                "dense": [
                    0.01926439255475998,
                    -0.0645047277212143
                ],
                "sparse": {
                    "values": [
                        1.6877434821696136
                    ],
                    "indices": [
                        613153351
                    ]
                },
                "rerank": [
                    [
                        0.03842781484127045,
                        0.10881761461496353,
                    ],
                    [
                        0.046593569219112396,
                        -0.023154577240347862
                    ]
                ]
            }

        mock_response = {
           "result":{
              "points":[
                 {
                    "id":2,
                    "version":0,
                    "score":1.5,
                    "payload":{
                       "content":"Great Wall of China is a historic fortification stretching thousands of miles, built to protect Chinese states from invasions."
                    }
                 },
                 {
                    "id":1,
                    "version":0,
                    "score":1.0,
                    "payload":{
                       "content":"Taj Mahal is a white marble mausoleum in India, built by Mughal Emperor Shah Jahan in memory of his wife Mumtaz Mahal."
                    }
                 }
              ]
           },
           "status":"ok",
           "time":0.003191196
        }

        mock_request.return_value = mock_response

        processor = LLMProcessor(bot, llm_type)
        response = await processor.__collection_hybrid_query__(collection_name, embeddings, limit, score_threshold)

        assert response == mock_response
        mock_request.assert_called_once_with(
            http_url=f"{Utility.environment['vector']['db']}/collections/{collection_name}/points/query",
            request_method="POST",
            headers={},
            request_body={
                "prefetch": [
                    {"query": embeddings.get("dense", []), "using": "dense", "limit": limit * 2},
                    {"query": embeddings.get("rerank", []), "using": "rerank", "limit": limit * 2},
                    {"query": embeddings.get("sparse", {}), "using": "sparse", "limit": limit * 2}
                ],
                "query": {"fusion": "rrf"},
                "with_payload": True,
                "score_threshold": score_threshold,
                "limit": limit
            },
            return_json=True,
            timeout=5
        )
        LLMSecret.objects.delete()

    @pytest.mark.asyncio
    @patch("kairon.shared.rest_client.AioRestClient.request", new_callable=AsyncMock)
    async def test_collection_hybrid_query_request_failure(self, mock_request):
        bot = "test_bot"
        llm_type = "openai"
        key = "test"
        user = "test"
        collection_name = "test_collection"
        limit = 5
        score_threshold = 0.7

        llm_secret = LLMSecret(
            llm_type=llm_type,
            api_key=key,
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        )
        llm_secret.save()

        embeddings = {
            "dense": [0.01926439255475998, -0.0645047277212143],
            "sparse": {"values": [1.6877434821696136], "indices": [613153351]},
            "rerank": [[0.03842781484127045, 0.10881761461496353], [0.046593569219112396, -0.023154577240347862]]
        }

        mock_request.side_effect = Exception("Request failed")

        processor = LLMProcessor(bot, llm_type)
        with pytest.raises(Exception, match="Request failed"):
            await processor.__collection_hybrid_query__(collection_name, embeddings, limit, score_threshold)

        mock_request.assert_called_once()
        LLMSecret.objects.delete()

    @pytest.mark.asyncio
    @patch("kairon.shared.rest_client.AioRestClient.request", new_callable=AsyncMock)
    async def test_collection_hybrid_query_empty_response(self, mock_request):
        bot = "test_bot"
        llm_type = "openai"
        key = "test"
        user = "test"
        collection_name = "test_collection"
        limit = 5
        score_threshold = 0.7

        llm_secret = LLMSecret(
            llm_type=llm_type,
            api_key=key,
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        )
        llm_secret.save()

        embeddings = {
            "dense": [0.01926439255475998, -0.0645047277212143],
            "sparse": {"values": [1.6877434821696136], "indices": [613153351]},
            "rerank": [[0.03842781484127045, 0.10881761461496353], [0.046593569219112396, -0.023154577240347862]]
        }

        mock_request.return_value = {}

        processor = LLMProcessor(bot, llm_type)
        response = await processor.__collection_hybrid_query__(collection_name, embeddings, limit, score_threshold)

        assert response == {}
        mock_request.assert_called_once()
        LLMSecret.objects.delete()

    @pytest.mark.asyncio
    @patch("kairon.shared.llm.processor.LLMProcessor._sparse_embedding")
    def test_sparse_embedding_single_sentence(self, mock_sparse):
        bot = "test_bot"
        llm_type = "openai"
        key = "test"
        user = "test"

        llm_secret = LLMSecret(
            llm_type=llm_type,
            api_key=key,
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        )
        llm_secret.save()

        processor = LLMProcessor(bot, llm_type)
        mock_sparse.passage_embed.return_value = iter([
            MagicMock(values=np.array([1.62, 1.87]), indices=np.array([101, 202]))
        ])

        result = processor.get_sparse_embedding(["Hello"])

        assert result == [{"values": [1.62, 1.87], "indices": [101, 202]}]
        mock_sparse.passage_embed.assert_called_once_with(["Hello"])
        LLMSecret.objects.delete()

    @pytest.mark.asyncio
    @patch("kairon.shared.llm.processor.LLMProcessor._sparse_embedding")
    async def test_sparse_embedding_multiple_sentences(self, mock_sparse):
        bot = "test_bot"
        llm_type = "openai"
        key = "test"
        user = "test"

        llm_secret = LLMSecret(
            llm_type=llm_type,
            api_key=key,
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        )
        llm_secret.save()

        processor = LLMProcessor(bot, llm_type)
        mock_sparse.passage_embed.return_value = iter([
            MagicMock(values=np.array([1.62, 1.87]), indices=np.array([101, 202])),
            MagicMock(values=np.array([2.71, 3.14]), indices=np.array([303, 404]))
        ])

        result = processor.get_sparse_embedding(["Hello", "World"])

        assert result == [
            {"values": [1.62, 1.87], "indices": [101, 202]},
            {"values": [2.71, 3.14], "indices": [303, 404]}
        ]
        mock_sparse.passage_embed.assert_called_once_with(["Hello", "World"])
        LLMSecret.objects.delete()

    @pytest.mark.asyncio
    @patch("kairon.shared.llm.processor.LLMProcessor._sparse_embedding")
    async def test_sparse_embedding_empty_list(self, mock_sparse):
        bot = "test_bot"
        llm_type = "openai"
        key = "test"
        user = "test"

        llm_secret = LLMSecret(
            llm_type=llm_type,
            api_key=key,
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        )
        llm_secret.save()

        processor = LLMProcessor(bot, llm_type)
        mock_sparse.passage_embed.return_value = iter([])

        result = processor.get_sparse_embedding([])

        assert result == []
        mock_sparse.passage_embed.assert_called_once_with([])
        LLMSecret.objects.delete()

    @pytest.mark.asyncio
    @patch("kairon.shared.llm.processor.LLMProcessor._sparse_embedding")
    async def test_sparse_embedding_raises_exception(self, mock_sparse):
        bot = "test_bot"
        llm_type = "openai"
        key = "test"
        user = "test"

        llm_secret = LLMSecret(
            llm_type=llm_type,
            api_key=key,
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        )
        llm_secret.save()

        processor = LLMProcessor(bot, llm_type)

        mock_sparse.passage_embed.side_effect = Exception("Not Found")

        with pytest.raises(Exception, match="Error processing sparse embeddings: Not Found"):
            processor.get_sparse_embedding(["Text of error case"])

        mock_sparse.passage_embed.assert_called_once_with(["Text of error case"])
        LLMSecret.objects.delete()

    @pytest.mark.asyncio
    @patch("kairon.shared.llm.processor.LLMProcessor._rerank_embedding")
    def test_rerank_embedding_single_sentence(self, mock_rerank):
        bot = "test_bot"
        llm_type = "openai"
        key = "test"
        user = "test"

        llm_secret = LLMSecret(
            llm_type=llm_type,
            api_key=key,
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        )
        llm_secret.save()

        processor = LLMProcessor(bot, llm_type)

        mock_rerank.passage_embed.return_value = iter([
            np.array([[0.11, 0.22, 0.33], [0.44, 0.55, 0.66]])
        ])

        result = processor.get_rerank_embedding(["Hello"])

        assert result == [
            [[0.11, 0.22, 0.33], [0.44, 0.55, 0.66]]
        ]

        mock_rerank.passage_embed.assert_called_once_with(["Hello"])
        LLMSecret.objects.delete()

    @pytest.mark.asyncio
    @patch("kairon.shared.llm.processor.LLMProcessor._rerank_embedding")
    def test_rerank_embedding_multiple_sentences(self, mock_rerank):
        bot = "test_bot"
        llm_type = "openai"
        key = "test"
        user = "test"

        llm_secret = LLMSecret(
            llm_type=llm_type,
            api_key=key,
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        )
        llm_secret.save()

        processor = LLMProcessor(bot, llm_type)

        mock_rerank.passage_embed.return_value = iter([
            np.array([[0.11, 0.22, 0.33], [0.44, 0.55, 0.66]]),
            np.array([[0.77, 0.88, 0.99], [1.11, 1.22, 1.33]])
        ])

        result = processor.get_rerank_embedding(["Hello", "World"])

        assert result == [
            [[0.11, 0.22, 0.33], [0.44, 0.55, 0.66]],
            [[0.77, 0.88, 0.99], [1.11, 1.22, 1.33]]
        ]

        mock_rerank.passage_embed.assert_called_once_with(["Hello", "World"])
        LLMSecret.objects.delete()

    @pytest.mark.asyncio
    @patch("kairon.shared.llm.processor.LLMProcessor._rerank_embedding")
    def test_rerank_embedding_empty_sentences(self, mock_rerank):
        bot = "test_bot"
        llm_type = "openai"
        key = "test"
        user = "test"

        llm_secret = LLMSecret(
            llm_type=llm_type,
            api_key=key,
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        )
        llm_secret.save()

        processor = LLMProcessor(bot, llm_type)

        mock_rerank.passage_embed.return_value = iter([])

        result = processor.get_rerank_embedding([])

        assert result == []

        mock_rerank.passage_embed.assert_called_once_with([])
        LLMSecret.objects.delete()

    @pytest.mark.asyncio
    @patch("kairon.shared.llm.processor.LLMProcessor._rerank_embedding")
    def test_rerank_embedding_raises_exception(self, mock_rerank):
        bot = "test_bot"
        llm_type = "openai"
        key = "test"
        user = "test"

        llm_secret = LLMSecret(
            llm_type=llm_type,
            api_key=key,
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        )
        llm_secret.save()

        processor = LLMProcessor(bot, llm_type)

        mock_rerank.passage_embed.side_effect = Exception("Not Found")

        with pytest.raises(Exception, match="Error processing rerank embeddings: Not Found"):
            processor.get_rerank_embedding(["Text of error case"])

        mock_rerank.passage_embed.assert_called_once_with(["Text of error case"])
        LLMSecret.objects.delete()

    # @pytest.mark.asyncio
    # @mock.patch.object(litellm, "aembedding", autospec=True)
    # @patch("kairon.shared.llm.processor.LLMProcessor.get_sparse_embedding")
    # @patch("kairon.shared.llm.processor.LLMProcessor.get_rerank_embedding")
    # async def test_get_embedding_single_text(self, mock_rerank, mock_sparse, mock_dense):
    #     bot = "test_bot"
    #     llm_type = "openai"
    #     key = "test"
    #     user = "test"
    #
    #     llm_secret = LLMSecret(
    #         llm_type=llm_type,
    #         api_key=key,
    #         models=["model1", "model2"],
    #         api_base_url="https://api.example.com",
    #         bot=bot,
    #         user=user
    #     )
    #     llm_secret.save()
    #
    #     processor = LLMProcessor(bot, llm_type)
    #     text = "Hello"
    #
    #     embedding = np.random.random(1536).tolist()
    #     mock_dense.return_value = litellm.EmbeddingResponse(
    #         **{'data': [{'embedding': embedding}]}
    #     )
    #
    #     bm25_embedding = [{"indices": [1850593538, 11711171], "values": [1.66, 1.66]}]
    #     mock_sparse.return_value = bm25_embedding
    #
    #     colbertv2_0_embedding = [[np.random.random(128).tolist()]]
    #     mock_rerank.return_value = colbertv2_0_embedding
    #
    #     result = await processor.get_embedding(text, user)
    #
    #     assert result == {
    #         "dense": embedding,
    #         "sparse": bm25_embedding[0],
    #         "rerank": colbertv2_0_embedding[0]
    #     }
    #
    #     mock_dense.assert_called_once_with(
    #         model="text-embedding-3-large",
    #         input=[text],
    #         metadata={'user': user, 'bot': bot, 'invocation': None},
    #         api_key=key,
    #         num_retries=3
    #     )
    #
    #     mock_sparse.assert_called_once_with([text])
    #     mock_rerank.assert_called_once_with([text])
    #
    #     LLMSecret.objects.delete()
    #
    # @pytest.mark.asyncio
    # @mock.patch.object(litellm, "aembedding", autospec=True)
    # @patch("kairon.shared.llm.processor.LLMProcessor.get_sparse_embedding")
    # @patch("kairon.shared.llm.processor.LLMProcessor.get_rerank_embedding")
    # async def test_get_embedding_multiple_texts(
    #     self, mock_rerank, mock_sparse, mock_dense
    # ):
    #     bot = "test_bot"
    #     llm_type = "openai"
    #     key = "test"
    #     user = "test"
    #
    #     llm_secret = LLMSecret(
    #         llm_type=llm_type,
    #         api_key=key,
    #         models=["model1", "model2"],
    #         api_base_url="https://api.example.com",
    #         bot=bot,
    #         user=user
    #     )
    #     llm_secret.save()
    #
    #     processor = LLMProcessor(bot, llm_type)
    #
    #     texts = ["Hello", "World"]
    #
    #     embedding = np.random.random(1536).tolist()
    #     mock_dense.return_value = litellm.EmbeddingResponse(
    #         **{'data': [{'embedding': embedding}, {'embedding': embedding}]}
    #     )
    #
    #     bm25_embeddings = [
    #         {"indices": [1850593538, 11711171], "values": [1.66, 1.66]},
    #         {"indices": [1850593538, 11711171], "values": [1.66, 1.66]}
    #     ]
    #     mock_sparse.return_value = bm25_embeddings
    #
    #     colbertv2_0_embeddings = [
    #         [np.random.random(128).tolist()],
    #         [np.random.random(128).tolist()]
    #     ]
    #     mock_rerank.return_value = colbertv2_0_embeddings
    #
    #     result = await processor.get_embedding(texts, user)
    #
    #     assert result == {
    #         "dense": [embedding, embedding],
    #         "sparse": bm25_embeddings,
    #         "rerank": colbertv2_0_embeddings
    #     }
    #
    #     mock_dense.assert_called_once_with(
    #         model="text-embedding-3-large",
    #         input=texts,
    #         metadata={'user': user, 'bot': bot, 'invocation': None},
    #         api_key=key,
    #         num_retries=3
    #     )
    #
    #     mock_sparse.assert_called_once_with(texts)
    #     mock_rerank.assert_called_once_with(texts)
    #
    #     LLMSecret.objects.delete()
    #
    # @pytest.mark.asyncio
    # @mock.patch.object(litellm, "aembedding", autospec=True)
    # @patch("kairon.shared.llm.processor.LLMProcessor.get_sparse_embedding")
    # @patch("kairon.shared.llm.processor.LLMProcessor.get_rerank_embedding")
    # async def test_get_embedding_dense_failure(self, mock_rerank, mock_sparse, mock_dense):
    #     bot = "test_bot"
    #     llm_type = "openai"
    #     key = "test"
    #     user = "test"
    #
    #     llm_secret = LLMSecret(
    #         llm_type=llm_type,
    #         api_key=key,
    #         models=["model1", "model2"],
    #         api_base_url="https://api.example.com",
    #         bot=bot,
    #         user=user
    #     )
    #     llm_secret.save()
    #
    #     processor = LLMProcessor(bot, llm_type)
    #     texts = ["Hello", "World"]
    #
    #     mock_dense.side_effect = Exception("Dense embedding failed")
    #
    #     bm25_embeddings = [
    #         {"indices": [1850593538, 11711171], "values": [1.66, 1.66]},
    #         {"indices": [1850593538, 11711171], "values": [1.66, 1.66]}
    #     ]
    #     mock_sparse.return_value = bm25_embeddings
    #
    #     colbertv2_0_embeddings = [
    #         [np.random.random(128).tolist()],
    #         [np.random.random(128).tolist()]
    #     ]
    #     mock_rerank.return_value = colbertv2_0_embeddings
    #
    #     with pytest.raises(Exception, match="Failed to fetch embeddings: Dense embedding failed"):
    #         await processor.get_embedding(texts, user)
    #
    #     mock_dense.assert_called_once_with(
    #         model="text-embedding-3-large",
    #         input=texts,
    #         metadata={'user': user, 'bot': bot, 'invocation': None},
    #         api_key=key,
    #         num_retries=3
    #     )
    #
    #     LLMSecret.objects.delete()
    #
    # @pytest.mark.asyncio
    # @mock.patch.object(litellm, "aembedding", autospec=True)
    # @patch("kairon.shared.llm.processor.LLMProcessor.get_sparse_embedding")
    # @patch("kairon.shared.llm.processor.LLMProcessor.get_rerank_embedding")
    # async def test_get_embedding_sparse_failure(self, mock_rerank, mock_sparse, mock_dense):
    #     bot = "test_bot"
    #     llm_type = "openai"
    #     key = "test"
    #     user = "test"
    #
    #     llm_secret = LLMSecret(
    #         llm_type=llm_type,
    #         api_key=key,
    #         models=["model1", "model2"],
    #         api_base_url="https://api.example.com",
    #         bot=bot,
    #         user=user
    #     )
    #     llm_secret.save()
    #
    #     processor = LLMProcessor(bot, llm_type)
    #     texts = ["Hello", "World"]
    #
    #     embedding = np.random.random(1536).tolist()
    #     mock_dense.return_value = litellm.EmbeddingResponse(
    #         **{'data': [{'embedding': embedding}, {'embedding': embedding}]}
    #     )
    #
    #     mock_sparse.side_effect = Exception("Sparse embedding failed")
    #
    #     colbertv2_0_embeddings = [
    #         [np.random.random(128).tolist()],
    #         [np.random.random(128).tolist()]
    #     ]
    #     mock_rerank.return_value = colbertv2_0_embeddings
    #
    #     with pytest.raises(Exception, match="Failed to fetch embeddings: Sparse embedding failed"):
    #         await processor.get_embedding(texts, user)
    #
    #     mock_dense.assert_called_once_with(
    #         model="text-embedding-3-large",
    #         input=texts,
    #         metadata={'user': user, 'bot': bot, 'invocation': None},
    #         api_key=key,
    #         num_retries=3
    #     )
    #
    #     LLMSecret.objects.delete()
    #
    # @pytest.mark.asyncio
    # @mock.patch.object(litellm, "aembedding", autospec=True)
    # @patch("kairon.shared.llm.processor.LLMProcessor.get_sparse_embedding")
    # @patch("kairon.shared.llm.processor.LLMProcessor.get_rerank_embedding")
    # async def test_get_embedding_rerank_failure(self, mock_rerank, mock_sparse, mock_dense):
    #     bot = "test_bot"
    #     llm_type = "openai"
    #     key = "test"
    #     user = "test"
    #
    #     llm_secret = LLMSecret(
    #         llm_type=llm_type,
    #         api_key=key,
    #         models=["model1", "model2"],
    #         api_base_url="https://api.example.com",
    #         bot=bot,
    #         user=user
    #     )
    #     llm_secret.save()
    #
    #     processor = LLMProcessor(bot, llm_type)
    #     texts = ["Hello", "World"]
    #
    #     embedding = np.random.random(1536).tolist()
    #     mock_dense.return_value = litellm.EmbeddingResponse(
    #         **{'data': [{'embedding': embedding}, {'embedding': embedding}]}
    #     )
    #
    #     bm25_embeddings = [
    #         {"indices": [1850593538, 11711171], "values": [1.66, 1.66]},
    #         {"indices": [1850593538, 11711171], "values": [1.66, 1.66]}
    #     ]
    #     mock_sparse.return_value = bm25_embeddings
    #
    #     mock_rerank.side_effect = Exception("Failed to fetch embeddings: Rerank embedding failed")
    #
    #     with pytest.raises(Exception, match="Rerank embedding failed"):
    #         await processor.get_embedding(texts, user)
    #
    #     mock_dense.assert_called_once_with(
    #         model="text-embedding-3-large",
    #         input=texts,
    #         metadata={'user': user, 'bot': bot, 'invocation': None},
    #         api_key=key,
    #         num_retries=3
    #     )
    #
    #     LLMSecret.objects.delete()

    def test_load_sparse_embedding_model_already_initialized(self):
        """Test that the sparse embedding model loads correctly when LLMProcessor is initialized."""
        bot = "test_bot"
        llm_type = "openai"
        key = "test"
        user = "test"

        llm_secret = LLMSecret(
            llm_type=llm_type,
            api_key=key,
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        )
        llm_secret.save()

        LLMProcessor._sparse_embedding = SparseTextEmbedding("Qdrant/bm25")

        log_output = StringIO()
        logger.add(log_output, format="{message}")

        processor = LLMProcessor(bot="test_bot", llm_type="openai")

        logger.remove()
        log_contents = log_output.getvalue()

        assert isinstance(LLMProcessor._sparse_embedding, SparseTextEmbedding)
        assert "SPARSE MODEL LOADED" not in log_contents

        LLMSecret.objects.delete()

    def test_load_sparse_embedding_model_not_initialized(self):
        """Test that the sparse embedding model loads correctly when LLMProcessor is not initialized."""
        bot = "test_bot"
        llm_type = "openai"
        key = "test"
        user = "test"

        llm_secret = LLMSecret(
            llm_type=llm_type,
            api_key=key,
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        )
        llm_secret.save()

        log_output = StringIO()
        logger.add(log_output, format="{message}")

        LLMProcessor._sparse_embedding = None
        LLMProcessor.load_sparse_embedding_model()

        logger.remove()
        log_contents = log_output.getvalue()

        assert isinstance(LLMProcessor._sparse_embedding, SparseTextEmbedding)
        assert "SPARSE MODEL LOADED" in log_contents
        LLMSecret.objects.delete()

    def test_load_sparse_embedding_model_fallback_cache(self):
        """Test that the sparse embedding model falls back to the Kairon cache if Hugging Face cache is missing."""
        bot = "test_bot"
        llm_type = "openai"
        key = "test"
        user = "test"

        llm_secret = LLMSecret(
            llm_type=llm_type,
            api_key=key,
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        )
        llm_secret.save()

        with patch("os.path.exists", return_value=False), \
             patch("kairon.shared.llm.processor.SparseTextEmbedding") as mock_sparse:

            mock_instance = mock_sparse.return_value
            LLMProcessor._sparse_embedding = None

            log_output = StringIO()
            logger.add(log_output, format="{message}")

            LLMProcessor.load_sparse_embedding_model()

            logger.remove()
            log_contents = log_output.getvalue()

            mock_sparse.assert_called_once_with("Qdrant/bm25", cache_dir="./kairon/pre-trained-models/")
            assert LLMProcessor._sparse_embedding is mock_instance
            assert "SPARSE MODEL LOADED" in log_contents

        LLMSecret.objects.delete()

    def test_load_sparse_embedding_model_hf_cache(self):
        """Test that the sparse embedding model falls back to the Kairon cache if Hugging Face cache is missing."""
        bot = "test_bot"
        llm_type = "openai"
        key = "test"
        user = "test"

        llm_secret = LLMSecret(
            llm_type=llm_type,
            api_key=key,
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        )
        llm_secret.save()

        with patch("os.path.exists", return_value=True):
            LLMProcessor._sparse_embedding = None

            log_output = StringIO()
            logger.add(log_output, format="{message}")

            LLMProcessor.load_sparse_embedding_model()

            logger.remove()
            log_contents = log_output.getvalue()

            assert isinstance(LLMProcessor._sparse_embedding, SparseTextEmbedding)
            assert "SPARSE MODEL LOADED" in log_contents

        LLMSecret.objects.delete()

    def test_load_rerank_embedding_model_not_initialized(self):
        """Test that the sparse embedding model loads correctly when LLMProcessor is not initialized."""
        bot = "test_bot"
        llm_type = "openai"
        key = "test"
        user = "test"

        llm_secret = LLMSecret(
            llm_type=llm_type,
            api_key=key,
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        )
        llm_secret.save()

        log_output = StringIO()
        logger.add(log_output, format="{message}")

        LLMProcessor._rerank_embedding = None
        LLMProcessor.load_rerank_embedding_model()

        logger.remove()
        log_contents = log_output.getvalue()

        assert isinstance(LLMProcessor._rerank_embedding, LateInteractionTextEmbedding)
        assert "RERANK MODEL LOADED" in log_contents
        LLMSecret.objects.delete()

    def test_load_rerank_embedding_model_hf_cache(self):
        """Test that the sparse embedding model falls back to the Kairon cache if Hugging Face cache is missing."""
        bot = "test_bot"
        llm_type = "openai"
        key = "test"
        user = "test"

        llm_secret = LLMSecret(
            llm_type=llm_type,
            api_key=key,
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        )
        llm_secret.save()

        with patch("os.path.exists", return_value=True):
            LLMProcessor._rerank_embedding = None

            log_output = StringIO()
            logger.add(log_output, format="{message}")

            LLMProcessor.load_rerank_embedding_model()

            logger.remove()
            log_contents = log_output.getvalue()

            assert isinstance(LLMProcessor._rerank_embedding, LateInteractionTextEmbedding)
            assert "RERANK MODEL LOADED" in log_contents

        LLMSecret.objects.delete()