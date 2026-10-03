"""PyAV stream decoder thread (requirements §10.1 step 1, §10.4, FR-4, standards/17 §3, §8).

- IDLE/COOLDOWN: non-key packets are dropped before decoding (cheaper than `skip_frame=nokey`).
- After switching back to full decoding, packets are dropped until the next keyframe so the decoder
  never produces frames with missing references.
- Dropped streams reconnect with exponential backoff (2 s -> 60 s).
- Decoded frames go into the 1-slot `LatestFrameBuffer`; nothing is queued.
- Error text never contains the stream URL (it can carry camera credentials).
"""

import logging
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import av
import numpy as np

from app.capture.frame_buffer import LatestFrameBuffer
from app.models.base import ImageBGR

logger = logging.getLogger(__name__)

_URL_PATTERN = re.compile(r"[a-zA-Z][a-zA-Z0-9+.-]*://\S+")


def safe_error(exc: BaseException) -> str:
    """Error text with any URL removed, so credentials never reach logs or the API."""
    return _URL_PATTERN.sub("<url>", f"{type(exc).__name__}: {exc}")[:300]


def is_file_source(url: str) -> bool:
    return url.startswith("file://") or not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", url)


@dataclass(frozen=True, slots=True)
class DecoderSettings:
    open_timeout_s: float
    read_timeout_s: float
    threads: int
    reconnect_min_s: float
    reconnect_max_s: float
    allow_file_sources: bool


class StreamDecoder(threading.Thread):
    def __init__(
        self, camera_id: int, url: str, buffer: LatestFrameBuffer, settings: DecoderSettings
    ) -> None:
        super().__init__(name=f"decoder-{camera_id}", daemon=True)
        self.camera_id = camera_id
        self._url = url
        self._buffer = buffer
        self._settings = settings
        self._stop_event = threading.Event()
        self._restart = threading.Event()
        self._keyframes_only = True
        self.connected = False
        self.last_error: str | None = None
        self.reconnects = 0
        self.codec: str | None = None
        self.width: int | None = None
        self.height: int | None = None

    # --- control (called from the processing thread) ---

    def set_keyframes_only(self, value: bool) -> None:
        self._keyframes_only = value

    def switch_source(self, url: str) -> None:
        if url != self._url:
            self._url = url
            self._restart.set()

    def request_restart(self) -> None:
        """Watchdog hook: drop the connection and reconnect."""
        self._restart.set()

    def stop(self) -> None:
        self._stop_event.set()

    # --- thread body ---

    def run(self) -> None:
        backoff = self._settings.reconnect_min_s
        while not self._stop_event.is_set():
            self._restart.clear()
            url = self._url
            try:
                self._decode(url)
                backoff = self._settings.reconnect_min_s
                if is_file_source(url):
                    continue  # dev clips loop forever
            except (av.FFmpegError, OSError, ValueError, StopIteration) as exc:
                self.last_error = safe_error(exc)
                logger.warning(
                    "stream error; reconnecting",
                    extra={"camera_id": self.camera_id, "error": self.last_error, "retry_in_s": backoff},
                )
            finally:
                self.connected = False
            if self._stop_event.is_set() or self._restart.is_set():
                continue
            self.reconnects += 1
            self._stop_event.wait(backoff)
            backoff = min(backoff * 2, self._settings.reconnect_max_s)

    def _open(self, url: str) -> av.container.InputContainer:
        timeout = (self._settings.open_timeout_s, self._settings.read_timeout_s)
        if is_file_source(url):
            if not self._settings.allow_file_sources:
                raise ValueError("file sources are only allowed in development")
            return av.open(str(Path(url.removeprefix("file://"))), timeout=timeout)
        options = {"rtsp_transport": "tcp", "fflags": "nobuffer", "flags": "low_delay"}
        return av.open(url, options=options, timeout=timeout)

    def _decode(self, url: str) -> None:
        with self._open(url) as container:
            stream = container.streams.video[0]
            stream.codec_context.thread_count = self._settings.threads
            self.codec = stream.codec_context.name
            self.width, self.height = stream.codec_context.width, stream.codec_context.height
            self.connected = True
            self.last_error = None
            pace_file = is_file_source(url)
            started = time.monotonic()
            first_pts: float | None = None
            waiting_for_key = True
            was_keyframes_only = self._keyframes_only
            for packet in container.demux(stream):
                if self._stop_event.is_set() or self._restart.is_set():
                    return
                if packet.size == 0:
                    continue
                keyframes_only = self._keyframes_only
                if was_keyframes_only and not keyframes_only:
                    waiting_for_key = True  # resume full decoding cleanly from the next keyframe
                was_keyframes_only = keyframes_only
                if pace_file and packet.pts is not None and packet.time_base is not None:
                    packet_time = float(packet.pts * packet.time_base)
                    first_pts = packet_time if first_pts is None else first_pts
                    delay = (packet_time - first_pts) - (time.monotonic() - started)
                    if delay > 0:
                        self._stop_event.wait(min(delay, 1.0))
                if not packet.is_keyframe and (keyframes_only or waiting_for_key):
                    continue
                if packet.is_keyframe:
                    waiting_for_key = False
                for frame in packet.decode():
                    self._buffer.put(frame.key_frame, datetime.now(UTC), _bgr_converter(frame))


def _bgr_converter(frame: av.VideoFrame) -> Callable[[], ImageBGR]:
    def convert() -> ImageBGR:
        return np.ascontiguousarray(frame.to_ndarray(format="bgr24"))

    return convert
