"""Small shared helpers for repositories."""

from datetime import UTC, datetime
from typing import Any

from facetrack_common.models import Base
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def get_live[M: Base](
    db: AsyncSession, model: type[M], entity_id: int, *, for_update: bool = False
) -> M | None:
    """Fetches a row by id, excluding soft-deleted rows when the model supports soft delete."""
    stmt = select(model).where(model.id == entity_id)  # type: ignore[attr-defined]
    if hasattr(model, "deleted_at"):
        stmt = stmt.where(model.deleted_at.is_(None))  # type: ignore[attr-defined]
    if for_update:
        stmt = stmt.with_for_update()
    return (await db.scalars(stmt)).first()


def soft_delete(entity: Any) -> None:
    entity.deleted_at = datetime.now(UTC)


def apply_changes(entity: Any, changes: dict[str, Any]) -> dict[str, Any]:
    """Sets attributes; returns {field: old value} for those that actually changed (audit)."""
    old: dict[str, Any] = {}
    for field, value in changes.items():
        current = getattr(entity, field)
        if current != value:
            old[field] = current
            setattr(entity, field, value)
    return old
