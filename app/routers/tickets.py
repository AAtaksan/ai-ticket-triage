"""Ticket endpoints - the core of the API."""
import math
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rate_limit import enforce_ticket_rate_limit
from app.models.enums import TicketCategory, TicketStatus, UserRole
from app.models.ticket import Ticket
from app.models.user import User
from app.schemas.ticket import (
    PaginatedTickets,
    TicketCreate,
    TicketCreateResponse,
    TicketOut,
    TicketUpdate,
)
from app.services.dependencies import get_current_user, require_agent
from app.services.hashing import compute_content_hash
from app.services.queue import enqueue_triage

router = APIRouter(prefix="/tickets", tags=["tickets"])


async def _get_owned_ticket(
    ticket_id: uuid.UUID, db: AsyncSession, user: User
) -> Ticket:
    """Fetch a ticket, enforcing that customers only see their own; agents see all."""
    ticket = await db.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if user.role != UserRole.agent.value and ticket.user_id != user.id:
        # Don't leak existence to other customers.
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


@router.post("", response_model=TicketCreateResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_ticket(
    payload: TicketCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Accept a ticket, persist it, enqueue AI triage, return 202 immediately."""
    await enforce_ticket_rate_limit(str(user.id))

    ticket = Ticket(
        user_id=user.id,
        subject=payload.subject,
        body=payload.body,
        status=TicketStatus.new.value,
        content_hash=compute_content_hash(payload.subject, payload.body),
    )
    db.add(ticket)
    await db.commit()
    await db.refresh(ticket)

    # Only after the ticket is safely in Postgres do we queue the slow work.
    await enqueue_triage(str(ticket.id))

    return TicketCreateResponse(id=ticket.id, status=TicketStatus.new)


@router.get("", response_model=PaginatedTickets)
async def list_tickets(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    status_filter: TicketStatus | None = Query(default=None, alias="status"),
    category: TicketCategory | None = Query(default=None),
    sort: str = Query(default="-created_at", description="e.g. -urgency_score, created_at"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
):
    """List tickets with filtering, sorting, pagination.

    Customers see only their own tickets; agents see everything."""
    conditions = []
    if user.role != UserRole.agent.value:
        conditions.append(Ticket.user_id == user.id)
    if status_filter is not None:
        conditions.append(Ticket.status == status_filter.value)
    if category is not None:
        conditions.append(Ticket.category == category.value)

    # --- sorting (whitelist columns to avoid injection) ---
    sortable = {
        "created_at": Ticket.created_at,
        "urgency_score": Ticket.urgency_score,
        "updated_at": Ticket.updated_at,
    }
    desc = sort.startswith("-")
    key = sort[1:] if desc else sort
    column = sortable.get(key, Ticket.created_at)
    order = column.desc() if desc else column.asc()

    base = select(Ticket)
    if conditions:
        base = base.where(*conditions)

    total = await db.scalar(
        select(func.count()).select_from(base.subquery())
    ) or 0

    rows = (
        await db.scalars(
            base.order_by(order).offset((page - 1) * size).limit(size)
        )
    ).all()

    return PaginatedTickets(
        items=[TicketOut.model_validate(t) for t in rows],
        total=total,
        page=page,
        size=size,
        pages=math.ceil(total / size) if total else 0,
    )


@router.get("/{ticket_id}", response_model=TicketOut)
async def get_ticket(
    ticket_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ticket = await _get_owned_ticket(ticket_id, db, user)
    return ticket


@router.patch("/{ticket_id}", response_model=TicketOut)
async def update_ticket(
    ticket_id: uuid.UUID,
    payload: TicketUpdate,
    db: AsyncSession = Depends(get_db),
    agent: User = Depends(require_agent),
):
    """Agent override: correct the AI or change status. Agents only."""
    ticket = await db.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")

    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        if field in {"status", "category"} and value is not None:
            value = value.value  # enum -> str
        setattr(ticket, field, value)

    await db.commit()
    await db.refresh(ticket)
    return ticket


@router.post("/{ticket_id}/reprocess", response_model=TicketCreateResponse,
             status_code=status.HTTP_202_ACCEPTED)
async def reprocess_ticket(
    ticket_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    agent: User = Depends(require_agent),
):
    """Re-run AI triage on a failed/misclassified ticket. Agents only."""
    ticket = await db.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")

    ticket.status = TicketStatus.new.value
    await db.commit()
    await enqueue_triage(str(ticket.id))
    return TicketCreateResponse(
        id=ticket.id, status=TicketStatus.new, message="Reprocessing queued."
    )
