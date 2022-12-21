from datetime import datetime
from mongoengine import (
    StringField,
    DateTimeField, Document,
)
from kairon.shared.data.signals import push_notification
from kairon.shared.utils import Utility
from mongoengine import signals


@push_notification.apply
class BotSecrets(Document):
    secret_type = StringField(required=True)
    value = StringField(required=True)
    bot = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)

    @classmethod
    def pre_save_post_validation(cls, sender, document, **kwargs):
        if not Utility.check_empty_string(document.value):
            document.value = Utility.encrypt_message(document.value)


signals.pre_save_post_validation.connect(BotSecrets.pre_save_post_validation, sender=BotSecrets)
