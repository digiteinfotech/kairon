from datetime import datetime

from mongoengine import StringField, ListField, BooleanField, DateTimeField, IntField, EmbeddedDocument, \
    EmbeddedDocumentField, DynamicField, DynamicDocument

from kairon.shared.data.constant import EVENT_STATUS
from kairon.shared.data.signals import push_notification


class TrainingComponentLog(EmbeddedDocument):
    count = IntField(default=0)
    data = ListField(DynamicField(), default=[])


class DomainLog(EmbeddedDocument):
    intents_count = IntField(default=0)
    actions_count = IntField(default=0)
    slots_count = IntField(default=0)
    utterances_count = IntField(default=0)
    forms_count = IntField(default=0)
    entities_count = IntField(default=0)
    data = ListField(StringField(), default=[])


@push_notification.apply
class ValidationLogs(DynamicDocument):
    intents = EmbeddedDocumentField(TrainingComponentLog, default=TrainingComponentLog)
    utterances = EmbeddedDocumentField(TrainingComponentLog, default=TrainingComponentLog)
    stories = EmbeddedDocumentField(TrainingComponentLog, default=TrainingComponentLog)
    training_examples = EmbeddedDocumentField(TrainingComponentLog, default=TrainingComponentLog)
    domain = EmbeddedDocumentField(DomainLog, default=DomainLog)
    config = EmbeddedDocumentField(TrainingComponentLog, default=TrainingComponentLog)
    rules = EmbeddedDocumentField(TrainingComponentLog, default=TrainingComponentLog)
    actions = ListField()
    multiflow_stories = EmbeddedDocumentField(TrainingComponentLog, default=TrainingComponentLog)
    bot_content = EmbeddedDocumentField(TrainingComponentLog, default=TrainingComponentLog)
    user_actions = EmbeddedDocumentField(TrainingComponentLog, default=TrainingComponentLog)
    exception = StringField(default="")
    is_data_uploaded = BooleanField(default=False)
    files_received = ListField(default=None)
    bot = StringField(required=True)
    user = StringField(required=True)
    start_timestamp = DateTimeField(default=datetime.utcnow)
    end_timestamp = DateTimeField(default=None)
    status = StringField(default=None)
    event_status = StringField(default=EVENT_STATUS.COMPLETED.value)

    meta = {"indexes": [{"fields": ["bot", ("bot", "event_status", "-start_timestamp")]}]}
