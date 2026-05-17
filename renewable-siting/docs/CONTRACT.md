# /analyze API Contract

This is the spine of the project. The contract is **frozen** at Phase 1.
Every subsequent phase replaces the *source* of a field, never the *shape*.

## Endpoint

`POST /analyze`

### Request

```json
{
  "state": "WA",
  "region_type": "county",
  "region_name": "Whatcom County"
}
```

- `state`: USPS 2-letter code, continental US only.
- `region_type`: `"county"` or `"city"`.
- `region_name`: human-readable name as it appears in the picker.

### Response

```json
{
  "region": {
    "name": "Whatcom County",
    "type": "county",
    "state": "WA",
    "bbox": [-122.76, 48.55, -120.97, 49.00],
    "centroid": [48.84, -121.93],
    "is_coastal": true
  },
  "consumption": {
    "total_mwh_per_year": 2100000,
    "fossil_mwh_per_year": 230000,
    "mix": {
      "coal": 0.04,
      "natural_gas": 0.07,
      "nuclear": 0.08,
      "hydro": 0.65,
      "wind": 0.08,
      "solar": 0.02,
      "other": 0.06
    },
    "source": "PHASE_1_HARDCODED"
  },
  "polygons": {
    "type": "FeatureCollection",
    "features": [
      {
        "type": "Feature",
        "geometry": { "type": "Polygon", "coordinates": [[[...]]] },
        "properties": {
          "category": "rooftop" | "parking" | "offshore_wind_zone",
          "area_m2": 1500,
          "est_annual_mwh": 0.22,
          "suitability_score": 0.85
        }
      }
    ]
  },
  "recommendation": {
    "primary": "mixed",
    "covered_mwh_per_year": 230000,
    "gap_mwh_per_year": 0,
    "alternatives": [
      { "tech": "offshore_wind", "rationale": "coastal region, fossil gap remains after rooftop solar", "potential_mwh": 180000 }
    ],
    "notes": "Whatcom is already 65% hydro; rooftop solar can plausibly close the remaining fossil gap."
  },
  "economics": {
    "install_cost_usd": 480000000,
    "annual_savings_usd": 32000000,
    "payback_years": 15,
    "co2_avoided_tons_per_year": 95000
  },
  "caveats": [
    "Consumption figures below state level are extrapolated from state totals by population share.",
    "Generation estimates use NREL PVWatts defaults and do not account for shading, structural, or zoning constraints.",
    "Cost and payback figures use national averages and are not site-specific.",
    "Offshore wind potential is technical, not permitted; real development requires multi-year federal review."
  ]
}
```

## Phase-by-phase: what becomes real

| Field | Phase 1 | Replaced in |
|-------|---------|-------------|
| `region.bbox`, `centroid` | Real (from a static lookup table) | — |
| `region.is_coastal` | Hardcoded | Phase 6 (coastline shapefile) |
| `consumption.*` | Hardcoded for Whatcom only | Phase 2 |
| `polygons.features` | Hand-placed sample polygons | Phase 4 (real), Phase 5 (CV refinement) |
| `properties.est_annual_mwh` | Trivial: area × 0.15 kWh/m² | Phase 3 (PVWatts) |
| `recommendation.*` | Hardcoded | Phase 6 |
| `economics.*` | Hardcoded | Phase 7 |
| `caveats` | Static list | Grows as we learn what's wrong |

## Why the contract is frozen

Because there are 4 people on the team and only one developer. If the API
shape changes mid-project, the frontend, backend, tests, and grad-student
data work all have to re-sync. Locking the shape early means each phase
is a localized change.

If the contract genuinely needs to evolve, that's a deliberate decision
and gets a PR titled `contract: ...` so everyone notices.
