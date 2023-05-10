from kairon.shared.admin.constants import BotSecretType
from kairon.shared.admin.processor import Sysadmin
from kairon.shared.constants import GPT3ResourceTypes
from kairon.shared.data.constant import DEFAULT_SYSTEM_PROMPT, DEFAULT_CONTEXT_PROMPT
from kairon.shared.llm.base import LLMBase
from typing import Text, Dict, List, Union

from kairon.shared.llm.clients.gpt3 import GPT3Resources
from kairon.shared.utils import Utility
import openai
from kairon.shared.data.data_objects import BotContent
from urllib.parse import urljoin
from kairon.exceptions import AppException
from loguru import logger as logging


class GPT3FAQEmbedding(LLMBase):

    __embedding__ = 1536

    def __init__(self, bot: Text):
        super().__init__(bot)
        self.db_url = Utility.environment['vector']['db']
        self.headers = {}
        if Utility.environment['vector']['key']:
            self.headers = {"api-key": Utility.environment['vector']['key']}
        self.suffix = "_faq_embd"
        self.cached_resp_suffix = "_cached_response_embd"
        self.vector_config = {'size': 1536, 'distance': 'Cosine'}
        self.api_key = Sysadmin.get_bot_secret(bot, BotSecretType.gpt_key.value, raise_err=True)
        self.client = GPT3Resources(self.api_key)
        self.__logs = []

    def train(self, *args, **kwargs) -> Dict:
        self.__create_collection__(self.bot + self.suffix)
        self.__create_collection__(self.bot + self.cached_resp_suffix)
        points = [{'id': content.vector_id,
                   'vector': self.__get_embedding(content.data),
                   'payload': {"content": content.data}} for content in BotContent.objects(bot=self.bot)]
        if points:
            self.__collection_upsert__(self.bot + self.suffix, {'points': points}, err_msg="Unable to train faq! contact support")
        return {"faq": points.__len__()}

    def predict(self, query: Text, *args, **kwargs) -> Dict:
        embeddings_created = False
        query_embedding = None
        try:
            query_embedding = self.__get_embedding(query)
            embeddings_created = True

            system_prompt = kwargs.pop('system_prompt', DEFAULT_SYSTEM_PROMPT)
            context_prompt = kwargs.pop('context_prompt', DEFAULT_CONTEXT_PROMPT)

            cached_response, match_found = self.__search_exact_match(query_embedding, **kwargs)
            if match_found:
                response = {"content": cached_response, "is_from_cache": True}
            else:
                context = self.__attach_similarity_prompt_if_enabled(query_embedding, context_prompt, **kwargs)
                response = {"content": self.__get_answer(query, system_prompt, context, **kwargs), "is_from_cache": False}
                self.__cache_response(query, query_embedding, response["content"], **kwargs)
        except openai.error.APIConnectionError as e:
            logging.exception(e)
            if embeddings_created:
                failure_stage = "Retrieving chat completion for the provided query."
            else:
                failure_stage = "Creating a new embedding for the provided query."
            self.__logs.append({'error': f"{failure_stage} {str(e)}"})
            response = {
                "content": self.__search_cache(query, query_embedding, err_msg=str(e), raise_err_if_not_exists=True, **kwargs),
                "is_from_cache": True, "is_failure": True, "exception": str(e)
            }
        except Exception as e:
            logging.exception(e)
            response = {
                "content": self.__search_cache(query, query_embedding, err_msg=str(e), raise_err_if_not_exists=True, **kwargs),
                "is_from_cache": True, "is_failure": True, "exception": str(e)
            }

        return response

    def __get_embedding(self, text: Text) -> List[float]:
        result, _ = self.client.invoke(GPT3ResourceTypes.embeddings.value, model="text-embedding-ada-002", input=text)
        return result

    def __get_answer(self, query, system_prompt: Text, context: Text, **kwargs):
        query_prompt = kwargs.get('query_prompt')
        use_query_prompt = kwargs.get('use_query_prompt')
        previous_bot_responses = kwargs.get('previous_bot_responses')
        hyperparameters = kwargs.get('hyperparameters', Utility.get_llm_hyperparameters())

        if use_query_prompt and query_prompt:
            query = self.__rephrase_query(query, system_prompt, query_prompt, hyperparameters=hyperparameters)
        messages = [
            {"role": "system", "content": system_prompt},
        ]
        if previous_bot_responses:
            messages.extend(previous_bot_responses)
        messages.append({"role": "user", "content": f"{context} \n Q: {query}\n A:"})

        completion, raw_response = self.client.invoke(GPT3ResourceTypes.chat_completion.value, messages=messages, **hyperparameters)
        self.__logs.append({'messages': messages, 'raw_completion_response': raw_response,
                          'type': 'answer_query', 'hyperparameters': hyperparameters})
        return completion

    def __rephrase_query(self, query, system_prompt: Text, query_prompt: Text, **kwargs):
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"{query_prompt}\n\n Q: {query}\n A:"}
        ]
        hyperparameters = kwargs.get('hyperparameters', Utility.get_llm_hyperparameters())

        completion, raw_response = self.client.invoke(GPT3ResourceTypes.chat_completion.value, messages=messages, **hyperparameters)
        self.__logs.append({'messages': messages, 'raw_completion_response': raw_response,
                            'type': 'rephrase_query', 'hyperparameters': hyperparameters})
        return completion

    def __create_collection__(self, collection_name: Text):
        Utility.execute_http_request(http_url=urljoin(self.db_url, f"/collections/{collection_name}"),
                                     request_method="DELETE",
                                     headers=self.headers,
                                     return_json=False)

        Utility.execute_http_request(http_url=urljoin(self.db_url, f"/collections/{collection_name}"),
                                     request_method="PUT",
                                     headers=self.headers,
                                     request_body={'name': collection_name, 'vectors': self.vector_config},
                                     return_json=False)

    def __collection_upsert__(self, collection_name: Text, data: Union[List, Dict], err_msg: Text, raise_err=True):
        response = Utility.execute_http_request(http_url=urljoin(self.db_url, f"/collections/{collection_name}/points"),
                                                request_method="PUT",
                                                headers=self.headers,
                                                request_body=data,
                                                return_json=True)
        if not response.get('result'):
            if "status" in response:
                logging.exception(response['status'].get('error'))
                if raise_err:
                    raise AppException(err_msg)

    def __collection_search__(self, collection_name: Text, vector: List, limit: int, score_threshold: float):
        response = Utility.execute_http_request(
            http_url=urljoin(self.db_url, f"/collections/{collection_name}/points/search"),
            request_method="POST",
            headers=self.headers,
            request_body={'vector': vector, 'limit': limit, 'with_payload': True, 'score_threshold': score_threshold},
            return_json=True)
        return response

    @property
    def logs(self):
        return self.__logs

    def __cache_response(self, query: Text, query_embedding: List, response: Text, **kwargs):
        enable_response_cache = kwargs.get("enable_response_cache", False)
        if enable_response_cache:
            vector_id = Utility.create_uuid_from_string(query)
            point = [{'id': vector_id, 'vector': query_embedding, 'payload': {"query": query, "response": response}}]
            self.__collection_upsert__(self.bot + self.cached_resp_suffix, {'points': point},
                                       err_msg="Unable to add response to cache!", raise_err=False)
            self.__logs.append({"message": "Response added to cache as `enable_response_cache` is enabled.", 'type': 'response_cached'})
        else:
            self.__logs.append({"message": "Skipping response caching as `enable_response_cache` is disabled."})

    def __search_cache(self, query: Text, query_embedding: List, **kwargs):
        search_result = None
        score_threshold = kwargs.get('similarity_threshold', 0.70)
        enable_response_cache = kwargs.get("enable_response_cache", False)
        err_msg = kwargs.get("err_msg")
        raise_err = kwargs.get("raise_err_if_not_exists", True)
        if enable_response_cache:
            if not query_embedding:
                query_embedding = self.__get_embedding(query)
            self.__logs.append({"message": "Searching recommendations from cache as `enable_response_cache` is enabled."})
            search_result = self.__collection_search__(self.bot + self.cached_resp_suffix, vector=query_embedding,
                                                       limit=3, score_threshold=score_threshold)
        else:
            self.__logs.append({"message": "Skipping recommendation search from cache as `enable_response_cache` is disabled."})

        if (not search_result or not search_result.get('result')) and raise_err:
            raise AppException(err_msg)

        return search_result

    def __search_exact_match(self, query_embedding: List, **kwargs):
        response = None
        is_match_found = False
        enable_response_cache = kwargs.get("enable_response_cache", False)
        if enable_response_cache:
            self.__logs.append({"message": "Searching exact match in cache as `enable_response_cache` is enabled."})
            search_result = self.__collection_search__(self.bot + self.cached_resp_suffix, vector=query_embedding,
                                                       limit=1, score_threshold=0.99)
            response = search_result["result"]
            if response:
                is_match_found = True
                response = search_result["result"][0]['payload']['response']
                self.__logs.append({"message": "Found exact query match in cache."})
        else:
            self.__logs.append({"message": "Skipping cache lookup as `enable_response_cache` is disabled."})
        return response, is_match_found

    def __attach_similarity_prompt_if_enabled(self, query_embedding, context_prompt, **kwargs):
        use_similarity_prompt = kwargs.pop('use_similarity_prompt')
        similarity_prompt_name = kwargs.pop('similarity_prompt_name')
        similarity_prompt_instructions = kwargs.pop('similarity_prompt_instructions')
        limit = kwargs.pop('top_results', 10)
        score_threshold = kwargs.pop('similarity_threshold', 0.70)
        if use_similarity_prompt:
            search_result = self.__collection_search__(self.bot + self.suffix, vector=query_embedding,
                                                       limit=limit, score_threshold=score_threshold)

            similarity_context = "\n".join([item['payload']['content'] for item in search_result['result']])
            similarity_context = f"{similarity_prompt_name}:\n{similarity_context}\n"
            similarity_context += f"Instructions on how to use {similarity_prompt_name}: {similarity_prompt_instructions}\n"
            context_prompt = f"{context_prompt}\n{similarity_context}"
        return context_prompt
