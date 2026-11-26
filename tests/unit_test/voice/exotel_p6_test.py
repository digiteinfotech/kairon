"""Exotel call lifecycle: hangup, silence handling, max duration, chat history, status tracking."""
import asyncio
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kairon.exceptions import AppException


async def _until(predicate, timeout=2.0):
    """Wait (without a fixed sleep) until ``predicate()`` is true; fail the test if it never is."""
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        assert asyncio.get_running_loop().time() < deadline, "condition not reached in time"
        await asyncio.sleep(0.005)


@pytest.fixture(autouse=True, scope="module")
def _load_env():
    os.environ["system_file"] = "./tests/testing_data/system.yaml"
    from kairon.shared.utils import Utility
    Utility.load_environment()
    Utility.load_system_metadata()
    from mongoengine import connect, disconnect
    connect(**Utility.mongoengine_connection(Utility.environment["database"]["url"]))
    yield
    disconnect()


class _T:
    def __init__(self, text, is_final):
        self.text, self.is_final, self.confidence = text, is_final, None


class _QueueSTT:
    def __init__(self):
        self.closed = False
        self.pushed = []
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


class _TTS:
    def __init__(self):
        self.spoken = []

    async def synthesize(self, text):
        self.spoken.append(text)
        yield b"\x01\x02" * 200


def _frame(event, **kw):
    return json.dumps({"event": event, "stream_sid": "S", **kw})


def _start(call="CALL1"):
    return _frame("start", start={"call_sid": call, "from": "+91111", "to": "0800",
                                  "media_format": {"sample_rate": "8000"}})


def _mark_ack(session):
    return _frame("mark", mark={"name": session._last_mark})


class _Harness:
    """A session with fakes plus everything it reports back."""

    def __init__(self, config=None, runner=None, welcome="Hello there", context=None, record_error=None):
        from kairon.shared.voice.exotel.session import AgentTurn, ExotelCallSession
        self.sent, self.recorded, self.ended, self.hangups = [], [], [], []

        async def sender(frame):
            self.sent.append(frame)

        async def on_hangup():
            self.hangups.append(True)

        async def recorder(sender_id, messages, slots, metadata):
            if record_error:
                raise record_error
            self.recorded.append((sender_id, list(messages), slots))

        async def loader(call_sid):
            return context or {}

        async def call_end(call_sid, reason, duration):
            self.ended.append((call_sid, reason, duration))

        async def default_runner(text, sid, meta):
            if text == "noinput":
                return AgentTurn(messages=[])
            return AgentTurn(messages=[f"you said {text}"])

        self.stt, self.tts = _QueueSTT(), _TTS()
        self.metrics = MagicMock()
        self.session = ExotelCallSession(
            bot="b", config=config or {}, sender=sender, stt=self.stt, tts=self.tts,
            agent_runner=runner or default_runner, pace=False, welcome_message=welcome,
            on_hangup=on_hangup, history_recorder=recorder, call_context_loader=loader,
            on_call_end=call_end, metrics=self.metrics,
        )
        self.AgentTurn = AgentTurn

    async def begin(self):
        await self.session.start()
        await self.session.on_message(_start())
        await asyncio.sleep(0.02)

    async def ack(self):
        await self.session.on_message(_mark_ack(self.session))


class TestHangup:

    @pytest.mark.asyncio
    async def test_bot_disconnect_plays_goodbye_then_closes_websocket(self):
        async def runner(text, sid, meta):
            return h.AgentTurn(messages=["Goodbye!"], hangup=True)

        h = _Harness(runner=runner, welcome=None)
        await h.begin()
        await h.stt.feed(_T("bye", True))
        await asyncio.sleep(0.05)
        assert h.tts.spoken == ["Goodbye!"]
        assert h.hangups == [] and not h.session.closed
        await h.ack()
        await asyncio.sleep(0.05)
        assert h.hangups == [True]
        assert h.session.closed and h.stt.closed
        assert h.ended and h.ended[0][:2] == ("CALL1", "bot_disconnect")

    @pytest.mark.asyncio
    async def test_hangup_does_not_cancel_itself_and_still_finalizes_metrics(self):
        """Regression: close() used to cancel the task that was running the hangup, so metrics were never saved."""
        async def runner(text, sid, meta):
            return h.AgentTurn(messages=["Bye"], hangup=True)

        h = _Harness(runner=runner, welcome=None)
        await h.begin()
        await h.stt.feed(_T("bye", True))
        await asyncio.sleep(0.05)
        await h.ack()
        await asyncio.sleep(0.05)
        h.metrics.finalize.assert_called_once()
        assert len(h.ended) == 1

    @pytest.mark.asyncio
    async def test_hangup_still_happens_if_playback_ack_never_arrives(self):
        async def runner(text, sid, meta):
            return h.AgentTurn(messages=["Bye"], hangup=True)

        h = _Harness(runner=runner, welcome=None)
        with patch("kairon.shared.voice.exotel.session.PLAYBACK_WAIT_SECONDS", 0.05):
            await h.begin()
            await h.stt.feed(_T("bye", True))
            await asyncio.sleep(0.3)
        assert h.hangups == [True] and h.session.closed

    @pytest.mark.asyncio
    async def test_hangup_without_callback_just_closes(self):
        from kairon.shared.voice.exotel.session import AgentTurn, ExotelCallSession

        async def runner(text, sid, meta):
            return AgentTurn(messages=[], hangup=True)

        s = ExotelCallSession(bot="b", config={}, sender=AsyncMock(), stt=_QueueSTT(), tts=_TTS(),
                              agent_runner=runner, pace=False, welcome_message=None)
        await s.start()
        await s.on_message(_start())
        await s.stt.feed(_T("bye", True))
        await asyncio.sleep(0.05)
        assert s.closed

    @pytest.mark.asyncio
    async def test_hangup_callback_error_is_swallowed(self):
        async def runner(text, sid, meta):
            return h.AgentTurn(messages=[], hangup=True)

        h = _Harness(runner=runner, welcome=None)
        h.session._on_hangup = AsyncMock(side_effect=RuntimeError("socket gone"))
        await h.begin()
        await h.stt.feed(_T("bye", True))
        await asyncio.sleep(0.05)
        assert h.session.closed

    @pytest.mark.asyncio
    async def test_caller_hangup_reports_caller_hangup(self):
        h = _Harness(welcome=None)
        await h.begin()
        await h.session.on_message(_frame("stop", stop={"call_sid": "CALL1"}))
        await asyncio.sleep(0.02)
        assert h.session.closed
        assert h.ended[0][:2] == ("CALL1", "caller_hangup") and h.ended[0][2] >= 0

    @pytest.mark.asyncio
    async def test_close_is_idempotent_and_reports_once(self):
        h = _Harness(welcome=None)
        await h.begin()
        await h.session.close()
        await h.session.close()
        assert len(h.ended) == 1

    @pytest.mark.asyncio
    async def test_hangup_after_close_does_nothing(self):
        h = _Harness(welcome=None)
        await h.begin()
        await h.session.close()
        await h.session._hangup("bot_disconnect")
        assert h.hangups == [] and h.ended[0][1] == "caller_hangup"

    @pytest.mark.asyncio
    async def test_call_end_callback_error_is_swallowed(self):
        h = _Harness(welcome=None)
        h.session._on_call_end = AsyncMock(side_effect=RuntimeError("db down"))
        await h.begin()
        await h.session.close()
        assert h.session.closed


class TestSpeechIsSerialised:

    @pytest.mark.asyncio
    async def test_concurrent_utterances_never_interleave(self):
        """A reprompt, the max-duration goodbye and an agent reply can fire together: audio must stay in order."""
        h = _Harness(welcome=None)
        order = []

        async def slow_stream(text):
            order.append(("start", text))
            await asyncio.sleep(0.05)
            order.append(("end", text))
            return False

        h.session._stream_tts = slow_stream
        await asyncio.gather(h.session._speak(["one"]), h.session._speak(["two"]), h.session._speak(["three", "four"]))
        for i in range(0, len(order), 2):
            assert order[i][0] == "start" and order[i + 1] == ("end", order[i][1])
        assert sorted(t for k, t in order if k == "start") == ["four", "one", "three", "two"]


