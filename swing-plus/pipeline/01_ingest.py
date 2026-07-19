# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
01_ingest.py - Pull Statcast pitch-level data with bat tracking fields.

Bat tracking is only available from 2023-07-11 onward (All-Star break).
We pull in chunks because pybaseball.statcast() is rate-limited and times
out on full-season requests. Cache to Parquet so we never re-pull.
"""

from pathlib import Path
from datetime import date, timedelta
import pandas as pd
from pybaseball import statcast

CACHE_DIR = Path("data/raw")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Define season-halves the way Driveline does (split at All-Star break).
# Update the 2025 H2 end date as the season progresses.
SEASON_HALVES = {
    "2023_H2": ("2023-07-14", "2023-10-01"),
    "2024_H1": ("2024-03-28", "2024-07-15"),
    "2024_H2": ("2024-07-19", "2024-09-29"),
    "2025_H1": ("2025-03-27", "2025-07-14"),
    "2025_H2": ("2025-07-18", "2025-09-28"),
}


def pull_range(start: str, end: str, label: str) -> pd.DataFrame:
    """Pull a date range in weekly chunks. pybaseball times out on large pulls."""
    cache_file = CACHE_DIR / f"statcast_{label}.parquet"
    if cache_file.exists():
        print(f"[{label}] cached, loading from disk")
        return pd.read_parquet(cache_file)

    print(f"[{label}] pulling {start} to {end}")
    start_d = date.fromisoformat(start)
    end_d = date.fromisoformat(end)
    chunks = []
    cursor = start_d
    while cursor <= end_d:
        chunk_end = min(cursor + timedelta(days=6), end_d)
        try:
            df = statcast(start_dt=cursor.isoformat(), end_dt=chunk_end.isoformat())
            if df is not None and len(df) > 0:
                chunks.append(df)
            print(f"  {cursor} -> {chunk_end}: {len(df) if df is not None else 0} rows")
        except Exception as e:
            print(f"  {cursor} -> {chunk_end}: FAILED ({e})")
        cursor = chunk_end + timedelta(days=1)

    if not chunks:
        raise RuntimeError(f"No data pulled for {label}")
    full = pd.concat(chunks, ignore_index=True)
    full.to_parquet(cache_file, index=False)
    print(f"[{label}] saved {len(full):,} rows -> {cache_file}")
    return full


def pull_all() -> dict[str, pd.DataFrame]:
    return {label: pull_range(s, e, label) for label, (s, e) in SEASON_HALVES.items()}


if __name__ == "__main__":
    # Start with a single half to validate the pipeline before pulling everything.
    df = pull_range("2024-07-19", "2024-09-29", "2024_H2")
    print(f"\nColumns ({len(df.columns)}): {sorted(df.columns)[:20]}...")
    print(f"Rows with bat_speed populated: {df['bat_speed'].notna().sum():,}")
