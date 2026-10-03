"""Event -> attendance flow (FR-16, FR-17, FR-20, FR-23, FR-27, FR-28) against a real database."""

import base64
import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from conftest import make_camera, make_employee, make_org, make_user
from facetrack_common.constants import (
    CRYPTO_PURPOSE_EMBEDDING,
    AttendanceStatus,
    CameraRole,
    EmployeeStatus,
    RecognitionStatus,
    ReviewStatus,
    UserRole,
)
from facetrack_common.events import RecognitionEvent
from facetrack_common.models import AttendanceDay, Holiday, Leave, RecognitionEventRecord, UnknownFace
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import get_cipher
from app.domain.attendance import service as attendance_service
from app.domain.recognition import service as recognition

PKT = ZoneInfo("Asia/Karachi")
MONDAY = datetime(2026, 10, 5, tzinfo=PKT).date()


def at(hour: int, minute: int = 0, day: int = 0) -> datetime:
    return datetime(2026, 10, 5 + day, hour, minute, tzinfo=PKT)


def event(camera_id: int, when: datetime, code: str | None = "E1", **extra: object) -> RecognitionEvent:
    return RecognitionEvent.model_validate(
        {
            "event_id": str(uuid.uuid4()),
            "camera_id": camera_id,
            "employee_code": code,
            "status": "recognized" if code else "unknown",
            "confidence": 0.71,
            "track_id": 1,
            "captured_at": when.astimezone(UTC).isoformat(),
            "snapshot_path": None,
            "model_name": "sface",
            "engine_node": "node-1",
            **extra,
        }
    )


@pytest.fixture
async def setup(db: AsyncSession) -> dict[str, object]:
    org = await make_org(db)
    employee = await make_employee(db, org, "E1", created_at=datetime(2026, 1, 1, tzinfo=UTC))
    entry = await make_camera(db, org, "Entrance", CameraRole.ENTRY)
    exit_ = await make_camera(db, org, "Exit", CameraRole.EXIT)
    general = await make_camera(db, org, "Floor 2", CameraRole.GENERAL)
    return {"org": org, "employee": employee, "entry": entry, "exit": exit_, "general": general}


async def _day(db: AsyncSession, employee_id: int, work_date=MONDAY):  # type: ignore[no-untyped-def]
    stmt = (
        select(AttendanceDay)
        .where(AttendanceDay.employee_id == employee_id, AttendanceDay.work_date == work_date)
        .execution_options(populate_existing=True)
    )
    return (await db.scalars(stmt)).first()


async def test_fr20_entry_then_exit_gives_check_in_and_check_out(db: AsyncSession, setup: dict) -> None:  # type: ignore[type-arg]
    await recognition.process_event(db, event(setup["entry"].id, at(9, 5)))
    day = await _day(db, setup["employee"].id)
    assert day is not None and day.status == AttendanceStatus.PRESENT and day.check_out_at is None
    await recognition.process_event(db, event(setup["exit"].id, at(18, 10)))
    day = await _day(db, setup["employee"].id)
    assert day.check_in_at == at(9, 5) and day.check_out_at == at(18, 10)
    assert day.worked_minutes == 545 and day.finalized_at is None


async def test_fr22_late_status_is_visible_live(db: AsyncSession, setup: dict) -> None:  # type: ignore[type-arg]
    await recognition.process_event(db, event(setup["entry"].id, at(9, 40)))
    day = await _day(db, setup["employee"].id)
    assert day.status == AttendanceStatus.LATE and day.late_minutes == 25


async def test_nfr7_duplicate_delivery_is_idempotent(db: AsyncSession, setup: dict) -> None:  # type: ignore[type-arg]
    original = event(setup["entry"].id, at(9, 5))
    first = await recognition.process_event(db, original)
    again = await recognition.process_event(db, original)
    assert first.stored and not again.stored
    count = await db.scalar(select(func.count()).select_from(RecognitionEventRecord))
    assert count == 1


