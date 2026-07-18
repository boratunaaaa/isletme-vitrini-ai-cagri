from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ApiModel


class KbEntryOut(ApiModel):
    id: uuid.UUID
    category: str
    title: str
    content: str
    is_active: bool
    version: int
    created_at: datetime
    updated_at: datetime


class KbEntryCreate(BaseModel):
    category: str = Field(min_length=2, max_length=60)
    title: str = Field(min_length=2, max_length=255)
    content: str = Field(min_length=2, max_length=8000)
    is_active: bool = True


class KbEntryUpdate(BaseModel):
    category: str | None = Field(default=None, min_length=2, max_length=60)
    title: str | None = Field(default=None, min_length=2, max_length=255)
    content: str | None = Field(default=None, min_length=2, max_length=8000)
    is_active: bool | None = None


class PromptVersionOut(ApiModel):
    id: uuid.UUID
    name: str
    system_prompt: str
    opening_script: str
    objective: str
    objection_rules: str
    is_active: bool
    created_at: datetime


class PromptVersionCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    system_prompt: str = Field(min_length=10)
    opening_script: str = Field(min_length=10)
    objective: str = Field(min_length=10)
    objection_rules: str = Field(min_length=10)
