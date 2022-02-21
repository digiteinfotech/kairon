from mongoengine import Document, StringField, DictField, DateTimeField, ValidationError
from datetime import datetime
from kairon.shared.utils import Utility

class Channels(Document):
    bot = StringField(required=True)
    connector_type = StringField(required=True, choices=Utility.get_channels)
    config = DictField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)

    def validate(self, clean=True):
        Utility.validate_channel_config(self.connector_type, self.config, ValidationError)
        if self.connector_type == "telegram":
            Utility.register_telegram_webhook(Utility.decrypt_message(self.config['access_token']), Utility.decrypt_message(self.config['webhook_url']))

