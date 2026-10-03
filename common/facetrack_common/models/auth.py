"""Portal users and payroll API clients (requirements §11, FR-34, FR-40)."""

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from facetrack_common.constants import AuthProvider, UserRole
from facetrack_common.models.base import Base, IdMixin, SoftDeleteMixin, TimestampMixin, enum_column
from facetrack_common.models.organization import NOT_DELETED

if TYPE_CHECKING:
    from facetrack_common.models.employee import Employee


class User(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A portal user. Role permissions are mapped in backend code (§4)."""

    __tablename__ = "users"
    __table_args__ = (
        Index("uq_users_username_live", "username", unique=True, postgresql_where=NOT_DELETED),
        Index("uq_users_email_live", "email", unique=True, postgresql_where=NOT_DELETED),
    )

    name: Mapped[str] = mapped_column(String(200))
    username: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(254))
    # Argon2 hash; null for Active Directory users, who never log in with a local password.
    password_hash: Mapped[str | None] = mapped_column(String(255))
    auth_provider: Mapped[AuthProvider] = mapped_column(
        enum_column(AuthProvider, "auth_provider"), default=AuthProvider.LOCAL
    )
    role: Mapped[UserRole] = mapped_column(enum_column(UserRole, "user_role"))
    employee_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("employees.id", ondelete="SET NULL"), unique=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Bumped on password change/reset so older reset links and sessions stop working.
    session_version: Mapped[int] = mapped_column(Integer, default=1)

    employee: Mapped["Employee | None"] = relationship()


class ApiClient(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    """An integration client (payroll). Only a hash and a short prefix of the key are stored."""

    __tablename__ = "api_clients"

    name: Mapped[str] = mapped_column(String(120))
    key_prefix: Mapped[str] = mapped_column(String(16), unique=True)
    key_hash: Mapped[str] = mapped_column(String(128))
    scopes: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
