# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
Defense+ — BACKTEST of the integrated career-defense projection.

Era handling (per the era check): DRS is league-relative each year and the spread is
stable (~7-8 run SD), so we work in era-relative runs throughout — the "rising bar" is
auto-absorbed by the relative metric and by the within-player aging curves. Realized
outcomes are likewise each-year DRS (vs that year's league).

Design: take defenders established (Inn>=600) in a base year (2016-2018). Project their
defensive runs over the SAME horizon to 2025 using the Career+ engine (shrunk base talent
+ per-position aging + exit hazard + migration). Compare to what they ACTUALLY accrued
(sum of realized DRS, base+1..2025). Check calibration, rank accuracy, interval coverage.
"""
import os, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore"); pd.set_option("display.width", 200)
rng = np.random.default_rng(11)
HOME = os.path.expanduser("~"); RAW = os.path.join(HOME, "defense_plus/data/raw")
POSADJ = {"C": 12.5, "SS": 7.5, "2B": 2.5, "3B": 2.5, "CF": 2.5, "LF": -7.5, "RF": -7.5, "1B": -12.5, "DH": -17.5}
SLOPE = {"C": 0.80, "CF": 0.73, "SS": 0.62, "RF": 0.37, "2B": 0.37, "3B": 0.23, "LF": 0.15, "1B": -0.07, "DH": 0.0}
MIG = {"SS": "2B", "2B": "3B", "3B": "1B", "CF": "LF", "RF": "LF", "LF": "1B", "C": "1B", "1B": "DH", "DH": "DH"}
EXIT = {22: .10, 23: .10, 24: .13, 25: .08, 26: .12, 27: .11, 28: .10, 29: .08, 30: .09, 31: .11, 32: .11, 33: .17, 34: .19, 35: .18, 36: .28, 37: .25, 38: .22, 39: .30, 40: .35}
SHRINK = 0.55   # DRS reliability -> regress base-year DRS toward 0 to estimate talent
PT = 0.85
def eh(a): a = int(round(a)); return EXIT.get(a, 0.10 if a < 22 else 0.5)

# load FG fielding (DRS) by player-position-season + age
fr = []
for y in range(2016, 2026):
    f = os.path.join(RAW, f"fg_field_full_{y}.csv")
    if os.path.exists(f):
        d = pd.read_csv(f).rename(columns={"xMLBAMID": "id"})
        for c in ["id", "DRS", "Inn"]: d[c] = pd.to_numeric(d[c], errors="coerce")
        d["year"] = y; fr.append(d[["id", "Pos", "year", "DRS", "Inn"]])
F = pd.concat(fr).dropna(subset=["id", "DRS"])
prim = F.loc[F[F.Inn >= 100].groupby(["id", "year"])["Inn"].idxmax()]   # primary pos/yr
dm = pd.read_parquet(os.path.join(HOME, "projection_engine/data/deep_mlb.parquet"))[["batter", "season", "age"]]

def sim_career(pos0, age0, tal0, horizon, M=1500):
    runs = np.empty(M)
    for m in range(M):
        pos, age, tal = pos0, age0, tal0; tot = 0.0
        for _ in range(horizon):
            if rng.random() < eh(age): break
            tot += (tal + POSADJ[pos]) * PT
            age += 1; tal -= SLOPE[pos]
            if rng.random() < 0.18 and rng.random() < (1 - eh(age)):   # simple migration
                nn = MIG[pos]
                if POSADJ[nn] < POSADJ[pos]: tal += 2.5
                pos = nn
        runs[m] = tot
    return runs

rows = []
for base in [2016, 2017, 2018]:
    bp = prim[(prim.year == base) & (prim.Inn >= 600)].merge(
        dm.rename(columns={"batter": "id", "season": "year"}), on=["id", "year"], how="left").dropna(subset=["age"])
    for _, r in bp.iterrows():
        pid, pos, age = int(r.id), r.Pos, float(r.age)
        if pos not in POSADJ or pos == "DH": continue
        tal = float(r.DRS) * SHRINK                       # shrunk talent estimate (position-relative runs)
        horizon = 2025 - base
        proj = sim_career(pos, age, tal, horizon)
        realized = F[(F.id == pid) & (F.year > base) & (F.year <= 2025) & (F.Inn >= 100)]["DRS"].sum()
        # realized "total value" adds the positional adjustment the player actually earned each yr
        radj = prim[(prim.id == pid) & (prim.year > base) & (prim.year <= 2025)]
        posval = sum(POSADJ.get(p, 0) * (i / 1350.0) for p, i in zip(radj.Pos, radj.Inn))
        rows.append(dict(id=pid, base=base, pos=pos, age=round(age),
                         proj=proj.mean(), p10=np.percentile(proj, 10), p90=np.percentile(proj, 90),
                         realized=realized + posval))
B = pd.DataFrame(rows)
print(f"backtest cohort: {len(B)} player-base-years (2016-18 base, Inn>=600), horizon to 2025\n")
rho = B[["proj", "realized"]].corr(method="spearman").iloc[0, 1]
bias = B.proj.mean() - B.realized.mean()
cover = ((B.realized >= B.p10) & (B.realized <= B.p90)).mean()
mae = (B.proj - B.realized).abs().mean()
print("=== BACKTEST RESULTS (career defensive runs, era-relative) ===")
print(f"  rank accuracy (Spearman proj vs realized): {rho:+.3f}")
print(f"  calibration bias (mean proj - mean realized): {bias:+.1f} runs  (proj {B.proj.mean():.1f} vs realized {B.realized.mean():.1f})")
print(f"  80% interval coverage: {cover*100:.0f}%   (target ~80%)")
print(f"  MAE: {mae:.1f} runs")
# by-position calibration
print("\n  by position (mean proj vs realized):")
for p, g in B.groupby("pos"):
    if len(g) >= 8: print(f"    {p:3} n={len(g):>3}  proj {g.proj.mean():>6.1f}  realized {g.realized.mean():>6.1f}  rank rho {g[['proj','realized']].corr('spearman').iloc[0,1]:+.2f}")
B.to_csv(os.path.join(HOME, "defense_plus/reports/23_backtest.csv"), index=False)
print("\nwrote reports/23_backtest.csv")
