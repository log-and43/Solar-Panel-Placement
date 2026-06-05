"""
FastAPI entrypoint.

Two endpoints in Phase 1:
- GET  /regions   → for the frontend dropdowns
- POST /analyze   → the spine endpoint
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .affordability import compute_buildout, status as affordability_status
from .pipeline import RegionNotFound, analyze
from .polygons import source_status as polygons_status
from .pvwatts import cache_stats, has_api_key
from .regions import RegionNotFound as _RNF, list_available, list_states, lookup, search
from .schemas import (
    AffordabilityRequest,
    AffordabilityResponse,
    AnalyzeRequest,
    AnalyzeResponse,
)


app = FastAPI(
    title="Renewable Siting Tool",
    description="Phase 5 — affordability / realism estimate.",
    version="0.5.0",
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


@app.get("/affordability/status")
def affordability_status_endpoint() -> dict:
    """Diagnostic for the Phase 5 affordability model."""
    return affordability_status()


@app.post("/affordability", response_model=AffordabilityResponse)
def affordability_endpoint(req: AffordabilityRequest) -> AffordabilityResponse:
    """
    Compute the low/high build-out + CO2 ranges for a region given budget
    sliders. Lightweight — does NOT re-run the polygon/PVWatts pipeline.
    The frontend calls this on slider changes.
    """
    try:
        record = lookup(req.state, req.region_type, req.region_name)
    except _RNF as e:
        raise HTTPException(status_code=404, detail=str(e))

    result = compute_buildout(
        record,
        budget_dollars=req.budget_dollars,
        allocation_pct=req.allocation_pct,
        horizon_years=req.horizon_years,
        capacity_factor=req.capacity_factor,
        grid_co2_tons_per_mwh=req.grid_co2_tons_per_mwh,
    )

    if result is None:
        return AffordabilityResponse(
            available=False,
            notes=["No budget data available for this region, and none was "
                   "provided. Build the Phase 5 finance data or enter a "
                   "budget manually."],
        )

    return AffordabilityResponse(
        available=True,
        installed_mw_low=result.installed_mw_low,
        installed_mw_high=result.installed_mw_high,
        annual_gwh_low=result.annual_gwh_low,
        annual_gwh_high=result.annual_gwh_high,
        co2_tons_per_year_low=result.co2_tons_per_year_low,
        co2_tons_per_year_high=result.co2_tons_per_year_high,
        co2_tons_cumulative_low=result.co2_tons_cumulative_low,
        co2_tons_cumulative_high=result.co2_tons_cumulative_high,
        budget_dollars=result.budget_dollars,
        allocation_pct=result.allocation_pct,
        horizon_years=result.horizon_years,
        capacity_factor=result.capacity_factor,
        grid_co2_tons_per_mwh=result.grid_co2_tons_per_mwh,
        cost_per_watt_low=result.cost_per_watt_low,
        cost_per_watt_high=result.cost_per_watt_high,
        source=result.source,
        notes=result.notes,
    )
