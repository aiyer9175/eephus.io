# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026
"""
Expansion E24 — Depth-chart PA allocator (the projected-regular gap fix).

Our champion predicts each player INDEPENDENTLY, so a team's predictions don't
respect the structural constraint that a team's hitters collectively get a
~fixed PA budget. E23 showed the residual Steamer gap is exactly on projected
regulars (pred>=500: ours MAE 101.6 vs Steamer 83.6) — Steamer allocates a
team PA pie down a depth chart; we don't.

Allocator: per (team, target_year), take champion predictions as role-strength,
WATER-FILL them to the team's OD-hitter PA budget with a per-player cap, so
regulars rise toward full-time PA and the team respects the constraint.

Leakage-safe:
  team        = Opening-Day active roster (statsapi), known preseason
  budget      = TRAINING-years (<=2022) mean realized PA among a team's
                OD-roster hitters (a structural constant, no test leakage)
  cap         = training 99th-pct realized PA
Players not on an OD active roster keep the raw champion prediction.

Reports raw vs allocated vs blend(raw,allocated) vs Steamer, overall + by
predicted-PA band. Incumbent universe, test 2023-25.
Output: research/E24_allocator.md
"""
import sys

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor

PT = "/Users/willcahoon/playing_time_model"
EXP = f"{PT}/expansion"
sys.path.insert(0, f"{PT}/pipeline")
import ptm_lib as L  # noqa: E402

lines = ["# Expansion E24 — Depth-Chart PA Allocator", ""]


def log(s=""):
    lines.append(s)
    print(s)


# ---------- champion assembly (M02-21) ----------
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
F = CHAMP + TXALL + ODF + PANELF + ["on_il_at_od"] + SEVF

# OD active-roster team per (player, target_year) — reflects offseason moves.
# champion_pairs carries a feature-year team_id from the spine; drop it.
inc = inc.drop(columns=[c for c in ["team_id"] if c in inc.columns])
team = (ros[ros.roster_type == "active"][["mlbam_id", "target_year", "team_id"]]
        .drop_duplicates(["mlbam_id", "target_year"]))
inc = inc.merge(team, on=["mlbam_id", "target_year"], how="left")

# champion predictions
train = inc[inc.target_year <= 2022].copy()
test = inc[inc.target_year.isin([2023, 2024, 2025])].copy()
mdl = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05,
                                    random_state=7).fit(train[F].fillna(0), train.pa_next)
train["pred"] = np.clip(mdl.predict(train[F].fillna(0)), 0, None)
test["pred"] = np.clip(mdl.predict(test[F].fillna(0)), 0, None)

# ---------- budget + cap from TRAINING only (leakage-safe constants) ----------
tr_team = train.dropna(subset=["team_id"])
budget = (tr_team.groupby(["target_year", "team_id"]).pa_next.sum()
          .groupby(level=0).mean().mean())          # avg OD-hitter PA per team
cap = train.pa_next.quantile(0.99)
log(f"- budget (training mean OD-hitter PA per team): {budget:.0f}; cap (99th pct): {cap:.0f}")


def water_fill(preds, budget, cap, iters=6):
    p = preds.astype(float).copy()
    for _ in range(iters):
        s = p.sum()
        if s <= 0:
            break
        free = p < cap - 1e-6
        scale = (budget - p[~free].sum()) / p[free].sum() if p[free].sum() > 0 else 1.0
        p[free] = np.minimum(p[free] * scale, cap)
        if abs(p.sum() - budget) < 1.0 or not free.any():
            break
    return p


test["alloc"] = test.pred
has_team = test.team_id.notna()
for (ty, tid), g in test[has_team].groupby(["target_year", "team_id"]):
    test.loc[g.index, "alloc"] = water_fill(g.pred.values, budget, cap).clip(0, cap)
test["alloc_blend"] = 0.5 * test.pred + 0.5 * test.alloc

# Steamer
pub = pd.read_parquet(f"{PT}/data/raw/public_projections.parquet")
st = (pub[pub.system == "steamer"][["mlbam_id", "season", "pa_proj"]]
      .rename(columns={"season": "target_year", "pa_proj": "pa_steamer"}))
test = test.merge(st, on=["mlbam_id", "target_year"], how="left")
log(f"- test incumbents: {len(test)}; with OD team {has_team.mean():.0%}")

c = test[test.pa_steamer.notna()].copy(); y = c.pa_next.values


def M(name, p):
    err = p - y; ss = ((y - y.mean()) ** 2).sum()
    return {"model": name, "R2": round(1 - (err ** 2).sum() / ss, 4),
            "MAE": round(float(np.abs(err).mean()), 1),
            "RMSE": round(float(np.sqrt((err ** 2).mean())), 1),
            "rho": round(float(spearmanr(p, y).statistic), 4)}


log("\n## Overall (incumbents, test 2023-25)")
log(pd.DataFrame([M("champion (raw)", c.pred.values),
                  M("allocator", c.alloc.values),
                  M("blend raw+alloc", c.alloc_blend.values),
                  M("Steamer", c.pa_steamer.values),
                  M("blend alloc+Steamer", 0.5 * c.alloc + 0.5 * c.pa_steamer)]).to_string(index=False))

log("\n## By PREDICTED-PA band (where the allocator should act)")
for lo, hi, lab in [(500, 9999, "pred>=500"), (300, 500, "pred 300-500"),
                    (0, 300, "pred<300")]:
    s = c[(c.pred >= lo) & (c.pred < hi)]
    if len(s) < 10:
        continue
    f = lambda col: np.abs(s[col] - s.pa_next).mean()
    log(f"- {lab} (n={len(s)}): raw {f('pred'):.1f} | alloc {f('alloc'):.1f} | "
        f"blend {f('alloc_blend'):.1f} | Steamer {f('pa_steamer'):.1f}")

log("\n## Verdict")
log("Allocator ships if it closes the projected-regular gap (pred>=500 toward")
log("Steamer 83.6) without hurting overall.")

with open(f"{EXP}/research/E24_allocator.md", "w") as f:
    f.write("\n".join(lines) + "\n")
print("\nreport written")
