"""Leave entered by HR (FR-24, Q30). HR-synced leave comes through `services/hr_sync`.

Adding or removing leave recomputes the employee's existing days in that range, so a day already
closed as Absent becomes On leave (and back) without waiting for anything else to happen.
"""

from datetime import date

from facetrack_common.constants import LeaveSource
from facetrack_common.models import Employee, Leave, User
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import transaction
from app.core.exceptions import NotFound, ValidationFailed
from app.domain.attendance import service as attendance_service
from app.domain.audit import service as audit
from app.domain.settings import service as settings_service
from app.repositories import attendance_repo, employee_repo
from app.repositories.base import get_live, soft_delete
from app.schemas.employee import LeaveCreate


async def recompute_leave_days(db: AsyncSession, employee: Employee, from_date: date, to_date: date) -> int:
    """Re-runs the rules for the employee's existing days in the range. Caller owns the transaction."""
    values = await settings_service.resolved(db)
    days = await attendance_repo.days_between(db, [employee.id], from_date, to_date)
    for day in days:
        await attendance_service.recompute_day(db, employee, day.work_date, values)
    return len(days)


async def create_leave(db: AsyncSession, payload: LeaveCreate, actor: User) -> Leave:
    async with transaction(db):
        employee = await employee_repo.get(db, payload.employee_id)  # with shift/location for the rules
        if employee is None:
            raise ValidationFailed(errors={"employee_id": ["Employee not found."]})
        leave = Leave(**payload.model_dump(), source=LeaveSource.MANUAL)
        db.add(leave)
        await db.flush()
        await audit.record(db, actor, "leave.create", "leave", leave.id, new=payload.model_dump())
        await recompute_leave_days(db, employee, payload.from_date, payload.to_date)
    return leave


async def delete_leave(db: AsyncSession, leave_id: int, actor: User) -> None:
    async with transaction(db):
        leave = await get_live(db, Leave, leave_id, for_update=True)
        if leave is None:
            raise NotFound("Leave not found.")
        soft_delete(leave)
        await db.flush()
        await audit.record(db, actor, "leave.delete", "leave", leave_id)
        employee = await employee_repo.get(db, leave.employee_id)
        if employee is not None:
            await recompute_leave_days(db, employee, leave.from_date, leave.to_date)
