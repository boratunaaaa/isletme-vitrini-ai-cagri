from __future__ import annotations

from sqlalchemy import func, select


def test_seed_is_idempotent_and_uses_realtime_models(clean_seed_rows, db_session):
    from app.config import get_settings
    from app.models.content import AgentPromptVersion, KnowledgeBaseEntry
    from app.models.pricing import ProviderPricing
    from app.seed import seed_all

    settings = get_settings()
    first = seed_all()
    second = seed_all()

    assert first["pricing"] == 2
    assert first["kb"] >= 5
    assert first["prompts"] == 1
    assert second == {"pricing": 0, "settings": 0, "kb": 0, "prompts": 0}

    models = set(db_session.scalars(select(ProviderPricing.model)).all())
    assert settings.OPENAI_REALTIME_DEFAULT_MODEL in models
    assert settings.OPENAI_REALTIME_PREMIUM_MODEL in models

    assert db_session.scalar(select(func.count(KnowledgeBaseEntry.id))) >= 5
    assert db_session.scalar(select(func.count(AgentPromptVersion.id))) == 1
    assert db_session.scalar(
        select(func.count(AgentPromptVersion.id)).where(AgentPromptVersion.is_active.is_(True))
    ) == 1