class TestSilenceHandling:

    def _cfg(self, **kw):
        return {"noinput_timeout_seconds": 0.05, "max_noinput_attempts": 1, **kw}

    @pytest.mark.asyncio
    async def test_silence_after_welcome_reprompts_with_fallback_phrase(self):
        h = _Harness(config=self._cfg(max_noinput_attempts=5))
        await h.begin()
        await asyncio.sleep(0.12)
        assert h.tts.spoken[0] == "Hello there"
        assert h.tts.spoken[1] == "I'm sorry, I didn't get that. Could you please repeat?"

    @pytest.mark.asyncio
    async def test_reprompt_repeats_last_bot_message(self):
        h = _Harness(config=self._cfg(max_noinput_attempts=5))
        await h.begin()
        await h.stt.feed(_T("order status", True))
        await asyncio.sleep(0.03)
        assert h.tts.spoken[-1] == "you said order status"
        await asyncio.sleep(0.09)
        assert h.tts.spoken.count("you said order status") >= 2

    @pytest.mark.asyncio
    async def test_second_silence_says_goodbye_and_hangs_up(self):
        h = _Harness(config=self._cfg(timeout_message="Thanks for calling. Bye."))
        await h.begin()
        await asyncio.sleep(0.25)
        await h.ack()
        await asyncio.sleep(0.05)
        assert "Thanks for calling. Bye." in h.tts.spoken
        assert h.hangups == [True] and h.session.closed
        assert h.ended[0][1] == "noinput_timeout"

    @pytest.mark.asyncio
    async def test_default_goodbye_message(self):
        from kairon.shared.voice.constants import DEFAULT_TIMEOUT_MESSAGE
        h = _Harness(config=self._cfg(max_noinput_attempts=0))
        await h.begin()
        await asyncio.sleep(0.12)
        assert h.tts.spoken[-1] == DEFAULT_TIMEOUT_MESSAGE

    @pytest.mark.asyncio
    async def test_caller_speaking_resets_the_silence_count(self):
        h = _Harness(config=self._cfg(noinput_timeout_seconds=0.3))
        await h.begin()
        await _until(lambda: h.session._noinput_count == 1)
        await h.stt.feed(_T("hello", True))
        await _until(lambda: h.session._noinput_count == 0)
        assert not h.session.closed

    @pytest.mark.asyncio
    async def test_partial_speech_restarts_the_countdown(self):
        h = _Harness(config={"noinput_timeout_seconds": 0.15})
        await h.begin()
        for _ in range(4):
            await asyncio.sleep(0.07)
            await h.stt.feed(_T("hmm", False))
        assert h.tts.spoken == ["Hello there"]

    @pytest.mark.asyncio
    async def test_empty_partial_does_not_restart_countdown(self):
        h = _Harness(config=self._cfg(max_noinput_attempts=5))
        await h.begin()
        await h.stt.feed(_T("", False))
        await h.stt.feed(_T("   ", True))
        await asyncio.sleep(0.12)
        assert len(h.tts.spoken) >= 2

    @pytest.mark.asyncio
    async def test_dtmf_counts_as_caller_activity(self):
        h = _Harness(config={"noinput_timeout_seconds": 0.12})
        await h.begin()
        await asyncio.sleep(0.07)
        await h.session.on_message(_frame("dtmf", dtmf={"digit": "5"}))
        await asyncio.sleep(0.09)
        assert h.tts.spoken == ["Hello there"]

    @pytest.mark.asyncio
    async def test_timeout_zero_disables_silence_handling(self):
        h = _Harness(config={"noinput_timeout_seconds": 0})
        await h.begin()
        await asyncio.sleep(0.15)
        assert h.tts.spoken == ["Hello there"] and not h.session.closed

    @pytest.mark.asyncio
    async def test_silence_is_sent_to_the_agent_as_a_noinput_turn(self):
        seen = []

        async def runner(text, sid, meta):
            seen.append(text)
            return h.AgentTurn(messages=["Are you still there?"])

        h = _Harness(runner=runner, config=self._cfg(max_noinput_attempts=5))
        await h.begin()
        await asyncio.sleep(0.12)
        assert seen[0] == "noinput"
        assert "Are you still there?" in h.tts.spoken
        assert h.session._last_agent_message == "Are you still there?"

    @pytest.mark.asyncio
    async def test_agent_can_hang_up_on_noinput(self):
        async def runner(text, sid, meta):
            return h.AgentTurn(messages=["Goodbye then"], hangup=True)

        h = _Harness(runner=runner, config=self._cfg(max_noinput_attempts=5))
        await h.begin()
        await asyncio.sleep(0.12)
        await h.ack()
        await asyncio.sleep(0.05)
        assert "Goodbye then" in h.tts.spoken
        assert h.session.closed and h.ended[0][1] == "bot_disconnect"

    @pytest.mark.asyncio
    async def test_agent_hangup_without_message_uses_timeout_message(self):
        async def runner(text, sid, meta):
            return h.AgentTurn(messages=[], hangup=True)

        h = _Harness(runner=runner, config=self._cfg(max_noinput_attempts=5, timeout_message="Bye now"))
        await h.begin()
        await asyncio.sleep(0.12)
        await h.ack()
        await asyncio.sleep(0.05)
        assert "Bye now" in h.tts.spoken and h.session.closed

    @pytest.mark.asyncio
    async def test_failed_noinput_turn_falls_back_to_reprompt(self):
        async def runner(text, sid, meta):
            raise RuntimeError("agent down")

        h = _Harness(runner=runner, config=self._cfg(max_noinput_attempts=5))
        await h.begin()
        await asyncio.sleep(0.12)
        assert h.tts.spoken[1] == "I'm sorry, I didn't get that. Could you please repeat?"
        assert not h.session.closed

    @pytest.mark.asyncio
    async def test_call_closed_during_noinput_turn_says_nothing(self):
        async def runner(text, sid, meta):
            await h.session.close()
            return h.AgentTurn(messages=["late"])

        h = _Harness(runner=runner, config=self._cfg(max_noinput_attempts=5))
        await h.begin()
        await asyncio.sleep(0.12)
        assert h.tts.spoken == ["Hello there"]

    @pytest.mark.asyncio
    async def test_terminator_only_dtmf_does_not_disable_silence_handling(self):
        h = _Harness(config=self._cfg(timeout_message="Bye."))
        await h.begin()
        await h.session.on_message(_frame("dtmf", dtmf={"digit": "#"}))
        await asyncio.sleep(0.3)
        await h.ack()
        await asyncio.sleep(0.05)
        assert "Bye." in h.tts.spoken and h.session.closed
        assert h.ended[0][1] == "noinput_timeout"

    @pytest.mark.asyncio
    async def test_partial_dtmf_entry_is_abandoned_on_silence(self):
        h = _Harness(config=self._cfg(timeout_message="Bye."))
        await h.begin()
        await h.session.on_message(_frame("dtmf", dtmf={"digit": "5"}))
        await asyncio.sleep(0.3)
        await h.ack()
        await asyncio.sleep(0.05)
        assert h.session._dtmf_buffer == "" and h.session.closed

    @pytest.mark.asyncio
    async def test_timeout_farewell_is_recorded_in_history(self):
        h = _Harness(config=self._cfg(timeout_message="Bye."))
        await h.begin()
        await asyncio.sleep(0.25)
        await h.ack()
        assert any(["Bye."] == msgs for _, msgs, _ in h.recorded)

    @pytest.mark.asyncio
    async def test_agent_hangup_fallback_farewell_is_recorded(self):
        async def runner(text, sid, meta):
            return h.AgentTurn(messages=[], hangup=True)

        h = _Harness(runner=runner, config=self._cfg(max_noinput_attempts=5, timeout_message="Bye now"))
        await h.begin()
        await asyncio.sleep(0.12)
        await h.ack()
        assert any(["Bye now"] == msgs for _, msgs, _ in h.recorded)

    @pytest.mark.asyncio
    async def test_no_reprompt_after_call_closed(self):
        h = _Harness(config=self._cfg())
        await h.begin()
        await h.session.close()
        await h.session._on_noinput()
        assert h.tts.spoken == ["Hello there"]

    @pytest.mark.asyncio
    async def test_bad_config_values_fall_back_to_defaults(self):
        from kairon.shared.voice.exotel.session import DEFAULT_NOINPUT_TIMEOUT_SECONDS, DEFAULT_MAX_NOINPUT_ATTEMPTS
        h = _Harness(config={"noinput_timeout_seconds": "abc", "max_noinput_attempts": -3, "max_call_duration_seconds": "x"})
        assert h.session.noinput_timeout == DEFAULT_NOINPUT_TIMEOUT_SECONDS
        assert h.session.max_noinput_attempts == DEFAULT_MAX_NOINPUT_ATTEMPTS
        assert h.session.max_call_duration == 0.0


class TestSessionRaces:
    """Timers and flags that used to interleave badly: each test pins one race."""

    @pytest.mark.asyncio
    async def test_dtmf_after_close_or_while_ending_is_ignored(self):
        h = _Harness(welcome=None, config={"dtmf": {"inter_digit_timeout": 5}})
        await h.begin()
        h.session._ending = True
        await h.session.on_message(_frame("dtmf", dtmf={"digit": "5"}))
        assert h.session._dtmf_buffer == "" and h.session._dtmf_timer is None
        h.session._ending = False
        await h.session.close()
        await h.session.on_message(_frame("dtmf", dtmf={"digit": "5"}))
        assert h.session._dtmf_buffer == "" and h.session._dtmf_timer is None

    @pytest.mark.asyncio
    async def test_keypad_turn_does_not_block_the_receive_loop(self):
        async def runner(text, sid, meta):
            await asyncio.sleep(0.3)
            return h.AgentTurn(messages=["done"])

        h = _Harness(runner=runner, welcome=None, config={"noinput_timeout_seconds": 0})
        await h.begin()
        await h.session.on_message(_frame("dtmf", dtmf={"digit": "5"}))
        started = asyncio.get_event_loop().time()
        await h.session.on_message(_frame("dtmf", dtmf={"digit": "#"}))
        assert asyncio.get_event_loop().time() - started < 0.1
        await h.session.on_message(_frame("stop", stop={"call_sid": "CALL1"}))
        assert h.session.closed
        await asyncio.sleep(0.05)
        assert "done" not in h.tts.spoken

    @pytest.mark.asyncio
    async def test_welcome_does_not_block_the_receive_loop(self):
        h = _Harness(config={"noinput_timeout_seconds": 0})

        async def slow_stream(text):
            await asyncio.sleep(0.3)
            return False

        h.session._stream_tts = slow_stream
        await h.session.start()
        started = asyncio.get_event_loop().time()
        await h.session.on_message(_start())
        assert asyncio.get_event_loop().time() - started < 0.1
        await h.session.on_message(_frame("stop", stop={"call_sid": "CALL1"}))
        assert h.session.closed

    @pytest.mark.asyncio
    async def test_keypad_and_spoken_turns_never_run_the_agent_together(self):
        running, peak = [0], [0]

        async def runner(text, sid, meta):
            running[0] += 1
            peak[0] = max(peak[0], running[0])
            await asyncio.sleep(0.1)
            running[0] -= 1
            return h.AgentTurn(messages=[f"re {text}"])

        h = _Harness(runner=runner, welcome=None, config={"noinput_timeout_seconds": 0})
        await h.begin()
        await h.stt.feed(_T("hello", True))
        await asyncio.sleep(0.02)
        await h.session.on_message(_frame("dtmf", dtmf={"digit": "5"}))
        await h.session.on_message(_frame("dtmf", dtmf={"digit": "#"}))
        await asyncio.sleep(0.4)
        assert peak[0] == 1
        assert [t for t in h.tts.spoken if t.startswith("re ")] == ["re hello", "re 5"]

    @pytest.mark.asyncio
    async def test_silence_countdown_never_fires_during_an_agent_turn(self):
        seen = []

        async def runner(text, sid, meta):
            seen.append(text)
            await asyncio.sleep(0.4)
            return h.AgentTurn(messages=["slow reply"])

        h = _Harness(runner=runner, welcome=None, config={"noinput_timeout_seconds": 0.05, "max_noinput_attempts": 5})
        await h.begin()
        await h.stt.feed(_T("hello", True))
        await asyncio.sleep(0.05)
        await h.session.on_message(_frame("dtmf", dtmf={"digit": "5"}))
        await asyncio.sleep(0.25)
        assert seen == ["hello"]

    @pytest.mark.asyncio
    async def test_two_closing_requests_play_one_goodbye(self):
        h = _Harness(welcome=None, config={"noinput_timeout_seconds": 0})
        await h.begin()
        await asyncio.gather(h.session._say_and_hangup(["first bye"], "max_duration"),
                             h.session._say_and_hangup(["second bye"], "noinput_timeout"))
        await h.ack()
        assert h.tts.spoken.count("first bye") + h.tts.spoken.count("second bye") == 1
        assert [m for _, m, _ in h.recorded if m] == [["first bye"]]

    @pytest.mark.asyncio
    async def test_reprompt_cut_off_by_the_goodbye_is_not_recorded(self):
        h = _Harness(welcome=None, config={"noinput_timeout_seconds": 0, "max_noinput_attempts": 5})
        await h.begin()

        async def cut_off(messages, final=False):
            h.session._ending = True
            return False

        h.session._speak = cut_off
        await h.session._on_noinput()
        assert h.recorded == []

    @pytest.mark.asyncio
    async def test_close_cancels_pending_keypad_and_welcome_tasks(self):
        async def runner(text, sid, meta):
            await asyncio.sleep(5)
            return h.AgentTurn(messages=["x"])

        h = _Harness(runner=runner, welcome=None, config={"noinput_timeout_seconds": 0})
        await h.begin()
        await h.session.on_message(_frame("dtmf", dtmf={"digit": "5"}))
        await h.session.on_message(_frame("dtmf", dtmf={"digit": "#"}))
        await asyncio.sleep(0.05)
        pending = list(h.session._turn_tasks)
        assert pending
        await h.session.close()
        await asyncio.sleep(0.02)
        assert all(t.done() for t in pending) and h.session._greet_task is None


