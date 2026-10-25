# Implementation Plan: AI BI Assistant

## Overview

Implement a Python 3.10+ FastAPI application that loads CSV sales data into SQLite, classifies natural-language questions via the Gemini API (with a keyword/regex fallback), executes deterministic parameterized SQL, and serves a plain HTML/JS single-page frontend. The build proceeds in layers: data pipeline first, then query engine, then classification, then API, then frontend, with tests woven in throughout.

## Tasks

- [ ] 1. Project scaffold and dependencies
  - Create `requirements.txt` with pinned versions: `fastapi`, `uvicorn[standard]`, `google-generativeai`, `pytest`, `pytest-asyncio`, `httpx`, `hypothesis`
  - Create `.env.example` with `GEMINI_API_KEY=your_key_here`
  - Create `README.md` with setup, run, test, and API usage instructions
  - Create empty package files: `main.py`, `data_loader.py`, `intent_classifier.py`, `query_engine.py`, `answer_builder.py`
  - Create `tests/` directory with empty `conftest.py`, `test_data_loader.py`, `test_intent_classifier.py`, `test_query_engine.py`, `test_answer_builder.py`, `test_api.py`
  - Create `frontend/` and `docs/` directories
  - _Requirements: 10.1, 10.5, 10.6_

- [ ] 2. Data loading pipeline
  - [ ] 2.1 Implement `data_loader.init_db()`
    - Create all three SQLite tables (`sales_raw`, `sales`, `rejected_rows`) by dropping and recreating on every call
    - Read `data/sales.csv` row by row and insert verbatim into `sales_raw`
    - Apply rejection rules in order: `duplicate_transaction_id`, `returned`, `missing_price`, `quantity_zero`, `unparseable_date`; write rejected rows with reason to `rejected_rows`
    - For valid rows compute `order_date_iso` (YYYY-MM-DD), `month` (YYYY-MM), and `revenue` (Quantity * Unit_price - Discount_amount); insert into `sales`
    - Raise `RuntimeError` with a clear message if `data/sales.csv` is missing at startup
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [ ]* 2.2 Write property test for date conversion round-trip (Property 1)
    - **Property 1: Date Conversion Round-Trip**
    - **Validates: Requirements 1.2, 1.3**
    - Use `hypothesis` to generate arbitrary DD-MM-YYYY date strings and assert the produced `YYYY-MM` month string matches the original calendar month

  - [ ]* 2.3 Write property test for revenue formula invariant (Property 2)
    - **Property 2: Revenue Formula Invariant**
    - **Validates: Requirements 1.4**
    - Use `hypothesis` to generate arbitrary positive `Quantity`, non-negative `Unit_price`, and non-negative `Discount_amount`, insert a synthetic row, and assert `revenue == Quantity * Unit_price - Discount_amount`

  - [ ]* 2.4 Write property test for rejection completeness (Property 3)
    - **Property 3: Rejection Completeness**
    - **Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6**
    - Use `hypothesis` to generate rows that violate at least one rule and assert each appears in `rejected_rows` and not in `sales`

  - [ ]* 2.5 Write unit tests for `data_loader`
    - Assert exactly 48 rows in `sales` and 3 rows in `rejected_rows` from `data/sales.csv`
    - Assert TXN0033 → reason `returned`, TXN0034 → reason `quantity_zero`, TXN0051 → reason `missing_price`
    - Assert total revenue across `sales` equals 1,439,200
    - _Requirements: 1.6, 1.7, 1.8, 1.9, 1.10_

