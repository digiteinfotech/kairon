import json
import re
from datetime import datetime
from .constant import EVENT_STATUS, SLOT_MAPPING_TYPE, TrainingDataSourceType
from .base_data import Auditlog
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
    FloatField
)
from rasa.shared.core.slots import (
    CategoricalSlot,
    FloatSlot,
    UnfeaturizedSlot,
    ListSlot,
    TextSlot,
    BooleanSlot, AnySlot,
)
from validators import url, ValidationFailure
from kairon.shared.data.signals import push_notification, auditlogger
from kairon.exceptions import AppException
from kairon.shared.utils import Utility
from kairon.shared.models import TemplateType, StoryStepType
from validators import domain


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
        return isinstance(other, self.__class__) and self.start == other.start and self.end == other.end and self.value == other.value \
               and self.entity == other.entity


@push_notification.apply
class TrainingExamples(Document):
    intent = StringField(required=True)
    text = StringField(required=True)
    bot = StringField(required=True)
    entities = ListField(EmbeddedDocumentField(Entity), default=None)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    meta = {"indexes": [{"fields": ["$text", ("bot", "status"), ("bot", "intent", "status")]}]}

    def validate(self, clean=True):
        if clean:
            self.clean()

        if self.entities:
            for ent in self.entities:
                ent.validate()
                extracted_ent = self.text[ent.start: ent.end]
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


@push_notification.apply
class EntitySynonyms(Document):
    bot = StringField(required=True)
    name = StringField(required=True)
    value = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    meta = {"indexes": [{"fields": ["$value"]}]}

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
        self.name = self.name.strip().strip().lower()
        self.value = self.value.strip()


@push_notification.apply
class LookupTables(Document):
    name = StringField(required=True)
    value = StringField(required=True)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    meta = {"indexes": [{"fields": ["$value"]}]}

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


@push_notification.apply
class RegexFeatures(Document):
    name = StringField(required=True)
    pattern = StringField(required=True)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    meta = {"indexes": [{"fields": ["$pattern"]}]}

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


@push_notification.apply
class Entities(Document):
    name = StringField(required=True)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

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
    mapping = ListField(required=True)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    def clean(self):
        self.slot = self.slot.strip().lower()
        mapping = []
        for slot_mapping in self.mapping:
            mapping_info = {'type': slot_mapping['type']}
            if slot_mapping['type'] == SLOT_MAPPING_TYPE.FROM_ENTITY.value:
                mapping_info['entity'] = slot_mapping.get('entity') or self.slot
                mapping_info['entity'] = mapping_info['entity'].lower()
            if slot_mapping.get('value') is not None:
                mapping_info['value'] = slot_mapping['value']
            if slot_mapping.get('intent'):
                on_intents = []
                for intent in slot_mapping['intent']:
                    on_intents.append(intent.lower())
                mapping_info['intent'] = on_intents
            if slot_mapping.get('not_intent'):
                not_intents = []
                for intent in slot_mapping['not_intent']:
                    not_intents.append(intent.lower())
                mapping_info['not_intent'] = not_intents
            mapping.append(mapping_info)
        self.mapping = mapping

    def validate(self, clean=True):
        from rasa.shared.core.domain import _validate_slot_mappings

        if not self.mapping or self.mapping == [{}]:
            raise ValueError("At least one mapping is required")
        if Utility.check_empty_string(self.slot):
            raise ValueError("Slot name cannot be empty or blank spaces")

        if clean:
            self.clean()

        try:
            _validate_slot_mappings({'form_name': {self.slot: self.mapping}})
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

    meta = {"indexes": [{"fields": ["$text", ("bot", "status"), ("bot", "name", "status")]}]}

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


@push_notification.apply
class SessionConfigs(Document):
    sesssionExpirationTime = LongField(required=True, default=60)
    carryOverSlots = BooleanField(required=True, default=True)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)


