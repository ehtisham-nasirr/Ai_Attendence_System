"""Payroll API keys and pull API (FR-34, FR-35; §12 `/integration/attendance`)."""

from datetime import UTC, date, datetime
from typing import Any

import pytest
from conftest import make_employee, make_org, make_user
from facetrack_common.constants import AttendanceStatus, UserRole
from facetrack_common.models import ApiClient, AttendanceDay, AuditLog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings


async def _days(db: AsyncSession) -> None:
    org = await make_org(db)
    employee = await make_employee(db, org, "S1", created_at=datetime(2026, 8, 1, tzinfo=UTC))
    employee.hr_external_id = "HR-77"
    for day, finalized in ((1, True), (2, False)):
        db.add(
            AttendanceDay(
                employee_id=employee.id,
                work_date=date(2026, 9, day),
                status=AttendanceStatus.PRESENT,
                check_in_at=datetime(2026, 9, day, 4, 0, tzinfo=UTC),
                worked_minutes=500,
                late_minutes=0,
                early_minutes=0,
                overtime_minutes=12,
                is_manual=False,
                finalized_at=datetime(2026, 9, day, 21, tzinfo=UTC) if finalized else None,
            )
        )
    await db.commit()


async def _key(make_api, db: AsyncSession) -> tuple[Any, str, int]:  # type: ignore[no-untyped-def]
    admin = await make_api(await make_user(db, UserRole.SUPER_ADMIN, "admin"))
    created = await admin.post("/api/v1/api-clients", json={"name": "Payroll"})
    assert created.status_code == 201
    data = created.json()["data"]
    return admin, data["api_key"], data["client"]["id"]


async def test_fr34_api_key_is_shown_once_and_stored_as_a_hash(make_api, db: AsyncSession) -> None:  # type: ignore[no-untyped-def]
    admin, key, client_id = await _key(make_api, db)
    assert key.startswith("ft_")
    stored = await db.get(ApiClient, client_id)
    assert stored is not None and key not in stored.key_hash and stored.scopes == ["attendance:read"]
    listing = (await admin.get("/api/v1/api-clients")).json()["data"]
    assert "api_key" not in listing[0] and listing[0]["key_prefix"] == stored.key_prefix
    audit = (await db.scalars(select(AuditLog).where(AuditLog.action == "api_client.create"))).one()
    assert key not in str(audit.new_values)
    hr = await make_api(await make_user(db, UserRole.HR_ADMIN, "hr"))
    assert (await hr.post("/api/v1/api-clients", json={"name": "x"})).status_code == 403


async def test_fr35_pull_returns_only_finalised_days(make_api, db: AsyncSession) -> None:  # type: ignore[no-untyped-def]
    await _days(db)
    _, key, client_id = await _key(make_api, db)
    payroll = await make_api()
    response = await payroll.get(
        "/api/v1/integration/attendance", params={"date": "2026-09-01"}, headers={"X-API-Key": key}
    )
    assert response.status_code == 200
    row = response.json()["data"][0]
    assert row["employee_code"] == "S1" and row["hr_external_id"] == "HR-77" and row["overtime_minutes"] == 12
    assert row["status_letter"] == "P"
    not_closed = await payroll.get(
        "/api/v1/integration/attendance", params={"date": "2026-09-02"}, headers={"X-API-Key": key}
    )
    assert not_closed.json()["data"] == []
    stored = await db.get(ApiClient, client_id, populate_existing=True)
    assert stored is not None and stored.last_used_at is not None


async def test_pull_rejects_missing_wrong_and_revoked_keys(make_api, db: AsyncSession) -> None:  # type: ignore[no-untyped-def]
    admin, key, client_id = await _key(make_api, db)
    payroll = await make_api()
    url, params = "/api/v1/integration/attendance", {"date": "2026-09-01"}
    assert (await payroll.get(url, params=params)).status_code == 401
    assert (await payroll.get(url, params=params, headers={"X-API-Key": key[:-2] + "xx"})).status_code == 401
    # A portal session is not an API key.
    assert (await admin.get(url, params=params)).status_code == 401
    assert (await admin.delete(f"/api/v1/api-clients/{client_id}")).status_code == 204
    assert (await payroll.get(url, params=params, headers={"X-API-Key": key})).status_code == 401


async def test_api_key_rate_limit(make_api, db: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    _, key, _ = await _key(make_api, db)
    monkeypatch.setattr(get_settings(), "api_key_rate_limit_per_minute", 2)
    payroll = await make_api()
    codes = [
        (
            await payroll.get(
                "/api/v1/integration/attendance", params={"date": "2026-09-01"}, headers={"X-API-Key": key}
            )
        ).status_code
        for _ in range(3)
    ]
    assert codes == [200, 200, 429]


async def test_manual_push_and_sync_are_admin_actions(
    make_api,
    db: AsyncSession,
    no_celery: list[tuple[str, tuple[Any, ...]]],  # type: ignore[no-untyped-def]
) -> None:
    admin = await make_api(await make_user(db, UserRole.SUPER_ADMIN, "admin"))
    assert (
        await admin.post("/api/v1/integration/payroll/push", params={"date": "2026-09-01"})
    ).status_code == 202
    assert (await admin.post("/api/v1/integration/hr/sync")).status_code == 202
    assert [n.rsplit(".", 1)[1] for n, _ in no_celery] == ["push_payroll", "sync_hr"]
    assert no_celery[0][1] == ("2026-09-01",)
    hr = await make_api(await make_user(db, UserRole.HR_ADMIN, "hr"))
    assert (await hr.post("/api/v1/integration/hr/sync")).status_code == 403
