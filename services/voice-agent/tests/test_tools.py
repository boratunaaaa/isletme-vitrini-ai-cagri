from __future__ import annotations

import uuid
from typing import Any

import pytest

from agent.errors import ToolExecutionError
from agent.models import AgentEventType, ToolDefinition, ToolResponse
from agent.tools import END_CALL_TOOL_NAME, TOOL_DEFINITIONS, ToolExecutor, summarize_tool_result


class FakeAPI:
    def __init__(self) -> None:
        self.calls: list[tuple[uuid.UUID, str, dict[str, Any]]] = []
        self.fail = False

    async def call_tool(
        self,
        call_id: uuid.UUID,
        backend_path: str,
        payload: dict[str, Any],
    ) -> ToolResponse:
        if self.fail:
            raise RuntimeError("tool failed")
        self.calls.append((call_id, backend_path, payload))
        return ToolResponse(status="ok", result={"outcome": "interested"})


class FakeEvents:
    def __init__(self) -> None:
        self.events: list[AgentEventType] = []

    async def emit(
        self,
        event_type: AgentEventType,
        payload: dict[str, Any] | None = None,
        *,
        important: bool = False,
    ) -> None:
        self.events.append(event_type)

    async def flush(self) -> None:
        return None


@pytest.mark.asyncio
@pytest.mark.parametrize("definition", TOOL_DEFINITIONS)
async def test_each_tool_calls_expected_backend_endpoint(definition: ToolDefinition) -> None:
    call_id = uuid.uuid4()
    api = FakeAPI()
    events = FakeEvents()
    executor = ToolExecutor(call_id=call_id, api=api, events=events)  # type: ignore[arg-type]

    await executor.execute(definition.name, _arguments_for(definition.name))

    assert api.calls[0][1] == definition.backend_path
    assert api.calls[0][2]["tool_call_id"].startswith(f"tool-{definition.name}-")
    assert events.events == [
        AgentEventType.TOOL_CALL_STARTED,
        AgentEventType.TOOL_CALL_COMPLETED,
    ]


@pytest.mark.asyncio
async def test_tool_failure_emits_failed_event() -> None:
    api = FakeAPI()
    api.fail = True
    events = FakeEvents()
    executor = ToolExecutor(call_id=uuid.uuid4(), api=api, events=events)  # type: ignore[arg-type]

    with pytest.raises(ToolExecutionError):
        await executor.execute("mark_interested", {"note": "ok"})

    assert events.events == [
        AgentEventType.TOOL_CALL_STARTED,
        AgentEventType.TOOL_CALL_FAILED,
    ]


def test_tool_summary_is_not_raw_json() -> None:
    response = ToolResponse(status="ok", result={"should_hangup": True, "hangup_performed": False})

    summary = summarize_tool_result("end_call_safely", response)

    assert "{" not in summary
    assert "Yeni soru sorma" in summary


# ─── end_call_safely -> CallTerminationWaiter kablo testi ─────────────────────


@pytest.mark.asyncio
async def test_end_call_safely_triggers_callback_exactly_once_on_success() -> None:
    api = FakeAPI()
    events = FakeEvents()
    calls = 0

    def on_end_call() -> None:
        nonlocal calls
        calls += 1

    executor = ToolExecutor(
        call_id=uuid.uuid4(), api=api, events=events, on_end_call_requested=on_end_call  # type: ignore[arg-type]
    )

    await executor.execute(END_CALL_TOOL_NAME, {"note": "iyi günler"})

    assert calls == 1


@pytest.mark.asyncio
async def test_end_call_safely_callback_not_triggered_when_backend_call_fails() -> None:
    api = FakeAPI()
    api.fail = True
    events = FakeEvents()
    calls = 0

    def on_end_call() -> None:
        nonlocal calls
        calls += 1

    executor = ToolExecutor(
        call_id=uuid.uuid4(), api=api, events=events, on_end_call_requested=on_end_call  # type: ignore[arg-type]
    )

    with pytest.raises(ToolExecutionError):
        await executor.execute(END_CALL_TOOL_NAME, {"note": "iyi günler"})

    assert calls == 0


@pytest.mark.asyncio
async def test_other_tools_do_not_trigger_end_call_callback() -> None:
    api = FakeAPI()
    events = FakeEvents()
    calls = 0

    def on_end_call() -> None:
        nonlocal calls
        calls += 1

    executor = ToolExecutor(
        call_id=uuid.uuid4(), api=api, events=events, on_end_call_requested=on_end_call  # type: ignore[arg-type]
    )

    await executor.execute("mark_interested", {"note": "ok"})

    assert calls == 0


def _arguments_for(name: str) -> dict[str, Any]:
    if name == "schedule_callback":
        return {"callback_at": "2026-07-18T12:00:00Z", "notes": "not"}
    if name == "add_to_suppression_list":
        return {"reason": "do not call"}
    if name == "finalize_call_outcome":
        return {"outcome": "interested", "safe_summary": "ilgili"}
    return {}
