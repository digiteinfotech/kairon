"""Unit tests for SpeechProviderConfig (MongoEngine model) and

SpeechProviderConfigProcessor (CRUD + single-query resolve).
"""
import os

import pytest
from mongoengine import connect, disconnect  # noqa: F401

from kairon.exceptions import AppException
from kairon.shared.utils import Utility


@pytest.fixture(autouse=True, scope="module")
def setup():
    os.environ["system_file"] = "./tests/testing_data/system.yaml"
    Utility.load_environment()
    Utility.load_system_metadata()
    connect(**Utility.mongoengine_connection(Utility.environment["database"]["url"]))
    yield
    disconnect()


class TestSpeechProviderConfig:

    def test_model_requires_provider(self):
        from kairon.shared.voice.data_objects import SpeechProviderConfig
        from mongoengine.errors import ValidationError

        doc = SpeechProviderConfig(scope="global")
        with pytest.raises(ValidationError):
            doc.validate()

    def test_model_requires_bot_id_for_bot_scope(self):
        from kairon.shared.voice.data_objects import SpeechProviderConfig
        from mongoengine.errors import ValidationError

        doc = SpeechProviderConfig(provider="sarvam", scope="bot", bot_id=None)
        with pytest.raises(ValidationError, match="bot_id is required"):
            doc.validate()

    def test_model_global_scope_no_bot_id_valid(self):
        from kairon.shared.voice.data_objects import SpeechProviderConfig

        doc = SpeechProviderConfig(provider="sarvam", scope="global")
        doc.validate()  # must not raise


class TestSpeechProviderConfigProcessorCrud:

    def test_save_global_returns_id(self):
        from kairon.shared.voice.processor import SpeechProviderConfigProcessor

        doc_id = SpeechProviderConfigProcessor.save(
            provider="sarvam",
            scope="global",
            metadata={"stt_url": "https://api.sarvam.ai/speech-to-text"},
            secrets={"api_key": "plain-key"},
        )
        assert doc_id and isinstance(doc_id, str)

    def test_get_masks_secrets(self):
        from kairon.shared.voice.processor import SpeechProviderConfigProcessor

        doc_id = SpeechProviderConfigProcessor.save(
            provider="polly",
            scope="global",
            secrets={"aws_access_key_id": "AKID", "aws_secret_access_key": "secret"},
        )
        result = SpeechProviderConfigProcessor.get(doc_id, mask_secrets=True)
        assert result["secrets"]["aws_access_key_id"] == "**********"
        assert result["secrets"]["aws_secret_access_key"] == "**********"
        assert result["provider"] == "polly"
        assert result["scope"] == "global"

    def test_get_not_found_raises(self):
        from kairon.shared.voice.processor import SpeechProviderConfigProcessor

        with pytest.raises(AppException, match="not found"):
            SpeechProviderConfigProcessor.get("000000000000000000000000")

    def test_save_upserts_existing(self):
        from kairon.shared.voice.processor import SpeechProviderConfigProcessor
        from kairon.shared.voice.data_objects import SpeechProviderConfig

        id1 = SpeechProviderConfigProcessor.save(
            provider="elevenlabs", scope="global", metadata={"v": 1}
        )
        id2 = SpeechProviderConfigProcessor.save(
            provider="elevenlabs", scope="global", metadata={"v": 2}
        )
        assert id1 == id2  # same document updated
        doc = SpeechProviderConfig.objects(id=id1).first()
        assert doc.metadata["v"] == 2

    def test_save_invalid_scope_raises(self):
        from kairon.shared.voice.processor import SpeechProviderConfigProcessor

        with pytest.raises(AppException, match="scope must be"):
            SpeechProviderConfigProcessor.save(provider="sarvam", scope="invalid")

    def test_save_bot_scope_missing_bot_id_raises(self):
        from kairon.shared.voice.processor import SpeechProviderConfigProcessor

        with pytest.raises(AppException, match="bot_id is required"):
            SpeechProviderConfigProcessor.save(provider="sarvam", scope="bot")

    def test_list_filters_by_scope(self):
        from kairon.shared.voice.processor import SpeechProviderConfigProcessor

        SpeechProviderConfigProcessor.save(
            provider="sarvam", scope="bot", bot_id="bot-list-test",
            secrets={"api_key": "botkey"},
        )
        bot_configs = SpeechProviderConfigProcessor.list(scope="bot", bot_id="bot-list-test")
        assert any(c["provider"] == "sarvam" and c["scope"] == "bot" for c in bot_configs)

    def test_delete_soft_deletes(self):
        from kairon.shared.voice.processor import SpeechProviderConfigProcessor
        from kairon.shared.voice.data_objects import SpeechProviderConfig

        doc_id = SpeechProviderConfigProcessor.save(
            provider="google", scope="global", metadata={"url": "x"}
        )
        SpeechProviderConfigProcessor.delete(doc_id)
        doc = SpeechProviderConfig.objects(id=doc_id).first()
        assert doc.status is False

    def test_delete_not_found_raises(self):
        from kairon.shared.voice.processor import SpeechProviderConfigProcessor

        with pytest.raises(AppException, match="not found"):
            SpeechProviderConfigProcessor.delete("000000000000000000000000")

    def test_list_available_returns_global_and_bot_scoped(self):
        from kairon.shared.voice.processor import SpeechProviderConfigProcessor

        bot = "list-avail-bot"
        SpeechProviderConfigProcessor.save(
            provider="sarvam-avail", scope="global",
            metadata={"url": "https://sarvam.ai"}, secrets={"api_key": "gkey"},
        )
        SpeechProviderConfigProcessor.save(
            provider="sarvam-avail", scope="bot", bot_id=bot,
            secrets={"api_key": "bkey"},
        )
        SpeechProviderConfigProcessor.save(
            provider="polly-avail", scope="global", secrets={"aws_access_key_id": "AK"},
        )

        results = SpeechProviderConfigProcessor.list_available(bot_id=bot)
        providers_returned = [(r["provider"], r["scope"]) for r in results]
        assert ("sarvam-avail", "global") in providers_returned
        assert ("sarvam-avail", "bot") in providers_returned
        assert ("polly-avail", "global") in providers_returned
        for r in results:
            for v in r["secrets"].values():
                assert v == "**********" or v == ""

    def test_list_available_filters_by_provider(self):
        from kairon.shared.voice.processor import SpeechProviderConfigProcessor

        bot = "list-avail-filter-bot"
        SpeechProviderConfigProcessor.save(provider="filter-stt", scope="global")
        SpeechProviderConfigProcessor.save(provider="filter-tts", scope="global")

        results = SpeechProviderConfigProcessor.list_available(bot_id=bot, provider="filter-stt")
        assert all(r["provider"] == "filter-stt" for r in results)

    def test_list_available_excludes_other_bot_scoped(self):
        from kairon.shared.voice.processor import SpeechProviderConfigProcessor

        SpeechProviderConfigProcessor.save(
            provider="excl-provider", scope="bot", bot_id="other-bot", secrets={"api_key": "x"},
        )
        results = SpeechProviderConfigProcessor.list_available(bot_id="query-bot")
        assert not any(
            r["provider"] == "excl-provider" and r["scope"] == "bot" for r in results
        )


