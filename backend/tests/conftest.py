"""Backend test fixtures.

Uses a real PostgreSQL and Redis: TEST_DATABASE_URL / TEST_REDIS_URL when set (local/CI services),
otherwise throw-away testcontainers (standards/11). The schema comes from the Alembic migrations.
No real faces are used: the engine client is replaced by a scripted fake.
"""

import base64
import os
import tempfile
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, time
from typing import Any

import numpy as np
import pytest
from facetrack_common.crypto import generate_key_b64

# --------------------------------------------------------------------------- environment (before app import)


def _start_services() -> tuple[str, str]:
    database_url = os.environ.get("TEST_DATABASE_URL")
    redis_url = os.environ.get("TEST_REDIS_URL")
    if database_url and redis_url:
        return database_url, redis_url
    from testcontainers.postgres import PostgresContainer
    from testcontainers.redis import RedisContainer

    postgres = PostgresContainer("pgvector/pgvector:pg16", driver="asyncpg").start()
    redis = RedisContainer("redis:7").start()
    return (
        database_url or postgres.get_connection_url(),
        redis_url or f"redis://{redis.get_container_host_ip()}:{redis.get_exposed_port(6379)}/0",
    )


DATABASE_URL, REDIS_URL = _start_services()
MEDIA_ROOT = tempfile.mkdtemp(prefix="facetrack-media-")
os.environ.update(
    {
        "DATABASE_URL": DATABASE_URL,
        "REDIS_URL": REDIS_URL,
        "JWT_SECRET": "test-jwt-secret-not-for-production",
        "ENCRYPTION_KEY": generate_key_b64(),
        "ENGINE_API_TOKEN": "engine-token",
        "ENGINE_NODES": '{"node-1": "http://engine-test:8100"}',
        "COOKIE_SECURE": "false",
        "MEDIA_ROOT": MEDIA_ROOT,
        "ENVIRONMENT": "development",
        "LOG_LEVEL": "WARNING",
    }
)

import httpx  # noqa: E402
from facetrack_common.constants import (  # noqa: E402
    CRYPTO_PURPOSE_CAMERA_URL,
    CRYPTO_PURPOSE_EMBEDDING,
    AuthProvider,
    CameraRole,
    EmployeeStatus,
    UserRole,
)
from facetrack_common.models import Camera, Department, Employee, Location, Shift, User  # noqa: E402
from facetrack_common.schemas.engine import CameraTestResult, EmbedResult  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.core.crypto import get_cipher  # noqa: E402
from app.core.db import get_engine, get_sessionmaker  # noqa: E402
from app.core.redis import get_async_redis, get_sync_redis  # noqa: E402
from app.core.security import CSRF_COOKIE, hash_password  # noqa: E402
from app.main import create_app  # noqa: E402

PASSWORD = "Correct-horse-42"


def _run_migrations() -> None:
    from alembic.config import Config

    from alembic import command

    config = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    config.attributes["database_url"] = DATABASE_URL
    command.downgrade(config, "base")
    command.upgrade(config, "head")


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> Iterator[None]:
    _run_migrations()
    yield


@pytest.fixture(autouse=True)
async def clean_state() -> AsyncIterator[None]:
    """Each test starts from empty tables and an empty Redis database."""
    async with get_engine().begin() as conn:
        tables = (
            await conn.execute(
                text(
                    "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename <> 'alembic_version' "
                    "AND tablename NOT LIKE 'recognition_events_%'"
                )
            )
        ).scalars()
        await conn.execute(text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE"))
    await get_async_redis().flushdb()
    yield


@pytest.fixture
async def db() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session


# --------------------------------------------------------------------------- fake engine


@dataclass
class FakeEngine:
    """Scripted stand-in for the internal engine API (no faces, no models)."""

    notifications: list[str] = field(default_factory=list)
    next_vectors: list[np.ndarray] = field(default_factory=list)
    reject_reason: str | None = None
    available: bool = True
    calls: int = 0
    statuses: dict[str, Any] = field(default_factory=dict)

    def vector(self, seed: int, dim: int = 128) -> np.ndarray:
        rng = np.random.default_rng(seed)
        v = rng.standard_normal(dim).astype(np.float32)
        return v / np.linalg.norm(v)

    async def embed_photo(self, image: bytes, node: str | None = None) -> EmbedResult:
        from app.core.exceptions import EngineUnavailable

        self.calls += 1
        if not self.available:
            raise EngineUnavailable()
        if self.reject_reason:
            return EmbedResult(
                accepted=False,
                rejection_reason=self.reject_reason,
                face_count=1,  # type: ignore[arg-type]
                face_width_px=90,
                model_name="sface",
            )
        vector = self.next_vectors.pop(0) if self.next_vectors else self.vector(self.calls)
        token = get_cipher().encrypt_embedding(vector, CRYPTO_PURPOSE_EMBEDDING)
        return EmbedResult(
            accepted=True,
            face_count=1,
            face_width_px=160,
            detector_score=0.95,
            quality_score=0.82,
            blur_variance=150.0,
            model_name="sface",
            embedding_dim=len(vector),
            embedding_encrypted=base64.b64encode(token).decode(),
        )

    async def test_camera(
        self, camera_id: int, node: str | None, use_substream: bool = False
    ) -> CameraTestResult:
        return CameraTestResult(ok=True, width=1920, height=1080, codec="h264", snapshot_jpeg_b64="AAAA")

    async def notify_engines(self, command: str) -> None:
        self.notifications.append(command)


@pytest.fixture(autouse=True)
def fake_engine(monkeypatch: pytest.MonkeyPatch) -> FakeEngine:
    from app.services import engine_client, mediamtx

    fake = FakeEngine()
    monkeypatch.setattr(engine_client, "embed_photo", fake.embed_photo)
    monkeypatch.setattr(engine_client, "test_camera", fake.test_camera)
    monkeypatch.setattr(engine_client, "notify_engines", fake.notify_engines)

    async def no_op(*_: Any, **__: Any) -> bool:
        return True

    monkeypatch.setattr(mediamtx, "upsert_path", no_op)
    monkeypatch.setattr(mediamtx, "delete_path", no_op)
    return fake


@pytest.fixture(autouse=True)
def no_celery(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, tuple[Any, ...]]]:
    """Celery tasks enqueued by the API are recorded instead of sent to a broker."""
    from app.worker import dispatch

    sent: list[tuple[str, tuple[Any, ...]]] = []
    monkeypatch.setattr(dispatch, "_send", lambda name, *args, **kwargs: sent.append((name, args)))
    return sent


