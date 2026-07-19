from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import write_audit
from app.core.rbac import Permission
from app.deps import client_ip, get_db, require_permission
from app.models.call import Call, CallUsage
from app.models.campaign import Campaign, CampaignLead
from app.models.enums import CampaignLeadStatus, CampaignStatus, LeadStatus
from app.models.lead import Lead
from app.models.user import User
from app.providers.conversation import EngineValidationError, validate_selection
from app.schemas.campaigns import (
    CampaignCreate,
    CampaignLeadsAdd,
    CampaignOut,
    CampaignStats,
    CampaignStatusChange,
    CampaignUpdate,
)
from app.schemas.common import OkResponse, Page
from app.services.call_policy import daily_call_count
from app.services.campaign_service import CampaignError, transition_campaign

router = APIRouter(prefix="/campaigns", tags=["campaigns"])

_ACTION_TO_STATUS = {
    "ready": CampaignStatus.READY.value,
    "start": CampaignStatus.RUNNING.value,
    "resume": CampaignStatus.RUNNING.value,
    "pause": CampaignStatus.PAUSED.value,
    "stop": CampaignStatus.COMPLETED.value,
    "cancel": CampaignStatus.CANCELLED.value,
    "draft": CampaignStatus.DRAFT.value,
}


@router.get("", response_model=Page[CampaignOut])
def list_campaigns(
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.CAMPAIGN_READ)),
) -> Page[CampaignOut]:
    total = int(db.scalar(select(func.count(Campaign.id))) or 0)
    campaigns = db.scalars(
        select(Campaign)
        .order_by(Campaign.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Page(
        items=[CampaignOut.model_validate(c) for c in campaigns],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=CampaignOut, status_code=status.HTTP_201_CREATED)
def create_campaign(
    payload: CampaignCreate,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(Permission.CAMPAIGN_WRITE)),
) -> CampaignOut:
    try:
        selection = validate_selection(
            engine=payload.conversation_engine,
            model=payload.realtime_model,
            voice=payload.realtime_voice,
            actor_role=actor.role,
        )
    except EngineValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    campaign = Campaign(
        **payload.model_dump(exclude={"conversation_engine", "realtime_model", "realtime_voice"}),
        conversation_engine=selection.engine,
        realtime_model=selection.model,
        realtime_voice=selection.voice,
        created_by=actor.id,
    )
    db.add(campaign)
    db.flush()
    write_audit(
        db,
        action="campaigns.create",
        user_id=actor.id,
        resource_type="campaign",
        resource_id=str(campaign.id),
        safe_metadata={"model": selection.model},
        ip_address=client_ip(request),
    )
    return CampaignOut.model_validate(campaign)


def _get_campaign(db: Session, campaign_id: uuid.UUID) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kampanya bulunamadı")
    return campaign


@router.get("/{campaign_id}", response_model=CampaignOut)
def get_campaign(
    campaign_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.CAMPAIGN_READ)),
) -> CampaignOut:
    return CampaignOut.model_validate(_get_campaign(db, campaign_id))


@router.patch("/{campaign_id}", response_model=CampaignOut)
def update_campaign(
    campaign_id: uuid.UUID,
    payload: CampaignUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(Permission.CAMPAIGN_WRITE)),
) -> CampaignOut:
    campaign = _get_campaign(db, campaign_id)
    if campaign.status == CampaignStatus.RUNNING.value:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Koşan kampanya düzenlenemez; önce duraklatın."
        )
    data = payload.model_dump(exclude_unset=True)
    if "realtime_model" in data or "realtime_voice" in data:
        try:
            selection = validate_selection(
                engine=campaign.conversation_engine,
                model=data.get("realtime_model", campaign.realtime_model),
                voice=data.get("realtime_voice", campaign.realtime_voice),
                actor_role=actor.role,
            )
        except EngineValidationError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
        data["realtime_model"] = selection.model
        data["realtime_voice"] = selection.voice
    for field, value in data.items():
        setattr(campaign, field, value)
    if campaign.call_end_hour <= campaign.call_start_hour:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Saat aralığı geçersiz")
    return CampaignOut.model_validate(campaign)


