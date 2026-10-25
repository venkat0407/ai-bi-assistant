# AI BI Assistant

A Python 3.10+ web application that loads CSV sales data into SQLite on startup, classifies natural-language business questions via the Gemini API (with a keyword/regex fallback), executes deterministic parameterized SQL, and serves a plain HTML/JS single-page frontend.

## Prerequisites

- Python 3.10+
- A Google Gemini API key ([get one here](https://aistudio.google.com/))

## Setup

1. **Clone the repository and enter the project directory:**

   ```bash
   git clone <repo-url>
   cd ai-bi-assistant
   ```

2. **Create and activate a virtual environment:**

   ```bash
   python -m venv .venv

   # Windows
   .venv\Scripts\activate

   # macOS / Linux
   source .venv/bin/activate
   ```

3. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables:**

   ```bash
   cp .env.example .env
   ```

   Edit `.env` and replace `your_key_here` with your actual Gemini API key:

   ```
   GEMINI_API_KEY=your_actual_gemini_api_key
   ```

5. **Verify the data file is present:**

   ```
   data/sales.csv
   ```

## Running the Application

```bash
uvicorn main:app --reload
```

The app will be available at [http://localhost:8000](http://localhost:8000).

On startup the data loader reads `data/sales.csv`, validates all rows, and populates the SQLite database (`bi_assistant.db`). You will see log output confirming how many rows were loaded and rejected.

## Running Tests

```bash
pytest tests/ -v
```

To run only a specific test file:

```bash
pytest tests/test_data_loader.py -v
pytest tests/test_query_engine.py -v
pytest tests/test_intent_classifier.py -v
pytest tests/test_answer_builder.py -v
pytest tests/test_api.py -v
```

To run property-based tests with more examples:

```bash
pytest tests/ -v --hypothesis-seed=0
```

## API Usage

### POST /ask

Submit a natural-language business question.

**Request:**

```http
POST /ask
Content-Type: application/json

{
  "question": "What is the total revenue?"
}
```

**Response:**

```json
{
  "answer": "Total revenue across all sales is £1,439,200.",
  "intent": "total_revenue",
  "params": {},
  "sql": "SELECT ROUND(SUM(revenue), 2) AS total_revenue FROM sales",
  "supporting_data": [{"total_revenue": 1439200.0}],
  "warnings": []
}
```

**Validation:**
- `question` must not be empty or whitespace → HTTP 422
- `question` must not exceed 500 characters → HTTP 422

### GET /health

Liveness probe.

```http
GET /health
```

```json
{"status": "ok"}
```

### GET /data-quality

Returns all rows that were rejected during the data loading phase, with their rejection reasons.

```http
GET /data-quality
```

```json
{
  "rejected_rows": [
    {
      "transaction_id": "TXN0033",
      "reason": "returned",
      ...
    }
  ]
}
```

### Supported Question Types

| Intent | Example question |
|---|---|
| `total_revenue` | "What is the total revenue?" |
| `top_product` | "Which product had the highest revenue?" |
| `monthly_trend` | "Show me the monthly revenue trend." |
| `top_region` | "Which region performed best?" |
| `compare_months` | "Compare revenue for 2026-04 and 2026-05." |
| `revenue_by_category` | "Break down revenue by category." |
| `revenue_by_channel` | "What is revenue by sales channel?" |

## Project Structure

```
ai-bi-assistant/
├── main.py                  # FastAPI app, routes, lifespan
├── data_loader.py           # CSV → SQLite pipeline
├── intent_classifier.py     # Gemini + keyword fallback
├── query_engine.py          # Parameterized SQL execution
├── answer_builder.py        # Template-driven answer text
├── frontend/
│   └── index.html           # Single-page frontend
├── data/
│   └── sales.csv            # Input sales data
├── tests/
│   ├── conftest.py
│   ├── test_data_loader.py
│   ├── test_intent_classifier.py
│   ├── test_query_engine.py
│   ├── test_answer_builder.py
│   └── test_api.py
├── docs/
│   ├── ARCHITECTURE.md
│   ├── AI_USAGE.md
│   └── LIMITATIONS.md
├── README.md
├── requirements.txt
└── .env.example
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md) — component diagram and storage layout
- [AI Usage](docs/AI_USAGE.md) — how Gemini is called and validated
- [Limitations](docs/LIMITATIONS.md) — known limitations and out-of-scope questions
