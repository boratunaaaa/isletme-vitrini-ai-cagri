"""`/api/leads/export` uçtan uca CSV formül enjeksiyonu regresyon testi.

PHASE_9_SECURITY_REPORT.md: bkz. tests/unit/test_csv_export_safety.py için
birim seviyesi kapsam. Bu test, gerçek HTTP endpoint'in ürettiği CSV
gövdesinde de tetikleyici karakterlerin nötrlendiğini doğrular.
"""

from __future__ import annotations

import csv
import io

from app.core.crypto import encrypt_pii, hash_phone
from app.core.phone import normalize_phone
from app.models.lead import Lead


def test_export_neutralizes_formula_injection_in_business_name(
    client, login_as, db_session
) -> None:
    normalized = normalize_phone("0532 999 88 77")
    lead = Lead(
        business_name='=HYPERLINK("http://evil.test/?x","click")',
        sector="Güzellik",
        city="İstanbul",
        phone_ciphertext=encrypt_pii(normalized.e164),
        phone_hash=hash_phone(normalized.e164),
        phone_last_four=normalized.last_four,
        phone_country_code=normalized.country_code,
    )
    db_session.add(lead)
    db_session.commit()

    headers = login_as(role="owner")
    response = client.post("/api/leads/export", headers=headers)

    assert response.status_code == 200
    reader = csv.reader(io.StringIO(response.text))
    rows = list(reader)
    business_name_cell = next(row[0] for row in rows[1:] if row[0].endswith('click")'))
    assert business_name_cell.startswith("'=")


def test_export_is_rate_limited_per_user(client, login_as) -> None:
    """PHASE_9_SECURITY_REPORT.md: tekrarlanan tam-veritabanı export'larını
    zorlaştırmak için kullanıcı-başına 5/60s limit uygulanır."""
    headers = login_as(role="owner")

    for _ in range(5):
        response = client.post("/api/leads/export", headers=headers)
        assert response.status_code == 200

    limited = client.post("/api/leads/export", headers=headers)
    assert limited.status_code == 429
