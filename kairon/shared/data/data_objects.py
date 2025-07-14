import re
from datetime import datetime

import ujson as json
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
    IntField,
    FloatField, GenericEmbeddedDocumentField,
)
from rasa.shared.constants import DEFAULT_NLU_FALLBACK_INTENT_NAME
from rasa.shared.core.slots import (
    CategoricalSlot,
    FloatSlot,
    ListSlot,
    TextSlot,
    BooleanSlot,
    AnySlot,
)
from validators import domain
from validators import url
from validators.utils import ValidationError as ValidationFailure

from kairon.exceptions import AppException
from kairon.shared.data.audit.data_objects import Auditlog
from kairon.shared.data.signals import push_notification, auditlogger
from kairon.shared.models import (
    TemplateType,
    StoryStepType,
    StoryType, GlobalSlotsEntryType, FlowTagType, UserMediaUploadStatus, UserMediaUploadType,
)
from kairon.shared.utils import Utility
from .constant import EVENT_STATUS, SLOT_MAPPING_TYPE, DEMO_REQUEST_STATUS
from ..constants import WhatsappBSPTypes, LLMResourceProvider


class Entity(EmbeddedDocument):
    start = LongField(required=True)
    end = LongField(required=True)
    value = StringField(required=True)
    entity = StringField(required=True)

    def validate(self, clean=True):
        if clean:
            self.clean()
        if Utility.check_empty_string(self.value) or Utility.check_empty_string(
            self.entity
        ):
            raise ValidationError(
                "Entity name and value cannot be empty or blank spaces"
            )

    def clean(self):
        if not Utility.check_empty_string(self.entity):
            self.entity = self.entity.strip().lower()

    def __eq__(self, other):
        return (
            isinstance(other, self.__class__)
            and self.start == other.start
            and self.end == other.end
            and self.value == other.value
            and self.entity == other.entity
        )


@auditlogger.log
@push_notification.apply
class TrainingExamples(Auditlog):
    intent = StringField(required=True)
    text = StringField(required=True)
    bot = StringField(required=True)
    entities = ListField(EmbeddedDocumentField(Entity), default=None)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    meta = {
        "indexes": [
            {"fields": ["$text", ("bot", "status"), ("bot", "intent", "status")]}
        ]
    }

    def validate(self, clean=True):
        if clean:
            self.clean()

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

    def clean(self):
        self.intent = self.intent.strip().lower()
        if self.entities:
            for ent in self.entities:
                ent.clean()


@auditlogger.log
@push_notification.apply
class Synonyms(Auditlog):
    bot = StringField(required=True)
    name = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    meta = {"indexes": [{"fields": ["bot", ("bot", "status", "name")]}]}

    def validate(self, clean=True):
        if clean:
            self.clean()

        if Utility.check_empty_string(self.name):
            raise ValidationError("Synonym cannot be empty or blank spaces")

    def clean(self):
        self.name = self.name.strip().lower()


@auditlogger.log
@push_notification.apply
class EntitySynonyms(Auditlog):
    bot = StringField(required=True)
    name = StringField(required=True)
    value = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    meta = {"indexes": [{"fields": ["$value", ("bot", "status")]}]}

    def validate(self, clean=True):
        if clean:
            self.clean()

        if Utility.check_empty_string(self.name) or Utility.check_empty_string(
            self.value
        ):
            raise ValidationError(
                "Synonym name and value cannot be empty or blank spaces"
            )

    def clean(self):
        self.name = self.name.strip().lower()
        self.value = self.value.strip()


@auditlogger.log
@push_notification.apply
class Lookup(Auditlog):
    name = StringField(required=True)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    meta = {"indexes": [{"fields": ["bot", ("bot", "status", "name")]}]}

    def validate(self, clean=True):
        if clean:
            self.clean()

        if Utility.check_empty_string(self.name):
            raise ValidationError("Lookup cannot be empty or blank spaces")

    def clean(self):
        self.name = self.name.strip().lower()


