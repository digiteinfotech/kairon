"""
TTS audio cache.

Synthesising the same phrase repeatedly (welcome prompts, re-prompts, "sorry I
didn't catch that", menu options) is wasteful and adds latency to every call.
:class:`TTSCache` is a bounded in-memory LRU keyed by the full synthesis
identity — provider, voice, language, sample rate and text — so two bots (or two
voices) never collide, and it returns the raw PCM ready to be re-framed for
Exotel.

Pure/stdlib-only so it is unit-testable without kairon.
"""
import hashlib
import threading
from collections import OrderedDict
from typing import Optional


def make_key(namespace: str, text: str) -> str:
    """Stable cache key for ``text`` under a synthesis ``namespace`` (typically
    ``"provider:voice:language:sample_rate"``)."""
    digest = hashlib.sha256(f"{namespace}\x00{text}".encode("utf-8")).hexdigest()
    return digest


class TTSCache:
    """Thread-safe bounded LRU cache of synthesised PCM.

    ``max_entries`` caps the number of cached utterances and ``max_bytes`` caps
    total audio held; the least-recently-used entries are evicted when either
    limit is exceeded. ``max_item_bytes`` skips caching utterances too large to
    be worth keeping (long dynamic responses).
    """

    def __init__(self, max_entries: int = 256, max_bytes: int = 32 * 1024 * 1024,
                 max_item_bytes: int = 1 * 1024 * 1024, enabled: bool = True):
        self.max_entries = max(1, max_entries)
        self.max_bytes = max(0, max_bytes)
        self.max_item_bytes = max(0, max_item_bytes)
        self.enabled = enabled
        self._store: "OrderedDict[str, bytes]" = OrderedDict()
        self._bytes = 0
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[bytes]:
        if not self.enabled:
            return None
        with self._lock:
            value = self._store.get(key)
            if value is None:
                self.misses += 1
                return None
            self._store.move_to_end(key)
            self.hits += 1
            return value

    def put(self, key: str, pcm: bytes) -> None:
        if not self.enabled or not pcm:
            return
        if self.max_item_bytes and len(pcm) > self.max_item_bytes:
            return
        with self._lock:
            if key in self._store:
                self._bytes -= len(self._store[key])
                self._store.move_to_end(key)
            self._store[key] = pcm
            self._bytes += len(pcm)
            self._evict()

    def _evict(self) -> None:
        while self._store and (
            len(self._store) > self.max_entries
            or (self.max_bytes and self._bytes > self.max_bytes)
        ):
            _, evicted = self._store.popitem(last=False)
            self._bytes -= len(evicted)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self._bytes = 0

    def __len__(self) -> int:
        return len(self._store)

    @property
    def current_bytes(self) -> int:
        return self._bytes
