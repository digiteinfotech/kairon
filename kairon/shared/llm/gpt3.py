from kairon.shared.admin.constants import BotSecretType
from kairon.shared.admin.processor import Sysadmin
from kairon.shared.data.constant import DEFAULT_SYSTEM_PROMPT, DEFAULT_CONTEXT_PROMPT
from kairon.shared.llm.base import LLMBase
from typing import Text, Dict, List, Union
from kairon.shared.utils import Utility
import openai
from kairon.shared.data.data_objects import BotContent
from urllib.parse import urljoin
from kairon.exceptions import AppException
from loguru import logger as logging


class GPT3FAQEmbedding(LLMBase):
    __answer_params__ = {
        "temperature": 0.0,
        "max_tokens": 300,
        "model": "gpt-3.5-turbo",
    }

    __embedding__ = 1536

    def __init__(self, bot: Text):
        super().__init__(bot)
        self.db_url = Utility.environment['vector']['db']
        self.headers = {}
        if Utility.environment['vector']['key']:
            self.headers = {"api-key": Utility.environment['vector']['key']}
        self.suffix = "_faq_embd"
        self.vector_config = {'size': 1536, 'distance': 'Cosine'}
        self.api_key = Sysadmin.get_bot_secret(bot, BotSecretType.gpt_key.value, raise_err=True)

    def train(self, *args, **kwargs) -> Dict:
        self.__create_collection__(self.bot + self.suffix)
        points = [{'id': content.vector_id,
                   'vector': self.__get_embedding(content.data),
                   'payload': {"content": content.data}} for content in BotContent.objects(bot=self.bot)]
        if points:
            self.__collection_upsert__(self.bot + self.suffix, {'points': points})
        return {"faq": points.__len__()}

    def predict(self, query: Text, *args, **kwargs) -> Dict:
        query_embedding = self.__get_embedding(query)

        limit = kwargs.get('top_results', 10)
        score_threshold = kwargs.get('similarity_threshold', 0.70)
        system_prompt = kwargs.pop('system_prompt', DEFAULT_SYSTEM_PROMPT)
        context_prompt = kwargs.pop('context_prompt', DEFAULT_CONTEXT_PROMPT)

        search_result = self.__collection_search__(self.bot + self.suffix, vector=query_embedding,
                                                   limit=limit, score_threshold=score_threshold)
        context = "\n".join([item['payload']['content'] for item in search_result['result']])
        return {"content": self.__get_answer(query, context, system_prompt=system_prompt, context_prompt=context_prompt,
                                             **kwargs)}

    def __get_embedding(self, text: Text) -> List[float]:
        result = openai.Embedding.create(
            api_key=self.api_key,
            model="text-embedding-ada-002",
            input=text
        )
        return result.to_dict_recursive()["data"][0]["embedding"]

    def __get_answer(self, query, context, system_prompt: Text, context_prompt: Text, **kwargs):
        query_prompt = kwargs.get('query_prompt')
        use_query_prompt = kwargs.get('use_query_prompt')
        previous_bot_responses = kwargs.get('previous_bot_responses')
        if use_query_prompt and query_prompt:
            query = self.__rephrase_query(query, system_prompt, query_prompt)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"{context_prompt} \n\nContext:\n{context}\n\n Q: {query}\n A:"}
        ]
        if previous_bot_responses:
            messages.append({"role": "assistant", "content": f"{previous_bot_responses}"})

        completion = openai.ChatCompletion.create(
            api_key=self.api_key,
            messages=messages,
            **self.__answer_params__
        )

        response = ' '.join([choice['message']['content'] for choice in completion.to_dict_recursive()['choices']])
        return response

    def __rephrase_query(self, query, system_prompt: Text, query_prompt: Text):
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"{query_prompt}\n\n Q: {query}\n A:"}
        ]
        completion = openai.ChatCompletion.create(
            api_key=self.api_key,
            messages=messages,
            **self.__answer_params__
        )
        response = ' '.join([choice['message']['content'] for choice in completion.to_dict_recursive()['choices']])
        return response

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

    def __collection_upsert__(self, collection_name: Text, data: Union[List, Dict]):
        response = Utility.execute_http_request(http_url=urljoin(self.db_url, f"/collections/{collection_name}/points"),
                                                request_method="PUT",
                                                headers=self.headers,
                                                request_body=data,
                                                return_json=True)
        if not response.get('result'):
            if "status" in response:
                logging.exception(response['status'].get('error'))
                raise AppException("Unable to train faq! contact support")

    def __collection_search__(self, collection_name: Text, vector: List, limit: int, score_threshold: float):
        response = Utility.execute_http_request(
            http_url=urljoin(self.db_url, f"/collections/{collection_name}/points/search"),
            request_method="POST",
            headers=self.headers,
            request_body={'vector': vector, 'limit': limit, 'with_payload': True, 'score_threshold': score_threshold},
            return_json=True)
        return response