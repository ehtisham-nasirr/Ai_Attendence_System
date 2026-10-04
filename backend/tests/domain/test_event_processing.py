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
from app.domain.settings import service as settings_service

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


# --------------------------------------------------------------------------- duplicate photos (Q59, §10.3)


def _snapshot(when: datetime, tag: str) -> str:
    """Writes a synthetic (non-face) snapshot object and returns its engine-style name (§10.2)."""
    from app.services import storage

    name = f"snapshots/{when.astimezone(UTC):%Y/%m/%d}/{tag}-{uuid.uuid4()}.jpg"
    storage.put_encrypted(name, b"\xff\xd8synthetic")
    return name


def _stored(name: str) -> bool:
    from facetrack_common.storage import StorageError

    from app.services import storage

    try:
        storage.get_store().get(name)
    except StorageError:
        return False
    return True


async def _snapshot_paths(db: AsyncSession, employee_id: int) -> dict[datetime, str | None]:
    stmt = (
        select(RecognitionEventRecord)
        .where(RecognitionEventRecord.employee_id == employee_id)
        .execution_options(populate_existing=True)
    )
    return {e.captured_at: e.snapshot_path for e in (await db.scalars(stmt)).all()}


async def _send(db: AsyncSession, camera_id: int, when: datetime, code: str | None = "E1"):  # type: ignore[no-untyped-def]
    path = _snapshot(when, code or "unknown")
    return await recognition.process_event(db, event(camera_id, when, code=code, snapshot_path=path)), path


CLOSE_MONDAY = at(3, 0, day=1).astimezone(UTC)  # day close is 02:00 the next morning


async def test_fr23_q59_day_close_prunes_repeat_photos_but_keeps_counted_ones(
    db: AsyncSession, setup: dict
) -> None:  # type: ignore[type-arg]
    from facetrack_common.models import AuditLog

    plan = [
        ("entry", 9, 0),
        ("entry", 9, 2),
        ("entry", 9, 4),
        ("entry", 9, 6),
        ("exit", 18, 0),
        ("exit", 18, 3),
    ]
    sent = [await _send(db, setup[role].id, at(h, m)) for role, h, m in plan]
    live = recognition.live_messages(event(setup["entry"].id, at(9, 2), snapshot_path=sent[1][1]), sent[1][0])
    assert live[0][1]["snapshot_available"] is True  # nothing is pruned while the day is open
    assert all(p is not None for p in (await _snapshot_paths(db, setup["employee"].id)).values())

    await attendance_service.close_due_days(db, now=CLOSE_MONDAY, lookback_days=1)
    stored = await _snapshot_paths(db, setup["employee"].id)
    assert len(stored) == 6  # every event row is kept (audit trail)
    # 09:02 and 09:04 are inside the 5-minute window of the kept 09:00 photo; 09:06 is 6 minutes after
    # it. 18:03 repeats the counted 18:00 check-out. At most one photo per window per camera.
    keeps = [True, False, False, True, True, False]
    assert [stored[at(h, m)] is not None for _, h, m in plan] == keeps
    assert [_stored(path) for _, path in sent] == keeps
    day = await _day(db, setup["employee"].id)
    assert stored[day.check_in_at] and stored[day.check_out_at] and day.finalized_at is not None
    audit_entry = (await db.scalars(select(AuditLog).where(AuditLog.action == "retention.delete"))).one()
    assert audit_entry.new_values == {"duplicate_event_snapshots": 3}
    # Idempotent: the next run does not prune again.
    await attendance_service.close_due_days(db, now=CLOSE_MONDAY, lookback_days=1)
    assert await _snapshot_paths(db, setup["employee"].id) == stored