class TestMaxCallDuration:

    @pytest.mark.asyncio
    async def test_cap_timer_starts_before_the_welcome_plays(self):
        h = _Harness(config={"max_call_duration_seconds": 5, "noinput_timeout_seconds": 0})
        seen = []

        async def slow_stream(text):
            seen.append(h.session._max_duration_task is not None)
            await asyncio.sleep(0.05)
            return False

        h.session._stream_tts = slow_stream
        await h.begin()
        assert seen == [True]

    @pytest.mark.asyncio
    async def test_reply_finishing_after_the_goodbye_is_not_played(self):
        async def runner(text, sid, meta):
            await asyncio.sleep(0.25)
            return h.AgentTurn(messages=["late reply"])

        h = _Harness(runner=runner, config={"max_call_duration_seconds": 0.08, "noinput_timeout_seconds": 0,
                                            "max_duration_message": "Time is up."})
        await h.begin()
        await h.stt.feed(_T("hello", True))
        await asyncio.sleep(0.4)
        await h.ack()
        assert "Time is up." in h.tts.spoken and "late reply" not in h.tts.spoken

    @pytest.mark.asyncio
    async def test_queued_reply_messages_are_dropped_once_the_call_is_ending(self):
        h = _Harness(welcome=None)
        await h.begin()
        h.session._ending = True
        assert await h.session._speak(["reply"]) is False
        assert "reply" not in h.tts.spoken
        await h.session._speak(["farewell"], final=True)
        assert "farewell" in h.tts.spoken

    def test_runtime_clamps_duration_and_survives_bad_dtmf_length(self):
        from kairon.shared.voice.constants import MAX_CALL_DURATION_LIMIT_SECONDS
        h = _Harness(config={"max_call_duration_seconds": 999999, "dtmf": {"max_length": "abc"}})
        assert h.session.max_call_duration == MAX_CALL_DURATION_LIMIT_SECONDS
        assert h.session.dtmf_max_length == 32

    @pytest.mark.asyncio
    async def test_call_is_ended_politely_at_the_limit(self):
        h = _Harness(config={"max_call_duration_seconds": 0.08, "noinput_timeout_seconds": 0,
                             "max_duration_message": "Time is up. Goodbye."})
        await h.begin()
        await asyncio.sleep(0.2)
        await h.ack()
        await asyncio.sleep(0.05)
        assert h.tts.spoken[-1] == "Time is up. Goodbye."
        assert h.hangups == [True] and h.ended[0][1] == "max_duration"

    @pytest.mark.asyncio
    async def test_default_max_duration_message(self):
        from kairon.shared.voice.constants import DEFAULT_MAX_DURATION_MESSAGE
        h = _Harness(config={"max_call_duration_seconds": 0.05, "noinput_timeout_seconds": 0})
        await h.begin()
        await asyncio.sleep(0.15)
        assert h.tts.spoken[-1] == DEFAULT_MAX_DURATION_MESSAGE

    @pytest.mark.asyncio
    async def test_no_limit_by_default(self):
        h = _Harness(config={"noinput_timeout_seconds": 0})
        await h.begin()
        assert h.session.max_call_duration == 0 and h.session._max_duration_task is None

    @pytest.mark.asyncio
    async def test_limit_does_not_fire_after_call_already_ended(self):
        h = _Harness(config={"max_call_duration_seconds": 0.1, "noinput_timeout_seconds": 0})
        await h.begin()
        await h.session.close()
        await asyncio.sleep(0.2)
        assert h.tts.spoken == ["Hello there"] and len(h.ended) == 1


class TestCallHistory:

    @pytest.mark.asyncio
    async def test_welcome_and_carried_slots_recorded_at_call_start(self):
        h = _Harness(context={"slots": {"customer_name": "Asha"}})
        await h.begin()
        assert h.recorded[0] == ("CALL1", ["Hello there"], {"customer_name": "Asha"})

    @pytest.mark.asyncio
    async def test_no_welcome_and_no_slots_records_nothing(self):
        h = _Harness(welcome=None)
        await h.begin()
        assert h.recorded == []

    @pytest.mark.asyncio
    async def test_first_caller_turn_waits_for_history_to_be_seeded(self):
        order = []
        release = asyncio.Event()

        async def runner(text, sid, meta):
            order.append("agent")
            return h.AgentTurn(messages=["ok"])

        h = _Harness(runner=runner)

        async def slow_recorder(sender_id, messages, slots, metadata):
            await release.wait()
            order.append("history")

        h.session._history_recorder = slow_recorder
        await h.begin()
        await h.stt.feed(_T("hi", True))
        await asyncio.sleep(0.05)
        assert order == []
        release.set()
        await asyncio.sleep(0.05)
        assert order == ["history", "agent"]

    @pytest.mark.asyncio
    async def test_reprompt_and_goodbye_are_recorded(self):
        h = _Harness(config={"noinput_timeout_seconds": 0.05, "max_noinput_attempts": 1})
        await h.begin()
        await asyncio.sleep(0.2)
        spoken = [m for _, msgs, _ in h.recorded for m in msgs]
        assert "Hello there" in spoken
        assert "I'm sorry, I didn't get that. Could you please repeat?" in spoken
        assert "We didn't hear from you. Thanks for your time. Goodbye." in spoken

    @pytest.mark.asyncio
    async def test_recorder_failure_never_breaks_the_call(self):
        h = _Harness(record_error=RuntimeError("mongo down"))
        await h.begin()
        await h.stt.feed(_T("hi", True))
        await asyncio.sleep(0.05)
        assert "you said hi" in h.tts.spoken and not h.session.closed

    @pytest.mark.asyncio
    async def test_context_loader_failure_still_records_welcome(self):
        h = _Harness()
        h.session._call_context_loader = AsyncMock(side_effect=RuntimeError("db"))
        await h.begin()
        assert h.recorded[0][1] == ["Hello there"] and h.recorded[0][2] is None

    @pytest.mark.asyncio
    async def test_bootstrap_failure_does_not_block_turns(self):
        h = _Harness()
        h.session._bootstrap_task = asyncio.ensure_future(asyncio.sleep(0))
        h.session._bootstrap_task.cancel()
        await h.begin()
        await h.stt.feed(_T("hi", True))
        await asyncio.sleep(0.05)
        assert "you said hi" in h.tts.spoken


class TestCallTracking:

    def _row(self, sid, status="initiated", initiator="bot", data=None):
        from kairon.shared.chat.data_objects import ChannelLogs
        return ChannelLogs(type="voice", status=status, message_id=sid, bot="bt", user="u",
                           initiator=initiator, data=data or {}).save()

    @pytest.fixture(autouse=True)
    def _clean(self):
        from kairon.shared.chat.data_objects import ChannelLogs
        ChannelLogs.objects(bot="bt").delete()
        yield
        ChannelLogs.objects(bot="bt").delete()

    def test_outbound_row_goes_initiated_answered_completed(self):
        from kairon.shared.chat.data_objects import ChannelLogs
        from kairon.shared.voice import constants as vc
        from kairon.shared.voice.utils import VoiceUtils
        self._row("S1")
        assert VoiceUtils.update_call_status("bt", "S1", vc.CallStatus.ANSWERED.value) == 1
        assert ChannelLogs.objects(bot="bt", message_id="S1").get().status == "answered"
        assert VoiceUtils.finish_call("bt", "S1", vc.CallEndReason.BOT_DISCONNECT.value, 12.34) == 1
        row = ChannelLogs.objects(bot="bt", message_id="S1").get()
        assert row.status == "completed"
        assert row.data["end_reason"] == "bot_disconnect" and row.data["duration_s"] == 12.3

    def test_error_end_marks_failed(self):
        from kairon.shared.chat.data_objects import ChannelLogs
        from kairon.shared.voice import constants as vc
        from kairon.shared.voice.utils import VoiceUtils
        self._row("S2")
        VoiceUtils.finish_call("bt", "S2", vc.CallEndReason.ERROR.value)
        row = ChannelLogs.objects(bot="bt", message_id="S2").get()
        assert row.status == "failed" and "duration_s" not in row.data

    def test_inbound_call_uses_its_resolver_row(self):
        from kairon.shared.chat.data_objects import ChannelLogs
        from kairon.shared.voice import constants as vc
        from kairon.shared.voice.utils import VoiceUtils
        self._row("S3", status="resolver", initiator=None, data={"Direction": "incoming"})
        assert VoiceUtils.finish_call("bt", "S3", vc.CallEndReason.CALLER_HANGUP.value, 5) == 1
        row = ChannelLogs.objects(bot="bt", message_id="S3").get()
        assert row.status == "completed" and row.data["Direction"] == "incoming"

    @pytest.mark.parametrize("stored", ["answered", "completed", "failed"])
    def test_inbound_row_is_found_in_every_state_it_goes_through(self, stored):
        """Regression: the resolver marks an inbound row ``answered``; ending the call must still find it."""
        from kairon.shared.voice.utils import VoiceUtils
        self._row(f"S-{stored}", status=stored, initiator=None)
        assert VoiceUtils.find_call_row("bt", f"S-{stored}") is not None

    def test_inbound_call_ends_as_completed_after_the_resolver_answered_it(self):
        from kairon.shared.chat.data_objects import ChannelLogs
        from kairon.shared.voice import constants as vc
        from kairon.shared.voice.utils import VoiceUtils
        self._row("S-in", status="resolver", initiator=None)
        VoiceUtils.update_call_status("bt", "S-in", vc.CallStatus.ANSWERED.value, only_if_not_terminal=True)
        assert VoiceUtils.finish_call("bt", "S-in", vc.CallEndReason.NOINPUT_TIMEOUT.value, 20) == 1
        row = ChannelLogs.objects(bot="bt", message_id="S-in").get()
        assert row.status == "completed" and row.data["end_reason"] == "noinput_timeout"

    def test_outbound_row_preferred_over_resolver_row(self):
        from kairon.shared.chat.data_objects import ChannelLogs
        from kairon.shared.voice import constants as vc
        from kairon.shared.voice.utils import VoiceUtils
        self._row("S4")
        self._row("S4", status="resolver", initiator=None)
        VoiceUtils.update_call_status("bt", "S4", vc.CallStatus.ANSWERED.value)
        assert ChannelLogs.objects(bot="bt", message_id="S4", initiator="bot").get().status == "answered"
        assert ChannelLogs.objects(bot="bt", message_id="S4", status="resolver").count() == 1

    def test_unknown_call_and_blank_sid_update_nothing(self):
        from kairon.shared.voice.utils import VoiceUtils
        assert VoiceUtils.update_call_status("bt", "NOPE", "answered") == 0
        assert VoiceUtils.update_call_status("bt", "", "answered") == 0

    def test_terminal_call_is_not_overwritten_when_asked_not_to(self):
        from kairon.shared.chat.data_objects import ChannelLogs
        from kairon.shared.voice import constants as vc
        from kairon.shared.voice.utils import VoiceUtils
        self._row("S5")
        VoiceUtils.finish_call("bt", "S5", vc.CallEndReason.NOINPUT_TIMEOUT.value)
        assert VoiceUtils.update_call_status("bt", "S5", vc.CallStatus.ANSWERED.value, only_if_not_terminal=True) == 0
        assert ChannelLogs.objects(bot="bt", message_id="S5").get().status == "completed"

    def test_terminal_guard_is_atomic_when_row_went_terminal_after_the_read(self):
        from kairon.shared.chat.data_objects import ChannelLogs
        from kairon.shared.voice import constants as vc
        from kairon.shared.voice.utils import VoiceUtils
        stale = self._row("S5b")
        ChannelLogs.objects(id=stale.id).update(set__status="completed")
        with patch.object(VoiceUtils, "find_call_row", return_value=stale):
            assert VoiceUtils.update_call_status(
                "bt", "S5b", vc.CallStatus.FAILED.value, only_if_not_terminal=True) == 0
        assert ChannelLogs.objects(bot="bt", message_id="S5b").get().status == "completed"

    @pytest.mark.parametrize("provider,expected", [
        ("busy", "busy"), ("no-answer", "no-answer"), ("No_Answer", "no-answer"), ("failed", "failed"),
        ("canceled", "canceled"), ("cancelled", "canceled"), ("completed", "completed")])
    def test_provider_status_callback_for_unanswered_calls(self, provider, expected):
        from kairon.shared.chat.data_objects import ChannelLogs
        from kairon.shared.voice.utils import VoiceUtils
        self._row("S6")
        assert VoiceUtils.apply_provider_status("bt", "S6", provider, {"Duration": "0", "Other": "x"}) == 1
        row = ChannelLogs.objects(bot="bt", message_id="S6").get()
        assert row.status == expected and row.data["provider_status"] == provider
        assert row.data["provider_Duration"] == "0" and "provider_Other" not in row.data

    def test_provider_completed_does_not_overwrite_our_end_reason(self):
        from kairon.shared.chat.data_objects import ChannelLogs
        from kairon.shared.voice import constants as vc
        from kairon.shared.voice.utils import VoiceUtils
        self._row("S7")
        VoiceUtils.finish_call("bt", "S7", vc.CallEndReason.MAX_DURATION.value, 60)
        assert VoiceUtils.apply_provider_status("bt", "S7", "completed") == 0
        assert ChannelLogs.objects(bot="bt", message_id="S7").get().data["end_reason"] == "max_duration"

    def test_unknown_provider_status_ignored(self):
        from kairon.shared.voice.utils import VoiceUtils
        self._row("S8")
        assert VoiceUtils.apply_provider_status("bt", "S8", "ringing-ish") == 0
        assert VoiceUtils.apply_provider_status("bt", "S8", None) == 0

    def test_tracking_errors_never_raise(self):
        from kairon.shared.voice import utils as vu
        from kairon.shared.voice.utils import VoiceUtils
        with patch.object(vu.ChannelLogs, "objects", side_effect=RuntimeError("db down")):
            assert VoiceUtils.update_call_status("bt", "S9", "answered") == 0
            assert VoiceUtils.load_call_context("bt", "S9") == {}

    def test_call_context_roundtrip(self):
        from kairon.shared.voice.utils import VoiceUtils
        self._row("S10", data={"slots": {"order_id": "A1"}, "origin_sender_id": "chat-user"})
        assert VoiceUtils.load_call_context("bt", "S10") == {"slots": {"order_id": "A1"}, "origin_sender_id": "chat-user"}
        assert VoiceUtils.load_call_context("bt", "UNKNOWN") == {"slots": {}, "origin_sender_id": None}
        assert VoiceUtils.load_call_context("bt", "") == {}

    def test_carry_over_skips_system_empty_and_oversized_slots(self):
        from kairon.shared.voice.utils import VoiceUtils
        picked = VoiceUtils.select_carry_over_slots({
            "customer_name": "Asha", "order": {"id": 7}, "bot": "b1", "session_started_metadata": {"x": 1},
            "kairon_action_response": "x", "empty": "", "nothing": None, "list": [], "requested_slot": "x",
            "huge": "y" * 5000, "number": 42,
        })
        assert picked == {"customer_name": "Asha", "number": 42}

    def test_carry_over_makes_values_json_safe(self):
        import datetime
        from kairon.shared.voice.utils import VoiceUtils
        picked = VoiceUtils.select_carry_over_slots({"when": datetime.date(2026, 1, 2), "tags": ["a", "b"]})
        assert picked == {"when": "2026-01-02", "tags": ["a", "b"]}
        assert VoiceUtils.select_carry_over_slots(None) == {}

    def test_carry_over_drops_unserialisable_values(self):
        from kairon.shared.voice.utils import VoiceUtils

        class Bad:
            def __str__(self):
                raise RuntimeError("no")
        assert VoiceUtils.select_carry_over_slots({"bad": Bad(), "ok": 1}) == {"ok": 1}


