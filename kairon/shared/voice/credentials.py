"""
Voice provider credential resolution (bring-your-own credentials).

STT/TTS credentials come from one of two places, in priority order:

  1. **Per-bot (BYO)** — a :class:`VoiceProviderCredential` document for the bot,
     when the bot's ``VoiceIntegrationSettings.use_bot_credentials`` is set. Secret
     fields inside it are stored encrypted and decrypted here on read, using the
     provider's ``secret_fields`` from the metadata registry.
  2. **Global** — the shared keys under ``voice.providers`` in system.yaml.

The decrypt/merge step is a pure static method so it can be unit-tested without a
database.
"""
import logging
from typing import Callable, List, Optional

from kairon.shared.constants import VoiceServiceType
from kairon.shared.utils import Utility

logger = logging.getLogger(__name__)


class VoiceCredentialResolver:

    @staticmethod
    def _global_credentials(provider: str) -> dict:
        providers = (Utility.environment.get("voice", {}) or {}).get("providers", {}) or {}
        return dict(providers.get(provider, {}) or {})

    @staticmethod
    def metadata_secret_fields(service_type: str, provider: str) -> List[str]:
        registry_key = (
            "stt_providers" if service_type == VoiceServiceType.stt.value else "tts_providers"
        )
        registry = Utility.system_metadata.get(registry_key, {}) or {}
        return list((registry.get(provider, {}) or {}).get("secret_fields", []) or [])

    @staticmethod
    def decrypt_config(config: dict, secret_fields: List[str],
                       decryptor: Optional[Callable[[str], str]] = None) -> dict:
        """Return a copy of ``config`` with each ``secret_fields`` entry decrypted.
        A field that fails to decrypt is left as-is (it may already be plaintext),
        so a mis-stored credential degrades rather than crashing the call."""
        decrypt = decryptor or Utility.decrypt_message
        resolved = dict(config or {})
        for field in secret_fields:
            value = resolved.get(field)
            if value:
                try:
                    resolved[field] = decrypt(value)
                except Exception as e:
                    logger.warning("Could not decrypt voice secret '%s': %s", field, e)
        return resolved

    @classmethod
    def _bot_credentials(cls, bot: str, service_type: str, provider: str) -> Optional[dict]:
        from kairon.shared.voice.data_objects import VoiceProviderCredential

        doc = VoiceProviderCredential.objects(
            bot=bot, type=service_type, provider=provider, status=True
        ).first()
        if not doc:
            return None
        secret_fields = cls.metadata_secret_fields(service_type, provider)
        return cls.decrypt_config(doc.config, secret_fields)

    @classmethod
    def resolve(cls, bot: str, service_type: str, provider: str,
                use_bot_credentials: bool = False) -> dict:
        """Resolve credentials for ``provider``. When ``use_bot_credentials`` is
        set and a per-bot credential exists it wins; otherwise the global keys are
        returned (possibly empty, which the adapter will reject with a clear
        error)."""
        if use_bot_credentials:
            try:
                byo = cls._bot_credentials(bot, service_type, provider)
            except Exception as e:
                logger.warning("BYO voice credential lookup failed bot=%s: %s", bot, e)
                byo = None
            if byo:
                return byo
        return cls._global_credentials(provider)
