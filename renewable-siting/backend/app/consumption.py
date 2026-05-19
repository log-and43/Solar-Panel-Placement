"""
Phase 2: real consumption numbers.

Replaces fakes.fake_consumption(). For states, uses EIA SEDS / eGRID directly.
For counties and cities, scales the state total by population share — this
is the extrapolation approach the original project brief called for.

Phase 1 fallback: if Phase 2 data isn't built, the pipeline still calls
fakes.fake_consumption() instead of this module.
"""

from __future__ import annotations

import math

from .data_store import data_available, states_df
from .regions import RegionRecord
from .schemas import Consumption, GenerationMix


# Tag for the Consumption.source field so the frontend / caveats know
# which phase produced the numbers.
SOURCE_TAG = "EIA SEDS 2022 + EPA eGRID 2022 + Census ACS 2023"


def _normalize_mix(mix_dict: dict) -> GenerationMix:
    """
    eGRID values are non-negative percentages that should sum to ~1.0,
    but floating-point and the 'other' remainder calculation may push the
    sum slightly off. Re-normalize so the response always sums to 1.0.
    """
    total = sum(mix_dict.values())
    if total <= 0:
        # Pathological — no mix data. Return all-zero (will get caveated upstream).
        return GenerationMix()
    norm = {k: max(0.0, v) / total for k, v in mix_dict.items()}
    return GenerationMix(**norm)


def real_consumption(region: RegionRecord) -> Consumption:
    """
    Compute real consumption for a region from the loaded data.

    Behavior:
      - state row: trust EIA + eGRID directly (we don't have a "state" region
        type in the picker, but this code path is here for completeness).
      - county / city: state total × (region pop / state pop).
    """
    if not data_available():
        # Should not be hit if pipeline checked first, but be defensive.
        raise RuntimeError("Phase 2 data not built; call fakes.fake_consumption instead.")

    states = states_df()
    state_row = states[states["state_abbr"] == region.state]
    if state_row.empty:
        raise RuntimeError(
            f"No state-level data for {region.state}. This shouldn't happen "
            f"if build_data.py ran successfully — please re-run it."
        )
    s = state_row.iloc[0]

    mix = _normalize_mix({
        "coal":         float(s.get("mix_coal", 0.0) or 0.0),
        "natural_gas":  float(s.get("mix_natural_gas", 0.0) or 0.0),
        "nuclear":      float(s.get("mix_nuclear", 0.0) or 0.0),
        "hydro":        float(s.get("mix_hydro", 0.0) or 0.0),
        "wind":         float(s.get("mix_wind", 0.0) or 0.0),
        "solar":        float(s.get("mix_solar", 0.0) or 0.0),
        "other":        float(s.get("mix_other", 0.0) or 0.0),
    })

    # Region-level totals.
    # The Parquet files store the already-scaled mwh, but as a defense in
    # depth we recompute from population if the stored value is missing.
    if region.electricity_mwh_per_year is not None and not math.isnan(region.electricity_mwh_per_year):
        total = region.electricity_mwh_per_year
    elif region.population is not None and region.population > 0:
        state_pop = int(s["population"])
        state_total = float(s["electricity_mwh_per_year"])
        total = state_total * (region.population / state_pop)
    else:
        # Last-resort fallback: use state total. Will be obvious in UI.
        total = float(s["electricity_mwh_per_year"])

    fossil = total * (mix.coal + mix.natural_gas)

    return Consumption(
        total_mwh_per_year=round(total, 0),
        fossil_mwh_per_year=round(fossil, 0),
        mix=mix,
        source=SOURCE_TAG,
    )


# ============================================================
# Per-region caveats — added to the response when relevant
# ============================================================

LOW_POP_THRESHOLD = 50_000


def consumption_caveats(region: RegionRecord) -> list[str]:
    """Additional caveats specific to this region's data quality."""
    caveats: list[str] = []
    if region.population is not None and region.population < LOW_POP_THRESHOLD:
        caveats.append(
            f"{region.name} has population {region.population:,}, below "
            f"{LOW_POP_THRESHOLD:,}. Consumption estimates extrapolated from "
            "state totals are especially uncertain at this scale — a single "
            "large industrial facility can dominate actual load."
        )
    if region.region_type == "city":
        caveats.append(
            "City-level consumption is state total × population share. "
            "Real city consumption depends on industrial mix, climate, "
            "and housing stock — none of which this scaling captures."
        )
    return caveats
