from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from datetime import UTC, datetime
from typing import Any, Protocol

from agent.api_client import InternalAPIClient
from agent.models import AgentEventType, LifecycleEventIn
from agent.redaction import safe_error_message, safe_value

logger = logging.getLogger(__name__)


class EventSink(Protocol):
    async def emit(
        self,
        event_type: AgentEventType,
        payload: dict[str, Any] | None = None,
        *,
        important: bool = False,
    ) -> None: ...

    async def flush(self) -> None: ...


class LifecycleEventDispatcher:
    def __init__(
        self,
        *,
        call_id: uuid.UUID,
        api: InternalAPIClient,
        max_size: int,
    ) -> None:
        self._call_id = call_id
        self._api = api
        self._sequence = 0
        self._queue: asyncio.Queue[LifecycleEventIn] = asyncio.Queue(maxsize=max_size)
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def emit(
        self,
        event_type: AgentEventType,
        payload: dict[str, Any] | None = None,
        *,
        important: bool = False,
    ) -> None:
        self._sequence += 1
        event = LifecycleEventIn(
            event_id=f"evt-{self._sequence}-{uuid.uuid4().hex[:16]}",
            event_type=event_type,
            occurred_at=datetime.now(UTC),
            sequence=self._sequence,
            payload=safe_value(payload or {}),
        )
        if important:
            await self._api.send_event(self._call_id, event)
            return
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning("Lifecycle event queue full; dropping %s", event_type.value)

    async def flush(self) -> None:
        await self._queue.join()

    async def stop(self) -> None:
        await self.flush()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _run(self) -> None:
        while True:
            event = await self._queue.get()
            try:
                await self._api.send_event(self._call_id, event)
            except Exception as exc:
                logger.warning("Lifecycle event delivery failed: %s", safe_error_message(exc))
            finally:
                self._queue.task_done()


class MemoryEventSink:
    def __init__(self) -> None:
        self.events: list[tuple[AgentEventType, dict[str, Any]]] = []

    async def emit(
        self,
        event_type: AgentEventType,
        payload: dict[str, Any] | None = None,
        *,
        important: bool = False,
    ) -> None:
        self.events.append((event_type, payload or {}))

    async def flush(self) -> None:
        return None
