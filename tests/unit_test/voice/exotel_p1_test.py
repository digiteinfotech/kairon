import base64
import json

import pytest

from kairon.shared.voice.exotel import audio, protocol
from kairon.shared.voice.exotel.protocol import ExotelEvent, parse_inbound
from kairon.shared.voice.exotel.session import AgentTurn, ExotelCallSession


# --------------------------------------------------------------------------- protocol
class TestExotelProtocol:

    def test_parse_media_decodes_payload(self):
        pcm = bytes(range(256)) * 2
        msg = json.dumps({
            "event": "media", "stream_sid": "S1", "sequence_number": "5",
            "media": {"payload": base64.b64encode(pcm).decode(), "chunk": "1", "timestamp": "20"},
        })
        f = parse_inbound(msg)
        assert f.event == ExotelEvent.MEDIA.value
        assert f.stream_sid == "S1" and f.sequence_number == 5
        assert f.media_payload == pcm and f.media_chunk == "1"

    def test_parse_start_extracts_call_identity(self):
        f = parse_inbound({
            "event": "start", "stream_sid": "S2",
            "start": {"call_sid": "C1", "account_sid": "A1", "from": "+911", "to": "+912",
                      "media_format": {"encoding": "audio/x-l16", "sample_rate": "8000"},
                      "custom_parameters": {"bot": "b1"}},
        })
        assert f.start.call_sid == "C1" and f.start.from_number == "+911"
        assert f.start.to_number == "+912" and f.start.sample_rate == 8000
        assert f.start.custom_parameters["bot"] == "b1"

    def test_parse_dtmf_and_stop_and_mark(self):
        assert parse_inbound({"event": "dtmf", "dtmf": {"digit": "7"}}).dtmf_digit == "7"
        assert parse_inbound({"event": "stop", "stream_sid": "S"}).event == "stop"
        assert parse_inbound({"event": "mark", "mark": {"name": "m1"}}).mark_name == "m1"

    def test_parse_malformed_is_safe(self):
        bad = parse_inbound("not json{")
        assert bad.event == "" and "unparsed" in bad.raw

    def test_builders_roundtrip(self):
        pcm = b"\x01\x02\x03\x04"
        m = protocol.build_media("S1", pcm)
        assert m["event"] == "media"
        assert protocol.decode_payload(m["media"]["payload"]) == pcm
        assert protocol.build_mark("S1", "end")["mark"]["name"] == "end"
        assert protocol.build_clear("S1") == {"event": "clear", "stream_sid": "S1"}

    def test_decode_payload_tolerates_bad_padding(self):
        assert protocol.decode_payload(None) == b""
        assert isinstance(protocol.decode_payload("QQ"), bytes)  # missing padding


# ----------------------------------------------------------------------------- audio
class TestAudioChunker:

    def test_frames_are_multiples_and_remainder_held(self):
        ch = audio.AudioChunker(multiple=320)
        ch.push(b"\x01\x02" * 400)  # 800 bytes
        frames = list(ch.drain())
        assert [len(x) for x in frames] == [320, 320]
        assert ch.pending_bytes() == 160

    def test_flush_pads_tail_with_silence(self):
        ch = audio.AudioChunker(multiple=320)
        ch.push(b"\xaa" * 160)
        flushed = list(ch.flush())
        assert len(flushed) == 1 and len(flushed[0]) == 320
        assert flushed[0][160:] == b"\x00" * 160

    def test_max_bytes_clamped_to_multiple(self):
        ch = audio.AudioChunker(multiple=320, max_bytes=1000, frame_bytes=1000)
        assert ch.max_bytes == 960 and ch.frame_bytes == 960
        ch.push(b"\x00" * 2000)
        assert [len(x) for x in ch.drain()] == [960, 960]
        assert ch.pending_bytes() == 80

    def test_chunk_pcm_convenience(self):
        frames = audio.chunk_pcm(b"\x05" * 700, multiple=320)
        assert [len(x) for x in frames] == [320, 320, 320]

    def test_silence_detection(self):
        assert audio.is_silence(b"\x00\x00" * 100)
        assert not audio.is_silence((b"\xff\x7f") * 100)
        assert audio.rms(b"") == 0.0


# ------------------------------------------------------------------------ sarvam parse
class TestSarvamParse:

    def _parse(self, payload):
        from kairon.shared.voice.stt.sarvam import SarvamSTT
        return SarvamSTT._parse_result(json.dumps(payload))

    def test_final_transcript(self):
        t = self._parse({"type": "final", "transcript": "hello", "is_final": True, "confidence": 0.9})
        assert t.text == "hello" and t.is_final and t.confidence == 0.9

    def test_partial_transcript(self):
        t = self._parse({"type": "partial", "text": "hel", "is_final": False})
        assert t.text == "hel" and t.is_final is False

    def test_nested_data_field(self):
        t = self._parse({"data": {"transcript": "world"}, "final": True})
        assert t.text == "world" and t.is_final

    def test_keepalive_returns_none(self):
        assert self._parse({"type": "ready"}) is None
        assert self._parse({"type": "pong"}) is None

    def test_builtin_adapter_registered(self):
        from kairon.shared.voice.stt.factory import STTFactory
        from kairon.shared.voice.tts.factory import TTSFactory
        from kairon.shared.voice.stt.sarvam import SarvamSTT
        from kairon.shared.voice.tts.polly import PollyTTS
        assert STTFactory.get("sarvam") is SarvamSTT
        assert TTSFactory.get("polly") is PollyTTS


