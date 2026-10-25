# Limitations

## Known Limitations

### Data Scope
- **Single CSV file**: The system only analyzes data from `data/sales.csv`
- **Static data**: Data is reloaded from CSV on every app startup; no live updates
- **51 transactions total**: Limited to the specific dataset provided (48 valid + 3 rejected)

### Supported Questions
The assistant can answer **only** these 7 question types:
1. Total revenue across all sales
2. Top product by revenue
3. Monthly revenue trend (time series)
4. Top region by revenue
5. Month-to-month revenue comparison (requires two specific YYYY-MM values)
6. Revenue breakdown by category
7. Revenue breakdown by sales channel

### Out-of-Scope Questions

❌ **Cannot answer**:
- Forecasting / predictions ("What will revenue be next month?")
- Profit calculations (no cost data available)
- Customer analysis (no customer data in the dataset)
- Weather, external events, market conditions
- Questions about individual transactions by ID (designed for aggregates only)
- Time periods not in the data (e.g., months before 2026-01 or after 2026-06)
- Comparisons across >2 months simultaneously
- "Why" questions requiring business context ("Why did sales drop?")

### Technical Limitations
- **Gemini API dependency**: If the API key is invalid or the service is down, the system falls back to keyword matching (less flexible)
- **Exact month format required**: Month comparisons need YYYY-MM format (e.g., "2026-05", not "May 2026" or "May")
- **No authentication**: The app has no user login or access control
- **Single-user**: Designed for local/demo use, not concurrent production traffic
- **No persistent state**: Database is rebuilt from scratch on every restart

### Query Constraints
- **Read-only**: No ability to update, delete, or insert data via questions
- **Aggregate focus**: Designed for summary statistics, not row-level details
- **Fixed SQL templates**: Only the 7 pre-defined query patterns are supported

## Supported vs Unsupported Examples

✅ **Supported**:
- "What is the total revenue?"
- "Show me monthly revenue"
- "Compare 2026-04 and 2026-05"
- "Which product made the most money?"

❌ **Unsupported**:
- "What will next quarter look like?" (forecasting)
- "Show me profit margins" (no cost data)
- "What's the weather in the South region?" (out of scope)
- "Why did Monitor sales increase?" (requires external context)
