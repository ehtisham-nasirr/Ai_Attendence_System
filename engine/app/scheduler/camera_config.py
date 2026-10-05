"""Per-camera runtime configuration: the camera row plus the recognition/engine settings it uses.

Built from the database on `/cameras/sync`; a camera process is restarted when its config changes.
Decrypted stream URLs exist only in memory and are never logged or returned by the API.
"""

import hashlib
import json
import logging
from dataclasses import asdict, dataclass
from typing import Any

from facetrack_common.constants import CRYPTO_PURPOSE_CAMERA_URL, ENTRANCE_CAMERA_ROLES, CameraRole
from facetrack_common.crypto import Cipher
from facetrack_common.models import Camera, Setting
from facetrack_common.settings_keys import resolve_settings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)


class CameraConfigError(Exception):
    """The camera cannot run safely with the current configuration."""


@dataclass(frozen=True)
class CameraRuntimeConfig:
    camera_id: int
    name: str
    role: CameraRole
    timezone: str
    main_url: str
    substream_url: str | None
    roi_polygon: list[list[float]] | None
    camera_fps: float | None
    operating_hours: list[dict[str, Any]] | None
    model_name: str
    match_threshold: float
    margin: float
    min_votes: int
    best_crops: int
    detector_min_score: float
    min_face_width_px: int
    min_crop_quality: float
    min_blur_variance: float
    embed_after_s: float
    track_lost_s: float
    liveness_required: bool
    liveness_spoof_threshold: float
    entrance_fps: float
    general_fps: float
    cooldown_fps: float
    cooldown_enter_s: float
    cooldown_idle_s: float
    motion_min_area_ratio: float
    peak_windows: list[dict[str, str]]
    conflict_gap: float = 0.15

    @property
    def is_entrance(self) -> bool:
        return self.role in ENTRANCE_CAMERA_ROLES

    def fingerprint(self) -> str:
        """Hash of everything that affects processing; a change restarts the camera process."""
        payload = json.dumps(asdict(self), sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()


def build_runtime_config(
    camera: Camera,
    timezone: str,
    settings: dict[str, Any],
    cipher: Cipher,
    model_name: str,
    liveness_available: bool,
) -> CameraRuntimeConfig:
    thresholds: dict[str, float] = settings["recognition.match_thresholds"]
    threshold = camera.match_threshold if camera.match_threshold is not None else thresholds.get(model_name)
    if threshold is None:
        # No safe default exists for an unconfigured model; refuse rather than guess (NFR-2).
        raise CameraConfigError(f"no match threshold configured for model '{model_name}'")
    liveness_required = camera.liveness_enabled and camera.role in ENTRANCE_CAMERA_ROLES
    if liveness_required and not liveness_available:
        raise CameraConfigError("liveness is enabled for this camera but no liveness model is installed")
    substream = (
        cipher.decrypt_str(camera.substream_url_encrypted, CRYPTO_PURPOSE_CAMERA_URL)
        if camera.substream_url_encrypted
        else None
    )
    return CameraRuntimeConfig(
        camera_id=camera.id,
        name=camera.name,
        role=camera.role,
        timezone=timezone,
        main_url=cipher.decrypt_str(camera.rtsp_url_encrypted, CRYPTO_PURPOSE_CAMERA_URL),
        substream_url=substream,
        roi_polygon=camera.roi_polygon,
        camera_fps=camera.fps,
        operating_hours=camera.operating_hours,
        model_name=model_name,
        match_threshold=float(threshold),
        margin=float(settings["recognition.margin"]),
        conflict_gap=float(settings["recognition.conflict_gap"]),
        min_votes=int(settings["recognition.min_votes"]),
        best_crops=int(settings["recognition.best_crops"]),
        detector_min_score=float(settings["recognition.detector_min_score"]),
        min_face_width_px=int(settings["recognition.min_face_width_px"]),
        min_crop_quality=float(settings["recognition.min_crop_quality"]),
        min_blur_variance=float(settings["recognition.min_blur_variance"]),
        embed_after_s=float(settings["recognition.embed_after_s"]),
        track_lost_s=float(settings["recognition.track_lost_s"]),
        liveness_required=liveness_required,
        liveness_spoof_threshold=float(settings["recognition.liveness_spoof_threshold"]),
        entrance_fps=float(settings["engine.entrance_fps"]),
        general_fps=float(settings["engine.general_fps"]),
        cooldown_fps=float(settings["engine.cooldown_fps"]),
        cooldown_enter_s=float(settings["engine.cooldown_enter_s"]),
        cooldown_idle_s=float(settings["engine.cooldown_idle_s"]),
        motion_min_area_ratio=float(settings["engine.motion_min_area_ratio"]),
        peak_windows=list(settings["engine.peak_windows"]),
    )


async def load_settings(sessions: async_sessionmaker[AsyncSession]) -> dict[str, Any]:
    async with sessions() as session:
        rows = (await session.execute(select(Setting.key, Setting.value))).all()
    return resolve_settings({key: value for key, value in rows})


async def load_camera_configs(
    sessions: async_sessionmaker[AsyncSession],
    cipher: Cipher,
    node: str,
    model_name: str,
    liveness_available: bool,
) -> tuple[list[CameraRuntimeConfig], dict[int, str]]:
    """Enabled cameras assigned to this node; returns (configs, {camera_id: error}) for refused ones."""
    settings = await load_settings(sessions)
    stmt = (
        select(Camera)
        .options(selectinload(Camera.location))
        .where(Camera.engine_node == node, Camera.is_enabled.is_(True), Camera.deleted_at.is_(None))
        .order_by(Camera.priority.desc(), Camera.id)
    )
    async with sessions() as session:
        cameras = (await session.scalars(stmt)).all()
    configs, errors = [], {}
    for camera in cameras:
        try:
            configs.append(
                build_runtime_config(
                    camera, camera.location.timezone, settings, cipher, model_name, liveness_available
                )
            )
        except CameraConfigError as exc:
            errors[camera.id] = str(exc)
            logger.error("camera refused", extra={"camera_id": camera.id, "error": str(exc)})
    return configs, errors
