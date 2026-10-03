"""Camera health from the engines (FR-3, FR-4): online/offline, last seen, runtime mode/FPS."""

import json
import logging
from datetime import UTC, datetime

from facetrack_common.constants import CameraStatus
from facetrack_common.models import Camera
from facetrack_common.schemas.engine import CameraRuntimeStatus
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import transaction
from app.core.redis import get_async_redis
from app.domain.cameras.service import RUNTIME_KEY
from app.domain.dashboard.service import LOAD_KEY

logger = logging.getLogger(__name__)
_RUNTIME_TTL_S = 120


async def apply_node_status(
    db: AsyncSession, node: str, statuses: list[CameraRuntimeStatus] | None, load_level: int | None
) -> list[Camera]:
    """Updates cameras of one engine node; `statuses=None` means the node is unreachable.

    Returns cameras that just went offline (for alerts).
    """
    now = datetime.now(UTC)
    redis = get_async_redis()
    by_id = {s.camera_id: s for s in statuses or []}
    went_offline: list[Camera] = []
    async with transaction(db):
        cameras = (
            await db.scalars(
                select(Camera)
                .where(Camera.engine_node == node, Camera.deleted_at.is_(None))
                .with_for_update()
            )
        ).all()
        for camera in cameras:
            if not camera.is_enabled:
                camera.status = CameraStatus.DISABLED
                camera.offline_since = None
                continue
            status = by_id.get(camera.id)
            online = status is not None and status.connected and status.process_alive
            if online and status is not None:
                camera.status = CameraStatus.ONLINE
                camera.last_seen_at = status.last_frame_at or now
                camera.offline_since = None
            else:
                if camera.status != CameraStatus.OFFLINE:
                    went_offline.append(camera)
                camera.status = CameraStatus.OFFLINE
                camera.offline_since = camera.offline_since or now
            if status is not None:
                runtime = {
                    "mode": status.mode.value,
                    "connected": status.connected,
                    "fps_target": status.fps_target,
                    "fps_actual": status.fps_actual,
                    "lag_seconds": status.lag_seconds,
                    "faces_today": status.faces_today,
                    "last_error": status.last_error,
                    "updated_at": now.isoformat(),
                }
                await redis.set(
                    RUNTIME_KEY.format(camera_id=camera.id), json.dumps(runtime), ex=_RUNTIME_TTL_S
                )
    if load_level is not None:
        await redis.set(LOAD_KEY.format(node=node), load_level, ex=_RUNTIME_TTL_S)
    return went_offline


async def offline_longer_than(db: AsyncSession, minutes: int) -> list[Camera]:
    cutoff = datetime.now(UTC).timestamp() - minutes * 60
    cameras = (
        await db.scalars(
            select(Camera).where(
                Camera.status == CameraStatus.OFFLINE,
                Camera.offline_since.is_not(None),
                Camera.deleted_at.is_(None),
            )
        )
    ).all()
    return [c for c in cameras if c.offline_since is not None and c.offline_since.timestamp() <= cutoff]
