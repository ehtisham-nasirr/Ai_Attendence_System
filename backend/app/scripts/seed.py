"""Seeds a fresh database: default settings, a default location and shift, and the first Super Admin.

Credentials come from the environment, never from code:
    SEED_ADMIN_USERNAME, SEED_ADMIN_EMAIL, SEED_ADMIN_PASSWORD
Safe to run more than once (existing rows are left alone).

    uv run python -m app.scripts.seed
"""

import asyncio
import os
from datetime import time

from facetrack_common.constants import AuthProvider, UserRole
from facetrack_common.models import Location, Shift, User
from facetrack_common.settings_keys import SETTINGS
from sqlalchemy import select

from app.core.db import get_sessionmaker, transaction
from app.core.security import hash_password, validate_password_policy
from app.repositories import system_repo


async def seed() -> None:
    username = os.environ.get("SEED_ADMIN_USERNAME", "")
    email = os.environ.get("SEED_ADMIN_EMAIL", "")
    password = os.environ.get("SEED_ADMIN_PASSWORD", "")
    async with get_sessionmaker()() as db, transaction(db):
        stored = await system_repo.all_settings(db)
        for key, spec in SETTINGS.items():
            if key not in stored and not spec.secret:
                await system_repo.upsert_setting(
                    db, key, spec.adapter.dump_python(spec.validate(spec.default), mode="json")
                )
        if (await db.scalars(select(Location.id))).first() is None:
            db.add(Location(name="Head Office", address=None, timezone="Asia/Karachi"))
        if (await db.scalars(select(Shift.id))).first() is None:
            db.add(
                Shift(
                    name="General 09:00-18:00",
                    start_time=time(9),
                    end_time=time(18),
                    grace_in_min=15,
                    grace_out_min=15,
                    half_day_pct=50,
                    is_night_shift=False,
                    weekly_offs=[6, 7],
                )
            )
        has_admin = (await db.scalars(select(User.id).where(User.role == UserRole.SUPER_ADMIN))).first()
        if has_admin is None:
            if not (username and email and password):
                raise SystemExit(
                    "Set SEED_ADMIN_USERNAME, SEED_ADMIN_EMAIL and SEED_ADMIN_PASSWORD to create the admin."
                )
            validate_password_policy(password)
            db.add(
                User(
                    name="Administrator",
                    username=username,
                    email=email,
                    role=UserRole.SUPER_ADMIN,
                    auth_provider=AuthProvider.LOCAL,
                    password_hash=hash_password(password),
                    is_active=True,
                    failed_login_attempts=0,
                    session_version=1,
                )
            )
    print("seed complete")


if __name__ == "__main__":
    asyncio.run(seed())
