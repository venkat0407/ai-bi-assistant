# Requirements Document

## Introduction

A Mini AI Business Intelligence Assistant built in Python 3.10+ using FastAPI, SQLite, and the Gemini API. The application loads sales transaction data from a CSV file into a SQLite database on startup, exposes a REST API for natural-language business questions, classifies questions via Gemini into parameterized query intents, executes deterministic SQL against cleaned data, and serves a single-page HTML/JS frontend with answers, supporting data, and trend charts.

## Glossary

- **System**: The AI BI Assistant application as a whole
- **Data_Loader**: The component that reads `data/sales.csv`, cleans data, and populates SQLite tables on startup
- **Sales_Raw**: The SQLite table `sales_raw` holding all rows from the CSV exactly as read
- **Sales**: The SQLite table `sales` holding only valid, cleaned rows with computed columns
- **Rejected_Rows**: The SQLite table `rejected_rows` holding invalid rows with a `reason` column
- **Query_Engine**: The component that executes parameterized SQL templates against the `sales` table
- **Intent_Classifier**: The component that calls the Gemini API to classify a natural-language question into an intent and params object
- **Keyword_Matcher**: The regex/keyword fallback classifier used when the Gemini API is unavailable or returns invalid JSON
- **Answer_Builder**: The component that generates human-readable answer text from computed numbers
- **Frontend**: The single-page HTML/JS UI served by FastAPI at the root path
- **Revenue**: Computed as `Quantity * Unit_price - Discount_amount` for each row
- **Supported_Intent**: One of `total_revenue`, `top_product`, `monthly_trend`, `top_region`, `compare_months`, `revenue_by_category`, `revenue_by_channel`

## Requirements

### Requirement 1: Data Loading and Initialization

**User Story:** As a system operator, I want the application to load and clean the CSV on startup, so that queries always run against fresh, consistent data.

#### Acceptance Criteria

1. WHEN the application starts, THE Data_Loader SHALL read all rows from `data/sales.csv` and insert them into the `Sales_Raw` table.
2. WHEN the application starts, THE Data_Loader SHALL convert each `Order_date` value from `DD-MM-YYYY` format to ISO `YYYY-MM-DD` format and store it in the `Sales` table.
3. WHEN the application starts, THE Data_Loader SHALL compute and store a `month` column in format `YYYY-MM` derived from the converted `Order_date` for each valid row in the `Sales` table.
4. WHEN the application starts, THE Data_Loader SHALL compute and store a `revenue` column as `Quantity * Unit_price - Discount_amount` for each valid row in the `Sales` table.
5. WHEN the application starts, THE Data_Loader SHALL recreate all tables from scratch, so that the database is stateless and always reflects the current CSV.
6. WHEN the application starts and all 51 CSV rows are processed, THE Data_Loader SHALL produce exactly 48 rows in the `Sales` table and exactly 3 rows in the `Rejected_Rows` table.
7. THE Data_Loader SHALL insert `TXN0033` into `Rejected_Rows` with reason `returned`.
8. THE Data_Loader SHALL insert `TXN0034` into `Rejected_Rows` with reason `quantity_zero`.
9. THE Data_Loader SHALL insert `TXN0051` into `Rejected_Rows` with reason `missing_price`.
10. THE System SHALL compute total revenue across all valid rows as 1,439,200.

### Requirement 2: Data Validation Rules

**User Story:** As a data analyst, I want invalid rows to be rejected and logged with a reason, so that my analytics are based on trustworthy data.

#### Acceptance Criteria

1. IF a row has `Quantity` less than or equal to 0, THEN THE Data_Loader SHALL reject that row with reason `quantity_zero`.
2. IF a row has a missing `Unit_price` or a `Unit_price` less than 0, THEN THE Data_Loader SHALL reject that row with reason `missing_price`.
3. IF a row has an `Order_date` that cannot be parsed as `DD-MM-YYYY`, THEN THE Data_Loader SHALL reject that row with reason `unparseable_date`.
4. IF a row has a `Transaction_Id` that duplicates an already-processed row, THEN THE Data_Loader SHALL reject the duplicate row with reason `duplicate_transaction_id`.
5. IF a row has `Status` equal to `Returned`, THEN THE Data_Loader SHALL reject that row with reason `returned` and exclude it from revenue calculations.
6. THE Data_Loader SHALL store all rejected rows in the `Rejected_Rows` table with the original row data and the applicable reason string.

