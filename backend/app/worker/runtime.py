"""Runs async domain services from (synchronous) Celery tasks.

Each worker process keeps one event loop and one database engine bound to it, so connections are
reused across tasks instead of being created per task.
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

_loop: asyncio.AbstractEventLoop | None = None
_engine: AsyncEngine | None = None
_sessions: async_sessionmaker[AsyncSession] | None = None


def _ensure() -> tuple[asyncio.AbstractEventLoop, async_sessionmaker[AsyncSession]]:
    global _loop, _engine, _sessions  # noqa: PLW0603  # per-process singletons
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
        _engine = create_async_engine(
            get_settings().database_url.get_secret_value(), pool_size=5, max_overflow=5, pool_pre_ping=True
        )
        _sessions = async_sessionmaker(_engine, expire_on_commit=False)
    assert _sessions is not None  # noqa: S101  # set together with the loop above
    return _loop, _sessions


def run_with_session[T](fn: Callable[[AsyncSession], Awaitable[T]]) -> T:
    loop, sessions = _ensure()

    async def runner() -> T:
        async with sessions() as session:
            return await fn(session)

    return loop.run_until_complete(runner())


def run[T](coroutine_factory: Callable[[], Awaitable[T]]) -> T:
    loop, _ = _ensure()
    return loop.run_until_complete(coroutine_factory())


def reset_for_tests(**_: Any) -> None:
    global _loop, _engine, _sessions  # noqa: PLW0603
    _loop = _engine = _sessions = None
