"""Portal users and roles (§4, Settings -> Users and roles). Super Admin only."""

from datetime import UTC, datetime

from facetrack_common.constants import AuthProvider, UserRole
from facetrack_common.models import Employee, User
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import transaction
from app.core.exceptions import Conflict, NotFound, ValidationFailed
from app.core.security import hash_password, validate_password_policy
from app.domain.audit import service as audit
from app.repositories import user_repo
from app.repositories.base import apply_changes, get_live, soft_delete
from app.schemas.user import UserCreate, UserOut, UserUpdate


def to_out(user: User) -> UserOut:
    out = UserOut.model_validate(user)
    out.is_locked = user.locked_until is not None and user.locked_until > datetime.now(UTC)
    return out


async def _check_employee_link(db: AsyncSession, role: UserRole, employee_id: int | None) -> None:
    if employee_id is not None and await get_live(db, Employee, employee_id) is None:
        raise ValidationFailed(errors={"employee_id": ["Employee not found."]})
    if role == UserRole.EMPLOYEE and employee_id is None:
        raise ValidationFailed(errors={"employee_id": ["An employee account must be linked to an employee."]})


async def create_user(db: AsyncSession, payload: UserCreate, actor: User) -> User:
    async with transaction(db):
        if await user_repo.exists_username_or_email(db, payload.username, payload.email):
            raise Conflict("A user with this username or email already exists.")
        await _check_employee_link(db, payload.role, payload.employee_id)
        password_hash = None
        if payload.auth_provider == AuthProvider.LOCAL:
            if not payload.password:
                raise ValidationFailed(errors={"password": ["A password is required for local accounts."]})
            validate_password_policy(payload.password)
            password_hash = hash_password(payload.password)
        user = User(
            name=payload.name,
            username=payload.username,
            email=payload.email,
            role=payload.role,
            auth_provider=payload.auth_provider,
            employee_id=payload.employee_id,
            password_hash=password_hash,
            is_active=True,
            failed_login_attempts=0,
            session_version=1,
        )
        db.add(user)
        await db.flush()
        await audit.record(
            db, actor, "user.create", "user", user.id, new=payload.model_dump(exclude={"password"})
        )
    return user


async def update_user(db: AsyncSession, user_id: int, payload: UserUpdate, actor: User) -> User:
    async with transaction(db):
        user = await get_live(db, User, user_id, for_update=True)
        if user is None:
            raise NotFound("User not found.")
        changes = payload.model_dump(exclude_unset=True, exclude={"password", "unlock"})
        if user.id == actor.id and (
            changes.get("is_active") is False or changes.get("role", user.role) != user.role
        ):
            raise ValidationFailed(
                errors={"role": ["You cannot deactivate yourself or change your own role."]}
            )
        if "email" in changes and await user_repo.exists_username_or_email(
            db, user.username, changes["email"], user.id
        ):
            raise Conflict("A user with this email already exists.")
        if "role" in changes or "employee_id" in changes:
            await _check_employee_link(
                db, changes.get("role", user.role), changes.get("employee_id", user.employee_id)
            )
        old = apply_changes(user, changes)
        if payload.password:
            if user.auth_provider != AuthProvider.LOCAL:
                raise ValidationFailed(errors={"password": ["Directory accounts have no local password."]})
            validate_password_policy(payload.password)
            user.password_hash = hash_password(payload.password)
            old["password"] = "[changed]"  # noqa: S105  # audit marker, not a password
        if payload.unlock or payload.password:
            user.failed_login_attempts = 0
            user.locked_until = None
        if old or payload.unlock:
            user.session_version += 1  # role/password/status changes end existing sessions
        await audit.record(
            db,
            actor,
            "user.update",
            "user",
            user.id,
            old=old,
            new={**changes, **({"unlock": True} if payload.unlock else {})},
        )
    return user


async def delete_user(db: AsyncSession, user_id: int, actor: User) -> None:
    if user_id == actor.id:
        raise ValidationFailed(errors={"id": ["You cannot delete your own account."]})
    async with transaction(db):
        user = await get_live(db, User, user_id, for_update=True)
        if user is None:
            raise NotFound("User not found.")
        soft_delete(user)
        user.is_active = False
        user.session_version += 1
        await audit.record(db, actor, "user.delete", "user", user_id)