@auditlogger.log
@push_notification.apply
class Slots(Auditlog):
    name = StringField(required=True)
    type = StringField(
        required=True,
        choices=[
            FloatSlot.type_name,
            CategoricalSlot.type_name,
            UnfeaturizedSlot.type_name,
            ListSlot.type_name,
            TextSlot.type_name,
            BooleanSlot.type_name,
            AnySlot.type_name
        ],
    )
    initial_value = DynamicField()
    value_reset_delay = LongField()
    auto_fill = BooleanField(default=True)
    values = ListField(StringField(), default=None)
    max_value = FloatField()
    min_value = FloatField()
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)
    influence_conversation = BooleanField(default=False)
    _has_been_set = BooleanField(default=False)

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
    type = StringField(required=True, choices=["user", "action", "form", "slot", "active_loop"])
    value = StringField()
    entities = ListField(EmbeddedDocumentField(Entity), default=None)

    def validate(self, clean=True):
        if clean:
            self.clean()
        if not Utility.check_empty_string(self.value) and self.type != 'slot':
            raise ValidationError("Value is allowed only for slot")
        if Utility.check_empty_string(self.name) and self.type != 'active_loop':
            raise ValidationError("Empty name is allowed only for active_loop")

    def clean(self):
        if not Utility.check_empty_string(self.name):
            self.name = self.name.strip().lower()
        if self.entities:
            for entity in self.entities:
                entity.clean()

    def __eq__(self, other):
        return isinstance(other, self.__class__) and self.name == other.name and self.type == other.type and self.value == other.value \
               and self.entities == other.entities


class StepFlowEvent(EmbeddedDocument):
    name = StringField(required=True)
    type = StringField(required=True, choices=[step_type.value for step_type in StoryStepType])
    node_id = StringField(required=True)
    component_id = StringField(required=True)

    def validate(self, clean=True):
        if clean:
            self.clean()
        if Utility.check_empty_string(self.name):
            raise ValidationError("Name cannot be empty")

    def clean(self):
        if not Utility.check_empty_string(self.name):
            self.name = self.name.strip().lower()


class MultiflowStoryEvents(EmbeddedDocument):
    step = EmbeddedDocumentField(StepFlowEvent, required=True)
    connections = ListField(EmbeddedDocumentField(StepFlowEvent))


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
    template_type = StringField(default=TemplateType.CUSTOM.value, choices=[template.value for template in TemplateType])

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
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)
    template_type = StringField(default=TemplateType.CUSTOM.value, choices=[template.value for template in TemplateType])

    meta = {"indexes": [{"fields": ["bot", ("bot", "block_name")]}]}

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
    template_type = StringField(default=TemplateType.CUSTOM.value, choices=[template.value for template in TemplateType])

    meta = {"indexes": [{"fields": ["bot", ("bot", "block_name")]}]}

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
class BotContent(Auditlog):
    data = StringField(required=True)
    user = StringField(required=True)
    bot = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)

    meta = {"indexes": [{"fields": ["bot"]}]}


@auditlogger.log
@push_notification.apply
class Configs(Auditlog):
    language = StringField(required=True, default="en")
    pipeline = DynamicField(required=True)
    policies = ListField(DictField(), required=True)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)


class EndPointHistory(EmbeddedDocument):
    url = StringField(required=True)
    token = StringField()

    def validate(self, clean=True):
        if Utility.check_empty_string(self.url):
            raise ValidationError("url cannot be blank or empty spaces")


class EndPointAction(EmbeddedDocument):
    url = StringField(required=True)

    def validate(self, clean=True):
        if isinstance(url(self.url), ValidationFailure):
            raise AppException("Invalid Action server url ")


class EndPointBot(EmbeddedDocument):
    url = StringField(required=True)
    token = StringField()
    token_type = StringField()

    def validate(self, clean=True):
        if isinstance(url(self.url), ValidationFailure):
            raise AppException("Invalid Bot server url")


@auditlogger.log
@push_notification.apply
class Endpoints(Auditlog):
    bot_endpoint = EmbeddedDocumentField(EndPointBot)
    action_endpoint = EmbeddedDocumentField(EndPointAction)
    history_endpoint = EmbeddedDocumentField(EndPointHistory)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)

    def validate(self, clean=True):
        if self.bot_endpoint:
            self.bot_endpoint.validate()

        if self.history_endpoint:
            self.history_endpoint.validate()

        if self.action_endpoint:
            self.action_endpoint.validate()


@push_notification.apply
class ModelTraining(Document):
    bot = StringField(required=True)
    user = StringField(required=True)
    status = StringField(default=EVENT_STATUS.INITIATED.value)
    start_timestamp = DateTimeField(default=None)
    end_timestamp = DateTimeField(default=None)
    model_path = StringField(default=None)
    exception = StringField(default=None)
    model_config = DictField()


@push_notification.apply
class ModelDeployment(Document):
    bot = StringField(required=True)
    user = StringField(required=True)
    model = StringField(default=None)
    url = StringField(default=None)
    status = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)


class TrainingExamplesTrainingDataGenerator(EmbeddedDocument):
    training_example = StringField(required=True)
    is_persisted = BooleanField(default=False)


class TrainingDataGeneratorResponse(EmbeddedDocument):
    intent = StringField(required=True)
    training_examples = ListField(EmbeddedDocumentField(TrainingExamplesTrainingDataGenerator), required=True)
    response = StringField(required=True)


@push_notification.apply
class TrainingDataGenerator(Document):
    bot = StringField(required=True)
    user = StringField(required=True)
    document_path = StringField(default=None)
    source_type = StringField(
        choices=[TrainingDataSourceType.document.value, TrainingDataSourceType.website.value],
        default=TrainingDataSourceType.document.value)
    status = StringField(default=EVENT_STATUS.INITIATED.value)
    start_timestamp = DateTimeField(default=None)
    last_update_timestamp = DateTimeField(default=None)
    end_timestamp = DateTimeField(default=None)
    response = ListField(EmbeddedDocumentField(TrainingDataGeneratorResponse), default=None)
    exception = StringField(default=None)


@auditlogger.log
@push_notification.apply
class BotSettings(Auditlog):
    ignore_utterances = BooleanField(default=False)
    force_import = BooleanField(default=False)
    rephrase_response = BooleanField(default=False)
    website_data_generator_depth_search_limit = IntField(default=2)
    enable_gpt_llm_faq = BooleanField(default=False)
    chat_token_expiry = IntField(default=30)
    refresh_token_expiry = IntField(default=60)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    def validate(self, clean=True):
        if clean:
            self.clean()

        if self.refresh_token_expiry <= self.chat_token_expiry:
            raise ValidationError("refresh_token_expiry must be greater than chat_token_expiry!")


@auditlogger.log
@push_notification.apply
class ChatClientConfig(Auditlog):
    config = DictField(required=True)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)
    white_listed_domain = ListField(StringField(), default=None)

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


@auditlogger.log
@push_notification.apply
class BotAssets(Auditlog):
    asset_type = StringField(required=True)
    path = StringField(required=True)
    url = StringField(required=True)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow())
    status = BooleanField(default=True)


class KeyVault(Document):
    key = StringField(required=True)
    value = StringField(required=True)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow())

    @classmethod
    def pre_save_post_validation(cls, sender, document, **kwargs):
        if not Utility.check_empty_string(document.value):
            document.value = Utility.encrypt_message(document.value)


from mongoengine import signals

signals.pre_save_post_validation.connect(KeyVault.pre_save_post_validation, sender=KeyVault)


@auditlogger.log
@push_notification.apply
class EventConfig(Auditlog):
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow())
    ws_url = StringField(required=True)
    headers = StringField()
    method = StringField(choices=["POST", "GET", "PATCH"])

    def validate(self, clean=True):
        if Utility.check_empty_string(self.ws_url):
            raise ValidationError("Event url can not be empty")

    @classmethod
    def pre_save_post_validation(self, sender, document, **kwargs):
        document.headers = Utility.encrypt_message(json.dumps(document.headers))


signals.pre_save_post_validation.connect(EventConfig.pre_save_post_validation, sender=EventConfig)
signals.pre_save_post_validation.connect(KeyVault.pre_save_post_validation, sender=KeyVault)

@push_notification.apply
class UserOrgMappings(Document):
    user = StringField(required=True)
    organization = StringField(required=True)
    feature_type = StringField(required=True)
    value = DynamicField(default=False)
    timestamp = DateTimeField(default=datetime.utcnow())
