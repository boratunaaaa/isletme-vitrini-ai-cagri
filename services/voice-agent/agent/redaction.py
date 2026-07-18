from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

SECRET_KEYS = {
    "authorization",
    "api_key",
    "api_secret",
    "openai_api_key",
    "livekit_api_secret",
    "internal_service_token",
    "password",
    "token",
    "secret",
    "sip_password",
}

_PHONE_RE = re.compile(r"\+?90?5\d{9}|\+\d{8,15}")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_BEARER_RE = re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE)
_OPENAI_KEY_RE = re.compile(r"sk-[A-Za-z0-9_\-]{16,}")
# query-string veya key=value biçiminde token/secret/api_key/password değerleri.
# "authorization" bilerek dışarıda bırakıldı: gerçek değeri neredeyse her zaman
# "Bearer ..." biçimindedir ve bu zaten `_BEARER_RE` tarafından tam olarak
# temizlenir; ikisini birden eşleştirmek aynı token'ı iki kez (çakışan
# aralıklarla) redakte edip okunabilirliği bozmadan hiçbir güvenlik faydası
# sağlamaz.
_KV_SECRET_RE = re.compile(r"(?i)\b(token|secret|api[_-]?key|password)\s*[=:]\s*[^\s&,;]+")


def redact_text(value: str) -> str:
    """Bilinen tüm hassas desenleri metinden temizler.

    Bu fonksiyon hem yapılandırılmış (dict/args) hem serbest metin (exception
    mesajı, traceback, HTTP response gövdesi) girdiler için TEK doğru kaynaktır;
    loglama katmanı burada üretilen çıktıyı asla atlamamalı.
    """
    redacted = _BEARER_RE.sub("Bearer [REDACTED]", value)
    redacted = _OPENAI_KEY_RE.sub("[REDACTED_OPENAI_KEY]", redacted)
    redacted = _KV_SECRET_RE.sub(lambda m: f"{m.group(1)}=[REDACTED]", redacted)
    redacted = _PHONE_RE.sub("[REDACTED_PHONE]", redacted)
    redacted = _EMAIL_RE.sub("[REDACTED_EMAIL]", redacted)
    return redacted


def safe_value(value: Any) -> Any:
    """Herhangi bir Python değerini loglamaya güvenli hale getirir.

    str/Mapping/Sequence dışındaki tipler (ör. Exception, pydantic modeli,
    dataclass) artık olduğu gibi bırakılmıyor; `str(value)` üzerinden
    redakte edilmiş bir metne çevriliyor. Bilinmeyen bir tipi "güvenli"
    sayıp aynen döndürmek yerine varsayılan olarak redakte etmek, yeni bir
    log call-site'ının bu fonksiyonu atlayarak sızıntı yaratmasını önler.
    """
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text.lower() in SECRET_KEYS or any(k in key_text.lower() for k in SECRET_KEYS):
                cleaned[key_text] = "[REDACTED]"
            else:
                cleaned[key_text] = safe_value(item)
        return cleaned
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray | str):
        return [safe_value(item) for item in value]
    if isinstance(value, int | float | bool) or value is None:
        return value
    # Exception, pydantic model, dataclass, vb. — fail-safe: metne çevirip redakte et
    return redact_text(str(value))


def safe_error_message(exc: BaseException) -> str:
    return redact_text(str(exc))
