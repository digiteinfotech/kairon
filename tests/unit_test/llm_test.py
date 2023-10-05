import json
import os
from urllib.parse import urljoin

import mock
import numpy as np
import pytest
import responses
from mongoengine import connect

from kairon.exceptions import AppException
from kairon.shared.admin.constants import BotSecretType
from kairon.shared.admin.data_objects import BotSecrets
from kairon.shared.data.constant import DEFAULT_SYSTEM_PROMPT
from kairon.shared.data.data_objects import CognitionData, LLMSettings
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
            inst = LLMFactory.get_instance( "faq")("test", LLMSettings(provider="openai").to_mongo().to_dict())
            assert isinstance(inst, GPT3FAQEmbedding)
            assert inst.db_url == Utility.environment['vector']['db']
            assert inst.headers == {'api-key': Utility.environment['vector']['key']}

    @responses.activate
    def test_gpt3_faq_embedding_train(self):
        bot = "test_embed_faq"
        user = "test"
        value = "nupurkhare"
        test_content = CognitionData(
            data="Welcome! Are you completely new to programming? If not then we presume you will be looking for information about why and how to get started with Python",
            bot=bot, user=user).save()
        secret = BotSecrets(secret_type=BotSecretType.gpt_key.value, value=value, bot=bot, user=user).save()

        embedding = list(np.random.random(GPT3FAQEmbedding.__embedding__))
        request_header = {"Authorization": "Bearer nupurkhare"}

        responses.add(
            url="https://api.openai.com/v1/embeddings",
            method="POST",
            status=200,
            match=[
                responses.matchers.json_params_matcher({"model": "text-embedding-ada-002", "input": test_content.data}),
                responses.matchers.header_matcher(request_header)],
            json={'data': [{'embedding': embedding}]}
        )

        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': secret}}):
            gpt3 = GPT3FAQEmbedding(test_content.bot, LLMSettings(provider="openai").to_mongo().to_dict())

            responses.add(
                "DELETE",
                urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.cached_resp_suffix}"),
                adding_headers={}
            )

            responses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.cached_resp_suffix}"),
                method="PUT",
                adding_headers={},
                match=[responses.matchers.json_params_matcher(
                    {'name': gpt3.bot + gpt3.cached_resp_suffix, 'vectors': gpt3.vector_config})],
                status=200
            )

            responses.add(
                "DELETE",
                urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.suffix}"),
                adding_headers={}
            )

            responses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.suffix}"),
                method="PUT",
                adding_headers={},
                match=[responses.matchers.json_params_matcher({'name': gpt3.bot + gpt3.suffix, 'vectors': gpt3.vector_config})],
                status=200
            )

            responses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.suffix}/points"),
                method="PUT",
                adding_headers={},
                match=[responses.matchers.json_params_matcher({'points': [{'id': test_content.vector_id,
                                                                  'vector': embedding,
                                                                  'payload': {'content': test_content.data,
                                                                              'collection_name': 'test_embed_faq_faq_embd'}
                                                                  }]})],
                json={"result": {"operation_id": 0, "status": "acknowledged"}, "status": "ok", "time": 0.003612634}
            )

            response = gpt3.train()
            assert response['faq'] == 1

    @responses.activate
    def test_gpt3_faq_embedding_train_payload_text(self):
        bot = "test_embed_faq_text"
        user = "test"
        value = "nupurkhare"
        test_content = CognitionData(
            data={"name": "Nupur", "city": "Pune"},
            content_type="json",
            metadata=[{"column_name": "name", "data_type": "str", "enable_search": True, "create_embeddings": True},
            {"column_name": "city", "data_type": "str", "enable_search": False, "create_embeddings": True}],
            collection="User_details",
            bot=bot, user=user).save()
        test_content_two = CognitionData(
            data={"country": "Spain", "lang": "spanish"},
            content_type="json",
            metadata=[{"column_name": "country", "data_type": "str", "enable_search": True, "create_embeddings": True},
                      {"column_name": "lang", "data_type": "str", "enable_search": False, "create_embeddings": True}],
            collection="Country_details",
            bot=bot, user=user).save()
        test_content_three = CognitionData(
            data={"role": "ds", "lang": "spanish"},
            content_type="json",
            metadata=[{"column_name": "role", "data_type": "str", "enable_search": True, "create_embeddings": True},
                      {"column_name": "lang", "data_type": "str", "enable_search": False, "create_embeddings": True}],
            collection="Country_details",
            bot=bot, user=user).save()
        secret = BotSecrets(secret_type=BotSecretType.gpt_key.value, value=value, bot=bot, user=user).save()

        embedding = list(np.random.random(GPT3FAQEmbedding.__embedding__))
        request_header = {"Authorization": "Bearer nupurkhare"}

        responses.add(
            url="https://api.openai.com/v1/embeddings",
            method="POST",
            status=200,
            match=[
                responses.matchers.json_params_matcher({"model": "text-embedding-ada-002", "input": json.dumps(test_content.data)}),
                responses.matchers.header_matcher(request_header)],
            json={'data': [{'embedding': embedding}]}
        )

        responses.add(
            url="https://api.openai.com/v1/embeddings",
            method="POST",
            status=200,
            match=[
                responses.matchers.json_params_matcher(
                    {"model": "text-embedding-ada-002", "input": json.dumps(test_content_two.data)}),
                responses.matchers.header_matcher(request_header)],
            json={'data': [{'embedding': embedding}]}
        )

        responses.add(
            url="https://api.openai.com/v1/embeddings",
            method="POST",
            status=200,
            match=[
                responses.matchers.json_params_matcher(
                    {"model": "text-embedding-ada-002", "input": json.dumps(test_content_three.data)}),
                responses.matchers.header_matcher(request_header)],
            json={'data': [{'embedding': embedding}]}
        )

        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': secret}}):
            gpt3 = GPT3FAQEmbedding(test_content.bot, LLMSettings(provider="openai").to_mongo().to_dict())

            responses.add(
                "DELETE",
                urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.cached_resp_suffix}"),
                adding_headers={}
            )

            responses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.cached_resp_suffix}"),
                method="PUT",
                adding_headers={},
                match=[responses.matchers.json_params_matcher(
                    {'name': gpt3.bot + gpt3.cached_resp_suffix, 'vectors': gpt3.vector_config})],
                status=200
            )

            responses.add(
                "DELETE",
                urljoin(Utility.environment['vector']['db'], f"/collections/test_embed_faq_text_User_details_faq_embd"),
                adding_headers={}
            )

            responses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/test_embed_faq_text_User_details_faq_embd"),
                method="PUT",
                adding_headers={},
                match=[responses.matchers.json_params_matcher(
                    {'name': 'test_embed_faq_text_User_details_faq_embd', 'vectors': gpt3.vector_config})],
                status=200
            )

            responses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/test_embed_faq_text_User_details_faq_embd/points"),
                method="PUT",
                adding_headers={},
                match=[responses.matchers.json_params_matcher({'points': [{'id': test_content.vector_id,
                                                                           'vector': embedding,
                                                                           'payload': {'name': 'Nupur',
                                                                                       'collection_name': 'test_embed_faq_text_User_details_faq_embd'}
                                                                           }]})],
                json={"result": {"operation_id": 0, "status": "acknowledged"}, "status": "ok", "time": 0.003612634}
            )

            responses.add(
                "DELETE",
                urljoin(Utility.environment['vector']['db'], f"/collections/test_embed_faq_text_Country_details_faq_embd"),
                adding_headers={}
            )

            responses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/test_embed_faq_text_Country_details_faq_embd"),
                method="PUT",
                adding_headers={},
                match=[responses.matchers.json_params_matcher(
                    {'name': 'test_embed_faq_text_Country_details_faq_embd', 'vectors': gpt3.vector_config})],
                status=200
            )

            responses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/test_embed_faq_text_Country_details_faq_embd/points"),
                method="PUT",
                adding_headers={},
                match=[responses.matchers.json_params_matcher({'points': [{'id': test_content_two.vector_id,
                                                                           'vector': embedding,
                                                                           'payload': {'collection_name': 'test_embed_faq_text_Country_details_faq_embd',
                                                                                       'country': 'Spain'}
                                                                           }]})],
                json={"result": {"operation_id": 0, "status": "acknowledged"}, "status": "ok", "time": 0.003612634}
            )

            responses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/test_embed_faq_text_Country_details_faq_embd/points"),
                method="PUT",
                adding_headers={},
                match=[responses.matchers.json_params_matcher({'points': [{'id': test_content_three.vector_id,
                                                                           'vector': embedding,
                                                                           'payload': {'collection_name': 'test_embed_faq_text_Country_details_faq_embd',
                                                                                       'role': 'ds'}
                                                                           }]})],
                json={"result": {"operation_id": 0, "status": "acknowledged"}, "status": "ok", "time": 0.003612634}
            )

            response = gpt3.train()

            assert response['faq'] == 3

    @responses.activate
    def test_gpt3_faq_embedding_train_payload_with_int(self):
        bot = "test_embed_faq_json"
        user = "test"
        value = "nupurkhare"
        test_content = CognitionData(
            data={"name": "Ram", "age": "23", "color": "red"},
            content_type="json",
            metadata=[{"column_name": "name", "data_type": "str", "enable_search": True, "create_embeddings": True},
            {"column_name": "age", "data_type": "int", "enable_search": True, "create_embeddings": False},
            {"column_name": "color", "data_type": "str", "enable_search": True, "create_embeddings": True}],
            bot=bot, user=user).save()
        secret = BotSecrets(secret_type=BotSecretType.gpt_key.value, value=value, bot=bot, user=user).save()

        embedding = list(np.random.random(GPT3FAQEmbedding.__embedding__))
        request_header = {"Authorization": "Bearer nupurkhare"}
        input = {"name": "Ram", "color": "red"}
        responses.add(
            url="https://api.openai.com/v1/embeddings",
            method="POST",
            status=200,
            match=[
                responses.matchers.json_params_matcher({"model": "text-embedding-ada-002", "input": json.dumps(input)}),
                responses.matchers.header_matcher(request_header)],
            json={'data': [{'embedding': embedding}]}
        )

        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': secret}}):
            gpt3 = GPT3FAQEmbedding(test_content.bot, LLMSettings(provider="openai").to_mongo().to_dict())

            responses.add(
                "DELETE",
                urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.cached_resp_suffix}"),
                adding_headers={}
            )

            responses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.cached_resp_suffix}"),
                method="PUT",
                adding_headers={},
                match=[responses.matchers.json_params_matcher(
                    {'name': gpt3.bot + gpt3.cached_resp_suffix, 'vectors': gpt3.vector_config})],
                status=200
            )

            responses.add(
                "DELETE",
                urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.suffix}"),
                adding_headers={}
            )

            responses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.suffix}"),
                method="PUT",
                adding_headers={},
                match=[responses.matchers.json_params_matcher(
                    {'name': gpt3.bot + gpt3.suffix, 'vectors': gpt3.vector_config})],
                status=200
            )

            responses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.suffix}/points"),
                method="PUT",
                adding_headers={},
                match=[responses.matchers.json_params_matcher({'points': [{'id': test_content.vector_id,
                                                                           'vector': embedding,
                                                                           'payload': {'name': 'Ram', 'age': 23, 'color': 'red',
                                                                                       'collection_name': 'test_embed_faq_json_faq_embd'}
                                                                           }]})],
                json={"result": {"operation_id": 0, "status": "acknowledged"}, "status": "ok", "time": 0.003612634}
            )

            response = gpt3.train()

            assert response['faq'] == 1

    @responses.activate
    def test_gpt3_faq_embedding_train_int(self):
        bot = "test_embed_faq_int"
        user = "test"
        value = "nupurkhare"
        test_content = CognitionData(
            data={"name": "Ram", "age": 23, "color": "red"},
            content_type="json",
            metadata=[{"column_name": "name", "data_type": "str", "enable_search": True, "create_embeddings": True},
                      {"column_name": "age", "data_type": "int", "enable_search": True, "create_embeddings": False},
                      {"column_name": "color", "data_type": "str", "enable_search": True, "create_embeddings": True}],
            bot=bot, user=user).save()
        secret = BotSecrets(secret_type=BotSecretType.gpt_key.value, value=value, bot=bot, user=user).save()

        embedding = list(np.random.random(GPT3FAQEmbedding.__embedding__))
        request_header = {"Authorization": "Bearer nupurkhare"}
        input = {"name": "Ram", "color": "red"}
        responses.add(
            url="https://api.openai.com/v1/embeddings",
            method="POST",
            status=200,
            match=[
                responses.matchers.json_params_matcher({"model": "text-embedding-ada-002", "input": json.dumps(input)}),
                responses.matchers.header_matcher(request_header)],
            json={'data': [{'embedding': embedding}]}
        )

        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': secret}}):
            gpt3 = GPT3FAQEmbedding(test_content.bot, LLMSettings(provider="openai").to_mongo().to_dict())

            responses.add(
                "DELETE",
                urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.cached_resp_suffix}"),
                adding_headers={}
            )

            responses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.cached_resp_suffix}"),
                method="PUT",
                adding_headers={},
                match=[responses.matchers.json_params_matcher(
                    {'name': gpt3.bot + gpt3.cached_resp_suffix, 'vectors': gpt3.vector_config})],
                status=200
            )

            responses.add(
                "DELETE",
                urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.suffix}"),
                adding_headers={}
            )

            responses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.suffix}"),
                method="PUT",
                adding_headers={},
                match=[responses.matchers.json_params_matcher(
                    {'name': gpt3.bot + gpt3.suffix, 'vectors': gpt3.vector_config})],
                status=200
            )

            responses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.suffix}/points"),
                method="PUT",
                adding_headers={},
                match=[responses.matchers.json_params_matcher({'points': [{'id': test_content.vector_id,
                                                                           'vector': embedding,
                                                                           'payload': {'age': 23, 'collection_name': 'test_embed_faq_int_faq_embd', 'color': 'red', 'name': 'Ram'}
                                                                           }]})],
                json={"result": {"operation_id": 0, "status": "acknowledged"}, "status": "ok", "time": 0.003612634}
            )

            response = gpt3.train()

            assert response['faq'] == 1

    @responses.activate
    def test_gpt3_faq_embedding_train_payload_json_no_metadata(self):
        bot = "test_embed_faq_json_no_metadata"
        user = "test"
        value = "nupurkhare"
        test_content = CognitionData(
            data={"name": "Nupur", "age": 25, "city": "Bengaluru"},
            content_type="json",
            metadata=[],
            bot=bot, user=user).save()
        secret = BotSecrets(secret_type=BotSecretType.gpt_key.value, value=value, bot=bot, user=user).save()

        embedding = list(np.random.random(GPT3FAQEmbedding.__embedding__))
        request_header = {"Authorization": "Bearer nupurkhare"}

        responses.add(
            url="https://api.openai.com/v1/embeddings",
            method="POST",
            status=200,
            match=[
                responses.matchers.json_params_matcher({"model": "text-embedding-ada-002", "input": json.dumps(test_content.data)}),
                responses.matchers.header_matcher(request_header)],
            json={'data': [{'embedding': embedding}]}
        )

        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': secret}}):
            gpt3 = GPT3FAQEmbedding(test_content.bot, LLMSettings(provider="openai").to_mongo().to_dict())

            responses.add(
                "DELETE",
                urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.cached_resp_suffix}"),
                adding_headers={}
            )

            responses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.cached_resp_suffix}"),
                method="PUT",
                adding_headers={},
                match=[responses.matchers.json_params_matcher(
                    {'name': gpt3.bot + gpt3.cached_resp_suffix, 'vectors': gpt3.vector_config})],
                status=200
            )

            responses.add(
                "DELETE",
                urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.suffix}"),
                adding_headers={}
            )

            responses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.suffix}"),
                method="PUT",
                adding_headers={},
                match=[responses.matchers.json_params_matcher(
                    {'name': gpt3.bot + gpt3.suffix, 'vectors': gpt3.vector_config})],
                status=200
            )

            responses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.suffix}/points"),
                method="PUT",
                adding_headers={},
                match=[responses.matchers.json_params_matcher({'points': [{'id': test_content.vector_id,
                                                                           'vector': embedding,
                                                                           'payload': {'age': 25, 'name': 'Nupur',
                                                                                       'collection_name': 'test_embed_faq_json_no_metadata_faq_embd',
                                                                                       'city': "Bengaluru"}
                                                                           }]})],
                json={"result": {"operation_id": 0, "status": "acknowledged"}, "status": "ok", "time": 0.003612634}
            )

            response = gpt3.train()

            assert response['faq'] == 1

    def test_gpt3_faq_embedding_train_failure(self):
        with pytest.raises(AppException, match=f"Bot secret '{BotSecretType.gpt_key.value}' not configured!"):
            GPT3FAQEmbedding('test_failure', LLMSettings(provider="openai").to_mongo().to_dict())

    @responses.activate
    def test_gpt3_faq_embedding_train_upsert_error(self):
        bot = "test_embed_faq_not_exists"
        user = "test"
        value = "nupurk"
        test_content = CognitionData(
            data="Welcome! Are you completely new to programming? If not then we presume you will be looking for information about why and how to get started with Python",
            bot=bot, user=user).save()
        secret = BotSecrets(secret_type=BotSecretType.gpt_key.value, value=value, bot=bot, user=user).save()

        embedding = list(np.random.random(GPT3FAQEmbedding.__embedding__))

        request_header = {"Authorization": "Bearer nupurk"}

        responses.add(
            url="https://api.openai.com/v1/embeddings",
            method="POST",
            status=200,
            match=[responses.matchers.json_params_matcher({"model": "text-embedding-ada-002", "input": test_content.data}),
                   responses.matchers.header_matcher(request_header)],
            json={'data': [{'embedding': embedding}]}
        )

        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': secret}}):
            gpt3 = GPT3FAQEmbedding(test_content.bot, LLMSettings(provider="openai").to_mongo().to_dict())

            responses.add(
                "DELETE",
                urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.cached_resp_suffix}"),
                adding_headers={}
            )

            responses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.cached_resp_suffix}"),
                method="PUT",
                adding_headers={},
                match=[responses.matchers.json_params_matcher(
                    {'name': gpt3.bot + gpt3.cached_resp_suffix, 'vectors': gpt3.vector_config})],
                status=200
            )

            responses.add(
                "DELETE",
                urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.suffix}"),
                adding_headers={}
            )

            responses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.suffix}"),
                method="PUT",
                adding_headers={},
                match=[responses.matchers.json_params_matcher({'name': gpt3.bot + gpt3.suffix, 'vectors': gpt3.vector_config})],
                status=200
            )

            responses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.suffix}/points"),
                method="PUT",
                adding_headers={},
                match=[responses.matchers.json_params_matcher({'points': [{'id': test_content.vector_id,
                                                                  'vector': embedding,
                                                                  'payload': {'content': test_content.data,
                                                                              'collection_name': 'test_embed_faq_not_exists_faq_embd'}
                                                                  }]})],
                json={"result": None,
                      'status': {'error': 'Json deserialize error: missing field `vectors` at line 1 column 34779'},
                      "time": 0.003612634}
            )

            with pytest.raises(AppException, match="Unable to train FAQ! Contact support"):
                gpt3.train()

    @responses.activate
    def test_gpt3_faq_embedding_train_payload_upsert_error_json(self):
        bot = "test_embed_faq_payload_upsert_error"
        user = "test"
        value = "nupurk"
        test_content = CognitionData(
            data={
                "filter": {
                    "should": [
                        {"key": "city", "match": {"value": "London"}},
                        {"key": "color", "match": {"value": "red"}}
                    ]
                }
            },
            content_type="json",
            metadata=[],
            bot=bot, user=user).save()
        secret = BotSecrets(secret_type=BotSecretType.gpt_key.value, value=value, bot=bot, user=user).save()

        embedding = list(np.random.random(GPT3FAQEmbedding.__embedding__))

        request_header = {"Authorization": "Bearer nupurk"}

        responses.add(
            url="https://api.openai.com/v1/embeddings",
            method="POST",
            status=200,
            match=[
                responses.matchers.json_params_matcher(
                    {"model": "text-embedding-ada-002", "input": json.dumps(test_content.data)}),
                responses.matchers.header_matcher(request_header)],
            json={'data': [{'embedding': embedding}]}
        )

        responses.add(
            url="https://api.openai.com/v1/embeddings",
            method="POST",
            status=200,
            match=[
                responses.matchers.json_params_matcher({"model": "text-embedding-ada-002", "input": test_content.data}),
                responses.matchers.header_matcher(request_header)],
            json={'data': [{'embedding': embedding}]}
        )

        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': secret}}):
            gpt3 = GPT3FAQEmbedding(test_content.bot, LLMSettings(provider="openai").to_mongo().to_dict())

            responses.add(
                "DELETE",
                urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.cached_resp_suffix}"),
                adding_headers={}
            )

            responses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.cached_resp_suffix}"),
                method="PUT",
                adding_headers={},
                match=[responses.matchers.json_params_matcher(
                    {'name': gpt3.bot + gpt3.cached_resp_suffix, 'vectors': gpt3.vector_config})],
                status=200
            )

            responses.add(
                "DELETE",
                urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.suffix}"),
                adding_headers={}
            )

            responses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.suffix}"),
                method="PUT",
                adding_headers={},
                match=[responses.matchers.json_params_matcher(
                    {'name': gpt3.bot + gpt3.suffix, 'vectors': gpt3.vector_config})],
                status=200
            )

            responses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.suffix}/points"),
                method="PUT",
                adding_headers={},
                match=[responses.matchers.json_params_matcher({'points': [{'id': test_content.vector_id,
                                                                           'vector': embedding,
                                                                           'payload': {
                                                                               "filter": {
                                                                                   "should": [
                                                                                       {"key": "city",
                                                                                        "match": {"value": "London"}},
                                                                                       {"key": "color",
                                                                                        "match": {"value": "red"}}
                                                                                   ]
                                                                               }, 'collection_name': 'test_embed_faq_payload_upsert_error_faq_embd'
                                                                           }
                                                                           }]})],
                json={"result": None,
                      'status': {'error': 'Json deserialize error: missing field `vectors` at line 1 column 34779'},
                      "time": 0.003612634}
            )

            with pytest.raises(AppException, match="Unable to train FAQ! Contact support"):
                gpt3.train()

    @responses.activate
    def test_gpt3_faq_embedding_predict(self):
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

        responses.add(
            url="https://api.openai.com/v1/embeddings",
            method="POST",
            status=200,
            match=[responses.matchers.json_params_matcher({"model": "text-embedding-ada-002", "input": query}),
                   responses.matchers.header_matcher(request_header)],
            json={'data': [{'embedding': embedding}]}
        )

        responses.add(
            url="https://api.openai.com/v1/chat/completions",
            method="POST",
            status=200,
            match=[responses.matchers.json_params_matcher(mock_completion_request),
                   responses.matchers.header_matcher(request_header)],
            json={'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}
        )


        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': secret}}):
            gpt3 = GPT3FAQEmbedding(test_content.bot, LLMSettings(provider="openai").to_mongo().to_dict())

            responses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.suffix}/points/search"),
                method="POST",
                adding_headers={},
                match=[responses.matchers.json_params_matcher(
                    {'vector': embedding, 'limit': 10, 'with_payload': True, 'score_threshold': 0.70})],
                json={'result': [
                    {'id': test_content.vector_id, 'score': 0.80, "payload": {'content': test_content.data}}]}
            )

            responses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.cached_resp_suffix}/points/search"),
                method="POST",
                adding_headers={},
                match=[responses.matchers.json_params_matcher(
                    {'vector': embedding, 'limit': 1, 'with_payload': True, 'score_threshold': 0.99})],
                json={'result': []}
            )

            responses.add(
                url=urljoin(Utility.environment['vector']['db'],
                            f"/collections/{gpt3.bot}{gpt3.cached_resp_suffix}/points"),
                method="PUT",
                adding_headers={},
                match=[responses.matchers.json_params_matcher(
                    {'points': [{'id': Utility.create_uuid_from_string(query), 'vector': embedding,
                                 'payload': {"query": query, "response": generated_text}}]})],
                json={"result": {"operation_id": 0, "status": "acknowledged"}, "status": "ok", "time": 0.003612634}
            )

            response = gpt3.predict(query, **k_faq_action_config)
            assert response['content'] == generated_text

    @responses.activate
    def test_gpt3_faq_embedding_predict_with_values(self):
        embedding = list(np.random.random(GPT3FAQEmbedding.__embedding__))

        test_content = CognitionData(
            data="Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.",
            bot="test_embed_faq_predict", user="test").save()

        generated_text = "Python is dynamically typed, garbage-collected, high level, general purpose programming."
        query = "What kind of language is python?"
        k_faq_action_config = {
            "system_prompt": "You are a personal assistant. Answer the question according to the below context",
            "context_prompt": "Based on below context answer question, if answer not in context check previous logs.",
            "top_results": 10, "similarity_threshold": 0.70, 'use_similarity_prompt': True, 'similarity_prompt_name': 'Similarity Prompt',
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

        responses.add(
            url="https://api.openai.com/v1/embeddings",
            method="POST",
            status=200,
            match=[responses.matchers.json_params_matcher({"model": "text-embedding-ada-002", "input": query}),
                   responses.matchers.header_matcher(request_header)],
            json={'data': [{'embedding': embedding}]}
        )

        responses.add(
            url="https://api.openai.com/v1/chat/completions",
            method="POST",
            status=200,
            match=[responses.matchers.json_params_matcher(mock_completion_request),
                   responses.matchers.header_matcher(request_header)],
            json={'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}
        )

        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': 'test'}}):
            gpt3 = GPT3FAQEmbedding(test_content.bot, LLMSettings(provider="openai").to_mongo().to_dict())

            responses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.suffix}/points/search"),
                method="POST",
                adding_headers={},
                match=[responses.matchers.json_params_matcher(
                    {'vector': embedding, 'limit': 10, 'with_payload': True, 'score_threshold': 0.70})],
                json={'result': [
                    {'id': test_content.vector_id, 'score': 0.80, "payload": {'content': test_content.data}}]}
            )

            responses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.cached_resp_suffix}/points/search"),
                method="POST",
                adding_headers={},
                match=[responses.matchers.json_params_matcher(
                    {'vector': embedding, 'limit': 1, 'with_payload': True, 'score_threshold': 0.99})],
                json={'result': []}
            )

            responses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.cached_resp_suffix}/points"),
                method="PUT",
                adding_headers={},
                match=[responses.matchers.json_params_matcher(
                    {'points': [{'id': Utility.create_uuid_from_string(query), 'vector': embedding,
                                 'payload': {"query": query, "response": generated_text}}]})],
                json={"result": {"operation_id": 0, "status": "acknowledged"}, "status": "ok", "time": 0.003612634}
            )

            response = gpt3.predict(query, **k_faq_action_config)
            assert response['content'] == generated_text
            assert gpt3.logs == [
                {'message': 'Skipping cache lookup as `enable_response_cache` is disabled.'},
                {'messages': [{'role': 'system', 'content': 'You are a personal assistant. Answer the question according to the below context'},
                              {'role': 'user', 'content': 'Based on below context answer question, if answer not in context check previous logs.\nSimilarity Prompt:\nPython is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.\nInstructions on how to use Similarity Prompt: Answer according to this context.\n \nQ: What kind of language is python? \nA:'}],
                 'raw_completion_response': {'choices': [{
                     'message': {'content': 'Python is dynamically typed, garbage-collected, high level, general purpose programming.', 'role': 'assistant'}}]},
                 'type': 'answer_query', 'hyperparameters': {'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-3.5-turbo', 'top_p': 0.0, 'n': 1, 'stream': False, 'stop': None, 'presence_penalty': 0.0, 'frequency_penalty': 0.0, 'logit_bias': {}}}, {'message': 'Skipping response caching as `enable_response_cache` is disabled.'}]

    @responses.activate
    def test_gpt3_faq_embedding_predict_with_values_with_instructions(self):
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
            {'role': 'system', 'content': 'You are a personal assistant. Answer the question according to the below context'},
            {'role': 'user', 'content': 'Based on below context answer question, if answer not in context check previous logs.\nSimilarity Prompt:\nJava is a high-level, general-purpose programming language. Java is known for its write once, run anywhere capability. \nInstructions on how to use Similarity Prompt: Answer according to this context.\n \nAnswer in a short way.\nKeep it simple. \nQ: What kind of language is python? \nA:'}
        ]}
        mock_completion_request.update(hyperparameters)
        request_header = {"Authorization": "Bearer knupur"}

        responses.add(
            url="https://api.openai.com/v1/embeddings",
            method="POST",
            status=200,
            match=[responses.matchers.json_params_matcher({"model": "text-embedding-ada-002", "input": query}),
                   responses.matchers.header_matcher(request_header)],
            json={'data': [{'embedding': embedding}]}
        )

        responses.add(
            url="https://api.openai.com/v1/chat/completions",
            method="POST",
            status=200,
            match=[responses.matchers.json_params_matcher(mock_completion_request),
                   responses.matchers.header_matcher(request_header)],
            json={'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}
        )

        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': 'test'}}):
            gpt3 = GPT3FAQEmbedding(test_content.bot, LLMSettings(provider="openai").to_mongo().to_dict())

            responses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.suffix}/points/search"),
                method="POST",
                adding_headers={},
                match=[responses.matchers.json_params_matcher(
                    {'vector': embedding, 'limit': 10, 'with_payload': True, 'score_threshold': 0.70})],
                json={'result': [
                    {'id': test_content.vector_id, 'score': 0.80, "payload": {'content': test_content.data}}]}
            )

            responses.add(
                url=urljoin(Utility.environment['vector']['db'],
                            f"/collections/{gpt3.bot}{gpt3.cached_resp_suffix}/points/search"),
                method="POST",
                adding_headers={},
                match=[responses.matchers.json_params_matcher(
                    {'vector': embedding, 'limit': 1, 'with_payload': True, 'score_threshold': 0.99})],
                json={'result': []}
            )

            responses.add(
                url=urljoin(Utility.environment['vector']['db'],
                            f"/collections/{gpt3.bot}{gpt3.cached_resp_suffix}/points"),
                method="PUT",
                adding_headers={},
                match=[responses.matchers.json_params_matcher(
                    {'points': [{'id': Utility.create_uuid_from_string(query), 'vector': embedding,
                                 'payload': {"query": query, "response": generated_text}}]})],
                json={"result": {"operation_id": 0, "status": "acknowledged"}, "status": "ok", "time": 0.003612634}
            )

            response = gpt3.predict(query, **k_faq_action_config)
            assert response['content'] == generated_text
            assert gpt3.logs == [
                {'message': 'Skipping cache lookup as `enable_response_cache` is disabled.'},
                {'messages': [{'role': 'system', 'content': 'You are a personal assistant. Answer the question according to the below context'},
                              {'role': 'user', 'content': 'Based on below context answer question, if answer not in context '
                                                          'check previous logs.\nSimilarity Prompt:\nJava is a high-level, general-purpose '
                                                          'programming language. Java is known for its write once, run anywhere capability. '
                                                          '\nInstructions on how to use Similarity Prompt: Answer according to this context.'
                                                          '\n \nAnswer in a short way.\nKeep it simple. \nQ: What kind of language is python? \nA:'}],
                 'raw_completion_response': {'choices': [{'message': {'content': 'Python is dynamically typed, garbage-collected, '
                                                                                 'high level, general purpose programming.', 'role': 'assistant'}}]},
                 'type': 'answer_query', 'hyperparameters': {'temperature': 0.0, 'max_tokens': 300, 'model': 'gpt-3.5-turbo', 'top_p': 0.0, 'n': 1,
                                                             'stream': False, 'stop': None, 'presence_penalty': 0.0, 'frequency_penalty': 0.0, 'logit_bias': {}}},
                {'message': 'Skipping response caching as `enable_response_cache` is disabled.'}]

    @responses.activate
    @mock.patch.object(GPT3FAQEmbedding, "_GPT3FAQEmbedding__get_answer", autospec=True)
    @mock.patch.object(GPT3FAQEmbedding, "_GPT3FAQEmbedding__get_embedding", autospec=True)
    def test_gpt3_faq_embedding_predict_completion_connection_error(self, mock_embedding, mock_completion):
        embedding = list(np.random.random(GPT3FAQEmbedding.__embedding__))

        test_content = CognitionData(
            data="Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.",
            bot="test_embed_faq_predict", user="test").save()

        generated_text = "Python is dynamically typed, garbage-collected, high level, general purpose programming."
        query = "What kind of language is python?"
        k_faq_action_config = {
            "system_prompt": "You are a personal assistant. Answer the question according to the below context",
            "context_prompt": "Based on below context answer question, if answer not in context check previous logs.",
            "top_results": 10, "similarity_threshold": 0.70, 'use_similarity_prompt': True, 'similarity_prompt_name': 'Similarity Prompt',
            'similarity_prompt_instructions': 'Answer according to this context.', "enable_response_cache": True}

        def __mock_connection_error(*args, **kwargs):
            import openai

            raise openai.error.APIConnectionError("Connection reset by peer!")

        mock_embedding.return_value = embedding
        mock_completion.side_effect = __mock_connection_error

        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': 'test'}}):
            gpt3 = GPT3FAQEmbedding(test_content.bot, LLMSettings(provider="openai").to_mongo().to_dict())

            responses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.suffix}/points/search"),
                method="POST",
                adding_headers={},
                match=[responses.matchers.json_params_matcher(
                    {'vector': embedding, 'limit': 10, 'with_payload': True, 'score_threshold': 0.70})],
                json={'result': [
                    {'id': test_content.vector_id, 'score': 0.80, "payload": {'content': test_content.data}}]}
            )

            responses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.cached_resp_suffix}/points/search"),
                method="POST",
                adding_headers={},
                match=[responses.matchers.json_params_matcher(
                    {'vector': embedding, 'limit': 1, 'with_payload': True, 'score_threshold': 0.99})],
                json={'result': []}
            )

            responses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.cached_resp_suffix}/points/search"),
                method="POST",
                adding_headers={},
                match=[responses.matchers.json_params_matcher(
                    {'vector': embedding, 'limit': 3, 'with_payload': True, 'score_threshold': 0.7})],
                json={'result': [
                    {'id': Utility.create_uuid_from_string(query), 'score': 0.80, "payload": {'query': query, "content": generated_text}}]}
            )

            response = gpt3.predict(query, **k_faq_action_config)

            assert response == {'content': {'result': [
                {'id': '5ec0694b-1c19-b8c6-c54d-1cdbff20ca64', 'score': 0.8,
                 'payload': {'query': 'What kind of language is python?',
                             'content': 'Python is dynamically typed, garbage-collected, high level, general purpose programming.'}}]},
                'is_from_cache': True, 'exception': "Connection reset by peer!", 'is_failure': True}

            assert mock_embedding.call_args.args[1] == query

            assert mock_completion.call_args.args[1] == 'What kind of language is python?'
            assert mock_completion.call_args.args[2] == 'You are a personal assistant. Answer the question according to the below context'
            assert mock_completion.call_args.args[3] == """Based on below context answer question, if answer not in context check previous logs.
Similarity Prompt:
Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.
Instructions on how to use Similarity Prompt: Answer according to this context.
"""
            assert mock_completion.call_args.kwargs == {'top_results': 10, 'similarity_threshold': 0.7,
                                                        'use_similarity_prompt': True, 'enable_response_cache': True,
                                                        'similarity_prompt_name': 'Similarity Prompt',
                                                        'similarity_prompt_instructions': 'Answer according to this context.'}
            assert gpt3.logs == [{'message': 'Searching exact match in cache as `enable_response_cache` is enabled.'},
                                 {'error': 'Retrieving chat completion for the provided query. Connection reset by peer!'},
                                 {'message': 'Searching recommendations from cache as `enable_response_cache` is enabled.'}]

    @responses.activate
    @mock.patch.object(GPT3FAQEmbedding, "_GPT3FAQEmbedding__get_embedding", autospec=True)
    def test_gpt3_faq_embedding_predict_exact_match(self, mock_embedding):
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

        mock_embedding.return_value = embedding

        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': 'test'}}):
            gpt3 = GPT3FAQEmbedding(test_content.bot, LLMSettings(provider="openai").to_mongo().to_dict())

            responses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.cached_resp_suffix}/points/search"),
                method="POST",
                adding_headers={},
                match=[responses.matchers.json_params_matcher(
                    {'vector': embedding, 'limit': 1, 'with_payload': True, 'score_threshold': 0.99})],
                json={'result': [{'id': '5ec0694b-1c19-b8c6-c54d-1cdbff20ca64', 'score': 1.0,
                                  'payload': {'query': query, 'response': generated_text}}]}
            )

            response = gpt3.predict(query, **k_faq_action_config)
            assert response == {'content': generated_text, 'is_from_cache': True}

            assert mock_embedding.call_args.args[1] == query
            assert gpt3.logs == [{'message': 'Searching exact match in cache as `enable_response_cache` is enabled.'},
                                 {"message": "Found exact query match in cache."}]

    @responses.activate
    @mock.patch.object(GPT3FAQEmbedding, "_GPT3FAQEmbedding__get_embedding", autospec=True)
    def test_gpt3_faq_embedding_predict_embedding_connection_error(self, mock_embedding):
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

            responses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.cached_resp_suffix}/points/search"),
                method="POST",
                adding_headers={},
                match=[responses.matchers.json_params_matcher(
                    {'vector': embedding, 'limit': 3, 'with_payload': True, 'score_threshold': 0.7})],
                json={'result': [
                    {'id': Utility.create_uuid_from_string(query), 'score': 0.80,
                     "payload": {'query': query, "content": generated_text}}]}
            )

            response = gpt3.predict(query, **k_faq_action_config)
            assert response == {'content': {'result': [
                {'id': '5ec0694b-1c19-b8c6-c54d-1cdbff20ca64', 'score': 0.8,
                 'payload': {'query': 'What kind of language is python?',
                             'content': 'Python is dynamically typed, garbage-collected, high level, general purpose programming.'}}]},
                'is_from_cache': True,  'exception': 'Connection reset by peer!', 'is_failure': True}

            assert mock_embedding.call_args.args[1] == query
            assert gpt3.logs == [{'error': 'Creating a new embedding for the provided query. Connection reset by peer!'},
                                 {'message': 'Searching recommendations from cache as `enable_response_cache` is enabled.'}]

    @responses.activate
    @mock.patch.object(GPT3FAQEmbedding, "_GPT3FAQEmbedding__get_answer", autospec=True)
    @mock.patch.object(GPT3FAQEmbedding, "_GPT3FAQEmbedding__get_embedding", autospec=True)
    def test_gpt3_faq_embedding_predict_completion_connection_error_query_not_cached(self, mock_embedding, mock_completion):
        embedding = list(np.random.random(GPT3FAQEmbedding.__embedding__))

        test_content = CognitionData(
            data="Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.",
            bot="test_embed_faq_predict", user="test").save()

        query = "What kind of language is python?"
        k_faq_action_config = {
            "system_prompt": "You are a personal assistant. Answer the question according to the below context",
            "context_prompt": "Based on below context answer question, if answer not in context check previous logs.",
            "top_results": 10, "similarity_threshold": 0.70, 'similarity_prompt_name': 'Similarity Prompt',
            'similarity_prompt_instructions': 'Answer according to this context.', 'use_similarity_prompt': True,
            "enable_response_cache": True
        }

        def __mock_exception(*args, **kwargs):
            raise ConnectionResetError("Connection reset by peer!")

        mock_embedding.return_value = embedding
        mock_completion.side_effect = __mock_exception

        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': 'test'}}):
            gpt3 = GPT3FAQEmbedding(test_content.bot, LLMSettings(provider="openai").to_mongo().to_dict())

            responses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.suffix}/points/search"),
                method="POST",
                adding_headers={},
                match=[responses.matchers.json_params_matcher(
                    {'vector': embedding, 'limit': 10, 'with_payload': True, 'score_threshold': 0.70})],
                json={'result': [
                    {'id': test_content.vector_id, 'score': 0.80, "payload": {'content': test_content.data}}]}
            )

            responses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.cached_resp_suffix}/points/search"),
                method="POST",
                adding_headers={},
                match=[responses.matchers.json_params_matcher(
                    {'vector': embedding, 'limit': 1, 'with_payload': True, 'score_threshold': 0.99})],
                json={'result': []}
            )

            responses.add(
                url=urljoin(Utility.environment['vector']['db'],
                            f"/collections/{gpt3.bot}{gpt3.cached_resp_suffix}/points/search"),
                method="POST",
                adding_headers={},
                match=[responses.matchers.json_params_matcher(
                    {'vector': embedding, 'limit': 3, 'with_payload': True, 'score_threshold': 0.7})],
                json={'result': []}
            )

            with pytest.raises(AppException, match="Connection reset by peer!"):
                gpt3.predict(query, **k_faq_action_config)

    @responses.activate
    def test_gpt3_faq_embedding_predict_with_previous_bot_responses(self):
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

        responses.add(
            url="https://api.openai.com/v1/embeddings",
            method="POST",
            status=200,
            match=[responses.matchers.json_params_matcher({"model": "text-embedding-ada-002", "input": query}),
                   responses.matchers.header_matcher(request_header)],
            json={'data': [{'embedding': embedding}]}
        )

        responses.add(
            url="https://api.openai.com/v1/chat/completions",
            method="POST",
            status=200,
            match=[responses.matchers.json_params_matcher(mock_completion_request),
                   responses.matchers.header_matcher(request_header)],
            json={'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}
        )

        gpt3 = GPT3FAQEmbedding(test_content.bot, LLMSettings(provider="openai").to_mongo().to_dict())

        responses.add(
            url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.suffix}/points/search"),
            method="POST",
            adding_headers={},
            match=[responses.matchers.json_params_matcher(
                {'vector': embedding, 'limit': 10, 'with_payload': True, 'score_threshold': 0.70})],
            json={'result': [
                {'id': test_content.vector_id, 'score': 0.80, "payload": {'content': test_content.data}}]}
        )

        responses.add(
            url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.cached_resp_suffix}/points/search"),
            method="POST",
            adding_headers={},
            match=[responses.matchers.json_params_matcher(
                {'vector': embedding, 'limit': 1, 'with_payload': True, 'score_threshold': 0.99})],
            json={'result': []}
        )

        responses.add(
            url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.cached_resp_suffix}/points"),
            method="PUT",
            adding_headers={},
            match=[responses.matchers.json_params_matcher(
                {'points': [{'id': Utility.create_uuid_from_string(query), 'vector': embedding,
                             'payload': {"query": query, "response": generated_text}}]})],
            json={"result": {"operation_id": 0, "status": "acknowledged"}, "status": "ok", "time": 0.003612634}
        )

        response = gpt3.predict(query, **k_faq_action_config)
        assert response['content'] == generated_text

    @responses.activate
    def test_gpt3_faq_embedding_predict_with_query_prompt(self):
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

        responses.add(
            url="https://api.openai.com/v1/embeddings",
            method="POST",
            status=200,
            match=[responses.matchers.json_params_matcher({"model": "text-embedding-ada-002", "input": query}),
                   responses.matchers.header_matcher(request_header)],
            json={'data': [{'embedding': embedding}]}
        )

        responses.add(
            url="https://api.openai.com/v1/chat/completions",
            method="POST",
            status=200,
            match=[responses.matchers.json_params_matcher(mock_rephrase_request),
                   responses.matchers.header_matcher(request_header)],
            json={'choices': [{'message': {'content': rephrased_query, 'role': 'assistant'}}]}
        )

        responses.add(
            url="https://api.openai.com/v1/chat/completions",
            method="POST",
            status=200,
            match=[responses.matchers.json_params_matcher(mock_completion_request),
                   responses.matchers.header_matcher(request_header)],
            json={'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}
        )

        gpt3 = GPT3FAQEmbedding(test_content.bot, LLMSettings(provider="openai").to_mongo().to_dict())

        responses.add(
            url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.suffix}/points/search"),
            method="POST",
            adding_headers={},
            match=[responses.matchers.json_params_matcher(
                {'vector': embedding, 'limit': 10, 'with_payload': True, 'score_threshold': 0.70})],
            json={'result': [
                {'id': test_content.vector_id, 'score': 0.80, "payload": {'content': test_content.data}}]}
        )
        responses.add(
            url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.cached_resp_suffix}/points/search"),
            method="POST",
            adding_headers={},
            match=[responses.matchers.json_params_matcher(
                {'vector': embedding, 'limit': 1, 'with_payload': True, 'score_threshold': 0.99})],
            json={'result': []}
        )
        responses.add(
            url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.cached_resp_suffix}/points"),
            method="PUT",
            adding_headers={},
            match=[responses.matchers.json_params_matcher(
                {'points': [{'id': Utility.create_uuid_from_string(query), 'vector': embedding,
                             'payload': {"query": query, "response": generated_text}}]})],
            json={"result": {"operation_id": 0, "status": "acknowledged"}, "status": "ok", "time": 0.003612634}
        )

        response = gpt3.predict(query, **k_faq_action_config)
        assert response['content'] == generated_text