class TestSpeechProviderConfigProcessorResolve:

    def test_resolve_single_query_returns_global(self):
        from kairon.shared.voice.processor import SpeechProviderConfigProcessor

        SpeechProviderConfigProcessor.save(
            provider="sarvam",
            scope="global",
            metadata={"url": "https://sarvam.ai"},
            secrets={"api_key": "global-key"},
        )
        result = SpeechProviderConfigProcessor.resolve("any-bot", ["sarvam"])
        assert "sarvam" in result
        assert result["sarvam"]["metadata"]["url"] == "https://sarvam.ai"
        # secrets must be decrypted (not the raw encrypted value)
        assert result["sarvam"]["secrets"]["api_key"] == "global-key"

    def test_resolve_bot_specific_overrides_global(self):
        from kairon.shared.voice.processor import SpeechProviderConfigProcessor

        SpeechProviderConfigProcessor.save(
            provider="sarvam", scope="global", secrets={"api_key": "global-key"}
        )
        SpeechProviderConfigProcessor.save(
            provider="sarvam", scope="bot", bot_id="byok-bot", secrets={"api_key": "bot-key"}
        )
        result = SpeechProviderConfigProcessor.resolve("byok-bot", ["sarvam"])
        assert result["sarvam"]["secrets"]["api_key"] == "bot-key"

    def test_resolve_falls_back_to_global_when_no_bot_config(self):
        from kairon.shared.voice.processor import SpeechProviderConfigProcessor

        SpeechProviderConfigProcessor.save(
            provider="sarvam", scope="global", secrets={"api_key": "global-key"}
        )
        result = SpeechProviderConfigProcessor.resolve("bot-with-no-byok", ["sarvam"])
        assert result["sarvam"]["secrets"]["api_key"] == "global-key"

    def test_resolve_multiple_providers_single_query(self):
        from kairon.shared.voice.processor import SpeechProviderConfigProcessor

        SpeechProviderConfigProcessor.save(
            provider="sarvam", scope="global", secrets={"api_key": "s-key"}
        )
        SpeechProviderConfigProcessor.save(
            provider="polly", scope="global",
            secrets={"aws_access_key_id": "AK", "aws_secret_access_key": "SK"},
        )
        result = SpeechProviderConfigProcessor.resolve("any-bot", ["sarvam", "polly"])
        assert "sarvam" in result
        assert "polly" in result
        assert result["sarvam"]["secrets"]["api_key"] == "s-key"
        assert result["polly"]["secrets"]["aws_access_key_id"] == "AK"

    def test_resolve_missing_provider_returns_empty_entry_not_raises(self):
        from kairon.shared.voice.processor import SpeechProviderConfigProcessor

        result = SpeechProviderConfigProcessor.resolve("any-bot", ["nonexistent-provider"])
        assert "nonexistent-provider" not in result

    def test_resolve_empty_list_returns_empty(self):
        from kairon.shared.voice.processor import SpeechProviderConfigProcessor

        result = SpeechProviderConfigProcessor.resolve("any-bot", [])
        assert result == {}


class TestSpeechProviderConfigDecryptConfig:

    def test_decrypts_only_secret_fields(self):
        from kairon.shared.voice.processor import SpeechProviderConfigProcessor

        out = SpeechProviderConfigProcessor.decrypt_config(
            {"api_key": "ENC", "region": "ap-south-1"},
            ["api_key"],
            decryptor=lambda v: f"dec({v})",
        )
        assert out["api_key"] == "dec(ENC)"
        assert out["region"] == "ap-south-1"

    def test_leaves_value_on_decryption_failure(self):
        from kairon.shared.voice.processor import SpeechProviderConfigProcessor

        def boom(_):
            raise ValueError("bad token")

        out = SpeechProviderConfigProcessor.decrypt_config(
            {"api_key": "plain"}, ["api_key"], decryptor=boom
        )
        assert out["api_key"] == "plain"

    def test_empty_config_returns_empty(self):
        from kairon.shared.voice.processor import SpeechProviderConfigProcessor

        assert SpeechProviderConfigProcessor.decrypt_config({}, ["api_key"]) == {}