def _handler_for_history():
    from kairon.chat.handlers.channels.clients.voice.exotel_stream import ExotelStreamHandler
    return ExotelStreamHandler(bot="b1", provider="exotel", token="T", websocket=MagicMock())


class TestRecordCallMessages:

    def _processor(self, known=("customer_name",), events=None):
        tracker = MagicMock()
        tracker.update = MagicMock(side_effect=lambda e: events.append(e) if events is not None else None)
        proc = MagicMock()
        proc.fetch_tracker_with_initial_session = AsyncMock(return_value=tracker)
        proc.save_tracker = AsyncMock()
        proc.domain.slots = [MagicMock(**{"name": n}) for n in known]
        for slot, n in zip(proc.domain.slots, known):
            slot.name = n
        return proc, tracker

    @pytest.mark.asyncio
    async def test_records_slots_and_bot_messages_in_order_then_saves(self):
        from rasa.shared.core.events import BotUttered, SlotSet
        events = []
        proc, tracker = self._processor(events=events)
        with patch("kairon.chat.handlers.channels.clients.voice.exotel_stream.AgentProcessor.get_agent",
                   return_value=MagicMock(processor=proc)):
            await _handler_for_history()._record_call_messages(
                "CALL1", ["Hello", "  ", "", "Welcome"],
                {"customer_name": "Asha", "not_in_domain": "x"}, {"channel_type": "voice"})
        proc.fetch_tracker_with_initial_session.assert_awaited_once_with("CALL1", None, {"channel_type": "voice"})
        assert [type(e) for e in events] == [SlotSet, BotUttered, BotUttered]
        assert (events[0].key, events[0].value) == ("customer_name", "Asha")
        assert [e.text for e in events[1:]] == ["Hello", "Welcome"]
        assert events[1].metadata == {"channel": "voice", "source": "voice_session"}
        proc.save_tracker.assert_awaited_once_with(tracker)

    @pytest.mark.asyncio
    async def test_no_slots_no_messages_still_starts_the_session(self):
        proc, tracker = self._processor()
        with patch("kairon.chat.handlers.channels.clients.voice.exotel_stream.AgentProcessor.get_agent",
                   return_value=MagicMock(processor=proc)):
            await _handler_for_history()._record_call_messages("CALL1", [], None, {})
        tracker.update.assert_not_called()
        proc.save_tracker.assert_awaited_once()


class TestOutboundLimitsAndStatus:

    def _client(self, **cfg):
        from kairon.shared.voice.exotel.outbound import ExotelOutboundClient
        return ExotelOutboundClient.from_config({"account_sid": "AC1", "api_key": "K1", "api_token": "T1",
                                                 "phone_number": "0800", **cfg})

    def _post(self, client, status_url=None):
        resp = MagicMock()
        resp.json.return_value = {"Call": {"Sid": "SID1"}}
        with patch("requests.post", return_value=resp) as post:
            client.connect_to_flow("+91", "555", status_url)
        return post.call_args.kwargs["data"]

    def test_no_time_limit_by_default(self):
        data = self._post(self._client())
        assert "TimeLimit" not in data and "StatusCallback" not in data

    def test_max_call_duration_becomes_exotel_time_limit_with_grace(self):
        data = self._post(self._client(max_call_duration_seconds=300))
        assert data["TimeLimit"] == "315"

    def test_time_limit_capped_at_exotel_ceiling(self):
        from kairon.shared.voice.constants import MAX_CALL_DURATION_LIMIT_SECONDS
        data = self._post(self._client(max_call_duration_seconds=14400))
        assert data["TimeLimit"] == str(MAX_CALL_DURATION_LIMIT_SECONDS)

    @pytest.mark.parametrize("bad", [None, "", 0, -5, "abc"])
    def test_bad_or_missing_duration_means_no_limit(self, bad):
        assert "TimeLimit" not in self._post(self._client(max_call_duration_seconds=bad))

    def test_status_callback_sent_when_status_url_given(self):
        data = self._post(self._client(), "https://chat/status/tok")
        assert data["StatusCallback"] == "https://chat/status/tok" and data["StatusCallbackMethod"] == "POST"


class TestStatusEndpointsAndCallbacks:

    def test_exotel_channel_endpoints_include_status_url(self):
        from kairon.shared.data.utils import DataUtility
        from kairon.shared.utils import Utility
        agent = {"model": {"agent": {"url": "https://chat.example.com"}}}
        channel = {"bot": "b1", "user": "u", "config": {"telephony_provider": "exotel"}}
        with patch("kairon.shared.auth.Authentication.generate_integration_token", return_value=("TOK", None)), \
                patch.dict(Utility.environment, agent):
            endpoints = DataUtility.get_voice_channel_endpoints(channel)
        assert endpoints["status_url"] == "https://chat.example.com/api/bot/b1/channel/voice/exotel/call/status/TOK"
        assert endpoints["call_url"].endswith("/channel/voice/exotel/resolver/TOK")

    def test_twilio_endpoints_unchanged(self):
        from kairon.shared.data.utils import DataUtility
        from kairon.shared.utils import Utility
        agent = {"model": {"agent": {"url": "https://chat.example.com"}}}
        channel = {"bot": "b1", "user": "u", "config": {"telephony_provider": "twilio"}}
        with patch("kairon.shared.auth.Authentication.generate_integration_token", return_value=("TOK", None)), \
                patch.dict(Utility.environment, agent):
            endpoints = DataUtility.get_voice_channel_endpoints(channel)
        assert set(endpoints) == {"call_url", "status_url"}
        assert endpoints["call_url"].endswith("/call/TOK")

    @pytest.mark.asyncio
    async def test_exotel_status_callback_updates_the_call_row(self):
        from kairon.chat.handlers.channels.clients.voice.exotel import ExotelVoiceProvider
        provider = ExotelVoiceProvider("b1", {"user": "u"})
        request = MagicMock()
        request.form = AsyncMock(return_value={"CallSid": "SID1", "Status": "no-answer", "Duration": "0"})
        with patch("kairon.chat.handlers.channels.clients.voice.exotel.VoiceUtils.apply_provider_status") as apply, \
                patch("kairon.chat.handlers.channels.clients.voice.exotel.ChannelLogs") as logs:
            await provider.handle_call_status(request, "b1")
        apply.assert_called_once_with("b1", "SID1", "no-answer",
                                      {"CallSid": "SID1", "Status": "no-answer", "Duration": "0"})
        logs.assert_called_once()

    @pytest.mark.asyncio
    async def test_status_callback_accepts_alternative_field_names(self):
        from kairon.chat.handlers.channels.clients.voice.exotel import ExotelVoiceProvider
        provider = ExotelVoiceProvider("b1", {})
        request = MagicMock()
        request.form = AsyncMock(return_value={"Sid": "SID2", "CallStatus": "busy"})
        with patch("kairon.chat.handlers.channels.clients.voice.exotel.VoiceUtils.apply_provider_status") as apply, \
                patch("kairon.chat.handlers.channels.clients.voice.exotel.ChannelLogs"):
            await provider.handle_call_status(request, "b1")
        assert apply.call_args.args[:3] == ("b1", "SID2", "busy")

    @pytest.mark.asyncio
    async def test_resolver_marks_call_answered(self):
        from kairon.chat.handlers.channels.voice import VoiceHandler
        request = MagicMock()
        request.query_params = {"CallSid": "SID9", "Direction": "outbound-dial"}
        user = MagicMock()
        user.get_user.return_value = "u"
        handler = VoiceHandler("b1", user, request, "exotel")
        provider = MagicMock()
        provider.build_resolver_response.return_value = {"url": "wss://x"}
        with patch.object(VoiceHandler, "_load_provider", return_value=(provider, {})), \
                patch("kairon.chat.handlers.channels.voice.ChannelLogs.save"), \
                patch("kairon.chat.handlers.channels.voice.VoiceUtils.update_call_status") as upd:
            assert await handler.handle_resolver_request() == {"url": "wss://x"}
        upd.assert_called_once_with("b1", "SID9", "answered", only_if_not_terminal=True)


