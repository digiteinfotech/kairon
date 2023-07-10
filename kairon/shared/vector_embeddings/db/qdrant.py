from abc import ABC
from typing import Text, Dict
from urllib.parse import urljoin

from kairon import Utility
from kairon.shared.actions.utils import ActionUtility
from kairon.shared.vector_embeddings.db.base import VectorEmbeddingsDbBase


class Qdrant(VectorEmbeddingsDbBase, ABC):

    def __init__(self, collection_name: Text, db_url: Text = None):
        self.collection_name = collection_name
        self.db_url = db_url
        if not self.db_url:
            self.db_url = Utility.environment['vector']['db']

    def embedding_search(self, request_body: Dict):
        url = urljoin(self.db_url, f"/collections/{self.collection_name}/points")
        embedding_search_result = ActionUtility.execute_http_request(http_url=url,
                                                                     request_method='POST',
                                                                     request_body=request_body)
        return embedding_search_result

    def payload_search(self, request_body: Dict):
        url = urljoin(self.db_url, f"/collections/{self.collection_name}/points/scroll")
        payload_filter_result = ActionUtility.execute_http_request(http_url=url,
                                                                   request_method='POST',
                                                                   request_body=request_body)
        return payload_filter_result
