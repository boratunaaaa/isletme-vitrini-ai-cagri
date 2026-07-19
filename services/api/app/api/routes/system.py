"""Dashboard özet metrikleri, entegrasyon ayarları, fiyatlandırma ve audit log erişimi.

Bu route dosyası Aşama 5 (Next.js yönetim paneli) hazırlığı sırasında eklendi:
`app/schemas/system.py`, `app/models/system.py`, `app/models/pricing.py` ve
`app/services/settings_service.py` önceden vardı ama hiçbir router bunları dışarı
açmıyordu — panelin Dashboard/Ayarlar/Entegrasyonlar/Fiyatlandırma/Audit Log
sayfaları için gerçek bir backend contract eksikliğiydi. Detay:
`docs/frontend-management-panel.md` ve `CLAUDE_PROGRESS_PHASE_5_FRONTEND.md`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.audit import write_audit
from app.core.rbac import Permission
from app.deps import client_ip, get_current_user, get_db, require_permission
from app.models.call import Call, CallUsage
from app.models.campaign import Campaign
from app.models.enums import ACTIVE_CALL_STATUSES, CallOutcome, CampaignStatus, LeadStatus
from app.models.lead import Lead
from app.models.ops import Callback
from app.models.pricing import ProviderPricing
from app.models.system import AuditLog, IntegrationSetting
from app.models.user import User
from app.schemas.common import Page
from app.schemas.system import (
    AuditLogOut,
    DashboardStats,
    IntegrationStatus,
    PricingOut,
    PricingUpdate,
    SettingItem,
    SettingUpdate,
)
from app.services.settings_service import EDITABLE_KEYS, integration_status, set_setting

router = APIRouter(tags=["system"])

_DECIMAL_PRICING_FIELDS = frozenset(
    {
        "input_audio_price_per_million",
        "cached_audio_price_per_million",
        "output_audio_price_per_million",
        "input_text_price_per_million",
        "cached_text_price_per_million",
        "output_text_price_per_million",
    }
)


def _today_bounds_utc() -> tuple[datetime, datetime]:
    tz = ZoneInfo(get_settings().APP_TIMEZONE)
    local_now = datetime.now(tz)
    day_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return day_start.astimezone(UTC), (day_start + timedelta(days=1)).astimezone(UTC)


@router.get("/dashboard/stats", response_model=DashboardStats)
def dashboard_stats(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> DashboardStats:
    settings = get_settings()
    start, end = _today_bounds_utc()

    today_calls = db.scalars(
        select(Call).where(Call.created_at >= start, Call.created_at < end)
    ).all()
    calls_today = len(today_calls)
    answered_today = sum(1 for c in today_calls if c.answered_at is not None)
    durations = [c.duration_seconds for c in today_calls if c.duration_seconds]
    avg_duration_seconds = int(sum(durations) / len(durations)) if durations else 0
    interested_count = sum(1 for c in today_calls if c.outcome == CallOutcome.INTERESTED.value)
    demo_requested_count = sum(
        1 for c in today_calls if c.outcome == CallOutcome.DEMO_REQUESTED.value
    )
    success_rate = round(interested_count / calls_today, 4) if calls_today else 0.0

    callback_count = int(
        db.scalar(
            select(func.count(Callback.id)).where(Callback.status.in_(["pending", "scheduled"]))
        )
        or 0
    )
    do_not_call_count = int(
        db.scalar(select(func.count(Lead.id)).where(Lead.status == LeadStatus.DO_NOT_CALL.value))
        or 0
    )

    ai_cost, telephony_cost, total_cost = db.execute(
        select(
            func.coalesce(func.sum(CallUsage.estimated_ai_cost), 0),
            func.coalesce(func.sum(CallUsage.estimated_telephony_cost), 0),
            func.coalesce(func.sum(CallUsage.estimated_total_cost), 0),
        )
        .select_from(CallUsage)
        .join(Call, Call.id == CallUsage.call_id)
        .where(Call.created_at >= start, Call.created_at < end)
    ).one()

    active_campaigns = int(
        db.scalar(
            select(func.count(Campaign.id)).where(Campaign.status == CampaignStatus.RUNNING.value)
        )
        or 0
    )
    live_calls = int(
        db.scalar(
            select(func.count(Call.id)).where(
                Call.status.in_([s.value for s in ACTIVE_CALL_STATUSES])
            )
        )
        or 0
    )

    return DashboardStats(
        calls_today=calls_today,
        answered_today=answered_today,
        avg_duration_seconds=avg_duration_seconds,
        interested_count=interested_count,
        demo_requested_count=demo_requested_count,
        callback_count=callback_count,
        do_not_call_count=do_not_call_count,
        success_rate=success_rate,
        ai_cost_today_usd=str(ai_cost),
        telephony_cost_today_usd=str(telephony_cost),
        total_cost_today_usd=str(total_cost),
        active_campaigns=active_campaigns,
        live_calls=live_calls,
        integrations=[
            IntegrationStatus(
                provider=str(item["provider"]),
                configured=bool(item["configured"]),
                detail=str(item["detail"]),
            )
            for item in integration_status(db)
        ],
        gates={
            "live_calls_enabled": settings.LIVE_CALLS_ENABLED,
            "campaigns_enabled": settings.CAMPAIGNS_ENABLED,
        },
    )


def _pricing_out(row: ProviderPricing) -> PricingOut:
    return PricingOut(
        id=row.id,
        provider=row.provider,
        model=row.model,
        input_audio_price_per_million=str(row.input_audio_price_per_million),
        cached_audio_price_per_million=str(row.cached_audio_price_per_million),
        output_audio_price_per_million=str(row.output_audio_price_per_million),
        input_text_price_per_million=str(row.input_text_price_per_million),
        cached_text_price_per_million=str(row.cached_text_price_per_million),
        output_text_price_per_million=str(row.output_text_price_per_million),
        currency=row.currency,
        effective_from=row.effective_from,
        is_active=row.is_active,
    )


@router.get("/pricing", response_model=list[PricingOut])
def list_pricing(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.SETTINGS_READ)),
) -> list[PricingOut]:
    rows = db.scalars(
        select(ProviderPricing).order_by(ProviderPricing.provider, ProviderPricing.model)
    ).all()
    return [_pricing_out(r) for r in rows]


@router.patch("/pricing/{pricing_id}", response_model=PricingOut)
def update_pricing(
    pricing_id: uuid.UUID,
    payload: PricingUpdate,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(Permission.PRICING_WRITE)),
) -> PricingOut:
    row = db.get(ProviderPricing, pricing_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fiyatlandırma kaydı bulunamadı")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        if field in _DECIMAL_PRICING_FIELDS:
            if value is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{field} boş olamaz")
            try:
                value = Decimal(value)
            except InvalidOperation as exc:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY, f"Geçersiz fiyat: {field}"
                ) from exc
        setattr(row, field, value)
    db.flush()
    write_audit(
        db,
        action="pricing.update",
        user_id=actor.id,
        resource_type="provider_pricing",
        resource_id=str(row.id),
        safe_metadata={"fields": sorted(data.keys())},
        ip_address=client_ip(request),
    )
    return _pricing_out(row)


@router.get("/settings", response_model=list[SettingItem])
def list_settings(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.SETTINGS_READ)),
) -> list[SettingItem]:
    existing = {
        (row.provider, row.setting_key): row for row in db.scalars(select(IntegrationSetting)).all()
    }
    items: list[SettingItem] = []
    for provider, key in sorted(EDITABLE_KEYS):
        row = existing.get((provider, key))
        items.append(
            SettingItem(
                provider=provider,
                setting_key=key,
                safe_value=row.safe_value if row else None,
                is_configured=bool(row and row.is_configured),
                updated_at=row.updated_at if row else None,
            )
        )
    return items


@router.patch("/settings", response_model=SettingItem)
def update_setting(
    payload: SettingUpdate,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(Permission.SETTINGS_WRITE)),
) -> SettingItem:
    try:
        row = set_setting(db, payload.provider, payload.setting_key, payload.value)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    write_audit(
        db,
        action="settings.update",
        user_id=actor.id,
        resource_type="integration_setting",
        resource_id=f"{payload.provider}.{payload.setting_key}",
        ip_address=client_ip(request),
    )
    return SettingItem(
        provider=row.provider,
        setting_key=row.setting_key,
        safe_value=row.safe_value,
        is_configured=row.is_configured,
        updated_at=row.updated_at,
    )


@router.get("/audit-logs", response_model=Page[AuditLogOut])
def list_audit_logs(
    page: int = 1,
    page_size: int = 50,
    action: str | None = None,
    user_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.AUDIT_READ)),
) -> Page[AuditLogOut]:
    page_size = min(max(page_size, 1), 200)
    query = select(AuditLog)
    if action:
        query = query.where(AuditLog.action == action)
    if user_id:
        query = query.where(AuditLog.user_id == user_id)
    total = int(db.scalar(select(func.count()).select_from(query.subquery())) or 0)
    rows = db.scalars(
        query.order_by(AuditLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return Page(
        items=[AuditLogOut.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )
