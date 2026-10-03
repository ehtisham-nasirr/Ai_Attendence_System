"""Locations, departments, shifts and holidays (requirements §11)."""

from datetime import date, time
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, Boolean, Date, ForeignKey, Index, Integer, String, Time, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from facetrack_common.models.base import Base, IdMixin, SoftDeleteMixin, TimestampMixin

if TYPE_CHECKING:
    from facetrack_common.models.auth import User

# Soft-deleted rows must not block re-creating a record with the same natural key.
NOT_DELETED = text("deleted_at IS NULL")


class Location(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    """An office site with its own cameras and timezone (FR-36)."""

    __tablename__ = "locations"
    __table_args__ = (Index("uq_locations_name_live", "name", unique=True, postgresql_where=NOT_DELETED),)

    name: Mapped[str] = mapped_column(String(120))
    address: Mapped[str | None] = mapped_column(String(500))
    timezone: Mapped[str] = mapped_column(String(64))


class Department(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "departments"
    __table_args__ = (Index("uq_departments_code_live", "code", unique=True, postgresql_where=NOT_DELETED),)

    name: Mapped[str] = mapped_column(String(120))
    code: Mapped[str] = mapped_column(String(32))
    manager_user_id: Mapped[int | None] = mapped_column(
        # use_alter: departments -> users -> employees -> departments is a cycle.
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL", use_alter=True),
        index=True,
    )

    manager: Mapped["User | None"] = relationship(foreign_keys=[manager_user_id])


class Shift(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A working shift (FR-21). Night shifts end on the next calendar day."""

    __tablename__ = "shifts"
    __table_args__ = (Index("uq_shifts_name_live", "name", unique=True, postgresql_where=NOT_DELETED),)

    name: Mapped[str] = mapped_column(String(120))
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    grace_in_min: Mapped[int] = mapped_column(Integer, default=15)
    grace_out_min: Mapped[int] = mapped_column(Integer, default=15)
    half_day_pct: Mapped[int] = mapped_column(Integer, default=50)
    is_night_shift: Mapped[bool] = mapped_column(Boolean, default=False)
    # ISO weekday numbers that are weekly offs: 1 = Monday ... 7 = Sunday.
    weekly_offs: Mapped[list[Any]] = mapped_column(JSONB, default=list)


class Holiday(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A public holiday at one location (FR-21)."""

    __tablename__ = "holidays"
    __table_args__ = (
        Index(
            "uq_holidays_location_date_live", "location_id", "date", unique=True, postgresql_where=NOT_DELETED
        ),
    )

    location_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("locations.id", ondelete="CASCADE"), index=True
    )
    date: Mapped[date] = mapped_column(Date)
    name: Mapped[str] = mapped_column(String(120))
