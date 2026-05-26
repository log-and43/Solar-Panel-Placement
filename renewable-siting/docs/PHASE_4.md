# Phase 4 — Real Polygons (Overture buildings + OSM parking)

This is the phase where the map stops looking like a demo. The Phase 1
placeholder rectangles get replaced with real building outlines from
Overture Maps and real parking polygons from OpenStreetMap.

## What changed

| File | Change |
|------|--------|
| `backend/app/polygons.py` | NEW: Overture + Overpass clients, filter+cap logic, per-region cache |
| `backend/app/pipeline.py` | Calls `real_polygons()` first; soft-falls-back to fakes when neither source returns anything |
| `backend/app/main.py` | NEW endpoint: `/polygons/status` |
| `backend/app/schemas.py` | `PolygonProperties` gains a `generation_source` field (separates polygon provenance from yield provenance) |
| `backend/requirements.txt` | Adds `duckdb>=1.1.0` |
| `backend/tests/test_phase4.py` | NEW: 11 tests, all run offline (mocked Overture + Overpass) |
| `frontend/src/lib/api.js` | Adds `getPolygonsStatus()` |
| `frontend/src/components/ModelNotes.jsx` | 4-tile provenance grid (was 3); shows polygons source and cache count |
| `frontend/src/components/ResultMap.jsx` | Tooltip shows polygon shape source and yield source separately |
| `.gitignore` | Adds `backend/data/polygon_cache/` |

## Data sources

**Buildings — Overture Maps.** Successor to Microsoft Building Footprints,
maintained jointly by Microsoft, Meta, Amazon, and TomTom. Hosted as
cloud-native GeoParquet on AWS S3, queryable via DuckDB's spatial extension
without downloading anything beyond the bbox we want.

**Parking — OpenStreetMap via Overpass.** Live query of `amenity=parking`
ways within the region bbox. Two mirrors (overpass-api.de and
overpass.kumi.systems) are tried in order; falls back gracefully if both
are unreachable.

**Setup:**
```bash
cd backend
source .venv/bin/activate
pip install -r requirements.txt   # picks up duckdb
```

That's all. No API keys, no .env edits. Overture and Overpass are
unauthenticated public services.

## Pre-filter strategy

| Layer | Min area | Max count | Rationale |
|-------|----------|-----------|-----------|
| Rooftops | 250 m² | 1,500 | Drops residential garages, sheds, and small homes. Most US rooftop solar capacity is on commercial/industrial scale buildings (warehouses, schools, big-box). Cap of 1,500 keeps PVWatts cold-run latency tolerable. |
| Parking | 500 m² | 500 | Drops street parking and micro-lots. Large surface lots are the realistic solar canopy candidates. |

The "filter + cap" approach was chosen over clustering small adjacent
buildings into neighborhood blobs. Clustering would have produced
abstract polygons that don't correspond to real installable surfaces,
turning the PVWatts call back into approximation. The filter+cap
version keeps every polygon a real, defensible solar candidate.

## Caching

**Per-region polygon cache** in `backend/data/polygon_cache/`, gitignored.
One JSON file per `(state, region_type, name)`. First call to a region:
~5-30 seconds (Overture S3 + Overpass). Subsequent calls: instant.

**PVWatts cache** already existed in Phase 3. Critical for Phase 4 because
1,500 buildings would otherwise blow through the 1,000/hour NREL rate
limit on a cold run. The existing cache-key bucketing (lat to 2 decimals,
system kW to 0.5 kW) collapses many polygons in the same neighborhood
into a single PVWatts call.

## Provenance separation

Before Phase 4, `PolygonProperties.source` was a single string used for
both "where did this polygon shape come from" and (after Phase 3) "where
did this yield estimate come from." That was a smell — Phase 4 splits it:

- `source` — polygon provenance: `"Phase 4 real polygons"`, `"PHASE_1_HARDCODED"`, or future `"Phase 5 CV-detected"`
- `generation_source` — yield provenance: `"NREL PVWatts v8 (NSRDB resource)"` or `"Approximation (no API key configured)"`

The tooltip on the map shows both, on separate lines.

## Soft fallback chain

When the user clicks Run:

1. `real_polygons(region)` tries Overture → if duckdb is missing or the
   S3 query fails, returns `[]` buildings.
2. Then tries Overpass → if both mirrors fail or no parking is tagged in
   OSM for this bbox, returns `[]` parking.
3. If **both** rooftops and parking come back empty, the pipeline falls
   back to Phase 1 `fake_polygons()` so the demo still shows something.
4. Caveats explain what happened. The user sees exactly which source
   succeeded and which fell back.

This means the app demos cleanly on a flight with no Wi-Fi (falls back
to Phase 1), and demos beautifully when online (real shapes, real
PVWatts numbers). Same principle as Phase 3.

## Known limits

- **OSM parking coverage is uneven.** Manhattan is well-mapped; rural
  counties may have zero tagged parking. The caveats panel surfaces this.
- **Overture buildings are static.** They reflect a snapshot in time —
  buildings constructed after the Overture release date won't appear.
- **No agricultural exclusion zone.** The "Avoid productive agriculture"
  toggle still doesn't filter polygons. Phase 6 wires that in.
- **No real offshore-wind polygons yet.** Coastal regions still get a
  synthesized offshore_wind_zone from Phase 1 logic. Phase 6 replaces.
- **No CV-detected parking yet.** Phase 5 augments OSM parking with SAM
  on NAIP tiles.

## What's still placeholder

The only Phase 1 leftovers in the pipeline are:
- Offshore wind zone polygon (synthesized for coastal regions)
- Cost / payback / CO₂ formulas (Phase 7)
- Recommendation engine (Phase 6)

`fake_polygons()` itself is still used as a fallback when both Phase 4
sources return nothing.

## Tests

11 new tests in `tests/test_phase4.py`, all offline (mocked sources).
Total suite: 34 passing, 9 skipped pending Phase 2 data or live network
calls. Test coverage includes:

- Area computation across latitudes
- Filter and cap behavior
- Cache write/read round-trip
- Empty-sources fallback
- Overpass JSON parsing (closed and unclosed ways)
- Pipeline integration via `/analyze`
