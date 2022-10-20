from abc import ABC, abstractmethod
from typing import List, Tuple, Text
from numpy import ndarray
from transformers.tokenization_utils import PreTrainedTokenizer


class BaseModel(ABC):

    @abstractmethod
    def preprocessor(self, token_ids: List[int], **kwargs) -> List[int]:
        raise NotImplementedError()

    @abstractmethod
    def post_processor(self, sequence_embeddings: ndarray, **kwargs) -> Tuple[ndarray, ndarray]:
        raise NotImplementedError()

    @abstractmethod
    def tokens_cleaner(self, token_ids: List[int], token_strings: List[Text], **kwargs) -> Tuple[List[int], List[Text]]:
        raise NotImplementedError()

    @staticmethod
    def get_max_sequence_length(model_weights: str, tokenizer: PreTrainedTokenizer):
        if model_weights.startswith("sentence-transformers"):
            MAX_SEQUENCE_LENGTHS = 128
        else:
            MAX_SEQUENCE_LENGTHS = tokenizer.model_max_length
        return MAX_SEQUENCE_LENGTHS