# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026
"""
Module 20 — Injury model integration (the MAE channel).

Module 17 showed Steamer's only remaining edge is MAE ~9 PA = winter
injury/news info. This integrates the injury model's GO components
(~/injury_model, handoff README rules respected):

Timestamp-valid construction for the BACKTEST (the handoff's
player_injury_features.csv is a through-2026 snapshot — leaky for
2023-25; rebuilt instead from risk_panel_yoy.parquet, 2015-2024):
  il_stints_t / il_days_t      IL load in feature year t
  career_il_stints/days @ t    cumsum of panel through t (left-trunc 2015)
  p_any_il_next, e_il_games    bucket lookup from risk_rates_by_history
                               (group-level table; fit on full window —
                               mild overlap, flagged; rates near-static)
  on_il_at_od                  D10/D15/D60 status on the 40-man (Mar 25)
                               or active (Apr 2) roster — OUR pull, 2004+

Coverage: panel features exist for targets 2016+ (NaN earlier; GBM-native).
Eval: Steamer-free preseason frame, BASE vs BASE+INJ; MAE-vs-Steamer watch.

Output: data/processed/injury_features.parquet, reports/20_injury.md
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

import ptm_lib as L

OUT = "/Users/willcahoon/playing_time_model"
INJ = "/Users/willcahoon/injury_model/data/processed"

lines = ["# Module 20 — Injury Model Integration", ""]


def log(s=""):
    lines.append(s)
    print(s)


# ---- timestamp-valid injury features from the YoY panel
panel = pd.read_parquet(f"{INJ}/risk_panel_yoy.parquet") \
          .rename(columns={"batter": "mlbam_id"})
panel = panel.sort_values(["mlbam_id", "season"])
panel["career_il_stints"] = panel.groupby("mlbam_id").stints.cumsum()
panel["career_il_days"] = panel.groupby("mlbam_id").days.cumsum()

rates = pd.read_csv(f"{INJ}/playing_time_handoff/risk_rates_by_history.csv")
# bucket labels are "0".."4" plus "5+" -> numeric cap then back to label
cap = max(int(b.rstrip("+")) for b in rates.bucket.astype(str))
panel["bucket"] = panel.career_il_stints.clip(upper=cap).astype(int).astype(str)
panel.loc[panel.career_il_stints >= cap, "bucket"] = f"{cap}+"
rates["bucket"] = rates.bucket.astype(str)
panel = panel.merge(rates[["bucket", "p_any_il_next", "mean_il_games_next"]],
                    on="bucket", how="left")

inj = panel[["mlbam_id", "season", "stints", "days", "career_il_stints",
             "career_il_days", "p_any_il_next", "mean_il_games_next"]] \
    .rename(columns={"stints": "il_stints_t", "days": "il_days_t"})
inj["target_year"] = inj.season + 1
inj = inj.drop(columns="season")
inj.to_parquet(f"{OUT}/data/processed/injury_features.parquet", index=False)
log(f"- panel features: {inj.shape}, target years "
    f"{inj.target_year.min()}-{inj.target_year.max()}")

# OD IL flag from our roster pull (2004+, fully timestamp-valid)
ros = pd.read_parquet(f"{OUT}/data/raw/od_rosters.parquet")
ros = ros[ros.mlbam_id.notna()].astype({"mlbam_id": int})
il = (ros[ros.status.isin(["D7", "D10", "D15", "D60"])]
      [["mlbam_id", "target_year"]].drop_duplicates()
      .assign(on_il_at_od=1))
log(f"- on_il_at_od rows: {len(il)} (D10/D15/D60 at Mar 25 / Apr 2 rosters)")

# ---- evaluation frame (Steamer-free preseason champion)
pairs, CHAMP = L.champion_pairs()
pairs["target_year"] = pairs.season + 1

txf = pd.read_parquet(f"{OUT}/data/processed/tx_features.parquet")
pairs = pairs.merge(txf, on=["mlbam_id", "target_year"], how="left")
TXALL = [c for c in txf.columns if c not in ("mlbam_id", "target_year")]
known = pairs.target_year >= 2004
pairs.loc[known, TXALL] = pairs.loc[known, TXALL].fillna(0)

od = pd.read_parquet(f"{OUT}/data/processed/od_features.parquet")
pairs = pairs.merge(od, on=["mlbam_id", "target_year"], how="left")
ODF = ["on_40man_od", "on_active_od", "od_pos_depth", "od_team_pos_players"]
cov = known & (pairs.target_year != 2020)
pairs.loc[cov, ["on_40man_od", "on_active_od"]] = (
    pairs.loc[cov, ["on_40man_od", "on_active_od"]].fillna(0))

pairs = pairs.merge(inj, on=["mlbam_id", "target_year"], how="left")
pairs = pairs.merge(il, on=["mlbam_id", "target_year"], how="left")
covI = pairs.target_year >= 2016
PANELF = ["il_stints_t", "il_days_t", "career_il_stints", "career_il_days",
          "p_any_il_next", "mean_il_games_next"]
# panel covers >=100-PA hitters; missing within era = low-PA -> 0 history
pairs.loc[covI, PANELF] = pairs.loc[covI, PANELF].fillna(0)
pairs.loc[known, "on_il_at_od"] = pairs.loc[known, "on_il_at_od"].fillna(0)
INJF = PANELF + ["on_il_at_od"]
log(f"- pairs coverage: panel era (2016+) {covI.mean():.0%} of pairs; "
    f"on_il_at_od era (2004+) {known.mean():.0%}")

# steamer for reference
pub = pd.read_parquet(f"{OUT}/data/raw/public_projections.parquet")
st = (pub[pub.system == "steamer"][["mlbam_id", "season", "pa_proj"]]
      .rename(columns={"season": "target_year", "pa_proj": "pa_steamer"}))
pairs = pairs.merge(st, on=["mlbam_id", "target_year"], how="left")

BASE = CHAMP + TXALL + ODF
train, test = L.split(pairs)


def run(F):
    m = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05,
                                      random_state=7)
    m.fit(train[F], train.pa_next)
    return np.clip(m.predict(test[F]), 0, None)


test = test.copy()
preds = {"BASE (no injury)": run(BASE), "BASE + INJ": run(BASE + INJF)}

common = test.pa_steamer.notna()
tt = test[common]
log(f"\n## Steamer-free preseason frame, common universe (n={common.sum()})")
res = [L.evaluate("Steamer (reference)", tt.pa_steamer.values, tt)]
for k, v in preds.items():
    res.append(L.evaluate(k, v[common.values], tt))
blend = 0.5 * preds["BASE + INJ"][common.values] + 0.5 * tt.pa_steamer.values
res.append(L.evaluate("blend (BASE+INJ, Steamer)", blend, tt))
log(pd.DataFrame(res).to_string(index=False))

log("\n## Segments (MAE: steamer | BASE | BASE+INJ)")
tt = tt.assign(p0=preds["BASE (no injury)"][common.values],
               p1=preds["BASE + INJ"][common.values])
segs = {"on_il_at_od=1": tt.on_il_at_od == 1,
        "career_il_stints>=3": tt.career_il_stints >= 3,
        "il_days_t>=30": tt.il_days_t >= 30,
        "no IL history": (tt.career_il_stints == 0) & (tt.on_il_at_od == 0),
        "age>=32": tt.age >= 32}
for nm, mask in segs.items():
    s = tt[mask]
    if len(s) < 20:
        log(f"- {nm}: n={len(s)}")
        continue
    a = L.evaluate("s", s.pa_steamer.values, s)
    b = L.evaluate("b", s.p0.values, s)
    c = L.evaluate("c", s.p1.values, s)
    log(f"- {nm} (n={len(s)}): MAE {a['MAE']} | {b['MAE']} | {c['MAE']}   "
        f"rho {a['Spearman']} | {b['Spearman']} | {c['Spearman']}")

with open(f"{OUT}/reports/20_injury.md", "w") as f:
    f.write("\n".join(lines) + "\n")
print("\nreport written")
