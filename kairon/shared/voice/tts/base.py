from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional


class BaseTTS(ABC):
    """
    Provider-agnostic streaming text-to-speech adapter.

    Concrete adapters (AWS Polly, Sarvam, ElevenLabs, Google, ...) live behind this
    interface and are registered with TTSFactory. `synthesize` yields raw PCM chunks
    so the gateway can start sending audio to the caller before the whole utterance
    is rendered. Chunking to Exotel's 320-byte-multiple rule is done by the gateway,
    not here.
    """

    def __init__(
        self,
        config: dict,
        voice: Optional[str] = None,
        language: Optional[str] = None,
        sample_rate: int = 8000,
    ):
        self.config = config
        self.voice = voice
        self.language = language
        self.sample_rate = sample_rate

    @abstractmethod
    def synthesize(self, text: str) -> AsyncIterator[bytes]:
        """Async-iterate raw PCM audio chunks for `text`."""
        raise NotImplementedError