# --------------------------------------------------------------------------- factories


async def make_user(
    db: AsyncSession, role: UserRole, username: str | None = None, employee_id: int | None = None
) -> User:
    username = username or f"{role.value}-{datetime.now(UTC).timestamp()}"
    user = User(
        name=username,
        username=username,
        email=f"{username}@example.com",
        role=role,
        auth_provider=AuthProvider.LOCAL,
        password_hash=hash_password(PASSWORD),
        employee_id=employee_id,
        is_active=True,
        failed_login_attempts=0,
        session_version=1,
    )
    db.add(user)
    await db.commit()
    return user


async def make_org(db: AsyncSession) -> dict[str, Any]:
    location = Location(name="HQ", timezone="Asia/Karachi")
    shift = Shift(
        name="Day",
        start_time=time(9),
        end_time=time(18),
        grace_in_min=15,
        grace_out_min=15,
        half_day_pct=50,
        is_night_shift=False,
        weekly_offs=[6, 7],
    )
    night = Shift(
        name="Night",
        start_time=time(22),
        end_time=time(6),
        grace_in_min=15,
        grace_out_min=15,
        half_day_pct=50,
        is_night_shift=True,
        weekly_offs=[],
    )
    sales = Department(name="Sales", code="SAL")
    finance = Department(name="Finance", code="FIN")
    db.add_all([location, shift, night, sales, finance])
    await db.commit()
    return {"location": location, "shift": shift, "night": night, "sales": sales, "finance": finance}


async def make_employee(
    db: AsyncSession,
    org: dict[str, Any],
    code: str,
    department: str = "sales",
    consent: bool = True,
    shift: str = "shift",
    created_at: datetime | None = None,
) -> Employee:
    employee = Employee(
        employee_code=code,
        full_name=f"Employee {code}",
        department_id=org[department].id,
        shift_id=org[shift].id,
        location_id=org["location"].id,
        status=EmployeeStatus.ACTIVE,
        consent_signed_at=datetime(2026, 9, 1, tzinfo=UTC) if consent else None,
    )
    if created_at is not None:
        employee.created_at = created_at
    db.add(employee)
    await db.commit()
    return employee


async def make_camera(
    db: AsyncSession,
    org: dict[str, Any],
    name: str,
    role: CameraRole,
    url: str = "rtsp://u:secret@10.0.0.5/1",
) -> Camera:
    camera = Camera(
        location_id=org["location"].id,
        name=name,
        role=role,
        engine_node="node-1",
        is_enabled=True,
        rtsp_url_encrypted=get_cipher().encrypt_str(url, CRYPTO_PURPOSE_CAMERA_URL),
    )
    db.add(camera)
    await db.commit()
    return camera


# --------------------------------------------------------------------------- HTTP client


class Api:
    """httpx client against the ASGI app, with login and CSRF handled like the portal does."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def login(self, username: str, password: str = PASSWORD) -> httpx.Response:
        response = await self.client.post(
            "/api/v1/auth/login", json={"username": username, "password": password}
        )
        csrf = self.client.cookies.get(CSRF_COOKIE)
        if csrf:
            self.client.headers["X-CSRF-Token"] = csrf
        return response

    async def as_user(self, user: User) -> "Api":
        response = await self.login(user.username)
        assert response.status_code == 200, response.text
        return self

    def __getattr__(self, name: str) -> Any:
        return getattr(self.client, name)


@pytest.fixture
async def api() -> AsyncIterator[Api]:
    app = create_app()
    transport = httpx.ASGITransport(app=app, client=("10.1.2.3", 50000))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield Api(client)


@pytest.fixture
async def make_api() -> AsyncIterator[Any]:
    """Several independent clients (one per user) in the same test."""
    clients: list[httpx.AsyncClient] = []
    app = create_app()

    async def factory(user: User | None = None) -> Api:
        transport = httpx.ASGITransport(app=app, client=("10.1.2.3", 50000))
        client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
        clients.append(client)
        api_client = Api(client)
        return await api_client.as_user(user) if user else api_client

    yield factory
    for client in clients:
        await client.aclose()


__all__ = ["get_sync_redis"]
