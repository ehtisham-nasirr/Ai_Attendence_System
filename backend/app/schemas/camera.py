"""Camera schemas (FR-1..FR-6). Stream URLs are write-only; responses never contain credentials."""

from typing import Any

from facetrack_common.constants import CameraMode, CameraRole, CameraStatus
from pydantic import Field, field_validator

from app.schemas.common import ApiModel, InputModel, UtcDateTime

_STREAM_URL = r"^(rtsp|rtsps|file)://\S+$"


def _check_polygon(value: list[list[float]] | None) -> list[list[float]] | None:
    if value is None:
        return value
    if len(value) < 3 or any(len(p) != 2 or not (0 <= p[0] <= 1 and 0 <= p[1] <= 1) for p in value):
        raise ValueError("ROI must be at least 3 points with coordinates normalised to [0, 1]")
    return value


def _check_hours(value: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    import re  # noqa: PLC0415

    if value is None:
        return value
    for window in value:
        if not re.match(r"^\d{2}:\d{2}$", str(window.get("start", ""))) or not re.match(
            r"^\d{2}:\d{2}$", str(window.get("end", ""))
        ):
            raise ValueError("operating hours windows need start and end as HH:MM")
        if any(int(day) < 1 or int(day) > 7 for day in window.get("days", [])):
            raise ValueError("operating hours days are ISO weekdays 1-7")
    return value


class CameraCreate(InputModel):
    name: str = Field(min_length=1, max_length=120)
    location_id: int
    role: CameraRole
    rtsp_url: str = Field(min_length=8, max_length=1024, pattern=_STREAM_URL)
    substream_url: str | None = Field(default=None, max_length=1024, pattern=_STREAM_URL)
    engine_node: str = Field(default="node-1", min_length=1, max_length=64)
    priority: int = Field(default=0, ge=0, le=100)
    operating_hours: list[dict[str, Any]] | None = None
    roi_polygon: list[list[float]] | None = None
    fps: float | None = Field(default=None, gt=0, le=15)
    match_threshold: float | None = Field(default=None, gt=0, lt=1)
    liveness_enabled: bool = False
    is_enabled: bool = True

    _roi = field_validator("roi_polygon")(_check_polygon)
    _hours = field_validator("operating_hours")(_check_hours)


class CameraUpdate(InputModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    location_id: int | None = None
    role: CameraRole | None = None
    rtsp_url: str | None = Field(default=None, max_length=1024, pattern=_STREAM_URL)
    substream_url: str | None = Field(default=None, max_length=1024, pattern=_STREAM_URL)
    clear_substream: bool = False
    engine_node: str | None = Field(default=None, min_length=1, max_length=64)
    priority: int | None = Field(default=None, ge=0, le=100)
    operating_hours: list[dict[str, Any]] | None = None
    roi_polygon: list[list[float]] | None = None
    clear_roi: bool = False
    fps: float | None = Field(default=None, gt=0, le=15)
    match_threshold: float | None = Field(default=None, gt=0, lt=1)
    liveness_enabled: bool | None = None
    is_enabled: bool | None = None

    _roi = field_validator("roi_polygon")(_check_polygon)
    _hours = field_validator("operating_hours")(_check_hours)


class CameraRuntimeOut(ApiModel):
    mode: CameraMode
    connected: bool
    fps_target: float
    fps_actual: float
    lag_seconds: float
    faces_today: int
    last_error: str | None
    updated_at: UtcDateTime | None


class CameraOut(ApiModel):
    id: int
    name: str
    location_id: int
    role: CameraRole
    stream_host: str
    has_substream: bool
    engine_node: str
    priority: int
    operating_hours: list[dict[str, Any]] | None
    roi_polygon: list[list[float]] | None
    fps: float | None
    match_threshold: float | None
    liveness_enabled: bool
    is_enabled: bool
    status: CameraStatus
    last_seen_at: UtcDateTime | None
    runtime: CameraRuntimeOut | None = None
    created_at: UtcDateTime


class CameraTestOut(ApiModel):
    ok: bool
    error: str | None
    width: int | None
    height: int | None
    codec: str | None
    snapshot_jpeg_b64: str | None


class CameraLiveOut(ApiModel):
    webrtc_url: str
    token: str
    expires_at: UtcDateTime
