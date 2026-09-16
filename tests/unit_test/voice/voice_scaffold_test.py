import os

import pytest

from kairon.exceptions import AppException
from kairon.shared.utils import Utility


@pytest.fixture(autouse=True, scope="class")
def setup():
    os.environ["system_file"] = "./tests/testing_data/system.yaml"
    Utility.load_environment()
    Utility.load_system_metadata()


class TestVoiceProviderMetadata:

    def test_stt_tts_metadata_loaded(self):
        assert set(Utility.system_metadata["stt_providers"]).issuperset(
            {"sarvam", "aws_transcribe", "google"}
        )
        assert set(Utility.system_metadata["tts_providers"]).issuperset(
            {"polly", "sarvam"}
        )

    def test_stt_provider_has_models_and_secret_fields(self):
        sarvam = Utility.system_metadata["stt_providers"]["sarvam"]
        assert sarvam["secret_fields"] == ["api_key"]
        assert sarvam["models"]["8000"]
        assert sarvam["streaming"] is True

    def test_tts_polly_neural_default_voice(self):
        polly = Utility.system_metadata["tts_providers"]["polly"]
        assert polly["engine"] == "neural"
        assert polly["default_voice"] == "Kajal"

    def test_exotel_registered_as_voice_channel(self):
        voice_channels = Utility.system_metadata["voice_channels"]
        assert "exotel" in voice_channels
        assert "twilio" in voice_channels
        assert set(voice_channels["exotel"]["required_fields"]) == {
            "api_key", "api_token", "account_sid", "subdomain", "exophone",
        }

    def test_get_channels_includes_voice(self):
        assert "voice" in Utility.get_channels()

    def test_global_voice_config_present(self):
        voice = Utility.environment["voice"]
        assert voice["chunk"]["multiple"] == 320
        assert voice["chunk"]["min_bytes"] == 3200
        assert voice["chunk"]["max_bytes"] == 100000
        assert voice["stt"]["fallback_order"] == ["sarvam", "aws_transcribe", "google"]
        assert voice["tts"]["fallback_order"] == ["polly", "sarvam"]


class TestExotelChannelValidation:

    def _cfg(self):
        return {
            "telephony_provider": "exotel",
            "api_key": "key-123",
            "api_token": "tok-123",
            "account_sid": "acc-sid",
            "subdomain": "api.exotel.com",
            "exophone": "08047000000",
        }

    def test_secret_fields_encrypted_non_secret_plaintext(self):
        cfg = self._cfg()
        Utility.validate_voice_provider(cfg, AppException, encrypt=True)
        # secrets no longer equal the plaintext
        assert cfg["api_key"] != "key-123"
        assert cfg["api_token"] != "tok-123"
        # non-secret required fields stay as-is
        assert cfg["account_sid"] == "acc-sid"
        assert cfg["exophone"] == "08047000000"
        assert cfg["telephony_provider"] == "exotel"

    def test_missing_required_field_raises(self):
        cfg = self._cfg()
        cfg.pop("exophone")
        with pytest.raises(AppException):
            Utility.validate_voice_provider(cfg, AppException, encrypt=False)

    def test_twilio_secret_fields_from_metadata_backward_compatible(self):
        cfg = {
            "telephony_provider": "twilio",
            "account_sid": "AC-sid",
            "auth_token": "auth-tok",
            "phone_number": "+15550001111",
        }
        Utility.validate_voice_provider(cfg, AppException, encrypt=True)
        assert cfg["account_sid"] != "AC-sid"
        assert cfg["auth_token"] != "auth-tok"
        assert cfg["phone_number"] == "+15550001111"


class _DummySTT:
    pass


class _DummyTTS:
    pass


class TestSTTTTSFactories:

    def test_supported_providers_from_metadata(self):
        from kairon.shared.voice.stt.factory import STTFactory
        from kairon.shared.voice.tts.factory import TTSFactory

        assert "sarvam" in STTFactory.supported_providers()
        assert "polly" in TTSFactory.supported_providers()

    def test_unknown_provider_metadata_raises(self):
        from kairon.shared.voice.stt.factory import STTFactory
        from kairon.shared.voice.tts.factory import TTSFactory

        with pytest.raises(AppException, match="not configured in metadata"):
            STTFactory.provider_metadata("vonage")
        with pytest.raises(AppException, match="not configured in metadata"):
            TTSFactory.provider_metadata("vonage")

    def test_metadata_provider_without_adapter_raises(self):
        from kairon.shared.voice.stt.factory import STTFactory

        # 'deepgram' is declared in metadata but ships no adapter yet
        with pytest.raises(AppException, match="no adapter implementation"):
            STTFactory.get("deepgram")

    def test_builtin_adapters_available(self):
        # MVP phase registers Sarvam (STT) and Polly (TTS) built-in adapters
        from kairon.shared.voice.stt.factory import STTFactory
        from kairon.shared.voice.tts.factory import TTSFactory
        from kairon.shared.voice.stt.sarvam import SarvamSTT
        from kairon.shared.voice.tts.polly import PollyTTS

        assert STTFactory.get("sarvam") is SarvamSTT
        assert TTSFactory.get("polly") is PollyTTS

    def test_register_then_get(self):
        from kairon.shared.voice.stt.factory import STTFactory
        from kairon.shared.voice.tts.factory import TTSFactory

        STTFactory.register("sarvam", _DummySTT)
        TTSFactory.register("polly", _DummyTTS)
        assert STTFactory.get("sarvam") is _DummySTT
        assert TTSFactory.get("polly") is _DummyTTS


class TestBotVoiceSettings:

    def test_voice_integration_settings_defaults(self):
        from kairon.shared.data.data_objects import VoiceIntegrationSettings

        v = VoiceIntegrationSettings()
        assert v.stt_provider == "sarvam"
        assert v.tts_provider == "polly"
        assert v.sample_rate == 8000
        assert v.use_bot_credentials is False

    def test_bot_settings_has_voice_field(self):
        from kairon.shared.data.data_objects import BotSettings

        assert "voice" in BotSettings._fields
