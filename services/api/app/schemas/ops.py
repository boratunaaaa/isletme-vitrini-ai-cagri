from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ApiModel


class CallbackOut(ApiModel):
    id: uuid.UUID
    lead_id: uuid.UUID
    call_id: uuid.UUID | None
    requested_at: datetime
    callback_at: datetime
    assigned_user_id: uuid.UUID | None
    status: str
    notes: str | None
    business_name: str | None = None


class CallbackUpdate(BaseModel):
    status: str | None = Field(default=None, pattern="^(pending|scheduled|done|cancelled|missed)$")
    callback_at: datetime | None = None
    assigned_user_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=4000)


class DemoRequestOut(ApiModel):
    id: uuid.UUID
    lead_id: uuid.UUID
    call_id: uuid.UUID | None
    requested_channel: str
    status: str
    assigned_user_id: uuid.UUID | None
    sent_at: datetime | None
    created_at: datetime
    business_name: str | None = None
    demo_link: str | None = None


class WaLinkResponse(BaseModel):
    wa_link: str


class SuppressionOut(ApiModel):
    id: uuid.UUID
    phone_last_four: str
    lead_id: uuid.UUID | None
    reason: str
    source: str
    added_by: uuid.UUID | None
    created_at: datetime
    business_name: str | None = None


class SuppressionCreate(BaseModel):
    lead_id: uuid.UUID | None = None
    phone: str | None = Field(default=None, description="Lead yoksa ham numara")
    reason: str = Field(min_length=2, max_length=255)
