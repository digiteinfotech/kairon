import logging
from typing import List, Text, Tuple

from numpy import ndarray, mean
from transformers import TFXLMRobertaModel, XLMRobertaTokenizerFast

from kairon.shared.nlu.featurizer.lm_models.base import BaseModel

logger = logging.getLogger(__name__)


class XLMRobertaModel(BaseModel):

    def __init__(self, model_weights: str, cache_dir: str=None, from_pt: bool = False, local_files: bool = False):
        if not model_weights:
            model_weights = "sentence-transformers/stsb-xlm-r-multilingual"
            logger.info(
                f"Model weights not specified. Will choose default model "
                f"weights: {model_weights}"
            )
        self.model_weights = model_weights
        self.tokenizer = XLMRobertaTokenizerFast.from_pretrained(model_weights,
                                            cache_dir= cache_dir,
                                            local_files_only=local_files)
        self.model = TFXLMRobertaModel.from_pretrained(model_weights,
                                            cache_dir= cache_dir,
                                            local_files_only=local_files,
                                            from_pt=from_pt)
        self.MAX_SEQUENCE_LENGTHS = self.get_max_sequence_length(model_weights, self.tokenizer)

    def preprocessor(self, token_ids: List[int], **kwargs) -> List[int]:
        return token_ids

    def post_processor(self, sequence_embeddings: ndarray, **kwargs) -> Tuple[ndarray, ndarray]:
        token_embeddings = sequence_embeddings
        sentence_embedding = mean(token_embeddings, axis=0)
        return sentence_embedding, token_embeddings

    def tokens_cleaner(self, token_ids: List[int], token_strings: List[Text], **kwargs) -> Tuple[List[int], List[Text]]:
        return token_ids, token_strings