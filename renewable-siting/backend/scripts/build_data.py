#!/usr/bin/env python3
"""
Build the Phase 2 data files.

What this does:
  1. Downloads source files from EIA, EPA, and Census (~50 MB total).
  2. Cleans + merges into three Parquet files:
       backend/data/states.parquet
       backend/data/counties.parquet
       backend/data/places.parquet
  3. Each output row has: name, state, FIPS, population, centroid_lat,
     centroid_lon, bbox (computed), consumption_mwh_per_year (states only),
     and generation mix percentages (states only).

How to use:
    cd backend
    python scripts/build_data.py --check        # test which URLs are reachable
    python scripts/build_data.py                # do the full build
    python scripts/build_data.py --skip-download # rebuild from already-downloaded raw files
    python scripts/build_data.py --override-url eia_seds_use=https://new.url/file.csv

Resumability: raw downloads land in backend/data/raw/ and are cached.
Re-running this script after a partial failure won't re-download what already
succeeded.

If something breaks, the error message will name the source. Look up that
source in backend/scripts/sources.py for the 'where_to_find_if_broken' hint.
"""

from __future__ import annotations

import argparse
import io
import sys
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd

# Local import — works when running from backend/ as cwd.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import (  # type: ignore[import-not-found]
    ALL_SOURCES,
    CENSUS_GAZ_COUNTIES,
    CENSUS_GAZ_PLACES,
    CENSUS_COUNTY_POP,
    CENSUS_PLACE_POP,
    CENSUS_STATE_POP,
    EIA_SEDS_USE,
    EPA_EGRID,
    Source,
)


# ============================================================
# Paths
# ============================================================
BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

# Continental US filter (drop AK, HI, PR, territories).
CONTINENTAL_EXCLUDES = {"AK", "HI", "PR", "VI", "GU", "MP", "AS", "DC"}
# DC is debatable; the original project brief says "continental US."
# We'll exclude it to be consistent. Easy to re-include if you want.


# ============================================================
# Download helpers
# ============================================================

def _local_path_for(source: Source) -> Path:
    return RAW_DIR / f"{source.name}{Path(source.url).suffix}"


def fetch(source: Source, force: bool = False) -> Path:
    """Download a source file to RAW_DIR, returning the local path."""
    local = _local_path_for(source)
    if local.exists() and not force:
        print(f"  [cache] {source.name}: using {local.name}")
        return local

    print(f"  [fetch] {source.name}: {source.url}")
    req = Request(source.url, headers={"User-Agent": "renewable-siting-build/0.2"})
    try:
        with urlopen(req, timeout=60) as resp:
            data = resp.read()
    except Exception as e:
        raise RuntimeError(
            f"Failed to download {source.name} from {source.url}\n"
            f"  Error: {e}\n"
            f"  Where to look if URL has moved: {source.where_to_find_if_broken}"
        ) from e

    local.write_bytes(data)
    print(f"  [ok]    wrote {local.name} ({len(data):,} bytes)")
    return local


def check_reachable() -> int:
    """HEAD each source URL and report status. Doesn't download bodies."""
    from urllib.request import Request, urlopen
    bad = 0
    for s in ALL_SOURCES:
        try:
            req = Request(s.url, method="HEAD",
                          headers={"User-Agent": "renewable-siting-build/0.2"})
            with urlopen(req, timeout=10) as resp:
                print(f"  [{resp.status}] {s.name}  {s.url}")
        except Exception as e:
            print(f"  [FAIL] {s.name}  {s.url}\n         {e}")
            print(f"         → see: {s.where_to_find_if_broken}")
            bad += 1
    return bad


# ============================================================
# Census population
# ============================================================

