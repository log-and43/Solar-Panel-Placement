# Phase 3 — Real Solar Generation (NREL PVWatts)

This phase replaces the Phase 1 placeholder formula
(`est_annual_mwh = area_m2 × 0.15 / 1000`) with real per-polygon solar
estimates from NREL's PVWatts v8 API.

## What changed

| File | Change |
|------|--------|
| `backend/app/pvwatts.py` | NEW: PVWatts client, disk-based cache, env-key loading, per-category defaults |
| `backend/app/pipeline.py` | Adds `_enrich_polygons_with_pvwatts()`, called after polygons are placed |
| `backend/app/main.py` | NEW endpoint: `/pvwatts/status` (cache stats, key configured?) |
| `backend/.env.example` | NEW: template for the local `.env` |
| `backend/requirements.txt` | Adds `shapely>=2.0.0` for polygon centroid math |
| `backend/tests/test_phase3.py` | NEW: 10 tests, all run without network |
| `frontend/src/lib/api.js` | Adds `getPvwattsStatus()` |
| `frontend/src/components/ModelNotes.jsx` | Shows PVWatts status and cache size |
| `.gitignore` | Adds `backend/data/pvwatts_cache.json` |

## Setup

1. **Get a key.** https://developer.nrel.gov/signup/ — instant, free, 90 seconds.
   Arrives by email as a 40-character string.

2. **Configure it.**
   ```bash
   cp backend/.env.example backend/.env
   # edit backend/.env and paste your key:
   PVWATTS_API_KEY=your_key_here
   ```

3. **Install the new dep.**
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

4. **Restart the backend.** uvicorn does NOT live-reload `.env` changes
   on its own; restart it after editing.

5. **Verify.** Hit http://localhost:8000/pvwatts/status — should return
   `{"api_key_configured": true, "cache": {"entries": 0, ...}}`. Run an
   analysis, then refetch — `entries` should jump to ~70 (one per polygon).

## How it works

- **`load_api_key()`** checks `PVWATTS_API_KEY` env var first, then
  `backend/.env`. Returns `None` if neither has it.
- **`pv_annual_mwh(lat, lon, area_m2, category)`** is the single public
  function. It:
  - Picks per-category defaults (rooftop = tilt≈latitude, fixed roof,
    14% losses; parking = flatter tilt, fixed open rack, 16% losses).
  - Computes system size from `area × packing_factor × W/m²`.
  - Builds a cache key from rounded lat/lon, system size, and array params.
  - Returns cached value if present.
  - Otherwise calls PVWatts, caches the result, returns it.
- **Failure modes:**
  - No API key → returns Phase-1 fallback formula, tagged
    `SOURCE_FALLBACK`.
  - PVWatts API error → logs warning, returns fallback. A mid-run
    network blip cannot 500 `/analyze`.
- **Cache** is a JSON file at `backend/data/pvwatts_cache.json`,
  gitignored. Grows monotonically. ~1 KB per polygon.

## Per-category solar defaults

| Category | Tilt | Array type | Losses | Packing | W/m² |
|----------|------|------------|--------|---------|------|
| rooftop  | ≈ latitude (cap 60°) | Fixed roof mount | 14% | 55% | 200 |
| parking  | min(latitude, 10°) | Fixed open rack | 16% | 65% | 200 |
| cv_detected_parking | same as parking | | | | |

Rationale notes:
- **Packing factor**: rooftops lose area to HVAC, walkways, setbacks,
  shade. 55% is a defensible commercial default. Parking canopies pack
  more densely because they're built specifically for panels — 65%.
- **Tilt**: rule of thumb is `tilt = latitude` for fixed-tilt year-round
  optimum. Parking canopies are flatter for structural and snow-load
  reasons; we cap at 10°.
- **Losses**: PVWatts default is 14% (soiling, wiring, inverter, etc.).
  Parking canopies see ~2% more from weather exposure and bird soiling.

These are not best-fit values for any specific site. They are reasonable
defaults that make our numbers comparable to industry rules-of-thumb.

## Cache invariants

The cache key is:
```
"{lat_to_2dp},{lon_to_2dp},{kw_rounded_to_half},{array_type},{tilt_int},{azimuth_to_5},{losses_int}"
```

Two polygons hash to the same cache key when they are:
- Within ~1.1 km of each other (lat/lon rounded to 2dp)
- Similar in system size (rounded to 0.5 kW)
- Same array type, tilt (1°), azimuth (5°), and losses (1%)

This is intentionally permissive — NSRDB resource data is at ~4 km
resolution, so two polygons in the same 1 km grid cell genuinely get
identical PVWatts output. Free deduplication.

## API rate limits

NREL's default rate limit is **1,000 requests/hour per key**. A typical
`/analyze` run is ~70 polygons. So you can do ~14 cold analyses per hour,
or hundreds per hour once the cache warms up. The status endpoint shows
the cache size so you can see this in action.

If you hit the limit, NREL returns 429. We log and fall back per-polygon,
so the response still arrives — just with some polygons on the approximation.

## Frontend behavior

The "Solar resource" tile in the model notes shows one of:
- `NREL PVWatts v8 (N cached)` — real data; N grows as you run analyses
- `Approximation (no key)` — fallback mode

The caveats panel says either:
- "Solar generation per polygon: NREL PVWatts v8 (NSRDB resource)..." (real)
- "Solar generation per polygon: approximation (area × 0.15 MWh/m²)..." (fallback)

## Testing

`pytest` runs 27 tests total, 18 pass without setup. The PVWatts-specific
tests (10 of them) mock the network call, so they don't burn API quota.

One optional test exercises a real PVWatts call:
```bash
PVWATTS_LIVE_TEST=1 pytest tests/test_phase3.py::test_live_pvwatts_call
```
Requires a configured API key. Don't run this in CI.

## What Phase 3 still does NOT do

- Real polygons (Phase 4 — still hand-placed rectangles)
- Real renewable-mix recommendation (Phase 6)
- Real cost numbers (Phase 7)
- Anything CV / ML (Phase 5)

The API contract is unchanged. Per-polygon `est_annual_mwh` is now real
when the API key is set; everything else still flows through the same
shape.
