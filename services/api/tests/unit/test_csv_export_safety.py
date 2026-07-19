"""CSV/Excel formül enjeksiyonu (CWE-1236) regresyon testleri.

PHASE_9_SECURITY_REPORT.md: `/api/leads/export` kullanıcı/import kontrollü
alanları (business_name, sector, city, district, website, demo_link) hiçbir
sanitizasyon olmadan CSV hücresine yazıyordu — `=HYPERLINK(...)` gibi bir
`business_name` Excel/Sheets'te formül olarak çalışabilirdi.
"""

from __future__ import annotations

import pytest

from app.api.routes.leads import _csv_safe


@pytest.mark.parametrize(
    "raw",
    [
        '=HYPERLINK("http://evil.test/?x","click")',
        "+1+1",
        "-2+3",
        "@SUM(1,2)",
        "=cmd|'/c calc'!A1",
    ],
)
def test_formula_trigger_prefixed_with_quote(raw: str) -> None:
    safe = _csv_safe(raw)
    assert safe.startswith("'")
    assert safe[1:] == raw


@pytest.mark.parametrize("raw", ["Normal İşletme", "", "İzmir Kuaför Salonu", "3 Yıldız"])
def test_normal_values_are_unchanged(raw: str) -> None:
    assert _csv_safe(raw) == raw
