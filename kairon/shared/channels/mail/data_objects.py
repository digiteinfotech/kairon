import time
from enum import Enum

from mongoengine import Document, StringField, ListField, FloatField, BooleanField, DictField
from kairon.exceptions import AppException
from kairon.shared.data.audit.data_objects import Auditlog
from kairon.shared.data.signals import auditlog, push_notification


class MailStatus(Enum):
    Processing = "processing"
    SUCCESS = "success"
    FAILED = "failed"

class MailResponseLog(Auditlog):
    """
    Mail response log
    """
    sender_id = StringField(required=True)
    subject = StringField(required=True)
    body = StringField(required=True)
    responses = ListField()
    slots = DictField()
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = FloatField(required=True)
    status = StringField(required=True, default=MailStatus.Processing.value)
