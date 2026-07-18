from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from datetime import UTC, datetime
from typing import Literal, Protocol

from agent.api_client import InternalAPIClient
from agent.models import TranscriptTurnIn
from agent.redaction import redact_text, safe_error_message

logger = logging.getLogger(__name__)


class TranscriptSink(Protocol):
    async def enqueue_turn(
        self,
        *,
        turn_id: str,
        speaker: Literal["user", "agent", "system"],
        text: str,
        started_at: datetime,
        ended_at: datetime,
        is_final: bool,
        sequence: int,
    ) -> None: ...

    async def flush(self) -> None: ...


class QueuedTranscriptSink:
    def __init__(self, *, call_id: uuid.UUID, api: InternalAPIClient, max_size: int) -> None:
        self._call_id = call_id
        self._api = api
        self._queue: asyncio.Queue[TranscriptTurnIn] = asyncio.Queue(maxsize=max_size)
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def enqueue_turn(
        self,
        *,
        turn_id: str,
        speaker: Literal["user", "agent", "system"],
        text: str,
        started_at: datetime | None = None,
        ended_at: datetime | None = None,
        is_final: bool,
        sequence: int,
    ) -> None:
        if not is_final:
            return
        now = datetime.now(UTC)
        turn = TranscriptTurnIn(
            turn_id=turn_id,
            speaker=speaker,
            text=redact_text(text)[:4000],
            started_at=started_at or now,
            ended_at=ended_at or now,
            is_final=True,
            sequence=sequence,
        )
        try:
            self._queue.put_nowait(turn)
        except asyncio.QueueFull:
            logger.warning("Transcript queue full; dropping non-critical turn")

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
            turn = await self._queue.get()
            try:
                await self._api.send_transcript_turn(self._call_id, turn)
            except Exception as exc:
                logger.warning("Transcript delivery failed: %s", safe_error_message(exc))
            finally:
                self._queue.task_done()


class MemoryTranscriptSink:
    def __init__(self) -> None:
        self.turns: list[TranscriptTurnIn] = []

    async def enqueue_turn(
        self,
        *,
        turn_id: str,
        speaker: Literal["user", "agent", "system"],
        text: str,
        started_at: datetime | None = None,
        ended_at: datetime | None = None,
        is_final: bool,
        sequence: int,
    ) -> None:
        if not is_final:
            return
        now = datetime.now(UTC)
        self.turns.append(
            TranscriptTurnIn(
                turn_id=turn_id,
                speaker=speaker,
                text=redact_text(text)[:4000],
                started_at=started_at or now,
                ended_at=ended_at or now,
                is_final=True,
                sequence=sequence,
            )
        )

    async def flush(self) -> None:
        return None
