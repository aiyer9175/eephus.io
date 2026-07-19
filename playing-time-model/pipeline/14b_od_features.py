# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026
"""
Module 14b — Opening Day roster features (the depth-chart layer, Model C lite).

Features per (player, target_year), all known at the prediction date:
  on_40man_od       on a 40-man roster Mar 25
  on_active_od      on an active roster Apr 2 (~Opening Day)
  od_pos_depth      teammates on same 40-man sharing his roster position
  od_team_pos_players  position players on that 40-man (squeeze measure)

Evaluation frame: PRESEASON (stack + tx). Watch the winter-DFA segment where
Steamer's MAE was 40 vs our 59 (Module 13b) — this is the targeted fix.

Output: reports/14_od_features.md, data/processed/od_features.parquet
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

import ptm_lib as L

OUT = "/Users/willcahoon/playing_time_model"

lines = ["# Module 14b — Opening Day Roster Features", ""]


def log(s=""):
    lines.append(s)
    print(s)


ros = pd.read_parquet(f"{OUT}/data/raw/od_rosters.parquet")
ros = ros[ros.mlbam_id.notna()].copy()
ros["mlbam_id"] = ros.mlbam_id.astype(int)

m40 = ros[(ros.roster_type == "40Man") & (ros.position != "P")].copy()
act = ros[(ros.roster_type == "active") & (ros.position != "P")]

depth = (m40.groupby(["target_year", "team_id", "position"])
            .mlbam_id.transform("size") - 1)
m40["od_pos_depth"] = depth
m40["od_team_pos_players"] = (m40.groupby(["target_year", "team_id"])
                                 .mlbam_id.transform("size"))

f40 = (m40.sort_values("od_pos_depth")
          .drop_duplicates(["mlbam_id", "target_year"], keep="last")
          [["mlbam_id", "target_year", "od_pos_depth",
            "od_team_pos_players"]])
f40["on_40man_od"] = 1
fact = (act[["mlbam_id", "target_year"]].drop_duplicates()
        .assign(on_active_od=1))

od = f40.merge(fact, on=["mlbam_id", "target_year"], how="outer")
od["on_40man_od"] = od.on_40man_od.fillna(0)
od["on_active_od"] = od.on_active_od.fillna(0)
od.to_parquet(f"{OUT}/data/processed/od_features.parquet", index=False)
log(f"- od features: {od.shape}, years "
    f"{od.target_year.min()}-{od.target_year.max()}")

ODF = ["on_40man_od", "on_active_od", "od_pos_depth", "od_team_pos_players"]

# ---- evaluation on the preseason frame
pairs, CHAMP = L.champion_pairs()
pairs["target_year"] = pairs.season + 1

txf = pd.read_parquet(f"{OUT}/data/processed/tx_features.parquet")
pairs = pairs.merge(txf, on=["mlbam_id", "target_year"], how="left")
TXALL = [c for c in txf.columns if c not in ("mlbam_id", "target_year")]
known = pairs.target_year >= 2004
pairs.loc[known, TXALL] = pairs.loc[known, TXALL].fillna(0)

pairs = pairs.merge(od, on=["mlbam_id", "target_year"], how="left")
cov = pairs.target_year >= 2004
pairs.loc[cov & (pairs.target_year != 2020),
          ["on_40man_od", "on_active_od"]] = (
    pairs.loc[cov & (pairs.target_year != 2020),
              ["on_40man_od", "on_active_od"]].fillna(0))

pub = pd.read_parquet(f"{OUT}/data/raw/public_projections.parquet")
st = (pub[pub.system == "steamer"]
      [["mlbam_id", "season", "pa_proj", "woba_proj", "g_proj"]]
      .rename(columns={"season": "target_year", "pa_proj": "pa_steamer",
                       "woba_proj": "woba_steamer", "g_proj": "g_steamer"}))
pairs = pairs.merge(st, on=["mlbam_id", "target_year"], how="left")
STACK = CHAMP + ["pa_steamer", "woba_steamer", "g_steamer"]

sanity = pairs[(pairs.target_year >= 2005) & (pairs.target_year <= 2025)
               & (pairs.target_year != 2020)]
log(f"- sanity: of pairs with on_active_od=1, next-year PA mean "
    f"{sanity[sanity.on_active_od == 1].pa_next.mean():.0f} vs not-on-OD "
    f"{sanity[sanity.on_active_od == 0].pa_next.mean():.0f}")

train, test = L.split(pairs)


def fit_pred(F):
    m = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05,
                                      random_state=7)
    m.fit(train[F], train.pa_next)
    return np.clip(m.predict(test[F]), 0, None)


test = test.copy()
FPRE = STACK + TXALL
preds = {"F-pre (13b)": fit_pred(FPRE), "F-pre + OD": fit_pred(FPRE + ODF)}

common = test.pa_steamer.notna()
tt = test[common].copy()
log(f"\n## PRESEASON frame, common universe (n={common.sum()})")
res = [L.evaluate("Steamer preseason", tt.pa_steamer.values, tt)]
for k, v in preds.items():
    res.append(L.evaluate(k, v[common.values], tt))
blend = 0.5 * preds["F-pre + OD"][common.values] + 0.5 * tt.pa_steamer.values
res.append(L.evaluate("blend (F-pre+OD, Steamer)/2", blend, tt))
log(pd.DataFrame(res).to_string(index=False))

tt["pa_old"] = preds["F-pre (13b)"][common.values]
tt["pa_new"] = preds["F-pre + OD"][common.values]
log("\n## Segments (MAE: steamer | F-pre | F-pre+OD)")
for nm, mask in {"off_des_out_clw>0": tt.off_des_out_clw > 0,
                 "pa_t<200": tt.pa_adj < 200,
                 "age<=25": tt.age <= 25,
                 "not on OD active": tt.on_active_od == 0,
                 "on OD active": tt.on_active_od == 1}.items():
    s = tt[mask]
    if len(s) < 20:
        log(f"- {nm}: n={len(s)}")
        continue
    a = L.evaluate("s", s.pa_steamer.values, s)
    b = L.evaluate("o", s.pa_old.values, s)
    c = L.evaluate("n", s.pa_new.values, s)
    log(f"- {nm} (n={len(s)}): MAE {a['MAE']} | {b['MAE']} | {c['MAE']}   "
        f"rho {a['Spearman']} | {b['Spearman']} | {c['Spearman']}")

with open(f"{OUT}/reports/14_od_features.md", "w") as f:
    f.write("\n".join(lines) + "\n")
print("\nreport written")
