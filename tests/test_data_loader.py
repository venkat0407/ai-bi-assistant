# test_data_loader.py — Tests for data_loader.py
# Covers: row counts, rejection rules, revenue totals, property-based tests

import re
import sqlite3

import pytest
from hypothesis import given, settings
import hypothesis.strategies as st

from data_loader import _parse_date, init_db


# ---------------------------------------------------------------------------
# Shared fixture — creates a fresh DB from the real CSV once per module
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def loaded_db(tmp_path_factory):
    """Build and populate a SQLite DB from data/sales.csv; return its path."""
    db = tmp_path_factory.mktemp("db") / "test.db"
    init_db(db_path=str(db), csv_path="data/sales.csv")
    return str(db)


# ---------------------------------------------------------------------------
# Unit Tests — Task 2.5
# ---------------------------------------------------------------------------


def test_sales_row_count(loaded_db):
    """Valid (clean) rows in the sales table should total 48."""
    with sqlite3.connect(loaded_db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0]
    assert count == 48


def test_rejected_row_count(loaded_db):
    """Rows that fail validation should land in rejected_rows; expect 3."""
    with sqlite3.connect(loaded_db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM rejected_rows").fetchone()[0]
    assert count == 3


def test_txn0033_rejected_as_returned(loaded_db):
    """TXN0033 has status='Returned' and must be rejected with reason='returned'."""
    with sqlite3.connect(loaded_db) as conn:
        row = conn.execute(
            "SELECT reason FROM rejected_rows WHERE transaction_id = 'TXN0033'"
        ).fetchone()
    assert row is not None, "TXN0033 not found in rejected_rows"
    assert row[0] == "returned"


def test_txn0034_rejected_as_quantity_zero(loaded_db):
    """TXN0034 has quantity=0 and must be rejected with reason='quantity_zero'."""
    with sqlite3.connect(loaded_db) as conn:
        row = conn.execute(
            "SELECT reason FROM rejected_rows WHERE transaction_id = 'TXN0034'"
        ).fetchone()
    assert row is not None, "TXN0034 not found in rejected_rows"
    assert row[0] == "quantity_zero"


def test_txn0051_rejected_as_missing_price(loaded_db):
    """TXN0051 has a blank unit_price and must be rejected with reason='missing_price'."""
    with sqlite3.connect(loaded_db) as conn:
        row = conn.execute(
            "SELECT reason FROM rejected_rows WHERE transaction_id = 'TXN0051'"
        ).fetchone()
    assert row is not None, "TXN0051 not found in rejected_rows"
    assert row[0] == "missing_price"


def test_total_revenue(loaded_db):
    """Sum of all revenue values in the sales table should equal 1,439,200.00."""
    with sqlite3.connect(loaded_db) as conn:
        total = conn.execute("SELECT ROUND(SUM(revenue), 2) FROM sales").fetchone()[0]
    assert total == 1439200.0


def test_sales_raw_row_count(loaded_db):
    """sales_raw must contain every row from the CSV verbatim — expect 51."""
    with sqlite3.connect(loaded_db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM sales_raw").fetchone()[0]
    assert count == 51


def test_month_column_format(loaded_db):
    """Every value in the month column must match the YYYY-MM format."""
    pattern = re.compile(r"^\d{4}-\d{2}$")
    with sqlite3.connect(loaded_db) as conn:
        rows = conn.execute("SELECT DISTINCT month FROM sales").fetchall()
    assert rows, "No rows found in sales — cannot validate month format"
    for (month,) in rows:
        assert pattern.match(month), f"month value '{month}' does not match YYYY-MM"


# ---------------------------------------------------------------------------
# Property 1: Date Conversion Round-Trip  — Task 2.2
# Validates: Requirements 1.2, 1.3
# ---------------------------------------------------------------------------


@given(
    year=st.integers(min_value=2020, max_value=2030),
    month=st.integers(min_value=1, max_value=12),
    day=st.integers(min_value=1, max_value=28),  # 1–28 avoids month-end edge cases
)
@settings(max_examples=200)
def test_date_conversion_round_trip(year: int, month: int, day: int) -> None:
    """**Validates: Requirements 1.2, 1.3**

    For any valid DD-MM-YYYY date string, _parse_date must:
    1. Return a non-None datetime (i.e., successfully parse the date).
    2. Produce a YYYY-MM month string (via strftime("%Y-%m-%d")[:7]) that matches
       the original calendar month of the input.
    """
    date_str = f"{day:02d}-{month:02d}-{year:04d}"
    expected_month = f"{year:04d}-{month:02d}"

    result = _parse_date(date_str)

    assert result is not None, (
        f"_parse_date returned None for a valid date string '{date_str}'"
    )
    actual_month = result.strftime("%Y-%m-%d")[:7]
    assert actual_month == expected_month, (
        f"Month mismatch for '{date_str}': expected '{expected_month}', got '{actual_month}'"
    )


# ---------------------------------------------------------------------------
# Unit tests: _parse_date rejects invalid / wrong-format strings — Task 2.2
# ---------------------------------------------------------------------------


def test_parse_date_invalid_text() -> None:
    """Non-date strings must return None."""
    assert _parse_date("not-a-date") is None


def test_parse_date_wrong_format_iso() -> None:
    """ISO format YYYY-MM-DD is not DD-MM-YYYY and must return None."""
    assert _parse_date("2026-01-03") is None


def test_parse_date_empty_string() -> None:
    """Empty string must return None."""
    assert _parse_date("") is None


def test_parse_date_partial_date() -> None:
    """Incomplete date string must return None."""
    assert _parse_date("01-2026") is None
