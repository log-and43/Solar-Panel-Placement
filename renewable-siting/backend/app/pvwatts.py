"""
Phase 3: real solar generation per polygon, via NREL PVWatts v8.

Architecture:
  - load_api_key(): reads PVWATTS_API_KEY from backend/.env at import time.
    Returns None if missing — the pipeline soft-falls-back to area × 0.15.
  - pv_annual_kwh(): given a polygon's (lat, lon, area_m2, category), returns
    estimated annual kWh. Checks disk cache before calling PVWatts.
  - The cache is a JSON file at backend/data/pvwatts_cache.json, gitignored.
    Keyed by (lat_rounded, lon_rounded, kw_bucket, array_type) so nearby
    polygons of similar size share cache hits.

PVWatts v8 docs: https://developer.nrel.gov/docs/solar/pvwatts/v8/
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
CACHE_PATH = DATA_DIR / "pvwatts_cache.json"
ENV_PATH = BACKEND_DIR / ".env"

PVWATTS_URL = "https://developer.nrel.gov/api/pvwatts/v8.json"

# Source tag for the response. Lets the frontend / caveats know which
# generation source produced the numbers.
SOURCE_REAL = "NREL PVWatts v8 (NSRDB resource)"
SOURCE_FALLBACK = "Approximation (no API key configured)"


# ============================================================
# .env loading (tiny, no extra dependency)
# ============================================================

def _load_env_file(path: Path) -> dict[str, str]:
    """Parse a simple KEY=value .env file. Ignores comments and blank lines."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip("'").strip('"')
        if key:
            out[key] = val
    return out


def load_api_key() -> Optional[str]:
    """
    Look up the NREL API key. Tries the following names in order, both as
    OS environment variables and as keys in backend/.env:

      - PVWATTS_API_KEY  (canonical for this project)
      - NREL_API_KEY     (canonical for NREL's broader API ecosystem)
      - ROCKIES_API_KEY  (legacy NREL naming, still in some examples)

    Returns None if none of them have a value.
    """
    candidates = ("PVWATTS_API_KEY", "NREL_API_KEY", "ROCKIES_API_KEY")
    # 1. OS environment variables first (e.g. set by CI or shell)
    for name in candidates:
        v = os.environ.get(name)
        if v and v.strip():
            return v.strip()
    # 2. Then the .env file
    env = _load_env_file(ENV_PATH)
    for name in candidates:
        v = env.get(name)
        if v and v.strip():
            return v.strip()
    return None


def has_api_key() -> bool:
    return load_api_key() is not None


# ============================================================
# Per-category PVWatts defaults
# ============================================================

# Rooftops: tilt ≈ latitude, fixed roof mount, south-facing.
# Parking canopies: flatter tilt, fixed open rack (more weather-exposed).
# Numbers from NREL PVWatts default conventions; see docs for justification.

CATEGORY_DEFAULTS: dict[str, dict] = {
    "rooftop": {
        "module_type": 1,          # standard
        "array_type": 1,           # fixed - roof mounted
        "losses": 14.0,            # %, PVWatts default
        "azimuth": 180.0,          # south-facing
        "packing_factor": 0.55,    # 55% of footprint becomes panel (rest is HVAC, setbacks, walkways)
        "watts_per_m2": 200.0,     # typical crystalline silicon module
    },
    "parking": {
        "module_type": 1,
        "array_type": 0,           # fixed open rack (canopy)
        "losses": 16.0,            # slightly higher: outdoor exposure, soiling
        "azimuth": 180.0,
        "packing_factor": 0.65,    # canopies pack more densely than rooftops
        "watts_per_m2": 200.0,
    },
    # cv_detected_parking uses the parking defaults — same physical reality.
    "cv_detected_parking": {
        "module_type": 1, "array_type": 0, "losses": 16.0,
        "azimuth": 180.0, "packing_factor": 0.65, "watts_per_m2": 200.0,
    },
}


# ============================================================
# Cache
# ============================================================

class _Cache:
    """JSON-on-disk cache. Loaded once, written incrementally."""

    def __init__(self, path: Path):
        self.path = path
        self._data: dict[str, float] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("PVWatts cache unreadable, starting fresh: %s", e)
                self._data = {}
        self._loaded = True

    def get(self, key: str) -> Optional[float]:
        self._ensure_loaded()
        return self._data.get(key)

    def set(self, key: str, value: float) -> None:
        self._ensure_loaded()
        self._data[key] = value
        self._flush()

    def _flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic-ish write: tmp file + rename. Avoids half-written JSON on crash.
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self._data), encoding="utf-8")
        tmp.replace(self.path)

    def stats(self) -> dict:
        self._ensure_loaded()
        return {"entries": len(self._data), "path": str(self.path)}


_cache = _Cache(CACHE_PATH)


def cache_stats() -> dict:
    return _cache.stats()


# ============================================================
# Cache key construction
# ============================================================

