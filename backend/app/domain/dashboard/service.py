"""Dashboard counters for today (FR-29). Computed from attendance days; the frontend only displays them."""

import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from facetrack_common.constants import AttendanceStatus
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import get_async_redis
from app.core.security import DataScope
from app.domain.attendance import rules
from app.domain.attendance.service import shift_rule
from app.domain.cameras.service import RUNTIME_KEY
from app.domain.settings import service as settings_service
from app.repositories import attendance_repo, camera_repo, employee_repo, event_repo, organization_repo
from app.schemas.system import CameraHealthItem, DashboardSummary, DepartmentCount, HourlyCount

_PRESENT = {
    AttendanceStatus.PRESENT,
    AttendanceStatus.LATE,
    AttendanceStatus.EARLY_EXIT,
    AttendanceStatus.HALF_DAY,
    AttendanceStatus.MISSING_CHECKOUT,
}
LOAD_KEY = "engine_load:{node}"


async def summary(db: AsyncSession, scope: DataScope, location_id: int | None) -> DashboardSummary:
    values = await settings_service.resolved(db)
    tz = ZoneInfo(str(values["general.timezone"]))
    if location_id:
        from facetrack_common.models import Location  # noqa: PLC0415

        location = await db.get(Location, location_id)
        if location is not None:
            tz = ZoneInfo(location.timezone)
    now = datetime.now(UTC)
    today = now.astimezone(tz).date()
    rule_settings = settings_service.rule_settings(values)

    employees = [
        e
        for e in await employee_repo.active_employees(db)
        if scope.allows(e.department_id, e.id) and (location_id is None or e.location_id == location_id)
    ]
    # Each employee's "today" is their current work date: before the 02:00 day close it is still
    # yesterday for a day shift, and a night shift keeps its start date (Q10).
    work_dates = {}
    for employee in employees:
        employee_tz = ZoneInfo(employee.location.timezone) if employee.location else tz
        work_dates[employee.id] = rules.work_date_for(
            now, shift_rule(employee.shift), employee_tz, rule_settings
        )
    days_by_date = {d: await attendance_repo.days_on(db, d) for d in set(work_dates.values()) | {today}}
    leave_by_date = {d: await employee_repo.leave_employee_ids_on(db, d) for d in days_by_date}
    holidays_by_date = {d: await organization_repo.holiday_location_ids(db, d) for d in days_by_date}

    counts: Counter[str] = Counter()
    departments: dict[int | None, DepartmentCount] = {}
    hourly: Counter[int] = Counter()
    for employee in employees:
        dept = departments.setdefault(
            employee.department_id,
            DepartmentCount(
                department_id=employee.department_id,
                department_name=employee.department.name if employee.department else "No department",
                present=0,
                absent=0,
                late=0,
            ),
        )
        work_date = work_dates[employee.id]
        day = days_by_date[work_date].get(employee.id)
        working = (
            employee.shift is not None
            and not rules.is_weekly_off(work_date, shift_rule(employee.shift))
            and employee.location_id not in holidays_by_date[work_date]
        )
        if employee.id in leave_by_date[work_date]:
            counts["on_leave"] += 1
            continue
        if day is not None and day.check_in_at is not None:
            counts["present"] += 1
            dept.present += 1
            hourly[day.check_in_at.astimezone(tz).hour] += 1
            if day.late_minutes > 0:
                counts["late"] += 1
                dept.late += 1
            if day.check_out_at is None:
                counts["in_office_now"] += 1
        elif day is not None and day.status in _PRESENT:
            counts["present"] += 1  # e.g. seen only on an exit camera, or a manual entry
            dept.present += 1
        elif working:
            counts["absent"] += 1
            dept.absent += 1
        if working:
            counts["expected"] += 1

    start = datetime.combine(today, datetime.min.time(), tzinfo=tz).astimezone(UTC)
    unknown_today = await event_repo.count_unknown_between(db, start, start + timedelta(days=1))
    cameras = await camera_repo.all_cameras(db)
    redis = get_async_redis()
    runtimes = await redis.mget([RUNTIME_KEY.format(camera_id=c.id) for c in cameras]) if cameras else []
    camera_items = []
    for camera, raw in zip(cameras, runtimes, strict=True):
        runtime = json.loads(raw) if raw else {}
        camera_items.append(
            CameraHealthItem(
                camera_id=camera.id,
                name=camera.name,
                status=camera.status.value,
                mode=runtime.get("mode"),
                fps_actual=runtime.get("fps_actual"),
            )
        )
    from app.core.config import get_settings  # noqa: PLC0415

    levels = {}
    for node in get_settings().engine_nodes:
        level = await redis.get(LOAD_KEY.format(node=node))
        if level is not None:
            levels[node] = int(level)

    return DashboardSummary(
        work_date=today,
        expected=counts["expected"],
        present=counts["present"],
        late=counts["late"],
        absent=counts["absent"],
        on_leave=counts["on_leave"],
        in_office_now=counts["in_office_now"],
        unknown_today=unknown_today,
        hourly_arrivals=[HourlyCount(hour=h, count=hourly[h]) for h in range(24) if hourly[h]],
        departments=sorted(departments.values(), key=lambda d: d.department_name),
        cameras=camera_items,
        load_levels=levels,
    )