def load_state_population(force_download: bool) -> pd.DataFrame:
    """Returns DataFrame with columns: state_fips, state_abbr, state_name, population."""
    local = fetch(CENSUS_STATE_POP, force=force_download)
    df = pd.read_csv(local, encoding="latin-1")

    # Vintage 2023 file: columns include STATE (FIPS), NAME, POPESTIMATE2023, SUMLEV
    # SUMLEV=040 is state-level rows
    df = df[df["SUMLEV"] == 40].copy()
    df = df.rename(columns={
        "STATE": "state_fips",
        "NAME": "state_name",
        "POPESTIMATE2023": "population",
    })

    # Map FIPS → 2-letter abbr using `us` package
    import us as us_states_pkg
    fips_to_abbr = {s.fips: s.abbr for s in us_states_pkg.states.STATES}
    df["state_abbr"] = df["state_fips"].astype(str).str.zfill(2).map(fips_to_abbr)
    df = df.dropna(subset=["state_abbr"])
    df = df[~df["state_abbr"].isin(CONTINENTAL_EXCLUDES)]

    return df[["state_fips", "state_abbr", "state_name", "population"]].reset_index(drop=True)


def load_county_population(force_download: bool) -> pd.DataFrame:
    """Returns columns: state_abbr, state_fips, county_fips, county_name, population."""
    local = fetch(CENSUS_COUNTY_POP, force=force_download)
    df = pd.read_csv(local, encoding="latin-1")

    # SUMLEV=050 is county-level rows
    df = df[df["SUMLEV"] == 50].copy()

    import us as us_states_pkg
    fips_to_abbr = {s.fips: s.abbr for s in us_states_pkg.states.STATES}

    df["state_fips"] = df["STATE"].astype(str).str.zfill(2)
    df["county_fips"] = df["COUNTY"].astype(str).str.zfill(3)
    df["state_abbr"] = df["state_fips"].map(fips_to_abbr)
    df = df.dropna(subset=["state_abbr"])
    df = df[~df["state_abbr"].isin(CONTINENTAL_EXCLUDES)]

    df = df.rename(columns={
        "CTYNAME": "county_name",
        "POPESTIMATE2023": "population",
    })

    return df[["state_abbr", "state_fips", "county_fips",
               "county_name", "population"]].reset_index(drop=True)


def load_place_population(force_download: bool, min_population: int) -> pd.DataFrame:
    """Returns columns: state_abbr, state_fips, place_fips, place_name, population."""
    local = fetch(CENSUS_PLACE_POP, force=force_download)
    df = pd.read_csv(local, encoding="latin-1")

    # SUMLEV=162 is incorporated places. 061 is minor civil divisions (skip).
    df = df[df["SUMLEV"] == 162].copy()

    import us as us_states_pkg
    fips_to_abbr = {s.fips: s.abbr for s in us_states_pkg.states.STATES}

    df["state_fips"] = df["STATE"].astype(str).str.zfill(2)
    df["place_fips"] = df["PLACE"].astype(str).str.zfill(5)
    df["state_abbr"] = df["state_fips"].map(fips_to_abbr)
    df = df.dropna(subset=["state_abbr"])
    df = df[~df["state_abbr"].isin(CONTINENTAL_EXCLUDES)]

    df = df.rename(columns={
        "NAME": "place_name",
        "POPESTIMATE2023": "population",
    })

    # Strip the "city"/"town"/"village" suffix from NAME so user-facing names are clean.
    # NAME comes through as e.g. "Bellingham city"; we want "Bellingham".
    for suffix in [" city", " town", " village", " borough", " CDP",
                   " municipality", " (balance)"]:
        df["place_name"] = df["place_name"].str.removesuffix(suffix)

    df = df[df["population"] >= min_population]

    return df[["state_abbr", "state_fips", "place_fips",
               "place_name", "population"]].reset_index(drop=True)


# ============================================================
# Census gazetteer (centroids)
# ============================================================

