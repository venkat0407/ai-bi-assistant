# Design Document

## Overview

The AI BI Assistant is a Python 3.10+ web application that loads a CSV of sales transactions into a SQLite database on startup, classifies natural-language questions through the Gemini API (with a keyword/regex fallback), executes deterministic parameterized SQL, and returns structured JSON answers to a plain HTML/JS single-page frontend. Every component except the Gemini API call is fully deterministic; the LLM is used only for intent classification, never for generating numeric answers.

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                          FastAPI App                             │
│                                                                  │
│  ┌────────────┐   startup   ┌─────────────────────────────────┐  │
│  │ data_loader│────────────►│  SQLite DB (in-memory or file)  │  │
│  │   .py      │             │  • sales_raw   (51 rows)        │  │
│  └────────────┘             │  • sales       (48 valid rows)  │  │
│                             │  • rejected_rows (3 rows)       │  │
│  POST /ask                  └──────────────┬──────────────────┘  │
│  ┌──────────────────────────────────────┐  │                     │
│  │  Request                             │  │                     │
│  │  question: str ──► IntentClassifier  │  │                     │
│  │                    ┌──────────────┐  │  │                     │
│  │                    │ Gemini API   │  │  │                     │
│  │                    │ (primary)    │  │  │                     │
│  │                    └──────┬───────┘  │  │                     │
│  │                    ┌──────▼───────┐  │  │                     │
│  │                    │KeywordMatcher│  │  │                     │
│  │                    │ (fallback)   │  │  │                     │
│  │                    └──────┬───────┘  │  │                     │
│  │          intent + params  │          │  │                     │
│  │                    ┌──────▼───────┐  │  │                     │
│  │                    │ QueryEngine  │◄─┘  │                     │
│  │                    │ (SQL only)   │     │                     │
│  │                    └──────┬───────┘     │                     │
│  │                    ┌──────▼───────┐     │                     │
│  │                    │ AnswerBuilder│     │                     │
│  │                    └──────┬───────┘     │                     │
│  │                    JSON response        │                     │
│  └──────────────────────────────────────┘  │                     │
│                                            │                     │
│  GET /           ── static HTML frontend   │                     │
│  GET /health     ── liveness probe         │                     │
│  GET /data-quality ── rejected rows list   │                     │
└──────────────────────────────────────────┘
```

## Components and Interfaces

### 1. `data_loader.py` — Data_Loader

Runs once at application startup via a FastAPI `lifespan` context manager. Connects to the SQLite file `bi_assistant.db`, drops and recreates all three tables, then processes `data/sales.csv` row by row.

**Responsibilities:**
- Read all rows from CSV and insert verbatim into `sales_raw`
- Validate each row; write invalid rows (with reason) to `rejected_rows`
- Transform valid rows and write to `sales` with computed columns

**Rejection Logic (applied in order — first match wins):**
1. `duplicate_transaction_id` — Transaction_Id already seen in this run
2. `returned` — Status == "Returned" (case-insensitive)
3. `missing_price` — Unit_price is empty/null or < 0
4. `quantity_zero` — Quantity <= 0
5. `unparseable_date` — Order_date cannot be parsed as DD-MM-YYYY

**Computed columns for valid rows:**
- `order_date_iso`: parsed date formatted as `YYYY-MM-DD`
- `month`: first 7 chars of `order_date_iso` → `YYYY-MM`
- `revenue`: `Quantity * Unit_price - Discount_amount`

### 2. `intent_classifier.py` — Intent_Classifier + Keyword_Matcher

**Intent_Classifier (Gemini-based):**

Calls Gemini with a structured prompt on every `/ask` request. The prompt asks Gemini to return a JSON object with exactly two keys: `intent` and `params`. If the API is unavailable or returns non-JSON, falls back to Keyword_Matcher.

After receiving a response, validates:
- `intent` is one of the `SUPPORTED_INTENTS` set or `"unsupported"`
- For `compare_months`: `params.month_a` and `params.month_b` match `YYYY-MM` regex and exist in the set of months in the `sales` table
- All param values (product names, regions, month strings) are in a pre-built whitelist derived from the actual data
- If any validation fails, returns `{"intent": "unsupported", "params": {}}`

**SQL-injection guard (applied before any classification):**
- If the question contains any of `DROP`, `DELETE`, `INSERT`, `UPDATE`, `ALTER`, `CREATE`, `TRUNCATE` (case-insensitive), immediately return `{"intent": "unsupported", "params": {}}`

**Keyword_Matcher (regex fallback):**

Used when Gemini is unavailable. Pattern matching against the lowercased question:

| Pattern | Intent |
|---|---|
| `total.*revenue`, `how much.*made` | `total_revenue` |
| `top.*product`, `best.*product` | `top_product` |
| `monthly.*trend`, `by month` | `monthly_trend` |
| `top.*region`, `best.*region` | `top_region` |
| `compare.*month` + two YYYY-MM groups | `compare_months` |
| `by.*category`, `revenue.*category` | `revenue_by_category` |
| `by.*channel`, `revenue.*channel` | `revenue_by_channel` |
| no match | `unsupported` |

### 3. `query_engine.py` — Query_Engine

Opens the SQLite database in **read-only mode** (`uri=True` with `?mode=ro`) for all query operations. Executes one of seven parameterized SQL templates based on intent. Returns a `QueryResult` dataclass.

**SQL Templates:**

```python
QUERIES = {
    "total_revenue": (
        "SELECT ROUND(SUM(revenue), 2) AS total_revenue FROM sales",
        []
    ),
    "top_product": (
        "SELECT product, ROUND(SUM(revenue), 2) AS revenue "
        "FROM sales GROUP BY product ORDER BY revenue DESC LIMIT 1",
        []
    ),
    "monthly_trend": (
        "SELECT month, ROUND(SUM(revenue), 2) AS revenue "
        "FROM sales GROUP BY month ORDER BY month ASC",
        []
    ),
    "top_region": (
        "SELECT region, ROUND(SUM(revenue), 2) AS revenue "
        "FROM sales GROUP BY region ORDER BY revenue DESC LIMIT 1",
        []
    ),
    "compare_months": (
        "SELECT month, ROUND(SUM(revenue), 2) AS revenue "
        "FROM sales WHERE month IN (?, ?) GROUP BY month",
        ["month_a", "month_b"]   # param names resolved from intent params
    ),
    "revenue_by_category": (
        "SELECT category, ROUND(SUM(revenue), 2) AS revenue "
        "FROM sales GROUP BY category ORDER BY revenue DESC",
        []
    ),
    "revenue_by_channel": (
        "SELECT sales_channel, ROUND(SUM(revenue), 2) AS revenue "
        "FROM sales GROUP BY sales_channel ORDER BY revenue DESC",
        []
    ),
}
```

All SQL uses `?` placeholders — no f-strings or string concatenation with user input.

For `compare_months`, post-query arithmetic computes:
- `absolute_difference = rev_b - rev_a`
- `percentage_change = (rev_b - rev_a) / rev_a * 100` (rounded to 1 decimal)

### 4. `answer_builder.py` — Answer_Builder

Consumes a `QueryResult` and produces a Python dict matching the API response schema. All answer text is template-driven from computed numbers — no LLM call.

**Answer Templates:**

| Intent | Answer template |
|---|---|
| `total_revenue` | `"Total revenue across all sales is £{value:,.0f}."` |
| `top_product` | `"The top product is {product} with total revenue of £{revenue:,.0f}."` |
| `monthly_trend` | `"Monthly revenue trend: {month}: £{revenue:,.0f}, …"` |
| `top_region` | `"The top region is {region} with total revenue of £{revenue:,.0f}."` |
| `compare_months` | `"Revenue for {month_a} was £{rev_a:,.0f} and for {month_b} was £{rev_b:,.0f}. Absolute change: £{diff:+,.0f}. Percentage change: {pct:+.1f}%."` |
| `revenue_by_category` | Lists all categories with their revenues. |
| `revenue_by_channel` | Lists all channels with their revenues. |
| `unsupported` | Lists all 7 supported intents. |

### 5. `main.py` — FastAPI Application

```python
# Startup: runs data_loader.init_db()
# Routes:
#   POST /ask
#   GET  /health
#   GET  /data-quality
#   GET  /          → serves frontend/index.html
```

**POST /ask request schema:**
```python
class AskRequest(BaseModel):
    question: str

    @validator("question")
    def validate_question(cls, v):
        stripped = v.strip()
        if not stripped:
            raise ValueError("question must not be empty or whitespace")
        if len(stripped) > 500:
            raise ValueError("question must not exceed 500 characters")
        return stripped
