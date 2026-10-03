"""Portal user schemas (Settings -> Users and roles)."""

from facetrack_common.constants import AuthProvider, UserRole
from pydantic import EmailStr, Field

from app.schemas.common import ApiModel, InputModel, UtcDateTime


class UserCreate(InputModel):
    name: str = Field(min_length=1, max_length=200)
    username: str = Field(min_length=3, max_length=120, pattern=r"^[A-Za-z0-9._@-]+$")
    email: EmailStr
    role: UserRole
    auth_provider: AuthProvider = AuthProvider.LOCAL
    employee_id: int | None = None
    password: str | None = Field(default=None, min_length=10, max_length=256)


class UserUpdate(InputModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    email: EmailStr | None = None
    role: UserRole | None = None
    employee_id: int | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=10, max_length=256)
    unlock: bool = False


class UserOut(ApiModel):
    id: int
    name: str
    username: str
    email: str
    role: UserRole
    auth_provider: AuthProvider
    employee_id: int | None
    is_active: bool
    is_locked: bool = False
    last_login_at: UtcDateTime | None
    created_at: UtcDateTime
