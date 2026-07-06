"""Request/response shapes for tickets."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import TicketCategory, TicketStatus


class TicketCreate(BaseModel):
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=10_000)


class TicketCreateResponse(BaseModel):
    """The instant 202 response - AI hasn't run yet."""
    id: uuid.UUID
    status: TicketStatus
    message: str = "Ticket received. AI triage in progress."


class TicketUpdate(BaseModel):
    """Agent override. Every field optional - only send what you change."""
    status: TicketStatus | None = None
    category: TicketCategory | None = None
    urgency_score: int | None = Field(default=None, ge=1, le=10)
    suggested_reply: str | None = None


class TicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    user_id: uuid.UUID
    subject: str
    body: str
    status: TicketStatus
    category: TicketCategory | None
    urgency_score: int | None
    ai_summary: str | None
    suggested_reply: str | None
    created_at: datetime
    updated_at: datetime


class PaginatedTickets(BaseModel):
    items: list[TicketOut]
    total: int
    page: int
    size: int
    pages: int
