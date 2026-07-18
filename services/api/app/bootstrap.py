from __future__ import annotations

import sys

from sqlalchemy import select

from app.config import get_settings
from app.core.security import hash_password
from app.db.session import session_scope
from app.models.user import User

WEAK_PASSWORD_MARKERS = ("password", "admin", "changeme", "123456", "qwerty")


def _validate_bootstrap_inputs(email: str, password: str) -> tuple[str, str]:
    normalized_email = email.strip().lower()
    if not normalized_email or "@" not in normalized_email:
        raise RuntimeError("BOOTSTRAP_ADMIN_EMAIL geçerli bir e-posta olmalı")
    if not password:
        raise RuntimeError("BOOTSTRAP_ADMIN_PASSWORD tanımlı olmalı")

    settings = get_settings()
    if settings.is_production:
        lowered = password.lower()
        if len(password) < 14 or any(marker in lowered for marker in WEAK_PASSWORD_MARKERS):
            raise RuntimeError(
                "Production bootstrap parolası güçlü ve varsayılan olmayan bir değer olmalı"
            )
    elif len(password) < 10:
        raise RuntimeError("BOOTSTRAP_ADMIN_PASSWORD en az 10 karakter olmalı")
    return normalized_email, password


def bootstrap_owner() -> str:
    settings = get_settings()
    email, password = _validate_bootstrap_inputs(
        settings.BOOTSTRAP_ADMIN_EMAIL,
        settings.BOOTSTRAP_ADMIN_PASSWORD,
    )
    with session_scope() as db:
        user = db.scalars(select(User).where(User.email == email)).first()
        if user is not None:
            if user.role != "owner":
                user.role = "owner"
            if not user.is_active:
                user.is_active = True
            return f"owner exists: {email}"

        user = User(
            email=email,
            full_name="Bootstrap Owner",
            password_hash=hash_password(password),
            role="owner",
            is_active=True,
        )
        db.add(user)
        db.flush()
        return f"owner created: {email}"


def main() -> int:
    try:
        print(bootstrap_owner())
        return 0
    except Exception as exc:
        print(f"bootstrap failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
