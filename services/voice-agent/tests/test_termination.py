from __future__ import annotations

import asyncio

import pytest

from agent.models import DisconnectReason
from agent.session import FakeRealtimeSession
from agent.termination import CallTerminationWaiter


def _waiter(*, max_duration: float = 5.0, grace: float = 1.0) -> CallTerminationWaiter:
    return CallTerminationWaiter(max_duration_seconds=max_duration, end_call_grace_seconds=grace)


@pytest.mark.asyncio
async def test_participant_disconnect_maps_to_remote_hangup() -> None:
    session = FakeRealtimeSession()
    waiter = _waiter()

    async def trigger() -> None:
        await asyncio.sleep(0.01)
        session.simulate_participant_disconnect()

    result, _ = await asyncio.gather(waiter.wait(session), trigger())

    assert result.reason == DisconnectReason.REMOTE_HANGUP
    assert "participant_disconnected" in result.detail


@pytest.mark.asyncio
async def test_job_shutdown_maps_to_agent_hangup() -> None:
    session = FakeRealtimeSession()
    waiter = _waiter()

    async def trigger() -> None:
        await asyncio.sleep(0.01)
        session.simulate_job_shutdown()

    result, _ = await asyncio.gather(waiter.wait(session), trigger())

    assert result.reason == DisconnectReason.AGENT_HANGUP
    assert "job_shutdown" in result.detail


@pytest.mark.asyncio
async def test_error_close_maps_to_openai_failure() -> None:
    session = FakeRealtimeSession()
    waiter = _waiter()

    async def trigger() -> None:
        await asyncio.sleep(0.01)
        session.simulate_error_close(RuntimeError("boom"))

    result, _ = await asyncio.gather(waiter.wait(session), trigger())

    assert result.reason == DisconnectReason.OPENAI_FAILURE


@pytest.mark.asyncio
async def test_fatal_realtime_error_terminates_with_openai_failure() -> None:
    """CODEX_AUDIT_PHASE_4_FIX.md YÜKSEK-1 regresyon testi: gerçek SDK
    `error` event'i (`recoverable=False`) artık terminal — eski davranışta
    yalnız kaydediliyor, job max_call_duration'a kadar açık kalıyordu."""
    session = FakeRealtimeSession()
    waiter = _waiter(max_duration=5.0)

    async def trigger() -> None:
        await asyncio.sleep(0.01)
        session.simulate_fatal_realtime_error("connection lost")

    result, _ = await asyncio.gather(waiter.wait(session), trigger())

    assert result.reason == DisconnectReason.OPENAI_FAILURE
    assert "sdk_close_reason=error" in result.detail


@pytest.mark.asyncio
async def test_recoverable_realtime_error_does_not_terminate() -> None:
    """`recoverable=True` — SDK kendi içinde toparlanır; görüşme gereksiz
    yere sonlandırılmamalı (yalnız timeout ile biter)."""
    session = FakeRealtimeSession()
    waiter = _waiter(max_duration=0.05)

    async def trigger() -> None:
        await asyncio.sleep(0.01)
        session.simulate_recoverable_realtime_error("transient STT glitch")

    result, _ = await asyncio.gather(waiter.wait(session), trigger())

    assert result.reason == DisconnectReason.TIMEOUT  # error terminal SAYILMADI


@pytest.mark.asyncio
async def test_two_separate_fatal_errors_only_first_counts() -> None:
    session = FakeRealtimeSession()
    waiter = _waiter(max_duration=5.0)

    async def trigger() -> None:
        await asyncio.sleep(0.01)
        session.simulate_fatal_realtime_error("first failure")
        session.simulate_fatal_realtime_error("second failure")

    result, _ = await asyncio.gather(waiter.wait(session), trigger())

    assert result.reason == DisconnectReason.OPENAI_FAILURE
    assert waiter._close_info["last_error"].message == "first failure"


@pytest.mark.asyncio
async def test_fatal_error_wins_race_against_remote_hangup_when_first() -> None:
    session = FakeRealtimeSession()
    waiter = _waiter(max_duration=5.0)

    async def trigger() -> None:
        await asyncio.sleep(0.01)
        session.simulate_fatal_realtime_error("fatal first")
        session.simulate_participant_disconnect()

    result, _ = await asyncio.gather(waiter.wait(session), trigger())

    assert result.reason == DisconnectReason.OPENAI_FAILURE  # ilk gelen kazanır


@pytest.mark.asyncio
async def test_remote_hangup_wins_race_against_fatal_error_when_first() -> None:
    session = FakeRealtimeSession()
    waiter = _waiter(max_duration=5.0)

    async def trigger() -> None:
        await asyncio.sleep(0.01)
        session.simulate_participant_disconnect()
        session.simulate_fatal_realtime_error("too late")

    result, _ = await asyncio.gather(waiter.wait(session), trigger())

    assert result.reason == DisconnectReason.REMOTE_HANGUP  # ilk gelen kazanır


