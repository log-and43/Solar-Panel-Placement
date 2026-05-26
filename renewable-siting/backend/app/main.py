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
from .polygons import source_status as polygons_status
from .pvwatts import cache_stats, has_api_key
from .regions import list_available, list_states, search
from .schemas import AnalyzeRequest, AnalyzeResponse


app = FastAPI(
    title="Renewable Siting Tool",
    description="Phase 4 — real polygons from Overture + OSM.",
    version="0.4.0",
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
    from .data_store import data_available
    return {
        "status": "ok",
        "phase": 2 if data_available() else 1,
        "data_built": data_available(),
    }


@app.get("/regions")
def regions() -> list[dict]:
    """Legacy Phase-1 endpoint. Frontend now uses /search and /states."""
    return list_available()


@app.get("/states")
def states_endpoint() -> list[dict]:
    """All states with data. Powers the state dropdown in the picker."""
    return list_states()


@app.get("/search")
def search_endpoint(
    region_type: str,
    q: str = "",
    state: str | None = None,
    limit: int = 25,
) -> list[dict]:
    """
    Typeahead search.
    Query params:
      region_type: 'county' or 'city' (required)
      q:           substring (empty → top results in state, by population)
      state:       2-letter state abbr; if None, search all states
      limit:       max results (default 25)
    """
    return search(state=state, region_type=region_type, query=q, limit=limit)


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze_endpoint(req: AnalyzeRequest) -> AnalyzeResponse:
    try:
        return analyze(req)
    except RegionNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/pvwatts/status")
def pvwatts_status() -> dict:
    """
    Diagnostic for the PVWatts integration. Lets the frontend show whether
    real solar data is active, and lets ops see how warm the cache is.
    """
    stats = cache_stats()
    return {
        "api_key_configured": has_api_key(),
        "cache": stats,
    }


@app.get("/polygons/status")
def polygons_status_endpoint() -> dict:
    """
    Diagnostic for the Phase 4 polygon sources. Reports whether the
    Overture stack is installed and how many regions are cached.
    """
    return polygons_status()
