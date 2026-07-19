from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from livekit import agents
from livekit.agents import AgentServer, JobContext

from agent.api_client import DuplicateConflictError, InternalAPIClient
from agent.config import VoiceAgentSettings, get_settings
from agent.errors import (
    CallNotDialableError,
    CompletionError,
    InternalAPIAuthenticationError,
    InternalAPIPermanentError,
    InternalAPITransientError,
    RealtimeSessionError,
    SIPParticipantError,
)
from agent.events import EventSink, LifecycleEventDispatcher
from agent.models import (
    AgentEventType,
    BootstrapResponse,
    CompletionIn,
    DialPlanResponse,
    DisconnectReason,
    GenericAcceptedResponse,
    JobMetadata,
)
from agent.redaction import safe_error_message
from agent.session import LiveKitRealtimeSessionAdapter, RealtimeSessionAdapter
from agent.sip import LiveKitSIPParticipantAdapter, SIPParticipantAdapter
from agent.termination import CallTerminationWaiter
from agent.tools import ToolExecutor, ToolRegistry
from agent.transcript import QueuedTranscriptSink, TranscriptSink
from agent.usage import ProviderUsageSink, usage_from_session

logger = logging.getLogger(__name__)


class JobLike(Protocol):
    @property
    def metadata(self) -> str: ...


class ContextLike(Protocol):
    @property
    def job(self) -> JobLike: ...

    @property
    def room(self) -> Any: ...

    async def connect(self) -> None: ...

    def shutdown(self, reason: str = "") -> None: ...


class MutableJobLike(Protocol):
    metadata: str


class MutableContextLike(Protocol):
    job: MutableJobLike
    room: Any

    async def connect(self) -> None: ...

    def shutdown(self, reason: str = "") -> None: ...


@dataclass
class RuntimeAdapters:
    api: InternalAPIClient
    sip: SIPParticipantAdapter
    realtime: RealtimeSessionAdapter


def _log_background_failure(task: asyncio.Task[None]) -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.warning("Arka plan session-event task'ı hata verdi: %s", safe_error_message(exc))


class SessionEventBridge:
    """Gerçek `AgentSession` event'lerini (konuşma durumu + final transcript
    turnleri) backend'e aktarır.

    `EventEmitter.on()` yalnız senkron callback kabul ettiği için (SDK
    kaynağında doğrulandı — async callback verilirse `ValueError` fırlatır),
    her callback burada `asyncio.create_task` ile arka plana devrediyor; bu
    SDK'nın kendi dokümantasyonunun önerdiği yöntemdir. Task'lar güçlü
    referansla (`self._background`) tutulur ki GC tarafından sessizce
    iptal edilmesinler; hataları `_log_background_failure` ile loglanır,
    sessizce yutulmaz.
    """

    def __init__(self, *, events: EventSink, transcript: TranscriptSink) -> None:
        self._events = events
        self._transcript = transcript
        self._turn_seq = 0
        self._background: set[asyncio.Task[None]] = set()

    def attach(self, session: Any) -> None:
        session.on("user_state_changed", self._on_user_state)
        session.on("agent_state_changed", self._on_agent_state)
        session.on("conversation_item_added", self._on_conversation_item)

    def detach(self, session: Any) -> None:
        with contextlib.suppress(Exception):
            session.off("user_state_changed", self._on_user_state)
        with contextlib.suppress(Exception):
            session.off("agent_state_changed", self._on_agent_state)
        with contextlib.suppress(Exception):
            session.off("conversation_item_added", self._on_conversation_item)

    async def drain(self) -> None:
        """Bekleyen arka plan task'larının teslim edilmesini bekler."""
        pending = [t for t in self._background if not t.done()]
        if pending:
            await asyncio.wait(pending, timeout=5.0)

    def _spawn(self, coro: Any) -> None:
        task = asyncio.create_task(coro)
        self._background.add(task)
        task.add_done_callback(self._background.discard)
        task.add_done_callback(_log_background_failure)

    def _on_user_state(self, ev: Any) -> None:
        new_state = getattr(ev, "new_state", None)
        old_state = getattr(ev, "old_state", None)
        if new_state == "speaking":
            self._spawn(self._events.emit(AgentEventType.USER_SPEECH_STARTED))
        elif old_state == "speaking" and new_state != "speaking":
            self._spawn(self._events.emit(AgentEventType.USER_SPEECH_STOPPED))

    def _on_agent_state(self, ev: Any) -> None:
        new_state = getattr(ev, "new_state", None)
        old_state = getattr(ev, "old_state", None)
        if new_state == "speaking":
            self._spawn(self._events.emit(AgentEventType.AGENT_SPEECH_STARTED))
        elif old_state == "speaking" and new_state != "speaking":
            self._spawn(self._events.emit(AgentEventType.AGENT_SPEECH_STOPPED))

    def _on_conversation_item(self, ev: Any) -> None:
        item = getattr(ev, "item", None)
        role = getattr(item, "role", None)
        text_content_fn = getattr(item, "text_content", None)
        text = text_content_fn if isinstance(text_content_fn, str) else None
        if not text or role not in ("user", "assistant", "system", "developer"):
            return
        speaker = "agent" if role == "assistant" else "user" if role == "user" else "system"
        self._turn_seq += 1
        created_at = getattr(item, "created_at", None)
        timestamp = (
            datetime.fromtimestamp(created_at, tz=UTC)
            if isinstance(created_at, int | float)
            else datetime.now(UTC)
        )
        turn_id = str(getattr(item, "id", None) or f"turn-{self._turn_seq}")
        self._spawn(
            self._transcript.enqueue_turn(
                turn_id=turn_id,
                speaker=speaker,  # type: ignore[arg-type]
                text=text,
                started_at=timestamp,
                ended_at=timestamp,
                is_final=True,
                sequence=self._turn_seq,
            )
        )