@auditlogger.log
@push_notification.apply
class LookupTables(Auditlog):
    name = StringField(required=True)
    value = StringField(required=True)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    meta = {"indexes": [{"fields": ["$value", ("bot", "status")]}]}

    def validate(self, clean=True):
        if clean:
            self.clean()

        if Utility.check_empty_string(self.name) or Utility.check_empty_string(
            self.value
        ):
            raise ValidationError(
                "Lookup name and value cannot be empty or blank spaces"
            )

    def clean(self):
        self.name = self.name.strip().lower()
        self.value = self.value.strip()


@auditlogger.log
@push_notification.apply
class RegexFeatures(Auditlog):
    name = StringField(required=True)
    pattern = StringField(required=True)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    meta = {"indexes": [{"fields": ["$pattern", ("bot", "status")]}]}

    def clean(self):
        self.name = self.name.strip().lower()

    def validate(self, clean=True):
        if clean:
            self.clean()

        if Utility.check_empty_string(self.name) or Utility.check_empty_string(
            self.pattern
        ):
            raise ValidationError(
                "Regex name and pattern cannot be empty or blank spaces"
            )
        else:
            try:
                re.compile(self.pattern)
            except Exception:
                raise AppException("invalid regular expression " + self.pattern)


@auditlogger.log
@push_notification.apply
class Intents(Auditlog):
    name = StringField(required=True)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)
    is_integration = BooleanField(default=False)
    use_entities = BooleanField(default=False)

    meta = {"indexes": [{"fields": ["bot", ("bot", "status")]}]}

    def validate(self, clean=True):
        if clean:
            self.clean()

        if Utility.check_empty_string(self.name):
            raise ValidationError("Intent Name cannot be empty or blank spaces")

    def clean(self):
        self.name = self.name.strip().lower()


@auditlogger.log
@push_notification.apply
class Entities(Auditlog):
    name = StringField(required=True)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    meta = {"indexes": [{"fields": ["bot", ("bot", "status")]}]}

    def clean(self):
        self.name = self.name.strip().lower()

    def validate(self, clean=True):
        if clean:
            self.clean()

        if Utility.check_empty_string(self.name):
            raise ValidationError("Entity Name cannot be empty or blank spaces")


@auditlogger.log
@push_notification.apply
class Forms(Auditlog):
    name = StringField(required=True)
    ignored_intents = ListField(StringField(), default=None)
    required_slots = ListField(StringField(), required=True)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    meta = {"indexes": [{"fields": ["bot", ("bot", "status", "name")]}]}

    def validate(self, clean=True):
        if clean:
            self.clean()

        if Utility.check_empty_string(self.name):
            raise ValidationError("Form name cannot be empty or blank spaces")

    def clean(self):
        self.name = self.name.strip().lower()
        for i in range(0, self.required_slots.__len__()):
            self.required_slots[i] = self.required_slots[i].lower()


@auditlogger.log
@push_notification.apply
class SlotMapping(Auditlog):
    slot = StringField(required=True)
    mapping = DictField(required=True)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)
    form_name = StringField(default=None)

    meta = {"indexes": [{"fields": ["bot", ("bot", "status")]}]}

    def clean(self):
        self.slot = self.slot.strip().lower()

        mapping_info = {"type": self.mapping["type"]}
        if self.mapping["type"] == SLOT_MAPPING_TYPE.FROM_ENTITY.value:
            mapping_info["entity"] = self.mapping.get("entity") or self.slot
            mapping_info["entity"] = mapping_info["entity"].lower()
        if self.mapping.get("value") is not None:
            mapping_info["value"] = self.mapping["value"]
        if self.mapping.get("intent"):
            on_intents = []
            for intent in self.mapping["intent"]:
                on_intents.append(intent.lower())
            mapping_info["intent"] = on_intents
        if self.mapping.get("not_intent"):
            not_intents = []
            for intent in self.mapping["not_intent"]:
                not_intents.append(intent.lower())
            mapping_info["not_intent"] = not_intents
        if self.mapping.get("conditions"):
            mapping_conditions = []
            for condition in self.mapping["conditions"]:
                if not Utility.check_empty_string(condition.get("active_loop")):
                    mapping_conditions.append({"active_loop": condition["active_loop"], "requested_slot": condition["requested_slot"]})
            if mapping_conditions:
                mapping_info["conditions"] = mapping_conditions
        self.mapping = mapping_info

    def validate(self, clean=True):
        from rasa.shared.core.slot_mappings import validate_slot_mappings
        from rasa.shared.core.constants import SLOT_MAPPINGS

        if not self.mapping or self.mapping == [{}]:
            raise ValueError("At least one mapping is required")
        if Utility.check_empty_string(self.slot):
            raise ValueError("Slot name cannot be empty or blank spaces")

        if clean:
            self.clean()

        try:
            validate_slot_mappings({self.slot: {SLOT_MAPPINGS: [self.mapping]}})
        except Exception as e:
            raise ValidationError(e)


