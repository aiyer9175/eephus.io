# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026
"""
Expansion E23 — SHIP isotonic top-end calibration into the full-population model.

E22 diagnosis: the champion under-projects 500+ PA iron-men (regression to the
mean). Isotonic recalibration of predicted->realized lifts the top end. Shipped
here as a permanent step:

  * calibrator fit on OUT-OF-FOLD train predictions (5-fold), NOT in-sample
    (in-sample preds under-correct) -> proper monotone recalibration.
  * fit SEPARATELY per slice (incumbent vs prospect PA distributions differ).
  * applied to the deployed full-population projection.

Writes the canonical calibrated deliverable and reports calibrated vs raw vs
Steamer (full pop + by slice + by PA band).

Output: data/processed/full_population_proj.parquet (calibrated, canonical),
        data/processed/full_population_proj_raw.parquet (pre-calibration),
        research/E23_calibration_ship.md
"""
import sys

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import (HistGradientBoostingClassifier,
                              HistGradientBoostingRegressor)
from sklearn.isotonic import IsotonicRegression
from sklearn.model_selection import KFold

PT = "/Users/willcahoon/playing_time_model"
EXP = f"{PT}/expansion"
DEEP_MIN = "/Users/willcahoon/projection_engine/data/deep_minors.parquet"
sys.path.insert(0, f"{PT}/pipeline")
import ptm_lib as L  # noqa: E402

lines = ["# Expansion E23 — Ship Isotonic Top-End Calibration", ""]


def log(s=""):
    lines.append(s)
    print(s)


def oof_isotonic(model_fac, X, y):
    """fit calibrator on 5-fold OOF preds; return fitted IsotonicRegression."""
    oof = np.zeros(len(y))
    yv = y.values
    for tr, va in KFold(5, shuffle=True, random_state=7).split(X):
        m = model_fac().fit(X.iloc[tr], yv[tr])
        oof[va] = np.clip(m.predict(X.iloc[va]), 0, None)
    return IsotonicRegression(out_of_bounds="clip").fit(oof, yv)


# ============ INCUMBENT slice (champion M02-21) ============
inc, CHAMP = L.champion_pairs()
inc["target_year"] = inc.season + 1
txf = pd.read_parquet(f"{PT}/data/processed/tx_features.parquet")
inc = inc.merge(txf, on=["mlbam_id", "target_year"], how="left")
TXALL = [c for c in txf.columns if c not in ("mlbam_id", "target_year")]
k = inc.target_year >= 2004
inc.loc[k, TXALL] = inc.loc[k, TXALL].fillna(0)
od = pd.read_parquet(f"{PT}/data/processed/od_features.parquet")
inc = inc.merge(od, on=["mlbam_id", "target_year"], how="left")
ODF = ["on_40man_od", "on_active_od", "od_pos_depth", "od_team_pos_players"]
kc = k & (inc.target_year != 2020)
inc.loc[kc, ["on_40man_od", "on_active_od"]] = inc.loc[kc, ["on_40man_od", "on_active_od"]].fillna(0)
ijf = pd.read_parquet(f"{PT}/data/processed/injury_features.parquet")
inc = inc.merge(ijf, on=["mlbam_id", "target_year"], how="left")
PANELF = ["il_stints_t", "il_days_t", "career_il_stints", "career_il_days"]
ki = inc.target_year >= 2016
inc.loc[ki, PANELF] = inc.loc[ki, PANELF].fillna(0)
sev = pd.read_parquet(f"{PT}/data/processed/injury_severity.parquet")
inc = inc.merge(sev, on=["mlbam_id", "target_year"], how="left")
SEVF = ["od_il_level", "od_region_exp_days"]
ros = pd.read_parquet(f"{PT}/data/raw/od_rosters.parquet")
ros = ros[ros.mlbam_id.notna()].astype({"mlbam_id": int})
ilr = (ros[ros.status.isin(["D7", "D10", "D15", "D60"])]
       [["mlbam_id", "target_year"]].drop_duplicates().assign(on_il_at_od=1))
