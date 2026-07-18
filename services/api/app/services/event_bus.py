"""Canlı olay yayını: Redis pub/sub → SSE.

publish_event senkron çalışır (Celery ve request handler'lardan çağrılabilir).
SSE endpoint'i async subscriber kullanır (app/api/routes/live.py).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.core.redis import get_redis

logger = logging.getLogger(__name__)

CHANNEL = "ivac:events"
MAX_PAYLOAD_BYTES = 16_384


def publish_event(event: dict[str, Any]) -> None:
    try:
        payload = json.dumps(event, ensure_ascii=False, default=str)
        if len(payload.encode()) > MAX_PAYLOAD_BYTES:
            event = {k: event[k] for k in ("type", "call_id", "ts") if k in event}
            event["truncated"] = True
            payload = json.dumps(event, ensure_ascii=False, default=str)
        get_redis().publish(CHANNEL, payload)
    except Exception:  # canlı yayın best-effort'tur; ana akışı asla düşürmez
        logger.warning("Event yayınlanamadı", exc_info=True)
