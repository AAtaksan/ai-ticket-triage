"""WebSocket endpoint for live dashboard updates.

Design: the worker publishes "ticket done" messages to a Redis pub/sub channel.
A single background task in the API process subscribes to that channel and
fan-outs each message to all connected WebSocket clients. This keeps the worker
and API decoupled - the worker never talks to sockets directly.
"""
import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.logging import get_logger
from app.core.redis import TICKET_EVENTS_CHANNEL, get_redis

logger = get_logger("ws")
router = APIRouter(tags=["websocket"])


class ConnectionManager:
    """Tracks live WebSocket connections and broadcasts to them."""

    def __init__(self) -> None:
        self.active: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self.active.add(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self.active.discard(ws)

    async def broadcast(self, message: str) -> None:
        async with self._lock:
            targets = list(self.active)
        for ws in targets:
            try:
                await ws.send_text(message)
            except Exception:
                await self.disconnect(ws)


manager = ConnectionManager()


async def redis_listener() -> None:
    """Background task: relay Redis pub/sub messages to all sockets.

    Started on app startup (see app/main.py lifespan)."""
    redis = get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(TICKET_EVENTS_CHANNEL)
    logger.info("subscribed to %s", TICKET_EVENTS_CHANNEL)
    try:
        async for message in pubsub.listen():
            if message is None or message.get("type") != "message":
                continue
            await manager.broadcast(message["data"])
    except asyncio.CancelledError:
        await pubsub.unsubscribe(TICKET_EVENTS_CHANNEL)
        raise
    except Exception as exc:
        logger.error("redis listener crashed: %s", exc)


@router.websocket("/ws/tickets")
async def ws_tickets(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # We don't expect client messages; this keeps the socket open and
            # detects disconnects.
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception:
        await manager.disconnect(websocket)
