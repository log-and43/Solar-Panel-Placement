"""
Phase 4 tests.

All tests run without network. The Overture and Overpass calls are
mocked. Live integration tests can be added later but are not in CI.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.polygons as poly
from app.main import app
from app.regions import RegionRecord


client = TestClient(app)


# ============================================================
# Helpers
# ============================================================

def _wa_region() -> RegionRecord:
    return RegionRecord(
        state="WA", region_type="county", name="Whatcom County",
        bbox=(-122.7596, 48.5454, -120.9716, 49.0027),
        centroid=(48.8420, -121.9302),
        is_coastal=True,
    )


def _square_polygon(cx_lon: float, cy_lat: float, half_deg: float) -> dict:
    """Make a square GeoJSON polygon centered at (cx_lon, cy_lat)."""
    return {
        "type": "Polygon",
        "coordinates": [[
            [cx_lon - half_deg, cy_lat - half_deg],
            [cx_lon + half_deg, cy_lat - half_deg],
            [cx_lon + half_deg, cy_lat + half_deg],
            [cx_lon - half_deg, cy_lat + half_deg],
            [cx_lon - half_deg, cy_lat - half_deg],
        ]],
    }


# ============================================================
# Status endpoint
# ============================================================

def test_polygons_status_endpoint() -> None:
    r = client.get("/polygons/status")
    assert r.status_code == 200
    data = r.json()
    for key in ("overture_available", "cache",
                "min_building_area_m2", "min_parking_area_m2",
                "max_buildings", "max_parking"):
        assert key in data


# ============================================================
# Area computation
# ============================================================

def test_polygon_area_m2_approximate() -> None:
    """A ~100m × 100m square should be ~10,000 m² regardless of latitude."""
    # At lat 48.75°, 0.0005 deg lat ≈ 55.7m → side ~111m → area ~12,300 m²
    g = _square_polygon(-122.48, 48.75, 0.0005)
    area = poly._polygon_area_m2(g)
    assert 8_000 < area < 16_000, f"Got {area}"


# ============================================================
# Filter + cap logic
# ============================================================

def test_to_features_filters_small_polygons() -> None:
    """Polygons below the min area threshold should be dropped."""
    small = _square_polygon(-122.48, 48.75, 0.00005)  # ~1.1m side, ~1m²
    big = _square_polygon(-122.48, 48.75, 0.001)      # ~111m side, ~12000m²
    features = poly._to_features(
        [small, big],
        category="rooftop",
        min_area=250.0,
        cap=10,
        suitability=0.8,
    )
    assert len(features) == 1
    assert features[0].properties.area_m2 > 250


def test_to_features_caps_total() -> None:
    """When more polygons survive filtering than the cap, take the largest."""
    geoms = []
    # 10 polygons of increasing size, all above min_area
    for i in range(1, 11):
        geoms.append(_square_polygon(-122.48, 48.75, 0.001 * i))
    features = poly._to_features(
        geoms,
        category="rooftop",
        min_area=250.0,
        cap=3,
        suitability=0.8,
    )
    assert len(features) == 3
    # Should be the three biggest, sorted descending
    areas = [f.properties.area_m2 for f in features]
    assert areas == sorted(areas, reverse=True)


# ============================================================
# Cache
# ============================================================

def test_cache_roundtrip(tmp_path, monkeypatch) -> None:
    """A successful fetch should be cached, and re-fetch should not re-call sources."""
    monkeypatch.setattr(poly, "POLYGON_CACHE_DIR", tmp_path)
    region = _wa_region()

    call_count = {"overture": 0, "osm": 0}

    def fake_overture(bbox):
        call_count["overture"] += 1
        return [_square_polygon(-122.48, 48.75, 0.001)]  # ~12k m² building

    def fake_osm(bbox):
        call_count["osm"] += 1
        return [_square_polygon(-122.48, 48.75, 0.0015)]  # ~28k m² parking

    monkeypatch.setattr(poly, "_fetch_overture_buildings", fake_overture)
    monkeypatch.setattr(poly, "_fetch_osm_parking", fake_osm)

    r1 = poly.real_polygons(region)
    assert call_count["overture"] == 1
    assert call_count["osm"] == 1
    assert r1.buildings_found == 1
    assert r1.parking_found == 1

    r2 = poly.real_polygons(region)
    # Cache hit — no new calls
    assert call_count["overture"] == 1
    assert call_count["osm"] == 1
    assert r2.buildings_found == 1
    assert r2.parking_found == 1


# ============================================================
# Soft fallback: empty sources
# ============================================================

def test_empty_sources_caveat(tmp_path, monkeypatch) -> None:
    """When both sources return nothing, we get caveats explaining why."""
    monkeypatch.setattr(poly, "POLYGON_CACHE_DIR", tmp_path)
    monkeypatch.setattr(poly, "_fetch_overture_buildings", lambda bbox: [])
    monkeypatch.setattr(poly, "_fetch_osm_parking", lambda bbox: [])

    result = poly.real_polygons(_wa_region())
    assert result.buildings_found == 0
    assert result.parking_found == 0
    assert result.notes  # should explain what happened


# ============================================================
# Pipeline integration via /analyze
# ============================================================

def test_analyze_uses_real_polygons(tmp_path, monkeypatch) -> None:
    """When Phase 4 sources return data, /analyze emits them in the response."""
    monkeypatch.setattr(poly, "POLYGON_CACHE_DIR", tmp_path)
    monkeypatch.setattr(poly, "_fetch_overture_buildings",
                        lambda bbox: [_square_polygon(-122.48, 48.75, 0.001)
                                      for _ in range(5)])
    monkeypatch.setattr(poly, "_fetch_osm_parking",
                        lambda bbox: [_square_polygon(-122.48, 48.75, 0.002)
                                      for _ in range(3)])

    r = client.post("/analyze", json={
        "state": "WA", "region_type": "county", "region_name": "Whatcom County",
    })
    assert r.status_code == 200
    data = r.json()
    categories = [f["properties"]["category"] for f in data["polygons"]["features"]]
    assert "rooftop" in categories
    assert "parking" in categories
    sources = {f["properties"]["source"] for f in data["polygons"]["features"]
               if f["properties"]["category"] in ("rooftop", "parking")}
    assert any("Phase 4" in s for s in sources)


def test_analyze_falls_back_when_phase4_returns_nothing(tmp_path, monkeypatch) -> None:
    """When neither Overture nor OSM has anything, we still ship a usable response."""
    monkeypatch.setattr(poly, "POLYGON_CACHE_DIR", tmp_path)
    monkeypatch.setattr(poly, "_fetch_overture_buildings", lambda bbox: [])
    monkeypatch.setattr(poly, "_fetch_osm_parking", lambda bbox: [])

    r = client.post("/analyze", json={
        "state": "WA", "region_type": "county", "region_name": "Whatcom County",
    })
    assert r.status_code == 200
    data = r.json()
    # Should have fallen back to Phase 1 fakes — non-empty.
    assert len(data["polygons"]["features"]) > 0
    # Caveats should explain.
    assert any("placeholder" in c.lower() or "phase 1" in c.lower()
               for c in data["caveats"])


# ============================================================
# Overpass response parsing
# ============================================================

def test_overpass_to_geojson_way() -> None:
    """A single way with closed geometry should become a Polygon."""
    payload = {"elements": [{
        "type": "way",
        "id": 1,
        "geometry": [
            {"lat": 48.0, "lon": -122.0},
            {"lat": 48.001, "lon": -122.0},
            {"lat": 48.001, "lon": -122.001},
            {"lat": 48.0, "lon": -122.001},
            {"lat": 48.0, "lon": -122.0},
        ],
    }]}
    geoms = poly._overpass_to_geojson(payload)
    assert len(geoms) == 1
    assert geoms[0]["type"] == "Polygon"
    # First and last coords should match (closed ring)
    coords = geoms[0]["coordinates"][0]
    assert coords[0] == coords[-1]


def test_overpass_to_geojson_unclosed_way_gets_closed() -> None:
    """A way whose last point != first should still produce a valid polygon."""
    payload = {"elements": [{
        "type": "way",
        "id": 1,
        "geometry": [
            {"lat": 48.0, "lon": -122.0},
            {"lat": 48.001, "lon": -122.0},
            {"lat": 48.001, "lon": -122.001},
            {"lat": 48.0, "lon": -122.001},
        ],
    }]}
    geoms = poly._overpass_to_geojson(payload)
    assert len(geoms) == 1
    coords = geoms[0]["coordinates"][0]
    assert coords[0] == coords[-1], "Polygon ring should be auto-closed"


def test_overpass_to_geojson_skips_short_geometry() -> None:
    """A 'way' with only 2 points isn't a polygon. Skip it."""
    payload = {"elements": [{
        "type": "way",
        "id": 1,
        "geometry": [
            {"lat": 48.0, "lon": -122.0},
            {"lat": 48.001, "lon": -122.0},
        ],
    }]}
    geoms = poly._overpass_to_geojson(payload)
    assert geoms == []
