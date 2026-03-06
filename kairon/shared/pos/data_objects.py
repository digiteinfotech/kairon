from datetime import datetime

from mongoengine import StringField, DateTimeField, DictField, ListField
from mongoengine.errors import ValidationError

from kairon import Utility
from kairon.shared.pos.constants import POSType, OnboardingStatus
from kairon.shared.data.audit.data_objects import Auditlog
from kairon.shared.data.signals import auditlogger


@auditlogger.log
class POSClientDetails(Auditlog):
    client_name = StringField(required=True)
    pos_type = StringField(required=True, default=POSType.odoo.value,
                           choices=[pos_type.value for pos_type in POSType])
    onboarding_status = StringField(required=True, default=OnboardingStatus.initiated.value,
                                    choices=[status.value for status in OnboardingStatus])
    bot = StringField(required=True)
    user = StringField(required=True)
    config = DictField(required=True)
    branches = ListField(DictField())
    timestamp = DateTimeField(default=datetime.utcnow)


    meta = {
        "indexes": [
            {"fields": ["bot", "client_name"], "unique": True},
            {"fields": ["bot", "client_name", "pos_type"]}
        ]
    }

    def validate(self, clean=True):
        if Utility.check_empty_string(self.client_name):
            raise ValidationError("Client Name is required")
        if not self.config:
            raise ValidationError("POS Config is required")
