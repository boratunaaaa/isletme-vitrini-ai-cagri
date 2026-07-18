from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Protocol, cast

from livekit.agents import Agent, AgentSession, CloseReason, room_io
from livekit.plugins import openai
from openai.types import realtime
from openai.types.realtime import realtime_audio_input_turn_detection as turn_detection_types

from agent.config import VoiceAgentSettings
from agent.errors import RealtimeSessionError
from agent.models import ALLOWED_MODELS, ALLOWED_VOICES, BootstrapResponse
from agent.redaction import safe_error_message
from agent.tools import ToolRegistry

logger = logging.getLogger(__name__)


def build_runtime_instructions(bootstrap: BootstrapResponse) -> str:
    lead = bootstrap.lead
    config = bootstrap.agent_configuration
    kb = "\n".join(
        f"- {item.category} / {item.title}: {item.content}" for item in bootstrap.knowledge_base
    )
    context = [
        config.system_prompt,
        f"## Görüşme hedefi\n{config.objective}",
        f"## İtiraz karşılama kuralları\n{config.objection_rules}",
        "## İşletme bağlamı",
        f"İşletme adı: {lead.business_name}",
    ]
    if lead.sector:
        context.append(f"Sektör: {lead.sector}")
    if lead.district or lead.city:
        context.append(f"Bölge: {', '.join(x for x in [lead.district, lead.city] if x)}")
    if lead.website:
        context.append(f"Web sitesi: {lead.website}")
    if bootstrap.campaign.name:
        context.append(f"Kampanya: {bootstrap.campaign.name}")
    context.extend(
        [
            "## Bilgi bankası",
            kb or "(Bilgi bankası boş. Emin olmadığın bilgiyi uydurma.)",
            "## Açılış",
            config.opening_script,
            "Açılışta İşletme Vitrini adına aradığını ve yapay zekâ destekli asistan "
            "olduğunu doğal biçimde belirt. Telefon numarası, token, API anahtarı veya "
            "teknik ID söyleme.",
        ]
    )
    return "\n\n".join(part for part in context if part)


class OpeningGate:
    def __init__(self, opening_script: str) -> None:
        self._opening_script = opening_script
        self._played = False

    async def play_once_after_answer(self, session: AgentSession) -> bool:
        if self._played:
            return False
        self._played = True
        await session.generate_reply(instructions=self._opening_script)
        return True


@dataclass
class RealtimeRuntime:
    session: AgentSession
    assistant: Agent
    opening: OpeningGate


class RealtimeSessionAdapter(Protocol):
    def build(self, bootstrap: BootstrapResponse, tools: ToolRegistry) -> RealtimeRuntime: ...

    async def start(self, runtime: RealtimeRuntime, room: Any) -> None: ...

    async def close(self, runtime: RealtimeRuntime) -> None: ...


