"""Attendance scoping and the correction workflow (FR-25, FR-26, ADR-0004, §4)."""

import uuid
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from conftest import make_camera, make_employee, make_org, make_user
from facetrack_common.constants import CameraRole, UserRole
from facetrack_common.events import RecognitionEvent
from facetrack_common.models import Department
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.recognition import service as recognition

PKT = ZoneInfo("Asia/Karachi")


def at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, 5, hour, minute, tzinfo=PKT)


async def _world(db: AsyncSession) -> dict:  # type: ignore[type-arg]
    org = await make_org(db)
    sales_emp = await make_employee(db, org, "S1", department="sales")
    fin_emp = await make_employee(db, org, "F1", department="finance")
    entry = await make_camera(db, org, "Entrance", CameraRole.ENTRY)
    for code in ("S1", "F1"):
        await recognition.process_event(
            db,
            RecognitionEvent.model_validate(
                {
                    "event_id": str(uuid.uuid4()),
                    "camera_id": entry.id,
                    "employee_code": code,
                    "status": "recognized",
                    "confidence": 0.7,
                    "track_id": 1,
                    "captured_at": at(9, 40).astimezone(UTC).isoformat(),
                    "model_name": "sface",
                    "engine_node": "node-1",
                }
            ),
        )
    manager = await make_user(db, UserRole.DEPARTMENT_MANAGER, "mgr")
    department = await db.get(Department, org["sales"].id)
    assert department is not None
    department.manager_user_id = manager.id
    await db.commit()
    return {
        "org": org,
        "sales_emp": sales_emp,
        "fin_emp": fin_emp,
        "manager": manager,
        "hr": await make_user(db, UserRole.HR_ADMIN, "hr"),
        "employee_user": await make_user(db, UserRole.EMPLOYEE, "s1user", employee_id=sales_emp.id),
        "operator": await make_user(db, UserRole.OPERATOR, "op"),
    }


async def _days(client) -> dict[str, dict]:  # type: ignore[no-untyped-def, type-arg]
    body = (await client.get("/api/v1/attendance", params={"date_from": "2026-10-05"})).json()
    return {row["employee_code"]: row for row in body["data"]}


async def test_section4_attendance_scope_per_role(make_api, db: AsyncSession) -> None:  # type: ignore[no-untyped-def]
    world = await _world(db)
    assert set(await _days(await make_api(world["hr"]))) == {"S1", "F1"}
    assert set(await _days(await make_api(world["manager"]))) == {"S1"}
    assert set(await _days(await make_api(world["employee_user"]))) == {"S1"}
    operator = await make_api(world["operator"])
    assert (await operator.get("/api/v1/attendance")).status_code == 403


async def test_out_of_scope_record_is_404(make_api, db: AsyncSession) -> None:  # type: ignore[no-untyped-def]
    world = await _world(db)
    hr_days = await _days(await make_api(world["hr"]))
    manager = await make_api(world["manager"])
    assert (await manager.get(f"/api/v1/attendance/{hr_days['F1']['id']}")).status_code == 404


async def test_fr26_employee_requests_and_manager_approves(make_api, db: AsyncSession) -> None:  # type: ignore[no-untyped-def]
    world = await _world(db)
    employee = await make_api(world["employee_user"])
    day = (await _days(employee))["S1"]
    assert day["status"] == "late" and day["late_minutes"] == 25
    request = await employee.post(
        f"/api/v1/attendance/{day['id']}/corrections",
        json={
            "field": "check_in_at",
            "new_value": "2026-10-05T09:00:00+05:00",
            "reason": "Badge reader queue",
        },
    )
    assert request.status_code == 201
    correction = request.json()["data"]["correction"]
    assert correction["status"] == "pending" and correction["old_value"].startswith("2026-10-05T04:40")
    assert (
        await employee.post(f"/api/v1/corrections/{correction['id']}/approve", json={})
    ).status_code == 403

    manager = await make_api(world["manager"])
    approved = await manager.post(f"/api/v1/corrections/{correction['id']}/approve", json={"comment": "ok"})
    assert approved.status_code == 200
    result = approved.json()["data"]
    assert result["correction"]["status"] == "approved" and result["correction"]["approved_by_name"] == "mgr"
    assert result["attendance"]["status"] == "present" and result["attendance"]["is_manual"] is True
    again = await manager.post(f"/api/v1/corrections/{correction['id']}/reject", json={})
    assert again.status_code == 409


async def test_adr0004_manager_cannot_decide_other_department(make_api, db: AsyncSession) -> None:  # type: ignore[no-untyped-def]
    world = await _world(db)
    hr = await make_api(world["hr"])
    fin_day = (await _days(hr))["F1"]
    fin_user = await make_user(db, UserRole.EMPLOYEE, "f1user", employee_id=world["fin_emp"].id)
    employee = await make_api(fin_user)
    request = await employee.post(
        f"/api/v1/attendance/{fin_day['id']}/corrections",
        json={"field": "status", "new_value": "present", "reason": "Was at a client site"},
    )
    correction_id = request.json()["data"]["correction"]["id"]
    manager = await make_api(world["manager"])
    assert (await manager.post(f"/api/v1/corrections/{correction_id}/approve", json={})).status_code == 404


