"""
Data store: loads the three Parquet files produced by scripts/build_data.py
and exposes them to the rest of the backend.

Loaded once at import time. The files are ~MB-scale, fitting easily in memory.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class DataNotBuiltError(RuntimeError):
    """Raised when the Parquet files don't exist yet."""


def _require(path: Path) -> Path:
    if not path.exists():
        raise DataNotBuiltError(
            f"Expected data file not found: {path}\n"
            f"Run: cd backend && python scripts/build_data.py"
        )
    return path


@cache
def states_df() -> pd.DataFrame:
    return pd.read_parquet(_require(DATA_DIR / "states.parquet"))


@cache
def counties_df() -> pd.DataFrame:
    return pd.read_parquet(_require(DATA_DIR / "counties.parquet"))


@cache
def places_df() -> pd.DataFrame:
    return pd.read_parquet(_require(DATA_DIR / "places.parquet"))


# ============================================================
# Phase 5: government finance data (capital outlay budgets)
# ============================================================

@cache
def finance_states_df() -> pd.DataFrame:
    return pd.read_parquet(_require(DATA_DIR / "finance_states.parquet"))


@cache
def finance_counties_df() -> pd.DataFrame:
    return pd.read_parquet(_require(DATA_DIR / "finance_counties.parquet"))


@cache
def finance_places_df() -> pd.DataFrame:
    return pd.read_parquet(_require(DATA_DIR / "finance_places.parquet"))


def data_available() -> bool:
    """True iff the core Phase-2 Parquet files exist. Lets the app start
    gracefully in Phase-1 mode if Phase 2 data hasn't been built yet."""
    for name in ("states.parquet", "counties.parquet", "places.parquet"):
        if not (DATA_DIR / name).exists():
            return False
    return True


def finance_available() -> bool:
    """True iff Phase-5 government-finance Parquet files exist. Phase 5
    degrades independently of Phase 2 — the app still works without it,
    just without the affordability panel."""
    for name in ("finance_states.parquet", "finance_counties.parquet",
                 "finance_places.parquet"):
        if not (DATA_DIR / name).exists():
            return False
    return True
