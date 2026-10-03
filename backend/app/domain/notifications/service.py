"""What the scheduled emails say and when they are due (FR-32, FR-33). Sending happens in Celery."""

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from facetrack_common.constants import ReportType, UserRole
from facetrack_common.models import User
from facetrack_common.settings_keys import ReportSchedule
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import DataScope, data_scope
from app.domain.attendance.rules import parse_hhmm
from app.domain.dashboard import service as dashboard_service
from app.schemas.system import DashboardSummary


@dataclass(frozen=True)
class Email:
    recipients: list[str]
    subject: str
    text: str


def summary_text(summary: DashboardSummary, heading: str) -> str:
    lines = [
        heading,
        "",
        f"Work date: {summary.work_date:%d %b %Y}",
        f"Expected: {summary.expected}",
        f"Present: {summary.present}",
        f"Late: {summary.late}",
        f"Absent so far: {summary.absent}",
        f"On leave: {summary.on_leave}",
        f"In office now: {summary.in_office_now}",
        f"Unknown faces today: {summary.unknown_today}",
    ]
    if summary.departments:
        lines += ["", "By department (present / late / absent):"]
        lines += [f"  {d.department_name}: {d.present} / {d.late} / {d.absent}" for d in summary.departments]
    offline = [c.name for c in summary.cameras if c.status == "offline"]
    if offline:
        lines += ["", f"Cameras offline: {', '.join(offline)}"]
    lines += ["", "Open the FaceTrack portal for details. Statuses are final after the day closes."]
    return "\n".join(lines)


async def daily_summary_emails(db: AsyncSession, hr_emails: list[str]) -> list[Email]:
    """HR gets the whole organisation; each department manager gets their own departments (§4 scope)."""
    emails: list[Email] = []
    if hr_emails:
        summary = await dashboard_service.summary(db, DataScope(all_employees=True), None)
        emails.append(
            Email(
                hr_emails,
                f"FaceTrack daily summary {summary.work_date:%d %b %Y}",
                summary_text(summary, "Attendance today"),
            )
        )
    managers = (
        await db.scalars(
            select(User).where(
                User.role == UserRole.DEPARTMENT_MANAGER, User.is_active.is_(True), User.deleted_at.is_(None)
            )
        )
    ).all()
    for manager in managers:
        scope = await data_scope(db, manager)
        if not scope.department_ids:
            continue
        summary = await dashboard_service.summary(db, scope, None)
        emails.append(
            Email(
                [manager.email],
                f"FaceTrack daily summary {summary.work_date:%d %b %Y}",
                summary_text(summary, "Attendance today in your departments"),
            )
        )
    return emails


@dataclass(frozen=True)
class DuePeriod:
    key: str
    date_from: date
    date_to: date


def schedule_id(schedule: ReportSchedule) -> str:
    raw = json.dumps(schedule.model_dump(mode="json"), sort_keys=True).encode()
    return hashlib.sha256(raw).hexdigest()[:16]


def due_period(schedule: ReportSchedule, local_now: datetime) -> DuePeriod | None:
    """The period a schedule should send now, or None. Daily: yesterday, from `time` each day.
    Weekly: last Monday to Sunday, from `time` on Monday. Monthly: last month, from `time` on the 1st."""
    today = local_now.date()
    if local_now.time() < parse_hhmm(schedule.time):
        return None
    if schedule.frequency == "daily":
        day = today - timedelta(days=1)
        return DuePeriod(f"{schedule_id(schedule)}:{day}", day, day)
    if schedule.frequency == "weekly":
        if today.isoweekday() != 1:
            return None
        start = today - timedelta(days=7)
        return DuePeriod(f"{schedule_id(schedule)}:{start}", start, today - timedelta(days=1))
    if today.day != 1:
        return None
    last = today - timedelta(days=1)
    first = last.replace(day=1)
    return DuePeriod(f"{schedule_id(schedule)}:{first}", first, last)


def schedulable(schedule: ReportSchedule) -> bool:
    # Employee history needs one employee; a schedule has no employee field.
    return schedule.report_type != ReportType.EMPLOYEE_HISTORY
