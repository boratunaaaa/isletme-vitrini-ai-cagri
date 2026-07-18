"""FastAPI dependency'leri: DB session, oturum, RBAC, CSRF, internal auth."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.rbac import Permission, has_permission
from app.core.security import (
    CSRF_HEADER,
    SESSION_COOKIE,
    load_session,
    verify_csrf,
    verify_internal_token_with_rotation,
)
from app.db.session import get_sessionmaker
from app.models.user import User


@dataclass(frozen=True)
class InternalServiceContext:
    service_name: str
    authenticated_with: str
    request_id: str


def get_db() -> Iterator[Session]:
    db = get_sessionmaker()()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_session_token(request: Request) -> str:
    token = request.cookies.get(SESSION_COOKIE, "")
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Oturum bulunamadı")
    return token


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = get_session_token(request)
    session_data = load_session(token)
    if session_data is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Oturum geçersiz veya süresi dolmuş")
    user = db.get(User, uuid.UUID(session_data.user_id))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Kullanıcı pasif veya silinmiş")
    # Mutasyon isteklerinde CSRF zorunlu
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        provided = request.headers.get(CSRF_HEADER)
        if not verify_csrf(token, provided):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "CSRF doğrulaması başarısız")
    return user


def require_permission(permission: Permission) -> Callable[[User], User]:
    def dependency(user: User = Depends(get_current_user)) -> User:
        if not has_permission(user.role, permission):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, f"Bu işlem için yetkiniz yok ({permission.value})"
            )
        return user

    return dependency


def require_internal_service(
    request: Request,
    authorization: str | None = Header(default=None),
) -> InternalServiceContext:
    """Voice agent → API dahili endpoint kimlik doğrulaması."""
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
    if token is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            {
                "code": "INTERNAL_AUTH_REQUIRED",
                "message": "Internal service authentication is required.",
            },
        )
    matched = verify_internal_token_with_rotation(token)
    if matched is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            {
                "code": "INTERNAL_AUTH_INVALID",
                "message": "Internal service authentication failed.",
            },
        )
    from app.config import get_settings
    from app.core.logging import request_id_var

    request_id = request.headers.get("X-Request-ID") or request_id_var.get() or ""
    return InternalServiceContext(
        service_name=get_settings().INTERNAL_SERVICE_NAME,
        authenticated_with=matched,
        request_id=request_id,
    )


def client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None
