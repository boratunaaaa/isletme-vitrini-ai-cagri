from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import write_audit
from app.core.rbac import Permission
from app.core.security import destroy_all_sessions_for_user, hash_password
from app.deps import client_ip, get_db, require_permission
from app.models.user import User
from app.schemas.auth import UserCreate, UserOut, UserUpdate
from app.schemas.common import OkResponse, Page

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=Page[UserOut])
def list_users(
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.USERS_MANAGE)),
) -> Page[UserOut]:
    total = int(db.scalar(select(func.count(User.id))) or 0)
    users = db.scalars(
        select(User).order_by(User.created_at).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return Page(
        items=[UserOut.model_validate(u) for u in users],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(Permission.USERS_MANAGE)),
) -> UserOut:
    exists = db.scalars(select(User).where(User.email == payload.email.lower())).first()
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "Bu e-posta zaten kayıtlı")
    user = User(
        email=payload.email.lower(),
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    db.flush()
    write_audit(
        db,
        action="users.create",
        user_id=actor.id,
        resource_type="user",
        resource_id=str(user.id),
        safe_metadata={"role": payload.role},
        ip_address=client_ip(request),
    )
    return UserOut.model_validate(user)


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(Permission.USERS_MANAGE)),
) -> UserOut:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kullanıcı bulunamadı")
    if user.role == "owner" and actor.id != user.id and payload.role and payload.role != "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Owner rolü başkası tarafından düşürülemez")

    changes: dict[str, str] = {}
    if payload.full_name is not None:
        user.full_name = payload.full_name
        changes["full_name"] = "updated"
    if payload.role is not None and payload.role != user.role:
        user.role = payload.role
        changes["role"] = payload.role
        destroy_all_sessions_for_user(str(user.id))  # rol değişince oturumlar düşer
    if payload.is_active is not None and payload.is_active != user.is_active:
        user.is_active = payload.is_active
        changes["is_active"] = str(payload.is_active)
        if not payload.is_active:
            destroy_all_sessions_for_user(str(user.id))
    if payload.password is not None:
        user.password_hash = hash_password(payload.password)
        changes["password"] = "reset"
        destroy_all_sessions_for_user(str(user.id))

    write_audit(
        db,
        action="users.update",
        user_id=actor.id,
        resource_type="user",
        resource_id=str(user.id),
        safe_metadata=changes,
        ip_address=client_ip(request),
    )
    return UserOut.model_validate(user)


@router.delete("/{user_id}", response_model=OkResponse)
def deactivate_user(
    user_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission(Permission.USERS_MANAGE)),
) -> OkResponse:
    """Kullanıcı silinmez, pasifleştirilir (audit bütünlüğü için)."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kullanıcı bulunamadı")
    if user.role == "owner":
        owner_count = int(
            db.scalar(
                select(func.count(User.id)).where(User.role == "owner", User.is_active.is_(True))
            )
            or 0
        )
        if owner_count <= 1:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Son owner pasifleştirilemez")
    user.is_active = False
    destroy_all_sessions_for_user(str(user.id))
    write_audit(
        db,
        action="users.deactivate",
        user_id=actor.id,
        resource_type="user",
        resource_id=str(user.id),
        ip_address=client_ip(request),
    )
    return OkResponse(detail="Kullanıcı pasifleştirildi")
