"""Correction workflow (FR-25, FR-26, ADR-0004).

- Employees request corrections to their own days; requests stay pending.
- HR Admin, Super Admin and department managers (own department) apply corrections directly,
  and decide pending requests. One approval is enough.
- The original value is kept in `old_value`; an approved correction locks that field.
"""

from datetime import UTC, datetime

from facetrack_common.constants import AttendanceStatus, CorrectionField, CorrectionStatus
from facetrack_common.models import AttendanceCorrection, AttendanceDay, User
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import transaction
from app.core.exceptions import Conflict, NotFound, PermissionDenied, ValidationFailed
from app.core.security import DataScope, Permission, has_permission
from app.domain.attendance import service as attendance_service
from app.domain.audit import service as audit
from app.domain.settings import service as settings_service
from app.repositories import attendance_repo
from app.schemas.attendance import CorrectionCreate, CorrectionOut


def to_out(correction: AttendanceCorrection) -> CorrectionOut:
    day = correction.attendance_day
    return CorrectionOut(
        id=correction.id,
        attendance_day_id=correction.attendance_day_id,
        employee_id=day.employee_id,
        employee_code=day.employee.employee_code,
        employee_name=day.employee.full_name,
        work_date=day.work_date,
        field=correction.field,
        old_value=correction.old_value,
        new_value=correction.new_value,
        reason=correction.reason,
        status=correction.status,
        requested_by=correction.requested_by,
        requested_by_name=correction.requester.name if correction.requester else None,
        approved_by=correction.approved_by,
        approved_by_name=correction.approver.name if correction.approver else None,
        approved_at=correction.approved_at,
        review_comment=correction.review_comment,
        created_at=correction.created_at,
    )


def _current_value(day: AttendanceDay, field: CorrectionField) -> str | None:
    value = getattr(day, field.value)
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    return str(value.value if isinstance(value, AttendanceStatus) else value)


async def _normalise_value(db: AsyncSession, day: AttendanceDay, field: CorrectionField, raw: str) -> str:
    if field == CorrectionField.STATUS:
        try:
            return AttendanceStatus(raw).value
        except ValueError as exc:
            raise ValidationFailed(errors={"new_value": ["Unknown attendance status."]}) from exc
    try:
        instant = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationFailed(errors={"new_value": ["Use an ISO 8601 time with timezone."]}) from exc
    if instant.tzinfo is None:
        raise ValidationFailed(errors={"new_value": ["The time must include a timezone."]})
    # The corrected time must belong to this work day (same boundaries as automatic attendance).
    if await attendance_service.work_date_of(db, day.employee, instant) != day.work_date:
        raise ValidationFailed(errors={"new_value": ["The time does not fall within this work day."]})
    return instant.astimezone(UTC).isoformat()


def _can_decide(user: User, scope: DataScope, day: AttendanceDay) -> bool:
    return (
        has_permission(user, Permission.ATTENDANCE_CORRECT)
        and scope.employee_id is None
        and scope.allows(day.employee.department_id, day.employee_id)
    )


async def request_or_apply(
    db: AsyncSession, day_id: int, payload: CorrectionCreate, actor: User, scope: DataScope
) -> tuple[AttendanceCorrection, AttendanceDay]:
    values = await settings_service.resolved(db)
    async with transaction(db):
        day = await attendance_service.get_in_scope(db, day_id, scope, for_update=True)
        applies_directly = _can_decide(actor, scope, day)
        if not applies_directly and not has_permission(actor, Permission.CORRECTIONS_REQUEST):
            raise PermissionDenied()
        new_value = await _normalise_value(db, day, payload.field, payload.new_value)
        now = datetime.now(UTC)
        correction = AttendanceCorrection(
            attendance_day_id=day.id,
            requested_by=actor.id,
            field=payload.field,
            old_value=_current_value(day, payload.field),
            new_value=new_value,
            reason=payload.reason,
            status=CorrectionStatus.APPROVED if applies_directly else CorrectionStatus.PENDING,
            approved_by=actor.id if applies_directly else None,
            approved_at=now if applies_directly else None,
        )
        db.add(correction)
        await db.flush()
        if applies_directly:
            await attendance_service.recompute_day(db, day.employee, day.work_date, values)
        action = "correction.apply" if applies_directly else "correction.request"
        await audit.record(
            db,
            actor,
            action,
            "attendance_day",
            day.id,
            old={payload.field.value: correction.old_value},
            new={payload.field.value: new_value, "reason": payload.reason},
        )
    return await _reload(db, correction.id), await attendance_service.get_in_scope(db, day_id, scope)


async def decide(
    db: AsyncSession, correction_id: int, approve: bool, comment: str | None, actor: User, scope: DataScope
) -> tuple[AttendanceCorrection, AttendanceDay]:
    values = await settings_service.resolved(db)
    async with transaction(db):
        correction = await attendance_repo.get_correction(db, correction_id, for_update=True)
        if correction is None:
            raise NotFound("Correction not found.")
        day = await attendance_service.get_in_scope(db, correction.attendance_day_id, scope, for_update=True)
        if not _can_decide(actor, scope, day):
            raise PermissionDenied("You cannot decide corrections for this employee.")
        if correction.status != CorrectionStatus.PENDING:
            raise Conflict("This correction has already been decided.")
        if approve:
            # The value may have changed since the request; keep the original as of now.
            correction.old_value = _current_value(day, correction.field)
        correction.status = CorrectionStatus.APPROVED if approve else CorrectionStatus.REJECTED
        correction.approved_by = actor.id
        correction.approved_at = datetime.now(UTC)
        correction.review_comment = comment
        await db.flush()
        if approve:
            await attendance_service.recompute_day(db, day.employee, day.work_date, values)
        await audit.record(
            db,
            actor,
            "correction.approve" if approve else "correction.reject",
            "attendance_correction",
            correction.id,
            new={"comment": comment},
        )
    return await _reload(db, correction_id), await attendance_service.get_in_scope(
        db, correction.attendance_day_id, scope
    )


async def _reload(db: AsyncSession, correction_id: int) -> AttendanceCorrection:
    correction = await attendance_repo.get_correction(db, correction_id)
    if correction is None:
        raise NotFound("Correction not found.")
    return correction
