from datetime import datetime

from mongoengine import (
    Document,
    signals,
    StringField,
    BooleanField,
    ListField, DateTimeField, DictField
)

from kairon.idp.constants import IDPConfigType
from kairon.shared.data.signals import auditlogger
from kairon.shared.utils import Utility


@auditlogger.log
class IdpConfig(Document):
    user = StringField(required=True)
    account = ListField(required=True)
    organization = StringField(required=True)
    status = BooleanField(default=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    config_type = StringField()
    config_sub_type = StringField(choices=[config_type.value for config_type in IDPConfigType])
    realm_name = StringField()
    idp_client_id = StringField()
    idp_client_secret = StringField()
    idp_admin_client_secret = StringField()
    config = DictField()

    @classmethod
    def pre_save_post_validation(cls, sender, document, **kwargs):
        config = document.config
        for conf in document.config:
            if conf in ("client_id", "client_secret"):
                document.config[conf] = Utility.encrypt_message(document.config[conf])
        document.config = config


signals.pre_save_post_validation.connect(IdpConfig.pre_save_post_validation, sender=IdpConfig)