class _CompletionAPI(Protocol):
    """`CompletionGuard.complete_once()`'un GERÇEKTEN ihtiyaç duyduğu yüzey.

    `InternalAPIClient`'ın somut sınıfı yerine yapısal (structural) bir
    Protocol kullanılır — `complete_once` yalnız `api.complete(...)` çağırır,
    başka hiçbir üye kullanmaz. Bu, testlerdeki dar test double'larının
    (`_RecordingAPI`/`_AlwaysFailingAPI` — yalnız `complete()` uygulayan)
    gerçek `InternalAPIClient`'tan miras almadan veya cast/ignore
    kullanmadan doğal olarak tip-uyumlu olmasını sağlar; production'da
    `InternalAPIClient` zaten bu yüzeyi karşılıyor, davranış DEĞİŞMEDİ."""

    async def complete(
        self, call_id: uuid.UUID, completion: CompletionIn
    ) -> GenericAcceptedResponse: ...


class CompletionGuard:
    """Completion teslimatını tek seferlik VE güvenilir hale getirir.

    Önceki tasarımdaki hata: `_completed` bayrağı API çağrısından ÖNCE set
    ediliyordu, bu yüzden teslimat başarısız olsa bile guard sessizce
    "tamamlandı" sayılıyordu (bkz. CLAUDE_AUDIT_PHASE_4.md YÜKSEK-1).
    Bu sürümde:
    - `_completed` yalnız `api.complete()` GERÇEKTEN başarılı olduğunda True olur.
    - Retry YALNIZ `InternalAPITransientError` için yapılır — bu istisna
      `api_client.py`'nin kendi iç retry bütçesi (timeout/connection-reset/
      429/5xx) tükendikten SONRA fırlatılır (bkz. CODEX_AUDIT_PHASE_4_FIX.md
      YÜKSEK-2). Kalıcı hatalar (`InternalAPIAuthenticationError` 401/403,
      `InternalAPIPermanentError` 400/404/422/vb., `CallNotDialableError`,
      `DuplicateConflictError` 409 farklı payload) İLK denemede fail eder —
      aynı payload'la tekrar denemek sonucu asla değiştirmez.
    - Tüm denemeler tükenirse (veya ilk denemede kalıcı hata alınırsa)
      `_exhausted=True` olur, açık bir `logger.error` üretilir ve
      `CompletionError` fırlatılır — sessiz yutma yok.
    - Aynı job içinde ikinci bir `complete_once` çağrısı (ör. genel except
      bloğundan) `_completed` veya `_exhausted` zaten True ise no-op'tur;
      böylece tükenmiş bir completion sonsuz retry döngüsüne girmez.
    - `asyncio.Lock` ile korunur: iki ayrı task aynı anda `complete_once`
      çağırırsa (ör. remote hangup ile end_call_safely yarışı) yalnız biri
      gerçekten `api.complete()` çağırır, diğeri kilit serbest kaldığında
      `_completed`'in artık True olduğunu görüp no-op döner.
    - Aynı `completion_event_id` (`f"completion-{call_id}"`) TÜM denemelerde
      korunur — backend idempotency anahtarı hiç değişmez.
    """

    def __init__(self, *, max_attempts: int = 3) -> None:
        self._completed = False
        self._exhausted = False
        self._max_attempts = max_attempts
        self._lock = asyncio.Lock()

    @property
    def completed(self) -> bool:
        return self._completed

    async def complete_once(
        self,
        *,
        api: _CompletionAPI,
        call_id: uuid.UUID,
        started_monotonic: float,
        reason: DisconnectReason,
        final_usage_event_id: str | None = None,
        sip_reason: str | None = None,
    ) -> None:
        async with self._lock:
            if self._completed:
                return
            if self._exhausted:
                logger.warning(
                    "Completion daha önce tükenmişti; tekrar denenmiyor (call_id=%s)", call_id
                )
                return

            ended_at = datetime.now(UTC)
            duration = max(int(time.monotonic() - started_monotonic), 0)
            completion = CompletionIn(
                completion_event_id=f"completion-{call_id}",
                disconnect_reason=reason.value,
                ended_at=ended_at,
                duration_seconds=duration,
                final_usage_event_id=final_usage_event_id,
                sip_reason=sip_reason,
            )

            last_exc: Exception | None = None
            attempts_made = 0
            for attempt in range(1, self._max_attempts + 1):
                attempts_made = attempt
                try:
                    await api.complete(call_id, completion)
                    self._completed = True
                    return
                except InternalAPITransientError as exc:
                    # Yalnız GERÇEKTEN geçici sınıf — api_client.py kendi iç
                    # retry bütçesini zaten tüketti; burada daha uzun vadeli
                    # bir pencereyle tekrar deneriz.
                    last_exc = exc
                    if attempt < self._max_attempts:
                        await asyncio.sleep(min(2 ** (attempt - 1) * 0.5, 4.0))
                        continue
                    break
                except (
                    InternalAPIAuthenticationError,
                    InternalAPIPermanentError,
                    CallNotDialableError,
                    DuplicateConflictError,
                ) as exc:
                    # Kalıcı hata — aynı payload'la tekrar denemek sonucu
                    # değiştirmez; ilk denemede fail et.
                    last_exc = exc
                    break
                except Exception as exc:  # noqa: BLE001 - bilinmeyen tip: güvenli varsayılan
                    # Sınıflandırılamayan bir hata tipini bilinmeden retry
                    # etmek, tam olarak bu bulgunun nedeniydi (her hatayı
                    # retry etmek). Güvenli varsayılan: tek deneme, fail.
                    last_exc = exc
                    break

            self._exhausted = True
            logger.error(
                "Completion teslimatı %s denemeden sonra başarısız oldu (call_id=%s, "
                "hata_sınıfı=%s); call backend'de terminal olmayan durumda kalabilir, "
                "watchdog'a düşecek: %s",
                attempts_made,
                call_id,
                type(last_exc).__name__ if last_exc else "unknown",
                safe_error_message(last_exc) if last_exc else "unknown",
            )
            raise CompletionError("Completion delivery failed.") from last_exc