class TestCallLimitConfigOnSave:

    def _save(self, **extra):
        from kairon.shared.utils import Utility
        cfg = {"telephony_provider": "exotel", "api_key": "K", "api_token": "T", "account_sid": "S",
               "phone_number": "0800", **extra}
        Utility.validate_channel("voice", cfg, AppException)
        return cfg

    def test_defaults(self):
        cfg = self._save()
        assert cfg["noinput_timeout_seconds"] == 8 and cfg["max_noinput_attempts"] == 1
        assert "max_call_duration_seconds" not in cfg

    def test_blank_values_get_defaults_and_blank_limit_is_dropped(self):
        cfg = self._save(noinput_timeout_seconds="", max_noinput_attempts=None, max_call_duration_seconds="")
        assert cfg["noinput_timeout_seconds"] == 8 and cfg["max_noinput_attempts"] == 1
        assert "max_call_duration_seconds" not in cfg

    def test_valid_values_kept_and_normalised(self):
        cfg = self._save(max_call_duration_seconds="600", noinput_timeout_seconds="5.5", max_noinput_attempts="3")
        assert cfg["max_call_duration_seconds"] == 600 and cfg["noinput_timeout_seconds"] == 5.5
        assert cfg["max_noinput_attempts"] == 3

    def test_zero_duration_means_unlimited_and_is_kept_so_it_can_clear_a_stored_limit(self):
        assert self._save(max_call_duration_seconds=0)["max_call_duration_seconds"] == 0
        assert self._save(max_call_duration_seconds="0")["max_call_duration_seconds"] == 0

    def test_zero_timeout_disables_silence_handling(self):
        assert self._save(noinput_timeout_seconds=0)["noinput_timeout_seconds"] == 0

    @pytest.mark.parametrize("field,value", [
        ("max_call_duration_seconds", -1), ("max_call_duration_seconds", 14401),
        ("max_call_duration_seconds", "abc"), ("noinput_timeout_seconds", -2), ("noinput_timeout_seconds", "x"),
        ("max_noinput_attempts", -1), ("max_noinput_attempts", "two")])
    def test_invalid_values_rejected(self, field, value):
        with pytest.raises(AppException, match=f"Invalid {field}"):
            self._save(**{field: value})

    def test_twilio_gets_none_of_these(self):
        from kairon.shared.utils import Utility
        cfg = {"telephony_provider": "twilio", "account_sid": "AC", "auth_token": "T", "phone_number": "+1"}
        Utility.validate_channel("voice", cfg, AppException)
        assert not {"noinput_timeout_seconds", "max_noinput_attempts", "max_call_duration_seconds"} & set(cfg)

    def test_integration_spec_lists_the_new_optional_fields(self):
        from kairon.shared.utils import Utility
        optional = Utility.system_metadata["voice_channels"]["exotel"]["optional_fields"]
        for field in ("max_call_duration_seconds", "noinput_timeout_seconds", "max_noinput_attempts",
                      "reprompt_fallback_phrase", "timeout_message", "max_duration_message"):
            assert field in optional


class TestCallActionContext:

    @pytest.mark.asyncio
    async def test_outbound_row_carries_slots_origin_and_status_url_is_passed(self):
        from rasa_sdk.executor import CollectingDispatcher
        from kairon.actions.definitions.voice_call import ActionVoiceCall
        tracker = MagicMock()
        tracker.sender_id = "chat-user-1"
        tracker.get_slot.return_value = "bot"
        tracker.get_latest_input_channel.return_value = "chat"
        tracker.latest_message = {"text": "call me"}
        tracker.get_intent_of_latest_message.return_value = "request_call"
        tracker.current_slot_values.return_value = {
            "customer_name": "Asha", "bot": "b", "order": None, "kairon_action_response": "x"}
        channel = {"telephony_provider": "exotel", "api_key": "K", "api_token": "T", "account_sid": "S",
                   "phone_number": "0800", "flow_app_id": "12", "status_url": "https://chat/status/tok"}
        cfg = {"name": "c", "telephony_provider": "exotel", "response": "Calling",
               "to_phone_number": {"value": "+91", "parameter_type": "value"}, "dispatch_bot_response": True}
        with patch.object(ActionVoiceCall, "retrieve_config", return_value=cfg), \
                patch("kairon.actions.definitions.voice_call.ChatDataProcessor.get_channel_config",
                      return_value={"config": channel}), \
                patch("kairon.actions.definitions.voice_call.ChannelLogs") as logs, \
                patch("kairon.actions.definitions.voice_call.ActionServerLogs"), \
                patch("kairon.shared.voice.exotel.outbound.ExotelOutboundClient.connect_to_flow",
                      return_value="SID") as connect:
            await ActionVoiceCall("b", "c").execute(CollectingDispatcher(), tracker, {}, action_call={})
        connect.assert_called_once_with("+91", "12", "https://chat/status/tok")
        data = logs.call_args.kwargs["data"]
        assert data["call_sid"] == "SID" and data["origin_sender_id"] == "chat-user-1"
        assert data["slots"] == {"customer_name": "Asha"}


class TestVoiceDisconnectAction:

    def _tracker(self, channel):
        tracker = MagicMock()
        tracker.sender_id = "s"
        tracker.latest_message = {"text": "bye"}
        tracker.get_intent_of_latest_message.return_value = "bye"
        tracker.get_latest_input_channel.return_value = channel
        return tracker

    async def _run(self, tracker):
        from rasa_sdk.executor import CollectingDispatcher
        from kairon.actions.definitions.voice_disconnect import ActionVoiceDisconnect
        dispatcher = MagicMock(spec=CollectingDispatcher)
        with patch("kairon.actions.definitions.voice_disconnect.ActionServerLogs") as logs:
            result = await ActionVoiceDisconnect("b", "kairon_voice_disconnect").execute(dispatcher, tracker, {})
        return result, dispatcher, logs

    @pytest.mark.asyncio
    async def test_voice_conversation_sends_disconnect(self):
        result, dispatcher, logs = await self._run(self._tracker("voice"))
        dispatcher.utter_custom_json.assert_called_once_with({"disconnect": True})
        assert logs.call_args.kwargs["bot_response"] == str({"disconnect": True}) and result == {}

    @pytest.mark.asyncio
    @pytest.mark.parametrize("channel", ["chat", "whatsapp", "slack"])
    async def test_other_channels_send_nothing(self, channel):
        _, dispatcher, logs = await self._run(self._tracker(channel))
        dispatcher.utter_custom_json.assert_not_called()
        assert "not a voice conversation" in logs.call_args.kwargs["bot_response"]

    @pytest.mark.asyncio
    async def test_web_chat_without_a_channel_name_never_receives_the_signal(self):
        """Regression: web chat sends no channel name; the raw {'disconnect': True} used to be shown to the user."""
        for channel in (None, ""):
            tracker = self._tracker(channel)
            _, dispatcher, logs = await self._run(tracker)
            dispatcher.utter_custom_json.assert_not_called()
            assert "not a voice conversation" in logs.call_args.kwargs["bot_response"]

    @pytest.mark.asyncio
    async def test_unknown_channel_with_no_metadata_does_nothing(self):
        tracker = self._tracker(None)
        tracker.get_latest_input_channel.side_effect = Exception("no channel")
        tracker.latest_message = {"text": "bye"}
        _, dispatcher, _ = await self._run(tracker)
        dispatcher.utter_custom_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_voice_identified_from_message_metadata_still_disconnects(self):
        tracker = self._tracker(None)
        tracker.latest_message = {"text": "bye", "metadata": {"channel_type": "voice"}}
        _, dispatcher, _ = await self._run(tracker)
        dispatcher.utter_custom_json.assert_called_once_with({"disconnect": True})

    @pytest.mark.asyncio
    async def test_dispatch_failure_is_logged_as_failure(self):
        from rasa_sdk.executor import CollectingDispatcher
        from kairon.actions.definitions.voice_disconnect import ActionVoiceDisconnect
        dispatcher = MagicMock(spec=CollectingDispatcher)
        dispatcher.utter_custom_json.side_effect = RuntimeError("boom")
        with patch("kairon.actions.definitions.voice_disconnect.ActionServerLogs") as logs, \
                patch("kairon.actions.definitions.voice_disconnect.ActionUtility.trigger_action_failure_mail") as mail:
            await ActionVoiceDisconnect("b", "kairon_voice_disconnect").execute(dispatcher, self._tracker("voice"), {})
        mail.assert_called_once()
        assert logs.call_args.kwargs["exception"] == "boom"

    def test_config_is_empty(self):
        from kairon.actions.definitions.voice_disconnect import ActionVoiceDisconnect
        assert ActionVoiceDisconnect("b", "n").retrieve_config() == {}


