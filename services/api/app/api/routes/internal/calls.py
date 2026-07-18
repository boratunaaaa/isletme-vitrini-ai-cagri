from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.internal.common import (
    InternalAPIError,
    ensure_not_terminal,
    error_response,
    get_call_or_error,
)
from app.config import get_settings
from app.core.crypto import decrypt_pii
from app.deps import InternalServiceContext, get_db, require_internal_service
from app.models.call import CallEvent, CallUsage
from app.models.campaign import Campaign
from app.models.content import AgentPromptVersion, KnowledgeBaseEntry
from app.models.enums import (
    CallStatus,
    UsageSource,
)
from app.models.internal import CallTranscriptTurn
from app.models.lead import Lead
from app.schemas.internal.voice_agent import (
    AgentConfiguration,
    AgentEventType,
    BootstrapCampaign,
    BootstrapLead,
    BootstrapResponse,
    CompletionIn,
    DialPlanResponse,
    GenericAcceptedResponse,
    InternalErrorCode,
    KnowledgeBaseItem,
    LifecycleEventIn,
    PolicyContext,
    TelephonyContext,
    TranscriptTurnIn,
    UsageResponse,
    UsageSourceIn,
    UsageUpdateIn,
)
from app.services import call_policy
from app.services.call_policy import CallPolicyError
from app.services.call_service import (
    InvalidTransition,
    derive_fallback_outcome,
    finalize_outcome,
    transition,
)
from app.services.campaign_service import handle_call_terminal, maybe_complete_campaign
from app.services.cost_service import UsageTokens, compute_ai_cost, get_active_pricing
from app.services.event_bus import publish_event
from app.services.internal_contract import (
    IdempotencyConflict,
    idempotent,
    redact_text,
    sanitize_payload,
)
from app.services.suppression_service import is_suppressed

router = APIRouter(prefix="/calls")

_DIALABLE_STATUSES = {CallStatus.QUEUED.value, CallStatus.PREPARING.value, CallStatus.DIALING.value}
_EVENT_TRANSITIONS = {
    AgentEventType.DIALING: CallStatus.DIALING,
    AgentEventType.RINGING: CallStatus.RINGING,
    AgentEventType.ANSWERED: CallStatus.ANSWERED,
    AgentEventType.AGENT_SESSION_STARTED: CallStatus.AGENT_ACTIVE,
}

# voice-agent'ın RFC 3261 tabanlı SIP sınıflandırması (bkz.
# services/voice-agent/agent/errors.py::classify_sip_status) -> backend
# terminal call status'u. Yalnız `disconnect_reason == "sip_failure"` iken
# kullanılır. Burada karşılığı olmayan nedenler (authentication_error,
# trunk_error, redirect_unsupported, unknown_sip_failure) kasıtlı olarak
# eşlenmez — bunlar müşteri/numara kaynaklı değil altyapı kaynaklı
# hatalardır ve mevcut `FAILED` fallback'i zaten doğru kategoridir.
_SIP_REASON_TO_STATUS: dict[str, CallStatus] = {
    "busy": CallStatus.BUSY,
    "no_answer": CallStatus.NO_ANSWER,
    "timeout": CallStatus.NO_ANSWER,  # yanıt hiç gelmedi — no_answer ile aynı aile
    "rejected": CallStatus.REJECTED,
    "cancelled": CallStatus.CANCELLED,
}

_PRE_TERMINAL_STATUSES = frozenset(
    s.value
    for s in (
        CallStatus.COMPLETED,
        CallStatus.FAILED,
        CallStatus.CANCELLED,
        CallStatus.BUSY,
        CallStatus.NO_ANSWER,
        CallStatus.REJECTED,
        CallStatus.VOICEMAIL,
    )
)


def _target_status_for_completion(payload: CompletionIn) -> CallStatus:
    if payload.disconnect_reason == "sip_failure" and payload.sip_reason:
        mapped = _SIP_REASON_TO_STATUS.get(payload.sip_reason)
        if mapped is not None:
            return mapped
    return CallStatus.COMPLETED


def _safe_error(exc: InternalAPIError, ctx: InternalServiceContext) -> JSONResponse:
    return error_response(exc, ctx.request_id)


