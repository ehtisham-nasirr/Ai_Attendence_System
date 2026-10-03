"""Cameras (requirements §11, FR-1..FR-6)."""

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer, LargeBinary, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from facetrack_common.constants import CameraRole, CameraStatus
from facetrack_common.models.base import Base, IdMixin, SoftDeleteMixin, TimestampMixin, enum_column
from facetrack_common.models.organization import NOT_DELETED

if TYPE_CHECKING:
    from facetrack_common.models.organization import Location


class Camera(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    """An IP camera. RTSP URLs (with credentials) are stored only as AES-256-GCM ciphertext (NFR-8)."""

    __tablename__ = "cameras"
    __table_args__ = (
        Index("uq_cameras_name_live", "name", unique=True, postgresql_where=NOT_DELETED),
        Index("ix_cameras_engine_node", "engine_node"),
    )

    location_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("locations.id", ondelete="RESTRICT"))
    name: Mapped[str] = mapped_column(String(120))
    rtsp_url_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    substream_url_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    # Name of the engine node that processes this camera (standards/17 §9).
    engine_node: Mapped[str] = mapped_column(String(64))
    priority: Mapped[int] = mapped_column(Integer, default=0)
    # {"days": [1..7], "start": "HH:MM", "end": "HH:MM"} windows in the location's timezone; null = always.
    operating_hours: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    role: Mapped[CameraRole] = mapped_column(enum_column(CameraRole, "camera_role"))
    # Normalised polygon [[x, y], ...] in [0, 1] frame coordinates (FR-5); null = whole frame.
    roi_polygon: Mapped[list[list[float]] | None] = mapped_column(JSONB)
    # ACTIVE detection rate; null = role default from settings (Q1).
    fps: Mapped[float | None] = mapped_column(Float)
    # Per-camera override of the model's default threshold (§9); null = settings default.
    match_threshold: Mapped[float | None] = mapped_column(Float)
    liveness_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[CameraStatus] = mapped_column(
        enum_column(CameraStatus, "camera_status"), default=CameraStatus.UNKNOWN
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # When the camera was first seen offline in the current outage, for the FR-4 five-minute alert.
    offline_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    location: Mapped["Location"] = relationship()
