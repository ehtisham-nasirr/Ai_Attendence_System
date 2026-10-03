"""Daily attendance, manual entries and corrections (FR-20..FR-26). Scoped by role (§4)."""

from datetime import date
from typing import Annotated

from facetrack_common.constants import AttendanceStatus, CorrectionStatus
from facetrack_common.models import User
from facetrack_common.schemas.envelope import ApiResponse, PaginatedResponse
from fastapi import APIRouter, Query, status

from app.api.deps import DbDep, PageDep, ScopeDep
from app.core.responses import created, ok, paginated
from app.core.security import CurrentUser, Permission, require_permission
from app.domain.attendance import register as register_service
from app.domain.attendance import service as attendance_service
from app.domain.corrections import service as correction_service
from app.repositories import attendance_repo
from app.schemas.attendance import (
    AttendanceDayOut,
    CorrectionCreate,
    CorrectionDecision,
    CorrectionOut,
    CorrectionResult,
    ManualAttendanceCreate,
    RegisterRow,
)

router = APIRouter(tags=["attendance"])
Viewer = Annotated[User, require_permission(Permission.ATTENDANCE_VIEW)]
Corrector = Annotated[User, require_permission(Permission.ATTENDANCE_CORRECT)]


@router.get("/attendance", response_model=PaginatedResponse[AttendanceDayOut], summary="Daily attendance")
async def list_attendance(
    db: DbDep,
    page: PageDep,
    scope: ScopeDep,
    _: Viewer,
    date_from: date | None = None,
    date_to: date | None = None,
    department_id: int | None = None,
    employee_id: int | None = None,
    status: AttendanceStatus | None = None,
) -> PaginatedResponse[AttendanceDayOut]:
    """HR/Admin see everyone, managers their departments, employees only themselves."""
    days, total = await attendance_repo.list_days(
        db,
        page,
        scope,
        date_from=date_from,
        date_to=date_to,
        department_id=department_id,
        employee_id=employee_id,
        status=status,
    )
    return paginated(
        [attendance_service.to_out(d) for d in days],
        page.page,
        page.page_size,
        total,
        "Attendance retrieved.",
    )


@router.get(
    "/attendance/register",
    response_model=PaginatedResponse[RegisterRow],
    summary="Monthly attendance register",
)
async def monthly_register(
    db: DbDep,
    page: PageDep,
    scope: ScopeDep,
    _: Viewer,
    month: Annotated[str, Query(pattern=r"^\d{4}-\d{2}$", description="YYYY-MM")],
    department_id: int | None = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> PaginatedResponse[RegisterRow]:
    """§13 screen 8: one row per employee in scope with a status letter per recorded day."""
    rows, total = await register_service.monthly_register(db, page, scope, month, department_id, search)
    return paginated(rows, page.page, page.page_size, total, "Register retrieved.")


@router.get("/attendance/{day_id}", response_model=ApiResponse[AttendanceDayOut])
async def get_attendance(day_id: int, db: DbDep, scope: ScopeDep, _: Viewer) -> ApiResponse[AttendanceDayOut]:
    return ok(
        attendance_service.to_out(await attendance_service.get_in_scope(db, day_id, scope)),
        "Attendance retrieved.",
    )


@router.post(
    "/attendance",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[AttendanceDayOut],
    summary="Add a manual attendance entry",
)
async def create_manual_entry(
    payload: ManualAttendanceCreate, db: DbDep, scope: ScopeDep, actor: Corrector
) -> ApiResponse[AttendanceDayOut]:
    """FR-25: for a day with no record yet. The reason is mandatory and every value is kept as an
    approved correction for the audit trail."""
    day = await attendance_service.create_manual_day(db, payload, actor, scope)
    return created(attendance_service.to_out(day), "Attendance entry added.")


@router.post(
    "/attendance/{day_id}/corrections",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[CorrectionResult],
    summary="Request or apply a correction",
)
async def correct_attendance(
    day_id: int, payload: CorrectionCreate, db: DbDep, scope: ScopeDep, actor: CurrentUser
) -> ApiResponse[CorrectionResult]:
    """Employees request (pending); HR, Admin and the department's manager apply directly (ADR-0004)."""
    correction, day = await correction_service.request_or_apply(db, day_id, payload, actor, scope)
    result = CorrectionResult(
        correction=correction_service.to_out(correction), attendance=attendance_service.to_out(day)
    )
    message = (
        "Correction applied." if correction.status == CorrectionStatus.APPROVED else "Correction requested."
    )
    return created(result, message)


@router.get("/corrections", response_model=PaginatedResponse[CorrectionOut], summary="Corrections")
async def list_corrections(
    db: DbDep, page: PageDep, scope: ScopeDep, _: Viewer, status: CorrectionStatus | None = None
) -> PaginatedResponse[CorrectionOut]:
    items, total = await attendance_repo.list_corrections(db, page, scope, status)
    return paginated(
        [correction_service.to_out(c) for c in items],
        page.page,
        page.page_size,
        total,
        "Corrections retrieved.",
    )


@router.post("/corrections/{correction_id}/approve", response_model=ApiResponse[CorrectionResult])
async def approve_correction(
    correction_id: int, payload: CorrectionDecision, db: DbDep, scope: ScopeDep, actor: Corrector
) -> ApiResponse[CorrectionResult]:
    correction, day = await correction_service.decide(db, correction_id, True, payload.comment, actor, scope)
    return ok(
        CorrectionResult(
            correction=correction_service.to_out(correction), attendance=attendance_service.to_out(day)
        ),
        "Correction approved.",
    )


@router.post("/corrections/{correction_id}/reject", response_model=ApiResponse[CorrectionResult])
async def reject_correction(
    correction_id: int, payload: CorrectionDecision, db: DbDep, scope: ScopeDep, actor: Corrector
) -> ApiResponse[CorrectionResult]:
    correction, day = await correction_service.decide(db, correction_id, False, payload.comment, actor, scope)
    return ok(
        CorrectionResult(
            correction=correction_service.to_out(correction), attendance=attendance_service.to_out(day)
        ),
        "Correction rejected.",
    )