def _lead_or_error(db: Session, lead_id: uuid.UUID) -> Lead:
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise InternalAPIError(InternalErrorCode.LEAD_NOT_FOUND, "Lead not found.", 404)
    return lead


def _campaign(db: Session, campaign_id: uuid.UUID | None) -> Campaign | None:
    return db.get(Campaign, campaign_id) if campaign_id else None


def _prompt_or_error(
    db: Session,
    call: Any,
    campaign: Campaign | None,
) -> AgentPromptVersion:
    prompt_id = call.agent_prompt_version_id or (
        campaign.agent_prompt_version_id if campaign else None
    )
    prompt = db.get(AgentPromptVersion, prompt_id) if prompt_id else None
    if prompt is None:
        prompt = db.scalars(
            select(AgentPromptVersion).where(AgentPromptVersion.is_active.is_(True)).limit(1)
        ).first()
    if prompt is None:
        raise InternalAPIError(
            InternalErrorCode.PROMPT_NOT_CONFIGURED,
            "Active prompt is not configured.",
            409,
        )
    return prompt


def _knowledge_base(db: Session, limit: int = 20) -> list[KnowledgeBaseItem]:
    entries = db.scalars(
        select(KnowledgeBaseEntry)
        .where(KnowledgeBaseEntry.is_active.is_(True))
        .order_by(KnowledgeBaseEntry.category, KnowledgeBaseEntry.title)
        .limit(limit)
    ).all()
    return [
        KnowledgeBaseItem(category=e.category, title=e.title, content=e.content) for e in entries
    ]


def _telephony() -> TelephonyContext:
    settings = get_settings()
    return TelephonyContext(
        outbound_trunk_id=settings.LIVEKIT_SIP_OUTBOUND_TRUNK_ID,
        caller_id=settings.NETGSM_OUTBOUND_NUMBER or None,
        sip_transport=settings.NETGSM_TRANSPORT,
        codec_preferences=[
            c.strip() for c in settings.NETGSM_CODEC_PREFERENCES.split(",") if c.strip()
        ],
    )


def _policy() -> PolicyContext:
    settings = get_settings()
    return PolicyContext(
        recording_enabled=settings.CALL_RECORDING_ENABLED,
        transcript_storage_enabled=settings.TRANSCRIPT_STORAGE_ENABLED,
        human_transfer_enabled=settings.HUMAN_TRANSFER_ENABLED,
    )


def _bootstrap_payload(db: Session, call_id: uuid.UUID) -> BootstrapResponse:
    call = get_call_or_error(db, call_id)
    ensure_not_terminal(call)
    if call.phone_hash and is_suppressed(db, call.phone_hash):
        raise InternalAPIError(InternalErrorCode.SUPPRESSED_PHONE, "Phone is suppressed.", 403)
    lead = _lead_or_error(db, call.lead_id)
    campaign = _campaign(db, call.campaign_id)
    prompt = _prompt_or_error(db, call, campaign)
    phone = decrypt_pii(lead.phone_ciphertext or "")
    max_duration = (
        campaign.max_call_duration_seconds if campaign else get_settings().MAX_CALL_DURATION_SECONDS
    )
    return BootstrapResponse(
        call_id=call.id,
        lead=BootstrapLead(
            business_name=lead.business_name,
            sector=lead.sector,
            city=lead.city,
            district=lead.district,
            website=lead.website,
            phone_e164=phone,
            phone_last_four=lead.phone_last_four,
        ),
        campaign=BootstrapCampaign(
            campaign_id=campaign.id if campaign else None,
            name=campaign.name if campaign else None,
            conversation_engine=call.conversation_provider,
            model=call.model,
            voice=call.voice,
            max_call_duration_seconds=max_duration,
        ),
        agent_configuration=AgentConfiguration(
            prompt_version_id=prompt.id,
            system_prompt=prompt.system_prompt,
            opening_script=prompt.opening_script,
            objective=prompt.objective,
            objection_rules=prompt.objection_rules,
            tool_policy={"free_sql": False, "controlled_tools_only": True},
        ),
        knowledge_base=_knowledge_base(db),
        telephony=_telephony(),
        policy=_policy(),
    )


