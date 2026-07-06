"""Helper to enqueue jobs onto ARQ from the API side.

The API and the worker share one Redis. The API pushes `process_ticket` jobs;
the worker (app/workers/worker.py) defines and runs them.
"""
from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.core.config import settings

_pool: ArqRedis | None = None


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(settings.redis_url)


async def get_arq_pool() -> ArqRedis:
    global _pool
    if _pool is None:
        _pool = await create_pool(_redis_settings())
    return _pool


async def enqueue_triage(ticket_id: str) -> None:
    pool = await get_arq_pool()
    await pool.enqueue_job("process_ticket", ticket_id)
