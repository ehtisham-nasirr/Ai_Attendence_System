"""Cameras."""

from facetrack_common.constants import CameraRole
from facetrack_common.models import Camera
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PageParams, apply_sort, fetch_page

_SORT = {"name": Camera.name, "priority": Camera.priority, "status": Camera.status, "role": Camera.role}
EXIT_ROLES = (CameraRole.EXIT, CameraRole.ENTRY_EXIT)


async def list_cameras(
    db: AsyncSession,
    params: PageParams,
    location_id: int | None,
    role: CameraRole | None,
    engine_node: str | None,
) -> tuple[list[Camera], int]:
    stmt = select(Camera).where(Camera.deleted_at.is_(None))
    if location_id:
        stmt = stmt.where(Camera.location_id == location_id)
    if role:
        stmt = stmt.where(Camera.role == role)
    if engine_node:
        stmt = stmt.where(Camera.engine_node == engine_node)
    return await fetch_page(db, apply_sort(stmt, params.sort, _SORT, Camera.id), params)


async def all_cameras(db: AsyncSession) -> list[Camera]:
    return list(
        (await db.scalars(select(Camera).where(Camera.deleted_at.is_(None)).order_by(Camera.id))).all()
    )


async def name_taken(db: AsyncSession, name: str, exclude_id: int | None = None) -> bool:
    stmt = select(Camera.id).where(func.lower(Camera.name) == name.lower(), Camera.deleted_at.is_(None))
    if exclude_id:
        stmt = stmt.where(Camera.id != exclude_id)
    return (await db.scalars(stmt)).first() is not None


async def location_has_exit_cameras(db: AsyncSession, location_id: int) -> bool:
    stmt = select(Camera.id).where(
        Camera.location_id == location_id,
        Camera.role.in_(EXIT_ROLES),
        Camera.is_enabled.is_(True),
        Camera.deleted_at.is_(None),
    )
    return (await db.scalars(stmt)).first() is not None


async def by_id_any(db: AsyncSession, camera_id: int) -> Camera | None:
    """Including soft-deleted cameras: events from a camera deleted moments ago are still valid."""
    return await db.get(Camera, camera_id)
