"""Tests for Exotel outbound action wiring, voice secret decryption, call status and TTS voice precedence."""
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kairon.exceptions import AppException


@pytest.fixture(autouse=True, scope="module")
def _load_env():
    os.environ["system_file"] = "./tests/testing_data/system.yaml"
    from kairon.shared.utils import Utility
    Utility.load_environment()
    Utility.load_system_metadata()


EXOTEL_CHANNEL = {
    "telephony_provider": "exotel",
    "api_key": "KEY",
    "api_token": "TOKEN",
    "account_sid": "SID",
    "phone_number": "0800",
    "subdomain": "api.in.exotel.com",
    "flow_app_id": "12345",
}


def _tracker():
    tracker = MagicMock()
    tracker.sender_id = "sender"
    tracker.get_slot.return_value = "bot"
    tracker.get_intent_of_latest_message.return_value = "intent"
    tracker.latest_message = {"text": "call me"}
    tracker.current_slot_values.return_value = {}
    return tracker


def _action_config(**kwargs):
    cfg = {
        "name": "exo_call",
        "telephony_provider": "exotel",
        "to_phone_number": {"value": "+911234567890", "parameter_type": "value"},
        "response": "Calling you now.",
        "dispatch_bot_response": True,
    }
    cfg.update(kwargs)
    return cfg


class TestExotelVoiceCallAction:

    async def _run(self, channel_config, action_config=None, tracker=None):
        from rasa_sdk.executor import CollectingDispatcher
        from kairon.actions.definitions.voice_call import ActionVoiceCall

        action = ActionVoiceCall("bot", "exo_call")
        dispatcher = CollectingDispatcher()
        with patch.object(ActionVoiceCall, "retrieve_config", return_value=action_config or _action_config()), \
                patch("kairon.actions.definitions.voice_call.ChatDataProcessor.get_channel_config",
                      return_value={"config": channel_config}), \
                patch("kairon.actions.definitions.voice_call.ChannelLogs.save") as log_save, \
                patch("kairon.actions.definitions.voice_call.ActionServerLogs.save"), \
                patch("kairon.actions.definitions.voice_call.ActionUtility.trigger_action_failure_mail"), \
                patch("kairon.shared.voice.exotel.outbound.ExotelOutboundClient.connect_to_flow",
                      return_value="EXO_SID") as connect:
            result = await action.execute(dispatcher, tracker or _tracker(), {}, action_call={})
        return result, dispatcher, connect, log_save

    @pytest.mark.asyncio
    async def test_exotel_uses_flow_app_id_and_exotel_credentials(self):
        result, dispatcher, connect, log_save = await self._run(dict(EXOTEL_CHANNEL))
        connect.assert_called_once_with("+911234567890", "12345", None)
        assert result["kairon_action_response"] == "Calling you now."
        log_save.assert_called_once()

    @pytest.mark.asyncio
    async def test_exotel_client_built_from_config(self):
        from kairon.shared.voice.exotel.outbound import ExotelOutboundClient
        with patch.object(ExotelOutboundClient, "from_config", wraps=ExotelOutboundClient.from_config) as fc:
            await self._run(dict(EXOTEL_CHANNEL))
        fc.assert_called_once()
        assert fc.call_args[0][0]["api_token"] == "TOKEN"

    @pytest.mark.asyncio
    async def test_exotel_missing_flow_app_id_fails(self):
        channel = {k: v for k, v in EXOTEL_CHANNEL.items() if k != "flow_app_id"}
        result, dispatcher, connect, _ = await self._run(channel)
        connect.assert_not_called()
        assert result["kairon_action_response"] == "I have failed to place the call"

    @pytest.mark.asyncio
    async def test_exotel_slot_phone(self):
        cfg = _action_config(to_phone_number={"value": "phone_slot", "parameter_type": "slot"})
        tracker = _tracker()
        tracker.get_slot.side_effect = lambda k: "+919999999999" if k == "phone_slot" else "bot"
        _, _, connect, _ = await self._run(dict(EXOTEL_CHANNEL), cfg, tracker)
        connect.assert_called_once_with("+919999999999", "12345", None)


