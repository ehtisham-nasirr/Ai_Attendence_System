"""Contracts of the internal engine API (requirements §12.2), used by the engine and the backend client."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from facetrack_common.constants import CameraMode, CameraRole, LoadLevel

EnrollmentRejection = Literal[
    "invalid_image", "no_face", "multiple_faces", "face_too_small", "low_quality", "blurred"
]


class EmbedResult(BaseModel):
    """`POST /embed` result: FR-9 photo validation plus the encrypted embedding when accepted."""

    accepted: bool
    rejection_reason: EnrollmentRejection | None = None
    face_count: int = Field(ge=0)
    face_width_px: int | None = None
    detector_score: float | None = None
    quality_score: float | None = None
    blur_variance: float | None = None
    model_name: str
    embedding_dim: int | None = None
    # AES-256-GCM ciphertext (base64) with purpose CRYPTO_PURPOSE_EMBEDDING; None when rejected.
    embedding_encrypted: str | None = None


class GalleryReloadResult(BaseModel):
    model_name: str
    employees: int = Field(ge=0)
    embeddings: int = Field(ge=0)
    version: int = Field(ge=0)


class CameraSyncResult(BaseModel):
    started: list[int]
    stopped: list[int]
    restarted: list[int]
    unchanged: list[int]


class CameraTestRequest(BaseModel):
    camera_id: int = Field(gt=0)
    use_substream: bool = False


class CameraTestResult(BaseModel):
    """FR-2 connection test. The snapshot is a JPEG (base64); it contains no stored data."""

    ok: bool
    error: str | None = None
    width: int | None = None
    height: int | None = None
    codec: str | None = None
    snapshot_jpeg_b64: str | None = None


class CameraRuntimeStatus(BaseModel):
    """`GET /cameras/status` item (FR-3, §12.2)."""

    camera_id: int
    name: str
    role: CameraRole
    mode: CameraMode
    connected: bool
    fps_target: float
    fps_actual: float
    last_frame_at: datetime | None = None
    lag_seconds: float
    faces_today: int
    restarts: int
    last_error: str | None = None
    process_alive: bool


class WorkerLoad(BaseModel):
    worker_id: int
    pid: int | None
    alive: bool
    tasks_done: int
    busy_ratio: float
    rss_mb: float


class LoadStatus(BaseModel):
    """`GET /load` result."""

    node: str
    cpu_percent: float
    level: LoadLevel
    level_since: datetime
    max_lag_seconds: float
    high_queue_depth: int
    low_queue_depth: int
    deferred_embeddings: int
    workers: list[WorkerLoad]


class EngineHealth(BaseModel):
    node: str
    status: Literal["ok", "degraded"]
    workers_alive: int
    cameras_running: int
    gallery_version: int
    redis_ok: bool
    database_ok: bool
