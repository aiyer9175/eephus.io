# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
decision_drivers.py — rolling per-game-date decision-driver trajectory, so Decision+
gets the same stacked-area drivers graph as Swing+.

Decomposes each pitch's swing-decision run value into 4 mutually-exclusive buckets
(out-of-zone × early/2-strike, in-zone × early/2-strike), rolls a trailing window,
and scales to Decision+ points so the bands stack to the rolling Decision+ line.
"""
import warnings; warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
import mlb_decision as md

PROC = Path(__file__).parent / "data" / "processed"
OUT = PROC / "decision_traj.parquet"
WIN, MINP = 250, 80


def build():
    agg, d = md.score(verbose=False)
    mu = float(agg.dec_rv100_tailored.mean()); sd = float(agg.dec_rv100_tailored.std())
    d = d.dropna(subset=["game_date"]).copy()
    iz = d["inzone"].values; two = (d["strikes"].values == 2); rv = d["drv_tailored"].values
    d["b_oze"] = np.where((~iz) & (~two), rv, 0.0)   # out-of-zone, early counts (chase discipline)
    d["b_ozl"] = np.where((~iz) & two, rv, 0.0)      # out-of-zone, 2 strikes (protect)
    d["b_ize"] = np.where(iz & (~two), rv, 0.0)      # in-zone, early (attack)
    d["b_izl"] = np.where(iz & two, rv, 0.0)         # in-zone, 2 strikes
    bcols = ["b_oze", "b_ozl", "b_ize", "b_izl"]
    Lb = {c: d[c].mean() for c in bcols}          # league mean run value per pitch, per bucket (centering)
    d["game_date"] = pd.to_datetime(d["game_date"])
    d = d.sort_values(["batter", "game_date"]).reset_index(drop=True)
    # trailing rolling mean of each bucket per batter, CENTERED on league avg, scaled to Decision+ points
    roll = d.groupby("batter")[bcols].transform(lambda s: s.rolling(WIN, min_periods=MINP).mean())
    for c in bcols:
        d[c + "_pts"] = (roll[c].values - Lb[c]) * 100 / sd * 10   # contribution vs league -> Decision+ points
    d["dp"] = 100 + d[[c + "_pts" for c in bcols]].sum(axis=1)
    d["season"] = d["game_date"].dt.year.astype(str)
    d = d.dropna(subset=[c + "_pts" for c in bcols])
    # one row per (batter, game_date): last rolling value of the day
    last = d.groupby(["batter", "season", d["game_date"].dt.strftime("%Y-%m-%d")]).tail(1)
    last = last.rename(columns={"game_date": "gd"})
    out = last[["batter", "season"]].copy()
    out["game_date"] = last["gd"].dt.strftime("%Y-%m-%d").values
    out["dp"] = last["dp"].round(1).values
    for c in bcols:
        out[c] = last[c + "_pts"].round(2).values
    out.to_parquet(OUT, index=False)
    print(f"wrote {OUT}: {len(out)} batter-game-dates, {out.batter.nunique()} hitters")
    return out


if __name__ == "__main__":
    build()
