"""Fixed-window rate limiting in Redis (standards/06: rate-limit /auth/login and API-key endpoints)."""

from app.core.exceptions import RateLimited
from app.core.redis import get_async_redis


async def enforce_rate_limit(bucket: str, limit_per_minute: int) -> None:
    redis = get_async_redis()
    key = f"ratelimit:{bucket}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, 60)
    if count > limit_per_minute:
        raise RateLimited()
