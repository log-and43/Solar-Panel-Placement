# Renewable Siting Tool

A decision-support web app for renewable energy siting in the continental US.
Given a state + county or city, the tool estimates electricity consumption,
identifies candidate sites for solar (rooftops, parking lots) and — for
coastal regions — offshore wind, and reports the gap between current fossil
generation and what renewables could cover, along with cost, payback, CO₂,
and an affordability ("what could this community actually build?") estimate.

Every number on screen states its data source. Where a value is still a
placeholder, it is labeled as such rather than presented as authoritative.

## Status

| Phase | What it does | Real source |
|-------|--------------|-------------|
| 1 | Scaffold + frozen API contract | (hardcoded Bellingham/Whatcom) |
| 2 | Electricity consumption + generation mix | EIA SEDS + EPA eGRID + Census ACS |
| 3 | Per-polygon solar generation | NREL PVWatts v8 |
| 4 | Building + parking polygons | Overture Maps + OpenStreetMap |
| 5 | Affordability / realism estimate | Census Gov Finances + NREL ATB |
| 6 | Alternative renewable (offshore wind / geothermal) | **placeholder — not yet built** |
| 7 | Economics (cost, payback, CO₂) | NREL ATB + EIA retail rates + eGRID-derived intensity |

Phases 1-5 and 7 are live. Phase 6 (the "Alternative renewable" card) is the
only remaining placeholder and is labeled as such in the UI.

---

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Python | 3.11+ (3.13 OK) | Backend. On Python 3.13, dependency versions are pinned with `>=` for wheel availability. |
| Node.js | 18+ (20+ recommended) | Frontend (Vite). |
| Git | any | — |
| NREL API key | free | Optional but recommended. Without it, solar generation falls back to a rough approximation (and says so). Get one at https://developer.nlr.gov/signup/ |

> **Domain note:** NREL migrated `developer.nrel.gov` -> `developer.nlr.gov`
> (old domain shut down 2026-05-29). The code already points at the new host.

---

## Quick start

The app has two halves that run at the same time in two terminals: a Python
backend (port 8000) and a React frontend (port 5173). Below are full
instructions for **Linux/macOS** and **Windows** — they differ only in the
virtual-environment and environment-variable syntax.

### 1. Clone

```bash
git clone <your-repo-url> Solar-Panel-Placement
cd Solar-Panel-Placement/renewable-siting
```

### 2. Backend setup

#### Linux / macOS

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

#### Windows (PowerShell)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

> If PowerShell blocks the activate script ("running scripts is disabled"),
> run once: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, then
> re-run the activate line.

#### Windows (Command Prompt / cmd.exe)

```bat
cd backend
python -m venv .venv
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
```

You'll know the venv is active when your prompt is prefixed with `(.venv)`.

### 3. Add your NREL API key (optional but recommended)

