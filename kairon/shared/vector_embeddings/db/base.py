from abc import ABC, abstractmethod
from typing import Dict, Text

from kairon.exceptions import AppException
from kairon.shared.actions.models import DbActionOperationType


class DatabaseBase(ABC):

    @abstractmethod
    async def perform_operation(self, request_body: Dict, user: str, **kwargs):
        raise NotImplementedError("Provider not implemented")
