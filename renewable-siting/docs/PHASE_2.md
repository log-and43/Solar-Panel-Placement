# Phase 2 — Real Consumption Data

This phase replaces `fake_consumption()` with real numbers from three
authoritative public sources, and replaces the dropdown picker with a
search-as-you-type picker that scales to thousands of regions.

## What changed

| File | Change |
|------|--------|
| `backend/scripts/sources.py` | URLs for EIA SEDS, EPA eGRID, Census ACS, Census TIGER gazetteers |
| `backend/scripts/build_data.py` | Downloads + cleans + writes 3 Parquet files |
| `backend/data/` | Output directory (Parquet files committed to repo) |
| `backend/app/data_store.py` | Loads Parquet files at import time |
| `backend/app/regions.py` | Reads from Parquet; Phase-1 fallback if files absent |
| `backend/app/consumption.py` | NEW: real consumption from EIA + eGRID + population scaling |
| `backend/app/pipeline.py` | Swaps `fake_consumption` for `real_consumption` when data is built |
| `backend/app/main.py` | NEW endpoints: `/states`, `/search` |
| `backend/app/fakes.py` | `fake_consumption` retained for Phase-1 fallback |
| `backend/tests/test_phase2.py` | NEW test file; tests that need data are auto-skipped if it's missing |
| `frontend/src/components/RegionPicker.jsx` | Dropdowns → typeahead search |
| `frontend/src/lib/api.js` | Adds `searchRegions`, `listStates`, `getHealth` |

## How to bring Phase 2 online

```bash
cd backend
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scripts/build_data.py --check       # test URL reachability
python scripts/build_data.py               # do the full build (~50 MB download, ~2 min)
pytest                                     # all tests now run (no skips)
uvicorn app.main:app --reload
```

After this, the frontend picker shows all US states with a typeahead box.

## Data sources

| Source | What we use | URL stability |
|--------|-------------|---------------|
| EIA SEDS | State electricity consumption (`ESTCB` MSN) | Stable URL pattern; new file each year |
| EPA eGRID | State generation mix (`ST22` sheet) | URL changes per release year; check `epa.gov/egrid/download-data` |
| Census ACS | State + county + place population | Stable bulk-download URL |
| Census TIGER | Centroids for counties and places | Stable bulk-download URL |

If a URL breaks, edit `backend/scripts/sources.py`. Each Source dataclass
has a `where_to_find_if_broken` field pointing to the upstream catalog
page.

## The extrapolation math (and its limits)

For counties and cities, we have no direct consumption data. We scale:

```
region_consumption ≈ state_consumption × (region_pop / state_pop)
```

This is uniform per-capita scaling. It implicitly assumes:

- Every person in the state consumes the same amount of electricity (false; it varies by climate and housing stock)
- Industrial load is distributed proportional to population (false; one factory in a small county can dominate)
- The state's generation mix is the mix the region "consumes" (false; electricity flows across regions on the grid, but it's the best public proxy)

The frontend surfaces a per-region caveat when the population is below
50,000, where these assumptions are especially fragile.

## Why Parquet, and why commit the data files

- Parquet is ~5–10× smaller than the source CSVs/Excel files
- Loading a Parquet file is faster than parsing CSV at every backend start
- Committed data means the repo is self-contained: anyone can clone and run
  without internet access
- Re-running the build script is straightforward when newer data is released

The committed Parquet files are under 5 MB total. Raw downloads live in
`backend/data/raw/` and are NOT committed (gitignored).

## Phase 2 still does NOT do

- Real polygons (still Phase 1 placeholders → Phase 4)
- Real per-polygon generation (still `area × 0.15` → Phase 3)
- Renewable mix recommendation (still hardcoded → Phase 6)
- Cost / payback / CO₂ from real sources (still national averages → Phase 7)

The API contract is unchanged; the frontend renders the same response
shape whether the consumption numbers came from EIA or from
`fake_consumption()`.
