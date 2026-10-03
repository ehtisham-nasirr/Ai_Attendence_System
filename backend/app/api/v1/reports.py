"""Reports (FR-30, FR-31; §12 `GET /reports/{type}`), scoped by role (§4).

Without `format` the report data is returned for preview (first 500 rows, with summary and chart).
With `format=xlsx|pdf` an export job is queued (202, standards/14); poll `/jobs/{job_id}` and download
`/jobs/{job_id}/file`.
"""

from datetime import date
from typing import Annotated, Literal

from facetrack_common.constants import AttendanceStatus, ReportType
from facetrack_common.models import User
from facetrack_common.schemas.envelope import ApiResponse
from fastapi import APIRouter, Query, status
from fastapi.responses import JSONResponse

from app.api.deps import DbDep, ScopeDep
from app.core.db import transaction
from app.core.responses import ok
from app.core.security import Permission, require_permission
from app.domain.audit import service as audit
from app.domain.reports import service as report_service
from app.schemas.report import ReportExportAccepted, ReportFilters, ReportOut
from app.services import jobs
from app.worker.dispatch import start_report_export

router = APIRouter(prefix="/reports", tags=["reports"])
Reporter = Annotated[User, require_permission(Permission.REPORTS_EXPORT)]


@router.get(
    "/{report_type}",
    response_model=ApiResponse[ReportOut],
    responses={202: {"model": ApiResponse[ReportExportAccepted], "description": "Export job queued"}},
    summary="Report data, or an Excel/PDF export job",
)
async def get_report(
    report_type: ReportType,
    db: DbDep,
    scope: ScopeDep,
    actor: Reporter,
    date_from: date,
    date_to: date,
    department_id: int | None = None,
    employee_id: int | None = None,
    status_filter: Annotated[AttendanceStatus | None, Query(alias="status")] = None,
    export_format: Annotated[Literal["xlsx", "pdf"] | None, Query(alias="format")] = None,
) -> ApiResponse[ReportOut] | JSONResponse:
    filters = ReportFilters(
        date_from=date_from,
        date_to=date_to,
        department_id=department_id,
        employee_id=employee_id,
        status=status_filter,
    )
    report_service.validate_filters(report_type, filters)
    if export_format is None:
        report = await report_service.build_report(
            db, scope, report_type, filters, limit=report_service.PREVIEW_ROWS
        )
        return ok(report, "Report generated.")

    job_id = await jobs.create_job("report_export", actor.id)
    params = filters.model_dump(mode="json")
    async with transaction(db):
        await audit.record(
            db, actor, "report.export", "report", report_type.value, new={**params, "format": export_format}
        )
    start_report_export(job_id, report_type.value, params, export_format, actor.id)
    body = ApiResponse[ReportExportAccepted](
        message="Export started.", data=ReportExportAccepted(job_id=job_id)
    ).model_dump(mode="json")
    return JSONResponse(body, status_code=status.HTTP_202_ACCEPTED)
