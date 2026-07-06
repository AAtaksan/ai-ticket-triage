"""ARQ worker - 'the cook'.

Run with:  arq app.workers.worker.WorkerSettings

ARQ gives us for free:
  * pulling jobs from Redis,
  * concurrency (multiple jobs at once),
  * automatic retries of jobs that raise (on top of our own inline retry loop).

Each job opens its own DB session, runs triage, and closes it.
"""
import uuid

from arq.connections import RedisSettings
from arq.worker import func

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.logging import configure_logging, get_logger
from app.services.triage_service import process_ticket

logger = get_logger("worker")


async def process_ticket_job(ctx: dict, ticket_id: str) -> str:
    """ARQ task: triage one ticket by id.

    The API enqueues this via `enqueue_job("process_ticket", ticket_id)`; the
    name is bound explicitly below with arq's `func(..., name=...)`.
    """
    async with AsyncSessionLocal() as db:
        await process_ticket(db, uuid.UUID(ticket_id))
    return ticket_id


async def startup(ctx: dict) -> None:
    configure_logging()
    logger.info("worker started (provider=%s)", settings.llm_provider)


async def shutdown(ctx: dict) -> None:
    logger.info("worker shutting down")


class WorkerSettings:
    """ARQ reads this class to configure the worker process."""

    # Bind the coroutine to the exact name the API enqueues.
    functions = [func(process_ticket_job, name="process_ticket")]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    on_startup = startup
    on_shutdown = shutdown
    max_tries = settings.max_ai_retries
    job_timeout = 60
