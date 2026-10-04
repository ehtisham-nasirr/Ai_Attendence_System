"""Recognition events and unknown faces."""

import uuid
from datetime import datetime
from typing import Any

from facetrack_common.constants import RecognitionStatus, ReviewStatus
from facetrack_common.models import Camera, RecognitionEventRecord, UnknownFace
from sqlalchemy import ColumnElement, Row, and_, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.pagination import PageParams, apply_sort, fetch_page

_EVENT_SORT = {
    "captured_at": RecognitionEventRecord.captured_at,
    "confidence": RecognitionEventRecord.confidence,
}


async def insert_event(db: AsyncSession, values: dict[str, Any]) -> int | None:
    """Idempotent insert: returns the new id, or None when this event was already stored."""
    stmt = (
        insert(RecognitionEventRecord)
        .values(**values)
        .on_conflict_do_nothing(constraint="uq_recognition_events_event_uuid")
        .returning(RecognitionEventRecord.id)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def get_event(
    db: AsyncSession, event_id: int, *, for_update: bool = False
) -> RecognitionEventRecord | None:
    stmt = (
        select(RecognitionEventRecord)
        .options(selectinload(RecognitionEventRecord.employee), selectinload(RecognitionEventRecord.camera))
        .where(RecognitionEventRecord.id == event_id)
    )
    if for_update:
        stmt = stmt.with_for_update(of=RecognitionEventRecord)
    return (await db.scalars(stmt)).first()


async def get_event_by_uuid(db: AsyncSession, event_uuid: uuid.UUID) -> RecognitionEventRecord | None:
    stmt = select(RecognitionEventRecord).where(RecognitionEventRecord.event_uuid == event_uuid)
    return (await db.scalars(stmt)).first()


async def list_events(
    db: AsyncSession,
    params: PageParams,
    *,
    camera_id: int | None,
    employee_id: int | None,
    status: RecognitionStatus | None,
    date_from: datetime | None,
    date_to: datetime | None,
) -> tuple[list[RecognitionEventRecord], int]:
    stmt = select(RecognitionEventRecord).options(
        selectinload(RecognitionEventRecord.employee), selectinload(RecognitionEventRecord.camera)
    )
    if camera_id:
        stmt = stmt.where(RecognitionEventRecord.camera_id == camera_id)
    if employee_id:
        stmt = stmt.where(RecognitionEventRecord.employee_id == employee_id)
    if status:
        stmt = stmt.where(RecognitionEventRecord.status == status)
    if date_from:
        stmt = stmt.where(RecognitionEventRecord.captured_at >= date_from)
    if date_to:
        stmt = stmt.where(RecognitionEventRecord.captured_at < date_to)
    sort = apply_sort(stmt, params.sort or "-captured_at", _EVENT_SORT, RecognitionEventRecord.id)
    return await fetch_page(db, sort, params)


async def employee_sightings(
    db: AsyncSession, employee_id: int, start: datetime, end: datetime
) -> list[tuple[int, datetime, int, Any]]:
    """Recognised, non-voided events of an employee in (start, end]: (id, captured_at, camera_id, role)."""
    stmt = (
        select(
            RecognitionEventRecord.id,
            RecognitionEventRecord.captured_at,
            RecognitionEventRecord.camera_id,
            Camera.role,
        )
        .join(Camera, Camera.id == RecognitionEventRecord.camera_id)
        .where(
            RecognitionEventRecord.employee_id == employee_id,
            RecognitionEventRecord.status == RecognitionStatus.RECOGNIZED,
            RecognitionEventRecord.captured_at > start,
            RecognitionEventRecord.captured_at <= end,
        )
    )
    return [(r[0], r[1], r[2], r[3]) for r in (await db.execute(stmt)).all()]


async def snapshot_sightings(
    db: AsyncSession, employee_id: int, start: datetime, end: datetime
) -> list[tuple[int, datetime, int, str, bool]]:
    """Recognised, non-voided events of an employee in (start, end] that still have a snapshot, oldest
    first: (id, captured_at, camera_id, snapshot_path, came from an unknown face). Used by the Q59
    duplicate-photo pruning at day close."""
    from_unknown = select(UnknownFace.id).where(UnknownFace.recognition_event_id == RecognitionEventRecord.id)
    stmt = (
        select(
            RecognitionEventRecord.id,
            RecognitionEventRecord.captured_at,
            RecognitionEventRecord.camera_id,
            RecognitionEventRecord.snapshot_path,
            from_unknown.exists(),
        )
        .where(
            RecognitionEventRecord.employee_id == employee_id,
            RecognitionEventRecord.status == RecognitionStatus.RECOGNIZED,
            RecognitionEventRecord.snapshot_path.is_not(None),
            RecognitionEventRecord.captured_at > start,
            RecognitionEventRecord.captured_at <= end,
        )
        .order_by(RecognitionEventRecord.captured_at, RecognitionEventRecord.id)
    )
    return [(r[0], r[1], r[2], r[3], bool(r[4])) for r in (await db.execute(stmt)).all() if r[3]]


async def events_for_update(db: AsyncSession, event_ids: list[int]) -> list[RecognitionEventRecord]:
    if not event_ids:
        return []
    stmt = (
        select(RecognitionEventRecord)
        .where(RecognitionEventRecord.id.in_(event_ids))
        .order_by(RecognitionEventRecord.id)
        .with_for_update(of=RecognitionEventRecord)
    )
    return list((await db.scalars(stmt)).all())


async def count_unknown_between(db: AsyncSession, start: datetime, end: datetime) -> int:
    stmt = (
        select(func.count())
        .select_from(UnknownFace)
        .where(and_(UnknownFace.captured_at >= start, UnknownFace.captured_at < end))
    )
    return int(await db.scalar(stmt) or 0)


async def clear_snapshot_paths(db: AsyncSession, paths: list[str]) -> None:
    if paths:
        await db.execute(
            update(RecognitionEventRecord)
            .where(RecognitionEventRecord.snapshot_path.in_(paths))
            .values(snapshot_path=None)
        )


async def employee_snapshot_paths(db: AsyncSession, employee_id: int) -> list[str]:
    stmt = select(RecognitionEventRecord.snapshot_path).where(
        RecognitionEventRecord.employee_id == employee_id, RecognitionEventRecord.snapshot_path.is_not(None)
    )
    return [p for p in await db.scalars(stmt) if p]


async def events_with_snapshots_before(
    db: AsyncSession, cutoff: datetime, limit: int
) -> list[tuple[int, datetime, str]]:
    stmt = (
        select(
            RecognitionEventRecord.id,
            RecognitionEventRecord.captured_at,
            RecognitionEventRecord.snapshot_path,
        )
        .where(RecognitionEventRecord.captured_at < cutoff, RecognitionEventRecord.snapshot_path.is_not(None))
        .limit(limit)
    )
    return [(r[0], r[1], r[2]) for r in (await db.execute(stmt)).all() if r[2] is not None]


# --- unknown faces ---


async def insert_unknown(db: AsyncSession, unknown: UnknownFace) -> None:
    db.add(unknown)
    await db.flush()


async def get_unknown(db: AsyncSession, unknown_id: int, *, for_update: bool = False) -> UnknownFace | None:
    stmt = select(UnknownFace).options(selectinload(UnknownFace.camera)).where(UnknownFace.id == unknown_id)
    if for_update:
        stmt = stmt.with_for_update(of=UnknownFace)
    return (await db.scalars(stmt)).first()


async def list_unknown(
    db: AsyncSession,
    params: PageParams,
    *,
    review_status: ReviewStatus | None,
    camera_id: int | None,
    date_from: datetime | None,
    date_to: datetime | None,
) -> tuple[list[UnknownFace], int]:
    stmt = (
        select(UnknownFace)
        .options(selectinload(UnknownFace.camera))
        .where(*_unknown_filters(review_status, camera_id, date_from, date_to))
    )
    sort = apply_sort(
        stmt, params.sort or "-captured_at", {"captured_at": UnknownFace.captured_at}, UnknownFace.id
    )
    return await fetch_page(db, sort, params)


# One unknown face as `unknown_for_grouping` returns it (columns are read by name).
type GroupingRow = Row[*tuple[Any, ...]]


def _unknown_filters(
    review_status: ReviewStatus | None,
    camera_id: int | None,
    date_from: datetime | None,
    date_to: datetime | None,
) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []
    if review_status:
        conditions.append(UnknownFace.review_status == review_status)
    if camera_id:
        conditions.append(UnknownFace.camera_id == camera_id)
    if date_from:
        conditions.append(UnknownFace.captured_at >= date_from)
    if date_to:
        conditions.append(UnknownFace.captured_at < date_to)
    return conditions


async def unknown_for_grouping(
    db: AsyncSession,
    *,
    review_status: ReviewStatus | None,
    camera_id: int | None,
    date_from: datetime | None,
    date_to: datetime | None,
    limit: int,
) -> tuple[list[GroupingRow], int]:
    """The newest `limit` unknown faces matching the filters (only the columns grouping and the cards
    need), and how many match in total."""
    columns = select(
        UnknownFace.id,
        UnknownFace.recognition_event_id,
        UnknownFace.captured_at,
        UnknownFace.camera_id,
        Camera.name.label("camera_name"),
        UnknownFace.liveness_score,
        UnknownFace.review_status,
        UnknownFace.assigned_employee_id,
        UnknownFace.reviewed_at,
        UnknownFace.snapshot_path.is_not(None).label("snapshot_available"),
        UnknownFace.model_name,
        UnknownFace.embedding_encrypted,
        UnknownFace.embedding_dim,
    ).join(Camera, Camera.id == UnknownFace.camera_id)
    stmt = columns.where(*_unknown_filters(review_status, camera_id, date_from, date_to))
    rows = (
        await db.execute(stmt.order_by(UnknownFace.captured_at.desc(), UnknownFace.id.desc()).limit(limit))
    ).all()
    total_stmt = (
        select(func.count())
        .select_from(UnknownFace)
        .where(*_unknown_filters(review_status, camera_id, date_from, date_to))
    )
    return list(rows), int(await db.scalar(total_stmt) or 0)


async def unknown_for_update(db: AsyncSession, unknown_ids: list[int]) -> list[UnknownFace]:
    """Locks the given unknown faces in id order (one order for every writer, so no deadlocks)."""
    if not unknown_ids:
        return []
    stmt = (
        select(UnknownFace)
        .where(UnknownFace.id.in_(unknown_ids))
        .order_by(UnknownFace.id)
        .with_for_update(of=UnknownFace)
    )
    return list((await db.scalars(stmt)).all())


async def unknown_before(db: AsyncSession, cutoff: datetime, limit: int) -> list[UnknownFace]:
    stmt = select(UnknownFace).where(UnknownFace.captured_at < cutoff).limit(limit)
    return list((await db.scalars(stmt)).all())


async def unknown_assigned_to(db: AsyncSession, employee_id: int) -> list[UnknownFace]:
    stmt = select(UnknownFace).where(UnknownFace.assigned_employee_id == employee_id)
    return list((await db.scalars(stmt)).all())
