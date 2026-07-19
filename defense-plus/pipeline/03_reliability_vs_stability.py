# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
Defense+ Module 03 — separating measurement RELIABILITY from true talent STABILITY.

Date-windowed pulls are blocked (FG/Savant ignore startdate/enddate/month for
fielding), so a literal within-season split-half is unavailable. Instead we use
the attenuation structure we already have:

    observed year-to-year corr at exposure n  ≈  rho_true * reliability(n)
    reliability(n) = n / (n + n0)          (Spearman-Brown form; n0 = innings at Rel=0.5)
 => r(n) = rho_true * n / (n + n0)

Fitting that curve across innings bins recovers BOTH:
  * n0          = stabilization point  -> pure measurement reliability / sample-hunger
  * rho_true    = year-to-year TRUE talent stability, net of noise -> the "real change" (aging/dev) signal
  * Rel(full)   = reliability at a full season (~1300 inn) = how much of one season's number is signal

Metric is z-scored within position-year so positions pool on one scale. Exposure =
min(Inn_t, Inn_t+1) of the pair (the binding sample). Pairs require Inn>=100 both yrs.
"""
import os, warnings
import numpy as np, pandas as pd
from scipy.optimize import curve_fit
warnings.filterwarnings("ignore"); pd.set_option("display.width", 220)

ROOT = os.path.expanduser("~/defense_plus")
RAW = os.path.join(ROOT, "data/raw"); REP = os.path.join(ROOT, "reports")
YEARS = [2021, 2022, 2023, 2024, 2025]
METRICS = ["OAA", "DRS", "UZR"]
FULL_SEASON_INN = 1300.0

# ---- load cached FG fielding, build z-scored long table ----
frames = []
for y in YEARS:
    d = pd.read_csv(os.path.join(RAW, f"fg_field_{y}.csv"))
    d = d.rename(columns={"xMLBAMID": "id"})
    d["id"] = pd.to_numeric(d["id"], errors="coerce")
    for c in ["Inn"] + METRICS:
        if c in d.columns: d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d[(d["id"].notna()) & (d["Pos"] != "P")].copy()
    d["id"] = d["id"].astype(int); d["year"] = y
    frames.append(d)
L = pd.concat(frames, ignore_index=True)

# z-score each metric within position-year (only over reasonably-sampled players)
for m in METRICS:
    base = L[L["Inn"] >= 100]
    mu = base.groupby(["Pos", "year"])[m].transform("mean")
    sd = base.groupby(["Pos", "year"])[m].transform("std")
    L[m + "_z"] = (L[m] - mu) / sd

# ---- build adjacent-year pairs ----
def pairs_for(metric):
    z = metric + "_z"
    out = []
    for pos, g in L.groupby("Pos"):
        for y in YEARS[:-1]:
            a = g[(g.year == y) & (g["Inn"] >= 100)][["id", z, "Inn"]].rename(columns={z: "v1", "Inn": "inn1"})
            b = g[(g.year == y + 1) & (g["Inn"] >= 100)][["id", z, "Inn"]].rename(columns={z: "v2", "Inn": "inn2"})
            mm = a.merge(b, on="id")
            out.append(mm)
    P = pd.concat(out, ignore_index=True).dropna(subset=["v1", "v2"])
    P["exposure"] = P[["inn1", "inn2"]].min(axis=1)
    return P

def model(n, rho, n0):
    return rho * n / (n + n0)

print("===== RELIABILITY vs STABILITY decomposition (FG fielding, pooled positions) =====\n")
summary = []
NBINS = 7
for m in METRICS:
    P = pairs_for(m)
    P = P[P["exposure"] >= 100]
    # quantile bins by exposure
    P["bin"] = pd.qcut(P["exposure"], NBINS, labels=False, duplicates="drop")
    rows = []
    for b, gb in P.groupby("bin"):
        if len(gb) < 25: continue
        rows.append((gb["exposure"].median(), gb["v1"].corr(gb["v2"]), len(gb)))
    B = pd.DataFrame(rows, columns=["inn", "r", "n"]).dropna()
    # fit r(n) = rho * n/(n+n0)
    try:
        popt, _ = curve_fit(model, B["inn"], B["r"], p0=[0.7, 600],
                            bounds=([0.05, 20], [1.0, 8000]), maxfev=20000)
        rho, n0 = popt
        rel_full = FULL_SEASON_INN / (FULL_SEASON_INN + n0)
        summary.append(dict(metric=m, rho_true=round(rho, 3), n0_inn=int(n0),
                            rel_full_season=round(rel_full, 3),
                            r_full_pred=round(rho * rel_full, 3), n_pairs=len(P)))
        print(f"## {m}: rho_true={rho:.3f}  n0={int(n0)} inn (Rel=0.5)  Rel(full~1300inn)={rel_full:.2f}")
        print("   exposure(inn) ->   r_obs   (n pairs)")
        for _, rr in B.iterrows():
            print(f"     {rr.inn:6.0f}        {rr.r:5.2f}    ({int(rr.n)})")
        print()
    except Exception as e:
        print(f"## {m}: fit failed {e}\n")

S = pd.DataFrame(summary)
S.to_csv(os.path.join(REP, "03_reliability_vs_stability.csv"), index=False)
print("================= SUMMARY =================")
print(S.to_string(index=False))
print("""
Read guide:
  rho_true        = year-to-year stability of TRUE talent (1.0 = no real change; <1 = genuine aging/dev/role change)
  n0_inn          = innings to reach 0.5 reliability (sample-hunger; bigger = noisier per inning)
  rel_full_season = fraction of a full season's metric that is signal (vs luck/noise)
""")
print(f"wrote {os.path.join(REP,'03_reliability_vs_stability.csv')}")
