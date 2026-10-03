"""Read-only database access for the engine (gallery, cameras, settings). The engine never writes."""

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


def create_session_factory(database_url: str) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(database_url, pool_size=2, max_overflow=2, pool_pre_ping=True)
    return engine, async_sessionmaker(engine, expire_on_commit=False)
