from mongoengine import (
    Document,
    signals,
    StringField,
    BooleanField,
    LongField
)
from mongoengine.errors import ValidationError
from validators import url, ValidationFailure

from kairon.idp.constants import IDPConfigType
from kairon.shared.data.base_data import Auditlog
from kairon.shared.data.signals import auditlogger
from kairon.shared.utils import Utility


@auditlogger.log
class IdpConfig(Document):
    user = StringField(required=True)
    account = LongField(required=True)
    status = BooleanField(default=True)
    config_type = StringField(choices=[config_type.value for config_type in IDPConfigType])
    idp_server = StringField()
    realm_name = StringField()
    client_id = StringField()
    client_secret = StringField()

    @classmethod
    def pre_save_post_validation(cls, sender, document, **kwargs):
        if Utility.check_empty_string(document.idp_server):
            document.idp_server = Utility.environment["idp"]["server_url"]

        document.client_id = Utility.encrypt_message(document.client_id)
        document.client_secret = Utility.encrypt_message(document.client_secret)


signals.pre_save_post_validation.connect(IdpConfig.pre_save_post_validation, sender=IdpConfig)


class KeycloakRealm(Document):
    user = StringField(required=True)
    account = LongField(required=True)
    status = BooleanField(default=True)
    realm_name = StringField()
