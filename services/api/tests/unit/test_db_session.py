"""`app/db/session.py` motor yapılandırma testleri.

PHASE_8_RESILIENCE_REPORT.md: önceden hiçbir statement/connect timeout
yoktu — `pool_pre_ping` yalnız ölü bir bağlantıyı checkout sırasında tespit
eder, takılı/yavaş bir sorguyu sınırlamaz. Bu test, `DB_STATEMENT_TIMEOUT_MS`
ayarının gerçek Postgres bağlantısına GUC olarak uygulandığını doğrular.
"""

from __future__ import annotations

from sqlalchemy import text

from app.db.session import get_engine


def test_statement_timeout_guc_is_applied_on_connection(migrated_db) -> None:
    with get_engine().connect() as conn:
        (value,) = conn.execute(text("SHOW statement_timeout")).one()
    assert value == "30s"
