from mongoengine import (
    Document,
    EmbeddedDocument,
    EmbeddedDocumentField,
    StringField,
    DateTimeField,
    BooleanField,
    ListField, DictField,
)
from mongoengine.errors import ValidationError
from datetime import datetime

from validators import ValidationFailure, url


class HttpActionRequestBody(EmbeddedDocument):
    key = StringField(required=True)
    value = StringField(default="")
    parameter_type = StringField(default="value", choices=["value", "slot", "sender_id"])

    def validate(self, clean=True):
        from .utils import ActionUtility

        if ActionUtility.is_empty(self.key):
            raise ValidationError("key in http action parameters cannot be empty")
        if self.parameter_type == "slot" and ActionUtility.is_empty(self.value):
            raise ValidationError("Provide name of the slot as value")


class HttpActionConfig(Document):
    auth_token = StringField(default="")
    action_name = StringField(required=True)
    response = StringField(required=True)
    http_url = StringField(required=True)
    request_method = StringField(required=True)
    params_list = ListField(EmbeddedDocumentField(HttpActionRequestBody), required=False)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)
    is_integration = BooleanField(default=False)

    def validate(self, clean=True):
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


class HttpActionLog(Document):
    intent = StringField()
    action = StringField()
    sender = StringField()
    url = StringField()
    request_params = DictField()
    api_response = StringField()
    bot_response = StringField()
    exception = StringField()
    bot = StringField()
    timestamp = DateTimeField(default=datetime.utcnow)
    status = StringField(default="SUCCESS")
