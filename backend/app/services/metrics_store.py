"""Cross-process operational metrics: Celery tasks write to Redis, the API exports them at /metrics."""

from collections.abc import Iterator

from prometheus_client.core import GaugeMetricFamily
from prometheus_client.registry import Collector

from app.core.redis import get_sync_redis

_HASH = "facetrack:metrics"

DESCRIPTIONS = {
    "event_queue_lag_seconds": "Age of the oldest unprocessed recognition event",
    "event_queue_pending": "Recognition events delivered but not yet acknowledged",
    "events_processed_total": "Recognition events stored by the backend",
    "events_dead_lettered_total": "Invalid recognition events moved to the dead-letter stream",
    "day_close_last_success_timestamp": "Unix time of the last successful day close",
    "payroll_push_failures_total": "Failed payroll pushes (after retries)",
    "payroll_push_last_success_timestamp": "Unix time of the last successful payroll push",
    "hr_sync_failures_total": "Failed HR syncs",
    "hr_sync_last_success_timestamp": "Unix time of the last successful HR sync",
    "cameras_offline": "Cameras currently offline",
    "retention_deleted_total": "Objects/rows deleted by the retention job",
}


def set_value(name: str, value: float) -> None:
    get_sync_redis().hset(_HASH, name, str(value))


def increment(name: str, amount: float = 1.0) -> None:
    get_sync_redis().hincrbyfloat(_HASH, name, amount)


class RedisMetricsCollector(Collector):
    def collect(self) -> Iterator[GaugeMetricFamily]:
        try:
            values = get_sync_redis().hgetall(_HASH)
        except Exception:  # metrics must never break scraping
            return
        for name, description in DESCRIPTIONS.items():
            if name in values:
                yield GaugeMetricFamily(f"facetrack_backend_{name}", description, value=float(values[name]))
