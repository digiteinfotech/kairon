from datetime import datetime

from mongoengine import (
    EmbeddedDocument,
    EmbeddedDocumentField,
    EmbeddedDocumentListField,
    StringField,
    DateTimeField,
    BooleanField,
    IntField,
    ListField,
    DictField,
    DynamicField,
    DynamicDocument,
    FloatField,
)
from mongoengine.errors import ValidationError
from validators import email
from validators import url
from validators.utils import ValidationError as ValidationFailure

from kairon.shared.actions.models import (
    ActionType,
    ActionParameterType,
    HttpRequestContentType,
    EvaluationType,
    DispatchType,
    DbQueryValueType,
    DbActionOperationType, UserMessageType,
)
from kairon.shared.constants import SLOT_SET_TYPE, FORM_SLOT_SET_TYPE
from kairon.shared.data.audit.data_objects import Auditlog
from kairon.shared.data.constant import (
    KAIRON_TWO_STAGE_FALLBACK,
    FALLBACK_MESSAGE,
    DEFAULT_NLU_FALLBACK_RESPONSE,
    DEFAULT_LLM
)
from kairon.shared.data.signals import push_notification, auditlogger
from kairon.shared.models import LlmPromptType, LlmPromptSource
from kairon.shared.utils import Utility


class HttpActionRequestBody(EmbeddedDocument):
    key = StringField(required=True)
    value = StringField(default="")
    parameter_type = StringField(
        default=ActionParameterType.value,
        choices=[p_type.value for p_type in ActionParameterType],
    )
    encrypt = BooleanField(default=False)

    meta = {"allow_inheritance": True}

    def clean(self):
        from .utils import ActionUtility

        if (
            self.parameter_type == ActionParameterType.slot.value
            and not ActionUtility.is_empty(self.value)
        ):
            self.value = self.value.lower()

        if self.parameter_type == ActionParameterType.key_vault.value:
            self.encrypt = True

    def validate(self, clean=True):
        from .utils import ActionUtility

        if clean:
            self.clean()

        if ActionUtility.is_empty(self.key):
            raise ValidationError("key in http action parameters cannot be empty")
        if (
            self.parameter_type == ActionParameterType.slot.value
            and ActionUtility.is_empty(self.value)
        ):
            raise ValidationError("Provide name of the slot as value")
        if (
            self.parameter_type == ActionParameterType.key_vault.value
            and ActionUtility.is_empty(self.value)
        ):
            raise ValidationError("Provide key from key vault as value")

    def __eq__(self, other):
        return (
            isinstance(other, self.__class__)
            and self.key == other.key
            and self.parameter_type == other.parameter_type
            and self.value == other.value
        )


class SetSlotsFromResponse(EmbeddedDocument):
    name = StringField(required=True)
    value = StringField(required=True)
    evaluation_type = StringField(
        default=EvaluationType.expression.value,
        choices=[p_type.value for p_type in EvaluationType],
    )


class HttpActionResponse(EmbeddedDocument):
    value = StringField(default=None)
    dispatch = BooleanField(default=True)
    evaluation_type = StringField(
        default=EvaluationType.expression.value,
        choices=[p_type.value for p_type in EvaluationType],
    )
    dispatch_type = StringField(
        default=DispatchType.text.value,
        choices=[d_type.value for d_type in DispatchType],
    )

    def validate(self, clean=True):
        from .utils import ActionUtility

        if self.dispatch_type not in [DispatchType.text.value, DispatchType.json.value]:
            raise ValidationError("Invalid dispatch_type")
        if self.dispatch and ActionUtility.is_empty(self.value):
            raise ValidationError("response is required for dispatch")


@auditlogger.log
@push_notification.apply
class PyscriptActionConfig(Auditlog):
    name = StringField(required=True)
    source_code = StringField(required=True)
    dispatch_response = BooleanField(default=True)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    def validate(self, clean=True):
        if clean:
            self.clean()

        if Utility.check_empty_string(self.name):
            raise ValidationError("Action name cannot be empty")
        if Utility.check_empty_string(self.source_code):
            raise ValidationError("Source code cannot be empty")


