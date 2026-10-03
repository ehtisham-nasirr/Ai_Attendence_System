"""Organisation CRUD (FR-21, FR-36) and user management (§4): success, invalid, 401/403/404/409, audit."""

from conftest import Api, make_employee, make_org, make_user
from facetrack_common.constants import UserRole
from facetrack_common.models import AuditLog, User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def _admin(api: Api, db: AsyncSession) -> User:
    admin = await make_user(db, UserRole.SUPER_ADMIN, "admin1")
    await api.as_user(admin)
    return admin


async def test_fr36_location_crud_with_audit(api: Api, db: AsyncSession) -> None:
    await _admin(api, db)
    created = await api.post("/api/v1/locations", json={"name": "Lahore", "timezone": "Asia/Karachi"})
    assert created.status_code == 201
    location_id = created.json()["data"]["id"]
    assert (await api.post("/api/v1/locations", json={"name": "Lahore"})).status_code == 409
    assert (
        await api.post("/api/v1/locations", json={"name": "X", "timezone": "Mars/Base"})
    ).status_code == 422
    updated = await api.put(f"/api/v1/locations/{location_id}", json={"address": "Gulberg"})
    assert updated.status_code == 200 and updated.json()["data"]["address"] == "Gulberg"
    listing = (await api.get("/api/v1/locations")).json()
    assert listing["pagination"]["total"] == 1
    assert (await api.delete(f"/api/v1/locations/{location_id}")).status_code == 204
    assert (await api.put(f"/api/v1/locations/{location_id}", json={"name": "Y"})).status_code == 404
    assert (await api.get("/api/v1/locations")).json()["pagination"]["total"] == 0
    actions = (
        await db.scalars(select(AuditLog.action).where(AuditLog.entity == "location").order_by(AuditLog.id))
    ).all()
    assert actions == ["location.create", "location.update", "location.delete"]


async def test_department_code_unique_and_manager_must_exist(api: Api, db: AsyncSession) -> None:
    admin = await _admin(api, db)
    body = {"name": "Operations", "code": "OPS"}
    created = await api.post("/api/v1/departments", json=body)
    assert created.status_code == 201
    department_id = created.json()["data"]["id"]
    assert (await api.post("/api/v1/departments", json=body)).status_code == 409
    assert (await api.post("/api/v1/departments", json={"name": "B", "code": "has space"})).status_code == 422
    bad_manager = await api.put(f"/api/v1/departments/{department_id}", json={"manager_user_id": 99999})
    assert bad_manager.status_code == 422 and "manager_user_id" in bad_manager.json()["errors"]
    good = await api.put(f"/api/v1/departments/{department_id}", json={"manager_user_id": admin.id})
    assert good.json()["data"]["manager_user_id"] == admin.id
    assert (await api.get(f"/api/v1/departments/{department_id}")).status_code == 200
    assert (await api.delete(f"/api/v1/departments/{department_id}")).status_code == 204
    assert (await api.get(f"/api/v1/departments/{department_id}")).status_code == 404


async def test_fr21_night_shift_and_weekly_off_validation(api: Api, db: AsyncSession) -> None:
    await _admin(api, db)
    created = await api.post(
        "/api/v1/shifts",
        json={
            "name": "Night",
            "start_time": "22:00",
            "end_time": "06:00",
            "is_night_shift": True,
            "weekly_offs": [7],
        },
    )
    assert created.status_code == 201
    shift_id = created.json()["data"]["id"]
    bad = await api.post(
        "/api/v1/shifts", json={"name": "Bad", "start_time": "09:00", "end_time": "18:00", "weekly_offs": [8]}
    )
    assert bad.status_code == 422
    assert (await api.put(f"/api/v1/shifts/{shift_id}", json={"weekly_offs": [0]})).status_code == 422
    updated = await api.put(f"/api/v1/shifts/{shift_id}", json={"weekly_offs": [6, 6, 5], "grace_in_min": 10})
    assert updated.json()["data"]["weekly_offs"] == [5, 6] and updated.json()["data"]["grace_in_min"] == 10
    assert (await api.get(f"/api/v1/shifts/{shift_id}")).status_code == 200
    assert (await api.delete(f"/api/v1/shifts/{shift_id}")).status_code == 204
    assert (await api.get(f"/api/v1/shifts/{shift_id}")).status_code == 404


async def test_holidays_are_unique_per_location_and_date(api: Api, db: AsyncSession) -> None:
    await _admin(api, db)
    org = await make_org(db)
    location_id = org["location"].id
    body = {"location_id": location_id, "date": "2026-12-25", "name": "Quaid Day"}
    created = await api.post("/api/v1/holidays", json=body)
    assert created.status_code == 201
    holiday_id = created.json()["data"]["id"]
    assert (await api.post("/api/v1/holidays", json=body)).status_code == 409
    assert (await api.post("/api/v1/holidays", json={**body, "location_id": 99999})).status_code == 404
    second = await api.post(
        "/api/v1/holidays", json={**body, "date": "2026-08-14", "name": "Independence Day"}
    )
    assert (
        await api.put(f"/api/v1/holidays/{second.json()['data']['id']}", json={"date": "2026-12-25"})
    ).status_code == 409
    in_range = await api.get("/api/v1/holidays", params={"date_from": "2026-12-01", "date_to": "2026-12-31"})
    assert [h["id"] for h in in_range.json()["data"]] == [holiday_id]
    assert (await api.delete(f"/api/v1/holidays/{holiday_id}")).status_code == 204
    assert (await api.delete(f"/api/v1/holidays/{holiday_id}")).status_code == 404


