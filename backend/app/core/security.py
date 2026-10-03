"""Authentication, RBAC and data scoping (requirements §4, §15, standards/06).

- Portal: JWT in an HttpOnly cookie, 30-minute sliding session, double-submit CSRF token.
- Integrations: `X-API-Key` (only a SHA-256 hash and a short prefix are stored).
- Permissions per role mirror the §4 table; data scope limits managers to their departments and
  employees to their own records. The backend is the final authority; the UI only mirrors it.
"""

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Annotated, Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from facetrack_common.constants import UserRole
from facetrack_common.models import ApiClient, Department, User
from fastapi import Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.core.exceptions import PermissionDenied, Unauthorized, ValidationFailed
from app.core.redis import get_async_redis

ACCESS_COOKIE = "ft_access"
CSRF_COOKIE = "ft_csrf"
CSRF_HEADER = "X-CSRF-Token"
API_KEY_HEADER = "X-API-Key"
_REFRESH_AFTER = timedelta(minutes=5)
_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_hasher = PasswordHasher()


class Permission(StrEnum):
    USERS_MANAGE = "users:manage"
    SETTINGS_MANAGE = "settings:manage"
    CAMERAS_MANAGE = "cameras:manage"
    EMPLOYEES_MANAGE = "employees:manage"
    BIOMETRICS_ERASE = "biometrics:erase"
    LIVE_VIEW = "live:view"
    ATTENDANCE_VIEW = "attendance:view"
    ATTENDANCE_CORRECT = "attendance:correct"
    CORRECTIONS_REQUEST = "corrections:request"
    UNKNOWN_FACES_REVIEW = "unknown_faces:review"
    UNKNOWN_FACES_ASSIGN = "unknown_faces:assign"
    EVENTS_VIEW = "events:view"
    EVENTS_VOID = "events:void"
    REPORTS_EXPORT = "reports:export"
    AUDIT_VIEW = "audit:view"
    DASHBOARD_VIEW = "dashboard:view"
    ORGANIZATION_VIEW = "organization:view"


P = Permission
# Requirements §4 (rows) x roles (columns); §12 role columns refine assign/void to Admin + HR.
ROLE_PERMISSIONS: dict[UserRole, frozenset[Permission]] = {
    UserRole.SUPER_ADMIN: frozenset(Permission),
    UserRole.HR_ADMIN: frozenset(
        {
            P.EMPLOYEES_MANAGE,
            P.LIVE_VIEW,
            P.ATTENDANCE_VIEW,
            P.ATTENDANCE_CORRECT,
            P.UNKNOWN_FACES_REVIEW,
            P.UNKNOWN_FACES_ASSIGN,
            P.EVENTS_VIEW,
            P.EVENTS_VOID,
            P.REPORTS_EXPORT,
            P.DASHBOARD_VIEW,
            P.ORGANIZATION_VIEW,
        }
    ),
    UserRole.DEPARTMENT_MANAGER: frozenset(
        {P.ATTENDANCE_VIEW, P.ATTENDANCE_CORRECT, P.REPORTS_EXPORT, P.DASHBOARD_VIEW, P.ORGANIZATION_VIEW}
    ),
    UserRole.OPERATOR: frozenset(
        {P.CAMERAS_MANAGE, P.LIVE_VIEW, P.UNKNOWN_FACES_REVIEW, P.EVENTS_VIEW, P.ORGANIZATION_VIEW}
    ),
    UserRole.EMPLOYEE: frozenset({P.ATTENDANCE_VIEW, P.CORRECTIONS_REQUEST, P.REPORTS_EXPORT}),
}


def permissions_for(role: UserRole) -> frozenset[Permission]:
    return ROLE_PERMISSIONS[role]


# --------------------------------------------------------------------------- passwords


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    if not password_hash:
        return False
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def validate_password_policy(password: str) -> None:
    """Q18: at least 10 characters with a letter and a digit."""
    if len(password) < 10 or not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        raise ValidationFailed(
            errors={"password": ["Password must be at least 10 characters and contain a letter and a digit."]}
        )


# --------------------------------------------------------------------------- tokens


def issue_access_token(user: User, settings: Settings, now: datetime | None = None) -> tuple[str, datetime]:
    now = now or datetime.now(UTC)
    expires = now + timedelta(minutes=settings.session_minutes)
    claims = {
        "sub": str(user.id),
        "sv": user.session_version,
        "jti": uuid.uuid4().hex,
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
        "typ": "access",
    }
    return jwt.encode(claims, settings.jwt_secret.get_secret_value(), settings.jwt_algorithm), expires


def decode_token(token: str, settings: Settings, expected_type: str) -> dict[str, Any]:
    try:
        claims: dict[str, Any] = jwt.decode(
            token, settings.jwt_secret.get_secret_value(), algorithms=[settings.jwt_algorithm]
        )
    except jwt.PyJWTError as exc:
        raise Unauthorized("Your session has expired. Please sign in again.") from exc
    if claims.get("typ") != expected_type:
        raise Unauthorized("Invalid token.")
    return claims


