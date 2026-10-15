import logging
import os
from abc import ABC
from typing import Any, Dict, List, Optional, Text, Tuple

import requests
import ujson as json
from rasa.engine.graph import GraphComponent, ExecutionContext
from rasa.engine.recipes.default_recipe import DefaultV1Recipe
from rasa.engine.storage.resource import Resource
from rasa.engine.storage.storage import ModelStorage
from rasa.nlu.classifiers.classifier import IntentClassifier
from rasa.nlu.extractors.extractor import EntityExtractorMixin
from rasa.shared.nlu.constants import TEXT, INTENT, ENTITIES, EXTRACTOR
from rasa.shared.nlu.training_data.message import Message
from rasa.shared.nlu.training_data.training_data import TrainingData
from rasa.shared.utils.io import create_directory_for_file

logger = logging.getLogger(__name__)

CLASSIFICATION_MODEL = "typesafe/jev-1.13"
OPENROUTER_DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"
FALLBACK_INTENT = "nlu_fallback"
ENTITY_THRESHOLD = 0.5
MAX_ENTITY_CANDIDATES = 40


@DefaultV1Recipe.register(
    [
        DefaultV1Recipe.ComponentType.INTENT_CLASSIFIER,
        DefaultV1Recipe.ComponentType.ENTITY_EXTRACTOR,
     ],
    is_trainable=True
)
class LLMClassifier(IntentClassifier, GraphComponent, EntityExtractorMixin, ABC):
    """Intent and entity classifier.

    Training samples are the only evidence. typesafe/jev-1.13 on OpenRouter's
    Decisions API chooses the intent from those samples and accepts or rejects
    entity values from the samples when they occur in the text. Jev does not
    invent span text.
    """

    def __init__(
        self,
        config: Optional[Dict[Text, Any]],
        model_storage: ModelStorage,
        resource: Resource,
        execution_context: ExecutionContext,
        data: Optional[List[Dict[Text, Any]]] = None,
    ) -> None:
        """Construct a new classifier."""
        self.component_config = config
        self._model_storage = model_storage
        self._resource = resource
        self._execution_context = execution_context
        self.data = data

    @classmethod
    def required_packages(cls) -> List[Text]:
        return ["requests"]

    @staticmethod
    def get_default_config() -> Dict[Text, Any]:
        return {
            "bot_id": None,
            "prediction_model": CLASSIFICATION_MODEL,
            "temperature": 0.0,
            "retry": 3,
        }

    def train(self, training_data: TrainingData) -> Resource:
        """Store training samples. Classification does not embed them."""
        samples = []
        for example in training_data.intent_examples:
            intent = example.get(INTENT)
            text = example.get(TEXT)
            if not intent or not text or not str(text).strip():
                continue
            samples.append({
                "text": str(text).strip(),
                INTENT: str(intent).strip(),
                ENTITIES: example.get(ENTITIES),
            })
        self.data = samples
        self.persist()
        return self._resource

    def _openrouter_api_key(self) -> Optional[Text]:
        bot_id = (self.component_config or {}).get("bot_id")
        if bot_id:
            from kairon.shared.admin.processor import Sysadmin
            secret = Sysadmin.get_llm_secret("openrouter", bot_id)
            return secret.get("api_key")
        return os.environ.get("LLM_API_KEY")

    def _samples(self) -> List[Dict[Text, Any]]:
        examples = []
        for row in self.data or []:
            intent = row.get(INTENT)
            if not intent:
                continue
            examples.append({
                "text": row.get(TEXT),
                "intent": intent,
                "entities": self._example_entities(row.get(ENTITIES)),
            })
        return examples

    @staticmethod
    def _example_entities(raw_entities) -> List[Dict[Text, Any]]:
        entities = []
        for entity in raw_entities or []:
            if not isinstance(entity, dict):
                continue
            entity_type = entity.get("entity")
            value = entity.get("value")
            if not entity_type or value is None or not str(value).strip():
                continue
            item = {"entity": str(entity_type), "value": str(value)}
            if entity.get("role"):
                item["role"] = entity["role"]
            if entity.get("group"):
                item["group"] = entity["group"]
            entities.append(item)
        return entities

    def _entity_candidates(self, text: Text, examples: List[Dict[Text, Any]]) -> List[Dict[Text, Any]]:
        """Sample entity values that occur in the text.

        A span is proposed only when a training sample labeled that value.
        Values absent from the samples are not checked.
        """
        if not text:
            return []
        candidates = []
        seen = set()

        def add(start, end, entity_type, role=None, group=None):
            if len(candidates) >= MAX_ENTITY_CANDIDATES:
                return
            if start < 0 or end <= start or end > len(text):
                return
            value = text[start:end]
            if not value.strip():
                return
            key = (start, end, entity_type)
            if key in seen:
                return
            seen.add(key)
            item = {
                "entity": entity_type,
                "value": value,
                "start": start,
                "end": end,
            }
            if role:
                item["role"] = role
            if group:
                item["group"] = group
            candidates.append(item)

        lowered = text.lower()
        for example in examples:
            for entity in example.get("entities") or []:
                needle = entity["value"].lower()
                offset = 0
                while len(candidates) < MAX_ENTITY_CANDIDATES:
                    index = lowered.find(needle, offset)
                    if index < 0:
                        break
                    add(
                        index,
                        index + len(entity["value"]),
                        entity["entity"],
                        entity.get("role"),
                        entity.get("group"),
                    )
                    offset = index + max(len(needle), 1)
                if len(candidates) >= MAX_ENTITY_CANDIDATES:
                    return candidates
        return candidates

    def _decisions_body(
        self, text: Text, examples: List[Dict[Text, Any]]
    ) -> Tuple[Dict[Text, Any], List[Dict[Text, Any]]]:
        criteria: Dict[Text, Text] = {}
        for example in examples:
            intent = example["intent"]
            if intent in criteria:
                continue
            samples = []
            for ex in examples:
                sample_text = ex.get("text")
                if ex["intent"] == intent and sample_text and sample_text not in samples:
                    samples.append(sample_text)
            criteria[intent] = "Examples: " + "; ".join(samples) if samples else intent
        criteria.setdefault(
            FALLBACK_INTENT,
            "The text does not match any other intent.",
        )
        questions: Dict[Text, Any] = {
            "intent": {
                "type": "choice",
                "instructions": (
                    "Which intent best classifies `text`? "
                    "Choose nlu_fallback when none of the other intents fit."
                ),
                "criteria": criteria,
            }
        }
        checks = []
        for index, candidate in enumerate(self._entity_candidates(text, examples)):
            key = f"entity_{index}"
            questions[key] = {
                "type": "noul",
                "instructions": (
                    f'Is "{candidate["value"]}" a {candidate["entity"]} in `text`?'
                ),
                "criteria": {
                    "true": f'The span is a {candidate["entity"]}.',
                    "false": f'The span is not a {candidate["entity"]}.',
                },
            }
            checks.append({"key": key, **candidate})
        # The Decisions API rejects chat model ids. A model trained while
        # prediction_model was gpt-* must still call Jev.
        body = {
            "model": CLASSIFICATION_MODEL,
            "state": {"text": text, "examples": examples},
            "questions": questions,
        }
        return body, checks

    @staticmethod
    def _intent_from_decision(payload: Dict[Text, Any]) -> Tuple[Text, float]:
        answer = (payload.get("answers") or {}).get("intent") or {}
        choice = answer.get("choice") or FALLBACK_INTENT
        probabilities = answer.get("probabilities") or {}
        confidence = probabilities.get(choice)
        if confidence is None:
            confidence = answer.get("confidence", 0.0)
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = 0.0
        return choice, max(0.0, min(1.0, confidence))

    @staticmethod
    def _entities_from_decision(
        payload: Dict[Text, Any], checks: List[Dict[Text, Any]]
    ) -> List[Dict[Text, Any]]:
        answers = payload.get("answers") or {}
        accepted = []
        for check in checks:
            answer = answers.get(check["key"]) or {}
            try:
                score = float(answer.get("noul", 0.0))
            except (TypeError, ValueError):
                score = 0.0
            if score <= ENTITY_THRESHOLD:
                continue
            entity = {
                "entity": check["entity"],
                "value": check["value"],
                "start": check["start"],
                "end": check["end"],
                "confidence": max(0.0, min(1.0, score)),
            }
            if check.get("role"):
                entity["role"] = check["role"]
            if check.get("group"):
                entity["group"] = check["group"]
            accepted.append(entity)
        return LLMClassifier._drop_overlapping_entities(accepted)

    @staticmethod
    def _drop_overlapping_entities(entities: List[Dict[Text, Any]]) -> List[Dict[Text, Any]]:
        kept = []
        ranked = sorted(
            entities,
            key=lambda entity: (
                -entity["confidence"],
                -(entity["end"] - entity["start"]),
            ),
        )
        for entity in ranked:
            if any(
                entity["entity"] == other["entity"]
                and entity["start"] < other["end"]
                and other["start"] < entity["end"]
                for other in kept
            ):
                continue
            kept.append(entity)
        kept.sort(key=lambda entity: entity["start"])
        return kept

    def _classify(self, text: Text) -> Tuple[Text, float, List[Dict[Text, Any]]]:
        examples = self._samples()
        if not any(example["intent"] != FALLBACK_INTENT for example in examples):
            return FALLBACK_INTENT, 0.0, []
        api_key = self._openrouter_api_key()
        if not api_key:
            raise KeyError("OpenRouter API key is not configured for LLMClassifier")
        body, checks = self._decisions_body(text, examples)
        response = requests.post(
            OPENROUTER_DECISIONS_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        logger.info(payload)
        intent, confidence = self._intent_from_decision(payload)
        return intent, confidence, self._entities_from_decision(payload, checks)

    def predict(self, text):
        try:
            return self._classify(text)
        except Exception as e:
            logger.exception(e)
        return FALLBACK_INTENT, 0.0, []

    def process(self, messages: List[Message]) -> List[Message]:
        """Return the most likely intent and its probability for a message."""
        for message in messages:
            if not self.data:
                # component is either not trained or didn't
                # receive enough training data
                intent = None
                intent_ranking = []
                entities = []
            else:
                label, confidence, entities = self.predict(message.get(TEXT))
                intent = {"name": label, "confidence": confidence, "reason": None}
                intent_ranking = [intent.copy()]
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
        """Loads stored training samples. Embedding indexes are ignored."""
        try:
            with model_storage.read_from(resource) as model_path:
                data_file = os.path.join(model_path, cls.__name__ + "_data.json")
                if os.path.exists(data_file):
                    with open(data_file, "r") as data_handle:
                        data = json.load(data_handle)
                    return cls(
                        config, model_storage, resource, execution_context, data
                    )
                return cls(config, model_storage, resource, execution_context)
        except ValueError:
            logger.debug(
                f"Failed to load {cls.__name__} from model storage. Resource "
                f"'{resource.name}' doesn't exist."
            )
        return cls(config, model_storage, resource, execution_context)

    def persist(self) -> None:
        """Persist training samples. No embedding index is written."""
        with self._model_storage.write_to(self._resource) as model_path:
            if not self.data:
                return
            data_file = os.path.join(model_path, self.__class__.__name__ + "_data.json")
            create_directory_for_file(data_file)
            with open(data_file, "w") as data_handle:
                json.dump(self.data, data_handle, escape_forward_slashes=True)

    def add_extractor_name(
        self, entities: List[Dict[Text, Any]]
    ) -> List[Dict[Text, Any]]:
        """Adds this extractor's name to a list of entities.

        Args:
            entities: the extracted entities.

        Returns:
            the modified entities.
        """
        entities_new = []
        for entity in entities:
            if isinstance(entity, dict):
                entity[EXTRACTOR] = self.name
                entities_new.append(entity.copy())
        return entities_new
