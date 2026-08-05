"""
Sarvam streaming speech-to-text adapter.

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

from kairon.exceptions import AppException
from kairon.shared.voice.stt.base import BaseSTT, Transcript
from kairon.shared.voice.stt.factory import STTFactory

logger = logging.getLogger(__name__)


class SarvamSTT(BaseSTT):
    ENDPOINT = "wss://api.sarvam.ai/speech-to-text/ws"
    DEFAULT_MODEL = "saarika:v2"

    def __init__(self, config: dict, language: str, sample_rate: int = 8000):
        super().__init__(config, language, sample_rate)
        self.api_key = config.get("api_key")
        if not self.api_key:
            raise AppException("Sarvam STT requires 'api_key' in provider config")
        self.model = config.get("model") or self.DEFAULT_MODEL
        self._ws = None
        self._queue: "asyncio.Queue" = asyncio.Queue()
        self._receiver_task: Optional[asyncio.Task] = None
        self._closed = False

    async def open(self) -> None:
        try:
            import websockets
        except ImportError as e:  # pragma: no cover - env dependent
            raise AppException(
                "`websockets` package is required for Sarvam streaming STT"
            ) from e
        url = (
            f"{self.ENDPOINT}?model={self.model}"
            f"&language-code={self.language}&sample-rate={self.sample_rate}"
        )
        try:
            self._ws = await websockets.connect(
                url, additional_headers={"api-subscription-key": self.api_key}
            )
        except TypeError:  # older websockets uses extra_headers
            self._ws = await websockets.connect(
                url, extra_headers={"api-subscription-key": self.api_key}
            )
        self._receiver_task = asyncio.ensure_future(self._receive_loop())

    async def push(self, pcm: bytes) -> None:
        if self._ws is None:
            raise AppException("SarvamSTT.push() called before open()")
        if not pcm:
            return
        message = json.dumps(
            {
                "audio": {
                    "data": base64.b64encode(pcm).decode("ascii"),
                    "encoding": "audio/x-l16",
                    "sample_rate": self.sample_rate,
                }
            }
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
        while True:
            item = await self._queue.get()
            if item is None:
                break
            yield item

    @staticmethod
    def _parse_result(raw) -> Optional[Transcript]:
        """Map a Sarvam WS message to a :class:`Transcript`.

        Tolerant of the several field names Sarvam has used across versions:
        text under ``transcript``/``text``, finality under ``is_final``/``final``
        or a ``type`` of ``"final"``/``"transcript"``. Returns ``None`` for
        keep-alive/non-transcript messages.
        """
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8", errors="replace")
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
        except (ValueError, TypeError):
            return None
        if not isinstance(data, dict):
            return None
        msg_type = str(data.get("type", "")).lower()
        if msg_type in ("error", "ready", "connected", "pong", "metadata"):
            return None
        text = data.get("transcript")
        if text is None:
            text = data.get("text")
        if text is None:
            inner = data.get("data") or {}
            if isinstance(inner, dict):
                text = inner.get("transcript") or inner.get("text")
        if text is None:
            return None
        is_final = data.get("is_final")
        if is_final is None:
            is_final = data.get("final")
        if is_final is None:
            is_final = msg_type in ("final", "transcript")
        confidence = data.get("confidence")
        return Transcript(text=str(text), is_final=bool(is_final), confidence=confidence)

    async def close(self) -> None:
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
