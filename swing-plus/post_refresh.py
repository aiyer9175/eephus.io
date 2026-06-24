# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
post_refresh.py — re-apply the Universal-Audit fixes that a full leaderboard
rebuild would otherwise drop. Idempotent; safe to run after every refresh.

  1. rebuild per-season Decision+ (decision_plus_season.parquet) from fresh traj
  2. patch leaderboard_{season,half}.parquet decision_plus_mlb -> per-season value
     (in place, no second full rebuild; alltime keeps the career value)
  3. re-add DCV+ posterior SD/interval + Contact+ forecast interval (fix_axis_intervals)
  4. re-add B2B+ proj_next interval (fix_b2b_proj_intervals)
"""

import subprocess
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).parent
PROC = ROOT / "data" / "processed"
PY = sys.executable


def _run(script):
    r = subprocess.run([PY, str(ROOT / script)], cwd=str(ROOT))
    if r.returncode != 0:
        print(f"  WARNING: {script} exited {r.returncode}")


def patch_boards():
    seas_p = PROC / "decision_plus_season.parquet"
    if not seas_p.exists():
        print("  decision_plus_season.parquet missing — skip board patch"); return
    ps = pd.read_parquet(seas_p)[["batter", "season", "decision_plus_mlb"]]
    ps["season"] = ps["season"].astype(str)
    for view, keycol in [("season", "season"), ("half", "half")]:
        p = PROC / f"leaderboard_{view}.parquet"
        if not p.exists():
            continue
        b = pd.read_parquet(p)
        if keycol not in b.columns or "decision_plus_mlb" not in b.columns:
            continue
        b["_js"] = b[keycol].astype(str).str[:4]
        m = ps.rename(columns={"season": "_js", "decision_plus_mlb": "_dps"})
        b = b.merge(m, on=["batter", "_js"], how="left")
        b["decision_plus_mlb"] = b["_dps"].combine_first(b["decision_plus_mlb"])
        b = b.drop(columns=["_dps", "_js"])
        b.to_parquet(p, index=False)
        nun = b.groupby("batter")["decision_plus_mlb"].nunique().median()
        print(f"  patched leaderboard_{view}: Decision+ per-season (median {nun:.0f} distinct/player)")


def _run_ext(path):
    """Run a script living in another project (absolute path)."""
    p = Path(path).expanduser()
    if not p.exists():
        print(f"  {p.name} missing — skip"); return
    r = subprocess.run([PY, str(p)], cwd=str(p.parent))
    if r.returncode != 0:
        print(f"  WARNING: {p.name} exited {r.returncode}")


def main():
    print("[post-refresh] 1/5 per-season Decision+");   _run("build_decision_season.py")
    print("[post-refresh] 2/5 patch boards");           patch_boards()
    print("[post-refresh] 3/5 DCV+/Contact+ intervals"); _run("fix_axis_intervals.py")
    print("[post-refresh] 4/5 B2B+ proj intervals");    _run("fix_b2b_proj_intervals.py")
    print("[post-refresh] 5/7 injury card");            _run_ext("~/injury_model/build_injury_card.py")
    print("[post-refresh] 6/7 defense projection (multi-yr+aging) + Variance+ def")
    _run_ext("~/defense_plus/build_defense_projection.py"); _run("fix_variance_defense.py")
    print("[post-refresh] 7/8 Variance+ history panel"); _run_ext("~/variance_plus/build_history_panel.py")
    print("[post-refresh] 8/8 pitch-type vulnerability profile"); _run("build_pitch_vuln.py")
    print("[post-refresh] done")


if __name__ == "__main__":
    main()