@router.get("/{call_id}/bootstrap", response_model=BootstrapResponse, include_in_schema=False)
def bootstrap_call(
    call_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    ctx: InternalServiceContext = Depends(require_internal_service),
) -> BootstrapResponse | JSONResponse:
    try:
        response = _bootstrap_payload(db, call_id)
        db.add(
            CallEvent(
                call_id=call_id,
                event_type="internal.bootstrap",
                safe_payload={"service": ctx.service_name},
                event_timestamp=datetime.now(UTC),
            )
        )
        return response
    except InternalAPIError as exc:
        return _safe_error(exc, ctx)


@router.get("/{call_id}/dial-plan", response_model=DialPlanResponse, include_in_schema=False)
def dial_plan(
    call_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: InternalServiceContext = Depends(require_internal_service),
) -> DialPlanResponse | JSONResponse:
    try:
        call = get_call_or_error(db, call_id)
        if call.status not in _DIALABLE_STATUSES:
            raise InternalAPIError(
                InternalErrorCode.CALL_NOT_DIALABLE, "Call is not dialable.", 409
            )
        if call.phone_hash and is_suppressed(db, call.phone_hash):
            raise InternalAPIError(InternalErrorCode.SUPPRESSED_PHONE, "Phone is suppressed.", 403)
        lead = _lead_or_error(db, call.lead_id)
        phone = decrypt_pii(lead.phone_ciphertext or "")
        try:
            call_policy.check_global_gates(phone)
        except CallPolicyError as err:
            raise InternalAPIError(InternalErrorCode.CALL_NOT_DIALABLE, err.code, 409) from err
        settings = get_settings()
        campaign = _campaign(db, call.campaign_id)
        max_duration = (
            campaign.max_call_duration_seconds if campaign else settings.MAX_CALL_DURATION_SECONDS
        )
        room_name = call.livekit_room_name or f"call-{call.id}"
        call.livekit_room_name = room_name
        db.add(
            CallEvent(
                call_id=call.id,
                event_type="internal.dial_plan",
                safe_payload={"service": ctx.service_name},
                event_timestamp=datetime.now(UTC),
            )
        )
        return DialPlanResponse(
            call_id=call.id,
            phone_e164=phone,
            sip_trunk_id=settings.LIVEKIT_SIP_OUTBOUND_TRUNK_ID,
            caller_id=settings.NETGSM_OUTBOUND_NUMBER or None,
            room_name=room_name,
            participant_identity=f"phone-{call.id}",
            participant_name=lead.business_name[:80],
            max_call_duration_seconds=max_duration,
        )
    except InternalAPIError as exc:
        return _safe_error(exc, ctx)


@router.post("/{call_id}/events", response_model=GenericAcceptedResponse, include_in_schema=False)
def ingest_event(
    call_id: uuid.UUID,
    payload: LifecycleEventIn,
    db: Session = Depends(get_db),
    ctx: InternalServiceContext = Depends(require_internal_service),
) -> GenericAcceptedResponse | JSONResponse:
    try:
        call = get_call_or_error(db, call_id)

        def handle() -> dict[str, Any]:
            safe_payload = sanitize_payload(payload.payload)
            target = _EVENT_TRANSITIONS.get(payload.event_type)
            if target is not None:
                try:
                    transition(
                        db, call, target, payload={"sequence": payload.sequence}, reason=None
                    )
                except InvalidTransition as exc:
                    raise InternalAPIError(
                        InternalErrorCode.INVALID_STATE_TRANSITION, str(exc), 409
                    ) from exc
            db.add(
                CallEvent(
                    call_id=call.id,
                    event_type=payload.event_type.value,
                    safe_payload={"sequence": payload.sequence, "payload": safe_payload},
                    event_timestamp=payload.occurred_at,
                )
            )
            publish_event(
                {
                    "type": "internal_call_event",
                    "call_id": str(call.id),
                    "event_type": payload.event_type.value,
                }
            )
            return {"status": "accepted", "detail": payload.event_type.value}

        result, replay = idempotent(
            db,
            call_id=call_id,
            external_id=payload.event_id,
            event_type=payload.event_type.value,
            payload=payload.model_dump(mode="json"),
            handler=handle,
        )
        return GenericAcceptedResponse(**result, idempotent=replay)
    except IdempotencyConflict:
        return _safe_error(
            InternalAPIError(
                InternalErrorCode.DUPLICATE_EVENT_CONFLICT,
                "Duplicate event id with different payload.",
                409,
            ),
            ctx,
        )
    except InternalAPIError as exc:
        return _safe_error(exc, ctx)


