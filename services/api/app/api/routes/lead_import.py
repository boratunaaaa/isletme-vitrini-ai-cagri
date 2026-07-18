from __future__ import annotations

import io
import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import write_audit
from app.core.phone import PhoneValidationError, normalize_phone
from app.core.rbac import Permission
from app.deps import client_ip, get_db, require_permission
from app.models.lead import ImportJob
from app.models.user import User
from app.schemas.leads import (
    ImportJobOut,
    ImportPreviewResponse,
    ImportResultOut,
)
from app.services.importer import commit_import, guess_column_mapping, parse_file

router = APIRouter(prefix="/imports", tags=["imports"])

MAX_UPLOAD_BYTES = 30 * 1024 * 1024  # 30 MB


async def _read_upload(file: UploadFile) -> bytes:
    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Dosya 30 MB sınırını aşıyor"
        )
    return raw


def _mask_preview_phone(value: object) -> object:
    """Önizlemede telefonlar maskelenir; düz metin numara UI'a bile gitmez."""
    if value is None:
        return None
    try:
        normalized = normalize_phone(str(value))
        return f"{normalized.country_code} ••• {normalized.last_four}"
    except PhoneValidationError:
        return str(value)[:20]


@router.post("/preview", response_model=ImportPreviewResponse)
async def preview_import(
    file: UploadFile = File(...),
    sheet_name: str | None = Form(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.LEADS_IMPORT)),
) -> ImportPreviewResponse:
    raw = await _read_upload(file)
    try:
        parsed = parse_file(io.BytesIO(raw), file.filename or "dosya", sheet_name)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    mapping = guess_column_mapping(parsed.headers)
    phone_column = mapping.get("phone")
    preview_rows: list[dict[str, object]] = []
    for row in parsed.rows[:20]:
        display: dict[str, object] = {
            k: (str(v)[:120] if v is not None else None) for k, v in row.items()
        }
        if phone_column and phone_column in display:
            display[phone_column] = _mask_preview_phone(row.get(phone_column))
        preview_rows.append(display)

    return ImportPreviewResponse(
        headers=parsed.headers,
        sheet_names=parsed.sheet_names,
        guessed_mapping=mapping,
        preview_rows=preview_rows,
        total_rows=len(parsed.rows),
    )


@router.post("/commit", response_model=ImportResultOut)
async def commit_import_endpoint(
    request: Request,
    file: UploadFile = File(...),
    mapping_json: str = Form(...),
    sheet_name: str | None = Form(default=None),
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(Permission.LEADS_IMPORT)),
) -> ImportResultOut:
    raw = await _read_upload(file)
    try:
        mapping = json.loads(mapping_json)
        if not isinstance(mapping, dict):
            raise ValueError("mapping bir nesne olmalı")
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Geçersiz mapping: {exc}",
        ) from exc

    try:
        parsed = parse_file(io.BytesIO(raw), file.filename or "dosya", sheet_name)
        result = commit_import(
            db,
            parsed_rows=parsed.rows,
            mapping={str(k): str(v) for k, v in mapping.items()},
            filename=file.filename or "dosya",
            created_by=actor.id,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    write_audit(
        db,
        action="leads.import",
        user_id=actor.id,
        resource_type="import_job",
        resource_id=result.job_id,
        safe_metadata={
            "imported": result.imported,
            "duplicates": result.duplicates,
            "invalid": result.invalid,
        },
        ip_address=client_ip(request),
    )
    return ImportResultOut(**result.__dict__)


@router.get("", response_model=list[ImportJobOut])
def list_import_jobs(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.LEADS_IMPORT)),
) -> list[ImportJobOut]:
    jobs = db.scalars(select(ImportJob).order_by(ImportJob.created_at.desc()).limit(50)).all()
    return [ImportJobOut.model_validate(j) for j in jobs]
