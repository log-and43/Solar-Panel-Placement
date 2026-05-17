"""
Pipeline orchestrator.

This is the function each phase modifies in tiny, localized ways:
when Phase 2 lands, the only line that changes is the call to fake_consumption.
The rest stays put.
"""

from __future__ import annotations

from .fakes import (
    PHASE_1_CAVEATS,
    fake_consumption,
    fake_economics,
    fake_polygons,
    fake_recommendation,
)
from .regions import RegionNotFound, lookup
from .schemas import AnalyzeRequest, AnalyzeResponse, Region


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

    consumption = fake_consumption(record)         # → Phase 2
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
        caveats=PHASE_1_CAVEATS,
    )


__all__ = ["analyze", "RegionNotFound"]
