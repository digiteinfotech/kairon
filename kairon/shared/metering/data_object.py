from datetime import datetime

from mongoengine import DynamicDocument, StringField, DynamicField, LongField, DateTimeField
from kairon.shared.metering.constants import MetricType


class Metering(DynamicDocument):
    bot = StringField()
    account = LongField()
    metric_type = StringField(required=True, choices=[m_type.value for m_type in MetricType])
    data = DynamicField()
    timestamp = DateTimeField(default=datetime.utcnow)
