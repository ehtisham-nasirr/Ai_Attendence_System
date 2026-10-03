"""Employees (FR-7, FR-13): CRUD, deactivation, deletion and biometric erasure.

Deactivating stops recognition immediately (gallery reload). Deleting an employee or erasing their
biometrics hard-deletes every face photo, embedding and snapshot (standards/18), then reloads the gallery.
"""

from datetime import UTC, datetime
from typing import Any

from facetrack_common.constants import EmployeeStatus
from facetrack_common.models import Department, Employee, Location, Shift, User
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import transaction
from app.core.exceptions import Conflict, NotFound, ValidationFailed
from app.domain.audit import service as audit
from app.domain.settings import service as settings_service
from app.repositories import employee_repo, event_repo
from app.repositories.base import apply_changes, get_live, soft_delete
from app.schemas.employee import EmployeeCreate, EmployeeOut, EmployeeUpdate
from app.services import engine_client, storage


async def to_out(db: AsyncSession, employees: list[Employee]) -> list[EmployeeOut]:
    values = await settings_service.resolved(db)
    minimum = int(values["enrollment.min_photos"])
    counts = await employee_repo.enrollment_counts(
        db, [e.id for e in employees], get_settings().embedder_model
    )
    result = []
    for employee in employees:
        out = EmployeeOut.model_validate(employee)
        out.department_name = employee.department.name if employee.department else None
        out.shift_name = employee.shift.name if employee.shift else None
        out.location_name = employee.location.name if employee.location else None
        out.enrolled_photos = counts.get(employee.id, 0)
        out.enrollment_complete = out.enrolled_photos >= minimum
        result.append(out)
    return result


async def get_or_404(db: AsyncSession, employee_id: int, *, for_update: bool = False) -> Employee:
    employee = await employee_repo.get(db, employee_id, for_update=for_update)
    if employee is None:
        raise NotFound("Employee not found.")
    return employee


async def _check_references(db: AsyncSession, changes: dict[str, Any]) -> None:
    errors = {}
    for field, model in (("department_id", Department), ("shift_id", Shift), ("location_id", Location)):
        if changes.get(field) is not None and await get_live(db, model, changes[field]) is None:
            errors[field] = [f"{model.__name__} not found."]
    if errors:
        raise ValidationFailed(errors=errors)


async def create_employee(db: AsyncSession, payload: EmployeeCreate, actor: User | None) -> Employee:
    async with transaction(db):
        if await employee_repo.code_exists(db, payload.employee_code):
            raise Conflict("An employee with this code already exists (codes are never reused).")
        await _check_references(db, payload.model_dump())
        employee = Employee(**payload.model_dump())
        if employee.status == EmployeeStatus.INACTIVE:
            employee.deactivated_at = datetime.now(UTC)
        db.add(employee)
        await db.flush()
        await audit.record(db, actor, "employee.create", "employee", employee.id, new=payload.model_dump())
    return await get_or_404(db, employee.id)


async def update_employee(
    db: AsyncSession, employee_id: int, payload: EmployeeUpdate, actor: User | None
) -> Employee:
    reload_gallery = False
    async with transaction(db):
        employee = await get_or_404(db, employee_id, for_update=True)
        changes = payload.model_dump(exclude_unset=True)
        await _check_references(db, changes)
        if changes.get("status") == EmployeeStatus.INACTIVE and employee.status != EmployeeStatus.INACTIVE:
            changes["deactivated_at"] = datetime.now(UTC)
            reload_gallery = True  # FR-13: stop recognising immediately
        elif changes.get("status") == EmployeeStatus.ACTIVE and employee.status != EmployeeStatus.ACTIVE:
            changes["deactivated_at"] = None
            reload_gallery = True
        old = apply_changes(employee, changes)
        await audit.record(db, actor, "employee.update", "employee", employee_id, old=old, new=changes)
    if reload_gallery:
        await engine_client.notify_engines("gallery_reload")
    return await get_or_404(db, employee_id)


async def erase_biometrics(
    db: AsyncSession, employee: Employee, actor: User | None, reason: str
) -> dict[str, int]:
    """FR-13 right to erasure: hard-deletes faces, embeddings, enrollment photos, event snapshots and
    unknown faces assigned to this employee. Must run inside the caller's transaction."""
    image_paths = await employee_repo.delete_faces(db, employee.id)
    snapshot_paths = await event_repo.employee_snapshot_paths(db, employee.id)
    await event_repo.clear_snapshot_paths(db, snapshot_paths)
    unknowns = await event_repo.unknown_assigned_to(db, employee.id)
    for unknown in unknowns:
        if unknown.snapshot_path:
            snapshot_paths.append(unknown.snapshot_path)
        await db.delete(unknown)
    deleted_objects = storage.delete_quietly(image_paths + snapshot_paths)
    counts = {
        "enrollments": len(image_paths),
        "event_snapshots": len(snapshot_paths) - sum(1 for u in unknowns if u.snapshot_path),
        "unknown_faces": len(unknowns),
        "objects_deleted": deleted_objects,
    }
    await audit.record(
        db, actor, "employee.biometrics_erase", "employee", employee.id, new={"reason": reason, **counts}
    )
    return counts


def _check_confirmation(employee: Employee, confirm_code: str) -> None:
    if confirm_code != employee.employee_code:
        raise ValidationFailed(
            errors={"confirm_employee_code": ["Type the employee code exactly to confirm."]}
        )


async def erase_employee_biometrics(
    db: AsyncSession, employee_id: int, confirm_code: str, actor: User
) -> dict[str, int]:
    async with transaction(db):
        employee = await get_or_404(db, employee_id, for_update=True)
        _check_confirmation(employee, confirm_code)
        counts = await erase_biometrics(db, employee, actor, reason="erasure request")
    await engine_client.notify_engines("gallery_reload")
    return counts


async def delete_employee(db: AsyncSession, employee_id: int, confirm_code: str, actor: User) -> None:
    """Soft-deletes the employee record (attendance history stays) and erases all face data (FR-13)."""
    async with transaction(db):
        employee = await get_or_404(db, employee_id, for_update=True)
        _check_confirmation(employee, confirm_code)
        await erase_biometrics(db, employee, actor, reason="employee deleted")
        employee.status = EmployeeStatus.INACTIVE
        employee.deactivated_at = employee.deactivated_at or datetime.now(UTC)
        soft_delete(employee)
        await audit.record(db, actor, "employee.delete", "employee", employee_id)
    await engine_client.notify_engines("gallery_reload")
