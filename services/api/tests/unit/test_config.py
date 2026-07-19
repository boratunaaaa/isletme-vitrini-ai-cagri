"""`Settings.validate_runtime()` production fail-fast davranışı.

CODEX_AUDIT_PHASE_6.md YÜKSEK-3 regresyon testleri: `.env.production.example`
placeholder'ları (`REPLACE_ME`) veya kısa/zayıf değerler production'da
sessizce kabul EDİLMEMELİ.
"""

import pytest

from app.config import Settings

_STRONG_SECRET = "a" * 40


def _production_settings(**overrides: str) -> Settings:
    fields: dict[str, object] = {
        "APP_ENV": "production",
        "APP_URL": "https://panel.example.com",
        "DATABASE_URL": "postgresql+psycopg://user:pass@host:5432/db",
        "JWT_SECRET": _STRONG_SECRET,
        "COOKIE_SECRET": _STRONG_SECRET,
        "PII_ENCRYPTION_KEY": _STRONG_SECRET,
        "PHONE_HASH_PEPPER": _STRONG_SECRET,
        "INTERNAL_SERVICE_TOKEN": _STRONG_SECRET,
    }
    fields.update(overrides)
    # `Settings(**fields)` `**dict` genişletmesiyle mypy'nin TÜM alan
    # tiplerine (int/bool dahil) karşı birleştirme yapmasına yol açıyordu
    # (repo genelinde pydantic mypy plugin YAPILANDIRILMAMIŞ — bunu eklemek
    # bu düzeltmenin kapsamı dışında bir infra değişikliği olurdu).
    # `model_validate` aynı doğrulamayı çalıştırır, tip açısından güvenlidir.
    return Settings.model_validate(fields)


def test_strong_secrets_pass_in_production() -> None:
    settings = _production_settings()
    settings.validate_runtime()  # raise etmemeli


@pytest.mark.parametrize(
    "field",
    [
        "JWT_SECRET",
        "COOKIE_SECRET",
        "PII_ENCRYPTION_KEY",
        "PHONE_HASH_PEPPER",
        "INTERNAL_SERVICE_TOKEN",
    ],
)
def test_replace_me_placeholder_rejected_in_production(field: str) -> None:
    settings = _production_settings(**{field: "REPLACE_ME"})
    with pytest.raises(RuntimeError, match="placeholder"):
        settings.validate_runtime()


def test_short_secret_rejected_in_production() -> None:
    settings = _production_settings(JWT_SECRET="short")
    with pytest.raises(RuntimeError, match="placeholder"):
        settings.validate_runtime()


def test_exact_example_marker_rejected_in_production() -> None:
    """Yalnız GERÇEKTEN template olarak kullanılan tam `example` değeri
    reddedilmeli — substring DEĞİL (bkz. CODEX_FINAL_AUDIT_PHASE_6.md ORTA-2)."""
    settings = _production_settings(COOKIE_SECRET="example")
    with pytest.raises(RuntimeError, match="placeholder"):
        settings.validate_runtime()


def test_exact_dummy_marker_rejected_in_production() -> None:
    settings = _production_settings(COOKIE_SECRET="dummy")
    with pytest.raises(RuntimeError, match="placeholder"):
        settings.validate_runtime()


def test_strong_secret_containing_example_substring_is_accepted_in_production() -> None:
    """CODEX_FINAL_AUDIT_PHASE_6.md ORTA-2 regresyonu: önceden `marker in
    canonical` (substring) kullanılıyordu, bu yüzden içinde yalnızca
    "example" GEÇEN güçlü/uzun bir secret yanlışlıkla reddediliyordu."""
    settings = _production_settings(COOKIE_SECRET="this-is-just-an-example-value-not-real")
    settings.validate_runtime()  # raise ETMEMELİ


def test_strong_secret_containing_dummy_substring_is_accepted_in_production() -> None:
    settings = _production_settings(PII_ENCRYPTION_KEY="mydummyvalue-a1b2c3d4e5f6g7h8i9j0")
    settings.validate_runtime()  # raise ETMEMELİ


def test_prod_example_prefixed_strong_secret_is_accepted_in_production() -> None:
    settings = _production_settings(
        PHONE_HASH_PEPPER="prod-example-9f8e7d6c5b4a3210fedcba9876543210"
    )
    settings.validate_runtime()  # raise ETMEMELİ


