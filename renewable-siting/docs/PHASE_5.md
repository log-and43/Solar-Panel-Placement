# Phase 5 — Affordability / Realism Estimate

Shifts the project's framing from *"how much renewable energy is technically
possible here"* to *"what could this community realistically afford to build
out over N years, and what would that displace in CO2."*

## What changed

| File | Change |
|------|--------|
| `backend/app/affordability.py` | NEW: budget lookup + low/high buildout & CO2 math |
| `backend/app/data_store.py` | Adds finance loaders + `finance_available()` |
| `backend/app/schemas.py` | Adds `AffordabilityRequest` / `AffordabilityResponse` |
| `backend/app/main.py` | NEW endpoints: `POST /affordability`, `GET /affordability/status` |
| `backend/scripts/sources.py` | Adds Census Government Finances source |
| `backend/scripts/build_finance.py` | NEW: builds finance Parquet files (with `--inspect` mode) |
| `backend/tests/test_phase5.py` | NEW: 10 offline tests |
| `frontend/src/lib/api.js` | Adds `getAffordability()` |
| `frontend/src/components/Affordability.jsx` | NEW: three-slider panel with range output |
| `frontend/src/App.jsx` | Places the Affordability panel below the diagnostic strip |

## The model

```
total_dollars   = budget_dollars × allocation_pct × horizon_years
capacity_high   = total_dollars / cost_per_watt_LOW      (cheap $/W → more MW)
capacity_low    = total_dollars / cost_per_watt_HIGH
annual_gwh      = MW × 8760 × capacity_factor × degradation_factor
co2_per_year    = annual_gwh × 1000 × grid_co2_tons_per_mwh
```

The **range** comes from NREL ATB's cost spread: low $0.90/W (aggressive
decline), high $1.80/W (status quo). The cheap-cost case yields the
*high* capacity estimate and vice versa.

## Setup

```bash
cd backend
source .venv/bin/activate

# Inspect the Census finance file structure first (recommended — the
# survey's schema changes year to year):
python scripts/build_finance.py --inspect

# Then build:
python scripts/build_finance.py
```

The `--inspect` step prints the raw columns so we can confirm the
capital-outlay column is mapped correctly before committing to a parse.
**This is deliberate** — the Census Government Finances format is the
least stable of all our sources, so the script is built to show its work.

If `--inspect` reveals the URL or schema has shifted, paste the output
and we update the parsing (same workflow as the eGRID percentage bug and
the Overture release version).

## Documented design choices

**Budget bucket = "capital outlay."** The broadest defensible
infrastructure-spend figure. Documented so a reviewer asking "why this
number" gets a clear answer.

**Commercial/utility scale only.** Cost figures are for commercial-scale
PV (~$0.90–1.80/W), matching the commercial-scale building and parking
polygons the app already uses. Residential rooftop (~$3/W) is excluded;
modeling it would be inconsistent with the polygon data.

**County/city budgets are population-extrapolated.** The Census state
finance survey is reliable at state level; sub-state budgets are scaled
by population share — the same approach (and same uncertainty) as Phase 2
consumption. Per-locality finance data could replace this later.

## Honesty surfaced in the UI / notes

- Budget figures below state level are population-share extrapolations.
- The model assumes the allocation is sustained for the full horizon — a
  political assumption that won't hold.
- Cumulative CO2 assumes full annual output for the whole horizon; real
  build-out is progressive, so early years displace less.
- CO2 displaced assumes the current grid mix holds. If the grid
  decarbonizes independently, each MWh of solar displaces less CO2,
  making the high-end CO2 figure optimistic.
- Panel degradation (~0.5%/yr) is applied as an average-over-horizon
  factor.
- Cost trajectories are NREL ATB projections, not guarantees.

## Why a separate endpoint (not part of /analyze)

The sliders change interactively. Re-running `/analyze` (which hits
Overture, OSM, and PVWatts) on every slider drag would be absurd. The
`/affordability` endpoint is lightweight pure arithmetic — it recomputes
in microseconds. The frontend debounces calls to it at 250ms.

## Graceful degradation

- If finance data isn't built, `/affordability` returns
  `available: false` and the panel invites the user to enter a budget
  manually.
- If a manual budget is entered, the math runs regardless of data files.
- The rest of the app is unaffected — Phase 5 degrades independently,
  same principle as every prior phase.

## Capacity factor & grid intensity

The endpoint currently uses documented defaults (capacity factor 0.18,
grid intensity 0.37 t/MWh) unless the caller overrides them. Wiring the
region-specific PVWatts capacity factor and eGRID grid intensity through
from `/analyze` is a Phase 7 polish item — the hooks (`capacity_factor`,
`grid_co2_tons_per_mwh` request fields) already exist.

## Tests

10 offline tests covering the buildout math, the low/high range invariant
(cheaper $/W → more MW), zero-allocation edge case, horizon scaling,
degradation, and the endpoint's available/unavailable behavior. Total
suite: 44 passing, 9 skipped.
