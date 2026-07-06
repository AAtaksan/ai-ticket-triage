"""FastAPI application entrypoint - 'the waiter'.

Wires together routers, the Redis pub/sub listener for WebSockets, static
dashboard files, and startup/shutdown lifecycle.
"""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.routers import auth, health, stats, tickets, ws

logger = get_logger("app")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    logger.info("starting %s (env=%s)", settings.app_name, settings.environment)
    # Start the Redis->WebSocket relay task.
    listener_task = asyncio.create_task(ws.redis_listener())
    try:
        yield
    finally:
        listener_task.cancel()
        try:
            await listener_task
        except asyncio.CancelledError:
            pass
        logger.info("shutdown complete")


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Async AI support-ticket triage system.",
    lifespan=lifespan,
)

# CORS - open in dev; lock down origins in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(tickets.router)
app.include_router(stats.router)
app.include_router(ws.router)


@app.get("/", include_in_schema=False)
async def root():
    """Serve the dashboard if present, else a hint."""
    index = STATIC_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    return {"message": f"{settings.app_name} API. Docs at /docs"}


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
