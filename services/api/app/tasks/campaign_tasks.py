"""Kampanya görevleri: dakikalık tick + callback hatırlatmaları."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import session_scope
from app.models.campaign import Campaign
from app.models.enums import CallbackStatus, CampaignLeadStatus, CampaignStatus
from app.models.lead import Lead
from app.models.ops import Callback
from app.providers.base import NotificationMessage
from app.providers.conversation import EngineValidationError, validate_selection
from app.providers.notification import InAppNotificationProvider
from app.services import call_policy
from app.services.call_policy import CallPolicyError
from app.services.campaign_service import maybe_complete_campaign, pick_due_campaign_leads
from app.services.orchestrator import initiate_call
from app.worker import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.campaign_tasks.campaign_tick")
def campaign_tick() -> None:
    """Her dakika: koşan kampanyalar için sıradaki aramaları başlat.

    Tüm kapılar (CAMPAIGNS_ENABLED, LIVE_CALLS_ENABLED, saat, limitler,
    suppression, allowlist) orchestrator + policy katmanında zorlanır.
    """
    settings = get_settings()
    if not settings.CAMPAIGNS_ENABLED or not settings.LIVE_CALLS_ENABLED:
        return

    with session_scope() as db:
        campaigns = db.scalars(
            select(Campaign).where(Campaign.status == CampaignStatus.RUNNING.value)
        ).all()
        for campaign in campaigns:
            _tick_campaign(db, campaign)


def _tick_campaign(db: Session, campaign: Campaign) -> None:
    if not call_policy.is_within_call_hours(campaign.call_start_hour, campaign.call_end_hour):
        return
    settings = get_settings()
    remaining_daily = min(
        campaign.daily_limit - call_policy.daily_call_count(db, campaign.id),
        settings.MAX_DAILY_CALLS - call_policy.daily_call_count(db),
    )
    remaining_concurrent = min(
        campaign.concurrent_call_limit - call_policy.concurrent_call_count(db, campaign.id),
        settings.MAX_CONCURRENT_CALLS - call_policy.concurrent_call_count(db),
    )
    slots = max(min(remaining_daily, remaining_concurrent), 0)
    if slots == 0:
        maybe_complete_campaign(db, campaign.id)
        return

    try:
        selection = validate_selection(
            engine=campaign.conversation_engine,
            model=campaign.realtime_model,
            voice=campaign.realtime_voice,
            actor_role="owner",  # kampanya oluşturulurken rol kontrolü yapıldı
            allow_test_engine=True,
        )
    except EngineValidationError as exc:
        logger.error("Kampanya %s motor doğrulaması başarısız: %s", campaign.id, exc)
        return

    for campaign_lead in pick_due_campaign_leads(db, campaign, slots):
        lead = db.get(Lead, campaign_lead.lead_id)
        if lead is None:
            campaign_lead.status = CampaignLeadStatus.SKIPPED.value
            continue
        try:
            initiate_call(
                db,
                lead=lead,
                selection=selection,
                campaign=campaign,
                idempotency_key=f"camp:{campaign.id}:{lead.id}:att{campaign_lead.attempt_count}",
            )
            campaign_lead.status = CampaignLeadStatus.CALLING.value
        except CallPolicyError as exc:
            if exc.code in {"suppressed", "no_phone"}:
                campaign_lead.status = CampaignLeadStatus.SUPPRESSED.value
                campaign_lead.final_outcome = exc.code
            elif exc.code in {
                "daily_limit",
                "concurrent_limit",
                "campaign_daily_limit",
                "campaign_concurrent_limit",
                "outside_call_hours",
                "campaigns_disabled",
                "live_calls_disabled",
            }:
                return  # kapasite/kapı bitti; sonraki tick'te devam
            else:
                logger.warning("Kampanya lead atlandı (%s)", exc.code)
                campaign_lead.status = CampaignLeadStatus.SKIPPED.value
                campaign_lead.final_outcome = exc.code
    maybe_complete_campaign(db, campaign.id)


@celery_app.task(name="app.tasks.campaign_tasks.callback_due_sweep")
def callback_due_sweep() -> None:
    """Zamanı gelen geri aramalar için panel bildirimi üretir (otomatik arama YOK)."""
    now = datetime.now(UTC)
    with session_scope() as db:
        due = db.scalars(
            select(Callback).where(
                Callback.status == CallbackStatus.PENDING.value,
                Callback.callback_at <= now,
            )
        ).all()
        for callback in due:
            callback.status = CallbackStatus.SCHEDULED.value
            lead = db.get(Lead, callback.lead_id)
            asyncio.run(
                InAppNotificationProvider().notify(
                    NotificationMessage(
                        kind="callback_due",
                        title="Geri arama zamanı geldi",
                        body=f"{lead.business_name if lead else 'Lead'} geri aranmayı bekliyor.",
                        resource_type="callback",
                        resource_id=str(callback.id),
                    )
                )
            )
