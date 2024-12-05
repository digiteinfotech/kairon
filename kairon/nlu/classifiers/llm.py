import ujson as json
import logging
import typing
from typing import Any, Dict, List, Optional, Text
from abc import ABC

from pydantic import BaseModel
from rasa.nlu.classifiers.classifier import IntentClassifier
from rasa.shared.nlu.training_data.message import Message
from rasa.shared.nlu.training_data.training_data import TrainingData
from rasa.engine.storage.resource import Resource
from rasa.engine.storage.storage import ModelStorage
import faiss
import rasa.utils.io as io_utils
from rasa.shared.nlu.constants import TEXT, INTENT, ENTITIES, ENTITY_ATTRIBUTE_TYPE
import numpy as np
from tqdm import tqdm
from rasa.engine.graph import GraphComponent, ExecutionContext
from rasa.engine.recipes.default_recipe import DefaultV1Recipe
import litellm
from rasa.shared.utils.io import create_directory_for_file
from more_itertools import chunked
import os
from rasa.nlu.extractors.extractor import EntityExtractorMixin

litellm.drop_params = True
os.environ["LITELLM_LOG"] = "ERROR"

logger = logging.getLogger(__name__)

if typing.TYPE_CHECKING:
    pass

@DefaultV1Recipe.register(
    DefaultV1Recipe.ComponentType.INTENT_CLASSIFIER, is_trainable=True
)
class LLMClassifier(IntentClassifier, GraphComponent, EntityExtractorMixin, ABC):
    """Intent and Entity classifiers using the OpenAI Completion framework"""

    system_prompt = "You will be provided with a text, and your task is to classify its intent and entities. Provide output in json format with the following keys intent, explanation, text and entities."

    def __init__(
        self,
        config: Optional[Dict[Text, Any]],
        model_storage: ModelStorage,
        resource: Resource,
        execution_context: ExecutionContext,
        vector: Optional[faiss.IndexFlatIP] = None,
        data: Optional[Dict[Text, Any]] = None,
    ) -> None:
        """Construct a new intent classifiers using the OpenAI Completion framework."""
        self.component_config = config
        self._model_storage = model_storage
        self._resource = resource
        self._execution_context = execution_context

        self.load_api_key(config.get("bot_id"))
        if vector is not None:
            self.vector = vector
        else:
            self.vector = faiss.IndexFlatIP(config.get("embedding_size", 1536))

        self.data = data


    @classmethod
    def required_packages(cls) -> List[Text]:
        return ["litellm", "numpy"]

    @staticmethod
    def get_default_config() -> Dict[Text, Any]:
        return {
            "bot_id": None,
            "prediction_model": "gpt-4o-mini",
            "embedding_model": "text-embedding-3-small",
            "embedding_size": 1536,
            "top_k": 5,
            "temperature": 0.0,
            "retry": 3,
        }

    def load_api_key(self, bot_id: Text):
        if bot_id:
            from kairon.shared.admin.processor import Sysadmin
            llm_secret = Sysadmin.get_llm_secret("openai", bot_id)
            self.api_key = llm_secret.get('api_key')
        elif os.environ.get("LLM_API_KEY"):
            self.api_key = os.environ.get("LLM_API_KEY")
        else:
            raise KeyError(
                f"either set bot_id'in LLMClassifier config or set LLM_API_KEY in environment variables"
            )

    def get_embeddings(self, text):
        embeddings = litellm.embedding(
            model="text-embedding-3-small", input=text, api_key=self.api_key, max_retries=3
        )
        return [ embedding['embedding'] for embedding in embeddings['data']]

    def train(self, training_data: TrainingData) -> Resource:
        """Train the intent classifiers on a data set."""
        data_map = []
        vector_map = []
        batch_size = 100
        with tqdm(len(training_data.intent_examples)) as pbar:
            counter = 1
            for chunks in chunked(training_data.intent_examples, batch_size):
                data = [{"text": example.get(TEXT).strip(), INTENT: example.get(INTENT).strip(), ENTITIES: example.get(ENTITIES)} for example in chunks if example.get(INTENT) and example.get(INTENT)]
                vector_data = [example.get(TEXT).strip() for example in chunks if example.get(INTENT) and example.get(TEXT)]
                if data and vector_data:
                    vector_map.extend(self.get_embeddings(vector_data))
                    data_map.extend(data)
                pbar.update(batch_size)
                counter +=1

        np_vector = np.asarray(vector_map, dtype=np.float32)
        faiss.normalize_L2(np_vector)
        self.vector.add(np_vector)
        self.data = data_map
        self.persist()
        return self._resource

    def prepare_context(self, embeddings, text):
        dist, indx = self.vector.search(
            np.asarray([embeddings], dtype=np.float32),
            k=self.component_config.get("top_k", 5),
        )
        intents = set()
        entities = set()
        data = []
        for i in indx[0]:
            if self.data[i].get(INTENT):
                intents.add(self.data[i][INTENT])
                entities = set([entity[ENTITY_ATTRIBUTE_TYPE] for entity in entities])
                entities_obj = self.data[i][ENTITIES]if self.data[i][ENTITIES] else []
                data.append({
                    'text': self.data[i][TEXT],
                    'intent': self.data[i][INTENT],
                    'entities': entities_obj
                })

        messages = [
            {"role": "user", "content": f"""You will be provided with a text, and your task is to classify its intent and extract any relevant entities. Provide the output in JSON format with the following keys: `intent`, `explanation`, `text`, and `entities`.

### Intents
The possible intents are:
{intents}

### Entities
You should extract entities from the text, although no specific entity types are provided (currently set to an empty set). 

The entities that can be extracted are:
{entities}

Ensure to only extract entities that are relevant to the classification.

---

**Example:**

```json
{json.dumps(data)}
```

### Task
Classify the intent and extract entities for the given text:

**Text**: `"take to xy100"`

Please provide your answer in the specified JSON format."""
             }
        ]


        return messages

    def predict(self, text):
        embedding = self.get_embeddings(text)[0]
        messages = self.prepare_context(embedding, text)
        intent = None
        explanation = None
        entities = []
        try:
            response = litellm.completion(
                model=self.component_config.get("prediction_model", "gpt-3.5-turbo"),
                messages=messages,
                response_format={ "type": "json_object" },
                temperature=self.component_config.get("temperature", 0.0),
                top_p=1,
                frequency_penalty=0,
                presence_penalty=0,
                api_key=self.api_key,
                max_retries=3
            )
            logger.debug(response)
            responses = json.loads(response.choices[0]["message"]["content"])
            intent = responses["intent"] if "intent" in responses.keys() else "nlu_fallback"
            explanation = responses["explanation"] if "explanation" in responses.keys() else None
            entities = responses["entities"]if "entities" in responses.keys() else []
        except Exception as e:
            logger.error(e)
        return intent, explanation, entities

    def process(self, messages: List[Message]) -> List[Message]:
        """Return the most likely intent and its probability for a message."""
        for message in messages:
            if not self.vector and not self.data:
                # component is either not trained or didn't
                # receive enough training data
                intent = None
                intent_ranking = []
                entities = []
            else:
                label, reason, entities = self.predict(message.get(TEXT))
                intent = {"name": label, "confidence": 1, "reason": reason}
                intent_ranking = []
                entities = self.add_extractor_name(entities)

            message.set("intent", intent, add_to_output=True)
            message.set("intent_ranking", intent_ranking, add_to_output=True)
            message.set(ENTITIES, entities, add_to_output=True)
        return messages

    @classmethod
    def create(
        cls,
        config: Dict[Text, Any],
        model_storage: ModelStorage,
        resource: Resource,
        execution_context: ExecutionContext,
    ) -> "LLMClassifier":
        """Creates a new untrained component (see parent class for full docstring)."""
        return cls(config, model_storage, resource, execution_context)

    @classmethod
    def load(
        cls,
        config: Dict[Text, Any],
        model_storage: ModelStorage,
        resource: Resource,
        execution_context: ExecutionContext,
        **kwargs: Any,
    ) -> "LLMClassifier":
        """Loads a policy from the storage (see parent class for full docstring)."""
        try:
            with model_storage.read_from(resource) as model_path:
                file_name = cls.__name__

                vector_file = os.path.join(model_path, file_name + "_vector.db")
                data_file = os.path.join(model_path, file_name + "_data.pkl")

                if os.path.exists(vector_file):
                    vector = faiss.read_index(vector_file)
                    data = io_utils.json_unpickle(data_file)
                    return cls(
                        config, model_storage, resource, execution_context, vector, data
                    )
                else:
                    return cls(config, model_storage, resource, execution_context)
        except ValueError:
            logger.debug(
                f"Failed to load {cls.__class__.__name__} from model storage. Resource "
                f"'{resource.name}' doesn't exist."
            )
        return cls(config, model_storage, resource, execution_context)

    def persist(self) -> None:
        """Persist this model into the passed directory."""
        with self._model_storage.write_to(self._resource) as model_path:
            file_name = self.__class__.__name__
            vector_file_name = file_name + "_vector.db"
            data_file_name = file_name + "_data.pkl"
            if self.vector and self.data:
                create_directory_for_file(model_path)
                faiss.write_index(
                    self.vector, os.path.join(model_path, vector_file_name)
                )
                io_utils.json_pickle(
                    os.path.join(model_path, data_file_name), self.data
                )