@router.post(
    "/{call_id}/transcript-turns", response_model=GenericAcceptedResponse, include_in_schema=False
)
def transcript_turn(
    call_id: uuid.UUID,
    payload: TranscriptTurnIn,
    db: Session = Depends(get_db),
    ctx: InternalServiceContext = Depends(require_internal_service),
) -> GenericAcceptedResponse | JSONResponse:
    try:
        get_call_or_error(db, call_id)
        settings = get_settings()

        def handle() -> dict[str, Any]:
            if not settings.TRANSCRIPT_STORAGE_ENABLED:
                return {"status": "ignored", "detail": "transcript_storage_disabled"}
            if not payload.is_final:
                return {"status": "ignored", "detail": "partial_turn_not_persisted"}
            redacted = redact_text(payload.text)
            db.add(
                CallTranscriptTurn(
                    call_id=call_id,
                    turn_id=payload.turn_id,
                    speaker=payload.speaker,
                    text_redacted=redacted,
                    started_at=payload.started_at,
                    ended_at=payload.ended_at,
                    is_final=payload.is_final,
                    sequence=payload.sequence,
                )
            )
            return {"status": "stored", "detail": "final_turn"}

        result, replay = idempotent(
            db,
            call_id=call_id,
            external_id=payload.turn_id,
            event_type="transcript_turn",
            payload=payload.model_dump(mode="json"),
            handler=handle,
        )
        return GenericAcceptedResponse(**result, idempotent=replay)
    except IdempotencyConflict:
        return _safe_error(
            InternalAPIError(
                InternalErrorCode.DUPLICATE_EVENT_CONFLICT,
                "Duplicate turn id with different payload.",
                409,
            ),
            ctx,
        )
    except InternalAPIError as exc:
        return _safe_error(exc, ctx)


@router.post("/{call_id}/usage", response_model=UsageResponse, include_in_schema=False)
def usage_update(
    call_id: uuid.UUID,
    payload: UsageUpdateIn,
    db: Session = Depends(get_db),
    ctx: InternalServiceContext = Depends(require_internal_service),
) -> UsageResponse | JSONResponse:
    try:
        call = get_call_or_error(db, call_id)
        if payload.provider != "openai" or payload.model != call.model:
            raise InternalAPIError(
                InternalErrorCode.VALIDATION_ERROR, "Usage model/provider mismatch.", 422
            )
        pricing = get_active_pricing(db, payload.provider, payload.model)
        if pricing is None and payload.usage_source != UsageSourceIn.UNAVAILABLE:
            raise InternalAPIError(
                InternalErrorCode.PRICING_NOT_CONFIGURED, "Pricing is not configured.", 409
            )

        def handle() -> dict[str, Any]:
            source = (
                UsageSource.PROVIDER.value
                if payload.usage_source == UsageSourceIn.PROVIDER_REPORTED
                else UsageSource.ESTIMATED.value
            )
            usage = UsageTokens(
                input_audio_tokens=payload.input_audio_tokens,
                cached_input_audio_tokens=payload.cached_input_audio_tokens,
                output_audio_tokens=payload.output_audio_tokens,
                input_text_tokens=payload.input_text_tokens,
                cached_input_text_tokens=payload.cached_input_text_tokens,
                output_text_tokens=payload.output_text_tokens,
                reasoning_tokens=payload.reasoning_tokens,
            )
            ai_cost = Decimal("0") if pricing is None else compute_ai_cost(usage, pricing)
            row = db.scalars(select(CallUsage).where(CallUsage.call_id == call_id)).first()
            if row is None:
                row = CallUsage(call_id=call_id, provider=payload.provider, model=payload.model)
                db.add(row)
            row.input_audio_tokens = payload.input_audio_tokens
            row.cached_input_audio_tokens = payload.cached_input_audio_tokens
            row.output_audio_tokens = payload.output_audio_tokens
            row.input_text_tokens = payload.input_text_tokens
            row.cached_input_text_tokens = payload.cached_input_text_tokens
            row.output_text_tokens = payload.output_text_tokens
            row.reasoning_tokens = payload.reasoning_tokens
            row.usage_source = source
            row.estimated_ai_cost = ai_cost
            telephony_cost = row.estimated_telephony_cost or Decimal("0")
            row.estimated_total_cost = ai_cost + telephony_cost
            db.add(
                CallEvent(
                    call_id=call_id,
                    event_type="usage_updated",
                    safe_payload={"source": source},
                    event_timestamp=payload.occurred_at,
                )
            )
            return {
                "status": "updated",
                "estimated_ai_cost_usd": str(ai_cost),
                "usage_source": source,
            }

        result, replay = idempotent(
            db,
            call_id=call_id,
            external_id=payload.usage_event_id,
            event_type="usage_updated",
            payload=payload.model_dump(mode="json"),
            handler=handle,
        )
        return UsageResponse(**result, idempotent=replay)
    except IdempotencyConflict:
        return _safe_error(
            InternalAPIError(
                InternalErrorCode.DUPLICATE_EVENT_CONFLICT,
                "Duplicate usage id with different payload.",
                409,
            ),
            ctx,
        )
    except InternalAPIError as exc:
        return _safe_error(exc, ctx)


