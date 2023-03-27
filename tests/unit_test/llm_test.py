import os
from urllib.parse import urljoin

import mock
import numpy as np
import pytest
import responses
from mongoengine import connect
from openai.openai_response import OpenAIResponse
from openai.util import convert_to_openai_object

from kairon.shared.admin.constants import BotSecretType
from kairon.shared.admin.data_objects import BotSecrets
from kairon.shared.data.constant import DEFAULT_CONTEXT_PROMPT, DEFAULT_SYSTEM_PROMPT
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
        BotSecrets(secret_type=BotSecretType.gpt_key.value, value='value', bot='test', user='test').save()
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
        bot = "test_embed_faq"
        user = "test"
        value = "nupurkhare"
        test_content = BotContent(
            data="Welcome! Are you completely new to programming? If not then we presume you will be looking for information about why and how to get started with Python",
            bot=bot, user=user).save()
        secret = BotSecrets(secret_type=BotSecretType.gpt_key.value, value=value, bot=bot, user=user).save()

        embedding = list(np.random.random(GPT3FAQEmbedding.__embedding__))
        mock_openai.return_value = convert_to_openai_object(OpenAIResponse({'data': [{'embedding': embedding}]}, {}))
        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': secret}}):
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

            print(mock_openai.call_args.kwargs['api_key'])
            assert mock_openai.call_args.kwargs['api_key'] == "nupurkhare"
            assert mock_openai.call_args.kwargs['input'] == test_content.data

    def test_gpt3_faq_embedding_train_failure(self):
        with pytest.raises(AppException, match=f"Bot secret '{BotSecretType.gpt_key.value}' not configured!"):
            GPT3FAQEmbedding('test_failure')

    @responses.activate
    @mock.patch("kairon.shared.llm.gpt3.openai.Embedding.create", autospec=True)
    def test_gpt3_faq_embedding_train_upsert_error(self, mock_openai):
        bot = "test_embed_faq_not_exists"
        user = "test"
        value = "nupurk"
        test_content = BotContent(
            data="Welcome! Are you completely new to programming? If not then we presume you will be looking for information about why and how to get started with Python",
            bot=bot, user=user).save()
        secret = BotSecrets(secret_type=BotSecretType.gpt_key.value, value=value, bot=bot, user=user).save()


        embedding = list(np.random.random(GPT3FAQEmbedding.__embedding__))
        mock_openai.return_value = convert_to_openai_object(OpenAIResponse({'data': [{'embedding': embedding}]}, {}))

        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': secret}}):
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

                assert mock_openai.call_args.kwargs['api_key'] == "nupurk"
                assert mock_openai.call_args.kwargs['input'] == test_content.data

    @responses.activate
    @mock.patch("kairon.shared.llm.gpt3.openai.ChatCompletion.create", autospec=True)
    @mock.patch("kairon.shared.llm.gpt3.openai.Embedding.create", autospec=True)
    def test_gpt3_faq_embedding_predict(self,
                                        mock_embedding,
                                        mock_completion
                                        ):
        embedding = list(np.random.random(GPT3FAQEmbedding.__embedding__))

        bot = "test_embed_faq_predict"
        user = "test"
        value = "knupur"
        test_content = BotContent(
            data="Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.",
            bot=bot, user=user).save()
        secret = BotSecrets(secret_type=BotSecretType.gpt_key.value, value=value, bot=bot, user=user).save()


        generated_text = "Python is dynamically typed, garbage-collected, high level, general purpose programming."
        query = "What kind of language is python?"

        mock_embedding.return_value = convert_to_openai_object(OpenAIResponse({'data': [{'embedding': embedding}]}, {}))
        mock_completion.return_value = convert_to_openai_object(
            OpenAIResponse({'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}, {}))

        with mock.patch.dict(Utility.environment, {'llm': {"faq": "GPT3_FAQ_EMBED", 'api_key': secret}}):
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

            print(mock_embedding.call_args.kwargs['api_key'])
            assert mock_embedding.call_args.kwargs['api_key'] == "knupur"
            assert mock_embedding.call_args.kwargs['input'] == query

            assert mock_completion.call_args.kwargs['api_key'] == "knupur"
            assert all(mock_completion.call_args.kwargs[key] == gpt3.__answer_params__[key] for key in
                       gpt3.__answer_params__.keys())
            assert mock_completion.call_args.kwargs[
                       'messages'] == [
            {"role": "system",
             "content": DEFAULT_SYSTEM_PROMPT},
            {"role": "user", "content": f"{DEFAULT_CONTEXT_PROMPT} \n\nContext:\n{test_content.data}\n\n Q: {query}\n A:"}
        ]

    @responses.activate
    @mock.patch("kairon.shared.llm.gpt3.openai.ChatCompletion.create", autospec=True)
    @mock.patch("kairon.shared.llm.gpt3.openai.Embedding.create", autospec=True)
    def test_gpt3_faq_embedding_predict_with_values(self,
                                                    mock_embedding,
                                                    mock_completion
                                                    ):
        embedding = list(np.random.random(GPT3FAQEmbedding.__embedding__))

        test_content = BotContent(
            data="Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.",
            bot="test_embed_faq_predict", user="test").save()

        generated_text = "Python is dynamically typed, garbage-collected, high level, general purpose programming."
        query = "What kind of language is python?"
        k_faq_action_config = {
            "system_prompt": "You are a personal assistant. Answer the question according to the below context",
            "context_prompt": "Based on below context answer question, if answer not in context check previous logs.",
            "top_results": 10, "similarity_threshold": 0.70}

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

            response = gpt3.predict(query, **k_faq_action_config)

            assert response['content'] == generated_text

            assert mock_embedding.call_args.kwargs['api_key'] == "knupur"
            assert mock_embedding.call_args.kwargs['input'] == query

            assert mock_completion.call_args.kwargs['api_key'] == "knupur"
            assert all(mock_completion.call_args.kwargs[key] == gpt3.__answer_params__[key] for key in
                       gpt3.__answer_params__.keys())
            assert mock_completion.call_args.kwargs[
                       'messages'] == [
                       {"role": "system",
                        "content": "You are a personal assistant. Answer the question according to the below context"},
                       {"role": "user",
                        "content":
                            f"Based on below context answer question, if answer not in context check previous logs."
                            f" \n\nContext:\n{test_content.data}\n\n Q: {query}\n A:"}
                   ]

    @responses.activate
    @mock.patch("kairon.shared.llm.gpt3.openai.ChatCompletion.create", autospec=True)
    @mock.patch("kairon.shared.llm.gpt3.openai.Embedding.create", autospec=True)
    def test_gpt3_faq_embedding_predict_with_previous_bot_responses(self,
                                        mock_embedding,
                                        mock_completion
                                        ):
        embedding = list(np.random.random(GPT3FAQEmbedding.__embedding__))

        bot = "test_embed_faq_predict"
        user = "test"
        value = "knupur"
        test_content = BotContent(
            data="Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.",
            bot=bot, user=user).save()

        generated_text = "Python is dynamically typed, garbage-collected, high level, general purpose programming."
        query = "What kind of language is python?"
        k_faq_action_config = {"previous_bot_responses": "A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language."}

        mock_embedding.return_value = convert_to_openai_object(OpenAIResponse({'data': [{'embedding': embedding}]}, {}))
        mock_completion.return_value = convert_to_openai_object(
            OpenAIResponse({'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}, {}))

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

        response = gpt3.predict(query, **k_faq_action_config)

        assert response['content'] == generated_text

        print(mock_embedding.call_args.kwargs['api_key'])
        assert mock_embedding.call_args.kwargs['api_key'] == "knupur"
        assert mock_embedding.call_args.kwargs['input'] == query

        assert mock_completion.call_args.kwargs['api_key'] == "knupur"
        assert all(mock_completion.call_args.kwargs[key] == gpt3.__answer_params__[key] for key in
                   gpt3.__answer_params__.keys())
        assert mock_completion.call_args.kwargs[
                   'messages'] == [
                   {"role": "system",
                    "content": DEFAULT_SYSTEM_PROMPT},
                   {"role": "user",
                    "content": f"{DEFAULT_CONTEXT_PROMPT} \n\nContext:\n{test_content.data}\n\n Q: {query}\n A:"},
                    {"role": "assistant",
                     "content": "A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language."}
               ]

    @responses.activate
    @mock.patch("kairon.shared.llm.gpt3.openai.ChatCompletion.create", autospec=True)
    @mock.patch("kairon.shared.llm.gpt3.openai.Embedding.create", autospec=True)
    def test_gpt3_faq_embedding_predict_with_query_prompt(self,
                                                                    mock_embedding,
                                                                    mock_completion
                                                                    ):
        embedding = list(np.random.random(GPT3FAQEmbedding.__embedding__))

        bot = "test_embed_faq_predict"
        user = "test"
        value = "knupur"
        test_content = BotContent(
            data="Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected.",
            bot=bot, user=user).save()

        generated_text = "Python is dynamically typed, garbage-collected, high level, general purpose programming."
        query = "What kind of language is python?"
        k_faq_action_config = {
            "query_prompt": "A programming language is a system of notation for writing computer programs.[1] Most programming languages are text-based formal languages, but they may also be graphical. They are a kind of computer language.",
            "use_query_prompt": True
        }

        mock_embedding.return_value = convert_to_openai_object(OpenAIResponse({'data': [{'embedding': embedding}]}, {}))
        mock_completion.return_value = convert_to_openai_object(
            OpenAIResponse({'choices': [{'message': {'content': generated_text, 'role': 'assistant'}}]}, {}))

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

        response = gpt3.predict(query, **k_faq_action_config)

        assert response['content'] == generated_text

        print(mock_embedding.call_args.kwargs['api_key'])
        assert mock_embedding.call_args.kwargs['api_key'] == "knupur"
        assert mock_embedding.call_args.kwargs['input'] == query

        assert mock_completion.call_args.kwargs['api_key'] == "knupur"
        assert all(mock_completion.call_args.kwargs[key] == gpt3.__answer_params__[key] for key in
                   gpt3.__answer_params__.keys())
        assert mock_completion.call_args.kwargs[
                   'messages'] == [
                   {"role": "system",
                    "content": DEFAULT_SYSTEM_PROMPT},
                   {"role": "user",
                    "content": f"{DEFAULT_CONTEXT_PROMPT}\n\n{k_faq_action_config['query_prompt']} \n\nContext:\n{test_content.data}\n\n Q: {query}\n A:"}
               ]
