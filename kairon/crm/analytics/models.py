from datetime import datetime
from enum import Enum

from mongoengine import (
    Document, StringField, IntField, FloatField, BooleanField, DateTimeField, DictField,
)
from mongoengine.errors import ValidationError

from kairon.shared.data.audit.data_objects import Auditlog
from kairon.shared.data.signals import auditlogger

MAX_PROMPT_LENGTH = 4000


class LeadRecordStatus(str, Enum):
    UNQUALIFIED = "UNQUALIFIED"              # analysed, not a lead (re-analysed if the conversation continues)
    NEEDS_CONTACT = "NEEDS_CONTACT"          # qualified by the model but no verifiable email/phone yet
    QUALIFIED = "QUALIFIED"                  # qualified, delivery to ERPNext pending (or being retried)
    DISPATCHED = "DISPATCHED"                # ERPNext accepted the lead (final)
    ANALYSIS_FAILED = "ANALYSIS_FAILED"      # LLM/parse error, will be retried
    FAILED_PERMANENT = "FAILED_PERMANENT"    # gave up after MAX_ATTEMPTS: the dead-letter set


@auditlogger.log
class CRMLeadQualificationConfig(Auditlog):
    """The company's active lead-qualification criteria. One per bot; the bot is the tenant boundary."""
    bot = StringField(required=True)
    prompt = StringField(required=True)
    version = IntField(default=1)
    enabled = BooleanField(default=True)
    min_confidence = FloatField(default=0.7)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)

    meta = {"indexes": [{"fields": ["bot"], "unique": True}]}

    def validate(self, clean=True):
        prompt = (self.prompt or "").strip()
        if not prompt:
            raise ValidationError("Lead qualification prompt cannot be empty")
        if len(prompt) > MAX_PROMPT_LENGTH:
            raise ValidationError(f"Lead qualification prompt must be at most {MAX_PROMPT_LENGTH} characters")
        if not 0.0 <= float(self.min_confidence if self.min_confidence is not None else 0.7) <= 1.0:
            raise ValidationError("min_confidence must be between 0 and 1")


class CRMLeadPromptRevision(Document):
    """Immutable history so every analysis result can name the exact criteria text that produced it."""
    bot = StringField(required=True)
    version = IntField(required=True)
    prompt = StringField(required=True)
    user = StringField(required=True)
    timestamp = DateTimeField(default=datetime.utcnow)

    meta = {"indexes": [{"fields": ["bot", "-version"], "unique": True}]}


class CRMLeadAnalysisState(Document):
    """Per-bot watermark plus a lease so overlapping runs and multiple workers never process the same bot twice."""
    bot = StringField(required=True)
    watermark = FloatField(default=0.0)            # epoch seconds: conversations up to here have been handled
    lease_owner = StringField()
    lease_until = DateTimeField()
    last_run_at = DateTimeField()
    last_run_stats = DictField()
    last_error = StringField()

    meta = {"indexes": [{"fields": ["bot"], "unique": True}]}


class CRMLeadAnalysisRecord(Document):
    """One row per (bot, sender). Gives idempotency, retry state and the permanent-failure (dead-letter) view."""
    bot = StringField(required=True)
    sender_id = StringField(required=True)
    status = StringField(required=True, choices=[s.value for s in LeadRecordStatus])
    last_message_ts = FloatField(default=0.0)      # newest message already covered by this analysis
    prompt_version = IntField()
    confidence = FloatField()
    reason = StringField()                         # the model's explanation (short)
    lead_fields = DictField()
    event_id = StringField()                       # stable, so a retried delivery is the same event
    attempts = IntField(default=0)
    next_attempt_at = DateTimeField()
    last_error = StringField()
    dispatched_at = DateTimeField()
    updated_at = DateTimeField(default=datetime.utcnow)

    meta = {
        "indexes": [
            {"fields": ["bot", "sender_id"], "unique": True},
            {"fields": ["bot", "status", "next_attempt_at"]},
        ]
    }
