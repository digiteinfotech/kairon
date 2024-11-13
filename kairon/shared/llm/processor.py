import time
import urllib.parse
from secrets import randbelow, choice
from typing import Text, Dict, List, Tuple, Union
from urllib.parse import urljoin

import litellm
from loguru import logger as logging
from mongoengine.base import BaseList
from tiktoken import get_encoding
from tqdm import tqdm

from kairon.exceptions import AppException
from kairon.shared.actions.utils import ActionUtility
from kairon.shared.admin.data_objects import LLMSecret
from kairon.shared.admin.processor import Sysadmin
from kairon.shared.cognition.data_objects import CognitionData
from kairon.shared.cognition.processor import CognitionDataProcessor
from kairon.shared.data.constant import DEFAULT_LLM
from kairon.shared.data.constant import DEFAULT_SYSTEM_PROMPT, DEFAULT_CONTEXT_PROMPT
from kairon.shared.llm.base import LLMBase
from kairon.shared.llm.data_objects import LLMLogs
from kairon.shared.llm.logger import LiteLLMLogger
from kairon.shared.models import CognitionDataType
from kairon.shared.rest_client import AioRestClient
from kairon.shared.utils import Utility
from http import HTTPStatus

litellm.callbacks = [LiteLLMLogger()]


class LLMProcessor(LLMBase):
    __embedding__ = 1536

    def __init__(self, bot: Text, llm_type: str):
        super().__init__(bot)
        self.db_url = Utility.environment['vector']['db']
        self.headers = {}
        if Utility.environment['vector']['key']:
            self.headers = {"api-key": Utility.environment['vector']['key']}
        self.suffix = "_faq_embd"
        self.llm_type = llm_type
        self.vector_config = {'size': self.__embedding__, 'distance': 'Cosine'}
        self.llm_secret = Sysadmin.get_llm_secret(llm_type, bot)

        if llm_type != DEFAULT_LLM:
            self.llm_secret_embedding = Sysadmin.get_llm_secret(DEFAULT_LLM, bot)
        else:
            self.llm_secret_embedding = self.llm_secret

        self.tokenizer = get_encoding("cl100k_base")
        self.EMBEDDING_CTX_LENGTH = 8191
        self.__logs = []

    async def train(self, user, *args, **kwargs) -> Dict:
        invocation = kwargs.pop('invocation', None)
        await self.__delete_collections()
        count = 0
        processor = CognitionDataProcessor()
        batch_size = 100

        collections_data = CognitionData.objects(bot=self.bot)
        collection_groups = {}
        for content in collections_data:
            content_dict = content.to_mongo()
            collection_name = content_dict.get('collection') or ""
            if collection_name not in collection_groups:
                collection_groups[collection_name] = []
            collection_groups[collection_name].append(content_dict)

        for collection_name, contents in collection_groups.items():
            collection = f"{self.bot}_{collection_name}{self.suffix}" if collection_name else f"{self.bot}{self.suffix}"
            await self.__create_collection__(collection)

            for i in tqdm(range(0, len(contents), batch_size), desc="Training FAQ"):
                batch_contents = contents[i:i + batch_size]

                embedding_payloads = []
                search_payloads = []
                vector_ids = []

                for content in batch_contents:
                    if content['content_type'] == CognitionDataType.json.value:
                        metadata = processor.find_matching_metadata(self.bot, content['data'],
                                                                    content.get('collection'))
                        search_payload, embedding_payload = Utility.retrieve_search_payload_and_embedding_payload(
                            content['data'], metadata)
                    else:
                        search_payload, embedding_payload = {'content': content["data"]}, content["data"]

                    embedding_payloads.append(embedding_payload)
                    search_payloads.append(search_payload)
                    vector_ids.append(content['vector_id'])

                embeddings = await self.get_embedding(embedding_payloads, user, invocation=invocation)

                points = [{'id': vector_ids[idx], 'vector': embeddings[idx], 'payload': search_payloads[idx]}
                          for idx in range(len(vector_ids))]
                await self.__collection_upsert__(collection, {'points': points},
                                                 err_msg="Unable to train FAQ! Contact support")
                count += len(batch_contents)

        return {"faq": count}

    async def predict(self, query: Text, user, *args, **kwargs) -> Tuple:
        start_time = time.time()
        embeddings_created = False
        invocation = kwargs.pop('invocation', None)
        try:
            query_embedding = await self.get_embedding(query, user, invocation=invocation)
            embeddings_created = True

            system_prompt = kwargs.pop('system_prompt', DEFAULT_SYSTEM_PROMPT)
            context_prompt = kwargs.pop('context_prompt', DEFAULT_CONTEXT_PROMPT)

            context = await self.__attach_similarity_prompt_if_enabled(query_embedding, context_prompt, **kwargs)
            answer = await self.__get_answer(query, system_prompt, context, user, invocation=invocation,**kwargs)
            response = {"content": answer}
        except Exception as e:
            logging.exception(e)
            if embeddings_created:
                failure_stage = "Retrieving chat completion for the provided query."
            else:
                failure_stage = "Creating a new embedding for the provided query."
            self.__logs.append({'error': f"{failure_stage} {str(e)}"})
            response = {"is_failure": True, "exception": str(e), "content": None}

        end_time = time.time()
        elapsed_time = end_time - start_time
        return response, elapsed_time

    def truncate_text(self, texts: List[Text]) -> List[Text]:
        """
        Truncate multiple texts to 8191 tokens for openai
        """
        truncated_texts = []

        for text in texts:
            tokens = self.tokenizer.encode(text)[:self.EMBEDDING_CTX_LENGTH]
            truncated_texts.append(self.tokenizer.decode(tokens))

        return truncated_texts

    async def get_embedding(self, texts: Union[Text, List[Text]], user, **kwargs):
        """
        Get embeddings for a batch of texts.
        """
        is_single_text = isinstance(texts, str)
        if is_single_text:
            texts = [texts]

        truncated_texts = self.truncate_text(texts)

        result = await litellm.aembedding(
            model="text-embedding-3-small",
            input=truncated_texts,
            metadata={'user': user, 'bot': self.bot, 'invocation': kwargs.get("invocation")},
            api_key=self.llm_secret_embedding.get('api_key'),
            num_retries=3
        )

        embeddings = [embedding["embedding"] for embedding in result["data"]]

        if is_single_text:
            return embeddings[0]

        return embeddings

    async def __parse_completion_response(self, response, **kwargs):
        if kwargs.get("stream"):
            formatted_response = ''
            msg_choice = randbelow(kwargs.get("n", 1))
            if response["choices"][0].get("index") == msg_choice and response["choices"][0]['delta'].get('content'):
                formatted_response = f"{response['choices'][0]['delta']['content']}"
        else:
            msg_choice = choice(response['choices'])
            formatted_response = msg_choice['message']['content']
        return formatted_response

    async def __get_completion(self, messages, hyperparameters, user, **kwargs):
        body = {
            'messages': messages,
            'hyperparameters': hyperparameters,
            'user': user,
            'invocation': kwargs.get("invocation")
        }

        timeout = Utility.environment['llm'].get('request_timeout', 30)
        http_response, status_code, elapsed_time, _ = await ActionUtility.execute_request_async(http_url=f"{Utility.environment['llm']['url']}/{urllib.parse.quote(self.bot)}/completion/{self.llm_type}",
                                                                     request_method="POST",
                                                                     request_body=body,
                                                                     timeout=timeout)

        logging.info(f"LLM request completed in {elapsed_time} for bot: {self.bot}")
        if status_code not in [200, 201, 202, 203, 204]:
            raise Exception(HTTPStatus(status_code).phrase)

        if isinstance(http_response, dict):
            return http_response.get("formatted_response"), http_response.get("response")
        else:
            return http_response, http_response


    async def __get_answer(self, query, system_prompt: Text, context: Text, user, **kwargs):
        use_query_prompt = False
        query_prompt = ''
        invocation = kwargs.pop('invocation')
        if kwargs.get('query_prompt', {}):
            query_prompt_dict = kwargs.pop('query_prompt')
            query_prompt = query_prompt_dict.get('query_prompt', '')
            use_query_prompt = query_prompt_dict.get('use_query_prompt')
        previous_bot_responses = kwargs.get('previous_bot_responses')
        hyperparameters = kwargs['hyperparameters']
        instructions = kwargs.get('instructions', [])
        instructions = '\n'.join(instructions)

        if use_query_prompt and query_prompt:
            query = await self.__rephrase_query(query, system_prompt, query_prompt,
                                                hyperparameters=hyperparameters,
                                                user=user,
                                                invocation=f"{invocation}_rephrase")
        messages = [
            {"role": "system", "content": system_prompt},
        ]
        if previous_bot_responses:
            messages.extend(previous_bot_responses)
        messages.append({"role": "user", "content": f"{context} \n{instructions} \nQ: {query} \nA:"}) if instructions \
            else messages.append({"role": "user", "content": f"{context} \nQ: {query} \nA:"})
        completion, raw_response = await self.__get_completion(messages=messages,
                                                               hyperparameters=hyperparameters,
                                                               user=user,
                                                               invocation=invocation)
        self.__logs.append({'messages': messages, 'raw_completion_response': raw_response,
                            'type': 'answer_query', 'hyperparameters': hyperparameters})
        return completion

    async def __rephrase_query(self, query, system_prompt: Text, query_prompt: Text, user, **kwargs):
        invocation = kwargs.pop('invocation')
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"{query_prompt}\n\n Q: {query}\n A:"}
        ]
        hyperparameters = kwargs['hyperparameters']

        completion, raw_response = await self.__get_completion(messages=messages,
                                                               hyperparameters=hyperparameters,
                                                               user=user,
                                                               invocation=invocation)
        self.__logs.append({'messages': messages, 'raw_completion_response': raw_response,
                            'type': 'rephrase_query', 'hyperparameters': hyperparameters})
        return completion

    async def __delete_collections(self):
        client = AioRestClient(False)
        try:
            response = await client.request(http_url=urljoin(self.db_url, "/collections"),
                                            request_method="GET",
                                            headers=self.headers,
                                            timeout=5)
            if response.get('result'):
                for collection in response['result'].get('collections') or []:
                    if collection['name'].startswith(self.bot):
                        await client.request(http_url=urljoin(self.db_url, f"/collections/{collection['name']}"),
                                             request_method="DELETE",
                                             headers=self.headers,
                                             return_json=False,
                                             timeout=5)
        finally:
            await client.cleanup()

    async def __create_collection__(self, collection_name: Text):
        await AioRestClient().request(http_url=urljoin(self.db_url, f"/collections/{collection_name}"),
                                      request_method="PUT",
                                      headers=self.headers,
                                      request_body={'name': collection_name, 'vectors': self.vector_config},
                                      return_json=False,
                                      timeout=5)

    async def __collection_upsert__(self, collection_name: Text, data: Dict, err_msg: Text, raise_err=True):
        client = AioRestClient()
        response = await client.request(http_url=urljoin(self.db_url, f"/collections/{collection_name}/points"),
                                        request_method="PUT",
                                        headers=self.headers,
                                        request_body=data,
                                        return_json=True,
                                        timeout=5)
        if not response.get('result'):
            if "status" in response:
                logging.exception(response['status'].get('error'))
                if raise_err:
                    raise AppException(err_msg)

    async def __collection_search__(self, collection_name: Text, vector: List, limit: int, score_threshold: float):
        client = AioRestClient()
        response = await client.request(
            http_url=urljoin(self.db_url, f"/collections/{collection_name}/points/search"),
            request_method="POST",
            headers=self.headers,
            request_body={'vector': vector, 'limit': limit, 'with_payload': True, 'score_threshold': score_threshold},
            return_json=True,
            timeout=5)
        return response

    @property
    def logs(self):
        return self.__logs

    async def __attach_similarity_prompt_if_enabled(self, query_embedding, context_prompt, **kwargs):
        similarity_prompt = kwargs.pop('similarity_prompt')
        for similarity_context_prompt in similarity_prompt:
            use_similarity_prompt = similarity_context_prompt.get('use_similarity_prompt')
            similarity_prompt_name = similarity_context_prompt.get('similarity_prompt_name')
            similarity_prompt_instructions = similarity_context_prompt.get('similarity_prompt_instructions')
            limit = similarity_context_prompt.get('top_results', 10)
            score_threshold = similarity_context_prompt.get('similarity_threshold', 0.70)
            extracted_values = []
            if use_similarity_prompt:
                if similarity_context_prompt.get('collection') == 'default':
                    collection_name = f"{self.bot}{self.suffix}"
                else:
                    collection_name = f"{self.bot}_{similarity_context_prompt.get('collection')}{self.suffix}"
                search_result = await self.__collection_search__(collection_name, vector=query_embedding, limit=limit,
                                                                 score_threshold=score_threshold)

                for entry in search_result['result']:
                    if 'content' not in entry['payload']:
                        extracted_payload = {}
                        for key, value in entry['payload'].items():
                            if key != 'collection_name':
                                extracted_payload[key] = value
                        extracted_values.append(extracted_payload)
                    else:
                        extracted_values.append(entry['payload']['content'])
                if extracted_values:
                    similarity_context = f"Instructions on how to use {similarity_prompt_name}:\n{extracted_values}\n{similarity_prompt_instructions}\n"
                    context_prompt = f"{context_prompt}\n{similarity_context}"
        return context_prompt

    @staticmethod
    def get_logs(bot: str, start_idx: int = 0, page_size: int = 10):
        """
        Get all logs for data importer event.
        @param bot: bot id.
        @param start_idx: start index
        @param page_size: page size
        @return: list of logs.
        """
        for log in LLMLogs.objects(metadata__bot=bot).order_by("-start_time").skip(start_idx).limit(page_size):
            llm_log = log.to_mongo().to_dict()
            llm_log.pop('_id')
            yield llm_log

    @staticmethod
    def get_row_count(bot: str):
        """
        Gets the count of rows in a LLMLogs for a particular bot.
        :param bot: bot id
        :return: Count of rows
        """
        return LLMLogs.objects(metadata__bot=bot).count()

    @staticmethod
    def fetch_llm_metadata(bot: str):
        """
        Fetches the llm_type and corresponding models for a particular bot.
        :param bot: bot id
        :return: dictionary where each key is a llm_type and the value is a list of models.
        """
        metadata = Utility.llm_metadata
        llm_types = metadata.keys()

        for llm_type in llm_types:
            secret = LLMSecret.objects(bot=bot, llm_type=llm_type).first()
            if not secret:
                secret = LLMSecret.objects(llm_type=llm_type, bot__exists=False).first()

            if secret:
                models = list(secret.models) if isinstance(secret.models, BaseList) else secret.models
            else:
                models = []

            metadata[llm_type]['properties']['model']['enum'] = models

        return metadata