# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
Defense+ Part 4 — UPGRADE jump aging to the joint-dropout model (audit fix).

Module 09 used player random intercepts but no dropout model. Here we use the
gold-standard `~/mlb-aging-curves/bayesian_curves.fit_joint_dropout` (hierarchical
+ shared-parameter dropout hazard) so dynamic survivorship is corrected. Compare the
corrected 27->33 decline to Module 09's player-intercept-only estimate.
"""
import os, sys, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.expanduser("~/mlb-aging-curves"))
import bayesian_curves as bc

HOME = os.path.expanduser("~"); RAW = os.path.join(HOME, "defense_plus/data/raw")
REP = os.path.join(HOME, "defense_plus/reports")
YEARS = list(range(2016, 2026))
COMP = {"reaction": "rel_league_reaction_distance", "burst": "rel_league_burst_distance",
        "route": "rel_league_routing_distance", "jump_total": "rel_league_bootup_distance"}
M09 = {"burst": -0.62, "OAA": -0.55, "jump_total": -0.49, "reaction": -0.19, "route": +0.20}  # 27->33, player-intercept

fr = []
for y in YEARS:
    d = pd.read_csv(os.path.join(RAW, f"ofjump_{y}.csv")).rename(columns={"resp_fielder_id": "id"}); d["year"] = y; fr.append(d)
J = pd.concat(fr, ignore_index=True).rename(columns={v: k for k, v in COMP.items()})
J["OAA"] = pd.to_numeric(J["outs_above_average"], errors="coerce")
for c in list(COMP) + ["n", "OAA"]:
    J[c] = pd.to_numeric(J[c], errors="coerce")
dm = pd.read_parquet(os.path.join(HOME, "projection_engine/data/deep_mlb.parquet"))[["batter", "season", "age"]]
J = J.merge(dm.rename(columns={"batter": "id", "season": "year"}), on=["id", "year"], how="left")
J = J[(J["n"] >= 20)].dropna(subset=list(COMP) + ["OAA", "age"]).copy()
for c in list(COMP) + ["OAA"]:
    J[c + "z"] = J.groupby("year")[c].transform(lambda x: (x - x.mean()) / x.std())

def curve_at(res, age):
    i = int(np.argmin(np.abs(res["age_grid"] - age)))
    return res["curve_mean"][i]

print(f"=== jump aging via JOINT-DROPOUT model (vs Module-09 player-intercept) ===")
print(f"{'signal':11}{'slope@27':>10}{'27->33 (joint)':>16}{'M09 27->33':>12}{'gamma(drop~abil)':>18}")
rows = []
for sig in ["burst", "OAA", "jump_total", "reaction", "route"]:
    d = J[["id", "year", "age", sig + "z", "n"]].rename(
        columns={"id": "player_id", "year": "Season", "age": "Age", sig + "z": "skill", "n": "wt"})
    dp = bc.prepare(d, "skill", "wt", min_weight=20)
    res = bc.fit_joint_dropout(dp, "skill", "wt", draws=600, tune=600, chains=2, cores=2, random_seed=1)
    c27, c33, c26, c28 = curve_at(res, 27), curve_at(res, 33), curve_at(res, 26), curve_at(res, 28)
    decline = c33 - c27
    slope27 = (c28 - c26) / 2.0
    gamma = float(np.median(res["gamma_post"]))
    rows.append(dict(signal=sig, slope_at27=round(slope27, 3), decline_27to33=round(decline, 2),
                     m09_27to33=M09[sig], gamma=round(gamma, 2), r2_age=round(res["r2_age"], 3)))
    print(f"{sig:11}{slope27:>10.3f}{decline:>16.2f}{M09[sig]:>12.2f}{gamma:>18.2f}")

R = pd.DataFrame(rows); R.to_csv(os.path.join(REP, "10_jump_joint.csv"), index=False)
# save curve for the headline signals
out = {}
for sig in ["burst", "OAA", "reaction", "route"]:
    d = J[["id", "year", "age", sig + "z", "n"]].rename(
        columns={"id": "player_id", "year": "Season", "age": "Age", sig + "z": "skill", "n": "wt"})
    dp = bc.prepare(d, "skill", "wt", min_weight=20)
    res = bc.fit_joint_dropout(dp, "skill", "wt", draws=600, tune=600, chains=2, cores=2, random_seed=2)
    g = res["age_grid"]; cm = res["curve_mean"]; c27 = cm[int(np.argmin(np.abs(g - 27)))]
    out[sig] = pd.Series(cm - c27, index=g)
cv = pd.DataFrame(out); cv.index.name = "age"; cv.to_csv(os.path.join(REP, "10_jump_joint_curves.csv"))
print("\ngamma>0 => higher-ability players survive longer (survivorship mechanism present).")
print(f"wrote reports/10_jump_joint.csv, reports/10_jump_joint_curves.csv")
