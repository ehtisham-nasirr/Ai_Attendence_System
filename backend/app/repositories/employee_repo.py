"""Employees, face enrollments and leave."""

from datetime import date
from typing import Any

from facetrack_common.constants import EmployeeStatus
from facetrack_common.models import Employee, FaceEnrollment, Leave
from sqlalchemy import Select, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.pagination import PageParams, apply_sort, fetch_page

_SORT = {
    "employee_code": Employee.employee_code,
    "full_name": Employee.full_name,
    "status": Employee.status,
    "created_at": Employee.created_at,
}


def _with_relations(stmt: Select[Any]) -> Select[Any]:
    return stmt.options(
        selectinload(Employee.department), selectinload(Employee.shift), selectinload(Employee.location)
    )


async def get(db: AsyncSession, employee_id: int, *, for_update: bool = False) -> Employee | None:
    stmt = _with_relations(select(Employee).where(Employee.id == employee_id, Employee.deleted_at.is_(None)))
    if for_update:
        stmt = stmt.with_for_update(of=Employee)
    employee: Employee | None = (await db.scalars(stmt)).first()
    return employee


async def by_code(db: AsyncSession, code: str) -> Employee | None:
    stmt = _with_relations(
        select(Employee).where(Employee.employee_code == code, Employee.deleted_at.is_(None))
    )
    return (await db.scalars(stmt)).first()


async def code_exists(db: AsyncSession, code: str) -> bool:
    # Codes are never reused, even after deletion (they match HR/payroll history).
    return (await db.scalars(select(Employee.id).where(Employee.employee_code == code))).first() is not None


async def list_employees(
    db: AsyncSession,
    params: PageParams,
    *,
    search: str | None,
    department_ids: frozenset[int] | None,
    status: EmployeeStatus | None,
    enrolled: bool | None,
) -> tuple[list[Employee], int]:
    stmt = _with_relations(select(Employee).where(Employee.deleted_at.is_(None)))
    if search:
        like = f"%{search.lower()}%"
        stmt = stmt.where(
            or_(func.lower(Employee.full_name).like(like), func.lower(Employee.employee_code).like(like))
        )
    if department_ids is not None:
        stmt = stmt.where(Employee.department_id.in_(department_ids))
    if status:
        stmt = stmt.where(Employee.status == status)
    if enrolled is not None:
        has_face = (
            select(FaceEnrollment.id)
            .where(FaceEnrollment.employee_id == Employee.id, FaceEnrollment.is_active.is_(True))
            .exists()
        )
        stmt = stmt.where(has_face if enrolled else ~has_face)
    return await fetch_page(db, apply_sort(stmt, params.sort, _SORT, Employee.id), params)


async def enrollment_counts(db: AsyncSession, employee_ids: list[int], model_name: str) -> dict[int, int]:
    if not employee_ids:
        return {}
    stmt = (
        select(FaceEnrollment.employee_id, func.count())
        .where(
            FaceEnrollment.employee_id.in_(employee_ids),
            FaceEnrollment.is_active.is_(True),
            FaceEnrollment.model_name == model_name,
        )
        .group_by(FaceEnrollment.employee_id)
    )
    return {employee_id: count for employee_id, count in (await db.execute(stmt)).all()}


async def active_employees(db: AsyncSession) -> list[Employee]:
    stmt = _with_relations(
        select(Employee).where(Employee.status == EmployeeStatus.ACTIVE, Employee.deleted_at.is_(None))
    )
    return list((await db.scalars(stmt)).all())


# --- face enrollments (biometric: hard delete only) ---


async def list_faces(db: AsyncSession, employee_id: int) -> list[FaceEnrollment]:
    stmt = select(FaceEnrollment).where(FaceEnrollment.employee_id == employee_id).order_by(FaceEnrollment.id)
    return list((await db.scalars(stmt)).all())


async def get_face(db: AsyncSession, employee_id: int, face_id: int) -> FaceEnrollment | None:
    stmt = select(FaceEnrollment).where(
        FaceEnrollment.id == face_id, FaceEnrollment.employee_id == employee_id
    )
    return (await db.scalars(stmt)).first()


async def other_employees_embeddings(
    db: AsyncSession, employee_id: int, model_name: str
) -> list[tuple[str, bytes, int]]:
    """(employee_code, ciphertext, dim) of other active employees' enrollments, for FR-10."""
    stmt = (
        select(Employee.employee_code, FaceEnrollment.embedding_encrypted, FaceEnrollment.embedding_dim)
        .join(Employee, Employee.id == FaceEnrollment.employee_id)
        .where(
            FaceEnrollment.employee_id != employee_id,
            FaceEnrollment.is_active.is_(True),
            FaceEnrollment.model_name == model_name,
            Employee.deleted_at.is_(None),
            Employee.status == EmployeeStatus.ACTIVE,
        )
    )
    return [(row[0], row[1], row[2]) for row in (await db.execute(stmt)).all()]


async def delete_faces(db: AsyncSession, employee_id: int) -> list[str]:
    """Hard-deletes all enrollments of an employee; returns their image paths for storage cleanup."""
    paths = list(
        await db.scalars(select(FaceEnrollment.image_path).where(FaceEnrollment.employee_id == employee_id))
    )
    await db.execute(delete(FaceEnrollment).where(FaceEnrollment.employee_id == employee_id))
    return paths


# --- leave ---


async def leave_employee_ids_on(db: AsyncSession, day: date) -> set[int]:
    stmt = select(Leave.employee_id).where(
        Leave.deleted_at.is_(None), Leave.from_date <= day, Leave.to_date >= day
    )
    return set(await db.scalars(stmt))


async def list_leaves(
    db: AsyncSession,
    params: PageParams,
    employee_id: int | None,
    date_from: date | None,
    date_to: date | None,
) -> tuple[list[Leave], int]:
    stmt = select(Leave).where(Leave.deleted_at.is_(None))
    if employee_id:
        stmt = stmt.where(Leave.employee_id == employee_id)
    if date_from:
        stmt = stmt.where(Leave.to_date >= date_from)
    if date_to:
        stmt = stmt.where(Leave.from_date <= date_to)
    return await fetch_page(
        db, apply_sort(stmt, params.sort, {"from_date": Leave.from_date}, Leave.from_date), params
    )


async def leave_by_external_ref(db: AsyncSession, ref: str) -> Leave | None:
    stmt = select(Leave).where(Leave.external_ref == ref, Leave.deleted_at.is_(None))
    return (await db.scalars(stmt)).first()