@auditlogger.log
@push_notification.apply
class Utterances(Auditlog):
    name = StringField(required=True)
    form_attached = StringField(default=None)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    meta = {"indexes": [{"fields": ["bot", ("bot", "status")]}]}

    def validate(self, clean=True):
        if clean:
            self.clean()

        if Utility.check_empty_string(self.name):
            raise ValidationError("Utterance Name cannot be empty or blank spaces")

    def clean(self):
        self.name = self.name.strip().lower()


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
    buttons = ListField(EmbeddedDocumentField(ResponseButton), default=None)

    def validate(self, clean=True):
        if Utility.check_empty_string(self.text):
            raise ValidationError("Response text cannot be empty or blank spaces")
        Utility.validate_document_list(self.buttons)


class ResponseCustom(EmbeddedDocument):
    custom = DictField(required=True)

    def validate(self, clean=True):
        if not (isinstance(self.custom, dict) and self.custom):
            raise ValidationError("Utterance must be dict type and must not be empty")


@auditlogger.log
@push_notification.apply
class Responses(Auditlog):
    name = StringField(required=True)
    text = EmbeddedDocumentField(ResponseText)
    custom = EmbeddedDocumentField(ResponseCustom)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    meta = {
        "indexes": [{"fields": ["$text", ("bot", "status"), ("bot", "name", "status")]}]
    }

    def validate(self, clean=True):
        if clean:
            self.clean()

        if Utility.check_empty_string(self.name):
            raise ValidationError("Response name cannot be empty or blank spaces")
        elif not self.text and not self.custom:
            raise ValidationError("Either Text or Custom response must be present!")
        else:
            if self.text:
                self.text.validate()
            elif self.custom:
                self.custom.validate()

    def clean(self):
        self.name = self.name.strip().lower()


@auditlogger.log
@push_notification.apply
class SessionConfigs(Auditlog):
    sesssionExpirationTime = LongField(required=True, default=60)
    carryOverSlots = BooleanField(required=True, default=True)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)

    meta = {"indexes": [{"fields": ["bot"]}]}


@auditlogger.log
@push_notification.apply
class Slots(Auditlog):
    name = StringField(required=True)
    type = StringField(
        required=True,
        choices=[
            FloatSlot.type_name,
            CategoricalSlot.type_name,
            ListSlot.type_name,
            TextSlot.type_name,
            BooleanSlot.type_name,
            AnySlot.type_name,
        ],
    )
    initial_value = DynamicField()
    value_reset_delay = LongField()
    values = ListField(StringField(), default=None)
    max_value = FloatField()
    min_value = FloatField()
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)
    influence_conversation = BooleanField(default=False)
    _has_been_set = BooleanField(default=False)
    is_default = BooleanField(default=False)

    meta = {"indexes": [{"fields": ["bot", ("bot", "status", "name")]}]}

    def clean(self):
        self.name = self.name.strip().lower()

    def validate(self, clean=True):
        if clean:
            self.clean()

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
            if not isinstance(self.initial_value, int):
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
    name = StringField(default=None)
    type = StringField(
        required=True, choices=["user", "action", "form", "slot", "active_loop"]
    )
    value = DynamicField()
    entities = ListField(EmbeddedDocumentField(Entity), default=None)

    def validate(self, clean=True):
        if clean:
            self.clean()
        if self.type != "slot" and self.value is not None:
            raise ValidationError("Value is allowed only for slot events")
        if (
            self.type == "slot"
            and self.value is not None
            and not isinstance(self.value, (str, int, bool))
        ):
            raise ValidationError(
                "slot values must be either None or of type int, str or boolean"
            )
        if Utility.check_empty_string(self.name) and self.type != "active_loop":
            raise ValidationError("Empty name is allowed only for active_loop")

    def clean(self):
        if not Utility.check_empty_string(self.name):
            self.name = self.name.strip().lower()
        if self.entities:
            for entity in self.entities:
                entity.clean()

    def __eq__(self, other):
        return (
            isinstance(other, self.__class__)
            and self.name == other.name
            and self.type == other.type
            and self.value == other.value
            and self.entities == other.entities
        )


