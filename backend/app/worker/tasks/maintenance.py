"""Partitions, stream trimming, retention and temp-file cleanup."""

import logging
import time
from datetime import UTC, date, datetime, timedelta
from typing import Any

from celery import shared_task
from facetrack_common.constants import RECOGNITION_EVENTS_STREAM
from sqlalchemy import text

from app.core.config import get_settings
from app.core.redis import get_sync_redis
from app.domain.retention import service as retention
from app.services import metrics_store
from app.worker import runtime
from app.worker.consumer import GROUP

logger = logging.getLogger(__name__)
_MONTHS_AHEAD = 3
_STREAM_KEEP_S = 24 * 3600


def _month_start(day: date, offset: int) -> date:
    month = day.month - 1 + offset
    return date(day.year + month // 12, month % 12 + 1, 1)


@shared_task(name="app.worker.tasks.maintenance.ensure_event_partitions")
def ensure_event_partitions() -> int:
    """Creates monthly partitions of recognition_events ahead of time (standards/05)."""

    async def handle(db: Any) -> int:
        created = 0
        today = datetime.now(UTC).date()
        for offset in range(0, _MONTHS_AHEAD + 1):
            start, end = _month_start(today, offset), _month_start(today, offset + 1)
            name = f"recognition_events_{start:%Y_%m}"
            exists = await db.scalar(text("SELECT to_regclass(:name) IS NOT NULL"), {"name": name})
            if exists:
                continue
            # DDL cannot take bind parameters; the name and bounds are generated from dates above.
            await db.execute(
                text(
                    f"CREATE TABLE IF NOT EXISTS {name} PARTITION OF recognition_events "
                    f"FOR VALUES FROM ('{start.isoformat()}') TO ('{end.isoformat()}')"
                )
            )
            created += 1
        await db.commit()
        return created

    created = runtime.run_with_session(handle)
    if created:
        logger.info("event partitions created", extra={"count": created})
    return created


@shared_task(name="app.worker.tasks.maintenance.trim_event_stream")
def trim_event_stream() -> int:
    """Drops stream entries older than 24 h that every consumer has acknowledged."""
    client: Any = get_sync_redis()  # redis-py types sync replies as Awaitable | Any
    minid_ms = int((time.time() - _STREAM_KEEP_S) * 1000)
    summary = client.xpending(RECOGNITION_EVENTS_STREAM, GROUP)
    if summary and summary.get("pending"):
        oldest_pending_ms = int(str(summary["min"]).split("-")[0])
        minid_ms = min(minid_ms, oldest_pending_ms)
    return int(client.xtrim(RECOGNITION_EVENTS_STREAM, minid=f"{minid_ms}-0", approximate=True))


@shared_task(name="app.worker.tasks.maintenance.apply_retention")
def apply_retention() -> dict[str, int]:
    async def handle(db: Any) -> dict[str, int]:
        return await retention.apply_retention(db)

    counts = runtime.run_with_session(handle)
    metrics_store.increment("retention_deleted_total", sum(counts.values()))
    return counts


@shared_task(name="app.worker.tasks.maintenance.cleanup_temp_files")
def cleanup_temp_files() -> int:
    """Uploaded import files are deleted after processing; this removes any left by a crash."""
    directory = get_settings().media_root / "tmp-imports"
    if not directory.exists():
        return 0
    cutoff = (datetime.now(UTC) - timedelta(hours=6)).timestamp()
    removed = 0
    for path in directory.iterdir():
        if path.is_file() and path.stat().st_mtime < cutoff:
            path.unlink(missing_ok=True)
            removed += 1
    return removed
