"""Call Orchestrator — tekil arama başlatmanın tek kapısı.

Sıralama (bölüm 15): doğrulama → suppression → limitler → saat → kilit →
idempotent Call kaydı → Celery kuyruğuna dial görevi. SIP tarafı worker +
voice-agent'ta ilerler; bu fonksiyon hiçbir koşulda doğrudan arama yapmaz.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.crypto import decrypt_pii
from app.core.locks import LockBackendUnavailable, LockNotAcquired, redis_lock
from app.models.call import Call
from app.models.campaign import Campaign
from app.models.enums import ACTIVE_CALL_STATUSES, CallStatus, ConversationEngine
from app.models.lead import Lead
from app.providers.conversation import EngineSelection
from app.services import call_policy
from app.services.call_policy import CallPolicyError
from app.services.call_service import record_event
from app.services.prompt_builder import get_active_prompt_version
from app.services.suppression_service import is_suppressed


def _resolve_phone(lead: Lead) -> str:
    if not lead.phone_ciphertext or not lead.phone_hash:
        raise CallPolicyError("no_phone", "Bu lead için kayıtlı telefon numarası yok.")
    return decrypt_pii(lead.phone_ciphertext)


def _active_call_exists(db: Session, lead_id: uuid.UUID) -> bool:
    return (
        db.scalar(
            select(Call.id)
            .where(
                Call.lead_id == lead_id,
                Call.status.in_([s.value for s in ACTIVE_CALL_STATUSES]),
            )
            .limit(1)
        )
        is not None
    )


def initiate_call(
    db: Session,
    *,
    lead: Lead,
    selection: EngineSelection,
    campaign: Campaign | None = None,
    initiated_by: uuid.UUID | None = None,
    idempotency_key: str | None = None,
    enqueue: bool = True,
) -> Call:
    """Call kaydı oluşturur ve dial görevini kuyruğa atar.

    Testler `enqueue=False` ile kuyruk olmadan aynı iş kurallarını doğrular.
    """
    # Idempotency: aynı anahtar daha önce işlendiyse mevcut çağrıyı dön
    if idempotency_key:
        existing = db.scalars(
            select(Call).where(Call.idempotency_key == idempotency_key)
        ).first()
        if existing is not None:
            return existing

    phone_e164 = _resolve_phone(lead)
    try:
        if is_suppressed(db, lead.phone_hash or ""):
            raise CallPolicyError("suppressed", "Numara engelleme listesinde; aranamaz.")

        call_policy.check_global_gates(phone_e164)
        call_policy.check_call_hours(campaign)
        call_policy.check_limits(db, campaign)

        try:
            with redis_lock(f"lead-call:{lead.id}", ttl_seconds=30):
                if _active_call_exists(db, lead.id):
                    raise CallPolicyError(
                        "call_in_progress", "Bu lead için zaten aktif bir arama var."
                    )
                prompt_version_id: uuid.UUID | None = None
                if campaign is not None and campaign.agent_prompt_version_id is not None:
                    prompt_version_id = campaign.agent_prompt_version_id
                else:
                    prompt_version_id = get_active_prompt_version(db).id

                call = Call(
                    lead_id=lead.id,
                    campaign_id=campaign.id if campaign else None,
                    initiated_by=initiated_by,
                    idempotency_key=idempotency_key,
                    telephony_provider=(
                        "test"
                        if selection.engine == ConversationEngine.TEST.value
                        else "livekit_netgsm"
                    ),
                    conversation_provider=selection.engine,
                    model=selection.model,
                    voice=selection.voice,
                    agent_prompt_version_id=prompt_version_id,
                    status=CallStatus.QUEUED.value,
                    phone_hash=lead.phone_hash,
                    phone_last_four=lead.phone_last_four,
                )
                db.add(call)
                db.flush()
                call.livekit_room_name = f"call-{call.id}"
                record_event(
                    db,
                    call,
                    "queued",
                    {"model": selection.model, "engine": selection.engine},
                )
        except LockNotAcquired as exc:
            raise CallPolicyError(
                "lead_locked", "Bu lead için eşzamanlı arama denemesi engellendi."
            ) from exc
        except LockBackendUnavailable as exc:
            raise CallPolicyError(
                "lock_backend_unavailable",
                "Arama başlatma şu anda geçici olarak kullanılamıyor; lütfen tekrar deneyin.",
            ) from exc
    finally:
        # Düz metin numara yalnız doğrulama için çözüldü; referansı bırak
        del phone_e164

    if enqueue:
        from app.tasks.call_tasks import place_call  # döngüsel importu önlemek için lokal

        place_call.apply_async(args=(str(call.id),), queue="calls")
    return call


def build_dial_info(db: Session, call: Call) -> dict[str, Any]:
    """Voice agent'ın internal endpoint'ten aldığı dial paketi.

    Telefon numarası yalnız bu cevapta yer alır; loglanmaz, event'e yazılmaz.
    """
    s = get_settings()
    lead = db.get(Lead, call.lead_id)
    if lead is None:
        raise CallPolicyError("lead_missing", "Lead bulunamadı")
    campaign = db.get(Campaign, call.campaign_id) if call.campaign_id else None
    max_duration = (
        campaign.max_call_duration_seconds if campaign else s.MAX_CALL_DURATION_SECONDS
    )
    return {
        "call_id": str(call.id),
        "room_name": call.livekit_room_name,
        "phone_e164": _resolve_phone(lead),
        "sip_trunk_id": s.LIVEKIT_SIP_OUTBOUND_TRUNK_ID,
        "engine": call.conversation_provider,
        "model": call.model,
        "voice": call.voice,
        "reasoning_effort": s.OPENAI_REALTIME_REASONING_EFFORT,
        "max_duration_seconds": max_duration,
        "transcript_enabled": s.TRANSCRIPT_STORAGE_ENABLED,
        "human_transfer_enabled": s.HUMAN_TRANSFER_ENABLED,
        "human_transfer_number_configured": bool(s.HUMAN_TRANSFER_NUMBER),
    }
