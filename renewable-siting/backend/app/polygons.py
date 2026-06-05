"""
Phase 4: real polygons from Overture Maps (buildings) and OpenStreetMap
parking (via Overpass API).

Public surface:
  real_polygons(region) -> PolygonCollection
  source_status() -> dict     # for /polygons/status diagnostic

Architecture choices (and why):

  - Overture Maps' GeoParquet (released by Microsoft+Meta+Amazon+TomTom) is
    queried via duckdb's spatial extension. This lets us pull just the
    bbox we care about without downloading the whole-state file.
  - OSM parking is fetched live from Overpass. Coverage varies wildly by
    region — sparse-coverage areas get an honest caveat in the response.
  - Both sources are cached to disk per (state, region_type, region_name).
    Cache is gitignored, accumulates over a demo.
  - When Overture is unreachable or returns nothing, we fall back to Phase 1
    fake polygons rather than break the pipeline. Same soft-fallback
    principle as Phase 3 PVWatts.

Tunable constants live at the top of the module so a teammate can tweak
without diving into the SQL.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from shapely.geometry import shape, mapping

from .regions import RegionRecord
from .schemas import PolygonCollection, PolygonFeature, PolygonProperties

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
POLYGON_CACHE_DIR = DATA_DIR / "polygon_cache"


# ============================================================
# Tunables
# ============================================================

# Pre-filter: drop buildings smaller than this. Residential garages,
# sheds, and small homes aren't realistic rooftop-solar candidates.
# Most US rooftop solar capacity is on commercial/industrial buildings.
MIN_BUILDING_AREA_M2 = 250.0

# Pre-filter for parking lots: skip street-side spots & micro-lots.
MIN_PARKING_AREA_M2 = 500.0

# Top-N caps after filtering. Sorted by area descending.
MAX_BUILDINGS = 1_500
MAX_PARKING = 500

# Overture release(s) to query. They publish monthly; the exact "release" path
# segment changes each release. We try a list of recent known-good releases in
# order, falling through to the next if a query returns no files. This means
# the pipeline survives Overture moving forward without code changes for a few
# months, and a teammate can add new releases here as Overture publishes them.
#
# When updating: check https://docs.overturemaps.org/release/ for the latest
# version string and add it at the top of the list. Or run the diagnostic in
# scripts/check_overture.py to list available releases.
OVERTURE_RELEASES: tuple[str, ...] = (
    "2026-04-15.0",   # confirmed current as of 2026-05
    "2026-03-19.0",
    "2026-02-19.0",
    "2026-01-22.0",
    "2025-12-18.0",
    "2025-11-13.0",
    "2025-10-23.0",
    "2025-09-24.0",
)
# Include the *.parquet suffix explicitly — some duckdb versions are picky
# about glob patterns matching directory listings vs file lists.
OVERTURE_BUILDINGS_URL = (
    "s3://overturemaps-us-west-2/release/{release}/theme=buildings/type=building/*.parquet"
)

# Overpass mirror. The main api.de and kumi.systems are both reliable.
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
OVERPASS_TIMEOUT_SECONDS = 25


# ============================================================
# Status
# ============================================================

SOURCE_OVERTURE = "Overture Maps (buildings)"
SOURCE_OSM = "OpenStreetMap via Overpass (parking)"
SOURCE_PHASE1 = "Phase 1 placeholder (Overture unreachable)"


@dataclass
class FetchResult:
    polygons: PolygonCollection
    buildings_source: str
    parking_source: str
    buildings_found: int
    parking_found: int
    notes: list[str]


# ============================================================
# Disk cache
# ============================================================

def _cache_path(region: RegionRecord) -> Path:
    safe_name = region.name.replace("/", "-").replace(" ", "_")
    return POLYGON_CACHE_DIR / f"{region.state}-{region.region_type}-{safe_name}.json"


def _read_cache(region: RegionRecord) -> Optional[dict]:
    p = _cache_path(region)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Polygon cache unreadable, ignoring: %s", e)
        return None


def _write_cache(region: RegionRecord, data: dict) -> None:
    POLYGON_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    p = _cache_path(region)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    tmp.replace(p)


def cache_stats() -> dict:
    if not POLYGON_CACHE_DIR.exists():
        return {"entries": 0, "path": str(POLYGON_CACHE_DIR)}
    return {
        "entries": len(list(POLYGON_CACHE_DIR.glob("*.json"))),
        "path": str(POLYGON_CACHE_DIR),
    }


# ============================================================
# Area in m² from a (lon, lat) polygon
# ============================================================

def _polygon_area_m2(geometry: dict) -> float:
    """
    Project the polygon to a local azimuthal equal-area projection so we
    can compute area in m². We avoid pyproj as a hard dependency by using
    a simple equirectangular approximation around the polygon's centroid —
    accurate to within a few percent for typical urban-scale polygons.
    """
    geom = shape(geometry)
    if geom.is_empty:
        return 0.0
    cy = geom.centroid.y  # latitude
    # 1 deg lat ≈ 111_320 m anywhere; 1 deg lon ≈ 111_320 * cos(lat)
    import math
    lat_m = 111_320.0
    lon_m = 111_320.0 * math.cos(math.radians(cy))
    # shapely .area is in (deg×deg). Convert.
    return float(geom.area) * lat_m * lon_m


# ============================================================
# Overture (buildings) via duckdb spatial
# ============================================================

# We import duckdb lazily so the rest of the app starts even if it isn't
# installed. If duckdb is unavailable, we soft-fall-back to Phase 1.

def _overture_available() -> bool:
    try:
        import duckdb  # noqa: F401
        return True
    except ImportError:
        return False


def _fetch_overture_buildings(bbox: tuple[float, float, float, float]
                              ) -> list[dict]:
    """
    Query Overture buildings within the bbox. Returns a list of GeoJSON
    polygons (no properties yet). Empty list on failure — the caller
    decides what to do.

    bbox is (west, south, east, north) in WGS84.

    We try each known Overture release in order. The first one that resolves
    (returns *any* response, even 0 rows in the bbox) wins. This lets the
    pipeline survive Overture publishing a new release without code changes
    for a few months, and lets a teammate add new releases to the constant.
    """
    if not _overture_available():
        logger.warning("duckdb not installed; skipping Overture buildings")
        return []

    import duckdb

    west, south, east, north = bbox

    con = duckdb.connect()
    try:
        con.execute("INSTALL spatial; LOAD spatial;")
        con.execute("INSTALL httpfs; LOAD httpfs;")
        con.execute("SET s3_region='us-west-2';")
    except Exception as e:
        logger.warning("duckdb extension setup failed: %s", e)
        con.close()
        return []

    last_err: Optional[Exception] = None
    for release in OVERTURE_RELEASES:
        url = OVERTURE_BUILDINGS_URL.format(release=release)
        try:
            # Overture's bbox is a STRUCT{xmin,ymin,xmax,ymax}. We use INTERSECTS
            # semantics (any overlap), not strict containment, so we don't drop
            # buildings that straddle the bbox edge.
            query = f"""
                SELECT ST_AsGeoJSON(geometry) AS geom_json
                FROM read_parquet('{url}', filename=true, hive_partitioning=1)
                WHERE
                    bbox.xmin < {east} AND bbox.xmax > {west}
                    AND bbox.ymin < {north} AND bbox.ymax > {south}
                LIMIT 5000
            """
            rows = con.execute(query).fetchall()
            logger.warning("Overture release %s returned %d buildings for bbox",
                           release, len(rows))
            # We found a release that works. If it returned 0 rows for the
            # bbox, that's fine — it means the area genuinely has no Overture
            # buildings. Don't fall through to older releases (which would
            # give us a different snapshot of the same area).
            con.close()
            out: list[dict] = []
            for (geom_json,) in rows:
                try:
                    out.append(json.loads(geom_json))
                except json.JSONDecodeError:
                    continue
            return out
        except Exception as e:
            last_err = e
            logger.warning("Overture release %s not available (%s); trying older",
                           release, type(e).__name__)
            continue

    con.close()
    logger.warning("All Overture releases failed; last error: %s", last_err)
    return []


# ============================================================
# OSM parking via Overpass
# ============================================================

def _overpass_query(bbox: tuple[float, float, float, float]) -> str:
    """Overpass QL: parking polygons within bbox."""
    west, south, east, north = bbox
    # Overpass uses (south, west, north, east) order.
    return f"""
