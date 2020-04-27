from mongoengine import (
    Document,
    StringField,
    DateTimeField,
    BooleanField,
    LongField,
    SequenceField,
)
from mongoengine.errors import ValidationError
from datetime import datetime
from bot_trainer.utils import Utility
from validators import email, ValidationFailure


class User(Document):
    email = StringField(required=True)
    first_name = StringField(required=True)
    last_name = StringField(required=True)
    password = StringField(required=True)
    role = StringField(required=True, default="trainer")
    is_integration_user = BooleanField(default=False)
    account = LongField(required=True)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

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
            raise ValidationError("Bot Name cannot be empty or blank space")


class Account(Document):
    id = SequenceField(required=True, primary_key=True)
    name = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    def validate(self, clean=True):
        if Utility.check_empty_string(self.name):
            raise ValidationError("Account Name cannot be empty or blank space")
