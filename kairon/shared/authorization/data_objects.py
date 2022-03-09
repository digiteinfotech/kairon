from mongoengine import (
    Document,
    StringField,
    DateTimeField,
    ListField
)
from mongoengine.errors import ValidationError
from kairon.shared.data.constant import INTEGRATION_STATUS, ACCESS_ROLES
from kairon.shared.utils import Utility


class Integration(Document):
    name = StringField(required=True)
    bot = StringField(required=True)
    user = StringField(required=True)
    iat = DateTimeField(required=True)
    expiry = DateTimeField(default=None)
    role = StringField(required=True, choices=[role_type.value for role_type in ACCESS_ROLES])
    access_list = ListField(StringField(), default=None)
    status = StringField(required=True, choices=[i_status.value for i_status in INTEGRATION_STATUS])

    def clean(self):
        if Utility.check_empty_string(self.name):
            raise ValidationError('name is required to add integration')
        self.name = self.name.strip().lower()

    def validate(self, clean=True):
        if clean:
            self.clean()
