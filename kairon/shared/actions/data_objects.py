from mongoengine import (
    EmbeddedDocument,
    EmbeddedDocumentField,
    StringField,
    DateTimeField,
    BooleanField,
    IntField,
    ListField, DictField, DynamicField, DynamicDocument
)
from mongoengine.errors import ValidationError
from datetime import datetime

from validators import ValidationFailure, url

from kairon.shared.actions.models import ActionType, ActionParameterType, HttpRequestContentType, \
    EvaluationType
from kairon.shared.constants import SLOT_SET_TYPE
from kairon.shared.data.base_data import Auditlog
from kairon.shared.data.constant import KAIRON_TWO_STAGE_FALLBACK, FALLBACK_MESSAGE
from kairon.shared.data.signals import push_notification, auditlogger
from kairon.shared.utils import Utility
from validators import email


class HttpActionRequestBody(EmbeddedDocument):
    key = StringField(required=True)
    value = StringField(default="")
    parameter_type = StringField(default=ActionParameterType.value,
                                 choices=[p_type.value for p_type in ActionParameterType])
    encrypt = BooleanField(default=False)

    meta = {'allow_inheritance': True}

    def clean(self):
        from .utils import ActionUtility

        if self.parameter_type == ActionParameterType.slot.value and not ActionUtility.is_empty(self.value):
            self.value = self.value.lower()

        if self.parameter_type == ActionParameterType.key_vault.value:
            self.encrypt = True

    def validate(self, clean=True):
        from .utils import ActionUtility

        if clean:
            self.clean()

        if ActionUtility.is_empty(self.key):
            raise ValidationError("key in http action parameters cannot be empty")
        if self.parameter_type == ActionParameterType.slot.value and ActionUtility.is_empty(self.value):
            raise ValidationError("Provide name of the slot as value")
        if self.parameter_type == ActionParameterType.key_vault.value and ActionUtility.is_empty(self.value):
            raise ValidationError("Provide key from key vault as value")

    def __eq__(self, other):
        return isinstance(other, self.__class__) and self.key == other.key and self.parameter_type == other.parameter_type and self.value == other.value


class SetSlotsFromResponse(EmbeddedDocument):
    name = StringField(required=True)
    value = StringField(required=True)
    evaluation_type = StringField(default=EvaluationType.expression.value,
                                  choices=[p_type.value for p_type in EvaluationType])


class HttpActionResponse(EmbeddedDocument):
    value = StringField(default=None)
    dispatch = BooleanField(default=True)
    evaluation_type = StringField(default=EvaluationType.expression.value,
                                  choices=[p_type.value for p_type in EvaluationType])

    def validate(self, clean=True):
        from .utils import ActionUtility

        if self.dispatch and ActionUtility.is_empty(self.value):
            raise ValidationError("response is required for dispatch")


@auditlogger.log
@push_notification.apply
class HttpActionConfig(Auditlog):
    action_name = StringField(required=True)
    http_url = StringField(required=True)
    request_method = StringField(required=True)
    content_type = StringField(default=HttpRequestContentType.json.value,
                               choices=[c_type.value for c_type in HttpRequestContentType])
    params_list = ListField(EmbeddedDocumentField(HttpActionRequestBody), required=False)
    headers = ListField(EmbeddedDocumentField(HttpActionRequestBody), required=False)
    response = EmbeddedDocumentField(HttpActionResponse, default=HttpActionResponse())
    set_slots = ListField(EmbeddedDocumentField(SetSlotsFromResponse))
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

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
        if isinstance(url(self.http_url), ValidationFailure):
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
            if param.encrypt is True and param.parameter_type == ActionParameterType.value.value:
                if not ActionUtility.is_empty(param.value):
                    param.value = Utility.encrypt_message(param.value)

        for param in document.params_list:
            if param.encrypt is True and param.parameter_type == ActionParameterType.value.value:
                if not ActionUtility.is_empty(param.value):
                    param.value = Utility.encrypt_message(param.value)


class ActionServerLogs(DynamicDocument):
    type = StringField()
    intent = StringField()
    action = StringField()
    sender = StringField()
    headers = DictField()
    url = StringField()
    request_method = StringField()
    request_params = DictField()
    api_response = StringField()
    bot_response = StringField()
    exception = StringField()
    messages = DynamicField()
    bot = StringField()
    timestamp = DateTimeField(default=datetime.utcnow)
    status = StringField(default="SUCCESS")


@auditlogger.log
@push_notification.apply
class Actions(Auditlog):
    name = StringField(required=True)
    type = StringField(choices=[type.value for type in ActionType], default=None)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    def clean(self):
        self.name = self.name.strip().lower()

    def validate(self, clean=True):
        if clean:
            self.clean()

        from .utils import ActionUtility

        if ActionUtility.is_empty(self.name):
            raise ValidationError("Action name cannot be empty or blank spaces")

        if self.name.startswith('utter_'):
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
        return isinstance(other, self.__class__) and self.name == other.name and self.type == other.type and self.value == other.value


