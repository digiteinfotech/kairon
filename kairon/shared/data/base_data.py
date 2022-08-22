from mongoengine import Document, StringField, DateTimeField, DictField, queryset_manager
from datetime import datetime

from kairon.shared.data.constant import AuditlogActions
from kairon.shared.data.signals import auditlog


class AuditLogData(Document):
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    action = StringField(required=True, choices=[action.value for action in AuditlogActions])
    entity = StringField(required=True)
    data = DictField()

    @queryset_manager
    def objects(cls, queryset):
        return queryset.order_by('-timestamp')


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

    def delete(self, signal_kwargs=None, event_url=None, **write_concern):
        super().delete(signal_kwargs, **write_concern)
        auditlog.send(self.__class__, document=self, action=AuditlogActions.DELETE.value,
                      event_url=event_url)

    def update(self, event_url=None, **kwargs):
        obj = super().update(**kwargs)
        auditlog.send(self.__class__, document=self, action=AuditlogActions.UPDATE.value, event_url=event_url)
        return obj
