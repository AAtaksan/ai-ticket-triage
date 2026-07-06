"""Test fixtures.

Tests run against an in-memory SQLite DB (via aiosqlite) so they need NO
Postgres/Redis. We override the `get_db` dependency and the Redis-backed pieces
(rate limiter + queue) so the API layer can be tested in isolation.

Set LLM_PROVIDER=mock (default) so no external AI calls happen.
"""
import asyncio

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def client(session_factory, monkeypatch):
    async def override_get_db():
        async with session_factory() as s:
            yield s

    # No-op the Redis-backed rate limiter and queue for API tests.
    async def noop_rate_limit(_user_id: str):
        return None

    async def noop_enqueue(_ticket_id: str):
        return None

    monkeypatch.setattr("app.routers.tickets.enforce_ticket_rate_limit", noop_rate_limit)
    monkeypatch.setattr("app.routers.tickets.enqueue_triage", noop_enqueue)

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def auth_headers(client):
    """Register + login a customer, return Authorization headers."""
    await client.post(
        "/auth/register",
        json={"email": "cust@example.com", "password": "supersecret1", "role": "customer"},
    )
    resp = await client.post(
        "/auth/login",
        json={"email": "cust@example.com", "password": "supersecret1"},
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
