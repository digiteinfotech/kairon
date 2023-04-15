import logging
import typing
from typing import Any, Dict, List, Optional, Text

from rasa.nlu.classifiers.classifier import IntentClassifier
from rasa.nlu.config import RasaNLUModelConfig
from rasa.shared.nlu.training_data.message import Message
from rasa.shared.nlu.training_data.training_data import TrainingData
from rasa.nlu.model import Metadata
import faiss
import rasa.utils.io as io_utils
import os
from rasa.shared.nlu.constants import TEXT, INTENT
import openai
import numpy as np

logger = logging.getLogger(__name__)

if typing.TYPE_CHECKING:
    pass


class OpenAIClassifier(IntentClassifier):
    """Intent and Entity classifier using the OpenAI Completion framework"""

    defaults = {
        "bot_id": None,
        "prediction_model": "gpt-4",
        "embedding_model": "text-embedding-ada-002",
        "embedding_size": 1536,
        "top_k": 5,
        "temperature": 0.0,
        "max_tokens": 50,
    }

    system_prompt = "You are an intent classifier. Based on the users prompt, you will classify the prompt to one of the intent if it is not from one of the stories you will classify it as nlu_fallback. Also provide the explanation why particular intent is classified."

    def __init__(
            self,
            component_config: Optional[Dict[Text, Any]] = None,
            vector: Optional[faiss.IndexFlatIP] = None,
            data: Optional[Dict[Text, Any]] = None
    ) -> None:
        """Construct a new intent classifier using the OpenAI Completion framework."""

        super().__init__(component_config)
        self.load_api_key(component_config.get("bot_id"))
        if vector is not None:
            self.vector = vector
        else:
            self.vector = faiss.IndexFlatIP(component_config.get("embedding_size", 1536))

        self.data = data

    @classmethod
    def required_packages(cls) -> List[Text]:
        return ["openai", "faiss", "numpy"]

    def load_api_key(self, bot_id: Text):
        if bot_id:
            from kairon.shared.admin.processor import Sysadmin
            from kairon.shared.admin.constants import BotSecretType
            self.api_key = Sysadmin.get_bot_secret(bot_id, BotSecretType.gpt_key.value, raise_err=True)
        elif os.environ.get("OPENAI_API_KEY"):
            self.api_key = os.environ.get("OPENAI_API_KEY")
        else:
            raise KeyError(
                f"either set bot_id'in OpenAIClassifier config or set OPENAI_API_KEY in environment variables"
            )

    def get_embeddings(self, text):
        embedding = openai.Embedding.create(
            model="text-embedding-ada-002",
            input=text,
            api_key=self.api_key
        )['data'][0]['embedding']
        return embedding

    def train(
            self,
            training_data: TrainingData,
            config: Optional[RasaNLUModelConfig] = None,
            **kwargs: Any,
    ) -> None:
        """Train the intent classifier on a data set."""
        data_map = []
        vector_map = []
        for example in training_data.intent_examples:
            vector_map.append(self.get_embeddings(example.get(TEXT)))
            data_map.append({'text': example.get(TEXT), 'intent': example.get(INTENT)})
        np_vector = np.asarray(vector_map, dtype=np.float32)
        faiss.normalize_L2(np_vector)
        self.vector.add(np_vector)
        self.data = data_map

    def prepare_context(self, embeddings, text):
        dist, indx = self.vector.search(np.asarray([embeddings], dtype=np.float32), k=self.component_config.get("top_k", 5))
        messages = [
            {"role": "system", "content": self.system_prompt},
        ]
        for i in indx[0]:
            messages.append({"role": "user", "content": f"text: {self.data[i]['text']}"})
            messages.append({"role": "assistant", "content": f"intent: {self.data[i]['intent']}"})
        messages.append({"role": "user", "content": f"text: {text}"})
        return messages

    def predict(self, text):
        embedding = self.get_embeddings(text)
        messages = self.prepare_context(embedding, text)
        response = openai.ChatCompletion.create(
            model=self.component_config.get("prediction_model", "gpt-4"),
            messages=messages,
            temperature=self.component_config.get("temperature", 0.0),
            max_tokens=self.component_config.get("max_tokens", 50),
            top_p=1,
            frequency_penalty=0,
            presence_penalty=0,
            stop=["\n\n"],
            api_key=self.api_key
        )
        intent_str, explanation_str = response.choices[0]['message']['content'].split('\n')
        intent = intent_str.split(':')[1].strip()
        explanation = explanation_str.split(':')[1].strip()
        return intent, explanation

    def process(self, message: Message, **kwargs: Any) -> None:
        """Return the most likely intent and its probability for a message."""

        if not self.vector and not self.data:
            # component is either not trained or didn't
            # receive enough training data
            intent = None
            intent_ranking = []
        else:
            label, reason = self.predict(message.get(TEXT))
            intent = {"name": label, "confidence": 1, "reason": reason}
            intent_ranking = []
            print(intent)

        message.set("intent", intent, add_to_output=True)
        message.set("intent_ranking", intent_ranking, add_to_output=True)

    @classmethod
    def load(
            cls,
            meta: Dict[Text, Any],
            model_dir: Text,
            model_metadata: Optional[Metadata] = None,
            cached_component: Optional["GPTPromptIntentClassifier"] = None,
            **kwargs: Any,
    ) -> "GPTPromptIntentClassifier":
        """Loads trained component (see parent class for full docstring)."""

        vector_file = os.path.join(model_dir, meta.get("vector"))
        data_file = os.path.join(model_dir, meta.get("data"))

        if os.path.exists(vector_file):
            vector = faiss.read_index(vector_file)
            data = io_utils.json_unpickle(data_file)
            return cls(meta, vector, data)
        else:
            return cls(meta)

    def persist(self, file_name: Text, model_dir: Text) -> Optional[Dict[Text, Any]]:
        """Persist this model into the passed directory."""

        vector_file_name = file_name + "_vector.db"
        data_file_name = file_name + "_data.pkl"
        if self.vector and self.data:
            faiss.write_index(self.vector, os.path.join(model_dir, vector_file_name))
            io_utils.json_pickle(
                os.path.join(model_dir, data_file_name), self.data
            )
        return {"vector": vector_file_name, "data": data_file_name}
