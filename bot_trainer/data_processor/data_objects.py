import re
from datetime import datetime
from bot_trainer.exceptions import AppException
from typing import Text, List, Dict
from mongoengine import (
    Document,
    EmbeddedDocument,
    EmbeddedDocumentField,
    StringField,
    LongField,
    ListField,
    ValidationError,
    DateTimeField,
    BooleanField,
    DictField,
    DynamicField,
)
from rasa.core.slots import CategoricalSlot, FloatSlot

from bot_trainer.utils import Utility


class Entity(EmbeddedDocument):
    start = LongField(required=True)
    end = LongField(required=True)
    value = StringField(required=True)
    entity = StringField(required=True)

    def validate(self, clean=True):
        if Utility.check_empty_string(self.value) or Utility.check_empty_string(
            self.entity
        ):
            raise ValidationError(
                "Entity name and value cannot be empty or blank spaces"
            )


class TrainingExamples(Document):
    intent = StringField(required=True)
    text = StringField(required=True)
    bot = StringField(required=True)
    entities = ListField(EmbeddedDocumentField(Entity))
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    meta = {"indexes": [{"fields": ["$text"]}]}

    def validate(self, clean=True):
        if self.entities:
            for ent in self.entities:
                ent.validate()
                extracted_ent = self.text[ent.start : ent.end]
                if extracted_ent != ent.value:
                    raise ValidationError(
                        "Invalid entity: "
                        + ent.entity
                        + ", value: "
                        + ent.value
                        + " does not match with the position in the text "
                        + extracted_ent
                    )
        elif Utility.check_empty_string(self.text) or Utility.check_empty_string(
            self.intent
        ):
            raise ValidationError(
                "Training Example name and text cannot be empty or blank spaces"
            )


class EntitySynonyms(Document):
    bot = StringField(required=True)
    synonym = StringField(required=True)
    value = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    meta = {"indexes": [{"fields": ["$value"]}]}

    def validate(self, clean=True):
        if Utility.check_empty_string(self.synonym) or Utility.check_empty_string(
            self.value
        ):
            raise ValidationError(
                "Synonym name and value cannot be empty or blank spaces"
            )


class LookupTables(Document):
    name = StringField(required=True)
    value = StringField(required=True)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    meta = {"indexes": [{"fields": ["$value"]}]}

    def validate(self, clean=True):
        if Utility.check_empty_string(self.name) or Utility.check_empty_string(
            self.value
        ):
            raise ValidationError(
                "Lookup name and value cannot be empty or blank spaces"
            )


class RegexFeatures(Document):
    name = StringField(required=True)
    pattern = StringField(required=True)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    meta = {"indexes": [{"fields": ["$pattern"]}]}

    def validate(self, clean=True):
        if Utility.check_empty_string(self.name) or Utility.check_empty_string(
            self.pattern
        ):
            raise ValidationError(
                "Regex name and pattern cannot be empty or blank spaces"
            )
        else:
            try:
                re.compile(self.pattern)
            except AppException as e:
                raise AppException("invalid regular expression " + self.pattern)


class Intents(Document):
    name = StringField(required=True)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    def validate(self, clean=True):
        if Utility.check_empty_string(self.name):
            raise ValidationError("Intent Name cannot be empty or blank spaces")


class Entities(Document):
    name = StringField(required=True)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    def validate(self, clean=True):
        if Utility.check_empty_string(self.name):
            raise ValidationError("Entity Name cannot be empty or blank spaces")


class Forms(Document):
    name = StringField(required=True)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    def validate(self, clean=True):
        if Utility.check_empty_string(self.name):
            raise ValidationError("Form name cannot be empty or blank spaces")


class ResponseButton(EmbeddedDocument):
    title = StringField(required=True)
    payload = StringField(required=True)

    def validate(self, clean=True):
        if not self.title or not self.payload:
            raise ValidationError("title and payload must be present!")
        elif Utility.check_empty_string(self.title) or Utility.check_empty_string(
            self.payload.strip()
        ):
            raise ValidationError(
                "Response title and payload cannot be empty or blank spaces"
            )


class ResponseText(EmbeddedDocument):
    text = StringField(required=True)
    image = StringField()
    channel = StringField()
    buttons = ListField(EmbeddedDocumentField(ResponseButton))

    def validate(self, clean=True):
        if Utility.check_empty_string(self.text):
            raise ValidationError("Response text cannot be empty or blank spaces")
        Utility.validate_document_list(self.buttons)


class ResponseCustom(EmbeddedDocument):
    custom = DictField(required=True)


class Responses(Document):
    name = StringField(required=True)
    text = EmbeddedDocumentField(ResponseText)
    custom = EmbeddedDocumentField(ResponseCustom)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    def validate(self, clean=True):
        if Utility.check_empty_string(self.name):
            raise ValidationError("Response name cannot be empty or blank spaces")
        elif not self.text and not self.custom:
            raise ValidationError("Either Text or Custom response must be present!")
        else:
            if self.text:
                self.text.validate()
            elif self.custom:
                self.custom.validate()


class Actions(Document):
    name = StringField(required=True)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    def validate(self, clean=True):
        if Utility.check_empty_string(self.name):
            raise ValidationError("Action name cannot be empty or blank spaces")


class SessionConfigs(Document):
    sesssionExpirationTime = LongField(required=True, default=60)
    carryOverSlots = BooleanField(required=True, default=True)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)


class Slots(Document):
    name = StringField(required=True)
    type = StringField(required=True)
    initial_value = DynamicField()
    value_reset_delay = LongField()
    auto_fill = BooleanField(default=True)
    values = ListField(StringField())
    max_value = LongField()
    min_value = LongField()
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    def validate(self, clean=True):
        if Utility.check_empty_string(self.name) or Utility.check_empty_string(
            self.type
        ):
            raise ValueError("Slot name and type cannot be empty or blank spaces")
        error = ""
        if self.type == FloatSlot.type_name:
            if not self.min_value and not self.max_value:
                self.min_value = 0.0
                self.max_value = 1.0
            if self.min_value < self.max_value:
                error = "FloatSlot must have min_value < max_value"
            if not isinstance(self.value, int):
                if error:
                    error += "\n"
                error = "FloatSlot initial_value must be numeric value"
                ValidationError(error)
        elif self.type == CategoricalSlot.type_name:
            if not self.values:
                raise ValidationError(
                    "CategoricalSlot must have list of categories in values field"
                )


class StoryEvents(EmbeddedDocument):
    name = StringField(required=True)
    type = StringField(required=True)
    value = StringField()


class Stories(Document):
    block_name = StringField(required=True)
    start_checkpoints = ListField(StringField(), required=True)
    end_checkpoints = ListField(StringField(), required=True)
    events = ListField(EmbeddedDocumentField(StoryEvents), required=True)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    def validate(self, clean=True):
        Utility.validate_document_list(self.events)
        if Utility.check_empty_string(self.block_name):
            raise ValidationError("Story path name cannot be empty or blank spaces")
        elif not self.events:
            raise ValidationError("Stories cannot be empty")
        elif self.events[0].type != "user":
            raise ValidationError("Stories must start with intent")
        elif self.events[-1].type != "action":
            raise ValidationError("Stories must end with action")


class Configs(Document):
    language = StringField(required=True, default="en")
    pipeline = ListField(DictField(), required=True)
    policies = ListField(DictField(), required=True)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)
