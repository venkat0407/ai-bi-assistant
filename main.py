# main.py
from contextlib import asynccontextmanager
from typing import List, Dict, Any

import sqlite3
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator

from data_loader import init_db
from intent_classifier import classify
from query_engine import execute
from answer_builder import build


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: load CSV into SQLite."""
    print("Loading data from CSV...")
    init_db()
    print("Data loaded successfully.")
    yield


app = FastAPI(lifespan=lifespan)


class AskRequest(BaseModel):
    question: str
    
    @field_validator("question")
    @classmethod
    def validate_question(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("question must not be empty or whitespace")
        if len(stripped) > 500:
            raise ValueError("question must not exceed 500 characters")
        return stripped


class AskResponse(BaseModel):
    answer: str
    intent: str
    params: Dict[str, Any]
    sql: str
    supporting_data: List[Dict[str, Any]]
    warnings: List[str]


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch all unhandled exceptions and return 500 with no stack trace."""
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"}
    )


@app.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest):
    """Process a natural-language business question."""
    # Classify intent
    classification = classify(req.question)
    
    # If unsupported, return immediately
    if classification.intent == "unsupported":
        query_result = type("obj", (), {
            "intent": "unsupported",
            "params": {},
            "sql": "",
            "rows": [],
            "computed": {},
            "warnings": []
        })()
        response_dict = build(query_result)
        return AskResponse(**response_dict)
    
    # Execute query
    query_result = execute(classification.intent, classification.params)
    
    # Build answer
    response_dict = build(query_result)
    
    return AskResponse(**response_dict)


@app.get("/health")
async def health():
    """Liveness probe."""
    return {"status": "ok"}


@app.get("/data-quality")
async def data_quality():
    """Return all rejected rows with their reasons."""
    conn = sqlite3.connect("bi_assistant.db")
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute("SELECT * FROM rejected_rows")
        rows = [dict(row) for row in cursor.fetchall()]
        return {"rejected_rows": rows}
    finally:
        conn.close()


@app.get("/")
async def root():
    """Serve the frontend."""
    return FileResponse("frontend/index.html")