def load_county_centroids(force_download: bool) -> pd.DataFrame:
    """Returns columns: state_fips, county_fips, centroid_lat, centroid_lon, area_land_m2."""
    local = fetch(CENSUS_GAZ_COUNTIES, force=force_download)

    with zipfile.ZipFile(local) as zf:
        # The zip contains one .txt file (tab-separated).
        names = [n for n in zf.namelist() if n.endswith(".txt")]
        if not names:
            raise RuntimeError(f"No .txt in {local}; contents: {zf.namelist()}")
        with zf.open(names[0]) as f:
            df = pd.read_csv(f, sep="\t", encoding="latin-1")

    # Column names in this file have trailing whitespace. Normalize.
    df.columns = [c.strip() for c in df.columns]

    # Columns of interest: USPS (state abbr), GEOID (5-digit state+county FIPS),
    # NAME, ALAND (land area m²), INTPTLAT, INTPTLONG
    df["state_fips"] = df["GEOID"].astype(str).str.zfill(5).str[:2]
    df["county_fips"] = df["GEOID"].astype(str).str.zfill(5).str[2:]
    df = df.rename(columns={
        "INTPTLAT": "centroid_lat",
        "INTPTLONG": "centroid_lon",
        "ALAND": "area_land_m2",
    })

    df = df[~df["USPS"].isin(CONTINENTAL_EXCLUDES)]

    return df[["state_fips", "county_fips",
               "centroid_lat", "centroid_lon", "area_land_m2"]].reset_index(drop=True)


def load_place_centroids(force_download: bool) -> pd.DataFrame:
    """Returns columns: state_fips, place_fips, centroid_lat, centroid_lon, area_land_m2."""
    local = fetch(CENSUS_GAZ_PLACES, force=force_download)

    with zipfile.ZipFile(local) as zf:
        names = [n for n in zf.namelist() if n.endswith(".txt")]
        with zf.open(names[0]) as f:
            df = pd.read_csv(f, sep="\t", encoding="latin-1")

    df.columns = [c.strip() for c in df.columns]
    df["state_fips"] = df["GEOID"].astype(str).str.zfill(7).str[:2]
    df["place_fips"] = df["GEOID"].astype(str).str.zfill(7).str[2:]
    df = df.rename(columns={
        "INTPTLAT": "centroid_lat",
        "INTPTLONG": "centroid_lon",
        "ALAND": "area_land_m2",
    })

    df = df[~df["USPS"].isin(CONTINENTAL_EXCLUDES)]

    return df[["state_fips", "place_fips",
               "centroid_lat", "centroid_lon", "area_land_m2"]].reset_index(drop=True)


# ============================================================
# EPA eGRID
# ============================================================

def load_egrid_state_mix(force_download: bool) -> pd.DataFrame:
    """
    Returns columns: state_abbr, plus fraction columns:
      mix_coal, mix_natural_gas, mix_nuclear, mix_hydro,
      mix_wind, mix_solar, mix_other
    """
    local = fetch(EPA_EGRID, force=force_download)

    # eGRID 2022: state-level data is on sheet 'ST22'. Header row is row 1 (zero-indexed).
    df = pd.read_excel(local, sheet_name="ST22", header=1)

    # Column abbreviations in eGRID:
    #   PSTATABB = state abbr
    #   STNGENAN = state annual net generation (MWh)
    #   STCLPR / STOLPR / STGSPR / STNCPR / STHYPR / STWIPR / STSOPR / STBMPR / STOFPR / STOPPR / STOTPR
    #     = % from coal / oil / gas / nuclear / hydro / wind / solar / biomass / other-fossil / other-renew / other
    # These are already PERCENTAGES (0–100), not fractions.

    df = df.rename(columns={"PSTATABB": "state_abbr"})

    keep = {
        "state_abbr": "state_abbr",
        "STCLPR": "mix_coal",
        "STGSPR": "mix_natural_gas",
        "STNCPR": "mix_nuclear",
        "STHYPR": "mix_hydro",
        "STWIPR": "mix_wind",
        "STSOPR": "mix_solar",
    }
    for col in keep:
        if col not in df.columns:
            raise RuntimeError(
                f"Expected column {col!r} in eGRID ST22 sheet but it's not there. "
                f"Available columns: {list(df.columns)[:30]}... "
                f"eGRID column names sometimes change between years; "
                f"see {EPA_EGRID.where_to_find_if_broken}"
            )

    out = df[list(keep)].rename(columns=keep).copy()
    out = out[~out["state_abbr"].isin(CONTINENTAL_EXCLUDES)]

    mix_cols = [c for c in out.columns if c.startswith("mix_")]
    for c in mix_cols:
        out[c] = pd.to_numeric(out[c], errors="coerce")

    # eGRID 2022 stores these as fractions already (0.0–1.0). Older releases
    # used percentages (0–100). Detect which we have by looking at the row sum:
    # if it's ~1.0 we have fractions; if it's ~100 we have percentages.
    sample_sum = out[mix_cols].sum(axis=1).median()
    if sample_sum > 5.0:
        # Looks like percentages — convert to fractions.
        print(f"  [info] eGRID values appear to be percentages (median row sum={sample_sum:.1f}); dividing by 100")
        for c in mix_cols:
            out[c] = out[c] / 100.0
    else:
        print(f"  [info] eGRID values appear to be fractions already (median row sum={sample_sum:.3f}); not rescaling")

    # "Other" is everything not accounted for above (oil, biomass, geothermal,
    # other-fossil, other-renewable). Compute as remainder.
    out["mix_other"] = (1.0 - out[mix_cols].sum(axis=1)).clip(lower=0.0)

    # State-level eGRID has a "US " row sometimes; drop non-2-letter codes.
    out = out[out["state_abbr"].astype(str).str.len() == 2]

    return out.reset_index(drop=True)


