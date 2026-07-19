"""Log redaksiyon regresyon testleri.

PHASE_8_RESILIENCE_REPORT.md: eski `_SECRET_KEY_RE` yalnız `\\S+` kullandığı
için "Authorization: Bearer <token>" biçiminde `Bearer` kelimesini yutup asıl
token'ı DIŞARIDA bırakıyordu (bir sonraki boşluk `\\S+`'i durduruyordu) ve
e-posta/OpenAI `sk-...` anahtarlarını hiç yakalamıyordu. Bu testler yalnız
`redact()` fonksiyonunu değil, GERÇEK handler + `JsonFormatter` çıktısını
(yani log toplama sisteminin göreceği nihai metni) `configure_logging()` ile
kurulan tam pipeline üzerinden doğrular.
"""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Iterator

import pytest

from app.core.logging import configure_logging, redact


@pytest.fixture()
def captured_log() -> Iterator[tuple[logging.Logger, io.StringIO]]:
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    configure_logging("DEBUG")
    stream = io.StringIO()
    for handler in root.handlers:
        handler.stream = stream  # type: ignore[attr-defined]
    logger = logging.getLogger("app.test.redaction")
    yield logger, stream
    for handler in list(root.handlers):
        root.removeHandler(handler)


def test_bearer_token_in_message_is_fully_redacted() -> None:
    text = redact("Authorization: Bearer sk-abcd1234567890ABCDEFGHIJ token=abc123")
    assert "sk-abcd1234567890ABCDEFGHIJ" not in text
    assert "abc123" not in text


def test_openai_style_key_is_redacted() -> None:
    text = redact("startup failed with key sk-proj-ABCDEFGHIJKLMNOPQRST")
    assert "sk-proj-ABCDEFGHIJKLMNOPQRST" not in text
    assert "[REDACTED_OPENAI_KEY]" in text


def test_email_is_redacted() -> None:
    text = redact("contact: someone@example.com")
    assert "someone@example.com" not in text
    assert "[REDACTED_EMAIL]" in text


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
    payload = json.loads(output.strip().splitlines()[-1])
    assert "sk-live-abcdef123456" not in payload["exception"]


def test_phone_in_message_is_redacted(
    captured_log: tuple[logging.Logger, io.StringIO],
) -> None:
    logger, stream = captured_log
    logger.info("Calling +905551112233 with token Bearer abcdef123456")

    output = stream.getvalue()
    assert "+905551112233" not in output
    assert "abcdef123456" not in output


def test_plain_secret_kv_pair_is_redacted() -> None:
    text = redact("password=hunter2secretvalue")
    assert "hunter2secretvalue" not in text
    assert "password=[REDACTED]" in text