- [ ] 3. Checkpoint — data pipeline
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. Query engine
  - [ ] 4.1 Implement `query_engine.execute()`
    - Define `QUERIES` dict with all seven parameterized SQL templates (`total_revenue`, `top_product`, `monthly_trend`, `top_region`, `compare_months`, `revenue_by_category`, `revenue_by_channel`)
    - Open database in read-only mode using `sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)` for every call
    - For `compare_months`: resolve `month_a`/`month_b` params, run SQL with `?` placeholders, then compute `absolute_difference` and `percentage_change` as post-query arithmetic
    - Return a `QueryResult` dataclass with `intent`, `params`, `sql`, `rows`, `computed`, `warnings`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11_

  - [ ]* 4.2 Write property test for aggregation correctness (Property 4)
    - **Property 4: Aggregation Correctness**
    - **Validates: Requirements 3.1, 3.3, 3.6, 3.7**
    - Use `hypothesis` to generate arbitrary sets of valid rows, load them into an in-memory DB, and assert sub-totals from grouping queries sum to the `total_revenue` result

  - [ ]* 4.3 Write property test for top-N supremacy (Property 5)
    - **Property 5: Top-N Supremacy**
    - **Validates: Requirements 3.2, 3.4**
    - Use `hypothesis` to generate arbitrary valid row sets and assert the returned top product / top region has revenue ≥ every other product / region in the set

  - [ ]* 4.4 Write property test for month comparison arithmetic (Property 6)
    - **Property 6: Month Comparison Arithmetic**
    - **Validates: Requirements 3.5**
    - Use `hypothesis` to generate two distinct months and arbitrary revenue rows and assert `absolute_difference == rev_B - rev_A` and `percentage_change == (rev_B - rev_A) / rev_A * 100` within floating-point tolerance

  - [ ]* 4.5 Write unit tests for `query_engine`
    - Test all 7 intents return correct results from the shared test DB
    - Assert top product is Monitor with revenue 473,000
    - Assert top region is South with revenue 411,200
    - Assert monthly trend returns 6 months with May 2026 revenue 318,500
    - Assert compare 2026-04 vs 2026-05 returns absolute change +77,800 and percentage change +32.3%
    - Assert that a write operation on the read-only connection raises `sqlite3.OperationalError`
    - _Requirements: 3.1–3.11, 8.4, 9.1_

- [ ] 5. Intent classifier
  - [ ] 5.1 Implement `intent_classifier.classify()`
    - Apply SQL injection guard (case-insensitive check for DROP, DELETE, INSERT, UPDATE, ALTER, CREATE, TRUNCATE) before any classification; return `unsupported` immediately if matched
    - Call Gemini API with the structured prompt; parse response with `json.loads()`; on any exception fall back to `Keyword_Matcher`
    - Validate returned `intent` against `SUPPORTED_INTENTS`; validate all param values against whitelist of products, regions, and months derived from the `sales` table
    - For `compare_months` validate `month_a`/`month_b` match `YYYY-MM` regex and exist in the `sales` table months set
    - Implement `Keyword_Matcher` regex fallback for all 7 intents
    - Return a `ClassificationResult` dataclass with `intent`, `params`, `source`
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 8.2, 8.3_

  - [ ]* 5.2 Write property test for whitelist enforcement (Property 8)
    - **Property 8: Whitelist Enforcement**
    - **Validates: Requirements 4.2, 4.6**
    - Use `hypothesis` to generate arbitrary param values not in the whitelist and assert the final intent is always `unsupported`

  - [ ]* 5.3 Write property test for SQL injection safety (Property 10)
    - **Property 10: SQL Injection Safety**
    - **Validates: Requirements 4.7, 8.1, 8.3**
    - Use `hypothesis` to generate question strings containing SQL DML/DDL keywords and assert the classifier always returns `unsupported` without calling the query engine

  - [ ]* 5.4 Write unit tests for `intent_classifier`
    - Test Gemini happy path (mock API returning valid JSON) → correct intent and params
    - Test Gemini returns non-JSON → fallback to `Keyword_Matcher`
    - Test Gemini unavailable (network error) → fallback to `Keyword_Matcher`
    - Test each `Keyword_Matcher` pattern maps to the correct intent
    - Test SQL injection attempt "DROP TABLE sales" → intent `unsupported`
    - Test param value not in whitelist → intent `unsupported`
    - _Requirements: 4.1–4.7, 8.2, 8.3, 9.1, 9.2, 9.3_

