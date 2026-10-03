"""Scheduled emails (FR-32), check-in confirmation (FR-33) and AD sign-in against an LDAP mock (FR-40)."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from conftest import PASSWORD, make_camera, make_employee, make_org, make_user
from facetrack_common.constants import CameraRole, UserRole
from facetrack_common.events import RecognitionEvent
from facetrack_common.models import Department, Setting
from facetrack_common.settings_keys import ReportSchedule
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.redis import get_async_redis
from app.domain.notifications import service as notifications
from app.domain.recognition import service as recognition
from app.services import directory, email
from app.worker.tasks import notifications as tasks

PKT = ZoneInfo("Asia/Karachi")


def _schedule(frequency: str) -> ReportSchedule:
    return ReportSchedule.model_validate(
        {"report_type": "daily", "frequency": frequency, "time": "07:00", "recipients": ["hr@example.com"]}
    )


def test_fr32_schedule_periods() -> None:
    monday = datetime(2026, 10, 5, 7, 30, tzinfo=PKT)
    daily = notifications.due_period(_schedule("daily"), monday)
    assert daily is not None and (daily.date_from, daily.date_to) == (monday.date() - timedelta(days=1),) * 2
    weekly = notifications.due_period(_schedule("weekly"), monday)
    assert weekly is not None and (str(weekly.date_from), str(weekly.date_to)) == ("2026-09-28", "2026-10-04")
    assert notifications.due_period(_schedule("weekly"), monday + timedelta(days=1)) is None
    first = datetime(2026, 10, 1, 8, 0, tzinfo=PKT)
    monthly = notifications.due_period(_schedule("monthly"), first)
    assert monthly is not None and (str(monthly.date_from), str(monthly.date_to)) == (
        "2026-09-01",
        "2026-09-30",
    )
    assert notifications.due_period(_schedule("daily"), monday.replace(hour=6)) is None  # before 07:00


async def test_fr32_due_emails_are_queued_once(
    db: AsyncSession, sent_tasks: list[tuple[str, tuple[Any, ...]]]
) -> None:
    db.add_all(
        [
            Setting(key="notifications.daily_summary_enabled", value=True),
            Setting(key="notifications.daily_summary_time", value="00:00"),
            Setting(
                key="notifications.report_schedules",
                value=[
                    {
                        "report_type": "daily",
                        "frequency": "daily",
                        "time": "00:00",
                        "recipients": ["hr@example.com"],
                    }
                ],
            ),
        ]
    )
    await db.commit()
    first = await asyncio.to_thread(tasks.run_due_notifications.run)
    assert first[0] == "daily_summary" and len(first) == 2
    assert await asyncio.to_thread(tasks.run_due_notifications.run) == []
    names = sorted(name.rsplit(".", 1)[1] for name, _ in sent_tasks)
    assert names == ["send_daily_summary", "send_scheduled_report"]


async def test_fr32_daily_summary_goes_to_hr_and_each_manager(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    org = await make_org(db)
    await make_employee(db, org, "S1")
    manager = await make_user(db, UserRole.DEPARTMENT_MANAGER, "mgr")
    department = await db.get(Department, org["sales"].id)
    assert department is not None
    department.manager_user_id = manager.id
    db.add(Setting(key="notifications.hr_emails", value=["hr@example.com"]))
    await db.commit()
    outbox: list[tuple[list[str], str, str]] = []
    monkeypatch.setattr(
        email,
        "send_email",
        lambda to, subject, text, attachments=None: outbox.append((to, subject, text)) or True,
    )
    # The task runs on the worker's own event loop: give it its own async Redis client (as a worker has).
    get_async_redis.cache_clear()
    try:
        assert await asyncio.to_thread(tasks.send_daily_summary.run) == 2
    finally:
        get_async_redis.cache_clear()
    # Whole organisation for HR (today may be a weekly off, so only the shape is checked).
    assert outbox[0][0] == ["hr@example.com"] and "Expected:" in outbox[0][2] and "Sales:" in outbox[0][2]
    assert outbox[1][0] == [manager.email] and "your departments" in outbox[1][2]


async def test_fr32_scheduled_report_is_emailed_with_attachment(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await make_employee(db, await make_org(db), "S1")
    outbox: list[Any] = []
    monkeypatch.setattr(
        email,
        "send_email",
        lambda to, subject, text, attachments=None: outbox.append((to, subject, attachments)) or True,
    )
    schedule = {
        "report_type": "absentee",
        "frequency": "daily",
        "time": "07:00",
        "recipients": ["hr@example.com"],
        "format": "pdf",
    }
    assert await asyncio.to_thread(tasks.send_scheduled_report.run, schedule, "2026-09-01", "2026-09-01")
    to, subject, attachments = outbox[0]
    assert to == ["hr@example.com"] and subject == "FaceTrack Absentee report 01 Sep 2026"
    assert attachments[0][0].endswith(".pdf") and attachments[0][1].startswith(b"%PDF")


async def test_fr33_checkin_confirmation_once_per_day(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    org = await make_org(db)
    employee = await make_employee(db, org, "S1")
    employee.email = "s1@example.com"
    camera = await make_camera(db, org, "Main entrance", CameraRole.ENTRY)
    db.add(Setting(key="notifications.checkin_confirmation", value=True))
    await db.commit()
    now = datetime.now(UTC)
    outcome = await recognition.process_event(
        db,
        RecognitionEvent.model_validate(
            {
                "event_id": str(uuid.uuid4()),
                "camera_id": camera.id,
                "employee_code": "S1",
                "status": "recognized",
                "confidence": 0.7,
                "track_id": 1,
                "captured_at": now.isoformat(),
                "model_name": "sface",
                "engine_node": "node-1",
            }
        ),
    )
    assert outcome.checkin_text == f"{now.astimezone(PKT):%H:%M} at Main entrance"
    outbox: list[Any] = []
    monkeypatch.setattr(
        email, "send_email", lambda to, subject, text, attachments=None: outbox.append((to, text)) or True
    )
    work_date = outcome.attendance.work_date.isoformat() if outcome.attendance else ""
    assert await asyncio.to_thread(tasks.confirm_checkin.run, employee.id, work_date, outcome.checkin_text)
    assert not await asyncio.to_thread(
        tasks.confirm_checkin.run, employee.id, work_date, outcome.checkin_text
    )
    assert outbox == [(["s1@example.com"], outbox[0][1])] and "Main entrance" in outbox[0][1]


async def test_old_replayed_events_do_not_notify(db: AsyncSession) -> None:
    org = await make_org(db)
    await make_employee(db, org, "S1")
    camera = await make_camera(db, org, "Main entrance", CameraRole.ENTRY)
    outcome = await recognition.process_event(
        db,
        RecognitionEvent.model_validate(
            {
                "event_id": str(uuid.uuid4()),
                "camera_id": camera.id,
                "employee_code": "S1",
                "status": "recognized",
                "confidence": 0.7,
                "track_id": 1,
                "captured_at": (datetime.now(UTC) - timedelta(hours=3)).isoformat(),
                "model_name": "sface",
                "engine_node": "node-1",
            }
        ),
    )
    assert outcome.stored and outcome.checkin_text is None


@pytest.fixture
def fake_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    """ldap3's in-memory MOCK_SYNC server with a service account and one user."""
    from ldap3 import MOCK_SYNC, OFFLINE_AD_2012_R2, Connection, Server

    settings = get_settings()
    monkeypatch.setattr(settings, "ldap_server_uri", "ldap://ad.example.local")
    monkeypatch.setattr(settings, "ldap_bind_dn", "cn=svc,dc=example,dc=local")
    monkeypatch.setattr(settings, "ldap_bind_password", __import__("pydantic").SecretStr("svc-pass"))
    monkeypatch.setattr(settings, "ldap_base_dn", "dc=example,dc=local")
    server = Server("ad.example.local", get_info=OFFLINE_AD_2012_R2)
    seed = Connection(server, client_strategy=MOCK_SYNC)
    seed.strategy.add_entry(
        "cn=svc,dc=example,dc=local", {"userPassword": "svc-pass", "sAMAccountName": "svc"}
    )
    seed.strategy.add_entry(
        "cn=Ali Khan,ou=staff,dc=example,dc=local",
        {"userPassword": PASSWORD, "sAMAccountName": "ali", "objectClass": "person"},
    )

    def connect(_: Any, user: str, password: str) -> Any:
        # Same Server object as `seed`, so the same in-memory directory.
        connection = Connection(server, user, password, client_strategy=MOCK_SYNC)
        connection.bind()
        if not connection.bound:
            from ldap3.core.exceptions import LDAPBindError

            raise LDAPBindError("invalid credentials")
        return connection

    monkeypatch.setattr(directory, "_server", lambda uri: server)
    monkeypatch.setattr(directory, "_connect", connect)


@pytest.mark.usefixtures("fake_directory")
async def test_fr40_directory_sign_in() -> None:
    assert await directory.verify_credentials("ali", PASSWORD)
    assert not await directory.verify_credentials("ali", "wrong-password")
    assert not await directory.verify_credentials("nobody", PASSWORD)
    assert not await directory.verify_credentials(
        "*)(sAMAccountName=*", PASSWORD
    )  # filter injection is escaped
    assert not await directory.verify_credentials("ali", "")