### Requirement 3: Analytics Query Engine

**User Story:** As a business user, I want the system to answer analytics questions about my sales data, so that I can make data-driven decisions.

#### Acceptance Criteria

1. WHEN the intent is `total_revenue`, THE Query_Engine SHALL return the sum of the `revenue` column across all rows in the `Sales` table.
2. WHEN the intent is `top_product`, THE Query_Engine SHALL return the product with the highest total revenue and its revenue value.
3. WHEN the intent is `monthly_trend`, THE Query_Engine SHALL return total revenue grouped by `month` in ascending chronological order, covering all months present in the `Sales` table.
4. WHEN the intent is `top_region`, THE Query_Engine SHALL return the region with the highest total revenue and its revenue value.
5. WHEN the intent is `compare_months` with params `month_a` and `month_b`, THE Query_Engine SHALL return the total revenue for each month, the absolute difference, and the percentage change from `month_a` to `month_b`.
6. WHERE the intent is `revenue_by_category`, THE Query_Engine SHALL return total revenue grouped by `Category`.
7. WHERE the intent is `revenue_by_channel`, THE Query_Engine SHALL return total revenue grouped by `Sales_channel`.
8. THE Query_Engine SHALL use only parameterized SQL statements with `?` placeholders and SHALL NOT construct SQL strings from user-provided input.
9. THE Query_Engine SHALL execute all queries on a read-only SQLite connection.
10. THE Query_Engine SHALL include the exact SQL statement used in every response.
11. THE Query_Engine SHALL include the supporting rows returned by the SQL query in every response.

### Requirement 4: AI Intent Classification

**User Story:** As a user asking natural-language questions, I want the system to understand my intent, so that I receive relevant analytics answers.

#### Acceptance Criteria

1. WHEN a question is received, THE Intent_Classifier SHALL call the Gemini API and request a JSON response containing exactly `intent` and `params` fields.
2. WHEN the Gemini API returns a valid JSON response, THE Intent_Classifier SHALL validate that `intent` is one of the Supported_Intent values or `unsupported`.
3. WHEN the Gemini API returns a valid JSON response with intent `compare_months`, THE Intent_Classifier SHALL validate that `month_a` and `month_b` params match the format `YYYY-MM` and fall within the date range present in the `Sales` table.
4. IF the Gemini API is unavailable or returns a response that is not valid JSON, THEN THE Keyword_Matcher SHALL classify the question using regex and keyword rules.
5. IF the Gemini API returns a JSON response where `intent` is not a Supported_Intent and not `unsupported`, THEN THE Intent_Classifier SHALL treat the intent as `unsupported`.
6. IF the Gemini API returns params containing values not in the whitelist of known products, regions, and valid month strings, THEN THE Intent_Classifier SHALL treat the intent as `unsupported`.
7. THE Intent_Classifier SHALL never pass raw user input as SQL or SQL fragments to the Query_Engine.

### Requirement 5: Answer Generation

**User Story:** As a user, I want clear, accurate answers generated from computed data, so that I can trust the numbers presented.

#### Acceptance Criteria

1. THE Answer_Builder SHALL generate all human-readable answer text from computed numeric results and SHALL NOT use LLM-generated text for numeric values.
2. WHEN the intent is `unsupported`, THE Answer_Builder SHALL return a clear message listing the Supported_Intent values that the user can ask about.
3. WHEN the intent is `compare_months` and a requested month is not present in the `Sales` table, THE Answer_Builder SHALL return a graceful message indicating the month is not in the dataset.
4. WHEN intent classification succeeds, THE Answer_Builder SHALL include `answer`, `intent`, `params`, `sql`, `supporting_data`, and `warnings` fields in the response.

### Requirement 6: REST API

**User Story:** As a developer or frontend client, I want a well-defined REST API, so that I can integrate questions and retrieve answers programmatically.

#### Acceptance Criteria