- [ ] 6. Answer builder
  - [ ] 6.1 Implement `answer_builder.build()`
    - Implement all 7 answer text templates driven purely from computed numbers in `QueryResult`
    - Implement the `unsupported` message that lists all 7 supported intent names
    - Handle graceful message for `compare_months` when a requested month is absent from the dataset
    - Return a dict matching the `AskResponse` schema fields: `answer`, `intent`, `params`, `sql`, `supporting_data`, `warnings`
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [ ]* 6.2 Write property test for response schema completeness (Property 7)
    - **Property 7: Response Schema Completeness**
    - **Validates: Requirements 3.10, 3.11, 5.4**
    - Use `hypothesis` to generate arbitrary supported intents and assert the returned dict always contains all six required fields and `sql` is non-empty

  - [ ]* 6.3 Write property test for unsupported intent listing (Property 11)
    - **Property 11: Unsupported Intent Listing**
    - **Validates: Requirements 5.2**
    - Use `hypothesis` (or parameterised test) to generate questions that resolve to `unsupported` and assert the `answer` field references all 7 supported intent names

  - [ ]* 6.4 Write unit tests for `answer_builder`
    - Assert answer text for each of the 7 intents matches expected format
    - Assert `unsupported` response contains all 7 intent names
    - Assert `compare_months` with missing month returns a graceful message
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [ ] 7. Checkpoint — core components
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. FastAPI application and wiring
  - [ ] 8.1 Implement `main.py` with lifespan, routes, and error handling
    - Wire `lifespan` context manager to call `data_loader.init_db()` on startup
    - Implement `POST /ask`: validate `AskRequest`, call `classify()` → `execute()` → `build()`, return `AskResponse`
    - Implement `GET /health` returning HTTP 200
    - Implement `GET /data-quality` returning all `rejected_rows`
    - Implement `GET /` serving `frontend/index.html`
    - Add global exception handler returning HTTP 500 `{"error": "Internal server error"}` with no stack trace
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [ ]* 8.2 Write property test for input validation rejection (Property 9)
    - **Property 9: Input Validation Rejection**
    - **Validates: Requirements 6.2, 6.3**
    - Use `hypothesis` to generate empty/whitespace strings and strings > 500 chars, POST them to `/ask`, and assert the response is HTTP 4xx and no DB query executes

  - [ ]* 8.3 Write integration tests for API endpoints
    - Test `POST /ask` with a valid question → 200 with all 6 response fields
    - Test empty question → 422 with no stack trace
    - Test question > 500 chars → 422 with no stack trace
    - Test "What's the weather?" → 200 with `intent == "unsupported"`
    - Test unhandled exception path → 500 with no stack trace and no internal details
    - Test `GET /health` → 200
    - Test `GET /data-quality` → 200 with 3 rejected rows
    - _Requirements: 6.1–6.6, 9.1_

- [ ] 9. Frontend
  - [ ] 9.1 Implement `frontend/index.html`
    - Single-page layout with text input, "Ask" button, and example-question chips for all 7 supported intents
    - On submit: POST to `/ask`, display answer in an answer card, render supporting data in a table, show SQL in a collapsible "SQL used" section
    - For `monthly_trend` intent: render a CSS bar chart (flexbox/grid + inline `height` % of max revenue) with no external library
    - All styling inline CSS; all JS vanilla ES2020; no CDN or npm dependencies
    - Serve from FastAPI at `/`
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_

- [ ] 10. Documentation
  - [ ] 10.1 Write `docs/ARCHITECTURE.md`
    - Include a Mermaid component diagram and explanation of storage layout and query path
    - _Requirements: 10.2_

  - [ ] 10.2 Write `docs/AI_USAGE.md`
    - Describe how Gemini is called, the exact prompt sent, what is validated, and the fallback strategy
    - _Requirements: 10.3_

  - [ ] 10.3 Write `docs/LIMITATIONS.md`
    - Describe known limitations, out-of-scope question types, and unsupported intents
    - _Requirements: 10.4_

- [ ] 11. Final checkpoint — full test suite
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation before moving to the next layer
- Property tests validate universal correctness invariants (Properties 1–11 from the design)
- Unit tests validate specific expected outcomes from the 51-row `data/sales.csv`
- All Gemini API calls are mocked in tests using `unittest.mock.patch` for determinism

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4", "2.5"] },
    { "id": 3, "tasks": ["4.1"] },
    { "id": 4, "tasks": ["4.2", "4.3", "4.4", "4.5", "5.1"] },
    { "id": 5, "tasks": ["5.2", "5.3", "5.4", "6.1"] },
    { "id": 6, "tasks": ["6.2", "6.3", "6.4", "8.1"] },
    { "id": 7, "tasks": ["8.2", "8.3", "9.1"] },
    { "id": 8, "tasks": ["10.1", "10.2", "10.3"] }
  ]
}
```
