"""Cameras (FR-1..FR-6): CRUD with encrypted stream URLs, connection test, live-view token.

Every change tells the engines to re-sync their cameras and updates the MediaMTX live-view path.
"""

import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

import jwt
from facetrack_common.constants import CRYPTO_PURPOSE_CAMERA_URL, CameraStatus
from facetrack_common.models import Camera, Location, User
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.crypto import get_cipher
from app.core.db import transaction
from app.core.exceptions import Conflict, NotFound, ValidationFailed
from app.core.redis import get_async_redis
from app.domain.audit import service as audit
from app.repositories import camera_repo
from app.repositories.base import apply_changes, get_live, soft_delete
from app.schemas.camera import (
    CameraCreate,
    CameraLiveOut,
    CameraOut,
    CameraRuntimeOut,
    CameraTestOut,
    CameraUpdate,
)
from app.services import engine_client, mediamtx

RUNTIME_KEY = "camera_runtime:{camera_id}"


def stream_host(url: str) -> str:
    """Host and port only — credentials and paths are never shown (standards/06)."""
    parts = urlsplit(url)
    return parts.hostname + (f":{parts.port}" if parts.port else "") if parts.hostname else parts.scheme


async def to_out(cameras: list[Camera]) -> list[CameraOut]:
    cipher = get_cipher()
    redis = get_async_redis()
    keys = [RUNTIME_KEY.format(camera_id=c.id) for c in cameras]
    runtimes = await redis.mget(keys) if keys else []
    result = []
    for camera, raw in zip(cameras, runtimes, strict=True):
        url = cipher.decrypt_str(camera.rtsp_url_encrypted, CRYPTO_PURPOSE_CAMERA_URL)
        result.append(
            CameraOut(
                id=camera.id,
                name=camera.name,
                location_id=camera.location_id,
                role=camera.role,
                stream_host=stream_host(url),
                has_substream=camera.substream_url_encrypted is not None,
                engine_node=camera.engine_node,
                priority=camera.priority,
                operating_hours=camera.operating_hours,
                roi_polygon=camera.roi_polygon,
                fps=camera.fps,
                match_threshold=camera.match_threshold,
                liveness_enabled=camera.liveness_enabled,
                is_enabled=camera.is_enabled,
                status=camera.status,
                last_seen_at=camera.last_seen_at,
                created_at=camera.created_at,
                runtime=CameraRuntimeOut.model_validate(json.loads(raw)) if raw else None,
            )
        )
    return result


def _check_url(url: str | None, field: str) -> None:
    if url and url.startswith("file://") and get_settings().environment != "development":
        raise ValidationFailed(errors={field: ["File sources are only allowed in development."]})


async def _check_engine_node(node: str) -> None:
    if node not in get_settings().engine_nodes:
        raise ValidationFailed(
            errors={"engine_node": [f"Unknown engine node. Known: {sorted(get_settings().engine_nodes)}"]}
        )


async def _sync_live_path(camera: Camera) -> None:
    cipher = get_cipher()
    token = camera.substream_url_encrypted or camera.rtsp_url_encrypted
    await mediamtx.upsert_path(camera.id, cipher.decrypt_str(token, CRYPTO_PURPOSE_CAMERA_URL))


async def sync_live_paths(db: AsyncSession) -> int:
    """Re-applies every camera's live-view path; MediaMTX keeps API-added paths only in memory, so this
    restores them after a MediaMTX restart. Returns the number of paths accepted."""
    cameras = await camera_repo.all_cameras(db)
    applied = 0
    for camera in cameras:
        if camera.deleted_at is None:
            await _sync_live_path(camera)
            applied += 1
    return applied


async def create_camera(db: AsyncSession, payload: CameraCreate, actor: User) -> Camera:
    _check_url(payload.rtsp_url, "rtsp_url")
    _check_url(payload.substream_url, "substream_url")
    await _check_engine_node(payload.engine_node)
    cipher = get_cipher()
    async with transaction(db):
        if await get_live(db, Location, payload.location_id) is None:
            raise ValidationFailed(errors={"location_id": ["Location not found."]})
        if await camera_repo.name_taken(db, payload.name):
            raise Conflict("A camera with this name already exists.")
        data = payload.model_dump(exclude={"rtsp_url", "substream_url"})
        camera = Camera(
            **data,
            rtsp_url_encrypted=cipher.encrypt_str(payload.rtsp_url, CRYPTO_PURPOSE_CAMERA_URL),
            substream_url_encrypted=(
                cipher.encrypt_str(payload.substream_url, CRYPTO_PURPOSE_CAMERA_URL)
                if payload.substream_url
                else None
            ),
            status=CameraStatus.UNKNOWN if payload.is_enabled else CameraStatus.DISABLED,
        )
        db.add(camera)
        await db.flush()
        await audit.record(db, actor, "camera.create", "camera", camera.id, new=data)
    await engine_client.notify_engines("cameras_sync")
    await _sync_live_path(camera)
    return camera


