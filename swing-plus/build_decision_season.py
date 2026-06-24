# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
build_decision_season.py — canonical PER-SEASON Decision+ (audit fix).

The leaderboard showed a static career value (decision_plus_mlb.csv merged on
batter), while the player modal showed a per-season value from decision_traj —
two different Decision+ systems (career-corr 0.53) giving the same player two
numbers. Fix: make the season-varying `decision_traj` the canonical headline,
re-anchored to the familiar CSV scale via OLS on the overlapping players, so we
keep season-variation AND a consistent scale.

Output: data/processed/decision_plus_season.parquet (batter, season, decision_plus, n_dp)
"""

import numpy as np
import pandas as pd
from pathlib import Path

PROC = Path(__file__).parent / "data" / "processed"


def main():
    tr = pd.read_parquet(PROC / "decision_traj.parquet")
    tr["season"] = tr["season"].astype(int)
    per = tr.groupby(["batter", "season"]).agg(dp=("dp", "mean"), n_dp=("dp", "size")).reset_index()

    # decision_traj IS the per-date version of the board's decision_plus_mlb model
    # (same swing-tailored RV; career-corr 0.97). Re-anchor per-season dp to that
    # exact scale so board + modal agree and the existing 100±10 unit is preserved.
    board = pd.read_parquet(PROC / "mlb_decision.parquet")[["batter", "decision_plus_mlb"]]
    trajc = per.groupby("batter")["dp"].mean().rename("trajc").reset_index()
    ov = board.merge(trajc, on="batter").dropna()
    b, a = np.polyfit(ov["trajc"], ov["decision_plus_mlb"], 1)
    print(f"re-anchor fit (n={len(ov)}): decision_plus_mlb = {a:.2f} + {b:.3f} * traj_dp  "
          f"(overlap corr {ov['trajc'].corr(ov['decision_plus_mlb']):.3f})")

    per["decision_plus_mlb"] = (a + b * per["dp"]).round(1)
    out = per[["batter", "season", "decision_plus_mlb", "n_dp"]]
    out.to_parquet(PROC / "decision_plus_season.parquet", index=False)
    print(f"saved decision_plus_season.parquet: {len(out)} rows, "
          f"mean {out['decision_plus_mlb'].mean():.1f} sd {out['decision_plus_mlb'].std():.1f} "
          f"(target board mean 100.0 sd 10.0)")
    # sanity: per-season is now season-varying
    nuniq = out.groupby("batter")["decision_plus_mlb"].nunique()
    print(f"distinct values per player: median {nuniq.median():.0f} (was 1 = static)")


if __name__ == "__main__":
    main()