class StepFlowEvent(EmbeddedDocument):
    name = StringField(required=True)
    type = StringField(
        required=True, choices=[step_type.value for step_type in StoryStepType]
    )
    value = DynamicField()
    node_id = StringField(required=True)
    component_id = StringField(required=True)

    def validate(self, clean=True):
        if clean:
            self.clean()
        if Utility.check_empty_string(self.name):
            raise ValidationError("Name cannot be empty")
        if self.type != StoryStepType.slot.value and self.value is not None:
            raise ValidationError("Value is allowed only for slot events")
        if (
            self.type == StoryStepType.slot.value
            and self.value is not None
            and not isinstance(self.value, (str, int, bool))
        ):
            raise ValidationError(
                "slot values must be either None or of type int, str or boolean"
            )

    def clean(self):
        if not Utility.check_empty_string(self.name):
            self.name = self.name.strip().lower()


class MultiflowStoryEvents(EmbeddedDocument):
    step = EmbeddedDocumentField(StepFlowEvent, required=True)
    connections = ListField(EmbeddedDocumentField(StepFlowEvent))


class MultiFlowStoryMetadata(EmbeddedDocument):
    node_id = StringField(required=True)
    flow_type = StringField(
        default=StoryType.story.value,
        choices=[StoryType.story.value, StoryType.rule.value],
    )

    def clean(self):
        if Utility.check_empty_string(self.flow_type):
            self.flow_type = StoryType.story.value


@auditlogger.log
@push_notification.apply
class Stories(Auditlog):
    block_name = StringField(required=True)
    start_checkpoints = ListField(StringField(), required=True)
    end_checkpoints = ListField(StringField())
    events = ListField(EmbeddedDocumentField(StoryEvents), required=True)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)
    template_type = StringField(
        default=TemplateType.CUSTOM.value,
        choices=[template.value for template in TemplateType],
    )

    meta = {"indexes": [{"fields": ["bot", ("bot", "block_name", "status")]}]}

    def validate(self, clean=True):
        if clean:
            self.clean()

        from .utils import DataUtility

        if Utility.check_empty_string(self.block_name):
            raise ValidationError("Story name cannot be empty or blank spaces")
        elif not self.events:
            raise ValidationError("events cannot be empty")
        DataUtility.validate_flow_events(self.events, "STORY", self.block_name)

    def clean(self):
        self.block_name = self.block_name.strip().lower()
        for event in self.events:
            event.clean()


@auditlogger.log
@push_notification.apply
class MultiflowStories(Auditlog):
    block_name = StringField(required=True)
    start_checkpoints = ListField(StringField(), required=True)
    end_checkpoints = ListField(StringField())
    events = ListField(EmbeddedDocumentField(MultiflowStoryEvents))
    metadata = ListField(EmbeddedDocumentField(MultiFlowStoryMetadata), default=None)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)
    template_type = StringField(
        default=TemplateType.CUSTOM.value,
        choices=[template.value for template in TemplateType],
    )

    flow_tags = ListField(StringField(), default=[FlowTagType.chatbot_flow.value])



    meta = {"indexes": [{"fields": ["bot", ("bot", "status", "block_name")]}]}

    def validate(self, clean=True):
        if clean:
            self.clean()

        if Utility.check_empty_string(self.block_name):
            raise ValidationError("Story name cannot be empty or blank spaces")
        elif not self.events:
            raise ValidationError("events cannot be empty")
        for event in self.events:
            event.step.validate()
            for connection in event.connections or []:
                connection.validate()

    def clean(self):
        self.block_name = self.block_name.strip().lower()


