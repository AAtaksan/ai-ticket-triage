"""Liveness/readiness probe used by hosting platforms."""
from fastapi import APIRouter
from sqlalchemy import text

from app.core.database import engine
from app.core.redis import get_redis

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    status = {"api": "ok", "db": "unknown", "redis": "unknown"}

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        status["db"] = "ok"
    except Exception:
        status["db"] = "down"

    try:
        pong = await get_redis().ping()
        status["redis"] = "ok" if pong else "down"
    except Exception:
        status["redis"] = "down"

    return status