1. THE System SHALL expose a `POST /ask` endpoint that accepts a JSON body with a `question` field of type string and returns a JSON response with `answer`, `intent`, `params`, `sql`, `supporting_data`, and `warnings` fields.
2. IF the `question` field in a `POST /ask` request is empty or contains only whitespace, THEN THE System SHALL return an HTTP 422 response with a JSON error message and SHALL NOT return a stack trace.
3. IF the `question` field in a `POST /ask` request exceeds 500 characters, THEN THE System SHALL return an HTTP 422 response with a JSON error message and SHALL NOT return a stack trace.
4. THE System SHALL expose a `GET /health` endpoint that returns an HTTP 200 response confirming the application is running.
5. THE System SHALL expose a `GET /data-quality` endpoint that returns the list of all rows in the `Rejected_Rows` table with their reasons.
6. IF an unhandled internal error occurs during request processing, THEN THE System SHALL return an HTTP 500 response with a JSON error message and SHALL NOT expose a stack trace or internal details.

### Requirement 7: Frontend User Interface

**User Story:** As a business user, I want a simple web interface, so that I can ask questions and view answers without writing code.

#### Acceptance Criteria

1. THE Frontend SHALL present a single-page interface with a text input field, an "Ask" button, and a set of example-question chips that pre-fill the text input when clicked.
2. WHEN a question is submitted, THE Frontend SHALL display the answer text in an answer card.
3. WHEN a response is received, THE Frontend SHALL display the supporting data rows in a table.
4. THE Frontend SHALL include a collapsible section labeled "SQL used" that shows the SQL statement from the response.
5. WHEN the intent is `monthly_trend`, THE Frontend SHALL render a CSS bar chart of revenue by month using plain HTML and CSS with no external chart library.
6. THE Frontend SHALL be served as a static HTML file by FastAPI at the root path `/`.
7. THE Frontend SHALL use only plain HTML and CSS and SHALL NOT depend on any external JavaScript or CSS library loaded from a CDN or npm.

### Requirement 8: Security and Safety

**User Story:** As a system operator, I want the application to be safe from injection attacks and data leakage, so that the database and user data are protected.

#### Acceptance Criteria

1. THE Query_Engine SHALL use only parameterized SQL with `?` placeholders and SHALL NEVER construct a SQL string from user-provided text.
2. THE System SHALL validate all intent and param values against a whitelist before executing any query.
3. IF a question contains SQL keywords such as `DROP`, `DELETE`, `INSERT`, `UPDATE`, or `ALTER`, THEN THE Intent_Classifier SHALL classify the intent as `unsupported` and SHALL NOT execute any database statement.
4. THE Query_Engine SHALL open the SQLite database in read-only mode for all query operations.

### Requirement 9: Testing

**User Story:** As a developer, I want a comprehensive test suite, so that I can verify correctness and prevent regressions.

#### Acceptance Criteria

1. THE System SHALL include at least 8 pytest test cases covering: total revenue equals 1,439,200; top product is Monitor with revenue 473,000; top region is South with revenue 411,200; monthly trend returns 6 months with May 2026 revenue equal to 318,500; compare 2026-04 vs 2026-05 returns absolute change +77,800 and percentage change +32.3%; empty question returns a 4xx HTTP response; "What's the weather?" returns an unsupported intent response; compare with month 2026-09 (not in data) returns a graceful message; data cleaning rejects TXN0033, TXN0034, and TXN0051; and a SQL injection attempt of "DROP TABLE sales" never reaches the database.
2. THE System SHALL mock the Gemini API in all tests so that tests are deterministic and do not require a live API key.
3. THE System SHALL include tests that verify parameterized SQL is used and that no raw user input reaches the database layer.

### Requirement 10: Documentation and Project Structure

**User Story:** As a developer onboarding to the project, I want complete documentation, so that I can set up, run, and understand the system quickly.

#### Acceptance Criteria

1. THE System SHALL include a `README.md` at the project root with setup instructions, run instructions, test instructions, and API usage examples.
2. THE System SHALL include `docs/ARCHITECTURE.md` containing a Mermaid diagram and an explanation of the storage layout and query path.
3. THE System SHALL include `docs/AI_USAGE.md` describing how the Gemini API is used, what prompts are sent, and what is validated.
4. THE System SHALL include `docs/LIMITATIONS.md` describing known limitations, out-of-scope questions, and unsupported intents.
5. THE System SHALL include a `requirements.txt` listing all Python dependencies with pinned versions.
6. THE System SHALL include a `.env.example` file showing the required environment variables, including the Gemini API key variable, without revealing actual secret values.
