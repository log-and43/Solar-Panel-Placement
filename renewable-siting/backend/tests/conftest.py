"""
Test-suite-wide configuration.

The most important thing this file does: disable network access from
tests by default. The /analyze pipeline (after Phase 4) tries to query
Overture Maps via S3 and OSM via Overpass on every call. Without this
default, a test that calls /analyze hangs or burns 30+ seconds per
region while pytest sits idle.

Individual tests (e.g. in test_phase4.py) override these mocks with
their own fixtures when they want to simulate specific scenarios.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _disable_phase4_network(monkeypatch):
    """
    Make Overture and Overpass return [] by default.

    Tests that want different behavior can call monkeypatch.setattr
    again — pytest applies fixtures inner-out, so the test's
    monkeypatch wins.

    Returning [] triggers the pipeline's soft-fallback to Phase 1
    polygons, which is fine for shape-of-response tests.
    """
    import app.polygons as poly
    monkeypatch.setattr(poly, "_fetch_overture_buildings", lambda bbox: [])
    monkeypatch.setattr(poly, "_fetch_osm_parking", lambda bbox: [])
    yield


@pytest.fixture(autouse=True)
def _disable_pvwatts_network(monkeypatch, tmp_path):
    """
    Redirect the PVWatts on-disk cache to a tmp directory per-test and
    block real PVWatts API calls. Tests that explicitly want real-ish
    PVWatts behavior provide their own mock for `_call_pvwatts`.

    Tests that explicitly want to test the no-key fallback path can
    delete the env vars and they'll naturally see SOURCE_FALLBACK
    without hitting the network anyway.
    """
    import os
    import app.pvwatts as pvw

    # Per-test isolated cache file so tests don't pollute each other.
    fresh_cache = pvw._Cache(tmp_path / "pv_cache.json")
    monkeypatch.setattr(pvw, "_cache", fresh_cache)

    # If the developer explicitly opted into live PVWatts testing, do NOT
    # block the network — that's the whole point of the live test.
    if os.environ.get("PVWATTS_LIVE_TEST") == "1":
        yield
        return

    # Otherwise block any unmocked PVWatts call. If a test wants to exercise
    # the success path, it overrides this with its own _call_pvwatts mock.
    def _no_network(*args, **kwargs):
        raise pvw.PVWattsError("Network blocked in tests; mock _call_pvwatts to exercise success path.")
    monkeypatch.setattr(pvw, "_call_pvwatts", _no_network)
    yield
