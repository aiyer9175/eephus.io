# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
Defense+ — complete the catcher component model: framing + throwing + BLOCKING.
Blocking was the missing component. Assemble value composition (which component
differentiates catcher value), reliability, and aging.
"""
import os, sys, time, warnings
import numpy as np, pandas as pd, requests
from io import StringIO
warnings.filterwarnings("ignore"); pd.set_option("display.width", 200)
sys.path.insert(0, os.path.expanduser("~/mlb-aging-curves")); import bayesian_curves as bc
HOME = os.path.expanduser("~"); RAW = os.path.join(HOME, "defense_plus/data/raw")
H = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
dm = pd.read_parquet(os.path.join(HOME, "projection_engine/data/deep_mlb.parquet"))[["batter", "season", "age"]].rename(columns={"batter": "id", "season": "year", "age": "p_age"})

def block_year(y):
    fp = os.path.join(RAW, f"blocking_{y}.csv")
    if not os.path.exists(fp):
        u = f"https://baseballsavant.mlb.com/leaderboard/catcher-blocking?year={y}&csv=true"
        pd.read_csv(StringIO(requests.get(u, headers=H, timeout=45).text)).to_csv(fp, index=False); time.sleep(0.3)
    return pd.read_csv(fp)

def load(stem, years, idc, valc, sampc, blocking=False):
    fr = []
    for y in years:
        d = block_year(y) if blocking else pd.read_csv(os.path.join(RAW, f"{stem}_{y}.csv"))
        d["year"] = y; fr.append(d)
    D = pd.concat(fr).rename(columns={idc: "id"})
    D["val"] = pd.to_numeric(D[valc], errors="coerce"); D["wt"] = pd.to_numeric(D[sampc], errors="coerce")
    return D.dropna(subset=["val"])

YR = range(2018, 2026)
fram = load("framing", YR, "id", "rv_tot", "pitches")
blok = load("blocking", YR, "player_id", "catcher_blocking_runs", "pitches", blocking=True)
pop = load("poptime", YR, "entity_id", "pop_2b_sba", "pop_2b_sba_count")

print("=== catcher value composition: run-value SD by component (bigger SD = differentiates value more) ===")
print(f"  FRAMING runs:  SD = {fram.val.std():.1f}  (mean |val| {fram.val.abs().mean():.1f})")
print(f"  BLOCKING runs: SD = {blok.val.std():.1f}  (mean |val| {blok.val.abs().mean():.1f})")
print("  -> framing dominates catcher defensive value; blocking is a small component\n")

def yoy(D):
    pr = []
    for y in YR:
        a = D[D.year == y][["id", "val"]]; b = D[D.year == y + 1][["id", "val"]].rename(columns={"val": "v2"})
        pr.append(a.merge(b, on="id"))
    P = pd.concat(pr).dropna()
    return P.val.corr(P.v2) if len(P) >= 25 else np.nan
print("=== reliability (y2y) ===")
print(f"  framing  r={yoy(fram):.2f}   blocking r={yoy(blok):.2f}   pop time r={yoy(pop):.2f}")

def fitage(D, minw, inv=False):
    d = D.merge(dm, on=["id", "year"], how="left").dropna(subset=["val", "p_age", "wt"])
    d["val"] = d.val * (-1 if inv else 1)
    d["valz"] = d.groupby("year")["val"].transform(lambda x: (x - x.mean()) / x.std())
    d = d.dropna(subset=["valz"]).rename(columns={"id": "player_id", "year": "Season", "p_age": "Age", "valz": "skill"})
    dp = bc.prepare(d, "skill", "wt", min_weight=minw)
    r = bc.fit_joint_dropout(dp, "skill", "wt", draws=500, tune=600, chains=2, cores=2, random_seed=1)
    g = r["age_grid"]; at = lambda a: r["curve_mean"][int(np.argmin(np.abs(g - a)))]
    return at(33) - at(27)
print("\n=== aging (27->33, SD) — completing framing/throwing/blocking ===")
print(f"  framing:  -0.41 (prior)   throwing/pop: -0.32 (prior)   blocking: {fitage(blok, 500):+.2f}")
print(f"\nwrote blocking_*.csv cache")
