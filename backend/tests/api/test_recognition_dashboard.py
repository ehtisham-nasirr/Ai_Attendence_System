"""Event log, void, unknown-face queue, snapshots, dashboard and live-feed scoping (FR-17, FR-27..FR-29)."""

import uuid
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import numpy as np
from conftest import make_camera, make_employee, make_org, make_user
from facetrack_common.constants import CRYPTO_PURPOSE_EMBEDDING, CRYPTO_PURPOSE_IMAGE, CameraRole, UserRole
from facetrack_common.events import RecognitionEvent
from facetrack_common.models import User
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import get_cipher
from app.core.security import DataScope
from app.domain.attendance import service as attendance_service
from app.domain.recognition import service as recognition
from app.services import storage
from app.ws.live import allowed

PKT = ZoneInfo("Asia/Karachi")


def _event(
    camera_id: int, code: str | None, snapshot: str | None = None, embedding: str | None = None
) -> RecognitionEvent:
    now = datetime.now(UTC).replace(microsecond=0)
    return RecognitionEvent.model_validate(
        {
            "event_id": str(uuid.uuid4()),
            "camera_id": camera_id,
            "employee_code": code,
            "status": "recognized" if code else "unknown",
            "confidence": 0.7,
            "track_id": 3,
            "captured_at": now.isoformat(),
            "snapshot_path": snapshot,
            "model_name": "sface",
            "engine_node": "node-1",
            "embedding_encrypted": embedding,
        }
    )


async def test_event_log_snapshot_and_void(make_api, db: AsyncSession) -> None:  # type: ignore[no-untyped-def]
    org = await make_org(db)
    await make_employee(db, org, "E1")
    camera = await make_camera(db, org, "Entrance", CameraRole.ENTRY)
    get_store = storage.get_store()
    get_store.put("snapshots/2026/10/05/x.jpg", get_cipher().encrypt(b"\xff\xd8jpeg", CRYPTO_PURPOSE_IMAGE))
    outcome = await recognition.process_event(
        db, _event(camera.id, "E1", snapshot="snapshots/2026/10/05/x.jpg")
    )
    hr = await make_api(await make_user(db, UserRole.HR_ADMIN, "hr"))
    events = (await hr.get("/api/v1/events")).json()
    assert events["data"][0]["employee_code"] == "E1" and events["data"][0]["snapshot_available"]
    snapshot = await hr.get(f"/api/v1/events/{outcome.event_id}/snapshot")
    assert snapshot.status_code == 200 and snapshot.content == b"\xff\xd8jpeg"
    void = await hr.post(f"/api/v1/events/{outcome.event_id}/void", json={"reason": "wrong person"})
    assert void.json()["data"]["status"] == "voided"
    assert (
        await hr.post(f"/api/v1/events/{outcome.event_id}/void", json={"reason": "again"})
    ).status_code == 409
    operator = await make_api(await make_user(db, UserRole.OPERATOR, "op"))
    assert (
        await operator.post(f"/api/v1/events/{outcome.event_id}/void", json={"reason": "nope"})
    ).status_code == 403
    manager = await make_api(await make_user(db, UserRole.DEPARTMENT_MANAGER, "mgr"))
    assert (
        await manager.get(f"/api/v1/events/{outcome.event_id}/snapshot")
    ).status_code == 404  # not their dept


async def test_fr17_fr27_unknown_queue_grouping_assign_and_dismiss(make_api, db: AsyncSession) -> None:  # type: ignore[no-untyped-def]
    org = await make_org(db)
    employee = await make_employee(db, org, "E1")
    camera = await make_camera(db, org, "Entrance", CameraRole.ENTRY)
    import base64

    same = np.ones(128, dtype=np.float32)
    other = np.zeros(128, dtype=np.float32)
    other[0] = 1.0
    for vector in (same, same, other):
        token = base64.b64encode(get_cipher().encrypt_embedding(vector, CRYPTO_PURPOSE_EMBEDDING)).decode()
        await recognition.process_event(db, _event(camera.id, None, embedding=token))
    operator = await make_api(await make_user(db, UserRole.OPERATOR, "op"))
    queue = (await operator.get("/api/v1/unknown-faces")).json()
    assert queue["pagination"]["total"] == 3
    groups = [f["group_id"] for f in sorted(queue["data"], key=lambda f: f["id"])]
    assert groups[0] == groups[1] != groups[2]
    first_id = sorted(queue["data"], key=lambda f: f["id"])[0]["id"]
    assert (
        await operator.post(f"/api/v1/unknown-faces/{first_id}/assign", json={"employee_id": employee.id})
    ).status_code == 403
    hr = await make_api(await make_user(db, UserRole.HR_ADMIN, "hr"))
    assigned = await hr.post(f"/api/v1/unknown-faces/{first_id}/assign", json={"employee_id": employee.id})
    assert assigned.json()["data"]["attendance_updated"] is True
    dismissed = await operator.patch(
        f"/api/v1/unknown-faces/{groups[2]}", json={"review_status": "dismissed"}
    )
    assert dismissed.json()["data"]["review_status"] == "dismissed"
    audit = (
        await (await make_api(await make_user(db, UserRole.SUPER_ADMIN, "admin"))).get(
            "/api/v1/audit-logs", params={"action": "unknown_face.view_queue"}
        )
    ).json()
    assert audit["pagination"]["total"] >= 1  # standards/18: viewing the queue is audited


