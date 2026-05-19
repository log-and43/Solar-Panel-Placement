"""
Phase 2 tests.

These tests fall into two groups:

1. Tests that run regardless of whether Phase 2 data has been built. They
   check that the app still works in Phase-1 fallback mode and that the
   search endpoint at least responds.

2. Tests that skip if Parquet files aren't present. They check the SHAPE
   of the built data (columns, value ranges) and that real consumption
   numbers come back when data is built.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.data_store import data_available, DATA_DIR
from app.main import app


client = TestClient(app)


# ============================================================
# Group 1: always-on tests
# ============================================================

def test_states_endpoint_responds() -> None:
    r = client.get("/states")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert "abbr" in data[0] and "name" in data[0]


def test_search_county_empty_query() -> None:
    r = client.get("/search", params={"region_type": "county", "state": "WA"})
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    # Whatcom County should appear in either Phase 1 fallback or Phase 2 data.
    assert any("Whatcom" in row["name"] for row in data), \
        f"Whatcom County not in WA search results: {data}"


def test_search_city_prefix() -> None:
    r = client.get("/search", params={"region_type": "city", "state": "WA", "q": "Belling"})
    assert r.status_code == 200
    data = r.json()
    assert any("Bellingham" in row["name"] for row in data)


def test_analyze_still_works_in_fallback() -> None:
    """The /analyze endpoint must keep working even without Phase 2 data."""
    r = client.post("/analyze", json={
        "state": "WA", "region_type": "county", "region_name": "Whatcom County",
    })
    assert r.status_code == 200


# ============================================================
# Group 2: tests that need the build script to have run
# ============================================================

needs_data = pytest.mark.skipif(
    not data_available(),
    reason="Phase 2 data files not built. Run: python scripts/build_data.py"
)


@needs_data
def test_states_data_columns() -> None:
    """The built states.parquet has the columns the loader expects."""
    import pandas as pd
    df = pd.read_parquet(DATA_DIR / "states.parquet")
    required = {
        "state_abbr", "state_name", "population",
        "mix_coal", "mix_natural_gas", "mix_nuclear",
        "mix_hydro", "mix_wind", "mix_solar", "mix_other",
        "electricity_mwh_per_year", "fossil_mwh_per_year",
    }
    missing = required - set(df.columns)
    assert not missing, f"states.parquet missing columns: {missing}"


@needs_data
def test_states_mix_sums_to_one() -> None:
    """eGRID mix percentages plus the 'other' remainder should sum to ~1.0 for every state."""
    import pandas as pd
    df = pd.read_parquet(DATA_DIR / "states.parquet")
    mix_cols = [c for c in df.columns if c.startswith("mix_")]
    totals = df[mix_cols].sum(axis=1)
    bad = df[(totals < 0.95) | (totals > 1.05)]
    assert bad.empty, f"States with mix not summing to ~1.0:\n{bad[['state_abbr'] + mix_cols + ['_'.join(['_'])]] if False else bad['state_abbr'].tolist()}"


@needs_data
def test_states_have_continental_coverage() -> None:
    """Should have ~48 continental states (50 minus AK, HI; possibly minus DC)."""
    import pandas as pd
    df = pd.read_parquet(DATA_DIR / "states.parquet")
    assert 45 <= len(df) <= 49, f"Unexpected state count: {len(df)}"
    abbrs = set(df["state_abbr"])
    # Sanity: known states
    for state in ("WA", "CA", "TX", "NY", "FL", "WV", "IA", "ND"):
        assert state in abbrs, f"Missing expected state {state}"


@needs_data
def test_counties_have_real_coverage() -> None:
    import pandas as pd
    df = pd.read_parquet(DATA_DIR / "counties.parquet")
    # ~3,100 counties in continental US, minus some not matched. Allow wide range.
    assert 2_500 < len(df) < 3_300, f"Unexpected county count: {len(df)}"


@needs_data
def test_whatcom_county_real_numbers() -> None:
    """The flagship region from the original project brief should produce
    plausible real numbers, not the Phase-1 hardcoded values."""
    r = client.post("/analyze", json={
        "state": "WA", "region_type": "county", "region_name": "Whatcom County",
    })
    assert r.status_code == 200
    data = r.json()
    c = data["consumption"]
    assert "EIA SEDS" in c["source"] or "eGRID" in c["source"], \
        f"Expected real-data source tag, got: {c['source']}"
    # Whatcom County has ~230k people; statewide is ~7.8M. WA used ~90 TWh in 2022.
    # 230/7800 × 90 ≈ 2.6 TWh. We test for a broad plausible range.
    assert 1_000_000 < c["total_mwh_per_year"] < 5_000_000, \
        f"Whatcom MWh outside plausible range: {c['total_mwh_per_year']}"
    # WA grid is hydro-dominated, so fossil share should be small.
    fossil_share = c["fossil_mwh_per_year"] / c["total_mwh_per_year"]
    assert 0.01 < fossil_share < 0.25, \
        f"WA fossil share outside expected range: {fossil_share}"
    # WA hydro share should be the dominant slice.
    assert c["mix"]["hydro"] > 0.4, \
        f"WA hydro fraction unexpectedly low: {c['mix']['hydro']}"


@needs_data
def test_west_virginia_is_coal_heavy() -> None:
    """WV should jump out as the canonical coal-heavy grid — sanity check that
    eGRID was actually read correctly, not e.g. that all states are hydro."""
    import pandas as pd
    df = pd.read_parquet(DATA_DIR / "states.parquet")
    wv = df[df["state_abbr"] == "WV"]
    assert not wv.empty
    assert wv["mix_coal"].iloc[0] > 0.5, \
        f"WV coal fraction unexpectedly low: {wv['mix_coal'].iloc[0]}"


@needs_data
def test_search_returns_top_cities_by_population() -> None:
    """An empty-query city search in CA should put Los Angeles near the top."""
    r = client.get("/search", params={"region_type": "city", "state": "CA", "limit": 5})
    assert r.status_code == 200
    data = r.json()
    names = [row["name"] for row in data]
    assert any("Los Angeles" in n for n in names), f"LA not in top CA cities: {names}"


@needs_data
def test_search_cross_state() -> None:
    """Searching without specifying state should still work."""
    r = client.get("/search", params={"region_type": "city", "q": "Springfield", "limit": 10})
    assert r.status_code == 200
    data = r.json()
    # Springfield is a notoriously ambiguous name; we should get multiple states.
    states = {row["state"] for row in data}
    assert len(states) >= 2, f"Cross-state search returned only: {states}"
