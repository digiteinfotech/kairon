from datetime import datetime
from mongoengine import (
    StringField,
    DateTimeField
)
from kairon.shared.data.audit.data_objects import Auditlog
from kairon.shared.data.signals import push_notification, auditlogger
from kairon.shared.utils import Utility
from mongoengine import signals


@auditlogger.log
@push_notification.apply
class BotSecrets(Auditlog):
    secret_type = StringField(required=True)
    value = StringField(required=True)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)

    meta = {"indexes": [{"fields": ["bot", ("bot", "secret_type")]}]}

    @classmethod
    def pre_save_post_validation(cls, sender, document, **kwargs):
        if not Utility.check_empty_string(document.value):
            document.value = Utility.encrypt_message(document.value)


signals.pre_save_post_validation.connect(BotSecrets.pre_save_post_validation, sender=BotSecrets)
