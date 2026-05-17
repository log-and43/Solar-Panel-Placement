"""
FastAPI entrypoint.

Two endpoints in Phase 1:
- GET  /regions   → for the frontend dropdowns
- POST /analyze   → the spine endpoint
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .pipeline import RegionNotFound, analyze
from .regions import list_available
from .schemas import AnalyzeRequest, AnalyzeResponse


app = FastAPI(
    title="Renewable Siting Tool",
    description="Phase 1 walking skeleton. See docs/CONTRACT.md.",
    version="0.1.0",
)

# Dev CORS: permissive for now. Lock down before any deploy.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "phase": 1}


@app.get("/regions")
def regions() -> list[dict]:
    """List regions the picker can offer. Phase 1: two entries."""
    return list_available()


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze_endpoint(req: AnalyzeRequest) -> AnalyzeResponse:
    try:
        return analyze(req)
    except RegionNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