class TestStreamHandlerWiring:

    def _handler(self, ws=None):
        from kairon.chat.handlers.channels.clients.voice.exotel_stream import ExotelStreamHandler
        ws = ws or MagicMock()
        ws.accept = AsyncMock()
        ws.close = AsyncMock()
        ws.send_text = AsyncMock()
        return ExotelStreamHandler(bot="b1", provider="exotel", token="T", websocket=ws), ws

    async def _run(self, ws, session):
        h, _ = self._handler(ws)
        base = "kairon.chat.handlers.channels.clients.voice.exotel_stream"
        session_cls = MagicMock(return_value=session)
        with patch.object(h, "authenticate", new_callable=AsyncMock, return_value=True), \
                patch(f"{base}.ChatDataProcessor.get_channel_config", return_value={"config": {"language": "en-IN"}}), \
                patch(f"{base}.SpeechProviderConfigProcessor.resolve", return_value={}), \
                patch.object(h, "_build_stt", return_value=(MagicMock(), "sarvam")), \
                patch.object(h, "_build_tts", return_value=(MagicMock(), "sarvam", "en-IN", None)), \
                patch(f"{base}.ExotelCallSession", session_cls):
            await h.run()
        return session_cls.call_args.kwargs

    @pytest.mark.asyncio
    async def test_loop_stops_when_session_is_closed_by_a_hangup(self):
        ws = MagicMock()
        ws.receive_text = AsyncMock(side_effect=["{}", "{}", "{}"])
        session = MagicMock(closed=False)
        session.start, session.close = AsyncMock(), AsyncMock()

        async def on_message(raw):
            session.closed = True
        session.on_message = AsyncMock(side_effect=on_message)
        await self._run(ws, session)
        assert session.on_message.await_count == 1 and ws.receive_text.await_count == 1

    @pytest.mark.asyncio
    async def test_socket_error_after_our_own_hangup_is_not_an_error(self):
        ws = MagicMock()
        session = MagicMock(closed=False, ending=False, end_reason=None)
        session.start, session.close, session.on_message = AsyncMock(), AsyncMock(), AsyncMock()

        async def receive():
            session.ending = True
            raise RuntimeError('Cannot call "receive" once a close message has been sent')
        ws.receive_text = AsyncMock(side_effect=receive)
        await self._run(ws, session)
        assert session.end_reason is None

    @pytest.mark.asyncio
    async def test_unexpected_socket_error_records_error_end_reason(self):
        ws = MagicMock()
        ws.receive_text = AsyncMock(side_effect=RuntimeError("socket exploded"))
        session = MagicMock(closed=False, ending=False, end_reason=None)
        session.start, session.close, session.on_message = AsyncMock(), AsyncMock(), AsyncMock()
        await self._run(ws, session)
        assert session.end_reason == "error"

    @pytest.mark.asyncio
    async def test_session_is_wired_with_hangup_history_context_and_end_callbacks(self):
        ws = MagicMock()
        ws.receive_text = AsyncMock(side_effect=RuntimeError("done"))
        session = MagicMock(closed=True)
        session.start, session.close, session.on_message = AsyncMock(), AsyncMock(), AsyncMock()
        kwargs = await self._run(ws, session)
        base = "kairon.chat.handlers.channels.clients.voice.exotel_stream"

        await kwargs["on_hangup"]()
        ws.close.assert_awaited_once_with(code=1000)

        with patch(f"{base}.ExotelStreamHandler._record_call_messages", new_callable=AsyncMock) as record:
            await kwargs["history_recorder"]("CALL1", ["hi"], {"a": 1}, {"m": 1})
        record.assert_awaited_once_with("CALL1", ["hi"], {"a": 1}, {"m": 1})

        with patch(f"{base}.VoiceUtils.load_call_context", return_value={"slots": {"a": 1}}) as load:
            assert await kwargs["call_context_loader"]("CALL1") == {"slots": {"a": 1}}
        load.assert_called_once_with("b1", "CALL1")

        with patch(f"{base}.VoiceUtils.finish_call") as finish:
            await kwargs["on_call_end"]("CALL1", "bot_disconnect", 12.5)
        finish.assert_called_once_with("b1", "CALL1", "bot_disconnect", 12.5)


class TestStreamUrlParamLimit:

    def _query(self, config, params):
        from urllib.parse import urlparse, parse_qs
        from kairon.chat.handlers.channels.clients.voice.exotel import ExotelVoiceProvider
        from kairon.shared.utils import Utility
        agent = {"model": {"agent": {"url": "https://chat.example.com"}}}
        with patch("kairon.shared.auth.Authentication.generate_integration_token", return_value=("TOK", None)), \
                patch.dict(Utility.environment, agent):
            url = ExotelVoiceProvider("b1", config).build_resolver_response(params, "b1", "u")["url"]
        return url, parse_qs(urlparse(url).query)

    FULL = {"CallSid": "CS1", "From": "07204194578", "To": "09513886363", "Direction": "outbound-dial",
            "CallFrom": "x", "CallTo": "y"}

    def test_never_more_than_three_params(self):
        for cfg in ({}, {"sample_rate": 8000}, {"sample_rate": 16000}):
            _, q = self._query(cfg, self.FULL)
            assert len(q) <= 3

    def test_only_call_sid_and_direction_kept(self):
        _, q = self._query({"sample_rate": 16000}, self.FULL)
        assert q == {"CallSid": ["CS1"], "Direction": ["outbound-dial"]}

    def test_missing_resolver_params_are_simply_omitted(self):
        _, q = self._query({"sample_rate": 8000}, {"CallSid": "CS1"})
        assert q == {"CallSid": ["CS1"]}
        _, q = self._query({}, {})
        assert q == {}


class _SwapSTT(_QueueSTT):
    def __init__(self, name):
        super().__init__()
        self.name, self.opened = name, False

    async def open(self):
        self.opened = True


class _SwapTTS(_TTS):
    def __init__(self, name):
        super().__init__()
        self.name = name


class TestAdoptNegotiatedRate:

    def _start16(self, call="CALL1"):
        return _frame("start", start={"call_sid": call, "from": "+91", "to": "0800",
                                      "media_format": {"encoding": "audio/x-raw", "sample_rate": "16000"}})

    def _harness(self, rebuild):
        from kairon.shared.voice.exotel.session import AgentTurn, ExotelCallSession
        self.sent = []

        async def sender(frame):
            self.sent.append(frame)

        async def runner(text, sid, meta):
            return AgentTurn(messages=[f"said {text}"])

        self.old_stt, self.old_tts = _SwapSTT("old"), _SwapTTS("old")
        return ExotelCallSession(
            bot="b", config={}, sender=sender, stt=self.old_stt, tts=self.old_tts, agent_runner=runner,
            pace=False, welcome_message=None, sample_rate=8000, tts_cache_namespace="ns:8000",
            rebuild_audio=rebuild,
        )

    @pytest.mark.asyncio
    async def test_matching_rate_does_not_rebuild(self):
        rebuild = AsyncMock()
        s = self._harness(rebuild)
        await s.start()
        await s.on_message(_start())
        rebuild.assert_not_awaited()
        assert s.stt is self.old_stt and s.sample_rate == 8000

    @pytest.mark.asyncio
    async def test_different_rate_swaps_stt_and_tts_and_keeps_working(self):
        new_stt, new_tts = _SwapSTT("new"), _SwapTTS("new")
        rebuild = AsyncMock(return_value=(new_stt, new_tts, "ns:16000"))
        s = self._harness(rebuild)
        await s.start()
        await s.on_message(self._start16())
        rebuild.assert_awaited_once_with(16000)
        assert s.sample_rate == 16000 and s.tts_cache_namespace == "ns:16000"
        assert s.stt is new_stt and s.tts is new_tts
        assert self.old_stt.closed and new_stt.opened
        await new_stt.feed(_T("hello", True))
        await asyncio.sleep(0.05)
        assert new_tts.spoken == ["said hello"] and self.old_tts.spoken == []
        await s.on_message(_frame("media", media={"payload": "AAAA"}))
        assert len(new_stt.pushed) == 1 and self.old_stt.pushed == []

    @pytest.mark.asyncio
    async def test_rebuild_failure_ends_the_call_instead_of_streaming_garbled_audio(self):
        rebuild = AsyncMock(side_effect=RuntimeError("no adapter"))
        s = self._harness(rebuild)
        await s.start()
        await s.on_message(self._start16())
        assert s.closed and s.end_reason == "error"
        assert s.stt is self.old_stt and s.tts.spoken == []

    @pytest.mark.asyncio
    async def test_without_a_rebuilder_only_the_rate_is_updated(self):
        s = self._harness(None)
        await s.start()
        await s.on_message(self._start16())
        assert s.sample_rate == 16000 and s.stt is self.old_stt

    @pytest.mark.asyncio
    async def test_start_frame_details_are_logged(self, caplog):
        import logging
        s = self._harness(None)
        await s.start()
        with caplog.at_level(logging.INFO, logger="kairon.shared.voice.exotel.session"):
            await s.on_message(_frame("start", start={
                "call_sid": "CALL1", "custom_parameters": {"k": "v"},
                "media_format": {"encoding": "audio/x-raw", "sample_rate": "8000"}}))
        assert any("media_format=audio/x-raw@8000" in r.message and "custom_parameter_keys=['k']" in r.message
                   and "configured_rate=8000" in r.message for r in caplog.records)


class TestHandlerRebuildAndQueryLogging:

    @pytest.mark.asyncio
    async def test_rebuild_callback_builds_stt_and_tts_for_the_new_rate(self):
        from kairon.chat.handlers.channels.clients.voice.exotel_stream import ExotelStreamHandler
        ws = MagicMock()
        ws.accept, ws.close, ws.send_text = AsyncMock(), AsyncMock(), AsyncMock()
        ws.receive_text = AsyncMock(side_effect=RuntimeError("done"))
        ws.query_params = {"CallSid": "C1", "sample-rate": "16000"}
        h = ExotelStreamHandler(bot="b1", provider="exotel", token="T", websocket=ws)
        base = "kairon.chat.handlers.channels.clients.voice.exotel_stream"
        session = MagicMock(closed=True)
        session.start, session.close, session.on_message = AsyncMock(), AsyncMock(), AsyncMock()
        session_cls = MagicMock(return_value=session)
        build_stt = MagicMock(return_value=("STT16", "sarvam"))
        build_tts = MagicMock(return_value=("TTS16", "sarvam", "en-IN", "ishita"))
        with patch.object(h, "authenticate", new_callable=AsyncMock, return_value=True), \
                patch(f"{base}.ChatDataProcessor.get_channel_config", return_value={"config": {"language": "en-IN"}}), \
                patch(f"{base}.SpeechProviderConfigProcessor.resolve", return_value={}), \
                patch.object(h, "_build_stt", build_stt), patch.object(h, "_build_tts", build_tts), \
                patch(f"{base}.ExotelCallSession", session_cls):
            await h.run()
            build_stt.reset_mock(), build_tts.reset_mock()
            stt, tts, namespace = await session_cls.call_args.kwargs["rebuild_audio"](16000)
        assert (stt, tts) == ("STT16", "TTS16")
        assert namespace == "sarvam:ishita:en-IN:16000"
        assert build_stt.call_args.args[1] == 16000 and build_tts.call_args.args[1] == 16000


