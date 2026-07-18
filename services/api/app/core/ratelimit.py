"""Redis tabanlı basit sabit-pencere rate limiter + login brute-force kilidi."""

from __future__ import annotations

import hashlib

from app.core.redis import get_redis


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after
        super().__init__(f"Rate limit aşıldı, {retry_after}s sonra tekrar deneyin")


def _bucket(name: str, identifier: str) -> str:
    digest = hashlib.sha256(identifier.encode()).hexdigest()[:24]
    return f"rl:{name}:{digest}"


def check_rate_limit(name: str, identifier: str, limit: int, window_seconds: int) -> None:
    r = get_redis()
    key = _bucket(name, identifier)
    current = r.incr(key)
    if current == 1:
        r.expire(key, window_seconds)
    if int(current) > limit:
        ttl = r.ttl(key)
        raise RateLimitExceeded(retry_after=max(int(ttl), 1))


def record_login_failure(identifier: str) -> int:
    r = get_redis()
    key = _bucket("loginfail", identifier)
    count = int(r.incr(key))
    r.expire(key, 900)  # 15 dakika pencere
    return count


def is_login_locked(identifier: str, max_failures: int = 10) -> bool:
    r = get_redis()
    value = r.get(_bucket("loginfail", identifier))
    return value is not None and int(value) >= max_failures


def clear_login_failures(identifier: str) -> None:
    get_redis().delete(_bucket("loginfail", identifier))
