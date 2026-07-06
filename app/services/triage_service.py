"""The brain of the worker: process one ticket end-to-end.

Flow (mirrors the "journey of a ticket" in the build plan):
  1. Load ticket, mark `processing`.
  2. Cache check: have we triaged identical content before? If yes -> reuse,
     log a `cache_hit`, done. (free + instant)
  3. Otherwise call the LLM, parse+validate JSON. On parse failure, retry with
     exponential backoff (handled by the caller/ARQ, but we also do one inline
     re-ask for robustness).
  4. Save results, mark `triaged`, store result in cache, log `classified`.
  5. Publish a "ticket done" event on Redis pub/sub for live dashboards.

Idempotent by design: processing the same ticket twice just overwrites the same
AI fields with the same values - no duplicated data.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.core.redis import CACHE_TTL_SECONDS, TICKET_EVENTS_CHANNEL, cache_key, get_redis
from app.models.ai_event import AIEvent
from app.models.enums import AIEventType, TicketStatus
from app.models.ticket import Ticket
from app.schemas.triage import TriageResult
from app.services.llm import LLMProvider, get_llm_provider
from app.services.triage_parser import TriageParseError, parse_triage

logger = get_logger("triage")


async def _publish_done(ticket: Ticket) -> None:
    """Notify connected dashboards that this ticket finished."""
    redis = get_redis()
    event = {
        "type": "ticket_updated",
        "id": str(ticket.id),
        "status": ticket.status,
        "category": ticket.category,
        "urgency_score": ticket.urgency_score,
        "subject": ticket.subject,
    }
    try:
        await redis.publish(TICKET_EVENTS_CHANNEL, json.dumps(event))
    except Exception as exc:  # pub/sub must never break triage
        logger.warning("publish failed for ticket %s: %s", ticket.id, exc)


def _apply_result(ticket: Ticket, result: TriageResult) -> None:
    ticket.category = result.category.value
    ticket.urgency_score = result.urgency_score
    ticket.ai_summary = result.summary
    ticket.suggested_reply = result.suggested_reply
    ticket.status = TicketStatus.triaged.value


async def _call_and_parse(
    provider: LLMProvider, subject: str, body: str
) -> tuple[TriageResult, str, int, dict]:
    """Call the LLM once; parse. Returns (result, model, tokens, raw_dict)."""
    resp = await provider.classify(subject, body)
    result = parse_triage(resp.text)
    try:
        raw = json.loads(resp.text) if resp.text.strip().startswith("{") else {"text": resp.text}
    except json.JSONDecodeError:
        raw = {"text": resp.text}
    return result, resp.model, resp.tokens_used, raw


async def process_ticket(db: AsyncSession, ticket_id: uuid.UUID) -> None:
    """Triage a single ticket. Called by the worker (and /reprocess)."""
    ticket = await db.get(Ticket, ticket_id)
    if ticket is None:
        logger.warning("ticket %s not found; skipping", ticket_id)
        return

    logger.info("processing ticket", extra={"ticket_id": str(ticket_id)})
    ticket.status = TicketStatus.processing.value
    await db.commit()

    redis = get_redis()
    provider = get_llm_provider()

    # ---- 1. Cache check ----
    ckey = cache_key(ticket.content_hash)
    try:
        cached = await redis.get(ckey)
    except Exception as exc:
        cached = None
        logger.warning("cache read failed: %s", exc)

    if cached:
        try:
            result = TriageResult.model_validate_json(cached)
            _apply_result(ticket, result)
            db.add(
                AIEvent(
                    ticket_id=ticket.id,
                    event_type=AIEventType.cache_hit.value,
                    model="cache",
                    tokens_used=0,
                    latency_ms=0,
                    raw_response={"cache_key": ckey},
                )
            )
            await db.commit()
            await db.refresh(ticket)
            logger.info("cache hit for ticket %s", ticket_id)
            await _publish_done(ticket)
            return
        except Exception as exc:
            logger.warning("cached value invalid, recomputing: %s", exc)

    # ---- 2. Call the LLM with retries + exponential backoff ----
    delays = [1, 4, 10]  # seconds; index i used before attempt i+1
    last_error: Exception | None = None
    for attempt in range(settings.max_ai_retries):
        start = time.perf_counter()
        try:
            result, model, tokens, raw = await _call_and_parse(
                provider, ticket.subject, ticket.body
            )
            latency_ms = int((time.perf_counter() - start) * 1000)

            _apply_result(ticket, result)
            db.add(
                AIEvent(
                    ticket_id=ticket.id,
                    event_type=AIEventType.classified.value,
                    model=model,
                    tokens_used=tokens,
                    latency_ms=latency_ms,
                    raw_response=raw,
                )
            )
            await db.commit()
            await db.refresh(ticket)

            # populate cache for next identical ticket
            try:
                await redis.set(
                    ckey, result.model_dump_json(), ex=CACHE_TTL_SECONDS
                )
            except Exception as exc:
                logger.warning("cache write failed: %s", exc)

            logger.info(
                "ticket %s triaged: category=%s urgency=%s (%dms, %d tokens)",
                ticket_id, result.category.value, result.urgency_score,
                latency_ms, tokens,
            )
            await _publish_done(ticket)
            return

        except (TriageParseError, Exception) as exc:  # noqa: BLE001
            last_error = exc
            latency_ms = int((time.perf_counter() - start) * 1000)
            db.add(
                AIEvent(
                    ticket_id=ticket.id,
                    event_type=AIEventType.retry.value,
                    model=getattr(provider, "model", settings.llm_provider),
                    latency_ms=latency_ms,
                    raw_response={"error": str(exc), "attempt": attempt + 1},
                )
            )
            await db.commit()
            logger.warning(
                "attempt %d/%d failed for ticket %s: %s",
                attempt + 1, settings.max_ai_retries, ticket_id, exc,
            )
            if attempt < settings.max_ai_retries - 1:
                await asyncio.sleep(delays[min(attempt, len(delays) - 1)])

    # ---- 3. All retries exhausted -> mark failed (graceful degradation) ----
    ticket.status = TicketStatus.failed.value
    db.add(
        AIEvent(
            ticket_id=ticket.id,
            event_type=AIEventType.failed.value,
            model=getattr(provider, "model", settings.llm_provider),
            raw_response={"error": str(last_error)},
        )
    )
    await db.commit()
    await db.refresh(ticket)
    logger.error("ticket %s marked FAILED after retries: %s", ticket_id, last_error)
    await _publish_done(ticket)