class TestVoiceConfigSecretDecryption:

    def _config(self, plain: dict, provider: str):
        from kairon.shared.utils import Utility
        enc = {k: Utility.encrypt_message(v) for k, v in plain.items()}
        return {"connector_type": "voice", "config": {"telephony_provider": provider, **enc}}

    def test_exotel_secret_fields_decrypted_unmasked(self):
        from kairon.shared.chat.processor import ChatDataProcessor
        cfg = self._config({"api_key": "K-12345678", "api_token": "T-12345678", "account_sid": "S-12345678"},
                           "exotel")
        cfg["config"]["phone_number"] = "0800"
        ChatDataProcessor._ChatDataProcessor__prepare_config(cfg, mask_characters=False)
        assert cfg["config"]["api_key"] == "K-12345678"
        assert cfg["config"]["api_token"] == "T-12345678"
        assert cfg["config"]["account_sid"] == "S-12345678"
        assert cfg["config"]["phone_number"] == "0800"

    def test_exotel_secret_fields_masked(self):
        from kairon.shared.chat.processor import ChatDataProcessor
        cfg = self._config({"api_key": "K-12345678", "api_token": "T-12345678", "account_sid": "S-12345678"},
                           "exotel")
        cfg["config"]["phone_number"] = "0800"
        ChatDataProcessor._ChatDataProcessor__prepare_config(cfg, mask_characters=True)
        assert cfg["config"]["api_key"] == "K-123*****"
        assert cfg["config"]["api_token"] == "T-123*****"
        assert cfg["config"]["account_sid"] == "S-123*****"
        assert cfg["config"]["phone_number"] == "0800"

    def test_twilio_unchanged(self):
        from kairon.shared.chat.processor import ChatDataProcessor
        cfg = self._config({"account_sid": "AC-12345678", "auth_token": "AU-12345678"}, "twilio")
        cfg["config"]["phone_number"] = "+1555"
        ChatDataProcessor._ChatDataProcessor__prepare_config(cfg, mask_characters=False)
        assert cfg["config"]["account_sid"] == "AC-12345678"
        assert cfg["config"]["auth_token"] == "AU-12345678"
        assert cfg["config"]["phone_number"] == "+1555"


class TestTTSVoiceFromSpeechProviderConfig:
    """Voice/speaker comes only from SpeechProviderConfig (bot, else global); never channel config or provider yml."""

    def _handler(self):
        from kairon.chat.handlers.channels.clients.voice.exotel_stream import ExotelStreamHandler
        return ExotelStreamHandler(bot="b1", provider="exotel", token="T", websocket=MagicMock())

    def _voice(self, metadata):
        h = self._handler()
        factory_cls = MagicMock()
        resolved = {"polly": {"metadata": metadata, "secrets": {}}}
        base = "kairon.chat.handlers.channels.clients.voice.exotel_stream.TTSFactory"
        with patch(f"{base}.provider_metadata",
                   return_value={"engine": "neural", "voices": {"en-IN": "YmlVoice"}, "default_voice": "YmlDefault"}), \
                patch(f"{base}.get", return_value=factory_cls):
            h._tts_builder("polly", "en-IN", 8000, resolved)()
        return factory_cls.call_args.kwargs["voice"]

    def test_voice_from_spc(self):
        assert self._voice({"voice": "SpeechCfg"}) == "SpeechCfg"

    def test_legacy_speaker_and_default_voice_keys_ignored(self):
        assert self._voice({"speaker": "arjun", "default_voice": "Old"}) is None

    def test_provider_yml_voice_ignored(self):
        assert self._voice({}) is None

    def test_channel_tts_voice_ignored(self):
        h = self._handler()
        resolved = {"polly": {"metadata": {"voice": "SpeechCfg"}, "secrets": {}}}
        with patch.object(h, "_tts_builder", return_value=lambda: MagicMock()):
            _, provider, lang, voice = h._build_tts(
                {"language": "hi-IN", "tts_voice": "FromChannel", "voice": "Legacy"}, 8000, resolved, ["polly"]
            )
        assert (provider, lang, voice) == ("polly", "hi-IN", "SpeechCfg")

    def test_build_tts_voice_none_when_no_spc_entry(self):
        h = self._handler()
        with patch.object(h, "_tts_builder", return_value=lambda: MagicMock()):
            _, _, _, voice = h._build_tts({}, 8000, {}, ["polly"])
        assert voice is None


