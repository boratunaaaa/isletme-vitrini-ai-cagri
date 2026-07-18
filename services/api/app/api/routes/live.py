"""SSE canlı olay akışı: panel EventSource ile bağlanır."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Request
from sse_starlette.sse import EventSourceResponse

from app.core.redis import get_redis_async
from app.deps import get_current_user
from app.models.user import User
from app.services.event_bus import CHANNEL

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/live", tags=["live"])

HEARTBEAT_SECONDS = 20


@router.get("/events")
async def event_stream(
    request: Request,
    _: User = Depends(get_current_user),
) -> EventSourceResponse:
    async def generator() -> AsyncIterator[dict]:
        redis = get_redis_async()
        pubsub = redis.pubsub()
        await pubsub.subscribe(CHANNEL)
        try:
            while True:
                if await request.is_disconnected():
                    break
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=HEARTBEAT_SECONDS
                )
                if message is None:
                    yield {"event": "heartbeat", "data": json.dumps({"ok": True})}
                    continue
                data = message.get("data")
                if isinstance(data, bytes):
                    data = data.decode()
                yield {"event": "message", "data": data}
        except asyncio.CancelledError:
            pass
        finally:
            try:
                await pubsub.unsubscribe(CHANNEL)
                await pubsub.aclose()
                await redis.aclose()
            except Exception:
                pass

    return EventSourceResponse(generator())
