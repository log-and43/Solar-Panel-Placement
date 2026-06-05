"""
Phase 5: affordability / realism estimate.

Shifts the project's framing from "what's technically possible" to "what
could this community actually afford to build out over N years, and what
would that displace in CO2."

Inputs:
  - budget_dollars: annual capital/infrastructure budget for the region
    (from Census Annual Survey of Government Finances; user-editable)
  - allocation_pct: share of that budget directed to renewable build-out
  - horizon_years: time horizon

Outputs (as LOW–HIGH ranges, never point estimates):
  - installed capacity (MW) and the annual generation it yields (GWh/yr)
  - CO2 displaced (tons/yr and cumulative over horizon)

The range comes from cost uncertainty: NREL ATB low/mid/high $/W
trajectories for commercial/utility-scale solar. The LOW cost case
produces the HIGH capacity estimate, and vice versa.

Design choices (documented for the writeup):
  - Budget bucket: "capital outlay" (broadest defensible infra spend).
  - Project scale: commercial/utility only. This matches the commercial-
    scale building + parking polygons the app uses. Residential rooftop
    (~$3/W) is excluded; modeling it would be inconsistent with our
    polygon data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .data_store import (
    finance_available,
    finance_counties_df,
    finance_places_df,
    finance_states_df,
    states_df,
)
from .regions import RegionRecord


# ============================================================
# NREL ATB cost trajectories — commercial/utility-scale solar PV
# ============================================================
# $/W installed (overnight capital cost, CAPEX), commercial-scale PV.
# Values from NREL ATB 2024 moderate scenario, rounded. The LOW figure is
# the ATB "Advanced" trajectory (aggressive cost decline); HIGH is the
# "Conservative" trajectory (status quo). MID is "Moderate".
#
# These are intentionally embedded rather than fetched: ATB publishes a
# handful of values per year that don't change between releases, and a
# tiny constant is more robust than another fragile download.
#
# Update annually from https://atb.nrel.gov/electricity/ if desired.
ATB_COST_PER_WATT = {
    "low": 0.90,    # aggressive cost decline
    "mid": 1.30,    # moderate
    "high": 1.80,   # conservative / status quo
}

# Panel degradation: output declines ~0.5%/yr. Over a horizon, the
# *average* annual output is lower than nameplate. We apply a simple
# average-degradation factor rather than year-by-year integration.
ANNUAL_DEGRADATION = 0.005


@dataclass
class AffordabilityRange:
    # Capacity the budget could fund
    installed_mw_low: float
    installed_mw_high: float
    # Annual generation from that capacity (GWh/yr), accounting for the
    # region's capacity factor and average degradation over the horizon
    annual_gwh_low: float
    annual_gwh_high: float
    # CO2 displaced per year (tons) and cumulative over the horizon
    co2_tons_per_year_low: float
    co2_tons_per_year_high: float
    co2_tons_cumulative_low: float
    co2_tons_cumulative_high: float
    # Echo back the inputs and key assumptions for UI display
    budget_dollars: float
    allocation_pct: float
    horizon_years: int
    capacity_factor: float
    grid_co2_tons_per_mwh: float
    cost_per_watt_low: float
    cost_per_watt_high: float
    source: str
    notes: list[str]


# ============================================================
# Region budget lookup
# ============================================================

def _nan_to_none(v):
    try:
        return None if v != v else v
    except Exception:
        return v


def region_capital_budget(region: RegionRecord) -> tuple[Optional[float], list[str]]:
    """
    Return (annual_capital_outlay_dollars, notes) for the region.

    Direct lookup for states and larger counties/places; population-share
    extrapolation from state totals otherwise (same approach as Phase 2
    consumption). Returns (None, notes) if finance data isn't built.
    """
    notes: list[str] = []
    if not finance_available():
        return None, ["Government-finance data not built; affordability "
                      "estimate unavailable. Run the Phase 5 build step."]

    state_u = region.state.upper()

    if region.region_type == "county":
        df = finance_counties_df()
        hit = df[(df["state_abbr"] == state_u)
                 & (df["county_name"].str.lower() == region.name.lower())]
        if not hit.empty:
            val = _nan_to_none(hit.iloc[0]["capital_outlay_dollars"])
            if val is not None:
                return float(val), notes
    elif region.region_type == "city":
        df = finance_places_df()
        hit = df[(df["state_abbr"] == state_u)
                 & (df["place_name"].str.lower() == region.name.lower())]
        if not hit.empty:
            val = _nan_to_none(hit.iloc[0]["capital_outlay_dollars"])
            if val is not None:
                return float(val), notes

    # Fall back to population-share extrapolation from state finance totals.
    fin_states = finance_states_df()
    srow = fin_states[fin_states["state_abbr"] == state_u]
    core_states = states_df()
    pop_row = core_states[core_states["state_abbr"] == state_u]
    if srow.empty or pop_row.empty or region.population is None:
        return None, notes + [
            f"No direct or extrapolated budget data for {region.name}."
        ]

    state_capital = float(srow.iloc[0]["capital_outlay_dollars"])
    state_pop = int(pop_row.iloc[0]["population"])
    if state_pop <= 0:
        return None, notes + ["State population missing; cannot extrapolate budget."]

    share = region.population / state_pop
    extrapolated = state_capital * share
    notes.append(
        f"{region.name} capital budget is extrapolated from state totals by "
        f"population share ({region.population:,}/{state_pop:,}). Direct "
        f"Census finance data was not available for this region."
    )
    return extrapolated, notes


# ============================================================
# The buildout computation
# ============================================================

def compute_buildout(
    region: RegionRecord,
    *,
    budget_dollars: Optional[float] = None,
    allocation_pct: float = 0.10,
    horizon_years: int = 20,
    capacity_factor: Optional[float] = None,
    grid_co2_tons_per_mwh: Optional[float] = None,
) -> Optional[AffordabilityRange]:
    """
    Compute the low/high buildout + CO2 ranges for a region.

    If budget_dollars is None, looks it up from finance data. If it can't
    be found (and isn't provided), returns None — caller treats this as
    "affordability estimate unavailable for this region."

    capacity_factor and grid_co2_tons_per_mwh can be passed in by the
    pipeline (which already has them); otherwise sensible defaults apply.
    """
    notes: list[str] = []

    if budget_dollars is None:
        budget_dollars, budget_notes = region_capital_budget(region)
        notes.extend(budget_notes)
        if budget_dollars is None:
            return None

    # Defaults if the pipeline didn't supply them.
    if capacity_factor is None:
        # US average commercial PV capacity factor ~0.18. Real value should
        # come from PVWatts for the region; this is a fallback.
        capacity_factor = 0.18
        notes.append("Capacity factor defaulted to 0.18 (US average); "
                     "region-specific PVWatts value preferred.")
    if grid_co2_tons_per_mwh is None:
        # US average ~0.37 tons CO2/MWh. Real value from eGRID per state.
        grid_co2_tons_per_mwh = 0.37
        notes.append("Grid CO2 intensity defaulted to 0.37 t/MWh (US average); "
                     "region-specific eGRID value preferred.")

    total_dollars = budget_dollars * allocation_pct * horizon_years

    # LOW cost → HIGH capacity, and vice versa.
    watts_high = total_dollars / ATB_COST_PER_WATT["low"]
    watts_low = total_dollars / ATB_COST_PER_WATT["high"]
    mw_low = watts_low / 1_000_000.0
    mw_high = watts_high / 1_000_000.0

    # Annual generation: MW × 8760 h × capacity_factor = MWh/yr → GWh/yr.
    # Apply average degradation over the horizon: mean of a linear decline
    # from 1.0 to (1 - deg*horizon) is (1 - deg*horizon/2).
    deg_factor = max(0.0, 1.0 - ANNUAL_DEGRADATION * horizon_years / 2.0)

    def annual_gwh(mw: float) -> float:
        mwh = mw * 8760.0 * capacity_factor * deg_factor
        return mwh / 1000.0

    gwh_low = annual_gwh(mw_low)
    gwh_high = annual_gwh(mw_high)

    # CO2 displaced: annual generation (MWh) × grid intensity (t/MWh).
    def co2_per_year(gwh: float) -> float:
        return gwh * 1000.0 * grid_co2_tons_per_mwh

    co2_yr_low = co2_per_year(gwh_low)
    co2_yr_high = co2_per_year(gwh_high)
    # Cumulative: approximate as annual × horizon (capacity assumed built
    # progressively, but we report the steady-state annual × years as a
    # simple upper-ish bound; documented as a simplification).
    co2_cum_low = co2_yr_low * horizon_years
    co2_cum_high = co2_yr_high * horizon_years

    notes.append(
        "Cumulative CO2 assumes capacity operates at full annual output for "
        "the whole horizon; real build-out is progressive, so early years "
        "displace less. This is a simplification."
    )
    notes.append(
        "CO2 displaced assumes the current grid mix holds. If the grid "
        "decarbonizes independently, each MWh of solar displaces less CO2, "
        "making the high-end CO2 figure optimistic."
    )

    return AffordabilityRange(
        installed_mw_low=round(mw_low, 2),
        installed_mw_high=round(mw_high, 2),
        annual_gwh_low=round(gwh_low, 3),
        annual_gwh_high=round(gwh_high, 3),
        co2_tons_per_year_low=round(co2_yr_low, 0),
        co2_tons_per_year_high=round(co2_yr_high, 0),
        co2_tons_cumulative_low=round(co2_cum_low, 0),
        co2_tons_cumulative_high=round(co2_cum_high, 0),
        budget_dollars=round(budget_dollars, 0),
        allocation_pct=allocation_pct,
        horizon_years=horizon_years,
        capacity_factor=round(capacity_factor, 3),
        grid_co2_tons_per_mwh=round(grid_co2_tons_per_mwh, 4),
        cost_per_watt_low=ATB_COST_PER_WATT["low"],
        cost_per_watt_high=ATB_COST_PER_WATT["high"],
        source="Census Gov Finances (capital outlay) + NREL ATB 2024 cost range",
        notes=notes,
    )


def status() -> dict:
    """Diagnostic for /affordability/status."""
    return {
        "finance_data_built": finance_available(),
        "atb_cost_per_watt": ATB_COST_PER_WATT,
        "annual_degradation": ANNUAL_DEGRADATION,
    }
