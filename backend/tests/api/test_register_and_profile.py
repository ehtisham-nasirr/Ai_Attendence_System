"""Monthly register (§13 screen 8) and portal profile/sign-in options (FR-40, NFR-14)."""

from datetime import UTC, date, datetime

from conftest import make_employee, make_org, make_user
from facetrack_common.constants import AttendanceStatus, UserRole
from facetrack_common.models import AttendanceDay, Department, Setting
from sqlalchemy.ext.asyncio import AsyncSession


def _day(
    employee_id: int, day: int, status: AttendanceStatus, worked: int = 480, late: int = 0
) -> AttendanceDay:
    return AttendanceDay(
        employee_id=employee_id,
        work_date=date(2026, 9, day),
        status=status,
        worked_minutes=worked,
        late_minutes=late,
        early_minutes=0,
        overtime_minutes=0,
        is_manual=False,
    )


async def test_register_letters_totals_and_scope(make_api, db: AsyncSession) -> None:  # type: ignore[no-untyped-def]
    org = await make_org(db)
    created = datetime(2026, 8, 1, tzinfo=UTC)
    s1 = await make_employee(db, org, "S1", department="sales", created_at=created)
    await make_employee(db, org, "S2", department="sales", created_at=created)
    f1 = await make_employee(db, org, "F1", department="finance", created_at=created)
    await make_employee(  # joins after September
        db, org, "S9", department="sales", created_at=datetime(2026, 11, 1, tzinfo=UTC)
    )
    db.add_all(
        [
            _day(s1.id, 1, AttendanceStatus.PRESENT),
            _day(s1.id, 2, AttendanceStatus.LATE, late=20),
            _day(s1.id, 3, AttendanceStatus.PRESENT),
            _day(s1.id, 4, AttendanceStatus.ABSENT, worked=0),
            _day(f1.id, 1, AttendanceStatus.ON_LEAVE, worked=0),
            AttendanceDay(  # next month: not in the September register
                employee_id=s1.id,
                work_date=date(2026, 10, 1),
                status=AttendanceStatus.PRESENT,
                worked_minutes=480,
                late_minutes=0,
                early_minutes=0,
                overtime_minutes=0,
                is_manual=False,
            ),
        ]
    )
    manager = await make_user(db, UserRole.DEPARTMENT_MANAGER, "mgr")
    department = await db.get(Department, org["sales"].id)
    assert department is not None
    department.manager_user_id = manager.id
    await db.commit()

    hr = await make_api(await make_user(db, UserRole.HR_ADMIN, "hr"))
    body = (await hr.get("/api/v1/attendance/register", params={"month": "2026-09"})).json()
    assert [r["employee_code"] for r in body["data"]] == ["F1", "S1", "S2"]  # S9 joined later
    s1_row = next(r for r in body["data"] if r["employee_code"] == "S1")
    assert [d["letter"] for d in s1_row["days"]] == ["P", "L", "P", "A"]
    assert s1_row["totals"] == {"P": 2, "L": 1, "A": 1}
    assert s1_row["worked_minutes"] == 1440 and s1_row["late_minutes"] == 20
    assert next(r for r in body["data"] if r["employee_code"] == "S2")["days"] == []

    scoped = (
        await (await make_api(manager)).get("/api/v1/attendance/register", params={"month": "2026-09"})
    ).json()
    assert [r["employee_code"] for r in scoped["data"]] == ["S1", "S2"]
    own = await make_api(await make_user(db, UserRole.EMPLOYEE, "s1u", employee_id=s1.id))
    mine = (await own.get("/api/v1/attendance/register", params={"month": "2026-09"})).json()
    assert [r["employee_code"] for r in mine["data"]] == ["S1"]

    assert (await hr.get("/api/v1/attendance/register", params={"month": "2026-13"})).status_code == 422
    assert (await hr.get("/api/v1/attendance/register", params={"month": "Sept"})).status_code == 422
    operator = await make_api(await make_user(db, UserRole.OPERATOR, "op"))
    assert (await operator.get("/api/v1/attendance/register", params={"month": "2026-09"})).status_code == 403


async def test_profile_carries_display_timezone(make_api, db: AsyncSession) -> None:  # type: ignore[no-untyped-def]
    user = await make_user(db, UserRole.HR_ADMIN, "hr")
    api = await make_api(user)
    assert (await api.get("/api/v1/auth/me")).json()["data"]["timezone"] == "Asia/Karachi"
    db.add(Setting(key="general.timezone", value="Asia/Dubai"))
    await db.commit()
    assert (await api.get("/api/v1/auth/me")).json()["data"]["timezone"] == "Asia/Dubai"


async def test_auth_options_are_public_and_reflect_ldap_setting(make_api, db: AsyncSession) -> None:  # type: ignore[no-untyped-def]
    anonymous = await make_api()
    assert (await anonymous.get("/api/v1/auth/options")).json()["data"] == {"ldap_enabled": False}
    db.add(Setting(key="auth.ldap_enabled", value=True))
    await db.commit()
    assert (await anonymous.get("/api/v1/auth/options")).json()["data"] == {"ldap_enabled": True}
