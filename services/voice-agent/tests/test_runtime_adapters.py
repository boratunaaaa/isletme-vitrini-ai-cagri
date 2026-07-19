from __future__ import annotations

import asyncio

import pytest
from livekit import api as lk_api
from livekit.agents import Agent, AgentServer, AgentSession
from livekit.plugins import openai as lk_openai

from agent.config import VoiceAgentSettings
from agent.errors import RealtimeSessionError
from agent.session import (
    FakeRealtimeSessionAdapter,
    LiveKitRealtimeSessionAdapter,
    build_runtime_instructions,
)
from agent.sip import LiveKitSIPParticipantAdapter, build_sip_participant_request
from agent.tools import ToolExecutor, ToolRegistry
from tests.factories import bootstrap, dial_plan


class NoopAPI:
    async def call_tool(self, *_args: object, **_kwargs: object) -> object:
        raise AssertionError("not called")


class NoopEvents:
    async def emit(self, *_args: object, **_kwargs: object) -> None:
        return None

    async def flush(self) -> None:
        return None


def test_tool_list_is_exactly_controlled_contract() -> None:
    from agent.tools import TOOL_DEFINITIONS

    assert [tool.name for tool in TOOL_DEFINITIONS] == [
        "get_service_information",
        "get_package_information",
        "request_demo_link",
        "schedule_callback",
        "mark_interested",
        "mark_not_interested",
        "mark_wrong_number",
        "mark_decision_maker_unavailable",
        "add_to_suppression_list",
        "request_human_transfer",
        "finalize_call_outcome",
        "end_call_safely",
    ]


def test_prompt_context_excludes_phone_and_secrets() -> None:
    data = bootstrap()

    instructions = build_runtime_instructions(data)

    assert "Örnek İşletme" in instructions
    assert "Güzellik" in instructions
    assert "+905551112233" not in instructions
    assert "OPENAI_API_KEY" not in instructions
    assert "INTERNAL_SERVICE_TOKEN" not in instructions


@pytest.mark.asyncio
async def test_opening_only_once_after_answer() -> None:
    data = bootstrap()
    adapter = FakeRealtimeSessionAdapter()
    registry = ToolRegistry(
        ToolExecutor(call_id=data.call_id, api=NoopAPI(), events=NoopEvents())  # type: ignore[arg-type]
    )
    runtime = adapter.build(data, registry)

    first = await runtime.opening.play_once_after_answer(runtime.session)
    second = await runtime.opening.play_once_after_answer(runtime.session)

    assert first is True
    assert second is False
    assert len(runtime.session.replies) == 1  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_fake_sip_duplicate_create_is_idempotent() -> None:
    from agent.sip import FakeSIPParticipantAdapter

    adapter = FakeSIPParticipantAdapter()
    plan = dial_plan()

    await adapter.create_participant(plan)
    await adapter.create_participant(plan)

    assert len(adapter.created) == 1


def test_realtime_model_and_voice_catalog_rejects_unknown() -> None:
    data = bootstrap()
    data.campaign.model = "not-a-real-model"
    adapter = FakeRealtimeSessionAdapter()
    registry = ToolRegistry(
        ToolExecutor(call_id=data.call_id, api=NoopAPI(), events=NoopEvents())  # type: ignore[arg-type]
    )

    # Fake adapter does not validate SDK catalogs; production validation is in settings.
    with pytest.raises(ValueError):
        VoiceAgentSettings(OPENAI_REALTIME_DEFAULT_MODEL="not-a-real-model")

    assert adapter.build(bootstrap(), registry).session is not None


# ─── Gerçek prod adapter'lar — ağ bağlantısı OLMADAN, gerçek SDK sınıflarına ──
#
# Bu testler CLAUDE_AUDIT_PHASE_4.md YÜKSEK-4 bulgusuna doğrudan cevaptır:
# önceki test paketinde `LiveKitRealtimeSessionAdapter`/`LiveKitSIPParticipantAdapter`
# hiç instantiate edilmiyordu; SDK kwarg/imza hatası hiçbir testte yakalanmazdı.
# Burada yalnız NESNE İNŞASI test edilir (ağ I/O yok) — `.start()`/gerçek SIP
# çağrısı bilerek test edilMEZ (bu oturumda gerçek bağlantı yasak).