class TestHandlerAgentTurnsAndDisconnect:

    def _handler(self, ws=None):
        from kairon.chat.handlers.channels.clients.voice.exotel_stream import ExotelStreamHandler
        ws = ws or MagicMock()
        return ExotelStreamHandler(bot="b1", provider="exotel", token="T", websocket=ws)

    BASE = "kairon.chat.handlers.channels.clients.voice.exotel_stream"

    @pytest.mark.asyncio
    async def test_agent_turn_returns_the_replies(self):
        h = self._handler()

        async def handle(bot, user_msg):
            await user_msg.output_channel.send_text_message("CALL1", "hello caller")

        with patch(f"{self.BASE}.AgentProcessor.handle_channel_message", side_effect=handle):
            turn = await h._make_agent_runner()("hi", "CALL1", {})
        assert turn.messages == ["hello caller"] and turn.hangup is False

    @pytest.mark.asyncio
    async def test_agent_turn_reports_the_disconnect_signal(self):
        h = self._handler()

        async def handle(bot, user_msg):
            await user_msg.output_channel.send_custom_json("CALL1", {"disconnect": True})

        with patch(f"{self.BASE}.AgentProcessor.handle_channel_message", side_effect=handle):
            turn = await h._make_agent_runner()("bye", "CALL1", {})
        assert turn.hangup is True

    @pytest.mark.parametrize("error,expected", [
        (RuntimeError('WebSocket is not connected. Need to call "accept" first.'), True),
        (RuntimeError("something else"), False),
        (ValueError("not connected"), False)])
    def test_caller_disconnected_by_error_message(self, error, expected):
        assert self._handler()._caller_disconnected(error) is expected

    def test_caller_disconnected_by_socket_state(self):
        from starlette.websockets import WebSocketState
        ws = MagicMock()
        ws.client_state = WebSocketState.DISCONNECTED
        assert self._handler(ws)._caller_disconnected(ValueError("x")) is True

    @pytest.mark.asyncio
    async def test_dead_socket_after_caller_hangup_is_not_an_error(self):
        """Regression: Exotel hanging up made starlette raise RuntimeError, which marked every call as failed."""
        base = "kairon.chat.handlers.channels.clients.voice.exotel_stream"
        ws = MagicMock()
        ws.accept, ws.close, ws.send_text = AsyncMock(), AsyncMock(), AsyncMock()
        ws.receive_text = AsyncMock(side_effect=RuntimeError('WebSocket is not connected. Need to call "accept" first.'))
        h = self._handler(ws)
        session = MagicMock(closed=False, ending=False, end_reason=None)
        session.start, session.close, session.on_message = AsyncMock(), AsyncMock(), AsyncMock()
        with patch.object(h, "authenticate", new_callable=AsyncMock, return_value=True), \
                patch(f"{base}.ChatDataProcessor.get_channel_config", return_value={"config": {"language": "en-IN"}}), \
                patch(f"{base}.SpeechProviderConfigProcessor.resolve", return_value={}), \
                patch.object(h, "_build_stt", return_value=(MagicMock(), "sarvam")), \
                patch.object(h, "_build_tts", return_value=(MagicMock(), "sarvam", "en-IN", None)), \
                patch(f"{base}.ExotelCallSession", MagicMock(return_value=session)):
            await h.run()
        assert session.end_reason is None
        session.close.assert_awaited()


class TestSharedVoiceChannelHelper:

    @pytest.mark.parametrize("channel,metadata,expected", [
        ("voice", None, True), ("chat", None, False), ("whatsapp", None, False), (None, None, False), ("", None, False),
        (None, {"channel_type": "voice"}, True), (None, {"channel_type": "chat"}, False), (None, {}, False)])
    def test_only_a_positively_identified_voice_call_counts(self, channel, metadata, expected):
        from kairon.shared.voice.utils import VoiceUtils
        tracker = MagicMock()
        tracker.get_latest_input_channel.return_value = channel
        tracker.latest_message = {"text": "x", "metadata": metadata}
        assert VoiceUtils.is_voice_conversation(tracker) is expected

    def test_missing_latest_message_is_not_a_voice_call(self):
        from kairon.shared.voice.utils import VoiceUtils
        tracker = MagicMock()
        tracker.get_latest_input_channel.return_value = None
        tracker.latest_message = None
        assert VoiceUtils.is_voice_conversation(tracker) is False


class TestExotelChannelConfigValidation:
    """``apply_exotel_defaults`` validates what the channel API stores for an Exotel voice channel."""

    REGISTRIES = {"stt_provider": {"sarvam": {}, "google": {}}, "tts_provider": {"sarvam": {}, "polly": {}}}

    def _apply(self, **config):
        from kairon.shared.voice.utils import VoiceUtils
        VoiceUtils.apply_exotel_defaults(config, ValueError, self.REGISTRIES)
        return config

    @pytest.mark.parametrize("subdomain", ["api.exotel.com", "API.In.Exotel.com ", "api.in.exotel.com"])
    def test_exotel_hosts_are_accepted_and_normalised(self, subdomain):
        assert self._apply(subdomain=subdomain)["subdomain"] == subdomain.strip().lower()

    @pytest.mark.parametrize("subdomain", [
        "evil.example.com", "api.exotel.com.evil.io", "exotel.com", "api.exotel.com/path", "user@api.exotel.com",
        "api.exotel.com:8443", "127.0.0.1", "notexotel.com"])
    def test_hosts_outside_exotel_are_rejected(self, subdomain):
        with pytest.raises(ValueError, match="Invalid subdomain"):
            self._apply(subdomain=subdomain)

    def test_blank_subdomain_is_left_for_the_caller_default(self):
        assert "subdomain" not in self._apply() and self._apply(subdomain="")["subdomain"] == ""

    @pytest.mark.parametrize("value,stored", [("12345", "12345"), (12345, "12345"), (" 678 ", "678")])
    def test_numeric_flow_app_id_is_accepted(self, value, stored):
        assert self._apply(flow_app_id=value)["flow_app_id"] == stored

    @pytest.mark.parametrize("value", ["../../etc", "12/34", "abc", "12 34", "1?x=y"])
    def test_non_numeric_flow_app_id_is_rejected(self, value):
        with pytest.raises(ValueError, match="Invalid flow_app_id"):
            self._apply(flow_app_id=value)

    def test_blank_flow_app_id_is_allowed(self):
        assert "flow_app_id" not in self._apply() and self._apply(flow_app_id=None)["flow_app_id"] is None

    def test_defaults_are_filled_in(self):
        config = self._apply()
        assert config["sample_rate"] == 8000
        assert config["stt_provider"] == config["tts_provider"] == "sarvam"
        assert config["noinput_timeout_seconds"] == 8 and config["max_noinput_attempts"] == 1

    @pytest.mark.parametrize("value,stored", [(16000, 16000), ("16000", 16000), (8000.0, 8000)])
    def test_supported_sample_rates(self, value, stored):
        assert self._apply(sample_rate=value)["sample_rate"] == stored

    @pytest.mark.parametrize("value", [24000, "abc", 0, 44100])
    def test_unsupported_sample_rates_are_rejected(self, value):
        with pytest.raises(ValueError, match="Unsupported sample_rate"):
            self._apply(sample_rate=value)

    def test_unknown_speech_provider_is_rejected(self):
        with pytest.raises(ValueError, match="Unsupported tts_provider"):
            self._apply(tts_provider="nope")
        assert self._apply(stt_provider="google", tts_provider="polly")["tts_provider"] == "polly"

    def test_missing_registry_accepts_any_provider(self):
        from kairon.shared.voice.utils import VoiceUtils
        config = {"stt_provider": "whatever"}
        VoiceUtils.apply_exotel_defaults(config, ValueError, {"stt_provider": None, "tts_provider": {}})
        assert config["stt_provider"] == "whatever" and config["tts_provider"] == "sarvam"

    def test_validate_voice_provider_applies_checks_and_default_subdomain(self):
        from kairon.shared.utils import Utility
        base = {"telephony_provider": "exotel", "api_key": "k", "api_token": "t", "account_sid": "a", "phone_number": "080"}
        with patch.object(Utility, "encrypt_message", side_effect=lambda v: f"enc:{v}"):
            config = dict(base)
            Utility.validate_voice_provider(config, ValueError)
            assert config["subdomain"] == Utility.environment["voice"]["exotel"]["subdomain"] == "api.exotel.com"
            assert config["api_token"] == "enc:t" and config["sample_rate"] == 8000
            with pytest.raises(ValueError, match="Invalid subdomain"):
                Utility.validate_voice_provider({**base, "subdomain": "evil.example.com"}, ValueError)


class TestSarvamSttGuards:

    def test_unsupported_rate_without_audioop_is_rejected_up_front(self):
        from kairon.exceptions import AppException
        from kairon.shared.voice.stt import sarvam
        with patch.object(sarvam, "audioop", None):
            with pytest.raises(AppException, match="cannot downsample 24000 Hz"):
                sarvam.SarvamSTT({"api_key": "k"}, "en-IN", 24000)
            assert sarvam.SarvamSTT({"api_key": "k"}, "en-IN", 16000).stream_rate == 16000

    @pytest.mark.parametrize("raw,expected", [
        ('{"transcript": "hi", "is_final": true, "confidence": 0.9}', ("hi", True, 0.9)),
        ('{"text": "hey", "final": false}', ("hey", False, None)),
        ('{"type": "final", "text": "done"}', ("done", True, None)),
        ('{"data": {"transcript": "nested"}}', ("nested", False, None)),
        ('{"data": {"text": "nested2"}}', ("nested2", False, None)),
        (b'{"text": "bytes"}', ("bytes", False, None))])
    def test_legacy_message_shapes(self, raw, expected):
        from kairon.shared.voice.stt.sarvam import SarvamSTT
        t = SarvamSTT._parse_result(raw)
        assert (t.text, t.is_final, t.confidence) == expected

    @pytest.mark.parametrize("raw", ['{"type": "error"}', '{"type": "pong"}', '{"data": "x"}', '{"data": null}',
                                     '{"other": 1}', "not json", "[1, 2]", None])
    def test_legacy_non_transcripts_are_ignored(self, raw):
        from kairon.shared.voice.stt.sarvam import SarvamSTT
        assert SarvamSTT._parse_result(raw) is None


