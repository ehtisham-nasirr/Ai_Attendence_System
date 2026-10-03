"""Async SQLAlchemy engine and sessions (standards/05)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    return create_async_engine(
        get_settings().database_url.get_secret_value(), pool_size=10, max_overflow=10, pool_pre_ping=True
    )


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request, rolled back if anything is left uncommitted."""
    async with get_sessionmaker()() as session:
        try:
            yield session
        finally:
            if session.in_transaction():
                await session.rollback()


@asynccontextmanager
async def transaction(db: AsyncSession) -> AsyncIterator[AsyncSession]:
    """One transaction per business operation (standards/05).

    Works whether or not the session already began implicitly (e.g. after loading the current user).
    """
    if db.in_transaction():
        try:
            yield db
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
    else:
        async with db.begin():
            yield db
