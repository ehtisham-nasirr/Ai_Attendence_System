"""Event delivery (FR-16, §10.1 step 11): snapshot to object storage, event to `recognition.events`.

Runs in its own thread inside each camera process, so a slow Redis or object store never stalls frame
processing. If delivery fails, events go to the encrypted disk buffer and are replayed in order
when the services come back (NFR-7). The in-memory hand-off queue is bounded; when it is full the
event goes straight to the disk buffer. Every event gets a sequence number when emitted and buffered
files are named by it, and replay only starts once the hand-off queue is empty, so events are always
delivered in emission order.
"""

import logging
import queue
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from facetrack_common.constants import CRYPTO_PURPOSE_IMAGE, RECOGNITION_EVENTS_STREAM
from facetrack_common.crypto import Cipher
from facetrack_common.events import RecognitionEvent
from facetrack_common.storage import ObjectStore

from app.publisher.disk_buffer import DiskBuffer

logger = logging.getLogger(__name__)

_REPLAY_BATCH = 50


class EventSink(Protocol):
    def put_snapshot(self, object_path: str, data: bytes) -> None: ...

    def publish(self, fields: dict[str, str]) -> None: ...


class RedisStoreSink:
    """Production sink: snapshot bytes (already encrypted) to object storage, event to Redis."""

    def __init__(self, redis_url: str, store: ObjectStore) -> None:
        import redis  # noqa: PLC0415

        self._redis = redis.Redis.from_url(redis_url, socket_timeout=3, socket_connect_timeout=3)
        self._store = store

    def put_snapshot(self, object_path: str, data: bytes) -> None:
        self._store.put(object_path, data)

    def publish(self, fields: dict[str, str]) -> None:
        # No MAXLEN: the backend trims entries only after it has acknowledged them.
        self._redis.xadd(RECOGNITION_EVENTS_STREAM, fields)  # type: ignore[arg-type]


def snapshot_object_path(captured_at: datetime, event_id: str) -> str:
    """`snapshots/YYYY/MM/DD/<event_id>.jpg` (§10.2); the object content is AES-256-GCM ciphertext."""
    return f"snapshots/{captured_at:%Y/%m/%d}/{event_id}.jpg"


@dataclass
class _Pending:
    seq: int
    event: RecognitionEvent
    snapshot_jpeg: bytes


class EventPublisher(threading.Thread):
    def __init__(self, sink: EventSink, buffer: DiskBuffer, cipher: Cipher, queue_size: int) -> None:
        super().__init__(name="event-publisher", daemon=True)
        self._sink = sink
        self._buffer = buffer
        self._cipher = cipher
        self._queue: queue.Queue[_Pending] = queue.Queue(maxsize=queue_size)
        self._stop_event = threading.Event()
        self._buffer_lock = threading.Lock()
        self._seq_lock = threading.Lock()
        self._seq = buffer.last_seq
        self.delivered = 0
        self.failed_deliveries = 0
        self.lost = 0  # refused by a full disk buffer: should never happen; alert on it

    @property
    def buffered(self) -> int:
        return len(self._buffer)

    def emit(self, event: RecognitionEvent, snapshot_jpeg: bytes) -> None:
        """Called from the processing loop. Never blocks."""
        with self._seq_lock:
            self._seq += 1
            item = _Pending(self._seq, event, snapshot_jpeg)
        try:
            self._queue.put_nowait(item)
        except queue.Full:
            self._to_disk(item)

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        self.join(timeout)

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                item = self._queue.get(timeout=0.5)
            except queue.Empty:
                self._replay()
                continue
            if len(self._buffer) > 0:
                self._to_disk(item)  # keep order: older buffered events go first
                if self._queue.empty():
                    self._replay()
            elif not self._deliver(item.event, item.snapshot_jpeg):
                self._to_disk(item)
        # Flush what is left in memory to disk so nothing is lost on shutdown.
        while True:
            try:
                self._to_disk(self._queue.get_nowait())
            except queue.Empty:
                break

    def _deliver(self, event: RecognitionEvent, snapshot_jpeg: bytes) -> bool:
        try:
            if event.snapshot_path and snapshot_jpeg:
                self._sink.put_snapshot(
                    event.snapshot_path, self._cipher.encrypt(snapshot_jpeg, CRYPTO_PURPOSE_IMAGE)
                )
            self._sink.publish(event.to_stream_fields())
        except Exception as exc:  # any sink failure means "buffer and retry later"
            self.failed_deliveries += 1
            logger.warning("event delivery failed; buffering", extra={"error": type(exc).__name__})
            return False
        self.delivered += 1
        return True

    def _to_disk(self, item: _Pending) -> None:
        with self._buffer_lock:
            stored = self._buffer.append(
                {"event": item.event.model_dump(mode="json")}, item.snapshot_jpeg, seq=item.seq
            )
        if not stored:
            self.lost += 1
            logger.critical(
                "event buffer full; event dropped", extra={"event_uuid": str(item.event.event_id)}
            )

    def _replay(self) -> None:
        with self._buffer_lock:
            if len(self._buffer) == 0:
                return
            for record in list(self._buffer.oldest(_REPLAY_BATCH)):
                event = RecognitionEvent.model_validate(record.header["event"])
                if not self._deliver(event, record.blob):
                    return  # still down; keep order and try again later
                self._buffer.remove(record)
