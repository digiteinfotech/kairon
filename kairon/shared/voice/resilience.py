"""
STT/TTS fallback chains.

A single provider outage should not drop a live call. These wrappers accept an
ordered list of *builders* (zero-arg callables that construct a concrete adapter)
derived from the ``fallback_order`` in system.yaml, and fail over between them:

  * :class:`FallbackSTT` — at :meth:`open` it tries each provider until one
    connects, then delegates the rest of the call to that adapter. Streaming STT
    cannot switch mid-utterance, so failover is open-time only.
  * :class:`FallbackTTS` — for each utterance it tries providers in order; if one
    fails *before emitting any audio* it moves to the next. Once audio has begun
    streaming to the caller it commits to that provider (you cannot un-send
    audio).

Both are duck-typed against the STT/TTS interfaces the call session expects, so
they drop in wherever a plain adapter would.
"""
import logging
from typing import AsyncIterator, Callable, List, Optional, Sequence, Tuple

from kairon.exceptions import AppException
from kairon.shared.voice.stt.base import Transcript

logger = logging.getLogger(__name__)

# (provider_name, builder) where builder() -> concrete adapter instance
NamedBuilder = Tuple[str, Callable[[], object]]


def _normalise(builders: Sequence) -> List[NamedBuilder]:
    out: List[NamedBuilder] = []
    for item in builders:
        if isinstance(item, tuple):
            out.append((item[0], item[1]))
        else:
            out.append((getattr(item, "__name__", "provider"), item))
    return out


class FallbackSTT:
    def __init__(self, builders: Sequence):
        self._builders = _normalise(builders)
        if not self._builders:
            raise AppException("FallbackSTT requires at least one provider builder")
        self.active = None
        self.active_provider: Optional[str] = None

    async def open(self) -> None:
        errors = []
        for name, builder in self._builders:
            try:
                adapter = builder()
                await adapter.open()
                self.active = adapter
                self.active_provider = name
                if errors:
                    logger.warning("STT failed over to '%s' after: %s", name, "; ".join(errors))
                return
            except Exception as e:
                errors.append(f"{name}: {e}")
                logger.warning("STT provider '%s' failed to open: %s", name, e)
        raise AppException(f"All STT providers failed to open ({'; '.join(errors)})")

    async def push(self, pcm: bytes) -> None:
        if self.active is not None:
            await self.active.push(pcm)

    async def transcripts(self) -> AsyncIterator[Transcript]:
        if self.active is None:
            return
        async for transcript in self.active.transcripts():
            yield transcript

    async def close(self) -> None:
        if self.active is not None:
            await self.active.close()


class FallbackTTS:
    def __init__(self, builders: Sequence):
        self._builders = _normalise(builders)
        if not self._builders:
            raise AppException("FallbackTTS requires at least one provider builder")

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        errors = []
        for name, builder in self._builders:
            emitted = False
            try:
                adapter = builder()
                async for chunk in adapter.synthesize(text):
                    emitted = True
                    yield chunk
                return  # provider completed the utterance
            except Exception as e:
                if emitted:
                    # already streaming this provider's audio; cannot switch now
                    logger.warning("TTS provider '%s' failed mid-utterance: %s", name, e)
                    return
                errors.append(f"{name}: {e}")
                logger.warning("TTS provider '%s' failed before audio: %s", name, e)
        logger.error("All TTS providers failed for utterance (%s)", "; ".join(errors))