@router.post("/{campaign_id}/leads", response_model=OkResponse)
def add_leads(
    campaign_id: uuid.UUID,
    payload: CampaignLeadsAdd,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.CAMPAIGN_WRITE)),
) -> OkResponse:
    campaign = _get_campaign(db, campaign_id)
    if campaign.status in (CampaignStatus.COMPLETED.value, CampaignStatus.CANCELLED.value):
        raise HTTPException(status.HTTP_409_CONFLICT, "Kapalı kampanyaya lead eklenemez")

    if payload.lead_ids:
        lead_ids = payload.lead_ids
    else:
        query = select(Lead.id).where(Lead.phone_hash.is_not(None))
        if payload.sector:
            query = query.where(Lead.sector == payload.sector)
        if payload.city:
            query = query.where(Lead.city == payload.city)
        if payload.district:
            query = query.where(Lead.district == payload.district)
        query = query.where(
            Lead.status.in_([payload.status] if payload.status else [LeadStatus.NEW.value])
        )
        lead_ids = list(db.scalars(query.limit(payload.limit)).all())

    existing = set(
        db.scalars(
            select(CampaignLead.lead_id).where(CampaignLead.campaign_id == campaign_id)
        ).all()
    )
    added = 0
    for lead_id in lead_ids:
        if lead_id in existing:
            continue
        db.add(CampaignLead(campaign_id=campaign_id, lead_id=lead_id))
        added += 1
    return OkResponse(detail=f"{added} lead kampanyaya eklendi")


@router.post("/{campaign_id}/status", response_model=CampaignOut)
def change_status(
    campaign_id: uuid.UUID,
    payload: CampaignStatusChange,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(Permission.CAMPAIGN_CONTROL)),
) -> CampaignOut:
    campaign = _get_campaign(db, campaign_id)
    target = _ACTION_TO_STATUS[payload.action]
    if payload.action in ("start", "resume"):
        lead_count = int(
            db.scalar(
                select(func.count(CampaignLead.id)).where(CampaignLead.campaign_id == campaign_id)
            )
            or 0
        )
        if lead_count == 0:
            raise HTTPException(status.HTTP_409_CONFLICT, "Kampanyada hiç lead yok")
    try:
        transition_campaign(campaign, target)
    except CampaignError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, exc.message) from exc
    write_audit(
        db,
        action=f"campaigns.{payload.action}",
        user_id=actor.id,
        resource_type="campaign",
        resource_id=str(campaign.id),
        ip_address=client_ip(request),
    )
    return CampaignOut.model_validate(campaign)


@router.get("/{campaign_id}/stats", response_model=CampaignStats)
def campaign_stats(
    campaign_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.CAMPAIGN_READ)),
) -> CampaignStats:
    _get_campaign(db, campaign_id)
    status_counts: dict[str, int] = {
        status: count
        for status, count in db.execute(
            select(CampaignLead.status, func.count(CampaignLead.id))
            .where(CampaignLead.campaign_id == campaign_id)
            .group_by(CampaignLead.status)
        ).all()
    }
    outcome_counts: dict[str, int] = {
        outcome: count
        for outcome, count in db.execute(
            select(Call.outcome, func.count(Call.id))
            .where(Call.campaign_id == campaign_id, Call.outcome.is_not(None))
            .group_by(Call.outcome)
        ).all()
        if outcome is not None
    }
    total_cost = db.scalar(
        select(func.coalesce(func.sum(CallUsage.estimated_total_cost), 0))
        .select_from(CallUsage)
        .join(Call, Call.id == CallUsage.call_id)
        .where(Call.campaign_id == campaign_id)
    ) or Decimal("0")
    return CampaignStats(
        total_leads=sum(status_counts.values()),
        pending=status_counts.get(CampaignLeadStatus.PENDING.value, 0),
        calling=status_counts.get(CampaignLeadStatus.CALLING.value, 0),
        retry_scheduled=status_counts.get(CampaignLeadStatus.RETRY_SCHEDULED.value, 0),
        completed=status_counts.get(CampaignLeadStatus.COMPLETED.value, 0),
        suppressed=status_counts.get(CampaignLeadStatus.SUPPRESSED.value, 0),
        exhausted=status_counts.get(CampaignLeadStatus.EXHAUSTED.value, 0),
        calls_today=daily_call_count(db, campaign_id),
        outcomes={k: v for k, v in outcome_counts.items() if k},
        total_cost_usd=str(total_cost),
    )