```

**POST /ask response schema:**
```python
class AskResponse(BaseModel):
    answer: str
    intent: str
    params: dict
    sql: str
    supporting_data: list[dict]
    warnings: list[str]
```

**Error handling:**
- Pydantic validation errors → 422 with JSON body, no stack trace
- Unhandled exceptions → caught by a global exception handler → 500 with `{"error": "Internal server error"}`, no stack trace

### 6. `frontend/index.html` — Frontend

A single static HTML file served by FastAPI at `/`. All styling is inline CSS; all JavaScript is vanilla ES2020.

**Layout:**
```
┌─────────────────────────────────────────────┐
│  AI BI Assistant                            │
│  ┌─────────────────────────────────────┐    │
│  │  Ask a question...              [Ask]│   │
│  └─────────────────────────────────────┘    │
│  Example chips: [Total Revenue] [Top Product]│
│                 [Monthly Trend] [Top Region] │
│                                             │
│  ┌──────────────────────────────────────┐   │
│  │  Answer card                         │   │
│  │  "Total revenue is £1,439,200"       │   │
│  └──────────────────────────────────────┘   │
│  ┌──────────────────────────────────────┐   │
│  │  Monthly Trend Chart (CSS bars)      │   │
│  │  ████ Jan  ████ Feb  ██████ Mar ...  │   │
│  └──────────────────────────────────────┘   │
│  ┌──────────────────────────────────────┐   │
│  │  Supporting Data table               │   │
│  └──────────────────────────────────────┘   │
│  ▼ SQL used                                 │
│    SELECT SUM(revenue) FROM sales           │
└─────────────────────────────────────────────┘
```

**CSS Bar Chart (monthly_trend only):**
- Rendered as a `<div>` grid where each bar is a `<div>` with `height` set as a percentage of the max revenue value
- No external library; purely CSS flexbox/grid + inline style for bar height

## Data Models

### SQLite Tables

```sql
CREATE TABLE sales_raw (
    transaction_id   TEXT,
    order_date       TEXT,
    product          TEXT,
    category         TEXT,
    region           TEXT,
    sales_channel    TEXT,
    quantity         TEXT,   -- stored as-is from CSV
    unit_price       TEXT,
    discount_amount  TEXT,
    status           TEXT
);

