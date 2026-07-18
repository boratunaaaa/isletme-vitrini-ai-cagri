from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.redis import get_redis
from app.deps import InternalServiceContext, get_db, require_internal_service
from app.models.content import AgentPromptVersion
from app.models.pricing import ProviderPricing

router = APIRouter()


@router.get("/health", include_in_schema=False)
def internal_health(
    db: Session = Depends(get_db),
    ctx: InternalServiceContext = Depends(require_internal_service),
) -> dict:
    database = "ok"
    redis = "ok"
    try:
        db.execute(text("select 1"))
    except Exception:
        database = "error"
    try:
        if not get_redis().ping():
            redis = "error"
    except Exception:
        redis = "error"
    pricing_count = int(db.scalar(select(func.count(ProviderPricing.id))) or 0)
    active_prompt = db.scalar(
        select(AgentPromptVersion.id).where(AgentPromptVersion.is_active.is_(True)).limit(1)
    )
    settings = get_settings()
    return {
        "status": "ok" if database == "ok" and redis == "ok" else "degraded",
        "service_name": ctx.service_name,
        "checks": {
            "database": database,
            "redis": redis,
            "pricing_seed": "ok" if pricing_count else "missing",
            "active_prompt": "ok" if active_prompt else "missing",
            "internal_auth_configured": bool(settings.INTERNAL_SERVICE_TOKEN),
        },
    }
