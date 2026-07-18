from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import pytest

from agent.errors import CallNotDialableError, SIPParticipantError, SIPTimeoutError
from agent.job_handler import RuntimeAdapters, VoiceAgentJobHandler, parse_call_id
from agent.models import AgentEventType, CompletionIn, GenericAcceptedResponse
from agent.session import FakeRealtimeSessionAdapter
from agent.sip import FakeSIPParticipantAdapter
from tests.factories import bootstrap, dial_plan


class FakeJob:
    def __init__(self, call_id: uuid.UUID) -> None:
        self.metadata = json.dumps({"call_id": str(call_id)})


class FakeContext:
    def __init__(self, call_id: uuid.UUID) -> None:
        self.job = FakeJob(call_id)
        self.room = object()
        self.connected = False
        self.shutdown_reason: str | None = None

    async def connect(self) -> None:
        self.connected = True

    def shutdown(self, reason: str = "") -> None:
        self.shutdown_reason = reason


class FakeAPI:
    def __init__(self, call_id: uuid.UUID, *, max_call_duration_seconds: int = 300) -> None:
        self.bootstrap_response = bootstrap()
        self.bootstrap_response.call_id = call_id
        self.dial_plan_response = dial_plan(
            call_id, max_call_duration_seconds=max_call_duration_seconds
        )
        self.events: list[AgentEventType] = []
        self.event_payloads: list[dict[str, Any]] = []
        self.completions: list[CompletionIn] = []
        self.usages: list[Any] = []
        self.transcript_turns: list[Any] = []
        self.bootstrap_error: Exception | None = None
        self.completed_event = asyncio.Event()

    async def bootstrap(self, call_id: uuid.UUID) -> object:
        if self.bootstrap_error:
            raise self.bootstrap_error
        return self.bootstrap_response

    async def dial_plan(self, call_id: uuid.UUID) -> object:
        return self.dial_plan_response

    async def send_event(self, call_id: uuid.UUID, event: object) -> GenericAcceptedResponse:
        self.events.append(event.event_type)  # type: ignore[attr-defined]
        self.event_payloads.append(event.payload)  # type: ignore[attr-defined]
        return GenericAcceptedResponse(status="accepted")

    async def send_transcript_turn(
        self, call_id: uuid.UUID, turn: object
    ) -> GenericAcceptedResponse:
        self.transcript_turns.append(turn)
        return GenericAcceptedResponse(status="stored")

    async def send_usage(self, call_id: uuid.UUID, usage: object) -> object:
        self.usages.append(usage)
        return object()

    async def complete(
        self,
        call_id: uuid.UUID,
        completion: CompletionIn,
    ) -> GenericAcceptedResponse:
        self.completions.append(completion)
        self.completed_event.set()
        return GenericAcceptedResponse(status="completed")

    async def call_tool(
        self, call_id: uuid.UUID, backend_path: str, payload: dict[str, Any]
    ) -> object:
        return object()


def _settings(**overrides: Any) -> Any:
    from agent.config import VoiceAgentSettings

    defaults: dict[str, Any] = {
        "INTERNAL_API_BASE_URL": "http://internal.test",
        "INTERNAL_SERVICE_TOKEN": "token",
        "EVENT_QUEUE_MAX_SIZE": 50,
        "TRANSCRIPT_QUEUE_MAX_SIZE": 50,
        "END_CALL_GRACE_SECONDS": 1,
    }
    defaults.update(overrides)
    return VoiceAgentSettings(**defaults)


def test_parse_call_id_rejects_invalid_metadata() -> None:
    with pytest.raises(ValueError):
        parse_call_id('{"phone":"+905551112233"}')