class TestVoiceChannelSaveFetchRoundTrip:
    """Save (validate_channel encrypts) then fetch (__prepare_config decrypts/masks) for both providers."""

    def _roundtrip(self, config: dict, mask: bool):
        from kairon.shared.utils import Utility
        from kairon.shared.chat.processor import ChatDataProcessor
        stored = dict(config)
        Utility.validate_channel("voice", stored, AppException)
        saved = dict(stored)
        doc = {"connector_type": "voice", "config": stored}
        ChatDataProcessor._ChatDataProcessor__prepare_config(doc, mask_characters=mask)
        return saved, doc["config"]

    def test_twilio_roundtrip_unmasked_same_as_input(self):
        plain = {"telephony_provider": "twilio", "account_sid": "AC1234567890", "auth_token": "TOK1234567890",
                 "phone_number": "+15550001111"}
        saved, fetched = self._roundtrip(plain, mask=False)
        assert saved["account_sid"] != plain["account_sid"] and saved["auth_token"] != plain["auth_token"]
        assert saved["phone_number"] == plain["phone_number"]
        assert fetched == plain

    def test_twilio_roundtrip_masked(self):
        plain = {"telephony_provider": "twilio", "account_sid": "AC1234567890", "auth_token": "TOK1234567890",
                 "phone_number": "+15550001111"}
        _, fetched = self._roundtrip(plain, mask=True)
        assert fetched["account_sid"] == "AC12345*****"
        assert fetched["auth_token"] == "TOK12345*****"
        assert fetched["phone_number"] == "+15550001111"

    def test_twilio_default_provider_when_not_specified(self):
        plain = {"account_sid": "AC1234567890", "auth_token": "TOK1234567890", "phone_number": "+1555"}
        _, fetched = self._roundtrip(plain, mask=False)
        assert fetched["telephony_provider"] == "twilio"
        assert fetched["auth_token"] == "TOK1234567890"

    def test_exotel_roundtrip_unmasked_same_as_input(self):
        plain = {"telephony_provider": "exotel", "api_key": "KEY1234567890", "api_token": "TOKEN1234567890",
                 "account_sid": "SID1234567890", "phone_number": "08000000000", "flow_app_id": "999"}
        saved, fetched = self._roundtrip(plain, mask=False)
        for secret in ("api_key", "api_token", "account_sid"):
            assert saved[secret] != plain[secret]
        assert saved["phone_number"] == plain["phone_number"]
        for key, value in plain.items():
            assert fetched[key] == value


class TestSarvamCurrentModels:
    """Sarvam retired saarika:v2 / bulbul:v2: defaults must be current and SPC stt_model/tts_model must win."""

    def test_stt_default_model_is_current(self):
        from kairon.shared.voice.stt.sarvam import SarvamSTT
        assert SarvamSTT({"api_key": "k"}, "hi-IN", 8000).model == "saaras:v4"

    def test_stt_model_key_from_speech_config_is_used(self):
        from kairon.shared.voice.stt.sarvam import SarvamSTT
        assert SarvamSTT({"api_key": "k", "stt_model": "custom:model"}, "hi-IN", 8000).model == "custom:model"

    def test_stt_ignores_the_generic_model_key_the_provider_registry_supplies(self):
        """metadata/stt_providers.yml hands every provider a per-rate ``model``; for Sarvam it is a retired one."""
        from kairon.shared.voice.stt.sarvam import SarvamSTT
        assert SarvamSTT({"api_key": "k", "model": "saarika:v2"}, "hi-IN", 8000).model == "saaras:v4"

    def test_tts_defaults_are_current(self):
        from kairon.shared.voice.tts.sarvam import SarvamTTS
        tts = SarvamTTS({"api_key": "k"})
        assert tts.model == "bulbul:v3"
        assert tts.speaker == "shubh"

    def test_tts_model_from_speech_config(self):
        from kairon.shared.voice.tts.sarvam import SarvamTTS
        assert SarvamTTS({"api_key": "k", "tts_model": "bulbul:v3"}, voice="priya").speaker == "priya"

    def test_parse_realtime_partial_and_final(self):
        from kairon.shared.voice.stt.sarvam import SarvamSTT
        part = SarvamSTT._parse_result('{"event":"transcript.partial","utterance_idx":0,"text":"नमस्ते"}')
        fin = SarvamSTT._parse_result('{"event":"transcript.final","utterance_idx":0,"text":"नमस्ते, मदद चाहिए।"}')
        assert (part.text, part.is_final) == ("नमस्ते", False)
        assert (fin.text, fin.is_final) == ("नमस्ते, मदद चाहिए।", True)

    @pytest.mark.parametrize("raw", [
        '{"event":"session.begin","request_id":"r"}', '{"event":"vad.speech_start","utterance_idx":0}',
        '{"event":"vad.speech_end","utterance_idx":0}', '{"event":"pong"}',
        '{"event":"session.end","total_duration_s":1}', '{"event":"error","code":"x","is_fatal":false,"message":"m"}'])
    def test_parse_realtime_non_transcript_events_ignored(self, raw):
        from kairon.shared.voice.stt.sarvam import SarvamSTT
        assert SarvamSTT._parse_result(raw) is None