async def test_fr25_hr_applies_directly_and_locked_field_survives_new_events(
    make_api, db: AsyncSession
) -> None:  # type: ignore[no-untyped-def]
    world = await _world(db)
    hr = await make_api(world["hr"])
    day = (await _days(hr))["S1"]
    applied = await hr.post(
        f"/api/v1/attendance/{day['id']}/corrections",
        json={
            "field": "check_in_at",
            "new_value": "2026-10-05T08:55:00+05:00",
            "reason": "Camera was offline",
        },
    )
    assert applied.json()["data"]["correction"]["status"] == "approved"
    # A later automatic event must not override the corrected (locked) check-in.
    entry_id = (await db.execute(text("select id from cameras where name='Entrance'"))).scalar()
    await recognition.process_event(
        db,
        RecognitionEvent.model_validate(
            {
                "event_id": str(uuid.uuid4()),
                "camera_id": entry_id,
                "employee_code": "S1",
                "status": "recognized",
                "confidence": 0.7,
                "track_id": 2,
                "captured_at": at(8, 30).astimezone(UTC).isoformat(),
                "model_name": "sface",
                "engine_node": "node-1",
            }
        ),
    )
    refreshed = (await _days(hr))["S1"]
    assert refreshed["check_in_at"] == "2026-10-05T03:55:00Z" and refreshed["status"] == "present"


async def test_correction_validation(make_api, db: AsyncSession) -> None:  # type: ignore[no-untyped-def]
    world = await _world(db)
    hr = await make_api(world["hr"])
    day = (await _days(hr))["S1"]
    url = f"/api/v1/attendance/{day['id']}/corrections"
    wrong_day = await hr.post(
        url, json={"field": "check_in_at", "new_value": "2026-10-09T09:00:00+05:00", "reason": "typo fix"}
    )
    assert wrong_day.status_code == 422
    naive = await hr.post(
        url, json={"field": "check_out_at", "new_value": "2026-10-05T18:00:00", "reason": "typo fix"}
    )
    assert naive.status_code == 422
    bad_status = await hr.post(url, json={"field": "status", "new_value": "vacation", "reason": "typo fix"})
    assert bad_status.status_code == 422
    no_reason = await hr.post(url, json={"field": "status", "new_value": "present", "reason": ""})
    assert no_reason.status_code == 422


async def test_fr25_manual_entry_for_a_missing_day(make_api, db: AsyncSession) -> None:  # type: ignore[no-untyped-def]
    world = await _world(db)
    hr = await make_api(world["hr"])
    body = {
        "employee_id": world["sales_emp"].id,
        "work_date": "2026-10-06",
        "check_in_at": "2026-10-06T09:00:00+05:00",
        "check_out_at": "2026-10-06T18:00:00+05:00",
        "reason": "Worked from branch office",
    }
    created = await hr.post("/api/v1/attendance", json=body)
    assert created.status_code == 201 and created.json()["data"]["is_manual"] is True
    assert (await hr.post("/api/v1/attendance", json=body)).status_code == 409
    employee = await make_api(world["employee_user"])
    assert (
        await employee.post("/api/v1/attendance", json={**body, "work_date": "2026-10-07"})
    ).status_code == 403


async def test_manual_entry_with_check_out_before_check_in_explains_why(make_api, db: AsyncSession) -> None:  # type: ignore[no-untyped-def]
    """Seen in the owner's test: 11:20 PM in, 04:21 PM out. The message must say what is wrong."""
    world = await _world(db)
    hr = await make_api(world["hr"])
    response = await hr.post(
        "/api/v1/attendance",
        json={
            "employee_id": world["sales_emp"].id,
            "work_date": "2026-10-06",
            "check_in_at": "2026-10-06T23:20:00+05:00",
            "check_out_at": "2026-10-06T16:21:00+05:00",
            "reason": "missed by camera",
        },
    )
    assert response.status_code == 422
    assert response.json()["errors"]["body"] == ["Check-out must be after check-in"]


async def test_corrections_list_tabs_are_scoped(make_api, db: AsyncSession) -> None:  # type: ignore[no-untyped-def]
    world = await _world(db)
    employee = await make_api(world["employee_user"])
    day = (await _days(employee))["S1"]
    await employee.post(
        f"/api/v1/attendance/{day['id']}/corrections",
        json={"field": "status", "new_value": "present", "reason": "Traffic jam"},
    )
    hr = await make_api(world["hr"])
    pending = await hr.get("/api/v1/corrections", params={"status": "pending"})
    assert pending.json()["pagination"]["total"] == 1
    operator = await make_api(world["operator"])
    assert (await operator.get("/api/v1/corrections")).status_code == 403
