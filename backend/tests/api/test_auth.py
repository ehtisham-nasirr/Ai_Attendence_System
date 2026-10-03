"""Authentication, sessions, CSRF, lockout, rate limits, password reset (FR-40, §15, standards/06)."""

from conftest import PASSWORD, Api, make_user
from facetrack_common.constants import UserRole
from facetrack_common.models import AuditLog, User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import ACCESS_COOKIE, CSRF_COOKIE
from app.domain.auth.service import password_reset_token


async def test_fr40_login_sets_httponly_session_and_csrf_cookie(api: Api, db: AsyncSession) -> None:
    user = await make_user(db, UserRole.HR_ADMIN, "hr1")
    response = await api.login("hr1")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True and body["data"]["role"] == "hr_admin"
    assert "employees:manage" in body["data"]["permissions"]
    cookies = response.headers.get_list("set-cookie")
    assert any(c.startswith(f"{ACCESS_COOKIE}=") and "HttpOnly" in c for c in cookies)
    assert any(c.startswith(f"{CSRF_COOKIE}=") and "HttpOnly" not in c for c in cookies)
    me = await api.get("/api/v1/auth/me")
    assert me.json()["data"]["id"] == user.id


async def test_wrong_password_is_401_with_generic_message(api: Api, db: AsyncSession) -> None:
    await make_user(db, UserRole.HR_ADMIN, "hr1")
    for username in ("hr1", "nobody"):
        response = await api.client.post(
            "/api/v1/auth/login", json={"username": username, "password": "wrong-pass1"}
        )
        assert response.status_code == 401
        assert response.json() == {"success": False, "message": "Invalid username or password.", "errors": {}}


async def test_unauthenticated_requests_are_401(api: Api) -> None:
    response = await api.get("/api/v1/auth/me")
    assert response.status_code == 401 and response.json()["success"] is False


async def test_section15_lockout_after_five_failed_logins(api: Api, db: AsyncSession) -> None:
    await make_user(db, UserRole.HR_ADMIN, "hr1")
    for _ in range(5):
        await api.client.post("/api/v1/auth/login", json={"username": "hr1", "password": "wrong-pass1"})
    response = await api.client.post("/api/v1/auth/login", json={"username": "hr1", "password": PASSWORD})
    assert response.status_code == 401 and "locked" in response.json()["message"]
    actions = list(await db.scalars(select(AuditLog.action)))
    assert actions.count("auth.login_failed") == 5 and "auth.login_locked" in actions


async def test_login_is_rate_limited_per_ip(api: Api, db: AsyncSession) -> None:
    await make_user(db, UserRole.HR_ADMIN, "hr1")
    statuses = [
        (await api.client.post("/api/v1/auth/login", json={"username": "x", "password": "y"})).status_code
        for _ in range(get_settings().login_rate_limit_per_minute + 1)
    ]
    assert statuses[-1] == 429


async def test_csrf_header_required_for_state_changes(api: Api, db: AsyncSession) -> None:
    await make_user(db, UserRole.SUPER_ADMIN, "admin")
    await api.login("admin")
    del api.client.headers["X-CSRF-Token"]
    response = await api.post("/api/v1/locations", json={"name": "Lahore", "timezone": "Asia/Karachi"})
    assert response.status_code == 403 and "CSRF" in response.json()["message"]


async def test_logout_revokes_the_session(api: Api, db: AsyncSession) -> None:
    await make_user(db, UserRole.HR_ADMIN, "hr1")
    await api.login("hr1")
    token = api.client.cookies.get(ACCESS_COOKIE)
    assert (await api.post("/api/v1/auth/logout")).status_code == 200
    api.client.cookies.set(ACCESS_COOKIE, token or "")
    assert (await api.get("/api/v1/auth/me")).status_code == 401


async def test_password_reset_is_single_use_and_ends_sessions(
    api: Api, db: AsyncSession, no_celery: list[tuple[str, tuple[object, ...]]]
) -> None:
    user = await make_user(db, UserRole.HR_ADMIN, "hr1")
    response = await api.post("/api/v1/auth/password-reset/request", json={"email": user.email})
    assert response.status_code == 202
    assert no_celery and no_celery[0][0].endswith("send_password_reset")
    unknown = await api.post("/api/v1/auth/password-reset/request", json={"email": "nobody@example.com"})
    assert unknown.status_code == 202  # never reveals whether an address exists
    token = password_reset_token(user, get_settings())
    ok = await api.post(
        "/api/v1/auth/password-reset/confirm", json={"token": token, "new_password": "New-password-99"}
    )
    assert ok.status_code == 200
    again = await api.post(
        "/api/v1/auth/password-reset/confirm", json={"token": token, "new_password": "Other-pass-77"}
    )
    assert again.status_code == 422
    assert (await api.login("hr1", "New-password-99")).status_code == 200


async def test_weak_password_rejected(api: Api, db: AsyncSession) -> None:
    user = await make_user(db, UserRole.HR_ADMIN, "hr1")
    token = password_reset_token(user, get_settings())
    response = await api.post(
        "/api/v1/auth/password-reset/confirm", json={"token": token, "new_password": "aaaaaaaaaa"}
    )
    assert response.status_code == 422 and "password" in response.json()["errors"]


async def test_deactivated_user_session_stops_working(api: Api, db: AsyncSession) -> None:
    user = await make_user(db, UserRole.HR_ADMIN, "hr1")
    await api.login("hr1")
    db_user = await db.get(User, user.id)
    assert db_user is not None
    db_user.is_active = False
    await db.commit()
    assert (await api.get("/api/v1/auth/me")).status_code == 401
