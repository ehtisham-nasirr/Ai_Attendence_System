"""Leave and holiday changes re-run the attendance rules for days that already exist (FR-22, FR-24)."""

from datetime import UTC, date, datetime
from typing import Any

from conftest import make_employee, make_org, make_user
from facetrack_common.constants import AttendanceStatus, UserRole
from facetrack_common.models import AttendanceDay
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.attendance import service as attendance_service
from app.domain.settings import service as settings_service

MONDAY = date(2026, 9, 7)


async def _closed_absent_day(db: AsyncSession) -> tuple[Any, AttendanceDay]:
    org = await make_org(db)
    employee = await make_employee(db, org, "E1", created_at=datetime(2026, 8, 1, tzinfo=UTC))
    values = await settings_service.resolved(db)
    day = await attendance_service.recompute_day(db, employee, MONDAY, values, finalize=True)
    await db.commit()
    assert day.status == AttendanceStatus.ABSENT
    return employee, day


async def test_fr24_leave_turns_closed_absent_day_into_on_leave_and_back(make_api, db: AsyncSession) -> None:  # type: ignore[no-untyped-def]
    employee, day = await _closed_absent_day(db)
    hr = await make_api(await make_user(db, UserRole.HR_ADMIN, "hr"))
    created = await hr.post(
        "/api/v1/leaves",
        json={
            "employee_id": employee.id,
            "from_date": "2026-09-07",
            "to_date": "2026-09-08",
            "type": "Annual",
        },
    )
    assert created.status_code == 201
    await db.refresh(day)
    assert day.status == AttendanceStatus.ON_LEAVE and day.finalized_at is not None

    assert (await hr.delete(f"/api/v1/leaves/{created.json()['data']['id']}")).status_code == 204
    await db.refresh(day)
    assert day.status == AttendanceStatus.ABSENT


async def test_holiday_changes_queue_recompute_for_each_affected_date(
    make_api,
    db: AsyncSession,
    no_celery: list[tuple[str, tuple[Any, ...]]],  # type: ignore[no-untyped-def]
) -> None:
    org = await make_org(db)
    admin = await make_api(await make_user(db, UserRole.SUPER_ADMIN, "admin"))
    created = await admin.post(
        "/api/v1/holidays", json={"location_id": org["location"].id, "date": "2026-09-07", "name": "Holiday"}
    )
    holiday_id = created.json()["data"]["id"]
    await admin.put(f"/api/v1/holidays/{holiday_id}", json={"date": "2026-09-08"})
    await admin.delete(f"/api/v1/holidays/{holiday_id}")
    recomputes = sorted(args[0] for name, args in no_celery if name.endswith("recompute_date"))
    assert recomputes == ["2026-09-07", "2026-09-07", "2026-09-08", "2026-09-08"]


async def test_recompute_date_applies_a_new_holiday_to_a_closed_day(db: AsyncSession) -> None:
    from facetrack_common.models import Holiday

    employee, day = await _closed_absent_day(db)
    db.add(Holiday(location_id=employee.location_id, date=MONDAY, name="Holiday"))
    await db.commit()
    assert await attendance_service.recompute_date(db, MONDAY) == 1
    await db.refresh(day)
    assert day.status == AttendanceStatus.HOLIDAY
