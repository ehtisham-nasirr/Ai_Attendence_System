"""Consumer of the `recognition.events` Redis stream (standards/02 § Event Consumer, NFR-7).

Reads with a consumer group and hands each message to the `process_event` Celery task, which
acknowledges (XACK) only after the event is committed. Messages that stay unacknowledged (worker
crash, database down) are reclaimed and re-dispatched; after too many deliveries they are moved to
the dead-letter stream. Processing is idempotent, so a redelivery never double-counts.
"""

import logging
import os
import socket
import threading
import time
from typing import Any

import redis
from facetrack_common.constants import RECOGNITION_EVENTS_DEAD_LETTER_STREAM, RECOGNITION_EVENTS_STREAM

from app.core.redis import get_sync_redis
from app.services import metrics_store

logger = logging.getLogger(__name__)

GROUP = "backend"
_BATCH = 50
_BLOCK_MS = 1000
_RECLAIM_IDLE_MS = 120_000
_RECLAIM_EVERY_S = 30.0
MAX_DELIVERIES = 10


def ensure_group(client: Any) -> None:  # redis-py types sync replies as Awaitable | Any
    try:
        # "0": on first start, also process events the engines buffered before the backend existed.
        client.xgroup_create(RECOGNITION_EVENTS_STREAM, GROUP, id="0", mkstream=True)
    except redis.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


def ack(message_id: str) -> None:
    get_sync_redis().xack(RECOGNITION_EVENTS_STREAM, GROUP, message_id)


def dead_letter(message_id: str, fields: dict[str, Any], reason: str) -> None:
    client = get_sync_redis()
    client.xadd(
        RECOGNITION_EVENTS_DEAD_LETTER_STREAM,
        {**fields, "error": reason[:500], "source_id": message_id},
        maxlen=100_000,
        approximate=True,
    )
    client.xack(RECOGNITION_EVENTS_STREAM, GROUP, message_id)
    metrics_store.increment("events_dead_lettered_total")


class EventStreamConsumer(threading.Thread):
    def __init__(self, dispatch: Any = None) -> None:
        super().__init__(name="event-stream-consumer", daemon=True)
        self._stop_event = threading.Event()
        self._name = f"{socket.gethostname()}-{os.getpid()}"
        self._dispatch = dispatch or _dispatch_to_celery
        self._last_reclaim = 0.0

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                client = get_sync_redis()
                ensure_group(client)
                self._loop(client)
            except redis.RedisError as exc:
                logger.warning("event stream unavailable; retrying", extra={"error": type(exc).__name__})
                self._stop_event.wait(5.0)

    def _loop(self, client: Any) -> None:
        while not self._stop_event.is_set():
            self.poll_once(client)

    def poll_once(self, client: Any) -> int:
        response = client.xreadgroup(
            GROUP, self._name, {RECOGNITION_EVENTS_STREAM: ">"}, count=_BATCH, block=_BLOCK_MS
        )
        dispatched = 0
        for _, messages in response or []:
            for message_id, fields in messages:
                self._dispatch(message_id, fields)
                dispatched += 1
        if time.monotonic() - self._last_reclaim > _RECLAIM_EVERY_S:
            self._reclaim(client)
            self._export_lag(client)
            self._last_reclaim = time.monotonic()
        return dispatched

    def _reclaim(self, client: Any) -> None:
        _, messages, _ = client.xautoclaim(
            RECOGNITION_EVENTS_STREAM,
            GROUP,
            self._name,
            min_idle_time=_RECLAIM_IDLE_MS,
            start_id="0-0",
            count=_BATCH,
        )
        if not messages:
            return
        details = {
            entry["message_id"]: entry["times_delivered"]
            for entry in client.xpending_range(RECOGNITION_EVENTS_STREAM, GROUP, "-", "+", count=_BATCH * 4)
        }
        for message_id, fields in messages:
            if fields is None:
                continue  # entry was trimmed
            if details.get(message_id, 0) > MAX_DELIVERIES:
                dead_letter(message_id, fields, "too many delivery attempts")
            else:
                self._dispatch(message_id, fields)

    @staticmethod
    def _export_lag(client: Any) -> None:
        summary = client.xpending(RECOGNITION_EVENTS_STREAM, GROUP)
        pending = int(summary.get("pending", 0)) if summary else 0
        lag = 0.0
        if pending and summary.get("min"):
            oldest_ms = int(str(summary["min"]).split("-")[0])
            lag = max(0.0, time.time() - oldest_ms / 1000)
        metrics_store.set_value("event_queue_pending", pending)
        metrics_store.set_value("event_queue_lag_seconds", lag)


def _dispatch_to_celery(message_id: str, fields: dict[str, Any]) -> None:
    from app.worker.tasks.events import process_event  # noqa: PLC0415

    process_event.delay(message_id, fields)