async def test_organization_permissions(make_api, db: AsyncSession) -> None:  # type: ignore[no-untyped-def]
    org = await make_org(db)
    anonymous = await make_api()
    assert (await anonymous.get("/api/v1/departments")).status_code == 401
    manager = await make_api(await make_user(db, UserRole.DEPARTMENT_MANAGER, "mgr"))
    assert (await manager.get("/api/v1/departments")).status_code == 200  # read for filters
    assert (await manager.post("/api/v1/departments", json={"name": "X", "code": "X"})).status_code == 403
    hr = await make_api(await make_user(db, UserRole.HR_ADMIN, "hr"))
    assert (await hr.delete(f"/api/v1/shifts/{org['shift'].id}")).status_code == 403
    employee = await make_api(
        await make_user(db, UserRole.EMPLOYEE, "emp", (await make_employee(db, org, "E-1")).id)
    )
    assert (await employee.get("/api/v1/shifts")).status_code == 403


async def test_user_lifecycle_and_self_protection(api: Api, db: AsyncSession) -> None:
    admin = await _admin(api, db)
    created = await api.post(
        "/api/v1/users",
        json={
            "name": "Hina HR",
            "username": "hina",
            "email": "hina@example.com",
            "role": "hr_admin",
            "password": "Strong-pass-1",
        },
    )
    assert created.status_code == 201
    user = created.json()["data"]
    assert "password" not in user and "password_hash" not in user
    assert (
        await api.post(
            "/api/v1/users",
            json={
                "name": "Dup",
                "username": "hina",
                "email": "x@example.com",
                "role": "hr_admin",
                "password": "Strong-pass-1",
            },
        )
    ).status_code == 409
    weak = await api.post(
        "/api/v1/users",
        json={
            "name": "W",
            "username": "weak",
            "email": "w@example.com",
            "role": "hr_admin",
            "password": "onlyletters",
        },
    )
    assert weak.status_code == 422
    no_link = await api.post(
        "/api/v1/users",
        json={
            "name": "E",
            "username": "emp",
            "email": "e@example.com",
            "role": "employee",
            "password": "Strong-pass-1",
        },
    )
    assert no_link.status_code == 422 and "employee_id" in no_link.json()["errors"]

    updated = await api.put(f"/api/v1/users/{user['id']}", json={"role": "department_manager"})
    assert updated.json()["data"]["role"] == "department_manager"
    stored = await db.get(User, user["id"], populate_existing=True)
    assert stored is not None and stored.session_version == 2  # role change ends sessions

    own = await api.put(f"/api/v1/users/{admin.id}", json={"role": "hr_admin"})
    assert own.status_code == 422
    assert (await api.delete(f"/api/v1/users/{admin.id}")).status_code == 422
    assert (await api.delete(f"/api/v1/users/{user['id']}")).status_code == 204
    assert (await api.get(f"/api/v1/users/{user['id']}")).status_code == 404
    assert (await api.get("/api/v1/users")).json()["pagination"]["total"] == 1


async def test_unlock_and_password_reset_by_admin(make_api, db: AsyncSession) -> None:  # type: ignore[no-untyped-def]
    admin = await make_api(await make_user(db, UserRole.SUPER_ADMIN, "admin1"))
    target = await make_user(db, UserRole.HR_ADMIN, "locked")
    outsider = await make_api()
    for _ in range(5):
        await outsider.login("locked", "Wrong-pass-99")
    listed = (await admin.get(f"/api/v1/users/{target.id}")).json()["data"]
    assert listed["is_locked"] is True
    reset = await admin.put(f"/api/v1/users/{target.id}", json={"unlock": True, "password": "Brand-new-77"})
    assert reset.status_code == 200 and reset.json()["data"]["is_locked"] is False
    assert (await outsider.login("locked", "Brand-new-77")).status_code == 200


async def test_employee_account_links_to_employee(api: Api, db: AsyncSession) -> None:
    await _admin(api, db)
    employee = await make_employee(db, await make_org(db), "E-100")
    created = await api.post(
        "/api/v1/users",
        json={
            "name": "Ali",
            "username": "ali",
            "email": "ali@example.com",
            "role": "employee",
            "employee_id": employee.id,
            "password": "Strong-pass-1",
        },
    )
    assert created.status_code == 201 and created.json()["data"]["employee_id"] == employee.id


async def test_users_endpoints_are_super_admin_only(make_api, db: AsyncSession) -> None:  # type: ignore[no-untyped-def]
    hr = await make_api(await make_user(db, UserRole.HR_ADMIN, "hr"))
    assert (await hr.get("/api/v1/users")).status_code == 403
    assert (await (await make_api()).get("/api/v1/users")).status_code == 401
