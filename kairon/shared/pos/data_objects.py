from datetime import datetime

from mongoengine import StringField, DateTimeField
from mongoengine.errors import ValidationError

from kairon.shared.utils import Utility
from kairon.shared.data.audit.data_objects import Auditlog
from kairon.shared.data.signals import auditlogger


@auditlogger.log
class OdooClientDetails(Auditlog):
    client_name = StringField(required=True)
    username = StringField(required=True)
    password = StringField(required=True)
    company = StringField()
    user = StringField(required=True)
    bot = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)

    def validate(self, clean=True):
        if Utility.check_empty_string(self.client_name):
            raise ValidationError("Client Name cannot be empty or blank spaces")
