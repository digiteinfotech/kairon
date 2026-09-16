import logging
from typing import Dict, List, Type

from kairon.exceptions import AppException
from kairon.shared.utils import Utility
from kairon.shared.voice.tts.base import BaseTTS

logger = logging.getLogger(__name__)

# Built-in adapter modules imported lazily on first use; importing each triggers
# its `TTSFactory.register(...)` call. Vendor SDKs stay lazily imported inside the
# adapters, so this import never pulls in boto3/etc.
_BUILTIN_ADAPTERS = ("kairon.shared.voice.tts.polly",)


class TTSFactory:
    """
    Registry-backed factory for streaming TTS adapters.

    A provider is usable only when it is BOTH declared in metadata/tts_providers.yml
    AND has a concrete adapter registered via `register`. Built-in adapters
    self-register when `_ensure_builtin_adapters` imports them (first `get`);
    external code may add more at any time via `register`.
    """

    __implementations: Dict[str, Type[BaseTTS]] = {}
    _builtin_loaded: bool = False

    @classmethod
    def _ensure_builtin_adapters(cls) -> None:
        if cls._builtin_loaded:
            return
        cls._builtin_loaded = True
        for module in _BUILTIN_ADAPTERS:
            try:
                __import__(module)
            except Exception as e:  # pragma: no cover - defensive
                logger.warning("Could not load built-in TTS adapter %s: %s", module, e)

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
        cls._ensure_builtin_adapters()
        if provider not in cls.__implementations:
            raise AppException(f"TTS provider '{provider}' has no adapter implementation")
        return cls.__implementations[provider]
