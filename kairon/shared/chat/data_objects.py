from mongoengine import Document, StringField, DictField, DateTimeField, ValidationError
from datetime import datetime
from .constant import SLACKCONSTANT
from kairon.shared.utils import Utility


class Channels(Document):
    bot = StringField(required=True)
    connector_type = StringField(required=True, choices=[SLACKCONSTANT.slack_connector.value])
    config = DictField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)

    def validate(self, clean=True):
        if self.connector_type in [SLACKCONSTANT.slack_connector.value]:
            if (SLACKCONSTANT.slack_token.value not in self.config
                    or SLACKCONSTANT.slack_signing_secret.value not in self.config):
                raise ValidationError(
                    f"Missing {SLACKCONSTANT.slack_token.value} or {SLACKCONSTANT.slack_signing_secret.value} in config")
            self.config[SLACKCONSTANT.slack_token.value] = Utility.encrypt_message(self.config[SLACKCONSTANT.slack_token.value])
            self.config[SLACKCONSTANT.slack_signing_secret.value] = Utility.encrypt_message(
                self.config[SLACKCONSTANT.slack_signing_secret.value])
        else:
            raise ValidationError(f"Invalid channel type {self.connector_type}")
