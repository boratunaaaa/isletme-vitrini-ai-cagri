from __future__ import annotations

import csv
import io
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.audit import write_audit
from app.core.crypto import decrypt_pii, encrypt_pii, hash_phone
from app.core.phone import PhoneValidationError, mask_phone, normalize_phone
from app.core.ratelimit import RateLimitExceeded, check_rate_limit
from app.core.rbac import Permission
from app.deps import client_ip, get_db, require_permission
from app.models.lead import Lead, LeadNote, LeadTag
from app.models.user import User
from app.schemas.common import Page
from app.schemas.leads import (
    LeadNoteCreate,
    LeadNoteOut,
    LeadOut,
    LeadTagAssign,
    LeadUpdate,
    PhoneRevealResponse,
    TagCreate,
    TagOut,
)

router = APIRouter(prefix="/leads", tags=["leads"])


def lead_to_out(lead: Lead) -> LeadOut:
    out = LeadOut.model_validate(lead)
    out.has_phone = bool(lead.phone_hash)
    if lead.phone_country_code and lead.phone_last_four:
        out.phone_masked = mask_phone(lead.phone_country_code, lead.phone_last_four)
    return out


@router.get("", response_model=Page[LeadOut])
def list_leads(
    page: int = 1,
    page_size: int = 50,
    q: str | None = None,
    sector: str | None = None,
    city: str | None = None,
    district: str | None = None,
    lead_status: str | None = None,
    priority: str | None = None,
    has_phone: bool | None = None,
    assigned_user_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.LEADS_READ)),
) -> Page[LeadOut]:
    page_size = min(max(page_size, 1), 200)
    query = select(Lead)
    if q:
        like = f"%{q}%"
        query = query.where(
            or_(Lead.business_name.ilike(like), Lead.address.ilike(like), Lead.sector.ilike(like))
        )
    if sector:
        query = query.where(Lead.sector == sector)
    if city:
        query = query.where(Lead.city == city)
    if district:
        query = query.where(Lead.district == district)
    if lead_status:
        query = query.where(Lead.status == lead_status)
    if priority:
        query = query.where(Lead.priority == priority)
    if has_phone is True:
        query = query.where(Lead.phone_hash.is_not(None))
    if has_phone is False:
        query = query.where(Lead.phone_hash.is_(None))
    if assigned_user_id:
        query = query.where(Lead.assigned_user_id == assigned_user_id)

    total = int(db.scalar(select(func.count()).select_from(query.subquery())) or 0)
    leads = db.scalars(
        query.order_by(Lead.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return Page(
        items=[lead_to_out(lead) for lead in leads],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/facets")
def lead_facets(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.LEADS_READ)),
) -> dict[str, list[str]]:
    sectors = [
        s for s in db.scalars(select(Lead.sector).distinct().order_by(Lead.sector)).all() if s
    ]
    cities = [c for c in db.scalars(select(Lead.city).distinct().order_by(Lead.city)).all() if c]
    districts = [
        d for d in db.scalars(select(Lead.district).distinct().order_by(Lead.district)).all() if d
    ]
    return {"sectors": sectors, "cities": cities, "districts": districts}


@router.get("/{lead_id}", response_model=LeadOut)
def get_lead(
    lead_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.LEADS_READ)),
) -> LeadOut:
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lead bulunamadı")
    return lead_to_out(lead)


@router.patch("/{lead_id}", response_model=LeadOut)
def update_lead(
    lead_id: uuid.UUID,
    payload: LeadUpdate,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(Permission.LEADS_WRITE)),
) -> LeadOut:
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lead bulunamadı")

    data = payload.model_dump(exclude_unset=True, exclude={"phone"})
    for field, value in data.items():
        setattr(lead, field, value)

    if payload.phone is not None:
        try:
            normalized = normalize_phone(payload.phone)
        except PhoneValidationError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
        lead.phone_ciphertext = encrypt_pii(normalized.e164)
        lead.phone_hash = hash_phone(normalized.e164)
        lead.phone_last_four = normalized.last_four
        lead.phone_country_code = normalized.country_code

    write_audit(
        db,
        action="leads.update",
        user_id=actor.id,
        resource_type="lead",
        resource_id=str(lead.id),
        safe_metadata={"fields": sorted(data.keys() | ({"phone"} if payload.phone else set()))},
        ip_address=client_ip(request),
    )
    return lead_to_out(lead)


@router.post("/{lead_id}/reveal-phone", response_model=PhoneRevealResponse)
def reveal_phone(
    lead_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(Permission.PHONE_REVEAL)),
) -> PhoneRevealResponse:
    """Tam numara gösterimi: yalnız owner/admin + audit kaydı.

    NOT (PHASE_9_SECURITY_REPORT.md): yetkili ama ele geçirilmiş bir hesabın
    script ile TÜM veritabanını tek tek numara açığa çıkararak sızdırmasını
    zorlaştırmak için kullanıcı-başına rate limit uygulanır.
    """
    try:
        check_rate_limit("phone-reveal", str(actor.id), limit=60, window_seconds=60)
    except RateLimitExceeded as exc:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Çok fazla telefon açma isteği; lütfen bekleyin.",
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
    lead = db.get(Lead, lead_id)
    if lead is None or not lead.phone_ciphertext:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Numara bulunamadı")
    write_audit(
        db,
        action="leads.phone_reveal",
        user_id=actor.id,
        resource_type="lead",
        resource_id=str(lead.id),
        ip_address=client_ip(request),
    )
    return PhoneRevealResponse(phone_e164=decrypt_pii(lead.phone_ciphertext))


