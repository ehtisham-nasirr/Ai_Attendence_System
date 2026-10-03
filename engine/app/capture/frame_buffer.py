"""Latest-frame-only buffer (requirements §10.4, standards/17 §3).

One slot that the decoder overwrites. Processing always takes the newest frame; if processing is slow,
older frames are dropped, never queued, so lag and memory cannot grow.
"""

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from app.models.base import ImageBGR


@dataclass(frozen=True, slots=True)
class FrameItem:
    seq: int
    decoded_at: float  # time.monotonic() when decoded
    wall_time: datetime  # UTC wall clock when decoded (event `captured_at`)
    is_keyframe: bool
    # Conversion to BGR is deferred until a frame is actually processed (it is not free at 1080p).
    to_bgr: Callable[[], ImageBGR]


class LatestFrameBuffer:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._item: FrameItem | None = None
        self._taken_seq = 0
        self.frames_written = 0
        self.frames_dropped = 0
        self.last_write_monotonic: float | None = None

    def put(self, is_keyframe: bool, wall_time: datetime, to_bgr: Callable[[], ImageBGR]) -> None:
        now = self._clock()
        with self._lock:
            if self._item is not None and self._item.seq > self._taken_seq:
                self.frames_dropped += 1  # overwritten before anyone processed it
            self.frames_written += 1
            self._item = FrameItem(self.frames_written, now, wall_time, is_keyframe, to_bgr)
            self.last_write_monotonic = now

    def take_latest(self) -> FrameItem | None:
        """The newest frame not yet taken, or None if nothing new arrived."""
        with self._lock:
            if self._item is None or self._item.seq <= self._taken_seq:
                return None
            self._taken_seq = self._item.seq
            return self._item

    def clear(self) -> None:
        with self._lock:
            self._item = None
            self._taken_seq = self.frames_written
