from datetime import datetime

from mongoengine import StringField, DateTimeField, DictField
from mongoengine.errors import ValidationError

from kairon.shared.pos.constants import POSType
from kairon.shared.data.audit.data_objects import Auditlog
from kairon.shared.data.signals import auditlogger


@auditlogger.log
class POSClientDetails(Auditlog):
    pos_type = StringField(required=True, default=POSType.odoo.value,
                           choices=[pos_type.value for pos_type in POSType])
    config = DictField(required=True)
    user = StringField(required=True)
    bot = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)

    def validate(self, clean=True):
        if not self.config:
            raise ValidationError("POS Config is required")

