from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.audit import write_audit
from app.core.ratelimit import (
    RateLimitExceeded,
    check_rate_limit,
    clear_login_failures,
    is_login_locked,
    record_login_failure,
)
from app.core.rbac import permissions_for
from app.core.security import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    create_session,
    csrf_token_for_session,
    destroy_session,
    hash_password,
    password_needs_rehash,
    register_session_for_user,
    verify_password,
)
from app.deps import client_ip, get_current_user, get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, MeResponse, UserOut
from app.schemas.common import OkResponse

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookies(response: Response, token: str) -> None:
    settings = get_settings()
    secure = settings.is_production
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=settings.SESSION_ABSOLUTE_SECONDS,
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token_for_session(token),
        httponly=False,  # double-submit için client okur
        secure=secure,
        samesite="lax",
        max_age=settings.SESSION_ABSOLUTE_SECONDS,
        path="/",
    )


@router.post("/login", response_model=MeResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> MeResponse:
    ip = client_ip(request) or "unknown"
    email = payload.email.lower()
    identifier = f"{ip}:{email}"
    # NOT (PHASE_9_SECURITY_REPORT.md): yalnız `{ip}:{email}` anahtarı,
    # kaynak IP'sini döndüren bir saldırganın her IP için TAZE bir kova/kilit
    # sayacı almasına izin verir — tek bir bilinen hesabı dağıtık şekilde
    # brute-force etmek fiilen sınırsız kalır. Hesap-seviyeli (yalnız e-posta)
    # ikinci bir sayaç, gerçek kullanıcıyı yanlışlıkla kilitleme riskini
    # düşük tutmak için IP-seviyeli eşikten (10) daha yüksek bir eşikle
    # (20) çalışır — savunma derinliği, tek başına ANA mekanizma değil.
    account_identifier = f"account:{email}"
    try:
        check_rate_limit("login", identifier, limit=5, window_seconds=60)
    except RateLimitExceeded as exc:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Çok fazla deneme; lütfen bekleyin.",
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
    if is_login_locked(identifier) or is_login_locked(account_identifier, max_failures=20):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Hesap geçici olarak kilitlendi (15 dk)."
        )

    user = db.scalars(select(User).where(User.email == email)).first()
    if user is None or not verify_password(user.password_hash, payload.password):
        record_login_failure(identifier)
        record_login_failure(account_identifier)
        # Kullanıcı var/yok bilgisi sızdırılmaz
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "E-posta veya parola hatalı")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Hesap pasif durumda")

    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(payload.password)

    clear_login_failures(identifier)
    clear_login_failures(account_identifier)
    user.last_login_at = datetime.now(UTC)
    token = create_session(str(user.id), user.role)
    register_session_for_user(token, str(user.id))
    _set_session_cookies(response, token)
    write_audit(db, action="auth.login", user_id=user.id, ip_address=ip)
    return MeResponse(
        user=UserOut.model_validate(user),
        permissions=permissions_for(user.role),
        csrf_token=csrf_token_for_session(token),
    )


@router.post("/logout", response_model=OkResponse)
def logout(
    request: Request,
    response: Response,
    _: User = Depends(get_current_user),
) -> OkResponse:
    token = request.cookies.get(SESSION_COOKIE, "")
    if token:
        destroy_session(token)
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    return OkResponse(detail="Çıkış yapıldı")


@router.get("/me", response_model=MeResponse)
def me(request: Request, user: User = Depends(get_current_user)) -> MeResponse:
    token = request.cookies.get(SESSION_COOKIE, "")
    return MeResponse(
        user=UserOut.model_validate(user),
        permissions=permissions_for(user.role),
        csrf_token=csrf_token_for_session(token),
    )
