# query_engine.py — Parameterized SQL execution against SQLite
# Executes one of seven fixed SQL templates based on the classified intent

import sqlite3
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class QueryResult:
    intent: str
    params: Dict[str, Any]
    sql: str
    rows: List[Dict[str, Any]]
    computed: Dict[str, Any]
    warnings: List[str]


# Seven parameterized SQL templates.
# Each entry is (sql_template, list_of_param_keys).
# param_keys names the keys in the `params` dict that supply the ? values, in order.
QUERIES: Dict[str, tuple] = {
    "total_revenue": (
        "SELECT ROUND(SUM(revenue), 2) AS total_revenue FROM sales",
        [],
    ),
    "top_product": (
        "SELECT product, ROUND(SUM(revenue), 2) AS revenue "
        "FROM sales GROUP BY product ORDER BY revenue DESC LIMIT 1",
        [],
    ),
    "monthly_trend": (
        "SELECT month, ROUND(SUM(revenue), 2) AS revenue "
        "FROM sales GROUP BY month ORDER BY month ASC",
        [],
    ),
    "top_region": (
        "SELECT region, ROUND(SUM(revenue), 2) AS revenue "
        "FROM sales GROUP BY region ORDER BY revenue DESC LIMIT 1",
        [],
    ),
    "compare_months": (
        "SELECT month, ROUND(SUM(revenue), 2) AS revenue "
        "FROM sales WHERE month IN (?, ?) GROUP BY month ORDER BY month ASC",
        ["month_a", "month_b"],
    ),
    "revenue_by_category": (
        "SELECT category, ROUND(SUM(revenue), 2) AS revenue "
        "FROM sales GROUP BY category ORDER BY revenue DESC",
        [],
    ),
    "revenue_by_channel": (
        "SELECT sales_channel, ROUND(SUM(revenue), 2) AS revenue "
        "FROM sales GROUP BY sales_channel ORDER BY revenue DESC",
        [],
    ),
}


def execute(
    intent: str,
    params: Dict[str, Any],
    db_path: str = "bi_assistant.db",
) -> QueryResult:
    """
    Execute the SQL template for `intent` against the read-only SQLite database.

    Parameters
    ----------
    intent   : one of the seven supported intent strings
    params   : dict of named parameters (used for compare_months)
    db_path  : path to the SQLite database file

    Returns
    -------
    QueryResult dataclass

    Raises
    ------
    ValueError  if `intent` is not a recognised key in QUERIES
    """
    if intent not in QUERIES:
        raise ValueError(f"Unknown intent: {intent}")

    sql_template, param_keys = QUERIES[intent]

    # Resolve positional ? values from named params dict
    sql_values = [params[k] for k in param_keys]

    warnings: List[str] = []
    computed: Dict[str, Any] = {}

    # Open DB in read-only mode — prevents any write operations
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        cursor.execute(sql_template, sql_values)
        rows = [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

    # Post-query arithmetic for compare_months
    if intent == "compare_months":
        month_a = params.get("month_a", "")
        month_b = params.get("month_b", "")

        rev_map: Dict[str, float] = {r["month"]: r["revenue"] for r in rows}

        # Warn about any requested month absent from the results
        if month_a not in rev_map:
            warnings.append(f"Month {month_a} is not present in the dataset.")
        if month_b not in rev_map:
            warnings.append(f"Month {month_b} is not present in the dataset.")

        if month_a in rev_map and month_b in rev_map:
            rev_a = rev_map[month_a]
            rev_b = rev_map[month_b]
            absolute_difference = round(rev_b - rev_a, 2)
            # Guard against division-by-zero (rev_a == 0)
            if rev_a != 0:
                percentage_change = round((rev_b - rev_a) / rev_a * 100, 1)
            else:
                percentage_change = None
                warnings.append(
                    f"Cannot compute percentage change: revenue for {month_a} is zero."
                )
            computed["rev_a"] = rev_a
            computed["rev_b"] = rev_b
            computed["absolute_difference"] = absolute_difference
            computed["percentage_change"] = percentage_change

    return QueryResult(
        intent=intent,
        params=params,
        sql=sql_template,
        rows=rows,
        computed=computed,
        warnings=warnings,
    )
