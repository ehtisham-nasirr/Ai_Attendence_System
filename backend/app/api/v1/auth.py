"""Authentication (FR-40): username/password and Active Directory, HttpOnly cookie sessions."""

from facetrack_common.constants import AuthProvider
from facetrack_common.schemas.envelope import ApiResponse
from fastapi import APIRouter, Request, Response, status

from app.api.deps import DbDep
from app.core.config import get_settings
from app.core.ratelimit import enforce_rate_limit
from app.core.request_context import get_request_context
from app.core.responses import ok
from app.core.security import (
    ACCESS_COOKIE,
    CurrentUser,
    clear_session_cookies,
    decode_token,
    issue_access_token,
    revoke_token,
    set_session_cookies,
)
from app.domain.auth import service as auth_service
from app.repositories import user_repo
from app.schemas.auth import LoginRequest, PasswordResetConfirm, PasswordResetRequest, UserProfile
from app.services import directory
from app.worker.dispatch import send_password_reset_email

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=ApiResponse[UserProfile], summary="Sign in")
async def login(payload: LoginRequest, response: Response, db: DbDep) -> ApiResponse[UserProfile]:
    """Sets the session cookie (HttpOnly) and a CSRF cookie. 5 failed attempts lock the account;
    requests are rate-limited per client IP (429)."""
    settings = get_settings()
    await enforce_rate_limit(f"login:{get_request_context().ip}", settings.login_rate_limit_per_minute)
    user = await auth_service.authenticate(
        db, payload.username, payload.password, payload.provider, directory.verify_credentials
    )
    token, expires = issue_access_token(user, settings)
    set_session_cookies(response, token, expires, settings)
    return ok(auth_service.profile(user, expires), "Signed in.")


@router.post("/logout", response_model=ApiResponse[None], summary="Sign out")
async def logout(request: Request, response: Response, user: CurrentUser) -> ApiResponse[None]:
    token = request.cookies.get(ACCESS_COOKIE)
    if token:
        await revoke_token(decode_token(token, get_settings(), "access"))
    clear_session_cookies(response)
    return ok(None, "Signed out.")


@router.get("/me", response_model=ApiResponse[UserProfile], summary="Current user")
async def me(user: CurrentUser) -> ApiResponse[UserProfile]:
    return ok(auth_service.profile(user), "Current user.")


@router.post(
    "/password-reset/request",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ApiResponse[None],
    summary="Email a password reset link",
)
async def request_password_reset(payload: PasswordResetRequest, db: DbDep) -> ApiResponse[None]:
    """Always answers 202 so the response never reveals whether an email address exists."""
    await enforce_rate_limit(f"reset:{get_request_context().ip}", get_settings().login_rate_limit_per_minute)
    user = await user_repo.by_email(db, str(payload.email))
    if user is not None and user.is_active and user.auth_provider == AuthProvider.LOCAL:
        token = auth_service.password_reset_token(user, get_settings())
        send_password_reset_email(
            user.email, f"{get_settings().portal_base_url}/reset-password?token={token}"
        )
    return ok(None, "If the address is registered, a reset link has been sent.")


@router.post("/password-reset/confirm", response_model=ApiResponse[None], summary="Set a new password")
async def confirm_password_reset(payload: PasswordResetConfirm, db: DbDep) -> ApiResponse[None]:
    await auth_service.reset_password(db, payload.token, payload.new_password, get_settings())
    return ok(None, "Password changed. Please sign in.")