async def test_nfr7_out_of_order_replay_gives_same_day(db: AsyncSession, setup: dict) -> None:  # type: ignore[type-arg]
    await recognition.process_event(db, event(setup["exit"].id, at(18, 10)))
    await recognition.process_event(db, event(setup["entry"].id, at(9, 5)))
    day = await _day(db, setup["employee"].id)
    assert day.check_in_at == at(9, 5) and day.check_out_at == at(18, 10)


async def test_fr17_unknown_event_creates_review_item_with_encrypted_embedding(
    db: AsyncSession, setup: dict
) -> None:  # type: ignore[type-arg]
    import numpy as np

    token = get_cipher().encrypt_embedding(np.ones(128, dtype=np.float32), CRYPTO_PURPOSE_EMBEDDING)
    unknown = event(
        setup["entry"].id, at(9, 5), code=None, embedding_encrypted=base64.b64encode(token).decode()
    )
    outcome = await recognition.process_event(db, unknown)
    face = (await db.scalars(select(UnknownFace))).one()
    assert outcome.stored and outcome.attendance is None
    assert face.review_status == ReviewStatus.PENDING and face.embedding_dim == 128
    assert face.embedding_encrypted == token  # stored as ciphertext (ADR-0001)


async def test_unknown_employee_code_is_rejected_for_dead_lettering(db: AsyncSession, setup: dict) -> None:  # type: ignore[type-arg]
    with pytest.raises(recognition.InvalidEvent):
        await recognition.process_event(db, event(setup["entry"].id, at(9, 5), code="NOPE"))
    with pytest.raises(recognition.InvalidEvent):
        await recognition.process_event(db, event(9999, at(9, 5)))


async def test_fr13_inactive_employee_events_do_not_mark_attendance(db: AsyncSession, setup: dict) -> None:  # type: ignore[type-arg]
    setup["employee"].status = EmployeeStatus.INACTIVE
    await db.commit()
    outcome = await recognition.process_event(db, event(setup["entry"].id, at(9, 5)))
    assert outcome.stored and outcome.attendance is None
    assert await _day(db, setup["employee"].id) is None


async def test_fr28_void_rebuilds_the_day_without_the_event(db: AsyncSession, setup: dict) -> None:  # type: ignore[type-arg]
    hr = await make_user(db, UserRole.HR_ADMIN, "hr1")
    wrong = await recognition.process_event(db, event(setup["entry"].id, at(8, 30)))
    await recognition.process_event(db, event(setup["entry"].id, at(9, 5)))
    assert (await _day(db, setup["employee"].id)).check_in_at == at(8, 30)
    voided = await recognition.void_event(db, wrong.event_id, "someone else", hr)
    assert voided.status == RecognitionStatus.VOIDED and voided.void_reason == "someone else"
    assert (await _day(db, setup["employee"].id)).check_in_at == at(9, 5)


async def test_fr27_assigning_an_unknown_face_counts_for_attendance(db: AsyncSession, setup: dict) -> None:  # type: ignore[type-arg]
    hr = await make_user(db, UserRole.HR_ADMIN, "hr1")
    await recognition.process_event(db, event(setup["entry"].id, at(9, 2), code=None))
    face = (await db.scalars(select(UnknownFace))).one()
    result, updated, added, _ = await recognition.assign_unknown(db, face.id, setup["employee"].id, False, hr)
    assert result.review_status == ReviewStatus.ASSIGNED and updated and not added
    day = await _day(db, setup["employee"].id)
    assert day.check_in_at == at(9, 2)
    with pytest.raises(Exception, match="already been reviewed"):
        await recognition.assign_unknown(db, face.id, setup["employee"].id, False, hr)


