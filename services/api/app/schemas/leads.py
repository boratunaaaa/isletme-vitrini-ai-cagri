from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import ApiModel


class TagOut(ApiModel):
    id: uuid.UUID
    name: str
    color: str


class LeadNoteOut(ApiModel):
    id: uuid.UUID
    user_id: uuid.UUID | None
    content: str
    created_at: datetime


class LeadOut(ApiModel):
    id: uuid.UUID
    external_place_id: str | None
    source: str
    business_name: str
    sector: str | None
    category: str | None
    city: str | None
    district: str | None
    address: str | None
    website: str | None
    rating: float | None
    review_count: int | None
    phone_masked: str | None = None  # servis katmanında doldurulur
    phone_last_four: str | None
    phone_country_code: str | None
    has_phone: bool = False
    status: str
    priority: str
    assigned_user_id: uuid.UUID | None
    demo_link: str | None
    last_contacted_at: datetime | None
    next_action_at: datetime | None
    created_at: datetime
    tags: list[TagOut] = []


class LeadUpdate(BaseModel):
    business_name: str | None = Field(default=None, min_length=1, max_length=500)
    sector: str | None = None
    city: str | None = None
    district: str | None = None
    address: str | None = None
    website: str | None = None
    demo_link: str | None = None
    status: str | None = None
    priority: str | None = Field(default=None, pattern="^(high|normal|low)$")
    assigned_user_id: uuid.UUID | None = None
    phone: str | None = Field(default=None, description="Yeni numara; normalize edilip şifrelenir")


class LeadNoteCreate(BaseModel):
    content: str = Field(min_length=1, max_length=5000)


class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    color: str = Field(default="#64748b", pattern="^#[0-9a-fA-F]{6}$")


class LeadTagAssign(BaseModel):
    tag_ids: list[uuid.UUID]


class PhoneRevealResponse(BaseModel):
    phone_e164: str


class ImportPreviewResponse(BaseModel):
    headers: list[str]
    sheet_names: list[str]
    guessed_mapping: dict[str, str]
    preview_rows: list[dict[str, Any]]
    total_rows: int


class ImportCommitRequest(BaseModel):
    mapping: dict[str, str]
    sheet_name: str | None = None


class ImportResultOut(BaseModel):
    job_id: str
    total_rows: int
    imported: int
    duplicates: int
    invalid: int
    errors: list[dict[str, Any]]


class ImportJobOut(ApiModel):
    id: uuid.UUID
    filename: str
    source_format: str
    status: str
    total_rows: int
    imported_count: int
    duplicate_count: int
    invalid_count: int
    created_at: datetime
