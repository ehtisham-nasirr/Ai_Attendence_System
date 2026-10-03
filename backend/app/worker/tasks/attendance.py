"""Day close (FR-23): finalises due employee-days. Idempotent — re-running changes nothing."""

import logging
import time
from datetime import date
from typing import Any

from celery import shared_task

from app.domain.attendance import service
from app.services import metrics_store
from app.worker import runtime

logger = logging.getLogger(__name__)


@shared_task(name="app.worker.tasks.attendance.close_due_days")
def close_due_days() -> int:
    async def handle(db: Any) -> int:
        return await service.close_due_days(db)

    finalised = runtime.run_with_session(handle)
    metrics_store.set_value("day_close_last_success_timestamp", time.time())
    if finalised:
        logger.info("days closed", extra={"finalised": finalised})
    return finalised


@shared_task(name="app.worker.tasks.attendance.recompute_date")
def recompute_date(work_date: str) -> int:
    async def handle(db: Any) -> int:
        return await service.recompute_date(db, date.fromisoformat(work_date))

    return runtime.run_with_session(handle)
