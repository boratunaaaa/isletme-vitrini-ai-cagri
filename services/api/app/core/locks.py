"""Distributed lock ve idempotency yardımcıları (Redis)."""

from __future__ import annotations

import logging
import secrets
from collections.abc import Iterator
from contextlib import contextmanager

from app.core.redis import get_redis

logger = logging.getLogger(__name__)


class LockNotAcquired(Exception):
    pass


@contextmanager
def redis_lock(name: str, ttl_seconds: int = 120) -> Iterator[None]:
    """SET NX tabanlı kilit. Alınamazsa LockNotAcquired fırlatır.

    Sahiplik token'ı ile yalnız kendi kilidimizi bırakırız (yanlışlıkla başka
    işlemin yenilediği kilidi silmemek için Lua ile atomik kontrol).
    """
    r = get_redis()
    key = f"lock:{name}"
    token = secrets.token_hex(16)
    acquired = r.set(key, token, nx=True, ex=ttl_seconds)
    if not acquired:
        raise LockNotAcquired(name)
    try:
        yield
    finally:
        release_script = (
            "if redis.call('get', KEYS[1]) == ARGV[1] then "
            "return redis.call('del', KEYS[1]) else return 0 end"
        )
        try:
            r.eval(release_script, 1, key, token)
        except Exception as exc:
            logger.warning(
                "redis_lock_release_failed",
                extra={"lock": name, "error": type(exc).__name__},
            )


def try_acquire(name: str, ttl_seconds: int) -> bool:
    return bool(get_redis().set(f"lock:{name}", "1", nx=True, ex=ttl_seconds))


def idempotency_seen(key: str, ttl_seconds: int = 86400) -> bool:
    """True dönerse bu idempotency key daha önce işlendi demektir."""
    return not bool(get_redis().set(f"idem:{key}", "1", nx=True, ex=ttl_seconds))
