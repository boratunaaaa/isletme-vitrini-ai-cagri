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
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# NOT (PHASE_8_RESILIENCE_REPORT.md): eski `_SECRET_KEY_RE` yalnız `\S+`
# kullandığı için "Authorization: Bearer <token>" biçiminde `Bearer` kelimesini
# yutup asıl token'ı DIŞARIDA bırakıyordu (boşluk `\S+`'i durduruyor). Ayrıca
# e-posta ve OpenAI `sk-...` anahtarlarını hiç yakalamıyordu. Voice-agent'ın
# zaten test edilmiş `agent/redaction.py` desenleriyle tutarlı hale getirildi.
_BEARER_RE = re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE)
_OPENAI_KEY_RE = re.compile(r"sk-[A-Za-z0-9_\-]{16,}")
_KV_SECRET_RE = re.compile(r"(?i)\b(token|secret|api[_-]?key|password)\s*[=:]\s*[^\s&,;]+")


def redact(text: str) -> str:
    for pattern in _PHONE_PATTERNS:
        text = pattern.sub("[REDACTED_PHONE]", text)
    text = _BEARER_RE.sub("Bearer [REDACTED]", text)
    text = _OPENAI_KEY_RE.sub("[REDACTED_OPENAI_KEY]", text)
    text = _KV_SECRET_RE.sub(lambda m: f"{m.group(1)}=[REDACTED]", text)
    text = _EMAIL_RE.sub("[REDACTED_EMAIL]", text)
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
