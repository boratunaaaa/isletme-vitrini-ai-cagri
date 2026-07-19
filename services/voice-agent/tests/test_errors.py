"""`classify_sip_status` RFC 3261 eşleme testleri.

PHASE_8_RESILIENCE_REPORT.md: `test_job_handler.py` yalnız `busy` (486),
`no_answer` (480), `rejected` (603) durumlarını `SIPParticipantError`
üzerinden dolaylı test ediyordu. Operasyonel açıdan en kritik durumlar olan
trunk hatası (Netgsm 5xx) ve SIP kimlik doğrulama hatası (401/403/407) hiç
doğrudan test edilmiyordu.
"""

from __future__ import annotations

import pytest

from agent.errors import SIP_FAILURE_REASONS, SIPParticipantError, classify_sip_status


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (None, "unknown_sip_failure"),
        (486, "busy"),
        (480, "no_answer"),
        (408, "no_answer"),
        (603, "rejected"),
        (487, "cancelled"),
        (401, "authentication_error"),
        (403, "authentication_error"),
        (407, "authentication_error"),
        (500, "trunk_error"),
        (503, "trunk_error"),
        (599, "trunk_error"),
        (301, "redirect_unsupported"),
        (302, "redirect_unsupported"),
        (399, "redirect_unsupported"),
        (999, "unknown_sip_failure"),
        (200, "unknown_sip_failure"),
    ],
)
def test_classify_sip_status(status_code: int | None, expected: str) -> None:
    assert classify_sip_status(status_code) == expected


def test_all_classification_outputs_are_declared_in_sip_failure_reasons() -> None:
    """`classify_sip_status`'ın döndürebileceği her değer `SIP_FAILURE_REASONS`
    kümesinde tanımlı olmalı — aksi halde `models.py`'deki enum/şema kontratı
    ile sessizce senkron dışı kalabilir."""
    sample_codes = [None, 100, 200, 301, 399, 401, 403, 407, 408, 480, 486, 487, 500, 599, 603, 999]
    for code in sample_codes:
        assert classify_sip_status(code) in SIP_FAILURE_REASONS


def test_sip_participant_error_derives_reason_from_status_code() -> None:
    error = SIPParticipantError("trunk unreachable", sip_status_code=503)
    assert error.reason == "trunk_error"

    error = SIPParticipantError("auth rejected", sip_status_code=401)
    assert error.reason == "authentication_error"
