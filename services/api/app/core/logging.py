"""Yapılandırılmış JSON loglama + PII redaksiyonu.

Her log satırı JSON'dur; request_id ve call_id contextvar'lardan eklenir.
RedactionFilter, log mesajlarındaki telefon benzeri desenleri maskeler —
telefon numarası hiçbir logda düz metin görünmez.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
call_id_var: ContextVar[str | None] = ContextVar("call_id", default=None)

_PHONE_PATTERNS = [
    re.compile(r"\+90[\s\-]?5\d{2}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}"),
    re.compile(r"\+\d{10,14}"),
    re.compile(r"\b0?5\d{9}\b"),
]
_SECRET_KEY_RE = re.compile(
    r"(password|secret|token|api[_-]?key|authorization)\s*[=:]\s*\S+", re.IGNORECASE
)


def redact(text: str) -> str:
    for pattern in _PHONE_PATTERNS:
        text = pattern.sub("[REDACTED_PHONE]", text)
    text = _SECRET_KEY_RE.sub(
        lambda m: m.group(0).split(m.group(0)[len(m.group(1))], 1)[0] + "=[REDACTED]",
        text,
    )
    return text


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            return True
        redacted = redact(message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if request_id := request_id_var.get():
            payload["request_id"] = request_id
        if call_id := call_id_var.get():
            payload["call_id"] = call_id
        if record.exc_info and record.exc_info[0] is not None:
            payload["exception"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactionFilter())
    root.addHandler(handler)
    for noisy in ("uvicorn.access", "httpx"):
        logging.getLogger(noisy).setLevel("WARNING")