Create a file named `.env` inside `backend/` (it's gitignored):

```
PVWATTS_API_KEY=your_key_here
```

`NREL_API_KEY` or `ROCKIES_API_KEY` are also accepted. Without a key the app
still runs — solar generation uses an approximation and the UI flags it.

### 4. Build the data files

The app needs the Census/EIA/eGRID data built into Parquet files before it
can serve real numbers. This downloads from public sources, so it needs
network access (and a few minutes). Run from `backend/` with the venv active:

```bash
python scripts/build_data.py
```

This writes `data/states.parquet`, `data/counties.parquet`, and
`data/places.parquet` (these **are** committed to the repo, so if you cloned a
repo that already has them you can skip this step).

Optional data builds:

```bash
# Government-finance budgets for the affordability panel (currently
# best-effort; the app falls back to manual budget entry if absent).
python scripts/build_finance.py --inspect   # check the source first
python scripts/build_finance.py
```

### 5. Run the backend

```bash
uvicorn app.main:app --reload
```

Leave it running. It serves on http://localhost:8000. Verify with:

```bash
curl http://localhost:8000/health
```

### 6. Frontend setup (a second terminal)

#### Linux / macOS / Windows (same commands)

```bash
cd renewable-siting/frontend
npm install
npm run dev
```

Open the URL Vite prints (default http://localhost:5173). Pick a state, then
a county or city (try **WA -> Whatcom County** or **WV -> Kanawha County** for
a high-carbon-grid contrast), and click **Run model**.

---

## Running the tests

From `backend/` with the venv active:

```bash
pytest
```

Expect roughly 57 passing, 1-9 skipped (skips are live-network tests that
only run when explicitly enabled). The tests run fully offline — external
APIs are mocked.

To run the one live PVWatts test against the real API (needs a key in `.env`):

```bash
# Linux / macOS
PVWATTS_LIVE_TEST=1 pytest tests/test_phase3.py -k live

# Windows PowerShell
$env:PVWATTS_LIVE_TEST=1; pytest tests/test_phase3.py -k live

# Windows cmd.exe
set PVWATTS_LIVE_TEST=1 && pytest tests/test_phase3.py -k live
```

---

## Optional: pre-warm the solar grid (faster demos)

By default, the first time you view a region the app calls PVWatts live (a few
seconds). You can pre-compute a coarse solar grid so every region resolves
instantly. This is purely a performance optimization — the app works without
it.

```bash
# See how big the job is (no API calls):
python scripts/warm_grid_solar.py --dry-run

# Warm at your API rate limit (1000/hr default; raise if NREL granted more):
python scripts/warm_grid_solar.py --rate 1000
```

It is resumable — re-run the same command after any interruption and it skips
what's done. It writes `data/grid_solar_cache.parquet` (gitignored). For the
fast-path to be used, `app/grid_solar.py` must be present (it reads that
cache); `app/pvwatts.py` falls back to the live path if either is missing.

---

## Repository layout

```
renewable-siting/
  backend/                 FastAPI app (Python)
    app/
      main.py              entrypoint, CORS, routing, status endpoints
      schemas.py           pydantic models — THE API CONTRACT
      regions.py           state / county / city lookup + search
      pipeline.py          orchestrator: builds the /analyze response
      consumption.py       Phase 2: real consumption from EIA/eGRID/Census
      polygons.py          Phase 4: Overture buildings + OSM parking
      pvwatts.py           Phase 3: per-polygon solar via NREL PVWatts
      grid_solar.py        grid fast-path lookup (reads the warmed cache)
      affordability.py     Phase 5: budget -> buildout + CO2 ranges
      economics.py         Phase 7: real cost / payback / CO2
      fakes.py             Phase-1 placeholders (fallbacks only now)
    scripts/
      build_data.py        downloads + builds the core Parquet data
      build_finance.py     Phase 5 government-finance data (best-effort)
      warm_grid_solar.py   pre-warms the PVWatts solar grid
      sources.py           data-source URLs + provenance notes
    tests/                 offline test suite (network mocked)
    data/                  Parquet data (committed); caches (gitignored)
    requirements.txt
    .env                   your API key (gitignored — create it yourself)

  frontend/                React + Vite + Leaflet
    src/
      App.jsx
      components/          RegionPicker, ResultMap, Diagnostic,
                           Affordability, DataQuality, ModelNotes,
                           SourceNote, Brand, LayersPanel, TargetsPanel
      lib/                 api.js (backend client), format.js
    index.html
    package.json

  docs/                    per-phase design notes (PHASE_*.md)
```

---

## Troubleshooting

**`externally-managed-environment` when running pip** — your virtual
environment isn't active (or is broken). Make sure your prompt shows
`(.venv)`. If it persists, rebuild the venv: delete the `.venv` folder and
redo step 2.

**`ModuleNotFoundError: No module named 'app'`** — you're running `uvicorn`
or `pytest` from the wrong directory. Run them from `backend/`, not from the
repo root or `frontend/`.

**Map shows blocky rectangles instead of real buildings** — the polygon
sources (Overture/OSM) returned nothing, so the app fell back to placeholders.
Check your network and the backend log; `data/polygon_cache/` caches results
per region (delete it to force a refetch).

**PVWatts / DNS errors** — confirm the host is `developer.nlr.gov` (post-2026
migration) and that your key is in `backend/.env`.

**Frontend can't reach the backend** — make sure the backend is running on
port 8000 and you started the frontend from `frontend/`.

**`npm install` errors about Node version** — upgrade to Node 18+ (20+
recommended).

---

## Notes for graders / reviewers

- Every displayed value carries a `Source:` line. Affordability and the
  economics cards also show the formula used.
- Numbers below the state level are extrapolated from state data by
  population share; this is stated in the UI caveats.
- The "Alternative renewable" card is the one remaining placeholder (Phase 6)
  and is labeled as such — it is not a real offshore-wind/geothermal estimate
  yet.
