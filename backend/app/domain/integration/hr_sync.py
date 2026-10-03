"""HR master-data sync (FR-12) and leave import (FR-24).

Employees are matched by `employee_code`. Fields the HR record does not carry are left alone, and an
employee missing from the HR feed is never deactivated or deleted automatically: only an explicit
`status: inactive` deactivates (Q44). Leave is matched by its HR id (`external_ref`); HR leave inside
the synced window that the HR system no longer returns is removed (cancelled), and every affected
attendance day is recomputed.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from facetrack_common.constants import EmployeeStatus, LeaveSource
from facetrack_common.models import Department, Leave
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import transaction
from app.core.exceptions import DomainError
from app.domain.audit import service as audit
from app.domain.employees import service as employee_service
from app.domain.leaves import service as leave_service
from app.repositories import employee_repo
from app.schemas.employee import EmployeeCreate, EmployeeUpdate

logger = logging.getLogger(__name__)
_EMPLOYEE_FIELDS = ("full_name", "designation", "email", "phone", "hr_external_id")


@dataclass
class SyncReport:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    leaves_added: int = 0
    leaves_updated: int = 0
    leaves_removed: int = 0
    errors: list[str] = field(default_factory=list)

    def error(self, message: str) -> None:
        if len(self.errors) < 100:
            self.errors.append(message)

    def as_dict(self) -> dict[str, Any]:
        return {**self.__dict__, "error_count": len(self.errors)}


def _text(record: dict[str, Any], key: str) -> str | None:
    value = record.get(key)
    return str(value).strip() or None if value is not None else None


async def _department_id(db: AsyncSession, code: str | None) -> int | None:
    if not code:
        return None
    return await db.scalar(
        select(Department.id).where(Department.code == code, Department.deleted_at.is_(None))
    )


async def sync_employees(db: AsyncSession, records: list[dict[str, Any]], report: SyncReport) -> None:
    for record in records:
        code = _text(record, "employee_code")
        if not code:
            report.error("record without employee_code skipped")
            continue
        values: dict[str, Any] = {k: _text(record, k) for k in _EMPLOYEE_FIELDS if k in record}
        if values.get("hr_external_id") is None and record.get("id") is not None:
            values["hr_external_id"] = str(record["id"])
        if "department_code" in record:
            department_id = await _department_id(db, _text(record, "department_code"))
            if department_id is None and _text(record, "department_code"):
                report.error(f"{code}: unknown department_code {record['department_code']!r}")
            else:
                values["department_id"] = department_id
        status = _text(record, "status")
        if status in (EmployeeStatus.ACTIVE.value, EmployeeStatus.INACTIVE.value):
            values["status"] = EmployeeStatus(status)
        try:
            existing = await employee_repo.by_code(db, code)
            if existing is None:
                if not values.get("full_name"):
                    report.error(f"{code}: new employee without full_name skipped")
                    continue
                await employee_service.create_employee(db, EmployeeCreate(employee_code=code, **values), None)
                report.created += 1
                continue
            changes = {k: v for k, v in values.items() if getattr(existing, k) != v}
            if not changes:
                report.unchanged += 1
                continue
            await employee_service.update_employee(db, existing.id, EmployeeUpdate(**changes), None)
            report.updated += 1
        except (ValidationError, DomainError) as exc:
            await db.rollback()
            report.error(f"{code}: {exc}")


async def sync_leaves(
    db: AsyncSession, records: list[dict[str, Any]], window: tuple[date, date], report: SyncReport
) -> None:
    seen: set[str] = set()
    for record in records:
        ref = _text(record, "external_ref") or _text(record, "id")
        code = _text(record, "employee_code")
        if not ref or not code:
            report.error("leave without id or employee_code skipped")
            continue
        if _text(record, "status") not in (None, "approved"):
            continue  # only approved leave counts (FR-24)
        try:
            from_date = date.fromisoformat(str(record["from_date"]))
            to_date = date.fromisoformat(str(record["to_date"]))
        except (KeyError, ValueError):
            report.error(f"leave {ref}: invalid dates")
            continue
        employee = await employee_repo.by_code(db, code)
        if employee is None or to_date < from_date:
            report.error(f"leave {ref}: unknown employee {code!r} or invalid range")
            continue
        seen.add(ref)
        leave_type = (_text(record, "type") or "Leave")[:64]
        async with transaction(db):
            leave = await db.scalar(
                select(Leave).where(Leave.external_ref == ref, Leave.source == LeaveSource.HR)
            )
            affected = [(from_date, to_date)]
            if leave is None:
                db.add(
                    Leave(
                        employee_id=employee.id,
                        from_date=from_date,
                        to_date=to_date,
                        type=leave_type,
                        source=LeaveSource.HR,
                        external_ref=ref,
                    )
                )
                report.leaves_added += 1
            elif (leave.from_date, leave.to_date, leave.type, leave.deleted_at) != (
                from_date,
                to_date,
                leave_type,
                None,
            ):
                affected.append((leave.from_date, leave.to_date))
                leave.from_date, leave.to_date, leave.type, leave.deleted_at = (
                    from_date,
                    to_date,
                    leave_type,
                    None,
                )
                report.leaves_updated += 1
            else:
                continue
            await db.flush()
            loaded = await employee_repo.get(db, employee.id)
            if loaded is not None:
                for start, end in affected:
                    await leave_service.recompute_leave_days(db, loaded, start, end)

    # HR leave inside the window that HR no longer returns was cancelled.
    stale = (
        await db.scalars(
            select(Leave).where(
                Leave.source == LeaveSource.HR,
                Leave.deleted_at.is_(None),
                Leave.from_date <= window[1],
                Leave.to_date >= window[0],
            )
        )
    ).all()
    for leave in stale:
        if leave.external_ref in seen:
            continue
        async with transaction(db):
            leave.deleted_at = datetime.now(UTC)
            await db.flush()
            employee = await employee_repo.get(db, leave.employee_id)
            if employee is not None:
                await leave_service.recompute_leave_days(db, employee, leave.from_date, leave.to_date)
        report.leaves_removed += 1


async def record_run(db: AsyncSession, report: SyncReport) -> None:
    async with transaction(db):
        await audit.record(db, None, "hr_sync.run", "integration", None, new=report.as_dict())
