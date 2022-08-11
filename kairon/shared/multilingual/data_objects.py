from mongoengine import Document, StringField, BooleanField, DateTimeField, IntField
from kairon.shared.data.signals import push_notification
from datetime import datetime


@push_notification.apply
class BotReplicationLogs(Document):
    bot = StringField(required=True)
    user = StringField(required=True)
    source_bot_name = StringField(default=None)
    destination_bot = StringField(default=None)
    s_lang = StringField(default=None)
    d_lang = StringField(default=None)
    copy_type = StringField(default="Translation")
    account = IntField(default=None)
    translate_responses = BooleanField(default=True)
    translate_actions = BooleanField(default=False)
    exception = StringField(default="")
    start_timestamp = DateTimeField(default=datetime.utcnow())
    end_timestamp = DateTimeField(default=None)
    status = StringField(default=None)
    event_status = StringField(default="COMPLETED")
