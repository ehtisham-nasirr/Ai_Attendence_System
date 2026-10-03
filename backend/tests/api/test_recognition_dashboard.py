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
