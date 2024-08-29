from datetime import datetime

from mongoengine import (
    Document,
    StringField,
    DateTimeField,
    BooleanField,
    LongField,
    SequenceField,
    DictField,
    FloatField,
    EmbeddedDocumentField,
    EmbeddedDocument,
    ListField,
    DynamicField,
)
from mongoengine.errors import ValidationError
from validators import email, ValidationError as ValidationFailure

from kairon.shared.constants import UserActivityType
from kairon.shared.data.audit.data_objects import Auditlog
from kairon.shared.data.signals import push_notification, auditlogger
from kairon.shared.data.constant import ACCESS_ROLES, ACTIVITY_STATUS
from kairon.shared.utils import Utility


@auditlogger.log
class BotAccess(Auditlog):
    accessor_email = StringField(required=True)
    role = StringField(required=True, choices=[role.value for role in ACCESS_ROLES])
    bot = StringField(required=True)
    bot_account = LongField(required=True)
    user = StringField(required=True)
    accept_timestamp = DateTimeField()
    timestamp = DateTimeField(default=datetime.utcnow)
    status = StringField(
        required=True, choices=[status.value for status in ACTIVITY_STATUS]
    )

    meta = {"indexes": [{"fields": ["bot", ("bot", "accessor_email", "status")]}]}


@auditlogger.log
class User(Auditlog):
    email = StringField(required=True)
    first_name = StringField(required=True)
    last_name = StringField(required=True)
    password = StringField(required=True)
    account = LongField(required=True)
    user = StringField(required=True)
    is_onboarded = BooleanField(default=False)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)
    meta = {"indexes": [{"fields": ["$email", "$first_name", "$last_name"]}]}

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


class BotMetaData(EmbeddedDocument):
    source_language = StringField(default=None)
    language = StringField(default="en")
    source_bot_id = StringField(default=None)
    from_template = DynamicField(default=None)


@auditlogger.log
@push_notification.apply
class Bot(Auditlog):
    name = StringField(required=True)
    account = LongField(required=True)
    user = StringField(required=True)
    metadata = EmbeddedDocumentField(BotMetaData, default=BotMetaData())
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    def validate(self, clean=True):
        if Utility.check_empty_string(self.name):
            raise ValidationError("Bot Name cannot be empty or blank spaces")


@auditlogger.log
class Account(Auditlog):
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


class Feedback(Document):
    rating = FloatField(required=True)
    scale = FloatField(default=5.0)
    feedback = StringField(default=None)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)

    meta = {"indexes": [{"fields": ["user", ("user", "-timestamp")]}]}


@auditlogger.log
class UiConfig(Auditlog):
    config = DictField(default={})
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)

    meta = {"indexes": [{"fields": ["user"]}]}


class MailTemplates(EmbeddedDocument):
    verification = StringField()
    verification_confirmation = StringField()
    password_reset = StringField()
    password_reset_confirmation = StringField()
    add_member_invitation = StringField()
    add_member_confirmation = StringField()
    password_generated = StringField()
    conversation = StringField()
    custom_text_mail = StringField()
    bot_msg_conversation = StringField()
    user_msg_conversation = StringField()
    update_role = StringField()
    untrusted_login = StringField()
    add_trusted_device = StringField()
    button_template = StringField()
    leave_bot_owner_notification = StringField()


class SystemProperties(Document):
    mail_templates = EmbeddedDocumentField(MailTemplates)


class UserActivityLog(Document):
    type = StringField(
        required=True, choices=[a_type.value for a_type in UserActivityType]
    )
    user = StringField()
    timestamp = DateTimeField(default=datetime.utcnow)
    account = LongField(required=True)
    bot = StringField()
    message = ListField(StringField(), default=None)
    data = DynamicField()

    meta = {"indexes": [{"fields": ["bot", ("user", "type", "timestamp")]}]}


@auditlogger.log
class TrustedDevice(Auditlog):
    fingerprint = StringField(required=True)
    user = StringField(required=True)
    is_confirmed = BooleanField(default=False)
    geo_location = DictField()
    timestamp = DateTimeField(default=datetime.utcnow)
    confirmation_timestamp = DateTimeField(default=None)
    status = BooleanField(default=True)

    meta = {"indexes": [{"fields": ["user", ("user", "status", "is_confirmed")]}]}


@auditlogger.log
class Organization(Auditlog):
    name = StringField(required=True)
    user = StringField(required=True)
    account = ListField(required=True)
    tags = ListField()
    timestamp = DateTimeField(default=datetime.utcnow)
    create_user = BooleanField(default=True)
    only_sso_login = BooleanField(default=False)

    meta = {"indexes": [{"fields": ["account", "name"]}]}
