# data_loader.py — CSV to SQLite pipeline
# Reads data/sales.csv, validates rows, and populates sales_raw, sales, and rejected_rows tables

import csv
import os
import sqlite3
from datetime import datetime
from typing import Dict, Optional, Set


# DDL for all three tables
_CREATE_SALES_RAW = """
CREATE TABLE sales_raw (
    transaction_id   TEXT,
    order_date       TEXT,
    product          TEXT,
    category         TEXT,
    region           TEXT,
    sales_channel    TEXT,
    quantity         TEXT,
    unit_price       TEXT,
    discount_amount  TEXT,
    status           TEXT
)
"""

_CREATE_SALES = """
CREATE TABLE sales (
    transaction_id   TEXT PRIMARY KEY,
    order_date_iso   TEXT NOT NULL,
    month            TEXT NOT NULL,
    product          TEXT NOT NULL,
    category         TEXT NOT NULL,
    region           TEXT NOT NULL,
    sales_channel    TEXT NOT NULL,
    quantity         INTEGER NOT NULL,
    unit_price       REAL NOT NULL,
    discount_amount  REAL NOT NULL DEFAULT 0,
    revenue          REAL NOT NULL,
    status           TEXT NOT NULL
)
"""

_CREATE_REJECTED_ROWS = """
CREATE TABLE rejected_rows (
    transaction_id   TEXT,
    order_date       TEXT,
    product          TEXT,
    category         TEXT,
    region           TEXT,
    sales_channel    TEXT,
    quantity         TEXT,
    unit_price       TEXT,
    discount_amount  TEXT,
    status           TEXT,
    reason           TEXT NOT NULL
)
"""


def _parse_date(date_str: str) -> Optional[datetime]:
    """Parse a DD-MM-YYYY date string; return None if unparseable."""
    try:
        return datetime.strptime(date_str.strip(), "%d-%m-%Y")
    except (ValueError, AttributeError):
        return None


def _parse_unit_price(price_str: str) -> Optional[float]:
    """
    Return the float value of the unit price string.
    Returns None if empty/whitespace; raises ValueError for non-numeric text.
    """
    stripped = price_str.strip() if price_str is not None else ""
    if stripped == "":
        return None
    return float(stripped)


def _validate_row(
    row: Dict[str, str],
    seen_ids: Set[str],
) -> Optional[str]:
    """
    Apply rejection rules in order (first match wins).
    Returns the reason string if the row should be rejected, else None.
    """
    txn_id = row.get("Transaction_Id", "").strip()

    # Rule 1: duplicate_transaction_id
    if txn_id in seen_ids:
        return "duplicate_transaction_id"

    # Rule 2: returned
    status = row.get("Status", "").strip()
    if status.lower() == "returned":
        return "returned"

    # Rule 3: missing_price
    raw_price = row.get("Unit_price", "")
    try:
        price = _parse_unit_price(raw_price)
    except ValueError:
        return "missing_price"
    if price is None or price < 0:
        return "missing_price"

    # Rule 4: quantity_zero
    raw_qty = row.get("Quantity", "").strip()
    try:
        qty = float(raw_qty)
    except (ValueError, TypeError):
        return "quantity_zero"
    if qty <= 0:
        return "quantity_zero"

    # Rule 5: unparseable_date
    order_date_str = row.get("Order_date", "")
    if _parse_date(order_date_str) is None:
        return "unparseable_date"

    return None


