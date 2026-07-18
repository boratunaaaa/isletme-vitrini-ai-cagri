from __future__ import annotations

import base64

import pytest

from app.config import get_settings
from app.core.crypto import decrypt_pii, encrypt_pii, hash_phone
from app.core.phone import normalize_phone


def test_encrypt_decrypt_roundtrip_and_nondeterministic_ciphertext() -> None:
    phone = "+905321234567"

    first = encrypt_pii(phone)
    second = encrypt_pii(phone)

    assert first != second
    assert decrypt_pii(first) == phone
    assert decrypt_pii(second) == phone


def test_decrypt_fails_with_wrong_key(monkeypatch: pytest.MonkeyPatch) -> None:
    token = encrypt_pii("+905321234567")
    monkeypatch.setenv("PII_ENCRYPTION_KEY", "another-test-pii-secret-minimum-32-chars")
    get_settings.cache_clear()

    with pytest.raises(Exception) as exc:
        decrypt_pii(token)

    assert "+905321234567" not in str(exc.value)
    assert "another-test-pii-secret" not in str(exc.value)


def test_ciphertext_tamper_is_authenticated() -> None:
    raw = bytearray(base64.b64decode(encrypt_pii("+905321234567")))
    raw[-1] ^= 1
    tampered = base64.b64encode(raw).decode("ascii")

    with pytest.raises(Exception) as exc:
        decrypt_pii(tampered)

    assert "+905321234567" not in str(exc.value)


def test_empty_plaintext_and_short_secret_fail_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError):
        encrypt_pii("")

    monkeypatch.setenv("PII_ENCRYPTION_KEY", "short")
    get_settings.cache_clear()

    with pytest.raises(ValueError) as exc:
        encrypt_pii("+905321234567")

    assert "short" not in str(exc.value)


def test_phone_hash_is_deterministic_peppered_and_not_reversible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = hash_phone(normalize_phone("0532 123 45 67").e164)
    second = hash_phone(normalize_phone("+90 532 123 45 67").e164)
    other = hash_phone("+905551112233")

    assert first == second
    assert first != other
    assert "+905321234567" not in first
    assert "5321234567" not in first

    monkeypatch.setenv("PHONE_HASH_PEPPER", "different-phone-pepper-minimum-32-chars")
    get_settings.cache_clear()
    assert hash_phone("+905321234567") != first
