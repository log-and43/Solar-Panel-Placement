#!/usr/bin/env python3
"""
Build the Phase 5 government-finance data files.

Produces:
  backend/data/finance_states.parquet
  backend/data/finance_counties.parquet   (may be sparse / state-derived)
  backend/data/finance_places.parquet      (may be sparse / state-derived)

Each has at minimum: state_abbr / name columns + capital_outlay_dollars.

IMPORTANT — read this before running:

The Census Annual Survey of Government Finances does NOT publish a clean
per-city CSV the way the population estimates do. Its formats change year
to year and per-locality coverage is partial. This script is therefore
deliberately defensive and verbose: it prints what it found at each step
so we can adjust the parsing to the actual file schema you get.

Run with --inspect first to see the raw columns without committing to a
parse:

    python scripts/build_finance.py --inspect
    python scripts/build_finance.py            # full build

If the source URL or schema has changed (likely), the --inspect output
tells us exactly what to fix. This is the same iterate-on-real-data
workflow we used for the eGRID percentage bug and the Overture release
version.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import CENSUS_GOV_FINANCE_STATE  # type: ignore[import-not-found]

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

CONTINENTAL_EXCLUDES = {"AK", "HI", "PR", "VI", "GU", "MP", "AS", "DC"}

# Candidate column names for "capital outlay" across Census finance vintages.
# The survey has used several labels; we try each.
CAPITAL_OUTLAY_CANDIDATES = [
    "Total Capital Outlay",
    "Capital outlay",
    "Capital Outlay",
    "TotalCapitalOutlay",
    "CapitalOutlay",
]
# Candidate state-name / abbr columns
STATE_NAME_CANDIDATES = ["State", "Name", "Geographic area", "STATE", "state"]


def fetch(source, force: bool = False) -> Path:
    local = RAW_DIR / f"{source.name}{Path(source.url).suffix}"
    if local.exists() and not force:
        print(f"  [cache] {source.name}: {local.name}")
        return local
    print(f"  [fetch] {source.name}: {source.url}")
    req = Request(source.url, headers={"User-Agent": "renewable-siting-finance/0.5"})
    try:
        with urlopen(req, timeout=60) as resp:
            data = resp.read()
    except Exception as e:
        raise RuntimeError(
            f"Failed to download {source.name}: {e}\n"
            f"  Where to look if URL moved: {source.where_to_find_if_broken}"
        ) from e
    local.write_bytes(data)
    print(f"  [ok]    wrote {local.name} ({len(data):,} bytes)")
    return local


def _find_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    lower_map = {c.lower().strip(): c for c in df.columns}
    for cand in candidates:
        if cand.lower().strip() in lower_map:
            return lower_map[cand.lower().strip()]
    return None


def inspect() -> int:
    """Download the finance file and print its structure. No parsing commitment."""
    local = fetch(CENSUS_GOV_FINANCE_STATE)
    print("\n[inspect] attempting to read as CSV...")
    try:
        df = pd.read_csv(local, encoding="latin-1")
    except Exception as e:
        print(f"  read_csv failed: {e}")
        print("  The file may be fixed-width, Excel, or have header junk rows.")
        print("  First 500 bytes:")
        print(local.read_bytes()[:500])
        return 1

    print(f"\n  shape: {df.shape}")
    print(f"  columns ({len(df.columns)}):")
    for c in df.columns[:40]:
        print(f"    - {c!r}")
    print("\n  first 3 rows:")
    print(df.head(3).to_string())

    cap_col = _find_column(df, CAPITAL_OUTLAY_CANDIDATES)
    state_col = _find_column(df, STATE_NAME_CANDIDATES)
    print(f"\n  detected capital-outlay column: {cap_col!r}")
    print(f"  detected state column:          {state_col!r}")
    if cap_col is None:
        print("\n  >> No capital-outlay column matched. Paste the column list")
        print("     above back to the assistant and we'll map the right one.")
    return 0


def build(force: bool = False) -> int:
    import us as us_pkg

    local = fetch(CENSUS_GOV_FINANCE_STATE, force=force)
    try:
        df = pd.read_csv(local, encoding="latin-1")
    except Exception as e:
        print(f"[error] Could not read finance CSV: {e}")
        print("Run with --inspect to see the raw structure.")
        return 1

    cap_col = _find_column(df, CAPITAL_OUTLAY_CANDIDATES)
    state_col = _find_column(df, STATE_NAME_CANDIDATES)
    if cap_col is None or state_col is None:
        print(f"[error] Could not locate required columns.")
        print(f"  capital-outlay column found: {cap_col!r}")
        print(f"  state column found:          {state_col!r}")
        print("Run with --inspect and share the column list to fix the mapping.")
        return 1

    # Map full state names → USPS abbreviations.
    name_to_abbr = {s.name.lower(): s.abbr for s in us_pkg.states.STATES}

    rows = []
    for _, r in df.iterrows():
        raw_name = str(r[state_col]).strip()
        abbr = name_to_abbr.get(raw_name.lower())
        if abbr is None:
            continue
        if abbr in CONTINENTAL_EXCLUDES:
            continue
        # Capital outlay may be in thousands of dollars in Census tables —
        # we store raw and note the unit assumption. Parse loosely.
        val = pd.to_numeric(str(r[cap_col]).replace(",", "").replace("$", ""),
                            errors="coerce")
        if val != val:  # NaN
            continue
        # Census state finance tables are typically in THOUSANDS of dollars.
        dollars = float(val) * 1000.0
        rows.append({"state_abbr": abbr, "capital_outlay_dollars": dollars})

    fin_states = pd.DataFrame(rows).drop_duplicates("state_abbr")
    if fin_states.empty:
        print("[error] No state rows parsed. Schema likely differs from expected.")
        print("Run with --inspect to diagnose.")
        return 1

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    fin_states.to_parquet(DATA_DIR / "finance_states.parquet", index=False)
    print(f"  finance_states: {len(fin_states)} rows")

    # Counties and places: the state survey doesn't give us these directly.
    # We write EMPTY frames with the right schema so the loader works; the
    # affordability module's population-share extrapolation fills them in
    # from the state totals at request time.
    empty_county = pd.DataFrame(columns=["state_abbr", "county_name",
                                         "capital_outlay_dollars"])
    empty_place = pd.DataFrame(columns=["state_abbr", "place_name",
                                        "capital_outlay_dollars"])
    empty_county.to_parquet(DATA_DIR / "finance_counties.parquet", index=False)
    empty_place.to_parquet(DATA_DIR / "finance_places.parquet", index=False)
    print("  finance_counties: 0 direct rows (population-extrapolated at runtime)")
    print("  finance_places:   0 direct rows (population-extrapolated at runtime)")

    print("\n[sanity] sample states:")
    for _, r in fin_states.head(5).iterrows():
        print(f"  {r['state_abbr']}: ${r['capital_outlay_dollars']:,.0f} capital outlay")

    print("\nDone. NOTE: county/city budgets are extrapolated from state totals")
    print("by population share until per-locality finance data is added.")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--inspect", action="store_true",
                   help="Download and print the file structure without parsing.")
    p.add_argument("--force-download", action="store_true")
    args = p.parse_args()

    if args.inspect:
        return inspect()
    return build(force=args.force_download)


if __name__ == "__main__":
    sys.exit(main())
