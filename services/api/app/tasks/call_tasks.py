"""Çağrı görevleri: dial dispatch, watchdog, terminal işleme."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.locks import idempotency_seen
from app.core.logging import call_id_var
from app.db.session import session_scope
from app.models.call import Call
from app.models.enums import ACTIVE_CALL_STATUSES, CallStatus
from app.providers.base import OutboundCallRequest
from app.providers.telephony import TelephonyError, get_telephony_provider
from app.services.call_service import (
    derive_fallback_outcome,
    finalize_outcome,
    record_event,
    transition,
)
from app.services.campaign_service import handle_call_terminal, maybe_complete_campaign
from app.services.orchestrator import build_dial_info
from app.worker import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.call_tasks.place_call", bind=True, max_retries=0)
def place_call(self: Any, call_id: str) -> None:
    """Queued çağrıyı LiveKit agent dispatch ile başlatır.

    SIP participant'ı agent oluşturur (LiveKit resmi deseni); bu görev yalnız
    dispatch eder. Gerçek telefon aramasının olabilmesi için LIVE_CALLS_ENABLED
    zaten orchestrator'da doğrulanmıştır; burada tekrar kontrol edilir
    (savunma katmanı).
    """
    call_id_var.set(call_id)
    settings = get_settings()
    with session_scope() as db:
        call = db.get(Call, uuid.UUID(call_id))
        if call is None or call.status != CallStatus.QUEUED.value:
            logger.info("place_call atlandı; call yok veya queued değil")
            return

        if not settings.LIVE_CALLS_ENABLED and call.telephony_provider != "test":
            transition(db, call, CallStatus.CANCELLED, reason="live_calls_disabled")
            _finalize_terminal(db, call)
            return

        # NOT (PHASE_8_RESILIENCE_REPORT.md): `task_acks_late=True` +
        # `worker_prefetch_multiplier=1` altında, worker gerçek SIP dial
        # İSTEĞİNİ gönderdikten SONRA ama bu `with session_scope()` bloğu
        # commit edilmeden ÖNCE çökerse (crash/OOM/SIGKILL), Celery görevi
        # QUEUED durumdaki DB satırıyla YENİDEN teslim eder — bu da
        # `create_outbound_call`'ın İKİNCİ kez çağrılıp gerçek bir müşteriyi
        # mükerrer aramasına yol açabilirdi. Redis tabanlı tek-seferlik işaret,
        # dial denemesini DB transaction'ından bağımsız olarak kalıcılaştırır:
        # ikinci teslimat, gerçek aramayı asla tekrar denemeden güvenli
        # şekilde FAILED'e döner.
        if idempotency_seen(f"dial:{call_id}"):
            logger.error(
                "place_call yeniden teslim edildi; dial daha önce denenmiş — "
                "mükerrer arama riskini önlemek için atlanıyor"
            )
            call.error_code = "duplicate_dispatch_prevented"
            transition(db, call, CallStatus.FAILED, reason="duplicate_dispatch_prevented")
            _finalize_terminal(db, call)
            return

        transition(db, call, CallStatus.PREPARING)
        dial_info = build_dial_info(db, call)
        provider = get_telephony_provider(call.telephony_provider)
        request = OutboundCallRequest(
            call_id=str(call.id),
            room_name=call.livekit_room_name or f"call-{call.id}",
            phone_e164=dial_info["phone_e164"],
            trunk_id=dial_info["sip_trunk_id"],
            agent_name=settings.LIVEKIT_AGENT_NAME,
            max_duration_seconds=dial_info["max_duration_seconds"],
            metadata={"call_id": str(call.id)},
        )
        try:
            result = asyncio.run(provider.create_outbound_call(request))
            call.provider_call_id = result.provider_call_id
            transition(db, call, CallStatus.DIALING)
        except TelephonyError as exc:
            logger.error("Dispatch hatası: %s", exc.code)
            call.error_code = exc.code
            transition(db, call, CallStatus.FAILED, reason=exc.code)
            _finalize_terminal(db, call)
            return

    watchdog_check.apply_async(
        args=(call_id,),
        countdown=(dial_info["max_duration_seconds"] + 180),
        queue="calls",
    )


@celery_app.task(name="app.tasks.call_tasks.watchdog_check")
def watchdog_check(call_id: str) -> None:
    """Süresi aşılan tekil çağrıyı zorla kapatır."""
    call_id_var.set(call_id)
    with session_scope() as db:
        call = db.get(Call, uuid.UUID(call_id))
        if call is None or CallStatus(call.status) not in ACTIVE_CALL_STATUSES:
            return
        _force_close(db, call, reason="watchdog_timeout")


@celery_app.task(name="app.tasks.call_tasks.watchdog_sweep")
def watchdog_sweep() -> None:
    """Emniyet süpürmesi: kuyrukta/aktif durumda takılı kalan çağrılar."""
    settings = get_settings()
    stale_before = datetime.now(UTC) - timedelta(
        seconds=settings.MAX_CALL_DURATION_SECONDS + 600
    )
    with session_scope() as db:
        stale_calls = db.scalars(
            select(Call).where(
                Call.status.in_([s.value for s in ACTIVE_CALL_STATUSES]),
                Call.created_at < stale_before,
            )
        ).all()
        for call in stale_calls:
            call_id_var.set(str(call.id))
            _force_close(db, call, reason="stale_sweep")


def _force_close(db: Session, call: Call, *, reason: str) -> None:
    provider = get_telephony_provider(call.telephony_provider)
    if call.livekit_room_name:
        try:
            asyncio.run(provider.hangup_call(call.livekit_room_name))
        except TelephonyError:
            logger.warning("Watchdog hangup başarısız (oda zaten kapalı olabilir)")
    call.error_code = call.error_code or reason
    try:
        transition(db, call, CallStatus.FAILED, reason=reason)
    except Exception:
        call.status = CallStatus.FAILED.value
        call.ended_at = datetime.now(UTC)
        record_event(db, call, "status:failed", {"reason": reason, "forced": True})
    _finalize_terminal(db, call)


def _finalize_terminal(db: Session, call: Call) -> None:
    """Terminal çağrı için: fallback outcome + lead/kampanya güncellemesi."""
    if call.outcome is None:
        fallback = derive_fallback_outcome(db, call)
        finalize_outcome(db, call, outcome=fallback)
        record_event(db, call, "outcome_fallback", {"outcome": fallback.value})
    handle_call_terminal(db, call)
    if call.campaign_id is not None:
        maybe_complete_campaign(db, call.campaign_id)


@celery_app.task(name="app.tasks.call_tasks.process_terminal_call")
def process_terminal_call(call_id: str) -> None:
    """Internal API, agent 'session ended' bildirdiğinde bu görevi tetikler."""
    call_id_var.set(call_id)
    with session_scope() as db:
        call = db.get(Call, uuid.UUID(call_id))
        if call is None:
            return
        if CallStatus(call.status) in ACTIVE_CALL_STATUSES:
            # Agent oturumu bitti ama telephony durumu terminal değilse tamamla
            try:
                transition(db, call, CallStatus.COMPLETED)
            except Exception:
                call.status = CallStatus.COMPLETED.value
                call.ended_at = datetime.now(UTC)
        _finalize_terminal(db, call)


@celery_app.task(name="app.tasks.call_tasks.hangup_call")
def hangup_call_task(call_id: str, requested_by: str | None = None) -> None:
    """Panelden 'aramayı sonlandır' isteği."""
    call_id_var.set(call_id)
    with session_scope() as db:
        call = db.get(Call, uuid.UUID(call_id))
        if call is None or CallStatus(call.status) not in ACTIVE_CALL_STATUSES:
            return
        record_event(db, call, "hangup_requested", {"by": requested_by})
        _force_close(db, call, reason="user_hangup")
