# Renewable Siting Tool

A decision-support web app for renewable energy siting in the continental US.
Given a state + county or city, the tool estimates electricity consumption,
identifies candidate sites for solar (rooftops, parking lots) and — for
coastal regions — offshore wind, and reports the gap between current fossil
generation and what renewables could cover, along with cost, payback, and
CO₂ estimates.

**Status: Phase 1 — Walking skeleton.** The full pipeline runs end-to-end
with hardcoded data for Bellingham / Whatcom County, WA. No real data sources
are wired up yet. The frontend, backend, API contract, and map rendering
all work; subsequent phases replace each piece of fake data with a real one.

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