@auditlogger.log
@push_notification.apply
class HttpActionConfig(Auditlog):
    action_name = StringField(required=True)
    http_url = StringField(required=True)
    request_method = StringField(required=True)
    content_type = StringField(
        default=HttpRequestContentType.json.value,
        choices=[c_type.value for c_type in HttpRequestContentType],
    )
    params_list = ListField(
        EmbeddedDocumentField(HttpActionRequestBody), required=False
    )
    dynamic_params = StringField(default=None)
    headers = ListField(EmbeddedDocumentField(HttpActionRequestBody), required=False)
    response = EmbeddedDocumentField(HttpActionResponse, default=HttpActionResponse())
    set_slots = ListField(EmbeddedDocumentField(SetSlotsFromResponse))
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    meta = {"indexes": [{"fields": ["bot", ("bot", "status", "action_name")]}]}

    def validate(self, clean=True):
        from kairon.shared.actions.utils import ActionUtility

        if clean:
            self.clean()

        if self.action_name is None or not self.action_name.strip():
            raise ValidationError("Action name cannot be empty")
        if self.request_method.upper() not in ("GET", "POST", "PUT", "DELETE"):
            raise ValidationError("Invalid HTTP method")
        if ActionUtility.is_empty(self.http_url):
            raise ValidationError("URL cannot be empty")
        if isinstance(url(self.http_url, simple_host=True), ValidationFailure):
            raise ValidationError("URL is malformed")
        for param in self.headers:
            param.validate()
        for param in self.params_list:
            param.validate()
        self.response.validate()

    def clean(self):
        self.action_name = self.action_name.strip().lower()

    @classmethod
    def pre_save_post_validation(cls, sender, document, **kwargs):
        from kairon.shared.actions.utils import ActionUtility

        for param in document.headers:
            if (
                param.encrypt is True
                and param.parameter_type == ActionParameterType.value.value
            ):
                if not ActionUtility.is_empty(param.value):
                    param.value = Utility.encrypt_message(param.value)

        for param in document.params_list:
            if (
                param.encrypt is True
                and param.parameter_type == ActionParameterType.value.value
            ):
                if not ActionUtility.is_empty(param.value):
                    param.value = Utility.encrypt_message(param.value)


class DbQuery(EmbeddedDocument):
    type = StringField(
        required=True, choices=[op_type.value for op_type in DbQueryValueType]
    )
    value = DynamicField(default=None)

    def validate(self, clean=True):
        if Utility.check_empty_string(self.type):
            raise ValidationError("payload type is required")


@auditlogger.log
@push_notification.apply
class DatabaseAction(Auditlog):
    name = StringField(required=True)
    collection = StringField(required=True)
    query_type = StringField(required=True, choices=[payload.value for payload in DbActionOperationType])
    payload = EmbeddedDocumentField(DbQuery, required=True)
    response = EmbeddedDocumentField(HttpActionResponse, default=HttpActionResponse())
    set_slots = ListField(EmbeddedDocumentField(SetSlotsFromResponse))
    db_type = StringField(required=True, default="qdrant")
    failure_response = StringField(default="I have failed to process your request.")
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    def validate(self, clean=True):
        if clean:
            self.clean()

        if self.name is None or not self.name.strip():
            raise ValidationError("Action name cannot be empty")
        if not self.query_type or self.query_type is None:
            raise ValidationError("query type is required")
        self.response.validate()
        self.payload.validate()


class ActionServerLogs(DynamicDocument):
    type = StringField()
    intent = StringField()
    action = StringField()
    sender = StringField()
    headers = DictField()
    url = StringField()
    request_method = StringField()
    request_params = DynamicField()
    api_response = StringField()
    bot_response = StringField()
    exception = StringField()
    messages = DynamicField()
    bot = StringField()
    timestamp = DateTimeField(default=datetime.utcnow)
    status = StringField(default="SUCCESS")

    meta = {"indexes": [{"fields": ["bot", ("bot", "-timestamp")]}]}


@auditlogger.log
@push_notification.apply
class Actions(Auditlog):
    name = StringField(required=True)
    type = StringField(choices=[type.value for type in ActionType], default=None)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    meta = {"indexes": [{"fields": ["bot", ("bot", "name", "status")]}]}

    def clean(self):
        self.name = self.name.strip().lower()

    def validate(self, clean=True):
        if clean:
            self.clean()

        from .utils import ActionUtility

        if ActionUtility.is_empty(self.name):
            raise ValidationError("Action name cannot be empty or blank spaces")

        if self.name.startswith("utter_"):
            raise ValidationError("Action name cannot start with utter_")


