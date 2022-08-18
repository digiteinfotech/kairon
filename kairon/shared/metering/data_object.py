from datetime import datetime

from mongoengine import DynamicDocument, StringField, DateField, DynamicField, LongField

from kairon.shared.metering.constants import MetricType


class Metering(DynamicDocument):
    bot = StringField(required=True)
    account = LongField(required=True)
    date = DateField(default=datetime.utcnow().date)
    metric_type = StringField(required=True, choices=[m_type.value for m_type in MetricType])
    data = DynamicField()
