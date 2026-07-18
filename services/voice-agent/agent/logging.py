"""PII-safe loglama.

İki katmanlı redaksiyon:
1. `RedactionFilter`: `record.msg`/`record.args`'ı formatlamadan ÖNCE temizler
   (yapılandırılmış tüketiciler — ör. ileride eklenebilecek bir JSON handler —
   ham `record.args`'ı okursa bile güvenli olsun diye).
2. `RedactingFormatter`: `logging.Formatter.format()`'ın ürettiği TAM string'i
   (mesaj + varsa traceback/exc_info) son adımda tekrar `redact_text()`'ten
   geçirir. `logger.exception(...)`/`exc_info=True` ile basılan traceback'ler
   filtre katmanına hiç uğramaz (Formatter, Filter'dan SONRA çalışır ve
   traceback'i kendi `formatException()` çağrısıyla ayrıca üretir) — bu yüzden
   asıl güvenlik garantisi bu katmandadır, Filter yalnız savunma derinliğidir.
"""

from __future__ import annotations

import logging
from typing import Any

from agent.redaction import redact_text, safe_value


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_text(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = safe_value(record.args)
            else:
                record.args = tuple(safe_value(arg) for arg in record.args)
        return True


class RedactingFormatter(logging.Formatter):
    """Nihai log satırını (mesaj + traceback dahil) redakte eder."""

    def format(self, record: logging.LogRecord) -> str:
        formatted = super().format(record)
        return redact_text(formatted)

    def formatException(self, ei: Any) -> str:  # noqa: N802 (logging API imzası)
        return redact_text(super().formatException(ei))

    def formatStack(self, stack_info: str) -> str:  # noqa: N802
        return redact_text(super().formatStack(stack_info))


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    formatter = RedactingFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    for existing_handler in root.handlers:
        # Formatter'ı her zaman redakte eden sürüme zorla — dışarıdan farklı bir
        # formatter eklenmiş olsa bile traceback sızıntısı garantisi kaybolmasın.
        if not isinstance(existing_handler.formatter, RedactingFormatter):
            existing_handler.setFormatter(formatter)
        if not any(isinstance(f, RedactionFilter) for f in existing_handler.filters):
            existing_handler.addFilter(RedactionFilter())


def safe_extra(**values: Any) -> dict[str, Any]:
    return {"extra": safe_value(values)}
