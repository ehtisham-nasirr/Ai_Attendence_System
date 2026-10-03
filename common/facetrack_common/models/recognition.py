"""Recognition events and unknown faces (requirements §11, FR-16, FR-17, FR-27, FR-28)."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from facetrack_common.constants import RecognitionStatus, ReviewStatus
from facetrack_common.models.base import Base, IdMixin, TimestampMixin, enum_column

if TYPE_CHECKING:
    from facetrack_common.models.camera import Camera
    from facetrack_common.models.employee import Employee


class RecognitionEventRecord(TimestampMixin, Base):
    """A stored recognition event. Range-partitioned by month on `captured_at` (§11).

    PostgreSQL requires the partition key in every unique constraint, so the primary key is
    (id, captured_at) and uniqueness of `event_uuid` is enforced as (event_uuid, captured_at):
    a replayed event always carries the same `captured_at` (docs/open-questions.md Q21).
    """

    __tablename__ = "recognition_events"
    __table_args__ = (
        UniqueConstraint("event_uuid", "captured_at", name="uq_recognition_events_event_uuid"),
        Index("ix_recognition_events_employee_captured", "employee_id", "captured_at"),
        Index("ix_recognition_events_camera_captured", "camera_id", "captured_at"),
        Index("ix_recognition_events_status_captured", "status", "captured_at"),
        {"postgresql_partition_by": "RANGE (captured_at)"},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    event_uuid: Mapped[uuid.UUID] = mapped_column(Uuid)
    camera_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("cameras.id", ondelete="RESTRICT"))
    employee_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("employees.id", ondelete="SET NULL")
    )
    status: Mapped[RecognitionStatus] = mapped_column(enum_column(RecognitionStatus, "recognition_status"))
    confidence: Mapped[float] = mapped_column(Float)
    liveness_score: Mapped[float | None] = mapped_column(Float)
    track_id: Mapped[int] = mapped_column(BigInteger)
    snapshot_path: Mapped[str | None] = mapped_column(String(512))
    model_name: Mapped[str] = mapped_column(String(64))
    engine_node: Mapped[str] = mapped_column(String(64))
    # FR-28: false recognitions are voided with a reason, kept for threshold tuning.
    void_reason: Mapped[str | None] = mapped_column(String(500))
    voided_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    camera: Mapped["Camera"] = relationship()
    employee: Mapped["Employee | None"] = relationship()


class UnknownFace(IdMixin, TimestampMixin, Base):
    """An unrecognised face awaiting review (FR-17, FR-27). Biometric data: hard-deleted by retention."""

    __tablename__ = "unknown_faces"
    __table_args__ = (Index("ix_unknown_faces_review_captured", "review_status", "captured_at"),)

    # No FK: recognition_events is partitioned (Q21). (recognition_event_id, captured_at) locates it.
    recognition_event_id: Mapped[int] = mapped_column(BigInteger, index=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    camera_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("cameras.id", ondelete="RESTRICT"))
    embedding_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    embedding_dim: Mapped[int | None] = mapped_column(Integer)
    model_name: Mapped[str] = mapped_column(String(64))
    snapshot_path: Mapped[str | None] = mapped_column(String(512))
    liveness_score: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[ReviewStatus] = mapped_column(
        enum_column(ReviewStatus, "review_status"), default=ReviewStatus.PENDING
    )
    assigned_employee_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("employees.id", ondelete="SET NULL")
    )
    reviewed_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    camera: Mapped["Camera"] = relationship()
    assigned_employee: Mapped["Employee | None"] = relationship()
