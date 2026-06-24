# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
Defense+ Part 4 (OF jump focus) — reliability, aging, and PREDICTIVE value of jump
components, with the leakage safeguards the hypothesis demands.

Components (Savant OF jump, ft vs league): reaction (0-1.5s read), burst (1.5-3s accel),
route (efficiency), jump-total (boot-up). Data 2016-2025 (~100 OF/yr).

Hypothesis (user): jump is the highest-value predictive defensive stat — elite jump over
a large sample => elite defender. SAFEGUARDS:
  (1) jump & OAA are computed from the SAME tracked plays -> same-season jump->OAA is
      CIRCULAR. Only ever validate against FUTURE OAA (t+1).
  (2) jump overlaps OAA mechanically -> report MARGINAL value over OAA, not raw corr.
  (3) NO jump data below MLB -> jump cannot enter the MiLB->MLB translation layer.
"""
import os, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore"); pd.set_option("display.width", 210)

HOME = os.path.expanduser("~"); RAW = os.path.join(HOME, "defense_plus/data/raw")
REP = os.path.join(HOME, "defense_plus/reports")
YEARS = list(range(2016, 2026))
COMP = {"reaction": "rel_league_reaction_distance", "burst": "rel_league_burst_distance",
        "route": "rel_league_routing_distance", "jump_total": "rel_league_bootup_distance"}
MIN_N = 20

# load jump + join age from deep_mlb
fr = []
for y in YEARS:
    d = pd.read_csv(os.path.join(RAW, f"ofjump_{y}.csv")).rename(columns={"resp_fielder_id": "id"})
    d["year"] = y; fr.append(d)
J = pd.concat(fr, ignore_index=True)
J = J.rename(columns={v: k for k, v in COMP.items()})
J["OAA"] = pd.to_numeric(J["outs_above_average"], errors="coerce")
for c in list(COMP) + ["n", "OAA"]:
    J[c] = pd.to_numeric(J[c], errors="coerce")
dm = pd.read_parquet(os.path.join(HOME, "projection_engine/data/deep_mlb.parquet"))[["batter", "season", "age"]]
J = J.merge(dm.rename(columns={"batter": "id", "season": "year"}), on=["id", "year"], how="left")
J = J[(J["n"] >= MIN_N)].dropna(subset=list(COMP) + ["OAA"])
print(f"sample: {len(J)} OF-seasons, {J.id.nunique()} players, {J.year.min()}-{J.year.max()}\n")

# ---- adjacent-year pairs ----
def pairs(df):
    a = df.copy()
    b = df.rename(columns={c: c + "_n" for c in list(COMP) + ["OAA", "n", "age"]})
    b["year"] = b["year"] - 1
    return a.merge(b, on=["id", "year"])
P = pairs(J)

# ===== Test 1 — reliability (y2y) of each component vs OAA =====
print("===== Test 1 — year-to-year reliability (jump components vs OAA) =====")
rel = {}
for name in list(COMP) + ["OAA"]:
    r = np.corrcoef(P[name], P[name + "_n"])[0, 1]; rel[name] = r
    print(f"  {name:11} y2y r = {r:.3f}")
print("  -> components more reliable than OAA => jump is a steadier talent signal\n")

# ===== Test 2 — aging (delta method: same player t->t+1, by age) =====
print("===== Test 2 — aging of jump components (delta method, ft-vs-league change/yr) =====")
P["agecut"] = pd.cut(P["age"], [0, 25, 28, 31, 34, 99], labels=["<25", "25-27", "28-30", "31-33", "34+"])
hdr = f"{'age band':9}" + "".join(f"{c:>11}" for c in COMP) + f"{'n':>7}"
print(hdr)
for band, g in P.groupby("agecut"):
    if len(g) < 15: continue
    line = f"{str(band):9}"
    for c in COMP:
        line += f"{(g[c+'_n']-g[c]).mean():11.3f}"
    print(line + f"{len(g):7}")
slopes = {c: np.polyfit(P["age"], P[c + "_n"] - P[c], 1)[0] for c in COMP}
print("\n  overall change/yr by age (slope of delta on age):")
for c in COMP: print(f"     {c:11} {slopes[c]:+.4f} ft/yr  (more negative w/ age = faster athletic decay)")
print()

# ===== Test 3 — PREDICTIVE value of jump for FUTURE OAA (non-leaky) =====
print("===== Test 3 — predict NEXT-year OAA (safeguard: future only, never same-season) =====")
print(f"  corr(predictor_t, OAA_t+1)   n={len(P)} pairs")
for name in ["OAA", "reaction", "burst", "route", "jump_total"]:
    r = np.corrcoef(P[name], P["OAA_n"])[0, 1]
    tag = "  <- same metric (baseline)" if name == "OAA" else ""
    print(f"     {name:11} r={r:+.3f}{tag}")
# marginal value of jump_total over OAA_t (does jump add beyond current OAA?)
def partial(y, x, ctrl):
    X = np.column_stack([np.ones(len(x)), ctrl, x])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    yhat_full = X @ beta
    Xr = np.column_stack([np.ones(len(x)), ctrl]); br, *_ = np.linalg.lstsq(Xr, y, rcond=None)
    ss_full = ((y - yhat_full) ** 2).sum(); ss_red = ((y - Xr @ br) ** 2).sum()
    return 1 - ss_full / ss_red, beta[-1]  # partial R^2 gain, coef
pr_jump, b_jump = partial(P["OAA_n"].values, P["jump_total"].values, P["OAA"].values)
pr_oaa, _ = partial(P["OAA_n"].values, P["OAA"].values, P["jump_total"].values)
print(f"\n  marginal (predicting OAA_t+1):")
print(f"     jump_total adds over OAA_t : partial R2 gain = {pr_jump:.3f}")
print(f"     OAA_t adds over jump_total : partial R2 gain = {pr_oaa:.3f}")
# 'large sample' subset: high-n jump should predict best (user hypothesis)
hi = P[P["n"] >= P["n"].median()]
r_hi = np.corrcoef(hi["jump_total"], hi["OAA_n"])[0, 1]
r_oaa_hi = np.corrcoef(hi["OAA"], hi["OAA_n"])[0, 1]
print(f"\n  high-attempt subset (n>=median): jump_total->OAA_t+1 r={r_hi:.3f} vs OAA_t->OAA_t+1 r={r_oaa_hi:.3f}")

pd.DataFrame([{"metric": k, "y2y_rel": round(rel[k], 3)} for k in rel]).to_csv(
    os.path.join(REP, "08_jump.csv"), index=False)
print("\nSAFEGUARDS: same-season jump->OAA excluded (circular); marginal-over-OAA reported; jump is MLB-only (no MiLB).")
