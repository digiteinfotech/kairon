from mongoengine import StringField, DateTimeField, DictField, BooleanField

from kairon.shared.data.base_data import Auditlog
from kairon.shared.data.signals import push_notification, auditlogger


@auditlogger.log
@push_notification.apply
class ModelTestingLogs(Auditlog):
    reference_id = StringField(default=None)
    data = DictField(default=None)
    type = StringField(required=True, choices=['nlu', 'stories', 'common'])
    exception = StringField(default=None)
    bot = StringField(required=True)
    user = StringField(required=True)
    start_timestamp = DateTimeField(default=None)
    end_timestamp = DateTimeField(default=None)
    status = StringField(default=None)
    event_status = StringField(default=None)
    is_augmented = BooleanField(default=False)