def parse_call_id(metadata: str) -> uuid.UUID:
    try:
        payload = json.loads(metadata or "{}")
        return JobMetadata.model_validate(payload).call_id
    except Exception as exc:
        raise ValueError("Job metadata must contain only a valid call_id.") from exc


class VoiceAgentJobHandler:
    def __init__(self, settings: VoiceAgentSettings, adapters: RuntimeAdapters) -> None:
        self._settings = settings
        self._adapters = adapters
        self._completion_guard = CompletionGuard()
        # Yalnız test gözlemlenebilirliği için: gerçek akışı hiçbir şekilde
        # değiştirmez, üretimde okunmaz. Testler `end_call_safely` tool
        # zincirini (ayrıca test_tools.py'de test edilir) yeniden kurmak
        # yerine gerçek `handle()` çağrısının kurduğu waiter'a doğrudan
        # erişip `request_end_call()` tetikleyebilsin diye eklendi.
        self.last_waiter: CallTerminationWaiter | None = None

    async def handle(self, ctx: ContextLike) -> None:
        started = time.monotonic()
        call_id = parse_call_id(ctx.job.metadata)
        events = LifecycleEventDispatcher(
            call_id=call_id,
            api=self._adapters.api,
            max_size=self._settings.EVENT_QUEUE_MAX_SIZE,
        )
        events.start()
        transcript = QueuedTranscriptSink(
            call_id=call_id,
            api=self._adapters.api,
            max_size=self._settings.TRANSCRIPT_QUEUE_MAX_SIZE,
        )
        transcript.start()
        usage_sink = ProviderUsageSink(call_id=call_id, api=self._adapters.api)
        bridge = SessionEventBridge(events=events, transcript=transcript)

        runtime = None
        dial_plan: DialPlanResponse | None = None
        bootstrap: BootstrapResponse | None = None
        try:
            bootstrap = await self._bootstrap(call_id)
            await events.emit(
                AgentEventType.AGENT_JOB_STARTED,
                {"call_id": str(call_id)},
                important=True,
            )
            dial_plan = await self._adapters.api.dial_plan(call_id)
            await ctx.connect()

            # Görüşme sonu bekleyicisi: dial plan'daki gerçek üst sınırla
            # kurulur; `end_call_safely` tool'u bunu tetikleyecek şekilde
            # ToolExecutor'a bağlanır (session henüz yok — yalnız event
            # referansı gerekiyor, bkz. agent/termination.py tasarım notu).
            waiter = CallTerminationWaiter(
                max_duration_seconds=float(dial_plan.max_call_duration_seconds),
                end_call_grace_seconds=self._settings.END_CALL_GRACE_SECONDS,
            )
            self.last_waiter = waiter
            tools = ToolRegistry(
                ToolExecutor(
                    call_id=call_id,
                    api=self._adapters.api,
                    events=events,
                    on_end_call_requested=waiter.request_end_call,
                )
            )
            runtime = self._adapters.realtime.build(bootstrap, tools)

            await events.emit(AgentEventType.SIP_PARTICIPANT_CREATING, important=True)
            await events.emit(AgentEventType.DIALING, important=True)
            try:
                sip_handle = await self._adapters.sip.create_participant(dial_plan)
            except SIPParticipantError as exc:
                await events.emit(
                    AgentEventType.AGENT_JOB_FAILED,
                    {"reason": "sip_failure", "sip_reason": exc.reason},
                    important=True,
                )
                await self._completion_guard.complete_once(
                    api=self._adapters.api,
                    call_id=call_id,
                    started_monotonic=started,
                    reason=DisconnectReason.SIP_FAILURE,
                    sip_reason=exc.reason,
                )
                return
            await events.emit(AgentEventType.RINGING, important=True)
            if sip_handle.answered:
                await events.emit(AgentEventType.ANSWERED, important=True)

            await self._adapters.realtime.start(runtime, ctx.room)
            bridge.attach(runtime.session)
            await events.emit(AgentEventType.AGENT_SESSION_STARTED, important=True)
            await runtime.opening.play_once_after_answer(runtime.session)

            # ─── GERÇEK GÖRÜŞME ───────────────────────────────────────────
            # Açılıştan sonra artık bekliyoruz: karşı taraf konuşabilir, model
            # tool çağırabilir, görüşme yalnız gerçek bir terminal olayla
            # (remote hangup / end_call_safely / timeout / hata) biter.
            termination = await waiter.wait(runtime.session)
            # ────────────────────────────────────────────────────────────

            final_usage_id = await self._report_final_usage(
                usage_sink, runtime.session, bootstrap.campaign.model
            )
            await events.emit(
                AgentEventType.CALL_DISCONNECTED,
                {"reason": termination.reason.value, "detail": termination.detail},
                important=True,
            )
            await self._completion_guard.complete_once(
                api=self._adapters.api,
                call_id=call_id,
                started_monotonic=started,
                reason=termination.reason,
                final_usage_event_id=final_usage_id,
            )
        except CallNotDialableError:
            await events.emit(
                AgentEventType.AGENT_JOB_FAILED,
                {"reason": "not_dialable"},
                important=True,
            )
            await self._completion_guard.complete_once(
                api=self._adapters.api,
                call_id=call_id,
                started_monotonic=started,
                reason=DisconnectReason.AGENT_ERROR,
            )
        except RealtimeSessionError:
            await events.emit(
                AgentEventType.AGENT_JOB_FAILED,
                {"reason": "openai_realtime_failure"},
                important=True,
            )
            await self._completion_guard.complete_once(
                api=self._adapters.api,
                call_id=call_id,
                started_monotonic=started,
                reason=DisconnectReason.OPENAI_FAILURE,
            )
        except Exception:
            logger.exception("Voice-agent job failed")
            await events.emit(
                AgentEventType.AGENT_JOB_FAILED,
                {"reason": "agent_error"},
                important=True,
            )
            with contextlib.suppress(CompletionError):
                await self._completion_guard.complete_once(
                    api=self._adapters.api,
                    call_id=call_id,
                    started_monotonic=started,
                    reason=DisconnectReason.AGENT_ERROR,
                )
        finally:
            if runtime is not None:
                bridge.detach(runtime.session)
                await bridge.drain()
            await transcript.stop()
            await events.emit(AgentEventType.AGENT_SESSION_ENDED, important=True)
            await events.stop()
            if runtime is not None:
                await self._adapters.realtime.close(runtime)
            if dial_plan is not None:
                await self._adapters.sip.hangup(
                    dial_plan.room_name,
                    dial_plan.participant_identity,
                )
            ctx.shutdown("voice-agent-job-finished")

    async def _bootstrap(self, call_id: uuid.UUID) -> BootstrapResponse:
        return await self._adapters.api.bootstrap(call_id)

    async def _report_final_usage(
        self, usage_sink: ProviderUsageSink, session: Any, model: str
    ) -> str | None:
        real_usage = usage_from_session(session, model=model, is_final=True)
        if real_usage is not None:
            await usage_sink.send_usage(real_usage)
            return real_usage.usage_event_id
        return await usage_sink.report_unavailable(model=model, is_final=True)


