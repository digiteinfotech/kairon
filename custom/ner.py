from rasa.nlu.components import Component
from typing import Any, Optional, Text, Dict, TYPE_CHECKING
import os
import spacy
import pickle
from spacy.matcher import Matcher
from rasa.nlu.extractors.extractor import EntityExtractor


if TYPE_CHECKING:
    from rasa.nlu.model import Metadata

PATTERN_NER_FILE = 'pattern_ner.pkl'
class SpacyPatternNER(EntityExtractor):
    """A new component"""
    name = "pattern_ner_spacy"
    # Defines what attributes the pipeline component will
    # provide when called. The listed attributes
    # should be set by the component on the message object
    # during test and train, e.g.
    # ```message.set("entities", [...])```
    provides = ["entities"]

    # Which attributes on a message are required by this
    # component. e.g. if requires contains "tokens", than a
    # previous component in the pipeline needs to have "tokens"
    # within the above described `provides` property.
    requires = ["tokens"]

    # Defines the default configuration parameters of a component
    # these values can be overwritten in the pipeline configuration
    # of the model. The component should choose sensible defaults
    # and should be able to create reasonable results with the defaults.
    defaults = {}

    # Defines what language(s) this component can handle.
    # This attribute is designed for instance method: `can_handle_language`.
    # Default value is None which means it can handle all languages.
    # This is an important feature for backwards compatibility of components.
    language_list = None

    def __init__(self, component_config=None, matcher=None):
        super(SpacyPatternNER, self).__init__(component_config)
        if matcher:
            self.matcher = matcher
            self.spacy_nlp = spacy.blank('en')
            self.spacy_nlp.vocab = self.matcher.vocab
        else:
            self.spacy_nlp = spacy.blank('en')
            self.matcher = Matcher(self.spacy_nlp.vocab)

    def train(self, training_data, cfg, **kwargs):
        """Train this component.

        This is the components chance to train itself provided
        with the training data. The component can rely on
        any context attribute to be present, that gets created
        by a call to :meth:`components.Component.pipeline_init`
        of ANY component and
        on any context attributes created by a call to
        :meth:`components.Component.train`
        of components previous to this one."""
        for lookup_table in training_data.lookup_tables:
            key = lookup_table['name']
            pattern = []
            for element in lookup_table['elements']:
                tokens = [{'LOWER': token.lower()} for token in str(element).split()]
                pattern.append(tokens)
            self.matcher.add(key, pattern)

    def process(self, message, **kwargs):
        """Process an incoming message.

        This is the components chance to process an incoming
        message. The component can rely on
        any context attribute to be present, that gets created
        by a call to :meth:`components.Component.pipeline_init`
        of ANY component and
        on any context attributes created by a call to
        :meth:`components.Component.process`
        of components previous to this one."""
        entities = []

        # with plural forms
        doc = self.spacy_nlp(message.data['text'].lower())
        matches = self.matcher(doc)
        entities = self.getNewEntityObj(doc, matches, entities)

        # Without plural forms
        doc = self.spacy_nlp(' '.join([token.lemma_ for token in doc]))
        matches = self.matcher(doc)
        entities = self.getNewEntityObj(doc, matches, entities)

        # Remove duplicates
        seen = set()
        new_entities = []

        for entityObj in entities:
            record = tuple(entityObj.items())
            if record not in seen:
                seen.add(record)
                new_entities.append(entityObj)

        message.set("entities", message.get("entities", []) + new_entities, add_to_output=True)


    def getNewEntityObj(self, doc, matches, entities):

        for ent_id, start, end in matches:
            new_entity_value = doc[start:end].text
            new_entity_value_len = len(new_entity_value.split())
            is_add = True

            for old_entity in entities:
                old_entity_value = old_entity["value"]
                old_entity_value_len = len(old_entity_value.split())

                if old_entity_value_len > new_entity_value_len and new_entity_value in old_entity_value:
                    is_add = False
                elif old_entity_value_len < new_entity_value_len and old_entity_value in new_entity_value:
                    entities.remove(old_entity)

            if is_add:
                entities.append({
                    'start': start,
                    'end': end,
                    'value': doc[start:end].text,
                    'entity': self.matcher.vocab.strings[ent_id],
                    'confidence': None,
                    'extractor': self.name
                })

        return entities


    def persist(self, file_name: Text, model_dir: Text) -> Optional[Dict[Text, Any]]:
        """Persist this component to disk for future loading."""
        if self.matcher:
            modelFile = os.path.join(model_dir, PATTERN_NER_FILE)
            self.saveModel(modelFile)
        return {"pattern_ner_file": PATTERN_NER_FILE}


    @classmethod
    def load(
        cls,
        meta: Dict[Text, Any],
        model_dir: Optional[Text] = None,
        model_metadata: Optional["Metadata"] = None,
        cached_component: Optional["Component"] = None,
        **kwargs: Any
    ) -> "Component":
        """Load this component from file."""

        file_name = meta.get("pattern_ner_file", PATTERN_NER_FILE)
        modelFile = os.path.join(model_dir, file_name)
        if os.path.exists(modelFile):
            modelLoad = open(modelFile, "rb")
            matcher = pickle.load(modelLoad)
            modelLoad.close()
            return cls(meta, matcher)
        else:
            return cls(meta)


    def saveModel(self, modelFile):
        modelSave = open(modelFile, "wb")
        pickle.dump(self.matcher, modelSave)
        modelSave.close()