async def _run_until_session_started(
    handler: VoiceAgentJobHandler, ctx: FakeContext, realtime: FakeRealtimeSessionAdapter
) -> asyncio.Task[None]:
    """`handle()`'ı arka planda başlatır ve realtime session `start()`
    edilene kadar (yani artık `waiter.wait()` içinde konuşmayı beklediği
    ana kadar) bekler. Testin gerçek görüşme sırasında SDK event'lerini
    simüle edebilmesi için gereklidir."""
    task = asyncio.create_task(handler.handle(ctx))
    for _ in range(200):
        if realtime.runtime is not None and getattr(realtime.runtime.session, "started", False):
            break
        await asyncio.sleep(0.005)
    else:
        raise AssertionError("Session zamanında başlamadı")
    return task


# ─── Normal görüşme: job açılıştan sonra aktif kalır ──────────────────────────


@pytest.mark.asyncio
async def test_job_stays_active_after_opening_until_real_termination() -> None:
    """KRİTİK regresyon testi: eski davranışta job açılış cümlesinden hemen
    sonra completion gönderip kapanıyordu (bkz. CLAUDE_AUDIT_PHASE_4.md
    KRİTİK-1). Bu test açılıştan SONRA hiçbir terminal event gelmeden
    completion gönderilmediğini, yalnız gerçek bir kapanış sinyali
    (participant disconnect) geldiğinde tam olarak bir kez gönderildiğini
    kanıtlar."""
    call_id = uuid.uuid4()
    api = FakeAPI(call_id)
    sip = FakeSIPParticipantAdapter()
    realtime = FakeRealtimeSessionAdapter()
    handler = VoiceAgentJobHandler(
        _settings(), RuntimeAdapters(api=api, sip=sip, realtime=realtime)  # type: ignore[arg-type]
    )
    ctx = FakeContext(call_id)

    task = await _run_until_session_started(handler, ctx, realtime)

    # Açılış söylendi ama görüşme HÂLÂ aktif — completion gönderilmemiş olmalı.
    await asyncio.sleep(0.02)
    assert len(realtime.runtime.session.replies) == 1  # type: ignore[union-attr]
    assert api.completions == []
    assert not task.done()

    # Kullanıcı (karşı taraf) simüle konuşuyor — job hâlâ aktif kalmalı.
    realtime.runtime.session.simulate_agent_speaking()  # type: ignore[union-attr]
    realtime.runtime.session.simulate_agent_idle()  # type: ignore[union-attr]
    await asyncio.sleep(0.02)
    assert api.completions == []

    # Gerçek terminal olay: karşı taraf kapatıyor.
    realtime.runtime.session.simulate_participant_disconnect()  # type: ignore[union-attr]
    await asyncio.wait_for(task, timeout=2.0)

    assert len(api.completions) == 1
    assert api.completions[0].disconnect_reason == "remote_hangup"
    assert AgentEventType.AGENT_JOB_STARTED in api.events
    assert AgentEventType.ANSWERED in api.events
    assert AgentEventType.AGENT_SPEECH_STARTED in api.events
    assert AgentEventType.AGENT_SPEECH_STOPPED in api.events
    assert AgentEventType.CALL_DISCONNECTED in api.events
    assert ctx.shutdown_reason == "voice-agent-job-finished"
    # Gerçek SDK usage sağlanmadığı için (fake session boş usage döner)
    # açıkça 'unavailable' raporlanmalı, sessizce atlanmamalı.
    assert len(api.usages) == 1
    assert api.usages[0].usage_source == "unavailable"


@pytest.mark.asyncio
async def test_real_usage_is_reported_when_session_provides_it() -> None:
    call_id = uuid.uuid4()
    api = FakeAPI(call_id)
    sip = FakeSIPParticipantAdapter()
    realtime = FakeRealtimeSessionAdapter()
    handler = VoiceAgentJobHandler(
        _settings(), RuntimeAdapters(api=api, sip=sip, realtime=realtime)  # type: ignore[arg-type]
    )
    ctx = FakeContext(call_id)

    task = await _run_until_session_started(handler, ctx, realtime)
    realtime.runtime.session.set_fake_usage(  # type: ignore[union-attr]
        input_audio_tokens=120, output_audio_tokens=80, input_text_tokens=10
    )
    realtime.runtime.session.simulate_participant_disconnect()  # type: ignore[union-attr]
    await asyncio.wait_for(task, timeout=2.0)

    assert len(api.usages) == 1
    usage = api.usages[0]
    assert usage.usage_source == "provider_reported"
    assert usage.input_audio_tokens == 120
    assert usage.output_audio_tokens == 80
    assert usage.input_text_tokens == 10


