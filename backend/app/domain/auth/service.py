"""Login, logout, lockout and password reset (FR-40, §15: lockout after 5 failures, 30-minute sessions)."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from facetrack_common.constants import AuthProvider
from facetrack_common.models import User
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.db import transaction
from app.core.exceptions import Unauthorized, ValidationFailed
from app.core.security import (
    decode_token,
    hash_password,
    permissions_for,
    validate_password_policy,
    verify_password,
)
from app.domain.audit import service as audit
from app.domain.settings import service as settings_service
from app.repositories import user_repo
from app.schemas.auth import UserProfile

logger = logging.getLogger(__name__)

MAX_FAILED_LOGINS = 5
_INVALID = "Invalid username or password."
_RESET_MINUTES = 30


def profile(user: User, timezone: str, expires: datetime | None = None) -> UserProfile:
    return UserProfile(
        id=user.id,
        name=user.name,
        username=user.username,
        email=user.email,
        role=user.role,
        employee_id=user.employee_id,
        permissions=sorted(p.value for p in permissions_for(user.role)),
        last_login_at=user.last_login_at,
        session_expires_at=expires,
        timezone=timezone,
    )


async def authenticate(
    db: AsyncSession, username: str, password: str, provider: str, directory_check: Any = None
) -> User:
    """Verifies credentials and applies the lockout policy. Raises Unauthorized on any failure."""
    now = datetime.now(UTC)
    # Every outcome is audited (FR-37); errors are raised only after the audit entry is committed.
    failure: str | None = None
    async with transaction(db):
        values = await settings_service.resolved(db)
        user = await user_repo.by_username(db, username, for_update=True)
        if user is None or not user.is_active:
            await audit.record(db, None, "auth.login_failed", "user", None, new={"username": username[:120]})
            failure = _INVALID
        elif user.locked_until is not None and user.locked_until > now:
            await audit.record(db, user, "auth.login_locked", "user", user.id)
            failure = "This account is temporarily locked after repeated failed sign-ins."
        elif not await _credentials_ok(user, username, password, provider, values, directory_check):
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= MAX_FAILED_LOGINS:
                user.locked_until = now + timedelta(minutes=int(values["auth.lockout_minutes"]))
                user.failed_login_attempts = 0
            await audit.record(
                db,
                user,
                "auth.login_failed",
                "user",
                user.id,
                new={"locked": user.locked_until is not None and user.locked_until > now},
            )
            failure = _INVALID
        else:
            user.failed_login_attempts = 0
            user.locked_until = None
            user.last_login_at = now
            await audit.record(
                db, user, "auth.login", "user", user.id, new={"provider": user.auth_provider.value}
            )
    if failure is not None or user is None:
        raise Unauthorized(failure or _INVALID)
    return user


async def _credentials_ok(
    user: User, username: str, password: str, provider: str, values: dict[str, Any], directory_check: Any
) -> bool:
    if user.auth_provider == AuthProvider.LDAP or provider == "ldap":
        return (
            user.auth_provider == AuthProvider.LDAP
            and bool(values["auth.ldap_enabled"])
            and directory_check is not None
            and bool(await directory_check(username, password))
        )
    return verify_password(user.password_hash, password)


def password_reset_token(user: User, settings: Settings) -> str:
    now = datetime.now(UTC)
    claims = {
        "sub": str(user.id),
        "sv": user.session_version,
        "typ": "reset",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=_RESET_MINUTES)).timestamp()),
    }
    return jwt.encode(claims, settings.jwt_secret.get_secret_value(), settings.jwt_algorithm)


async def reset_password(db: AsyncSession, token: str, new_password: str, settings: Settings) -> None:
    claims = decode_token(token, settings, "reset")
    validate_password_policy(new_password)
    async with transaction(db):
        user = await db.get(User, int(claims["sub"]), with_for_update=True)
        # session_version changes on every password change, so a reset link works only once.
        if user is None or user.deleted_at is not None or user.session_version != claims.get("sv"):
            raise ValidationFailed(errors={"token": ["This reset link is invalid or has already been used."]})
        if user.auth_provider != AuthProvider.LOCAL:
            raise ValidationFailed(
                errors={"token": ["Directory accounts reset passwords in Active Directory."]}
            )
        user.password_hash = hash_password(new_password)
        user.session_version += 1
        user.failed_login_attempts = 0
        user.locked_until = None
        await audit.record(db, user, "auth.password_reset", "user", user.id)
