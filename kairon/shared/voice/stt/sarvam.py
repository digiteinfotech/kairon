"""Sarvam streaming speech-to-text adapter.

Implements :class:`~kairon.shared.voice.stt.base.BaseSTT` over Sarvam's realtime
STT WebSocket. Audio frames pushed by the gateway are forwarded to Sarvam; the
partial and final transcripts Sarvam emits are surfaced through
:meth:`transcripts`.

The ``websockets`` dependency is imported lazily inside :meth:`open` so importing
this module (e.g. at factory registration time) never requires the SDK to be
installed. The vendor message shape is isolated in the pure, unit-testable
:meth:`_parse_result` static method so it can be corrected without touching the
streaming machinery.
"""
import asyncio
import base64
import json
import logging
from typing import AsyncIterator, Optional

try:
    import audioop
except ImportError:  # pragma: no cover
    audioop = None

from kairon.exceptions import AppException
from kairon.shared.voice.stt.base import BaseSTT, Transcript
from kairon.shared.voice.stt.factory import STTFactory
from kairon.shared.voice.utils import VoiceUtils

logger = logging.getLogger(__name__)


class SarvamSTT(BaseSTT):
    """Streaming STT adapter backed by Sarvam's real-time WebSocket API."""

    NATIVE_RATES = (8000, 16000)
    FALLBACK_RATE = 16000

    def __init__(self, config: dict, language: str, sample_rate: int = 8000):
        """Validate api_key and set up internal queue and socket state."""
        super().__init__(config, language, sample_rate)
        self.api_key = config.get("api_key")
        if not self.api_key:
            raise AppException("Sarvam STT requires 'api_key' in provider config")
        self.endpoint = config.get("stt_url") or VoiceUtils.provider_default("stt", "sarvam", "endpoint")
        self.model = config.get("stt_model") or VoiceUtils.provider_default("stt", "sarvam", "model")
        self.stream_rate = self.sample_rate if self.sample_rate in self.NATIVE_RATES else self.FALLBACK_RATE
        if self.stream_rate != self.sample_rate and audioop is None:
            raise AppException(
                f"Sarvam STT cannot downsample {self.sample_rate} Hz audio on this Python version; "
                f"use one of {list(self.NATIVE_RATES)} Hz"
            )
        self._resample_state = None
        self._ws = None
        self._queue: "asyncio.Queue" = asyncio.Queue()
        self._receiver_task: Optional[asyncio.Task] = None
        self._closed = False

    async def open(self) -> None:
        """Connect to Sarvam STT WebSocket and start the background receive loop."""
        try:
            import websockets
        except ImportError as e:  # pragma: no cover - env dependent
            raise AppException(
                "`websockets` package is required for Sarvam streaming STT"
            ) from e
        url = (
            f"{self.endpoint}?language_code={self.language}&model={self.model}"
            f"&sample_rate={self.stream_rate}&encoding=linear16"
        )
        self._ws = await websockets.connect(
            url, extra_headers={"API-SUBSCRIPTION-KEY": self.api_key}
        )
        self._receiver_task = asyncio.ensure_future(self._receive_loop())

    async def push(self, pcm: bytes) -> None:
        """Base64-encode and send a PCM chunk to the active WebSocket session."""
        if self._ws is None:
            raise AppException("SarvamSTT.push() called before open()")
        if not pcm:
            return
        if self.stream_rate != self.sample_rate:
            pcm, self._resample_state = audioop.ratecv(
                pcm, 2, 1, self.sample_rate, self.stream_rate, self._resample_state
            )
            if not pcm:
                return
        message = json.dumps(
            {"event": "audio_input", "audio": base64.b64encode(pcm).decode("ascii")}
        )
        await self._ws.send(message)

    async def _receive_loop(self) -> None:
        try:
            async for raw in self._ws:
                transcript = self._parse_result(raw)
                if transcript is not None:
                    await self._queue.put(transcript)
        except asyncio.CancelledError:  # pragma: no cover
            raise
        except Exception as e:  # pragma: no cover - network dependent
            logger.debug("Sarvam STT receive loop ended: %s", e)
        finally:
            await self._queue.put(None)  # sentinel -> ends transcripts()

    async def transcripts(self) -> AsyncIterator[Transcript]:
        """Yield Transcript objects as Sarvam emits them; ends when socket closes."""
        while True:
            item = await self._queue.get()
            if item is None:
                break
            yield item

    @staticmethod
    def _parse_result(raw) -> Optional[Transcript]:
        """Map a Sarvam WS message to a :class:`Transcript`; ``None`` for non-transcript messages."""
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8", errors="replace")
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
        except (ValueError, TypeError):
            return None
        if not isinstance(data, dict):
            return None
        event = str(data.get("event", "")).lower()
        if event in ("transcript.partial", "transcript.final"):
            return Transcript(
                text=str(data.get("text") or ""),
                is_final=event == "transcript.final",
                confidence=None,
            )
        if event:
            return None
        return SarvamSTT._parse_legacy_result(data)

    @staticmethod
    def _parse_legacy_result(data: dict) -> Optional[Transcript]:
        """Parse the older, event-less message shape.

        Tolerant of the several field names Sarvam has used: text under ``transcript``/``text`` (also nested in
        ``data``), finality under ``is_final``/``final`` or a ``type`` of ``"final"``/``"transcript"``.
        """
        msg_type = str(data.get("type", "")).lower()
        if msg_type in ("error", "ready", "connected", "pong", "metadata"):
            return None
        text = data.get("transcript")
        if text is None:
            text = data.get("text")
        if text is None:
            inner = data.get("data")
            if isinstance(inner, dict):
                text = inner.get("transcript") or inner.get("text")
        if text is None:
            return None
        is_final = data.get("is_final")
        if is_final is None:
            is_final = data.get("final")
        if is_final is None:
            is_final = msg_type in ("final", "transcript")
        return Transcript(text=str(text), is_final=bool(is_final), confidence=data.get("confidence"))

    async def close(self) -> None:
        """Cancel the receive loop and close the WebSocket connection."""
        if self._closed:
            return
        self._closed = True
        if self._receiver_task is not None:
            self._receiver_task.cancel()
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception as e:  # pragma: no cover
                logger.debug("Error closing Sarvam STT socket: %s", e)


STTFactory.register("sarvam", SarvamSTT)