class TestResolverStreamUrl:
    """Resolver wss URL carries only CallSid/Direction; sample rate comes from the start frame, not the URL."""

    def _wss(self, config):
        from urllib.parse import urlparse, parse_qs
        from kairon.chat.handlers.channels.clients.voice.exotel import ExotelVoiceProvider
        from kairon.shared.utils import Utility
        agent = {"model": {"agent": {"url": "https://chat.example.com"}}}
        with patch("kairon.shared.auth.Authentication.generate_integration_token", return_value=("TOK", None)), \
                patch.dict(Utility.environment, agent):
            url = ExotelVoiceProvider("b1", config).build_resolver_response(
                {"CallSid": "CS1", "From": "+91", "To": "080", "Direction": "outbound-dial", "junk": "x"}, "b1", "u")["url"]
        return url, parse_qs(urlparse(url).query)

    @pytest.mark.parametrize("config", [{}, {"sample_rate": 16000}, {"sample_rate": "abc"}])
    def test_only_call_sid_and_direction(self, config):
        url, q = self._wss(config)
        assert url.startswith("wss://")
        assert q == {"CallSid": ["CS1"], "Direction": ["outbound-dial"]}


class TestExotelSampleRateDefaultOnSave:
    """Saving an exotel voice channel defaults sample_rate to 8000 and rejects unsupported values."""

    def _save(self, **extra):
        from kairon.shared.utils import Utility
        cfg = {"telephony_provider": "exotel", "api_key": "K", "api_token": "T", "account_sid": "S",
               "phone_number": "0800", **extra}
        Utility.validate_channel("voice", cfg, AppException)
        return cfg

    def test_defaults_to_8000_when_missing(self):
        assert self._save()["sample_rate"] == 8000

    def test_defaults_to_8000_when_blank(self):
        assert self._save(sample_rate="")["sample_rate"] == 8000

    @pytest.mark.parametrize("value,expected", [(8000, 8000), (16000, 16000), ("16000", 16000)])
    def test_supported_values_kept_as_int(self, value, expected):
        assert self._save(sample_rate=value)["sample_rate"] == expected

    @pytest.mark.parametrize("value", [24000, 44100, "abc", 0])
    def test_unsupported_values_rejected(self, value):
        with pytest.raises(AppException, match="Unsupported sample_rate"):
            self._save(sample_rate=value)

    def test_twilio_gets_no_sample_rate(self):
        from kairon.shared.utils import Utility
        cfg = {"telephony_provider": "twilio", "account_sid": "AC", "auth_token": "T", "phone_number": "+1"}
        Utility.validate_channel("voice", cfg, AppException)
        assert "sample_rate" not in cfg

    def test_default_survives_roundtrip_fetch(self):
        from kairon.shared.chat.processor import ChatDataProcessor
        cfg = self._save()
        doc = {"connector_type": "voice", "config": dict(cfg)}
        ChatDataProcessor._ChatDataProcessor__prepare_config(doc, mask_characters=False)
        assert doc["config"]["sample_rate"] == 8000


