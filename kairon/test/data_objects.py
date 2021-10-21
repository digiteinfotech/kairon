from datetime import datetime

from mongoengine import Document, StringField, BooleanField, DateTimeField, DictField


class ModelTestingLogs(Document):
    stories = DictField(default=None)
    nlu = DictField(default=None)
    exception = StringField(default=None)
    run_on_test_stories = BooleanField(default=False)
    bot = StringField(required=True)
    user = StringField(required=True)
    start_timestamp = DateTimeField(default=datetime.utcnow())
    end_timestamp = DateTimeField(default=None)
    status = StringField(default=None)
    event_status = StringField(default="Completed")