@auditlogger.log
@push_notification.apply
class Rules(Auditlog):
    block_name = StringField(required=True)
    condition_events_indices = ListField(IntField(), default=[])
    start_checkpoints = ListField(StringField(), required=True)
    end_checkpoints = ListField(StringField())
    events = ListField(EmbeddedDocumentField(StoryEvents), required=True)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)
    template_type = StringField(
        default=TemplateType.CUSTOM.value,
        choices=[template.value for template in TemplateType],
    )
    flow_tags = ListField(StringField(), default=[FlowTagType.chatbot_flow.value])

    meta = {"indexes": [{"fields": ["bot", ("bot", "status", "block_name")]}]}

    def clean(self):
        self.block_name = self.block_name.strip().lower()
        for event in self.events:
            event.clean()

    def validate(self, clean=True):
        if clean:
            self.clean()
        from .utils import DataUtility

        if Utility.check_empty_string(self.block_name):
            raise ValidationError("rule name cannot be empty or blank spaces")
        elif not self.events:
            raise ValidationError("events cannot be empty")
        DataUtility.validate_flow_events(self.events, "RULE", self.block_name)


@auditlogger.log
@push_notification.apply
class Configs(Auditlog):
    recipe = StringField(required=True, default="default.v1")
    language = StringField(required=True, default="en")
    pipeline = DynamicField(required=True)
    policies = ListField(DictField(), required=True)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    meta = {"indexes": [{"fields": ["bot", ("bot", "status")]}]}


class EndPointHistory(EmbeddedDocument):
    url = StringField(required=True)
    token = StringField()

    def validate(self, clean=True):
        if Utility.check_empty_string(self.url):
            raise ValidationError("url cannot be blank or empty spaces")


class EndPointAction(EmbeddedDocument):
    url = StringField(required=True)

    def validate(self, clean=True):
        if isinstance(url(self.url, simple_host=True), ValidationFailure):
            raise AppException("Invalid Action server url ")


class EndPointBot(EmbeddedDocument):
    url = StringField(required=True)
    token = StringField()
    token_type = StringField()

    def validate(self, clean=True):
        if isinstance(url(self.url, simple_host=True), ValidationFailure):
            raise AppException("Invalid Bot server url")


@auditlogger.log
@push_notification.apply
class DemoRequestLogs(Document):
    first_name = StringField(required=True)
    last_name = StringField(required=True)
    email = StringField(required=True)
    phone = StringField(default=None)
    message = StringField(default=None)
    recaptcha_response = StringField(default=None)
    status = StringField(default=DEMO_REQUEST_STATUS.REQUEST_RECEIVED.value,
                         choices=[type.value for type in DEMO_REQUEST_STATUS])
    timestamp = DateTimeField(default=datetime.utcnow)

    def validate(self, clean=True):
        from validators import email

        if clean:
            self.clean()

        if Utility.check_empty_string(self.first_name):
            raise ValidationError("first_name cannot be empty")
        if Utility.check_empty_string(self.last_name):
            raise ValidationError("last_name cannot be empty")
        if isinstance(email(self.email), ValidationFailure):
            raise ValidationError("Invalid email address")
        if self.status not in [type.value for type in DEMO_REQUEST_STATUS]:
            raise ValidationError("Invalid demo request status")


@auditlogger.log
@push_notification.apply
class Endpoints(Auditlog):
    bot_endpoint = EmbeddedDocumentField(EndPointBot)
    action_endpoint = EmbeddedDocumentField(EndPointAction)
    history_endpoint = EmbeddedDocumentField(EndPointHistory)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)

    meta = {"indexes": [{"fields": ["bot"]}]}

    def validate(self, clean=True):
        if self.bot_endpoint:
            self.bot_endpoint.validate()

        if self.history_endpoint:
            self.history_endpoint.validate()

        if self.action_endpoint:
            self.action_endpoint.validate()


