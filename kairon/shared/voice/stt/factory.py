from typing import Dict, List, Type

from kairon.exceptions import AppException
from kairon.shared.utils import Utility
from kairon.shared.voice.stt.base import BaseSTT


class STTFactory:
    """
    Registry-backed factory for streaming STT adapters.

    A provider is usable only when it is BOTH declared in metadata/stt_providers.yml
    (capabilities, required/secret fields, models) AND has a concrete adapter
    registered via `register`. Concrete adapters register themselves at import time
    (added in the MVP phase), keeping this scaffold free of vendor imports.
    """

    __implementations: Dict[str, Type[BaseSTT]] = {}

    @classmethod
    def register(cls, provider: str, impl: Type[BaseSTT]) -> None:
        cls.__implementations[provider] = impl

    @classmethod
    def supported_providers(cls) -> List[str]:
        return list(Utility.system_metadata.get("stt_providers", {}).keys())

    @classmethod
    def provider_metadata(cls, provider: str) -> dict:
        providers = Utility.system_metadata.get("stt_providers", {})
        if provider not in providers:
            raise AppException(f"STT provider '{provider}' is not configured in metadata")
        return providers[provider]

    @classmethod
    def get(cls, provider: str) -> Type[BaseSTT]:
        cls.provider_metadata(provider)
        if provider not in cls.__implementations:
            raise AppException(f"STT provider '{provider}' has no adapter implementation")
        return cls.__implementations[provider]
