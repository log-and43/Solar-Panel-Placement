#!/usr/bin/env python3
"""
Warm a PVWatts solar-resource grid for the populated continental US.

KEY IDEA (the architecture decision):
  PVWatts yield depends only on LOCATION + array geometry, NOT on any
  specific building. So we pre-compute a per-kW yield on a coarse
  geographic grid, once per (cell, category). At request time, a polygon
  snaps to the nearest grid cell, picks its category's value, and scales
  by the polygon's actual kW. This severs the warming run from Overture
  and Overpass entirely — no polygon fetching needed to warm.

WHAT GETS WARMED:
  - Grid: ~0.1 degree (~11 km) cells. NSRDB (PVWatts' resource data) is
    ~4 km native, and irradiance changes little over 11 km, so this is a
    defensible sampling resolution. Documented as such.
  - Populated cells only: derived from the Census region centroids you
    already have (every county centroid + every city centroid, plus an
    optional neighborhood around cities). No population raster needed.
  - Per category: rooftop and parking get separate calls because their
    tilt / array-type / losses genuinely differ (not a linear scalar).
  - Single 1 kW reference per (cell, category). System size is collapsed:
    PVWatts output is linear in system_capacity, so request-time code
    multiplies the stored per-kW yield by the polygon's actual kW. This
    is accurate to a fraction of a percent.

OUTPUT:
  data/grid_solar_cache.parquet with columns:
    cell_lat, cell_lon, category, kwh_per_kw_year, tilt, array_type, losses
  Resumable: re-running skips (cell, category) pairs already present.

SELF-CONTAINED: makes its own PVWatts calls (reads the key from .env),
so it does not depend on app.pvwatts internals. Only app.regions is used,
for enumerating the populated points.

USAGE:
    python scripts/warm_grid_solar.py --dry-run            # count + estimate
    python scripts/warm_grid_solar.py --dry-run --city-radius 1
    python scripts/warm_grid_solar.py --rate 1000          # real run
    python scripts/warm_grid_solar.py --rate 5000 --city-radius 1
    # Resume after interruption: just run the same command again.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.regions import list_states, lookup, search  # noqa: E402

DATA_DIR = BACKEND_DIR / "data"
GRID_CACHE_PATH = DATA_DIR / "grid_solar_cache.parquet"
PROGRESS_PATH = DATA_DIR / "warm_grid_progress.json"
ENV_PATH = BACKEND_DIR / ".env"

PVWATTS_URL = "https://developer.nlr.gov/api/pvwatts/v8.json"

GRID_DEG = 0.1  # ~11 km cells

# Per-category array geometry. These are the canonical params once grid
# lookup becomes the primary path. Rooftop = latitude-tilted roof mount;
# parking = near-flat canopy. Kept distinct because tilt/array/losses are
# NOT linear scalars (unlike system size).
CATEGORY_PARAMS = {
    "rooftop": {"array_type": 1, "module_type": 0, "losses": 14.0,
                "azimuth": 180.0, "tilt_mode": "latitude"},
    "parking": {"array_type": 0, "module_type": 0, "losses": 16.0,
                "azimuth": 180.0, "tilt_mode": "flat"},
}


# ============================================================
# API key (self-contained .env reader)
# ============================================================

def load_api_key() -> str | None:
    import os
    for name in ("PVWATTS_API_KEY", "NREL_API_KEY", "ROCKIES_API_KEY"):
        v = os.environ.get(name)
        if v and v.strip():
            return v.strip()
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            if "=" not in line or line.strip().startswith("#"):
                continue
            k, val = line.split("=", 1)
            if k.strip().upper() in ("PVWATTS_API_KEY", "NREL_API_KEY", "ROCKIES_API_KEY"):
                val = val.strip().strip("\"'")
                if val:
                    return val
    return None


# ============================================================
# PVWatts call (self-contained)
# ============================================================

class PVWattsError(RuntimeError):
    pass


def call_pvwatts_per_kw(api_key: str, lat: float, lon: float,
                        tilt: float, azimuth: float, array_type: int,
                        module_type: int, losses: float) -> float:
    """Return annual kWh for a 1 kW system at this location/geometry."""
    params = {
        "api_key": api_key, "lat": f"{lat:.4f}", "lon": f"{lon:.4f}",
        "system_capacity": 1, "azimuth": azimuth, "tilt": f"{tilt:.1f}",
        "array_type": array_type, "module_type": module_type,
        "losses": losses, "dataset": "nsrdb", "timeframe": "monthly",
    }
    url = f"{PVWATTS_URL}?{urlencode(params)}"
    req = Request(url, headers={"User-Agent": "renewable-siting-gridwarm/0.6"})
    try:
        with urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")[:200]
        except Exception:
            pass
        raise PVWattsError(f"HTTP {e.code}: {body}") from e
    except (URLError, TimeoutError) as e:
        raise PVWattsError(f"network: {e}") from e

    errs = payload.get("errors") or []
    out = payload.get("outputs") or {}
    annual = float(out.get("ac_annual") or 0)
    if errs or annual <= 0:
        raise PVWattsError(f"bad output: {errs or 'empty'}")
    return annual


# ============================================================
# Grid construction from populated points
# ============================================================

def snap(v: float) -> float:
    return round(round(v / GRID_DEG) * GRID_DEG, 4)


def populated_cells(city_radius: int, limit_regions: int | None) -> set[tuple[float, float]]:
    """
    Build the set of (cell_lat, cell_lon) to warm.

    - Every county centroid contributes its cell (rural coverage).
    - Every city centroid contributes its cell, plus a (2*city_radius+1)^2
      neighborhood block (urban coverage; people aren't only at the exact
      centroid). city_radius=0 → centroid only; 1 → 3x3; 2 → 5x5.
    """
    cells: set[tuple[float, float]] = set()
    count = 0
    for st in list_states():
        abbr = st["abbr"]
        for rtype in ("county", "city"):
            for h in search(state=abbr, region_type=rtype, query="", limit=10000):
                try:
                    rec = lookup(h["state"], h["region_type"], h["name"])
                except Exception:
                    continue
                lat, lon = rec.centroid  # (lat, lon)
                clat, clon = snap(lat), snap(lon)
                if rtype == "city" and city_radius > 0:
                    for i in range(-city_radius, city_radius + 1):
                        for j in range(-city_radius, city_radius + 1):
                            cells.add((round(clat + i * GRID_DEG, 4),
                                       round(clon + j * GRID_DEG, 4)))
                else:
                    cells.add((clat, clon))
                count += 1
                if limit_regions and count >= limit_regions:
                    return cells
    return cells


def tilt_for(category: str, lat: float) -> float:
    mode = CATEGORY_PARAMS[category]["tilt_mode"]
    if mode == "latitude":
        return max(5.0, min(45.0, abs(lat)))
    return max(0.0, min(10.0, abs(lat)))  # flat canopy


# ============================================================
# Existing-cache load (for resume)
# ============================================================

def load_done() -> set[tuple[float, float, str]]:
    if not GRID_CACHE_PATH.exists():
        return set()
    import pandas as pd
    df = pd.read_parquet(GRID_CACHE_PATH)
    return {(round(r.cell_lat, 4), round(r.cell_lon, 4), r.category)
            for r in df.itertuples()}


def append_rows(rows: list[dict]) -> None:
    import pandas as pd
    new = pd.DataFrame(rows)
    if GRID_CACHE_PATH.exists():
        old = pd.read_parquet(GRID_CACHE_PATH)
        new = pd.concat([old, new], ignore_index=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    new.to_parquet(GRID_CACHE_PATH, index=False)


# ============================================================
# Rate limiter
# ============================================================

class RateLimiter:
    def __init__(self, per_hour: int):
        self.min_interval = 3600.0 / max(1, per_hour)
        self._last = 0.0

    def wait(self) -> None:
        now = time.monotonic()
        gap = now - self._last
        if gap < self.min_interval:
            time.sleep(self.min_interval - gap)
        self._last = time.monotonic()


def write_progress(d: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = PROGRESS_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, indent=2), encoding="utf-8")
    tmp.replace(PROGRESS_PATH)


# ============================================================
# Main
# ============================================================

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--rate", type=int, default=1000, help="PVWatts calls/hour ceiling.")
    p.add_argument("--dry-run", action="store_true", help="Count cells + estimate, no calls.")
    p.add_argument("--city-radius", type=int, default=0,
                   help="Cell neighborhood radius around cities (0=centroid, 1=3x3, 2=5x5).")
    p.add_argument("--limit-regions", type=int, default=None, help="Cap regions (testing).")
    args = p.parse_args()

    categories = list(CATEGORY_PARAMS.keys())

    print(f"Building populated grid (0.1 deg, city-radius={args.city_radius})...")
    cells = populated_cells(args.city_radius, args.limit_regions)
    total_units = len(cells) * len(categories)
    print(f"  {len(cells)} unique cells x {len(categories)} categories = {total_units} reference calls.\n")

    if args.dry_run:
        for rate in sorted({args.rate, 1000, 5000}):
            hrs = total_units / rate
            print(f"  at {rate}/hr: ~{hrs:.1f} hours ({hrs/24:.1f} days)")
        print("\n  (Re-run without --dry-run to warm. Resumable.)")
        return 0

    api_key = load_api_key()
    if not api_key:
        print("[error] No PVWatts API key found in env or .env.")
        return 1

    done = load_done()
    print(f"  {len(done)} (cell,category) pairs already cached; resuming.\n")

    limiter = RateLimiter(args.rate)
    made = skipped = errors = 0
    start = time.time()
    buffer: list[dict] = []

    sorted_cells = sorted(cells)
    for idx, (clat, clon) in enumerate(sorted_cells, 1):
        for cat in categories:
            if (clat, clon, cat) in done:
                skipped += 1
                continue
            params = CATEGORY_PARAMS[cat]
            tilt = tilt_for(cat, clat)
            limiter.wait()
            try:
                kwh = _with_backoff(api_key, clat, clon, tilt, params)
                buffer.append({
                    "cell_lat": clat, "cell_lon": clon, "category": cat,
                    "kwh_per_kw_year": round(kwh, 2), "tilt": round(tilt, 1),
                    "array_type": params["array_type"], "losses": params["losses"],
                })
                made += 1
            except PVWattsError as e:
                errors += 1
                print(f"    {clat},{clon} {cat}: {e}")

        # Flush to disk every 50 cells so progress survives interruption.
        if buffer and idx % 50 == 0:
            append_rows(buffer)
            buffer = []
            elapsed = time.time() - start
            rate_actual = made / (elapsed / 3600.0) if elapsed > 0 else 0
            print(f"[{idx}/{len(sorted_cells)} cells] made={made} skip={skipped} "
                  f"err={errors} ~{rate_actual:.0f}/hr")
            write_progress({
                "cells_done": idx, "cells_total": len(sorted_cells),
                "calls_made": made, "skipped": skipped, "errors": errors,
                "elapsed_seconds": round(elapsed, 0),
            })

    if buffer:
        append_rows(buffer)

    elapsed = time.time() - start
    print("\n=== Summary ===")
    print(f"  calls made: {made}  skipped: {skipped}  errors: {errors}")
    print(f"  elapsed:    {elapsed/3600.0:.2f} hours")
    print(f"  cache file: {GRID_CACHE_PATH}")
    return 0


def _with_backoff(api_key, lat, lon, tilt, params, max_retries=5) -> float:
    delay = 5.0
    for attempt in range(max_retries):
        try:
            return call_pvwatts_per_kw(
                api_key, lat, lon, tilt, params["azimuth"],
                params["array_type"], params["module_type"], params["losses"])
        except PVWattsError as e:
            msg = str(e).lower()
            if "429" in msg or "rate" in msg or "limit" in msg or "503" in msg:
                print(f"    backoff {delay:.0f}s (attempt {attempt+1})")
                time.sleep(delay)
                delay = min(delay * 2, 300)
                continue
            raise
    raise PVWattsError("max retries after backoff")


if __name__ == "__main__":
    sys.exit(main())
