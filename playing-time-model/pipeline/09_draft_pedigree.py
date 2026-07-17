# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026
"""
Module 9 — Draft pedigree (ladder rung E2).

Fixes Module 6's coverage problem: draft position exists for every training
year (1990-2025) and is timestamp-valid forever. Tests whether teams give
extra runway to high picks beyond usage + talent + minors usage.

Features: overall_pick, log_bonus, drafted (0 = intl signing),
          years_since_draft, top10_pick, first_rounder.

Baseline here = current champion (rung F': FEATS_B + minors usage).

Output: reports/09_draft_pedigree.md
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

import ptm_lib as L

OUT = "/Users/willcahoon/playing_time_model"
DRAFT = f"{OUT}/data/raw/draft_history.parquet"
DEEP_MIN = "/Users/willcahoon/projection_engine/data/deep_minors.parquet"

lines = ["# Module 9 — Draft Pedigree (Rung E2)", ""]


def log(s=""):
    lines.append(s)
    print(s)


# rebuild champion features (minors usage, as in Module 7)
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
MINORS = ["pa_aaa_adj", "pa_milb_adj", "woba_aaa", "mlb_share", "shuttle"]
CHAMP = L.FEATS_B + MINORS

# draft features
dr = pd.read_parquet(DRAFT)
pairs = pairs.merge(dr[["mlbam_id", "draft_year", "overall_pick",
                        "signing_bonus"]], on="mlbam_id", how="left")
pairs["drafted"] = pairs.draft_year.notna().astype(int)
pairs["years_since_draft"] = pairs.season - pairs.draft_year
pairs["log_bonus"] = np.log1p(pairs.signing_bonus)
pairs["top10_pick"] = (pairs.overall_pick <= 10).astype(int)
pairs["first_rounder"] = (pairs.overall_pick <= 30).astype(int)
DRAFTF = ["overall_pick", "log_bonus", "drafted", "years_since_draft",
          "top10_pick", "first_rounder"]
log(f"- drafted share of pairs: {pairs.drafted.mean():.1%} "
    f"(0 = international signing)")

train, test = L.split(pairs)
rows, models = [], {}
for name, F in [("F' champion", CHAMP), ("E2 + draft pedigree", CHAMP + DRAFTF)]:
    m = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05,
                                      random_state=7)
    m.fit(train[F], train.pa_next)
    rows.append(L.evaluate(name, m.predict(test[F]), test))
    models[name] = (m, F)

log("\n## Pooled holdout (targets 2023-2025)")
log(pd.DataFrame(rows).to_string(index=False))

mE, FE = models["E2 + draft pedigree"]
mC, FC = models["F' champion"]
log("\n## Segments")
segs = {"age<=25": test.age <= 25, "first_rounder": test.first_rounder == 1,
        "top10_pick": test.top10_pick == 1, "pa_t<200": test.pa_adj < 200,
        "yrs_since_draft<=4": test.years_since_draft <= 4}
for nm, mask in segs.items():
    tt = test[mask]
    if len(tt) < 20:
        log(f"- {nm}: n={len(tt)} too small")
        continue
    c = L.evaluate("c", mC.predict(tt[FC]), tt)
    e = L.evaluate("e", mE.predict(tt[FE]), tt)
    log(f"- {nm} (n={len(tt)}): MAE {c['MAE']} -> {e['MAE']}, "
        f"R2 {c['R2']} -> {e['R2']}, rho {c['Spearman']} -> {e['Spearman']}")

with open(f"{OUT}/reports/09_draft_pedigree.md", "w") as f:
    f.write("\n".join(lines) + "\n")
print("\nreport written")
