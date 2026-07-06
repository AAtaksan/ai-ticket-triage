"""Simple per-user rate limiting backed by Redis.

We use a fixed-window counter: one Redis key per (user, minute-bucket) with a
60s TTL. First hit sets the key to 1 and expires it; each hit increments. Over
the limit -> 429. Redis being down should not take the API down, so on error we
fail OPEN (allow the request) and log it.
"""
import time

from fastapi import HTTPException, status

from app.core.config import settings
from app.core.logging import get_logger
from app.core.redis import get_redis

logger = get_logger("rate_limit")


async def enforce_ticket_rate_limit(user_id: str) -> None:
    limit = settings.rate_limit_tickets_per_minute
    if limit <= 0:
        return
    bucket = int(time.time() // 60)
    key = f"rl:tickets:{user_id}:{bucket}"
    try:
        redis = get_redis()
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, 60)
    except Exception as exc:  # fail open
        logger.warning("rate limiter unavailable, allowing request: %s", exc)
        return
    if count > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded: max {limit} tickets per minute.",
            headers={"Retry-After": "60"},
        )