async def test_q59_counted_sighting_keeps_its_photo_inside_the_window(db: AsyncSession, setup: dict) -> None:  # type: ignore[type-arg]
    await _send(db, setup["entry"].id, at(9, 0))
    await recognition.process_event(db, event(setup["exit"].id, at(18, 0)))  # no snapshot from the engine
    _, repeat_path = await _send(db, setup["exit"].id, at(18, 3))
    last, last_path = await _send(db, setup["exit"].id, at(18, 6))
    await attendance_service.close_due_days(db, now=CLOSE_MONDAY, lookback_days=1)
    day = await _day(db, setup["employee"].id)
    # 18:06 is 3 minutes after the 18:03 photo, but it is the counted check-out (§10.3 repeats 18:00).
    assert day.check_out_event_id == last.event_id
    assert _stored(last_path) and _stored(repeat_path)


async def test_fr28_q59_void_before_close_keeps_the_new_check_in_photo(db: AsyncSession, setup: dict) -> None:  # type: ignore[type-arg]
    hr = await make_user(db, UserRole.HR_ADMIN, "hr1")
    (first, first_path), (second, second_path) = [
        await _send(db, setup["entry"].id, at(9, minute)) for minute in (0, 3)
    ]
    await recognition.void_event(db, first.event_id, "someone else", hr)  # a false accept (NFR-2)
    await attendance_service.close_due_days(db, now=CLOSE_MONDAY, lookback_days=1)
    day = await _day(db, setup["employee"].id)
    assert day.check_in_event_id == second.event_id
    assert _stored(second_path) and _stored(first_path)  # the voided mark keeps its evidence too


async def test_fr27_q59_assign_before_close_keeps_the_new_check_out_photo(
    db: AsyncSession, setup: dict
) -> None:  # type: ignore[type-arg]
    hr = await make_user(db, UserRole.HR_ADMIN, "hr1")
    await _send(db, setup["entry"].id, at(9, 0))
    _, unknown_path = await _send(db, setup["exit"].id, at(17, 59), code=None)
    _, kept_path = await _send(db, setup["exit"].id, at(18, 2))
    late, late_path = await _send(db, setup["exit"].id, at(18, 6))
    face = (await db.scalars(select(UnknownFace))).one()
    # 18:02 now repeats 17:59, so the counted check-out moves to 18:06 (§10.3 cooldown chain).
    await recognition.assign_unknown(db, face.id, setup["employee"].id, False, hr)
    await attendance_service.close_due_days(db, now=CLOSE_MONDAY, lookback_days=1)
    day = await _day(db, setup["employee"].id)
    assert day.check_out_event_id == late.event_id and _stored(late_path)
    # The assigned face shares its object with the unknown-face row: never pruned.
    assert _stored(unknown_path)
    assert not _stored(kept_path)  # 18:02 is a repeat of the 17:59 photo and is not counted


async def test_fr27_q59_assigned_face_inside_the_window_keeps_its_photo(
    db: AsyncSession, setup: dict
) -> None:  # type: ignore[type-arg]
    hr = await make_user(db, UserRole.HR_ADMIN, "hr1")
    await _send(db, setup["entry"].id, at(9, 0))
    _, unknown_path = await _send(db, setup["entry"].id, at(9, 2), code=None)
    face = (await db.scalars(select(UnknownFace))).one()
    await recognition.assign_unknown(db, face.id, setup["employee"].id, False, hr)
    await attendance_service.close_due_days(db, now=CLOSE_MONDAY, lookback_days=1)
    # The event shares its object with the unknown-face row (review screen, gallery): never pruned.
    assert _stored(unknown_path)


@pytest.mark.parametrize("shift", ["shift", "night"])
async def test_fr23_q59_photos_are_pruned_per_work_day(db: AsyncSession, setup: dict, shift: str) -> None:  # type: ignore[type-arg]
    employee = await make_employee(
        db, setup["org"], "N1", shift=shift, created_at=datetime(2026, 1, 1, tzinfo=UTC)
    )
    values = await settings_service.resolved(db)
    ctx = attendance_service.employee_context(employee, values)
    close = attendance_service.day_window(MONDAY, ctx)[1]
    (_, before_path), (after, after_path) = [
        await _send(db, setup["entry"].id, close + offset, code="N1")
        for offset in (timedelta(minutes=-2), timedelta(minutes=1))
    ]
    next_close = attendance_service.day_window(MONDAY + timedelta(days=1), ctx)[1]
    await attendance_service.close_due_days(db, now=next_close + timedelta(hours=1), lookback_days=3)
    # Three minutes apart on one camera, but on two work days: each is its day's check-in.
    next_day = await _day(db, employee.id, MONDAY + timedelta(days=1))
    assert next_day.check_in_event_id == after.event_id
    assert _stored(before_path) and _stored(after_path)