class TestSessionEdgeCases:
    """Rare paths of the call session that must still behave: no frame details, races with hangup, TTS failures."""

    @pytest.mark.asyncio
    async def test_start_frame_without_details_still_starts_the_call(self):
        h = _Harness(welcome=None)
        await h.session.start()
        await h.session.on_message(_frame("start"))
        assert h.session.call_sid is None or h.session.call_sid == ""
        assert h.session._noinput_task is None or not h.session._noinput_task.done()

    @pytest.mark.asyncio
    async def test_ending_flag_is_exposed_while_hanging_up(self):
        h = _Harness(welcome=None)
        await h.begin()
        assert h.session.ending is False
        h.session._ending = True
        assert h.session.ending is True

    @pytest.mark.asyncio
    async def test_turns_and_timers_are_ignored_once_the_call_is_ending(self):
        runner = AsyncMock()
        h = _Harness(welcome=None, runner=runner)
        await h.begin()
        h.session._ending = True
        h.session._noinput_count = 1
        h.session._caller_active()
        assert h.session._noinput_count == 1
        h.session._noinput_task = None
        h.session._arm_noinput()
        assert h.session._noinput_task is None
        await h.session._run_turn("hello")
        runner.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_turn_after_the_call_closed_is_dropped(self):
        runner = AsyncMock()
        h = _Harness(welcome=None, runner=runner)
        await h.begin()
        await h.session.close()
        await h.session._run_turn("late words")
        runner.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_hangup_that_loses_the_race_to_close_does_nothing_more(self):
        h = _Harness(welcome=None)
        await h.begin()

        async def closed_while_waiting():
            await h.session.close()

        with patch.object(h.session, "_wait_for_playback", side_effect=closed_while_waiting):
            await h.session._hangup("bot_disconnect")
        assert h.hangups == [] and h.session.closed and len(h.ended) == 1

    @pytest.mark.asyncio
    async def test_bootstrap_cancellation_is_propagated(self):
        async def slow_loader(call_sid):
            await asyncio.sleep(10)

        h = _Harness(welcome="Hi")
        h.session._call_context_loader = slow_loader
        await h.session.start()
        await h.session.on_message(_start())
        await asyncio.sleep(0.02)
        task = h.session._bootstrap_task
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    @pytest.mark.asyncio
    async def test_tts_failure_after_some_audio_still_sends_a_mark(self):
        class PartialTTS:
            async def synthesize(self, text):
                yield b"\x01\x02" * 4000
                raise RuntimeError("provider dropped")

        h = _Harness(welcome=None)
        h.session.tts = PartialTTS()
        await h.begin()
        await h.session._speak(["hello"])
        events = [f["event"] if isinstance(f, dict) else json.loads(f)["event"] for f in h.sent]
        assert "media" in events and events[-1] == "mark"

    @pytest.mark.asyncio
    async def test_tts_failure_before_any_audio_sends_nothing_and_does_not_wait_for_a_mark(self):
        class BrokenTTS:
            async def synthesize(self, text):
                raise RuntimeError("provider down")
                yield b""

        h = _Harness(welcome=None)
        h.session.tts = BrokenTTS()
        await h.begin()
        before = len(h.sent)
        await h.session._speak(["hello"])
        assert len(h.sent) == before and h.session._last_mark is None


class TestSmallGaps:

    def test_exotel_client_error_text_hides_blank_and_real_secrets(self):
        from kairon.shared.voice.exotel.outbound import ExotelOutboundClient
        client = ExotelOutboundClient("sid", "", "080", api_key="KEY", api_token="")
        client.api_token = ""
        assert client._scrub("boom KEY here") == "boom *** here"

    def test_sarvam_tts_requires_requests_package(self):
        import sys
        from kairon.exceptions import AppException
        from kairon.shared.voice.tts.sarvam import SarvamTTS
        tts = SarvamTTS({"api_key": "k"}, "en-IN", 8000)
        with patch.dict(sys.modules, {"requests": None}):
            with pytest.raises(AppException, match="requests"):
                tts._synthesize_sync("hi")

    @pytest.mark.asyncio
    async def test_websocket_disconnect_is_a_normal_end(self):
        from starlette.websockets import WebSocketDisconnect
        ws = MagicMock()
        ws.receive_text = AsyncMock(side_effect=WebSocketDisconnect())
        session = MagicMock(closed=False, ending=False, end_reason=None)
        session.start, session.close, session.on_message = AsyncMock(), AsyncMock(), AsyncMock()
        await TestStreamHandlerWiring()._run(ws, session)
        assert session.end_reason is None
        session.close.assert_awaited()


class TestSttBuilderModelSelection:
    """The STT model defaults to the provider's model for the call's sample rate, unless the bot's config sets one."""

    def _build(self, resolved, rate=16000):
        from kairon.chat.handlers.channels.clients.voice.exotel_stream import ExotelStreamHandler
        base = "kairon.chat.handlers.channels.clients.voice.exotel_stream"
        handler = ExotelStreamHandler(bot="b1", provider="exotel", token="T", websocket=MagicMock())
        adapter = MagicMock()
        with patch(f"{base}.STTFactory.provider_metadata", return_value={"models": {"16000": "rate-model"}}), \
                patch(f"{base}.STTFactory.get", return_value=adapter):
            handler._stt_builder("sarvam", "en-IN", rate, resolved)()
        return adapter.call_args.args[0]

    def test_model_for_the_sample_rate_is_used_by_default(self):
        assert self._build({"sarvam": {"secrets": {"api_key": "k"}}})["model"] == "rate-model"

    def test_explicit_model_in_the_speech_config_wins(self):
        creds = self._build({"sarvam": {"metadata": {"model": "custom"}, "secrets": {"api_key": "k"}}})
        assert creds["model"] == "custom"

    def test_rate_without_a_model_mapping_adds_none(self):
        assert "model" not in self._build({"sarvam": {"secrets": {"api_key": "k"}}}, rate=8000)


class TestProviderDefaults:
    """Endpoint, model and speaker a speech provider uses when the bot's speech config names none."""

    def _with_env(self, voice_env):
        from kairon.shared.utils import Utility
        return patch.dict(Utility.environment, {"voice": voice_env})

    def test_system_yaml_value_wins(self):
        from kairon.shared.voice.utils import VoiceUtils
        with self._with_env({"tts": {"sarvam": {"speaker": "anushka"}}}):
            assert VoiceUtils.provider_default("tts", "sarvam", "speaker") == "anushka"

    def test_falls_back_to_the_built_in_defaults(self):
        from kairon.shared.voice.utils import VoiceUtils
        for env in ({}, {"tts": None}, {"tts": {"polly": {"speaker": "Aditi"}}}, {"tts": {"sarvam": {}}}):
            with self._with_env(env):
                assert VoiceUtils.provider_default("tts", "sarvam", "speaker") == "shubh"
                assert VoiceUtils.provider_default("stt", "sarvam", "model") == "saaras:v4"

    def test_unknown_provider_or_key_has_no_default(self):
        from kairon.shared.voice.utils import VoiceUtils
        with self._with_env({}):
            assert VoiceUtils.provider_default("tts", "elevenlabs", "speaker") is None
            assert VoiceUtils.provider_default("stt", "sarvam", "speaker") is None
            assert VoiceUtils.provider_default("other", "sarvam", "model") is None

    def test_adapters_use_them_unless_the_bots_speech_config_says_otherwise(self):
        from kairon.shared.voice.stt.sarvam import SarvamSTT
        from kairon.shared.voice.tts.polly import PollyTTS
        from kairon.shared.voice.tts.sarvam import SarvamTTS
        polly_cfg = {"aws_access_key_id": "a", "aws_secret_access_key": "b"}
        env = {
            "stt": {"sarvam": {"endpoint": "wss://stt.example/ws", "model": "stt-x"}},
            "tts": {"sarvam": {"endpoint": "https://tts.example", "model": "tts-x", "speaker": "anushka"},
                    "polly": {"speaker": "Aditi"}},
        }
        with self._with_env(env):
            stt = SarvamSTT({"api_key": "k"}, "en-IN")
            assert (stt.endpoint, stt.model) == ("wss://stt.example/ws", "stt-x")
            stt = SarvamSTT({"api_key": "k", "stt_url": "wss://own/ws", "stt_model": "own"}, "en-IN")
            assert (stt.endpoint, stt.model) == ("wss://own/ws", "own")
            tts = SarvamTTS({"api_key": "k"})
            assert (tts.endpoint, tts.model, tts.speaker) == ("https://tts.example", "tts-x", "anushka")
            tts = SarvamTTS({"api_key": "k", "tts_url": "https://own", "tts_model": "own"}, voice="vidya")
            assert (tts.endpoint, tts.model, tts.speaker) == ("https://own", "own", "vidya")
            assert PollyTTS(polly_cfg).voice == "Aditi"
            assert PollyTTS({**polly_cfg, "default_voice": "Kajal"}).voice == "Kajal"
            assert PollyTTS(polly_cfg, voice="Joanna").voice == "Joanna"


class TestProviderPolymorphism:
    """Providers differ in how they place a call and normalise their config, not in the callers' branching."""

    EXOTEL = {"account_sid": "acct", "api_key": "k", "api_token": "t", "phone_number": "080", "flow_app_id": "99",
              "status_url": "https://cb/status"}

    def test_exotel_places_the_call_through_its_flow(self):
        from kairon.shared.voice.factory import VoiceOutboundFactory
        client = VoiceOutboundFactory.get_client("exotel").from_config(self.EXOTEL)
        with patch.object(type(client), "connect_to_flow", return_value="SID1") as connect:
            assert client.place_call("+91000", self.EXOTEL) == "SID1"
        connect.assert_called_once_with("+91000", "99", "https://cb/status")

    def test_exotel_without_a_flow_cannot_place_a_call(self):
        from kairon.exceptions import AppException
        from kairon.shared.voice.factory import VoiceOutboundFactory
        config = {k: v for k, v in self.EXOTEL.items() if k != "flow_app_id"}
        client = VoiceOutboundFactory.get_client("exotel").from_config(config)
        with pytest.raises(AppException, match="flow_app_id is not configured"):
            client.place_call("+91000", config)

    def test_exotel_blank_status_url_is_not_sent(self):
        from kairon.shared.voice.factory import VoiceOutboundFactory
        config = {**self.EXOTEL, "status_url": ""}
        client = VoiceOutboundFactory.get_client("exotel").from_config(config)
        with patch.object(type(client), "connect_to_flow", return_value="S") as connect:
            client.place_call("+91000", config)
        connect.assert_called_once_with("+91000", "99", None)

    def test_twilio_places_the_call_with_its_urls(self):
        from kairon.shared.voice.factory import VoiceOutboundFactory
        config = {"account_sid": "a", "auth_token": "t", "phone_number": "+1555", "call_url": "https://c",
                  "status_url": "https://s"}
        client = VoiceOutboundFactory.get_client("twilio").from_config(config)
        assert (client.account_sid, client.auth_token, client.from_number) == ("a", "t", "+1555")
        with patch.object(type(client), "initiate_call", return_value="SID2") as initiate:
            assert client.place_call("+91000", config) == "SID2"
        initiate.assert_called_once_with("+91000", "https://c", "https://s")
        with patch.object(type(client), "initiate_call", return_value="SID3") as initiate:
            client.place_call("+91000", {})
        initiate.assert_called_once_with("+91000", "", "")

    def test_a_provider_without_rules_leaves_the_config_untouched(self):
        from kairon.chat.handlers.channels.clients.voice.factory import VoiceProviderFactory
        config = {"account_sid": "a", "sample_rate": "garbage"}
        VoiceProviderFactory.get_provider("twilio").normalize_config(config, ValueError, {})
        assert config == {"account_sid": "a", "sample_rate": "garbage"}

    def test_exotel_normalises_its_config_and_defaults_the_subdomain(self):
        from kairon.chat.handlers.channels.clients.voice.factory import VoiceProviderFactory
        from kairon.shared.utils import Utility
        provider = VoiceProviderFactory.get_provider("exotel")
        config = {"sample_rate": "16000"}
        provider.normalize_config(config, ValueError, {})
        assert config["sample_rate"] == 16000 and config["subdomain"] == "api.exotel.com"
        with patch.dict(Utility.environment, {"voice": {"exotel": {"subdomain": "api.in.exotel.com"}}}):
            config = {}
            provider.normalize_config(config, ValueError, {})
        assert config["subdomain"] == "api.in.exotel.com"
        config = {"subdomain": "api.in.exotel.com"}
        provider.normalize_config(config, ValueError, {})
        assert config["subdomain"] == "api.in.exotel.com"
