"""Locations, departments, shifts, holidays."""

from datetime import date

from facetrack_common.models import Department, Holiday, Location, Shift
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PageParams, apply_sort, fetch_page


async def list_locations(db: AsyncSession, params: PageParams) -> tuple[list[Location], int]:
    stmt = select(Location).where(Location.deleted_at.is_(None))
    return await fetch_page(db, apply_sort(stmt, params.sort, {"name": Location.name}, Location.id), params)


async def location_name_taken(db: AsyncSession, name: str, exclude_id: int | None = None) -> bool:
    stmt = select(Location.id).where(func.lower(Location.name) == name.lower(), Location.deleted_at.is_(None))
    if exclude_id:
        stmt = stmt.where(Location.id != exclude_id)
    return (await db.scalars(stmt)).first() is not None


async def list_departments(
    db: AsyncSession, params: PageParams, ids: frozenset[int] | None = None
) -> tuple[list[Department], int]:
    stmt = select(Department).where(Department.deleted_at.is_(None))
    if ids is not None:
        stmt = stmt.where(Department.id.in_(ids))
    sort = {"name": Department.name, "code": Department.code}
    return await fetch_page(db, apply_sort(stmt, params.sort, sort, Department.id), params)


async def department_code_taken(db: AsyncSession, code: str, exclude_id: int | None = None) -> bool:
    stmt = select(Department.id).where(
        func.lower(Department.code) == code.lower(), Department.deleted_at.is_(None)
    )
    if exclude_id:
        stmt = stmt.where(Department.id != exclude_id)
    return (await db.scalars(stmt)).first() is not None


async def list_shifts(db: AsyncSession, params: PageParams) -> tuple[list[Shift], int]:
    stmt = select(Shift).where(Shift.deleted_at.is_(None))
    return await fetch_page(db, apply_sort(stmt, params.sort, {"name": Shift.name}, Shift.id), params)


async def shift_name_taken(db: AsyncSession, name: str, exclude_id: int | None = None) -> bool:
    stmt = select(Shift.id).where(func.lower(Shift.name) == name.lower(), Shift.deleted_at.is_(None))
    if exclude_id:
        stmt = stmt.where(Shift.id != exclude_id)
    return (await db.scalars(stmt)).first() is not None


async def list_holidays(
    db: AsyncSession,
    params: PageParams,
    location_id: int | None,
    date_from: date | None,
    date_to: date | None,
) -> tuple[list[Holiday], int]:
    stmt = select(Holiday).where(Holiday.deleted_at.is_(None))
    if location_id:
        stmt = stmt.where(Holiday.location_id == location_id)
    if date_from:
        stmt = stmt.where(Holiday.date >= date_from)
    if date_to:
        stmt = stmt.where(Holiday.date <= date_to)
    return await fetch_page(db, apply_sort(stmt, params.sort, {"date": Holiday.date}, Holiday.date), params)


async def holiday_exists(
    db: AsyncSession, location_id: int, day: date, exclude_id: int | None = None
) -> bool:
    stmt = select(Holiday.id).where(
        Holiday.location_id == location_id, Holiday.date == day, Holiday.deleted_at.is_(None)
    )
    if exclude_id:
        stmt = stmt.where(Holiday.id != exclude_id)
    return (await db.scalars(stmt)).first() is not None


async def holiday_location_ids(db: AsyncSession, day: date) -> set[int]:
    rows = await db.scalars(
        select(Holiday.location_id).where(Holiday.date == day, Holiday.deleted_at.is_(None))
    )
    return set(rows)
