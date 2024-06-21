from abc import ABC, abstractmethod
from typing import Dict, Text

from kairon.exceptions import AppException
from kairon.shared.actions.models import DbActionOperationType


class VectorEmbeddingsDbBase(ABC):

    @abstractmethod
    async def embedding_search(self, request_body: Dict, **kwargs):
        raise NotImplementedError("Provider not implemented")

    @abstractmethod
    async def payload_search(self, request_body: Dict, **kwargs):
        raise NotImplementedError("Provider not implemented")

    async def perform_operation(self, op_type: Text, request_body: Dict, **kwargs):
        supported_ops = {DbActionOperationType.payload_search.value: self.payload_search,
                         DbActionOperationType.embedding_search.value: self.embedding_search}
        if op_type not in supported_ops.keys():
            raise AppException("Operation type not supported")
        return await supported_ops[op_type](request_body, **kwargs)
