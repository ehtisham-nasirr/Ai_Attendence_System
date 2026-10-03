"""Reports (FR-30, FR-31): rows, summary and chart data for each report type, scoped by role (§4).

Values come from the stored attendance days; nothing is recalculated here (standards/15). Times stay
UTC in the data and are formatted per employee timezone only by the exporters and the portal.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from facetrack_common.constants import ATTENDANCE_STATUS_LETTERS, AttendanceStatus, ReportType
from facetrack_common.models import AttendanceDay
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationFailed
from app.core.pagination import PageParams
from app.core.security import DataScope
from app.domain.attendance import register as register_service
from app.domain.settings import service as settings_service
from app.repositories import attendance_repo
from app.schemas.report import (
    ColumnKind,
    ReportChart,
    ReportChartSeries,
    ReportColumn,
    ReportFilters,
    ReportOut,
    ReportSummaryItem,
)

MAX_RANGE_DAYS = 366
PREVIEW_ROWS = 500

TITLES: dict[ReportType, str] = {
    ReportType.DAILY: "Daily attendance",
    ReportType.MONTHLY_REGISTER: "Monthly register",
    ReportType.LATE_ARRIVALS: "Late arrivals",
    ReportType.EARLY_EXITS: "Early exits",
    ReportType.ABSENTEE: "Absentee report",
    ReportType.OVERTIME: "Overtime",
    ReportType.DEPARTMENT_SUMMARY: "Department summary",
    ReportType.EMPLOYEE_HISTORY: "Employee history",
}

_ATTENDED = AttendanceDay.check_in_at.is_not(None)


def _col(key: str, label: str, kind: ColumnKind) -> ReportColumn:
    return ReportColumn(key=key, label=label, kind=kind)


_DATE = _col("work_date", "Date", "date")
_CODE = _col("employee_code", "Code", "code")
_NAME = _col("employee_name", "Employee", "text")
_DEPT = _col("department", "Department", "text")
_SHIFT = _col("shift", "Shift", "text")
_IN = _col("check_in_at", "Check-in", "time")
_OUT = _col("check_out_at", "Check-out", "time")
_WORKED = _col("worked_minutes", "Worked", "minutes")
_LATE = _col("late_minutes", "Late", "minutes")
_EARLY = _col("early_minutes", "Early exit", "minutes")
_OVERTIME = _col("overtime_minutes", "Overtime", "minutes")
_STATUS = _col("status", "Status", "status")
_MANUAL = _col("is_manual", "Manual", "bool")

_DAY_COLUMNS = [
    _DATE,
    _CODE,
    _NAME,
    _DEPT,
    _SHIFT,
    _IN,
    _OUT,
    _WORKED,
    _LATE,
    _EARLY,
    _OVERTIME,
    _STATUS,
    _MANUAL,
]


@dataclass(frozen=True)
class _ListSpec:
    columns: list[ReportColumn]
    condition: Any = None
    statuses: tuple[AttendanceStatus, ...] = ()


_LIST_REPORTS: dict[ReportType, _ListSpec] = {
    ReportType.DAILY: _ListSpec(_DAY_COLUMNS),
    ReportType.EMPLOYEE_HISTORY: _ListSpec(_DAY_COLUMNS),
    ReportType.LATE_ARRIVALS: _ListSpec(
        [_DATE, _CODE, _NAME, _DEPT, _SHIFT, _IN, _LATE, _STATUS], AttendanceDay.late_minutes > 0
    ),
    ReportType.EARLY_EXITS: _ListSpec(
        [_DATE, _CODE, _NAME, _DEPT, _SHIFT, _OUT, _EARLY, _STATUS], AttendanceDay.early_minutes > 0
    ),
    ReportType.ABSENTEE: _ListSpec(
        [_DATE, _CODE, _NAME, _DEPT, _SHIFT, _STATUS], None, (AttendanceStatus.ABSENT,)
    ),
    ReportType.OVERTIME: _ListSpec(
        [_DATE, _CODE, _NAME, _DEPT, _SHIFT, _IN, _OUT, _WORKED, _OVERTIME],
        AttendanceDay.overtime_minutes > 0,
    ),
}


def validate_filters(report_type: ReportType, filters: ReportFilters) -> tuple[date, date]:
    if filters.date_to < filters.date_from:
        raise ValidationFailed(errors={"date_to": ["Must be on or after the start date."]})
    if (filters.date_to - filters.date_from).days >= MAX_RANGE_DAYS:
        raise ValidationFailed(errors={"date_to": [f"Reports cover at most {MAX_RANGE_DAYS} days."]})
    if report_type == ReportType.EMPLOYEE_HISTORY and filters.employee_id is None:
        raise ValidationFailed(errors={"employee_id": ["Choose the employee."]})
    if report_type == ReportType.MONTHLY_REGISTER:
        # The register is one calendar month: the month of the start date.
        first, last = register_service.month_bounds(f"{filters.date_from:%Y-%m}")
        return first, last
    return filters.date_from, filters.date_to


def _day_row(day: AttendanceDay, default_tz: str) -> dict[str, Any]:
    employee = day.employee
    return {
        "work_date": day.work_date.isoformat(),
        "employee_code": employee.employee_code,
        "employee_name": employee.full_name,
        "department": employee.department.name if employee.department else None,
        "shift": day.shift.name if day.shift else None,
        "check_in_at": day.check_in_at.isoformat() if day.check_in_at else None,
        "check_out_at": day.check_out_at.isoformat() if day.check_out_at else None,
        "worked_minutes": day.worked_minutes,
        "late_minutes": day.late_minutes,
        "early_minutes": day.early_minutes,
        "overtime_minutes": day.overtime_minutes,
        "status": day.status.value if day.status else None,
        "is_manual": day.is_manual,
        # Not a column: the timezone exporters use to show this row's times.
        "_tz": employee.location.timezone if employee.location else default_tz,
    }


def _per_date_chart(days: list[AttendanceDay], series: list[tuple[str, str]], value: Any) -> ReportChart:
    buckets: dict[str, Counter[str]] = defaultdict(Counter)
    for day in days:
        for key, _ in series:
            buckets[day.work_date.isoformat()][key] += value(day, key)
    return ReportChart(
        x_key="work_date",
        series=[ReportChartSeries(key=key, label=label) for key, label in series],
        data=[{"work_date": d, **{key: buckets[d][key] for key, _ in series}} for d in sorted(buckets)],
    )


def _list_summary(
    report_type: ReportType, days: list[AttendanceDay]
) -> tuple[list[ReportSummaryItem], ReportChart]:
    employees = len({d.employee_id for d in days})
    if report_type == ReportType.LATE_ARRIVALS:
        return (
            [
                ReportSummaryItem(label="Late days", value=len(days)),
                ReportSummaryItem(label="Employees", value=employees),
                ReportSummaryItem(
                    label="Total late", value=sum(d.late_minutes for d in days), kind="minutes"
                ),
            ],
            _per_date_chart(days, [("late", "Late arrivals")], lambda d, _: 1),
        )
    if report_type == ReportType.EARLY_EXITS:
        return (
            [
                ReportSummaryItem(label="Early exits", value=len(days)),
                ReportSummaryItem(label="Employees", value=employees),
                ReportSummaryItem(
                    label="Total early", value=sum(d.early_minutes for d in days), kind="minutes"
                ),
            ],
            _per_date_chart(days, [("early", "Early exits")], lambda d, _: 1),
        )
    if report_type == ReportType.ABSENTEE:
        return (
            [
                ReportSummaryItem(label="Absent days", value=len(days)),
                ReportSummaryItem(label="Employees", value=employees),
            ],
            _per_date_chart(days, [("absent", "Absent")], lambda d, _: 1),
        )
    if report_type == ReportType.OVERTIME:
        total = sum(d.overtime_minutes for d in days)
        return (
            [
                ReportSummaryItem(label="Days with overtime", value=len(days)),
                ReportSummaryItem(label="Employees", value=employees),
                ReportSummaryItem(label="Total overtime", value=total, kind="minutes"),
            ],
            _per_date_chart(
                days, [("overtime_hours", "Overtime (hours)")], lambda d, _: round(d.overtime_minutes / 60, 2)
            ),
        )
    statuses = Counter(d.status for d in days if d.status)
    attended = [d for d in days if d.check_in_at]
    summary = [
        ReportSummaryItem(label="Days", value=len(days)),
        ReportSummaryItem(label="Attended", value=len(attended)),
        ReportSummaryItem(label="Late", value=statuses.get(AttendanceStatus.LATE, 0)),
        ReportSummaryItem(label="Absent", value=statuses.get(AttendanceStatus.ABSENT, 0)),
        ReportSummaryItem(label="On leave", value=statuses.get(AttendanceStatus.ON_LEAVE, 0)),
        ReportSummaryItem(label="Worked", value=sum(d.worked_minutes for d in days), kind="minutes"),
    ]
    chart = _per_date_chart(
        days,
        [("attended", "Attended"), ("late", "Late"), ("absent", "Absent")],
        lambda d, key: int(
            (key == "attended" and d.check_in_at is not None)
            or (key == "late" and d.status == AttendanceStatus.LATE)
            or (key == "absent" and d.status == AttendanceStatus.ABSENT)
        ),
    )
    return summary, chart


def _department_summary(
    days: list[AttendanceDay],
) -> tuple[list[ReportColumn], list[dict[str, Any]], ReportChart]:
    groups: dict[str, list[AttendanceDay]] = defaultdict(list)
    for day in days:
        groups[day.employee.department.name if day.employee.department else "No department"].append(day)
    rows = []
    for name in sorted(groups):
        items = groups[name]
        attended = [d for d in items if d.check_in_at]
        rows.append(
            {
                "department": name,
                "employees": len({d.employee_id for d in items}),
                "attended_days": len(attended),
                "late_days": sum(1 for d in items if d.late_minutes > 0),
                "early_days": sum(1 for d in items if d.early_minutes > 0),
                "absent_days": sum(1 for d in items if d.status == AttendanceStatus.ABSENT),
                "leave_days": sum(1 for d in items if d.status == AttendanceStatus.ON_LEAVE),
                "missing_checkout_days": sum(
                    1 for d in items if d.status == AttendanceStatus.MISSING_CHECKOUT
                ),
                "overtime_minutes": sum(d.overtime_minutes for d in items),
                "avg_worked_minutes": round(sum(d.worked_minutes for d in attended) / len(attended))
                if attended
                else 0,
            }
        )
    columns = [
        _DEPT,
        _col("employees", "Employees", "count"),
        _col("attended_days", "Attended days", "count"),
        _col("late_days", "Late days", "count"),
        _col("early_days", "Early exits", "count"),
        _col("absent_days", "Absent days", "count"),
        _col("leave_days", "Leave days", "count"),
        _col("missing_checkout_days", "Missing check-out", "count"),
        _col("overtime_minutes", "Overtime", "minutes"),
        _col("avg_worked_minutes", "Avg worked per day", "minutes"),
    ]
    chart = ReportChart(
        x_key="department",
        series=[
            ReportChartSeries(key="attended_days", label="Attended"),
            ReportChartSeries(key="late_days", label="Late"),
            ReportChartSeries(key="absent_days", label="Absent"),
        ],
        data=[
            {k: row[k] for k in ("department", "attended_days", "late_days", "absent_days")} for row in rows
        ],
    )
    return columns, rows, chart


async def _register(
    db: AsyncSession, scope: DataScope, first: date, last: date, filters: ReportFilters, limit: int | None
) -> tuple[list[ReportColumn], list[dict[str, Any]], int]:
    params = PageParams(page=1, page_size=limit or 100_000, sort=None)
    rows, total = await register_service.monthly_register(
        db, params, scope, f"{first:%Y-%m}", filters.department_id, None
    )
    if filters.employee_id:
        rows = [r for r in rows if r.employee_id == filters.employee_id]
        total = len(rows)
    days = [first + timedelta(days=i) for i in range((last - first).days + 1)]
    columns = [_CODE, _NAME, _DEPT]
    columns += [_col(f"d{d.day:02d}", str(d.day), "letter") for d in days]
    columns += [_col(f"total_{entry}", entry, "count") for entry in ATTENDANCE_STATUS_LETTERS.values()]
    columns += [_col("worked_minutes", "Worked", "minutes")]
    out = []
    for row in rows:
        record: dict[str, Any] = {
            "employee_code": row.employee_code,
            "employee_name": row.employee_name,
            "department": row.department_name,
            "worked_minutes": row.worked_minutes,
        }
        for cell in row.days:
            record[f"d{cell.work_date.day:02d}"] = cell.letter
        for letter in ATTENDANCE_STATUS_LETTERS.values():
            record[f"total_{letter}"] = row.totals.get(letter, 0)
        out.append(record)
    return columns, out, total


async def build_report(
    db: AsyncSession, scope: DataScope, report_type: ReportType, filters: ReportFilters, *, limit: int | None
) -> ReportOut:
    """`limit` caps the rows returned (preview); exports pass None to get everything."""
    first, last = validate_filters(report_type, filters)
    values = await settings_service.resolved(db)
    default_tz = str(values["general.timezone"])
    common: dict[str, Any] = {
        "report_type": report_type,
        "title": TITLES[report_type],
        "date_from": first,
        "date_to": last,
        "timezone": default_tz,
    }

    if report_type == ReportType.MONTHLY_REGISTER:
        columns, rows, total = await _register(db, scope, first, last, filters, limit)
        summary = [ReportSummaryItem(label="Employees", value=total)]
        return ReportOut(
            **common,
            columns=columns,
            rows=rows,
            total_rows=total,
            truncated=len(rows) < total,
            summary=summary,
            chart=None,
        )

    statuses = [filters.status] if filters.status else []
    query: dict[str, Any] = {
        "date_from": first,
        "date_to": last,
        "department_id": filters.department_id,
        "employee_id": filters.employee_id,
    }

    if report_type == ReportType.DEPARTMENT_SUMMARY:
        days = await attendance_repo.report_days(db, scope, **query, statuses=statuses or None)
        columns, rows, chart = _department_summary(days)
        summary = [
            ReportSummaryItem(label="Departments", value=len(rows)),
            ReportSummaryItem(label="Employees", value=len({d.employee_id for d in days})),
        ]
        return ReportOut(
            **common,
            columns=columns,
            rows=rows,
            total_rows=len(rows),
            truncated=False,
            summary=summary,
            chart=chart,
        )

    spec = _LIST_REPORTS[report_type]
    all_statuses = list(spec.statuses) or statuses or None
    if spec.statuses and statuses:
        all_statuses = [s for s in spec.statuses if s in statuses]
    total = await attendance_repo.count_report_days(
        db, scope, **query, statuses=all_statuses, condition=spec.condition
    )
    days = await attendance_repo.report_days(
        db, scope, **query, statuses=all_statuses, condition=spec.condition, limit=limit
    )
    # Summary and chart describe the whole result, not only the preview rows.
    everything = (
        days
        if limit is None or total <= limit
        else await attendance_repo.report_days(
            db, scope, **query, statuses=all_statuses, condition=spec.condition
        )
    )
    summary, chart = _list_summary(report_type, everything)
    return ReportOut(
        **common,
        columns=spec.columns,
        rows=[_day_row(d, default_tz) for d in days],
        total_rows=total,
        truncated=len(days) < total,
        summary=summary,
        chart=chart,
    )
