#!/usr/bin/env python3
"""
Probe the CURRENT Overture buildings schema so we can fix the query.

The release 2026-04-15.0 exists (parquet files are there) but our query
throws BinderException — meaning the column/struct names we filter on
(bbox.xmin, geometry, etc.) don't match the current schema. This prints
the actual schema so we can correct app/polygons.py.

Usage:
    python scripts/check_overture_schema.py
"""
from __future__ import annotations
import sys

try:
    import duckdb
except ImportError:
    print("duckdb not installed.")
    sys.exit(1)

RELEASE = "2026-04-15.0"
URL = (f"s3://overturemaps-us-west-2/release/{RELEASE}"
       f"/theme=buildings/type=building/*.parquet")


def main() -> int:
    con = duckdb.connect()
    con.execute("INSTALL spatial; LOAD spatial;")
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute("SET s3_region='us-west-2';")

    print(f"Probing schema of {RELEASE}...\n")

    # DESCRIBE shows column names + types without scanning much data.
    try:
        rows = con.execute(f"DESCRIBE SELECT * FROM read_parquet('{URL}') LIMIT 1").fetchall()
    except Exception as e:
        print(f"DESCRIBE failed: {e}")
        return 1

    print("Columns in current Overture buildings release:")
    bbox_col = None
    geom_col = None
    for name, ctype, *_ in rows:
        print(f"  {name}: {ctype}")
        low = name.lower()
        if "bbox" in low:
            bbox_col = (name, ctype)
        if low in ("geometry", "geom", "wkb_geometry"):
            geom_col = (name, ctype)

    print()
    if bbox_col:
        print(f">> bbox column: {bbox_col[0]} (type: {bbox_col[1]})")
        print("   ^ note the SUBFIELD names in that struct type above —")
        print("     we need them for the spatial filter (e.g. xmin vs minx).")
    else:
        print(">> No 'bbox' column found. The spatial filter must use a")
        print("   different mechanism (maybe ST_ functions on geometry directly).")
    if geom_col:
        print(f">> geometry column: {geom_col[0]} (type: {geom_col[1]})")

    # Try to pull one row's bbox struct to see its field names concretely.
    if bbox_col:
        try:
            sample = con.execute(
                f"SELECT {bbox_col[0]} FROM read_parquet('{URL}') LIMIT 1"
            ).fetchone()
            print(f"\nSample bbox value: {sample}")
        except Exception as e:
            print(f"\n(could not fetch sample bbox: {e})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
