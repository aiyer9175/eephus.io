# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
Defense+ Part 4 — general position aging (joint-dropout, the audit-blessed standard).

How does defensive value age, and where does each position peak? Run the
survivorship-corrected `~/mlb-aging-curves/fit_joint_dropout` per position. Dropout =
not playing that position next year (so an aging SS forced to 3B counts as a SS exit ->
the model corrects the "survivor SS look young" bias). Metric: OAA (2016-2025) for the
seven non-C positions; DRS for catchers (no catcher OAA). Weight = innings.
"""
import os, sys, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.expanduser("~/mlb-aging-curves"))
import bayesian_curves as bc

HOME = os.path.expanduser("~"); RAW = os.path.join(HOME, "defense_plus/data/raw")
REP = os.path.join(HOME, "defense_plus/reports")
YEARS = list(range(2016, 2026))
POS_METRIC = {"C": "DRS", "SS": "OAA", "2B": "OAA", "3B": "OAA",
              "CF": "OAA", "LF": "OAA", "RF": "OAA", "1B": "OAA"}
MIN_INN = 300

fr = []
for y in YEARS:
    d = pd.read_csv(os.path.join(RAW, f"fg_field_full_{y}.csv")).rename(columns={"xMLBAMID": "id"})
    d["year"] = y; fr.append(d)
F = pd.concat(fr, ignore_index=True)
for c in ["id", "Inn", "OAA", "DRS"]:
    F[c] = pd.to_numeric(F[c], errors="coerce")
F = F[F.id.notna()].copy(); F["id"] = F.id.astype(int)
dm = pd.read_parquet(os.path.join(HOME, "projection_engine/data/deep_mlb.parquet"))[["batter", "season", "age"]]
F = F.merge(dm.rename(columns={"batter": "id", "season": "year"}), on=["id", "year"], how="left")

def peak_and_decline(res):
    g, cm = res["age_grid"], res["curve_mean"]
    m = (g >= 21) & (g <= 37)
    gg, cc = g[m], cm[m]
    peak_age = int(gg[int(np.argmax(cc))])
    def at(a): return cm[int(np.argmin(np.abs(g - a)))]
    return peak_age, at(peak_age) - at(33), at(27) - at(33)   # peak->33 and 27->33 declines (runs)

rows, curves = [], {}
for pos, metric in POS_METRIC.items():
    d = F[(F.Pos == pos) & (F.Inn >= MIN_INN)].dropna(subset=[metric, "age", "Inn"]).copy()
    d = d[["id", "year", "age", metric, "Inn"]].rename(
        columns={"id": "player_id", "year": "Season", "age": "Age", metric: "skill", "Inn": "wt"})
    if d["player_id"].nunique() < 60:
        print(f"{pos}: too few players ({d.player_id.nunique()})"); continue
    dp = bc.prepare(d, "skill", "wt", min_weight=MIN_INN)
    res = bc.fit_joint_dropout(dp, "skill", "wt", draws=500, tune=500, chains=2, cores=2, random_seed=1)
    pk, decl_pk33, decl_2733 = peak_and_decline(res)
    gamma = float(np.median(res["gamma_post"]))
    rows.append(dict(pos=pos, metric=metric, peak_age=pk, decline_peak_to_33=round(decl_pk33, 1),
                     decline_27_33=round(decl_2733, 1), gamma=round(gamma, 2),
                     n=res["n_obs"], players=res["n_players"]))
    g = res["age_grid"]; cm = res["curve_mean"]; c_pk = cm[int(np.argmin(np.abs(g - pk)))]
    curves[pos] = pd.Series(cm - c_pk, index=g)   # centered at own peak
    print(f"{pos:3} [{metric}] peak~{pk}  peak->33 decline={decl_pk33:+.1f} runs  "
          f"27->33={decl_2733:+.1f}  gamma={gamma:+.2f}  (n={res['n_obs']}, players={res['n_players']})", flush=True)

R = pd.DataFrame(rows).sort_values("peak_age")
R.to_csv(os.path.join(REP, "11_position_aging.csv"), index=False)
cv = pd.DataFrame(curves); cv.index.name = "age"; cv.to_csv(os.path.join(REP, "11_position_aging_curves.csv"))
print("\n=== POSITION DEFENSIVE AGING (joint-dropout, runs vs own peak) ===")
print(R.to_string(index=False))
print(f"\nwrote reports/11_position_aging.csv, reports/11_position_aging_curves.csv")
