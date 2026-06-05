"""Phase 7 tests — real economics."""

from __future__ import annotations

from app.economics import (
    grid_intensity_tons_per_mwh,
    real_economics,
    EIA_COMMERCIAL_RATE_USD_PER_KWH,
)
from app.schemas import (
    Consumption, GenerationMix, PolygonCollection, PolygonFeature, PolygonProperties,
)


def _mix(**kw) -> GenerationMix:
    base = dict(coal=0, natural_gas=0, nuclear=0, hydro=0, wind=0, solar=0, other=0)
    base.update(kw)
    return GenerationMix(**base)


def _consumption(mix: GenerationMix) -> Consumption:
    return Consumption(total_mwh_per_year=1_000_000, fossil_mwh_per_year=100_000,
                       mix=mix, source="test")


def _polys() -> PolygonCollection:
    feats = [
        PolygonFeature(geometry={"type": "Polygon", "coordinates": [[[0, 0]]]},
                       properties=PolygonProperties(
                           category="rooftop", area_m2=10_000, est_annual_mwh=1500.0,
                           suitability_score=0.8, source="test")),
        PolygonFeature(geometry={"type": "Polygon", "coordinates": [[[0, 0]]]},
                       properties=PolygonProperties(
                           category="parking", area_m2=5_000, est_annual_mwh=700.0,
                           suitability_score=0.7, source="test")),
    ]
    return PolygonCollection(features=feats)


def test_grid_intensity_coal_vs_clean() -> None:
    coal = grid_intensity_tons_per_mwh(_mix(coal=1.0))
    hydro = grid_intensity_tons_per_mwh(_mix(hydro=1.0))
    assert coal > 0.9          # ~1.02
    assert hydro == 0.0
    assert coal > hydro


def test_grid_intensity_blends() -> None:
    half = grid_intensity_tons_per_mwh(_mix(coal=0.5, hydro=0.5))
    assert abs(half - 0.51) < 0.01  # 0.5 * 1.02


def test_real_economics_basic() -> None:
    econ, src = real_economics(_consumption(_mix(coal=0.5, natural_gas=0.5)),
                               _polys(), "OH")
    # Installed watts: 10000*0.55*200 + 5000*0.65*200 = 1.1M + 0.65M = 1.75M W
    # Cost at $1.30/W = $2.275M
    assert 2_000_000 < econ.install_cost_usd < 2_500_000
    # Generation 2200 MWh; OH rate 0.107 → savings = 2.2M kWh * 0.107 ≈ $235k
    assert econ.annual_savings_usd > 0
    assert econ.payback_years is not None and econ.payback_years > 0
    # CO2: 2200 MWh * (0.5*1.02 + 0.5*0.43=0.725) ≈ 1595 t
    assert 1400 < econ.co2_avoided_tons_per_year < 1800
    assert "ATB" in src["install_cost"]
    assert "eGRID" in src["co2_avoided"]


def test_unknown_state_uses_national_rate() -> None:
    econ, src = real_economics(_consumption(_mix(coal=1.0)), _polys(), "ZZ")
    assert "national average" in src["annual_savings"]


def test_all_states_have_rates() -> None:
    # Sanity: the rate table covers the 48 continental states.
    assert len(EIA_COMMERCIAL_RATE_USD_PER_KWH) >= 48
    for st in ("WA", "WV", "CA", "TX", "FL"):
        assert st in EIA_COMMERCIAL_RATE_USD_PER_KWH