@auditlogger.log
@push_notification.apply
class SlotSetAction(Auditlog):
    name = StringField(required=True)
    set_slots = ListField(EmbeddedDocumentField(SetSlots), required=True)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    def validate(self, clean=True):
        if clean:
            self.clean()

    def clean(self):
        self.name = self.name.strip().lower()
        for slot_to_set in self.set_slots:
            slot_to_set.validate()


@auditlogger.log
@push_notification.apply
class FormValidationAction(Auditlog):
    name = StringField(required=True)
    slot = StringField(required=True)
    validation_semantic = DictField(default={})
    valid_response = StringField(default=None)
    invalid_response = StringField(default=None)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    def clean(self):
        self.name = self.name.strip().lower()
        self.slot = self.slot.strip().lower()

    def validate(self, clean=True):
        if clean:
            self.clean()


class CustomActionRequestParameters(HttpActionRequestBody):
    value = StringField(required=True)
    parameter_type = StringField(default=ActionParameterType.value,
                                 choices=[ActionParameterType.value, ActionParameterType.slot,
                                          ActionParameterType.key_vault, ActionParameterType.sender_id])


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
    tls = BooleanField(default=False)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

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

    def clean(self):
        self.action_name = self.action_name.strip().lower()
        if self.smtp_userid:
            self.smtp_userid.key = "smtp_userid"
        if self.smtp_password:
            self.smtp_password.key = "smtp_password"


@auditlogger.log
@push_notification.apply
class GoogleSearchAction(Auditlog):
    name = StringField(required=True)
    api_key = EmbeddedDocumentField(CustomActionRequestParameters, required=True)
    search_engine_id = StringField(required=True)
    failure_response = StringField(default='I have failed to process your request.')
    num_results = IntField(default=1)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    def validate(self, clean=True):
        if clean:
            self.clean()

    def clean(self):
        self.name = self.name.strip().lower()
        self.api_key.key = "api_key"
        if Utility.check_empty_string(self.failure_response):
            self.failure_response = 'I have failed to process your request.'
        try:
            self.num_results = int(self.num_results)
        except ValueError:
            self.num_results = 1


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

    def validate(self, clean=True):
        from kairon.shared.actions.utils import ActionUtility

        if clean:
            self.clean()
        try:
            param_type = self.api_token.parameter_type
            if param_type in {ActionParameterType.value, ActionParameterType.key_vault}:
                api_token = self.api_token.value
                if ActionParameterType.key_vault == param_type:
                    api_token = ActionUtility.get_secret_from_key_vault(api_token, self.bot)
                ActionUtility.get_jira_client(self.url, self.user_name, api_token)
                ActionUtility.validate_jira_action(self.url, self.user_name, api_token, self.project_key, self.issue_type, self.parent_key)
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

    def validate(self, clean=True):
        from kairon.shared.actions.utils import ActionUtility

        if clean:
            self.clean()
        try:
            param_type = self.api_token.parameter_type
            if param_type in {ActionParameterType.value, ActionParameterType.key_vault}:
                api_token = self.api_token.value
                if ActionParameterType.key_vault == param_type:
                    api_token = ActionUtility.get_secret_from_key_vault(api_token, self.bot)
                ActionUtility.validate_zendesk_credentials(self.subdomain, self.user_name, api_token)
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

    def validate(self, clean=True):
        from kairon.shared.actions.utils import ActionUtility

        if clean:
            self.clean()
        try:
            param_type = self.api_token.parameter_type
            if param_type in {ActionParameterType.value, ActionParameterType.key_vault}:
                api_token = self.api_token.value
                if ActionParameterType.key_vault == param_type:
                    api_token = ActionUtility.get_secret_from_key_vault(api_token, self.bot)
                ActionUtility.validate_pipedrive_credentials(self.domain, api_token)
            if Utility.check_empty_string(self.metadata.get('name')):
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
    text_recommendations = EmbeddedDocumentField(TwoStageFallbackTextualRecommendations, default=None)
    trigger_rules = ListField(EmbeddedDocumentField(QuickReplies, default=None))
    bot = StringField(required=True)
    fallback_message = StringField(default=FALLBACK_MESSAGE)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    def validate(self, clean=True):
        if clean:
            self.clean()

        if not self.text_recommendations and not self.trigger_rules:
            raise ValidationError("One of text_recommendations or trigger_rules should be defined")

    def clean(self):
        self.name = self.name.strip().lower()


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

    def validate(self, clean=True):
        if clean:
            self.clean()

        if not (self.api_key and self.api_secret and self.amount and self.currency):
            raise ValidationError("Fields api_key, api_secret, amount, currency are required!")

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
signals.pre_save_post_validation.connect(HttpActionConfig.pre_save_post_validation, sender=HttpActionConfig)
