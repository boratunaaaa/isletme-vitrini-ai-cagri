"""Callback, demo talepleri ve suppression listesi endpoint'leri."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import write_audit
from app.core.crypto import decrypt_pii, hash_phone
from app.core.phone import PhoneValidationError, normalize_phone
from app.core.rbac import Permission
from app.deps import client_ip, get_db, require_permission
from app.models.lead import Lead
from app.models.ops import Callback, DemoRequest, SuppressionEntry
from app.models.user import User
from app.providers.notification import WaMeManualNotificationProvider
from app.schemas.common import OkResponse
from app.schemas.ops import (
    CallbackOut,
    CallbackUpdate,
    DemoRequestOut,
    SuppressionCreate,
    SuppressionOut,
    WaLinkResponse,
)
from app.services.suppression_service import add_suppression, remove_suppression

router = APIRouter(tags=["ops"])


# ─── Callbacks ───────────────────────────────────────────────────────────────


@router.get("/callbacks", response_model=list[CallbackOut])
def list_callbacks(
    include_done: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.LEADS_READ)),
) -> list[CallbackOut]:
    query = (
        select(Callback, Lead.business_name)
        .join(Lead, Lead.id == Callback.lead_id)
        .order_by(Callback.callback_at)
    )
    if not include_done:
        query = query.where(Callback.status.in_(["pending", "scheduled"]))
    rows = db.execute(query.limit(500)).all()
    results = []
    for callback, name in rows:
        out = CallbackOut.model_validate(callback)
        out.business_name = name
        results.append(out)
    return results


@router.patch("/callbacks/{callback_id}", response_model=CallbackOut)
def update_callback(
    callback_id: uuid.UUID,
    payload: CallbackUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.LEADS_WRITE)),
) -> CallbackOut:
    callback = db.get(Callback, callback_id)
    if callback is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Geri arama kaydı bulunamadı")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(callback, field, value)
    db.flush()
    lead = db.get(Lead, callback.lead_id)
    out = CallbackOut.model_validate(callback)
    out.business_name = lead.business_name if lead else None
    return out


# ─── Demo talepleri ──────────────────────────────────────────────────────────


@router.get("/demo-requests", response_model=list[DemoRequestOut])
def list_demo_requests(
    include_sent: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.LEADS_READ)),
) -> list[DemoRequestOut]:
    query = (
        select(DemoRequest, Lead.business_name, Lead.demo_link)
        .join(Lead, Lead.id == DemoRequest.lead_id)
        .order_by(DemoRequest.created_at.desc())
    )
    if not include_sent:
        query = query.where(DemoRequest.status == "pending")
    rows = db.execute(query.limit(500)).all()
    results = []
    for demo, name, link in rows:
        out = DemoRequestOut.model_validate(demo)
        out.business_name = name
        out.demo_link = link
        results.append(out)
    return results


@router.get("/demo-requests/{demo_id}/wa-link", response_model=WaLinkResponse)
def demo_wa_link(
    demo_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    # NOT (PHASE_9_SECURITY_REPORT.md): önceden `Permission.CALL_INITIATE`
    # gerektiriyordu — bu, `PHONE_REVEAL` YETKİSİ OLMAYAN `sales_agent`
    # rolünün (bkz. app/core/rbac.py `_MATRIX`) tam açık telefon numarasını
    # bu farklı-yetkili endpoint üzerinden almasına izin veriyordu (dedicated
    # `leads.py::reveal_phone` doğru şekilde PHONE_REVEAL istiyordu). Bu
    # endpoint'in TEK amacı telefon numarası içeren bir link üretmek olduğu
    # için doğru yetki PHONE_REVEAL'dir.
    actor: User = Depends(require_permission(Permission.PHONE_REVEAL)),
) -> WaLinkResponse:
    """wa.me linki üretir (manuel gönderim). Numara içerdiği için audit'lenir."""
    demo = db.get(DemoRequest, demo_id)
    if demo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Demo talebi bulunamadı")
    lead = db.get(Lead, demo.lead_id)
    if lead is None or not lead.phone_ciphertext:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lead telefonu yok")
    text = (
        f"Merhaba, İşletme Vitrini'nden yazıyorum. Görüşmemizde bahsettiğimiz "
        f"{lead.business_name} demo sayfası: {lead.demo_link or '(demo linki hazırlanıyor)'}"
    )
    link = WaMeManualNotificationProvider.build_link(decrypt_pii(lead.phone_ciphertext), text)
    write_audit(
        db,
        action="demos.wa_link",
        user_id=actor.id,
        resource_type="demo_request",
        resource_id=str(demo_id),
        ip_address=client_ip(request),
    )
    return WaLinkResponse(wa_link=link)


@router.post("/demo-requests/{demo_id}/mark-sent", response_model=OkResponse)
def mark_demo_sent(
    demo_id: uuid.UUID,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(Permission.LEADS_WRITE)),
) -> OkResponse:
    demo = db.get(DemoRequest, demo_id)
    if demo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Demo talebi bulunamadı")
    demo.status = "sent"
    demo.sent_at = datetime.now(UTC)
    demo.assigned_user_id = actor.id
    return OkResponse(detail="Demo gönderildi olarak işaretlendi")


# ─── Suppression ─────────────────────────────────────────────────────────────


@router.get("/suppression", response_model=list[SuppressionOut])
def list_suppression(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.LEADS_READ)),
) -> list[SuppressionOut]:
    rows = db.execute(
        select(SuppressionEntry, Lead.business_name)
        .outerjoin(Lead, Lead.id == SuppressionEntry.lead_id)
        .order_by(SuppressionEntry.created_at.desc())
        .limit(1000)
    ).all()
    results = []
    for entry, name in rows:
        out = SuppressionOut.model_validate(entry)
        out.business_name = name
        results.append(out)
    return results


@router.post("/suppression", response_model=SuppressionOut, status_code=status.HTTP_201_CREATED)
def create_suppression(
    payload: SuppressionCreate,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(Permission.SUPPRESSION_WRITE)),
) -> SuppressionOut:
    if payload.lead_id:
        lead = db.get(Lead, payload.lead_id)
        if lead is None or not lead.phone_hash or not lead.phone_last_four:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Lead veya telefonu bulunamadı")
        phone_hash_value, last_four = lead.phone_hash, lead.phone_last_four
        lead.status = "do_not_call"
    elif payload.phone:
        try:
            normalized = normalize_phone(payload.phone)
        except PhoneValidationError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
        phone_hash_value, last_four = hash_phone(normalized.e164), normalized.last_four
    else:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "lead_id veya phone zorunlu")

    entry = add_suppression(
        db,
        phone_hash=phone_hash_value,
        phone_last_four=last_four,
        reason=payload.reason,
        source="manual",
        lead_id=payload.lead_id,
        added_by=actor.id,
    )
    write_audit(
        db,
        action="suppression.add",
        user_id=actor.id,
        resource_type="suppression",
        resource_id=str(entry.id),
        safe_metadata={"reason": payload.reason},
        ip_address=client_ip(request),
    )
    out = SuppressionOut.model_validate(entry)
    return out


@router.delete("/suppression/{entry_id}", response_model=OkResponse)
def delete_suppression(
    entry_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(Permission.SUPPRESSION_REMOVE)),
) -> OkResponse:
    if not remove_suppression(db, entry_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kayıt bulunamadı")
    write_audit(
        db,
        action="suppression.remove",
        user_id=actor.id,
        resource_type="suppression",
        resource_id=str(entry_id),
        ip_address=client_ip(request),
    )
    return OkResponse(detail="Engel kaldırıldı")