@router.post("/{call_id}/complete", response_model=GenericAcceptedResponse, include_in_schema=False)
def complete_call(
    call_id: uuid.UUID,
    payload: CompletionIn,
    db: Session = Depends(get_db),
    ctx: InternalServiceContext = Depends(require_internal_service),
) -> GenericAcceptedResponse | JSONResponse:
    try:
        call = get_call_or_error(db, call_id)

        def handle() -> dict[str, Any]:
            if call.status not in _PRE_TERMINAL_STATUSES:
                target_status = _target_status_for_completion(payload)
                try:
                    transition(db, call, target_status, reason=payload.disconnect_reason)
                except InvalidTransition:
                    # Hedef durum (ör. call zaten ANSWERED'ken busy/no_answer
                    # gibi yalnız pre-answer durumlardan ulaşılabilen bir
                    # statüye geçmeye çalışmak) geçersizse güvenli varsayılan:
                    # FAILED. Bu, önceki davranışla birebir aynı fallback'tir.
                    call.status = CallStatus.FAILED.value
                    call.ended_at = payload.ended_at
                    call.disconnect_reason = payload.disconnect_reason
            call.ended_at = payload.ended_at
            call.duration_seconds = payload.duration_seconds
            if call.outcome is None:
                finalize_outcome(db, call, outcome=derive_fallback_outcome(db, call))
            # Lead/campaign_lead etkilerini TEK doğru kaynaktan (retry policy
            # dahil) uygula — önceden burada `link.status` doğrudan ve
            # koşulsuz `COMPLETED` yapılıyordu, bu da busy/no_answer/rejected
            # sonuçlarının kampanya retry zamanlamasına hiç yansımamasına
            # neden oluyordu (CODEX_AUDIT_PHASE_4_FIX.md YÜKSEK-3).
            handle_call_terminal(db, call)
            if call.campaign_id:
                maybe_complete_campaign(db, call.campaign_id)
            db.add(
                CallEvent(
                    call_id=call_id,
                    event_type="call_completed",
                    safe_payload={
                        "reason": payload.disconnect_reason,
                        "sip_reason": payload.sip_reason,
                    },
                    event_timestamp=payload.ended_at,
                )
            )
            publish_event(
                {"type": "call_completed", "call_id": str(call_id), "status": call.status}
            )
            return {"status": "completed", "detail": call.outcome or ""}

        result, replay = idempotent(
            db,
            call_id=call_id,
            external_id=payload.completion_event_id,
            event_type="call_completed",
            payload=payload.model_dump(mode="json"),
            handler=handle,
        )
        return GenericAcceptedResponse(**result, idempotent=replay)
    except IdempotencyConflict:
        return _safe_error(
            InternalAPIError(
                InternalErrorCode.DUPLICATE_EVENT_CONFLICT,
                "Duplicate completion id with different payload.",
                409,
            ),
            ctx,
        )
    except InternalAPIError as exc:
        return _safe_error(exc, ctx)
