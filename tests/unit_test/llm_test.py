import os
from urllib.parse import urljoin
import ujson as json
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


class TestLLM:
    @pytest.fixture(autouse=True, scope="class")
    def init_connection(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))

    @pytest.mark.asyncio
    @mock.patch.object(litellm, "aembedding", autospec=True)
    async def test_gpt3_faq_embedding_train(self, mock_embedding, aioresponses):
        bot = "test_embed_faq"
        user = "test"
        value = "nupurkhare"
        test_content = CognitionData(
            data="Welcome! Are you completely new to programming? If not then we presume you will be looking for information about why and how to get started with Python",
            bot=bot, user=user).save()
        llm_secret = LLMSecret(
            llm_type="openai",
            api_key= value,
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        )
        llm_secret.save()

        embedding = list(np.random.random(LLMProcessor.__embedding__))
        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': llm_secret},
                                                   'vector': {'db': "http://kairon:6333", "key": None}}):
            mock_embedding.return_value = litellm.EmbeddingResponse(**{'data': [{'embedding': embedding}]})
            gpt3 = LLMProcessor(test_content.bot, DEFAULT_LLM)

            aioresponses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections"),
                method="GET",
                payload={"time": 0, "status": "ok", "result": {"collections": []}})

            aioresponses.add(
                method="DELETE",
                url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.suffix}"),
            )

            aioresponses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.suffix}"),
                method="PUT",
                status=200
            )

            aioresponses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.suffix}/points"),
                method="PUT",
                payload={"result": {"operation_id": 0, "status": "acknowledged"}, "status": "ok", "time": 0.003612634}
            )

            response = await gpt3.train(user=user)
            assert response['faq'] == 1

            assert list(aioresponses.requests.values())[1][0].kwargs['json'] == {'name': gpt3.bot + gpt3.suffix,
                                                                                 'vectors': gpt3.vector_config}
            assert list(aioresponses.requests.values())[2][0].kwargs['json'] == {
                'points': [{'id': test_content.vector_id,
                            'vector': embedding,
                            'payload': {'content': test_content.data}
                            }]}

            expected = {"model": "text-embedding-3-large",
                        "input": [test_content.data], 'metadata': {'user': user, 'bot': bot, 'invocation': None},
                        "api_key": value,
                        "num_retries": 3}
            assert not DeepDiff(mock_embedding.call_args[1], expected, ignore_order=True)

    @pytest.mark.asyncio
    @mock.patch.object(litellm, "aembedding", autospec=True)
    async def test_gpt3_faq_embedding_train_payload_text(self, mock_embedding, aioresponses):
        bot = "test_embed_faq_text"
        user = "test"
        value = "nupurkhare"
        CognitionSchema(
            metadata=[{"column_name": "country", "data_type": "str", "enable_search": True, "create_embeddings": True},
                      {"column_name": "lang", "data_type": "str", "enable_search": False, "create_embeddings": True},
                      {"column_name": "role", "data_type": "str", "enable_search": True, "create_embeddings": True}],
            collection_name="Country_details",
            bot=bot, user=user).save()
        CognitionSchema(
            metadata=[{"column_name": "name", "data_type": "str", "enable_search": True, "create_embeddings": True},
                      {"column_name": "city", "data_type": "str", "enable_search": False, "create_embeddings": True}],
            collection_name="User_details",
            bot=bot, user=user
        ).save()
        test_content_two = CognitionData(
            data={"country": "Spain", "lang": "spanish"},
            content_type="json",
            collection="Country_details",
            bot=bot, user=user).save()
        test_content_three = CognitionData(
            data={"role": "ds", "lang": "spanish"},
            content_type="json",
            collection="Country_details",
            bot=bot, user=user).save()
        test_content = CognitionData(
            data={"name": "Nupur", "city": "Pune"},
            content_type="json",
            collection="User_details",
            bot=bot, user=user).save()

        llm_secret = LLMSecret(
            llm_type="openai",
            api_key=value,
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        )
        llm_secret.save()

        embedding = list(np.random.random(LLMProcessor.__embedding__))
        mock_embedding.side_effect = (
        litellm.EmbeddingResponse(**{'data': [{'embedding': embedding}, {'embedding': embedding}]}),
        litellm.EmbeddingResponse(**{'data': [{'embedding': embedding}]}))
        gpt3 = LLMProcessor(bot, DEFAULT_LLM)
        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': llm_secret}}):
            aioresponses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections"),
                method="GET",
                payload={"time": 0, "status": "ok",
                         "result": {"collections": [{"name": "test_embed_faq_text_swift_faq_embd"},
                                                    {"name": "example_bot_swift_faq_embd"}]}}
            )

            aioresponses.add(
                method="DELETE",
                url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}_swift{gpt3.suffix}"),
            )

            aioresponses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}_user_details{gpt3.suffix}"),
                method="PUT",
                status=200
            )

            aioresponses.add(
                url=urljoin(Utility.environment['vector']['db'],
                            f"/collections/{gpt3.bot}_user_details{gpt3.suffix}/points"),
                method="PUT",
                payload={"result": {"operation_id": 0, "status": "acknowledged"}, "status": "ok", "time": 0.003612634}
            )

            aioresponses.add(
                url=urljoin(Utility.environment['vector']['db'],
                            f"/collections/{gpt3.bot}_country_details{gpt3.suffix}"),
                method="PUT",
                status=200
            )

            aioresponses.add(
                url=urljoin(Utility.environment['vector']['db'],
                            f"/collections/{gpt3.bot}_country_details{gpt3.suffix}/points"),
                method="PUT",
                payload={"result": {"operation_id": 0, "status": "acknowledged"}, "status": "ok", "time": 0.003612634}
            )

            aioresponses.add(
                url=urljoin(Utility.environment['vector']['db'],
                            f"/collections/test_embed_faq_text_country_details_faq_embd/points"),
                method="PUT",
                payload={"result": {"operation_id": 0, "status": "acknowledged"}, "status": "ok", "time": 0.003612634}
            )

            response = await gpt3.train(user=user)
            assert response['faq'] == 3

            assert list(aioresponses.requests.values())[2][0].kwargs['json'] == {
                'name': f"{gpt3.bot}_country_details{gpt3.suffix}",
                'vectors': gpt3.vector_config}
            assert list(aioresponses.requests.values())[3][0].kwargs['json'] == {
                'points': [{'id': test_content_two.vector_id,
                            'vector': embedding,
                            'payload': {'country': 'Spain'}},
                           {'id': test_content_three.vector_id,
                            'vector': embedding,
                            'payload': {'role': 'ds'}}
                           ]}
            assert list(aioresponses.requests.values())[4][0].kwargs['json'] == {
                'name': f"{gpt3.bot}_user_details{gpt3.suffix}",
                'vectors': gpt3.vector_config}
            assert list(aioresponses.requests.values())[5][0].kwargs['json'] == {
                'points': [{'id': test_content.vector_id,
                            'vector': embedding,
                            'payload': {'name': 'Nupur'}}]}
            assert response['faq'] == 3

            expected = {"model": "text-embedding-3-large",
                        "input": [json.dumps(test_content.data)],
                        'metadata': {'user': user, 'bot': bot, 'invocation': None},
                        "api_key": value,
                        "num_retries": 3}
            assert not DeepDiff(mock_embedding.call_args[1], expected, ignore_order=True)

    @pytest.mark.asyncio
    @mock.patch.object(litellm, "aembedding", autospec=True)
    async def test_gpt3_faq_embedding_train_payload_with_int(self, mock_embedding, aioresponses):
        bot = "test_embed_faq_json"
        user = "test"
        value = "nupurkhare"
        CognitionSchema(
            metadata=[{"column_name": "name", "data_type": "str", "enable_search": True, "create_embeddings": True},
                      {"column_name": "age", "data_type": "int", "enable_search": True, "create_embeddings": False},
                      {"column_name": "color", "data_type": "str", "enable_search": True, "create_embeddings": True}],
            collection_name="payload_with_int",
            bot=bot, user=user).save()
        test_content = CognitionData(
            data={"name": "Ram", "age": 23, "color": "red"},
            content_type="json",
            collection="payload_with_int",
            bot=bot, user=user).save()

        llm_secret = LLMSecret(
            llm_type="openai",
            api_key=value,
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        )
        llm_secret.save()

        embedding = list(np.random.random(LLMProcessor.__embedding__))
        input = {"name": "Ram", "color": "red"}
        mock_embedding.return_value = litellm.EmbeddingResponse(**{'data': [{'embedding': embedding}]})

        gpt3 = LLMProcessor(bot, DEFAULT_LLM)
        aioresponses.add(
            url=urljoin(Utility.environment['vector']['db'],
                        f"/collections/test_embed_faq_json_payload_with_int_faq_embd"),
            method="PUT",
            status=200
        )
        aioresponses.add(
            url=urljoin(Utility.environment['vector']['db'], f"/collections"),
            method="GET",
            payload={"time": 0, "status": "ok", "result": {"collections": []}})

        aioresponses.add(
            url=urljoin(Utility.environment['vector']['db'],
                        f"/collections/test_embed_faq_json_payload_with_int_faq_embd/points"),
            method="PUT",
            payload={"result": {"operation_id": 0, "status": "acknowledged"}, "status": "ok", "time": 0.003612634}
        )

        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': llm_secret}}):
            response = await gpt3.train(user=user)
            assert response['faq'] == 1

            assert list(aioresponses.requests.values())[1][0].kwargs['json'] == {
                'name': 'test_embed_faq_json_payload_with_int_faq_embd',
                'vectors': gpt3.vector_config}
            assert list(aioresponses.requests.values())[2][0].kwargs['json'] == {
                'points': [{'id': test_content.vector_id,
                            'vector': embedding,
                            'payload': {'name': 'Ram', 'age': 23, 'color': 'red'}
                            }]}

            expected = {"model": "text-embedding-3-large",
                        "input": [json.dumps(input)], 'metadata': {'user': user, 'bot': bot, 'invocation': None},
                        "api_key": value,
                        "num_retries": 3}
            assert not DeepDiff(mock_embedding.call_args[1], expected, ignore_order=True)

    @pytest.mark.asyncio
    @mock.patch.object(litellm, "aembedding", autospec=True)
    async def test_gpt3_faq_embedding_train_int(self, mock_embedding, aioresponses):
        bot = "test_int"
        user = "test"
        value = "nupurkhare"
        CognitionSchema(
            metadata=[{"column_name": "name", "data_type": "str", "enable_search": True, "create_embeddings": True},
                      {"column_name": "age", "data_type": "int", "enable_search": True, "create_embeddings": False},
                      {"column_name": "color", "data_type": "str", "enable_search": True, "create_embeddings": True}],
            collection_name="embd_int",
            bot=bot, user=user).save()
        test_content = CognitionData(
            data={"name": "Ram", "age": 23, "color": "red"},
            content_type="json",
            collection="embd_int",
            bot=bot, user=user).save()

        llm_secret = LLMSecret(
            llm_type="openai",
            api_key=value,
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        )
        llm_secret.save()

        embedding = list(np.random.random(LLMProcessor.__embedding__))
        input = {"name": "Ram", "color": "red"}
        mock_embedding.return_value = litellm.EmbeddingResponse(**{'data': [{'embedding': embedding}]})
        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': llm_secret}}):
            gpt3 = LLMProcessor(bot, DEFAULT_LLM)

            aioresponses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections"),
                method="GET",
                payload={"time": 0, "status": "ok", "result": {"collections": []}})

            aioresponses.add(
                method="DELETE",
                url=urljoin(Utility.environment['vector']['db'], f"/collections/test_int_embd_int_faq_embd"),
            )

            aioresponses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/test_int_embd_int_faq_embd"),
                method="PUT",
                status=200
            )

            aioresponses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/test_int_embd_int_faq_embd"),
                method="PUT",
                status=200
            )

            aioresponses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/test_int_embd_int_faq_embd/points"),
                method="PUT",
                payload={"result": {"operation_id": 0, "status": "acknowledged"}, "status": "ok", "time": 0.003612634}
            )

            response = await gpt3.train(user=user)
            assert response['faq'] == 1

            assert list(aioresponses.requests.values())[1][0].kwargs['json'] == {'name': 'test_int_embd_int_faq_embd',
                                                                                 'vectors': gpt3.vector_config}
            expected_payload = test_content.data
            #expected_payload['collection_name'] = 'test_int_embd_int_faq_embd'
            assert list(aioresponses.requests.values())[2][0].kwargs['json'] == {
                'points': [{'id': test_content.vector_id,
                            'vector': embedding,
                            'payload': expected_payload
                            }]}

            expected = {"model": "text-embedding-3-large",
                        "input": [json.dumps(input)], 'metadata': {'user': user, 'bot': bot, 'invocation': None},
                        "api_key": value,
                        "num_retries": 3}
            assert not DeepDiff(mock_embedding.call_args[1], expected, ignore_order=True)

    def test_gpt3_faq_embedding_train_failure(self):
        with pytest.raises(AppException, match=f"LLM secret for '{DEFAULT_LLM}' is not configured!"):
            LLMProcessor('test_gpt3_faq_embedding_train_failure', DEFAULT_LLM)

    @pytest.mark.asyncio
    @mock.patch.object(litellm, "aembedding", autospec=True)
    async def test_gpt3_faq_embedding_train_upsert_error(self, mock_embedding, aioresponses):
        bot = "test_embed_faq_not_exists"
        user = "test"
        value = "nupurk"
        test_content = CognitionData(
            data="Welcome! Are you completely new to programming? If not then we presume you will be looking for information about why and how to get started with Python",
            bot=bot, user=user).save()

        llm_secret = LLMSecret(
            llm_type="openai",
            api_key=value,
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        )
        llm_secret.save()

        embedding = list(np.random.random(LLMProcessor.__embedding__))

        mock_embedding.return_value = litellm.EmbeddingResponse(**{'data': [{'embedding': embedding}]})

        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': llm_secret}}):
            gpt3 = LLMProcessor(test_content.bot, DEFAULT_LLM)

            aioresponses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections"),
                method="GET",
                payload={"time": 0, "status": "ok", "result": {"collections": []}})

            aioresponses.add(
                method="DELETE",
                url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.suffix}")
            )

            aioresponses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.suffix}"),
                method="PUT",
                status=200
            )

            aioresponses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.suffix}/points"),
                method="PUT",
                payload={"result": None,
                         'status': {'error': 'Json deserialize error: missing field `vectors` at line 1 column 34779'},
                         "time": 0.003612634}
            )

            with pytest.raises(AppException, match="Unable to train FAQ! Contact support"):
                await gpt3.train(user=user)

            assert list(aioresponses.requests.values())[1][0].kwargs['json'] == {'name': gpt3.bot + gpt3.suffix,
                                                                                 'vectors': gpt3.vector_config}
            assert list(aioresponses.requests.values())[2][0].kwargs['json'] == {
                'points': [{'id': test_content.vector_id,
                            'vector': embedding, 'payload': {'content': test_content.data}}]}

            expected = {"model": "text-embedding-3-large",
                        "input": [test_content.data], 'metadata': {'user': user, 'bot': bot, 'invocation': None},
                        "api_key": value,
                        "num_retries": 3}
            assert not DeepDiff(mock_embedding.call_args[1], expected, ignore_order=True)

    @pytest.mark.asyncio
    @mock.patch.object(litellm, "aembedding", autospec=True)
    async def test_gpt3_faq_embedding_train_payload_upsert_error_json(self, mock_embedding, aioresponses):
        bot = "payload_upsert_error"
        user = "test"
        value = "nupurk"
        CognitionSchema(
            metadata=[{"column_name": "city", "data_type": "str", "enable_search": True, "create_embeddings": True},
                      {"column_name": "color", "data_type": "str", "enable_search": True, "create_embeddings": True}],
            collection_name="error_json",
            bot=bot, user=user
        ).save()
        test_content = CognitionData(
            data={'city': 'London', 'color': 'red'},
            content_type="json",
            collection="error_json",
            bot=bot, user=user).save()

        llm_secret = LLMSecret(
            llm_type="openai",
            api_key=value,
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        )
        llm_secret.save()

        embedding = list(np.random.random(LLMProcessor.__embedding__))

        mock_embedding.return_value = litellm.EmbeddingResponse(**{'data': [{'embedding': embedding}]})
        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': llm_secret}}):
            gpt3 = LLMProcessor(test_content.bot, DEFAULT_LLM)

            aioresponses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections"),
                method="GET",
                payload={"time": 0, "status": "ok", "result": {"collections": []}})

            aioresponses.add(
                method="DELETE",
                url=urljoin(Utility.environment['vector']['db'],
                            f"/collections/payload_upsert_error_error_json_faq_embd"),
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

            assert list(aioresponses.requests.values())[1][0].kwargs['json'] == {
                'name': 'payload_upsert_error_error_json_faq_embd', 'vectors': gpt3.vector_config}
            expected_payload = test_content.data
            #expected_payload['collection_name'] = 'payload_upsert_error_error_json_faq_embd'
            assert list(aioresponses.requests.values())[2][0].kwargs['json'] == {
                'points': [{'id': test_content.vector_id,
                            'vector': embedding,
                            'payload': expected_payload
                            }]}

            expected = {"model": "text-embedding-3-large",
                        "input": [json.dumps(test_content.data)], 'metadata': {'user': user, 'bot': bot, 'invocation': None},
                        "api_key": value,
                        "num_retries": 3}
            assert not DeepDiff(mock_embedding.call_args[1], expected, ignore_order=True)

    @pytest.mark.asyncio
    @mock.patch.object(litellm, "aembedding", autospec=True)
    async def test_gpt3_faq_embedding_predict(self, mock_embedding, aioresponses):
        embedding = list(np.random.random(LLMProcessor.__embedding__))

        bot = "test_embed_faq_predict"
        user = "test"
        value = "knupur"
        collection = 'python'
        llm_type = "openai"
        test_content = CognitionData(
            data="Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.",
            collection=collection, bot=bot, user=user).save()

        llm_secret = LLMSecret(
            llm_type=llm_type,
            api_key=value,
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        )
        llm_secret.save()

        generated_text = "Python is dynamically typed, garbage-collected, high level, general purpose programming."
        query = "What kind of language is python?"
        hyperparameters = Utility.get_default_llm_hyperparameters()

        k_faq_action_config = {
            "system_prompt": "You are a personal assistant. Answer the question according to the below context",
            "context_prompt": "Based on below context answer question, if answer not in context check previous logs.",
            "similarity_prompt": [{"top_results": 10, "similarity_threshold": 0.70, 'use_similarity_prompt': True,
                                   'similarity_prompt_name': 'Similarity Prompt',
                                   'similarity_prompt_instructions': 'Answer according to this context.',
                                   'collection': 'python'}],
            "hyperparameters": hyperparameters
        }
        mock_embedding.return_value = litellm.EmbeddingResponse(**{'data': [{'embedding': embedding}]})

        aioresponses.add(
            url=urljoin(Utility.environment['llm']['url'],
                        f"/{bot}/completion/{llm_type}"),
            method="POST",
            status=200,
            payload={'formatted_response': generated_text,
                     'response': {'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}},
        )

        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': llm_secret, 'url': "http://localhost"}}):
            gpt3 = LLMProcessor(test_content.bot, DEFAULT_LLM)

            aioresponses.add(
                url=urljoin(Utility.environment['vector']['db'],
                            f"/collections/{gpt3.bot}_{test_content.collection}{gpt3.suffix}/points/search"),
                method="POST",
                payload={'result': [
                    {'id': test_content.vector_id, 'score': 0.80, "payload": {'content': test_content.data}}]}
            )

            response, time_elapsed = await gpt3.predict(query, user=user, **k_faq_action_config)

            assert list(aioresponses.requests.values())[0][0].kwargs['json'] == {'vector': embedding, 'limit': 10,
                                                                                 'with_payload': True,
                                                                                 'score_threshold': 0.70}
            assert isinstance(time_elapsed, float) and time_elapsed > 0.0

            expected = {"model": "text-embedding-3-large",
                        "input": [query], 'metadata': {'user': user, 'bot': bot, 'invocation': None},
                        "api_key": value,
                        "num_retries": 3}
            assert not DeepDiff(mock_embedding.call_args[1], expected, ignore_order=True)

    @pytest.mark.asyncio
    @mock.patch.object(litellm, "aembedding", autospec=True)
    async def test_gpt3_faq_embedding_predict_with_default_collection(self, mock_embedding,
                                                                      aioresponses):
        embedding = list(np.random.random(LLMProcessor.__embedding__))

        bot = "test_embed_faq_predict_with_default_collection"
        user = "test"
        value = "knupur"
        collection = 'default'
        llm_type = "openai"
        test_content = CognitionData(
            data="Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.",
            collection=collection, bot=bot, user=user).save()

        llm_secret = LLMSecret(
            llm_type=llm_type,
            api_key=value,
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        )
        llm_secret.save()

        generated_text = "Python is dynamically typed, garbage-collected, high level, general purpose programming."
        query = "What kind of language is python?"
        hyperparameters = Utility.get_default_llm_hyperparameters()
        k_faq_action_config = {
            "system_prompt": "You are a personal assistant. Answer the question according to the below context",
            "context_prompt": "Based on below context answer question, if answer not in context check previous logs.",
            "similarity_prompt": [{"top_results": 10, "similarity_threshold": 0.70, 'use_similarity_prompt': True,
                                   'similarity_prompt_name': 'Similarity Prompt',
                                   'similarity_prompt_instructions': 'Answer according to this context.',
                                   'collection': 'default'}],
            'hyperparameters': hyperparameters
        }

        mock_embedding.return_value = litellm.EmbeddingResponse(**{'data': [{'embedding': embedding}]})

        aioresponses.add(
            url=urljoin(Utility.environment['llm']['url'],
                        f"/{bot}/completion/{llm_type}"),
            method="POST",
            status=200,
            payload={'formatted_response': generated_text,
                     'response': {'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}},
        )

        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': llm_secret}}):
            gpt3 = LLMProcessor(test_content.bot, DEFAULT_LLM)

            aioresponses.add(
                url=urljoin(Utility.environment['vector']['db'],
                            f"/collections/{gpt3.bot}{gpt3.suffix}/points/search"),
                method="POST",
                payload={'result': [
                    {'id': test_content.vector_id, 'score': 0.80, "payload": {'content': test_content.data}}]}
            )

        response, time_elapsed = await gpt3.predict(query, user=user, **k_faq_action_config)
        assert response['content'] == generated_text

        assert list(aioresponses.requests.values())[0][0].kwargs['json'] == {'vector': embedding, 'limit': 10,
                                                                             'with_payload': True,
                                                                             'score_threshold': 0.70}

        assert isinstance(time_elapsed, float) and time_elapsed > 0.0

        expected = {"model": "text-embedding-3-large",
                    "input": [query], 'metadata': {'user': user, 'bot': bot, 'invocation': None},
                    "api_key": value,
                    "num_retries": 3}
        assert not DeepDiff(mock_embedding.call_args[1], expected, ignore_order=True)

    @pytest.mark.asyncio
    @mock.patch.object(litellm, "aembedding", autospec=True)
    async def test_gpt3_faq_embedding_predict_with_values(self, mock_embedding, aioresponses):
        embedding = list(np.random.random(LLMProcessor.__embedding__))

        test_content = CognitionData(
            data="Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.",
            collection='python', bot="test_gpt3_faq_embedding_predict_with_values", user="test").save()

        generated_text = "Python is dynamically typed, garbage-collected, high level, general purpose programming."
        query = "What kind of language is python?"


        hyperparameters = Utility.get_default_llm_hyperparameters()
        key = 'test'
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
            "similarity_prompt": [{"top_results": 10, "similarity_threshold": 0.70, 'use_similarity_prompt': True,
                                   'similarity_prompt_name': 'Similarity Prompt',
                                   'similarity_prompt_instructions': 'Answer according to this context.',
                                   'collection': 'python'}],
            "hyperparameters": hyperparameters
        }

        mock_embedding.return_value = litellm.EmbeddingResponse(**{'data': [{'embedding': embedding}]})

        aioresponses.add(
            url=urljoin(Utility.environment['llm']['url'],
                        f"/{test_content.bot}/completion/{llm_type}"),
            method="POST",
            status=200,
            payload={'formatted_response': generated_text,
                     'response': {'id': 'chatcmpl-5cde438e-0c93-47d8-bbee-13319b4f2000',
                                'created': 1720090690,
                                'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}},
        )
        with mock.patch.dict(Utility.environment, {'vector': {"key": "test", 'db': "http://localhost:6333"}}):
            gpt3 = LLMProcessor(test_content.bot, DEFAULT_LLM)

            aioresponses.add(
                url=urljoin(Utility.environment['vector']['db'],
                            f"/collections/{gpt3.bot}_{test_content.collection}{gpt3.suffix}/points/search"),
                method="POST",
                payload={'result': [
                    {'id': test_content.vector_id, 'score': 0.80, "payload": {'content': test_content.data}}]}
            )

            response, time_elapsed = await gpt3.predict(query, user=user, **k_faq_action_config)
            assert response['content'] == generated_text
            assert gpt3.logs == [{'messages': [{'role': 'system', 'content': 'You are a personal assistant. Answer the question according to the below context'}, {'role': 'user', 'content': "Based on below context answer question, if answer not in context check previous logs.\nInstructions on how to use Similarity Prompt:\n['Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.']\nAnswer according to this context.\n \nQ: What kind of language is python? \nA:"}], 'raw_completion_response': {'id': 'chatcmpl-5cde438e-0c93-47d8-bbee-13319b4f2000', 'created': 1720090690, 'choices': [{'message': {'content': 'Python is dynamically typed, garbage-collected, high level, general purpose programming.', 'role': 'assistant'}}]}, 'type': 'answer_query', 'hyperparameters': {'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-4.1-mini', 'top_p': 0.0, 'n': 1, 'stop': None, 'presence_penalty': 0.0, 'frequency_penalty': 0.0, 'logit_bias': {}}}]

            assert list(aioresponses.requests.values())[0][0].kwargs['json'] == {'vector': embedding, 'limit': 10,
                                                                                 'with_payload': True,
                                                                                 'score_threshold': 0.70}

            assert isinstance(time_elapsed, float) and time_elapsed > 0.0

            expected = {"model": "text-embedding-3-large",
                        "input": [query], 'metadata': {'user': user, 'bot': gpt3.bot, 'invocation': None},
                        "api_key": key,
                        "num_retries": 3}
            assert not DeepDiff(mock_embedding.call_args[1], expected, ignore_order=True)

    @pytest.mark.asyncio
    @mock.patch.object(litellm, "aembedding", autospec=True)
    async def test_gpt3_faq_embedding_predict_with_values_and_stream(self, mock_embedding,
                                                                     aioresponses):
        embedding = list(np.random.random(LLMProcessor.__embedding__))

        test_content = CognitionData(
            data="Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.",
            collection='python', bot="test_gpt3_faq_embedding_predict_with_values_and_stream", user="test").save()

        generated_text = "Python is dynamically typed, garbage-collected, high level, general purpose programming."
        query = "What kind of language is python?"
        hyperparameters = Utility.get_default_llm_hyperparameters()
        hyperparameters['stream'] = True
        key = 'test'
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
            "similarity_prompt": [{"top_results": 10, "similarity_threshold": 0.70, 'use_similarity_prompt': True,
                                   'similarity_prompt_name': 'Similarity Prompt',
                                   'similarity_prompt_instructions': 'Answer according to this context.',
                                   'collection': 'python'}],
            "hyperparameters": hyperparameters
        }

        mock_embedding.return_value = litellm.EmbeddingResponse(**{'data': [{'embedding': embedding}]})

        aioresponses.add(
            url=urljoin(Utility.environment['llm']['url'],
                        f"/{test_content.bot}/completion/{llm_type}"),
            method="POST",
            status=200,
            payload={'formatted_response': generated_text,
                     'response': {'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}},
        )

        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': key, 'url': 'http://localhost'}}):
            gpt3 = LLMProcessor(test_content.bot, DEFAULT_LLM)

            aioresponses.add(
                url=urljoin(Utility.environment['vector']['db'],
                            f"/collections/{gpt3.bot}_{test_content.collection}{gpt3.suffix}/points/search"),
                method="POST",
                payload={'result': [
                    {'id': test_content.vector_id, 'score': 0.80, "payload": {'content': test_content.data}}]}
            )

            response, time_elapsed = await gpt3.predict(query, user=user, **k_faq_action_config)
            assert response['content'] == "Python is dynamically typed, garbage-collected, high level, general purpose programming."
            assert gpt3.logs == [{'messages': [{'role': 'system', 'content': 'You are a personal assistant. Answer the question according to the below context'}, {'role': 'user', 'content': "Based on below context answer question, if answer not in context check previous logs.\nInstructions on how to use Similarity Prompt:\n['Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.']\nAnswer according to this context.\n \nQ: What kind of language is python? \nA:"}], 'raw_completion_response': {'choices': [{'message': {'content': 'Python is dynamically typed, garbage-collected, high level, general purpose programming.', 'role': 'assistant'}}]}, 'type': 'answer_query', 'hyperparameters': {'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-4.1-mini', 'top_p': 0.0, 'n': 1, 'stop': None, 'presence_penalty': 0.0, 'frequency_penalty': 0.0, 'logit_bias': {}, 'stream': True}}]

            assert list(aioresponses.requests.values())[0][0].kwargs['json'] == {'vector': embedding, 'limit': 10,
                                                                                 'with_payload': True,
                                                                                 'score_threshold': 0.70}

            assert isinstance(time_elapsed, float) and time_elapsed > 0.0

            expected = {"model": "text-embedding-3-large",
                        "input": [query], 'metadata': {'user': user, 'bot': gpt3.bot, 'invocation': None},
                        "api_key": key,
                        "num_retries": 3}
            assert not DeepDiff(mock_embedding.call_args[1], expected, ignore_order=True)

    @pytest.mark.asyncio
    @mock.patch.object(litellm, "aembedding", autospec=True)
    async def test_gpt3_faq_embedding_predict_with_values_with_instructions(self,
                                                                            mock_embedding,
                                                                            aioresponses):
        embedding = list(np.random.random(LLMProcessor.__embedding__))
        user = "test"
        bot = "payload_with_instruction"
        key = 'test'
        llm_type = 'openai'
        CognitionSchema(
            metadata=[{"column_name": "name", "data_type": "str", "enable_search": True, "create_embeddings": True},
                      {"column_name": "city", "data_type": "str", "enable_search": True, "create_embeddings": True}],
            collection_name="User_details",
            bot=bot, user=user
        ).save()
        test_content1 = CognitionData(
            data={"name": "Nupur", "city": "Pune"},
            content_type="json",
            collection="User_details",
            bot=bot, user=user).save()
        test_content2 = CognitionData(
            data={"name": "Fahad", "city": "Mumbai"},
            content_type="json",
            collection="User_details",
            bot=bot, user=user).save()
        test_content3 = CognitionData(
            data={"name": "Hitesh", "city": "Mumbai"},
            content_type="json",
            collection="User_details",
            bot=bot, user=user).save()

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
            "similarity_prompt": [{"top_results": 10,
                                   "similarity_threshold": 0.70,
                                   'use_similarity_prompt': True,
                                   'similarity_prompt_name': 'Similarity Prompt',
                                   'similarity_prompt_instructions': 'Answer according to this context.',
                                   "collection": "user_details"}],
            'instructions': ['Answer in a short way.', 'Keep it simple.'],
            "hyperparameters": hyperparameters
        }

        mock_embedding.return_value = litellm.EmbeddingResponse(**{'data': [{'embedding': embedding}]})

        expected_body = {'messages': [
            {'role': 'system',
             'content': 'You are a personal assistant. Answer the question according to the below context'},
            {'role': 'user',
             'content': "Based on below context answer question, if answer not in context check previous logs.\nInstructions on how to use Similarity Prompt:\n[{'name': 'Fahad', 'city': 'Mumbai'}, {'name': 'Hitesh', 'city': 'Mumbai'}]\nAnswer according to this context.\n \nAnswer in a short way.\nKeep it simple. \nQ: List all the user lives in mumbai city \nA:"}
        ],
         "hyperparameters": hyperparameters,
         'user': user,
         'invocation': 'prompt_action'
         }

        aioresponses.add(
            url=urljoin(Utility.environment['llm']['url'],
                        f"/{bot}/completion/{llm_type}"),
            method="POST",
            status=200,
            payload={'formatted_response': generated_text,
                     'response': {'choices': [{'id': 'chatcmpl-836a9b38-dfe9-4ae0-9f94-f431e2e8e8d1',
                                                          'choices': [{'finish_reason': 'stop', 'index': 0, 'message': {
                                                              'content': 'Hitesh and Fahad lives in mumbai city.',
                                                              'role': 'assistant'}}], 'created': 1720090691,
                                                          'model': None, 'object': 'chat.completion',
                                                          'system_fingerprint': None, 'usage': {}}]}},
            body=expected_body
        )

        gpt3 = LLMProcessor(bot, DEFAULT_LLM)
        aioresponses.add(
            url=urljoin(Utility.environment['vector']['db'],
                        f"/collections/{gpt3.bot}_{test_content1.collection}{gpt3.suffix}/points/search"),
            method="POST",
            payload={'result': [
                {'id': test_content2.vector_id, 'score': 0.80, "payload": test_content2.data},
                {'id': test_content3.vector_id, 'score': 0.80, "payload": test_content3.data}
            ]}
        )

        response, time_elapsed = await gpt3.predict(query, user=user, **k_faq_action_config)
        assert response['content'] == generated_text
        assert not DeepDiff(gpt3.logs, [{'messages': [{'role': 'system', 'content': 'You are a personal assistant. Answer the question according to the below context'}, {'role': 'user', 'content': "Based on below context answer question, if answer not in context check previous logs.\nInstructions on how to use Similarity Prompt:\n[{'name': 'Fahad', 'city': 'Mumbai'}, {'name': 'Hitesh', 'city': 'Mumbai'}]\nAnswer according to this context.\n \nAnswer in a short way.\nKeep it simple. \nQ: List all the user lives in mumbai city \nA:"}], 'raw_completion_response': {'choices': [{'id': 'chatcmpl-836a9b38-dfe9-4ae0-9f94-f431e2e8e8d1', 'choices': [{'finish_reason': 'stop', 'index': 0, 'message': {'content': 'Hitesh and Fahad lives in mumbai city.', 'role': 'assistant'}}], 'created': 1720090691, 'model': None, 'object': 'chat.completion', 'system_fingerprint': None, 'usage': {}}]}, 'type': 'answer_query', 'hyperparameters': {'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-4.1-mini', 'top_p': 0.0, 'n': 1, 'stop': None, 'presence_penalty': 0.0, 'frequency_penalty': 0.0, 'logit_bias': {}}}], ignore_order=True)

        assert list(aioresponses.requests.values())[0][0].kwargs['json'] == {'vector': embedding, 'limit': 10,
                                                                             'with_payload': True,
                                                                             'score_threshold': 0.70}

        assert isinstance(time_elapsed, float) and time_elapsed > 0.0

        expected = {"model": "text-embedding-3-large",
                    "input": [query], 'metadata': {'user': user, 'bot': bot, 'invocation': None},
                    "api_key": key,
                    "num_retries": 3}
        assert not DeepDiff(mock_embedding.call_args[1], expected, ignore_order=True)

    @pytest.mark.asyncio
    @mock.patch.object(litellm, "aembedding", autospec=True)
    async def test_gpt3_faq_embedding_predict_completion_connection_error(self, mock_embedding,
                                                                          aioresponses):
        embedding = list(np.random.random(LLMProcessor.__embedding__))
        bot = "test_gpt3_faq_embedding_predict_completion_connection_error"
        user = 'test'
        key = "test"
        llm_type = "openai"

        test_content = CognitionData(
            data="Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.",
            collection='python', bot=bot, user=user).save()

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
        generated_text = "Python is dynamically typed, garbage-collected, high level, general purpose programming."
        query = "What kind of language is python?"

        k_faq_action_config = {
            "system_prompt": "You are a personal assistant. Answer the question according to the below context",
            "context_prompt": "Based on below context answer question, if answer not in context check previous logs.",
            "similarity_prompt": [{"top_results": 10, "similarity_threshold": 0.70, 'use_similarity_prompt': True,
                                   'similarity_prompt_name': 'Similarity Prompt',
                                   'similarity_prompt_instructions': 'Answer according to this context.',
                                   "collection": 'python'}],
            "hyperparameters": hyperparameters
        }

        mock_embedding.return_value = litellm.EmbeddingResponse(**{'data': [{'embedding': embedding}]})

        aioresponses.add(
            url=urljoin(Utility.environment['llm']['url'],
                        f"/{bot}/completion/{llm_type}"),
            method="POST",
            exception=Exception("Connection reset by peer!")
        )

        gpt3 = LLMProcessor(test_content.bot, DEFAULT_LLM)

        aioresponses.add(
            url=urljoin(Utility.environment['vector']['db'],
                        f"/collections/{gpt3.bot}_{test_content.collection}{gpt3.suffix}/points/search"),
            method="POST",
            payload={'result': [
                {'id': test_content.vector_id, 'score': 0.80, "payload": {'content': test_content.data}}]}
        )

        response, time_elapsed = await gpt3.predict(query, user=user, **k_faq_action_config)
        assert response == {'is_failure': True, 'exception': 'Internal Server Error', 'content': None}


        assert gpt3.logs == [{'error': 'Retrieving chat completion for the provided query. Internal Server Error'}]

        assert list(aioresponses.requests.values())[0][0].kwargs['json'] == {'vector': embedding, 'limit': 10,
                                                                             'with_payload': True,
                                                                             'score_threshold': 0.70}
        assert isinstance(time_elapsed, float) and time_elapsed > 0.0

        expected = {"model": "text-embedding-3-large",
                    "input": [query], 'metadata': {'user': user, 'bot': bot, 'invocation': None},
                    "api_key": key,
                    "num_retries": 3}
        assert not DeepDiff(mock_embedding.call_args[1], expected, ignore_order=True)


    @pytest.mark.asyncio
    @mock.patch("kairon.shared.rest_client.AioRestClient._AioRestClient__trigger", autospec=True)
    @mock.patch.object(litellm, "aembedding", autospec=True)
    async def test_gpt3_faq_embedding_predict_exact_match(self, mock_embedding, mock_llm_request):
        embedding = list(np.random.random(LLMProcessor.__embedding__))
        user = "test"
        bot = "test_gpt3_faq_embedding_predict_exact_match"
        key = 'test'
        test_content = CognitionData(
            data="Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.",
            collection='python', bot=bot, user=user).save()

        llm_secret = LLMSecret(
            llm_type="openai",
            api_key=key,
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=test_content.bot,
            user=user
        )
        llm_secret.save()


        query = "What kind of language is python?"
        hyperparameters = Utility.get_default_llm_hyperparameters()
        k_faq_action_config = {
            "system_prompt": "You are a personal assistant. Answer the question according to the below context",
            "context_prompt": "Based on below context answer question, if answer not in context check previous logs.",
            "similarity_prompt": [{"top_results": 10, "similarity_threshold": 0.70, 'use_similarity_prompt': True,
                                   'similarity_prompt_name': 'Similarity Prompt',
                                   'similarity_prompt_instructions': 'Answer according to this context.',
                                   "collection": 'python'}],
            "hyperparameters": hyperparameters
        }

        mock_embedding.return_value = litellm.EmbeddingResponse(**{'data': [{'embedding': embedding}]})
        mock_llm_request.side_effect = ClientConnectionError()

        gpt3 = LLMProcessor(test_content.bot, DEFAULT_LLM)

        response, time_elapsed = await gpt3.predict(query, user="test", **k_faq_action_config)
        assert response == {'exception': 'Failed to connect to service: localhost', 'is_failure': True, "content": None}

        assert gpt3.logs == [
            {'error': 'Retrieving chat completion for the provided query. Failed to connect to service: localhost'}]
        assert isinstance(time_elapsed, float) and time_elapsed > 0.0

        expected = {"model": "text-embedding-3-large",
                    "input": [query], 'metadata': {'user': user, 'bot': bot, 'invocation': None},
                    "api_key": key,
                    "num_retries": 3}
        assert not DeepDiff(mock_embedding.call_args[1], expected, ignore_order=True)

    @pytest.mark.asyncio
    @mock.patch.object(litellm, "aembedding", autospec=True)
    async def test_gpt3_faq_embedding_predict_embedding_connection_error(self, mock_embedding):
        embedding = list(np.random.random(LLMProcessor.__embedding__))
        user = "test"
        bot = "test_gpt3_faq_embedding_predict_embedding_connection_error"
        key = "test"
        test_content = CognitionData(
            data="Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.",
            bot=bot, user=user).save()

        llm_secret = LLMSecret(
            llm_type="openai",
            api_key=key,
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=test_content.bot,
            user=user
        )
        llm_secret.save()

        hyperparameters = Utility.get_default_llm_hyperparameters()
        generated_text = "Python is dynamically typed, garbage-collected, high level, general purpose programming."
        query = "What kind of language is python?"

        k_faq_action_config = {
            "system_prompt": "You are a personal assistant. Answer the question according to the below context",
            "context_prompt": "Based on below context answer question, if answer not in context check previous logs.",
            "hyperparameters": hyperparameters
        }

        gpt3 = LLMProcessor(test_content.bot, DEFAULT_LLM)
        mock_embedding.side_effect = [Exception("Connection reset by peer!"), litellm.EmbeddingResponse(**{'data': [{'embedding': embedding}]})]

        response, time_elapsed = await gpt3.predict(query, user="test", **k_faq_action_config)
        assert response == {'exception': 'Connection reset by peer!', 'is_failure': True, "content": None}

        assert gpt3.logs == [{'error': 'Creating a new embedding for the provided query. Connection reset by peer!'}]
        assert isinstance(time_elapsed, float) and time_elapsed > 0.0

        expected = {"model": "text-embedding-3-large",
                    "input": [query], 'metadata': {'user': user, 'bot': bot, 'invocation': None},
                    "api_key": key,
                    "num_retries": 3}
        assert not DeepDiff(mock_embedding.call_args[1], expected, ignore_order=True)

    @pytest.mark.asyncio
    @mock.patch.object(litellm, "aembedding", autospec=True)
    async def test_gpt3_faq_embedding_predict_with_previous_bot_responses(self, mock_embedding,
                                                                          aioresponses):
        embedding = list(np.random.random(LLMProcessor.__embedding__))
        llm_type = "openai"
        bot = "test_gpt3_faq_embedding_predict_with_previous_bot_responses"
        user = "test"
        key = "test"
        hyperparameters = Utility.get_default_llm_hyperparameters()
        test_content = CognitionData(
            data="Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.",
            collection='python', bot=bot, user=user).save()

        llm_secret = LLMSecret(
            llm_type="openai",
            api_key=key,
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=test_content.bot,
            user=user
        )
        llm_secret.save()

        generated_text = "Python is dynamically typed, garbage-collected, high level, general purpose programming."
        query = "What kind of language is python?"
        k_faq_action_config = {
            "previous_bot_responses": [
                {'role': 'user', 'content': 'hello'},
                {'role': 'assistant', 'content': 'how are you'},
            ],
            "similarity_prompt": [{'use_similarity_prompt': True, 'similarity_prompt_name': 'Similarity Prompt',
                                   'similarity_prompt_instructions': 'Answer according to this context.',
                                   "collection": 'python'}],
            "hyperparameters": hyperparameters
        }

        mock_embedding.return_value = litellm.EmbeddingResponse(**{'data': [{'embedding': embedding}]})
        expected_body = {'messages': [
            {'role': 'system', 'content': 'You are a personal assistant. Answer question based on the context below'},
            {'role': 'user', 'content': 'hello'},
            {'role': 'assistant', 'content': 'how are you'},
            {'role': 'user',
             'content': "Answer question based on the context below, if answer is not in the context go check previous logs.\nInstructions on how to use Similarity Prompt:\n['Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.']\nAnswer according to this context.\n \nQ: What kind of language is python? \nA:"}
        ],
         "hyperparameters": hyperparameters,
         'user': user,
         'invocation': 'prompt_action'
         }

        aioresponses.add(
            url=urljoin(Utility.environment['llm']['url'],
                        f"/{bot}/completion/{llm_type}"),
            method="POST",
            status=200,
            payload={'formatted_response': generated_text,
                     'response': {'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}},
            body=expected_body
        )

        gpt3 = LLMProcessor(test_content.bot, DEFAULT_LLM)

        aioresponses.add(
            url=urljoin(Utility.environment['vector']['db'],
                        f"/collections/{gpt3.bot}_{test_content.collection}{gpt3.suffix}/points/search"),
            method="POST",
            payload={'result': [
                {'id': test_content.vector_id, 'score': 0.80, "payload": {'content': test_content.data}}]}
        )

        response, time_elapsed = await gpt3.predict(query, user=user, **k_faq_action_config)
        assert response['content'] == generated_text

        assert list(aioresponses.requests.values())[0][0].kwargs['json'] == {'vector': embedding, 'limit': 10,
                                                                             'with_payload': True,
                                                                             'score_threshold': 0.70}

        assert isinstance(time_elapsed, float) and time_elapsed > 0.0

        expected = {"model": "text-embedding-3-large",
                    "input": [query], 'metadata': {'user': user, 'bot': bot, 'invocation': None},
                    "api_key": key,
                    "num_retries": 3}
        assert not DeepDiff(mock_embedding.call_args[1], expected, ignore_order=True)

    @pytest.mark.asyncio
    @mock.patch.object(litellm, "aembedding", autospec=True)
    async def test_gpt3_faq_embedding_predict_with_query_prompt(self, mock_embedding, aioresponses):
        embedding = list(np.random.random(LLMProcessor.__embedding__))

        llm_type = "openai"
        bot = "test_gpt3_faq_embedding_predict_with_query_prompt"
        user = "test"
        key = "test"
        test_content = CognitionData(
            data="Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.",
            collection='python', bot=bot, user=user).save()

        llm_secret = LLMSecret(
            llm_type=llm_type,
            api_key=key,
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=test_content.bot,
            user=user
        )
        llm_secret.save()

        generated_text = "Python is dynamically typed, garbage-collected, high level, general purpose programming."
        query = "What kind of language is python?"
        rephrased_query = "Explain python is called high level programming language in laymen terms?"
        hyperparameters = Utility.get_default_llm_hyperparameters()

        k_faq_action_config = {"query_prompt": {
            "query_prompt": "A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.",
            "use_query_prompt": True},
            "similarity_prompt": [
                {'use_similarity_prompt': True, 'similarity_prompt_name': 'Similarity Prompt',
                 'similarity_prompt_instructions': 'Answer according to this context.',
                 "collection": 'python'}],
            "hyperparameters": hyperparameters
        }

        mock_rephrase_request = {"messages": [
            {"role": "system",
             "content": DEFAULT_SYSTEM_PROMPT},
            {"role": "user",
             "content": f"{k_faq_action_config.get('query_prompt')['query_prompt']}\n\n Q: {query}\n A:"}
        ]}

        mock_rephrase_request.update(hyperparameters)

        mock_embedding.return_value = litellm.EmbeddingResponse(**{'data': [{'embedding': embedding}]})
        expected_body = {'messages': [
            {"role": "system",
             "content": DEFAULT_SYSTEM_PROMPT},
            {'role': 'user',
             'content': "Answer question based on the context below, if answer is not in the context go check previous logs.\nInstructions on how to use Similarity Prompt:\n['Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.']\nAnswer according to this context.\n \nQ: Explain python is called high level programming language in laymen terms? \nA:"}
        ],
         "hyperparameters": hyperparameters,
         'user': user,
         'invocation': 'prompt_action'
         }

        aioresponses.add(
            url=urljoin(Utility.environment['llm']['url'],
                        f"/{bot}/completion/{llm_type}"),
            method="POST",
            status=200,
            payload={'formatted_response': generated_text,
                     'response': {'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}},
            body=expected_body,
            repeat=True
        )

        gpt3 = LLMProcessor(test_content.bot, DEFAULT_LLM)

        aioresponses.add(
            url=urljoin(Utility.environment['vector']['db'],
                        f"/collections/{gpt3.bot}_{test_content.collection}{gpt3.suffix}/points/search"),
            method="POST",
            payload={'result': [
                {'id': test_content.vector_id, 'score': 0.80, "payload": {'content': test_content.data}}]}
        )

        response, time_elapsed = await gpt3.predict(query, user=user, **k_faq_action_config)
        assert response['content'] == generated_text

        assert list(aioresponses.requests.values())[0][0].kwargs['json'] == {'vector': embedding, 'limit': 10,
                                                                             'with_payload': True,
                                                                             'score_threshold': 0.70}
        assert isinstance(time_elapsed, float) and time_elapsed > 0.0

        expected = {"model": "text-embedding-3-large",
                    "input": [query], 'metadata': {'user': user, 'bot': bot, 'invocation': None},
                    "api_key": key,
                    "num_retries": 3}
        assert not DeepDiff(mock_embedding.call_args[1], expected, ignore_order=True)

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

        with patch("os.path.exists", return_value=False):
            LLMProcessor._sparse_embedding = None

            log_output = StringIO()
            logger.add(log_output, format="{message}")

            LLMProcessor.load_sparse_embedding_model()

            logger.remove()
            log_contents = log_output.getvalue()

            assert isinstance(LLMProcessor._sparse_embedding, SparseTextEmbedding)
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