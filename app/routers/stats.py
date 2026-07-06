"""Dashboard metrics endpoint."""
from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.ai_event import AIEvent
from app.models.enums import AIEventType
from app.models.ticket import Ticket
from app.models.user import User
from app.schemas.stats import (
    CategoryCount,
    StatsResponse,
    StatusCount,
)
from app.services.dependencies import get_current_user

router = APIRouter(tags=["stats"])


@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    total = await db.scalar(select(func.count()).select_from(Ticket)) or 0

    status_rows = (
        await db.execute(
            select(Ticket.status, func.count()).group_by(Ticket.status)
        )
    ).all()
    category_rows = (
        await db.execute(
            select(Ticket.category, func.count())
            .where(Ticket.category.is_not(None))
            .group_by(Ticket.category)
        )
    ).all()

    avg_urgency = await db.scalar(select(func.avg(Ticket.urgency_score)))

    # cache hit rate = cache_hit events / (classified + cache_hit) events
    hit_count = await db.scalar(
        select(func.count()).where(AIEvent.event_type == AIEventType.cache_hit.value)
    ) or 0
    classified_count = await db.scalar(
        select(func.count()).where(AIEvent.event_type == AIEventType.classified.value)
    ) or 0
    denom = hit_count + classified_count
    cache_hit_rate = (hit_count / denom) if denom else 0.0

    avg_latency = await db.scalar(
        select(func.avg(AIEvent.latency_ms)).where(AIEvent.latency_ms.is_not(None))
    )
    total_tokens = await db.scalar(
        select(func.coalesce(func.sum(AIEvent.tokens_used), 0))
    ) or 0

    return StatsResponse(
        total_tickets=total,
        by_status=[StatusCount(status=s or "unknown", count=c) for s, c in status_rows],
        by_category=[CategoryCount(category=cat, count=c) for cat, c in category_rows],
        avg_urgency=float(avg_urgency) if avg_urgency is not None else None,
        cache_hit_rate=round(cache_hit_rate, 4),
        avg_ai_latency_ms=float(avg_latency) if avg_latency is not None else None,
        total_tokens_used=int(total_tokens),
    )
