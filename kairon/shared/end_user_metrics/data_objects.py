from mongoengine import StringField, DateTimeField, DynamicDocument
from datetime import datetime

from kairon.shared.end_user_metrics.constants import MetricTypes


class EndUserMetrics(DynamicDocument):
    log_type = StringField(required=True, choices=[l_type.value for l_type in MetricTypes])
    sender_id = StringField(required=True)
    bot = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