async def test_fr29_dashboard_counts_scoped(make_api, db: AsyncSession) -> None:  # type: ignore[no-untyped-def]
    org = await make_org(db)
    await make_employee(db, org, "S1", department="sales")
    await make_employee(db, org, "F1", department="finance")
    camera = await make_camera(db, org, "Entrance", CameraRole.ENTRY)
    await recognition.process_event(db, _event(camera.id, "S1"))
    hr = await make_api(await make_user(db, UserRole.HR_ADMIN, "hr"))
    summary = (await hr.get("/api/v1/dashboard/summary")).json()["data"]
    assert summary["present"] == 1 and summary["in_office_now"] == 1
    assert len(summary["cameras"]) == 1 and sum(h["count"] for h in summary["hourly_arrivals"]) == 1
    employee = await make_api(await make_user(db, UserRole.EMPLOYEE, "e", employee_id=None))
    assert (await employee.get("/api/v1/dashboard/summary")).status_code == 403


def test_ws_live_messages_follow_rest_scoping() -> None:
    def user(role: UserRole) -> User:
        return User(id=1, role=role, name="x", username="x", email="x@example.com")

    recognition_msg = {"type": "RecognitionCreated", "data": {"employee_id": 5, "department_id": 2}}
    attendance_msg = {"type": "AttendanceUpdated", "data": {"employee_id": 5, "department_id": 2}}
    camera_msg = {"type": "CameraStatusChanged", "data": {"camera_id": 1}}
    everyone = DataScope(all_employees=True)
    manager_dept_2 = DataScope(all_employees=False, department_ids=frozenset({2}))
    manager_dept_3 = DataScope(all_employees=False, department_ids=frozenset({3}))
    assert allowed(recognition_msg, user(UserRole.OPERATOR), DataScope(False))
    assert allowed(recognition_msg, user(UserRole.DEPARTMENT_MANAGER), manager_dept_2)
    assert not allowed(recognition_msg, user(UserRole.DEPARTMENT_MANAGER), manager_dept_3)
    assert allowed(attendance_msg, user(UserRole.HR_ADMIN), everyone)
    assert not allowed(attendance_msg, user(UserRole.OPERATOR), DataScope(False))
    assert allowed(camera_msg, user(UserRole.OPERATOR), DataScope(False))
    assert not allowed(camera_msg, user(UserRole.EMPLOYEE), DataScope(False, employee_id=5))
    assert not allowed({"type": "Other", "data": {}}, user(UserRole.SUPER_ADMIN), everyone)


# --------------------------------------------------------------------------- one card per person (§13 screen 9)


def _unknown_at(
    camera_id: int, when: datetime, vector: np.ndarray | None, snapshot: str | None = None
) -> RecognitionEvent:
    import base64

    token = (
        base64.b64encode(get_cipher().encrypt_embedding(vector, CRYPTO_PURPOSE_EMBEDDING)).decode()
        if vector is not None
        else None
    )
    event = _event(camera_id, None, snapshot=snapshot, embedding=token)
    return event.model_copy(update={"captured_at": when})


def _person(seed: int) -> np.ndarray:
    """A synthetic identity direction (random vector, not a face)."""
    vector = np.random.default_rng(seed).standard_normal(128).astype(np.float32)
    return vector / np.linalg.norm(vector)


def _sighting(person: np.ndarray, seed: int) -> np.ndarray:
    """One synthetic sighting: the identity plus noise (cosine to the identity about 0.75)."""
    noise = np.random.default_rng(1000 + seed).standard_normal(128).astype(np.float32) * 0.08
    return (person + noise).astype(np.float32)