@pytest.mark.asyncio
async def test_fatal_error_wins_race_against_timeout() -> None:
    session = FakeRealtimeSession()
    waiter = _waiter(max_duration=0.08)

    async def trigger() -> None:
        await asyncio.sleep(0.01)
        session.simulate_fatal_realtime_error("fatal before timeout")

    result, _ = await asyncio.gather(waiter.wait(session), trigger())

    assert result.reason == DisconnectReason.OPENAI_FAILURE


@pytest.mark.asyncio
async def test_fatal_error_wins_race_against_end_call_safely() -> None:
    session = FakeRealtimeSession()
    waiter = _waiter(max_duration=5.0, grace=2.0)

    async def trigger() -> None:
        await asyncio.sleep(0.01)
        session.simulate_fatal_realtime_error("fatal during end-call")
        waiter.request_end_call()

    result, _ = await asyncio.gather(waiter.wait(session), trigger())

    assert result.reason == DisconnectReason.OPENAI_FAILURE


@pytest.mark.asyncio
async def test_timeout_when_nothing_happens() -> None:
    session = FakeRealtimeSession()
    waiter = _waiter(max_duration=0.05, grace=1.0)

    result = await waiter.wait(session)

    assert result.reason == DisconnectReason.TIMEOUT
    assert result.detail == "max_call_duration_exceeded"


@pytest.mark.asyncio
async def test_end_call_flow_waits_for_agent_to_finish_speaking_then_closes() -> None:
    session = FakeRealtimeSession()
    waiter = _waiter(max_duration=5.0, grace=2.0)

    async def trigger() -> None:
        await asyncio.sleep(0.01)
        waiter.request_end_call()
        await asyncio.sleep(0.01)
        session.simulate_agent_speaking()
        await asyncio.sleep(0.01)
        session.simulate_agent_idle()

    result, _ = await asyncio.gather(waiter.wait(session), trigger())

    assert result.reason == DisconnectReason.AGENT_HANGUP
    assert session.closed is True


@pytest.mark.asyncio
async def test_end_call_flow_proceeds_after_grace_timeout_if_agent_never_speaks() -> None:
    session = FakeRealtimeSession()
    waiter = _waiter(max_duration=5.0, grace=0.05)

    async def trigger() -> None:
        await asyncio.sleep(0.01)
        waiter.request_end_call()
        # Agent hiç konuşmuyor — grace süresi dolunca yine de kapanmalı.

    result, _ = await asyncio.gather(waiter.wait(session), trigger())

    assert result.reason == DisconnectReason.AGENT_HANGUP
    assert session.closed is True


@pytest.mark.asyncio
async def test_remote_hangup_wins_race_against_end_call_request() -> None:
    """Karşı taraf tam end_call_safely ile aynı anda kapatırsa gerçek
    kapanış nedeni (participant_disconnected) korunmalı, agent'ın kendi
    aclose() çağrısıyla ezilmemeli."""
    session = FakeRealtimeSession()
    waiter = _waiter(max_duration=5.0, grace=2.0)

    async def trigger() -> None:
        await asyncio.sleep(0.01)
        waiter.request_end_call()
        session.simulate_participant_disconnect()  # aynı anda gerçek hangup

    result, _ = await asyncio.gather(waiter.wait(session), trigger())

    assert result.reason == DisconnectReason.REMOTE_HANGUP


@pytest.mark.asyncio
async def test_wait_detaches_listeners_after_completion() -> None:
    session = FakeRealtimeSession()
    waiter = _waiter(max_duration=1.0)

    async def trigger() -> None:
        await asyncio.sleep(0.01)
        session.simulate_participant_disconnect()

    await asyncio.gather(waiter.wait(session), trigger())

    assert session._listeners.get("close", set()) == set()
    assert session._listeners.get("error", set()) == set()


@pytest.mark.asyncio
async def test_no_busy_wait_loop_present() -> None:
    """`wait()` yalnız event-driven olmalı; kısa bir max_duration ile
    çağrıldığında CPU'yu meşgul etmeden (yield ederek) timeout'a düşmeli."""
    session = FakeRealtimeSession()
    waiter = _waiter(max_duration=0.02, grace=0.01)

    started = asyncio.get_event_loop().time()
    result = await waiter.wait(session)
    elapsed = asyncio.get_event_loop().time() - started

    assert result.reason == DisconnectReason.TIMEOUT
    assert elapsed < 0.5  # makul bir üst sınır, busy-wait olsa çok daha yavaş/CPU-yoğun olurdu
