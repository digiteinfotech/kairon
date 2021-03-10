import validators
ValidationFailure = validators.ValidationFailure
from mongoengine import (
    Document,
    EmbeddedDocument,
    EmbeddedDocumentField,
    StringField,
    DateTimeField,
    BooleanField,
    ListField,
)
from mongoengine.errors import ValidationError
from datetime import datetime



class HttpActionRequestBody(EmbeddedDocument):
    key = StringField(required=True)
    value = StringField(default="")
    parameter_type = StringField(default="value", choices=["value", "slot", "sender_id"])

    def validate(self, clean=True):
        from kairon.action_server.actions import ActionUtility

        if self.parameter_type == "value" and ActionUtility.is_empty(self.value):
            raise ValidationError("Either value for the key should be given or parameter_type should be set to slot or sender_id")


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

    def validate(self, clean=True):
        if self.action_name is None or not self.action_name.strip():
            raise ValidationError("Action name cannot be empty")
        if self.http_url is None or not self.http_url.strip():
            raise ValidationError("URL cannot be empty")
        if isinstance(validators.url(self.http_url), ValidationFailure):
            raise ValidationError("URL is malformed")
        if self.request_method.upper() not in ("GET", "POST", "PUT", "DELETE"):
            raise ValidationError("Invalid HTTP method")