@auditlogger.log
@push_notification.apply
class ModelTraining(Auditlog):
    bot = StringField(required=True)
    user = StringField(required=True)
    status = StringField(default=EVENT_STATUS.INITIATED.value)
    start_timestamp = DateTimeField(default=None)
    end_timestamp = DateTimeField(default=None)
    model_path = StringField(default=None)
    exception = StringField(default=None)
    model_config = DictField()

    meta = {"indexes": [{"fields": ["bot", ("bot", "status", "-start_timestamp")]}]}


@auditlogger.log
@push_notification.apply
class ModelDeployment(Auditlog):
    bot = StringField(required=True)
    user = StringField(required=True)
    model = StringField(default=None)
    url = StringField(default=None)
    status = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)

    meta = {"indexes": [{"fields": ["bot"]}]}


class TrainingExamplesTrainingDataGenerator(EmbeddedDocument):
    training_example = StringField(required=True)
    is_persisted = BooleanField(default=False)


class TrainingDataGeneratorResponse(EmbeddedDocument):
    intent = StringField(required=True)
    training_examples = ListField(
        EmbeddedDocumentField(TrainingExamplesTrainingDataGenerator), required=True
    )
    response = StringField(required=True)


class LLMSettings(EmbeddedDocument):
    enable_faq = BooleanField(default=False)
    provider = StringField(
        default=LLMResourceProvider.openai.value,
        choices=[LLMResourceProvider.azure.value, LLMResourceProvider.openai.value],
    )
    embeddings_model_id = StringField()
    chat_completion_model_id = StringField()
    api_version = StringField()


class Analytics(EmbeddedDocument):
    fallback_intent = StringField(default=DEFAULT_NLU_FALLBACK_INTENT_NAME)


@auditlogger.log
@push_notification.apply
class BotSettings(Auditlog):
    is_billed = BooleanField(default=False)
    ignore_utterances = BooleanField(default=False)
    force_import = BooleanField(default=False)
    rephrase_response = BooleanField(default=False)
    website_data_generator_depth_search_limit = IntField(default=2)
    llm_settings = EmbeddedDocumentField(LLMSettings, default=LLMSettings())
    analytics = EmbeddedDocumentField(Analytics, default=Analytics())
    chat_token_expiry = IntField(default=30)
    refresh_token_expiry = IntField(default=60)
    whatsapp = StringField(
        default="meta", choices=["meta", WhatsappBSPTypes.bsp_360dialog.value]
    )
    notification_scheduling_limit = IntField(default=4)
    retry_broadcasting_limit = IntField(default=3)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)
    training_limit_per_day = IntField(default=5)
    test_limit_per_day = IntField(default=5)
    data_importer_limit_per_day = IntField(default=5)
    content_importer_limit_per_day = IntField(default=5)
    multilingual_limit_per_day = IntField(default=2)
    data_generation_limit_per_day = IntField(default=3)
    dynamic_broadcast_execution_timeout = IntField(default=21600)
    cognition_collections_limit = IntField(default=3)
    cognition_columns_per_collection_limit = IntField(default=5)
    integrations_per_user_limit = IntField(default=3)
    live_agent_enabled = BooleanField(default=False)
    max_actions_per_parallel_action = IntField(default=5)
    catalog_sync_limit_per_day = IntField(default=5)

    meta = {"indexes": [{"fields": ["bot", ("bot", "status")]}]}

    def validate(self, clean=True):
        if clean:
            self.clean()

        if self.refresh_token_expiry <= self.chat_token_expiry:
            raise ValidationError(
                "refresh_token_expiry must be greater than chat_token_expiry!"
            )


@auditlogger.log
@push_notification.apply
class ChatClientConfig(Auditlog):
    config = DictField(required=True)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)
    white_listed_domain = ListField(StringField(), default=None)

    meta = {"indexes": [{"fields": ["bot", ("bot", "status")]}]}

    def validate(self, clean=True):
        if isinstance(self.white_listed_domain, list):
            for val in self.white_listed_domain:
                if val != "*" and isinstance(domain(val), ValidationFailure):
                    raise ValidationError("One of the domain is invalid")


