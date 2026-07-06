"""Seed the database with realistic fake tickets so demos never look empty.

Usage (inside the api container or with env pointing at your DB):
    python -m scripts.seed

It registers a demo agent + customer, then submits ~15 varied tickets through
the same code path the API uses (hash + enqueue), so the worker will triage them.
"""
import asyncio
import random

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.enums import TicketStatus, UserRole
from app.models.ticket import Ticket
from app.models.user import User
from app.services.hashing import compute_content_hash
from app.services.queue import enqueue_triage
from sqlalchemy import select

SAMPLE_TICKETS = [
    ("Charged twice this month!!", "I see two $29 charges for the same subscription. Please refund one immediately."),
    ("App crashes on startup", "Every time I open the mobile app it crashes instantly on my iPhone 14."),
    ("Want a refund", "The product didn't work as advertised, I'd like my money back please."),
    ("Can't log into my account", "I forgot my password and the reset email never arrives."),
    ("How do I export my data?", "Just a quick question about exporting reports to CSV."),
    ("URGENT: production is down", "Our whole team can't access the dashboard, this is business-critical!"),
    ("Billing address change", "I moved and need to update the billing address on my invoice."),
    ("Feature not working", "The bulk-upload button does nothing when I click it."),
    ("Double billed again", "This is the second month in a row I've been charged twice. Very frustrated."),
    ("Account locked out", "After a few login attempts my account got locked. Please help."),
    ("Thank you!", "Just wanted to say the new update is great. No issues."),
    ("Payment failed but money taken", "My card was charged but the order shows as failed."),
    ("Bug in report totals", "The monthly totals don't add up correctly in the analytics page."),
    ("Cancel my subscription", "Please cancel and refund the last charge, I no longer need the service."),
    ("Slow performance", "The app has been really slow to load pages for the last two days."),
]


async def main() -> None:
    async with AsyncSessionLocal() as db:
        # demo agent
        agent = await db.scalar(select(User).where(User.email == "agent@demo.com"))
        if agent is None:
            agent = User(email="agent@demo.com",
                         hashed_password=hash_password("password123"),
                         role=UserRole.agent.value)
            db.add(agent)

        customer = await db.scalar(select(User).where(User.email == "customer@demo.com"))
        if customer is None:
            customer = User(email="customer@demo.com",
                            hashed_password=hash_password("password123"),
                            role=UserRole.customer.value)
            db.add(customer)
        await db.commit()
        await db.refresh(customer)

        created_ids = []
        for subject, body in SAMPLE_TICKETS:
            ticket = Ticket(
                user_id=customer.id,
                subject=subject,
                body=body,
                status=TicketStatus.new.value,
                content_hash=compute_content_hash(subject, body),
            )
            db.add(ticket)
            await db.commit()
            await db.refresh(ticket)
            created_ids.append(str(ticket.id))

    # enqueue triage jobs (worker will process them)
    for tid in created_ids:
        await enqueue_triage(tid)

    print(f"Seeded {len(created_ids)} tickets.")
    print("Login:  agent@demo.com / password123  (agent)")
    print("        customer@demo.com / password123  (customer)")


if __name__ == "__main__":
    asyncio.run(main())
