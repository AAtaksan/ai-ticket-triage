"""The contract for what the LLM must return.

The worker validates the model's raw JSON against `TriageResult`. If the AI
returns junk (missing fields, urgency=15, unknown category), validation fails
and we retry - this is what keeps AI output from corrupting our database.
"""
from pydantic import BaseModel, Field, field_validator

from app.models.enums import TicketCategory


class TriageResult(BaseModel):
    category: TicketCategory
    urgency_score: int = Field(ge=1, le=10)
    summary: str = Field(min_length=1, max_length=300)
    suggested_reply: str = Field(min_length=1, max_length=2000)

    @field_validator("urgency_score", mode="before")
    @classmethod
    def clamp_urgency(cls, v):
        """Never trust the AI blindly - clamp to 1..10 even if it says 15."""
        try:
            v = int(v)
        except (TypeError, ValueError):
            return v
        return max(1, min(10, v))


class TriageResultMeta(BaseModel):
    """What the provider returns alongside the parsed result."""
    result: TriageResult
    model: str
    tokens_used: int
    raw_response: dict