CREATE TABLE sales (
    transaction_id   TEXT PRIMARY KEY,
    order_date_iso   TEXT NOT NULL,   -- YYYY-MM-DD
    month            TEXT NOT NULL,   -- YYYY-MM
    product          TEXT NOT NULL,
    category         TEXT NOT NULL,
    region           TEXT NOT NULL,
    sales_channel    TEXT NOT NULL,
    quantity         INTEGER NOT NULL,
    unit_price       REAL NOT NULL,
    discount_amount  REAL NOT NULL DEFAULT 0,
    revenue          REAL NOT NULL,
    status           TEXT NOT NULL
);

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
);
```

### Python Dataclasses

```python
@dataclass
class QueryResult:
    intent: str
    params: dict
    sql: str
    rows: list[dict]       # raw rows from SQLite
    computed: dict         # post-query derived values (e.g. diff, pct_change)
    warnings: list[str]

@dataclass
class ClassificationResult:
    intent: str
    params: dict
    source: str            # "gemini" | "keyword_matcher"
```

### Gemini API Prompt

```
You are a BI assistant. Classify the following business question into one intent.

Respond with ONLY a JSON object with two keys:
- "intent": one of [total_revenue, top_product, monthly_trend, top_region,
  compare_months, revenue_by_category, revenue_by_channel, unsupported]
