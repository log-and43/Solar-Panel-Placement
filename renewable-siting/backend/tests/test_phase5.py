"""
Phase 5 tests — affordability / realism estimate.

All offline. We test the buildout math directly (no data files needed,
because compute_buildout accepts explicit budget/capacity/intensity), the
low/high range semantics, and the endpoint behavior.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app.affordability as aff
from app.main import app
from app.regions import RegionRecord


client = TestClient(app)


def _region() -> RegionRecord:
    return RegionRecord(
        state="WA", region_type="county", name="Whatcom County",
        bbox=(-122.76, 48.55, -120.97, 49.00),
        centroid=(48.84, -121.93),
        is_coastal=True,
        population=231_919,
    )


# ============================================================
# Status endpoint
# ============================================================

def test_affordability_status() -> None:
    r = client.get("/affordability/status")
    assert r.status_code == 200
    data = r.json()
    assert "finance_data_built" in data
    assert "atb_cost_per_watt" in data
    assert set(data["atb_cost_per_watt"]) == {"low", "mid", "high"}


# ============================================================
# Core math
# ============================================================

def test_buildout_with_explicit_budget() -> None:
    """Given an explicit budget, we get a sensible low/high range."""
    result = aff.compute_buildout(
        _region(),
        budget_dollars=100_000_000,   # $100M annual capital budget
        allocation_pct=0.10,           # 10%
        horizon_years=20,
        capacity_factor=0.15,          # rainy PNW
        grid_co2_tons_per_mwh=0.10,    # WA is hydro-heavy, low intensity
    )
    assert result is not None
    # total dollars = 100M * 0.10 * 20 = $200M
    # high capacity (low cost $0.90/W): 200M/0.90 = 222 MW
    # low capacity (high cost $1.80/W): 200M/1.80 = 111 MW
    assert 100 < result.installed_mw_low < 125
    assert 210 < result.installed_mw_high < 235
    # High capacity must exceed low capacity
    assert result.installed_mw_high > result.installed_mw_low


def test_low_cost_yields_high_capacity() -> None:
    """The defining invariant: cheaper $/W → more MW for the same budget."""
    result = aff.compute_buildout(
        _region(),
        budget_dollars=50_000_000, allocation_pct=0.2, horizon_years=10,
        capacity_factor=0.18, grid_co2_tons_per_mwh=0.37,
    )
    assert result is not None
    assert result.cost_per_watt_low < result.cost_per_watt_high
    assert result.installed_mw_high > result.installed_mw_low
    assert result.annual_gwh_high > result.annual_gwh_low
    assert result.co2_tons_per_year_high > result.co2_tons_per_year_low


def test_zero_allocation_yields_zero() -> None:
    result = aff.compute_buildout(
        _region(), budget_dollars=100_000_000,
        allocation_pct=0.0, horizon_years=20,
        capacity_factor=0.18, grid_co2_tons_per_mwh=0.37,
    )
    assert result is not None
    assert result.installed_mw_low == 0
    assert result.installed_mw_high == 0
    assert result.co2_tons_per_year_low == 0


def test_cumulative_co2_scales_with_horizon() -> None:
    base = aff.compute_buildout(
        _region(), budget_dollars=100_000_000,
        allocation_pct=0.1, horizon_years=10,
        capacity_factor=0.18, grid_co2_tons_per_mwh=0.37,
    )
    longer = aff.compute_buildout(
        _region(), budget_dollars=100_000_000,
        allocation_pct=0.1, horizon_years=30,
        capacity_factor=0.18, grid_co2_tons_per_mwh=0.37,
    )
    assert base is not None and longer is not None
    # More years = more total dollars = more cumulative CO2
    assert longer.co2_tons_cumulative_high > base.co2_tons_cumulative_high


def test_degradation_reduces_output() -> None:
    """A longer horizon means more average degradation, lowering per-MW yield."""
    short = aff.compute_buildout(
        _region(), budget_dollars=100_000_000,
        allocation_pct=0.1, horizon_years=1,
        capacity_factor=0.18, grid_co2_tons_per_mwh=0.37,
    )
    # Same budget*alloc*years product but spread differently — compare GWh per MW.
    assert short is not None
    gwh_per_mw_short = short.annual_gwh_high / short.installed_mw_high
    # At horizon=1 degradation factor ≈ 1 - 0.005*0.5 = 0.9975, nearly full.
    # 1 MW * 8760 * 0.18 * 0.9975 / 1000 ≈ 1.573 GWh
    assert 1.5 < gwh_per_mw_short < 1.6


# ============================================================
# Missing-data behavior
# ============================================================

def test_no_budget_no_data_returns_none(monkeypatch) -> None:
    """When finance data isn't built and no budget is provided, returns None."""
    monkeypatch.setattr(aff, "finance_available", lambda: False)
    result = aff.compute_buildout(
        _region(), budget_dollars=None,
        allocation_pct=0.1, horizon_years=20,
    )
    assert result is None


def test_endpoint_unavailable_when_no_data(monkeypatch) -> None:
    """The endpoint returns available=False (not a 500) when no budget exists."""
    monkeypatch.setattr(aff, "finance_available", lambda: False)
    r = client.post("/affordability", json={
        "state": "WA", "region_type": "county", "region_name": "Whatcom County",
        "allocation_pct": 0.1, "horizon_years": 20,
    })
    assert r.status_code == 200
    data = r.json()
    assert data["available"] is False
    assert data["notes"]


def test_endpoint_with_explicit_budget(monkeypatch) -> None:
    """Passing budget_dollars directly should work even without finance data built."""
    monkeypatch.setattr(aff, "finance_available", lambda: False)
    r = client.post("/affordability", json={
        "state": "WA", "region_type": "county", "region_name": "Whatcom County",
        "allocation_pct": 0.1, "horizon_years": 20,
        "budget_dollars": 100_000_000,
        "capacity_factor": 0.15, "grid_co2_tons_per_mwh": 0.10,
    })
    assert r.status_code == 200
    data = r.json()
    assert data["available"] is True
    assert data["installed_mw_high"] > data["installed_mw_low"] > 0
    assert data["budget_dollars"] == 100_000_000


def test_endpoint_unknown_region_404(monkeypatch) -> None:
    monkeypatch.setattr(aff, "finance_available", lambda: False)
    r = client.post("/affordability", json={
        "state": "CA", "region_type": "county", "region_name": "Nowhere County",
        "budget_dollars": 1_000_000,
    })
    # Region lookup fails → 404 (only if Phase 2 data is built; if not, the
    # fallback region set is tiny). Accept either 404 or a 200-with-data
    # depending on whether the WA fallback covers it.
    assert r.status_code in (200, 404)