# ============================================================
# EIA SEDS — state electricity consumption
# ============================================================

# EIA SEDS uses MSN codes (Mnemonic State Number) for what's being measured.
# ESTCB = Electricity sales to ultimate customers, total, billion Btu.
# We use this as state electricity consumption.
EIA_ELECTRICITY_MSN = "ESTCB"
BTU_PER_MWH = 3_412_140.0  # 1 MWh = 3.41214 million Btu (exactly)


def load_eia_state_consumption(force_download: bool, year: int = 2022) -> pd.DataFrame:
    """Returns columns: state_abbr, electricity_mwh_per_year."""
    local = fetch(EIA_SEDS_USE, force=force_download)
    df = pd.read_csv(local)

    # SEDS columns: 'Data_Status' (header row), 'State' (abbr), 'MSN', then year columns like '1960', '1961', ..., '2022'
    year_col = str(year)
    if year_col not in df.columns:
        # Pick the latest year that IS present.
        year_cols = [c for c in df.columns if c.isdigit()]
        if not year_cols:
            raise RuntimeError(
                f"EIA SEDS file has no year columns. Available: {list(df.columns)[:10]}"
            )
        year_col = max(year_cols, key=int)
        print(f"  [info] EIA year {year} not in SEDS file; using {year_col} instead")

    rows = df[df["MSN"] == EIA_ELECTRICITY_MSN].copy()
    if rows.empty:
        raise RuntimeError(
            f"No rows with MSN={EIA_ELECTRICITY_MSN} in SEDS file. "
            f"Has the MSN code changed? See https://www.eia.gov/state/seds/seds-technical-notes-complete.php"
        )

    # 'State' is 2-letter abbreviation; SEDS values are in billion BTU.
    rows = rows.rename(columns={"State": "state_abbr"})
    rows["electricity_billion_btu"] = pd.to_numeric(rows[year_col], errors="coerce")
    rows = rows.dropna(subset=["electricity_billion_btu"])

    rows["electricity_mwh_per_year"] = (
        rows["electricity_billion_btu"] * 1_000_000_000.0 / BTU_PER_MWH
    )
    rows = rows[~rows["state_abbr"].isin(CONTINENTAL_EXCLUDES)]
    rows = rows[rows["state_abbr"].astype(str).str.len() == 2]
    # SEDS has a "US" row with country totals; the length-2 filter is too permissive.
    rows = rows[rows["state_abbr"] != "US"]

    return rows[["state_abbr", "electricity_mwh_per_year"]].reset_index(drop=True)


# ============================================================
# Bounding box heuristic
# ============================================================

