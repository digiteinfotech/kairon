"""Tests for ExotelStreamHandler, ExotelVoiceProvider, SarvamSTT, SarvamTTS, PollyTTS."""
import asyncio
import base64
import io
import json
import os
import wave
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kairon.exceptions import AppException


@pytest.fixture(autouse=True, scope="module")
def _load_env():
    """Load system.yaml so Utility.environment is populated before any import of AgentProcessor."""
    os.environ["system_file"] = "./tests/testing_data/system.yaml"
    from kairon.shared.utils import Utility
    Utility.load_environment()
    Utility.load_system_metadata()


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _make_wav(num_frames: int = 160, rate: int = 8000, channels: int = 1, width: int = 2) -> bytes:
    """Return minimal WAV bytes with sine-ish PCM data."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(b"\x10\x20" * num_frames)
    return buf.getvalue()


# ──────────────────────────────────────────────────────────────────────────────
# ExotelVoiceProvider
# ──────────────────────────────────────────────────────────────────────────────

class TestExotelVoiceProvider:

    def _provider(self, config=None):
        from kairon.chat.handlers.channels.clients.voice.exotel import ExotelVoiceProvider
        return ExotelVoiceProvider(bot="b1", config=config or {})

    def test_is_streaming(self):
        assert self._provider().is_streaming() is True

    def test_supports_dynamic_resolver(self):
        from kairon.chat.handlers.channels.clients.voice.exotel import ExotelVoiceProvider
        assert ExotelVoiceProvider.supports_dynamic_resolver() is True

    def test_validate_signature_always_true(self):
        p = self._provider()
        assert p.validate_signature(MagicMock(), "http://url", {}) is True

    def test_build_hangup_response(self):
        xml = self._provider().build_hangup_response([])
        assert "<Hangup" in xml and xml.startswith("<?xml")

    def test_build_voice_response_uses_config_stream_url(self):
        p = self._provider(config={"stream_url": "wss://stream.example.com/ws"})
        xml = p.build_voice_response([], "https://unused.example.com/call/tok")
        assert "wss://stream.example.com/ws" in xml
        assert "<Stream" in xml

    def test_build_voice_response_derives_stream_url(self):
        from kairon.chat.handlers.channels.clients.voice.exotel import _derive_stream_url
        p = self._provider()
        call_url = "https://chat.example.com/api/bot/b1/channel/voice/exotel/call/TOKEN123"
        xml = p.build_voice_response([], call_url)
        expected_wss = _derive_stream_url(call_url)
        assert expected_wss in xml

    def test_derive_stream_url_converts_scheme_and_path(self):
        from kairon.chat.handlers.channels.clients.voice.exotel import _derive_stream_url
        url = _derive_stream_url("https://host.com/api/bot/b1/channel/voice/exotel/call/TOK")
        assert url.startswith("wss://")
        assert "/stream/" in url and "TOK" in url

    def test_validate_config_valid(self):
        p = self._provider()
        p.validate_config({"api_key": "k", "api_token": "t", "account_sid": "s", "exophone": "e"})

    def test_validate_config_missing_field_raises(self):
        p = self._provider()
        with pytest.raises(AppException, match="api_key"):
            p.validate_config({"api_token": "t", "account_sid": "s", "exophone": "e"})

    @pytest.mark.asyncio
    async def test_handle_call_status_logs_and_saves(self):
        request = MagicMock()
        request.form = AsyncMock(return_value={
            "Status": "completed", "CallSid": "CS123"
        })
        p = self._provider(config={"user": "testuser"})
        with patch("kairon.chat.handlers.channels.clients.voice.exotel.ChannelLogs") as MockLog:
            instance = MagicMock()
            MockLog.return_value = instance
            await p.handle_call_status(request, "b1")
        MockLog.assert_called_once()
        instance.save.assert_called_once()
        call_kwargs = MockLog.call_args.kwargs
        assert call_kwargs["status"] == "completed"
        assert call_kwargs["message_id"] == "CS123"
        assert call_kwargs["bot"] == "b1"

    @pytest.mark.asyncio
    async def test_handle_call_status_missing_fields_defaults(self):
        request = MagicMock()
        request.form = AsyncMock(return_value={})
        p = self._provider()
        with patch("kairon.chat.handlers.channels.clients.voice.exotel.ChannelLogs") as MockLog:
            MockLog.return_value = MagicMock()
            await p.handle_call_status(request, "b1")
        call_kwargs = MockLog.call_args.kwargs
        assert call_kwargs["status"] == "unknown"
        assert call_kwargs["message_id"] == "unknown"

    def test_build_resolver_response_returns_url(self):
        p = self._provider()
        with patch.object(p, "_generate_stream_wss_url", return_value="wss://x/stream/TOK"):
            result = p.build_resolver_response({"CallSid": "CS1"}, "b1", "user@x")
        assert result == {"url": "wss://x/stream/TOK"}

    def test_build_greeting_response_no_wav_raises(self):
        p = self._provider(config={})
        with pytest.raises(AppException, match="greeting_wav_url"):
            p.build_greeting_response({}, "b1", "user@x")

    def test_build_greeting_response_includes_wav_url(self):
        p = self._provider(config={"greeting_wav_url": "https://cdn.example.com/hi.wav"})
        with patch.object(p, "_generate_stream_wss_url", return_value="wss://x/stream/T"):
            xml = p.build_greeting_response({}, "b1", "u")
        assert "https://cdn.example.com/hi.wav" in xml
        assert "wss://x/stream/T" in xml
        assert "<Play" in xml and "<Stream" in xml

    def test_generate_stream_wss_url_structure(self):
        p = self._provider()
        mock_token = "FAKE_JWT_TOKEN"
        # Authentication and Utility are imported locally inside the method, so patch at source
        with (
            patch("kairon.shared.auth.Authentication.generate_integration_token",
                  return_value=(mock_token, None)) as mock_gen,
            patch("kairon.shared.utils.Utility.environment",
                  new={"model": {"agent": {"url": "https://chat.example.com"}}}),
        ):
            url = p._generate_stream_wss_url("b1", "u@x", {"CallSid": "CS99", "From": "+91"})
        assert url.startswith("wss://")
        assert mock_token in url
        mock_gen.assert_called_once()


# ──────────────────────────────────────────────────────────────────────────────
# SarvamSTT
# ──────────────────────────────────────────────────────────────────────────────

class TestSarvamSTT:

    def test_missing_api_key_raises(self):
        from kairon.shared.voice.stt.sarvam import SarvamSTT
        with pytest.raises(AppException, match="api_key"):
            SarvamSTT({}, "en-IN")

    def test_init_uses_model_from_config(self):
        from kairon.shared.voice.stt.sarvam import SarvamSTT
        stt = SarvamSTT({"api_key": "k", "model": "saarika:v1"}, "hi-IN", 16000)
        assert stt.model == "saarika:v1"
        assert stt.api_key == "k"
        assert stt.sample_rate == 16000

    def test_init_default_model(self):
        from kairon.shared.voice.stt.sarvam import SarvamSTT
        stt = SarvamSTT({"api_key": "k"}, "en-IN")
        assert stt.model == SarvamSTT.DEFAULT_MODEL

    def test_push_before_open_raises(self):
        from kairon.shared.voice.stt.sarvam import SarvamSTT
        stt = SarvamSTT({"api_key": "k"}, "en-IN")

        async def _run():
            with pytest.raises(AppException, match="before open"):
                await stt.push(b"\x00" * 100)

        asyncio.get_event_loop().run_until_complete(_run())

    def test_push_empty_pcm_skips(self):
        from kairon.shared.voice.stt.sarvam import SarvamSTT
        stt = SarvamSTT({"api_key": "k"}, "en-IN")
        stt._ws = MagicMock()  # pretend open

        async def _run():
            stt._ws.send = AsyncMock()
            await stt.push(b"")
            stt._ws.send.assert_not_called()

        asyncio.get_event_loop().run_until_complete(_run())

    def test_push_encodes_pcm_as_base64_json(self):
        from kairon.shared.voice.stt.sarvam import SarvamSTT
        stt = SarvamSTT({"api_key": "k"}, "en-IN")
        stt._ws = MagicMock()

        async def _run():
            stt._ws.send = AsyncMock()
            pcm = b"\x10\x20" * 40
            await stt.push(pcm)
            stt._ws.send.assert_awaited_once()
            msg = json.loads(stt._ws.send.call_args.args[0])
            decoded = base64.b64decode(msg["audio"]["data"])
            assert decoded == pcm

        asyncio.get_event_loop().run_until_complete(_run())

    def test_close_idempotent(self):
        from kairon.shared.voice.stt.sarvam import SarvamSTT
        stt = SarvamSTT({"api_key": "k"}, "en-IN")

        async def _run():
            await stt.close()
            await stt.close()  # second call must not raise

        asyncio.get_event_loop().run_until_complete(_run())

    def test_close_cancels_task_and_socket(self):
        from kairon.shared.voice.stt.sarvam import SarvamSTT
        stt = SarvamSTT({"api_key": "k"}, "en-IN")
        fake_task = MagicMock()
        fake_ws = MagicMock()
        fake_ws.close = AsyncMock()
        stt._receiver_task = fake_task
        stt._ws = fake_ws

        async def _run():
            await stt.close()

        asyncio.get_event_loop().run_until_complete(_run())
        fake_task.cancel.assert_called_once()
        fake_ws.close.assert_awaited_once()

    def test_transcripts_yields_from_queue(self):
        from kairon.shared.voice.stt.sarvam import SarvamSTT
        from kairon.shared.voice.stt.base import Transcript
        stt = SarvamSTT({"api_key": "k"}, "en-IN")

        async def _run():
            await stt._queue.put(Transcript("hello", True))
            await stt._queue.put(None)  # sentinel
            results = [t async for t in stt.transcripts()]
            assert len(results) == 1
            assert results[0].text == "hello"

        asyncio.get_event_loop().run_until_complete(_run())

    @pytest.mark.asyncio
    async def test_open_connects_to_sarvam_wss(self):
        from kairon.shared.voice.stt.sarvam import SarvamSTT
        stt = SarvamSTT({"api_key": "mykey"}, "hi-IN", 8000)
        fake_ws = MagicMock()
        fake_ws.__aiter__ = MagicMock(return_value=iter([]))

        with patch("websockets.connect", new_callable=AsyncMock, return_value=fake_ws):
            await stt.open()

        assert stt._ws is fake_ws
        assert stt._receiver_task is not None
        stt._receiver_task.cancel()


# ──────────────────────────────────────────────────────────────────────────────
# SarvamTTS
# ──────────────────────────────────────────────────────────────────────────────

class TestSarvamTTS:

    def test_missing_api_key_raises(self):
        from kairon.shared.voice.tts.sarvam import SarvamTTS
        with pytest.raises(AppException, match="api_key"):
            SarvamTTS({})

    def test_init_resolves_fields(self):
        from kairon.shared.voice.tts.sarvam import SarvamTTS
        tts = SarvamTTS({"api_key": "k", "speaker": "arjun", "tts_model": "bulbul:v1"},
                        voice="meera", language="hi-IN", sample_rate=16000)
        assert tts.api_key == "k"
        assert tts.speaker == "arjun"  # config takes priority over voice
        assert tts.model == "bulbul:v1"
        assert tts.sample_rate == 16000
        assert tts.language == "hi-IN"

    def test_init_voice_fallback_when_no_speaker_in_config(self):
        from kairon.shared.voice.tts.sarvam import SarvamTTS
        tts = SarvamTTS({"api_key": "k"}, voice="meera")
        assert tts.speaker == "meera"

    def test_init_default_speaker(self):
        from kairon.shared.voice.tts.sarvam import SarvamTTS
        tts = SarvamTTS({"api_key": "k"})
        assert tts.speaker == SarvamTTS.DEFAULT_SPEAKER

    @pytest.mark.asyncio
    async def test_synthesize_empty_text_yields_nothing(self):
        from kairon.shared.voice.tts.sarvam import SarvamTTS
        tts = SarvamTTS({"api_key": "k"})
        chunks = [c async for c in tts.synthesize("")]
        assert chunks == []

    @pytest.mark.asyncio
    async def test_synthesize_whitespace_only_yields_nothing(self):
        from kairon.shared.voice.tts.sarvam import SarvamTTS
        tts = SarvamTTS({"api_key": "k"})
        chunks = [c async for c in tts.synthesize("   ")]
        assert chunks == []

    @pytest.mark.asyncio
    async def test_synthesize_calls_sync_and_yields_chunks(self):
        from kairon.shared.voice.tts.sarvam import SarvamTTS, _YIELD_CHUNK
        tts = SarvamTTS({"api_key": "k"})
        pcm = b"\xAA\xBB" * 1000  # 2000 bytes
        with patch.object(tts, "_synthesize_sync", return_value=pcm):
            chunks = [c async for c in tts.synthesize("hello")]
        assert b"".join(chunks) == pcm
        # each chunk is at most _YIELD_CHUNK bytes
        assert all(len(c) <= _YIELD_CHUNK for c in chunks)

    def test_synthesize_sync_http_error_raises(self):
        from kairon.shared.voice.tts.sarvam import SarvamTTS
        tts = SarvamTTS({"api_key": "k"})
        resp = MagicMock()
        resp.status_code = 401
        resp.text = "Unauthorized"
        resp.raise_for_status.side_effect = Exception("401 Unauthorized")
        with patch("requests.post", return_value=resp):
            with pytest.raises(Exception):
                tts._synthesize_sync("test")

    def test_synthesize_sync_empty_audios_returns_empty(self):
        from kairon.shared.voice.tts.sarvam import SarvamTTS
        tts = SarvamTTS({"api_key": "k"})
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"audios": []}
        with patch("requests.post", return_value=resp):
            result = tts._synthesize_sync("test")
        assert result == b""

    def test_synthesize_sync_decodes_wav(self):
        from kairon.shared.voice.tts.sarvam import SarvamTTS
        tts = SarvamTTS({"api_key": "k"}, sample_rate=8000)
        wav = _make_wav(160, 8000, 1, 2)
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"audios": [base64.b64encode(wav).decode()]}
        with patch("requests.post", return_value=resp):
            result = tts._synthesize_sync("test")
        assert isinstance(result, bytes) and len(result) > 0

    def test_wav_to_pcm_mono_passthrough(self):
        from kairon.shared.voice.tts.sarvam import _wav_to_pcm
        wav = _make_wav(160, 8000, 1, 2)
        pcm = _wav_to_pcm(wav, 8000)
        assert len(pcm) == 160 * 2  # 160 frames × 2 bytes

    def test_wav_to_pcm_stereo_to_mono(self):
        from kairon.shared.voice.tts.sarvam import _wav_to_pcm
        wav = _make_wav(160, 8000, 2, 2)
        pcm = _wav_to_pcm(wav, 8000)
        # stereo → mono: result is half the channels; just verify non-empty bytes
        assert isinstance(pcm, bytes) and len(pcm) > 0

    def test_wav_to_pcm_resamples(self):
        from kairon.shared.voice.tts.sarvam import _wav_to_pcm
        wav = _make_wav(160, 16000, 1, 2)
        pcm = _wav_to_pcm(wav, 8000)
        # resampled: 160 frames at 16kHz → ~80 frames at 8kHz
        assert len(pcm) > 0 and len(pcm) < 160 * 2


# ──────────────────────────────────────────────────────────────────────────────
# PollyTTS
# ──────────────────────────────────────────────────────────────────────────────

class TestPollyTTS:

    def test_missing_access_key_raises(self):
        from kairon.shared.voice.tts.polly import PollyTTS
        with pytest.raises(AppException, match="aws_access_key_id"):
            PollyTTS({"aws_secret_access_key": "s"})

    def test_missing_secret_key_raises(self):
        from kairon.shared.voice.tts.polly import PollyTTS
        with pytest.raises(AppException, match="aws_secret_access_key"):
            PollyTTS({"aws_access_key_id": "a"})

    def test_init_resolves_defaults(self):
        from kairon.shared.voice.tts.polly import PollyTTS
        tts = PollyTTS({"aws_access_key_id": "A", "aws_secret_access_key": "S"})
        assert tts.voice == "Kajal"
        assert tts.region == "ap-south-1"
        assert tts.engine == "neural"
        assert tts.sample_rate == 8000

    def test_init_voice_override(self):
        from kairon.shared.voice.tts.polly import PollyTTS
        tts = PollyTTS(
            {"aws_access_key_id": "A", "aws_secret_access_key": "S"},
            voice="Joanna", language="en-US", sample_rate=16000,
        )
        assert tts.voice == "Joanna"
        assert tts.sample_rate == 16000

    @pytest.mark.asyncio
    async def test_synthesize_empty_text_yields_nothing(self):
        from kairon.shared.voice.tts.polly import PollyTTS
        tts = PollyTTS({"aws_access_key_id": "A", "aws_secret_access_key": "S"})
        chunks = [c async for c in tts.synthesize("")]
        assert chunks == []

    @pytest.mark.asyncio
    async def test_synthesize_whitespace_only_yields_nothing(self):
        from kairon.shared.voice.tts.polly import PollyTTS
        tts = PollyTTS({"aws_access_key_id": "A", "aws_secret_access_key": "S"})
        chunks = [c async for c in tts.synthesize("  ")]
        assert chunks == []

    @pytest.mark.asyncio
    async def test_synthesize_calls_sync_and_chunks(self):
        from kairon.shared.voice.tts.polly import PollyTTS, _YIELD_CHUNK
        tts = PollyTTS({"aws_access_key_id": "A", "aws_secret_access_key": "S"})
        pcm = b"\x01\x02" * 1000
        with patch.object(tts, "_synthesize_sync", return_value=pcm):
            chunks = [c async for c in tts.synthesize("Hello world")]
        assert b"".join(chunks) == pcm
        assert all(len(c) <= _YIELD_CHUNK for c in chunks)

    def test_synthesize_sync_with_mock_boto3(self):
        from kairon.shared.voice.tts.polly import PollyTTS
        tts = PollyTTS({"aws_access_key_id": "A", "aws_secret_access_key": "S"})
        pcm = b"\x10\x20" * 100
        mock_stream = MagicMock()
        mock_stream.read.return_value = pcm
        mock_client = MagicMock()
        mock_client.synthesize_speech.return_value = {"AudioStream": mock_stream}
        with patch("boto3.client", return_value=mock_client):
            result = tts._synthesize_sync("test")
        assert result == pcm
        mock_client.synthesize_speech.assert_called_once_with(
            Text="test",
            OutputFormat="pcm",
            VoiceId="Kajal",
            Engine="neural",
            SampleRate="8000",
        )

    def test_synthesize_sync_no_audio_stream(self):
        from kairon.shared.voice.tts.polly import PollyTTS
        tts = PollyTTS({"aws_access_key_id": "A", "aws_secret_access_key": "S"})
        mock_client = MagicMock()
        mock_client.synthesize_speech.return_value = {}  # no AudioStream
        with patch("boto3.client", return_value=mock_client):
            result = tts._synthesize_sync("test")
        assert result == b""


# ──────────────────────────────────────────────────────────────────────────────
# ExotelStreamHandler
# ──────────────────────────────────────────────────────────────────────────────

class _FakeWebSocket:
    """Minimal WS stub for ExotelStreamHandler tests."""

    def __init__(self, messages=None):
        self._messages = list(messages or [])
        self.accepted = False
        self.closed_code = None
        self.sent = []

    async def accept(self):
        self.accepted = True

    async def close(self, code=1000):
        self.closed_code = code

    async def send_text(self, data):
        self.sent.append(data)

    async def receive_text(self):
        if self._messages:
            return self._messages.pop(0)
        from starlette.websockets import WebSocketDisconnect
        raise WebSocketDisconnect()


class TestExotelStreamHandler:

    def _handler(self, ws=None):
        from kairon.chat.handlers.channels.clients.voice.exotel_stream import ExotelStreamHandler
        ws = ws or _FakeWebSocket()
        return ExotelStreamHandler(bot="b1", provider="exotel", token="TOK", websocket=ws), ws

    def test_init_stores_fields(self):
        h, _ = self._handler()
        assert h.bot == "b1"
        assert h.provider == "exotel"
        assert h.token == "TOK"
        assert h.user is None

    @pytest.mark.asyncio
    async def test_authenticate_success(self):
        h, ws = self._handler()
        mock_user = MagicMock()
        with patch(
            "kairon.chat.handlers.channels.clients.voice.exotel_stream.Authentication"
            ".get_current_user_and_bot",
            new_callable=AsyncMock,
            return_value=mock_user,
        ):
            result = await h.authenticate()
        assert result is True
        assert h.user is mock_user

    @pytest.mark.asyncio
    async def test_authenticate_failure_closes_socket(self):
        h, ws = self._handler()
        with patch(
            "kairon.chat.handlers.channels.clients.voice.exotel_stream.Authentication"
            ".get_current_user_and_bot",
            new_callable=AsyncMock,
            side_effect=Exception("bad token"),
        ):
            result = await h.authenticate()
        assert result is False
        assert ws.closed_code == 1008

    def test_provider_chain_bot_choice_first_no_duplicates(self):
        h, _ = self._handler()
        with patch.object(h, "_voice_env", return_value={
            "stt": {"default_provider": "sarvam", "fallback_order": ["sarvam", "deepgram"]},
        }):
            chain = h._provider_chain({"stt_provider": "sarvam"}, "stt", "sarvam")
        assert chain[0] == "sarvam"
        assert chain.count("sarvam") == 1

    def test_provider_chain_fallback_when_not_configured(self):
        h, _ = self._handler()
        with patch.object(h, "_voice_env", return_value={
            "stt": {"fallback_order": ["sarvam", "deepgram"]},
        }):
            chain = h._provider_chain({}, "stt", "sarvam")
        assert "sarvam" in chain

    def test_provider_chain_default_when_empty_env(self):
        h, _ = self._handler()
        with patch.object(h, "_voice_env", return_value={}):
            chain = h._provider_chain({}, "stt", "sarvam")
        assert chain == ["sarvam"]

    def test_base_metadata(self):
        h, _ = self._handler()
        h.user = MagicMock(account=99)
        meta = h._base_metadata()
        assert meta["bot"] == "b1"
        assert meta["account"] == 99
        assert meta["is_integration_user"] is True

    def test_build_stt_returns_fallback_and_primary(self):
        from kairon.shared.voice.resilience import FallbackSTT
        h, _ = self._handler()
        with patch("kairon.chat.handlers.channels.clients.voice.exotel_stream.STTFactory"
                   ".provider_metadata", return_value={"models": {"8000": "saarika:v2"}}):
            with patch("kairon.chat.handlers.channels.clients.voice.exotel_stream.STTFactory"
                       ".get", return_value=MagicMock(return_value=MagicMock())):
                stt, primary = h._build_stt({"language": "en-IN"}, 8000, {}, ["sarvam"])
        assert isinstance(stt, FallbackSTT)
        assert primary == "sarvam"

    def test_build_tts_returns_fallback_and_primary_and_lang(self):
        from kairon.shared.voice.resilience import FallbackTTS
        h, _ = self._handler()
        with patch("kairon.chat.handlers.channels.clients.voice.exotel_stream.TTSFactory"
                   ".provider_metadata", return_value={"engine": "neural", "default_voice": "Kajal"}):
            with patch("kairon.chat.handlers.channels.clients.voice.exotel_stream.TTSFactory"
                       ".get", return_value=MagicMock(return_value=MagicMock())):
                tts, primary, lang, voice = h._build_tts({"language": "en-IN"}, 8000, {}, ["polly"])
        assert isinstance(tts, FallbackTTS)
        assert primary == "polly"
        assert lang == "en-IN"

    @pytest.mark.asyncio
    async def test_run_auth_failure_returns_early(self):
        h, ws = self._handler()
        with patch.object(h, "authenticate", new_callable=AsyncMock, return_value=False):
            await h.run()
        # websocket never accepted
        assert not ws.accepted

    @pytest.mark.asyncio
    async def test_run_missing_config_closes_1011(self):
        h, ws = self._handler()
        with patch.object(h, "authenticate", new_callable=AsyncMock, return_value=True):
            h.user = MagicMock(account=1)
            with patch(
                "kairon.chat.handlers.channels.clients.voice.exotel_stream.ChatDataProcessor"
                ".get_channel_config",
                side_effect=Exception("not found"),
            ):
                await h.run()
        assert ws.closed_code == 1011

    @pytest.mark.asyncio
    async def test_run_stt_build_failure_closes_1011(self):
        from kairon.shared.voice.resilience import FallbackSTT, FallbackTTS
        h, ws = self._handler()
        h.user = MagicMock(account=1)
        with patch.object(h, "authenticate", new_callable=AsyncMock, return_value=True):
            with patch(
                "kairon.chat.handlers.channels.clients.voice.exotel_stream.ChatDataProcessor"
                ".get_channel_config",
                return_value={"config": {"language": "en-IN", "welcome_message": None}},
            ):
                with patch(
                    "kairon.chat.handlers.channels.clients.voice.exotel_stream"
                    ".SpeechProviderConfigProcessor.resolve",
                    return_value={},
                ):
                    with patch.object(h, "_build_stt", side_effect=AppException("no stt")):
                        await h.run()
        assert ws.closed_code == 1011

    @pytest.mark.asyncio
    async def test_run_happy_path_accepts_socket_and_pumps(self):
        """Full run: auth OK, config OK, session starts and on_message called for each frame."""
        h, ws = self._handler(ws=_FakeWebSocket(messages=[
            json.dumps({"event": "start", "stream_sid": "S",
                        "start": {"call_sid": "C", "media_format": {"sample_rate": "8000"}}})
        ]))
        h.user = MagicMock(account=1)

        mock_session = MagicMock()
        mock_session.start = AsyncMock()
        mock_session.on_message = AsyncMock()
        mock_session.close = AsyncMock()

        mock_stt = MagicMock()
        mock_tts = MagicMock()

        with patch.object(h, "authenticate", new_callable=AsyncMock, return_value=True):
            with patch(
                "kairon.chat.handlers.channels.clients.voice.exotel_stream.ChatDataProcessor"
                ".get_channel_config",
                return_value={"config": {"language": "en-IN", "welcome_message": None}},
            ):
                with patch(
                    "kairon.chat.handlers.channels.clients.voice.exotel_stream"
                    ".SpeechProviderConfigProcessor.resolve",
                    return_value={},
                ):
                    with patch.object(h, "_build_stt", return_value=(mock_stt, "sarvam")):
                        with patch.object(h, "_build_tts",
                                          return_value=(mock_tts, "polly", "en-IN", None)):
                            with patch(
                                "kairon.chat.handlers.channels.clients.voice.exotel_stream"
                                ".ExotelCallSession",
                                return_value=mock_session,
                            ):
                                await h.run()

        assert ws.accepted
        mock_session.start.assert_awaited_once()
        mock_session.on_message.assert_awaited_once()
        mock_session.close.assert_awaited_once()


# ──────────────────────────────────────────────────────────────────────────────
# ExotelStreamHandler inner closures
# ──────────────────────────────────────────────────────────────────────────────

class TestExotelStreamHandlerClosures:
    """Cover the inner build closures in _stt_builder / _tts_builder / _make_agent_runner."""

    def _handler(self):
        from kairon.chat.handlers.channels.clients.voice.exotel_stream import ExotelStreamHandler
        ws = _FakeWebSocket()
        return ExotelStreamHandler(bot="b1", provider="exotel", token="TOK", websocket=ws)

    def test_stt_builder_closure_calls_factory(self):
        h = self._handler()
        mock_cls = MagicMock(return_value=MagicMock())
        resolved = {"sarvam": {"metadata": {"foo": "bar"}, "secrets": {"api_key": "k"}}}
        with patch(
            "kairon.chat.handlers.channels.clients.voice.exotel_stream.STTFactory.provider_metadata",
            return_value={"models": {"8000": "saarika:v2"}},
        ):
            with patch(
                "kairon.chat.handlers.channels.clients.voice.exotel_stream.STTFactory.get",
                return_value=mock_cls,
            ):
                build = h._stt_builder("sarvam", "en-IN", 8000, resolved)
                instance = build()
        mock_cls.assert_called_once()
        args = mock_cls.call_args[0]
        assert "api_key" in args[0]
        assert "model" in args[0]

    def test_tts_builder_closure_calls_factory(self):
        h = self._handler()
        mock_cls = MagicMock(return_value=MagicMock())
        resolved = {"polly": {"metadata": {"aws_access_key_id": "A"}, "secrets": {"aws_secret_access_key": "S"}}}
        with patch(
            "kairon.chat.handlers.channels.clients.voice.exotel_stream.TTSFactory.provider_metadata",
            return_value={"engine": "neural", "default_voice": "Kajal"},
        ):
            with patch(
                "kairon.chat.handlers.channels.clients.voice.exotel_stream.TTSFactory.get",
                return_value=mock_cls,
            ):
                build = h._tts_builder("polly", "en-IN", 8000, None, resolved)
                instance = build()
        mock_cls.assert_called_once()
        kwargs = mock_cls.call_args.kwargs
        assert kwargs.get("voice") == "Kajal"

    @pytest.mark.asyncio
    async def test_make_agent_runner_closure(self):
        h = self._handler()
        h.user = MagicMock(account=1)

        from kairon.shared.voice.exotel.session import AgentTurn
        mock_out = MagicMock()
        mock_out.get_messages.return_value = ["hi"]
        mock_out.should_hangup.return_value = False

        with patch(
            "kairon.chat.handlers.channels.clients.voice.exotel_stream.VoiceOutput",
            return_value=mock_out,
        ):
            with patch(
                "kairon.chat.handlers.channels.clients.voice.exotel_stream.AgentProcessor"
                ".handle_channel_message",
                new_callable=AsyncMock,
            ):
                runner = h._make_agent_runner()
                turn = await runner("hello", "sender1", {"bot": "b1"})
        assert isinstance(turn, AgentTurn)
        assert turn.messages == ["hi"]


# ──────────────────────────────────────────────────────────────────────────────
# ExotelCallSession — uncovered branches
# ──────────────────────────────────────────────────────────────────────────────

class _QueueSTT2:
    def __init__(self):
        self.pushed = []
        self.closed = False
        self._q = asyncio.Queue()

    async def open(self): pass

    async def push(self, pcm):
        self.pushed.append(pcm)

    async def feed(self, t):
        await self._q.put(t)

    async def transcripts(self):
        from kairon.shared.voice.stt.base import Transcript
        while True:
            item = await self._q.get()
            if item is None:
                break
            yield item

    async def close(self):
        self.closed = True
        await self._q.put(None)


class _SimpleTTS:
    async def synthesize(self, text):
        yield b"\x01\x02" * 350


class TestSessionBranches:

    def _make_session(self, runner=None, config=None, pace=False, metrics=None, cache=None):
        import asyncio
        sent = []

        async def sender(frame):
            sent.append(frame)

        stt = _QueueSTT2()
        tts = _SimpleTTS()

        async def default_runner(t, sid, m):
            from kairon.shared.voice.exotel.session import AgentTurn
            return AgentTurn(messages=["ok"])

        from kairon.shared.voice.exotel.session import ExotelCallSession
        s = ExotelCallSession(
            bot="b", config=config or {}, sender=sender, stt=stt, tts=tts,
            agent_runner=runner or default_runner,
            pace=pace, metrics=metrics, tts_cache=cache,
            tts_cache_namespace="ns",
        )
        return s, sent, stt

    def _start_msg(self):
        return json.dumps({
            "event": "start", "stream_sid": "SS1",
            "start": {"call_sid": "CC1", "from": "+91", "to": "+92",
                      "media_format": {"sample_rate": "8000"}},
        })

    # stop event
    @pytest.mark.asyncio
    async def test_stop_event_closes_session(self):
        s, sent, stt = self._make_session()
        await s.start()
        await s.on_message(self._start_msg())
        stop_msg = json.dumps({"event": "stop", "stream_sid": "SS1"})
        await s.on_message(stop_msg)
        assert s._closed

    # mark event
    @pytest.mark.asyncio
    async def test_mark_event_handled(self):
        s, sent, stt = self._make_session()
        await s.start()
        await s.on_message(self._start_msg())
        mark_msg = json.dumps({"event": "mark", "mark": {"name": "utt-1"}, "stream_sid": "SS1"})
        await s.on_message(mark_msg)  # should not raise

    # connected event
    @pytest.mark.asyncio
    async def test_connected_event_is_a_noop(self):
        s, sent, stt = self._make_session()
        await s.start()
        await s.on_message(json.dumps({"event": "connected", "stream_sid": "SS1"}))

    # unknown event
    @pytest.mark.asyncio
    async def test_unknown_event_logged(self):
        s, sent, stt = self._make_session()
        await s.start()
        await s.on_message(json.dumps({"event": "weirdstuff", "stream_sid": "SS1"}))

    # double start
    @pytest.mark.asyncio
    async def test_double_start_ignored(self):
        s, sent, stt = self._make_session()
        await s.start()
        await s.on_message(self._start_msg())
        assert s.call_sid == "CC1"
        # Second start with different sid should be ignored
        s2 = json.dumps({"event": "start", "stream_sid": "OTHER",
                          "start": {"call_sid": "CC2", "media_format": {"sample_rate": "8000"}}})
        await s.on_message(s2)
        assert s.call_sid == "CC1"  # unchanged

    # barge_in
    @pytest.mark.asyncio
    async def test_barge_in_sends_clear_frame(self):
        s, sent, stt = self._make_session()
        await s.start()
        await s.on_message(self._start_msg())
        sent.clear()
        await s.barge_in()
        assert any(f.get("event") == "clear" for f in sent)

    @pytest.mark.asyncio
    async def test_barge_in_without_stream_sid_is_noop(self):
        s, sent, stt = self._make_session()
        await s.start()
        await s.barge_in()  # no stream_sid yet — should not raise

    # close idempotent
    @pytest.mark.asyncio
    async def test_close_idempotent(self):
        s, sent, stt = self._make_session()
        await s.start()
        await s.on_message(self._start_msg())
        await s.close()
        await s.close()  # second close should not raise
        assert s._closed

    # metrics finalize in close
    @pytest.mark.asyncio
    async def test_close_finalizes_metrics(self):
        from kairon.shared.voice.metrics import CallMetrics
        finalized = []
        metrics = CallMetrics(bot="b", call_sid="", sink=finalized.append)
        s, sent, stt = self._make_session(metrics=metrics)
        await s.start()
        await s.on_message(self._start_msg())
        await s.close()
        assert len(finalized) == 1

    # _stream_tts when no stream_sid
    @pytest.mark.asyncio
    async def test_stream_tts_drops_when_no_stream_sid(self):
        s, sent, stt = self._make_session()
        await s.start()
        # don't call on_message(start) → stream_sid stays ""
        result = await s._stream_tts("hello")
        assert result is False
        assert not sent  # no media frames sent

    # _frame_seconds
    def test_frame_seconds_calculation(self):
        from kairon.shared.voice.exotel.session import ExotelCallSession

        async def noop_sender(f): pass
        from kairon.shared.voice.exotel.session import ExotelCallSession
        s, _, _ = self._make_session()
        # 8000 Hz, 2 bytes/sample → 16000 bytes/sec
        # 1600 bytes → 0.1 seconds
        assert abs(s._frame_seconds(1600) - 0.1) < 0.001

    # pace mode — _send_media sleep path
    @pytest.mark.asyncio
    async def test_send_media_pace_mode_runs(self):
        s, sent, stt = self._make_session(pace=True)
        await s.start()
        await s.on_message(self._start_msg())
        # Set stream_sid to allow sending
        assert s.stream_sid == "SS1"
        # Call _send_media directly (tiny frame → tiny sleep)
        await s._send_media(b"\x00\x00" * 2)
        assert any(f.get("event") == "media" for f in sent)

    # empty transcript text filtered
    @pytest.mark.asyncio
    async def test_empty_transcript_text_ignored(self):
        turns = []

        async def runner(t, sid, m):
            from kairon.shared.voice.exotel.session import AgentTurn
            turns.append(t)
            return AgentTurn(messages=[])

        s, sent, stt = self._make_session(runner=runner)
        await s.start()
        await s.on_message(self._start_msg())
        # Feed empty and whitespace-only final transcripts
        from kairon.shared.voice.stt.base import Transcript
        await stt.feed(Transcript("", True))
        await stt.feed(Transcript("   ", True))
        await asyncio.sleep(0.05)
        assert turns == []

    # turn is None
    @pytest.mark.asyncio
    async def test_none_turn_is_handled(self):
        async def runner(t, sid, m):
            return None

        s, sent, stt = self._make_session(runner=runner)
        await s.start()
        await s.on_message(self._start_msg())
        from kairon.shared.voice.stt.base import Transcript
        sent.clear()
        await stt.feed(Transcript("hi", True))
        await asyncio.sleep(0.05)
        # no media should be sent (turn returned None)
        assert not any(f.get("event") == "media" for f in sent)


# ──────────────────────────────────────────────────────────────────────────────
# VoiceProviderFactory
# ──────────────────────────────────────────────────────────────────────────────

class TestVoiceProviderFactory:

    def test_get_exotel_provider(self):
        from kairon.chat.handlers.channels.clients.voice.factory import VoiceProviderFactory
        from kairon.chat.handlers.channels.clients.voice.exotel import ExotelVoiceProvider
        cls = VoiceProviderFactory.get_provider("exotel")
        assert cls is ExotelVoiceProvider

    def test_unknown_provider_raises(self):
        from kairon.chat.handlers.channels.clients.voice.factory import VoiceProviderFactory
        with pytest.raises(Exception, match="not implemented"):
            VoiceProviderFactory.get_provider("vonage")


# ──────────────────────────────────────────────────────────────────────────────
# Cache — uncovered branches
# ──────────────────────────────────────────────────────────────────────────────

class TestTTSCacheAdditional:

    def test_update_existing_key_adjusts_bytes(self):
        from kairon.shared.voice.cache import TTSCache
        c = TTSCache()
        c.put("k", b"\x01" * 100)
        assert c.current_bytes == 100
        c.put("k", b"\x02" * 50)  # overwrite same key
        assert c.current_bytes == 50
        assert c.get("k") == b"\x02" * 50

    def test_clear_empties_cache(self):
        from kairon.shared.voice.cache import TTSCache
        c = TTSCache()
        c.put("a", b"AAA")
        c.put("b", b"BBB")
        c.clear()
        assert len(c) == 0
        assert c.current_bytes == 0

    def test_current_bytes_property(self):
        from kairon.shared.voice.cache import TTSCache
        c = TTSCache()
        assert c.current_bytes == 0
        c.put("x", b"\xFF" * 200)
        assert c.current_bytes == 200

    def test_make_key_function(self):
        from kairon.shared.voice.cache import make_key
        k1 = make_key("ns", "hello world")
        assert isinstance(k1, str) and len(k1) > 0

    def test_lru_eviction_by_bytes(self):
        from kairon.shared.voice.cache import TTSCache
        c = TTSCache(max_entries=100, max_bytes=50)
        c.put("a", b"\x01" * 30)
        c.put("b", b"\x02" * 30)  # total=60 > max_bytes=50 → evicts "a"
        assert c.get("a") is None
        assert c.get("b") is not None


# ──────────────────────────────────────────────────────────────────────────────
# Resilience — uncovered branches
# ──────────────────────────────────────────────────────────────────────────────

class TestResilienceAdditional:

    def test_fallback_stt_empty_builders_raises(self):
        from kairon.shared.voice.resilience import FallbackSTT
        with pytest.raises(Exception):
            FallbackSTT([])

    def test_fallback_tts_empty_builders_raises(self):
        from kairon.shared.voice.resilience import FallbackTTS
        with pytest.raises(Exception):
            FallbackTTS([])

    def test_normalise_non_tuple_builder(self):
        """A bare callable (not a tuple) is treated as a builder."""
        from kairon.shared.voice.resilience import FallbackTTS

        async def fake_synthesize(text):
            yield b"chunk"
            return

        class FakeAdapter:
            __name__ = "fake"
            async def synthesize(self, text):
                yield b"chunk"
                return

        ft = FallbackTTS([FakeAdapter])  # non-tuple builder
        # normalise should run without error

    @pytest.mark.asyncio
    async def test_fallback_stt_transcripts_when_no_active(self):
        from kairon.shared.voice.resilience import FallbackSTT

        class OKAdapter:
            async def open(self): pass
            async def push(self, p): pass
            async def transcripts(self):
                return
                yield
            async def close(self): pass

        fs = FallbackSTT([("ok", OKAdapter)])
        # Don't call open() — active remains None
        results = [t async for t in fs.transcripts()]
        assert results == []

    @pytest.mark.asyncio
    async def test_fallback_tts_mid_utterance_failure(self):
        """Provider that fails AFTER emitting audio should stop (not fall over to next)."""
        from kairon.shared.voice.resilience import FallbackTTS

        class FailMidAdapter:
            async def synthesize(self, text):
                yield b"first-chunk"
                raise RuntimeError("network error mid-stream")

        class GoodAdapter:
            async def synthesize(self, text):
                yield b"good-chunk"

        ft = FallbackTTS([("bad", lambda: FailMidAdapter()), ("good", lambda: GoodAdapter())])
        chunks = [c async for c in ft.synthesize("text")]
        # first chunk was yielded before failure; good provider NOT tried (emitted=True)
        assert b"first-chunk" in chunks
        assert b"good-chunk" not in chunks


# ──────────────────────────────────────────────────────────────────────────────
# SarvamSTT — _receive_loop and _parse_result gaps
# ──────────────────────────────────────────────────────────────────────────────

class TestSarvamSTTAdditional:

    def _parse(self, payload):
        from kairon.shared.voice.stt.sarvam import SarvamSTT
        return SarvamSTT._parse_result(payload)

    def test_parse_bytes_input(self):
        """Line 110: bytes input decoded before JSON parse."""
        t = self._parse(b'{"transcript": "hello", "is_final": true}')
        assert t is not None and t.text == "hello"

    def test_parse_invalid_json_returns_none(self):
        """Lines 113-114: ValueError on bad JSON."""
        assert self._parse("not valid json{{") is None

    def test_parse_non_dict_json_returns_none(self):
        """Line 116: data is list not dict."""
        import json
        assert self._parse(json.dumps(["a", "b"])) is None

    def test_parse_no_text_anywhere_returns_none(self):
        """Line 128: data field present but no transcript/text inside."""
        import json
        result = self._parse(json.dumps({"data": {"other": 42}, "type": "partial"}))
        assert result is None

    def test_parse_is_final_from_msg_type(self):
        """Line 133: is_final derived from msg_type when both is_final and final absent."""
        import json
        result = self._parse(json.dumps({"type": "final", "transcript": "hi"}))
        assert result is not None and result.is_final is True

        result2 = self._parse(json.dumps({"type": "partial", "transcript": "hi"}))
        assert result2 is not None and result2.is_final is False

    def test_parse_is_final_from_final_key(self):
        """Line 128: is_final falls through to 'final' key."""
        import json
        result = self._parse(json.dumps({"transcript": "hi", "final": True}))
        assert result is not None and result.is_final is True

    @pytest.mark.asyncio
    async def test_receive_loop_populates_queue(self):
        """Lines 80-90: _receive_loop reads WS and puts transcripts on queue."""
        from kairon.shared.voice.stt.sarvam import SarvamSTT
        stt = SarvamSTT({"api_key": "k"}, "en-IN")

        raw_messages = [
            '{"type": "final", "transcript": "hello", "is_final": true}',
            '{"type": "ready"}',  # keepalive → None from _parse_result → not put
        ]

        class FakeWS:
            def __init__(self, msgs):
                self._msgs = list(msgs)

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self._msgs:
                    return self._msgs.pop(0)
                raise StopAsyncIteration

        stt._ws = FakeWS(raw_messages)
        await stt._receive_loop()
        # queue: one Transcript + sentinel
        item = stt._queue.get_nowait()
        assert item is not None and item.text == "hello"
        sentinel = stt._queue.get_nowait()
        assert sentinel is None


# ──────────────────────────────────────────────────────────────────────────────
# SpeechProviderConfigProcessor helper functions
# ──────────────────────────────────────────────────────────────────────────────

class TestSpeechProcessorHelpers:

    def test_encrypt_secrets_roundtrip(self):
        from kairon.shared.voice.processor import SpeechProviderConfigProcessor
        secrets = {"api_key": "mykey"}
        encrypted = SpeechProviderConfigProcessor._encrypt_secrets("sarvam", secrets)
        assert encrypted["api_key"] != "mykey"
        decrypted = SpeechProviderConfigProcessor._decrypt_secrets("sarvam", encrypted)
        assert decrypted["api_key"] == "mykey"

    def test_encrypt_secrets_empty_value_kept(self):
        from kairon.shared.voice.processor import SpeechProviderConfigProcessor
        secrets = {"api_key": ""}
        encrypted = SpeechProviderConfigProcessor._encrypt_secrets("sarvam", secrets)
        assert encrypted["api_key"] == ""

    def test_decrypt_secrets_empty_value_kept(self):
        from kairon.shared.voice.processor import SpeechProviderConfigProcessor
        secrets = {"api_key": ""}
        decrypted = SpeechProviderConfigProcessor._decrypt_secrets("sarvam", secrets)
        assert decrypted["api_key"] == ""

    def test_encrypt_secrets_failure_keeps_value(self):
        from kairon.shared.voice.processor import SpeechProviderConfigProcessor
        secrets = {"api_key": "plaintext"}
        with patch("kairon.shared.voice.processor.Utility.encrypt_message",
                   side_effect=Exception("encrypt failed")):
            result = SpeechProviderConfigProcessor._encrypt_secrets("sarvam", secrets)
        # on failure, value kept as-is
        assert result["api_key"] == "plaintext"

    def test_decrypt_secrets_failure_keeps_value(self):
        from kairon.shared.voice.processor import SpeechProviderConfigProcessor
        secrets = {"api_key": "encrypted_value"}
        with patch("kairon.shared.voice.processor.Utility.decrypt_message",
                   side_effect=Exception("decrypt failed")):
            result = SpeechProviderConfigProcessor._decrypt_secrets("sarvam", secrets)
        assert result["api_key"] == "encrypted_value"


# ──────────────────────────────────────────────────────────────────────────────
# Audio helpers — uncovered branches
# ──────────────────────────────────────────────────────────────────────────────

class TestAudioHelpersAdditional:

    def test_frame_multiple_zero_multiple_returns_nbytes(self):
        from kairon.shared.voice.exotel.audio import frame_multiple
        assert frame_multiple(500, 0) == 500
        assert frame_multiple(500, -1) == 500

    def test_pad_to_multiple_zero_multiple_passthrough(self):
        from kairon.shared.voice.exotel.audio import pad_to_multiple
        pcm = b"\x01" * 100
        assert pad_to_multiple(pcm, 0) is pcm

    def test_pad_to_multiple_already_aligned(self):
        from kairon.shared.voice.exotel.audio import pad_to_multiple
        pcm = b"\x01" * 320  # exactly 320 bytes → already aligned to 320
        result = pad_to_multiple(pcm, 320)
        assert result == pcm and len(result) == 320

    def test_is_silence_empty_input(self):
        from kairon.shared.voice.exotel.audio import is_silence
        assert is_silence(b"") is True

    def test_rms_fallback_pure_python(self):
        """Cover pure Python rms path by mocking audioop import to raise."""
        import sys
        from kairon.shared.voice.exotel import audio
        # Force the audioop ImportError branch
        pcm = b"\x10\x00" * 100  # 100 samples of value 0x0010 = 16
        with patch.dict(sys.modules, {"audioop": None}):
            result = audio.rms(pcm)
        assert result > 0.0


# ──────────────────────────────────────────────────────────────────────────────
# Protocol — uncovered branches
# ──────────────────────────────────────────────────────────────────────────────

class TestProtocolAdditional:

    def test_parse_inbound_bytes_input(self):
        from kairon.shared.voice.exotel.protocol import parse_inbound
        msg = json.dumps({"event": "stop", "stream_sid": "SS1"}).encode()
        frame = parse_inbound(msg)
        assert frame.event == "stop"

    def test_parse_inbound_non_dict_non_string(self):
        from kairon.shared.voice.exotel.protocol import parse_inbound
        frame = parse_inbound(12345)  # int → not dict, not str
        assert frame.event == ""

    def test_parse_inbound_start_without_top_stream_sid(self):
        """stream_sid comes from start.stream_sid when top-level is absent."""
        from kairon.shared.voice.exotel.protocol import parse_inbound
        frame = parse_inbound({
            "event": "start",
            "start": {
                "stream_sid": "SS_FROM_START",
                "call_sid": "CC1",
                "media_format": {"sample_rate": "8000"},
            },
        })
        assert frame.stream_sid == "SS_FROM_START"

    def test_decode_payload_bytes_input(self):
        from kairon.shared.voice.exotel.protocol import decode_payload
        pcm = b"\x10\x20" * 10
        payload_bytes = base64.b64encode(pcm)
        result = decode_payload(payload_bytes)
        assert result == pcm

    def test_decode_payload_invalid_falls_back_to_urlsafe(self):
        """Lines 163-167: first b64decode raises, urlsafe succeeds on second call."""
        import binascii
        from kairon.shared.voice.exotel.protocol import decode_payload
        expected = b"\xfb\xff\xfb"
        valid_urlsafe = base64.urlsafe_b64encode(expected).decode()
        # side_effect: first call fails (from decode_payload try), second call
        # returns decoded bytes (called internally by urlsafe_b64decode).
        import kairon.shared.voice.exotel.protocol as proto_mod
        with patch.object(proto_mod.base64, "b64decode",
                          side_effect=[binascii.Error("bad"), expected]):
            result = decode_payload(valid_urlsafe)
        assert result == expected

    def test_decode_payload_completely_invalid(self):
        from kairon.shared.voice.exotel.protocol import decode_payload
        result = decode_payload("!!!not base64 at all!!!")
        assert result == b""


# ──────────────────────────────────────────────────────────────────────────────
# Session — DTMF timer and metrics exception branches
# ──────────────────────────────────────────────────────────────────────────────

class TestSessionDTMFTimer:

    def _make_session(self, runner=None, config=None):
        sent = []

        async def sender(frame):
            sent.append(frame)

        stt = _QueueSTT2()
        tts = _SimpleTTS()

        async def default_runner(t, sid, m):
            from kairon.shared.voice.exotel.session import AgentTurn
            return AgentTurn(messages=["ok"])

        from kairon.shared.voice.exotel.session import ExotelCallSession
        s = ExotelCallSession(
            bot="b", config=config or {}, sender=sender, stt=stt, tts=tts,
            agent_runner=runner or default_runner,
            pace=False, tts_cache_namespace="ns",
        )
        return s, sent, stt

    def _start_msg(self):
        return json.dumps({
            "event": "start", "stream_sid": "SS1",
            "start": {"call_sid": "CC1", "from": "+91", "to": "+92",
                      "media_format": {"sample_rate": "8000"}},
        })

    @pytest.mark.asyncio
    async def test_dtmf_timer_arms_and_cancels(self):
        """DTMF inter_digit_timeout > 0 arms a timer; terminator cancels it."""
        digits = []

        async def runner(t, sid, m):
            from kairon.shared.voice.exotel.session import AgentTurn
            digits.append(t)
            return AgentTurn(messages=[])

        cfg = {"dtmf": {"enabled": True, "terminator": "#", "max_length": 10,
                        "inter_digit_timeout": 0.05}}
        s, sent, stt = self._make_session(runner=runner, config=cfg)
        await s.start()
        await s.on_message(self._start_msg())

        # Push digit — timer arms
        await s.on_message(json.dumps({"event": "dtmf", "dtmf": {"digit": "5"}}))
        assert s._dtmf_timer is not None  # timer armed

        # Push terminator — timer cancels and turn runs
        await s.on_message(json.dumps({"event": "dtmf", "dtmf": {"digit": "#"}}))
        await asyncio.sleep(0.05)
        assert s._dtmf_timer is None  # cancelled
        assert digits == ["5"]

    @pytest.mark.asyncio
    async def test_dtmf_timer_fires_on_timeout(self):
        """When timer fires (no more digits), buffered digits submitted."""
        digits = []

        async def runner(t, sid, m):
            from kairon.shared.voice.exotel.session import AgentTurn
            digits.append(t)
            return AgentTurn(messages=[])

        cfg = {"dtmf": {"enabled": True, "terminator": "#", "max_length": 10,
                        "inter_digit_timeout": 0.02}}
        s, sent, stt = self._make_session(runner=runner, config=cfg)
        await s.start()
        await s.on_message(self._start_msg())
        await s.on_message(json.dumps({"event": "dtmf", "dtmf": {"digit": "7"}}))
        # wait for timer to fire
        await asyncio.sleep(0.1)
        assert digits == ["7"]

    @pytest.mark.asyncio
    async def test_metrics_turn_exception_not_fatal(self):
        """If metrics.turn() raises, the session should continue (not crash)."""
        from kairon.shared.voice.metrics import CallMetrics
        mock_metrics = MagicMock(spec=CallMetrics)
        mock_metrics.call_sid = ""
        mock_metrics.turn.side_effect = RuntimeError("metrics broken")

        from kairon.shared.voice.exotel.session import AgentTurn
        turns = []

        async def runner(t, sid, m):
            turns.append(t)
            return AgentTurn(messages=["response"])

        from kairon.shared.voice.exotel.session import ExotelCallSession
        sent = []

        async def sender(frame):
            sent.append(frame)

        stt = _QueueSTT2()
        s = ExotelCallSession(
            bot="b", config={}, sender=sender, stt=stt, tts=_SimpleTTS(),
            agent_runner=runner, pace=False, metrics=mock_metrics,
            tts_cache_namespace="ns",
        )
        await s.start()
        start_msg = json.dumps({
            "event": "start", "stream_sid": "SS1",
            "start": {"call_sid": "CC1", "media_format": {"sample_rate": "8000"}},
        })
        await s.on_message(start_msg)
        from kairon.shared.voice.stt.base import Transcript
        await stt.feed(Transcript("hello", True))
        await asyncio.sleep(0.05)
        # turn ran despite metrics exception
        assert "hello" in turns


# ──────────────────────────────────────────────────────────────────────────────
# persist_call_metrics
# ──────────────────────────────────────────────────────────────────────────────

class TestPersistCallMetrics:

    def test_persist_call_metrics_saves_all_fields(self):
        from kairon.shared.voice.metrics import persist_call_metrics
        summary = {
            "bot": "b1", "call_sid": "CS1", "provider": "exotel",
            "stt_provider": "sarvam", "tts_provider": "polly",
            "turns": 2, "duration_ms": 5000.0,
            "agent_ms_avg": 200.0, "agent_ms_max": 300.0,
            "tts_ms_avg": 100.0, "tts_ms_max": 150.0,
            "tts_cache_hits": 1,
        }
        # VoiceCallMetrics is imported locally inside persist_call_metrics
        with patch("kairon.shared.voice.data_objects.VoiceCallMetrics") as MockDoc:
            instance = MagicMock()
            MockDoc.return_value = instance
            persist_call_metrics(summary)
        MockDoc.assert_called_once()
        instance.save.assert_called_once()


# ──────────────────────────────────────────────────────────────────────────────
# Remaining gaps: audio rms pure-python zero, sarvam TTS warning, auth close fail
# ──────────────────────────────────────────────────────────────────────────────

async def _empty_async_gen():
    """Empty async generator helper."""
    return
    yield  # makes it an async generator


class TestRemainingGaps:

    def test_sarvam_tts_http_error_logs_warning(self):
        """Lines 77-78: status >= 400 logs warning before raise_for_status."""
        from kairon.shared.voice.tts.sarvam import SarvamTTS
        tts = SarvamTTS({"api_key": "k"})
        resp = MagicMock()
        resp.status_code = 429
        resp.text = "Too Many Requests"
        resp.raise_for_status.side_effect = Exception("HTTP 429")
        with patch("requests.post", return_value=resp):
            with pytest.raises(Exception):
                tts._synthesize_sync("test")

    def test_sarvam_tts_width_conversion(self):
        """Line 35: width != 2 triggers audioop.lin2lin in _wav_to_pcm."""
        from kairon.shared.voice.tts.sarvam import _wav_to_pcm
        wav = _make_wav(160, 8000, 1, 1)  # 8-bit samples (width=1)
        pcm = _wav_to_pcm(wav, 8000)
        assert isinstance(pcm, bytes) and len(pcm) > 0

    @pytest.mark.asyncio
    async def test_authenticate_ws_close_also_fails(self):
        """Lines 65-66: auth raises AND subsequent websocket.close() also raises."""
        ws = _FakeWebSocket()

        async def failing_close(code=1000):
            raise RuntimeError("close failed too")

        ws.close = failing_close
        from kairon.chat.handlers.channels.clients.voice.exotel_stream import ExotelStreamHandler
        h = ExotelStreamHandler(bot="b1", provider="exotel", token="TOK", websocket=ws)
        with patch(
            "kairon.chat.handlers.channels.clients.voice.exotel_stream.Authentication"
            ".get_current_user_and_bot",
            new_callable=AsyncMock,
            side_effect=Exception("invalid token"),
        ):
            result = await h.authenticate()
        assert result is False

    @pytest.mark.asyncio
    async def test_run_sender_closure_sends_frames(self):
        """Line 192: sender closure inside run() calls websocket.send_text."""
        ws = _FakeWebSocket(messages=[
            json.dumps({"event": "start", "stream_sid": "S",
                        "start": {"call_sid": "C", "media_format": {"sample_rate": "8000"}}})
        ])
        from kairon.chat.handlers.channels.clients.voice.exotel_stream import ExotelStreamHandler
        h = ExotelStreamHandler(bot="b1", provider="exotel", token="TOK", websocket=ws)
        h.user = MagicMock(account=1)

        mock_stt = MagicMock()
        mock_stt.open = AsyncMock()
        mock_stt.transcripts = MagicMock(return_value=_empty_async_gen())
        mock_stt.close = AsyncMock()
        mock_tts = MagicMock()
        mock_tts.synthesize = MagicMock(return_value=_empty_async_gen())

        with patch.object(h, "authenticate", new_callable=AsyncMock, return_value=True):
            with patch(
                "kairon.chat.handlers.channels.clients.voice.exotel_stream.ChatDataProcessor"
                ".get_channel_config",
                return_value={"config": {"language": "en-IN", "welcome_message": "Hi"}},
            ):
                with patch(
                    "kairon.chat.handlers.channels.clients.voice.exotel_stream"
                    ".SpeechProviderConfigProcessor.resolve",
                    return_value={},
                ):
                    with patch.object(h, "_build_stt", return_value=(mock_stt, "sarvam")):
                        with patch.object(h, "_build_tts",
                                          return_value=(mock_tts, "polly", "en-IN", None)):
                            await h.run()
        assert ws.accepted
