from datetime import datetime

from mongoengine import StringField, BooleanField, DateTimeField, DynamicDocument, DictField
from kairon.shared.data.signals import push_notification


@push_notification.apply
class ContentValidationLogs(DynamicDocument):
    event_id = StringField(required=True, unique=True)
    validation_errors = DictField(default={})
    exception = StringField(default="")
    is_data_uploaded = BooleanField(default=False)
    file_received = StringField(default="")
    bot = StringField(required=True)
    user = StringField(required=True)
    table = StringField(default="")
    start_timestamp = DateTimeField(default=datetime.utcnow)
    end_timestamp = DateTimeField(default=None)
    status = StringField(default=None)
    event_status = StringField(default="COMPLETED")

    meta = {"indexes": [{"fields": ["bot", "event_id", ("bot", "event_status", "-start_timestamp")]}]}