@router.get("/{lead_id}/notes", response_model=list[LeadNoteOut])
def list_notes(
    lead_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.LEADS_READ)),
) -> list[LeadNoteOut]:
    notes = db.scalars(
        select(LeadNote).where(LeadNote.lead_id == lead_id).order_by(LeadNote.created_at.desc())
    ).all()
    return [LeadNoteOut.model_validate(n) for n in notes]


@router.post("/{lead_id}/notes", response_model=LeadNoteOut, status_code=status.HTTP_201_CREATED)
def add_note(
    lead_id: uuid.UUID,
    payload: LeadNoteCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(Permission.LEADS_WRITE)),
) -> LeadNoteOut:
    if db.get(Lead, lead_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lead bulunamadı")
    note = LeadNote(lead_id=lead_id, user_id=actor.id, content=payload.content)
    db.add(note)
    db.flush()
    return LeadNoteOut.model_validate(note)


@router.post("/{lead_id}/tags", response_model=LeadOut)
def assign_tags(
    lead_id: uuid.UUID,
    payload: LeadTagAssign,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.LEADS_WRITE)),
) -> LeadOut:
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lead bulunamadı")
    tags = db.scalars(select(LeadTag).where(LeadTag.id.in_(payload.tag_ids))).all()
    lead.tags = list(tags)
    db.flush()
    return lead_to_out(lead)


@router.get("/tags/all", response_model=list[TagOut])
def list_tags(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.LEADS_READ)),
) -> list[TagOut]:
    tags = db.scalars(select(LeadTag).order_by(LeadTag.name)).all()
    return [TagOut.model_validate(t) for t in tags]


@router.post("/tags", response_model=TagOut, status_code=status.HTTP_201_CREATED)
def create_tag(
    payload: TagCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.LEADS_WRITE)),
) -> TagOut:
    existing = db.scalars(select(LeadTag).where(LeadTag.name == payload.name)).first()
    if existing:
        return TagOut.model_validate(existing)
    tag = LeadTag(name=payload.name, color=payload.color)
    db.add(tag)
    db.flush()
    return TagOut.model_validate(tag)


_FORMULA_TRIGGER_CHARS = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(value: str) -> str:
    """CSV/Excel formül enjeksiyonuna (CWE-1236) karşı hücre değerini nötrler.

    NOT (PHASE_9_SECURITY_REPORT.md): `business_name`/`sector`/`city`/
    `district`/`website`/`demo_link` kullanıcı/import kontrollüdür (manuel
    PATCH veya toplu import ile gelir). Excel/Sheets, `=`/`+`/`-`/`@` ile
    başlayan bir hücreyi formül olarak yorumlar — ör. `=HYPERLINK(...)`.
    Standart OWASP mitigasyonu: tetikleyici karakterden önce görünürlüğü
    bozmayan bir tek tırnak ekleyip metni düz metin olarak zorlamak.
    """
    if value and value[0] in _FORMULA_TRIGGER_CHARS:
        return "'" + value
    return value


@router.post("/export")
def export_leads(
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(Permission.LEADS_EXPORT)),
) -> StreamingResponse:
    """CSV dışa aktarma — telefonlar MASKELİ (düz metin numara asla export edilmez).

    NOT (PHASE_9_SECURITY_REPORT.md): tekrarlanan tam-veritabanı export'larını
    (ucuz DoS + veri sızdırma script'i) zorlaştırmak için kullanıcı-başına
    rate limit uygulanır — export'lar doğası gereği seyrek yapılan işlemlerdir.
    """
    try:
        check_rate_limit("leads-export", str(actor.id), limit=5, window_seconds=60)
    except RateLimitExceeded as exc:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Çok fazla export isteği; lütfen bekleyin.",
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
    leads = db.scalars(select(Lead).order_by(Lead.created_at)).all()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "Firma",
            "Sektör",
            "Şehir",
            "İlçe",
            "Telefon (maskeli)",
            "Durum",
            "Website",
            "Demo Link",
            "Puan",
            "Yorum",
        ]
    )
    for lead in leads:
        masked = (
            mask_phone(lead.phone_country_code, lead.phone_last_four)
            if lead.phone_country_code and lead.phone_last_four
            else ""
        )
        writer.writerow(
            [
                _csv_safe(lead.business_name),
                _csv_safe(lead.sector or ""),
                _csv_safe(lead.city or ""),
                _csv_safe(lead.district or ""),
                masked,
                lead.status,
                _csv_safe(lead.website or ""),
                _csv_safe(lead.demo_link or ""),
                lead.rating if lead.rating is not None else "",
                lead.review_count if lead.review_count is not None else "",
            ]
        )
    write_audit(
        db,
        action="leads.export",
        user_id=actor.id,
        safe_metadata={"count": len(leads)},
        ip_address=client_ip(request),
    )
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=leads-masked.csv"},
    )
