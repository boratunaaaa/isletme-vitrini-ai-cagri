"""Bakım görevleri: transcript retention temizliği."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import update
from sqlalchemy.engine import CursorResult

from app.config import get_settings
from app.db.session import session_scope
from app.models.call import Call
from app.services.settings_service import get_decimal_setting
from app.worker import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.maintenance_tasks.retention_cleanup")
def retention_cleanup() -> None:
    """TRANSCRIPT_RETENTION_DAYS'ten eski transkriptleri siler (satır kalır,
    yalnız transcript alanı NULL olur). Panelden gün değeri override edilebilir."""
    settings = get_settings()
    with session_scope() as db:
        days = int(
            get_decimal_setting(
                db,
                "calls",
                "transcript_retention_days",
                Decimal(settings.TRANSCRIPT_RETENTION_DAYS),
            )
        )
        if days <= 0:
            return
        cutoff = datetime.now(UTC) - timedelta(days=days)
        result = db.execute(
            update(Call)
            .where(Call.ended_at.is_not(None), Call.ended_at < cutoff, Call.transcript.is_not(None))
            .values(transcript=None)
        )
        rowcount = result.rowcount if isinstance(result, CursorResult) else 0
        logger.info("Retention: %s çağrının transkripti temizlendi", rowcount)
