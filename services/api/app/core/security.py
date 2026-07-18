"""Kimlik doğrulama: Argon2id parola hash'i + Redis tabanlı opaque oturum.

Oturum tasarımı:
- Token: 256-bit rastgele, httpOnly+SameSite=Lax cookie'de taşınır.
- Redis'te `session:{token}` altında user_id/role/absolute_expiry tutulur.
- Kayan (idle) TTL + mutlak ömür; logout anında iptal edilebilir.
- CSRF: double-submit — oturum token'ına HMAC ile bağlı ayrı bir csrf token
  httpOnly OLMAYAN cookie'ye yazılır; mutasyon isteklerinde X-CSRF-Token
  header'ı ile eşleşmesi zorunludur.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.config import get_settings
from app.core.redis import get_redis

_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)

SESSION_COOKIE = "ivac_session"
CSRF_COOKIE = "ivac_csrf"
CSRF_HEADER = "X-CSRF-Token"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def password_needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


@dataclass(frozen=True)
class SessionData:
    user_id: str
    role: str
    created_at: float
    absolute_expiry: float


def _session_key(token: str) -> str:
    digest = hashlib.sha256(token.encode()).hexdigest()
    return f"session:{digest}"


def create_session(user_id: str, role: str) -> str:
    settings = get_settings()
    token = secrets.token_urlsafe(32)
    now = time.time()
    data = SessionData(
        user_id=user_id,
        role=role,
        created_at=now,
        absolute_expiry=now + settings.SESSION_ABSOLUTE_SECONDS,
    )
    get_redis().set(
        _session_key(token),
        json.dumps(data.__dict__),
        ex=settings.SESSION_IDLE_SECONDS,
    )
    return token


def load_session(token: str) -> SessionData | None:
    if not token:
        return None
    settings = get_settings()
    r = get_redis()
    key = _session_key(token)
    raw = r.get(key)
    if raw is None:
        return None
    data = SessionData(**json.loads(raw))
    if data.absolute_expiry < time.time():
        r.delete(key)
        return None
    r.expire(key, settings.SESSION_IDLE_SECONDS)  # kayan TTL
    return data


def destroy_session(token: str) -> None:
    if token:
        get_redis().delete(_session_key(token))


def destroy_all_sessions_for_user(user_id: str) -> None:
    """Not: token hash'leri user'a göre indekslenmez; user bazlı iptal için
    ayrı bir set tutulur."""
    r = get_redis()
    members = r.smembers(f"user_sessions:{user_id}")
    if members:
        digests = [m.decode() if isinstance(m, bytes) else str(m) for m in members]
        r.delete(*[f"session:{digest}" for digest in digests])
        r.delete(f"user_sessions:{user_id}")


def register_session_for_user(token: str, user_id: str) -> None:
    digest = hashlib.sha256(token.encode()).hexdigest()
    r = get_redis()
    r.sadd(f"user_sessions:{user_id}", digest)
    r.expire(f"user_sessions:{user_id}", get_settings().SESSION_ABSOLUTE_SECONDS)


def csrf_token_for_session(session_token: str) -> str:
    secret = get_settings().JWT_SECRET.encode()
    return hmac.new(secret, f"csrf:{session_token}".encode(), hashlib.sha256).hexdigest()


def verify_csrf(session_token: str, provided: str | None) -> bool:
    if not provided:
        return False
    expected = csrf_token_for_session(session_token)
    return hmac.compare_digest(expected, provided)


def verify_internal_token(provided: str | None) -> bool:
    expected = get_settings().INTERNAL_SERVICE_TOKEN
    if not provided or not expected:
        return False
    return hmac.compare_digest(expected, provided)


def verify_internal_token_with_rotation(provided: str | None) -> str | None:
    if not provided:
        return None
    settings = get_settings()
    if settings.INTERNAL_SERVICE_TOKEN and hmac.compare_digest(
        settings.INTERNAL_SERVICE_TOKEN, provided
    ):
        return "current"
    if settings.INTERNAL_SERVICE_TOKEN_PREVIOUS and hmac.compare_digest(
        settings.INTERNAL_SERVICE_TOKEN_PREVIOUS, provided
    ):
        return "previous"
    return None
