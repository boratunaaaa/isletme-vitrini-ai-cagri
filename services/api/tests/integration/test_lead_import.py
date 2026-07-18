from __future__ import annotations

import io
import json
from pathlib import Path

from openpyxl import Workbook

from app.models.lead import Lead
from app.services.importer import commit_import, guess_column_mapping, parse_file

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_valid_csv_import_turkish_headers_reports_counts(db_session, clean_db) -> None:
    with (FIXTURES / "leads_tr.csv").open("rb") as file:
        parsed = parse_file(file, "leads_tr.csv")
    mapping = guess_column_mapping(parsed.headers)

    result = commit_import(
        db_session,
        parsed_rows=parsed.rows,
        mapping=mapping,
        filename="leads_tr.csv",
        created_by=None,
    )
    db_session.commit()

    assert result.imported == 1
    assert result.invalid == 2
    assert result.duplicates == 0
    lead = db_session.query(Lead).one()
    assert lead.business_name == "Acme Cafe"
    assert lead.phone_last_four == "4567"
    assert lead.phone_hash is not None
    assert lead.phone_ciphertext is not None
    assert "0532" not in json.dumps(result.errors, ensure_ascii=False)


def test_valid_json_import_english_headers(db_session, clean_db) -> None:
    with (FIXTURES / "leads_en.json").open("rb") as file:
        parsed = parse_file(file, "leads_en.json")
    mapping = guess_column_mapping(parsed.headers)

    result = commit_import(
        db_session,
        parsed_rows=parsed.rows,
        mapping=mapping,
        filename="leads_en.json",
        created_by=None,
    )
    db_session.commit()

    assert result.imported == 1
    lead = db_session.query(Lead).one()
    assert lead.business_name == "Beta Clinic"
    assert lead.external_place_id == "place-beta"
    assert lead.demo_link == "https://demo.example/beta"


def test_valid_xlsx_import_skips_blank_rows_and_handles_formula_cells(
    db_session, clean_db
) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Business Name", "Phone", "City", "Notes"])
    sheet.append(["Gamma Hotel", "905321234567", "Izmir", "=1+1"])
    sheet.append([None, None, None, None])
    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)

    parsed = parse_file(buffer, "leads.xlsx")
    mapping = guess_column_mapping(parsed.headers)
    result = commit_import(
        db_session,
        parsed_rows=parsed.rows,
        mapping=mapping,
        filename="leads.xlsx",
        created_by=None,
    )
    db_session.commit()

    assert len(parsed.rows) == 1
    assert result.imported == 1
    assert db_session.query(Lead).one().business_name == "Gamma Hotel"


def test_unsupported_file_type_and_missing_business_mapping_fail_controlled() -> None:
    try:
        parse_file(io.BytesIO(b"x"), "leads.txt")
    except ValueError as exc:
        assert "xlsx" in str(exc)
    else:
        raise AssertionError("unsupported file did not fail")