async def update_camera(db: AsyncSession, camera_id: int, payload: CameraUpdate, actor: User) -> Camera:
    _check_url(payload.rtsp_url, "rtsp_url")
    _check_url(payload.substream_url, "substream_url")
    if payload.engine_node:
        await _check_engine_node(payload.engine_node)
    cipher = get_cipher()
    async with transaction(db):
        camera = await get_live(db, Camera, camera_id, for_update=True)
        if camera is None:
            raise NotFound("Camera not found.")
        changes: dict[str, Any] = payload.model_dump(
            exclude_unset=True, exclude={"rtsp_url", "substream_url", "clear_substream", "clear_roi"}
        )
        if "name" in changes and await camera_repo.name_taken(db, changes["name"], camera_id):
            raise Conflict("A camera with this name already exists.")
        if "location_id" in changes and await get_live(db, Location, changes["location_id"]) is None:
            raise ValidationFailed(errors={"location_id": ["Location not found."]})
        if payload.clear_roi:
            changes["roi_polygon"] = None
        old = apply_changes(camera, changes)
        if payload.rtsp_url:
            camera.rtsp_url_encrypted = cipher.encrypt_str(payload.rtsp_url, CRYPTO_PURPOSE_CAMERA_URL)
            old["rtsp_url"] = "[changed]"
        if payload.substream_url:
            camera.substream_url_encrypted = cipher.encrypt_str(
                payload.substream_url, CRYPTO_PURPOSE_CAMERA_URL
            )
            old["substream_url"] = "[changed]"
        elif payload.clear_substream:
            camera.substream_url_encrypted = None
            old["substream_url"] = "[removed]"
        if "is_enabled" in changes:
            camera.status = CameraStatus.UNKNOWN if camera.is_enabled else CameraStatus.DISABLED
        await audit.record(db, actor, "camera.update", "camera", camera_id, old=old, new=changes)
    await engine_client.notify_engines("cameras_sync")
    await _sync_live_path(camera)
    return camera


async def delete_camera(db: AsyncSession, camera_id: int, actor: User) -> None:
    async with transaction(db):
        camera = await get_live(db, Camera, camera_id, for_update=True)
        if camera is None:
            raise NotFound("Camera not found.")
        soft_delete(camera)
        camera.is_enabled = False
        await audit.record(db, actor, "camera.delete", "camera", camera_id)
    await engine_client.notify_engines("cameras_sync")
    await mediamtx.delete_path(camera_id)


async def test_camera(db: AsyncSession, camera_id: int, use_substream: bool, actor: User) -> CameraTestOut:
    """FR-2: connection test with a live snapshot, through the camera's engine node."""
    camera = await get_live(db, Camera, camera_id)
    if camera is None:
        raise NotFound("Camera not found.")
    result = await engine_client.test_camera(camera.id, camera.engine_node, use_substream)
    async with transaction(db):
        locked = await get_live(db, Camera, camera_id, for_update=True)
        if locked is not None and result.ok:
            locked.last_seen_at = datetime.now(UTC)
        await audit.record(db, actor, "camera.test", "camera", camera_id, new={"ok": result.ok})
    return CameraTestOut.model_validate(result.model_dump())


async def live_view(db: AsyncSession, camera_id: int, actor: User) -> CameraLiveOut:
    """Short-lived token bound to one camera path; MediaMTX checks it with /internal/mediamtx/auth."""
    camera = await get_live(db, Camera, camera_id)
    if camera is None:
        raise NotFound("Camera not found.")
    settings = get_settings()
    expires = datetime.now(UTC) + timedelta(seconds=settings.live_token_seconds)
    token = jwt.encode(
        {
            "typ": "live",
            "sub": str(actor.id),
            "path": mediamtx.path_name(camera.id),
            "exp": int(expires.timestamp()),
            "jti": secrets.token_hex(8),
        },
        settings.jwt_secret.get_secret_value(),
        settings.jwt_algorithm,
    )
    base = settings.mediamtx_webrtc_public_path.rstrip("/")
    return CameraLiveOut(
        webrtc_url=f"{base}/{mediamtx.path_name(camera.id)}/whep", token=token, expires_at=expires
    )


def verify_live_token(token: str, path: str) -> bool:
    settings = get_settings()
    try:
        claims = jwt.decode(
            token, settings.jwt_secret.get_secret_value(), algorithms=[settings.jwt_algorithm]
        )
    except jwt.PyJWTError:
        return False
    return claims.get("typ") == "live" and claims.get("path") == path