class SetSlots(EmbeddedDocument):
    name = StringField(required=True)
    type = StringField(required=True, choices=[type.value for type in SLOT_SET_TYPE])
    value = DynamicField()

    def validate(self, clean=True):
        if clean:
            self.clean()

    def clean(self):
        self.name = self.name.strip().lower()

    def __eq__(self, other):
        return (
            isinstance(other, self.__class__)
            and self.name == other.name
            and self.type == other.type
            and self.value == other.value
        )


@auditlogger.log
@push_notification.apply
class SlotSetAction(Auditlog):
    name = StringField(required=True)
    set_slots = ListField(EmbeddedDocumentField(SetSlots), required=True)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    meta = {"indexes": [{"fields": ["bot", ("bot", "name", "status")]}]}

    def validate(self, clean=True):
        if clean:
            self.clean()

    def clean(self):
        self.name = self.name.strip().lower()
        for slot_to_set in self.set_slots:
            slot_to_set.validate()


class FormSlotSet(EmbeddedDocument):
    type = StringField(
        default=FORM_SLOT_SET_TYPE.current.value,
        choices=[type.value for type in FORM_SLOT_SET_TYPE],
    )
    value = DynamicField()

    def validate(self, clean=True):
        if self.type not in [
            FORM_SLOT_SET_TYPE.current.value,
            FORM_SLOT_SET_TYPE.custom.value,
            FORM_SLOT_SET_TYPE.slot.value,
        ]:
            raise ValidationError("Invalid form_slot_set_type")


@auditlogger.log
@push_notification.apply
class FormValidationAction(Auditlog):
    name = StringField(required=True)
    slot = StringField(required=True)
    is_required = BooleanField(default=True)
    validation_semantic = StringField(default=None)
    valid_response = StringField(default=None)
    invalid_response = StringField(default=None)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)
    slot_set = EmbeddedDocumentField(FormSlotSet, default=FormSlotSet())

    meta = {"indexes": [{"fields": ["bot", ("bot", "name", "status")]}]}

    def clean(self):
        self.name = self.name.strip().lower()
        self.slot = self.slot.strip().lower()

    def validate(self, clean=True):
        if clean:
            self.clean()


class CustomActionRequestParameters(HttpActionRequestBody):
    value = StringField(required=True)
    parameter_type = StringField(
        default=ActionParameterType.value,
        choices=[
            ActionParameterType.value,
            ActionParameterType.slot,
            ActionParameterType.key_vault,
            ActionParameterType.sender_id,
        ],
    )


@auditlogger.log
@push_notification.apply
class EmailActionConfig(Auditlog):
    action_name = StringField(required=True)
    smtp_url = StringField(required=True)
    smtp_port = IntField(required=True)
    smtp_userid = EmbeddedDocumentField(CustomActionRequestParameters)
    smtp_password = EmbeddedDocumentField(CustomActionRequestParameters, required=True)
    from_email = StringField(required=True)
    subject = StringField(required=True)
    to_email = ListField(StringField(), required=True)
    response = StringField(required=True)
    custom_text = EmbeddedDocumentField(CustomActionRequestParameters)
    tls = BooleanField(default=False)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    meta = {"indexes": [{"fields": ["bot", ("bot", "action_name", "status")]}]}

    def validate(self, clean=True):
        from kairon.shared.actions.utils import ActionUtility

        if clean:
            self.clean()

        if ActionUtility.is_empty(self.action_name):
            raise ValidationError("Action name cannot be empty")
        if ActionUtility.is_empty(self.smtp_url):
            raise ValidationError("URL cannot be empty")
        if not Utility.validate_smtp(self.smtp_url, self.smtp_port):
            raise ValidationError("Invalid SMTP url")
        elif isinstance(email(self.from_email), ValidationFailure):
            raise ValidationError("Invalid From or To email address")
        else:
            for to_email in self.to_email:
                if isinstance(email(to_email), ValidationFailure):
                    raise ValidationError("Invalid From or To email address")

        if self.custom_text and self.custom_text.parameter_type not in {ActionParameterType.value, ActionParameterType.slot}:
            raise ValidationError("custom_text can only be of type value or slot!")

    def clean(self):
        self.action_name = self.action_name.strip().lower()
        if self.smtp_userid:
            self.smtp_userid.key = "smtp_userid"
        if self.smtp_password:
            self.smtp_password.key = "smtp_password"
        if self.custom_text:
            self.custom_text.key = "custom_text"


