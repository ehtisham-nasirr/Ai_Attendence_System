"""Retention (FR-39, §15): hard-deletes expired snapshots, unknown faces and leavers' enrollment data.

Periods come from the `settings` table. Every run writes one audit entry with counts only.
"""

import logging
from datetime import UTC, datetime, timedelta

from facetrack_common.constants import EmployeeStatus
from facetrack_common.models import Employee, FaceEnrollment
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import transaction
from app.domain.audit import service as audit
from app.domain.employees.service import erase_biometrics
from app.domain.settings import service as settings_service
from app.repositories import event_repo
from app.services import storage

logger = logging.getLogger(__name__)
_BATCH = 500


async def apply_retention(db: AsyncSession, now: datetime | None = None) -> dict[str, int]:
    now = now or datetime.now(UTC)
    values = await settings_service.resolved(db)
    counts = {"event_snapshots": 0, "unknown_faces": 0, "leaver_enrollments": 0}

    snapshot_cutoff = now - timedelta(days=int(values["retention.snapshot_days"]))
    while True:
        rows = await event_repo.events_with_snapshots_before(db, snapshot_cutoff, _BATCH)
        if not rows:
            break
        paths = [path for _, _, path in rows]
        async with transaction(db):
            await event_repo.clear_snapshot_paths(db, paths)
        storage.delete_quietly(paths)
        counts["event_snapshots"] += len(paths)

    unknown_cutoff = now - timedelta(days=int(values["retention.unknown_face_days"]))
    while True:
        faces = await event_repo.unknown_before(db, unknown_cutoff, _BATCH)
        if not faces:
            break
        async with transaction(db):
            for face in faces:
                await db.delete(face)
        storage.delete_quietly([f.snapshot_path for f in faces if f.snapshot_path])
        counts["unknown_faces"] += len(faces)

    exit_cutoff = now - timedelta(days=int(values["retention.enrollment_after_exit_days"]))
    leavers = (
        await db.scalars(
            select(Employee).where(
                Employee.status == EmployeeStatus.INACTIVE,
                Employee.deactivated_at.is_not(None),
                Employee.deactivated_at < exit_cutoff,
                select(FaceEnrollment.id).where(FaceEnrollment.employee_id == Employee.id).exists(),
            )
        )
    ).all()
    for employee in leavers:
        async with transaction(db):
            erased = await erase_biometrics(db, employee, None, reason="retention: employee left")
        counts["leaver_enrollments"] += erased["enrollments"]

    if any(counts.values()):
        async with transaction(db):
            await audit.record(db, None, "retention.delete", "retention", None, new=counts)
        logger.info("retention applied", extra=counts)
    return counts
