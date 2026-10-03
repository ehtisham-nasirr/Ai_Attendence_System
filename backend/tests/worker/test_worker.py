"""Event consumer, dead-lettering, Celery task idempotency, import, retention, partitions (standards/02, 11)."""

import asyncio
import io
import os
import uuid
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from conftest import make_camera, make_employee, make_org, make_user
from facetrack_common.constants import (
    RECOGNITION_EVENTS_DEAD_LETTER_STREAM,
    RECOGNITION_EVENTS_STREAM,
    CameraRole,
    EmployeeStatus,
    UserRole,
)
from facetrack_common.events import RecognitionEvent
from facetrack_common.models import Employee, FaceEnrollment, RecognitionEventRecord, UnknownFace
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import get_sync_redis
from app.domain.employees import importer
from app.domain.retention import service as retention
from app.worker import runtime
from app.worker.consumer import GROUP, EventStreamConsumer, ensure_group
from app.worker.tasks import events as event_tasks
from app.worker.tasks import maintenance


@pytest.fixture(autouse=True)
def fresh_runtime() -> None:
    runtime.reset_for_tests()


def _fields(camera_id: int, code: str = "E1") -> dict[str, str]:
    return RecognitionEvent.model_validate(
        {
            "event_id": str(uuid.uuid4()),
            "camera_id": camera_id,
            "employee_code": code,
            "status": "recognized",
            "confidence": 0.7,
            "track_id": 1,
            "captured_at": datetime.now(UTC).isoformat(),
            "model_name": "sface",
            "engine_node": "node-1",
        }
    ).to_stream_fields()


async def test_consumer_dispatches_and_task_acks_after_commit(db: AsyncSession) -> None:
    org = await make_org(db)
    await make_employee(db, org, "E1")
    camera = await make_camera(db, org, "Entrance", CameraRole.ENTRY)
    redis = get_sync_redis()
    redis.xadd(RECOGNITION_EVENTS_STREAM, _fields(camera.id))
    redis.xadd(RECOGNITION_EVENTS_STREAM, {"payload": "{not json"})
    ensure_group(redis)
    dispatched: list[tuple[str, dict[str, str]]] = []
    consumer = EventStreamConsumer(
        dispatch=lambda message_id, fields: dispatched.append((message_id, fields))
    )
    assert consumer.poll_once(redis) == 2
    assert redis.xpending(RECOGNITION_EVENTS_STREAM, GROUP)["pending"] == 2
    results = [
        await asyncio.to_thread(event_tasks.process_event.run, mid, fields) for mid, fields in dispatched
    ]
    assert results == ["stored", "dead-lettered"]
    assert redis.xpending(RECOGNITION_EVENTS_STREAM, GROUP)["pending"] == 0
    assert redis.xlen(RECOGNITION_EVENTS_DEAD_LETTER_STREAM) == 1
    # Redelivery of an already-processed message is harmless (idempotent).
    assert await asyncio.to_thread(event_tasks.process_event.run, *dispatched[0]) == "duplicate"
    assert await db.scalar(select(func.count()).select_from(RecognitionEventRecord)) == 1


async def test_unknown_employee_is_dead_lettered(db: AsyncSession) -> None:
    org = await make_org(db)
    camera = await make_camera(db, org, "Entrance", CameraRole.ENTRY)
    redis = get_sync_redis()
    message_id = redis.xadd(RECOGNITION_EVENTS_STREAM, _fields(camera.id, "GHOST"))
    ensure_group(redis)
    EventStreamConsumer(dispatch=lambda *_: None).poll_once(redis)
    result = await asyncio.to_thread(event_tasks.process_event.run, message_id, _fields(camera.id, "GHOST"))
    assert result == "dead-lettered"


async def test_partitions_are_created_ahead() -> None:
    created = await asyncio.to_thread(maintenance.ensure_event_partitions.run)
    assert created >= 0
    assert await asyncio.to_thread(maintenance.ensure_event_partitions.run) == 0  # idempotent


def _xlsx(rows: list[list[str]]) -> bytes:
    from openpyxl import Workbook

    workbook = Workbook()
    for row in rows:
        workbook.active.append(row)
    out = io.BytesIO()
    workbook.save(out)
    return out.getvalue()