async def test_fr21_night_shift_check_out_after_midnight_lands_on_start_date(db: AsyncSession) -> None:
    org = await make_org(db)
    employee = await make_employee(db, org, "N1", shift="night")
    entry = await make_camera(db, org, "Entrance", CameraRole.ENTRY)
    exit_ = await make_camera(db, org, "Exit", CameraRole.EXIT)
    await recognition.process_event(db, event(entry.id, at(22, 5), code="N1"))
    await recognition.process_event(db, event(exit_.id, at(6, 10, day=1), code="N1"))
    day = await _day(db, employee.id, MONDAY)
    assert day is not None and day.check_out_at == at(6, 10, day=1) and day.worked_minutes == 485
    assert await _day(db, employee.id, MONDAY + timedelta(days=1)) is None


async def test_fr23_day_close_finalises_absent_missing_checkout_leave_holiday(db: AsyncSession) -> None:
    org = await make_org(db)
    created = datetime(2026, 1, 1, tzinfo=UTC)
    present = await make_employee(db, org, "P1", created_at=created)
    missing = await make_employee(db, org, "M1", created_at=created)
    absent = await make_employee(db, org, "A1", created_at=created)
    on_leave = await make_employee(db, org, "L1", created_at=created)
    entry = await make_camera(db, org, "Entrance", CameraRole.ENTRY)
    exit_ = await make_camera(db, org, "Exit", CameraRole.EXIT)
    db.add(Leave(employee_id=on_leave.id, from_date=MONDAY, to_date=MONDAY, type="annual", source="manual"))
    await db.commit()
    await recognition.process_event(db, event(entry.id, at(9), code="P1"))
    await recognition.process_event(db, event(exit_.id, at(18), code="P1"))
    await recognition.process_event(db, event(entry.id, at(9), code="M1"))

    before_close = at(1, 59, day=1).astimezone(UTC)
    assert await attendance_service.close_due_days(db, now=before_close, lookback_days=0) == 0
    after_close = at(2, 1, day=1).astimezone(UTC)
    finalised = await attendance_service.close_due_days(db, now=after_close, lookback_days=1)
    statuses = {e.employee_code: (await _day(db, e.id)).status for e in (present, missing, absent, on_leave)}
    assert statuses == {
        "P1": AttendanceStatus.PRESENT,
        "M1": AttendanceStatus.MISSING_CHECKOUT,
        "A1": AttendanceStatus.ABSENT,
        "L1": AttendanceStatus.ON_LEAVE,
    }
    assert finalised >= 4
    # Idempotent: a second run changes nothing.
    assert await attendance_service.close_due_days(db, now=after_close, lookback_days=1) == 0
    assert {
        e.employee_code: (await _day(db, e.id)).status for e in (present, missing, absent, on_leave)
    } == statuses


async def test_fr21_holiday_and_weekly_off_at_day_close(db: AsyncSession) -> None:
    org = await make_org(db)
    employee = await make_employee(db, org, "H1", created_at=datetime(2026, 1, 1, tzinfo=UTC))
    db.add(Holiday(location_id=org["location"].id, date=MONDAY, name="Holiday"))
    await db.commit()
    # At 03:00 the previous day is closable (day close 02:00), the current one is not yet.
    await attendance_service.close_due_days(db, now=at(3, 0, day=1).astimezone(UTC), lookback_days=1)
    await attendance_service.close_due_days(db, now=at(3, 0, day=6).astimezone(UTC), lookback_days=1)
    assert (await _day(db, employee.id)).status == AttendanceStatus.HOLIDAY
    saturday = MONDAY + timedelta(days=5)
    assert (await _day(db, employee.id, saturday)).status == AttendanceStatus.WEEKLY_OFF


async def test_late_event_after_close_updates_the_finalised_day(db: AsyncSession, setup: dict) -> None:  # type: ignore[type-arg]
    await attendance_service.close_due_days(db, now=at(3, 0, day=1).astimezone(UTC), lookback_days=1)
    assert (await _day(db, setup["employee"].id)).status == AttendanceStatus.ABSENT
    await recognition.process_event(db, event(setup["entry"].id, at(9, 0)))  # replayed after an outage
    day = await _day(db, setup["employee"].id)
    assert day.status == AttendanceStatus.MISSING_CHECKOUT and day.finalized_at is not None
