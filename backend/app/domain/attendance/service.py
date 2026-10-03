"""Attendance processing (FR-20..FR-25): turns recognised events into attendance days.

A day is always recomputed from all of its non-voided events (`rules.derive_times`), so the result
does not depend on arrival order: replayed, late or voided events give the same answer (NFR-7).
Approved corrections lock their field (ADR-0004); everything else is recomputed by the rules.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from facetrack_common.constants import (
    ATTENDANCE_STATUS_LETTERS,
    AttendanceStatus,
    CorrectionField,
    CorrectionStatus,
    EmployeeStatus,
)
from facetrack_common.models import AttendanceCorrection, AttendanceDay, Employee, Holiday, Leave, Shift, User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import transaction
from app.core.exceptions import Conflict, NotFound, PermissionDenied
from app.core.security import DataScope
from app.domain.attendance import rules
from app.domain.audit import service as audit
from app.domain.settings import service as settings_service
from app.repositories import attendance_repo, camera_repo, employee_repo, event_repo
from app.schemas.attendance import AttendanceDayOut, ManualAttendanceCreate

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmployeeContext:
    shift: rules.ShiftRule | None
    tz: ZoneInfo
    settings: rules.RuleSettings


def shift_rule(shift: Shift | None) -> rules.ShiftRule | None:
    if shift is None or shift.deleted_at is not None:
        return None
    return rules.ShiftRule(
        start_time=shift.start_time,
        end_time=shift.end_time,
        grace_in_min=shift.grace_in_min,
        grace_out_min=shift.grace_out_min,
        half_day_pct=shift.half_day_pct,
        is_night_shift=shift.is_night_shift,
        weekly_offs=frozenset(int(d) for d in (shift.weekly_offs or [])),
    )


def employee_context(employee: Employee, values: dict[str, Any]) -> EmployeeContext:
    tz_name = employee.location.timezone if employee.location else str(values["general.timezone"])
    return EmployeeContext(
        shift_rule(employee.shift), ZoneInfo(tz_name), settings_service.rule_settings(values)
    )


def day_window(work_date: date, ctx: EmployeeContext) -> tuple[datetime, datetime]:
    """(exclusive start, inclusive end) of the instants that belong to `work_date`."""
    start = rules.day_close_at(work_date - timedelta(days=1), ctx.shift, ctx.tz, ctx.settings)
    return start, rules.day_close_at(work_date, ctx.shift, ctx.tz, ctx.settings)


async def _is_holiday(db: AsyncSession, employee: Employee, work_date: date) -> bool:
    if employee.location_id is None:
        return False
    stmt = select(Holiday.id).where(
        Holiday.location_id == employee.location_id, Holiday.date == work_date, Holiday.deleted_at.is_(None)
    )
    return (await db.scalars(stmt)).first() is not None


async def _on_leave(db: AsyncSession, employee_id: int, work_date: date) -> bool:
    stmt = select(Leave.id).where(
        Leave.employee_id == employee_id,
        Leave.deleted_at.is_(None),
        Leave.from_date <= work_date,
        Leave.to_date >= work_date,
    )
    return (await db.scalars(stmt)).first() is not None


async def _has_exit_cameras(db: AsyncSession, employee: Employee) -> bool:
    if employee.location_id is None:
        return True  # unknown location: keep the stricter "exit cameras only" rule
    return await camera_repo.location_has_exit_cameras(db, employee.location_id)


async def recompute_day(
    db: AsyncSession,
    employee: Employee,
    work_date: date,
    values: dict[str, Any],
    *,
    finalize: bool = False,
) -> AttendanceDay:
    """Recomputes one employee-day from events, corrections, leave and holidays. Caller owns the
    transaction; the row is locked for the rest of it."""
    ctx = employee_context(employee, values)
    day = await attendance_repo.get_or_create_for_update(db, employee.id, work_date, employee.shift_id)
    start, end = day_window(work_date, ctx)
    sightings = [
        rules.Sighting(event_id, captured_at, camera_id, role)
        for event_id, captured_at, camera_id, role in await event_repo.employee_sightings(
            db, employee.id, start, end
        )
    ]
    check_in, check_out = rules.derive_times(sightings, ctx.settings, await _has_exit_cameras(db, employee))
    locked = await attendance_repo.locked_fields(db, day.id)

    day.check_in_at, day.check_in_event_id = (
        (_parse_locked(locked[CorrectionField.CHECK_IN_AT]), None)
        if CorrectionField.CHECK_IN_AT in locked
        else (check_in.captured_at if check_in else None, check_in.event_id if check_in else None)
    )
    day.check_out_at, day.check_out_event_id = (
        (_parse_locked(locked[CorrectionField.CHECK_OUT_AT]), None)
        if CorrectionField.CHECK_OUT_AT in locked
        else (check_out.captured_at if check_out else None, check_out.event_id if check_out else None)
    )
    if day.check_in_at and day.check_out_at and day.check_out_at <= day.check_in_at:
        day.check_out_at, day.check_out_event_id = None, None
    manual_status = (
        AttendanceStatus(locked[CorrectionField.STATUS]) if CorrectionField.STATUS in locked else None
    )

    finalize = finalize or day.finalized_at is not None
    result = rules.compute_day(
        rules.DayInputs(
            work_date=work_date,
            shift=ctx.shift,
            tz=ctx.tz,
            check_in=day.check_in_at,
            check_out=day.check_out_at,
            on_leave=await _on_leave(db, employee.id, work_date),
            holiday=await _is_holiday(db, employee, work_date),
            manual_status=manual_status,
        ),
        ctx.settings,
        finalize,
    )
    day.shift_id = day.shift_id or employee.shift_id
    day.worked_minutes = result.worked_minutes
    day.late_minutes = result.late_minutes
    day.early_minutes = result.early_minutes
    day.overtime_minutes = result.overtime_minutes
    day.status = result.status
    day.is_manual = bool(locked)
    if finalize and day.finalized_at is None:
        day.finalized_at = datetime.now(UTC)
    return day


def _parse_locked(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(UTC)


async def apply_recognition(
    db: AsyncSession, employee: Employee, captured_at: datetime, values: dict[str, Any]
) -> AttendanceDay | None:
    """FR-20: called by the event processor inside its transaction. Inactive employees are ignored."""
    if employee.status != EmployeeStatus.ACTIVE or employee.deleted_at is not None:
        return None
    ctx = employee_context(employee, values)
    work_date = rules.work_date_for(captured_at, ctx.shift, ctx.tz, ctx.settings)
    return await recompute_day(db, employee, work_date, values)


async def work_date_of(db: AsyncSession, employee: Employee, instant: datetime) -> date:
    values = await settings_service.resolved(db)
    ctx = employee_context(employee, values)
    return rules.work_date_for(instant, ctx.shift, ctx.tz, ctx.settings)


# --------------------------------------------------------------------------- day close (FR-23)


async def close_due_days(db: AsyncSession, now: datetime | None = None, lookback_days: int = 2) -> int:
    """Finalises every employee-day whose close time has passed and is not finalised yet.

    Idempotent: finalised days are skipped, so re-running gives the same result (standards/02).
    Returns the number of days finalised.
    """
    now = now or datetime.now(UTC)
    values = await settings_service.resolved(db)
    finalised = 0
    for employee in await employee_repo.active_employees(db):
        ctx = employee_context(employee, values)
        today = now.astimezone(ctx.tz).date()
        created_local = employee.created_at.astimezone(ctx.tz).date()
        for offset in range(lookback_days, -1, -1):
            work_date = today - timedelta(days=offset)
            if (
                work_date < created_local
                or rules.day_close_at(work_date, ctx.shift, ctx.tz, ctx.settings) > now
            ):
                continue
            existing = await attendance_repo.find(db, employee.id, work_date)
            if existing is not None and existing.finalized_at is not None:
                continue
            async with transaction(db):
                await recompute_day(db, employee, work_date, values, finalize=True)
            finalised += 1
    return finalised


async def recompute_date(db: AsyncSession, work_date: date) -> int:
    """Re-runs the rules for one date for every active employee (e.g. after a holiday was added)."""
    values = await settings_service.resolved(db)
    count = 0
    for employee in await employee_repo.active_employees(db):
        existing = await attendance_repo.find(db, employee.id, work_date)
        if existing is None:
            continue
        async with transaction(db):
            await recompute_day(db, employee, work_date, values)
        count += 1
    return count


# --------------------------------------------------------------------------- reads


def to_out(day: AttendanceDay) -> AttendanceDayOut:
    employee = day.employee
    return AttendanceDayOut(
        id=day.id,
        employee_id=day.employee_id,
        employee_code=employee.employee_code,
        employee_name=employee.full_name,
        department_id=employee.department_id,
        department_name=employee.department.name if employee.department else None,
        work_date=day.work_date,
        shift_id=day.shift_id,
        shift_name=day.shift.name if day.shift else None,
        check_in_at=day.check_in_at,
        check_out_at=day.check_out_at,
        check_in_event_id=day.check_in_event_id,
        check_out_event_id=day.check_out_event_id,
        worked_minutes=day.worked_minutes,
        late_minutes=day.late_minutes,
        early_minutes=day.early_minutes,
        overtime_minutes=day.overtime_minutes,
        status=day.status,
        status_letter=ATTENDANCE_STATUS_LETTERS.get(day.status) if day.status else None,
        is_manual=day.is_manual,
        finalized_at=day.finalized_at,
    )


async def get_in_scope(
    db: AsyncSession, day_id: int, scope: DataScope, *, for_update: bool = False
) -> AttendanceDay:
    day = await attendance_repo.get(db, day_id, for_update=for_update)
    if day is None or not scope.allows(day.employee.department_id, day.employee_id):
        raise NotFound("Attendance record not found.")  # out of scope looks the same as missing (§04)
    return day


# --------------------------------------------------------------------------- manual entry (FR-25)


async def create_manual_day(
    db: AsyncSession, payload: ManualAttendanceCreate, actor: User, scope: DataScope
) -> AttendanceDay:
    employee = await employee_repo.get(db, payload.employee_id)
    if employee is None or not scope.allows(employee.department_id, employee.id):
        raise NotFound("Employee not found.")
    if scope.employee_id is not None:
        raise PermissionDenied("Employees request corrections instead of adding entries.")
    values = await settings_service.resolved(db)
    async with transaction(db):
        if await attendance_repo.find(db, employee.id, payload.work_date) is not None:
            raise Conflict("An attendance record already exists for this date; correct it instead.")
        day = await attendance_repo.get_or_create_for_update(
            db, employee.id, payload.work_date, employee.shift_id
        )
        now = datetime.now(UTC)
        fields: list[tuple[CorrectionField, str]] = []
        if payload.check_in_at:
            fields.append((CorrectionField.CHECK_IN_AT, payload.check_in_at.astimezone(UTC).isoformat()))
        if payload.check_out_at:
            fields.append((CorrectionField.CHECK_OUT_AT, payload.check_out_at.astimezone(UTC).isoformat()))
        if payload.status:
            fields.append((CorrectionField.STATUS, payload.status.value))
        for field, value in fields:
            db.add(
                AttendanceCorrection(
                    attendance_day_id=day.id,
                    requested_by=actor.id,
                    field=field,
                    old_value=None,
                    new_value=value,
                    reason=payload.reason,
                    status=CorrectionStatus.APPROVED,
                    approved_by=actor.id,
                    approved_at=now,
                )
            )
        await db.flush()
        await recompute_day(db, employee, payload.work_date, values)
        await audit.record(
            db,
            actor,
            "attendance.manual_create",
            "attendance_day",
            day.id,
            new=payload.model_dump(mode="json"),
        )
    return await get_in_scope(db, day.id, scope)
