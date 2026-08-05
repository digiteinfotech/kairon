from typing import Dict, List, Type

from kairon.exceptions import AppException
from kairon.shared.utils import Utility
from kairon.shared.voice.tts.base import BaseTTS


class TTSFactory:
    """
    Registry-backed factory for streaming TTS adapters.

    A provider is usable only when it is BOTH declared in metadata/tts_providers.yml
    AND has a concrete adapter registered via `register`. Concrete adapters register
    themselves at import time (added in the MVP phase).
    """

    __implementations: Dict[str, Type[BaseTTS]] = {}

    @classmethod
    def register(cls, provider: str, impl: Type[BaseTTS]) -> None:
        cls.__implementations[provider] = impl

    @classmethod
    def supported_providers(cls) -> List[str]:
        return list(Utility.system_metadata.get("tts_providers", {}).keys())

    @classmethod
    def provider_metadata(cls, provider: str) -> dict:
        providers = Utility.system_metadata.get("tts_providers", {})
        if provider not in providers:
            raise AppException(f"TTS provider '{provider}' is not configured in metadata")
        return providers[provider]

    @classmethod
    def get(cls, provider: str) -> Type[BaseTTS]:
        cls.provider_metadata(provider)
        if provider not in cls.__implementations:
            raise AppException(f"TTS provider '{provider}' has no adapter implementation")
        return cls.__implementations[provider]
