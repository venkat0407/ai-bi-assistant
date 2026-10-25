# answer_builder.py
from typing import Dict, List, Any
from query_engine import QueryResult


def build(result: QueryResult) -> Dict[str, Any]:
    """Build a user-facing answer dict from a QueryResult."""
    intent = result.intent
    rows = result.rows
    computed = result.computed
    warnings = result.warnings.copy()
    
    answer = ""
    
    if intent == "total_revenue":
        total = rows[0]["total_revenue"] if rows else 0
        answer = f"Total revenue across all sales is £{total:,.0f}."
    
    elif intent == "top_product":
        if rows:
            product = rows[0]["product"]
            revenue = rows[0]["revenue"]
            answer = f"The top product is {product} with total revenue of £{revenue:,.0f}."
        else:
            answer = "No products found."
    
    elif intent == "monthly_trend":
        if rows:
            trend_parts = [f"{r['month']}: £{r['revenue']:,.0f}" for r in rows]
            answer = "Monthly revenue trend: " + ", ".join(trend_parts) + "."
        else:
            answer = "No monthly data available."
    
    elif intent == "top_region":
        if rows:
            region = rows[0]["region"]
            revenue = rows[0]["revenue"]
            answer = f"The top region is {region} with total revenue of £{revenue:,.0f}."
        else:
            answer = "No regions found."
    
    elif intent == "compare_months":
        month_a = result.params.get("month_a", "")
        month_b = result.params.get("month_b", "")
        
        if "rev_a" in computed and "rev_b" in computed:
            rev_a = computed["rev_a"]
            rev_b = computed["rev_b"]
            diff = computed["absolute_difference"]
            pct = computed.get("percentage_change")
            
            if pct is not None:
                answer = (f"Revenue for {month_a} was £{rev_a:,.0f} and for {month_b} was £{rev_b:,.0f}. "
                         f"Absolute change: £{diff:+,.0f}. Percentage change: {pct:+.1f}%.")
            else:
                answer = (f"Revenue for {month_a} was £{rev_a:,.0f} and for {month_b} was £{rev_b:,.0f}. "
                         f"Absolute change: £{diff:+,.0f}. (Percentage change unavailable.)")
        else:
            # One or both months missing
            if month_a and month_b:
                answer = f"Unable to compare {month_a} and {month_b}. One or both months are not in the dataset."
            else:
                answer = "Unable to compare months. Please specify two valid months in YYYY-MM format."
    
    elif intent == "revenue_by_category":
        if rows:
            cat_parts = [f"{r['category']}: £{r['revenue']:,.0f}" for r in rows]
            answer = "Revenue by category: " + ", ".join(cat_parts) + "."
        else:
            answer = "No category data available."
    
    elif intent == "revenue_by_channel":
        if rows:
            chan_parts = [f"{r['sales_channel']}: £{r['revenue']:,.0f}" for r in rows]
            answer = "Revenue by sales channel: " + ", ".join(chan_parts) + "."
        else:
            answer = "No sales channel data available."
    
    elif intent == "unsupported":
        answer = ("I can answer questions about: total revenue, top product, monthly revenue trend, "
                 "top region, month-to-month comparisons, revenue by category, and revenue by sales channel. "
                 "Please rephrase your question to match one of these intents.")
    
    else:
        answer = "Unknown intent."
    
    return {
        "answer": answer,
        "intent": intent,
        "params": result.params,
        "sql": result.sql,
        "supporting_data": rows,
        "warnings": warnings
    }
