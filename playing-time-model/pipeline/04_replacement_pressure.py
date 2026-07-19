# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026
"""
Module 4 — Replacement Pressure+ (ladder rung C).

Question: who is competing for the same PA?

Leakage-safe construction: all competitor features come from the SAME team
and SAME season as the feature year t (no offseason-move knowledge, no t+1
depth charts). Team attribution is the spine's last-team-of-season; noisy
for midseason movers (num_teams>1) — accepted and noted.

Features (at the player's primary position, year t):
  share_pos_starts   player GS at primary pos / team GS at that pos
  comp_best_woba     best marcel wOBA among same-team players with >=10 GS there
  comp_n             same-team players with >=20 GS there (excl. player)
  comp_young         1 if any such competitor is age <= 25
  team_pos_hhi       start concentration at the position (Herfindahl) —
                     low = unsettled job, high = locked starter
Rung C = FEATS_B + these. Same split as Module 3.

Output: reports/04_replacement_pressure.md,
        data/processed/replacement_features.parquet
"""
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

import ptm_lib as L

OUT = "/Users/willcahoon/playing_time_model"
POS = ["c", "1b", "2b", "3b", "ss", "lf", "cf", "rf", "dh"]

lines = ["# Module 4 — Replacement Pressure+ (Rung C)", ""]


def log(s=""):
    lines.append(s)
    print(s)


sp = L.prepare_spine()

# long table: one row per player-season-position with GS there
longs = []
for p in POS:
    sub = sp[["mlbam_id", "season", "team_id", "age", "woba_marcel",
              f"gs_{p}"]].rename(columns={f"gs_{p}": "gs_pos"})
    sub["pos"] = p.upper()
    longs.append(sub[sub.gs_pos > 0])
long = pd.concat(longs, ignore_index=True)

grp = long.groupby(["season", "team_id", "pos"])
team_pos = grp.gs_pos.sum().rename("team_pos_gs").reset_index()
hhi = grp.apply(lambda d: ((d.gs_pos / d.gs_pos.sum()) ** 2).sum(),
                include_groups=False).rename("team_pos_hhi").reset_index()

long = long.merge(team_pos, on=["season", "team_id", "pos"])
long = long.merge(hhi, on=["season", "team_id", "pos"])
long["share"] = long.gs_pos / long.team_pos_gs


def comp_feats(d):
    out = []
    for _, r in d.iterrows():
        comp = d[(d.mlbam_id != r.mlbam_id) & (d.gs_pos >= 10)]
        big = comp[comp.gs_pos >= 20]
        out.append((r.mlbam_id,
                    comp.woba_marcel.max() if len(comp) else float("nan"),
                    len(big),
                    int((big.age <= 25).any()) if len(big) else 0))
    return pd.DataFrame(out, columns=["mlbam_id", "comp_best_woba",
                                      "comp_n", "comp_young"])


cf = (long.groupby(["season", "team_id", "pos"])
          .apply(comp_feats, include_groups=False)
          .reset_index()[["season", "team_id", "pos", "mlbam_id",
                          "comp_best_woba", "comp_n", "comp_young"]])
long = long.merge(cf, on=["season", "team_id", "pos", "mlbam_id"])

# attach at the player's primary position
feats = long.rename(columns={"pos": "primary_pos", "share": "share_pos_starts"})
feats = feats[["mlbam_id", "season", "primary_pos", "share_pos_starts",
               "comp_best_woba", "comp_n", "comp_young", "team_pos_hhi"]]

pairs = L.build_pairs(sp)
pairs = pairs.merge(feats, on=["mlbam_id", "season", "primary_pos"],
                    how="left")
NEW = ["share_pos_starts", "comp_best_woba", "comp_n", "comp_young",
       "team_pos_hhi"]
cov = pairs[NEW].notna().mean()
log(f"- coverage of new features on pairs: "
    f"{ {k: round(v, 3) for k, v in cov.items()} }")
log("  (missing = player had 0 starts at any position — pure bench/PH rows)")
pairs["comp_young"] = pairs.comp_young.fillna(0)

feats.to_parquet(f"{OUT}/data/processed/replacement_features.parquet",
                 index=False)

train, test = L.split(pairs)
log(f"- train {len(train)} / test {len(test)}\n")

rows = []
for name, F in [("B  (benchmark)", L.FEATS_B), ("C  + replacement", L.FEATS_B + NEW)]:
    m = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05,
                                      random_state=7)
    m.fit(train[F], train.pa_next)
    rows.append(L.evaluate(name, m.predict(test[F]), test))
    if "replacement" in name:
        mC, FC = m, F

res = pd.DataFrame(rows)
log("## Pooled holdout (targets 2023-2025)")
log(res.to_string(index=False))

log("\n## Segments (Rung C)")
segs = {"age<=25": test.age <= 25, "age 26-31": test.age.between(26, 31),
        "age>=32": test.age >= 32, "pa_t<200": test.pa_adj < 200,
        "pa_t>=400": test.pa_adj >= 400}
for nm, mask in segs.items():
    tt = test[mask]
    log(str(L.evaluate(f"C {nm} (n={len(tt)})", mC.predict(tt[FC]), tt)))

with open(f"{OUT}/reports/04_replacement_pressure.md", "w") as f:
    f.write("\n".join(lines) + "\n")
print("\nreport written")
