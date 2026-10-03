"""Finalised attendance for payroll (FR-35): the pull API rows and the signed push webhook.

Push sends every finalised day changed since the last successful delivery (a watermark on
`updated_at`). Night shifts that close after the push time and corrections made after the day closed
therefore reach payroll on the next push; the receiver upserts by (employee_code, work_date).
"""

import hashlib
import hmac
import json
import time
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from facetrack_common.constants import ATTENDANCE_STATUS_LETTERS
from facetrack_common.models import AttendanceDay, Employee
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.pagination import PageParams, fetch_page
from app.schemas.integration import IntegrationAttendanceOut

SIGNATURE_HEADER = "X-FaceTrack-Signature"
DELIVERY_HEADER = "X-FaceTrack-Delivery"
MAX_DAYS_PER_DELIVERY = 5_000
# Days updated in the last minute wait for the next push, so a transaction still in flight is not skipped.
SETTLE = timedelta(minutes=1)


def to_out(day: AttendanceDay) -> IntegrationAttendanceOut:
    employee = day.employee
    return IntegrationAttendanceOut(
        employee_code=employee.employee_code,
        hr_external_id=employee.hr_external_id,
        employee_name=employee.full_name,
        department_code=employee.department.code if employee.department else None,
        work_date=day.work_date,
        shift_name=day.shift.name if day.shift else None,
        check_in_at=day.check_in_at,
        check_out_at=day.check_out_at,
        worked_minutes=day.worked_minutes,
        late_minutes=day.late_minutes,
        early_minutes=day.early_minutes,
        overtime_minutes=day.overtime_minutes,
        status=day.status,
        status_letter=ATTENDANCE_STATUS_LETTERS.get(day.status) if day.status else None,
        is_manual=day.is_manual,
        finalized_at=day.finalized_at,
        updated_at=day.updated_at,
    )


def _finalised() -> Any:
    return (
        select(AttendanceDay)
        .join(Employee, Employee.id == AttendanceDay.employee_id)
        .options(
            selectinload(AttendanceDay.employee).selectinload(Employee.department),
            selectinload(AttendanceDay.shift),
        )
        .where(AttendanceDay.finalized_at.is_not(None))
    )


async def finalised_for_date(
    db: AsyncSession, work_date: date, params: PageParams
) -> tuple[list[AttendanceDay], int]:
    stmt = _finalised().where(AttendanceDay.work_date == work_date).order_by(Employee.employee_code)
    return await fetch_page(db, stmt, params)


async def changed_since(db: AsyncSession, watermark: datetime, now: datetime) -> list[AttendanceDay]:
    stmt = (
        _finalised()
        .where(AttendanceDay.updated_at > watermark, AttendanceDay.updated_at <= now - SETTLE)
        .order_by(AttendanceDay.updated_at, AttendanceDay.id)
        .limit(MAX_DAYS_PER_DELIVERY)
    )
    return list((await db.scalars(stmt)).all())


def build_payload(days: list[AttendanceDay], reason: str) -> dict[str, Any]:
    return {
        "event": "attendance.finalized",
        "delivery_id": str(uuid.uuid4()),
        "reason": reason,
        "generated_at": datetime.now(UTC).isoformat(),
        "days": [to_out(day).model_dump(mode="json") for day in days],
    }


def sign(body: bytes, secret: str, timestamp: int | None = None) -> str:
    """`t=<unix seconds>,v1=<hex HMAC-SHA256 of "<t>.<body>">` (receivers reject old timestamps)."""
    t = int(time.time()) if timestamp is None else timestamp
    digest = hmac.new(secret.encode(), f"{t}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={t},v1={digest}"


def verify(body: bytes, header: str, secret: str, tolerance_s: int = 300, now: int | None = None) -> bool:
    """Reference check for receivers (and tests)."""
    parts = dict(part.split("=", 1) for part in header.split(",") if "=" in part)
    try:
        t = int(parts["t"])
    except (KeyError, ValueError):
        return False
    if abs((int(time.time()) if now is None else now) - t) > tolerance_s:
        return False
    expected = sign(body, secret, t).split("v1=", 1)[1]
    return hmac.compare_digest(expected, parts.get("v1", ""))


def encode(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
