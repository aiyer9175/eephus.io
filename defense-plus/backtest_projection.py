# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
backtest_projection.py — walk-forward backtest of the multi-year aging-aware
defensive projection. For each target year T (2021-2025): project using only
seasons <= T-1, compare to realized composite def at T (Inn>=300, stable).
Compares naive(single T-1) vs blend(no aging) vs blend+aging, and checks
def_sd interval calibration.
"""

import glob
import numpy as np
import pandas as pd
from pathlib import Path
from scipy.stats import spearmanr

ROOT = Path(__file__).parent
N0 = 400.0
MARCEL_W = {0: 6.0, 1: 3.0, 2: 1.0}
SYS = ["OAA", "DRS", "FRP"]


def composite_panel():
    files = glob.glob(str(ROOT / "data/raw/fg_field_full_20*.csv"))
    d = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    d = d[d["Inn"] >= 50].rename(columns={"xMLBAMID": "batter"}).copy()
    d["batter"] = pd.to_numeric(d["batter"], errors="coerce").astype("Int64")
    drs_sd = d.groupby("Pos")["DRS"].std()
    rows = []
    for (pos, seas), g in d.groupby(["Pos", "Season"]):
        z = pd.DataFrame({s: (g[s] - g[s].mean()) / g[s].std() for s in SYS if g[s].std() > 0})
        gg = g.assign(dz=z.mean(axis=1))
        gg["rel"] = gg["Inn"] / (gg["Inn"] + N0)
        gg["dval"] = gg["dz"] * drs_sd.get(pos, 8) * gg["rel"]
        rows.append(gg[["batter", "Season", "Pos", "Inn", "rel", "dval"]])
    return pd.concat(rows).dropna(subset=["batter"]), drs_sd


def main():
    p, drs_sd = composite_panel()
    ac = pd.read_csv(ROOT / "reports" / "11_position_aging_curves.csv").set_index("age")
    deep = pd.read_parquet(Path.home() / "projection_engine/data/deep_mlb.parquet")
    deep["batter"] = pd.to_numeric(deep["batter"], errors="coerce").astype("Int64")
    age_map = deep.set_index(["batter", "season"])["age"].to_dict()

    recs = []
    for T in range(2021, 2026):
        realized = p[(p.Season == T) & (p.Inn >= 300)][["batter", "Pos", "dval"]].rename(columns={"dval": "real"})
        for _, rz in realized.iterrows():
            bid = rz["batter"]; pos = rz["Pos"]
            hist = p[(p.batter == bid) & (p.Season.between(T - 3, T - 1))].sort_values("Season")
            if hist.empty:
                continue
            lag = (T - 1 - hist["Season"]).clip(0, 2); w = lag.map(MARCEL_W).values * hist["rel"].values
            if w.sum() == 0:
                continue
            base = np.average(hist["dval"].values, weights=w)
            rel_tot = hist["rel"].sum() / (hist["rel"].sum() + 1.0)
            blend = base * (0.6 + 0.4 * rel_tot)
            naive = hist[hist.Season == T - 1]["dval"].values
            naive = float(naive[0]) if len(naive) else blend
            # aging shift
            age_T = age_map.get((bid, T), np.nan); d_age = 0.0
            if pos in ac.columns and not np.isnan(age_T):
                s_bar = np.average(hist["Season"].values, weights=w)
                a0 = int(round(age_T - (T - s_bar))); a1 = int(round(age_T))
                a0, a1 = max(a0, ac.index.min()), min(a1, ac.index.max())
                if a0 in ac.index and a1 in ac.index and pd.notna(ac.loc[a0, pos]) and pd.notna(ac.loc[a1, pos]):
                    d_age = ac.loc[a1, pos] - ac.loc[a0, pos]
            aged = blend + d_age
            sd = np.sqrt(1 - rel_tot) * drs_sd.get(pos, 8) + (1.5 if hist.Season.nunique() == 1 else 0.0)
            recs.append({"T": T, "pos": pos, "real": rz["real"], "naive": naive, "blend": blend, "aged": aged, "sd": sd})
    r = pd.DataFrame(recs)
    print(f"backtest n={len(r)} player-years (2021-25, realized Inn>=300)")
    for col in ["naive", "blend", "aged"]:
        rho = spearmanr(r[col], r["real"]).correlation
        mae = (r[col] - r["real"]).abs().mean(); bias = (r[col] - r["real"]).mean()
        print(f"  {col:6s}  Spearman {rho:.3f}  MAE {mae:.2f}  bias {bias:+.2f}")
    # SHIPPED config: headline = blend (no aging), def_sd with +1.7 drift
    r["sd_ship"] = np.sqrt(r["sd"] ** 2 + 1.7 ** 2)
    z = (r["real"] - r["blend"]) / r["sd_ship"]
    print(f"\n  SHIPPED (blend + drift) coverage: 50%={100*(z.abs()<=0.674).mean():.0f}% 80%={100*(z.abs()<=1.282).mean():.0f}% 90%={100*(z.abs()<=1.645).mean():.0f}%")
    # MI specifically
    mi = r[r.pos.isin(["SS", "2B"])]
    print(f"\n  MI (SS/2B) n={len(mi)}: aged Spearman {spearmanr(mi['aged'],mi['real']).correlation:.3f} MAE {(mi['aged']-mi['real']).abs().mean():.2f}; 80% cov {100*((mi['real']-mi['aged']).abs()<=1.282*mi['sd']).mean():.0f}%")
    print(f"  MI naive Spearman {spearmanr(mi['naive'],mi['real']).correlation:.3f} (does multi-yr+aging beat single season for MI?)")


if __name__ == "__main__":
    main()