@auditlogger.log
@push_notification.apply
class GoogleSearchAction(Auditlog):
    name = StringField(required=True)
    api_key = EmbeddedDocumentField(CustomActionRequestParameters, default=None)
    search_engine_id = StringField(default=None)
    website = StringField(default=None)
    failure_response = StringField(default="I have failed to process your request.")
    num_results = IntField(default=1)
    dispatch_response = BooleanField(default=True)
    set_slot = StringField()
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    meta = {"indexes": [{"fields": ["bot", ("bot", "name", "status")]}]}

    def validate(self, clean=True):
        if clean:
            self.clean()

    def clean(self):
        self.name = self.name.strip().lower()
        if self.api_key:
            self.api_key.key = "api_key"
        if Utility.check_empty_string(self.failure_response):
            self.failure_response = "I have failed to process your request."
        try:
            self.num_results = int(self.num_results)
        except ValueError:
            self.num_results = 1


@auditlogger.log
@push_notification.apply
class WebSearchAction(Auditlog):
    name = StringField(required=True)
    website = StringField(default=None)
    failure_response = StringField(default='I have failed to process your request.')
    topn = IntField(default=1)
    dispatch_response = BooleanField(default=True)
    set_slot = StringField()
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    meta = {"indexes": [{"fields": ["bot", ("bot", "name", "status")]}]}

    def validate(self, clean=True):
        if clean:
            self.clean()
        if Utility.check_empty_string(self.name):
            raise ValidationError("Action name cannot be empty")
        if self.topn < 1:
            raise ValidationError("topn must be greater than or equal to 1!")

    def clean(self):
        self.name = self.name.strip().lower()
        if Utility.check_empty_string(self.failure_response):
            self.failure_response = 'I have failed to process your request.'


@auditlogger.log
@push_notification.apply
class JiraAction(Auditlog):
    name = StringField(required=True)
    url = StringField(required=True)
    user_name = StringField(required=True)
    api_token = EmbeddedDocumentField(CustomActionRequestParameters, required=True)
    project_key = StringField(required=True)
    issue_type = StringField(required=True)
    parent_key = StringField(default=None)
    summary = StringField(required=True)
    response = StringField(required=True)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    meta = {"indexes": [{"fields": ["bot", ("bot", "name", "status")]}]}

    def validate(self, clean=True):
        from kairon.shared.actions.utils import ActionUtility

        if clean:
            self.clean()
        try:
            param_type = self.api_token.parameter_type
            if param_type in {ActionParameterType.value, ActionParameterType.key_vault}:
                api_token = self.api_token.value
                if ActionParameterType.key_vault == param_type:
                    api_token = ActionUtility.get_secret_from_key_vault(
                        api_token, self.bot
                    )
                ActionUtility.get_jira_client(self.url, self.user_name, api_token)
                ActionUtility.validate_jira_action(
                    self.url,
                    self.user_name,
                    api_token,
                    self.project_key,
                    self.issue_type,
                    self.parent_key,
                )
        except Exception as e:
            raise ValidationError(e)

    def clean(self):
        self.name = self.name.strip().lower()
        if self.api_token:
            self.api_token.key = "api_token"


@auditlogger.log
@push_notification.apply
class ZendeskAction(Auditlog):
    name = StringField(required=True)
    subdomain = StringField(required=True)
    user_name = StringField(required=True)
    api_token = EmbeddedDocumentField(CustomActionRequestParameters, required=True)
    subject = StringField(required=True)
    response = StringField(required=True)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    meta = {"indexes": [{"fields": ["bot", ("bot", "name", "status")]}]}

    def validate(self, clean=True):
        from kairon.shared.actions.utils import ActionUtility

        if clean:
            self.clean()
        try:
            param_type = self.api_token.parameter_type
            if param_type in {ActionParameterType.value, ActionParameterType.key_vault}:
                api_token = self.api_token.value
                if ActionParameterType.key_vault == param_type:
                    api_token = ActionUtility.get_secret_from_key_vault(
                        api_token, self.bot
                    )
                ActionUtility.validate_zendesk_credentials(
                    self.subdomain, self.user_name, api_token
                )
        except Exception as e:
            raise ValidationError(e)

    def clean(self):
        self.name = self.name.strip().lower()
        if self.api_token:
            self.api_token.key = "api_token"


