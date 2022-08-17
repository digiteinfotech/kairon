from mongoengine import Document, StringField, DateTimeField, DictField, queryset_manager
from datetime import datetime

from kairon.shared.data.signals import auditlog


class AuditLogData(Document):
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    action = StringField(required=True)
    action_on = StringField(required=True)
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
        auditlog.send(self.__class__, document=self, created=kwargs.get("created"), action="save", event_url=event_url)
        return obj

    def delete(self, signal_kwargs=None, event_url=None, **write_concern):
        super().delete(signal_kwargs, **write_concern)
        auditlog.send(self.__class__, document=self, action="delete",
                      event_url=event_url)

    def update(self, event_url=None, **kwargs):
        obj = super().update(**kwargs)
        auditlog.send(self.__class__, document=self, action="update", event_url=event_url)
        return obj
