"""Attendance days and corrections (requirements §11, FR-20..FR-26)."""

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from facetrack_common.constants import AttendanceStatus, CorrectionField, CorrectionStatus
from facetrack_common.models.base import Base, IdMixin, TimestampMixin, enum_column

if TYPE_CHECKING:
    from facetrack_common.models.auth import User
    from facetrack_common.models.employee import Employee
    from facetrack_common.models.organization import Shift


class AttendanceDay(IdMixin, TimestampMixin, Base):
    """One employee's attendance for one work date. Values are computed only by the backend domain."""

    __tablename__ = "attendance_days"
    __table_args__ = (
        UniqueConstraint("employee_id", "work_date", name="uq_attendance_days_employee_work_date"),
        Index("ix_attendance_days_work_date_status", "work_date", "status"),
    )

    employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("employees.id", ondelete="CASCADE"))
    work_date: Mapped[date] = mapped_column(Date)
    shift_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("shifts.id", ondelete="SET NULL"))
    check_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    check_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # No FK: recognition_events is partitioned (docs/open-questions.md Q21).
    check_in_event_id: Mapped[int | None] = mapped_column(BigInteger)
    check_out_event_id: Mapped[int | None] = mapped_column(BigInteger)
    worked_minutes: Mapped[int] = mapped_column(Integer, default=0)
    late_minutes: Mapped[int] = mapped_column(Integer, default=0)
    early_minutes: Mapped[int] = mapped_column(Integer, default=0)
    overtime_minutes: Mapped[int] = mapped_column(Integer, default=0)
    # Null until the first check-in or the day close (Q12).
    status: Mapped[AttendanceStatus | None] = mapped_column(
        enum_column(AttendanceStatus, "attendance_status")
    )
    is_manual: Mapped[bool] = mapped_column(Boolean, default=False)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    employee: Mapped["Employee"] = relationship()
    shift: Mapped["Shift | None"] = relationship()
    corrections: Mapped[list["AttendanceCorrection"]] = relationship(back_populates="attendance_day")


class AttendanceCorrection(IdMixin, TimestampMixin, Base):
    """A requested or applied change to one field of an attendance day (FR-25, FR-26).

    `old_value` keeps the original data; approved corrections lock that field (ADR-0004).
    """

    __tablename__ = "attendance_corrections"
    __table_args__ = (Index("ix_attendance_corrections_status_created", "status", "created_at"),)

    attendance_day_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("attendance_days.id", ondelete="CASCADE"), index=True
    )
    requested_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="RESTRICT"))
    field: Mapped[CorrectionField] = mapped_column(enum_column(CorrectionField, "correction_field"))
    old_value: Mapped[str | None] = mapped_column(String(64))
    new_value: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[CorrectionStatus] = mapped_column(
        enum_column(CorrectionStatus, "correction_status"), default=CorrectionStatus.PENDING
    )
    approved_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_comment: Mapped[str | None] = mapped_column(Text)

    attendance_day: Mapped[AttendanceDay] = relationship(back_populates="corrections")
    requester: Mapped["User"] = relationship(foreign_keys=[requested_by])
    approver: Mapped["User | None"] = relationship(foreign_keys=[approved_by])
