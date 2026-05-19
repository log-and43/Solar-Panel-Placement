"""
Pipeline orchestrator.

This is the function each phase modifies in tiny, localized ways:
when Phase 2 lands, the only line that changes is the call to fake_consumption.
The rest stays put.
"""

from __future__ import annotations

from .consumption import consumption_caveats, real_consumption
from .data_store import data_available
from .fakes import (
    PHASE_1_CAVEATS,
    fake_consumption,
    fake_economics,
    fake_polygons,
    fake_recommendation,
)
from .regions import RegionNotFound, lookup
from .schemas import AnalyzeRequest, AnalyzeResponse, Region


# Caveats common to Phase 2+ (when real consumption data IS available).
# These augment Phase 1 caveats; later phases (3, 4, ...) will replace more
# of these as fake bits become real.
PHASE_2_CAVEATS: list[str] = [
    "Consumption: state totals from EIA SEDS (2022), generation mix from "
    "EPA eGRID (2022), populations from Census ACS (2023). Sub-state "
    "values are extrapolated by population share.",
    "Polygon placement and per-polygon generation are still placeholders "
    "(Phase 4/3 will replace).",
    "Cost, payback, and CO₂ figures still use national averages and are "
    "not site-specific (Phase 7 will refine).",
    "Offshore wind potential, when shown, is technical only. Real "
    "development requires multi-year federal lease and environmental review.",
]


def analyze(req: AnalyzeRequest) -> AnalyzeResponse:
    record = lookup(req.state, req.region_type, req.region_name)

    region = Region(
        name=record.name,
        type=record.region_type,
        state=record.state,
        bbox=record.bbox,
        centroid=record.centroid,
        is_coastal=record.is_coastal,
    )

    # Phase 2: real consumption when data is built; fake otherwise.
    if data_available():
        consumption = real_consumption(record)
        caveats = list(PHASE_2_CAVEATS) + consumption_caveats(record)
    else:
        consumption = fake_consumption(record)
        caveats = list(PHASE_1_CAVEATS)

    polygons = fake_polygons(record)               # → Phases 4, 5
    recommendation = fake_recommendation(          # → Phase 6
        record, consumption, polygons,
    )
    economics = fake_economics(                    # → Phase 7
        consumption, polygons, recommendation,
    )

    return AnalyzeResponse(
        region=region,
        consumption=consumption,
        polygons=polygons,
        recommendation=recommendation,
        economics=economics,
        caveats=caveats,
    )


__all__ = ["analyze", "RegionNotFound"]