def test_example_in_middle_of_strong_secret_is_accepted_in_production() -> None:
    settings = _production_settings(JWT_SECRET="a1b2c3-example-d4e5f6g7h8i9j0k1l2m3n4o5")
    settings.validate_runtime()  # raise ETMEMELİ


def test_dummy_in_middle_of_strong_secret_is_accepted_in_production() -> None:
    settings = _production_settings(JWT_SECRET="a1b2c3-dummy-d4e5f6g7h8i9j0k1l2m3n4o5")
    settings.validate_runtime()  # raise ETMEMELİ


# ── CODEX_REAUDIT_PHASE_6.md YÜKSEK-3: whitespace-only secret bypass ────────
# 20+ boşluk karakterinden oluşan bir JWT_SECRET, `validate_runtime()`'ın
# önceki (strip'siz) hali altında production'da PASS veriyordu — `not value`
# whitespace-only bir string için False döner, `len(value)` de eşiği geçer.
# Aşağıdaki tüm varyantlar artık `missing`/`placeholder` olarak reddedilmeli.

_WHITESPACE_ONLY_VARIANTS = {
    "empty_string": "",
    "single_space": " ",
    "twenty_spaces": " " * 20,
    "tabs": "\t\t\t\t\t",
    "newlines": "\n\n\n\n\n",
    "mixed_whitespace": " \t\n \t\n \t\n \t\n \t\n",
    "unicode_nbsp": " " * 20,
}


@pytest.mark.parametrize(
    "value", _WHITESPACE_ONLY_VARIANTS.values(), ids=_WHITESPACE_ONLY_VARIANTS.keys()
)
def test_whitespace_only_secret_treated_as_missing_in_production(value: str) -> None:
    """Whitespace-only değer strip sonrası boş sayılır -> 'eksik' hatası (placeholder DEĞİL)."""
    settings = _production_settings(JWT_SECRET=value)
    with pytest.raises(RuntimeError, match="eksik zorunlu secret"):
        settings.validate_runtime()


_PLACEHOLDER_VARIANTS = {
    "padded_replace_me": "   REPLACE_ME   ",
    "lowercase_replace_me": "replace_me",
    "hyphenated_padded_replace_me": " replace-me ",
    "upper_change_me_underscore": "CHANGE_ME",
    "lowercase_changeme": "changeme",
    "your_secret_here": "your-secret-here",
}


@pytest.mark.parametrize("value", _PLACEHOLDER_VARIANTS.values(), ids=_PLACEHOLDER_VARIANTS.keys())
def test_placeholder_variant_rejected_in_production(value: str) -> None:
    settings = _production_settings(JWT_SECRET=value)
    with pytest.raises(RuntimeError, match="placeholder"):
        settings.validate_runtime()


def test_below_minimum_length_rejected_in_production() -> None:
    settings = _production_settings(JWT_SECRET="a" * 19)  # eşik: 20
    with pytest.raises(RuntimeError, match="placeholder"):
        settings.validate_runtime()


def test_padded_but_otherwise_valid_secret_is_accepted_in_production() -> None:
    """Başında/sonunda whitespace olan ama strip sonrası geçerli uzun bir
    secret KABUL edilmeli — normalize etmek onu reddetmek anlamına gelmez."""
    settings = _production_settings(JWT_SECRET="   " + _STRONG_SECRET + "   ")
    settings.validate_runtime()  # raise etmemeli


def test_normal_long_test_secret_is_accepted_in_production() -> None:
    settings = _production_settings(JWT_SECRET="a-genuinely-long-random-looking-secret-value-123")
    settings.validate_runtime()  # raise etmemeli


def test_non_production_mode_does_not_enforce_placeholder_check() -> None:
    """Production DIŞINDA whitespace-only/placeholder secret'lar dev-insecure
    değerlerle otomatik doldurulur — validate_runtime() raise ETMEMELİ."""
    settings = Settings.model_validate({"APP_ENV": "development", "JWT_SECRET": " " * 20})
    settings.validate_runtime()
    assert settings.JWT_SECRET.startswith("dev-insecure-")
