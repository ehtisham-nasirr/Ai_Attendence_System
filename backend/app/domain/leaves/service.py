"""Leave entered by HR (FR-24, Q30). HR-synced leave comes through `services/hr_sync`."""

from facetrack_common.constants import LeaveSource
from facetrack_common.models import Employee, Leave, User
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import transaction
from app.core.exceptions import NotFound, ValidationFailed
from app.domain.audit import service as audit
from app.repositories.base import get_live, soft_delete
from app.schemas.employee import LeaveCreate


async def create_leave(db: AsyncSession, payload: LeaveCreate, actor: User) -> Leave:
    async with transaction(db):
        if await get_live(db, Employee, payload.employee_id) is None:
            raise ValidationFailed(errors={"employee_id": ["Employee not found."]})
        leave = Leave(**payload.model_dump(), source=LeaveSource.MANUAL)
        db.add(leave)
        await db.flush()
        await audit.record(db, actor, "leave.create", "leave", leave.id, new=payload.model_dump())
    return leave


async def delete_leave(db: AsyncSession, leave_id: int, actor: User) -> None:
    async with transaction(db):
        leave = await get_live(db, Leave, leave_id, for_update=True)
        if leave is None:
            raise NotFound("Leave not found.")
        soft_delete(leave)
        await audit.record(db, actor, "leave.delete", "leave", leave_id)
