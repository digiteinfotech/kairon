"""
Per-call voice metrics.

Streaming voice quality lives and dies on latency, so every turn's agent think
time and TTS time are recorded, plus TTS cache hit-rate and total call duration.
:class:`CallMetrics` is a pure aggregator (stdlib only, unit-testable); it invokes
an optional ``sink`` on :meth:`finalize` so persistence (to the
``VoiceCallMetrics`` collection) stays decoupled and swappable.
"""
import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


def now_ms() -> float:
    """Monotonic clock in milliseconds (safe for measuring durations)."""
    return time.monotonic() * 1000.0


@dataclass
class TurnTiming:
    agent_ms: float
    tts_ms: float
    cache_hit: bool = False


@dataclass
class CallMetrics:
    bot: str
    call_sid: str
    provider: str = "exotel"
    stt_provider: str = ""
    tts_provider: str = ""
    sink: Optional[Callable[[Dict], None]] = None
    _turns: List[TurnTiming] = field(default_factory=list)
    _start_ms: float = field(default_factory=now_ms)
    _finalized: bool = False

    def turn(self, agent_ms: float, tts_ms: float, cache_hit: bool = False) -> None:
        self._turns.append(TurnTiming(agent_ms=agent_ms, tts_ms=tts_ms, cache_hit=cache_hit))

    def summary(self) -> Dict:
        agent = [t.agent_ms for t in self._turns]
        tts = [t.tts_ms for t in self._turns]
        cache_hits = sum(1 for t in self._turns if t.cache_hit)
        n = len(self._turns)
        return {
            "bot": self.bot,
            "call_sid": self.call_sid,
            "provider": self.provider,
            "stt_provider": self.stt_provider,
            "tts_provider": self.tts_provider,
            "turns": n,
            "duration_ms": round(now_ms() - self._start_ms, 2),
            "agent_ms_avg": round(sum(agent) / n, 2) if n else 0.0,
            "agent_ms_max": round(max(agent), 2) if agent else 0.0,
            "tts_ms_avg": round(sum(tts) / n, 2) if n else 0.0,
            "tts_ms_max": round(max(tts), 2) if tts else 0.0,
            "tts_cache_hits": cache_hits,
        }

    def finalize(self) -> Dict:
        summary = self.summary()
        if self._finalized:
            return summary
        self._finalized = True
        if self.sink is not None:
            try:
                self.sink(summary)
            except Exception as e:  # pragma: no cover - persistence is best-effort
                logger.warning("Voice metrics sink failed bot=%s: %s", self.bot, e)
        return summary


def persist_call_metrics(summary: Dict) -> None:
    """Sink that writes a metrics summary to the ``VoiceCallMetrics`` collection.
    Lazy-imports the document so importing this module never touches mongoengine."""
    from kairon.shared.voice.data_objects import VoiceCallMetrics

    VoiceCallMetrics(
        bot=summary.get("bot"),
        call_sid=summary.get("call_sid"),
        provider=summary.get("provider", "exotel"),
        stt_provider=summary.get("stt_provider", ""),
        tts_provider=summary.get("tts_provider", ""),
        turns=summary.get("turns", 0),
        duration_ms=summary.get("duration_ms", 0.0),
        agent_ms_avg=summary.get("agent_ms_avg", 0.0),
        agent_ms_max=summary.get("agent_ms_max", 0.0),
        tts_ms_avg=summary.get("tts_ms_avg", 0.0),
        tts_ms_max=summary.get("tts_ms_max", 0.0),
        tts_cache_hits=summary.get("tts_cache_hits", 0),
    ).save()
