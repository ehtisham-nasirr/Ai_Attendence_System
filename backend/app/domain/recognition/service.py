"""Recognition events and unknown faces (FR-16, FR-17, FR-20, FR-27, FR-28).

`process_event` is idempotent: an event is stored once per `event_uuid` (+ `captured_at`), and the
attendance day is recomputed from all events, so processing the same event twice changes nothing.
"""

import asyncio
import base64
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from facetrack_common.constants import (
    CRYPTO_PURPOSE_EMBEDDING,
    EnrollmentSource,
    RecognitionStatus,
    ReviewStatus,
    WsMessageType,
)
from facetrack_common.events import RecognitionEvent
from facetrack_common.models import (
    AttendanceDay,
    Employee,
    FaceEnrollment,
    RecognitionEventRecord,
    UnknownFace,
    User,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import get_cipher
from app.core.db import transaction
from app.core.exceptions import Conflict, EngineUnavailable, NotFound, ValidationFailed
from app.core.pagination import PageParams
from app.domain.attendance import service as attendance_service
from app.domain.audit import service as audit
from app.domain.employees import enrollment
from app.domain.recognition import grouping
from app.domain.settings import service as settings_service
from app.repositories import camera_repo, employee_repo, event_repo
from app.schemas.recognition import (
    UNKNOWN_GROUP_SAMPLES,
    UNKNOWN_GROUPING_MAX_FACES,
    EventOut,
    UnknownFaceGrouping,
    UnknownFaceGroupOut,
    UnknownFaceOut,
)
from app.services import engine_client, storage

logger = logging.getLogger(__name__)


class InvalidEvent(Exception):
    """The event is well-formed but cannot be accepted (unknown camera/employee); dead-letter it."""


# A check-in confirmation (FR-33) is only sent for an event this recent; replays of old events stay quiet.
CHECKIN_NOTICE_MAX_AGE = timedelta(minutes=15)


@dataclass
class ProcessOutcome:
    stored: bool
    event_id: int | None
    attendance: AttendanceDay | None
    employee: Employee | None
    # Set when this event became the day's check-in: "09:05 at Main entrance" (employee local time).
    checkin_text: str | None = None


def event_to_out(event: RecognitionEventRecord) -> EventOut:
    return EventOut(
        id=event.id,
        event_uuid=str(event.event_uuid),
        camera_id=event.camera_id,
        camera_name=event.camera.name if event.camera else None,
        employee_id=event.employee_id,
        employee_code=event.employee.employee_code if event.employee else None,
        employee_name=event.employee.full_name if event.employee else None,
        status=event.status,
        confidence=event.confidence,
        liveness_score=event.liveness_score,
        track_id=event.track_id,
        captured_at=event.captured_at,
        snapshot_available=event.snapshot_path is not None,
        model_name=event.model_name,
        void_reason=event.void_reason,
        voided_at=event.voided_at,
    )


async def process_event(db: AsyncSession, event: RecognitionEvent) -> ProcessOutcome:
    """Stores one engine event and applies it to attendance (FR-20). Commits its own transaction.

    Duplicate photos of a sighting are pruned only when the day closes (Q59, `attendance.service`).
    """
    values = await settings_service.resolved(db)
    async with transaction(db):
        camera = await camera_repo.by_id_any(db, event.camera_id)
        if camera is None:
            raise InvalidEvent("unknown camera")
        employee: Employee | None = None
        if event.status == "recognized":
            employee = await employee_repo.by_code(db, event.employee_code or "")
            if employee is None:
                raise InvalidEvent("unknown employee code")
        event_id = await event_repo.insert_event(
            db,
            {
                "event_uuid": event.event_id,
                "camera_id": camera.id,
                "employee_id": employee.id if employee else None,
                "status": RecognitionStatus(event.status),
                "confidence": event.confidence,
                "liveness_score": event.liveness_score,
                "track_id": event.track_id,
                "snapshot_path": event.snapshot_path,
                "captured_at": event.captured_at,
                "model_name": event.model_name,
                "engine_node": event.engine_node,
            },
        )
        if event_id is None:
            # Duplicate delivery: nothing to store. If the stored row has no snapshot (pruned at day close,
            # or deleted by retention), an object the engine wrote again must not be kept (standards/18).
            storage.delete_quietly(await _orphaned_snapshot(db, event))
            return ProcessOutcome(False, None, None, employee)
        if event.status == "unknown":
            db.add(_unknown_face(event, event_id))
            await db.flush()
        day = None
        checkin_text = None
        if employee is not None:
            day = await attendance_service.apply_recognition(db, employee, event.captured_at, values)
            if (
                day is not None
                and day.check_in_event_id == event_id
                and datetime.now(UTC) - event.captured_at <= CHECKIN_NOTICE_MAX_AGE
            ):
                tz = attendance_service.employee_context(employee, values).tz
                checkin_text = f"{event.captured_at.astimezone(tz):%H:%M} at {camera.name}"
    return ProcessOutcome(True, event_id, day, employee, checkin_text)


async def _orphaned_snapshot(db: AsyncSession, event: RecognitionEvent) -> list[str]:
    if event.snapshot_path is None or not event.snapshot_path.startswith(storage.EVENT_SNAPSHOT_PREFIX):
        return []
    stored = await event_repo.get_event_by_uuid(db, event.event_id)
    if stored is None or stored.snapshot_path is not None:
        return []
    return [event.snapshot_path]


def _unknown_face(event: RecognitionEvent, event_id: int) -> UnknownFace:
    token = base64.b64decode(event.embedding_encrypted) if event.embedding_encrypted else None
    dim = None
    if token is not None:
        # Decrypting only proves the ciphertext is valid and gives its dimension; it is stored encrypted.
        raw = get_cipher().decrypt(token, CRYPTO_PURPOSE_EMBEDDING)
        dim = len(raw) // 4
    return UnknownFace(
        recognition_event_id=event_id,
        captured_at=event.captured_at,
        camera_id=event.camera_id,
        embedding_encrypted=token,
        embedding_dim=dim,
        model_name=event.model_name,
        snapshot_path=event.snapshot_path,
        liveness_score=event.liveness_score,
        review_status=ReviewStatus.PENDING,
    )


def live_messages(
    event: RecognitionEvent, outcome: ProcessOutcome
) -> list[tuple[WsMessageType, dict[str, Any]]]:
    """`/ws/live` messages for a processed event (RecognitionCreated / AttendanceUpdated)."""
    if not outcome.stored or outcome.event_id is None:
        return []
    employee = outcome.employee
    messages: list[tuple[WsMessageType, dict[str, Any]]] = [
        (
            WsMessageType.RECOGNITION_CREATED,
            {
                "event_id": outcome.event_id,
                "camera_id": event.camera_id,
                "status": event.status,
                "employee_id": employee.id if employee else None,
                "employee_code": employee.employee_code if employee else None,
                "employee_name": employee.full_name if employee else None,
                "department_id": employee.department_id if employee else None,
                "confidence": event.confidence,
                "captured_at": event.captured_at.isoformat(),
                "bbox": list(event.bbox) if event.bbox else None,
                "snapshot_available": event.snapshot_path is not None,
            },
        )
    ]
    day = outcome.attendance
    if day is not None and employee is not None:
        messages.append(
            (
                WsMessageType.ATTENDANCE_UPDATED,
                {
                    "attendance_day_id": day.id,
                    "employee_id": employee.id,
                    "department_id": employee.department_id,
                    "work_date": day.work_date.isoformat(),
                    "status": day.status.value if day.status else None,
                    "check_in_at": day.check_in_at.isoformat() if day.check_in_at else None,
                    "check_out_at": day.check_out_at.isoformat() if day.check_out_at else None,
                },
            )
        )
    return messages


# --------------------------------------------------------------------------- void (FR-28)


async def void_event(db: AsyncSession, event_id: int, reason: str, actor: User) -> RecognitionEventRecord:
    values = await settings_service.resolved(db)
    async with transaction(db):
        event = await event_repo.get_event(db, event_id, for_update=True)
        if event is None:
            raise NotFound("Event not found.")
        if event.status == RecognitionStatus.VOIDED:
            raise Conflict("This event is already voided.")
        if event.status != RecognitionStatus.RECOGNIZED:
            raise Conflict("Only recognised events can be voided; dismiss unknown faces instead.")
        event.status = RecognitionStatus.VOIDED
        event.void_reason = reason
        event.voided_by = actor.id
        event.voided_at = datetime.now(UTC)
        await db.flush()
        employee = await employee_repo.get(db, event.employee_id) if event.employee_id else None
        if employee is not None:
            # Kept (voided) for monthly threshold tuning; the day is rebuilt without it.
            work_date = await attendance_service.work_date_of(db, employee, event.captured_at)
            await attendance_service.recompute_day(db, employee, work_date, values)
        await audit.record(
            db,
            actor,
            "event.void",
            "recognition_event",
            event.id,
            old={"status": "recognized"},
            new={"status": "voided", "reason": reason, "confidence": event.confidence},
        )
    reloaded = await event_repo.get_event(db, event_id)
    if reloaded is None:
        raise NotFound("Event not found.")
    return reloaded


async def event_snapshot(event: RecognitionEventRecord | UnknownFace) -> bytes:
    if not event.snapshot_path:
        raise NotFound("No snapshot (deleted by retention or never stored).")
    try:
        return storage.get_decrypted(event.snapshot_path)
    except Exception as exc:  # missing object or undecryptable: same answer for the client
        raise NotFound("Snapshot not available.") from exc


# --------------------------------------------------------------------------- unknown faces (FR-17, FR-27)


def group_by_similarity(faces: list[UnknownFace], thresholds: dict[str, float]) -> dict[int, int]:
    """Groups the faces of one page of the per-face list (§13 screen 9; method in `grouping`).

    Faces without an embedding get no group id, as before.
    """
    return grouping.group_faces(
        (
            grouping.FaceVector(f.id, f.captured_at, f.model_name, f.embedding_encrypted, f.embedding_dim)
            for f in faces
            if f.embedding_encrypted and f.embedding_dim
        ),
        thresholds,
    )


def unknown_to_out(face: UnknownFace, group_id: int | None = None) -> UnknownFaceOut:
    return UnknownFaceOut(
        id=face.id,
        recognition_event_id=face.recognition_event_id,
        captured_at=face.captured_at,
        camera_id=face.camera_id,
        camera_name=face.camera.name if face.camera else None,
        liveness_score=face.liveness_score,
        review_status=face.review_status,
        assigned_employee_id=face.assigned_employee_id,
        reviewed_at=face.reviewed_at,
        snapshot_available=face.snapshot_path is not None,
        group_id=group_id,
    )


async def review_queue(
    db: AsyncSession,
    page: PageParams,
    actor: User,
    *,
    review_status: ReviewStatus | None,
    camera_id: int | None,
    date_from: datetime | None,
    date_to: datetime | None,
) -> tuple[list[UnknownFaceOut], int]:
    """The review queue, grouped by similarity. Viewing it is audit-logged (standards/18)."""
    faces, total = await event_repo.list_unknown(
        db, page, review_status=review_status, camera_id=camera_id, date_from=date_from, date_to=date_to
    )
    values = await settings_service.resolved(db)
    groups = group_by_similarity(faces, values["recognition.match_thresholds"])
    async with transaction(db):
        await audit.record(
            db, actor, "unknown_face.view_queue", "unknown_face", None, new={"page": page.page}
        )
    return [unknown_to_out(face, groups.get(face.id)) for face in faces], total


_GROUP_SORT = ("last_seen_at", "first_seen_at", "face_count")


async def review_groups(
    db: AsyncSession,
    page: PageParams,
    actor: User,
    *,
    review_status: ReviewStatus | None,
    camera_id: int | None,
    date_from: datetime | None,
    date_to: datetime | None,
) -> tuple[list[UnknownFaceGroupOut], int, UnknownFaceGrouping]:
    """The review queue as one card per person, grouped over every matching face (not per page).

    At most UNKNOWN_GROUPING_MAX_FACES of the newest faces are grouped; `UnknownFaceGrouping` says when
    older ones were left out. Viewing the queue is audit-logged (standards/18).
    Returns (groups of the requested page, number of groups, grouping coverage).
    """
    sort = page.sort or "-last_seen_at"
    sort_key = sort.lstrip("-")
    if sort_key not in _GROUP_SORT:
        raise ValidationFailed(errors={"sort": [f"Sorting by '{sort_key}' is not supported."]})
    rows, faces_total = await event_repo.unknown_for_grouping(
        db,
        review_status=review_status,
        camera_id=camera_id,
        date_from=date_from,
        date_to=date_to,
        limit=UNKNOWN_GROUPING_MAX_FACES,
    )
    values = await settings_service.resolved(db)
    vectors = [
        grouping.FaceVector(
            row.id, row.captured_at, row.model_name, row.embedding_encrypted, row.embedding_dim
        )
        for row in rows
    ]
    # Decrypting and comparing up to 5,000 embeddings is CPU work: keep it off the event loop.
    group_of = await asyncio.to_thread(grouping.group_faces, vectors, values["recognition.match_thresholds"])
    members: dict[int, list[event_repo.GroupingRow]] = defaultdict(list)
    for row in rows:  # newest first, so every member list is newest first too
        members[group_of[row.id]].append(row)
    cards = [_group_card(group_id, faces) for group_id, faces in members.items()]
    cards.sort(key=lambda card: (getattr(card, sort_key), card.group_id), reverse=sort.startswith("-"))
    async with transaction(db):
        await audit.record(
            db,
            actor,
            "unknown_face.view_queue",
            "unknown_face",
            None,
            new={"page": page.page, "view": "groups"},
        )
    coverage = UnknownFaceGrouping(
        faces_total=faces_total,
        faces_grouped=len(rows),
        max_faces=UNKNOWN_GROUPING_MAX_FACES,
        truncated=faces_total > len(rows),
    )
    return cards[page.offset : page.offset + page.page_size], len(cards), coverage


def _group_card(group_id: int, faces: list[event_repo.GroupingRow]) -> UnknownFaceGroupOut:
    """One card; `faces` is newest first."""
    cameras: dict[int, str] = {}
    for face in faces:
        cameras.setdefault(face.camera_id, face.camera_name)
    # Stable sort: faces with a snapshot first, newest first within each half.
    samples = sorted(faces, key=lambda face: not face.snapshot_available)[:UNKNOWN_GROUP_SAMPLES]
    return UnknownFaceGroupOut(
        group_id=group_id,
        face_count=len(faces),
        pending_count=sum(1 for face in faces if face.review_status == ReviewStatus.PENDING),
        first_seen_at=faces[-1].captured_at,
        last_seen_at=faces[0].captured_at,
        camera_ids=list(cameras),
        camera_names=list(cameras.values()),
        face_ids=[face.id for face in faces],
        samples=[
            UnknownFaceOut(
                id=face.id,
                recognition_event_id=face.recognition_event_id,
                captured_at=face.captured_at,
                camera_id=face.camera_id,
                camera_name=face.camera_name,
                liveness_score=face.liveness_score,
                review_status=face.review_status,
                assigned_employee_id=face.assigned_employee_id,
                reviewed_at=face.reviewed_at,
                snapshot_available=bool(face.snapshot_available),
                group_id=group_id,
            )
            for face in samples
        ],
    )


def _mark_reviewed(
    face: UnknownFace, status: ReviewStatus, actor: User, employee_id: int | None = None
) -> None:
    face.review_status = status
    face.assigned_employee_id = employee_id
    face.reviewed_by = actor.id
    face.reviewed_at = datetime.now(UTC)


async def assign_unknown(
    db: AsyncSession, unknown_id: int, employee_id: int, add_to_gallery: bool, actor: User
) -> tuple[UnknownFace, bool, bool, str | None]:
    """FR-27: the unknown sighting becomes a recognised event of `employee_id` and counts for attendance.

    Optionally the snapshot is added to the employee's gallery after the same FR-9 checks as any photo.
    Returns (face, attendance_updated, added_to_gallery, gallery_rejection_reason).
    """
    values = await settings_service.resolved(db)
    employee = await employee_repo.get(db, employee_id)
    if employee is None:
        raise ValidationFailed(errors={"employee_id": ["Employee not found."]})
    if add_to_gallery:
        enrollment.ensure_consent(employee)
    async with transaction(db):
        face = await event_repo.get_unknown(db, unknown_id, for_update=True)
        if face is None:
            raise NotFound("Unknown face not found.")
        if face.review_status != ReviewStatus.PENDING:
            raise Conflict("This face has already been reviewed.")
        event = await event_repo.get_event(db, face.recognition_event_id, for_update=True)
        _mark_reviewed(face, ReviewStatus.ASSIGNED, actor, employee.id)
        attendance_updated = False
        if event is not None:
            event.status = RecognitionStatus.RECOGNIZED
            event.employee_id = employee.id
            await db.flush()
            attendance_updated = (
                await attendance_service.apply_recognition(db, employee, event.captured_at, values)
                is not None
            )
        await audit.record(
            db,
            actor,
            "unknown_face.assign",
            "unknown_face",
            face.id,
            new={"employee_id": employee.id, "add_to_gallery": add_to_gallery},
        )

    added, rejection = False, None
    if add_to_gallery and face.snapshot_path:
        added, rejection = await _add_snapshot_to_gallery(db, face, employee, actor, values)
    reloaded = await event_repo.get_unknown(db, unknown_id)
    return reloaded or face, attendance_updated, added, rejection


async def _add_snapshot_to_gallery(
    db: AsyncSession, face: UnknownFace, employee: Employee, actor: User, values: dict[str, Any]
) -> tuple[bool, str | None]:
    snapshot = await event_snapshot(face)
    result = await engine_client.embed_photo(snapshot)  # same FR-9 gate as uploaded photos (Q27)
    if not result.accepted or not result.embedding_encrypted or not result.embedding_dim:
        return False, result.rejection_reason
    async with transaction(db):
        active = sum(1 for f in await employee_repo.list_faces(db, employee.id) if f.is_active)
        if active >= int(values["enrollment.max_photos"]):
            return False, "too_many_photos"
        image_path = storage.new_object_name(f"enroll/{employee.id}", "jpg")
        storage.put_encrypted(image_path, snapshot)
        db.add(
            FaceEnrollment(
                employee_id=employee.id,
                image_path=image_path,
                embedding_encrypted=base64.b64decode(result.embedding_encrypted),
                embedding_dim=result.embedding_dim,
                model_name=result.model_name,
                quality_score=float(result.quality_score or 0.0),
                source=EnrollmentSource.REVIEW,
                is_active=True,
            )
        )
        await audit.record(
            db,
            actor,
            "employee.enroll",
            "employee",
            employee.id,
            new={"source": "review", "unknown_face_id": face.id},
        )
    await engine_client.notify_engines("gallery_reload")
    return True, None


async def dismiss_unknown(db: AsyncSession, unknown_id: int, actor: User) -> UnknownFace:
    async with transaction(db):
        face = await event_repo.get_unknown(db, unknown_id, for_update=True)
        if face is None:
            raise NotFound("Unknown face not found.")
        if face.review_status != ReviewStatus.PENDING:
            raise Conflict("This face has already been reviewed.")
        _mark_reviewed(face, ReviewStatus.DISMISSED, actor)
        await audit.record(db, actor, "unknown_face.dismiss", "unknown_face", face.id)
    reloaded = await event_repo.get_unknown(db, unknown_id)
    return reloaded or face


@dataclass
class BulkReviewOutcome:
    processed_ids: list[int]
    skipped: list[tuple[int, Literal["not_found", "already_reviewed"]]] = field(default_factory=list)
    attendance_updated: bool = False
    added_to_gallery: bool = False
    gallery_face_id: int | None = None
    gallery_rejection_reason: str | None = None


async def bulk_review(
    db: AsyncSession,
    face_ids: list[int],
    action: Literal["assign", "dismiss"],
    employee_id: int | None,
    add_to_gallery: bool,
    actor: User,
) -> BulkReviewOutcome:
    """One decision for a whole group card (§13 screen 9, FR-27).

    Every face gets what the per-face assign or dismiss does, all in one transaction: an assigned
    face becomes a recognised sighting of the employee and each affected attendance day is rebuilt
    once. Faces that no longer exist or are no longer pending are skipped and reported. Each face is
    audit-logged on its own, without biometric data (standards/18). With `add_to_gallery`, only the
    first assigned face (request order) with a snapshot is offered to the gallery (Q43).
    """
    values = await settings_service.resolved(db)
    employee: Employee | None = None
    if action == "assign":
        employee = await employee_repo.get(db, employee_id) if employee_id is not None else None
        if employee is None:
            raise ValidationFailed(errors={"employee_id": ["Employee not found."]})
        if add_to_gallery:
            enrollment.ensure_consent(employee)
    requested = list(dict.fromkeys(face_ids))
    outcome = BulkReviewOutcome(processed_ids=[])
    async with transaction(db):
        locked = {face.id: face for face in await event_repo.unknown_for_update(db, requested)}
        pending: list[UnknownFace] = []
        for face_id in requested:
            face = locked.get(face_id)
            if face is None:
                outcome.skipped.append((face_id, "not_found"))
            elif face.review_status != ReviewStatus.PENDING:
                outcome.skipped.append((face_id, "already_reviewed"))
            else:
                pending.append(face)
        for face in pending:
            if employee is not None:
                _mark_reviewed(face, ReviewStatus.ASSIGNED, actor, employee.id)
                audit_action, audit_new = (
                    "unknown_face.assign",
                    {"employee_id": employee.id, "add_to_gallery": add_to_gallery, "bulk": True},
                )
            else:
                _mark_reviewed(face, ReviewStatus.DISMISSED, actor)
                audit_action, audit_new = "unknown_face.dismiss", {"bulk": True}
            await audit.record(db, actor, audit_action, "unknown_face", face.id, new=audit_new)
        if employee is not None and pending:
            events = await event_repo.events_for_update(db, [face.recognition_event_id for face in pending])
            for event in events:
                event.status = RecognitionStatus.RECOGNIZED
                event.employee_id = employee.id
            await db.flush()
            days = await attendance_service.apply_recognitions(
                db, employee, [event.captured_at for event in events], values
            )
            outcome.attendance_updated = bool(days)
    outcome.processed_ids = [face.id for face in pending]

    if employee is not None and add_to_gallery and pending:
        candidate = next((face for face in pending if face.snapshot_path), None)
        if candidate is None:
            outcome.gallery_rejection_reason = "no_snapshot"
            return outcome
        outcome.gallery_face_id = candidate.id
        try:
            added, rejection = await _add_snapshot_to_gallery(db, candidate, employee, actor, values)
        except NotFound:
            added, rejection = False, "snapshot_unavailable"
        except EngineUnavailable:
            # The decisions above are committed; only the gallery step could not run.
            added, rejection = False, "engine_unavailable"
        outcome.added_to_gallery, outcome.gallery_rejection_reason = added, rejection
    return outcome
