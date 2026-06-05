"""
Pydantic schemas for the /analyze endpoint.

This module IS the API contract. If you find yourself wanting to change
a field shape here, stop and read docs/CONTRACT.md first. The frozen-shape
rule exists because the team has one developer and three collaborators
working in parallel — schema churn is expensive.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


# ---------- Request ----------

class AnalyzeRequest(BaseModel):
    state: str = Field(..., description="USPS 2-letter state code, continental US.")
    region_type: Literal["county", "city"]
    region_name: str

    @field_validator("state")
    @classmethod
    def _state_upper(cls, v: str) -> str:
        v = v.strip().upper()
        if len(v) != 2 or not v.isalpha():
            raise ValueError("state must be a 2-letter USPS code")
        return v

    @field_validator("region_name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("region_name cannot be empty")
        return v


# ---------- Response: region ----------

class Region(BaseModel):
    name: str
    type: Literal["county", "city"]
    state: str
    # bbox in [west, south, east, north] (lon/lat). Matches GeoJSON convention.
    bbox: tuple[float, float, float, float]
    # centroid in [lat, lon] for Leaflet convenience.
    centroid: tuple[float, float]
    is_coastal: bool


# ---------- Response: consumption ----------

class GenerationMix(BaseModel):
    coal: float = 0.0
    natural_gas: float = 0.0
    nuclear: float = 0.0
    hydro: float = 0.0
    wind: float = 0.0
    solar: float = 0.0
    other: float = 0.0

    @field_validator("*")
    @classmethod
    def _frac(cls, v: float) -> float:
        # Tolerate small floating drift but reject obviously wrong values.
        if v < -0.001 or v > 1.001:
            raise ValueError(f"mix fraction out of range: {v}")
        return max(0.0, min(1.0, v))


class Consumption(BaseModel):
    total_mwh_per_year: float
    fossil_mwh_per_year: float
    mix: GenerationMix
    source: str = Field(..., description="e.g. 'PHASE_1_HARDCODED' or 'eGRID 2023 + EIA SEDS 2022'.")


# ---------- Response: polygons (GeoJSON-ish) ----------
# We don't import geojson-pydantic; for our needs a permissive dict is fine
# and lets us pass through extra GeoJSON quirks unchanged.

PolygonCategory = Literal["rooftop", "parking", "offshore_wind_zone", "cv_detected_parking"]


class PolygonProperties(BaseModel):
    category: PolygonCategory
    area_m2: float
    est_annual_mwh: float
    suitability_score: float = Field(..., ge=0.0, le=1.0)
    # Where did the polygon shape come from? (e.g. "Phase 4 real polygons", "PHASE_1_HARDCODED")
    source: str = Field(default="PHASE_1_HARDCODED")
    # Where did the est_annual_mwh estimate come from? (e.g. PVWatts vs fallback)
    # Optional so older callers/tests don't break.
    generation_source: str | None = None


class PolygonFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    geometry: dict  # raw GeoJSON geometry; we don't validate further
    properties: PolygonProperties


class PolygonCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[PolygonFeature]


# ---------- Response: recommendation ----------

PrimaryTech = Literal["solar", "wind", "offshore_wind", "mixed", "insufficient"]


class Alternative(BaseModel):
    tech: Literal["solar", "onshore_wind", "offshore_wind", "hydro", "geothermal"]
    rationale: str
    potential_mwh: float


class Recommendation(BaseModel):
    primary: PrimaryTech
    covered_mwh_per_year: float
    gap_mwh_per_year: float
    alternatives: list[Alternative] = []
    notes: str = ""


# ---------- Response: economics ----------

class Economics(BaseModel):
    install_cost_usd: float
    annual_savings_usd: float
    payback_years: Optional[float]  # None if savings <= 0
    co2_avoided_tons_per_year: float


# ---------- Top-level response ----------

class AnalyzeResponse(BaseModel):
    region: Region
    consumption: Consumption
    polygons: PolygonCollection
    recommendation: Recommendation
    economics: Economics
    # Phase 7: per-field provenance strings for the economics numbers.
    # Optional so older callers/tests are unaffected.
    economics_sources: Optional[dict] = None
    caveats: list[str]


# ---------- Phase 5: affordability ----------

class AffordabilityRequest(BaseModel):
    state: str
    region_type: Literal["county", "city"]
    region_name: str
    # Slider values
    allocation_pct: float = Field(default=0.10, ge=0.0, le=1.0)
    horizon_years: int = Field(default=20, ge=1, le=50)
    # Optional overrides. If the frontend already has these from /analyze
    # it can pass them so the budget number matches the rest of the page.
    budget_dollars: Optional[float] = Field(default=None, ge=0.0)
    capacity_factor: Optional[float] = Field(default=None, gt=0.0, le=1.0)
    grid_co2_tons_per_mwh: Optional[float] = Field(default=None, ge=0.0)

    @field_validator("state")
    @classmethod
    def _state_upper(cls, v: str) -> str:
        return v.strip().upper()


class AffordabilityResponse(BaseModel):
    available: bool  # False when finance data isn't built / no budget found
    installed_mw_low: Optional[float] = None
    installed_mw_high: Optional[float] = None
    annual_gwh_low: Optional[float] = None
    annual_gwh_high: Optional[float] = None
    co2_tons_per_year_low: Optional[float] = None
    co2_tons_per_year_high: Optional[float] = None
    co2_tons_cumulative_low: Optional[float] = None
    co2_tons_cumulative_high: Optional[float] = None
    budget_dollars: Optional[float] = None
    allocation_pct: Optional[float] = None
    horizon_years: Optional[int] = None
    capacity_factor: Optional[float] = None
    grid_co2_tons_per_mwh: Optional[float] = None
    cost_per_watt_low: Optional[float] = None
    cost_per_watt_high: Optional[float] = None
    source: Optional[str] = None
    notes: list[str] = []
