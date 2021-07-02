from datetime import datetime

from mongoengine import (
    Document,
    StringField,
    DateTimeField,
    BooleanField,
    LongField,
    SequenceField,
    DictField, ListField
)
from mongoengine.errors import ValidationError
from validators import email, ValidationFailure

from kairon.utils import Utility


class User(Document):
    email = StringField(required=True)
    first_name = StringField(required=True)
    last_name = StringField(required=True)
    password = StringField(required=True)
    role = StringField(required=True, default="trainer")
    is_integration_user = BooleanField(default=False)
    account = LongField(required=True)
    bot = ListField(StringField(), required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)
    last_password_reset_requested = DateTimeField()

    def validate(self, clean=True):
        if (
                Utility.check_empty_string(self.email)
                or Utility.check_empty_string(self.first_name)
                or Utility.check_empty_string(self.last_name)
                or Utility.check_empty_string(self.password)
        ):
            raise ValidationError(
                "Email, FirstName, LastName and password cannot be empty or blank space"
            )
        elif isinstance(email(self.email), ValidationFailure):
            raise ValidationError("Please enter valid email address")


class Bot(Document):
    name = StringField(required=True)
    account = LongField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    def validate(self, clean=True):
        if Utility.check_empty_string(self.name):
            raise ValidationError("Bot Name cannot be empty or blank spaces")


class Account(Document):
    id = SequenceField(required=True, primary_key=True)
    name = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)
    license = DictField()

    def validate(self, clean=True):
        if Utility.check_empty_string(self.name):
            raise ValidationError("Account Name cannot be empty or blank spaces")


class UserEmailConfirmation(Document):
    email = StringField(required=True, primary_key=True)
    timestamp = DateTimeField(default=datetime.utcnow)

    def validate(self, clean=True):
        if Utility.check_empty_string(self.email):
            raise ValidationError("Email cannot be empty or blank spaces")
        elif isinstance(email(self.email), ValidationFailure):
            raise ValidationError("Invalid email address")


class Integrations(Document):
    name = StringField(required=True)
    bot = StringField(required=True)
    user = StringField(required=True)
    issued_at = DateTimeField(required=True)
    status = StringField(required=True, choices=["active", "inactive", "deleted"])