def init_db(db_path: str = "bi_assistant.db", csv_path: str = "data/sales.csv") -> None:
    """
    Load and clean sales.csv into SQLite.

    Creates (or recreates) three tables:
      - sales_raw    : all rows verbatim from the CSV
      - sales        : valid, cleaned rows with computed columns
      - rejected_rows: invalid rows with their rejection reason

    Raises RuntimeError if csv_path does not exist.
    """
    if not os.path.exists(csv_path):
        raise RuntimeError(
            f"Required data file not found: '{csv_path}'. "
            "Please ensure data/sales.csv is present before starting the application."
        )

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()

        # Drop existing tables and recreate fresh
        cursor.execute("DROP TABLE IF EXISTS sales_raw")
        cursor.execute("DROP TABLE IF EXISTS sales")
        cursor.execute("DROP TABLE IF EXISTS rejected_rows")
        cursor.execute(_CREATE_SALES_RAW)
        cursor.execute(_CREATE_SALES)
        cursor.execute(_CREATE_REJECTED_ROWS)
        conn.commit()

        seen_ids: Set[str] = set()

        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)

            for row in reader:
                # Normalise: strip whitespace from all keys and values
                row = {k.strip(): (v.strip() if v is not None else "") for k, v in row.items()}

                txn_id = row.get("Transaction_Id", "")

                # --- Insert verbatim into sales_raw ---
                cursor.execute(
                    """
                    INSERT INTO sales_raw (
                        transaction_id, order_date, product, category,
                        region, sales_channel, quantity, unit_price,
                        discount_amount, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        txn_id,
                        row.get("Order_date", ""),
                        row.get("Product", ""),
                        row.get("Category", ""),
                        row.get("Region", ""),
                        row.get("Sales_channel", ""),
                        row.get("Quantity", ""),
                        row.get("Unit_price", ""),
                        row.get("Discount_amount", ""),
                        row.get("Status", ""),
                    ),
                )

                # --- Validate ---
                reason = _validate_row(row, seen_ids)

                if reason is not None:
                    # Insert into rejected_rows
                    cursor.execute(
                        """
                        INSERT INTO rejected_rows (
                            transaction_id, order_date, product, category,
                            region, sales_channel, quantity, unit_price,
                            discount_amount, status, reason
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            txn_id,
                            row.get("Order_date", ""),
                            row.get("Product", ""),
                            row.get("Category", ""),
                            row.get("Region", ""),
                            row.get("Sales_channel", ""),
                            row.get("Quantity", ""),
                            row.get("Unit_price", ""),
                            row.get("Discount_amount", ""),
                            row.get("Status", ""),
                            reason,
                        ),
                    )
                else:
                    # Valid row — compute derived columns and insert into sales
                    seen_ids.add(txn_id)

                    dt = _parse_date(row["Order_date"])
                    order_date_iso = dt.strftime("%Y-%m-%d")
                    month = order_date_iso[:7]

                    quantity = int(float(row["Quantity"]))
                    unit_price = float(row["Unit_price"])
                    discount_amount_str = row.get("Discount_amount", "").strip()
                    discount_amount = float(discount_amount_str) if discount_amount_str else 0.0
                    revenue = quantity * unit_price - discount_amount

                    cursor.execute(
                        """
                        INSERT INTO sales (
                            transaction_id, order_date_iso, month, product, category,
                            region, sales_channel, quantity, unit_price,
                            discount_amount, revenue, status
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            txn_id,
                            order_date_iso,
                            month,
                            row.get("Product", ""),
                            row.get("Category", ""),
                            row.get("Region", ""),
                            row.get("Sales_channel", ""),
                            quantity,
                            unit_price,
                            discount_amount,
                            revenue,
                            row.get("Status", ""),
                        ),
                    )

                # Track seen IDs after processing (so a valid row blocks future duplicates)
                # Note: duplicates of *any* seen ID are rejected, including ones already rejected
                # for another reason. We add to seen_ids only for valid rows (duplicates of
                # invalid rows should still be caught if they share a Transaction_Id with a
                # row already processed as valid). Per spec, first-match wins so a row that was
                # rejected for 'returned' does NOT block a later row with the same Transaction_Id
                # from being rejected as 'duplicate_transaction_id'. We therefore add the ID
                # to seen_ids only after a row passes all validation (i.e., is written to sales).
                # This matches the spec intent: duplicates of valid rows are caught; rows that
                # were themselves rejected don't "claim" the ID.

        conn.commit()
    finally:
        conn.close()
