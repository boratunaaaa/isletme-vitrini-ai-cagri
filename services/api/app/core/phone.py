"""Telefon numarası normalizasyonu ve maskeleme.

Kural: veritabanına yalnız E.164 normalize edilmiş numaranın şifreli hali
girer; düz metin numara log'a, hata mesajına ve API cevabına asla yazılmaz.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import phonenumbers

_CLEAN_RE = re.compile(r"[\s\-\(\)\. ]+")


class PhoneValidationError(ValueError):
    """Numara geçersiz. Mesaj numaranın kendisini içermez."""


@dataclass(frozen=True)
class NormalizedPhone:
    e164: str
    country_code: str
    last_four: str
    is_tr_mobile: bool


def normalize_phone(raw: str, default_region: str = "TR") -> NormalizedPhone:
    if not raw or not raw.strip():
        raise PhoneValidationError("Telefon numarası boş")
    if re.search(r"[A-Za-zÇĞİÖŞÜçğıöşü]", raw):
        raise PhoneValidationError("Telefon numarası geçersiz karakter içeriyor")
    cleaned = _CLEAN_RE.sub("", raw.strip())
    try:
        parsed = phonenumbers.parse(cleaned, default_region)
    except phonenumbers.NumberParseException as exc:
        raise PhoneValidationError("Telefon numarası ayrıştırılamadı") from exc
    if not phonenumbers.is_valid_number(parsed):
        raise PhoneValidationError("Geçersiz telefon numarası")
    e164 = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    number_type = phonenumbers.number_type(parsed)
    is_tr_mobile = parsed.country_code == 90 and number_type in (
        phonenumbers.PhoneNumberType.MOBILE,
        phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE,
    )
    return NormalizedPhone(
        e164=e164,
        country_code=f"+{parsed.country_code}",
        last_four=e164[-4:],
        is_tr_mobile=is_tr_mobile,
    )


def mask_phone(country_code: str, last_four: str) -> str:
    return f"{country_code} ••• •• {last_four[:2]} {last_four[2:]}"
