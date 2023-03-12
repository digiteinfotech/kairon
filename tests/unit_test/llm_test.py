import os
from urllib.parse import urljoin

import mock
import numpy as np
import pytest
import responses
from mongoengine import connect
from openai.openai_response import OpenAIResponse
from openai.util import convert_to_openai_object

from kairon.shared.data.data_objects import BotContent
from kairon.shared.llm.factory import LLMFactory
from kairon.shared.llm.gpt3 import GPT3FAQEmbedding, LLMBase
from kairon.shared.utils import Utility
from kairon.exceptions import AppException


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
            LLMFactory.get_instance("test", "sample")

    def test_llm_factory_faq_type(self):
        inst = LLMFactory.get_instance("test", "faq")
        assert isinstance(inst, GPT3FAQEmbedding)
        assert inst.db_url == Utility.environment['vector']['db']
        assert inst.headers == {}

    def test_llm_factory_faq_type_set_vector_key(self):
        with mock.patch.dict(Utility.environment, {'vector': {"db": "http://test:6333", 'key': 'test'}}):
            inst = LLMFactory.get_instance("test", "faq")
            assert isinstance(inst, GPT3FAQEmbedding)
            assert inst.db_url == Utility.environment['vector']['db']
            assert inst.headers == {'api-key': Utility.environment['vector']['key']}

    @responses.activate
    @mock.patch("kairon.shared.llm.gpt3.openai.Embedding.create", autospec=True)
    def test_gpt3_faq_embedding_train(self, mock_openai):
        test_content = BotContent(
            data="Welcome! Are you completely new to programming? If not then we presume you will be looking for information about why and how to get started with Python",
            bot="test_embed_faq", user="test").save()

        embedding = list(np.random.random(GPT3FAQEmbedding.__embedding__))
        mock_openai.return_value = convert_to_openai_object(OpenAIResponse({'data': [{'embedding': embedding}]}, {}))
        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': 'test'}}):
            gpt3 = GPT3FAQEmbedding(test_content.bot)

            responses.add(
                "DELETE",
                urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.suffix}"),
                adding_headers={}
            )

            responses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.suffix}"),
                method="PUT",
                adding_headers={},
                match=[responses.json_params_matcher({'name': gpt3.bot + gpt3.suffix, 'vectors': gpt3.vector_config})],
                status=200
            )

            responses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.suffix}/points"),
                method="PUT",
                adding_headers={},
                match=[responses.json_params_matcher({'points': [{'id': test_content.vector_id,
                                                                  'vector': embedding,
                                                                  'payload': {'content': test_content.data}
                                                                  }]})],
                json={"result": {"operation_id": 0, "status": "acknowledged"}, "status": "ok", "time": 0.003612634}
            )

            response = gpt3.train()
            assert response['faq'] == 1

            assert mock_openai.call_args.kwargs['api_key'] == Utility.environment['llm']['api_key']
            assert mock_openai.call_args.kwargs['input'] == test_content.data

    @responses.activate
    @mock.patch("kairon.shared.llm.gpt3.openai.Embedding.create", autospec=True)
    def test_gpt3_faq_embedding_train_upsert_error(self, mock_openai):
        test_content = BotContent(
            data="Welcome! Are you completely new to programming? If not then we presume you will be looking for information about why and how to get started with Python",
            bot="test_embed_faq_not_exists", user="test").save()

        embedding = list(np.random.random(GPT3FAQEmbedding.__embedding__))
        mock_openai.return_value = convert_to_openai_object(OpenAIResponse({'data': [{'embedding': embedding}]}, {}))

        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': 'test'}}):
            gpt3 = GPT3FAQEmbedding(test_content.bot)

            responses.add(
                "DELETE",
                urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.suffix}"),
                adding_headers={}
            )

            responses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.suffix}"),
                method="PUT",
                adding_headers={},
                match=[responses.json_params_matcher({'name': gpt3.bot + gpt3.suffix, 'vectors': gpt3.vector_config})],
                status=200
            )

            responses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.suffix}/points"),
                method="PUT",
                adding_headers={},
                match=[responses.json_params_matcher({'points': [{'id': test_content.vector_id,
                                                                  'vector': embedding,
                                                                  'payload': {'content': test_content.data}
                                                                  }]})],
                json={"result": None,
                      'status': {'error': 'Json deserialize error: missing field `vectors` at line 1 column 34779'},
                      "time": 0.003612634}
            )

            with pytest.raises(AppException, match="Unable to train faq! contact support"):
                gpt3.train()

                assert mock_openai.call_args.kwargs['api_key'] == Utility.environment['llm']['api_key']
                assert mock_openai.call_args.kwargs['input'] == test_content.data

    @responses.activate
    @mock.patch("kairon.shared.llm.gpt3.openai.ChatCompletion.create", autospec=True)
    @mock.patch("kairon.shared.llm.gpt3.openai.Embedding.create", autospec=True)
    def test_gpt3_faq_embedding_predict(self,
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
        mock_completion.return_value = convert_to_openai_object(
            OpenAIResponse({'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}, {}))

        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': 'test'}}):
            gpt3 = GPT3FAQEmbedding(test_content.bot)

            responses.add(
                url=urljoin(Utility.environment['vector']['db'], f"/collections/{gpt3.bot}{gpt3.suffix}/points/search"),
                method="POST",
                adding_headers={},
                match=[responses.json_params_matcher(
                    {'vector': embedding, 'limit': 10, 'with_payload': True, 'score_threshold': 0.70})],
                json={'result': [
                    {'id': test_content.vector_id, 'score': 0.80, "payload": {'content': test_content.data}}]}
            )

            response = gpt3.predict(query)

            assert response['content'] == generated_text

            assert mock_embedding.call_args.kwargs['api_key'] == Utility.environment['llm']['api_key']
            assert mock_embedding.call_args.kwargs['input'] == query

            assert mock_completion.call_args.kwargs['api_key'] == Utility.environment['llm']['api_key']
            assert all(mock_completion.call_args.kwargs[key] == gpt3.__answer_params__[key] for key in
                       gpt3.__answer_params__.keys())
            assert mock_completion.call_args.kwargs[
                       'messages'] == [
            {"role": "system",
             "content": "You are a personal assistant. Answer question based on the context below"},
            {"role": "user", "content": f"{gpt3.__answer_command__} \n\nContext:\n{test_content.data}\n\n Q: {query}\n A:"}
        ]
