import asyncio
import base64
import json

import pytest

from kairon.exceptions import AppException
from kairon.shared.voice.cache import TTSCache, make_key
from kairon.shared.voice.credentials import VoiceCredentialResolver
from kairon.shared.voice.metrics import CallMetrics
from kairon.shared.voice.resilience import FallbackSTT, FallbackTTS
from kairon.shared.voice.exotel.session import AgentTurn, ExotelCallSession


# ------------------------------------------------------------------------- cache
class TestTTSCache:

    def test_hit_and_miss(self):
        c = TTSCache()
        k = make_key("polly:Kajal:en-IN:8000", "hello")
        assert c.get(k) is None and c.misses == 1
        c.put(k, b"A" * 50)
        assert c.get(k) == b"A" * 50 and c.hits == 1

    def test_lru_eviction_by_count(self):
        c = TTSCache(max_entries=2, max_bytes=10_000)
        a, b, d = (make_key("n", x) for x in ("a", "b", "c"))
        c.put(a, b"1"); c.put(b, b"2")
        c.get(a)                 # touch 'a' so 'b' is now LRU
        c.put(d, b"3")           # evicts 'b'
        assert c.get(a) is not None and c.get(d) is not None
        assert c.get(b) is None and len(c) == 2

    def test_namespace_isolation(self):
        assert make_key("polly:Kajal:en-IN:8000", "hi") != make_key("polly:meera:hi-IN:8000", "hi")

    def test_skips_oversized_items(self):
        c = TTSCache(max_item_bytes=10)
        c.put("k", b"x" * 50)
        assert c.get("k") is None

    def test_disabled(self):
        c = TTSCache(enabled=False)
        c.put("k", b"x")
        assert c.get("k") is None


# ---------------------------------------------------------------------- fallback
class _FakeTTS:
    def __init__(self, chunks=None, fail_before=False, fail_after=False):
        self.chunks = chunks or [b"aa", b"bb"]
        self.fail_before = fail_before
        self.fail_after = fail_after

    async def synthesize(self, text):
        if self.fail_before:
            raise RuntimeError("boom-before")
        for ch in self.chunks:
            yield ch
        if self.fail_after:
            raise RuntimeError("boom-after")


class _FakeSTT:
    def __init__(self, fail_open=False):
        self.fail_open = fail_open
        self.opened = False
        self.closed = False
        self.pushed = []

    async def open(self):
        if self.fail_open:
            raise RuntimeError("no-open")
        self.opened = True

    async def push(self, pcm):
        self.pushed.append(pcm)

    async def transcripts(self):
        from kairon.shared.voice.stt.base import Transcript
        yield Transcript("t", True)

    async def close(self):
        self.closed = True


class TestFallback:

    @pytest.mark.asyncio
    async def test_tts_fails_over_before_audio(self):
        ft = FallbackTTS([
            ("p1", lambda: _FakeTTS(fail_before=True)),
            ("p2", lambda: _FakeTTS(chunks=[b"xx"])),
        ])
        assert [c async for c in ft.synthesize("hi")] == [b"xx"]

    @pytest.mark.asyncio
    async def test_tts_primary_wins(self):
        ft = FallbackTTS([
            ("p1", lambda: _FakeTTS(chunks=[b"yy"])),
            ("p2", lambda: _FakeTTS(chunks=[b"zz"])),
        ])
        assert [c async for c in ft.synthesize("hi")] == [b"yy"]

    @pytest.mark.asyncio
    async def test_tts_all_fail_is_empty(self):
        ft = FallbackTTS([("p1", lambda: _FakeTTS(fail_before=True))])
        assert [c async for c in ft.synthesize("hi")] == []

    @pytest.mark.asyncio
    async def test_stt_open_failover(self):
        good = _FakeSTT()
        fs = FallbackSTT([("s1", lambda: _FakeSTT(fail_open=True)), ("s2", lambda: good)])
        await fs.open()
        assert fs.active is good and fs.active_provider == "s2"
        await fs.push(b"z")
        assert good.pushed == [b"z"]
        assert [t.text async for t in fs.transcripts()] == ["t"]
        await fs.close()
        assert good.closed

    @pytest.mark.asyncio
    async def test_stt_all_fail_raises(self):
        fs = FallbackSTT([("s1", lambda: _FakeSTT(fail_open=True))])
        with pytest.raises(AppException):
            await fs.open()


# ----------------------------------------------------------------------- metrics
class TestCallMetrics:

    def test_aggregation(self):
        m = CallMetrics(bot="b", call_sid="c")
        m.turn(10, 20, cache_hit=False)
        m.turn(30, 40, cache_hit=True)
        s = m.summary()
        assert s["turns"] == 2
        assert s["agent_ms_avg"] == 20 and s["agent_ms_max"] == 30
        assert s["tts_ms_avg"] == 30 and s["tts_ms_max"] == 40
        assert s["tts_cache_hits"] == 1

    def test_finalize_invokes_sink_once(self):
        seen = []
        m = CallMetrics(bot="b", call_sid="c", sink=seen.append)
        m.turn(1, 1)
        first = m.finalize()
        m.finalize()
        assert len(seen) == 1 and seen[0]["turns"] == 1 and first["turns"] == 1