@auditlogger.log
@push_notification.apply
class ConversationsHistoryDeleteLogs(Auditlog):
    bot = StringField(required=True)
    user = StringField(required=True)
    sender_id = StringField(default=None)
    till_date = DateTimeField(default=None)
    status = StringField(default=None)
    start_timestamp = DateTimeField(default=None)
    end_timestamp = DateTimeField(default=None)
    exception = StringField(default=None)

    meta = {"indexes": [{"fields": ["bot", ("bot", "status", "-start_timestamp")]}]}


@auditlogger.log
@push_notification.apply
class BotAssets(Auditlog):
    asset_type = StringField(required=True)
    path = StringField(required=True)
    url = StringField(required=True)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    meta = {"indexes": [{"fields": ["bot", ("bot", "status")]}]}


@auditlogger.log
class KeyVault(Auditlog):
    key = StringField(required=True)
    value = StringField(required=True)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)

    meta = {"indexes": [{"fields": ["bot"]}]}

    @classmethod
    def pre_save_post_validation(cls, sender, document, **kwargs):
        if not Utility.check_empty_string(document.value):
            document.value = Utility.encrypt_message(document.value)


from mongoengine import signals

signals.pre_save_post_validation.connect(
    KeyVault.pre_save_post_validation, sender=KeyVault
)


@auditlogger.log
@push_notification.apply
class EventConfig(Auditlog):
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    ws_url = StringField(required=True)
    headers = StringField()
    method = StringField(choices=["POST", "GET", "PATCH"])

    meta = {"indexes": [{"fields": ["bot"]}]}

    def validate(self, clean=True):
        if Utility.check_empty_string(self.ws_url):
            raise ValidationError("Event url can not be empty")

    @classmethod
    def pre_save_post_validation(self, sender, document, **kwargs):
        document.headers = Utility.encrypt_message(json.dumps(document.headers))


signals.pre_save_post_validation.connect(
    EventConfig.pre_save_post_validation, sender=EventConfig
)
signals.pre_save_post_validation.connect(
    KeyVault.pre_save_post_validation, sender=KeyVault
)


@push_notification.apply
class UserOrgMappings(Document):
    user = StringField(required=True)
    organization = StringField(required=True)
    feature_type = StringField(required=True)
    value = DynamicField(default=False)
    timestamp = DateTimeField(default=datetime.utcnow)

    meta = {"indexes": [{"fields": ["user", ("user", "feature_type", "organization")]}]}



class GlobalSlots(Auditlog):
    entry_type = StringField(default=GlobalSlotsEntryType.agentic_flow.value, choices=[entry_type.value for entry_type in GlobalSlotsEntryType])
    slots = DictField()
    sender_id = StringField(required=True)
    bot = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)

    meta = {"indexes": [{"fields": ["bot", ("bot", "sender_id", "entry_type")]}]}





class UserMediaData(Auditlog):
    media_id = StringField(required=True)
    media_url = StringField()
    filename = StringField(required=True)
    extension = StringField(required=True)
    output_filename = StringField()
    summary = StringField()
    upload_status = StringField(default=UserMediaUploadStatus.processing.value,
                                choices=[e.value for e in UserMediaUploadStatus])
    upload_type = StringField(default=UserMediaUploadType.user_uploaded.value,
                              choices=[e.value for e in UserMediaUploadType])
    filesize = IntField(default=0)
    additional_log = StringField()
    sender_id = StringField(required=True)
    bot = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    external_upload_info = DictField()


    meta = {"indexes": [{"fields": ["bot", ("bot", "sender_id"), "media_id"]}]}


class PetpoojaSyncConfig(EmbeddedDocument):
    process_push_menu = BooleanField(default=False)
    process_item_toggle = BooleanField(default=False)

@auditlogger.log
@push_notification.apply
class POSIntegrations(Auditlog):
    bot = StringField(required=True)
    provider = StringField(required=True)
    config = DictField(required=True)
    sync_type = StringField(required=True, default=None)
    smart_catalog_enabled = BooleanField(default=False)
    meta_enabled = BooleanField(default=False)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    sync_options = GenericEmbeddedDocumentField(required=True)

    meta = {"indexes": [{"fields": ["bot", "provider"]}]}