def _cache_key(lat: float, lon: float, system_kw: float, array_type: int,
               tilt: float, azimuth: float, losses: float) -> str:
    """
    Round inputs so nearby polygons of similar size share cache hits.

    Rationale:
      - NSRDB resource data is at ~4 km resolution; rounding lat/lon to 2
        decimals (~1.1 km) is well within a single resource cell.
      - Rounding system size to 0.5 kW buckets means a 50 m² and 55 m² roof
        of the same category share an entry.
      - Tilt rounded to 1°, azimuth to 5°, losses to 1% — all far below
        PVWatts noise.
    """
    return (
        f"{round(lat, 2)},{round(lon, 2)},"
        f"{round(system_kw * 2) / 2:.1f},"
        f"{array_type},{round(tilt):d},{round(azimuth / 5) * 5:d},"
        f"{round(losses):d}"
    )


# ============================================================
# PVWatts call
# ============================================================

class PVWattsError(RuntimeError):
    pass


def _call_pvwatts(api_key: str, *, system_kw: float, lat: float, lon: float,
                  module_type: int, array_type: int, tilt: float, azimuth: float,
                  losses: float, timeout: float = 15.0) -> float:
    """Returns ac_annual (kWh)."""
    params = {
        "api_key": api_key,
        "system_capacity": f"{system_kw:.3f}",
        "module_type": module_type,
        "losses": f"{losses:.1f}",
        "array_type": array_type,
        "tilt": f"{tilt:.1f}",
        "azimuth": f"{azimuth:.1f}",
        "lat": f"{lat:.4f}",
        "lon": f"{lon:.4f}",
        "timeframe": "hourly",
        "dataset": "nsrdb",
    }
    url = f"{PVWATTS_URL}?{urlencode(params)}"
    req = Request(url, headers={"User-Agent": "renewable-siting/0.3"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        # Read the body anyway — NREL usually returns useful error JSON.
        detail = ""
        try:
            detail = e.read().decode("utf-8", errors="ignore")[:400]
        except Exception:
            pass
        raise PVWattsError(f"PVWatts HTTP {e.code}: {detail}") from e
    except URLError as e:
        raise PVWattsError(f"PVWatts network error: {e}") from e

    # NREL responds 200 even when params are invalid; check the body.
    errs = body.get("errors") or []
    if errs:
        raise PVWattsError(f"PVWatts errors: {errs}")
    outputs = body.get("outputs") or {}
    annual = outputs.get("ac_annual")
    if annual is None:
        raise PVWattsError(f"PVWatts missing ac_annual; body keys: {list(body.keys())}")
    return float(annual)


# ============================================================
# Public API used by pipeline
# ============================================================

def pv_annual_mwh(
    *, lat: float, lon: float, area_m2: float, category: str,
) -> tuple[float, str]:
    """
    Return (annual MWh, source_tag) for a single polygon.

    If no API key is configured, returns the fallback approximation.
    If PVWatts call fails, logs and returns the fallback approximation —
    so a transient network issue mid-run can't take down /analyze.
    """
    defaults = CATEGORY_DEFAULTS.get(category)
    if defaults is None:
        # Unknown category (e.g. offshore_wind_zone) — not solar; caller
        # should not be asking us. Return 0 to be defensive.
        return 0.0, SOURCE_FALLBACK

    api_key = load_api_key()
    panel_area = area_m2 * defaults["packing_factor"]
    system_kw = (panel_area * defaults["watts_per_m2"]) / 1000.0

    # Tilt = latitude (rule of thumb for fixed-tilt panels).
    tilt = max(0.0, min(60.0, abs(lat)))
    if defaults["array_type"] == 0:
        # Parking canopies are typically flatter than roofs.
        tilt = min(tilt, 10.0)

    if api_key is None or system_kw <= 0:
        # Fallback: rough 150 kWh/m² of panel per year. The OLD Phase-1
        # formula was area × 0.15 (without packing factor), which assumed
        # the whole footprint was panel; we keep that math here for
        # backward compatibility with the existing demo numbers.
        fallback_mwh = area_m2 * 0.00015 * 1000  # area_m2 * 0.15 / 1000 = MWh
        return area_m2 * 0.15 / 1000.0, SOURCE_FALLBACK

    # Check cache
    key = _cache_key(
        lat, lon, system_kw, defaults["array_type"],
        tilt, defaults["azimuth"], defaults["losses"],
    )
    cached = _cache.get(key)
    if cached is not None:
        return cached / 1000.0, SOURCE_REAL  # cache stores kWh; convert to MWh

    # Call NREL
    try:
        annual_kwh = _call_pvwatts(
            api_key,
            system_kw=system_kw, lat=lat, lon=lon,
            module_type=defaults["module_type"],
            array_type=defaults["array_type"],
            tilt=tilt, azimuth=defaults["azimuth"],
            losses=defaults["losses"],
        )
    except PVWattsError as e:
        logger.warning("PVWatts failed for (%.4f, %.4f, %s): %s — falling back",
                       lat, lon, category, e)
        return area_m2 * 0.15 / 1000.0, SOURCE_FALLBACK

    _cache.set(key, annual_kwh)
    return annual_kwh / 1000.0, SOURCE_REAL
