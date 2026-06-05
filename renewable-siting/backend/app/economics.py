"""
Phase 7: real, sourced economics.

Replaces fakes.fake_economics. Computes installation cost, annual bill
savings, simple payback, and CO2 avoided from real inputs:

  - Installed capacity / generation: from the polygons' PVWatts results
    (Phase 3/4), already in the response.
  - Install cost: NREL ATB 2024 commercial-PV capital cost ($/W). Same
    constant the affordability model uses, so the two agree.
  - Grid CO2 intensity: DERIVED from the region's EPA eGRID generation mix
    using standard per-fuel output emission factors. This is a derivation,
    not a direct eGRID emission rate — labeled as such.
  - Retail electricity rate: EIA state-average commercial rate (¢/kWh),
    embedded as a small stable table (EIA publishes these annually; they
    move slowly). Used for the bill-savings / payback figure.

Every number carries a source string so the UI can show provenance.
"""

from __future__ import annotations

from .schemas import Consumption, Economics, GenerationMix, PolygonCollection


# ============================================================
# NREL ATB 2024 commercial PV capital cost ($/W installed).
# Mid scenario — matches affordability.py's ATB_COST_PER_WATT["mid"].
# ============================================================
ATB_COST_PER_WATT_MID = 1.30

# Panel power density used to convert polygon panel-area → installed watts.
# Matches pvwatts.CATEGORY_DEFAULTS watts_per_m2.
WATTS_PER_M2 = 200.0
# Packing factors (fraction of footprint that becomes panel). Match
# pvwatts.CATEGORY_DEFAULTS so cost and generation use the same geometry.
PACKING = {"rooftop": 0.55, "parking": 0.65, "cv_detected_parking": 0.65}


# ============================================================
# Per-fuel CO2 output emission factors (metric tons CO2 per MWh).
# Standard lifecycle/combustion figures for grid-displacement estimates:
#   coal ~1.02, natural gas ~0.43, oil-ish "other" partial. Non-emitting
#   sources (nuclear, hydro, wind, solar) ~0 at the point of generation.
# These let us derive a blended grid intensity from the eGRID mix.
# ============================================================
FUEL_CO2_TONS_PER_MWH = {
    "coal": 1.02,
    "natural_gas": 0.43,
    "nuclear": 0.0,
    "hydro": 0.0,
    "wind": 0.0,
    "solar": 0.0,
    # "other" is a grab-bag (biomass, oil, petroleum coke, misc). Use a
    # conservative partial factor rather than 0 so we don't understate.
    "other": 0.30,
}


# ============================================================
# EIA state-average COMMERCIAL retail electricity rate ($/kWh).
# Source: EIA Electric Power Monthly, state commercial sector averages
# (2023-2024 vintage, rounded). Stable year to year. Commercial rate is
# the right one because our polygons are commercial-scale roofs & lots.
# ============================================================
EIA_COMMERCIAL_RATE_USD_PER_KWH = {
    "AL": 0.125, "AZ": 0.107, "AR": 0.099, "CA": 0.236, "CO": 0.111,
    "CT": 0.197, "DE": 0.110, "FL": 0.105, "GA": 0.110, "ID": 0.085,
    "IL": 0.097, "IN": 0.114, "IA": 0.099, "KS": 0.108, "KY": 0.110,
    "LA": 0.099, "ME": 0.146, "MD": 0.119, "MA": 0.205, "MI": 0.122,
    "MN": 0.110, "MS": 0.114, "MO": 0.092, "MT": 0.107, "NE": 0.092,
    "NV": 0.094, "NH": 0.176, "NJ": 0.135, "NM": 0.105, "NY": 0.171,
    "NC": 0.094, "ND": 0.098, "OH": 0.107, "OK": 0.090, "OR": 0.097,
    "PA": 0.110, "RI": 0.184, "SC": 0.111, "SD": 0.103, "TN": 0.116,
    "TX": 0.084, "UT": 0.090, "VA": 0.092, "VT": 0.165, "WA": 0.094,
    "WV": 0.111, "WI": 0.116, "WY": 0.106,
}
NATIONAL_AVG_COMMERCIAL_RATE = 0.128  # EIA US commercial avg, fallback


