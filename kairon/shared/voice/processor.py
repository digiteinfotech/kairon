"""Voice provider configuration processor.

Manages ``SpeechProviderConfig`` documents in MongoDB.
Provides CRUD for global (Kairon-managed) and bot-scoped (BYOK) provider
configurations, plus a single-query resolution method used by the telephony
handlers to obtain all required STT/TTS credentials in one DB round-trip.
"""
import logging
from typing import List, Optional

from kairon.exceptions import AppException
from kairon.shared.utils import Utility

logger = logging.getLogger(__name__)


def _secret_fields_for_provider(provider: str) -> List[str]:
    """Return the union of secret_fields from stt_providers + tts_providers metadata."""
    meta = getattr(Utility, "system_metadata", {}) or {}
    fields: set = set()
    for registry_key in ("stt_providers", "tts_providers"):
        spec = (meta.get(registry_key) or {}).get(provider, {}) or {}
        fields.update(spec.get("secret_fields") or [])
    return list(fields)


class SpeechProviderConfigProcessor:

    @staticmethod
    def _encrypt_secrets(provider: str, secrets: dict) -> dict:
        enc = {}
        for field, value in secrets.items():
            if value:
                try:
                    enc[field] = Utility.encrypt_message(value)
                except Exception as e:
                    logger.warning("Could not encrypt voice secret '%s.%s': %s", provider, field, e)
                    enc[field] = value
            else:
                enc[field] = value
        return enc

    @staticmethod
    def _decrypt_secrets(provider: str, secrets: dict) -> dict:
        dec = {}
        for field, value in secrets.items():
            if value:
                try:
                    dec[field] = Utility.decrypt_message(value)
                except Exception as e:
                    logger.warning("Could not decrypt voice secret '%s.%s': %s — kept as-is", provider, field, e)
                    dec[field] = value
            else:
                dec[field] = value
        return dec

    @staticmethod
    def decrypt_config(config: dict, secret_fields: List[str], decryptor=None) -> dict:
        """Decrypt the specified secret fields in config. Non-secret fields are untouched.

        On decryption failure the value is left as-is (graceful degradation).
        Accepts an optional custom decryptor for testability.
        """
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

    @staticmethod
    def _mask_secrets(secrets: dict) -> dict:
        return {field: "**********" if value else value for field, value in secrets.items()}

    @staticmethod
    def _to_dict(doc, mask_secrets: bool = True) -> dict:
        raw = {
            "id": str(doc.id),
            "provider": doc.provider,
            "scope": doc.scope,
            "bot_id": doc.bot_id,
            "metadata": dict(doc.metadata or {}),
            "secrets": (
                SpeechProviderConfigProcessor._mask_secrets(doc.secrets or {})
                if mask_secrets
                else SpeechProviderConfigProcessor._decrypt_secrets(doc.provider, doc.secrets or {})
            ),
            "status": doc.status,
            "timestamp": doc.timestamp.isoformat() if doc.timestamp else None,
        }
        return raw

    @classmethod
    def save(
            cls,
            provider: str,
            scope: str,
            bot_id: Optional[str] = None,
            metadata: Optional[dict] = None,
            secrets: Optional[dict] = None,
            user: str = "system",
    ) -> str:
        """Upsert a provider config document. Returns the document id string."""
        from kairon.shared.voice.data_objects import SpeechProviderConfig

        if scope not in ("global", "bot"):
            raise AppException("scope must be 'global' or 'bot'")
        if scope == "bot" and not bot_id:
            raise AppException("bot_id is required for scope='bot'")

        secrets_enc = cls._encrypt_secrets(provider, secrets or {})

        filter_args = {"provider": provider, "scope": scope, "bot_id": bot_id}
        doc = SpeechProviderConfig.objects(**filter_args).first()
        if not doc:
            doc = SpeechProviderConfig(provider=provider, scope=scope, bot_id=bot_id)

        doc.user = user
        if metadata is not None:
            doc.metadata = metadata
        if secrets:
            doc.secrets = secrets_enc
        doc.status = True
        doc.save()
        return str(doc.id)

    @classmethod
    def get(cls, doc_id: str, mask_secrets: bool = True) -> dict:
        """Return one provider config document. Secrets are masked by default."""
        from kairon.shared.voice.data_objects import SpeechProviderConfig

        doc = SpeechProviderConfig.objects(id=doc_id).first()
        if not doc:
            raise AppException(f"Voice provider config '{doc_id}' not found")
        return cls._to_dict(doc, mask_secrets)

    @classmethod
    def list(
            cls,
            scope: Optional[str] = None,
            bot_id: Optional[str] = None,
            provider: Optional[str] = None,
            mask_secrets: bool = True,
    ) -> List[dict]:
        """List provider config documents, optionally filtered. Secrets always masked."""
        from kairon.shared.voice.data_objects import SpeechProviderConfig

        filters = {"status": True}
        if scope:
            filters["scope"] = scope
        if bot_id is not None:
            filters["bot_id"] = bot_id
        if provider:
            filters["provider"] = provider

        docs = SpeechProviderConfig.objects(**filters)
        return [cls._to_dict(doc, mask_secrets=True) for doc in docs]

    @classmethod
    def delete(cls, doc_id: str) -> None:
        """Soft-delete a provider config document (sets status=False)."""
        from kairon.shared.voice.data_objects import SpeechProviderConfig

        updated = SpeechProviderConfig.objects(id=doc_id).update_one(set__status=False)
        if not updated:
            raise AppException(f"Voice provider config '{doc_id}' not found")

    @classmethod
    def list_available(
            cls,
            bot_id: str,
            provider: Optional[str] = None,
    ) -> List[dict]:
        """Return all active provider configs visible to a bot: bot-scoped + global.

        Bot-scoped entries for the same provider appear alongside global ones —
        the caller (or the UI) can use scope/bot_id fields to distinguish them.
        Secrets are always masked.
        """
        from kairon.shared.voice.data_objects import SpeechProviderConfig

        raw_filter: dict = {
            "$or": [
                {"scope": "global", "bot_id": None},
                {"scope": "bot", "bot_id": bot_id},
            ]
        }
        if provider:
            raw_filter["provider"] = provider
        docs = SpeechProviderConfig.objects(status=True, __raw__=raw_filter)
        return [cls._to_dict(doc, mask_secrets=True) for doc in docs]

    @classmethod
    def resolve(cls, bot: str, providers: List[str]) -> dict:
        """Resolve provider configurations for a list of providers in ONE MongoDB query.

        Returns a dict keyed by provider name:
            {
              "sarvam": {"metadata": {...}, "secrets": {decrypted}},
              "polly":  {"metadata": {...}, "secrets": {decrypted}},
            }

        Priority: bot-specific (scope='bot', bot_id=bot) > global (scope='global').
        Providers with no configuration in the DB return an empty entry; the adapter
        will raise a clear error when required credentials are missing.
        """
        from kairon.shared.voice.data_objects import SpeechProviderConfig

        if not providers:
            return {}

        docs = list(
            SpeechProviderConfig.objects(
                provider__in=providers,
                status=True,
                __raw__={
                    "$or": [
                        {"scope": "global", "bot_id": None},
                        {"scope": "bot", "bot_id": bot},
                    ]
                },
            ).only("provider", "scope", "bot_id", "metadata", "secrets")
        )

        resolved: dict = {}
        for doc in docs:
            entry = {
                "metadata": dict(doc.metadata or {}),
                "secrets": cls._decrypt_secrets(doc.provider, doc.secrets or {}),
            }
            # bot-specific overrides global
            if doc.provider not in resolved or doc.scope == "bot":
                resolved[doc.provider] = entry

        return resolved
