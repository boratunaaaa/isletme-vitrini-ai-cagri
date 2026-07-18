from __future__ import annotations

import pytest

from app.core.phone import PhoneValidationError, normalize_phone


@pytest.mark.parametrize(
    "raw",
    [
        "0532 123 45 67",
        "5321234567",
        "905321234567",
        "+90 532 123 45 67",
        "(0532) 123-45-67",
        "  0532 123 45 67  ",
    ],
)
def test_turkish_phone_formats_normalize_to_e164(raw: str) -> None:
    normalized = normalize_phone(raw)

    assert normalized.e164 == "+905321234567"
    assert normalized.country_code == "+90"
    assert normalized.last_four == "4567"
    assert normalized.is_tr_mobile is True


@pytest.mark.parametrize("raw", ["123", "053212345678901", "0532abc4567", "", "   "])
def test_invalid_phone_values_raise_controlled_error(raw: str) -> None:
    with pytest.raises(PhoneValidationError) as exc:
        normalize_phone(raw)

    if raw.strip():
        assert raw.strip() not in str(exc.value)


def test_non_turkish_valid_number_is_currently_accepted_but_not_tr_mobile() -> None:
    normalized = normalize_phone("+1 415 555 2671")

    assert normalized.e164 == "+14155552671"
    assert normalized.is_tr_mobile is False
