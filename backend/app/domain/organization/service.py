"""Locations, departments, shifts and holidays (FR-21, FR-36, §13 Settings tabs). CRUD + audit."""

from typing import Any

from facetrack_common.models import Department, Holiday, Location, Shift, User
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import transaction
from app.core.exceptions import Conflict, NotFound, ValidationFailed
from app.domain.audit import service as audit
from app.repositories import organization_repo as repo
from app.repositories.base import apply_changes, get_live, soft_delete
from app.schemas.organization import (
    DepartmentCreate,
    DepartmentUpdate,
    HolidayCreate,
    HolidayUpdate,
    LocationCreate,
    LocationUpdate,
    ShiftCreate,
    ShiftUpdate,
)
from app.worker.dispatch import recompute_attendance_date


def _changes(payload: BaseModel) -> dict[str, Any]:
    return payload.model_dump(exclude_unset=True)


async def _get_or_404[M](db: AsyncSession, model: type[M], entity_id: int, label: str) -> M:
    entity = await get_live(db, model, entity_id)  # type: ignore[type-var]
    if entity is None:
        raise NotFound(f"{label} not found.")
    return entity


# --- locations ---


async def create_location(db: AsyncSession, payload: LocationCreate, actor: User) -> Location:
    async with transaction(db):
        if await repo.location_name_taken(db, payload.name):
            raise Conflict("A location with this name already exists.")
        location = Location(**payload.model_dump())
        db.add(location)
        await db.flush()
        await audit.record(db, actor, "location.create", "location", location.id, new=payload.model_dump())
    return location


async def update_location(
    db: AsyncSession, location_id: int, payload: LocationUpdate, actor: User
) -> Location:
    async with transaction(db):
        location = await _get_or_404(db, Location, location_id, "Location")
        changes = _changes(payload)
        if "name" in changes and await repo.location_name_taken(db, changes["name"], location_id):
            raise Conflict("A location with this name already exists.")
        old = apply_changes(location, changes)
        await audit.record(db, actor, "location.update", "location", location_id, old=old, new=changes)
    return location


async def delete_location(db: AsyncSession, location_id: int, actor: User) -> None:
    async with transaction(db):
        location = await _get_or_404(db, Location, location_id, "Location")
        soft_delete(location)
        await audit.record(db, actor, "location.delete", "location", location_id)


# --- departments ---


async def _check_manager(db: AsyncSession, user_id: int | None) -> None:
    if user_id is not None and await get_live(db, User, user_id) is None:
        raise ValidationFailed(errors={"manager_user_id": ["User not found."]})


async def create_department(db: AsyncSession, payload: DepartmentCreate, actor: User) -> Department:
    async with transaction(db):
        if await repo.department_code_taken(db, payload.code):
            raise Conflict("A department with this code already exists.")
        await _check_manager(db, payload.manager_user_id)
        department = Department(**payload.model_dump())
        db.add(department)
        await db.flush()
        await audit.record(
            db, actor, "department.create", "department", department.id, new=payload.model_dump()
        )
    return department


async def update_department(
    db: AsyncSession, department_id: int, payload: DepartmentUpdate, actor: User
) -> Department:
    async with transaction(db):
        department = await _get_or_404(db, Department, department_id, "Department")
        changes = _changes(payload)
        if "code" in changes and await repo.department_code_taken(db, changes["code"], department_id):
            raise Conflict("A department with this code already exists.")
        await _check_manager(db, changes.get("manager_user_id"))
        old = apply_changes(department, changes)
        await audit.record(db, actor, "department.update", "department", department_id, old=old, new=changes)
    return department


async def delete_department(db: AsyncSession, department_id: int, actor: User) -> None:
    async with transaction(db):
        department = await _get_or_404(db, Department, department_id, "Department")
        soft_delete(department)
        await audit.record(db, actor, "department.delete", "department", department_id)


# --- shifts ---


async def create_shift(db: AsyncSession, payload: ShiftCreate, actor: User) -> Shift:
    async with transaction(db):
        if await repo.shift_name_taken(db, payload.name):
            raise Conflict("A shift with this name already exists.")
        shift = Shift(**payload.model_dump())
        db.add(shift)
        await db.flush()
        await audit.record(db, actor, "shift.create", "shift", shift.id, new=payload.model_dump())
    return shift


async def update_shift(db: AsyncSession, shift_id: int, payload: ShiftUpdate, actor: User) -> Shift:
    async with transaction(db):
        shift = await _get_or_404(db, Shift, shift_id, "Shift")
        changes = _changes(payload)
        if "weekly_offs" in changes and changes["weekly_offs"] is not None:
            if any(day < 1 or day > 7 for day in changes["weekly_offs"]):
                raise ValidationFailed(errors={"weekly_offs": ["Weekly offs are ISO weekdays 1-7."]})
            changes["weekly_offs"] = sorted(set(changes["weekly_offs"]))
        if "name" in changes and await repo.shift_name_taken(db, changes["name"], shift_id):
            raise Conflict("A shift with this name already exists.")
        old = apply_changes(shift, changes)
        await audit.record(db, actor, "shift.update", "shift", shift_id, old=old, new=changes)
    return shift


async def delete_shift(db: AsyncSession, shift_id: int, actor: User) -> None:
    async with transaction(db):
        shift = await _get_or_404(db, Shift, shift_id, "Shift")
        soft_delete(shift)
        await audit.record(db, actor, "shift.delete", "shift", shift_id)


# --- holidays ---


async def create_holiday(db: AsyncSession, payload: HolidayCreate, actor: User) -> Holiday:
    async with transaction(db):
        await _get_or_404(db, Location, payload.location_id, "Location")
        if await repo.holiday_exists(db, payload.location_id, payload.date):
            raise Conflict("A holiday already exists on this date for this location.")
        holiday = Holiday(**payload.model_dump())
        db.add(holiday)
        await db.flush()
        await audit.record(db, actor, "holiday.create", "holiday", holiday.id, new=payload.model_dump())
    recompute_attendance_date(payload.date.isoformat())
    return holiday


async def update_holiday(db: AsyncSession, holiday_id: int, payload: HolidayUpdate, actor: User) -> Holiday:
    async with transaction(db):
        holiday = await _get_or_404(db, Holiday, holiday_id, "Holiday")
        changes = _changes(payload)
        if "date" in changes and await repo.holiday_exists(
            db, holiday.location_id, changes["date"], holiday_id
        ):
            raise Conflict("A holiday already exists on this date for this location.")
        old = apply_changes(holiday, changes)
        await audit.record(db, actor, "holiday.update", "holiday", holiday_id, old=old, new=changes)
    for affected in {holiday.date, old.get("date", holiday.date)}:
        recompute_attendance_date(affected.isoformat())
    return holiday


async def delete_holiday(db: AsyncSession, holiday_id: int, actor: User) -> None:
    async with transaction(db):
        holiday = await _get_or_404(db, Holiday, holiday_id, "Holiday")
        soft_delete(holiday)
        await audit.record(db, actor, "holiday.delete", "holiday", holiday_id)
    recompute_attendance_date(holiday.date.isoformat())
