
from mongoengine import DynamicDocument, StringField, DynamicField, LongField, DateTimeField
from kairon.shared.clock import utc_now
from kairon.shared.metering.constants import MetricType


class Metering(DynamicDocument):
    bot = StringField()
    account = LongField()
    metric_type = StringField(required=True, choices=[m_type.value for m_type in MetricType])
    data = DynamicField()
    timestamp = DateTimeField(default=utc_now)

    meta = {"indexes": [
        {"fields": ["account", ("metric_type", "timestamp"), ("account", "bot", "metric_type", "timestamp")]}]}
