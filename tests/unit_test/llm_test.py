import os
import urllib
from unittest import mock
from unittest.mock import patch, AsyncMock
from urllib.parse import urljoin

import numpy as np
import pytest
from aiohttp import ClientConnectionError
from mongoengine import connect

from kairon.shared.rest_client import AioRestClient
from kairon.shared.utils import Utility


from kairon.exceptions import AppException
from kairon.shared.admin.data_objects import BotSecrets, LLMSecret
from kairon.shared.cognition.data_objects import CognitionData, CognitionSchema
from kairon.shared.data.constant import DEFAULT_SYSTEM_PROMPT, DEFAULT_LLM
from kairon.shared.llm.processor import LLMProcessor
from deepdiff import DeepDiff


class TestLLM:
    @pytest.fixture(autouse=True, scope="class")
    def init_connection(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))

    @pytest.mark.asyncio
    @mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
    async def test_gpt3_faq_embedding_train(self, mock_get_embedding, aioresponses):
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

        text_embedding_3_small_embeddings = [np.random.random(1536).tolist()]
        colbertv2_0_embeddings = [[np.random.random(128).tolist()]]
        bm25_embeddings = [{
            "indices": [1850593538, 11711171],
            "values": [1.66, 1.66]
        }]

        embeddings = {
            "dense": text_embedding_3_small_embeddings,
            "rerank": colbertv2_0_embeddings,
            "sparse": bm25_embeddings,
        }
        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': llm_secret, 'url': "http://kairon:8333"},
                                                   'vector': {'db': "http://kairon:6333", "key": None}}):
            mock_get_embedding.return_value = embeddings
            gpt3 = LLMProcessor(test_content.bot, DEFAULT_LLM)

            aioresponses.add(
                url=urljoin(Utility.environment['llm']['url'], f"/{bot}/config"),
                method="GET",
                payload={
                    "configs":{
                        "vectors_config":{
                            "dense":{"size":1536,"distance":"Cosine"},
                            "rerank":{"size":128,"distance":"Cosine","multivector_config":{"comparator":"max_sim"}}},
                        "sparse_vectors_config":{
                            "sparse":{}
                        }
                    }
                }
            )

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
            assert list(aioresponses.requests.values())[2][0].kwargs['json'] == {
                'name': gpt3.bot + gpt3.suffix,
                'vectors': gpt3.vectors_config,
                'sparse_vectors': gpt3.sparse_vectors_config
            }
            expected_embeddings = {key: value[0] for key, value in embeddings.items()}
            assert list(aioresponses.requests.values())[3][0].kwargs['json'] == {
                'points': [{'id': test_content.vector_id,
                            'vector': expected_embeddings,
                            'payload': {'content': test_content.data}
                            }]}

    @pytest.mark.asyncio
    @mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
    async def test_gpt3_faq_embedding_train_payload_text(self, mock_get_embedding, aioresponses):
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

        text_embedding_3_small_embeddings = [np.random.random(1536).tolist(), np.random.random(1536).tolist()]
        colbertv2_0_embeddings = [[np.random.random(128).tolist()], [np.random.random(128).tolist()]]
        bm25_embeddings = [{
            "indices": [1850593538, 11711171],
            "values": [1.66, 1.66]
        },
            {
                "indices": [1850593538, 11711171],
                "values": [1.66, 1.66]
            }
        ]

        embeddings = {
            "dense": text_embedding_3_small_embeddings,
            "rerank": colbertv2_0_embeddings,
            "sparse": bm25_embeddings,
        }
        gpt3 = LLMProcessor(bot, DEFAULT_LLM)
        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': llm_secret, 'url': "http://kairon:8333"}}):
            mock_get_embedding.return_value = embeddings
            aioresponses.add(
                url=urljoin(Utility.environment['llm']['url'], f"/{bot}/config"),
                method="GET",
                payload={
                    "configs": {
                        "vectors_config": {
                            "dense": {"size": 1536, "distance": "Cosine"},
                            "rerank": {"size": 128, "distance": "Cosine",
                                       "multivector_config": {"comparator": "max_sim"}}},
                        "sparse_vectors_config": {
                            "sparse": {}
                        }
                    }
                }
            )
            aioresponses.add(
                url=urljoin(Utility.environment['llm']['url'], f"/{bot}/config"),
                method="GET",
                payload={
                    "configs": {
                        "vectors_config": {
                            "dense": {"size": 1536, "distance": "Cosine"},
                            "rerank": {"size": 128, "distance": "Cosine",
                                       "multivector_config": {"comparator": "max_sim"}}},
                        "sparse_vectors_config": {
                            "sparse": {}
                        }
                    }
                }
            )
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

            assert list(aioresponses.requests.values())[3][0].kwargs['json'] == {
                'name': f"{gpt3.bot}_country_details{gpt3.suffix}",
                'vectors': gpt3.vectors_config,
                'sparse_vectors': gpt3.sparse_vectors_config
            }

            expected_embeddings = [{key: value[0] for key, value in embeddings.items()}, {key: value[1] for key, value in embeddings.items()}]
            assert list(aioresponses.requests.values())[4][0].kwargs['json'] == {
                'points': [{'id': test_content_two.vector_id,
                            'payload': {'country': 'Spain'},
                            'vector': expected_embeddings[0]
                            },
                           {'id': test_content_three.vector_id,
                            'payload': {'role': 'ds'},
                            'vector': expected_embeddings[1],
                            }
                           ]}

            assert list(aioresponses.requests.values())[5][0].kwargs['json'] == {
                'name': f"{gpt3.bot}_user_details{gpt3.suffix}",
                'vectors': gpt3.vectors_config,
                'sparse_vectors': gpt3.sparse_vectors_config
            }
            assert list(aioresponses.requests.values())[6][0].kwargs['json'] == {
                'points': [{'id': test_content.vector_id,
                            'vector': expected_embeddings[0],
                            'payload': {'name': 'Nupur'}}]}

    @pytest.mark.asyncio
    @mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
    async def test_gpt3_faq_embedding_train_payload_with_int(self, mock_get_embedding, aioresponses):
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

        text_embedding_3_small_embeddings = [np.random.random(1536).tolist()]
        colbertv2_0_embeddings = [[np.random.random(128).tolist()]]
        bm25_embeddings = [{
            "indices": [1850593538, 11711171],
            "values": [1.66, 1.66]
        }]

        embeddings = {
            "dense": text_embedding_3_small_embeddings,
            "rerank": colbertv2_0_embeddings,
            "sparse": bm25_embeddings,
        }
        mock_get_embedding.return_value = embeddings

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

        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': llm_secret,  'url': "http://kairon:8333"}}):
            aioresponses.add(
                url=urljoin(Utility.environment['llm']['url'], f"/{bot}/config"),
                method="GET",
                payload={
                    "configs": {
                        "vectors_config": {
                            "dense": {"size": 1536, "distance": "Cosine"},
                            "rerank": {"size": 128, "distance": "Cosine",
                                       "multivector_config": {"comparator": "max_sim"}}},
                        "sparse_vectors_config": {
                            "sparse": {}
                        }
                    }
                }
            )
            response = await gpt3.train(user=user)
            assert response['faq'] == 1

            assert list(aioresponses.requests.values())[2][0].kwargs['json'] == {
                'name': 'test_embed_faq_json_payload_with_int_faq_embd',
                'vectors': gpt3.vectors_config,
                'sparse_vectors': gpt3.sparse_vectors_config
            }
            expected_embeddings = {key: value[0] for key, value in embeddings.items()}
            assert list(aioresponses.requests.values())[3][0].kwargs['json'] == {
                'points': [{'id': test_content.vector_id,
                            'vector': expected_embeddings,
                            'payload': {'name': 'Ram', 'age': 23, 'color': 'red'}
                            }]}

    @pytest.mark.asyncio
    @mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
    async def test_gpt3_faq_embedding_train_int(self, mock_get_embedding, aioresponses):
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

        text_embedding_3_small_embeddings = [np.random.random(1536).tolist()]
        colbertv2_0_embeddings = [[np.random.random(128).tolist()]]
        bm25_embeddings = [{
            "indices": [1850593538, 11711171],
            "values": [1.66, 1.66]
        }]

        embeddings = {
            "dense": text_embedding_3_small_embeddings,
            "rerank": colbertv2_0_embeddings,
            "sparse": bm25_embeddings,
        }
        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': llm_secret, 'url': "http://kairon:8333"}}):
            gpt3 = LLMProcessor(bot, DEFAULT_LLM)
            mock_get_embedding.return_value = embeddings

            aioresponses.add(
                url=urljoin(Utility.environment['llm']['url'], f"/{bot}/config"),
                method="GET",
                payload={
                    "configs": {
                        "vectors_config": {
                            "dense": {"size": 1536, "distance": "Cosine"},
                            "rerank": {"size": 128, "distance": "Cosine",
                                       "multivector_config": {"comparator": "max_sim"}}},
                        "sparse_vectors_config": {
                            "sparse": {}
                        }
                    }
                }
            )


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

            assert list(aioresponses.requests.values())[2][0].kwargs['json'] == {'name': 'test_int_embd_int_faq_embd',
                                                                                 'vectors': gpt3.vectors_config,
                                                                                 'sparse_vectors': gpt3.sparse_vectors_config}
            expected_embeddings = {key: value[0] for key, value in embeddings.items()}
            assert list(aioresponses.requests.values())[3][0].kwargs['json'] == {
                'points': [{'id': test_content.vector_id,
                            'vector': expected_embeddings,
                            'payload': test_content.data
                            }]}

    def test_gpt3_faq_embedding_train_failure(self):
        with pytest.raises(AppException, match=f"LLM secret for '{DEFAULT_LLM}' is not configured!"):
            LLMProcessor('test_gpt3_faq_embedding_train_failure', DEFAULT_LLM)

    @pytest.mark.asyncio
    @mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
    async def test_gpt3_faq_embedding_train_upsert_error(self, mock_get_embedding, aioresponses):
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

        text_embedding_3_small_embeddings = [np.random.random(1536).tolist()]
        colbertv2_0_embeddings = [[np.random.random(128).tolist()]]
        bm25_embeddings = [{
            "indices": [1850593538, 11711171],
            "values": [1.66, 1.66]
        }]

        embeddings = {
            "dense": text_embedding_3_small_embeddings,
            "rerank": colbertv2_0_embeddings,
            "sparse": bm25_embeddings,
        }

        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': llm_secret, 'url': "http://kairon:8333"}}):
            gpt3 = LLMProcessor(test_content.bot, DEFAULT_LLM)
            mock_get_embedding.return_value = embeddings
            aioresponses.add(
                url=urljoin(Utility.environment['llm']['url'], f"/{bot}/config"),
                method="GET",
                payload={
                    "configs": {
                        "vectors_config": {
                            "dense": {"size": 1536, "distance": "Cosine"},
                            "rerank": {"size": 128, "distance": "Cosine",
                                       "multivector_config": {"comparator": "max_sim"}}},
                        "sparse_vectors_config": {
                            "sparse": {}
                        }
                    }
                }
            )

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

            assert list(aioresponses.requests.values())[2][0].kwargs['json'] == {'name': gpt3.bot + gpt3.suffix,
                                                                                 'vectors': gpt3.vectors_config,
                                                                                 'sparse_vectors': gpt3.sparse_vectors_config}
            expected_embeddings = {key: value[0] for key, value in embeddings.items()}
            assert list(aioresponses.requests.values())[3][0].kwargs['json'] == {
                'points': [{'id': test_content.vector_id,
                            'vector': expected_embeddings, 'payload': {'content': test_content.data}}]}


    @pytest.mark.asyncio
    @mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
    async def test_gpt3_faq_embedding_train_payload_upsert_error_json(self, mock_get_embedding, aioresponses):
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

        text_embedding_3_small_embeddings = [np.random.random(1536).tolist()]
        colbertv2_0_embeddings = [[np.random.random(128).tolist()]]
        bm25_embeddings = [{
            "indices": [1850593538, 11711171],
            "values": [1.66, 1.66]
        }]

        embeddings = {
            "dense": text_embedding_3_small_embeddings,
            "rerank": colbertv2_0_embeddings,
            "sparse": bm25_embeddings,
        }
        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': llm_secret, 'url': "http://kairon:8333"}}):
            gpt3 = LLMProcessor(test_content.bot, DEFAULT_LLM)

            mock_get_embedding.return_value = embeddings

            aioresponses.add(
                url=urljoin(Utility.environment['llm']['url'], f"/{bot}/config"),
                method="GET",
                payload={
                    "configs": {
                        "vectors_config": {
                            "dense": {"size": 1536, "distance": "Cosine"},
                            "rerank": {"size": 128, "distance": "Cosine",
                                       "multivector_config": {"comparator": "max_sim"}}},
                        "sparse_vectors_config": {
                            "sparse": {}
                        }
                    }
                }
            )
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

            assert list(aioresponses.requests.values())[2][0].kwargs['json'] == {
                'name': 'payload_upsert_error_error_json_faq_embd', 'vectors': gpt3.vectors_config,
                'sparse_vectors': gpt3.sparse_vectors_config}
            expected_embeddings = {key: value[0] for key, value in embeddings.items()}
            assert list(aioresponses.requests.values())[3][0].kwargs['json'] == {
                'points': [{'id': test_content.vector_id,
                            'vector': expected_embeddings,
                            'payload': test_content.data
                            }]}

    @pytest.mark.asyncio
    @mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
    async def test_gpt3_faq_embedding_predict(self, mock_get_embedding, aioresponses):

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

        text_embedding_3_small_embeddings = np.random.random(1536).tolist()
        colbertv2_0_embeddings = [np.random.random(128).tolist()]
        bm25_embeddings = {
            "indices": [1850593538, 11711171],
            "values": [1.66, 1.66]
        }

        embeddings = {
            "dense": text_embedding_3_small_embeddings,
            "rerank": colbertv2_0_embeddings,
            "sparse": bm25_embeddings,
        }

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
        mock_get_embedding.return_value = embeddings
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
                            f"/collections/{gpt3.bot}_{test_content.collection}{gpt3.suffix}/points/query"),
                method="POST",
                payload = {
                   "result":{
                      "points":[
                         {
                            "id":test_content.vector_id,
                            "version":0,
                            "score":0.80,
                            "payload":{
                               "content": test_content.data
                            }
                         }
                      ]
                   },
                   "status":"ok",
                   "time":0.000957728
                }
            )

            response, time_elapsed = await gpt3.predict(query, user=user, **k_faq_action_config)
            assert list(aioresponses.requests.values())[0][0].kwargs['json'] == {
                "prefetch": [
                    {
                        "query": embeddings.get("dense", []),
                        "using": "dense",
                        "limit": 20
                    },
                    {
                        "query": embeddings.get("rerank", []),
                        "using": "rerank",
                        "limit": 20
                    },
                    {
                        "query": embeddings.get("sparse", {}),
                        "using": "sparse",
                        "limit": 20
                    }
                ],
                "query": {"fusion": "rrf"},
                "with_payload": True,
                "score_threshold": 0.70,
                "limit": 10
            }
            assert isinstance(time_elapsed, float) and time_elapsed > 0.0

    @pytest.mark.asyncio
    @mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
    async def test_gpt3_faq_embedding_predict_with_default_collection(self, mock_get_embedding,
                                                                      aioresponses):
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

        text_embedding_3_small_embeddings = np.random.random(1536).tolist()
        colbertv2_0_embeddings = [np.random.random(128).tolist()]
        bm25_embeddings = {
            "indices": [1850593538, 11711171],
            "values": [1.66, 1.66]
        }

        embeddings = {
            "dense": text_embedding_3_small_embeddings,
            "rerank": colbertv2_0_embeddings,
            "sparse": bm25_embeddings,
        }

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
        mock_get_embedding.return_value = embeddings

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
                            f"/collections/{gpt3.bot}{gpt3.suffix}/points/query"),
                method="POST",
                payload={
                    "result": {
                        "points": [
                            {
                                "id": test_content.vector_id,
                                "version": 0,
                                "score": 0.80,
                                "payload":{
                                   "content": test_content.data
                                }
                            }
                        ]
                    },
                    "status": "ok",
                    "time": 0.000957728
                }
            )

        response, time_elapsed = await gpt3.predict(query, user=user, **k_faq_action_config)
        assert response['content'] == generated_text

        assert list(aioresponses.requests.values())[0][0].kwargs['json'] == {
            "prefetch": [
                {
                    "query": embeddings.get("dense", []),
                    "using": "dense",
                    "limit": 20
                },
                {
                    "query": embeddings.get("rerank", []),
                    "using": "rerank",
                    "limit": 20
                },
                {
                    "query": embeddings.get("sparse", {}),
                    "using": "sparse",
                    "limit": 20
                }
            ],
            "query": {"fusion": "rrf"},
            "with_payload": True,
            "score_threshold": 0.70,
            "limit": 10
        }

        assert isinstance(time_elapsed, float) and time_elapsed > 0.0

    @pytest.mark.asyncio
    @mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
    async def test_gpt3_faq_embedding_predict_with_values(self, mock_get_embedding, aioresponses):

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

        text_embedding_3_small_embeddings = np.random.random(1536).tolist()
        colbertv2_0_embeddings = [np.random.random(128).tolist()]
        bm25_embeddings = {
            "indices": [1850593538, 11711171],
            "values": [1.66, 1.66]
        }

        embeddings = {
            "dense": text_embedding_3_small_embeddings,
            "rerank": colbertv2_0_embeddings,
            "sparse": bm25_embeddings,
        }

        mock_get_embedding.return_value = embeddings

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
                            f"/collections/{gpt3.bot}_{test_content.collection}{gpt3.suffix}/points/query"),
                method="POST",
                payload={
                    "result": {
                        "points": [
                            {
                                "id": test_content.vector_id,
                                "version": 0,
                                "score": 0.80,
                                "payload": {
                                    "content": test_content.data
                                }
                            }
                        ]
                    },
                    "status": "ok",
                    "time": 0.000957728
                }
            )

            response, time_elapsed = await gpt3.predict(query, user=user, **k_faq_action_config)
            assert response['content'] == generated_text
            assert gpt3.logs == [{'messages': [{'role': 'system', 'content': 'You are a personal assistant. Answer the question according to the below context'}, {'role': 'user', 'content': "Based on below context answer question, if answer not in context check previous logs.\nInstructions on how to use Similarity Prompt:\n['Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.']\nAnswer according to this context.\n \nQ: What kind of language is python? \nA:"}], 'raw_completion_response': {'id': 'chatcmpl-5cde438e-0c93-47d8-bbee-13319b4f2000', 'created': 1720090690, 'choices': [{'message': {'content': 'Python is dynamically typed, garbage-collected, high level, general purpose programming.', 'role': 'assistant'}}]}, 'type': 'answer_query', 'hyperparameters': {'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-4o-mini', 'top_p': 0.0, 'n': 1, 'stop': None, 'presence_penalty': 0.0, 'frequency_penalty': 0.0, 'logit_bias': {}}}]

            assert list(aioresponses.requests.values())[0][0].kwargs['json'] == {
                "prefetch": [
                    {
                        "query": embeddings.get("dense", []),
                        "using": "dense",
                        "limit": 20
                    },
                    {
                        "query": embeddings.get("rerank", []),
                        "using": "rerank",
                        "limit": 20
                    },
                    {
                        "query": embeddings.get("sparse", {}),
                        "using": "sparse",
                        "limit": 20
                    }
                ],
                "query": {"fusion": "rrf"},
                "with_payload": True,
                "score_threshold": 0.70,
                "limit": 10
            }
            assert isinstance(time_elapsed, float) and time_elapsed > 0.0

    @pytest.mark.asyncio
    @mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
    async def test_gpt3_faq_embedding_predict_with_values_and_stream(self, mock_get_embedding,
                                                                     aioresponses):

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

        text_embedding_3_small_embeddings = np.random.random(1536).tolist()
        colbertv2_0_embeddings = [np.random.random(128).tolist()]
        bm25_embeddings = {
            "indices": [1850593538, 11711171],
            "values": [1.66, 1.66]
        }

        embeddings = {
            "dense": text_embedding_3_small_embeddings,
            "rerank": colbertv2_0_embeddings,
            "sparse": bm25_embeddings,
        }
        mock_get_embedding.return_value = embeddings

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
                            f"/collections/{gpt3.bot}_{test_content.collection}{gpt3.suffix}/points/query"),
                method="POST",
                payload={
                    "result": {
                        "points": [
                            {
                                "id": test_content.vector_id,
                                "version": 0,
                                "score": 0.80,
                                "payload": {
                                    "content": test_content.data
                                }
                            }
                        ]
                    },
                    "status": "ok",
                    "time": 0.000957728
                }
            )

            response, time_elapsed = await gpt3.predict(query, user=user, **k_faq_action_config)
            assert response['content'] == "Python is dynamically typed, garbage-collected, high level, general purpose programming."
            assert gpt3.logs == [{'messages': [{'role': 'system', 'content': 'You are a personal assistant. Answer the question according to the below context'}, {'role': 'user', 'content': "Based on below context answer question, if answer not in context check previous logs.\nInstructions on how to use Similarity Prompt:\n['Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.']\nAnswer according to this context.\n \nQ: What kind of language is python? \nA:"}], 'raw_completion_response': {'choices': [{'message': {'content': 'Python is dynamically typed, garbage-collected, high level, general purpose programming.', 'role': 'assistant'}}]}, 'type': 'answer_query', 'hyperparameters': {'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-4o-mini', 'top_p': 0.0, 'n': 1, 'stop': None, 'presence_penalty': 0.0, 'frequency_penalty': 0.0, 'logit_bias': {}, 'stream': True}}]

            assert list(aioresponses.requests.values())[0][0].kwargs['json'] == {
                "prefetch": [
                    {
                        "query": embeddings.get("dense", []),
                        "using": "dense",
                        "limit": 20
                    },
                    {
                        "query": embeddings.get("rerank", []),
                        "using": "rerank",
                        "limit": 20
                    },
                    {
                        "query": embeddings.get("sparse", {}),
                        "using": "sparse",
                        "limit": 20
                    }
                ],
                "query": {"fusion": "rrf"},
                "with_payload": True,
                "score_threshold": 0.70,
                "limit": 10
            }
            assert isinstance(time_elapsed, float) and time_elapsed > 0.0

    @pytest.mark.asyncio
    @mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
    async def test_gpt3_faq_embedding_predict_with_values_with_instructions(self,
                                                                            mock_get_embedding,
                                                                            aioresponses):
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

        text_embedding_3_small_embeddings = np.random.random(1536).tolist()
        colbertv2_0_embeddings = [np.random.random(128).tolist()]
        bm25_embeddings = {
            "indices": [1850593538, 11711171],
            "values": [1.66, 1.66]
        }

        embeddings = {
            "dense": text_embedding_3_small_embeddings,
            "rerank": colbertv2_0_embeddings,
            "sparse": bm25_embeddings,
        }

        mock_get_embedding.return_value = embeddings

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
                        f"/collections/{gpt3.bot}_{test_content1.collection}{gpt3.suffix}/points/query"),
            method="POST",
            payload={
                "result": {
                    "points": [
                        {
                            "id": test_content2.vector_id,
                            "version": 0,
                            "score": 0.80,
                            "payload": {
                                "content": test_content2.data
                            }
                        },
                        {
                            "id": test_content3.vector_id,
                            "version": 0,
                            "score": 0.80,
                            "payload": {
                                "content": test_content3.data
                            }
                        }
                    ]
                },
                "status": "ok",
                "time": 0.000957728
            }
        )

        response, time_elapsed = await gpt3.predict(query, user=user, **k_faq_action_config)
        assert response['content'] == generated_text
        assert not DeepDiff(gpt3.logs, [{'messages': [{'role': 'system', 'content': 'You are a personal assistant. Answer the question according to the below context'}, {'role': 'user', 'content': "Based on below context answer question, if answer not in context check previous logs.\nInstructions on how to use Similarity Prompt:\n[{'name': 'Fahad', 'city': 'Mumbai'}, {'name': 'Hitesh', 'city': 'Mumbai'}]\nAnswer according to this context.\n \nAnswer in a short way.\nKeep it simple. \nQ: List all the user lives in mumbai city \nA:"}], 'raw_completion_response': {'choices': [{'id': 'chatcmpl-836a9b38-dfe9-4ae0-9f94-f431e2e8e8d1', 'choices': [{'finish_reason': 'stop', 'index': 0, 'message': {'content': 'Hitesh and Fahad lives in mumbai city.', 'role': 'assistant'}}], 'created': 1720090691, 'model': None, 'object': 'chat.completion', 'system_fingerprint': None, 'usage': {}}]}, 'type': 'answer_query', 'hyperparameters': {'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-4o-mini', 'top_p': 0.0, 'n': 1, 'stop': None, 'presence_penalty': 0.0, 'frequency_penalty': 0.0, 'logit_bias': {}}}], ignore_order=True)

        assert list(aioresponses.requests.values())[0][0].kwargs['json'] == {
            "prefetch": [
                {
                    "query": embeddings.get("dense", []),
                    "using": "dense",
                    "limit": 20
                },
                {
                    "query": embeddings.get("rerank", []),
                    "using": "rerank",
                    "limit": 20
                },
                {
                    "query": embeddings.get("sparse", {}),
                    "using": "sparse",
                    "limit": 20
                }
            ],
            "query": {"fusion": "rrf"},
            "with_payload": True,
            "score_threshold": 0.70,
            "limit": 10
        }
        assert isinstance(time_elapsed, float) and time_elapsed > 0.0

    @pytest.mark.asyncio
    @mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
    async def test_gpt3_faq_embedding_predict_completion_connection_error(self, mock_get_embedding,
                                                                          aioresponses):
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
        text_embedding_3_small_embeddings = np.random.random(1536).tolist()
        colbertv2_0_embeddings = [np.random.random(128).tolist()]
        bm25_embeddings = {
            "indices": [1850593538, 11711171],
            "values": [1.66, 1.66]
        }

        embeddings = {
            "dense": text_embedding_3_small_embeddings,
            "rerank": colbertv2_0_embeddings,
            "sparse": bm25_embeddings,
        }
        mock_get_embedding.return_value = embeddings

        aioresponses.add(
            url=urljoin(Utility.environment['llm']['url'],
                        f"/{bot}/completion/{llm_type}"),
            method="POST",
            exception=Exception("Connection reset by peer!")
        )

        gpt3 = LLMProcessor(test_content.bot, DEFAULT_LLM)

        aioresponses.add(
            url=urljoin(Utility.environment['vector']['db'],
                        f"/collections/{gpt3.bot}_{test_content.collection}{gpt3.suffix}/points/query"),
            method="POST",
            payload={
                "result": {
                    "points": [
                        {
                            "id": test_content.vector_id,
                            "version": 0,
                            "score": 0.80,
                            "payload": {
                                "content": test_content.data
                            }
                        }
                    ]
                },
                "status": "ok",
                "time": 0.000957728
            }
        )

        response, time_elapsed = await gpt3.predict(query, user=user, **k_faq_action_config)
        assert response == {'is_failure': True, 'exception': 'Internal Server Error', 'content': None}


        assert gpt3.logs == [{'error': 'Retrieving chat completion for the provided query. Internal Server Error'}]

        assert list(aioresponses.requests.values())[0][0].kwargs['json'] == {
            "prefetch": [
                {
                    "query": embeddings.get("dense", []),
                    "using": "dense",
                    "limit": 20
                },
                {
                    "query": embeddings.get("rerank", []),
                    "using": "rerank",
                    "limit": 20
                },
                {
                    "query": embeddings.get("sparse", {}),
                    "using": "sparse",
                    "limit": 20
                }
            ],
            "query": {"fusion": "rrf"},
            "with_payload": True,
            "score_threshold": 0.70,
            "limit": 10
        }
        assert isinstance(time_elapsed, float) and time_elapsed > 0.0


    @pytest.mark.asyncio
    @mock.patch("kairon.shared.rest_client.AioRestClient._AioRestClient__trigger", autospec=True)
    @mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
    async def test_gpt3_faq_embedding_predict_exact_match(self, mock_get_embedding, mock_llm_request):
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

        text_embedding_3_small_embeddings = np.random.random(1536).tolist()
        colbertv2_0_embeddings = [np.random.random(128).tolist()]
        bm25_embeddings = {
            "indices": [1850593538, 11711171],
            "values": [1.66, 1.66]
        }

        embeddings = {
            "dense": text_embedding_3_small_embeddings,
            "rerank": colbertv2_0_embeddings,
            "sparse": bm25_embeddings,
        }

        mock_get_embedding.return_value = embeddings
        mock_llm_request.side_effect = ClientConnectionError()

        gpt3 = LLMProcessor(test_content.bot, DEFAULT_LLM)

        response, time_elapsed = await gpt3.predict(query, user="test", **k_faq_action_config)
        assert response == {'exception': 'Failed to connect to service: localhost', 'is_failure': True, "content": None}

        assert gpt3.logs == [
            {'error': 'Retrieving chat completion for the provided query. Failed to connect to service: localhost'}]
        assert isinstance(time_elapsed, float) and time_elapsed > 0.0

    @pytest.mark.asyncio
    @mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
    async def test_gpt3_faq_embedding_predict_embedding_connection_error(self, mock_get_embedding, aioresponses):
        user = "test"
        bot = "test_gpt3_faq_embedding_predict_embedding_connection_error"
        key = "test"
        llm_type = "openai"
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
        text_embedding_3_small_embeddings = np.random.random(1536).tolist()
        colbertv2_0_embeddings = [np.random.random(128).tolist()]
        bm25_embeddings = {
            "indices": [1850593538, 11711171],
            "values": [1.66, 1.66]
        }

        embeddings = {
            "dense": text_embedding_3_small_embeddings,
            "rerank": colbertv2_0_embeddings,
            "sparse": bm25_embeddings,
        }

        mock_get_embedding.side_effect = Exception("Connection reset by peer!")
        response, time_elapsed = await gpt3.predict(query, user="test", **k_faq_action_config)
        assert response == {'exception': 'Connection reset by peer!', 'is_failure': True, "content": None}

        assert gpt3.logs == [{'error': 'Creating a new embedding for the provided query. Connection reset by peer!'}]
        assert isinstance(time_elapsed, float) and time_elapsed > 0.0

    @pytest.mark.asyncio
    @mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
    async def test_gpt3_faq_embedding_predict_with_previous_bot_responses(self, mock_get_embedding,
                                                                          aioresponses):
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
        text_embedding_3_small_embeddings = np.random.random(1536).tolist()
        colbertv2_0_embeddings = [np.random.random(128).tolist()]
        bm25_embeddings = {
            "indices": [1850593538, 11711171],
            "values": [1.66, 1.66]
        }

        embeddings = {
            "dense": text_embedding_3_small_embeddings,
            "rerank": colbertv2_0_embeddings,
            "sparse": bm25_embeddings,
        }

        mock_get_embedding.return_value = embeddings
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
                        f"/collections/{gpt3.bot}_{test_content.collection}{gpt3.suffix}/points/query"),
            method="POST",
            payload={
                "result": {
                    "points": [
                        {
                            "id": test_content.vector_id,
                            "version": 0,
                            "score": 0.80,
                            "payload": {
                                "content": test_content.data
                            }
                        }
                    ]
                },
                "status": "ok",
                "time": 0.000957728
            }
        )

        response, time_elapsed = await gpt3.predict(query, user=user, **k_faq_action_config)
        assert response['content'] == generated_text

        assert list(aioresponses.requests.values())[0][0].kwargs['json'] == {
            "prefetch": [
                {
                    "query": embeddings.get("dense", []),
                    "using": "dense",
                    "limit": 20
                },
                {
                    "query": embeddings.get("rerank", []),
                    "using": "rerank",
                    "limit": 20
                },
                {
                    "query": embeddings.get("sparse", {}),
                    "using": "sparse",
                    "limit": 20
                }
            ],
            "query": {"fusion": "rrf"},
            "with_payload": True,
            "score_threshold": 0.70,
            "limit": 10
        }

        assert isinstance(time_elapsed, float) and time_elapsed > 0.

    @pytest.mark.asyncio
    @mock.patch.object(LLMProcessor, "get_embedding", autospec=True)
    async def test_gpt3_faq_embedding_predict_with_query_prompt(self, mock_get_embedding, aioresponses):

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
        text_embedding_3_small_embeddings = np.random.random(1536).tolist()
        colbertv2_0_embeddings = [np.random.random(128).tolist()]
        bm25_embeddings = {
            "indices": [1850593538, 11711171],
            "values": [1.66, 1.66]
        }

        embeddings = {
            "dense": text_embedding_3_small_embeddings,
            "rerank": colbertv2_0_embeddings,
            "sparse": bm25_embeddings,
        }

        mock_get_embedding.return_value = embeddings
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
                        f"/collections/{gpt3.bot}_{test_content.collection}{gpt3.suffix}/points/query"),
            method="POST",
            payload={
                "result": {
                    "points": [
                        {
                            "id": test_content.vector_id,
                            "version": 0,
                            "score": 0.80,
                            "payload": {
                                "content": test_content.data
                            }
                        }
                    ]
                },
                "status": "ok",
                "time": 0.000957728
            }
        )

        response, time_elapsed = await gpt3.predict(query, user=user, **k_faq_action_config)
        assert response['content'] == generated_text

        assert list(aioresponses.requests.values())[0][0].kwargs['json'] == {
            "prefetch": [
                {
                    "query": embeddings.get("dense", []),
                    "using": "dense",
                    "limit": 20
                },
                {
                    "query": embeddings.get("rerank", []),
                    "using": "rerank",
                    "limit": 20
                },
                {
                    "query": embeddings.get("sparse", {}),
                    "using": "sparse",
                    "limit": 20
                }
            ],
            "query": {"fusion": "rrf"},
            "with_payload": True,
            "score_threshold": 0.70,
            "limit": 10
        }
        assert isinstance(time_elapsed, float) and time_elapsed > 0.0

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
    @patch("kairon.shared.actions.utils.ActionUtility.execute_request_async", new_callable=AsyncMock)
    async def test_get_embedding_success_single_text(self, mock_execute_request_async):
        bot = "test_bot"
        llm_type = "openai"
        key = "test"
        user = "test"
        texts = "Hello how are you??"
        invocation = "test_invocation"
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
            "embedding": {
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
                    ],
                    [
                        0.0206329133361578,
                        -0.07174995541572571
                    ],
                    [
                        -0.007417665328830481,
                        0.09697738289833069
                    ]
                ]
            }
        }

        mock_execute_request_async.return_value = (mock_response, 200, None, None)

        processor = LLMProcessor(bot, llm_type)
        embeddings = await processor.get_embedding(texts, user, invocation=invocation)

        assert embeddings == mock_response["embedding"]
        mock_execute_request_async.assert_called_once_with(
            http_url=f"{Utility.environment['llm']['url']}/{urllib.parse.quote(bot)}/embedding/{llm_type}",
            request_method="POST",
            request_body={
                'texts': texts,
                'user': user,
                'invocation': invocation
            },
            timeout=Utility.environment['llm'].get('request_timeout', 30)
        )
        LLMSecret.objects.delete()

    @pytest.mark.asyncio
    @patch("kairon.shared.actions.utils.ActionUtility.execute_request_async", new_callable=AsyncMock)
    async def test_get_embedding_success_multiple_texts(self, mock_execute_request_async):
        bot = "test_bot"
        llm_type = "openai"
        key = "test"
        user = "test"
        texts = ["Hello how are you?","I am Python"]
        invocation = "test_invocation"
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
            "embedding": {
                "dense": [
                    [
                        -0.014715306460857391,
                        -0.022890476509928703
                    ],
                    [
                        -0.019074518233537674,
                        -0.0060106911696493626
                    ]
                ],
                "sparse": [
                    {
                        "values": [
                            1.6877434821696136
                        ],
                        "indices": [
                            613153351
                        ]
                    },
                    {
                        "values": [
                            1.6877434821696136
                        ],
                        "indices": [
                            948991206
                        ]
                    }
                ],
                "rerank": [
                    [
                        [
                            -0.17043153941631317,
                            -0.05260511487722397
                        ],
                        [
                            -0.0009218898485414684,
                            0.028302231803536415
                        ],
                        [
                            0.006710350513458252,
                            0.06639177352190018
                        ],
                        [
                            -0.1451372504234314,
                            -0.0822567492723465
                        ]
                    ],
                    [
                        [
                            -0.09881757199764252,
                            -0.05606473982334137
                        ],
                        [
                            -0.06487230211496353,
                            -0.042552437633275986
                        ],
                        [
                            -0.09635651856660843,
                            -0.06676826626062393
                        ],
                        [
                            -0.09975136816501617,
                            -0.07088008522987366
                        ]
                    ]
                ]
            }
        }

        mock_execute_request_async.return_value = (mock_response, 200, None, None)

        processor = LLMProcessor(bot, llm_type)
        embeddings = await processor.get_embedding(texts, user, invocation=invocation)

        assert embeddings == mock_response["embedding"]
        mock_execute_request_async.assert_called_once_with(
            http_url=f"{Utility.environment['llm']['url']}/{urllib.parse.quote(bot)}/embedding/{llm_type}",
            request_method="POST",
            request_body={
                'texts': texts,
                'user': user,
                'invocation': invocation
            },
            timeout=Utility.environment['llm'].get('request_timeout', 30)
        )
        LLMSecret.objects.delete()


    @pytest.mark.asyncio
    @patch("kairon.shared.actions.utils.ActionUtility.execute_request_async", new_callable=AsyncMock)
    async def test_get_embedding_api_error(self, mock_execute_request_async):
        bot = "test_bot"
        llm_type = "openai"
        key = "test"
        user = "test"
        texts = ["Hello how are you?", "I am Python"]
        invocation = "test_invocation"

        llm_secret = LLMSecret(
            llm_type=llm_type,
            api_key=key,
            models=["model1", "model2"],
            api_base_url="https://api.example.com",
            bot=bot,
            user=user
        )
        llm_secret.save()

        mock_execute_request_async.return_value = ({"message": "Internal Server Error"}, 500, None, None)

        processor = LLMProcessor(bot, llm_type)

        with pytest.raises(Exception, match="Failed to fetch embeddings: Internal Server Error"):
            await processor.get_embedding(texts, user, invocation=invocation)

        mock_execute_request_async.assert_called_once_with(
            http_url=f"{Utility.environment['llm']['url']}/{urllib.parse.quote(bot)}/embedding/{llm_type}",
            request_method="POST",
            request_body={
                'texts': texts,
                'user': user,
                'invocation': invocation
            },
            timeout=Utility.environment['llm'].get('request_timeout', 30)
        )
        LLMSecret.objects.delete()

    @pytest.mark.asyncio
    @patch("kairon.shared.actions.utils.ActionUtility.execute_request_async", new_callable=AsyncMock)
    async def test_get_embedding_empty_response(self, mock_execute_request_async):
        bot = "test_bot"
        llm_type = "openai"
        key = "test"
        user = "test"
        texts = ["Hello how are you?", "I am Python"]
        invocation = "test_invocation"

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
        embeddings = await processor.get_embedding(texts, user, invocation=invocation)

        assert embeddings == {}

        mock_execute_request_async.assert_called_once_with(
            http_url=f"{Utility.environment['llm']['url']}/{urllib.parse.quote(bot)}/embedding/{llm_type}",
            request_method="POST",
            request_body={
                'texts': texts,
                'user': user,
                'invocation': invocation
            },
            timeout=Utility.environment['llm'].get('request_timeout', 30)
        )
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