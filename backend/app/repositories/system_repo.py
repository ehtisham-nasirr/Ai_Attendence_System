"""Settings and the audit log."""

from datetime import datetime
from typing import Any

from facetrack_common.models import AuditLog, Setting, User
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PageParams, apply_sort


async def all_settings(db: AsyncSession) -> dict[str, Any]:
    return {key: value for key, value in (await db.execute(select(Setting.key, Setting.value))).all()}


async def upsert_setting(db: AsyncSession, key: str, value: Any) -> None:
    stmt = insert(Setting).values(key=key, value=value)
    await db.execute(
        stmt.on_conflict_do_update(index_elements=[Setting.key], set_={"value": stmt.excluded.value})
    )


async def list_audit(
    db: AsyncSession,
    params: PageParams,
    *,
    user_id: int | None,
    action: str | None,
    entity: str | None,
    date_from: datetime | None,
    date_to: datetime | None,
) -> tuple[list[tuple[AuditLog, str | None]], int]:
    stmt: Any = select(AuditLog, User.name).outerjoin(User, User.id == AuditLog.user_id)
    if user_id:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if action:
        stmt = stmt.where(AuditLog.action.like(f"{action}%"))
    if entity:
        stmt = stmt.where(AuditLog.entity == entity)
    if date_from:
        stmt = stmt.where(AuditLog.created_at >= date_from)
    if date_to:
        stmt = stmt.where(AuditLog.created_at < date_to)
    stmt = apply_sort(stmt, params.sort or "-created_at", {"created_at": AuditLog.created_at}, AuditLog.id)
    total = await db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = (await db.execute(stmt.offset(params.offset).limit(params.page_size))).all()
    return [(log, name) for log, name in rows], int(total)