- "params": an object (empty {} if not needed; for compare_months include
  "month_a" and "month_b" as YYYY-MM strings)

Question: {question}
```

Response is parsed with `json.loads()`. Any exception (network error, non-JSON body, missing keys) triggers fallback to Keyword_Matcher.

### Internal Component Interfaces

```python
# data_loader.py
def init_db(db_path: str = "bi_assistant.db", csv_path: str = "data/sales.csv") -> None: ...

# intent_classifier.py
def classify(question: str, db_path: str) -> ClassificationResult: ...

# query_engine.py
def execute(intent: str, params: dict, db_path: str) -> QueryResult: ...

# answer_builder.py
def build(result: QueryResult) -> dict: ...  # returns AskResponse-compatible dict
```

## Project Structure

```
ai-bi-assistant/
├── main.py                  # FastAPI app, routes, lifespan
├── data_loader.py           # CSV → SQLite pipeline
├── intent_classifier.py     # Gemini + keyword fallback
├── query_engine.py          # Parameterized SQL execution
├── answer_builder.py        # Template-driven answer text
├── frontend/
│   └── index.html           # SPA — plain HTML/CSS/JS
├── data/
│   └── sales.csv
├── tests/
│   ├── conftest.py          # pytest fixtures, mock Gemini, test DB setup
│   ├── test_data_loader.py
│   ├── test_intent_classifier.py
│   ├── test_query_engine.py
│   ├── test_answer_builder.py
│   └── test_api.py          # FastAPI TestClient integration tests
├── docs/
│   ├── ARCHITECTURE.md
│   ├── AI_USAGE.md
│   └── LIMITATIONS.md
├── README.md
├── requirements.txt
└── .env.example
```

## Error Handling

| Scenario | Behaviour |
|---|---|
| Gemini API unreachable / timeout | Keyword_Matcher fallback; `warnings` field includes `"AI classification unavailable, using keyword fallback"` |
| Gemini returns non-JSON | Same as above |
| Gemini returns invalid intent string | Intent set to `unsupported`; no fallback needed |
| Param value not in whitelist | Intent set to `unsupported` |
| `compare_months` month not in data | Graceful answer message; HTTP 200; `warnings` field populated |
| Empty / whitespace question | HTTP 422, JSON error body, no stack trace |
| Question > 500 chars | HTTP 422, JSON error body, no stack trace |
| SQL injection keywords in question | Intent set to `unsupported` before any DB access |
| Any unhandled exception | HTTP 500, `{"error": "Internal server error"}`, no stack trace |
| Missing `data/sales.csv` at startup | Application raises `RuntimeError` and fails to start with a clear message |

## Security Design

1. **Parameterized SQL only**: The query engine accepts an `intent` string (matched against a fixed dict of known queries) and a `params` dict (validated against a whitelist). No user text ever reaches a SQL string.
2. **Read-only DB connection**: All `/ask` queries open the DB with `sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)`, preventing any write operations.
3. **Whitelist validation**: After Gemini classification, params are checked against sets of known `products`, `regions`, and `months` built from the loaded `sales` table.
4. **SQL keyword guard**: Questions are scanned for DML/DDL keywords before classification begins.
5. **No LLM-generated numbers**: All numeric values in answers are derived exclusively from SQL query results. The LLM output is discarded after the `intent` and `params` keys are extracted.

## Testing Strategy

**Dual Testing Approach:**

- **Unit / example-based tests** (`pytest`): Cover specific expected outcomes — the 51-row CSV producing exactly 48 valid and 3 rejected rows, each named rejection transaction, the exact total revenue of £1,439,200, HTTP 422 for empty questions, HTTP 500 without stack trace on unhandled errors, and the Gemini fallback path.
- **Property-based tests** (`hypothesis`): Cover universal invariants — date conversion correctness for arbitrary DD-MM-YYYY inputs, revenue formula for arbitrary numeric inputs, rejection rules for arbitrary invalid rows, aggregation correctness across arbitrary row sets, whitelist enforcement for arbitrary param values, and input validation rejection for arbitrary oversized/blank strings.

**Mocking Strategy:**
- All tests mock the Gemini API using `unittest.mock.patch` so tests are deterministic and require no live API key.
- A shared `conftest.py` fixture initialises a fresh in-memory SQLite database from `data/sales.csv` before each test module.
- The read-only query engine is tested by verifying that write operations raise `sqlite3.OperationalError`.

**Test Files:**

| File | Focus |
|---|---|
| `tests/test_data_loader.py` | CSV loading, rejection rules, row counts, revenue totals |
| `tests/test_intent_classifier.py` | Gemini happy path, fallback, whitelist, SQL injection guard |
| `tests/test_query_engine.py` | All 7 intents, parameterized SQL, read-only mode |
| `tests/test_answer_builder.py` | Answer text templates, unsupported message, compare months edge case |
| `tests/test_api.py` | FastAPI endpoints — /ask, /health, /data-quality, 422, 500 |

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Date Conversion Round-Trip

*For any* date string in `DD-MM-YYYY` format, converting it to `YYYY-MM-DD` and then extracting the first 7 characters to form a `YYYY-MM` month string should produce the same calendar month as the original date.

**Validates: Requirements 1.2, 1.3**

### Property 2: Revenue Formula Invariant

*For any* row with a positive integer `Quantity`, non-negative `Unit_price`, and non-negative `Discount_amount`, the computed `revenue` stored in the `sales` table SHALL equal `Quantity * Unit_price - Discount_amount`.

**Validates: Requirements 1.4**

### Property 3: Rejection Completeness

*For any* input row that violates at least one validation rule (quantity ≤ 0, missing/negative price, unparseable date, duplicate transaction ID, or Status == "Returned"), that row SHALL appear in `rejected_rows` and SHALL NOT appear in `sales`.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6**

### Property 4: Aggregation Correctness

*For any* set of rows in the `sales` table, the `total_revenue` query result SHALL equal the arithmetic sum of all individual `revenue` values, and grouping queries (`monthly_trend`, `revenue_by_category`, `revenue_by_channel`) SHALL produce sub-totals that sum to the same total.

**Validates: Requirements 3.1, 3.3, 3.6, 3.7**

### Property 5: Top-N Supremacy

*For any* set of rows in the `sales` table, the product (or region) returned by `top_product` (or `top_region`) SHALL have a total revenue greater than or equal to the total revenue of every other product (or region).

**Validates: Requirements 3.2, 3.4**

### Property 6: Month Comparison Arithmetic

*For any* two months `A` and `B` present in the `sales` table, the `compare_months` result SHALL satisfy: `absolute_difference == rev_B - rev_A` and `percentage_change == (rev_B - rev_A) / rev_A * 100` (within floating-point tolerance).

**Validates: Requirements 3.5**

### Property 7: Response Schema Completeness

*For any* supported intent, the JSON response from `POST /ask` SHALL contain all six fields (`answer`, `intent`, `params`, `sql`, `supporting_data`, `warnings`) and the `sql` field SHALL be a non-empty string.

**Validates: Requirements 3.10, 3.11, 5.4**

### Property 8: Whitelist Enforcement

*For any* param value returned by Gemini that does not appear in the pre-built whitelist of known products, regions, and valid month strings, the final classified intent SHALL be `unsupported`.

**Validates: Requirements 4.2, 4.6**

### Property 9: Input Validation Rejection

*For any* question string that is empty, composed entirely of whitespace, or exceeds 500 characters, `POST /ask` SHALL return an HTTP 4xx status code and SHALL NOT execute any database query.

**Validates: Requirements 6.2, 6.3**

### Property 10: SQL Injection Safety

*For any* question string that contains SQL DML or DDL keywords (`DROP`, `DELETE`, `INSERT`, `UPDATE`, `ALTER`, `CREATE`, `TRUNCATE`), the Intent_Classifier SHALL return intent `unsupported` and the Query_Engine SHALL NOT be called with that input.

**Validates: Requirements 4.7, 8.1, 8.3**

### Property 11: Unsupported Intent Listing

*For any* question that results in intent `unsupported`, the `answer` field in the response SHALL reference all seven supported intent names so the user knows what they can ask.

**Validates: Requirements 5.2**
