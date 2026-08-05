"""
Audio framing helpers for the Exotel streaming gateway.

Exotel accepts outbound media only in payloads whose byte length is a multiple of
``chunk.multiple`` (320 bytes for 8 kHz / 16-bit / 20 ms frames) and bounded by
``chunk.max_bytes``. TTS adapters, however, yield PCM in arbitrary-sized chunks.
:class:`AudioChunker` bridges the two: push raw PCM as it is synthesised, pull
back Exotel-legal frames.

Silence detection (:func:`rms`, :func:`is_silence`) supports utterance
endpointing and barge-in. Everything here is stdlib-only and pure so it can be
unit-tested without kairon/rasa or a live socket.
"""
from typing import Iterator, List, Optional

DEFAULT_MULTIPLE = 320
DEFAULT_MAX_BYTES = 100000
DEFAULT_SILENCE_RMS = 500.0


def frame_multiple(nbytes: int, multiple: int) -> int:
    """Largest multiple of ``multiple`` that is <= ``nbytes`` (0 if smaller)."""
    if multiple <= 0:
        return nbytes
    return (nbytes // multiple) * multiple


def pad_to_multiple(pcm: bytes, multiple: int) -> bytes:
    """Right-pad ``pcm`` with silence (0x00) up to the next multiple of
    ``multiple`` so a final short chunk is still a legal Exotel frame."""
    if multiple <= 0:
        return pcm
    remainder = len(pcm) % multiple
    if remainder == 0:
        return pcm
    return pcm + b"\x00" * (multiple - remainder)


def rms(pcm: bytes) -> float:
    """Root-mean-square amplitude of 16-bit signed little-endian PCM.

    Uses stdlib ``audioop`` when available (fast, C), falling back to a pure
    Python computation on interpreters where ``audioop`` has been removed
    (Python 3.13+). Returns 0.0 for empty/odd-length input.
    """
    if len(pcm) < 2:
        return 0.0
    usable = pcm[: len(pcm) - (len(pcm) % 2)]
    try:  # pragma: no cover - exercised on <3.13
        import audioop

        return float(audioop.rms(usable, 2))
    except Exception:
        pass
    total = 0
    count = 0
    for i in range(0, len(usable), 2):
        sample = int.from_bytes(usable[i:i + 2], "little", signed=True)
        total += sample * sample
        count += 1
    if not count:
        return 0.0
    return (total / count) ** 0.5


def is_silence(pcm: bytes, threshold: float = DEFAULT_SILENCE_RMS) -> bool:
    """True when ``pcm``'s RMS energy is below ``threshold`` (i.e. the caller is
    not speaking). Empty input counts as silence."""
    if not pcm:
        return True
    return rms(pcm) < threshold


class AudioChunker:
    """Buffers PCM and emits Exotel-legal frames.

    Each yielded chunk length is a multiple of ``multiple`` and at most
    ``max_bytes``. By default frames are emitted one ``frame_bytes`` unit at a
    time (``frame_bytes`` defaults to ``multiple`` = one 20 ms frame) so the
    gateway can pace playback to real time and interrupt cleanly on barge-in;
    raise ``frame_bytes`` to batch more audio per send. Bytes that do not fill a
    whole frame are retained until more audio arrives or :meth:`flush` is called
    (which pads the tail with silence).
    """

    def __init__(self, multiple: int = DEFAULT_MULTIPLE, max_bytes: int = DEFAULT_MAX_BYTES,
                 frame_bytes: Optional[int] = None):
        self.multiple = multiple if multiple and multiple > 0 else DEFAULT_MULTIPLE
        max_frame = frame_multiple(max(max_bytes, self.multiple), self.multiple)
        self.max_bytes = max_frame or self.multiple
        unit = frame_bytes if frame_bytes else self.multiple
        unit = frame_multiple(max(unit, self.multiple), self.multiple) or self.multiple
        self.frame_bytes = min(unit, self.max_bytes)
        self._buffer = bytearray()

    def push(self, pcm: Optional[bytes]) -> None:
        if pcm:
            self._buffer.extend(pcm)

    def _emit(self, upto: int) -> Iterator[bytes]:
        sent = 0
        while sent < upto:
            take = min(self.frame_bytes, upto - sent)
            take = frame_multiple(take, self.multiple)
            if take <= 0:
                break
            yield bytes(self._buffer[sent:sent + take])
            sent += take
        if sent:
            del self._buffer[:sent]

    def drain(self) -> Iterator[bytes]:
        """Yield all currently complete frames, keeping any sub-frame remainder."""
        ready = frame_multiple(len(self._buffer), self.multiple)
        yield from self._emit(ready)

    def flush(self) -> Iterator[bytes]:
        """Yield every remaining frame, padding the final short chunk with silence
        so the whole buffer is drained. Call at end of an utterance."""
        if self._buffer:
            padded = pad_to_multiple(bytes(self._buffer), self.multiple)
            self._buffer = bytearray(padded)
        yield from self._emit(len(self._buffer))

    def pending_bytes(self) -> int:
        return len(self._buffer)


def chunk_pcm(pcm: bytes, multiple: int = DEFAULT_MULTIPLE,
              max_bytes: int = DEFAULT_MAX_BYTES) -> List[bytes]:
    """Convenience: split a complete PCM buffer into Exotel-legal frames,
    padding the tail with silence. Equivalent to pushing ``pcm`` into an
    :class:`AudioChunker` and flushing."""
    chunker = AudioChunker(multiple=multiple, max_bytes=max_bytes)
    chunker.push(pcm)
    return list(chunker.flush())