class LiveKitRealtimeSessionAdapter:
    def __init__(self, settings: VoiceAgentSettings) -> None:
        self._settings = settings

    def build(self, bootstrap: BootstrapResponse, tools: ToolRegistry) -> RealtimeRuntime:
        model = bootstrap.campaign.model or self._settings.OPENAI_REALTIME_DEFAULT_MODEL
        voice = bootstrap.campaign.voice or self._settings.OPENAI_REALTIME_DEFAULT_VOICE
        if model not in ALLOWED_MODELS:
            raise RealtimeSessionError("Unsupported realtime model.")
        if voice not in ALLOWED_VOICES:
            raise RealtimeSessionError("Unsupported realtime voice.")
        rt_model = openai.realtime.RealtimeModel(
            model=model,
            voice=voice,
            modalities=["audio"],
            api_key=self._settings.openai_api_key,
            input_audio_transcription=realtime.AudioTranscription(
                model="gpt-realtime-whisper",
                language="tr",
            ),
            turn_detection=turn_detection_types.SemanticVad(
                type="semantic_vad",
                create_response=True,
                eagerness="auto",
                interrupt_response=True,
            ),
            max_session_duration=float(bootstrap.campaign.max_call_duration_seconds),
        )
        livekit_tools = cast(Any, tools.livekit_tools())
        session: AgentSession = AgentSession(
            llm=rt_model,
            tools=livekit_tools,
            max_tool_steps=3,
            allow_interruptions=True,
            min_interruption_duration=0.35,
            user_away_timeout=None,
        )
        assistant = Agent(
            instructions=build_runtime_instructions(bootstrap),
            tools=livekit_tools,
            allow_interruptions=True,
        )
        return RealtimeRuntime(
            session=session,
            assistant=assistant,
            opening=OpeningGate(bootstrap.agent_configuration.opening_script),
        )

    async def start(self, runtime: RealtimeRuntime, room: Any) -> None:
        try:
            await asyncio.wait_for(
                runtime.session.start(
                    room=room,
                    agent=runtime.assistant,
                    room_options=room_io.RoomOptions(
                        audio_input=room_io.AudioInputOptions(
                            sample_rate=24000,
                            num_channels=1,
                            auto_gain_control=True,
                        ),
                        close_on_disconnect=True,
                    ),
                ),
                timeout=self._settings.REALTIME_STARTUP_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            raise RealtimeSessionError(
                f"Realtime session failed: {safe_error_message(exc)}"
            ) from exc

    async def close(self, runtime: RealtimeRuntime) -> None:
        await runtime.session.aclose()


# ─── Test double'ları ─────────────────────────────────────────────────────────
#
# `FakeRealtimeSession`, gerçek `AgentSession`'ın bu modülün ihtiyaç duyduğu
# yüzeyini (event emitter `.on/.off`, `.agent_state`, `.usage`, `.aclose()`nin
# kendi "close" event'ini tetiklemesi) taklit eder. Gerçek SDK davranışı
# `livekit.rtc.EventEmitter` kaynağından doğrulanmıştır: `.on()` yalnız
# senkron callback kabul eder, `.emit()` kayıtlı callback'leri senkron çağırır.


class _FakeCloseEvent:
    def __init__(self, reason: Any, error: Exception | None = None) -> None:
        self.reason = reason
        self.error = error


class _FakeAgentStateChangedEvent:
    def __init__(self, old_state: str, new_state: str) -> None:
        self.old_state = old_state
        self.new_state = new_state


class _FakeRealtimeModelError:
    """Gerçek `RealtimeModelError`'ın (bkz. `livekit/agents/llm/realtime.py`)
    testler için ihtiyaç duyulan tek alanını (`recoverable`) taklit eder."""

    def __init__(self, message: str, *, recoverable: bool) -> None:
        self.message = message
        self.recoverable = recoverable

    def __str__(self) -> str:
        return self.message


class _FakeErrorEvent:
    def __init__(self, error: Any) -> None:
        self.error = error


class _FakeModelUsage:
    def __init__(self, **fields: int) -> None:
        self.type = "llm_usage"
        self.provider = "openai"
        self.model = fields.pop("model", "gpt-realtime-2.1-mini")
        for key, value in fields.items():
            setattr(self, key, value)

    def __getattr__(self, name: str) -> int:  # alanı hiç set edilmemişse 0
        return 0


@dataclass
class _FakeUsageSnapshot:
    model_usage: list[Any] = field(default_factory=list)


class FakeRealtimeSession:
    """Minimal, gerçek `EventEmitter` semantiğine sadık sahte oturum."""

    def __init__(self) -> None:
        self.started = False
        self.closed = False
        self.replies: list[str] = []
        self.agent_state = "initializing"
        self.usage = _FakeUsageSnapshot()
        self._listeners: dict[str, set[Any]] = {}

    def on(self, event: str, callback: Any) -> Any:
        self._listeners.setdefault(event, set()).add(callback)
        return callback

    def off(self, event: str, callback: Any) -> None:
        self._listeners.get(event, set()).discard(callback)

    def emit(self, event: str, *args: Any) -> None:
        for callback in list(self._listeners.get(event, set())):
            callback(*args)

    async def start(self, **_: Any) -> None:
        self.started = True

    async def generate_reply(self, *, instructions: str, **_: Any) -> None:
        self.replies.append(instructions)

    async def aclose(self) -> None:
        self.closed = True
        self.emit("close", _FakeCloseEvent(reason=CloseReason.USER_INITIATED))

    # Testlerin senaryo simülasyonu için kullandığı yardımcılar (gerçek SDK'da
    # karşılığı yok; yalnız test double'ında bulunur):

    def simulate_participant_disconnect(self) -> None:
        self.emit("close", _FakeCloseEvent(reason=CloseReason.PARTICIPANT_DISCONNECTED))

    def simulate_error_close(self, error: Exception | None = None) -> None:
        self.emit("close", _FakeCloseEvent(reason=CloseReason.ERROR, error=error))

    def simulate_job_shutdown(self) -> None:
        self.emit("close", _FakeCloseEvent(reason=CloseReason.JOB_SHUTDOWN))

    def simulate_fatal_realtime_error(self, message: str = "connection lost") -> None:
        """`recoverable=False` ile gerçek SDK `error` event'i (`close` DEĞİL —
        SDK'da `error` ve `close` ayrı event'lerdir, bkz. `termination.py`)."""
        self.emit("error", _FakeErrorEvent(_FakeRealtimeModelError(message, recoverable=False)))

    def simulate_recoverable_realtime_error(self, message: str = "transient glitch") -> None:
        """`recoverable=True` — SDK kendi içinde toparlanır, terminal DEĞİL."""
        self.emit("error", _FakeErrorEvent(_FakeRealtimeModelError(message, recoverable=True)))

    def simulate_agent_speaking(self) -> None:
        old = self.agent_state
        self.agent_state = "speaking"
        self.emit("agent_state_changed", _FakeAgentStateChangedEvent(old, "speaking"))

    def simulate_agent_idle(self) -> None:
        old = self.agent_state
        self.agent_state = "listening"
        self.emit("agent_state_changed", _FakeAgentStateChangedEvent(old, "listening"))

    def set_fake_usage(self, **fields: int) -> None:
        self.usage = _FakeUsageSnapshot(model_usage=[_FakeModelUsage(**fields)])


class FakeRealtimeSessionAdapter:
    def __init__(self) -> None:
        self.runtime: RealtimeRuntime | None = None

    def build(self, bootstrap: BootstrapResponse, tools: ToolRegistry) -> RealtimeRuntime:
        session = FakeRealtimeSession()
        assistant = Agent(instructions=build_runtime_instructions(bootstrap), tools=[])
        runtime = RealtimeRuntime(
            session=session,  # type: ignore[arg-type]
            assistant=assistant,
            opening=OpeningGate(bootstrap.agent_configuration.opening_script),
        )
        self.runtime = runtime
        return runtime

    async def start(self, runtime: RealtimeRuntime, room: Any) -> None:
        await runtime.session.start(room=room, agent=runtime.assistant)  # type: ignore[call-arg]

    async def close(self, runtime: RealtimeRuntime) -> None:
        await runtime.session.aclose()
