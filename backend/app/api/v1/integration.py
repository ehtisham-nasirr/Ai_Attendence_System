"""HR/payroll integration (FR-12, FR-34, FR-35; §12 `/integration/attendance`).

The payroll system authenticates with `X-API-Key`. API keys and manual runs are managed by Super Admins.
"""

from datetime import date
from typing import Annotated

from facetrack_common.models import ApiClient, User
from facetrack_common.schemas.envelope import ApiResponse, PaginatedResponse
from fastapi import APIRouter, Query, status

from app.api.deps import DbDep, PageDep
from app.core.db import transaction
from app.core.responses import created, ok, paginated
from app.core.security import Permission, require_permission, require_scope
from app.domain.audit import service as audit
from app.domain.integration import api_clients, payroll
from app.schemas.integration import (
    ApiClientCreate,
    ApiClientCreated,
    ApiClientOut,
    ApiClientUpdate,
    IntegrationAttendanceOut,
    IntegrationJobAccepted,
)
from app.worker.dispatch import push_payroll_now, sync_hr_now

router = APIRouter(tags=["integration"])
Admin = Annotated[User, require_permission(Permission.SETTINGS_MANAGE)]
PayrollClient = Annotated[ApiClient, require_scope("attendance:read")]


@router.get(
    "/integration/attendance",
    response_model=PaginatedResponse[IntegrationAttendanceOut],
    summary="Finalised attendance for payroll (API key)",
)
async def integration_attendance(
    db: DbDep,
    page: PageDep,
    client: PayrollClient,
    work_date: Annotated[date, Query(alias="date", description="Work date, YYYY-MM-DD")],
) -> PaginatedResponse[IntegrationAttendanceOut]:
    """Only days already finalised by the day-close job are returned (FR-35); call after the day closes.
    Values are the stored attendance including approved corrections."""
    days, total = await payroll.finalised_for_date(db, work_date, page)
    return paginated(
        [payroll.to_out(d) for d in days], page.page, page.page_size, total, "Attendance retrieved."
    )


@router.get("/api-clients", response_model=ApiResponse[list[ApiClientOut]], summary="API keys")
async def list_api_clients(db: DbDep, _: Admin) -> ApiResponse[list[ApiClientOut]]:
    return ok([api_clients.to_out(c) for c in await api_clients.list_clients(db)], "API clients retrieved.")


@router.post(
    "/api-clients",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[ApiClientCreated],
    summary="Create an API key (shown once)",
)
async def create_api_client(
    payload: ApiClientCreate, db: DbDep, actor: Admin
) -> ApiResponse[ApiClientCreated]:
    client, key = await api_clients.create_client(db, payload, actor)
    return created(ApiClientCreated(client=api_clients.to_out(client), api_key=key), "API key created.")


@router.put("/api-clients/{client_id}", response_model=ApiResponse[ApiClientOut], summary="Update an API key")
async def update_api_client(
    client_id: int, payload: ApiClientUpdate, db: DbDep, actor: Admin
) -> ApiResponse[ApiClientOut]:
    client = await api_clients.update_client(db, client_id, payload, actor)
    return ok(api_clients.to_out(client), "API key updated.")


@router.delete(
    "/api-clients/{client_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Revoke an API key"
)
async def revoke_api_client(client_id: int, db: DbDep, actor: Admin) -> None:
    await api_clients.revoke_client(db, client_id, actor)


@router.post(
    "/integration/payroll/push",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ApiResponse[IntegrationJobAccepted],
    summary="Send attendance to the payroll webhook now",
)
async def push_payroll(
    db: DbDep,
    actor: Admin,
    work_date: Annotated[date | None, Query(alias="date", description="Resend one work date")] = None,
) -> ApiResponse[IntegrationJobAccepted]:
    """Without `date`: sends every finalised day changed since the last delivery (as the schedule does)."""
    async with transaction(db):
        await audit.record(
            db, actor, "payroll.push_requested", "integration", None, new={"date": str(work_date)}
        )
    push_payroll_now(work_date.isoformat() if work_date else None)
    return ok(
        IntegrationJobAccepted(task="payroll_push", detail="Payroll push queued."), "Payroll push queued."
    )


@router.post(
    "/integration/hr/sync",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ApiResponse[IntegrationJobAccepted],
    summary="Run the HR sync now",
)
async def run_hr_sync(db: DbDep, actor: Admin) -> ApiResponse[IntegrationJobAccepted]:
    async with transaction(db):
        await audit.record(db, actor, "hr_sync.requested", "integration", None)
    sync_hr_now()
    return ok(IntegrationJobAccepted(task="hr_sync", detail="HR sync queued."), "HR sync queued.")
