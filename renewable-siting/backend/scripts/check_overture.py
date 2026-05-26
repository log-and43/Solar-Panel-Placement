#!/usr/bin/env python3
"""
Probe Overture Maps S3 to discover the current release version.

Run this whenever the build appears to fail with "No files found" for
Overture buildings — it'll print the actual release paths that exist,
so you can update OVERTURE_RELEASES in app/polygons.py.

Usage:
    python scripts/check_overture.py
"""

from __future__ import annotations

import sys

try:
    import duckdb
except ImportError:
    print("duckdb not installed. Run: pip install -r requirements.txt")
    sys.exit(1)


def main() -> int:
    con = duckdb.connect()
    try:
        con.execute("INSTALL httpfs; LOAD httpfs;")
        con.execute("SET s3_region='us-west-2';")
    except Exception as e:
        print(f"duckdb setup failed: {e}")
        return 1

    print("Looking up published Overture buildings releases...\n")
    try:
        # Pull a handful of building-partition files, extract their release
        # segment, and dedup. This is more reliable than globbing release/*
        # directly because some duckdb glob behaviors don't list "directories".
        query = """
            SELECT DISTINCT
                regexp_extract(file, 'release/([0-9-.]+)/', 1) AS release
            FROM glob('s3://overturemaps-us-west-2/release/*/theme=buildings/type=building/*.parquet')
            ORDER BY release DESC
            LIMIT 12
        """
        rows = con.execute(query).fetchall()
    except Exception as e:
        print(f"Glob failed: {e}")
        return 1

    if not rows:
        print("No buildings found. The bucket layout may have changed.")
        return 1

    print("Latest releases (most recent first):")
    for (r,) in rows:
        print(f"  {r}")
    print()
    print("To update the code: copy the top entry into the top of")
    print("OVERTURE_RELEASES in app/polygons.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
