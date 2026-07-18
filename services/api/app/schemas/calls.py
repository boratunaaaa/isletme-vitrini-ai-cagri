from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import ApiModel


class CallInitiateRequest(BaseModel):
    lead_id: uuid.UUID
    engine: str | None = None
    model: str | None = None
    voice: str | None = None
    idempotency_key: str | None = Field(default=None, max_length=80)


class CallOut(ApiModel):
    id: uuid.UUID
    lead_id: uuid.UUID
    campaign_id: uuid.UUID | None
    initiated_by: uuid.UUID | None
    telephony_provider: str
    conversation_provider: str
    model: str
    voice: str
    status: str
    outcome: str | None
    phone_last_four: str | None
    started_at: datetime | None
    answered_at: datetime | None
    ended_at: datetime | None
    duration_seconds: int | None
    disconnect_reason: str | None
    error_code: str | None
    safe_summary: str | None
    callback_at: datetime | None
    demo_requested: bool
    transfer_requested: bool
    created_at: datetime
    business_name: str | None = None  # join ile doldurulur


class CallEventOut(ApiModel):
    id: uuid.UUID
    event_type: str
    safe_payload: dict[str, Any] | None
    event_timestamp: datetime


class CallUsageOut(ApiModel):
    provider: str
    model: str
    input_audio_tokens: int
    cached_input_audio_tokens: int
    output_audio_tokens: int
    input_text_tokens: int
    cached_input_text_tokens: int
    output_text_tokens: int
    reasoning_tokens: int | None
    usage_source: str
    estimated_ai_cost: str
    estimated_telephony_cost: str
    estimated_total_cost: str
    currency: str


class CallDetailOut(BaseModel):
    call: CallOut
    events: list[CallEventOut]
    usage: CallUsageOut | None
    transcript: list[dict[str, Any]] | None


class QualityMetricsIn(BaseModel):
    user_quality_score: int | None = Field(default=None, ge=1, le=10)
    tr_naturalness_score: int | None = Field(default=None, ge=1, le=10)
    understanding_score: int | None = Field(default=None, ge=1, le=10)
    sales_flow_score: int | None = Field(default=None, ge=1, le=10)
    notes: str | None = Field(default=None, max_length=4000)
