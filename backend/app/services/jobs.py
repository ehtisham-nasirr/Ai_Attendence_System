"""Background job status (imports, report exports) kept in Redis for 24 hours (standards/14: 202 + job)."""

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from app.core.redis import get_async_redis, get_sync_redis

_TTL_SECONDS = 24 * 3600


def _key(job_id: str) -> str:
    return f"job:{job_id}"


async def create_job(kind: str, owner_user_id: int) -> str:
    job_id = uuid.uuid4().hex
    record = {
        "id": job_id,
        "kind": kind,
        "owner": owner_user_id,
        "status": "queued",
        "created_at": datetime.now(UTC).isoformat(),
        "message": None,
        "result": None,
        "file": None,
    }
    await get_async_redis().set(_key(job_id), json.dumps(record), ex=_TTL_SECONDS)
    return job_id


async def get_job(job_id: str) -> dict[str, Any] | None:
    raw = await get_async_redis().get(_key(job_id))
    return None if raw is None else dict(json.loads(raw))


def update_job_sync(job_id: str, **changes: Any) -> None:
    redis = get_sync_redis()
    raw = redis.get(_key(job_id))
    if raw is None:
        return
    record = json.loads(raw)
    record.update(changes)
    redis.set(_key(job_id), json.dumps(record, default=str), ex=_TTL_SECONDS)