def bbox_from_centroid_and_area(lat: float, lon: float, area_m2: float
                                ) -> tuple[float, float, float, float]:
    """
    Build a rough bbox from (centroid_lat, centroid_lon, land_area_m²).
    Assumes a roughly square region. This is a heuristic — real bboxes
    come from TIGER shapefiles, which we'll wire up in a later phase.

    Returns (west, south, east, north) in degrees, GeoJSON convention.
    """
    if area_m2 <= 0 or pd.isna(area_m2):
        # Default to ~10 km box if area is missing
        side_m = 10_000.0
    else:
        # Slightly enlarge so the box covers boundary irregularities.
        side_m = (area_m2 ** 0.5) * 1.4

    # Meters per degree latitude is ~110_540 (constant).
    # Meters per degree longitude scales by cos(lat).
    import math
    dlat = side_m / 2 / 110_540.0
    dlon = side_m / 2 / (111_320.0 * max(0.05, math.cos(math.radians(lat))))
    return (lon - dlon, lat - dlat, lon + dlon, lat + dlat)


# ============================================================
# Build pipeline
# ============================================================

def build_states(force_download: bool) -> pd.DataFrame:
    print("\n[states]")
    pop = load_state_population(force_download)
    mix = load_egrid_state_mix(force_download)
    cons = load_eia_state_consumption(force_download)

    merged = pop.merge(mix, on="state_abbr", how="left")
    merged = merged.merge(cons, on="state_abbr", how="left")

    missing_mix = merged[merged["mix_coal"].isna()]["state_abbr"].tolist()
    missing_cons = merged[merged["electricity_mwh_per_year"].isna()]["state_abbr"].tolist()
    if missing_mix:
        print(f"  [warn] no eGRID mix for: {missing_mix}")
    if missing_cons:
        print(f"  [warn] no EIA consumption for: {missing_cons}")

    # Fossil = coal + natural gas. (Oil is rare in US power; rolled into 'other'.)
    merged["fossil_fraction"] = merged["mix_coal"].fillna(0) + merged["mix_natural_gas"].fillna(0)
    merged["fossil_mwh_per_year"] = merged["electricity_mwh_per_year"] * merged["fossil_fraction"]

    return merged


def build_counties(states: pd.DataFrame, force_download: bool) -> pd.DataFrame:
    print("\n[counties]")
    pop = load_county_population(force_download)
    cen = load_county_centroids(force_download)

    merged = pop.merge(cen, on=["state_fips", "county_fips"], how="left")
    merged["centroid_lat"] = pd.to_numeric(merged["centroid_lat"], errors="coerce")
    merged["centroid_lon"] = pd.to_numeric(merged["centroid_lon"], errors="coerce")
    merged["area_land_m2"] = pd.to_numeric(merged["area_land_m2"], errors="coerce")
    merged = merged.dropna(subset=["centroid_lat", "centroid_lon"])

    # Bring in state-level numbers for scaling
    state_pop = states[["state_abbr", "population"]].rename(
        columns={"population": "state_population"}
    )
    state_cons = states[["state_abbr", "electricity_mwh_per_year",
                         "fossil_mwh_per_year"]].rename(
        columns={
            "electricity_mwh_per_year": "state_mwh",
            "fossil_mwh_per_year": "state_fossil_mwh",
        }
    )
    merged = merged.merge(state_pop, on="state_abbr", how="left")
    merged = merged.merge(state_cons, on="state_abbr", how="left")

    # Scaled consumption
    share = merged["population"] / merged["state_population"]
    merged["electricity_mwh_per_year"] = merged["state_mwh"] * share
    merged["fossil_mwh_per_year"] = merged["state_fossil_mwh"] * share

    # Bounding boxes
    bboxes = merged.apply(
        lambda r: bbox_from_centroid_and_area(r["centroid_lat"], r["centroid_lon"],
                                              r["area_land_m2"]),
        axis=1,
    )
    merged["bbox_west"] = [b[0] for b in bboxes]
    merged["bbox_south"] = [b[1] for b in bboxes]
    merged["bbox_east"] = [b[2] for b in bboxes]
    merged["bbox_north"] = [b[3] for b in bboxes]

    return merged