async def entrypoint(ctx: JobContext) -> None:
    # NOT (PRODUCTION_INFRA_REPORT.md): bu fonksiyon MUTLAKA modül seviyesinde
    # (üst düzey, closure OLMAYAN) tanımlanmalı — LiveKit'in job process pool'u
    # her job'ı ayrı bir alt süreçte (forkserver) çalıştırmak için entrypoint
    # referansını pickle'lar; `settings`'i closure ile yakalayan iç içe bir
    # fonksiyon `AttributeError: Can't pickle local object` ile başarısız olur
    # (gerçek Linux Docker container'ında ampirik olarak doğrulandı — macOS'ta
    # farklı bir multiprocessing start method kullanıldığı için gizli kalmıştı).
    # `get_settings()` `@lru_cache`'li olduğu için alt süreç kendi ayarlarını
    # ortam değişkenlerinden ucuz şekilde yeniden türetir, pickle taşımaya
    # gerek kalmaz.
    settings = get_settings()
    api = InternalAPIClient(settings)
    try:
        handler = VoiceAgentJobHandler(
            settings,
            RuntimeAdapters(
                api=api,
                sip=LiveKitSIPParticipantAdapter(settings),
                realtime=LiveKitRealtimeSessionAdapter(settings),
            ),
        )
        await handler.handle(ctx)
    finally:
        await api.aclose()


