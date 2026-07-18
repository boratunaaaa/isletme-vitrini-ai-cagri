from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import ApiModel


class PricingOut(ApiModel):
    id: uuid.UUID
    provider: str
    model: str
    input_audio_price_per_million: str
    cached_audio_price_per_million: str
    output_audio_price_per_million: str
    input_text_price_per_million: str
    cached_text_price_per_million: str
    output_text_price_per_million: str
    currency: str
    effective_from: datetime
    is_active: bool


class PricingUpdate(BaseModel):
    input_audio_price_per_million: str | None = None
    cached_audio_price_per_million: str | None = None
    output_audio_price_per_million: str | None = None
    input_text_price_per_million: str | None = None
    cached_text_price_per_million: str | None = None
    output_text_price_per_million: str | None = None
    is_active: bool | None = None


class SettingItem(BaseModel):
    provider: str
    setting_key: str
    safe_value: str | None
    is_configured: bool
    updated_at: datetime | None = None


class SettingUpdate(BaseModel):
    provider: str
    setting_key: str
    value: str | None = Field(default=None, max_length=500)


class IntegrationStatus(BaseModel):
    provider: str
    configured: bool
    detail: str


class AuditLogOut(ApiModel):
    id: uuid.UUID
    user_id: uuid.UUID | None
    action: str
    resource_type: str | None
    resource_id: str | None
    safe_metadata: dict[str, Any] | None
    ip_address: str | None
    created_at: datetime


class DashboardStats(BaseModel):
    calls_today: int
    answered_today: int
    avg_duration_seconds: int
    interested_count: int
    demo_requested_count: int
    callback_count: int
    do_not_call_count: int
    success_rate: float
    ai_cost_today_usd: str
    telephony_cost_today_usd: str
    total_cost_today_usd: str
    active_campaigns: int
    live_calls: int
    integrations: list[IntegrationStatus]
    gates: dict[str, bool]