@auditlogger.log
@push_notification.apply
class PipedriveLeadsAction(Auditlog):
    name = StringField(required=True)
    domain = StringField(required=True)
    api_token = EmbeddedDocumentField(CustomActionRequestParameters, required=True)
    title = StringField(required=True)
    metadata = DictField(required=True)
    response = StringField(required=True)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    meta = {"indexes": [{"fields": ["bot", ("bot", "name", "status")]}]}

    def validate(self, clean=True):
        from kairon.shared.actions.utils import ActionUtility

        if clean:
            self.clean()
        try:
            param_type = self.api_token.parameter_type
            if param_type in {ActionParameterType.value, ActionParameterType.key_vault}:
                api_token = self.api_token.value
                if ActionParameterType.key_vault == param_type:
                    api_token = ActionUtility.get_secret_from_key_vault(
                        api_token, self.bot
                    )
                ActionUtility.validate_pipedrive_credentials(self.domain, api_token)
            if Utility.check_empty_string(self.metadata.get("name")):
                raise ValidationError("metadata: name is required")
        except Exception as e:
            raise ValidationError(e)

    def clean(self):
        self.name = self.name.strip().lower()
        if self.api_token:
            self.api_token.key = "api_token"


@auditlogger.log
@push_notification.apply
class HubspotFormsAction(Auditlog):
    name = StringField(required=True)
    portal_id = StringField(required=True)
    form_guid = StringField(required=True)
    fields = ListField(EmbeddedDocumentField(HttpActionRequestBody), required=True)
    response = StringField(required=True)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    meta = {"indexes": [{"fields": ["bot", ("bot", "name", "status")]}]}

    def validate(self, clean=True):
        if clean:
            self.clean()

    def clean(self):
        self.name = self.name.strip().lower()


class QuickReplies(EmbeddedDocument):
    text = StringField(required=True)
    payload = StringField(required=True)
    message = StringField()
    is_dynamic_msg = BooleanField(default=False)


class TwoStageFallbackTextualRecommendations(EmbeddedDocument):
    count = IntField(default=0)
    use_intent_ranking = BooleanField(default=False)


@auditlogger.log
@push_notification.apply
class KaironTwoStageFallbackAction(Auditlog):
    name = StringField(default=KAIRON_TWO_STAGE_FALLBACK)
    text_recommendations = EmbeddedDocumentField(
        TwoStageFallbackTextualRecommendations, default=None
    )
    trigger_rules = ListField(EmbeddedDocumentField(QuickReplies, default=None))
    bot = StringField(required=True)
    fallback_message = StringField(default=FALLBACK_MESSAGE)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    meta = {"indexes": [{"fields": ["bot", ("bot", "name", "status")]}]}

    def validate(self, clean=True):
        if clean:
            self.clean()

        if not self.text_recommendations and not self.trigger_rules:
            raise ValidationError(
                "One of text_recommendations or trigger_rules should be defined"
            )

    def clean(self):
        self.name = self.name.strip().lower()


class PromptHyperparameter(EmbeddedDocument):
    top_results = IntField(default=10)
    similarity_threshold = FloatField(default=0.70)

    def validate(self, clean=True):
        if not 0.3 <= self.similarity_threshold <= 1:
            raise ValidationError("similarity_threshold should be within 0.3 and 1")
        if self.top_results > 30:
            raise ValidationError("top_results should not be greater than 30")


class LlmPrompt(EmbeddedDocument):
    name = StringField(required=True)
    hyperparameters = EmbeddedDocumentField(PromptHyperparameter)
    data = StringField()
    instructions = StringField()
    type = StringField(
        required=True,
        choices=[
            LlmPromptType.user.value,
            LlmPromptType.system.value,
            LlmPromptType.query.value,
        ],
    )
    source = StringField(
        choices=[
            LlmPromptSource.static.value,
            LlmPromptSource.history.value,
            LlmPromptSource.bot_content.value,
            LlmPromptSource.action.value,
            LlmPromptSource.slot.value,
        ],
        default=LlmPromptSource.static.value,
    )
    is_enabled = BooleanField(default=True)

    def validate(self, clean=True):
        if (
            self.type == LlmPromptType.system.value
            and self.source != LlmPromptSource.static.value
        ):
            raise ValidationError("System prompt must have static source!")
        if self.hyperparameters:
            self.hyperparameters.validate()
        if self.source == LlmPromptSource.bot_content.value and Utility.check_empty_string(self.data):
            self.data = "default"


class UserQuestion(EmbeddedDocument):
    type = StringField(default=UserMessageType.from_user_message.value,
                       choices=[p_type.value for p_type in UserMessageType])
    value = StringField(default=None)