async def _queue_two_people(db: AsyncSession, camera_id: int) -> dict[str, list[int]]:
    """Person A seen 5 times and B 4 times, interleaved over 9 minutes, plus 2 faces without an embedding."""
    from facetrack_common.models import UnknownFace
    from sqlalchemy import select

    a, b = _person(1), _person(2)
    start = datetime(2026, 10, 5, 4, 0, tzinfo=UTC)
    plan = ["A", "B", "A", "B", "A", "-", "B", "A", "B", "A", "-"]
    for minute, who in enumerate(plan):
        vector = None if who == "-" else _sighting(a if who == "A" else b, minute)
        snapshot = None
        if who == "A" and minute in (0, 4, 9):
            snapshot = f"snapshots/2026/10/05/u-{minute}.jpg"
            storage.put_encrypted(snapshot, b"\xff\xd8synthetic")
        when = start.replace(minute=minute)
        await recognition.process_event(db, _unknown_at(camera_id, when, vector, snapshot))
    faces = (await db.scalars(select(UnknownFace).order_by(UnknownFace.captured_at))).all()
    ids: dict[str, list[int]] = {"A": [], "B": [], "-": []}
    for who, face in zip(plan, faces, strict=True):
        ids[who].append(face.id)
    return ids


async def test_fr17_unknown_groups_one_card_per_person_across_pages(make_api, db: AsyncSession) -> None:  # type: ignore[no-untyped-def]
    org = await make_org(db)
    camera = await make_camera(db, org, "Entrance", CameraRole.ENTRY)
    ids = await _queue_two_people(db, camera.id)
    operator = await make_api(await make_user(db, UserRole.OPERATOR, "op"))

    # The per-face list still works and, with 4 faces per page, spreads person A over pages.
    per_face = (await operator.get("/api/v1/unknown-faces", params={"page_size": 4})).json()
    assert per_face["pagination"]["total"] == 11 and len(per_face["data"]) == 4

    first = (await operator.get("/api/v1/unknown-faces/groups", params={"page_size": 2})).json()
    assert first["success"] is True
    assert first["pagination"] == {"page": 1, "page_size": 2, "total": 4}  # A, B and two singletons
    assert first["grouping"] == {
        "faces_total": 11,
        "faces_grouped": 11,
        "max_faces": 5000,
        "truncated": False,
    }
    second = (await operator.get("/api/v1/unknown-faces/groups", params={"page_size": 2, "page": 2})).json()
    cards = first["data"] + second["data"]
    by_ids = {frozenset(card["face_ids"]): card for card in cards}
    card_a, card_b = by_ids[frozenset(ids["A"])], by_ids[frozenset(ids["B"])]
    assert card_a["face_count"] == 5 and card_a["pending_count"] == 5
    assert card_a["group_id"] == ids["A"][0]  # the oldest face of the group: a stable id
    assert card_a["face_ids"] == list(reversed(ids["A"]))  # newest first
    assert card_a["camera_ids"] == [camera.id] and card_a["camera_names"] == ["Entrance"]
    assert (
        card_a["first_seen_at"] == "2026-10-05T04:00:00Z" and card_a["last_seen_at"] == "2026-10-05T04:09:00Z"
    )
    # Thumbnails: faces with a snapshot first (newest first), then the rest; at most 8.
    assert [s["snapshot_available"] for s in card_a["samples"]] == [True, True, True, False, False]
    assert [s["id"] for s in card_a["samples"][:3]] == [ids["A"][4], ids["A"][2], ids["A"][0]]
    assert {s["group_id"] for s in card_a["samples"]} == {card_a["group_id"]}
    assert card_b["face_count"] == 4 and set(card_b["face_ids"]) == set(ids["B"])
    singletons = [card for card in cards if card["face_count"] == 1]
    assert sorted(card["group_id"] for card in singletons) == sorted(ids["-"])
    # Newest activity first: the last face (no embedding, 04:10) is the newest card.
    assert [card["last_seen_at"] for card in cards] == sorted(
        (c["last_seen_at"] for c in cards), reverse=True
    )
    biggest = (await operator.get("/api/v1/unknown-faces/groups", params={"sort": "-face_count"})).json()
    assert [card["face_count"] for card in biggest["data"]] == [5, 4, 1, 1]
    assert (await operator.get("/api/v1/unknown-faces/groups", params={"sort": "id"})).status_code == 422

    audit = (
        await (await make_api(await make_user(db, UserRole.SUPER_ADMIN, "admin"))).get(
            "/api/v1/audit-logs", params={"action": "unknown_face.view_queue"}
        )
    ).json()
    assert any(row["new_values"] == {"page": 2, "view": "groups"} for row in audit["data"])  # standards/18
    assert all("embedding" not in str(row) for row in audit["data"])