# --------------------------------------------------------------------------- fakes
class _Transcript:
    def __init__(self, text, is_final):
        self.text = text
        self.is_final = is_final
        self.confidence = None


class _FakeSTT:
    def __init__(self):
        import asyncio
        self.pushed = []
        self.opened = False
        self.closed = False
        self._q = asyncio.Queue()

    async def open(self):
        self.opened = True

    async def push(self, pcm):
        self.pushed.append(pcm)

    async def feed(self, t):
        await self._q.put(t)

    async def transcripts(self):
        while True:
            item = await self._q.get()
            if item is None:
                break
            yield item

    async def close(self):
        self.closed = True
        await self._q.put(None)


class _FakeTTS:
    def __init__(self):
        self.calls = []

    async def synthesize(self, text):
        self.calls.append(text)
        yield b"\x10\x20" * 350  # 700 bytes


def _media(sid, pcm):
    return json.dumps({"event": "media", "stream_sid": sid,
                       "media": {"payload": base64.b64encode(pcm).decode()}})


def _start(sid="ST1"):
    return json.dumps({"event": "start", "stream_sid": sid,
                       "start": {"call_sid": "CS1", "from": "+91", "to": "+92",
                                 "media_format": {"sample_rate": "8000"}}})


# --------------------------------------------------------------------------- session
class TestExotelSession:

    def _session(self, runner, welcome="Hi there"):
        sent = []

        async def sender(frame):
            sent.append(frame)

        stt = _FakeSTT()
        tts = _FakeTTS()
        s = ExotelCallSession(
            bot="b1", config={"welcome_message": welcome}, sender=sender,
            stt=stt, tts=tts, agent_runner=runner, pace=False, metadata={"account": 7},
        )
        return s, sent, stt, tts

    @pytest.mark.asyncio
    async def test_welcome_played_on_start(self):
        async def runner(text, sid, meta):
            return AgentTurn(messages=["ignored"])

        s, sent, stt, tts = self._session(runner)
        await s.start()
        assert stt.opened
        await s.on_message(_start())
        assert s.stream_sid == "ST1" and s.call_sid == "CS1"
        media = [f for f in sent if f["event"] == "media"]
        marks = [f for f in sent if f["event"] == "mark"]
        assert media and marks
        for f in media:
            assert len(base64.b64decode(f["media"]["payload"])) % 320 == 0
        assert tts.calls == ["Hi there"]

    @pytest.mark.asyncio
    async def test_media_pushed_to_stt(self):
        async def runner(text, sid, meta):
            return AgentTurn(messages=[])

        s, sent, stt, tts = self._session(runner, welcome=None)
        await s.start()
        await s.on_message(_start())
        pcm = b"\xaa\xbb" * 160
        await s.on_message(_media("ST1", pcm))
        assert stt.pushed[-1] == pcm

    @pytest.mark.asyncio
    async def test_final_transcript_runs_turn_and_streams_reply(self):
        import asyncio
        turns = []

        async def runner(text, sid, meta):
            turns.append((text, sid, dict(meta)))
            return AgentTurn(messages=["You said " + text])

        s, sent, stt, tts = self._session(runner, welcome=None)
        await s.start()
        await s.on_message(_start())
        sent.clear()
        await stt.feed(_Transcript("hello", True))
        await asyncio.sleep(0.05)
        assert turns and turns[-1][0] == "hello"
        assert turns[-1][2]["account"] == 7 and turns[-1][1] == "CS1"
        assert any(f["event"] == "media" for f in sent)
        assert any(f["event"] == "mark" for f in sent)

    @pytest.mark.asyncio
    async def test_partial_transcript_ignored(self):
        import asyncio
        turns = []

        async def runner(text, sid, meta):
            turns.append(text)
            return AgentTurn(messages=[])

        s, sent, stt, tts = self._session(runner, welcome=None)
        await s.start()
        await s.on_message(_start())
        await stt.feed(_Transcript("partial", False))
        await asyncio.sleep(0.02)
        assert turns == []

    @pytest.mark.asyncio
    async def test_hangup_closes_session(self):
        import asyncio

        async def runner(text, sid, meta):
            return AgentTurn(messages=["Goodbye"], hangup=True)

        s, sent, stt, tts = self._session(runner, welcome=None)
        await s.start()
        await s.on_message(_start())
        await stt.feed(_Transcript("bye", True))
        await asyncio.sleep(0.05)
        assert s._closed and stt.closed

    @pytest.mark.asyncio
    async def test_agent_error_yields_apology(self):
        import asyncio

        async def runner(text, sid, meta):
            raise RuntimeError("brain down")

        s, sent, stt, tts = self._session(runner, welcome=None)
        await s.start()
        await s.on_message(_start())
        sent.clear()
        await stt.feed(_Transcript("hello", True))
        await asyncio.sleep(0.05)
        # apology is synthesised and streamed as media
        assert any(f["event"] == "media" for f in sent)