def build_server(settings: VoiceAgentSettings) -> AgentServer:
    server = AgentServer(
        ws_url=settings.LIVEKIT_URL,
        api_key=settings.LIVEKIT_API_KEY.get_secret_value(),
        api_secret=settings.LIVEKIT_API_SECRET.get_secret_value(),
        # NOT (PHASE_8_RESILIENCE_REPORT.md): `GRACEFUL_SHUTDOWN_SECONDS`
        # önceden hiçbir yere bağlı DEĞİLDİ (ayarlanmış izlenimi veren ölü bir
        # ayar). SDK'nın `shutdown_process_timeout`'u — SIGTERM sonrası
        # `handle()`'ın kendi `finally` bloğunun (transcript/event bridge
        # drain, realtime session kapatma, SIP hangup) tamamlanması için
        # tanınan süre — tam olarak bu ayarın anlamıyla eşleşiyor. SDK'nın
        # `drain_timeout`'u (aktif çağrının TAMAMEN bitmesini bekleme süresi,
        # varsayılan 1800s) BİLEREK değiştirilmedi: 120s'lik üst sınırı olan
        # bu ayarı oraya bağlamak, uzun süren gerçek bir görüşmeyi ortasında
        # zorla kesme riskini artırırdı — mevcut cömert varsayılan daha güvenli.
        shutdown_process_timeout=settings.GRACEFUL_SHUTDOWN_SECONDS,
    )
    server.rtc_session(entrypoint, agent_name=settings.LIVEKIT_AGENT_NAME)
    return server


def run_worker(settings: VoiceAgentSettings) -> None:
    settings.require_runtime_ready()
    server = build_server(settings)
    agents.cli.run_app(server)
