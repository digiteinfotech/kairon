from datetime import datetime

from mongoengine import StringField, DateTimeField, ListField, EmbeddedDocumentField, EmbeddedDocument, \
    ValidationError, IntField, DynamicDocument, DynamicField, URLField, DictField

from kairon.shared.custom_widgets.constants import CustomWidgetParameterType
from kairon.shared.data.audit.data_objects import Auditlog
from kairon.shared.data.signals import push_notification, auditlogger


class CustomWidgetParameters(EmbeddedDocument):
    key = StringField(required=True)
    value = StringField(default="")
    parameter_type = StringField(default=CustomWidgetParameterType.value.value,
                                 choices=[p_type.value for p_type in CustomWidgetParameterType])

    def validate(self, clean=True):
        from kairon import Utility

        if clean:
            self.clean()

        if Utility.check_empty_string(self.key):
            raise ValidationError("key in parameters cannot be empty!")
        if self.parameter_type == CustomWidgetParameterType.key_vault.value and Utility.check_empty_string(self.value):
            raise ValidationError("Provide key from key vault as value!")


@auditlogger.log
@push_notification.apply
class CustomWidgets(Auditlog):
    name = StringField(required=True)
    http_url = URLField(required=True)
    request_method = StringField(default="GET", choices=["GET", "POST"])
    request_parameters = ListField(EmbeddedDocumentField(CustomWidgetParameters))
    dynamic_parameters = StringField(default=None)
    headers = ListField(EmbeddedDocumentField(CustomWidgetParameters))
    timeout = IntField(default=5)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)

    meta = {"indexes": [{"fields": ["bot"]}]}

    def validate(self, clean=True):
        if clean:
            self.clean()

        for params in self.request_parameters or []:
            params.validate()

        for params in self.headers or []:
            params.validate()


@auditlogger.log
@push_notification.apply
class CustomWidgetsRequestLog(DynamicDocument):
    name = StringField()
    request_method = StringField()
    http_url = StringField()
    headers = DynamicField()
    request_parameters = DynamicField()
    response = DynamicField()
    exception = StringField()
    requested_by = StringField(required=True)
    bot = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)

    meta = {"indexes": [{"fields": ["bot", ("bot", "-timestamp")]}]}

@auditlogger.log
@push_notification.apply
class CustomWidgetsGlobalConfig(Auditlog):
    global_config = ListField(DictField())
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)

    meta = {
        'indexes': [
            {'fields': ['bot'], 'unique': True}
        ]
    }

