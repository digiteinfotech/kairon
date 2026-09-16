"""
AWS Polly text-to-speech adapter.

Implements :class:`~kairon.shared.voice.tts.base.BaseTTS` using Polly's
``synthesize_speech`` with ``OutputFormat="pcm"`` — Polly returns 16-bit signed
little-endian mono PCM at 8000/16000 Hz, exactly the ``audio/x-l16`` format
Exotel streams, so no transcoding is needed.

``boto3`` is a synchronous SDK; the blocking call is offloaded to a thread so the
call loop's event loop is never stalled. The import is lazy so this module can be
imported (and the adapter registered) without boto3 present.
"""
import asyncio
import logging
from typing import AsyncIterator, Optional

from kairon.exceptions import AppException
from kairon.shared.voice.tts.base import BaseTTS
from kairon.shared.voice.tts.factory import TTSFactory

logger = logging.getLogger(__name__)

# ~50 ms of 8 kHz/16-bit audio per yielded chunk; the gateway re-frames to
# Exotel's 320-byte multiple, this just bounds memory / first-audio latency.
_YIELD_CHUNK = 800


class PollyTTS(BaseTTS):
    def __init__(
        self,
        config: dict,
        voice: Optional[str] = None,
        language: Optional[str] = None,
        sample_rate: int = 8000,
    ):
        super().__init__(config, voice=voice, language=language, sample_rate=sample_rate)
        self.access_key = config.get("aws_access_key_id")
        self.secret_key = config.get("aws_secret_access_key")
        self.region = config.get("region", "ap-south-1")
        self.engine = config.get("engine", "neural")
        self.voice = voice or config.get("default_voice") or "Kajal"
        if not self.access_key or not self.secret_key:
            raise AppException(
                "Polly TTS requires 'aws_access_key_id' and 'aws_secret_access_key'"
            )

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        if not text or not text.strip():
            return
        loop = asyncio.get_event_loop()
        audio = await loop.run_in_executor(None, self._synthesize_sync, text)
        for i in range(0, len(audio), _YIELD_CHUNK):
            yield audio[i:i + _YIELD_CHUNK]

    def _synthesize_sync(self, text: str) -> bytes:
        try:
            import boto3
        except ImportError as e:  # pragma: no cover - env dependent
            raise AppException("`boto3` package is required for Polly TTS") from e
        client = boto3.client(
            "polly",
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region,
        )
        try:
            response = client.synthesize_speech(
                Text=text,
                OutputFormat="pcm",
                VoiceId=self.voice,
                Engine=self.engine,
                SampleRate=str(self.sample_rate),
            )
        except Exception as e:  # pragma: no cover - network dependent
            raise AppException(f"Polly synthesis failed: {e}") from e
        stream = response.get("AudioStream")
        if stream is None:
            return b""
        return stream.read()


TTSFactory.register("polly", PollyTTS)