def _real_settings(**overrides: object) -> VoiceAgentSettings:
    defaults: dict[str, object] = {
        "LIVEKIT_URL": "wss://example.invalid",
        "LIVEKIT_API_KEY": "fake-key",
        "LIVEKIT_API_SECRET": "fake-secret",
        "OPENAI_API_KEY": "sk-test-not-real",
    }
    defaults.update(overrides)
    # `VoiceAgentSettings(**defaults)` `**dict` genişletmesiyle mypy'nin TÜM
    # alan tiplerine (SecretStr/HttpUrl/float/int dahil) karşı birleştirme
    # yapmasına yol açıyordu (CODEX_REAUDIT_PHASE_6.md). `model_validate`
    # aynı doğrulamayı çalıştırır, tip açısından güvenlidir.
    return VoiceAgentSettings.model_validate(defaults)


@pytest.mark.asyncio
async def test_real_realtime_adapter_builds_actual_sdk_objects() -> None:
    """`LiveKitRealtimeSessionAdapter.build()` gerçek `openai.realtime.RealtimeModel`,
    `livekit.agents.AgentSession` ve `Agent` nesnelerini geçerli parametrelerle
    inşa edebiliyor mu? Ağ çağrısı yapılmaz (nesne inşası saf Python'dur).
    `AgentSession.__init__` çalışan bir event loop gerektirdiği için (gerçek
    SDK kaynağında doğrulandı: `asyncio.get_event_loop()`), bu test async'tir
    — üretimde de `build()` her zaman `handle()` içinden, zaten çalışan bir
    event loop'ta çağrılır."""
    settings = _real_settings()
    adapter = LiveKitRealtimeSessionAdapter(settings)
    data = bootstrap()
    registry = ToolRegistry(
        ToolExecutor(call_id=data.call_id, api=NoopAPI(), events=NoopEvents())  # type: ignore[arg-type]
    )

    runtime = adapter.build(data, registry)

    assert isinstance(runtime.session, AgentSession)
    assert isinstance(runtime.assistant, Agent)
    assert isinstance(runtime.session.llm, lk_openai.realtime.RealtimeModel)


def test_real_realtime_adapter_rejects_unsupported_model() -> None:
    settings = _real_settings()
    adapter = LiveKitRealtimeSessionAdapter(settings)
    data = bootstrap()
    data.campaign.model = "not-a-real-model"
    registry = ToolRegistry(
        ToolExecutor(call_id=data.call_id, api=NoopAPI(), events=NoopEvents())  # type: ignore[arg-type]
    )

    with pytest.raises(RealtimeSessionError):
        adapter.build(data, registry)


def test_real_realtime_adapter_rejects_unsupported_voice() -> None:
    settings = _real_settings()
    adapter = LiveKitRealtimeSessionAdapter(settings)
    data = bootstrap()
    data.campaign.voice = "not-a-real-voice"
    registry = ToolRegistry(
        ToolExecutor(call_id=data.call_id, api=NoopAPI(), events=NoopEvents())  # type: ignore[arg-type]
    )

    with pytest.raises(RealtimeSessionError):
        adapter.build(data, registry)


@pytest.mark.asyncio
async def test_real_realtime_adapter_registers_all_controlled_tools_on_session() -> None:
    """Modele KAYIT EDİLEN tool'ların gerçek `function_tool` nesneleri olduğu
    ve backend kontrat listesindeki 12 tool'la birebir eşleştiği doğrulanır."""
    from agent.tools import TOOL_DEFINITIONS

    settings = _real_settings()
    adapter = LiveKitRealtimeSessionAdapter(settings)
    data = bootstrap()
    registry = ToolRegistry(
        ToolExecutor(call_id=data.call_id, api=NoopAPI(), events=NoopEvents())  # type: ignore[arg-type]
    )

    runtime = adapter.build(data, registry)

    registered_names = {getattr(t, "name", None) or t.info.name for t in runtime.session.tools}  # type: ignore[union-attr]
    expected_names = {d.name for d in TOOL_DEFINITIONS}
    assert registered_names == expected_names


class _RaisingSession:
    async def start(self, **_kwargs: object) -> None:
        raise RuntimeError("connection refused")


class _HangingSession:
    async def start(self, **_kwargs: object) -> None:
        await asyncio.sleep(10)


