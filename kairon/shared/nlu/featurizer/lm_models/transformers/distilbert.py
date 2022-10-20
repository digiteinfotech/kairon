from kairon.shared.nlu.featurizer.lm_models.base import BaseModel
from transformers import TFDistilBertModel, DistilBertTokenizerFast
from typing import List, Text, Tuple
from rasa.nlu.utils.hugging_face.transformers_pre_post_processors import bert_tokens_pre_processor, bert_embeddings_post_processor, bert_tokens_cleaner
from numpy import ndarray
import logging

logger = logging.getLogger(__name__)


class DistilBertModel(BaseModel):

    def __init__(self, model_weights: str, cache_dir: str=None, from_pt: bool = False, local_files: bool = False):
        if not model_weights:
            model_weights = "distilbert-base-uncased"
            logger.info(
                f"Model weights not specified. Will choose default model "
                f"weights: {model_weights}"
            )
        self.tokenizer = DistilBertTokenizerFast.from_pretrained(model_weights,
                                            cache_dir= cache_dir,
                                            local_files_only=local_files)
        self.model = TFDistilBertModel.from_pretrained(model_weights,
                                            cache_dir= cache_dir,
                                            local_files_only=local_files,
                                            from_pt=from_pt)
        self.MAX_SEQUENCE_LENGTHS = self.get_max_sequence_length(model_weights, self.tokenizer)

    def preprocessor(self, token_ids: List[int], **kwargs) -> List[int]:
        return bert_tokens_pre_processor(token_ids)

    def post_processor(self, sequence_embeddings: ndarray, **kwargs) -> Tuple[ndarray, ndarray]:
        return bert_embeddings_post_processor(sequence_embeddings)

    def tokens_cleaner(self, token_ids: List[int], token_strings: List[Text], **kwargs) -> Tuple[List[int], List[Text]]:
        return bert_tokens_cleaner(token_ids=token_ids, token_strings=token_strings)