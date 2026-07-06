"""Async SQLAlchemy engine + session factory.

Everything DB-related funnels through here so the rest of the app never touches
engine internals. `get_db` is the FastAPI dependency that hands each request its
own session and guarantees it's closed afterwards.
"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    """Base class all ORM models inherit from."""


engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,  # transparently recycle dead connections
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # let us read attributes after commit
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields a session, always closes it."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
