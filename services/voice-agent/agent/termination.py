"""Görüşme sonu bekleme koordinatörü.

Gerçek LiveKit Agents SDK'sında (`livekit-agents==1.5.17`) `AgentSession`,
`livekit.rtc.EventEmitter[EventTypes]`'i miras alır (bkz.
`.venv/lib/python3.11/site-packages/livekit/agents/voice/agent_session.py`).
"close" event'i, oturum GERÇEKTEN kapandığında `CloseEvent(reason=CloseReason(...))`
payload'ıyla emit edilir — kaynak kodda doğrulanmış tetikleyiciler:

- `RoomIO` (`voice/room_io/room_io.py:432`): `RoomOptions(close_on_disconnect=True)`
  iken bağlı katılımcı (karşı taraf) LiveKit odasından ayrılırsa
  `session._close_soon(reason=CloseReason.PARTICIPANT_DISCONNECTED)` çağırır.
- `AgentSession.aclose()` (kendi kodumuzun çağırdığı) → kaynakta doğrulandı:
  `async def aclose(self): await self._aclose_impl(reason=CloseReason.USER_INITIATED)`
  — yani kendi `aclose()` çağrımız SDK'nın "close" event'ini KENDİSİ tetikler,
  event'i biz taklit etmiyoruz.
- Job runtime'ın job'ı kapatması → `CloseReason.JOB_SHUTDOWN`.
- Ölümcül bir hata → `CloseReason.ERROR`.
- Görev tamamlanma akışı → `CloseReason.TASK_COMPLETED`.

`EventEmitter.on()` yalnız SENKRON callback kabul eder (async fonksiyon
verilirse SDK kaynağında `ValueError` fırlatıldığı doğrulandı —
`livekit/rtc/event_emitter.py`); bu yüzden bu modüldeki callback'ler yalnız
`asyncio.Event.set()` çağırır, hiçbir I/O yapmaz.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from typing import Any, Protocol

from livekit.agents import CloseReason

from agent.models import DisconnectReason
from agent.redaction import redact_text

logger = logging.getLogger(__name__)

# CloseReason (SDK) -> DisconnectReason (bizim internal API sözleşmemiz).
# Backend `CompletionIn.disconnect_reason` serbest metin `str`dir (bkz.
# services/api/app/schemas/internal/voice_agent.py), bu yüzden bu eşleme
# backend şema değişikliği gerektirmeden genişletilebilir.
_CLOSE_REASON_MAP: dict[Any, DisconnectReason] = {
    CloseReason.PARTICIPANT_DISCONNECTED: DisconnectReason.REMOTE_HANGUP,
    CloseReason.USER_INITIATED: DisconnectReason.AGENT_HANGUP,
    CloseReason.JOB_SHUTDOWN: DisconnectReason.AGENT_HANGUP,
    CloseReason.TASK_COMPLETED: DisconnectReason.COMPLETED,
    CloseReason.ERROR: DisconnectReason.OPENAI_FAILURE,
}


class SessionLike(Protocol):
    # `event` kasıtlı olarak `Any` — gerçek `AgentSession.on/off` bunu bir
    # `Literal[...]` union'ı olarak tipler (bkz. livekit/agents/voice/events.py
    # EventTypes); Protocol'ün yapısal eşleşmesi dar bir Literal parametreyi
    # geniş `str` ile uyumsuz sayar, bu yüzden burada `Any` kullanılır.
    def on(self, event: Any, callback: Any) -> Any: ...
    def off(self, event: Any, callback: Any) -> None: ...
    async def aclose(self) -> None: ...


@dataclass(frozen=True)
class TerminationResult:
    reason: DisconnectReason
    detail: str


class CallTerminationWaiter:
    """Açılış cümlesinden sonra GERÇEK görüşme sonunu bekler.

    Üç yoldan biriyle biter (busy-wait veya yapay `while True` YOK — tamamı
    `asyncio.Event`/`asyncio.wait` tabanlı, event-driven):

    1. SDK'nın `close` event'i (uzak taraf kapattı / job shutdown / hata /
       görev tamamlandı) — gerçek sebep `CloseEvent.reason`'dan okunur.
    2. Modelin `end_call_safely` tool'unu çağırması → agent'ın kapanış
       cümlesini bitirmesi için kısa bir nezaket penceresi (`agent_state_changed`
       event'i izlenir) → kendi `session.aclose()` çağrımız.
    3. `max_call_duration_seconds` aşılırsa zorla TIMEOUT (üst sınır güvenliği).

    `request_end_call()` bağımsız olarak (session'dan önce, tool registry
    inşa edilirken) çağrılabilir olsun diye session, constructor'da değil
    yalnız `wait()` çağrısında alınır.
    """

    def __init__(self, *, max_duration_seconds: float, end_call_grace_seconds: float) -> None:
        self._max_duration = max_duration_seconds
        self._grace = end_call_grace_seconds
        self._close_event = asyncio.Event()
        self._close_info: dict[str, Any] = {}
        self._end_call_event = asyncio.Event()

    def request_end_call(self) -> None:
        """`end_call_safely` tool'u backend tarafından başarıyla işlendiğinde
        (`ToolExecutor` callback'i üzerinden) çağrılır. Idempotent'tir."""
        self._end_call_event.set()

    async def wait(self, session: SessionLike) -> TerminationResult:
        session.on("close", self._on_close)
        session.on("error", self._on_error)
        try:
            close_waiter = asyncio.create_task(self._close_event.wait())
            end_call_waiter = asyncio.create_task(self._end_call_flow(session))
            try:
                done, _pending = await asyncio.wait(
                    {close_waiter, end_call_waiter},
                    timeout=self._max_duration,
                    return_when=asyncio.FIRST_COMPLETED,
                )
            finally:
                for task in (close_waiter, end_call_waiter):
                    if not task.done():
                        task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await task

            if not done and not self._close_event.is_set():
                return TerminationResult(DisconnectReason.TIMEOUT, "max_call_duration_exceeded")

            if self._close_event.is_set():
                sdk_reason = self._close_info.get("reason")
                mapped = _CLOSE_REASON_MAP.get(sdk_reason, DisconnectReason.AGENT_ERROR)
                reason_name = getattr(sdk_reason, "value", str(sdk_reason))
                return TerminationResult(mapped, f"sdk_close_reason={reason_name}")

            # Güvenlik ağı: normal akışta close_event set edilmeden buraya
            # ulaşılamaz; yine de sessiz bir None dönüşü yerine açık bir
            # sonuç üretilir.
            return TerminationResult(DisconnectReason.AGENT_ERROR, "unknown_termination")
        finally:
            with contextlib.suppress(Exception):
                session.off("close", self._on_close)
            with contextlib.suppress(Exception):
                session.off("error", self._on_error)

    def _on_close(self, ev: Any) -> None:
        if not self._close_event.is_set():
            self._close_info["reason"] = getattr(ev, "reason", None)
            self._close_info["error"] = getattr(ev, "error", None)
            self._close_event.set()

    def _on_error(self, ev: Any) -> None:
        """Gerçek SDK `error` event'i (`ErrorEvent`) her zaman `close`
        tetiklemez — CODEX_AUDIT_PHASE_4_FIX.md YÜKSEK-1 bulgusu.

        Fatal/non-fatal ayrımı SDK kaynağından doğrulanan gerçek bir alana
        dayanır: `LLMError`/`RealtimeModelError`/`STTError`/`TTSError` hepsi
        `recoverable: bool` taşır (bkz. `livekit/agents/llm/realtime.py`,
        OpenAI plugin `_emit_error(error, recoverable=...)` — bağlantı/auth
        gibi kurtarılamaz durumlarda `recoverable=False`, toparlanabilir
        durumlarda `recoverable=True` kullanıldığı kaynakta doğrulandı).
        Yalnız `recoverable is False` (KESİN fatal) terminal sayılır; `True`
        veya bilinmeyen (`None`) durumlarda SDK kendi içinde toparlanır —
        görüşme gereksiz yere sonlandırılmaz.
        """
        error = getattr(ev, "error", None)
        self._close_info.setdefault("last_error", error)
        recoverable = getattr(error, "recoverable", None)
        if recoverable is False and not self._close_event.is_set():
            logger.warning(
                "Fatal (recoverable=False) realtime hatası; görüşme sonlandırılıyor: %s",
                redact_text(str(error)),
            )
            self._close_info["reason"] = CloseReason.ERROR
            self._close_event.set()

    async def _end_call_flow(self, session: SessionLike) -> None:
        await self._end_call_event.wait()
        await self._wait_agent_finished_speaking(session)
        if not self._close_event.is_set():
            with contextlib.suppress(Exception):
                await session.aclose()
            # `aclose()` kendi "close" event'ini zaten tetikler (doğrulanmış
            # gerçek SDK davranışı). Test double'ları bunu uygulamıyorsa diye
            # kısa bir ek bekleme + savunma amaçlı manuel set uygulanır.
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._close_event.wait(), timeout=2.0)
            if not self._close_event.is_set():
                self._close_info.setdefault("reason", CloseReason.USER_INITIATED)
                self._close_event.set()

    async def _wait_agent_finished_speaking(self, session: SessionLike) -> None:
        """`end_call_safely` sonrası modelin kapanış cümlesini sesli olarak
        bitirmesini bekler. Gerçek `agent_state_changed` event'i izlenir;
        ajan hiç konuşmaya başlamadıysa veya nezaket süresi dolarsa devam
        edilir (görüşmeyi sonsuza kadar bekletmemek için üst sınır)."""
        finished = asyncio.Event()
        state: dict[str, bool] = {"saw_speaking": False}

        def _on_state(ev: Any) -> None:
            new_state = getattr(ev, "new_state", None)
            if new_state == "speaking":
                state["saw_speaking"] = True
            elif state["saw_speaking"] and new_state is not None:
                finished.set()

        session.on("agent_state_changed", _on_state)
        try:
            await asyncio.wait_for(finished.wait(), timeout=self._grace)
        except TimeoutError:
            logger.info("End-call grace penceresi doldu, kapanışa devam ediliyor")
        finally:
            with contextlib.suppress(Exception):
                session.off("agent_state_changed", _on_state)