inc = inc.merge(ilr, on=["mlbam_id", "target_year"], how="left")
inc.loc[k, "on_il_at_od"] = inc.loc[k, "on_il_at_od"].fillna(0)
inc.loc[k, SEVF] = inc.loc[k, SEVF].fillna(0)
INC_F = CHAMP + TXALL + ODF + PANELF + ["on_il_at_od"] + SEVF
itr, ite = inc[inc.target_year <= 2022].copy(), inc[inc.target_year.isin([2023, 2024, 2025])].copy()


def inc_fac():
    return HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05, random_state=7)


inc_cal = oof_isotonic(inc_fac, itr[INC_F].fillna(0), itr.pa_next)
inc_mdl = inc_fac().fit(itr[INC_F].fillna(0), itr.pa_next)
ite["pred_raw"] = np.clip(inc_mdl.predict(ite[INC_F].fillna(0)), 0, None)
ite["pred"] = inc_cal.predict(ite.pred_raw)
ite["slice"] = "incumbent"

# ============ PROSPECT slice (E11 direct-mean) ============
mn = pd.read_parquet(DEEP_MIN)
sp = pd.read_parquet(f"{PT}/data/processed/usage_spine.parquet")[["mlbam_id", "season", "pa"]]
mlb = sp.sort_values("season"); mlb["career_pa"] = mlb.groupby("mlbam_id").pa.cumsum()
upm = mn[mn.sport.isin([11, 12])].copy()
lvl = upm.sort_values("sport").groupby(["batter", "season"]).first().reset_index().rename(columns={"batter": "mlbam_id"})
tot = mn.groupby(["batter", "season"]).pa.sum().rename("pa_milb_t").reset_index().rename(columns={"batter": "mlbam_id"})
u = lvl.merge(tot, on=["mlbam_id", "season"]); u = u[u.age <= 30]
u = u.merge(mlb[["mlbam_id", "season", "career_pa"]], on=["mlbam_id", "season"], how="left")
u["career_pa"] = u.sort_values("season").groupby("mlbam_id").career_pa.ffill(); u = u[u.career_pa.isna() | (u.career_pa == 0)]
t2 = tot.copy(); t2["season"] += 1; t2 = t2.rename(columns={"pa_milb_t": "pa_milb_l1"}); u = u.merge(t2, on=["mlbam_id", "season"], how="left")
nxt = sp.rename(columns={"pa": "pa_next"}).copy(); nxt["season"] -= 1; u = u.merge(nxt, on=["mlbam_id", "season"], how="left")
u["pa_next"] = u.pa_next.fillna(0); u["target_year"] = u.season + 1
dr = pd.read_parquet(f"{PT}/data/raw/draft_history.parquet")
u = u.merge(dr[["mlbam_id", "draft_year", "overall_pick", "signing_bonus"]], on="mlbam_id", how="left")
u["drafted"] = u.draft_year.notna().astype(int); u["years_since_draft"] = u.season - u.draft_year; u["log_bonus"] = np.log1p(u.signing_bonus)
tx = pd.read_parquet(f"{PT}/data/raw/transactions.parquet"); tx = tx[tx.mlbam_id.notna()].astype({"mlbam_id": int}); tx["date"] = pd.to_datetime(tx.date)
se = tx[tx.type_code == "SE"].groupby("mlbam_id").date.min().rename("first_se"); u = u.merge(se, on="mlbam_id", how="left")
u["selected_40man"] = (u.first_se <= pd.to_datetime(u.target_year.astype(str) + "-03-25")).astype(int)
u = u.merge(od, on=["mlbam_id", "target_year"], how="left")
ko = u.target_year >= 2004; u.loc[ko, ["on_40man_od", "on_active_od"]] = u.loc[ko, ["on_40man_od", "on_active_od"]].fillna(0)
ped = pd.read_parquet(f"{PT}/data/processed/pedigree_features.parquet")
u = u.merge(ped[["mlbam_id", "season", "fv_latest", "top100_rank", "org_rank"]], on=["mlbam_id", "season"], how="left")
PRO_F = ["age", "sport", "pa", "pa_milb_t", "pa_milb_l1", "woba", "k_pct", "bb_pct", "iso",
         "overall_pick", "log_bonus", "drafted", "years_since_draft", "selected_40man",
         "on_40man_od", "on_active_od", "od_pos_depth", "od_team_pos_players",
         "fv_latest", "top100_rank", "org_rank"]