[out:json][timeout:{OVERPASS_TIMEOUT_SECONDS}];
(
  way["amenity"="parking"]({south},{west},{north},{east});
  relation["amenity"="parking"]({south},{west},{north},{east});
);
out geom;
""".strip()


def _fetch_osm_parking(bbox: tuple[float, float, float, float]) -> list[dict]:
    """
    Query Overpass for parking polygons. Returns GeoJSON polygons.
    Tries multiple mirrors; returns [] if all fail (caller decides).
    """
    query = _overpass_query(bbox)
    data = urlencode({"data": query}).encode("utf-8")

    last_err: Optional[Exception] = None
    for url in OVERPASS_URLS:
        try:
            req = Request(
                url,
                data=data,
                headers={"User-Agent": "renewable-siting/0.4"},
            )
            with urlopen(req, timeout=OVERPASS_TIMEOUT_SECONDS + 5) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            return _overpass_to_geojson(payload)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as e:
            last_err = e
            logger.warning("Overpass %s failed: %s", url, e)
            continue

    logger.warning("All Overpass mirrors failed; last error: %s", last_err)
    return []


def _overpass_to_geojson(payload: dict) -> list[dict]:
    """Convert Overpass `out geom` JSON to a list of GeoJSON polygons."""
    out: list[dict] = []
    for el in payload.get("elements", []):
        et = el.get("type")
        if et == "way" and el.get("geometry"):
            coords = [[p["lon"], p["lat"]] for p in el["geometry"]]
            if len(coords) < 4:
                continue
            # Ensure ring closure for GeoJSON
            if coords[0] != coords[-1]:
                coords.append(coords[0])
            out.append({"type": "Polygon", "coordinates": [coords]})
        elif et == "relation":
            # Relations with multiple ways — combine outer rings into a MultiPolygon.
            # Simple approach: take each outer member as its own Polygon.
            for member in el.get("members", []):
                if member.get("role") != "outer" or not member.get("geometry"):
                    continue
                coords = [[p["lon"], p["lat"]] for p in member["geometry"]]
                if len(coords) < 4:
                    continue
                if coords[0] != coords[-1]:
                    coords.append(coords[0])
                out.append({"type": "Polygon", "coordinates": [coords]})
    return out


# ============================================================
# Polygon construction
# ============================================================

def _to_features(
    geoms: list[dict],
    *,
    category: str,
    min_area: float,
    cap: int,
    suitability: float,
) -> list[PolygonFeature]:
    """Filter by area, sort by area desc, cap, wrap as PolygonFeatures."""
    sized = []
    for g in geoms:
        try:
            area = _polygon_area_m2(g)
        except Exception:
            continue
        if area < min_area:
            continue
        sized.append((area, g))
    sized.sort(key=lambda x: x[0], reverse=True)
    sized = sized[:cap]

    features: list[PolygonFeature] = []
    for area, g in sized:
        features.append(PolygonFeature(
            geometry=g,
            properties=PolygonProperties(
                category=category,  # type: ignore[arg-type]
                area_m2=round(area, 0),
                est_annual_mwh=0.0,  # filled in by PVWatts enrichment step
                suitability_score=suitability,
                source="Phase 4 real polygons",
            ),
        ))
    return features


# ============================================================
# Public entrypoint
# ============================================================

def real_polygons(region: RegionRecord) -> FetchResult:
    """
    Fetch building and parking polygons for a region. Cached per region.
    """
    # Cache hit?
    cached = _read_cache(region)
    if cached is not None:
        try:
            coll = PolygonCollection.model_validate(cached["polygons"])
            return FetchResult(
                polygons=coll,
                buildings_source=cached.get("buildings_source", SOURCE_OVERTURE),
                parking_source=cached.get("parking_source", SOURCE_OSM),
                buildings_found=cached.get("buildings_found", 0),
                parking_found=cached.get("parking_found", 0),
                notes=cached.get("notes", []),
            )
        except Exception as e:
            logger.warning("Cached polygons for %s/%s/%s invalid; refetching: %s",
                           region.state, region.region_type, region.name, e)

    notes: list[str] = []

    # Buildings (Overture)
    overture_geoms = _fetch_overture_buildings(region.bbox)
    if overture_geoms:
        b_source = SOURCE_OVERTURE
        b_features = _to_features(
            overture_geoms,
            category="rooftop",
            min_area=MIN_BUILDING_AREA_M2,
            cap=MAX_BUILDINGS,
            suitability=0.80,
        )
        if not b_features:
            notes.append(
                f"Overture returned {len(overture_geoms)} buildings but none "
                f"met the {MIN_BUILDING_AREA_M2:.0f} m² minimum area threshold."
            )
    else:
        b_source = SOURCE_PHASE1
        b_features = []
        notes.append(
            "Overture buildings unreachable for this region — install duckdb "
            "(`pip install duckdb`) and confirm network access to S3, or "
            "rely on Phase 1 placeholder polygons."
        )

    # Parking (OSM via Overpass)
    osm_geoms = _fetch_osm_parking(region.bbox)
    if osm_geoms:
        p_source = SOURCE_OSM
        p_features = _to_features(
            osm_geoms,
            category="parking",
            min_area=MIN_PARKING_AREA_M2,
            cap=MAX_PARKING,
            suitability=0.70,
        )
        if not p_features:
            notes.append(
                f"OSM returned {len(osm_geoms)} parking shapes but none met "
                f"the {MIN_PARKING_AREA_M2:.0f} m² minimum area threshold."
            )
    else:
        p_source = "OSM unavailable"
        p_features = []
        notes.append(
            "OpenStreetMap parking coverage for this region is sparse or "
            "the Overpass API was unreachable. Parking-lot solar candidates "
            "will not appear on the map."
        )

    # Offshore wind zones are still synthesized for coastal regions until
    # Phase 6 provides real ones. Same as the Phase 1 logic.
    offshore_features: list[PolygonFeature] = []
    if region.is_coastal:
        from .fakes import fake_polygons as _phase1_polys
        ph1 = _phase1_polys(region)
        offshore_features = [
            f for f in ph1.features
            if f.properties.category == "offshore_wind_zone"
        ]

    all_features = b_features + p_features + offshore_features
    coll = PolygonCollection(features=all_features)

    result = FetchResult(
        polygons=coll,
        buildings_source=b_source,
        parking_source=p_source,
        buildings_found=len(b_features),
        parking_found=len(p_features),
        notes=notes,
    )

    # Persist cache (excluding offshore — it's synthesized cheaply)
    _write_cache(region, {
        "polygons": json.loads(coll.model_dump_json()),
        "buildings_source": b_source,
        "parking_source": p_source,
        "buildings_found": len(b_features),
        "parking_found": len(p_features),
        "notes": notes,
    })

    return result


# ============================================================
# Status (for /polygons/status endpoint)
# ============================================================

def source_status() -> dict:
    return {
        "overture_available": _overture_available(),
        "cache": cache_stats(),
        "min_building_area_m2": MIN_BUILDING_AREA_M2,
        "min_parking_area_m2": MIN_PARKING_AREA_M2,
        "max_buildings": MAX_BUILDINGS,
        "max_parking": MAX_PARKING,
    }
