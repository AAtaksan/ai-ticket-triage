"""The `tickets` table - the heart of the app.

Lifecycle of `status`:  new -> processing -> triaged   (or -> failed)
The AI-filled columns (category, urgency_score, ai_summary, suggested_reply)
are NULL until the worker finishes triage.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import TicketStatus


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    subject: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[str] = mapped_column(
        String, nullable=False, default=TicketStatus.new.value, index=True
    )

    # --- AI-filled fields (NULL until triaged) ---
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    urgency_score: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggested_reply: Mapped[str | None] = mapped_column(Text, nullable=True)

    # sha256(subject + body) - the cache key for dedup.
    content_hash: Mapped[str] = mapped_column(String, nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped["User"] = relationship(back_populates="tickets")  # noqa: F821
    ai_events: Mapped[list["AIEvent"]] = relationship(  # noqa: F821
        back_populates="ticket", cascade="all, delete-orphan"
    )
