"""Settings and the audit log (requirements §11, FR-37, FR-38)."""

from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from facetrack_common.models.base import Base, IdMixin, TimestampMixin


class Setting(IdMixin, TimestampMixin, Base):
    """One configuration value. Keys and defaults are defined in `facetrack_common.settings_keys`."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(120), unique=True)
    value: Mapped[Any] = mapped_column(JSONB)


class AuditLog(IdMixin, TimestampMixin, Base):
    """Append-only audit trail (FR-37). Never stores biometric data, passwords or keys."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_entity", "entity", "entity_id"),
        Index("ix_audit_logs_created_at", "created_at"),
    )

    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    old_values: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    new_values: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(500))
