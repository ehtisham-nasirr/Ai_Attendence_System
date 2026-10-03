"""Recognition events and unknown faces."""

import uuid
from datetime import datetime
from typing import Any

from facetrack_common.constants import RecognitionStatus, ReviewStatus
from facetrack_common.models import Camera, RecognitionEventRecord, UnknownFace
from sqlalchemy import and_, func, select, update
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
    stmt = select(UnknownFace).options(selectinload(UnknownFace.camera))
    if review_status:
        stmt = stmt.where(UnknownFace.review_status == review_status)
    if camera_id:
        stmt = stmt.where(UnknownFace.camera_id == camera_id)
    if date_from:
        stmt = stmt.where(UnknownFace.captured_at >= date_from)
    if date_to:
        stmt = stmt.where(UnknownFace.captured_at < date_to)
    sort = apply_sort(
        stmt, params.sort or "-captured_at", {"captured_at": UnknownFace.captured_at}, UnknownFace.id
    )
    return await fetch_page(db, sort, params)


async def unknown_before(db: AsyncSession, cutoff: datetime, limit: int) -> list[UnknownFace]:
    stmt = select(UnknownFace).where(UnknownFace.captured_at < cutoff).limit(limit)
    return list((await db.scalars(stmt)).all())


async def unknown_assigned_to(db: AsyncSession, employee_id: int) -> list[UnknownFace]:
    stmt = select(UnknownFace).where(UnknownFace.assigned_employee_id == employee_id)
    return list((await db.scalars(stmt)).all())
