"""
Region lookup.

Phase 1 ships with Whatcom County and Bellingham, WA — the example from
the original project brief. The lookup table is the same shape it will be
in later phases; we just add more entries (or replace this with a Census
TIGER-derived lookup) without changing the function signature.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class RegionRecord:
    state: str
    region_type: Literal["county", "city"]
    name: str
    # GeoJSON-convention bbox: west, south, east, north
    bbox: tuple[float, float, float, float]
    # Leaflet-convention centroid: lat, lon
    centroid: tuple[float, float]
    is_coastal: bool


# Phase 1: hardcoded. Phase 6 (or earlier if convenient) replaces this with
# a TIGER / Census Bureau shapefile lookup. The key is the tuple
# (state, region_type, name_lowercased).
_REGIONS: dict[tuple[str, str, str], RegionRecord] = {
    ("WA", "county", "whatcom county"): RegionRecord(
        state="WA",
        region_type="county",
        name="Whatcom County",
        bbox=(-122.7596, 48.5454, -120.9716, 49.0027),
        centroid=(48.8420, -121.9302),
        is_coastal=True,
    ),
    ("WA", "city", "bellingham"): RegionRecord(
        state="WA",
        region_type="city",
        name="Bellingham",
        bbox=(-122.5400, 48.6900, -122.4100, 48.7900),
        centroid=(48.7519, -122.4787),
        is_coastal=True,
    ),
}


class RegionNotFound(LookupError):
    pass


def lookup(state: str, region_type: str, name: str) -> RegionRecord:
    key = (state.upper(), region_type.lower(), name.strip().lower())
    if key not in _REGIONS:
        raise RegionNotFound(
            f"No record for state={state} type={region_type} name={name!r}. "
            "Phase 1 ships with WA/Whatcom County and WA/Bellingham only."
        )
    return _REGIONS[key]


def list_available() -> list[dict]:
    """Used by the frontend to populate dropdowns."""
    return [
        {"state": r.state, "region_type": r.region_type, "name": r.name}
        for r in _REGIONS.values()
    ]