async def test_fr17_unknown_groups_report_truncation_and_scoping(
    make_api, db: AsyncSession, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    org = await make_org(db)
    camera = await make_camera(db, org, "Entrance", CameraRole.ENTRY)
    other = await make_camera(db, org, "Exit", CameraRole.EXIT)
    await _queue_two_people(db, camera.id)
    await recognition.process_event(
        db, _unknown_at(other.id, datetime(2026, 10, 5, 5, tzinfo=UTC), _person(3))
    )
    operator = await make_api(await make_user(db, UserRole.OPERATOR, "op"))
    monkeypatch.setattr(recognition, "UNKNOWN_GROUPING_MAX_FACES", 3)
    cut = (await operator.get("/api/v1/unknown-faces/groups")).json()
    assert cut["grouping"] == {"faces_total": 12, "faces_grouped": 3, "max_faces": 3, "truncated": True}
    assert sum(card["face_count"] for card in cut["data"]) == 3
    monkeypatch.undo()
    exit_only = (await operator.get("/api/v1/unknown-faces/groups", params={"camera_id": other.id})).json()
    assert exit_only["grouping"]["faces_total"] == 1 and exit_only["data"][0]["camera_names"] == ["Exit"]
    dismissed = (
        await operator.get("/api/v1/unknown-faces/groups", params={"review_status": "dismissed"})
    ).json()
    assert dismissed["data"] == [] and dismissed["pagination"]["total"] == 0
    employee = await make_api(await make_user(db, UserRole.EMPLOYEE, "emp"))
    assert (await employee.get("/api/v1/unknown-faces/groups")).status_code == 403
    anonymous = await make_api()
    assert (await anonymous.get("/api/v1/unknown-faces/groups")).status_code == 401


async def test_fr27_bulk_assign_and_dismiss_a_group(make_api, db: AsyncSession, fake_engine) -> None:  # type: ignore[no-untyped-def]
    from facetrack_common.constants import ReviewStatus
    from facetrack_common.models import AttendanceDay, RecognitionEventRecord, UnknownFace
    from sqlalchemy import select

    org = await make_org(db)
    employee = await make_employee(db, org, "E1")
    no_consent = await make_employee(db, org, "E2", consent=False)
    camera = await make_camera(db, org, "Entrance", CameraRole.ENTRY)
    ids = await _queue_two_people(db, camera.id)
    operator = await make_api(await make_user(db, UserRole.OPERATOR, "op"))
    hr = await make_api(await make_user(db, UserRole.HR_ADMIN, "hr"))
    group_a = list(reversed(ids["A"]))  # as the groups endpoint lists them: newest first

    # Same permissions as the single actions: operators may dismiss but not assign (§4).
    forbidden = await operator.post(
        "/api/v1/unknown-faces/bulk",
        json={"face_ids": group_a, "action": "assign", "employee_id": employee.id},
    )
    assert forbidden.status_code == 403
    for bad in (
        {"face_ids": group_a, "action": "assign"},
        {"face_ids": group_a, "action": "dismiss", "employee_id": employee.id},
        {"face_ids": [], "action": "dismiss"},
        {"face_ids": [0], "action": "dismiss"},
        {"face_ids": group_a, "action": "delete"},
    ):
        assert (await hr.post("/api/v1/unknown-faces/bulk", json=bad)).status_code == 422, bad
    missing = await hr.post(
        "/api/v1/unknown-faces/bulk", json={"face_ids": group_a, "action": "assign", "employee_id": 999999}
    )
    assert missing.status_code == 422 and "employee_id" in missing.json()["errors"]
    refused = await hr.post(
        "/api/v1/unknown-faces/bulk",
        json={"face_ids": group_a, "action": "assign", "employee_id": no_consent.id, "add_to_gallery": True},
    )
    assert refused.status_code == 422  # standards/18: no gallery without consent, and nothing assigned
    reviewed = select(UnknownFace).where(UnknownFace.review_status != ReviewStatus.PENDING)
    assert (await db.scalars(reviewed)).first() is None

    assigned = await hr.post(
        "/api/v1/unknown-faces/bulk",
        json={
            "face_ids": [*group_a, 999999],
            "action": "assign",
            "employee_id": employee.id,
            "add_to_gallery": True,
        },
    )
    assert assigned.status_code == 200, assigned.text
    result = assigned.json()["data"]
    assert result["processed_ids"] == group_a
    assert result["skipped"] == [{"id": 999999, "reason": "not_found"}]
    assert result["attendance_updated"] is True
    # Only one photo goes to the gallery: the first assigned face (request order) with a snapshot (Q43).
    assert result["added_to_gallery"] is True and result["gallery_face_id"] == ids["A"][4]
    assert fake_engine.calls == 1 and "gallery_reload" in fake_engine.notifications
    assert (
        assigned.json()["message"] == "5 unknown face(s) assigned. 1 skipped (already reviewed or not found)."
    )

    employee_id = employee.id
    db.expire_all()
    events = (
        await db.scalars(
            select(RecognitionEventRecord).where(RecognitionEventRecord.employee_id == employee_id)
        )
    ).all()
    assert len(events) == 5 and {e.status.value for e in events} == {"recognized"}
    day = (await db.scalars(select(AttendanceDay).where(AttendanceDay.employee_id == employee_id))).one()
    assert day.check_in_at == datetime(2026, 10, 5, 4, 0, tzinfo=UTC)  # the earliest sighting of the group

    again = (
        await hr.post(
            "/api/v1/unknown-faces/bulk",
            json={"face_ids": group_a, "action": "assign", "employee_id": employee_id},
        )
    ).json()["data"]
    assert again["processed_ids"] == [] and {s["reason"] for s in again["skipped"]} == {"already_reviewed"}

    dismissed = await operator.post(
        "/api/v1/unknown-faces/bulk", json={"face_ids": ids["B"], "action": "dismiss"}
    )
    assert dismissed.status_code == 200 and dismissed.json()["data"]["processed_ids"] == ids["B"]
    pending = (await operator.get("/api/v1/unknown-faces/groups")).json()
    assert sorted(card["group_id"] for card in pending["data"]) == sorted(ids["-"])

    audit = (
        await (await make_api(await make_user(db, UserRole.SUPER_ADMIN, "admin"))).get(
            "/api/v1/audit-logs", params={"action": "unknown_face.assign", "page_size": 50}
        )
    ).json()
    assert audit["pagination"]["total"] == 5  # one entry per face (FR-37)
    assert all(row["new_values"]["bulk"] is True for row in audit["data"])


async def test_q59_event_log_shows_a_pruned_snapshot_as_unavailable(make_api, db: AsyncSession) -> None:  # type: ignore[no-untyped-def]
    org = await make_org(db)
    await make_employee(db, org, "E1", created_at=datetime(2026, 1, 1, tzinfo=UTC))
    camera = await make_camera(db, org, "Entrance", CameraRole.ENTRY)
    outcomes = []
    for minute in (0, 2):  # a repeat inside the 5-minute §10.3 window
        name = f"snapshots/2026/10/05/{minute}-{uuid.uuid4()}.jpg"
        storage.put_encrypted(name, b"\xff\xd8synthetic")
        captured_at = datetime(2026, 10, 5, 9, minute, tzinfo=PKT).astimezone(UTC)
        base = _event(camera.id, "E1", snapshot=name)
        outcomes.append(
            await recognition.process_event(db, base.model_copy(update={"captured_at": captured_at}))
        )
    kept, pruned = outcomes
    hr = await make_api(await make_user(db, UserRole.HR_ADMIN, "hr"))
    before = {row["id"]: row for row in (await hr.get("/api/v1/events")).json()["data"]}
    assert before[pruned.event_id]["snapshot_available"] is True  # kept until the day closes
    await attendance_service.close_due_days(
        db, now=datetime(2026, 10, 6, 3, 0, tzinfo=PKT).astimezone(UTC), lookback_days=1
    )
    rows = {row["id"]: row for row in (await hr.get("/api/v1/events")).json()["data"]}
    assert rows[kept.event_id]["snapshot_available"] is True
    assert (
        rows[pruned.event_id]["snapshot_available"] is False
        and rows[pruned.event_id]["status"] == "recognized"
    )
    assert (await hr.get(f"/api/v1/events/{kept.event_id}/snapshot")).status_code == 200
    missing = await hr.get(f"/api/v1/events/{pruned.event_id}/snapshot")
    assert missing.status_code == 404 and missing.json()["success"] is False
