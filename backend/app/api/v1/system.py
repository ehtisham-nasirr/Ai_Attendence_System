"""Dashboard, settings, audit log, background jobs and health."""

from datetime import datetime
from typing import Annotated, Any

from facetrack_common.models import User
from facetrack_common.schemas.envelope import ApiResponse, PaginatedResponse
from fastapi import APIRouter
from fastapi.responses import Response
from sqlalchemy import text

from app.api.deps import DbDep, PageDep, ScopeDep
from app.core.exceptions import NotFound
from app.core.redis import get_async_redis
from app.core.responses import ok, paginated
from app.core.security import CurrentUser, Permission, require_permission
from app.domain.dashboard import service as dashboard_service
from app.domain.settings import service as settings_service
from app.repositories import system_repo
from app.schemas.system import AuditLogOut, DashboardSummary, JobOut, SettingItem, SettingsUpdate
from app.services import jobs, storage

router = APIRouter(tags=["system"])
Admin = Annotated[User, require_permission(Permission.SETTINGS_MANAGE)]
Auditor = Annotated[User, require_permission(Permission.AUDIT_VIEW)]
DashboardUser = Annotated[User, require_permission(Permission.DASHBOARD_VIEW)]


@router.get("/dashboard/summary", response_model=ApiResponse[DashboardSummary], summary="Today's counters")
async def dashboard_summary(
    db: DbDep, scope: ScopeDep, _: DashboardUser, location_id: int | None = None
) -> ApiResponse[DashboardSummary]:
    return ok(await dashboard_service.summary(db, scope, location_id), "Dashboard retrieved.")


@router.get("/settings", response_model=ApiResponse[list[SettingItem]], summary="System settings")
async def get_settings(db: DbDep, _: Admin) -> ApiResponse[list[SettingItem]]:
    return ok(await settings_service.list_items(db), "Settings retrieved.")


@router.put("/settings", response_model=ApiResponse[list[SettingItem]], summary="Update settings")
async def update_settings(payload: SettingsUpdate, db: DbDep, actor: Admin) -> ApiResponse[list[SettingItem]]:
    """FR-38. Each key is validated against its definition; secrets are stored encrypted and never
    returned. Recognition/engine changes make the engines re-sync."""
    return ok(await settings_service.update(db, payload.values, actor), "Settings updated.")


@router.get("/audit-logs", response_model=PaginatedResponse[AuditLogOut], summary="Audit trail")
async def list_audit_logs(
    db: DbDep,
    page: PageDep,
    _: Auditor,
    user_id: int | None = None,
    action: str | None = None,
    entity: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> PaginatedResponse[AuditLogOut]:
    rows, total = await system_repo.list_audit(
        db, page, user_id=user_id, action=action, entity=entity, date_from=date_from, date_to=date_to
    )
    items = []
    for log, name in rows:
        out = AuditLogOut.model_validate(log)
        out.user_name = name
        items.append(out)
    return paginated(items, page.page, page.page_size, total, "Audit log retrieved.")


async def _owned_job(job_id: str, user: User) -> dict[str, Any]:
    job = await jobs.get_job(job_id)
    if job is None or job.get("owner") != user.id:
        raise NotFound("Job not found.")
    return job


@router.get("/jobs/{job_id}", response_model=ApiResponse[JobOut], summary="Background job status")
async def get_job(job_id: str, user: CurrentUser) -> ApiResponse[JobOut]:
    job = await _owned_job(job_id, user)
    out = JobOut.model_validate({**job, "file_available": bool(job.get("file"))})
    return ok(out, "Job retrieved.")


@router.get("/jobs/{job_id}/file", response_class=Response, summary="Download a job's output file")
async def get_job_file(job_id: str, user: CurrentUser) -> Response:
    job = await _owned_job(job_id, user)
    file_info = job.get("file")
    if not isinstance(file_info, dict):
        raise NotFound("No file for this job.")
    data = storage.get_decrypted(str(file_info["path"]))
    return Response(
        data,
        media_type=str(file_info["content_type"]),
        headers={
            "Content-Disposition": f'attachment; filename="{file_info["filename"]}"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/health", response_model=ApiResponse[dict[str, str]], summary="Liveness and readiness")
async def health(db: DbDep) -> ApiResponse[dict[str, str]]:
    checks = {"database": "ok", "redis": "ok"}
    try:
        await db.execute(text("SELECT 1"))
    except Exception:  # health reports instead of raising
        checks["database"] = "unavailable"
    try:
        await get_async_redis().ping()
    except Exception:
        checks["redis"] = "unavailable"
    checks["status"] = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return ok(checks, "Health checked.")
