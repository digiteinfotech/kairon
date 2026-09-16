from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator, Optional


@dataclass
class Transcript:
    """A single STT result. `is_final` distinguishes streaming partials from the
    endpointed final transcript that is handed to the agent brain."""
    text: str
    is_final: bool
    confidence: Optional[float] = None


class BaseSTT(ABC):
    """
    Provider-agnostic streaming speech-to-text adapter.

    The agent core never imports a vendor SDK; concrete adapters (Sarvam, AWS
    Transcribe, Google, ...) live behind this interface and are registered with
    STTFactory. Usage per call:

        stt = STTFactory.get(provider)(config, language, sample_rate)
        await stt.open()
        await stt.push(pcm_bytes)          # repeatedly, as media frames arrive
        async for t in stt.transcripts():  # partial + final results
            ...
        await stt.close()
    """

    def __init__(self, config: dict, language: str, sample_rate: int = 8000):
        self.config = config
        self.language = language
        self.sample_rate = sample_rate

    @abstractmethod
    async def open(self) -> None:
        """Open the streaming session to the vendor."""
        raise NotImplementedError

    @abstractmethod
    async def push(self, pcm: bytes) -> None:
        """Feed a chunk of raw PCM audio into the stream."""
        raise NotImplementedError

    @abstractmethod
    def transcripts(self) -> AsyncIterator[Transcript]:
        """Async-iterate transcripts (partials then finals) as the vendor emits them."""
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        """Close the streaming session and release resources."""
        raise NotImplementedError
