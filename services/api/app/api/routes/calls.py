from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.audit import write_audit
from app.core.rbac import Permission
from app.deps import client_ip, get_db, require_permission
from app.models.call import Call, CallEvent, CallQualityMetrics, CallUsage
from app.models.enums import ACTIVE_CALL_STATUSES
from app.models.lead import Lead
from app.models.user import User
from app.providers.conversation import EngineValidationError, validate_selection
from app.schemas.calls import (
    CallDetailOut,
    CallEventOut,
    CallInitiateRequest,
    CallOut,
    CallUsageOut,
    QualityMetricsIn,
)
from app.schemas.common import OkResponse, Page
from app.services.call_policy import CallPolicyError
from app.services.orchestrator import initiate_call

router = APIRouter(prefix="/calls", tags=["calls"])


def _call_out(call: Call, business_name: str | None = None) -> CallOut:
    out = CallOut.model_validate(call)
    out.business_name = business_name
    return out


@router.post("", response_model=CallOut, status_code=status.HTTP_201_CREATED)
def initiate(
    payload: CallInitiateRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(Permission.CALL_INITIATE)),
) -> CallOut:
    lead = db.get(Lead, payload.lead_id)
    if lead is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lead bulunamadı")
    try:
        selection = validate_selection(
            engine=payload.engine,
            model=payload.model,
            voice=payload.voice,
            actor_role=actor.role,
        )
    except EngineValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    try:
        call = initiate_call(
            db,
            lead=lead,
            selection=selection,
            initiated_by=actor.id,
            idempotency_key=payload.idempotency_key,
        )
    except CallPolicyError as exc:
        status_code = (
            status.HTTP_403_FORBIDDEN
            if exc.code in ("live_calls_disabled", "not_in_allowlist", "suppressed")
            else status.HTTP_409_CONFLICT
        )
        raise HTTPException(status_code, exc.message) from exc
    write_audit(
        db,
        action="calls.initiate",
        user_id=actor.id,
        resource_type="call",
        resource_id=str(call.id),
        safe_metadata={"model": selection.model, "lead_id": str(lead.id)},
        ip_address=client_ip(request),
    )
    return _call_out(call, lead.business_name)


@router.get("", response_model=Page[CallOut])
def list_calls(
    page: int = 1,
    page_size: int = 50,
    call_status: str | None = None,
    outcome: str | None = None,
    campaign_id: uuid.UUID | None = None,
    lead_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.LEADS_READ)),
) -> Page[CallOut]:
    page_size = min(max(page_size, 1), 200)
    query = select(Call, Lead.business_name).join(Lead, Lead.id == Call.lead_id)
    if call_status:
        query = query.where(Call.status == call_status)
    if outcome:
        query = query.where(Call.outcome == outcome)
    if campaign_id:
        query = query.where(Call.campaign_id == campaign_id)
    if lead_id:
        query = query.where(Call.lead_id == lead_id)
    total = int(db.scalar(select(func.count()).select_from(query.subquery())) or 0)
    rows = db.execute(
        query.order_by(Call.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return Page(
        items=[_call_out(call, name) for call, name in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/live", response_model=list[CallOut])
def live_calls(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.LEADS_READ)),
) -> list[CallOut]:
    rows = db.execute(
        select(Call, Lead.business_name)
        .join(Lead, Lead.id == Call.lead_id)
        .where(Call.status.in_([s.value for s in ACTIVE_CALL_STATUSES]))
        .order_by(Call.created_at.desc())
    ).all()
    return [_call_out(call, name) for call, name in rows]


@router.get("/{call_id}", response_model=CallDetailOut)
def call_detail(
    call_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.LEADS_READ)),
) -> CallDetailOut:
    call = db.get(Call, call_id)
    if call is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Arama bulunamadı")
    lead = db.get(Lead, call.lead_id)
    events = db.scalars(
        select(CallEvent).where(CallEvent.call_id == call_id).order_by(CallEvent.event_timestamp)
    ).all()
    usage = db.scalars(select(CallUsage).where(CallUsage.call_id == call_id)).first()
    usage_out = None
    if usage is not None:
        usage_out = CallUsageOut(
            provider=usage.provider,
            model=usage.model,
            input_audio_tokens=usage.input_audio_tokens,
            cached_input_audio_tokens=usage.cached_input_audio_tokens,
            output_audio_tokens=usage.output_audio_tokens,
            input_text_tokens=usage.input_text_tokens,
            cached_input_text_tokens=usage.cached_input_text_tokens,
            output_text_tokens=usage.output_text_tokens,
            reasoning_tokens=usage.reasoning_tokens,
            usage_source=usage.usage_source,
            estimated_ai_cost=str(usage.estimated_ai_cost),
            estimated_telephony_cost=str(usage.estimated_telephony_cost),
            estimated_total_cost=str(usage.estimated_total_cost),
            currency=usage.currency,
        )
    return CallDetailOut(
        call=_call_out(call, lead.business_name if lead else None),
        events=[CallEventOut.model_validate(e) for e in events],
        usage=usage_out,
        transcript=call.transcript if get_settings().TRANSCRIPT_STORAGE_ENABLED else None,
    )


@router.post("/{call_id}/hangup", response_model=OkResponse)
def hangup(
    call_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(Permission.CALL_TERMINATE)),
) -> OkResponse:
    call = db.get(Call, call_id)
    if call is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Arama bulunamadı")
    if call.status not in [s.value for s in ACTIVE_CALL_STATUSES]:
        raise HTTPException(status.HTTP_409_CONFLICT, "Arama zaten sonlanmış")
    from app.tasks.call_tasks import hangup_call_task

    hangup_call_task.apply_async(args=(str(call_id), str(actor.id)), queue="calls")
    write_audit(
        db,
        action="calls.hangup",
        user_id=actor.id,
        resource_type="call",
        resource_id=str(call_id),
        ip_address=client_ip(request),
    )
    return OkResponse(detail="Sonlandırma isteği kuyruğa alındı")


@router.post("/{call_id}/quality", response_model=OkResponse)
def rate_quality(
    call_id: uuid.UUID,
    payload: QualityMetricsIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.LEADS_WRITE)),
) -> OkResponse:
    call = db.get(Call, call_id)
    if call is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Arama bulunamadı")
    metrics = db.scalars(
        select(CallQualityMetrics).where(CallQualityMetrics.call_id == call_id)
    ).first()
    if metrics is None:
        metrics = CallQualityMetrics(call_id=call_id)
        db.add(metrics)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(metrics, field, value)
    return OkResponse(detail="Kalite puanları kaydedildi")
