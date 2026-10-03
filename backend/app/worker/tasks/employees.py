"""Bulk employee import (FR-11), run in the background (standards/14: 202 + job)."""

import logging
from pathlib import Path
from typing import Any

from celery import shared_task
from facetrack_common.models import User

from app.domain.employees import importer
from app.services import jobs
from app.worker import runtime

logger = logging.getLogger(__name__)


@shared_task(name="app.worker.tasks.employees.import_employees")
def import_employees(job_id: str, sheet_path: str, zip_path: str | None, actor_id: int) -> None:
    jobs.update_job_sync(job_id, status="running")

    async def handle(db: Any) -> dict[str, Any]:
        actor = await db.get(User, actor_id)
        if actor is None:
            raise RuntimeError("importing user no longer exists")
        return await importer.import_employees(
            db, Path(sheet_path), Path(zip_path) if zip_path else None, actor
        )

    try:
        result = runtime.run_with_session(handle)
        jobs.update_job_sync(
            job_id,
            status="succeeded",
            result=result,
            message=f"{result['created']} created, {result['updated']} updated",
        )
    except Exception as exc:  # report the failure on the job instead of losing it
        logger.exception("employee import failed", extra={"job_id": job_id})
        jobs.update_job_sync(job_id, status="failed", message=f"Import failed: {type(exc).__name__}")
    finally:
        for path in (sheet_path, zip_path):
            if path:
                Path(path).unlink(missing_ok=True)  # uploaded files are not kept