# ------------------------------------------------------------------- credentials
class TestCredentialResolver:

    def test_decrypt_config_uses_secret_fields(self):
        out = VoiceCredentialResolver.decrypt_config(
            {"api_key": "ENC", "region": "ap-south-1"},
            ["api_key"],
            decryptor=lambda v: f"dec({v})",
        )
        assert out["api_key"] == "dec(ENC)"
        assert out["region"] == "ap-south-1"  # non-secret untouched

    def test_decrypt_leaves_value_on_failure(self):
        def boom(_):
            raise ValueError("bad token")

        out = VoiceCredentialResolver.decrypt_config({"api_key": "plain"}, ["api_key"], decryptor=boom)
        assert out["api_key"] == "plain"


# --------------------------------------------------------------------- fakes/util
class _Transcript:
    def __init__(self, text, is_final):
        self.text = text
        self.is_final = is_final
        self.confidence = None


class _QueueSTT:
    def __init__(self):
        self.pushed = []
        self.closed = False
        self._q = asyncio.Queue()

    async def open(self):
        pass

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


class _CountingTTS:
    def __init__(self):
        self.calls = 0

    async def synthesize(self, text):
        self.calls += 1
        yield b"\x01\x02" * 350


def _start(sid="S", call="C"):
    return json.dumps({"event": "start", "stream_sid": sid,
                       "start": {"call_sid": call, "media_format": {"sample_rate": "8000"}}})


def _dtmf(d):
    return json.dumps({"event": "dtmf", "dtmf": {"digit": d}})


# ------------------------------------------------------------------- session P2
class TestSessionResilienceFeatures:

    def _session(self, runner, config=None, cache=None, metrics=None):
        sent = []

        async def sender(frame):
            sent.append(frame)

        stt = _QueueSTT()
        tts = _CountingTTS()
        s = ExotelCallSession(
            bot="b", config=config or {}, sender=sender, stt=stt, tts=tts,
            agent_runner=runner, pace=False, metrics=metrics, tts_cache=cache,
            tts_cache_namespace="polly:Kajal:en-IN:8000",
        )
        return s, sent, stt, tts

    @pytest.mark.asyncio
    async def test_cache_avoids_resynthesis_and_counts_hit(self):
        async def runner(t, sid, m):
            return AgentTurn(messages=["same reply"])

        cache = TTSCache()
        metrics = CallMetrics(bot="b", call_sid="")
        s, sent, stt, tts = self._session(runner, config={"welcome_message": None},
                                          cache=cache, metrics=metrics)
        await s.start()
        await s.on_message(_start())
        assert metrics.call_sid == "C"
        await stt.feed(_Transcript("hi", True))
        await asyncio.sleep(0.05)
        assert tts.calls == 1
        await stt.feed(_Transcript("hi again", True))
        await asyncio.sleep(0.05)
        assert tts.calls == 1  # served from cache
        assert metrics.summary()["tts_cache_hits"] == 1

    @pytest.mark.asyncio
    async def test_dtmf_terminator_submits_collected_digits(self):
        digits = []

        async def runner(t, sid, m):
            digits.append(t)
            return AgentTurn(messages=[])

        s, sent, stt, tts = self._session(
            runner, config={"dtmf": {"terminator": "#", "max_length": 10}})
        await s.start()
        await s.on_message(_start())
        for d in ("1", "2", "3"):
            await s.on_message(_dtmf(d))
        assert digits == []
        await s.on_message(_dtmf("#"))
        await asyncio.sleep(0.02)
        assert digits == ["123"]

    @pytest.mark.asyncio
    async def test_dtmf_max_length_auto_submits(self):
        digits = []

        async def runner(t, sid, m):
            digits.append(t)
            return AgentTurn(messages=[])

        s, sent, stt, tts = self._session(
            runner, config={"dtmf": {"terminator": "#", "max_length": 4}})
        await s.start()
        await s.on_message(_start())
        for d in ("9", "8", "7", "6"):
            await s.on_message(_dtmf(d))
        await asyncio.sleep(0.02)
        assert digits == ["9876"]

    @pytest.mark.asyncio
    async def test_dtmf_disabled(self):
        digits = []

        async def runner(t, sid, m):
            digits.append(t)
            return AgentTurn(messages=[])

        s, sent, stt, tts = self._session(runner, config={"dtmf": {"enabled": False}})
        await s.start()
        await s.on_message(_start())
        await s.on_message(_dtmf("1"))
        await s.on_message(_dtmf("#"))
        await asyncio.sleep(0.02)
        assert digits == []
