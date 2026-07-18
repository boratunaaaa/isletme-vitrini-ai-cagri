from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import ApiModel


class CampaignBase(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=4000)
    conversation_engine: str = "openai_realtime"
    realtime_model: str | None = None
    realtime_voice: str | None = None
    agent_prompt_version_id: uuid.UUID | None = None
    daily_limit: int = Field(default=10, ge=1, le=500)
    concurrent_call_limit: int = Field(default=1, ge=1, le=10)
    call_start_hour: int = Field(default=10, ge=0, le=23)
    call_end_hour: int = Field(default=17, ge=1, le=24)
    max_call_duration_seconds: int = Field(default=300, ge=60, le=1800)
    max_retry_count: int = Field(default=2, ge=0, le=5)
    retry_delay_minutes: int = Field(default=120, ge=15, le=2880)
    region_filter: list[str] | None = None
    sector_filter: list[str] | None = None

    @model_validator(mode="after")
    def _hours_valid(self) -> CampaignBase:
        if self.call_end_hour <= self.call_start_hour:
            raise ValueError("Bitiş saati başlangıç saatinden büyük olmalı")
        return self


class CampaignCreate(CampaignBase):
    pass


class CampaignUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = None
    realtime_model: str | None = None
    realtime_voice: str | None = None
    agent_prompt_version_id: uuid.UUID | None = None
    daily_limit: int | None = Field(default=None, ge=1, le=500)
    concurrent_call_limit: int | None = Field(default=None, ge=1, le=10)
    call_start_hour: int | None = Field(default=None, ge=0, le=23)
    call_end_hour: int | None = Field(default=None, ge=1, le=24)
    max_call_duration_seconds: int | None = Field(default=None, ge=60, le=1800)
    max_retry_count: int | None = Field(default=None, ge=0, le=5)
    retry_delay_minutes: int | None = Field(default=None, ge=15, le=2880)


class CampaignOut(ApiModel):
    id: uuid.UUID
    name: str
    description: str | None
    status: str
    conversation_engine: str
    realtime_model: str
    realtime_voice: str
    agent_prompt_version_id: uuid.UUID | None
    daily_limit: int
    concurrent_call_limit: int
    call_start_hour: int
    call_end_hour: int
    max_call_duration_seconds: int
    max_retry_count: int
    retry_delay_minutes: int
    region_filter: list | None
    sector_filter: list | None
    created_at: datetime


class CampaignStats(BaseModel):
    total_leads: int
    pending: int
    calling: int
    retry_scheduled: int
    completed: int
    suppressed: int
    exhausted: int
    calls_today: int
    outcomes: dict[str, int]
    total_cost_usd: str


class CampaignLeadsAdd(BaseModel):
    lead_ids: list[uuid.UUID] | None = None
    # veya filtre ile toplu ekleme
    sector: str | None = None
    city: str | None = None
    district: str | None = None
    status: str | None = None
    limit: int = Field(default=100, ge=1, le=5000)


class CampaignStatusChange(BaseModel):
    action: str = Field(pattern="^(ready|start|pause|resume|stop|cancel|draft)$")
