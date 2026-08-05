"""
Exotel streaming call session — the MVP voice call loop.

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

The WebSocket receive loop, authentication, and construction of the concrete
STT/TTS adapters and agent runner live in the channel handler; this class takes
them as injected collaborators.
"""
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable, List, Optional

from kairon.shared.voice.cache import make_key
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


@dataclass
class AgentTurn:
    """Result of running one turn of the agent brain."""
    messages: List[str] = field(default_factory=list)
    hangup: bool = False


# async (text, sender_id, metadata) -> AgentTurn
AgentRunner = Callable[[str, str, dict], Awaitable[AgentTurn]]
# async (frame_dict) -> None : serialise + send one frame to the websocket
FrameSender = Callable[[dict], Awaitable[None]]


class ExotelCallSession:
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
    ):
        self.bot = bot
        self.config = config or {}
        self._send = sender
        self.stt = stt
        self.tts = tts
        self.agent_runner = agent_runner
        self.metadata = dict(metadata or {})
        self.welcome_message = welcome_message if welcome_message is not None else config.get(
            "welcome_message"
        )
        self.chunk_multiple = chunk_multiple
        self.chunk_max_bytes = chunk_max_bytes
        self.sample_rate = sample_rate
        self.pace = pace
        self.metrics = metrics
        self.tts_cache = tts_cache
        self.tts_cache_namespace = tts_cache_namespace

        dtmf_cfg = (self.config.get("dtmf") or {})
        self.dtmf_enabled = bool(dtmf_cfg.get("enabled", True))
        self.dtmf_terminator = str(dtmf_cfg.get("terminator", "#"))
        self.dtmf_max_length = int(dtmf_cfg.get("max_length", 32))
        self.dtmf_timeout = float(dtmf_cfg.get("inter_digit_timeout", 0) or 0)
        self._dtmf_buffer = ""
        self._dtmf_timer: Optional[asyncio.Task] = None

        self.stream_sid: str = ""
        self.call_sid: str = ""
        self.start_info: Optional[StartInfo] = None
        self._mark_counter = 0
        self._started = False
        self._closed = False
        self._consumer_task: Optional[asyncio.Task] = None

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
        if self._started:
            return
        self._started = True
        self.start_info = frame.start
        self.stream_sid = frame.stream_sid or (frame.start.stream_sid if frame.start else "")
        if frame.start:
            self.call_sid = frame.start.call_sid
            if frame.start.sample_rate:
                self.sample_rate = frame.start.sample_rate
            self.metadata.setdefault("caller_phone", frame.start.from_number)
            self.metadata.setdefault("called_number", frame.start.to_number)
        self.metadata.setdefault("call_sid", self.call_sid or self.stream_sid)
        if self.metrics is not None and not getattr(self.metrics, "call_sid", ""):
            self.metrics.call_sid = self.call_sid or self.stream_sid
        logger.info(
            "Exotel stream started bot=%s stream_sid=%s call_sid=%s",
            self.bot, self.stream_sid, self.call_sid,
        )
        if self.welcome_message:
            await self._speak([self.welcome_message])

    async def _on_media(self, frame: InboundFrame) -> None:
        if frame.media_payload:
            try:
                await self.stt.push(frame.media_payload)
            except Exception as e:  # pragma: no cover - network dependent
                logger.warning("STT push failed bot=%s: %s", self.bot, e)

    async def _on_dtmf(self, frame: InboundFrame) -> None:
        digit = frame.dtmf_digit
        if not self.dtmf_enabled or not digit:
            logger.debug("DTMF ignored (enabled=%s) bot=%s", self.dtmf_enabled, self.bot)
            return
        logger.info("DTMF digit '%s' bot=%s call_sid=%s", digit, self.bot, self.call_sid)
        if digit == self.dtmf_terminator:
            await self._submit_dtmf()
            return
        self._dtmf_buffer += digit
        if len(self._dtmf_buffer) >= self.dtmf_max_length:
            await self._submit_dtmf()
            return
        self._arm_dtmf_timer()

    async def _submit_dtmf(self) -> None:
        digits = self._dtmf_buffer
        self._dtmf_buffer = ""
        self._cancel_dtmf_timer()
        if digits:
            await self._run_turn(digits)

    def _arm_dtmf_timer(self) -> None:
        self._cancel_dtmf_timer()
        if self.dtmf_timeout > 0:
            self._dtmf_timer = asyncio.ensure_future(self._dtmf_timeout_submit())

    def _cancel_dtmf_timer(self) -> None:
        if self._dtmf_timer is not None:
            self._dtmf_timer.cancel()
            self._dtmf_timer = None

    async def _dtmf_timeout_submit(self) -> None:
        try:
            await asyncio.sleep(self.dtmf_timeout)
            await self._submit_dtmf()
        except asyncio.CancelledError:  # pragma: no cover
            pass

    def _on_mark(self, frame: InboundFrame) -> None:
        logger.debug("Mark '%s' acknowledged bot=%s", frame.mark_name, self.bot)

    async def _on_stop(self, frame: InboundFrame) -> None:
        logger.info("Exotel stream stopped bot=%s call_sid=%s", self.bot, self.call_sid)
        await self.close()

    # --------------------------------------------------------------- transcripts
    async def _consume_transcripts(self) -> None:
        try:
            async for transcript in self.stt.transcripts():
                if not transcript.is_final:
                    continue
                text = (transcript.text or "").strip()
                if not text:
                    continue
                await self._run_turn(text)
        except asyncio.CancelledError:  # pragma: no cover
            raise
        except Exception as e:  # pragma: no cover - network dependent
            logger.warning("Transcript consumer ended bot=%s: %s", self.bot, e)

    async def _run_turn(self, text: str) -> None:
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
            tts_start = now_ms()
            cache_hit = await self._speak(turn.messages)
            tts_ms = now_ms() - tts_start
        if self.metrics is not None:
            try:
                self.metrics.turn(agent_ms, tts_ms, cache_hit)
            except Exception:  # pragma: no cover
                pass
        if turn.hangup:
            await self.close()

    # ----------------------------------------------------------------- playback
    async def _speak(self, messages: List[str]) -> bool:
        """Synthesise and stream each message. Returns True if every non-empty
        message was served from the TTS cache."""
        served = False
        all_cached = True
        for message in messages:
            if message and message.strip():
                served = True
                cached = await self._stream_tts(message)
                all_cached = all_cached and cached
        return served and all_cached

    async def _stream_tts(self, text: str) -> bool:
        """Stream one utterance; returns True if it was served from cache."""
        if not self.stream_sid:
            logger.debug("No stream_sid yet; dropping utterance bot=%s", self.bot)
            return False

        cache_key = None
        if self.tts_cache is not None:
            cache_key = make_key(self.tts_cache_namespace, text)
            cached = self.tts_cache.get(cache_key)
            if cached is not None:
                for frame in chunk_pcm(cached, self.chunk_multiple, self.chunk_max_bytes):
                    await self._send_media(frame)
                await self._send(build_mark(self.stream_sid, self._next_mark()))
                return True

        buffer = bytearray()
        chunker = AudioChunker(multiple=self.chunk_multiple, max_bytes=self.chunk_max_bytes)
        try:
            async for pcm in self.tts.synthesize(text):
                if pcm:
                    buffer.extend(pcm)
                chunker.push(pcm)
                for frame in chunker.drain():
                    await self._send_media(frame)
            for frame in chunker.flush():
                await self._send_media(frame)
        except Exception as e:  # pragma: no cover - network dependent
            logger.warning("TTS streaming failed bot=%s: %s", self.bot, e)
            return False
        if cache_key is not None and buffer:
            self.tts_cache.put(cache_key, bytes(buffer))
        await self._send(build_mark(self.stream_sid, self._next_mark()))
        return False

    async def _send_media(self, frame: bytes) -> None:
        await self._send(build_media(self.stream_sid, frame))
        if self.pace:
            await asyncio.sleep(self._frame_seconds(len(frame)))

    def _frame_seconds(self, nbytes: int) -> float:
        # 16-bit mono PCM: bytes / (sample_rate * 2 bytes/sample)
        denom = float(self.sample_rate * 2) or 1.0
        return max(nbytes / denom, 0.0)

    def _next_mark(self) -> str:
        self._mark_counter += 1
        return f"utt-{self._mark_counter}"

    async def barge_in(self) -> None:
        """Discard audio already buffered on Exotel's side (interrupt the bot)."""
        if self.stream_sid:
            await self._send(build_clear(self.stream_sid))

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._cancel_dtmf_timer()
        if self._consumer_task is not None:
            self._consumer_task.cancel()
        try:
            await self.stt.close()
        except Exception as e:  # pragma: no cover
            logger.debug("Error closing STT bot=%s: %s", self.bot, e)
        if self.metrics is not None:
            try:
                self.metrics.finalize()
            except Exception:  # pragma: no cover
                pass