# ============================================================
# Source strings (shown in UI provenance blurbs)
# ============================================================
SOURCE_COST = "NREL ATB 2024 commercial-PV capital cost ($1.30/W)"
SOURCE_RATE = "EIA state-average commercial electricity rate"
SOURCE_CO2 = "Derived from EPA eGRID generation mix (per-fuel emission factors)"


def grid_intensity_tons_per_mwh(mix: GenerationMix) -> float:
    """Blend per-fuel CO2 factors by the region's generation mix shares."""
    return (
        mix.coal * FUEL_CO2_TONS_PER_MWH["coal"]
        + mix.natural_gas * FUEL_CO2_TONS_PER_MWH["natural_gas"]
        + mix.nuclear * FUEL_CO2_TONS_PER_MWH["nuclear"]
        + mix.hydro * FUEL_CO2_TONS_PER_MWH["hydro"]
        + mix.wind * FUEL_CO2_TONS_PER_MWH["wind"]
        + mix.solar * FUEL_CO2_TONS_PER_MWH["solar"]
        + mix.other * FUEL_CO2_TONS_PER_MWH["other"]
    )


def _installed_watts(polygons: PolygonCollection) -> float:
    """Installed watts from polygon footprints, matching PVWatts geometry."""
    watts = 0.0
    for f in polygons.features:
        cat = f.properties.category
        pack = PACKING.get(cat)
        if pack is None:
            continue  # not a solar polygon
        watts += f.properties.area_m2 * pack * WATTS_PER_M2
    return watts


def real_economics(
    consumption: Consumption,
    polygons: PolygonCollection,
    state_abbr: str,
) -> tuple[Economics, dict]:
    """
    Compute real economics. Returns (Economics, sources_dict) where
    sources_dict maps each field to its source string for the UI.
    """
    # Installed capacity & generation from the polygons (real PVWatts).
    installed_watts = _installed_watts(polygons)
    annual_kwh = sum(
        f.properties.est_annual_mwh * 1000.0
        for f in polygons.features
        if f.properties.category in PACKING
    )

    # Cost: ATB $/W.
    install_cost = installed_watts * ATB_COST_PER_WATT_MID

    # Savings: real state commercial retail rate.
    rate = EIA_COMMERCIAL_RATE_USD_PER_KWH.get(state_abbr, NATIONAL_AVG_COMMERCIAL_RATE)
    rate_is_fallback = state_abbr not in EIA_COMMERCIAL_RATE_USD_PER_KWH
    annual_savings = annual_kwh * rate

    payback = (install_cost / annual_savings) if annual_savings > 0 else None

    # CO2 avoided: generation × derived grid intensity.
    intensity = grid_intensity_tons_per_mwh(consumption.mix)
    annual_mwh = annual_kwh / 1000.0
    co2_avoided = annual_mwh * intensity

    econ = Economics(
        install_cost_usd=round(install_cost, 0),
        annual_savings_usd=round(annual_savings, 0),
        payback_years=round(payback, 1) if payback is not None else None,
        co2_avoided_tons_per_year=round(co2_avoided, 0),
    )

    rate_src = SOURCE_RATE + (
        " (US national average — no state value on file)" if rate_is_fallback else
        f" ({state_abbr}: ${rate:.3f}/kWh)"
    )
    sources = {
        "install_cost": SOURCE_COST,
        "annual_savings": rate_src,
        "payback": f"install cost ÷ annual savings; {rate_src}",
        "co2_avoided": f"{SOURCE_CO2} — {state_abbr} grid ≈ {intensity:.3f} t/MWh",
        "grid_intensity_tons_per_mwh": round(intensity, 4),
        "retail_rate_usd_per_kwh": round(rate, 4),
        "cost_per_watt": ATB_COST_PER_WATT_MID,
    }
    return econ, sources
