from kairon.shared.llm.base import LLMBase
from typing import Text, Dict, List, Union
from kairon.shared.utils import Utility
import openai
from kairon.shared.data.data_objects import BotContent
from urllib.parse import urljoin


class GPT3FAQEmbedding(LLMBase):
    __answer_command__ = "Answer the question as truthfully as possible using the provided context, always add the link from the document in the answer if available, and if the answer is not contained within the text below, simply state 'I don't know.'"
    __answer_params__ = {
        "temperature": 0.0,
        "max_tokens": 300,
        "model": "text-davinci-003",
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
        self.api_key = Utility.environment['llm']['api_key']

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

        search_result = self.__collection_search__(self.bot + self.suffix, vector=query_embedding)
        context = "\n".join([item['payload']['content'] for item in search_result['result']])
        return {"content": self.__get_answer(query, context)}

    def __get_embedding(self, text: Text) -> List[float]:
        result = openai.Embedding.create(
            api_key=self.api_key,
            model="text-embedding-ada-002",
            input=text
        )
        return result.to_dict_recursive()["data"][0]["embedding"]

    def __get_answer(self, query, context):
        completion = openai.Completion.create(
            api_key=self.api_key,
            prompt=f"{self.__answer_command__} \n\nContext:\n{context}\n\n Q: {query}\n A:",
            **self.__answer_params__
        )
        response = ' '.join([choice['text'] for choice in completion.to_dict_recursive()['choices']])
        return response

    def __create_collection__(self, collection_name: Text):
        col_info = Utility.execute_http_request(http_url=urljoin(self.db_url, f"/collections/{collection_name}"),
                                                request_method="GET",
                                                headers=self.headers,
                                                return_json=True)
        if not col_info.get('result'):
            Utility.execute_http_request(http_url=urljoin(self.db_url, f"/collections/{collection_name}"),
                                         request_method="PUT",
                                         headers=self.headers,
                                         request_body={'name': collection_name, 'vectors': self.vector_config},
                                         return_json=True)

    def __collection_upsert__(self, collection_name: Text, data: Union[List, Dict]):
        Utility.execute_http_request(http_url=urljoin(self.db_url, f"/collections/{collection_name}/points"),
                                     request_method="PUT",
                                     headers=self.headers,
                                     request_body=data,
                                     return_json=True)

    def __collection_search__(self, collection_name: Text, vector: List):
        response = Utility.execute_http_request(http_url=urljoin(self.db_url, f"/collections/{collection_name}/points/search"),
                                     request_method="POST",
                                     headers=self.headers,
                                     request_body={'vector': vector, 'limit': 10, 'with_payload': True, 'score_threshold': 0.70},
                                     return_json=True)
        return response
