"""Auth schemas (FR-40)."""

from typing import Literal

from facetrack_common.constants import UserRole
from pydantic import EmailStr, Field

from app.schemas.common import ApiModel, InputModel, UtcDateTime


class LoginRequest(InputModel):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=256)
    provider: Literal["local", "ldap"] = "local"


class UserProfile(ApiModel):
    id: int
    name: str
    username: str
    email: str
    role: UserRole
    employee_id: int | None
    permissions: list[str]
    last_login_at: UtcDateTime | None
    session_expires_at: UtcDateTime | None = None


class PasswordResetRequest(InputModel):
    email: EmailStr


class PasswordResetConfirm(InputModel):
    token: str = Field(min_length=10, max_length=2048)
    new_password: str = Field(min_length=10, max_length=256)
