from abc import ABC, abstractmethod
from typing import Dict, Text

from kairon.exceptions import AppException
from kairon.shared.actions.models import VectorDbOperationClass


class VectorEmbeddingsDbBase(ABC):

    @abstractmethod
    def embedding_search(self, request_body: Dict):
        raise NotImplementedError("Provider not implemented")

    @abstractmethod
    def payload_search(self, request_body: Dict):
        raise NotImplementedError("Provider not implemented")

    def perform_operation(self, op_type: Text, request_body: Dict):
        supported_ops = {VectorDbOperationClass.payload_search.value: self.payload_search,
                         VectorDbOperationClass.embedding_search.value: self.embedding_search}
        if op_type not in supported_ops.keys():
            raise AppException("Operation type not supported")
        return supported_ops[op_type](request_body)
