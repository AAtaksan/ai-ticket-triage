"""Shared async Redis client.

Redis pulls triple duty in this project:
  1. Cache   - AI results keyed by content_hash (the "warm pizza" trick).
  2. Queue   - ARQ stores jobs here (handled by arq's own pool).
  3. Pub/Sub - worker publishes "ticket done" events; the API relays them to
               connected WebSocket dashboards.
"""
from redis.asyncio import Redis, from_url

from app.core.config import settings

# Channel used for the worker -> API "ticket finished" notifications.
TICKET_EVENTS_CHANNEL = "ticket_events"

# Cache TTL: how long we remember an AI answer for identical content.
CACHE_TTL_SECONDS = 60 * 60 * 24  # 24 hours


_redis: Redis | None = None


def get_redis() -> Redis:
    """Lazily create a process-wide Redis client (decodes to str)."""
    global _redis
    if _redis is None:
        _redis = from_url(settings.redis_url, decode_responses=True)
    return _redis


def cache_key(content_hash: str) -> str:
    return f"ai_result:{content_hash}"
