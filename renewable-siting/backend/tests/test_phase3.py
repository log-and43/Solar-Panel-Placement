"""
Phase 3 tests.

These run without network access by default. The PVWatts integration is
tested by:
  - Asserting fallback behavior when no API key is set
  - Mocking the urlopen call to simulate NREL responses
  - Verifying cache hits/misses
  - Testing the polygon enrichment step end-to-end via /analyze

One optional test will hit the live NREL API if PVWATTS_LIVE_TEST=1 is set
in the environment. CI / normal test runs should NOT set this.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import app.pvwatts as pvw
from app.main import app


client = TestClient(app)


# ============================================================
# Always-on: behavior without an API key
# ============================================================

def test_pvwatts_status_endpoint() -> None:
    r = client.get("/pvwatts/status")
    assert r.status_code == 200
    data = r.json()
    assert "api_key_configured" in data
    assert "cache" in data
    assert "entries" in data["cache"]


def test_analyze_works_without_api_key(monkeypatch) -> None:
    """The whole pipeline must still produce a response when no key is set."""
    monkeypatch.delenv("PVWATTS_API_KEY", raising=False)
    monkeypatch.delenv("NREL_API_KEY", raising=False)
    monkeypatch.delenv("ROCKIES_API_KEY", raising=False)
    monkeypatch.setattr(pvw, "ENV_PATH", Path("/nonexistent/.env"))
    r = client.post("/analyze", json={
        "state": "WA", "region_type": "county", "region_name": "Whatcom County",
    })
    assert r.status_code == 200
    data = r.json()
    # At least one rooftop/parking polygon should have the fallback generation_source.
    gen_sources = {
        f["properties"].get("generation_source")
        for f in data["polygons"]["features"]
        if f["properties"]["category"] in ("rooftop", "parking")
    }
    assert pvw.SOURCE_FALLBACK in gen_sources, \
        f"Expected fallback generation_source, got {gen_sources}"
    # Fallback caveat should be present.
    assert any("PVWATTS_API_KEY" in c for c in data["caveats"])


def test_fallback_formula_matches_phase1() -> None:
    """Backward compat: with no key, est_annual_mwh should still equal area * 0.15 / 1000."""
    mwh, source = pvw.pv_annual_mwh(
        lat=48.75, lon=-122.48, area_m2=2000.0, category="rooftop",
    )
    assert source == pvw.SOURCE_FALLBACK
    assert abs(mwh - 0.3) < 1e-6  # 2000 * 0.15 / 1000 == 0.3


# ============================================================
# Multi-env-var support (post-Codex Phase 3 adoption)
# ============================================================

@pytest.mark.parametrize("env_name", ["PVWATTS_API_KEY", "NREL_API_KEY", "ROCKIES_API_KEY"])
def test_api_key_loaded_from_any_known_env_var(monkeypatch, env_name) -> None:
    """Either canonical name or any of the NREL ecosystem aliases should work."""
    monkeypatch.delenv("PVWATTS_API_KEY", raising=False)
    monkeypatch.delenv("NREL_API_KEY", raising=False)
    monkeypatch.delenv("ROCKIES_API_KEY", raising=False)
    monkeypatch.setattr(pvw, "ENV_PATH", Path("/nonexistent/.env"))
    monkeypatch.setenv(env_name, "test_value_42")
    assert pvw.load_api_key() == "test_value_42"
    assert pvw.has_api_key()


def test_canonical_name_wins_over_aliases(monkeypatch) -> None:
    """When multiple are set, PVWATTS_API_KEY should win — it's the project canonical."""
    monkeypatch.setattr(pvw, "ENV_PATH", Path("/nonexistent/.env"))
    monkeypatch.setenv("PVWATTS_API_KEY", "canonical")
    monkeypatch.setenv("NREL_API_KEY", "alias_nrel")
    monkeypatch.setenv("ROCKIES_API_KEY", "alias_rockies")
    assert pvw.load_api_key() == "canonical"


