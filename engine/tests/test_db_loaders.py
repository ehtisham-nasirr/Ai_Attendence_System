"""Gallery and camera loading from a real PostgreSQL (FR-13, FR-19). Skipped without TEST_DATABASE_URL.

Uses throw-away tables created from the shared models; the backend's Alembic migrations are tested
in the backend suite.
"""

import os
from collections.abc import AsyncIterator
from datetime import time

import numpy as np
import pytest
from facetrack_common.constants import (
    CRYPTO_PURPOSE_CAMERA_URL,
    CRYPTO_PURPOSE_EMBEDDING,
    CameraRole,
    EmployeeStatus,
    EnrollmentSource,
)
from facetrack_common.crypto import Cipher
from facetrack_common.models import Base, Camera, Employee, FaceEnrollment, Location, Setting, Shift
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.gallery.loader import load_gallery
from app.models.base import l2_normalise
from app.scheduler.camera_config import load_camera_configs

DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL not set")


@pytest.fixture
async def sessions() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    assert DATABASE_URL is not None
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


async def _seed(sessions: async_sessionmaker[AsyncSession], cipher: Cipher) -> None:
    rng = np.random.default_rng(0)
    async with sessions() as session, session.begin():
        location = Location(name="HQ", timezone="Asia/Karachi")
        shift = Shift(name="Day", start_time=time(9), end_time=time(18), weekly_offs=[6, 7])
        session.add_all([location, shift])
        await session.flush()
        for code, status, deleted in (
            ("E1", EmployeeStatus.ACTIVE, False),
            ("E2", EmployeeStatus.INACTIVE, False),
            ("E3", EmployeeStatus.ACTIVE, True),
        ):
            employee = Employee(
                employee_code=code, full_name=code, status=status, shift_id=shift.id, location_id=location.id
            )
            if deleted:
                from datetime import UTC, datetime

                employee.deleted_at = datetime.now(UTC)
            session.add(employee)
            await session.flush()
            for model, dim in (("sface", 128), ("arcface_r50", 512)):
                vector = l2_normalise(rng.standard_normal((1, dim)).astype(np.float32))[0]
                session.add(
                    FaceEnrollment(
                        employee_id=employee.id,
                        image_path=f"enroll/{code}.jpg",
                        model_name=model,
                        embedding_dim=dim,
                        embedding_encrypted=cipher.encrypt_embedding(vector, CRYPTO_PURPOSE_EMBEDDING),
                        quality_score=0.9,
                        source=EnrollmentSource.UPLOAD,
                        is_active=True,
                    )
                )
        for name, node, enabled in (
            ("Entrance", "node-1", True),
            ("Other node", "node-2", True),
            ("Disabled", "node-1", False),
        ):
            session.add(
                Camera(
                    location_id=location.id,
                    name=name,
                    engine_node=node,
                    role=CameraRole.ENTRY,
                    is_enabled=enabled,
                    rtsp_url_encrypted=cipher.encrypt_str("rtsp://u:p@cam/1", CRYPTO_PURPOSE_CAMERA_URL),
                )
            )
        session.add(Setting(key="recognition.margin", value=0.1))


async def test_fr13_fr19_gallery_has_only_active_employees_of_the_current_model(
    sessions: async_sessionmaker[AsyncSession], cipher: Cipher
) -> None:
    await _seed(sessions, cipher)
    snapshot = await load_gallery(sessions, cipher, "sface", 128, version=5)
    assert snapshot.employee_codes == ["E1"]
    assert snapshot.vectors.shape == (1, 128) and snapshot.version == 5
    arcface = await load_gallery(sessions, cipher, "arcface_r50", 512, version=6)
    assert arcface.vectors.shape == (1, 512)


async def test_cameras_for_this_node_only_with_settings_applied(
    sessions: async_sessionmaker[AsyncSession], cipher: Cipher
) -> None:
    await _seed(sessions, cipher)
    configs, refused = await load_camera_configs(
        sessions, cipher, "node-1", "sface", liveness_available=False
    )
    assert [c.name for c in configs] == ["Entrance"] and refused == {}
    assert configs[0].margin == 0.1 and configs[0].timezone == "Asia/Karachi"
    assert configs[0].main_url == "rtsp://u:p@cam/1"
