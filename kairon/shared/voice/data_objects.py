from datetime import datetime

from mongoengine import (
    Document,
    StringField,
    DictField,
    DateTimeField,
    BooleanField,
    IntField,
    FloatField,
    ValidationError,
)

from kairon.shared.data.audit.data_objects import Auditlog
from kairon.shared.data.signals import auditlogger, push_notification


@auditlogger.log
@push_notification.apply
class SpeechProviderConfig(Auditlog):
    """
    STT/TTS provider configuration — global (Kairon-managed) or bot-scoped (BYOK).

    `metadata` holds non-secret provider config (URLs, model, speaker, etc.).
    `secrets` holds encrypted credential fields (encrypted by SpeechProviderConfigProcessor).
    Bot-scoped entries override global ones during resolution.
    """
    provider = StringField(required=True)
    scope = StringField(required=True, choices=["global", "bot"])
    bot_id = StringField(null=True)
    metadata = DictField(default=dict)
    secrets = DictField(default=dict)
    status = BooleanField(default=True)
    timestamp = DateTimeField(default=datetime.utcnow)

    meta = {
        "indexes": [
            {"fields": ["provider", "scope", "bot_id"]},
        ]
    }

    def validate(self, clean=True):
        if not self.provider:
            raise ValidationError("provider is required")
        if self.scope == "bot" and not self.bot_id:
            raise ValidationError("bot_id is required when scope='bot'")


class VoiceCallMetrics(Document):
    """
    Per-call latency/quality metrics for a streaming voice call.

    One document is written when a call ends: agent think-time and TTS synthesis
    time (average and worst-case across turns), TTS cache hit count, turn count
    and total duration. Used for latency dashboards and provider comparison.
    """
    bot = StringField(required=True)
    call_sid = StringField(default="")
    provider = StringField(default="exotel")
    stt_provider = StringField(default="")
    tts_provider = StringField(default="")
    turns = IntField(default=0)
    duration_ms = FloatField(default=0.0)
    agent_ms_avg = FloatField(default=0.0)
    agent_ms_max = FloatField(default=0.0)
    tts_ms_avg = FloatField(default=0.0)
    tts_ms_max = FloatField(default=0.0)
    tts_cache_hits = IntField(default=0)
    timestamp = DateTimeField(default=datetime.utcnow)

    meta = {
        "indexes": [
            {"fields": ["bot", "call_sid"]},
            {"fields": ["timestamp"]},
        ]
    }
