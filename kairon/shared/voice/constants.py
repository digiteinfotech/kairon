"""Constants shared by the voice channel code: defaults and call lifecycle statuses."""
from enum import Enum

DEFAULT_SAMPLE_RATE = 8000
EXOTEL_SAMPLE_RATES = (8000, 16000)
DEFAULT_SPEECH_PROVIDER = "sarvam"
EXOTEL_DOMAIN_SUFFIX = ".exotel.com"

MAX_CALL_DURATION_LIMIT_SECONDS = 14400

DEFAULT_NOINPUT_TIMEOUT_SECONDS = 8
DEFAULT_MAX_NOINPUT_ATTEMPTS = 1

CALLBACK_AUDIT_INITIATOR = "provider_callback"
UNKNOWN_CALL_SID = "unknown"


class CallStatus(str, Enum):
    """Lifecycle status of a call row."""

    INITIATED = "initiated"
    ANSWERED = "answered"
    COMPLETED = "completed"
    FAILED = "failed"


class CallEndReason(str, Enum):
    """Why a call that reached us ended."""

    CALLER_HANGUP = "caller_hangup"
    BOT_DISCONNECT = "bot_disconnect"
    NOINPUT_TIMEOUT = "noinput_timeout"
    MAX_DURATION = "max_duration"
    ERROR = "error"


TERMINAL_STATUSES = {
    CallStatus.COMPLETED.value,
    CallStatus.FAILED.value,
    "busy",
    "no-answer",
    "canceled",
}
PROVIDER_STATUS_MAP = {
    "completed": CallStatus.COMPLETED.value,
    "failed": CallStatus.FAILED.value,
    "busy": "busy",
    "no-answer": "no-answer",
    "no_answer": "no-answer",
    "noanswer": "no-answer",
    "canceled": "canceled",
    "cancelled": "canceled",
}
EXCLUDED_CARRY_OVER_SLOTS = {"session_started_metadata", "requested_slot"}
MAX_CARRY_OVER_SLOT_CHARS = 2000

DEFAULT_REPROMPT_PHRASE = "I'm sorry, I didn't get that. Could you please repeat?"
DEFAULT_TIMEOUT_MESSAGE = "We didn't hear from you. Thanks for your time. Goodbye."
DEFAULT_MAX_DURATION_MESSAGE = "I'm sorry, we have reached the maximum call duration. Thank you for your time. Goodbye."
PLAYBACK_WAIT_SECONDS = 5.0

PROVIDER_DEFAULTS = {
    "stt": {
        "sarvam": {
            "endpoint": "wss://api.sarvam.ai/speech-to-text-realtime/ws",
            "model": "saaras:v4",
        },
    },
    "tts": {
        "sarvam": {
            "endpoint": "https://api.sarvam.ai/text-to-speech",
            "model": "bulbul:v3",
            "speaker": "shubh",
        },
        "polly": {"speaker": "Kajal"},
    },
}