class TestExotelSpeechProviderDefaultsOnSave:
    """Saving an exotel voice channel defaults stt_provider/tts_provider to sarvam and validates given values."""

    def _save(self, **extra):
        from kairon.shared.utils import Utility
        cfg = {"telephony_provider": "exotel", "api_key": "K", "api_token": "T", "account_sid": "S",
               "phone_number": "0800", **extra}
        Utility.validate_channel("voice", cfg, AppException)
        return cfg

    def test_both_default_to_sarvam_when_missing(self):
        cfg = self._save()
        assert (cfg["stt_provider"], cfg["tts_provider"]) == ("sarvam", "sarvam")

    def test_blank_values_default_to_sarvam(self):
        cfg = self._save(stt_provider="", tts_provider=None)
        assert (cfg["stt_provider"], cfg["tts_provider"]) == ("sarvam", "sarvam")

    def test_explicit_valid_providers_kept(self):
        cfg = self._save(stt_provider="deepgram", tts_provider="polly")
        assert (cfg["stt_provider"], cfg["tts_provider"]) == ("deepgram", "polly")

    def test_only_missing_one_is_defaulted(self):
        cfg = self._save(tts_provider="polly")
        assert (cfg["stt_provider"], cfg["tts_provider"]) == ("sarvam", "polly")

    @pytest.mark.parametrize("field", ["stt_provider", "tts_provider"])
    def test_unknown_provider_rejected(self, field):
        with pytest.raises(AppException, match=f"Unsupported {field}"):
            self._save(**{field: "nonexistent_vendor"})

    def test_twilio_gets_no_speech_provider_defaults(self):
        from kairon.shared.utils import Utility
        cfg = {"telephony_provider": "twilio", "account_sid": "AC", "auth_token": "T", "phone_number": "+1"}
        Utility.validate_channel("voice", cfg, AppException)
        assert "stt_provider" not in cfg and "tts_provider" not in cfg

    def test_runtime_tts_fallback_default_is_sarvam(self):
        from kairon.chat.handlers.channels.clients.voice.exotel_stream import ExotelStreamHandler
        h = ExotelStreamHandler(bot="b1", provider="exotel", token="T", websocket=MagicMock())
        with patch.object(h, "_voice_env", return_value={}):
            assert h._provider_chain({}, "tts", "sarvam")[0] == "sarvam"


class TestSarvamSTTRates:
    """Sarvam realtime STT takes 8000/16000; other call rates (24 kHz) are downsampled to 16000."""

    @pytest.mark.parametrize("rate,stream", [(8000, 8000), (16000, 16000), (24000, 16000)])
    @pytest.mark.asyncio
    async def test_open_url_uses_native_stream_rate(self, rate, stream):
        from kairon.shared.voice.stt.sarvam import SarvamSTT
        stt = SarvamSTT({"api_key": "k"}, "hi-IN", rate)
        fake_ws = MagicMock()
        fake_ws.__aiter__ = MagicMock(return_value=iter([]))
        with patch("websockets.connect", new_callable=AsyncMock, return_value=fake_ws) as conn:
            await stt.open()
        assert f"sample_rate={stream}" in conn.call_args.args[0]
        assert stt.sample_rate == rate and stt.stream_rate == stream
        stt._receiver_task.cancel()

    @pytest.mark.asyncio
    async def test_push_downsamples_24k_to_16k(self):
        import base64
        import json
        from kairon.shared.voice.stt.sarvam import SarvamSTT
        stt = SarvamSTT({"api_key": "k"}, "hi-IN", 24000)
        stt._ws = MagicMock()
        stt._ws.send = AsyncMock()
        pcm = b"\x10\x20" * 2400
        await stt.push(pcm)
        sent = base64.b64decode(json.loads(stt._ws.send.call_args.args[0])["audio"])
        assert abs(len(sent) - 3200) <= 8

    @pytest.mark.parametrize("rate", [8000, 16000])
    @pytest.mark.asyncio
    async def test_push_native_rates_pass_through(self, rate):
        import base64
        import json
        from kairon.shared.voice.stt.sarvam import SarvamSTT
        stt = SarvamSTT({"api_key": "k"}, "hi-IN", rate)
        stt._ws = MagicMock()
        stt._ws.send = AsyncMock()
        pcm = b"\x01\x02" * 160
        await stt.push(pcm)
        assert base64.b64decode(json.loads(stt._ws.send.call_args.args[0])["audio"]) == pcm

    @pytest.mark.asyncio
    async def test_push_skips_chunk_that_downsamples_to_nothing(self):
        from kairon.shared.voice.stt.sarvam import SarvamSTT
        stt = SarvamSTT({"api_key": "k"}, "hi-IN", 24000)
        stt._ws = MagicMock()
        stt._ws.send = AsyncMock()
        with patch("kairon.shared.voice.stt.sarvam.audioop.ratecv", return_value=(b"", None)):
            await stt.push(b"\x01\x02")
        stt._ws.send.assert_not_awaited()


