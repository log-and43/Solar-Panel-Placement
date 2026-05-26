# Renewable Siting Tool

A decision-support web app for renewable energy siting in the continental US.
Given a state + county or city, the tool estimates electricity consumption,
identifies candidate sites for solar (rooftops, parking lots) and — for
coastal regions — offshore wind, and reports the gap between current fossil
generation and what renewables could cover, along with cost, payback, and
CO₂ estimates.

**Status: Phase 4 — real polygons from Overture Maps + OSM parking.**
Buildings come from Overture (Microsoft/Meta/Amazon/TomTom open mapping),
parking lots from OpenStreetMap via Overpass. Polygon shapes are filtered
to commercial-scale candidates (≥ 250 m² for rooftops, ≥ 500 m² for parking).
Per-polygon solar generation comes from NREL PVWatts when configured.
Cost estimates and recommendation logic are still placeholders — Phases
6 and 7. The API contract is unchanged.

See `docs/PHASE_4.md` for setup. See `docs/PHASE_2.md`, `docs/PHASE_3.md`,
and `docs/PHASE_*_POST_CODEX.md` for prior phases.

## Why a walking skeleton first

Every component is shippable from day one. Each subsequent phase replaces
one fake thing with one real thing without changing the API contract. If we
run out of semester, we always have a working demo of whatever phase we
finished last.

## Phase plan

| Phase | Replaces | Real source |
|-------|----------|-------------|
| 1 | (nothing — scaffold) | All hardcoded for Bellingham/Whatcom |
| 2 | Consumption numbers | eGRID + EIA SEDS + Census ACS |
| 3 | Solar generation per polygon | NREL PVWatts API |
| 4 | Polygons | Microsoft Building Footprints + OSM parking |
| 5 | Polygon refinement (optional) | SAM 2 on NAIP tiles |
| 6 | Coastal/alternative recommendation | NREL WIND Toolkit + coastline shapefile |
| 7 | Economics | NREL ATB cost data + polish |

## Repository layout

```
backend/        FastAPI app
  app/
    main.py             entrypoint, CORS, routing
    schemas.py          pydantic models (THE API CONTRACT)
    regions.py          state/county/city lookup
    pipeline.py         orchestrator: builds the /analyze response
    fakes.py            Phase-1 hardcoded data (will be replaced piece by piece)
  tests/
    test_contract.py    asserts the /analyze response shape stays stable
  requirements.txt
  README.md             backend dev instructions

frontend/       React + Vite + Leaflet
  src/
    App.jsx             top-level app
    components/
      RegionPicker.jsx  state → county/city selector
      ResultMap.jsx     Leaflet map with highlighted polygons
      Diagnostic.jsx    numbers panel
      Caveats.jsx       honest-limitations panel
    lib/
      api.js            backend client
      types.js          mirrors backend schemas
  index.html
  package.json
  README.md             frontend dev instructions

docs/
  ARCHITECTURE.md       the diagram and design rationale
  CONTRACT.md           the /analyze schema, frozen
  PHASES.md             what each phase does in detail
  CAVEATS.md            the honest-limitations list (grows over time)
```

## Running locally

Backend:
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Frontend:
```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173, pick WA → Whatcom County (or Bellingham), click Run.

## Suggested initial commits

1. `chore: scaffold backend + frontend + docs` — everything in this drop
2. `docs: phase plan and API contract` — the docs/ files specifically
3. `feat(backend): /analyze endpoint with Phase 1 fake data`
4. `feat(frontend): region picker, map, diagnostic, caveats`

Or just squash to one initial commit. Up to you.
