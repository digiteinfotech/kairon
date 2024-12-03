import logging
import os
from abc import ABC
from typing import Any, Optional, Text, List, Dict, Tuple, Type

import numpy as np
import openai
from rasa.engine.graph import GraphComponent, ExecutionContext
from rasa.engine.recipes.default_recipe import DefaultV1Recipe
from rasa.nlu.constants import (
    DENSE_FEATURIZABLE_ATTRIBUTES,
    SEQUENCE_FEATURES,
    SENTENCE_FEATURES,
    FEATURIZER_CLASS_ALIAS,
    TOKENS_NAMES
)
from rasa.nlu.featurizers.dense_featurizer.dense_featurizer import DenseFeaturizer
from rasa.nlu.tokenizers.tokenizer import Tokenizer
from rasa.shared.nlu.constants import (
    TEXT,
    FEATURE_TYPE_SENTENCE,
    FEATURE_TYPE_SEQUENCE,
    ACTION_TEXT,
)
from rasa.shared.nlu.training_data.features import Features
from rasa.shared.nlu.training_data.message import Message
from rasa.shared.nlu.training_data.training_data import TrainingData
from tqdm import tqdm

logger = logging.getLogger(__name__)

@DefaultV1Recipe.register(
    DefaultV1Recipe.ComponentType.MESSAGE_FEATURIZER, is_trainable=False
)
class OpenAIFeaturizer(DenseFeaturizer, GraphComponent, ABC):
    """Featurizer using openai language models."""


    def __init__(
            self, config: Dict[Text, Any], execution_context: ExecutionContext
    ) -> None:
        """Initializes OpenAIFeaturizer with the specified model.

        Args:
            component_config: Configuration for the component.
        """
        super(OpenAIFeaturizer, self).__init__(execution_context.node_name, config)
        self.load_api_key(config.get("bot_id"))

    def load_api_key(self, bot_id: Text):
        if bot_id:
            from kairon.shared.admin.processor import Sysadmin
            llm_secret = Sysadmin.get_llm_secret("openai", bot_id)
            self.api_key = llm_secret.get('api_key')
        elif os.environ.get("OPENAI_API_KEY"):
            self.api_key = os.environ.get("OPENAI_API_KEY")
        else:
            raise KeyError(
                f"either set bot_id'in OpenAIFeaturizer config or set OPENAI_API_KEY in environment variables"
            )

    @classmethod
    def required_components(cls) -> List[Type]:
        """Packages needed to be installed."""
        return [Tokenizer]

    @classmethod
    def required_packages(cls) -> List[Text]:
        """Packages needed to be installed."""
        return ["openai"]

    @staticmethod
    def get_default_config() -> Dict[Text, Any]:
        """Returns OpenAIFeaturizer's default config."""
        return {
            **DenseFeaturizer.get_default_config(),
            "bot_id": None,
        }

    def get_tokens_embeddings(self, tokens):
        embeddings = []
        for token in tokens:
            embeddings.append(self.get_embeddings(token.text))
        return embeddings

    def get_embeddings(self, text):
        embedding = openai.Embedding.create(
            model="text-embedding-3-small",
            input=text,
            api_key=self.api_key
        )['data'][0]['embedding']
        return embedding

    def _get_model_features_for_batch(
            self,
            batch_examples: List[Message],
            attribute: Text,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Compute dense features of each example in the batch.

        Args:
            batch_examples: List of examples in the batch.
            attribute: attribute of the Message object to be processed.

        Returns:
            Sentence and token level dense representations.
        """
        sentence_embeddings = []
        sequence_embeddings = []
        for example in batch_examples:
            text = example.get(attribute)
            tokens = example.get(TOKENS_NAMES[attribute])

            sequence_embeddings.append(np.array(self.get_tokens_embeddings(tokens)))
            sentence_embeddings.append(np.array([self.get_embeddings(text)]))

        return np.array(sentence_embeddings), np.array(sequence_embeddings)

    def _get_docs_for_batch(
            self,
            batch_examples: List[Message],
            attribute: Text,
    ) -> List[Dict[Text, Any]]:
        """Compute language model docs for all examples in the batch.

        Args:
            batch_examples: Batch of message objects for which language model docs
            need to be computed.
            attribute: Property of message to be processed, one of ``TEXT`` or
            ``RESPONSE``.

        Returns:
            List of language model docs for each message in batch.
        """

        (
            batch_sentence_features,
            batch_sequence_features,
        ) = self._get_model_features_for_batch(
            batch_examples, attribute
        )

        # A doc consists of
        # {'sequence_features': ..., 'sentence_features': ...}
        batch_docs = []
        for index in range(len(batch_examples)):
            doc = {
                SEQUENCE_FEATURES: batch_sequence_features[index],
                SENTENCE_FEATURES: np.reshape(batch_sentence_features[index], (1, -1)),
            }
            batch_docs.append(doc)

        return batch_docs

    def process_training_data(self, training_data: TrainingData) -> TrainingData:
        """Compute tokens and dense features for each message in training data.

        Args:
            training_data: NLU training data to be tokenized and featurized
            config: NLU pipeline config consisting of all components.
        """
        batch_size = 64

        for attribute in DENSE_FEATURIZABLE_ATTRIBUTES:

            non_empty_examples = list(
                filter(lambda x: x.get(attribute), training_data.training_examples)
            )

            batch_start_index = 0
            with tqdm(
                    total=len(non_empty_examples),
                    desc=f"Computing language model features for attribute '{attribute}'",
            ) as pbar:
                while batch_start_index < len(non_empty_examples):

                    batch_end_index = min(
                        batch_start_index + batch_size, len(non_empty_examples)
                    )
                    # Collect batch examples
                    batch_messages = non_empty_examples[batch_start_index:batch_end_index]

                    # Construct a doc with relevant features
                    # extracted(tokens, dense_features)
                    batch_docs = self._get_docs_for_batch(batch_messages, attribute)

                    for index, ex in enumerate(batch_messages):
                        self._set_lm_features(batch_docs[index], ex, attribute)
                        pbar.update(1)
                    batch_start_index += batch_size
        return training_data

    def process(self, messages: List[Message]) -> List[Message]:
        """Process an incoming message by computing its tokens and dense features.

        Args:
            message: Incoming message object
        """
        # process of all featurizers operates only on TEXT and ACTION_TEXT attributes,
        # because all other attributes are labels which are featurized during training
        # and their features are stored by the model itself.
        for message in messages:
            for attribute in {TEXT, ACTION_TEXT}:
                if message.get(attribute):
                    self._set_lm_features(
                        self._get_docs_for_batch(
                            [message], attribute=attribute
                        )[0],
                        message,
                        attribute,
                    )
        return messages

    def _set_lm_features(
            self, doc: Dict[Text, Any], message: Message, attribute: Text = TEXT
    ) -> None:
        """Adds the precomputed word vectors to the messages features."""
        sequence_features = doc[SEQUENCE_FEATURES]
        sentence_features = doc[SENTENCE_FEATURES]

        final_sequence_features = Features(
            sequence_features,
            FEATURE_TYPE_SEQUENCE,
            attribute,
            self.component_config[FEATURIZER_CLASS_ALIAS],
        )
        message.add_features(final_sequence_features)
        final_sentence_features = Features(
            sentence_features,
            FEATURE_TYPE_SENTENCE,
            attribute,
            self.component_config[FEATURIZER_CLASS_ALIAS],
        )
        message.add_features(final_sentence_features)