def test_api_key_loaded_from_dotenv_with_alias(monkeypatch, tmp_path) -> None:
    """A .env file using an alias name should still be picked up."""
    monkeypatch.delenv("PVWATTS_API_KEY", raising=False)
    monkeypatch.delenv("NREL_API_KEY", raising=False)
    monkeypatch.delenv("ROCKIES_API_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("# A comment\nNREL_API_KEY=from_dotenv\n", encoding="utf-8")
    monkeypatch.setattr(pvw, "ENV_PATH", env_file)
    assert pvw.load_api_key() == "from_dotenv"


# ============================================================
# Cache key
# ============================================================

def test_cache_key_rounding() -> None:
    """Two nearby polygons of similar size should produce the same cache key."""
    k1 = pvw._cache_key(48.7519, -122.4787, 10.05, 1, 48.0, 180.0, 14.0)
    k2 = pvw._cache_key(48.7520, -122.4788, 10.12, 1, 48.0, 180.0, 14.0)
    assert k1 == k2, f"Expected same key for nearby polygons:\n  {k1}\n  {k2}"


def test_cache_key_separates_distinct_systems() -> None:
    """A 2 kW system in Bellingham must not share a key with a 200 kW system."""
    k1 = pvw._cache_key(48.75, -122.48, 2.0, 1, 48.0, 180.0, 14.0)
    k2 = pvw._cache_key(48.75, -122.48, 200.0, 1, 48.0, 180.0, 14.0)
    assert k1 != k2


def test_cache_key_separates_distant_locations() -> None:
    """Bellingham, WA and Bellingham, MA must hash differently."""
    k_wa = pvw._cache_key(48.75, -122.48, 10.0, 1, 48.0, 180.0, 14.0)
    k_ma = pvw._cache_key(42.10, -71.02, 10.0, 1, 42.0, 180.0, 14.0)
    assert k_wa != k_ma


# ============================================================
# Cache persistence across in-process calls
# ============================================================

def test_cache_writes_and_reads(tmp_path, monkeypatch) -> None:
    """A successful PVWatts call should be cached and subsequent calls reused."""
    fake_key = "TEST_KEY_NOT_REAL_xxxxxxxxxxxxxxxxxxxxxxx"
    monkeypatch.setenv("PVWATTS_API_KEY", fake_key)

    # Redirect cache to a fresh tmp file by swapping the module-level cache.
    fresh_cache = pvw._Cache(tmp_path / "pv_cache.json")
    monkeypatch.setattr(pvw, "_cache", fresh_cache)

    call_count = {"n": 0}
    def fake_call(api_key, **kwargs):
        call_count["n"] += 1
        return 12345.0  # kWh
    monkeypatch.setattr(pvw, "_call_pvwatts", fake_call)

    # First call: hits the (fake) API
    mwh1, src1 = pvw.pv_annual_mwh(lat=48.75, lon=-122.48, area_m2=2000.0, category="rooftop")
    # Second call with same params: cache hit
    mwh2, src2 = pvw.pv_annual_mwh(lat=48.75, lon=-122.48, area_m2=2000.0, category="rooftop")

    assert call_count["n"] == 1, "Cache should have prevented second API call"
    assert mwh1 == mwh2 == 12345.0 / 1000.0
    assert src1 == src2 == pvw.SOURCE_REAL

    # Verify the cache file was actually written
    assert (tmp_path / "pv_cache.json").exists()
    data = json.loads((tmp_path / "pv_cache.json").read_text())
    assert len(data) == 1


def test_pvwatts_network_failure_falls_back(tmp_path, monkeypatch) -> None:
    """A PVWattsError mid-run must fall back to the approximation, not 500."""
    monkeypatch.setenv("PVWATTS_API_KEY", "fake")
    monkeypatch.setattr(pvw, "_cache", pvw._Cache(tmp_path / "pv_cache.json"))

    def boom(api_key, **kwargs):
        raise pvw.PVWattsError("simulated network blip")
    monkeypatch.setattr(pvw, "_call_pvwatts", boom)

    mwh, src = pvw.pv_annual_mwh(lat=48.75, lon=-122.48, area_m2=2000.0, category="rooftop")
    assert src == pvw.SOURCE_FALLBACK
    assert mwh == pytest.approx(2000.0 * 0.15 / 1000.0)


# ============================================================
# Polygon enrichment via /analyze, with mocked PVWatts
# ============================================================

def test_analyze_uses_pvwatts_when_key_set(tmp_path, monkeypatch) -> None:
    """When a key is set, rooftop/parking polygons should get the REAL source tag."""
    monkeypatch.setenv("PVWATTS_API_KEY", "fake")
    monkeypatch.setattr(pvw, "_cache", pvw._Cache(tmp_path / "pv_cache.json"))

    def fake_call(api_key, **kwargs):
        # Return a per-call kWh value that varies with kW so we can verify
        # that PVWatts (not the fallback) shaped the answer.
        return kwargs["system_kw"] * 1500.0  # ~1500 kWh/kW/yr, typical-ish
    monkeypatch.setattr(pvw, "_call_pvwatts", fake_call)

    r = client.post("/analyze", json={
        "state": "WA", "region_type": "county", "region_name": "Whatcom County",
    })
    assert r.status_code == 200
    data = r.json()

    rooftop_or_parking = [
        f for f in data["polygons"]["features"]
        if f["properties"]["category"] in ("rooftop", "parking")
    ]
    assert rooftop_or_parking, "Expected rooftop/parking polygons in the response"
    for f in rooftop_or_parking:
        assert f["properties"]["generation_source"] == pvw.SOURCE_REAL, \
            f"Expected real PVWatts generation_source, got {f['properties'].get('generation_source')}"
        # Values from fake_call: system_kw * 1500. Both should be > 0.
        assert f["properties"]["est_annual_mwh"] > 0

    # Offshore wind zone polygons should NOT have been touched by PVWatts
    offshore = [f for f in data["polygons"]["features"]
                if f["properties"]["category"] == "offshore_wind_zone"]
    if offshore:
        # Whatever generation_source they have, it shouldn't be PVWatts real.
        for f in offshore:
            assert f["properties"].get("generation_source") != pvw.SOURCE_REAL


# ============================================================
# Optional live test — only when PVWATTS_LIVE_TEST=1
# ============================================================

@pytest.mark.skipif(
    os.environ.get("PVWATTS_LIVE_TEST") != "1" or not pvw.has_api_key(),
    reason="Set PVWATTS_LIVE_TEST=1 and configure PVWATTS_API_KEY to run."
)
def test_live_pvwatts_call() -> None:
    """One real call against NREL. Skipped unless PVWATTS_LIVE_TEST=1."""
    # Bellingham, WA, ~5 kW system.
    annual_kwh = pvw._call_pvwatts(
        pvw.load_api_key(),
        system_kw=5.0, lat=48.75, lon=-122.48,
        module_type=1, array_type=1, tilt=48.0, azimuth=180.0, losses=14.0,
    )
    # A 5 kW system in Bellingham (rainy PNW) should produce maybe 4000–6500 kWh/yr.
    # Bounds are loose on purpose.
    assert 2_000 < annual_kwh < 10_000, f"Unexpected PVWatts annual kWh: {annual_kwh}"
