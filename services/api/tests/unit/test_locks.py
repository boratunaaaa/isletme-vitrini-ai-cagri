from __future__ import annotations

import time

import pytest

from app.core.locks import LockNotAcquired, redis_lock


def test_redis_lock_acquire_conflict_and_ttl(redis_client) -> None:
    with redis_lock("phase2-lock", ttl_seconds=1):
        assert redis_client.get("lock:phase2-lock") is not None
        with pytest.raises(LockNotAcquired), redis_lock("phase2-lock", ttl_seconds=1):
            pass
    assert redis_client.get("lock:phase2-lock") is None

    with redis_lock("phase2-lock-ttl", ttl_seconds=1):
        pass
    time.sleep(1.1)
    with redis_lock("phase2-lock-ttl", ttl_seconds=1):
        assert redis_client.get("lock:phase2-lock-ttl") is not None


def test_lock_release_only_deletes_own_token(redis_client) -> None:
    redis_client.set("lock:owned", "other-token", ex=30)
    script = (
        "if redis.call('get', KEYS[1]) == ARGV[1] then "
        "return redis.call('del', KEYS[1]) else return 0 end"
    )

    assert redis_client.eval(script, 1, "lock:owned", "wrong-token") == 0
    assert redis_client.get("lock:owned") is not None


def test_lock_release_errors_are_logged(monkeypatch: pytest.MonkeyPatch) -> None:
    warnings: list[tuple[str, dict]] = []

    class BrokenRedis:
        def set(self, *args, **kwargs):
            return True

        def eval(self, *args, **kwargs):
            raise RuntimeError("redis down")

    monkeypatch.setattr("app.core.locks.get_redis", lambda: BrokenRedis())
    monkeypatch.setattr(
        "app.core.locks.logger.warning",
        lambda message, **kwargs: warnings.append((message, kwargs)),
    )

    with redis_lock("broken-release", ttl_seconds=1):
        pass

    assert warnings == [
        (
            "redis_lock_release_failed",
            {"extra": {"lock": "broken-release", "error": "RuntimeError"}},
        )
    ]
