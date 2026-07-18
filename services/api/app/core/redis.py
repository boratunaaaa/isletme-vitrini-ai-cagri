from __future__ import annotations

from functools import lru_cache

import redis
import redis.asyncio as aioredis

from app.config import get_settings


@lru_cache(maxsize=1)
def get_redis() -> redis.Redis:
    return redis.Redis.from_url(get_settings().REDIS_URL, decode_responses=True)


def get_redis_async() -> aioredis.Redis:
    return aioredis.Redis.from_url(get_settings().REDIS_URL, decode_responses=True)