ptr, pte = u[u.target_year <= 2022].copy(), u[u.target_year.isin([2023, 2024, 2025])].copy()


def pro_fac():
    return HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05, random_state=7)


pro_cal = oof_isotonic(pro_fac, ptr[PRO_F], ptr.pa_next)
pro_mdl = pro_fac().fit(ptr[PRO_F], ptr.pa_next)
pte["pred_raw"] = np.clip(pro_mdl.predict(pte[PRO_F]), 0, None)
pte["pred"] = pro_cal.predict(pte.pred_raw)
pte["slice"] = "prospect"

# ============ unify + Steamer ============
cols = ["mlbam_id", "target_year", "pa_next", "pred_raw", "pred", "slice"]
full = pd.concat([ite[cols], pte[cols]], ignore_index=True)
full = full.sort_values("slice").drop_duplicates(["mlbam_id", "target_year"], keep="first")
pub = pd.read_parquet(f"{PT}/data/raw/public_projections.parquet")
stm = (pub[pub.system == "steamer"][["mlbam_id", "season", "pa_proj"]]
       .rename(columns={"season": "target_year", "pa_proj": "pa_steamer"}))
full = full.merge(stm, on=["mlbam_id", "target_year"], how="left")
full.rename(columns={"pred": "pred"}).to_parquet(f"{EXP}/data/processed/full_population_proj.parquet", index=False)
full.rename(columns={"pred_raw": "pred_uncal"})[["mlbam_id", "target_year", "pa_next", "pred_uncal", "slice"]] \
    .to_parquet(f"{EXP}/data/processed/full_population_proj_raw.parquet", index=False)


def met(name, p, y):
    err = np.asarray(p) - y; ss = ((y - y.mean()) ** 2).sum()
    return {"model": name, "R2": round(1 - (err ** 2).sum() / ss, 4),
            "MAE": round(float(np.abs(err).mean()), 1),
            "RMSE": round(float(np.sqrt((err ** 2).mean())), 1),
            "rho": round(float(spearmanr(p, y).statistic), 4)}


c = full[full.pa_steamer.notna()].copy(); y = c.pa_next.values
log("## Full population — calibrated (shipped) vs raw vs Steamer (n=%d)" % len(c))
log(pd.DataFrame([met("Ours RAW (pre-calib)", c.pred_raw, y),
                  met("Ours CALIBRATED (shipped)", c.pred, y),
                  met("Steamer", c.pa_steamer, y),
                  met("blend calibrated+Steamer", 0.5 * c.pred + 0.5 * c.pa_steamer, y)]).to_string(index=False))
log("\n## By slice (calibrated)")
for s in ["incumbent", "prospect"]:
    d = c[c.slice == s]
    log(f"- {s}: " + str(met("cal", d.pred, d.pa_next.values))
        + " | raw MAE " + str(round(float(np.abs(d.pred_raw - d.pa_next).mean()), 1)))
log("\n## 500+ PA band (the target of the fix)")
hi = c[c.pa_next >= 500]
log(f"- raw  bias {(hi.pred_raw-hi.pa_next).mean():+.1f}  MAE {np.abs(hi.pred_raw-hi.pa_next).mean():.1f}")
log(f"- cal  bias {(hi.pred-hi.pa_next).mean():+.1f}  MAE {np.abs(hi.pred-hi.pa_next).mean():.1f}")

with open(f"{EXP}/research/E23_calibration_ship.md", "w") as f:
    f.write("\n".join(lines) + "\n")
print("\nreport written")
