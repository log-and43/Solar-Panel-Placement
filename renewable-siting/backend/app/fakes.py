"""
Phase 1 fake data, segregated by future-phase owner.

Every function in this module corresponds to one thing a later phase will
replace with a real data source. The function signatures are stable; the
bodies are not.

When you replace a fake, delete the body and import the real implementation.
Do NOT delete the function — keep the seam.
"""

from __future__ import annotations

from .regions import RegionRecord
from .schemas import (
    Alternative,
    Consumption,
    Economics,
    GenerationMix,
    PolygonCollection,
    PolygonFeature,
    PolygonProperties,
    Recommendation,
)


# ============================================================
# Replaced in Phase 2 (eGRID + EIA SEDS + Census ACS)
# ============================================================
def fake_consumption(region: RegionRecord) -> Consumption:
    # Rough plausible numbers for Whatcom County circa 2022.
    # Source for the SHAPE of these numbers, not the values:
    #   EIA Washington state electricity profile + eGRID NWPP region mix.
    # Values are intentionally rounded; do not cite.
    if region.region_type == "county":
        total = 2_100_000.0
    else:  # city
        total = 950_000.0

    mix = GenerationMix(
        coal=0.04,
        natural_gas=0.07,
        nuclear=0.08,
        hydro=0.65,
        wind=0.08,
        solar=0.02,
        other=0.06,
    )
    fossil = total * (mix.coal + mix.natural_gas)

    return Consumption(
        total_mwh_per_year=total,
        fossil_mwh_per_year=fossil,
        mix=mix,
        source="PHASE_1_HARDCODED",
    )


# ============================================================
# Replaced in Phase 4 (Microsoft Building Footprints + OSM parking).
# Phase 5 may augment with CV-detected polygons.
# ============================================================
def fake_polygons(region: RegionRecord) -> PolygonCollection:
    """
    Place demo polygons inside the region bbox so the map has something to
    render. Coordinates are illustrative; these are not real rooftops or
    parking lots.

    Phase-1 design choice: counts and sizes are tuned so the diagnostic
    panel produces plausible-looking gap/coverage numbers for a county-scale
    demo. Real Phase-4 polygons will be far more numerous (thousands) and
    will come from Microsoft Building Footprints + OSM.
    """
    import math
    lat, lon = region.centroid

    def rect(cx_lon: float, cy_lat: float, dlon: float, dlat: float) -> list[list[list[float]]]:
        return [[
            [cx_lon - dlon, cy_lat - dlat],
            [cx_lon + dlon, cy_lat - dlat],
            [cx_lon + dlon, cy_lat + dlat],
            [cx_lon - dlon, cy_lat + dlat],
            [cx_lon - dlon, cy_lat - dlat],
        ]]

    features: list[PolygonFeature] = []

    # Scale density by region: a county needs many more polygons than a city
    # for the diagnostic panel to read as a believable demo.
    if region.region_type == "county":
        rooftop_count = 60
        parking_count = 15
        spread = 0.06   # degrees, roughly half-bbox
    else:  # city
        rooftop_count = 24
        parking_count = 6
        spread = 0.015

    # Pseudo-random but deterministic placement using a small LCG so the demo
    # is reproducible without pulling in numpy.
    seed = abs(hash((region.state, region.region_type, region.name))) % (2**31)
    def next_uniform() -> float:
        nonlocal seed
        seed = (seed * 1103515245 + 12345) & 0x7fffffff
        return seed / 0x7fffffff

    for i in range(rooftop_count):
        dlon_off = (next_uniform() - 0.5) * 2 * spread
        dlat_off = (next_uniform() - 0.5) * 2 * spread
        # Building sizes from ~800 m² (small commercial) to ~3500 m² (big box).
        area = 800.0 + next_uniform() * 2700.0
        # Make footprint roughly square at this latitude.
        side_deg = math.sqrt(area) / 111_000.0  # meters→deg lat
        features.append(PolygonFeature(
            geometry={
                "type": "Polygon",
                "coordinates": rect(lon + dlon_off, lat + dlat_off, side_deg / 2, side_deg / 2),
            },
            properties=PolygonProperties(
                category="rooftop",
                area_m2=round(area, 0),
                est_annual_mwh=area * 0.15,  # placeholder; Phase 3 replaces with PVWatts (~150 kWh/m²/yr)
                suitability_score=0.80,
            ),
        ))

    for i in range(parking_count):
        dlon_off = (next_uniform() - 0.5) * 2 * spread
        dlat_off = (next_uniform() - 0.5) * 2 * spread
        # Parking lots ~3000–15000 m².
        area = 3000.0 + next_uniform() * 12000.0
        side_deg = math.sqrt(area) / 111_000.0
        # Parking lots tend to be wider than tall.
        features.append(PolygonFeature(
            geometry={
                "type": "Polygon",
                "coordinates": rect(lon + dlon_off, lat + dlat_off, side_deg * 0.9, side_deg * 0.5),
            },
            properties=PolygonProperties(
                category="parking",
                area_m2=round(area, 0),
                est_annual_mwh=area * 0.12,  # canopy solar a bit less efficient
                suitability_score=0.70,
            ),
        ))

    # If coastal, throw in a single offshore wind zone polygon offshore.
    if region.is_coastal:
        # Push west of the centroid by ~0.1 deg lon (~7 km at this latitude).
        features.append(PolygonFeature(
            geometry={
                "type": "Polygon",
                "coordinates": rect(lon - 0.10, lat, 0.02, 0.015),
            },
            properties=PolygonProperties(
                category="offshore_wind_zone",
                area_m2=4_000_000.0,  # ~4 km² zone
                est_annual_mwh=180_000.0,
                suitability_score=0.65,
            ),
        ))

    return PolygonCollection(features=features)


