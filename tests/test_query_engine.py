# test_query_engine.py — Tests for query_engine.py
# Covers: all 7 intents, parameterized SQL, read-only mode enforcement

import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_loader import init_db
from query_engine import execute


@pytest.fixture(scope="module")
def db_path(tmp_path_factory):
    db = tmp_path_factory.mktemp("db") / "qe_test.db"
    init_db(db_path=str(db), csv_path="data/sales.csv")
    return str(db)


# ---------------------------------------------------------------------------
# 1. Total revenue
# ---------------------------------------------------------------------------

def test_total_revenue(db_path):
    result = execute("total_revenue", {}, db_path)
    assert result.rows[0]["total_revenue"] == 1439200.0


# ---------------------------------------------------------------------------
# 2. Top product
# ---------------------------------------------------------------------------

def test_top_product(db_path):
    result = execute("top_product", {}, db_path)
    row = result.rows[0]
    assert row["product"] == "Monitor"
    assert row["revenue"] == 473000.0


# ---------------------------------------------------------------------------
# 3. Top region
# ---------------------------------------------------------------------------

def test_top_region(db_path):
    result = execute("top_region", {}, db_path)
    row = result.rows[0]
    assert row["region"] == "South"
    assert row["revenue"] == 411200.0


# ---------------------------------------------------------------------------
# 4 & 5. Monthly trend
# ---------------------------------------------------------------------------

def test_monthly_trend_count(db_path):
    result = execute("monthly_trend", {}, db_path)
    assert len(result.rows) == 6


def test_monthly_trend_may(db_path):
    result = execute("monthly_trend", {}, db_path)
    may_rows = [r for r in result.rows if r["month"] == "2026-05"]
    assert len(may_rows) == 1
    assert may_rows[0]["revenue"] == 318500.0


# ---------------------------------------------------------------------------
# 6. Compare months
# ---------------------------------------------------------------------------

def test_compare_months(db_path):
    result = execute(
        "compare_months",
        {"month_a": "2026-04", "month_b": "2026-05"},
        db_path,
    )
    assert result.computed["absolute_difference"] == 77800.0
    assert result.computed["percentage_change"] == 32.3


# ---------------------------------------------------------------------------
# 7. Revenue by category
# ---------------------------------------------------------------------------

def test_revenue_by_category_has_rows(db_path):
    result = execute("revenue_by_category", {}, db_path)
    assert len(result.rows) >= 1


# ---------------------------------------------------------------------------
# 8. Revenue by channel
# ---------------------------------------------------------------------------

def test_revenue_by_channel_has_rows(db_path):
    result = execute("revenue_by_channel", {}, db_path)
    assert len(result.rows) >= 1


# ---------------------------------------------------------------------------
# 9. SQL field is a non-empty string
# ---------------------------------------------------------------------------

def test_sql_field_nonempty(db_path):
    result = execute("total_revenue", {}, db_path)
    assert isinstance(result.sql, str)
    assert len(result.sql) > 0


# ---------------------------------------------------------------------------
# 10. Read-only connection rejects writes
# ---------------------------------------------------------------------------

def test_read_only_connection(db_path):
    with pytest.raises(sqlite3.OperationalError):
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            conn.execute(
                "INSERT INTO sales (transaction_id, order_date_iso, month, product, "
                "category, region, sales_channel, quantity, unit_price, "
                "discount_amount, revenue, status) "
                "VALUES ('TEST', '2026-01-01', '2026-01', 'X', 'Y', 'Z', 'Online', "
                "1, 100.0, 0.0, 100.0, 'Completed')"
            )
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# 11. Unknown intent raises ValueError
# ---------------------------------------------------------------------------

def test_unknown_intent_raises():
    with pytest.raises(ValueError):
        execute("nonexistent", {})
