# Frontend (React + Vite + Leaflet)

Phase 1 walking skeleton.

## Local dev

```bash
npm install
npm run dev
```

Open http://localhost:5173. Make sure the backend is running on
http://localhost:8000 first.

## Environment

Set `VITE_API_BASE` to point at a different backend URL. Defaults to
`http://localhost:8000`.

## Layout

- `RegionPicker` — state/denomination/name → calls `/regions` to populate.
- `ResultMap` — Leaflet with Esri World Imagery basemap, draws GeoJSON
  polygons returned by `/analyze`, colored by category. Map auto-fits the
  region bbox when results arrive.
- `Diagnostic` — generation mix bar, consumption stats, recommendation,
  economics. Reads strictly from the API contract; doesn't compute anything
  the backend didn't provide.
- `Caveats` — renders `result.caveats` verbatim. The honesty surface.

## Why no state management library

Single-screen app. `useState` is plenty. If/when Phase 6 brings comparison
between regions, revisit.

## Build

```bash
npm run build
```

Outputs to `dist/`. The map's tile layer loads from Esri's public ArcGIS
endpoint, which has no API key requirement for low-traffic use. Read their
ToS before any production deploy.