# ============================================================
# Replaced in Phase 6 (NSRDB + WIND Toolkit + coastline distance)
# ============================================================
def fake_recommendation(
    region: RegionRecord,
    consumption: Consumption,
    polygons: PolygonCollection,
) -> Recommendation:
    rooftop_parking_mwh = sum(
        f.properties.est_annual_mwh
        for f in polygons.features
        if f.properties.category in ("rooftop", "parking")
    )
    offshore_mwh = sum(
        f.properties.est_annual_mwh
        for f in polygons.features
        if f.properties.category == "offshore_wind_zone"
    )

    fossil_gap = consumption.fossil_mwh_per_year - rooftop_parking_mwh

    alternatives: list[Alternative] = []
    if region.is_coastal and offshore_mwh > 0:
        alternatives.append(Alternative(
            tech="offshore_wind",
            rationale=(
                "Coastal region. Even with rooftop and parking solar, large "
                "load centers will likely not be covered by solar alone in "
                "the Pacific Northwest's solar resource."
            ),
            potential_mwh=offshore_mwh,
        ))

    if fossil_gap <= 0:
        primary: str = "solar"
        notes = (
            "Rooftop and parking solar potential (placeholder values) "
            "exceeds the fossil-generation share. Real numbers will "
            "shift this in Phase 2/3."
        )
        covered = consumption.fossil_mwh_per_year
        gap = 0.0
    elif offshore_mwh >= fossil_gap:
        primary = "mixed"
        notes = (
            "Rooftop and parking solar alone do not close the fossil gap. "
            "Offshore wind potential exists nearby and is sufficient on "
            "paper to close it. Real-world deployment requires multi-year "
            "federal review (see caveats)."
        )
        covered = consumption.fossil_mwh_per_year
        gap = 0.0
    else:
        primary = "insufficient"
        notes = (
            "Identified renewable potential does not close the fossil gap. "
            "This may indicate sparse polygon data (Phase 1 is hand-placed) "
            "or genuinely limited siting options."
        )
        covered = rooftop_parking_mwh + offshore_mwh
        gap = consumption.fossil_mwh_per_year - covered

    return Recommendation(
        primary=primary,  # type: ignore[arg-type]
        covered_mwh_per_year=covered,
        gap_mwh_per_year=max(0.0, gap),
        alternatives=alternatives,
        notes=notes,
    )


# ============================================================
# Replaced in Phase 7 (NREL ATB + state retail rates + eGRID CO2 intensity)
# ============================================================
def fake_economics(
    consumption: Consumption,
    polygons: PolygonCollection,
    recommendation: Recommendation,
) -> Economics:
    # Pretend commercial rooftop solar at ~$1.50/W installed, ~200 W/m² panels.
    rooftop_parking_m2 = sum(
        f.properties.area_m2
        for f in polygons.features
        if f.properties.category in ("rooftop", "parking")
    )
    installed_watts = rooftop_parking_m2 * 200.0
    install_cost = installed_watts * 1.50

    # Pretend retail rate of $0.11/kWh average for WA.
    annual_kwh = sum(
        f.properties.est_annual_mwh * 1000.0
        for f in polygons.features
        if f.properties.category in ("rooftop", "parking")
    )
    annual_savings = annual_kwh * 0.11

    payback = (install_cost / annual_savings) if annual_savings > 0 else None

    # WA grid is mostly hydro, so CO2 intensity is low. Use ~100 kg/MWh placeholder.
    co2_avoided = recommendation.covered_mwh_per_year * 0.10  # tons (kg/1000)

    return Economics(
        install_cost_usd=round(install_cost, 0),
        annual_savings_usd=round(annual_savings, 0),
        payback_years=round(payback, 1) if payback is not None else None,
        co2_avoided_tons_per_year=round(co2_avoided, 0),
    )


# ============================================================
# Caveats: list grows as we learn. Static for Phase 1.
# ============================================================
PHASE_1_CAVEATS: list[str] = [
    "PHASE 1 (current): all numbers in this response are placeholders. "
    "Do not interpret as real estimates.",
    "Consumption below state level will be extrapolated by population share "
    "(Phase 2). Significant uncertainty for low-population regions.",
    "Generation potential is technical, not permitted or economically optimal. "
    "Real rooftops lose 30–60% of theoretical area to shading, equipment, "
    "and setbacks.",
    "Cost and payback figures use national averages and are not site-specific.",
    "Offshore wind potential, when shown, is technical only. Real development "
    "requires multi-year federal lease and environmental review.",
]
