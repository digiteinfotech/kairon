from typing import Text, Dict, List
from urllib.parse import urljoin

import openai
from loguru import logger as logging
from tiktoken import get_encoding
from tqdm import tqdm

from kairon.exceptions import AppException
from kairon.shared.admin.constants import BotSecretType
from kairon.shared.admin.processor import Sysadmin
from kairon.shared.cognition.data_objects import CognitionData
from kairon.shared.cognition.processor import CognitionDataProcessor
from kairon.shared.constants import GPT3ResourceTypes
from kairon.shared.data.constant import DEFAULT_SYSTEM_PROMPT, DEFAULT_CONTEXT_PROMPT
from kairon.shared.llm.base import LLMBase
from kairon.shared.llm.clients.factory import LLMClientFactory
from kairon.shared.models import CognitionDataType
from kairon.shared.rest_client import AioRestClient
from kairon.shared.utils import Utility


class GPT3FAQEmbedding(LLMBase):
    __embedding__ = 1536

    def __init__(self, bot: Text, llm_settings: dict):
        super().__init__(bot)
        self.db_url = Utility.environment['vector']['db']
        self.headers = {}
        if Utility.environment['vector']['key']:
            self.headers = {"api-key": Utility.environment['vector']['key']}
        self.suffix = "_faq_embd"
        self.vector_config = {'size': 1536, 'distance': 'Cosine'}
        self.llm_settings = llm_settings
        self.api_key = Sysadmin.get_bot_secret(bot, BotSecretType.gpt_key.value, raise_err=True)
        self.client = LLMClientFactory.get_resource_provider(llm_settings["provider"])(self.api_key,
                                                                                       **self.llm_settings)
        self.tokenizer = get_encoding("cl100k_base")
        self.EMBEDDING_CTX_LENGTH = 8191
        self.__logs = []

    async def train(self, *args, **kwargs) -> Dict:
        await self.__delete_collections()
        count = 0
        processor = CognitionDataProcessor()
        collection_groups = list(CognitionData.objects.aggregate([
            {'$match': {'bot': self.bot}},
            {'$group': {'_id': "$collection", 'content': {'$push': "$$ROOT"}}},
            {'$project': {'collection': "$_id", 'content': 1, '_id': 0}}
        ]))
        for collections in collection_groups:
            collection = f"{self.bot}_{collections['collection']}{self.suffix}" if collections[
                'collection'] else f"{self.bot}{self.suffix}"
            await self.__create_collection__(collection)
            for content in tqdm(collections['content'], desc="Training FAQ"):
                if content['content_type'] == CognitionDataType.json.value:
                    metadata = processor.find_matching_metadata(self.bot, content['data'], content.get('collection'))
                    search_payload, embedding_payload = Utility.retrieve_search_payload_and_embedding_payload(
                        content['data'], metadata)
                else:
                    search_payload, embedding_payload = {'content': content["data"]}, content["data"]
                search_payload['collection_name'] = collection
                embeddings = await self.__get_embedding(embedding_payload)
                points = [{'id': content['vector_id'], 'vector': embeddings, 'payload': search_payload}]
                await self.__collection_upsert__(collection, {'points': points},
                                                 err_msg="Unable to train FAQ! Contact support")
                count += 1
        return {"faq": count}

    async def predict(self, query: Text, *args, **kwargs) -> Dict:
        embeddings_created = False
        try:
            query_embedding = await self.__get_embedding(query)
            embeddings_created = True

            system_prompt = kwargs.pop('system_prompt', DEFAULT_SYSTEM_PROMPT)
            context_prompt = kwargs.pop('context_prompt', DEFAULT_CONTEXT_PROMPT)

            context = await self.__attach_similarity_prompt_if_enabled(query_embedding, context_prompt, **kwargs)
            answer = await self.__get_answer(query, system_prompt, context, **kwargs)
            response = {"content": answer}
        except openai.error.APIConnectionError as e:
            logging.exception(e)
            if embeddings_created:
                failure_stage = "Retrieving chat completion for the provided query."
            else:
                failure_stage = "Creating a new embedding for the provided query."
            self.__logs.append({'error': f"{failure_stage} {str(e)}"})
            response = {"is_failure": True, "exception": str(e), "content": None}
        except Exception as e:
            logging.exception(e)
            response = {"is_failure": True, "exception": str(e), "content": None}

        return response

    def truncate_text(self, text: Text) -> Text:
        """
        Truncate text to 8191 tokens for openai
        """
        tokens = self.tokenizer.encode(text)[:self.EMBEDDING_CTX_LENGTH]
        return self.tokenizer.decode(tokens)

    async def __get_embedding(self, text: Text) -> List[float]:
        truncated_text = self.truncate_text(text)
        result, _ = await self.client.invoke(GPT3ResourceTypes.embeddings.value, model="text-embedding-ada-002",
                                             input=truncated_text)
        return result

    async def __get_answer(self, query, system_prompt: Text, context: Text, **kwargs):
        use_query_prompt = False
        query_prompt = ''
        if kwargs.get('query_prompt', {}):
            query_prompt_dict = kwargs.pop('query_prompt')
            query_prompt = query_prompt_dict.get('query_prompt', '')
            use_query_prompt = query_prompt_dict.get('use_query_prompt')

        previous_bot_responses = kwargs.get('previous_bot_responses')
        hyperparameters = kwargs.get('hyperparameters', Utility.get_llm_hyperparameters())
        instructions = kwargs.get('instructions', [])
        instructions = '\n'.join(instructions)
        if use_query_prompt and query_prompt:
            query = await self.__rephrase_query(query, system_prompt, query_prompt, hyperparameters=hyperparameters)
        messages = [
            {"role": "system", "content": system_prompt},
        ]
        if previous_bot_responses:
            messages.extend(previous_bot_responses)
        messages.append({"role": "user", "content": f"{context} \n{instructions} \nQ: {query} \nA:"}) if instructions \
            else messages.append({"role": "user", "content": f"{context} \nQ: {query} \nA:"})

        completion, raw_response = await self.client.invoke(GPT3ResourceTypes.chat_completion.value, messages=messages,
                                                            **hyperparameters)
        self.__logs.append({'messages': messages, 'raw_completion_response': raw_response,
                            'type': 'answer_query', 'hyperparameters': hyperparameters})
        return completion

    async def __rephrase_query(self, query, system_prompt: Text, query_prompt: Text, **kwargs):
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"{query_prompt}\n\n Q: {query}\n A:"}
        ]
        hyperparameters = kwargs.get('hyperparameters', Utility.get_llm_hyperparameters())

        completion, raw_response = await self.client.invoke(GPT3ResourceTypes.chat_completion.value, messages=messages,
                                                            **hyperparameters)
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
            similarity_context = ""
            extracted_values = []
            if use_similarity_prompt:
                collection_name = f"{self.bot}_{similarity_context_prompt.get('collection')}{self.suffix}" if similarity_context_prompt.get(
                    'collection') else f"{self.bot}{self.suffix}"
                search_result = await self.__collection_search__(collection_name, vector=query_embedding, limit=limit,
                                                                 score_threshold=score_threshold)

                for entry in search_result['result']:
                    extracted_payload = {}
                    if 'content' not in entry['payload']:
                        for key, value in entry['payload'].items():
                            if key != 'collection_name':
                                extracted_payload[key] = value
                        extracted_values.append(extracted_payload)
                        similarity_context = f"{similarity_prompt_name}:\n{extracted_values}\n"
                    else:
                        similarity_context = entry['payload']['content']
                        similarity_context = f"{similarity_prompt_name}:\n{similarity_context}\n"
                    if similarity_prompt_instructions:
                        similarity_context += f"Instructions on how to use {similarity_prompt_name}: {similarity_prompt_instructions}\n"
                context_prompt = f"{context_prompt}\n{similarity_context}"
        return context_prompt