#!/usr/bin/env python3
"""
Probe the Census Government Finances API to find a working query.

We can't browse from the build environment, so this tries several candidate
API calls against the live Census API (which YOUR machine can reach) and
reports which one returns usable data. Run it, paste the output back, and
we wire the winning query into build_finance.py.

Background: the data.census.gov table viewer URL
  data.census.gov/table/GOVSTIMESERIES.GS00LF01?...&nkd=GOVTYPE~001,time~2022
is an interactive web app, not a downloadable file. The data behind it is
served by the Census API at:
  https://api.census.gov/data/timeseries/govs

This script tries a few variable/geography combinations because the exact
variable names for "capital outlay" in the govs time-series aren't something
we can confirm without hitting the live API.

Usage:
    python scripts/probe_census_finance.py
"""

from __future__ import annotations

import json
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API_BASE = "https://api.census.gov/data/timeseries/govs"

# Candidate queries. The govs time-series uses variable codes; we try the
# most likely capital-outlay-related ones plus a metadata fetch so we can
# SEE the real variable names if our guesses miss.
CANDIDATES = [
    {
        "label": "Variable metadata (lists ALL available variables)",
        "url": f"{API_BASE}/variables.json",
        "is_metadata": True,
    },
    {
        "label": "State-level, EXPENDTOT + by govtype, 2022",
        "url": f"{API_BASE}?" + urlencode({
            "get": "GEO_ID,NAME,EXPENDTOT",
            "for": "state:*",
            "YEAR": "2022",
        }),
        "is_metadata": False,
    },
    {
        "label": "State-level, AMOUNT with category filter, 2022",
        "url": f"{API_BASE}?" + urlencode({
            "get": "GEO_ID,NAME,AMOUNT",
            "for": "state:*",
            "YEAR": "2022",
        }),
        "is_metadata": False,
    },
]


def try_one(c: dict) -> None:
    print(f"\n=== {c['label']} ===")
    print(f"    {c['url'][:120]}{'...' if len(c['url']) > 120 else ''}")
    req = Request(c["url"], headers={"User-Agent": "renewable-siting-probe/0.5"})
    try:
        with urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            pass
        print(f"    HTTP {e.code}: {detail}")
        return
    except (URLError, TimeoutError) as e:
        print(f"    network error: {e}")
        return

    if c["is_metadata"]:
        # Print variable names that look budget/expenditure-related so we can
        # pick the right one.
        try:
            data = json.loads(body)
            variables = data.get("variables", {})
            print(f"    {len(variables)} variables total. Budget/spend-related ones:")
            for name, meta in sorted(variables.items()):
                label = (meta.get("label") or "").lower()
                if any(k in label for k in ("capital", "outlay", "expenditure",
                                            "spend", "construction")):
                    print(f"      {name}: {meta.get('label')}")
        except json.JSONDecodeError:
            print(f"    (could not parse metadata) first 300 chars:\n{body[:300]}")
        return

    # Data response: Census returns a JSON array-of-arrays, header row first.
    try:
        data = json.loads(body)
        print(f"    OK — {len(data)-1} data rows. Header: {data[0]}")
        if len(data) > 1:
            print(f"    sample row: {data[1]}")
    except json.JSONDecodeError:
        print(f"    Non-JSON response, first 300 chars:\n{body[:300]}")


def main() -> int:
    print("Probing Census Government Finances API...")
    print("(Your machine can reach api.census.gov; the build sandbox cannot.)")
    for c in CANDIDATES:
        try_one(c)
    print("\n---")
    print("Paste this entire output back. The metadata block tells us the real")
    print("variable name for capital outlay; the data blocks tell us which query")
    print("shape actually returns rows. Then we wire the winner into")
    print("build_finance.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
