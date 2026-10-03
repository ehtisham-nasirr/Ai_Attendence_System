"""Migrations on a fresh database (standards/11): upgrade head, no model drift (`alembic check`), downgrade -1, upgrade again."""

import asyncio
import os
import uuid
from collections.abc import Callable, Iterator

import asyncpg
import pytest
from alembic.config import Config
from conftest import DATABASE_URL
from sqlalchemy import Connection, inspect
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command

_ALEMBIC_INI = os.path.join(os.path.dirname(__file__), "..", "..", "alembic.ini")


def _admin_dsn() -> str:
    return make_url(DATABASE_URL).set(drivername="postgresql").render_as_string(hide_password=False)


async def _admin(sql: str) -> None:
    connection = await asyncpg.connect(_admin_dsn())
    try:
        await connection.execute(sql)
    finally:
        await connection.close()


@pytest.fixture
def fresh_database() -> Iterator[str]:
    name = f"facetrack_migration_{uuid.uuid4().hex[:8]}"
    asyncio.run(_admin(f'CREATE DATABASE "{name}"'))
    try:
        yield make_url(DATABASE_URL).set(database=name).render_as_string(hide_password=False)
    finally:
        asyncio.run(_admin(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


def _config(url: str) -> Config:
    config = Config(_ALEMBIC_INI)
    config.attributes["database_url"] = url
    return config


def _inspect[T](url: str, fn: Callable[[Connection], T]) -> T:
    async def run() -> T:
        engine = create_async_engine(url)
        try:
            async with engine.connect() as connection:
                return await connection.run_sync(fn)
        finally:
            await engine.dispose()

    return asyncio.run(run())


def _tables(connection: Connection) -> set[str]:
    return set(inspect(connection).get_table_names())


def test_upgrade_head_matches_models_then_downgrade_and_upgrade_again(fresh_database: str) -> None:
    config = _config(fresh_database)
    command.upgrade(config, "head")
    assert {"employees", "attendance_days", "recognition_events", "face_enrollments"} <= _inspect(
        fresh_database, _tables
    )
    command.check(config)  # raises if the models and the migrated schema differ
    command.downgrade(config, "-1")
    assert _inspect(fresh_database, _tables) <= {"alembic_version"}
    command.upgrade(config, "head")
    assert "attendance_days" in _inspect(fresh_database, _tables)
