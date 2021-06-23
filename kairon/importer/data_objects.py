from datetime import datetime

from mongoengine import Document, StringField, ListField, BooleanField, DateTimeField, IntField, EmbeddedDocument, \
    EmbeddedDocumentField


class TrainingComponentLog(EmbeddedDocument):
    count = IntField(default=0)
    data = ListField(StringField(), default=[])


class DomainLog(EmbeddedDocument):
    intents_count = IntField(default=0)
    actions_count = IntField(default=0)
    slots_count = IntField(default=0)
    utterances_count = IntField(default=0)
    forms_count = IntField(default=0)
    entities_count = IntField(default=0)
    data = ListField(StringField(), default=[])


class ValidationLogs(Document):
    intents = EmbeddedDocumentField(TrainingComponentLog, default=TrainingComponentLog)
    utterances = EmbeddedDocumentField(TrainingComponentLog, default=TrainingComponentLog)
    stories = EmbeddedDocumentField(TrainingComponentLog, default=TrainingComponentLog)
    training_examples = EmbeddedDocumentField(TrainingComponentLog, default=TrainingComponentLog)
    domain = EmbeddedDocumentField(DomainLog, default=DomainLog)
    config = EmbeddedDocumentField(TrainingComponentLog, default=TrainingComponentLog)
    http_actions = EmbeddedDocumentField(TrainingComponentLog, default=TrainingComponentLog)
    exception = StringField(default="")
    is_data_uploaded = BooleanField(default=False)
    files_received = ListField(default=None)
    bot = StringField(required=True)
    user = StringField(required=True)
    start_timestamp = DateTimeField(default=datetime.utcnow())
    end_timestamp = DateTimeField(default=None)
    status = StringField(default=None)
    event_status = StringField(default="COMPLETED")