async def test_fr11_import_upserts_rows_and_reports_errors(db: AsyncSession, tmp_path: Path) -> None:
    org = await make_org(db)
    actor = await make_user(db, UserRole.HR_ADMIN, "hr")
    sheet = tmp_path / "e.xlsx"
    sheet.write_bytes(
        _xlsx(
            [
                ["Employee Code", "Full Name", "Department Code", "Shift", "Location", "Consent Signed At"],
                ["E-1", "Ali", "SAL", "Day", "HQ", "2026-09-01T09:00:00+05:00"],
                ["E-2", "Sara", "XXX", "Day", "HQ", ""],
                ["bad code!", "Bad", "", "", "", ""],
            ]
        )
    )
    from PIL import Image

    photo = io.BytesIO()
    Image.new("RGB", (300, 300), (100, 100, 100)).save(photo, format="JPEG")
    archive = tmp_path / "p.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("E-1/1.jpg", photo.getvalue())
        zf.writestr("NOBODY_1.jpg", photo.getvalue())
    report = await importer.import_employees(db, sheet, archive, actor)
    assert report["created"] == 1 and report["photos_accepted"] == 1
    messages = " ".join(e["message"] for e in report["errors"])
    assert "unknown department_code" in messages and "employee_code" in messages and "no employee" in messages
    assert (
        org["sales"].id
        == (await db.scalars(select(Employee.department_id).where(Employee.employee_code == "E-1"))).one()
    )


def test_zip_with_path_traversal_or_nesting_is_refused(tmp_path: Path) -> None:
    for name in ("../evil.jpg", "inner.zip"):
        archive = tmp_path / f"{uuid.uuid4().hex}.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr(name, b"x")
        with pytest.raises(ValueError):
            importer.safe_zip_photos(archive, 100)


async def test_fr39_retention_deletes_expired_biometric_data(db: AsyncSession) -> None:
    from app.services import storage

    org = await make_org(db)
    leaver = await make_employee(db, org, "L1")
    camera = await make_camera(db, org, "Entrance", CameraRole.ENTRY)
    old = datetime.now(UTC) - timedelta(days=120)
    storage.put_encrypted("snapshots/old.jpg", b"jpeg")
    db.add(
        RecognitionEventRecord(
            event_uuid=uuid.uuid4(),
            camera_id=camera.id,
            status="unknown",
            confidence=0.1,
            track_id=1,
            snapshot_path="snapshots/old.jpg",
            captured_at=old,
            model_name="sface",
            engine_node="node-1",
        )
    )
    db.add(
        UnknownFace(
            recognition_event_id=1,
            captured_at=old,
            camera_id=camera.id,
            model_name="sface",
            snapshot_path="snapshots/old.jpg",
        )
    )
    leaver.status = EmployeeStatus.INACTIVE
    leaver.deactivated_at = datetime.now(UTC) - timedelta(days=45)
    db.add(
        FaceEnrollment(
            employee_id=leaver.id,
            image_path="enroll/x.jpg",
            embedding_encrypted=b"x",
            embedding_dim=128,
            model_name="sface",
            quality_score=0.9,
            source="upload",
        )
    )
    await db.commit()
    counts = await retention.apply_retention(db)
    assert counts == {"event_snapshots": 1, "unknown_faces": 1, "leaver_enrollments": 1}
    assert await db.scalar(select(func.count()).select_from(UnknownFace)) == 0
    assert await db.scalar(select(func.count()).select_from(FaceEnrollment)) == 0
    assert not (Path(os.environ["MEDIA_ROOT"]) / "snapshots/old.jpg").exists()
    assert await retention.apply_retention(db) == {
        "event_snapshots": 0,
        "unknown_faces": 0,
        "leaver_enrollments": 0,
    }


async def test_migration_downgrade_and_upgrade_round_trip() -> None:
    from alembic.config import Config
    from conftest import DATABASE_URL, _run_migrations

    from alembic import command

    config = Config(os.path.join(os.path.dirname(__file__), "..", "..", "alembic.ini"))
    config.attributes["database_url"] = DATABASE_URL
    # Alembic's env runs its own event loop, so it runs in a worker thread like the real CLI.
    await asyncio.to_thread(command.downgrade, config, "base")
    await asyncio.to_thread(_run_migrations)
    from app.core.db import get_engine

    async with get_engine().connect() as conn:
        tables = await conn.scalar(
            text(
                "select count(*) from pg_tables where schemaname='public' "
                "and tablename not like 'recognition_events_%' and tablename<>'alembic_version'"
            )
        )
    assert tables == 16
