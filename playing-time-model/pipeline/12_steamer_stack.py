# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026
"""
Module 12 — Steamer stack (Model race: opportunity prior + roster layer).

Module 11 showed preseason Steamer beats the October-information champion
(MAE 90 vs 115): its edge is the information date (offseason moves, spring
depth charts). This module moves OUR prediction date to preseason too, by
feeding the archived preseason Steamer PA/wOBA for the target year as a
prior and letting the GBM learn when to deviate using usage history,
minors shuttle, and draft pedigree.

Steamer archives exist 2010+ → stack trains on targets 2010-2022 (steamer
feature NaN earlier; GBM handles natively).

Question: does our layer add value ON TOP of the best public system?

Output: reports/12_steamer_stack.md
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

import ptm_lib as L

OUT = "/Users/willcahoon/playing_time_model"
PUB = f"{OUT}/data/raw/public_projections.parquet"
DRAFT = f"{OUT}/data/raw/draft_history.parquet"
DEEP_MIN = "/Users/willcahoon/projection_engine/data/deep_minors.parquet"

lines = ["# Module 12 — Steamer Stack", ""]


def log(s=""):
    lines.append(s)
    print(s)


# champion features (rung E2, as Module 9)
mn = pd.read_parquet(DEEP_MIN)
aaa = (mn[mn.sport == 11].groupby(["batter", "season"])
       .agg(pa_aaa=("pa", "sum"), woba_aaa=("woba", "mean")).reset_index())
allm = mn.groupby(["batter", "season"]).pa.sum().rename("pa_milb").reset_index()
mfeat = allm.merge(aaa, on=["batter", "season"], how="left") \
            .rename(columns={"batter": "mlbam_id"})

pairs = L.build_pairs()
pairs = pairs.merge(mfeat, on=["mlbam_id", "season"], how="left")
pre = pairs.season < 2008
pairs.loc[~pre, ["pa_milb", "pa_aaa"]] = (
    pairs.loc[~pre, ["pa_milb", "pa_aaa"]].fillna(0))
pairs["pa_aaa_adj"] = pairs.pa_aaa * pairs.scale
pairs["pa_milb_adj"] = pairs.pa_milb * pairs.scale
pairs["mlb_share"] = pairs.pa / (pairs.pa + pairs.pa_milb).replace(0, np.nan)
pairs["shuttle"] = ((pairs.pa > 0) & (pairs.pa_milb >= 50)).astype(float)
pairs.loc[pre, "shuttle"] = np.nan

dr = pd.read_parquet(DRAFT)
pairs = pairs.merge(dr[["mlbam_id", "draft_year", "overall_pick",
                        "signing_bonus"]], on="mlbam_id", how="left")
pairs["drafted"] = pairs.draft_year.notna().astype(int)
pairs["years_since_draft"] = pairs.season - pairs.draft_year
pairs["log_bonus"] = np.log1p(pairs.signing_bonus)
pairs["top10_pick"] = (pairs.overall_pick <= 10).astype(int)
pairs["first_rounder"] = (pairs.overall_pick <= 30).astype(int)

CHAMP = (L.FEATS_B
         + ["pa_aaa_adj", "pa_milb_adj", "woba_aaa", "mlb_share", "shuttle"]
         + ["overall_pick", "log_bonus", "drafted", "years_since_draft",
            "top10_pick", "first_rounder"])

# preseason Steamer for the TARGET year (legitimate at a preseason
# prediction date — this redefines the deliverable as a March projection)
pub = pd.read_parquet(PUB)
st = pub[pub.system == "steamer"][["mlbam_id", "season", "pa_proj",
                                   "woba_proj", "g_proj"]]
st = st.rename(columns={"season": "target_year", "pa_proj": "pa_steamer",
                        "woba_proj": "woba_steamer", "g_proj": "g_steamer"})
pairs["target_year"] = pairs.season + 1
pairs = pairs.merge(st, on=["mlbam_id", "target_year"], how="left")
log(f"- Steamer feature coverage by era: "
    f"pre-2010 targets {pairs[pairs.target_year < 2010].pa_steamer.notna().mean():.0%}, "
    f"2010+ targets {pairs[pairs.target_year >= 2010].pa_steamer.notna().mean():.0%}")

STACK = CHAMP + ["pa_steamer", "woba_steamer", "g_steamer"]

train, test = L.split(pairs)
fits = {}
for name, F in [("champion", CHAMP), ("stack", STACK)]:
    m = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05,
                                      random_state=7)
    m.fit(train[F], train.pa_next)
    fits[name] = (m, F)

test = test.copy()
test["pa_champ"] = np.clip(fits["champion"][0].predict(test[CHAMP]), 0, None)
test["pa_stack"] = np.clip(fits["stack"][0].predict(test[STACK]), 0, None)

common = test[test.pa_steamer.notna()].copy()
common["pa_blend"] = 0.5 * common.pa_stack + 0.5 * common.pa_steamer
log(f"\n## Head-to-head, common universe (n={len(common)}, targets 2023-25)")
rows = [
    L.evaluate("Steamer preseason", common.pa_steamer.values, common),
    L.evaluate("Champion (Oct info)", common.pa_champ.values, common),
    L.evaluate("STACK (champ + Steamer prior)", common.pa_stack.values, common),
    L.evaluate("50/50 stack+Steamer blend", common.pa_blend.values, common),
]
log(pd.DataFrame(rows).to_string(index=False))

log("\n## Segments (MAE: steamer | stack)")
for nm, mask in {"age<=25": common.age <= 25,
                 "pa_t<200": common.pa_adj < 200,
                 "pa_t>=400": common.pa_adj >= 400,
                 "shuttle=1": common.shuttle == 1,
                 "2023": common.target_year == 2023,
                 "2024": common.target_year == 2024,
                 "2025": common.target_year == 2025}.items():
    s = common[mask]
    a = L.evaluate("s", s.pa_steamer.values, s)
    b = L.evaluate("k", s.pa_stack.values, s)
    log(f"- {nm} (n={len(s)}): MAE {a['MAE']} | {b['MAE']}   "
        f"rho {a['Spearman']} | {b['Spearman']}")

with open(f"{OUT}/reports/12_steamer_stack.md", "w") as f:
    f.write("\n".join(lines) + "\n")
print("\nreport written")
