"""Log redaksiyon regresyon testleri.

CLAUDE_AUDIT_PHASE_4.md KRİTİK-2: `logger.exception()`/`exc_info=True` ile
basılan traceback'ler eski `RedactionFilter` tarafından hiç kapsanmıyordu;
canlı repro ile telefon ve Bearer token'ın düz metin sızdığı kanıtlanmıştı.

Bu testler yalnız `RedactionFilter` NESNESİNİ değil, GERÇEK handler +
formatter çıktısını (yani kullanıcının/log toplama sisteminin göreceği nihai
metni) doğrular — `configure_logging()` ile kurulan tam pipeline üzerinden.
"""

from __future__ import annotations

import io
import logging

import httpx
import pytest

from agent.logging import configure_logging


@pytest.fixture()
def captured_log() -> tuple[logging.Logger, io.StringIO]:
    """Her testte temiz bir root logger + capture stream kurar."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    configure_logging("DEBUG")
    stream = io.StringIO()
    for handler in root.handlers:
        handler.stream = stream  # type: ignore[attr-defined]
    logger = logging.getLogger("agent.test.redaction")
    yield logger, stream
    for handler in list(root.handlers):
        root.removeHandler(handler)


def test_phone_in_valueerror_traceback_is_redacted(
    captured_log: tuple[logging.Logger, io.StringIO],
) -> None:
    logger, stream = captured_log
    try:
        raise ValueError("dial-plan phone_e164=+905551112233 could not be parsed")
    except ValueError:
        logger.exception("Dial plan parse failed")

    output = stream.getvalue()
    assert "+905551112233" not in output
    assert "[REDACTED_PHONE]" in output


def test_bearer_token_in_exception_traceback_is_redacted(
    captured_log: tuple[logging.Logger, io.StringIO],
) -> None:
    logger, stream = captured_log
    try:
        raise RuntimeError(
            "internal API rejected request with header Authorization: Bearer sk-live-abcdef123456"
        )
    except RuntimeError:
        logger.exception("Internal API call failed")

    output = stream.getvalue()
    assert "sk-live-abcdef123456" not in output
    assert "[REDACTED]" in output


def test_nested_dict_with_openai_key_is_redacted_via_extra(
    captured_log: tuple[logging.Logger, io.StringIO],
) -> None:
    logger, stream = captured_log
    payload = {
        "call_id": "abc-123",
        "config": {"openai_api_key": "sk-abcdefghijklmnopqrstuvwx", "nested": {"token": "t0p"}},
    }
    logger.warning("Bootstrap payload: %s", payload)

    output = stream.getvalue()
    assert "sk-abcdefghijklmnopqrstuvwx" not in output
    assert "t0p" not in output or "[REDACTED]" in output


def test_url_query_token_is_redacted(
    captured_log: tuple[logging.Logger, io.StringIO],
) -> None:
    logger, stream = captured_log
    try:
        raise RuntimeError(
            "GET http://internal.test/api/internal/v1/calls/1?token=abcdef123456 -> 500"
        )
    except RuntimeError:
        logger.exception("Request failed")

    output = stream.getvalue()
    assert "abcdef123456" not in output


def test_httpx_error_traceback_is_redacted(
    captured_log: tuple[logging.Logger, io.StringIO],
) -> None:
    logger, stream = captured_log
    request = httpx.Request(
        "POST",
        "http://internal.test/api/internal/v1/calls/1/events",
        headers={"Authorization": "Bearer sk-internal-secret-value-000"},
    )
    try:
        raise httpx.TimeoutException("timed out contacting +905551112233 handler", request=request)
    except httpx.TimeoutException:
        logger.exception("Lifecycle event delivery failed")

    output = stream.getvalue()
    assert "sk-internal-secret-value-000" not in output
    assert "+905551112233" not in output


def test_transcript_containing_exception_is_redacted(
    captured_log: tuple[logging.Logger, io.StringIO],
) -> None:
    logger, stream = captured_log
    try:
        raise ValueError(
            "Transcript validation failed for turn text='Telefonum +905551112233, "
            "e-postam ayse@example.com'"
        )
    except ValueError:
        logger.exception("Transcript turn rejected")

    output = stream.getvalue()
    assert "+905551112233" not in output
    assert "ayse@example.com" not in output
    assert "[REDACTED_PHONE]" in output
    assert "[REDACTED_EMAIL]" in output


def test_exc_info_true_kwarg_is_also_redacted(
    captured_log: tuple[logging.Logger, io.StringIO],
) -> None:
    logger, stream = captured_log
    try:
        raise RuntimeError("failed for +905551112233")
    except RuntimeError:
        logger.error("Operation failed", exc_info=True)

    output = stream.getvalue()
    assert "+905551112233" not in output


def test_plain_message_without_exception_still_redacted(
    captured_log: tuple[logging.Logger, io.StringIO],
) -> None:
    logger, stream = captured_log
    logger.info("Calling +905551112233 with token Bearer abcdef123456")

    output = stream.getvalue()
    assert "+905551112233" not in output
    assert "abcdef123456" not in output
