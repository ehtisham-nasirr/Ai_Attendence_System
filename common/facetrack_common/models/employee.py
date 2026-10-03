"""Employees, face enrollments and leave (requirements §11)."""

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from facetrack_common.constants import EmployeeStatus, EnrollmentSource, LeaveSource
from facetrack_common.models.base import Base, IdMixin, SoftDeleteMixin, TimestampMixin, enum_column

if TYPE_CHECKING:
    from facetrack_common.models.organization import Department, Location, Shift


class Employee(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    """An employee (FR-7). `employee_code` matches the HR/payroll system and is never reused."""

    __tablename__ = "employees"

    employee_code: Mapped[str] = mapped_column(String(64), unique=True)
    full_name: Mapped[str] = mapped_column(String(200))
    department_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("departments.id", ondelete="SET NULL"), index=True
    )
    designation: Mapped[str | None] = mapped_column(String(120))
    shift_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("shifts.id", ondelete="SET NULL"), index=True
    )
    location_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("locations.id", ondelete="SET NULL"), index=True
    )
    email: Mapped[str | None] = mapped_column(String(254))
    phone: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[EmployeeStatus] = mapped_column(
        enum_column(EmployeeStatus, "employee_status"), default=EmployeeStatus.ACTIVE, index=True
    )
    # Enrollment is blocked until written consent is recorded (§15, standards/18).
    consent_signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Start of the enrollment-retention clock (exit + 30 days, §15).
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hr_external_id: Mapped[str | None] = mapped_column(String(64), unique=True)

    department: Mapped["Department | None"] = relationship()
    shift: Mapped["Shift | None"] = relationship()
    location: Mapped["Location | None"] = relationship()
    face_enrollments: Mapped[list["FaceEnrollment"]] = relationship(
        back_populates="employee", cascade="all, delete-orphan", passive_deletes=True
    )


class FaceEnrollment(IdMixin, TimestampMixin, Base):
    """One enrolled face photo and its embedding. Biometric data: hard-deleted on erasure (FR-13).

    The embedding is AES-256-GCM ciphertext (ADR-0001); never compare embeddings across models.
    """

    __tablename__ = "face_enrollments"

    employee_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("employees.id", ondelete="CASCADE"), index=True
    )
    image_path: Mapped[str] = mapped_column(String(512))
    embedding_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    embedding_dim: Mapped[int] = mapped_column(Integer)
    model_name: Mapped[str] = mapped_column(String(64), index=True)
    quality_score: Mapped[float] = mapped_column(Float)
    source: Mapped[EnrollmentSource] = mapped_column(enum_column(EnrollmentSource, "enrollment_source"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    employee: Mapped[Employee] = relationship(back_populates="face_enrollments")


class Leave(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Approved leave (FR-24). Imported from HR or entered by HR; every row counts as approved (Q16)."""

    __tablename__ = "leaves"
    __table_args__ = (
        Index("ix_leaves_employee_dates", "employee_id", "from_date", "to_date"),
        Index(
            "uq_leaves_external_ref_live",
            "external_ref",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND external_ref IS NOT NULL"),
        ),
    )

    employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("employees.id", ondelete="CASCADE"))
    from_date: Mapped[date] = mapped_column(Date)
    to_date: Mapped[date] = mapped_column(Date)
    type: Mapped[str] = mapped_column(String(64))
    source: Mapped[LeaveSource] = mapped_column(enum_column(LeaveSource, "leave_source"))
    # The HR system's id of the leave record, so nightly sync is idempotent.
    external_ref: Mapped[str | None] = mapped_column(String(64))

    employee: Mapped[Employee] = relationship()
