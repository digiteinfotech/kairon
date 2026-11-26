"""Exotel streaming call session: the voice call loop.

One :class:`ExotelCallSession` drives a single call for its whole lifetime:

    caller audio ── media frames ──▶ STT ──final transcript──▶ agent brain
                                                                    │
    caller  ◀── media frames ◀── AudioChunker ◀── TTS ◀── bot reply messages

Responsibilities kept here (transport-agnostic, so it is unit-testable with fakes):
  * dispatch inbound Exotel frames (start / media / dtmf / stop / mark)
  * feed caller audio to the STT stream
  * on each final transcript, run one agent turn and stream the reply back,
    re-framed to Exotel's 320-byte-multiple rule and paced to real time
  * greet the caller with the configured welcome message on ``start``
  * silence handling: reprompt, then say goodbye and hang up
  * hard cap on the call length, and an orderly hang-up (the goodbye finishes playing, then the websocket is closed)
  * adopt the sample rate Exotel actually negotiated, as reported by the ``start`` frame
  * report how the call ended, and keep the bot-only utterances in the chat history

The WebSocket receive loop, authentication, and construction of the concrete
STT/TTS adapters and agent runner live in the channel handler; this class takes
them as injected collaborators.
"""
import asyncio
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, List, Optional

from kairon.shared.voice.cache import make_key
from kairon.shared.voice.constants import (
    DEFAULT_MAX_DURATION_MESSAGE,
    DEFAULT_MAX_NOINPUT_ATTEMPTS,
    DEFAULT_NOINPUT_TIMEOUT_SECONDS,
    DEFAULT_REPROMPT_PHRASE,
    DEFAULT_TIMEOUT_MESSAGE,
    PLAYBACK_WAIT_SECONDS,
    CallEndReason,
)
from kairon.shared.voice.exotel.audio import AudioChunker, chunk_pcm
from kairon.shared.voice.exotel.protocol import (
    ExotelEvent,
    InboundFrame,
    StartInfo,
    build_clear,
    build_mark,
    build_media,
    parse_inbound,
)
from kairon.shared.voice.metrics import now_ms

logger = logging.getLogger(__name__)


