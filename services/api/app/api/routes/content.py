"""Bilgi bankası ve prompt versiyonu endpoint'leri."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.audit import write_audit
from app.core.rbac import Permission
from app.deps import client_ip, get_db, require_permission
from app.models.content import AgentPromptVersion, KnowledgeBaseEntry
from app.models.user import User
from app.schemas.common import OkResponse
from app.schemas.content import (
    KbEntryCreate,
    KbEntryOut,
    KbEntryUpdate,
    PromptVersionCreate,
    PromptVersionOut,
)

router = APIRouter(tags=["content"])


@router.get("/kb", response_model=list[KbEntryOut])
def list_kb(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.LEADS_READ)),
) -> list[KbEntryOut]:
    entries = db.scalars(
        select(KnowledgeBaseEntry).order_by(KnowledgeBaseEntry.category, KnowledgeBaseEntry.title)
    ).all()
    return [KbEntryOut.model_validate(e) for e in entries]


@router.post("/kb", response_model=KbEntryOut, status_code=status.HTTP_201_CREATED)
def create_kb(
    payload: KbEntryCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(Permission.KB_WRITE)),
) -> KbEntryOut:
    entry = KnowledgeBaseEntry(**payload.model_dump(), created_by=actor.id)
    db.add(entry)
    db.flush()
    return KbEntryOut.model_validate(entry)


@router.patch("/kb/{entry_id}", response_model=KbEntryOut)
def update_kb(
    entry_id: uuid.UUID,
    payload: KbEntryUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(Permission.KB_WRITE)),
) -> KbEntryOut:
    entry = db.get(KnowledgeBaseEntry, entry_id)
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kayıt bulunamadı")
    data = payload.model_dump(exclude_unset=True)
    if data:
        for field, value in data.items():
            setattr(entry, field, value)
        entry.version += 1  # içerik versiyonlanır
    return KbEntryOut.model_validate(entry)


@router.delete("/kb/{entry_id}", response_model=OkResponse)
def deactivate_kb(
    entry_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.KB_WRITE)),
) -> OkResponse:
    entry = db.get(KnowledgeBaseEntry, entry_id)
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kayıt bulunamadı")
    entry.is_active = False
    return OkResponse(detail="Kayıt pasifleştirildi (silinmedi)")


# ─── Promptlar ───────────────────────────────────────────────────────────────


@router.get("/prompts", response_model=list[PromptVersionOut])
def list_prompts(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.LEADS_READ)),
) -> list[PromptVersionOut]:
    versions = db.scalars(
        select(AgentPromptVersion).order_by(AgentPromptVersion.created_at.desc())
    ).all()
    return [PromptVersionOut.model_validate(v) for v in versions]


@router.post("/prompts", response_model=PromptVersionOut, status_code=status.HTTP_201_CREATED)
def create_prompt(
    payload: PromptVersionCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(Permission.PROMPT_WRITE)),
) -> PromptVersionOut:
    exists = db.scalars(
        select(AgentPromptVersion).where(AgentPromptVersion.name == payload.name)
    ).first()
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "Bu isimde bir versiyon zaten var")
    version = AgentPromptVersion(**payload.model_dump(), created_by=actor.id)
    db.add(version)
    db.flush()
    return PromptVersionOut.model_validate(version)


@router.post("/prompts/{version_id}/activate", response_model=PromptVersionOut)
def activate_prompt(
    version_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(Permission.PROMPT_WRITE)),
) -> PromptVersionOut:
    version = db.get(AgentPromptVersion, version_id)
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Versiyon bulunamadı")
    db.execute(update(AgentPromptVersion).values(is_active=False))
    version.is_active = True
    write_audit(
        db,
        action="prompts.activate",
        user_id=actor.id,
        resource_type="prompt_version",
        resource_id=str(version_id),
        safe_metadata={"name": version.name},
        ip_address=client_ip(request),
    )
    return PromptVersionOut.model_validate(version)
