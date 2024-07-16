from abc import ABC
from typing import Text, Dict, List
from urllib.parse import urljoin

from kairon import Utility
from kairon.shared.actions.utils import ActionUtility
from kairon.shared.llm.processor import LLMProcessor
from kairon.shared.data.constant import DEFAULT_LLM
from kairon.shared.vector_embeddings.db.base import DatabaseBase
from kairon.shared.actions.models import DbActionOperationType
from kairon.shared.actions.exception import ActionFailure


class Qdrant(DatabaseBase, ABC):
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
        self.llm = LLMProcessor(self.bot, DEFAULT_LLM)
        self.EMBEDDING_CTX_LENGTH = 8191

    async def __get_embedding(self, text: Text, user: str, **kwargs) -> List[float]:
        return await self.llm.get_embedding(text, user=user, invocation='db_action_qdrant')

    async def perform_operation(self, data: Dict, user: str, **kwargs):
        request = {}
        url = urljoin(self.db_url, f"/collections/{self.collection_name}/points/query")
        if DbActionOperationType.embedding_search in data:
            user_msg = data.get(DbActionOperationType.embedding_search)
            if user_msg and isinstance(user_msg, str):
                vector = await self.__get_embedding(user_msg, user, **kwargs)
                request['query'] = vector
                request['score_threshold'] = 0.70

        if DbActionOperationType.payload_search in data:
            payload = data.get(DbActionOperationType.payload_search)
            if payload:
                request.update(**payload)

        if request:
            request.update(**{'with_payload': True, 'limit': 10})
            result = ActionUtility.execute_http_request(http_url=url,
                                                        request_method='POST',
                                                        request_body=request)
        else:
            raise ActionFailure('No Operation to perform')
        return result
