# AI Usage

## Gemini API Integration

### When It's Called

The Gemini API is called on **every** `/ask` request as the primary classification method.

### Prompt Template

```
You are a BI assistant. Classify the following business question into one intent.

Respond with ONLY a JSON object with two keys:
- "intent": one of [total_revenue, top_product, monthly_trend, top_region, compare_months, revenue_by_category, revenue_by_channel, unsupported]
- "params": an object (empty {} if not needed; for compare_months include "month_a" and "month_b" as YYYY-MM strings)

Question: <user question>
```

### Model

- **Model**: `gemini-2.0-flash-exp`
- **Library**: `google-generativeai` (Python SDK)
- **API Key**: Loaded from `GEMINI_API_KEY` environment variable

### Response Handling

1. Parse response as JSON using `json.loads(response.text)`
2. Extract `intent` and `params` keys
3. Validate `intent` is in the supported set or equals `"unsupported"`
4. For `compare_months`: validate `month_a` and `month_b` are YYYY-MM format and present in the DB
5. Validate all param values against a whitelist of known products, regions, and months

### Fallback Strategy

If the Gemini API:
- Is unavailable (network error, timeout)
- Returns non-JSON content
- Returns invalid JSON structure
- Raises any exception

...the system **immediately falls back** to the keyword/regex matcher with no retry.

### What Gemini Does NOT Do

- **Generate numeric answers** — all revenue figures come from SQL query results
- **Write SQL** — SQL templates are fixed in code; Gemini only classifies intent
- **Access the database** — Gemini has no direct DB access

## Keyword Matcher (Fallback)

Uses regex patterns to match common question phrasings:
- `"total.*revenue"` → total_revenue
- `"top.*product"` → top_product
- `"compare.*2026-04.*2026-05"` → compare_months (extracts YYYY-MM groups)
- etc.

The keyword matcher is deterministic and does not require an API key.
