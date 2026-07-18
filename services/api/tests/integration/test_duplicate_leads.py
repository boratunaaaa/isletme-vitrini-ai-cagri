from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.crypto import encrypt_pii, hash_phone
from app.core.phone import normalize_phone
from app.models.lead import Lead
from app.services.importer import commit_import, guess_column_mapping


def test_duplicate_place_id_and_phone_are_skipped(db_session, clean_db) -> None:
    rows = [
        {"Firma": "A", "Telefon": "0532 123 45 67", "Place ID": "same-place"},
        {"Firma": "B", "Telefon": "+90 532 999 99 99", "Place ID": "same-place"},
        {"Firma": "C", "Telefon": "+90 532 123 45 67", "Place ID": "other-place"},
        {"Firma": "D", "Telefon": "+90 555 111 22 33", "Place ID": "new-place"},
    ]
    mapping = guess_column_mapping(list(rows[0]))

    result = commit_import(
        db_session,
        parsed_rows=rows,
        mapping=mapping,
        filename="leads.csv",
        created_by=None,
    )
    db_session.commit()

    assert result.imported == 2
    assert result.duplicates == 2
    assert db_session.query(Lead).count() == 2


def test_existing_phone_duplicate_is_detected_without_pii_error(db_session, clean_db) -> None:
    normalized = normalize_phone("0532 123 45 67")
    db_session.add(
        Lead(
            business_name="Existing",
            phone_ciphertext=encrypt_pii(normalized.e164),
            phone_hash=hash_phone(normalized.e164),
            phone_last_four=normalized.last_four,
            phone_country_code=normalized.country_code,
        )
    )
    db_session.commit()

    result = commit_import(
        db_session,
        parsed_rows=[{"Firma": "Incoming", "Telefon": "+90 532 123 45 67"}],
        mapping={"business_name": "Firma", "phone": "Telefon"},
        filename="leads.csv",
        created_by=None,
    )

    assert result.imported == 0
    assert result.duplicates == 1
    assert "+905321234567" not in str(result.errors)


def test_unique_phone_hash_constraint_protects_concurrent_duplicate(db_session, clean_db) -> None:
    normalized = normalize_phone("0532 123 45 67")
    phone_hash = hash_phone(normalized.e164)
    db_session.add_all(
        [
            Lead(
                business_name="First",
                phone_ciphertext=encrypt_pii(normalized.e164),
                phone_hash=phone_hash,
                phone_last_four=normalized.last_four,
                phone_country_code=normalized.country_code,
            ),
            Lead(
                business_name="Second",
                phone_ciphertext=encrypt_pii(normalized.e164),
                phone_hash=phone_hash,
                phone_last_four=normalized.last_four,
                phone_country_code=normalized.country_code,
            ),
        ]
    )

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
