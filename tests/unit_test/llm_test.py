import pytest
import os
from kairon.shared.utils import Utility
from mongoengine import connect
import mock
from kairon.shared.llm.gpt3 import GPT3FAQEmbedding, LLMBase
from kairon.shared.llm.factory import LLMFactory
from kairon.shared.data.data_objects import BotContent
import numpy as np
from qdrant_client.models import ScoredPoint
from uuid6 import uuid7
from openai.util import convert_to_openai_object
from openai.openai_response import OpenAIResponse


class TestLLM:
    @pytest.fixture(autouse=True, scope="class")
    def init_connection(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))

    def test_llm_base_train(self):
        with pytest.raises(Exception):
            base = LLMBase()
            base.train()

    def test_llm_base_predict(self):
        with pytest.raises(Exception):
            base = LLMBase()
            base.predict("Sample")

    def test_llm_factory_invalid_type(self):
        with pytest.raises(Exception):
            LLMFactory.get_instance("test", "sample")

    @mock.patch("kairon.shared.llm.gpt3.QdrantClient", autospec=True)
    def test_llm_factory_faq_type(self, mock_vec_client):
        inst = LLMFactory.get_instance("test", "faq")
        assert isinstance(inst, GPT3FAQEmbedding)
        assert mock_vec_client.call_args.kwargs['url'] == Utility.environment['vector']['db']
        assert mock_vec_client.call_args.kwargs['api_key'] == Utility.environment['vector']['key']

    @mock.patch("kairon.shared.llm.gpt3.QdrantClient", autospec=True)
    def test_llm_factory_faq_type_set_vector_key(self, mock_vec_client):
        with mock.patch.dict(Utility.environment, {'vector': {"db": "http://test:6333", 'key': 'test'}}):
            inst = LLMFactory.get_instance("test", "faq")
            assert isinstance(inst, GPT3FAQEmbedding)
            assert mock_vec_client.call_args.kwargs['url'] == Utility.environment['vector']['db']
            assert mock_vec_client.call_args.kwargs['api_key'] == Utility.environment['vector']['key']

    @mock.patch("kairon.shared.llm.gpt3.openai.Embedding.create", autospec=True)
    @mock.patch("kairon.shared.llm.gpt3.QdrantClient", autospec=True)
    def test_gpt3_faq_embedding_train_collection_exists(self, mock_vec_client, mock_openai):
        embedding = list(np.random.random(GPT3FAQEmbedding.__embedding__))
        mock_openai.return_value = convert_to_openai_object(OpenAIResponse({'data': [{'embedding': embedding}]}, {}))

        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': 'test'}}):
            test_content = BotContent(
                data="Welcome! Are you completely new to programming? If not then we presume you will be looking for information about why and how to get started with Python",
                bot="test_embed_faq", user="test").save()

            gpt3 = GPT3FAQEmbedding(test_content.bot)
            response = gpt3.train()

            assert response['faq'] == 1

            name, args, kwargs = mock_vec_client.method_calls.pop(0)
            assert name == '().get_collection'
            assert kwargs['collection_name'] == test_content.bot + gpt3.suffix

            name, args, kwargs = mock_vec_client.method_calls.pop(0)
            assert name == '().upsert'
            assert kwargs['collection_name'] == test_content.bot + gpt3.suffix
            point = kwargs['points'][0]
            assert point.vector == embedding
            assert point.payload['content'] == test_content.data

            assert mock_openai.call_args.kwargs['api_key'] == Utility.environment['llm']['api_key']
            assert mock_openai.call_args.kwargs['input'] == test_content.data

    @mock.patch("kairon.shared.llm.gpt3.openai.Embedding.create", autospec=True)
    @mock.patch("kairon.shared.llm.gpt3.QdrantClient.upsert", autospec=True)
    @mock.patch("kairon.shared.llm.gpt3.QdrantClient.recreate_collection", autospec=True)
    @mock.patch("kairon.shared.llm.gpt3.QdrantClient.get_collection", autospec=True)
    def test_gpt3_faq_embedding_train_collection_does_not_exists(self,
                                                                 mock_get_collection,
                                                                 mock_recreate_collection,
                                                                 mock_upsert,
                                                                 mock_openai):
        embedding = list(np.random.random(GPT3FAQEmbedding.__embedding__))
        mock_openai.return_value = convert_to_openai_object(OpenAIResponse({'data': [{'embedding': embedding}]}, {}))

        mock_get_collection.side_effect = Exception()

        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': 'test'}}):
            test_content = BotContent(
                data="Welcome! Are you completely new to programming? If not then we presume you will be looking for information about why and how to get started with Python",
                bot="test_embed_faq_not_exists", user="test").save()

            gpt3 = GPT3FAQEmbedding(test_content.bot)
            response = gpt3.train()
            assert response['faq'] == 1

            assert mock_recreate_collection.call_args.kwargs['collection_name'] == test_content.bot + gpt3.suffix
            assert mock_recreate_collection.call_args.kwargs['vectors_config'] == gpt3.vector_config

            assert mock_upsert.call_args.kwargs['collection_name'] == test_content.bot + gpt3.suffix
            point = mock_upsert.call_args.kwargs['points'][0]
            assert point.vector == embedding
            assert point.payload['content'] == test_content.data

            assert mock_openai.call_args.kwargs['api_key'] == Utility.environment['llm']['api_key']
            assert mock_openai.call_args.kwargs['input'] == test_content.data

    @mock.patch("kairon.shared.llm.gpt3.openai.Completion.create", autospec=True)
    @mock.patch("kairon.shared.llm.gpt3.openai.Embedding.create", autospec=True)
    @mock.patch("kairon.shared.llm.gpt3.QdrantClient.search", autospec=True)
    def test_gpt3_faq_embedding_predict(self,
                                        mock_search,
                                        mock_embedding,
                                        mock_completion
                                        ):
        embedding = list(np.random.random(GPT3FAQEmbedding.__embedding__))

        test_content = BotContent(
            data="Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.",
            bot="test_embed_faq_predict", user="test").save()

        generated_text = "Python is dynamically typed, garbage-collected, high level, general purpose programming."
        query = "What kind of language is python?"

        mock_embedding.return_value = convert_to_openai_object(OpenAIResponse({'data': [{'embedding': embedding}]}, {}))
        mock_completion.return_value = convert_to_openai_object(OpenAIResponse({'choices': [{'text': generated_text}]}, {}))
        mock_search.return_value = [ScoredPoint(id=uuid7().__str__(), score=0.80, version=1, payload={'content': test_content.data})]

        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': 'test'}}):

            gpt3 = GPT3FAQEmbedding(test_content.bot)
            response = gpt3.predict(query)

            assert response['content'] == generated_text

            assert mock_search.call_args.kwargs['collection_name'] == test_content.bot + gpt3.suffix
            assert mock_search.call_args.kwargs['query_vector'] == embedding
            assert mock_search.call_args.kwargs['with_payload']
            assert mock_search.call_args.kwargs['limit'] == 10

            assert mock_embedding.call_args.kwargs['api_key'] == Utility.environment['llm']['api_key']
            assert mock_embedding.call_args.kwargs['input'] == query

            assert mock_completion.call_args.kwargs['api_key'] == Utility.environment['llm']['api_key']
            assert mock_completion.call_args.kwargs['prompt'] == f"{gpt3.__answer_command__} \n\nContext:\n{test_content.data}\n\n Q: {query}\n A:"
            assert all(mock_completion.call_args.kwargs[key] == gpt3.__answer_params__[key] for key in gpt3.__answer_params__.keys())
