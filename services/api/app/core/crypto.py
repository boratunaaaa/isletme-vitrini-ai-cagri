"""PII şifreleme ve deterministik telefon hash'i.

- Şifreleme: AES-256-GCM. Anahtar, PII_ENCRYPTION_KEY'den HKDF-SHA256 ile
  türetilir; böylece env'e herhangi bir güçlü rastgele string konabilir.
- Hash: HMAC-SHA256(PHONE_HASH_PEPPER, e164). Suppression ve duplicate
  kontrolü için deterministiktir; pepper olmadan geri çevrilemez.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import get_settings

_NONCE_LEN = 12
_MIN_SECRET_LEN = 32


def _derive_key(secret: str, info: bytes) -> bytes:
    if len(secret) < _MIN_SECRET_LEN:
        raise ValueError("PII_ENCRYPTION_KEY geçersiz")
    return HKDF(algorithm=SHA256(), length=32, salt=b"ivac-pii-v1", info=info).derive(
        secret.encode("utf-8")
    )


def _aesgcm() -> AESGCM:
    return AESGCM(_derive_key(get_settings().PII_ENCRYPTION_KEY, b"phone"))


def encrypt_pii(plaintext: str) -> str:
    if not plaintext:
        raise ValueError("PII plaintext boş olamaz")
    nonce = os.urandom(_NONCE_LEN)
    ciphertext = _aesgcm().encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + ciphertext).decode("ascii")


def decrypt_pii(token: str) -> str:
    raw = base64.b64decode(token.encode("ascii"))
    nonce, ciphertext = raw[:_NONCE_LEN], raw[_NONCE_LEN:]
    return _aesgcm().decrypt(nonce, ciphertext, None).decode("utf-8")


def hash_phone(e164: str) -> str:
    pepper = get_settings().PHONE_HASH_PEPPER
    if len(pepper) < _MIN_SECRET_LEN:
        raise ValueError("PHONE_HASH_PEPPER geçersiz")
    return hmac.new(pepper.encode("utf-8"), e164.encode("utf-8"), hashlib.sha256).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())
