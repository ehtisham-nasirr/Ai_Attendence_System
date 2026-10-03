"""Users."""

from facetrack_common.models import User
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PageParams, apply_sort, fetch_page

_SORT = {"name": User.name, "username": User.username, "role": User.role, "created_at": User.created_at}


async def by_username(db: AsyncSession, username: str, *, for_update: bool = False) -> User | None:
    stmt = select(User).where(func.lower(User.username) == username.lower(), User.deleted_at.is_(None))
    if for_update:
        stmt = stmt.with_for_update()
    return (await db.scalars(stmt)).first()


async def by_email(db: AsyncSession, email: str) -> User | None:
    stmt = select(User).where(func.lower(User.email) == email.lower(), User.deleted_at.is_(None))
    return (await db.scalars(stmt)).first()


async def exists_username_or_email(
    db: AsyncSession, username: str, email: str, exclude_id: int | None = None
) -> bool:
    stmt = select(User.id).where(
        User.deleted_at.is_(None),
        or_(func.lower(User.username) == username.lower(), func.lower(User.email) == email.lower()),
    )
    if exclude_id is not None:
        stmt = stmt.where(User.id != exclude_id)
    return (await db.scalars(stmt)).first() is not None


async def list_users(
    db: AsyncSession, params: PageParams, search: str | None, role: str | None
) -> tuple[list[User], int]:
    stmt = select(User).where(User.deleted_at.is_(None))
    if search:
        like = f"%{search.lower()}%"
        stmt = stmt.where(or_(func.lower(User.name).like(like), func.lower(User.username).like(like)))
    if role:
        stmt = stmt.where(User.role == role)
    return await fetch_page(db, apply_sort(stmt, params.sort, _SORT, User.id), params)
