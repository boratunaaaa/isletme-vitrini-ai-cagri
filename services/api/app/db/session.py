from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    settings = get_settings()
    return create_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        pool_size=5,
        # NOT (PHASE_8_RESILIENCE_REPORT.md): `pool_pre_ping` yalnız ÖLÜ bir
        # bağlantıyı checkout sırasında tespit eder — TAKILI/yavaş bir
        # sorguyu sınırlamaz. `statement_timeout` (psycopg `options` GUC'u
        # ile bağlantı seviyesinde ayarlanır) her sorguyu bağımsız olarak
        # sınırlar; hem web isteklerini hem Celery görevlerini korur.
        connect_args={"options": f"-c statement_timeout={settings.DB_STATEMENT_TIMEOUT_MS}"},
    )


@lru_cache(maxsize=1)
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Celery task'ları ve script'ler için transaction scope'u."""
    db = get_sessionmaker()()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
