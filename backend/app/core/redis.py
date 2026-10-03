"""Redis clients: async for the API (rate limits, sessions, live fan-out), sync for Celery tasks."""

from functools import lru_cache
from typing import Any

import redis
import redis.asyncio as aioredis

from app.core.config import get_settings


@lru_cache
def get_async_redis() -> "aioredis.Redis":
    client: aioredis.Redis = aioredis.Redis.from_url(
        get_settings().redis_url.get_secret_value(), decode_responses=True
    )
    return client


@lru_cache
def get_sync_redis() -> Any:
    """Typed as Any: redis-py annotates sync replies as `Awaitable | Any`, which is unusable."""
    return redis.Redis.from_url(get_settings().redis_url.get_secret_value(), decode_responses=True)