def _non_negative_number(value, default: float) -> float:
    """``value`` as a finite float >= 0, else ``default`` (config values may be missing, blank or garbage)."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) and number >= 0 else default


@dataclass
class CallSettings:
    """The per-call behaviour a bot configures in its voice channel config; bad or missing values use the defaults."""

    welcome_message: Optional[str] = None
    dtmf_enabled: bool = True
    dtmf_terminator: str = "#"
    dtmf_max_length: int = 32
    dtmf_timeout: float = 0.0
    noinput_timeout: float = DEFAULT_NOINPUT_TIMEOUT_SECONDS
    max_noinput_attempts: int = DEFAULT_MAX_NOINPUT_ATTEMPTS
    reprompt_phrase: str = DEFAULT_REPROMPT_PHRASE
    timeout_message: str = DEFAULT_TIMEOUT_MESSAGE
    max_call_duration: float = 0.0
    max_duration_message: str = DEFAULT_MAX_DURATION_MESSAGE

    @classmethod
    def from_config(cls, config: dict) -> "CallSettings":
        """Read the settings from the voice channel ``config``."""
        dtmf = config.get("dtmf") or {}
        return cls(
            welcome_message=config.get("welcome_message"),
            dtmf_enabled=bool(dtmf.get("enabled", True)),
            dtmf_terminator=str(dtmf.get("terminator", "#")),
            dtmf_max_length=int(dtmf.get("max_length", 32)),
            dtmf_timeout=float(dtmf.get("inter_digit_timeout", 0) or 0),
            noinput_timeout=_non_negative_number(
                config.get("noinput_timeout_seconds"), DEFAULT_NOINPUT_TIMEOUT_SECONDS
            ),
            max_noinput_attempts=int(
                _non_negative_number(config.get("max_noinput_attempts"), DEFAULT_MAX_NOINPUT_ATTEMPTS)
            ),
            reprompt_phrase=config.get("reprompt_fallback_phrase") or DEFAULT_REPROMPT_PHRASE,
            timeout_message=config.get("timeout_message") or DEFAULT_TIMEOUT_MESSAGE,
            max_call_duration=_non_negative_number(config.get("max_call_duration_seconds"), 0.0),
            max_duration_message=config.get("max_duration_message") or DEFAULT_MAX_DURATION_MESSAGE,
        )


@dataclass
class AgentTurn:
    """Result of running one turn of the agent brain."""

    messages: List[str] = field(default_factory=list)
    hangup: bool = False


# async (text, sender_id, metadata) -> AgentTurn
AgentRunner = Callable[[str, str, dict], Awaitable[AgentTurn]]
# async (frame_dict) -> None : serialise + send one frame to the websocket
FrameSender = Callable[[dict], Awaitable[None]]
HangupCallback = Callable[[], Awaitable[None]]
HistoryRecorder = Callable[[str, List[str], Optional[dict], dict], Awaitable[None]]
CallContextLoader = Callable[[str], Awaitable[dict]]
CallEndCallback = Callable[[str, str, float], Awaitable[None]]
AudioRebuilder = Callable[[int], Awaitable[tuple]]


class ExotelCallSession:
    """Drives one Exotel WebSocket call: STT -> agent -> TTS -> media frames."""

    def __init__(
        self,
        *,
        bot: str,
        config: dict,
        sender: FrameSender,
        stt,
        tts,
        agent_runner: AgentRunner,
        metadata: Optional[dict] = None,
        welcome_message: Optional[str] = None,
        chunk_multiple: int = 320,
        chunk_max_bytes: int = 100000,
        sample_rate: int = 8000,
        pace: bool = True,
        metrics=None,
        tts_cache=None,
        tts_cache_namespace: str = "",
        on_hangup: Optional[HangupCallback] = None,
        history_recorder: Optional[HistoryRecorder] = None,
        call_context_loader: Optional[CallContextLoader] = None,
        on_call_end: Optional[CallEndCallback] = None,
        rebuild_audio: Optional[AudioRebuilder] = None,
    ):
        """Wire STT/TTS adapters, agent runner and sender for one call lifetime.

        :param config: the voice channel config (welcome message, silence handling, call limits, DTMF)
        :param on_hangup: closes the websocket; that is what makes Exotel end the call
        :param history_recorder: stores bot-only utterances and carried slots in the call's chat history
        :param call_context_loader: loads the context (slots) an outbound call inherits from the triggering chat
        :param on_call_end: told once, with the end reason and duration, when the call is over
        :param rebuild_audio: rebuilds STT/TTS when Exotel negotiates another sample rate than configured
        """
        self.bot = bot
        self.config = config or {}
        self._send = sender
        self.stt = stt
        self.tts = tts
        self.agent_runner = agent_runner
        self.metadata = dict(metadata or {})
        settings = CallSettings.from_config(self.config)
        self.welcome_message = welcome_message if welcome_message is not None else settings.welcome_message
        self.chunk_multiple = chunk_multiple
        self.chunk_max_bytes = chunk_max_bytes
        self.sample_rate = sample_rate
        self.pace = pace
        self.metrics = metrics
        self.tts_cache = tts_cache
        self.tts_cache_namespace = tts_cache_namespace

        self.dtmf_enabled = settings.dtmf_enabled
        self.dtmf_terminator = settings.dtmf_terminator
        self.dtmf_max_length = settings.dtmf_max_length
        self.dtmf_timeout = settings.dtmf_timeout
        self._dtmf_buffer = ""
        self._dtmf_timer: Optional[asyncio.Task] = None

        self.stream_sid: str = ""
        self.call_sid: str = ""
        self.start_info: Optional[StartInfo] = None
        self._mark_counter = 0
        self._started = False
        self._closed = False
        self._ending = False
        self._consumer_task: Optional[asyncio.Task] = None

        self._on_hangup = on_hangup
        self._history_recorder = history_recorder
        self._call_context_loader = call_context_loader
        self._on_call_end = on_call_end
        self._rebuild_audio = rebuild_audio

        self.noinput_timeout = settings.noinput_timeout
        self.max_noinput_attempts = settings.max_noinput_attempts
        self.reprompt_phrase = settings.reprompt_phrase
        self.timeout_message = settings.timeout_message
        self.max_call_duration = settings.max_call_duration
        self.max_duration_message = settings.max_duration_message
        self.end_reason: Optional[str] = None
        self._noinput_count = 0
        self._noinput_task: Optional[asyncio.Task] = None
        self._max_duration_task: Optional[asyncio.Task] = None
        self._bootstrap_task: Optional[asyncio.Task] = None
        self._last_agent_message: Optional[str] = None
        self._last_mark: Optional[str] = None
        self._mark_event = asyncio.Event()
        self._speak_lock = asyncio.Lock()
        self._started_at: Optional[float] = None
        self._turns = 0

    @property
    def closed(self) -> bool:
        """True once the call is over (hung up by either side)."""
        return self._closed

    @property
    def ending(self) -> bool:
        """True once the bot has started hanging up (its goodbye is playing, the socket is about to close)."""
        return self._ending

    # ------------------------------------------------------------------ lifecycle
    async def start(self) -> None:
        """Open the STT stream and begin consuming transcripts."""
        await self.stt.open()
        self._consumer_task = asyncio.ensure_future(self._consume_transcripts())

    async def on_message(self, raw) -> None:
        """Entry point for one raw inbound websocket message."""
        frame = parse_inbound(raw)
        await self.on_frame(frame)

    async def on_frame(self, frame: InboundFrame) -> None:
        """Dispatch a parsed inbound frame to the appropriate event handler."""
        event = frame.event
        if event == ExotelEvent.START.value:
            await self._on_start(frame)
        elif event == ExotelEvent.MEDIA.value:
            await self._on_media(frame)
        elif event == ExotelEvent.DTMF.value:
            await self._on_dtmf(frame)
        elif event == ExotelEvent.STOP.value:
            await self._on_stop(frame)
        elif event == ExotelEvent.MARK.value:
            self._on_mark(frame)
        elif event in (ExotelEvent.CONNECTED.value, ""):
            return
        else:
            logger.debug("Unhandled Exotel event '%s' bot=%s", event, self.bot)

    async def _on_start(self, frame: InboundFrame) -> None:
        """Handle the ``start`` frame: learn the call identity and rate, greet the caller, arm the timers."""
        if self._started:
            return
        self._started = True
        self.start_info = frame.start
        self.stream_sid = frame.stream_sid or (frame.start.stream_sid if frame.start else "")
        if frame.start:
            self.call_sid = frame.start.call_sid
            logger.info(
                "Exotel start frame bot=%s call_sid=%s media_format=%s@%s custom_parameter_keys=%s configured_rate=%s",
                self.bot, frame.start.call_sid, frame.start.encoding, frame.start.sample_rate,
                sorted(frame.start.custom_parameters), self.sample_rate,
            )
            if frame.start.sample_rate and not await self._adopt_stream_rate(frame.start.sample_rate):
                return
            self.metadata.setdefault("caller_phone", frame.start.from_number)
            self.metadata.setdefault("called_number", frame.start.to_number)
        self.metadata.setdefault("call_sid", self.call_sid or self.stream_sid)
        if self.metrics is not None and not getattr(self.metrics, "call_sid", ""):
            self.metrics.call_sid = self.call_sid or self.stream_sid
        self._started_at = time.monotonic()
        self._bootstrap_task = asyncio.ensure_future(self._bootstrap_conversation())
        if self.welcome_message:
            await self._speak([self.welcome_message])
        self._arm_noinput()
        self._arm_max_duration()

    async def _adopt_stream_rate(self, rate: int) -> bool:
        """Make the call use the sample rate the ``start`` frame reports.

        The frame is authoritative: if Exotel negotiated another rate than the one STT/TTS were built for, they are
        rebuilt for the real rate, otherwise the caller would hear (and we would transcribe) garbled audio.

        :return: False if the call had to be ended because the speech adapters could not be rebuilt
        """
        if rate == self.sample_rate:
            return True
        if self._rebuild_audio is None:
            self.sample_rate = rate
            return True
        logger.warning(
            "Exotel stream rate %s differs from the configured %s: rebuilding STT/TTS bot=%s",
            rate, self.sample_rate, self.bot,
        )
        try:
            stt, tts, namespace = await self._rebuild_audio(rate)
        except Exception as e:
            logger.error("Could not rebuild speech adapters for %s Hz bot=%s, ending the call: %s", rate, self.bot, e)
            await self._hangup(CallEndReason.ERROR.value)
            return False
        self._cancel_task("_consumer_task")
        try:
            await self.stt.close()
        except Exception as e:  # pragma: no cover - adapter specific
            logger.debug("Error closing old STT bot=%s: %s", self.bot, e)
        self.stt, self.tts, self.tts_cache_namespace, self.sample_rate = stt, tts, namespace, rate
        await self.stt.open()
        self._consumer_task = asyncio.ensure_future(self._consume_transcripts())
        return True

    async def _bootstrap_conversation(self) -> None:
        """Start the call's chat history: inherited slots (outbound calls) and the welcome message."""
        try:
            slots = None
            if self._call_context_loader is not None and self.call_sid:
                try:
                    slots = (await self._call_context_loader(self.call_sid) or {}).get("slots") or None
                except Exception as e:
                    logger.warning("Could not load call context bot=%s: %s", self.bot, e)
            await self._record([self.welcome_message] if self.welcome_message else [], slots)
        except asyncio.CancelledError:
            raise
        except Exception:  # pragma: no cover - the steps above already log their own failures
            logger.exception("Call history bootstrap failed bot=%s", self.bot)

    async def _await_bootstrap(self) -> None:
        """Wait until the call's history has been started, so the first turn is recorded after the welcome."""
        if self._bootstrap_task is not None:
            await asyncio.gather(self._bootstrap_task, return_exceptions=True)

    async def _record(self, messages: List[str], slots: Optional[dict] = None) -> None:
        """Store bot-only utterances (welcome, reprompts, goodbyes) and carried slots in the call's chat history."""
        if self._history_recorder is None or (not messages and not slots):
            return
        sender_id = self.call_sid or self.stream_sid or "anonymous"
        try:
            await self._history_recorder(sender_id, list(messages), slots, self.metadata)
        except Exception as e:
            logger.warning("Could not record call history bot=%s: %s", self.bot, e)

    async def _on_media(self, frame: InboundFrame) -> None:
        """Feed one chunk of caller audio to STT."""
        if frame.media_payload:
            try:
                await self.stt.push(frame.media_payload)
            except Exception as e:  # pragma: no cover - network dependent
                logger.warning("STT push failed bot=%s: %s", self.bot, e)

    async def _on_dtmf(self, frame: InboundFrame) -> None:
        """Collect keypad digits and submit them as a turn on the terminator, the max length or the inter-digit timeout."""
        digit = frame.dtmf_digit
        if not self.dtmf_enabled or not digit:
            logger.debug("DTMF ignored (enabled=%s) bot=%s", self.dtmf_enabled, self.bot)
            return
        logger.info("DTMF digit '%s' bot=%s call_sid=%s", digit, self.bot, self.call_sid)
        self._caller_active()
        if digit == self.dtmf_terminator:
            await self._submit_dtmf()
            return
        self._dtmf_buffer += digit
        if len(self._dtmf_buffer) >= self.dtmf_max_length:
            await self._submit_dtmf()
            return
        self._arm_dtmf_timer()

    async def _submit_dtmf(self) -> None:
        """Run the collected digits as one caller turn."""
        digits = self._dtmf_buffer
        self._dtmf_buffer = ""
        self._cancel_dtmf_timer()
        if digits:
            await self._run_turn(digits)

    def _arm_dtmf_timer(self) -> None:
        """(Re)start the inter-digit timeout, if one is configured."""
        self._cancel_dtmf_timer()
        if self.dtmf_timeout > 0:
            self._dtmf_timer = asyncio.ensure_future(self._dtmf_timeout_submit())

    def _cancel_dtmf_timer(self) -> None:
        """Stop the inter-digit timeout (without cancelling itself when the timeout is what submits the digits)."""
        self._cancel_task("_dtmf_timer")

    async def _dtmf_timeout_submit(self) -> None:
        """Submit the digits collected so far once the caller stops pressing keys."""
        try:
            await asyncio.sleep(self.dtmf_timeout)
            await self._submit_dtmf()
        except asyncio.CancelledError:  # pragma: no cover
            pass

    def _on_mark(self, frame: InboundFrame) -> None:
        """Exotel echoes a mark once the audio before it has been played: note it if it is the last one we sent."""
        logger.debug("Mark '%s' acknowledged bot=%s", frame.mark_name, self.bot)
        if frame.mark_name and frame.mark_name == self._last_mark:
            self._mark_event.set()

    async def _on_stop(self, frame: InboundFrame) -> None:
        """The caller (or Exotel) ended the call."""
        logger.info("Exotel stream stopped bot=%s call_sid=%s", self.bot, self.call_sid)
        self.end_reason = self.end_reason or CallEndReason.CALLER_HANGUP.value
        await self.close()

    # --------------------------------------------------------------- transcripts
    async def _consume_transcripts(self) -> None:
        """Turn the STT's final transcripts into agent turns; partial ones only prove the caller is speaking."""
        try:
            async for transcript in self.stt.transcripts():
                text = (transcript.text or "").strip()
                if not transcript.is_final:
                    if text:
                        self._arm_noinput()
                    continue
                if not text:
                    continue
                await self._run_turn(text)
        except asyncio.CancelledError:  # pragma: no cover
            raise
        except Exception as e:  # pragma: no cover - network dependent
            logger.warning("Transcript consumer ended bot=%s: %s", self.bot, e)

    async def _run_turn(self, text: str) -> None:
        """Run one agent turn for what the caller said and play the reply (hanging up if the agent asked to)."""
        if self._closed or self._ending:
            return
        self._caller_active()
        await self._await_bootstrap()
        self._turns += 1
        sender_id = self.call_sid or self.stream_sid or "anonymous"
        agent_start = now_ms()
        try:
            turn = await self.agent_runner(text, sender_id, self.metadata)
        except Exception as e:
            logger.exception("Agent turn failed bot=%s: %s", self.bot, e)
            turn = AgentTurn(messages=["Sorry, something went wrong. Please try again."])
        agent_ms = now_ms() - agent_start
        if turn is None:
            return
        tts_ms = 0.0
        cache_hit = False
        if turn.messages:
            self._last_agent_message = next(
                (m for m in reversed(turn.messages) if m and m.strip()), self._last_agent_message)
            tts_start = now_ms()
            cache_hit = await self._speak(turn.messages)
            tts_ms = now_ms() - tts_start
        if self.metrics is not None:
            try:
                self.metrics.turn(agent_ms, tts_ms, cache_hit)
            except Exception as e:
                logger.debug("Metrics update failed bot=%s: %s", self.bot, e)
        if turn.hangup:
            await self._hangup(CallEndReason.BOT_DISCONNECT.value)
            return
        self._arm_noinput()

    def _caller_active(self) -> None:
        """The caller did something (spoke / pressed a key): stop the silence countdown and forgive past silence."""
        if self._ending:
            return
        self._cancel_task("_noinput_task")
        self._noinput_count = 0

    def _arm_noinput(self) -> None:
        """(Re)start the silence countdown; ``_on_noinput`` fires if the caller says nothing for a while."""
        if self._ending:
            return
        self._cancel_task("_noinput_task")
        if self._closed or self.noinput_timeout <= 0:
            return
        self._noinput_task = asyncio.ensure_future(self._noinput_wait())

    async def _noinput_wait(self) -> None:
        """Sleep through the silence timeout, then handle the silence."""
        try:
            await asyncio.sleep(self.noinput_timeout)
            await self._on_noinput()
        except asyncio.CancelledError:
            return
        except Exception:  # pragma: no cover - a failure here must not silently end the call's timers
            logger.exception("Silence handling failed bot=%s", self.bot)

    async def _on_noinput(self) -> None:
        """Caller stayed silent: repeat the last bot message, then (after ``max_noinput_attempts``) say goodbye and hang up."""
        if self._closed:
            return
        if self._noinput_count >= self.max_noinput_attempts:
            await self._say_and_hangup([self.timeout_message], CallEndReason.NOINPUT_TIMEOUT.value)
            return
        self._noinput_count += 1
        messages = [self._last_agent_message or self.reprompt_phrase]
        await self._speak(messages)
        await self._record(messages)
        self._arm_noinput()

    def _arm_max_duration(self) -> None:
        """Start the call-length cap, if one is configured."""
        self._cancel_task("_max_duration_task")
        if self.max_call_duration > 0:
            self._max_duration_task = asyncio.ensure_future(self._max_duration_wait())

    async def _max_duration_wait(self) -> None:
        """Sleep until the call-length cap, then say goodbye and hang up."""
        try:
            await asyncio.sleep(self.max_call_duration)
            if not self._closed:
                await self._say_and_hangup([self.max_duration_message], CallEndReason.MAX_DURATION.value)
        except asyncio.CancelledError:
            return
        except Exception:  # pragma: no cover - see _noinput_wait
            logger.exception("Max call duration handling failed bot=%s", self.bot)

    async def _say_and_hangup(self, messages: List[str], reason: str) -> None:
        """Speak a final message, record it in the history and hang up."""
        self._ending = True
        await self._speak(messages)
        await self._record(messages)
        await self._hangup(reason)

    async def _hangup(self, reason: str) -> None:
        """End the call from our side: let the last utterance finish playing, close the websocket (that is
        what makes Exotel end the call), then tear the session down."""
        if self._closed:
            return
        self._ending = True
        self.end_reason = self.end_reason or reason
        await self._wait_for_playback()
        if self._closed:
            return
        if self._on_hangup is not None:
            try:
                await self._on_hangup()
            except Exception as e:
                logger.debug("Hangup callback failed bot=%s: %s", self.bot, e)
        await self.close()

    async def _wait_for_playback(self) -> None:
        """Wait (bounded) until Exotel confirms the last utterance has been played."""
        if self._last_mark is None or self._mark_event.is_set():
            return
        try:
            await asyncio.wait_for(self._mark_event.wait(), timeout=PLAYBACK_WAIT_SECONDS)
        except asyncio.TimeoutError:
            logger.debug("Timed out waiting for playback mark bot=%s", self.bot)

    def _cancel_task(self, attr: str) -> None:
        """Cancel a background task, unless it is the one currently running (a task must not cancel itself)."""
        task = getattr(self, attr, None)
        if task is not None and task is not asyncio.current_task():
            task.cancel()
        setattr(self, attr, None)

    async def _speak(self, messages: List[str]) -> bool:
        """Synthesise and stream each message; return True if all were served from TTS cache.

        Serialised: a reprompt, the max-duration goodbye and an agent reply may all want the line at once and
        must never interleave their audio frames."""
        served = False
        all_cached = True
        async with self._speak_lock:
            for message in messages:
                if message and message.strip():
                    served = True
                    cached = await self._stream_tts(message)
                    all_cached = all_cached and cached
        return served and all_cached

    async def _stream_tts(self, text: str) -> bool:
        """Stream one utterance, then a mark; returns True if it was served from the TTS cache."""
        if not self.stream_sid:
            logger.debug("No stream_sid yet; dropping utterance bot=%s", self.bot)
            return False
        cache_key = make_key(self.tts_cache_namespace, text) if self.tts_cache is not None else None
        cached_audio = self.tts_cache.get(cache_key) if cache_key is not None else None
        if cached_audio is not None:
            for frame in chunk_pcm(cached_audio, self.chunk_multiple, self.chunk_max_bytes):
                await self._send_media(frame)
            await self._send_mark()
            return True
        await self._synthesize_and_stream(text, cache_key)
        return False

    async def _synthesize_and_stream(self, text: str, cache_key: Optional[str]) -> None:
        """Synthesise ``text`` and stream it as it arrives; cache the audio, and always end with a mark.

        If synthesis fails part-way the audio already sent still gets its mark, so a following hang-up waits for
        what the caller is actually hearing instead of cutting it off."""
        buffer = bytearray()
        sent_any = False
        chunker = AudioChunker(multiple=self.chunk_multiple, max_bytes=self.chunk_max_bytes)
        try:
            async for pcm in self.tts.synthesize(text):
                if pcm:
                    buffer.extend(pcm)
                chunker.push(pcm)
                for frame in chunker.drain():
                    sent_any = True
                    await self._send_media(frame)
            for frame in chunker.flush():
                sent_any = True
                await self._send_media(frame)
        except Exception as e:
            logger.warning("TTS streaming failed bot=%s: %s", self.bot, e)
            if sent_any:
                await self._send_mark()
            return
        if cache_key is not None and buffer:
            self.tts_cache.put(cache_key, bytes(buffer))
        await self._send_mark()

    async def _send_mark(self) -> None:
        """Send a mark after an utterance; Exotel echoes it back once the audio before it has been played."""
        name = self._next_mark()
        self._last_mark = name
        self._mark_event.clear()
        await self._send(build_mark(self.stream_sid, name))

    async def _send_media(self, frame: bytes) -> None:
        """Send one audio frame, then (when pacing) wait as long as the frame plays so the stream runs in real time."""
        await self._send(build_media(self.stream_sid, frame))
        if self.pace:
            await asyncio.sleep(self._frame_seconds(len(frame)))

    def _frame_seconds(self, nbytes: int) -> float:
        """Playing time of ``nbytes`` of 16-bit mono PCM at the call's sample rate."""
        denom = float(self.sample_rate * 2) or 1.0
        return max(nbytes / denom, 0.0)

    def _next_mark(self) -> str:
        """Name of the next playback mark."""
        self._mark_counter += 1
        return f"utt-{self._mark_counter}"

    async def barge_in(self) -> None:
        """Discard audio already buffered on Exotel's side (interrupt the bot)."""
        if self.stream_sid:
            await self._send(build_clear(self.stream_sid))

    async def close(self) -> None:
        """Tear down STT and the background tasks, emit final metrics and report how the call ended. Idempotent."""
        if self._closed:
            return
        self._closed = True
        self.end_reason = self.end_reason or CallEndReason.CALLER_HANGUP.value
        self._cancel_dtmf_timer()
        for attr in ("_noinput_task", "_max_duration_task", "_consumer_task", "_bootstrap_task"):
            self._cancel_task(attr)
        try:
            await self.stt.close()
        except Exception as e:  # pragma: no cover - adapter specific
            logger.debug("Error closing STT bot=%s: %s", self.bot, e)
        self._finalize_metrics()
        await self._report_call_end()

    def _finalize_metrics(self) -> None:
        """Persist the call's latency metrics."""
        if self.metrics is None:
            return
        try:
            self.metrics.finalize()
        except Exception as e:  # pragma: no cover - sink specific
            logger.debug("Metrics finalize failed bot=%s: %s", self.bot, e)

    async def _report_call_end(self) -> None:
        """Tell the owner of the call (status tracking) why and after how long it ended."""
        if self._on_call_end is None or not self.call_sid:
            return
        duration = (time.monotonic() - self._started_at) if self._started_at else 0.0
        try:
            await self._on_call_end(self.call_sid, self.end_reason, duration)
        except Exception as e:
            logger.debug("Call-end callback failed bot=%s: %s", self.bot, e)
