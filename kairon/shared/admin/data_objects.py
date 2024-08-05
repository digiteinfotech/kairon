from datetime import datetime
from mongoengine import (
    StringField,
    DateTimeField, ValidationError, ListField
)
from kairon.shared.data.audit.data_objects import Auditlog
from kairon.shared.data.signals import push_notification, auditlogger
from kairon.shared.utils import Utility
from mongoengine import signals


@auditlogger.log
@push_notification.apply
class BotSecrets(Auditlog):
    secret_type = StringField(required=True)
    value = StringField(required=True)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)

    meta = {"indexes": [{"fields": ["bot", ("bot", "secret_type")]}]}

    @classmethod
    def pre_save_post_validation(cls, sender, document, **kwargs):
        if not Utility.check_empty_string(document.value):
            document.value = Utility.encrypt_message(document.value)


signals.pre_save_post_validation.connect(BotSecrets.pre_save_post_validation, sender=BotSecrets)


@auditlogger.log
@push_notification.apply
class LLMSecret(Auditlog):
    llm_type = StringField(required=True)
    api_key = StringField(required=True)
    models = ListField(StringField(), required=True)
    api_base_url = StringField()
    api_version = StringField()
    project = StringField()
    location = StringField()
    token = StringField()
    bot = StringField()
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)

    meta = {
        "indexes": [
            {"fields": ["llm_type"]}
        ]
    }

    def validate(self, clean=True):
        if clean:
            self.clean()

        required_fields = ['llm_type', 'api_key', 'models', 'user']
        for field in required_fields:
            if not getattr(self, field):
                raise ValidationError(f"{field} is required.")

        if not isinstance(self.models, list) or not all(isinstance(model, str) for model in self.models):
            raise ValidationError("Models should be a list of strings.")

        if not self.user or Utility.check_empty_string(self.user):
            raise ValidationError("User cannot be empty")

    def clean(self):
        self.llm_type = self.llm_type.strip().lower() if self.llm_type else None
        self.api_key = self.api_key.strip() if self.api_key else None
        self.models = [model.strip() for model in self.models] if self.models else []
        self.api_base_url = self.api_base_url.strip() if self.api_base_url else None
        self.api_version = self.api_version.strip() if self.api_version else None
        self.project = self.project.strip() if self.project else None
        self.location = self.location.strip() if self.location else None
        self.token = self.token.strip() if self.token else None


    @classmethod
    def pre_save_post_validation(cls, sender, document, **kwargs):
        if not Utility.check_empty_string(document.api_key):
            document.api_key = Utility.encrypt_message(document.api_key)
        if not Utility.check_empty_string(document.token):
            document.token = Utility.encrypt_message(document.token)


signals.pre_save_post_validation.connect(LLMSecret.pre_save_post_validation, sender=LLMSecret)