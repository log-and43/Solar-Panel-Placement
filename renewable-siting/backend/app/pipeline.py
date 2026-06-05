"""
Pipeline orchestrator.

Each phase modifies one step in this orchestrator. The contract on the
output (AnalyzeResponse) is unchanged across phases by design.
"""

from __future__ import annotations

import logging

from shapely.geometry import shape

from .consumption import consumption_caveats, real_consumption
from .data_store import data_available
from .economics import real_economics
from .fakes import (
    PHASE_1_CAVEATS,
    fake_consumption,
    fake_economics,
    fake_polygons,
    fake_recommendation,
)
from .polygons import (
    FetchResult,
    SOURCE_OSM,
    SOURCE_OVERTURE,
    SOURCE_PHASE1,
    real_polygons,
)
from .pvwatts import (
    SOURCE_FALLBACK as PV_SOURCE_FALLBACK,
    SOURCE_REAL as PV_SOURCE_REAL,
    has_api_key,
    pv_annual_mwh,
)
from .regions import RegionNotFound, lookup
from .schemas import AnalyzeRequest, AnalyzeResponse, PolygonCollection, Region

logger = logging.getLogger(__name__)


PHASE_2_CAVEATS: list[str] = [
    "Consumption: state totals from EIA SEDS (2022), generation mix from "
    "EPA eGRID (2022), populations from Census ACS (2023). Sub-state "
    "values are extrapolated by population share.",
    "Cost, payback, and CO₂ figures still use national averages and are "
    "not site-specific (Phase 7 will refine).",
    "Offshore wind potential, when shown, is technical only. Real "
    "development requires multi-year federal lease and environmental review.",
]

PVWATTS_REAL_CAVEAT = (
    "Solar generation per polygon: NREL PVWatts v8 (NSRDB resource), with "
    "rooftop and parking defaults for tilt, azimuth, packing factor, and "
    "system losses."
)
PVWATTS_FALLBACK_CAVEAT = (
    "Solar generation per polygon: approximation (area × 0.15 MWh/m²). "
    "To use real NREL PVWatts data, add PVWATTS_API_KEY to backend/.env "
    "(free key at https://developer.nlr.gov/signup/)."
)


def _polygon_centroid(geometry: dict) -> tuple[float, float]:
    """Return (lat, lon) for a GeoJSON polygon."""
    geom = shape(geometry)
    c = geom.centroid
    return c.y, c.x


def _enrich_polygons_with_pvwatts(polygons: PolygonCollection) -> PolygonCollection:
    """
    Replace placeholder est_annual_mwh on rooftop/parking polygons with
    real PVWatts numbers (when an API key is configured). Offshore wind
    zones are left alone — they're not solar.
    """
    solar_categories = {"rooftop", "parking", "cv_detected_parking"}
    for feature in polygons.features:
        cat = feature.properties.category
        if cat not in solar_categories:
            continue
        lat, lon = _polygon_centroid(feature.geometry)
        mwh, source = pv_annual_mwh(
            lat=lat, lon=lon,
            area_m2=feature.properties.area_m2,
            category=cat,
        )
        feature.properties.est_annual_mwh = round(mwh, 3)
        feature.properties.generation_source = source
    return polygons


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

    # Phase 4: real polygons (with soft fallback to Phase 1 fakes).
    fetched = real_polygons(record)
    has_solar_polys = any(
        f.properties.category in ("rooftop", "parking", "cv_detected_parking")
        for f in fetched.polygons.features
    )
    if not has_solar_polys:
        # Buildings + parking both empty. Don't ship a map with only an
        # offshore wind zone; fall back to Phase 1 placeholders so the
        # demo still has something visually meaningful.
        logger.warning("Phase 4 sources returned no solar polygons for %s/%s/%s; "
                       "falling back to Phase 1 placeholders.",
                       record.state, record.region_type, record.name)
        polygons = fake_polygons(record)
        caveats.append(
            "Phase 4 polygon sources (Overture buildings, OSM parking) "
            "returned no usable shapes for this region. Showing Phase 1 "
            "placeholder polygons instead."
        )
    else:
        polygons = fetched.polygons
        # Phase-4-specific caveats based on what actually came back
        if fetched.buildings_source == SOURCE_OVERTURE:
            caveats.append(
                f"Rooftops: {fetched.buildings_found} from Overture Maps "
                f"(filtered to buildings ≥ 250 m², top by area)."
            )
        else:
            caveats.append(
                "Rooftops: Overture buildings unavailable; showing Phase 1 "
                "placeholders only."
            )
        if fetched.parking_source == SOURCE_OSM:
            if fetched.parking_found > 0:
                caveats.append(
                    f"Parking: {fetched.parking_found} polygons from OSM "
                    f"(filtered to ≥ 500 m²). OSM coverage varies widely; "
                    f"this region may have undermapped parking."
                )
            else:
                caveats.append(
                    "Parking: OSM returned no parking-lot polygons for this "
                    "bbox. Rural and small-town regions are often unmapped."
                )
        else:
            caveats.append(
                "Parking: OpenStreetMap / Overpass was unreachable. "
                "No parking-lot candidates appear on the map."
            )
        for note in fetched.notes:
            caveats.append(note)

    polygons = _enrich_polygons_with_pvwatts(polygons)

    if has_api_key():
        caveats.append(PVWATTS_REAL_CAVEAT)
    else:
        caveats.append(PVWATTS_FALLBACK_CAVEAT)

    recommendation = fake_recommendation(          # → Phase 6
        record, consumption, polygons,
    )

    # Phase 7: real economics (cost from NREL ATB, savings from EIA state
    # retail rate, CO2 from eGRID-derived grid intensity). Needs the real
    # generation mix, so it requires Phase 2 data; otherwise fall back.
    if data_available():
        economics, econ_sources = real_economics(consumption, polygons, record.state)
        caveats.append(
            "Economics: install cost from NREL ATB 2024 ($1.30/W commercial PV); "
            "bill savings from EIA state commercial retail rate; CO₂ avoided from "
            "grid intensity derived from the EPA eGRID generation mix. Simple "
            "payback ignores financing, incentives, degradation, and rate inflation."
        )
    else:
        economics = fake_economics(consumption, polygons, recommendation)
        econ_sources = None

    return AnalyzeResponse(
        region=region,
        consumption=consumption,
        polygons=polygons,
        recommendation=recommendation,
        economics=economics,
        economics_sources=econ_sources,
        caveats=caveats,
    )


__all__ = ["analyze", "RegionNotFound"]
