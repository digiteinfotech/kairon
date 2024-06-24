from abc import ABC
from typing import Text, Dict, List
from urllib.parse import urljoin
from tiktoken import get_encoding

from kairon import Utility
from kairon.shared.actions.utils import ActionUtility
from kairon.shared.admin.constants import BotSecretType
from kairon.shared.admin.processor import Sysadmin
from kairon.shared.constants import GPT3ResourceTypes
from kairon.shared.llm.processor import LLMProcessor
from kairon.shared.vector_embeddings.db.base import VectorEmbeddingsDbBase


class Qdrant(VectorEmbeddingsDbBase, ABC):
    __embedding__ = 1536

    def __init__(self, bot: Text, collection_name: Text, llm_settings: dict, db_url: Text = None):
        self.bot = bot
        self.collection_name = collection_name
        self.db_url = db_url
        if not self.db_url:
            self.db_url = Utility.environment['vector']['db']
        self.headers = {}
        if Utility.environment['vector']['key']:
            self.headers = {"api-key": Utility.environment['vector']['key']}
        self.llm_settings = llm_settings
        self.llm = LLMProcessor(self.bot)
        self.tokenizer = get_encoding("cl100k_base")
        self.EMBEDDING_CTX_LENGTH = 8191

    async def __get_embedding(self, text: Text, user: str, **kwargs) -> List[float]:
        return await self.llm.get_embedding(text, user=user)

    async def embedding_search(self, request_body: Dict, user: str, **kwargs):
        url = urljoin(self.db_url, f"/collections/{self.collection_name}/points")
        if request_body.get("text"):
            url = urljoin(self.db_url, f"/collections/{self.collection_name}/points/search")
            user_msg = request_body.get("text")
            vector = await self.__get_embedding(user_msg, user, **kwargs)
            request_body = {'vector': vector, 'limit': 10, 'with_payload': True, 'score_threshold': 0.70}
        embedding_search_result = ActionUtility.execute_http_request(http_url=url,
                                                                     request_method='POST',
                                                                     headers=self.headers,
                                                                     request_body=request_body)
        return embedding_search_result

    async def payload_search(self, request_body: Dict, user, **kwargs):
        url = urljoin(self.db_url, f"/collections/{self.collection_name}/points/scroll")
        payload_filter_result = ActionUtility.execute_http_request(http_url=url,
                                                                   request_method='POST',
                                                                   request_body=request_body)
        return payload_filter_result
