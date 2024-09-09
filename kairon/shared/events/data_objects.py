from mongoengine import StringField, DictField, DateTimeField, DynamicDocument, FloatField, DynamicField
from datetime import datetime

from kairon.shared.data.constant import TASK_TYPE


class ExecutorLogs(DynamicDocument):
    task_type = StringField(choices=[task_type.value for task_type in TASK_TYPE])
    event_class = StringField()
    data = DynamicField()
    status = StringField(required=True)
    exception = StringField()
    response = DictField()
    time_elapsed = FloatField()
    timestamp = DateTimeField(default=datetime.utcnow)

