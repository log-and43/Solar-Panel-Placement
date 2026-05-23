# Post-Codex Phase 2

This phase is a frontend merge with a parallel Codex-built version produced
by a teammate. It adopts visual and interaction patterns from that version
without changing the backend, data layer, or API contract.

## What was adopted

| From Codex | Where it lives now |
|------------|---------------------|
| Dark satellite theme (palette `#101414`, `#181f1e`, `#a7b8ae`, `#67d391`, `#f5c45b`, `#53c7df`, `#6ea2ff`) | `tailwind.config.js`, `src/index.css` |
| "SP" brand mark, "Solar Placement" naming | `src/components/Brand.jsx` |
| Segmented County/City control | `RegionPicker.jsx` |
| Energy target input ("Fossil energy to offset") | `TargetsPanel.jsx` |
| "Avoid productive agriculture" toggle (disabled, marked Phase 6) | `TargetsPanel.jsx` |
| "Include offshore zones" toggle (real filter) | `TargetsPanel.jsx` |
| Per-category layer toggles (rooftop / parking / offshore / CV) | `LayersPanel.jsx` |
| 4-card diagnostic strip below the map | `Diagnostic.jsx` |
| Model-notes section with provenance grid | `ModelNotes.jsx` |
| Status pill (Ready / Analyzing / Error) | `App.jsx` topbar |
| Map legend styled to match the rest of the dark theme | `ResultMap.jsx` |

## What was kept from our version

- **Backend architecture**: FastAPI, Pydantic schemas, frozen API contract
- **Data pipeline**: build script downloading EIA SEDS, EPA eGRID, Census ACS into Parquet at build time (not API-at-runtime)
- **Coverage**: 48 continental states, ~3,100 counties, ~3,100 cities ≥ 10k population
- **Phase-1 fallback**: app degrades to fallback mode if Parquet files aren't built
- **Honest caveats panel**: limitations surfaced in the UI
- **17 tests**: contract test + Phase 2 tests preserved
- **The map-real-Leaflet-with-Esri-satellite-tiles instead of a fake CSS grid**

## What was deliberately not adopted

- Hardcoded `STATE_CENTERS` / `COORDS` lookup tables — we have real centroids for ~6,000 regions from Census TIGER, no need for hand-typed lat/lng for ~24 places
- `SEED_DATA` (4 states, 12 places hand-typed) — we have real EIA SEDS + Census ACS
- Census API proxy at runtime — our build-time Parquet approach is offline-resilient
- The template-polygon "model" — polygons at fixed screen positions like `x:18, y:18`, scaled by invented multipliers `× 0.45`. This is fake analysis. Phase 4 replaces our Phase 1 hand-placed polygons with real Microsoft Building Footprints + OSM data; we don't want to layer additional fake math on top.

## How the new controls actually behave

**Energy target input.** When set, the diagnostic recomputes the "% covered"
against this number instead of `consumption.fossil_mwh_per_year`. The
backend response is unchanged; this is a frontend-only override that lets
the user explore "what if we just wanted to offset 1.21 GWh of coal" without
needing to displace the entire fossil load. **Real.**

**Include offshore zones.** Filters out `offshore_wind_zone` polygons from
the map regardless of the layer panel state. **Real.**

**Avoid productive agriculture.** Disabled checkbox with a "Phase 6" hint.
We don't have agriculture data yet. The Codex version used this as a
multiplier in a fake siting model; we won't lie about it. When Phase 6
brings in NREL siting layers, this toggle gets wired through to a real
siting-suitability filter.

**Layer toggles.** Frontend-only filter on the polygon FeatureCollection
returned by the backend. **Real.**

## Why this merge is worth doing

The Codex version is a more polished demo surface; our version is more
defensible underneath. The grader who clicks through to the demo sees
the dark satellite theme, the energy target knob, the layer toggles, the
four-card diagnostics. The grader who reads the code or the writeup sees
the EIA pipeline, the 17 tests, the frozen contract, the honest caveats.
Both audiences are satisfied.

## Iteration model

Two parallel implementations + AI tooling + a human integrating them per
phase. Each phase the two implementations exchange ideas: visual taste
flows one way, data engineering rigor flows the other. Future phases:

- **Phase 3 (PVWatts):** swap rooftop/parking est_annual_mwh for real NREL PVWatts
- **Phase 4 (real polygons):** Microsoft Building Footprints + OSM parking
- **Phase 5 (ML):** SAM 2 on NAIP tiles for parking lots OSM missed
- **Phase 6 (recommendation engine):** NREL WIND Toolkit, coastline distance, agriculture data — wires the Phase 2 "avoid agriculture" toggle to real siting layers
- **Phase 7 (economics polish):** NREL ATB, state-specific retail rates