# ─── Agent end-call (end_call_safely) ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_end_call_safely_flow_completes_with_agent_hangup() -> None:
    call_id = uuid.uuid4()
    api = FakeAPI(call_id)
    sip = FakeSIPParticipantAdapter()
    realtime = FakeRealtimeSessionAdapter()
    handler = VoiceAgentJobHandler(
        _settings(END_CALL_GRACE_SECONDS=1),
        RuntimeAdapters(api=api, sip=sip, realtime=realtime),  # type: ignore[arg-type]
    )
    ctx = FakeContext(call_id)

    task = await _run_until_session_started(handler, ctx, realtime)
    assert handler.last_waiter is not None

    # Model `end_call_safely` tool'unu çağırdı (backend zaten test_tools.py'de
    # ayrıca doğrulanıyor) — job handler bunu gerçek waiter üzerinden alır.
    handler.last_waiter.request_end_call()
    await asyncio.sleep(0.01)
    realtime.runtime.session.simulate_agent_speaking()  # type: ignore[union-attr]
    await asyncio.sleep(0.01)
    realtime.runtime.session.simulate_agent_idle()  # type: ignore[union-attr]

    await asyncio.wait_for(task, timeout=2.0)

    assert len(api.completions) == 1
    assert api.completions[0].disconnect_reason == "agent_hangup"
    assert len(sip.hangups) == 1


# ─── Timeout ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_max_call_duration_timeout_completes_with_timeout_reason() -> None:
    call_id = uuid.uuid4()
    api = FakeAPI(call_id, max_call_duration_seconds=1)
    sip = FakeSIPParticipantAdapter()
    realtime = FakeRealtimeSessionAdapter()
    handler = VoiceAgentJobHandler(
        _settings(), RuntimeAdapters(api=api, sip=sip, realtime=realtime)  # type: ignore[arg-type]
    )
    ctx = FakeContext(call_id)

    await _run_until_session_started(handler, ctx, realtime)
    # Hiçbir terminal event tetiklenmiyor — yalnız max_call_duration_seconds
    # (1 saniye) aşılınca kendiliğinden TIMEOUT ile tamamlanmalı.
    await asyncio.wait_for(api.completed_event.wait(), timeout=3.0)

    assert len(api.completions) == 1
    assert api.completions[0].disconnect_reason == "timeout"


# ─── Runtime error terminal lifecycle (CODEX_AUDIT_PHASE_4_FIX.md YÜKSEK-1) ───


@pytest.mark.asyncio
async def test_fatal_realtime_error_terminates_job_with_single_completion() -> None:
    call_id = uuid.uuid4()
    api = FakeAPI(call_id)
    sip = FakeSIPParticipantAdapter()
    realtime = FakeRealtimeSessionAdapter()
    handler = VoiceAgentJobHandler(
        _settings(), RuntimeAdapters(api=api, sip=sip, realtime=realtime)  # type: ignore[arg-type]
    )
    ctx = FakeContext(call_id)

    task = await _run_until_session_started(handler, ctx, realtime)
    realtime.runtime.session.simulate_fatal_realtime_error("connection lost")  # type: ignore[union-attr]
    await asyncio.wait_for(task, timeout=2.0)

    assert len(api.completions) == 1
    assert api.completions[0].disconnect_reason == "openai_failure"
    assert len(sip.hangups) == 1  # kaynaklar yine de temizlendi


