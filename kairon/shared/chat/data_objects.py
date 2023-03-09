from mongoengine import Document, StringField, DictField, DateTimeField, ValidationError
from datetime import datetime

from kairon.chat.converters.channels.constants import CHANNEL_TYPES
from kairon.shared.constants import WhatsappBSPTypes
from kairon.shared.data.signals import push_notification
from kairon.shared.utils import Utility


@push_notification.apply
class Channels(Document):
    bot = StringField(required=True)
    connector_type = StringField(required=True, choices=Utility.get_channels)
    config = DictField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    meta_config = DictField()

    def validate(self, clean=True):
        from kairon.shared.data.utils import DataUtility
        from kairon.shared.data.processor import MongoProcessor

        bot_settings = MongoProcessor.get_bot_settings(self.bot, self.user)
        bot_settings = bot_settings.to_mongo().to_dict()
        bsp_type = self.config.get('bsp_type', "meta")
        if self.connector_type == CHANNEL_TYPES.WHATSAPP.value and bot_settings["whatsapp"] != bsp_type:
            raise ValidationError("Feature disabled for this account. Please contact support!")

        Utility.validate_channel(self.connector_type, self.config, ValidationError)
        if self.connector_type == "telegram":
            webhook_url = DataUtility.get_channel_endpoint({
                'bot': self.bot, 'user': self.user, 'connector_type': self.connector_type
            })
            Utility.register_telegram_webhook(Utility.decrypt_message(self.config['access_token']), webhook_url)

