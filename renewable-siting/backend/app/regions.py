"""
Region lookup.

Phase 2: reads from the Parquet files produced by scripts/build_data.py.

If those files don't exist yet (fresh clone, build not run), falls back to
the Phase-1 hardcoded entries for Whatcom County and Bellingham so the app
still demos.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .data_store import counties_df, data_available, places_df, states_df


@dataclass(frozen=True)
class RegionRecord:
    state: str
    region_type: Literal["county", "city"]
    name: str
    bbox: tuple[float, float, float, float]   # west, south, east, north
    centroid: tuple[float, float]              # lat, lon
    is_coastal: bool
    # New in Phase 2 (None if Phase-1 fallback active for this region):
    population: int | None = None
    electricity_mwh_per_year: float | None = None
    fossil_mwh_per_year: float | None = None


# ============================================================
# Phase 1 fallback — kept so the app demos without the build step
# ============================================================
_PHASE1_FALLBACK: dict[tuple[str, str, str], RegionRecord] = {
    ("WA", "county", "whatcom county"): RegionRecord(
        state="WA", region_type="county", name="Whatcom County",
        bbox=(-122.7596, 48.5454, -120.9716, 49.0027),
        centroid=(48.8420, -121.9302),
        is_coastal=True,
    ),
    ("WA", "city", "bellingham"): RegionRecord(
        state="WA", region_type="city", name="Bellingham",
        bbox=(-122.5400, 48.6900, -122.4100, 48.7900),
        centroid=(48.7519, -122.4787),
        is_coastal=True,
    ),
}


# Coastal-state heuristic. A county/city in one of these states *may* be
# coastal; we pessimistically treat all of them as coastal in Phase 2.
# Phase 6 replaces this with a real coastline-distance check.
COASTAL_STATES: frozenset[str] = frozenset({
    "ME", "NH", "MA", "RI", "CT", "NY", "NJ", "DE", "MD", "VA",
    "NC", "SC", "GA", "FL", "AL", "MS", "LA", "TX", "CA", "OR", "WA",
})


class RegionNotFound(LookupError):
    pass


def _nan_to_none(v):
    try:
        return None if v != v else v  # NaN-check via inequality with self
    except Exception:
        return v


def _county_row_to_record(row) -> RegionRecord:
    pop = _nan_to_none(row["population"])
    mwh = _nan_to_none(row["electricity_mwh_per_year"])
    fossil = _nan_to_none(row["fossil_mwh_per_year"])
    return RegionRecord(
        state=row["state_abbr"],
        region_type="county",
        name=row["county_name"],
        bbox=(float(row["bbox_west"]), float(row["bbox_south"]),
              float(row["bbox_east"]), float(row["bbox_north"])),
        centroid=(float(row["centroid_lat"]), float(row["centroid_lon"])),
        is_coastal=row["state_abbr"] in COASTAL_STATES,
        population=int(pop) if pop is not None else None,
        electricity_mwh_per_year=float(mwh) if mwh is not None else None,
        fossil_mwh_per_year=float(fossil) if fossil is not None else None,
    )


def _place_row_to_record(row) -> RegionRecord:
    pop = _nan_to_none(row["population"])
    mwh = _nan_to_none(row["electricity_mwh_per_year"])
    fossil = _nan_to_none(row["fossil_mwh_per_year"])
    return RegionRecord(
        state=row["state_abbr"],
        region_type="city",
        name=row["place_name"],
        bbox=(float(row["bbox_west"]), float(row["bbox_south"]),
              float(row["bbox_east"]), float(row["bbox_north"])),
        centroid=(float(row["centroid_lat"]), float(row["centroid_lon"])),
        is_coastal=row["state_abbr"] in COASTAL_STATES,
        population=int(pop) if pop is not None else None,
        electricity_mwh_per_year=float(mwh) if mwh is not None else None,
        fossil_mwh_per_year=float(fossil) if fossil is not None else None,
    )


def lookup(state: str, region_type: str, name: str) -> RegionRecord:
    state_u = state.upper()
    rtype = region_type.lower()
    name_clean = name.strip()

    if not data_available():
        key = (state_u, rtype, name_clean.lower())
        if key not in _PHASE1_FALLBACK:
            raise RegionNotFound(
                f"No record for state={state} type={region_type} name={name!r}. "
                "Phase 2 data files are not built yet — only WA/Whatcom County "
                "and WA/Bellingham are available. To enable full coverage, run: "
                "cd backend && python scripts/build_data.py"
            )
        return _PHASE1_FALLBACK[key]

    if rtype == "county":
        df = counties_df()
        candidates = df[df["state_abbr"] == state_u]
        hit = candidates[candidates["county_name"].str.lower() == name_clean.lower()]
        if hit.empty:
            # Try with/without "County" suffix
            n_lower = name_clean.lower().removesuffix(" county").strip()
            hit = candidates[
                candidates["county_name"].str.lower()
                .str.removesuffix(" county").str.strip() == n_lower
            ]
        if hit.empty:
            raise RegionNotFound(
                f"County {name!r} not found in {state_u}. "
                f"Try the full name including 'County' suffix."
            )
        return _county_row_to_record(hit.iloc[0])

    elif rtype == "city":
        df = places_df()
        candidates = df[df["state_abbr"] == state_u]
        hit = candidates[candidates["place_name"].str.lower() == name_clean.lower()]
        if hit.empty:
            raise RegionNotFound(
                f"City {name!r} not found in {state_u}. "
                f"Note: only cities with population ≥ build-script cutoff are included."
            )
        return _place_row_to_record(hit.iloc[0])

    else:
        raise RegionNotFound(f"Unknown region_type: {region_type}")


def list_states() -> list[dict]:
    """All states with at least one entry. Used by the picker."""
    if not data_available():
        return [{"abbr": "WA", "name": "Washington"}]
    df = states_df()
    return [
        {"abbr": row["state_abbr"], "name": row["state_name"]}
        for _, row in df.sort_values("state_name").iterrows()
    ]


def search(state: str | None, region_type: str, query: str, limit: int = 25) -> list[dict]:
    """Search for regions by substring. Powers the frontend typeahead."""
    query_lower = query.strip().lower()
    rtype = region_type.lower()

    if not data_available():
        results = []
        for rec in _PHASE1_FALLBACK.values():
            if rec.region_type != rtype:
                continue
            if state and rec.state != state.upper():
                continue
            if query_lower and query_lower not in rec.name.lower():
                continue
            results.append({
                "state": rec.state,
                "region_type": rec.region_type,
                "name": rec.name,
                "population": rec.population,
            })
        return results[:limit]

    if rtype == "county":
        df = counties_df()
        name_col = "county_name"
    elif rtype == "city":
        df = places_df()
        name_col = "place_name"
    else:
        return []

    if state:
        df = df[df["state_abbr"] == state.upper()]

    if query_lower:
        df = df[df[name_col].str.lower().str.contains(query_lower, na=False, regex=False)]

    df = df.copy()
    df["_prefix"] = df[name_col].str.lower().str.startswith(query_lower).astype(int)
    df = df.sort_values(["_prefix", "population"], ascending=[False, False])
    df = df.head(limit)

    return [
        {
            "state": row["state_abbr"],
            "region_type": rtype,
            "name": row[name_col],
            "population": int(row["population"]) if row["population"] == row["population"] else None,
        }
        for _, row in df.iterrows()
    ]


# Back-compat alias for Phase 1 test
def list_available() -> list[dict]:
    """Phase-1 compatibility: lists fallback regions when data isn't built."""
    if not data_available():
        return [
            {"state": r.state, "region_type": r.region_type, "name": r.name}
            for r in _PHASE1_FALLBACK.values()
        ]
    # When Phase 2 data is available, this returns just the seed entries
    # (frontend uses /search for the full list).
    return [
        {"state": "WA", "region_type": "county", "name": "Whatcom County"},
        {"state": "WA", "region_type": "city", "name": "Bellingham"},
    ]
