from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from agent.models import UsageSourceIn
from agent.transcript import MemoryTranscriptSink
from agent.usage import MemoryUsageSink, usage_from_session


@pytest.mark.asyncio
async def test_final_transcript_turn_is_stored_redacted() -> None:
    sink = MemoryTranscriptSink()
    now = datetime.now(UTC)

    await sink.enqueue_turn(
        turn_id="turn-1",
        speaker="user",
        text="Telefonum +905551112233",
        started_at=now,
        ended_at=now,
        is_final=True,
        sequence=1,
    )

    assert sink.turns[0].text == "Telefonum [REDACTED_PHONE]"


@pytest.mark.asyncio
async def test_partial_transcript_turn_is_ignored() -> None:
    sink = MemoryTranscriptSink()

    await sink.enqueue_turn(
        turn_id="turn-1",
        speaker="user",
        text="partial",
        is_final=False,
        sequence=1,
    )

    assert sink.turns == []


def _fake_session(*, model_usage: list[object]) -> SimpleNamespace:
    return SimpleNamespace(usage=SimpleNamespace(model_usage=model_usage))


def test_usage_from_session_maps_real_llm_usage_field_names() -> None:
    """Gerçek `LLMModelUsage` alan adları bizim `UsageUpdateIn` şemamızla
    BİREBİR AYNI DEĞİL (SDK `input_cached_audio_tokens` derken bizim
    şemamız `cached_input_audio_tokens` kullanıyor) — bu test alan eşlemesinin
    doğru yönde yapıldığını, ters çevrilmediğini kanıtlar."""
    llm_usage = SimpleNamespace(
        type="llm_usage",
        provider="openai",
        model="gpt-realtime-2.1-mini",
        input_audio_tokens=100,
        input_cached_audio_tokens=15,
        output_audio_tokens=200,
        input_text_tokens=30,
        input_cached_text_tokens=5,
        output_text_tokens=40,
    )
    session = _fake_session(model_usage=[llm_usage])

    usage = usage_from_session(session, model="gpt-realtime-2.1-mini")

    assert usage is not None
    assert usage.input_audio_tokens == 100
    assert usage.cached_input_audio_tokens == 15
    assert usage.output_audio_tokens == 200
    assert usage.input_text_tokens == 30
    assert usage.cached_input_text_tokens == 5
    assert usage.output_text_tokens == 40
    assert usage.reasoning_tokens is None  # SDK bu alanı sağlamıyor, uydurulmadı
    assert usage.usage_source == UsageSourceIn.PROVIDER_REPORTED
    assert usage.is_final is True


def test_usage_from_session_returns_none_when_no_llm_usage_present() -> None:
    session = _fake_session(model_usage=[])

    assert usage_from_session(session, model="gpt-realtime-2.1-mini") is None


def test_usage_from_session_ignores_non_llm_usage_entries() -> None:
    tts_usage = SimpleNamespace(type="tts_usage", provider="openai", model="tts-1")
    session = _fake_session(model_usage=[tts_usage])

    assert usage_from_session(session, model="gpt-realtime-2.1-mini") is None


def test_usage_from_session_handles_missing_session_usage_attribute() -> None:
    session = SimpleNamespace()  # `.usage` özelliği hiç yok

    assert usage_from_session(session, model="gpt-realtime-2.1-mini") is None


@pytest.mark.asyncio
async def test_usage_sink_deduplicates_event_ids() -> None:
    sink = MemoryUsageSink()
    event_id = await sink.report_unavailable(model="gpt-realtime-2.1-mini", is_final=True)

    await sink.send_usage(sink.usages[0])

    assert event_id.startswith("usage-unavailable-")
    assert len(sink.usages) == 1
    assert sink.usages[0].usage_source == UsageSourceIn.UNAVAILABLE
