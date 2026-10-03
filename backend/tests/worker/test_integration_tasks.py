"""Payroll push (FR-35, §12 webhook) and HR sync (FR-12, FR-24) as the worker runs them."""

import asyncio
import json
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
import pytest
from celery.exceptions import Retry
from conftest import make_employee, make_org
from facetrack_common.constants import AttendanceStatus, EmployeeStatus, LeaveSource
from facetrack_common.models import AttendanceDay, Employee, Leave, Setting
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.redis import get_sync_redis
from app.domain.integration import payroll
from app.services import hr_client
from app.worker.tasks import integration

SECRET = "test-webhook-secret"


@pytest.fixture
def webhook(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Captures deliveries instead of calling a real payroll system."""
    received: list[dict[str, Any]] = []

    def post(url: str, content: bytes, headers: dict[str, str], timeout: float) -> httpx.Response:
        received.append({"url": url, "body": content, "headers": headers})
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setattr(integration.httpx, "post", post)
    monkeypatch.setattr(get_settings(), "payroll_webhook_secret", __import__("pydantic").SecretStr(SECRET))
    return received


async def _configure_push(db: AsyncSession) -> None:
    db.add_all(
        [
            Setting(key="integration.payroll_mode", value="push"),
            Setting(key="integration.payroll_webhook_url", value="https://payroll.example.com/hook"),
        ]
    )
    await db.commit()


async def _finalised_day(
    db: AsyncSession, employee: Employee, day: int, minutes_ago: int = 30
) -> AttendanceDay:
    record = AttendanceDay(
        employee_id=employee.id,
        work_date=date(2026, 9, day),
        status=AttendanceStatus.PRESENT,
        worked_minutes=480,
        late_minutes=0,
        early_minutes=0,
        overtime_minutes=0,
        is_manual=False,
        finalized_at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
    )
    db.add(record)
    await db.commit()
    await db.execute(
        update(AttendanceDay)
        .where(AttendanceDay.id == record.id)
        .values(updated_at=datetime.now(UTC) - timedelta(minutes=minutes_ago))
    )
    await db.commit()
    return record


async def test_fr35_push_is_signed_and_sends_each_change_once(
    db: AsyncSession, webhook: list[dict[str, Any]]
) -> None:
    await _configure_push(db)
    org = await make_org(db)
    employee = await make_employee(db, org, "S1")
    get_sync_redis().set(integration.WATERMARK_KEY, (datetime.now(UTC) - timedelta(hours=2)).isoformat())
    await _finalised_day(db, employee, 1)

    result = await asyncio.to_thread(integration.push_payroll.run)
    assert result["sent"] == 1
    delivery = webhook[0]
    assert payroll.verify(delivery["body"], delivery["headers"][payroll.SIGNATURE_HEADER], SECRET)
    assert not payroll.verify(delivery["body"] + b" ", delivery["headers"][payroll.SIGNATURE_HEADER], SECRET)
    payload = json.loads(delivery["body"])
    assert payload["event"] == "attendance.finalized" and payload["days"][0]["employee_code"] == "S1"
    assert delivery["headers"][payroll.DELIVERY_HEADER] == payload["delivery_id"]

    # Nothing changed: nothing is sent again.
    assert (await asyncio.to_thread(integration.push_payroll.run)) == {"sent": 0}
    # A later correction of a closed day is sent on the next push.
    await _finalised_day(db, employee, 2, minutes_ago=5)
    assert (await asyncio.to_thread(integration.push_payroll.run))["sent"] == 1


async def test_push_retries_five_times_then_alerts(
    db: AsyncSession,
    webhook: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    sent_tasks: list[tuple[str, tuple[Any, ...]]],
) -> None:
    await _configure_push(db)
    employee = await make_employee(db, await make_org(db), "S1")
    await _finalised_day(db, employee, 1)

    def down(*_: Any, **__: Any) -> httpx.Response:
        raise httpx.ConnectError("payroll down")

    monkeypatch.setattr(integration.httpx, "post", down)

    def attempt(retries: int) -> Any:
        # Celery's request context is per thread; with a task id the call behaves as in the worker.
        integration.push_payroll.push_request(id="delivery-1", retries=retries, called_directly=False)
        try:
            return integration.push_payroll.run()
        finally:
            integration.push_payroll.pop_request()

    with pytest.raises(Retry):
        await asyncio.to_thread(attempt, 0)
    assert any(name.endswith("push_payroll") for name, _ in sent_tasks)  # the next attempt was queued
    with pytest.raises(httpx.ConnectError):
        await asyncio.to_thread(attempt, integration.MAX_ATTEMPTS)
    assert any(name.endswith("send_alert") and args[0] == "Payroll push failed" for name, args in sent_tasks)
    assert get_sync_redis().get(integration.WATERMARK_KEY) is None  # failed deliveries do not move it


async def test_push_skips_when_not_configured(db: AsyncSession) -> None:
    assert (await asyncio.to_thread(integration.push_payroll.run)) == {"sent": 0, "skipped": "not configured"}


async def test_fr12_fr24_hr_sync_upserts_employees_and_leave(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    org = await make_org(db)
    existing = await make_employee(db, org, "S1", created_at=datetime(2026, 8, 1, tzinfo=UTC))
    today = datetime.now(UTC).date()
    closed = AttendanceDay(
        employee_id=existing.id,
        work_date=today - timedelta(days=3),
        status=AttendanceStatus.ABSENT,
        worked_minutes=0,
        late_minutes=0,
        early_minutes=0,
        overtime_minutes=0,
        is_manual=False,
        finalized_at=datetime.now(UTC),
    )
    stale = Leave(
        employee_id=existing.id,
        from_date=today - timedelta(days=10),
        to_date=today - timedelta(days=9),
        type="Annual",
        source=LeaveSource.HR,
        external_ref="L-OLD",
    )
    db.add_all([closed, stale, Setting(key="integration.hr_base_url", value="https://hr.example.com/api")])
    await db.commit()

    monkeypatch.setattr(
        hr_client,
        "fetch_employees",
        lambda base: [
            {
                "employee_code": "S1",
                "full_name": "Renamed Person",
                "department_code": "FIN",
                "status": "inactive",
            },
            {"employee_code": "N1", "full_name": "New Hire", "department_code": "SAL", "id": 501},
            {"employee_code": "X1", "full_name": "Bad Dept", "department_code": "NOPE"},
            {"full_name": "No code"},
        ],
    )
    monkeypatch.setattr(
        hr_client,
        "fetch_leaves",
        lambda base, a, b: [
            {
                "id": "L-1",
                "employee_code": "S1",
                "from_date": str(today - timedelta(days=3)),
                "to_date": str(today - timedelta(days=3)),
                "type": "Sick",
                "status": "approved",
            },
            {
                "id": "L-2",
                "employee_code": "S1",
                "from_date": str(today),
                "to_date": str(today),
                "status": "pending",
            },
        ],
    )
    report = await asyncio.to_thread(integration.sync_hr.run)
    assert (report["created"], report["updated"]) == (2, 1)  # N1 and X1 (without department) created
    assert report["leaves_added"] == 1 and report["leaves_removed"] == 1 and report["error_count"] == 2

    s1 = (
        await db.scalars(
            select(Employee).where(Employee.employee_code == "S1").execution_options(populate_existing=True)
        )
    ).one()
    assert s1.full_name == "Renamed Person" and s1.status == EmployeeStatus.INACTIVE
    assert s1.department_id == org["finance"].id
    n1 = (await db.scalars(select(Employee).where(Employee.employee_code == "N1"))).one()
    assert n1.hr_external_id == "501"
    await db.refresh(closed)
    assert closed.status == AttendanceStatus.ON_LEAVE  # recomputed after the HR leave arrived
    await db.refresh(stale)
    assert stale.deleted_at is not None


async def test_hr_sync_failure_alerts(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch, sent_tasks: list[tuple[str, tuple[Any, ...]]]
) -> None:
    db.add(Setting(key="integration.hr_base_url", value="https://hr.example.com/api"))
    await db.commit()

    def broken(base: str) -> list[dict[str, Any]]:
        raise hr_client.HrSystemError("HR system request failed: ConnectError")

    monkeypatch.setattr(hr_client, "fetch_employees", broken)
    assert "error" in await asyncio.to_thread(integration.sync_hr.run)
    assert any(name.endswith("send_alert") for name, _ in sent_tasks)


async def test_scheduler_runs_each_job_once_per_day(
    db: AsyncSession, sent_tasks: list[tuple[str, tuple[Any, ...]]]
) -> None:
    db.add_all(
        [
            Setting(key="integration.payroll_mode", value="push"),
            Setting(key="integration.payroll_push_time", value="00:00"),
            Setting(key="integration.hr_sync_enabled", value=True),
            Setting(key="integration.hr_sync_time", value="00:00"),
        ]
    )
    await db.commit()
    assert sorted(await asyncio.to_thread(integration.run_due_integrations.run)) == [
        "hr_sync",
        "payroll_push",
    ]
    assert await asyncio.to_thread(integration.run_due_integrations.run) == []
    assert sorted(n.rsplit(".", 1)[1] for n, _ in sent_tasks) == ["push_payroll", "sync_hr"]
