"""Reports (FR-30, FR-31; §12 `GET /reports/{type}`), scoped by role (§4).

Without `format` the report data is returned for preview (first 500 rows, with summary and chart).
With `format=xlsx|pdf` an export job is queued (202, standards/14); poll `/jobs/{job_id}` and download
`/jobs/{job_id}/file`.
"""

import asyncio
from datetime import UTC, date, datetime
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from facetrack_common.constants import AttendanceStatus, ReportType
from facetrack_common.models import User
from facetrack_common.schemas.envelope import ApiResponse
from fastapi import APIRouter, Query, Response, status
from fastapi.responses import JSONResponse

from app.api.deps import DbDep, ScopeDep
from app.core.db import transaction
from app.core.responses import ok
from app.core.security import CurrentUser, Permission, require_permission
from app.domain.audit import service as audit
from app.domain.reports import export as report_export
from app.domain.reports import service as report_service
from app.domain.settings import service as settings_service
from app.schemas.report import ReportExportAccepted, ReportFilters, ReportOut, SheetExportIn
from app.services import jobs
from app.worker.dispatch import start_report_export

router = APIRouter(prefix="/reports", tags=["reports"])
Reporter = Annotated[User, require_permission(Permission.REPORTS_EXPORT)]
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.post(
    "/sheet",
    response_class=Response,
    responses={200: {"content": {XLSX: {}}, "description": "The Excel file"}},
    summary="Excel file of a list view, with status colours",
)
async def export_sheet(payload: SheetExportIn, db: DbDep, user: CurrentUser) -> Response:
    """§13 "export on every list" as a coloured .xlsx (Q62). The rows are what the user's own list screen
    loaded through the API (at most 10,000), so no extra data is exposed; the export is audit-logged."""
    timezone = str((await settings_service.resolved(db))["general.timezone"])
    generated = f"{datetime.now(UTC).astimezone(ZoneInfo(timezone)):%d-%m-%Y %H:%M} ({timezone})"
    rows = [[(cell.value, cell.tone) for cell in row] for row in payload.rows]
    # XlsxWriter is CPU work: keep it off the event loop.
    data = await asyncio.to_thread(
        report_export.sheet_to_xlsx, payload.title, payload.columns, rows, generated, user.name
    )
    async with transaction(db):
        await audit.record(
            db, user, "list.export", "export", None, new={"title": payload.title, "rows": len(rows)}
        )
    file_name = payload.file_name if payload.file_name.endswith(".xlsx") else f"{payload.file_name}.xlsx"
    return Response(
        data,
        media_type=XLSX,
        headers={"Content-Disposition": f'attachment; filename="{file_name}"', "Cache-Control": "no-store"},
    )


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
