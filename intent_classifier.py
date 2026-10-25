# intent_classifier.py
import json
import os
import re
import sqlite3
from dataclasses import dataclass
from typing import Dict, Set

from dotenv import load_dotenv

load_dotenv()

SUPPORTED_INTENTS = {
    "total_revenue", "top_product", "monthly_trend", "top_region",
    "compare_months", "revenue_by_category", "revenue_by_channel"
}

SQL_INJECTION_KEYWORDS = {"DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "CREATE", "TRUNCATE"}


@dataclass
class ClassificationResult:
    intent: str
    params: Dict
    source: str  # "gemini" | "keyword_matcher" | "guard"


def _sql_injection_guard(question: str) -> bool:
    """Return True if question contains SQL injection keywords."""
    upper_q = question.upper()
    return any(kw in upper_q for kw in SQL_INJECTION_KEYWORDS)


def _build_whitelist(db_path: str) -> Dict[str, Set[str]]:
    """Build whitelist of known products, regions, and months from the DB."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        products = {row[0] for row in conn.execute("SELECT DISTINCT product FROM sales")}
        regions = {row[0] for row in conn.execute("SELECT DISTINCT region FROM sales")}
        months = {row[0] for row in conn.execute("SELECT DISTINCT month FROM sales")}
        return {"products": products, "regions": regions, "months": months}
    finally:
        conn.close()


def _validate_params(intent: str, params: Dict, whitelist: Dict[str, Set[str]]) -> bool:
    """Validate params against whitelist for the given intent."""
    if intent == "unsupported":
        return True
    
    if intent == "compare_months":
        month_a = params.get("month_a", "")
        month_b = params.get("month_b", "")
        pattern = re.compile(r"^\d{4}-\d{2}$")
        
        if not pattern.match(month_a) or not pattern.match(month_b):
            return False
        if month_a not in whitelist["months"] or month_b not in whitelist["months"]:
            return False
    
    return True


def _keyword_matcher(question: str) -> ClassificationResult:
    """Fallback regex/keyword classifier."""
    q = question.lower()
    
    # compare_months - extract two YYYY-MM patterns
    compare_match = re.search(r"compare.*?(\d{4}-\d{2}).*?(\d{4}-\d{2})", q)
    if compare_match:
        return ClassificationResult(
            intent="compare_months",
            params={"month_a": compare_match.group(1), "month_b": compare_match.group(2)},
            source="keyword_matcher"
        )
    
    # Other patterns
    if re.search(r"total.*revenue|how much.*made|what.*revenue", q):
        return ClassificationResult("total_revenue", {}, "keyword_matcher")
    if re.search(r"top.*product|best.*product|highest.*product|product.*highest|product.*best", q):
        return ClassificationResult("top_product", {}, "keyword_matcher")
    if re.search(r"monthly.*trend|by month|month.*revenue|revenue.*month", q):
        return ClassificationResult("monthly_trend", {}, "keyword_matcher")
    if re.search(r"top.*region|best.*region|highest.*region", q):
        return ClassificationResult("top_region", {}, "keyword_matcher")
    if re.search(r"by.*category|revenue.*category|category.*revenue", q):
        return ClassificationResult("revenue_by_category", {}, "keyword_matcher")
    if re.search(r"by.*channel|revenue.*channel|channel.*revenue", q):
        return ClassificationResult("revenue_by_channel", {}, "keyword_matcher")
    
    return ClassificationResult("unsupported", {}, "keyword_matcher")


def _call_gemini(question: str) -> Dict:
    """Call Gemini API and return parsed JSON. Raises on any error."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set")
    
    import google.generativeai as genai
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.0-flash-exp")
    
    prompt = f"""You are a BI assistant. Classify the following business question into one intent.

Respond with ONLY a JSON object with two keys:
- "intent": one of [total_revenue, top_product, monthly_trend, top_region, compare_months, revenue_by_category, revenue_by_channel, unsupported]
- "params": an object (empty {{}} if not needed; for compare_months include "month_a" and "month_b" as YYYY-MM strings)

Question: {question}"""
    
    response = model.generate_content(prompt)
    return json.loads(response.text)


def classify(question: str, db_path: str = "bi_assistant.db") -> ClassificationResult:
    """Classify a question into an intent with params."""
    question = question.strip()
    
    # SQL injection guard
    if _sql_injection_guard(question):
        return ClassificationResult("unsupported", {}, "guard")
    
    # Try Gemini first
    try:
        result = _call_gemini(question)
        intent = result.get("intent", "unsupported")
        params = result.get("params", {})
        
        # Validate intent is supported
        if intent not in SUPPORTED_INTENTS and intent != "unsupported":
            intent = "unsupported"
            params = {}
        
        # Validate params against whitelist
        if intent != "unsupported":
            whitelist = _build_whitelist(db_path)
            if not _validate_params(intent, params, whitelist):
                intent = "unsupported"
                params = {}
        
        return ClassificationResult(intent, params, "gemini")
    
    except Exception:
        # Fall back to keyword matcher on any error
        return _keyword_matcher(question)
