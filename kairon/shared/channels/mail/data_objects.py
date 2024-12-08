import time
from enum import Enum

from mongoengine import Document, StringField, ListField, FloatField, DictField, IntField
from kairon.shared.data.audit.data_objects import Auditlog



class MailChannelStateData(Document):
    event_id = StringField()
    last_email_uid = IntField(default=0)
    bot = StringField(required=True)
    timestamp = FloatField(default=time.time())

    meta = {"indexes": ["bot"]}

    def save(self, *args, **kwargs):
        self.timestamp = time.time()
        super(MailChannelStateData, self).save(*args, **kwargs)

class MailStatus(Enum):
    Processing = "processing"
    SUCCESS = "success"
    FAILED = "failed"

class MailResponseLog(Auditlog):
    """
    Mail response log
    """
    sender_id = StringField(required=True)
    subject = StringField()
    body = StringField()
    responses = ListField()
    slots = DictField()
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = FloatField(required=True)
    status = StringField(required=True, default=MailStatus.Processing.value)

    meta = {"indexes": ["bot"]}

    def save(self, *args, **kwargs):
        self.timestamp = time.time()
        super(MailResponseLog, self).save(*args, **kwargs)