@auditlogger.log
@push_notification.apply
class PromptAction(Auditlog):
    name = StringField(required=True)
    num_bot_responses = IntField(default=5)
    failure_message = StringField(default=DEFAULT_NLU_FALLBACK_RESPONSE)
    user_question = EmbeddedDocumentField(UserQuestion, default=UserQuestion())
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    llm_type = StringField(default=DEFAULT_LLM, choices=Utility.get_llms())
    hyperparameters = DictField(default=Utility.get_default_llm_hyperparameters)
    llm_prompts = EmbeddedDocumentListField(LlmPrompt, required=True)
    instructions = ListField(StringField())
    set_slots = EmbeddedDocumentListField(SetSlotsFromResponse)
    dispatch_response = BooleanField(default=True)
    status = BooleanField(default=True)

    meta = {"indexes": [{"fields": ["bot", ("bot", "name", "status")]}]}

    def clean(self):
        for key, value in Utility.get_llm_hyperparameters(self.llm_type).items():
            if key not in self.hyperparameters:
                self.hyperparameters.update({key: value})

    def validate(self, clean=True):
        if clean:
            self.clean()
        if self.num_bot_responses > 5:
            raise ValidationError("num_bot_responses should not be greater than 5")
        if not self.llm_prompts:
            raise ValidationError("llm_prompts are required!")
        for prompts in self.llm_prompts:
            prompts.validate()
        dict_data = self.to_mongo().to_dict()
        Utility.validate_kairon_faq_llm_prompts(
            dict_data["llm_prompts"], ValidationError
        )
        Utility.validate_llm_hyperparameters(
            dict_data["hyperparameters"], self.llm_type, ValidationError
        )


@auditlogger.log
@push_notification.apply
class RazorpayAction(Auditlog):
    name = StringField(required=True)
    api_key = EmbeddedDocumentField(CustomActionRequestParameters, required=True)
    api_secret = EmbeddedDocumentField(CustomActionRequestParameters, required=True)
    amount = EmbeddedDocumentField(CustomActionRequestParameters, required=True)
    currency = EmbeddedDocumentField(CustomActionRequestParameters, required=True)
    username = EmbeddedDocumentField(CustomActionRequestParameters)
    email = EmbeddedDocumentField(CustomActionRequestParameters)
    contact = EmbeddedDocumentField(CustomActionRequestParameters)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    meta = {"indexes": [{"fields": ["bot", ("bot", "name", "status")]}]}

    def validate(self, clean=True):
        if clean:
            self.clean()

        if not (self.api_key and self.api_secret and self.amount and self.currency):
            raise ValidationError(
                "Fields api_key, api_secret, amount, currency are required!"
            )

    def clean(self):
        self.name = self.name.strip().lower()
        if self.api_key:
            self.api_key.key = "api_key"
        if self.api_secret:
            self.api_secret.key = "api_secret"
        if self.amount:
            self.amount.key = "amount"
        if self.currency:
            self.currency.key = "currency"
        if self.username:
            self.username.key = "username"
        if self.email:
            self.email.key = "email"
        if self.contact:
            self.contact.key = "contact"


from mongoengine import signals

signals.pre_save_post_validation.connect(
    HttpActionConfig.pre_save_post_validation, sender=HttpActionConfig
)


@auditlogger.log
@push_notification.apply
class LiveAgentActionConfig(Auditlog):
    name = StringField(default='live_agent_action')
    bot_response = StringField(default='Connecting to live agent')
    agent_connect_response = StringField(default='Connected to live agent')
    agent_disconnect_response = StringField(default='Disconnected from live agent')
    agent_not_available_response = StringField(default='No agents available')
    dispatch_bot_response = BooleanField(default=True)
    dispatch_agent_connect_response = BooleanField(default=True)
    dispatch_agent_disconnect_response = BooleanField(default=True)
    dispatch_agent_not_available_response = BooleanField(default=True)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    meta = {"indexes": [{"fields": ["bot", ("bot", "action_name", "status")]}]}

    def validate(self, clean=True):
        if clean:
            self.clean()

    def clean(self):
        self.name = self.name.strip().lower()
        if Utility.check_empty_string(self.name):
            raise ValidationError("Action name cannot be empty or blank spaces")
        if self.name.startswith("utter_"):
            raise ValidationError("Action name cannot start with utter_")


