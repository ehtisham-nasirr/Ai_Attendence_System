"""Reports API (§12 `GET /reports/{type}`, FR-31): preview, 202 export job, download by owner only."""

import asyncio
from datetime import UTC, date, datetime
from typing import Any

from conftest import make_employee, make_org, make_user
from facetrack_common.constants import AttendanceStatus, UserRole
from facetrack_common.models import AttendanceDay, AuditLog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.worker.tasks.reports import export_report


async def _seed(db: AsyncSession) -> dict[str, Any]:
    org = await make_org(db)
    employee = await make_employee(db, org, "S1", created_at=datetime(2026, 8, 1, tzinfo=UTC))
    db.add(
        AttendanceDay(
            employee_id=employee.id,
            work_date=date(2026, 9, 1),
            status=AttendanceStatus.LATE,
            check_in_at=datetime(2026, 9, 1, 4, 40, tzinfo=UTC),
            worked_minutes=480,
            late_minutes=25,
            early_minutes=0,
            overtime_minutes=0,
            is_manual=False,
            finalized_at=datetime(2026, 9, 1, 21, tzinfo=UTC),
        )
    )
    await db.commit()
    return {"org": org, "employee": employee}


PARAMS = {"date_from": "2026-09-01", "date_to": "2026-09-30"}


async def test_preview_and_permissions(make_api, db: AsyncSession) -> None:  # type: ignore[no-untyped-def]
    await _seed(db)
    hr = await make_api(await make_user(db, UserRole.HR_ADMIN, "hr"))
    body = (await hr.get("/api/v1/reports/late_arrivals", params=PARAMS)).json()
    assert body["data"]["title"] == "Late arrivals" and body["data"]["total_rows"] == 1
    assert body["data"]["rows"][0]["late_minutes"] == 25
    assert (await hr.get("/api/v1/reports/no_such_report", params=PARAMS)).status_code == 422
    assert (
        await hr.get("/api/v1/reports/daily", params={"date_from": "2026-09-30", "date_to": "2026-09-01"})
    ).status_code == 422
    operator = await make_api(await make_user(db, UserRole.OPERATOR, "op"))
    assert (await operator.get("/api/v1/reports/daily", params=PARAMS)).status_code == 403


async def test_fr31_export_runs_as_a_job_and_only_its_owner_downloads(
    make_api,
    db: AsyncSession,
    no_celery: list[tuple[str, tuple[Any, ...]]],  # type: ignore[no-untyped-def]
) -> None:
    await _seed(db)
    hr_user = await make_user(db, UserRole.HR_ADMIN, "hr")
    hr = await make_api(hr_user)
    response = await hr.get("/api/v1/reports/daily", params={**PARAMS, "format": "xlsx"})
    assert response.status_code == 202
    job_id = response.json()["data"]["job_id"]
    name, args = no_celery[-1]
    assert name.endswith("export_report") and args[1:4] == (
        "daily",
        {**PARAMS, "department_id": None, "employee_id": None, "status": None},
        "xlsx",
    )
    audit = (await db.scalars(select(AuditLog).where(AuditLog.action == "report.export"))).one()
    assert audit.new_values["format"] == "xlsx"

    await asyncio.to_thread(export_report, *args)  # what the worker does (tasks run outside the event loop)
    job = (await hr.get(f"/api/v1/jobs/{job_id}")).json()["data"]
    assert job["status"] == "succeeded" and job["file_available"] and job["message"] == "1 rows"
    download = await hr.get(f"/api/v1/jobs/{job_id}/file")
    assert download.status_code == 200 and download.content.startswith(b"PK")  # xlsx is a zip
    assert "facetrack-daily-20260901-20260930.xlsx" in download.headers["content-disposition"]
    other = await make_api(await make_user(db, UserRole.HR_ADMIN, "hr2"))
    assert (await other.get(f"/api/v1/jobs/{job_id}/file")).status_code == 404


async def test_export_uses_the_requesting_users_scope(
    make_api,
    db: AsyncSession,
    no_celery: list[tuple[str, tuple[Any, ...]]],  # type: ignore[no-untyped-def]
) -> None:
    data = await _seed(db)
    other = await make_employee(
        db, data["org"], "F1", department="finance", created_at=datetime(2026, 8, 1, tzinfo=UTC)
    )
    employee_user = await make_user(db, UserRole.EMPLOYEE, "f1u", employee_id=other.id)
    api = await make_api(employee_user)
    response = await api.get("/api/v1/reports/daily", params={**PARAMS, "format": "pdf"})
    assert response.status_code == 202
    await asyncio.to_thread(export_report, *no_celery[-1][1])
    job = (await api.get(f"/api/v1/jobs/{response.json()['data']['job_id']}")).json()["data"]
    assert job["status"] == "succeeded" and job["message"] == "0 rows"  # S1's day is not theirs


SHEET = {
    "title": "Event log",
    "file_name": "events-2026-10-04.xlsx",
    "columns": ["Time", "Status"],
    "rows": [
        [{"value": "17:03"}, {"value": "Recognised", "tone": "ok"}],
        [{"value": "17:04"}, {"value": "Unknown", "tone": "warn"}],
    ],
}


async def test_list_export_returns_a_coloured_xlsx_and_is_audited(make_api, db: AsyncSession) -> None:  # type: ignore[no-untyped-def]
    await make_org(db)
    operator = await make_api(await make_user(db, UserRole.OPERATOR, "op"))
    response = await operator.post("/api/v1/reports/sheet", json=SHEET)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert 'filename="events-2026-10-04.xlsx"' in response.headers["content-disposition"]
    assert response.content[:2] == b"PK"
    entry = (await db.scalars(select(AuditLog).where(AuditLog.action == "list.export"))).one()
    assert entry.new_values == {"title": "Event log", "rows": 2}


async def test_list_export_rejects_bad_input_and_anonymous_users(make_api, db: AsyncSession) -> None:  # type: ignore[no-untyped-def]
    await make_org(db)
    user = await make_api(await make_user(db, UserRole.HR_ADMIN, "hr"))
    ragged = {**SHEET, "rows": [[{"value": "only one cell"}]]}
    assert (await user.post("/api/v1/reports/sheet", json=ragged)).status_code == 422
    bad_tone = {**SHEET, "rows": [[{"value": "a"}, {"value": "b", "tone": "pink"}]]}
    assert (await user.post("/api/v1/reports/sheet", json=bad_tone)).status_code == 422
    bad_name = {**SHEET, "file_name": "../../etc/passwd"}
    assert (await user.post("/api/v1/reports/sheet", json=bad_name)).status_code == 422
    anonymous = await make_api()
    assert (await anonymous.post("/api/v1/reports/sheet", json=SHEET)).status_code == 401
