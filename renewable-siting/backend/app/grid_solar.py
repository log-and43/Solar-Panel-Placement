"""
Grid solar lookup (Part B of the grid-warming architecture).

Reads the warmed grid produced by scripts/warm_grid_solar.py
(data/grid_solar_cache.parquet) and answers: "for a polygon at (lat, lon)
of this category and this many kW, what's the annual kWh?" — by snapping
to the nearest 0.1deg grid cell, reading the per-kW yield for the
category, and multiplying by kW.

This is the fast path: a warmed cell is an instant in-memory lookup, no
network. On a miss (cell not warmed, or grid file absent), the caller
falls back to the live PVWatts path in pvwatts.py.

Loaded once into memory (the grid is small — tens of thousands of rows).
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parent.parent
GRID_CACHE_PATH = BACKEND_DIR / "data" / "grid_solar_cache.parquet"

GRID_DEG = 0.1  # must match scripts/warm_grid_solar.py

# Map the app's polygon categories to the grid's warmed categories.
# cv_detected_parking shares parking's physical geometry.
_CATEGORY_ALIAS = {
    "rooftop": "rooftop",
    "parking": "parking",
    "cv_detected_parking": "parking",
}


def grid_available() -> bool:
    return GRID_CACHE_PATH.exists()


@lru_cache(maxsize=1)
def _grid() -> dict[tuple[float, float, str], float]:
    """
    Load the warmed grid into a dict keyed by (cell_lat, cell_lon, category)
    → kwh_per_kw_year. Cached for the process lifetime. Returns {} if the
    file is absent so callers cleanly fall back.
    """
    if not GRID_CACHE_PATH.exists():
        return {}
    try:
        import pandas as pd
        df = pd.read_parquet(GRID_CACHE_PATH)
    except Exception as e:
        logger.warning("Could not load grid solar cache: %s", e)
        return {}
    out: dict[tuple[float, float, str], float] = {}
    for r in df.itertuples():
        out[(round(r.cell_lat, 4), round(r.cell_lon, 4), r.category)] = float(r.kwh_per_kw_year)
    logger.info("Loaded grid solar cache: %d (cell,category) entries", len(out))
    return out


def _snap(v: float) -> float:
    return round(round(v / GRID_DEG) * GRID_DEG, 4)


def lookup_annual_kwh(lat: float, lon: float, system_kw: float, category: str
                      ) -> Optional[float]:
    """
    Return annual kWh for a system of `system_kw` at (lat, lon) for
    `category`, using the warmed grid. Returns None on a miss so the caller
    falls back to the live PVWatts path.

    The grid stores per-kW yield (1 kW reference); we scale linearly by
    system_kw — accurate to a fraction of a percent since PVWatts output
    is linear in system_capacity.
    """
    grid = _grid()
    if not grid:
        return None
    cat = _CATEGORY_ALIAS.get(category)
    if cat is None:
        return None
    key = (_snap(lat), _snap(lon), cat)
    per_kw = grid.get(key)
    if per_kw is None:
        return None
    return per_kw * system_kw


def stats() -> dict:
    g = _grid()
    return {"grid_available": bool(g), "entries": len(g),
            "path": str(GRID_CACHE_PATH)}
