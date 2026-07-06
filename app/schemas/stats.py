"""Response shape for the /stats dashboard endpoint."""
from pydantic import BaseModel


class CategoryCount(BaseModel):
    category: str
    count: int


class StatusCount(BaseModel):
    status: str
    count: int


class StatsResponse(BaseModel):
    total_tickets: int
    by_status: list[StatusCount]
    by_category: list[CategoryCount]
    avg_urgency: float | None
    cache_hit_rate: float          # 0..1 over all AI events
    avg_ai_latency_ms: float | None
    total_tokens_used: int
