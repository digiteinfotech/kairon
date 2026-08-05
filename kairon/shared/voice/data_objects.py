from datetime import datetime

from mongoengine import (
    StringField,
    DictField,
    DateTimeField,
    BooleanField,
    ValidationError,
)

from kairon.shared.constants import VoiceServiceType
from kairon.shared.data.audit.data_objects import Auditlog
from kairon.shared.data.signals import auditlogger, push_notification


@auditlogger.log
@push_notification.apply
class VoiceProviderCredential(Auditlog):
    """
    Bot-scoped credentials for a streaming voice STT/TTS provider (BYO provider).

    Secret fields inside `config` are encrypted by the caller before saving,
    using the provider's `secret_fields` from stt_providers.yml / tts_providers.yml.
    When absent for a bot, the layer falls back to the global keys in system.yaml.
    """
    bot = StringField(required=True)
    user = StringField(required=True)
    type = StringField(
        required=True,
        choices=[VoiceServiceType.stt.value, VoiceServiceType.tts.value],
    )
    provider = StringField(required=True)
    config = DictField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)
    status = BooleanField(default=True)

    meta = {
        "indexes": [
            {"fields": ["bot", "type", "provider"]}
        ]
    }

    def validate(self, clean=True):
        if not self.provider:
            raise ValidationError("provider is required")
        if not self.config:
            raise ValidationError("config is required")
