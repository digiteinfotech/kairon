from datetime import datetime

from mongoengine import Document, StringField, DateTimeField, DictField, ListField, EmbeddedDocument, \
    DynamicField, EmbeddedDocumentField

from kairon.shared.data.constant import AuditlogActions
from kairon.shared.data.signals import auditlog


class Attributes(EmbeddedDocument):
    key = StringField()
    value = DynamicField()


class AuditLogData(Document):
    attributes = ListField(EmbeddedDocumentField(Attributes, required=True))
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    action = StringField(required=True, choices=[action.value for action in AuditlogActions])
    entity = StringField(required=True)
    data = DictField()


class Auditlog(Document):
    meta = {'abstract': True}

    def save(
            self,
            force_insert=False,
            validate=True,
            clean=True,
            write_concern=None,
            cascade=None,
            cascade_kwargs=None,
            _refs=None,
            save_condition=None,
            event_url=None,
            signal_kwargs=None,
            **kwargs,
    ):
        doc_id = self.to_mongo(fields=[self._meta["id_field"]])
        created = "_id" not in doc_id or self._created or force_insert

        obj = super().save(
            force_insert=force_insert,
            validate=validate,
            clean=clean,
            write_concern=write_concern,
            cascade=cascade,
            cascade_kwargs=cascade_kwargs,
            _refs=_refs,
            save_condition=save_condition,
            signal_kwargs=signal_kwargs,
            **kwargs,
        )
        action = AuditlogActions.SAVE.value
        if not created:
            action = AuditlogActions.UPDATE.value

        auditlog.send(self.__class__, document=self, created=kwargs.get("created"), action=action,
                      event_url=event_url)
        return obj

    @classmethod
    def insert(cls, doc_or_docs):
        document_instances = cls.objects.insert(doc_or_docs, load_bulk=True)
        auditlog.send(cls, document=document_instances, action=AuditlogActions.BULK_INSERT.value)

    def delete(self, signal_kwargs=None, event_url=None, user=None, **write_concern):
        super().delete(signal_kwargs, **write_concern)
        auditlog.send(self.__class__, document=self, action=AuditlogActions.DELETE.value,
                      event_url=event_url, user=user)

    def update(self, event_url=None, **kwargs):
        obj = super().update(**kwargs)
        auditlog.send(self.__class__, document=self, action=AuditlogActions.UPDATE.value, event_url=event_url)
        return obj
