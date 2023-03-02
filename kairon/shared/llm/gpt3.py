from kairon.shared.llm.base import LLMBase
from typing import Text, Dict, List
from kairon.shared.utils import Utility
import openai
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from kairon.shared.data.data_objects import BotContent


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
        self.db_client = QdrantClient(
            **{'url': Utility.environment['vector']['db'], 'api_key': Utility.environment['vector']['key']})
        self.suffix = "_faq_embd"
        self.vector_config = VectorParams(size=1536, distance=Distance.COSINE)
        self.api_key = Utility.environment['llm']['api_key']

    def train(self, *args, **kwargs) -> Dict:
        try:
            self.db_client.get_collection(collection_name=self.bot + self.suffix)
        except:
            self.db_client.recreate_collection(
                collection_name=self.bot + self.suffix,
                vectors_config=self.vector_config
            )
        points = [PointStruct(id=id.__str__(),
                              vector=self.__get_embedding(content.data),
                              payload={"content": content.data}) for content in BotContent.objects(bot=self.bot)]
        if points:
            self.db_client.upsert(
                collection_name=self.bot + self.suffix,
                points=points
            )
        return {"faq": points.__len__()}

    def predict(self, query: Text, *args, **kwargs) -> Dict:
        query_embedding = self.__get_embedding(query)

        search_result = self.db_client.search(
            collection_name=self.bot + self.suffix,
            query_vector=query_embedding,
            with_payload=True,
            limit=10
        )
        context = "\n".join([score_point.payload['content'] for score_point in search_result])
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
