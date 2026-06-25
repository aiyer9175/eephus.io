# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
refresh_2026.py — pull new 2026 H1 Statcast rows and rebuild all leaderboards.

Steps:
  1. Pull May-29 → today in weekly chunks, append to statcast_2026_H1.parquet.
  2. Re-score 2026 B2B+, Contact+, DCV+ axes via the existing per-axis scripts.
  3. Run the full run_leaderboard pipeline (--no-pull, cache is already updated).
"""

import warnings; warnings.filterwarnings("ignore")
import subprocess, sys
from datetime import date, timedelta
from pathlib import Path
import pandas as pd
from pybaseball import statcast

RAW  = Path(__file__).parent / "data" / "raw"
CACHE = RAW / "statcast_2026_H1.parquet"
TODAY = date.today().isoformat()

# ── 1. Pull the gap ──────────────────────────────────────────────────────────
existing = pd.read_parquet(CACHE)
LAST_DATE = str(existing["game_date"].max())[:10]   # read from cache, not hardcoded
print(f"[1/3] Pulling {LAST_DATE} (exclusive) → {TODAY}")
print(f"  existing cache: {len(existing):,} rows, up to {LAST_DATE}")

cursor = date.fromisoformat(LAST_DATE) + timedelta(days=1)
end_d  = date.today()
new_chunks = []
while cursor <= end_d:
    chunk_end = min(cursor + timedelta(days=6), end_d)
    try:
        df = statcast(start_dt=cursor.isoformat(), end_dt=chunk_end.isoformat())
        if df is not None and len(df):
            new_chunks.append(df)
            print(f"  {cursor} → {chunk_end}: {len(df):,} rows")
        else:
            print(f"  {cursor} → {chunk_end}: 0 rows")
    except Exception as e:
        print(f"  {cursor} → {chunk_end}: FAILED ({e})")
    cursor = chunk_end + timedelta(days=1)

if new_chunks:
    new = pd.concat(new_chunks, ignore_index=True)
    combined = pd.concat([existing, new], ignore_index=True)
    combined["game_date"] = pd.to_datetime(combined["game_date"]).dt.strftime("%Y-%m-%d")
    combined = combined.drop_duplicates(subset=["game_pk", "at_bat_number", "pitch_number"],
                                        keep="last")
    combined.to_parquet(CACHE, index=False)
    print(f"  saved: {len(combined):,} total rows (added {len(combined)-len(existing):,})")
else:
    print("  no new rows found — cache unchanged")

# ── 2. Re-score 2026 per-axis rows ───────────────────────────────────────────
print("\n[2/3] Re-scoring 2026 B2B+ / Contact+ / DCV+")
py = sys.executable
for script in ["b2b_2026.py", "contact_2026.py", "dcv_2026.py"]:
    path = Path(__file__).parent / script
    if not path.exists():
        print(f"  {script}: NOT FOUND — skipping"); continue
    print(f"  running {script}...")
    result = subprocess.run([py, str(path)], capture_output=True, text=True,
                            cwd=str(Path(__file__).parent))
    for line in (result.stdout + result.stderr).strip().splitlines():
        print(f"    {line}")
    if result.returncode != 0:
        print(f"  WARNING: {script} exited {result.returncode}")

# ── 3. Full leaderboard rebuild ───────────────────────────────────────────────
print("\n[3/4] Rebuilding leaderboards (run_leaderboard.py --no-pull)")
result = subprocess.run(
    [py, str(Path(__file__).parent / "run_leaderboard.py"), "--no-pull"],
    cwd=str(Path(__file__).parent)
)
if result.returncode != 0:
    sys.exit(result.returncode)

# ── 4. Re-apply Universal-Audit fixes the rebuild drops (self-healing) ─────────
print("\n[4/4] Post-refresh fixes (per-season Decision+, axis intervals)")
result = subprocess.run(
    [py, str(Path(__file__).parent / "post_refresh.py")],
    cwd=str(Path(__file__).parent)
)
sys.exit(result.returncode)
