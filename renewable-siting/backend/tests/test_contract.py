"""
Contract test.

This test exists to prevent the API shape from drifting accidentally as
future phases land. If a phase legitimately needs to change the contract,
update docs/CONTRACT.md, then update this test, then change the code —
in that order.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health() -> None:
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["phase"] in (1, 2)
    assert isinstance(data["data_built"], bool)


def test_regions_list() -> None:
    r = client.get("/regions")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) >= 2
    # Known seeded regions
    names = {(d["state"], d["region_type"], d["name"]) for d in data}
    assert ("WA", "county", "Whatcom County") in names
    assert ("WA", "city", "Bellingham") in names


def test_analyze_unknown_region_returns_404() -> None:
    r = client.post("/analyze", json={
        "state": "CA", "region_type": "county", "region_name": "Nowhere County",
    })
    assert r.status_code == 404


def test_analyze_whatcom_response_shape() -> None:
    r = client.post("/analyze", json={
        "state": "WA", "region_type": "county", "region_name": "Whatcom County",
    })
    assert r.status_code == 200, r.text
    data = r.json()

    # Top-level keys
    for key in ("region", "consumption", "polygons", "recommendation", "economics", "caveats"):
        assert key in data, f"missing top-level key: {key}"

    # Region
    region = data["region"]
    assert region["name"] == "Whatcom County"
    assert region["type"] == "county"
    assert region["state"] == "WA"
    assert len(region["bbox"]) == 4
    assert len(region["centroid"]) == 2
    assert isinstance(region["is_coastal"], bool)

    # Consumption
    c = data["consumption"]
    assert c["total_mwh_per_year"] > 0
    assert 0 <= c["fossil_mwh_per_year"] <= c["total_mwh_per_year"]
    mix = c["mix"]
    total_share = sum(mix[k] for k in mix)
    assert 0.98 <= total_share <= 1.02, f"mix should sum ~1.0, got {total_share}"

    # Polygons
    polys = data["polygons"]
    assert polys["type"] == "FeatureCollection"
    assert len(polys["features"]) >= 1
    for feat in polys["features"]:
        assert feat["type"] == "Feature"
        assert feat["geometry"]["type"] == "Polygon"
        props = feat["properties"]
        assert props["category"] in (
            "rooftop", "parking", "offshore_wind_zone", "cv_detected_parking",
        )
        assert props["area_m2"] > 0
        assert props["est_annual_mwh"] >= 0
        assert 0.0 <= props["suitability_score"] <= 1.0

    # Recommendation
    rec = data["recommendation"]
    assert rec["primary"] in ("solar", "wind", "offshore_wind", "mixed", "insufficient")
    assert rec["covered_mwh_per_year"] >= 0
    assert rec["gap_mwh_per_year"] >= 0

    # Economics
    econ = data["economics"]
    assert econ["install_cost_usd"] >= 0
    assert econ["annual_savings_usd"] >= 0
    assert econ["co2_avoided_tons_per_year"] >= 0
    # payback_years can be None if savings == 0

    # Caveats — must always include at least one placeholder/limitation note
    assert len(data["caveats"]) > 0, "response must always include caveats"


def test_bellingham_is_smaller_than_whatcom() -> None:
    """City should have lower consumption than its containing county."""
    rw = client.post("/analyze", json={
        "state": "WA", "region_type": "county", "region_name": "Whatcom County",
    }).json()
    rb = client.post("/analyze", json={
        "state": "WA", "region_type": "city", "region_name": "Bellingham",
    }).json()
    assert rb["consumption"]["total_mwh_per_year"] < rw["consumption"]["total_mwh_per_year"]
