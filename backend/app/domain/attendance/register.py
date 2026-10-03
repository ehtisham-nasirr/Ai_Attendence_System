"""Monthly attendance register (§13 screen 8, FR-30): employee-by-day status letters with row totals."""

import calendar
from collections import Counter, defaultdict
from datetime import date

from facetrack_common.constants import ATTENDANCE_STATUS_LETTERS
from facetrack_common.models import AttendanceDay
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationFailed
from app.core.pagination import PageParams
from app.core.security import DataScope
from app.repositories import attendance_repo
from app.schemas.attendance import RegisterDay, RegisterRow


def month_bounds(month: str) -> tuple[date, date]:
    """`YYYY-MM` -> first and last day of that month."""
    try:
        year, number = (int(part) for part in month.split("-"))
        first = date(year, number, 1)
    except ValueError as exc:
        raise ValidationFailed(errors={"month": ["Use the format YYYY-MM."]}) from exc
    return first, date(year, number, calendar.monthrange(year, number)[1])


def build_row(
    employee_id: int, code: str, name: str, department: str | None, days: list[AttendanceDay]
) -> RegisterRow:
    ordered = sorted(days, key=lambda d: d.work_date)
    letters = [ATTENDANCE_STATUS_LETTERS[d.status] for d in ordered if d.status is not None]
    return RegisterRow(
        employee_id=employee_id,
        employee_code=code,
        employee_name=name,
        department_name=department,
        days=[
            RegisterDay(
                work_date=d.work_date,
                status=d.status,
                letter=ATTENDANCE_STATUS_LETTERS.get(d.status) if d.status else None,
                is_manual=d.is_manual,
            )
            for d in ordered
        ],
        totals=dict(Counter(letters)),
        worked_minutes=sum(d.worked_minutes for d in ordered),
        late_minutes=sum(d.late_minutes for d in ordered),
        overtime_minutes=sum(d.overtime_minutes for d in ordered),
    )


async def monthly_register(
    db: AsyncSession,
    params: PageParams,
    scope: DataScope,
    month: str,
    department_id: int | None,
    search: str | None,
) -> tuple[list[RegisterRow], int]:
    first, last = month_bounds(month)
    employees, total = await attendance_repo.register_employees(
        db, params, scope, month_start=first, month_end=last, department_id=department_id, search=search
    )
    by_employee: dict[int, list[AttendanceDay]] = defaultdict(list)
    for day in await attendance_repo.days_between(db, [e.id for e in employees], first, last):
        by_employee[day.employee_id].append(day)
    rows = [
        build_row(
            e.id, e.employee_code, e.full_name, e.department.name if e.department else None, by_employee[e.id]
        )
        for e in employees
    ]
    return rows, total
