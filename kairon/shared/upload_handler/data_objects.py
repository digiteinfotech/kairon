from datetime import datetime

from mongoengine import StringField, DateTimeField, DynamicDocument, DictField, BooleanField

from kairon.shared.data.constant import EVENT_STATUS
from kairon.shared.data.signals import push_notification

@push_notification.apply
class UploadHandlerLogs(DynamicDocument):
    bot = StringField(required=True)
    user = StringField(required=True)
    file_name = StringField(default="")
    upload_type = StringField(default="")
    collection_name=StringField(default="")
    upload_errors = DictField(default={})
    exception = StringField(default="")
    is_uploaded = BooleanField(default=False)
    status = StringField(default=None)
    event_status = StringField(default=EVENT_STATUS.COMPLETED.value)
    start_timestamp = DateTimeField(default=datetime.utcnow)
    end_timestamp = DateTimeField(default=None)

    meta = {
        "indexes": [
            {
                "fields": ["bot", "event_status", "-start_timestamp"]
            }
        ]
    }