SEQUENCE = [("entry", 9, 0), ("entry", 9, 2), ("entry", 9, 4), ("exit", 18, 0), ("exit", 18, 3)]


async def _replay(db: AsyncSession, setup: dict, code: str, order: list[int], photos: bool) -> AttendanceDay:  # type: ignore[type-arg]
    employee = await make_employee(db, setup["org"], code, created_at=datetime(2026, 1, 1, tzinfo=UTC))
    for index in order:
        role, hour, minute = SEQUENCE[index]
        when = at(hour, minute)
        path = _snapshot(when, code) if photos else None
        await recognition.process_event(db, event(setup[role].id, when, code=code, snapshot_path=path))
    return await _day(db, employee.id)


async def test_nfr7_q59_pruning_is_the_same_in_any_arrival_order(db: AsyncSession, setup: dict) -> None:  # type: ignore[type-arg]
    def summary(day: AttendanceDay) -> tuple[object, ...]:
        return (day.check_in_at, day.check_out_at, day.status, day.worked_minutes, day.late_minutes)

    orders = {"B0": [0, 1, 2, 3, 4], "B1": [0, 1, 2, 3, 4], "B2": [4, 3, 2, 1, 0], "B3": [1, 2, 0, 4, 3]}
    days = {
        code: await _replay(db, setup, code, order, photos=code != "B0") for code, order in orders.items()
    }
    await attendance_service.close_due_days(db, now=CLOSE_MONDAY, lookback_days=1)
    closed = {code: await _day(db, day.employee_id) for code, day in days.items()}
    assert len({summary(day) for day in closed.values()}) == 1  # photos never change attendance
    assert closed["B0"].check_in_at == at(9, 0) and closed["B0"].check_out_at == at(18, 0)
    counts = await db.execute(
        select(RecognitionEventRecord.employee_id, func.count()).group_by(RecognitionEventRecord.employee_id)
    )
    assert sorted(n for _, n in counts.all()) == [5, 5, 5, 5]  # no event row is ever dropped
    for code in ("B1", "B2", "B3"):
        paths = await _snapshot_paths(db, closed[code].employee_id)
        assert [paths[at(h, m)] is not None for _, h, m in SEQUENCE] == [True, False, False, True, False]


async def test_q59_resent_photo_of_a_pruned_event_is_deleted(db: AsyncSession, setup: dict) -> None:  # type: ignore[type-arg]
    from app.services import storage

    kept_path = _snapshot(at(9, 0), "k")
    kept = event(setup["entry"].id, at(9, 0), snapshot_path=kept_path)
    await recognition.process_event(db, kept)
    pruned_path = _snapshot(at(9, 2), "p")
    pruned = event(setup["entry"].id, at(9, 2), snapshot_path=pruned_path)
    await recognition.process_event(db, pruned)
    await attendance_service.close_due_days(db, now=CLOSE_MONDAY, lookback_days=1)
    assert not _stored(pruned_path)
    # The engine delivers the same event again and writes its snapshot object again (buffer replay).
    storage.put_encrypted(pruned_path, b"\xff\xd8synthetic")
    again = await recognition.process_event(db, pruned)
    assert not again.stored and not _stored(pruned_path)
    # A duplicate delivery of an event that kept its photo leaves the photo alone.
    assert not (await recognition.process_event(db, kept)).stored and _stored(kept_path)
