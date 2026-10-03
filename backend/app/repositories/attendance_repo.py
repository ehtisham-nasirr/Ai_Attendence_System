"""Attendance days and corrections."""

from datetime import date

from facetrack_common.constants import AttendanceStatus, CorrectionField, CorrectionStatus
from facetrack_common.models import AttendanceCorrection, AttendanceDay, Employee
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.pagination import PageParams, apply_sort, fetch_page
from app.core.security import DataScope

_SORT = {
    "work_date": AttendanceDay.work_date,
    "check_in_at": AttendanceDay.check_in_at,
    "check_out_at": AttendanceDay.check_out_at,
    "status": AttendanceDay.status,
    "late_minutes": AttendanceDay.late_minutes,
}


def scope_filter(stmt, scope: DataScope):  # type: ignore[no-untyped-def]
    """Restricts a statement joined with Employee to the user's data scope (§4)."""
    if scope.all_employees:
        return stmt
    if scope.employee_id is not None:
        return stmt.where(Employee.id == scope.employee_id)
    return stmt.where(Employee.department_id.in_(scope.department_ids or {-1}))


async def get_or_create_for_update(
    db: AsyncSession, employee_id: int, work_date: date, shift_id: int | None
) -> AttendanceDay:
    """Row lock on (employee, work_date); concurrent events for the same day serialise here."""
    await db.execute(
        insert(AttendanceDay)
        .values(
            employee_id=employee_id,
            work_date=work_date,
            shift_id=shift_id,
            worked_minutes=0,
            late_minutes=0,
            early_minutes=0,
            overtime_minutes=0,
            is_manual=False,
        )
        .on_conflict_do_nothing(constraint="uq_attendance_days_employee_work_date")
    )
    stmt = (
        select(AttendanceDay)
        .where(AttendanceDay.employee_id == employee_id, AttendanceDay.work_date == work_date)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return (await db.scalars(stmt)).one()


async def get(db: AsyncSession, day_id: int, *, for_update: bool = False) -> AttendanceDay | None:
    stmt = (
        select(AttendanceDay)
        .options(
            selectinload(AttendanceDay.employee).selectinload(Employee.department),
            selectinload(AttendanceDay.employee).selectinload(Employee.location),
            selectinload(AttendanceDay.shift),
        )
        .where(AttendanceDay.id == day_id)
        .execution_options(populate_existing=True)
    )
    if for_update:
        stmt = stmt.with_for_update(of=AttendanceDay)
    return (await db.scalars(stmt)).first()


async def find(db: AsyncSession, employee_id: int, work_date: date) -> AttendanceDay | None:
    stmt = select(AttendanceDay).where(
        AttendanceDay.employee_id == employee_id, AttendanceDay.work_date == work_date
    )
    return (await db.scalars(stmt)).first()


async def list_days(
    db: AsyncSession,
    params: PageParams,
    scope: DataScope,
    *,
    date_from: date | None,
    date_to: date | None,
    department_id: int | None,
    employee_id: int | None,
    status: AttendanceStatus | None,
) -> tuple[list[AttendanceDay], int]:
    stmt = (
        select(AttendanceDay)
        .join(Employee, Employee.id == AttendanceDay.employee_id)
        .options(
            selectinload(AttendanceDay.employee).selectinload(Employee.department),
            selectinload(AttendanceDay.shift),
        )
        .where(Employee.deleted_at.is_(None))
    )
    stmt = scope_filter(stmt, scope)
    if date_from:
        stmt = stmt.where(AttendanceDay.work_date >= date_from)
    if date_to:
        stmt = stmt.where(AttendanceDay.work_date <= date_to)
    if department_id:
        stmt = stmt.where(Employee.department_id == department_id)
    if employee_id:
        stmt = stmt.where(AttendanceDay.employee_id == employee_id)
    if status:
        stmt = stmt.where(AttendanceDay.status == status)
    sort = apply_sort(
        stmt, params.sort, {**_SORT, "employee_code": Employee.employee_code}, Employee.employee_code
    )
    return await fetch_page(db, sort, params)


async def days_on(db: AsyncSession, work_date: date) -> dict[int, AttendanceDay]:
    rows = await db.scalars(select(AttendanceDay).where(AttendanceDay.work_date == work_date))
    return {row.employee_id: row for row in rows}


async def locked_fields(db: AsyncSession, day_id: int) -> dict[CorrectionField, str]:
    """Approved corrections per field (latest wins): these fields are no longer automatic (ADR-0004)."""
    stmt = (
        select(AttendanceCorrection.field, AttendanceCorrection.new_value)
        .where(
            AttendanceCorrection.attendance_day_id == day_id,
            AttendanceCorrection.status == CorrectionStatus.APPROVED,
        )
        .order_by(AttendanceCorrection.approved_at, AttendanceCorrection.id)
    )
    return {field: value for field, value in (await db.execute(stmt)).all()}


async def locked_fields_for_days(
    db: AsyncSession, day_ids: list[int]
) -> dict[int, dict[CorrectionField, str]]:
    if not day_ids:
        return {}
    stmt = (
        select(
            AttendanceCorrection.attendance_day_id, AttendanceCorrection.field, AttendanceCorrection.new_value
        )
        .where(
            AttendanceCorrection.attendance_day_id.in_(day_ids),
            AttendanceCorrection.status == CorrectionStatus.APPROVED,
        )
        .order_by(AttendanceCorrection.approved_at, AttendanceCorrection.id)
    )
    result: dict[int, dict[CorrectionField, str]] = {}
    for day_id, field, value in (await db.execute(stmt)).all():
        result.setdefault(day_id, {})[field] = value
    return result


# --- corrections ---


async def get_correction(
    db: AsyncSession, correction_id: int, *, for_update: bool = False
) -> AttendanceCorrection | None:
    stmt = (
        select(AttendanceCorrection)
        .options(
            selectinload(AttendanceCorrection.attendance_day).selectinload(AttendanceDay.employee),
            selectinload(AttendanceCorrection.requester),
            selectinload(AttendanceCorrection.approver),
        )
        .where(AttendanceCorrection.id == correction_id)
        .execution_options(populate_existing=True)
    )
    if for_update:
        stmt = stmt.with_for_update(of=AttendanceCorrection)
    return (await db.scalars(stmt)).first()


async def list_corrections(
    db: AsyncSession, params: PageParams, scope: DataScope, status: CorrectionStatus | None
) -> tuple[list[AttendanceCorrection], int]:
    stmt = (
        select(AttendanceCorrection)
        .join(AttendanceDay, AttendanceDay.id == AttendanceCorrection.attendance_day_id)
        .join(Employee, Employee.id == AttendanceDay.employee_id)
        .options(
            selectinload(AttendanceCorrection.attendance_day).selectinload(AttendanceDay.employee),
            selectinload(AttendanceCorrection.requester),
            selectinload(AttendanceCorrection.approver),
        )
    )
    stmt = scope_filter(stmt, scope)
    if status:
        stmt = stmt.where(AttendanceCorrection.status == status)
    sort = apply_sort(
        stmt,
        params.sort or "-created_at",
        {"created_at": AttendanceCorrection.created_at},
        AttendanceCorrection.id,
    )
    return await fetch_page(db, sort, params)
