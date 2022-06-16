from mongoengine import (
    Document,
    EmbeddedDocument,
    EmbeddedDocumentField,
    StringField,
    DateTimeField,
    BooleanField,
    IntField,
    ListField, DictField, DynamicField
)
from mongoengine.errors import ValidationError
from datetime import datetime

from validators import ValidationFailure, url

from kairon.shared.actions.models import ActionType, ActionParameterType
from kairon.shared.constants import SLOT_SET_TYPE
from kairon.shared.data.signals import push_notification
from kairon.shared.utils import Utility
from validators import email


class HttpActionRequestBody(EmbeddedDocument):
    key = StringField(required=True)
    value = StringField(default="")
    parameter_type = StringField(default=ActionParameterType.value,
                                 choices=[p_type.value for p_type in ActionParameterType])

    def clean(self):
        from .utils import ActionUtility

        if self.parameter_type == ActionParameterType.slot.value and not ActionUtility.is_empty(self.value):
            self.value = self.value.lower()

    def validate(self, clean=True):
        from .utils import ActionUtility

        if clean:
            self.clean()

        if ActionUtility.is_empty(self.key):
            raise ValidationError("key in http action parameters cannot be empty")
        if self.parameter_type == "slot" and ActionUtility.is_empty(self.value):
            raise ValidationError("Provide name of the slot as value")


@push_notification.apply
class HttpActionConfig(Document):
    action_name = StringField(required=True)
    response = StringField(required=True)
    http_url = StringField(required=True)
    request_method = StringField(required=True)
    params_list = ListField(EmbeddedDocumentField(HttpActionRequestBody), required=False)
    headers = ListField(EmbeddedDocumentField(HttpActionRequestBody), required=False)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    def validate(self, clean=True):
        if clean:
            self.clean()

        if self.action_name is None or not self.action_name.strip():
            raise ValidationError("Action name cannot be empty")
        if self.http_url is None or not self.http_url.strip():
            raise ValidationError("URL cannot be empty")
        if isinstance(url(self.http_url), ValidationFailure):
            raise ValidationError("URL is malformed")
        if self.request_method.upper() not in ("GET", "POST", "PUT", "DELETE"):
            raise ValidationError("Invalid HTTP method")

        for param in self.params_list:
            param.validate()

        for param in self.headers:
            param.validate()

    def clean(self):
        self.action_name = self.action_name.strip().lower()


class ActionServerLogs(Document):
    type = StringField()
    intent = StringField()
    action = StringField()
    sender = StringField()
    headers = DictField()
    url = StringField()
    request_params = DictField()
    api_response = StringField()
    bot_response = StringField()
    exception = StringField()
    messages = ListField(StringField())
    bot = StringField()
    timestamp = DateTimeField(default=datetime.utcnow)
    status = StringField(default="SUCCESS")


@push_notification.apply
class Actions(Document):
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


@push_notification.apply
class SlotSetAction(Document):
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


@push_notification.apply
class FormValidationAction(Document):
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


@push_notification.apply
class EmailActionConfig(Document):
    action_name = StringField(required=True)
    smtp_url = StringField(required=True)
    smtp_port = IntField(required=True)
    smtp_userid = StringField()
    smtp_password = StringField(required=True)
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
        if clean:
            self.clean()

        if self.action_name is None or not self.action_name.strip():
            raise ValidationError("Action name cannot be empty")
        if self.smtp_url is None or not self.smtp_url.strip():
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

    @classmethod
    def pre_save_post_validation(cls, sender, document, **kwargs):
        document.smtp_url = Utility.encrypt_message(document.smtp_url)
        document.smtp_password = Utility.encrypt_message(document.smtp_password)
        if not Utility.check_empty_string(document.smtp_userid):
            document.smtp_userid = Utility.encrypt_message(document.smtp_userid)
        document.from_email = Utility.encrypt_message(document.from_email)


@push_notification.apply
class GoogleSearchAction(Document):
    name = StringField(required=True)
    api_key = StringField(required=True)
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
        if Utility.check_empty_string(self.failure_response):
            self.failure_response = 'I have failed to process your request.'
        try:
            self.num_results = int(self.num_results)
        except ValueError:
            self.num_results = 1

    @classmethod
    def pre_save_post_validation(cls, sender, document, **kwargs):
        document.api_key = Utility.encrypt_message(document.api_key)


@push_notification.apply
class JiraAction(Document):
    name = StringField(required=True)
    url = StringField(required=True)
    user_name = StringField(required=True)
    api_token = StringField(required=True)
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
            ActionUtility.get_jira_client(self.url, self.user_name, self.api_token)
            ActionUtility.validate_jira_action(self.url, self.user_name, self.api_token, self.project_key, self.issue_type, self.parent_key)
        except Exception as e:
            raise ValidationError(e)

    def clean(self):
        self.name = self.name.strip().lower()

    @classmethod
    def pre_save_post_validation(cls, sender, document, **kwargs):
        document.user_name = Utility.encrypt_message(document.user_name)
        document.api_token = Utility.encrypt_message(document.api_token)


@push_notification.apply
class ZendeskAction(Document):
    name = StringField(required=True)
    subdomain = StringField(required=True)
    user_name = StringField(required=True)
    api_token = StringField(required=True)
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
            ActionUtility.validate_zendesk_credentials(self.subdomain, self.user_name, self.api_token)
        except Exception as e:
            raise ValidationError(e)

    def clean(self):
        self.name = self.name.strip().lower()

    @classmethod
    def pre_save_post_validation(cls, sender, document, **kwargs):
        document.user_name = Utility.encrypt_message(document.user_name)
        document.api_token = Utility.encrypt_message(document.api_token)


@push_notification.apply
class PipedriveLeadsAction(Document):
    name = StringField(required=True)
    domain = StringField(required=True)
    api_token = StringField(required=True)
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
            ActionUtility.validate_pipedrive_credentials(self.domain, self.api_token)
            if Utility.check_empty_string(self.metadata.get('name')):
                raise ValidationError("metadata: name is required")
        except Exception as e:
            raise ValidationError(e)

    def clean(self):
        self.name = self.name.strip().lower()

    @classmethod
    def pre_save_post_validation(cls, sender, document, **kwargs):
        document.api_token = Utility.encrypt_message(document.api_token)


@push_notification.apply
class HubspotFormsAction(Document):
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


from mongoengine import signals
signals.pre_save_post_validation.connect(GoogleSearchAction.pre_save_post_validation, sender=GoogleSearchAction)
signals.pre_save_post_validation.connect(EmailActionConfig.pre_save_post_validation, sender=EmailActionConfig)
signals.pre_save_post_validation.connect(JiraAction.pre_save_post_validation, sender=JiraAction)
signals.pre_save_post_validation.connect(ZendeskAction.pre_save_post_validation, sender=ZendeskAction)
signals.pre_save_post_validation.connect(PipedriveLeadsAction.pre_save_post_validation, sender=PipedriveLeadsAction)
