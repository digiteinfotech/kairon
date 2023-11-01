import json
import os
from urllib.parse import urljoin

import mock
import numpy as np
import pytest
from mongoengine import connect

from kairon.exceptions import AppException
from kairon.shared.admin.constants import BotSecretType
from kairon.shared.admin.data_objects import BotSecrets
from kairon.shared.cognition.data_objects import CognitionData, CognitionSchema
from kairon.shared.data.constant import DEFAULT_SYSTEM_PROMPT
from kairon.shared.data.data_objects import LLMSettings
from kairon.shared.llm.factory import LLMFactory
from kairon.shared.llm.gpt3 import GPT3FAQEmbedding, LLMBase
from kairon.shared.utils import Utility


class TestLLM:
    @pytest.fixture(autouse=True, scope="class")
    def init_connection(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))

    def test_llm_base_train(self):
        with pytest.raises(Exception):
            base = LLMBase("Test")
            base.train()

    def test_llm_base_predict(self):
        with pytest.raises(Exception):
            base = LLMBase('Test')
            base.predict("Sample")

    def test_llm_factory_invalid_type(self):
        with pytest.raises(Exception):
            LLMFactory.get_instance("sample")("test", LLMSettings(provider="openai").to_mongo().to_dict())

    def test_llm_factory_faq_type(self):
        BotSecrets(secret_type=BotSecretType.gpt_key.value, value='value', bot='test', user='test').save()
        inst = LLMFactory.get_instance("faq")("test", LLMSettings(provider="openai").to_mongo().to_dict())
        assert isinstance(inst, GPT3FAQEmbedding)
        assert inst.db_url == Utility.environment['vector']['db']
        assert inst.headers == {}

    def test_llm_factory_faq_type_set_vector_key(self):
        with mock.patch.dict(Utility.environment, {'vector': {"db": "http://test:6333", 'key': 'test'}}):
            inst = LLMFactory.get_instance("faq")("test", LLMSettings(provider="openai").to_mongo().to_dict())
            assert isinstance(inst, GPT3FAQEmbedding)
            assert inst.db_url == Utility.environment['vector']['db']
            assert inst.headers == {'api-key': Utility.environment['vector']['key']}

    @pytest.mark.asyncio
    async def test_gpt3_faq_embedding_train(self, aioresponses):
        bot = "test_embed_faq"
        user = "test"
        value = "nupurkhare"
        test_content = CognitionData(
            data="Welcome! Are you completely new to programming? If not then we presume you will be looking for information about why and how to get started with Python",
            bot=bot, user=user).save()
        secret = BotSecrets(secret_type=BotSecretType.gpt_key.value, value=value, bot=bot, user=user).save()

        embedding = list(np.random.random(GPT3FAQEmbedding.__embedding__))
        request_header = {"Authorization": "Bearer nupurkhare"}

        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': secret},
                                                   'vector': {'db': "http://kairon:6333", "key": None}}):
            aioresponses.add(
                url="https://api.openai.com/v1/embeddings",
                method="POST",
                status=200,
                payload={'data': [{'embedding': embedding}]}
            )

            gpt3 = GPT3FAQEmbedding(test_content.bot, LLMSettings(provider="openai").to_mongo().to_dict())

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

            response = await gpt3.train()
            assert response['faq'] == 1

            assert list(aioresponses.requests.values())[1][0].kwargs['json'] == {'name': gpt3.bot + gpt3.suffix,
                                                                                 'vectors': gpt3.vector_config}
            assert list(aioresponses.requests.values())[2][0].kwargs['json'] == {"model": "text-embedding-ada-002",
                                                                                 "input": test_content.data}
            assert list(aioresponses.requests.values())[2][0].kwargs['headers'] == request_header

            assert list(aioresponses.requests.values())[3][0].kwargs['json'] == {
                'points': [{'id': test_content.vector_id,
                            'vector': embedding,
                            'payload': {"collection_name": f"{gpt3.bot}{gpt3.suffix}", 'content': test_content.data}
                            }]}

    @pytest.mark.asyncio
    async def test_gpt3_faq_embedding_train_payload_text(self, aioresponses):
        bot = "test_embed_faq_text"
        user = "test"
        value = "nupurkhare"
        CognitionSchema(
            metadata=[{"column_name": "name", "data_type": "str", "enable_search": True, "create_embeddings": True},
                      {"column_name": "city", "data_type": "str", "enable_search": False, "create_embeddings": True}],
            collection_name="User_details",
            bot=bot, user=user
        ).save()
        CognitionSchema(
            metadata=[{"column_name": "country", "data_type": "str", "enable_search": True, "create_embeddings": True},
                      {"column_name": "lang", "data_type": "str", "enable_search": False, "create_embeddings": True},
                      {"column_name": "role", "data_type": "str", "enable_search": True, "create_embeddings": True}],
            collection_name="Country_details",
            bot=bot, user=user).save()
        test_content = CognitionData(
            data={"name": "Nupur", "city": "Pune"},
            content_type="json",
            collection="User_details",
            bot=bot, user=user).save()
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
        secret = BotSecrets(secret_type=BotSecretType.gpt_key.value, value=value, bot=bot, user=user).save()

        embedding = list(np.random.random(GPT3FAQEmbedding.__embedding__))
        request_header = {"Authorization": "Bearer nupurkhare"}

        aioresponses.add(
            url="https://api.openai.com/v1/embeddings",
            method="POST",
            status=200,
            payload={'data': [{'embedding': embedding}]},
            repeat=True
        )

        gpt3 = GPT3FAQEmbedding(test_content.bot, LLMSettings(provider="openai").to_mongo().to_dict())
        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': secret}}):
            aioresponses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections"),
                method="GET",
                payload={"time": 0, "status": "ok", "result": {"collections": [{"name": "test_embed_faq_text_swift_faq_embd"},
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
                url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}_user_details{gpt3.suffix}/points"),
                method="PUT",
                payload={"result": {"operation_id": 0, "status": "acknowledged"}, "status": "ok", "time": 0.003612634}
            )

            aioresponses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}_country_details{gpt3.suffix}"),
                method="PUT",
                status=200
            )

            aioresponses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}_country_details{gpt3.suffix}/points"),
                method="PUT",
                payload={"result": {"operation_id": 0, "status": "acknowledged"}, "status": "ok", "time": 0.003612634}
            )

            aioresponses.add(
                url=urljoin(Utility.environment['vector']['db'],
                            f"/collections/test_embed_faq_text_country_details_faq_embd/points"),
                method="PUT",
                payload={"result": {"operation_id": 0, "status": "acknowledged"}, "status": "ok", "time": 0.003612634}
            )

            response = await gpt3.train()
            assert response['faq'] == 3

            assert list(aioresponses.requests.values())[2][0].kwargs['json'] == {'name': f"{gpt3.bot}_country_details{gpt3.suffix}",
                                                                                 'vectors': gpt3.vector_config}

            assert list(aioresponses.requests.values())[3][0].kwargs['json'] == {"model": "text-embedding-ada-002",
                                                                                 "input": '{"country": "Spain", "lang": "spanish"}'}
            assert list(aioresponses.requests.values())[3][0].kwargs['headers'] == request_header
            assert list(aioresponses.requests.values())[3][1].kwargs['json'] == {"model": "text-embedding-ada-002",
                                                                                 "input": '{"lang": "spanish", "role": "ds"}'}
            assert list(aioresponses.requests.values())[3][1].kwargs['headers'] == request_header
            assert list(aioresponses.requests.values())[3][2].kwargs['json'] == {"model": "text-embedding-ada-002",
                                                                                 "input": '{"name": "Nupur", "city": "Pune"}'}
            assert list(aioresponses.requests.values())[3][2].kwargs['headers'] == request_header
            assert list(aioresponses.requests.values())[4][0].kwargs['json'] == {'points': [{'id': test_content_two.vector_id,
                                                                                             'vector': embedding,
                                                                                             'payload': {'collection_name': f"{gpt3.bot}_country_details{gpt3.suffix}",
                                                                                                         'country': 'Spain'}}]}
            assert list(aioresponses.requests.values())[4][1].kwargs['json'] == {'points': [{'id': test_content_three.vector_id,
                                                                                             'vector': embedding,
                                                                                             'payload': {'collection_name': f"{gpt3.bot}_country_details{gpt3.suffix}", 'role': 'ds'}}]}

            assert list(aioresponses.requests.values())[5][0].kwargs['json'] == {'name': f"{gpt3.bot}_user_details{gpt3.suffix}",
                                                                                 'vectors': gpt3.vector_config}
            assert list(aioresponses.requests.values())[6][0].kwargs['json'] == {'points': [{'id': test_content.vector_id,
                                                                                             'vector': embedding,
                                                                                             'payload': {'collection_name': f"{gpt3.bot}_user_details{gpt3.suffix}",
                                                                                                         'name': 'Nupur'}}]}
            assert response['faq'] == 3

    @pytest.mark.asyncio
    async def test_gpt3_faq_embedding_train_payload_with_int(self, aioresponses):
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
            data={"name": "Ram", "age": "23", "color": "red"},
            content_type="json",
            collection="payload_with_int",
            bot=bot, user=user).save()
        secret = BotSecrets(secret_type=BotSecretType.gpt_key.value, value=value, bot=bot, user=user).save()

        embedding = list(np.random.random(GPT3FAQEmbedding.__embedding__))
        request_header = {"Authorization": "Bearer nupurkhare"}
        input = {"name": "Ram", "color": "red"}
        aioresponses.add(
            url="https://api.openai.com/v1/embeddings",
            method="POST",
            status=200,
            payload={'data': [{'embedding': embedding}]}
        )

        gpt3 = GPT3FAQEmbedding(test_content.bot, LLMSettings(provider="openai").to_mongo().to_dict())
        aioresponses.add(
            url=urljoin(Utility.environment['vector']['db'], f"/collections/test_embed_faq_json_payload_with_int_faq_embd"),
            method="PUT",
            status=200
        )
        aioresponses.add(
            url=urljoin(Utility.environment['vector']['db'], f"/collections"),
            method="GET",
            payload={"time": 0, "status": "ok", "result": {"collections": []}})

        aioresponses.add(
            url=urljoin(Utility.environment['vector']['db'], f"/collections/test_embed_faq_json_payload_with_int_faq_embd/points"),
            method="PUT",
            payload={"result": {"operation_id": 0, "status": "acknowledged"}, "status": "ok", "time": 0.003612634}
        )

        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': secret}}):
            response = await gpt3.train()
            assert response['faq'] == 1

            assert list(aioresponses.requests.values())[1][0].kwargs['json'] == {'name': 'test_embed_faq_json_payload_with_int_faq_embd',
                                                                                 'vectors': gpt3.vector_config}
            assert list(aioresponses.requests.values())[2][0].kwargs['json'] == {"model": "text-embedding-ada-002",
                                                                                 "input": json.dumps(input)}
            assert list(aioresponses.requests.values())[2][0].kwargs['headers'] == request_header
            assert list(aioresponses.requests.values())[3][0].kwargs['json'] == {'points': [{'id': test_content.vector_id,
                            'vector': embedding,
                            'payload': {'name': 'Ram', 'age': 23, 'color': 'red', "collection_name": "test_embed_faq_json_payload_with_int_faq_embd"}
                            }]}

    @pytest.mark.asyncio
    async def test_gpt3_faq_embedding_train_int(self, aioresponses):
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
        secret = BotSecrets(secret_type=BotSecretType.gpt_key.value, value=value, bot=bot, user=user).save()

        embedding = list(np.random.random(GPT3FAQEmbedding.__embedding__))
        request_header = {"Authorization": "Bearer nupurkhare"}
        input = {"name": "Ram", "color": "red"}
        aioresponses.add(
            url="https://api.openai.com/v1/embeddings",
            method="POST",
            status=200,
            payload={'data': [{'embedding': embedding}]}
        )

        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': secret}}):
            gpt3 = GPT3FAQEmbedding(test_content.bot, LLMSettings(provider="openai").to_mongo().to_dict())

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

            response = await gpt3.train()
            assert response['faq'] == 1

            assert list(aioresponses.requests.values())[1][0].kwargs['json'] == {'name': 'test_int_embd_int_faq_embd',
                                                                                 'vectors': gpt3.vector_config}
            assert list(aioresponses.requests.values())[2][0].kwargs['json'] == {"model": "text-embedding-ada-002",
                                                                                 "input": json.dumps(input)}
            assert list(aioresponses.requests.values())[2][0].kwargs['headers'] == request_header
            expected_payload = test_content.data
            expected_payload['collection_name'] = 'test_int_embd_int_faq_embd'
            assert list(aioresponses.requests.values())[3][0].kwargs['json'] == {
                'points': [{'id': test_content.vector_id,
                            'vector': embedding,
                            'payload': expected_payload
                            }]}

    def test_gpt3_faq_embedding_train_failure(self):
        with pytest.raises(AppException, match=f"Bot secret '{BotSecretType.gpt_key.value}' not configured!"):
            GPT3FAQEmbedding('test_failure', LLMSettings(provider="openai").to_mongo().to_dict())

    @pytest.mark.asyncio
    async def test_gpt3_faq_embedding_train_upsert_error(self, aioresponses):
        bot = "test_embed_faq_not_exists"
        user = "test"
        value = "nupurk"
        test_content = CognitionData(
            data="Welcome! Are you completely new to programming? If not then we presume you will be looking for information about why and how to get started with Python",
            bot=bot, user=user).save()
        secret = BotSecrets(secret_type=BotSecretType.gpt_key.value, value=value, bot=bot, user=user).save()

        embedding = list(np.random.random(GPT3FAQEmbedding.__embedding__))

        request_header = {"Authorization": "Bearer nupurk"}

        aioresponses.add(
            url="https://api.openai.com/v1/embeddings",
            method="POST",
            status=200,
            payload={'data': [{'embedding': embedding}]}
        )

        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': secret}}):
            gpt3 = GPT3FAQEmbedding(test_content.bot, LLMSettings(provider="openai").to_mongo().to_dict())

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
                await gpt3.train()

            assert list(aioresponses.requests.values())[1][0].kwargs['json'] == {'name': gpt3.bot + gpt3.suffix, 'vectors': gpt3.vector_config}
            assert list(aioresponses.requests.values())[2][0].kwargs['json'] == {"model": "text-embedding-ada-002", "input": test_content.data}
            assert list(aioresponses.requests.values())[2][0].kwargs['headers'] == request_header
            assert list(aioresponses.requests.values())[3][0].kwargs['json'] == {'points': [{'id': test_content.vector_id,
                                                                  'vector': embedding, 'payload': {'collection_name': f"{bot}{gpt3.suffix}",'content': test_content.data}}]}


    @pytest.mark.asyncio
    async def test_gpt3_faq_embedding_train_payload_upsert_error_json(self, aioresponses):
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
        secret = BotSecrets(secret_type=BotSecretType.gpt_key.value, value=value, bot=bot, user=user).save()

        embedding = list(np.random.random(GPT3FAQEmbedding.__embedding__))

        request_header = {"Authorization": "Bearer nupurk"}

        aioresponses.add(
            url="https://api.openai.com/v1/embeddings",
            method="POST",
            status=200,
            payload={'data': [{'embedding': embedding}]}
        )

        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': secret}}):
            gpt3 = GPT3FAQEmbedding(test_content.bot, LLMSettings(provider="openai").to_mongo().to_dict())

            aioresponses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections"),
                method="GET",
                payload={"time": 0, "status": "ok", "result": {"collections": []}})

            aioresponses.add(
                method="DELETE",
                url=urljoin(Utility.environment['vector']['db'], f"/collections/payload_upsert_error_error_json_faq_embd"),
            )

            aioresponses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/payload_upsert_error_error_json_faq_embd"),
                method="PUT",
                status=200
            )

            aioresponses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/payload_upsert_error_error_json_faq_embd/points"),
                method="PUT",
                payload={"result": None,
                      'status': {'error': 'Json deserialize error: missing field `vectors` at line 1 column 34779'},
                      "time": 0.003612634}
            )

            with pytest.raises(AppException, match="Unable to train FAQ! Contact support"):
                await gpt3.train()

            assert list(aioresponses.requests.values())[1][0].kwargs['json'] == {'name': 'payload_upsert_error_error_json_faq_embd', 'vectors': gpt3.vector_config}
            assert list(aioresponses.requests.values())[2][0].kwargs['json'] == {"model": "text-embedding-ada-002", "input": json.dumps(test_content.data)}
            assert list(aioresponses.requests.values())[2][0].kwargs['headers'] == request_header
            expected_payload = test_content.data
            expected_payload['collection_name'] = 'payload_upsert_error_error_json_faq_embd'
            assert list(aioresponses.requests.values())[3][0].kwargs['json'] == {'points': [{'id': test_content.vector_id,
                                                                           'vector': embedding,
                                                                           'payload': expected_payload
                                                                           }]}

    @pytest.mark.asyncio
    async def test_gpt3_faq_embedding_predict(self, aioresponses):
        embedding = list(np.random.random(GPT3FAQEmbedding.__embedding__))

        bot = "test_embed_faq_predict"
        user = "test"
        value = "knupur"
        test_content = CognitionData(
            data="Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.",
            bot=bot, user=user).save()
        secret = BotSecrets(secret_type=BotSecretType.gpt_key.value, value=value, bot=bot, user=user).save()

        generated_text = "Python is dynamically typed, garbage-collected, high level, general purpose programming."
        query = "What kind of language is python?"

        k_faq_action_config = {
            "system_prompt": "You are a personal assistant. Answer the question according to the below context",
            "context_prompt": "Based on below context answer question, if answer not in context check previous logs.",
            "top_results": 10, "similarity_threshold": 0.70, 'use_similarity_prompt': True,
            'similarity_prompt_name': 'Similarity Prompt',
            'similarity_prompt_instructions': 'Answer according to this context.'}
        hyperparameters = Utility.get_llm_hyperparameters()
        mock_completion_request = {"messages": [
            {'role': 'system',
             'content': 'You are a personal assistant. Answer the question according to the below context'},
            {'role': 'user',
             'content': 'Based on below context answer question, if answer not in context check previous logs.\nSimilarity Prompt:\nPython is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.\nInstructions on how to use Similarity Prompt: Answer according to this context.\n \nQ: What kind of language is python? \nA:'}
        ]}
        mock_completion_request.update(hyperparameters)
        request_header = {"Authorization": "Bearer knupur"}

        aioresponses.add(
            url="https://api.openai.com/v1/embeddings",
            method="POST",
            status=200,
            payload={'data': [{'embedding': embedding}]}
        )

        aioresponses.add(
            url="https://api.openai.com/v1/chat/completions",
            method="POST",
            status=200,
            payload={'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}
        )

        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': secret}}):
            gpt3 = GPT3FAQEmbedding(test_content.bot, LLMSettings(provider="openai").to_mongo().to_dict())

            aioresponses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.suffix}/points/search"),
                method="POST",
                payload={'result': [
                    {'id': test_content.vector_id, 'score': 0.80, "payload": {'content': test_content.data}}]}
            )

            response = await gpt3.predict(query, **k_faq_action_config)
            assert response['content'] == generated_text

            assert list(aioresponses.requests.values())[0][0].kwargs['json'] == {"model": "text-embedding-ada-002",
                                                                                 "input": query}
            assert list(aioresponses.requests.values())[0][0].kwargs['headers'] == request_header

            assert list(aioresponses.requests.values())[1][0].kwargs['json'] == {'vector': embedding, 'limit': 10,
                                                                                 'with_payload': True,
                                                                                 'score_threshold': 0.70}

            assert list(aioresponses.requests.values())[2][0].kwargs['json'] == mock_completion_request
            assert list(aioresponses.requests.values())[2][0].kwargs['headers'] == request_header

    @pytest.mark.asyncio
    async def test_gpt3_faq_embedding_predict_with_values(self, aioresponses):
        embedding = list(np.random.random(GPT3FAQEmbedding.__embedding__))

        test_content = CognitionData(
            data="Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.",
            bot="test_embed_faq_predict", user="test").save()

        generated_text = "Python is dynamically typed, garbage-collected, high level, general purpose programming."
        query = "What kind of language is python?"
        k_faq_action_config = {
            "system_prompt": "You are a personal assistant. Answer the question according to the below context",
            "context_prompt": "Based on below context answer question, if answer not in context check previous logs.",
            "top_results": 10, "similarity_threshold": 0.70, 'use_similarity_prompt': True,
            'similarity_prompt_name': 'Similarity Prompt',
            'similarity_prompt_instructions': 'Answer according to this context.'}

        hyperparameters = Utility.get_llm_hyperparameters()
        mock_completion_request = {"messages": [
            {"role": "system",
             "content": "You are a personal assistant. Answer the question according to the below context"},
            {'role': 'user',
             'content': 'Based on below context answer question, if answer not in context check previous logs.\nSimilarity Prompt:\nPython is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.\nInstructions on how to use Similarity Prompt: Answer according to this context.\n \nQ: What kind of language is python? \nA:'}
        ]}
        mock_completion_request.update(hyperparameters)
        request_header = {"Authorization": "Bearer knupur"}

        aioresponses.add(
            url="https://api.openai.com/v1/embeddings",
            method="POST",
            status=200,
            payload={'data': [{'embedding': embedding}]}
        )

        aioresponses.add(
            url="https://api.openai.com/v1/chat/completions",
            method="POST",
            status=200,
            payload={'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}
        )

        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': 'test'}}):
            gpt3 = GPT3FAQEmbedding(test_content.bot, LLMSettings(provider="openai").to_mongo().to_dict())

            aioresponses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.suffix}/points/search"),
                method="POST",
                payload={'result': [
                    {'id': test_content.vector_id, 'score': 0.80, "payload": {'content': test_content.data}}]}
            )

            response = await gpt3.predict(query, **k_faq_action_config)
            assert response['content'] == generated_text
            assert gpt3.logs == [
                {'messages': [{'role': 'system',
                               'content': 'You are a personal assistant. Answer the question according to the below context'},
                              {'role': 'user',
                               'content': 'Based on below context answer question, if answer not in context check previous logs.\nSimilarity Prompt:\nPython is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.\nInstructions on how to use Similarity Prompt: Answer according to this context.\n \nQ: What kind of language is python? \nA:'}],
                 'raw_completion_response': {'choices': [{
                     'message': {
                         'content': 'Python is dynamically typed, garbage-collected, high level, general purpose programming.',
                         'role': 'assistant'}}]},
                 'type': 'answer_query',
                 'hyperparameters': {'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-3.5-turbo', 'top_p': 0.0,
                                     'n': 1, 'stream': False, 'stop': None, 'presence_penalty': 0.0,
                                     'frequency_penalty': 0.0, 'logit_bias': {}}}]

            assert list(aioresponses.requests.values())[0][0].kwargs['json'] == {"model": "text-embedding-ada-002", "input": query}
            assert list(aioresponses.requests.values())[0][0].kwargs['headers'] == request_header

            assert list(aioresponses.requests.values())[1][0].kwargs['json'] == {'vector': embedding, 'limit': 10, 'with_payload': True, 'score_threshold': 0.70}

            assert list(aioresponses.requests.values())[2][0].kwargs['json'] == mock_completion_request
            assert list(aioresponses.requests.values())[2][0].kwargs['headers'] == request_header

    @pytest.mark.asyncio
    async def test_gpt3_faq_embedding_predict_with_values_with_instructions(self, aioresponses):
        embedding = list(np.random.random(GPT3FAQEmbedding.__embedding__))

        test_content = CognitionData(
            data="Java is a high-level, general-purpose programming language. Java is known for its write once, run anywhere capability. ",
            bot="test_embed_faq_predict", user="test").save()

        generated_text = "Python is dynamically typed, garbage-collected, high level, general purpose programming."
        query = "What kind of language is python?"
        k_faq_action_config = {
            "system_prompt": "You are a personal assistant. Answer the question according to the below context",
            "context_prompt": "Based on below context answer question, if answer not in context check previous logs.",
            "top_results": 10, "similarity_threshold": 0.70, 'use_similarity_prompt': True,
            'similarity_prompt_name': 'Similarity Prompt',
            'similarity_prompt_instructions': 'Answer according to this context.',
            'instructions': ['Answer in a short way.', 'Keep it simple.']}

        hyperparameters = Utility.get_llm_hyperparameters()
        mock_completion_request = {"messages": [
            {'role': 'system',
             'content': 'You are a personal assistant. Answer the question according to the below context'},
            {'role': 'user',
             'content': 'Based on below context answer question, if answer not in context check previous logs.\nSimilarity Prompt:\nJava is a high-level, general-purpose programming language. Java is known for its write once, run anywhere capability. \nInstructions on how to use Similarity Prompt: Answer according to this context.\n \nAnswer in a short way.\nKeep it simple. \nQ: What kind of language is python? \nA:'}
        ]}
        mock_completion_request.update(hyperparameters)
        request_header = {"Authorization": "Bearer knupur"}

        aioresponses.add(
            url="https://api.openai.com/v1/embeddings",
            method="POST",
            status=200,
            payload={'data': [{'embedding': embedding}]}
        )

        aioresponses.add(
            url="https://api.openai.com/v1/chat/completions",
            method="POST",
            status=200,
            payload={'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}
        )

        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': 'test'}}):
            gpt3 = GPT3FAQEmbedding(test_content.bot, LLMSettings(provider="openai").to_mongo().to_dict())

            aioresponses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.suffix}/points/search"),
                method="POST",
                payload={'result': [
                    {'id': test_content.vector_id, 'score': 0.80, "payload": {'content': test_content.data}}]}
            )

            response = await gpt3.predict(query, **k_faq_action_config)
            assert response['content'] == generated_text
            assert gpt3.logs == [
                {'messages': [{'role': 'system',
                               'content': 'You are a personal assistant. Answer the question according to the below context'},
                              {'role': 'user',
                               'content': 'Based on below context answer question, if answer not in context '
                                          'check previous logs.\nSimilarity Prompt:\nJava is a high-level, general-purpose '
                                          'programming language. Java is known for its write once, run anywhere capability. '
                                          '\nInstructions on how to use Similarity Prompt: Answer according to this context.'
                                          '\n \nAnswer in a short way.\nKeep it simple. \nQ: What kind of language is python? \nA:'}],
                 'raw_completion_response': {
                     'choices': [{'message': {'content': 'Python is dynamically typed, garbage-collected, '
                                                         'high level, general purpose programming.',
                                              'role': 'assistant'}}]},
                 'type': 'answer_query',
                 'hyperparameters': {'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-3.5-turbo', 'top_p': 0.0,
                                     'n': 1,
                                     'stream': False, 'stop': None, 'presence_penalty': 0.0, 'frequency_penalty': 0.0,
                                     'logit_bias': {}}}]

            assert list(aioresponses.requests.values())[0][0].kwargs['json'] == {"model": "text-embedding-ada-002", "input": query}
            assert list(aioresponses.requests.values())[0][0].kwargs['headers'] == request_header

            assert list(aioresponses.requests.values())[1][0].kwargs['json'] == {'vector': embedding, 'limit': 10, 'with_payload': True, 'score_threshold': 0.70}

            assert list(aioresponses.requests.values())[2][0].kwargs['json'] == mock_completion_request
            assert list(aioresponses.requests.values())[2][0].kwargs['headers'] == request_header

    @pytest.mark.asyncio
    @mock.patch.object(GPT3FAQEmbedding, "_GPT3FAQEmbedding__get_answer", autospec=True)
    @mock.patch.object(GPT3FAQEmbedding, "_GPT3FAQEmbedding__get_embedding", autospec=True)
    async def test_gpt3_faq_embedding_predict_completion_connection_error(self, mock_embedding, mock_completion, aioresponses):
        embedding = list(np.random.random(GPT3FAQEmbedding.__embedding__))

        test_content = CognitionData(
            data="Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.",
            bot="test_embed_faq_predict", user="test").save()

        generated_text = "Python is dynamically typed, garbage-collected, high level, general purpose programming."
        query = "What kind of language is python?"
        k_faq_action_config = {
            "system_prompt": "You are a personal assistant. Answer the question according to the below context",
            "context_prompt": "Based on below context answer question, if answer not in context check previous logs.",
            "top_results": 10, "similarity_threshold": 0.70, 'use_similarity_prompt': True,
            'similarity_prompt_name': 'Similarity Prompt',
            'similarity_prompt_instructions': 'Answer according to this context.', "enable_response_cache": True}

        def __mock_connection_error(*args, **kwargs):
            import openai

            raise openai.error.APIConnectionError("Connection reset by peer!")

        mock_embedding.return_value = embedding
        mock_completion.side_effect = __mock_connection_error

        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': 'test'}}):
            gpt3 = GPT3FAQEmbedding(test_content.bot, LLMSettings(provider="openai").to_mongo().to_dict())

            aioresponses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.suffix}/points/search"),
                method="POST",
                payload={'result': [
                    {'id': test_content.vector_id, 'score': 0.80, "payload": {'content': test_content.data}}]}
            )

            response = await gpt3.predict(query, **k_faq_action_config)

            assert response == {'exception': "Connection reset by peer!", 'is_failure': True, "content": None}

            assert mock_embedding.call_args.args[1] == query

            assert mock_completion.call_args.args[1] == 'What kind of language is python?'
            assert mock_completion.call_args.args[
                       2] == 'You are a personal assistant. Answer the question according to the below context'
            assert mock_completion.call_args.args[3] == """Based on below context answer question, if answer not in context check previous logs.
Similarity Prompt:
Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.
Instructions on how to use Similarity Prompt: Answer according to this context.
"""
            assert mock_completion.call_args.kwargs == {'top_results': 10, 'similarity_threshold': 0.7,
                                                        'use_similarity_prompt': True, 'enable_response_cache': True,
                                                        'similarity_prompt_name': 'Similarity Prompt',
                                                        'similarity_prompt_instructions': 'Answer according to this context.'}
            assert gpt3.logs == [{'error': 'Retrieving chat completion for the provided query. Connection reset by peer!'}]

            assert list(aioresponses.requests.values())[0][0].kwargs['json'] == {'vector': embedding, 'limit': 10, 'with_payload': True, 'score_threshold': 0.70}

    @pytest.mark.asyncio
    @mock.patch.object(GPT3FAQEmbedding, "_GPT3FAQEmbedding__get_embedding", autospec=True)
    async def test_gpt3_faq_embedding_predict_exact_match(self, mock_embedding):
        embedding = list(np.random.random(GPT3FAQEmbedding.__embedding__))

        test_content = CognitionData(
            data="Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.",
            bot="test_embed_faq_predict", user="test").save()

        query = "What kind of language is python?"
        k_faq_action_config = {
            "system_prompt": "You are a personal assistant. Answer the question according to the below context",
            "context_prompt": "Based on below context answer question, if answer not in context check previous logs.",
            "top_results": 10, "similarity_threshold": 0.70, 'use_similarity_prompt': True,
            'similarity_prompt_name': 'Similarity Prompt',
            'similarity_prompt_instructions': 'Answer according to this context.', "enable_response_cache": True}

        mock_embedding.return_value = embedding

        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': 'test'}}):
            gpt3 = GPT3FAQEmbedding(test_content.bot, LLMSettings(provider="openai").to_mongo().to_dict())

            response = await gpt3.predict(query, **k_faq_action_config)
            assert response == {'exception': 'Failed to connect to service: localhost', 'is_failure': True, "content": None}

            assert mock_embedding.call_args.args[1] == query
            assert gpt3.logs == []

    @pytest.mark.asyncio
    @mock.patch.object(GPT3FAQEmbedding, "_GPT3FAQEmbedding__get_embedding", autospec=True)
    async def test_gpt3_faq_embedding_predict_embedding_connection_error(self, mock_embedding):
        import openai

        embedding = list(np.random.random(GPT3FAQEmbedding.__embedding__))

        test_content = CognitionData(
            data="Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.",
            bot="test_embed_faq_predict", user="test").save()

        generated_text = "Python is dynamically typed, garbage-collected, high level, general purpose programming."
        query = "What kind of language is python?"
        k_faq_action_config = {
            "system_prompt": "You are a personal assistant. Answer the question according to the below context",
            "context_prompt": "Based on below context answer question, if answer not in context check previous logs.",
            "top_results": 10, "similarity_threshold": 0.70, "enable_response_cache": True}

        mock_embedding.side_effect = [openai.error.APIConnectionError("Connection reset by peer!"), embedding]

        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': 'test'}}):
            gpt3 = GPT3FAQEmbedding(test_content.bot, LLMSettings(provider="openai").to_mongo().to_dict())

            response = await gpt3.predict(query, **k_faq_action_config)
            assert response == {'exception': 'Connection reset by peer!', 'is_failure': True, "content": None}

            assert mock_embedding.call_args.args[1] == query
            assert gpt3.logs == [{'error': 'Creating a new embedding for the provided query. Connection reset by peer!'}]

    @pytest.mark.asyncio
    async def test_gpt3_faq_embedding_predict_with_previous_bot_responses(self, aioresponses):
        embedding = list(np.random.random(GPT3FAQEmbedding.__embedding__))

        bot = "test_embed_faq_predict"
        user = "test"
        test_content = CognitionData(
            data="Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.",
            bot=bot, user=user).save()

        generated_text = "Python is dynamically typed, garbage-collected, high level, general purpose programming."
        query = "What kind of language is python?"
        k_faq_action_config = {
            "previous_bot_responses": [
                {'role': 'user', 'content': 'hello'},
                {'role': 'assistant', 'content': 'how are you'},
            ], 'use_similarity_prompt': True, 'similarity_prompt_name': 'Similarity Prompt',
            'similarity_prompt_instructions': 'Answer according to this context.'}
        hyperparameters = Utility.get_llm_hyperparameters()
        mock_completion_request = {"messages": [
            {'role': 'system', 'content': 'You are a personal assistant. Answer question based on the context below'},
            {'role': 'user', 'content': 'hello'},
            {'role': 'assistant', 'content': 'how are you'},
            {'role': 'user',
             'content': 'Answer question based on the context below, if answer is not in the context go check previous logs.\nSimilarity Prompt:\nPython is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.\nInstructions on how to use Similarity Prompt: Answer according to this context.\n \nQ: What kind of language is python? \nA:'}
        ]}
        mock_completion_request.update(hyperparameters)
        request_header = {"Authorization": "Bearer knupur"}

        aioresponses.add(
            url="https://api.openai.com/v1/embeddings",
            method="POST",
            status=200,
            payload={'data': [{'embedding': embedding}]}
        )

        aioresponses.add(
            url="https://api.openai.com/v1/chat/completions",
            method="POST",
            status=200,
            payload={'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}
        )

        gpt3 = GPT3FAQEmbedding(test_content.bot, LLMSettings(provider="openai").to_mongo().to_dict())

        aioresponses.add(
            url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.suffix}/points/search"),
            method="POST",
            payload={'result': [
                {'id': test_content.vector_id, 'score': 0.80, "payload": {'content': test_content.data}}]}
        )

        response = await gpt3.predict(query, **k_faq_action_config)
        assert response['content'] == generated_text

        assert list(aioresponses.requests.values())[0][0].kwargs['json'] == {"model": "text-embedding-ada-002",
                                                                             "input": query}
        assert list(aioresponses.requests.values())[0][0].kwargs['headers'] == request_header

        assert list(aioresponses.requests.values())[1][0].kwargs['json'] == {'vector': embedding, 'limit': 10,
                                                                             'with_payload': True,
                                                                             'score_threshold': 0.70}

        assert list(aioresponses.requests.values())[2][0].kwargs['json'] == mock_completion_request
        assert list(aioresponses.requests.values())[2][0].kwargs['headers'] == request_header

    @pytest.mark.asyncio
    async def test_gpt3_faq_embedding_predict_with_query_prompt(self, aioresponses):
        embedding = list(np.random.random(GPT3FAQEmbedding.__embedding__))

        bot = "test_embed_faq_predict"
        user = "test"
        test_content = CognitionData(
            data="Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.",
            bot=bot, user=user).save()

        generated_text = "Python is dynamically typed, garbage-collected, high level, general purpose programming."
        query = "What kind of language is python?"
        rephrased_query = "Explain python is called high level programming language in laymen terms?"
        k_faq_action_config = {
            "query_prompt": "A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.",
            "use_query_prompt": True, 'use_similarity_prompt': True, 'similarity_prompt_name': 'Similarity Prompt',
            'similarity_prompt_instructions': 'Answer according to this context.'
        }
        hyperparameters = Utility.get_llm_hyperparameters()
        mock_rephrase_request = {"messages": [
            {"role": "system",
             "content": DEFAULT_SYSTEM_PROMPT},
            {"role": "user",
             "content": f"{k_faq_action_config['query_prompt']}\n\n Q: {query}\n A:"}
        ]}

        mock_completion_request = {"messages": [
            {"role": "system",
             "content": DEFAULT_SYSTEM_PROMPT},
            {'role': 'user',
             'content': 'Answer question based on the context below, if answer is not in the context go check previous logs.\nSimilarity Prompt:\nPython is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.\nInstructions on how to use Similarity Prompt: Answer according to this context.\n \nQ: Explain python is called high level programming language in laymen terms? \nA:'}
        ]}
        mock_rephrase_request.update(hyperparameters)
        mock_completion_request.update(hyperparameters)
        request_header = {"Authorization": "Bearer knupur"}

        aioresponses.add(
            url="https://api.openai.com/v1/embeddings",
            method="POST",
            status=200,
            payload={'data': [{'embedding': embedding}]}
        )

        aioresponses.add(
            url="https://api.openai.com/v1/chat/completions",
            method="POST",
            status=200,
            payload={'choices': [{'message': {'content': rephrased_query, 'role': 'assistant'}}]}
        )

        aioresponses.add(
            url="https://api.openai.com/v1/chat/completions",
            method="POST",
            status=200,
            payload={'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]},
            repeat=True
        )

        gpt3 = GPT3FAQEmbedding(test_content.bot, LLMSettings(provider="openai").to_mongo().to_dict())

        aioresponses.add(
            url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.suffix}/points/search"),
            method="POST",
            payload={'result': [
                {'id': test_content.vector_id, 'score': 0.80, "payload": {'content': test_content.data}}]}
        )

        response = await gpt3.predict(query, **k_faq_action_config)
        assert response['content'] == generated_text

        assert list(aioresponses.requests.values())[0][0].kwargs['json'] == {"model": "text-embedding-ada-002",
                                                                             "input": query}
        assert list(aioresponses.requests.values())[0][0].kwargs['headers'] == request_header
        assert list(aioresponses.requests.values())[1][0].kwargs['json'] == {'vector': embedding, 'limit': 10,
                                                                             'with_payload': True,
                                                                             'score_threshold': 0.70}
        assert list(aioresponses.requests.values())[2][0].kwargs['json'] == mock_rephrase_request
        assert list(aioresponses.requests.values())[2][0].kwargs['headers'] == request_header
        assert list(aioresponses.requests.values())[2][1].kwargs['json'] == mock_completion_request
        assert list(aioresponses.requests.values())[2][1].kwargs['headers'] == request_header