def set_session_cookies(response: Response, token: str, expires: datetime, settings: Settings) -> None:
    max_age = int((expires - datetime.now(UTC)).total_seconds())
    response.set_cookie(
        ACCESS_COOKIE,
        token,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        secrets.token_urlsafe(24),
        max_age=max_age,
        httponly=False,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
    )


def clear_session_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


async def revoke_token(claims: dict[str, Any]) -> None:
    ttl = max(1, int(claims["exp"]) - int(datetime.now(UTC).timestamp()))
    await get_async_redis().set(f"revoked:{claims['jti']}", "1", ex=ttl)


# --------------------------------------------------------------------------- current user


def _check_csrf(request: Request, settings: Settings) -> None:
    if request.method not in _UNSAFE_METHODS:
        return
    cookie = request.cookies.get(CSRF_COOKIE)
    header = request.headers.get(CSRF_HEADER)
    if not cookie or not header or not hmac.compare_digest(cookie, header):
        raise PermissionDenied("Missing or invalid CSRF token.")
    origin = request.headers.get("origin")
    if origin and settings.cors_origins and origin not in settings.cors_origins:
        raise PermissionDenied("Request origin is not allowed.")


async def get_current_user(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    settings = get_settings()
    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        raise Unauthorized()
    claims = decode_token(token, settings, "access")
    if await get_async_redis().exists(f"revoked:{claims['jti']}"):
        raise Unauthorized("Your session has ended. Please sign in again.")
    _check_csrf(request, settings)
    user = await db.scalar(select(User).where(User.id == int(claims["sub"]), User.deleted_at.is_(None)))
    if user is None or not user.is_active or user.session_version != claims.get("sv"):
        raise Unauthorized("Your session has ended. Please sign in again.")
    request.state.user_id = user.id
    # Sliding 30-minute session: re-issue the cookie on activity.
    issued = datetime.fromtimestamp(int(claims["iat"]), UTC)
    if datetime.now(UTC) - issued > _REFRESH_AFTER:
        new_token, expires = issue_access_token(user, settings)
        await revoke_token(claims)
        set_session_cookies(response, new_token, expires, settings)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_permission(permission: Permission) -> Any:
    async def dependency(user: CurrentUser) -> User:
        if permission not in permissions_for(user.role):
            raise PermissionDenied()
        return user

    return Depends(dependency)


def has_permission(user: User, permission: Permission) -> bool:
    return permission in permissions_for(user.role)


# --------------------------------------------------------------------------- data scope


@dataclass(frozen=True)
class DataScope:
    """Which employees' attendance/records a user may see (§4 "View attendance")."""

    all_employees: bool
    department_ids: frozenset[int] = frozenset()
    employee_id: int | None = None

    def allows(self, employee_department_id: int | None, employee_id: int) -> bool:
        if self.all_employees:
            return True
        if self.employee_id is not None:
            return employee_id == self.employee_id
        return employee_department_id is not None and employee_department_id in self.department_ids


async def data_scope(db: AsyncSession, user: User) -> DataScope:
    if user.role in (UserRole.SUPER_ADMIN, UserRole.HR_ADMIN):
        return DataScope(all_employees=True)
    if user.role == UserRole.DEPARTMENT_MANAGER:
        ids = await db.scalars(
            select(Department.id).where(
                Department.manager_user_id == user.id, Department.deleted_at.is_(None)
            )
        )
        return DataScope(all_employees=False, department_ids=frozenset(ids))
    if user.role == UserRole.EMPLOYEE and user.employee_id is not None:
        return DataScope(all_employees=False, employee_id=user.employee_id)
    return DataScope(all_employees=False)  # operators and unlinked employees see no attendance


# --------------------------------------------------------------------------- API keys (FR-34)


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def generate_api_key() -> tuple[str, str]:
    """Returns (full key shown once, prefix stored for identification)."""
    prefix = secrets.token_hex(4)
    return f"ft_{prefix}_{secrets.token_urlsafe(32)}", prefix


async def get_api_client(request: Request, db: Annotated[AsyncSession, Depends(get_db)]) -> ApiClient:
    key = request.headers.get(API_KEY_HEADER, "")
    parts = key.split("_")
    if len(parts) < 3 or parts[0] != "ft":
        raise Unauthorized("A valid API key is required.")
    client = await db.scalar(
        select(ApiClient).where(
            ApiClient.key_prefix == parts[1], ApiClient.is_active.is_(True), ApiClient.deleted_at.is_(None)
        )
    )
    if client is None or not hmac.compare_digest(client.key_hash, hash_api_key(key)):
        raise Unauthorized("A valid API key is required.")
    from app.core.ratelimit import enforce_rate_limit  # noqa: PLC0415  # avoids an import cycle

    await enforce_rate_limit(f"apikey:{client.id}", get_settings().api_key_rate_limit_per_minute)
    now = datetime.now(UTC)
    if client.last_used_at is None or now - client.last_used_at > timedelta(minutes=1):
        client.last_used_at = now
        await db.commit()
    return client


def require_scope(scope: str) -> Any:
    async def dependency(client: Annotated[ApiClient, Depends(get_api_client)]) -> ApiClient:
        if scope not in (client.scopes or []):
            raise PermissionDenied("This API key does not have the required scope.")
        return client

    return Depends(dependency)
