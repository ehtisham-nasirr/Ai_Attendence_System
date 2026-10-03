"""Report exports (FR-31) and scheduled report emails (FR-32), run in Celery (standards/14)."""

import logging
from typing import Any

from celery import shared_task
from facetrack_common.constants import ReportType
from facetrack_common.models import User

from app.core.security import DataScope, data_scope
from app.domain.reports import describe
from app.domain.reports import export as report_export
from app.domain.reports import service as report_service
from app.schemas.report import ReportFilters, ReportOut
from app.services import jobs, storage
from app.worker import runtime

logger = logging.getLogger(__name__)

CONTENT_TYPES = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}


async def render_report(
    db: Any, report_type: ReportType, filters: ReportFilters, fmt: str, scope: DataScope, generated_by: str
) -> tuple[ReportOut, bytes]:
    report = await report_service.build_report(db, scope, report_type, filters, limit=None)
    text = await describe.filters_text(db, filters)
    data = (
        report_export.to_xlsx(report, text, generated_by)
        if fmt == "xlsx"
        else report_export.to_pdf(report, text, generated_by)
    )
    return report, data


def file_name(report_type: ReportType, filters: ReportFilters, fmt: str) -> str:
    return f"facetrack-{report_type.value}-{filters.date_from:%Y%m%d}-{filters.date_to:%Y%m%d}.{fmt}"


@shared_task(name="app.worker.tasks.reports.export_report")
def export_report(job_id: str, report_type: str, params: dict[str, Any], fmt: str, actor_id: int) -> None:
    jobs.update_job_sync(job_id, status="running")
    kind = ReportType(report_type)
    filters = ReportFilters.model_validate(params)

    async def handle(db: Any) -> tuple[ReportOut, bytes]:
        actor = await db.get(User, actor_id)
        if actor is None or not actor.is_active:
            raise PermissionError("the requesting user is no longer active")
        # The export sees exactly what the user may see (same scope as the API).
        return await render_report(db, kind, filters, fmt, await data_scope(db, actor), actor.name)

    try:
        report, data = runtime.run_with_session(handle)
        name = storage.new_object_name("exports", fmt)
        storage.put_encrypted(name, data)
        jobs.update_job_sync(
            job_id,
            status="succeeded",
            message=f"{report.total_rows} rows",
            file={
                "path": name,
                "filename": file_name(kind, filters, fmt),
                "content_type": CONTENT_TYPES[fmt],
            },
        )
    except Exception as exc:  # report the failure on the job instead of losing it
        logger.exception("report export failed", extra={"job_id": job_id, "report_type": report_type})
        jobs.update_job_sync(job_id, status="failed", message=f"Export failed: {type(exc).__name__}")