def build_places(states: pd.DataFrame, force_download: bool,
                 min_population: int) -> pd.DataFrame:
    print("\n[places]")
    pop = load_place_population(force_download, min_population=min_population)
    cen = load_place_centroids(force_download)

    merged = pop.merge(cen, on=["state_fips", "place_fips"], how="left")
    merged["centroid_lat"] = pd.to_numeric(merged["centroid_lat"], errors="coerce")
    merged["centroid_lon"] = pd.to_numeric(merged["centroid_lon"], errors="coerce")
    merged["area_land_m2"] = pd.to_numeric(merged["area_land_m2"], errors="coerce")
    merged = merged.dropna(subset=["centroid_lat", "centroid_lon"])

    state_pop = states[["state_abbr", "population"]].rename(
        columns={"population": "state_population"}
    )
    state_cons = states[["state_abbr", "electricity_mwh_per_year",
                         "fossil_mwh_per_year"]].rename(
        columns={
            "electricity_mwh_per_year": "state_mwh",
            "fossil_mwh_per_year": "state_fossil_mwh",
        }
    )
    merged = merged.merge(state_pop, on="state_abbr", how="left")
    merged = merged.merge(state_cons, on="state_abbr", how="left")

    share = merged["population"] / merged["state_population"]
    merged["electricity_mwh_per_year"] = merged["state_mwh"] * share
    merged["fossil_mwh_per_year"] = merged["state_fossil_mwh"] * share

    bboxes = merged.apply(
        lambda r: bbox_from_centroid_and_area(r["centroid_lat"], r["centroid_lon"],
                                              r["area_land_m2"]),
        axis=1,
    )
    merged["bbox_west"] = [b[0] for b in bboxes]
    merged["bbox_south"] = [b[1] for b in bboxes]
    merged["bbox_east"] = [b[2] for b in bboxes]
    merged["bbox_north"] = [b[3] for b in bboxes]

    return merged


# ============================================================
# Main
# ============================================================

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check", action="store_true",
                   help="Test source URL reachability; do not download.")
    p.add_argument("--skip-download", action="store_true",
                   help="Use cached raw files only; fail if any are missing.")
    p.add_argument("--force-download", action="store_true",
                   help="Re-download even if cached.")
    p.add_argument("--min-place-population", type=int, default=10_000,
                   help="Minimum population for cities to be included (default: 10000).")
    args = p.parse_args()

    if args.check:
        print("Checking reachability of all sources...\n")
        bad = check_reachable()
        if bad:
            print(f"\n{bad} source(s) unreachable.")
            return 1
        print("\nAll sources reachable.")
        return 0

    if args.skip_download:
        # Verify every expected raw file exists.
        missing = [s for s in ALL_SOURCES if not _local_path_for(s).exists()]
        if missing:
            print("--skip-download set but these raw files are missing:")
            for s in missing:
                print(f"  - {_local_path_for(s)}")
            return 1

    force = args.force_download

    print(f"Building data files. Output → {DATA_DIR}")
    print(f"Raw cache → {RAW_DIR}")
    print(f"Place population cutoff: {args.min_place_population:,}")

    states = build_states(force_download=force)
    counties = build_counties(states, force_download=force)
    places = build_places(states, force_download=force,
                          min_population=args.min_place_population)

    print("\n[write]")
    states.to_parquet(DATA_DIR / "states.parquet", index=False)
    counties.to_parquet(DATA_DIR / "counties.parquet", index=False)
    places.to_parquet(DATA_DIR / "places.parquet", index=False)
    print(f"  states:   {len(states):>5} rows → states.parquet")
    print(f"  counties: {len(counties):>5} rows → counties.parquet")
    print(f"  places:   {len(places):>5} rows → places.parquet")

    # Sanity printout
    print("\n[sanity] sample rows:")
    print("  Washington state:")
    print(states[states["state_abbr"] == "WA"].iloc[0].to_dict())
    print("  Whatcom County, WA:")
    wc = counties[(counties["state_abbr"] == "WA") &
                  (counties["county_name"].str.contains("Whatcom", na=False))]
    if not wc.empty:
        print(wc.iloc[0].to_dict())
    else:
        print("  (not found — check Census file)")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
