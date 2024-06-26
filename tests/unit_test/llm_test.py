import os
from unittest import mock
from urllib.parse import urljoin

import numpy as np
import pytest
import ujson as json
from aiohttp import ClientConnectionError
from mongoengine import connect

from kairon.shared.utils import Utility

Utility.load_system_metadata()

from kairon.exceptions import AppException
from kairon.shared.admin.constants import BotSecretType
from kairon.shared.admin.data_objects import BotSecrets
from kairon.shared.cognition.data_objects import CognitionData, CognitionSchema
from kairon.shared.data.constant import DEFAULT_SYSTEM_PROMPT
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
        secret = BotSecrets(secret_type=BotSecretType.gpt_key.value, value=value, bot=bot, user=user).save()

        embedding = list(np.random.random(LLMProcessor.__embedding__))
        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': secret},
                                                   'vector': {'db': "http://kairon:6333", "key": None}}):
            mock_embedding.return_value = {'data': [{'embedding': embedding}]}
            gpt3 = LLMProcessor(test_content.bot)

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

            expected = {"model": "text-embedding-3-small",
                        "input": [test_content.data], 'metadata': {'user': user, 'bot': bot},
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

        embedding = list(np.random.random(LLMProcessor.__embedding__))
        mock_embedding.side_effect = {'data': [{'embedding': embedding}]}, {'data': [{'embedding': embedding}]}, {
            'data': [{'embedding': embedding}]}
        gpt3 = LLMProcessor(bot)
        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': secret}}):
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
                            'payload': {'country': 'Spain'}}]}
            assert list(aioresponses.requests.values())[3][1].kwargs['json'] == {
                'points': [{'id': test_content_three.vector_id,
                            'vector': embedding,
                            'payload': {'role': 'ds'}}]}

            assert list(aioresponses.requests.values())[4][0].kwargs['json'] == {
                'name': f"{gpt3.bot}_user_details{gpt3.suffix}",
                'vectors': gpt3.vector_config}
            assert list(aioresponses.requests.values())[5][0].kwargs['json'] == {
                'points': [{'id': test_content.vector_id,
                            'vector': embedding,
                            'payload': {'name': 'Nupur'}}]}
            assert response['faq'] == 3

            expected = {"model": "text-embedding-3-small",
                        "input": [json.dumps(test_content.data)], 'metadata': {'user': user, 'bot': bot},
                        "api_key": value,
                        "num_retries": 3}
            print(mock_embedding.call_args)
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
            data={"name": "Ram", "age": "23", "color": "red"},
            content_type="json",
            collection="payload_with_int",
            bot=bot, user=user).save()
        secret = BotSecrets(secret_type=BotSecretType.gpt_key.value, value=value, bot=bot, user=user).save()

        embedding = list(np.random.random(LLMProcessor.__embedding__))
        input = {"name": "Ram", "color": "red"}
        mock_embedding.return_value = {'data': [{'embedding': embedding}]}

        gpt3 = LLMProcessor(bot)
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

        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': secret}}):
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

            expected = {"model": "text-embedding-3-small",
                        "input": [json.dumps(input)], 'metadata': {'user': user, 'bot': bot},
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
        secret = BotSecrets(secret_type=BotSecretType.gpt_key.value, value=value, bot=bot, user=user).save()

        embedding = list(np.random.random(LLMProcessor.__embedding__))
        input = {"name": "Ram", "color": "red"}
        mock_embedding.return_value = {'data': [{'embedding': embedding}]}
        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': secret}}):
            gpt3 = LLMProcessor(bot)

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

            expected = {"model": "text-embedding-3-small",
                        "input": [json.dumps(input)], 'metadata': {'user': user, 'bot': bot},
                        "api_key": value,
                        "num_retries": 3}
            assert not DeepDiff(mock_embedding.call_args[1], expected, ignore_order=True)

    def test_gpt3_faq_embedding_train_failure(self):
        with pytest.raises(AppException, match=f"Bot secret '{BotSecretType.gpt_key.value}' not configured!"):
            LLMProcessor('test_failure')

    @pytest.mark.asyncio
    @mock.patch.object(litellm, "aembedding", autospec=True)
    async def test_gpt3_faq_embedding_train_upsert_error(self, mock_embedding, aioresponses):
        bot = "test_embed_faq_not_exists"
        user = "test"
        value = "nupurk"
        test_content = CognitionData(
            data="Welcome! Are you completely new to programming? If not then we presume you will be looking for information about why and how to get started with Python",
            bot=bot, user=user).save()
        secret = BotSecrets(secret_type=BotSecretType.gpt_key.value, value=value, bot=bot, user=user).save()

        embedding = list(np.random.random(LLMProcessor.__embedding__))

        mock_embedding.return_value = {'data': [{'embedding': embedding}]}

        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': secret}}):
            gpt3 = LLMProcessor(test_content.bot)

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

            expected = {"model": "text-embedding-3-small",
                        "input": [test_content.data], 'metadata': {'user': user, 'bot': bot},
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
        secret = BotSecrets(secret_type=BotSecretType.gpt_key.value, value=value, bot=bot, user=user).save()

        embedding = list(np.random.random(LLMProcessor.__embedding__))

        mock_embedding.return_value = {'data': [{'embedding': embedding}]}
        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': secret}}):
            gpt3 = LLMProcessor(test_content.bot)

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

            expected = {"model": "text-embedding-3-small",
                        "input": [json.dumps(test_content.data)], 'metadata': {'user': user, 'bot': bot},
                        "api_key": value,
                        "num_retries": 3}
            assert not DeepDiff(mock_embedding.call_args[1], expected, ignore_order=True)

    @pytest.mark.asyncio
    @mock.patch.object(litellm, "acompletion", autospec=True)
    @mock.patch.object(litellm, "aembedding", autospec=True)
    async def test_gpt3_faq_embedding_predict(self, mock_embedding, mock_completion, aioresponses):
        embedding = list(np.random.random(LLMProcessor.__embedding__))

        bot = "test_embed_faq_predict"
        user = "test"
        value = "knupur"
        collection = 'python'
        test_content = CognitionData(
            data="Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.",
            collection=collection, bot=bot, user=user).save()
        secret = BotSecrets(secret_type=BotSecretType.gpt_key.value, value=value, bot=bot, user=user).save()

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
        mock_completion_request = {"messages": [
            {'role': 'system',
             'content': 'You are a personal assistant. Answer the question according to the below context'},
            {'role': 'user',
             'content': "Based on below context answer question, if answer not in context check previous logs.\nInstructions on how to use Similarity Prompt:\n['Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.']\nAnswer according to this context.\n \nQ: What kind of language is python? \nA:"}
        ]}
        mock_completion_request.update(hyperparameters)
        mock_embedding.return_value = {'data': [{'embedding': embedding}]}
        mock_completion.return_value = {'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}
        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': secret}}):
            gpt3 = LLMProcessor(test_content.bot)

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

            expected = {"model": "text-embedding-3-small",
                        "input": [query], 'metadata': {'user': user, 'bot': bot},
                        "api_key": value,
                        "num_retries": 3}
            assert not DeepDiff(mock_embedding.call_args[1], expected, ignore_order=True)
            expected = mock_completion_request.copy()
            expected['metadata'] = {'user': user, 'bot': bot}
            expected['api_key'] = value
            expected['num_retries'] = 3
            assert not DeepDiff(mock_completion.call_args[1], expected, ignore_order=True)

    @pytest.mark.asyncio
    @mock.patch.object(litellm, "acompletion", autospec=True)
    @mock.patch.object(litellm, "aembedding", autospec=True)
    async def test_gpt3_faq_embedding_predict_with_default_collection(self, mock_embedding, mock_completion,
                                                                      aioresponses):
        embedding = list(np.random.random(LLMProcessor.__embedding__))

        bot = "test_embed_faq_predict_with_default_collection"
        user = "test"
        value = "knupur"
        collection = 'default'
        test_content = CognitionData(
            data="Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.",
            collection=collection, bot=bot, user=user).save()
        secret = BotSecrets(secret_type=BotSecretType.gpt_key.value, value=value, bot=bot, user=user).save()

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

        mock_completion_request = {"messages": [
            {'role': 'system',
             'content': 'You are a personal assistant. Answer the question according to the below context'},
            {'role': 'user',
             'content': "Based on below context answer question, if answer not in context check previous logs.\nInstructions on how to use Similarity Prompt:\n['Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.']\nAnswer according to this context.\n \nQ: What kind of language is python? \nA:"}
        ]}
        mock_completion_request.update(hyperparameters)
        mock_embedding.return_value = {'data': [{'embedding': embedding}]}
        mock_completion.return_value = {'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}
        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': secret}}):
            gpt3 = LLMProcessor(test_content.bot)

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

            expected = {"model": "text-embedding-3-small",
                        "input": [query], 'metadata': {'user': user, 'bot': bot},
                        "api_key": value,
                        "num_retries": 3}
            assert not DeepDiff(mock_embedding.call_args[1], expected, ignore_order=True)
            expected = mock_completion_request.copy()
            expected['metadata'] = {'user': user, 'bot': bot}
            expected['api_key'] = value
            expected['num_retries'] = 3
            assert not DeepDiff(mock_completion.call_args[1], expected, ignore_order=True)

    @pytest.mark.asyncio
    @mock.patch.object(litellm, "acompletion", autospec=True)
    @mock.patch.object(litellm, "aembedding", autospec=True)
    async def test_gpt3_faq_embedding_predict_with_values(self, mock_embedding, mock_completion, aioresponses):
        embedding = list(np.random.random(LLMProcessor.__embedding__))

        test_content = CognitionData(
            data="Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.",
            collection='python', bot="test_gpt3_faq_embedding_predict_with_values", user="test").save()

        generated_text = "Python is dynamically typed, garbage-collected, high level, general purpose programming."
        query = "What kind of language is python?"
        hyperparameters = Utility.get_default_llm_hyperparameters()
        key = 'test'
        user = "tests"
        BotSecrets(secret_type=BotSecretType.gpt_key.value, value=key, bot=test_content.bot, user=user).save()
        k_faq_action_config = {
            "system_prompt": "You are a personal assistant. Answer the question according to the below context",
            "context_prompt": "Based on below context answer question, if answer not in context check previous logs.",
            "similarity_prompt": [{"top_results": 10, "similarity_threshold": 0.70, 'use_similarity_prompt': True,
                                   'similarity_prompt_name': 'Similarity Prompt',
                                   'similarity_prompt_instructions': 'Answer according to this context.',
                                   'collection': 'python'}],
            "hyperparameters": hyperparameters
        }

        mock_completion_request = {"messages": [
            {"role": "system",
             "content": "You are a personal assistant. Answer the question according to the below context"},
            {'role': 'user',
             'content': "Based on below context answer question, if answer not in context check previous logs.\nInstructions on how to use Similarity Prompt:\n['Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.']\nAnswer according to this context.\n \nQ: What kind of language is python? \nA:"}
        ]}
        mock_completion_request.update(hyperparameters)
        mock_embedding.return_value = {'data': [{'embedding': embedding}]}
        mock_completion.return_value = {'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}

        with mock.patch.dict(Utility.environment, {'vector': {"key": "test", 'db': "http://localhost:6333"}}):
            gpt3 = LLMProcessor(test_content.bot)

            aioresponses.add(
                url=urljoin(Utility.environment['vector']['db'],
                            f"/collections/{gpt3.bot}_{test_content.collection}{gpt3.suffix}/points/search"),
                method="POST",
                payload={'result': [
                    {'id': test_content.vector_id, 'score': 0.80, "payload": {'content': test_content.data}}]}
            )

            response, time_elapsed = await gpt3.predict(query, user=user, **k_faq_action_config)
            assert response['content'] == generated_text
            assert gpt3.logs == [
                {'messages': [{'role': 'system',
                               'content': 'You are a personal assistant. Answer the question according to the below context'},
                              {'role': 'user',
                               'content': "Based on below context answer question, if answer not in context check previous logs.\nInstructions on how to use Similarity Prompt:\n['Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.']\nAnswer according to this context.\n \nQ: What kind of language is python? \nA:"}],
                 'raw_completion_response': {'choices': [{
                     'message': {
                         'content': 'Python is dynamically typed, garbage-collected, high level, general purpose programming.',
                         'role': 'assistant'}}]},
                 'type': 'answer_query',
                 'hyperparameters': {'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-3.5-turbo', 'top_p': 0.0,
                                     'n': 1, 'stop': None, 'presence_penalty': 0.0,
                                     'frequency_penalty': 0.0, 'logit_bias': {}}}]

            assert list(aioresponses.requests.values())[0][0].kwargs['json'] == {'vector': embedding, 'limit': 10,
                                                                                 'with_payload': True,
                                                                                 'score_threshold': 0.70}

            assert isinstance(time_elapsed, float) and time_elapsed > 0.0

            expected = {"model": "text-embedding-3-small",
                        "input": [query], 'metadata': {'user': user, 'bot': gpt3.bot},
                        "api_key": key,
                        "num_retries": 3}
            assert not DeepDiff(mock_embedding.call_args[1], expected, ignore_order=True)
            expected = mock_completion_request.copy()
            expected['metadata'] = {'user': user, 'bot': gpt3.bot}
            expected['api_key'] = key
            expected['num_retries'] = 3
            assert not DeepDiff(mock_completion.call_args[1], expected, ignore_order=True)

    @pytest.mark.asyncio
    @mock.patch.object(litellm, "acompletion", autospec=True)
    @mock.patch.object(litellm, "aembedding", autospec=True)
    async def test_gpt3_faq_embedding_predict_with_values_and_stream(self, mock_embedding, mock_completion,
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
        BotSecrets(secret_type=BotSecretType.gpt_key.value, value=key, bot=test_content.bot, user=user).save()
        k_faq_action_config = {
            "system_prompt": "You are a personal assistant. Answer the question according to the below context",
            "context_prompt": "Based on below context answer question, if answer not in context check previous logs.",
            "similarity_prompt": [{"top_results": 10, "similarity_threshold": 0.70, 'use_similarity_prompt': True,
                                   'similarity_prompt_name': 'Similarity Prompt',
                                   'similarity_prompt_instructions': 'Answer according to this context.',
                                   'collection': 'python'}],
            "hyperparameters": hyperparameters
        }

        mock_completion_request = {"messages": [
            {"role": "system",
             "content": "You are a personal assistant. Answer the question according to the below context"},
            {'role': 'user',
             'content': "Based on below context answer question, if answer not in context check previous logs.\nInstructions on how to use Similarity Prompt:\n['Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.']\nAnswer according to this context.\n \nQ: What kind of language is python? \nA:"}
        ]}
        mock_completion_request.update(hyperparameters)
        mock_embedding.return_value = {'data': [{'embedding': embedding}]}
        mock_completion.side_effect = [{'choices': [
            {'delta': {'role': 'assistant', 'content': generated_text[0:29]}, 'finish_reason': None, 'index': 0}]},
                                       {'choices': [{'delta': {'role': 'assistant', 'content': generated_text[29:60]},
                                                     'finish_reason': None, 'index': 0}]},
                                       {'choices': [{'delta': {'role': 'assistant', 'content': generated_text[60:]},
                                                     'finish_reason': 'stop', 'index': 0}]}
                                       ]

        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': key}}):
            gpt3 = LLMProcessor(test_content.bot)

            aioresponses.add(
                url=urljoin(Utility.environment['vector']['db'],
                            f"/collections/{gpt3.bot}_{test_content.collection}{gpt3.suffix}/points/search"),
                method="POST",
                payload={'result': [
                    {'id': test_content.vector_id, 'score': 0.80, "payload": {'content': test_content.data}}]}
            )

            response, time_elapsed = await gpt3.predict(query, user=user, **k_faq_action_config)
            assert response['content'] == "Python is dynamically typed, "
            assert gpt3.logs == [
                {'messages': [{'role': 'system',
                               'content': 'You are a personal assistant. Answer the question according to the below context'},
                              {'role': 'user',
                               'content': "Based on below context answer question, if answer not in context check previous logs.\nInstructions on how to use Similarity Prompt:\n['Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.']\nAnswer according to this context.\n \nQ: What kind of language is python? \nA:"}],
                 'raw_completion_response': {'choices': [
                     {'delta': {'role': 'assistant', 'content': generated_text[0:29]}, 'finish_reason': None,
                      'index': 0}]},
                 'type': 'answer_query',
                 'hyperparameters': {'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-3.5-turbo', 'top_p': 0.0,
                                     'n': 1, 'stream': True, 'stop': None, 'presence_penalty': 0.0,
                                     'frequency_penalty': 0.0, 'logit_bias': {}}}]

            assert list(aioresponses.requests.values())[0][0].kwargs['json'] == {'vector': embedding, 'limit': 10,
                                                                                 'with_payload': True,
                                                                                 'score_threshold': 0.70}

            assert isinstance(time_elapsed, float) and time_elapsed > 0.0

            expected = {"model": "text-embedding-3-small",
                        "input": [query], 'metadata': {'user': user, 'bot': gpt3.bot},
                        "api_key": key,
                        "num_retries": 3}
            assert not DeepDiff(mock_embedding.call_args[1], expected, ignore_order=True)
            expected = mock_completion_request.copy()
            expected['metadata'] = {'user': user, 'bot': gpt3.bot}
            expected['api_key'] = key
            expected['num_retries'] = 3
            assert not DeepDiff(mock_completion.call_args[1], expected, ignore_order=True)

    @pytest.mark.asyncio
    @mock.patch.object(litellm, "acompletion", autospec=True)
    @mock.patch.object(litellm, "aembedding", autospec=True)
    async def test_gpt3_faq_embedding_predict_with_values_with_instructions(self,
                                                                            mock_embedding,
                                                                            mock_completion,
                                                                            aioresponses):
        embedding = list(np.random.random(LLMProcessor.__embedding__))
        user = "test"
        bot = "payload_with_instruction"
        key = 'test'
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

        BotSecrets(secret_type=BotSecretType.gpt_key.value, value=key, bot=bot, user=user).save()

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

        mock_completion_request = {"messages": [
            {'role': 'system',
             'content': 'You are a personal assistant. Answer the question according to the below context'},
            {'role': 'user',
             'content': "Based on below context answer question, if answer not in context check previous logs.\nInstructions on how to use Similarity Prompt:\n[{'name': 'Fahad', 'city': 'Mumbai'}, {'name': 'Hitesh', 'city': 'Mumbai'}]\nAnswer according to this context.\n \nAnswer in a short way.\nKeep it simple. \nQ: List all the user lives in mumbai city \nA:"}
        ]}
        mock_completion_request.update(hyperparameters)
        mock_embedding.return_value = {'data': [{'embedding': embedding}]}
        mock_completion.return_value = {'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}

        gpt3 = LLMProcessor(bot)
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
        assert gpt3.logs == [{'messages': [{'role': 'system',
                                            'content': 'You are a personal assistant. Answer the question according to the below context'},
                                           {'role': 'user',
                                            'content': "Based on below context answer question, if answer not in context check previous logs.\nInstructions on how to use Similarity Prompt:\n[{'name': 'Fahad', 'city': 'Mumbai'}, {'name': 'Hitesh', 'city': 'Mumbai'}]\nAnswer according to this context.\n \nAnswer in a short way.\nKeep it simple. \nQ: List all the user lives in mumbai city \nA:"}],
                              'raw_completion_response': {'choices': [{'message': {
                                  'content': 'Hitesh and Fahad lives in mumbai city.', 'role': 'assistant'}}]},
                              'type': 'answer_query',
                              'hyperparameters': {'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-3.5-turbo',
                                                  'top_p': 0.0, 'n': 1, 'stop': None,
                                                  'presence_penalty': 0.0, 'frequency_penalty': 0.0, 'logit_bias': {}}}]

        assert list(aioresponses.requests.values())[0][0].kwargs['json'] == {'vector': embedding, 'limit': 10,
                                                                             'with_payload': True,
                                                                             'score_threshold': 0.70}

        assert isinstance(time_elapsed, float) and time_elapsed > 0.0

        expected = {"model": "text-embedding-3-small",
                    "input": [query], 'metadata': {'user': user, 'bot': bot},
                    "api_key": key,
                    "num_retries": 3}
        assert not DeepDiff(mock_embedding.call_args[1], expected, ignore_order=True)
        expected = mock_completion_request.copy()
        expected['metadata'] = {'user': user, 'bot': bot}
        expected['api_key'] = key
        expected['num_retries'] = 3
        assert not DeepDiff(mock_completion.call_args[1], expected, ignore_order=True)

    @pytest.mark.asyncio
    @mock.patch.object(litellm, "acompletion", autospec=True)
    @mock.patch.object(litellm, "aembedding", autospec=True)
    async def test_gpt3_faq_embedding_predict_completion_connection_error(self, mock_embedding, mock_completion,
                                                                          aioresponses):
        embedding = list(np.random.random(LLMProcessor.__embedding__))
        bot = "test_gpt3_faq_embedding_predict_completion_connection_error"
        user = 'test'
        key = "test"

        test_content = CognitionData(
            data="Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.",
            collection='python', bot=bot, user=user).save()
        BotSecrets(secret_type=BotSecretType.gpt_key.value, value=key, bot=test_content.bot, user=user).save()

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

        def __mock_connection_error(*args, **kwargs):
            raise Exception("Connection reset by peer!")

        mock_embedding.return_value = {'data': [{'embedding': embedding}]}
        mock_completion.side_effect = __mock_connection_error

        gpt3 = LLMProcessor(test_content.bot)

        aioresponses.add(
            url=urljoin(Utility.environment['vector']['db'],
                        f"/collections/{gpt3.bot}_{test_content.collection}{gpt3.suffix}/points/search"),
            method="POST",
            payload={'result': [
                {'id': test_content.vector_id, 'score': 0.80, "payload": {'content': test_content.data}}]}
        )

        response, time_elapsed = await gpt3.predict(query, user=user, **k_faq_action_config)
        assert response == {'exception': "Connection reset by peer!", 'is_failure': True, "content": None}

        assert gpt3.logs == [{'error': 'Retrieving chat completion for the provided query. Connection reset by peer!'}]

        assert list(aioresponses.requests.values())[0][0].kwargs['json'] == {'vector': embedding, 'limit': 10,
                                                                             'with_payload': True,
                                                                             'score_threshold': 0.70}
        assert isinstance(time_elapsed, float) and time_elapsed > 0.0

        expected = {"model": "text-embedding-3-small",
                    "input": [query], 'metadata': {'user': user, 'bot': bot},
                    "api_key": key,
                    "num_retries": 3}
        assert not DeepDiff(mock_embedding.call_args[1], expected, ignore_order=True)
        expected = {'messages': [{'role': 'system',
                                  'content': 'You are a personal assistant. Answer the question according to the below context'},
                                 {'role': 'user',
                                  'content': "Based on below context answer question, if answer not in context check previous logs.\nInstructions on how to use Similarity Prompt:\n['Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.']\nAnswer according to this context.\n \nQ: What kind of language is python? \nA:"}],
                    'metadata': {'user': 'test', 'bot': 'test_gpt3_faq_embedding_predict_completion_connection_error'},
                    'api_key': 'test', 'num_retries': 3, 'temperature': 0.0, 'max_tokens': 300,
                    'model': 'gpt-3.5-turbo', 'top_p': 0.0, 'n': 1, 'stop': None,
                    'presence_penalty': 0.0, 'frequency_penalty': 0.0, 'logit_bias': {}}
        assert not DeepDiff(mock_completion.call_args[1], expected, ignore_order=True)

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
        BotSecrets(secret_type=BotSecretType.gpt_key.value, value=key, bot=test_content.bot, user=user).save()

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

        mock_embedding.return_value = {'data': [{'embedding': embedding}]}
        mock_llm_request.side_effect = ClientConnectionError()

        gpt3 = LLMProcessor(test_content.bot)

        response, time_elapsed = await gpt3.predict(query, user="test", **k_faq_action_config)
        assert response == {'exception': 'Failed to connect to service: localhost', 'is_failure': True, "content": None}

        assert gpt3.logs == [
            {'error': 'Retrieving chat completion for the provided query. Failed to connect to service: localhost'}]
        assert isinstance(time_elapsed, float) and time_elapsed > 0.0

        expected = {"model": "text-embedding-3-small",
                    "input": [query], 'metadata': {'user': user, 'bot': bot},
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
        BotSecrets(secret_type=BotSecretType.gpt_key.value, value=key, bot=test_content.bot, user=user).save()

        hyperparameters = Utility.get_default_llm_hyperparameters()
        generated_text = "Python is dynamically typed, garbage-collected, high level, general purpose programming."
        query = "What kind of language is python?"

        k_faq_action_config = {
            "system_prompt": "You are a personal assistant. Answer the question according to the below context",
            "context_prompt": "Based on below context answer question, if answer not in context check previous logs.",
            "hyperparameters": hyperparameters
        }
        mock_embedding.side_effect = [Exception("Connection reset by peer!"), {'data': [{'embedding': embedding}]}]

        gpt3 = LLMProcessor(test_content.bot)
        mock_embedding.side_effect = [Exception("Connection reset by peer!"), embedding]

        response, time_elapsed = await gpt3.predict(query, user="test", **k_faq_action_config)
        assert response == {'exception': 'Connection reset by peer!', 'is_failure': True, "content": None}

        assert gpt3.logs == [{'error': 'Creating a new embedding for the provided query. Connection reset by peer!'}]
        assert isinstance(time_elapsed, float) and time_elapsed > 0.0

        expected = {"model": "text-embedding-3-small",
                    "input": [query], 'metadata': {'user': user, 'bot': bot},
                    "api_key": key,
                    "num_retries": 3}
        assert not DeepDiff(mock_embedding.call_args[1], expected, ignore_order=True)

    @pytest.mark.asyncio
    @mock.patch.object(litellm, "acompletion", autospec=True)
    @mock.patch.object(litellm, "aembedding", autospec=True)
    async def test_gpt3_faq_embedding_predict_with_previous_bot_responses(self, mock_embedding, mock_completion,
                                                                          aioresponses):
        embedding = list(np.random.random(LLMProcessor.__embedding__))

        bot = "test_gpt3_faq_embedding_predict_with_previous_bot_responses"
        user = "test"
        key = "test"
        hyperparameters = Utility.get_default_llm_hyperparameters()
        test_content = CognitionData(
            data="Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.",
            collection='python', bot=bot, user=user).save()
        BotSecrets(secret_type=BotSecretType.gpt_key.value, value=key, bot=test_content.bot, user=user).save()

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

        mock_completion_request = {"messages": [
            {'role': 'system', 'content': 'You are a personal assistant. Answer question based on the context below'},
            {'role': 'user', 'content': 'hello'},
            {'role': 'assistant', 'content': 'how are you'},
            {'role': 'user',
             'content': "Answer question based on the context below, if answer is not in the context go check previous logs.\nInstructions on how to use Similarity Prompt:\n['Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.']\nAnswer according to this context.\n \nQ: What kind of language is python? \nA:"}
        ]}
        mock_completion_request.update(hyperparameters)
        mock_embedding.return_value = {'data': [{'embedding': embedding}]}
        mock_completion.return_value = {'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}

        gpt3 = LLMProcessor(test_content.bot)

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

        expected = {"model": "text-embedding-3-small",
                    "input": [query], 'metadata': {'user': user, 'bot': bot},
                    "api_key": key,
                    "num_retries": 3}
        assert not DeepDiff(mock_embedding.call_args[1], expected, ignore_order=True)
        expected = mock_completion_request.copy()
        expected['metadata'] = {'user': user, 'bot': bot}
        expected['api_key'] = key
        expected['num_retries'] = 3
        assert not DeepDiff(mock_completion.call_args[1], expected, ignore_order=True)

    @pytest.mark.asyncio
    @mock.patch.object(litellm, "acompletion", autospec=True)
    @mock.patch.object(litellm, "aembedding", autospec=True)
    async def test_gpt3_faq_embedding_predict_with_query_prompt(self, mock_embedding, mock_completion, aioresponses):
        embedding = list(np.random.random(LLMProcessor.__embedding__))

        bot = "test_gpt3_faq_embedding_predict_with_query_prompt"
        user = "test"
        key = "test"
        test_content = CognitionData(
            data="Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.",
            collection='python', bot=bot, user=user).save()
        BotSecrets(secret_type=BotSecretType.gpt_key.value, value=key, bot=test_content.bot, user=user).save()

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

        mock_completion_request = {"messages": [
            {"role": "system",
             "content": DEFAULT_SYSTEM_PROMPT},
            {'role': 'user',
             'content': "Answer question based on the context below, if answer is not in the context go check previous logs.\nInstructions on how to use Similarity Prompt:\n['Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.']\nAnswer according to this context.\n \nQ: Explain python is called high level programming language in laymen terms? \nA:"}
        ]}
        mock_rephrase_request.update(hyperparameters)
        mock_completion_request.update(hyperparameters)

        mock_embedding.return_value = {'data': [{'embedding': embedding}]}
        mock_completion.side_effect = {'choices': [{'message': {'content': rephrased_query, 'role': 'assistant'}}]}, {
            'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}

        gpt3 = LLMProcessor(test_content.bot)

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

        expected = {"model": "text-embedding-3-small",
                    "input": [query], 'metadata': {'user': user, 'bot': bot},
                    "api_key": key,
                    "num_retries": 3}
        assert not DeepDiff(mock_embedding.call_args[1], expected, ignore_order=True)
        expected = mock_completion_request.copy()
        expected['metadata'] = {'user': user, 'bot': bot}
        expected['api_key'] = key
        expected['num_retries'] = 3
        assert not DeepDiff(mock_completion.call_args[1], expected, ignore_order=True)

    @pytest.mark.asyncio
    async def test_llm_logging(self):
        from kairon.shared.llm.logger import LiteLLMLogger
        bot = "test_llm_logging"
        user = "test"
        litellm.callbacks = [LiteLLMLogger()]

        result = await litellm.acompletion(messages=["Hi"],
                                           model="gpt-3.5-turbo",
                                           mock_response="Hi, How may i help you?",
                                           metadata={'user': user, 'bot': bot})
        assert result

        result = litellm.completion(messages=["Hi"],
                                    model="gpt-3.5-turbo",
                                    mock_response="Hi, How may i help you?",
                                    metadata={'user': user, 'bot': bot})
        assert result

        result = litellm.completion(messages=["Hi"],
                                    model="gpt-3.5-turbo",
                                    mock_response="Hi, How may i help you?",
                                    stream=True,
                                    metadata={'user': user, 'bot': bot})
        for chunk in result:
            print(chunk["choices"][0]["delta"]["content"])
            assert chunk["choices"][0]["delta"]["content"]

        result = await litellm.acompletion(messages=["Hi"],
                                           model="gpt-3.5-turbo",
                                           mock_response="Hi, How may i help you?",
                                           stream=True,
                                           metadata={'user': user, 'bot': bot})
        async for chunk in result:
            print(chunk["choices"][0]["delta"]["content"])
            assert chunk["choices"][0]["delta"]["content"]

        with pytest.raises(Exception) as e:
            await litellm.acompletion(messages=["Hi"],
                                       model="gpt-3.5-turbo",
                                       mock_response=Exception("Authentication error"),
                                       metadata={'user': user, 'bot': bot})

            assert str(e) == "Authentication error"

        with pytest.raises(Exception) as e:
            litellm.completion(messages=["Hi"],
                                model="gpt-3.5-turbo",
                                mock_response=Exception("Authentication error"),
                                metadata={'user': user, 'bot': bot})

            assert str(e) == "Authentication error"

        with pytest.raises(Exception) as e:
            await litellm.acompletion(messages=["Hi"],
                                       model="gpt-3.5-turbo",
                                       mock_response=Exception("Authentication error"),
                                       stream=True,
                                       metadata={'user': user, 'bot': bot})

            assert str(e) == "Authentication error"