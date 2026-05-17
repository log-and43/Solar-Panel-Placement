# Phase Plan

Each phase is intended to fit in roughly one to two weeks of part-time work
and to result in a working, demoable system at the end.

## Phase 1 — Walking skeleton (DONE in this commit)

**Goal:** Click the button, see a real map with highlighted polygons over
satellite imagery, see a diagnostic panel with plausible numbers, see the
honest-limitations panel. Everything is fake; the pipeline is real.

**Definition of done:**
- `uvicorn app.main:app --reload` runs
- `npm run dev` runs
- Selecting WA → Whatcom County → Run produces a map with sample rooftop
  and parking polygons in Bellingham, plus a numbers panel
- The contract test passes

## Phase 2 — Real consumption data

**Owner:** Grad student #1 + you for integration.
**Goal:** Replace `consumption.*` with real numbers from eGRID + EIA SEDS + Census ACS.

**Steps:**
1. Download the latest eGRID file (state-level generation mix).
2. Download EIA State Energy Data System (state-level total electricity consumption).
3. Use Census ACS 5-year for population at the city / county level.
4. `city_consumption ≈ state_consumption × (city_pop / state_pop)`.
   Add an uncertainty caveat for any region with <50k population.
5. Cache locally as Parquet or JSON — don't re-pull every request.

**Risk:** EIA APIs sometimes change; if so, fall back to the downloadable CSVs.

## Phase 3 — Real solar generation per polygon

**Owner:** You (NREL APIs require code).
**Goal:** Replace the trivial `area × 0.15` formula with NREL PVWatts.

**Steps:**
1. Get a free NREL developer API key (instant, no review).
2. For each rooftop/parking polygon, call PVWatts with:
   - lat/lon = polygon centroid
   - system size = area × packing factor (~0.6 for rooftop, ~0.4 for parking canopy) × panel W/m² (~200)
   - tilt = latitude, azimuth = 180 (south-facing default), losses = 14% (default)
3. PVWatts returns annual kWh; convert to MWh and store on the polygon.

**Risk:** Rate limits. Cache aggressively per (lat-rounded, lon-rounded) tuple.

## Phase 4 — Real polygons from public datasets

**Owner:** You (geospatial work).
**Goal:** Replace hand-placed Phase-1 polygons with real building footprints
and parking polygons.

**Steps:**
1. Microsoft US Building Footprints: download the per-state GeoJSON, clip to
   the region bbox. These are pre-computed for all of the US.
2. OSM parking lots: query Overpass for `amenity=parking` within the bbox.
3. Filter by minimum area (skip tiny garages; require ≥100 m² for rooftop,
   ≥500 m² for parking).
4. Hand the resulting FeatureCollection through Phase 3 to attach MWh.

**Risk:** OSM coverage varies wildly. Caveat any region with sparse parking data.

## Phase 5 — CV refinement (optional, only if Phase 4 done with time)

**Owner:** You.
**Goal:** Use SAM 2 on NAIP tiles to find parking lots OSM missed.

**Steps:**
1. Pull NAIP tiles for the bbox from Microsoft Planetary Computer (free, STAC API).
2. Run SAM 2 with a grid of point prompts.
3. Filter masks by shape (rectangularity > 0.6), area, and color (asphalt = dark, low saturation).
4. Reproject masks to lat/lon polygons; subtract overlap with OSM polygons.
5. Add as `properties.source = "cv_detected"` so the UI can show provenance.

**Risk:** This is the only phase that's "real" ML and the only one that needs a GPU.
If we drop it, the project is still complete. Treat as stretch goal.

## Phase 6 — Recommendation engine + coastal/offshore wind

**Owner:** Grad student #2 + you.
**Goal:** Replace hardcoded `recommendation` with a transparent scoring function.

**Steps:**
1. Coastline shapefile (NOAA): determine `is_coastal` (any part of region within 10 km of coast).
2. NREL NSRDB (solar) and WIND Toolkit (wind at 80m) — pull resource averages for the centroid.
3. Scoring function:
   - If rooftop+parking solar covers `fossil_mwh`, recommend solar, done.
   - Otherwise, evaluate offshore wind (if coastal) or onshore wind (if avg wind speed > 6 m/s at 80m and rural land available) for the gap.
   - If neither closes the gap, report it honestly — don't pretend the math works.

**Risk:** WIND Toolkit data is large. Use the API, don't download the whole thing.

## Phase 7 — Economics + polish

**Owner:** Grad student #1 + you.
**Goal:** Real cost and payback numbers.

**Steps:**
1. NREL ATB 2024 (Annual Technology Baseline) for $/W installed by tech.
2. Rooftop solar: ~$2.80/W installed (residential), ~$1.50/W (commercial). Use commercial as default.
3. Annual savings = annual_mwh × local retail electricity price (EIA state average).
4. CO₂ avoided = displaced_fossil_mwh × state grid CO₂ intensity (eGRID).
5. Polish: loading states, error handling, deploy if there's time.

**Risk:** Payback math is sensitive to assumptions. Show the inputs, let the user see what they're getting.
