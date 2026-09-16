"""
Exotel Voice Streaming (Voicebot) WebSocket protocol.

Exotel streams a live call to a bidirectional WebSocket as JSON text frames. The
shape mirrors Twilio Media Streams closely:

    inbound (Exotel -> us):
        {"event": "connected"}
        {"event": "start", "stream_sid": "...", "sequence_number": "1",
         "start": {"call_sid": "...", "account_sid": "...", "from": "...",
                   "to": "...", "media_format": {"encoding": "audio/x-l16",
                   "sample_rate": 8000}, "custom_parameters": {...}}}
        {"event": "media", "stream_sid": "...", "sequence_number": "2",
         "media": {"payload": "<base64 pcm>", "timestamp": "...", "chunk": "1"}}
        {"event": "dtmf", "stream_sid": "...", "dtmf": {"digit": "1"}}
        {"event": "mark", "stream_sid": "...", "mark": {"name": "..."}}
        {"event": "stop", "stream_sid": "...", "stop": {"call_sid": "..."}}

    outbound (us -> Exotel):
        {"event": "media", "stream_sid": "...", "media": {"payload": "<base64>"}}
        {"event": "mark", "stream_sid": "...", "mark": {"name": "..."}}
        {"event": "clear", "stream_sid": "..."}     # flush buffered playback

Audio is raw 16-bit signed little-endian PCM (``audio/x-l16``) at the call's
sample rate (8000 Hz for telephony), base64-encoded in ``media.payload``.

This module is intentionally dependency-free (stdlib only) so the framing logic
can be unit-tested without a live socket or any kairon/rasa imports.
"""
import base64
import binascii
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class ExotelEvent(str, Enum):
    CONNECTED = "connected"
    START = "start"
    MEDIA = "media"
    DTMF = "dtmf"
    MARK = "mark"
    STOP = "stop"
    CLEAR = "clear"


@dataclass
class StartInfo:
    """Parsed ``start`` payload: call identity and negotiated media format."""
    stream_sid: str = ""
    call_sid: str = ""
    account_sid: str = ""
    from_number: str = ""
    to_number: str = ""
    sample_rate: int = 8000
    encoding: str = "audio/x-l16"
    custom_parameters: Dict[str, Any] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class InboundFrame:
    """A normalised view over one inbound Exotel frame.

    ``media_payload`` holds the *decoded* PCM bytes (not the base64 string) so
    callers never touch the wire encoding.
    """
    event: str
    stream_sid: str = ""
    sequence_number: Optional[int] = None
    media_payload: Optional[bytes] = None
    media_timestamp: Optional[str] = None
    media_chunk: Optional[str] = None
    dtmf_digit: Optional[str] = None
    mark_name: Optional[str] = None
    start: Optional[StartInfo] = None
    raw: Dict[str, Any] = field(default_factory=dict)


def _to_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_inbound(message: Any) -> InboundFrame:
    """Parse a raw Exotel frame (JSON ``str``/``bytes`` or already-decoded dict)
    into an :class:`InboundFrame`. Unknown/malformed frames yield an
    ``InboundFrame`` with the best-effort event name and ``raw`` populated, never
    an exception — a noisy carrier must not tear down the call loop.
    """
    if isinstance(message, (bytes, bytearray)):
        message = message.decode("utf-8", errors="replace")
    if isinstance(message, str):
        try:
            message = json.loads(message)
        except (ValueError, TypeError):
            return InboundFrame(event="", raw={"unparsed": str(message)})
    if not isinstance(message, dict):
        return InboundFrame(event="", raw={"unparsed": repr(message)})

    event = str(message.get("event", "")).lower()
    stream_sid = message.get("stream_sid") or message.get("streamSid") or ""
    frame = InboundFrame(
        event=event,
        stream_sid=stream_sid,
        sequence_number=_to_int(message.get("sequence_number")),
        raw=message,
    )

    if event == ExotelEvent.MEDIA.value:
        media = message.get("media") or {}
        frame.media_payload = decode_payload(media.get("payload"))
        frame.media_timestamp = media.get("timestamp")
        frame.media_chunk = media.get("chunk")
    elif event == ExotelEvent.START.value:
        start = message.get("start") or {}
        media_format = start.get("media_format") or start.get("mediaFormat") or {}
        frame.start = StartInfo(
            stream_sid=stream_sid or start.get("stream_sid", ""),
            call_sid=start.get("call_sid") or start.get("callSid") or "",
            account_sid=start.get("account_sid") or start.get("accountSid") or "",
            from_number=start.get("from") or start.get("from_number") or "",
            to_number=start.get("to") or start.get("to_number") or "",
            sample_rate=_to_int(media_format.get("sample_rate")) or 8000,
            encoding=media_format.get("encoding") or "audio/x-l16",
            custom_parameters=start.get("custom_parameters")
            or start.get("customParameters")
            or {},
            raw=start,
        )
        if not frame.stream_sid:
            frame.stream_sid = frame.start.stream_sid
    elif event == ExotelEvent.DTMF.value:
        dtmf = message.get("dtmf") or {}
        frame.dtmf_digit = dtmf.get("digit") or dtmf.get("digits")
    elif event == ExotelEvent.MARK.value:
        mark = message.get("mark") or {}
        frame.mark_name = mark.get("name")

    return frame


def decode_payload(payload: Optional[str]) -> bytes:
    """Base64-decode a media payload to raw PCM bytes; tolerant of ``None``,
    padding errors, and urlsafe encoding."""
    if not payload:
        return b""
    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode("ascii", errors="replace")
    # pad to a multiple of 4 so a truncated frame still decodes what it can
    padded = payload + "=" * (-len(payload) % 4)
    try:
        return base64.b64decode(padded)
    except (binascii.Error, ValueError):
        try:
            return base64.urlsafe_b64decode(padded)
        except (binascii.Error, ValueError):
            return b""


def encode_payload(pcm: bytes) -> str:
    """Base64-encode raw PCM bytes for an outbound media frame."""
    return base64.b64encode(pcm).decode("ascii")


def build_media(stream_sid: str, pcm: bytes) -> Dict[str, Any]:
    """Build an outbound ``media`` frame carrying ``pcm`` audio to the caller."""
    return {
        "event": ExotelEvent.MEDIA.value,
        "stream_sid": stream_sid,
        "media": {"payload": encode_payload(pcm)},
    }


def build_mark(stream_sid: str, name: str) -> Dict[str, Any]:
    """Build a ``mark`` frame. Exotel echoes it back once the audio queued before
    it has finished playing — used to know when the bot's utterance is done."""
    return {
        "event": ExotelEvent.MARK.value,
        "stream_sid": stream_sid,
        "mark": {"name": name},
    }


def build_clear(stream_sid: str) -> Dict[str, Any]:
    """Build a ``clear`` frame to discard audio already buffered on Exotel's side
    (used for barge-in / interrupting the bot)."""
    return {"event": ExotelEvent.CLEAR.value, "stream_sid": stream_sid}