class TestVoiceCallGuard:
    """A caller already on a voice call can never place another outbound call (prevents call chains)."""

    def _voice_tracker(self, via="input_channel", channel="voice"):
        tracker = _tracker()
        if via == "input_channel":
            tracker.get_latest_input_channel.return_value = channel
        else:
            tracker.get_latest_input_channel.side_effect = Exception("no channel")
            tracker.latest_message = {"text": "call me", "metadata": {"channel_type": channel}}
        return tracker

    async def _run(self, tracker, channel_config=None):
        from rasa_sdk.executor import CollectingDispatcher
        from kairon.actions.definitions.voice_call import ActionVoiceCall
        dispatcher = CollectingDispatcher()
        with patch.object(ActionVoiceCall, "retrieve_config", return_value=_action_config()) as retrieve, \
                patch("kairon.actions.definitions.voice_call.ChatDataProcessor.get_channel_config",
                      return_value={"config": channel_config or dict(EXOTEL_CHANNEL)}) as get_cfg, \
                patch("kairon.actions.definitions.voice_call.ChannelLogs.save") as log_save, \
                patch("kairon.actions.definitions.voice_call.ActionServerLogs") as asl, \
                patch("kairon.actions.definitions.voice_call.ActionUtility.trigger_action_failure_mail") as mail, \
                patch("kairon.shared.voice.exotel.outbound.ExotelOutboundClient.connect_to_flow",
                      return_value="SID") as connect:
            result = await ActionVoiceCall("bot", "exo_call").execute(dispatcher, tracker, {}, action_call={})
        return result, dispatcher, connect, retrieve, get_cfg, log_save, asl, mail

    @pytest.mark.asyncio
    @pytest.mark.parametrize("via", ["input_channel", "metadata"])
    async def test_voice_conversation_never_dials(self, via):
        from kairon.actions.definitions.voice_call import ALREADY_ON_CALL_RESPONSE
        result, dispatcher, connect, retrieve, get_cfg, log_save, asl, mail = await self._run(self._voice_tracker(via))
        connect.assert_not_called()
        log_save.assert_not_called()
        retrieve.assert_not_called()
        get_cfg.assert_not_called()
        mail.assert_not_called()
        assert result["kairon_action_response"] == ALREADY_ON_CALL_RESPONSE
        assert [m["text"] for m in dispatcher.messages] == [ALREADY_ON_CALL_RESPONSE]

    @pytest.mark.asyncio
    async def test_refusal_is_logged_as_success_with_message(self):
        from kairon.actions.definitions.voice_call import ALREADY_ON_CALL_RESPONSE
        _, _, _, _, _, _, asl, _ = await self._run(self._voice_tracker())
        kwargs = asl.call_args.kwargs
        from kairon.shared.data.constant import STATUSES
        assert kwargs["status"] == STATUSES.SUCCESS.value and kwargs["exception"] is None
        assert kwargs["bot_response"] == ALREADY_ON_CALL_RESPONSE
        asl.return_value.save.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("channel", ["chat", "whatsapp", "slack"])
    async def test_other_channels_still_place_the_call(self, channel):
        tracker = _tracker()
        tracker.get_latest_input_channel.return_value = channel
        result, _, connect, *_ = await self._run(tracker)
        connect.assert_called_once_with("+911234567890", "12345", None)
        assert result["kairon_action_response"] == "Calling you now."

    @pytest.mark.asyncio
    async def test_unknown_channel_still_places_the_call(self):
        tracker = _tracker()
        result, _, connect, *_ = await self._run(tracker)
        connect.assert_called_once()


class TestExotelCallSidParsing:

    def test_non_dict_call_value_yields_empty_sid(self):
        from kairon.shared.voice.exotel.outbound import ExotelOutboundClient
        assert ExotelOutboundClient._parse_call_sid({"Call": "unexpected"}) == ""
