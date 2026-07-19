"""Kampanya motoru: durum yönetimi, kuyruk seçimi, terminal çağrı işleme."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.call import Call
from app.models.campaign import Campaign, CampaignLead
from app.models.enums import (
    CallOutcome,
    CallStatus,
    CampaignLeadStatus,
    CampaignStatus,
    LeadStatus,
)
from app.models.lead import Lead
from app.services.call_policy import compute_next_retry

logger = logging.getLogger(__name__)

VALID_CAMPAIGN_TRANSITIONS: dict[str, frozenset[str]] = {
    CampaignStatus.DRAFT.value: frozenset(
        {CampaignStatus.READY.value, CampaignStatus.CANCELLED.value}
    ),
    CampaignStatus.READY.value: frozenset(
        {
            CampaignStatus.RUNNING.value,
            CampaignStatus.DRAFT.value,
            CampaignStatus.CANCELLED.value,
        }
    ),
    CampaignStatus.RUNNING.value: frozenset(
        {
            CampaignStatus.PAUSED.value,
            CampaignStatus.COMPLETED.value,
            CampaignStatus.CANCELLED.value,
        }
    ),
    CampaignStatus.PAUSED.value: frozenset(
        {
            CampaignStatus.RUNNING.value,
            CampaignStatus.CANCELLED.value,
            CampaignStatus.COMPLETED.value,
        }
    ),
}


class CampaignError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def transition_campaign(campaign: Campaign, new_status: str) -> Campaign:
    allowed = VALID_CAMPAIGN_TRANSITIONS.get(campaign.status, frozenset())
    if new_status not in allowed:
        raise CampaignError(
            "invalid_transition", f"Kampanya {campaign.status} → {new_status} geçişi geçersiz."
        )
    campaign.status = new_status
    return campaign


def pick_due_campaign_leads(db: Session, campaign: Campaign, limit: int) -> list[CampaignLead]:
    """Sıradaki aranabilir kampanya lead'leri (retry zamanı gelmiş olanlar dahil)."""
    now = datetime.now(UTC)
    rows = db.scalars(
        select(CampaignLead)
        .join(Lead, Lead.id == CampaignLead.lead_id)
        .where(
            CampaignLead.campaign_id == campaign.id,
            CampaignLead.status.in_(
                [CampaignLeadStatus.PENDING.value, CampaignLeadStatus.RETRY_SCHEDULED.value]
            ),
            (CampaignLead.next_attempt_at.is_(None)) | (CampaignLead.next_attempt_at <= now),
            Lead.phone_hash.is_not(None),
        )
        .order_by(CampaignLead.next_attempt_at.asc().nullsfirst(), CampaignLead.created_at.asc())
        .limit(limit)
    ).all()
    return list(rows)


_OUTCOME_TO_LEAD_STATUS: dict[str, str] = {
    CallOutcome.INTERESTED.value: LeadStatus.INTERESTED.value,
    CallOutcome.DEMO_REQUESTED.value: LeadStatus.DEMO_REQUESTED.value,
    CallOutcome.CALLBACK_REQUESTED.value: LeadStatus.CALLBACK_SCHEDULED.value,
    CallOutcome.NOT_INTERESTED.value: LeadStatus.NOT_INTERESTED.value,
    CallOutcome.DO_NOT_CALL.value: LeadStatus.DO_NOT_CALL.value,
    CallOutcome.WRONG_NUMBER.value: LeadStatus.WRONG_NUMBER.value,
    CallOutcome.BUSINESS_CLOSED.value: LeadStatus.CLOSED_LOST.value,
    CallOutcome.TRANSFERRED_TO_HUMAN.value: LeadStatus.INTERESTED.value,
}


def handle_call_terminal(db: Session, call: Call) -> None:
    """Terminal duruma ulaşan çağrının lead + campaign_lead etkileri.

    Idempotent: campaign_lead CALLING durumunda değilse ikinci kez işlemez.
    """
    lead = db.get(Lead, call.lead_id)
    if lead is not None:
        lead.last_contacted_at = datetime.now(UTC)
        if call.outcome and call.outcome in _OUTCOME_TO_LEAD_STATUS:
            lead.status = _OUTCOME_TO_LEAD_STATUS[call.outcome]
        elif lead.status == LeadStatus.NEW.value:
            lead.status = LeadStatus.CONTACTED.value
        if call.callback_at is not None:
            lead.next_action_at = call.callback_at

    if call.campaign_id is None:
        return
    campaign = db.get(Campaign, call.campaign_id)
    campaign_lead = db.scalars(
        select(CampaignLead).where(
            CampaignLead.campaign_id == call.campaign_id,
            CampaignLead.lead_id == call.lead_id,
        )
    ).first()
    if campaign is None or campaign_lead is None:
        return
    if campaign_lead.status != CampaignLeadStatus.CALLING.value:
        return  # zaten işlenmiş (duplicate event koruması)

    campaign_lead.attempt_count += 1
    if call.outcome == CallOutcome.DO_NOT_CALL.value:
        campaign_lead.status = CampaignLeadStatus.SUPPRESSED.value
        campaign_lead.final_outcome = call.outcome
        return

    next_attempt = compute_next_retry(
        call_status=call.status,
        outcome=call.outcome,
        attempt_count=campaign_lead.attempt_count,
        max_retry_count=campaign.max_retry_count,
        retry_delay_minutes=campaign.retry_delay_minutes,
        callback_at=call.callback_at,
    )
    if next_attempt is not None:
        campaign_lead.status = CampaignLeadStatus.RETRY_SCHEDULED.value
        campaign_lead.next_attempt_at = next_attempt
    else:
        exhausted = call.outcome is None and CallStatus(call.status) in (
            CallStatus.NO_ANSWER,
            CallStatus.BUSY,
            CallStatus.VOICEMAIL,
            CallStatus.FAILED,
        )
        campaign_lead.status = (
            CampaignLeadStatus.EXHAUSTED.value if exhausted else CampaignLeadStatus.COMPLETED.value
        )
        campaign_lead.final_outcome = call.outcome or call.status


def maybe_complete_campaign(db: Session, campaign_id: uuid.UUID) -> None:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None or campaign.status != CampaignStatus.RUNNING.value:
        return
    remaining = db.scalar(
        select(CampaignLead.id)
        .where(
            CampaignLead.campaign_id == campaign_id,
            CampaignLead.status.in_(
                [
                    CampaignLeadStatus.PENDING.value,
                    CampaignLeadStatus.RETRY_SCHEDULED.value,
                    CampaignLeadStatus.CALLING.value,
                    CampaignLeadStatus.SCHEDULED.value,
                ]
            ),
        )
        .limit(1)
    )
    if remaining is None:
        campaign.status = CampaignStatus.COMPLETED.value
