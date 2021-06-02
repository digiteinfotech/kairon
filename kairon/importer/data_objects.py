from datetime import datetime

from mongoengine import Document, StringField, ListField, BooleanField, DateTimeField


class ValidationLogs(Document):
    intents = ListField(StringField(), default=[])
    utterances = ListField(StringField(), default=[])
    stories = ListField(StringField(), default=[])
    training_examples = ListField(StringField(), default=[])
    domain = ListField(StringField(), default=[])
    config = ListField(StringField(), default=[])
    http_actions = ListField(StringField(), default=[])
    exception = StringField(default=None)
    is_data_uploaded = BooleanField(default=False)
    files_received = ListField(default=None)
    bot = StringField(required=True)
    user = StringField(required=True)
    start_timestamp = DateTimeField(default=datetime.utcnow())
    end_timestamp = DateTimeField(default=None)
    status = StringField(default=None)
    event_status = StringField(default="COMPLETED")