@pytest.mark.asyncio
async def test_recoverable_realtime_error_keeps_job_active() -> None:
    call_id = uuid.uuid4()
    api = FakeAPI(call_id)
    sip = FakeSIPParticipantAdapter()
    realtime = FakeRealtimeSessionAdapter()
    handler = VoiceAgentJobHandler(
        _settings(), RuntimeAdapters(api=api, sip=sip, realtime=realtime)  # type: ignore[arg-type]
    )
    ctx = FakeContext(call_id)

    task = await _run_until_session_started(handler, ctx, realtime)
    realtime.runtime.session.simulate_recoverable_realtime_error("transient glitch")  # type: ignore[union-attr]
    await asyncio.sleep(0.02)

    assert api.completions == []  # kurtarılabilir hata görüşmeyi bitirmedi
    assert not task.done()

    # Temizlik: gerçek terminal olayla job'ı sonlandır.
    realtime.runtime.session.simulate_participant_disconnect()  # type: ignore[union-attr]
    await asyncio.wait_for(task, timeout=2.0)
    assert len(api.completions) == 1
    assert api.completions[0].disconnect_reason == "remote_hangup"


# ─── SIP hata ayrımı ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sip_busy_failure_carries_differentiated_reason() -> None:
    call_id = uuid.uuid4()
    api = FakeAPI(call_id)
    sip = FakeSIPParticipantAdapter()
    sip.fail = SIPParticipantError("busy", sip_status_code=486, sip_status="Busy Here")
    handler = VoiceAgentJobHandler(
        _settings(),
        RuntimeAdapters(api=api, sip=sip, realtime=FakeRealtimeSessionAdapter()),  # type: ignore[arg-type]
    )

    await handler.handle(FakeContext(call_id))

    assert len(api.completions) == 1
    assert api.completions[0].disconnect_reason == "sip_failure"
    # CODEX_AUDIT_PHASE_4_FIX.md YÜKSEK-3: sip_reason artık event payload'ının
    # yanı sıra COMPLETION payload'ına da taşınıyor — backend bunu call
    # status/outcome/retry policy için okuyabilsin diye.
    assert api.completions[0].sip_reason == "busy"
    failed_payloads = [
        p for e, p in zip(api.events, api.event_payloads, strict=True)
        if e == AgentEventType.AGENT_JOB_FAILED
    ]
    assert failed_payloads[0]["sip_reason"] == "busy"


@pytest.mark.asyncio
async def test_sip_no_answer_failure_carries_differentiated_reason() -> None:
    call_id = uuid.uuid4()
    api = FakeAPI(call_id)
    sip = FakeSIPParticipantAdapter()
    sip.fail = SIPParticipantError("no answer", sip_status_code=480, sip_status="Temp Unavailable")
    handler = VoiceAgentJobHandler(
        _settings(),
        RuntimeAdapters(api=api, sip=sip, realtime=FakeRealtimeSessionAdapter()),  # type: ignore[arg-type]
    )

    await handler.handle(FakeContext(call_id))

    failed_payloads = [
        p for e, p in zip(api.events, api.event_payloads, strict=True)
        if e == AgentEventType.AGENT_JOB_FAILED
    ]
    assert failed_payloads[0]["sip_reason"] == "no_answer"


@pytest.mark.asyncio
async def test_sip_timeout_uses_timeout_reason() -> None:
    call_id = uuid.uuid4()
    api = FakeAPI(call_id)
    sip = FakeSIPParticipantAdapter()
    sip.fail = SIPTimeoutError("no response from trunk")
    handler = VoiceAgentJobHandler(
        _settings(),
        RuntimeAdapters(api=api, sip=sip, realtime=FakeRealtimeSessionAdapter()),  # type: ignore[arg-type]
    )

    await handler.handle(FakeContext(call_id))

    failed_payloads = [
        p for e, p in zip(api.events, api.event_payloads, strict=True)
        if e == AgentEventType.AGENT_JOB_FAILED
    ]
    assert failed_payloads[0]["sip_reason"] == "timeout"
    assert len(api.completions) == 1
    assert api.completions[0].disconnect_reason == "sip_failure"


