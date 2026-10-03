"""Camera health from engine status (FR-3, FR-4)."""

from datetime import UTC, datetime, timedelta

from conftest import make_camera, make_org
from facetrack_common.constants import CameraMode, CameraRole, CameraStatus
from facetrack_common.models import Camera
from facetrack_common.schemas.engine import CameraRuntimeStatus
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import get_async_redis
from app.domain.cameras import status as camera_status


def _runtime(camera_id: int, connected: bool) -> CameraRuntimeStatus:
    return CameraRuntimeStatus(
        camera_id=camera_id,
        name="x",
        role=CameraRole.ENTRY,
        mode=CameraMode.ACTIVE,
        connected=connected,
        fps_target=4,
        fps_actual=3.8,
        last_frame_at=datetime.now(UTC),
        lag_seconds=0.05,
        faces_today=3,
        restarts=0,
        last_error=None if connected else "OSError: Connection refused",
        process_alive=True,
    )


async def test_fr3_online_offline_and_runtime_cache(db: AsyncSession) -> None:
    org = await make_org(db)
    online = await make_camera(db, org, "A", CameraRole.ENTRY)
    offline = await make_camera(db, org, "B", CameraRole.EXIT)
    went = await camera_status.apply_node_status(
        db, "node-1", [_runtime(online.id, True), _runtime(offline.id, False)], 2
    )
    assert [c.id for c in went] == [offline.id]
    await db.refresh(online)
    await db.refresh(offline)
    assert online.status == CameraStatus.ONLINE and online.offline_since is None
    assert offline.status == CameraStatus.OFFLINE and offline.offline_since is not None
    assert await get_async_redis().get("engine_load:node-1") == "2"
    assert await get_async_redis().get(f"camera_runtime:{online.id}") is not None


async def test_fr4_unreachable_node_marks_cameras_offline_and_alert_after_delay(db: AsyncSession) -> None:
    org = await make_org(db)
    camera = await make_camera(db, org, "A", CameraRole.ENTRY)
    await camera_status.apply_node_status(db, "node-1", None, None)
    assert await camera_status.offline_longer_than(db, 5) == []  # just went offline
    stored = await db.get(Camera, camera.id)
    assert stored is not None
    stored.offline_since = datetime.now(UTC) - timedelta(minutes=6)
    await db.commit()
    assert [c.id for c in await camera_status.offline_longer_than(db, 5)] == [camera.id]
    # Back online clears the outage.
    await camera_status.apply_node_status(db, "node-1", [_runtime(camera.id, True)], 1)
    await db.refresh(stored)
    assert stored.offline_since is None and stored.status == CameraStatus.ONLINE


async def test_disabled_camera_is_reported_disabled(db: AsyncSession) -> None:
    org = await make_org(db)
    camera = await make_camera(db, org, "A", CameraRole.ENTRY)
    camera.is_enabled = False
    await db.commit()
    await camera_status.apply_node_status(db, "node-1", [], 1)
    await db.refresh(camera)
    assert camera.status == CameraStatus.DISABLED
