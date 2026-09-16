"""
Sarvam text-to-speech adapter.

POST https://api.sarvam.ai/text-to-speech — returns base64-encoded WAV.
WAV is decoded, stripped to raw PCM, and resampled to the target sample rate.
The blocking HTTP call is offloaded to a thread pool so the event loop is not stalled.
"""
import asyncio
import base64
import io
import logging
import wave
from typing import AsyncIterator, Optional

from kairon.exceptions import AppException
from kairon.shared.voice.tts.base import BaseTTS
from kairon.shared.voice.tts.factory import TTSFactory

logger = logging.getLogger(__name__)

_DEFAULT_ENDPOINT = "https://api.sarvam.ai/text-to-speech"
_YIELD_CHUNK = 800  # ~50 ms of 8 kHz/16-bit audio per yield


def _wav_to_pcm(wav_bytes: bytes, target_rate: int) -> bytes:
    """Decode WAV bytes → raw 16-bit signed mono PCM at target_rate."""
    import audioop
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        rate = w.getframerate()
        channels = w.getnchannels()
        width = w.getsampwidth()
        pcm = w.readframes(w.getnframes())
    if channels == 2:
        pcm = audioop.tomono(pcm, width, 0.5, 0.5)
    if width != 2:
        pcm = audioop.lin2lin(pcm, width, 2)
    if rate != target_rate:
        pcm, _ = audioop.ratecv(pcm, 2, 1, rate, target_rate, None)
    return pcm


class SarvamTTS(BaseTTS):
    """TTS adapter that calls the Sarvam HTTP API and decodes WAV to PCM chunks."""

    DEFAULT_MODEL = "bulbul:v2"
    DEFAULT_SPEAKER = "anushka"

    def __init__(
        self,
        config: dict,
        voice: Optional[str] = None,
        language: Optional[str] = None,
        sample_rate: int = 8000,
    ):
        """Validate api_key and resolve model, speaker and language from config."""
        super().__init__(config, voice=voice, language=language, sample_rate=sample_rate)
        self.api_key = config.get("api_key")
        if not self.api_key:
            raise AppException("Sarvam TTS requires 'api_key' in provider config")
        self.endpoint = config.get("tts_url") or _DEFAULT_ENDPOINT
        self.model = config.get("tts_model") or config.get("model") or self.DEFAULT_MODEL
        # config["speaker"] (SpeechProviderConfig) takes priority over generic voice_override
        self.speaker = config.get("speaker") or voice or self.DEFAULT_SPEAKER
        self.language = language or config.get("language", "en-IN")

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        """POST to Sarvam TTS in a thread, decode WAV to PCM, yield chunks."""
        if not text or not text.strip():
            return
        loop = asyncio.get_running_loop()
        pcm = await loop.run_in_executor(None, self._synthesize_sync, text)
        for i in range(0, len(pcm), _YIELD_CHUNK):
            yield pcm[i:i + _YIELD_CHUNK]

    def _synthesize_sync(self, text: str) -> bytes:
        try:
            import requests
        except ImportError as e:
            raise AppException("`requests` package is required for Sarvam TTS") from e
        resp = requests.post(
            self.endpoint,
            headers={
                "api-subscription-key": self.api_key,
                "Content-Type": "application/json",
            },
            json={
                "text": text,
                "target_language_code": self.language,
                "speaker": self.speaker,
                "model": self.model,
            },
            timeout=30,
        )
        if resp.status_code >= 400:
            logger.warning("Sarvam TTS %s: %s", resp.status_code, resp.text)
        resp.raise_for_status()
        audios = resp.json().get("audios") or []
        if not audios:
            return b""
        wav_bytes = base64.b64decode(audios[0])
        return _wav_to_pcm(wav_bytes, self.sample_rate)


TTSFactory.register("sarvam", SarvamTTS)