@pytest.mark.asyncio
async def test_real_realtime_adapter_start_wraps_connection_failure() -> None:
    """PHASE_8_RESILIENCE_REPORT.md: `LiveKitRealtimeSessionAdapter.start()`
    gerçek OpenAI realtime bağlantı hatasını `RealtimeSessionError`'a
    çevirdiğini iddia ediyordu ama hiçbir test bunu doğrulamıyordu (yalnız
    `FakeRealtimeSessionAdapter` test ediliyordu, o da hiç sarmalama yapmaz)."""
    from agent.session import RealtimeRuntime

    settings = _real_settings()
    adapter = LiveKitRealtimeSessionAdapter(settings)
    runtime = RealtimeRuntime(session=_RaisingSession(), assistant=object(), opening=object())  # type: ignore[arg-type]

    with pytest.raises(RealtimeSessionError, match="connection refused"):
        await adapter.start(runtime, room=object())


@pytest.mark.asyncio
async def test_real_realtime_adapter_start_wraps_timeout() -> None:
    from agent.session import RealtimeRuntime

    settings = _real_settings(REALTIME_STARTUP_TIMEOUT_SECONDS=0.05)
    adapter = LiveKitRealtimeSessionAdapter(settings)
    runtime = RealtimeRuntime(session=_HangingSession(), assistant=object(), opening=object())  # type: ignore[arg-type]

    with pytest.raises(RealtimeSessionError):
        await adapter.start(runtime, room=object())


def test_real_sip_participant_request_uses_dial_plan_fields() -> None:
    """`CreateSIPParticipantRequest`'in gerçek protobuf alanlarının dial-plan
    verisiyle doğru doldurulduğu — ağ çağrısı yapılmadan — doğrulanır."""
    plan = dial_plan(max_call_duration_seconds=180)

    request = build_sip_participant_request(plan)

    assert isinstance(request, lk_api.CreateSIPParticipantRequest)
    assert request.sip_trunk_id == plan.sip_trunk_id
    assert request.sip_call_to == plan.phone_e164
    assert request.room_name == plan.room_name
    assert request.participant_identity == plan.participant_identity
    assert request.participant_name == plan.participant_name
    assert request.wait_until_answered is True
    assert request.hide_phone_number is True
    assert request.max_call_duration.seconds == 180


def test_real_sip_participant_request_never_logs_or_exposes_extra_fields() -> None:
    """`hide_phone_number=True` dışında telefonun response/metadata alanlarına
    sızmadığını doğrular (`participant_metadata` boş olmalı)."""
    plan = dial_plan()

    request = build_sip_participant_request(plan)

    assert request.participant_metadata == ""
    assert plan.phone_e164 not in str(request.participant_attributes)


def test_real_sip_adapter_constructs_without_network_call() -> None:
    settings = _real_settings()
    adapter = LiveKitSIPParticipantAdapter(settings)
    assert adapter._settings is settings  # yalnız nesne inşası, I/O yok


def test_agent_server_entrypoint_constructs_without_network_call() -> None:
    """`build_server()`'ın gerçek `AgentServer` yapılandırmasıyla import/inşa
    edilebildiğini doğrular (worker'ı gerçekten BAŞLATMAZ)."""
    from agent.job_handler import build_server

    settings = _real_settings(
        INTERNAL_API_BASE_URL="http://internal.test",
        INTERNAL_SERVICE_TOKEN="token",
        LIVEKIT_SIP_OUTBOUND_TRUNK_ID="trunk-id",
    )

    server = build_server(settings)

    assert isinstance(server, AgentServer)
    # PHASE_8_RESILIENCE_REPORT.md: GRACEFUL_SHUTDOWN_SECONDS önceden hiçbir
    # yere bağlı değildi (ölü ayar); artık SDK'nın shutdown_process_timeout'una
    # aktarılıyor — bu, SIGTERM sonrası handle()'ın finally bloğuna tanınan
    # gerçek süre.
    assert server._shutdown_process_timeout == settings.GRACEFUL_SHUTDOWN_SECONDS


def test_entrypoint_is_picklable_for_job_process_pool() -> None:
    """LiveKit job process pool, her job'ı forkserver ile ayrı bir alt
    süreçte çalıştırmak için entrypoint referansını pickle'lar — bu yalnız
    modül seviyesinde (closure OLMAYAN) bir fonksiyon için mümkündür.
    Gerçek Linux Docker container'ında `AttributeError: Can't pickle local
    object 'build_server.<locals>.entrypoint'` ile ampirik olarak
    doğrulanmış bir regresyonu önler (bkz. PRODUCTION_INFRA_REPORT.md)."""
    import pickle

    from agent.job_handler import entrypoint

    dumped = pickle.dumps(entrypoint)
    restored = pickle.loads(dumped)

    assert restored is entrypoint