@pytest.mark.asyncio
async def test_sip_failure_never_starts_realtime_session() -> None:
    call_id = uuid.uuid4()
    api = FakeAPI(call_id)
    sip = FakeSIPParticipantAdapter()
    sip.fail = SIPParticipantError("rejected", sip_status_code=603)
    realtime = FakeRealtimeSessionAdapter()
    handler = VoiceAgentJobHandler(
        _settings(), RuntimeAdapters(api=api, sip=sip, realtime=realtime)  # type: ignore[arg-type]
    )

    await handler.handle(FakeContext(call_id))

    assert realtime.runtime is not None  # build() çağrıldı (session var)
    assert realtime.runtime.session.started is False  # ama hiç start() edilmedi
    assert realtime.runtime.session.replies == []  # açılış asla söylenmedi


# ─── Bootstrap başarısızlığı ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bootstrap_failure_does_not_start_sip_or_realtime() -> None:
    call_id = uuid.uuid4()
    api = FakeAPI(call_id)
    api.bootstrap_error = CallNotDialableError("not dialable")
    sip = FakeSIPParticipantAdapter()
    realtime = FakeRealtimeSessionAdapter()
    handler = VoiceAgentJobHandler(
        _settings(), RuntimeAdapters(api=api, sip=sip, realtime=realtime)  # type: ignore[arg-type]
    )

    await handler.handle(FakeContext(call_id))

    assert sip.created == []
    assert realtime.runtime is None
    assert len(api.completions) == 1
    assert api.completions[0].disconnect_reason == "agent_error"


# ─── Kaynak temizliği ve tek completion garantisi ─────────────────────────


@pytest.mark.asyncio
async def test_hangup_called_exactly_once_after_remote_disconnect() -> None:
    call_id = uuid.uuid4()
    api = FakeAPI(call_id)
    sip = FakeSIPParticipantAdapter()
    realtime = FakeRealtimeSessionAdapter()
    handler = VoiceAgentJobHandler(
        _settings(), RuntimeAdapters(api=api, sip=sip, realtime=realtime)  # type: ignore[arg-type]
    )
    ctx = FakeContext(call_id)

    task = await _run_until_session_started(handler, ctx, realtime)
    realtime.runtime.session.simulate_participant_disconnect()  # type: ignore[union-attr]
    await asyncio.wait_for(task, timeout=2.0)

    assert len(sip.hangups) == 1
    assert len(api.completions) == 1


@pytest.mark.asyncio
async def test_transcript_turns_captured_from_conversation_items() -> None:
    """Gerçek `conversation_item_added` event'inden final transcript
    turn'lerinin backend'e aktarıldığını doğrular (KRİTİK-1 düzeltmesinin
    yan ürünü — eskiden hiçbir konuşma olmadığı için transcript hep boştu)."""
    call_id = uuid.uuid4()
    api = FakeAPI(call_id)
    sip = FakeSIPParticipantAdapter()
    realtime = FakeRealtimeSessionAdapter()
    handler = VoiceAgentJobHandler(
        _settings(), RuntimeAdapters(api=api, sip=sip, realtime=realtime)  # type: ignore[arg-type]
    )
    ctx = FakeContext(call_id)

    task = await _run_until_session_started(handler, ctx, realtime)
    session = realtime.runtime.session  # type: ignore[union-attr]

    class _FakeChatItem:
        def __init__(self, role: str, text: str, item_id: str) -> None:
            self.role = role
            self.text_content = text
            self.id = item_id
            self.created_at = 0.0

    class _FakeConversationItemEvent:
        def __init__(self, item: _FakeChatItem) -> None:
            self.item = item

    session.emit(
        "conversation_item_added",
        _FakeConversationItemEvent(_FakeChatItem("user", "Web sitemiz zaten var.", "item-1")),
    )
    session.emit(
        "conversation_item_added",
        _FakeConversationItemEvent(
            _FakeChatItem("assistant", "Anlıyorum, kısaca bahsedebilir miyim?", "item-2")
        ),
    )
    await asyncio.sleep(0.02)
    session.simulate_participant_disconnect()
    await asyncio.wait_for(task, timeout=2.0)

    assert len(api.transcript_turns) == 2
    assert api.transcript_turns[0].speaker == "user"
    assert api.transcript_turns[1].speaker == "agent"
